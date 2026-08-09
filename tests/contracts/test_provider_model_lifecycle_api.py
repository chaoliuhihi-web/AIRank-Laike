from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from apps.api import main as api_main
from apps.api import provider_model_lifecycle


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def validate_schema(name: str, payload: object) -> None:
    migration_schema = load_schema("provider_model_migration_response.schema.json")
    registry = Registry().with_resource(
        migration_schema["$id"], Resource.from_contents(migration_schema)
    )
    contract = load_schema(name)
    Draft202012Validator.check_schema(contract)
    Draft202012Validator(
        contract, registry=registry, format_checker=FormatChecker()
    ).validate(payload)


def migration_record(status: str = "planned", version: int = 1) -> dict[str, object]:
    now = datetime(2026, 8, 9, 6, 0, tzinfo=timezone.utc)
    return {
        "contract_version": "airank.provider-model-migration.v1",
        "migration_id": "pmm_" + "a" * 32,
        "tenant_id": "tenant_demo",
        "provider": "deepseek",
        "route_id": "deepseek:default",
        "from_model": "deepseek-v3.2",
        "to_model": "deepseek-v4-pro",
        "from_configuration_fingerprint": "b" * 64,
        "status": status,
        "plan_version": version,
        "validation_request_audit_id": "pra_target_l3" if version >= 2 else None,
        "validation_provider_request_id_present": version >= 2,
        "validation_configuration_fingerprint": "c" * 64 if version >= 2 else None,
        "validation_requested_at": now if version >= 2 else None,
        "reason": "migrate before announced model sunset",
        "created_by": "provider_admin",
        "validated_by": "provider_admin" if version >= 2 else None,
        "approved_by": "release_admin" if status == "approved" else None,
        "created_at": now,
        "updated_at": now,
        "validated_at": now if version >= 2 else None,
        "approved_at": now if status == "approved" else None,
        "latest_event_sha256": "d" * 64,
        "event_chain_status": "valid",
        "validation_evidence_status": "valid" if version >= 2 else "missing",
        "release_eligible": status == "approved",
        "events": [],
    }


def test_provider_model_migration_contract_and_tenant_scope(monkeypatch) -> None:
    class FakeRepository:
        def list(self, tenant_id: str):
            assert tenant_id == "tenant_demo"
            return [migration_record()]

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    monkeypatch.setattr(provider_model_lifecycle, "repository", lambda: FakeRepository())

    response = TestClient(api_main.app).get(
        "/api/v1/admin/provider-model-migrations",
        headers={"tenant-id": "tenant_demo", "X-AIRank-Trace-Id": "trc_model_migration"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["migrations"][0]["status"] == "planned"
    validate_schema("provider_model_migration_portfolio_response.schema.json", response.json())


def test_provider_model_migration_create_validate_and_approve_are_audited(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeRepository:
        def create(self, tenant_id, payload, **kwargs):
            calls.append(("create", {"tenant_id": tenant_id, "payload": payload, **kwargs}))
            return migration_record()

        def bind_validation(self, tenant_id, migration_id, payload, **kwargs):
            calls.append(("validate", {"tenant_id": tenant_id, "migration_id": migration_id, "payload": payload, **kwargs}))
            return migration_record("validated", 2)

        def approve(self, tenant_id, migration_id, payload, **kwargs):
            calls.append(("approve", {"tenant_id": tenant_id, "migration_id": migration_id, "payload": payload, **kwargs}))
            return migration_record("approved", 3)

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    monkeypatch.setattr(provider_model_lifecycle, "repository", lambda: FakeRepository())
    client = TestClient(api_main.app)
    create = client.post(
        "/api/v1/admin/provider-model-migrations",
        headers={"Idempotency-Key": "migration-deepseek-20260809"},
        json={
            "provider": "deepseek",
            "route_id": "deepseek:default",
            "from_model": "deepseek-v3.2",
            "to_model": "deepseek-v4-pro",
            "from_configuration_fingerprint": "b" * 64,
            "reason": "migrate before announced model sunset",
        },
    )
    validate = client.post(
        "/api/v1/admin/provider-model-migrations/pmm_" + "a" * 32 + "/validate",
        json={
            "request_audit_id": "pra_target_l3",
            "expected_version": 1,
            "reason": "bind target model L3 evidence",
        },
    )
    approve = client.post(
        "/api/v1/admin/provider-model-migrations/pmm_" + "a" * 32 + "/approve",
        json={"expected_version": 2, "reason": "approve verified migration"},
    )

    assert [create.status_code, validate.status_code, approve.status_code] == [201, 200, 200]
    assert [item[0] for item in calls] == ["create", "validate", "approve"]
    assert calls[0][1]["idempotency_key"] == "migration-deepseek-20260809"
    assert calls[1][1]["payload"].request_audit_id == "pra_target_l3"
    assert approve.json()["data"]["status"] == "approved"
    validate_schema("provider_model_migration_response.schema.json", approve.json())


def test_provider_model_migration_requires_admin_permission(monkeypatch) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    response = TestClient(api_main.app).get("/api/v1/admin/provider-model-migrations")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from apps.api import main as api_main
from apps.api.provider_usage import MySQLProviderUsageLedger
from airank_provider_gateway import ProviderGatewayError


ROOT = Path(__file__).resolve().parents[2]


def validate_response(schema_name: str, payload: dict) -> None:
    schema = json.loads(
        (ROOT / "packages" / "contracts" / schema_name).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def price_record() -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "price_version_id": "provider_price_test",
        "provider": "qianwen",
        "route_id": "qianwen:default",
        "model": "qwen-test",
        "catalog_version": 1,
        "currency": "CNY",
        "pricing_unit": "per_1m_tokens",
        "input_price_per_million": "2.00000000",
        "output_price_per_million": "8.00000000",
        "effective_from": now,
        "effective_until": None,
        "source_kind": "official_price_page",
        "source_reference": "https://example.test/qianwen-pricing",
        "source_sha256": "a" * 64,
        "reason": "verified official price version",
        "created_by": "provider-admin",
        "created_at": now,
    }


def usage_ledger_record() -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "contract": "airank.provider-usage-ledger.v1",
        "events": [
            {
                "usage_event_id": "provider_usage_test",
                "project_id": "project_test",
                "request_audit_id": "audit_test",
                "provider": "qianwen",
                "route_id": "qianwen:default",
                "model": "qwen-test",
                "outcome": "failed",
                "provider_request_id_present": True,
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "usage_precision": "exact",
                "usage_source": "provider_response",
                "raw_usage_sha256": "b" * 64,
                "cost_amount": "0.000600000000",
                "cost_currency": "CNY",
                "cost_precision": "estimated",
                "cost_source": "catalog_calculated",
                "price_version_id": "provider_price_test",
                "calculation_sha256": "c" * 64,
                "occurred_at": now,
                "created_at": now,
            }
        ],
        "summary": {
            "event_count": 1,
            "exact_usage_count": 1,
            "estimated_usage_count": 0,
            "unknown_usage_count": 0,
            "exact_cost_count": 0,
            "estimated_cost_count": 1,
            "unknown_cost_count": 0,
            "known_cost_event_count": 1,
            "cost_coverage_rate": 1.0,
            "known_cost_amount": "0.000600000000",
            "known_cost_currency": "CNY",
            "aggregate_cost_precision": "estimated",
        },
        "filters": {
            "provider": "qianwen",
            "project_id": None,
            "usage_precision": None,
            "cost_precision": "estimated",
            "occurred_from": None,
            "occurred_until": None,
            "limit": 50,
        },
    }


def test_provider_usage_ledger_filters_precision_and_keeps_failure_usage(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeLedger:
        def list_usage(self, **kwargs):
            calls.append(kwargs)
            return usage_ledger_record()

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    monkeypatch.setattr(api_main, "build_provider_usage_ledger", lambda: FakeLedger())
    response = TestClient(api_main.app).get(
        "/api/v1/admin/provider-usage?provider=qianwen&cost_precision=estimated&limit=50",
        headers={"tenant-id": "tenant_usage_test", "X-AIRank-Trace-Id": "trc_usage"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["events"][0]["outcome"] == "failed"
    assert body["data"]["events"][0]["cost_precision"] == "estimated"
    assert body["data"]["summary"]["known_cost_amount"] == "0.000600000000"
    assert calls[0]["tenant_id"] == "tenant_usage_test"
    assert calls[0]["cost_precision"] == "estimated"
    validate_response("provider_usage_ledger_response.schema.json", body)


def test_provider_price_create_is_versioned_evidenced_and_admin_scoped(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeLedger:
        def create_price_version(self, **kwargs):
            calls.append(kwargs)
            return {
                **price_record(),
                "backfilled_usage_count": 4,
                "replay_status": "created",
            }

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_usage_test")
    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "airank:provider:admin")
    monkeypatch.setattr(api_main, "build_provider_usage_ledger", lambda: FakeLedger())
    api_main._DEV_AUTH_SESSIONS.clear()
    payload = {
        "provider": "qianwen",
        "route_id": "qianwen:default",
        "model": "qwen-test",
        "currency": "CNY",
        "input_price_per_million": "2",
        "output_price_per_million": "8",
        "effective_from": datetime.now(timezone.utc).isoformat(),
        "source_kind": "official_price_page",
        "source_reference": "https://example.test/qianwen-pricing",
        "expected_previous_version": 0,
        "reason": "verified official price version",
    }
    client = TestClient(api_main.app)
    forbidden = client.post("/api/v1/admin/provider-prices", json=payload)
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "provider-admin", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]
    response = client.post(
        "/api/v1/admin/provider-prices",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "X-AIRank-User-Id": "provider-admin",
            "tenant-id": "tenant_usage_test",
        },
    )

    assert forbidden.status_code == 401
    assert response.status_code == 201
    assert calls[0]["tenant_id"] == "tenant_usage_test"
    assert calls[0]["expected_previous_version"] == 0
    assert response.json()["data"]["backfilled_usage_count"] == 4
    validate_response("provider_price_version_create_request.schema.json", payload)
    validate_response("provider_price_version_response.schema.json", response.json())


def test_provider_price_portfolio_is_tenant_scoped(monkeypatch) -> None:
    class FakeLedger:
        def list_price_versions(self, *, tenant_id):
            assert tenant_id == "tenant_usage_test"
            return [price_record()]

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    monkeypatch.setattr(api_main, "build_provider_usage_ledger", lambda: FakeLedger())
    response = TestClient(api_main.app).get(
        "/api/v1/admin/provider-prices",
        headers={"tenant-id": "tenant_usage_test"},
    )

    assert response.status_code == 200
    validate_response("provider_price_portfolio_response.schema.json", response.json())


def test_provider_price_evidence_rejects_inline_credentials_before_database_use() -> None:
    ledger = MySQLProviderUsageLedger("sqlite+pysqlite:///:memory:")

    with pytest.raises(ProviderGatewayError) as error:
        ledger.create_price_version(
            tenant_id="tenant_usage_test",
            provider_key="qianwen",
            route_id="qianwen:default",
            model_name="qwen-test",
            currency="CNY",
            input_price_per_million="2",
            output_price_per_million="8",
            effective_from=datetime.now(timezone.utc),
            effective_until=None,
            source_kind="manual_verified",
            source_reference="api_key=must-not-be-persisted",
            expected_previous_version=0,
            reason="manual price verification",
            created_by="provider-admin",
        )

    assert error.value.code == "PROVIDER_PRICE_INVALID"

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import delivery_routes
from apps.api.main import app
from apps.api.operation_guard import InMemoryOperationGuard


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def validate_schema(name: str, payload: object) -> None:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


class AuditDeliveryRepository(delivery_routes.InMemoryDeliveryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.guard = InMemoryOperationGuard()
        self.claim = self.guard.claim(
            tenant_id="tenant_publish",
            operation_type="publisher.publish",
            resource_key="package_publish_guard",
            idempotency_key="publish-operation-contract-key",
            request_sha256="a" * 64,
            request_key_id=None,
            actor="publisher-contract-worker",
            trace_id="job_publish_contract",
        )
        self.guard.mark_external_started(
            self.claim.operation_id,
            "publisher-contract-worker",
            "job_publish_contract",
        )

    def list_attempts(self, tenant_id: str, package_id: str) -> list[delivery_routes.PublishAttemptData]:
        if tenant_id != "tenant_publish" or package_id != "package_publish_guard":
            raise delivery_routes._not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
        return [
            delivery_routes.PublishAttemptData(
                attempt_id="publish_attempt_123456789abc",
                package_id=package_id,
                attempt_number=1,
                channel="http",
                status="outcome_unknown",
                request_sha256="a" * 64,
                operation_id=self.claim.operation_id,
                operation_state="external_started",
                external_effect_started=True,
                reconciliation_required=True,
                error_code="PUBLISH_NETWORK_FAILED",
                error_message="response was not received",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        ]

    def get_operation(self, tenant_id: str, operation_id: str) -> delivery_routes.PublishOperationData:
        record = self.guard.get_audit(tenant_id, operation_id)
        if record is None or record.operation_type != "publisher.publish":
            raise delivery_routes._not_found("OPERATION_NOT_FOUND", {"operation_id": operation_id})
        return delivery_routes._publish_operation_data(record)


def test_publish_attempt_and_operation_evidence_are_schema_valid_and_tenant_scoped(monkeypatch) -> None:
    repository = AuditDeliveryRepository()
    monkeypatch.setattr(delivery_routes, "DELIVERY_REPOSITORY", repository)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    client = TestClient(app)

    attempts = client.get(
        "/api/v1/publish-packages/package_publish_guard/attempts",
        headers={"tenant-id": "tenant_publish"},
    )
    assert attempts.status_code == 200
    assert attempts.json()["data"][0]["status"] == "outcome_unknown"
    assert attempts.json()["data"][0]["reconciliation_required"] is True
    validate_schema("publish_attempt_list_response.schema.json", attempts.json())

    operation = client.get(
        f"/api/v1/publish-operations/{repository.claim.operation_id}",
        headers={"tenant-id": "tenant_publish"},
    )
    assert operation.status_code == 200
    assert operation.json()["data"]["replay_status"] == "forbidden_unknown"
    assert [event["event_sequence"] for event in operation.json()["data"]["events"]] == [1, 2]
    validate_schema("publish_operation_response.schema.json", operation.json())

    cross_tenant = client.get(
        f"/api/v1/publish-operations/{repository.claim.operation_id}",
        headers={"tenant-id": "tenant_other"},
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "OPERATION_NOT_FOUND"


def test_publish_operation_detail_requires_delivery_admin_permission(monkeypatch) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    delivery_routes.require_delivery_admin("airank:delivery:admin")
    with pytest.raises(StarletteHTTPException) as forbidden:
        delivery_routes.require_delivery_admin("airank:provider:admin")
    assert forbidden.value.status_code == 403
    assert forbidden.value.detail["details"]["required_permission"] == "airank:delivery:admin"

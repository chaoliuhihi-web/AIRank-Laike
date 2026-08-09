from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import delivery_routes
from apps.api import main as api_main
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


def test_publication_mutation_requires_admin_and_uses_authenticated_actor(monkeypatch) -> None:
    class MutationRepository(delivery_routes.InMemoryDeliveryRepository):
        captured: delivery_routes.PublishMutationCreateRequest | None = None

        def create_mutation(self, tenant_id, package_id, payload):
            self.captured = payload
            return delivery_routes.PublishPackageData(
                package_id="package_mutation_contract",
                tenant_id=tenant_id,
                project_id="project_contract",
                asset_id="asset_contract",
                snapshot_id="snapshot_contract",
                content_review_id="review_contract",
                channel="http",
                status="queued",
                implementation_status="partial",
                idempotency_key=payload.idempotency_key,
                content_sha256="b" * 64,
                created_at=datetime.now(timezone.utc),
                publication_action=payload.action,
                target_package_id=package_id,
                action_reason=payload.reason,
                requested_by=payload.requested_by,
            )

    repository = MutationRepository()
    monkeypatch.setattr(delivery_routes, "DELIVERY_REPOSITORY", repository)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_publish")
    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "console:read")
    api_main._DEV_AUTH_SESSIONS.clear()
    client = TestClient(app)
    payload = {
        "action": "withdraw",
        "idempotency_key": "publish-withdraw-contract-1",
        "reason": "客户授权撤回当前页面并要求保留完整审计记录。",
        "requested_by": "spoofed-browser-actor",
    }

    ordinary_token = client.post(
        "/api/v1/auth/login",
        json={"username": "ordinary-publisher", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]
    forbidden = client.post(
        "/api/v1/publish-packages/package_original/mutations",
        headers={
            "tenant-id": "tenant_publish",
            "Authorization": f"Bearer {ordinary_token}",
            "X-AIRank-Permissions": "airank:delivery:admin",
        },
        json=payload,
    )
    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "airank:delivery:admin")
    admin_token = client.post(
        "/api/v1/auth/login",
        json={"username": "publisher-admin", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]
    allowed = client.post(
        "/api/v1/publish-packages/package_original/mutations",
        headers={
            "tenant-id": "tenant_publish",
            "Authorization": f"Bearer {admin_token}",
            "X-AIRank-User-Id": "spoofed-browser-actor",
        },
        json=payload,
    )

    assert forbidden.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["data"]["requested_by"] == "publisher-admin"
    assert repository.captured is not None
    assert repository.captured.requested_by == "publisher-admin"


def test_publication_mutation_request_schema_separates_update_and_withdraw() -> None:
    validate_schema(
        "publish_mutation_create_request.schema.json",
        {
            "action": "update",
            "replacement_asset_id": "asset_revision_2",
            "idempotency_key": "publish-update-contract-2",
            "reason": "使用审核后的第二版事实内容更新客户页面。",
            "requested_by": "publisher-admin",
        },
    )
    validate_schema(
        "publish_mutation_create_request.schema.json",
        {
            "action": "withdraw",
            "replacement_asset_id": None,
            "idempotency_key": "publish-withdraw-contract-2",
            "reason": "客户撤回授权，页面必须转为不可公开状态。",
            "requested_by": "publisher-admin",
        },
    )
    with pytest.raises(ValidationError):
        validate_schema(
            "publish_mutation_create_request.schema.json",
            {
                "action": "update",
                "idempotency_key": "publish-update-contract-3",
                "reason": "更新请求缺少替换资产，应当被契约拒绝。",
                "requested_by": "publisher-admin",
            },
        )

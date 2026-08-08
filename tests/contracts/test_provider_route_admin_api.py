from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from airank_provider_gateway import ProviderGatewayError
from apps.api import main as api_main


ROOT = Path(__file__).resolve().parents[2]


def validate_response(schema_name: str, payload: dict) -> None:
    schema = json.loads(
        (ROOT / "packages" / "contracts" / schema_name).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def route_record() -> dict[str, object]:
    return {
        "provider": "qianwen",
        "label": "千问",
        "route_id": "qianwen:default",
        "endpoint_host": "dashscope.aliyuncs.com",
        "model": "qwen-test",
        "request_kind": "responses_web_search",
        "configured": True,
        "enabled": True,
        "base_priority": 0,
        "effective_priority": 0,
        "priority_override": None,
        "control_version": 0,
        "updated_by": None,
        "reason": None,
        "updated_at": None,
        "configuration_fingerprint": "a" * 64,
        "request_count_24h": 3,
        "success_count_24h": 3,
        "failure_count_24h": 0,
        "success_rate_24h": 1.0,
        "average_duration_ms_24h": 125.5,
        "total_tokens_24h": 300,
        "cost_amount_24h": None,
        "cost_currency": None,
    }


def test_provider_route_admin_lists_only_public_operational_state(monkeypatch) -> None:
    class FakeOperations:
        def list_route_status(self, _manifests):
            return [route_record()]

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    monkeypatch.setattr(api_main, "build_provider_route_operations", lambda: FakeOperations())

    response = TestClient(api_main.app).get(
        "/api/v1/admin/provider-routes",
        headers={"X-AIRank-Trace-Id": "trc_provider_routes"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["routes"][0]["request_count_24h"] == 3
    assert "api_key" not in response.text
    assert "secret" not in response.text
    validate_response("provider_route_status_response.schema.json", body)


def test_provider_route_admin_updates_with_version_and_reason(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeOperations:
        def sync_manifests(self, _manifests):
            return None

        def set_route_control(self, provider, route_id, **kwargs):
            calls.append({"provider": provider, "route_id": route_id, **kwargs})
            return {
                "provider": provider,
                "route_id": route_id,
                "enabled": kwargs["enabled"],
                "priority_override": kwargs["priority_override"],
                "control_version": 1,
                "updated_by": kwargs["changed_by"],
                "reason": kwargs["reason"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    monkeypatch.setattr(api_main, "build_provider_route_operations", lambda: FakeOperations())

    response = TestClient(api_main.app).put(
        "/api/v1/admin/provider-routes/qianwen/qianwen:default",
        json={
            "enabled": True,
            "priority_override": 50,
            "expected_version": 0,
            "reason": "raise healthy route priority",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["control_version"] == 1
    validate_response("provider_route_control_response.schema.json", response.json())
    assert calls[0]["changed_by"] == "dev_only_provider_admin"
    assert calls[0]["expected_version"] == 0


def test_provider_route_admin_rejects_stale_version_and_inline_secret(monkeypatch) -> None:
    class ConflictOperations:
        def set_route_control(self, provider, route_id, **_kwargs):
            raise ProviderGatewayError(
                provider,
                "PROVIDER_ROUTE_CONTROL_CONFLICT",
                "reload before updating",
            )

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    monkeypatch.setattr(api_main, "build_provider_route_operations", lambda: ConflictOperations())
    client = TestClient(api_main.app)

    conflict = client.put(
        "/api/v1/admin/provider-routes/qianwen/qianwen:default",
        json={
            "enabled": True,
            "expected_version": 0,
            "reason": "stale operator update",
        },
    )
    unsafe = client.put(
        "/api/v1/admin/provider-routes/qianwen/qianwen:default",
        json={
            "enabled": True,
            "expected_version": 0,
            "reason": "must reject inline credential",
            "api_key": "must-not-be-accepted",
        },
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PROVIDER_ROUTE_CONTROL_CONFLICT"
    assert unsafe.status_code == 422

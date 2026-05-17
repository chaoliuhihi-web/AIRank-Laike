from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api import main as api_main


ROOT = Path(__file__).resolve().parents[2]


def load_schema(name: str) -> dict[str, Any]:
    schema_path = ROOT / "packages" / "contracts" / name
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_schema(name: str, body: dict[str, Any]) -> None:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(body)


def test_auth_login_contract_accepts_dev_only_adapter(monkeypatch: Any) -> None:
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_demo")
    client = TestClient(api_main.app)
    request_body = {"username": "local_admin", "password": "local_password", "yudao_tenant_id": "1"}

    validate_schema("auth_login_request.schema.json", request_body)
    response = client.post(
        "/api/v1/auth/login",
        json=request_body,
        headers={"X-AIRank-Trace-Id": "trc_auth_dev"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_auth_dev"
    assert body["data"]["dev_only"] is True
    assert body["data"]["tenant_id"] == "tenant_demo"
    assert body["data"]["yudao_tenant_id"] == "1"
    assert body["data"]["access_token"].startswith("dev_only_")
    validate_schema("auth_login_response.schema.json", body)


def test_auth_login_bridges_to_yudao_and_permission_info(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request_external_json(
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        calls.append({"url": url, "method": method, "headers": headers or {}, "body": body, "timeout": timeout})
        if url.endswith("/login"):
            return {"code": 0, "data": {"accessToken": "tok_yudao_123", "expiresIn": 7200}}
        return {"code": 0, "data": {"user": {"id": 42, "username": "admin", "nickname": "Admin"}}}

    monkeypatch.setenv("AIRANK_AUTH_MODE", "yudao")
    monkeypatch.setenv("YUDAO_BASE_URL", "http://yudao.local")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_demo")
    monkeypatch.setattr(api_main, "request_external_json", fake_request_external_json)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "secret", "yudao_tenant_id": "1"},
        headers={"X-AIRank-Trace-Id": "trc_auth_yudao"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["access_token"] == "tok_yudao_123"
    assert body["data"]["dev_only"] is False
    assert body["data"]["user"]["user_id"] == "42"
    assert calls[0]["url"] == "http://yudao.local/admin-api/system/auth/login"
    assert calls[0]["headers"]["tenant-id"] == "1"
    assert calls[1]["url"] == "http://yudao.local/admin-api/system/auth/get-permission-info"
    assert calls[1]["headers"]["Authorization"] == "Bearer tok_yudao_123"
    validate_schema("auth_login_response.schema.json", body)


def test_auth_login_returns_registered_error_for_bad_yudao_credentials(monkeypatch: Any) -> None:
    def fake_request_external_json(
        _url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return {"code": 100200300, "msg": "bad credentials", "data": None}

    monkeypatch.setenv("AIRANK_AUTH_MODE", "yudao")
    monkeypatch.setenv("YUDAO_BASE_URL", "http://yudao.local")
    monkeypatch.setattr(api_main, "request_external_json", fake_request_external_json)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong", "yudao_tenant_id": "1"},
        headers={"X-AIRank-Trace-Id": "trc_auth_failed"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "AUTH_LOGIN_FAILED"
    assert body["error"]["trace_id"] == "trc_auth_failed"
    validate_schema("error_response.schema.json", body)

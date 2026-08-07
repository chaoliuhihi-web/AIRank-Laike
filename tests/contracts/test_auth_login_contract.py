from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import delivery_routes, knowledge_routes, main as api_main, retest_routes


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
    monkeypatch.delenv("YUDAO_LOGIN_URL", raising=False)
    monkeypatch.delenv("YUDAO_PERMISSION_INFO_URL", raising=False)
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


def test_required_dev_auth_accepts_only_issued_token_and_matching_tenant(monkeypatch: Any) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_auth_test")
    api_main._DEV_AUTH_SESSIONS.clear()
    client = TestClient(api_main.app)

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "auth_user", "password": "local", "yudao_tenant_id": "1"},
    )
    token = login_response.json()["data"]["access_token"]

    missing = client.get("/api/v1/console/overview", headers={"tenant-id": "tenant_auth_test"})
    forged = client.get(
        "/api/v1/console/overview",
        headers={"tenant-id": "tenant_auth_test", "Authorization": "Bearer dev_only_forged"},
    )
    wrong_tenant = client.get(
        "/api/v1/console/overview",
        headers={"tenant-id": "another_tenant", "Authorization": f"Bearer {token}"},
    )
    valid = client.get(
        "/api/v1/console/overview",
        headers={"tenant-id": "tenant_auth_test", "Authorization": f"Bearer {token}"},
    )

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTH_TOKEN_MISSING"
    assert forged.status_code == 401
    assert forged.json()["error"]["code"] == "AUTH_TOKEN_INVALID"
    assert wrong_tenant.status_code == 403
    assert wrong_tenant.json()["error"]["code"] == "TENANT_MISMATCH"
    assert valid.status_code == 200


def test_required_yudao_auth_revalidates_permission_info(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request_external_json(url: str, *, method="GET", headers=None, body=None, timeout=None):
        calls.append({"url": url, "method": method, "headers": headers or {}})
        return {"code": 0, "data": {"user": {"id": 99, "username": "api-user"}}}

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "yudao")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_yudao_auth")
    monkeypatch.setenv("YUDAO_BASE_URL", "http://yudao.local")
    monkeypatch.setattr(api_main, "request_external_json", fake_request_external_json)
    client = TestClient(api_main.app)

    response = client.get(
        "/api/v1/console/overview",
        headers={
            "tenant-id": "tenant_yudao_auth",
            "X-Yudao-Tenant-Id": "8",
            "Authorization": "Bearer yudao-token",
            "X-AIRank-User-Id": "spoofed-user",
        },
    )

    assert response.status_code == 200
    assert calls[0]["headers"]["Authorization"] == "Bearer yudao-token"
    assert calls[0]["headers"]["tenant-id"] == "8"


def test_skill_admin_endpoint_uses_trusted_permissions_and_rejects_spoofing(monkeypatch: Any) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_skill_admin")
    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "console:read")
    api_main._DEV_AUTH_SESSIONS.clear()
    client = TestClient(api_main.app)
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "ordinary-user", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]

    forbidden = client.get(
        "/api/v1/admin/skills",
        headers={
            "tenant-id": "tenant_skill_admin",
            "Authorization": f"Bearer {token}",
            "X-AIRank-Permissions": "airank:skill:admin",
        },
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "AUTH_PERMISSION_FORBIDDEN"

    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "airank:skill:admin")
    admin_token = client.post(
        "/api/v1/auth/login",
        json={"username": "skill-admin", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]
    allowed = client.get(
        "/api/v1/admin/skills",
        headers={"tenant-id": "tenant_skill_admin", "Authorization": f"Bearer {admin_token}"},
    )

    assert allowed.status_code == 200
    assert len(allowed.json()["data"]["skills"]) == 8


def test_yudao_permission_extraction_and_admin_wildcards_are_explicit() -> None:
    permissions = api_main.extract_yudao_permissions(
        {"code": 0, "data": {"permissions": ["airank:skill:admin", "airank:skill:admin", "console:read"]}}
    )

    assert permissions == ("airank:skill:admin", "console:read")
    assert api_main.permission_allows(permissions, "airank:skill:admin") is True
    assert api_main.permission_allows(("airank:skill:*",), "airank:skill:admin") is True
    assert api_main.permission_allows(("*:*:*",), "airank:skill:admin") is True
    assert api_main.permission_allows(("console:read",), "airank:skill:admin") is False


def test_audited_actor_comes_from_authenticated_session(monkeypatch: Any) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_actor_test")
    monkeypatch.setattr(
        knowledge_routes,
        "KNOWLEDGE_REPOSITORY",
        knowledge_routes.InMemoryKnowledgeRepository(),
    )
    api_main._DEV_AUTH_SESSIONS.clear()
    client = TestClient(api_main.app)
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "trusted-user", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]

    response = client.post(
        "/api/v1/projects/project_1/facts",
        headers={
            "tenant-id": "tenant_actor_test",
            "Authorization": f"Bearer {token}",
            "X-AIRank-User-Id": "spoofed-user",
        },
        json={
            "title": "可信审计身份",
            "fact_text": "审计身份必须来自认证上下文。",
            "created_by": "spoofed-body-user",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["created_by"] == "trusted-user"
    assert api_main.trusted_authenticated_actor("spoofed", "trusted-user") == "trusted-user"
    assert knowledge_routes.trusted_review_actor("spoofed", "trusted-user") == "trusted-user"
    assert delivery_routes.trusted_actor("spoofed", "trusted-user") == "trusted-user"
    assert retest_routes.trusted_completion_actor("spoofed", "trusted-user") == "trusted-user"
    with pytest.raises(StarletteHTTPException):
        delivery_routes.trusted_actor("spoofed", None)

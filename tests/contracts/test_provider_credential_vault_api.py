from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from airank_provider_gateway import CredentialKeyring, ProviderGatewayError, ProviderRequestContext, ProviderSettings
from apps.api import main as api_main
from apps.api import provider_credentials


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def validate_schema(name: str, payload: object) -> None:
    response_schema = load_schema("provider_credential_response.schema.json")
    operation_schema = load_schema("provider_credential_operation_response.schema.json")
    registry = (
        Registry()
        .with_resource(response_schema["$id"], Resource.from_contents(response_schema))
        .with_resource(operation_schema["$id"], Resource.from_contents(operation_schema))
    )
    contract = load_schema(name)
    Draft202012Validator.check_schema(contract)
    Draft202012Validator(
        contract,
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(payload)


class VerifiedCredential:
    def verify(self, *, tenant_id: str, provider: str, route_id: str, secret: str):
        assert tenant_id == "tenant_vault"
        assert provider == "qianwen"
        assert route_id == "qianwen:default"
        assert secret.startswith("sk-")
        return {
            "status": "verified",
            "probe_level": "l3_generation",
            "model": "qwen3.6-plus",
            "endpoint_host": "dashscope.aliyuncs.com",
            "request_id_present": True,
            "provider_request_id_sha256": "a" * 64,
            "duration_ms": 12,
            "evidence_grade": "provider_api_search_unverified",
            "verified_at": "2026-08-09T01:00:00+00:00",
        }


def vault(verifier=None):
    environment = {
        "QIANWEN_API_KEY": "environment-fallback-secret",
        "QIANWEN_API_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "QIANWEN_MODEL": "qwen3.6-plus",
    }
    keyring = CredentialKeyring(
        active_encryption_key_id="enc-v1",
        encryption_keys={"enc-v1": b"e" * 32},
        active_fingerprint_key_id="fp-v1",
        fingerprint_keys={"fp-v1": b"f" * 32},
    )
    return provider_credentials.InMemoryProviderCredentialVault(
        keyring, verifier=verifier or VerifiedCredential(), env=environment
    )


def request(secret: str, expected_version: int):
    return provider_credentials.CredentialUpsertRequest(
        secret=secret,
        expected_version=expected_version,
        reason="scheduled credential rotation",
        confirm_billable=True,
    )


def settings() -> ProviderSettings:
    return ProviderSettings(
        endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        api_key="environment-fallback-secret",
        model="qwen3.6-plus",
        disabled=False,
        max_tokens=128,
        temperature=0.2,
        reasoning_effort=None,
        request_kind="chat_completions_search",
        allowed_endpoint_hosts=("dashscope.aliyuncs.com",),
        allow_custom_endpoint=False,
    )


def test_vault_rotation_scrubs_old_ciphertext_and_revoke_blocks_env_fallback() -> None:
    repository = vault()
    first = repository.upsert(
        "tenant_vault", "qianwen", "qianwen:default", request("sk-first-private-value", 0), "admin_1", "trc_1", "credential-upsert-1"
    )
    assert first.source == "vault_active"
    assert first.secret_mask != "sk-first-private-value"
    resolved = repository.resolve_settings(
        "qianwen",
        "qianwen:default",
        settings(),
        context=ProviderRequestContext(tenant_id="tenant_vault"),
    )
    assert resolved.api_key == "sk-first-private-value"
    assert resolved.credential_source == "tenant_vault"
    assert resolved.credential_version == 1

    second = repository.upsert(
        "tenant_vault", "qianwen", "qianwen:default", request("sk-second-private-value", 1), "admin_1", "trc_2", "credential-upsert-2"
    )
    history = repository._records[("tenant_vault", "qianwen", "qianwen:default")]
    assert second.credential_version == 2
    assert history[0].envelope.ciphertext == ""
    assert history[0].envelope.nonce == ""
    assert history[0].envelope.secret_mask == "rotated"

    revoked = repository.revoke(
        "tenant_vault",
        "qianwen",
        "qianwen:default",
        provider_credentials.CredentialRevokeRequest(expected_version=2, reason="credential compromised"),
        "admin_2",
        "trc_3",
        "credential-revoke-2",
    )
    assert revoked.source == "vault_revoked"
    assert history[1].envelope.ciphertext == ""
    with pytest.raises(ProviderGatewayError) as captured:
        repository.resolve_settings(
            "qianwen",
            "qianwen:default",
            settings(),
            context=ProviderRequestContext(tenant_id="tenant_vault"),
        )
    assert captured.value.code == "PROVIDER_CREDENTIAL_REVOKED"
    assert captured.value.request_contract == {
        "credential_source": "tenant_vault",
        "credential_id": second.credential_id,
        "credential_version": 2,
    }

    replacement = repository.upsert(
        "tenant_vault",
        "qianwen",
        "qianwen:default",
        request("sk-third-private-value", 2),
        "admin_3",
        "trc_4",
        "credential-upsert-3",
    )
    assert replacement.credential_version == 3
    assert history[1].status == "revoked"
    assert history[1].envelope.secret_mask == "deleted"


def test_vault_api_never_returns_plaintext_and_uses_trusted_actor(monkeypatch) -> None:
    repository = vault()
    monkeypatch.setattr(provider_credentials, "get_provider_credential_vault", lambda: repository)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    client = TestClient(api_main.app)
    secret = "sk-api-private-value"
    response = client.put(
        "/api/v1/admin/provider-credentials/qianwen/qianwen:default",
        headers={"tenant-id": "tenant_vault", "X-AIRank-User-Id": "spoofed-actor", "Idempotency-Key": "api-credential-upsert-1"},
        json={"secret": secret, "expected_version": 0, "reason": "initial tenant BYOK", "confirm_billable": True},
    )
    assert response.status_code == 200
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert secret not in serialized
    assert "secret_ciphertext" not in serialized
    assert response.json()["data"]["source"] == "vault_active"
    validate_schema("provider_credential_response.schema.json", response.json())

    portfolio = client.get(
        "/api/v1/admin/provider-credentials", headers={"tenant-id": "tenant_vault"}
    )
    assert portfolio.status_code == 200
    assert secret not in json.dumps(portfolio.json(), ensure_ascii=False)
    validate_schema("provider_credential_portfolio_response.schema.json", portfolio.json())


def test_vault_request_contracts_and_required_auth_are_strict(monkeypatch) -> None:
    for name, payload in (
        (
            "provider_credential_upsert_request.schema.json",
            {
                "secret": "sk-private-credential",
                "expected_version": 0,
                "reason": "initial tenant credential",
                "confirm_billable": True,
            },
        ),
        (
            "provider_credential_revoke_request.schema.json",
            {"expected_version": 1, "reason": "credential compromised"},
        ),
    ):
        validate_schema(name, payload)

    repository = vault()
    monkeypatch.setattr(provider_credentials, "get_provider_credential_vault", lambda: repository)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_vault")
    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "console:read")
    api_main._DEV_AUTH_SESSIONS.clear()
    client = TestClient(api_main.app)
    ordinary_token = client.post(
        "/api/v1/auth/login",
        json={"username": "ordinary-user", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]

    forbidden = client.get(
        "/api/v1/admin/provider-credentials",
        headers={
            "tenant-id": "tenant_vault",
            "Authorization": f"Bearer {ordinary_token}",
            "X-AIRank-Permissions": "airank:provider:admin",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "AUTH_PERMISSION_FORBIDDEN"
    forbidden_operations = client.get(
        "/api/v1/admin/provider-credential-operations",
        headers={
            "tenant-id": "tenant_vault",
            "Authorization": f"Bearer {ordinary_token}",
        },
    )
    assert forbidden_operations.status_code == 403
    assert forbidden_operations.json()["error"]["code"] == "AUTH_PERMISSION_FORBIDDEN"

    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "airank:provider:admin")
    admin_token = client.post(
        "/api/v1/auth/login",
        json={"username": "provider-admin", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]
    secret = "sk-admin-private-value"
    allowed = client.put(
        "/api/v1/admin/provider-credentials/qianwen/qianwen:default",
        headers={
            "tenant-id": "tenant_vault",
            "Authorization": f"Bearer {admin_token}",
            "X-AIRank-User-Id": "spoofed-actor",
            "Idempotency-Key": "api-admin-credential-upsert-1",
        },
        json={
            "secret": secret,
            "expected_version": 0,
            "reason": "initial tenant credential",
            "confirm_billable": True,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["created_by"] == "provider-admin"
    assert secret not in json.dumps(allowed.json(), ensure_ascii=False)
    allowed_operations = client.get(
        "/api/v1/admin/provider-credential-operations",
        headers={
            "tenant-id": "tenant_vault",
            "Authorization": f"Bearer {admin_token}",
        },
    )
    assert allowed_operations.status_code == 200
    assert len(allowed_operations.json()["data"]["operations"]) == 1


def test_vault_rejects_unchanged_secret_after_real_verification() -> None:
    repository = vault()
    repository.upsert(
        "tenant_vault", "qianwen", "qianwen:default", request("sk-same-private-value", 0), "admin", "trc_1", "same-credential-upsert-1"
    )
    with pytest.raises(provider_credentials.CredentialVaultError) as captured:
        repository.upsert(
            "tenant_vault", "qianwen", "qianwen:default", request("sk-same-private-value", 1), "admin", "trc_2", "same-credential-upsert-2"
        )
    assert captured.value.code == "CREDENTIAL_UNCHANGED"

    repository.keyring = CredentialKeyring(
        active_encryption_key_id="enc-v2",
        encryption_keys={"enc-v1": b"e" * 32, "enc-v2": b"n" * 32},
        active_fingerprint_key_id="fp-v2",
        fingerprint_keys={"fp-v1": b"f" * 32, "fp-v2": b"g" * 32},
    )
    with pytest.raises(provider_credentials.CredentialVaultError) as rotated_key_error:
        repository.upsert(
            "tenant_vault",
            "qianwen",
            "qianwen:default",
            request("sk-same-private-value", 1),
            "admin",
            "trc_3",
            "same-credential-upsert-3",
        )
    assert rotated_key_error.value.code == "CREDENTIAL_UNCHANGED"


def test_invalid_secret_validation_never_echoes_plaintext(monkeypatch) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    marker = "LEAKME"
    response = TestClient(api_main.app).put(
        "/api/v1/admin/provider-credentials/qianwen/qianwen:default",
        headers={"tenant-id": "tenant_vault", "Idempotency-Key": "invalid-secret-upsert-1"},
        json={
            "secret": marker,
            "expected_version": 0,
            "reason": "invalid secret validation",
            "confirm_billable": True,
        },
    )
    assert response.status_code == 422
    assert marker not in response.text


class CountingCredential(VerifiedCredential):
    def __init__(self) -> None:
        self.call_count = 0

    def verify(self, **kwargs):
        self.call_count += 1
        return super().verify(**kwargs)


def test_upsert_idempotent_replay_never_repeats_l3_and_survives_fingerprint_key_rotation() -> None:
    verifier = CountingCredential()
    repository = vault(verifier)
    payload = request("sk-idempotent-private-value", 0)

    first = repository.upsert(
        "tenant_vault", "qianwen", "qianwen:default", payload, "admin", "trc_first", "stable-upsert-key"
    )
    repository.keyring = CredentialKeyring(
        active_encryption_key_id="enc-v2",
        encryption_keys={"enc-v1": b"e" * 32, "enc-v2": b"n" * 32},
        active_fingerprint_key_id="fp-v2",
        fingerprint_keys={"fp-v1": b"f" * 32, "fp-v2": b"g" * 32},
    )
    replay = repository.upsert(
        "tenant_vault", "qianwen", "qianwen:default", payload, "admin", "trc_replay", "stable-upsert-key"
    )

    assert verifier.call_count == 1
    assert replay.idempotent_replay is True
    assert replay.operation_id == first.operation_id
    assert replay.credential_id == first.credential_id

    with pytest.raises(provider_credentials.CredentialVaultError) as conflict:
        repository.upsert(
            "tenant_vault",
            "qianwen",
            "qianwen:default",
            request("sk-different-private-value", 0),
            "admin",
            "trc_conflict",
            "stable-upsert-key",
        )
    assert conflict.value.code == "OPERATION_IDEMPOTENCY_CONFLICT"
    assert verifier.call_count == 1


def test_failed_l3_operation_is_not_automatically_repeated() -> None:
    class FailingCredential:
        call_count = 0

        def verify(self, **_kwargs):
            self.call_count += 1
            raise provider_credentials.CredentialVaultError(
                "CREDENTIAL_PROVIDER_VERIFICATION_FAILED", "L3 rejected credential"
            )

    verifier = FailingCredential()
    repository = vault(verifier)
    payload = request("sk-provider-rejected-value", 0)
    for _attempt in range(2):
        with pytest.raises(provider_credentials.CredentialVaultError) as failure:
            repository.upsert(
                "tenant_vault", "qianwen", "qianwen:default", payload, "admin", "trc_failure", "failed-upsert-key"
            )
        assert failure.value.code == "CREDENTIAL_PROVIDER_VERIFICATION_FAILED"
    assert verifier.call_count == 1


def test_concurrent_duplicate_after_external_start_reports_unknown_without_second_l3() -> None:
    started = Event()
    release = Event()

    class BlockingCredential(CountingCredential):
        def verify(self, **kwargs):
            self.call_count += 1
            started.set()
            assert release.wait(timeout=5)
            return VerifiedCredential.verify(self, **kwargs)

    verifier = BlockingCredential()
    repository = vault(verifier)
    payload = request("sk-concurrent-private-value", 0)
    completed: list[provider_credentials.ProviderCredentialData] = []

    thread = Thread(
        target=lambda: completed.append(
            repository.upsert(
                "tenant_vault", "qianwen", "qianwen:default", payload, "admin", "trc_owner", "concurrent-upsert-key"
            )
        )
    )
    thread.start()
    assert started.wait(timeout=5)
    try:
        with pytest.raises(provider_credentials.CredentialVaultError) as duplicate:
            repository.upsert(
                "tenant_vault", "qianwen", "qianwen:default", payload, "admin", "trc_duplicate", "concurrent-upsert-key"
            )
        assert duplicate.value.code == "OPERATION_OUTCOME_UNKNOWN"
        assert verifier.call_count == 1
    finally:
        release.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(completed) == 1


def test_provider_credential_writes_require_idempotency_header(monkeypatch) -> None:
    monkeypatch.setattr(provider_credentials, "get_provider_credential_vault", vault)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    response = TestClient(api_main.app).put(
        "/api/v1/admin/provider-credentials/qianwen/qianwen:default",
        headers={"tenant-id": "tenant_vault"},
        json={
            "secret": "sk-missing-idempotency-header",
            "expected_version": 0,
            "reason": "must reject missing operation key",
            "confirm_billable": True,
        },
    )
    assert response.status_code == 422


def test_operation_audit_list_and_detail_are_tenant_scoped_and_schema_valid(monkeypatch) -> None:
    repository = vault(CountingCredential())
    created = repository.upsert(
        "tenant_vault",
        "qianwen",
        "qianwen:default",
        request("sk-operation-audit-private-value", 0),
        "audit-admin",
        "trc_operation_audit",
        "operation-audit-upsert-key",
    )
    monkeypatch.setattr(provider_credentials, "get_provider_credential_vault", lambda: repository)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    client = TestClient(api_main.app)

    listed = client.get(
        "/api/v1/admin/provider-credential-operations",
        headers={"tenant-id": "tenant_vault"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["reconciliation_required_count"] == 0
    assert len(listed.json()["data"]["operations"]) == 1
    assert listed.json()["data"]["operations"][0]["events"] == []
    validate_schema("provider_credential_operation_list_response.schema.json", listed.json())

    detail = client.get(
        f"/api/v1/admin/provider-credential-operations/{created.operation_id}",
        headers={"tenant-id": "tenant_vault"},
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["replay_status"] == "available"
    assert detail.json()["data"]["response_credential_id"] == created.credential_id
    assert [event["event_sequence"] for event in detail.json()["data"]["events"]] == [1, 2, 3]
    validate_schema("provider_credential_operation_response.schema.json", detail.json())

    cross_tenant = client.get(
        f"/api/v1/admin/provider-credential-operations/{created.operation_id}",
        headers={"tenant-id": "tenant_other"},
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "OPERATION_NOT_FOUND"


def test_operation_audit_marks_external_started_as_reconciliation_required() -> None:
    repository = vault()
    guard = repository.operation_guard
    claim = guard.claim(
        tenant_id="tenant_vault",
        operation_type="provider_credential.upsert",
        resource_key="qianwen/qianwen:default",
        idempotency_key="unknown-outcome-operation-key",
        request_sha256="a" * 64,
        request_key_id="fp-v1",
        actor="audit-admin",
        trace_id="trc_unknown",
    )
    guard.mark_external_started(claim.operation_id, "audit-admin", "trc_unknown")

    listed = repository.list_operations("tenant_vault", state="external_started")
    assert listed.reconciliation_required_count == 1
    assert listed.operations[0].reconciliation_required is True
    assert listed.operations[0].replay_status == "forbidden_unknown"
    detail = repository.get_operation("tenant_vault", claim.operation_id)
    assert detail is not None
    assert [event.event_type for event in detail.events] == [
        "operation_claimed",
        "external_effect_started",
    ]

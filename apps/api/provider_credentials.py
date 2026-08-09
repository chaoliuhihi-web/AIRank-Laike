from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from threading import Lock
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from .operation_guard import (
        InMemoryOperationGuard,
        MySQLOperationGuard,
        OperationGuard,
        OperationGuardError,
    )
except ImportError:  # pragma: no cover - direct module execution compatibility
    from operation_guard import (  # type: ignore[no-redef]
        InMemoryOperationGuard,
        MySQLOperationGuard,
        OperationGuard,
        OperationGuardError,
    )

from airank_provider_gateway import (
    CredentialEnvelope,
    CredentialKeyring,
    CredentialVaultError,
    PROVIDER_MANIFESTS,
    ProviderGateway,
    ProviderGatewayError,
    ProviderRequestContext,
    ProviderSettings,
    get_manifest,
    resolve_provider_routes,
)


router = APIRouter(prefix="/api/v1", tags=["provider-credentials"])
CONTRACT_VERSION = "airank.provider-credential-vault.v1"
KEYRING_CONTRACT_VERSION = "airank.provider-credential-keyring.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def error(status_code: int, code: str, details: Mapping[str, object]) -> StarletteHTTPException:
    return StarletteHTTPException(
        status_code=status_code, detail={"code": code, "details": dict(details)}
    )


def auth_enforcement_required() -> bool:
    return os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower() in {
        "1",
        "true",
        "yes",
        "required",
    }


def require_provider_admin(permission_header: Optional[str]) -> None:
    if not auth_enforcement_required():
        return
    required = os.getenv("AIRANK_PROVIDER_ADMIN_PERMISSION", "airank:provider:admin").strip()
    granted = {item.strip() for item in (permission_header or "").split(",") if item.strip()}
    namespace = required.rsplit(":", 1)[0]
    if not granted.intersection({required, "*", "*:*:*", f"{namespace}:*"}):
        raise error(403, "AUTH_PERMISSION_FORBIDDEN", {"required_permission": required})


def trusted_actor(authenticated_actor: Optional[str]) -> str:
    actor = str(authenticated_actor or "").strip()
    if actor:
        return actor[:128]
    if not auth_enforcement_required():
        return "dev_only_provider_admin"
    raise error(401, "AUTH_TOKEN_INVALID", {"reason": "authenticated_actor_required"})


class CredentialUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: SecretStr = Field(min_length=8, max_length=16_384, repr=False)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=3, max_length=500)
    confirm_billable: Literal[True]


class CredentialRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class CredentialVerificationData(BaseModel):
    status: Literal["verified"]
    probe_level: Literal["l3_generation"]
    model: str
    endpoint_host: str
    request_id_present: bool
    provider_request_id_sha256: Optional[str] = None
    duration_ms: int
    evidence_grade: str
    verified_at: datetime


class ProviderCredentialData(BaseModel):
    contract_version: Literal["airank.provider-credential-vault.v1"] = CONTRACT_VERSION
    provider: str
    label: str
    route_id: str
    source: Literal[
        "vault_active",
        "vault_revoked",
        "vault_key_unavailable",
        "environment_legacy",
        "unconfigured",
    ]
    status: Literal["active", "revoked", "unconfigured", "blocked"]
    configured: bool
    credential_id: Optional[str] = None
    credential_version: int = 0
    secret_mask: Optional[str] = None
    fingerprint_prefix: Optional[str] = None
    encryption_key_id: Optional[str] = None
    fingerprint_key_id: Optional[str] = None
    algorithm: Optional[str] = None
    verification: Optional[CredentialVerificationData] = None
    rotated_from_id: Optional[str] = None
    created_by: Optional[str] = None
    activated_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    latest_event_sha256: Optional[str] = None
    operation_id: Optional[str] = None
    idempotent_replay: bool = False
    known_limitations: list[str] = Field(default_factory=list)


class ProviderCredentialPortfolioData(BaseModel):
    contract_version: Literal["airank.provider-credential-vault.v1"] = CONTRACT_VERSION
    keyring_contract_version: Literal[
        "airank.provider-credential-keyring.v1"
    ] = KEYRING_CONTRACT_VERSION
    keyring_status: Literal["ready", "blocked"]
    credentials: list[ProviderCredentialData]
    known_limitations: list[str] = Field(default_factory=list)


class ProviderCredentialResponse(BaseModel):
    data: ProviderCredentialData
    meta: dict[str, str]


class ProviderCredentialPortfolioResponse(BaseModel):
    data: ProviderCredentialPortfolioData
    meta: dict[str, str]


class CredentialVerifier(Protocol):
    def verify(
        self,
        *,
        tenant_id: str,
        provider: str,
        route_id: str,
        secret: str,
    ) -> Mapping[str, object]: ...


class GatewayCredentialVerifier:
    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self.env = env if env is not None else os.environ

    def verify(
        self,
        *,
        tenant_id: str,
        provider: str,
        route_id: str,
        secret: str,
    ) -> Mapping[str, object]:
        manifest = get_manifest(provider)
        if manifest is None:
            raise CredentialVaultError(
                "PROVIDER_NOT_SUPPORTED", "provider is not supported by the credential vault"
            )
        routes = resolve_provider_routes(manifest, self.env)
        selected = next((item for item in routes if item.route_id == route_id), None)
        if selected is None:
            raise CredentialVaultError(
                "PROVIDER_ROUTE_NOT_FOUND", "provider route is not configured"
            )
        verify_key_env = "AIRANK_CREDENTIAL_VERIFY_SECRET"
        settings = selected.settings
        isolated = dict(self.env)
        isolated[verify_key_env] = secret
        isolated[f"{manifest.provider.upper()}_PROVIDER_DISABLED"] = "false"
        isolated[f"{manifest.provider.upper()}_ROUTES_JSON"] = canonical_json(
            [
                {
                    "route_id": route_id,
                    "priority": 0,
                    "endpoint": settings.endpoint,
                    "model": settings.model,
                    "key_env": verify_key_env,
                    "max_tokens": min(settings.max_tokens, 32),
                    "temperature": settings.temperature,
                    "reasoning_effort": settings.reasoning_effort,
                    "request_kind": settings.request_kind,
                }
            ]
        )
        try:
            timeout = float(isolated.get("AIRANK_CREDENTIAL_VERIFY_TIMEOUT_SECONDS") or "45")
        except ValueError:
            timeout = 45.0
        gateway = ProviderGateway(env=isolated, max_attempts=1, timeout_seconds=timeout)
        verified_at = utc_now()
        try:
            result = gateway.generate(
                manifest.provider,
                "凭证验证：只回复 OK。",
                request_context=ProviderRequestContext(
                    tenant_id=tenant_id,
                    project_id="provider_credential_vault",
                    idempotency_key=f"credential-verify:{uuid4().hex}",
                ),
            )
        except ProviderGatewayError as exc:
            raise CredentialVaultError(
                "CREDENTIAL_PROVIDER_VERIFICATION_FAILED",
                f"provider L3 verification failed ({exc.code})",
            ) from exc
        return {
            "status": "verified",
            "probe_level": "l3_generation",
            "model": result.model,
            "endpoint_host": result.endpoint_host,
            "request_id_present": bool(result.request_id),
            "provider_request_id_sha256": (
                hashlib.sha256(str(result.request_id).encode("utf-8")).hexdigest()
                if result.request_id
                else None
            ),
            "duration_ms": result.duration_ms,
            "evidence_grade": result.evidence_grade,
            "verified_at": verified_at.isoformat(),
        }


@dataclass
class _CredentialRecord:
    credential_id: str
    tenant_id: str
    provider: str
    route_id: str
    credential_version: int
    status: str
    is_current: bool
    envelope: CredentialEnvelope
    verification: dict[str, object]
    request_sha256: str
    rotated_from_id: Optional[str]
    reason: str
    created_by: str
    created_at: datetime
    activated_at: datetime
    revoked_at: Optional[datetime] = None
    scrubbed_at: Optional[datetime] = None
    latest_event_sha256: Optional[str] = None


class ProviderCredentialVault(Protocol):
    def portfolio(self, tenant_id: str) -> ProviderCredentialPortfolioData: ...

    def upsert(
        self,
        tenant_id: str,
        provider: str,
        route_id: str,
        payload: CredentialUpsertRequest,
        actor: str,
        trace_id: str,
        idempotency_key: str,
    ) -> ProviderCredentialData: ...

    def revoke(
        self,
        tenant_id: str,
        provider: str,
        route_id: str,
        payload: CredentialRevokeRequest,
        actor: str,
        trace_id: str,
        idempotency_key: str,
    ) -> ProviderCredentialData: ...

    def resolve_settings(
        self,
        provider: str,
        route_id: str,
        settings: ProviderSettings,
        *,
        context: ProviderRequestContext,
    ) -> ProviderSettings: ...


def _route(provider: str, route_id: str, env: Mapping[str, str]) -> tuple[str, ProviderSettings]:
    manifest = get_manifest(provider)
    if manifest is None:
        raise CredentialVaultError("PROVIDER_NOT_SUPPORTED", "provider is not supported")
    selected = next(
        (item for item in resolve_provider_routes(manifest, env) if item.route_id == route_id),
        None,
    )
    if selected is None:
        raise CredentialVaultError("PROVIDER_ROUTE_NOT_FOUND", "provider route is not configured")
    return manifest.label, selected.settings


def _verification(value: Mapping[str, object]) -> CredentialVerificationData:
    return CredentialVerificationData.model_validate(dict(value))


def _guard_error(exc: OperationGuardError) -> CredentialVaultError:
    return CredentialVaultError(exc.code, exc.message)


def _replayed_credential(claim_response: Optional[dict[str, object]], operation_id: str) -> ProviderCredentialData:
    if claim_response is None:
        raise CredentialVaultError(
            "OPERATION_STATE_CONFLICT",
            "successful operation is missing its replay response",
        )
    return ProviderCredentialData.model_validate(claim_response).model_copy(
        update={"operation_id": operation_id, "idempotent_replay": True}
    )


def _record_data(record: _CredentialRecord, label: str, *, keyring_ready: bool) -> ProviderCredentialData:
    if record.status == "active" and keyring_ready:
        source, status, configured = "vault_active", "active", True
        limitations: list[str] = []
    elif record.status == "active":
        source, status, configured = "vault_key_unavailable", "blocked", False
        limitations = ["credential_keyring_unavailable"]
    else:
        source, status, configured = "vault_revoked", "revoked", False
        limitations = ["credential_revoked_and_ciphertext_scrubbed"]
    return ProviderCredentialData(
        provider=record.provider,
        label=label,
        route_id=record.route_id,
        source=source,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        configured=configured,
        credential_id=record.credential_id,
        credential_version=record.credential_version,
        secret_mask=record.envelope.secret_mask,
        fingerprint_prefix=record.envelope.secret_fingerprint[:24],
        encryption_key_id=record.envelope.encryption_key_id,
        fingerprint_key_id=record.envelope.fingerprint_key_id,
        algorithm=record.envelope.algorithm,
        verification=_verification(record.verification),
        rotated_from_id=record.rotated_from_id,
        created_by=record.created_by,
        activated_at=record.activated_at,
        revoked_at=record.revoked_at,
        latest_event_sha256=record.latest_event_sha256,
        known_limitations=limitations,
    )


class InMemoryProviderCredentialVault:
    def __init__(
        self,
        keyring: CredentialKeyring | None,
        *,
        verifier: CredentialVerifier | None = None,
        env: Mapping[str, str] | None = None,
        operation_guard: OperationGuard | None = None,
    ) -> None:
        self.keyring = keyring
        self.verifier = verifier or GatewayCredentialVerifier(env)
        self.env = env if env is not None else os.environ
        self.operation_guard = operation_guard or InMemoryOperationGuard()
        self._records: dict[tuple[str, str, str], list[_CredentialRecord]] = {}
        self._lock = Lock()

    def _current(self, tenant_id: str, provider: str, route_id: str) -> Optional[_CredentialRecord]:
        records = self._records.get((tenant_id, provider, route_id), [])
        return next((record for record in reversed(records) if record.is_current), None)

    def portfolio(self, tenant_id: str) -> ProviderCredentialPortfolioData:
        records: list[ProviderCredentialData] = []
        for manifest in PROVIDER_MANIFESTS.values():
            for route in resolve_provider_routes(manifest, self.env):
                current = self._current(tenant_id, manifest.provider, route.route_id)
                if current is not None:
                    records.append(_record_data(current, manifest.label, keyring_ready=self.keyring is not None))
                else:
                    records.append(
                        ProviderCredentialData(
                            provider=manifest.provider,
                            label=manifest.label,
                            route_id=route.route_id,
                            source="environment_legacy" if route.settings.configured else "unconfigured",
                            status="active" if route.settings.configured else "unconfigured",
                            configured=route.settings.configured,
                            known_limitations=(
                                ["environment_credential_is_not_tenant_scoped_or_vault_rotatable"]
                                if route.settings.configured
                                else ["provider_credential_not_configured"]
                            ),
                        )
                    )
        return ProviderCredentialPortfolioData(
            keyring_status="ready" if self.keyring is not None else "blocked",
            credentials=records,
            known_limitations=([] if self.keyring is not None else ["credential_keyring_unavailable"]),
        )

    def upsert(self, tenant_id: str, provider: str, route_id: str, payload: CredentialUpsertRequest, actor: str, trace_id: str, idempotency_key: str) -> ProviderCredentialData:
        if self.keyring is None:
            raise CredentialVaultError("CREDENTIAL_KEYRING_UNAVAILABLE", "credential keyring is unavailable")
        label, _ = _route(provider, route_id, self.env)
        secret = payload.secret.get_secret_value()
        operation_type = "provider_credential.upsert"
        resource_key = f"{provider}/{route_id}"
        try:
            request_key_id = self.operation_guard.request_key_id(
                tenant_id, operation_type, resource_key, idempotency_key
            ) or self.keyring.active_fingerprint_key_id
            request_fingerprint, request_key_id = self.keyring.fingerprint_secret(
                tenant_id=tenant_id,
                provider=provider,
                route_id=route_id,
                plaintext=secret,
                fingerprint_key_id=request_key_id,
            )
            claim = self.operation_guard.claim(
                tenant_id=tenant_id,
                operation_type=operation_type,
                resource_key=resource_key,
                idempotency_key=idempotency_key,
                request_sha256=canonical_sha256(
                    {
                        "provider": provider,
                        "route_id": route_id,
                        "expected_version": payload.expected_version,
                        "reason": payload.reason,
                        "confirm_billable": payload.confirm_billable,
                        "secret_fingerprint": request_fingerprint,
                    }
                ),
                request_key_id=request_key_id,
                actor=actor,
                trace_id=trace_id,
            )
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        if claim.idempotent_replay:
            return _replayed_credential(claim.response, claim.operation_id)
        try:
            with self._lock:
                current = self._current(tenant_id, provider, route_id)
                actual_version = current.credential_version if current else 0
                if actual_version != payload.expected_version:
                    raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
                if current is not None and self.keyring.matches_fingerprint(
                    tenant_id=tenant_id,
                    provider=provider,
                    route_id=route_id,
                    plaintext=secret,
                    expected_fingerprint=current.envelope.secret_fingerprint,
                    fingerprint_key_id=current.envelope.fingerprint_key_id,
                ):
                    raise CredentialVaultError("CREDENTIAL_UNCHANGED", "new credential matches current credential")
            self.operation_guard.mark_external_started(claim.operation_id, actor, trace_id)
            try:
                verification = dict(
                    self.verifier.verify(
                        tenant_id=tenant_id,
                        provider=provider,
                        route_id=route_id,
                        secret=secret,
                    )
                )
            except CredentialVaultError:
                raise
            except Exception as exc:
                raise CredentialVaultError(
                    "CREDENTIAL_PROVIDER_VERIFICATION_FAILED",
                    "provider L3 verification failed",
                ) from exc
            now = utc_now()
            credential_id = f"provider_credential_{uuid4().hex[:16]}"
            version = payload.expected_version + 1
            envelope = self.keyring.encrypt(
                tenant_id=tenant_id,
                provider=provider,
                route_id=route_id,
                credential_id=credential_id,
                credential_version=version,
                plaintext=secret,
            )
            request_sha256 = canonical_sha256(
                {
                    "provider": provider,
                    "route_id": route_id,
                    "version": version,
                    "fingerprint": envelope.secret_fingerprint,
                    "reason": payload.reason,
                    "verification": verification,
                }
            )
            with self._lock:
                current = self._current(tenant_id, provider, route_id)
                actual_version = current.credential_version if current else 0
                if actual_version != payload.expected_version:
                    raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
                if current is not None and self.keyring.matches_fingerprint(
                    tenant_id=tenant_id,
                    provider=provider,
                    route_id=route_id,
                    plaintext=secret,
                    expected_fingerprint=current.envelope.secret_fingerprint,
                    fingerprint_key_id=current.envelope.fingerprint_key_id,
                ):
                    raise CredentialVaultError("CREDENTIAL_UNCHANGED", "new credential matches current credential")
                previous_hash = current.latest_event_sha256 if current else None
                if current:
                    current.is_current = False
                    current.scrubbed_at = now
                    if current.status == "active":
                        current.status = "rotated"
                        current.envelope = replace(
                            current.envelope,
                            ciphertext="",
                            nonce="",
                            secret_mask="rotated",
                        )
                record = _CredentialRecord(
                    credential_id=credential_id,
                    tenant_id=tenant_id,
                    provider=provider,
                    route_id=route_id,
                    credential_version=version,
                    status="active",
                    is_current=True,
                    envelope=envelope,
                    verification=verification,
                    request_sha256=request_sha256,
                    rotated_from_id=current.credential_id if current else None,
                    reason=payload.reason,
                    created_by=actor,
                    created_at=now,
                    activated_at=now,
                )
                record.latest_event_sha256 = canonical_sha256({"previous": previous_hash, "event": "credential_activated", "credential_id": credential_id, "version": version, "fingerprint": envelope.secret_fingerprint, "actor": actor, "reason": payload.reason, "created_at": now.isoformat()})
                self._records.setdefault((tenant_id, provider, route_id), []).append(record)
            data = _record_data(record, label, keyring_ready=True).model_copy(
                update={"operation_id": claim.operation_id}
            )
            self.operation_guard.succeed(
                claim.operation_id, data.model_dump(mode="json"), actor, trace_id
            )
            return data
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        except CredentialVaultError as exc:
            self.operation_guard.fail(claim.operation_id, exc.code, actor, trace_id)
            raise

    def revoke(self, tenant_id: str, provider: str, route_id: str, payload: CredentialRevokeRequest, actor: str, trace_id: str, idempotency_key: str) -> ProviderCredentialData:
        label, _ = _route(provider, route_id, self.env)
        operation_type = "provider_credential.revoke"
        resource_key = f"{provider}/{route_id}"
        try:
            claim = self.operation_guard.claim(
                tenant_id=tenant_id,
                operation_type=operation_type,
                resource_key=resource_key,
                idempotency_key=idempotency_key,
                request_sha256=canonical_sha256(
                    {
                        "provider": provider,
                        "route_id": route_id,
                        "expected_version": payload.expected_version,
                        "reason": payload.reason,
                    }
                ),
                request_key_id=None,
                actor=actor,
                trace_id=trace_id,
            )
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        if claim.idempotent_replay:
            return _replayed_credential(claim.response, claim.operation_id)
        try:
            with self._lock:
                current = self._current(tenant_id, provider, route_id)
                if current is None:
                    raise CredentialVaultError("CREDENTIAL_NOT_FOUND", "credential was not found")
                if current.credential_version != payload.expected_version:
                    raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
                if current.status != "active":
                    raise CredentialVaultError("CREDENTIAL_ALREADY_REVOKED", "credential is already revoked")
            self.operation_guard.mark_external_started(claim.operation_id, actor, trace_id)
            now = utc_now()
            with self._lock:
                current = self._current(tenant_id, provider, route_id)
                if current is None:
                    raise CredentialVaultError("CREDENTIAL_NOT_FOUND", "credential was not found")
                if current.credential_version != payload.expected_version:
                    raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
                if current.status != "active":
                    raise CredentialVaultError("CREDENTIAL_ALREADY_REVOKED", "credential is already revoked")
                previous_hash = current.latest_event_sha256
                current.status = "revoked"
                current.envelope = replace(current.envelope, ciphertext="", nonce="", secret_mask="deleted")
                current.revoked_at = now
                current.scrubbed_at = now
                current.reason = payload.reason
                current.latest_event_sha256 = canonical_sha256({"previous": previous_hash, "event": "credential_revoked", "credential_id": current.credential_id, "version": current.credential_version, "fingerprint": current.envelope.secret_fingerprint, "actor": actor, "reason": payload.reason, "created_at": now.isoformat()})
            data = _record_data(current, label, keyring_ready=self.keyring is not None).model_copy(
                update={"operation_id": claim.operation_id}
            )
            self.operation_guard.succeed(
                claim.operation_id, data.model_dump(mode="json"), actor, trace_id
            )
            return data
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        except CredentialVaultError as exc:
            self.operation_guard.fail(claim.operation_id, exc.code, actor, trace_id)
            raise

    def resolve_settings(self, provider: str, route_id: str, settings: ProviderSettings, *, context: ProviderRequestContext) -> ProviderSettings:
        current = self._current(context.tenant_id, provider, route_id)
        if current is None:
            return settings
        credential_contract = {
            "credential_source": "tenant_vault",
            "credential_id": current.credential_id,
            "credential_version": current.credential_version,
        }
        if current.status != "active":
            raise ProviderGatewayError(
                provider,
                "PROVIDER_CREDENTIAL_REVOKED",
                "tenant provider credential is revoked",
                request_contract=credential_contract,
            )
        if self.keyring is None:
            raise ProviderGatewayError(
                provider,
                "PROVIDER_CREDENTIAL_KEY_UNAVAILABLE",
                "tenant provider credential key is unavailable",
                request_contract=credential_contract,
            )
        try:
            secret = self.keyring.decrypt(
                tenant_id=context.tenant_id,
                provider=provider,
                route_id=route_id,
                credential_id=current.credential_id,
                credential_version=current.credential_version,
                envelope=current.envelope,
            )
        except CredentialVaultError as exc:
            raise ProviderGatewayError(
                provider,
                exc.code,
                exc.message,
                request_contract=credential_contract,
            ) from exc
        return replace(settings, api_key=secret, credential_source="tenant_vault", credential_id=current.credential_id, credential_version=current.credential_version)


class MySQLProviderCredentialVault(InMemoryProviderCredentialVault):
    def __init__(self, database_url: str, keyring: CredentialKeyring | None, *, verifier: CredentialVerifier | None = None, env: Mapping[str, str] | None = None, operation_guard: OperationGuard | None = None) -> None:
        super().__init__(
            keyring,
            verifier=verifier,
            env=env,
            operation_guard=operation_guard or MySQLOperationGuard(database_url),
        )
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _from_row(row: Mapping[str, Any], latest_event_sha256: Optional[str] = None) -> _CredentialRecord:
        verification = row["verification_json"]
        if isinstance(verification, str):
            verification = json.loads(verification)
        return _CredentialRecord(
            credential_id=str(row["id"]), tenant_id=str(row["tenant_id"]), provider=str(row["provider_key"]), route_id=str(row["route_id"]), credential_version=int(row["credential_version"]), status=str(row["status"]), is_current=bool(row["is_current"]),
            envelope=CredentialEnvelope(ciphertext=str(row["secret_ciphertext"]), nonce=str(row["secret_nonce"]), secret_mask=str(row["secret_mask"]), secret_fingerprint=str(row["secret_fingerprint"]), encryption_key_id=str(row["encryption_key_id"]), fingerprint_key_id=str(row["fingerprint_key_id"]), algorithm=str(row["algorithm"])),
            verification=dict(verification), request_sha256=str(row["request_sha256"]), rotated_from_id=str(row["rotated_from_id"]) if row["rotated_from_id"] else None, reason=str(row["reason"]), created_by=str(row["created_by"]), created_at=row["created_at"].replace(tzinfo=timezone.utc), activated_at=row["activated_at"].replace(tzinfo=timezone.utc), revoked_at=row["revoked_at"].replace(tzinfo=timezone.utc) if row["revoked_at"] else None, scrubbed_at=row["scrubbed_at"].replace(tzinfo=timezone.utc) if row["scrubbed_at"] else None, latest_event_sha256=latest_event_sha256,
        )

    @staticmethod
    def _select_current(conn: Any, tenant_id: str, provider: str, route_id: str, *, for_update: bool = False) -> Optional[Mapping[str, Any]]:
        suffix = " FOR UPDATE" if for_update else ""
        return conn.execute(text("SELECT * FROM airank_provider_credentials WHERE tenant_id=:tenant_id AND provider_key=:provider AND route_id=:route_id AND is_current=1 ORDER BY credential_version DESC LIMIT 1" + suffix), {"tenant_id": tenant_id, "provider": provider, "route_id": route_id}).mappings().first()

    @staticmethod
    def _latest_event(conn: Any, tenant_id: str, provider: str, route_id: str) -> Optional[str]:
        value = conn.execute(
            text(
                "SELECT event_sha256 FROM airank_provider_credential_events "
                "WHERE tenant_id=:tenant_id AND provider_key=:provider AND route_id=:route_id "
                "ORDER BY event_sequence DESC LIMIT 1"
            ),
            {"tenant_id": tenant_id, "provider": provider, "route_id": route_id},
        ).scalar()
        return str(value) if value else None

    @staticmethod
    def _append_event(conn: Any, *, tenant_id: str, credential_id: str, provider: str, route_id: str, version: int, event_type: str, fingerprint: str, actor: str, reason: str, trace_id: str, created_at: datetime) -> str:
        latest = conn.execute(
            text(
                "SELECT event_sequence,event_sha256 FROM airank_provider_credential_events "
                "WHERE tenant_id=:tenant_id AND provider_key=:provider AND route_id=:route_id "
                "ORDER BY event_sequence DESC LIMIT 1 FOR UPDATE"
            ),
            {"tenant_id": tenant_id, "provider": provider, "route_id": route_id},
        ).mappings().first()
        previous = str(latest["event_sha256"]) if latest else None
        event_sequence = int(latest["event_sequence"]) + 1 if latest else 1
        event_id = f"provider_credential_event_{uuid4().hex[:16]}"
        payload = {"contract_version": CONTRACT_VERSION, "event_id": event_id, "tenant_id": tenant_id, "credential_id": credential_id, "provider": provider, "route_id": route_id, "credential_version": version, "event_sequence": event_sequence, "event_type": event_type, "credential_fingerprint": fingerprint, "previous_event_sha256": previous, "actor": actor, "reason": reason, "trace_id": trace_id, "created_at": created_at.isoformat()}
        digest = canonical_sha256(payload)
        conn.execute(text("INSERT INTO airank_provider_credential_events (id,tenant_id,credential_id,provider_key,route_id,credential_version,event_sequence,event_type,credential_fingerprint,previous_event_sha256,event_sha256,actor,reason,trace_id,created_at) VALUES (:id,:tenant_id,:credential_id,:provider,:route_id,:version,:event_sequence,:event_type,:fingerprint,:previous,:digest,:actor,:reason,:trace_id,:created_at)"), {"id": event_id, "tenant_id": tenant_id, "credential_id": credential_id, "provider": provider, "route_id": route_id, "version": version, "event_sequence": event_sequence, "event_type": event_type, "fingerprint": fingerprint, "previous": previous, "digest": digest, "actor": actor, "reason": reason, "trace_id": trace_id, "created_at": database_datetime(created_at)})
        return digest

    def portfolio(self, tenant_id: str) -> ProviderCredentialPortfolioData:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT c.*, (SELECT e.event_sha256 FROM airank_provider_credential_events e WHERE e.tenant_id=c.tenant_id AND e.provider_key=c.provider_key AND e.route_id=c.route_id ORDER BY e.event_sequence DESC LIMIT 1) AS latest_event_sha256 FROM airank_provider_credentials c WHERE c.tenant_id=:tenant_id AND c.is_current=1"), {"tenant_id": tenant_id}).mappings().all()
        current = {(str(row["provider_key"]), str(row["route_id"])): self._from_row(row, str(row["latest_event_sha256"]) if row["latest_event_sha256"] else None) for row in rows}
        records: list[ProviderCredentialData] = []
        for manifest in PROVIDER_MANIFESTS.values():
            for route in resolve_provider_routes(manifest, self.env):
                stored = current.get((manifest.provider, route.route_id))
                if stored:
                    records.append(_record_data(stored, manifest.label, keyring_ready=self.keyring is not None))
                else:
                    records.append(ProviderCredentialData(provider=manifest.provider, label=manifest.label, route_id=route.route_id, source="environment_legacy" if route.settings.configured else "unconfigured", status="active" if route.settings.configured else "unconfigured", configured=route.settings.configured, known_limitations=["environment_credential_is_not_tenant_scoped_or_vault_rotatable"] if route.settings.configured else ["provider_credential_not_configured"]))
        return ProviderCredentialPortfolioData(keyring_status="ready" if self.keyring is not None else "blocked", credentials=records, known_limitations=[] if self.keyring is not None else ["credential_keyring_unavailable"])

    def upsert(self, tenant_id: str, provider: str, route_id: str, payload: CredentialUpsertRequest, actor: str, trace_id: str, idempotency_key: str) -> ProviderCredentialData:
        if self.keyring is None:
            raise CredentialVaultError("CREDENTIAL_KEYRING_UNAVAILABLE", "credential keyring is unavailable")
        label, _ = _route(provider, route_id, self.env)
        secret = payload.secret.get_secret_value()
        operation_type = "provider_credential.upsert"
        resource_key = f"{provider}/{route_id}"
        try:
            request_key_id = self.operation_guard.request_key_id(
                tenant_id, operation_type, resource_key, idempotency_key
            ) or self.keyring.active_fingerprint_key_id
            request_fingerprint, request_key_id = self.keyring.fingerprint_secret(
                tenant_id=tenant_id,
                provider=provider,
                route_id=route_id,
                plaintext=secret,
                fingerprint_key_id=request_key_id,
            )
            claim = self.operation_guard.claim(
                tenant_id=tenant_id,
                operation_type=operation_type,
                resource_key=resource_key,
                idempotency_key=idempotency_key,
                request_sha256=canonical_sha256(
                    {
                        "provider": provider,
                        "route_id": route_id,
                        "expected_version": payload.expected_version,
                        "reason": payload.reason,
                        "confirm_billable": payload.confirm_billable,
                        "secret_fingerprint": request_fingerprint,
                    }
                ),
                request_key_id=request_key_id,
                actor=actor,
                trace_id=trace_id,
            )
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        if claim.idempotent_replay:
            return _replayed_credential(claim.response, claim.operation_id)
        try:
            with self.engine.connect() as conn:
                current_row = self._select_current(conn, tenant_id, provider, route_id)
            actual_version = int(current_row["credential_version"]) if current_row else 0
            if actual_version != payload.expected_version:
                raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
            if current_row and self.keyring.matches_fingerprint(
                tenant_id=tenant_id,
                provider=provider,
                route_id=route_id,
                plaintext=secret,
                expected_fingerprint=str(current_row["secret_fingerprint"]),
                fingerprint_key_id=str(current_row["fingerprint_key_id"]),
            ):
                raise CredentialVaultError("CREDENTIAL_UNCHANGED", "new credential matches current credential")
            self.operation_guard.mark_external_started(claim.operation_id, actor, trace_id)
            try:
                verification = dict(
                    self.verifier.verify(
                        tenant_id=tenant_id,
                        provider=provider,
                        route_id=route_id,
                        secret=secret,
                    )
                )
            except CredentialVaultError:
                raise
            except Exception as exc:
                raise CredentialVaultError(
                    "CREDENTIAL_PROVIDER_VERIFICATION_FAILED",
                    "provider L3 verification failed",
                ) from exc
            now = utc_now()
            version = payload.expected_version + 1
            credential_id = f"provider_credential_{uuid4().hex[:16]}"
            envelope = self.keyring.encrypt(
                tenant_id=tenant_id,
                provider=provider,
                route_id=route_id,
                credential_id=credential_id,
                credential_version=version,
                plaintext=secret,
            )
            request_sha256 = canonical_sha256({"provider": provider, "route_id": route_id, "version": version, "fingerprint": envelope.secret_fingerprint, "reason": payload.reason, "verification": verification})
            with self.engine.begin() as conn:
                locked = self._select_current(conn, tenant_id, provider, route_id, for_update=True)
                locked_version = int(locked["credential_version"]) if locked else 0
                if locked_version != payload.expected_version:
                    raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
                rotated_from_id = str(locked["id"]) if locked else None
                if locked:
                    if self.keyring.matches_fingerprint(
                        tenant_id=tenant_id,
                        provider=provider,
                        route_id=route_id,
                        plaintext=secret,
                        expected_fingerprint=str(locked["secret_fingerprint"]),
                        fingerprint_key_id=str(locked["fingerprint_key_id"]),
                    ):
                        raise CredentialVaultError("CREDENTIAL_UNCHANGED", "new credential matches current credential")
                    was_active = str(locked["status"]) == "active"
                    if was_active:
                        conn.execute(text("UPDATE airank_provider_credentials SET status='rotated',is_current=0,secret_ciphertext='',secret_nonce='',secret_mask='rotated',scrubbed_at=:now WHERE id=:id"), {"now": database_datetime(now), "id": rotated_from_id})
                    else:
                        conn.execute(text("UPDATE airank_provider_credentials SET is_current=0 WHERE id=:id"), {"id": rotated_from_id})
                    self._append_event(conn, tenant_id=tenant_id, credential_id=rotated_from_id, provider=provider, route_id=route_id, version=locked_version, event_type="credential_rotated_out" if was_active else "credential_replaced_after_revoke", fingerprint=str(locked["secret_fingerprint"]), actor=actor, reason=payload.reason, trace_id=trace_id, created_at=now)
                conn.execute(text("INSERT INTO airank_provider_credentials (id,tenant_id,provider_key,route_id,credential_version,status,is_current,secret_ciphertext,secret_nonce,secret_mask,secret_fingerprint,encryption_key_id,fingerprint_key_id,algorithm,verification_json,request_sha256,rotated_from_id,reason,created_by,created_at,activated_at) VALUES (:id,:tenant_id,:provider,:route_id,:version,'active',1,:ciphertext,:nonce,:mask,:fingerprint,:encryption_key_id,:fingerprint_key_id,:algorithm,:verification_json,:request_sha256,:rotated_from_id,:reason,:actor,:now,:now)"), {"id": credential_id, "tenant_id": tenant_id, "provider": provider, "route_id": route_id, "version": version, "ciphertext": envelope.ciphertext, "nonce": envelope.nonce, "mask": envelope.secret_mask, "fingerprint": envelope.secret_fingerprint, "encryption_key_id": envelope.encryption_key_id, "fingerprint_key_id": envelope.fingerprint_key_id, "algorithm": envelope.algorithm, "verification_json": canonical_json(verification), "request_sha256": request_sha256, "rotated_from_id": rotated_from_id, "reason": payload.reason, "actor": actor, "now": database_datetime(now)})
                latest_hash = self._append_event(conn, tenant_id=tenant_id, credential_id=credential_id, provider=provider, route_id=route_id, version=version, event_type="credential_activated", fingerprint=envelope.secret_fingerprint, actor=actor, reason=payload.reason, trace_id=trace_id, created_at=now)
                row = self._select_current(conn, tenant_id, provider, route_id)
            assert row is not None
            data = _record_data(self._from_row(row, latest_hash), label, keyring_ready=True).model_copy(
                update={"operation_id": claim.operation_id}
            )
            self.operation_guard.succeed(
                claim.operation_id, data.model_dump(mode="json"), actor, trace_id
            )
            return data
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        except CredentialVaultError as exc:
            self.operation_guard.fail(claim.operation_id, exc.code, actor, trace_id)
            raise

    def revoke(self, tenant_id: str, provider: str, route_id: str, payload: CredentialRevokeRequest, actor: str, trace_id: str, idempotency_key: str) -> ProviderCredentialData:
        label, _ = _route(provider, route_id, self.env)
        operation_type = "provider_credential.revoke"
        resource_key = f"{provider}/{route_id}"
        try:
            claim = self.operation_guard.claim(
                tenant_id=tenant_id,
                operation_type=operation_type,
                resource_key=resource_key,
                idempotency_key=idempotency_key,
                request_sha256=canonical_sha256(
                    {
                        "provider": provider,
                        "route_id": route_id,
                        "expected_version": payload.expected_version,
                        "reason": payload.reason,
                    }
                ),
                request_key_id=None,
                actor=actor,
                trace_id=trace_id,
            )
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        if claim.idempotent_replay:
            return _replayed_credential(claim.response, claim.operation_id)
        try:
            with self.engine.connect() as conn:
                current = self._select_current(conn, tenant_id, provider, route_id)
            if current is None:
                raise CredentialVaultError("CREDENTIAL_NOT_FOUND", "credential was not found")
            if int(current["credential_version"]) != payload.expected_version:
                raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
            if str(current["status"]) != "active":
                raise CredentialVaultError("CREDENTIAL_ALREADY_REVOKED", "credential is already revoked")
            self.operation_guard.mark_external_started(claim.operation_id, actor, trace_id)
            now = utc_now()
            with self.engine.begin() as conn:
                row = self._select_current(conn, tenant_id, provider, route_id, for_update=True)
                if row is None:
                    raise CredentialVaultError("CREDENTIAL_NOT_FOUND", "credential was not found")
                if int(row["credential_version"]) != payload.expected_version:
                    raise CredentialVaultError("STATE_VERSION_CONFLICT", "credential version changed")
                if str(row["status"]) != "active":
                    raise CredentialVaultError("CREDENTIAL_ALREADY_REVOKED", "credential is already revoked")
                conn.execute(text("UPDATE airank_provider_credentials SET status='revoked',secret_ciphertext='',secret_nonce='',secret_mask='deleted',reason=:reason,revoked_at=:now,scrubbed_at=:now WHERE id=:id"), {"reason": payload.reason, "now": database_datetime(now), "id": row["id"]})
                latest_hash = self._append_event(conn, tenant_id=tenant_id, credential_id=str(row["id"]), provider=provider, route_id=route_id, version=int(row["credential_version"]), event_type="credential_revoked", fingerprint=str(row["secret_fingerprint"]), actor=actor, reason=payload.reason, trace_id=trace_id, created_at=now)
                updated = self._select_current(conn, tenant_id, provider, route_id)
            assert updated is not None
            data = _record_data(self._from_row(updated, latest_hash), label, keyring_ready=self.keyring is not None).model_copy(
                update={"operation_id": claim.operation_id}
            )
            self.operation_guard.succeed(
                claim.operation_id, data.model_dump(mode="json"), actor, trace_id
            )
            return data
        except OperationGuardError as exc:
            raise _guard_error(exc) from exc
        except CredentialVaultError as exc:
            self.operation_guard.fail(claim.operation_id, exc.code, actor, trace_id)
            raise

    def resolve_settings(self, provider: str, route_id: str, settings: ProviderSettings, *, context: ProviderRequestContext) -> ProviderSettings:
        with self.engine.connect() as conn:
            row = self._select_current(conn, context.tenant_id, provider, route_id)
        if row is None:
            return settings
        record = self._from_row(row)
        credential_contract = {
            "credential_source": "tenant_vault",
            "credential_id": record.credential_id,
            "credential_version": record.credential_version,
        }
        if record.status != "active":
            raise ProviderGatewayError(
                provider,
                "PROVIDER_CREDENTIAL_REVOKED",
                "tenant provider credential is revoked",
                request_contract=credential_contract,
            )
        if self.keyring is None:
            raise ProviderGatewayError(
                provider,
                "PROVIDER_CREDENTIAL_KEY_UNAVAILABLE",
                "tenant provider credential key is unavailable",
                request_contract=credential_contract,
            )
        try:
            secret = self.keyring.decrypt(tenant_id=context.tenant_id, provider=provider, route_id=route_id, credential_id=record.credential_id, credential_version=record.credential_version, envelope=record.envelope)
        except CredentialVaultError as exc:
            raise ProviderGatewayError(
                provider,
                exc.code,
                exc.message,
                request_contract=credential_contract,
            ) from exc
        return replace(settings, api_key=secret, credential_source="tenant_vault", credential_id=record.credential_id, credential_version=record.credential_version)


def build_keyring(env: Mapping[str, str] | None = None) -> CredentialKeyring | None:
    values = env if env is not None else os.environ
    configured = any(str(values.get(name) or "").strip() for name in ("AIRANK_CREDENTIAL_ACTIVE_ENCRYPTION_KEY_ID", "AIRANK_CREDENTIAL_ENCRYPTION_KEYS", "AIRANK_CREDENTIAL_ACTIVE_FINGERPRINT_KEY_ID", "AIRANK_CREDENTIAL_FINGERPRINT_KEYS"))
    if not configured:
        return None
    return CredentialKeyring.from_env(values)


def build_provider_credential_vault(database_url: str | None = None, *, env: Mapping[str, str] | None = None, verifier: CredentialVerifier | None = None) -> ProviderCredentialVault:
    values = env if env is not None else os.environ
    keyring = build_keyring(values)
    url = str(database_url or values.get("AIRANK_DATABASE_URL") or "").strip()
    if url:
        return MySQLProviderCredentialVault(url, keyring, verifier=verifier, env=values)
    return InMemoryProviderCredentialVault(keyring, verifier=verifier, env=values)


_VAULT: ProviderCredentialVault | None = None
_VAULT_SIGNATURE: tuple[str, ...] | None = None


def get_provider_credential_vault() -> ProviderCredentialVault:
    global _VAULT, _VAULT_SIGNATURE
    names = ("AIRANK_DATABASE_URL", "AIRANK_CREDENTIAL_ACTIVE_ENCRYPTION_KEY_ID", "AIRANK_CREDENTIAL_ENCRYPTION_KEYS", "AIRANK_CREDENTIAL_ACTIVE_FINGERPRINT_KEY_ID", "AIRANK_CREDENTIAL_FINGERPRINT_KEYS")
    signature = tuple(str(os.getenv(name) or "") for name in names)
    if _VAULT is None or signature != _VAULT_SIGNATURE:
        _VAULT = build_provider_credential_vault(env=os.environ)
        _VAULT_SIGNATURE = signature
    return _VAULT


def raise_vault_error(exc: CredentialVaultError) -> None:
    if exc.code in {"PROVIDER_NOT_SUPPORTED", "PROVIDER_ROUTE_NOT_FOUND", "CREDENTIAL_NOT_FOUND"}:
        status = 404
    elif exc.code in {
        "STATE_VERSION_CONFLICT",
        "CREDENTIAL_UNCHANGED",
        "CREDENTIAL_ALREADY_REVOKED",
        "OPERATION_IDEMPOTENCY_CONFLICT",
        "OPERATION_IN_PROGRESS",
        "OPERATION_OUTCOME_UNKNOWN",
        "OPERATION_STATE_CONFLICT",
        "OPERATION_PREVIOUSLY_FAILED",
    }:
        status = 409
    elif exc.code in {
        "CREDENTIAL_KEYRING_UNAVAILABLE",
        "CREDENTIAL_KEYRING_CONFIG_INVALID",
        "CREDENTIAL_KEY_ID_INVALID",
        "CREDENTIAL_KEY_MATERIAL_INVALID",
        "CREDENTIAL_KEY_MATERIAL_DUPLICATE",
        "CREDENTIAL_KEY_DOMAIN_REUSE",
        "CREDENTIAL_ENCRYPTION_KEY_UNAVAILABLE",
        "CREDENTIAL_FINGERPRINT_KEY_UNAVAILABLE",
        "CREDENTIAL_ALGORITHM_UNSUPPORTED",
        "CREDENTIAL_DECRYPTION_FAILED",
    }:
        status = 503
    else:
        status = 422
    raise error(status, exc.code, {"reason": exc.message}) from exc


@router.get("/admin/provider-credentials", response_model=ProviderCredentialPortfolioResponse)
def list_provider_credentials(tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> ProviderCredentialPortfolioResponse:
    require_provider_admin(permission_header)
    try:
        data = get_provider_credential_vault().portfolio(tenant_id)
    except CredentialVaultError as exc:
        raise_vault_error(exc)
    return ProviderCredentialPortfolioResponse(data=data, meta=response_meta(trace_id))


@router.put("/admin/provider-credentials/{provider}/{route_id}", response_model=ProviderCredentialResponse)
def upsert_provider_credential(provider: str, route_id: str, payload: CredentialUpsertRequest, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160), tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> ProviderCredentialResponse:
    require_provider_admin(permission_header); actor = trusted_actor(authenticated_actor); trusted_trace = trace_id or f"trc_{uuid4().hex[:16]}"
    try:
        data = get_provider_credential_vault().upsert(tenant_id, provider, route_id, payload, actor, trusted_trace, idempotency_key)
    except CredentialVaultError as exc:
        raise_vault_error(exc)
    return ProviderCredentialResponse(data=data, meta=response_meta(trusted_trace))


@router.post("/admin/provider-credentials/{provider}/{route_id}/revoke", response_model=ProviderCredentialResponse)
def revoke_provider_credential(provider: str, route_id: str, payload: CredentialRevokeRequest, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160), tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> ProviderCredentialResponse:
    require_provider_admin(permission_header); actor = trusted_actor(authenticated_actor); trusted_trace = trace_id or f"trc_{uuid4().hex[:16]}"
    try:
        data = get_provider_credential_vault().revoke(tenant_id, provider, route_id, payload, actor, trusted_trace, idempotency_key)
    except CredentialVaultError as exc:
        raise_vault_error(exc)
    return ProviderCredentialResponse(data=data, meta=response_meta(trusted_trace))

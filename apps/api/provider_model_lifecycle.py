from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from typing import Any, Literal, Mapping, Optional
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_provider_gateway import ModelLifecycle


router = APIRouter(prefix="/api/v1", tags=["provider-model-lifecycle"])
CONTRACT_VERSION = "airank.provider-model-migration.v1"
DEFAULT_EXECUTION_WINDOW_DAYS = 30
DEFAULT_RELEASE_WINDOW_DAYS = 90
APPROVED_MIGRATION_STATUSES = {"approved", "activated"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def positive_env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name) or default))
    except ValueError:
        return default


def derive_model_lifecycle(
    lifecycle: ModelLifecycle | None,
    *,
    migration_status: str | None = None,
    now: datetime | None = None,
    execution_window_days: int | None = None,
    release_window_days: int | None = None,
) -> dict[str, object]:
    """Derive execution and release gates without mutating Provider evidence."""

    execution_days = (
        execution_window_days
        if execution_window_days is not None
        else positive_env_int(
            "AIRANK_PROVIDER_MODEL_MIN_DAYS_TO_SUNSET", DEFAULT_EXECUTION_WINDOW_DAYS
        )
    )
    release_days = (
        release_window_days
        if release_window_days is not None
        else positive_env_int(
            "AIRANK_PROVIDER_MODEL_RELEASE_MIN_DAYS_TO_SUNSET", DEFAULT_RELEASE_WINDOW_DAYS
        )
    )
    release_days = max(execution_days, release_days)
    if lifecycle is None:
        return {
            "lifecycle_status": "unmanaged",
            "sunset_at": None,
            "replacement_model": None,
            "lifecycle_source": None,
            "days_to_sunset": None,
            "execution_min_days_to_sunset": execution_days,
            "release_min_days_to_sunset": release_days,
            "execution_gate_status": "pass",
            "release_gate_status": "pass",
            "lifecycle_reason": "manifest has no announced sunset for the configured model",
        }

    current = now or utc_now()
    remaining_seconds = (lifecycle.sunset_at - current).total_seconds()
    days_to_sunset = math.ceil(remaining_seconds / 86_400)
    approved = migration_status in APPROVED_MIGRATION_STATUSES
    if remaining_seconds <= 0:
        status = "expired"
        execution_gate = "blocked"
        release_gate = "blocked"
        reason = f"configured model expired; migrate to {lifecycle.replacement}"
    elif remaining_seconds <= execution_days * 86_400:
        status = "required"
        execution_gate = "blocked"
        release_gate = "blocked"
        reason = (
            f"configured model is inside the {execution_days}-day execution stop window; "
            f"switch to {lifecycle.replacement}"
        )
    elif remaining_seconds <= release_days * 86_400:
        status = "migration_planning"
        execution_gate = "pass"
        release_gate = "pass" if approved else "blocked"
        reason = (
            f"validated migration is approved for {lifecycle.replacement}"
            if approved
            else f"release requires a validated and approved migration to {lifecycle.replacement}"
        )
    else:
        status = "current"
        execution_gate = "pass"
        release_gate = "pass"
        reason = f"sunset is outside the {release_days}-day release planning window"
    return {
        "lifecycle_status": status,
        "sunset_at": lifecycle.sunset_at.isoformat(),
        "replacement_model": lifecycle.replacement,
        "lifecycle_source": lifecycle.source,
        "days_to_sunset": days_to_sunset,
        "execution_min_days_to_sunset": execution_days,
        "release_min_days_to_sunset": release_days,
        "execution_gate_status": execution_gate,
        "release_gate_status": release_gate,
        "lifecycle_reason": reason,
    }


class ProviderModelMigrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ProviderModelMigrationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["doubao", "qianwen", "kimi", "deepseek"]
    route_id: str = Field(min_length=1, max_length=64)
    from_model: str = Field(min_length=1, max_length=160)
    to_model: str = Field(min_length=1, max_length=160)
    from_configuration_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    reason: str = Field(min_length=3, max_length=500)


class ProviderModelMigrationValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_audit_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ProviderModelMigrationApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ProviderModelMigrationEventData(BaseModel):
    event_sequence: int
    event_type: str
    from_status: Optional[str] = None
    to_status: str
    plan_version: int
    request_audit_id: Optional[str] = None
    previous_event_sha256: Optional[str] = None
    event_sha256: str
    actor: str
    reason: str
    trace_id: str
    created_at: datetime


class ProviderModelMigrationData(BaseModel):
    contract_version: Literal["airank.provider-model-migration.v1"] = CONTRACT_VERSION
    migration_id: str
    tenant_id: str
    provider: str
    route_id: str
    from_model: str
    to_model: str
    from_configuration_fingerprint: str
    status: Literal[
        "planned", "validation_failed", "validated", "approved", "activated", "canceled"
    ]
    plan_version: int
    validation_request_audit_id: Optional[str] = None
    validation_provider_request_id_present: bool
    validation_configuration_fingerprint: Optional[str] = None
    validation_requested_at: Optional[datetime] = None
    reason: str
    created_by: str
    validated_by: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    validated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    latest_event_sha256: str
    event_chain_status: Literal["valid", "invalid"]
    validation_evidence_status: Literal["valid", "missing", "invalid"]
    release_eligible: bool
    events: list[ProviderModelMigrationEventData] = Field(default_factory=list)


class ProviderModelMigrationResponse(BaseModel):
    data: ProviderModelMigrationData
    meta: dict[str, str]


class ProviderModelMigrationPortfolioData(BaseModel):
    contract: Literal["airank.provider-model-migration.v1"] = CONTRACT_VERSION
    migrations: list[ProviderModelMigrationData]


class ProviderModelMigrationPortfolioResponse(BaseModel):
    data: ProviderModelMigrationPortfolioData
    meta: dict[str, str]


class MySQLProviderModelLifecycle:
    def __init__(self, database_url: str | Any) -> None:
        self.engine = (
            create_engine(database_url, pool_pre_ping=True)
            if isinstance(database_url, str)
            else database_url
        )

    @staticmethod
    def _event_from_row(row: Mapping[str, Any]) -> dict[str, object]:
        return {
            "event_sequence": int(row["event_sequence"]),
            "event_type": str(row["event_type"]),
            "from_status": str(row["from_status"]) if row["from_status"] else None,
            "to_status": str(row["to_status"]),
            "plan_version": int(row["plan_version"]),
            "request_audit_id": str(row["request_audit_id"]) if row["request_audit_id"] else None,
            "previous_event_sha256": (
                str(row["previous_event_sha256"]) if row["previous_event_sha256"] else None
            ),
            "event_sha256": str(row["event_sha256"]),
            "actor": str(row["actor"]),
            "reason": str(row["reason"]),
            "trace_id": str(row["trace_id"]),
            "created_at": row["created_at"].replace(tzinfo=timezone.utc),
        }

    @staticmethod
    def _plan_from_row(
        row: Mapping[str, Any], events: list[dict[str, object]] | None = None
    ) -> dict[str, object]:
        event_list = events or []
        latest_hash = (
            str(row["latest_event_sha256"])
            if "latest_event_sha256" in row and row["latest_event_sha256"]
            else str(event_list[-1]["event_sha256"] if event_list else "")
        )
        return {
            "contract_version": CONTRACT_VERSION,
            "migration_id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "provider": str(row["provider_key"]),
            "route_id": str(row["route_id"]),
            "from_model": str(row["from_model"]),
            "to_model": str(row["to_model"]),
            "from_configuration_fingerprint": str(row["from_configuration_fingerprint"]),
            "status": str(row["status"]),
            "plan_version": int(row["plan_version"]),
            "validation_request_audit_id": (
                str(row["validation_request_audit_id"])
                if row["validation_request_audit_id"]
                else None
            ),
            "validation_provider_request_id_present": bool(
                row["validation_provider_request_id"]
            ),
            "validation_configuration_fingerprint": (
                str(row["validation_configuration_fingerprint"])
                if row["validation_configuration_fingerprint"]
                else None
            ),
            "validation_requested_at": (
                row["validation_requested_at"].replace(tzinfo=timezone.utc)
                if row["validation_requested_at"]
                else None
            ),
            "reason": str(row["reason"]),
            "created_by": str(row["created_by"]),
            "validated_by": str(row["validated_by"]) if row["validated_by"] else None,
            "approved_by": str(row["approved_by"]) if row["approved_by"] else None,
            "created_at": row["created_at"].replace(tzinfo=timezone.utc),
            "updated_at": row["updated_at"].replace(tzinfo=timezone.utc),
            "validated_at": (
                row["validated_at"].replace(tzinfo=timezone.utc) if row["validated_at"] else None
            ),
            "approved_at": (
                row["approved_at"].replace(tzinfo=timezone.utc) if row["approved_at"] else None
            ),
            "latest_event_sha256": latest_hash,
            "event_chain_status": str(row.get("event_chain_status") or "invalid"),
            "validation_evidence_status": str(
                row.get("validation_evidence_status") or "missing"
            ),
            "release_eligible": bool(row.get("release_eligible")),
            "events": event_list,
        }

    @staticmethod
    def _event_chain_valid(row: Mapping[str, Any], events: list[Mapping[str, Any]]) -> bool:
        previous: str | None = None
        for expected_sequence, event in enumerate(events, start=1):
            if int(event["event_sequence"]) != expected_sequence:
                return False
            if (str(event["previous_event_sha256"]) if event["previous_event_sha256"] else None) != previous:
                return False
            payload = {
                "contract_version": CONTRACT_VERSION,
                "event_id": str(event["id"]),
                "tenant_id": str(event["tenant_id"]),
                "migration_id": str(event["migration_id"]),
                "event_sequence": int(event["event_sequence"]),
                "event_type": str(event["event_type"]),
                "from_status": str(event["from_status"]) if event["from_status"] else None,
                "to_status": str(event["to_status"]),
                "plan_version": int(event["plan_version"]),
                "request_audit_id": str(event["request_audit_id"]) if event["request_audit_id"] else None,
                "previous_event_sha256": previous,
                "actor": str(event["actor"]),
                "reason": str(event["reason"]),
                "trace_id": str(event["trace_id"]),
                "created_at": event["created_at"].replace(tzinfo=timezone.utc).isoformat(),
            }
            digest = canonical_sha256(payload)
            if digest != str(event["event_sha256"]):
                return False
            previous = digest
        return bool(events) and int(events[-1]["plan_version"]) == int(row["plan_version"])

    @staticmethod
    def _validation_evidence_status(conn: Any, row: Mapping[str, Any]) -> str:
        audit_id = row["validation_request_audit_id"]
        if not audit_id:
            return "missing"
        audit = conn.execute(
            text(
                "SELECT provider_key,route_id,model_name,configuration_fingerprint,"
                "provider_request_id,outcome,requested_at,completed_at "
                "FROM airank_provider_request_audits "
                "WHERE tenant_id=:tenant_id AND id=:audit_id"
            ),
            {"tenant_id": row["tenant_id"], "audit_id": audit_id},
        ).mappings().first()
        if not audit:
            return "invalid"
        valid = bool(
            str(audit["provider_key"]) == str(row["provider_key"])
            and str(audit["route_id"] or "") == str(row["route_id"])
            and str(audit["model_name"]) == str(row["to_model"])
            and str(audit["configuration_fingerprint"])
            == str(row["validation_configuration_fingerprint"] or "")
            and str(audit["outcome"]) == "success"
            and str(audit["provider_request_id"] or "").strip()
            and str(audit["provider_request_id"])
            == str(row["validation_provider_request_id"] or "")
            and audit["completed_at"] is not None
            and audit["requested_at"] >= row["created_at"]
        )
        return "valid" if valid else "invalid"

    def _integrity_fields(
        self, conn: Any, row: Mapping[str, Any], events: list[Mapping[str, Any]]
    ) -> dict[str, object]:
        event_valid = self._event_chain_valid(row, events)
        evidence_status = self._validation_evidence_status(conn, row)
        return {
            "event_chain_status": "valid" if event_valid else "invalid",
            "validation_evidence_status": evidence_status,
            "release_eligible": bool(
                str(row["status"]) in APPROVED_MIGRATION_STATUSES
                and event_valid
                and evidence_status == "valid"
            ),
        }

    def _append_event(
        self,
        conn: Any,
        *,
        row: Mapping[str, Any],
        event_type: str,
        from_status: str | None,
        to_status: str,
        plan_version: int,
        request_audit_id: str | None,
        actor: str,
        reason: str,
        trace_id: str,
        created_at: datetime,
    ) -> None:
        created_at = created_at.astimezone(timezone.utc).replace(
            microsecond=(created_at.microsecond // 1000) * 1000
        )
        latest = conn.execute(
            text(
                "SELECT event_sequence,event_sha256 FROM airank_provider_model_migration_events "
                "WHERE tenant_id=:tenant_id AND migration_id=:migration_id "
                "ORDER BY event_sequence DESC LIMIT 1 FOR UPDATE"
            ),
            {"tenant_id": row["tenant_id"], "migration_id": row["id"]},
        ).mappings().first()
        sequence = int(latest["event_sequence"]) + 1 if latest else 1
        previous = str(latest["event_sha256"]) if latest else None
        event_id = f"pmme_{uuid4().hex}"
        payload = {
            "contract_version": CONTRACT_VERSION,
            "event_id": event_id,
            "tenant_id": row["tenant_id"],
            "migration_id": row["id"],
            "event_sequence": sequence,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "plan_version": plan_version,
            "request_audit_id": request_audit_id,
            "previous_event_sha256": previous,
            "actor": actor,
            "reason": reason,
            "trace_id": trace_id,
            "created_at": created_at.isoformat(),
        }
        digest = canonical_sha256(payload)
        conn.execute(
            text(
                "INSERT INTO airank_provider_model_migration_events "
                "(id,tenant_id,migration_id,event_sequence,event_type,from_status,to_status,"
                "plan_version,request_audit_id,previous_event_sha256,event_sha256,actor,reason,"
                "trace_id,created_at) VALUES (:id,:tenant_id,:migration_id,:event_sequence,"
                ":event_type,:from_status,:to_status,:plan_version,:request_audit_id,:previous,"
                ":digest,:actor,:reason,:trace_id,:created_at)"
            ),
            {
                **payload,
                "id": event_id,
                "previous": previous,
                "digest": digest,
                "created_at": database_datetime(created_at),
            },
        )

    def get(self, tenant_id: str, migration_id: str) -> dict[str, object] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM airank_provider_model_migrations "
                    "WHERE tenant_id=:tenant_id AND id=:migration_id"
                ),
                {"tenant_id": tenant_id, "migration_id": migration_id},
            ).mappings().first()
            if row is None:
                return None
            event_rows = conn.execute(
                    text(
                        "SELECT * FROM airank_provider_model_migration_events "
                        "WHERE tenant_id=:tenant_id AND migration_id=:migration_id "
                        "ORDER BY event_sequence"
                    ),
                    {"tenant_id": tenant_id, "migration_id": migration_id},
                ).mappings().all()
            integrity = self._integrity_fields(conn, row, event_rows)
            record = {**dict(row), **integrity}
            events = [self._event_from_row(event) for event in event_rows]
        return self._plan_from_row(record, events)

    def list(self, tenant_id: str) -> list[dict[str, object]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT m.*, (SELECT e.event_sha256 FROM airank_provider_model_migration_events e "
                    "WHERE e.tenant_id=m.tenant_id AND e.migration_id=m.id "
                    "ORDER BY e.event_sequence DESC LIMIT 1) AS latest_event_sha256 "
                    "FROM airank_provider_model_migrations m WHERE m.tenant_id=:tenant_id "
                    "ORDER BY m.updated_at DESC, m.id DESC"
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
            records: list[dict[str, object]] = []
            for row in rows:
                event_rows = conn.execute(
                    text(
                        "SELECT * FROM airank_provider_model_migration_events "
                        "WHERE tenant_id=:tenant_id AND migration_id=:migration_id "
                        "ORDER BY event_sequence"
                    ),
                    {"tenant_id": tenant_id, "migration_id": row["id"]},
                ).mappings().all()
                integrity = self._integrity_fields(conn, row, event_rows)
                records.append(
                    self._plan_from_row(
                        {**dict(row), **integrity},
                        [self._event_from_row(event) for event in event_rows],
                    )
                )
        return records

    def latest_plan_map(self, tenant_id: str) -> dict[tuple[str, str, str, str], dict[str, object]]:
        return {
            (
                str(item["provider"]),
                str(item["route_id"]),
                str(item["from_model"]),
                str(item["from_configuration_fingerprint"]),
            ): item
            for item in self.list(tenant_id)
        }

    def create(
        self,
        tenant_id: str,
        payload: ProviderModelMigrationCreateRequest,
        *,
        actor: str,
        trace_id: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        request_basis = payload.model_dump()
        request_sha = canonical_sha256(request_basis)
        key_sha = canonical_sha256({"idempotency_key": idempotency_key})
        now = utc_now()
        migration_id: str | None = None
        concurrent_reconcile = False
        with self.engine.begin() as conn:
            replay = conn.execute(
                text(
                    "SELECT * FROM airank_provider_model_migrations "
                    "WHERE tenant_id=:tenant_id AND idempotency_key_sha256=:key_sha"
                ),
                {"tenant_id": tenant_id, "key_sha": key_sha},
            ).mappings().first()
            if replay:
                if str(replay["request_sha256"]) != request_sha:
                    raise ProviderModelMigrationError(
                        "PROVIDER_MODEL_MIGRATION_IDEMPOTENCY_CONFLICT",
                        "idempotency key was already used with a different migration request",
                    )
                migration_id = str(replay["id"])
            else:
                route = conn.execute(
                    text(
                        "SELECT model_name,configuration_fingerprint FROM airank_provider_routes "
                        "WHERE provider_key=:provider AND route_id=:route_id AND is_current=1 "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"provider": payload.provider, "route_id": payload.route_id},
                ).mappings().first()
                if route is None:
                    raise ProviderModelMigrationError(
                        "PROVIDER_ROUTE_NOT_FOUND", "current Provider route was not found", status_code=404
                    )
                if (
                    str(route["model_name"]) != payload.from_model
                    or str(route["configuration_fingerprint"])
                    != payload.from_configuration_fingerprint
                ):
                    raise ProviderModelMigrationError(
                        "PROVIDER_MODEL_MIGRATION_BASIS_CONFLICT",
                        "configured Provider route changed; reload before creating a migration",
                    )
                manifest = conn.execute(
                    text(
                        "SELECT lifecycle_json FROM airank_provider_manifests "
                        "WHERE provider_key=:provider AND is_current=1 "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"provider": payload.provider},
                ).mappings().first()
                lifecycle_map = json.loads(str(manifest["lifecycle_json"])) if manifest else {}
                lifecycle = lifecycle_map.get(payload.from_model) if isinstance(lifecycle_map, dict) else None
                if not isinstance(lifecycle, dict):
                    raise ProviderModelMigrationError(
                        "PROVIDER_MODEL_LIFECYCLE_UNMANAGED",
                        "configured model has no announced lifecycle requiring migration",
                        status_code=422,
                    )
                if str(lifecycle.get("replacement") or "") != payload.to_model:
                    raise ProviderModelMigrationError(
                        "PROVIDER_MODEL_MIGRATION_TARGET_INVALID",
                        "target model must match the manifest replacement",
                        status_code=422,
                    )
                migration_id = f"pmm_{uuid4().hex}"
                row_values = {
                    "id": migration_id,
                    "tenant_id": tenant_id,
                    "provider": payload.provider,
                    "route_id": payload.route_id,
                    "from_model": payload.from_model,
                    "to_model": payload.to_model,
                    "fingerprint": payload.from_configuration_fingerprint,
                    "key_sha": key_sha,
                    "request_sha": request_sha,
                    "reason": payload.reason.strip(),
                    "actor": actor,
                    "now": database_datetime(now),
                }
                insert_result = conn.execute(
                    text(
                        "INSERT IGNORE INTO airank_provider_model_migrations "
                        "(id,tenant_id,provider_key,route_id,from_model,to_model,"
                        "from_configuration_fingerprint,status,plan_version,idempotency_key_sha256,"
                        "request_sha256,reason,created_by,created_at,updated_at) VALUES "
                        "(:id,:tenant_id,:provider,:route_id,:from_model,:to_model,:fingerprint,"
                        "'planned',1,:key_sha,:request_sha,:reason,:actor,:now,:now)"
                    ),
                    row_values,
                )
                if insert_result.rowcount == 1:
                    event_row = {
                        "id": migration_id,
                        "tenant_id": tenant_id,
                    }
                    self._append_event(
                        conn,
                        row=event_row,
                        event_type="migration_planned",
                        from_status=None,
                        to_status="planned",
                        plan_version=1,
                        request_audit_id=None,
                        actor=actor,
                        reason=payload.reason.strip(),
                        trace_id=trace_id,
                        created_at=now,
                    )
                else:
                    concurrent_reconcile = True
        if concurrent_reconcile:
            with self.engine.connect() as conn:
                concurrent = conn.execute(
                    text(
                        "SELECT * FROM airank_provider_model_migrations WHERE tenant_id=:tenant_id "
                        "AND (idempotency_key_sha256=:key_sha OR "
                        "(provider_key=:provider AND route_id=:route_id "
                        "AND from_configuration_fingerprint=:fingerprint))"
                    ),
                    row_values,
                ).mappings().first()
            if concurrent is None:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_BASIS_CONFLICT",
                    "concurrent migration creation could not be reconciled",
                )
            if str(concurrent["idempotency_key_sha256"]) == key_sha:
                if str(concurrent["request_sha256"]) != request_sha:
                    raise ProviderModelMigrationError(
                        "PROVIDER_MODEL_MIGRATION_IDEMPOTENCY_CONFLICT",
                        "idempotency key was concurrently used with a different request",
                    )
                migration_id = str(concurrent["id"])
            else:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_BASIS_CONFLICT",
                    "a migration already exists for the current route configuration",
                )
        if migration_id is None:  # pragma: no cover - all successful branches assign an id
            raise ProviderModelMigrationError(
                "PROVIDER_MODEL_MIGRATION_BASIS_CONFLICT", "migration id was not resolved"
            )
        result = self.get(tenant_id, migration_id)
        if result is None:  # pragma: no cover - same transaction inserted the plan
            raise ProviderModelMigrationError("PROVIDER_MODEL_MIGRATION_NOT_FOUND", "migration disappeared")
        return result

    def bind_validation(
        self,
        tenant_id: str,
        migration_id: str,
        payload: ProviderModelMigrationValidateRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> dict[str, object]:
        now = utc_now()
        validation_error: ProviderModelMigrationError | None = None
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM airank_provider_model_migrations "
                    "WHERE tenant_id=:tenant_id AND id=:migration_id FOR UPDATE"
                ),
                {"tenant_id": tenant_id, "migration_id": migration_id},
            ).mappings().first()
            if row is None:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_NOT_FOUND", "migration was not found", status_code=404
                )
            if int(row["plan_version"]) != payload.expected_version:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_VERSION_CONFLICT", "migration version changed; reload"
                )
            if str(row["status"]) not in {"planned", "validation_failed"}:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_STATE_INVALID",
                    "only planned or validation_failed migrations can bind validation evidence",
                )
            audit = conn.execute(
                text(
                    "SELECT id,provider_key,route_id,model_name,configuration_fingerprint,"
                    "provider_request_id,outcome,requested_at,completed_at "
                    "FROM airank_provider_request_audits "
                    "WHERE tenant_id=:tenant_id AND id=:audit_id FOR UPDATE"
                ),
                {"tenant_id": tenant_id, "audit_id": payload.request_audit_id},
            ).mappings().first()
            valid = bool(
                audit
                and str(audit["provider_key"]) == str(row["provider_key"])
                and str(audit["route_id"] or "") == str(row["route_id"])
                and str(audit["model_name"]) == str(row["to_model"])
                and str(audit["outcome"]) == "success"
                and str(audit["provider_request_id"] or "").strip()
                and audit["completed_at"] is not None
                and audit["requested_at"] >= row["created_at"]
            )
            next_version = int(row["plan_version"]) + 1
            if not valid:
                conn.execute(
                    text(
                        "UPDATE airank_provider_model_migrations SET status='validation_failed',"
                        "plan_version=:version,reason=:reason,validated_by=:actor,updated_at=:now "
                        "WHERE tenant_id=:tenant_id AND id=:migration_id"
                    ),
                    {
                        "version": next_version,
                        "reason": payload.reason.strip(),
                        "actor": actor,
                        "now": database_datetime(now),
                        "tenant_id": tenant_id,
                        "migration_id": migration_id,
                    },
                )
                self._append_event(
                    conn,
                    row=row,
                    event_type="validation_rejected",
                    from_status=str(row["status"]),
                    to_status="validation_failed",
                    plan_version=next_version,
                    request_audit_id=None,
                    actor=actor,
                    reason=payload.reason.strip(),
                    trace_id=trace_id,
                    created_at=now,
                )
                validation_error = ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_VALIDATION_FAILED",
                    "target model requires a post-plan successful L3 request audit with a Provider request id",
                    status_code=422,
                )
            else:
                conn.execute(
                    text(
                        "UPDATE airank_provider_model_migrations SET status='validated',"
                        "plan_version=:version,validation_request_audit_id=:audit_id,"
                        "validation_provider_request_id=:provider_request_id,"
                        "validation_configuration_fingerprint=:fingerprint,"
                        "validation_requested_at=:requested_at,reason=:reason,validated_by=:actor,"
                        "validated_at=:now,updated_at=:now WHERE tenant_id=:tenant_id AND id=:migration_id"
                    ),
                    {
                        "version": next_version,
                        "audit_id": audit["id"],
                        "provider_request_id": audit["provider_request_id"],
                        "fingerprint": audit["configuration_fingerprint"],
                        "requested_at": audit["requested_at"],
                        "reason": payload.reason.strip(),
                        "actor": actor,
                        "now": database_datetime(now),
                        "tenant_id": tenant_id,
                        "migration_id": migration_id,
                    },
                )
                self._append_event(
                    conn,
                    row=row,
                    event_type="target_l3_validated",
                    from_status=str(row["status"]),
                    to_status="validated",
                    plan_version=next_version,
                    request_audit_id=str(audit["id"]),
                    actor=actor,
                    reason=payload.reason.strip(),
                    trace_id=trace_id,
                    created_at=now,
                )
        if validation_error is not None:
            raise validation_error
        result = self.get(tenant_id, migration_id)
        assert result is not None
        return result

    def approve(
        self,
        tenant_id: str,
        migration_id: str,
        payload: ProviderModelMigrationApproveRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> dict[str, object]:
        now = utc_now()
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM airank_provider_model_migrations "
                    "WHERE tenant_id=:tenant_id AND id=:migration_id FOR UPDATE"
                ),
                {"tenant_id": tenant_id, "migration_id": migration_id},
            ).mappings().first()
            if row is None:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_NOT_FOUND", "migration was not found", status_code=404
                )
            if int(row["plan_version"]) != payload.expected_version:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_VERSION_CONFLICT", "migration version changed; reload"
                )
            if str(row["status"]) != "validated" or not row["validation_request_audit_id"]:
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_APPROVAL_BLOCKED",
                    "approval requires bound successful L3 validation evidence",
                )
            audit = conn.execute(
                text(
                    "SELECT outcome,provider_request_id,model_name FROM airank_provider_request_audits "
                    "WHERE tenant_id=:tenant_id AND id=:audit_id"
                ),
                {"tenant_id": tenant_id, "audit_id": row["validation_request_audit_id"]},
            ).mappings().first()
            if not (
                audit
                and str(audit["outcome"]) == "success"
                and str(audit["provider_request_id"] or "").strip()
                and str(audit["model_name"]) == str(row["to_model"])
            ):
                raise ProviderModelMigrationError(
                    "PROVIDER_MODEL_MIGRATION_APPROVAL_BLOCKED",
                    "bound target validation audit is no longer valid",
                )
            next_version = int(row["plan_version"]) + 1
            conn.execute(
                text(
                    "UPDATE airank_provider_model_migrations SET status='approved',"
                    "plan_version=:version,reason=:reason,approved_by=:actor,approved_at=:now,"
                    "updated_at=:now WHERE tenant_id=:tenant_id AND id=:migration_id"
                ),
                {
                    "version": next_version,
                    "reason": payload.reason.strip(),
                    "actor": actor,
                    "now": database_datetime(now),
                    "tenant_id": tenant_id,
                    "migration_id": migration_id,
                },
            )
            self._append_event(
                conn,
                row=row,
                event_type="migration_approved",
                from_status="validated",
                to_status="approved",
                plan_version=next_version,
                request_audit_id=str(row["validation_request_audit_id"]),
                actor=actor,
                reason=payload.reason.strip(),
                trace_id=trace_id,
                created_at=now,
            )
        result = self.get(tenant_id, migration_id)
        assert result is not None
        return result

    def list_release_gates(
        self,
        tenant_id: str,
        *,
        now: datetime | None = None,
        execution_window_days: int | None = None,
        release_window_days: int | None = None,
    ) -> list[dict[str, object]]:
        plans = self.latest_plan_map(tenant_id)
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT r.provider_key,r.route_id,r.model_name,r.configuration_fingerprint,"
                    "m.lifecycle_json,COALESCE(c.enabled,1) AS enabled "
                    "FROM airank_provider_routes r "
                    "JOIN airank_provider_manifests m ON m.provider_key=r.provider_key AND m.is_current=1 "
                    "LEFT JOIN airank_provider_route_controls c "
                    "ON c.provider_key=r.provider_key AND c.route_id=r.route_id "
                    "WHERE r.is_current=1"
                )
            ).mappings().all()
        result: list[dict[str, object]] = []
        for row in rows:
            if not bool(row["enabled"]):
                continue
            lifecycle_map = json.loads(str(row["lifecycle_json"] or "{}"))
            raw = lifecycle_map.get(str(row["model_name"])) if isinstance(lifecycle_map, dict) else None
            lifecycle = None
            if isinstance(raw, dict) and raw.get("sunset_at") and raw.get("replacement"):
                lifecycle = ModelLifecycle(
                    sunset_at=datetime.fromisoformat(str(raw["sunset_at"]).replace("Z", "+00:00")),
                    replacement=str(raw["replacement"]),
                    source=str(raw.get("source") or "unknown"),
                )
            key = (
                str(row["provider_key"]),
                str(row["route_id"]),
                str(row["model_name"]),
                str(row["configuration_fingerprint"]),
            )
            plan = plans.get(key)
            effective_migration_status = (
                str(plan["status"])
                if plan is not None and bool(plan["release_eligible"])
                else None
            )
            derived = derive_model_lifecycle(
                lifecycle,
                migration_status=effective_migration_status,
                now=now,
                execution_window_days=execution_window_days,
                release_window_days=release_window_days,
            )
            result.append(
                {
                    "provider": key[0],
                    "route_id": key[1],
                    "model": key[2],
                    "configuration_fingerprint": key[3],
                    "migration_id": str(plan["migration_id"]) if plan else None,
                    "migration_status": str(plan["status"]) if plan else None,
                    "migration_release_eligible": (
                        bool(plan["release_eligible"]) if plan else False
                    ),
                    **derived,
                }
            )
        return result


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


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
        raise StarletteHTTPException(
            status_code=403,
            detail={"code": "AUTH_PERMISSION_FORBIDDEN", "details": {"required_permission": required}},
        )


def trusted_actor(value: Optional[str]) -> str:
    actor = str(value or "").strip()
    if actor:
        return actor[:128]
    if not auth_enforcement_required():
        return "dev_only_provider_admin"
    raise StarletteHTTPException(
        status_code=401,
        detail={"code": "AUTH_TOKEN_INVALID", "details": {"reason": "authenticated_actor_required"}},
    )


def repository() -> MySQLProviderModelLifecycle:
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    if not database_url:
        raise StarletteHTTPException(
            status_code=503,
            detail={"code": "INTEGRATION_CAPABILITY_BLOCKED", "details": {"capability": "provider_model_lifecycle"}},
        )
    return MySQLProviderModelLifecycle(database_url)


def raise_migration_error(exc: ProviderModelMigrationError) -> None:
    raise StarletteHTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "details": {"reason": exc.message}},
    ) from exc


@router.get(
    "/admin/provider-model-migrations",
    response_model=ProviderModelMigrationPortfolioResponse,
    response_model_exclude_none=True,
)
def list_provider_model_migrations(
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ProviderModelMigrationPortfolioResponse:
    require_provider_admin(permissions)
    records = repository().list(tenant_id)
    return ProviderModelMigrationPortfolioResponse(
        data=ProviderModelMigrationPortfolioData(
            migrations=[ProviderModelMigrationData.model_validate(item) for item in records]
        ),
        meta=response_meta(trace_id),
    )


@router.post(
    "/admin/provider-model-migrations",
    response_model=ProviderModelMigrationResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_provider_model_migration(
    payload: ProviderModelMigrationCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    actor_header: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ProviderModelMigrationResponse:
    require_provider_admin(permissions)
    actor = trusted_actor(actor_header)
    trusted_trace = trace_id or f"trc_{uuid4().hex[:16]}"
    try:
        record = repository().create(
            tenant_id,
            payload,
            actor=actor,
            trace_id=trusted_trace,
            idempotency_key=idempotency_key,
        )
    except ProviderModelMigrationError as exc:
        raise_migration_error(exc)
    return ProviderModelMigrationResponse(
        data=ProviderModelMigrationData.model_validate(record), meta=response_meta(trusted_trace)
    )


@router.post(
    "/admin/provider-model-migrations/{migration_id}/validate",
    response_model=ProviderModelMigrationResponse,
    response_model_exclude_none=True,
)
def validate_provider_model_migration(
    migration_id: str,
    payload: ProviderModelMigrationValidateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    actor_header: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ProviderModelMigrationResponse:
    require_provider_admin(permissions)
    actor = trusted_actor(actor_header)
    trusted_trace = trace_id or f"trc_{uuid4().hex[:16]}"
    try:
        record = repository().bind_validation(
            tenant_id, migration_id, payload, actor=actor, trace_id=trusted_trace
        )
    except ProviderModelMigrationError as exc:
        raise_migration_error(exc)
    return ProviderModelMigrationResponse(
        data=ProviderModelMigrationData.model_validate(record), meta=response_meta(trusted_trace)
    )


@router.post(
    "/admin/provider-model-migrations/{migration_id}/approve",
    response_model=ProviderModelMigrationResponse,
    response_model_exclude_none=True,
)
def approve_provider_model_migration(
    migration_id: str,
    payload: ProviderModelMigrationApproveRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    actor_header: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ProviderModelMigrationResponse:
    require_provider_admin(permissions)
    actor = trusted_actor(actor_header)
    trusted_trace = trace_id or f"trc_{uuid4().hex[:16]}"
    try:
        record = repository().approve(
            tenant_id, migration_id, payload, actor=actor, trace_id=trusted_trace
        )
    except ProviderModelMigrationError as exc:
        raise_migration_error(exc)
    return ProviderModelMigrationResponse(
        data=ProviderModelMigrationData.model_validate(record), meta=response_meta(trusted_trace)
    )

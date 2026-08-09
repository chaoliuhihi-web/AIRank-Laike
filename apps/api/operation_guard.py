from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from threading import Lock
from typing import Any, Mapping, Optional, Protocol
from uuid import uuid4

from sqlalchemy import bindparam, create_engine, text


CONTRACT_VERSION = "airank.operation-guard.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def idempotency_key_sha256(value: str) -> str:
    key = str(value or "").strip()
    if not 8 <= len(key) <= 160 or any(character.isspace() for character in key):
        raise OperationGuardError(
            "OPERATION_IDEMPOTENCY_KEY_INVALID",
            "idempotency key must contain 8-160 non-whitespace characters",
        )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class OperationGuardError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class OperationClaim:
    operation_id: str
    idempotent_replay: bool
    response: Optional[dict[str, object]] = None


@dataclass(frozen=True)
class OperationAuditEvent:
    event_sequence: int
    event_type: str
    from_state: Optional[str]
    to_state: str
    request_sha256: str
    previous_event_sha256: Optional[str]
    event_sha256: str
    actor: str
    trace_id: str
    created_at: datetime


@dataclass(frozen=True)
class OperationAuditRecord:
    operation_id: str
    tenant_id: str
    operation_type: str
    resource_key: str
    request_sha256: str
    request_key_id: Optional[str]
    state: str
    external_effect_started: bool
    response: Optional[dict[str, object]]
    error_code: Optional[str]
    created_by: str
    trace_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    events: tuple[OperationAuditEvent, ...] = ()


@dataclass
class _OperationRecord:
    operation_id: str
    tenant_id: str
    operation_type: str
    resource_key: str
    idempotency_key_sha256: str
    request_sha256: str
    request_key_id: Optional[str]
    state: str
    external_effect_started: bool
    response: Optional[dict[str, object]]
    error_code: Optional[str]
    created_by: str
    trace_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    latest_event_sha256: Optional[str] = None
    event_sequence: int = 0
    events: list[OperationAuditEvent] = field(default_factory=list)


class OperationGuard(Protocol):
    def request_key_id(
        self,
        tenant_id: str,
        operation_type: str,
        resource_key: str,
        idempotency_key: str,
    ) -> Optional[str]: ...

    def claim(
        self,
        *,
        tenant_id: str,
        operation_type: str,
        resource_key: str,
        idempotency_key: str,
        request_sha256: str,
        request_key_id: Optional[str],
        actor: str,
        trace_id: str,
    ) -> OperationClaim: ...

    def mark_external_started(self, operation_id: str, actor: str, trace_id: str) -> None: ...

    def succeed(
        self,
        operation_id: str,
        response: Mapping[str, object],
        actor: str,
        trace_id: str,
    ) -> None: ...

    def fail(self, operation_id: str, error_code: str, actor: str, trace_id: str) -> None: ...

    def list_audits(
        self,
        tenant_id: str,
        *,
        operation_types: tuple[str, ...],
        state: Optional[str] = None,
        limit: int = 50,
    ) -> list[OperationAuditRecord]: ...

    def get_audit(self, tenant_id: str, operation_id: str) -> Optional[OperationAuditRecord]: ...


class InMemoryOperationGuard:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, str], _OperationRecord] = {}
        self._by_id: dict[str, _OperationRecord] = {}
        self._lock = Lock()

    @staticmethod
    def _key(
        tenant_id: str,
        operation_type: str,
        resource_key: str,
        idempotency_key: str,
    ) -> tuple[str, str, str, str]:
        return (
            tenant_id,
            operation_type,
            resource_key,
            idempotency_key_sha256(idempotency_key),
        )

    def request_key_id(self, tenant_id: str, operation_type: str, resource_key: str, idempotency_key: str) -> Optional[str]:
        with self._lock:
            record = self._records.get(self._key(tenant_id, operation_type, resource_key, idempotency_key))
            return record.request_key_id if record else None

    def _event(self, record: _OperationRecord, event_type: str, from_state: Optional[str], to_state: str, actor: str, trace_id: str, now: datetime) -> None:
        record.event_sequence += 1
        previous = record.latest_event_sha256
        record.latest_event_sha256 = canonical_sha256(
            {
                "contract_version": CONTRACT_VERSION,
                "operation_id": record.operation_id,
                "event_sequence": record.event_sequence,
                "event_type": event_type,
                "from_state": from_state,
                "to_state": to_state,
                "request_sha256": record.request_sha256,
                "previous_event_sha256": previous,
                "actor": actor,
                "trace_id": trace_id,
                "created_at": now.isoformat(),
            }
        )
        record.events.append(
            OperationAuditEvent(
                event_sequence=record.event_sequence,
                event_type=event_type,
                from_state=from_state,
                to_state=to_state,
                request_sha256=record.request_sha256,
                previous_event_sha256=previous,
                event_sha256=record.latest_event_sha256,
                actor=actor,
                trace_id=trace_id,
                created_at=now,
            )
        )

    @staticmethod
    def _audit(record: _OperationRecord, *, include_events: bool) -> OperationAuditRecord:
        return OperationAuditRecord(
            operation_id=record.operation_id,
            tenant_id=record.tenant_id,
            operation_type=record.operation_type,
            resource_key=record.resource_key,
            request_sha256=record.request_sha256,
            request_key_id=record.request_key_id,
            state=record.state,
            external_effect_started=record.external_effect_started,
            response=dict(record.response) if record.response is not None else None,
            error_code=record.error_code,
            created_by=record.created_by,
            trace_id=record.trace_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
            events=tuple(record.events) if include_events else (),
        )

    @staticmethod
    def _replay(record: _OperationRecord) -> OperationClaim:
        if record.state == "succeeded" and record.response is not None:
            return OperationClaim(record.operation_id, True, dict(record.response))
        if record.state == "failed":
            raise OperationGuardError(
                record.error_code or "OPERATION_PREVIOUSLY_FAILED",
                "the original operation failed and will not be repeated",
            )
        if record.state == "claimed":
            raise OperationGuardError(
                "OPERATION_IN_PROGRESS",
                "an operation with this idempotency key is already in progress",
            )
        raise OperationGuardError(
            "OPERATION_OUTCOME_UNKNOWN",
            "the external effect may have started; automatic replay is forbidden",
        )

    def claim(self, *, tenant_id: str, operation_type: str, resource_key: str, idempotency_key: str, request_sha256: str, request_key_id: Optional[str], actor: str, trace_id: str) -> OperationClaim:
        key = self._key(tenant_id, operation_type, resource_key, idempotency_key)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.request_sha256 != request_sha256:
                    raise OperationGuardError(
                        "OPERATION_IDEMPOTENCY_CONFLICT",
                        "idempotency key was already used with a different request",
                    )
                return self._replay(existing)
            now = utc_now()
            record = _OperationRecord(
                operation_id=f"operation_guard_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                operation_type=operation_type,
                resource_key=resource_key,
                idempotency_key_sha256=key[3],
                request_sha256=request_sha256,
                request_key_id=request_key_id,
                state="claimed",
                external_effect_started=False,
                response=None,
                error_code=None,
                created_by=actor,
                trace_id=trace_id,
                created_at=now,
                updated_at=now,
            )
            self._event(record, "operation_claimed", None, "claimed", actor, trace_id, now)
            self._records[key] = record
            self._by_id[record.operation_id] = record
            return OperationClaim(record.operation_id, False)

    def mark_external_started(self, operation_id: str, actor: str, trace_id: str) -> None:
        with self._lock:
            record = self._by_id[operation_id]
            if record.state != "claimed":
                raise OperationGuardError("OPERATION_STATE_CONFLICT", "operation is not claimable")
            now = utc_now()
            self._event(record, "external_effect_started", record.state, "external_started", actor, trace_id, now)
            record.state = "external_started"
            record.external_effect_started = True
            record.updated_at = now

    def succeed(self, operation_id: str, response: Mapping[str, object], actor: str, trace_id: str) -> None:
        with self._lock:
            record = self._by_id[operation_id]
            if record.state not in {"claimed", "external_started"}:
                raise OperationGuardError("OPERATION_STATE_CONFLICT", "operation cannot succeed")
            now = utc_now()
            self._event(record, "operation_succeeded", record.state, "succeeded", actor, trace_id, now)
            record.state = "succeeded"
            record.response = dict(response)
            record.updated_at = now
            record.completed_at = now

    def fail(self, operation_id: str, error_code: str, actor: str, trace_id: str) -> None:
        with self._lock:
            record = self._by_id[operation_id]
            if record.state in {"succeeded", "failed"}:
                return
            now = utc_now()
            self._event(record, "operation_failed", record.state, "failed", actor, trace_id, now)
            record.state = "failed"
            record.error_code = error_code
            record.updated_at = now
            record.completed_at = now

    def list_audits(self, tenant_id: str, *, operation_types: tuple[str, ...], state: Optional[str] = None, limit: int = 50) -> list[OperationAuditRecord]:
        allowed = set(operation_types)
        with self._lock:
            records = [
                record
                for record in self._by_id.values()
                if record.tenant_id == tenant_id
                and record.operation_type in allowed
                and (state is None or record.state == state)
            ]
            records.sort(key=lambda item: (item.created_at, item.operation_id), reverse=True)
            return [self._audit(record, include_events=False) for record in records[:limit]]

    def get_audit(self, tenant_id: str, operation_id: str) -> Optional[OperationAuditRecord]:
        with self._lock:
            record = self._by_id.get(operation_id)
            if record is None or record.tenant_id != tenant_id:
                return None
            return self._audit(record, include_events=True)


class MySQLOperationGuard:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _row(conn: Any, tenant_id: str, operation_type: str, resource_key: str, key_sha256: str, *, for_update: bool = False) -> Optional[Mapping[str, Any]]:
        suffix = " FOR UPDATE" if for_update else ""
        return conn.execute(
            text(
                "SELECT * FROM airank_operation_guards WHERE tenant_id=:tenant_id "
                "AND operation_type=:operation_type AND resource_key=:resource_key "
                "AND idempotency_key_sha256=:key_sha256" + suffix
            ),
            {"tenant_id": tenant_id, "operation_type": operation_type, "resource_key": resource_key, "key_sha256": key_sha256},
        ).mappings().first()

    @staticmethod
    def _append_event(conn: Any, row: Mapping[str, Any], event_type: str, from_state: Optional[str], to_state: str, actor: str, trace_id: str, now: datetime) -> None:
        latest = conn.execute(
            text("SELECT event_sequence,event_sha256 FROM airank_operation_guard_events WHERE operation_id=:operation_id ORDER BY event_sequence DESC LIMIT 1 FOR UPDATE"),
            {"operation_id": row["id"]},
        ).mappings().first()
        sequence = int(latest["event_sequence"]) + 1 if latest else 1
        previous = str(latest["event_sha256"]) if latest else None
        event_id = f"operation_event_{uuid4().hex[:16]}"
        payload = {
            "contract_version": CONTRACT_VERSION,
            "event_id": event_id,
            "tenant_id": row["tenant_id"],
            "operation_id": row["id"],
            "event_sequence": sequence,
            "event_type": event_type,
            "from_state": from_state,
            "to_state": to_state,
            "request_sha256": row["request_sha256"],
            "previous_event_sha256": previous,
            "actor": actor,
            "trace_id": trace_id,
            "created_at": now.isoformat(),
        }
        digest = canonical_sha256(payload)
        conn.execute(
            text("INSERT INTO airank_operation_guard_events (id,tenant_id,operation_id,event_sequence,event_type,from_state,to_state,request_sha256,previous_event_sha256,event_sha256,actor,trace_id,created_at) VALUES (:id,:tenant_id,:operation_id,:event_sequence,:event_type,:from_state,:to_state,:request_sha256,:previous,:digest,:actor,:trace_id,:created_at)"),
            {"id": event_id, "tenant_id": row["tenant_id"], "operation_id": row["id"], "event_sequence": sequence, "event_type": event_type, "from_state": from_state, "to_state": to_state, "request_sha256": row["request_sha256"], "previous": previous, "digest": digest, "actor": actor, "trace_id": trace_id, "created_at": database_datetime(now)},
        )

    def request_key_id(self, tenant_id: str, operation_type: str, resource_key: str, idempotency_key: str) -> Optional[str]:
        key_sha = idempotency_key_sha256(idempotency_key)
        with self.engine.connect() as conn:
            row = self._row(conn, tenant_id, operation_type, resource_key, key_sha)
        return str(row["request_key_id"]) if row and row["request_key_id"] else None

    def claim(self, *, tenant_id: str, operation_type: str, resource_key: str, idempotency_key: str, request_sha256: str, request_key_id: Optional[str], actor: str, trace_id: str) -> OperationClaim:
        key_sha = idempotency_key_sha256(idempotency_key)
        operation_id = f"operation_guard_{uuid4().hex[:16]}"
        now = utc_now()
        with self.engine.begin() as conn:
            inserted = conn.execute(
                text("INSERT IGNORE INTO airank_operation_guards (id,tenant_id,operation_type,resource_key,idempotency_key_sha256,request_sha256,request_key_id,state,external_effect_started,created_by,trace_id,created_at,updated_at) VALUES (:id,:tenant_id,:operation_type,:resource_key,:key_sha,:request_sha,:request_key_id,'claimed',0,:actor,:trace_id,:now,:now)"),
                {"id": operation_id, "tenant_id": tenant_id, "operation_type": operation_type, "resource_key": resource_key, "key_sha": key_sha, "request_sha": request_sha256, "request_key_id": request_key_id, "actor": actor, "trace_id": trace_id, "now": database_datetime(now)},
            ).rowcount == 1
            row = self._row(conn, tenant_id, operation_type, resource_key, key_sha, for_update=True)
            assert row is not None
            if str(row["request_sha256"]) != request_sha256:
                raise OperationGuardError("OPERATION_IDEMPOTENCY_CONFLICT", "idempotency key was already used with a different request")
            if inserted:
                self._append_event(conn, row, "operation_claimed", None, "claimed", actor, trace_id, now)
                return OperationClaim(str(row["id"]), False)
            state = str(row["state"])
            if state == "succeeded" and row["response_json"] is not None:
                response = row["response_json"]
                if isinstance(response, str):
                    response = json.loads(response)
                return OperationClaim(str(row["id"]), True, dict(response))
            if state == "failed":
                raise OperationGuardError(str(row["error_code"] or "OPERATION_PREVIOUSLY_FAILED"), "the original operation failed and will not be repeated")
            if state == "claimed":
                raise OperationGuardError("OPERATION_IN_PROGRESS", "an operation with this idempotency key is already in progress")
            raise OperationGuardError("OPERATION_OUTCOME_UNKNOWN", "the external effect may have started; automatic replay is forbidden")

    def _transition(self, operation_id: str, *, allowed: set[str], to_state: str, event_type: str, actor: str, trace_id: str, response: Optional[Mapping[str, object]] = None, error_code: Optional[str] = None, external_started: Optional[bool] = None) -> None:
        now = utc_now()
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM airank_operation_guards WHERE id=:id FOR UPDATE"), {"id": operation_id}).mappings().one()
            current = str(row["state"])
            if current not in allowed:
                if current == to_state:
                    return
                raise OperationGuardError("OPERATION_STATE_CONFLICT", "operation state transition is invalid")
            conn.execute(
                text("UPDATE airank_operation_guards SET state=:state,external_effect_started=COALESCE(:external_started,external_effect_started),response_json=:response_json,error_code=:error_code,updated_at=:now,completed_at=:completed_at WHERE id=:id"),
                {"state": to_state, "external_started": int(external_started) if external_started is not None else None, "response_json": canonical_json(response) if response is not None else None, "error_code": error_code, "now": database_datetime(now), "completed_at": database_datetime(now) if to_state in {"succeeded", "failed"} else None, "id": operation_id},
            )
            self._append_event(conn, row, event_type, current, to_state, actor, trace_id, now)

    def mark_external_started(self, operation_id: str, actor: str, trace_id: str) -> None:
        self._transition(operation_id, allowed={"claimed"}, to_state="external_started", event_type="external_effect_started", actor=actor, trace_id=trace_id, external_started=True)

    def succeed(self, operation_id: str, response: Mapping[str, object], actor: str, trace_id: str) -> None:
        self._transition(operation_id, allowed={"claimed", "external_started"}, to_state="succeeded", event_type="operation_succeeded", actor=actor, trace_id=trace_id, response=response)

    def fail(self, operation_id: str, error_code: str, actor: str, trace_id: str) -> None:
        self._transition(operation_id, allowed={"claimed", "external_started"}, to_state="failed", event_type="operation_failed", actor=actor, trace_id=trace_id, error_code=error_code)

    @staticmethod
    def _audit_record(row: Mapping[str, Any], events: tuple[OperationAuditEvent, ...] = ()) -> OperationAuditRecord:
        response = row["response_json"]
        if isinstance(response, str):
            response = json.loads(response)
        return OperationAuditRecord(
            operation_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            operation_type=str(row["operation_type"]),
            resource_key=str(row["resource_key"]),
            request_sha256=str(row["request_sha256"]),
            request_key_id=str(row["request_key_id"]) if row["request_key_id"] else None,
            state=str(row["state"]),
            external_effect_started=bool(row["external_effect_started"]),
            response=dict(response) if response is not None else None,
            error_code=str(row["error_code"]) if row["error_code"] else None,
            created_by=str(row["created_by"]),
            trace_id=str(row["trace_id"]),
            created_at=utc_datetime(row["created_at"]),
            updated_at=utc_datetime(row["updated_at"]),
            completed_at=utc_datetime(row["completed_at"]) if row["completed_at"] else None,
            events=events,
        )

    def list_audits(self, tenant_id: str, *, operation_types: tuple[str, ...], state: Optional[str] = None, limit: int = 50) -> list[OperationAuditRecord]:
        if not operation_types:
            return []
        clauses = ["tenant_id=:tenant_id", "operation_type IN :operation_types"]
        parameters: dict[str, object] = {
            "tenant_id": tenant_id,
            "operation_types": operation_types,
            "limit": max(1, min(int(limit), 100)),
        }
        if state is not None:
            clauses.append("state=:state")
            parameters["state"] = state
        statement = text(
            "SELECT * FROM airank_operation_guards WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC,id DESC LIMIT :limit"
        ).bindparams(bindparam("operation_types", expanding=True))
        with self.engine.connect() as conn:
            rows = conn.execute(statement, parameters).mappings().all()
        return [self._audit_record(row) for row in rows]

    def get_audit(self, tenant_id: str, operation_id: str) -> Optional[OperationAuditRecord]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM airank_operation_guards WHERE tenant_id=:tenant_id AND id=:operation_id"),
                {"tenant_id": tenant_id, "operation_id": operation_id},
            ).mappings().first()
            if row is None:
                return None
            event_rows = conn.execute(
                text(
                    "SELECT * FROM airank_operation_guard_events "
                    "WHERE tenant_id=:tenant_id AND operation_id=:operation_id "
                    "ORDER BY event_sequence"
                ),
                {"tenant_id": tenant_id, "operation_id": operation_id},
            ).mappings().all()
        events = tuple(
            OperationAuditEvent(
                event_sequence=int(event["event_sequence"]),
                event_type=str(event["event_type"]),
                from_state=str(event["from_state"]) if event["from_state"] else None,
                to_state=str(event["to_state"]),
                request_sha256=str(event["request_sha256"]),
                previous_event_sha256=str(event["previous_event_sha256"]) if event["previous_event_sha256"] else None,
                event_sha256=str(event["event_sha256"]),
                actor=str(event["actor"]),
                trace_id=str(event["trace_id"]),
                created_at=utc_datetime(event["created_at"]),
            )
            for event in event_rows
        )
        return self._audit_record(row, events)

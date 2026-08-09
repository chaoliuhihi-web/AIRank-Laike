from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from threading import Lock
from typing import Any, Literal, Mapping, Optional, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_evidence import ObjectStorageError, build_object_storage_from_env, sha256_bytes

try:
    from .delivery_routes import require_delivery_admin, response_meta, trusted_actor
    from .operation_guard import (
        MySQLOperationGuard,
        OperationGuardError,
        canonical_json,
        canonical_sha256,
        database_datetime,
        idempotency_key_sha256,
        utc_datetime,
    )
except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
    from delivery_routes import require_delivery_admin, response_meta, trusted_actor  # type: ignore[no-redef]
    from operation_guard import (  # type: ignore[no-redef]
        MySQLOperationGuard,
        OperationGuardError,
        canonical_json,
        canonical_sha256,
        database_datetime,
        idempotency_key_sha256,
        utc_datetime,
    )


TRACE_HEADER = "X-AIRank-Trace-Id"
CONTRACT_VERSION = "airank.publication-reconciliation.v1"
METHOD = "two_person_manual_evidence"
router = APIRouter(prefix="/api/v1", tags=["publication-reconciliation"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _http_error(status: int, code: str, details: Optional[dict[str, Any]] = None) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=status, detail={"code": code, "details": details or {}})


class PublicationReconciliationSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_outcome: Literal["succeeded"] = "succeeded"
    published_url: str = Field(min_length=1, max_length=2048)
    external_receipt_id: str = Field(min_length=1, max_length=255)
    response_status: int = Field(ge=200, le=299)
    evidence_object_ref_id: str = Field(min_length=1, max_length=64)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_note: str = Field(min_length=20, max_length=2000)
    observed_at: datetime
    submitted_by: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @field_validator("published_url")
    @classmethod
    def published_url_is_absolute_http(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("published_url must be an absolute http(s) URL without embedded credentials")
        return value

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        if value.astimezone(timezone.utc) > utc_now():
            raise ValueError("observed_at cannot be in the future")
        return value.astimezone(timezone.utc)


class PublicationReconciliationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approved", "rejected"]
    reviewed_by: str = Field(min_length=1, max_length=128)
    review_note: str = Field(min_length=10, max_length=2000)
    evidence_object_ref_id: str = Field(min_length=1, max_length=64)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=160)


class PublicationReconciliationEventData(BaseModel):
    event_sequence: int
    event_type: str
    from_status: Optional[str] = None
    to_status: Literal["awaiting_review", "approved", "rejected", "applied"]
    request_sha256: str
    evidence_sha256: str
    previous_event_sha256: Optional[str] = None
    event_sha256: str
    actor: str
    trace_id: str
    created_at: datetime


class PublicationReconciliationData(BaseModel):
    contract_version: Literal["airank.publication-reconciliation.v1"] = CONTRACT_VERSION
    case_id: str
    tenant_id: str
    project_id: str
    package_id: str
    attempt_id: str
    operation_id: str
    proposed_outcome: Literal["succeeded"]
    status: Literal["awaiting_review", "approved", "rejected", "applied"]
    reconciliation_method: Literal["two_person_manual_evidence"] = METHOD
    external_delivery_verified: Literal[False] = False
    published_url: str
    external_receipt_id: str
    response_status: int
    evidence_object_ref_id: str
    evidence_sha256: str
    evidence_note: str
    observed_at: datetime
    submitted_by: str
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    request_sha256: str
    receipt_sha256: Optional[str] = None
    latest_event_sha256: str
    event_sequence: int
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    events: list[PublicationReconciliationEventData] = Field(default_factory=list)
    idempotent_replay: bool = False


class PublicationReconciliationResponse(BaseModel):
    data: PublicationReconciliationData
    meta: dict[str, str]


class PublicationReconciliationListResponse(BaseModel):
    data: list[PublicationReconciliationData]
    meta: dict[str, str]


class PublicationReconciliationRepository(Protocol):
    def submit(
        self,
        tenant_id: str,
        package_id: str,
        payload: PublicationReconciliationSubmitRequest,
        trace_id: str,
    ) -> PublicationReconciliationData: ...

    def review(
        self,
        tenant_id: str,
        case_id: str,
        payload: PublicationReconciliationReviewRequest,
        trace_id: str,
    ) -> PublicationReconciliationData: ...

    def list_project(self, tenant_id: str, project_id: str) -> list[PublicationReconciliationData]: ...

    def get(self, tenant_id: str, case_id: str) -> PublicationReconciliationData: ...


class InMemoryPublicationReconciliationRepository:
    """Contract-test repository. Production reconciliation always uses MySQL."""

    def __init__(self) -> None:
        self.cases: dict[tuple[str, str], PublicationReconciliationData] = {}
        self.outcome_unknown: dict[tuple[str, str], dict[str, str]] = {}
        self.evidence_objects: dict[tuple[str, str], tuple[str, str]] = {}
        self._request_keys: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._review_keys: dict[tuple[str, str], tuple[str, str]] = {}
        self._lock = Lock()

    def register_outcome_unknown(
        self,
        tenant_id: str,
        project_id: str,
        package_id: str,
        attempt_id: str,
        operation_id: str,
        *,
        channel: str = "http",
    ) -> None:
        self.outcome_unknown[(tenant_id, package_id)] = {
            "project_id": project_id,
            "attempt_id": attempt_id,
            "operation_id": operation_id,
            "channel": channel,
        }

    def register_evidence_object(self, tenant_id: str, project_id: str, object_ref_id: str, sha256: str) -> None:
        self.evidence_objects[(tenant_id, object_ref_id)] = (project_id, sha256)

    @staticmethod
    def _request_hash(package_id: str, payload: PublicationReconciliationSubmitRequest) -> str:
        return canonical_sha256({"package_id": package_id, **payload.model_dump(exclude={"idempotency_key"}, mode="json")})

    @staticmethod
    def _event(case: PublicationReconciliationData, event_type: str, from_status: Optional[str], to_status: str, actor: str, trace_id: str, at: datetime) -> PublicationReconciliationData:
        sequence = case.event_sequence + 1
        event_payload = {
            "contract_version": CONTRACT_VERSION,
            "case_id": case.case_id,
            "event_sequence": sequence,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "request_sha256": case.request_sha256,
            "evidence_sha256": case.evidence_sha256,
            "previous_event_sha256": case.latest_event_sha256 or None,
            "actor": actor,
            "trace_id": trace_id,
            "created_at": at.isoformat(),
        }
        event_sha256 = canonical_sha256(event_payload)
        event = PublicationReconciliationEventData(
            **event_payload,
            event_sha256=event_sha256,
        )
        return case.model_copy(update={
            "status": to_status,
            "event_sequence": sequence,
            "latest_event_sha256": event_sha256,
            "events": [*case.events, event],
        })

    def submit(self, tenant_id: str, package_id: str, payload: PublicationReconciliationSubmitRequest, trace_id: str) -> PublicationReconciliationData:
        request_hash = self._request_hash(package_id, payload)
        key_hash = idempotency_key_sha256(payload.idempotency_key)
        replay_key = (tenant_id, package_id, key_hash)
        with self._lock:
            prior = self._request_keys.get(replay_key)
            if prior:
                if prior[1] != request_hash:
                    raise _http_error(409, "PUBLISH_RECONCILIATION_IDEMPOTENCY_CONFLICT")
                return self.cases[(tenant_id, prior[0])].model_copy(update={"idempotent_replay": True})
            pending = self.outcome_unknown.get((tenant_id, package_id))
            if pending is None:
                raise _http_error(409, "PUBLISH_RECONCILIATION_NOT_REQUIRED", {"package_id": package_id})
            evidence = self.evidence_objects.get((tenant_id, payload.evidence_object_ref_id))
            if evidence != (pending["project_id"], payload.evidence_sha256):
                raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID")
            if any(item.package_id == package_id and item.status == "awaiting_review" for item in self.cases.values()):
                raise _http_error(409, "PUBLISH_RECONCILIATION_ACTIVE_CASE")
            if pending["channel"] == "wordpress" and not payload.external_receipt_id.isdigit():
                raise _http_error(409, "PUBLISH_MUTATION_REMOTE_ID_INVALID")
            now = utc_now()
            case = PublicationReconciliationData(
                case_id=f"publish_recon_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                project_id=pending["project_id"],
                package_id=package_id,
                attempt_id=pending["attempt_id"],
                operation_id=pending["operation_id"],
                proposed_outcome="succeeded",
                status="awaiting_review",
                published_url=payload.published_url,
                external_receipt_id=payload.external_receipt_id,
                response_status=payload.response_status,
                evidence_object_ref_id=payload.evidence_object_ref_id,
                evidence_sha256=payload.evidence_sha256,
                evidence_note=payload.evidence_note,
                observed_at=payload.observed_at,
                submitted_by=payload.submitted_by,
                request_sha256=request_hash,
                latest_event_sha256="",
                event_sequence=0,
                submitted_at=now,
            )
            case = self._event(case, "reconciliation_submitted", None, "awaiting_review", payload.submitted_by, trace_id, now)
            self.cases[(tenant_id, case.case_id)] = case
            self._request_keys[replay_key] = (case.case_id, request_hash)
            return case

    def review(self, tenant_id: str, case_id: str, payload: PublicationReconciliationReviewRequest, trace_id: str) -> PublicationReconciliationData:
        with self._lock:
            case = self.cases.get((tenant_id, case_id))
            if case is None:
                raise _http_error(404, "PUBLISH_RECONCILIATION_NOT_FOUND", {"case_id": case_id})
            review_key = idempotency_key_sha256(payload.idempotency_key)
            review_hash = canonical_sha256({"case_id": case_id, **payload.model_dump(exclude={"idempotency_key"}, mode="json")})
            prior_review = self._review_keys.get((tenant_id, case_id))
            if prior_review is not None:
                if prior_review != (review_key, review_hash):
                    raise _http_error(409, "PUBLISH_RECONCILIATION_REVIEW_CONFLICT")
                return case.model_copy(update={"idempotent_replay": True})
            if payload.reviewed_by == case.submitted_by:
                raise _http_error(409, "PUBLISH_RECONCILIATION_SECOND_PERSON_REQUIRED")
            if case.status != "awaiting_review":
                raise _http_error(409, "PUBLISH_RECONCILIATION_STATE_CONFLICT", {"status": case.status})
            if payload.evidence_object_ref_id != case.evidence_object_ref_id or payload.evidence_sha256 != case.evidence_sha256:
                raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID", {"reason": "reviewed_evidence_mismatch"})
            now = utc_now()
            if payload.action == "rejected":
                updated = self._event(case, "reconciliation_rejected", case.status, "rejected", payload.reviewed_by, trace_id, now)
            else:
                approved = self._event(case, "reconciliation_approved", case.status, "approved", payload.reviewed_by, trace_id, now)
                receipt_sha256 = canonical_sha256(_manual_attestation(approved, payload.reviewed_by))
                updated = self._event(approved, "reconciliation_applied", "approved", "applied", payload.reviewed_by, trace_id, now).model_copy(update={"receipt_sha256": receipt_sha256, "applied_at": now})
            updated = updated.model_copy(update={"reviewed_by": payload.reviewed_by, "review_note": payload.review_note, "reviewed_at": now})
            self.cases[(tenant_id, case_id)] = updated
            self._review_keys[(tenant_id, case_id)] = (review_key, review_hash)
            return updated

    def list_project(self, tenant_id: str, project_id: str) -> list[PublicationReconciliationData]:
        return sorted(
            [item for (item_tenant, _), item in self.cases.items() if item_tenant == tenant_id and item.project_id == project_id],
            key=lambda item: (item.submitted_at, item.case_id),
            reverse=True,
        )

    def get(self, tenant_id: str, case_id: str) -> PublicationReconciliationData:
        case = self.cases.get((tenant_id, case_id))
        if case is None:
            raise _http_error(404, "PUBLISH_RECONCILIATION_NOT_FOUND", {"case_id": case_id})
        return case


def _manual_attestation(case: PublicationReconciliationData, reviewed_by: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "reconciliation_case_id": case.case_id,
        "reconciliation_method": METHOD,
        "external_delivery_verified": False,
        "observed_outcome": "succeeded",
        "tenant_id": case.tenant_id,
        "project_id": case.project_id,
        "package_id": case.package_id,
        "attempt_id": case.attempt_id,
        "operation_id": case.operation_id,
        "published_url": case.published_url,
        "external_receipt_id": case.external_receipt_id,
        "response_status": case.response_status,
        "evidence_object_ref_id": case.evidence_object_ref_id,
        "evidence_sha256": case.evidence_sha256,
        "observed_at": case.observed_at.isoformat(),
        "submitted_by": case.submitted_by,
        "reviewed_by": reviewed_by,
        "request_sha256": case.request_sha256,
    }


class MySQLPublicationReconciliationRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.operation_guard = MySQLOperationGuard(database_url)

    def _verify_object_bytes(self, tenant_id: str, object_ref_id: str, expected_sha256: str) -> None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT sha256,byte_size,metadata_json FROM airank_object_refs WHERE tenant_id=:tenant_id AND id=:object_ref_id"),
                {"tenant_id": tenant_id, "object_ref_id": object_ref_id},
            ).mappings().first()
        if row is None or str(row["sha256"] or "") != expected_sha256:
            raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID", {"reason": "object_or_hash_mismatch"})
        metadata = _json_object(row["metadata_json"])
        if metadata.get("immutable") is not True:
            raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID", {"reason": "object_not_immutable"})
        object_key = str(metadata.get("object_key") or "")
        storage_driver = str(metadata.get("storage_driver") or "")
        if not object_key or not storage_driver:
            raise _http_error(503, "PUBLISH_RECONCILIATION_EVIDENCE_UNAVAILABLE", {"reason": "storage_metadata_missing"})
        try:
            storage = build_object_storage_from_env()
            if storage.driver != storage_driver:
                raise ObjectStorageError("configured storage driver does not match evidence record")
            payload = storage.get_bytes(object_key)
        except ObjectStorageError as exc:
            raise _http_error(503, "PUBLISH_RECONCILIATION_EVIDENCE_UNAVAILABLE") from exc
        if sha256_bytes(payload) != expected_sha256 or (row["byte_size"] is not None and len(payload) != int(row["byte_size"])):
            raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID", {"reason": "stored_bytes_integrity_failed"})

    @staticmethod
    def _request_hash(package_id: str, payload: PublicationReconciliationSubmitRequest) -> str:
        return canonical_sha256({"package_id": package_id, **payload.model_dump(exclude={"idempotency_key"}, mode="json")})

    @staticmethod
    def _append_event(
        conn: Any,
        row: Mapping[str, Any],
        *,
        event_type: str,
        from_status: Optional[str],
        to_status: str,
        actor: str,
        trace_id: str,
        now: datetime,
    ) -> str:
        latest = conn.execute(
            text("SELECT event_sequence,event_sha256 FROM airank_publish_reconciliation_events WHERE case_id=:case_id ORDER BY event_sequence DESC LIMIT 1 FOR UPDATE"),
            {"case_id": row["id"]},
        ).mappings().first()
        sequence = int(latest["event_sequence"]) + 1 if latest else 1
        previous = str(latest["event_sha256"]) if latest else None
        event_id = f"publish_recon_event_{uuid4().hex[:16]}"
        event_payload = {
            "contract_version": CONTRACT_VERSION,
            "event_id": event_id,
            "tenant_id": row["tenant_id"],
            "case_id": row["id"],
            "event_sequence": sequence,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "request_sha256": row["request_sha256"],
            "evidence_sha256": row["evidence_sha256"],
            "previous_event_sha256": previous,
            "actor": actor,
            "trace_id": trace_id,
            "created_at": now.isoformat(),
        }
        digest = canonical_sha256(event_payload)
        conn.execute(
            text("""
                INSERT INTO airank_publish_reconciliation_events (
                  id,tenant_id,case_id,event_sequence,event_type,from_status,to_status,
                  request_sha256,evidence_sha256,previous_event_sha256,event_sha256,
                  actor,trace_id,created_at
                ) VALUES (
                  :id,:tenant_id,:case_id,:event_sequence,:event_type,:from_status,:to_status,
                  :request_sha256,:evidence_sha256,:previous_event_sha256,:event_sha256,
                  :actor,:trace_id,:created_at
                )
            """),
            {
                **event_payload,
                "id": event_id,
                "event_sha256": digest,
                "created_at": database_datetime(now),
            },
        )
        conn.execute(
            text("UPDATE airank_publish_reconciliation_cases SET latest_event_sha256=:digest,event_sequence=:sequence,updated_at=:now WHERE id=:case_id"),
            {"digest": digest, "sequence": sequence, "now": database_datetime(now), "case_id": row["id"]},
        )
        return digest

    def _case_data(self, conn: Any, row: Mapping[str, Any], *, replay: bool = False, include_events: bool = False) -> PublicationReconciliationData:
        events: list[PublicationReconciliationEventData] = []
        if include_events:
            event_rows = conn.execute(
                text("SELECT * FROM airank_publish_reconciliation_events WHERE tenant_id=:tenant_id AND case_id=:case_id ORDER BY event_sequence ASC"),
                {"tenant_id": row["tenant_id"], "case_id": row["id"]},
            ).mappings().all()
            events = [
                PublicationReconciliationEventData(
                    event_sequence=int(event["event_sequence"]),
                    event_type=str(event["event_type"]),
                    from_status=str(event["from_status"]) if event["from_status"] else None,
                    to_status=str(event["to_status"]),
                    request_sha256=str(event["request_sha256"]),
                    evidence_sha256=str(event["evidence_sha256"]),
                    previous_event_sha256=str(event["previous_event_sha256"]) if event["previous_event_sha256"] else None,
                    event_sha256=str(event["event_sha256"]),
                    actor=str(event["actor"]),
                    trace_id=str(event["trace_id"]),
                    created_at=utc_datetime(event["created_at"]),
                )
                for event in event_rows
            ]
        return PublicationReconciliationData(
            case_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            package_id=str(row["package_id"]),
            attempt_id=str(row["attempt_id"]),
            operation_id=str(row["operation_id"]),
            proposed_outcome=str(row["proposed_outcome"]),
            status=str(row["status"]),
            published_url=str(row["published_url"]),
            external_receipt_id=str(row["external_receipt_id"]),
            response_status=int(row["response_status"]),
            evidence_object_ref_id=str(row["evidence_object_ref_id"]),
            evidence_sha256=str(row["evidence_sha256"]),
            evidence_note=str(row["evidence_note"]),
            observed_at=utc_datetime(row["observed_at"]),
            submitted_by=str(row["submitted_by"]),
            reviewed_by=str(row["reviewed_by"]) if row["reviewed_by"] else None,
            review_note=str(row["review_note"]) if row["review_note"] else None,
            request_sha256=str(row["request_sha256"]),
            receipt_sha256=str(row["receipt_sha256"]) if row["receipt_sha256"] else None,
            latest_event_sha256=str(row["latest_event_sha256"] or ""),
            event_sequence=int(row["event_sequence"]),
            submitted_at=utc_datetime(row["submitted_at"]),
            reviewed_at=utc_datetime(row["reviewed_at"]) if row["reviewed_at"] else None,
            applied_at=utc_datetime(row["applied_at"]) if row["applied_at"] else None,
            events=events,
            idempotent_replay=replay,
        )

    def submit(self, tenant_id: str, package_id: str, payload: PublicationReconciliationSubmitRequest, trace_id: str) -> PublicationReconciliationData:
        self._verify_object_bytes(tenant_id, payload.evidence_object_ref_id, payload.evidence_sha256)
        submitted_at = utc_now()
        key_sha256 = idempotency_key_sha256(payload.idempotency_key)
        request_sha256 = self._request_hash(package_id, payload)
        case_id = f"publish_recon_{uuid4().hex[:16]}"
        with self.engine.begin() as conn:
            replay = conn.execute(
                text("SELECT * FROM airank_publish_reconciliation_cases WHERE tenant_id=:tenant_id AND package_id=:package_id AND idempotency_key_sha256=:key_sha256 FOR UPDATE"),
                {"tenant_id": tenant_id, "package_id": package_id, "key_sha256": key_sha256},
            ).mappings().first()
            if replay is not None:
                if str(replay["request_sha256"]) != request_sha256:
                    raise _http_error(409, "PUBLISH_RECONCILIATION_IDEMPOTENCY_CONFLICT")
                return self._case_data(conn, replay, replay=True, include_events=True)
            package = conn.execute(
                text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND id=:package_id AND deleted_at IS NULL FOR UPDATE"),
                {"tenant_id": tenant_id, "package_id": package_id},
            ).mappings().first()
            if package is None:
                raise _http_error(404, "PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
            if package["status"] != "outcome_unknown" or package["channel"] not in {"wordpress", "http"}:
                raise _http_error(409, "PUBLISH_RECONCILIATION_NOT_REQUIRED", {"package_id": package_id, "status": package["status"]})
            active = conn.execute(
                text("SELECT id FROM airank_publish_reconciliation_cases WHERE tenant_id=:tenant_id AND package_id=:package_id AND status IN ('awaiting_review','approved') ORDER BY submitted_at DESC LIMIT 1 FOR UPDATE"),
                {"tenant_id": tenant_id, "package_id": package_id},
            ).first()
            if active is not None:
                raise _http_error(409, "PUBLISH_RECONCILIATION_ACTIVE_CASE", {"case_id": active[0]})
            attempt = conn.execute(
                text("SELECT * FROM airank_publish_attempts WHERE tenant_id=:tenant_id AND package_id=:package_id AND status='outcome_unknown' ORDER BY attempt_number DESC LIMIT 1 FOR UPDATE"),
                {"tenant_id": tenant_id, "package_id": package_id},
            ).mappings().first()
            if attempt is None or not attempt["operation_id"]:
                raise _http_error(409, "PUBLISH_RECONCILIATION_OPERATION_INVALID", {"reason": "outcome_unknown_attempt_missing"})
            operation = conn.execute(
                text("SELECT * FROM airank_operation_guards WHERE tenant_id=:tenant_id AND id=:operation_id FOR UPDATE"),
                {"tenant_id": tenant_id, "operation_id": attempt["operation_id"]},
            ).mappings().first()
            if operation is None or operation["state"] != "external_started" or not operation["external_effect_started"] or operation["operation_type"] != "publisher.publish" or operation["resource_key"] != package_id or operation["request_sha256"] != attempt["request_sha256"]:
                raise _http_error(409, "PUBLISH_RECONCILIATION_OPERATION_INVALID", {"reason": "operation_scope_or_state_mismatch"})
            evidence = conn.execute(
                text("SELECT project_id,sha256,metadata_json FROM airank_object_refs WHERE tenant_id=:tenant_id AND id=:object_ref_id FOR UPDATE"),
                {"tenant_id": tenant_id, "object_ref_id": payload.evidence_object_ref_id},
            ).mappings().first()
            if evidence is None or evidence["project_id"] != package["project_id"] or str(evidence["sha256"] or "") != payload.evidence_sha256 or _json_object(evidence["metadata_json"]).get("immutable") is not True:
                raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID", {"reason": "tenant_project_hash_or_immutability_mismatch"})
            if package["channel"] == "wordpress" and not payload.external_receipt_id.isdigit():
                raise _http_error(409, "PUBLISH_MUTATION_REMOTE_ID_INVALID", {"remote_id": payload.external_receipt_id})
            conn.execute(
                text("""
                    INSERT INTO airank_publish_reconciliation_cases (
                      id,tenant_id,project_id,package_id,attempt_id,operation_id,
                      proposed_outcome,status,published_url,external_receipt_id,response_status,
                      evidence_object_ref_id,evidence_sha256,evidence_note,observed_at,
                      submitted_by,idempotency_key_sha256,request_sha256,
                      submitted_at,updated_at
                    ) VALUES (
                      :id,:tenant_id,:project_id,:package_id,:attempt_id,:operation_id,
                      'succeeded','awaiting_review',:published_url,:external_receipt_id,:response_status,
                      :evidence_object_ref_id,:evidence_sha256,:evidence_note,:observed_at,
                      :submitted_by,:idempotency_key_sha256,:request_sha256,
                      :submitted_at,:submitted_at
                    )
                """),
                {
                    "id": case_id,
                    "tenant_id": tenant_id,
                    "project_id": package["project_id"],
                    "package_id": package_id,
                    "attempt_id": attempt["id"],
                    "operation_id": operation["id"],
                    "published_url": payload.published_url,
                    "external_receipt_id": payload.external_receipt_id,
                    "response_status": payload.response_status,
                    "evidence_object_ref_id": payload.evidence_object_ref_id,
                    "evidence_sha256": payload.evidence_sha256,
                    "evidence_note": payload.evidence_note,
                    "observed_at": database_datetime(payload.observed_at),
                    "submitted_by": payload.submitted_by,
                    "idempotency_key_sha256": key_sha256,
                    "request_sha256": request_sha256,
                    "submitted_at": database_datetime(submitted_at),
                },
            )
            row = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE id=:case_id FOR UPDATE"), {"case_id": case_id}).mappings().one()
            self._append_event(conn, row, event_type="reconciliation_submitted", from_status=None, to_status="awaiting_review", actor=payload.submitted_by, trace_id=trace_id, now=submitted_at)
            updated = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE id=:case_id"), {"case_id": case_id}).mappings().one()
            return self._case_data(conn, updated, include_events=True)

    def review(self, tenant_id: str, case_id: str, payload: PublicationReconciliationReviewRequest, trace_id: str) -> PublicationReconciliationData:
        with self.engine.connect() as preliminary_conn:
            preliminary = preliminary_conn.execute(
                text("SELECT package_id,evidence_object_ref_id,evidence_sha256 FROM airank_publish_reconciliation_cases WHERE tenant_id=:tenant_id AND id=:case_id"),
                {"tenant_id": tenant_id, "case_id": case_id},
            ).mappings().first()
        if preliminary is None:
            raise _http_error(404, "PUBLISH_RECONCILIATION_NOT_FOUND", {"case_id": case_id})
        if payload.action == "approved":
            self._verify_object_bytes(
                tenant_id,
                str(preliminary["evidence_object_ref_id"]),
                str(preliminary["evidence_sha256"]),
            )
        reviewed_at = utc_now()
        review_key_sha256 = idempotency_key_sha256(payload.idempotency_key)
        review_request_sha256 = canonical_sha256({"case_id": case_id, **payload.model_dump(exclude={"idempotency_key"}, mode="json")})
        with self.engine.begin() as conn:
            package = conn.execute(
                text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND id=:package_id AND deleted_at IS NULL FOR UPDATE"),
                {"tenant_id": tenant_id, "package_id": preliminary["package_id"]},
            ).mappings().first()
            if package is None:
                raise _http_error(404, "PUBLISH_PACKAGE_NOT_FOUND", {"package_id": preliminary["package_id"]})
            row = conn.execute(
                text("SELECT * FROM airank_publish_reconciliation_cases WHERE tenant_id=:tenant_id AND id=:case_id FOR UPDATE"),
                {"tenant_id": tenant_id, "case_id": case_id},
            ).mappings().first()
            if row is None:
                raise _http_error(404, "PUBLISH_RECONCILIATION_NOT_FOUND", {"case_id": case_id})
            if row["package_id"] != package["id"]:
                raise _http_error(409, "PUBLISH_RECONCILIATION_OPERATION_INVALID", {"reason": "case_package_changed"})
            if row["review_idempotency_key_sha256"]:
                if row["review_idempotency_key_sha256"] != review_key_sha256 or row["review_request_sha256"] != review_request_sha256:
                    raise _http_error(409, "PUBLISH_RECONCILIATION_REVIEW_CONFLICT")
                return self._case_data(conn, row, replay=True, include_events=True)
            if row["status"] != "awaiting_review":
                raise _http_error(409, "PUBLISH_RECONCILIATION_STATE_CONFLICT", {"status": row["status"]})
            if payload.reviewed_by == row["submitted_by"]:
                raise _http_error(409, "PUBLISH_RECONCILIATION_SECOND_PERSON_REQUIRED")
            if payload.evidence_object_ref_id != row["evidence_object_ref_id"] or payload.evidence_sha256 != row["evidence_sha256"]:
                raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID", {"reason": "reviewed_evidence_mismatch"})
            if payload.action == "rejected":
                conn.execute(
                    text("UPDATE airank_publish_reconciliation_cases SET status='rejected',reviewed_by=:reviewed_by,review_note=:review_note,review_idempotency_key_sha256=:key_sha,review_request_sha256=:request_sha,reviewed_at=:reviewed_at,updated_at=:reviewed_at WHERE id=:case_id"),
                    {"reviewed_by": payload.reviewed_by, "review_note": payload.review_note, "key_sha": review_key_sha256, "request_sha": review_request_sha256, "reviewed_at": database_datetime(reviewed_at), "case_id": case_id},
                )
                self._append_event(conn, row, event_type="reconciliation_rejected", from_status="awaiting_review", to_status="rejected", actor=payload.reviewed_by, trace_id=trace_id, now=reviewed_at)
                updated = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE id=:case_id"), {"case_id": case_id}).mappings().one()
                return self._case_data(conn, updated, include_events=True)

            attempt = conn.execute(text("SELECT * FROM airank_publish_attempts WHERE tenant_id=:tenant_id AND id=:attempt_id FOR UPDATE"), {"tenant_id": tenant_id, "attempt_id": row["attempt_id"]}).mappings().one()
            operation = conn.execute(text("SELECT * FROM airank_operation_guards WHERE tenant_id=:tenant_id AND id=:operation_id FOR UPDATE"), {"tenant_id": tenant_id, "operation_id": row["operation_id"]}).mappings().one()
            evidence = conn.execute(text("SELECT project_id,sha256,metadata_json FROM airank_object_refs WHERE tenant_id=:tenant_id AND id=:object_ref_id FOR UPDATE"), {"tenant_id": tenant_id, "object_ref_id": row["evidence_object_ref_id"]}).mappings().one()
            if package["status"] != "outcome_unknown" or attempt["status"] != "outcome_unknown" or attempt["operation_id"] != operation["id"] or operation["state"] != "external_started" or not operation["external_effect_started"] or operation["resource_key"] != package["id"] or operation["request_sha256"] != attempt["request_sha256"]:
                raise _http_error(409, "PUBLISH_RECONCILIATION_OPERATION_INVALID", {"reason": "state_changed_before_review"})
            if evidence["project_id"] != package["project_id"] or str(evidence["sha256"] or "") != row["evidence_sha256"] or _json_object(evidence["metadata_json"]).get("immutable") is not True:
                raise _http_error(409, "PUBLISH_RECONCILIATION_EVIDENCE_INVALID", {"reason": "evidence_changed_before_review"})

            case_data = self._case_data(conn, row)
            attestation = _manual_attestation(case_data, payload.reviewed_by)
            receipt_sha256 = canonical_sha256(attestation)
            resolved_package_status = "withdrawn" if package["publication_action"] == "withdraw" else "delivered"
            operation_response: dict[str, object] = {
                "status": resolved_package_status,
                "published_url": row["published_url"],
                "request_sha256": operation["request_sha256"],
                "response_sha256": receipt_sha256,
                "response_status": int(row["response_status"]),
                "remote_id": row["external_receipt_id"],
                "idempotent_replay": False,
                "receipt_origin": "manual_reconciliation",
                "reconciliation_case_id": case_id,
                "reconciliation_method": METHOD,
                "external_delivery_verified": False,
                "evidence_object_ref_id": row["evidence_object_ref_id"],
                "evidence_sha256": row["evidence_sha256"],
            }
            try:
                self.operation_guard.transition_in_transaction(
                    conn,
                    str(operation["id"]),
                    allowed={"external_started"},
                    to_state="succeeded",
                    event_type="operation_reconciled_succeeded",
                    actor=payload.reviewed_by,
                    trace_id=trace_id,
                    response=operation_response,
                    now=reviewed_at,
                )
            except OperationGuardError as exc:
                raise _http_error(409, "PUBLISH_RECONCILIATION_OPERATION_INVALID", {"reason": exc.code}) from exc

            metadata = _json_object(package["metadata_json"])
            metadata["implementation_status"] = "partial"
            metadata.pop("reconciliation_required", None)
            metadata.pop("reconciliation_reason", None)
            metadata["reconciliation_resolution"] = {
                "case_id": case_id,
                "method": METHOD,
                "external_delivery_verified": False,
                "evidence_object_ref_id": row["evidence_object_ref_id"],
                "evidence_sha256": row["evidence_sha256"],
                "submitted_by": row["submitted_by"],
                "reviewed_by": payload.reviewed_by,
                "applied_at": reviewed_at.isoformat(),
            }
            metadata["delivery_receipt"] = {
                "attempt_id": attempt["id"],
                "attempt_number": int(attempt["attempt_number"]),
                "operation_id": operation["id"],
                "request_sha256": attempt["request_sha256"],
                "response_sha256": receipt_sha256,
                "response_status": int(row["response_status"]),
                "remote_id": row["external_receipt_id"],
                "idempotent_replay": False,
                "delivered_at": reviewed_at.isoformat(),
                "publication_action": package["publication_action"],
                "receipt_origin": "manual_reconciliation",
                "reconciliation_case_id": case_id,
                "reconciliation_method": METHOD,
                "external_delivery_verified": False,
            }
            target_metadata: Optional[dict[str, Any]] = None
            target_status: Optional[str] = None
            if package["publication_action"] in {"update", "withdraw"}:
                if not package["target_package_id"]:
                    raise _http_error(409, "PUBLISH_MUTATION_TARGET_INVALID")
                target = conn.execute(text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND id=:target_id AND deleted_at IS NULL FOR UPDATE"), {"tenant_id": tenant_id, "target_id": package["target_package_id"]}).mappings().first()
                if target is None or target["status"] != "published":
                    raise _http_error(409, "PUBLISH_MUTATION_TARGET_STATE_CONFLICT", {"status": target["status"] if target else None})
                target_status = "superseded" if package["publication_action"] == "update" else "withdrawn"
                target_metadata = _json_object(target["metadata_json"])
                lineage_key = "superseded_by_package_id" if package["publication_action"] == "update" else "withdrawn_by_package_id"
                target_metadata[lineage_key] = package["id"]
                target_metadata["superseded_at" if package["publication_action"] == "update" else "withdrawn_at"] = reviewed_at.isoformat()
                target_metadata["mutation_reason"] = package["action_reason"]

            conn.execute(text("UPDATE airank_publish_attempts SET status='succeeded',response_status=:response_status,response_sha256=:response_sha256,reconciliation_case_id=:case_id,finished_at=:finished_at WHERE tenant_id=:tenant_id AND id=:attempt_id AND status='outcome_unknown'"), {"response_status": int(row["response_status"]), "response_sha256": receipt_sha256, "case_id": case_id, "finished_at": database_datetime(reviewed_at), "tenant_id": tenant_id, "attempt_id": attempt["id"]})
            conn.execute(text("UPDATE airank_publish_packages SET status=:status,published_url=:published_url,metadata_json=:metadata_json,updated_at=:updated_at WHERE tenant_id=:tenant_id AND id=:package_id AND status='outcome_unknown'"), {"status": resolved_package_status, "published_url": row["published_url"], "metadata_json": json.dumps(metadata, ensure_ascii=False), "updated_at": database_datetime(reviewed_at), "tenant_id": tenant_id, "package_id": package["id"]})
            if target_metadata is not None and target_status is not None:
                conn.execute(text("UPDATE airank_publish_packages SET status=:status,metadata_json=:metadata_json,updated_at=:updated_at WHERE tenant_id=:tenant_id AND id=:target_id AND status='published'"), {"status": target_status, "metadata_json": json.dumps(target_metadata, ensure_ascii=False), "updated_at": database_datetime(reviewed_at), "tenant_id": tenant_id, "target_id": package["target_package_id"]})

            conn.execute(text("UPDATE airank_publish_reconciliation_cases SET status='approved',reviewed_by=:reviewed_by,review_note=:review_note,review_idempotency_key_sha256=:key_sha,review_request_sha256=:request_sha,receipt_sha256=:receipt_sha,reviewed_at=:reviewed_at,updated_at=:reviewed_at WHERE id=:case_id"), {"reviewed_by": payload.reviewed_by, "review_note": payload.review_note, "key_sha": review_key_sha256, "request_sha": review_request_sha256, "receipt_sha": receipt_sha256, "reviewed_at": database_datetime(reviewed_at), "case_id": case_id})
            approved_row = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE id=:case_id FOR UPDATE"), {"case_id": case_id}).mappings().one()
            self._append_event(conn, approved_row, event_type="reconciliation_approved", from_status="awaiting_review", to_status="approved", actor=payload.reviewed_by, trace_id=trace_id, now=reviewed_at)
            conn.execute(text("UPDATE airank_publish_reconciliation_cases SET status='applied',applied_at=:applied_at,updated_at=:applied_at WHERE id=:case_id"), {"applied_at": database_datetime(reviewed_at), "case_id": case_id})
            applied_row = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE id=:case_id FOR UPDATE"), {"case_id": case_id}).mappings().one()
            self._append_event(conn, applied_row, event_type="reconciliation_applied", from_status="approved", to_status="applied", actor=payload.reviewed_by, trace_id=trace_id, now=reviewed_at)
            updated = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE id=:case_id"), {"case_id": case_id}).mappings().one()
            return self._case_data(conn, updated, include_events=True)

    def list_project(self, tenant_id: str, project_id: str) -> list[PublicationReconciliationData]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY submitted_at DESC,id DESC"), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
            return [self._case_data(conn, row) for row in rows]

    def get(self, tenant_id: str, case_id: str) -> PublicationReconciliationData:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM airank_publish_reconciliation_cases WHERE tenant_id=:tenant_id AND id=:case_id"), {"tenant_id": tenant_id, "case_id": case_id}).mappings().first()
            if row is None:
                raise _http_error(404, "PUBLISH_RECONCILIATION_NOT_FOUND", {"case_id": case_id})
            return self._case_data(conn, row, include_events=True)


def build_repository() -> PublicationReconciliationRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLPublicationReconciliationRepository(database_url) if database_url else InMemoryPublicationReconciliationRepository()


PUBLICATION_RECONCILIATION_REPOSITORY: PublicationReconciliationRepository = build_repository()


@router.post("/publish-packages/{package_id}/reconciliations", response_model=PublicationReconciliationResponse, status_code=201)
def submit_publication_reconciliation(
    package_id: str,
    payload: PublicationReconciliationSubmitRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> PublicationReconciliationResponse:
    require_delivery_admin(permission_header)
    resolved_trace_id = trace_id or f"trc_{uuid4().hex[:16]}"
    trusted_payload = payload.model_copy(update={"submitted_by": trusted_actor(payload.submitted_by, authenticated_actor)})
    return PublicationReconciliationResponse(
        data=PUBLICATION_RECONCILIATION_REPOSITORY.submit(tenant_id, package_id, trusted_payload, resolved_trace_id),
        meta=response_meta(resolved_trace_id),
    )


@router.post("/publish-reconciliations/{case_id}/review", response_model=PublicationReconciliationResponse)
def review_publication_reconciliation(
    case_id: str,
    payload: PublicationReconciliationReviewRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> PublicationReconciliationResponse:
    require_delivery_admin(permission_header)
    resolved_trace_id = trace_id or f"trc_{uuid4().hex[:16]}"
    trusted_payload = payload.model_copy(update={"reviewed_by": trusted_actor(payload.reviewed_by, authenticated_actor)})
    return PublicationReconciliationResponse(
        data=PUBLICATION_RECONCILIATION_REPOSITORY.review(tenant_id, case_id, trusted_payload, resolved_trace_id),
        meta=response_meta(resolved_trace_id),
    )


@router.get("/projects/{project_id}/publish-reconciliations", response_model=PublicationReconciliationListResponse)
def list_publication_reconciliations(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> PublicationReconciliationListResponse:
    require_delivery_admin(permission_header)
    return PublicationReconciliationListResponse(
        data=PUBLICATION_RECONCILIATION_REPOSITORY.list_project(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.get("/publish-reconciliations/{case_id}", response_model=PublicationReconciliationResponse)
def get_publication_reconciliation(
    case_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> PublicationReconciliationResponse:
    require_delivery_admin(permission_header)
    return PublicationReconciliationResponse(
        data=PUBLICATION_RECONCILIATION_REPOSITORY.get(tenant_id, case_id),
        meta=response_meta(trace_id),
    )

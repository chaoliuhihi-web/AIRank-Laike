from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from threading import Lock
from typing import Any, Literal, Optional, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_crawler_lite import CITATION_CAPTURE_VERSION


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["citation-source-capture"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    if authenticated_actor:
        return authenticated_actor
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})


def validate_source_url(value: str) -> str:
    normalized = value.strip()
    try:
        parsed = urlsplit(normalized)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("citation URL has an invalid port") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("citation URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("citation URL must not contain credentials")
    if parsed.fragment:
        raise ValueError("citation URL must not contain a fragment")
    return normalized


def as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"unsupported datetime {value!r}")


class CitationCaptureCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=160)
    requested_by: str = Field(min_length=1, max_length=64)


class CitationCaptureBatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=160)
    requested_by: str = Field(min_length=1, max_length=64)
    citation_ids: list[str] = Field(min_length=1, max_length=50)

    @field_validator("citation_ids")
    @classmethod
    def validate_citation_ids(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if any(not value or len(value) > 64 for value in normalized):
            raise ValueError("citation ids must contain 1 to 64 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("citation ids must be unique")
        return normalized


class CitationSourceSegmentData(BaseModel):
    segment_id: str
    segment_index: int
    source_start: int
    source_end: int
    segment_text: str
    segment_sha256: str


class CitationSourceCaptureData(BaseModel):
    capture_id: str
    tenant_id: str
    project_id: str
    citation_id: str
    job_id: str
    requested_url: str
    final_url: Optional[str] = None
    status: Literal["queued", "running", "completed", "blocked", "failed"]
    capture_version: str
    evidence_grade: Optional[str] = None
    response_status: Optional[int] = None
    content_type: Optional[str] = None
    response_bytes: Optional[int] = None
    content_sha256: Optional[str] = None
    visible_text_sha256: Optional[str] = None
    raw_object_ref_id: Optional[str] = None
    text_object_ref_id: Optional[str] = None
    connected_ip: Optional[str] = None
    redirect_count: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    requested_by: str
    segments: list[CitationSourceSegmentData]
    segments_loaded: bool = True
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    idempotent_replay: bool = False


class CitationSourceCaptureResponse(BaseModel):
    data: CitationSourceCaptureData
    meta: dict[str, str]


class CitationSourceCaptureListResponse(BaseModel):
    data: list[CitationSourceCaptureData]
    meta: dict[str, str]


class CitationCaptureBatchData(BaseModel):
    snapshot_id: str
    requested_count: int
    queued_count: int
    idempotent_replay_count: int
    captures: list[CitationSourceCaptureData]


class CitationCaptureBatchResponse(BaseModel):
    data: CitationCaptureBatchData
    meta: dict[str, str]


class CitationCaptureRepository(Protocol):
    def create(
        self,
        tenant_id: str,
        citation_id: str,
        payload: CitationCaptureCreateRequest,
        *,
        request_context_sha256: str | None = None,
    ) -> CitationSourceCaptureData: ...

    def list(self, tenant_id: str, citation_id: str) -> list[CitationSourceCaptureData]: ...

    def get(self, tenant_id: str, capture_id: str) -> CitationSourceCaptureData: ...

    def snapshot_citation_ids(self, tenant_id: str, snapshot_id: str) -> list[str]: ...

    def validate_batch(
        self, tenant_id: str, snapshot_id: str, citation_ids: list[str]
    ) -> None: ...

    def list_latest_by_snapshot(
        self, tenant_id: str, snapshot_id: str
    ) -> list[CitationSourceCaptureData]: ...


class InMemoryCitationCaptureRepository:
    def __init__(self) -> None:
        self._citations: dict[tuple[str, str], tuple[str, str, str, int]] = {}
        self._captures: dict[tuple[str, str], CitationSourceCaptureData] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._lock = Lock()

    def seed_citation(
        self,
        *,
        tenant_id: str,
        citation_id: str,
        project_id: str,
        url: str,
        snapshot_id: str = "snapshot_1",
        citation_order: int = 1,
    ) -> None:
        self._citations[(tenant_id, citation_id)] = (
            project_id,
            validate_source_url(url),
            snapshot_id,
            citation_order,
        )

    def create(
        self,
        tenant_id: str,
        citation_id: str,
        payload: CitationCaptureCreateRequest,
        *,
        request_context_sha256: str | None = None,
    ) -> CitationSourceCaptureData:
        citation = self._citations.get((tenant_id, citation_id))
        if citation is None:
            raise StarletteHTTPException(404, detail={"code": "CITATION_NOT_FOUND"})
        project_id, requested_url, _snapshot_id, _citation_order = citation
        request_sha256 = capture_request_sha256(
            tenant_id,
            project_id,
            citation_id,
            requested_url,
            request_context_sha256=request_context_sha256,
        )
        key = (tenant_id, project_id, payload.idempotency_key)
        with self._lock:
            existing = self._idempotency.get(key)
            if existing:
                existing_capture_id, existing_sha256 = existing
                if existing_sha256 != request_sha256:
                    raise StarletteHTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                return self._captures[(tenant_id, existing_capture_id)].model_copy(
                    update={"idempotent_replay": True}
                )
            now = utc_now()
            capture_id = f"citation_capture_{uuid4().hex}"
            row = CitationSourceCaptureData(
                capture_id=capture_id,
                tenant_id=tenant_id,
                project_id=project_id,
                citation_id=citation_id,
                job_id=f"job_citation_capture_{uuid4().hex}",
                requested_url=requested_url,
                status="queued",
                capture_version=CITATION_CAPTURE_VERSION,
                requested_by=payload.requested_by,
                segments=[],
                created_at=now,
            )
            self._captures[(tenant_id, capture_id)] = row
            self._idempotency[key] = (capture_id, request_sha256)
            return row

    def list(self, tenant_id: str, citation_id: str) -> list[CitationSourceCaptureData]:
        if (tenant_id, citation_id) not in self._citations:
            raise StarletteHTTPException(404, detail={"code": "CITATION_NOT_FOUND"})
        rows = [
            row
            for (row_tenant, _), row in self._captures.items()
            if row_tenant == tenant_id and row.citation_id == citation_id
        ]
        return sorted(rows, key=lambda row: (row.created_at, row.capture_id), reverse=True)

    def get(self, tenant_id: str, capture_id: str) -> CitationSourceCaptureData:
        try:
            return self._captures[(tenant_id, capture_id)]
        except KeyError as exc:
            raise StarletteHTTPException(
                404, detail={"code": "CITATION_CAPTURE_NOT_FOUND"}
            ) from exc

    def snapshot_citation_ids(self, tenant_id: str, snapshot_id: str) -> list[str]:
        rows = [
            (citation_order, citation_id)
            for (row_tenant, citation_id), (
                _project_id,
                _url,
                row_snapshot_id,
                citation_order,
            ) in self._citations.items()
            if row_tenant == tenant_id and row_snapshot_id == snapshot_id
        ]
        return [citation_id for _order, citation_id in sorted(rows)]

    def validate_batch(
        self, tenant_id: str, snapshot_id: str, citation_ids: list[str]
    ) -> None:
        allowed_ids = set(self.snapshot_citation_ids(tenant_id, snapshot_id))
        if any(citation_id not in allowed_ids for citation_id in citation_ids):
            raise StarletteHTTPException(
                404, detail={"code": "CITATION_NOT_FOUND_IN_SNAPSHOT"}
            )
        for citation_id in citation_ids:
            citation = self._citations[(tenant_id, citation_id)]
            try:
                validate_source_url(citation[1])
            except ValueError as exc:
                raise StarletteHTTPException(
                    409,
                    detail={
                        "code": "CITATION_CAPTURE_URL_INVALID",
                        "details": {"citation_id": citation_id, "reason": str(exc)},
                    },
                ) from exc

    def list_latest_by_snapshot(
        self, tenant_id: str, snapshot_id: str
    ) -> list[CitationSourceCaptureData]:
        latest: list[CitationSourceCaptureData] = []
        for citation_id in self.snapshot_citation_ids(tenant_id, snapshot_id):
            rows = self.list(tenant_id, citation_id)
            if rows:
                latest.append(
                    rows[0].model_copy(
                        update={"segments": [], "segments_loaded": False}
                    )
                )
        return latest


class MySQLCitationCaptureRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create(
        self,
        tenant_id: str,
        citation_id: str,
        payload: CitationCaptureCreateRequest,
        *,
        request_context_sha256: str | None = None,
    ) -> CitationSourceCaptureData:
        now = utc_now().replace(tzinfo=None)
        with self.engine.begin() as conn:
            citation = conn.execute(
                text(
                    """
                    SELECT id, project_id, url FROM airank_source_citations
                    WHERE tenant_id=:tenant_id AND id=:citation_id
                    FOR UPDATE
                    """
                ),
                {"tenant_id": tenant_id, "citation_id": citation_id},
            ).mappings().first()
            if citation is None:
                raise StarletteHTTPException(404, detail={"code": "CITATION_NOT_FOUND"})
            try:
                requested_url = validate_source_url(str(citation["url"] or ""))
            except ValueError as exc:
                raise StarletteHTTPException(
                    409,
                    detail={"code": "CITATION_CAPTURE_URL_INVALID", "details": {"reason": str(exc)}},
                ) from exc
            project_id = str(citation["project_id"])
            request_sha256 = capture_request_sha256(
                tenant_id,
                project_id,
                citation_id,
                requested_url,
                request_context_sha256=request_context_sha256,
            )
            existing = conn.execute(
                text(
                    """
                    SELECT id, request_sha256 FROM airank_citation_source_captures
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND idempotency_key=:idempotency_key
                    FOR UPDATE
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "idempotency_key": payload.idempotency_key,
                },
            ).mappings().first()
            if existing:
                if str(existing["request_sha256"]) != request_sha256:
                    raise StarletteHTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                capture_id = str(existing["id"])
            else:
                capture_id = f"citation_capture_{uuid4().hex}"
                job_id = f"job_citation_capture_{uuid4().hex}"
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_async_jobs (
                          id, tenant_id, project_id, job_type, status, priority,
                          scheduled_at, timeout_seconds, attempt_count, max_attempts,
                          payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, 'citation.capture', 'queued', 25,
                          :scheduled_at, 120, 0, 3, :payload_json, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": job_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "scheduled_at": now,
                        "payload_json": json.dumps(
                            {
                                "capture_id": capture_id,
                                "citation_id": citation_id,
                                "requested_url": requested_url,
                                "capture_version": CITATION_CAPTURE_VERSION,
                            },
                            ensure_ascii=False,
                        ),
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_citation_source_captures (
                          id, tenant_id, project_id, citation_id, job_id,
                          idempotency_key, request_sha256, requested_url, status,
                          capture_version, requested_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :citation_id, :job_id,
                          :idempotency_key, :request_sha256, :requested_url, 'queued',
                          :capture_version, :requested_by, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": capture_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "citation_id": citation_id,
                        "job_id": job_id,
                        "idempotency_key": payload.idempotency_key,
                        "request_sha256": request_sha256,
                        "requested_url": requested_url,
                        "capture_version": CITATION_CAPTURE_VERSION,
                        "requested_by": payload.requested_by,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
        return self.get(tenant_id, capture_id).model_copy(
            update={"idempotent_replay": bool(existing)}
        )

    def list(self, tenant_id: str, citation_id: str) -> list[CitationSourceCaptureData]:
        with self.engine.begin() as conn:
            exists = conn.execute(
                text(
                    "SELECT id FROM airank_source_citations "
                    "WHERE tenant_id=:tenant_id AND id=:citation_id"
                ),
                {"tenant_id": tenant_id, "citation_id": citation_id},
            ).first()
            if exists is None:
                raise StarletteHTTPException(404, detail={"code": "CITATION_NOT_FOUND"})
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_citation_source_captures
                    WHERE tenant_id=:tenant_id AND citation_id=:citation_id
                    ORDER BY created_at DESC, id DESC LIMIT 100
                    """
                ),
                {"tenant_id": tenant_id, "citation_id": citation_id},
            ).mappings().all()
        return [capture_row(row, segments=[], segments_loaded=False) for row in rows]

    def get(self, tenant_id: str, capture_id: str) -> CitationSourceCaptureData:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM airank_citation_source_captures "
                    "WHERE tenant_id=:tenant_id AND id=:capture_id"
                ),
                {"tenant_id": tenant_id, "capture_id": capture_id},
            ).mappings().first()
            if row is None:
                raise StarletteHTTPException(
                    404, detail={"code": "CITATION_CAPTURE_NOT_FOUND"}
                )
            segment_rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_citation_source_segments
                    WHERE tenant_id=:tenant_id AND capture_id=:capture_id
                    ORDER BY segment_index, id
                    """
                ),
                {"tenant_id": tenant_id, "capture_id": capture_id},
            ).mappings().all()
        segments = [
            CitationSourceSegmentData(
                segment_id=str(item["id"]),
                segment_index=int(item["segment_index"]),
                source_start=int(item["source_start"]),
                source_end=int(item["source_end"]),
                segment_text=str(item["segment_text"]),
                segment_sha256=str(item["segment_sha256"]),
            )
            for item in segment_rows
        ]
        return capture_row(row, segments=segments)

    def snapshot_citation_ids(self, tenant_id: str, snapshot_id: str) -> list[str]:
        with self.engine.begin() as conn:
            snapshot = conn.execute(
                text(
                    "SELECT id FROM airank_answer_snapshots "
                    "WHERE tenant_id=:tenant_id AND id=:snapshot_id"
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).first()
            if snapshot is None:
                raise StarletteHTTPException(
                    404, detail={"code": "ANSWER_SNAPSHOT_NOT_FOUND"}
                )
            rows = conn.execute(
                text(
                    """
                    SELECT id FROM airank_source_citations
                    WHERE tenant_id=:tenant_id AND snapshot_id=:snapshot_id
                    ORDER BY citation_order, id
                    LIMIT 1000
                    """
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).scalars().all()
        return [str(value) for value in rows]

    def validate_batch(
        self, tenant_id: str, snapshot_id: str, citation_ids: list[str]
    ) -> None:
        citation_params = {
            f"citation_id_{index}": citation_id
            for index, citation_id in enumerate(citation_ids)
        }
        citation_placeholders = ", ".join(
            f":citation_id_{index}" for index in range(len(citation_ids))
        )
        with self.engine.begin() as conn:
            snapshot = conn.execute(
                text(
                    "SELECT id FROM airank_answer_snapshots "
                    "WHERE tenant_id=:tenant_id AND id=:snapshot_id"
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).first()
            if snapshot is None:
                raise StarletteHTTPException(
                    404, detail={"code": "ANSWER_SNAPSHOT_NOT_FOUND"}
                )
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, url FROM airank_source_citations
                    WHERE tenant_id=:tenant_id AND snapshot_id=:snapshot_id
                      AND id IN ({citation_placeholders})
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "snapshot_id": snapshot_id,
                    **citation_params,
                },
            ).mappings().all()
        citations = {str(row["id"]): str(row["url"] or "") for row in rows}
        if any(citation_id not in citations for citation_id in citation_ids):
            raise StarletteHTTPException(
                404, detail={"code": "CITATION_NOT_FOUND_IN_SNAPSHOT"}
            )
        for citation_id in citation_ids:
            try:
                validate_source_url(citations[citation_id])
            except ValueError as exc:
                raise StarletteHTTPException(
                    409,
                    detail={
                        "code": "CITATION_CAPTURE_URL_INVALID",
                        "details": {"citation_id": citation_id, "reason": str(exc)},
                    },
                ) from exc

    def list_latest_by_snapshot(
        self, tenant_id: str, snapshot_id: str
    ) -> list[CitationSourceCaptureData]:
        self.snapshot_citation_ids(tenant_id, snapshot_id)
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT capture.*
                    FROM airank_citation_source_captures capture
                    INNER JOIN airank_source_citations citation
                      ON citation.id=capture.citation_id
                     AND citation.tenant_id=capture.tenant_id
                    WHERE capture.tenant_id=:tenant_id
                      AND citation.snapshot_id=:snapshot_id
                      AND NOT EXISTS (
                        SELECT 1
                        FROM airank_citation_source_captures newer
                        WHERE newer.tenant_id=capture.tenant_id
                          AND newer.citation_id=capture.citation_id
                          AND (
                            newer.created_at > capture.created_at
                            OR (newer.created_at = capture.created_at AND newer.id > capture.id)
                          )
                      )
                    ORDER BY citation.citation_order, citation.id
                    LIMIT 1000
                    """
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).mappings().all()
        return [
            capture_row(row, segments=[], segments_loaded=False) for row in rows
        ]


def capture_request_sha256(
    tenant_id: str,
    project_id: str,
    citation_id: str,
    requested_url: str,
    *,
    request_context_sha256: str | None = None,
) -> str:
    payload = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "citation_id": citation_id,
        "requested_url": requested_url,
        "capture_version": CITATION_CAPTURE_VERSION,
    }
    if request_context_sha256 is not None:
        payload["request_context_sha256"] = request_context_sha256
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def capture_row(
    row: Any,
    *,
    segments: list[CitationSourceSegmentData],
    segments_loaded: bool = True,
) -> CitationSourceCaptureData:
    return CitationSourceCaptureData(
        capture_id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        citation_id=str(row["citation_id"]),
        job_id=str(row["job_id"]),
        requested_url=str(row["requested_url"]),
        final_url=str(row["final_url"]) if row["final_url"] else None,
        status=str(row["status"]),  # type: ignore[arg-type]
        capture_version=str(row["capture_version"]),
        evidence_grade=str(row["evidence_grade"]) if row["evidence_grade"] else None,
        response_status=int(row["response_status"]) if row["response_status"] is not None else None,
        content_type=str(row["content_type"]) if row["content_type"] else None,
        response_bytes=int(row["response_bytes"]) if row["response_bytes"] is not None else None,
        content_sha256=str(row["content_sha256"]) if row["content_sha256"] else None,
        visible_text_sha256=(
            str(row["visible_text_sha256"]) if row["visible_text_sha256"] else None
        ),
        raw_object_ref_id=str(row["raw_object_ref_id"]) if row["raw_object_ref_id"] else None,
        text_object_ref_id=(
            str(row["text_object_ref_id"]) if row["text_object_ref_id"] else None
        ),
        connected_ip=str(row["connected_ip"]) if row["connected_ip"] else None,
        redirect_count=int(row["redirect_count"]) if row["redirect_count"] is not None else None,
        error_code=str(row["error_code"]) if row["error_code"] else None,
        error_message=str(row["error_message"]) if row["error_message"] else None,
        requested_by=str(row["requested_by"]),
        segments=segments,
        segments_loaded=segments_loaded,
        started_at=as_utc(row["started_at"]) if row["started_at"] else None,
        completed_at=as_utc(row["completed_at"]) if row["completed_at"] else None,
        created_at=as_utc(row["created_at"]),
    )


def build_repository() -> CitationCaptureRepository:
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    return (
        MySQLCitationCaptureRepository(database_url)
        if database_url
        else InMemoryCitationCaptureRepository()
    )


CITATION_CAPTURE_REPOSITORY = build_repository()


@router.post(
    "/citations/{citation_id}/source-captures",
    response_model=CitationSourceCaptureResponse,
    status_code=202,
)
def create_citation_source_capture(
    citation_id: str,
    payload: CitationCaptureCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> CitationSourceCaptureResponse:
    trusted_payload = payload.model_copy(
        update={"requested_by": trusted_actor(payload.requested_by, authenticated_actor)}
    )
    return CitationSourceCaptureResponse(
        data=CITATION_CAPTURE_REPOSITORY.create(tenant_id, citation_id, trusted_payload),
        meta=response_meta(trace_id),
    )


@router.post(
    "/answer-snapshots/{snapshot_id}/citation-source-captures:batch",
    response_model=CitationCaptureBatchResponse,
    status_code=202,
)
def create_citation_source_capture_batch(
    snapshot_id: str,
    payload: CitationCaptureBatchCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> CitationCaptureBatchResponse:
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    CITATION_CAPTURE_REPOSITORY.validate_batch(
        tenant_id, snapshot_id, payload.citation_ids
    )
    request_context_sha256 = hashlib.sha256(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "snapshot_id": snapshot_id,
                "citation_ids": payload.citation_ids,
                "capture_version": CITATION_CAPTURE_VERSION,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    idempotency_prefix = hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:24]
    captures = [
        CITATION_CAPTURE_REPOSITORY.create(
            tenant_id,
            citation_id,
            CitationCaptureCreateRequest(
                idempotency_key=f"citation-batch-{idempotency_prefix}-{index:02d}",
                requested_by=actor,
            ),
            request_context_sha256=request_context_sha256,
        )
        for index, citation_id in enumerate(payload.citation_ids)
    ]
    replay_count = sum(1 for capture in captures if capture.idempotent_replay)
    return CitationCaptureBatchResponse(
        data=CitationCaptureBatchData(
            snapshot_id=snapshot_id,
            requested_count=len(captures),
            queued_count=len(captures) - replay_count,
            idempotent_replay_count=replay_count,
            captures=captures,
        ),
        meta=response_meta(trace_id),
    )


@router.get(
    "/citations/{citation_id}/source-captures",
    response_model=CitationSourceCaptureListResponse,
)
def list_citation_source_captures(
    citation_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> CitationSourceCaptureListResponse:
    return CitationSourceCaptureListResponse(
        data=CITATION_CAPTURE_REPOSITORY.list(tenant_id, citation_id),
        meta=response_meta(trace_id),
    )


@router.get(
    "/answer-snapshots/{snapshot_id}/citation-source-captures/latest",
    response_model=CitationSourceCaptureListResponse,
)
def list_latest_citation_source_captures(
    snapshot_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> CitationSourceCaptureListResponse:
    return CitationSourceCaptureListResponse(
        data=CITATION_CAPTURE_REPOSITORY.list_latest_by_snapshot(
            tenant_id, snapshot_id
        ),
        meta=response_meta(trace_id),
    )


@router.get(
    "/citation-source-captures/{capture_id}",
    response_model=CitationSourceCaptureResponse,
)
def get_citation_source_capture(
    capture_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> CitationSourceCaptureResponse:
    return CitationSourceCaptureResponse(
        data=CITATION_CAPTURE_REPOSITORY.get(tenant_id, capture_id),
        meta=response_meta(trace_id),
    )

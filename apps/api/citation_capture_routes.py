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
from pydantic import BaseModel, ConfigDict, Field
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


class CitationCaptureRepository(Protocol):
    def create(
        self, tenant_id: str, citation_id: str, payload: CitationCaptureCreateRequest
    ) -> CitationSourceCaptureData: ...

    def list(self, tenant_id: str, citation_id: str) -> list[CitationSourceCaptureData]: ...

    def get(self, tenant_id: str, capture_id: str) -> CitationSourceCaptureData: ...


class InMemoryCitationCaptureRepository:
    def __init__(self) -> None:
        self._citations: dict[tuple[str, str], tuple[str, str]] = {}
        self._captures: dict[tuple[str, str], CitationSourceCaptureData] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._lock = Lock()

    def seed_citation(
        self, *, tenant_id: str, citation_id: str, project_id: str, url: str
    ) -> None:
        self._citations[(tenant_id, citation_id)] = (project_id, validate_source_url(url))

    def create(
        self, tenant_id: str, citation_id: str, payload: CitationCaptureCreateRequest
    ) -> CitationSourceCaptureData:
        citation = self._citations.get((tenant_id, citation_id))
        if citation is None:
            raise StarletteHTTPException(404, detail={"code": "CITATION_NOT_FOUND"})
        project_id, requested_url = citation
        request_sha256 = capture_request_sha256(tenant_id, project_id, citation_id, requested_url)
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


class MySQLCitationCaptureRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create(
        self, tenant_id: str, citation_id: str, payload: CitationCaptureCreateRequest
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
                tenant_id, project_id, citation_id, requested_url
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
        return [capture_row(row, segments=[]) for row in rows]

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


def capture_request_sha256(
    tenant_id: str, project_id: str, citation_id: str, requested_url: str
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "citation_id": citation_id,
                "requested_url": requested_url,
                "capture_version": CITATION_CAPTURE_VERSION,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def capture_row(row: Any, *, segments: list[CitationSourceSegmentData]) -> CitationSourceCaptureData:
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

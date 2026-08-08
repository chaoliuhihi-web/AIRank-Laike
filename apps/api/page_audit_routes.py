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

from airank_crawler_lite import PAGE_AUDIT_RULES_VERSION


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["page-extractability"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def _as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"unsupported datetime {value!r}")


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _validate_public_http_shape(value: str) -> str:
    normalized = value.strip()
    try:
        parsed = urlsplit(normalized)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("url has an invalid port") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("url must not contain credentials")
    if parsed.fragment:
        raise ValueError("url must not contain a fragment")
    return normalized


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    if not authenticated_actor:
        raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})
    return authenticated_actor


class PageAuditCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = Field(default=None, min_length=4, max_length=2048)
    idempotency_key: str = Field(min_length=8, max_length=160)
    requested_by: str = Field(min_length=1, max_length=64)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_public_http_shape(value) if value else value


class PageAuditFindingData(BaseModel):
    finding_id: str
    rule_id: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    status: Literal["passed", "failed"]
    title: str
    description: str
    recommendation: str
    evidence: dict[str, Any]
    score_delta: int


class PageAuditRunData(BaseModel):
    run_id: str
    tenant_id: str
    project_id: str
    job_id: str
    requested_url: str
    final_url: Optional[str] = None
    status: Literal["queued", "running", "completed", "blocked", "failed"]
    rules_version: str
    evidence_grade: Optional[str] = None
    technical_extractability_score: Optional[int] = None
    response_status: Optional[int] = None
    response_content_type: Optional[str] = None
    response_bytes: Optional[int] = None
    content_sha256: Optional[str] = None
    connected_ip: Optional[str] = None
    redirect_count: Optional[int] = None
    extracted: dict[str, Any]
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    requested_by: str
    finding_count: int
    failed_finding_count: int
    findings: list[PageAuditFindingData]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    idempotent_replay: bool = False


class PageAuditResponse(BaseModel):
    data: PageAuditRunData
    meta: dict[str, str]


class PageAuditListResponse(BaseModel):
    data: list[PageAuditRunData]
    meta: dict[str, str]


class PageAuditRepository(Protocol):
    def create(
        self,
        tenant_id: str,
        project_id: str,
        payload: PageAuditCreateRequest,
    ) -> PageAuditRunData:
        ...

    def list(self, tenant_id: str, project_id: str) -> list[PageAuditRunData]:
        ...

    def get(self, tenant_id: str, project_id: str, run_id: str) -> PageAuditRunData:
        ...


class InMemoryPageAuditRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str], PageAuditRunData] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._lock = Lock()

    def create(self, tenant_id: str, project_id: str, payload: PageAuditCreateRequest) -> PageAuditRunData:
        if not payload.url:
            raise StarletteHTTPException(status_code=400, detail={"code": "PAGE_AUDIT_URL_REQUIRED"})
        key = (tenant_id, project_id, payload.idempotency_key)
        with self._lock:
            if key in self._idempotency:
                existing = self._rows[(tenant_id, project_id, self._idempotency[key])]
                if existing.requested_url != payload.url:
                    raise StarletteHTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                return existing.model_copy(update={"idempotent_replay": True})
            now = utc_now()
            run_id = f"page_audit_{uuid4().hex}"
            row = PageAuditRunData(
                run_id=run_id,
                tenant_id=tenant_id,
                project_id=project_id,
                job_id=f"job_{uuid4().hex}",
                requested_url=payload.url,
                status="queued",
                rules_version=PAGE_AUDIT_RULES_VERSION,
                extracted={},
                requested_by=payload.requested_by,
                finding_count=0,
                failed_finding_count=0,
                findings=[],
                created_at=now,
            )
            self._rows[(tenant_id, project_id, run_id)] = row
            self._idempotency[key] = run_id
            return row

    def list(self, tenant_id: str, project_id: str) -> list[PageAuditRunData]:
        return sorted(
            [row for (tenant, project, _), row in self._rows.items() if tenant == tenant_id and project == project_id],
            key=lambda row: (row.created_at, row.run_id),
            reverse=True,
        )

    def get(self, tenant_id: str, project_id: str, run_id: str) -> PageAuditRunData:
        try:
            return self._rows[(tenant_id, project_id, run_id)]
        except KeyError as exc:
            raise StarletteHTTPException(status_code=404, detail={"code": "PAGE_AUDIT_NOT_FOUND"}) from exc


class MySQLPageAuditRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create(self, tenant_id: str, project_id: str, payload: PageAuditCreateRequest) -> PageAuditRunData:
        now = utc_now().replace(tzinfo=None)
        with self.engine.begin() as conn:
            project = conn.execute(
                text(
                    """
                    SELECT website_url FROM airank_projects
                    WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
                    FOR UPDATE
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().first()
            if project is None:
                raise StarletteHTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND"})
            candidate_url = str(payload.url or project["website_url"] or "")
            if not candidate_url:
                raise StarletteHTTPException(status_code=400, detail={"code": "PAGE_AUDIT_URL_REQUIRED"})
            try:
                requested_url = _validate_public_http_shape(candidate_url)
            except ValueError as exc:
                raise StarletteHTTPException(
                    status_code=400,
                    detail={"code": "PAGE_AUDIT_URL_INVALID", "message": str(exc)},
                ) from exc
            request_sha256 = hashlib.sha256(
                json.dumps(
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "requested_url": requested_url,
                        "rules_version": PAGE_AUDIT_RULES_VERSION,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            existing = conn.execute(
                text(
                    """
                    SELECT id, request_sha256 FROM airank_page_audit_runs
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
                if existing["request_sha256"] != request_sha256:
                    raise StarletteHTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                replay_id = str(existing["id"])
            else:
                replay_id = ""
                run_id = f"page_audit_{uuid4().hex}"
                job_id = f"job_page_audit_{uuid4().hex}"
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_async_jobs (
                          id, tenant_id, project_id, job_type, status, priority,
                          scheduled_at, timeout_seconds, attempt_count, max_attempts,
                          payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, 'page.audit', 'queued', 30,
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
                                "run_id": run_id,
                                "requested_url": requested_url,
                                "rules_version": PAGE_AUDIT_RULES_VERSION,
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
                        INSERT INTO airank_page_audit_runs (
                          id, tenant_id, project_id, job_id, idempotency_key,
                          request_sha256, requested_url, status, rules_version,
                          requested_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :job_id, :idempotency_key,
                          :request_sha256, :requested_url, 'queued', :rules_version,
                          :requested_by, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": run_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "idempotency_key": payload.idempotency_key,
                        "request_sha256": request_sha256,
                        "requested_url": requested_url,
                        "rules_version": PAGE_AUDIT_RULES_VERSION,
                        "requested_by": payload.requested_by,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                replay_id = run_id
        result = self.get(tenant_id, project_id, replay_id)
        return result.model_copy(update={"idempotent_replay": bool(existing)})

    def list(self, tenant_id: str, project_id: str) -> list[PageAuditRunData]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT r.*,
                           COUNT(f.id) AS finding_count,
                           SUM(CASE WHEN f.status='failed' THEN 1 ELSE 0 END) AS failed_finding_count
                    FROM airank_page_audit_runs r
                    LEFT JOIN airank_page_audit_findings f
                      ON f.tenant_id=r.tenant_id AND f.run_id=r.id
                    WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id
                    GROUP BY r.id
                    ORDER BY r.created_at DESC, r.id DESC
                    LIMIT 100
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        return [self._row(row, findings=[]) for row in rows]

    def get(self, tenant_id: str, project_id: str, run_id: str) -> PageAuditRunData:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT r.*,
                           COUNT(f.id) AS finding_count,
                           SUM(CASE WHEN f.status='failed' THEN 1 ELSE 0 END) AS failed_finding_count
                    FROM airank_page_audit_runs r
                    LEFT JOIN airank_page_audit_findings f
                      ON f.tenant_id=r.tenant_id AND f.run_id=r.id
                    WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id AND r.id=:run_id
                    GROUP BY r.id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id},
            ).mappings().first()
            if row is None:
                raise StarletteHTTPException(status_code=404, detail={"code": "PAGE_AUDIT_NOT_FOUND"})
            finding_rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_page_audit_findings
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    ORDER BY FIELD(severity,'critical','high','medium','low','info'), rule_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run_id},
            ).mappings().all()
        findings = [
            PageAuditFindingData(
                finding_id=str(item["id"]),
                rule_id=str(item["rule_id"]),
                severity=str(item["severity"]),  # type: ignore[arg-type]
                status=str(item["status"]),  # type: ignore[arg-type]
                title=str(item["title"]),
                description=str(item["description"]),
                recommendation=str(item["recommendation"] or ""),
                evidence=_json_object(item["evidence_json"]),
                score_delta=int(item["score_delta"] or 0),
            )
            for item in finding_rows
        ]
        return self._row(row, findings=findings)

    @staticmethod
    def _row(row: Any, *, findings: list[PageAuditFindingData]) -> PageAuditRunData:
        return PageAuditRunData(
            run_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            job_id=str(row["job_id"]),
            requested_url=str(row["requested_url"]),
            final_url=str(row["final_url"]) if row["final_url"] else None,
            status=str(row["status"]),  # type: ignore[arg-type]
            rules_version=str(row["rules_version"]),
            evidence_grade=str(row["evidence_grade"]) if row["evidence_grade"] else None,
            technical_extractability_score=(
                int(row["technical_extractability_score"])
                if row["technical_extractability_score"] is not None
                else None
            ),
            response_status=int(row["response_status"]) if row["response_status"] is not None else None,
            response_content_type=(
                str(row["response_content_type"]) if row["response_content_type"] else None
            ),
            response_bytes=int(row["response_bytes"]) if row["response_bytes"] is not None else None,
            content_sha256=str(row["content_sha256"]) if row["content_sha256"] else None,
            connected_ip=str(row["connected_ip"]) if row["connected_ip"] else None,
            redirect_count=int(row["redirect_count"]) if row["redirect_count"] is not None else None,
            extracted=_json_object(row["extracted_json"]),
            error_code=str(row["error_code"]) if row["error_code"] else None,
            error_message=str(row["error_message"]) if row["error_message"] else None,
            requested_by=str(row["requested_by"]),
            finding_count=int(row["finding_count"] or 0),
            failed_finding_count=int(row["failed_finding_count"] or 0),
            findings=findings,
            started_at=_as_utc(row["started_at"]) if row["started_at"] else None,
            completed_at=_as_utc(row["completed_at"]) if row["completed_at"] else None,
            created_at=_as_utc(row["created_at"]),
        )


def build_repository() -> PageAuditRepository:
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    return MySQLPageAuditRepository(database_url) if database_url else InMemoryPageAuditRepository()


PAGE_AUDIT_REPOSITORY = build_repository()


@router.post(
    "/projects/{project_id}/page-audits",
    response_model=PageAuditResponse,
    status_code=202,
)
def create_page_audit(
    project_id: str,
    payload: PageAuditCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> PageAuditResponse:
    trusted_payload = payload.model_copy(
        update={"requested_by": trusted_actor(payload.requested_by, authenticated_actor)}
    )
    return PageAuditResponse(
        data=PAGE_AUDIT_REPOSITORY.create(tenant_id, project_id, trusted_payload),
        meta=response_meta(trace_id),
    )


@router.get("/projects/{project_id}/page-audits", response_model=PageAuditListResponse)
def list_page_audits(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> PageAuditListResponse:
    return PageAuditListResponse(
        data=PAGE_AUDIT_REPOSITORY.list(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.get("/projects/{project_id}/page-audits/{run_id}", response_model=PageAuditResponse)
def get_page_audit(
    project_id: str,
    run_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> PageAuditResponse:
    return PageAuditResponse(
        data=PAGE_AUDIT_REPOSITORY.get(tenant_id, project_id, run_id),
        meta=response_meta(trace_id),
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Mapping, Protocol

from sqlalchemy import create_engine, text

from airank_crawler_lite import PAGE_AUDIT_RULES_VERSION, PageAuditResult, PageAuditService
from airank_domain import AsyncJob
from airank_outbound_security import OutboundSecurityError

from .lease import InMemoryJobLeaseStore, MySQLJobLeaseStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PageAuditWorkerError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class PageAuditExecutionSnapshot:
    tenant_id: str
    project_id: str
    run_id: str
    job_id: str
    requested_url: str
    status: str
    rules_version: str
    technical_extractability_score: int | None = None
    content_sha256: str | None = None


class PageAuditExecutionRepository(Protocol):
    def load(self, tenant_id: str, run_id: str, job_id: str) -> PageAuditExecutionSnapshot:
        ...

    def begin(self, snapshot: PageAuditExecutionSnapshot, started_at: datetime) -> None:
        ...

    def complete(
        self,
        snapshot: PageAuditExecutionSnapshot,
        result: PageAuditResult,
        completed_at: datetime,
    ) -> None:
        ...

    def fail(
        self,
        snapshot: PageAuditExecutionSnapshot,
        error: PageAuditWorkerError,
        completed_at: datetime,
        *,
        status: str,
    ) -> None:
        ...


class MySQLPageAuditExecutionRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def load(self, tenant_id: str, run_id: str, job_id: str) -> PageAuditExecutionSnapshot:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT tenant_id, project_id, id, job_id, requested_url, status,
                           rules_version, technical_extractability_score, content_sha256
                    FROM airank_page_audit_runs
                    WHERE tenant_id=:tenant_id AND id=:run_id AND job_id=:job_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run_id, "job_id": job_id},
            ).mappings().first()
        if row is None:
            raise PageAuditWorkerError("PAGE_AUDIT_NOT_FOUND", "page audit run was not found")
        return PageAuditExecutionSnapshot(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["id"]),
            job_id=str(row["job_id"]),
            requested_url=str(row["requested_url"]),
            status=str(row["status"]),
            rules_version=str(row["rules_version"]),
            technical_extractability_score=(
                int(row["technical_extractability_score"])
                if row["technical_extractability_score"] is not None
                else None
            ),
            content_sha256=str(row["content_sha256"]) if row["content_sha256"] else None,
        )

    def begin(self, snapshot: PageAuditExecutionSnapshot, started_at: datetime) -> None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE airank_page_audit_runs
                    SET status='running', started_at=COALESCE(started_at,:started_at),
                        error_code=NULL, error_message=NULL, updated_at=:started_at
                    WHERE tenant_id=:tenant_id AND id=:run_id AND job_id=:job_id
                      AND status IN ('queued','running','failed','blocked')
                    """
                ),
                {
                    "started_at": started_at.astimezone(timezone.utc).replace(tzinfo=None),
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                    "job_id": snapshot.job_id,
                },
            )
        if result.rowcount != 1:
            raise PageAuditWorkerError("PAGE_AUDIT_STATE_CONFLICT", "page audit run cannot start")

    def complete(
        self,
        snapshot: PageAuditExecutionSnapshot,
        result: PageAuditResult,
        completed_at: datetime,
    ) -> None:
        completed = completed_at.astimezone(timezone.utc).replace(tzinfo=None)
        extracted = {
            "title": result.title,
            "meta_description": result.meta_description,
            "canonical_url": result.canonical_url,
            "robots_directives": list(result.robots_directives),
            "h1_count": result.h1_count,
            "visible_text_chars": result.visible_text_chars,
            "json_ld_types": list(result.json_ld_types),
        }
        with self.engine.begin() as conn:
            existing_status = conn.execute(
                text(
                    """
                    SELECT status FROM airank_page_audit_runs
                    WHERE tenant_id=:tenant_id AND id=:run_id AND job_id=:job_id
                    FOR UPDATE
                    """
                ),
                {
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                    "job_id": snapshot.job_id,
                },
            ).scalar_one_or_none()
            if existing_status == "completed":
                return
            if existing_status != "running":
                raise PageAuditWorkerError("PAGE_AUDIT_STATE_CONFLICT", "page audit run is not running")
            for finding in result.findings:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_page_audit_findings (
                          id, tenant_id, project_id, run_id, rule_id, severity,
                          status, title, description, recommendation, evidence_json,
                          score_delta, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :run_id, :rule_id, :severity,
                          :status, :title, :description, :recommendation, :evidence_json,
                          :score_delta, :created_at
                        )
                        ON DUPLICATE KEY UPDATE id=id
                        """
                    ),
                    {
                        "id": f"page_finding_{snapshot.run_id[-16:]}_{finding.rule_id.replace('.', '_')}",
                        "tenant_id": snapshot.tenant_id,
                        "project_id": snapshot.project_id,
                        "run_id": snapshot.run_id,
                        "rule_id": finding.rule_id,
                        "severity": finding.severity,
                        "status": finding.status,
                        "title": finding.title,
                        "description": finding.description,
                        "recommendation": finding.recommendation or None,
                        "evidence_json": json.dumps(dict(finding.evidence), ensure_ascii=False),
                        "score_delta": finding.score_delta,
                        "created_at": completed,
                    },
                )
            conn.execute(
                text(
                    """
                    UPDATE airank_page_audit_runs
                    SET status='completed', final_url=:final_url,
                        evidence_grade=:evidence_grade,
                        technical_extractability_score=:technical_extractability_score,
                        response_status=:response_status,
                        response_content_type=:response_content_type,
                        response_bytes=:response_bytes,
                        content_sha256=:content_sha256,
                        connected_ip=:connected_ip,
                        redirect_count=:redirect_count,
                        extracted_json=:extracted_json,
                        error_code=NULL, error_message=NULL,
                        completed_at=:completed_at, updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:run_id AND job_id=:job_id
                    """
                ),
                {
                    "final_url": result.final_url,
                    "evidence_grade": result.evidence_grade,
                    "technical_extractability_score": result.technical_extractability_score,
                    "response_status": result.response_status,
                    "response_content_type": result.content_type,
                    "response_bytes": result.response_bytes,
                    "content_sha256": result.content_sha256,
                    "connected_ip": result.connected_ip,
                    "redirect_count": result.redirect_count,
                    "extracted_json": json.dumps(extracted, ensure_ascii=False),
                    "completed_at": completed,
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                    "job_id": snapshot.job_id,
                },
            )

    def fail(
        self,
        snapshot: PageAuditExecutionSnapshot,
        error: PageAuditWorkerError,
        completed_at: datetime,
        *,
        status: str,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_page_audit_runs
                    SET status=:status, error_code=:error_code,
                        error_message=:error_message, completed_at=:completed_at,
                        updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:run_id AND job_id=:job_id
                      AND status <> 'completed'
                    """
                ),
                {
                    "status": status,
                    "error_code": error.code,
                    "error_message": error.message[:1000],
                    "completed_at": completed_at.astimezone(timezone.utc).replace(tzinfo=None),
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                    "job_id": snapshot.job_id,
                },
            )


def build_page_audit_service() -> PageAuditService:
    try:
        timeout_seconds = max(1.0, float(os.getenv("AIRANK_PAGE_AUDIT_TIMEOUT_SECONDS") or 20))
    except ValueError:
        timeout_seconds = 20.0
    try:
        max_response_bytes = max(1, int(os.getenv("AIRANK_PAGE_AUDIT_MAX_RESPONSE_BYTES") or 2_000_000))
    except ValueError:
        max_response_bytes = 2_000_000
    return PageAuditService(
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
    )


def run_next_page_audit_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: PageAuditExecutionRepository,
    service: PageAuditService,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> PageAuditResult | None:
    started_at = now or utc_now()
    job = store.claim_next(worker_id, started_at, job_types={"page.audit"})
    if job is None:
        return None
    return run_claimed_page_audit_job(
        store,
        repository,
        service,
        job=job,
        worker_id=worker_id,
        started_at=started_at,
    )


def run_claimed_page_audit_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: PageAuditExecutionRepository,
    service: PageAuditService,
    *,
    job: AsyncJob,
    worker_id: str,
    started_at: datetime,
) -> PageAuditResult | None:
    payload = job.payload if isinstance(job.payload, Mapping) else {}
    run_id = str(payload.get("run_id") or "")
    if not run_id or str(payload.get("rules_version") or "") != PAGE_AUDIT_RULES_VERSION:
        error = PageAuditWorkerError("PAGE_AUDIT_JOB_INVALID", "page audit job payload is invalid")
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    try:
        snapshot = repository.load(job.tenant_id, run_id, job.id)
    except PageAuditWorkerError as exc:
        store.fail(job.id, worker_id, utc_now(), exc.code, exc.message)
        raise
    if snapshot.project_id != (job.project_id or ""):
        error = PageAuditWorkerError("PAGE_AUDIT_SCOPE_MISMATCH", "page audit job project scope differs")
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    if snapshot.status == "completed":
        store.succeed(
            job.id,
            worker_id,
            utc_now(),
            {
                "run_id": run_id,
                "technical_extractability_score": snapshot.technical_extractability_score,
                "content_sha256": snapshot.content_sha256,
                "idempotent_replay": True,
            },
        )
        return None
    repository.begin(snapshot, started_at)
    try:
        result = service.audit(snapshot.requested_url)
    except OutboundSecurityError as exc:
        error = PageAuditWorkerError(
            f"PAGE_AUDIT_{exc.code.removeprefix('OUTBOUND_')}",
            exc.message,
            retryable=exc.retryable,
        )
        finished_at = utc_now()
        repository.fail(
            snapshot,
            error,
            finished_at,
            status="failed" if error.retryable else "blocked",
        )
        store.fail(job.id, worker_id, finished_at, error.code, error.message)
        raise error from exc
    except Exception as exc:
        error = PageAuditWorkerError(
            "PAGE_AUDIT_INTERNAL_ERROR",
            f"page audit execution failed: {type(exc).__name__}",
        )
        finished_at = utc_now()
        repository.fail(snapshot, error, finished_at, status="failed")
        store.fail(job.id, worker_id, finished_at, error.code, error.message)
        raise error from exc
    finished_at = utc_now()
    repository.complete(snapshot, result, finished_at)
    store.succeed(
        job.id,
        worker_id,
        finished_at,
        {
            "run_id": run_id,
            "technical_extractability_score": result.technical_extractability_score,
            "content_sha256": result.content_sha256,
            "evidence_grade": result.evidence_grade,
        },
    )
    return result

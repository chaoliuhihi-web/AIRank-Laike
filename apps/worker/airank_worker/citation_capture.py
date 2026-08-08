from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Protocol

from sqlalchemy import create_engine, text

from airank_crawler_lite import (
    CITATION_CAPTURE_VERSION,
    CitationSourceCaptureResult,
    CitationSourceCaptureService,
)
from airank_domain import AsyncJob
from airank_evidence import ObjectStorage, ObjectStorageError, StoredObject
from airank_outbound_security import OutboundSecurityError

from .lease import InMemoryJobLeaseStore, MySQLJobLeaseStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CitationCaptureWorkerError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class CitationCaptureExecutionSnapshot:
    tenant_id: str
    project_id: str
    capture_id: str
    citation_id: str
    job_id: str
    requested_url: str
    status: str
    capture_version: str
    content_sha256: str | None = None
    raw_object_ref_id: str | None = None


class CitationCaptureExecutionRepository(Protocol):
    def load(
        self, tenant_id: str, capture_id: str, job_id: str
    ) -> CitationCaptureExecutionSnapshot: ...

    def begin(self, snapshot: CitationCaptureExecutionSnapshot, started_at: datetime) -> None: ...

    def complete(
        self,
        snapshot: CitationCaptureExecutionSnapshot,
        result: CitationSourceCaptureResult,
        raw_object: StoredObject,
        text_object: StoredObject,
        completed_at: datetime,
    ) -> None: ...

    def fail(
        self,
        snapshot: CitationCaptureExecutionSnapshot,
        error: CitationCaptureWorkerError,
        completed_at: datetime,
        *,
        status: str,
    ) -> None: ...


class MySQLCitationCaptureExecutionRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def load(
        self, tenant_id: str, capture_id: str, job_id: str
    ) -> CitationCaptureExecutionSnapshot:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT tenant_id, project_id, id, citation_id, job_id,
                           requested_url, status, capture_version,
                           content_sha256, raw_object_ref_id
                    FROM airank_citation_source_captures
                    WHERE tenant_id=:tenant_id AND id=:capture_id AND job_id=:job_id
                    """
                ),
                {"tenant_id": tenant_id, "capture_id": capture_id, "job_id": job_id},
            ).mappings().first()
        if row is None:
            raise CitationCaptureWorkerError(
                "CITATION_CAPTURE_NOT_FOUND", "citation source capture was not found"
            )
        return CitationCaptureExecutionSnapshot(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            capture_id=str(row["id"]),
            citation_id=str(row["citation_id"]),
            job_id=str(row["job_id"]),
            requested_url=str(row["requested_url"]),
            status=str(row["status"]),
            capture_version=str(row["capture_version"]),
            content_sha256=str(row["content_sha256"]) if row["content_sha256"] else None,
            raw_object_ref_id=(
                str(row["raw_object_ref_id"]) if row["raw_object_ref_id"] else None
            ),
        )

    def begin(self, snapshot: CitationCaptureExecutionSnapshot, started_at: datetime) -> None:
        moment = started_at.astimezone(timezone.utc).replace(tzinfo=None)
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE airank_citation_source_captures
                    SET status='running', started_at=COALESCE(started_at,:started_at),
                        error_code=NULL, error_message=NULL, updated_at=:started_at
                    WHERE tenant_id=:tenant_id AND id=:capture_id AND job_id=:job_id
                      AND status IN ('queued','running','failed','blocked')
                    """
                ),
                {
                    "started_at": moment,
                    "tenant_id": snapshot.tenant_id,
                    "capture_id": snapshot.capture_id,
                    "job_id": snapshot.job_id,
                },
            )
        if result.rowcount != 1:
            raise CitationCaptureWorkerError(
                "CITATION_CAPTURE_STATE_CONFLICT", "citation source capture cannot start"
            )

    def complete(
        self,
        snapshot: CitationCaptureExecutionSnapshot,
        result: CitationSourceCaptureResult,
        raw_object: StoredObject,
        text_object: StoredObject,
        completed_at: datetime,
    ) -> None:
        completed = completed_at.astimezone(timezone.utc).replace(tzinfo=None)
        raw_object_id = f"obj_citation_raw_{snapshot.capture_id[-24:]}"
        text_object_id = f"obj_citation_text_{snapshot.capture_id[-24:]}"
        raw_metadata = {
            "kind": "citation_source_page",
            "citation_id": snapshot.citation_id,
            "capture_id": snapshot.capture_id,
            "source_url": snapshot.requested_url,
            "final_url": result.final_url,
            "storage_driver": raw_object.driver,
            "object_key": raw_object.key,
            "capture_version": result.capture_version,
        }
        text_metadata = {
            "kind": "citation_source_text",
            "citation_id": snapshot.citation_id,
            "capture_id": snapshot.capture_id,
            "source_url": snapshot.requested_url,
            "final_url": result.final_url,
            "storage_driver": text_object.driver,
            "object_key": text_object.key,
            "capture_version": result.capture_version,
        }
        with self.engine.begin() as conn:
            current_status = conn.execute(
                text(
                    """
                    SELECT status FROM airank_citation_source_captures
                    WHERE tenant_id=:tenant_id AND id=:capture_id AND job_id=:job_id
                    FOR UPDATE
                    """
                ),
                {
                    "tenant_id": snapshot.tenant_id,
                    "capture_id": snapshot.capture_id,
                    "job_id": snapshot.job_id,
                },
            ).scalar_one_or_none()
            if current_status == "completed":
                return
            if current_status != "running":
                raise CitationCaptureWorkerError(
                    "CITATION_CAPTURE_STATE_CONFLICT", "citation source capture is not running"
                )
            for object_id, stored, metadata in (
                (raw_object_id, raw_object, raw_metadata),
                (text_object_id, text_object, text_metadata),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_object_refs (
                          id, tenant_id, project_id, object_type, object_uri,
                          content_type, byte_size, sha256, metadata_json, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, 'evidence', :object_uri,
                          :content_type, :byte_size, :sha256, :metadata_json, :created_at
                        ) ON DUPLICATE KEY UPDATE id=id
                        """
                    ),
                    {
                        "id": object_id,
                        "tenant_id": snapshot.tenant_id,
                        "project_id": snapshot.project_id,
                        "object_uri": stored.uri,
                        "content_type": stored.content_type,
                        "byte_size": stored.byte_size,
                        "sha256": stored.sha256,
                        "metadata_json": json.dumps(metadata, ensure_ascii=False),
                        "created_at": completed,
                    },
                )
            for segment in result.segments:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_citation_source_segments (
                          id, tenant_id, project_id, capture_id, segment_index,
                          source_start, source_end, segment_text, segment_sha256, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :capture_id, :segment_index,
                          :source_start, :source_end, :segment_text, :segment_sha256, :created_at
                        ) ON DUPLICATE KEY UPDATE id=id
                        """
                    ),
                    {
                        "id": f"citation_segment_{snapshot.capture_id[-16:]}_{segment.segment_index}",
                        "tenant_id": snapshot.tenant_id,
                        "project_id": snapshot.project_id,
                        "capture_id": snapshot.capture_id,
                        "segment_index": segment.segment_index,
                        "source_start": segment.source_start,
                        "source_end": segment.source_end,
                        "segment_text": segment.segment_text,
                        "segment_sha256": segment.segment_sha256,
                        "created_at": completed,
                    },
                )
            conn.execute(
                text(
                    """
                    UPDATE airank_citation_source_captures
                    SET status='completed', final_url=:final_url,
                        evidence_grade=:evidence_grade,
                        response_status=:response_status, content_type=:content_type,
                        response_bytes=:response_bytes, content_sha256=:content_sha256,
                        visible_text_sha256=:visible_text_sha256,
                        raw_object_ref_id=:raw_object_ref_id,
                        text_object_ref_id=:text_object_ref_id,
                        connected_ip=:connected_ip, redirect_count=:redirect_count,
                        error_code=NULL, error_message=NULL,
                        completed_at=:completed_at, updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:capture_id AND job_id=:job_id
                    """
                ),
                {
                    "final_url": result.final_url,
                    "evidence_grade": result.evidence_grade,
                    "response_status": result.response_status,
                    "content_type": result.content_type,
                    "response_bytes": result.response_bytes,
                    "content_sha256": result.content_sha256,
                    "visible_text_sha256": result.visible_text_sha256,
                    "raw_object_ref_id": raw_object_id,
                    "text_object_ref_id": text_object_id,
                    "connected_ip": result.connected_ip,
                    "redirect_count": result.redirect_count,
                    "completed_at": completed,
                    "tenant_id": snapshot.tenant_id,
                    "capture_id": snapshot.capture_id,
                    "job_id": snapshot.job_id,
                },
            )

    def fail(
        self,
        snapshot: CitationCaptureExecutionSnapshot,
        error: CitationCaptureWorkerError,
        completed_at: datetime,
        *,
        status: str,
    ) -> None:
        moment = completed_at.astimezone(timezone.utc).replace(tzinfo=None)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_citation_source_captures
                    SET status=:status, error_code=:error_code,
                        error_message=:error_message, completed_at=:completed_at,
                        updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:capture_id AND job_id=:job_id
                      AND status <> 'completed'
                    """
                ),
                {
                    "status": status,
                    "error_code": error.code,
                    "error_message": error.message[:1000],
                    "completed_at": moment,
                    "tenant_id": snapshot.tenant_id,
                    "capture_id": snapshot.capture_id,
                    "job_id": snapshot.job_id,
                },
            )


def build_citation_capture_service() -> CitationSourceCaptureService:
    try:
        timeout_seconds = max(
            1.0, float(os.getenv("AIRANK_CITATION_CAPTURE_TIMEOUT_SECONDS") or 20)
        )
    except ValueError:
        timeout_seconds = 20.0
    try:
        max_response_bytes = max(
            1, int(os.getenv("AIRANK_CITATION_CAPTURE_MAX_RESPONSE_BYTES") or 2_000_000)
        )
    except ValueError:
        max_response_bytes = 2_000_000
    return CitationSourceCaptureService(
        timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes
    )


def source_object_keys(
    snapshot: CitationCaptureExecutionSnapshot, result: CitationSourceCaptureResult
) -> tuple[str, str]:
    prefix = f"tenants/{snapshot.tenant_id}/projects/{snapshot.project_id}/citation-sources"
    extension = "html" if result.content_type in {"text/html", "application/xhtml+xml"} else "txt"
    return (
        f"{prefix}/raw/{result.content_sha256}.{extension}",
        f"{prefix}/text/{result.visible_text_sha256}.txt",
    )


def run_next_citation_capture_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: CitationCaptureExecutionRepository,
    service: CitationSourceCaptureService,
    object_storage: ObjectStorage,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> CitationSourceCaptureResult | None:
    started_at = now or utc_now()
    job = store.claim_next(worker_id, started_at, job_types={"citation.capture"})
    if job is None:
        return None
    return run_claimed_citation_capture_job(
        store,
        repository,
        service,
        object_storage,
        job=job,
        worker_id=worker_id,
        started_at=started_at,
    )


def run_claimed_citation_capture_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: CitationCaptureExecutionRepository,
    service: CitationSourceCaptureService,
    object_storage: ObjectStorage,
    *,
    job: AsyncJob,
    worker_id: str,
    started_at: datetime,
) -> CitationSourceCaptureResult | None:
    payload = job.payload if isinstance(job.payload, dict) else {}
    capture_id = str(payload.get("capture_id") or "")
    if (
        not capture_id
        or not payload.get("citation_id")
        or str(payload.get("capture_version") or "") != CITATION_CAPTURE_VERSION
    ):
        error = CitationCaptureWorkerError(
            "CITATION_CAPTURE_JOB_INVALID", "citation capture job payload is invalid"
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    try:
        snapshot = repository.load(job.tenant_id, capture_id, job.id)
    except CitationCaptureWorkerError as exc:
        store.fail(job.id, worker_id, utc_now(), exc.code, exc.message)
        raise
    if (
        snapshot.project_id != (job.project_id or "")
        or snapshot.citation_id != str(payload["citation_id"])
        or snapshot.capture_version != CITATION_CAPTURE_VERSION
    ):
        error = CitationCaptureWorkerError(
            "CITATION_CAPTURE_SCOPE_MISMATCH", "citation capture job scope differs"
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    if snapshot.status == "completed":
        store.succeed(
            job.id,
            worker_id,
            utc_now(),
            {
                "capture_id": capture_id,
                "content_sha256": snapshot.content_sha256,
                "raw_object_ref_id": snapshot.raw_object_ref_id,
                "idempotent_replay": True,
            },
        )
        return None
    repository.begin(snapshot, started_at)
    try:
        result = service.capture(snapshot.requested_url)
        raw_key, text_key = source_object_keys(snapshot, result)
        raw_object = object_storage.put_bytes(
            result.raw_body, key=raw_key, content_type=result.content_type
        )
        text_object = object_storage.put_bytes(
            result.visible_text.encode("utf-8"), key=text_key, content_type="text/plain; charset=utf-8"
        )
        if (
            raw_object.sha256 != result.content_sha256
            or text_object.sha256 != result.visible_text_sha256
        ):
            raise ObjectStorageError("stored citation object hash does not match capture result")
    except OutboundSecurityError as exc:
        error = CitationCaptureWorkerError(
            f"CITATION_CAPTURE_{exc.code.removeprefix('OUTBOUND_')}",
            exc.message,
            retryable=exc.retryable,
        )
    except ObjectStorageError as exc:
        error = CitationCaptureWorkerError(
            "CITATION_CAPTURE_STORAGE_FAILED",
            f"immutable citation storage failed: {type(exc).__name__}",
            retryable=True,
        )
    except ValueError as exc:
        error = CitationCaptureWorkerError("CITATION_CAPTURE_CONTENT_INVALID", str(exc))
    except Exception as exc:
        error = CitationCaptureWorkerError(
            "CITATION_CAPTURE_INTERNAL_ERROR",
            f"citation source capture failed: {type(exc).__name__}",
        )
    else:
        finished_at = utc_now()
        repository.complete(snapshot, result, raw_object, text_object, finished_at)
        store.succeed(
            job.id,
            worker_id,
            finished_at,
            {
                "capture_id": capture_id,
                "content_sha256": result.content_sha256,
                "visible_text_sha256": result.visible_text_sha256,
                "evidence_grade": result.evidence_grade,
            },
        )
        return result
    finished_at = utc_now()
    repository.fail(
        snapshot,
        error,
        finished_at,
        status="failed" if error.retryable else "blocked",
    )
    store.fail(job.id, worker_id, finished_at, error.code, error.message)
    raise error

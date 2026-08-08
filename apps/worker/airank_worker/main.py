from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from airank_evidence import ObjectStorageError, build_object_storage_from_env

from .citation_capture import (
    CitationCaptureWorkerError,
    MySQLCitationCaptureExecutionRepository,
    build_citation_capture_service,
    run_next_citation_capture_job,
)

from .lease import MySQLJobLeaseStore
from .knowledge_sync import (
    KnowledgeSyncWorkerError,
    MySQLKnowledgeSyncExecutionRepository,
    build_knowledge_sync_service,
    run_next_knowledge_sync_job,
)
from .publisher import (
    MySQLPublishExecutionRepository,
    PublisherError,
    PublisherGateway,
    run_next_publish_job,
)
from .page_audit import (
    MySQLPageAuditExecutionRepository,
    PageAuditWorkerError,
    build_page_audit_service,
    run_next_page_audit_job,
)
from .scan import ScanWorkerError, run_next_real_scan_job


JOB_TYPE_FILTERS: dict[str, set[str]] = {
    "all": {
        "publish.package",
        "scan.provider",
        "page.audit",
        "citation.capture",
        "knowledge.source.sync",
    },
    "publish": {"publish.package"},
    "scan": {"scan.provider"},
    "page-audit": {"page.audit"},
    "citation-capture": {"citation.capture"},
    "knowledge-sync": {"knowledge.source.sync"},
}


class WorkerScopeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WorkerScope:
    tenant_id: str | None
    project_id: str | None
    job_id: str | None
    global_scope: bool

    def to_record(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "global_scope": self.global_scope,
        }


def _clean(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_worker_scope(
    args: argparse.Namespace,
    env: Mapping[str, str] | None = None,
) -> WorkerScope:
    source = env or os.environ
    tenant_id = _clean(args.tenant_id) or _clean(source.get("AIRANK_WORKER_TENANT_ID"))
    project_id = _clean(args.project_id) or _clean(source.get("AIRANK_WORKER_PROJECT_ID"))
    job_id = _clean(args.job_id) or _clean(source.get("AIRANK_WORKER_JOB_ID"))
    if project_id and not tenant_id:
        raise WorkerScopeError(
            "WORKER_TENANT_SCOPE_REQUIRED",
            "project scope requires an explicit tenant scope",
        )
    if tenant_id or project_id or job_id:
        if args.allow_global_scope:
            raise WorkerScopeError(
                "WORKER_SCOPE_CONFLICT",
                "global scope cannot be combined with tenant, project, or job scope",
            )
        return WorkerScope(tenant_id, project_id, job_id, False)
    global_enabled = _enabled(source.get("AIRANK_WORKER_GLOBAL_SCOPE_ENABLED"))
    if not args.allow_global_scope or not global_enabled:
        raise WorkerScopeError(
            "WORKER_SCOPE_REQUIRED",
            "set a tenant/project/job scope, or explicitly enable and allow global scope",
        )
    return WorkerScope(None, None, None, True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIRank governed background worker")
    parser.add_argument("--once", action="store_true", help="claim at most one eligible job and exit")
    parser.add_argument("--drain", action="store_true", help="exit successfully when the scoped queue is empty")
    parser.add_argument("--max-jobs", type=int, help="stop after processing this many scoped jobs")
    parser.add_argument("--dry-run", action="store_true", help="inspect the scoped due queue without claiming jobs")
    parser.add_argument("--tenant-id", help="limit claims and timeout recovery to one tenant")
    parser.add_argument("--project-id", help="limit claims and timeout recovery to one project; requires tenant")
    parser.add_argument("--job-id", help="limit execution to one exact async job")
    parser.add_argument(
        "--allow-global-scope",
        action="store_true",
        help="allow all tenants only when AIRANK_WORKER_GLOBAL_SCOPE_ENABLED=true",
    )
    parser.add_argument(
        "--job-type",
        choices=("all", "publish", "scan", "page-audit", "citation-capture", "knowledge-sync"),
        default="all",
        help="limit this process to one governed job family",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_jobs is not None and args.max_jobs < 1:
        print(json.dumps({"status": "blocked", "error_code": "WORKER_MAX_JOBS_INVALID"}))
        return 2
    if args.once and args.max_jobs not in {None, 1}:
        print(json.dumps({"status": "blocked", "error_code": "WORKER_LIMIT_CONFLICT"}))
        return 2
    try:
        scope = resolve_worker_scope(args)
    except WorkerScopeError as exc:
        print(json.dumps({"status": "blocked", "error_code": exc.code}))
        return 2
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    if not database_url:
        print(json.dumps({"status": "blocked", "error_code": "DATABASE_NOT_CONFIGURED"}))
        return 2
    worker_id = str(os.getenv("AIRANK_WORKER_ID") or "airank-worker").strip()
    try:
        poll_seconds = max(0.25, float(os.getenv("AIRANK_WORKER_POLL_SECONDS") or 3))
    except ValueError:
        poll_seconds = 3.0
    store = MySQLJobLeaseStore(
        database_url,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        job_id=scope.job_id,
    )
    if args.dry_run:
        inspection = store.inspect_claimable(
            datetime.now(timezone.utc),
            job_types=JOB_TYPE_FILTERS[args.job_type],
        )
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "scope": scope.to_record(),
                    "job_type": args.job_type,
                    **inspection.to_record(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    repository = MySQLPublishExecutionRepository(database_url)
    gateway = PublisherGateway()
    page_audit_repository = MySQLPageAuditExecutionRepository(database_url)
    page_audit_service = build_page_audit_service()
    citation_capture_repository = MySQLCitationCaptureExecutionRepository(database_url)
    citation_capture_service = build_citation_capture_service()
    knowledge_sync_repository = MySQLKnowledgeSyncExecutionRepository(database_url)
    knowledge_sync_service = build_knowledge_sync_service()
    try:
        citation_object_storage = build_object_storage_from_env()
    except ObjectStorageError as exc:
        if args.job_type in {"all", "citation-capture", "knowledge-sync"}:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "error_code": "EVIDENCE_STORAGE_NOT_CONFIGURED",
                        "error_type": type(exc).__name__,
                    }
                )
            )
            return 2
        citation_object_storage = None

    processed_count = 0
    failed_count = 0
    job_limit = 1 if args.once else args.max_jobs
    while True:
        receipt = None
        scan_result = None
        page_audit_result = None
        citation_capture_result = None
        knowledge_sync_result = None
        try:
            if args.job_type in {"all", "publish"}:
                receipt = run_next_publish_job(
                    store,
                    repository,
                    gateway,
                    worker_id=worker_id,
                )
            if receipt is None and args.job_type in {"all", "scan"}:
                scan_result = run_next_real_scan_job(store, worker_id=worker_id)
            if receipt is None and scan_result is None and args.job_type in {"all", "page-audit"}:
                page_audit_result = run_next_page_audit_job(
                    store,
                    page_audit_repository,
                    page_audit_service,
                    worker_id=worker_id,
                )
            if (
                receipt is None
                and scan_result is None
                and page_audit_result is None
                and args.job_type in {"all", "citation-capture"}
                and citation_object_storage is not None
            ):
                citation_capture_result = run_next_citation_capture_job(
                    store,
                    citation_capture_repository,
                    citation_capture_service,
                    citation_object_storage,
                    worker_id=worker_id,
                )
            if (
                receipt is None
                and scan_result is None
                and page_audit_result is None
                and citation_capture_result is None
                and args.job_type in {"all", "knowledge-sync"}
                and citation_object_storage is not None
            ):
                knowledge_sync_result = run_next_knowledge_sync_job(
                    store,
                    knowledge_sync_repository,
                    knowledge_sync_service,
                    citation_object_storage,
                    worker_id=worker_id,
                )
        except PublisherError as exc:
            processed_count += 1
            failed_count += 1
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                    ensure_ascii=False,
                )
            )
        except ScanWorkerError as exc:
            processed_count += 1
            failed_count += 1
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                    ensure_ascii=False,
                )
            )
        except PageAuditWorkerError as exc:
            processed_count += 1
            failed_count += 1
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                    ensure_ascii=False,
                )
            )
        except CitationCaptureWorkerError as exc:
            processed_count += 1
            failed_count += 1
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                    ensure_ascii=False,
                )
            )
        except KnowledgeSyncWorkerError as exc:
            processed_count += 1
            failed_count += 1
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            if receipt is not None:
                print(
                    json.dumps(
                        {
                            "status": "delivered",
                            "published_url": receipt.published_url,
                            "request_sha256": receipt.request_sha256,
                            "response_sha256": receipt.response_sha256,
                            "idempotent_replay": receipt.idempotent_replay,
                        },
                        ensure_ascii=False,
                    )
                )
            elif scan_result is not None:
                print(json.dumps(scan_result.to_record(), ensure_ascii=False))
            elif page_audit_result is not None:
                print(json.dumps(page_audit_result.to_record(), ensure_ascii=False))
            elif citation_capture_result is not None:
                print(
                    json.dumps(
                        {
                            "status": "captured",
                            "content_sha256": citation_capture_result.content_sha256,
                            "visible_text_sha256": citation_capture_result.visible_text_sha256,
                            "segment_count": len(citation_capture_result.segments),
                            "evidence_grade": citation_capture_result.evidence_grade,
                        },
                        ensure_ascii=False,
                    )
                )
            elif knowledge_sync_result is not None:
                print(json.dumps(knowledge_sync_result.to_record(), ensure_ascii=False))
            handled = any(
                item is not None
                for item in (
                    receipt,
                    scan_result,
                    page_audit_result,
                    citation_capture_result,
                    knowledge_sync_result,
                )
            )
            if handled:
                processed_count += 1
                if scan_result is not None and scan_result.status == "failed":
                    failed_count += 1
            elif args.once or args.drain or job_limit is not None:
                print(
                    json.dumps(
                        {
                            "status": "drained",
                            "processed_count": processed_count,
                            "failed_count": failed_count,
                            "scope": scope.to_record(),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                return 1 if failed_count else 0
        if job_limit is not None and processed_count >= job_limit:
            return 1 if failed_count else 0
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import time

from airank_evidence import ObjectStorageError, build_object_storage_from_env

from .citation_capture import (
    CitationCaptureWorkerError,
    MySQLCitationCaptureExecutionRepository,
    build_citation_capture_service,
    run_next_citation_capture_job,
)

from .lease import MySQLJobLeaseStore
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIRank governed background worker")
    parser.add_argument("--once", action="store_true", help="claim at most one eligible job and exit")
    parser.add_argument(
        "--job-type",
        choices=("all", "publish", "scan", "page-audit", "citation-capture"),
        default="all",
        help="limit this process to publish or scan jobs",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    if not database_url:
        print(json.dumps({"status": "blocked", "error_code": "DATABASE_NOT_CONFIGURED"}))
        return 2
    worker_id = str(os.getenv("AIRANK_WORKER_ID") or "airank-worker").strip()
    try:
        poll_seconds = max(0.25, float(os.getenv("AIRANK_WORKER_POLL_SECONDS") or 3))
    except ValueError:
        poll_seconds = 3.0
    store = MySQLJobLeaseStore(database_url)
    repository = MySQLPublishExecutionRepository(database_url)
    gateway = PublisherGateway()
    page_audit_repository = MySQLPageAuditExecutionRepository(database_url)
    page_audit_service = build_page_audit_service()
    citation_capture_repository = MySQLCitationCaptureExecutionRepository(database_url)
    citation_capture_service = build_citation_capture_service()
    try:
        citation_object_storage = build_object_storage_from_env()
    except ObjectStorageError as exc:
        if args.job_type in {"all", "citation-capture"}:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "error_code": "CITATION_CAPTURE_STORAGE_NOT_CONFIGURED",
                        "error_type": type(exc).__name__,
                    }
                )
            )
            return 2
        citation_object_storage = None

    while True:
        receipt = None
        scan_result = None
        page_audit_result = None
        citation_capture_result = None
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
        except PublisherError as exc:
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
            if args.once:
                return 1
        except ScanWorkerError as exc:
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
            if args.once:
                return 1
        except PageAuditWorkerError as exc:
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
            if args.once:
                return 1
        except CitationCaptureWorkerError as exc:
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
            if args.once:
                return 1
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
            if args.once:
                return 1 if scan_result is not None and scan_result.status == "failed" else 0
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

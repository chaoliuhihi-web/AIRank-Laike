from __future__ import annotations

import argparse
import json
import os
import time

from .lease import MySQLJobLeaseStore
from .publisher import (
    MySQLPublishExecutionRepository,
    PublisherError,
    PublisherGateway,
    run_next_publish_job,
)
from .scan import ScanWorkerError, run_next_real_scan_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIRank governed background worker")
    parser.add_argument("--once", action="store_true", help="claim at most one eligible job and exit")
    parser.add_argument(
        "--job-type",
        choices=("all", "publish", "scan"),
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

    while True:
        receipt = None
        scan_result = None
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
            if args.once:
                return 1 if scan_result is not None and scan_result.status == "failed" else 0
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

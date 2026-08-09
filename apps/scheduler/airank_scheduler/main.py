from __future__ import annotations

import argparse
import json
import os
import time
from typing import Mapping

from apps.api.retest_routes import CompleteRetestRequest, MySQLRetestRepository
from apps.runtime_health import write_process_heartbeat

from .knowledge_sync import MySQLKnowledgeSyncScheduler
from .opportunity_action_escalation import MySQLOpportunityActionEscalationScheduler
from .opportunity_directory_sync import MySQLOpportunityDirectorySyncScheduler
from .retest import MySQLRetestScheduler
from .review_escalation import MySQLReviewEscalationScheduler
from .reviewer_directory_sync import MySQLReviewerDirectorySyncScheduler


def _clean(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_scope(
    args: argparse.Namespace,
    env: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None, str | None, bool]:
    source = env or os.environ
    tenant_id = _clean(args.tenant_id) or _clean(source.get("AIRANK_SCHEDULER_TENANT_ID"))
    project_id = _clean(args.project_id) or _clean(source.get("AIRANK_SCHEDULER_PROJECT_ID"))
    window_id = _clean(args.window_id) or _clean(source.get("AIRANK_SCHEDULER_WINDOW_ID"))
    if project_id and not tenant_id:
        raise ValueError("SCHEDULER_TENANT_SCOPE_REQUIRED")
    if tenant_id or project_id or window_id:
        if args.allow_global_scope:
            raise ValueError("SCHEDULER_SCOPE_CONFLICT")
        return tenant_id, project_id, window_id, False
    if not (
        args.allow_global_scope
        and _enabled(source.get("AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED"))
    ):
        raise ValueError("SCHEDULER_SCOPE_REQUIRED")
    return None, None, None, True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AIRank durable retest, knowledge, and reviewer-SLA scheduler"
    )
    parser.add_argument("--once", action="store_true", help="run one scheduler tick and exit")
    parser.add_argument("--dry-run", action="store_true", help="inspect due/ready windows without mutation")
    parser.add_argument("--tenant-id")
    parser.add_argument("--project-id")
    parser.add_argument("--window-id")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--allow-global-scope", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.limit < 1 or args.poll_seconds < 0.25:
        print(json.dumps({"status": "blocked", "error_code": "SCHEDULER_ARGUMENT_INVALID"}))
        return 2
    try:
        tenant_id, project_id, window_id, global_scope = resolve_scope(args)
    except ValueError as exc:
        print(json.dumps({"status": "blocked", "error_code": str(exc)}))
        return 2
    database_url = _clean(os.getenv("AIRANK_DATABASE_URL"))
    if not database_url:
        print(json.dumps({"status": "blocked", "error_code": "DATABASE_NOT_CONFIGURED"}))
        return 2
    scheduler_id = _clean(os.getenv("AIRANK_SCHEDULER_ID")) or "airank-retest-scheduler"
    scheduler = MySQLRetestScheduler(
        database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        window_id=window_id,
        scheduler_id=scheduler_id,
    )
    knowledge_scheduler = MySQLKnowledgeSyncScheduler(
        database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        scheduler_id=scheduler_id,
    )
    review_escalation_scheduler = MySQLReviewEscalationScheduler(
        database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        scheduler_id=scheduler_id,
    )
    opportunity_action_escalation_scheduler = MySQLOpportunityActionEscalationScheduler(
        database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        scheduler_id=scheduler_id,
    )
    reviewer_directory_scheduler = MySQLReviewerDirectorySyncScheduler(
        database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        scheduler_id=scheduler_id,
    )
    opportunity_directory_scheduler = MySQLOpportunityDirectorySyncScheduler(
        database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        scheduler_id=scheduler_id,
    )
    if args.dry_run:
        retest_preview = scheduler.preview().to_record()
        knowledge_preview = (
            {"skipped": "window_id scope only"}
            if window_id
            else knowledge_scheduler.preview().to_record()
        )
        review_escalation_preview = (
            {"skipped": "window_id scope only"}
            if window_id
            else review_escalation_scheduler.preview().to_record()
        )
        opportunity_action_escalation_preview = (
            {"skipped": "window_id scope only"}
            if window_id
            else opportunity_action_escalation_scheduler.preview().to_record()
        )
        reviewer_directory_preview = (
            {"skipped": "window_id scope only"}
            if window_id
            else reviewer_directory_scheduler.preview().to_record()
        )
        opportunity_directory_preview = (
            {"skipped": "window_id scope only"}
            if window_id
            else opportunity_directory_scheduler.preview().to_record()
        )
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "scope": {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "window_id": window_id,
                        "global_scope": global_scope,
                    },
                    "retest": retest_preview,
                    "knowledge_sync": knowledge_preview,
                    "review_escalation": review_escalation_preview,
                    "opportunity_action_escalation": opportunity_action_escalation_preview,
                    "reviewer_directory_sync": reviewer_directory_preview,
                    "opportunity_directory_sync": opportunity_directory_preview,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    retest_repository = MySQLRetestRepository(database_url)
    write_process_heartbeat("scheduler.json", component="scheduler", identity=scheduler_id)
    while True:
        finalized: list[dict[str, object]] = []
        for ready in scheduler.ready_to_finalize(limit=args.limit):
            result = retest_repository.complete_window(
                ready["tenant_id"],
                ready["window_id"],
                CompleteRetestRequest(
                    compare_run_id=ready["compare_run_id"],
                    completed_by=scheduler_id,
                ),
            )
            finalized.append(
                {
                    "window_id": ready["window_id"],
                    "compare_run_id": ready["compare_run_id"],
                    "report_status": result.report_status,
                    "report_sha256": result.report_sha256,
                }
            )
        dispatched = scheduler.dispatch_due(limit=args.limit)
        knowledge_dispatched = (
            [] if window_id else knowledge_scheduler.dispatch_due(limit=args.limit)
        )
        review_escalations = (
            []
            if window_id
            else review_escalation_scheduler.dispatch_overdue(limit=args.limit)
        )
        opportunity_action_escalations = (
            []
            if window_id
            else opportunity_action_escalation_scheduler.dispatch_overdue(
                limit=args.limit
            )
        )
        reviewer_directory_dispatched = (
            []
            if window_id
            else reviewer_directory_scheduler.dispatch_due(limit=args.limit)
        )
        opportunity_directory_dispatched = (
            []
            if window_id
            else opportunity_directory_scheduler.dispatch_due(limit=args.limit)
        )
        print(
            json.dumps(
                {
                    "status": "tick_completed",
                    "finalized": finalized,
                    "dispatched": [item.to_record() for item in dispatched],
                    "knowledge_sync_dispatched": [
                        item.to_record() for item in knowledge_dispatched
                    ],
                    "review_escalations": [
                        item.to_record() for item in review_escalations
                    ],
                    "opportunity_action_escalations": [
                        item.to_record() for item in opportunity_action_escalations
                    ],
                    "reviewer_directory_sync_dispatched": [
                        item.to_record() for item in reviewer_directory_dispatched
                    ],
                    "opportunity_directory_sync_dispatched": [
                        item.to_record() for item in opportunity_directory_dispatched
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        write_process_heartbeat("scheduler.json", component="scheduler", identity=scheduler_id)
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

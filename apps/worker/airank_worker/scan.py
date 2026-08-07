from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any, Mapping
from uuid import uuid4

from airank_evidence import AnswerSnapshot, MockAnswerProvider, ProviderPayloadError
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .lease import InMemoryJobLeaseStore, MySQLJobLeaseStore, parse_json_value


@dataclass(frozen=True)
class ScanDispatchResult:
    run_id: str
    status: str
    task_count: int
    completed_count: int
    failed_count: int
    blocked_count: int
    trigger_job_id: str
    idempotent_replay: bool = False

    def to_record(self) -> dict[str, object]:
        return asdict(self)


class ScanWorkerError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_next_real_scan_job(
    store: MySQLJobLeaseStore,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> ScanDispatchResult | None:
    claimed_at = now or utc_now()
    job = store.claim_next(worker_id, claimed_at, job_types={"scan.provider"})
    if job is None:
        return None
    payload = job.payload if isinstance(job.payload, Mapping) else {}
    run_id = str(payload.get("run_id") or "")
    task_id = str(payload.get("scan_task_id") or "")
    project_id = str(payload.get("project_id") or job.project_id or "")
    if not run_id or not task_id or not project_id:
        error = ScanWorkerError("SCAN_JOB_INVALID", "scan job is missing run, task, or project scope")
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error

    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    if not database_url:
        error = ScanWorkerError("DATABASE_NOT_CONFIGURED", "AIRANK_DATABASE_URL is required")
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as conn:
        run_row = conn.execute(
            text(
                """
                SELECT tenant_id, project_id, status
                FROM airank_scan_runs
                WHERE id = :run_id AND deleted_at IS NULL
                """
            ),
            {"run_id": run_id},
        ).mappings().first()
        task_row = conn.execute(
            text(
                """
                SELECT tenant_id, project_id, run_id, status, error_code, error_message
                FROM airank_scan_tasks
                WHERE id = :task_id
                """
            ),
            {"task_id": task_id},
        ).mappings().first()
        if (
            run_row is None
            or task_row is None
            or run_row["tenant_id"] != job.tenant_id
            or task_row["tenant_id"] != job.tenant_id
            or run_row["project_id"] != project_id
            or task_row["project_id"] != project_id
            or task_row["run_id"] != run_id
        ):
            error = ScanWorkerError("SCAN_JOB_SCOPE_MISMATCH", "scan job scope does not match run and task")
            store.fail(job.id, worker_id, utc_now(), error.code, error.message)
            raise error

        if run_row["status"] in {"completed", "failed", "canceled"}:
            return _replay_terminal_run(
                store,
                worker_id=worker_id,
                job_id=job.id,
                run_id=run_id,
                task_row=dict(task_row),
                engine=engine,
            )

        claimed_run = conn.execute(
            text(
                """
                UPDATE airank_scan_runs
                SET status = 'running',
                    started_at = COALESCE(started_at, :started_at),
                    updated_at = :started_at
                WHERE tenant_id = :tenant_id
                  AND id = :run_id
                  AND status = 'queued'
                """
            ),
            {"tenant_id": job.tenant_id, "run_id": run_id, "started_at": claimed_at},
        ).rowcount

        if claimed_run != 1 and run_row["status"] == "running":
            live_run_jobs = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND job_type = 'scan.provider'
                      AND status = 'running'
                      AND id <> :job_id
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id')) = :run_id
                    """
                ),
                {
                    "tenant_id": job.tenant_id,
                    "project_id": project_id,
                    "job_id": job.id,
                    "run_id": run_id,
                },
            ).scalar_one()
        else:
            live_run_jobs = 0

    if claimed_run != 1:
        if live_run_jobs:
            # Another scan job owns the run-level lease. It will update every
            # task/job in this run. Defer this redundant trigger so concurrent
            # workers cannot drain the whole queue while the owner is healthy.
            try:
                store.defer_claim(job.id, worker_id, utc_now(), delay_seconds=5)
            except Exception:
                # The owner may have completed the entire run between the live
                # lease query and this update. The persisted run/task state is
                # authoritative and the next claim is an idempotent replay.
                pass
            return _scan_result(engine, job.id, run_id, "in_progress", idempotent_replay=True)
        # The run says running but its prior async-job lease has expired. Calls
        # may already have reached an external Provider, so automatic replay is
        # unsafe. Fail closed and preserve one immutable infrastructure-failure
        # sample for every task that has no answer snapshot.
        _fail_unpersisted_scan_tasks(
            engine,
            tenant_id=job.tenant_id,
            project_id=project_id,
            run_id=run_id,
            finished_at=utc_now(),
            error_code="SCAN_RUN_LEASE_EXPIRED",
            error_message=(
                "The scan worker lease expired before durable batch completion. "
                "Automatic replay was suppressed to prevent duplicate Provider calls; create a new scan run to retry."
            ),
            capture_mode="worker_lease_expired",
        )
        return _scan_result(engine, job.id, run_id, "failed")

    try:
        from apps.api import main as api_main

        project = api_main.get_mysql_project(job.tenant_id, project_id)
        run = api_main.MySQLScanRepository(database_url).get_run(job.tenant_id, run_id)
        competitors = api_main.list_mysql_project_competitors(job.tenant_id, project_id)
        question_ids = set(run.question_scope.question_ids)
        questions = [
            question
            for question in api_main.list_mysql_project_questions(job.tenant_id, project_id)
            if question.question_id in question_ids
        ]
        def heartbeat_scan(_task_id: str, _phase: str) -> None:
            current = store.get(job.id)
            if current.status.value == "running":
                store.heartbeat(job.id, worker_id, utc_now())

        api_main.complete_mysql_brand_scan(
            job.tenant_id,
            project,
            competitors,
            questions,
            run,
            progress_hook=heartbeat_scan,
        )
    except StarletteHTTPException:
        # The scan orchestrator persists task failures, immutable failure evidence,
        # and the terminal run before returning its fail-closed 503.
        return _scan_result(engine, job.id, run_id, "failed")
    except Exception as exc:
        error = ScanWorkerError(
            "SCAN_WORKER_INTERNAL_ERROR",
            f"scan worker execution failed: {type(exc).__name__}",
            retryable=False,
        )
        _fail_unpersisted_scan_tasks(
            engine,
            tenant_id=job.tenant_id,
            project_id=project_id,
            run_id=run_id,
            finished_at=utc_now(),
            error_code=error.code,
            error_message=(
                f"{error.message}. Automatic replay was suppressed because the external-call outcome may be unknown; "
                "create a new scan run to retry."
            ),
            capture_mode="worker_internal_failure",
        )
        raise error from exc

    return _scan_result(engine, job.id, run_id, "completed")


def _fail_unpersisted_scan_tasks(
    engine: Any,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    finished_at: datetime,
    error_code: str,
    error_message: str,
    capture_mode: str,
) -> None:
    with engine.begin() as conn:
        task_rows = conn.execute(
            text(
                """
                SELECT t.id, t.question_id, t.provider, t.cohort_type,
                       t.prompt_version_id, t.sample_index, t.session_id,
                       t.collector_surface, t.evidence_level, t.request_json
                FROM airank_scan_tasks t
                LEFT JOIN airank_answer_snapshots s
                  ON s.tenant_id = t.tenant_id AND s.task_id = t.id
                WHERE t.tenant_id = :tenant_id
                  AND t.project_id = :project_id
                  AND t.run_id = :run_id
                  AND t.status IN ('queued', 'running')
                  AND s.id IS NULL
                ORDER BY t.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id},
        ).mappings().all()

        for task in task_rows:
            snapshot_id = f"snap_{uuid4().hex[:12]}"
            evidence_id = f"evidence_{uuid4().hex[:12]}"
            raw_response = {
                "provider": task["provider"],
                "sample_status": "failed",
                "failure": {
                    "error_code": error_code,
                    "error_message": error_message,
                    "blocked": False,
                    "retryable": False,
                    "automatic_replay_suppressed": True,
                },
                "capture_metadata": {
                    "capture_mode": capture_mode,
                    "collector_surface": task["collector_surface"],
                    "provider_response_available": False,
                },
            }
            raw_json = json.dumps(raw_response, ensure_ascii=False, sort_keys=True)
            raw_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            request_metadata = {
                "task_request": parse_json_value(task["request_json"], {}),
                "failure": raw_response["failure"],
            }
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, cohort_type, prompt_version_id, sample_index,
                      session_id, collector_surface, evidence_level, sample_status,
                      answer_text, answer_sha256, raw_response_sha256,
                      brand_mentioned, brand_rank, mention_class, target_entity_mentions_json,
                      model_name, search_enabled, competitor_mentions_json, sentiment, confidence,
                      raw_response_ref_id, screenshot_ref_id, request_metadata_ref_id,
                      external_trace_id, created_at
                    ) VALUES (
                      :snapshot_id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :cohort_type, :prompt_version_id, :sample_index,
                      :session_id, :collector_surface, :evidence_level, 'failed',
                      '', NULL, :raw_sha256,
                      0, NULL, 'unknown', JSON_ARRAY(),
                      NULL, NULL, JSON_ARRAY(), NULL, NULL,
                      :evidence_id, NULL, :evidence_id,
                      NULL, :finished_at
                    )
                    """
                ),
                {
                    "snapshot_id": snapshot_id,
                    "evidence_id": evidence_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "task_id": task["id"],
                    "question_id": task["question_id"],
                    "provider": task["provider"],
                    "cohort_type": task["cohort_type"],
                    "prompt_version_id": task["prompt_version_id"],
                    "sample_index": task["sample_index"],
                    "session_id": task["session_id"],
                    "collector_surface": task["collector_surface"],
                    "evidence_level": task["evidence_level"],
                    "raw_sha256": raw_sha256,
                    "finished_at": finished_at,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_snapshots (
                      id, tenant_id, project_id, answer_snapshot_id,
                      raw_response_json, raw_response_sha256, screenshot_ref_id,
                      source_panel_ref_id, request_metadata_json, captured_at, created_at
                    ) VALUES (
                      :evidence_id, :tenant_id, :project_id, :snapshot_id,
                      :raw_json, :raw_sha256, NULL,
                      NULL, :request_metadata_json, :finished_at, :finished_at
                    )
                    """
                ),
                {
                    "evidence_id": evidence_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "snapshot_id": snapshot_id,
                    "raw_json": raw_json,
                    "raw_sha256": raw_sha256,
                    "request_metadata_json": json.dumps(
                        request_metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                    "finished_at": finished_at,
                },
            )

        conn.execute(
            text(
                """
                UPDATE airank_scan_tasks
                SET status = 'failed',
                    attempt_count = GREATEST(attempt_count, 1),
                    started_at = COALESCE(started_at, :finished_at),
                    finished_at = :finished_at,
                    updated_at = :finished_at,
                    error_code = :error_code,
                    error_message = :error_message,
                    response_meta_json = :response_meta_json
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND run_id = :run_id
                  AND status IN ('queued', 'running')
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "finished_at": finished_at,
                "error_code": error_code,
                "error_message": error_message,
                "response_meta_json": json.dumps(
                    {
                        "mode": capture_mode,
                        "provider_response_available": False,
                        "automatic_replay_suppressed": True,
                    },
                    ensure_ascii=False,
                ),
            },
        )
        conn.execute(
            text(
                """
                UPDATE airank_async_jobs
                SET status = 'failed',
                    finished_at = :finished_at,
                    updated_at = :finished_at,
                    error_code = :error_code,
                    error_message = :error_message
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND job_type = 'scan.provider'
                  AND status IN ('queued', 'running')
                  AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id')) = :run_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "finished_at": finished_at,
                "error_code": error_code,
                "error_message": error_message,
            },
        )
        conn.execute(
            text(
                """
                UPDATE airank_scan_runs
                SET status = 'failed',
                    error_message = :error_message,
                    finished_at = :finished_at,
                    updated_at = :finished_at
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id = :run_id
                  AND status = 'running'
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "error_message": error_message,
                "finished_at": finished_at,
            },
        )


def _replay_terminal_run(
    store: MySQLJobLeaseStore,
    *,
    worker_id: str,
    job_id: str,
    run_id: str,
    task_row: dict[str, Any],
    engine: Any,
) -> ScanDispatchResult:
    finished_at = utc_now()
    if str(task_row.get("status")) in {"completed", "succeeded"}:
        store.succeed(job_id, worker_id, finished_at, {"run_id": run_id, "idempotent_replay": True})
        status = "completed"
    else:
        store.fail(
            job_id,
            worker_id,
            finished_at,
            str(task_row.get("error_code") or "SCAN_PROVIDER_FAILED"),
            str(task_row.get("error_message") or "scan task already failed"),
        )
        status = "failed"
    return _scan_result(engine, job_id, run_id, status, idempotent_replay=True)


def _scan_result(
    engine: Any,
    trigger_job_id: str,
    run_id: str,
    status: str,
    *,
    idempotent_replay: bool = False,
) -> ScanDispatchResult:
    with engine.begin() as conn:
        counts = conn.execute(
            text(
                """
                SELECT COUNT(*) AS task_count,
                       SUM(CASE WHEN status IN ('completed', 'succeeded') THEN 1 ELSE 0 END) AS completed_count,
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                       SUM(CASE WHEN status = 'failed' AND error_code LIKE '%BLOCK%' THEN 1 ELSE 0 END) AS blocked_count
                FROM airank_scan_tasks
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().one()
    return ScanDispatchResult(
        run_id=run_id,
        status=status,
        task_count=int(counts["task_count"] or 0),
        completed_count=int(counts["completed_count"] or 0),
        failed_count=int(counts["failed_count"] or 0),
        blocked_count=int(counts["blocked_count"] or 0),
        trigger_job_id=trigger_job_id,
        idempotent_replay=idempotent_replay,
    )


def run_next_mock_scan_job(
    store: InMemoryJobLeaseStore,
    provider: MockAnswerProvider,
    *,
    worker_id: str,
    now: datetime,
) -> AnswerSnapshot | None:
    job = store.claim_next(worker_id, now)
    if job is None:
        return None
    try:
        snapshot = provider.answer(
            job.payload or {},
            tenant_id=job.tenant_id,
            project_id=job.project_id or str((job.payload or {}).get("project_id") or ""),
            task_id=job.id,
            created_at=now,
        )
    except ProviderPayloadError as exc:
        store.fail(job.id, worker_id, now, "FACT_SOURCE_REQUIRED", str(exc))
        raise
    except Exception as exc:
        store.fail(job.id, worker_id, now, "SCAN_PROVIDER_BLOCKED", str(exc))
        raise

    store.succeed(
        job.id,
        worker_id,
        now,
        {
            "snapshot": snapshot.to_record(),
            "citations": [citation.to_record() for citation in snapshot.citations],
        },
    )
    return snapshot

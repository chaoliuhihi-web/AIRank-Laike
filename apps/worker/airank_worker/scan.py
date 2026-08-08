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
    tenant_id: str | None = None,
) -> ScanDispatchResult | None:
    claimed_at = now or utc_now()
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    if database_url:
        engine = create_engine(database_url, pool_pre_ping=True)
        timed_out_jobs = [
            timed_out
            for timed_out in store.sweep_timeouts(
                claimed_at,
                tenant_id=tenant_id,
                job_types={"scan.provider"},
            )
            if timed_out.job_type == "scan.provider"
        ]
        recovered_timeouts: list[ScanDispatchResult] = []
        for timed_out in timed_out_jobs:
            recovered = _recover_timed_out_scan_job(
                engine,
                database_url=database_url,
                job=timed_out,
                finished_at=claimed_at,
            )
            if recovered is not None:
                recovered_timeouts.append(recovered)
        if recovered_timeouts:
            return recovered_timeouts[-1]

    job = store.claim_next(
        worker_id,
        claimed_at,
        job_types={"scan.provider"},
        tenant_id=tenant_id,
    )
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
                SELECT tenant_id, project_id, run_id, provider, collector_surface,
                       status, error_code, error_message
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

        if str(task_row["status"]) in {"completed", "succeeded", "failed", "canceled"}:
            return _replay_terminal_run(
                store,
                worker_id=worker_id,
                job_id=job.id,
                run_id=run_id,
                task_row=dict(task_row),
                engine=engine,
            )
        if str(run_row["status"]) == "canceled":
            error = ScanWorkerError("SCAN_RUN_CANCELED", "scan run was canceled before task execution")
            store.fail(job.id, worker_id, utc_now(), error.code, error.message)
            raise error

        claimed_task = conn.execute(
            text(
                """
                UPDATE airank_scan_tasks
                SET status = 'running',
                    attempt_count = GREATEST(attempt_count, :attempt_count),
                    started_at = COALESCE(started_at, :started_at),
                    updated_at = :started_at
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id = :task_id
                  AND status = 'queued'
                """
            ),
            {
                "tenant_id": job.tenant_id,
                "project_id": project_id,
                "task_id": task_id,
                "attempt_count": job.attempt_count,
                "started_at": claimed_at,
            },
        ).rowcount
        if claimed_task == 1:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_scan_task_attempts (
                      id, tenant_id, project_id, run_id, task_id, job_id,
                      attempt_number, provider, collector_surface, status,
                      metadata_json, started_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :job_id,
                      :attempt_number, :provider, :collector_surface, 'running',
                      :metadata_json, :started_at, :started_at
                    )
                    """
                ),
                {
                    "id": f"scan_attempt_{uuid4().hex[:12]}",
                    "tenant_id": job.tenant_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "task_id": task_id,
                    "job_id": job.id,
                    "attempt_number": job.attempt_count,
                    "provider": task_row["provider"],
                    "collector_surface": task_row["collector_surface"],
                    "metadata_json": json.dumps(
                        {"worker_id": worker_id, "lease_timeout_seconds": job.timeout_seconds},
                        ensure_ascii=False,
                    ),
                    "started_at": claimed_at,
                },
            )
        conn.execute(
            text(
                """
                UPDATE airank_scan_runs
                SET status = 'running',
                    started_at = COALESCE(started_at, :started_at),
                    updated_at = :started_at
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id = :run_id
                  AND status IN ('queued', 'running')
                """
            ),
            {
                "tenant_id": job.tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "started_at": claimed_at,
            },
        )

    if claimed_task != 1:
        # A requeued job whose task is still running has an unknown external-call
        # outcome. Never replay it automatically: preserve one immutable failure
        # sample for this slot only, leaving completed sibling slots untouched.
        _fail_unpersisted_scan_task(
            engine,
            tenant_id=job.tenant_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            job_id=job.id,
            attempt_number=job.attempt_count,
            attempt_status="suppressed",
            finished_at=utc_now(),
            error_code="SCAN_TASK_LEASE_EXPIRED",
            error_message=(
                "The scan task lease expired before durable evidence persistence. "
                "Automatic replay was suppressed to prevent duplicate Provider calls; create a new scan run to retry."
            ),
            capture_mode="worker_task_lease_expired",
        )
        _finalize_run_from_durable_state(database_url, job.tenant_id, project_id, run_id)
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
            only_task_id=task_id,
            worker_job_id=job.id,
            worker_attempt_number=job.attempt_count,
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
        _fail_unpersisted_scan_task(
            engine,
            tenant_id=job.tenant_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            job_id=job.id,
            attempt_number=job.attempt_count,
            attempt_status="failed",
            finished_at=utc_now(),
            error_code=error.code,
            error_message=(
                f"{error.message}. Automatic replay was suppressed because the external-call outcome may be unknown; "
                "create a new scan run to retry."
            ),
            capture_mode="worker_internal_failure",
        )
        try:
            _finalize_run_from_durable_state(database_url, job.tenant_id, project_id, run_id)
        except Exception:
            # The task failure and evidence are already durable. A later worker
            # will aggregate the run after the transient dependency recovers.
            pass
        raise error from exc

    persisted_job = store.get(job.id)
    result_status = "completed" if persisted_job.status.value == "succeeded" else persisted_job.status.value
    return _scan_result(engine, job.id, run_id, result_status)


def _recover_timed_out_scan_job(
    engine: Any,
    *,
    database_url: str,
    job: Any,
    finished_at: datetime,
) -> ScanDispatchResult | None:
    payload = job.payload if isinstance(job.payload, Mapping) else {}
    run_id = str(payload.get("run_id") or "")
    task_id = str(payload.get("scan_task_id") or "")
    project_id = str(payload.get("project_id") or job.project_id or "")
    if not run_id or not task_id or not project_id:
        return None
    with engine.begin() as conn:
        scope = conn.execute(
            text(
                """
                SELECT t.status AS task_status, r.status AS run_status
                FROM airank_scan_tasks t
                JOIN airank_scan_runs r
                  ON r.tenant_id = t.tenant_id AND r.id = t.run_id
                WHERE t.tenant_id = :tenant_id
                  AND t.project_id = :project_id
                  AND t.run_id = :run_id
                  AND t.id = :task_id
                """
            ),
            {
                "tenant_id": job.tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "task_id": task_id,
            },
        ).mappings().first()
    if scope is None or str(scope["task_status"]) != "running":
        return None

    _fail_unpersisted_scan_task(
        engine,
        tenant_id=job.tenant_id,
        project_id=project_id,
        run_id=run_id,
        task_id=task_id,
        job_id=job.id,
        attempt_number=job.attempt_count,
        attempt_status="unknown",
        finished_at=finished_at,
        error_code="SCAN_TASK_LEASE_EXPIRED",
        error_message=(
            "The scan task worker timed out before durable evidence persistence. "
            "Automatic replay was suppressed to prevent duplicate Provider calls; create a new scan run to retry."
        ),
        capture_mode="worker_task_timeout",
    )
    _finalize_run_from_durable_state(database_url, job.tenant_id, project_id, run_id)
    return _scan_result(engine, job.id, run_id, "failed")


def _fail_unpersisted_scan_task(
    engine: Any,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    task_id: str,
    job_id: str,
    attempt_number: int,
    attempt_status: str,
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
                  AND t.id = :task_id
                  AND t.status IN ('queued', 'running')
                  AND s.id IS NULL
                ORDER BY t.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "task_id": task_id},
        ).mappings().all()

        answer_snapshot_id: str | None = None
        evidence_snapshot_id: str | None = None
        for task in task_rows:
            snapshot_id = f"snap_{uuid4().hex[:12]}"
            evidence_id = f"evidence_{uuid4().hex[:12]}"
            answer_snapshot_id = snapshot_id
            evidence_snapshot_id = evidence_id
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
                UPDATE airank_scan_task_attempts
                SET status = 'unknown',
                    error_code = :error_code,
                    error_message = :error_message,
                    completed_at = :finished_at
                WHERE tenant_id = :tenant_id
                  AND task_id = :task_id
                  AND status = 'running'
                """
            ),
            {
                "tenant_id": tenant_id,
                "task_id": task_id,
                "error_code": error_code,
                "error_message": error_message,
                "finished_at": finished_at,
            },
        )
        attempt_update = conn.execute(
            text(
                """
                UPDATE airank_scan_task_attempts
                SET status = :status,
                    answer_snapshot_id = :answer_snapshot_id,
                    evidence_snapshot_id = :evidence_snapshot_id,
                    error_code = :error_code,
                    error_message = :error_message,
                    metadata_json = :metadata_json,
                    completed_at = :finished_at
                WHERE tenant_id = :tenant_id
                  AND task_id = :task_id
                  AND job_id = :job_id
                  AND attempt_number = :attempt_number
                """
            ),
            {
                "tenant_id": tenant_id,
                "task_id": task_id,
                "job_id": job_id,
                "attempt_number": attempt_number,
                "status": attempt_status,
                "answer_snapshot_id": answer_snapshot_id,
                "evidence_snapshot_id": evidence_snapshot_id,
                "error_code": error_code,
                "error_message": error_message,
                "metadata_json": json.dumps(
                    {
                        "capture_mode": capture_mode,
                        "automatic_replay_suppressed": True,
                        "provider_response_available": False,
                    },
                    ensure_ascii=False,
                ),
                "finished_at": finished_at,
            },
        )
        if attempt_update.rowcount == 0 and task_rows:
            task = task_rows[0]
            conn.execute(
                text(
                    """
                    INSERT INTO airank_scan_task_attempts (
                      id, tenant_id, project_id, run_id, task_id, job_id,
                      attempt_number, provider, collector_surface, status,
                      answer_snapshot_id, evidence_snapshot_id,
                      error_code, error_message, metadata_json,
                      started_at, completed_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :job_id,
                      :attempt_number, :provider, :collector_surface, :status,
                      :answer_snapshot_id, :evidence_snapshot_id,
                      :error_code, :error_message, :metadata_json,
                      :finished_at, :finished_at, :finished_at
                    )
                    """
                ),
                {
                    "id": f"scan_attempt_{uuid4().hex[:12]}",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "task_id": task_id,
                    "job_id": job_id,
                    "attempt_number": attempt_number,
                    "provider": task["provider"],
                    "collector_surface": task["collector_surface"],
                    "status": attempt_status,
                    "answer_snapshot_id": answer_snapshot_id,
                    "evidence_snapshot_id": evidence_snapshot_id,
                    "error_code": error_code,
                    "error_message": error_message,
                    "metadata_json": json.dumps(
                        {
                            "capture_mode": capture_mode,
                            "automatic_replay_suppressed": True,
                            "provider_response_available": False,
                        },
                        ensure_ascii=False,
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
                  AND id = :task_id
                  AND status IN ('queued', 'running')
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "task_id": task_id,
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
                  AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.scan_task_id')) = :task_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "task_id": task_id,
                "finished_at": finished_at,
                "error_code": error_code,
                "error_message": error_message,
            },
        )


def _finalize_run_from_durable_state(
    database_url: str,
    tenant_id: str,
    project_id: str,
    run_id: str,
) -> dict[str, Any]:
    from apps.api import main as api_main

    project = api_main.get_mysql_project(tenant_id, project_id)
    run = api_main.MySQLScanRepository(database_url).get_run(tenant_id, run_id)
    competitors = api_main.list_mysql_project_competitors(tenant_id, project_id)
    question_ids = set(run.question_scope.question_ids)
    questions = [
        question
        for question in api_main.list_mysql_project_questions(tenant_id, project_id)
        if question.question_id in question_ids
    ]
    return api_main.finalize_mysql_scan_run_if_terminal(tenant_id, project, competitors, questions, run)


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

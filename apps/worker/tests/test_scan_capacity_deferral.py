from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import create_engine, text

from apps.worker.airank_worker.scan import _defer_preflight_scan_task


NOW = datetime(2026, 8, 9, 15, 30, tzinfo=timezone.utc)


def test_preflight_capacity_deferral_requeues_without_answer_evidence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_scan_tasks (
                  id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, run_id TEXT,
                  status TEXT, scheduled_at DATETIME, started_at DATETIME,
                  finished_at DATETIME, updated_at DATETIME, error_code TEXT,
                  error_message TEXT, response_meta_json TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_scan_task_attempts (
                  tenant_id TEXT, task_id TEXT, job_id TEXT, attempt_number INTEGER,
                  status TEXT, error_code TEXT, error_message TEXT,
                  metadata_json TEXT, completed_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_scan_tasks VALUES (
                  'task-1', 'tenant-1', 'project-1', 'run-1', 'running', :now,
                  :now, NULL, :now, NULL, NULL, NULL
                )
                """
            ),
            {"now": NOW},
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_scan_task_attempts VALUES (
                  'tenant-1', 'task-1', 'job-1', 1, 'running', NULL, NULL, NULL, NULL
                )
                """
            )
        )

    retry_at = NOW + timedelta(seconds=5)
    _defer_preflight_scan_task(
        engine,
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        job_id="job-1",
        attempt_number=1,
        finished_at=NOW,
        retry_at=retry_at,
        error_code="PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED",
        error_message="provider distributed concurrency limit is reached",
    )

    with engine.begin() as conn:
        task = conn.execute(text("SELECT * FROM airank_scan_tasks")).mappings().one()
        attempt = conn.execute(text("SELECT * FROM airank_scan_task_attempts")).mappings().one()

    assert task["status"] == "queued"
    assert task["error_code"] is None
    assert task["response_meta_json"] is None
    assert attempt["status"] == "deferred"
    assert attempt["error_code"] == "PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED"
    assert json.loads(attempt["metadata_json"])["provider_request_sent"] is False

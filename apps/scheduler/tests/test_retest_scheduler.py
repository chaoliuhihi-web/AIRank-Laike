from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import text

from airank_scheduler.retest import MySQLRetestScheduler


NOW = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)


def build_scheduler() -> MySQLRetestScheduler:
    scheduler = MySQLRetestScheduler(
        "sqlite+pysqlite:///:memory:",
        tenant_id="tenant_1",
        project_id="project_1",
        scheduler_id="scheduler-test",
    )
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_scan_runs (
                  id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL, name VARCHAR(255),
                  run_type VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
                  provider_scope_json TEXT, question_scope_json TEXT,
                  model_route_snapshot TEXT, metrics_json TEXT,
                  created_by VARCHAR(64), created_at DATETIME NOT NULL,
                  updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_scan_tasks (
                  id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL, run_id VARCHAR(64) NOT NULL,
                  question_id VARCHAR(64) NOT NULL, provider VARCHAR(64) NOT NULL,
                  cohort_type VARCHAR(32) NOT NULL, prompt_version_id VARCHAR(64) NOT NULL,
                  sample_index INT NOT NULL, session_id VARCHAR(96) NOT NULL,
                  collector_surface VARCHAR(32) NOT NULL, evidence_level VARCHAR(64) NOT NULL,
                  status VARCHAR(32) NOT NULL, attempt_count INT NOT NULL,
                  scheduled_at DATETIME, request_json TEXT,
                  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_async_jobs (
                  id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64), job_type VARCHAR(64) NOT NULL,
                  status VARCHAR(32) NOT NULL, priority INT NOT NULL,
                  scheduled_at DATETIME NOT NULL, payload_json TEXT,
                  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_retest_observation_windows (
                  id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL, package_id VARCHAR(64) NOT NULL,
                  baseline_run_id VARCHAR(64), window_label VARCHAR(16) NOT NULL,
                  due_at DATETIME NOT NULL, status VARCHAR(32) NOT NULL,
                  compare_run_id VARCHAR(64), result_json TEXT,
                  completed_at DATETIME, created_at DATETIME NOT NULL,
                  updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_audit_events (
                  id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64), actor_user_id VARCHAR(64),
                  event_type VARCHAR(128) NOT NULL, entity_type VARCHAR(128),
                  entity_id VARCHAR(64), trace_id VARCHAR(128), payload_json TEXT,
                  created_at DATETIME NOT NULL
                )
                """
            )
        )
    return scheduler


def seed_baseline(scheduler: MySQLRetestScheduler) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_scan_runs (
                  id, tenant_id, project_id, name, run_type, status,
                  provider_scope_json, question_scope_json, model_route_snapshot,
                  metrics_json, created_by, created_at, updated_at
                ) VALUES (
                  'baseline_1', 'tenant_1', 'project_1', 'baseline', 'baseline', 'completed',
                  :providers, :questions, :routes, '{}', 'tester', :now, :now
                )
                """
            ),
            {
                "providers": json.dumps(["qianwen"]),
                "questions": json.dumps({"mode": "selected", "question_ids": ["question_1"]}),
                "routes": json.dumps({"qianwen": "route_1"}),
                "now": NOW,
            },
        )
        for sample_index in (1, 2):
            request = {
                "run_id": "baseline_1",
                "scan_task_id": f"baseline_task_{sample_index}",
                "project_id": "project_1",
                "question_id": "question_1",
                "question_text": "入队时冻结的问题文本",
                "provider": "qianwen",
                "cohort_type": "blind",
                "prompt_version_id": "prompt_v1",
                "sample_index": sample_index,
                "session_id": f"baseline_session_{sample_index}",
                "collector_surface": "api",
                "evidence_level": "provider_api",
            }
            conn.execute(
                text(
                    """
                    INSERT INTO airank_scan_tasks (
                      id, tenant_id, project_id, run_id, question_id, provider,
                      cohort_type, prompt_version_id, sample_index, session_id,
                      collector_surface, evidence_level, status, attempt_count,
                      scheduled_at, request_json, created_at, updated_at
                    ) VALUES (
                      :id, 'tenant_1', 'project_1', 'baseline_1', 'question_1', 'qianwen',
                      'blind', 'prompt_v1', :sample_index, :session_id,
                      'api', 'provider_api', 'completed', 1,
                      :now, :request_json, :now, :now
                    )
                    """
                ),
                {
                    "id": f"baseline_task_{sample_index}",
                    "sample_index": sample_index,
                    "session_id": f"baseline_session_{sample_index}",
                    "request_json": json.dumps(request, ensure_ascii=False),
                    "now": NOW,
                },
            )


def seed_window(
    scheduler: MySQLRetestScheduler,
    *,
    window_id: str,
    label: str,
    due_at: datetime,
    tenant_id: str = "tenant_1",
    project_id: str = "project_1",
) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_retest_observation_windows (
                  id, tenant_id, project_id, package_id, baseline_run_id,
                  window_label, due_at, status, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, 'package_1', 'baseline_1',
                  :label, :due_at, 'scheduled', :now, :now
                )
                """
            ),
            {
                "id": window_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "label": label,
                "due_at": due_at,
                "now": NOW,
            },
        )


def test_scheduler_records_t0_and_clones_frozen_retest_contract_idempotently() -> None:
    scheduler = build_scheduler()
    seed_baseline(scheduler)
    seed_window(scheduler, window_id="window_t0", label="T0", due_at=NOW - timedelta(minutes=2))
    seed_window(scheduler, window_id="window_t7", label="T+7", due_at=NOW - timedelta(minutes=1))

    preview = scheduler.preview(NOW)
    records = scheduler.dispatch_due(now=NOW, limit=10)
    replay = scheduler.dispatch_due(now=NOW, limit=10)

    assert preview.due_window_count == 2
    assert [item.action for item in records] == ["baseline_recorded", "scan_dispatched"]
    assert replay == []
    compare_run_id = records[1].compare_run_id
    assert compare_run_id
    with scheduler.engine.begin() as conn:
        t0 = conn.execute(text("SELECT * FROM airank_retest_observation_windows WHERE id='window_t0'")).mappings().one()
        t7 = conn.execute(text("SELECT * FROM airank_retest_observation_windows WHERE id='window_t7'")).mappings().one()
        tasks = conn.execute(
            text("SELECT * FROM airank_scan_tasks WHERE run_id=:run_id ORDER BY sample_index"),
            {"run_id": compare_run_id},
        ).mappings().all()
        jobs = conn.execute(
            text("SELECT * FROM airank_async_jobs WHERE project_id='project_1' ORDER BY id")
        ).mappings().all()
        audits = conn.execute(text("SELECT event_type FROM airank_audit_events ORDER BY event_type")).scalars().all()
    assert t0["status"] == "completed"
    assert t0["compare_run_id"] == "baseline_1"
    assert t7["status"] == "sampling"
    assert t7["compare_run_id"] == compare_run_id
    assert len(tasks) == 2 and len(jobs) == 2
    assert all(json.loads(task["request_json"])["question_text"] == "入队时冻结的问题文本" for task in tasks)
    assert {task["session_id"] for task in tasks}.isdisjoint({"baseline_session_1", "baseline_session_2"})
    assert audits == ["retest.baseline_recorded", "retest.scan_dispatched"]

    with scheduler.engine.begin() as conn:
        conn.execute(
            text("UPDATE airank_scan_runs SET status='completed' WHERE id=:run_id"),
            {"run_id": compare_run_id},
        )
    ready = scheduler.ready_to_finalize(limit=10)
    assert ready == [
        {
            "window_id": "window_t7",
            "tenant_id": "tenant_1",
            "project_id": "project_1",
            "compare_run_id": compare_run_id,
            "run_status": "completed",
        }
    ]


def test_scheduler_blocks_retest_when_frozen_prompt_is_missing() -> None:
    scheduler = build_scheduler()
    seed_baseline(scheduler)
    with scheduler.engine.begin() as conn:
        conn.execute(
            text("UPDATE airank_scan_tasks SET request_json='{}' WHERE run_id='baseline_1'")
        )
    seed_window(scheduler, window_id="window_missing", label="T+7", due_at=NOW)

    record = scheduler.dispatch_due(now=NOW, limit=1)[0]

    assert record.action == "blocked"
    assert record.error_code == "RETEST_FROZEN_PROMPT_MISSING"
    with scheduler.engine.begin() as conn:
        row = conn.execute(
            text("SELECT status, result_json FROM airank_retest_observation_windows WHERE id='window_missing'")
        ).mappings().one()
        compare_count = conn.execute(
            text("SELECT COUNT(*) FROM airank_scan_runs WHERE run_type='retest'")
        ).scalar_one()
    assert row["status"] == "blocked"
    assert json.loads(row["result_json"])["error_code"] == "RETEST_FROZEN_PROMPT_MISSING"
    assert compare_count == 0

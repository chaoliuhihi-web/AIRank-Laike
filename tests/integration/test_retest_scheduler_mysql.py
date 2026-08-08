from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from airank_scheduler import MySQLRetestScheduler
from apps.api.main import (
    BuyerQuestionCreateRequest,
    MySQLProjectRepository,
    MySQLScanRepository,
    ProjectCreateRequest,
    ScanRunCreateRequest,
)
from apps.api.retest_routes import CompleteRetestRequest, MySQLRetestRepository
from airank_worker.lease import MySQLJobLeaseStore


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.columns
                WHERE table_schema=DATABASE() AND column_name='tenant_id'
                  AND table_name LIKE 'airank\\_%'
                ORDER BY table_name DESC
                """
            )
        ).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        try:
            for table_name in tables:
                conn.execute(
                    text(f"DELETE FROM `{table_name}` WHERE tenant_id=:tenant_id"),
                    {"tenant_id": tenant_id},
                )
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def test_real_mysql_scheduler_clones_frozen_contract_and_scopes_queue() -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real integration checks")
    tenant_id = f"tenant_retest_scheduler_{uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    engine = create_engine(database_url(), pool_pre_ping=True)
    projects = MySQLProjectRepository(database_url())
    scans = MySQLScanRepository(database_url())

    try:
        project = projects.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://example.com/retest-scheduler",
                brand_name_hint="AIRank Scheduler QA",
                industry_hint="B2B SaaS",
            ),
        )
        question = projects.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="入队时不可变的复测问题？",
                status="confirmed",
                source="manual",
                recommended_providers=["qianwen"],
            ),
        )
        baseline = scans.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                repetitions=2,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        baseline_tasks = scans.list_tasks(tenant_id, baseline.run_id)
        with engine.begin() as conn:
            baseline_request_rows = conn.execute(
                text(
                    """
                    SELECT request_json FROM airank_scan_tasks
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    ORDER BY sample_index
                    """
                ),
                {"tenant_id": tenant_id, "run_id": baseline.run_id},
            ).scalars().all()
        frozen_questions = [
            json.loads(value)["question_text"] if isinstance(value, str) else value["question_text"]
            for value in baseline_request_rows
        ]
        package_id = f"package_scheduler_{uuid4().hex[:12]}"
        window_id = f"window_scheduler_{uuid4().hex[:12]}"
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_buyer_questions
                    SET question_text='后来被编辑的问题文本', updated_at=:now
                    WHERE tenant_id=:tenant_id AND id=:question_id
                    """
                ),
                {"now": now, "tenant_id": tenant_id, "question_id": question.question_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='completed', finished_at=:now, updated_at=:now
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {"now": now, "tenant_id": tenant_id, "run_id": baseline.run_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_runs
                    SET status='completed', finished_at=:now, updated_at=:now
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {"now": now, "tenant_id": tenant_id, "run_id": baseline.run_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs
                    SET status='succeeded', finished_at=:now, updated_at=:now
                    WHERE tenant_id=:tenant_id
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id'))=:run_id
                    """
                ),
                {"now": now, "tenant_id": tenant_id, "run_id": baseline.run_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_publish_packages (
                      id, tenant_id, project_id, package_type, channel, status,
                      published_url, published_at, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'content_asset', 'export', 'published',
                      'https://example.com/retest-result', :now, :now, :now
                    )
                    """
                ),
                {
                    "id": package_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "now": now,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_retest_observation_windows (
                      id, tenant_id, project_id, package_id, baseline_run_id,
                      window_label, due_at, status, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :package_id, :baseline_run_id,
                      'T+7', :due_at, 'scheduled', :now, :now
                    )
                    """
                ),
                {
                    "id": window_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "package_id": package_id,
                    "baseline_run_id": baseline.run_id,
                    "due_at": now - timedelta(seconds=1),
                    "now": now,
                },
            )

        scheduler = MySQLRetestScheduler(
            database_url(),
            tenant_id=tenant_id,
            project_id=project.project_id,
            window_id=window_id,
            scheduler_id="integration-scheduler",
        )
        preview = scheduler.preview(now)
        record = scheduler.dispatch_due(now=now, limit=1)[0]

        assert preview.due_window_count == 1
        assert record.action == "scan_dispatched"
        assert record.task_count == len(baseline_tasks) == 2
        assert record.compare_run_id
        with engine.begin() as conn:
            cloned = conn.execute(
                text(
                    """
                    SELECT request_json, session_id FROM airank_scan_tasks
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    ORDER BY sample_index
                    """
                ),
                {"tenant_id": tenant_id, "run_id": record.compare_run_id},
            ).mappings().all()
            window = conn.execute(
                text(
                    "SELECT status, compare_run_id FROM airank_retest_observation_windows WHERE tenant_id=:tenant_id AND id=:id"
                ),
                {"tenant_id": tenant_id, "id": window_id},
            ).mappings().one()
            audit_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_audit_events
                    WHERE tenant_id=:tenant_id AND entity_id=:window_id
                      AND event_type='retest.scan_dispatched'
                    """
                ),
                {"tenant_id": tenant_id, "window_id": window_id},
            ).scalar_one()
        assert window["status"] == "sampling"
        assert window["compare_run_id"] == record.compare_run_id
        cloned_questions = [
            json.loads(row["request_json"])["question_text"]
            if isinstance(row["request_json"], str)
            else row["request_json"]["question_text"]
            for row in cloned
        ]
        assert cloned_questions == frozen_questions
        assert all(value != "后来被编辑的问题文本" for value in cloned_questions)
        assert {row["session_id"] for row in cloned}.isdisjoint({task.session_id for task in baseline_tasks})
        assert audit_count == 1

        scoped_store = MySQLJobLeaseStore(
            database_url(),
            tenant_id=tenant_id,
            project_id=project.project_id,
        )
        queue = scoped_store.inspect_claimable(
            now + timedelta(seconds=1), job_types={"scan.provider"}
        )
        assert queue.eligible_count == 2
        assert queue.counts_by_job_type == {"scan.provider": 2}
        assert scheduler.dispatch_due(now=now, limit=1) == []

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='failed', error_code='SCHEDULER_TEST_FAILURE',
                        error_message='intentional integration failure',
                        finished_at=:finished_at, updated_at=:finished_at
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {
                    "finished_at": now + timedelta(seconds=2),
                    "tenant_id": tenant_id,
                    "run_id": record.compare_run_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_runs
                    SET status='failed', finished_at=:finished_at, updated_at=:finished_at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {
                    "finished_at": now + timedelta(seconds=2),
                    "tenant_id": tenant_id,
                    "run_id": record.compare_run_id,
                },
            )
        ready = scheduler.ready_to_finalize(limit=1)
        assert ready[0]["window_id"] == window_id
        result = MySQLRetestRepository(database_url()).complete_window(
            tenant_id,
            window_id,
            CompleteRetestRequest(
                compare_run_id=record.compare_run_id,
                completed_by="integration-scheduler",
            ),
        )
        assert result.report_status == "quality_blocked"
        assert result.attribution_policy == "observational_non_causal.v1"
        with engine.begin() as conn:
            final_window = conn.execute(
                text(
                    "SELECT status, compare_run_id FROM airank_retest_observation_windows WHERE tenant_id=:tenant_id AND id=:id"
                ),
                {"tenant_id": tenant_id, "id": window_id},
            ).mappings().one()
            report_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_reports WHERE tenant_id=:tenant_id AND id=:report_id"
                ),
                {"tenant_id": tenant_id, "report_id": result.report_id},
            ).scalar_one()
        assert final_window["status"] == "completed_with_limitations"
        assert final_window["compare_run_id"] == record.compare_run_id
        assert report_count == 1
    finally:
        cleanup_tenant(engine, tenant_id)
        engine.dispose()

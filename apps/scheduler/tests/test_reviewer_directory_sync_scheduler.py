from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import text

from airank_scheduler.reviewer_directory_sync import (
    MySQLReviewerDirectorySyncScheduler,
)


NOW = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)


def build_scheduler() -> MySQLReviewerDirectorySyncScheduler:
    scheduler = MySQLReviewerDirectorySyncScheduler(
        "sqlite+pysqlite:///:memory:",
        tenant_id="tenant_1",
        project_id="project_1",
        scheduler_id="review-directory-scheduler-test",
    )
    with scheduler.engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE airank_evidence_review_team_sync_bindings (
              id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
              project_id VARCHAR(64) NOT NULL, team_id VARCHAR(64) NOT NULL,
              reviewer_role VARCHAR(32) NOT NULL, external_group_id VARCHAR(128) NOT NULL,
              status VARCHAR(32) NOT NULL, sync_enabled INT NOT NULL,
              sync_interval_minutes INT NOT NULL, next_sync_at DATETIME NOT NULL,
              version INT NOT NULL, updated_by VARCHAR(128), updated_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_async_jobs (
              id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
              project_id VARCHAR(64), job_type VARCHAR(64) NOT NULL,
              status VARCHAR(32) NOT NULL, priority INT NOT NULL,
              scheduled_at DATETIME NOT NULL, timeout_seconds INT NOT NULL,
              attempt_count INT NOT NULL, max_attempts INT NOT NULL,
              payload_json TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_audit_events (
              id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
              project_id VARCHAR(64), actor_user_id VARCHAR(128),
              event_type VARCHAR(128) NOT NULL, entity_type VARCHAR(128),
              entity_id VARCHAR(64), payload_json TEXT, created_at DATETIME NOT NULL
            )
        """))
    return scheduler


def seed_binding(
    scheduler: MySQLReviewerDirectorySyncScheduler,
    *,
    binding_id: str,
    due_at: datetime,
    enabled: bool = True,
) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO airank_evidence_review_team_sync_bindings (
              id, tenant_id, project_id, team_id, reviewer_role,
              external_group_id, status, sync_enabled, sync_interval_minutes,
              next_sync_at, version, updated_by, updated_at
            ) VALUES (
              :id, 'tenant_1', 'project_1', 'team_1', 'secondary', '42',
              'active', :enabled, 60, :due_at, 3, 'tester', :due_at
            )
        """), {"id": binding_id, "enabled": int(enabled), "due_at": due_at})


def test_scheduler_dispatches_scoped_directory_job_once_and_advances_due_time() -> None:
    scheduler = build_scheduler()
    seed_binding(scheduler, binding_id="binding_due", due_at=NOW - timedelta(minutes=5))

    assert scheduler.preview(NOW).to_record() == {
        "due_binding_count": 1,
        "next_binding_id": "binding_due",
    }
    first = scheduler.dispatch_due(now=NOW, limit=10)
    replay = scheduler.dispatch_due(now=NOW, limit=10)

    assert len(first) == 1
    assert replay == []
    with scheduler.engine.begin() as conn:
        binding = conn.execute(text("SELECT * FROM airank_evidence_review_team_sync_bindings")).mappings().one()
        job = conn.execute(text("SELECT * FROM airank_async_jobs")).mappings().one()
        audit = conn.execute(text("SELECT * FROM airank_audit_events")).mappings().one()
    next_sync_at = binding["next_sync_at"]
    if isinstance(next_sync_at, str):
        next_sync_at = datetime.fromisoformat(next_sync_at)
    assert next_sync_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=60)
    payload = json.loads(job["payload_json"])
    assert job["job_type"] == "reviewer.directory.sync"
    assert job["max_attempts"] == 1
    assert payload["contract_version"] == "airank.reviewer-directory-sync.v1"
    assert payload["binding_version"] == 3
    assert "token" not in json.dumps(payload).lower()
    assert audit["event_type"] == "evidence_review.yudao_sync_dispatched"


def test_scheduler_skips_disabled_and_future_bindings() -> None:
    scheduler = build_scheduler()
    seed_binding(scheduler, binding_id="binding_disabled", due_at=NOW, enabled=False)
    seed_binding(scheduler, binding_id="binding_future", due_at=NOW + timedelta(minutes=1))

    assert scheduler.preview(NOW).due_binding_count == 0
    assert scheduler.dispatch_due(now=NOW, limit=10) == []


def test_scheduler_project_scope_requires_tenant() -> None:
    try:
        MySQLReviewerDirectorySyncScheduler(
            "sqlite+pysqlite:///:memory:", project_id="project_1"
        )
    except ValueError as exc:
        assert str(exc) == "project scope requires tenant scope"
    else:
        raise AssertionError("project-only directory sync scope must fail closed")

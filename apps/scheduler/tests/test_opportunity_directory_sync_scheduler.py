from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import text

from airank_scheduler.opportunity_directory_sync import (
    MySQLOpportunityDirectorySyncScheduler,
)


NOW = datetime(2026, 8, 9, 11, 30, tzinfo=timezone.utc)


def build_scheduler() -> MySQLOpportunityDirectorySyncScheduler:
    scheduler = MySQLOpportunityDirectorySyncScheduler(
        "sqlite+pysqlite:///:memory:",
        tenant_id="tenant_1",
        project_id="project_1",
        scheduler_id="opportunity-directory-scheduler-test",
    )
    with scheduler.engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE airank_opportunity_action_team_sync_bindings (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
              project_id TEXT NOT NULL, team_id TEXT NOT NULL,
              external_group_id TEXT NOT NULL, status TEXT NOT NULL,
              sync_enabled INTEGER NOT NULL, sync_interval_minutes INTEGER NOT NULL,
              next_sync_at DATETIME, version INTEGER NOT NULL,
              updated_by TEXT, updated_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_async_jobs (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT,
              job_type TEXT NOT NULL, status TEXT NOT NULL, priority INTEGER NOT NULL,
              scheduled_at DATETIME NOT NULL, timeout_seconds INTEGER NOT NULL,
              attempt_count INTEGER NOT NULL, max_attempts INTEGER NOT NULL,
              payload_json TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_audit_events (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT,
              actor_user_id TEXT, event_type TEXT NOT NULL, entity_type TEXT,
              entity_id TEXT, payload_json TEXT, created_at DATETIME NOT NULL
            )
        """))
    return scheduler


def seed_binding(
    scheduler: MySQLOpportunityDirectorySyncScheduler,
    *,
    binding_id: str,
    due_at: datetime,
    enabled: bool = True,
) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO airank_opportunity_action_team_sync_bindings (
                  id, tenant_id, project_id, team_id, external_group_id,
                  status, sync_enabled, sync_interval_minutes, next_sync_at,
                  version, updated_by, updated_at
                ) VALUES (
                  :id, 'tenant_1', 'project_1', 'team_1', '42', 'active',
                  :enabled, 60, :due_at, 3, 'tester', :due_at
                )
            """),
            {"id": binding_id, "enabled": int(enabled), "due_at": due_at},
        )


def test_scheduler_dispatches_scoped_job_and_contains_no_credentials() -> None:
    scheduler = build_scheduler()
    seed_binding(
        scheduler,
        binding_id="binding_due",
        due_at=NOW - timedelta(minutes=5),
    )

    assert scheduler.preview(NOW).due_binding_count == 1
    dispatched = scheduler.dispatch_due(now=NOW, limit=10)
    assert len(dispatched) == 1
    assert scheduler.dispatch_due(now=NOW, limit=10) == []
    with scheduler.engine.begin() as conn:
        job = conn.execute(text("SELECT * FROM airank_async_jobs")).mappings().one()
        audit = conn.execute(text("SELECT * FROM airank_audit_events")).mappings().one()
    payload = json.loads(job["payload_json"])
    assert job["job_type"] == "opportunity.directory.sync"
    assert payload["contract_version"] == "airank.opportunity-action-directory-sync.v1"
    assert payload["binding_version"] == 3
    assert not {"token", "authorization", "credential", "secret"}.intersection(payload)
    assert audit["event_type"] == "opportunity_action.directory_sync_dispatched"


def test_scheduler_skips_disabled_or_future_and_requires_bounded_scope() -> None:
    scheduler = build_scheduler()
    seed_binding(scheduler, binding_id="disabled", due_at=NOW, enabled=False)
    seed_binding(
        scheduler,
        binding_id="future",
        due_at=NOW + timedelta(minutes=1),
    )
    assert scheduler.preview(NOW).due_binding_count == 0
    assert scheduler.dispatch_due(now=NOW) == []
    try:
        MySQLOpportunityDirectorySyncScheduler(
            "sqlite+pysqlite:///:memory:", project_id="project_1"
        )
    except ValueError as exc:
        assert str(exc) == "project scope requires tenant scope"
    else:
        raise AssertionError("project-only opportunity directory scope must fail closed")

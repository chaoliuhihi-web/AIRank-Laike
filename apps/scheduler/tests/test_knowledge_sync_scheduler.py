from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import text

from airank_scheduler.knowledge_sync import MySQLKnowledgeSyncScheduler


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def build_scheduler() -> MySQLKnowledgeSyncScheduler:
    scheduler = MySQLKnowledgeSyncScheduler(
        "sqlite+pysqlite:///:memory:",
        tenant_id="tenant_1",
        project_id="project_1",
        scheduler_id="knowledge-scheduler-test",
    )
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_knowledge_sync_policies (
                  id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL, current_source_id VARCHAR(64) NOT NULL,
                  source_uri VARCHAR(2048) NOT NULL, interval_hours INT NOT NULL,
                  enabled INT NOT NULL, next_run_at DATETIME NOT NULL,
                  updated_by VARCHAR(64), updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_knowledge_sync_runs (
                  id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL, policy_id VARCHAR(64) NOT NULL,
                  source_before_id VARCHAR(64) NOT NULL, job_id VARCHAR(64) NOT NULL,
                  idempotency_key VARCHAR(160) NOT NULL, status VARCHAR(32) NOT NULL,
                  requested_url VARCHAR(2048) NOT NULL, scheduled_at DATETIME NOT NULL,
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
                  scheduled_at DATETIME NOT NULL, timeout_seconds INT NOT NULL,
                  attempt_count INT NOT NULL, max_attempts INT NOT NULL,
                  payload_json TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
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
                  entity_id VARCHAR(64), payload_json TEXT, created_at DATETIME NOT NULL
                )
                """
            )
        )
    return scheduler


def seed_policy(
    scheduler: MySQLKnowledgeSyncScheduler,
    *,
    policy_id: str,
    due_at: datetime,
    enabled: bool = True,
) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_knowledge_sync_policies (
                  id, tenant_id, project_id, current_source_id, source_uri,
                  interval_hours, enabled, next_run_at, updated_by, updated_at
                ) VALUES (
                  :id, 'tenant_1', 'project_1', 'source_1',
                  'https://example.com/facts', 24, :enabled, :due_at, 'tester', :due_at
                )
                """
            ),
            {"id": policy_id, "enabled": 1 if enabled else 0, "due_at": due_at},
        )


def test_scheduler_dispatches_one_durable_sync_job_and_advances_schedule() -> None:
    scheduler = build_scheduler()
    seed_policy(scheduler, policy_id="policy_due", due_at=NOW - timedelta(minutes=5))

    preview = scheduler.preview(NOW)
    first = scheduler.dispatch_due(now=NOW, limit=10)
    replay = scheduler.dispatch_due(now=NOW, limit=10)

    assert preview.to_record() == {"due_policy_count": 1, "next_policy_id": "policy_due"}
    assert len(first) == 1
    assert replay == []
    with scheduler.engine.begin() as conn:
        policy = conn.execute(
            text("SELECT * FROM airank_knowledge_sync_policies WHERE id='policy_due'")
        ).mappings().one()
        run = conn.execute(text("SELECT * FROM airank_knowledge_sync_runs")).mappings().one()
        job = conn.execute(text("SELECT * FROM airank_async_jobs")).mappings().one()
        audit = conn.execute(text("SELECT * FROM airank_audit_events")).mappings().one()
    stored_next_run_at = policy["next_run_at"]
    if isinstance(stored_next_run_at, str):
        stored_next_run_at = datetime.fromisoformat(stored_next_run_at)
    assert stored_next_run_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=24)
    assert run["status"] == "queued"
    assert run["job_id"] == job["id"] == first[0].job_id
    assert job["job_type"] == "knowledge.source.sync"
    assert json.loads(job["payload_json"])["contract_version"] == "airank.knowledge-source-sync.v1"
    assert audit["event_type"] == "knowledge.sync.dispatched"


def test_scheduler_skips_disabled_policy_and_policy_with_active_run() -> None:
    scheduler = build_scheduler()
    seed_policy(scheduler, policy_id="policy_disabled", due_at=NOW, enabled=False)
    seed_policy(scheduler, policy_id="policy_active", due_at=NOW)
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_knowledge_sync_runs (
                  id, tenant_id, project_id, policy_id, source_before_id,
                  job_id, idempotency_key, status, requested_url,
                  scheduled_at, created_at, updated_at
                ) VALUES (
                  'run_active', 'tenant_1', 'project_1', 'policy_active', 'source_1',
                  'job_active', 'active-key', 'running', 'https://example.com/facts',
                  :now, :now, :now
                )
                """
            ),
            {"now": NOW},
        )

    assert scheduler.preview(NOW).due_policy_count == 0
    assert scheduler.dispatch_due(now=NOW, limit=10) == []

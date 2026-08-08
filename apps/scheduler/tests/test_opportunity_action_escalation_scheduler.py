from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import text

from airank_scheduler.opportunity_action_escalation import (
    MySQLOpportunityActionEscalationScheduler,
)


NOW = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)


def build_scheduler() -> MySQLOpportunityActionEscalationScheduler:
    scheduler = MySQLOpportunityActionEscalationScheduler(
        "sqlite+pysqlite:///:memory:",
        tenant_id="tenant_action",
        project_id="project_action",
        scheduler_id="scheduler-action-test",
    )
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_opportunity_actions (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                  project_id TEXT NOT NULL, opportunity_id TEXT NOT NULL,
                  source_kind TEXT NOT NULL, status TEXT NOT NULL,
                  assigned_to TEXT, due_at DATETIME NOT NULL,
                  routing_state TEXT NOT NULL, routing_team_id TEXT,
                  routing_route_version INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_opportunity_action_teams (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                  project_id TEXT NOT NULL, external_sync_state TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_opportunity_action_team_members (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                  team_id TEXT NOT NULL, status TEXT NOT NULL,
                  receives_escalations INTEGER NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_outbox_events (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT,
                  event_type TEXT NOT NULL, aggregate_type TEXT NOT NULL,
                  aggregate_id TEXT NOT NULL, trace_id TEXT, status TEXT NOT NULL,
                  available_at DATETIME NOT NULL, published_at DATETIME,
                  attempt_count INTEGER NOT NULL, payload_json TEXT,
                  error_code TEXT, error_message TEXT,
                  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                )
                """
            )
        )
    return scheduler


def seed_action(
    scheduler: MySQLOpportunityActionEscalationScheduler,
    *,
    action_id: str,
    status: str,
    due_at: datetime,
    assigned_to: str | None = None,
    tenant_id: str = "tenant_action",
    project_id: str = "project_action",
    team_id: str | None = None,
) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_opportunity_actions (
                  id, tenant_id, project_id, opportunity_id, source_kind,
                  status, assigned_to, due_at, routing_state,
                  routing_team_id, routing_route_version
                ) VALUES (
                  :id, :tenant_id, :project_id, :opportunity_id,
                  'brand_visibility', :status, :assigned_to, :due_at,
                  :routing_state, :team_id, :route_version
                )
                """
            ),
            {
                "id": action_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "opportunity_id": "opportunity_" + action_id[-20:],
                "status": status,
                "assigned_to": assigned_to,
                "due_at": due_at,
                "routing_state": "team_routed" if team_id else "unrestricted_legacy",
                "team_id": team_id,
                "route_version": 1 if team_id else None,
            },
        )


def test_opportunity_action_escalation_is_scoped_idempotent_and_truthful() -> None:
    scheduler = build_scheduler()
    team_id = "opportunity_action_team_" + "a" * 20
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO airank_opportunity_action_teams "
                "(id, tenant_id, project_id, external_sync_state) "
                "VALUES (:id, 'tenant_action', 'project_action', 'not_configured')"
            ),
            {"id": team_id},
        )
        conn.execute(
            text(
                "INSERT INTO airank_opportunity_action_team_members "
                "(id, tenant_id, team_id, status, receives_escalations) "
                "VALUES ('member-one', 'tenant_action', :team_id, 'active', 1), "
                "('member-two', 'tenant_action', :team_id, 'active', 0)"
            ),
            {"team_id": team_id},
        )
    seed_action(
        scheduler,
        action_id="opportunity_action_" + "1" * 20,
        status="in_progress",
        due_at=NOW - timedelta(hours=2),
        assigned_to="private-owner",
        team_id=team_id,
    )
    seed_action(
        scheduler,
        action_id="opportunity_action_" + "2" * 20,
        status="evidence_blocked",
        due_at=NOW - timedelta(hours=1),
    )
    seed_action(
        scheduler,
        action_id="opportunity_action_" + "3" * 20,
        status="open",
        due_at=NOW + timedelta(hours=1),
    )
    seed_action(
        scheduler,
        action_id="opportunity_action_" + "4" * 20,
        status="verified_not_observed",
        due_at=NOW - timedelta(days=1),
    )
    seed_action(
        scheduler,
        action_id="opportunity_action_" + "5" * 20,
        status="open",
        due_at=NOW - timedelta(days=1),
        tenant_id="tenant_other",
        project_id="project_other",
    )

    before = scheduler.preview(NOW)
    assert before.overdue_action_count == 2
    assert before.dispatchable_count == 2
    first = scheduler.dispatch_overdue(now=NOW, limit=1)
    second = scheduler.dispatch_overdue(now=NOW, limit=10)
    assert len(first) == 1
    assert len(second) == 1
    assert scheduler.dispatch_overdue(now=NOW, limit=10) == []
    after = scheduler.preview(NOW)
    assert after.pending_event_count == 2
    assert after.dispatchable_count == 0

    with scheduler.engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT aggregate_type, aggregate_id, payload_json "
                "FROM airank_outbox_events ORDER BY aggregate_id"
            )
        ).mappings().all()
    assert len(rows) == 2
    routed = json.loads(str(rows[0]["payload_json"]))
    assert rows[0]["aggregate_type"] == "opportunity_action"
    assert routed["schema_version"] == "airank.opportunity-action-sla-escalation.v1"
    assert routed["eligible_recipient_count"] == 1
    assert routed["delivery_claim"] == "outbox_pending_not_delivered"
    assert routed["effect_claim_allowed"] is False
    assert "assigned_to" not in routed
    legacy = json.loads(str(rows[1]["payload_json"]))
    assert legacy["eligible_recipient_count"] == 0
    assert legacy["external_sync_state"] == "not_configured"


def test_opportunity_action_escalation_rechecks_before_insert() -> None:
    scheduler = build_scheduler()
    action_id = "opportunity_action_" + "6" * 20
    seed_action(
        scheduler,
        action_id=action_id,
        status="open",
        due_at=NOW - timedelta(hours=1),
    )
    original = scheduler._load_candidate_for_update

    def finalize_then_load(conn, expected, checked_at):  # noqa: ANN001
        conn.execute(
            text(
                "UPDATE airank_opportunity_actions SET status='waived' WHERE id=:id"
            ),
            {"id": action_id},
        )
        return original(conn, expected, checked_at)

    scheduler._load_candidate_for_update = finalize_then_load  # type: ignore[method-assign]
    assert scheduler.dispatch_overdue(now=NOW, limit=10) == []
    with scheduler.engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM airank_outbox_events")).scalar_one() == 0


def test_opportunity_action_escalation_project_scope_requires_tenant() -> None:
    try:
        MySQLOpportunityActionEscalationScheduler(
            "sqlite+pysqlite:///:memory:", project_id="project_only"
        )
    except ValueError as exc:
        assert str(exc) == "project scope requires tenant scope"
    else:
        raise AssertionError("project-only opportunity action escalation must fail closed")

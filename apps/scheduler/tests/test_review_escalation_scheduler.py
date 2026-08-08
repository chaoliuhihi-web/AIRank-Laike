from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import text

from airank_scheduler.review_escalation import MySQLReviewEscalationScheduler


NOW = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)


def build_scheduler() -> MySQLReviewEscalationScheduler:
    scheduler = MySQLReviewEscalationScheduler(
        "sqlite+pysqlite:///:memory:",
        tenant_id="tenant_review",
        project_id="project_review",
        scheduler_id="scheduler-review-test",
    )
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_evidence_review_cases (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
                  status TEXT NOT NULL, created_at DATETIME NOT NULL,
                  updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_evidence_review_assignments (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, case_id TEXT NOT NULL,
                  reviewer_role TEXT NOT NULL, assigned_to TEXT NOT NULL,
                  status TEXT NOT NULL, due_at DATETIME NOT NULL,
                  lease_expires_at DATETIME NOT NULL
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


def seed_case(
    scheduler: MySQLReviewEscalationScheduler,
    *,
    case_id: str,
    status: str,
    created_at: datetime,
    updated_at: datetime | None = None,
    tenant_id: str = "tenant_review",
    project_id: str = "project_review",
) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_evidence_review_cases
                  (id, tenant_id, project_id, status, created_at, updated_at)
                VALUES (:id, :tenant_id, :project_id, :status, :created_at, :updated_at)
                """
            ),
            {
                "id": case_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "status": status,
                "created_at": created_at,
                "updated_at": updated_at or created_at,
            },
        )


def seed_assignment(
    scheduler: MySQLReviewEscalationScheduler,
    *,
    assignment_id: str,
    case_id: str,
    role: str,
    due_at: datetime,
    lease_expires_at: datetime,
) -> None:
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_evidence_review_assignments
                  (id, tenant_id, case_id, reviewer_role, assigned_to,
                   status, due_at, lease_expires_at)
                VALUES (:id, 'tenant_review', :case_id, :role, 'reviewer-private',
                        'active', :due_at, :lease_expires_at)
                """
            ),
            {
                "id": assignment_id,
                "case_id": case_id,
                "role": role,
                "due_at": due_at,
                "lease_expires_at": lease_expires_at,
            },
        )


def test_review_escalation_is_scoped_idempotent_and_truthful() -> None:
    scheduler = build_scheduler()
    seed_case(
        scheduler,
        case_id="case_unassigned_overdue",
        status="awaiting_secondary",
        created_at=NOW - timedelta(days=2),
    )
    seed_case(
        scheduler,
        case_id="case_assigned_overdue",
        status="disputed",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(hours=5),
    )
    seed_assignment(
        scheduler,
        assignment_id="assignment_assigned",
        case_id="case_assigned_overdue",
        role="adjudicator",
        due_at=NOW - timedelta(hours=1),
        lease_expires_at=NOW + timedelta(minutes=5),
    )
    seed_case(
        scheduler,
        case_id="case_expired_overdue",
        status="awaiting_secondary",
        created_at=NOW - timedelta(days=3),
    )
    seed_assignment(
        scheduler,
        assignment_id="assignment_expired",
        case_id="case_expired_overdue",
        role="secondary",
        due_at=NOW - timedelta(hours=2),
        lease_expires_at=NOW - timedelta(minutes=1),
    )
    seed_case(
        scheduler,
        case_id="case_not_due",
        status="awaiting_secondary",
        created_at=NOW - timedelta(hours=1),
    )
    seed_case(
        scheduler,
        case_id="case_final",
        status="agreed",
        created_at=NOW - timedelta(days=4),
    )
    seed_case(
        scheduler,
        case_id="case_other_tenant",
        status="awaiting_secondary",
        created_at=NOW - timedelta(days=4),
        tenant_id="tenant_other",
        project_id="project_other",
    )

    preview = scheduler.preview(NOW)
    assert preview.overdue_case_count == 3
    assert preview.pending_event_count == 0
    assert preview.dispatchable_count == 3
    assert preview.next_due_case_id == "case_unassigned_overdue"

    first = scheduler.dispatch_overdue(now=NOW, limit=2)
    second = scheduler.dispatch_overdue(now=NOW, limit=2)
    replay = scheduler.dispatch_overdue(now=NOW, limit=10)
    assert len(first) == 2
    assert len(second) == 1
    assert replay == []
    assert {item.assignment_state for item in [*first, *second]} == {
        "unassigned",
        "assigned",
        "expired",
    }
    assert all(item.outbox_status == "pending" for item in [*first, *second])

    after = scheduler.preview(NOW)
    assert after.overdue_case_count == 3
    assert after.pending_event_count == 3
    assert after.dispatchable_count == 0
    assert after.next_due_case_id is None

    with scheduler.engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT event_type, aggregate_id, payload_json
                FROM airank_outbox_events
                ORDER BY aggregate_id
                """
            )
        ).mappings().all()
    assert len(rows) == 3
    assert {str(row["event_type"]) for row in rows} == {
        "evidence_review.sla_overdue.v1"
    }
    for row in rows:
        payload = json.loads(str(row["payload_json"]))
        assert payload["schema_version"] == "airank.evidence-review-sla-escalation.v1"
        assert payload["delivery_claim"] == "outbox_pending_not_delivered"
        assert "assigned_to" not in payload
        assert "assignment_id" not in payload


def test_review_escalation_project_scope_requires_tenant() -> None:
    try:
        MySQLReviewEscalationScheduler(
            "sqlite+pysqlite:///:memory:", project_id="project_only"
        )
    except ValueError as exc:
        assert str(exc) == "project scope requires tenant scope"
    else:  # pragma: no cover
        raise AssertionError("project-only review escalation scope must fail closed")


def test_review_escalation_rechecks_case_before_persisting() -> None:
    scheduler = build_scheduler()
    seed_case(
        scheduler,
        case_id="case_completed_after_scan",
        status="awaiting_secondary",
        created_at=NOW - timedelta(days=2),
    )
    stale_candidate = scheduler._overdue_candidates(NOW)[0]
    with scheduler.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE airank_evidence_review_cases "
                "SET status='agreed' WHERE id='case_completed_after_scan'"
            )
        )
    scheduler._overdue_candidates = lambda checked_at: [stale_candidate]  # type: ignore[method-assign]

    assert scheduler.dispatch_overdue(now=NOW, limit=10) == []
    with scheduler.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM airank_outbox_events")).scalar_one() == 0

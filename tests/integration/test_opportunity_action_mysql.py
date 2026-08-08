from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.opportunity_action_routes import (
    MySQLOpportunityActionRepository,
    OpportunityActionClaimRequest,
    OpportunityActionCreateRequest,
    OpportunityActionTransitionRequest,
)
from apps.api.opportunity_routing_routes import (
    MySQLOpportunityActionRoutingRepository,
    OpportunityActionMemberUpsertRequest,
    OpportunityActionRoutePutRequest,
    OpportunityActionTeamCreateRequest,
)
from apps.api.opportunity_routes import CONTRACT_VERSION, POLICY_VERSION, stable_id
from airank_scheduler import MySQLOpportunityActionEscalationScheduler


DATABASE_URL = os.getenv("AIRANK_DATABASE_URL", "").strip()
RUN_REAL_MYSQL = os.getenv("AIRANK_RUN_REAL_MYSQL", "").strip() == "1"
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not RUN_REAL_MYSQL,
    reason="real MySQL opportunity action integration requires AIRANK_RUN_REAL_MYSQL=1",
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def insert_run(
    conn,
    *,
    run_id: str,
    tenant_id: str,
    project_id: str,
    key: str,
    evaluated_at: datetime,
    previous_run_id: str | None,
    opportunity_ids: list[str],
    cleared_ids: list[str],
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO airank_opportunity_derivation_runs (
              id, tenant_id, project_id, contract_version, policy_version,
              idempotency_key, request_sha256, source_basis_sha256,
              evaluated_at, knowledge_window_days, previous_run_id,
              opportunity_ids_json, cleared_opportunity_ids_json,
              source_counts_json, opportunity_count, new_count,
              persisting_count, cleared_count, status, created_by,
              trace_id, created_at
            ) VALUES (
              :id, :tenant_id, :project_id, :contract_version, :policy_version,
              :idempotency_key, :request_sha256, :source_basis_sha256,
              :evaluated_at, 30, :previous_run_id,
              :opportunity_ids_json, :cleared_opportunity_ids_json,
              :source_counts_json, :opportunity_count, 0,
              :persisting_count, :cleared_count, 'succeeded', 'action-qa',
              :trace_id, :created_at
            )
            """
        ),
        {
            "id": run_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "contract_version": CONTRACT_VERSION,
            "policy_version": POLICY_VERSION,
            "idempotency_key": key,
            "request_sha256": sha("request-" + key),
            "source_basis_sha256": sha("basis-" + key),
            "evaluated_at": evaluated_at,
            "previous_run_id": previous_run_id,
            "opportunity_ids_json": json.dumps(opportunity_ids),
            "cleared_opportunity_ids_json": json.dumps(cleared_ids),
            "source_counts_json": json.dumps(
                {
                    "brand_visibility": len(opportunity_ids),
                    "citation_support": 0,
                    "fact_governance": 0,
                    "page_extractability": 0,
                }
            ),
            "opportunity_count": len(opportunity_ids),
            "persisting_count": len(opportunity_ids) if previous_run_id else 0,
            "cleared_count": len(cleared_ids),
            "trace_id": "trc_" + sha(key)[:16],
            "created_at": evaluated_at,
        },
    )


def insert_snapshot(
    conn,
    *,
    snapshot_id: str,
    run_id: str,
    opportunity_id: str,
    tenant_id: str,
    project_id: str,
    state: str,
    seed: str,
    created_at: datetime,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO airank_intervention_opportunity_snapshots (
              id, tenant_id, project_id, derivation_run_id, opportunity_id,
              contract_version, policy_version, source_kind, source_ref_type,
              source_ref_id, issue_code, source_evidence_sha256, evidence_level,
              state, intervention_gate, severity, priority_score,
              score_factors_json, source_refs_json, title, description,
              recommended_action, observed_at, snapshot_sha256, created_at
            ) VALUES (
              :id, :tenant_id, :project_id, :run_id, :opportunity_id,
              :contract_version, :policy_version, 'brand_visibility', 'evidence_gap',
              :source_ref_id, 'brand_unmentioned', :evidence_sha256,
              'quality_gated_repeated_samples', :state, :intervention_gate,
              'high', 80, :score_factors, :source_refs,
              '真实重复样本未提及品牌',
              '该观察只表示真实样本未提及，不承诺后续推荐。',
              'collect_enterprise_fact_evidence', :observed_at,
              :snapshot_sha256, :created_at
            )
            """
        ),
        {
            "id": snapshot_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "opportunity_id": opportunity_id,
            "contract_version": CONTRACT_VERSION,
            "policy_version": POLICY_VERSION,
            "source_ref_id": "gap_action_" + sha(seed)[:20],
            "evidence_sha256": sha("evidence-" + seed),
            "state": state,
            "intervention_gate": "content_action_ready" if state == "ready_for_action" else "evidence_blocked",
            "score_factors": json.dumps(
                {"severity_points": 30, "evidence_points": 35, "urgency_points": 15, "total": 80}
            ),
            "source_refs": json.dumps(
                {
                    "gap_ids": ["gap_action_" + sha(seed)[:20]],
                    "answer_snapshot_ids": [],
                    "evidence_snapshot_ids": [],
                    "citation_ids": [],
                    "citation_review_ids": [],
                    "knowledge_source_ids": [],
                    "fact_revision_ids": [],
                    "fact_conflict_ids": [],
                    "page_audit_run_ids": [],
                    "page_audit_finding_ids": [],
                }
            ),
            "observed_at": created_at,
            "snapshot_sha256": sha("snapshot-" + seed),
            "created_at": created_at,
        },
    )


def test_real_mysql_opportunity_action_requires_owner_and_newer_clear_snapshot() -> None:
    suffix = uuid4().hex[:12]
    tenant_id = f"tenant_action_{suffix}"
    project_id = f"project_action_{suffix}"
    opportunity_id = stable_id("opportunity", tenant_id, project_id, "brand_visibility", "gap", "brand_unmentioned", POLICY_VERSION)
    run_one = stable_id("opportunity_run", tenant_id, project_id, "run-one")
    run_two = stable_id("opportunity_run", tenant_id, project_id, "run-two")
    run_three = stable_id("opportunity_run", tenant_id, project_id, "run-three")
    snapshot_one = stable_id("opportunity_snapshot", run_one, opportunity_id)
    snapshot_two = stable_id("opportunity_snapshot", run_two, opportunity_id)
    at = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    repository = MySQLOpportunityActionRepository(DATABASE_URL)
    routing_repository = MySQLOpportunityActionRoutingRepository(DATABASE_URL)
    escalation_scheduler = MySQLOpportunityActionEscalationScheduler(
        DATABASE_URL,
        tenant_id=tenant_id,
        project_id=project_id,
        scheduler_id="action-integration-qa",
    )

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO airank_projects "
                    "(id, tenant_id, name, brand_name, status, created_by) "
                    "VALUES (:id, :tenant_id, 'Action QA', 'Action QA', 'active', 'action-qa')"
                ),
                {"id": project_id, "tenant_id": tenant_id},
            )
            insert_run(
                conn,
                run_id=run_one,
                tenant_id=tenant_id,
                project_id=project_id,
                key="one-" + suffix,
                evaluated_at=at,
                previous_run_id=None,
                opportunity_ids=[opportunity_id],
                cleared_ids=[],
            )
            insert_snapshot(
                conn,
                snapshot_id=snapshot_one,
                run_id=run_one,
                opportunity_id=opportunity_id,
                tenant_id=tenant_id,
                project_id=project_id,
                state="blocked_evidence",
                seed="one-" + suffix,
                created_at=at,
            )

        routing = routing_repository.create_team(
            tenant_id,
            project_id,
            OpportunityActionTeamCreateRequest(name="Action QA Team " + suffix),
            "action-team-" + suffix,
            "routing-admin",
        )
        team_id = routing.teams[0].team_id
        routing_repository.upsert_member(
            tenant_id,
            project_id,
            team_id,
            "owner-user",
            OpportunityActionMemberUpsertRequest(
                display_name="Opportunity Owner",
                max_active_actions=1,
                receives_escalations=True,
            ),
            "routing-admin",
        )
        routing = routing_repository.put_route(
            tenant_id,
            project_id,
            "brand_visibility",
            OpportunityActionRoutePutRequest(team_id=team_id),
            "routing-admin",
        )
        assert routing.routing_mode == "blocked"
        assert routing.routes[0].routing_ready is True

        created = repository.create(
            tenant_id,
            project_id,
            snapshot_one,
            OpportunityActionCreateRequest(requested_by="spoofed", due_in_days=7),
            idempotency_key="action-create-" + suffix,
            actor="owner-user",
            trace_id="trc_action_create_" + suffix,
        )
        assert created.status == "evidence_blocked"
        assert created.assigned_to is None
        assert created.effect_claim_allowed is False
        assert created.event_count == 1
        assert created.routing_state == "team_routed"
        assert created.routing_team_id == team_id

        with pytest.raises(StarletteHTTPException) as unrouted:
            repository.claim(
                tenant_id,
                project_id,
                created.action_id,
                OpportunityActionClaimRequest(requested_by="spoofed", expected_version=1),
                idempotency_key="action-unrouted-" + suffix,
                actor="other-user",
                trace_id="trc_action_unrouted_" + suffix,
            )
        assert unrouted.value.status_code == 403

        claimed = repository.claim(
            tenant_id,
            project_id,
            created.action_id,
            OpportunityActionClaimRequest(requested_by="spoofed", expected_version=1),
            idempotency_key="action-claim-" + suffix,
            actor="owner-user",
            trace_id="trc_action_claim_" + suffix,
        )
        assert claimed.status == "evidence_blocked"
        assert claimed.assigned_to == "owner-user"
        assert claimed.version == 2
        assert claimed.routing_state == "team_routed"
        assert claimed.routing_member_id is not None
        assert claimed.external_membership_verified is False
        with pytest.raises(StarletteHTTPException) as forbidden:
            repository.transition(
                tenant_id,
                project_id,
                claimed.action_id,
                OpportunityActionTransitionRequest(
                    transition="release",
                    requested_by="spoofed",
                    expected_version=2,
                    reason="其他账号不能释放当前责任人的行动",
                ),
                idempotency_key="action-foreign-" + suffix,
                actor="other-user",
                trace_id="trc_action_foreign_" + suffix,
            )
        assert forbidden.value.status_code == 403

        with engine.begin() as conn:
            insert_run(
                conn,
                run_id=run_two,
                tenant_id=tenant_id,
                project_id=project_id,
                key="two-" + suffix,
                evaluated_at=at + timedelta(days=1),
                previous_run_id=run_one,
                opportunity_ids=[opportunity_id],
                cleared_ids=[],
            )
            insert_snapshot(
                conn,
                snapshot_id=snapshot_two,
                run_id=run_two,
                opportunity_id=opportunity_id,
                tenant_id=tenant_id,
                project_id=project_id,
                state="ready_for_action",
                seed="two-" + suffix,
                created_at=at + timedelta(days=1),
            )

        refreshed = repository.transition(
            tenant_id,
            project_id,
            claimed.action_id,
            OpportunityActionTransitionRequest(
                transition="refresh_evidence",
                requested_by="spoofed",
                expected_version=2,
                reason="新的完整机会快照已通过事实证据门禁",
            ),
            idempotency_key="action-refresh-" + suffix,
            actor="owner-user",
            trace_id="trc_action_refresh_" + suffix,
        )
        assert refreshed.status == "in_progress"
        assert refreshed.latest_snapshot_id == snapshot_two
        assert refreshed.latest_evidence_sha256 != created.latest_evidence_sha256
        assert refreshed.version == 3

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE airank_opportunity_actions SET due_at=:due_at "
                    "WHERE tenant_id=:tenant_id AND id=:action_id"
                ),
                {
                    "due_at": at,
                    "tenant_id": tenant_id,
                    "action_id": refreshed.action_id,
                },
            )
        escalation = escalation_scheduler.dispatch_overdue(
            now=at + timedelta(days=1, hours=1), limit=10
        )
        assert len(escalation) == 1
        assert escalation[0].routing_team_id == team_id
        assert escalation[0].eligible_recipient_count == 1
        escalated = repository.list(tenant_id, project_id).actions[0]
        assert escalated.escalation_count == 1
        assert escalated.pending_escalation_count == 1
        assert escalated.external_delivery_verified is False

        with engine.begin() as conn:
            insert_run(
                conn,
                run_id=run_three,
                tenant_id=tenant_id,
                project_id=project_id,
                key="three-" + suffix,
                evaluated_at=at + timedelta(days=2),
                previous_run_id=run_two,
                opportunity_ids=[],
                cleared_ids=[opportunity_id],
            )

        completed = repository.transition(
            tenant_id,
            project_id,
            refreshed.action_id,
            OpportunityActionTransitionRequest(
                transition="verify_not_observed",
                requested_by="spoofed",
                expected_version=3,
                reason="最新完整复测中本轮未再观察到该机会，等待后续窗口继续观察",
                verification_run_id=run_three,
                acknowledge_no_outcome_claim=True,
            ),
            idempotency_key="action-verify-" + suffix,
            actor="owner-user",
            trace_id="trc_action_verify_" + suffix,
        )
        assert completed.status == "verified_not_observed"
        assert completed.effect_claim_allowed is False
        assert completed.verification_run_id == run_three
        assert completed.verification_basis_sha256 == sha("basis-three-" + suffix)
        assert completed.event_count == 4
        assert completed.version == 4

        listed = repository.list(tenant_id, project_id)
        assert listed.final_count == 1
        assert listed.open_count == 0
        with engine.begin() as conn:
            events = conn.execute(
                text(
                    "SELECT previous_event_sha256, event_sha256, action_version "
                    "FROM airank_opportunity_action_events "
                    "WHERE tenant_id=:tenant_id AND action_id=:action_id "
                    "ORDER BY action_version"
                ),
                {"tenant_id": tenant_id, "action_id": completed.action_id},
            ).mappings().all()
        assert len(events) == 4
        assert events[0]["previous_event_sha256"] is None
        assert all(
            str(events[index]["previous_event_sha256"]) == str(events[index - 1]["event_sha256"])
            for index in range(1, len(events))
        )
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM airank_opportunity_action_events WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_notification_delivery_receipts WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_notification_deliveries WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_outbox_events WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_actions WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_action_routes WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_action_team_members WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_action_teams WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_intervention_opportunity_snapshots WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("UPDATE airank_opportunity_derivation_runs SET previous_run_id=NULL WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_derivation_runs WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_projects WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})

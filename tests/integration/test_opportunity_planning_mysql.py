from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.opportunity_action_routes import (
    MySQLOpportunityActionRepository,
    OpportunityActionClaimRequest,
    OpportunityActionCreateRequest,
)
from apps.api.opportunity_planning_routes import (
    MySQLOpportunityPlanningRepository,
    OpportunityDependencyCreateRequest,
    OpportunityDependencyWaiveRequest,
    OpportunityExecutionPlanPutRequest,
)
from apps.api.opportunity_routes import POLICY_VERSION, stable_id
from tests.integration.test_opportunity_action_mysql import insert_run, insert_snapshot


DATABASE_URL = os.getenv("AIRANK_DATABASE_URL", "").strip()
RUN_REAL_MYSQL = os.getenv("AIRANK_RUN_REAL_MYSQL", "").strip() == "1"
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not RUN_REAL_MYSQL,
    reason="real MySQL opportunity planning integration requires AIRANK_RUN_REAL_MYSQL=1",
)


def test_real_mysql_opportunity_planning_totals_dependencies_and_audit_chain() -> None:
    suffix = uuid4().hex[:12]
    tenant_id = f"tenant_plan_{suffix}"
    project_id = f"project_plan_{suffix}"
    run_id = stable_id("opportunity_run", tenant_id, project_id, "planning")
    opportunity_a = stable_id(
        "opportunity",
        tenant_id,
        project_id,
        "brand_visibility",
        "gap-a",
        "brand_unmentioned",
        POLICY_VERSION,
    )
    opportunity_b = stable_id(
        "opportunity",
        tenant_id,
        project_id,
        "brand_visibility",
        "gap-b",
        "brand_unmentioned",
        POLICY_VERSION,
    )
    snapshot_a = stable_id("opportunity_snapshot", run_id, opportunity_a)
    snapshot_b = stable_id("opportunity_snapshot", run_id, opportunity_b)
    at = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    actions = MySQLOpportunityActionRepository(DATABASE_URL)
    planning = MySQLOpportunityPlanningRepository(DATABASE_URL)

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO airank_projects "
                    "(id, tenant_id, name, brand_name, status, created_by) "
                    "VALUES (:id, :tenant_id, 'Planning QA', 'Planning QA', 'active', 'planning-qa')"
                ),
                {"id": project_id, "tenant_id": tenant_id},
            )
            insert_run(
                conn,
                run_id=run_id,
                tenant_id=tenant_id,
                project_id=project_id,
                key="planning-" + suffix,
                evaluated_at=at,
                previous_run_id=None,
                opportunity_ids=[opportunity_a, opportunity_b],
                cleared_ids=[],
            )
            insert_snapshot(
                conn,
                snapshot_id=snapshot_a,
                run_id=run_id,
                opportunity_id=opportunity_a,
                tenant_id=tenant_id,
                project_id=project_id,
                state="ready_for_action",
                seed="plan-a-" + suffix,
                created_at=at,
            )
            insert_snapshot(
                conn,
                snapshot_id=snapshot_b,
                run_id=run_id,
                opportunity_id=opportunity_b,
                tenant_id=tenant_id,
                project_id=project_id,
                state="ready_for_action",
                seed="plan-b-" + suffix,
                created_at=at,
            )

        action_a = actions.create(
            tenant_id,
            project_id,
            snapshot_a,
            OpportunityActionCreateRequest(requested_by="spoofed", due_in_days=7),
            idempotency_key="plan-action-a-" + suffix,
            actor="planning-admin",
            trace_id="trc_plan_action_a_" + suffix,
        )
        action_b = actions.create(
            tenant_id,
            project_id,
            snapshot_b,
            OpportunityActionCreateRequest(requested_by="spoofed", due_in_days=14),
            idempotency_key="plan-action-b-" + suffix,
            actor="planning-admin",
            trace_id="trc_plan_action_b_" + suffix,
        )

        empty = planning.portfolio(tenant_id, project_id)
        assert empty.planning_required_count == 2
        assert empty.approved_plan_count == 0
        assert empty.planning_coverage_complete is False
        assert empty.total_estimated_effort_hours is None
        assert empty.total_estimated_budget_amount is None

        plan_a_payload = OpportunityExecutionPlanPutRequest(
            status="approved",
            estimated_effort_hours=Decimal("4.00"),
            estimated_budget_amount=Decimal("1000.00"),
            planned_start_at=at,
            planned_due_at=at + timedelta(days=7),
            assumptions="实施负责人按当前事实补证范围手工估算，真实成本以交付记录为准。",
        )
        plan_a = planning.put_plan(
            tenant_id,
            project_id,
            action_a.action_id,
            plan_a_payload,
            actor="planning-admin",
            trace_id="trc_plan_a_" + suffix,
        )
        replay = planning.put_plan(
            tenant_id,
            project_id,
            action_a.action_id,
            plan_a_payload,
            actor="planning-admin",
            trace_id="trc_plan_a_replay_" + suffix,
        )
        assert replay.idempotent_replay is True
        assert replay.version == plan_a.version == 1
        partial = planning.portfolio(tenant_id, project_id)
        assert partial.approved_plan_count == 1
        assert partial.planning_coverage_complete is False
        assert partial.total_estimated_budget_amount is None

        planning.put_plan(
            tenant_id,
            project_id,
            action_b.action_id,
            OpportunityExecutionPlanPutRequest(
                status="approved",
                estimated_effort_hours=Decimal("6.00"),
                estimated_budget_amount=Decimal("2000.00"),
                planned_start_at=at + timedelta(days=7),
                planned_due_at=at + timedelta(days=14),
                assumptions="实施负责人按当前页面干预范围手工估算，真实成本以交付记录为准。",
            ),
            actor="planning-admin",
            trace_id="trc_plan_b_" + suffix,
        )
        complete = planning.portfolio(tenant_id, project_id)
        assert complete.planning_coverage_complete is True
        assert complete.total_estimated_effort_hours == Decimal("10.00")
        assert complete.total_estimated_budget_amount == Decimal("3000.00")
        assert complete.outcome_forecast_allowed is False

        dependency_payload = OpportunityDependencyCreateRequest(
            prerequisite_action_id=action_a.action_id,
            dependency_type="finish_to_start",
            rationale="先完成事实补证，再启动页面内容干预",
        )
        dependency = planning.create_dependency(
            tenant_id,
            project_id,
            action_b.action_id,
            dependency_payload,
            idempotency_key="plan-dependency-" + suffix,
            actor="planning-admin",
            trace_id="trc_dependency_" + suffix,
        )
        replay_dependency = planning.create_dependency(
            tenant_id,
            project_id,
            action_b.action_id,
            dependency_payload,
            idempotency_key="plan-dependency-" + suffix,
            actor="planning-admin",
            trace_id="trc_dependency_replay_" + suffix,
        )
        assert replay_dependency.idempotent_replay is True
        assert replay_dependency.dependency_id == dependency.dependency_id

        blocked = planning.portfolio(tenant_id, project_id)
        assert blocked.topological_order == [[action_a.action_id], [action_b.action_id]]
        assert blocked.blocked_action_ids == [action_b.action_id]
        assert next(plan for plan in blocked.plans if plan.action_id == action_b.action_id).unsatisfied_dependency_count == 1
        with pytest.raises(StarletteHTTPException) as dependency_blocked:
            actions.claim(
                tenant_id,
                project_id,
                action_b.action_id,
                OpportunityActionClaimRequest(
                    requested_by="spoofed",
                    expected_version=1,
                ),
                idempotency_key="plan-claim-blocked-" + suffix,
                actor="planning-owner",
                trace_id="trc_claim_blocked_" + suffix,
            )
        assert dependency_blocked.value.status_code == 409
        assert dependency_blocked.value.detail["code"] == "OPPORTUNITY_ACTION_DEPENDENCY_BLOCKED"

        with pytest.raises(StarletteHTTPException) as cycle:
            planning.create_dependency(
                tenant_id,
                project_id,
                action_a.action_id,
                OpportunityDependencyCreateRequest(
                    prerequisite_action_id=action_b.action_id,
                    dependency_type="finish_to_start",
                    rationale="该反向依赖应被循环检测拒绝",
                ),
                idempotency_key="plan-cycle-" + suffix,
                actor="planning-admin",
                trace_id="trc_cycle_" + suffix,
            )
        assert cycle.value.status_code == 409

        waived = planning.waive_dependency(
            tenant_id,
            project_id,
            dependency.dependency_id,
            OpportunityDependencyWaiveRequest(
                expected_version=1,
                waiver_reason="客户书面确认本轮并行推进，但该豁免不能证明任何推荐或增长结果。",
                acknowledge_no_outcome_claim=True,
            ),
            actor="planning-admin",
            trace_id="trc_waiver_" + suffix,
        )
        assert waived.status == "waived"
        assert waived.satisfied is True
        after_waiver = planning.portfolio(tenant_id, project_id)
        assert after_waiver.blocked_action_ids == []
        assert after_waiver.topological_order == [sorted([action_a.action_id, action_b.action_id])]
        claimed = actions.claim(
            tenant_id,
            project_id,
            action_b.action_id,
            OpportunityActionClaimRequest(
                requested_by="spoofed",
                expected_version=1,
            ),
            idempotency_key="plan-claim-after-waiver-" + suffix,
            actor="planning-owner",
            trace_id="trc_claim_after_waiver_" + suffix,
        )
        assert claimed.status == "in_progress"
        assert claimed.assigned_to == "planning-owner"

        with engine.begin() as conn:
            events = conn.execute(
                text(
                    "SELECT aggregate_version, previous_event_sha256, event_sha256 "
                    "FROM airank_opportunity_action_plan_events "
                    "WHERE tenant_id=:tenant_id AND aggregate_type='dependency' "
                    "AND aggregate_id=:aggregate_id ORDER BY aggregate_version"
                ),
                {"tenant_id": tenant_id, "aggregate_id": dependency.dependency_id},
            ).mappings().all()
        assert len(events) == 2
        assert events[0]["previous_event_sha256"] is None
        assert str(events[1]["previous_event_sha256"]) == str(events[0]["event_sha256"])
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM airank_opportunity_action_plan_events WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_action_dependencies WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_action_plans WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_action_events WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_actions WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_intervention_opportunity_snapshots WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("UPDATE airank_opportunity_derivation_runs SET previous_run_id=NULL WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_derivation_runs WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_projects WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})

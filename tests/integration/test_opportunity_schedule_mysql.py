from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from apps.api.opportunity_action_routes import (
    MySQLOpportunityActionRepository,
    OpportunityActionClaimRequest,
    OpportunityActionCreateRequest,
)
from apps.api.opportunity_planning_routes import (
    MySQLOpportunityPlanningRepository,
    OpportunityExecutionPlanPutRequest,
)
from apps.api.opportunity_routing_routes import (
    MySQLOpportunityActionRoutingRepository,
    OpportunityActionMemberUpsertRequest,
    OpportunityActionRoutePutRequest,
    OpportunityActionTeamCreateRequest,
)
from apps.api.opportunity_routes import POLICY_VERSION, stable_id
from apps.api.opportunity_schedule_routes import (
    MySQLOpportunityScheduleRepository,
    OpportunityCapacityCalendarPutRequest,
    OpportunityCapacityExceptionPutRequest,
    OpportunityScheduleCreateRequest,
)
from tests.integration.test_opportunity_action_mysql import insert_run, insert_snapshot


DATABASE_URL = os.getenv("AIRANK_DATABASE_URL", "").strip()
RUN_REAL_MYSQL = os.getenv("AIRANK_RUN_REAL_MYSQL", "").strip() == "1"
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not RUN_REAL_MYSQL,
    reason="real MySQL opportunity schedule integration requires AIRANK_RUN_REAL_MYSQL=1",
)


def test_real_mysql_capacity_calendar_conflict_and_immutable_schedule_snapshots() -> None:
    suffix = uuid4().hex[:12]
    tenant_id = f"tenant_capacity_{suffix}"
    project_id = f"project_capacity_{suffix}"
    run_id = stable_id("opportunity_run", tenant_id, project_id, "capacity")
    opportunity_ids = [
        stable_id(
            "opportunity",
            tenant_id,
            project_id,
            "brand_visibility",
            f"gap-{index}",
            "brand_unmentioned",
            POLICY_VERSION,
        )
        for index in (1, 2)
    ]
    snapshot_ids = [stable_id("opportunity_snapshot", run_id, value) for value in opportunity_ids]
    at = datetime(2026, 8, 10, 1, 0, tzinfo=timezone.utc)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    routing = MySQLOpportunityActionRoutingRepository(DATABASE_URL)
    actions = MySQLOpportunityActionRepository(DATABASE_URL)
    planning = MySQLOpportunityPlanningRepository(DATABASE_URL)
    scheduling = MySQLOpportunityScheduleRepository(DATABASE_URL)

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO airank_projects "
                    "(id, tenant_id, name, brand_name, status, created_by) "
                    "VALUES (:id, :tenant_id, 'Capacity QA', 'Capacity QA', 'active', 'capacity-qa')"
                ),
                {"id": project_id, "tenant_id": tenant_id},
            )
            insert_run(
                conn,
                run_id=run_id,
                tenant_id=tenant_id,
                project_id=project_id,
                key="capacity-" + suffix,
                evaluated_at=at,
                previous_run_id=None,
                opportunity_ids=opportunity_ids,
                cleared_ids=[],
            )
            for index, snapshot_id in enumerate(snapshot_ids):
                insert_snapshot(
                    conn,
                    snapshot_id=snapshot_id,
                    run_id=run_id,
                    opportunity_id=opportunity_ids[index],
                    tenant_id=tenant_id,
                    project_id=project_id,
                    state="ready_for_action",
                    seed=f"capacity-{index}-{suffix}",
                    created_at=at,
                )

        routed = routing.create_team(
            tenant_id,
            project_id,
            OpportunityActionTeamCreateRequest(name="Capacity delivery"),
            "capacity-team-" + suffix,
            "capacity-admin",
        )
        team_id = routed.teams[0].team_id
        routed = routing.upsert_member(
            tenant_id,
            project_id,
            team_id,
            "capacity-owner",
            OpportunityActionMemberUpsertRequest(
                display_name="Capacity Owner",
                max_active_actions=5,
            ),
            "capacity-admin",
        )
        member_id = routed.teams[0].members[0].member_id
        routing.put_route(
            tenant_id,
            project_id,
            "brand_visibility",
            OpportunityActionRoutePutRequest(team_id=team_id),
            "capacity-admin",
        )

        action_rows = []
        for index, snapshot_id in enumerate(snapshot_ids):
            created = actions.create(
                tenant_id,
                project_id,
                snapshot_id,
                OpportunityActionCreateRequest(requested_by="ignored", due_in_days=30),
                idempotency_key=f"capacity-action-{index}-{suffix}",
                actor="capacity-admin",
                trace_id=f"trc_capacity_action_{index}_{suffix}",
            )
            claimed = actions.claim(
                tenant_id,
                project_id,
                created.action_id,
                OpportunityActionClaimRequest(requested_by="ignored", expected_version=1),
                idempotency_key=f"capacity-claim-{index}-{suffix}",
                actor="capacity-owner",
                trace_id=f"trc_capacity_claim_{index}_{suffix}",
            )
            assert claimed.routing_member_id == member_id
            planning.put_plan(
                tenant_id,
                project_id,
                claimed.action_id,
                OpportunityExecutionPlanPutRequest(
                    status="approved",
                    estimated_effort_hours=Decimal("8"),
                    estimated_budget_amount=Decimal("1000"),
                    planned_start_at=at,
                    planned_due_at=at + timedelta(hours=8),
                    assumptions="交付负责人按单日八小时人工估算，真实投入仍以客户确认的工时记录为准。",
                ),
                actor="capacity-admin",
                trace_id=f"trc_capacity_plan_{index}_{suffix}",
            )
            action_rows.append(claimed)

        calendar = scheduling.put_calendar(
            tenant_id,
            project_id,
            member_id,
            OpportunityCapacityCalendarPutRequest(
                timezone="Asia/Shanghai",
                weekly_capacity_hours=Decimal("8"),
                workdays=[1],
                assumptions="团队确认每周一可用于该项目的人工容量为八小时，不代表已发生工时或成本。",
            ),
            actor="capacity-admin",
            trace_id="trc_capacity_calendar_" + suffix,
        )
        replay_calendar = scheduling.put_calendar(
            tenant_id,
            project_id,
            member_id,
            OpportunityCapacityCalendarPutRequest(
                timezone="Asia/Shanghai",
                weekly_capacity_hours=Decimal("8"),
                workdays=[1],
                assumptions="团队确认每周一可用于该项目的人工容量为八小时，不代表已发生工时或成本。",
            ),
            actor="capacity-admin",
            trace_id="trc_capacity_calendar_replay_" + suffix,
        )
        assert replay_calendar.idempotent_replay is True
        assert replay_calendar.version == calendar.version == 1
        exception = scheduling.put_exception(
            tenant_id,
            project_id,
            member_id,
            date(2026, 8, 17),
            OpportunityCapacityExceptionPutRequest(
                available_hours=Decimal("0"),
                reason="客户确认该周一团队培训，项目可用容量为零。",
            ),
            actor="capacity-admin",
            trace_id="trc_capacity_exception_" + suffix,
        )
        assert exception.external_calendar_verified is False

        first = scheduling.create_schedule(
            tenant_id,
            project_id,
            OpportunityScheduleCreateRequest(as_of_date=date(2026, 8, 10)),
            idempotency_key="capacity-schedule-first-" + suffix,
            actor="capacity-admin",
            trace_id="trc_capacity_schedule_first_" + suffix,
        )
        assert first.action_count == 2
        assert first.capacity_conflict_count == 2
        assert first.blocked_count == 2
        assert first.schedule_feasible is False
        assert {item.schedule_state for item in first.items} == {"capacity_exceeded"}
        replay = scheduling.create_schedule(
            tenant_id,
            project_id,
            OpportunityScheduleCreateRequest(as_of_date=date(2026, 8, 10)),
            idempotency_key="capacity-schedule-first-" + suffix,
            actor="capacity-admin",
            trace_id="trc_capacity_schedule_replay_" + suffix,
        )
        assert replay.idempotent_replay is True
        assert replay.run_id == first.run_id
        independent_snapshot = scheduling.create_schedule(
            tenant_id,
            project_id,
            OpportunityScheduleCreateRequest(as_of_date=date(2026, 8, 10)),
            idempotency_key="capacity-schedule-independent-" + suffix,
            actor="capacity-admin",
            trace_id="trc_capacity_schedule_independent_" + suffix,
        )
        assert independent_snapshot.run_id != first.run_id
        assert independent_snapshot.source_manifest_sha256 == first.source_manifest_sha256
        assert independent_snapshot.result_sha256 == first.result_sha256
        assert independent_snapshot.idempotent_replay is False

        updated = scheduling.put_calendar(
            tenant_id,
            project_id,
            member_id,
            OpportunityCapacityCalendarPutRequest(
                timezone="Asia/Shanghai",
                weekly_capacity_hours=Decimal("16"),
                workdays=[1],
                assumptions="团队重新确认每周一可投入十六小时，仍属于人工计划容量而不是已发生工时。",
                expected_version=1,
            ),
            actor="capacity-admin",
            trace_id="trc_capacity_calendar_update_" + suffix,
        )
        assert updated.version == 2
        second = scheduling.create_schedule(
            tenant_id,
            project_id,
            OpportunityScheduleCreateRequest(as_of_date=date(2026, 8, 10)),
            idempotency_key="capacity-schedule-second-" + suffix,
            actor="capacity-admin",
            trace_id="trc_capacity_schedule_second_" + suffix,
        )
        assert second.run_id != first.run_id
        assert second.source_manifest_sha256 != first.source_manifest_sha256
        assert second.scheduled_count == 2
        assert second.blocked_count == 0
        assert second.capacity_conflict_count == 0
        assert second.schedule_feasible is True
        assert second.outcome_forecast_allowed is False
        portfolio = scheduling.portfolio(tenant_id, project_id)
        assert portfolio.capacity_coverage_complete is True
        assert portfolio.latest_schedule is not None
        assert portfolio.latest_schedule.run_id == second.run_id

        with engine.begin() as conn:
            calendar_events = conn.execute(
                text(
                    "SELECT aggregate_version, previous_event_sha256, event_sha256 "
                    "FROM airank_opportunity_capacity_events "
                    "WHERE tenant_id=:tenant_id AND aggregate_type='calendar' "
                    "ORDER BY aggregate_version"
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
            schedule_count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM airank_opportunity_schedule_runs WHERE tenant_id=:tenant_id"),
                    {"tenant_id": tenant_id},
                ).scalar_one()
            )
            schedule_item_count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM airank_opportunity_schedule_items WHERE tenant_id=:tenant_id"),
                    {"tenant_id": tenant_id},
                ).scalar_one()
            )
        assert len(calendar_events) == 2
        assert calendar_events[0]["previous_event_sha256"] is None
        assert str(calendar_events[1]["previous_event_sha256"]) == str(calendar_events[0]["event_sha256"])
        assert schedule_count == 3
        assert schedule_item_count == 6
    finally:
        with engine.begin() as conn:
            for table in (
                "airank_opportunity_schedule_items",
                "airank_opportunity_schedule_runs",
                "airank_opportunity_capacity_events",
                "airank_opportunity_capacity_exceptions",
                "airank_opportunity_capacity_calendars",
                "airank_opportunity_action_plan_events",
                "airank_opportunity_action_dependencies",
                "airank_opportunity_action_plans",
                "airank_opportunity_action_events",
                "airank_opportunity_actions",
                "airank_opportunity_action_routes",
                "airank_opportunity_action_team_members",
                "airank_opportunity_action_teams",
                "airank_intervention_opportunity_snapshots",
            ):
                conn.execute(text(f"DELETE FROM {table} WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(
                text("UPDATE airank_opportunity_derivation_runs SET previous_run_id=NULL WHERE tenant_id=:tenant_id"),
                {"tenant_id": tenant_id},
            )
            conn.execute(
                text("DELETE FROM airank_opportunity_derivation_runs WHERE tenant_id=:tenant_id"),
                {"tenant_id": tenant_id},
            )
            conn.execute(
                text("DELETE FROM airank_projects WHERE tenant_id=:tenant_id"),
                {"tenant_id": tenant_id},
            )

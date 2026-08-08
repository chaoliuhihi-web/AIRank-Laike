from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_opportunity_actions_require_ownership_sla_and_newer_verification() -> None:
    migration = (ROOT / "apps/api/alembic/versions/20260809_0034_opportunity_actions.py").read_text(encoding="utf-8")
    routes = (ROOT / "apps/api/opportunity_action_routes.py").read_text(encoding="utf-8")
    for required in (
        "airank_opportunity_actions",
        "airank_opportunity_action_events",
        "previous_event_sha256",
        "event_sha256",
        "assigned_to",
        "due_at",
        "effect_claim_allowed",
        "verification_basis_sha256",
    ):
        assert required in migration
    assert 'FINAL_STATUSES = {"verified_not_observed", "waived"}' in routes
    assert "verification_run_must_be_latest_complete_derivation" in routes
    assert "verification_run_opportunity_manifest_is_inconsistent" in routes
    assert "opportunity_still_present_in_verification_run" in routes
    assert '"effect_claim_allowed": False' in routes
    assert '"OPPORTUNITY_ACTION_OWNER_FORBIDDEN"' in routes


def test_all_clear_opportunity_snapshot_is_allowed_only_after_a_real_baseline() -> None:
    routes = (ROOT / "apps/api/opportunity_routes.py").read_text(encoding="utf-8")
    derivation_schema = (ROOT / "packages/contracts/opportunity_derivation_response.schema.json").read_text(encoding="utf-8")
    assert "if not candidates and previous is None" in routes
    assert '"opportunity_count": { "type": "integer", "minimum": 0 }' in derivation_schema
    assert '"minItems": 1' not in derivation_schema


def test_opportunity_action_routing_is_capacity_gated_and_escalation_is_truthful() -> None:
    migration = (ROOT / "apps/api/alembic/versions/20260809_0035_opportunity_action_routing.py").read_text(encoding="utf-8")
    routing = (ROOT / "apps/api/opportunity_routing_routes.py").read_text(encoding="utf-8")
    actions = (ROOT / "apps/api/opportunity_action_routes.py").read_text(encoding="utf-8")
    scheduler = (ROOT / "apps/scheduler/airank_scheduler/opportunity_action_escalation.py").read_text(encoding="utf-8")
    worker = (ROOT / "apps/worker/airank_worker/review_notification.py").read_text(encoding="utf-8")
    for required in (
        "airank_opportunity_action_teams",
        "airank_opportunity_action_team_members",
        "airank_opportunity_action_routes",
        "max_active_actions",
        "external_membership_verified",
        "routing_route_version",
        "routing_member_version",
    ):
        assert required in migration
    assert "actor_is_not_active_team_member" in routing
    assert "member_capacity_reached" in routing
    assert "OPPORTUNITY_ACTION_CAPACITY_REACHED" in actions
    assert 'ACTION_SLA_ESCALATION_EVENT = "opportunity_action.sla_overdue.v1"' in scheduler
    assert '"effect_claim_allowed": False' in scheduler
    assert '"delivery_claim": "outbox_pending_not_delivered"' in scheduler
    assert "assigned_to" not in scheduler.split("payload = {", 1)[1].split("}", 1)[0]
    assert "ACTION_EVENT_TYPE" in worker


def test_opportunity_action_routing_is_visible_in_the_real_asset_workflow() -> None:
    board = (ROOT / "apps/web/src/console/OpportunityBoard.tsx").read_text(encoding="utf-8")
    api = (ROOT / "apps/web/src/console/api.ts").read_text(encoding="utf-8")
    assert "airank.opportunity-action-routing.v1" in board
    assert "手工成员不冒充 Yudao 已核验" in board
    assert "SLA 升级" in board
    assert "fetchOpportunityActionRouting" in api
    assert "putOpportunityActionRoute" in api


def test_opportunity_execution_planning_separates_estimates_from_outcomes() -> None:
    migration = (ROOT / "apps/api/alembic/versions/20260809_0036_opportunity_execution_plans.py").read_text(encoding="utf-8")
    routes = (ROOT / "apps/api/opportunity_planning_routes.py").read_text(encoding="utf-8")
    for required in (
        "airank_opportunity_action_plans",
        "airank_opportunity_action_dependencies",
        "airank_opportunity_action_plan_events",
        "estimated_effort_hours",
        "estimated_budget_amount",
        "previous_event_sha256",
        "outcome_forecast_allowed",
    ):
        assert required in migration
    assert 'estimate_source="human_estimate"' in routes
    assert '"no_growth_or_recommendation_forecast"' in routes
    assert '"outcome_forecast_allowed": False' in routes
    assert "_contains_cycle" in routes
    assert "ORDER BY id FOR UPDATE" in routes
    assert "planning_coverage_complete=coverage" in routes
    assert "acknowledge_no_outcome_claim" in routes
    actions = (ROOT / "apps/api/opportunity_action_routes.py").read_text(encoding="utf-8")
    assert "OPPORTUNITY_ACTION_DEPENDENCY_BLOCKED" in actions
    assert "_require_dependencies_satisfied" in actions


def test_opportunity_execution_planning_is_visible_in_the_real_asset_workflow() -> None:
    board = (ROOT / "apps/web/src/console/OpportunityBoard.tsx").read_text(encoding="utf-8")
    api = (ROOT / "apps/web/src/console/api.ts").read_text(encoding="utf-8")
    assert "airank.opportunity-execution-plan.v1" in board
    assert "人工预算与前置依赖" in board
    assert "效果声明：禁止" in board
    assert "planning_coverage_complete" in board
    assert "fetchOpportunityExecutionPortfolio" in api
    assert "putOpportunityExecutionPlan" in api
    assert "createOpportunityDependency" in api
    assert "waiveOpportunityDependency" in api

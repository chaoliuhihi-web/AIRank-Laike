from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, ValidationError
from pydantic import ValidationError as PydanticValidationError
import pytest
from referencing import Registry, Resource
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import opportunity_planning_routes
from apps.api.main import app
from apps.api.opportunity_planning_routes import (
    MySQLOpportunityPlanningRepository,
    OpportunityDependencyData,
    OpportunityExecutionPlanData,
    OpportunityExecutionPlanPutRequest,
    OpportunityExecutionPortfolioData,
    PLANNING_CONTRACT_VERSION,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
NOW = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)
ACTION_A = "opportunity_action_" + "a" * 20
ACTION_B = "opportunity_action_" + "b" * 20
DEPENDENCY_ID = "opportunity_dependency_" + "c" * 20


def load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def dependency_data(*, replay: bool = False) -> OpportunityDependencyData:
    return OpportunityDependencyData(
        dependency_id=DEPENDENCY_ID,
        action_id=ACTION_B,
        prerequisite_action_id=ACTION_A,
        prerequisite_status="in_progress",
        dependency_type="finish_to_start",
        status="active",
        satisfied=False,
        rationale="先完成事实补证，再开始页面干预",
        waiver_reason=None,
        version=1,
        created_by="trusted-admin",
        updated_by="trusted-admin",
        created_at=NOW,
        updated_at=NOW,
        idempotent_replay=replay,
    )


def plan_data(*, replay: bool = False) -> OpportunityExecutionPlanData:
    return OpportunityExecutionPlanData(
        plan_id="opportunity_plan_" + "d" * 20,
        action_id=ACTION_B,
        action_status="in_progress",
        contract_version=PLANNING_CONTRACT_VERSION,
        status="approved",
        estimate_source="human_estimate",
        estimated_effort_hours=Decimal("6.50"),
        estimated_budget_amount=Decimal("2800.00"),
        currency="CNY",
        planned_start_at=NOW,
        planned_due_at=NOW + timedelta(days=7),
        assumptions="由实施负责人根据当前证据缺口手工估算，实际投入以交付记录为准。",
        outcome_forecast_allowed=False,
        dependencies=[dependency_data()],
        unsatisfied_dependency_count=1,
        version=1,
        event_count=1,
        last_event_sha256="e" * 64,
        created_by="trusted-admin",
        updated_by="trusted-admin",
        created_at=NOW,
        updated_at=NOW,
        idempotent_replay=replay,
    )


class FakePlanningRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def portfolio(self, tenant_id, project_id):  # noqa: ANN001
        self.calls.append(("portfolio", project_id))
        return OpportunityExecutionPortfolioData(
            project_id=project_id,
            contract_version=PLANNING_CONTRACT_VERSION,
            planning_required_count=1,
            approved_plan_count=1,
            planning_coverage_complete=True,
            total_estimated_effort_hours=Decimal("6.50"),
            total_estimated_budget_amount=Decimal("2800.00"),
            currency="CNY",
            topological_order=[[ACTION_A], [ACTION_B]],
            blocked_action_ids=[ACTION_B],
            plans=[plan_data()],
            unplanned_action_ids=[],
            outcome_forecast_allowed=False,
            known_limitations=["human_estimate_not_invoice_or_spend"],
        )

    def put_plan(self, tenant_id, project_id, action_id, payload, *, actor, trace_id):  # noqa: ANN001
        assert actor == "trusted-admin"
        assert payload.status == "approved"
        self.calls.append(("plan", action_id))
        return plan_data()

    def create_dependency(self, tenant_id, project_id, action_id, payload, *, idempotency_key, actor, trace_id):  # noqa: ANN001,E501
        assert actor == "trusted-admin"
        assert idempotency_key == "planning-dependency-key"
        self.calls.append(("dependency", action_id))
        return dependency_data()

    def waive_dependency(self, tenant_id, project_id, dependency_id, payload, *, actor, trace_id):  # noqa: ANN001,E501
        assert actor == "trusted-admin"
        assert payload.acknowledge_no_outcome_claim is True
        self.calls.append(("waive", dependency_id))
        item = dependency_data()
        return item.model_copy(
            update={
                "status": "waived",
                "satisfied": True,
                "waiver_reason": payload.waiver_reason,
                "version": 2,
            }
        )


def admin_headers() -> dict[str, str]:
    return {
        "tenant-id": "tenant_action",
        "X-AIRank-User-Id": "trusted-admin",
        "X-AIRank-Permissions": "airank:opportunity:admin",
    }


def test_planning_api_uses_authenticated_admin_and_real_contracts(monkeypatch) -> None:  # noqa: ANN001
    repository = FakePlanningRepository()
    monkeypatch.setattr(
        opportunity_planning_routes,
        "OPPORTUNITY_PLANNING_REPOSITORY",
        repository,
    )
    client = TestClient(app)
    plan = client.put(
        f"/api/v1/projects/project_action/opportunity-actions/{ACTION_B}/plan",
        headers=admin_headers(),
        json={
            "status": "approved",
            "estimated_effort_hours": "6.50",
            "estimated_budget_amount": "2800.00",
            "currency": "CNY",
            "planned_start_at": NOW.isoformat(),
            "planned_due_at": (NOW + timedelta(days=7)).isoformat(),
            "assumptions": "由实施负责人根据当前证据缺口手工估算，实际投入以交付记录为准。",
        },
    )
    dependency = client.post(
        f"/api/v1/projects/project_action/opportunity-actions/{ACTION_B}/dependencies",
        headers={**admin_headers(), "Idempotency-Key": "planning-dependency-key"},
        json={
            "prerequisite_action_id": ACTION_A,
            "dependency_type": "finish_to_start",
            "rationale": "先完成事实补证，再开始页面干预",
        },
    )
    waived = client.post(
        f"/api/v1/projects/project_action/opportunity-dependencies/{DEPENDENCY_ID}/waivers",
        headers=admin_headers(),
        json={
            "expected_version": 1,
            "waiver_reason": "客户书面确认本轮不等待前置行动，但该豁免不代表任何增长结果。",
            "acknowledge_no_outcome_claim": True,
        },
    )
    portfolio = client.get(
        "/api/v1/projects/project_action/opportunity-execution-portfolio",
        headers=admin_headers(),
    )
    assert [plan.status_code, dependency.status_code, waived.status_code, portfolio.status_code] == [200, 201, 200, 200]
    assert repository.calls == [
        ("plan", ACTION_B),
        ("dependency", ACTION_B),
        ("waive", DEPENDENCY_ID),
        ("portfolio", "project_action"),
    ]
    Draft202012Validator(
        load_schema("opportunity_execution_plan.schema.json"),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
        registry=Registry().with_resource(
            "https://airank.local/contracts/opportunity_dependency.schema.json",
            Resource.from_contents(load_schema("opportunity_dependency.schema.json")),
        ),
    ).validate(plan.json()["data"])
    Draft202012Validator(
        load_schema("opportunity_dependency.schema.json"),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    ).validate(dependency.json()["data"])
    registry = Registry().with_resources(
        [
            (
                "https://airank.local/contracts/opportunity_dependency.schema.json",
                Resource.from_contents(load_schema("opportunity_dependency.schema.json")),
            ),
            (
                "https://airank.local/contracts/opportunity_execution_plan.schema.json",
                Resource.from_contents(load_schema("opportunity_execution_plan.schema.json")),
            ),
        ]
    )
    Draft202012Validator(
        load_schema("opportunity_execution_portfolio_response.schema.json"),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
        registry=registry,
    ).validate(portfolio.json())
    assert portfolio.json()["data"]["outcome_forecast_allowed"] is False
    assert waived.json()["data"]["satisfied"] is True


def test_planning_mutations_are_admin_gated(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    with pytest.raises(StarletteHTTPException) as forbidden:
        opportunity_planning_routes.require_planning_admin(None)
    assert forbidden.value.status_code == 403
    assert forbidden.value.detail["code"] == "AUTH_PERMISSION_FORBIDDEN"
    opportunity_planning_routes.require_planning_admin("airank:opportunity:admin")


def test_planning_request_schemas_are_strict_and_no_outcome_claim_is_literal() -> None:
    valid = {
        "opportunity_execution_plan_put_request.schema.json": {
            "status": "approved",
            "estimated_effort_hours": "6.50",
            "estimated_budget_amount": "2800.00",
            "currency": "CNY",
            "assumptions": "由实施负责人根据当前证据缺口手工估算，实际投入以交付记录为准。",
        },
        "opportunity_dependency_create_request.schema.json": {
            "prerequisite_action_id": ACTION_A,
            "dependency_type": "evidence_prerequisite",
            "rationale": "事实证据审核通过后才允许执行",
        },
        "opportunity_dependency_waive_request.schema.json": {
            "expected_version": 1,
            "waiver_reason": "客户书面确认跳过前置步骤，但不据此声明任何增长或推荐效果。",
            "acknowledge_no_outcome_claim": True,
        },
    }
    for name, instance in valid.items():
        loaded = load_schema(name)
        Draft202012Validator.check_schema(loaded)
        Draft202012Validator(loaded).validate(instance)
    for name in (
        "opportunity_dependency.schema.json",
        "opportunity_execution_plan.schema.json",
        "opportunity_execution_plan_response.schema.json",
        "opportunity_dependency_response.schema.json",
        "opportunity_execution_portfolio_response.schema.json",
    ):
        Draft202012Validator.check_schema(load_schema(name))
    invalid = {**valid["opportunity_dependency_waive_request.schema.json"], "acknowledge_no_outcome_claim": False}
    try:
        Draft202012Validator(load_schema("opportunity_dependency_waive_request.schema.json")).validate(invalid)
    except ValidationError:
        pass
    else:
        raise AssertionError("dependency waiver must acknowledge that no outcome claim is allowed")


def test_approved_plan_requires_explained_assumptions_and_ordered_timezone() -> None:
    with pytest.raises(PydanticValidationError):
        OpportunityExecutionPlanPutRequest(
            status="approved",
            estimated_effort_hours=Decimal("2"),
            estimated_budget_amount=Decimal("100"),
            assumptions="too short",
        )
    with pytest.raises(PydanticValidationError):
        OpportunityExecutionPlanPutRequest(
            estimated_effort_hours=Decimal("2"),
            estimated_budget_amount=Decimal("100"),
            assumptions="这是一个满足草稿长度的人工估算",
            planned_start_at=datetime(2026, 8, 10, 9, 0),
        )
    with pytest.raises(PydanticValidationError):
        OpportunityExecutionPlanPutRequest(
            estimated_effort_hours=Decimal("2"),
            estimated_budget_amount=Decimal("100"),
            assumptions="这是一个满足草稿长度的人工估算",
            planned_start_at=NOW + timedelta(days=1),
            planned_due_at=NOW,
        )


def test_dependency_graph_cycle_and_topological_layers_are_deterministic() -> None:
    rows = [
        {"action_id": ACTION_B, "prerequisite_action_id": ACTION_A, "status": "active"}
    ]
    assert MySQLOpportunityPlanningRepository._contains_cycle(rows) is False
    assert MySQLOpportunityPlanningRepository._topological_order([ACTION_A, ACTION_B], rows) == [
        [ACTION_A],
        [ACTION_B],
    ]
    assert MySQLOpportunityPlanningRepository._topological_order(
        [ACTION_A, ACTION_B],
        [*rows, {**rows[0], "dependency_type": "evidence_prerequisite"}],
    ) == [[ACTION_A], [ACTION_B]]
    assert MySQLOpportunityPlanningRepository._contains_cycle(
        [
            *rows,
            {"action_id": ACTION_A, "prerequisite_action_id": ACTION_B, "status": "active"},
        ]
    ) is True

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError as PydanticValidationError
import pytest
from referencing import Registry, Resource
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import opportunity_schedule_routes
from apps.api.main import app
from apps.api.opportunity_schedule_routes import (
    CAPACITY_CONTRACT_VERSION,
    SCHEDULE_CONTRACT_VERSION,
    SCHEDULE_POLICY_VERSION,
    MySQLOpportunityScheduleRepository,
    OpportunityCapacityCalendarData,
    OpportunityCapacityCalendarPutRequest,
    OpportunityCapacityExceptionData,
    OpportunityCapacityPortfolioData,
    OpportunityScheduleItemData,
    OpportunityScheduleRunData,
    OpportunityScheduleWindowData,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
NOW = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
PROJECT_ID = "project_capacity"
TEAM_ID = "opportunity_action_team_" + "1" * 20
MEMBER_ID = "opportunity_action_member_" + "2" * 20
CALENDAR_ID = "opportunity_capacity_calendar_" + "3" * 20
EXCEPTION_ID = "opportunity_capacity_exception_" + "4" * 20
ACTION_ID = "opportunity_action_" + "5" * 20
PLAN_ID = "opportunity_plan_" + "6" * 20
RUN_ID = "opportunity_schedule_run_" + "7" * 20
ITEM_ID = "opportunity_schedule_item_" + "8" * 20


def load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def registry() -> Registry:
    names = (
        "opportunity_capacity_exception.schema.json",
        "opportunity_capacity_calendar.schema.json",
        "opportunity_schedule_run.schema.json",
    )
    return Registry().with_resources(
        [
            (
                f"https://airank.local/contracts/{name}",
                Resource.from_contents(load_schema(name)),
            )
            for name in names
        ]
    )


def exception_data(*, replay: bool = False) -> OpportunityCapacityExceptionData:
    return OpportunityCapacityExceptionData(
        exception_id=EXCEPTION_ID,
        exception_date=date(2026, 8, 17),
        available_hours=Decimal("0"),
        reason="客户确认当日团队不可用，容量覆盖为零。",
        exception_source="manual",
        external_calendar_verified=False,
        version=1,
        created_by="trusted-admin",
        updated_by="trusted-admin",
        created_at=NOW,
        updated_at=NOW,
        idempotent_replay=replay,
    )


def calendar_data(*, replay: bool = False) -> OpportunityCapacityCalendarData:
    return OpportunityCapacityCalendarData(
        calendar_id=CALENDAR_ID,
        team_id=TEAM_ID,
        member_id=MEMBER_ID,
        user_id="delivery-owner",
        display_name="交付负责人",
        member_status="active",
        member_version=1,
        contract_version=CAPACITY_CONTRACT_VERSION,
        timezone="Asia/Shanghai",
        weekly_capacity_hours=Decimal("40"),
        workdays=[1, 2, 3, 4, 5],
        assumptions="容量由交付负责人按未来九十天可投入工时人工确认，不代表实际工时。",
        capacity_source="manual",
        external_calendar_verified=False,
        status="active",
        exceptions=[exception_data()],
        version=1,
        event_count=1,
        last_event_sha256="a" * 64,
        created_by="trusted-admin",
        updated_by="trusted-admin",
        created_at=NOW,
        updated_at=NOW,
        idempotent_replay=replay,
    )


def schedule_data(*, replay: bool = False) -> OpportunityScheduleRunData:
    windows = [
        OpportunityScheduleWindowData(
            window_code=code,
            start_date=date(2026, 8, 10) + timedelta(days=index * 30),
            end_date=date(2026, 8, 10) + timedelta(days=index * 30 + 29),
            available_capacity_hours=Decimal("160"),
            scheduled_effort_hours=Decimal("8") if index == 0 else Decimal("0"),
            utilization_rate=Decimal("0.05") if index == 0 else Decimal("0"),
            action_count=1 if index == 0 else 0,
            blocked_action_count=0,
        )
        for index, code in enumerate(("day_0_30", "day_31_60", "day_61_90"))
    ]
    item = OpportunityScheduleItemData(
        item_id=ITEM_ID,
        action_id=ACTION_ID,
        action_version=2,
        plan_id=PLAN_ID,
        plan_version=1,
        member_id=MEMBER_ID,
        member_version=1,
        calendar_id=CALENDAR_ID,
        calendar_version=1,
        window_code="day_0_30",
        schedule_state="scheduled",
        reason_codes=[],
        planned_start_at=NOW,
        planned_due_at=NOW + timedelta(days=7),
        estimated_effort_hours=Decimal("8"),
        scheduled_effort_hours=Decimal("8"),
        peak_daily_utilization=Decimal("0.2"),
        item_sha256="b" * 64,
    )
    return OpportunityScheduleRunData(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        contract_version=SCHEDULE_CONTRACT_VERSION,
        policy_version=SCHEDULE_POLICY_VERSION,
        as_of_date=date(2026, 8, 10),
        horizon_days=90,
        status="complete",
        source_manifest_sha256="c" * 64,
        result_sha256="d" * 64,
        action_count=1,
        scheduled_count=1,
        blocked_count=0,
        outside_horizon_count=0,
        capacity_conflict_count=0,
        schedule_feasible=True,
        windows=windows,
        items=[item],
        outcome_forecast_allowed=False,
        known_limitations=["manual_capacity_not_external_calendar"],
        created_by="trusted-admin",
        created_at=NOW,
        idempotent_replay=replay,
    )


class FakeScheduleRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def portfolio(self, tenant_id, project_id):  # noqa: ANN001
        self.calls.append(("portfolio", project_id))
        return OpportunityCapacityPortfolioData(
            project_id=project_id,
            contract_version=CAPACITY_CONTRACT_VERSION,
            active_member_count=1,
            configured_calendar_count=1,
            capacity_coverage_complete=True,
            calendars=[calendar_data()],
            latest_schedule=schedule_data(),
            outcome_forecast_allowed=False,
            known_limitations=["manual_capacity_not_external_calendar"],
        )

    def put_calendar(self, tenant_id, project_id, member_id, payload, *, actor, trace_id):  # noqa: ANN001,E501
        assert actor == "trusted-admin"
        assert payload.workdays == [1, 2, 3, 4, 5]
        self.calls.append(("calendar", member_id))
        return calendar_data()

    def put_exception(self, tenant_id, project_id, member_id, exception_date, payload, *, actor, trace_id):  # noqa: ANN001,E501
        assert actor == "trusted-admin"
        assert payload.available_hours == Decimal("0")
        self.calls.append(("exception", member_id))
        return exception_data()

    def create_schedule(self, tenant_id, project_id, payload, *, idempotency_key, actor, trace_id):  # noqa: ANN001,E501
        assert actor == "trusted-admin"
        assert idempotency_key == "schedule-create-key"
        self.calls.append(("schedule", project_id))
        return schedule_data()


def admin_headers() -> dict[str, str]:
    return {
        "tenant-id": "tenant_capacity",
        "X-AIRank-User-Id": "trusted-admin",
        "X-AIRank-Permissions": "airank:opportunity:admin",
    }


def validate(name: str, instance: object) -> None:
    Draft202012Validator(
        load_schema(name),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
        registry=registry(),
    ).validate(instance)


def test_capacity_schedule_api_uses_trusted_admin_and_versioned_contracts(monkeypatch) -> None:  # noqa: ANN001
    repository = FakeScheduleRepository()
    monkeypatch.setattr(
        opportunity_schedule_routes,
        "OPPORTUNITY_SCHEDULE_REPOSITORY",
        repository,
    )
    client = TestClient(app)
    calendar = client.put(
        f"/api/v1/projects/{PROJECT_ID}/opportunity-action-team-members/{MEMBER_ID}/capacity-calendar",
        headers=admin_headers(),
        json={
            "timezone": "Asia/Shanghai",
            "weekly_capacity_hours": "40",
            "workdays": [1, 2, 3, 4, 5],
            "assumptions": "容量由交付负责人按未来九十天可投入工时人工确认，不代表实际工时。",
        },
    )
    exception = client.put(
        f"/api/v1/projects/{PROJECT_ID}/opportunity-action-team-members/{MEMBER_ID}/capacity-calendar/exceptions/2026-08-17",
        headers=admin_headers(),
        json={"available_hours": "0", "reason": "客户确认当日团队不可用，容量覆盖为零。"},
    )
    schedule = client.post(
        f"/api/v1/projects/{PROJECT_ID}/opportunity-execution-schedules",
        headers={**admin_headers(), "Idempotency-Key": "schedule-create-key"},
        json={"as_of_date": "2026-08-10", "horizon_days": 90},
    )
    portfolio = client.get(
        f"/api/v1/projects/{PROJECT_ID}/opportunity-capacity-portfolio",
        headers=admin_headers(),
    )
    assert [calendar.status_code, exception.status_code, schedule.status_code, portfolio.status_code] == [200, 200, 201, 200]
    assert repository.calls == [
        ("calendar", MEMBER_ID),
        ("exception", MEMBER_ID),
        ("schedule", PROJECT_ID),
        ("portfolio", PROJECT_ID),
    ]
    validate("opportunity_capacity_calendar_response.schema.json", calendar.json())
    validate("opportunity_capacity_exception_response.schema.json", exception.json())
    validate("opportunity_schedule_run_response.schema.json", schedule.json())
    validate("opportunity_capacity_portfolio_response.schema.json", portfolio.json())
    assert schedule.json()["data"]["outcome_forecast_allowed"] is False


def test_capacity_inputs_are_strict_and_schedule_horizon_is_fixed() -> None:
    valid = {
        "opportunity_capacity_calendar_put_request.schema.json": {
            "timezone": "Asia/Shanghai",
            "weekly_capacity_hours": "40",
            "workdays": [1, 2, 3, 4, 5],
            "assumptions": "容量由交付负责人按未来九十天可投入工时人工确认，不代表实际工时。",
        },
        "opportunity_capacity_exception_put_request.schema.json": {
            "available_hours": "0",
            "reason": "客户确认当日团队不可用，容量覆盖为零。",
        },
        "opportunity_schedule_create_request.schema.json": {
            "as_of_date": "2026-08-10",
            "horizon_days": 90,
        },
    }
    for name, instance in valid.items():
        schema = load_schema(name)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(instance)
        with pytest.raises(Exception):
            Draft202012Validator(schema).validate({**instance, "unexpected": True})
    with pytest.raises(PydanticValidationError):
        OpportunityCapacityCalendarPutRequest(
            timezone="Not/A-Timezone",
            weekly_capacity_hours=Decimal("40"),
            workdays=[1, 1],
            assumptions="容量由交付负责人按未来九十天可投入工时人工确认，不代表实际工时。",
        )
    with pytest.raises(PydanticValidationError):
        OpportunityCapacityCalendarPutRequest(
            timezone="Asia/Shanghai",
            weekly_capacity_hours=Decimal("40"),
            workdays=[1, 2, 3, 4, 5],
            assumptions=" " * 20,
        )
    calendar_schema = Draft202012Validator(
        load_schema("opportunity_capacity_calendar_put_request.schema.json")
    )
    exception_schema = Draft202012Validator(
        load_schema("opportunity_capacity_exception_put_request.schema.json")
    )
    assert not calendar_schema.is_valid(
        {
            **valid["opportunity_capacity_calendar_put_request.schema.json"],
            "weekly_capacity_hours": "168.01",
        }
    )
    assert not exception_schema.is_valid(
        {
            **valid["opportunity_capacity_exception_put_request.schema.json"],
            "available_hours": "24.01",
        }
    )


def test_capacity_schedule_detects_shared_member_daily_overallocation() -> None:
    repository = object.__new__(MySQLOpportunityScheduleRepository)
    calendar = {
        "id": CALENDAR_ID,
        "member_id": MEMBER_ID,
        "version": 1,
        "timezone": "UTC",
        "weekly_capacity_hours": Decimal("8"),
        "workdays_json": json.dumps([1]),
        "request_sha256": "1" * 64,
        "status": "active",
    }

    def action(seed: str) -> dict:
        return {
            "id": "opportunity_action_" + seed * 20,
            "version": 2,
            "status": "in_progress",
            "assigned_to": "delivery-owner",
            "routing_team_id": TEAM_ID,
            "routing_member_id": MEMBER_ID,
            "routing_member_version": 1,
            "latest_snapshot_sha256": seed * 64,
            "plan_id": "opportunity_plan_" + seed * 20,
            "plan_status": "approved",
            "estimated_effort_hours": Decimal("8"),
            "planned_start_at": NOW,
            "planned_due_at": NOW + timedelta(hours=8),
            "plan_version": 1,
            "plan_request_sha256": seed * 64,
            "member_status": "active",
            "member_version_current": 1,
            "calendar_id": CALENDAR_ID,
            "calendar_status": "active",
            "calendar_timezone": "UTC",
            "weekly_capacity_hours": Decimal("8"),
            "workdays_json": json.dumps([1]),
            "calendar_version": 1,
            "calendar_request_sha256": "1" * 64,
        }

    calculated = repository._calculate_schedule(
        "tenant_capacity",
        PROJECT_ID,
        date(2026, 8, 10),
        {
            "actions": [action("a"), action("b")],
            "dependencies": [],
            "exceptions": [],
            "active_calendars": [calendar],
        },
    )
    assert calculated["action_count"] == 2
    assert calculated["scheduled_count"] == 0
    assert calculated["blocked_count"] == 2
    assert calculated["capacity_conflict_count"] == 2
    assert calculated["schedule_feasible"] is False
    assert {
        item["values"]["schedule_state"] for item in calculated["items"]
    } == {"capacity_exceeded"}
    assert calculated["windows_json"][0]["scheduled_effort_hours"] == "16.00"

    dependent = action("c")
    dependency_aware = repository._calculate_schedule(
        "tenant_capacity",
        PROJECT_ID,
        date(2026, 8, 10),
        {
            "actions": [dependent, action("d")],
            "dependencies": [
                {
                    "action_id": dependent["id"],
                    "status": "active",
                    "prerequisite_status": "in_progress",
                }
            ],
            "exceptions": [],
            "active_calendars": [calendar],
        },
    )
    dependent_item = next(
        item for item in dependency_aware["items"] if item["values"]["action_id"] == dependent["id"]
    )
    assert dependent_item["values"]["schedule_state"] == "dependency_blocked"
    assert set(dependent_item["hash_record"]["reason_codes"]) == {
        "active_dependency_not_satisfied",
        "daily_capacity_exceeded",
    }

    historical = action("e")
    historical["planned_start_at"] = NOW - timedelta(days=8)
    historical["planned_due_at"] = NOW - timedelta(days=1)
    past = repository._calculate_schedule(
        "tenant_capacity",
        PROJECT_ID,
        date(2026, 8, 10),
        {
            "actions": [historical],
            "dependencies": [],
            "exceptions": [],
            "active_calendars": [calendar],
        },
    )
    assert past["items"][0]["values"]["window_code"] == "outside_horizon"
    assert past["items"][0]["values"]["schedule_state"] == "outside_horizon"
    assert past["schedule_feasible"] is False


def test_capacity_mutations_are_admin_gated(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    with pytest.raises(StarletteHTTPException) as forbidden:
        opportunity_schedule_routes.require_schedule_admin(None)
    assert forbidden.value.status_code == 403
    opportunity_schedule_routes.require_schedule_admin("airank:opportunity:admin")

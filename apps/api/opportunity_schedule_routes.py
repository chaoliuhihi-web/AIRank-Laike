from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, text

from apps.api.opportunity_routes import as_utc, canonical_sha256, error, response_meta, stable_id


router = APIRouter(prefix="/api/v1", tags=["opportunity-capacity-scheduling"])

CAPACITY_CONTRACT_VERSION = "airank.opportunity-capacity-calendar.v1"
SCHEDULE_CONTRACT_VERSION = "airank.opportunity-capacity-schedule.v1"
SCHEDULE_POLICY_VERSION = "airank.opportunity-capacity-policy.v1"
FINAL_ACTION_STATUSES = {"verified_not_observed", "waived"}
WINDOW_CODES = ("day_0_30", "day_31_60", "day_61_90")
BLOCKED_STATES = {
    "unplanned",
    "dates_missing",
    "owner_missing",
    "calendar_missing",
    "calendar_unavailable",
    "dependency_blocked",
    "capacity_exceeded",
}
ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: Optional[datetime]) -> Optional[datetime]:
    return as_utc(value).replace(tzinfo=None) if value is not None else None


def decimal_text(value: Decimal) -> str:
    return format(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f")


def json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def schedule_admin_permission() -> str:
    return (
        os.getenv("AIRANK_OPPORTUNITY_ADMIN_PERMISSION", "airank:opportunity:admin").strip()
        or "airank:opportunity:admin"
    )


def auth_enforcement_required() -> bool:
    return os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower() in {
        "1",
        "true",
        "yes",
        "required",
    }


def require_schedule_admin(permission_header: Optional[str]) -> None:
    if not auth_enforcement_required():
        return
    granted = {
        item.strip() for item in (permission_header or "").split(",") if item.strip()
    }
    required = schedule_admin_permission()
    namespace = required.rsplit(":", 1)[0]
    if not granted.intersection({required, "*", "*:*:*", f"{namespace}:*"}):
        raise error(403, "AUTH_PERMISSION_FORBIDDEN", {"required_permission": required})


def trusted_actor(authenticated_actor: Optional[str]) -> str:
    actor = str(authenticated_actor or "").strip()
    if actor:
        return actor[:128]
    if not auth_enforcement_required():
        return "console-opportunity-scheduler"
    raise error(401, "AUTH_TOKEN_INVALID", {"reason": "authenticated_actor_required"})


class OpportunityCapacityCalendarPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = Field(min_length=1, max_length=64)
    weekly_capacity_hours: Decimal = Field(gt=ZERO, le=Decimal("168"))
    workdays: list[int] = Field(min_length=1, max_length=7)
    assumptions: str = Field(min_length=20, max_length=2000)
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        cleaned = value.strip()
        try:
            ZoneInfo(cleaned)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return cleaned

    @field_validator("workdays")
    @classmethod
    def valid_workdays(cls, value: list[int]) -> list[int]:
        if any(item < 1 or item > 7 for item in value):
            raise ValueError("workdays must use ISO weekday values 1 through 7")
        if len(set(value)) != len(value):
            raise ValueError("workdays must be unique")
        return sorted(value)

    @field_validator("assumptions")
    @classmethod
    def material_assumptions(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 20:
            raise ValueError("assumptions must contain at least 20 non-whitespace characters")
        return cleaned


class OpportunityCapacityExceptionPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_hours: Decimal = Field(ge=ZERO, le=Decimal("24"))
    reason: str = Field(min_length=8, max_length=1000)
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("reason")
    @classmethod
    def material_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 8:
            raise ValueError("reason must contain at least 8 non-whitespace characters")
        return cleaned


class OpportunityScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    horizon_days: Literal[90] = 90


class OpportunityCapacityExceptionData(BaseModel):
    exception_id: str
    exception_date: date
    available_hours: Decimal
    reason: str
    exception_source: Literal["manual"]
    external_calendar_verified: Literal[False]
    version: int = Field(ge=1)
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class OpportunityCapacityCalendarData(BaseModel):
    calendar_id: str
    team_id: str
    member_id: str
    user_id: str
    display_name: Optional[str]
    member_status: Literal["active", "disabled"]
    member_version: int = Field(ge=1)
    contract_version: Literal["airank.opportunity-capacity-calendar.v1"]
    timezone: str
    weekly_capacity_hours: Decimal
    workdays: list[int]
    assumptions: str
    capacity_source: Literal["manual"]
    external_calendar_verified: Literal[False]
    status: Literal["active", "disabled"]
    exceptions: list[OpportunityCapacityExceptionData]
    version: int = Field(ge=1)
    event_count: int = Field(ge=1)
    last_event_sha256: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class OpportunityScheduleWindowData(BaseModel):
    window_code: Literal["day_0_30", "day_31_60", "day_61_90"]
    start_date: date
    end_date: date
    available_capacity_hours: Decimal
    scheduled_effort_hours: Decimal
    utilization_rate: Optional[Decimal]
    action_count: int = Field(ge=0)
    blocked_action_count: int = Field(ge=0)


class OpportunityScheduleItemData(BaseModel):
    item_id: str
    action_id: str
    action_version: int = Field(ge=1)
    plan_id: Optional[str]
    plan_version: Optional[int]
    member_id: Optional[str]
    member_version: Optional[int]
    calendar_id: Optional[str]
    calendar_version: Optional[int]
    window_code: Literal[
        "day_0_30", "day_31_60", "day_61_90", "outside_horizon", "unscheduled"
    ]
    schedule_state: Literal[
        "scheduled",
        "unplanned",
        "dates_missing",
        "owner_missing",
        "calendar_missing",
        "calendar_unavailable",
        "dependency_blocked",
        "capacity_exceeded",
        "outside_horizon",
    ]
    reason_codes: list[str]
    planned_start_at: Optional[datetime]
    planned_due_at: Optional[datetime]
    estimated_effort_hours: Optional[Decimal]
    scheduled_effort_hours: Decimal
    peak_daily_utilization: Optional[Decimal]
    item_sha256: str


class OpportunityScheduleRunData(BaseModel):
    run_id: str
    project_id: str
    contract_version: Literal["airank.opportunity-capacity-schedule.v1"]
    policy_version: Literal["airank.opportunity-capacity-policy.v1"]
    as_of_date: date
    horizon_days: Literal[90]
    status: Literal["complete"]
    source_manifest_sha256: str
    result_sha256: str
    action_count: int = Field(ge=0)
    scheduled_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    outside_horizon_count: int = Field(ge=0)
    capacity_conflict_count: int = Field(ge=0)
    schedule_feasible: bool
    windows: list[OpportunityScheduleWindowData]
    items: list[OpportunityScheduleItemData]
    outcome_forecast_allowed: Literal[False]
    known_limitations: list[str]
    created_by: str
    created_at: datetime
    idempotent_replay: bool = False


class OpportunityCapacityPortfolioData(BaseModel):
    project_id: str
    contract_version: Literal["airank.opportunity-capacity-calendar.v1"]
    active_member_count: int = Field(ge=0)
    configured_calendar_count: int = Field(ge=0)
    capacity_coverage_complete: bool
    calendars: list[OpportunityCapacityCalendarData]
    latest_schedule: Optional[OpportunityScheduleRunData]
    outcome_forecast_allowed: Literal[False]
    known_limitations: list[str]


class OpportunityCapacityPortfolioResponse(BaseModel):
    data: OpportunityCapacityPortfolioData
    meta: dict[str, str]


class OpportunityCapacityCalendarResponse(BaseModel):
    data: OpportunityCapacityCalendarData
    meta: dict[str, str]


class OpportunityCapacityExceptionResponse(BaseModel):
    data: OpportunityCapacityExceptionData
    meta: dict[str, str]


class OpportunityScheduleRunResponse(BaseModel):
    data: OpportunityScheduleRunData
    meta: dict[str, str]


class OpportunityScheduleRepository(Protocol):
    def portfolio(self, tenant_id: str, project_id: str) -> OpportunityCapacityPortfolioData: ...

    def put_calendar(
        self,
        tenant_id: str,
        project_id: str,
        member_id: str,
        payload: OpportunityCapacityCalendarPutRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityCapacityCalendarData: ...

    def put_exception(
        self,
        tenant_id: str,
        project_id: str,
        member_id: str,
        exception_date: date,
        payload: OpportunityCapacityExceptionPutRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityCapacityExceptionData: ...

    def create_schedule(
        self,
        tenant_id: str,
        project_id: str,
        payload: OpportunityScheduleCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityScheduleRunData: ...


class InMemoryOpportunityScheduleRepository:
    def portfolio(self, tenant_id: str, project_id: str) -> OpportunityCapacityPortfolioData:
        return OpportunityCapacityPortfolioData(
            project_id=project_id,
            contract_version=CAPACITY_CONTRACT_VERSION,
            active_member_count=0,
            configured_calendar_count=0,
            capacity_coverage_complete=False,
            calendars=[],
            latest_schedule=None,
            outcome_forecast_allowed=False,
            known_limitations=["database_not_configured"],
        )

    def put_calendar(self, *args: Any, **kwargs: Any) -> OpportunityCapacityCalendarData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_capacity"})

    def put_exception(self, *args: Any, **kwargs: Any) -> OpportunityCapacityExceptionData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_capacity"})

    def create_schedule(self, *args: Any, **kwargs: Any) -> OpportunityScheduleRunData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_capacity"})


class MySQLOpportunityScheduleRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def portfolio(self, tenant_id: str, project_id: str) -> OpportunityCapacityPortfolioData:
        with self.engine.begin() as conn:
            self._require_project(conn, tenant_id, project_id)
            calendars = self._calendars(conn, tenant_id, project_id)
            active_member_count = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM airank_opportunity_action_team_members "
                        "WHERE tenant_id=:tenant_id AND project_id=:project_id AND status='active'"
                    ),
                    {"tenant_id": tenant_id, "project_id": project_id},
                ).scalar_one()
            )
            active_calendar_members = {
                item.member_id
                for item in calendars
                if item.status == "active" and item.member_status == "active"
            }
            latest = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_schedule_runs "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().first()
            limitations = [
                "manual_capacity_not_external_calendar",
                "human_estimate_not_timesheet_invoice_or_spend",
                "schedule_not_growth_or_recommendation_forecast",
            ]
            if active_member_count and len(active_calendar_members) < active_member_count:
                limitations.append("capacity_calendar_coverage_incomplete")
            return OpportunityCapacityPortfolioData(
                project_id=project_id,
                contract_version=CAPACITY_CONTRACT_VERSION,
                active_member_count=active_member_count,
                configured_calendar_count=len(active_calendar_members),
                capacity_coverage_complete=(
                    active_member_count > 0
                    and len(active_calendar_members) == active_member_count
                ),
                calendars=calendars,
                latest_schedule=self._schedule_data(conn, latest) if latest else None,
                outcome_forecast_allowed=False,
                known_limitations=limitations,
            )

    def put_calendar(
        self,
        tenant_id: str,
        project_id: str,
        member_id: str,
        payload: OpportunityCapacityCalendarPutRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityCapacityCalendarData:
        record = {
            "contract_version": CAPACITY_CONTRACT_VERSION,
            "timezone": payload.timezone,
            "weekly_capacity_hours": decimal_text(payload.weekly_capacity_hours),
            "workdays": payload.workdays,
            "assumptions": payload.assumptions.strip(),
            "capacity_source": "manual",
            "external_calendar_verified": False,
        }
        request_sha256 = canonical_sha256(record)
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            member = self._member(conn, tenant_id, project_id, member_id)
            suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_capacity_calendars "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND member_id=:member_id" + suffix
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "member_id": member_id,
                },
            ).mappings().first()
            if existing is not None and str(existing["request_sha256"]) == request_sha256:
                return self._calendar_data(conn, existing, idempotent_replay=True)
            if existing is None:
                if payload.expected_version is not None:
                    raise error(
                        409,
                        "OPPORTUNITY_CAPACITY_VERSION_CONFLICT",
                        {"expected_version": payload.expected_version, "actual_version": None},
                    )
                calendar_id = stable_id("opportunity_capacity_calendar", tenant_id, project_id, member_id)
                version = 1
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_capacity_calendars (
                          id, tenant_id, project_id, team_id, member_id, user_id,
                          contract_version, timezone, weekly_capacity_hours,
                          workdays_json, assumptions, capacity_source,
                          external_calendar_verified, status, request_sha256,
                          version, created_by, updated_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :team_id, :member_id,
                          :user_id, :contract_version, :timezone, :weekly_hours,
                          :workdays_json, :assumptions, 'manual', 0, 'active',
                          :request_sha256, 1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": calendar_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "team_id": member["team_id"],
                        "member_id": member_id,
                        "user_id": member["user_id"],
                        "contract_version": CAPACITY_CONTRACT_VERSION,
                        "timezone": payload.timezone,
                        "weekly_hours": payload.weekly_capacity_hours,
                        "workdays_json": json.dumps(payload.workdays),
                        "assumptions": payload.assumptions.strip(),
                        "request_sha256": request_sha256,
                        "actor": actor,
                        "at": at,
                    },
                )
                event_type = "capacity_calendar_created"
            else:
                actual = int(existing["version"])
                if payload.expected_version != actual:
                    raise error(
                        409,
                        "OPPORTUNITY_CAPACITY_VERSION_CONFLICT",
                        {"expected_version": payload.expected_version, "actual_version": actual},
                    )
                calendar_id = str(existing["id"])
                version = actual + 1
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_capacity_calendars
                        SET team_id=:team_id, user_id=:user_id, timezone=:timezone,
                            weekly_capacity_hours=:weekly_hours,
                            workdays_json=:workdays_json, assumptions=:assumptions,
                            capacity_source='manual', external_calendar_verified=0,
                            status='active', request_sha256=:request_sha256,
                            version=:version, updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:id
                        """
                    ),
                    {
                        "team_id": member["team_id"],
                        "user_id": member["user_id"],
                        "timezone": payload.timezone,
                        "weekly_hours": payload.weekly_capacity_hours,
                        "workdays_json": json.dumps(payload.workdays),
                        "assumptions": payload.assumptions.strip(),
                        "request_sha256": request_sha256,
                        "version": version,
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "id": calendar_id,
                    },
                )
                event_type = "capacity_calendar_updated"
            self._append_event(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                aggregate_type="calendar",
                aggregate_id=calendar_id,
                aggregate_version=version,
                event_type=event_type,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                payload=record,
                created_at=at,
            )
            row = conn.execute(
                text("SELECT * FROM airank_opportunity_capacity_calendars WHERE id=:id"),
                {"id": calendar_id},
            ).mappings().one()
            return self._calendar_data(conn, row)

    def put_exception(
        self,
        tenant_id: str,
        project_id: str,
        member_id: str,
        exception_date: date,
        payload: OpportunityCapacityExceptionPutRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityCapacityExceptionData:
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            calendar = self._calendar_row(conn, tenant_id, project_id, member_id, lock=True)
            record = {
                "contract_version": CAPACITY_CONTRACT_VERSION,
                "calendar_id": str(calendar["id"]),
                "exception_date": exception_date.isoformat(),
                "available_hours": decimal_text(payload.available_hours),
                "reason": payload.reason.strip(),
                "exception_source": "manual",
                "external_calendar_verified": False,
            }
            request_sha256 = canonical_sha256(record)
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_capacity_exceptions "
                    "WHERE tenant_id=:tenant_id AND calendar_id=:calendar_id "
                    "AND exception_date=:exception_date FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_id,
                    "calendar_id": calendar["id"],
                    "exception_date": exception_date,
                },
            ).mappings().first()
            if existing is not None and str(existing["request_sha256"]) == request_sha256:
                return self._exception_data(existing, idempotent_replay=True)
            if existing is None:
                if payload.expected_version is not None:
                    raise error(
                        409,
                        "OPPORTUNITY_CAPACITY_EXCEPTION_VERSION_CONFLICT",
                        {"expected_version": payload.expected_version, "actual_version": None},
                    )
                exception_id = stable_id(
                    "opportunity_capacity_exception",
                    tenant_id,
                    str(calendar["id"]),
                    exception_date.isoformat(),
                )
                version = 1
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_capacity_exceptions (
                          id, tenant_id, project_id, calendar_id, exception_date,
                          available_hours, reason, exception_source,
                          external_calendar_verified, request_sha256, version,
                          created_by, updated_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :calendar_id,
                          :exception_date, :available_hours, :reason, 'manual', 0,
                          :request_sha256, 1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": exception_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "calendar_id": calendar["id"],
                        "exception_date": exception_date,
                        "available_hours": payload.available_hours,
                        "reason": payload.reason.strip(),
                        "request_sha256": request_sha256,
                        "actor": actor,
                        "at": at,
                    },
                )
                event_type = "capacity_exception_created"
            else:
                actual = int(existing["version"])
                if payload.expected_version != actual:
                    raise error(
                        409,
                        "OPPORTUNITY_CAPACITY_EXCEPTION_VERSION_CONFLICT",
                        {"expected_version": payload.expected_version, "actual_version": actual},
                    )
                exception_id = str(existing["id"])
                version = actual + 1
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_capacity_exceptions
                        SET available_hours=:available_hours, reason=:reason,
                            exception_source='manual', external_calendar_verified=0,
                            request_sha256=:request_sha256, version=:version,
                            updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:id
                        """
                    ),
                    {
                        "available_hours": payload.available_hours,
                        "reason": payload.reason.strip(),
                        "request_sha256": request_sha256,
                        "version": version,
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "id": exception_id,
                    },
                )
                event_type = "capacity_exception_updated"
            self._append_event(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                aggregate_type="exception",
                aggregate_id=exception_id,
                aggregate_version=version,
                event_type=event_type,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                payload=record,
                created_at=at,
            )
            row = conn.execute(
                text("SELECT * FROM airank_opportunity_capacity_exceptions WHERE id=:id"),
                {"id": exception_id},
            ).mappings().one()
            return self._exception_data(row)

    def create_schedule(
        self,
        tenant_id: str,
        project_id: str,
        payload: OpportunityScheduleCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityScheduleRunData:
        request_record = {
            "contract_version": SCHEDULE_CONTRACT_VERSION,
            "policy_version": SCHEDULE_POLICY_VERSION,
            "as_of_date": payload.as_of_date.isoformat(),
            "horizon_days": payload.horizon_days,
            "outcome_forecast_allowed": False,
        }
        request_sha256 = canonical_sha256(request_record)
        created_at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            self._require_project(conn, tenant_id, project_id)
            replay = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_schedule_runs "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND idempotency_key=:idempotency_key FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
            if replay is not None:
                if str(replay["request_sha256"]) != request_sha256:
                    raise error(
                        409,
                        "OPPORTUNITY_SCHEDULE_IDEMPOTENCY_CONFLICT",
                        {"idempotency_key": idempotency_key},
                    )
                return self._schedule_data(conn, replay, idempotent_replay=True)

            sources = self._schedule_sources(conn, tenant_id, project_id)
            source_manifest_sha256 = canonical_sha256(sources["manifest"])
            calculated = self._calculate_schedule(
                tenant_id,
                project_id,
                payload.as_of_date,
                sources,
            )
            run_id = stable_id(
                "opportunity_schedule_run",
                tenant_id,
                project_id,
                payload.as_of_date.isoformat(),
                source_manifest_sha256,
                SCHEDULE_POLICY_VERSION,
                idempotency_key,
            )
            items_for_hash = [item["hash_record"] for item in calculated["items"]]
            result_record = {
                "contract_version": SCHEDULE_CONTRACT_VERSION,
                "policy_version": SCHEDULE_POLICY_VERSION,
                "as_of_date": payload.as_of_date.isoformat(),
                "horizon_days": 90,
                "source_manifest_sha256": source_manifest_sha256,
                "windows": calculated["windows_json"],
                "items": items_for_hash,
                "outcome_forecast_allowed": False,
            }
            result_sha256 = canonical_sha256(result_record)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_opportunity_schedule_runs (
                      id, tenant_id, project_id, contract_version, policy_version,
                      as_of_date, horizon_days, status, idempotency_key,
                      request_sha256, source_manifest_sha256, result_sha256,
                      action_count, scheduled_count, blocked_count,
                      outside_horizon_count, capacity_conflict_count,
                      schedule_feasible, outcome_forecast_allowed, windows_json,
                      known_limitations_json, created_by, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :contract_version,
                      :policy_version, :as_of_date, 90, 'complete',
                      :idempotency_key, :request_sha256,
                      :source_manifest_sha256, :result_sha256, :action_count,
                      :scheduled_count, :blocked_count, :outside_horizon_count,
                      :capacity_conflict_count, :schedule_feasible, 0,
                      :windows_json, :known_limitations_json, :created_by,
                      :created_at
                    )
                    """
                ),
                {
                    "id": run_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "contract_version": SCHEDULE_CONTRACT_VERSION,
                    "policy_version": SCHEDULE_POLICY_VERSION,
                    "as_of_date": payload.as_of_date,
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "source_manifest_sha256": source_manifest_sha256,
                    "result_sha256": result_sha256,
                    "action_count": calculated["action_count"],
                    "scheduled_count": calculated["scheduled_count"],
                    "blocked_count": calculated["blocked_count"],
                    "outside_horizon_count": calculated["outside_horizon_count"],
                    "capacity_conflict_count": calculated["capacity_conflict_count"],
                    "schedule_feasible": calculated["schedule_feasible"],
                    "windows_json": json.dumps(calculated["windows_json"], ensure_ascii=False),
                    "known_limitations_json": json.dumps(calculated["known_limitations"]),
                    "created_by": actor,
                    "created_at": created_at,
                },
            )
            for item in calculated["items"]:
                values = item["values"]
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_schedule_items (
                          id, tenant_id, project_id, run_id, action_id,
                          action_version, plan_id, plan_version, member_id,
                          member_version, calendar_id, calendar_version,
                          window_code, schedule_state, reason_codes_json,
                          planned_start_at, planned_due_at,
                          estimated_effort_hours, scheduled_effort_hours,
                          peak_daily_utilization, item_sha256, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :run_id, :action_id,
                          :action_version, :plan_id, :plan_version, :member_id,
                          :member_version, :calendar_id, :calendar_version,
                          :window_code, :schedule_state, :reason_codes_json,
                          :planned_start_at, :planned_due_at,
                          :estimated_effort_hours, :scheduled_effort_hours,
                          :peak_daily_utilization, :item_sha256, :created_at
                        )
                        """
                    ),
                    {
                        **values,
                        "id": stable_id("opportunity_schedule_item", run_id, values["action_id"]),
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "run_id": run_id,
                        "created_at": created_at,
                    },
                )
            row = conn.execute(
                text("SELECT * FROM airank_opportunity_schedule_runs WHERE id=:id"),
                {"id": run_id},
            ).mappings().one()
            return self._schedule_data(conn, row)

    @staticmethod
    def _require_project(conn: Any, tenant_id: str, project_id: str) -> None:
        row = conn.execute(
            text(
                "SELECT id FROM airank_projects WHERE tenant_id=:tenant_id "
                "AND id=:project_id AND deleted_at IS NULL"
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).first()
        if row is None:
            raise error(404, "PROJECT_NOT_FOUND", {"project_id": project_id})

    @classmethod
    def _member(cls, conn: Any, tenant_id: str, project_id: str, member_id: str) -> Mapping[str, Any]:
        cls._require_project(conn, tenant_id, project_id)
        row = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_action_team_members "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:member_id"
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "member_id": member_id},
        ).mappings().first()
        if row is None or str(row["status"]) != "active":
            raise error(404, "OPPORTUNITY_CAPACITY_MEMBER_NOT_FOUND", {"member_id": member_id})
        return row

    def _calendar_row(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        member_id: str,
        *,
        lock: bool = False,
    ) -> Mapping[str, Any]:
        suffix = " FOR UPDATE" if lock and self.engine.dialect.name == "mysql" else ""
        row = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_capacity_calendars "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "AND member_id=:member_id" + suffix
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "member_id": member_id},
        ).mappings().first()
        if row is None:
            raise error(
                404,
                "OPPORTUNITY_CAPACITY_CALENDAR_NOT_FOUND",
                {"member_id": member_id},
            )
        return row

    def _calendars(self, conn: Any, tenant_id: str, project_id: str) -> list[OpportunityCapacityCalendarData]:
        rows = conn.execute(
            text(
                "SELECT calendar.*, member.display_name, member.status AS member_status, "
                "member.version AS member_version FROM airank_opportunity_capacity_calendars calendar "
                "JOIN airank_opportunity_action_team_members member "
                "ON member.tenant_id=calendar.tenant_id AND member.id=calendar.member_id "
                "WHERE calendar.tenant_id=:tenant_id AND calendar.project_id=:project_id "
                "ORDER BY calendar.team_id, calendar.user_id"
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        return [self._calendar_data(conn, row) for row in rows]

    def _calendar_data(
        self,
        conn: Any,
        row: Mapping[str, Any],
        *,
        idempotent_replay: bool = False,
    ) -> OpportunityCapacityCalendarData:
        enriched = row
        if "member_status" not in row:
            enriched = conn.execute(
                text(
                    "SELECT calendar.*, member.display_name, member.status AS member_status, "
                    "member.version AS member_version FROM airank_opportunity_capacity_calendars calendar "
                    "JOIN airank_opportunity_action_team_members member "
                    "ON member.tenant_id=calendar.tenant_id AND member.id=calendar.member_id "
                    "WHERE calendar.id=:id"
                ),
                {"id": row["id"]},
            ).mappings().one()
        exceptions = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_capacity_exceptions "
                "WHERE tenant_id=:tenant_id AND calendar_id=:calendar_id "
                "ORDER BY exception_date"
            ),
            {"tenant_id": enriched["tenant_id"], "calendar_id": enriched["id"]},
        ).mappings().all()
        events = conn.execute(
            text(
                "SELECT event_sha256 FROM airank_opportunity_capacity_events "
                "WHERE tenant_id=:tenant_id AND aggregate_type='calendar' "
                "AND aggregate_id=:aggregate_id ORDER BY aggregate_version"
            ),
            {"tenant_id": enriched["tenant_id"], "aggregate_id": enriched["id"]},
        ).scalars().all()
        return OpportunityCapacityCalendarData(
            calendar_id=str(enriched["id"]),
            team_id=str(enriched["team_id"]),
            member_id=str(enriched["member_id"]),
            user_id=str(enriched["user_id"]),
            display_name=str(enriched["display_name"]) if enriched["display_name"] else None,
            member_status=str(enriched["member_status"]),
            member_version=int(enriched["member_version"]),
            contract_version=CAPACITY_CONTRACT_VERSION,
            timezone=str(enriched["timezone"]),
            weekly_capacity_hours=Decimal(str(enriched["weekly_capacity_hours"])),
            workdays=[int(item) for item in json_list(enriched["workdays_json"])],
            assumptions=str(enriched["assumptions"]),
            capacity_source="manual",
            external_calendar_verified=False,
            status=str(enriched["status"]),
            exceptions=[self._exception_data(item) for item in exceptions],
            version=int(enriched["version"]),
            event_count=len(events),
            last_event_sha256=str(events[-1]) if events else "",
            created_by=str(enriched["created_by"]),
            updated_by=str(enriched["updated_by"]),
            created_at=as_utc(enriched["created_at"]),
            updated_at=as_utc(enriched["updated_at"]),
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _exception_data(
        row: Mapping[str, Any], *, idempotent_replay: bool = False
    ) -> OpportunityCapacityExceptionData:
        return OpportunityCapacityExceptionData(
            exception_id=str(row["id"]),
            exception_date=row["exception_date"],
            available_hours=Decimal(str(row["available_hours"])),
            reason=str(row["reason"]),
            exception_source="manual",
            external_calendar_verified=False,
            version=int(row["version"]),
            created_by=str(row["created_by"]),
            updated_by=str(row["updated_by"]),
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _manifest_value(value: object) -> object:
        if isinstance(value, datetime):
            return as_utc(value).isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return decimal_text(value)
        return value

    def _schedule_sources(self, conn: Any, tenant_id: str, project_id: str) -> dict[str, Any]:
        actions = list(
            conn.execute(
                text(
                    """
                    SELECT action.*, plan.id AS plan_id, plan.status AS plan_status,
                           plan.estimated_effort_hours, plan.planned_start_at,
                           plan.planned_due_at, plan.version AS plan_version,
                           plan.request_sha256 AS plan_request_sha256,
                           member.status AS member_status,
                           member.version AS member_version_current,
                           calendar.id AS calendar_id,
                           calendar.status AS calendar_status,
                           calendar.timezone AS calendar_timezone,
                           calendar.weekly_capacity_hours,
                           calendar.workdays_json, calendar.version AS calendar_version,
                           calendar.request_sha256 AS calendar_request_sha256
                    FROM airank_opportunity_actions action
                    LEFT JOIN airank_opportunity_action_plans plan
                      ON plan.tenant_id=action.tenant_id AND plan.action_id=action.id
                    LEFT JOIN airank_opportunity_action_team_members member
                      ON member.tenant_id=action.tenant_id
                     AND member.id=action.routing_member_id
                    LEFT JOIN airank_opportunity_capacity_calendars calendar
                      ON calendar.tenant_id=action.tenant_id
                     AND calendar.member_id=action.routing_member_id
                    WHERE action.tenant_id=:tenant_id AND action.project_id=:project_id
                      AND action.status NOT IN ('verified_not_observed','waived')
                    ORDER BY action.created_at, action.id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        )
        dependencies = list(
            conn.execute(
                text(
                    """
                    SELECT dependency.id, dependency.action_id,
                           dependency.prerequisite_action_id, dependency.status,
                           dependency.version, dependency.request_sha256,
                           prerequisite.status AS prerequisite_status
                    FROM airank_opportunity_action_dependencies dependency
                    JOIN airank_opportunity_actions prerequisite
                      ON prerequisite.tenant_id=dependency.tenant_id
                     AND prerequisite.id=dependency.prerequisite_action_id
                    WHERE dependency.tenant_id=:tenant_id
                      AND dependency.project_id=:project_id
                    ORDER BY dependency.id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        )
        exceptions = list(
            conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_capacity_exceptions "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "ORDER BY calendar_id, exception_date"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        )
        active_calendars = list(
            conn.execute(
                text(
                    "SELECT calendar.* FROM airank_opportunity_capacity_calendars calendar "
                    "JOIN airank_opportunity_action_team_members member "
                    "ON member.tenant_id=calendar.tenant_id AND member.id=calendar.member_id "
                    "WHERE calendar.tenant_id=:tenant_id AND calendar.project_id=:project_id "
                    "AND calendar.status='active' AND member.status='active' "
                    "ORDER BY calendar.id"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        )
        action_fields = (
            "id", "version", "status", "assigned_to", "routing_team_id",
            "routing_member_id", "routing_member_version", "latest_snapshot_sha256",
            "plan_id", "plan_status", "estimated_effort_hours", "planned_start_at",
            "planned_due_at", "plan_version", "plan_request_sha256", "member_status",
            "member_version_current", "calendar_id", "calendar_status", "calendar_timezone",
            "weekly_capacity_hours", "workdays_json", "calendar_version",
            "calendar_request_sha256",
        )
        dependency_fields = (
            "id", "action_id", "prerequisite_action_id", "status", "version",
            "request_sha256", "prerequisite_status",
        )
        exception_fields = (
            "id", "calendar_id", "exception_date", "available_hours", "version", "request_sha256",
        )
        calendar_fields = (
            "id", "member_id", "version", "timezone", "weekly_capacity_hours",
            "workdays_json", "request_sha256", "status",
        )
        manifest = {
            "policy_version": SCHEDULE_POLICY_VERSION,
            "actions": [
                {field: self._manifest_value(row[field]) for field in action_fields}
                for row in actions
            ],
            "dependencies": [
                {field: self._manifest_value(row[field]) for field in dependency_fields}
                for row in dependencies
            ],
            "exceptions": [
                {field: self._manifest_value(row[field]) for field in exception_fields}
                for row in exceptions
            ],
            "calendars": [
                {field: self._manifest_value(row[field]) for field in calendar_fields}
                for row in active_calendars
            ],
        }
        return {
            "actions": actions,
            "dependencies": dependencies,
            "exceptions": exceptions,
            "active_calendars": active_calendars,
            "manifest": manifest,
        }

    @staticmethod
    def _dates(start: date, end: date) -> list[date]:
        return [start + timedelta(days=index) for index in range((end - start).days + 1)]

    @staticmethod
    def _window_for(local_due: date, as_of_date: date) -> str:
        offset = (local_due - as_of_date).days
        if offset < 30:
            return "day_0_30"
        if offset < 60:
            return "day_31_60"
        if offset < 90:
            return "day_61_90"
        return "outside_horizon"

    @staticmethod
    def _calendar_available_hours(
        calendar: Mapping[str, Any],
        day: date,
        exception_by_calendar_day: Mapping[tuple[str, date], Decimal],
    ) -> Decimal:
        override = exception_by_calendar_day.get((str(calendar["id"]), day))
        if override is not None:
            return override
        workdays = [int(item) for item in json_list(calendar["workdays_json"])]
        if day.isoweekday() not in workdays or not workdays:
            return ZERO
        return Decimal(str(calendar["weekly_capacity_hours"])) / Decimal(len(workdays))

    def _calculate_schedule(
        self,
        tenant_id: str,
        project_id: str,
        as_of_date: date,
        sources: Mapping[str, Any],
    ) -> dict[str, Any]:
        horizon_end = as_of_date + timedelta(days=89)
        exceptions = {
            (str(row["calendar_id"]), row["exception_date"]): Decimal(str(row["available_hours"]))
            for row in sources["exceptions"]
        }
        calendars = {str(row["id"]): row for row in sources["active_calendars"]}
        dependency_blocked = {
            str(row["action_id"])
            for row in sources["dependencies"]
            if str(row["status"]) == "active"
            and str(row["prerequisite_status"]) not in FINAL_ACTION_STATUSES
        }
        allocations: dict[tuple[str, date], Decimal] = defaultdict(lambda: ZERO)
        item_allocations: dict[str, list[tuple[str, date, Decimal]]] = defaultdict(list)
        prepared: list[dict[str, Any]] = []
        for row in sources["actions"]:
            action_id = str(row["id"])
            reasons: list[str] = []
            state = "scheduled"
            window = "unscheduled"
            plan_id = str(row["plan_id"]) if row["plan_id"] else None
            member_id = str(row["routing_member_id"]) if row["routing_member_id"] else None
            calendar_id = str(row["calendar_id"]) if row["calendar_id"] else None
            effort = Decimal(str(row["estimated_effort_hours"])) if row["estimated_effort_hours"] is not None else None
            scheduled_effort = ZERO
            if not plan_id or str(row["plan_status"] or "") != "approved":
                state = "unplanned"
                reasons.append("approved_plan_missing")
            elif row["planned_start_at"] is None or row["planned_due_at"] is None:
                state = "dates_missing"
                reasons.append("approved_plan_dates_missing")
            elif not row["assigned_to"] or not member_id or str(row["member_status"] or "") != "active":
                state = "owner_missing"
                reasons.append("active_routed_owner_missing")
            elif not calendar_id or calendar_id not in calendars:
                state = "calendar_missing"
                reasons.append("active_capacity_calendar_missing")
            else:
                calendar = calendars[calendar_id]
                zone = ZoneInfo(str(calendar["timezone"]))
                local_start = as_utc(row["planned_start_at"]).astimezone(zone).date()
                local_due = as_utc(row["planned_due_at"]).astimezone(zone).date()
                window = self._window_for(local_due, as_of_date)
                if local_due < as_of_date:
                    state = "outside_horizon"
                    window = "outside_horizon"
                    reasons.append("plan_due_before_as_of")
                if (local_due - local_start).days > 730:
                    state = "calendar_unavailable"
                    reasons.append("plan_date_range_exceeds_policy")
                else:
                    plan_days = [
                        day
                        for day in self._dates(local_start, local_due)
                        if self._calendar_available_hours(calendar, day, exceptions) > ZERO
                    ]
                    if not plan_days:
                        state = "calendar_unavailable"
                        reasons.append("no_available_workday_in_plan_range")
                    elif effort is not None:
                        effort_per_day = effort / Decimal(len(plan_days))
                        for day in plan_days:
                            if as_of_date <= day <= horizon_end:
                                allocations[(calendar_id, day)] += effort_per_day
                                item_allocations[action_id].append((calendar_id, day, effort_per_day))
                                scheduled_effort += effort_per_day
                        if window == "outside_horizon" and not item_allocations[action_id]:
                            state = "outside_horizon"
                            reasons.append("plan_due_outside_90_day_horizon")
            if action_id in dependency_blocked:
                reasons.append("active_dependency_not_satisfied")
                if state == "scheduled":
                    state = "dependency_blocked"
            prepared.append(
                {
                    "row": row,
                    "action_id": action_id,
                    "plan_id": plan_id,
                    "member_id": member_id,
                    "calendar_id": calendar_id,
                    "effort": effort,
                    "scheduled_effort": scheduled_effort,
                    "window": window,
                    "state": state,
                    "reasons": reasons,
                }
            )

        capacity_conflict_actions: set[str] = set()
        items: list[dict[str, Any]] = []
        for item in prepared:
            peak: Optional[Decimal] = None
            for calendar_id, day, _allocated in item_allocations[item["action_id"]]:
                available = self._calendar_available_hours(calendars[calendar_id], day, exceptions)
                utilization = allocations[(calendar_id, day)] / available if available > ZERO else Decimal("9999")
                peak = utilization if peak is None else max(peak, utilization)
                if available <= ZERO or allocations[(calendar_id, day)] > available:
                    capacity_conflict_actions.add(item["action_id"])
            if item["action_id"] in capacity_conflict_actions:
                item["reasons"].append("daily_capacity_exceeded")
                if item["state"] == "scheduled":
                    item["state"] = "capacity_exceeded"
            row = item["row"]
            hash_record = {
                "action_id": item["action_id"],
                "action_version": int(row["version"]),
                "plan_id": item["plan_id"],
                "plan_version": int(row["plan_version"]) if row["plan_version"] is not None else None,
                "member_id": item["member_id"],
                "member_version": int(row["member_version_current"]) if row["member_version_current"] is not None else None,
                "calendar_id": item["calendar_id"],
                "calendar_version": int(row["calendar_version"]) if row["calendar_version"] is not None else None,
                "window_code": item["window"],
                "schedule_state": item["state"],
                "reason_codes": sorted(set(item["reasons"])),
                "planned_start_at": as_utc(row["planned_start_at"]).isoformat() if row["planned_start_at"] else None,
                "planned_due_at": as_utc(row["planned_due_at"]).isoformat() if row["planned_due_at"] else None,
                "estimated_effort_hours": decimal_text(item["effort"]) if item["effort"] is not None else None,
                "scheduled_effort_hours": decimal_text(item["scheduled_effort"]),
                "peak_daily_utilization": format(peak.quantize(FOUR_PLACES), "f") if peak is not None else None,
            }
            item_sha256 = canonical_sha256(hash_record)
            values = {
                "action_id": item["action_id"],
                "action_version": int(row["version"]),
                "plan_id": item["plan_id"],
                "plan_version": int(row["plan_version"]) if row["plan_version"] is not None else None,
                "member_id": item["member_id"],
                "member_version": int(row["member_version_current"]) if row["member_version_current"] is not None else None,
                "calendar_id": item["calendar_id"],
                "calendar_version": int(row["calendar_version"]) if row["calendar_version"] is not None else None,
                "window_code": item["window"],
                "schedule_state": item["state"],
                "reason_codes_json": json.dumps(sorted(set(item["reasons"]))),
                "planned_start_at": database_datetime(row["planned_start_at"]),
                "planned_due_at": database_datetime(row["planned_due_at"]),
                "estimated_effort_hours": item["effort"],
                "scheduled_effort_hours": item["scheduled_effort"],
                "peak_daily_utilization": peak,
                "item_sha256": item_sha256,
            }
            items.append({"hash_record": {**hash_record, "item_sha256": item_sha256}, "values": values})

        windows_json: list[dict[str, object]] = []
        for index, window_code in enumerate(WINDOW_CODES):
            start = as_of_date + timedelta(days=index * 30)
            end = start + timedelta(days=29)
            available = ZERO
            scheduled = ZERO
            for calendar in calendars.values():
                for day in self._dates(start, end):
                    available += self._calendar_available_hours(calendar, day, exceptions)
            for (calendar_id, day), amount in allocations.items():
                if start <= day <= end:
                    scheduled += amount
            window_items = [item for item in items if item["values"]["window_code"] == window_code]
            blocked = [item for item in window_items if item["values"]["schedule_state"] in BLOCKED_STATES]
            utilization = scheduled / available if available > ZERO else None
            windows_json.append(
                {
                    "window_code": window_code,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "available_capacity_hours": decimal_text(available),
                    "scheduled_effort_hours": decimal_text(scheduled),
                    "utilization_rate": format(utilization.quantize(FOUR_PLACES), "f") if utilization is not None else None,
                    "action_count": len(window_items),
                    "blocked_action_count": len(blocked),
                }
            )
        action_count = len(items)
        scheduled_count = sum(item["values"]["schedule_state"] == "scheduled" for item in items)
        outside_count = sum(item["values"]["schedule_state"] == "outside_horizon" for item in items)
        blocked_count = sum(item["values"]["schedule_state"] in BLOCKED_STATES for item in items)
        limitations = [
            "manual_capacity_not_external_calendar",
            "human_estimate_not_timesheet_invoice_or_spend",
            "schedule_not_growth_or_recommendation_forecast",
            "schedule_snapshot_does_not_move_or_complete_actions",
        ]
        return {
            "items": items,
            "windows_json": windows_json,
            "known_limitations": limitations,
            "action_count": action_count,
            "scheduled_count": scheduled_count,
            "blocked_count": blocked_count,
            "outside_horizon_count": outside_count,
            "capacity_conflict_count": len(capacity_conflict_actions),
            "schedule_feasible": bool(action_count) and blocked_count == 0 and outside_count == 0,
        }

    def _schedule_data(
        self,
        conn: Any,
        row: Mapping[str, Any],
        *,
        idempotent_replay: bool = False,
    ) -> OpportunityScheduleRunData:
        item_rows = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_schedule_items "
                "WHERE tenant_id=:tenant_id AND run_id=:run_id ORDER BY action_id"
            ),
            {"tenant_id": row["tenant_id"], "run_id": row["id"]},
        ).mappings().all()
        items = [
            OpportunityScheduleItemData(
                item_id=str(item["id"]),
                action_id=str(item["action_id"]),
                action_version=int(item["action_version"]),
                plan_id=str(item["plan_id"]) if item["plan_id"] else None,
                plan_version=int(item["plan_version"]) if item["plan_version"] is not None else None,
                member_id=str(item["member_id"]) if item["member_id"] else None,
                member_version=int(item["member_version"]) if item["member_version"] is not None else None,
                calendar_id=str(item["calendar_id"]) if item["calendar_id"] else None,
                calendar_version=int(item["calendar_version"]) if item["calendar_version"] is not None else None,
                window_code=str(item["window_code"]),
                schedule_state=str(item["schedule_state"]),
                reason_codes=[str(value) for value in json_list(item["reason_codes_json"])],
                planned_start_at=as_utc(item["planned_start_at"]) if item["planned_start_at"] else None,
                planned_due_at=as_utc(item["planned_due_at"]) if item["planned_due_at"] else None,
                estimated_effort_hours=Decimal(str(item["estimated_effort_hours"])) if item["estimated_effort_hours"] is not None else None,
                scheduled_effort_hours=Decimal(str(item["scheduled_effort_hours"])),
                peak_daily_utilization=Decimal(str(item["peak_daily_utilization"])) if item["peak_daily_utilization"] is not None else None,
                item_sha256=str(item["item_sha256"]),
            )
            for item in item_rows
        ]
        windows = [OpportunityScheduleWindowData.model_validate(item) for item in json_list(row["windows_json"])]
        return OpportunityScheduleRunData(
            run_id=str(row["id"]),
            project_id=str(row["project_id"]),
            contract_version=SCHEDULE_CONTRACT_VERSION,
            policy_version=SCHEDULE_POLICY_VERSION,
            as_of_date=row["as_of_date"],
            horizon_days=90,
            status="complete",
            source_manifest_sha256=str(row["source_manifest_sha256"]),
            result_sha256=str(row["result_sha256"]),
            action_count=int(row["action_count"]),
            scheduled_count=int(row["scheduled_count"]),
            blocked_count=int(row["blocked_count"]),
            outside_horizon_count=int(row["outside_horizon_count"]),
            capacity_conflict_count=int(row["capacity_conflict_count"]),
            schedule_feasible=bool(row["schedule_feasible"]),
            windows=windows,
            items=items,
            outcome_forecast_allowed=False,
            known_limitations=[str(value) for value in json_list(row["known_limitations_json"])],
            created_by=str(row["created_by"]),
            created_at=as_utc(row["created_at"]),
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _append_event(
        conn: Any,
        *,
        tenant_id: str,
        project_id: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: str,
        request_sha256: str,
        actor: str,
        trace_id: str,
        payload: Mapping[str, object],
        created_at: datetime,
    ) -> None:
        previous = conn.execute(
            text(
                "SELECT event_sha256 FROM airank_opportunity_capacity_events "
                "WHERE tenant_id=:tenant_id AND aggregate_type=:aggregate_type "
                "AND aggregate_id=:aggregate_id ORDER BY aggregate_version DESC LIMIT 1"
            ),
            {
                "tenant_id": tenant_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
            },
        ).scalar()
        event_sha256 = canonical_sha256(
            {
                "contract_version": CAPACITY_CONTRACT_VERSION,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "aggregate_version": aggregate_version,
                "event_type": event_type,
                "request_sha256": request_sha256,
                "previous_event_sha256": str(previous) if previous else None,
                "payload": dict(payload),
            }
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_opportunity_capacity_events (
                  id, tenant_id, project_id, aggregate_type, aggregate_id,
                  event_type, aggregate_version, request_sha256,
                  previous_event_sha256, event_sha256, actor_user_id,
                  trace_id, payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :aggregate_type, :aggregate_id,
                  :event_type, :aggregate_version, :request_sha256,
                  :previous_event_sha256, :event_sha256, :actor,
                  :trace_id, :payload_json, :created_at
                )
                """
            ),
            {
                "id": stable_id(
                    "opportunity_capacity_event",
                    aggregate_type,
                    aggregate_id,
                    str(aggregate_version),
                    event_sha256,
                ),
                "tenant_id": tenant_id,
                "project_id": project_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "aggregate_version": aggregate_version,
                "request_sha256": request_sha256,
                "previous_event_sha256": str(previous) if previous else None,
                "event_sha256": event_sha256,
                "actor": actor,
                "trace_id": trace_id,
                "payload_json": json.dumps(dict(payload), ensure_ascii=False, sort_keys=True),
                "created_at": created_at,
            },
        )


def build_repository() -> OpportunityScheduleRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL", "").strip()
    return MySQLOpportunityScheduleRepository(database_url) if database_url else InMemoryOpportunityScheduleRepository()


OPPORTUNITY_SCHEDULE_REPOSITORY: OpportunityScheduleRepository = build_repository()


@router.get(
    "/projects/{project_id}/opportunity-capacity-portfolio",
    response_model=OpportunityCapacityPortfolioResponse,
)
def get_opportunity_capacity_portfolio(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
) -> OpportunityCapacityPortfolioResponse:
    return OpportunityCapacityPortfolioResponse(
        data=OPPORTUNITY_SCHEDULE_REPOSITORY.portfolio(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.put(
    "/projects/{project_id}/opportunity-action-team-members/{member_id}/capacity-calendar",
    response_model=OpportunityCapacityCalendarResponse,
)
def put_opportunity_capacity_calendar(
    project_id: str,
    member_id: str,
    payload: OpportunityCapacityCalendarPutRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityCapacityCalendarResponse:
    require_schedule_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityCapacityCalendarResponse(
        data=OPPORTUNITY_SCHEDULE_REPOSITORY.put_calendar(
            tenant_id,
            project_id,
            member_id,
            payload,
            actor=trusted_actor(authenticated_actor),
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )


@router.put(
    "/projects/{project_id}/opportunity-action-team-members/{member_id}/capacity-calendar/exceptions/{exception_date}",
    response_model=OpportunityCapacityExceptionResponse,
)
def put_opportunity_capacity_exception(
    project_id: str,
    member_id: str,
    exception_date: date,
    payload: OpportunityCapacityExceptionPutRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityCapacityExceptionResponse:
    require_schedule_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityCapacityExceptionResponse(
        data=OPPORTUNITY_SCHEDULE_REPOSITORY.put_exception(
            tenant_id,
            project_id,
            member_id,
            exception_date,
            payload,
            actor=trusted_actor(authenticated_actor),
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )


@router.post(
    "/projects/{project_id}/opportunity-execution-schedules",
    response_model=OpportunityScheduleRunResponse,
    status_code=201,
)
def create_opportunity_execution_schedule(
    project_id: str,
    payload: OpportunityScheduleCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityScheduleRunResponse:
    require_schedule_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityScheduleRunResponse(
        data=OPPORTUNITY_SCHEDULE_REPOSITORY.create_schedule(
            tenant_id,
            project_id,
            payload,
            idempotency_key=idempotency_key,
            actor=trusted_actor(authenticated_actor),
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )

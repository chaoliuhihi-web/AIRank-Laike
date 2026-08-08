from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import create_engine, text

from apps.api.opportunity_routes import as_utc, canonical_sha256, error, response_meta, stable_id


router = APIRouter(prefix="/api/v1", tags=["opportunity-execution-planning"])

PLANNING_CONTRACT_VERSION = "airank.opportunity-execution-plan.v1"
FINAL_ACTION_STATUSES = {"verified_not_observed", "waived"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: Optional[datetime]) -> Optional[datetime]:
    return as_utc(value).replace(tzinfo=None) if value is not None else None


def planning_admin_permission() -> str:
    return (
        os.getenv(
            "AIRANK_OPPORTUNITY_ADMIN_PERMISSION", "airank:opportunity:admin"
        ).strip()
        or "airank:opportunity:admin"
    )


def auth_enforcement_required() -> bool:
    return os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower() in {
        "1",
        "true",
        "yes",
        "required",
    }


def require_planning_admin(permission_header: Optional[str]) -> None:
    if not auth_enforcement_required():
        return
    granted = {
        item.strip() for item in (permission_header or "").split(",") if item.strip()
    }
    required = planning_admin_permission()
    namespace = required.rsplit(":", 1)[0]
    if not granted.intersection({required, "*", "*:*:*", f"{namespace}:*"}):
        raise error(403, "AUTH_PERMISSION_FORBIDDEN", {"required_permission": required})


def trusted_actor(authenticated_actor: Optional[str]) -> str:
    actor = str(authenticated_actor or "").strip()
    if actor:
        return actor[:128]
    if not auth_enforcement_required():
        return "console-opportunity-planner"
    raise error(401, "AUTH_TOKEN_INVALID", {"reason": "authenticated_actor_required"})


class OpportunityExecutionPlanPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["draft", "approved"] = "draft"
    estimated_effort_hours: Decimal = Field(gt=Decimal("0"), le=Decimal("10000"))
    estimated_budget_amount: Decimal = Field(ge=Decimal("0"), le=Decimal("100000000"))
    currency: Literal["CNY"] = "CNY"
    planned_start_at: Optional[datetime] = None
    planned_due_at: Optional[datetime] = None
    assumptions: str = Field(min_length=8, max_length=4000)
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("planned_start_at", "planned_due_at")
    @classmethod
    def require_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("planning timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_plan(self) -> "OpportunityExecutionPlanPutRequest":
        if self.planned_start_at and self.planned_due_at:
            if as_utc(self.planned_due_at) <= as_utc(self.planned_start_at):
                raise ValueError("planned_due_at must be after planned_start_at")
        if self.status == "approved" and len(self.assumptions.strip()) < 20:
            raise ValueError("approved plan assumptions must contain at least 20 characters")
        return self


class OpportunityDependencyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prerequisite_action_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^opportunity_action_[0-9a-f]{20}$",
    )
    dependency_type: Literal["finish_to_start", "evidence_prerequisite"]
    rationale: str = Field(min_length=12, max_length=2000)


class OpportunityDependencyWaiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    waiver_reason: str = Field(min_length=20, max_length=2000)
    acknowledge_no_outcome_claim: Literal[True]


class OpportunityDependencyData(BaseModel):
    dependency_id: str
    action_id: str
    prerequisite_action_id: str
    prerequisite_status: str
    dependency_type: Literal["finish_to_start", "evidence_prerequisite"]
    status: Literal["active", "waived"]
    satisfied: bool
    rationale: str
    waiver_reason: Optional[str]
    version: int = Field(ge=1)
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class OpportunityExecutionPlanData(BaseModel):
    plan_id: str
    action_id: str
    action_status: str
    contract_version: Literal["airank.opportunity-execution-plan.v1"]
    status: Literal["draft", "approved"]
    estimate_source: Literal["human_estimate"]
    estimated_effort_hours: Decimal
    estimated_budget_amount: Decimal
    currency: Literal["CNY"]
    planned_start_at: Optional[datetime]
    planned_due_at: Optional[datetime]
    assumptions: str
    outcome_forecast_allowed: Literal[False]
    dependencies: list[OpportunityDependencyData]
    unsatisfied_dependency_count: int = Field(ge=0)
    version: int = Field(ge=1)
    event_count: int = Field(ge=1)
    last_event_sha256: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class OpportunityExecutionPortfolioData(BaseModel):
    project_id: str
    contract_version: Literal["airank.opportunity-execution-plan.v1"]
    planning_required_count: int = Field(ge=0)
    approved_plan_count: int = Field(ge=0)
    planning_coverage_complete: bool
    total_estimated_effort_hours: Optional[Decimal]
    total_estimated_budget_amount: Optional[Decimal]
    currency: Literal["CNY"]
    topological_order: list[list[str]]
    blocked_action_ids: list[str]
    plans: list[OpportunityExecutionPlanData]
    unplanned_action_ids: list[str]
    outcome_forecast_allowed: Literal[False]
    known_limitations: list[str]


class OpportunityExecutionPortfolioResponse(BaseModel):
    data: OpportunityExecutionPortfolioData
    meta: dict[str, str]


class OpportunityExecutionPlanResponse(BaseModel):
    data: OpportunityExecutionPlanData
    meta: dict[str, str]


class OpportunityDependencyResponse(BaseModel):
    data: OpportunityDependencyData
    meta: dict[str, str]


class OpportunityPlanningRepository(Protocol):
    def portfolio(self, tenant_id: str, project_id: str) -> OpportunityExecutionPortfolioData: ...

    def put_plan(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityExecutionPlanPutRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityExecutionPlanData: ...

    def create_dependency(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityDependencyCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityDependencyData: ...

    def waive_dependency(
        self,
        tenant_id: str,
        project_id: str,
        dependency_id: str,
        payload: OpportunityDependencyWaiveRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityDependencyData: ...


class InMemoryOpportunityPlanningRepository:
    def portfolio(self, tenant_id: str, project_id: str) -> OpportunityExecutionPortfolioData:
        return OpportunityExecutionPortfolioData(
            project_id=project_id,
            contract_version=PLANNING_CONTRACT_VERSION,
            planning_required_count=0,
            approved_plan_count=0,
            planning_coverage_complete=False,
            total_estimated_effort_hours=None,
            total_estimated_budget_amount=None,
            currency="CNY",
            topological_order=[],
            blocked_action_ids=[],
            plans=[],
            unplanned_action_ids=[],
            outcome_forecast_allowed=False,
            known_limitations=["database_not_configured"],
        )

    def put_plan(self, *args: Any, **kwargs: Any) -> OpportunityExecutionPlanData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_planning"})

    def create_dependency(self, *args: Any, **kwargs: Any) -> OpportunityDependencyData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_planning"})

    def waive_dependency(self, *args: Any, **kwargs: Any) -> OpportunityDependencyData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_planning"})


class MySQLOpportunityPlanningRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def portfolio(self, tenant_id: str, project_id: str) -> OpportunityExecutionPortfolioData:
        with self.engine.begin() as conn:
            actions = self._actions(conn, tenant_id, project_id)
            plans = self._plans(conn, tenant_id, project_id)
            plan_by_action = {item.action_id: item for item in plans}
            required = [
                str(row["id"])
                for row in actions
                if str(row["status"]) not in FINAL_ACTION_STATUSES
            ]
            approved = [
                action_id
                for action_id in required
                if action_id in plan_by_action
                and plan_by_action[action_id].status == "approved"
            ]
            coverage = bool(required) and len(approved) == len(required)
            total_effort = (
                sum((plan_by_action[action_id].estimated_effort_hours for action_id in approved), Decimal("0"))
                if coverage
                else None
            )
            total_budget = (
                sum((plan_by_action[action_id].estimated_budget_amount for action_id in approved), Decimal("0"))
                if coverage
                else None
            )
            dependencies = self._dependency_rows(conn, tenant_id, project_id)
            unresolved_dependencies = [
                row
                for row in dependencies
                if str(row["status"]) == "active"
                and str(row["action_id"]) in required
                and str(row["prerequisite_status"]) not in FINAL_ACTION_STATUSES
            ]
            order = self._topological_order(required, unresolved_dependencies)
            blocked = sorted(
                {
                    str(row["action_id"])
                    for row in unresolved_dependencies
                }
            )
            return OpportunityExecutionPortfolioData(
                project_id=project_id,
                contract_version=PLANNING_CONTRACT_VERSION,
                planning_required_count=len(required),
                approved_plan_count=len(approved),
                planning_coverage_complete=coverage,
                total_estimated_effort_hours=total_effort,
                total_estimated_budget_amount=total_budget,
                currency="CNY",
                topological_order=order,
                blocked_action_ids=blocked,
                plans=plans,
                unplanned_action_ids=sorted(set(required) - set(approved)),
                outcome_forecast_allowed=False,
                known_limitations=[
                    "human_estimate_not_invoice_or_spend",
                    "no_growth_or_recommendation_forecast",
                    "calendar_capacity_scheduling_not_implemented",
                ],
            )

    def put_plan(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityExecutionPlanPutRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityExecutionPlanData:
        request_record = {
            "contract_version": PLANNING_CONTRACT_VERSION,
            "action_id": action_id,
            "status": payload.status,
            "estimate_source": "human_estimate",
            "estimated_effort_hours": format(payload.estimated_effort_hours, "f"),
            "estimated_budget_amount": format(payload.estimated_budget_amount, "f"),
            "currency": payload.currency,
            "planned_start_at": as_utc(payload.planned_start_at).isoformat() if payload.planned_start_at else None,
            "planned_due_at": as_utc(payload.planned_due_at).isoformat() if payload.planned_due_at else None,
            "assumptions": payload.assumptions.strip(),
            "outcome_forecast_allowed": False,
        }
        request_sha256 = canonical_sha256(request_record)
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            self._require_action(conn, tenant_id, project_id, action_id, mutable=True)
            suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_action_plans "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND action_id=:action_id" + suffix
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "action_id": action_id},
            ).mappings().first()
            if existing is not None and str(existing["request_sha256"]) == request_sha256:
                return self._plan_data(conn, existing, idempotent_replay=True)
            if existing is None:
                if payload.expected_version is not None:
                    raise error(409, "OPPORTUNITY_PLAN_VERSION_CONFLICT", {"actual_version": None})
                plan_id = stable_id("opportunity_plan", tenant_id, project_id, action_id)
                version = 1
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_action_plans (
                          id, tenant_id, project_id, action_id, contract_version,
                          status, estimate_source, estimated_effort_hours,
                          estimated_budget_amount, currency, planned_start_at,
                          planned_due_at, assumptions, outcome_forecast_allowed,
                          request_sha256, version, created_by, updated_by,
                          created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :action_id,
                          :contract_version, :status, 'human_estimate',
                          :effort, :budget, :currency, :planned_start_at,
                          :planned_due_at, :assumptions, 0, :request_sha256,
                          1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": plan_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "action_id": action_id,
                        "contract_version": PLANNING_CONTRACT_VERSION,
                        "status": payload.status,
                        "effort": payload.estimated_effort_hours,
                        "budget": payload.estimated_budget_amount,
                        "currency": payload.currency,
                        "planned_start_at": database_datetime(payload.planned_start_at),
                        "planned_due_at": database_datetime(payload.planned_due_at),
                        "assumptions": payload.assumptions.strip(),
                        "request_sha256": request_sha256,
                        "actor": actor,
                        "at": at,
                    },
                )
                event_type = "plan_created"
            else:
                actual = int(existing["version"])
                if payload.expected_version != actual:
                    raise error(
                        409,
                        "OPPORTUNITY_PLAN_VERSION_CONFLICT",
                        {"expected_version": payload.expected_version, "actual_version": actual},
                    )
                plan_id = str(existing["id"])
                version = actual + 1
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_plans
                        SET status=:status, estimated_effort_hours=:effort,
                            estimated_budget_amount=:budget, currency=:currency,
                            planned_start_at=:planned_start_at,
                            planned_due_at=:planned_due_at,
                            assumptions=:assumptions, outcome_forecast_allowed=0,
                            request_sha256=:request_sha256, version=:version,
                            updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:id
                        """
                    ),
                    {
                        "status": payload.status,
                        "effort": payload.estimated_effort_hours,
                        "budget": payload.estimated_budget_amount,
                        "currency": payload.currency,
                        "planned_start_at": database_datetime(payload.planned_start_at),
                        "planned_due_at": database_datetime(payload.planned_due_at),
                        "assumptions": payload.assumptions.strip(),
                        "request_sha256": request_sha256,
                        "version": version,
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "id": plan_id,
                    },
                )
                event_type = "plan_updated"
            row = conn.execute(
                text("SELECT * FROM airank_opportunity_action_plans WHERE id=:id"),
                {"id": plan_id},
            ).mappings().one()
            self._append_event(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                aggregate_type="plan",
                aggregate_id=plan_id,
                aggregate_version=version,
                event_type=event_type,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                payload=request_record,
                created_at=at,
            )
            return self._plan_data(conn, row)

    def create_dependency(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityDependencyCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityDependencyData:
        if action_id == payload.prerequisite_action_id:
            raise error(409, "OPPORTUNITY_DEPENDENCY_INVALID", {"reason": "self_dependency"})
        request_record = {
            "contract_version": PLANNING_CONTRACT_VERSION,
            "action_id": action_id,
            "prerequisite_action_id": payload.prerequisite_action_id,
            "dependency_type": payload.dependency_type,
            "rationale": payload.rationale.strip(),
            "outcome_forecast_allowed": False,
        }
        request_sha256 = canonical_sha256(request_record)
        at = database_datetime(utc_now())
        dependency_id = stable_id(
            "opportunity_dependency",
            tenant_id,
            project_id,
            action_id,
            payload.prerequisite_action_id,
            payload.dependency_type,
        )
        with self.engine.begin() as conn:
            target_action = self._require_action(
                conn, tenant_id, project_id, action_id, mutable=True
            )
            if str(target_action["status"]) == "in_progress":
                raise error(
                    409,
                    "OPPORTUNITY_DEPENDENCY_INVALID",
                    {"reason": "target_action_already_in_progress"},
                )
            self._require_action(
                conn, tenant_id, project_id, payload.prerequisite_action_id, mutable=False
            )
            if self.engine.dialect.name == "mysql":
                # Serialize graph mutations per project so concurrent reverse
                # edges cannot both pass cycle detection.
                conn.execute(
                    text(
                        "SELECT id FROM airank_opportunity_actions "
                        "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                        "ORDER BY id FOR UPDATE"
                    ),
                    {"tenant_id": tenant_id, "project_id": project_id},
                ).all()
            replay = conn.execute(
                text(
                    "SELECT dependency.*, prerequisite.status AS prerequisite_status "
                    "FROM airank_opportunity_action_dependencies dependency "
                    "JOIN airank_opportunity_actions prerequisite "
                    "ON prerequisite.tenant_id=dependency.tenant_id "
                    "AND prerequisite.id=dependency.prerequisite_action_id "
                    "WHERE dependency.tenant_id=:tenant_id "
                    "AND dependency.project_id=:project_id "
                    "AND dependency.idempotency_key=:idempotency_key"
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
            if replay is not None:
                if str(replay["request_sha256"]) != request_sha256:
                    raise error(409, "IDEMPOTENCY_CONFLICT", {"operation": "create_dependency"})
                return self._dependency_data(replay, idempotent_replay=True)
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_action_dependencies "
                    "WHERE tenant_id=:tenant_id AND id=:id"
                ),
                {"tenant_id": tenant_id, "id": dependency_id},
            ).mappings().first()
            if existing is not None:
                if str(existing["request_sha256"]) != request_sha256:
                    raise error(409, "IDEMPOTENCY_CONFLICT", {"dependency_id": dependency_id})
                return self._dependency_data(
                    self._dependency_row(conn, tenant_id, dependency_id),
                    idempotent_replay=True,
                )
            rows = self._dependency_rows(conn, tenant_id, project_id)
            candidate = {
                "action_id": action_id,
                "prerequisite_action_id": payload.prerequisite_action_id,
                "status": "active",
            }
            if self._contains_cycle([*rows, candidate]):
                raise error(409, "OPPORTUNITY_DEPENDENCY_CYCLE", {"action_id": action_id})
            conn.execute(
                text(
                    """
                    INSERT INTO airank_opportunity_action_dependencies (
                      id, tenant_id, project_id, action_id,
                      prerequisite_action_id, dependency_type, status,
                      rationale, waiver_reason, waived_by, waived_at,
                      idempotency_key, request_sha256, version, created_by, updated_by,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :action_id,
                      :prerequisite_action_id, :dependency_type, 'active',
                      :rationale, NULL, NULL, NULL, :idempotency_key, :request_sha256,
                      1, :actor, :actor, :at, :at
                    )
                    """
                ),
                {
                    "id": dependency_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "action_id": action_id,
                    "prerequisite_action_id": payload.prerequisite_action_id,
                    "dependency_type": payload.dependency_type,
                    "rationale": payload.rationale.strip(),
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "actor": actor,
                    "at": at,
                },
            )
            row = self._dependency_row(conn, tenant_id, dependency_id)
            self._append_event(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                aggregate_type="dependency",
                aggregate_id=dependency_id,
                aggregate_version=1,
                event_type="dependency_created",
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                payload=request_record,
                created_at=at,
            )
            return self._dependency_data(row)

    def waive_dependency(
        self,
        tenant_id: str,
        project_id: str,
        dependency_id: str,
        payload: OpportunityDependencyWaiveRequest,
        *,
        actor: str,
        trace_id: str,
    ) -> OpportunityDependencyData:
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            row = conn.execute(
                text(
                    """
                    SELECT dependency.*, prerequisite.status AS prerequisite_status
                    FROM airank_opportunity_action_dependencies dependency
                    JOIN airank_opportunity_actions prerequisite
                      ON prerequisite.tenant_id=dependency.tenant_id
                     AND prerequisite.id=dependency.prerequisite_action_id
                    WHERE dependency.tenant_id=:tenant_id
                      AND dependency.project_id=:project_id
                      AND dependency.id=:dependency_id
                    """ + suffix
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "dependency_id": dependency_id,
                },
            ).mappings().first()
            if row is None:
                raise error(404, "OPPORTUNITY_DEPENDENCY_NOT_FOUND", {"dependency_id": dependency_id})
            if str(row["status"]) == "waived":
                return self._dependency_data(row, idempotent_replay=True)
            if int(row["version"]) != payload.expected_version:
                raise error(
                    409,
                    "OPPORTUNITY_DEPENDENCY_VERSION_CONFLICT",
                    {"expected_version": payload.expected_version, "actual_version": int(row["version"])},
                )
            version = int(row["version"]) + 1
            request_record = {
                "contract_version": PLANNING_CONTRACT_VERSION,
                "dependency_id": dependency_id,
                "waiver_reason": payload.waiver_reason.strip(),
                "acknowledge_no_outcome_claim": True,
                "outcome_forecast_allowed": False,
            }
            request_sha256 = canonical_sha256(request_record)
            conn.execute(
                text(
                    """
                    UPDATE airank_opportunity_action_dependencies
                    SET status='waived', waiver_reason=:waiver_reason,
                        waived_by=:actor, waived_at=:at,
                        request_sha256=:request_sha256, version=:version,
                        updated_by=:actor, updated_at=:at
                    WHERE tenant_id=:tenant_id AND id=:dependency_id
                    """
                ),
                {
                    "waiver_reason": payload.waiver_reason.strip(),
                    "actor": actor,
                    "at": at,
                    "request_sha256": request_sha256,
                    "version": version,
                    "tenant_id": tenant_id,
                    "dependency_id": dependency_id,
                },
            )
            updated = self._dependency_row(conn, tenant_id, dependency_id)
            self._append_event(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                aggregate_type="dependency",
                aggregate_id=dependency_id,
                aggregate_version=version,
                event_type="dependency_waived",
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                payload=request_record,
                created_at=at,
            )
            return self._dependency_data(updated)

    @staticmethod
    def _require_action(
        conn: Any,
        tenant_id: str,
        project_id: str,
        action_id: str,
        *,
        mutable: bool,
    ) -> Mapping[str, Any]:
        row = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_actions "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:action_id"
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "action_id": action_id},
        ).mappings().first()
        if row is None:
            raise error(404, "OPPORTUNITY_ACTION_NOT_FOUND", {"action_id": action_id})
        if mutable and str(row["status"]) in FINAL_ACTION_STATUSES:
            raise error(409, "OPPORTUNITY_ACTION_FINAL", {"action_id": action_id})
        return row

    @staticmethod
    def _actions(conn: Any, tenant_id: str, project_id: str) -> list[Mapping[str, Any]]:
        project = conn.execute(
            text(
                "SELECT id FROM airank_projects WHERE tenant_id=:tenant_id "
                "AND id=:project_id AND deleted_at IS NULL"
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).first()
        if project is None:
            raise error(404, "PROJECT_NOT_FOUND", {"project_id": project_id})
        return list(
            conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_actions "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "ORDER BY created_at, id"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        )

    def _plans(self, conn: Any, tenant_id: str, project_id: str) -> list[OpportunityExecutionPlanData]:
        rows = conn.execute(
            text(
                """
                SELECT plan.*, action.status AS action_status
                FROM airank_opportunity_action_plans plan
                JOIN airank_opportunity_actions action
                  ON action.tenant_id=plan.tenant_id AND action.id=plan.action_id
                WHERE plan.tenant_id=:tenant_id AND plan.project_id=:project_id
                ORDER BY plan.created_at, plan.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        return [self._plan_data(conn, row) for row in rows]

    def _plan_data(
        self,
        conn: Any,
        row: Mapping[str, Any],
        *,
        idempotent_replay: bool = False,
    ) -> OpportunityExecutionPlanData:
        action_status = row.get("action_status")
        if action_status is None:
            action_status = conn.execute(
                text(
                    "SELECT status FROM airank_opportunity_actions "
                    "WHERE tenant_id=:tenant_id AND id=:action_id"
                ),
                {"tenant_id": row["tenant_id"], "action_id": row["action_id"]},
            ).scalar_one()
        dependency_rows = self._dependency_rows(
            conn,
            str(row["tenant_id"]),
            str(row["project_id"]),
            action_id=str(row["action_id"]),
        )
        dependencies = [self._dependency_data(item) for item in dependency_rows]
        event_rows = conn.execute(
            text(
                "SELECT event_sha256 FROM airank_opportunity_action_plan_events "
                "WHERE tenant_id=:tenant_id AND aggregate_type='plan' "
                "AND aggregate_id=:plan_id ORDER BY aggregate_version"
            ),
            {"tenant_id": row["tenant_id"], "plan_id": row["id"]},
        ).scalars().all()
        return OpportunityExecutionPlanData(
            plan_id=str(row["id"]),
            action_id=str(row["action_id"]),
            action_status=str(action_status),
            contract_version=PLANNING_CONTRACT_VERSION,
            status=str(row["status"]),
            estimate_source="human_estimate",
            estimated_effort_hours=Decimal(str(row["estimated_effort_hours"])),
            estimated_budget_amount=Decimal(str(row["estimated_budget_amount"])),
            currency="CNY",
            planned_start_at=as_utc(row["planned_start_at"]) if row["planned_start_at"] else None,
            planned_due_at=as_utc(row["planned_due_at"]) if row["planned_due_at"] else None,
            assumptions=str(row["assumptions"]),
            outcome_forecast_allowed=False,
            dependencies=dependencies,
            unsatisfied_dependency_count=sum(
                item.status == "active" and not item.satisfied for item in dependencies
            ),
            version=int(row["version"]),
            event_count=len(event_rows),
            last_event_sha256=str(event_rows[-1]) if event_rows else "",
            created_by=str(row["created_by"]),
            updated_by=str(row["updated_by"]),
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _dependency_rows(
        conn: Any,
        tenant_id: str,
        project_id: str,
        *,
        action_id: Optional[str] = None,
    ) -> list[Mapping[str, Any]]:
        filter_sql = " AND dependency.action_id=:action_id" if action_id else ""
        params: dict[str, object] = {"tenant_id": tenant_id, "project_id": project_id}
        if action_id:
            params["action_id"] = action_id
        return list(
            conn.execute(
                text(
                    """
                    SELECT dependency.*, prerequisite.status AS prerequisite_status
                    FROM airank_opportunity_action_dependencies dependency
                    JOIN airank_opportunity_actions prerequisite
                      ON prerequisite.tenant_id=dependency.tenant_id
                     AND prerequisite.id=dependency.prerequisite_action_id
                    WHERE dependency.tenant_id=:tenant_id
                      AND dependency.project_id=:project_id
                    """ + filter_sql + " ORDER BY dependency.created_at, dependency.id"
                ),
                params,
            ).mappings().all()
        )

    @staticmethod
    def _dependency_row(conn: Any, tenant_id: str, dependency_id: str) -> Mapping[str, Any]:
        row = conn.execute(
            text(
                """
                SELECT dependency.*, prerequisite.status AS prerequisite_status
                FROM airank_opportunity_action_dependencies dependency
                JOIN airank_opportunity_actions prerequisite
                  ON prerequisite.tenant_id=dependency.tenant_id
                 AND prerequisite.id=dependency.prerequisite_action_id
                WHERE dependency.tenant_id=:tenant_id AND dependency.id=:dependency_id
                """
            ),
            {"tenant_id": tenant_id, "dependency_id": dependency_id},
        ).mappings().one()
        return row

    @staticmethod
    def _dependency_data(
        row: Mapping[str, Any], *, idempotent_replay: bool = False
    ) -> OpportunityDependencyData:
        status = str(row["status"])
        prerequisite_status = str(row["prerequisite_status"])
        return OpportunityDependencyData(
            dependency_id=str(row["id"]),
            action_id=str(row["action_id"]),
            prerequisite_action_id=str(row["prerequisite_action_id"]),
            prerequisite_status=prerequisite_status,
            dependency_type=str(row["dependency_type"]),
            status=status,
            satisfied=status == "waived" or prerequisite_status in FINAL_ACTION_STATUSES,
            rationale=str(row["rationale"]),
            waiver_reason=str(row["waiver_reason"]) if row["waiver_reason"] else None,
            version=int(row["version"]),
            created_by=str(row["created_by"]),
            updated_by=str(row["updated_by"]),
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _contains_cycle(rows: list[Mapping[str, Any]]) -> bool:
        graph: dict[str, set[str]] = {}
        nodes: set[str] = set()
        for row in rows:
            if str(row["status"]) != "active":
                continue
            action_id = str(row["action_id"])
            prerequisite_id = str(row["prerequisite_action_id"])
            graph.setdefault(action_id, set()).add(prerequisite_id)
            nodes.update({action_id, prerequisite_id})
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(next_node) for next_node in graph.get(node, set())):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in nodes)

    @staticmethod
    def _topological_order(
        action_ids: list[str], rows: list[Mapping[str, Any]]
    ) -> list[list[str]]:
        nodes = set(action_ids)
        dependents: dict[str, set[str]] = {node: set() for node in nodes}
        indegree = {node: 0 for node in nodes}
        for row in rows:
            if str(row["status"]) != "active":
                continue
            action_id = str(row["action_id"])
            prerequisite_id = str(row["prerequisite_action_id"])
            nodes.update({action_id, prerequisite_id})
            already_linked = action_id in dependents.setdefault(prerequisite_id, set())
            dependents[prerequisite_id].add(action_id)
            dependents.setdefault(action_id, set())
            indegree.setdefault(prerequisite_id, 0)
            if not already_linked:
                indegree[action_id] = indegree.get(action_id, 0) + 1
        layers: list[list[str]] = []
        remaining = set(nodes)
        while remaining:
            layer = sorted(node for node in remaining if indegree.get(node, 0) == 0)
            if not layer:
                raise error(409, "OPPORTUNITY_DEPENDENCY_CYCLE", {"reason": "persisted_cycle"})
            layers.append(layer)
            for node in layer:
                remaining.remove(node)
                for dependent in dependents.get(node, set()):
                    indegree[dependent] -= 1
        return layers

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
                "SELECT event_sha256 FROM airank_opportunity_action_plan_events "
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
                "contract_version": PLANNING_CONTRACT_VERSION,
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
                INSERT INTO airank_opportunity_action_plan_events (
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
                    "opportunity_plan_event",
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


def build_repository() -> OpportunityPlanningRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL", "").strip()
    return MySQLOpportunityPlanningRepository(database_url) if database_url else InMemoryOpportunityPlanningRepository()


OPPORTUNITY_PLANNING_REPOSITORY: OpportunityPlanningRepository = build_repository()


@router.get(
    "/projects/{project_id}/opportunity-execution-portfolio",
    response_model=OpportunityExecutionPortfolioResponse,
)
def get_opportunity_execution_portfolio(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
) -> OpportunityExecutionPortfolioResponse:
    return OpportunityExecutionPortfolioResponse(
        data=OPPORTUNITY_PLANNING_REPOSITORY.portfolio(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.put(
    "/projects/{project_id}/opportunity-actions/{action_id}/plan",
    response_model=OpportunityExecutionPlanResponse,
)
def put_opportunity_execution_plan(
    project_id: str,
    action_id: str,
    payload: OpportunityExecutionPlanPutRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityExecutionPlanResponse:
    require_planning_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityExecutionPlanResponse(
        data=OPPORTUNITY_PLANNING_REPOSITORY.put_plan(
            tenant_id,
            project_id,
            action_id,
            payload,
            actor=trusted_actor(authenticated_actor),
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )


@router.post(
    "/projects/{project_id}/opportunity-actions/{action_id}/dependencies",
    response_model=OpportunityDependencyResponse,
    status_code=201,
)
def create_opportunity_dependency(
    project_id: str,
    action_id: str,
    payload: OpportunityDependencyCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityDependencyResponse:
    require_planning_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityDependencyResponse(
        data=OPPORTUNITY_PLANNING_REPOSITORY.create_dependency(
            tenant_id,
            project_id,
            action_id,
            payload,
            idempotency_key=idempotency_key,
            actor=trusted_actor(authenticated_actor),
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )


@router.post(
    "/projects/{project_id}/opportunity-dependencies/{dependency_id}/waivers",
    response_model=OpportunityDependencyResponse,
)
def waive_opportunity_dependency(
    project_id: str,
    dependency_id: str,
    payload: OpportunityDependencyWaiveRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityDependencyResponse:
    require_planning_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityDependencyResponse(
        data=OPPORTUNITY_PLANNING_REPOSITORY.waive_dependency(
            tenant_id,
            project_id,
            dependency_id,
            payload,
            actor=trusted_actor(authenticated_actor),
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )

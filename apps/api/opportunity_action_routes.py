from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.opportunity_routes import (
    CONTRACT_VERSION as OPPORTUNITY_CONTRACT_VERSION,
    as_utc,
    canonical_sha256,
    error,
    response_meta,
    stable_id,
    trusted_actor,
)
from apps.api.opportunity_routing_routes import (
    resolve_action_claim_route,
    resolve_action_route_summary,
)


router = APIRouter(prefix="/api/v1", tags=["opportunity-actions"])

ACTION_CONTRACT_VERSION = "airank.opportunity-action.v1"
FINAL_STATUSES = {"verified_not_observed", "waived"}
DEFAULT_DUE_DAYS = {"critical": 3, "high": 7, "medium": 14, "low": 30, "info": 30}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def action_error(status_code: int, code: str, details: Mapping[str, object]) -> StarletteHTTPException:
    return error(status_code, code, details)


class OpportunityActionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = Field(min_length=1, max_length=128)
    due_in_days: Optional[int] = Field(default=None, ge=1, le=90)
    action_note: Optional[str] = Field(default=None, min_length=8, max_length=2000)


class OpportunityActionClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)


class OpportunityActionTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transition: Literal["refresh_evidence", "release", "verify_not_observed", "waive"]
    requested_by: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=2000)
    verification_run_id: Optional[str] = Field(default=None, max_length=64)
    acknowledge_no_outcome_claim: bool = False

    @model_validator(mode="after")
    def verify_transition_requirements(self) -> "OpportunityActionTransitionRequest":
        if self.transition == "verify_not_observed" and not self.verification_run_id:
            raise ValueError("verification_run_id is required for verify_not_observed")
        if self.transition in {"verify_not_observed", "waive"} and not self.acknowledge_no_outcome_claim:
            raise ValueError("final transitions require acknowledge_no_outcome_claim=true")
        if self.transition == "waive" and len(self.reason.strip()) < 20:
            raise ValueError("waiver reason must contain at least 20 characters")
        return self


class OpportunityActionData(BaseModel):
    action_id: str
    project_id: str
    opportunity_id: str
    contract_version: Literal["airank.opportunity-action.v1"]
    source_kind: Literal[
        "brand_visibility",
        "citation_support",
        "fact_governance",
        "page_extractability",
    ]
    action_type: str
    status: Literal[
        "open",
        "in_progress",
        "evidence_blocked",
        "verified_not_observed",
        "waived",
    ]
    source_snapshot_id: str
    source_derivation_run_id: str
    source_snapshot_sha256: str
    source_evidence_sha256: str
    latest_snapshot_id: str
    latest_derivation_run_id: str
    latest_snapshot_sha256: str
    latest_evidence_sha256: str
    routing_state: Literal["unrestricted_legacy", "team_routed", "blocked"]
    routing_team_id: Optional[str]
    routing_route_version: Optional[int]
    routing_member_id: Optional[str]
    routing_member_version: Optional[int]
    external_membership_verified: bool
    assigned_to: Optional[str]
    assigned_at: Optional[datetime]
    due_at: datetime
    sla_state: Literal["on_track", "due_soon", "overdue", "final"]
    action_note: str
    verification_run_id: Optional[str]
    verification_basis_sha256: Optional[str]
    closure_reason: Optional[str]
    effect_claim_allowed: Literal[False]
    event_count: int = Field(ge=1)
    last_event_sha256: str
    escalation_count: int = Field(ge=0)
    pending_escalation_count: int = Field(ge=0)
    external_delivery_verified: bool
    latest_escalated_at: Optional[datetime]
    created_by: str
    updated_by: str
    version: int = Field(ge=1)
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class OpportunityActionResponse(BaseModel):
    data: OpportunityActionData
    meta: dict[str, str]


class OpportunityActionListData(BaseModel):
    project_id: str
    contract_version: Literal["airank.opportunity-action.v1"]
    actions: list[OpportunityActionData]
    open_count: int
    evidence_blocked_count: int
    overdue_count: int
    final_count: int


class OpportunityActionListResponse(BaseModel):
    data: OpportunityActionListData
    meta: dict[str, str]


def sla_state(due_at: object, status: str, *, at: Optional[datetime] = None) -> str:
    if status in FINAL_STATUSES:
        return "final"
    now = as_utc(at or utc_now())
    due = as_utc(due_at)
    if due <= now:
        return "overdue"
    if due - now <= timedelta(hours=24):
        return "due_soon"
    return "on_track"


class OpportunityActionRepository(Protocol):
    def create(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
        payload: OpportunityActionCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionData: ...

    def claim(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityActionClaimRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionData: ...

    def transition(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityActionTransitionRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionData: ...

    def list(self, tenant_id: str, project_id: str) -> OpportunityActionListData: ...


class InMemoryOpportunityActionRepository:
    def create(self, tenant_id: str, project_id: str, snapshot_id: str, payload: OpportunityActionCreateRequest, *, idempotency_key: str, actor: str, trace_id: str) -> OpportunityActionData:  # noqa: E501
        raise action_error(404, "OPPORTUNITY_SNAPSHOT_NOT_FOUND", {"snapshot_id": snapshot_id})

    def claim(self, tenant_id: str, project_id: str, action_id: str, payload: OpportunityActionClaimRequest, *, idempotency_key: str, actor: str, trace_id: str) -> OpportunityActionData:  # noqa: E501
        raise action_error(404, "OPPORTUNITY_ACTION_NOT_FOUND", {"action_id": action_id})

    def transition(self, tenant_id: str, project_id: str, action_id: str, payload: OpportunityActionTransitionRequest, *, idempotency_key: str, actor: str, trace_id: str) -> OpportunityActionData:  # noqa: E501
        raise action_error(404, "OPPORTUNITY_ACTION_NOT_FOUND", {"action_id": action_id})

    def list(self, tenant_id: str, project_id: str) -> OpportunityActionListData:
        return OpportunityActionListData(
            project_id=project_id,
            contract_version=ACTION_CONTRACT_VERSION,
            actions=[],
            open_count=0,
            evidence_blocked_count=0,
            overdue_count=0,
            final_count=0,
        )


class MySQLOpportunityActionRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
        payload: OpportunityActionCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionData:
        request_sha256 = canonical_sha256(
            {
                "contract_version": ACTION_CONTRACT_VERSION,
                "snapshot_id": snapshot_id,
                "due_in_days": payload.due_in_days,
                "action_note": payload.action_note,
            }
        )
        with self.engine.begin() as conn:
            snapshot = conn.execute(
                text(
                    """
                    SELECT s.*, r.created_at AS run_created_at
                    FROM airank_intervention_opportunity_snapshots s
                    JOIN airank_opportunity_derivation_runs r
                      ON r.tenant_id=s.tenant_id AND r.id=s.derivation_run_id
                    WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                      AND s.id=:snapshot_id
                    """
                    + (" FOR UPDATE" if self.engine.dialect.name == "mysql" else "")
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "snapshot_id": snapshot_id},
            ).mappings().first()
            if snapshot is None:
                raise action_error(404, "OPPORTUNITY_SNAPSHOT_NOT_FOUND", {"snapshot_id": snapshot_id})
            latest_run = self._latest_run(conn, tenant_id, project_id)
            if latest_run is None or str(latest_run["id"]) != str(snapshot["derivation_run_id"]):
                raise action_error(
                    409,
                    "OPPORTUNITY_ACTION_TRANSITION_INVALID",
                    {"reason": "source_snapshot_is_not_from_latest_complete_derivation"},
                )
            existing = self._find_by_opportunity(
                conn, tenant_id, project_id, str(snapshot["opportunity_id"]), lock=True
            )
            if existing is not None:
                if str(existing["creation_request_sha256"]) != request_sha256:
                    raise action_error(409, "IDEMPOTENCY_CONFLICT", {"opportunity_id": str(snapshot["opportunity_id"])})
                return self._data(conn, existing, idempotent_replay=True)
            for field in ("snapshot_sha256", "source_evidence_sha256"):
                if len(str(snapshot[field] or "")) != 64:
                    raise action_error(
                        409,
                        "OPPORTUNITY_ACTION_TRANSITION_INVALID",
                        {"reason": f"invalid_{field}"},
                    )
            severity = str(snapshot["severity"])
            due_days = payload.due_in_days or DEFAULT_DUE_DAYS.get(severity, 14)
            now = utc_now().replace(tzinfo=None)
            due_at = now + timedelta(days=due_days)
            status = "evidence_blocked" if str(snapshot["state"]) == "blocked_evidence" else "open"
            routing = resolve_action_route_summary(
                conn,
                tenant_id,
                project_id,
                str(snapshot["source_kind"]),
            )
            action_id = stable_id(
                "opportunity_action",
                tenant_id,
                project_id,
                str(snapshot["opportunity_id"]),
                ACTION_CONTRACT_VERSION,
            )
            note = payload.action_note or (
                f"执行 {str(snapshot['recommended_action'])}；完成状态只能由后续完整机会快照验证，"
                "不能据此声明品牌推荐或增长。"
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_opportunity_actions (
                      id, tenant_id, project_id, opportunity_id, contract_version,
                      source_kind, action_type, status, source_snapshot_id,
                      source_derivation_run_id, source_snapshot_sha256,
                      source_evidence_sha256, latest_snapshot_id,
                      latest_derivation_run_id, latest_snapshot_sha256,
                      latest_evidence_sha256, routing_state, routing_team_id,
                      routing_route_version, routing_member_id,
                      routing_member_version, external_membership_verified,
                      assigned_to, assigned_at, due_at,
                      action_note, verification_run_id, verification_basis_sha256,
                      closure_reason, effect_claim_allowed, creation_idempotency_key,
                      creation_request_sha256, created_by, updated_by, version,
                      completed_at, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :opportunity_id, :contract_version,
                      :source_kind, :action_type, :status, :source_snapshot_id,
                      :source_derivation_run_id, :source_snapshot_sha256,
                      :source_evidence_sha256, :source_snapshot_id,
                      :source_derivation_run_id, :source_snapshot_sha256,
                      :source_evidence_sha256, :routing_state, :routing_team_id,
                      :routing_route_version, NULL, NULL, 0,
                      NULL, NULL, :due_at,
                      :action_note, NULL, NULL, NULL, 0, :idempotency_key,
                      :request_sha256, :actor, :actor, 1, NULL, :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": action_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "opportunity_id": str(snapshot["opportunity_id"]),
                    "contract_version": ACTION_CONTRACT_VERSION,
                    "source_kind": str(snapshot["source_kind"]),
                    "action_type": str(snapshot["recommended_action"]),
                    "status": status,
                    "source_snapshot_id": snapshot_id,
                    "source_derivation_run_id": str(snapshot["derivation_run_id"]),
                    "source_snapshot_sha256": str(snapshot["snapshot_sha256"]),
                    "source_evidence_sha256": str(snapshot["source_evidence_sha256"]),
                    "routing_state": routing.routing_state,
                    "routing_team_id": routing.team_id,
                    "routing_route_version": routing.route_version,
                    "due_at": due_at,
                    "action_note": note,
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "actor": actor,
                    "created_at": now,
                },
            )
            action = self._find(conn, tenant_id, project_id, action_id, lock=False)
            assert action is not None
            self._append_event(
                conn,
                action,
                event_type="created",
                from_status=None,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                created_at=now,
            )
            return self._data(conn, action)

    def claim(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityActionClaimRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionData:
        request_sha256 = canonical_sha256(
            {
                "contract_version": ACTION_CONTRACT_VERSION,
                "operation": "claim",
                "action_id": action_id,
                "expected_version": payload.expected_version,
            }
        )
        with self.engine.begin() as conn:
            action = self._required_action(conn, tenant_id, project_id, action_id, lock=True)
            replay = self._event_replay(conn, tenant_id, action_id, idempotency_key, request_sha256)
            if replay:
                return self._data(conn, action, idempotent_replay=True)
            self._validate_mutable(action, payload.expected_version)
            assigned_to = str(action["assigned_to"] or "")
            if assigned_to and assigned_to != actor:
                raise action_error(403, "OPPORTUNITY_ACTION_OWNER_FORBIDDEN", {"action_id": action_id})
            if str(action["status"]) == "open":
                self._require_dependencies_satisfied(
                    conn, tenant_id, project_id, action_id
                )
            routing = resolve_action_claim_route(
                conn,
                self.engine.dialect.name,
                tenant_id,
                project_id,
                str(action["source_kind"]),
                actor,
                action_id=action_id,
                lock_member=True,
            )
            if routing.at_capacity:
                raise action_error(
                    409,
                    "OPPORTUNITY_ACTION_CAPACITY_REACHED",
                    {
                        "active_action_count": routing.active_action_count,
                        "max_active_actions": routing.max_active_actions,
                    },
                )
            if routing.routing_state == "blocked":
                code = (
                    "OPPORTUNITY_ACTION_ROUTING_FORBIDDEN"
                    if routing.reason == "actor_is_not_active_team_member"
                    else "OPPORTUNITY_ACTION_ROUTING_BLOCKED"
                )
                status_code = 403 if code.endswith("FORBIDDEN") else 409
                raise action_error(status_code, code, {"reason": routing.reason or "routing_not_ready"})
            now = utc_now().replace(tzinfo=None)
            next_status = "in_progress" if str(action["status"]) == "open" else str(action["status"])
            next_version = int(action["version"]) + 1
            conn.execute(
                text(
                    """
                    UPDATE airank_opportunity_actions
                    SET assigned_to=:actor,
                        assigned_at=COALESCE(assigned_at, :updated_at),
                        status=:status, routing_state=:routing_state,
                        routing_team_id=:routing_team_id,
                        routing_route_version=:routing_route_version,
                        routing_member_id=:routing_member_id,
                        routing_member_version=:routing_member_version,
                        external_membership_verified=:external_verified,
                        updated_by=:actor,
                        version=:version, updated_at=:updated_at
                    WHERE tenant_id=:tenant_id AND id=:action_id
                    """
                ),
                {
                    "actor": actor,
                    "status": next_status,
                    "routing_state": routing.routing_state,
                    "routing_team_id": routing.team_id,
                    "routing_route_version": routing.route_version,
                    "routing_member_id": routing.member_id,
                    "routing_member_version": routing.member_version,
                    "external_verified": routing.external_membership_verified,
                    "version": next_version,
                    "updated_at": now,
                    "tenant_id": tenant_id,
                    "action_id": action_id,
                },
            )
            updated = self._required_action(conn, tenant_id, project_id, action_id, lock=False)
            self._append_event(
                conn,
                updated,
                event_type="claimed",
                from_status=str(action["status"]),
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                created_at=now,
            )
            return self._data(conn, updated)

    def transition(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        payload: OpportunityActionTransitionRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionData:
        request_sha256 = canonical_sha256(
            {
                "contract_version": ACTION_CONTRACT_VERSION,
                "operation": payload.transition,
                "action_id": action_id,
                "expected_version": payload.expected_version,
                "reason": payload.reason,
                "verification_run_id": payload.verification_run_id,
                "acknowledge_no_outcome_claim": payload.acknowledge_no_outcome_claim,
            }
        )
        with self.engine.begin() as conn:
            action = self._required_action(conn, tenant_id, project_id, action_id, lock=True)
            replay = self._event_replay(conn, tenant_id, action_id, idempotency_key, request_sha256)
            if replay:
                return self._data(conn, action, idempotent_replay=True)
            self._validate_mutable(action, payload.expected_version)
            assigned_to = str(action["assigned_to"] or "")
            if assigned_to and assigned_to != actor:
                raise action_error(403, "OPPORTUNITY_ACTION_OWNER_FORBIDDEN", {"action_id": action_id})
            now = utc_now().replace(tzinfo=None)
            values: dict[str, Any] = {
                "status": str(action["status"]),
                "assigned_to": action["assigned_to"],
                "assigned_at": action["assigned_at"],
                "latest_snapshot_id": str(action["latest_snapshot_id"]),
                "latest_derivation_run_id": str(action["latest_derivation_run_id"]),
                "latest_snapshot_sha256": str(action["latest_snapshot_sha256"]),
                "latest_evidence_sha256": str(action["latest_evidence_sha256"]),
                "routing_state": str(action["routing_state"]),
                "routing_team_id": action["routing_team_id"],
                "routing_route_version": action["routing_route_version"],
                "routing_member_id": action["routing_member_id"],
                "routing_member_version": action["routing_member_version"],
                "external_membership_verified": bool(
                    action["external_membership_verified"]
                ),
                "verification_run_id": action["verification_run_id"],
                "verification_basis_sha256": action["verification_basis_sha256"],
                "closure_reason": action["closure_reason"],
                "completed_at": action["completed_at"],
            }
            event_type = payload.transition
            if payload.transition == "refresh_evidence":
                latest_run = self._latest_run(conn, tenant_id, project_id)
                latest_snapshot = self._latest_snapshot_for_opportunity(
                    conn, tenant_id, project_id, str(action["opportunity_id"]), latest_run
                )
                if latest_snapshot is None or str(latest_snapshot["state"]) != "ready_for_action":
                    raise action_error(
                        409,
                        "OPPORTUNITY_ACTION_VERIFICATION_REQUIRED",
                        {"reason": "latest_opportunity_evidence_is_not_action_ready"},
                    )
                if str(latest_snapshot["id"]) == str(action["latest_snapshot_id"]):
                    raise action_error(
                        409,
                        "OPPORTUNITY_ACTION_TRANSITION_INVALID",
                        {"reason": "no_newer_opportunity_evidence"},
                    )
                if assigned_to:
                    self._require_dependencies_satisfied(
                        conn, tenant_id, project_id, action_id
                    )
                values.update(
                    status="in_progress" if assigned_to else "open",
                    latest_snapshot_id=str(latest_snapshot["id"]),
                    latest_derivation_run_id=str(latest_snapshot["derivation_run_id"]),
                    latest_snapshot_sha256=str(latest_snapshot["snapshot_sha256"]),
                    latest_evidence_sha256=str(latest_snapshot["source_evidence_sha256"]),
                )
            elif payload.transition == "release":
                self._require_owner(action, actor)
                values.update(
                    status="open" if str(action["status"]) == "in_progress" else str(action["status"]),
                    assigned_to=None,
                    assigned_at=None,
                    routing_member_id=None,
                    routing_member_version=None,
                    external_membership_verified=False,
                )
            elif payload.transition == "verify_not_observed":
                self._require_owner(action, actor)
                verification = self._verification_run(
                    conn,
                    tenant_id,
                    project_id,
                    str(payload.verification_run_id),
                    action,
                )
                values.update(
                    status="verified_not_observed",
                    verification_run_id=str(verification["id"]),
                    verification_basis_sha256=str(verification["source_basis_sha256"]),
                    closure_reason=payload.reason,
                    completed_at=now,
                )
            elif payload.transition == "waive":
                self._require_owner(action, actor)
                values.update(status="waived", closure_reason=payload.reason, completed_at=now)
            next_version = int(action["version"]) + 1
            conn.execute(
                text(
                    """
                    UPDATE airank_opportunity_actions
                    SET status=:status, assigned_to=:assigned_to, assigned_at=:assigned_at,
                        latest_snapshot_id=:latest_snapshot_id,
                        latest_derivation_run_id=:latest_derivation_run_id,
                        latest_snapshot_sha256=:latest_snapshot_sha256,
                        latest_evidence_sha256=:latest_evidence_sha256,
                        routing_state=:routing_state,
                        routing_team_id=:routing_team_id,
                        routing_route_version=:routing_route_version,
                        routing_member_id=:routing_member_id,
                        routing_member_version=:routing_member_version,
                        external_membership_verified=:external_membership_verified,
                        verification_run_id=:verification_run_id,
                        verification_basis_sha256=:verification_basis_sha256,
                        closure_reason=:closure_reason, completed_at=:completed_at,
                        effect_claim_allowed=0, updated_by=:actor,
                        version=:version, updated_at=:updated_at
                    WHERE tenant_id=:tenant_id AND id=:action_id
                    """
                ),
                {
                    **values,
                    "actor": actor,
                    "version": next_version,
                    "updated_at": now,
                    "tenant_id": tenant_id,
                    "action_id": action_id,
                },
            )
            updated = self._required_action(conn, tenant_id, project_id, action_id, lock=False)
            self._append_event(
                conn,
                updated,
                event_type=event_type,
                from_status=str(action["status"]),
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                created_at=now,
            )
            return self._data(conn, updated)

    def list(self, tenant_id: str, project_id: str) -> OpportunityActionListData:
        with self.engine.begin() as conn:
            project = conn.execute(
                text(
                    "SELECT id FROM airank_projects WHERE tenant_id=:tenant_id "
                    "AND id=:project_id AND deleted_at IS NULL"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).first()
            if project is None:
                raise action_error(404, "PROJECT_NOT_FOUND", {"project_id": project_id})
            rows = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_actions "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "ORDER BY CASE status WHEN 'evidence_blocked' THEN 0 "
                    "WHEN 'in_progress' THEN 1 WHEN 'open' THEN 2 ELSE 3 END, due_at, id"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
            actions = [self._data(conn, row) for row in rows]
            return OpportunityActionListData(
                project_id=project_id,
                contract_version=ACTION_CONTRACT_VERSION,
                actions=actions,
                open_count=sum(item.status in {"open", "in_progress"} for item in actions),
                evidence_blocked_count=sum(item.status == "evidence_blocked" for item in actions),
                overdue_count=sum(item.sla_state == "overdue" for item in actions),
                final_count=sum(item.status in FINAL_STATUSES for item in actions),
            )

    def _find(self, conn: Any, tenant_id: str, project_id: str, action_id: str, *, lock: bool) -> Optional[Mapping[str, Any]]:
        suffix = " FOR UPDATE" if lock and self.engine.dialect.name == "mysql" else ""
        return conn.execute(
            text(
                "SELECT * FROM airank_opportunity_actions "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:action_id" + suffix
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "action_id": action_id},
        ).mappings().first()

    def _required_action(self, conn: Any, tenant_id: str, project_id: str, action_id: str, *, lock: bool) -> Mapping[str, Any]:
        row = self._find(conn, tenant_id, project_id, action_id, lock=lock)
        if row is None:
            raise action_error(404, "OPPORTUNITY_ACTION_NOT_FOUND", {"action_id": action_id})
        return row

    def _find_by_opportunity(self, conn: Any, tenant_id: str, project_id: str, opportunity_id: str, *, lock: bool) -> Optional[Mapping[str, Any]]:
        suffix = " FOR UPDATE" if lock and self.engine.dialect.name == "mysql" else ""
        return conn.execute(
            text(
                "SELECT * FROM airank_opportunity_actions WHERE tenant_id=:tenant_id "
                "AND project_id=:project_id AND opportunity_id=:opportunity_id "
                "AND contract_version=:contract_version" + suffix
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "opportunity_id": opportunity_id,
                "contract_version": ACTION_CONTRACT_VERSION,
            },
        ).mappings().first()

    @staticmethod
    def _latest_run(conn: Any, tenant_id: str, project_id: str) -> Optional[Mapping[str, Any]]:
        return conn.execute(
            text(
                "SELECT * FROM airank_opportunity_derivation_runs "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "ORDER BY created_at DESC, id DESC LIMIT 1"
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().first()

    @staticmethod
    def _latest_snapshot_for_opportunity(
        conn: Any,
        tenant_id: str,
        project_id: str,
        opportunity_id: str,
        latest_run: Optional[Mapping[str, Any]],
    ) -> Optional[Mapping[str, Any]]:
        if latest_run is None:
            return None
        return conn.execute(
            text(
                "SELECT * FROM airank_intervention_opportunity_snapshots "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "AND derivation_run_id=:run_id AND opportunity_id=:opportunity_id"
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": str(latest_run["id"]),
                "opportunity_id": opportunity_id,
            },
        ).mappings().first()

    def _verification_run(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        run_id: str,
        action: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        latest = self._latest_run(conn, tenant_id, project_id)
        if latest is None or str(latest["id"]) != run_id:
            raise action_error(
                409,
                "OPPORTUNITY_ACTION_VERIFICATION_REQUIRED",
                {"reason": "verification_run_must_be_latest_complete_derivation"},
            )
        source_run = conn.execute(
            text(
                "SELECT created_at FROM airank_opportunity_derivation_runs "
                "WHERE tenant_id=:tenant_id AND id=:run_id"
            ),
            {"tenant_id": tenant_id, "run_id": str(action["source_derivation_run_id"])},
        ).mappings().first()
        if source_run is None or as_utc(latest["created_at"]) <= as_utc(source_run["created_at"]):
            raise action_error(
                409,
                "OPPORTUNITY_ACTION_VERIFICATION_REQUIRED",
                {"reason": "verification_run_is_not_newer_than_source"},
            )
        opportunity_id = str(action["opportunity_id"])
        latest_ids = set(json_list(latest["opportunity_ids_json"]))
        if int(latest["opportunity_count"]) != len(latest_ids):
            raise action_error(
                409,
                "OPPORTUNITY_ACTION_VERIFICATION_REQUIRED",
                {"reason": "verification_run_opportunity_manifest_is_inconsistent"},
            )
        if opportunity_id in latest_ids:
            raise action_error(
                409,
                "OPPORTUNITY_ACTION_VERIFICATION_REQUIRED",
                {"reason": "opportunity_still_present_in_verification_run"},
            )
        if len(str(latest["source_basis_sha256"] or "")) != 64:
            raise action_error(
                409,
                "OPPORTUNITY_ACTION_VERIFICATION_REQUIRED",
                {"reason": "verification_basis_hash_invalid"},
            )
        return latest

    @staticmethod
    def _validate_mutable(action: Mapping[str, Any], expected_version: int) -> None:
        if str(action["status"]) in FINAL_STATUSES:
            raise action_error(409, "OPPORTUNITY_ACTION_FINAL", {"action_id": str(action["id"])})
        if int(action["version"]) != expected_version:
            raise action_error(
                409,
                "OPPORTUNITY_ACTION_VERSION_CONFLICT",
                {"expected_version": expected_version, "actual_version": int(action["version"])},
            )

    @staticmethod
    def _require_owner(action: Mapping[str, Any], actor: str) -> None:
        if str(action["assigned_to"] or "") != actor:
            raise action_error(403, "OPPORTUNITY_ACTION_OWNER_FORBIDDEN", {"action_id": str(action["id"])})

    @staticmethod
    def _require_dependencies_satisfied(
        conn: Any,
        tenant_id: str,
        project_id: str,
        action_id: str,
    ) -> None:
        rows = conn.execute(
            text(
                """
                SELECT dependency.id
                FROM airank_opportunity_action_dependencies dependency
                JOIN airank_opportunity_actions prerequisite
                  ON prerequisite.tenant_id=dependency.tenant_id
                 AND prerequisite.id=dependency.prerequisite_action_id
                WHERE dependency.tenant_id=:tenant_id
                  AND dependency.project_id=:project_id
                  AND dependency.action_id=:action_id
                  AND dependency.status='active'
                  AND prerequisite.status NOT IN ('verified_not_observed', 'waived')
                ORDER BY dependency.id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "action_id": action_id,
            },
        ).scalars().all()
        if rows:
            raise action_error(
                409,
                "OPPORTUNITY_ACTION_DEPENDENCY_BLOCKED",
                {"unsatisfied_dependency_count": len(rows)},
            )

    @staticmethod
    def _event_replay(conn: Any, tenant_id: str, action_id: str, idempotency_key: str, request_sha256: str) -> bool:
        row = conn.execute(
            text(
                "SELECT request_sha256 FROM airank_opportunity_action_events "
                "WHERE tenant_id=:tenant_id AND action_id=:action_id "
                "AND idempotency_key=:idempotency_key"
            ),
            {"tenant_id": tenant_id, "action_id": action_id, "idempotency_key": idempotency_key},
        ).mappings().first()
        if row is None:
            return False
        if str(row["request_sha256"]) != request_sha256:
            raise action_error(409, "IDEMPOTENCY_CONFLICT", {"action_id": action_id})
        return True

    def _append_event(
        self,
        conn: Any,
        action: Mapping[str, Any],
        *,
        event_type: str,
        from_status: Optional[str],
        idempotency_key: str,
        request_sha256: str,
        actor: str,
        trace_id: str,
        created_at: datetime,
    ) -> None:
        previous = conn.execute(
            text(
                "SELECT event_sha256 FROM airank_opportunity_action_events "
                "WHERE tenant_id=:tenant_id AND action_id=:action_id "
                "ORDER BY action_version DESC LIMIT 1"
            ),
            {"tenant_id": str(action["tenant_id"]), "action_id": str(action["id"])},
        ).scalar()
        payload = {
            "contract_version": ACTION_CONTRACT_VERSION,
            "opportunity_id": str(action["opportunity_id"]),
            "status": str(action["status"]),
            "assigned_to": str(action["assigned_to"]) if action["assigned_to"] else None,
            "due_at": as_utc(action["due_at"]).isoformat(),
            "latest_snapshot_id": str(action["latest_snapshot_id"]),
            "latest_snapshot_sha256": str(action["latest_snapshot_sha256"]),
            "latest_evidence_sha256": str(action["latest_evidence_sha256"]),
            "routing_state": str(action["routing_state"]),
            "routing_team_id": str(action["routing_team_id"]) if action["routing_team_id"] else None,
            "routing_route_version": int(action["routing_route_version"]) if action["routing_route_version"] is not None else None,
            "routing_member_id": str(action["routing_member_id"]) if action["routing_member_id"] else None,
            "routing_member_version": int(action["routing_member_version"]) if action["routing_member_version"] is not None else None,
            "external_membership_verified": bool(action["external_membership_verified"]),
            "verification_run_id": str(action["verification_run_id"]) if action["verification_run_id"] else None,
            "verification_basis_sha256": str(action["verification_basis_sha256"]) if action["verification_basis_sha256"] else None,
            "effect_claim_allowed": False,
        }
        event_sha256 = canonical_sha256(
            {
                "action_id": str(action["id"]),
                "event_type": event_type,
                "from_status": from_status,
                "to_status": str(action["status"]),
                "action_version": int(action["version"]),
                "request_sha256": request_sha256,
                "previous_event_sha256": str(previous) if previous else None,
                "payload": payload,
            }
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_opportunity_action_events (
                  id, tenant_id, project_id, action_id, event_type,
                  from_status, to_status, action_version, idempotency_key,
                  request_sha256, previous_event_sha256, event_sha256,
                  actor_user_id, trace_id, payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :action_id, :event_type,
                  :from_status, :to_status, :action_version, :idempotency_key,
                  :request_sha256, :previous_event_sha256, :event_sha256,
                  :actor, :trace_id, :payload_json, :created_at
                )
                """
            ),
            {
                "id": stable_id("opportunity_action_event", str(action["id"]), str(action["version"]), event_sha256),
                "tenant_id": str(action["tenant_id"]),
                "project_id": str(action["project_id"]),
                "action_id": str(action["id"]),
                "event_type": event_type,
                "from_status": from_status,
                "to_status": str(action["status"]),
                "action_version": int(action["version"]),
                "idempotency_key": idempotency_key,
                "request_sha256": request_sha256,
                "previous_event_sha256": str(previous) if previous else None,
                "event_sha256": event_sha256,
                "actor": actor,
                "trace_id": trace_id,
                "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                "created_at": created_at,
            },
        )

    def _data(self, conn: Any, action: Mapping[str, Any], *, idempotent_replay: bool = False) -> OpportunityActionData:
        events = conn.execute(
            text(
                "SELECT event_sha256 FROM airank_opportunity_action_events "
                "WHERE tenant_id=:tenant_id AND action_id=:action_id "
                "ORDER BY action_version"
            ),
            {"tenant_id": str(action["tenant_id"]), "action_id": str(action["id"])},
        ).scalars().all()
        escalation = conn.execute(
            text(
                """
                SELECT COUNT(event.id) AS escalation_count,
                       SUM(CASE WHEN event.status='pending' THEN 1 ELSE 0 END)
                         AS pending_count,
                       MAX(event.created_at) AS latest_escalated_at,
                       MAX(CASE WHEN event.status='published'
                                      AND delivery.status='succeeded'
                                THEN 1 ELSE 0 END) AS delivery_verified
                FROM airank_outbox_events event
                LEFT JOIN airank_notification_deliveries delivery
                  ON delivery.tenant_id=event.tenant_id
                 AND delivery.outbox_event_id=event.id
                 AND delivery.channel='webhook'
                WHERE event.tenant_id=:tenant_id
                  AND event.aggregate_type='opportunity_action'
                  AND event.aggregate_id=:action_id
                  AND event.event_type='opportunity_action.sla_overdue.v1'
                """
            ),
            {"tenant_id": str(action["tenant_id"]), "action_id": str(action["id"])},
        ).mappings().one()
        return OpportunityActionData(
            action_id=str(action["id"]),
            project_id=str(action["project_id"]),
            opportunity_id=str(action["opportunity_id"]),
            contract_version=ACTION_CONTRACT_VERSION,
            source_kind=str(action["source_kind"]),
            action_type=str(action["action_type"]),
            status=str(action["status"]),
            source_snapshot_id=str(action["source_snapshot_id"]),
            source_derivation_run_id=str(action["source_derivation_run_id"]),
            source_snapshot_sha256=str(action["source_snapshot_sha256"]),
            source_evidence_sha256=str(action["source_evidence_sha256"]),
            latest_snapshot_id=str(action["latest_snapshot_id"]),
            latest_derivation_run_id=str(action["latest_derivation_run_id"]),
            latest_snapshot_sha256=str(action["latest_snapshot_sha256"]),
            latest_evidence_sha256=str(action["latest_evidence_sha256"]),
            routing_state=str(action["routing_state"]),
            routing_team_id=str(action["routing_team_id"]) if action["routing_team_id"] else None,
            routing_route_version=int(action["routing_route_version"]) if action["routing_route_version"] is not None else None,
            routing_member_id=str(action["routing_member_id"]) if action["routing_member_id"] else None,
            routing_member_version=int(action["routing_member_version"]) if action["routing_member_version"] is not None else None,
            external_membership_verified=bool(action["external_membership_verified"]),
            assigned_to=str(action["assigned_to"]) if action["assigned_to"] else None,
            assigned_at=as_utc(action["assigned_at"]) if action["assigned_at"] else None,
            due_at=as_utc(action["due_at"]),
            sla_state=sla_state(action["due_at"], str(action["status"])),
            action_note=str(action["action_note"]),
            verification_run_id=str(action["verification_run_id"]) if action["verification_run_id"] else None,
            verification_basis_sha256=str(action["verification_basis_sha256"]) if action["verification_basis_sha256"] else None,
            closure_reason=str(action["closure_reason"]) if action["closure_reason"] else None,
            effect_claim_allowed=False,
            event_count=len(events),
            last_event_sha256=str(events[-1]) if events else "",
            escalation_count=int(escalation["escalation_count"] or 0),
            pending_escalation_count=int(escalation["pending_count"] or 0),
            external_delivery_verified=bool(escalation["delivery_verified"]),
            latest_escalated_at=(
                as_utc(escalation["latest_escalated_at"])
                if escalation["latest_escalated_at"]
                else None
            ),
            created_by=str(action["created_by"]),
            updated_by=str(action["updated_by"]),
            version=int(action["version"]),
            completed_at=as_utc(action["completed_at"]) if action["completed_at"] else None,
            created_at=as_utc(action["created_at"]),
            updated_at=as_utc(action["updated_at"]),
            idempotent_replay=idempotent_replay,
        )


def build_repository() -> OpportunityActionRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL", "").strip()
    return MySQLOpportunityActionRepository(database_url) if database_url else InMemoryOpportunityActionRepository()


OPPORTUNITY_ACTION_REPOSITORY: OpportunityActionRepository = build_repository()


@router.post(
    "/projects/{project_id}/opportunities/{snapshot_id}/actions",
    response_model=OpportunityActionResponse,
    status_code=201,
)
def create_opportunity_action(
    project_id: str,
    snapshot_id: str,
    payload: OpportunityActionCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> OpportunityActionResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    return OpportunityActionResponse(
        data=OPPORTUNITY_ACTION_REPOSITORY.create(
            tenant_id,
            project_id,
            snapshot_id,
            payload,
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )


@router.get(
    "/projects/{project_id}/opportunity-actions",
    response_model=OpportunityActionListResponse,
)
def list_opportunity_actions(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
) -> OpportunityActionListResponse:
    return OpportunityActionListResponse(
        data=OPPORTUNITY_ACTION_REPOSITORY.list(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.post(
    "/projects/{project_id}/opportunity-actions/{action_id}/claims",
    response_model=OpportunityActionResponse,
)
def claim_opportunity_action(
    project_id: str,
    action_id: str,
    payload: OpportunityActionClaimRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> OpportunityActionResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    return OpportunityActionResponse(
        data=OPPORTUNITY_ACTION_REPOSITORY.claim(
            tenant_id,
            project_id,
            action_id,
            payload,
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )


@router.post(
    "/projects/{project_id}/opportunity-actions/{action_id}/transitions",
    response_model=OpportunityActionResponse,
)
def transition_opportunity_action(
    project_id: str,
    action_id: str,
    payload: OpportunityActionTransitionRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> OpportunityActionResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    return OpportunityActionResponse(
        data=OPPORTUNITY_ACTION_REPOSITORY.transition(
            tenant_id,
            project_id,
            action_id,
            payload,
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from threading import RLock
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_xinghe_adapter import (
    YudaoDirectoryError,
    YudaoReviewerDirectoryClient,
    YudaoReviewerDirectorySnapshot,
)


router = APIRouter(prefix="/api/v1", tags=["evidence-review-routing"])
TRACE_HEADER = "X-AIRank-Trace-Id"
REVIEWER_ROLES = ("secondary", "adjudicator")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_admin_permission() -> str:
    return (
        os.getenv("AIRANK_REVIEW_ADMIN_PERMISSION", "airank:review:admin").strip()
        or "airank:review:admin"
    )


def auth_enforcement_required() -> bool:
    return os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled").strip().lower() in {
        "1",
        "true",
        "yes",
        "required",
    }


def require_review_admin(permission_header: Optional[str]) -> None:
    if not auth_enforcement_required():
        return
    granted = {
        item.strip()
        for item in (permission_header or "").split(",")
        if item.strip()
    }
    required = review_admin_permission()
    namespace = required.rsplit(":", 1)[0]
    if not granted.intersection({required, "*", "*:*:*", f"{namespace}:*"}):
        raise StarletteHTTPException(
            403,
            detail={
                "code": "AUTH_PERMISSION_FORBIDDEN",
                "details": {"required_permission": required},
            },
        )


def trusted_actor(authenticated_actor: Optional[str]) -> str:
    actor = str(authenticated_actor or "console-review-admin").strip()
    if not actor:
        raise StarletteHTTPException(401, detail={"code": "AUTH_REQUIRED"})
    return actor[:64]


class ReviewerTeamCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)


class ReviewerTeamMemberUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    priority: int = Field(default=100, ge=1, le=10_000)
    max_active_assignments: int = Field(default=5, ge=1, le=100)
    receives_escalations: bool = True
    expected_version: Optional[int] = Field(default=None, ge=1)


class ReviewerRoleRoutePutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(min_length=1, max_length=64)
    expected_version: Optional[int] = Field(default=None, ge=1)


class ReviewerDirectoryBindingPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_group_id: str = Field(min_length=1, max_length=128)
    sync_enabled: bool = True
    sync_interval_minutes: int = Field(default=60, ge=15, le=10_080)
    default_priority: int = Field(default=100, ge=1, le=10_000)
    default_max_active_assignments: int = Field(default=5, ge=1, le=100)
    default_receives_escalations: bool = True
    expected_version: Optional[int] = Field(default=None, ge=1)


class ReviewerTeamMemberData(BaseModel):
    member_id: str
    user_id: str
    display_name: Optional[str]
    reviewer_role: Literal["secondary", "adjudicator"]
    priority: int
    max_active_assignments: int
    receives_escalations: bool
    status: Literal["active", "disabled"]
    membership_source: Literal["manual", "yudao"]
    external_membership_verified: bool
    version: int
    updated_at: datetime


class ReviewerTeamData(BaseModel):
    team_id: str
    name: str
    status: Literal["active", "disabled"]
    external_source: Literal["manual", "yudao"]
    external_group_id: Optional[str]
    external_sync_state: Literal[
        "not_configured", "pending", "verified", "stale", "failed"
    ]
    version: int
    member_count: int
    members: list[ReviewerTeamMemberData]
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class ReviewerRoleRouteData(BaseModel):
    route_id: str
    reviewer_role: Literal["secondary", "adjudicator"]
    team_id: str
    team_name: str
    routing_strategy: Literal["manual_claim"]
    status: Literal["active", "disabled"]
    version: int
    eligible_member_count: int
    escalation_recipient_count: int
    routing_ready: bool
    updated_at: datetime


class ReviewerDirectoryBindingData(BaseModel):
    binding_id: str
    team_id: str
    team_name: str
    reviewer_role: Literal["secondary", "adjudicator"]
    external_source: Literal["yudao"] = "yudao"
    external_group_id: str
    status: Literal["active", "disabled"]
    sync_enabled: bool
    sync_interval_minutes: int
    default_priority: int
    default_max_active_assignments: int
    default_receives_escalations: bool
    last_sync_state: Literal[
        "not_configured", "pending", "verified", "stale", "failed"
    ]
    last_sync_run_id: Optional[str]
    last_synced_at: Optional[datetime]
    next_sync_at: Optional[datetime]
    last_error_code: Optional[str]
    version: int
    updated_at: datetime


class ReviewerDirectorySyncRunData(BaseModel):
    run_id: str
    binding_id: str
    team_id: str
    reviewer_role: Literal["secondary", "adjudicator"]
    external_group_id: str
    status: Literal["running", "succeeded", "failed"]
    endpoint_host: Optional[str]
    response_sha256: Optional[str]
    discovered_member_count: int = Field(ge=0)
    active_member_count: int = Field(ge=0)
    upserted_member_count: int = Field(ge=0)
    disabled_member_count: int = Field(ge=0)
    error_code: Optional[str]
    retryable: bool
    started_at: datetime
    finished_at: Optional[datetime]
    idempotent_replay: bool = False


class ReviewerRoutingData(BaseModel):
    project_id: str
    routing_mode: Literal["unrestricted_legacy", "team_routed", "blocked"]
    external_sync_state: Literal[
        "not_configured", "pending", "verified", "stale", "failed"
    ]
    teams: list[ReviewerTeamData]
    routes: list[ReviewerRoleRouteData]
    sync_bindings: list[ReviewerDirectoryBindingData]
    recent_sync_runs: list[ReviewerDirectorySyncRunData]
    known_limitations: list[str]


class ReviewerRoutingResponse(BaseModel):
    data: ReviewerRoutingData
    meta: dict[str, str]


@dataclass(frozen=True)
class ReviewerRoleEligibility:
    routing_mode: str
    allowed: bool
    at_capacity: bool
    team_id: str | None
    route_version: int | None
    active_assignment_count: int
    max_active_assignments: int | None
    reason: str | None


@dataclass(frozen=True)
class ReviewerEscalationRouteSnapshot:
    routing_state: str
    team_id: str | None
    route_version: int | None
    eligible_recipient_count: int
    external_sync_state: str


def resolve_actor_role_eligibility(
    conn: Any,
    tenant_id: str,
    project_id: str,
    actor: str,
    reviewer_role: str,
    *,
    lock_member: bool = False,
    as_of: datetime | None = None,
) -> ReviewerRoleEligibility:
    if reviewer_role not in REVIEWER_ROLES:
        raise ValueError("unsupported reviewer role")
    route = conn.execute(
        text(
            """
            SELECT route.team_id, route.version AS route_version,
                   team.status AS team_status
            FROM airank_evidence_review_routes route
            LEFT JOIN airank_evidence_review_teams team
              ON team.tenant_id=route.tenant_id AND team.id=route.team_id
            WHERE route.tenant_id=:tenant_id AND route.project_id=:project_id
              AND route.reviewer_role=:reviewer_role AND route.status='active'
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "reviewer_role": reviewer_role,
        },
    ).mappings().first()
    if route is None:
        configured_route_count = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_evidence_review_routes "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND status='active'"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).scalar_one()
        )
        if configured_route_count > 0:
            return ReviewerRoleEligibility(
                routing_mode="team_routed",
                allowed=False,
                at_capacity=False,
                team_id=None,
                route_version=None,
                active_assignment_count=0,
                max_active_assignments=None,
                reason="role_unconfigured",
            )
        return ReviewerRoleEligibility(
            routing_mode="unrestricted_legacy",
            allowed=True,
            at_capacity=False,
            team_id=None,
            route_version=None,
            active_assignment_count=0,
            max_active_assignments=None,
            reason=None,
        )
    if str(route["team_status"] or "") != "active":
        return ReviewerRoleEligibility(
            routing_mode="team_routed",
            allowed=False,
            at_capacity=False,
            team_id=str(route["team_id"]),
            route_version=int(route["route_version"]),
            active_assignment_count=0,
            max_active_assignments=None,
            reason="team_inactive",
        )
    lock_suffix = ""
    if lock_member and getattr(getattr(conn, "dialect", None), "name", "") == "mysql":
        lock_suffix = " FOR UPDATE"
    member = conn.execute(
        text(
            f"""
            SELECT id, max_active_assignments
            FROM airank_evidence_review_team_members
            WHERE tenant_id=:tenant_id AND project_id=:project_id
              AND team_id=:team_id AND yudao_user_id=:actor
              AND reviewer_role=:reviewer_role AND status='active'
            {lock_suffix}
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "team_id": route["team_id"],
            "actor": actor,
            "reviewer_role": reviewer_role,
        },
    ).mappings().first()
    if member is None:
        return ReviewerRoleEligibility(
            routing_mode="team_routed",
            allowed=False,
            at_capacity=False,
            team_id=str(route["team_id"]),
            route_version=int(route["route_version"]),
            active_assignment_count=0,
            max_active_assignments=None,
            reason="actor_not_routed",
        )
    active_count = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*) FROM airank_evidence_review_assignments
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND reviewer_role=:reviewer_role AND assigned_to=:actor
                  AND status='active' AND lease_expires_at>:as_of
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "reviewer_role": reviewer_role,
                "actor": actor,
                "as_of": as_of or now_utc(),
            },
        ).scalar_one()
    )
    maximum = int(member["max_active_assignments"])
    return ReviewerRoleEligibility(
        routing_mode="team_routed",
        allowed=True,
        at_capacity=active_count >= maximum,
        team_id=str(route["team_id"]),
        route_version=int(route["route_version"]),
        active_assignment_count=active_count,
        max_active_assignments=maximum,
        reason="capacity_reached" if active_count >= maximum else None,
    )


def resolve_escalation_route_snapshot(
    conn: Any,
    tenant_id: str,
    project_id: str,
    reviewer_role: str,
) -> ReviewerEscalationRouteSnapshot:
    route = conn.execute(
        text(
            """
            SELECT route.team_id, route.version AS route_version,
                   team.status AS team_status,
                   team.external_sync_state
            FROM airank_evidence_review_routes route
            LEFT JOIN airank_evidence_review_teams team
              ON team.tenant_id=route.tenant_id AND team.id=route.team_id
            WHERE route.tenant_id=:tenant_id AND route.project_id=:project_id
              AND route.reviewer_role=:reviewer_role AND route.status='active'
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "reviewer_role": reviewer_role,
        },
    ).mappings().first()
    if route is None:
        configured_route_count = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_evidence_review_routes "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND status='active'"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).scalar_one()
        )
        if configured_route_count > 0:
            return ReviewerEscalationRouteSnapshot(
                routing_state="blocked_role_unconfigured",
                team_id=None,
                route_version=None,
                eligible_recipient_count=0,
                external_sync_state="not_configured",
            )
        return ReviewerEscalationRouteSnapshot(
            routing_state="unrestricted_legacy",
            team_id=None,
            route_version=None,
            eligible_recipient_count=0,
            external_sync_state="not_configured",
        )
    team_id = str(route["team_id"])
    version = int(route["route_version"])
    external_sync_state = str(route["external_sync_state"] or "not_configured")
    if str(route["team_status"] or "") != "active":
        return ReviewerEscalationRouteSnapshot(
            routing_state="blocked_team_inactive",
            team_id=team_id,
            route_version=version,
            eligible_recipient_count=0,
            external_sync_state=external_sync_state,
        )
    recipient_count = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*) FROM airank_evidence_review_team_members
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND team_id=:team_id AND reviewer_role=:reviewer_role
                  AND status='active' AND receives_escalations=1
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "team_id": team_id,
                "reviewer_role": reviewer_role,
            },
        ).scalar_one()
    )
    return ReviewerEscalationRouteSnapshot(
        routing_state=("resolved" if recipient_count > 0 else "blocked_no_recipients"),
        team_id=team_id,
        route_version=version,
        eligible_recipient_count=recipient_count,
        external_sync_state=external_sync_state,
    )


class ReviewerRoutingRepository(Protocol):
    def get_routing(self, tenant_id: str, project_id: str) -> ReviewerRoutingData: ...

    def create_team(
        self,
        tenant_id: str,
        project_id: str,
        payload: ReviewerTeamCreateRequest,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> ReviewerRoutingData: ...

    def upsert_member(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        user_id: str,
        reviewer_role: str,
        payload: ReviewerTeamMemberUpsertRequest,
        actor: str,
        trace_id: str,
    ) -> ReviewerRoutingData: ...

    def put_route(
        self,
        tenant_id: str,
        project_id: str,
        reviewer_role: str,
        payload: ReviewerRoleRoutePutRequest,
        actor: str,
        trace_id: str,
    ) -> ReviewerRoutingData: ...

    def put_sync_binding(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        reviewer_role: str,
        payload: ReviewerDirectoryBindingPutRequest,
        actor: str,
        trace_id: str,
    ) -> ReviewerRoutingData: ...

    def run_directory_sync(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        reviewer_role: str,
        idempotency_key: str,
        actor: str,
        trace_id: str,
        directory_client: YudaoReviewerDirectoryClient,
    ) -> ReviewerRoutingData: ...


class InMemoryReviewerRoutingRepository:
    def __init__(self) -> None:
        self.lock = RLock()
        self.projects: set[tuple[str, str]] = {("tenant_1", "project_1")}
        self.teams: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self.members: dict[tuple[str, str], dict[tuple[str, str, str], dict[str, Any]]] = {}
        self.routes: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self.idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        self.sync_bindings: dict[
            tuple[str, str], dict[tuple[str, str], dict[str, Any]]
        ] = {}
        self.sync_runs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.sync_idempotency: dict[
            tuple[str, str, str, str], tuple[str, str]
        ] = {}

    def get_routing(self, tenant_id: str, project_id: str) -> ReviewerRoutingData:
        with self.lock:
            self._project(tenant_id, project_id)
            return self._data(tenant_id, project_id)

    def create_team(self, tenant_id: str, project_id: str, payload: ReviewerTeamCreateRequest, idempotency_key: str, actor: str, trace_id: str) -> ReviewerRoutingData:
        del trace_id
        with self.lock:
            self._project(tenant_id, project_id)
            request_hash = canonical_sha256(payload.model_dump())
            key = (tenant_id, project_id, idempotency_key)
            existing = self.idempotency.get(key)
            if existing:
                if existing[1] != request_hash:
                    raise StarletteHTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                return self._data(
                    tenant_id, project_id, replay_team_id=existing[0]
                )
            if any(
                item["name"] == payload.name.strip()
                for item in self.teams.get((tenant_id, project_id), {}).values()
            ):
                raise StarletteHTTPException(
                    409, detail={"code": "EVIDENCE_REVIEW_TEAM_NAME_CONFLICT"}
                )
            team_id = f"review_team_{uuid4().hex}"
            at = now_utc()
            self.teams.setdefault((tenant_id, project_id), {})[team_id] = {
                "team_id": team_id, "name": payload.name.strip(), "status": "active",
                "external_source": "manual", "external_group_id": None,
                "external_sync_state": "not_configured", "version": 1,
                "created_at": at, "updated_at": at, "idempotent_replay": False,
                "created_by": actor,
            }
            self.idempotency[key] = (team_id, request_hash)
            return self._data(tenant_id, project_id)

    def upsert_member(self, tenant_id: str, project_id: str, team_id: str, user_id: str, reviewer_role: str, payload: ReviewerTeamMemberUpsertRequest, actor: str, trace_id: str) -> ReviewerRoutingData:
        del trace_id
        with self.lock:
            self._project(tenant_id, project_id)
            if team_id not in self.teams.get((tenant_id, project_id), {}):
                raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_TEAM_NOT_FOUND"})
            key = (team_id, user_id, reviewer_role)
            existing = self.members.setdefault((tenant_id, project_id), {}).get(key)
            if existing and payload.expected_version != existing["version"]:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            if not existing and payload.expected_version is not None:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            at = now_utc()
            self.members[(tenant_id, project_id)][key] = {
                "member_id": existing["member_id"] if existing else f"review_member_{uuid4().hex}",
                "user_id": user_id, "display_name": payload.display_name,
                "reviewer_role": reviewer_role, "priority": payload.priority,
                "max_active_assignments": payload.max_active_assignments,
                "receives_escalations": payload.receives_escalations,
                "status": "active", "membership_source": "manual",
                "external_membership_verified": False,
                "version": (existing["version"] + 1 if existing else 1),
                "updated_at": at, "updated_by": actor,
            }
            return self._data(tenant_id, project_id)

    def put_route(self, tenant_id: str, project_id: str, reviewer_role: str, payload: ReviewerRoleRoutePutRequest, actor: str, trace_id: str) -> ReviewerRoutingData:
        del trace_id
        with self.lock:
            self._project(tenant_id, project_id)
            team = self.teams.get((tenant_id, project_id), {}).get(payload.team_id)
            if not team or team["status"] != "active":
                raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_TEAM_NOT_FOUND"})
            existing = self.routes.setdefault((tenant_id, project_id), {}).get(reviewer_role)
            if existing and payload.expected_version != existing["version"]:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            if not existing and payload.expected_version is not None:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            at = now_utc()
            self.routes[(tenant_id, project_id)][reviewer_role] = {
                "route_id": existing["route_id"] if existing else f"review_route_{uuid4().hex}",
                "reviewer_role": reviewer_role, "team_id": payload.team_id,
                "team_name": team["name"], "routing_strategy": "manual_claim",
                "status": "active", "version": (existing["version"] + 1 if existing else 1),
                "updated_at": at, "updated_by": actor,
            }
            return self._data(tenant_id, project_id)

    def put_sync_binding(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        reviewer_role: str,
        payload: ReviewerDirectoryBindingPutRequest,
        actor: str,
        trace_id: str,
    ) -> ReviewerRoutingData:
        del trace_id
        with self.lock:
            self._project(tenant_id, project_id)
            team = self.teams.get((tenant_id, project_id), {}).get(team_id)
            if not team or team["status"] != "active":
                raise StarletteHTTPException(
                    404, detail={"code": "EVIDENCE_REVIEW_TEAM_NOT_FOUND"}
                )
            key = (team_id, reviewer_role)
            existing = self.sync_bindings.setdefault(
                (tenant_id, project_id), {}
            ).get(key)
            if existing and payload.expected_version != existing["version"]:
                raise StarletteHTTPException(
                    409,
                    detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"},
                )
            if not existing and payload.expected_version is not None:
                raise StarletteHTTPException(
                    409,
                    detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"},
                )
            at = now_utc()
            binding_id = (
                existing["binding_id"]
                if existing
                else f"review_sync_binding_{uuid4().hex}"
            )
            self.sync_bindings[(tenant_id, project_id)][key] = {
                "binding_id": binding_id,
                "team_id": team_id,
                "team_name": team["name"],
                "reviewer_role": reviewer_role,
                "external_source": "yudao",
                "external_group_id": payload.external_group_id.strip(),
                "status": "active",
                "sync_enabled": payload.sync_enabled,
                "sync_interval_minutes": payload.sync_interval_minutes,
                "default_priority": payload.default_priority,
                "default_max_active_assignments": payload.default_max_active_assignments,
                "default_receives_escalations": payload.default_receives_escalations,
                "last_sync_state": "pending",
                "last_sync_run_id": existing.get("last_sync_run_id") if existing else None,
                "last_synced_at": existing.get("last_synced_at") if existing else None,
                "next_sync_at": at,
                "last_error_code": None,
                "version": (existing["version"] + 1 if existing else 1),
                "updated_at": at,
                "updated_by": actor,
            }
            team["external_source"] = "yudao"
            team["external_group_id"] = self._team_external_group_id(
                tenant_id, project_id, team_id
            )
            team["external_sync_state"] = "pending"
            team["updated_at"] = at
            return self._data(tenant_id, project_id)

    def run_directory_sync(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        reviewer_role: str,
        idempotency_key: str,
        actor: str,
        trace_id: str,
        directory_client: YudaoReviewerDirectoryClient,
    ) -> ReviewerRoutingData:
        del trace_id
        with self.lock:
            self._project(tenant_id, project_id)
            key = (team_id, reviewer_role)
            binding = self.sync_bindings.get((tenant_id, project_id), {}).get(key)
            if not binding or binding["status"] != "active":
                raise StarletteHTTPException(
                    404,
                    detail={"code": "EVIDENCE_REVIEW_YUDAO_BINDING_NOT_FOUND"},
                )
            request_hash = canonical_sha256(
                {
                    "binding_id": binding["binding_id"],
                    "binding_version": binding["version"],
                    "external_group_id": binding["external_group_id"],
                }
            )
            replay_key = (tenant_id, binding["binding_id"], idempotency_key, reviewer_role)
            existing = self.sync_idempotency.get(replay_key)
            if existing:
                if existing[1] != request_hash:
                    raise StarletteHTTPException(
                        409, detail={"code": "IDEMPOTENCY_CONFLICT"}
                    )
                return self._data(
                    tenant_id, project_id, replay_sync_run_id=existing[0]
                )
            run_id = f"review_sync_run_{uuid4().hex}"
            started_at = now_utc()
            binding_snapshot = dict(binding)
        try:
            snapshot = directory_client.fetch_department(
                str(binding_snapshot["external_group_id"])
            )
        except YudaoDirectoryError as exc:
            with self.lock:
                at = now_utc()
                binding["last_sync_state"] = "failed"
                binding["last_sync_run_id"] = run_id
                binding["last_error_code"] = exc.code
                binding["next_sync_at"] = at + timedelta(
                    minutes=binding["sync_interval_minutes"]
                )
                binding["updated_at"] = at
                self._update_in_memory_team_sync_state(
                    tenant_id, project_id, team_id, at
                )
                self.sync_runs.setdefault((tenant_id, project_id), []).append(
                    {
                        "run_id": run_id,
                        "binding_id": binding["binding_id"],
                        "team_id": team_id,
                        "reviewer_role": reviewer_role,
                        "external_group_id": binding["external_group_id"],
                        "status": "failed",
                        "endpoint_host": None,
                        "response_sha256": None,
                        "discovered_member_count": 0,
                        "active_member_count": 0,
                        "upserted_member_count": 0,
                        "disabled_member_count": 0,
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                        "started_at": started_at,
                        "finished_at": at,
                        "idempotent_replay": False,
                    }
                )
                self.sync_idempotency[replay_key] = (run_id, request_hash)
            raise StarletteHTTPException(
                503,
                detail={
                    "code": "EVIDENCE_REVIEW_YUDAO_SYNC_FAILED",
                    "details": {"upstream_code": exc.code, "retryable": exc.retryable},
                },
            ) from exc
        with self.lock:
            current = self.sync_bindings[(tenant_id, project_id)].get(key)
            if not current or current["version"] != binding_snapshot["version"]:
                raise StarletteHTTPException(
                    409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"}
                )
            counts = self._apply_in_memory_directory_snapshot(
                tenant_id,
                project_id,
                current,
                snapshot,
                actor,
            )
            at = now_utc()
            current["last_sync_state"] = "verified"
            current["last_sync_run_id"] = run_id
            current["last_synced_at"] = at
            current["next_sync_at"] = at + timedelta(
                minutes=current["sync_interval_minutes"]
            )
            current["last_error_code"] = None
            current["updated_at"] = at
            self._update_in_memory_team_sync_state(tenant_id, project_id, team_id, at)
            self.sync_runs.setdefault((tenant_id, project_id), []).append(
                {
                    "run_id": run_id,
                    "binding_id": current["binding_id"],
                    "team_id": team_id,
                    "reviewer_role": reviewer_role,
                    "external_group_id": current["external_group_id"],
                    "status": "succeeded",
                    "endpoint_host": snapshot.endpoint_host,
                    "response_sha256": snapshot.response_sha256,
                    "discovered_member_count": len(snapshot.members),
                    "active_member_count": counts["active"],
                    "upserted_member_count": counts["upserted"],
                    "disabled_member_count": counts["disabled"],
                    "error_code": None,
                    "retryable": False,
                    "started_at": started_at,
                    "finished_at": at,
                    "idempotent_replay": False,
                }
            )
            self.sync_idempotency[replay_key] = (run_id, request_hash)
            return self._data(tenant_id, project_id)

    def _apply_in_memory_directory_snapshot(
        self,
        tenant_id: str,
        project_id: str,
        binding: dict[str, Any],
        snapshot: YudaoReviewerDirectorySnapshot,
        actor: str,
    ) -> dict[str, int]:
        members = self.members.setdefault((tenant_id, project_id), {})
        active_reviewers = [member for member in snapshot.members if member.enabled]
        active_ids = {member.user_id for member in active_reviewers}
        disabled = 0
        for key, member in members.items():
            if (
                key[0] == binding["team_id"]
                and key[2] == binding["reviewer_role"]
                and member["membership_source"] == "yudao"
                and member["status"] == "active"
                and key[1] not in active_ids
            ):
                member["status"] = "disabled"
                member["version"] += 1
                member["updated_at"] = now_utc()
                disabled += 1
        upserted = 0
        for reviewer in active_reviewers:
            key = (binding["team_id"], reviewer.user_id, binding["reviewer_role"])
            existing = members.get(key)
            at = now_utc()
            desired = {
                "member_id": (
                    existing["member_id"]
                    if existing
                    else f"review_member_{uuid4().hex}"
                ),
                "user_id": reviewer.user_id,
                "display_name": reviewer.display_name or reviewer.username,
                "reviewer_role": binding["reviewer_role"],
                "priority": binding["default_priority"],
                "max_active_assignments": binding[
                    "default_max_active_assignments"
                ],
                "receives_escalations": binding[
                    "default_receives_escalations"
                ],
                "status": "active",
                "membership_source": "yudao",
                "external_membership_verified": True,
            }
            if existing is not None and all(
                existing.get(field) == value
                for field, value in desired.items()
                if field != "member_id"
            ):
                continue
            members[key] = {
                **desired,
                "version": existing["version"] + 1 if existing else 1,
                "updated_at": at,
                "updated_by": actor,
            }
            upserted += 1
        return {"active": len(active_ids), "upserted": upserted, "disabled": disabled}

    def _team_external_group_id(
        self, tenant_id: str, project_id: str, team_id: str
    ) -> str | None:
        groups = {
            item["external_group_id"]
            for (bound_team_id, _), item in self.sync_bindings.get(
                (tenant_id, project_id), {}
            ).items()
            if bound_team_id == team_id and item["status"] == "active"
        }
        return next(iter(groups)) if len(groups) == 1 else None

    def _update_in_memory_team_sync_state(
        self, tenant_id: str, project_id: str, team_id: str, at: datetime
    ) -> None:
        team = self.teams[(tenant_id, project_id)][team_id]
        states = [
            item["last_sync_state"]
            for (bound_team_id, _), item in self.sync_bindings.get(
                (tenant_id, project_id), {}
            ).items()
            if bound_team_id == team_id and item["status"] == "active"
        ]
        state = "not_configured"
        for candidate in ("failed", "stale", "pending", "verified"):
            if candidate in states:
                state = candidate
                break
        team["external_source"] = "yudao"
        team["external_group_id"] = self._team_external_group_id(
            tenant_id, project_id, team_id
        )
        team["external_sync_state"] = state
        team["updated_at"] = at

    def _project(self, tenant_id: str, project_id: str) -> None:
        if (tenant_id, project_id) not in self.projects:
            raise StarletteHTTPException(404, detail={"code": "PROJECT_NOT_FOUND"})

    def _data(
        self,
        tenant_id: str,
        project_id: str,
        replay_team_id: str | None = None,
        replay_sync_run_id: str | None = None,
    ) -> ReviewerRoutingData:
        members = self.members.get((tenant_id, project_id), {})
        teams = []
        for team in self.teams.get((tenant_id, project_id), {}).values():
            team_members = [ReviewerTeamMemberData(**item) for key, item in members.items() if key[0] == team["team_id"]]
            teams.append(
                ReviewerTeamData(
                    **{
                        **team,
                        "member_count": len(team_members),
                        "members": team_members,
                        "idempotent_replay": team["team_id"] == replay_team_id,
                    }
                )
            )
        route_rows = []
        for route in self.routes.get((tenant_id, project_id), {}).values():
            eligible = [item for key, item in members.items() if key[0] == route["team_id"] and key[2] == route["reviewer_role"] and item["status"] == "active"]
            recipients = [item for item in eligible if item["receives_escalations"]]
            team = self.teams.get((tenant_id, project_id), {}).get(route["team_id"])
            route_rows.append(
                ReviewerRoleRouteData(
                    **route,
                    eligible_member_count=len(eligible),
                    escalation_recipient_count=len(recipients),
                    routing_ready=bool(eligible)
                    and team is not None
                    and team["status"] == "active",
                )
            )
        active_roles = {
            item.reviewer_role for item in route_rows if item.status == "active"
        }
        configured = bool(active_roles)
        ready = active_roles == set(REVIEWER_ROLES) and all(
            item.routing_ready for item in route_rows if item.status == "active"
        )
        bindings = [
            ReviewerDirectoryBindingData(**item)
            for item in self.sync_bindings.get((tenant_id, project_id), {}).values()
        ]
        recent_runs = [
            ReviewerDirectorySyncRunData(
                **{
                    **item,
                    "idempotent_replay": item["run_id"] == replay_sync_run_id,
                }
            )
            for item in reversed(
                self.sync_runs.get((tenant_id, project_id), [])[-20:]
            )
        ]
        external_states = {
            item.external_sync_state for item in teams if item.status == "active"
        }
        external_sync_state = "not_configured"
        for state in ("failed", "stale", "pending", "verified"):
            if state in external_states:
                external_sync_state = state
                break
        return ReviewerRoutingData(
            project_id=project_id,
            routing_mode=("unrestricted_legacy" if not configured else "team_routed" if ready else "blocked"),
            external_sync_state=external_sync_state,
            teams=teams,
            routes=route_rows,
            sync_bindings=bindings,
            recent_sync_runs=recent_runs,
            known_limitations=[
                "yudao_group_sync_not_verified",
                "external_notification_delivery_not_verified",
            ],
        )


class MySQLReviewerRoutingRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def get_routing(self, tenant_id: str, project_id: str) -> ReviewerRoutingData:
        with self.engine.begin() as conn:
            self._project(conn, tenant_id, project_id)
            return self._data(conn, tenant_id, project_id)

    def create_team(self, tenant_id: str, project_id: str, payload: ReviewerTeamCreateRequest, idempotency_key: str, actor: str, trace_id: str) -> ReviewerRoutingData:
        at = now_utc()
        request_hash = canonical_sha256(payload.model_dump())
        with self.engine.begin() as conn:
            self._project(conn, tenant_id, project_id)
            existing = conn.execute(text("SELECT id, request_sha256 FROM airank_evidence_review_teams WHERE tenant_id=:tenant_id AND project_id=:project_id AND idempotency_key=:idempotency_key"), {"tenant_id": tenant_id, "project_id": project_id, "idempotency_key": idempotency_key}).mappings().first()
            if existing:
                if str(existing["request_sha256"]) != request_hash:
                    raise StarletteHTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                return self._data(conn, tenant_id, project_id, replay_team_id=str(existing["id"]))
            duplicate_name = conn.execute(
                text(
                    "SELECT id FROM airank_evidence_review_teams "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND name=:name"
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "name": payload.name.strip(),
                },
            ).first()
            if duplicate_name is not None:
                raise StarletteHTTPException(
                    409, detail={"code": "EVIDENCE_REVIEW_TEAM_NAME_CONFLICT"}
                )
            team_id = f"review_team_{uuid4().hex}"
            conn.execute(text("""
                INSERT INTO airank_evidence_review_teams (
                  id, tenant_id, project_id, name, status, external_source,
                  external_group_id, external_sync_state, idempotency_key,
                  request_sha256, version, created_by, updated_by, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :name, 'active', 'manual',
                  NULL, 'not_configured', :idempotency_key, :request_sha256,
                  1, :actor, :actor, :at, :at
                )
            """), {"id": team_id, "tenant_id": tenant_id, "project_id": project_id, "name": payload.name.strip(), "idempotency_key": idempotency_key, "request_sha256": request_hash, "actor": actor, "at": at})
            self._audit(conn, tenant_id, project_id, actor, "evidence_review.team_created", "evidence_review_team", team_id, trace_id, {"external_source": "manual"}, at)
            return self._data(conn, tenant_id, project_id)

    def upsert_member(self, tenant_id: str, project_id: str, team_id: str, user_id: str, reviewer_role: str, payload: ReviewerTeamMemberUpsertRequest, actor: str, trace_id: str) -> ReviewerRoutingData:
        at = now_utc()
        with self.engine.begin() as conn:
            self._active_team(conn, tenant_id, project_id, team_id)
            lock = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            existing = conn.execute(text(f"SELECT * FROM airank_evidence_review_team_members WHERE tenant_id=:tenant_id AND team_id=:team_id AND yudao_user_id=:user_id AND reviewer_role=:reviewer_role{lock}"), {"tenant_id": tenant_id, "team_id": team_id, "user_id": user_id, "reviewer_role": reviewer_role}).mappings().first()
            if existing is None and payload.expected_version is not None:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            if existing is not None and payload.expected_version != int(existing["version"]):
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            if existing is None:
                member_id = f"review_member_{uuid4().hex}"
                version = 1
                conn.execute(text("""
                    INSERT INTO airank_evidence_review_team_members (
                      id, tenant_id, project_id, team_id, yudao_user_id,
                      display_name, reviewer_role, priority, max_active_assignments,
                      receives_escalations, status, membership_source,
                      external_membership_verified, version, created_by, updated_by,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :team_id, :user_id,
                      :display_name, :reviewer_role, :priority, :max_active,
                      :receives, 'active', 'manual', 0, 1, :actor, :actor, :at, :at
                    )
                """), {"id": member_id, "tenant_id": tenant_id, "project_id": project_id, "team_id": team_id, "user_id": user_id, "display_name": payload.display_name, "reviewer_role": reviewer_role, "priority": payload.priority, "max_active": payload.max_active_assignments, "receives": payload.receives_escalations, "actor": actor, "at": at})
                event_type = "evidence_review.team_member_added"
            else:
                member_id = str(existing["id"])
                version = int(existing["version"]) + 1
                conn.execute(text("""
                    UPDATE airank_evidence_review_team_members
                    SET display_name=:display_name, priority=:priority,
                        max_active_assignments=:max_active,
                        receives_escalations=:receives, status='active',
                        membership_source='manual', external_membership_verified=0,
                        version=:version, updated_by=:actor, updated_at=:at
                    WHERE tenant_id=:tenant_id AND id=:id
                """), {"display_name": payload.display_name, "priority": payload.priority, "max_active": payload.max_active_assignments, "receives": payload.receives_escalations, "version": version, "actor": actor, "at": at, "tenant_id": tenant_id, "id": member_id})
                event_type = "evidence_review.team_member_updated"
            self._audit(conn, tenant_id, project_id, actor, event_type, "evidence_review_team_member", member_id, trace_id, {"team_id": team_id, "reviewer_role": reviewer_role, "version": version}, at)
            return self._data(conn, tenant_id, project_id)

    def put_route(self, tenant_id: str, project_id: str, reviewer_role: str, payload: ReviewerRoleRoutePutRequest, actor: str, trace_id: str) -> ReviewerRoutingData:
        at = now_utc()
        with self.engine.begin() as conn:
            self._active_team(conn, tenant_id, project_id, payload.team_id)
            lock = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            existing = conn.execute(text(f"SELECT * FROM airank_evidence_review_routes WHERE tenant_id=:tenant_id AND project_id=:project_id AND reviewer_role=:reviewer_role{lock}"), {"tenant_id": tenant_id, "project_id": project_id, "reviewer_role": reviewer_role}).mappings().first()
            if existing is None and payload.expected_version is not None:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            if existing is not None and payload.expected_version != int(existing["version"]):
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"})
            if existing is None:
                route_id = f"review_route_{uuid4().hex}"
                version = 1
                conn.execute(text("""
                    INSERT INTO airank_evidence_review_routes (
                      id, tenant_id, project_id, reviewer_role, team_id,
                      routing_strategy, status, version, created_by, updated_by,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :reviewer_role, :team_id,
                      'manual_claim', 'active', 1, :actor, :actor, :at, :at
                    )
                """), {"id": route_id, "tenant_id": tenant_id, "project_id": project_id, "reviewer_role": reviewer_role, "team_id": payload.team_id, "actor": actor, "at": at})
            else:
                route_id = str(existing["id"])
                version = int(existing["version"]) + 1
                conn.execute(text("""
                    UPDATE airank_evidence_review_routes
                    SET team_id=:team_id, routing_strategy='manual_claim',
                        status='active', version=:version, updated_by=:actor,
                        updated_at=:at
                    WHERE tenant_id=:tenant_id AND id=:id
                """), {"team_id": payload.team_id, "version": version, "actor": actor, "at": at, "tenant_id": tenant_id, "id": route_id})
            self._audit(conn, tenant_id, project_id, actor, "evidence_review.route_configured", "evidence_review_route", route_id, trace_id, {"reviewer_role": reviewer_role, "team_id": payload.team_id, "version": version}, at)
            return self._data(conn, tenant_id, project_id)

    def put_sync_binding(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        reviewer_role: str,
        payload: ReviewerDirectoryBindingPutRequest,
        actor: str,
        trace_id: str,
    ) -> ReviewerRoutingData:
        at = now_utc()
        with self.engine.begin() as conn:
            self._active_team(conn, tenant_id, project_id, team_id)
            lock = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_evidence_review_team_sync_bindings "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND team_id=:team_id AND reviewer_role=:reviewer_role"
                    + lock
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                    "reviewer_role": reviewer_role,
                },
            ).mappings().first()
            if existing is None and payload.expected_version is not None:
                raise StarletteHTTPException(
                    409,
                    detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"},
                )
            if existing is not None and payload.expected_version != int(existing["version"]):
                raise StarletteHTTPException(
                    409,
                    detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"},
                )
            if existing is None:
                binding_id = f"review_sync_binding_{uuid4().hex}"
                version = 1
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_evidence_review_team_sync_bindings (
                          id, tenant_id, project_id, team_id, reviewer_role,
                          external_source, external_group_id, status, sync_enabled,
                          sync_interval_minutes, default_priority,
                          default_max_active_assignments,
                          default_receives_escalations, last_sync_state,
                          last_sync_run_id, last_synced_at, next_sync_at,
                          last_error_code, version, created_by, updated_by,
                          created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :team_id, :reviewer_role,
                          'yudao', :external_group_id, 'active', :sync_enabled,
                          :sync_interval, :default_priority, :default_max_active,
                          :default_receives, 'pending', NULL, NULL, :next_sync_at,
                          NULL, 1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": binding_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "team_id": team_id,
                        "reviewer_role": reviewer_role,
                        "external_group_id": payload.external_group_id.strip(),
                        "sync_enabled": payload.sync_enabled,
                        "sync_interval": payload.sync_interval_minutes,
                        "default_priority": payload.default_priority,
                        "default_max_active": payload.default_max_active_assignments,
                        "default_receives": payload.default_receives_escalations,
                        "next_sync_at": at,
                        "actor": actor,
                        "at": at,
                    },
                )
            else:
                binding_id = str(existing["id"])
                version = int(existing["version"]) + 1
                conn.execute(
                    text(
                        """
                        UPDATE airank_evidence_review_team_sync_bindings
                        SET external_group_id=:external_group_id, status='active',
                            sync_enabled=:sync_enabled,
                            sync_interval_minutes=:sync_interval,
                            default_priority=:default_priority,
                            default_max_active_assignments=:default_max_active,
                            default_receives_escalations=:default_receives,
                            last_sync_state='pending', next_sync_at=:next_sync_at,
                            last_error_code=NULL, version=:version,
                            updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:id
                        """
                    ),
                    {
                        "external_group_id": payload.external_group_id.strip(),
                        "sync_enabled": payload.sync_enabled,
                        "sync_interval": payload.sync_interval_minutes,
                        "default_priority": payload.default_priority,
                        "default_max_active": payload.default_max_active_assignments,
                        "default_receives": payload.default_receives_escalations,
                        "next_sync_at": at,
                        "version": version,
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "id": binding_id,
                    },
                )
            self._refresh_team_external_sync(
                conn, tenant_id, project_id, team_id, actor, at
            )
            self._audit(
                conn,
                tenant_id,
                project_id,
                actor,
                "evidence_review.yudao_binding_configured",
                "evidence_review_team_sync_binding",
                binding_id,
                trace_id,
                {
                    "team_id": team_id,
                    "reviewer_role": reviewer_role,
                    "external_group_id": payload.external_group_id.strip(),
                    "version": version,
                },
                at,
            )
            return self._data(conn, tenant_id, project_id)

    def run_directory_sync(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        reviewer_role: str,
        idempotency_key: str,
        actor: str,
        trace_id: str,
        directory_client: YudaoReviewerDirectoryClient,
    ) -> ReviewerRoutingData:
        started_at = now_utc()
        lock = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        with self.engine.begin() as conn:
            self._active_team(conn, tenant_id, project_id, team_id)
            binding = conn.execute(
                text(
                    "SELECT * FROM airank_evidence_review_team_sync_bindings "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND team_id=:team_id AND reviewer_role=:reviewer_role "
                    "AND status='active'" + lock
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                    "reviewer_role": reviewer_role,
                },
            ).mappings().first()
            if binding is None:
                raise StarletteHTTPException(
                    404,
                    detail={"code": "EVIDENCE_REVIEW_YUDAO_BINDING_NOT_FOUND"},
                )
            request_hash = canonical_sha256(
                {
                    "binding_id": str(binding["id"]),
                    "binding_version": int(binding["version"]),
                    "external_group_id": str(binding["external_group_id"]),
                }
            )
            replay = conn.execute(
                text(
                    "SELECT id, request_sha256 FROM "
                    "airank_evidence_review_team_sync_runs "
                    "WHERE tenant_id=:tenant_id AND binding_id=:binding_id "
                    "AND idempotency_key=:idempotency_key"
                ),
                {
                    "tenant_id": tenant_id,
                    "binding_id": binding["id"],
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
            if replay is not None:
                if str(replay["request_sha256"]) != request_hash:
                    raise StarletteHTTPException(
                        409, detail={"code": "IDEMPOTENCY_CONFLICT"}
                    )
                return self._data(
                    conn,
                    tenant_id,
                    project_id,
                    replay_sync_run_id=str(replay["id"]),
                )
            run_id = f"review_sync_run_{uuid4().hex}"
            binding_snapshot = {
                "id": str(binding["id"]),
                "version": int(binding["version"]),
                "external_group_id": str(binding["external_group_id"]),
                "sync_interval_minutes": int(binding["sync_interval_minutes"]),
            }
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_review_team_sync_runs (
                      id, tenant_id, project_id, team_id, binding_id,
                      reviewer_role, external_group_id, status, idempotency_key,
                      request_sha256, requested_by, trace_id, endpoint_host,
                      response_sha256, discovered_member_count,
                      active_member_count, upserted_member_count,
                      disabled_member_count, error_code, retryable, started_at,
                      finished_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :team_id, :binding_id,
                      :reviewer_role, :external_group_id, 'running',
                      :idempotency_key, :request_sha256, :actor, :trace_id,
                      NULL, NULL, 0, 0, 0, 0, NULL, 0, :started_at, NULL,
                      :started_at
                    )
                    """
                ),
                {
                    "id": run_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                    "binding_id": binding["id"],
                    "reviewer_role": reviewer_role,
                    "external_group_id": binding["external_group_id"],
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_hash,
                    "actor": actor,
                    "trace_id": trace_id,
                    "started_at": started_at,
                },
            )
            conn.execute(
                text(
                    "UPDATE airank_evidence_review_team_sync_bindings "
                    "SET last_sync_state='pending', last_sync_run_id=:run_id, "
                    "last_error_code=NULL, updated_by=:actor, updated_at=:at "
                    "WHERE tenant_id=:tenant_id AND id=:binding_id"
                ),
                {
                    "run_id": run_id,
                    "actor": actor,
                    "at": started_at,
                    "tenant_id": tenant_id,
                    "binding_id": binding["id"],
                },
            )
            self._refresh_team_external_sync(
                conn, tenant_id, project_id, team_id, actor, started_at
            )
        try:
            snapshot = directory_client.fetch_department(
                binding_snapshot["external_group_id"]
            )
        except YudaoDirectoryError as exc:
            finished_at = now_utc()
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE airank_evidence_review_team_sync_runs
                        SET status='failed', error_code=:error_code,
                            retryable=:retryable, finished_at=:finished_at
                        WHERE tenant_id=:tenant_id AND id=:run_id
                        """
                    ),
                    {
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                        "finished_at": finished_at,
                        "tenant_id": tenant_id,
                        "run_id": run_id,
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_evidence_review_team_sync_bindings
                        SET last_sync_state='failed', last_sync_run_id=:run_id,
                            last_error_code=:error_code, next_sync_at=:next_sync_at,
                            updated_by=:actor, updated_at=:finished_at
                        WHERE tenant_id=:tenant_id AND id=:binding_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "error_code": exc.code,
                        "next_sync_at": finished_at
                        + timedelta(
                            minutes=binding_snapshot["sync_interval_minutes"]
                        ),
                        "actor": actor,
                        "finished_at": finished_at,
                        "tenant_id": tenant_id,
                        "binding_id": binding_snapshot["id"],
                    },
                )
                self._refresh_team_external_sync(
                    conn, tenant_id, project_id, team_id, actor, finished_at
                )
                self._audit(
                    conn,
                    tenant_id,
                    project_id,
                    actor,
                    "evidence_review.yudao_sync_failed",
                    "evidence_review_team_sync_run",
                    run_id,
                    trace_id,
                    {
                        "team_id": team_id,
                        "reviewer_role": reviewer_role,
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                    finished_at,
                )
            raise StarletteHTTPException(
                503,
                detail={
                    "code": "EVIDENCE_REVIEW_YUDAO_SYNC_FAILED",
                    "details": {"upstream_code": exc.code, "retryable": exc.retryable},
                },
            ) from exc

        finished_at = now_utc()
        with self.engine.begin() as conn:
            current = conn.execute(
                text(
                    "SELECT * FROM airank_evidence_review_team_sync_bindings "
                    "WHERE tenant_id=:tenant_id AND id=:binding_id" + lock
                ),
                {"tenant_id": tenant_id, "binding_id": binding_snapshot["id"]},
            ).mappings().first()
            if (
                current is None
                or int(current["version"]) != binding_snapshot["version"]
                or str(current["external_group_id"])
                != binding_snapshot["external_group_id"]
                or str(current["status"]) != "active"
            ):
                conn.execute(
                    text(
                        "UPDATE airank_evidence_review_team_sync_runs "
                        "SET status='failed', error_code='YUDAO_REVIEW_SYNC_BINDING_CHANGED', "
                        "retryable=0, finished_at=:finished_at "
                        "WHERE tenant_id=:tenant_id AND id=:run_id"
                    ),
                    {
                        "finished_at": finished_at,
                        "tenant_id": tenant_id,
                        "run_id": run_id,
                    },
                )
                raise StarletteHTTPException(
                    409,
                    detail={"code": "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"},
                )
            existing_members = conn.execute(
                text(
                    """
                    SELECT id, yudao_user_id, display_name, priority,
                           max_active_assignments, receives_escalations,
                           membership_source, external_membership_verified,
                           status, version
                    FROM airank_evidence_review_team_members
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND team_id=:team_id AND reviewer_role=:reviewer_role
                    """
                    + lock
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                    "reviewer_role": reviewer_role,
                },
            ).mappings().all()
            existing_by_user = {
                str(item["yudao_user_id"]): item for item in existing_members
            }
            active_reviewers = [
                member for member in snapshot.members if member.enabled
            ]
            active_user_ids = {member.user_id for member in active_reviewers}
            disabled_count = 0
            for user_id, member in existing_by_user.items():
                if (
                    str(member["membership_source"]) == "yudao"
                    and str(member["status"]) == "active"
                    and user_id not in active_user_ids
                ):
                    conn.execute(
                        text(
                            """
                            UPDATE airank_evidence_review_team_members
                            SET status='disabled', external_membership_verified=0,
                                version=version+1, updated_by=:actor,
                                updated_at=:finished_at
                            WHERE tenant_id=:tenant_id AND id=:id
                            """
                        ),
                        {
                            "actor": actor,
                            "finished_at": finished_at,
                            "tenant_id": tenant_id,
                            "id": member["id"],
                        },
                    )
                    disabled_count += 1
            upserted_count = 0
            for reviewer in active_reviewers:
                existing = existing_by_user.get(reviewer.user_id)
                display_name = reviewer.display_name or reviewer.username
                if existing is None:
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_evidence_review_team_members (
                              id, tenant_id, project_id, team_id, yudao_user_id,
                              display_name, reviewer_role, priority,
                              max_active_assignments, receives_escalations,
                              status, membership_source,
                              external_membership_verified, version, created_by,
                              updated_by, created_at, updated_at
                            ) VALUES (
                              :id, :tenant_id, :project_id, :team_id, :user_id,
                              :display_name, :reviewer_role, :priority,
                              :max_active, :receives, 'active', 'yudao', 1, 1,
                              :actor, :actor, :at, :at
                            )
                            """
                        ),
                        {
                            "id": f"review_member_{uuid4().hex}",
                            "tenant_id": tenant_id,
                            "project_id": project_id,
                            "team_id": team_id,
                            "user_id": reviewer.user_id,
                            "display_name": display_name,
                            "reviewer_role": reviewer_role,
                            "priority": current["default_priority"],
                            "max_active": current[
                                "default_max_active_assignments"
                            ],
                            "receives": current[
                                "default_receives_escalations"
                            ],
                            "actor": actor,
                            "at": finished_at,
                        },
                    )
                    upserted_count += 1
                else:
                    unchanged = (
                        (existing["display_name"] or None) == display_name
                        and int(existing["priority"])
                        == int(current["default_priority"])
                        and int(existing["max_active_assignments"])
                        == int(current["default_max_active_assignments"])
                        and bool(existing["receives_escalations"])
                        == bool(current["default_receives_escalations"])
                        and str(existing["status"]) == "active"
                        and str(existing["membership_source"]) == "yudao"
                        and bool(existing["external_membership_verified"])
                    )
                    if unchanged:
                        continue
                    conn.execute(
                        text(
                            """
                            UPDATE airank_evidence_review_team_members
                            SET display_name=:display_name, priority=:priority,
                                max_active_assignments=:max_active,
                                receives_escalations=:receives, status='active',
                                membership_source='yudao',
                                external_membership_verified=1,
                                version=version+1, updated_by=:actor,
                                updated_at=:at
                            WHERE tenant_id=:tenant_id AND id=:id
                            """
                        ),
                        {
                            "display_name": display_name,
                            "priority": current["default_priority"],
                            "max_active": current[
                                "default_max_active_assignments"
                            ],
                            "receives": current[
                                "default_receives_escalations"
                            ],
                            "actor": actor,
                            "at": finished_at,
                            "tenant_id": tenant_id,
                            "id": existing["id"],
                        },
                    )
                    upserted_count += 1
            conn.execute(
                text(
                    """
                    UPDATE airank_evidence_review_team_sync_runs
                    SET status='succeeded', endpoint_host=:endpoint_host,
                        response_sha256=:response_sha256,
                        discovered_member_count=:discovered,
                        active_member_count=:active_count,
                        upserted_member_count=:upserted,
                        disabled_member_count=:disabled,
                        error_code=NULL, retryable=0, finished_at=:finished_at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {
                    "endpoint_host": snapshot.endpoint_host,
                    "response_sha256": snapshot.response_sha256,
                    "discovered": len(snapshot.members),
                    "active_count": len(active_user_ids),
                    "upserted": upserted_count,
                    "disabled": disabled_count,
                    "finished_at": finished_at,
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_evidence_review_team_sync_bindings
                    SET last_sync_state='verified', last_sync_run_id=:run_id,
                        last_synced_at=:finished_at, next_sync_at=:next_sync_at,
                        last_error_code=NULL, updated_by=:actor,
                        updated_at=:finished_at
                    WHERE tenant_id=:tenant_id AND id=:binding_id
                    """
                ),
                {
                    "run_id": run_id,
                    "finished_at": finished_at,
                    "next_sync_at": finished_at
                    + timedelta(minutes=int(current["sync_interval_minutes"])),
                    "actor": actor,
                    "tenant_id": tenant_id,
                    "binding_id": binding_snapshot["id"],
                },
            )
            self._refresh_team_external_sync(
                conn, tenant_id, project_id, team_id, actor, finished_at
            )
            self._audit(
                conn,
                tenant_id,
                project_id,
                actor,
                "evidence_review.yudao_sync_succeeded",
                "evidence_review_team_sync_run",
                run_id,
                trace_id,
                {
                    "team_id": team_id,
                    "reviewer_role": reviewer_role,
                    "external_group_id": binding_snapshot["external_group_id"],
                    "response_sha256": snapshot.response_sha256,
                    "active_member_count": len(active_user_ids),
                    "disabled_member_count": disabled_count,
                },
                finished_at,
            )
            return self._data(conn, tenant_id, project_id)

    @staticmethod
    def _refresh_team_external_sync(
        conn: Any,
        tenant_id: str,
        project_id: str,
        team_id: str,
        actor: str,
        at: datetime,
    ) -> None:
        rows = conn.execute(
            text(
                """
                SELECT external_group_id, last_sync_state
                FROM airank_evidence_review_team_sync_bindings
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND team_id=:team_id AND status='active'
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "team_id": team_id,
            },
        ).mappings().all()
        states = {str(row["last_sync_state"]) for row in rows}
        state = "not_configured"
        for candidate in ("failed", "stale", "pending", "verified"):
            if candidate in states:
                state = candidate
                break
        groups = {str(row["external_group_id"]) for row in rows}
        external_group_id = next(iter(groups)) if len(groups) == 1 else None
        conn.execute(
            text(
                """
                UPDATE airank_evidence_review_teams
                SET external_source='yudao', external_group_id=:external_group_id,
                    external_sync_state=:external_sync_state,
                    version=version+1, updated_by=:actor, updated_at=:at
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:team_id
                """
            ),
            {
                "external_group_id": external_group_id,
                "external_sync_state": state,
                "actor": actor,
                "at": at,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "team_id": team_id,
            },
        )

    @staticmethod
    def _project(conn: Any, tenant_id: str, project_id: str) -> None:
        if conn.execute(text("SELECT id FROM airank_projects WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL"), {"tenant_id": tenant_id, "project_id": project_id}).first() is None:
            raise StarletteHTTPException(404, detail={"code": "PROJECT_NOT_FOUND"})

    @classmethod
    def _active_team(cls, conn: Any, tenant_id: str, project_id: str, team_id: str) -> None:
        cls._project(conn, tenant_id, project_id)
        if conn.execute(text("SELECT id FROM airank_evidence_review_teams WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:team_id AND status='active'"), {"tenant_id": tenant_id, "project_id": project_id, "team_id": team_id}).first() is None:
            raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_TEAM_NOT_FOUND"})

    @staticmethod
    def _audit(conn: Any, tenant_id: str, project_id: str, actor: str, event_type: str, entity_type: str, entity_id: str, trace_id: str, payload: Mapping[str, Any], at: datetime) -> None:
        conn.execute(text("""
            INSERT INTO airank_audit_events (
              id, tenant_id, project_id, actor_user_id, event_type,
              entity_type, entity_id, trace_id, payload_json, created_at
            ) VALUES (
              :id, :tenant_id, :project_id, :actor, :event_type,
              :entity_type, :entity_id, :trace_id, :payload_json, :at
            )
        """), {"id": f"audit_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id, "actor": actor, "event_type": event_type, "entity_type": entity_type, "entity_id": entity_id, "trace_id": trace_id, "payload_json": json.dumps(dict(payload), ensure_ascii=False, sort_keys=True), "at": at})

    def _data(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        replay_team_id: str | None = None,
        replay_sync_run_id: str | None = None,
    ) -> ReviewerRoutingData:
        team_rows = conn.execute(text("SELECT * FROM airank_evidence_review_teams WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY created_at, id"), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        member_rows = conn.execute(text("SELECT * FROM airank_evidence_review_team_members WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY priority, created_at, id"), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        members_by_team: dict[str, list[ReviewerTeamMemberData]] = {}
        for row in member_rows:
            members_by_team.setdefault(str(row["team_id"]), []).append(ReviewerTeamMemberData(member_id=str(row["id"]), user_id=str(row["yudao_user_id"]), display_name=row["display_name"], reviewer_role=str(row["reviewer_role"]), priority=int(row["priority"]), max_active_assignments=int(row["max_active_assignments"]), receives_escalations=bool(row["receives_escalations"]), status=str(row["status"]), membership_source=str(row["membership_source"]), external_membership_verified=bool(row["external_membership_verified"]), version=int(row["version"]), updated_at=row["updated_at"]))
        teams = [ReviewerTeamData(team_id=str(row["id"]), name=str(row["name"]), status=str(row["status"]), external_source=str(row["external_source"]), external_group_id=row["external_group_id"], external_sync_state=str(row["external_sync_state"]), version=int(row["version"]), member_count=len(members_by_team.get(str(row["id"]), [])), members=members_by_team.get(str(row["id"]), []), created_at=row["created_at"], updated_at=row["updated_at"], idempotent_replay=str(row["id"]) == replay_team_id) for row in team_rows]
        team_names = {item.team_id: item.name for item in teams}
        route_rows = conn.execute(text("""
            SELECT route.*, team.status AS team_status,
                   SUM(CASE WHEN member.status='active' THEN 1 ELSE 0 END) AS eligible_count,
                   SUM(CASE WHEN member.status='active' AND member.receives_escalations=1 THEN 1 ELSE 0 END) AS recipient_count
            FROM airank_evidence_review_routes route
            LEFT JOIN airank_evidence_review_teams team
              ON team.tenant_id=route.tenant_id AND team.id=route.team_id
            LEFT JOIN airank_evidence_review_team_members member
              ON member.tenant_id=route.tenant_id AND member.team_id=route.team_id
             AND member.reviewer_role=route.reviewer_role
            WHERE route.tenant_id=:tenant_id AND route.project_id=:project_id
            GROUP BY route.id
            ORDER BY route.reviewer_role
        """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        routes = [ReviewerRoleRouteData(route_id=str(row["id"]), reviewer_role=str(row["reviewer_role"]), team_id=str(row["team_id"]), team_name=team_names.get(str(row["team_id"]), "已失效团队"), routing_strategy=str(row["routing_strategy"]), status=str(row["status"]), version=int(row["version"]), eligible_member_count=int(row["eligible_count"] or 0), escalation_recipient_count=int(row["recipient_count"] or 0), routing_ready=str(row["status"]) == "active" and str(row["team_status"] or "") == "active" and int(row["eligible_count"] or 0) > 0, updated_at=row["updated_at"]) for row in route_rows]
        active_roles = {
            item.reviewer_role for item in routes if item.status == "active"
        }
        configured = bool(active_roles)
        ready = active_roles == set(REVIEWER_ROLES) and all(
            item.routing_ready for item in routes if item.status == "active"
        )
        external_states = {item.external_sync_state for item in teams if item.status == "active"}
        external_sync_state = "not_configured"
        for state in ("failed", "stale", "pending", "verified"):
            if state in external_states:
                external_sync_state = state
                break
        binding_rows = conn.execute(
            text(
                """
                SELECT binding.*, team.name AS team_name
                FROM airank_evidence_review_team_sync_bindings binding
                JOIN airank_evidence_review_teams team
                  ON team.tenant_id=binding.tenant_id AND team.id=binding.team_id
                WHERE binding.tenant_id=:tenant_id
                  AND binding.project_id=:project_id
                ORDER BY binding.reviewer_role, binding.created_at, binding.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        bindings = [
            ReviewerDirectoryBindingData(
                binding_id=str(row["id"]),
                team_id=str(row["team_id"]),
                team_name=str(row["team_name"]),
                reviewer_role=str(row["reviewer_role"]),
                external_source="yudao",
                external_group_id=str(row["external_group_id"]),
                status=str(row["status"]),
                sync_enabled=bool(row["sync_enabled"]),
                sync_interval_minutes=int(row["sync_interval_minutes"]),
                default_priority=int(row["default_priority"]),
                default_max_active_assignments=int(
                    row["default_max_active_assignments"]
                ),
                default_receives_escalations=bool(
                    row["default_receives_escalations"]
                ),
                last_sync_state=str(row["last_sync_state"]),
                last_sync_run_id=(
                    str(row["last_sync_run_id"])
                    if row["last_sync_run_id"] is not None
                    else None
                ),
                last_synced_at=row["last_synced_at"],
                next_sync_at=row["next_sync_at"],
                last_error_code=row["last_error_code"],
                version=int(row["version"]),
                updated_at=row["updated_at"],
            )
            for row in binding_rows
        ]
        run_rows = conn.execute(
            text(
                """
                SELECT * FROM airank_evidence_review_team_sync_runs
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY started_at DESC, id DESC LIMIT 20
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        recent_runs = [
            ReviewerDirectorySyncRunData(
                run_id=str(row["id"]),
                binding_id=str(row["binding_id"]),
                team_id=str(row["team_id"]),
                reviewer_role=str(row["reviewer_role"]),
                external_group_id=str(row["external_group_id"]),
                status=str(row["status"]),
                endpoint_host=row["endpoint_host"],
                response_sha256=row["response_sha256"],
                discovered_member_count=int(row["discovered_member_count"]),
                active_member_count=int(row["active_member_count"]),
                upserted_member_count=int(row["upserted_member_count"]),
                disabled_member_count=int(row["disabled_member_count"]),
                error_code=row["error_code"],
                retryable=bool(row["retryable"]),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                idempotent_replay=str(row["id"]) == replay_sync_run_id,
            )
            for row in run_rows
        ]
        return ReviewerRoutingData(project_id=project_id, routing_mode=("unrestricted_legacy" if not configured else "team_routed" if ready else "blocked"), external_sync_state=external_sync_state, teams=teams, routes=routes, sync_bindings=bindings, recent_sync_runs=recent_runs, known_limitations=["yudao_group_sync_not_verified", "external_notification_delivery_not_verified"])


def build_repository() -> ReviewerRoutingRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLReviewerRoutingRepository(database_url) if database_url else InMemoryReviewerRoutingRepository()


REVIEWER_ROUTING_REPOSITORY: ReviewerRoutingRepository = build_repository()
REVIEWER_DIRECTORY_CLIENT = YudaoReviewerDirectoryClient()


@router.get(
    "/projects/{project_id}/evidence-review-routing",
    response_model=ReviewerRoutingResponse,
)
def get_reviewer_routing(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ReviewerRoutingResponse:
    require_review_admin(permissions)
    return ReviewerRoutingResponse(
        data=REVIEWER_ROUTING_REPOSITORY.get_routing(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.post(
    "/projects/{project_id}/evidence-review-teams",
    response_model=ReviewerRoutingResponse,
    status_code=201,
)
def create_reviewer_team(
    project_id: str,
    payload: ReviewerTeamCreateRequest,
    idempotency_key: str = Header(min_length=8, max_length=160, alias="Idempotency-Key"),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ReviewerRoutingResponse:
    require_review_admin(permissions)
    meta = response_meta(trace_id)
    return ReviewerRoutingResponse(
        data=REVIEWER_ROUTING_REPOSITORY.create_team(
            tenant_id,
            project_id,
            payload,
            idempotency_key,
            trusted_actor(authenticated_actor),
            meta["trace_id"],
        ),
        meta=meta,
    )


@router.put(
    "/projects/{project_id}/evidence-review-teams/{team_id}/members/{user_id}/{reviewer_role}",
    response_model=ReviewerRoutingResponse,
)
def upsert_reviewer_team_member(
    project_id: str,
    payload: ReviewerTeamMemberUpsertRequest,
    team_id: str = Path(min_length=1, max_length=64),
    user_id: str = Path(min_length=1, max_length=128),
    reviewer_role: Literal["secondary", "adjudicator"] = Path(),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ReviewerRoutingResponse:
    require_review_admin(permissions)
    meta = response_meta(trace_id)
    return ReviewerRoutingResponse(
        data=REVIEWER_ROUTING_REPOSITORY.upsert_member(
            tenant_id,
            project_id,
            team_id,
            user_id,
            reviewer_role,
            payload,
            trusted_actor(authenticated_actor),
            meta["trace_id"],
        ),
        meta=meta,
    )


@router.put(
    "/projects/{project_id}/evidence-review-routes/{reviewer_role}",
    response_model=ReviewerRoutingResponse,
)
def put_reviewer_role_route(
    project_id: str,
    payload: ReviewerRoleRoutePutRequest,
    reviewer_role: Literal["secondary", "adjudicator"] = Path(),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> ReviewerRoutingResponse:
    require_review_admin(permissions)
    meta = response_meta(trace_id)
    return ReviewerRoutingResponse(
        data=REVIEWER_ROUTING_REPOSITORY.put_route(
            tenant_id,
            project_id,
            reviewer_role,
            payload,
            trusted_actor(authenticated_actor),
            meta["trace_id"],
        ),
        meta=meta,
    )


@router.put(
    "/projects/{project_id}/evidence-review-teams/{team_id}/sync-bindings/{reviewer_role}",
    response_model=ReviewerRoutingResponse,
)
def put_reviewer_directory_binding(
    project_id: str,
    payload: ReviewerDirectoryBindingPutRequest,
    team_id: str = Path(min_length=1, max_length=64),
    reviewer_role: Literal["secondary", "adjudicator"] = Path(),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
    permissions: Optional[str] = Header(
        default=None, alias="X-AIRank-Permissions"
    ),
) -> ReviewerRoutingResponse:
    require_review_admin(permissions)
    meta = response_meta(trace_id)
    return ReviewerRoutingResponse(
        data=REVIEWER_ROUTING_REPOSITORY.put_sync_binding(
            tenant_id,
            project_id,
            team_id,
            reviewer_role,
            payload,
            trusted_actor(authenticated_actor),
            meta["trace_id"],
        ),
        meta=meta,
    )


@router.post(
    "/projects/{project_id}/evidence-review-teams/{team_id}/sync-bindings/{reviewer_role}/runs",
    response_model=ReviewerRoutingResponse,
)
def run_reviewer_directory_sync(
    project_id: str,
    team_id: str = Path(min_length=1, max_length=64),
    reviewer_role: Literal["secondary", "adjudicator"] = Path(),
    idempotency_key: str = Header(
        min_length=8, max_length=160, alias="Idempotency-Key"
    ),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
    permissions: Optional[str] = Header(
        default=None, alias="X-AIRank-Permissions"
    ),
) -> ReviewerRoutingResponse:
    require_review_admin(permissions)
    meta = response_meta(trace_id)
    return ReviewerRoutingResponse(
        data=REVIEWER_ROUTING_REPOSITORY.run_directory_sync(
            tenant_id,
            project_id,
            team_id,
            reviewer_role,
            idempotency_key,
            trusted_actor(authenticated_actor),
            meta["trace_id"],
            REVIEWER_DIRECTORY_CLIENT,
        ),
        meta=meta,
    )

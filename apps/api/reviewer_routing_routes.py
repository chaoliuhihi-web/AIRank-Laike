from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


class ReviewerRoutingData(BaseModel):
    project_id: str
    routing_mode: Literal["unrestricted_legacy", "team_routed", "blocked"]
    external_sync_state: Literal[
        "not_configured", "pending", "verified", "stale", "failed"
    ]
    teams: list[ReviewerTeamData]
    routes: list[ReviewerRoleRouteData]
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


class InMemoryReviewerRoutingRepository:
    def __init__(self) -> None:
        self.lock = RLock()
        self.projects: set[tuple[str, str]] = {("tenant_1", "project_1")}
        self.teams: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self.members: dict[tuple[str, str], dict[tuple[str, str, str], dict[str, Any]]] = {}
        self.routes: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self.idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}

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

    def _project(self, tenant_id: str, project_id: str) -> None:
        if (tenant_id, project_id) not in self.projects:
            raise StarletteHTTPException(404, detail={"code": "PROJECT_NOT_FOUND"})

    def _data(
        self,
        tenant_id: str,
        project_id: str,
        replay_team_id: str | None = None,
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
        return ReviewerRoutingData(
            project_id=project_id,
            routing_mode=("unrestricted_legacy" if not configured else "team_routed" if ready else "blocked"),
            external_sync_state="not_configured",
            teams=teams,
            routes=route_rows,
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

    def _data(self, conn: Any, tenant_id: str, project_id: str, replay_team_id: str | None = None) -> ReviewerRoutingData:
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
        return ReviewerRoutingData(project_id=project_id, routing_mode=("unrestricted_legacy" if not configured else "team_routed" if ready else "blocked"), external_sync_state=external_sync_state, teams=teams, routes=routes, known_limitations=["yudao_group_sync_not_verified", "external_notification_delivery_not_verified"])


def build_repository() -> ReviewerRoutingRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLReviewerRoutingRepository(database_url) if database_url else InMemoryReviewerRoutingRepository()


REVIEWER_ROUTING_REPOSITORY: ReviewerRoutingRepository = build_repository()


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

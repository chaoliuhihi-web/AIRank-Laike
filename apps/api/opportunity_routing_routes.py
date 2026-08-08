from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Literal, Mapping, Optional, Protocol

from fastapi import APIRouter, Header, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.opportunity_routes import canonical_sha256, error, response_meta, stable_id


router = APIRouter(prefix="/api/v1", tags=["opportunity-action-routing"])

ROUTING_CONTRACT_VERSION = "airank.opportunity-action-routing.v1"
SOURCE_KINDS = (
    "brand_visibility",
    "citation_support",
    "fact_governance",
    "page_extractability",
)
SourceKind = Literal[
    "brand_visibility",
    "citation_support",
    "fact_governance",
    "page_extractability",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def auth_enforcement_required() -> bool:
    return os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower() in {
        "1",
        "true",
        "yes",
        "required",
    }


def opportunity_admin_permission() -> str:
    return (
        os.getenv(
            "AIRANK_OPPORTUNITY_ADMIN_PERMISSION", "airank:opportunity:admin"
        ).strip()
        or "airank:opportunity:admin"
    )


def require_opportunity_admin(permission_header: Optional[str]) -> None:
    if not auth_enforcement_required():
        return
    granted = {
        item.strip() for item in (permission_header or "").split(",") if item.strip()
    }
    required = opportunity_admin_permission()
    namespace = required.rsplit(":", 1)[0]
    if not granted.intersection({required, "*", "*:*:*", f"{namespace}:*"}):
        raise error(
            403,
            "AUTH_PERMISSION_FORBIDDEN",
            {"required_permission": required},
        )


def trusted_admin_actor(authenticated_actor: Optional[str]) -> str:
    actor = str(authenticated_actor or "").strip()
    if actor:
        return actor[:128]
    if not auth_enforcement_required():
        return "console-opportunity-admin"
    raise error(401, "AUTH_TOKEN_INVALID", {"reason": "authenticated_actor_required"})


class OpportunityActionTeamCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)


class OpportunityActionMemberUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    priority: int = Field(default=100, ge=1, le=10_000)
    max_active_actions: int = Field(default=5, ge=1, le=100)
    receives_escalations: bool = True
    expected_version: Optional[int] = Field(default=None, ge=1)


class OpportunityActionRoutePutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(min_length=1, max_length=64)
    expected_version: Optional[int] = Field(default=None, ge=1)


class OpportunityActionTeamMemberData(BaseModel):
    member_id: str
    user_id: str
    display_name: Optional[str]
    priority: int
    max_active_actions: int
    active_action_count: int = Field(ge=0)
    at_capacity: bool
    receives_escalations: bool
    status: Literal["active", "disabled"]
    membership_source: Literal["manual", "yudao"]
    external_membership_verified: bool
    version: int = Field(ge=1)
    updated_at: datetime


class OpportunityActionTeamData(BaseModel):
    team_id: str
    name: str
    status: Literal["active", "disabled"]
    external_source: Literal["manual", "yudao"]
    external_group_id: Optional[str]
    external_sync_state: Literal[
        "not_configured", "pending", "verified", "stale", "failed"
    ]
    version: int = Field(ge=1)
    member_count: int = Field(ge=0)
    members: list[OpportunityActionTeamMemberData]
    created_at: datetime
    updated_at: datetime


class OpportunityActionRouteData(BaseModel):
    route_id: str
    source_kind: SourceKind
    team_id: str
    team_name: str
    routing_strategy: Literal["manual_claim"]
    status: Literal["active", "disabled"]
    version: int = Field(ge=1)
    eligible_member_count: int = Field(ge=0)
    escalation_recipient_count: int = Field(ge=0)
    routing_ready: bool
    updated_at: datetime


class OpportunityActionRoutingData(BaseModel):
    project_id: str
    contract_version: Literal["airank.opportunity-action-routing.v1"]
    routing_mode: Literal["unrestricted_legacy", "team_routed", "blocked"]
    teams: list[OpportunityActionTeamData]
    routes: list[OpportunityActionRouteData]
    missing_source_kinds: list[SourceKind]
    known_limitations: list[str]
    idempotent_replay: bool = False


class OpportunityActionRoutingResponse(BaseModel):
    data: OpportunityActionRoutingData
    meta: dict[str, str]


@dataclass(frozen=True)
class ActionClaimRouteSnapshot:
    routing_state: str
    team_id: Optional[str]
    route_version: Optional[int]
    member_id: Optional[str]
    member_version: Optional[int]
    external_membership_verified: bool
    eligible_member_count: int
    escalation_recipient_count: int
    active_action_count: int
    max_active_actions: Optional[int]
    at_capacity: bool
    reason: Optional[str]


def _route_row(
    conn: Any,
    tenant_id: str,
    project_id: str,
    source_kind: str,
) -> tuple[int, Optional[Mapping[str, Any]]]:
    configured_count = int(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM airank_opportunity_action_routes "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id"
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).scalar_one()
    )
    if configured_count == 0:
        return 0, None
    row = conn.execute(
        text(
            """
            SELECT route.*, team.status AS team_status,
                   team.external_sync_state AS team_external_sync_state
            FROM airank_opportunity_action_routes route
            JOIN airank_opportunity_action_teams team
              ON team.tenant_id=route.tenant_id AND team.id=route.team_id
            WHERE route.tenant_id=:tenant_id AND route.project_id=:project_id
              AND route.source_kind=:source_kind
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "source_kind": source_kind,
        },
    ).mappings().first()
    return configured_count, row


def resolve_action_claim_route(
    conn: Any,
    dialect_name: str,
    tenant_id: str,
    project_id: str,
    source_kind: str,
    actor: str,
    *,
    action_id: Optional[str] = None,
    lock_member: bool = False,
) -> ActionClaimRouteSnapshot:
    configured_count, route = _route_row(conn, tenant_id, project_id, source_kind)
    if configured_count == 0:
        return ActionClaimRouteSnapshot(
            routing_state="unrestricted_legacy",
            team_id=None,
            route_version=None,
            member_id=None,
            member_version=None,
            external_membership_verified=False,
            eligible_member_count=0,
            escalation_recipient_count=0,
            active_action_count=0,
            max_active_actions=None,
            at_capacity=False,
            reason=None,
        )
    if (
        route is None
        or str(route["status"]) != "active"
        or str(route["team_status"]) != "active"
    ):
        return ActionClaimRouteSnapshot(
            routing_state="blocked",
            team_id=str(route["team_id"]) if route else None,
            route_version=int(route["version"]) if route else None,
            member_id=None,
            member_version=None,
            external_membership_verified=False,
            eligible_member_count=0,
            escalation_recipient_count=0,
            active_action_count=0,
            max_active_actions=None,
            at_capacity=False,
            reason="source_route_missing_or_disabled",
        )
    team_id = str(route["team_id"])
    counts = conn.execute(
        text(
            """
            SELECT
              SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS eligible_count,
              SUM(CASE WHEN status='active' AND receives_escalations=1
                       THEN 1 ELSE 0 END) AS recipient_count
            FROM airank_opportunity_action_team_members
            WHERE tenant_id=:tenant_id AND project_id=:project_id AND team_id=:team_id
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id, "team_id": team_id},
    ).mappings().one()
    eligible_count = int(counts["eligible_count"] or 0)
    recipient_count = int(counts["recipient_count"] or 0)
    suffix = " FOR UPDATE" if lock_member and dialect_name == "mysql" else ""
    member = conn.execute(
        text(
            "SELECT * FROM airank_opportunity_action_team_members "
            "WHERE tenant_id=:tenant_id AND project_id=:project_id "
            "AND team_id=:team_id AND user_id=:user_id AND status='active'" + suffix
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "team_id": team_id,
            "user_id": actor,
        },
    ).mappings().first()
    if member is None:
        return ActionClaimRouteSnapshot(
            routing_state="blocked",
            team_id=team_id,
            route_version=int(route["version"]),
            member_id=None,
            member_version=None,
            external_membership_verified=False,
            eligible_member_count=eligible_count,
            escalation_recipient_count=recipient_count,
            active_action_count=0,
            max_active_actions=None,
            at_capacity=False,
            reason="actor_is_not_active_team_member",
        )
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "actor": actor,
    }
    exclude_sql = ""
    if action_id:
        exclude_sql = " AND id<>:action_id"
        params["action_id"] = action_id
    active_count = int(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM airank_opportunity_actions "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "AND assigned_to=:actor "
                "AND status IN ('open','in_progress','evidence_blocked')" + exclude_sql
            ),
            params,
        ).scalar_one()
    )
    maximum = int(member["max_active_actions"])
    at_capacity = active_count >= maximum
    return ActionClaimRouteSnapshot(
        routing_state="blocked" if at_capacity else "team_routed",
        team_id=team_id,
        route_version=int(route["version"]),
        member_id=str(member["id"]),
        member_version=int(member["version"]),
        external_membership_verified=bool(member["external_membership_verified"]),
        eligible_member_count=eligible_count,
        escalation_recipient_count=recipient_count,
        active_action_count=active_count,
        max_active_actions=maximum,
        at_capacity=at_capacity,
        reason="member_capacity_reached" if at_capacity else None,
    )


def resolve_action_route_summary(
    conn: Any,
    tenant_id: str,
    project_id: str,
    source_kind: str,
) -> ActionClaimRouteSnapshot:
    configured_count, route = _route_row(conn, tenant_id, project_id, source_kind)
    if configured_count == 0:
        return ActionClaimRouteSnapshot(
            routing_state="unrestricted_legacy",
            team_id=None,
            route_version=None,
            member_id=None,
            member_version=None,
            external_membership_verified=False,
            eligible_member_count=0,
            escalation_recipient_count=0,
            active_action_count=0,
            max_active_actions=None,
            at_capacity=False,
            reason=None,
        )
    if (
        route is None
        or str(route["status"]) != "active"
        or str(route["team_status"]) != "active"
    ):
        return ActionClaimRouteSnapshot(
            routing_state="blocked",
            team_id=str(route["team_id"]) if route else None,
            route_version=int(route["version"]) if route else None,
            member_id=None,
            member_version=None,
            external_membership_verified=False,
            eligible_member_count=0,
            escalation_recipient_count=0,
            active_action_count=0,
            max_active_actions=None,
            at_capacity=False,
            reason="source_route_missing_or_disabled",
        )
    counts = conn.execute(
        text(
            """
            SELECT
              SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS eligible_count,
              SUM(CASE WHEN status='active' AND receives_escalations=1
                       THEN 1 ELSE 0 END) AS recipient_count
            FROM airank_opportunity_action_team_members
            WHERE tenant_id=:tenant_id AND project_id=:project_id AND team_id=:team_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "team_id": str(route["team_id"]),
        },
    ).mappings().one()
    eligible_count = int(counts["eligible_count"] or 0)
    recipient_count = int(counts["recipient_count"] or 0)
    return ActionClaimRouteSnapshot(
        routing_state="team_routed" if eligible_count > 0 else "blocked",
        team_id=str(route["team_id"]),
        route_version=int(route["version"]),
        member_id=None,
        member_version=None,
        external_membership_verified=False,
        eligible_member_count=eligible_count,
        escalation_recipient_count=recipient_count,
        active_action_count=0,
        max_active_actions=None,
        at_capacity=False,
        reason=None if eligible_count > 0 else "route_has_no_active_members",
    )


class OpportunityActionRoutingRepository(Protocol):
    def get_routing(
        self, tenant_id: str, project_id: str, *, idempotent_replay: bool = False
    ) -> OpportunityActionRoutingData: ...

    def create_team(
        self,
        tenant_id: str,
        project_id: str,
        payload: OpportunityActionTeamCreateRequest,
        idempotency_key: str,
        actor: str,
    ) -> OpportunityActionRoutingData: ...

    def upsert_member(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        user_id: str,
        payload: OpportunityActionMemberUpsertRequest,
        actor: str,
    ) -> OpportunityActionRoutingData: ...

    def put_route(
        self,
        tenant_id: str,
        project_id: str,
        source_kind: str,
        payload: OpportunityActionRoutePutRequest,
        actor: str,
    ) -> OpportunityActionRoutingData: ...


class InMemoryOpportunityActionRoutingRepository:
    def get_routing(
        self, tenant_id: str, project_id: str, *, idempotent_replay: bool = False
    ) -> OpportunityActionRoutingData:
        return OpportunityActionRoutingData(
            project_id=project_id,
            contract_version=ROUTING_CONTRACT_VERSION,
            routing_mode="unrestricted_legacy",
            teams=[],
            routes=[],
            missing_source_kinds=list(SOURCE_KINDS),
            known_limitations=[
                "manual_membership_not_externally_verified",
                "yudao_action_team_sync_not_configured",
            ],
            idempotent_replay=idempotent_replay,
        )

    def create_team(self, *args: Any, **kwargs: Any) -> OpportunityActionRoutingData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_action_routing"})

    def upsert_member(self, *args: Any, **kwargs: Any) -> OpportunityActionRoutingData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_action_routing"})

    def put_route(self, *args: Any, **kwargs: Any) -> OpportunityActionRoutingData:
        raise error(409, "DATABASE_NOT_CONFIGURED", {"domain": "opportunity_action_routing"})


class MySQLOpportunityActionRoutingRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def get_routing(
        self, tenant_id: str, project_id: str, *, idempotent_replay: bool = False
    ) -> OpportunityActionRoutingData:
        with self.engine.begin() as conn:
            self._require_project(conn, tenant_id, project_id)
            return self._routing_data(
                conn, tenant_id, project_id, idempotent_replay=idempotent_replay
            )

    def create_team(
        self,
        tenant_id: str,
        project_id: str,
        payload: OpportunityActionTeamCreateRequest,
        idempotency_key: str,
        actor: str,
    ) -> OpportunityActionRoutingData:
        request_sha256 = canonical_sha256(
            {
                "contract_version": ROUTING_CONTRACT_VERSION,
                "operation": "create_team",
                "name": payload.name.strip(),
            }
        )
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            self._require_project(conn, tenant_id, project_id)
            replay = conn.execute(
                text(
                    "SELECT request_sha256 FROM airank_opportunity_action_teams "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND idempotency_key=:idempotency_key"
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
            if replay is not None:
                if str(replay["request_sha256"]) != request_sha256:
                    raise error(409, "IDEMPOTENCY_CONFLICT", {"operation": "create_team"})
                return self._routing_data(conn, tenant_id, project_id, idempotent_replay=True)
            team_id = stable_id(
                "opportunity_action_team", tenant_id, project_id, payload.name.strip()
            )
            try:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_action_teams (
                          id, tenant_id, project_id, name, status,
                          external_source, external_group_id, external_sync_state,
                          idempotency_key, request_sha256, version,
                          created_by, updated_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :name, 'active',
                          'manual', NULL, 'not_configured', :idempotency_key,
                          :request_sha256, 1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": team_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "name": payload.name.strip(),
                        "idempotency_key": idempotency_key,
                        "request_sha256": request_sha256,
                        "actor": actor,
                        "at": at,
                    },
                )
            except IntegrityError as exc:
                raise error(
                    409,
                    "OPPORTUNITY_ACTION_TEAM_CONFLICT",
                    {"name": payload.name.strip()},
                ) from exc
            return self._routing_data(conn, tenant_id, project_id)

    def upsert_member(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        user_id: str,
        payload: OpportunityActionMemberUpsertRequest,
        actor: str,
    ) -> OpportunityActionRoutingData:
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            self._require_team(conn, tenant_id, project_id, team_id)
            suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_action_team_members "
                    "WHERE tenant_id=:tenant_id AND team_id=:team_id AND user_id=:user_id"
                    + suffix
                ),
                {"tenant_id": tenant_id, "team_id": team_id, "user_id": user_id},
            ).mappings().first()
            if existing is None:
                if payload.expected_version is not None:
                    raise error(
                        409,
                        "OPPORTUNITY_ACTION_MEMBER_VERSION_CONFLICT",
                        {"expected_version": payload.expected_version, "actual_version": None},
                    )
                member_id = stable_id("opportunity_action_member", tenant_id, team_id, user_id)
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_action_team_members (
                          id, tenant_id, project_id, team_id, user_id, display_name,
                          priority, max_active_actions, receives_escalations,
                          status, membership_source, external_membership_verified,
                          version, created_by, updated_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :team_id, :user_id,
                          :display_name, :priority, :max_active_actions, :receives,
                          'active', 'manual', 0, 1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": member_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "team_id": team_id,
                        "user_id": user_id,
                        "display_name": payload.display_name,
                        "priority": payload.priority,
                        "max_active_actions": payload.max_active_actions,
                        "receives": payload.receives_escalations,
                        "actor": actor,
                        "at": at,
                    },
                )
            else:
                actual_version = int(existing["version"])
                if payload.expected_version != actual_version:
                    raise error(
                        409,
                        "OPPORTUNITY_ACTION_MEMBER_VERSION_CONFLICT",
                        {
                            "expected_version": payload.expected_version,
                            "actual_version": actual_version,
                        },
                    )
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_team_members
                        SET display_name=:display_name, priority=:priority,
                            max_active_actions=:max_active_actions,
                            receives_escalations=:receives, status='active',
                            version=:version, updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:id
                        """
                    ),
                    {
                        "display_name": payload.display_name,
                        "priority": payload.priority,
                        "max_active_actions": payload.max_active_actions,
                        "receives": payload.receives_escalations,
                        "version": actual_version + 1,
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "id": str(existing["id"]),
                    },
                )
            return self._routing_data(conn, tenant_id, project_id)

    def put_route(
        self,
        tenant_id: str,
        project_id: str,
        source_kind: str,
        payload: OpportunityActionRoutePutRequest,
        actor: str,
    ) -> OpportunityActionRoutingData:
        if source_kind not in SOURCE_KINDS:
            raise error(422, "VALIDATION_ERROR", {"field": "source_kind"})
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            self._require_team(conn, tenant_id, project_id, payload.team_id)
            suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_action_routes "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND source_kind=:source_kind" + suffix
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_kind": source_kind,
                },
            ).mappings().first()
            if existing is None:
                if payload.expected_version is not None:
                    raise error(
                        409,
                        "OPPORTUNITY_ACTION_ROUTE_VERSION_CONFLICT",
                        {"expected_version": payload.expected_version, "actual_version": None},
                    )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_action_routes (
                          id, tenant_id, project_id, source_kind, team_id,
                          routing_strategy, status, version, created_by,
                          updated_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :source_kind, :team_id,
                          'manual_claim', 'active', 1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": stable_id(
                            "opportunity_action_route", tenant_id, project_id, source_kind
                        ),
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "source_kind": source_kind,
                        "team_id": payload.team_id,
                        "actor": actor,
                        "at": at,
                    },
                )
            else:
                actual_version = int(existing["version"])
                if payload.expected_version != actual_version:
                    raise error(
                        409,
                        "OPPORTUNITY_ACTION_ROUTE_VERSION_CONFLICT",
                        {
                            "expected_version": payload.expected_version,
                            "actual_version": actual_version,
                        },
                    )
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_routes
                        SET team_id=:team_id, status='active', version=:version,
                            updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:id
                        """
                    ),
                    {
                        "team_id": payload.team_id,
                        "version": actual_version + 1,
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "id": str(existing["id"]),
                    },
                )
            return self._routing_data(conn, tenant_id, project_id)

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
    def _require_team(
        cls, conn: Any, tenant_id: str, project_id: str, team_id: str
    ) -> Mapping[str, Any]:
        cls._require_project(conn, tenant_id, project_id)
        row = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_action_teams "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:team_id"
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "team_id": team_id},
        ).mappings().first()
        if row is None:
            raise error(404, "OPPORTUNITY_ACTION_TEAM_NOT_FOUND", {"team_id": team_id})
        if str(row["status"]) != "active":
            raise error(409, "OPPORTUNITY_ACTION_ROUTING_BLOCKED", {"reason": "team_disabled"})
        return row

    @staticmethod
    def _routing_data(
        conn: Any,
        tenant_id: str,
        project_id: str,
        *,
        idempotent_replay: bool = False,
    ) -> OpportunityActionRoutingData:
        team_rows = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_action_teams "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "ORDER BY created_at, id"
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        member_rows = conn.execute(
            text(
                """
                SELECT member.*,
                       (SELECT COUNT(*) FROM airank_opportunity_actions action
                        WHERE action.tenant_id=member.tenant_id
                          AND action.project_id=member.project_id
                          AND action.assigned_to=member.user_id
                          AND action.status IN ('open','in_progress','evidence_blocked'))
                         AS active_action_count
                FROM airank_opportunity_action_team_members member
                WHERE member.tenant_id=:tenant_id AND member.project_id=:project_id
                ORDER BY member.team_id, member.priority, member.user_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        members_by_team: dict[str, list[OpportunityActionTeamMemberData]] = {}
        for row in member_rows:
            active_count = int(row["active_action_count"] or 0)
            maximum = int(row["max_active_actions"])
            members_by_team.setdefault(str(row["team_id"]), []).append(
                OpportunityActionTeamMemberData(
                    member_id=str(row["id"]),
                    user_id=str(row["user_id"]),
                    display_name=row["display_name"],
                    priority=int(row["priority"]),
                    max_active_actions=maximum,
                    active_action_count=active_count,
                    at_capacity=active_count >= maximum,
                    receives_escalations=bool(row["receives_escalations"]),
                    status=str(row["status"]),
                    membership_source=str(row["membership_source"]),
                    external_membership_verified=bool(
                        row["external_membership_verified"]
                    ),
                    version=int(row["version"]),
                    updated_at=row["updated_at"],
                )
            )
        teams = [
            OpportunityActionTeamData(
                team_id=str(row["id"]),
                name=str(row["name"]),
                status=str(row["status"]),
                external_source=str(row["external_source"]),
                external_group_id=row["external_group_id"],
                external_sync_state=str(row["external_sync_state"]),
                version=int(row["version"]),
                member_count=len(members_by_team.get(str(row["id"]), [])),
                members=members_by_team.get(str(row["id"]), []),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in team_rows
        ]
        team_names = {item.team_id: item.name for item in teams}
        route_rows = conn.execute(
            text(
                """
                SELECT route.*, team.status AS team_status,
                       SUM(CASE WHEN member.status='active' THEN 1 ELSE 0 END)
                         AS eligible_count,
                       SUM(CASE WHEN member.status='active'
                                      AND member.receives_escalations=1
                                THEN 1 ELSE 0 END) AS recipient_count
                FROM airank_opportunity_action_routes route
                JOIN airank_opportunity_action_teams team
                  ON team.tenant_id=route.tenant_id AND team.id=route.team_id
                LEFT JOIN airank_opportunity_action_team_members member
                  ON member.tenant_id=route.tenant_id AND member.team_id=route.team_id
                WHERE route.tenant_id=:tenant_id AND route.project_id=:project_id
                GROUP BY route.id, route.tenant_id, route.project_id,
                         route.source_kind, route.team_id, route.routing_strategy,
                         route.status, route.version, route.created_by,
                         route.updated_by, route.created_at, route.updated_at,
                         team.status
                ORDER BY route.source_kind
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        routes = [
            OpportunityActionRouteData(
                route_id=str(row["id"]),
                source_kind=str(row["source_kind"]),
                team_id=str(row["team_id"]),
                team_name=team_names.get(str(row["team_id"]), "已失效团队"),
                routing_strategy=str(row["routing_strategy"]),
                status=str(row["status"]),
                version=int(row["version"]),
                eligible_member_count=int(row["eligible_count"] or 0),
                escalation_recipient_count=int(row["recipient_count"] or 0),
                routing_ready=(
                    str(row["status"]) == "active"
                    and str(row["team_status"]) == "active"
                    and int(row["eligible_count"] or 0) > 0
                ),
                updated_at=row["updated_at"],
            )
            for row in route_rows
        ]
        route_by_kind = {item.source_kind: item for item in routes}
        missing = [kind for kind in SOURCE_KINDS if kind not in route_by_kind]
        configured = bool(routes)
        ready = configured and not missing and all(item.routing_ready for item in routes)
        mode = "unrestricted_legacy" if not configured else "team_routed" if ready else "blocked"
        return OpportunityActionRoutingData(
            project_id=project_id,
            contract_version=ROUTING_CONTRACT_VERSION,
            routing_mode=mode,
            teams=teams,
            routes=routes,
            missing_source_kinds=missing,
            known_limitations=[
                "manual_membership_not_externally_verified",
                "yudao_action_team_sync_not_configured",
                "external_notification_delivery_requires_customer_webhook",
            ],
            idempotent_replay=idempotent_replay,
        )


def build_repository() -> OpportunityActionRoutingRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL", "").strip()
    return (
        MySQLOpportunityActionRoutingRepository(database_url)
        if database_url
        else InMemoryOpportunityActionRoutingRepository()
    )


OPPORTUNITY_ACTION_ROUTING_REPOSITORY: OpportunityActionRoutingRepository = (
    build_repository()
)


@router.get(
    "/projects/{project_id}/opportunity-action-routing",
    response_model=OpportunityActionRoutingResponse,
)
def get_opportunity_action_routing(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
) -> OpportunityActionRoutingResponse:
    return OpportunityActionRoutingResponse(
        data=OPPORTUNITY_ACTION_ROUTING_REPOSITORY.get_routing(
            tenant_id, project_id
        ),
        meta=response_meta(trace_id),
    )


@router.post(
    "/projects/{project_id}/opportunity-action-teams",
    response_model=OpportunityActionRoutingResponse,
    status_code=201,
)
def create_opportunity_action_team(
    project_id: str,
    payload: OpportunityActionTeamCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityActionRoutingResponse:
    require_opportunity_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityActionRoutingResponse(
        data=OPPORTUNITY_ACTION_ROUTING_REPOSITORY.create_team(
            tenant_id,
            project_id,
            payload,
            idempotency_key,
            trusted_admin_actor(authenticated_actor),
        ),
        meta=meta,
    )


@router.put(
    "/projects/{project_id}/opportunity-action-teams/{team_id}/members/{user_id}",
    response_model=OpportunityActionRoutingResponse,
)
def upsert_opportunity_action_team_member(
    project_id: str,
    payload: OpportunityActionMemberUpsertRequest,
    team_id: str = Path(min_length=1, max_length=64),
    user_id: str = Path(min_length=1, max_length=128),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityActionRoutingResponse:
    require_opportunity_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityActionRoutingResponse(
        data=OPPORTUNITY_ACTION_ROUTING_REPOSITORY.upsert_member(
            tenant_id,
            project_id,
            team_id,
            user_id,
            payload,
            trusted_admin_actor(authenticated_actor),
        ),
        meta=meta,
    )


@router.put(
    "/projects/{project_id}/opportunity-action-routes/{source_kind}",
    response_model=OpportunityActionRoutingResponse,
)
def put_opportunity_action_route(
    project_id: str,
    payload: OpportunityActionRoutePutRequest,
    source_kind: SourceKind = Path(),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> OpportunityActionRoutingResponse:
    require_opportunity_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityActionRoutingResponse(
        data=OPPORTUNITY_ACTION_ROUTING_REPOSITORY.put_route(
            tenant_id,
            project_id,
            source_kind,
            payload,
            trusted_admin_actor(authenticated_actor),
        ),
        meta=meta,
    )

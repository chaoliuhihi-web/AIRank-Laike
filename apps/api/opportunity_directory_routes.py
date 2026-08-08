from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol

from fastapi import APIRouter, Header, Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, text

from airank_xinghe_adapter import (
    YudaoDirectoryError,
    YudaoReviewerDirectoryClient as YudaoDirectoryClient,
    YudaoReviewerDirectorySnapshot as YudaoDirectorySnapshot,
)
from apps.api.opportunity_routes import canonical_sha256, error, response_meta, stable_id
from apps.api.opportunity_routing_routes import (
    require_opportunity_admin,
    trusted_admin_actor,
)


router = APIRouter(prefix="/api/v1", tags=["opportunity-action-directory"])

DIRECTORY_SYNC_CONTRACT_VERSION = "airank.opportunity-action-directory-sync.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class OpportunityActionDirectoryBindingPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_group_id: str = Field(min_length=1, max_length=128)
    sync_enabled: bool = True
    sync_interval_minutes: int = Field(default=60, ge=15, le=10_080)
    default_priority: int = Field(default=100, ge=1, le=10_000)
    default_max_active_actions: int = Field(default=5, ge=1, le=100)
    default_receives_escalations: bool = True
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("external_group_id")
    @classmethod
    def validate_external_group_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_group_id must not be blank")
        return normalized


class OpportunityActionDirectoryBindingData(BaseModel):
    binding_id: str
    team_id: str
    team_name: str
    external_source: Literal["yudao"] = "yudao"
    external_group_id: str
    status: Literal["active", "disabled"]
    sync_enabled: bool
    sync_interval_minutes: int
    default_priority: int
    default_max_active_actions: int
    default_receives_escalations: bool
    last_sync_state: Literal[
        "not_configured", "pending", "verified", "stale", "failed"
    ]
    last_sync_run_id: Optional[str]
    last_synced_at: Optional[datetime]
    next_sync_at: Optional[datetime]
    last_error_code: Optional[str]
    version: int = Field(ge=1)
    updated_at: datetime


class OpportunityActionDirectorySyncRunData(BaseModel):
    run_id: str
    binding_id: str
    binding_version: int = Field(ge=1)
    team_id: str
    external_group_id: str
    status: Literal["running", "succeeded", "failed"]
    endpoint_host: Optional[str]
    response_sha256: Optional[str]
    discovered_member_count: int = Field(ge=0)
    active_member_count: int = Field(ge=0)
    created_member_count: int = Field(ge=0)
    updated_member_count: int = Field(ge=0)
    unchanged_member_count: int = Field(ge=0)
    disabled_member_count: int = Field(ge=0)
    manual_conflict_count: int = Field(ge=0)
    error_code: Optional[str]
    retryable: bool
    started_at: datetime
    finished_at: Optional[datetime]
    idempotent_replay: bool = False


class OpportunityActionDirectoryData(BaseModel):
    project_id: str
    contract_version: Literal["airank.opportunity-action-directory-sync.v1"]
    bindings: list[OpportunityActionDirectoryBindingData]
    recent_sync_runs: list[OpportunityActionDirectorySyncRunData]
    configured_team_count: int = Field(ge=0)
    verified_team_count: int = Field(ge=0)
    known_limitations: list[str]


class OpportunityActionDirectoryResponse(BaseModel):
    data: OpportunityActionDirectoryData
    meta: dict[str, str]


class OpportunityActionDirectoryRepository(Protocol):
    def get_state(
        self,
        tenant_id: str,
        project_id: str,
        *,
        replay_run_id: str | None = None,
    ) -> OpportunityActionDirectoryData: ...

    def put_binding(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        payload: OpportunityActionDirectoryBindingPutRequest,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionDirectoryData: ...

    def run_sync(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        idempotency_key: str,
        actor: str,
        trace_id: str,
        directory_client: YudaoDirectoryClient,
    ) -> OpportunityActionDirectoryData: ...


class InMemoryOpportunityActionDirectoryRepository:
    def get_state(
        self,
        tenant_id: str,
        project_id: str,
        *,
        replay_run_id: str | None = None,
    ) -> OpportunityActionDirectoryData:
        del tenant_id, replay_run_id
        return OpportunityActionDirectoryData(
            project_id=project_id,
            contract_version=DIRECTORY_SYNC_CONTRACT_VERSION,
            bindings=[],
            recent_sync_runs=[],
            configured_team_count=0,
            verified_team_count=0,
            known_limitations=[
                "database_not_configured",
                "yudao_directory_endpoint_not_verified",
            ],
        )

    def put_binding(self, *args: Any, **kwargs: Any) -> OpportunityActionDirectoryData:
        raise error(
            409,
            "DATABASE_NOT_CONFIGURED",
            {"domain": "opportunity_action_directory"},
        )

    def run_sync(self, *args: Any, **kwargs: Any) -> OpportunityActionDirectoryData:
        raise error(
            409,
            "DATABASE_NOT_CONFIGURED",
            {"domain": "opportunity_action_directory"},
        )


class MySQLOpportunityActionDirectoryRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def get_state(
        self,
        tenant_id: str,
        project_id: str,
        *,
        replay_run_id: str | None = None,
    ) -> OpportunityActionDirectoryData:
        with self.engine.begin() as conn:
            self._require_project(conn, tenant_id, project_id)
            return self._data(
                conn,
                tenant_id,
                project_id,
                replay_run_id=replay_run_id,
            )

    def put_binding(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        payload: OpportunityActionDirectoryBindingPutRequest,
        actor: str,
        trace_id: str,
    ) -> OpportunityActionDirectoryData:
        at = database_datetime(utc_now())
        lock = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        external_group_id = payload.external_group_id.strip()
        request_sha256 = canonical_sha256(
            {
                "contract_version": DIRECTORY_SYNC_CONTRACT_VERSION,
                "team_id": team_id,
                "external_group_id": external_group_id,
                "sync_enabled": payload.sync_enabled,
                "sync_interval_minutes": payload.sync_interval_minutes,
                "default_priority": payload.default_priority,
                "default_max_active_actions": payload.default_max_active_actions,
                "default_receives_escalations": payload.default_receives_escalations,
            }
        )
        with self.engine.begin() as conn:
            team = self._require_team(
                conn, tenant_id, project_id, team_id, lock=bool(lock)
            )
            existing = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_action_team_sync_bindings "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND team_id=:team_id" + lock
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                },
            ).mappings().first()
            if existing is None:
                if payload.expected_version is not None:
                    raise error(
                        409,
                        "OPPORTUNITY_ACTION_DIRECTORY_VERSION_CONFLICT",
                        {
                            "expected_version": payload.expected_version,
                            "actual_version": None,
                        },
                    )
                binding_id = stable_id(
                    "opportunity_action_sync_binding", tenant_id, project_id, team_id
                )
                version = 1
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_action_team_sync_bindings (
                          id, tenant_id, project_id, team_id, external_source,
                          external_group_id, status, sync_enabled,
                          sync_interval_minutes, default_priority,
                          default_max_active_actions, default_receives_escalations,
                          last_sync_state, last_sync_run_id, last_synced_at,
                          next_sync_at, last_error_code, request_sha256, version,
                          created_by, updated_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :team_id, 'yudao',
                          :external_group_id, 'active', :sync_enabled,
                          :sync_interval_minutes, :default_priority,
                          :default_max_active_actions, :default_receives_escalations,
                          'pending', NULL, NULL, :next_sync_at, NULL,
                          :request_sha256, 1, :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": binding_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "team_id": team_id,
                        "external_group_id": external_group_id,
                        "sync_enabled": int(payload.sync_enabled),
                        "sync_interval_minutes": payload.sync_interval_minutes,
                        "default_priority": payload.default_priority,
                        "default_max_active_actions": payload.default_max_active_actions,
                        "default_receives_escalations": int(
                            payload.default_receives_escalations
                        ),
                        "next_sync_at": at if payload.sync_enabled else None,
                        "request_sha256": request_sha256,
                        "actor": actor,
                        "at": at,
                    },
                )
            else:
                actual_version = int(existing["version"])
                if payload.expected_version != actual_version:
                    raise error(
                        409,
                        "OPPORTUNITY_ACTION_DIRECTORY_VERSION_CONFLICT",
                        {
                            "expected_version": payload.expected_version,
                            "actual_version": actual_version,
                        },
                    )
                binding_id = str(existing["id"])
                version = actual_version + 1
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_team_sync_bindings
                        SET external_group_id=:external_group_id, status='active',
                            sync_enabled=:sync_enabled,
                            sync_interval_minutes=:sync_interval_minutes,
                            default_priority=:default_priority,
                            default_max_active_actions=:default_max_active_actions,
                            default_receives_escalations=:default_receives_escalations,
                            last_sync_state='pending',
                            next_sync_at=:next_sync_at, last_error_code=NULL,
                            request_sha256=:request_sha256, version=:version,
                            updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:binding_id
                        """
                    ),
                    {
                        "external_group_id": external_group_id,
                        "sync_enabled": int(payload.sync_enabled),
                        "sync_interval_minutes": payload.sync_interval_minutes,
                        "default_priority": payload.default_priority,
                        "default_max_active_actions": payload.default_max_active_actions,
                        "default_receives_escalations": int(
                            payload.default_receives_escalations
                        ),
                        "next_sync_at": at if payload.sync_enabled else None,
                        "request_sha256": request_sha256,
                        "version": version,
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "binding_id": binding_id,
                    },
                )
            conn.execute(
                text(
                    """
                    UPDATE airank_opportunity_action_teams
                    SET external_source='yudao', external_group_id=:external_group_id,
                        external_sync_state='pending', version=:version,
                        updated_by=:actor, updated_at=:at
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND id=:team_id
                    """
                ),
                {
                    "external_group_id": external_group_id,
                    "version": int(team["version"]) + 1,
                    "actor": actor,
                    "at": at,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                },
            )
            self._audit(
                conn,
                tenant_id,
                project_id,
                actor,
                "opportunity_action.directory_binding_saved",
                "opportunity_action_team_sync_binding",
                binding_id,
                trace_id,
                {
                    "contract_version": DIRECTORY_SYNC_CONTRACT_VERSION,
                    "team_id": team_id,
                    "external_group_id": external_group_id,
                    "sync_enabled": payload.sync_enabled,
                    "binding_version": version,
                    "request_sha256": request_sha256,
                },
                at,
            )
            return self._data(conn, tenant_id, project_id)

    def run_sync(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        idempotency_key: str,
        actor: str,
        trace_id: str,
        directory_client: YudaoDirectoryClient,
    ) -> OpportunityActionDirectoryData:
        started_at = utc_now()
        started_db = database_datetime(started_at)
        lock = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        with self.engine.begin() as conn:
            self._require_team(conn, tenant_id, project_id, team_id, lock=bool(lock))
            binding = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_action_team_sync_bindings "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND team_id=:team_id AND status='active'" + lock
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                },
            ).mappings().first()
            if binding is None:
                raise error(
                    404,
                    "OPPORTUNITY_ACTION_DIRECTORY_BINDING_NOT_FOUND",
                    {"team_id": team_id},
                )
            request_sha256 = canonical_sha256(
                {
                    "contract_version": DIRECTORY_SYNC_CONTRACT_VERSION,
                    "binding_id": str(binding["id"]),
                    "binding_version": int(binding["version"]),
                    "external_group_id": str(binding["external_group_id"]),
                }
            )
            replay = conn.execute(
                text(
                    "SELECT id, request_sha256 FROM "
                    "airank_opportunity_action_team_sync_runs "
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
                if str(replay["request_sha256"]) != request_sha256:
                    raise error(409, "IDEMPOTENCY_CONFLICT", {"operation": "directory_sync"})
                return self._data(
                    conn,
                    tenant_id,
                    project_id,
                    replay_run_id=str(replay["id"]),
                )
            run_id = stable_id(
                "opportunity_action_sync_run",
                tenant_id,
                str(binding["id"]),
                idempotency_key,
            )
            binding_snapshot = {
                "id": str(binding["id"]),
                "version": int(binding["version"]),
                "external_group_id": str(binding["external_group_id"]),
                "sync_interval_minutes": int(binding["sync_interval_minutes"]),
            }
            conn.execute(
                text(
                    """
                    INSERT INTO airank_opportunity_action_team_sync_runs (
                      id, tenant_id, project_id, team_id, binding_id,
                      binding_version, external_group_id, status,
                      idempotency_key, request_sha256, requested_by, trace_id,
                      endpoint_host, response_sha256, discovered_member_count,
                      active_member_count, created_member_count,
                      updated_member_count, unchanged_member_count,
                      disabled_member_count, manual_conflict_count, error_code,
                      retryable, started_at, finished_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :team_id, :binding_id,
                      :binding_version, :external_group_id, 'running',
                      :idempotency_key, :request_sha256, :actor, :trace_id,
                      NULL, NULL, 0, 0, 0, 0, 0, 0, 0, NULL, 0,
                      :started_at, NULL, :started_at
                    )
                    """
                ),
                {
                    "id": run_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                    "binding_id": binding_snapshot["id"],
                    "binding_version": binding_snapshot["version"],
                    "external_group_id": binding_snapshot["external_group_id"],
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "actor": actor,
                    "trace_id": trace_id,
                    "started_at": started_db,
                },
            )
        try:
            snapshot = directory_client.fetch_department(
                str(binding_snapshot["external_group_id"])
            )
        except YudaoDirectoryError as exc:
            self._record_failed_run(
                tenant_id,
                project_id,
                team_id,
                run_id,
                binding_snapshot,
                actor,
                trace_id,
                exc.code,
                exc.retryable,
            )
            raise error(
                503,
                "OPPORTUNITY_ACTION_DIRECTORY_SYNC_FAILED",
                {"upstream_code": exc.code, "retryable": exc.retryable},
            ) from exc

        binding_changed = False
        finished_at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            current = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_action_team_sync_bindings "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND team_id=:team_id AND status='active'" + lock
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "team_id": team_id,
                },
            ).mappings().first()
            if (
                current is None
                or str(current["id"]) != binding_snapshot["id"]
                or int(current["version"]) != binding_snapshot["version"]
                or str(current["external_group_id"])
                != binding_snapshot["external_group_id"]
            ):
                binding_changed = True
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_team_sync_runs
                        SET status='failed', error_code=:error_code, retryable=0,
                            endpoint_host=:endpoint_host,
                            response_sha256=:response_sha256,
                            discovered_member_count=:discovered_member_count,
                            finished_at=:finished_at
                        WHERE tenant_id=:tenant_id AND id=:run_id
                          AND status='running'
                        """
                    ),
                    {
                        "error_code": "OPPORTUNITY_ACTION_DIRECTORY_BINDING_CHANGED",
                        "endpoint_host": snapshot.endpoint_host,
                        "response_sha256": snapshot.response_sha256,
                        "discovered_member_count": len(snapshot.members),
                        "finished_at": finished_at,
                        "tenant_id": tenant_id,
                        "run_id": run_id,
                    },
                )
                self._audit(
                    conn,
                    tenant_id,
                    project_id,
                    actor,
                    "opportunity_action.directory_sync_failed",
                    "opportunity_action_team_sync_run",
                    run_id,
                    trace_id,
                    {
                        "contract_version": DIRECTORY_SYNC_CONTRACT_VERSION,
                        "binding_id": binding_snapshot["id"],
                        "binding_version": binding_snapshot["version"],
                        "team_id": team_id,
                        "response_sha256": snapshot.response_sha256,
                        "error_code": "OPPORTUNITY_ACTION_DIRECTORY_BINDING_CHANGED",
                        "retryable": False,
                    },
                    finished_at,
                )
            else:
                counts = self._apply_snapshot(
                    conn,
                    tenant_id,
                    project_id,
                    team_id,
                    current,
                    snapshot,
                    actor,
                    finished_at,
                )
                next_sync_at = finished_at + timedelta(
                    minutes=int(current["sync_interval_minutes"])
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_team_sync_bindings
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
                        "next_sync_at": next_sync_at,
                        "actor": actor,
                        "tenant_id": tenant_id,
                        "binding_id": binding_snapshot["id"],
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_teams
                        SET external_source='yudao',
                            external_group_id=:external_group_id,
                            external_sync_state='verified', version=version+1,
                            updated_by=:actor, updated_at=:finished_at
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND id=:team_id
                        """
                    ),
                    {
                        "external_group_id": binding_snapshot["external_group_id"],
                        "actor": actor,
                        "finished_at": finished_at,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "team_id": team_id,
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_team_sync_runs
                        SET status='succeeded', endpoint_host=:endpoint_host,
                            response_sha256=:response_sha256,
                            discovered_member_count=:discovered,
                            active_member_count=:active,
                            created_member_count=:created,
                            updated_member_count=:updated,
                            unchanged_member_count=:unchanged,
                            disabled_member_count=:disabled,
                            manual_conflict_count=:manual_conflict,
                            error_code=NULL, retryable=0,
                            finished_at=:finished_at
                        WHERE tenant_id=:tenant_id AND id=:run_id
                          AND status='running'
                        """
                    ),
                    {
                        "endpoint_host": snapshot.endpoint_host,
                        "response_sha256": snapshot.response_sha256,
                        "discovered": len(snapshot.members),
                        **counts,
                        "finished_at": finished_at,
                        "tenant_id": tenant_id,
                        "run_id": run_id,
                    },
                )
                self._audit(
                    conn,
                    tenant_id,
                    project_id,
                    actor,
                    "opportunity_action.directory_sync_succeeded",
                    "opportunity_action_team_sync_run",
                    run_id,
                    trace_id,
                    {
                        "contract_version": DIRECTORY_SYNC_CONTRACT_VERSION,
                        "binding_id": binding_snapshot["id"],
                        "binding_version": binding_snapshot["version"],
                        "team_id": team_id,
                        "response_sha256": snapshot.response_sha256,
                        **counts,
                    },
                    finished_at,
                )
                result = self._data(conn, tenant_id, project_id)
        if binding_changed:
            raise error(
                409,
                "OPPORTUNITY_ACTION_DIRECTORY_BINDING_CHANGED",
                {"team_id": team_id, "run_id": run_id},
            )
        return result

    def _record_failed_run(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        run_id: str,
        binding: Mapping[str, Any],
        actor: str,
        trace_id: str,
        error_code: str,
        retryable: bool,
    ) -> None:
        at = database_datetime(utc_now())
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_opportunity_action_team_sync_runs
                    SET status='failed', error_code=:error_code,
                        retryable=:retryable, finished_at=:at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                      AND status='running'
                    """
                ),
                {
                    "error_code": error_code,
                    "retryable": int(retryable),
                    "at": at,
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                },
            )
            current = conn.execute(
                text(
                    "SELECT version FROM airank_opportunity_action_team_sync_bindings "
                    "WHERE tenant_id=:tenant_id AND id=:binding_id"
                ),
                {"tenant_id": tenant_id, "binding_id": binding["id"]},
            ).mappings().first()
            if current is not None and int(current["version"]) == int(binding["version"]):
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_team_sync_bindings
                        SET last_sync_state='failed', last_sync_run_id=:run_id,
                            last_error_code=:error_code,
                            next_sync_at=:next_sync_at, updated_by=:actor,
                            updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:binding_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "error_code": error_code,
                        "next_sync_at": at
                        + timedelta(minutes=int(binding["sync_interval_minutes"])),
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "binding_id": binding["id"],
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_teams
                        SET external_sync_state='failed', version=version+1,
                            updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND id=:team_id
                        """
                    ),
                    {
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "team_id": team_id,
                    },
                )
            self._audit(
                conn,
                tenant_id,
                project_id,
                actor,
                "opportunity_action.directory_sync_failed",
                "opportunity_action_team_sync_run",
                run_id,
                trace_id,
                {
                    "contract_version": DIRECTORY_SYNC_CONTRACT_VERSION,
                    "binding_id": binding["id"],
                    "binding_version": binding["version"],
                    "team_id": team_id,
                    "error_code": error_code,
                    "retryable": retryable,
                },
                at,
            )

    @staticmethod
    def _apply_snapshot(
        conn: Any,
        tenant_id: str,
        project_id: str,
        team_id: str,
        binding: Mapping[str, Any],
        snapshot: YudaoDirectorySnapshot,
        actor: str,
        at: datetime,
    ) -> dict[str, int]:
        existing_rows = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_action_team_members "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "AND team_id=:team_id"
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "team_id": team_id,
            },
        ).mappings().all()
        existing_by_user = {str(row["user_id"]): row for row in existing_rows}
        active_directory_members = {
            member.user_id: member for member in snapshot.members if member.enabled
        }
        counts = {
            "active": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "disabled": 0,
            "manual_conflict": 0,
        }
        for row in existing_rows:
            user_id = str(row["user_id"])
            if (
                str(row["membership_source"]) == "yudao"
                and str(row["status"]) == "active"
                and user_id not in active_directory_members
            ):
                conn.execute(
                    text(
                        """
                        UPDATE airank_opportunity_action_team_members
                        SET status='disabled', external_membership_verified=0,
                            version=version+1, updated_by=:actor, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:member_id
                        """
                    ),
                    {
                        "actor": actor,
                        "at": at,
                        "tenant_id": tenant_id,
                        "member_id": row["id"],
                    },
                )
                counts["disabled"] += 1
        for user_id, member in active_directory_members.items():
            existing = existing_by_user.get(user_id)
            if existing is not None and str(existing["membership_source"]) != "yudao":
                counts["manual_conflict"] += 1
                continue
            display_name = member.display_name or member.username
            desired = {
                "display_name": display_name,
                "priority": int(binding["default_priority"]),
                "max_active_actions": int(binding["default_max_active_actions"]),
                "receives_escalations": bool(binding["default_receives_escalations"]),
                "status": "active",
                "membership_source": "yudao",
                "external_membership_verified": True,
            }
            if existing is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_opportunity_action_team_members (
                          id, tenant_id, project_id, team_id, user_id,
                          display_name, priority, max_active_actions,
                          receives_escalations, status, membership_source,
                          external_membership_verified, version, created_by,
                          updated_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :team_id, :user_id,
                          :display_name, :priority, :max_active_actions,
                          :receives_escalations, 'active', 'yudao', 1, 1,
                          :actor, :actor, :at, :at
                        )
                        """
                    ),
                    {
                        "id": stable_id(
                            "opportunity_action_member",
                            tenant_id,
                            team_id,
                            user_id,
                        ),
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "team_id": team_id,
                        "user_id": user_id,
                        "display_name": display_name,
                        "priority": desired["priority"],
                        "max_active_actions": desired["max_active_actions"],
                        "receives_escalations": int(
                            desired["receives_escalations"]
                        ),
                        "actor": actor,
                        "at": at,
                    },
                )
                counts["created"] += 1
                counts["active"] += 1
                continue
            unchanged = (
                existing["display_name"] == desired["display_name"]
                and int(existing["priority"]) == desired["priority"]
                and int(existing["max_active_actions"])
                == desired["max_active_actions"]
                and bool(existing["receives_escalations"])
                == desired["receives_escalations"]
                and str(existing["status"]) == "active"
                and bool(existing["external_membership_verified"])
            )
            if unchanged:
                counts["unchanged"] += 1
                counts["active"] += 1
                continue
            conn.execute(
                text(
                    """
                    UPDATE airank_opportunity_action_team_members
                    SET display_name=:display_name, priority=:priority,
                        max_active_actions=:max_active_actions,
                        receives_escalations=:receives_escalations,
                        status='active', membership_source='yudao',
                        external_membership_verified=1, version=version+1,
                        updated_by=:actor, updated_at=:at
                    WHERE tenant_id=:tenant_id AND id=:member_id
                      AND membership_source='yudao'
                    """
                ),
                {
                    "display_name": display_name,
                    "priority": desired["priority"],
                    "max_active_actions": desired["max_active_actions"],
                    "receives_escalations": int(
                        desired["receives_escalations"]
                    ),
                    "actor": actor,
                    "at": at,
                    "tenant_id": tenant_id,
                    "member_id": existing["id"],
                },
            )
            counts["updated"] += 1
            counts["active"] += 1
        return counts

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
        cls,
        conn: Any,
        tenant_id: str,
        project_id: str,
        team_id: str,
        *,
        lock: bool = False,
    ) -> Mapping[str, Any]:
        cls._require_project(conn, tenant_id, project_id)
        suffix = " FOR UPDATE" if lock else ""
        row = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_action_teams "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "AND id=:team_id" + suffix
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "team_id": team_id},
        ).mappings().first()
        if row is None:
            raise error(
                404, "OPPORTUNITY_ACTION_TEAM_NOT_FOUND", {"team_id": team_id}
            )
        if str(row["status"]) != "active":
            raise error(
                409,
                "OPPORTUNITY_ACTION_ROUTING_BLOCKED",
                {"reason": "team_disabled"},
            )
        return row

    @staticmethod
    def _audit(
        conn: Any,
        tenant_id: str,
        project_id: str,
        actor: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        trace_id: str,
        payload: Mapping[str, Any],
        at: datetime,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO airank_audit_events (
                  id, tenant_id, project_id, actor_user_id, event_type,
                  entity_type, entity_id, payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :actor, :event_type,
                  :entity_type, :entity_id, :payload_json, :created_at
                )
                """
            ),
            {
                "id": stable_id(
                    "audit_opportunity_directory",
                    tenant_id,
                    entity_id,
                    event_type,
                    str(payload.get("binding_version") or "0"),
                    str(payload.get("response_sha256") or payload.get("request_sha256") or ""),
                ),
                "tenant_id": tenant_id,
                "project_id": project_id,
                "actor": actor,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload_json": json.dumps(
                    {**payload, "trace_id": trace_id},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "created_at": at,
            },
        )

    @staticmethod
    def _data(
        conn: Any,
        tenant_id: str,
        project_id: str,
        *,
        replay_run_id: str | None = None,
    ) -> OpportunityActionDirectoryData:
        binding_rows = conn.execute(
            text(
                """
                SELECT binding.*, team.name AS team_name
                FROM airank_opportunity_action_team_sync_bindings binding
                JOIN airank_opportunity_action_teams team
                  ON team.tenant_id=binding.tenant_id AND team.id=binding.team_id
                WHERE binding.tenant_id=:tenant_id
                  AND binding.project_id=:project_id
                ORDER BY team.name, binding.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        run_rows = conn.execute(
            text(
                """
                SELECT * FROM airank_opportunity_action_team_sync_runs
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY started_at DESC, id DESC LIMIT 20
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        bindings = [
            OpportunityActionDirectoryBindingData(
                binding_id=str(row["id"]),
                team_id=str(row["team_id"]),
                team_name=str(row["team_name"]),
                external_source="yudao",
                external_group_id=str(row["external_group_id"]),
                status=str(row["status"]),
                sync_enabled=bool(row["sync_enabled"]),
                sync_interval_minutes=int(row["sync_interval_minutes"]),
                default_priority=int(row["default_priority"]),
                default_max_active_actions=int(row["default_max_active_actions"]),
                default_receives_escalations=bool(
                    row["default_receives_escalations"]
                ),
                last_sync_state=str(row["last_sync_state"]),
                last_sync_run_id=row["last_sync_run_id"],
                last_synced_at=row["last_synced_at"],
                next_sync_at=row["next_sync_at"],
                last_error_code=row["last_error_code"],
                version=int(row["version"]),
                updated_at=row["updated_at"],
            )
            for row in binding_rows
        ]
        recent_sync_runs = [
            OpportunityActionDirectorySyncRunData(
                run_id=str(row["id"]),
                binding_id=str(row["binding_id"]),
                binding_version=int(row["binding_version"]),
                team_id=str(row["team_id"]),
                external_group_id=str(row["external_group_id"]),
                status=str(row["status"]),
                endpoint_host=row["endpoint_host"],
                response_sha256=row["response_sha256"],
                discovered_member_count=int(row["discovered_member_count"]),
                active_member_count=int(row["active_member_count"]),
                created_member_count=int(row["created_member_count"]),
                updated_member_count=int(row["updated_member_count"]),
                unchanged_member_count=int(row["unchanged_member_count"]),
                disabled_member_count=int(row["disabled_member_count"]),
                manual_conflict_count=int(row["manual_conflict_count"]),
                error_code=row["error_code"],
                retryable=bool(row["retryable"]),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                idempotent_replay=str(row["id"]) == replay_run_id,
            )
            for row in run_rows
        ]
        active_bindings = [item for item in bindings if item.status == "active"]
        verified_count = sum(
            1 for item in active_bindings if item.last_sync_state == "verified"
        )
        limitations: list[str] = []
        if not active_bindings:
            limitations.append("yudao_action_team_sync_not_configured")
        elif verified_count != len(active_bindings):
            limitations.append("yudao_action_team_sync_not_verified")
        limitations.extend(
            [
                "directory_credentials_are_runtime_only",
                "manual_members_are_never_externally_verified",
            ]
        )
        return OpportunityActionDirectoryData(
            project_id=project_id,
            contract_version=DIRECTORY_SYNC_CONTRACT_VERSION,
            bindings=bindings,
            recent_sync_runs=recent_sync_runs,
            configured_team_count=len(active_bindings),
            verified_team_count=verified_count,
            known_limitations=limitations,
        )


def build_repository() -> OpportunityActionDirectoryRepository:
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    return (
        MySQLOpportunityActionDirectoryRepository(database_url)
        if database_url
        else InMemoryOpportunityActionDirectoryRepository()
    )


OPPORTUNITY_ACTION_DIRECTORY_REPOSITORY: OpportunityActionDirectoryRepository = (
    build_repository()
)
OPPORTUNITY_ACTION_DIRECTORY_CLIENT = YudaoDirectoryClient()


@router.get(
    "/projects/{project_id}/opportunity-action-directory-sync",
    response_model=OpportunityActionDirectoryResponse,
)
def get_opportunity_action_directory_sync(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(
        default=None, max_length=128, alias="X-AIRank-Trace-Id"
    ),
) -> OpportunityActionDirectoryResponse:
    return OpportunityActionDirectoryResponse(
        data=OPPORTUNITY_ACTION_DIRECTORY_REPOSITORY.get_state(
            tenant_id, project_id
        ),
        meta=response_meta(trace_id),
    )


@router.put(
    "/projects/{project_id}/opportunity-action-teams/{team_id}/sync-binding",
    response_model=OpportunityActionDirectoryResponse,
)
def put_opportunity_action_directory_binding(
    project_id: str,
    payload: OpportunityActionDirectoryBindingPutRequest,
    team_id: str = Path(min_length=1, max_length=64),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(
        default=None, max_length=128, alias="X-AIRank-Trace-Id"
    ),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
    permissions: Optional[str] = Header(
        default=None, alias="X-AIRank-Permissions"
    ),
) -> OpportunityActionDirectoryResponse:
    require_opportunity_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityActionDirectoryResponse(
        data=OPPORTUNITY_ACTION_DIRECTORY_REPOSITORY.put_binding(
            tenant_id,
            project_id,
            team_id,
            payload,
            trusted_admin_actor(authenticated_actor),
            meta["trace_id"],
        ),
        meta=meta,
    )


@router.post(
    "/projects/{project_id}/opportunity-action-teams/{team_id}/sync-runs",
    response_model=OpportunityActionDirectoryResponse,
)
def run_opportunity_action_directory_sync(
    project_id: str,
    team_id: str = Path(min_length=1, max_length=64),
    idempotency_key: str = Header(
        min_length=8, max_length=160, alias="Idempotency-Key"
    ),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(
        default=None, max_length=128, alias="X-AIRank-Trace-Id"
    ),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
    permissions: Optional[str] = Header(
        default=None, alias="X-AIRank-Permissions"
    ),
) -> OpportunityActionDirectoryResponse:
    require_opportunity_admin(permissions)
    meta = response_meta(trace_id)
    return OpportunityActionDirectoryResponse(
        data=OPPORTUNITY_ACTION_DIRECTORY_REPOSITORY.run_sync(
            tenant_id,
            project_id,
            team_id,
            idempotency_key,
            trusted_admin_actor(authenticated_actor),
            meta["trace_id"],
            OPPORTUNITY_ACTION_DIRECTORY_CLIENT,
        ),
        meta=meta,
    )

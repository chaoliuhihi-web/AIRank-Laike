from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from . import knowledge_routes
except ImportError:  # pragma: no cover - supports direct uvicorn execution.
    import knowledge_routes  # type: ignore[no-redef]


TRACE_HEADER = "X-AIRank-Trace-Id"
SYNC_CONTRACT_VERSION = "airank.knowledge-source-sync.v1"
router = APIRouter(prefix="/api/v1", tags=["knowledge-source-sync"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    if not authenticated_actor:
        raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})
    return authenticated_actor


class KnowledgeSyncPolicyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=160)
    interval_hours: int = Field(default=24, ge=1, le=720)
    created_by: str = Field(min_length=1, max_length=64)


class KnowledgeSyncPolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    enabled: bool
    interval_hours: int = Field(ge=1, le=720)
    reason: str = Field(min_length=3, max_length=500)
    updated_by: str = Field(min_length=1, max_length=64)


class KnowledgeSyncTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=160)
    requested_by: str = Field(min_length=1, max_length=64)


class KnowledgeSyncPolicyData(BaseModel):
    policy_id: str
    tenant_id: str
    project_id: str
    anchor_source_id: str
    current_source_id: str
    source_uri: str
    interval_hours: int
    enabled: bool
    version: int
    next_run_at: datetime
    last_run_id: Optional[str] = None
    last_status: Optional[Literal["unchanged", "changed", "failed", "blocked"]] = None
    last_checked_at: Optional[datetime] = None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class KnowledgeSyncRunData(BaseModel):
    run_id: str
    tenant_id: str
    project_id: str
    policy_id: str
    source_before_id: str
    source_after_id: Optional[str] = None
    job_id: str
    status: Literal["queued", "running", "unchanged", "changed", "failed", "blocked"]
    requested_url: str
    final_url: Optional[str] = None
    evidence_grade: Optional[str] = None
    response_status: Optional[int] = None
    content_type: Optional[str] = None
    response_bytes: Optional[int] = None
    raw_content_sha256: Optional[str] = None
    visible_text_sha256: Optional[str] = None
    raw_object_ref_id: Optional[str] = None
    text_object_ref_id: Optional[str] = None
    connected_ip: Optional[str] = None
    redirect_count: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    scheduled_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    idempotent_replay: bool = False


class KnowledgeSyncPolicyResponse(BaseModel):
    data: KnowledgeSyncPolicyData
    meta: dict[str, str]


class KnowledgeSyncPolicyListResponse(BaseModel):
    data: list[KnowledgeSyncPolicyData]
    meta: dict[str, str]


class KnowledgeSyncRunResponse(BaseModel):
    data: KnowledgeSyncRunData
    meta: dict[str, str]


class KnowledgeSyncRunListResponse(BaseModel):
    data: list[KnowledgeSyncRunData]
    meta: dict[str, str]


class KnowledgeSyncRepository(Protocol):
    def create_policy(
        self,
        tenant_id: str,
        project_id: str,
        source: knowledge_routes.KnowledgeSourceData,
        payload: KnowledgeSyncPolicyCreateRequest,
    ) -> KnowledgeSyncPolicyData: ...

    def list_policies(self, tenant_id: str, project_id: str) -> list[KnowledgeSyncPolicyData]: ...

    def update_policy(
        self,
        tenant_id: str,
        policy_id: str,
        payload: KnowledgeSyncPolicyUpdateRequest,
    ) -> KnowledgeSyncPolicyData: ...

    def trigger(
        self,
        tenant_id: str,
        policy_id: str,
        payload: KnowledgeSyncTriggerRequest,
    ) -> KnowledgeSyncRunData: ...

    def list_runs(
        self, tenant_id: str, project_id: str, *, policy_id: Optional[str], limit: int
    ) -> list[KnowledgeSyncRunData]: ...


class InMemoryKnowledgeSyncRepository:
    def __init__(self) -> None:
        self.policies: dict[tuple[str, str], KnowledgeSyncPolicyData] = {}
        self.runs: dict[tuple[str, str], KnowledgeSyncRunData] = {}
        self.policy_idempotency: dict[tuple[str, str, str], str] = {}
        self.run_idempotency: dict[tuple[str, str, str], str] = {}

    def create_policy(
        self,
        tenant_id: str,
        project_id: str,
        source: knowledge_routes.KnowledgeSourceData,
        payload: KnowledgeSyncPolicyCreateRequest,
    ) -> KnowledgeSyncPolicyData:
        replay_key = (tenant_id, project_id, payload.idempotency_key)
        if replay_key in self.policy_idempotency:
            existing = self.policies[(tenant_id, self.policy_idempotency[replay_key])]
            return existing.model_copy(update={"idempotent_replay": True})
        self._validate_source(source)
        if any(
            item.project_id == project_id and item.anchor_source_id == source.source_id
            for (item_tenant, _), item in self.policies.items()
            if item_tenant == tenant_id
        ):
            raise StarletteHTTPException(
                status_code=409,
                detail={"code": "KNOWLEDGE_SYNC_POLICY_EXISTS", "details": {"source_id": source.source_id}},
            )
        created_at = utc_now()
        policy_id = f"ksync_policy_{uuid4().hex[:16]}"
        data = KnowledgeSyncPolicyData(
            policy_id=policy_id,
            tenant_id=tenant_id,
            project_id=project_id,
            anchor_source_id=source.source_id,
            current_source_id=source.source_id,
            source_uri=source.source_uri or "",
            interval_hours=payload.interval_hours,
            enabled=True,
            version=1,
            next_run_at=created_at + timedelta(hours=payload.interval_hours),
            created_by=payload.created_by,
            updated_by=payload.created_by,
            created_at=created_at,
            updated_at=created_at,
        )
        self.policies[(tenant_id, policy_id)] = data
        self.policy_idempotency[replay_key] = policy_id
        self._create_run(data, f"initial:{payload.idempotency_key}", created_at)
        return data

    @staticmethod
    def _validate_source(source: knowledge_routes.KnowledgeSourceData) -> None:
        parsed = urlparse(source.source_uri or "")
        if source.status != "active" or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise StarletteHTTPException(
                status_code=409,
                detail={"code": "KNOWLEDGE_SYNC_SOURCE_NOT_ELIGIBLE", "details": {"source_id": source.source_id}},
            )

    def list_policies(self, tenant_id: str, project_id: str) -> list[KnowledgeSyncPolicyData]:
        return sorted(
            [
                item
                for (item_tenant, _), item in self.policies.items()
                if item_tenant == tenant_id and item.project_id == project_id
            ],
            key=lambda item: item.created_at,
            reverse=True,
        )

    def update_policy(
        self,
        tenant_id: str,
        policy_id: str,
        payload: KnowledgeSyncPolicyUpdateRequest,
    ) -> KnowledgeSyncPolicyData:
        current = self.policies.get((tenant_id, policy_id))
        if current is None:
            raise _policy_not_found(policy_id)
        if current.version != payload.expected_version:
            raise _version_conflict(policy_id, current.version)
        now = utc_now()
        updated = current.model_copy(
            update={
                "enabled": payload.enabled,
                "interval_hours": payload.interval_hours,
                "version": current.version + 1,
                "next_run_at": now if payload.enabled and not current.enabled else current.next_run_at,
                "updated_by": payload.updated_by,
                "updated_at": now,
                "idempotent_replay": False,
            }
        )
        self.policies[(tenant_id, policy_id)] = updated
        return updated

    def trigger(
        self,
        tenant_id: str,
        policy_id: str,
        payload: KnowledgeSyncTriggerRequest,
    ) -> KnowledgeSyncRunData:
        policy = self.policies.get((tenant_id, policy_id))
        if policy is None:
            raise _policy_not_found(policy_id)
        if not policy.enabled:
            raise StarletteHTTPException(status_code=409, detail={"code": "KNOWLEDGE_SYNC_POLICY_DISABLED"})
        replay_key = (tenant_id, policy_id, payload.idempotency_key)
        if replay_key in self.run_idempotency:
            return self.runs[(tenant_id, self.run_idempotency[replay_key])].model_copy(update={"idempotent_replay": True})
        active = next(
            (
                item
                for (item_tenant, _), item in self.runs.items()
                if item_tenant == tenant_id and item.policy_id == policy_id and item.status in {"queued", "running"}
            ),
            None,
        )
        if active is not None:
            raise StarletteHTTPException(
                status_code=409,
                detail={
                    "code": "KNOWLEDGE_SYNC_ALREADY_ACTIVE",
                    "details": {"run_id": active.run_id, "status": active.status},
                },
            )
        return self._create_run(policy, payload.idempotency_key, utc_now())

    def _create_run(
        self, policy: KnowledgeSyncPolicyData, idempotency_key: str, scheduled_at: datetime
    ) -> KnowledgeSyncRunData:
        run_id = f"ksync_run_{uuid4().hex[:16]}"
        job_id = f"job_ksync_{uuid4().hex[:16]}"
        row = KnowledgeSyncRunData(
            run_id=run_id,
            tenant_id=policy.tenant_id,
            project_id=policy.project_id,
            policy_id=policy.policy_id,
            source_before_id=policy.current_source_id,
            job_id=job_id,
            status="queued",
            requested_url=policy.source_uri,
            scheduled_at=scheduled_at,
            created_at=scheduled_at,
        )
        self.runs[(policy.tenant_id, run_id)] = row
        self.run_idempotency[(policy.tenant_id, policy.policy_id, idempotency_key)] = run_id
        return row

    def list_runs(
        self, tenant_id: str, project_id: str, *, policy_id: Optional[str], limit: int
    ) -> list[KnowledgeSyncRunData]:
        rows = [
            item
            for (item_tenant, _), item in self.runs.items()
            if item_tenant == tenant_id
            and item.project_id == project_id
            and (policy_id is None or item.policy_id == policy_id)
        ]
        return sorted(rows, key=lambda item: item.created_at, reverse=True)[:limit]


class MySQLKnowledgeSyncRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _policy(row: Mapping[str, Any], *, replay: bool = False) -> KnowledgeSyncPolicyData:
        return KnowledgeSyncPolicyData(
            policy_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            anchor_source_id=str(row["anchor_source_id"]),
            current_source_id=str(row["current_source_id"]),
            source_uri=str(row["source_uri"]),
            interval_hours=int(row["interval_hours"]),
            enabled=bool(row["enabled"]),
            version=int(row["version"]),
            next_run_at=_as_utc(row["next_run_at"]),
            last_run_id=str(row["last_run_id"]) if row["last_run_id"] else None,
            last_status=str(row["last_status"]) if row["last_status"] else None,  # type: ignore[arg-type]
            last_checked_at=_optional_utc(row["last_checked_at"]),
            created_by=str(row["created_by"]),
            updated_by=str(row["updated_by"]),
            created_at=_as_utc(row["created_at"]),
            updated_at=_as_utc(row["updated_at"]),
            idempotent_replay=replay,
        )

    @staticmethod
    def _run(row: Mapping[str, Any], *, replay: bool = False) -> KnowledgeSyncRunData:
        return KnowledgeSyncRunData(
            run_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            policy_id=str(row["policy_id"]),
            source_before_id=str(row["source_before_id"]),
            source_after_id=str(row["source_after_id"]) if row["source_after_id"] else None,
            job_id=str(row["job_id"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            requested_url=str(row["requested_url"]),
            final_url=str(row["final_url"]) if row["final_url"] else None,
            evidence_grade=str(row["evidence_grade"]) if row["evidence_grade"] else None,
            response_status=int(row["response_status"]) if row["response_status"] is not None else None,
            content_type=str(row["content_type"]) if row["content_type"] else None,
            response_bytes=int(row["response_bytes"]) if row["response_bytes"] is not None else None,
            raw_content_sha256=str(row["raw_content_sha256"]) if row["raw_content_sha256"] else None,
            visible_text_sha256=str(row["visible_text_sha256"]) if row["visible_text_sha256"] else None,
            raw_object_ref_id=str(row["raw_object_ref_id"]) if row["raw_object_ref_id"] else None,
            text_object_ref_id=str(row["text_object_ref_id"]) if row["text_object_ref_id"] else None,
            connected_ip=str(row["connected_ip"]) if row["connected_ip"] else None,
            redirect_count=int(row["redirect_count"]) if row["redirect_count"] is not None else None,
            error_code=str(row["error_code"]) if row["error_code"] else None,
            error_message=str(row["error_message"]) if row["error_message"] else None,
            scheduled_at=_as_utc(row["scheduled_at"]),
            started_at=_optional_utc(row["started_at"]),
            completed_at=_optional_utc(row["completed_at"]),
            created_at=_as_utc(row["created_at"]),
            idempotent_replay=replay,
        )

    def create_policy(
        self,
        tenant_id: str,
        project_id: str,
        source: knowledge_routes.KnowledgeSourceData,
        payload: KnowledgeSyncPolicyCreateRequest,
    ) -> KnowledgeSyncPolicyData:
        InMemoryKnowledgeSyncRepository._validate_source(source)
        now = utc_now()
        with self.engine.begin() as conn:
            replay = conn.execute(
                text(
                    """
                    SELECT * FROM airank_knowledge_sync_policies
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND idempotency_key=:idempotency_key
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "idempotency_key": payload.idempotency_key},
            ).mappings().first()
            if replay is not None:
                return self._policy(replay, replay=True)
            source_row = conn.execute(
                text(
                    """
                    SELECT id, source_uri, status FROM airank_knowledge_sources
                    WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:source_id
                    FOR UPDATE
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "source_id": source.source_id},
            ).mappings().first()
            if source_row is None:
                raise StarletteHTTPException(status_code=404, detail={"code": "KNOWLEDGE_SOURCE_NOT_FOUND"})
            if str(source_row["status"]) != "active" or not str(source_row["source_uri"] or ""):
                raise StarletteHTTPException(status_code=409, detail={"code": "KNOWLEDGE_SYNC_SOURCE_NOT_ELIGIBLE"})
            duplicate = conn.execute(
                text(
                    """
                    SELECT id FROM airank_knowledge_sync_policies
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND anchor_source_id=:source_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "source_id": source.source_id},
            ).scalar_one_or_none()
            if duplicate:
                raise StarletteHTTPException(
                    status_code=409,
                    detail={"code": "KNOWLEDGE_SYNC_POLICY_EXISTS", "details": {"policy_id": duplicate}},
                )
            policy_id = f"ksync_policy_{uuid4().hex[:16]}"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_knowledge_sync_policies (
                      id, tenant_id, project_id, anchor_source_id, current_source_id,
                      source_uri, idempotency_key, interval_hours, enabled, version,
                      next_run_at, created_by, updated_by, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :source_id, :source_id,
                      :source_uri, :idempotency_key, :interval_hours, 1, 1,
                      :next_run_at, :actor, :actor, :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": policy_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_id": source.source_id,
                    "source_uri": str(source_row["source_uri"]),
                    "idempotency_key": payload.idempotency_key,
                    "interval_hours": payload.interval_hours,
                    "next_run_at": now + timedelta(hours=payload.interval_hours),
                    "actor": payload.created_by,
                    "created_at": now,
                },
            )
            self._enqueue(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                policy_id=policy_id,
                source_id=source.source_id,
                source_uri=str(source_row["source_uri"]),
                idempotency_key=f"initial:{payload.idempotency_key}",
                requested_by=payload.created_by,
                scheduled_at=now,
            )
            _audit(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                actor=payload.created_by,
                event_type="knowledge.sync.policy_created",
                entity_type="knowledge_sync_policy",
                entity_id=policy_id,
                payload={
                    "anchor_source_id": source.source_id,
                    "interval_hours": payload.interval_hours,
                    "source_uri": str(source_row["source_uri"]),
                },
                created_at=now,
            )
            row = conn.execute(
                text("SELECT * FROM airank_knowledge_sync_policies WHERE id=:id"), {"id": policy_id}
            ).mappings().one()
        return self._policy(row)

    def list_policies(self, tenant_id: str, project_id: str) -> list[KnowledgeSyncPolicyData]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_knowledge_sync_policies
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                    ORDER BY created_at DESC, id DESC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        return [self._policy(row) for row in rows]

    def update_policy(
        self,
        tenant_id: str,
        policy_id: str,
        payload: KnowledgeSyncPolicyUpdateRequest,
    ) -> KnowledgeSyncPolicyData:
        now = utc_now()
        with self.engine.begin() as conn:
            current = conn.execute(
                text(
                    "SELECT * FROM airank_knowledge_sync_policies WHERE tenant_id=:tenant_id AND id=:policy_id FOR UPDATE"
                ),
                {"tenant_id": tenant_id, "policy_id": policy_id},
            ).mappings().first()
            if current is None:
                raise _policy_not_found(policy_id)
            if int(current["version"]) != payload.expected_version:
                raise _version_conflict(policy_id, int(current["version"]))
            next_run_at = now if payload.enabled and not bool(current["enabled"]) else current["next_run_at"]
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_policies
                    SET enabled=:enabled, interval_hours=:interval_hours,
                        version=version+1, next_run_at=:next_run_at,
                        updated_by=:updated_by, updated_at=:updated_at
                    WHERE tenant_id=:tenant_id AND id=:policy_id AND version=:expected_version
                    """
                ),
                {
                    "enabled": 1 if payload.enabled else 0,
                    "interval_hours": payload.interval_hours,
                    "next_run_at": next_run_at,
                    "updated_by": payload.updated_by,
                    "updated_at": now,
                    "tenant_id": tenant_id,
                    "policy_id": policy_id,
                    "expected_version": payload.expected_version,
                },
            )
            _audit(
                conn,
                tenant_id=tenant_id,
                project_id=str(current["project_id"]),
                actor=payload.updated_by,
                event_type="knowledge.sync.policy_updated",
                entity_type="knowledge_sync_policy",
                entity_id=policy_id,
                payload={
                    "expected_version": payload.expected_version,
                    "enabled": payload.enabled,
                    "interval_hours": payload.interval_hours,
                    "reason": payload.reason,
                },
                created_at=now,
            )
            row = conn.execute(text("SELECT * FROM airank_knowledge_sync_policies WHERE id=:id"), {"id": policy_id}).mappings().one()
        return self._policy(row)

    def trigger(
        self,
        tenant_id: str,
        policy_id: str,
        payload: KnowledgeSyncTriggerRequest,
    ) -> KnowledgeSyncRunData:
        now = utc_now()
        with self.engine.begin() as conn:
            replay = conn.execute(
                text(
                    """
                    SELECT * FROM airank_knowledge_sync_runs
                    WHERE tenant_id=:tenant_id
                      AND policy_id=:policy_id
                      AND idempotency_key=:idempotency_key
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "policy_id": policy_id,
                    "idempotency_key": payload.idempotency_key,
                },
            ).mappings().first()
            if replay is not None:
                return self._run(replay, replay=True)
            policy = conn.execute(
                text(
                    "SELECT * FROM airank_knowledge_sync_policies WHERE tenant_id=:tenant_id AND id=:policy_id FOR UPDATE"
                ),
                {"tenant_id": tenant_id, "policy_id": policy_id},
            ).mappings().first()
            if policy is None:
                raise _policy_not_found(policy_id)
            if not bool(policy["enabled"]):
                raise StarletteHTTPException(status_code=409, detail={"code": "KNOWLEDGE_SYNC_POLICY_DISABLED"})
            active = conn.execute(
                text(
                    """
                    SELECT * FROM airank_knowledge_sync_runs
                    WHERE tenant_id=:tenant_id AND policy_id=:policy_id
                      AND status IN ('queued','running')
                    ORDER BY scheduled_at DESC LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "policy_id": policy_id},
            ).mappings().first()
            if active is not None:
                raise StarletteHTTPException(
                    status_code=409,
                    detail={
                        "code": "KNOWLEDGE_SYNC_ALREADY_ACTIVE",
                        "details": {"run_id": str(active["id"]), "status": str(active["status"])},
                    },
                )
            run_id = self._enqueue(
                conn,
                tenant_id=tenant_id,
                project_id=str(policy["project_id"]),
                policy_id=policy_id,
                source_id=str(policy["current_source_id"]),
                source_uri=str(policy["source_uri"]),
                idempotency_key=payload.idempotency_key,
                requested_by=payload.requested_by,
                scheduled_at=now,
            )
            _audit(
                conn,
                tenant_id=tenant_id,
                project_id=str(policy["project_id"]),
                actor=payload.requested_by,
                event_type="knowledge.sync.manually_triggered",
                entity_type="knowledge_sync_run",
                entity_id=run_id,
                payload={"policy_id": policy_id, "source_before_id": str(policy["current_source_id"])},
                created_at=now,
            )
            row = conn.execute(text("SELECT * FROM airank_knowledge_sync_runs WHERE id=:id"), {"id": run_id}).mappings().one()
        return self._run(row)

    @staticmethod
    def _enqueue(
        conn: Any,
        *,
        tenant_id: str,
        project_id: str,
        policy_id: str,
        source_id: str,
        source_uri: str,
        idempotency_key: str,
        requested_by: str,
        scheduled_at: datetime,
    ) -> str:
        run_id = f"ksync_run_{uuid4().hex[:16]}"
        job_id = f"job_ksync_{uuid4().hex[:16]}"
        job_payload = {
            "contract_version": SYNC_CONTRACT_VERSION,
            "sync_run_id": run_id,
            "policy_id": policy_id,
            "source_before_id": source_id,
            "requested_by": requested_by,
        }
        conn.execute(
            text(
                """
                INSERT INTO airank_async_jobs (
                  id, tenant_id, project_id, job_type, status, priority,
                  scheduled_at, timeout_seconds, attempt_count, max_attempts,
                  payload_json, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, 'knowledge.source.sync', 'queued', 60,
                  :scheduled_at, 120, 0, 3, :payload_json, :scheduled_at, :scheduled_at
                )
                """
            ),
            {
                "id": job_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "scheduled_at": scheduled_at,
                "payload_json": json.dumps(job_payload, ensure_ascii=False, sort_keys=True),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_knowledge_sync_runs (
                  id, tenant_id, project_id, policy_id, source_before_id,
                  job_id, idempotency_key, status, requested_url,
                  scheduled_at, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :policy_id, :source_before_id,
                  :job_id, :idempotency_key, 'queued', :requested_url,
                  :scheduled_at, :scheduled_at, :scheduled_at
                )
                """
            ),
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "policy_id": policy_id,
                "source_before_id": source_id,
                "job_id": job_id,
                "idempotency_key": idempotency_key,
                "requested_url": source_uri,
                "scheduled_at": scheduled_at,
            },
        )
        return run_id

    def list_runs(
        self, tenant_id: str, project_id: str, *, policy_id: Optional[str], limit: int
    ) -> list[KnowledgeSyncRunData]:
        clauses = ["tenant_id=:tenant_id", "project_id=:project_id"]
        params: dict[str, Any] = {"tenant_id": tenant_id, "project_id": project_id, "limit": limit}
        if policy_id:
            clauses.append("policy_id=:policy_id")
            params["policy_id"] = policy_id
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT * FROM airank_knowledge_sync_runs
                    WHERE {' AND '.join(clauses)}
                    ORDER BY scheduled_at DESC, id DESC LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [self._run(row) for row in rows]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _optional_utc(value: Optional[datetime]) -> Optional[datetime]:
    return _as_utc(value) if value is not None else None


def _policy_not_found(policy_id: str) -> StarletteHTTPException:
    return StarletteHTTPException(
        status_code=404,
        detail={"code": "KNOWLEDGE_SYNC_POLICY_NOT_FOUND", "details": {"policy_id": policy_id}},
    )


def _version_conflict(policy_id: str, current_version: int) -> StarletteHTTPException:
    return StarletteHTTPException(
        status_code=409,
        detail={
            "code": "KNOWLEDGE_SYNC_VERSION_CONFLICT",
            "details": {"policy_id": policy_id, "current_version": current_version},
        },
    )


def _audit(
    conn: Any,
    *,
    tenant_id: str,
    project_id: str,
    actor: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: Mapping[str, Any],
    created_at: datetime,
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
            "id": f"audit_{uuid4().hex[:16]}",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "actor": actor,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload_json": json.dumps(dict(payload), ensure_ascii=False, sort_keys=True),
            "created_at": created_at,
        },
    )


def build_repository() -> KnowledgeSyncRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLKnowledgeSyncRepository(database_url) if database_url else InMemoryKnowledgeSyncRepository()


KNOWLEDGE_SYNC_REPOSITORY: KnowledgeSyncRepository = build_repository()


def _active_source(tenant_id: str, project_id: str, source_id: str) -> knowledge_routes.KnowledgeSourceData:
    source = next(
        (
            item
            for item in knowledge_routes.KNOWLEDGE_REPOSITORY.list_sources(tenant_id, project_id)
            if item.source_id == source_id
        ),
        None,
    )
    if source is None:
        raise StarletteHTTPException(
            status_code=404,
            detail={"code": "KNOWLEDGE_SOURCE_NOT_FOUND", "details": {"source_id": source_id}},
        )
    return source


@router.post(
    "/projects/{project_id}/knowledge-sources/{source_id}/sync-policies",
    response_model=KnowledgeSyncPolicyResponse,
    status_code=201,
)
def create_sync_policy(
    project_id: str,
    source_id: str,
    payload: KnowledgeSyncPolicyCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> KnowledgeSyncPolicyResponse:
    trusted = payload.model_copy(update={"created_by": trusted_actor(payload.created_by, authenticated_actor)})
    source = _active_source(tenant_id, project_id, source_id)
    return KnowledgeSyncPolicyResponse(
        data=KNOWLEDGE_SYNC_REPOSITORY.create_policy(tenant_id, project_id, source, trusted),
        meta=response_meta(trace_id),
    )


@router.get(
    "/projects/{project_id}/knowledge-source-sync-policies",
    response_model=KnowledgeSyncPolicyListResponse,
)
def list_sync_policies(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> KnowledgeSyncPolicyListResponse:
    return KnowledgeSyncPolicyListResponse(
        data=KNOWLEDGE_SYNC_REPOSITORY.list_policies(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.patch(
    "/knowledge-source-sync-policies/{policy_id}",
    response_model=KnowledgeSyncPolicyResponse,
)
def update_sync_policy(
    policy_id: str,
    payload: KnowledgeSyncPolicyUpdateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> KnowledgeSyncPolicyResponse:
    trusted = payload.model_copy(update={"updated_by": trusted_actor(payload.updated_by, authenticated_actor)})
    return KnowledgeSyncPolicyResponse(
        data=KNOWLEDGE_SYNC_REPOSITORY.update_policy(tenant_id, policy_id, trusted),
        meta=response_meta(trace_id),
    )


@router.post(
    "/knowledge-source-sync-policies/{policy_id}/runs",
    response_model=KnowledgeSyncRunResponse,
    status_code=201,
)
def trigger_sync_run(
    policy_id: str,
    payload: KnowledgeSyncTriggerRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> KnowledgeSyncRunResponse:
    trusted = payload.model_copy(update={"requested_by": trusted_actor(payload.requested_by, authenticated_actor)})
    return KnowledgeSyncRunResponse(
        data=KNOWLEDGE_SYNC_REPOSITORY.trigger(tenant_id, policy_id, trusted),
        meta=response_meta(trace_id),
    )


@router.get(
    "/projects/{project_id}/knowledge-source-sync-runs",
    response_model=KnowledgeSyncRunListResponse,
)
def list_sync_runs(
    project_id: str,
    policy_id: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> KnowledgeSyncRunListResponse:
    return KnowledgeSyncRunListResponse(
        data=KNOWLEDGE_SYNC_REPOSITORY.list_runs(
            tenant_id, project_id, policy_id=policy_id, limit=limit
        ),
        meta=response_meta(trace_id),
    )

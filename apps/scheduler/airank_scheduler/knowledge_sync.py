from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json

from sqlalchemy import create_engine, text


SYNC_CONTRACT_VERSION = "airank.knowledge-source-sync.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


@dataclass(frozen=True)
class KnowledgeSyncQueuePreview:
    due_policy_count: int
    next_policy_id: str | None

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeSyncDispatchRecord:
    policy_id: str
    run_id: str
    job_id: str
    source_before_id: str
    scheduled_at: datetime

    def to_record(self) -> dict[str, object]:
        return asdict(self)


class MySQLKnowledgeSyncScheduler:
    """Turns due, customer-authorized source policies into durable sync jobs."""

    def __init__(
        self,
        database_url: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        scheduler_id: str = "airank-knowledge-sync-scheduler",
    ) -> None:
        if project_id and not tenant_id:
            raise ValueError("project scope requires tenant scope")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.scheduler_id = scheduler_id

    def preview(self, now: datetime | None = None) -> KnowledgeSyncQueuePreview:
        checked_at = now or utc_now()
        scope_sql, params = self._scope_sql("p")
        params["now"] = checked_at
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT p.id
                    FROM airank_knowledge_sync_policies p
                    WHERE p.enabled=1 AND p.next_run_at<=:now {scope_sql}
                      AND NOT EXISTS (
                        SELECT 1 FROM airank_knowledge_sync_runs r
                        WHERE r.tenant_id=p.tenant_id AND r.policy_id=p.id
                          AND r.status IN ('queued','running')
                      )
                    ORDER BY p.next_run_at, p.id
                    """
                ),
                params,
            ).all()
        return KnowledgeSyncQueuePreview(
            due_policy_count=len(rows),
            next_policy_id=str(rows[0][0]) if rows else None,
        )

    def dispatch_due(
        self, *, now: datetime | None = None, limit: int = 10
    ) -> list[KnowledgeSyncDispatchRecord]:
        if limit < 1:
            raise ValueError("dispatch limit must be positive")
        dispatched_at = now or utc_now()
        records: list[KnowledgeSyncDispatchRecord] = []
        for _ in range(limit):
            record = self._dispatch_one(dispatched_at)
            if record is None:
                break
            records.append(record)
        return records

    def _dispatch_one(self, dispatched_at: datetime) -> KnowledgeSyncDispatchRecord | None:
        scope_sql, params = self._scope_sql("p")
        params["now"] = dispatched_at
        lock_sql = " FOR UPDATE SKIP LOCKED" if self.engine.dialect.name == "mysql" else ""
        with self.engine.begin() as conn:
            policy = conn.execute(
                text(
                    f"""
                    SELECT p.*
                    FROM airank_knowledge_sync_policies p
                    WHERE p.enabled=1 AND p.next_run_at<=:now {scope_sql}
                      AND NOT EXISTS (
                        SELECT 1 FROM airank_knowledge_sync_runs r
                        WHERE r.tenant_id=p.tenant_id AND r.policy_id=p.id
                          AND r.status IN ('queued','running')
                      )
                    ORDER BY p.next_run_at, p.id
                    LIMIT 1{lock_sql}
                    """
                ),
                params,
            ).mappings().first()
            if policy is None:
                return None
            policy_id = str(policy["id"])
            tenant_id = str(policy["tenant_id"])
            project_id = str(policy["project_id"])
            source_id = str(policy["current_source_id"])
            due_at = policy["next_run_at"]
            due_marker = due_at.isoformat() if isinstance(due_at, datetime) else str(due_at)
            run_id = _stable_id("ksync_run", tenant_id, policy_id, due_marker)
            job_id = _stable_id("job_ksync", tenant_id, policy_id, due_marker)
            idempotency_key = f"scheduled:{policy_id}:{due_marker}"
            job_payload = {
                "contract_version": SYNC_CONTRACT_VERSION,
                "sync_run_id": run_id,
                "policy_id": policy_id,
                "source_before_id": source_id,
                "requested_by": self.scheduler_id,
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
                    "scheduled_at": dispatched_at,
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
                    "requested_url": str(policy["source_uri"]),
                    "scheduled_at": dispatched_at,
                },
            )
            next_run_at = dispatched_at + timedelta(hours=int(policy["interval_hours"]))
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_policies
                    SET next_run_at=:next_run_at, updated_by=:updated_by,
                        updated_at=:updated_at
                    WHERE tenant_id=:tenant_id AND id=:policy_id AND enabled=1
                    """
                ),
                {
                    "next_run_at": next_run_at,
                    "updated_by": self.scheduler_id,
                    "updated_at": dispatched_at,
                    "tenant_id": tenant_id,
                    "policy_id": policy_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, actor_user_id, event_type,
                      entity_type, entity_id, payload_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :actor, 'knowledge.sync.dispatched',
                      'knowledge_sync_run', :entity_id, :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": _stable_id("audit_ksync", tenant_id, run_id),
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "actor": self.scheduler_id,
                    "entity_id": run_id,
                    "payload_json": json.dumps(
                        {
                            "contract_version": SYNC_CONTRACT_VERSION,
                            "policy_id": policy_id,
                            "source_before_id": source_id,
                            "job_id": job_id,
                            "next_run_at": next_run_at.isoformat(),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "created_at": dispatched_at,
                },
            )
        return KnowledgeSyncDispatchRecord(
            policy_id=policy_id,
            run_id=run_id,
            job_id=job_id,
            source_before_id=source_id,
            scheduled_at=dispatched_at,
        )

    def _scope_sql(self, alias: str) -> tuple[str, dict[str, object]]:
        clauses: list[str] = []
        params: dict[str, object] = {}
        if self.tenant_id:
            clauses.append(f"{alias}.tenant_id=:tenant_id")
            params["tenant_id"] = self.tenant_id
        if self.project_id:
            clauses.append(f"{alias}.project_id=:project_id")
            params["project_id"] = self.project_id
        return (" AND " + " AND ".join(clauses) if clauses else ""), params

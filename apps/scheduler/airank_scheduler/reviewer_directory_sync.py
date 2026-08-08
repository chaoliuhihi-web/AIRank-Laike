from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json

from sqlalchemy import create_engine, text


SYNC_CONTRACT_VERSION = "airank.reviewer-directory-sync.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


@dataclass(frozen=True)
class ReviewerDirectorySyncQueuePreview:
    due_binding_count: int
    next_binding_id: str | None

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewerDirectorySyncDispatchRecord:
    binding_id: str
    team_id: str
    reviewer_role: str
    job_id: str
    scheduled_at: datetime

    def to_record(self) -> dict[str, object]:
        return asdict(self)


class MySQLReviewerDirectorySyncScheduler:
    """Queues due Yudao reviewer-directory bindings without storing credentials."""

    def __init__(
        self,
        database_url: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        scheduler_id: str = "airank-reviewer-directory-sync-scheduler",
    ) -> None:
        if project_id and not tenant_id:
            raise ValueError("project scope requires tenant scope")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.scheduler_id = scheduler_id

    def preview(
        self, now: datetime | None = None
    ) -> ReviewerDirectorySyncQueuePreview:
        checked_at = now or utc_now()
        scope_sql, params = self._scope_sql("binding")
        params["now"] = checked_at
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT binding.id
                    FROM airank_evidence_review_team_sync_bindings binding
                    WHERE binding.status='active' AND binding.sync_enabled=1
                      AND binding.next_sync_at<=:now {scope_sql}
                    ORDER BY binding.next_sync_at, binding.id
                    """
                ),
                params,
            ).all()
        return ReviewerDirectorySyncQueuePreview(
            due_binding_count=len(rows),
            next_binding_id=str(rows[0][0]) if rows else None,
        )

    def dispatch_due(
        self, *, now: datetime | None = None, limit: int = 10
    ) -> list[ReviewerDirectorySyncDispatchRecord]:
        if limit < 1:
            raise ValueError("dispatch limit must be positive")
        dispatched_at = now or utc_now()
        records: list[ReviewerDirectorySyncDispatchRecord] = []
        for _ in range(limit):
            record = self._dispatch_one(dispatched_at)
            if record is None:
                break
            records.append(record)
        return records

    def _dispatch_one(
        self, dispatched_at: datetime
    ) -> ReviewerDirectorySyncDispatchRecord | None:
        scope_sql, params = self._scope_sql("binding")
        params["now"] = dispatched_at
        lock_sql = " FOR UPDATE SKIP LOCKED" if self.engine.dialect.name == "mysql" else ""
        with self.engine.begin() as conn:
            binding = conn.execute(
                text(
                    f"""
                    SELECT binding.*
                    FROM airank_evidence_review_team_sync_bindings binding
                    WHERE binding.status='active' AND binding.sync_enabled=1
                      AND binding.next_sync_at<=:now {scope_sql}
                    ORDER BY binding.next_sync_at, binding.id
                    LIMIT 1{lock_sql}
                    """
                ),
                params,
            ).mappings().first()
            if binding is None:
                return None
            tenant_id = str(binding["tenant_id"])
            project_id = str(binding["project_id"])
            binding_id = str(binding["id"])
            team_id = str(binding["team_id"])
            reviewer_role = str(binding["reviewer_role"])
            due_at = binding["next_sync_at"]
            due_marker = due_at.isoformat() if isinstance(due_at, datetime) else str(due_at)
            job_id = _stable_id("job_rdir", tenant_id, binding_id, due_marker)
            idempotency_key = f"scheduled:{binding_id}:{due_marker}"
            payload = {
                "contract_version": SYNC_CONTRACT_VERSION,
                "binding_id": binding_id,
                "binding_version": int(binding["version"]),
                "team_id": team_id,
                "reviewer_role": reviewer_role,
                "external_group_id": str(binding["external_group_id"]),
                "idempotency_key": idempotency_key,
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
                      :id, :tenant_id, :project_id,
                      'reviewer.directory.sync', 'queued', 45,
                      :scheduled_at, 120, 0, 1, :payload_json,
                      :scheduled_at, :scheduled_at
                    )
                    """
                ),
                {
                    "id": job_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "scheduled_at": dispatched_at,
                    "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                },
            )
            next_sync_at = dispatched_at + timedelta(
                minutes=int(binding["sync_interval_minutes"])
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_evidence_review_team_sync_bindings
                    SET next_sync_at=:next_sync_at, updated_by=:actor,
                        updated_at=:updated_at
                    WHERE tenant_id=:tenant_id AND id=:binding_id
                      AND status='active' AND sync_enabled=1
                    """
                ),
                {
                    "next_sync_at": next_sync_at,
                    "actor": self.scheduler_id,
                    "updated_at": dispatched_at,
                    "tenant_id": tenant_id,
                    "binding_id": binding_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, actor_user_id, event_type,
                      entity_type, entity_id, payload_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :actor,
                      'evidence_review.yudao_sync_dispatched',
                      'evidence_review_team_sync_binding', :entity_id,
                      :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": _stable_id("audit_rdir", tenant_id, job_id),
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "actor": self.scheduler_id,
                    "entity_id": binding_id,
                    "payload_json": json.dumps(
                        {
                            "contract_version": SYNC_CONTRACT_VERSION,
                            "job_id": job_id,
                            "team_id": team_id,
                            "reviewer_role": reviewer_role,
                            "binding_version": int(binding["version"]),
                            "next_sync_at": next_sync_at.isoformat(),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "created_at": dispatched_at,
                },
            )
        return ReviewerDirectorySyncDispatchRecord(
            binding_id=binding_id,
            team_id=team_id,
            reviewer_role=reviewer_role,
            job_id=job_id,
            scheduled_at=dispatched_at,
        )

    def _scope_sql(self, alias: str) -> tuple[str, dict[str, object]]:
        clauses: list[str] = []
        params: dict[str, object] = {}
        if self.tenant_id:
            clauses.append(f"{alias}.tenant_id=:scope_tenant_id")
            params["scope_tenant_id"] = self.tenant_id
        if self.project_id:
            clauses.append(f"{alias}.project_id=:scope_project_id")
            params["scope_project_id"] = self.project_id
        return (" AND " + " AND ".join(clauses) if clauses else "", params)

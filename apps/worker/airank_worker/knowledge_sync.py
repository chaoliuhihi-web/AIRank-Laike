from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Mapping, Protocol
from uuid import uuid4

from sqlalchemy import create_engine, text

from airank_crawler_lite import CitationSourceCaptureResult, CitationSourceCaptureService
from airank_domain import AsyncJob, segment_source_text
from airank_evidence import ObjectStorage, ObjectStorageError, StoredObject
from airank_outbound_security import OutboundSecurityError

from .lease import InMemoryJobLeaseStore, MySQLJobLeaseStore


SYNC_CONTRACT_VERSION = "airank.knowledge-source-sync.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeSyncWorkerError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class KnowledgeSyncExecutionSnapshot:
    tenant_id: str
    project_id: str
    run_id: str
    policy_id: str
    job_id: str
    source_before_id: str
    requested_url: str
    run_status: str
    policy_enabled: bool
    source_type: str
    source_title: str
    source_uri: str
    source_status: str
    source_revision_number: int
    source_content_sha256: str
    authority_level: str
    risk_level: str
    valid_from: datetime | None
    valid_until: datetime | None


@dataclass(frozen=True)
class KnowledgeSyncOutcome:
    run_id: str
    policy_id: str
    status: str
    source_before_id: str
    source_after_id: str
    raw_content_sha256: str
    visible_text_sha256: str
    raw_object_ref_id: str
    text_object_ref_id: str
    idempotent_replay: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "policy_id": self.policy_id,
            "status": self.status,
            "source_before_id": self.source_before_id,
            "source_after_id": self.source_after_id,
            "raw_content_sha256": self.raw_content_sha256,
            "visible_text_sha256": self.visible_text_sha256,
            "raw_object_ref_id": self.raw_object_ref_id,
            "text_object_ref_id": self.text_object_ref_id,
            "idempotent_replay": self.idempotent_replay,
        }


class KnowledgeSyncExecutionRepository(Protocol):
    def load(self, tenant_id: str, run_id: str, job_id: str) -> KnowledgeSyncExecutionSnapshot: ...

    def begin(self, snapshot: KnowledgeSyncExecutionSnapshot, started_at: datetime) -> None: ...

    def complete(
        self,
        snapshot: KnowledgeSyncExecutionSnapshot,
        result: CitationSourceCaptureResult,
        raw_object: StoredObject,
        text_object: StoredObject,
        completed_at: datetime,
    ) -> KnowledgeSyncOutcome: ...

    def fail(
        self,
        snapshot: KnowledgeSyncExecutionSnapshot,
        error: KnowledgeSyncWorkerError,
        completed_at: datetime,
        *,
        status: str,
    ) -> None: ...

    def schedule_retry(
        self,
        snapshot: KnowledgeSyncExecutionSnapshot,
        error: KnowledgeSyncWorkerError,
        recorded_at: datetime,
        retry_at: datetime,
    ) -> None: ...


class MySQLKnowledgeSyncExecutionRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def load(self, tenant_id: str, run_id: str, job_id: str) -> KnowledgeSyncExecutionSnapshot:
        with self.engine.begin() as conn:
            row = self._load_row(conn, tenant_id, run_id, job_id, lock=True)
            if row is None:
                raise KnowledgeSyncWorkerError(
                    "KNOWLEDGE_SYNC_RUN_NOT_FOUND", "knowledge source sync run was not found"
                )
            if str(row["source_status"]) != "active":
                replacement = conn.execute(
                    text(
                        """
                        SELECT id
                        FROM airank_knowledge_sources
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND source_uri=:source_uri AND status='active'
                        ORDER BY revision_number DESC, captured_at DESC, id DESC
                        LIMIT 1 FOR UPDATE
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": str(row["project_id"]),
                        "source_uri": str(row["policy_source_uri"]),
                    },
                ).scalar_one_or_none()
                if replacement is None:
                    raise KnowledgeSyncWorkerError(
                        "KNOWLEDGE_SYNC_SOURCE_STALE",
                        "sync policy no longer points to an active source revision",
                    )
                conn.execute(
                    text(
                        """
                        UPDATE airank_knowledge_sync_policies
                        SET current_source_id=:source_id, version=version+1,
                            updated_by='knowledge-sync-worker', updated_at=:updated_at
                        WHERE tenant_id=:tenant_id AND id=:policy_id
                        """
                    ),
                    {
                        "source_id": replacement,
                        "updated_at": utc_now(),
                        "tenant_id": tenant_id,
                        "policy_id": str(row["policy_id"]),
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_knowledge_sync_runs
                        SET source_before_id=:source_id, updated_at=:updated_at
                        WHERE tenant_id=:tenant_id AND id=:run_id AND status='queued'
                        """
                    ),
                    {
                        "source_id": replacement,
                        "updated_at": utc_now(),
                        "tenant_id": tenant_id,
                        "run_id": run_id,
                    },
                )
                row = self._load_row(conn, tenant_id, run_id, job_id, lock=True)
                if row is None:
                    raise KnowledgeSyncWorkerError(
                        "KNOWLEDGE_SYNC_RUN_NOT_FOUND", "knowledge source sync run disappeared"
                    )
        return self._snapshot(row)

    @staticmethod
    def _load_row(
        conn: Any, tenant_id: str, run_id: str, job_id: str, *, lock: bool
    ) -> Mapping[str, Any] | None:
        lock_sql = " FOR UPDATE" if lock else ""
        return conn.execute(
            text(
                f"""
                SELECT r.*, p.enabled AS policy_enabled,
                       p.current_source_id, p.source_uri AS policy_source_uri,
                       s.source_type, s.title AS source_title, s.source_uri,
                       s.status AS source_status, s.revision_number,
                       s.authority_level, s.risk_level, s.valid_from, s.valid_until,
                       c.content_sha256 AS source_content_sha256
                FROM airank_knowledge_sync_runs r
                JOIN airank_knowledge_sync_policies p
                  ON p.tenant_id=r.tenant_id AND p.id=r.policy_id
                JOIN airank_knowledge_sources s
                  ON s.tenant_id=r.tenant_id AND s.id=p.current_source_id
                JOIN airank_knowledge_source_contents c
                  ON c.tenant_id=r.tenant_id AND c.knowledge_source_id=s.id
                WHERE r.tenant_id=:tenant_id AND r.id=:run_id AND r.job_id=:job_id
                {lock_sql}
                """
            ),
            {"tenant_id": tenant_id, "run_id": run_id, "job_id": job_id},
        ).mappings().first()

    @staticmethod
    def _snapshot(row: Mapping[str, Any]) -> KnowledgeSyncExecutionSnapshot:
        return KnowledgeSyncExecutionSnapshot(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["id"]),
            policy_id=str(row["policy_id"]),
            job_id=str(row["job_id"]),
            source_before_id=str(row["current_source_id"]),
            requested_url=str(row["requested_url"]),
            run_status=str(row["status"]),
            policy_enabled=bool(row["policy_enabled"]),
            source_type=str(row["source_type"]),
            source_title=str(row["source_title"]),
            source_uri=str(row["source_uri"]),
            source_status=str(row["source_status"]),
            source_revision_number=int(row["revision_number"]),
            source_content_sha256=str(row["source_content_sha256"]),
            authority_level=str(row["authority_level"]),
            risk_level=str(row["risk_level"]),
            valid_from=_optional_utc(row["valid_from"]),
            valid_until=_optional_utc(row["valid_until"]),
        )

    def begin(self, snapshot: KnowledgeSyncExecutionSnapshot, started_at: datetime) -> None:
        if not snapshot.policy_enabled:
            raise KnowledgeSyncWorkerError(
                "KNOWLEDGE_SYNC_POLICY_DISABLED", "knowledge source sync policy is disabled"
            )
        if snapshot.source_status != "active":
            raise KnowledgeSyncWorkerError(
                "KNOWLEDGE_SYNC_SOURCE_STALE", "knowledge source revision is not active"
            )
        moment = _db_datetime(started_at)
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_runs
                    SET status='running', started_at=COALESCE(started_at,:started_at),
                        error_code=NULL, error_message=NULL, updated_at=:started_at
                    WHERE tenant_id=:tenant_id AND id=:run_id AND job_id=:job_id
                      AND status IN ('queued','running','failed','blocked')
                    """
                ),
                {
                    "started_at": moment,
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                    "job_id": snapshot.job_id,
                },
            )
        if result.rowcount != 1:
            raise KnowledgeSyncWorkerError(
                "KNOWLEDGE_SYNC_STATE_CONFLICT", "knowledge source sync run cannot start"
            )

    def complete(
        self,
        snapshot: KnowledgeSyncExecutionSnapshot,
        result: CitationSourceCaptureResult,
        raw_object: StoredObject,
        text_object: StoredObject,
        completed_at: datetime,
    ) -> KnowledgeSyncOutcome:
        completed = _db_datetime(completed_at)
        raw_object_id = f"obj_ksync_raw_{snapshot.run_id[-24:]}"
        text_object_id = f"obj_ksync_text_{snapshot.run_id[-24:]}"
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT r.status, p.current_source_id, p.enabled,
                           s.revision_number, s.status AS source_status
                    FROM airank_knowledge_sync_runs r
                    JOIN airank_knowledge_sync_policies p
                      ON p.tenant_id=r.tenant_id AND p.id=r.policy_id
                    JOIN airank_knowledge_sources s
                      ON s.tenant_id=r.tenant_id AND s.id=p.current_source_id
                    WHERE r.tenant_id=:tenant_id AND r.id=:run_id AND r.job_id=:job_id
                    FOR UPDATE
                    """
                ),
                {
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                    "job_id": snapshot.job_id,
                },
            ).mappings().first()
            if row is None:
                raise KnowledgeSyncWorkerError(
                    "KNOWLEDGE_SYNC_RUN_NOT_FOUND", "knowledge source sync run was not found"
                )
            if str(row["status"]) in {"unchanged", "changed"}:
                stored = self._stored_outcome(conn, snapshot)
                return KnowledgeSyncOutcome(**stored, idempotent_replay=True)
            if str(row["status"]) != "running" or str(row["current_source_id"]) != snapshot.source_before_id:
                raise KnowledgeSyncWorkerError(
                    "KNOWLEDGE_SYNC_STATE_CONFLICT", "sync source changed while capture was running"
                )
            if not bool(row["enabled"]):
                raise KnowledgeSyncWorkerError(
                    "KNOWLEDGE_SYNC_POLICY_DISABLED", "sync policy was disabled while capture was running"
                )
            self._insert_object_ref(
                conn, snapshot, raw_object_id, raw_object, result, kind="knowledge_source_raw"
            )
            self._insert_object_ref(
                conn, snapshot, text_object_id, text_object, result, kind="knowledge_source_text"
            )
            changed = result.visible_text_sha256 != snapshot.source_content_sha256
            source_after_id = snapshot.source_before_id
            status = "unchanged"
            if changed:
                collision = conn.execute(
                    text(
                        """
                        SELECT id FROM airank_knowledge_sources
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND content_sha256=:content_sha256
                          AND id<>:source_id
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": snapshot.tenant_id,
                        "project_id": snapshot.project_id,
                        "content_sha256": result.visible_text_sha256,
                        "source_id": snapshot.source_before_id,
                    },
                ).scalar_one_or_none()
                if collision is not None:
                    raise KnowledgeSyncWorkerError(
                        "KNOWLEDGE_SYNC_CONTENT_COLLISION",
                        "captured content already belongs to another immutable source lineage",
                    )
                source_after_id = f"source_sync_{snapshot.run_id[-20:]}"
                segments = segment_source_text(source_after_id, result.visible_text, max_characters=1200)
                source_metadata = {
                    "sync_contract_version": SYNC_CONTRACT_VERSION,
                    "sync_run_id": snapshot.run_id,
                    "requested_url": snapshot.requested_url,
                    "final_url": result.final_url,
                    "raw_content_sha256": result.content_sha256,
                    "visible_text_sha256": result.visible_text_sha256,
                    "evidence_grade": result.evidence_grade,
                    "connected_ip": result.connected_ip,
                    "redirect_count": result.redirect_count,
                    "raw_object_ref_id": raw_object_id,
                    "text_object_ref_id": text_object_id,
                }
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_knowledge_sources (
                          id, tenant_id, project_id, parent_source_id, idempotency_key,
                          source_type, title, source_uri, object_ref_id, content_sha256,
                          authority_level, risk_level, status, revision_number,
                          captured_at, valid_from, valid_until, metadata_json, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :parent_source_id, :idempotency_key,
                          :source_type, :title, :source_uri, :object_ref_id, :content_sha256,
                          :authority_level, :risk_level, 'active', :revision_number,
                          :captured_at, :valid_from, :valid_until, :metadata_json, :created_at
                        )
                        """
                    ),
                    {
                        "id": source_after_id,
                        "tenant_id": snapshot.tenant_id,
                        "project_id": snapshot.project_id,
                        "parent_source_id": snapshot.source_before_id,
                        "idempotency_key": f"ksync:{snapshot.policy_id}:{result.visible_text_sha256}",
                        "source_type": snapshot.source_type,
                        "title": snapshot.source_title,
                        "source_uri": snapshot.source_uri,
                        "object_ref_id": raw_object_id,
                        "content_sha256": result.visible_text_sha256,
                        "authority_level": snapshot.authority_level,
                        "risk_level": snapshot.risk_level,
                        "revision_number": int(row["revision_number"]) + 1,
                        "captured_at": completed,
                        "valid_from": _db_optional(snapshot.valid_from),
                        "valid_until": _db_optional(snapshot.valid_until),
                        "metadata_json": json.dumps(source_metadata, ensure_ascii=False, sort_keys=True),
                        "created_at": completed,
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_knowledge_source_contents (
                          knowledge_source_id, tenant_id, project_id, content_text,
                          content_sha256, content_type, byte_size, created_at
                        ) VALUES (
                          :source_id, :tenant_id, :project_id, :content_text,
                          :content_sha256, 'text/plain; charset=utf-8', :byte_size, :created_at
                        )
                        """
                    ),
                    {
                        "source_id": source_after_id,
                        "tenant_id": snapshot.tenant_id,
                        "project_id": snapshot.project_id,
                        "content_text": result.visible_text,
                        "content_sha256": result.visible_text_sha256,
                        "byte_size": len(result.visible_text.encode("utf-8")),
                        "created_at": completed,
                    },
                )
                for segment in segments:
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_knowledge_segments (
                              id, tenant_id, project_id, knowledge_source_id,
                              segment_index, segment_text, source_start, source_end,
                              content_sha256, embedding_status, created_at
                            ) VALUES (
                              :id, :tenant_id, :project_id, :source_id,
                              :segment_index, :segment_text, :source_start, :source_end,
                              :content_sha256, 'pending', :created_at
                            )
                            """
                        ),
                        {
                            "id": segment.id,
                            "tenant_id": snapshot.tenant_id,
                            "project_id": snapshot.project_id,
                            "source_id": source_after_id,
                            "segment_index": segment.segment_index,
                            "segment_text": segment.text,
                            "source_start": segment.source_start,
                            "source_end": segment.source_end,
                            "content_sha256": segment.content_sha256,
                            "created_at": completed,
                        },
                    )
                conn.execute(
                    text(
                        """
                        UPDATE airank_knowledge_sources SET status='stale'
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND id=:source_id AND status='active'
                        """
                    ),
                    {
                        "tenant_id": snapshot.tenant_id,
                        "project_id": snapshot.project_id,
                        "source_id": snapshot.source_before_id,
                    },
                )
                status = "changed"
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_runs
                    SET source_after_id=:source_after_id, status=:status,
                        final_url=:final_url, evidence_grade=:evidence_grade,
                        response_status=:response_status, content_type=:content_type,
                        response_bytes=:response_bytes,
                        raw_content_sha256=:raw_content_sha256,
                        visible_text_sha256=:visible_text_sha256,
                        raw_object_ref_id=:raw_object_ref_id,
                        text_object_ref_id=:text_object_ref_id,
                        connected_ip=:connected_ip, redirect_count=:redirect_count,
                        error_code=NULL, error_message=NULL,
                        completed_at=:completed_at, updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:run_id AND job_id=:job_id
                    """
                ),
                {
                    "source_after_id": source_after_id,
                    "status": status,
                    "final_url": result.final_url,
                    "evidence_grade": result.evidence_grade,
                    "response_status": result.response_status,
                    "content_type": result.content_type,
                    "response_bytes": result.response_bytes,
                    "raw_content_sha256": result.content_sha256,
                    "visible_text_sha256": result.visible_text_sha256,
                    "raw_object_ref_id": raw_object_id,
                    "text_object_ref_id": text_object_id,
                    "connected_ip": result.connected_ip,
                    "redirect_count": result.redirect_count,
                    "completed_at": completed,
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                    "job_id": snapshot.job_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_policies
                    SET current_source_id=:source_after_id, last_run_id=:run_id,
                        last_status=:status, last_checked_at=:completed_at,
                        version=version+:version_delta,
                        updated_by='knowledge-sync-worker', updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:policy_id
                    """
                ),
                {
                    "source_after_id": source_after_id,
                    "run_id": snapshot.run_id,
                    "status": status,
                    "completed_at": completed,
                    "version_delta": 1 if changed else 0,
                    "tenant_id": snapshot.tenant_id,
                    "policy_id": snapshot.policy_id,
                },
            )
            self._audit(
                conn,
                snapshot,
                event_type="knowledge.sync.changed" if changed else "knowledge.sync.unchanged",
                payload={
                    "source_before_id": snapshot.source_before_id,
                    "source_after_id": source_after_id,
                    "raw_content_sha256": result.content_sha256,
                    "visible_text_sha256": result.visible_text_sha256,
                    "raw_object_ref_id": raw_object_id,
                    "text_object_ref_id": text_object_id,
                    "evidence_grade": result.evidence_grade,
                },
                created_at=completed,
            )
        return KnowledgeSyncOutcome(
            run_id=snapshot.run_id,
            policy_id=snapshot.policy_id,
            status=status,
            source_before_id=snapshot.source_before_id,
            source_after_id=source_after_id,
            raw_content_sha256=result.content_sha256,
            visible_text_sha256=result.visible_text_sha256,
            raw_object_ref_id=raw_object_id,
            text_object_ref_id=text_object_id,
        )

    @staticmethod
    def _insert_object_ref(
        conn: Any,
        snapshot: KnowledgeSyncExecutionSnapshot,
        object_id: str,
        stored: StoredObject,
        result: CitationSourceCaptureResult,
        *,
        kind: str,
    ) -> None:
        metadata = {
            "kind": kind,
            "sync_contract_version": SYNC_CONTRACT_VERSION,
            "sync_run_id": snapshot.run_id,
            "policy_id": snapshot.policy_id,
            "source_before_id": snapshot.source_before_id,
            "requested_url": snapshot.requested_url,
            "final_url": result.final_url,
            "storage_driver": stored.driver,
            "object_key": stored.key,
        }
        conn.execute(
            text(
                """
                INSERT INTO airank_object_refs (
                  id, tenant_id, project_id, object_type, object_uri,
                  content_type, byte_size, sha256, metadata_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, 'knowledge_source', :object_uri,
                  :content_type, :byte_size, :sha256, :metadata_json, :created_at
                ) ON DUPLICATE KEY UPDATE id=id
                """
            ),
            {
                "id": object_id,
                "tenant_id": snapshot.tenant_id,
                "project_id": snapshot.project_id,
                "object_uri": stored.uri,
                "content_type": stored.content_type,
                "byte_size": stored.byte_size,
                "sha256": stored.sha256,
                "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                "created_at": utc_now(),
            },
        )

    @staticmethod
    def _stored_outcome(conn: Any, snapshot: KnowledgeSyncExecutionSnapshot) -> dict[str, Any]:
        row = conn.execute(
            text(
                """
                SELECT status, source_after_id, raw_content_sha256,
                       visible_text_sha256, raw_object_ref_id, text_object_ref_id
                FROM airank_knowledge_sync_runs
                WHERE tenant_id=:tenant_id AND id=:run_id
                """
            ),
            {"tenant_id": snapshot.tenant_id, "run_id": snapshot.run_id},
        ).mappings().one()
        return {
            "run_id": snapshot.run_id,
            "policy_id": snapshot.policy_id,
            "status": str(row["status"]),
            "source_before_id": snapshot.source_before_id,
            "source_after_id": str(row["source_after_id"]),
            "raw_content_sha256": str(row["raw_content_sha256"]),
            "visible_text_sha256": str(row["visible_text_sha256"]),
            "raw_object_ref_id": str(row["raw_object_ref_id"]),
            "text_object_ref_id": str(row["text_object_ref_id"]),
        }

    def fail(
        self,
        snapshot: KnowledgeSyncExecutionSnapshot,
        error: KnowledgeSyncWorkerError,
        completed_at: datetime,
        *,
        status: str,
    ) -> None:
        completed = _db_datetime(completed_at)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_runs
                    SET status=:status, error_code=:error_code,
                        error_message=:error_message, completed_at=:completed_at,
                        updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                      AND status NOT IN ('unchanged','changed')
                    """
                ),
                {
                    "status": status,
                    "error_code": error.code,
                    "error_message": error.message[:1000],
                    "completed_at": completed,
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_policies
                    SET last_run_id=:run_id, last_status=:status,
                        last_checked_at=:completed_at,
                        updated_by='knowledge-sync-worker', updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:policy_id
                    """
                ),
                {
                    "run_id": snapshot.run_id,
                    "status": status,
                    "completed_at": completed,
                    "tenant_id": snapshot.tenant_id,
                    "policy_id": snapshot.policy_id,
                },
            )
            self._audit(
                conn,
                snapshot,
                event_type=f"knowledge.sync.{status}",
                payload={"error_code": error.code, "retryable": error.retryable},
                created_at=completed,
            )

    def schedule_retry(
        self,
        snapshot: KnowledgeSyncExecutionSnapshot,
        error: KnowledgeSyncWorkerError,
        recorded_at: datetime,
        retry_at: datetime,
    ) -> None:
        recorded = _db_datetime(recorded_at)
        scheduled = _db_datetime(retry_at)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_runs
                    SET status='queued', error_code=:error_code,
                        error_message=:error_message, completed_at=NULL,
                        updated_at=:updated_at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                      AND status NOT IN ('unchanged','changed')
                    """
                ),
                {
                    "error_code": error.code,
                    "error_message": error.message[:1000],
                    "updated_at": recorded,
                    "tenant_id": snapshot.tenant_id,
                    "run_id": snapshot.run_id,
                },
            )
            self._audit(
                conn,
                snapshot,
                event_type="knowledge.sync.retry_scheduled",
                payload={
                    "error_code": error.code,
                    "retryable": True,
                    "retry_at": _as_utc(retry_at).isoformat(),
                },
                created_at=recorded,
            )

    @staticmethod
    def _audit(
        conn: Any,
        snapshot: KnowledgeSyncExecutionSnapshot,
        *,
        event_type: str,
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
                  :id, :tenant_id, :project_id, 'knowledge-sync-worker', :event_type,
                  'knowledge_sync_run', :entity_id, :payload_json, :created_at
                )
                """
            ),
            {
                "id": f"audit_{uuid4().hex[:16]}",
                "tenant_id": snapshot.tenant_id,
                "project_id": snapshot.project_id,
                "event_type": event_type,
                "entity_id": snapshot.run_id,
                "payload_json": json.dumps(dict(payload), ensure_ascii=False, sort_keys=True),
                "created_at": created_at,
            },
        )


def build_knowledge_sync_service() -> CitationSourceCaptureService:
    try:
        timeout_seconds = max(
            1.0, float(os.getenv("AIRANK_KNOWLEDGE_SYNC_TIMEOUT_SECONDS") or 20)
        )
    except ValueError:
        timeout_seconds = 20.0
    try:
        max_response_bytes = max(
            1, int(os.getenv("AIRANK_KNOWLEDGE_SYNC_MAX_RESPONSE_BYTES") or 2_000_000)
        )
    except ValueError:
        max_response_bytes = 2_000_000
    return CitationSourceCaptureService(
        timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes
    )


def knowledge_sync_object_keys(
    snapshot: KnowledgeSyncExecutionSnapshot, result: CitationSourceCaptureResult
) -> tuple[str, str]:
    prefix = f"tenants/{snapshot.tenant_id}/projects/{snapshot.project_id}/knowledge-sync"
    extension = "html" if result.content_type in {"text/html", "application/xhtml+xml"} else "txt"
    return (
        f"{prefix}/raw/{result.content_sha256}.{extension}",
        f"{prefix}/text/{result.visible_text_sha256}.txt",
    )


def run_next_knowledge_sync_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: KnowledgeSyncExecutionRepository,
    service: CitationSourceCaptureService,
    object_storage: ObjectStorage,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> KnowledgeSyncOutcome | None:
    started_at = now or utc_now()
    job = store.claim_next(worker_id, started_at, job_types={"knowledge.source.sync"})
    if job is None:
        return None
    return run_claimed_knowledge_sync_job(
        store,
        repository,
        service,
        object_storage,
        job=job,
        worker_id=worker_id,
        started_at=started_at,
    )


def run_claimed_knowledge_sync_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: KnowledgeSyncExecutionRepository,
    service: CitationSourceCaptureService,
    object_storage: ObjectStorage,
    *,
    job: AsyncJob,
    worker_id: str,
    started_at: datetime,
) -> KnowledgeSyncOutcome | None:
    payload = job.payload if isinstance(job.payload, dict) else {}
    run_id = str(payload.get("sync_run_id") or "")
    if (
        not run_id
        or not payload.get("policy_id")
        or str(payload.get("contract_version") or "") != SYNC_CONTRACT_VERSION
    ):
        error = KnowledgeSyncWorkerError(
            "KNOWLEDGE_SYNC_JOB_INVALID", "knowledge source sync job payload is invalid"
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    try:
        snapshot = repository.load(job.tenant_id, run_id, job.id)
    except KnowledgeSyncWorkerError as exc:
        store.fail(job.id, worker_id, utc_now(), exc.code, exc.message)
        raise
    if snapshot.project_id != (job.project_id or "") or snapshot.policy_id != str(payload["policy_id"]):
        error = KnowledgeSyncWorkerError(
            "KNOWLEDGE_SYNC_SCOPE_MISMATCH", "knowledge source sync job scope differs"
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    if snapshot.run_status in {"unchanged", "changed"}:
        store.succeed(
            job.id,
            worker_id,
            utc_now(),
            {"sync_run_id": run_id, "status": snapshot.run_status, "idempotent_replay": True},
        )
        return None
    try:
        repository.begin(snapshot, started_at)
        result = service.capture(snapshot.requested_url)
        raw_key, text_key = knowledge_sync_object_keys(snapshot, result)
        raw_object = object_storage.put_bytes(
            result.raw_body, key=raw_key, content_type=result.content_type
        )
        text_object = object_storage.put_bytes(
            result.visible_text.encode("utf-8"),
            key=text_key,
            content_type="text/plain; charset=utf-8",
        )
        if raw_object.sha256 != result.content_sha256 or text_object.sha256 != result.visible_text_sha256:
            raise ObjectStorageError("stored knowledge sync object hash does not match capture result")
        outcome = repository.complete(
            snapshot, result, raw_object, text_object, utc_now()
        )
    except OutboundSecurityError as exc:
        error = KnowledgeSyncWorkerError(
            f"KNOWLEDGE_SYNC_{exc.code.removeprefix('OUTBOUND_')}",
            exc.message,
            retryable=exc.retryable,
        )
    except ObjectStorageError as exc:
        error = KnowledgeSyncWorkerError(
            "KNOWLEDGE_SYNC_STORAGE_FAILED",
            f"immutable knowledge source storage failed: {type(exc).__name__}",
            retryable=True,
        )
    except KnowledgeSyncWorkerError as exc:
        error = exc
    except ValueError as exc:
        error = KnowledgeSyncWorkerError("KNOWLEDGE_SYNC_CONTENT_INVALID", str(exc))
    except Exception as exc:
        error = KnowledgeSyncWorkerError(
            "KNOWLEDGE_SYNC_INTERNAL_ERROR",
            f"knowledge source sync failed: {type(exc).__name__}",
        )
    else:
        finished_at = utc_now()
        store.succeed(job.id, worker_id, finished_at, outcome.to_record())
        return outcome
    finished_at = utc_now()
    store.fail(job.id, worker_id, finished_at, error.code, error.message)
    if error.retryable and job.attempt_count < job.max_attempts:
        delay_seconds = min(300, 5 * (2 ** max(0, job.attempt_count - 1)))
        retry_base = max(_as_utc(finished_at), _as_utc(started_at))
        retry_at = retry_base + timedelta(seconds=delay_seconds)
        store.requeue_for_retry(job.id, retry_at)
        repository.schedule_retry(snapshot, error, finished_at, retry_at)
    else:
        repository.fail(
            snapshot,
            error,
            finished_at,
            status="failed" if error.retryable else "blocked",
        )
    raise error


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _db_datetime(value: datetime) -> datetime:
    return _as_utc(value).replace(tzinfo=None)


def _db_optional(value: datetime | None) -> datetime | None:
    return _db_datetime(value) if value is not None else None

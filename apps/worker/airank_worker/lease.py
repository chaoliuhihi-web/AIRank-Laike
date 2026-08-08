from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from typing import Iterable

from airank_domain import (
    AsyncJob,
    AsyncJobStatus,
    JobOwnershipError,
    claim_job,
    complete_job,
    fail_job,
    heartbeat_job,
    timeout_job,
)
from sqlalchemy import bindparam, create_engine, text


class InMemoryJobLeaseStore:
    """Small deterministic lease store used until MySQL persistence is wired."""

    def __init__(self, jobs: Iterable[AsyncJob] | None = None) -> None:
        self._jobs: dict[str, AsyncJob] = {}
        for job in jobs or ():
            self.add(job)

    def add(self, job: AsyncJob) -> None:
        if job.id in self._jobs:
            raise ValueError(f"job {job.id} already exists")
        self._jobs[job.id] = job

    def get(self, job_id: str) -> AsyncJob:
        return self._jobs[job_id]

    def all(self) -> list[AsyncJob]:
        return list(self._jobs.values())

    def claim_next(
        self,
        worker_id: str,
        now: datetime,
        *,
        job_types: set[str] | None = None,
        tenant_id: str | None = None,
    ) -> AsyncJob | None:
        self.sweep_timeouts(now, tenant_id=tenant_id, job_types=job_types)
        claimable = [
            job
            for job in self._jobs.values()
            if job.status == AsyncJobStatus.QUEUED
            and job.is_due(now)
            and (not job_types or job.job_type in job_types)
            and (tenant_id is None or job.tenant_id == tenant_id)
        ]
        if not claimable:
            return None
        selected = sorted(claimable, key=lambda job: (job.priority, job.scheduled_at, job.id))[0]
        claimed = claim_job(selected, worker_id, now)
        self._jobs[claimed.id] = claimed
        return claimed

    def heartbeat(self, job_id: str, worker_id: str, now: datetime) -> AsyncJob:
        updated = heartbeat_job(self._jobs[job_id], worker_id, now)
        self._jobs[job_id] = updated
        return updated

    def succeed(
        self,
        job_id: str,
        worker_id: str,
        now: datetime,
        result: dict[str, object] | None = None,
    ) -> AsyncJob:
        updated = complete_job(self._jobs[job_id], worker_id, now, result)
        self._jobs[job_id] = updated
        return updated

    def fail(
        self,
        job_id: str,
        worker_id: str,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> AsyncJob:
        updated = fail_job(self._jobs[job_id], worker_id, now, error_code, error_message)
        self._jobs[job_id] = updated
        return updated

    def sweep_timeouts(
        self,
        now: datetime,
        *,
        tenant_id: str | None = None,
        job_types: set[str] | None = None,
    ) -> list[AsyncJob]:
        timed_out: list[AsyncJob] = []
        for job in list(self._jobs.values()):
            if (
                job.is_timed_out(now)
                and (tenant_id is None or job.tenant_id == tenant_id)
                and (not job_types or job.job_type in job_types)
            ):
                updated = timeout_job(job, now)
                self._jobs[job.id] = updated
                timed_out.append(updated)
        return timed_out

    def requeue_for_retry(self, job_id: str, now: datetime) -> AsyncJob:
        job = self._jobs[job_id]
        if job.status not in {AsyncJobStatus.FAILED, AsyncJobStatus.TIMEOUT}:
            raise ValueError(f"job {job.id} is {job.status.value}, not retryable")
        if job.attempt_count >= job.max_attempts:
            raise ValueError(f"job {job.id} has no attempts remaining")
        updated = replace(
            job,
            status=AsyncJobStatus.QUEUED,
            scheduled_at=now,
            locked_by=None,
            locked_at=None,
            heartbeat_at=None,
            finished_at=None,
            updated_at=now,
        )
        self._jobs[job_id] = updated
        return updated

    def defer_claim(
        self,
        job_id: str,
        worker_id: str,
        now: datetime,
        *,
        delay_seconds: int = 5,
    ) -> AsyncJob:
        job = self._jobs[job_id]
        if job.status != AsyncJobStatus.RUNNING or job.locked_by != worker_id:
            raise JobOwnershipError(f"worker {worker_id} does not own running job {job_id}")
        updated = replace(
            job,
            status=AsyncJobStatus.QUEUED,
            scheduled_at=now + timedelta(seconds=max(1, delay_seconds)),
            locked_by=None,
            locked_at=None,
            heartbeat_at=None,
            attempt_count=max(0, job.attempt_count - 1),
            started_at=None,
            finished_at=None,
            updated_at=now,
        )
        self._jobs[job_id] = updated
        return updated


def parse_json_value(value: object, fallback: object) -> object:
    if value is None:
        return fallback
    if isinstance(value, str):
        return json.loads(value)
    return value


def coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported datetime value: {value!r}")


class MySQLJobLeaseStore:
    """Persistent lease store backed by the AIRank `airank_async_jobs` table."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url, pool_pre_ping=True)

    def add(self, job: AsyncJob) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_async_jobs (
                      id, tenant_id, project_id, job_type, status, priority,
                      scheduled_at, locked_by, locked_at, heartbeat_at,
                      timeout_seconds, attempt_count, max_attempts, payload_json,
                      result_json, error_code, error_message, started_at,
                      finished_at, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :job_type, :status, :priority,
                      :scheduled_at, :locked_by, :locked_at, :heartbeat_at,
                      :timeout_seconds, :attempt_count, :max_attempts, :payload_json,
                      :result_json, :error_code, :error_message, :started_at,
                      :finished_at, :created_at, :updated_at
                    )
                    """
                ),
                self._job_params(job),
            )

    def get(self, job_id: str) -> AsyncJob:
        with self._engine.begin() as conn:
            row = self._select_job(conn, job_id)
        if row is None:
            raise KeyError(job_id)
        return self._row_to_job(row)

    def all(self) -> list[AsyncJob]:
        with self._engine.begin() as conn:
            rows = conn.execute(text("SELECT * FROM airank_async_jobs ORDER BY created_at ASC, id ASC")).mappings().all()
        return [self._row_to_job(row) for row in rows]

    def claim_next(
        self,
        worker_id: str,
        now: datetime,
        *,
        job_types: set[str] | None = None,
        tenant_id: str | None = None,
    ) -> AsyncJob | None:
        self.sweep_timeouts(now, tenant_id=tenant_id, job_types=job_types)
        with self._engine.begin() as conn:
            query = text(
                """
                SELECT *
                FROM airank_async_jobs
                WHERE status = 'queued'
                  AND scheduled_at <= :now
                  {job_type_clause}
                  {tenant_clause}
                ORDER BY priority ASC, scheduled_at ASC, id ASC
                LIMIT 1
                """.format(
                    job_type_clause="AND job_type IN :job_types" if job_types else "",
                    tenant_clause="AND tenant_id = :tenant_id" if tenant_id else "",
                )
            )
            params: dict[str, object] = {"now": now}
            if job_types:
                query = query.bindparams(bindparam("job_types", expanding=True))
                params["job_types"] = sorted(job_types)
            if tenant_id:
                params["tenant_id"] = tenant_id
            row = conn.execute(
                query,
                params,
            ).mappings().first()
            if row is None:
                return None
            claimed = claim_job(self._row_to_job(row), worker_id, now)
            result = conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs
                    SET status = :status,
                        locked_by = :locked_by,
                        locked_at = :locked_at,
                        heartbeat_at = :heartbeat_at,
                        started_at = :started_at,
                        attempt_count = :attempt_count,
                        error_code = NULL,
                        error_message = NULL,
                        updated_at = :updated_at
                    WHERE id = :id
                      AND status = 'queued'
                    """
                ),
                self._job_params(claimed),
            )
            if result.rowcount != 1:
                return None
            return claimed

    def heartbeat(self, job_id: str, worker_id: str, now: datetime) -> AsyncJob:
        updated = heartbeat_job(self.get(job_id), worker_id, now)
        self._update_job(updated)
        return updated

    def succeed(
        self,
        job_id: str,
        worker_id: str,
        now: datetime,
        result: dict[str, object] | None = None,
    ) -> AsyncJob:
        updated = complete_job(self.get(job_id), worker_id, now, result)
        self._update_job(updated)
        return updated

    def fail(
        self,
        job_id: str,
        worker_id: str,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> AsyncJob:
        updated = fail_job(self.get(job_id), worker_id, now, error_code, error_message)
        self._update_job(updated)
        return updated

    def sweep_timeouts(
        self,
        now: datetime,
        *,
        tenant_id: str | None = None,
        job_types: set[str] | None = None,
    ) -> list[AsyncJob]:
        with self._engine.begin() as conn:
            query = "SELECT * FROM airank_async_jobs WHERE status = 'running'"
            params: dict[str, object] = {}
            if tenant_id:
                query += " AND tenant_id = :tenant_id"
                params["tenant_id"] = tenant_id
            if job_types:
                query += " AND job_type IN :job_types"
                statement = text(query).bindparams(bindparam("job_types", expanding=True))
                params["job_types"] = sorted(job_types)
            else:
                statement = text(query)
            rows = conn.execute(statement, params).mappings().all()
            timed_out: list[AsyncJob] = []
            for row in rows:
                job = self._row_to_job(row)
                if not job.is_timed_out(now):
                    continue
                updated = timeout_job(job, now)
                conn.execute(
                    text(
                        """
                        UPDATE airank_async_jobs
                        SET status = :status,
                            error_code = :error_code,
                            error_message = :error_message,
                            finished_at = :finished_at,
                            updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    self._job_params(updated),
                )
                timed_out.append(updated)
        return timed_out

    def requeue_for_retry(self, job_id: str, now: datetime) -> AsyncJob:
        job = self.get(job_id)
        if job.status not in {AsyncJobStatus.FAILED, AsyncJobStatus.TIMEOUT}:
            raise ValueError(f"job {job.id} is {job.status.value}, not retryable")
        if job.attempt_count >= job.max_attempts:
            raise ValueError(f"job {job.id} has no attempts remaining")
        updated = replace(
            job,
            status=AsyncJobStatus.QUEUED,
            scheduled_at=now,
            locked_by=None,
            locked_at=None,
            heartbeat_at=None,
            finished_at=None,
            updated_at=now,
        )
        self._update_job(updated)
        return updated

    def defer_claim(
        self,
        job_id: str,
        worker_id: str,
        now: datetime,
        *,
        delay_seconds: int = 5,
    ) -> AsyncJob:
        job = self.get(job_id)
        if job.status != AsyncJobStatus.RUNNING or job.locked_by != worker_id:
            raise JobOwnershipError(f"worker {worker_id} does not own running job {job_id}")
        updated = replace(
            job,
            status=AsyncJobStatus.QUEUED,
            scheduled_at=now + timedelta(seconds=max(1, delay_seconds)),
            locked_by=None,
            locked_at=None,
            heartbeat_at=None,
            attempt_count=max(0, job.attempt_count - 1),
            started_at=None,
            finished_at=None,
            updated_at=now,
        )
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs
                    SET status = :status,
                        scheduled_at = :scheduled_at,
                        locked_by = NULL,
                        locked_at = NULL,
                        heartbeat_at = NULL,
                        attempt_count = :attempt_count,
                        started_at = NULL,
                        finished_at = NULL,
                        updated_at = :updated_at
                    WHERE id = :id
                      AND status = 'running'
                      AND locked_by = :worker_id
                    """
                ),
                {
                    "id": job_id,
                    "worker_id": worker_id,
                    "status": updated.status.value,
                    "scheduled_at": updated.scheduled_at,
                    "attempt_count": updated.attempt_count,
                    "updated_at": updated.updated_at,
                },
            )
        if result.rowcount != 1:
            raise JobOwnershipError(f"worker {worker_id} lost ownership of running job {job_id}")
        return updated

    def _select_job(self, conn: object, job_id: str) -> object | None:
        return conn.execute(  # type: ignore[attr-defined]
            text("SELECT * FROM airank_async_jobs WHERE id = :id"),
            {"id": job_id},
        ).mappings().first()

    def _update_job(self, job: AsyncJob) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs
                    SET status = :status,
                        priority = :priority,
                        scheduled_at = :scheduled_at,
                        locked_by = :locked_by,
                        locked_at = :locked_at,
                        heartbeat_at = :heartbeat_at,
                        timeout_seconds = :timeout_seconds,
                        attempt_count = :attempt_count,
                        max_attempts = :max_attempts,
                        payload_json = :payload_json,
                        result_json = :result_json,
                        error_code = :error_code,
                        error_message = :error_message,
                        started_at = :started_at,
                        finished_at = :finished_at,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                self._job_params(job),
            )

    def _row_to_job(self, row: object) -> AsyncJob:
        return AsyncJob(
            id=row["id"],  # type: ignore[index]
            tenant_id=row["tenant_id"],  # type: ignore[index]
            project_id=row["project_id"],  # type: ignore[index]
            job_type=row["job_type"],  # type: ignore[index]
            status=AsyncJobStatus(row["status"]),  # type: ignore[index]
            priority=row["priority"],  # type: ignore[index]
            scheduled_at=coerce_datetime(row["scheduled_at"]),  # type: ignore[index]
            locked_by=row["locked_by"],  # type: ignore[index]
            locked_at=coerce_datetime(row["locked_at"]) if row["locked_at"] else None,  # type: ignore[index]
            heartbeat_at=coerce_datetime(row["heartbeat_at"]) if row["heartbeat_at"] else None,  # type: ignore[index]
            timeout_seconds=row["timeout_seconds"],  # type: ignore[index]
            attempt_count=row["attempt_count"],  # type: ignore[index]
            max_attempts=row["max_attempts"],  # type: ignore[index]
            payload=parse_json_value(row["payload_json"], None),  # type: ignore[index]
            result=parse_json_value(row["result_json"], None),  # type: ignore[index]
            error_code=row["error_code"],  # type: ignore[index]
            error_message=row["error_message"],  # type: ignore[index]
            started_at=coerce_datetime(row["started_at"]) if row["started_at"] else None,  # type: ignore[index]
            finished_at=coerce_datetime(row["finished_at"]) if row["finished_at"] else None,  # type: ignore[index]
            created_at=coerce_datetime(row["created_at"]),  # type: ignore[index]
            updated_at=coerce_datetime(row["updated_at"]),  # type: ignore[index]
        )

    def _job_params(self, job: AsyncJob) -> dict[str, object]:
        return {
            "id": job.id,
            "tenant_id": job.tenant_id,
            "project_id": job.project_id,
            "job_type": job.job_type,
            "status": job.status.value,
            "priority": job.priority,
            "scheduled_at": job.scheduled_at,
            "locked_by": job.locked_by,
            "locked_at": job.locked_at,
            "heartbeat_at": job.heartbeat_at,
            "timeout_seconds": job.timeout_seconds,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
            "payload_json": json.dumps(job.payload) if job.payload is not None else None,
            "result_json": json.dumps(job.result) if job.result is not None else None,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

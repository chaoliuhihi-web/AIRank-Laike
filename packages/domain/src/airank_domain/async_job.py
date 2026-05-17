from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class AsyncJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"


class JobStateError(ValueError):
    """Raised when a transition would hide an invalid job state."""


class JobOwnershipError(ValueError):
    """Raised when a worker mutates a lease owned by another worker."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AsyncJob:
    id: str
    tenant_id: str
    job_type: str
    status: AsyncJobStatus = AsyncJobStatus.QUEUED
    priority: int = 100
    scheduled_at: datetime = field(default_factory=utc_now)
    project_id: str | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    heartbeat_at: datetime | None = None
    timeout_seconds: int = 300
    attempt_count: int = 0
    max_attempts: int = 3
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def is_due(self, now: datetime) -> bool:
        return self.scheduled_at <= now

    def is_terminal(self) -> bool:
        return self.status in {
            AsyncJobStatus.SUCCEEDED,
            AsyncJobStatus.FAILED,
            AsyncJobStatus.TIMEOUT,
        }

    def heartbeat_deadline(self) -> datetime | None:
        last_seen = self.heartbeat_at or self.locked_at
        if last_seen is None:
            return None
        return last_seen + timedelta(seconds=self.timeout_seconds)

    def is_timed_out(self, now: datetime) -> bool:
        deadline = self.heartbeat_deadline()
        return self.status == AsyncJobStatus.RUNNING and deadline is not None and deadline <= now


def claim_job(job: AsyncJob, worker_id: str, now: datetime) -> AsyncJob:
    if job.status != AsyncJobStatus.QUEUED:
        raise JobStateError(f"cannot claim job {job.id} from {job.status.value}")
    if not job.is_due(now):
        raise JobStateError(f"cannot claim job {job.id} before scheduled_at")
    if job.attempt_count >= job.max_attempts:
        return fail_job(
            replace(job, status=AsyncJobStatus.RUNNING, locked_by=worker_id),
            worker_id,
            now,
            "JOB_MAX_ATTEMPTS_EXCEEDED",
            "job exceeded max attempts before claim",
        )
    return replace(
        job,
        status=AsyncJobStatus.RUNNING,
        locked_by=worker_id,
        locked_at=now,
        heartbeat_at=now,
        started_at=job.started_at or now,
        attempt_count=job.attempt_count + 1,
        updated_at=now,
        error_code=None,
        error_message=None,
    )


def heartbeat_job(job: AsyncJob, worker_id: str, now: datetime) -> AsyncJob:
    ensure_running_owner(job, worker_id)
    return replace(job, heartbeat_at=now, updated_at=now)


def complete_job(
    job: AsyncJob,
    worker_id: str,
    now: datetime,
    result: dict[str, Any] | None = None,
) -> AsyncJob:
    ensure_running_owner(job, worker_id)
    return replace(
        job,
        status=AsyncJobStatus.SUCCEEDED,
        result=result,
        finished_at=now,
        updated_at=now,
    )


def fail_job(
    job: AsyncJob,
    worker_id: str,
    now: datetime,
    error_code: str,
    error_message: str,
) -> AsyncJob:
    ensure_running_owner(job, worker_id)
    return replace(
        job,
        status=AsyncJobStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
        finished_at=now,
        updated_at=now,
    )


def timeout_job(job: AsyncJob, now: datetime) -> AsyncJob:
    if job.status != AsyncJobStatus.RUNNING:
        raise JobStateError(f"cannot timeout job {job.id} from {job.status.value}")
    if not job.is_timed_out(now):
        raise JobStateError(f"cannot timeout job {job.id} before heartbeat deadline")
    return replace(
        job,
        status=AsyncJobStatus.TIMEOUT,
        error_code="JOB_TIMEOUT",
        error_message="worker heartbeat exceeded timeout_seconds",
        finished_at=now,
        updated_at=now,
    )


def ensure_running_owner(job: AsyncJob, worker_id: str) -> None:
    if job.status != AsyncJobStatus.RUNNING:
        raise JobStateError(f"job {job.id} is {job.status.value}, not running")
    if job.locked_by != worker_id:
        raise JobOwnershipError(f"job {job.id} is locked by {job.locked_by}")

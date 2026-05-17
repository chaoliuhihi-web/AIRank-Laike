from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from airank_domain import (
    AsyncJob,
    AsyncJobStatus,
    claim_job,
    complete_job,
    fail_job,
    heartbeat_job,
    timeout_job,
)


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

    def claim_next(self, worker_id: str, now: datetime) -> AsyncJob | None:
        self.sweep_timeouts(now)
        claimable = [
            job
            for job in self._jobs.values()
            if job.status == AsyncJobStatus.QUEUED and job.is_due(now)
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

    def sweep_timeouts(self, now: datetime) -> list[AsyncJob]:
        timed_out: list[AsyncJob] = []
        for job in list(self._jobs.values()):
            if job.is_timed_out(now):
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

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from airank_domain import AsyncJob, AsyncJobStatus, JobOwnershipError
from airank_worker import InMemoryJobLeaseStore


NOW = datetime(2026, 5, 17, 8, 0, tzinfo=timezone.utc)


def test_claim_heartbeat_and_succeed_job() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="job_scan_1",
                tenant_id="tenant_1",
                project_id="project_1",
                job_type="scan",
                priority=10,
                scheduled_at=NOW,
            )
        ]
    )

    claimed = store.claim_next("worker-a", NOW)
    assert claimed is not None
    assert claimed.status == AsyncJobStatus.RUNNING
    assert claimed.locked_by == "worker-a"
    assert claimed.attempt_count == 1

    heartbeat_at = NOW + timedelta(seconds=10)
    heartbeat = store.heartbeat("job_scan_1", "worker-a", heartbeat_at)
    assert heartbeat.heartbeat_at == heartbeat_at

    finished = store.succeed("job_scan_1", "worker-a", heartbeat_at, {"snapshots": 1})
    assert finished.status == AsyncJobStatus.SUCCEEDED
    assert finished.result == {"snapshots": 1}
    assert store.claim_next("worker-b", heartbeat_at) is None


def test_failed_job_does_not_return_to_queued_without_explicit_retry() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="job_scan_2",
                tenant_id="tenant_1",
                job_type="scan",
                scheduled_at=NOW,
            )
        ]
    )

    store.claim_next("worker-a", NOW)
    failed = store.fail(
        "job_scan_2",
        "worker-a",
        NOW + timedelta(seconds=1),
        "PROVIDER_ERROR",
        "mock provider failed",
    )

    assert failed.status == AsyncJobStatus.FAILED
    assert failed.error_code == "PROVIDER_ERROR"
    assert store.claim_next("worker-b", NOW + timedelta(seconds=2)) is None


def test_running_job_times_out_after_missed_heartbeat() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="job_scan_3",
                tenant_id="tenant_1",
                job_type="scan",
                scheduled_at=NOW,
                timeout_seconds=30,
            )
        ]
    )

    store.claim_next("worker-a", NOW)
    timed_out = store.sweep_timeouts(NOW + timedelta(seconds=31))

    assert [job.id for job in timed_out] == ["job_scan_3"]
    stored = store.get("job_scan_3")
    assert stored.status == AsyncJobStatus.TIMEOUT
    assert stored.error_code == "JOB_TIMEOUT"
    assert store.claim_next("worker-b", NOW + timedelta(seconds=32)) is None


def test_only_lock_owner_can_mutate_running_job() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="job_scan_4",
                tenant_id="tenant_1",
                job_type="scan",
                scheduled_at=NOW,
            )
        ]
    )

    store.claim_next("worker-a", NOW)

    with pytest.raises(JobOwnershipError):
        store.heartbeat("job_scan_4", "worker-b", NOW + timedelta(seconds=5))

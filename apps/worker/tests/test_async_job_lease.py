from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from airank_domain import AsyncJob, AsyncJobStatus, JobOwnershipError
from airank_worker import InMemoryJobLeaseStore, MySQLJobLeaseStore
from airank_worker.lease import coerce_datetime


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


def test_exhausted_job_uses_registered_error_code() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="job_scan_5",
                tenant_id="tenant_1",
                job_type="scan",
                scheduled_at=NOW,
                attempt_count=3,
                max_attempts=3,
            )
        ]
    )

    exhausted = store.claim_next("worker-a", NOW)

    assert exhausted is not None
    assert exhausted.status == AsyncJobStatus.FAILED
    assert exhausted.error_code == "JOB_MAX_ATTEMPTS_EXCEEDED"


def test_claim_can_be_limited_to_handler_job_types() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(id="job_scan_first", tenant_id="tenant_1", job_type="scan.provider", priority=1, scheduled_at=NOW),
            AsyncJob(id="job_publish_second", tenant_id="tenant_1", job_type="publish.package", priority=2, scheduled_at=NOW),
        ]
    )

    claimed = store.claim_next("publisher", NOW, job_types={"publish.package"})

    assert claimed is not None
    assert claimed.id == "job_publish_second"
    assert store.get("job_scan_first").status == AsyncJobStatus.QUEUED


def test_in_memory_claim_can_be_deferred_without_spending_an_attempt() -> None:
    store = InMemoryJobLeaseStore(
        [AsyncJob(id="job_defer", tenant_id="tenant_1", job_type="scan.provider", scheduled_at=NOW)]
    )
    store.claim_next("worker-a", NOW)

    deferred = store.defer_claim("job_defer", "worker-a", NOW, delay_seconds=5)

    assert deferred.status == AsyncJobStatus.QUEUED
    assert deferred.attempt_count == 0
    assert deferred.scheduled_at == NOW + timedelta(seconds=5)
    assert store.claim_next("worker-b", NOW + timedelta(seconds=4)) is None
    assert store.claim_next("worker-b", NOW + timedelta(seconds=5)) is not None


def create_mysql_lease_table(store: MySQLJobLeaseStore) -> None:
    with store._engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_async_jobs (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NULL,
                  job_type VARCHAR(64) NOT NULL,
                  status VARCHAR(32) NOT NULL,
                  priority INT NOT NULL,
                  scheduled_at DATETIME NOT NULL,
                  locked_by VARCHAR(128) NULL,
                  locked_at DATETIME NULL,
                  heartbeat_at DATETIME NULL,
                  timeout_seconds INT NOT NULL,
                  attempt_count INT NOT NULL,
                  max_attempts INT NOT NULL,
                  payload_json TEXT NULL,
                  result_json TEXT NULL,
                  error_code VARCHAR(128) NULL,
                  error_message TEXT NULL,
                  started_at DATETIME NULL,
                  finished_at DATETIME NULL,
                  created_at DATETIME NOT NULL,
                  updated_at DATETIME NOT NULL
                )
                """
            )
        )


def test_mysql_lease_store_claim_heartbeat_and_succeed_job() -> None:
    store = MySQLJobLeaseStore("sqlite+pysqlite:///:memory:")
    create_mysql_lease_table(store)
    store.add(
        AsyncJob(
            id="job_db_1",
            tenant_id="tenant_1",
            project_id="project_1",
            job_type="scan.provider",
            priority=10,
            scheduled_at=NOW,
            payload={"provider": "chatgpt"},
        )
    )

    claimed = store.claim_next("worker-db", NOW)
    assert claimed is not None
    assert claimed.status == AsyncJobStatus.RUNNING
    assert claimed.locked_by == "worker-db"
    assert claimed.attempt_count == 1
    assert claimed.payload == {"provider": "chatgpt"}

    heartbeat_at = NOW + timedelta(seconds=10)
    heartbeat = store.heartbeat("job_db_1", "worker-db", heartbeat_at)
    assert heartbeat.heartbeat_at == heartbeat_at

    finished = store.succeed("job_db_1", "worker-db", heartbeat_at, {"snapshots": 1})
    assert finished.status == AsyncJobStatus.SUCCEEDED
    assert finished.result == {"snapshots": 1}
    assert store.get("job_db_1").status == AsyncJobStatus.SUCCEEDED
    assert store.claim_next("worker-other", heartbeat_at) is None


def test_mysql_lease_store_sweeps_timeouts_and_retries_explicitly() -> None:
    store = MySQLJobLeaseStore("sqlite+pysqlite:///:memory:")
    create_mysql_lease_table(store)
    store.add(
        AsyncJob(
            id="job_db_timeout",
            tenant_id="tenant_1",
            job_type="scan.provider",
            scheduled_at=NOW,
            timeout_seconds=30,
        )
    )

    store.claim_next("worker-db", NOW)
    timed_out = store.sweep_timeouts(NOW + timedelta(seconds=31))
    assert [job.id for job in timed_out] == ["job_db_timeout"]
    assert store.get("job_db_timeout").status == AsyncJobStatus.TIMEOUT

    retried = store.requeue_for_retry("job_db_timeout", NOW + timedelta(seconds=40))
    assert retried.status == AsyncJobStatus.QUEUED
    assert retried.locked_by is None
    assert store.claim_next("worker-db-2", NOW + timedelta(seconds=40)) is not None


def test_mysql_lease_store_preserves_owner_checks() -> None:
    store = MySQLJobLeaseStore("sqlite+pysqlite:///:memory:")
    create_mysql_lease_table(store)
    store.add(AsyncJob(id="job_db_owner", tenant_id="tenant_1", job_type="scan.provider", scheduled_at=NOW))

    store.claim_next("worker-a", NOW)

    with pytest.raises(JobOwnershipError):
        store.succeed("job_db_owner", "worker-b", NOW + timedelta(seconds=1), None)


def test_mysql_lease_store_filters_job_type_before_claim() -> None:
    store = MySQLJobLeaseStore("sqlite+pysqlite:///:memory:")
    create_mysql_lease_table(store)
    store.add(AsyncJob(id="job_db_scan", tenant_id="tenant_1", job_type="scan.provider", priority=1, scheduled_at=NOW))
    store.add(AsyncJob(id="job_db_publish", tenant_id="tenant_1", job_type="publish.package", priority=2, scheduled_at=NOW))

    claimed = store.claim_next("publisher", NOW, job_types={"publish.package"})

    assert claimed is not None
    assert claimed.id == "job_db_publish"
    assert store.get("job_db_scan").status == AsyncJobStatus.QUEUED


def test_mysql_lease_store_defers_redundant_claim_without_spending_attempt() -> None:
    store = MySQLJobLeaseStore("sqlite+pysqlite:///:memory:")
    create_mysql_lease_table(store)
    store.add(AsyncJob(id="job_db_defer", tenant_id="tenant_1", job_type="scan.provider", scheduled_at=NOW))
    store.claim_next("worker-a", NOW)

    deferred = store.defer_claim("job_db_defer", "worker-a", NOW, delay_seconds=5)

    assert deferred.status == AsyncJobStatus.QUEUED
    assert deferred.attempt_count == 0
    assert deferred.locked_by is None
    assert store.claim_next("worker-b", NOW + timedelta(seconds=4)) is None
    claimed_again = store.claim_next("worker-b", NOW + timedelta(seconds=5))
    assert claimed_again is not None
    assert claimed_again.attempt_count == 1


def test_mysql_datetime_coercion_normalizes_naive_values_to_utc() -> None:
    coerced = coerce_datetime(datetime(2026, 5, 17, 8, 0))

    assert coerced.tzinfo == timezone.utc
    assert coerced <= NOW

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))

from airank_domain import AsyncJob, AsyncJobStatus  # noqa: E402
from airank_worker import InMemoryJobLeaseStore  # noqa: E402


def test_async_job_lifecycle_acceptance() -> None:
    now = datetime(2026, 5, 17, 8, 0, tzinfo=timezone.utc)
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="job_acceptance_scan",
                tenant_id="tenant_demo",
                project_id="project_demo",
                job_type="scan",
                scheduled_at=now,
                timeout_seconds=10,
            ),
            AsyncJob(
                id="job_acceptance_timeout",
                tenant_id="tenant_demo",
                project_id="project_demo",
                job_type="scan",
                scheduled_at=now,
                timeout_seconds=5,
            ),
        ]
    )

    first = store.claim_next("worker-demo", now)
    assert first is not None
    assert first.status == AsyncJobStatus.RUNNING
    store.heartbeat(first.id, "worker-demo", now + timedelta(seconds=2))
    succeeded = store.succeed(first.id, "worker-demo", now + timedelta(seconds=3))
    assert succeeded.status == AsyncJobStatus.SUCCEEDED

    second = store.claim_next("worker-demo", now + timedelta(seconds=3))
    assert second is not None
    timed_out = store.sweep_timeouts(now + timedelta(seconds=9))
    assert [job.id for job in timed_out] == [second.id]
    assert store.get(second.id).status == AsyncJobStatus.TIMEOUT

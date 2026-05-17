from __future__ import annotations

from datetime import datetime

from airank_evidence import AnswerSnapshot, MockAnswerProvider, ProviderPayloadError

from .lease import InMemoryJobLeaseStore


def run_next_mock_scan_job(
    store: InMemoryJobLeaseStore,
    provider: MockAnswerProvider,
    *,
    worker_id: str,
    now: datetime,
) -> AnswerSnapshot | None:
    job = store.claim_next(worker_id, now)
    if job is None:
        return None
    try:
        snapshot = provider.answer(
            job.payload or {},
            tenant_id=job.tenant_id,
            project_id=job.project_id or str((job.payload or {}).get("project_id") or ""),
            task_id=job.id,
            created_at=now,
        )
    except ProviderPayloadError as exc:
        store.fail(job.id, worker_id, now, "FACT_SOURCE_REQUIRED", str(exc))
        raise
    except Exception as exc:
        store.fail(job.id, worker_id, now, "SCAN_PROVIDER_BLOCKED", str(exc))
        raise

    store.succeed(
        job.id,
        worker_id,
        now,
        {
            "snapshot": snapshot.to_record(),
            "citations": [citation.to_record() for citation in snapshot.citations],
        },
    )
    return snapshot

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_domain import AsyncJob, AsyncJobStatus
from airank_evidence import MockAnswerProvider, ProviderPayloadError
from airank_worker import InMemoryJobLeaseStore
from airank_worker.scan import run_next_mock_scan_job


NOW = datetime(2026, 5, 17, 9, 0, tzinfo=timezone.utc)


def test_mock_scan_job_generates_snapshot_and_citation() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="task_1",
                tenant_id="tenant_1",
                project_id="project_1",
                job_type="scan.mock",
                scheduled_at=NOW,
                payload={
                    "run_id": "run_1",
                    "question_id": "question_1",
                    "question_text": "Which vendor is best for AI search visibility?",
                    "answer_text": "AIRank is visible in AI answers when evidence is cited.",
                    "brand_mentioned": True,
                    "brand_rank": 1,
                    "citations": [
                        {
                            "title": "AIRank evidence page",
                            "url": "https://example.com/airank/evidence",
                            "cited_text": "AIRank publishes cited evidence for AI answers.",
                            "relevance_score": 0.98,
                        }
                    ],
                },
            )
        ]
    )

    snapshot = run_next_mock_scan_job(
        store,
        MockAnswerProvider(),
        worker_id="worker-a",
        now=NOW,
    )

    assert snapshot is not None
    assert snapshot.id == "snap_task_1"
    assert snapshot.citations[0].snapshot_id == snapshot.id
    assert snapshot.citations[0].host == "example.com"
    stored = store.get("task_1")
    assert stored.status == AsyncJobStatus.SUCCEEDED
    assert stored.result is not None
    assert stored.result["snapshot"]["id"] == "snap_task_1"
    assert stored.result["citations"][0]["id"] == "cite_snap_task_1_1"


def test_mock_scan_job_fails_without_citation_and_does_not_requeue() -> None:
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="task_missing_citation",
                tenant_id="tenant_1",
                project_id="project_1",
                job_type="scan.mock",
                scheduled_at=NOW,
                payload={
                    "run_id": "run_1",
                    "question_id": "question_1",
                    "question_text": "Which vendor is best?",
                    "answer_text": "AIRank is mentioned, but no source is present.",
                    "citations": [],
                },
            )
        ]
    )

    with pytest.raises(ProviderPayloadError):
        run_next_mock_scan_job(
            store,
            MockAnswerProvider(),
            worker_id="worker-a",
            now=NOW,
        )

    stored = store.get("task_missing_citation")
    assert stored.status == AsyncJobStatus.FAILED
    assert stored.error_code == "ProviderPayloadError"
    assert store.claim_next("worker-b", NOW) is None

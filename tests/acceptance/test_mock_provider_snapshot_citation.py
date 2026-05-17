from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "evidence" / "src"))

from airank_domain import AsyncJob, AsyncJobStatus  # noqa: E402
from airank_evidence import MockAnswerProvider  # noqa: E402
from airank_worker import InMemoryJobLeaseStore  # noqa: E402
from airank_worker.scan import run_next_mock_scan_job  # noqa: E402


def test_mock_provider_snapshot_citation_acceptance() -> None:
    now = datetime(2026, 5, 17, 9, 30, tzinfo=timezone.utc)
    store = InMemoryJobLeaseStore(
        [
            AsyncJob(
                id="task_acceptance_mock",
                tenant_id="tenant_demo",
                project_id="project_demo",
                job_type="scan.mock",
                scheduled_at=now,
                payload={
                    "run_id": "run_demo",
                    "question_id": "question_demo",
                    "question_text": "Can AIRank prove AI answer visibility?",
                    "answer_text": "AIRank can prove visibility when every answer has citations.",
                    "brand_mentioned": True,
                    "brand_rank": 1,
                    "citations": [
                        {
                            "title": "Visibility evidence",
                            "url": "https://example.com/visibility",
                            "cited_text": "Evidence must be linked to every answer snapshot.",
                        }
                    ],
                },
            )
        ]
    )

    snapshot = run_next_mock_scan_job(
        store,
        MockAnswerProvider(),
        worker_id="worker-demo",
        now=now,
    )

    assert snapshot is not None
    assert snapshot.citations
    assert snapshot.citations[0].url == "https://example.com/visibility"
    assert store.get("task_acceptance_mock").status == AsyncJobStatus.SUCCEEDED

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "evidence" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "score" / "src"))

from airank_evidence import AnswerSnapshot, SourceCitation  # noqa: E402
from airank_score import calculate_airank_score  # noqa: E402
from apps.api.main import app  # noqa: E402


def test_project_scan_to_score_acceptance_chain() -> None:
    client = TestClient(app)
    headers = {"tenant-id": "tenant_acceptance", "X-AIRank-Trace-Id": "trc_scan_score_acceptance"}

    project = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"website_url": "www.example.com", "brand_name_hint": "ExampleTech"},
    )
    assert project.status_code == 201
    project_id = project.json()["data"]["project_id"]

    question = client.post(
        f"/api/v1/projects/{project_id}/buyer-questions",
        headers=headers,
        json={
            "question_text": "How should a buyer compare AI visibility platforms?",
            "question_type": "compare",
            "recommended_providers": ["chatgpt"],
        },
    )
    assert question.status_code == 201
    question_id = question.json()["data"]["question_id"]

    scan_run = client.post(
        "/api/v1/scan-runs",
        headers=headers,
        json={
            "project_id": project_id,
            "provider_scope": ["chatgpt"],
            "question_scope": {"mode": "selected", "question_ids": [question_id]},
        },
    )
    assert scan_run.status_code == 201
    run_id = scan_run.json()["data"]["run_id"]

    tasks = client.get(f"/api/v1/scan-runs/{run_id}/tasks", headers=headers)
    assert tasks.status_code == 200
    task_id = tasks.json()["data"][0]["task_id"]

    created_at = datetime(2026, 5, 17, 14, 30, tzinfo=timezone.utc)
    citation = SourceCitation(
        id="cite_scan_score_acceptance",
        tenant_id="tenant_acceptance",
        project_id=project_id,
        snapshot_id="snap_scan_score_acceptance",
        citation_order=1,
        title="Score source",
        url="https://example.com/score-source",
        host="example.com",
        source_type="web",
        cited_text="The answer includes a source-backed brand recommendation.",
        created_at=created_at,
    )
    snapshot = AnswerSnapshot(
        id="snap_scan_score_acceptance",
        tenant_id="tenant_acceptance",
        project_id=project_id,
        run_id=run_id,
        task_id=task_id,
        question_id=question_id,
        question_text="How should a buyer compare AI visibility platforms?",
        provider="chatgpt",
        answer_text="ExampleTech is recommended with cited evidence.",
        citations=(citation,),
        brand_mentioned=True,
        brand_rank=1,
        created_at=created_at,
    )

    score = calculate_airank_score(snapshot)
    assert score.snapshot_id == snapshot.id
    assert score.total > 0
    assert "cite_scan_score_acceptance" in score.components[0].evidence_refs

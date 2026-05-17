from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "evidence" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "score" / "src"))

from airank_evidence import AnswerSnapshot, SourceCitation  # noqa: E402
from airank_score import calculate_airank_score  # noqa: E402


def test_score_pure_function_acceptance() -> None:
    created_at = datetime(2026, 5, 17, 10, 30, tzinfo=timezone.utc)
    citation = SourceCitation(
        id="cite_score_acceptance",
        tenant_id="tenant_demo",
        project_id="project_demo",
        snapshot_id="snap_score_acceptance",
        citation_order=1,
        title="Score evidence",
        url="https://example.com/score",
        host="example.com",
        source_type="web",
        cited_text="Scoring uses cited answer snapshots.",
        created_at=created_at,
    )
    snapshot = AnswerSnapshot(
        id="snap_score_acceptance",
        tenant_id="tenant_demo",
        project_id="project_demo",
        run_id="run_demo",
        task_id="task_demo",
        question_id="question_demo",
        question_text="Can score be repeated?",
        provider="mock",
        answer_text="The score is repeatable when the input evidence is identical.",
        citations=(citation,),
        brand_mentioned=True,
        brand_rank=1,
        created_at=created_at,
    )

    first = calculate_airank_score(snapshot)
    second = calculate_airank_score(snapshot)

    assert first == second
    assert first.snapshot_id == snapshot.id
    assert "cite_score_acceptance" in first.components[0].evidence_refs

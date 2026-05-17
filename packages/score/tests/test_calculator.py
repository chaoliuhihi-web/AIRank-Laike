from __future__ import annotations

from datetime import datetime, timezone

from airank_evidence import AnswerSnapshot, SourceCitation
from airank_score import calculate_airank_score


def build_snapshot() -> AnswerSnapshot:
    created_at = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    citation = SourceCitation(
        id="cite_1",
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snap_1",
        citation_order=1,
        title="Evidence",
        url="https://example.com/evidence",
        host="example.com",
        source_type="web",
        cited_text="AIRank evidence exists.",
        created_at=created_at,
    )
    return AnswerSnapshot(
        id="snap_1",
        tenant_id="tenant_1",
        project_id="project_1",
        run_id="run_1",
        task_id="task_1",
        question_id="question_1",
        question_text="Can AIRank prove visibility?",
        provider="mock",
        answer_text="AIRank is cited.",
        citations=(citation,),
        brand_mentioned=True,
        brand_rank=1,
        created_at=created_at,
    )


def test_score_is_pure_for_same_snapshot_and_citations() -> None:
    snapshot = build_snapshot()

    first = calculate_airank_score(snapshot)
    second = calculate_airank_score(snapshot)

    assert first == second
    assert first.total == 47.5
    assert first.to_record() == second.to_record()
    assert first.components[0].evidence_refs == ("snap_1", "cite_1")


def test_score_marks_missing_future_inputs_as_pending() -> None:
    result = calculate_airank_score(build_snapshot())

    pending = {component.key: component.reason for component in result.components if component.points == 0}
    assert pending == {
        "competitor_suppression": "pending_input",
        "fact_consistency": "pending_input",
        "purchase_intent_coverage": "pending_input",
        "answer_stability": "pending_input",
    }

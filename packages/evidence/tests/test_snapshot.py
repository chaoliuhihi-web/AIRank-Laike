from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_evidence import AnswerSnapshot, SourceCitation


NOW = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)


def build_citation(
    *,
    tenant_id: str = "tenant_1",
    project_id: str = "project_1",
    snapshot_id: str = "snap_1",
) -> SourceCitation:
    return SourceCitation(
        id="cite_snapshot_1",
        tenant_id=tenant_id,
        project_id=project_id,
        snapshot_id=snapshot_id,
        citation_order=1,
        title="Snapshot evidence",
        url="https://example.com/snapshot",
        host="example.com",
        source_type="web",
        cited_text="Snapshot citations must belong to the same evidence chain.",
        created_at=NOW,
    )


def test_answer_snapshot_rejects_mismatched_citation_chain() -> None:
    with pytest.raises(ValueError, match="snapshot_id"):
        AnswerSnapshot(
            id="snap_1",
            tenant_id="tenant_1",
            project_id="project_1",
            run_id="run_1",
            task_id="task_1",
            question_id="question_1",
            question_text="Can mismatched citations be accepted?",
            provider="mock",
            answer_text="No.",
            citations=(build_citation(snapshot_id="snap_other"),),
            created_at=NOW,
        )


def test_answer_snapshot_rejects_invalid_brand_rank() -> None:
    with pytest.raises(ValueError, match="brand_rank"):
        AnswerSnapshot(
            id="snap_1",
            tenant_id="tenant_1",
            project_id="project_1",
            run_id="run_1",
            task_id="task_1",
            question_id="question_1",
            question_text="Can rank zero score?",
            provider="mock",
            answer_text="No.",
            citations=(build_citation(),),
            brand_mentioned=True,
            brand_rank=0,
            created_at=NOW,
        )


def test_valid_not_mentioned_snapshot_can_be_saved_without_citations() -> None:
    snapshot = AnswerSnapshot(
        id="snap_not_mentioned",
        tenant_id="tenant_1",
        project_id="project_1",
        run_id="run_1",
        task_id="task_1",
        question_id="question_1",
        question_text="有哪些企业级 GEO 工具？",
        provider="qianwen",
        answer_text="可以考虑甲平台和乙平台。",
        citations=(),
        created_at=NOW,
    )

    assert snapshot.brand_mentioned is False
    assert snapshot.mention_class.value == "not_mentioned"
    assert snapshot.answer_sha256
    assert snapshot.to_record()["citation_ids"] == []

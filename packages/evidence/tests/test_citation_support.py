from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from airank_evidence import (
    CitationClaim,
    CitationSupportEvidenceGrade,
    CitationSupportLabel,
    CitationSupportReview,
    calculate_citation_support_metrics,
)


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)
ANSWER = "AIRank 提供可追溯的证据链，但不承诺发布后一定被模型推荐。"


def claim() -> CitationClaim:
    return CitationClaim.from_answer(
        id="claim_1",
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snapshot_1",
        answer_text=ANSWER,
        answer_start=0,
        answer_end=15,
        created_by="reviewer_1",
        created_at=NOW,
    )


def review(
    *,
    review_id: str,
    label: CitationSupportLabel,
    grade: CitationSupportEvidenceGrade,
    reviewed_at: datetime = NOW,
) -> CitationSupportReview:
    return CitationSupportReview(
        id=review_id,
        tenant_id="tenant_1",
        project_id="project_1",
        claim_id="claim_1",
        citation_id="citation_1",
        label=label,
        evidence_grade=grade,
        source_excerpt="产品文档说明每条结论都可以回到原始样本。",
        source_content_sha256="a" * 64,
        source_object_ref_id="object_1" if grade == CitationSupportEvidenceGrade.SOURCE_PAGE_SNAPSHOT else None,
        rationale="来源原文与回答断言直接对应。",
        review_method="human",
        reviewed_by="reviewer_2",
        reviewed_at=reviewed_at,
    )


def test_claim_boundary_and_answer_hash_are_immutable() -> None:
    item = claim()
    assert item.claim_text == ANSWER[0:15]
    assert item.verify_answer(ANSWER) is True
    assert item.verify_answer(f"{ANSWER}。") is False
    with pytest.raises(ValueError, match="boundary"):
        CitationClaim.from_answer(
            id="bad",
            tenant_id="tenant_1",
            project_id="project_1",
            snapshot_id="snapshot_1",
            answer_text=ANSWER,
            answer_start=-1,
            answer_end=4,
            created_by="reviewer_1",
            created_at=NOW,
        )


def test_provider_excerpt_review_is_provisional_and_not_scored() -> None:
    metrics = calculate_citation_support_metrics(
        selected_citation_ids=("citation_1",),
        claims=(claim(),),
        reviews=(
            review(
                review_id="review_1",
                label=CitationSupportLabel.SUPPORTS,
                grade=CitationSupportEvidenceGrade.PROVIDER_EXCERPT_ONLY,
            ),
        ),
    )
    assert metrics.selected_citation_count == 1
    assert metrics.review_count == 1
    assert metrics.commercially_verified_review_count == 0
    assert metrics.citation_support_rate is None
    assert "citation_support_has_no_source_page_snapshot" in metrics.known_limitations


def test_latest_source_page_review_drives_support_rate_without_overwriting_history() -> None:
    metrics = calculate_citation_support_metrics(
        selected_citation_ids=("citation_1",),
        claims=(claim(),),
        reviews=(
            review(
                review_id="review_old",
                label=CitationSupportLabel.INSUFFICIENT,
                grade=CitationSupportEvidenceGrade.SOURCE_PAGE_SNAPSHOT,
            ),
            review(
                review_id="review_new",
                label=CitationSupportLabel.SUPPORTS,
                grade=CitationSupportEvidenceGrade.SOURCE_PAGE_SNAPSHOT,
                reviewed_at=NOW + timedelta(minutes=1),
            ),
        ),
    )
    assert metrics.review_count == 1
    assert metrics.commercially_verified_review_count == 1
    assert metrics.supports_count == 1
    assert metrics.insufficient_count == 0
    assert metrics.citation_support_rate == 1.0


def test_unknown_claim_or_unselected_citation_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown claim"):
        calculate_citation_support_metrics(
            selected_citation_ids=("citation_1",),
            claims=(),
            reviews=(
                review(
                    review_id="review_1",
                    label=CitationSupportLabel.SUPPORTS,
                    grade=CitationSupportEvidenceGrade.SOURCE_PAGE_SNAPSHOT,
                ),
            ),
        )

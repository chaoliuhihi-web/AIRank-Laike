from __future__ import annotations

from datetime import datetime, timezone

from airank_evidence import (
    AnswerClaimKind,
    FactAccuracyClaim,
    FactAccuracyEvidenceGrade,
    FactAccuracyReview,
    FactAccuracyVerdict,
    calculate_fact_accuracy_metrics,
)


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def claim(claim_id: str, kind: AnswerClaimKind = AnswerClaimKind.BRAND_FACT) -> FactAccuracyClaim:
    return FactAccuracyClaim(
        id=claim_id,
        snapshot_id="snapshot_1",
        claim_kind=kind,
        claim_text="AIRank 支持多平台重复采样。",
        claim_sha256="a" * 64,
        answer_start=0,
        answer_end=17,
        subject_entity_text="AIRank",
    )


def review(
    review_id: str,
    claim_id: str,
    verdict: FactAccuracyVerdict,
    *,
    current: bool = True,
    method: str = "human",
) -> FactAccuracyReview:
    return FactAccuracyReview(
        id=review_id,
        claim_id=claim_id,
        verdict=verdict,
        evidence_grade=FactAccuracyEvidenceGrade.APPROVED_FACT_SOURCE_BOUNDARY,
        rationale="人工核对审核事实与原始来源边界。",
        review_method=method,
        reviewed_by="reviewer_1",
        reviewed_at=NOW,
        fact_revision_id="factrev_1",
        knowledge_source_id="source_1",
        knowledge_segment_id="segment_1",
        fact_revision_sha256="b" * 64,
        source_content_sha256="c" * 64,
        quoted_text_sha256="d" * 64,
        source_start=0,
        source_end=17,
        fact_revision_current=current,
        source_current=True,
        no_open_conflict=True,
        exact_boundary_verified=True,
    )


def test_fact_accuracy_requires_complete_decisive_claim_coverage() -> None:
    metrics = calculate_fact_accuracy_metrics(
        claims=(claim("claim_1"), claim("claim_2")),
        reviews=(review("review_1", "claim_1", FactAccuracyVerdict.ACCURATE),),
    )

    assert metrics.evaluation_coverage_rate == 0.5
    assert metrics.fact_accuracy is None
    assert "fact_claims_unreviewed" in metrics.known_limitations
    assert "fact_accuracy_incomplete_coverage" in metrics.known_limitations


def test_fact_accuracy_counts_accurate_inaccurate_and_outdated_decisions() -> None:
    metrics = calculate_fact_accuracy_metrics(
        claims=(claim("claim_1"), claim("claim_2"), claim("claim_3")),
        reviews=(
            review("review_1", "claim_1", FactAccuracyVerdict.ACCURATE),
            review("review_2", "claim_2", FactAccuracyVerdict.INACCURATE),
            review("review_3", "claim_3", FactAccuracyVerdict.OUTDATED),
        ),
    )

    assert metrics.evaluation_coverage_rate == 1.0
    assert metrics.fact_accuracy == 0.333333
    assert metrics.accurate_count == 1
    assert metrics.inaccurate_count == 1
    assert metrics.outdated_count == 1
    assert metrics.known_limitations == ()


def test_stale_or_ai_assisted_reviews_never_enter_commercial_accuracy() -> None:
    metrics = calculate_fact_accuracy_metrics(
        claims=(claim("claim_1"), claim("claim_2")),
        reviews=(
            review(
                "review_1",
                "claim_1",
                FactAccuracyVerdict.ACCURATE,
                current=False,
            ),
            review(
                "review_2",
                "claim_2",
                FactAccuracyVerdict.ACCURATE,
                method="ai_assisted",
            ),
        ),
    )

    assert metrics.commercially_verified_claim_count == 0
    assert metrics.fact_accuracy is None
    assert "provisional_or_stale_fact_reviews_excluded" in metrics.known_limitations


def test_insufficient_evidence_is_recorded_but_not_scored_as_inaccurate() -> None:
    insufficient = FactAccuracyReview(
        id="review_1",
        claim_id="claim_1",
        verdict=FactAccuracyVerdict.INSUFFICIENT_EVIDENCE,
        evidence_grade=FactAccuracyEvidenceGrade.NO_APPROVED_FACT,
        rationale="企业事实库没有可核验的审核事实。",
        review_method="human",
        reviewed_by="reviewer_1",
        reviewed_at=NOW,
    )
    metrics = calculate_fact_accuracy_metrics(
        claims=(claim("claim_1"),),
        reviews=(insufficient,),
    )

    assert metrics.insufficient_evidence_count == 1
    assert metrics.fact_accuracy is None
    assert "fact_accuracy_contains_insufficient_evidence" in metrics.known_limitations


def test_opinion_claims_are_excluded_from_fact_accuracy_denominator() -> None:
    metrics = calculate_fact_accuracy_metrics(
        claims=(claim("claim_1", AnswerClaimKind.OPINION),),
        reviews=(),
    )

    assert metrics.registered_claim_count == 1
    assert metrics.factual_claim_count == 0
    assert metrics.fact_accuracy is None
    assert metrics.known_limitations == ("fact_claims_not_registered",)

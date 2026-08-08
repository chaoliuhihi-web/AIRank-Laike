from __future__ import annotations

from datetime import datetime, timezone

from airank_domain.measurement import (
    CollectorSurface,
    EvidenceLevel,
    MeasurementSample,
    MentionClass,
    PromptCohortType,
    SampleContext,
    SampleStatus,
)
from airank_score import calculate_cohort_metrics


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def context(sample_index: int) -> SampleContext:
    return SampleContext(
        prompt_version_id="prompt_v_test",
        cohort_type=PromptCohortType.BLIND,
        sample_index=sample_index,
        session_id=f"session_{sample_index}",
        surface=CollectorSurface.API,
        evidence_level=EvidenceLevel.PROVIDER_API,
        provider="qianwen",
        captured_at=NOW,
    )


def test_not_mentioned_is_kept_in_effective_denominator() -> None:
    samples = [
        MeasurementSample(
            sample_id="sample_1",
            question_id="question_1",
            context=context(1),
            status=SampleStatus.VALID,
            answer_text="推荐 AIRank。",
            mention_class=MentionClass.RECOMMENDED,
            brand_rank=1,
            citation_count=1,
            citation_support_score=1.0,
        ),
        MeasurementSample(
            sample_id="sample_2",
            question_id="question_1",
            context=context(2),
            status=SampleStatus.VALID,
            answer_text="推荐另外两个工具。",
            mention_class=MentionClass.NOT_MENTIONED,
        ),
        MeasurementSample(
            sample_id="sample_3",
            question_id="question_1",
            context=context(3),
            status=SampleStatus.BLOCKED,
            failure_code="PROVIDER_AUTH_BLOCKED",
        ),
    ]

    metrics = calculate_cohort_metrics(samples)

    assert metrics.total_sample_count == 3
    assert metrics.valid_sample_count == 2
    assert metrics.blocked_sample_count == 1
    assert metrics.not_mentioned_count == 1
    assert metrics.mention_rate == 0.5
    assert metrics.recommendation_rate == 0.5
    assert metrics.top1_rate == 0.5
    assert metrics.citation_recall_rate == 0.5
    assert metrics.stability == 0.5


def test_failed_and_blocked_samples_are_not_effective_answers() -> None:
    samples = [
        MeasurementSample(
            sample_id="sample_failed",
            question_id="question_1",
            context=context(1),
            status=SampleStatus.FAILED,
            failure_code="PROVIDER_TIMEOUT",
        ),
        MeasurementSample(
            sample_id="sample_blocked",
            question_id="question_1",
            context=context(2),
            status=SampleStatus.BLOCKED,
            failure_code="PROVIDER_LOGIN_REQUIRED",
        ),
    ]

    metrics = calculate_cohort_metrics(samples)

    assert metrics.valid_sample_count == 0
    assert metrics.valid_sample_rate == 0
    assert metrics.mention_rate == 0
    assert metrics.stability is None


def test_fact_accuracy_reports_claim_coverage_separately_from_accuracy() -> None:
    samples = [
        MeasurementSample(
            sample_id="sample_fact_1",
            question_id="question_1",
            context=context(1),
            status=SampleStatus.VALID,
            answer_text="AIRank 支持重复采样。",
            mention_class=MentionClass.MENTIONED,
            fact_claim_count=2,
            fact_reviewed_claim_count=2,
            fact_accuracy=0.5,
        ),
        MeasurementSample(
            sample_id="sample_fact_2",
            question_id="question_1",
            context=context(2),
            status=SampleStatus.VALID,
            answer_text="AIRank 支持证据下钻。",
            mention_class=MentionClass.MENTIONED,
            fact_claim_count=1,
            fact_reviewed_claim_count=0,
        ),
    ]

    metrics = calculate_cohort_metrics(samples)

    assert metrics.fact_claim_count == 3
    assert metrics.fact_reviewed_claim_count == 2
    assert metrics.fact_accuracy_coverage_rate == 0.666667
    assert metrics.fact_accuracy == 0.5

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
from airank_score import build_measurement_quality_report


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def sample(index: int, *, raw_hash: bool = True, status: SampleStatus = SampleStatus.VALID) -> MeasurementSample:
    return MeasurementSample(
        sample_id=f"sample_{index}",
        question_id="question_1",
        context=SampleContext(
            prompt_version_id="prompt_1",
            cohort_type=PromptCohortType.BLIND,
            sample_index=index,
            session_id=f"session_{index}",
            surface=CollectorSurface.API,
            evidence_level=EvidenceLevel.PROVIDER_API,
            provider="qianwen",
            captured_at=NOW,
        ),
        status=status,
        answer_text="本次未发现目标品牌。" if status == SampleStatus.VALID else None,
        raw_response_sha256=(str(index) * 64)[:64] if raw_hash else None,
        mention_class=MentionClass.NOT_MENTIONED if status == SampleStatus.VALID else MentionClass.UNKNOWN,
        failure_code=None if status == SampleStatus.VALID else "provider_timeout",
    )


def test_quality_report_keeps_not_mentioned_in_valid_denominator() -> None:
    samples = tuple(sample(index) for index in range(1, 4))
    signatures = tuple(f"question_1|qianwen|blind|api|{index}" for index in range(1, 4))

    report = build_measurement_quality_report(run_id="run_1", samples=samples, signatures=signatures)

    assert report.publishable is True
    assert report.metrics.valid_sample_count == 3
    assert report.metrics.not_mentioned_count == 3
    assert report.metrics.mention_rate == 0
    assert "valid_samples_have_no_provider_citations" in report.known_limitations
    assert len(report.data_sha256) == 64
    assert len(report.report_sha256) == 64


def test_quality_report_blocks_duplicate_contract_missing_raw_hash_and_low_valid_rate() -> None:
    samples = (
        sample(1, raw_hash=False),
        sample(2, status=SampleStatus.FAILED),
        sample(3, status=SampleStatus.BLOCKED),
    )
    signatures = ("duplicate", "duplicate", "third")

    report = build_measurement_quality_report(run_id="run_bad", samples=samples, signatures=signatures)

    assert report.publishable is False
    blocked = {item.code for item in report.checks if item.status == "blocked"}
    assert blocked >= {"sample_contracts_unique", "raw_response_hashes_present", "valid_sample_rate"}

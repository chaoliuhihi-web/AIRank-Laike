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
from airank_score import SampleEvidenceManifest, build_measurement_quality_report


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


def api_evidence(index: int, *, complete: bool = True) -> SampleEvidenceManifest:
    return SampleEvidenceManifest(
        sample_id=f"sample_{index}",
        surface=CollectorSurface.API,
        evidence_level=EvidenceLevel.PROVIDER_API,
        request_metadata_sha256="a" * 64 if complete else None,
        external_trace_id=f"provider-request-{index}" if complete else None,
        provider_request_audit_id=f"audit-{index}" if complete else None,
    )


def test_quality_report_keeps_not_mentioned_in_valid_denominator() -> None:
    samples = tuple(sample(index) for index in range(1, 4))
    signatures = tuple(f"question_1|qianwen|blind|api|{index}" for index in range(1, 4))

    report = build_measurement_quality_report(
        run_id="run_1",
        samples=samples,
        signatures=signatures,
        evidence_manifests=tuple(api_evidence(index) for index in range(1, 4)),
    )

    assert report.publishable is True
    assert report.metrics.valid_sample_count == 3
    assert report.metrics.not_mentioned_count == 3
    assert report.metrics.mention_rate == 0
    assert "valid_samples_have_no_provider_citations" in report.known_limitations
    assert "fact_claims_not_registered" in report.known_limitations
    assert "fact_accuracy_not_evaluated" in report.known_limitations
    assert len(report.data_sha256) == 64
    assert len(report.report_sha256) == 64
    assert report.surface_evidence[0].evidence_complete_count == 3
    assert report.surface_evidence[0].blocker_count == 0


def test_quality_report_hashes_fact_accuracy_and_exposes_partial_coverage() -> None:
    samples = list(sample(index) for index in range(1, 4))
    samples[0] = MeasurementSample(
        **{
            **samples[0].__dict__,
            "fact_claim_count": 1,
            "fact_reviewed_claim_count": 1,
            "fact_accuracy": 1.0,
        }
    )
    samples[1] = MeasurementSample(
        **{
            **samples[1].__dict__,
            "fact_claim_count": 1,
            "fact_reviewed_claim_count": 0,
        }
    )
    report = build_measurement_quality_report(
        run_id="run_fact_coverage",
        samples=tuple(samples),
        signatures=tuple(
            f"question_1|qianwen|blind|api|{index}" for index in range(1, 4)
        ),
        evidence_manifests=tuple(api_evidence(index) for index in range(1, 4)),
    )

    assert report.metrics.fact_claim_count == 2
    assert report.metrics.fact_reviewed_claim_count == 1
    assert report.metrics.fact_accuracy_coverage_rate == 0.5
    assert report.metrics.fact_accuracy == 1.0
    assert "fact_accuracy_incomplete_coverage" in report.known_limitations


def test_quality_report_blocks_single_sample_even_when_evidence_is_complete() -> None:
    report = build_measurement_quality_report(
        run_id="run_single",
        samples=(sample(1),),
        signatures=("question_1|qianwen|blind|api|1",),
        evidence_manifests=(api_evidence(1),),
    )

    assert report.publishable is False
    repetition_check = next(item for item in report.checks if item.code == "independent_repetitions_complete")
    assert repetition_check.status == "blocked"
    assert repetition_check.actual == 1
    assert "repeat_stability_unavailable" in report.known_limitations


def test_quality_report_keeps_failed_run_auditable_but_non_publishable() -> None:
    report = build_measurement_quality_report(
        run_id="run_failed",
        run_status="failed",
        samples=tuple(sample(index) for index in range(1, 4)),
        signatures=tuple(f"question_1|qianwen|blind|api|{index}" for index in range(1, 4)),
        evidence_manifests=tuple(api_evidence(index) for index in range(1, 4)),
    )

    status_check = next(item for item in report.checks if item.code == "run_status_publishable")
    assert status_check.status == "blocked"
    assert status_check.actual == "failed"
    assert report.publishable is False


def test_quality_report_rejects_reused_session_even_with_three_sample_indexes() -> None:
    reused = tuple(
        MeasurementSample(
            sample_id=f"sample_reused_{index}",
            question_id="question_1",
            context=SampleContext(
                prompt_version_id="prompt_1",
                cohort_type=PromptCohortType.BLIND,
                sample_index=index,
                session_id="session_reused",
                surface=CollectorSurface.API,
                evidence_level=EvidenceLevel.PROVIDER_API,
                provider="qianwen",
                captured_at=NOW,
            ),
            status=SampleStatus.VALID,
            answer_text="本次未发现目标品牌。",
            raw_response_sha256=(str(index) * 64)[:64],
            mention_class=MentionClass.NOT_MENTIONED,
        )
        for index in range(1, 4)
    )
    report = build_measurement_quality_report(
        run_id="run_reused_session",
        samples=reused,
        signatures=tuple(f"question_1|qianwen|blind|api|{index}" for index in range(1, 4)),
        evidence_manifests=tuple(
            SampleEvidenceManifest(
                sample_id=f"sample_reused_{index}",
                surface=CollectorSurface.API,
                evidence_level=EvidenceLevel.PROVIDER_API,
                request_metadata_sha256="a" * 64,
                external_trace_id=f"request-{index}",
                provider_request_audit_id=f"audit-{index}",
            )
            for index in range(1, 4)
        ),
    )

    assert report.publishable is False
    assert next(item for item in report.checks if item.code == "independent_repetitions_complete").status == "blocked"


def test_quality_report_blocks_duplicate_contract_missing_raw_hash_and_low_valid_rate() -> None:
    samples = (
        sample(1, raw_hash=False),
        sample(2, status=SampleStatus.FAILED),
        sample(3, status=SampleStatus.BLOCKED),
    )
    signatures = ("duplicate", "duplicate", "third")

    report = build_measurement_quality_report(
        run_id="run_bad",
        samples=samples,
        signatures=signatures,
        evidence_manifests=(api_evidence(1, complete=False), api_evidence(2), api_evidence(3)),
    )

    assert report.publishable is False
    blocked = {item.code for item in report.checks if item.status == "blocked"}
    assert blocked >= {
        "sample_contracts_unique",
        "raw_response_hashes_present",
        "valid_sample_rate",
        "valid_request_metadata_present",
        "provider_trace_ids_present",
        "api_provider_audits_present",
    }


def test_quality_report_requires_surface_specific_consumer_evidence() -> None:
    answer = "AIRank 可作为候选。"
    web_sample = MeasurementSample(
        sample_id="sample_web",
        question_id="question_web",
        context=SampleContext(
            prompt_version_id="prompt_web",
            cohort_type=PromptCohortType.BLIND,
            sample_index=1,
            session_id="session_web",
            surface=CollectorSurface.WEB,
            evidence_level=EvidenceLevel.CONSUMER_WEB,
            provider="doubao",
            captured_at=NOW,
        ),
        status=SampleStatus.VALID,
        answer_text=answer,
        raw_response_sha256="b" * 64,
        mention_class=MentionClass.CANDIDATE,
        citation_count=1,
    )
    incomplete = SampleEvidenceManifest(
        sample_id="sample_web",
        surface=CollectorSurface.WEB,
        evidence_level=EvidenceLevel.CONSUMER_WEB,
        request_metadata_sha256="c" * 64,
        external_trace_id="browser:doubao:1",
        screenshot_ref_id="object-answer",
        screenshot_sha256="d" * 64,
        screenshot_immutable=True,
        conversation_isolation_verified=True,
        source_panel_status="not_present",
    )

    report = build_measurement_quality_report(
        run_id="run_web",
        samples=(web_sample,),
        signatures=("question_web|doubao|blind|web|1",),
        evidence_manifests=(incomplete,),
    )

    blocked = {item.code for item in report.checks if item.status == "blocked"}
    assert "consumer_screenshots_complete" not in blocked
    assert "consumer_source_panel_evidence_consistent" in blocked
    assert report.surface_evidence[0].blocker_count == 1


def test_quality_report_blocks_consumer_sample_without_verified_conversation_isolation() -> None:
    answer = "本次未发现目标品牌。"
    web_sample = MeasurementSample(
        sample_id="sample_web_unisolated",
        question_id="question_web_unisolated",
        context=SampleContext(
            prompt_version_id="prompt_web_unisolated",
            cohort_type=PromptCohortType.BLIND,
            sample_index=1,
            session_id="session_web_unisolated",
            surface=CollectorSurface.WEB,
            evidence_level=EvidenceLevel.CONSUMER_WEB,
            provider="qianwen",
            captured_at=NOW,
        ),
        status=SampleStatus.VALID,
        answer_text=answer,
        raw_response_sha256="e" * 64,
        mention_class=MentionClass.NOT_MENTIONED,
    )
    manifest = SampleEvidenceManifest(
        sample_id="sample_web_unisolated",
        surface=CollectorSurface.WEB,
        evidence_level=EvidenceLevel.CONSUMER_WEB,
        request_metadata_sha256="f" * 64,
        external_trace_id="browser:qianwen:unisolated",
        screenshot_ref_id="object-answer",
        screenshot_sha256="1" * 64,
        screenshot_immutable=True,
        source_panel_status="not_present",
    )

    report = build_measurement_quality_report(
        run_id="run_web_unisolated",
        samples=(web_sample,),
        signatures=("question_web_unisolated|qianwen|blind|web|1",),
        evidence_manifests=(manifest,),
    )

    isolation = next(
        item for item in report.checks
        if item.code == "consumer_conversation_isolation_verified"
    )
    assert isolation.status == "blocked"
    assert isolation.actual == 1
    assert report.surface_evidence[0].evidence_complete_count == 0

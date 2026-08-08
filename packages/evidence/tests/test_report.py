from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_evidence import (
    EvidenceReport,
    ReportConclusion,
    ReportEvidencePacketError,
    build_report_conclusion,
    build_report_evidence_packet,
)
from airank_evidence.report import canonical_json_sha256


NOW = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)


def test_report_conclusion_requires_full_evidence_chain() -> None:
    with pytest.raises(ValueError, match="snapshot"):
        ReportConclusion(
            id="conclusion_bad",
            title="Unsupported",
            body="Missing snapshot.",
            snapshot_ids=(),
            citation_ids=("cite_1",),
            fact_atom_ids=("fact_1",),
        )

    with pytest.raises(ValueError, match="citation"):
        ReportConclusion(
            id="conclusion_bad",
            title="Unsupported",
            body="Missing citation.",
            snapshot_ids=("snap_1",),
            citation_ids=(),
            fact_atom_ids=("fact_1",),
        )

    with pytest.raises(ValueError, match="FactAtom"):
        ReportConclusion(
            id="conclusion_bad",
            title="Unsupported",
            body="Missing FactAtom.",
            snapshot_ids=("snap_1",),
            citation_ids=("cite_1",),
            fact_atom_ids=(),
        )


def test_evidence_report_json_contains_traceable_conclusion() -> None:
    conclusion = build_report_conclusion(
        id="conclusion_1",
        title="AIRank is cited",
        body="AIRank appeared with cited supporting evidence.",
        snapshot_id="snap_1",
        citation_id="cite_1",
        fact_atom_id="fact_1",
    )
    report = EvidenceReport(
        id="report_1",
        tenant_id="tenant_1",
        project_id="project_1",
        title="AIRank evidence report",
        conclusions=(conclusion,),
        generated_at=NOW,
    )

    payload = report.to_json()
    assert payload["conclusions"][0]["evidence"] == {
        "snapshot_ids": ["snap_1"],
        "citation_ids": ["cite_1"],
        "fact_atom_ids": ["fact_1"],
    }


def publishable_report_record() -> dict:
    quality = {
        "contract_version": "airank.measurement-quality.v4",
        "publishable": True,
        "report_sha256": "1" * 64,
    }
    return {
        "report_id": "report_1",
        "tenant_id": "tenant_1",
        "project_id": "project_1",
        "report_type": "retest",
        "title": "T+7 GEO 复测观察报告",
        "status": "generated",
        "report_sha256": "2" * 64,
        "metrics": {
            "report_status": "generated",
            "baseline_quality": quality,
            "compare_quality": quality,
            "baseline_metrics": {
                "total_sample_count": 1,
                "valid_sample_count": 1,
                "not_mentioned_count": 1,
                "fact_claim_count": 0,
                "fact_reviewed_claim_count": 0,
                "fact_accuracy_coverage_rate": None,
                "fact_accuracy": None,
            },
            "compare_metrics": {
                "total_sample_count": 1,
                "valid_sample_count": 1,
                "not_mentioned_count": 0,
                "fact_claim_count": 0,
                "fact_reviewed_claim_count": 0,
                "fact_accuracy_coverage_rate": None,
                "fact_accuracy": None,
            },
            "metric_deltas": {"mention_rate": 0.083333},
            "known_limitations": ["citation_support_not_evaluated"],
            "attribution_policy": "observational_non_causal.v1",
            "confidence": "medium",
            "conclusion": "观察到提及率变化，不能证明因果。",
        },
        "evidence_index": {
            "baseline_run_id": "scan_baseline",
            "compare_run_id": "scan_compare",
            "evidence_refs": ["scan_run:scan_baseline", "scan_run:scan_compare"],
        },
        "generated_by": "user_1",
        "generated_at": "2026-08-08T12:00:00+00:00",
    }


def test_report_evidence_packet_is_deterministic_and_includes_customer_audit_fields() -> None:
    sample_index = [
        {
            "task_id": "task_1",
            "run_id": "scan_baseline",
            "snapshot_id": "snap_1",
            "sample_status": "valid",
            "mention_class": "not_mentioned",
            "answer_sha256": "3" * 64,
            "raw_response_sha256": "5" * 64,
            "evidence_snapshot_id": "evidence_1",
            "collector_surface": "web",
        },
        {
            "task_id": "task_2",
            "run_id": "scan_compare",
            "snapshot_id": "snap_2",
            "sample_status": "valid",
            "mention_class": "recommended",
            "answer_sha256": "6" * 64,
            "raw_response_sha256": "7" * 64,
            "evidence_snapshot_id": "evidence_2",
            "collector_surface": "web",
        },
    ]
    citation_index = [{"citation_id": "cite_1", "snapshot_id": "snap_1", "url": "https://example.com"}]
    object_index = [{"object_ref_id": "object_1", "sha256": "4" * 64, "byte_size": 123}]

    first = build_report_evidence_packet(
        report_record=publishable_report_record(),
        sample_index=sample_index,
        citation_index=citation_index,
        fact_accuracy_index=[],
        evidence_object_index=object_index,
    )
    replay = build_report_evidence_packet(
        report_record=publishable_report_record(),
        sample_index=sample_index,
        citation_index=citation_index,
        fact_accuracy_index=[],
        evidence_object_index=object_index,
    )

    assert first.packet_id == replay.packet_id
    assert first.sha256 == replay.sha256
    assert first.canonical_bytes == replay.canonical_bytes
    assert first.manifest["quality_gates"]["eligible"] is True
    assert first.manifest["measurement"]["formulas"]["mention_rate"].endswith("valid_sample_count")
    assert first.manifest["measurement"]["known_limitations"] == ["citation_support_not_evaluated"]
    assert first.manifest["sample_index"][0]["mention_class"] == "not_mentioned"
    assert first.manifest["attribution"]["policy"] == "observational_non_causal.v1"
    assert first.manifest["counts"] == {
        "samples": 2,
        "citations": 1,
        "fact_claims": 0,
        "fact_accuracy_reviews": 0,
        "evidence_objects": 1,
        "known_limitations": 1,
    }


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda report: report.update(status="quality_blocked"), "not generated"),
        (lambda report: report.update(report_sha256=None), "report_sha256"),
        (lambda report: report.update(evidence_index={}), "baseline or compare"),
        (
            lambda report: report["metrics"]["baseline_quality"].update(publishable=False),
            "not publishable",
        ),
    ],
)
def test_report_evidence_packet_rejects_ineligible_report(mutator, message: str) -> None:
    report = publishable_report_record()
    mutator(report)
    with pytest.raises(ReportEvidencePacketError, match=message):
        build_report_evidence_packet(
            report_record=report,
            sample_index=[
                {
                    "task_id": "task_1",
                    "run_id": "scan_baseline",
                    "snapshot_id": "snap_1",
                    "sample_status": "valid",
                    "mention_class": "not_mentioned",
                    "answer_sha256": "3" * 64,
                    "raw_response_sha256": "4" * 64,
                    "evidence_snapshot_id": "evidence_1",
                    "collector_surface": "web",
                },
                {
                    "task_id": "task_2",
                    "run_id": "scan_compare",
                    "snapshot_id": "snap_2",
                    "sample_status": "valid",
                    "mention_class": "recommended",
                    "answer_sha256": "5" * 64,
                    "raw_response_sha256": "6" * 64,
                    "evidence_snapshot_id": "evidence_2",
                    "collector_surface": "web",
                },
            ],
            citation_index=[],
            fact_accuracy_index=[],
            evidence_object_index=[],
        )


def test_report_evidence_packet_binds_fact_review_hash_and_metrics() -> None:
    report = publishable_report_record()
    report["metrics"]["compare_metrics"].update(
        {
            "fact_claim_count": 1,
            "fact_reviewed_claim_count": 1,
            "fact_accuracy_coverage_rate": 1.0,
            "fact_accuracy": 1.0,
        }
    )
    samples = [
        {
            "task_id": "task_1",
            "run_id": "scan_baseline",
            "snapshot_id": "snap_1",
            "sample_status": "valid",
            "mention_class": "not_mentioned",
            "answer_sha256": "3" * 64,
            "raw_response_sha256": "5" * 64,
            "evidence_snapshot_id": "evidence_1",
            "collector_surface": "web",
        },
        {
            "task_id": "task_2",
            "run_id": "scan_compare",
            "snapshot_id": "snap_2",
            "sample_status": "valid",
            "mention_class": "recommended",
            "answer_sha256": "6" * 64,
            "raw_response_sha256": "7" * 64,
            "evidence_snapshot_id": "evidence_2",
            "collector_surface": "web",
        },
    ]
    review = {
        "review_id": "review_1",
        "verdict": "accurate",
        "evidence_grade": "approved_fact_source_boundary",
        "fact_revision_id": "revision_1",
        "knowledge_source_id": "source_1",
        "knowledge_segment_id": "segment_1",
        "fact_revision_sha256": "8" * 64,
        "source_content_sha256": "9" * 64,
        "quoted_text_sha256": "a" * 64,
        "source_start": 4,
        "source_end": 12,
        "review_method": "human",
        "reviewed_by": "reviewer_1",
        "reviewed_at": "2026-08-08T12:00:00+00:00",
        "supersedes_review_id": None,
        "commercially_verified": True,
    }
    review["review_record_sha256"] = canonical_json_sha256(review)
    packet = build_report_evidence_packet(
        report_record=report,
        sample_index=samples,
        citation_index=[],
        fact_accuracy_index=[
            {
                "claim_id": "claim_1",
                "snapshot_id": "snap_2",
                "claim_kind": "brand_fact",
                "claim_sha256": "b" * 64,
                "answer_start": 0,
                "answer_end": 8,
                "subject_entity_text": "AIRank",
                "latest_review": review,
            }
        ],
        evidence_object_index=[],
    )

    assert packet.manifest["counts"]["fact_claims"] == 1
    assert packet.manifest["counts"]["fact_accuracy_reviews"] == 1
    assert packet.manifest["fact_accuracy_index"][0]["latest_review"]["review_record_sha256"] == review["review_record_sha256"]

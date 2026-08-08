from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
from zipfile import ZipFile

import pytest

from airank_evidence import (
    EvidenceReport,
    ReportConclusion,
    ReportEvidencePacketError,
    ReportEvidencePacketVerificationError,
    build_report_conclusion,
    build_report_evidence_packet,
    verify_report_evidence_packet,
)
from airank_evidence.report import canonical_json_sha256


NOW = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)


def passed_integrity() -> dict[str, object]:
    return {
        "policy_version": "airank.evidence-integrity.v2",
        "status": "passed",
        "entity_count": 9,
        "verified_count": 9,
        "blocking_finding_count": 0,
        "manifest_sha256": "f" * 64,
    }


def source_governance_for(
    citation_index: list[dict],
    *,
    reviewed: bool = False,
    valid_until: str | None = None,
) -> dict:
    by_host: dict[str, dict[str, set[str]]] = {}
    unresolved: list[str] = []
    for citation in citation_index:
        host = citation.get("host")
        if not host:
            unresolved.append(citation["citation_id"])
            continue
        aggregate = by_host.setdefault(host, {"citation_ids": set(), "snapshot_ids": set()})
        aggregate["citation_ids"].add(citation["citation_id"])
        aggregate["snapshot_ids"].add(citation["snapshot_id"])
    entries = []
    for host, aggregate in sorted(by_host.items()):
        revision = None
        status = "unclassified"
        if reviewed:
            status = "reviewed"
            revision = {
                "revision_id": f"source_revision_{host}",
                "revision_number": 1,
                "normalized_host": host,
                "source_category_l1": "news_media",
                "source_type": "regional_news_media",
                "ecosystem": "Example Media",
                "classification_status": "reviewed",
                "classification_method": "human_review",
                "classification_confidence": "high",
                "authority_level": "high",
                "usage_policy": "primary_evidence",
                "risk_level": "low",
                "evidence_note_sha256": hashlib.sha256(b"human reviewed source").hexdigest(),
                "evidence_url": f"https://{host}/about",
                "source_dataset_name": None,
                "source_dataset_version": None,
                "valid_until": valid_until,
                "reviewed_by": "reviewer_1",
                "reviewed_at": "2026-08-08T11:00:00+00:00",
                "supersedes_revision_id": None,
                "request_sha256": "c" * 64,
                "effective": valid_until is None or valid_until >= "2026-08-08T12:00:00+00:00",
            }
            revision["revision_record_sha256"] = canonical_json_sha256(revision)
        entries.append(
            {
                "normalized_host": host,
                "citation_ids": sorted(aggregate["citation_ids"]),
                "snapshot_ids": sorted(aggregate["snapshot_ids"]),
                "run_ids": [],
                "classification_status": status,
                "current_revision": revision,
            }
        )
    return {
        "policy_version": "airank.source-governance.v1",
        "evaluated_at": "2026-08-08T12:00:00+00:00",
        "entries": entries,
        "unresolved_citation_ids": sorted(unresolved),
    }


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
    citation_index = [{"citation_id": "cite_1", "snapshot_id": "snap_1", "url": "https://example.com", "host": "example.com"}]
    object_index = [{"object_ref_id": "object_1", "sha256": "4" * 64, "byte_size": 123}]

    first = build_report_evidence_packet(
        report_record=publishable_report_record(),
        sample_index=sample_index,
        citation_index=citation_index,
        fact_accuracy_index=[],
        evidence_object_index=object_index,
        source_governance=source_governance_for(citation_index),
        integrity_audit=passed_integrity(),
    )
    replay = build_report_evidence_packet(
        report_record=publishable_report_record(),
        sample_index=sample_index,
        citation_index=citation_index,
        fact_accuracy_index=[],
        evidence_object_index=object_index,
        source_governance=source_governance_for(citation_index),
        integrity_audit=passed_integrity(),
    )

    assert first.packet_id == replay.packet_id
    assert first.sha256 == replay.sha256
    assert first.canonical_bytes == replay.canonical_bytes
    assert first.manifest_bytes == replay.manifest_bytes
    with ZipFile(io.BytesIO(first.canonical_bytes)) as archive:
        assert archive.namelist() == [
            "README.txt",
            "manifest/report-evidence.json",
            "report/report.html",
            "review/scorecard.csv",
            "SHA256SUMS",
        ]
        assert archive.read("manifest/report-evidence.json") == first.manifest_bytes
        scorecard_text = archive.read("review/scorecard.csv").decode("utf-8-sig")
        scorecard_rows = list(csv.DictReader(io.StringIO(scorecard_text)))
        assert len(scorecard_rows) == 5
        assert all(
            not row[field]
            for row in scorecard_rows
            for field in ("score_0_to_5", "reviewer", "reviewed_at", "rationale", "decision")
        )
        assert "不证明发布动作造成了变化" in archive.read("report/report.html").decode("utf-8")
    verification = verify_report_evidence_packet(
        first.canonical_bytes,
        expected_sha256=first.sha256,
    )
    assert verification.status == "verified"
    assert verification.packet_id == first.packet_id
    assert first.manifest["quality_gates"]["eligible"] is True
    assert first.manifest["evidence_integrity"] == passed_integrity()
    assert first.manifest["measurement"]["formulas"]["mention_rate"].endswith("valid_sample_count")
    assert first.manifest["measurement"]["known_limitations"] == [
        "citation_support_not_evaluated",
        "source_authority_unclassified",
    ]
    assert first.manifest["sample_index"][0]["mention_class"] == "not_mentioned"
    assert first.manifest["attribution"]["policy"] == "observational_non_causal.v1"
    assert first.manifest["counts"] == {
        "samples": 2,
        "citations": 1,
        "fact_claims": 0,
        "fact_accuracy_reviews": 0,
        "source_hosts": 1,
        "source_effective_classifications": 0,
        "source_authority_resolved": 0,
        "source_authority_coverage_rate": 0.0,
        "source_authority_summary_eligible": False,
        "evidence_objects": 1,
        "known_limitations": 2,
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
            source_governance=source_governance_for([]),
            integrity_audit=passed_integrity(),
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
        "review_case_id": "evidence_review_case_1",
        "reviewer_role": "secondary",
        "review_case_status": "agreed",
        "review_case_purpose": "production",
        "evidence_verified": True,
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
        source_governance=source_governance_for([]),
        integrity_audit=passed_integrity(),
    )

    assert packet.manifest["counts"]["fact_claims"] == 1
    assert packet.manifest["counts"]["fact_accuracy_reviews"] == 1
    assert packet.manifest["source_governance"]["summary"]["authority_summary_eligible"] is False
    assert packet.manifest["fact_accuracy_index"][0]["latest_review"]["review_record_sha256"] == review["review_record_sha256"]


def test_report_evidence_packet_recomputes_independently_reviewed_citation_support() -> None:
    report = publishable_report_record()
    report["metrics"]["baseline_metrics"]["citation_support"] = 1.0
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
            "citation_support_score": 1.0,
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
            "citation_support_score": None,
        },
    ]
    support_review = {
        "claim_id": "claim_1",
        "claim_sha256": "8" * 64,
        "answer_start": 0,
        "answer_end": 8,
        "review_id": "review_1",
        "support_label": "supports",
        "evidence_grade": "source_page_snapshot",
        "source_content_sha256": "9" * 64,
        "source_object_ref_id": "object_source_1",
        "source_capture_id": "capture_1",
        "source_segment_id": "segment_1",
        "source_start": 0,
        "source_end": 16,
        "review_method": "human",
        "reviewed_by": "reviewer_2",
        "reviewed_at": "2026-08-08T12:00:00+00:00",
        "review_case_id": "evidence_review_case_1",
        "reviewer_role": "secondary",
        "review_case_status": "agreed",
        "review_case_purpose": "production",
        "evidence_verified": True,
        "commercially_verified": True,
    }
    support_review["review_record_sha256"] = canonical_json_sha256(support_review)
    citations = [
        {
            "citation_id": "cite_1",
            "snapshot_id": "snap_1",
            "url": "https://example.com/source",
            "host": "example.com",
            "support_reviews": [support_review],
        }
    ]
    packet = build_report_evidence_packet(
        report_record=report,
        sample_index=samples,
        citation_index=citations,
        fact_accuracy_index=[],
        evidence_object_index=[],
        source_governance=source_governance_for(citations),
        integrity_audit=passed_integrity(),
    )
    assert packet.manifest["measurement"]["baseline_metrics"]["citation_support"] == 1.0
    assert packet.manifest["citation_index"][0]["support_reviews"][0]["review_case_status"] == "agreed"

    tampered = dict(support_review)
    tampered["review_case_purpose"] = "benchmark"
    tampered["review_record_sha256"] = canonical_json_sha256(
        {key: value for key, value in tampered.items() if key != "review_record_sha256"}
    )
    citations[0]["support_reviews"] = [tampered]
    with pytest.raises(ReportEvidencePacketError, match="benchmark review"):
        build_report_evidence_packet(
            report_record=report,
            sample_index=samples,
            citation_index=citations,
            fact_accuracy_index=[],
            evidence_object_index=[],
            source_governance=source_governance_for(citations),
            integrity_audit=passed_integrity(),
        )


def test_report_evidence_packet_binds_effective_source_governance_hashes() -> None:
    citations = [
        {
            "citation_id": "cite_1",
            "snapshot_id": "snap_1",
            "url": "https://news.example.com/article",
            "host": "news.example.com",
        }
    ]
    packet = build_report_evidence_packet(
        report_record=publishable_report_record(),
        sample_index=[
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
        ],
        citation_index=citations,
        fact_accuracy_index=[],
        evidence_object_index=[],
        source_governance=source_governance_for(citations, reviewed=True),
        integrity_audit=passed_integrity(),
    )

    summary = packet.manifest["source_governance"]["summary"]
    assert packet.manifest["schema_version"] == "airank.report-evidence-packet.v7"
    assert summary["source_host_count"] == 1
    assert summary["authority_coverage_rate"] == 1.0
    assert summary["authority_summary_eligible"] is True
    assert packet.manifest["source_governance"]["known_limitations"] == []

    tampered = source_governance_for(citations, reviewed=True)
    tampered["entries"][0]["current_revision"]["authority_level"] = "low"
    with pytest.raises(ReportEvidencePacketError, match="revision hash"):
        build_report_evidence_packet(
            report_record=publishable_report_record(),
            sample_index=packet.manifest["sample_index"],
            citation_index=citations,
            fact_accuracy_index=[],
            evidence_object_index=[],
            source_governance=tampered,
            integrity_audit=passed_integrity(),
        )


def test_report_evidence_packet_verifier_requires_external_anchor_and_rejects_tamper() -> None:
    citations = [
        {
            "citation_id": "cite_1",
            "snapshot_id": "snap_1",
            "url": "https://example.com",
            "host": "example.com",
        }
    ]
    packet = build_report_evidence_packet(
        report_record=publishable_report_record(),
        sample_index=[
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
        ],
        citation_index=citations,
        fact_accuracy_index=[],
        evidence_object_index=[],
        source_governance=source_governance_for(citations),
        integrity_audit=passed_integrity(),
    )
    with pytest.raises(ReportEvidencePacketVerificationError, match="external"):
        verify_report_evidence_packet(packet.canonical_bytes, expected_sha256="")
    tampered = packet.canonical_bytes[:-1] + bytes([packet.canonical_bytes[-1] ^ 1])
    with pytest.raises(ReportEvidencePacketVerificationError, match="external anchor"):
        verify_report_evidence_packet(tampered, expected_sha256=packet.sha256)

    with ZipFile(io.BytesIO(packet.canonical_bytes)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members["report/report.html"] += b"tampered"
    altered_output = io.BytesIO()
    with ZipFile(altered_output, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    altered = altered_output.getvalue()
    with pytest.raises(ReportEvidencePacketVerificationError, match="member hash mismatch"):
        verify_report_evidence_packet(
            altered,
            expected_sha256=hashlib.sha256(altered).hexdigest(),
        )

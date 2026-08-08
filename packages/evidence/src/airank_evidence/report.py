from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any


REPORT_EVIDENCE_PACKET_VERSION = "airank.report-evidence-packet.v2"
QUALITY_CONTRACT_VERSION = "airank.measurement-quality.v4"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

METRIC_FORMULAS: dict[str, str] = {
    "valid_sample_rate": "valid_sample_count / total_sample_count",
    "mention_rate": "mentioned_valid_sample_count / valid_sample_count",
    "recommendation_rate": "recommended_valid_sample_count / valid_sample_count",
    "top1_rate": "top1_valid_sample_count / valid_sample_count",
    "top3_rate": "top3_valid_sample_count / valid_sample_count",
    "top5_rate": "top5_valid_sample_count / valid_sample_count",
    "conditional_top3_rate": "top3_valid_sample_count / ranked_sample_count",
    "stability": "mean(modal_outcome_count / repeated_group_sample_count)",
    "citation_recall_rate": "valid_samples_with_provider_citation / valid_sample_count",
    "citation_support": "mean(reviewed_citation_support_score)",
    "fact_accuracy": "accurate_commercially_verified_fact_claim_count / factual_claim_count; emitted only at complete decisive coverage",
}


class ReportEvidencePacketError(ValueError):
    """The stored report cannot produce a customer-deliverable evidence packet."""


@dataclass(frozen=True)
class ReportEvidencePacket:
    packet_id: str
    manifest: dict[str, Any]
    canonical_bytes: bytes
    sha256: str


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_json_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _publishable_quality(metrics: dict[str, Any], key: str) -> dict[str, Any]:
    quality = metrics.get(key)
    if not isinstance(quality, dict):
        raise ReportEvidencePacketError(f"{key} is missing")
    if quality.get("contract_version") != QUALITY_CONTRACT_VERSION:
        raise ReportEvidencePacketError(f"{key} uses an unsupported quality contract")
    if quality.get("publishable") is not True:
        raise ReportEvidencePacketError(f"{key} is not publishable")
    return quality


def build_report_evidence_packet(
    *,
    report_record: dict[str, Any],
    sample_index: list[dict[str, Any]],
    citation_index: list[dict[str, Any]],
    fact_accuracy_index: list[dict[str, Any]],
    evidence_object_index: list[dict[str, Any]],
) -> ReportEvidencePacket:
    """Build a deterministic, immutable manifest without copying raw answer bodies."""

    metrics = report_record.get("metrics")
    evidence_index = report_record.get("evidence_index")
    report_sha256 = str(report_record.get("report_sha256") or "")
    if report_record.get("status") != "generated" or not isinstance(metrics, dict):
        raise ReportEvidencePacketError("report is not generated")
    baseline_quality = _publishable_quality(metrics, "baseline_quality")
    compare_quality = _publishable_quality(metrics, "compare_quality")
    if not SHA256_RE.fullmatch(report_sha256):
        raise ReportEvidencePacketError("report_sha256 is missing or invalid")
    if not isinstance(evidence_index, dict):
        raise ReportEvidencePacketError("evidence_index is missing")
    required_run_refs = ("baseline_run_id", "compare_run_id")
    if any(not evidence_index.get(key) for key in required_run_refs):
        raise ReportEvidencePacketError("evidence_index is missing baseline or compare run")
    if evidence_index["baseline_run_id"] == evidence_index["compare_run_id"]:
        raise ReportEvidencePacketError("baseline and compare run must be distinct")
    if not sample_index:
        raise ReportEvidencePacketError("sample_index is empty")
    expected_run_ids = {
        str(evidence_index["baseline_run_id"]),
        str(evidence_index["compare_run_id"]),
    }
    indexed_run_ids = {str(item.get("run_id") or "") for item in sample_index}
    if indexed_run_ids != expected_run_ids:
        raise ReportEvidencePacketError("sample_index contains an unexpected or missing run")
    run_metric_pairs = (
        (str(evidence_index["baseline_run_id"]), metrics.get("baseline_metrics")),
        (str(evidence_index["compare_run_id"]), metrics.get("compare_metrics")),
    )
    for run_id, run_metrics in run_metric_pairs:
        if not isinstance(run_metrics, dict):
            raise ReportEvidencePacketError(f"metrics are missing for run {run_id}")
        indexed_samples = [item for item in sample_index if item.get("run_id") == run_id]
        valid_samples = [item for item in indexed_samples if item.get("sample_status") == "valid"]
        not_mentioned = [
            item for item in valid_samples if item.get("mention_class") == "not_mentioned"
        ]
        expected_counts = {
            "total_sample_count": len(indexed_samples),
            "valid_sample_count": len(valid_samples),
            "not_mentioned_count": len(not_mentioned),
        }
        for metric_name, actual_count in expected_counts.items():
            if run_metrics.get(metric_name) != actual_count:
                raise ReportEvidencePacketError(
                    f"sample_index {metric_name} does not match metrics for run {run_id}"
                )
        for item in valid_samples:
            if (
                not item.get("snapshot_id")
                or not item.get("evidence_snapshot_id")
                or not SHA256_RE.fullmatch(str(item.get("answer_sha256") or ""))
                or not SHA256_RE.fullmatch(str(item.get("raw_response_sha256") or ""))
            ):
                raise ReportEvidencePacketError(
                    f"valid sample evidence is incomplete for task {item.get('task_id')}"
                )
            if (
                item.get("collector_surface") == "api"
                and not item.get("provider_request_audit_id")
            ):
                raise ReportEvidencePacketError(
                    f"provider request audit is missing for task {item.get('task_id')}"
                )
    snapshot_ids = {str(item["snapshot_id"]) for item in sample_index if item.get("snapshot_id")}
    if any(str(item.get("snapshot_id") or "") not in snapshot_ids for item in citation_index):
        raise ReportEvidencePacketError("citation_index references an unknown snapshot")
    for item in citation_index:
        cited_text_sha256 = item.get("cited_text_sha256")
        if cited_text_sha256 is not None and not SHA256_RE.fullmatch(str(cited_text_sha256)):
            raise ReportEvidencePacketError("citation_index contains an invalid cited text hash")
    if any(
        str(item.get("snapshot_id") or "") not in snapshot_ids
        for item in fact_accuracy_index
    ):
        raise ReportEvidencePacketError("fact_accuracy_index references an unknown snapshot")
    for item in fact_accuracy_index:
        if item.get("claim_kind") not in {"brand_fact", "competitor_fact"}:
            raise ReportEvidencePacketError("fact_accuracy_index contains a non-factual claim")
        if not SHA256_RE.fullmatch(str(item.get("claim_sha256") or "")):
            raise ReportEvidencePacketError("fact_accuracy_index contains an invalid claim hash")
        start = item.get("answer_start")
        end = item.get("answer_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            raise ReportEvidencePacketError("fact_accuracy_index contains an invalid answer boundary")
        review = item.get("latest_review")
        if review is None:
            continue
        if not isinstance(review, dict):
            raise ReportEvidencePacketError("fact_accuracy_index contains an invalid review")
        review_sha256 = review.get("review_record_sha256")
        review_payload = {key: value for key, value in review.items() if key != "review_record_sha256"}
        if (
            not SHA256_RE.fullmatch(str(review_sha256 or ""))
            or canonical_json_sha256(review_payload) != review_sha256
        ):
            raise ReportEvidencePacketError("fact_accuracy_index contains an invalid review hash")
        if review.get("commercially_verified") is True:
            for digest_key in (
                "fact_revision_sha256",
                "source_content_sha256",
                "quoted_text_sha256",
            ):
                if not SHA256_RE.fullmatch(str(review.get(digest_key) or "")):
                    raise ReportEvidencePacketError(
                        f"fact_accuracy_index contains an invalid {digest_key}"
                    )
            source_start = review.get("source_start")
            source_end = review.get("source_end")
            if (
                not isinstance(source_start, int)
                or not isinstance(source_end, int)
                or source_start < 0
                or source_end <= source_start
            ):
                raise ReportEvidencePacketError(
                    "fact_accuracy_index contains an invalid source boundary"
                )

    snapshot_run = {
        str(item["snapshot_id"]): str(item["run_id"])
        for item in sample_index
        if item.get("snapshot_id")
    }
    for run_id, run_metrics in run_metric_pairs:
        run_claims = [
            item
            for item in fact_accuracy_index
            if snapshot_run.get(str(item.get("snapshot_id") or "")) == run_id
        ]
        decisive = [
            item
            for item in run_claims
            if isinstance(item.get("latest_review"), dict)
            and item["latest_review"].get("commercially_verified") is True
            and item["latest_review"].get("verdict")
            in {"accurate", "inaccurate", "outdated"}
        ]
        expected_fact_accuracy = (
            round(
                sum(
                    item["latest_review"].get("verdict") == "accurate"
                    for item in decisive
                )
                / len(run_claims),
                6,
            )
            if run_claims and len(decisive) == len(run_claims)
            else None
        )
        expected_fact_metrics = {
            "fact_claim_count": len(run_claims),
            "fact_reviewed_claim_count": len(decisive),
            "fact_accuracy_coverage_rate": (
                round(len(decisive) / len(run_claims), 6) if run_claims else None
            ),
            "fact_accuracy": expected_fact_accuracy,
        }
        for metric_name, expected_value in expected_fact_metrics.items():
            if run_metrics.get(metric_name) != expected_value:
                raise ReportEvidencePacketError(
                    f"fact_accuracy_index {metric_name} does not match metrics for run {run_id}"
                )
    for item in evidence_object_index:
        if not item.get("object_ref_id") or not SHA256_RE.fullmatch(str(item.get("sha256") or "")):
            raise ReportEvidencePacketError("evidence_object_index contains an invalid object hash")

    source_record_sha256 = canonical_json_sha256(report_record)
    packet_id = f"report_packet_{source_record_sha256[:20]}"
    known_limitations = metrics.get("known_limitations")
    if not isinstance(known_limitations, list):
        known_limitations = []
    risks = [
        {
            "code": "OBSERVATIONAL_ATTRIBUTION_ONLY",
            "level": "high",
            "statement": "Observed changes do not prove that the published intervention caused the result.",
        },
        {
            "code": "PROVIDER_OUTPUT_VOLATILITY",
            "level": "medium",
            "statement": "Provider model, search state, time, region, and ranking volatility may affect repeated answers.",
        },
    ]
    if known_limitations:
        risks.append(
            {
                "code": "KNOWN_MEASUREMENT_LIMITATIONS",
                "level": "medium",
                "statement": "See known_limitations; no missing metric is synthesized.",
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": REPORT_EVIDENCE_PACKET_VERSION,
        "packet_id": packet_id,
        "canonicalization": "airank.sorted-key-utf8-json.v1",
        "report": {
            "report_id": report_record["report_id"],
            "tenant_id": report_record["tenant_id"],
            "project_id": report_record["project_id"],
            "report_type": report_record["report_type"],
            "title": report_record["title"],
            "status": report_record["status"],
            "report_sha256": report_sha256,
            "source_record_sha256": source_record_sha256,
            "generated_at": report_record.get("generated_at"),
            "generated_by": report_record.get("generated_by"),
        },
        "quality_gates": {
            "baseline": baseline_quality,
            "compare": compare_quality,
            "eligible": True,
        },
        "measurement": {
            "baseline_metrics": metrics.get("baseline_metrics", {}),
            "compare_metrics": metrics.get("compare_metrics", {}),
            "metric_deltas": metrics.get("metric_deltas", {}),
            "formulas": dict(METRIC_FORMULAS),
            "known_limitations": known_limitations,
        },
        "attribution": {
            "policy": metrics.get("attribution_policy", "observational_non_causal.v1"),
            "confidence": metrics.get("confidence", "low"),
            "conclusion": metrics.get("conclusion", ""),
            "assumptions": [
                "Baseline and comparison cohorts passed the recorded quality gates.",
                "Unmentioned valid samples remain in the metric denominator.",
                "No causal guarantee or provider recommendation guarantee is asserted.",
            ],
            "risks": risks,
        },
        "evidence_index": evidence_index,
        "sample_index": sample_index,
        "citation_index": citation_index,
        "fact_accuracy_index": fact_accuracy_index,
        "evidence_object_index": evidence_object_index,
        "counts": {
            "samples": len(sample_index),
            "citations": len(citation_index),
            "fact_claims": len(fact_accuracy_index),
            "fact_accuracy_reviews": sum(
                item.get("latest_review") is not None for item in fact_accuracy_index
            ),
            "evidence_objects": len(evidence_object_index),
            "known_limitations": len(known_limitations),
        },
    }
    canonical_bytes = canonical_json_bytes(manifest)
    return ReportEvidencePacket(
        packet_id=packet_id,
        manifest=manifest,
        canonical_bytes=canonical_bytes,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
    )


@dataclass(frozen=True)
class ReportConclusion:
    id: str
    title: str
    body: str
    snapshot_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    fact_atom_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.snapshot_ids:
            raise ValueError("report conclusion must reference at least one snapshot")
        if not self.citation_ids:
            raise ValueError("report conclusion must reference at least one citation")
        if not self.fact_atom_ids:
            raise ValueError("report conclusion must reference at least one FactAtom")

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "evidence": {
                "snapshot_ids": list(self.snapshot_ids),
                "citation_ids": list(self.citation_ids),
                "fact_atom_ids": list(self.fact_atom_ids),
            },
        }


@dataclass(frozen=True)
class EvidenceReport:
    id: str
    tenant_id: str
    project_id: str
    title: str
    conclusions: tuple[ReportConclusion, ...]
    generated_at: datetime

    def __post_init__(self) -> None:
        if not self.conclusions:
            raise ValueError("evidence report must include at least one conclusion")

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "title": self.title,
            "generated_at": self.generated_at.isoformat(),
            "conclusions": [conclusion.to_record() for conclusion in self.conclusions],
        }


def build_report_conclusion(
    *,
    id: str,
    title: str,
    body: str,
    snapshot_id: str,
    citation_id: str,
    fact_atom_id: str,
) -> ReportConclusion:
    return ReportConclusion(
        id=id,
        title=title,
        body=body,
        snapshot_ids=(snapshot_id,),
        citation_ids=(citation_id,),
        fact_atom_ids=(fact_atom_id,),
    )

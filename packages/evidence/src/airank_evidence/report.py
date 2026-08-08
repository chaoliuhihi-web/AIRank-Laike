from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from .source_registry import normalize_source_host


REPORT_EVIDENCE_PACKET_VERSION = "airank.report-evidence-packet.v4"
QUALITY_CONTRACT_VERSION = "airank.measurement-quality.v4"
SOURCE_GOVERNANCE_VERSION = "airank.source-governance.v1"
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


def _validate_independent_commercial_review(
    review: dict[str, Any], *, index_name: str
) -> None:
    if review.get("commercially_verified") is not True:
        return
    if review.get("evidence_verified") is not True:
        raise ReportEvidencePacketError(
            f"{index_name} commercial review lacks verified evidence"
        )
    if not review.get("review_case_id"):
        raise ReportEvidencePacketError(
            f"{index_name} commercial review lacks an independent review case"
        )
    if review.get("reviewer_role") not in {"secondary", "adjudicator"}:
        raise ReportEvidencePacketError(
            f"{index_name} commercial review lacks an independent final reviewer"
        )
    if review.get("review_case_status") not in {"agreed", "adjudicated"}:
        raise ReportEvidencePacketError(
            f"{index_name} commercial review case is not final"
        )
    if review.get("review_case_purpose") != "production":
        raise ReportEvidencePacketError(
            f"{index_name} benchmark review cannot enter commercial metrics"
        )


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


def _parsed_datetime(value: Any, key: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        raise ReportEvidencePacketError(f"{key} is missing or invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReportEvidencePacketError(f"{key} is missing or invalid") from exc


def _validate_source_governance(
    citation_index: list[dict[str, Any]],
    source_governance: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if source_governance.get("policy_version") != SOURCE_GOVERNANCE_VERSION:
        raise ReportEvidencePacketError("source_governance uses an unsupported policy")
    evaluated_at = _parsed_datetime(
        source_governance.get("evaluated_at"), "source_governance evaluated_at"
    )
    entries = source_governance.get("entries")
    unresolved_citation_ids = source_governance.get("unresolved_citation_ids")
    if not isinstance(entries, list) or not isinstance(unresolved_citation_ids, list):
        raise ReportEvidencePacketError("source_governance index is missing")

    citations_by_host: dict[str, set[str]] = {}
    expected_unresolved: set[str] = set()
    snapshots_by_host: dict[str, set[str]] = {}
    for citation in citation_index:
        citation_id = str(citation.get("citation_id") or "")
        snapshot_id = str(citation.get("snapshot_id") or "")
        if not citation_id:
            raise ReportEvidencePacketError("citation_index contains a citation without an id")
        try:
            normalized_host = normalize_source_host(str(citation.get("host") or ""))
        except ValueError:
            expected_unresolved.add(citation_id)
            continue
        citations_by_host.setdefault(normalized_host, set()).add(citation_id)
        snapshots_by_host.setdefault(normalized_host, set()).add(snapshot_id)

    if set(str(item) for item in unresolved_citation_ids) != expected_unresolved:
        raise ReportEvidencePacketError(
            "source_governance unresolved citations do not match citation_index"
        )

    entry_hosts: set[str] = set()
    classified_host_count = 0
    effective_classified_host_count = 0
    expired_classification_count = 0
    unclassified_host_count = 0
    unknown_authority_host_count = 0
    authority_resolved_host_count = 0
    primary_evidence_host_count = 0
    prohibited_host_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            raise ReportEvidencePacketError("source_governance contains an invalid entry")
        try:
            normalized_host = normalize_source_host(str(entry.get("normalized_host") or ""))
        except ValueError as exc:
            raise ReportEvidencePacketError(
                "source_governance contains an invalid normalized host"
            ) from exc
        if normalized_host in entry_hosts:
            raise ReportEvidencePacketError("source_governance contains a duplicate host")
        entry_hosts.add(normalized_host)
        if set(str(item) for item in entry.get("citation_ids", [])) != citations_by_host.get(
            normalized_host, set()
        ):
            raise ReportEvidencePacketError(
                "source_governance citation ids do not match citation_index"
            )
        if set(str(item) for item in entry.get("snapshot_ids", [])) != snapshots_by_host.get(
            normalized_host, set()
        ):
            raise ReportEvidencePacketError(
                "source_governance snapshot ids do not match citation_index"
            )

        revision = entry.get("current_revision")
        if revision is None:
            if entry.get("classification_status") != "unclassified":
                raise ReportEvidencePacketError(
                    "source_governance unclassified entry has an invalid status"
                )
            unclassified_host_count += 1
            continue
        if not isinstance(revision, dict):
            raise ReportEvidencePacketError(
                "source_governance contains an invalid classification revision"
            )
        revision_sha256 = str(revision.get("revision_record_sha256") or "")
        revision_record = {
            key: value
            for key, value in revision.items()
            if key != "revision_record_sha256"
        }
        if (
            not SHA256_RE.fullmatch(revision_sha256)
            or canonical_json_sha256(revision_record) != revision_sha256
        ):
            raise ReportEvidencePacketError(
                "source_governance contains an invalid revision hash"
            )
        if revision.get("normalized_host") != normalized_host:
            raise ReportEvidencePacketError(
                "source_governance revision host does not match its entry"
            )
        if entry.get("classification_status") != revision.get("classification_status"):
            raise ReportEvidencePacketError(
                "source_governance classification status does not match its revision"
            )
        if not SHA256_RE.fullmatch(str(revision.get("request_sha256") or "")):
            raise ReportEvidencePacketError(
                "source_governance contains an invalid request hash"
            )
        if not SHA256_RE.fullmatch(str(revision.get("evidence_note_sha256") or "")):
            raise ReportEvidencePacketError(
                "source_governance contains an invalid evidence note hash"
            )
        reviewed_at = _parsed_datetime(
            revision.get("reviewed_at"), "source_governance reviewed_at"
        )
        if reviewed_at > evaluated_at:
            raise ReportEvidencePacketError(
                "source_governance includes a revision newer than its evaluation time"
            )
        valid_until_raw = revision.get("valid_until")
        valid_until = (
            _parsed_datetime(valid_until_raw, "source_governance valid_until")
            if valid_until_raw
            else None
        )
        expected_effective = valid_until is None or valid_until >= evaluated_at
        if revision.get("effective") is not expected_effective:
            raise ReportEvidencePacketError(
                "source_governance revision effectiveness is inconsistent"
            )

        classified_host_count += 1
        if expected_effective:
            effective_classified_host_count += 1
            if revision.get("authority_level") == "unknown":
                unknown_authority_host_count += 1
            else:
                authority_resolved_host_count += 1
            if revision.get("usage_policy") == "primary_evidence":
                primary_evidence_host_count += 1
            if revision.get("usage_policy") == "prohibited":
                prohibited_host_count += 1
        else:
            expired_classification_count += 1

    if entry_hosts != set(citations_by_host):
        raise ReportEvidencePacketError(
            "source_governance hosts do not match citation_index"
        )

    source_host_count = len(entry_hosts)
    classification_complete = (
        not expected_unresolved
        and effective_classified_host_count == source_host_count
    )
    authority_summary_eligible = (
        source_host_count > 0
        and classification_complete
        and unknown_authority_host_count == 0
    )
    authority_coverage_rate = (
        round(authority_resolved_host_count / source_host_count, 6)
        if source_host_count
        else None
    )
    limitations: list[str] = []
    if unclassified_host_count:
        limitations.append("source_authority_unclassified")
    if expired_classification_count:
        limitations.append("source_classification_expired")
    if expected_unresolved:
        limitations.append("citation_host_unresolved")
    if unknown_authority_host_count:
        limitations.append("source_authority_unknown")
    if prohibited_host_count:
        limitations.append("source_usage_prohibited")
    summary = {
        "source_host_count": source_host_count,
        "classified_host_count": classified_host_count,
        "effective_classified_host_count": effective_classified_host_count,
        "unclassified_host_count": unclassified_host_count,
        "expired_classification_count": expired_classification_count,
        "unresolved_citation_count": len(expected_unresolved),
        "unknown_authority_host_count": unknown_authority_host_count,
        "authority_resolved_host_count": authority_resolved_host_count,
        "primary_evidence_host_count": primary_evidence_host_count,
        "prohibited_host_count": prohibited_host_count,
        "authority_coverage_rate": authority_coverage_rate,
        "classification_complete": classification_complete,
        "authority_summary_eligible": authority_summary_eligible,
    }
    return summary, limitations


def build_report_evidence_packet(
    *,
    report_record: dict[str, Any],
    sample_index: list[dict[str, Any]],
    citation_index: list[dict[str, Any]],
    fact_accuracy_index: list[dict[str, Any]],
    evidence_object_index: list[dict[str, Any]],
    source_governance: dict[str, Any],
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
        support_values = [
            float(item["citation_support_score"])
            for item in valid_samples
            if item.get("citation_support_score") is not None
        ]
        expected_citation_support = (
            round(sum(support_values) / len(support_values), 6)
            if support_values
            else None
        )
        if run_metrics.get("citation_support") != expected_citation_support:
            raise ReportEvidencePacketError(
                f"sample_index citation_support does not match metrics for run {run_id}"
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
    support_values_by_snapshot: dict[str, list[float]] = {}
    for item in citation_index:
        cited_text_sha256 = item.get("cited_text_sha256")
        if cited_text_sha256 is not None and not SHA256_RE.fullmatch(str(cited_text_sha256)):
            raise ReportEvidencePacketError("citation_index contains an invalid cited text hash")
        support_reviews = item.get("support_reviews", [])
        if not isinstance(support_reviews, list):
            raise ReportEvidencePacketError("citation_index contains invalid support reviews")
        for review in support_reviews:
            if not isinstance(review, dict):
                raise ReportEvidencePacketError("citation_index contains an invalid support review")
            review_sha256 = review.get("review_record_sha256")
            review_payload = {
                key: value
                for key, value in review.items()
                if key != "review_record_sha256"
            }
            if (
                not SHA256_RE.fullmatch(str(review_sha256 or ""))
                or canonical_json_sha256(review_payload) != review_sha256
            ):
                raise ReportEvidencePacketError(
                    "citation_index contains an invalid support review hash"
                )
            if not SHA256_RE.fullmatch(str(review.get("claim_sha256") or "")):
                raise ReportEvidencePacketError(
                    "citation_index contains an invalid support claim hash"
                )
            support_start = review.get("answer_start")
            support_end = review.get("answer_end")
            if (
                not isinstance(support_start, int)
                or not isinstance(support_end, int)
                or support_start < 0
                or support_end <= support_start
            ):
                raise ReportEvidencePacketError(
                    "citation_index contains an invalid support claim boundary"
                )
            _validate_independent_commercial_review(
                review, index_name="citation_index"
            )
            if review.get("commercially_verified") is not True:
                continue
            if review.get("evidence_grade") != "source_page_snapshot":
                raise ReportEvidencePacketError(
                    "citation_index commercial review lacks a source page snapshot"
                )
            for key in (
                "source_object_ref_id",
                "source_capture_id",
                "source_segment_id",
            ):
                if not review.get(key):
                    raise ReportEvidencePacketError(
                        f"citation_index commercial review is missing {key}"
                    )
            if not SHA256_RE.fullmatch(
                str(review.get("source_content_sha256") or "")
            ):
                raise ReportEvidencePacketError(
                    "citation_index contains an invalid source content hash"
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
                    "citation_index contains an invalid support source boundary"
                )
            label = review.get("support_label")
            if label not in {"supports", "contradicts", "insufficient"}:
                raise ReportEvidencePacketError(
                    "citation_index contains an invalid support label"
                )
            support_values_by_snapshot.setdefault(
                str(item.get("snapshot_id") or ""), []
            ).append(1.0 if label == "supports" else 0.0)

    for sample in sample_index:
        snapshot_id = str(sample.get("snapshot_id") or "")
        values = support_values_by_snapshot.get(snapshot_id, [])
        expected_support = round(sum(values) / len(values), 6) if values else None
        if sample.get("citation_support_score") != expected_support:
            raise ReportEvidencePacketError(
                f"citation support evidence does not match sample {snapshot_id}"
            )
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
            _validate_independent_commercial_review(
                review, index_name="fact_accuracy_index"
            )
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

    source_governance_summary, source_governance_limitations = _validate_source_governance(
        citation_index,
        source_governance,
    )

    source_record_sha256 = canonical_json_sha256(report_record)
    report_known_limitations = metrics.get("known_limitations")
    if not isinstance(report_known_limitations, list):
        report_known_limitations = []
    known_limitations = list(
        dict.fromkeys(
            [str(item) for item in report_known_limitations]
            + source_governance_limitations
        )
    )
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
    if source_governance_limitations:
        risks.append(
            {
                "code": "SOURCE_GOVERNANCE_LIMITATIONS",
                "level": "high",
                "statement": "Source authority or usage conclusions remain ineligible until the recorded source-governance limitations are resolved.",
            }
        )

    manifest_basis: dict[str, Any] = {
        "schema_version": REPORT_EVIDENCE_PACKET_VERSION,
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
        "source_governance": {
            **source_governance,
            "summary": source_governance_summary,
            "known_limitations": source_governance_limitations,
        },
        "evidence_object_index": evidence_object_index,
        "counts": {
            "samples": len(sample_index),
            "citations": len(citation_index),
            "fact_claims": len(fact_accuracy_index),
            "fact_accuracy_reviews": sum(
                item.get("latest_review") is not None for item in fact_accuracy_index
            ),
            "source_hosts": source_governance_summary["source_host_count"],
            "source_effective_classifications": source_governance_summary[
                "effective_classified_host_count"
            ],
            "source_authority_resolved": source_governance_summary[
                "authority_resolved_host_count"
            ],
            "source_authority_coverage_rate": source_governance_summary[
                "authority_coverage_rate"
            ],
            "source_authority_summary_eligible": source_governance_summary[
                "authority_summary_eligible"
            ],
            "evidence_objects": len(evidence_object_index),
            "known_limitations": len(known_limitations),
        },
    }
    packet_basis_sha256 = canonical_json_sha256(manifest_basis)
    packet_id = f"report_packet_{packet_basis_sha256[:20]}"
    manifest: dict[str, Any] = {
        **manifest_basis,
        "packet_id": packet_id,
        "packet_basis_sha256": packet_basis_sha256,
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

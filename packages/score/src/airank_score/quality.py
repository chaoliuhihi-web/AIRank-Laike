from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Literal, Sequence

from airank_domain.measurement import MeasurementSample, MentionClass, SampleStatus, canonical_json_sha256

from .measurement import CohortMetrics, calculate_cohort_metrics


QUALITY_CONTRACT_VERSION = "airank.measurement-quality.v1"


@dataclass(frozen=True)
class QualityCheck:
    code: str
    status: Literal["pass", "blocked", "warning"]
    actual: int | float | str | bool | None
    expected: str
    detail: str

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeasurementQualityReport:
    contract_version: str
    run_id: str
    status: Literal["pass", "blocked"]
    publishable: bool
    data_sha256: str
    report_sha256: str
    metrics: CohortMetrics
    checks: tuple[QualityCheck, ...]
    known_limitations: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "run_id": self.run_id,
            "status": self.status,
            "publishable": self.publishable,
            "data_sha256": self.data_sha256,
            "report_sha256": self.report_sha256,
            "metrics": self.metrics.to_record(),
            "checks": [item.to_record() for item in self.checks],
            "known_limitations": list(self.known_limitations),
        }


def build_measurement_quality_report(
    *,
    run_id: str,
    samples: Iterable[MeasurementSample],
    signatures: Sequence[str],
    minimum_valid_sample_rate: float = 0.8,
) -> MeasurementQualityReport:
    sample_list = list(samples)
    signature_list = list(signatures)
    metrics = calculate_cohort_metrics(sample_list)
    checks: list[QualityCheck] = []

    def add_check(code: str, passed: bool, actual: Any, expected: str, detail: str) -> None:
        checks.append(QualityCheck(code, "pass" if passed else "blocked", actual, expected, detail))

    add_check("samples_present", bool(sample_list), len(sample_list), "> 0", "报告必须来自至少一个真实任务样本。")
    add_check(
        "signature_count_matches",
        len(signature_list) == len(sample_list),
        len(signature_list),
        f"= {len(sample_list)}",
        "每个样本必须有一条可比较任务签名。",
    )
    sample_ids = [item.sample_id for item in sample_list]
    add_check(
        "sample_ids_unique",
        len(sample_ids) == len(set(sample_ids)),
        len(sample_ids) - len(set(sample_ids)),
        "= 0 duplicates",
        "重复样本 ID 会导致分母和指标被重复计算。",
    )
    add_check(
        "sample_contracts_unique",
        len(signature_list) == len(set(signature_list)),
        len(signature_list) - len(set(signature_list)),
        "= 0 duplicates",
        "同一问题、平台、终端和轮次不能重复占用一个采样位。",
    )
    partition_count = metrics.valid_sample_count + metrics.failed_sample_count + metrics.blocked_sample_count
    add_check(
        "status_partition_complete",
        partition_count == metrics.total_sample_count,
        partition_count,
        f"= {metrics.total_sample_count}",
        "有效、失败和阻塞必须覆盖全部样本，未提及仍属于有效样本。",
    )
    add_check(
        "valid_samples_present",
        metrics.valid_sample_count > 0,
        metrics.valid_sample_count,
        "> 0",
        "没有有效回答时不得发布品牌可见度或变化结论。",
    )
    add_check(
        "valid_sample_rate",
        metrics.valid_sample_rate >= minimum_valid_sample_rate,
        metrics.valid_sample_rate,
        f">= {minimum_valid_sample_rate}",
        "有效样本率过低时结果易被失败/阻塞偏差主导。",
    )
    missing_answer_hash = sum(
        item.status == SampleStatus.VALID and not item.answer_sha256 for item in sample_list
    )
    add_check(
        "valid_answer_hashes_present",
        missing_answer_hash == 0,
        missing_answer_hash,
        "= 0 missing",
        "每个有效回答必须绑定逐字回答 SHA-256。",
    )
    missing_raw_hash = sum(not item.raw_response_sha256 for item in sample_list)
    add_check(
        "raw_response_hashes_present",
        missing_raw_hash == 0,
        missing_raw_hash,
        "= 0 missing",
        "有效、失败和阻塞样本都必须可追溯到原始响应或原始失败快照。",
    )
    unclassified_valid = sum(
        item.status == SampleStatus.VALID and item.mention_class == MentionClass.UNKNOWN
        for item in sample_list
    )
    add_check(
        "valid_mentions_classified",
        unclassified_valid == 0,
        unclassified_valid,
        "= 0 unknown",
        "有效样本必须明确区分推荐、候选、提及、负面和未提及。",
    )

    limitations: list[str] = []
    valid_samples = [item for item in sample_list if item.status == SampleStatus.VALID]
    if valid_samples and not any(item.citation_count > 0 for item in valid_samples):
        limitations.append("valid_samples_have_no_provider_citations")
    if valid_samples and not any(item.citation_support_score is not None for item in valid_samples):
        limitations.append("citation_support_not_evaluated")
    if valid_samples and not any(item.fact_accuracy is not None for item in valid_samples):
        limitations.append("fact_accuracy_not_evaluated")
    if metrics.stability is None:
        limitations.append("repeat_stability_unavailable")

    data_payload = {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "run_id": run_id,
        "signatures": signature_list,
        "samples": [
            {
                "sample_id": item.sample_id,
                "question_id": item.question_id,
                "status": item.status.value,
                "answer_sha256": item.answer_sha256,
                "raw_response_sha256": item.raw_response_sha256,
                "mention_class": item.mention_class.value,
                "brand_rank": item.brand_rank,
                "citation_count": item.citation_count,
                "failure_code": item.failure_code,
            }
            for item in sample_list
        ],
    }
    data_sha256 = canonical_json_sha256(data_payload)
    publishable = all(item.status != "blocked" for item in checks)
    report_payload = {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "run_id": run_id,
        "publishable": publishable,
        "data_sha256": data_sha256,
        "metrics": metrics.to_record(),
        "checks": [item.to_record() for item in checks],
        "known_limitations": limitations,
    }
    return MeasurementQualityReport(
        contract_version=QUALITY_CONTRACT_VERSION,
        run_id=run_id,
        status="pass" if publishable else "blocked",
        publishable=publishable,
        data_sha256=data_sha256,
        report_sha256=canonical_json_sha256(report_payload),
        metrics=metrics,
        checks=tuple(checks),
        known_limitations=tuple(limitations),
    )

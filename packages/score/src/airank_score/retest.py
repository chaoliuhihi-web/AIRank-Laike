from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Mapping

from .measurement import CohortMetrics


RATE_METRICS = (
    "valid_sample_rate",
    "mention_rate",
    "recommendation_rate",
    "top1_rate",
    "top3_rate",
    "top5_rate",
    "conditional_top3_rate",
    "stability",
    "citation_recall_rate",
    "citation_support",
    "fact_accuracy",
)


@dataclass(frozen=True)
class RetestComparison:
    baseline_run_id: str
    compare_run_id: str
    comparable: bool
    mismatch_reasons: tuple[str, ...]
    confidence: Literal["low", "medium"]
    baseline_metrics: CohortMetrics
    compare_metrics: CohortMetrics
    metric_deltas: Mapping[str, float | None]
    conclusion: str
    attribution_policy: str = "observational_non_causal.v1"

    def to_record(self) -> dict[str, object]:
        record = asdict(self)
        record["mismatch_reasons"] = list(self.mismatch_reasons)
        return record


def compare_retest_metrics(
    *,
    baseline_run_id: str,
    compare_run_id: str,
    baseline_metrics: CohortMetrics,
    compare_metrics: CohortMetrics,
    baseline_signature: tuple[str, ...],
    compare_signature: tuple[str, ...],
) -> RetestComparison:
    mismatch_reasons: list[str] = []
    if baseline_signature != compare_signature:
        mismatch_reasons.append("sample_contract_mismatch")
    if baseline_metrics.total_sample_count != compare_metrics.total_sample_count:
        mismatch_reasons.append("sample_count_mismatch")
    if baseline_metrics.valid_sample_count == 0 or compare_metrics.valid_sample_count == 0:
        mismatch_reasons.append("no_valid_samples")

    comparable = not mismatch_reasons
    enough_valid_samples = min(
        baseline_metrics.valid_sample_count,
        compare_metrics.valid_sample_count,
    ) >= 12
    healthy_sample_rate = min(
        baseline_metrics.valid_sample_rate,
        compare_metrics.valid_sample_rate,
    ) >= 0.8
    confidence: Literal["low", "medium"] = (
        "medium" if comparable and enough_valid_samples and healthy_sample_rate else "low"
    )

    metric_deltas: dict[str, float | None] = {}
    for metric_name in RATE_METRICS:
        before = getattr(baseline_metrics, metric_name)
        after = getattr(compare_metrics, metric_name)
        metric_deltas[metric_name] = (
            None if before is None or after is None else round(after - before, 6)
        )

    recommendation_delta = metric_deltas["recommendation_rate"]
    mention_delta = metric_deltas["mention_rate"]
    if not comparable:
        conclusion = (
            "基线与复测样本口径不一致，只能展示各自观测值，不能据此判断干预变化。"
            f"当前归因置信度为{confidence}。"
        )
    else:
        conclusion = (
            "在同口径样本中，观察到"
            f"提及率变化 {format_delta(mention_delta)}，"
            f"明确推荐率变化 {format_delta(recommendation_delta)}。"
            "该变化可能与发布干预相关，也可能受模型版本、联网结果和时间波动影响，"
            f"不能据此证明因果；当前归因置信度为{confidence}。"
        )

    return RetestComparison(
        baseline_run_id=baseline_run_id,
        compare_run_id=compare_run_id,
        comparable=comparable,
        mismatch_reasons=tuple(mismatch_reasons),
        confidence=confidence,
        baseline_metrics=baseline_metrics,
        compare_metrics=compare_metrics,
        metric_deltas=metric_deltas,
        conclusion=conclusion,
    )


def format_delta(value: float | None) -> str:
    if value is None:
        return "暂无可比数据"
    return f"{value * 100:+.1f} 个百分点"

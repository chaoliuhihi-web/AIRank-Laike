from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Iterable

from airank_domain.measurement import MeasurementSample, MentionClass, SampleStatus


@dataclass(frozen=True)
class CohortMetrics:
    total_sample_count: int
    valid_sample_count: int
    failed_sample_count: int
    blocked_sample_count: int
    valid_sample_rate: float
    not_mentioned_count: int
    mention_rate: float
    recommendation_rate: float
    top1_rate: float
    top3_rate: float
    top5_rate: float
    conditional_top3_rate: float | None
    ranked_sample_count: int
    stability: float | None
    citation_recall_rate: float
    citation_support: float | None
    fact_accuracy: float | None

    def to_record(self) -> dict[str, int | float | None]:
        return asdict(self)


def rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def calculate_cohort_metrics(samples: Iterable[MeasurementSample]) -> CohortMetrics:
    all_samples = list(samples)
    valid = [sample for sample in all_samples if sample.status == SampleStatus.VALID]
    failed = [sample for sample in all_samples if sample.status == SampleStatus.FAILED]
    blocked = [sample for sample in all_samples if sample.status == SampleStatus.BLOCKED]
    denominator = len(valid)

    mentioned_classes = {
        MentionClass.RECOMMENDED,
        MentionClass.CANDIDATE,
        MentionClass.MENTIONED,
        MentionClass.NEGATIVE,
    }
    mentioned = sum(sample.mention_class in mentioned_classes for sample in valid)
    recommended = sum(sample.mention_class == MentionClass.RECOMMENDED for sample in valid)
    not_mentioned = sum(sample.mention_class == MentionClass.NOT_MENTIONED for sample in valid)
    ranked = [sample for sample in valid if sample.brand_rank is not None]
    top1 = sum(sample.brand_rank == 1 for sample in valid)
    top3 = sum(sample.brand_rank is not None and sample.brand_rank <= 3 for sample in valid)
    top5 = sum(sample.brand_rank is not None and sample.brand_rank <= 5 for sample in valid)

    support_values = [sample.citation_support_score for sample in valid if sample.citation_support_score is not None]
    fact_values = [sample.fact_accuracy for sample in valid if sample.fact_accuracy is not None]
    citation_samples = sum(sample.citation_count > 0 for sample in valid)

    return CohortMetrics(
        total_sample_count=len(all_samples),
        valid_sample_count=denominator,
        failed_sample_count=len(failed),
        blocked_sample_count=len(blocked),
        valid_sample_rate=rate(denominator, len(all_samples)),
        not_mentioned_count=not_mentioned,
        mention_rate=rate(mentioned, denominator),
        recommendation_rate=rate(recommended, denominator),
        top1_rate=rate(top1, denominator),
        top3_rate=rate(top3, denominator),
        top5_rate=rate(top5, denominator),
        conditional_top3_rate=rate(top3, len(ranked)) if ranked else None,
        ranked_sample_count=len(ranked),
        stability=calculate_repeat_stability(valid),
        citation_recall_rate=rate(citation_samples, denominator),
        citation_support=round(fmean(support_values), 6) if support_values else None,
        fact_accuracy=round(fmean(fact_values), 6) if fact_values else None,
    )


def calculate_repeat_stability(samples: Iterable[MeasurementSample]) -> float | None:
    groups: dict[tuple[str, str, str, str], list[MeasurementSample]] = defaultdict(list)
    for sample in samples:
        key = (
            sample.question_id,
            sample.context.provider,
            sample.context.cohort_type.value,
            sample.context.surface.value,
        )
        groups[key].append(sample)

    agreements: list[float] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        outcomes = [(sample.mention_class.value, sample.brand_rank) for sample in group]
        modal_count = Counter(outcomes).most_common(1)[0][1]
        agreements.append(modal_count / len(group))
    return round(fmean(agreements), 6) if agreements else None

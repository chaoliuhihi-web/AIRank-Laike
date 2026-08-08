from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean


FINAL_REVIEW_STATUSES = frozenset({"agreed", "adjudicated"})


@dataclass(frozen=True)
class IndependentReviewPair:
    case_id: str
    review_kind: str
    primary_label: str | None
    secondary_label: str | None
    status: str
    adjudication_label: str | None = None

    def __post_init__(self) -> None:
        if self.review_kind not in {"citation_support", "fact_accuracy"}:
            raise ValueError("independent review kind is invalid")
        if self.status not in {
            "awaiting_secondary",
            "disputed",
            "agreed",
            "adjudicated",
            "void",
        }:
            raise ValueError("independent review status is invalid")
        if self.status in {"disputed", "agreed", "adjudicated"} and (
            not self.primary_label or not self.secondary_label
        ):
            raise ValueError("completed independent review requires two labels")
        if self.status == "agreed" and self.primary_label != self.secondary_label:
            raise ValueError("agreed review pair must have matching labels")
        if self.status == "disputed" and self.primary_label == self.secondary_label:
            raise ValueError("disputed review pair must have different labels")
        if self.status == "adjudicated" and not self.adjudication_label:
            raise ValueError("adjudicated review pair requires a final label")

    @property
    def independently_reviewed(self) -> bool:
        return bool(self.primary_label and self.secondary_label)

    @property
    def initial_agreement(self) -> bool | None:
        if not self.independently_reviewed:
            return None
        return self.primary_label == self.secondary_label

    @property
    def finalized(self) -> bool:
        return self.status in FINAL_REVIEW_STATUSES


@dataclass(frozen=True)
class ReviewQualityMetrics:
    case_count: int
    independently_reviewed_case_count: int
    finalized_case_count: int
    awaiting_secondary_count: int
    disputed_count: int
    agreement_count: int
    disagreement_count: int
    adjudicated_count: int
    raw_agreement_rate: float | None
    cohen_kappa: float | None
    benchmark_minimum_case_count: int
    benchmark_minimum_kappa: float
    benchmark_ready: bool
    benchmark_quality_passed: bool
    known_limitations: tuple[str, ...]


def calculate_review_quality_metrics(
    pairs: tuple[IndependentReviewPair, ...],
    *,
    benchmark_minimum_case_count: int = 20,
    benchmark_minimum_kappa: float = 0.8,
) -> ReviewQualityMetrics:
    if benchmark_minimum_case_count < 2:
        raise ValueError("benchmark minimum case count must be at least two")
    if not 0.0 <= benchmark_minimum_kappa <= 1.0:
        raise ValueError("benchmark minimum kappa must be between zero and one")
    active = tuple(pair for pair in pairs if pair.status != "void")
    reviewed = tuple(pair for pair in active if pair.independently_reviewed)
    agreements = tuple(pair for pair in reviewed if pair.initial_agreement is True)
    disagreements = tuple(pair for pair in reviewed if pair.initial_agreement is False)
    finalized = tuple(pair for pair in active if pair.finalized)

    raw_agreement_rate = (
        round(len(agreements) / len(reviewed), 6) if reviewed else None
    )
    cohen_kappa = _cohen_kappa(reviewed)
    limitations: list[str] = []
    if not active:
        limitations.append("review_benchmark_has_no_cases")
    if len(reviewed) < len(active):
        limitations.append("review_cases_awaiting_independent_second_review")
    if any(pair.status == "disputed" for pair in active):
        limitations.append("review_cases_awaiting_adjudication")
    if len(reviewed) < benchmark_minimum_case_count:
        limitations.append("review_benchmark_sample_too_small")
    if reviewed and cohen_kappa is None:
        limitations.append("review_benchmark_kappa_not_estimable")

    benchmark_ready = (
        len(reviewed) >= benchmark_minimum_case_count
        and len(finalized) == len(active)
        and cohen_kappa is not None
    )
    benchmark_quality_passed = bool(
        benchmark_ready
        and cohen_kappa is not None
        and cohen_kappa >= benchmark_minimum_kappa
    )
    if benchmark_ready and not benchmark_quality_passed:
        limitations.append("review_benchmark_kappa_below_threshold")
    return ReviewQualityMetrics(
        case_count=len(active),
        independently_reviewed_case_count=len(reviewed),
        finalized_case_count=len(finalized),
        awaiting_secondary_count=sum(
            pair.status == "awaiting_secondary" for pair in active
        ),
        disputed_count=sum(pair.status == "disputed" for pair in active),
        agreement_count=len(agreements),
        disagreement_count=len(disagreements),
        adjudicated_count=sum(pair.status == "adjudicated" for pair in active),
        raw_agreement_rate=raw_agreement_rate,
        cohen_kappa=cohen_kappa,
        benchmark_minimum_case_count=benchmark_minimum_case_count,
        benchmark_minimum_kappa=benchmark_minimum_kappa,
        benchmark_ready=benchmark_ready,
        benchmark_quality_passed=benchmark_quality_passed,
        known_limitations=tuple(limitations),
    )


def _cohen_kappa(pairs: tuple[IndependentReviewPair, ...]) -> float | None:
    if not pairs:
        return None
    labels = sorted(
        {
            str(label)
            for pair in pairs
            for label in (pair.primary_label, pair.secondary_label)
            if label is not None
        }
    )
    if len(labels) < 2:
        return None
    total = len(pairs)
    observed = fmean(
        1.0 if pair.primary_label == pair.secondary_label else 0.0
        for pair in pairs
    )
    expected = sum(
        (
            sum(pair.primary_label == label for pair in pairs) / total
        )
        * (
            sum(pair.secondary_label == label for pair in pairs) / total
        )
        for label in labels
    )
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else None
    return round((observed - expected) / (1.0 - expected), 6)

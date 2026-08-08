from __future__ import annotations

import pytest

from airank_evidence import IndependentReviewPair, calculate_review_quality_metrics


def pair(
    case_id: str,
    primary: str | None,
    secondary: str | None,
    status: str,
    adjudication: str | None = None,
) -> IndependentReviewPair:
    return IndependentReviewPair(
        case_id=case_id,
        review_kind="citation_support",
        primary_label=primary,
        secondary_label=secondary,
        status=status,
        adjudication_label=adjudication,
    )


def test_review_quality_keeps_pending_and_disputed_cases_out_of_ready_benchmark() -> None:
    metrics = calculate_review_quality_metrics(
        (
            pair("case_1", "supports", None, "awaiting_secondary"),
            pair("case_2", "supports", "contradicts", "disputed"),
            pair("case_3", "supports", "supports", "agreed"),
        ),
        benchmark_minimum_case_count=2,
    )

    assert metrics.case_count == 3
    assert metrics.independently_reviewed_case_count == 2
    assert metrics.finalized_case_count == 1
    assert metrics.raw_agreement_rate == 0.5
    assert metrics.cohen_kappa == 0.0
    assert metrics.benchmark_ready is False
    assert "review_cases_awaiting_independent_second_review" in metrics.known_limitations
    assert "review_cases_awaiting_adjudication" in metrics.known_limitations


def test_review_quality_computes_multiclass_kappa_from_real_pairs() -> None:
    metrics = calculate_review_quality_metrics(
        (
            pair("case_1", "supports", "supports", "agreed"),
            pair("case_2", "supports", "supports", "agreed"),
            pair("case_3", "contradicts", "contradicts", "agreed"),
            pair("case_4", "insufficient", "supports", "adjudicated", "supports"),
        ),
        benchmark_minimum_case_count=4,
    )

    assert metrics.raw_agreement_rate == 0.75
    assert metrics.cohen_kappa == pytest.approx(0.555556)
    assert metrics.adjudicated_count == 1
    assert metrics.benchmark_ready is True
    assert metrics.benchmark_quality_passed is False
    assert "review_benchmark_kappa_below_threshold" in metrics.known_limitations


def test_review_quality_passes_only_after_sample_and_kappa_thresholds() -> None:
    metrics = calculate_review_quality_metrics(
        tuple(
            pair(f"case_{index}", label, label, "agreed")
            for index, label in enumerate(
                ("supports", "contradicts", "insufficient", "supports"), start=1
            )
        ),
        benchmark_minimum_case_count=4,
    )

    assert metrics.benchmark_ready is True
    assert metrics.benchmark_minimum_kappa == 0.8
    assert metrics.cohen_kappa == 1.0
    assert metrics.benchmark_quality_passed is True


def test_invalid_agreement_state_is_rejected() -> None:
    with pytest.raises(ValueError, match="matching labels"):
        pair("case_bad", "supports", "contradicts", "agreed")

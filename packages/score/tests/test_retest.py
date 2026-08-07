from airank_score.measurement import CohortMetrics
from airank_score.retest import compare_retest_metrics


def metrics(*, valid: int, total: int, mention: float, recommend: float) -> CohortMetrics:
    return CohortMetrics(
        total_sample_count=total,
        valid_sample_count=valid,
        failed_sample_count=total - valid,
        blocked_sample_count=0,
        valid_sample_rate=valid / total,
        not_mentioned_count=valid - round(valid * mention),
        mention_rate=mention,
        recommendation_rate=recommend,
        top1_rate=0.1,
        top3_rate=0.2,
        top5_rate=0.3,
        conditional_top3_rate=0.4,
        ranked_sample_count=round(valid * 0.5),
        stability=0.8,
        citation_recall_rate=0.2,
        citation_support=None,
        fact_accuracy=None,
    )


def test_same_contract_reports_observed_delta_without_causal_claim() -> None:
    result = compare_retest_metrics(
        baseline_run_id="run_t0",
        compare_run_id="run_t7",
        baseline_metrics=metrics(valid=12, total=12, mention=0.25, recommend=0.1),
        compare_metrics=metrics(valid=12, total=12, mention=0.5, recommend=0.2),
        baseline_signature=("q1|qianwen|blind|api|1|prompt-v1",),
        compare_signature=("q1|qianwen|blind|api|1|prompt-v1",),
    )

    assert result.comparable is True
    assert result.confidence == "medium"
    assert result.metric_deltas["mention_rate"] == 0.25
    assert "观察到" in result.conclusion
    assert "可能与" in result.conclusion
    assert "不能据此证明因果" in result.conclusion


def test_different_contract_is_low_confidence_and_not_comparable() -> None:
    result = compare_retest_metrics(
        baseline_run_id="run_t0",
        compare_run_id="run_t7",
        baseline_metrics=metrics(valid=3, total=3, mention=0.0, recommend=0.0),
        compare_metrics=metrics(valid=3, total=3, mention=1.0, recommend=1.0),
        baseline_signature=("q1|qianwen|blind|api|1|prompt-v1",),
        compare_signature=("q1|doubao|assisted|api|1|prompt-v2",),
    )

    assert result.comparable is False
    assert result.confidence == "low"
    assert "sample_contract_mismatch" in result.mismatch_reasons
    assert "不能据此判断" in result.conclusion

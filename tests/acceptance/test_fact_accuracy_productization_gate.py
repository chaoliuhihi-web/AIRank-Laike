from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_fact_accuracy_has_immutable_domain_storage_and_api_contracts() -> None:
    migration = read("apps/api/alembic/versions/20260808_0019_fact_accuracy_reviews.py")
    domain = read("packages/evidence/src/airank_evidence/fact_accuracy.py")
    routes = read("apps/api/citation_support_routes.py")

    for token in (
        "airank_fact_accuracy_reviews",
        "fact_revision_sha256",
        "source_content_sha256",
        "quoted_text_sha256",
        "source_start",
        "source_end",
        "idempotency_key",
        "supersedes_review_id",
    ):
        assert token in migration
    assert "eligible_for_fact_accuracy" in domain
    assert "commercially_verified" in domain
    assert "decisive_count == factual_count" in domain
    assert '"/samples/{snapshot_id}/fact-accuracy"' in routes
    assert '"/answer-claims/{claim_id}/fact-accuracy-reviews"' in routes
    assert "sample.fact_accuracy_reviewed" in routes
    assert "load_fact_accuracy_bundles_from_connection" in routes
    assert (ROOT / "packages/contracts/fact_accuracy_review_request.schema.json").is_file()
    assert (ROOT / "packages/contracts/fact_accuracy_bundle_response.schema.json").is_file()


def test_fact_accuracy_is_recomputed_into_quality_and_customer_evidence_packet() -> None:
    retest = read("apps/api/retest_routes.py")
    quality = read("packages/score/src/airank_score/quality.py")
    report = read("packages/evidence/src/airank_evidence/report.py")
    repository = read("apps/api/report_packet.py")

    assert 'row["fact_accuracy"] = fact_metrics.fact_accuracy if fact_metrics else None' in retest
    assert 'row["fact_reviewed_claim_count"] = fact_metrics.decisive_claim_count if fact_metrics else 0' in retest
    assert '"fact_accuracy": item.fact_accuracy' in quality
    assert "airank.report-evidence-packet.v8" in report
    assert '"fact_accuracy_index": fact_accuracy_index' in report
    assert 'f"fact_accuracy_index {metric_name} does not match metrics' in report
    assert "review_record_sha256" in repository
    latest_review_fields = repository.split('latest_review = {', 1)[1].split('}', 1)[0]
    assert '"quoted_text":' not in latest_review_fields
    assert '"quoted_text_sha256":' in latest_review_fields


def test_console_exposes_honest_manual_fact_accuracy_workflow_without_demo_values() -> None:
    api = read("apps/web/src/console/api.ts")
    app = read("apps/web/src/App.tsx")

    for token in (
        "fetchFactAccuracy",
        "createFactEvidenceReviewCase",
        "fact_revision_id",
        "Idempotency-Key",
    ):
        assert token in api
    assert "createFactAccuracyReview" not in api
    for label in (
        "事实准确性 · 人工证据审核",
        "只有全部事实声明完成确定性人工核验后才输出准确率",
        "证据不足",
        "当前审核不进入商业指标",
    ):
        assert label in app
    assert "Math.random() * 100" not in app

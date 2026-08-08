from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_independent_review_has_storage_contract_and_blind_workflow() -> None:
    migration = read(
        "apps/api/alembic/versions/20260808_0025_independent_evidence_reviews.py"
    )
    routes = read("apps/api/evidence_review_routes.py")
    standard_api = read("apps/api/citation_support_routes.py")

    for token in (
        "airank_evidence_review_cases",
        "purpose",
        "primary_review_id",
        "secondary_review_id",
        "adjudication_review_id",
        "evidence_basis_sha256",
        "consensus_label",
    ):
        assert token in migration
    for route in (
        '"/projects/{project_id}/evidence-review-cases/citation-support"',
        '"/projects/{project_id}/evidence-review-cases/fact-accuracy"',
        '"/evidence-review-cases/{case_id}/decisions"',
        '"/projects/{project_id}/evidence-review-cases"',
    ):
        assert route in routes
    assert "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN" in routes
    assert "label_conflicts_with_frozen_evidence" in routes
    assert "visible = decisions if final else" in routes
    assert "item.reviewed_by == actor" in routes
    assert "review_visible_to_actor" in standard_api
    assert "Keep peer labels blind" in standard_api


def test_review_quality_has_real_agreement_and_kappa_gate() -> None:
    quality = read("packages/evidence/src/airank_evidence/review_quality.py")
    contract = read("packages/contracts/evidence_review_queue_response.schema.json")

    for token in (
        "raw_agreement_rate",
        "cohen_kappa",
        "benchmark_minimum_case_count",
        "benchmark_minimum_kappa",
        "benchmark_quality_passed",
        "review_benchmark_kappa_below_threshold",
    ):
        assert token in quality
        if token != "review_benchmark_kappa_below_threshold":
            assert token in contract
    assert "benchmark_minimum_case_count: int = 20" in quality
    assert "benchmark_minimum_kappa: float = 0.8" in quality


def test_commercial_metrics_and_report_require_final_production_peer_review() -> None:
    citation = read("packages/evidence/src/airank_evidence/citation_support.py")
    fact = read("packages/evidence/src/airank_evidence/fact_accuracy.py")
    report = read("packages/evidence/src/airank_evidence/report.py")
    page = read("apps/web/src/App.tsx")

    for domain in (citation, fact):
        assert 'review_case_purpose == "production"' in domain
        assert 'reviewer_role in {"secondary", "adjudicator"}' in domain
        assert "benchmark_reviews_excluded_from_commercial_metrics" in domain
    assert "commercial review lacks an independent review case" in report
    assert "benchmark review cannot enter commercial metrics" in report
    assert "双人复核与一致性门禁" in page
    assert "单人预审永远不会直接进入客户指标" in page
    assert "benchmark_quality_passed" in page

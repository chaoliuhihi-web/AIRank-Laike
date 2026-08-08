from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cross_domain_opportunities_are_immutable_and_evidence_scoped() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260809_0033_intervention_opportunities.py"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "apps" / "api" / "opportunity_routes.py").read_text(
        encoding="utf-8"
    )

    for required in (
        "airank_opportunity_derivation_runs",
        "airank_intervention_opportunity_snapshots",
        "source_basis_sha256",
        "source_evidence_sha256",
        "snapshot_sha256",
        "cleared_opportunity_ids_json",
    ):
        assert required in migration

    for source_kind in (
        'source_kind="brand_visibility"',
        'source_kind="citation_support"',
        'source_kind="fact_governance"',
        'source_kind="page_extractability"',
    ):
        assert source_kind in routes
    assert 'GAP_CONTRACT_VERSION = "airank.evidence-gap.v2"' in routes
    assert 'str(row["case_status"]) in {"agreed", "adjudicated"}' in routes
    assert 'str(row["evidence_grade"]) == "source_page_snapshot"' in routes
    assert "content_sha256 IS NOT NULL" in routes
    assert "系统不会自动选择有利版本" in routes
    assert "不是品牌推荐率或增长结论" in routes
    assert "不表示任何干预后必然获得模型推荐" in routes


def test_opportunity_score_is_not_a_recommendation_metric() -> None:
    routes = (ROOT / "apps" / "api" / "opportunity_routes.py").read_text(
        encoding="utf-8"
    )
    web = (
        ROOT / "apps" / "web" / "src" / "console" / "OpportunityBoard.tsx"
    ).read_text(encoding="utf-8")

    assert "SEVERITY_POINTS" in routes
    assert "EVIDENCE_POINTS" in routes
    assert "urgency_points" in routes
    assert "brand_recommendation_probability" not in routes
    # The frontend gate is intentionally added together with the API slice.
    assert 'data-testid="cross-domain-opportunity-board"' in web

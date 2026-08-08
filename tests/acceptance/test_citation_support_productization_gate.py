from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_citation_support_schema_preserves_claim_boundaries_and_append_only_reviews() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0013_citation_support_reviews.py"
    ).read_text(encoding="utf-8")
    for required in (
        "airank_answer_claims",
        "airank_citation_support_reviews",
        "answer_start",
        "answer_end",
        "answer_sha256",
        "claim_sha256",
        "support_label",
        "evidence_grade",
        "source_content_sha256",
        "source_object_ref_id",
        "review_method",
        "supersedes_review_id",
    ):
        assert required in migration


def test_only_human_reviewed_source_page_snapshots_enter_commercial_support_rate() -> None:
    evidence = (
        ROOT
        / "packages"
        / "evidence"
        / "src"
        / "airank_evidence"
        / "citation_support.py"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "apps" / "api" / "citation_support_routes.py").read_text(encoding="utf-8")

    assert "CitationSupportEvidenceGrade.SOURCE_PAGE_SNAPSHOT" in evidence
    assert 'self.review_method == "human"' in evidence
    assert "provisional_reviews_excluded_from_support_rate" in evidence
    assert 'metadata.get("kind") != "citation_source_page"' in routes
    assert 'metadata.get("citation_id") != payload.citation_id' in routes


def test_frontend_never_equates_selected_citations_with_support() -> None:
    app = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    api = (ROOT / "apps" / "web" / "src" / "console" / "api.ts").read_text(encoding="utf-8")

    assert "引用选择 ≠ 引用支持" in app
    assert "人工核对 + 不可变来源页面" in app
    assert "可交付支持率" in app
    assert "fetchCitationSupport" in api

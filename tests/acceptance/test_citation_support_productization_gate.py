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
    assert 'metadata.get("capture_id") != payload.source_capture_id' in routes
    for required in (
        "source_capture_id",
        "source_segment_id",
        "source_start",
        "source_end",
        "exact_source_excerpt",
    ):
        assert required in evidence or required in routes


def test_citation_source_pages_are_captured_as_immutable_worker_evidence() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0014_citation_source_captures.py"
    ).read_text(encoding="utf-8")
    route = (ROOT / "apps" / "api" / "citation_capture_routes.py").read_text(encoding="utf-8")
    worker = (
        ROOT / "apps" / "worker" / "airank_worker" / "citation_capture.py"
    ).read_text(encoding="utf-8")
    crawler = (
        ROOT
        / "packages"
        / "crawler-lite"
        / "src"
        / "airank_crawler_lite"
        / "source_capture.py"
    ).read_text(encoding="utf-8")

    for required in (
        "airank_citation_source_captures",
        "airank_citation_source_segments",
        "raw_object_ref_id",
        "visible_text_sha256",
    ):
        assert required in migration
    assert "citation.capture" in route
    assert "source_page_dns_pinned" in crawler
    assert '"kind": "citation_source_page"' in worker
    assert '"kind": "citation_source_text"' in worker
    assert "stored citation object hash does not match capture result" in worker


def test_frontend_never_equates_selected_citations_with_support() -> None:
    app = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    api = (ROOT / "apps" / "web" / "src" / "console" / "api.ts").read_text(encoding="utf-8")

    assert "引用选择 ≠ 引用支持" in app
    assert "不可变来源页面 + 不同审核人一致/裁决" in app
    assert "可交付支持率" in app
    assert "fetchCitationSupport" in api
    assert "抓取来源页" in app
    assert "原文边界" in app
    assert "createCitationEvidenceReviewCase" in api
    assert "createCitationSupportReview" not in api
    assert "createCitationSourceCaptureBatch" in api
    assert "fetchLatestCitationSourceCaptures" in api
    assert "批量准备来源正文" in app
    assert "抓取成功只代表页面已存证，不代表来源支持回答" in app
    assert "const detail = await fetchCitationSourceCapture(captureId);" in app
    assert "selected.snapshot_id, controller.signal" in app

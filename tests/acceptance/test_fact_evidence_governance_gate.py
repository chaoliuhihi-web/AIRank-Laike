from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from airank_domain import (
    ClaimAssertion,
    ClaimStatus,
    ClaimSupport,
    ClaimSupportType,
    FactRevision,
    FactRevisionStatus,
    approve_fact_revision,
    sha256_text,
    verify_claim_assertion,
)
from airank_evidence import EvidenceSnapshot


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def test_fact_claim_requires_reviewed_current_evidence() -> None:
    proposed = FactRevision(
        id="revision_1",
        tenant_id="tenant_1",
        project_id="project_1",
        fact_atom_id="fact_1",
        revision_number=1,
        fact_text="AIRank 支持私有化部署。",
        status=FactRevisionStatus.PROPOSED,
        source_ids=(),
        content_sha256=sha256_text("AIRank 支持私有化部署。"),
        created_by="operator_1",
        created_at=NOW,
    )
    assertion = ClaimAssertion(
        id="claim_1",
        tenant_id="tenant_1",
        project_id="project_1",
        claim_text=proposed.fact_text,
        status=ClaimStatus.DRAFT,
        created_at=NOW,
    )
    support = ClaimSupport(
        id="support_1",
        tenant_id="tenant_1",
        project_id="project_1",
        assertion_id=assertion.id,
        fact_revision_id=proposed.id,
        knowledge_source_id="source_1",
        support_type=ClaimSupportType.SUPPORTS,
        quoted_text=proposed.fact_text,
        source_start=12,
        source_end=25,
        support_score=1.0,
        created_at=NOW,
    )

    before_review = verify_claim_assertion(
        assertion,
        supports=(support,),
        approved_revisions=(proposed,),
        open_conflicts=(),
        verified_by="reviewer_2",
        verified_at=NOW,
    )
    assert before_review.status == ClaimStatus.NEEDS_EVIDENCE

    approved = approve_fact_revision(
        proposed,
        source_ids=(support.knowledge_source_id,),
        reviewed_by="reviewer_1",
        reviewed_at=NOW,
    )
    after_review = verify_claim_assertion(
        assertion,
        supports=(support,),
        approved_revisions=(approved,),
        open_conflicts=(),
        verified_by="reviewer_2",
        verified_at=NOW,
    )
    assert after_review.status == ClaimStatus.VERIFIED


def test_raw_provider_response_is_content_addressed() -> None:
    snapshot = EvidenceSnapshot.create(
        id="evidence_1",
        tenant_id="tenant_1",
        project_id="project_1",
        answer_snapshot_id="answer_1",
        raw_response={"provider": "qianwen", "answer": "原始回答"},
        captured_at=NOW,
        screenshot_ref_id="object_screenshot_1",
        source_panel_ref_id="object_sources_1",
    )

    assert snapshot.verify_integrity() is True
    assert len(snapshot.raw_response_sha256) == 64
    assert snapshot.screenshot_ref_id == "object_screenshot_1"
    assert snapshot.source_panel_ref_id == "object_sources_1"


def test_fact_governance_migration_contains_required_domain_objects() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0004_fact_evidence_governance.py"
    ).read_text(encoding="utf-8")

    required = (
        "airank_knowledge_sources",
        "airank_fact_revisions",
        "airank_fact_conflicts",
        "airank_claim_assertions",
        "airank_claim_supports",
        "source_start",
        "source_end",
        "valid_until",
        "current_revision_id",
        "risk_level",
    )
    for name in required:
        assert name in migration


def test_knowledge_ingestion_migration_preserves_raw_content_and_exact_boundaries() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0006_knowledge_ingestion.py"
    ).read_text(encoding="utf-8")

    required = (
        "airank_knowledge_source_contents",
        "airank_knowledge_segments",
        "content_sha256",
        "source_start",
        "source_end",
        "idempotency_key",
        "embedding_status",
        "fk_airank_fact_current_revision",
    )
    for name in required:
        assert name in migration


def test_knowledge_governance_openapi_exposes_review_and_conflict_workflow() -> None:
    source = (ROOT / "apps" / "api" / "knowledge_routes.py").read_text(encoding="utf-8")

    required_routes = (
        '/projects/{project_id}/knowledge-sources',
        '/projects/{project_id}/knowledge-sources/{source_id}/revisions',
        '/projects/{project_id}/knowledge-search',
        '/projects/{project_id}/facts',
        '/projects/{project_id}/facts/{fact_id}/revisions',
        '/projects/{project_id}/fact-revisions/{revision_id}/review',
        '/projects/{project_id}/facts/{fact_id}/conflicts',
        '/projects/{project_id}/fact-conflicts/{conflict_id}/resolve',
        '/projects/{project_id}/content-assets',
    )
    for route in required_routes:
        assert route in source


def test_delivery_governance_has_review_snapshot_idempotency_and_retest_windows() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0007_delivery_governance.py"
    ).read_text(encoding="utf-8")

    required = (
        "airank_content_reviews",
        "airank_publish_snapshots",
        "airank_publish_attempts",
        "airank_retest_observation_windows",
        "idempotency_key",
        "content_sha256",
        "T+30",
    )
    for name in required:
        assert name in migration or name in (ROOT / "apps" / "api" / "delivery_routes.py").read_text(encoding="utf-8")


def test_retest_attribution_requires_same_contract_and_cautious_language() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0008_retest_attribution.py"
    ).read_text(encoding="utf-8")
    route = (ROOT / "apps" / "api" / "retest_routes.py").read_text(encoding="utf-8")
    scorer = (ROOT / "packages" / "score" / "src" / "airank_score" / "retest.py").read_text(encoding="utf-8")

    for name in (
        "observation_window_id",
        "comparison_contract_version",
        "report_sha256",
        "evidence_index_json",
    ):
        assert name in migration
    assert '/retest-windows/{window_id}/complete' in route
    assert "sample_contract_mismatch" in scorer
    assert "不能据此证明因果" in scorer


def test_question_governance_has_version_provenance_review_and_cohort_gates() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0009_question_governance.py"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "apps" / "api" / "question_routes.py").read_text(encoding="utf-8")
    main = (ROOT / "apps" / "api" / "main.py").read_text(encoding="utf-8")

    for name in (
        "airank_question_maps",
        "airank_buyer_question_revisions",
        "airank_buyer_question_reviews",
        "question_version_id",
        "taxonomy_version",
        "dedupe_sha256",
        "source_kind",
        "observed_query",
    ):
        assert name in migration
    assert "context.is_offline_mode()" in migration
    assert "/question-maps/compile" in routes
    assert "/buyer-questions/{question_id}/review" in routes
    assert 'row["status"] == "confirmed" and row["cohort_type"] == cohort_type' in main


def test_question_observation_batches_preserve_provenance_and_block_pii() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0010_question_observations.py"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "apps" / "api" / "question_routes.py").read_text(encoding="utf-8")

    for name in (
        "airank_question_observation_batches",
        "airank_question_observations",
        "payload_sha256",
        "content_sha256",
        "evidence_grade",
        "rights_attested",
        "pii_blocked_count",
    ):
        assert name in migration
    assert "/question-observation-batches" in routes
    assert "customer_provided_not_independently_verified" in routes
    assert "occurrence_count_is_source_frequency_not_search_volume" in routes
    assert "detected_pii_reasons" in routes

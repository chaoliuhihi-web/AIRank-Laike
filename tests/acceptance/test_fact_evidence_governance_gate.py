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

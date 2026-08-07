from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from airank_domain import (
    ClaimAssertion,
    ClaimStatus,
    ClaimSupport,
    ClaimSupportType,
    ConflictStatus,
    FactConflict,
    FactRevision,
    FactRevisionStatus,
    KnowledgeSource,
    SourceStatus,
    approve_fact_revision,
    verify_claim_assertion,
)
from airank_domain.measurement import sha256_text


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def proposed_revision() -> FactRevision:
    return FactRevision(
        id="factrev_1",
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


def support(support_type: ClaimSupportType = ClaimSupportType.SUPPORTS) -> ClaimSupport:
    return ClaimSupport(
        id=f"support_{support_type.value}",
        tenant_id="tenant_1",
        project_id="project_1",
        assertion_id="claim_1",
        fact_revision_id="factrev_1",
        knowledge_source_id="source_1",
        support_type=support_type,
        quoted_text="AIRank 支持私有化部署。",
        source_start=20,
        source_end=34,
        support_score=1.0,
        created_at=NOW,
    )


def test_knowledge_source_enforces_hash_revision_and_validity() -> None:
    source = KnowledgeSource(
        id="source_1",
        tenant_id="tenant_1",
        project_id="project_1",
        source_type="official_website",
        title="产品说明",
        source_uri="https://example.com/product",
        content_sha256=sha256_text("source"),
        authority_level="official",
        risk_level="low",
        status=SourceStatus.ACTIVE,
        revision_number=1,
        captured_at=NOW,
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
    )

    assert source.is_current_at(NOW) is True
    assert source.is_current_at(NOW + timedelta(days=31)) is False


def test_fact_revision_requires_sources_and_human_review_before_approval() -> None:
    with pytest.raises(ValueError, match="requires source_ids"):
        FactRevision(
            **{**proposed_revision().__dict__, "status": FactRevisionStatus.APPROVED}
        )

    approved = approve_fact_revision(
        proposed_revision(),
        source_ids=("source_1",),
        reviewed_by="reviewer_1",
        reviewed_at=NOW,
    )

    assert approved.status == FactRevisionStatus.APPROVED
    assert approved.is_approved_at(NOW) is True


def test_claim_verification_requires_approved_revision_and_blocks_open_conflict() -> None:
    assertion = ClaimAssertion(
        id="claim_1",
        tenant_id="tenant_1",
        project_id="project_1",
        claim_text="AIRank 支持私有化部署。",
        status=ClaimStatus.DRAFT,
        created_at=NOW,
    )
    approved = approve_fact_revision(
        proposed_revision(), source_ids=("source_1",), reviewed_by="reviewer_1", reviewed_at=NOW
    )

    verified = verify_claim_assertion(
        assertion,
        supports=(support(),),
        approved_revisions=(approved,),
        open_conflicts=(),
        verified_by="reviewer_2",
        verified_at=NOW,
    )
    assert verified.status == ClaimStatus.VERIFIED

    conflict = FactConflict(
        id="conflict_1",
        tenant_id="tenant_1",
        project_id="project_1",
        fact_atom_id="fact_1",
        left_revision_id="factrev_1",
        right_revision_id="factrev_2",
        conflict_type="value_mismatch",
        description="部署能力描述冲突",
        status=ConflictStatus.OPEN,
        detected_at=NOW,
    )
    blocked = verify_claim_assertion(
        assertion,
        supports=(support(),),
        approved_revisions=(approved,),
        open_conflicts=(conflict,),
        verified_by="reviewer_2",
        verified_at=NOW,
    )
    assert blocked.status == ClaimStatus.BLOCKED_CONFLICT

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum


class SourceStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    DISABLED = "disabled"


class FactRevisionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class ConflictStatus(str, Enum):
    OPEN = "open"
    RESOLVED_LEFT = "resolved_left"
    RESOLVED_RIGHT = "resolved_right"
    RESOLVED_NEW_REVISION = "resolved_new_revision"
    DISMISSED = "dismissed"


class ClaimStatus(str, Enum):
    DRAFT = "draft"
    VERIFIED = "verified"
    NEEDS_EVIDENCE = "needs_evidence"
    BLOCKED_CONFLICT = "blocked_conflict"


class ClaimSupportType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class KnowledgeSource:
    id: str
    tenant_id: str
    project_id: str
    source_type: str
    title: str
    source_uri: str
    content_sha256: str
    authority_level: str
    risk_level: str
    status: SourceStatus
    revision_number: int
    captured_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    object_ref_id: str | None = None
    parent_source_id: str | None = None

    def __post_init__(self) -> None:
        if self.revision_number < 1:
            raise ValueError("KnowledgeSource revision_number must be positive")
        if len(self.content_sha256) != 64:
            raise ValueError("KnowledgeSource content_sha256 must be SHA-256")
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("KnowledgeSource valid_until must be later than valid_from")
        if not self.source_uri and not self.object_ref_id:
            raise ValueError("KnowledgeSource requires source_uri or object_ref_id")

    def is_current_at(self, at: datetime) -> bool:
        if self.status != SourceStatus.ACTIVE:
            return False
        if self.valid_from and at < self.valid_from:
            return False
        if self.valid_until and at >= self.valid_until:
            return False
        return True


@dataclass(frozen=True)
class FactRevision:
    id: str
    tenant_id: str
    project_id: str
    fact_atom_id: str
    revision_number: int
    fact_text: str
    status: FactRevisionStatus
    source_ids: tuple[str, ...]
    content_sha256: str
    created_by: str
    created_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None

    def __post_init__(self) -> None:
        if self.revision_number < 1:
            raise ValueError("FactRevision revision_number must be positive")
        if not self.fact_text.strip():
            raise ValueError("FactRevision fact_text is required")
        if len(self.content_sha256) != 64:
            raise ValueError("FactRevision content_sha256 must be SHA-256")
        if self.status == FactRevisionStatus.APPROVED:
            if not self.source_ids:
                raise ValueError("approved FactRevision requires source_ids")
            if not self.reviewed_by or not self.reviewed_at:
                raise ValueError("approved FactRevision requires human review")
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("FactRevision valid_until must be later than valid_from")

    def is_approved_at(self, at: datetime) -> bool:
        if self.status != FactRevisionStatus.APPROVED:
            return False
        if self.valid_from and at < self.valid_from:
            return False
        if self.valid_until and at >= self.valid_until:
            return False
        return True


def approve_fact_revision(
    revision: FactRevision,
    *,
    source_ids: tuple[str, ...],
    reviewed_by: str,
    reviewed_at: datetime,
    review_note: str | None = None,
) -> FactRevision:
    if not source_ids:
        raise ValueError("cannot approve FactRevision without source_ids")
    return replace(
        revision,
        status=FactRevisionStatus.APPROVED,
        source_ids=source_ids,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        review_note=review_note,
    )


@dataclass(frozen=True)
class FactConflict:
    id: str
    tenant_id: str
    project_id: str
    fact_atom_id: str
    left_revision_id: str
    right_revision_id: str
    conflict_type: str
    description: str
    status: ConflictStatus
    detected_at: datetime
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None

    def __post_init__(self) -> None:
        if self.left_revision_id == self.right_revision_id:
            raise ValueError("FactConflict revisions must be different")
        is_resolved = self.status != ConflictStatus.OPEN
        if is_resolved and (not self.resolved_by or not self.resolved_at):
            raise ValueError("resolved FactConflict requires resolver and resolved_at")
        if not is_resolved and (self.resolved_by or self.resolved_at):
            raise ValueError("open FactConflict cannot include resolution fields")


@dataclass(frozen=True)
class ClaimSupport:
    id: str
    tenant_id: str
    project_id: str
    assertion_id: str
    fact_revision_id: str
    knowledge_source_id: str
    support_type: ClaimSupportType
    quoted_text: str
    source_start: int
    source_end: int
    support_score: float | None
    created_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.source_start < 0 or self.source_end <= self.source_start:
            raise ValueError("ClaimSupport requires a valid source text boundary")
        if not self.quoted_text.strip():
            raise ValueError("ClaimSupport requires quoted_text")
        if self.support_score is not None and not 0 <= self.support_score <= 1:
            raise ValueError("ClaimSupport support_score must be between 0 and 1")


@dataclass(frozen=True)
class ClaimAssertion:
    id: str
    tenant_id: str
    project_id: str
    claim_text: str
    status: ClaimStatus
    created_at: datetime
    asset_id: str | None = None
    supports: tuple[ClaimSupport, ...] = ()
    verified_by: str | None = None
    verified_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.claim_text.strip():
            raise ValueError("ClaimAssertion claim_text is required")
        supporting = [support for support in self.supports if support.support_type == ClaimSupportType.SUPPORTS]
        contradictory = [support for support in self.supports if support.support_type == ClaimSupportType.CONTRADICTS]
        if self.status == ClaimStatus.VERIFIED:
            if not supporting or contradictory:
                raise ValueError("verified ClaimAssertion requires support and no contradiction")
            if not self.verified_by or not self.verified_at:
                raise ValueError("verified ClaimAssertion requires verifier and verified_at")


def verify_claim_assertion(
    assertion: ClaimAssertion,
    *,
    supports: tuple[ClaimSupport, ...],
    approved_revisions: tuple[FactRevision, ...],
    open_conflicts: tuple[FactConflict, ...],
    verified_by: str,
    verified_at: datetime,
) -> ClaimAssertion:
    approved_ids = {
        revision.id for revision in approved_revisions if revision.is_approved_at(verified_at)
    }
    if any(conflict.status == ConflictStatus.OPEN for conflict in open_conflicts):
        return replace(assertion, status=ClaimStatus.BLOCKED_CONFLICT, supports=supports)
    usable = tuple(
        support
        for support in supports
        if support.fact_revision_id in approved_ids and support.support_type == ClaimSupportType.SUPPORTS
    )
    if not usable:
        return replace(assertion, status=ClaimStatus.NEEDS_EVIDENCE, supports=supports)
    if any(support.support_type == ClaimSupportType.CONTRADICTS for support in supports):
        return replace(assertion, status=ClaimStatus.BLOCKED_CONFLICT, supports=supports)
    return replace(
        assertion,
        status=ClaimStatus.VERIFIED,
        supports=usable,
        verified_by=verified_by,
        verified_at=verified_at,
    )

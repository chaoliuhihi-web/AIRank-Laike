from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from statistics import fmean

from airank_domain.measurement import sha256_text

from .fact_accuracy import AnswerClaimKind
from .review_quality import FINAL_REVIEW_STATUSES


class CitationSupportLabel(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    INSUFFICIENT = "insufficient"


class CitationSupportEvidenceGrade(str, Enum):
    PROVIDER_EXCERPT_ONLY = "provider_excerpt_only"
    SOURCE_PANEL_CAPTURE = "source_panel_capture"
    SOURCE_PAGE_SNAPSHOT = "source_page_snapshot"


@dataclass(frozen=True)
class CitationClaim:
    id: str
    tenant_id: str
    project_id: str
    snapshot_id: str
    claim_text: str
    answer_start: int
    answer_end: int
    answer_sha256: str
    created_by: str
    created_at: datetime
    claim_kind: AnswerClaimKind = AnswerClaimKind.UNCLASSIFIED
    subject_entity_text: str | None = None

    @classmethod
    def from_answer(
        cls,
        *,
        id: str,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
        answer_text: str,
        answer_start: int,
        answer_end: int,
        created_by: str,
        created_at: datetime,
        claim_kind: AnswerClaimKind = AnswerClaimKind.UNCLASSIFIED,
        subject_entity_text: str | None = None,
    ) -> "CitationClaim":
        if answer_start < 0 or answer_end <= answer_start or answer_end > len(answer_text):
            raise ValueError("citation claim requires a valid answer boundary")
        claim_text = answer_text[answer_start:answer_end]
        if not claim_text.strip():
            raise ValueError("citation claim cannot be blank")
        return cls(
            id=id,
            tenant_id=tenant_id,
            project_id=project_id,
            snapshot_id=snapshot_id,
            claim_text=claim_text,
            answer_start=answer_start,
            answer_end=answer_end,
            answer_sha256=sha256_text(answer_text.strip()),
            created_by=created_by,
            created_at=created_at,
            claim_kind=claim_kind,
            subject_entity_text=subject_entity_text,
        )

    def verify_answer(self, answer_text: str) -> bool:
        return (
            sha256_text(answer_text.strip()) == self.answer_sha256
            and answer_text[self.answer_start : self.answer_end] == self.claim_text
        )


@dataclass(frozen=True)
class CitationSupportReview:
    id: str
    tenant_id: str
    project_id: str
    claim_id: str
    citation_id: str
    label: CitationSupportLabel
    evidence_grade: CitationSupportEvidenceGrade
    source_excerpt: str
    source_content_sha256: str
    source_object_ref_id: str | None
    rationale: str
    review_method: str
    reviewed_by: str
    reviewed_at: datetime
    source_capture_id: str | None = None
    source_segment_id: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    review_case_id: str | None = None
    reviewer_role: str = "single"
    review_case_status: str = "single_review"
    review_case_purpose: str = "single_review"

    def __post_init__(self) -> None:
        if not self.source_excerpt.strip():
            raise ValueError("citation support review requires a source excerpt")
        if re.fullmatch(r"[0-9a-f]{64}", self.source_content_sha256) is None:
            raise ValueError("citation support review requires a source content SHA-256")
        if not self.rationale.strip():
            raise ValueError("citation support review requires rationale")
        if self.review_method not in {"human", "ai_assisted"}:
            raise ValueError("citation support review method is invalid")
        if self.evidence_grade == CitationSupportEvidenceGrade.SOURCE_PAGE_SNAPSHOT:
            if not all(
                (
                    self.source_object_ref_id,
                    self.source_capture_id,
                    self.source_segment_id,
                )
            ):
                raise ValueError(
                    "source page support requires an immutable capture, object, and segment"
                )
            if (
                self.source_start is None
                or self.source_end is None
                or self.source_start < 0
                or self.source_end <= self.source_start
            ):
                raise ValueError("source page support requires an exact source boundary")

    @property
    def evidence_verified(self) -> bool:
        return (
            self.evidence_grade == CitationSupportEvidenceGrade.SOURCE_PAGE_SNAPSHOT
            and self.review_method == "human"
            and self.source_capture_id is not None
            and self.source_segment_id is not None
            and self.source_start is not None
            and self.source_end is not None
        )

    @property
    def commercially_verified(self) -> bool:
        return (
            self.evidence_verified
            and self.review_case_id is not None
            and self.reviewer_role in {"secondary", "adjudicator"}
            and self.review_case_status in FINAL_REVIEW_STATUSES
            and self.review_case_purpose == "production"
        )


@dataclass(frozen=True)
class CitationSupportMetrics:
    selected_citation_count: int
    claim_count: int
    review_count: int
    commercially_verified_review_count: int
    supports_count: int
    contradicts_count: int
    insufficient_count: int
    citation_support_rate: float | None
    known_limitations: tuple[str, ...]


def calculate_citation_support_metrics(
    *,
    selected_citation_ids: tuple[str, ...],
    claims: tuple[CitationClaim, ...],
    reviews: tuple[CitationSupportReview, ...],
) -> CitationSupportMetrics:
    claim_ids = {claim.id for claim in claims}
    citation_ids = set(selected_citation_ids)
    if any(review.claim_id not in claim_ids for review in reviews):
        raise ValueError("citation support review references an unknown claim")
    if any(review.citation_id not in citation_ids for review in reviews):
        raise ValueError("citation support review references an unselected citation")
    benchmark_reviews = tuple(
        review for review in reviews if review.review_case_purpose == "benchmark"
    )
    latest_by_pair: dict[tuple[str, str], CitationSupportReview] = {}
    for review in sorted(
        (item for item in reviews if item.review_case_purpose != "benchmark"),
        key=lambda item: (item.reviewed_at, item.id),
    ):
        latest_by_pair[(review.claim_id, review.citation_id)] = review
    current = tuple(latest_by_pair.values())
    verified = tuple(review for review in current if review.commercially_verified)
    supports = sum(review.label == CitationSupportLabel.SUPPORTS for review in verified)
    contradicts = sum(review.label == CitationSupportLabel.CONTRADICTS for review in verified)
    insufficient = sum(review.label == CitationSupportLabel.INSUFFICIENT for review in verified)
    rates = [1.0 if review.label == CitationSupportLabel.SUPPORTS else 0.0 for review in verified]
    limitations: list[str] = []
    if selected_citation_ids and not claims:
        limitations.append("selected_citations_have_no_answer_claims")
    if claims and not current:
        limitations.append("citation_support_not_reviewed")
    if benchmark_reviews:
        limitations.append("benchmark_reviews_excluded_from_commercial_metrics")
    if current and not verified:
        limitations.append("citation_support_has_no_source_page_snapshot")
        if any(review.review_case_status not in FINAL_REVIEW_STATUSES for review in current):
            limitations.append("citation_support_independent_review_required")
    if len(verified) < len(current):
        limitations.append("provisional_reviews_excluded_from_support_rate")
    return CitationSupportMetrics(
        selected_citation_count=len(citation_ids),
        claim_count=len(claims),
        review_count=len(current),
        commercially_verified_review_count=len(verified),
        supports_count=supports,
        contradicts_count=contradicts,
        insufficient_count=insufficient,
        citation_support_rate=round(fmean(rates), 6) if rates else None,
        known_limitations=tuple(limitations),
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from statistics import fmean

from .review_quality import FINAL_REVIEW_STATUSES


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AnswerClaimKind(str, Enum):
    UNCLASSIFIED = "unclassified"
    BRAND_FACT = "brand_fact"
    COMPETITOR_FACT = "competitor_fact"
    GENERAL_FACT = "general_fact"
    OPINION = "opinion"

    @property
    def eligible_for_fact_accuracy(self) -> bool:
        return self in {self.BRAND_FACT, self.COMPETITOR_FACT}


class FactAccuracyVerdict(str, Enum):
    ACCURATE = "accurate"
    INACCURATE = "inaccurate"
    OUTDATED = "outdated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

    @property
    def decisive(self) -> bool:
        return self != self.INSUFFICIENT_EVIDENCE

    @property
    def score(self) -> float | None:
        if self == self.ACCURATE:
            return 1.0
        if self in {self.INACCURATE, self.OUTDATED}:
            return 0.0
        return None


class FactAccuracyEvidenceGrade(str, Enum):
    APPROVED_FACT_SOURCE_BOUNDARY = "approved_fact_source_boundary"
    NO_APPROVED_FACT = "no_approved_fact"


@dataclass(frozen=True)
class FactAccuracyClaim:
    id: str
    snapshot_id: str
    claim_kind: AnswerClaimKind
    claim_text: str
    claim_sha256: str
    answer_start: int
    answer_end: int
    subject_entity_text: str | None = None

    def __post_init__(self) -> None:
        if not self.claim_text.strip():
            raise ValueError("fact accuracy claim text is required")
        if self.answer_start < 0 or self.answer_end <= self.answer_start:
            raise ValueError("fact accuracy claim requires a valid answer boundary")
        if not SHA256_RE.fullmatch(self.claim_sha256):
            raise ValueError("fact accuracy claim requires claim SHA-256")


@dataclass(frozen=True)
class FactAccuracyReview:
    id: str
    claim_id: str
    verdict: FactAccuracyVerdict
    evidence_grade: FactAccuracyEvidenceGrade
    rationale: str
    review_method: str
    reviewed_by: str
    reviewed_at: datetime
    fact_revision_id: str | None = None
    knowledge_source_id: str | None = None
    knowledge_segment_id: str | None = None
    fact_revision_sha256: str | None = None
    source_content_sha256: str | None = None
    quoted_text_sha256: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    supersedes_review_id: str | None = None
    fact_revision_current: bool = False
    source_current: bool = False
    no_open_conflict: bool = False
    exact_boundary_verified: bool = False
    review_case_id: str | None = None
    reviewer_role: str = "single"
    review_case_status: str = "single_review"
    review_case_purpose: str = "single_review"

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError("fact accuracy review requires rationale")
        if self.review_method not in {"human", "ai_assisted"}:
            raise ValueError("fact accuracy review method is invalid")
        if self.evidence_grade == FactAccuracyEvidenceGrade.NO_APPROVED_FACT:
            if self.verdict != FactAccuracyVerdict.INSUFFICIENT_EVIDENCE:
                raise ValueError("no-approved-fact evidence can only be insufficient")
            return
        required_text = (
            self.fact_revision_id,
            self.knowledge_source_id,
            self.knowledge_segment_id,
            self.fact_revision_sha256,
            self.source_content_sha256,
            self.quoted_text_sha256,
        )
        if not all(required_text):
            raise ValueError("fact accuracy review requires approved fact source evidence")
        for digest in (
            self.fact_revision_sha256,
            self.source_content_sha256,
            self.quoted_text_sha256,
        ):
            if not SHA256_RE.fullmatch(str(digest or "")):
                raise ValueError("fact accuracy review contains an invalid SHA-256")
        if (
            self.source_start is None
            or self.source_end is None
            or self.source_start < 0
            or self.source_end <= self.source_start
        ):
            raise ValueError("fact accuracy review requires an exact source boundary")

    @property
    def evidence_verified(self) -> bool:
        return (
            self.evidence_grade
            == FactAccuracyEvidenceGrade.APPROVED_FACT_SOURCE_BOUNDARY
            and self.review_method == "human"
            and self.fact_revision_current
            and self.source_current
            and self.no_open_conflict
            and self.exact_boundary_verified
        )

    @property
    def commercially_verified(self) -> bool:
        return (
            self.evidence_verified
            and self.verdict.decisive
            and self.review_case_id is not None
            and self.reviewer_role in {"secondary", "adjudicator"}
            and self.review_case_status in FINAL_REVIEW_STATUSES
            and self.review_case_purpose == "production"
        )


@dataclass(frozen=True)
class FactAccuracyMetrics:
    registered_claim_count: int
    factual_claim_count: int
    reviewed_claim_count: int
    commercially_verified_claim_count: int
    decisive_claim_count: int
    accurate_count: int
    inaccurate_count: int
    outdated_count: int
    insufficient_evidence_count: int
    evaluation_coverage_rate: float | None
    fact_accuracy: float | None
    known_limitations: tuple[str, ...]


def calculate_fact_accuracy_metrics(
    *,
    claims: tuple[FactAccuracyClaim, ...],
    reviews: tuple[FactAccuracyReview, ...],
) -> FactAccuracyMetrics:
    claim_ids = {claim.id for claim in claims}
    if any(review.claim_id not in claim_ids for review in reviews):
        raise ValueError("fact accuracy review references an unknown claim")

    factual_claims = tuple(
        claim for claim in claims if claim.claim_kind.eligible_for_fact_accuracy
    )
    factual_ids = {claim.id for claim in factual_claims}
    benchmark_reviews = tuple(
        review for review in reviews if review.review_case_purpose == "benchmark"
    )
    latest_by_claim: dict[str, FactAccuracyReview] = {}
    for review in sorted(
        (item for item in reviews if item.review_case_purpose != "benchmark"),
        key=lambda item: (item.reviewed_at, item.id),
    ):
        if review.claim_id in factual_ids:
            latest_by_claim[review.claim_id] = review
    current = tuple(latest_by_claim.values())
    verified = tuple(review for review in current if review.commercially_verified)
    decisive = tuple(review for review in verified if review.verdict.decisive)
    scores = [review.verdict.score for review in decisive]
    decisive_scores = [score for score in scores if score is not None]
    factual_count = len(factual_claims)
    decisive_count = len(decisive_scores)

    limitations: list[str] = []
    if not factual_claims:
        limitations.append("fact_claims_not_registered")
    elif len(current) < factual_count:
        limitations.append("fact_claims_unreviewed")
    if current and len(verified) < len(current):
        limitations.append("provisional_or_stale_fact_reviews_excluded")
        if any(review.review_case_status not in FINAL_REVIEW_STATUSES for review in current):
            limitations.append("fact_accuracy_independent_review_required")
    if benchmark_reviews:
        limitations.append("benchmark_reviews_excluded_from_commercial_metrics")
    if any(
        review.verdict == FactAccuracyVerdict.INSUFFICIENT_EVIDENCE
        for review in current
    ):
        limitations.append("fact_accuracy_contains_insufficient_evidence")
    if factual_claims and decisive_count < factual_count:
        limitations.append("fact_accuracy_incomplete_coverage")

    return FactAccuracyMetrics(
        registered_claim_count=len(claims),
        factual_claim_count=factual_count,
        reviewed_claim_count=len(current),
        commercially_verified_claim_count=len(verified),
        decisive_claim_count=decisive_count,
        accurate_count=sum(
            review.verdict == FactAccuracyVerdict.ACCURATE for review in verified
        ),
        inaccurate_count=sum(
            review.verdict == FactAccuracyVerdict.INACCURATE for review in verified
        ),
        outdated_count=sum(
            review.verdict == FactAccuracyVerdict.OUTDATED for review in verified
        ),
        insufficient_evidence_count=sum(
            review.verdict == FactAccuracyVerdict.INSUFFICIENT_EVIDENCE
            for review in current
        ),
        evaluation_coverage_rate=(
            round(decisive_count / factual_count, 6) if factual_count else None
        ),
        fact_accuracy=(
            round(fmean(decisive_scores), 6)
            if factual_count and decisive_count == factual_count
            else None
        ),
        known_limitations=tuple(limitations),
    )

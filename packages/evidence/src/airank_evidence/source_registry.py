from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal


SourceCategoryL1 = Literal[
    "brand_corporate",
    "government_public",
    "news_media",
    "vertical_professional",
    "platform_community",
    "business_services",
    "research_documentation",
    "search_page_proxy",
    "other",
]
ClassificationStatus = Literal["reviewed", "curated"]
ClassificationMethod = Literal["human_review", "dataset_import"]
ClassificationConfidence = Literal["low", "medium", "high"]
AuthorityLevel = Literal["unknown", "low", "medium", "high", "official"]
UsagePolicy = Literal["primary_evidence", "context_only", "lead_only", "prohibited"]
RiskLevel = Literal["low", "medium", "high", "critical"]


def normalize_source_host(value: str) -> str:
    """Normalize one exact DNS host without inferring a registrable parent domain."""

    raw = value.strip().rstrip(".").lower()
    if not raw:
        raise ValueError("source host is required")
    if any(marker in raw for marker in ("://", "/", "?", "#", "@", ":")):
        raise ValueError("source registry accepts a host only")
    try:
        ascii_host = raw.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("source host must be a valid DNS host") from exc
    if len(ascii_host) > 253:
        raise ValueError("source host must be a valid DNS host")
    labels = ascii_host.split(".")
    if len(labels) < 2:
        raise ValueError("source host must be a valid DNS host")
    for label in labels:
        if (
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or any(not (char.isalnum() or char == "-") for char in label)
        ):
            raise ValueError("source host must be a valid DNS host")
    return ascii_host


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class SourceClassificationRevision:
    revision_id: str
    revision_number: int
    normalized_host: str
    source_category_l1: SourceCategoryL1
    source_type: str
    ecosystem: str | None
    classification_status: ClassificationStatus
    classification_method: ClassificationMethod
    classification_confidence: ClassificationConfidence
    authority_level: AuthorityLevel
    usage_policy: UsagePolicy
    risk_level: RiskLevel
    evidence_note: str
    evidence_url: str | None
    valid_until: datetime | None
    reviewed_by: str
    reviewed_at: datetime
    supersedes_revision_id: str | None = None

    def __post_init__(self) -> None:
        if self.revision_number < 1:
            raise ValueError("revision_number must be positive")
        if normalize_source_host(self.normalized_host) != self.normalized_host:
            raise ValueError("normalized_host must be canonical")
        if not self.source_type.strip():
            raise ValueError("source_type is required")
        if len(self.evidence_note.strip()) < 8:
            raise ValueError("evidence_note must explain the classification")
        if not self.reviewed_by.strip():
            raise ValueError("reviewed_by is required")
        if self.revision_number > 1 and not self.supersedes_revision_id:
            raise ValueError("later revisions must supersede the previous revision")

    def is_effective(self, now: datetime | None = None) -> bool:
        if self.valid_until is None:
            return True
        checked_at = _as_utc(now or datetime.now(timezone.utc))
        return _as_utc(self.valid_until) >= checked_at


def current_source_classification(
    revisions: Iterable[SourceClassificationRevision],
    *,
    now: datetime | None = None,
) -> SourceClassificationRevision | None:
    del now  # Expiry is exposed by `is_effective`; history is never hidden.
    rows = list(revisions)
    if not rows:
        return None
    hosts = {row.normalized_host for row in rows}
    if len(hosts) != 1:
        raise ValueError("source classification history must contain one host")
    return max(rows, key=lambda row: (row.revision_number, _as_utc(row.reviewed_at), row.revision_id))

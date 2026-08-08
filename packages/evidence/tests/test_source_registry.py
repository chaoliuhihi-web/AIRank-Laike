from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from airank_evidence import (
    SourceClassificationRevision,
    current_source_classification,
    normalize_source_host,
)


def test_source_host_normalization_is_exact_and_does_not_guess_parent_domain() -> None:
    assert normalize_source_host(" News.Example.COM. ") == "news.example.com"
    assert normalize_source_host("例子.公司") == "xn--fsqu00a.xn--55qx5d"

    with pytest.raises(ValueError, match="host only"):
        normalize_source_host("https://example.com/article")
    with pytest.raises(ValueError, match="valid DNS host"):
        normalize_source_host("bad_host.example")


def test_current_source_classification_uses_latest_revision_and_preserves_expiry() -> None:
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    first = SourceClassificationRevision(
        revision_id="source_class_1",
        revision_number=1,
        normalized_host="example.com",
        source_category_l1="brand_corporate",
        source_type="brand_corporate",
        ecosystem="Example",
        classification_status="reviewed",
        classification_method="human_review",
        classification_confidence="high",
        authority_level="official",
        usage_policy="primary_evidence",
        risk_level="low",
        evidence_note="Official ownership page was checked by a human reviewer.",
        evidence_url="https://example.com/about",
        valid_until=now - timedelta(days=1),
        reviewed_by="reviewer_1",
        reviewed_at=now - timedelta(days=2),
    )
    current = SourceClassificationRevision(
        revision_id="source_class_2",
        revision_number=2,
        normalized_host="example.com",
        source_category_l1="research_documentation",
        source_type="document_platform",
        ecosystem=None,
        classification_status="reviewed",
        classification_method="human_review",
        classification_confidence="medium",
        authority_level="medium",
        usage_policy="context_only",
        risk_level="medium",
        evidence_note="The current site is a document host, not the represented brand.",
        evidence_url=None,
        valid_until=now + timedelta(days=30),
        reviewed_by="reviewer_2",
        reviewed_at=now,
        supersedes_revision_id="source_class_1",
    )

    resolved = current_source_classification([first, current], now=now)

    assert resolved is not None
    assert resolved.revision_id == "source_class_2"
    assert resolved.is_effective(now)
    assert not first.is_effective(now)


def test_source_classification_rejects_unreviewed_or_inconsistent_revisions() -> None:
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="reviewed_by"):
        SourceClassificationRevision(
            revision_id="source_class_bad",
            revision_number=1,
            normalized_host="example.com",
            source_category_l1="other",
            source_type="unknown",
            ecosystem=None,
            classification_status="reviewed",
            classification_method="human_review",
            classification_confidence="low",
            authority_level="unknown",
            usage_policy="context_only",
            risk_level="medium",
            evidence_note="Human evidence is required for every classification.",
            evidence_url=None,
            valid_until=None,
            reviewed_by="",
            reviewed_at=now,
        )

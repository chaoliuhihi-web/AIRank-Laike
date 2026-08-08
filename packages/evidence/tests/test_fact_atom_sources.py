from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from airank_domain import (
    Disclosure,
    FactAtom,
    FactAtomStatus,
    FactSubjectType,
    TrustLevel,
    confirm_fact_atom,
)
from airank_evidence import SourceCitation, fact_source_ref_from_citation


NOW = datetime(2026, 5, 17, 11, 0, tzinfo=timezone.utc)


def build_fact() -> FactAtom:
    return FactAtom(
        id="fact_1",
        tenant_id="tenant_1",
        project_id="project_1",
        fact_type="brand_claim",
        title="AIRank evidence",
        fact_text="AIRank requires cited evidence for claims.",
    )


def build_citation() -> SourceCitation:
    return SourceCitation(
        id="cite_fact_1",
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snap_1",
        citation_order=1,
        title="Evidence source",
        url="https://example.com/facts",
        host="example.com",
        source_type="web",
        cited_text="AIRank requires cited evidence.",
        created_at=NOW,
    )


def test_confirmed_fact_atom_requires_traceable_source() -> None:
    with pytest.raises(ValueError, match="confirmed FactAtom"):
        FactAtom(
            id="fact_bad",
            tenant_id="tenant_1",
            project_id="project_1",
            fact_type="brand_claim",
            title="Unsupported",
            fact_text="Unsupported fact.",
            status=FactAtomStatus.CONFIRMED,
        )

    with pytest.raises(ValueError, match="cannot confirm"):
        confirm_fact_atom(build_fact(), reviewed_by="reviewer_1", reviewed_at=NOW)


def test_fact_atom_subject_binding_is_complete_and_frozen() -> None:
    with pytest.raises(ValueError, match="requires subject_ref_id"):
        FactAtom(
            id="fact_subject_missing",
            tenant_id="tenant_1",
            project_id="project_1",
            fact_type="brand_claim",
            title="Missing subject",
            fact_text="Entity facts require stable subject identity.",
            subject_type=FactSubjectType.BRAND,
        )

    fact = FactAtom(
        id="fact_subject_bound",
        tenant_id="tenant_1",
        project_id="project_1",
        fact_type="brand_claim",
        title="Bound subject",
        fact_text="Entity facts require stable subject identity.",
        subject_type=FactSubjectType.BRAND,
        subject_ref_id="subject_airank",
    )

    assert fact.subject_type == FactSubjectType.BRAND
    assert fact.subject_ref_id == "subject_airank"
    with pytest.raises(FrozenInstanceError):
        fact.subject_ref_id = "subject_peer"  # type: ignore[misc]


def test_fact_atom_can_be_confirmed_with_source_citation() -> None:
    source = fact_source_ref_from_citation(build_citation())

    confirmed = confirm_fact_atom(
        build_fact(),
        reviewed_by="reviewer_1",
        reviewed_at=NOW,
        sources=(source,),
        trust_level=TrustLevel.B,
        disclosure=Disclosure.PUBLIC,
    )

    assert confirmed.status == FactAtomStatus.CONFIRMED
    assert confirmed.sources[0].citation_id == "cite_fact_1"
    assert confirmed.sources[0].snapshot_id == "snap_1"
    assert confirmed.disclosure == Disclosure.PUBLIC

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_domain import FactAtom, confirm_fact_atom
from airank_evidence import (
    SourceCitation,
    fact_source_ref_from_citation,
    generate_gap_from_citations,
)


NOW = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def build_citation() -> SourceCitation:
    return SourceCitation(
        id="cite_gap_1",
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snap_1",
        citation_order=1,
        title="FAQ source",
        url="https://example.com/faq",
        host="example.com",
        source_type="web",
        cited_text="Customers ask for evidence-backed FAQs.",
        created_at=NOW,
    )


def test_content_gap_is_traceable_to_question_citation_and_fact_atom() -> None:
    citation = build_citation()
    fact = confirm_fact_atom(
        FactAtom(
            id="fact_gap_1",
            tenant_id="tenant_1",
            project_id="project_1",
            fact_type="faq",
            title="FAQ evidence",
            fact_text="FAQ content should cite source material.",
        ),
        reviewed_by="reviewer_1",
        reviewed_at=NOW,
        sources=(fact_source_ref_from_citation(citation),),
    )

    gap = generate_gap_from_citations(
        tenant_id="tenant_1",
        project_id="project_1",
        question_id="question_1",
        fact_atom=fact,
        citations=(citation,),
    )

    assert gap.related_question_ids == ("question_1",)
    assert gap.citation_ids == ("cite_gap_1",)
    assert gap.fact_atom_ids == ("fact_gap_1",)


def test_content_gap_requires_citations() -> None:
    fact = FactAtom(
        id="fact_gap_2",
        tenant_id="tenant_1",
        project_id="project_1",
        fact_type="faq",
        title="Unsupported",
        fact_text="Unsupported gap.",
    )

    with pytest.raises(ValueError, match="source citations"):
        generate_gap_from_citations(
            tenant_id="tenant_1",
            project_id="project_1",
            question_id="question_1",
            fact_atom=fact,
            citations=(),
        )

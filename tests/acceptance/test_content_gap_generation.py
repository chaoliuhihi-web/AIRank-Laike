from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "evidence" / "src"))

from airank_domain import FactAtom, confirm_fact_atom  # noqa: E402
from airank_evidence import (  # noqa: E402
    SourceCitation,
    fact_source_ref_from_citation,
    generate_gap_from_citations,
)


def test_content_gap_generation_acceptance() -> None:
    now = datetime(2026, 5, 17, 12, 30, tzinfo=timezone.utc)
    citation = SourceCitation(
        id="cite_gap_acceptance",
        tenant_id="tenant_demo",
        project_id="project_demo",
        snapshot_id="snap_gap_acceptance",
        citation_order=1,
        title="Gap source",
        url="https://example.com/gap-source",
        host="example.com",
        source_type="web",
        cited_text="The buyer question needs a source-backed answer.",
        created_at=now,
    )
    fact = confirm_fact_atom(
        FactAtom(
            id="fact_gap_acceptance",
            tenant_id="tenant_demo",
            project_id="project_demo",
            fact_type="faq",
            title="Gap fact",
            fact_text="A source-backed FAQ can close this evidence gap.",
        ),
        reviewed_by="reviewer_demo",
        reviewed_at=now,
        sources=(fact_source_ref_from_citation(citation),),
    )

    gap = generate_gap_from_citations(
        tenant_id="tenant_demo",
        project_id="project_demo",
        question_id="question_gap_acceptance",
        fact_atom=fact,
        citations=(citation,),
    )

    assert gap.related_question_ids == ("question_gap_acceptance",)
    assert gap.citation_ids == ("cite_gap_acceptance",)
    assert gap.fact_atom_ids == ("fact_gap_acceptance",)

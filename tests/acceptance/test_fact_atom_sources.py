from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "evidence" / "src"))

from airank_domain import FactAtom, FactAtomStatus, confirm_fact_atom  # noqa: E402
from airank_evidence import SourceCitation, fact_source_ref_from_citation  # noqa: E402


def test_fact_atom_source_acceptance() -> None:
    now = datetime(2026, 5, 17, 11, 30, tzinfo=timezone.utc)
    fact = FactAtom(
        id="fact_acceptance",
        tenant_id="tenant_demo",
        project_id="project_demo",
        fact_type="brand_claim",
        title="Cited claim",
        fact_text="AIRank only confirms facts with source references.",
    )
    citation = SourceCitation(
        id="cite_acceptance",
        tenant_id="tenant_demo",
        project_id="project_demo",
        snapshot_id="snap_acceptance",
        citation_order=1,
        title="Source",
        url="https://example.com/fact-source",
        host="example.com",
        source_type="web",
        cited_text="Facts require sources.",
        created_at=now,
    )

    confirmed = confirm_fact_atom(
        fact,
        reviewed_by="reviewer_demo",
        reviewed_at=now,
        sources=(fact_source_ref_from_citation(citation),),
    )
    assert confirmed.status == FactAtomStatus.CONFIRMED

    with pytest.raises(ValueError):
        confirm_fact_atom(fact, reviewed_by="reviewer_demo", reviewed_at=now)

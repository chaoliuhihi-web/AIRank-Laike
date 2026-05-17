from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "evidence" / "src"))

from airank_domain import FactAtom, confirm_fact_atom  # noqa: E402
from airank_evidence import ReportConclusion  # noqa: E402


def test_evidence_chain_rejects_unsourced_confirmed_fact_and_report_conclusion() -> None:
    now = datetime(2026, 5, 17, 15, 30, tzinfo=timezone.utc)
    fact = FactAtom(
        id="fact_review_gate",
        tenant_id="tenant_demo",
        project_id="project_demo",
        fact_type="brand_claim",
        title="Unsupported",
        fact_text="This fact has no source.",
    )

    with pytest.raises(ValueError, match="cannot confirm"):
        confirm_fact_atom(fact, reviewed_by="reviewer_demo", reviewed_at=now)

    with pytest.raises(ValueError, match="snapshot"):
        ReportConclusion(
            id="conclusion_without_snapshot",
            title="Unsupported conclusion",
            body="This conclusion has no evidence chain.",
            snapshot_ids=(),
            citation_ids=("cite_demo",),
            fact_atom_ids=("fact_demo",),
        )

    with pytest.raises(ValueError, match="citation"):
        ReportConclusion(
            id="conclusion_without_citation",
            title="Unsupported conclusion",
            body="This conclusion has no evidence chain.",
            snapshot_ids=("snap_demo",),
            citation_ids=(),
            fact_atom_ids=("fact_demo",),
        )

    with pytest.raises(ValueError, match="FactAtom"):
        ReportConclusion(
            id="conclusion_without_fact",
            title="Unsupported conclusion",
            body="This conclusion has no evidence chain.",
            snapshot_ids=("snap_demo",),
            citation_ids=("cite_demo",),
            fact_atom_ids=(),
        )

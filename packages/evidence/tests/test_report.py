from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_evidence import EvidenceReport, ReportConclusion, build_report_conclusion


NOW = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)


def test_report_conclusion_requires_full_evidence_chain() -> None:
    with pytest.raises(ValueError, match="snapshot"):
        ReportConclusion(
            id="conclusion_bad",
            title="Unsupported",
            body="Missing snapshot.",
            snapshot_ids=(),
            citation_ids=("cite_1",),
            fact_atom_ids=("fact_1",),
        )

    with pytest.raises(ValueError, match="citation"):
        ReportConclusion(
            id="conclusion_bad",
            title="Unsupported",
            body="Missing citation.",
            snapshot_ids=("snap_1",),
            citation_ids=(),
            fact_atom_ids=("fact_1",),
        )

    with pytest.raises(ValueError, match="FactAtom"):
        ReportConclusion(
            id="conclusion_bad",
            title="Unsupported",
            body="Missing FactAtom.",
            snapshot_ids=("snap_1",),
            citation_ids=("cite_1",),
            fact_atom_ids=(),
        )


def test_evidence_report_json_contains_traceable_conclusion() -> None:
    conclusion = build_report_conclusion(
        id="conclusion_1",
        title="AIRank is cited",
        body="AIRank appeared with cited supporting evidence.",
        snapshot_id="snap_1",
        citation_id="cite_1",
        fact_atom_id="fact_1",
    )
    report = EvidenceReport(
        id="report_1",
        tenant_id="tenant_1",
        project_id="project_1",
        title="AIRank evidence report",
        conclusions=(conclusion,),
        generated_at=NOW,
    )

    payload = report.to_json()
    assert payload["conclusions"][0]["evidence"] == {
        "snapshot_ids": ["snap_1"],
        "citation_ids": ["cite_1"],
        "fact_atom_ids": ["fact_1"],
    }

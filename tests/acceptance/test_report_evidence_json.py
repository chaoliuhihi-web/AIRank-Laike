from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "evidence" / "src"))

from airank_evidence import EvidenceReport, build_report_conclusion  # noqa: E402


def test_report_evidence_json_acceptance() -> None:
    conclusion = build_report_conclusion(
        id="conclusion_acceptance",
        title="Traceable recommendation",
        body="The report conclusion is backed by snapshot, citation and FactAtom.",
        snapshot_id="snap_acceptance",
        citation_id="cite_acceptance",
        fact_atom_id="fact_acceptance",
    )
    report = EvidenceReport(
        id="report_acceptance",
        tenant_id="tenant_demo",
        project_id="project_demo",
        title="Evidence report",
        conclusions=(conclusion,),
        generated_at=datetime(2026, 5, 17, 13, 30, tzinfo=timezone.utc),
    )

    payload = report.to_json()
    evidence = payload["conclusions"][0]["evidence"]
    assert evidence["snapshot_ids"] == ["snap_acceptance"]
    assert evidence["citation_ids"] == ["cite_acceptance"]
    assert evidence["fact_atom_ids"] == ["fact_acceptance"]

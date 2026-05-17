from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReportConclusion:
    id: str
    title: str
    body: str
    snapshot_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    fact_atom_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.snapshot_ids:
            raise ValueError("report conclusion must reference at least one snapshot")
        if not self.citation_ids:
            raise ValueError("report conclusion must reference at least one citation")
        if not self.fact_atom_ids:
            raise ValueError("report conclusion must reference at least one FactAtom")

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "evidence": {
                "snapshot_ids": list(self.snapshot_ids),
                "citation_ids": list(self.citation_ids),
                "fact_atom_ids": list(self.fact_atom_ids),
            },
        }


@dataclass(frozen=True)
class EvidenceReport:
    id: str
    tenant_id: str
    project_id: str
    title: str
    conclusions: tuple[ReportConclusion, ...]
    generated_at: datetime

    def __post_init__(self) -> None:
        if not self.conclusions:
            raise ValueError("evidence report must include at least one conclusion")

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "title": self.title,
            "generated_at": self.generated_at.isoformat(),
            "conclusions": [conclusion.to_record() for conclusion in self.conclusions],
        }


def build_report_conclusion(
    *,
    id: str,
    title: str,
    body: str,
    snapshot_id: str,
    citation_id: str,
    fact_atom_id: str,
) -> ReportConclusion:
    return ReportConclusion(
        id=id,
        title=title,
        body=body,
        snapshot_ids=(snapshot_id,),
        citation_ids=(citation_id,),
        fact_atom_ids=(fact_atom_id,),
    )

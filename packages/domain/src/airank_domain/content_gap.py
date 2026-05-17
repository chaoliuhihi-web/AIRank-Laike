from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .fact_atom import FactAtom


class GapSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ContentGap:
    id: str
    tenant_id: str
    project_id: str
    gap_type: str
    severity: GapSeverity
    title: str
    description: str
    related_question_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    fact_atom_ids: tuple[str, ...]
    suggested_asset_type: str
    status: str = "open"

    def __post_init__(self) -> None:
        if not self.related_question_ids:
            raise ValueError("content gap must reference at least one question")
        if not self.citation_ids:
            raise ValueError("content gap must reference at least one citation")
        if not self.fact_atom_ids:
            raise ValueError("content gap must reference at least one FactAtom")


def generate_content_gap(
    *,
    tenant_id: str,
    project_id: str,
    question_id: str,
    citation_ids: tuple[str, ...],
    fact_atom: FactAtom,
    gap_type: str = "evidence_gap",
    severity: GapSeverity = GapSeverity.MEDIUM,
    suggested_asset_type: str = "faq",
) -> ContentGap:
    if not fact_atom.sources:
        raise ValueError("content gap requires a sourced FactAtom")
    return ContentGap(
        id=f"gap_{question_id}_{fact_atom.id}",
        tenant_id=tenant_id,
        project_id=project_id,
        gap_type=gap_type,
        severity=severity,
        title=f"Evidence gap for {question_id}",
        description=f"Question {question_id} needs content backed by FactAtom {fact_atom.id}.",
        related_question_ids=(question_id,),
        citation_ids=tuple(sorted(citation_ids)),
        fact_atom_ids=(fact_atom.id,),
        suggested_asset_type=suggested_asset_type,
    )

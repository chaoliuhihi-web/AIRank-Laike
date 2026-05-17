from __future__ import annotations

from airank_domain import ContentGap, FactAtom, GapSeverity, generate_content_gap

from .snapshot import SourceCitation


def generate_gap_from_citations(
    *,
    tenant_id: str,
    project_id: str,
    question_id: str,
    fact_atom: FactAtom,
    citations: tuple[SourceCitation, ...],
    severity: GapSeverity = GapSeverity.MEDIUM,
    suggested_asset_type: str = "faq",
) -> ContentGap:
    if not citations:
        raise ValueError("content gap requires source citations")
    return generate_content_gap(
        tenant_id=tenant_id,
        project_id=project_id,
        question_id=question_id,
        citation_ids=tuple(citation.id for citation in citations),
        fact_atom=fact_atom,
        severity=severity,
        suggested_asset_type=suggested_asset_type,
    )

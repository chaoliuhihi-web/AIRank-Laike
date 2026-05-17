from __future__ import annotations

from airank_domain import FactSourceRef

from .snapshot import SourceCitation


def fact_source_ref_from_citation(
    citation: SourceCitation,
    *,
    source_type: str = "citation",
    support_type: str = "supports",
) -> FactSourceRef:
    return FactSourceRef(
        id=f"factsrc_{citation.id}",
        source_type=source_type,
        support_type=support_type,
        citation_id=citation.id,
        snapshot_id=citation.snapshot_id,
        source_url=citation.url,
        source_title=citation.title,
    )

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum


class FactAtomStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    STALE = "stale"


class TrustLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class Disclosure(str, Enum):
    PUBLIC = "public"
    REDACTED = "redacted"
    INTERNAL = "internal"
    FORBIDDEN = "forbidden"
    PENDING_APPROVAL = "pending_approval"


@dataclass(frozen=True)
class FactSourceRef:
    id: str
    source_type: str
    support_type: str = "supports"
    citation_id: str | None = None
    snapshot_id: str | None = None
    object_ref_id: str | None = None
    source_url: str | None = None
    source_title: str | None = None

    def has_traceable_source(self) -> bool:
        return bool(self.citation_id or self.object_ref_id or self.source_url)


@dataclass(frozen=True)
class FactAtom:
    id: str
    tenant_id: str
    project_id: str
    fact_type: str
    title: str
    fact_text: str
    status: FactAtomStatus = FactAtomStatus.DRAFT
    trust_level: TrustLevel = TrustLevel.C
    disclosure: Disclosure = Disclosure.PENDING_APPROVAL
    sources: tuple[FactSourceRef, ...] = ()
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.status == FactAtomStatus.CONFIRMED and not has_traceable_sources(self.sources):
            raise ValueError("confirmed FactAtom must include a citation, object ref, or source URL")


def confirm_fact_atom(
    fact_atom: FactAtom,
    *,
    reviewed_by: str,
    reviewed_at: datetime,
    sources: tuple[FactSourceRef, ...] | None = None,
    trust_level: TrustLevel = TrustLevel.B,
    disclosure: Disclosure | None = None,
) -> FactAtom:
    next_sources = sources if sources is not None else fact_atom.sources
    if not has_traceable_sources(next_sources):
        raise ValueError("cannot confirm FactAtom without traceable source")
    return replace(
        fact_atom,
        status=FactAtomStatus.CONFIRMED,
        trust_level=trust_level,
        disclosure=disclosure or fact_atom.disclosure,
        sources=next_sources,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
    )


def has_traceable_sources(sources: tuple[FactSourceRef, ...]) -> bool:
    return any(source.has_traceable_source() for source in sources)

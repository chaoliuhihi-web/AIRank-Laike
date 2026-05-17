"""AIRank evidence primitives."""

from .fact_source import fact_source_ref_from_citation
from .gap import generate_gap_from_citations
from .provider import MockAnswerProvider, ProviderPayloadError
from .snapshot import AnswerSnapshot, SourceCitation

__all__ = [
    "AnswerSnapshot",
    "MockAnswerProvider",
    "ProviderPayloadError",
    "SourceCitation",
    "fact_source_ref_from_citation",
    "generate_gap_from_citations",
]

"""AIRank evidence primitives."""

from .fact_source import fact_source_ref_from_citation
from .gap import generate_gap_from_citations
from .provider import MockAnswerProvider, ProviderPayloadError
from .report import EvidenceReport, ReportConclusion, build_report_conclusion
from .snapshot import AnswerSnapshot, SourceCitation

__all__ = [
    "AnswerSnapshot",
    "MockAnswerProvider",
    "ProviderPayloadError",
    "EvidenceReport",
    "ReportConclusion",
    "SourceCitation",
    "build_report_conclusion",
    "fact_source_ref_from_citation",
    "generate_gap_from_citations",
]

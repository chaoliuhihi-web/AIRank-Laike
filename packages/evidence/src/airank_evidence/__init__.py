"""AIRank evidence primitives."""

from .fact_source import fact_source_ref_from_citation
from .citation_support import (
    CitationClaim,
    CitationSupportEvidenceGrade,
    CitationSupportLabel,
    CitationSupportMetrics,
    CitationSupportReview,
    calculate_citation_support_metrics,
)
from .evidence_snapshot import EvidenceSnapshot
from .gap import generate_gap_from_citations
from .object_storage import (
    FilesystemObjectStorage,
    ObjectStorageError,
    S3CompatibleObjectStorage,
    StoredObject,
    build_object_storage_from_env,
    sha256_bytes,
)
from .provider import MockAnswerProvider, ProviderPayloadError
from .report import EvidenceReport, ReportConclusion, build_report_conclusion
from .snapshot import AnswerSnapshot, SourceCitation

__all__ = [
    "AnswerSnapshot",
    "CitationClaim",
    "CitationSupportEvidenceGrade",
    "CitationSupportLabel",
    "CitationSupportMetrics",
    "CitationSupportReview",
    "MockAnswerProvider",
    "ProviderPayloadError",
    "EvidenceReport",
    "EvidenceSnapshot",
    "FilesystemObjectStorage",
    "ObjectStorageError",
    "ReportConclusion",
    "SourceCitation",
    "S3CompatibleObjectStorage",
    "StoredObject",
    "build_object_storage_from_env",
    "calculate_citation_support_metrics",
    "sha256_bytes",
    "build_report_conclusion",
    "fact_source_ref_from_citation",
    "generate_gap_from_citations",
]

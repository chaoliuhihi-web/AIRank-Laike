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
from .fact_accuracy import (
    AnswerClaimKind,
    FactAccuracyClaim,
    FactAccuracyEvidenceGrade,
    FactAccuracyMetrics,
    FactAccuracyReview,
    FactAccuracyVerdict,
    calculate_fact_accuracy_metrics,
)
from .gap import generate_gap_from_citations
from .object_storage import (
    FilesystemObjectStorage,
    ObjectStorage,
    ObjectStorageError,
    S3CompatibleObjectStorage,
    StoredObject,
    build_object_storage_from_env,
    sha256_bytes,
)
from .provider import MockAnswerProvider, ProviderPayloadError
from .report import (
    EvidenceReport,
    METRIC_FORMULAS,
    REPORT_EVIDENCE_PACKET_VERSION,
    ReportConclusion,
    ReportEvidencePacket,
    ReportEvidencePacketError,
    build_report_conclusion,
    build_report_evidence_packet,
    canonical_json_bytes,
    canonical_json_sha256,
)
from .snapshot import AnswerSnapshot, SourceCitation
from .source_registry import (
    SourceClassificationRevision,
    current_source_classification,
    normalize_source_host,
)

__all__ = [
    "AnswerSnapshot",
    "AnswerClaimKind",
    "CitationClaim",
    "CitationSupportEvidenceGrade",
    "CitationSupportLabel",
    "CitationSupportMetrics",
    "CitationSupportReview",
    "MockAnswerProvider",
    "ProviderPayloadError",
    "EvidenceReport",
    "EvidenceSnapshot",
    "FactAccuracyClaim",
    "FactAccuracyEvidenceGrade",
    "FactAccuracyMetrics",
    "FactAccuracyReview",
    "FactAccuracyVerdict",
    "FilesystemObjectStorage",
    "ObjectStorageError",
    "ObjectStorage",
    "METRIC_FORMULAS",
    "REPORT_EVIDENCE_PACKET_VERSION",
    "ReportConclusion",
    "ReportEvidencePacket",
    "ReportEvidencePacketError",
    "SourceCitation",
    "SourceClassificationRevision",
    "S3CompatibleObjectStorage",
    "StoredObject",
    "build_object_storage_from_env",
    "calculate_citation_support_metrics",
    "calculate_fact_accuracy_metrics",
    "sha256_bytes",
    "build_report_conclusion",
    "build_report_evidence_packet",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "fact_source_ref_from_citation",
    "generate_gap_from_citations",
    "current_source_classification",
    "normalize_source_host",
]

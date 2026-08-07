from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from airank_domain.measurement import (
    CollectorSurface,
    EvidenceLevel,
    MentionClass,
    PromptCohortType,
    SampleStatus,
    SURFACE_EVIDENCE_LEVEL,
    sha256_text,
)


@dataclass(frozen=True)
class SourceCitation:
    id: str
    tenant_id: str
    project_id: str
    snapshot_id: str
    citation_order: int
    title: str
    url: str
    host: str
    source_type: str
    cited_text: str
    created_at: datetime
    relevance_score: float | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "snapshot_id": self.snapshot_id,
            "citation_order": self.citation_order,
            "title": self.title,
            "url": self.url,
            "host": self.host,
            "source_type": self.source_type,
            "cited_text": self.cited_text,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class AnswerSnapshot:
    id: str
    tenant_id: str
    project_id: str
    run_id: str
    task_id: str
    question_id: str
    question_text: str
    provider: str
    answer_text: str
    citations: tuple[SourceCitation, ...]
    created_at: datetime
    brand_mentioned: bool = False
    brand_rank: int | None = None
    cohort_type: PromptCohortType = PromptCohortType.BLIND
    prompt_version_id: str | None = None
    sample_index: int = 1
    session_id: str | None = None
    collector_surface: CollectorSurface = CollectorSurface.WEB
    evidence_level: EvidenceLevel = EvidenceLevel.CONSUMER_WEB
    sample_status: SampleStatus = SampleStatus.VALID
    mention_class: MentionClass = MentionClass.NOT_MENTIONED
    model_name: str | None = None
    model_version: str | None = None
    search_enabled: bool | None = None
    locale: str = "zh-CN"
    region: str | None = None
    answer_sha256: str | None = None
    raw_response_sha256: str | None = None
    raw_response_ref_id: str | None = None
    screenshot_ref_id: str | None = None
    source_panel_ref_id: str | None = None
    request_metadata_ref_id: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.sample_status == SampleStatus.VALID and not self.answer_text.strip():
            raise ValueError("valid answer snapshot requires answer_text")
        if self.sample_status != SampleStatus.VALID and self.answer_text.strip():
            raise ValueError("failed or blocked snapshot must not contain answer_text")
        if self.brand_rank is not None and self.brand_rank < 1:
            raise ValueError("brand_rank must be a positive rank when present")
        if self.sample_index < 1:
            raise ValueError("sample_index must be positive")
        if self.evidence_level != SURFACE_EVIDENCE_LEVEL[self.collector_surface]:
            raise ValueError("collector_surface and evidence_level must describe the same capture surface")
        if self.sample_status == SampleStatus.VALID:
            digest = sha256_text(self.answer_text.strip())
            if self.answer_sha256 and self.answer_sha256 != digest:
                raise ValueError("answer_sha256 does not match answer_text")
            if not self.answer_sha256:
                object.__setattr__(self, "answer_sha256", digest)
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        for citation in self.citations:
            if citation.tenant_id != self.tenant_id:
                raise ValueError("citation tenant_id must match answer snapshot tenant_id")
            if citation.project_id != self.project_id:
                raise ValueError("citation project_id must match answer snapshot project_id")
            if citation.snapshot_id != self.id:
                raise ValueError("citation snapshot_id must match answer snapshot id")

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "question_id": self.question_id,
            "question_text": self.question_text,
            "provider": self.provider,
            "answer_text": self.answer_text,
            "brand_mentioned": self.brand_mentioned,
            "brand_rank": self.brand_rank,
            "cohort_type": self.cohort_type.value,
            "prompt_version_id": self.prompt_version_id,
            "sample_index": self.sample_index,
            "session_id": self.session_id,
            "collector_surface": self.collector_surface.value,
            "evidence_level": self.evidence_level.value,
            "sample_status": self.sample_status.value,
            "mention_class": self.mention_class.value,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "search_enabled": self.search_enabled,
            "locale": self.locale,
            "region": self.region,
            "answer_sha256": self.answer_sha256,
            "raw_response_sha256": self.raw_response_sha256,
            "raw_response_ref_id": self.raw_response_ref_id,
            "screenshot_ref_id": self.screenshot_ref_id,
            "source_panel_ref_id": self.source_panel_ref_id,
            "request_metadata_ref_id": self.request_metadata_ref_id,
            "confidence": self.confidence,
            "citation_ids": [citation.id for citation in self.citations],
            "created_at": self.created_at.isoformat(),
        }


def host_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"citation URL must include host: {url}")
    return parsed.netloc.lower()

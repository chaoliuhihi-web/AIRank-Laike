from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


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

    def __post_init__(self) -> None:
        if not self.citations:
            raise ValueError("answer snapshot must include at least one citation")
        if self.brand_rank is not None and self.brand_rank < 1:
            raise ValueError("brand_rank must be a positive rank when present")
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
            "citation_ids": [citation.id for citation in self.citations],
            "created_at": self.created_at.isoformat(),
        }


def host_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"citation URL must include host: {url}")
    return parsed.netloc.lower()

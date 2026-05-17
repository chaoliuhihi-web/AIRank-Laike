from __future__ import annotations

from datetime import datetime
from typing import Any

from .snapshot import AnswerSnapshot, SourceCitation, host_from_url


class ProviderPayloadError(ValueError):
    """Raised when a manual/mock provider payload cannot produce evidence."""


class MockAnswerProvider:
    """Deterministic provider used for worker and acceptance tests."""

    provider_name = "mock"

    def answer(
        self,
        payload: dict[str, Any],
        *,
        tenant_id: str,
        project_id: str,
        task_id: str,
        created_at: datetime,
    ) -> AnswerSnapshot:
        run_id = required_text(payload, "run_id")
        question_id = required_text(payload, "question_id")
        question_text = required_text(payload, "question_text")
        answer_text = required_text(payload, "answer_text")
        citations_payload = payload.get("citations")
        if not isinstance(citations_payload, list) or not citations_payload:
            raise ProviderPayloadError("citations must contain at least one source")

        snapshot_id = str(payload.get("snapshot_id") or f"snap_{task_id}")
        citations = tuple(
            build_citation(
                item,
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=snapshot_id,
                order=index,
                created_at=created_at,
            )
            for index, item in enumerate(citations_payload, start=1)
        )

        return AnswerSnapshot(
            id=snapshot_id,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            question_id=question_id,
            question_text=question_text,
            provider=str(payload.get("provider") or self.provider_name),
            answer_text=answer_text,
            citations=citations,
            brand_mentioned=bool(payload.get("brand_mentioned", False)),
            brand_rank=payload.get("brand_rank"),
            created_at=created_at,
        )


def build_citation(
    item: Any,
    *,
    tenant_id: str,
    project_id: str,
    snapshot_id: str,
    order: int,
    created_at: datetime,
) -> SourceCitation:
    if not isinstance(item, dict):
        raise ProviderPayloadError("citation must be an object")
    url = required_text(item, "url")
    title = required_text(item, "title")
    cited_text = required_text(item, "cited_text")
    return SourceCitation(
        id=str(item.get("id") or f"cite_{snapshot_id}_{order}"),
        tenant_id=tenant_id,
        project_id=project_id,
        snapshot_id=snapshot_id,
        citation_order=order,
        title=title,
        url=url,
        host=str(item.get("host") or host_from_url(url)),
        source_type=str(item.get("source_type") or "web"),
        cited_text=cited_text,
        relevance_score=item.get("relevance_score"),
        created_at=created_at,
    )


def required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProviderPayloadError(f"{key} is required")
    return value

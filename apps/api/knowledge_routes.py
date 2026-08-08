from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
import json
import os
import re
from typing import Any, Literal, Mapping, Optional, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import bindparam, create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import segment_source_text, sha256_text
from airank_skills import run_skill


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["knowledge-governance"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_review_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    if not authenticated_actor:
        raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})
    return authenticated_actor


class KnowledgeSourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=160)
    source_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=512)
    content_text: str = Field(min_length=1, max_length=2_000_000)
    source_uri: Optional[str] = Field(default=None, max_length=2048)
    content_type: str = Field(default="text/plain", min_length=1, max_length=128)
    authority_level: Literal["official", "verified_third_party", "community", "unclassified"] = "unclassified"
    risk_level: Literal["low", "medium", "high", "restricted"] = "medium"
    parent_source_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    captured_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    segment_max_characters: int = Field(default=1200, ge=100, le=8000)

    @field_validator("source_uri")
    @classmethod
    def source_uri_must_be_http(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_uri must be an absolute http(s) URL")
        return value

    @model_validator(mode="after")
    def validity_must_be_ordered(self) -> "KnowledgeSourceCreateRequest":
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be later than valid_from")
        return self


class KnowledgeSourceData(BaseModel):
    source_id: str
    tenant_id: str
    project_id: str
    source_type: str
    title: str
    source_uri: Optional[str]
    content_sha256: str
    byte_size: int
    authority_level: str
    risk_level: str
    status: Literal["active", "stale", "disabled"]
    revision_number: int
    parent_source_id: Optional[str]
    segment_count: int
    captured_at: datetime
    valid_from: Optional[datetime]
    valid_until: Optional[datetime]
    idempotent_replay: bool = False


class KnowledgeSourceResponse(BaseModel):
    data: KnowledgeSourceData
    meta: dict[str, str]


class KnowledgeSourceListResponse(BaseModel):
    data: list[KnowledgeSourceData]
    meta: dict[str, str]


class KnowledgeSearchResultData(BaseModel):
    rank: int
    segment_id: str
    source_id: str
    source_revision_number: int
    source_title: str
    source_uri: Optional[str]
    segment_index: int
    text: str
    source_start: int
    source_end: int
    content_sha256: str
    match_type: Literal["exact", "terms"]
    matched_terms: list[str]


class KnowledgeSearchData(BaseModel):
    query: str
    retrieval_mode: Literal["lexical_only"] = "lexical_only"
    vector_status: Literal["not_configured"] = "not_configured"
    matched_count: int
    returned_count: int
    candidate_limit_reached: bool
    results: list[KnowledgeSearchResultData]


class KnowledgeSearchResponse(BaseModel):
    data: KnowledgeSearchData
    meta: dict[str, str]


class FactProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    fact_type: str = Field(default="brand_claim", min_length=1, max_length=64)
    fact_text: str = Field(min_length=1, max_length=10000)
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    risk_level: Literal["low", "medium", "high", "restricted"] = "medium"
    disclosure: Literal["public", "redacted", "internal", "forbidden", "pending_approval"] = "pending_approval"
    created_by: str = Field(min_length=1, max_length=64)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    @field_validator("source_ids")
    @classmethod
    def sources_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source_ids must contain unique values")
        return value


class FactRevisionData(BaseModel):
    fact_id: str
    revision_id: str
    tenant_id: str
    project_id: str
    title: str
    fact_type: str
    fact_text: str
    content_sha256: str
    revision_number: int
    status: Literal["proposed", "approved", "superseded", "rejected"]
    source_ids: list[str]
    risk_level: str
    disclosure: str
    created_by: str
    created_at: datetime
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    eligible_for_generation: bool
    eligibility_reason: str


class FactRevisionResponse(BaseModel):
    data: FactRevisionData
    meta: dict[str, str]


class FactRevisionListResponse(BaseModel):
    data: list[FactRevisionData]
    meta: dict[str, str]


class FactRevisionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approved", "rejected"]
    reviewed_by: str = Field(min_length=1, max_length=64)
    review_note: Optional[str] = Field(default=None, min_length=1, max_length=1000)


class FactConflictCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_revision_id: str = Field(min_length=1, max_length=64)
    right_revision_id: str = Field(min_length=1, max_length=64)
    conflict_type: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def revisions_must_differ(self) -> "FactConflictCreateRequest":
        if self.left_revision_id == self.right_revision_id:
            raise ValueError("conflict revisions must differ")
        return self


class FactConflictResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: Literal["resolved_left", "resolved_right", "resolved_new_revision", "dismissed"]
    resolved_by: str = Field(min_length=1, max_length=64)
    resolution_note: str = Field(min_length=1, max_length=2000)


class FactConflictData(BaseModel):
    conflict_id: str
    tenant_id: str
    project_id: str
    fact_id: str
    left_revision_id: str
    right_revision_id: str
    conflict_type: str
    description: str
    status: Literal["open", "resolved_left", "resolved_right", "resolved_new_revision", "dismissed"]
    detected_at: datetime
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None


class FactConflictResponse(BaseModel):
    data: FactConflictData
    meta: dict[str, str]


class FactConflictListResponse(BaseModel):
    data: list[FactConflictData]
    meta: dict[str, str]


class KnowledgeGovernanceAlertData(BaseModel):
    alert_id: str
    kind: Literal["source_stale", "source_expired", "source_expiring", "fact_expired", "fact_expiring", "open_conflict"]
    severity: Literal["critical", "warning"]
    entity_type: Literal["knowledge_source", "fact_revision", "fact_conflict"]
    entity_id: str
    title: str
    message: str
    due_at: Optional[datetime] = None
    days_remaining: Optional[int] = None


class KnowledgeGovernanceData(BaseModel):
    status: Literal["healthy", "attention_required"]
    as_of: datetime
    within_days: int
    source_count: int
    approved_fact_count: int
    stale_source_count: int
    expired_source_count: int
    expiring_source_count: int
    expired_fact_count: int
    expiring_fact_count: int
    open_conflict_count: int
    action_required_count: int
    alerts: list[KnowledgeGovernanceAlertData]


class KnowledgeGovernanceResponse(BaseModel):
    data: KnowledgeGovernanceData
    meta: dict[str, str]


class GovernedContentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_type: Literal["fact_page", "product_page", "faq", "comparison_page", "case_page", "research_page", "json_ld", "llms_txt"]
    title: str = Field(min_length=1, max_length=255)
    direction: str = Field(min_length=1, max_length=1000)
    fact_revision_ids: list[str] = Field(min_length=1, max_length=50)
    created_by: str = Field(min_length=1, max_length=64)

    @field_validator("fact_revision_ids")
    @classmethod
    def revisions_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("fact_revision_ids must contain unique values")
        return value


class GovernedContentData(BaseModel):
    asset_id: str
    tenant_id: str
    project_id: str
    asset_type: str
    title: str
    body_md: str
    status: Literal["draft", "approved", "rejected", "changes_requested"]
    generation_mode: Literal["approved_fact_template", "evidence_bound_page_blueprint"]
    skill_id: Optional[str] = None
    skill_version: Optional[str] = None
    blueprint_sha256: Optional[str] = None
    section_count: int = 0
    fact_revision_ids: list[str]
    claim_assertion_ids: list[str]
    claim_support_ids: list[str]
    created_at: datetime


class GovernedContentResponse(BaseModel):
    data: GovernedContentData
    meta: dict[str, str]


class GovernedContentListResponse(BaseModel):
    data: list[GovernedContentData]
    meta: dict[str, str]


def _page_blueprint_or_error(payload: GovernedContentCreateRequest, facts: list[dict[str, Any]]) -> dict[str, Any]:
    blueprint = run_skill(
        "intervention.page-blueprint",
        {
            "asset_type": payload.asset_type,
            "title": payload.title,
            "direction": payload.direction,
            "facts": facts,
        },
    )
    if blueprint.get("status") != "draft" or not blueprint.get("body_md"):
        raise StarletteHTTPException(
            status_code=409,
            detail={
                "code": "CONTENT_EVIDENCE_MISSING",
                "details": {
                    "reason": "page_blueprint_needs_evidence",
                    "missing_evidence": blueprint.get("missing_evidence", []),
                },
            },
        )
    return blueprint


class KnowledgeRepository(Protocol):
    def create_source(self, tenant_id: str, project_id: str, payload: KnowledgeSourceCreateRequest) -> KnowledgeSourceData: ...
    def revise_source(self, tenant_id: str, project_id: str, source_id: str, payload: KnowledgeSourceCreateRequest) -> KnowledgeSourceData: ...
    def list_sources(self, tenant_id: str, project_id: str) -> list[KnowledgeSourceData]: ...
    def search_segments(self, tenant_id: str, project_id: str, query: str, limit: int) -> KnowledgeSearchData: ...
    def propose_fact(self, tenant_id: str, project_id: str, payload: FactProposalRequest) -> FactRevisionData: ...
    def revise_fact(self, tenant_id: str, project_id: str, fact_id: str, payload: FactProposalRequest) -> FactRevisionData: ...
    def list_facts(self, tenant_id: str, project_id: str) -> list[FactRevisionData]: ...
    def review_revision(self, tenant_id: str, project_id: str, revision_id: str, payload: FactRevisionReviewRequest) -> FactRevisionData: ...
    def create_conflict(self, tenant_id: str, project_id: str, fact_id: str, payload: FactConflictCreateRequest) -> FactConflictData: ...
    def list_conflicts(self, tenant_id: str, project_id: str, status: Optional[str] = None) -> list[FactConflictData]: ...
    def resolve_conflict(self, tenant_id: str, project_id: str, conflict_id: str, payload: FactConflictResolveRequest) -> FactConflictData: ...
    def create_governed_content(self, tenant_id: str, project_id: str, payload: GovernedContentCreateRequest) -> GovernedContentData: ...
    def list_governed_content(self, tenant_id: str, project_id: str) -> list[GovernedContentData]: ...


class InMemoryKnowledgeRepository:
    """Contract-only repository. Production evidence requires MySQL."""

    def __init__(self) -> None:
        self.sources: dict[tuple[str, str], KnowledgeSourceData] = {}
        self.source_contents: dict[tuple[str, str], str] = {}
        self.source_segments: dict[tuple[str, str], tuple[Any, ...]] = {}
        self.idempotency: dict[tuple[str, str, str], str] = {}
        self.facts: dict[tuple[str, str], FactRevisionData] = {}
        self.conflicts: dict[tuple[str, str], FactConflictData] = {}
        self.content_assets: dict[tuple[str, str], GovernedContentData] = {}
        self.claim_support_links: dict[tuple[str, str], str] = {}

    def create_source(self, tenant_id: str, project_id: str, payload: KnowledgeSourceCreateRequest) -> KnowledgeSourceData:
        replay_key = (tenant_id, project_id, payload.idempotency_key)
        if replay_key in self.idempotency:
            existing = self.sources[(tenant_id, self.idempotency[replay_key])]
            return existing.model_copy(update={"idempotent_replay": True})
        content_sha256 = sha256_text(payload.content_text)
        duplicate = next((
            source
            for (item_tenant, _), source in self.sources.items()
            if item_tenant == tenant_id
            and source.project_id == project_id
            and source.content_sha256 == content_sha256
        ), None)
        if duplicate is not None:
            self.idempotency[replay_key] = duplicate.source_id
            return duplicate.model_copy(update={"idempotent_replay": True})
        parent = None
        revision_number = 1
        if payload.parent_source_id:
            parent = self.sources.get((tenant_id, payload.parent_source_id))
            if parent is None or parent.project_id != project_id:
                raise _not_found("KNOWLEDGE_SOURCE_NOT_FOUND", {"source_id": payload.parent_source_id})
            if parent.status != "active":
                raise StarletteHTTPException(status_code=409, detail={
                    "code": "STATE_CONFLICT",
                    "details": {"source_id": parent.source_id, "status": parent.status},
                })
            revision_number = parent.revision_number + 1
        source_id = f"source_{uuid4().hex[:12]}"
        segments = segment_source_text(source_id, payload.content_text, max_characters=payload.segment_max_characters)
        data = KnowledgeSourceData(
            source_id=source_id,
            tenant_id=tenant_id,
            project_id=project_id,
            source_type=payload.source_type,
            title=payload.title,
            source_uri=payload.source_uri,
            content_sha256=content_sha256,
            byte_size=len(payload.content_text.encode("utf-8")),
            authority_level=payload.authority_level,
            risk_level=payload.risk_level,
            status="active",
            revision_number=revision_number,
            parent_source_id=payload.parent_source_id,
            segment_count=len(segments),
            captured_at=payload.captured_at or utc_now(),
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
        )
        self.sources[(tenant_id, source_id)] = data
        self.source_contents[(tenant_id, source_id)] = payload.content_text
        self.source_segments[(tenant_id, source_id)] = segments
        self.idempotency[replay_key] = source_id
        if parent is not None:
            self.sources[(tenant_id, parent.source_id)] = parent.model_copy(update={"status": "stale"})
        return data

    def revise_source(self, tenant_id: str, project_id: str, source_id: str, payload: KnowledgeSourceCreateRequest) -> KnowledgeSourceData:
        return self.create_source(
            tenant_id,
            project_id,
            payload.model_copy(update={"parent_source_id": source_id}),
        )

    def list_sources(self, tenant_id: str, project_id: str) -> list[KnowledgeSourceData]:
        return [value for (item_tenant, _), value in self.sources.items() if item_tenant == tenant_id and value.project_id == project_id]

    def search_segments(self, tenant_id: str, project_id: str, query: str, limit: int) -> KnowledgeSearchData:
        candidates: list[dict[str, Any]] = []
        now = utc_now()
        for (item_tenant, source_id), segments in self.source_segments.items():
            source = self.sources.get((item_tenant, source_id))
            if (
                item_tenant != tenant_id
                or source is None
                or source.project_id != project_id
                or source.status != "active"
                or (source.valid_from is not None and _as_utc(source.valid_from) > now)
                or (source.valid_until is not None and _as_utc(source.valid_until) <= now)
            ):
                continue
            for segment in segments:
                match = _lexical_match(query, segment.text)
                if match is None:
                    continue
                candidates.append({
                    "segment": segment,
                    "source": source,
                    "match_type": match[0],
                    "matched_terms": match[1],
                    "first_match": match[2],
                })
        return _knowledge_search_data(query, candidates, limit=limit, candidate_limit_reached=False)

    def propose_fact(self, tenant_id: str, project_id: str, payload: FactProposalRequest) -> FactRevisionData:
        missing = [source_id for source_id in payload.source_ids if (tenant_id, source_id) not in self.sources]
        if missing:
            raise _not_found("KNOWLEDGE_SOURCE_NOT_FOUND", {"source_ids": missing})
        fact_id = f"fact_{uuid4().hex[:12]}"
        revision_id = f"factrev_{uuid4().hex[:12]}"
        now = utc_now()
        data = FactRevisionData(
            fact_id=fact_id,
            revision_id=revision_id,
            tenant_id=tenant_id,
            project_id=project_id,
            title=payload.title,
            fact_type=payload.fact_type,
            fact_text=payload.fact_text,
            content_sha256=sha256_text(payload.fact_text),
            revision_number=1,
            status="proposed",
            source_ids=payload.source_ids,
            risk_level=payload.risk_level,
            disclosure=payload.disclosure,
            created_by=payload.created_by,
            created_at=now,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            eligible_for_generation=False,
            eligibility_reason="human_review_required" if payload.source_ids else "evidence_required",
        )
        self.facts[(tenant_id, revision_id)] = data
        return data

    def revise_fact(self, tenant_id: str, project_id: str, fact_id: str, payload: FactProposalRequest) -> FactRevisionData:
        current = [value for (item_tenant, _), value in self.facts.items() if item_tenant == tenant_id and value.project_id == project_id and value.fact_id == fact_id]
        if not current:
            raise _not_found("FACT_NOT_FOUND", {"fact_id": fact_id})
        missing = [source_id for source_id in payload.source_ids if (tenant_id, source_id) not in self.sources]
        if missing:
            raise _not_found("KNOWLEDGE_SOURCE_NOT_FOUND", {"source_ids": missing})
        revision_id = f"factrev_{uuid4().hex[:12]}"
        data = FactRevisionData(
            fact_id=fact_id,
            revision_id=revision_id,
            tenant_id=tenant_id,
            project_id=project_id,
            title=payload.title,
            fact_type=payload.fact_type,
            fact_text=payload.fact_text,
            content_sha256=sha256_text(payload.fact_text),
            revision_number=max(value.revision_number for value in current) + 1,
            status="proposed",
            source_ids=payload.source_ids,
            risk_level=payload.risk_level,
            disclosure=payload.disclosure,
            created_by=payload.created_by,
            created_at=utc_now(),
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            eligible_for_generation=False,
            eligibility_reason="human_review_required" if payload.source_ids else "evidence_required",
        )
        self.facts[(tenant_id, revision_id)] = data
        return data

    def _effective_fact(self, revision: FactRevisionData, at: datetime) -> FactRevisionData:
        reason = "approved_current_fact"
        eligible = revision.status == "approved"
        if revision.status != "approved":
            reason = revision.status if revision.status in {"rejected", "superseded"} else ("evidence_required" if not revision.source_ids else "human_review_required")
        elif any(
            conflict.tenant_id == revision.tenant_id
            and conflict.project_id == revision.project_id
            and conflict.fact_id == revision.fact_id
            and conflict.status == "open"
            for conflict in self.conflicts.values()
        ):
            eligible, reason = False, "open_conflict"
        elif revision.valid_from and _as_utc(revision.valid_from) > at:
            eligible, reason = False, "not_yet_valid"
        elif revision.valid_until and _as_utc(revision.valid_until) <= at:
            eligible, reason = False, "expired"
        elif not revision.source_ids:
            eligible, reason = False, "evidence_required"
        else:
            current_sources = [self.sources.get((revision.tenant_id, source_id)) for source_id in revision.source_ids]
            if any(
                source is None
                or source.project_id != revision.project_id
                or source.status != "active"
                or (source.valid_from is not None and _as_utc(source.valid_from) > at)
                or (source.valid_until is not None and _as_utc(source.valid_until) <= at)
                for source in current_sources
            ):
                eligible, reason = False, "source_stale"
        return revision.model_copy(update={"eligible_for_generation": eligible, "eligibility_reason": reason})

    def list_facts(self, tenant_id: str, project_id: str) -> list[FactRevisionData]:
        now = utc_now()
        return [
            self._effective_fact(value, now)
            for (item_tenant, _), value in self.facts.items()
            if item_tenant == tenant_id and value.project_id == project_id
        ]

    def review_revision(self, tenant_id: str, project_id: str, revision_id: str, payload: FactRevisionReviewRequest) -> FactRevisionData:
        key = (tenant_id, revision_id)
        revision = self.facts.get(key)
        if revision is None or revision.project_id != project_id:
            raise _not_found("FACT_REVISION_NOT_FOUND", {"revision_id": revision_id})
        if payload.action == "approved" and not revision.source_ids:
            raise StarletteHTTPException(status_code=400, detail={"code": "FACT_SOURCE_REQUIRED", "details": {"revision_id": revision_id}})
        if payload.action == "approved" and any(
            item.fact_id == revision.fact_id and item.status == "open" for item in self.conflicts.values()
        ):
            raise StarletteHTTPException(status_code=409, detail={"code": "FACT_CONFLICT_OPEN", "details": {"fact_id": revision.fact_id}})
        now = utc_now()
        if payload.action == "approved" and any(
            (source := self.sources.get((tenant_id, source_id))) is None
            or source.project_id != project_id
            or source.status != "active"
            or (source.valid_from is not None and _as_utc(source.valid_from) > now)
            or (source.valid_until is not None and _as_utc(source.valid_until) <= now)
            for source_id in revision.source_ids
        ):
            raise StarletteHTTPException(status_code=409, detail={"code": "FACT_SOURCE_STALE", "details": {"source_ids": revision.source_ids}})
        if payload.action == "approved":
            for existing_key, existing in list(self.facts.items()):
                if existing.fact_id == revision.fact_id and existing.status == "approved" and existing.revision_id != revision_id:
                    self.facts[existing_key] = existing.model_copy(
                        update={
                            "status": "superseded",
                            "eligible_for_generation": False,
                            "eligibility_reason": "superseded",
                        }
                    )
        updated = revision.model_copy(
            update={
                "status": payload.action,
                "reviewed_by": payload.reviewed_by,
                "reviewed_at": now,
                "review_note": payload.review_note,
                "eligible_for_generation": payload.action == "approved",
                "eligibility_reason": "approved_current_fact" if payload.action == "approved" else "rejected",
            }
        )
        self.facts[key] = updated
        return self._effective_fact(updated, now)

    def create_conflict(self, tenant_id: str, project_id: str, fact_id: str, payload: FactConflictCreateRequest) -> FactConflictData:
        revisions = {
            value.revision_id: value
            for value in self.facts.values()
            if value.tenant_id == tenant_id and value.project_id == project_id
        }
        if payload.left_revision_id not in revisions or payload.right_revision_id not in revisions:
            raise _not_found("FACT_REVISION_NOT_FOUND", {"revision_ids": [payload.left_revision_id, payload.right_revision_id]})
        if any(revisions[item].fact_id != fact_id for item in (payload.left_revision_id, payload.right_revision_id)):
            raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"fact_id": fact_id}})
        existing = next((
            conflict
            for conflict in self.conflicts.values()
            if conflict.tenant_id == tenant_id
            and conflict.project_id == project_id
            and conflict.fact_id == fact_id
            and {conflict.left_revision_id, conflict.right_revision_id} == {payload.left_revision_id, payload.right_revision_id}
        ), None)
        if existing is not None:
            raise StarletteHTTPException(status_code=409, detail={
                "code": "STATE_CONFLICT",
                "details": {"conflict_id": existing.conflict_id, "status": existing.status},
            })
        data = FactConflictData(
            conflict_id=f"conflict_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            project_id=project_id,
            fact_id=fact_id,
            left_revision_id=payload.left_revision_id,
            right_revision_id=payload.right_revision_id,
            conflict_type=payload.conflict_type,
            description=payload.description,
            status="open",
            detected_at=utc_now(),
        )
        self.conflicts[(tenant_id, data.conflict_id)] = data
        return data

    def list_conflicts(self, tenant_id: str, project_id: str, status: Optional[str] = None) -> list[FactConflictData]:
        return sorted(
            [
                conflict
                for (item_tenant, _), conflict in self.conflicts.items()
                if item_tenant == tenant_id
                and conflict.project_id == project_id
                and (status is None or conflict.status == status)
            ],
            key=lambda conflict: conflict.detected_at,
            reverse=True,
        )

    def resolve_conflict(self, tenant_id: str, project_id: str, conflict_id: str, payload: FactConflictResolveRequest) -> FactConflictData:
        key = (tenant_id, conflict_id)
        conflict = self.conflicts.get(key)
        if conflict is None or conflict.project_id != project_id:
            raise _not_found("FACT_CONFLICT_NOT_FOUND", {"conflict_id": conflict_id})
        updated = conflict.model_copy(update={"status": payload.resolution, "resolved_by": payload.resolved_by, "resolved_at": utc_now(), "resolution_note": payload.resolution_note})
        self.conflicts[key] = updated
        return updated

    def create_governed_content(self, tenant_id: str, project_id: str, payload: GovernedContentCreateRequest) -> GovernedContentData:
        revisions = []
        supports: list[tuple[FactRevisionData, str, int, int]] = []
        for revision_id in payload.fact_revision_ids:
            revision = self.facts.get((tenant_id, revision_id))
            if revision is None or revision.project_id != project_id:
                raise _not_found("FACT_REVISION_NOT_FOUND", {"revision_id": revision_id})
            revision = self._effective_fact(revision, utc_now())
            if not revision.eligible_for_generation or revision.status != "approved":
                raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_EVIDENCE_MISSING", "details": {"revision_id": revision_id, "reason": revision.eligibility_reason}})
            revisions.append(revision)
            for source_id in revision.source_ids:
                source_text = self.source_contents.get((tenant_id, source_id), "")
                source = self.sources.get((tenant_id, source_id))
                if source is None or sha256_text(source_text) != source.content_sha256:
                    raise StarletteHTTPException(
                        status_code=409,
                        detail={
                            "code": "CONTENT_EVIDENCE_MISSING",
                            "details": {
                                "revision_id": revision_id,
                                "reason": "source_content_integrity_failed",
                                "source_id": source_id,
                            },
                        },
                    )
                start = source_text.find(revision.fact_text)
                if start >= 0:
                    supports.append((revision, source_id, start, start + len(revision.fact_text)))
                    break
            else:
                raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_EVIDENCE_MISSING", "details": {"revision_id": revision_id, "reason": "exact_source_boundary_missing"}})
        created_at = utc_now()
        asset_id = f"asset_{uuid4().hex[:12]}"
        assertion_ids = [f"claim_{uuid4().hex[:12]}" for _ in revisions]
        support_ids = [f"support_{uuid4().hex[:12]}" for _ in supports]
        blueprint = _page_blueprint_or_error(
            payload,
            [
                {
                    "fact_id": revision.fact_id,
                    "revision_id": revision.revision_id,
                    "title": revision.title,
                    "fact_text": revision.fact_text,
                    "status": revision.status,
                    "eligible_for_generation": revision.eligible_for_generation,
                    "valid_until": revision.valid_until.isoformat() if revision.valid_until else None,
                    "conflict_status": "none",
                    "support_ids": [support_id],
                    "evidence": [
                        {
                            "source_id": source_id,
                            "source_sha256": sha256_text(
                                self.source_contents[(tenant_id, source_id)]
                            ),
                            "source_start": start,
                            "source_end": end,
                            "quoted_text": revision.fact_text,
                        }
                    ],
                }
                for (revision, source_id, start, end), support_id in zip(supports, support_ids)
            ],
        )
        data = GovernedContentData(
            asset_id=asset_id,
            tenant_id=tenant_id,
            project_id=project_id,
            asset_type=payload.asset_type,
            title=blueprint["title"],
            body_md=blueprint["body_md"],
            status="draft",
            generation_mode="evidence_bound_page_blueprint",
            skill_id=blueprint["skill_id"],
            skill_version=blueprint["skill_version"],
            blueprint_sha256=blueprint["blueprint_sha256"],
            section_count=len(blueprint["sections"]),
            fact_revision_ids=payload.fact_revision_ids,
            claim_assertion_ids=assertion_ids,
            claim_support_ids=support_ids,
            created_at=created_at,
        )
        self.content_assets[(tenant_id, asset_id)] = data
        for assertion_id, support_id in zip(assertion_ids, support_ids):
            self.claim_support_links[(tenant_id, support_id)] = assertion_id
        return data

    def list_governed_content(self, tenant_id: str, project_id: str) -> list[GovernedContentData]:
        return sorted(
            [
                asset
                for (item_tenant, _), asset in self.content_assets.items()
                if item_tenant == tenant_id and asset.project_id == project_id
            ],
            key=lambda asset: asset.created_at,
            reverse=True,
        )


class MySQLKnowledgeRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _ensure_project(conn: Any, tenant_id: str, project_id: str) -> None:
        exists = conn.execute(text("SELECT id FROM airank_projects WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL"), {"tenant_id": tenant_id, "project_id": project_id}).first()
        if exists is None:
            raise _not_found("PROJECT_NOT_FOUND", {"project_id": project_id})

    @staticmethod
    def _source_data(row: Mapping[str, Any], *, replay: bool = False) -> KnowledgeSourceData:
        return KnowledgeSourceData(
            source_id=row["id"], tenant_id=row["tenant_id"], project_id=row["project_id"], source_type=row["source_type"], title=row["title"], source_uri=row["source_uri"], content_sha256=row["content_sha256"], byte_size=int(row["byte_size"]), authority_level=row["authority_level"], risk_level=row["risk_level"], status=row["status"], revision_number=int(row["revision_number"]), parent_source_id=row["parent_source_id"], segment_count=int(row["segment_count"]), captured_at=_as_utc(row["captured_at"]), valid_from=_optional_utc(row["valid_from"]), valid_until=_optional_utc(row["valid_until"]), idempotent_replay=replay,
        )

    def create_source(self, tenant_id: str, project_id: str, payload: KnowledgeSourceCreateRequest) -> KnowledgeSourceData:
        content_sha256 = sha256_text(payload.content_text)
        captured_at = payload.captured_at or utc_now()
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            existing = conn.execute(text("""
                SELECT s.*, c.byte_size,
                       (SELECT COUNT(*) FROM airank_knowledge_segments g WHERE g.tenant_id=s.tenant_id AND g.knowledge_source_id=s.id) AS segment_count
                FROM airank_knowledge_sources s JOIN airank_knowledge_source_contents c ON c.knowledge_source_id=s.id
                WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                  AND (s.idempotency_key=:idempotency_key OR s.content_sha256=:content_sha256)
                ORDER BY (s.idempotency_key=:idempotency_key) DESC LIMIT 1
            """), {"tenant_id": tenant_id, "project_id": project_id, "idempotency_key": payload.idempotency_key, "content_sha256": content_sha256}).mappings().first()
            if existing is not None:
                return self._source_data(existing, replay=True)
            revision_number = 1
            if payload.parent_source_id:
                parent = conn.execute(text("SELECT id, revision_number, status FROM airank_knowledge_sources WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:source_id FOR UPDATE"), {"tenant_id": tenant_id, "project_id": project_id, "source_id": payload.parent_source_id}).mappings().first()
                if parent is None:
                    raise _not_found("KNOWLEDGE_SOURCE_NOT_FOUND", {"source_id": payload.parent_source_id})
                if parent["status"] != "active":
                    raise StarletteHTTPException(status_code=409, detail={
                        "code": "STATE_CONFLICT",
                        "details": {"source_id": parent["id"], "status": parent["status"]},
                    })
                revision_number = int(parent["revision_number"]) + 1
            source_id = f"source_{uuid4().hex[:12]}"
            segments = segment_source_text(source_id, payload.content_text, max_characters=payload.segment_max_characters)
            conn.execute(text("""
                INSERT INTO airank_knowledge_sources (
                  id, tenant_id, project_id, parent_source_id, idempotency_key,
                  source_type, title, source_uri, content_sha256, authority_level,
                  risk_level, status, revision_number, captured_at, valid_from, valid_until
                ) VALUES (
                  :id, :tenant_id, :project_id, :parent_source_id, :idempotency_key,
                  :source_type, :title, :source_uri, :content_sha256, :authority_level,
                  :risk_level, 'active', :revision_number, :captured_at, :valid_from, :valid_until
                )
            """), {"id": source_id, "tenant_id": tenant_id, "project_id": project_id, "parent_source_id": payload.parent_source_id, "idempotency_key": payload.idempotency_key, "source_type": payload.source_type, "title": payload.title, "source_uri": payload.source_uri, "content_sha256": content_sha256, "authority_level": payload.authority_level, "risk_level": payload.risk_level, "revision_number": revision_number, "captured_at": captured_at, "valid_from": payload.valid_from, "valid_until": payload.valid_until})
            byte_size = len(payload.content_text.encode("utf-8"))
            conn.execute(text("""
                INSERT INTO airank_knowledge_source_contents (
                  knowledge_source_id, tenant_id, project_id, content_text,
                  content_sha256, content_type, byte_size
                ) VALUES (
                  :knowledge_source_id, :tenant_id, :project_id, :content_text,
                  :content_sha256, :content_type, :byte_size
                )
            """), {"knowledge_source_id": source_id, "tenant_id": tenant_id, "project_id": project_id, "content_text": payload.content_text, "content_sha256": content_sha256, "content_type": payload.content_type, "byte_size": byte_size})
            for segment in segments:
                conn.execute(text("""
                    INSERT INTO airank_knowledge_segments (
                      id, tenant_id, project_id, knowledge_source_id, segment_index,
                      segment_text, source_start, source_end, content_sha256
                    ) VALUES (
                      :id, :tenant_id, :project_id, :knowledge_source_id, :segment_index,
                      :segment_text, :source_start, :source_end, :content_sha256
                    )
                """), {"id": segment.id, "tenant_id": tenant_id, "project_id": project_id, "knowledge_source_id": source_id, "segment_index": segment.segment_index, "segment_text": segment.text, "source_start": segment.source_start, "source_end": segment.source_end, "content_sha256": segment.content_sha256})
            if payload.parent_source_id:
                conn.execute(text("""
                    UPDATE airank_knowledge_sources SET status='stale'
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND id=:source_id AND status='active'
                """), {"tenant_id": tenant_id, "project_id": project_id, "source_id": payload.parent_source_id})
        return KnowledgeSourceData(source_id=source_id, tenant_id=tenant_id, project_id=project_id, source_type=payload.source_type, title=payload.title, source_uri=payload.source_uri, content_sha256=content_sha256, byte_size=byte_size, authority_level=payload.authority_level, risk_level=payload.risk_level, status="active", revision_number=revision_number, parent_source_id=payload.parent_source_id, segment_count=len(segments), captured_at=captured_at, valid_from=payload.valid_from, valid_until=payload.valid_until)

    def revise_source(self, tenant_id: str, project_id: str, source_id: str, payload: KnowledgeSourceCreateRequest) -> KnowledgeSourceData:
        return self.create_source(
            tenant_id,
            project_id,
            payload.model_copy(update={"parent_source_id": source_id}),
        )

    def list_sources(self, tenant_id: str, project_id: str) -> list[KnowledgeSourceData]:
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            rows = conn.execute(text("""
                SELECT s.*, c.byte_size,
                       (SELECT COUNT(*) FROM airank_knowledge_segments g WHERE g.tenant_id=s.tenant_id AND g.knowledge_source_id=s.id) AS segment_count
                FROM airank_knowledge_sources s JOIN airank_knowledge_source_contents c ON c.knowledge_source_id=s.id
                WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                ORDER BY s.captured_at DESC, s.id ASC
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        return [self._source_data(row) for row in rows]

    def search_segments(self, tenant_id: str, project_id: str, query: str, limit: int) -> KnowledgeSearchData:
        candidate_limit = 5000
        now = utc_now()
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            rows = conn.execute(text("""
                SELECT g.id AS segment_id, g.knowledge_source_id, g.segment_index,
                       g.segment_text, g.source_start, g.source_end, g.content_sha256,
                       s.revision_number, s.title, s.source_uri
                FROM airank_knowledge_segments g
                JOIN airank_knowledge_sources s ON s.id=g.knowledge_source_id
                WHERE g.tenant_id=:tenant_id AND g.project_id=:project_id
                  AND s.tenant_id=:tenant_id AND s.project_id=:project_id
                  AND s.status='active'
                  AND (s.valid_from IS NULL OR s.valid_from<=:now)
                  AND (s.valid_until IS NULL OR s.valid_until>:now)
                ORDER BY s.revision_number DESC, g.segment_index ASC, g.id ASC
                LIMIT :candidate_limit
            """), {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "now": now,
                "candidate_limit": candidate_limit + 1,
            }).mappings().all()
        candidates: list[dict[str, Any]] = []
        for row in rows[:candidate_limit]:
            match = _lexical_match(query, row["segment_text"])
            if match is None:
                continue
            candidates.append({
                "row": row,
                "match_type": match[0],
                "matched_terms": match[1],
                "first_match": match[2],
            })
        return _knowledge_search_data(
            query,
            candidates,
            limit=limit,
            candidate_limit_reached=len(rows) > candidate_limit,
        )

    @staticmethod
    def _fact_data(row: Mapping[str, Any], open_conflict_count: int = 0) -> FactRevisionData:
        sources = row["source_ids_json"]
        if isinstance(sources, str):
            sources = json.loads(sources)
        source_ids = list(sources or [])
        now = utc_now()
        valid_until = row["valid_until"]
        if valid_until is not None and valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        valid_from = row["valid_from"]
        if valid_from is not None and valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=timezone.utc)
        current_source_count = int(row.get("current_source_count", len(source_ids)))
        eligible = (
            row["revision_status"] == "approved"
            and bool(source_ids)
            and current_source_count == len(source_ids)
            and not open_conflict_count
            and (valid_from is None or valid_from <= now)
            and (valid_until is None or valid_until > now)
        )
        if eligible:
            reason = "approved_current_fact"
        elif row["revision_status"] in {"rejected", "superseded"}:
            reason = row["revision_status"]
        elif open_conflict_count:
            reason = "open_conflict"
        elif valid_from is not None and valid_from > now:
            reason = "not_yet_valid"
        elif valid_until is not None and valid_until <= now:
            reason = "expired"
        elif not source_ids:
            reason = "evidence_required"
        elif current_source_count != len(source_ids):
            reason = "source_stale"
        else:
            reason = "human_review_required"
        return FactRevisionData(
            fact_id=row["fact_id"], revision_id=row["revision_id"], tenant_id=row["tenant_id"], project_id=row["project_id"], title=row["title"], fact_type=row["fact_type"], fact_text=row["fact_text"], content_sha256=row["content_sha256"], revision_number=int(row["revision_number"]), status=row["revision_status"], source_ids=source_ids, risk_level=row["risk_level"], disclosure=row["disclosure"], created_by=row["created_by"], created_at=_as_utc(row["created_at"]), reviewed_by=row["reviewed_by"], reviewed_at=_optional_utc(row["reviewed_at"]), review_note=row["review_note"], valid_from=valid_from, valid_until=valid_until, eligible_for_generation=eligible, eligibility_reason=reason,
        )

    def propose_fact(self, tenant_id: str, project_id: str, payload: FactProposalRequest) -> FactRevisionData:
        now = utc_now()
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            if payload.source_ids:
                source_query = text("SELECT COUNT(*) FROM airank_knowledge_sources WHERE tenant_id=:tenant_id AND project_id=:project_id AND status='active' AND id IN :source_ids").bindparams(bindparam("source_ids", expanding=True))
                count = conn.execute(source_query, {"tenant_id": tenant_id, "project_id": project_id, "source_ids": payload.source_ids}).scalar_one()
                if int(count) != len(payload.source_ids):
                    raise _not_found("KNOWLEDGE_SOURCE_NOT_FOUND", {"source_ids": payload.source_ids})
            fact_id = f"fact_{uuid4().hex[:12]}"
            revision_id = f"factrev_{uuid4().hex[:12]}"
            content_sha256 = sha256_text(payload.fact_text)
            conn.execute(text("""
                INSERT INTO airank_fact_atoms (
                  id, tenant_id, project_id, fact_type, title, fact_text,
                  current_revision_id, risk_level, valid_until, trust_level,
                  disclosure, status, owner_user_id, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :fact_type, :title, :fact_text,
                  NULL, :risk_level, :valid_until, 'C', :disclosure, 'draft',
                  :created_by, :created_at, :created_at
                )
            """), {"id": fact_id, "tenant_id": tenant_id, "project_id": project_id, "fact_type": payload.fact_type, "title": payload.title, "fact_text": payload.fact_text, "risk_level": payload.risk_level, "valid_until": payload.valid_until, "disclosure": payload.disclosure, "created_by": payload.created_by, "created_at": now})
            conn.execute(text("""
                INSERT INTO airank_fact_revisions (
                  id, tenant_id, project_id, fact_atom_id, revision_number,
                  fact_text, content_sha256, status, source_ids_json,
                  valid_from, valid_until, created_by, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :fact_atom_id, 1,
                  :fact_text, :content_sha256, 'proposed', :source_ids_json,
                  :valid_from, :valid_until, :created_by, :created_at
                )
            """), {"id": revision_id, "tenant_id": tenant_id, "project_id": project_id, "fact_atom_id": fact_id, "fact_text": payload.fact_text, "content_sha256": content_sha256, "source_ids_json": json.dumps(payload.source_ids, ensure_ascii=False), "valid_from": payload.valid_from, "valid_until": payload.valid_until, "created_by": payload.created_by, "created_at": now})
            row = {"fact_id": fact_id, "revision_id": revision_id, "tenant_id": tenant_id, "project_id": project_id, "title": payload.title, "fact_type": payload.fact_type, "fact_text": payload.fact_text, "content_sha256": content_sha256, "revision_number": 1, "revision_status": "proposed", "source_ids_json": payload.source_ids, "risk_level": payload.risk_level, "disclosure": payload.disclosure, "created_by": payload.created_by, "created_at": now, "reviewed_by": None, "reviewed_at": None, "review_note": None, "valid_from": payload.valid_from, "valid_until": payload.valid_until}
        return self._fact_data(row)

    def revise_fact(self, tenant_id: str, project_id: str, fact_id: str, payload: FactProposalRequest) -> FactRevisionData:
        now = utc_now()
        with self.engine.begin() as conn:
            fact = conn.execute(text("SELECT id FROM airank_fact_atoms WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:fact_id AND deleted_at IS NULL FOR UPDATE"), {"tenant_id": tenant_id, "project_id": project_id, "fact_id": fact_id}).first()
            if fact is None:
                raise _not_found("FACT_NOT_FOUND", {"fact_id": fact_id})
            if payload.source_ids:
                source_query = text("SELECT COUNT(*) FROM airank_knowledge_sources WHERE tenant_id=:tenant_id AND project_id=:project_id AND status='active' AND id IN :source_ids").bindparams(bindparam("source_ids", expanding=True))
                count = conn.execute(source_query, {"tenant_id": tenant_id, "project_id": project_id, "source_ids": payload.source_ids}).scalar_one()
                if int(count) != len(payload.source_ids):
                    raise _not_found("KNOWLEDGE_SOURCE_NOT_FOUND", {"source_ids": payload.source_ids})
            revision_number = int(conn.execute(text("SELECT COALESCE(MAX(revision_number), 0) FROM airank_fact_revisions WHERE tenant_id=:tenant_id AND fact_atom_id=:fact_id"), {"tenant_id": tenant_id, "fact_id": fact_id}).scalar_one()) + 1
            revision_id = f"factrev_{uuid4().hex[:12]}"
            content_sha256 = sha256_text(payload.fact_text)
            conn.execute(text("""
                INSERT INTO airank_fact_revisions (
                  id, tenant_id, project_id, fact_atom_id, revision_number,
                  fact_text, content_sha256, status, source_ids_json,
                  valid_from, valid_until, created_by, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :fact_atom_id, :revision_number,
                  :fact_text, :content_sha256, 'proposed', :source_ids_json,
                  :valid_from, :valid_until, :created_by, :created_at
                )
            """), {"id": revision_id, "tenant_id": tenant_id, "project_id": project_id, "fact_atom_id": fact_id, "revision_number": revision_number, "fact_text": payload.fact_text, "content_sha256": content_sha256, "source_ids_json": json.dumps(payload.source_ids, ensure_ascii=False), "valid_from": payload.valid_from, "valid_until": payload.valid_until, "created_by": payload.created_by, "created_at": now})
            conn.execute(text("UPDATE airank_fact_atoms SET title=:title, fact_type=:fact_type, fact_text=:fact_text, risk_level=:risk_level, disclosure=:disclosure, valid_until=:valid_until, updated_at=:updated_at WHERE tenant_id=:tenant_id AND id=:fact_id"), {"title": payload.title, "fact_type": payload.fact_type, "fact_text": payload.fact_text, "risk_level": payload.risk_level, "disclosure": payload.disclosure, "valid_until": payload.valid_until, "updated_at": now, "tenant_id": tenant_id, "fact_id": fact_id})
            row = self._fact_rows(conn, tenant_id, project_id, revision_id=revision_id)[0]
        return self._fact_data(row, int(row["open_conflict_count"]))

    def _fact_rows(self, conn: Any, tenant_id: str, project_id: str, *, revision_id: Optional[str] = None) -> list[Mapping[str, Any]]:
        condition = "AND r.id=:revision_id" if revision_id else ""
        return conn.execute(text(f"""
            SELECT f.id AS fact_id, r.id AS revision_id, f.tenant_id, f.project_id,
                   f.title, f.fact_type, r.fact_text, r.content_sha256,
                   r.revision_number, r.status AS revision_status, r.source_ids_json,
                   f.risk_level, f.disclosure, r.created_by, r.created_at,
                   r.reviewed_by, r.reviewed_at, r.review_note, r.valid_from, r.valid_until,
                   (SELECT COUNT(*) FROM airank_fact_conflicts c
                    WHERE c.tenant_id=f.tenant_id AND c.fact_atom_id=f.id AND c.status='open') AS open_conflict_count
                   ,(SELECT COUNT(*) FROM airank_knowledge_sources s
                     WHERE s.tenant_id=f.tenant_id AND s.project_id=f.project_id
                       AND s.status='active'
                       AND (s.valid_from IS NULL OR s.valid_from<=UTC_TIMESTAMP(6))
                       AND (s.valid_until IS NULL OR s.valid_until>UTC_TIMESTAMP(6))
                       AND JSON_CONTAINS(r.source_ids_json, JSON_QUOTE(s.id), '$')) AS current_source_count
            FROM airank_fact_atoms f JOIN airank_fact_revisions r ON r.fact_atom_id=f.id
            WHERE f.tenant_id=:tenant_id AND f.project_id=:project_id AND f.deleted_at IS NULL
              {condition}
            ORDER BY f.updated_at DESC, r.revision_number DESC
        """), {"tenant_id": tenant_id, "project_id": project_id, "revision_id": revision_id}).mappings().all()

    def list_facts(self, tenant_id: str, project_id: str) -> list[FactRevisionData]:
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            rows = self._fact_rows(conn, tenant_id, project_id)
        return [self._fact_data(row, int(row["open_conflict_count"])) for row in rows]

    def review_revision(self, tenant_id: str, project_id: str, revision_id: str, payload: FactRevisionReviewRequest) -> FactRevisionData:
        reviewed_at = utc_now()
        with self.engine.begin() as conn:
            rows = self._fact_rows(conn, tenant_id, project_id, revision_id=revision_id)
            if not rows:
                raise _not_found("FACT_REVISION_NOT_FOUND", {"revision_id": revision_id})
            row = rows[0]
            source_ids = row["source_ids_json"] if isinstance(row["source_ids_json"], list) else json.loads(row["source_ids_json"] or "[]")
            if payload.action == "approved":
                if not source_ids:
                    raise StarletteHTTPException(status_code=400, detail={"code": "FACT_SOURCE_REQUIRED", "details": {"revision_id": revision_id}})
                if int(row["open_conflict_count"]):
                    raise StarletteHTTPException(status_code=409, detail={"code": "FACT_CONFLICT_OPEN", "details": {"fact_id": row["fact_id"]}})
                current_source_query = text("SELECT COUNT(*) FROM airank_knowledge_sources WHERE tenant_id=:tenant_id AND project_id=:project_id AND status='active' AND (valid_from IS NULL OR valid_from<=:now) AND (valid_until IS NULL OR valid_until>:now) AND id IN :source_ids").bindparams(bindparam("source_ids", expanding=True))
                current_count = conn.execute(current_source_query, {"tenant_id": tenant_id, "project_id": project_id, "now": reviewed_at, "source_ids": source_ids}).scalar_one()
                if int(current_count) != len(source_ids):
                    raise StarletteHTTPException(status_code=409, detail={"code": "FACT_SOURCE_STALE", "details": {"source_ids": source_ids}})
                conn.execute(text("UPDATE airank_fact_revisions SET status='superseded' WHERE tenant_id=:tenant_id AND fact_atom_id=:fact_id AND status='approved' AND id<>:revision_id"), {"tenant_id": tenant_id, "fact_id": row["fact_id"], "revision_id": revision_id})
            conn.execute(text("UPDATE airank_fact_revisions SET status=:status, reviewed_by=:reviewed_by, reviewed_at=:reviewed_at, review_note=:review_note WHERE tenant_id=:tenant_id AND id=:revision_id"), {"status": payload.action, "reviewed_by": payload.reviewed_by, "reviewed_at": reviewed_at, "review_note": payload.review_note, "tenant_id": tenant_id, "revision_id": revision_id})
            fact_status = "confirmed" if payload.action == "approved" else "rejected"
            current_revision_id = revision_id if payload.action == "approved" else None
            conn.execute(text("UPDATE airank_fact_atoms SET status=:status, current_revision_id=:current_revision_id, reviewed_by=:reviewed_by, reviewed_at=:reviewed_at, updated_at=:reviewed_at WHERE tenant_id=:tenant_id AND id=:fact_id"), {"status": fact_status, "current_revision_id": current_revision_id, "reviewed_by": payload.reviewed_by, "reviewed_at": reviewed_at, "tenant_id": tenant_id, "fact_id": row["fact_id"]})
            updated = self._fact_rows(conn, tenant_id, project_id, revision_id=revision_id)[0]
        return self._fact_data(updated, int(updated["open_conflict_count"]))

    def create_conflict(self, tenant_id: str, project_id: str, fact_id: str, payload: FactConflictCreateRequest) -> FactConflictData:
        detected_at = utc_now()
        with self.engine.begin() as conn:
            revision_query = text("SELECT id, fact_atom_id FROM airank_fact_revisions WHERE tenant_id=:tenant_id AND project_id=:project_id AND id IN :revision_ids ORDER BY id FOR UPDATE").bindparams(bindparam("revision_ids", expanding=True))
            rows = conn.execute(revision_query, {"tenant_id": tenant_id, "project_id": project_id, "revision_ids": [payload.left_revision_id, payload.right_revision_id]}).mappings().all()
            if len(rows) != 2:
                raise _not_found("FACT_REVISION_NOT_FOUND", {"revision_ids": [payload.left_revision_id, payload.right_revision_id]})
            if any(row["fact_atom_id"] != fact_id for row in rows):
                raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"fact_id": fact_id}})
            existing = conn.execute(text("""
                SELECT id, status FROM airank_fact_conflicts
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND fact_atom_id=:fact_id
                  AND ((left_revision_id=:left_revision_id AND right_revision_id=:right_revision_id)
                    OR (left_revision_id=:right_revision_id AND right_revision_id=:left_revision_id))
                LIMIT 1
            """), {
                "tenant_id": tenant_id, "project_id": project_id, "fact_id": fact_id,
                "left_revision_id": payload.left_revision_id, "right_revision_id": payload.right_revision_id,
            }).mappings().first()
            if existing is not None:
                raise StarletteHTTPException(status_code=409, detail={
                    "code": "STATE_CONFLICT",
                    "details": {"conflict_id": existing["id"], "status": existing["status"]},
                })
            conflict_id = f"conflict_{uuid4().hex[:12]}"
            conn.execute(text("""
                INSERT INTO airank_fact_conflicts (
                  id, tenant_id, project_id, fact_atom_id, left_revision_id,
                  right_revision_id, conflict_type, description, status, detected_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :fact_id, :left_revision_id,
                  :right_revision_id, :conflict_type, :description, 'open', :detected_at
                )
            """), {"id": conflict_id, "tenant_id": tenant_id, "project_id": project_id, "fact_id": fact_id, "left_revision_id": payload.left_revision_id, "right_revision_id": payload.right_revision_id, "conflict_type": payload.conflict_type, "description": payload.description, "detected_at": detected_at})
        return FactConflictData(conflict_id=conflict_id, tenant_id=tenant_id, project_id=project_id, fact_id=fact_id, left_revision_id=payload.left_revision_id, right_revision_id=payload.right_revision_id, conflict_type=payload.conflict_type, description=payload.description, status="open", detected_at=detected_at)

    @staticmethod
    def _conflict_data(row: Mapping[str, Any]) -> FactConflictData:
        return FactConflictData(
            conflict_id=row["id"], tenant_id=row["tenant_id"], project_id=row["project_id"],
            fact_id=row["fact_atom_id"], left_revision_id=row["left_revision_id"],
            right_revision_id=row["right_revision_id"], conflict_type=row["conflict_type"],
            description=row["description"], status=row["status"], detected_at=_as_utc(row["detected_at"]),
            resolved_by=row["resolved_by"], resolved_at=_optional_utc(row["resolved_at"]),
            resolution_note=row["resolution_note"],
        )

    def list_conflicts(self, tenant_id: str, project_id: str, status: Optional[str] = None) -> list[FactConflictData]:
        condition = "AND status=:status" if status else ""
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            rows = conn.execute(text(f"""
                SELECT * FROM airank_fact_conflicts
                WHERE tenant_id=:tenant_id AND project_id=:project_id {condition}
                ORDER BY (status='open') DESC, detected_at DESC, id DESC
            """), {"tenant_id": tenant_id, "project_id": project_id, "status": status}).mappings().all()
        return [self._conflict_data(row) for row in rows]

    def resolve_conflict(self, tenant_id: str, project_id: str, conflict_id: str, payload: FactConflictResolveRequest) -> FactConflictData:
        resolved_at = utc_now()
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM airank_fact_conflicts WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:conflict_id FOR UPDATE"), {"tenant_id": tenant_id, "project_id": project_id, "conflict_id": conflict_id}).mappings().first()
            if row is None:
                raise _not_found("FACT_CONFLICT_NOT_FOUND", {"conflict_id": conflict_id})
            if row["status"] != "open":
                raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"conflict_id": conflict_id, "status": row["status"]}})
            conn.execute(text("UPDATE airank_fact_conflicts SET status=:status, resolved_by=:resolved_by, resolved_at=:resolved_at, resolution_note=:resolution_note WHERE tenant_id=:tenant_id AND id=:conflict_id"), {"status": payload.resolution, "resolved_by": payload.resolved_by, "resolved_at": resolved_at, "resolution_note": payload.resolution_note, "tenant_id": tenant_id, "conflict_id": conflict_id})
        return FactConflictData(conflict_id=conflict_id, tenant_id=tenant_id, project_id=project_id, fact_id=row["fact_atom_id"], left_revision_id=row["left_revision_id"], right_revision_id=row["right_revision_id"], conflict_type=row["conflict_type"], description=row["description"], status=payload.resolution, detected_at=_as_utc(row["detected_at"]), resolved_by=payload.resolved_by, resolved_at=resolved_at, resolution_note=payload.resolution_note)

    def create_governed_content(self, tenant_id: str, project_id: str, payload: GovernedContentCreateRequest) -> GovernedContentData:
        created_at = utc_now()
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            revision_query = text("""
                SELECT f.id AS fact_id, f.current_revision_id, f.title, f.fact_type,
                       f.disclosure, f.risk_level, r.id AS revision_id, r.fact_text,
                       r.status, r.source_ids_json, r.valid_from, r.valid_until, r.reviewed_by,
                       (SELECT COUNT(*) FROM airank_fact_conflicts c
                        WHERE c.tenant_id=f.tenant_id AND c.fact_atom_id=f.id AND c.status='open') AS open_conflict_count
                FROM airank_fact_revisions r JOIN airank_fact_atoms f ON f.id=r.fact_atom_id
                WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id
                  AND r.id IN :revision_ids
            """).bindparams(bindparam("revision_ids", expanding=True))
            rows = conn.execute(revision_query, {"tenant_id": tenant_id, "project_id": project_id, "revision_ids": payload.fact_revision_ids}).mappings().all()
            by_id = {row["revision_id"]: row for row in rows}
            if len(by_id) != len(payload.fact_revision_ids):
                missing = [item for item in payload.fact_revision_ids if item not in by_id]
                raise _not_found("FACT_REVISION_NOT_FOUND", {"revision_ids": missing})
            support_rows: list[dict[str, Any]] = []
            ordered_rows = [by_id[item] for item in payload.fact_revision_ids]
            for row in ordered_rows:
                valid_until = row["valid_until"]
                if valid_until is not None and valid_until.tzinfo is None:
                    valid_until = valid_until.replace(tzinfo=timezone.utc)
                invalid_reason = None
                if row["status"] != "approved" or row["current_revision_id"] != row["revision_id"]:
                    invalid_reason = "revision_not_current_approved"
                elif int(row["open_conflict_count"]):
                    invalid_reason = "open_conflict"
                elif row.get("valid_from") is not None and _as_utc(row["valid_from"]) > created_at:
                    invalid_reason = "fact_not_yet_valid"
                elif valid_until is not None and valid_until <= created_at:
                    invalid_reason = "fact_expired"
                elif row["disclosure"] not in {"public", "redacted"}:
                    invalid_reason = "disclosure_not_publishable"
                if invalid_reason:
                    raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_EVIDENCE_MISSING", "details": {"revision_id": row["revision_id"], "reason": invalid_reason}})
                source_ids = row["source_ids_json"] if isinstance(row["source_ids_json"], list) else json.loads(row["source_ids_json"] or "[]")
                exact_support = None
                for source_id in source_ids:
                    source = conn.execute(text("""
                        SELECT s.id, s.content_sha256, c.content_text
                        FROM airank_knowledge_sources s
                        JOIN airank_knowledge_source_contents c ON c.knowledge_source_id=s.id
                        WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                          AND s.id=:source_id AND s.status='active'
                          AND (s.valid_from IS NULL OR s.valid_from<=:now)
                          AND (s.valid_until IS NULL OR s.valid_until>:now)
                    """), {"tenant_id": tenant_id, "project_id": project_id, "source_id": source_id, "now": created_at}).mappings().first()
                    if source is None:
                        continue
                    if sha256_text(source["content_text"]) != source["content_sha256"]:
                        raise StarletteHTTPException(
                            status_code=409,
                            detail={
                                "code": "CONTENT_EVIDENCE_MISSING",
                                "details": {
                                    "revision_id": row["revision_id"],
                                    "reason": "source_content_integrity_failed",
                                    "source_id": source_id,
                                },
                            },
                        )
                    start = source["content_text"].find(row["fact_text"])
                    if start >= 0:
                        exact_support = {
                            "revision": row,
                            "source_id": source_id,
                            "source_sha256": source["content_sha256"],
                            "start": start,
                            "end": start + len(row["fact_text"]),
                        }
                        break
                if exact_support is None:
                    raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_EVIDENCE_MISSING", "details": {"revision_id": row["revision_id"], "reason": "exact_source_boundary_missing"}})
                support_rows.append(exact_support)
            asset_id = f"asset_{uuid4().hex[:12]}"
            assertion_ids = [f"claim_{uuid4().hex[:12]}" for _ in support_rows]
            support_ids = [f"support_{uuid4().hex[:12]}" for _ in support_rows]
            blueprint = _page_blueprint_or_error(
                payload,
                [
                    {
                        "fact_id": item["revision"]["fact_id"],
                        "revision_id": item["revision"]["revision_id"],
                        "title": item["revision"]["title"],
                        "fact_text": item["revision"]["fact_text"],
                        "status": item["revision"]["status"],
                        "eligible_for_generation": True,
                        "valid_until": (
                            _as_utc(item["revision"]["valid_until"]).isoformat()
                            if item["revision"]["valid_until"] is not None
                            else None
                        ),
                        "conflict_status": "none",
                        "support_ids": [support_id],
                        "evidence": [
                            {
                                "source_id": item["source_id"],
                                "source_sha256": item["source_sha256"],
                                "source_start": item["start"],
                                "source_end": item["end"],
                                "quoted_text": item["revision"]["fact_text"],
                            }
                        ],
                    }
                    for item, support_id in zip(support_rows, support_ids)
                ],
            )
            body_md = blueprint["body_md"]
            asset_metadata = {
                "generation_mode": "evidence_bound_page_blueprint",
                "fact_revision_ids": payload.fact_revision_ids,
                "created_by": payload.created_by,
                "skill_id": blueprint["skill_id"],
                "skill_version": blueprint["skill_version"],
                "blueprint_sha256": blueprint["blueprint_sha256"],
                "sections": blueprint["sections"],
                "claim_bindings": blueprint["claim_bindings"],
                "structured_data": blueprint["structured_data"],
                "editorial_brief_sha256": blueprint["editorial_brief_sha256"],
            }
            conn.execute(text("""
                INSERT INTO airank_content_assets (
                  id, tenant_id, project_id, asset_type, title, body_md, content_sha256,
                  status, fact_atom_ids, metadata_json, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :asset_type, :title, :body_md, :content_sha256,
                  'draft', :fact_atom_ids, :metadata_json, :created_at, :created_at
                )
            """), {"id": asset_id, "tenant_id": tenant_id, "project_id": project_id, "asset_type": payload.asset_type, "title": blueprint["title"], "body_md": body_md, "content_sha256": sha256_text(body_md), "fact_atom_ids": json.dumps([row["fact_id"] for row in ordered_rows], ensure_ascii=False), "metadata_json": json.dumps(asset_metadata, ensure_ascii=False), "created_at": created_at})
            for item, assertion_id, support_id in zip(
                support_rows, assertion_ids, support_ids
            ):
                row = item["revision"]
                conn.execute(text("""
                    INSERT INTO airank_claim_assertions (
                      id, tenant_id, project_id, asset_id, claim_text, claim_sha256,
                      status, verified_by, verified_at, metadata_json, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :asset_id, :claim_text, :claim_sha256,
                      'verified', :verified_by, :verified_at, :metadata_json, :created_at, :created_at
                    )
                """), {"id": assertion_id, "tenant_id": tenant_id, "project_id": project_id, "asset_id": asset_id, "claim_text": row["fact_text"], "claim_sha256": sha256_text(row["fact_text"]), "verified_by": row["reviewed_by"] or payload.created_by, "verified_at": created_at, "metadata_json": json.dumps({"fact_revision_id": row["revision_id"], "generation_mode": "evidence_bound_page_blueprint", "blueprint_sha256": blueprint["blueprint_sha256"]}, ensure_ascii=False), "created_at": created_at})
                conn.execute(text("""
                    INSERT INTO airank_claim_supports (
                      id, tenant_id, project_id, assertion_id, fact_revision_id,
                      knowledge_source_id, support_type, quoted_text, source_start,
                      source_end, support_score, reviewed_by, reviewed_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :assertion_id, :fact_revision_id,
                      :knowledge_source_id, 'supports', :quoted_text, :source_start,
                      :source_end, 1.0, :reviewed_by, :reviewed_at, :created_at
                    )
                """), {"id": support_id, "tenant_id": tenant_id, "project_id": project_id, "assertion_id": assertion_id, "fact_revision_id": row["revision_id"], "knowledge_source_id": item["source_id"], "quoted_text": row["fact_text"], "source_start": item["start"], "source_end": item["end"], "reviewed_by": row["reviewed_by"] or payload.created_by, "reviewed_at": created_at, "created_at": created_at})
        return GovernedContentData(
            asset_id=asset_id,
            tenant_id=tenant_id,
            project_id=project_id,
            asset_type=payload.asset_type,
            title=blueprint["title"],
            body_md=body_md,
            status="draft",
            generation_mode="evidence_bound_page_blueprint",
            skill_id=blueprint["skill_id"],
            skill_version=blueprint["skill_version"],
            blueprint_sha256=blueprint["blueprint_sha256"],
            section_count=len(blueprint["sections"]),
            fact_revision_ids=payload.fact_revision_ids,
            claim_assertion_ids=assertion_ids,
            claim_support_ids=support_ids,
            created_at=created_at,
        )

    def list_governed_content(self, tenant_id: str, project_id: str) -> list[GovernedContentData]:
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            rows = conn.execute(text("""
                SELECT id, tenant_id, project_id, asset_type, title, body_md, status,
                       metadata_json, created_at
                FROM airank_content_assets
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND deleted_at IS NULL
                ORDER BY created_at DESC, id DESC
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
            assets: list[GovernedContentData] = []
            for row in rows:
                metadata = row["metadata_json"] if isinstance(row["metadata_json"], Mapping) else json.loads(row["metadata_json"] or "{}")
                assertions = conn.execute(text("""
                    SELECT id FROM airank_claim_assertions
                    WHERE tenant_id=:tenant_id AND asset_id=:asset_id
                    ORDER BY created_at ASC, id ASC
                """), {"tenant_id": tenant_id, "asset_id": row["id"]}).scalars().all()
                supports = []
                if assertions:
                    supports = conn.execute(
                        text("""
                            SELECT id FROM airank_claim_supports
                            WHERE tenant_id=:tenant_id AND assertion_id IN :assertion_ids
                            ORDER BY created_at ASC, id ASC
                        """).bindparams(bindparam("assertion_ids", expanding=True)),
                        {"tenant_id": tenant_id, "assertion_ids": list(assertions)},
                    ).scalars().all()
                assets.append(GovernedContentData(
                    asset_id=row["id"], tenant_id=row["tenant_id"], project_id=row["project_id"],
                    asset_type=row["asset_type"], title=row["title"], body_md=row["body_md"] or "",
                    status=row["status"],
                    generation_mode=metadata.get("generation_mode") or "approved_fact_template",
                    skill_id=metadata.get("skill_id"),
                    skill_version=metadata.get("skill_version"),
                    blueprint_sha256=metadata.get("blueprint_sha256"),
                    section_count=len(metadata.get("sections") or []),
                    fact_revision_ids=list(metadata.get("fact_revision_ids") or []),
                    claim_assertion_ids=list(assertions), claim_support_ids=list(supports),
                    created_at=row["created_at"],
                ))
        return assets


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _optional_utc(value: Optional[datetime]) -> Optional[datetime]:
    return _as_utc(value) if value is not None else None


def _lexical_terms(query: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", query.strip().lower())
    terms: list[str] = [normalized]
    for token in re.findall(r"[a-z0-9][a-z0-9._+-]*|[\u3400-\u9fff]+", normalized):
        terms.append(token)
        if re.fullmatch(r"[\u3400-\u9fff]+", token) and len(token) > 2:
            terms.extend(token[index : index + 2] for index in range(len(token) - 1))
    return list(dict.fromkeys(term for term in terms if term))[:32]


def _lexical_match(query: str, text_value: str) -> Optional[tuple[Literal["exact", "terms"], list[str], int]]:
    normalized_query = re.sub(r"\s+", " ", query.strip().lower())
    normalized_text = text_value.lower()
    terms = _lexical_terms(query)
    matched_terms = [term for term in terms if term in normalized_text]
    if not matched_terms:
        return None
    exact = normalized_query in normalized_text
    first_match = normalized_text.find(normalized_query) if exact else min(normalized_text.find(term) for term in matched_terms)
    return ("exact" if exact else "terms", matched_terms, first_match)


def _knowledge_search_data(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    limit: int,
    candidate_limit_reached: bool,
) -> KnowledgeSearchData:
    def row_values(candidate: dict[str, Any]) -> tuple[Any, Any]:
        if "row" in candidate:
            return candidate["row"], None
        return candidate["segment"], candidate["source"]

    def sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
        record, source = row_values(candidate)
        revision_number = int(record["revision_number"]) if source is None else source.revision_number
        segment_index = int(record["segment_index"]) if source is None else record.segment_index
        segment_id = str(record["segment_id"]) if source is None else record.id
        return (
            0 if candidate["match_type"] == "exact" else 1,
            -len(candidate["matched_terms"]),
            candidate["first_match"],
            -revision_number,
            segment_index,
            segment_id,
        )

    ordered = sorted(candidates, key=sort_key)
    results: list[KnowledgeSearchResultData] = []
    for rank, candidate in enumerate(ordered[:limit], start=1):
        record, source = row_values(candidate)
        if source is None:
            result = KnowledgeSearchResultData(
                rank=rank,
                segment_id=record["segment_id"],
                source_id=record["knowledge_source_id"],
                source_revision_number=int(record["revision_number"]),
                source_title=record["title"],
                source_uri=record["source_uri"],
                segment_index=int(record["segment_index"]),
                text=record["segment_text"],
                source_start=int(record["source_start"]),
                source_end=int(record["source_end"]),
                content_sha256=record["content_sha256"],
                match_type=candidate["match_type"],
                matched_terms=candidate["matched_terms"],
            )
        else:
            result = KnowledgeSearchResultData(
                rank=rank,
                segment_id=record.id,
                source_id=source.source_id,
                source_revision_number=source.revision_number,
                source_title=source.title,
                source_uri=source.source_uri,
                segment_index=record.segment_index,
                text=record.text,
                source_start=record.source_start,
                source_end=record.source_end,
                content_sha256=record.content_sha256,
                match_type=candidate["match_type"],
                matched_terms=candidate["matched_terms"],
            )
        results.append(result)
    return KnowledgeSearchData(
        query=query.strip(),
        matched_count=len(ordered),
        returned_count=len(results),
        candidate_limit_reached=candidate_limit_reached,
        results=results,
    )


def derive_knowledge_governance(
    sources: list[KnowledgeSourceData],
    facts: list[FactRevisionData],
    conflicts: list[FactConflictData],
    *,
    within_days: int,
    as_of: Optional[datetime] = None,
) -> KnowledgeGovernanceData:
    evaluated_at = _as_utc(as_of or utc_now())
    window_seconds = within_days * 24 * 60 * 60
    alerts: list[KnowledgeGovernanceAlertData] = []

    def add_expiry_alert(
        *,
        entity_type: Literal["knowledge_source", "fact_revision"],
        entity_id: str,
        title: str,
        due_at: datetime,
    ) -> None:
        due = _as_utc(due_at)
        remaining_seconds = (due - evaluated_at).total_seconds()
        if remaining_seconds > window_seconds:
            return
        expired = remaining_seconds <= 0
        entity_label = "知识来源" if entity_type == "knowledge_source" else "事实修订"
        kind = f"{'source' if entity_type == 'knowledge_source' else 'fact'}_{'expired' if expired else 'expiring'}"
        days_remaining = ceil(remaining_seconds / (24 * 60 * 60))
        alerts.append(KnowledgeGovernanceAlertData(
            alert_id=f"{kind}:{entity_id}",
            kind=kind,
            severity="critical" if expired else "warning",
            entity_type=entity_type,
            entity_id=entity_id,
            title=title,
            message=f"{entity_label}已过期，必须更新证据后再用于内容生成。" if expired else f"{entity_label}将在 {days_remaining} 天内到期，请安排复核。",
            due_at=due,
            days_remaining=days_remaining,
        ))

    for source in sources:
        if source.status == "stale":
            alerts.append(KnowledgeGovernanceAlertData(
                alert_id=f"source_stale:{source.source_id}",
                kind="source_stale",
                severity="critical",
                entity_type="knowledge_source",
                entity_id=source.source_id,
                title=source.title,
                message="知识来源已有新版本，引用旧来源的事实必须重新核验。",
            ))
        elif source.status == "active" and source.valid_until is not None:
            add_expiry_alert(
                entity_type="knowledge_source",
                entity_id=source.source_id,
                title=source.title,
                due_at=source.valid_until,
            )
    for fact in facts:
        if fact.status == "approved" and fact.valid_until is not None:
            add_expiry_alert(
                entity_type="fact_revision",
                entity_id=fact.revision_id,
                title=fact.title,
                due_at=fact.valid_until,
            )
    open_conflicts = [conflict for conflict in conflicts if conflict.status == "open"]
    for conflict in open_conflicts:
        alerts.append(KnowledgeGovernanceAlertData(
            alert_id=f"open_conflict:{conflict.conflict_id}",
            kind="open_conflict",
            severity="critical",
            entity_type="fact_conflict",
            entity_id=conflict.conflict_id,
            title=conflict.description,
            message="事实冲突尚未由人工裁决，关联事实不得用于内容生成。",
        ))

    severity_order = {"critical": 0, "warning": 1}
    alerts.sort(key=lambda alert: (severity_order[alert.severity], alert.due_at or evaluated_at, alert.alert_id))
    kinds = [alert.kind for alert in alerts]
    return KnowledgeGovernanceData(
        status="attention_required" if alerts else "healthy",
        as_of=evaluated_at,
        within_days=within_days,
        source_count=len(sources),
        approved_fact_count=sum(fact.status == "approved" for fact in facts),
        stale_source_count=kinds.count("source_stale"),
        expired_source_count=kinds.count("source_expired"),
        expiring_source_count=kinds.count("source_expiring"),
        expired_fact_count=kinds.count("fact_expired"),
        expiring_fact_count=kinds.count("fact_expiring"),
        open_conflict_count=len(open_conflicts),
        action_required_count=len(alerts),
        alerts=alerts,
    )


def _not_found(code: str, details: dict[str, Any]) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=404, detail={"code": code, "details": details})


def build_repository() -> KnowledgeRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLKnowledgeRepository(database_url) if database_url else InMemoryKnowledgeRepository()


KNOWLEDGE_REPOSITORY: KnowledgeRepository = build_repository()


@router.post("/projects/{project_id}/knowledge-sources", response_model=KnowledgeSourceResponse, status_code=201)
def create_knowledge_source(project_id: str, payload: KnowledgeSourceCreateRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> KnowledgeSourceResponse:
    return KnowledgeSourceResponse(data=KNOWLEDGE_REPOSITORY.create_source(tenant_id, project_id, payload), meta=response_meta(trace_id))


@router.get("/projects/{project_id}/knowledge-sources", response_model=KnowledgeSourceListResponse)
def list_knowledge_sources(project_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> KnowledgeSourceListResponse:
    return KnowledgeSourceListResponse(data=KNOWLEDGE_REPOSITORY.list_sources(tenant_id, project_id), meta=response_meta(trace_id))


@router.post("/projects/{project_id}/knowledge-sources/{source_id}/revisions", response_model=KnowledgeSourceResponse, status_code=201)
def revise_knowledge_source(project_id: str, source_id: str, payload: KnowledgeSourceCreateRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> KnowledgeSourceResponse:
    return KnowledgeSourceResponse(
        data=KNOWLEDGE_REPOSITORY.revise_source(tenant_id, project_id, source_id, payload),
        meta=response_meta(trace_id),
    )


@router.get("/projects/{project_id}/knowledge-search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    project_id: str,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> KnowledgeSearchResponse:
    return KnowledgeSearchResponse(
        data=KNOWLEDGE_REPOSITORY.search_segments(tenant_id, project_id, q, limit),
        meta=response_meta(trace_id),
    )


@router.post("/projects/{project_id}/facts", response_model=FactRevisionResponse, status_code=201)
def propose_fact(project_id: str, payload: FactProposalRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> FactRevisionResponse:
    trusted_payload = payload.model_copy(update={"created_by": trusted_review_actor(payload.created_by, authenticated_actor)})
    return FactRevisionResponse(data=KNOWLEDGE_REPOSITORY.propose_fact(tenant_id, project_id, trusted_payload), meta=response_meta(trace_id))


@router.get("/projects/{project_id}/facts", response_model=FactRevisionListResponse)
def list_facts(project_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> FactRevisionListResponse:
    return FactRevisionListResponse(data=KNOWLEDGE_REPOSITORY.list_facts(tenant_id, project_id), meta=response_meta(trace_id))


@router.post("/projects/{project_id}/facts/{fact_id}/revisions", response_model=FactRevisionResponse, status_code=201)
def revise_fact(project_id: str, fact_id: str, payload: FactProposalRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> FactRevisionResponse:
    trusted_payload = payload.model_copy(update={"created_by": trusted_review_actor(payload.created_by, authenticated_actor)})
    return FactRevisionResponse(data=KNOWLEDGE_REPOSITORY.revise_fact(tenant_id, project_id, fact_id, trusted_payload), meta=response_meta(trace_id))


@router.patch("/projects/{project_id}/fact-revisions/{revision_id}/review", response_model=FactRevisionResponse)
def review_fact_revision(project_id: str, revision_id: str, payload: FactRevisionReviewRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> FactRevisionResponse:
    trusted_payload = payload.model_copy(
        update={"reviewed_by": trusted_review_actor(payload.reviewed_by, authenticated_actor)}
    )
    return FactRevisionResponse(data=KNOWLEDGE_REPOSITORY.review_revision(tenant_id, project_id, revision_id, trusted_payload), meta=response_meta(trace_id))


@router.post("/projects/{project_id}/facts/{fact_id}/conflicts", response_model=FactConflictResponse, status_code=201)
def create_fact_conflict(project_id: str, fact_id: str, payload: FactConflictCreateRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> FactConflictResponse:
    return FactConflictResponse(data=KNOWLEDGE_REPOSITORY.create_conflict(tenant_id, project_id, fact_id, payload), meta=response_meta(trace_id))


@router.get("/projects/{project_id}/fact-conflicts", response_model=FactConflictListResponse)
def list_fact_conflicts(
    project_id: str,
    status: Optional[Literal["open", "resolved_left", "resolved_right", "resolved_new_revision", "dismissed"]] = Query(default=None),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> FactConflictListResponse:
    return FactConflictListResponse(
        data=KNOWLEDGE_REPOSITORY.list_conflicts(tenant_id, project_id, status),
        meta=response_meta(trace_id),
    )


@router.get("/projects/{project_id}/knowledge-governance", response_model=KnowledgeGovernanceResponse)
def get_knowledge_governance(
    project_id: str,
    within_days: int = Query(default=30, ge=1, le=365),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> KnowledgeGovernanceResponse:
    sources = KNOWLEDGE_REPOSITORY.list_sources(tenant_id, project_id)
    facts = KNOWLEDGE_REPOSITORY.list_facts(tenant_id, project_id)
    conflicts = KNOWLEDGE_REPOSITORY.list_conflicts(tenant_id, project_id, "open")
    return KnowledgeGovernanceResponse(
        data=derive_knowledge_governance(
            sources,
            facts,
            conflicts,
            within_days=within_days,
        ),
        meta=response_meta(trace_id),
    )


@router.patch("/projects/{project_id}/fact-conflicts/{conflict_id}/resolve", response_model=FactConflictResponse)
def resolve_fact_conflict(project_id: str, conflict_id: str, payload: FactConflictResolveRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> FactConflictResponse:
    trusted_payload = payload.model_copy(update={"resolved_by": trusted_review_actor(payload.resolved_by, authenticated_actor)})
    return FactConflictResponse(data=KNOWLEDGE_REPOSITORY.resolve_conflict(tenant_id, project_id, conflict_id, trusted_payload), meta=response_meta(trace_id))


@router.post("/projects/{project_id}/content-assets", response_model=GovernedContentResponse, status_code=201)
def create_governed_content(project_id: str, payload: GovernedContentCreateRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> GovernedContentResponse:
    trusted_payload = payload.model_copy(update={"created_by": trusted_review_actor(payload.created_by, authenticated_actor)})
    return GovernedContentResponse(data=KNOWLEDGE_REPOSITORY.create_governed_content(tenant_id, project_id, trusted_payload), meta=response_meta(trace_id))


@router.get("/projects/{project_id}/content-assets", response_model=GovernedContentListResponse)
def list_governed_content(project_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> GovernedContentListResponse:
    return GovernedContentListResponse(data=KNOWLEDGE_REPOSITORY.list_governed_content(tenant_id, project_id), meta=response_meta(trace_id))

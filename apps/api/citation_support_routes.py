from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from threading import RLock
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain.measurement import sha256_text
from airank_evidence import (
    AnswerClaimKind,
    CitationClaim,
    CitationSupportEvidenceGrade,
    CitationSupportLabel,
    CitationSupportReview,
    FactAccuracyClaim,
    FactAccuracyEvidenceGrade,
    FactAccuracyReview,
    FactAccuracyVerdict,
    calculate_citation_support_metrics,
    calculate_fact_accuracy_metrics,
)


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["citation-support"])
PENDING_INDEPENDENT_REVIEW_STATUSES = frozenset(
    {"creating", "awaiting_secondary", "disputed"}
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested: str, authenticated: Optional[str]) -> str:
    if authenticated:
        return authenticated.strip()
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested.strip()
    raise StarletteHTTPException(
        status_code=401, detail={"code": "AUTH_TOKEN_INVALID"}
    )


def review_visible_to_actor(
    *,
    review_case_id: Optional[str],
    review_case_status: str,
    reviewed_by: str,
    actor_id: Optional[str],
) -> bool:
    """Keep peer labels blind until the independent review case is final."""
    if not review_case_id or review_case_status not in PENDING_INDEPENDENT_REVIEW_STATUSES:
        return True
    return bool(actor_id and reviewed_by == actor_id)


class CitationClaimCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_start: int = Field(ge=0)
    answer_end: int = Field(gt=0)
    extraction_method: Literal["manual", "ai_assisted"] = "manual"
    extractor_version: str = Field(default="airank.citation-claim.manual.v1", min_length=1, max_length=64)
    claim_kind: Literal[
        "unclassified",
        "brand_fact",
        "competitor_fact",
        "general_fact",
        "opinion",
    ] = "unclassified"
    subject_entity_text: Optional[str] = Field(default=None, min_length=1, max_length=512)
    created_by: str = Field(min_length=1, max_length=64)


class CitationSupportReviewCreateRequest(BaseModel):
    citation_id: str = Field(min_length=1, max_length=64)
    support_label: Literal["supports", "contradicts", "insufficient"]
    evidence_grade: Literal[
        "provider_excerpt_only",
        "source_panel_capture",
        "source_page_snapshot",
    ]
    source_excerpt: str = Field(min_length=1, max_length=20_000)
    source_content_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    source_object_ref_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    source_capture_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    source_segment_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    source_start: Optional[int] = Field(default=None, ge=0)
    source_end: Optional[int] = Field(default=None, gt=0)
    rationale: str = Field(min_length=1, max_length=4_000)
    review_method: Literal["human", "ai_assisted"] = "human"
    reviewed_by: str = Field(min_length=1, max_length=64)


def exact_source_excerpt(
    payload: CitationSupportReviewCreateRequest, segment: Mapping[str, Any]
) -> bool:
    if payload.source_start is None or payload.source_end is None:
        return False
    segment_start = int(segment["source_start"])
    segment_end = int(segment["source_end"])
    if not (
        segment_start <= payload.source_start < payload.source_end <= segment_end
    ):
        return False
    relative_start = payload.source_start - segment_start
    relative_end = payload.source_end - segment_start
    return str(segment["segment_text"])[relative_start:relative_end] == payload.source_excerpt


class CitationClaimData(BaseModel):
    claim_id: str
    snapshot_id: str
    claim_text: str
    answer_start: int
    answer_end: int
    answer_sha256: str
    claim_sha256: str
    extraction_method: str
    extractor_version: str
    claim_kind: str
    subject_entity_text: Optional[str]
    created_by: str
    created_at: datetime


class FactAccuracyReviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["accurate", "inaccurate", "outdated", "insufficient_evidence"]
    fact_revision_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=4_000)
    review_method: Literal["human", "ai_assisted"] = "human"
    reviewed_by: str = Field(min_length=1, max_length=64)


class FactAccuracyReviewData(BaseModel):
    review_id: str
    claim_id: str
    verdict: str
    evidence_grade: str
    fact_revision_id: Optional[str]
    knowledge_source_id: Optional[str]
    knowledge_segment_id: Optional[str]
    fact_revision_sha256: Optional[str]
    source_content_sha256: Optional[str]
    quoted_text: Optional[str]
    quoted_text_sha256: Optional[str]
    source_start: Optional[int]
    source_end: Optional[int]
    rationale: str
    review_method: str
    reviewed_by: str
    reviewed_at: datetime
    supersedes_review_id: Optional[str]
    review_case_id: Optional[str] = None
    reviewer_role: str = "single"
    review_case_status: str = "single_review"
    review_case_purpose: str = "single_review"
    evidence_verified: bool = False
    commercially_verified: bool
    idempotent_replay: bool = False


class FactAccuracyMetricsData(BaseModel):
    registered_claim_count: int
    factual_claim_count: int
    reviewed_claim_count: int
    commercially_verified_claim_count: int
    decisive_claim_count: int
    accurate_count: int
    inaccurate_count: int
    outdated_count: int
    insufficient_evidence_count: int
    evaluation_coverage_rate: Optional[float]
    fact_accuracy: Optional[float]
    known_limitations: list[str]


class FactAccuracyBundleData(BaseModel):
    snapshot_id: str
    claims: list[CitationClaimData]
    reviews: list[FactAccuracyReviewData]
    metrics: FactAccuracyMetricsData


class FactAccuracyBundleResponse(BaseModel):
    data: FactAccuracyBundleData
    meta: dict[str, str]


class FactAccuracyReviewResponse(BaseModel):
    data: FactAccuracyReviewData
    meta: dict[str, str]


class CitationSupportReviewData(BaseModel):
    review_id: str
    claim_id: str
    citation_id: str
    support_label: str
    evidence_grade: str
    source_excerpt: str
    source_content_sha256: str
    source_object_ref_id: Optional[str]
    source_capture_id: Optional[str]
    source_segment_id: Optional[str]
    source_start: Optional[int]
    source_end: Optional[int]
    rationale: str
    review_method: str
    reviewed_by: str
    reviewed_at: datetime
    supersedes_review_id: Optional[str]
    review_case_id: Optional[str] = None
    reviewer_role: str = "single"
    review_case_status: str = "single_review"
    review_case_purpose: str = "single_review"
    evidence_verified: bool = False
    commercially_verified: bool


class CitationSupportMetricsData(BaseModel):
    selected_citation_count: int
    claim_count: int
    review_count: int
    commercially_verified_review_count: int
    supports_count: int
    contradicts_count: int
    insufficient_count: int
    citation_support_rate: Optional[float]
    known_limitations: list[str]


class CitationSupportBundleData(BaseModel):
    snapshot_id: str
    claims: list[CitationClaimData]
    reviews: list[CitationSupportReviewData]
    metrics: CitationSupportMetricsData


class CitationClaimResponse(BaseModel):
    data: CitationClaimData
    meta: dict[str, str]


class CitationSupportReviewResponse(BaseModel):
    data: CitationSupportReviewData
    meta: dict[str, str]


class CitationSupportBundleResponse(BaseModel):
    data: CitationSupportBundleData
    meta: dict[str, str]


class CitationSupportRepository(Protocol):
    def create_claim(
        self, tenant_id: str, snapshot_id: str, payload: CitationClaimCreateRequest
    ) -> CitationClaimData: ...
    def create_review(
        self, tenant_id: str, claim_id: str, payload: CitationSupportReviewCreateRequest
    ) -> CitationSupportReviewData: ...
    def get_bundle(
        self, tenant_id: str, snapshot_id: str, actor_id: Optional[str] = None
    ) -> CitationSupportBundleData: ...
    def create_fact_accuracy_review(
        self,
        tenant_id: str,
        claim_id: str,
        payload: FactAccuracyReviewCreateRequest,
        idempotency_key: str,
        trace_id: str,
    ) -> FactAccuracyReviewData: ...
    def get_fact_accuracy_bundle(
        self, tenant_id: str, snapshot_id: str, actor_id: Optional[str] = None
    ) -> FactAccuracyBundleData: ...


class InMemoryCitationSupportRepository:
    def __init__(self) -> None:
        self.lock = RLock()
        self.samples: dict[tuple[str, str], dict[str, str]] = {}
        self.citations: dict[str, dict[str, str]] = {}
        self.objects: dict[str, dict[str, str]] = {}
        self.captures: dict[str, dict[str, str]] = {}
        self.segments: dict[str, dict[str, Any]] = {}
        self.claims: dict[str, CitationClaimData] = {}
        self.reviews: list[CitationSupportReviewData] = []
        self.fact_accuracy_reviews: list[FactAccuracyReviewData] = []
        self.fact_accuracy_idempotency: dict[tuple[str, str], FactAccuracyReviewData] = {}
        self.approved_facts: dict[str, dict[str, Any]] = {}

    def seed_sample(
        self,
        *,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
        answer_text: str,
        citation_id: str,
        cited_text: str,
    ) -> None:
        self.samples[(tenant_id, snapshot_id)] = {
            "project_id": project_id,
            "answer_text": answer_text,
        }
        self.citations[citation_id] = {
            "tenant_id": tenant_id,
            "snapshot_id": snapshot_id,
            "cited_text": cited_text,
        }

    def seed_source_object(
        self,
        *,
        tenant_id: str,
        project_id: str,
        object_ref_id: str,
        sha256: str,
        kind: str,
        citation_id: str,
    ) -> None:
        self.objects[object_ref_id] = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "sha256": sha256,
            "kind": kind,
            "citation_id": citation_id,
        }

    def seed_source_capture(
        self,
        *,
        tenant_id: str,
        project_id: str,
        capture_id: str,
        citation_id: str,
        raw_object_ref_id: str,
        content_sha256: str,
        segment_id: str,
        segment_text: str,
        segment_start: int = 0,
    ) -> None:
        self.captures[capture_id] = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "citation_id": citation_id,
            "raw_object_ref_id": raw_object_ref_id,
            "content_sha256": content_sha256,
            "status": "completed",
        }
        self.segments[segment_id] = {
            "capture_id": capture_id,
            "source_start": segment_start,
            "source_end": segment_start + len(segment_text),
            "segment_text": segment_text,
        }

    def seed_approved_fact(
        self,
        *,
        tenant_id: str,
        project_id: str,
        fact_revision_id: str,
        fact_text: str,
        knowledge_source_id: str,
        knowledge_segment_id: str,
        source_content: str,
        current: bool = True,
        source_current: bool = True,
        open_conflict_count: int = 0,
    ) -> None:
        start = source_content.find(fact_text)
        if start < 0:
            raise ValueError("seed fact text must exist in source content")
        self.approved_facts[fact_revision_id] = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "fact_revision_id": fact_revision_id,
            "fact_text": fact_text,
            "fact_revision_sha256": sha256_text(fact_text),
            "knowledge_source_id": knowledge_source_id,
            "knowledge_segment_id": knowledge_segment_id,
            "source_content": source_content,
            "source_content_sha256": sha256_text(source_content),
            "source_start": start,
            "source_end": start + len(fact_text),
            "current": current,
            "source_current": source_current,
            "open_conflict_count": open_conflict_count,
        }

    def create_claim(
        self, tenant_id: str, snapshot_id: str, payload: CitationClaimCreateRequest
    ) -> CitationClaimData:
        with self.lock:
            sample = self.samples.get((tenant_id, snapshot_id))
            if sample is None:
                raise StarletteHTTPException(404, detail={"code": "OBJECT_REF_NOT_FOUND"})
            claim = CitationClaim.from_answer(
                id=f"citation_claim_{uuid4().hex}",
                tenant_id=tenant_id,
                project_id=sample["project_id"],
                snapshot_id=snapshot_id,
                answer_text=sample["answer_text"],
                answer_start=payload.answer_start,
                answer_end=payload.answer_end,
                created_by=payload.created_by,
                created_at=now_utc(),
                claim_kind=AnswerClaimKind(payload.claim_kind),
                subject_entity_text=payload.subject_entity_text,
            )
            for current in self.claims.values():
                if (
                    current.snapshot_id == snapshot_id
                    and current.answer_start == claim.answer_start
                    and current.answer_end == claim.answer_end
                    and current.claim_sha256 == sha256_text(claim.claim_text)
                    and current.claim_kind == payload.claim_kind
                ):
                    return current
            data = CitationClaimData(
                claim_id=claim.id,
                snapshot_id=snapshot_id,
                claim_text=claim.claim_text,
                answer_start=claim.answer_start,
                answer_end=claim.answer_end,
                answer_sha256=claim.answer_sha256,
                claim_sha256=sha256_text(claim.claim_text),
                extraction_method=payload.extraction_method,
                extractor_version=payload.extractor_version,
                claim_kind=payload.claim_kind,
                subject_entity_text=payload.subject_entity_text,
                created_by=claim.created_by,
                created_at=claim.created_at,
            )
            self.claims[data.claim_id] = data
            return data

    def create_review(
        self, tenant_id: str, claim_id: str, payload: CitationSupportReviewCreateRequest
    ) -> CitationSupportReviewData:
        with self.lock:
            claim = self.claims.get(claim_id)
            citation = self.citations.get(payload.citation_id)
            if claim is None:
                raise StarletteHTTPException(404, detail={"code": "CITATION_CLAIM_NOT_FOUND"})
            if citation is None:
                raise StarletteHTTPException(404, detail={"code": "CITATION_NOT_FOUND"})
            if citation["tenant_id"] != tenant_id or citation["snapshot_id"] != claim.snapshot_id:
                raise StarletteHTTPException(404, detail={"code": "CITATION_NOT_FOUND"})
            sample = self.samples[(tenant_id, claim.snapshot_id)]
            self._validate_evidence(
                tenant_id,
                sample["project_id"],
                payload,
                citation["cited_text"],
            )
            previous = next(
                (
                    item
                    for item in reversed(self.reviews)
                    if item.claim_id == claim_id and item.citation_id == payload.citation_id
                ),
                None,
            )
            data = self._review_data(claim_id, payload, previous.review_id if previous else None)
            self.reviews.append(data)
            return data

    def get_bundle(
        self, tenant_id: str, snapshot_id: str, actor_id: Optional[str] = None
    ) -> CitationSupportBundleData:
        with self.lock:
            if (tenant_id, snapshot_id) not in self.samples:
                raise StarletteHTTPException(404, detail={"code": "OBJECT_REF_NOT_FOUND"})
            claims = [item for item in self.claims.values() if item.snapshot_id == snapshot_id]
            claim_ids = {item.claim_id for item in claims}
            reviews = [
                item
                for item in self.reviews
                if item.claim_id in claim_ids
                and review_visible_to_actor(
                    review_case_id=item.review_case_id,
                    review_case_status=item.review_case_status,
                    reviewed_by=item.reviewed_by,
                    actor_id=actor_id,
                )
            ]
            citation_ids = tuple(
                item_id
                for item_id, item in self.citations.items()
                if item["tenant_id"] == tenant_id and item["snapshot_id"] == snapshot_id
            )
            return build_bundle(snapshot_id, citation_ids, claims, reviews)

    def create_fact_accuracy_review(
        self,
        tenant_id: str,
        claim_id: str,
        payload: FactAccuracyReviewCreateRequest,
        idempotency_key: str,
        trace_id: str,
    ) -> FactAccuracyReviewData:
        del trace_id
        with self.lock:
            replay = self.fact_accuracy_idempotency.get((tenant_id, idempotency_key))
            if replay is not None:
                if replay.claim_id != claim_id:
                    raise StarletteHTTPException(
                        409, detail={"code": "IDEMPOTENCY_CONFLICT"}
                    )
                return replay.model_copy(update={"idempotent_replay": True})
            claim = self.claims.get(claim_id)
            if claim is None:
                raise StarletteHTTPException(
                    404, detail={"code": "CITATION_CLAIM_NOT_FOUND"}
                )
            sample = self.samples.get((tenant_id, claim.snapshot_id))
            if sample is None:
                raise StarletteHTTPException(
                    404, detail={"code": "CITATION_CLAIM_NOT_FOUND"}
                )
            if not AnswerClaimKind(claim.claim_kind).eligible_for_fact_accuracy:
                raise StarletteHTTPException(
                    409, detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": "claim_kind_not_factual"}}
                )
            previous = next(
                (
                    item
                    for item in reversed(self.fact_accuracy_reviews)
                    if item.claim_id == claim_id
                ),
                None,
            )
            data = self._build_in_memory_fact_accuracy_review(
                tenant_id,
                sample["project_id"],
                claim,
                payload,
                previous.review_id if previous else None,
            )
            self.fact_accuracy_reviews.append(data)
            self.fact_accuracy_idempotency[(tenant_id, idempotency_key)] = data
            return data

    def get_fact_accuracy_bundle(
        self, tenant_id: str, snapshot_id: str, actor_id: Optional[str] = None
    ) -> FactAccuracyBundleData:
        with self.lock:
            if (tenant_id, snapshot_id) not in self.samples:
                raise StarletteHTTPException(404, detail={"code": "OBJECT_REF_NOT_FOUND"})
            claims = [
                item for item in self.claims.values() if item.snapshot_id == snapshot_id
            ]
            claim_ids = {item.claim_id for item in claims}
            reviews = [
                item
                for item in self.fact_accuracy_reviews
                if item.claim_id in claim_ids
                and review_visible_to_actor(
                    review_case_id=item.review_case_id,
                    review_case_status=item.review_case_status,
                    reviewed_by=item.reviewed_by,
                    actor_id=actor_id,
                )
            ]
            return build_fact_accuracy_bundle(snapshot_id, claims, reviews)

    def _build_in_memory_fact_accuracy_review(
        self,
        tenant_id: str,
        project_id: str,
        claim: CitationClaimData,
        payload: FactAccuracyReviewCreateRequest,
        supersedes_review_id: Optional[str],
    ) -> FactAccuracyReviewData:
        reviewed_at = now_utc()
        verdict = FactAccuracyVerdict(payload.verdict)
        if verdict == FactAccuracyVerdict.INSUFFICIENT_EVIDENCE:
            if payload.fact_revision_id is not None:
                raise StarletteHTTPException(
                    409,
                    detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": "insufficient_review_must_not_bind_fact"}},
                )
            model = FactAccuracyReview(
                id=f"fact_accuracy_review_{uuid4().hex}",
                claim_id=claim.claim_id,
                verdict=verdict,
                evidence_grade=FactAccuracyEvidenceGrade.NO_APPROVED_FACT,
                rationale=payload.rationale,
                review_method=payload.review_method,
                reviewed_by=payload.reviewed_by,
                reviewed_at=reviewed_at,
                supersedes_review_id=supersedes_review_id,
            )
            return fact_accuracy_review_data(model, None, False)
        fact = self.approved_facts.get(payload.fact_revision_id or "")
        if fact is None:
            raise StarletteHTTPException(
                409,
                detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": "approved_fact_required"}},
            )
        if fact["tenant_id"] != tenant_id or fact["project_id"] != project_id:
            raise StarletteHTTPException(
                409, detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID"}
            )
        model = FactAccuracyReview(
            id=f"fact_accuracy_review_{uuid4().hex}",
            claim_id=claim.claim_id,
            verdict=verdict,
            evidence_grade=FactAccuracyEvidenceGrade.APPROVED_FACT_SOURCE_BOUNDARY,
            rationale=payload.rationale,
            review_method=payload.review_method,
            reviewed_by=payload.reviewed_by,
            reviewed_at=reviewed_at,
            fact_revision_id=fact["fact_revision_id"],
            knowledge_source_id=fact["knowledge_source_id"],
            knowledge_segment_id=fact["knowledge_segment_id"],
            fact_revision_sha256=fact["fact_revision_sha256"],
            source_content_sha256=fact["source_content_sha256"],
            quoted_text_sha256=sha256_text(fact["fact_text"]),
            source_start=fact["source_start"],
            source_end=fact["source_end"],
            supersedes_review_id=supersedes_review_id,
            fact_revision_current=bool(fact["current"]),
            source_current=bool(fact["source_current"]),
            no_open_conflict=int(fact["open_conflict_count"]) == 0,
            exact_boundary_verified=(
                fact["source_content"][fact["source_start"] : fact["source_end"]]
                == fact["fact_text"]
            ),
        )
        return fact_accuracy_review_data(model, fact["fact_text"], False)

    @staticmethod
    def _validate_provider_excerpt(payload: CitationSupportReviewCreateRequest, cited_text: str) -> None:
        if payload.evidence_grade != "provider_excerpt_only":
            if not payload.source_object_ref_id:
                raise StarletteHTTPException(
                    409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"}
                )
            return
        normalized = cited_text.strip()
        if not normalized or payload.source_excerpt.strip() not in normalized:
            raise StarletteHTTPException(
                409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"}
            )
        if payload.source_content_sha256 != sha256_text(normalized):
            raise StarletteHTTPException(
                409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"}
            )

    def _validate_evidence(
        self,
        tenant_id: str,
        project_id: str,
        payload: CitationSupportReviewCreateRequest,
        cited_text: str,
    ) -> None:
        if payload.evidence_grade == "provider_excerpt_only":
            self._validate_provider_excerpt(payload, cited_text)
            return
        source_object = self.objects.get(payload.source_object_ref_id or "")
        if (
            source_object is None
            or source_object["tenant_id"] != tenant_id
            or source_object["project_id"] != project_id
            or source_object["sha256"] != payload.source_content_sha256
        ):
            raise StarletteHTTPException(
                409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"}
            )
        if payload.evidence_grade == "source_page_snapshot" and (
            source_object["kind"] != "citation_source_page"
            or source_object["citation_id"] != payload.citation_id
        ):
            raise StarletteHTTPException(
                409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"}
            )
        if payload.evidence_grade == "source_page_snapshot":
            capture = self.captures.get(payload.source_capture_id or "")
            segment = self.segments.get(payload.source_segment_id or "")
            if (
                capture is None
                or segment is None
                or capture["tenant_id"] != tenant_id
                or capture["project_id"] != project_id
                or capture["citation_id"] != payload.citation_id
                or capture["status"] != "completed"
                or capture["raw_object_ref_id"] != payload.source_object_ref_id
                or capture["content_sha256"] != payload.source_content_sha256
                or segment["capture_id"] != payload.source_capture_id
                or not exact_source_excerpt(payload, segment)
            ):
                raise StarletteHTTPException(
                    409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"}
                )

    @staticmethod
    def _review_data(
        claim_id: str,
        payload: CitationSupportReviewCreateRequest,
        supersedes_review_id: Optional[str],
    ) -> CitationSupportReviewData:
        reviewed_at = now_utc()
        model = CitationSupportReview(
            id=f"citation_review_{uuid4().hex}",
            tenant_id="validated-by-repository",
            project_id="validated-by-repository",
            claim_id=claim_id,
            citation_id=payload.citation_id,
            label=CitationSupportLabel(payload.support_label),
            evidence_grade=CitationSupportEvidenceGrade(payload.evidence_grade),
            source_excerpt=payload.source_excerpt,
            source_content_sha256=payload.source_content_sha256,
            source_object_ref_id=payload.source_object_ref_id,
            rationale=payload.rationale,
            review_method=payload.review_method,
            reviewed_by=payload.reviewed_by,
            reviewed_at=reviewed_at,
            source_capture_id=payload.source_capture_id,
            source_segment_id=payload.source_segment_id,
            source_start=payload.source_start,
            source_end=payload.source_end,
        )
        return CitationSupportReviewData(
            review_id=model.id,
            claim_id=claim_id,
            citation_id=model.citation_id,
            support_label=model.label.value,
            evidence_grade=model.evidence_grade.value,
            source_excerpt=model.source_excerpt,
            source_content_sha256=model.source_content_sha256,
            source_object_ref_id=model.source_object_ref_id,
            source_capture_id=model.source_capture_id,
            source_segment_id=model.source_segment_id,
            source_start=model.source_start,
            source_end=model.source_end,
            rationale=model.rationale,
            review_method=model.review_method,
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
            supersedes_review_id=supersedes_review_id,
            evidence_verified=model.evidence_verified,
            commercially_verified=model.commercially_verified,
        )


class MySQLCitationSupportRepository(InMemoryCitationSupportRepository):
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create_claim(
        self, tenant_id: str, snapshot_id: str, payload: CitationClaimCreateRequest
    ) -> CitationClaimData:
        created_at = now_utc()
        with self.engine.begin() as conn:
            sample = conn.execute(
                text(
                    """
                    SELECT id, project_id, answer_text, answer_sha256
                    FROM airank_answer_snapshots
                    WHERE tenant_id=:tenant_id AND id=:snapshot_id
                    """
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).mappings().first()
            if sample is None:
                raise StarletteHTTPException(404, detail={"code": "OBJECT_REF_NOT_FOUND"})
            try:
                claim = CitationClaim.from_answer(
                    id=f"citation_claim_{uuid4().hex}",
                    tenant_id=tenant_id,
                    project_id=str(sample["project_id"]),
                    snapshot_id=snapshot_id,
                    answer_text=str(sample["answer_text"] or ""),
                    answer_start=payload.answer_start,
                    answer_end=payload.answer_end,
                    created_by=payload.created_by,
                    created_at=created_at,
                    claim_kind=AnswerClaimKind(payload.claim_kind),
                    subject_entity_text=payload.subject_entity_text,
                )
            except ValueError as exc:
                raise StarletteHTTPException(
                    409,
                    detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID", "details": {"reason": str(exc)}},
                ) from exc
            existing = conn.execute(
                text(
                    """
                    SELECT * FROM airank_answer_claims
                    WHERE tenant_id=:tenant_id AND snapshot_id=:snapshot_id
                      AND answer_start=:answer_start AND answer_end=:answer_end
                      AND claim_sha256=:claim_sha256 AND claim_kind=:claim_kind
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "snapshot_id": snapshot_id,
                    "answer_start": claim.answer_start,
                    "answer_end": claim.answer_end,
                    "claim_sha256": sha256_text(claim.claim_text),
                    "claim_kind": payload.claim_kind,
                },
            ).mappings().first()
            if existing is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_answer_claims (
                          id, tenant_id, project_id, snapshot_id, claim_text,
                          answer_start, answer_end, answer_sha256, claim_sha256,
                          extraction_method, extractor_version, claim_kind,
                          subject_entity_text, created_by, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :snapshot_id, :claim_text,
                          :answer_start, :answer_end, :answer_sha256, :claim_sha256,
                          :extraction_method, :extractor_version, :claim_kind,
                          :subject_entity_text, :created_by, :created_at
                        )
                        """
                    ),
                    {
                        "id": claim.id,
                        "tenant_id": tenant_id,
                        "project_id": claim.project_id,
                        "snapshot_id": snapshot_id,
                        "claim_text": claim.claim_text,
                        "answer_start": claim.answer_start,
                        "answer_end": claim.answer_end,
                        "answer_sha256": claim.answer_sha256,
                        "claim_sha256": sha256_text(claim.claim_text),
                        "extraction_method": payload.extraction_method,
                        "extractor_version": payload.extractor_version,
                        "claim_kind": payload.claim_kind,
                        "subject_entity_text": payload.subject_entity_text,
                        "created_by": claim.created_by,
                        "created_at": created_at,
                    },
                )
                existing = conn.execute(
                    text("SELECT * FROM airank_answer_claims WHERE id=:id"), {"id": claim.id}
                ).mappings().one()
        return claim_row(existing)

    def create_review(
        self, tenant_id: str, claim_id: str, payload: CitationSupportReviewCreateRequest
    ) -> CitationSupportReviewData:
        reviewed_at = now_utc()
        with self.engine.begin() as conn:
            pair = conn.execute(
                text(
                    """
                    SELECT cl.project_id, cl.snapshot_id, c.cited_text
                    FROM airank_answer_claims cl
                    JOIN airank_source_citations c
                      ON c.tenant_id=cl.tenant_id AND c.snapshot_id=cl.snapshot_id
                    WHERE cl.tenant_id=:tenant_id AND cl.id=:claim_id AND c.id=:citation_id
                    """
                ),
                {"tenant_id": tenant_id, "claim_id": claim_id, "citation_id": payload.citation_id},
            ).mappings().first()
            if pair is None:
                claim_exists = conn.execute(
                    text("SELECT id FROM airank_answer_claims WHERE tenant_id=:tenant_id AND id=:id"),
                    {"tenant_id": tenant_id, "id": claim_id},
                ).first()
                code = "CITATION_NOT_FOUND" if claim_exists else "CITATION_CLAIM_NOT_FOUND"
                raise StarletteHTTPException(404, detail={"code": code})
            self._validate_mysql_evidence(conn, tenant_id, str(pair["project_id"]), payload, str(pair["cited_text"] or ""))
            previous = conn.execute(
                text(
                    """
                    SELECT id FROM airank_citation_support_reviews
                    WHERE tenant_id=:tenant_id AND claim_id=:claim_id AND citation_id=:citation_id
                    ORDER BY reviewed_at DESC, id DESC LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "claim_id": claim_id, "citation_id": payload.citation_id},
            ).first()
            model = CitationSupportReview(
                id=f"citation_review_{uuid4().hex}",
                tenant_id=tenant_id,
                project_id=str(pair["project_id"]),
                claim_id=claim_id,
                citation_id=payload.citation_id,
                label=CitationSupportLabel(payload.support_label),
                evidence_grade=CitationSupportEvidenceGrade(payload.evidence_grade),
                source_excerpt=payload.source_excerpt,
                source_content_sha256=payload.source_content_sha256,
                source_object_ref_id=payload.source_object_ref_id,
                rationale=payload.rationale,
                review_method=payload.review_method,
                reviewed_by=payload.reviewed_by,
                reviewed_at=reviewed_at,
                source_capture_id=payload.source_capture_id,
                source_segment_id=payload.source_segment_id,
                source_start=payload.source_start,
                source_end=payload.source_end,
            )
            supersedes = str(previous[0]) if previous else None
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_support_reviews (
                      id, tenant_id, project_id, claim_id, citation_id, support_label,
                      evidence_grade, source_excerpt, source_content_sha256,
                      source_object_ref_id, source_capture_id, source_segment_id,
                      source_start, source_end, rationale, review_method, reviewed_by,
                      reviewed_at, supersedes_review_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :claim_id, :citation_id, :support_label,
                      :evidence_grade, :source_excerpt, :source_content_sha256,
                      :source_object_ref_id, :source_capture_id, :source_segment_id,
                      :source_start, :source_end, :rationale, :review_method, :reviewed_by,
                      :reviewed_at, :supersedes_review_id, :created_at
                    )
                    """
                ),
                {
                    "id": model.id,
                    "tenant_id": tenant_id,
                    "project_id": model.project_id,
                    "claim_id": claim_id,
                    "citation_id": model.citation_id,
                    "support_label": model.label.value,
                    "evidence_grade": model.evidence_grade.value,
                    "source_excerpt": model.source_excerpt,
                    "source_content_sha256": model.source_content_sha256,
                    "source_object_ref_id": model.source_object_ref_id,
                    "source_capture_id": model.source_capture_id,
                    "source_segment_id": model.source_segment_id,
                    "source_start": model.source_start,
                    "source_end": model.source_end,
                    "rationale": model.rationale,
                    "review_method": model.review_method,
                    "reviewed_by": model.reviewed_by,
                    "reviewed_at": reviewed_at,
                    "supersedes_review_id": supersedes,
                    "created_at": reviewed_at,
                },
            )
        return review_model_data(model, supersedes)

    def get_bundle(
        self, tenant_id: str, snapshot_id: str, actor_id: Optional[str] = None
    ) -> CitationSupportBundleData:
        with self.engine.begin() as conn:
            sample = conn.execute(
                text("SELECT id FROM airank_answer_snapshots WHERE tenant_id=:tenant_id AND id=:id"),
                {"tenant_id": tenant_id, "id": snapshot_id},
            ).first()
            if sample is None:
                raise StarletteHTTPException(404, detail={"code": "OBJECT_REF_NOT_FOUND"})
            citation_ids = tuple(
                str(row[0])
                for row in conn.execute(
                    text(
                        "SELECT id FROM airank_source_citations WHERE tenant_id=:tenant_id AND snapshot_id=:snapshot_id ORDER BY citation_order, id"
                    ),
                    {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
                ).all()
            )
            claim_rows = conn.execute(
                text(
                    "SELECT * FROM airank_answer_claims WHERE tenant_id=:tenant_id AND snapshot_id=:snapshot_id ORDER BY answer_start, id"
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).mappings().all()
            claims = [claim_row(row) for row in claim_rows]
            claim_ids = [item.claim_id for item in claims]
            reviews: list[CitationSupportReviewData] = []
            if claim_ids:
                placeholders = ", ".join(f":claim_{index}" for index in range(len(claim_ids)))
                params: dict[str, Any] = {"tenant_id": tenant_id}
                params.update({f"claim_{index}": value for index, value in enumerate(claim_ids)})
                review_rows = conn.execute(
                    text(
                        f"""
                        SELECT r.*, c.status AS review_case_status,
                               c.purpose AS review_case_purpose
                        FROM airank_citation_support_reviews r
                        LEFT JOIN airank_evidence_review_cases c
                          ON c.tenant_id=r.tenant_id AND c.id=r.review_case_id
                        WHERE r.tenant_id=:tenant_id AND r.claim_id IN ({placeholders})
                        ORDER BY r.reviewed_at, r.id
                        """
                    ),
                    params,
                ).mappings().all()
                reviews = [
                    review
                    for review in (review_row(row) for row in review_rows)
                    if review_visible_to_actor(
                        review_case_id=review.review_case_id,
                        review_case_status=review.review_case_status,
                        reviewed_by=review.reviewed_by,
                        actor_id=actor_id,
                    )
                ]
        return build_bundle(snapshot_id, citation_ids, claims, reviews)

    def create_fact_accuracy_review(
        self,
        tenant_id: str,
        claim_id: str,
        payload: FactAccuracyReviewCreateRequest,
        idempotency_key: str,
        trace_id: str,
    ) -> FactAccuracyReviewData:
        reviewed_at = now_utc()
        with self.engine.begin() as conn:
            replay = conn.execute(
                text(
                    """
                    SELECT id, claim_id
                    FROM airank_fact_accuracy_reviews
                    WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key
                    """
                ),
                {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
            ).mappings().first()
            if replay is not None:
                if str(replay["claim_id"]) != claim_id:
                    raise StarletteHTTPException(
                        409, detail={"code": "IDEMPOTENCY_CONFLICT"}
                    )
                return self._get_fact_accuracy_review(
                    conn, tenant_id, str(replay["id"]), replay=True
                )

            claim = conn.execute(
                text(
                    """
                    SELECT cl.*, s.project_id AS sample_project_id
                    FROM airank_answer_claims cl
                    JOIN airank_answer_snapshots s
                      ON s.tenant_id=cl.tenant_id AND s.id=cl.snapshot_id
                    WHERE cl.tenant_id=:tenant_id AND cl.id=:claim_id
                    """
                ),
                {"tenant_id": tenant_id, "claim_id": claim_id},
            ).mappings().first()
            if claim is None:
                raise StarletteHTTPException(
                    404, detail={"code": "CITATION_CLAIM_NOT_FOUND"}
                )
            if not AnswerClaimKind(
                str(claim.get("claim_kind") or "unclassified")
            ).eligible_for_fact_accuracy:
                raise StarletteHTTPException(
                    409,
                    detail={
                        "code": "FACT_ACCURACY_EVIDENCE_INVALID",
                        "details": {"reason": "claim_kind_not_factual"},
                    },
                )
            project_id = str(claim["project_id"])
            verdict = FactAccuracyVerdict(payload.verdict)
            evidence: dict[str, Any]
            if verdict == FactAccuracyVerdict.INSUFFICIENT_EVIDENCE:
                if payload.fact_revision_id is not None:
                    raise StarletteHTTPException(
                        409,
                        detail={
                            "code": "FACT_ACCURACY_EVIDENCE_INVALID",
                            "details": {"reason": "insufficient_review_must_not_bind_fact"},
                        },
                    )
                evidence = {
                    "evidence_grade": FactAccuracyEvidenceGrade.NO_APPROVED_FACT.value,
                    "fact_revision_id": None,
                    "knowledge_source_id": None,
                    "knowledge_segment_id": None,
                    "fact_revision_sha256": None,
                    "source_content_sha256": None,
                    "quoted_text": None,
                    "quoted_text_sha256": None,
                    "source_start": None,
                    "source_end": None,
                }
            else:
                evidence = self._resolve_current_fact_evidence(
                    conn,
                    tenant_id,
                    project_id,
                    payload.fact_revision_id,
                    reviewed_at,
                )
            previous = conn.execute(
                text(
                    """
                    SELECT id FROM airank_fact_accuracy_reviews
                    WHERE tenant_id=:tenant_id AND claim_id=:claim_id
                    ORDER BY reviewed_at DESC, id DESC LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "claim_id": claim_id},
            ).first()
            review_id = f"fact_accuracy_review_{uuid4().hex}"
            supersedes = str(previous[0]) if previous else None
            insert_prefix = (
                "INSERT OR IGNORE" if self.engine.dialect.name == "sqlite" else "INSERT IGNORE"
            )
            inserted = conn.execute(
                text(
                    f"""
                    {insert_prefix} INTO airank_fact_accuracy_reviews (
                      id, tenant_id, project_id, claim_id, verdict, evidence_grade,
                      fact_revision_id, knowledge_source_id, knowledge_segment_id,
                      fact_revision_sha256, source_content_sha256, quoted_text,
                      quoted_text_sha256, source_start, source_end, rationale,
                      review_method, reviewed_by, reviewed_at,
                      supersedes_review_id, idempotency_key, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :claim_id, :verdict, :evidence_grade,
                      :fact_revision_id, :knowledge_source_id, :knowledge_segment_id,
                      :fact_revision_sha256, :source_content_sha256, :quoted_text,
                      :quoted_text_sha256, :source_start, :source_end, :rationale,
                      :review_method, :reviewed_by, :reviewed_at,
                      :supersedes_review_id, :idempotency_key, :created_at
                    )
                    """
                ),
                {
                    "id": review_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "claim_id": claim_id,
                    "verdict": verdict.value,
                    **evidence,
                    "rationale": payload.rationale,
                    "review_method": payload.review_method,
                    "reviewed_by": payload.reviewed_by,
                    "reviewed_at": reviewed_at,
                    "supersedes_review_id": supersedes,
                    "idempotency_key": idempotency_key,
                    "created_at": reviewed_at,
                },
            )
            if inserted.rowcount == 0:
                raced = conn.execute(
                    text(
                        """
                        SELECT id, claim_id FROM airank_fact_accuracy_reviews
                        WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key
                        """
                    ),
                    {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
                ).mappings().one()
                if str(raced["claim_id"]) != claim_id:
                    raise StarletteHTTPException(
                        409, detail={"code": "IDEMPOTENCY_CONFLICT"}
                    )
                return self._get_fact_accuracy_review(
                    conn, tenant_id, str(raced["id"]), replay=True
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, event_type, entity_type,
                      entity_id, trace_id, payload_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'sample.fact_accuracy_reviewed',
                      'fact_accuracy_review', :entity_id, :trace_id,
                      :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": f"audit_{uuid4().hex}",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "entity_id": review_id,
                    "trace_id": trace_id,
                    "payload_json": json.dumps(
                        {
                            "claim_id": claim_id,
                            "verdict": verdict.value,
                            "evidence_grade": evidence["evidence_grade"],
                            "fact_revision_id": evidence["fact_revision_id"],
                            "fact_revision_sha256": evidence["fact_revision_sha256"],
                            "source_content_sha256": evidence["source_content_sha256"],
                            "review_method": payload.review_method,
                            "reviewed_by": payload.reviewed_by,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "created_at": reviewed_at,
                },
            )
            return self._get_fact_accuracy_review(
                conn, tenant_id, review_id, replay=False
            )

    def get_fact_accuracy_bundle(
        self, tenant_id: str, snapshot_id: str, actor_id: Optional[str] = None
    ) -> FactAccuracyBundleData:
        with self.engine.begin() as conn:
            sample = conn.execute(
                text(
                    "SELECT id FROM airank_answer_snapshots WHERE tenant_id=:tenant_id AND id=:id"
                ),
                {"tenant_id": tenant_id, "id": snapshot_id},
            ).first()
            if sample is None:
                raise StarletteHTTPException(404, detail={"code": "OBJECT_REF_NOT_FOUND"})
            claim_rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_answer_claims
                    WHERE tenant_id=:tenant_id AND snapshot_id=:snapshot_id
                    ORDER BY answer_start, id
                    """
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).mappings().all()
            claims = [claim_row(row) for row in claim_rows]
            claim_ids = [item.claim_id for item in claims]
            reviews: list[FactAccuracyReviewData] = []
            if claim_ids:
                placeholders = ", ".join(
                    f":fact_claim_{index}" for index in range(len(claim_ids))
                )
                params: dict[str, Any] = {"tenant_id": tenant_id}
                params.update(
                    {f"fact_claim_{index}": value for index, value in enumerate(claim_ids)}
                )
                rows = conn.execute(
                    text(
                        f"""
                        SELECT id FROM airank_fact_accuracy_reviews
                        WHERE tenant_id=:tenant_id AND claim_id IN ({placeholders})
                        ORDER BY reviewed_at, id
                        """
                    ),
                    params,
                ).all()
                reviews = [
                    self._get_fact_accuracy_review(
                        conn, tenant_id, str(row[0]), replay=False
                    )
                    for row in rows
                ]
                reviews = [
                    review
                    for review in reviews
                    if review_visible_to_actor(
                        review_case_id=review.review_case_id,
                        review_case_status=review.review_case_status,
                        reviewed_by=review.reviewed_by,
                        actor_id=actor_id,
                    )
                ]
        return build_fact_accuracy_bundle(snapshot_id, claims, reviews)

    @staticmethod
    def _resolve_current_fact_evidence(
        conn: Any,
        tenant_id: str,
        project_id: str,
        fact_revision_id: Optional[str],
        reviewed_at: datetime,
    ) -> dict[str, Any]:
        if not fact_revision_id:
            raise StarletteHTTPException(
                409,
                detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": "fact_revision_required"}},
            )
        fact = conn.execute(
            text(
                """
                SELECT r.*, f.current_revision_id, f.disclosure,
                       (SELECT COUNT(*) FROM airank_fact_conflicts c
                        WHERE c.tenant_id=r.tenant_id
                          AND c.fact_atom_id=r.fact_atom_id
                          AND c.status='open') AS open_conflict_count
                FROM airank_fact_revisions r
                JOIN airank_fact_atoms f
                  ON f.tenant_id=r.tenant_id AND f.id=r.fact_atom_id
                WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id
                  AND r.id=:revision_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "revision_id": fact_revision_id,
            },
        ).mappings().first()
        if fact is None:
            raise StarletteHTTPException(
                404, detail={"code": "FACT_REVISION_NOT_FOUND"}
            )
        invalid_reason = None
        if str(fact["status"]) != "approved" or str(fact["current_revision_id"] or "") != fact_revision_id:
            invalid_reason = "revision_not_current_approved"
        elif int(fact["open_conflict_count"] or 0):
            invalid_reason = "open_conflict"
        elif fact["valid_from"] is not None and _utc_datetime(fact["valid_from"]) > reviewed_at:
            invalid_reason = "fact_not_yet_valid"
        elif fact["valid_until"] is not None and _utc_datetime(fact["valid_until"]) <= reviewed_at:
            invalid_reason = "fact_expired"
        elif str(fact["disclosure"]) not in {"public", "redacted"}:
            invalid_reason = "fact_not_disclosable"
        elif not fact["reviewed_by"] or not fact["reviewed_at"]:
            invalid_reason = "human_fact_review_required"
        if invalid_reason:
            raise StarletteHTTPException(
                409,
                detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": invalid_reason}},
            )
        source_ids = _json_list(fact["source_ids_json"])
        for source_id in source_ids:
            source = conn.execute(
                text(
                    """
                    SELECT s.id, s.content_sha256, c.content_text
                    FROM airank_knowledge_sources s
                    JOIN airank_knowledge_source_contents c
                      ON c.knowledge_source_id=s.id AND c.tenant_id=s.tenant_id
                    WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                      AND s.id=:source_id AND s.status='active'
                      AND (s.valid_from IS NULL OR s.valid_from<=:reviewed_at)
                      AND (s.valid_until IS NULL OR s.valid_until>:reviewed_at)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_id": source_id,
                    "reviewed_at": reviewed_at,
                },
            ).mappings().first()
            if source is None:
                continue
            fact_text = str(fact["fact_text"])
            source_content = str(source["content_text"])
            start = source_content.find(fact_text)
            if start < 0:
                continue
            end = start + len(fact_text)
            segment = conn.execute(
                text(
                    """
                    SELECT id, segment_text, source_start, source_end
                    FROM airank_knowledge_segments
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND knowledge_source_id=:source_id
                      AND source_start<=:source_start AND source_end>=:source_end
                    ORDER BY segment_index LIMIT 1
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_id": source_id,
                    "source_start": start,
                    "source_end": end,
                },
            ).mappings().first()
            if segment is None:
                continue
            relative_start = start - int(segment["source_start"])
            relative_end = end - int(segment["source_start"])
            if str(segment["segment_text"])[relative_start:relative_end] != fact_text:
                continue
            return {
                "evidence_grade": FactAccuracyEvidenceGrade.APPROVED_FACT_SOURCE_BOUNDARY.value,
                "fact_revision_id": fact_revision_id,
                "knowledge_source_id": str(source["id"]),
                "knowledge_segment_id": str(segment["id"]),
                "fact_revision_sha256": str(fact["content_sha256"]),
                "source_content_sha256": str(source["content_sha256"]),
                "quoted_text": fact_text,
                "quoted_text_sha256": sha256_text(fact_text),
                "source_start": start,
                "source_end": end,
            }
        raise StarletteHTTPException(
            409,
            detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": "exact_source_boundary_missing"}},
        )

    @staticmethod
    def _get_fact_accuracy_review(
        conn: Any, tenant_id: str, review_id: str, *, replay: bool
    ) -> FactAccuracyReviewData:
        row = conn.execute(
            text(
                """
                SELECT ar.*, fr.status AS fact_status,
                       fr.content_sha256 AS current_fact_sha256,
                       fr.valid_from AS fact_valid_from,
                       fr.valid_until AS fact_valid_until,
                       f.current_revision_id, f.disclosure,
                       src.status AS source_status,
                       src.content_sha256 AS current_source_sha256,
                       src.valid_from AS source_valid_from,
                       src.valid_until AS source_valid_until,
                       content.content_text, segment.segment_text,
                       segment.source_start AS segment_start,
                       segment.source_end AS segment_end,
                       review_case.status AS review_case_status,
                       review_case.purpose AS review_case_purpose,
                       (SELECT COUNT(*) FROM airank_fact_conflicts c
                        WHERE c.tenant_id=ar.tenant_id
                          AND c.fact_atom_id=fr.fact_atom_id
                          AND c.status='open') AS open_conflict_count
                FROM airank_fact_accuracy_reviews ar
                LEFT JOIN airank_fact_revisions fr
                  ON fr.tenant_id=ar.tenant_id AND fr.id=ar.fact_revision_id
                LEFT JOIN airank_fact_atoms f
                  ON f.tenant_id=fr.tenant_id AND f.id=fr.fact_atom_id
                LEFT JOIN airank_knowledge_sources src
                  ON src.tenant_id=ar.tenant_id AND src.id=ar.knowledge_source_id
                LEFT JOIN airank_knowledge_source_contents content
                  ON content.tenant_id=src.tenant_id
                 AND content.knowledge_source_id=src.id
                LEFT JOIN airank_knowledge_segments segment
                  ON segment.tenant_id=ar.tenant_id
                 AND segment.id=ar.knowledge_segment_id
                LEFT JOIN airank_evidence_review_cases review_case
                  ON review_case.tenant_id=ar.tenant_id
                 AND review_case.id=ar.review_case_id
                WHERE ar.tenant_id=:tenant_id AND ar.id=:review_id
                """
            ),
            {"tenant_id": tenant_id, "review_id": review_id},
        ).mappings().one()
        return fact_accuracy_review_row(row, replay=replay)

    @staticmethod
    def _validate_mysql_evidence(conn, tenant_id: str, project_id: str, payload: CitationSupportReviewCreateRequest, cited_text: str) -> None:
        if payload.evidence_grade == "provider_excerpt_only":
            InMemoryCitationSupportRepository._validate_provider_excerpt(payload, cited_text)
            return
        if not payload.source_object_ref_id:
            raise StarletteHTTPException(409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"})
        object_row = conn.execute(
            text(
                """
                SELECT sha256, metadata_json FROM airank_object_refs
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:object_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "object_id": payload.source_object_ref_id},
        ).mappings().first()
        if object_row is None or str(object_row["sha256"] or "") != payload.source_content_sha256:
            raise StarletteHTTPException(409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"})
        if payload.evidence_grade == "source_page_snapshot":
            metadata = json_object(object_row["metadata_json"])
            if (
                metadata.get("kind") != "citation_source_page"
                or metadata.get("citation_id") != payload.citation_id
                or metadata.get("capture_id") != payload.source_capture_id
            ):
                raise StarletteHTTPException(409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"})
            source_row = conn.execute(
                text(
                    """
                    SELECT cap.status, cap.citation_id, cap.raw_object_ref_id,
                           cap.content_sha256, seg.capture_id,
                           seg.source_start AS segment_start,
                           seg.source_end AS segment_end, seg.segment_text
                    FROM airank_citation_source_captures cap
                    JOIN airank_citation_source_segments seg
                      ON seg.tenant_id=cap.tenant_id AND seg.capture_id=cap.id
                    WHERE cap.tenant_id=:tenant_id AND cap.project_id=:project_id
                      AND cap.id=:capture_id AND seg.id=:segment_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "capture_id": payload.source_capture_id or "",
                    "segment_id": payload.source_segment_id or "",
                },
            ).mappings().first()
            if (
                source_row is None
                or str(source_row["status"]) != "completed"
                or str(source_row["citation_id"]) != payload.citation_id
                or str(source_row["raw_object_ref_id"] or "") != payload.source_object_ref_id
                or str(source_row["content_sha256"] or "") != payload.source_content_sha256
                or not exact_source_excerpt(
                    payload,
                    {
                        "source_start": int(source_row["segment_start"]),
                        "source_end": int(source_row["segment_end"]),
                        "segment_text": str(source_row["segment_text"]),
                    },
                )
            ):
                raise StarletteHTTPException(
                    409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"}
                )


def claim_row(row: Mapping[str, Any]) -> CitationClaimData:
    return CitationClaimData(
        claim_id=str(row["id"]),
        snapshot_id=str(row["snapshot_id"]),
        claim_text=str(row["claim_text"]),
        answer_start=int(row["answer_start"]),
        answer_end=int(row["answer_end"]),
        answer_sha256=str(row["answer_sha256"]),
        claim_sha256=str(row["claim_sha256"]),
        extraction_method=str(row["extraction_method"]),
        extractor_version=str(row["extractor_version"]),
        claim_kind=str(row.get("claim_kind") or "unclassified"),
        subject_entity_text=(
            str(row["subject_entity_text"]) if row.get("subject_entity_text") else None
        ),
        created_by=str(row["created_by"]),
        created_at=row["created_at"],
    )


def review_model_data(model: CitationSupportReview, supersedes: Optional[str]) -> CitationSupportReviewData:
    return CitationSupportReviewData(
        review_id=model.id,
        claim_id=model.claim_id,
        citation_id=model.citation_id,
        support_label=model.label.value,
        evidence_grade=model.evidence_grade.value,
        source_excerpt=model.source_excerpt,
        source_content_sha256=model.source_content_sha256,
        source_object_ref_id=model.source_object_ref_id,
        source_capture_id=model.source_capture_id,
        source_segment_id=model.source_segment_id,
        source_start=model.source_start,
        source_end=model.source_end,
        rationale=model.rationale,
        review_method=model.review_method,
        reviewed_by=model.reviewed_by,
        reviewed_at=model.reviewed_at,
        supersedes_review_id=supersedes,
        review_case_id=model.review_case_id,
        reviewer_role=model.reviewer_role,
        review_case_status=model.review_case_status,
        review_case_purpose=model.review_case_purpose,
        evidence_verified=model.evidence_verified,
        commercially_verified=model.commercially_verified,
    )


def review_row(row: Mapping[str, Any]) -> CitationSupportReviewData:
    model = CitationSupportReview(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        claim_id=str(row["claim_id"]),
        citation_id=str(row["citation_id"]),
        label=CitationSupportLabel(str(row["support_label"])),
        evidence_grade=CitationSupportEvidenceGrade(str(row["evidence_grade"])),
        source_excerpt=str(row["source_excerpt"]),
        source_content_sha256=str(row["source_content_sha256"]),
        source_object_ref_id=str(row["source_object_ref_id"]) if row["source_object_ref_id"] else None,
        rationale=str(row["rationale"]),
        review_method=str(row["review_method"]),
        reviewed_by=str(row["reviewed_by"]),
        reviewed_at=row["reviewed_at"],
        source_capture_id=(
            str(row["source_capture_id"]) if row.get("source_capture_id") else None
        ),
        source_segment_id=(
            str(row["source_segment_id"]) if row.get("source_segment_id") else None
        ),
        source_start=(int(row["source_start"]) if row.get("source_start") is not None else None),
        source_end=(int(row["source_end"]) if row.get("source_end") is not None else None),
        review_case_id=(
            str(row["review_case_id"]) if row.get("review_case_id") else None
        ),
        reviewer_role=str(row.get("reviewer_role") or "single"),
        review_case_status=str(row.get("review_case_status") or "single_review"),
        review_case_purpose=str(row.get("review_case_purpose") or "single_review"),
    )
    return review_model_data(model, str(row["supersedes_review_id"]) if row["supersedes_review_id"] else None)


def fact_accuracy_review_data(
    model: FactAccuracyReview,
    quoted_text: Optional[str],
    replay: bool,
) -> FactAccuracyReviewData:
    return FactAccuracyReviewData(
        review_id=model.id,
        claim_id=model.claim_id,
        verdict=model.verdict.value,
        evidence_grade=model.evidence_grade.value,
        fact_revision_id=model.fact_revision_id,
        knowledge_source_id=model.knowledge_source_id,
        knowledge_segment_id=model.knowledge_segment_id,
        fact_revision_sha256=model.fact_revision_sha256,
        source_content_sha256=model.source_content_sha256,
        quoted_text=quoted_text,
        quoted_text_sha256=model.quoted_text_sha256,
        source_start=model.source_start,
        source_end=model.source_end,
        rationale=model.rationale,
        review_method=model.review_method,
        reviewed_by=model.reviewed_by,
        reviewed_at=model.reviewed_at,
        supersedes_review_id=model.supersedes_review_id,
        review_case_id=model.review_case_id,
        reviewer_role=model.reviewer_role,
        review_case_status=model.review_case_status,
        review_case_purpose=model.review_case_purpose,
        evidence_verified=model.evidence_verified,
        commercially_verified=model.commercially_verified,
        idempotent_replay=replay,
    )


def fact_accuracy_review_row(
    row: Mapping[str, Any], *, replay: bool
) -> FactAccuracyReviewData:
    reviewed_at = _utc_datetime(row["reviewed_at"])
    now = now_utc()
    has_fact = bool(row.get("fact_revision_id"))
    fact_current = bool(
        has_fact
        and str(row.get("fact_status") or "") == "approved"
        and str(row.get("current_revision_id") or "")
        == str(row.get("fact_revision_id") or "")
        and str(row.get("current_fact_sha256") or "")
        == str(row.get("fact_revision_sha256") or "")
        and str(row.get("disclosure") or "") in {"public", "redacted"}
        and (
            row.get("fact_valid_from") is None
            or _utc_datetime(row["fact_valid_from"]) <= now
        )
        and (
            row.get("fact_valid_until") is None
            or _utc_datetime(row["fact_valid_until"]) > now
        )
    )
    source_current = bool(
        has_fact
        and str(row.get("source_status") or "") == "active"
        and str(row.get("current_source_sha256") or "")
        == str(row.get("source_content_sha256") or "")
        and (
            row.get("source_valid_from") is None
            or _utc_datetime(row["source_valid_from"]) <= now
        )
        and (
            row.get("source_valid_until") is None
            or _utc_datetime(row["source_valid_until"]) > now
        )
    )
    quoted_text = str(row["quoted_text"]) if row.get("quoted_text") else None
    exact_boundary = False
    if (
        quoted_text is not None
        and row.get("source_start") is not None
        and row.get("source_end") is not None
        and row.get("segment_start") is not None
        and row.get("segment_end") is not None
        and row.get("segment_text") is not None
        and row.get("content_text") is not None
    ):
        start = int(row["source_start"])
        end = int(row["source_end"])
        segment_start = int(row["segment_start"])
        segment_end = int(row["segment_end"])
        relative_start = start - segment_start
        relative_end = end - segment_start
        exact_boundary = bool(
            0 <= start < end <= len(str(row["content_text"]))
            and segment_start <= start < end <= segment_end
            and str(row["content_text"])[start:end] == quoted_text
            and str(row["segment_text"])[relative_start:relative_end] == quoted_text
            and sha256_text(quoted_text)
            == str(row.get("quoted_text_sha256") or "")
        )
    model = FactAccuracyReview(
        id=str(row["id"]),
        claim_id=str(row["claim_id"]),
        verdict=FactAccuracyVerdict(str(row["verdict"])),
        evidence_grade=FactAccuracyEvidenceGrade(str(row["evidence_grade"])),
        rationale=str(row["rationale"]),
        review_method=str(row["review_method"]),
        reviewed_by=str(row["reviewed_by"]),
        reviewed_at=reviewed_at,
        fact_revision_id=(
            str(row["fact_revision_id"]) if row.get("fact_revision_id") else None
        ),
        knowledge_source_id=(
            str(row["knowledge_source_id"])
            if row.get("knowledge_source_id")
            else None
        ),
        knowledge_segment_id=(
            str(row["knowledge_segment_id"])
            if row.get("knowledge_segment_id")
            else None
        ),
        fact_revision_sha256=(
            str(row["fact_revision_sha256"])
            if row.get("fact_revision_sha256")
            else None
        ),
        source_content_sha256=(
            str(row["source_content_sha256"])
            if row.get("source_content_sha256")
            else None
        ),
        quoted_text_sha256=(
            str(row["quoted_text_sha256"])
            if row.get("quoted_text_sha256")
            else None
        ),
        source_start=(
            int(row["source_start"]) if row.get("source_start") is not None else None
        ),
        source_end=(
            int(row["source_end"]) if row.get("source_end") is not None else None
        ),
        supersedes_review_id=(
            str(row["supersedes_review_id"])
            if row.get("supersedes_review_id")
            else None
        ),
        fact_revision_current=fact_current,
        source_current=source_current,
        no_open_conflict=int(row.get("open_conflict_count") or 0) == 0,
        exact_boundary_verified=exact_boundary,
        review_case_id=(
            str(row["review_case_id"]) if row.get("review_case_id") else None
        ),
        reviewer_role=str(row.get("reviewer_role") or "single"),
        review_case_status=str(row.get("review_case_status") or "single_review"),
        review_case_purpose=str(row.get("review_case_purpose") or "single_review"),
    )
    return fact_accuracy_review_data(model, quoted_text, replay)


def build_fact_accuracy_bundle(
    snapshot_id: str,
    claims: list[CitationClaimData],
    reviews: list[FactAccuracyReviewData],
) -> FactAccuracyBundleData:
    claim_models = tuple(
        FactAccuracyClaim(
            id=item.claim_id,
            snapshot_id=item.snapshot_id,
            claim_kind=AnswerClaimKind(item.claim_kind),
            claim_text=item.claim_text,
            claim_sha256=item.claim_sha256,
            answer_start=item.answer_start,
            answer_end=item.answer_end,
            subject_entity_text=item.subject_entity_text,
        )
        for item in claims
    )
    review_models = tuple(
        FactAccuracyReview(
            id=item.review_id,
            claim_id=item.claim_id,
            verdict=FactAccuracyVerdict(item.verdict),
            evidence_grade=FactAccuracyEvidenceGrade(item.evidence_grade),
            rationale=item.rationale,
            review_method=item.review_method,
            reviewed_by=item.reviewed_by,
            reviewed_at=item.reviewed_at,
            fact_revision_id=item.fact_revision_id,
            knowledge_source_id=item.knowledge_source_id,
            knowledge_segment_id=item.knowledge_segment_id,
            fact_revision_sha256=item.fact_revision_sha256,
            source_content_sha256=item.source_content_sha256,
            quoted_text_sha256=item.quoted_text_sha256,
            source_start=item.source_start,
            source_end=item.source_end,
            supersedes_review_id=item.supersedes_review_id,
            fact_revision_current=item.commercially_verified,
            source_current=item.commercially_verified,
            no_open_conflict=item.commercially_verified,
            exact_boundary_verified=item.commercially_verified,
            review_case_id=item.review_case_id,
            reviewer_role=item.reviewer_role,
            review_case_status=item.review_case_status,
            review_case_purpose=item.review_case_purpose,
        )
        for item in reviews
    )
    metrics = calculate_fact_accuracy_metrics(
        claims=claim_models,
        reviews=review_models,
    )
    return FactAccuracyBundleData(
        snapshot_id=snapshot_id,
        claims=claims,
        reviews=reviews,
        metrics=FactAccuracyMetricsData(
            registered_claim_count=metrics.registered_claim_count,
            factual_claim_count=metrics.factual_claim_count,
            reviewed_claim_count=metrics.reviewed_claim_count,
            commercially_verified_claim_count=metrics.commercially_verified_claim_count,
            decisive_claim_count=metrics.decisive_claim_count,
            accurate_count=metrics.accurate_count,
            inaccurate_count=metrics.inaccurate_count,
            outdated_count=metrics.outdated_count,
            insufficient_evidence_count=metrics.insufficient_evidence_count,
            evaluation_coverage_rate=metrics.evaluation_coverage_rate,
            fact_accuracy=metrics.fact_accuracy,
            known_limitations=list(metrics.known_limitations),
        ),
    )


def load_fact_accuracy_bundles_from_connection(
    conn: Any,
    tenant_id: str,
    snapshot_ids: list[str] | tuple[str, ...],
) -> dict[str, FactAccuracyBundleData]:
    """Load recalculable fact-accuracy bundles inside an existing transaction."""

    ordered_snapshot_ids = tuple(dict.fromkeys(item for item in snapshot_ids if item))
    if not ordered_snapshot_ids:
        return {}
    snapshot_placeholders = ", ".join(
        f":fact_snapshot_{index}" for index in range(len(ordered_snapshot_ids))
    )
    params: dict[str, Any] = {"tenant_id": tenant_id}
    params.update(
        {
            f"fact_snapshot_{index}": value
            for index, value in enumerate(ordered_snapshot_ids)
        }
    )
    claim_rows = conn.execute(
        text(
            f"""
            SELECT * FROM airank_answer_claims
            WHERE tenant_id=:tenant_id
              AND snapshot_id IN ({snapshot_placeholders})
            ORDER BY snapshot_id, answer_start, id
            """
        ),
        params,
    ).mappings().all()
    claims_by_snapshot: dict[str, list[CitationClaimData]] = {
        snapshot_id: [] for snapshot_id in ordered_snapshot_ids
    }
    for row in claim_rows:
        claims_by_snapshot[str(row["snapshot_id"])].append(claim_row(row))

    claim_ids = [str(row["id"]) for row in claim_rows]
    reviews_by_claim: dict[str, list[FactAccuracyReviewData]] = {}
    if claim_ids:
        claim_placeholders = ", ".join(
            f":fact_claim_{index}" for index in range(len(claim_ids))
        )
        review_params: dict[str, Any] = {"tenant_id": tenant_id}
        review_params.update(
            {f"fact_claim_{index}": value for index, value in enumerate(claim_ids)}
        )
        review_rows = conn.execute(
            text(
                f"""
                SELECT id, claim_id
                FROM airank_fact_accuracy_reviews
                WHERE tenant_id=:tenant_id
                  AND claim_id IN ({claim_placeholders})
                ORDER BY reviewed_at, id
                """
            ),
            review_params,
        ).mappings().all()
        for row in review_rows:
            review = MySQLCitationSupportRepository._get_fact_accuracy_review(
                conn,
                tenant_id,
                str(row["id"]),
                replay=False,
            )
            reviews_by_claim.setdefault(str(row["claim_id"]), []).append(review)

    bundles: dict[str, FactAccuracyBundleData] = {}
    for snapshot_id in ordered_snapshot_ids:
        claims = claims_by_snapshot[snapshot_id]
        reviews = [
            review
            for claim in claims
            for review in reviews_by_claim.get(claim.claim_id, [])
        ]
        bundles[snapshot_id] = build_fact_accuracy_bundle(
            snapshot_id,
            claims,
            reviews,
        )
    return bundles


def load_citation_support_bundles_from_connection(
    conn: Any,
    tenant_id: str,
    snapshot_ids: list[str] | tuple[str, ...],
) -> dict[str, CitationSupportBundleData]:
    """Load citation-support bundles without exposing pending peer decisions."""

    ordered_snapshot_ids = tuple(dict.fromkeys(item for item in snapshot_ids if item))
    if not ordered_snapshot_ids:
        return {}
    placeholders = ", ".join(
        f":citation_snapshot_{index}" for index in range(len(ordered_snapshot_ids))
    )
    params: dict[str, Any] = {"tenant_id": tenant_id}
    params.update(
        {
            f"citation_snapshot_{index}": value
            for index, value in enumerate(ordered_snapshot_ids)
        }
    )
    citation_rows = conn.execute(
        text(
            f"""
            SELECT id, snapshot_id
            FROM airank_source_citations
            WHERE tenant_id=:tenant_id AND snapshot_id IN ({placeholders})
            ORDER BY snapshot_id, citation_order, id
            """
        ),
        params,
    ).mappings().all()
    citation_ids_by_snapshot: dict[str, list[str]] = {
        snapshot_id: [] for snapshot_id in ordered_snapshot_ids
    }
    for row in citation_rows:
        citation_ids_by_snapshot[str(row["snapshot_id"])].append(str(row["id"]))

    claim_rows = conn.execute(
        text(
            f"""
            SELECT * FROM airank_answer_claims
            WHERE tenant_id=:tenant_id AND snapshot_id IN ({placeholders})
            ORDER BY snapshot_id, answer_start, id
            """
        ),
        params,
    ).mappings().all()
    claims_by_snapshot: dict[str, list[CitationClaimData]] = {
        snapshot_id: [] for snapshot_id in ordered_snapshot_ids
    }
    for row in claim_rows:
        claims_by_snapshot[str(row["snapshot_id"])].append(claim_row(row))

    reviews_by_claim: dict[str, list[CitationSupportReviewData]] = {}
    claim_ids = [str(row["id"]) for row in claim_rows]
    if claim_ids:
        claim_placeholders = ", ".join(
            f":citation_claim_{index}" for index in range(len(claim_ids))
        )
        review_params: dict[str, Any] = {"tenant_id": tenant_id}
        review_params.update(
            {
                f"citation_claim_{index}": value
                for index, value in enumerate(claim_ids)
            }
        )
        review_rows = conn.execute(
            text(
                f"""
                SELECT r.*, c.status AS review_case_status,
                       c.purpose AS review_case_purpose
                FROM airank_citation_support_reviews r
                LEFT JOIN airank_evidence_review_cases c
                  ON c.tenant_id=r.tenant_id AND c.id=r.review_case_id
                WHERE r.tenant_id=:tenant_id
                  AND r.claim_id IN ({claim_placeholders})
                ORDER BY r.reviewed_at, r.id
                """
            ),
            review_params,
        ).mappings().all()
        for row in review_rows:
            reviews_by_claim.setdefault(str(row["claim_id"]), []).append(
                review_row(row)
            )

    return {
        snapshot_id: build_bundle(
            snapshot_id,
            tuple(citation_ids_by_snapshot[snapshot_id]),
            claims_by_snapshot[snapshot_id],
            [
                review
                for claim in claims_by_snapshot[snapshot_id]
                for review in reviews_by_claim.get(claim.claim_id, [])
            ],
        )
        for snapshot_id in ordered_snapshot_ids
    }


def build_bundle(
    snapshot_id: str,
    citation_ids: tuple[str, ...],
    claims: list[CitationClaimData],
    reviews: list[CitationSupportReviewData],
) -> CitationSupportBundleData:
    claim_models = tuple(
        CitationClaim(
            id=item.claim_id,
            tenant_id="validated-by-repository",
            project_id="validated-by-repository",
            snapshot_id=item.snapshot_id,
            claim_text=item.claim_text,
            answer_start=item.answer_start,
            answer_end=item.answer_end,
            answer_sha256=item.answer_sha256,
            created_by=item.created_by,
            created_at=item.created_at,
            claim_kind=AnswerClaimKind(item.claim_kind),
            subject_entity_text=item.subject_entity_text,
        )
        for item in claims
    )
    review_models = tuple(
        CitationSupportReview(
            id=item.review_id,
            tenant_id="validated-by-repository",
            project_id="validated-by-repository",
            claim_id=item.claim_id,
            citation_id=item.citation_id,
            label=CitationSupportLabel(item.support_label),
            evidence_grade=CitationSupportEvidenceGrade(item.evidence_grade),
            source_excerpt=item.source_excerpt,
            source_content_sha256=item.source_content_sha256,
            source_object_ref_id=item.source_object_ref_id,
            rationale=item.rationale,
            review_method=item.review_method,
            reviewed_by=item.reviewed_by,
            reviewed_at=item.reviewed_at,
            source_capture_id=item.source_capture_id,
            source_segment_id=item.source_segment_id,
            source_start=item.source_start,
            source_end=item.source_end,
            review_case_id=item.review_case_id,
            reviewer_role=item.reviewer_role,
            review_case_status=item.review_case_status,
            review_case_purpose=item.review_case_purpose,
        )
        for item in reviews
    )
    metrics = calculate_citation_support_metrics(
        selected_citation_ids=citation_ids,
        claims=claim_models,
        reviews=review_models,
    )
    return CitationSupportBundleData(
        snapshot_id=snapshot_id,
        claims=claims,
        reviews=reviews,
        metrics=CitationSupportMetricsData(
            selected_citation_count=metrics.selected_citation_count,
            claim_count=metrics.claim_count,
            review_count=metrics.review_count,
            commercially_verified_review_count=metrics.commercially_verified_review_count,
            supports_count=metrics.supports_count,
            contradicts_count=metrics.contradicts_count,
            insufficient_count=metrics.insufficient_count,
            citation_support_rate=metrics.citation_support_rate,
            known_limitations=list(metrics.known_limitations),
        ),
    )


def json_object(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = json.loads(value or "[]")
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return []


def _utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def build_repository() -> CitationSupportRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLCitationSupportRepository(database_url) if database_url else InMemoryCitationSupportRepository()


CITATION_SUPPORT_REPOSITORY: CitationSupportRepository = build_repository()


@router.get("/samples/{snapshot_id}/citation-support", response_model=CitationSupportBundleResponse)
def get_citation_support(
    snapshot_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
) -> CitationSupportBundleResponse:
    return CitationSupportBundleResponse(
        data=CITATION_SUPPORT_REPOSITORY.get_bundle(
            tenant_id, snapshot_id, authenticated_actor
        ),
        meta=response_meta(trace_id),
    )


@router.post("/samples/{snapshot_id}/citation-claims", response_model=CitationClaimResponse, status_code=201)
def create_citation_claim(
    snapshot_id: str,
    payload: CitationClaimCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> CitationClaimResponse:
    trusted = payload.model_copy(update={"created_by": trusted_actor(payload.created_by, authenticated_actor)})
    try:
        data = CITATION_SUPPORT_REPOSITORY.create_claim(tenant_id, snapshot_id, trusted)
    except ValueError as exc:
        raise StarletteHTTPException(
            409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID", "details": {"reason": str(exc)}}
        ) from exc
    return CitationClaimResponse(data=data, meta=response_meta(trace_id))


@router.post("/citation-claims/{claim_id}/reviews", response_model=CitationSupportReviewResponse, status_code=201)
def create_citation_support_review(
    claim_id: str,
    payload: CitationSupportReviewCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> CitationSupportReviewResponse:
    trusted = payload.model_copy(update={"reviewed_by": trusted_actor(payload.reviewed_by, authenticated_actor)})
    try:
        data = CITATION_SUPPORT_REPOSITORY.create_review(tenant_id, claim_id, trusted)
    except ValueError as exc:
        raise StarletteHTTPException(
            409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID", "details": {"reason": str(exc)}}
        ) from exc
    return CitationSupportReviewResponse(data=data, meta=response_meta(trace_id))


@router.get(
    "/samples/{snapshot_id}/fact-accuracy",
    response_model=FactAccuracyBundleResponse,
)
def get_fact_accuracy(
    snapshot_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
) -> FactAccuracyBundleResponse:
    return FactAccuracyBundleResponse(
        data=CITATION_SUPPORT_REPOSITORY.get_fact_accuracy_bundle(
            tenant_id, snapshot_id, authenticated_actor
        ),
        meta=response_meta(trace_id),
    )


@router.post(
    "/answer-claims/{claim_id}/fact-accuracy-reviews",
    response_model=FactAccuracyReviewResponse,
    status_code=201,
)
def create_fact_accuracy_review(
    claim_id: str,
    payload: FactAccuracyReviewCreateRequest,
    idempotency_key: str = Header(
        min_length=8, max_length=160, alias="Idempotency-Key"
    ),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
) -> FactAccuracyReviewResponse:
    meta = response_meta(trace_id)
    trusted = payload.model_copy(
        update={
            "reviewed_by": trusted_actor(
                payload.reviewed_by, authenticated_actor
            )
        }
    )
    try:
        data = CITATION_SUPPORT_REPOSITORY.create_fact_accuracy_review(
            tenant_id,
            claim_id,
            trusted,
            idempotency_key,
            meta["trace_id"],
        )
    except ValueError as exc:
        raise StarletteHTTPException(
            409,
            detail={
                "code": "FACT_ACCURACY_EVIDENCE_INVALID",
                "details": {"reason": str(exc)},
            },
        ) from exc
    return FactAccuracyReviewResponse(data=data, meta=meta)

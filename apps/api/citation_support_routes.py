from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from threading import RLock
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain.measurement import sha256_text
from airank_evidence import (
    CitationClaim,
    CitationSupportEvidenceGrade,
    CitationSupportLabel,
    CitationSupportReview,
    calculate_citation_support_metrics,
)


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["citation-support"])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested: str, authenticated: Optional[str]) -> str:
    return (authenticated or requested).strip()


class CitationClaimCreateRequest(BaseModel):
    answer_start: int = Field(ge=0)
    answer_end: int = Field(gt=0)
    extraction_method: Literal["manual", "ai_assisted"] = "manual"
    extractor_version: str = Field(default="airank.citation-claim.manual.v1", min_length=1, max_length=64)
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
    rationale: str = Field(min_length=1, max_length=4_000)
    review_method: Literal["human", "ai_assisted"] = "human"
    reviewed_by: str = Field(min_length=1, max_length=64)


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
    created_by: str
    created_at: datetime


class CitationSupportReviewData(BaseModel):
    review_id: str
    claim_id: str
    citation_id: str
    support_label: str
    evidence_grade: str
    source_excerpt: str
    source_content_sha256: str
    source_object_ref_id: Optional[str]
    rationale: str
    review_method: str
    reviewed_by: str
    reviewed_at: datetime
    supersedes_review_id: Optional[str]
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
    def get_bundle(self, tenant_id: str, snapshot_id: str) -> CitationSupportBundleData: ...


class InMemoryCitationSupportRepository:
    def __init__(self) -> None:
        self.lock = RLock()
        self.samples: dict[tuple[str, str], dict[str, str]] = {}
        self.citations: dict[str, dict[str, str]] = {}
        self.objects: dict[str, dict[str, str]] = {}
        self.claims: dict[str, CitationClaimData] = {}
        self.reviews: list[CitationSupportReviewData] = []

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
            )
            for current in self.claims.values():
                if (
                    current.snapshot_id == snapshot_id
                    and current.answer_start == claim.answer_start
                    and current.answer_end == claim.answer_end
                    and current.claim_sha256 == sha256_text(claim.claim_text)
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

    def get_bundle(self, tenant_id: str, snapshot_id: str) -> CitationSupportBundleData:
        with self.lock:
            if (tenant_id, snapshot_id) not in self.samples:
                raise StarletteHTTPException(404, detail={"code": "OBJECT_REF_NOT_FOUND"})
            claims = [item for item in self.claims.values() if item.snapshot_id == snapshot_id]
            claim_ids = {item.claim_id for item in claims}
            reviews = [item for item in self.reviews if item.claim_id in claim_ids]
            citation_ids = tuple(
                item_id
                for item_id, item in self.citations.items()
                if item["tenant_id"] == tenant_id and item["snapshot_id"] == snapshot_id
            )
            return build_bundle(snapshot_id, citation_ids, claims, reviews)

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
            rationale=model.rationale,
            review_method=model.review_method,
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
            supersedes_review_id=supersedes_review_id,
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
                      AND claim_sha256=:claim_sha256
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "snapshot_id": snapshot_id,
                    "answer_start": claim.answer_start,
                    "answer_end": claim.answer_end,
                    "claim_sha256": sha256_text(claim.claim_text),
                },
            ).mappings().first()
            if existing is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_answer_claims (
                          id, tenant_id, project_id, snapshot_id, claim_text,
                          answer_start, answer_end, answer_sha256, claim_sha256,
                          extraction_method, extractor_version, created_by, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :snapshot_id, :claim_text,
                          :answer_start, :answer_end, :answer_sha256, :claim_sha256,
                          :extraction_method, :extractor_version, :created_by, :created_at
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
            )
            supersedes = str(previous[0]) if previous else None
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_support_reviews (
                      id, tenant_id, project_id, claim_id, citation_id, support_label,
                      evidence_grade, source_excerpt, source_content_sha256,
                      source_object_ref_id, rationale, review_method, reviewed_by,
                      reviewed_at, supersedes_review_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :claim_id, :citation_id, :support_label,
                      :evidence_grade, :source_excerpt, :source_content_sha256,
                      :source_object_ref_id, :rationale, :review_method, :reviewed_by,
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
                    "rationale": model.rationale,
                    "review_method": model.review_method,
                    "reviewed_by": model.reviewed_by,
                    "reviewed_at": reviewed_at,
                    "supersedes_review_id": supersedes,
                    "created_at": reviewed_at,
                },
            )
        return review_model_data(model, supersedes)

    def get_bundle(self, tenant_id: str, snapshot_id: str) -> CitationSupportBundleData:
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
                        f"SELECT * FROM airank_citation_support_reviews WHERE tenant_id=:tenant_id AND claim_id IN ({placeholders}) ORDER BY reviewed_at, id"
                    ),
                    params,
                ).mappings().all()
                reviews = [review_row(row) for row in review_rows]
        return build_bundle(snapshot_id, citation_ids, claims, reviews)

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
            ):
                raise StarletteHTTPException(409, detail={"code": "CITATION_SUPPORT_EVIDENCE_INVALID"})


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
        rationale=model.rationale,
        review_method=model.review_method,
        reviewed_by=model.reviewed_by,
        reviewed_at=model.reviewed_at,
        supersedes_review_id=supersedes,
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
    )
    return review_model_data(model, str(row["supersedes_review_id"]) if row["supersedes_review_id"] else None)


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


def build_repository() -> CitationSupportRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLCitationSupportRepository(database_url) if database_url else InMemoryCitationSupportRepository()


CITATION_SUPPORT_REPOSITORY: CitationSupportRepository = build_repository()


@router.get("/samples/{snapshot_id}/citation-support", response_model=CitationSupportBundleResponse)
def get_citation_support(
    snapshot_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> CitationSupportBundleResponse:
    return CitationSupportBundleResponse(
        data=CITATION_SUPPORT_REPOSITORY.get_bundle(tenant_id, snapshot_id),
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

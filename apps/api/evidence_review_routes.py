from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from threading import RLock
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain.measurement import sha256_text
from airank_evidence import IndependentReviewPair, calculate_review_quality_metrics

try:
    from . import citation_support_routes as citation_routes
except ImportError:  # pragma: no cover
    import citation_support_routes as citation_routes  # type: ignore[no-redef]


router = APIRouter(prefix="/api/v1", tags=["evidence-review-quality"])
TRACE_HEADER = "X-AIRank-Trace-Id"
BENCHMARK_VERSION = "airank.evidence-review-benchmark.v1"
BENCHMARK_MINIMUM_CASE_COUNT = 20


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def canonical_sha256(value: Mapping[str, Any]) -> str:
    return sha256_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested: str, authenticated: Optional[str]) -> str:
    return citation_routes.trusted_actor(requested, authenticated)


class CitationReviewCaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=64)
    purpose: Literal["production", "benchmark"] = "production"
    benchmark_version: Optional[str] = Field(default=None, min_length=1, max_length=64)
    review: citation_routes.CitationSupportReviewCreateRequest

    @model_validator(mode="after")
    def validate_benchmark(self) -> "CitationReviewCaseCreateRequest":
        if self.purpose == "benchmark" and not self.benchmark_version:
            self.benchmark_version = BENCHMARK_VERSION
        if self.purpose == "production" and self.benchmark_version is not None:
            raise ValueError("production review case cannot declare benchmark_version")
        return self


class FactReviewCaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=64)
    purpose: Literal["production", "benchmark"] = "production"
    benchmark_version: Optional[str] = Field(default=None, min_length=1, max_length=64)
    review: citation_routes.FactAccuracyReviewCreateRequest

    @model_validator(mode="after")
    def validate_benchmark(self) -> "FactReviewCaseCreateRequest":
        if self.purpose == "benchmark" and not self.benchmark_version:
            self.benchmark_version = BENCHMARK_VERSION
        if self.purpose == "production" and self.benchmark_version is not None:
            raise ValueError("production review case cannot declare benchmark_version")
        return self


class EvidenceReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=32)
    rationale: str = Field(min_length=1, max_length=4_000)
    reviewed_by: str = Field(min_length=1, max_length=64)


class EvidenceReviewDecisionData(BaseModel):
    reviewer_role: Literal["primary", "secondary", "adjudicator"]
    label: str
    rationale: str
    reviewed_by: str
    reviewed_at: datetime
    review_id: str


class EvidenceReviewCaseData(BaseModel):
    case_id: str
    tenant_id: str
    project_id: str
    snapshot_id: str
    review_kind: Literal["citation_support", "fact_accuracy"]
    claim_id: str
    citation_id: Optional[str]
    evidence_basis_sha256: str
    purpose: Literal["production", "benchmark"]
    benchmark_version: Optional[str]
    status: Literal[
        "creating",
        "awaiting_secondary",
        "disputed",
        "agreed",
        "adjudicated",
        "void",
    ]
    consensus_label: Optional[str]
    decision_count: int
    current_actor_role: Optional[Literal["primary", "secondary", "adjudicator"]]
    next_action: Literal["submit_secondary", "adjudicate", "complete", "none"]
    visible_decisions: list[EvidenceReviewDecisionData]
    created_by: str
    finalized_by: Optional[str]
    created_at: datetime
    finalized_at: Optional[datetime]
    version: int
    idempotent_replay: bool = False


class ReviewQualityMetricsData(BaseModel):
    case_count: int
    independently_reviewed_case_count: int
    finalized_case_count: int
    awaiting_secondary_count: int
    disputed_count: int
    agreement_count: int
    disagreement_count: int
    adjudicated_count: int
    raw_agreement_rate: Optional[float]
    cohen_kappa: Optional[float]
    benchmark_minimum_case_count: int
    benchmark_minimum_kappa: float
    benchmark_ready: bool
    benchmark_quality_passed: bool
    known_limitations: list[str]


class EvidenceReviewQueueData(BaseModel):
    project_id: str
    snapshot_id: Optional[str]
    cases: list[EvidenceReviewCaseData]
    production_quality: ReviewQualityMetricsData
    benchmark_quality: ReviewQualityMetricsData


class EvidenceReviewCaseResponse(BaseModel):
    data: EvidenceReviewCaseData
    meta: dict[str, str]


class EvidenceReviewQueueResponse(BaseModel):
    data: EvidenceReviewQueueData
    meta: dict[str, str]


class EvidenceReviewRepository(Protocol):
    def create_citation_case(
        self,
        tenant_id: str,
        project_id: str,
        payload: CitationReviewCaseCreateRequest,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData: ...

    def create_fact_case(
        self,
        tenant_id: str,
        project_id: str,
        payload: FactReviewCaseCreateRequest,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData: ...

    def submit_decision(
        self,
        tenant_id: str,
        case_id: str,
        payload: EvidenceReviewDecisionRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData: ...

    def list_cases(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_id: Optional[str],
        actor: str,
    ) -> EvidenceReviewQueueData: ...


def evidence_basis_for_citation(
    claim_id: str, review: citation_routes.CitationSupportReviewCreateRequest
) -> str:
    return canonical_sha256(
        {
            "claim_id": claim_id,
            "citation_id": review.citation_id,
            "evidence_grade": review.evidence_grade,
            "source_excerpt": review.source_excerpt,
            "source_content_sha256": review.source_content_sha256,
            "source_object_ref_id": review.source_object_ref_id,
            "source_capture_id": review.source_capture_id,
            "source_segment_id": review.source_segment_id,
            "source_start": review.source_start,
            "source_end": review.source_end,
        }
    )


def evidence_basis_for_fact(
    claim_id: str, review: citation_routes.FactAccuracyReviewCreateRequest
) -> str:
    return canonical_sha256(
        {
            "claim_id": claim_id,
            "fact_revision_id": review.fact_revision_id,
            "evidence_mode": (
                "no_approved_fact"
                if review.verdict == "insufficient_evidence"
                else "approved_fact_source_boundary"
            ),
        }
    )


def target_key(review_kind: str, claim_id: str, citation_id: Optional[str]) -> str:
    return canonical_sha256(
        {
            "review_kind": review_kind,
            "claim_id": claim_id,
            "citation_id": citation_id,
        }
    )


def allowed_labels(review_kind: str) -> set[str]:
    if review_kind == "citation_support":
        return {"supports", "contradicts", "insufficient"}
    return {"accurate", "inaccurate", "outdated", "insufficient_evidence"}


def validate_label_against_frozen_evidence(
    review_kind: str,
    primary: Any,
    label: str,
) -> None:
    """A peer may relabel frozen evidence, but cannot change its evidence class."""

    if review_kind != "fact_accuracy":
        return
    evidence_grade = (
        str(primary.get("evidence_grade"))
        if isinstance(primary, Mapping)
        else str(primary.evidence_grade)
    )
    evidence_grade = evidence_grade.rsplit(".", 1)[-1].lower()
    has_approved_fact = evidence_grade == "approved_fact_source_boundary"
    label_is_insufficient = label == "insufficient_evidence"
    if has_approved_fact == label_is_insufficient:
        raise StarletteHTTPException(
            409,
            detail={
                "code": "EVIDENCE_REVIEW_LABEL_INVALID",
                "details": {"reason": "label_conflicts_with_frozen_evidence"},
            },
        )


def metrics_data(pairs: tuple[IndependentReviewPair, ...]) -> ReviewQualityMetricsData:
    value = calculate_review_quality_metrics(
        pairs,
        benchmark_minimum_case_count=BENCHMARK_MINIMUM_CASE_COUNT,
    )
    return ReviewQualityMetricsData(
        case_count=value.case_count,
        independently_reviewed_case_count=value.independently_reviewed_case_count,
        finalized_case_count=value.finalized_case_count,
        awaiting_secondary_count=value.awaiting_secondary_count,
        disputed_count=value.disputed_count,
        agreement_count=value.agreement_count,
        disagreement_count=value.disagreement_count,
        adjudicated_count=value.adjudicated_count,
        raw_agreement_rate=value.raw_agreement_rate,
        cohen_kappa=value.cohen_kappa,
        benchmark_minimum_case_count=value.benchmark_minimum_case_count,
        benchmark_minimum_kappa=value.benchmark_minimum_kappa,
        benchmark_ready=value.benchmark_ready,
        benchmark_quality_passed=value.benchmark_quality_passed,
        known_limitations=list(value.known_limitations),
    )


class InMemoryEvidenceReviewRepository:
    def __init__(self) -> None:
        self.lock = RLock()
        self.cases: dict[str, dict[str, Any]] = {}
        self.idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}

    def create_citation_case(
        self,
        tenant_id: str,
        project_id: str,
        payload: CitationReviewCaseCreateRequest,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData:
        del trace_id
        review = payload.review.model_copy(update={"reviewed_by": actor})
        request_hash = canonical_sha256(
            {"project_id": project_id, **payload.model_dump(mode="json"), "actor": actor}
        )
        with self.lock:
            replay = self._replay(tenant_id, project_id, idempotency_key, request_hash, actor)
            if replay:
                return replay
            repo = citation_routes.CITATION_SUPPORT_REPOSITORY
            if not isinstance(repo, citation_routes.InMemoryCitationSupportRepository):
                raise RuntimeError("in-memory review repository requires in-memory citation repository")
            case_id = f"evidence_review_case_{uuid4().hex}"
            basis = evidence_basis_for_citation(payload.claim_id, review)
            duplicate = self._find_basis(tenant_id, project_id, "citation_support", basis, payload.purpose)
            if duplicate:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_CASE_EXISTS", "details": {"case_id": duplicate}})
            created = repo.create_review(tenant_id, payload.claim_id, review)
            decorated = created.model_copy(
                update={
                    "review_case_id": case_id,
                    "reviewer_role": "primary",
                    "review_case_status": "awaiting_secondary",
                    "review_case_purpose": payload.purpose,
                    "commercially_verified": False,
                }
            )
            repo.reviews[-1] = decorated
            case = self._new_case(
                case_id=case_id,
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=repo.claims[payload.claim_id].snapshot_id,
                review_kind="citation_support",
                claim_id=payload.claim_id,
                citation_id=review.citation_id,
                evidence_basis_sha256=basis,
                purpose=payload.purpose,
                benchmark_version=payload.benchmark_version,
                idempotency_key=idempotency_key,
                request_sha256=request_hash,
                actor=actor,
                review=decorated,
            )
            self.cases[case_id] = case
            self.idempotency[(tenant_id, project_id, idempotency_key)] = (request_hash, case_id)
            return self._case_data(case, actor)

    def create_fact_case(
        self,
        tenant_id: str,
        project_id: str,
        payload: FactReviewCaseCreateRequest,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData:
        review = payload.review.model_copy(update={"reviewed_by": actor})
        request_hash = canonical_sha256(
            {"project_id": project_id, **payload.model_dump(mode="json"), "actor": actor}
        )
        with self.lock:
            replay = self._replay(tenant_id, project_id, idempotency_key, request_hash, actor)
            if replay:
                return replay
            repo = citation_routes.CITATION_SUPPORT_REPOSITORY
            if not isinstance(repo, citation_routes.InMemoryCitationSupportRepository):
                raise RuntimeError("in-memory review repository requires in-memory citation repository")
            basis = evidence_basis_for_fact(payload.claim_id, review)
            duplicate = self._find_basis(tenant_id, project_id, "fact_accuracy", basis, payload.purpose)
            if duplicate:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_CASE_EXISTS", "details": {"case_id": duplicate}})
            created = repo.create_fact_accuracy_review(
                tenant_id,
                payload.claim_id,
                review,
                f"{idempotency_key}:primary",
                trace_id,
            )
            case_id = f"evidence_review_case_{uuid4().hex}"
            decorated = created.model_copy(
                update={
                    "review_case_id": case_id,
                    "reviewer_role": "primary",
                    "review_case_status": "awaiting_secondary",
                    "review_case_purpose": payload.purpose,
                    "commercially_verified": False,
                }
            )
            repo.fact_accuracy_reviews[-1] = decorated
            repo.fact_accuracy_idempotency[(tenant_id, f"{idempotency_key}:primary")] = decorated
            case = self._new_case(
                case_id=case_id,
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=repo.claims[payload.claim_id].snapshot_id,
                review_kind="fact_accuracy",
                claim_id=payload.claim_id,
                citation_id=None,
                evidence_basis_sha256=basis,
                purpose=payload.purpose,
                benchmark_version=payload.benchmark_version,
                idempotency_key=idempotency_key,
                request_sha256=request_hash,
                actor=actor,
                review=decorated,
            )
            self.cases[case_id] = case
            self.idempotency[(tenant_id, project_id, idempotency_key)] = (request_hash, case_id)
            return self._case_data(case, actor)

    def submit_decision(
        self,
        tenant_id: str,
        case_id: str,
        payload: EvidenceReviewDecisionRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData:
        with self.lock:
            case = self.cases.get(case_id)
            if case is None or case["tenant_id"] != tenant_id:
                raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_CASE_NOT_FOUND"})
            self._validate_decision(case, payload.label, actor)
            primary = case["decisions"][0]
            role = "secondary" if case["status"] == "awaiting_secondary" else "adjudicator"
            review = self._clone_in_memory_review(case, primary, payload, actor, role, trace_id)
            case["decisions"].append(review)
            case["version"] += 1
            if role == "secondary":
                if review_label_value(primary) == payload.label:
                    case.update(
                        status="agreed",
                        consensus_label=payload.label,
                        finalized_by=actor,
                        finalized_at=now_utc(),
                    )
                else:
                    case["status"] = "disputed"
            else:
                case.update(
                    status="adjudicated",
                    consensus_label=payload.label,
                    finalized_by=actor,
                    finalized_at=now_utc(),
                )
            self._decorate_latest_review(case, review)
            return self._case_data(case, actor)

    def list_cases(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_id: Optional[str],
        actor: str,
    ) -> EvidenceReviewQueueData:
        with self.lock:
            cases = [
                value
                for value in self.cases.values()
                if value["tenant_id"] == tenant_id
                and value["project_id"] == project_id
                and (snapshot_id is None or value["snapshot_id"] == snapshot_id)
            ]
            return build_queue(project_id, snapshot_id, cases, actor)

    def _replay(self, tenant_id: str, project_id: str, key: str, request_hash: str, actor: str) -> Optional[EvidenceReviewCaseData]:
        item = self.idempotency.get((tenant_id, project_id, key))
        if item is None:
            return None
        stored_hash, case_id = item
        if stored_hash != request_hash:
            raise StarletteHTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
        return self._case_data(self.cases[case_id], actor).model_copy(update={"idempotent_replay": True})

    def _find_basis(self, tenant_id: str, project_id: str, kind: str, basis: str, purpose: str) -> Optional[str]:
        return next(
            (
                case_id
                for case_id, case in self.cases.items()
                if case["tenant_id"] == tenant_id
                and case["project_id"] == project_id
                and case["review_kind"] == kind
                and case["evidence_basis_sha256"] == basis
                and case["purpose"] == purpose
            ),
            None,
        )

    @staticmethod
    def _new_case(**values: Any) -> dict[str, Any]:
        review = values.pop("review")
        created_at = now_utc()
        return {
            **values,
            "status": "awaiting_secondary",
            "consensus_label": None,
            "decisions": [review],
            "version": 1,
            "created_by": values["actor"],
            "finalized_by": None,
            "created_at": created_at,
            "finalized_at": None,
        }

    @staticmethod
    def _validate_decision(case: Mapping[str, Any], label: str, actor: str) -> None:
        if case["status"] not in {"awaiting_secondary", "disputed"}:
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_CASE_FINAL"})
        if label not in allowed_labels(str(case["review_kind"])):
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_LABEL_INVALID"})
        validate_label_against_frozen_evidence(
            str(case["review_kind"]), case["decisions"][0], label
        )
        if any(item.reviewed_by == actor for item in case["decisions"]):
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN"})

    @staticmethod
    def _case_data(case: Mapping[str, Any], actor: str) -> EvidenceReviewCaseData:
        return case_data_from_mapping(case, actor)

    @staticmethod
    def _clone_in_memory_review(case: Mapping[str, Any], primary: Any, payload: EvidenceReviewDecisionRequest, actor: str, role: str, trace_id: str) -> Any:
        repo = citation_routes.CITATION_SUPPORT_REPOSITORY
        if case["review_kind"] == "citation_support":
            request = citation_routes.CitationSupportReviewCreateRequest(
                citation_id=primary.citation_id,
                support_label=payload.label,
                evidence_grade=primary.evidence_grade,
                source_excerpt=primary.source_excerpt,
                source_content_sha256=primary.source_content_sha256,
                source_object_ref_id=primary.source_object_ref_id,
                source_capture_id=primary.source_capture_id,
                source_segment_id=primary.source_segment_id,
                source_start=primary.source_start,
                source_end=primary.source_end,
                rationale=payload.rationale,
                review_method="human",
                reviewed_by=actor,
            )
            created = repo.create_review(case["tenant_id"], case["claim_id"], request)
            decorated = created.model_copy(update={"review_case_id": case["case_id"], "reviewer_role": role, "review_case_status": case["status"], "review_case_purpose": case["purpose"], "commercially_verified": False})
            repo.reviews[-1] = decorated
            return decorated
        primary_request = citation_routes.FactAccuracyReviewCreateRequest(
            verdict=payload.label,
            fact_revision_id=primary.fact_revision_id,
            rationale=payload.rationale,
            review_method="human",
            reviewed_by=actor,
        )
        created = repo.create_fact_accuracy_review(case["tenant_id"], case["claim_id"], primary_request, f"{case['case_id']}:{role}", trace_id)
        decorated = created.model_copy(update={"review_case_id": case["case_id"], "reviewer_role": role, "review_case_status": case["status"], "review_case_purpose": case["purpose"], "commercially_verified": False})
        repo.fact_accuracy_reviews[-1] = decorated
        return decorated

    @staticmethod
    def _decorate_latest_review(case: Mapping[str, Any], review: Any) -> None:
        repo = citation_routes.CITATION_SUPPORT_REPOSITORY
        final = case["status"] in {"agreed", "adjudicated"}
        updated = review.model_copy(
            update={
                "review_case_status": case["status"],
                "commercially_verified": bool(
                    final
                    and review.evidence_verified
                    and review.review_case_purpose == "production"
                ),
            }
        )
        if case["review_kind"] == "citation_support":
            repo.reviews[-1] = updated
            case["decisions"][-1] = updated
        else:
            repo.fact_accuracy_reviews[-1] = updated
            case["decisions"][-1] = updated


class MySQLEvidenceReviewRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create_citation_case(
        self,
        tenant_id: str,
        project_id: str,
        payload: CitationReviewCaseCreateRequest,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData:
        review = payload.review.model_copy(update={"reviewed_by": actor})
        request_hash = canonical_sha256(
            {"project_id": project_id, **payload.model_dump(mode="json"), "actor": actor}
        )
        reviewed_at = now_utc()
        with self.engine.begin() as conn:
            replay = self._idempotent_case(conn, tenant_id, project_id, idempotency_key, request_hash, actor)
            if replay:
                return replay
            pair = conn.execute(
                text(
                    """
                    SELECT cl.project_id, cl.snapshot_id, c.cited_text
                    FROM airank_answer_claims cl
                    JOIN airank_source_citations c
                      ON c.tenant_id=cl.tenant_id AND c.snapshot_id=cl.snapshot_id
                    WHERE cl.tenant_id=:tenant_id AND cl.id=:claim_id
                      AND c.id=:citation_id
                    """
                ),
                {"tenant_id": tenant_id, "claim_id": payload.claim_id, "citation_id": review.citation_id},
            ).mappings().first()
            if pair is None or str(pair["project_id"]) != project_id:
                raise StarletteHTTPException(404, detail={"code": "CITATION_CLAIM_NOT_FOUND"})
            citation_routes.MySQLCitationSupportRepository._validate_mysql_evidence(
                conn, tenant_id, project_id, review, str(pair["cited_text"] or "")
            )
            basis = evidence_basis_for_citation(payload.claim_id, review)
            case_id = f"evidence_review_case_{uuid4().hex}"
            review_id = f"citation_review_{uuid4().hex}"
            self._insert_case(
                conn,
                case_id=case_id,
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=str(pair["snapshot_id"]),
                review_kind="citation_support",
                claim_id=payload.claim_id,
                citation_id=review.citation_id,
                evidence_basis_sha256=basis,
                purpose=payload.purpose,
                benchmark_version=payload.benchmark_version,
                idempotency_key=idempotency_key,
                request_sha256=request_hash,
                actor=actor,
                created_at=reviewed_at,
            )
            previous = self._latest_review_id(conn, "citation_support", tenant_id, payload.claim_id, review.citation_id)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_support_reviews (
                      id, tenant_id, project_id, claim_id, citation_id, support_label,
                      evidence_grade, source_excerpt, source_content_sha256,
                      source_object_ref_id, source_capture_id, source_segment_id,
                      source_start, source_end, rationale, review_method, reviewed_by,
                      reviewed_at, review_case_id, reviewer_role,
                      supersedes_review_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :claim_id, :citation_id, :label,
                      :evidence_grade, :source_excerpt, :source_content_sha256,
                      :source_object_ref_id, :source_capture_id, :source_segment_id,
                      :source_start, :source_end, :rationale, 'human', :reviewed_by,
                      :reviewed_at, :review_case_id, 'primary',
                      :supersedes_review_id, :created_at
                    )
                    """
                ),
                {
                    "id": review_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "claim_id": payload.claim_id,
                    "citation_id": review.citation_id,
                    "label": review.support_label,
                    "evidence_grade": review.evidence_grade,
                    "source_excerpt": review.source_excerpt,
                    "source_content_sha256": review.source_content_sha256,
                    "source_object_ref_id": review.source_object_ref_id,
                    "source_capture_id": review.source_capture_id,
                    "source_segment_id": review.source_segment_id,
                    "source_start": review.source_start,
                    "source_end": review.source_end,
                    "rationale": review.rationale,
                    "reviewed_by": actor,
                    "reviewed_at": reviewed_at,
                    "review_case_id": case_id,
                    "supersedes_review_id": previous,
                    "created_at": reviewed_at,
                },
            )
            self._activate_case(conn, case_id, review_id, reviewed_at)
            self._audit(conn, tenant_id, project_id, case_id, "evidence_review.case_created", actor, trace_id, {"review_kind": "citation_support", "review_id": review_id, "purpose": payload.purpose}, reviewed_at)
            return self._load_case(conn, tenant_id, case_id, actor)

    def create_fact_case(
        self,
        tenant_id: str,
        project_id: str,
        payload: FactReviewCaseCreateRequest,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData:
        review = payload.review.model_copy(update={"reviewed_by": actor})
        request_hash = canonical_sha256(
            {"project_id": project_id, **payload.model_dump(mode="json"), "actor": actor}
        )
        reviewed_at = now_utc()
        with self.engine.begin() as conn:
            replay = self._idempotent_case(conn, tenant_id, project_id, idempotency_key, request_hash, actor)
            if replay:
                return replay
            claim = conn.execute(
                text("SELECT * FROM airank_answer_claims WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:claim_id"),
                {"tenant_id": tenant_id, "project_id": project_id, "claim_id": payload.claim_id},
            ).mappings().first()
            if claim is None:
                raise StarletteHTTPException(404, detail={"code": "CITATION_CLAIM_NOT_FOUND"})
            if not citation_routes.AnswerClaimKind(str(claim.get("claim_kind") or "unclassified")).eligible_for_fact_accuracy:
                raise StarletteHTTPException(409, detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": "claim_kind_not_factual"}})
            verdict = citation_routes.FactAccuracyVerdict(review.verdict)
            if verdict == citation_routes.FactAccuracyVerdict.INSUFFICIENT_EVIDENCE:
                if review.fact_revision_id is not None:
                    raise StarletteHTTPException(409, detail={"code": "FACT_ACCURACY_EVIDENCE_INVALID", "details": {"reason": "insufficient_review_must_not_bind_fact"}})
                evidence = {
                    "evidence_grade": "no_approved_fact",
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
                evidence = citation_routes.MySQLCitationSupportRepository._resolve_current_fact_evidence(
                    conn, tenant_id, project_id, review.fact_revision_id, reviewed_at
                )
            basis = canonical_sha256({"claim_id": payload.claim_id, **evidence})
            case_id = f"evidence_review_case_{uuid4().hex}"
            review_id = f"fact_accuracy_review_{uuid4().hex}"
            self._insert_case(
                conn,
                case_id=case_id,
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=str(claim["snapshot_id"]),
                review_kind="fact_accuracy",
                claim_id=payload.claim_id,
                citation_id=None,
                evidence_basis_sha256=basis,
                purpose=payload.purpose,
                benchmark_version=payload.benchmark_version,
                idempotency_key=idempotency_key,
                request_sha256=request_hash,
                actor=actor,
                created_at=reviewed_at,
            )
            previous = self._latest_review_id(conn, "fact_accuracy", tenant_id, payload.claim_id, None)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_fact_accuracy_reviews (
                      id, tenant_id, project_id, claim_id, verdict, evidence_grade,
                      fact_revision_id, knowledge_source_id, knowledge_segment_id,
                      fact_revision_sha256, source_content_sha256, quoted_text,
                      quoted_text_sha256, source_start, source_end, rationale,
                      review_method, reviewed_by, reviewed_at, review_case_id,
                      reviewer_role, supersedes_review_id, idempotency_key, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :claim_id, :verdict, :evidence_grade,
                      :fact_revision_id, :knowledge_source_id, :knowledge_segment_id,
                      :fact_revision_sha256, :source_content_sha256, :quoted_text,
                      :quoted_text_sha256, :source_start, :source_end, :rationale,
                      'human', :reviewed_by, :reviewed_at, :review_case_id,
                      'primary', :supersedes_review_id, :idempotency_key, :created_at
                    )
                    """
                ),
                {
                    "id": review_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "claim_id": payload.claim_id,
                    "verdict": verdict.value,
                    **evidence,
                    "rationale": review.rationale,
                    "reviewed_by": actor,
                    "reviewed_at": reviewed_at,
                    "review_case_id": case_id,
                    "supersedes_review_id": previous,
                    "idempotency_key": f"{idempotency_key}:primary",
                    "created_at": reviewed_at,
                },
            )
            self._activate_case(conn, case_id, review_id, reviewed_at)
            self._audit(conn, tenant_id, project_id, case_id, "evidence_review.case_created", actor, trace_id, {"review_kind": "fact_accuracy", "review_id": review_id, "purpose": payload.purpose}, reviewed_at)
            return self._load_case(conn, tenant_id, case_id, actor)

    def submit_decision(
        self,
        tenant_id: str,
        case_id: str,
        payload: EvidenceReviewDecisionRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewCaseData:
        reviewed_at = now_utc()
        with self.engine.begin() as conn:
            lock_suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
            case = conn.execute(
                text(f"SELECT * FROM airank_evidence_review_cases WHERE tenant_id=:tenant_id AND id=:case_id{lock_suffix}"),
                {"tenant_id": tenant_id, "case_id": case_id},
            ).mappings().first()
            if case is None:
                raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_CASE_NOT_FOUND"})
            status = str(case["status"])
            if status not in {"awaiting_secondary", "disputed"}:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_CASE_FINAL"})
            kind = str(case["review_kind"])
            if payload.label not in allowed_labels(kind):
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_LABEL_INVALID"})
            decisions = self._decision_rows(conn, case)
            if any(str(item["reviewed_by"]) == actor for item in decisions):
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN"})
            role = "secondary" if status == "awaiting_secondary" else "adjudicator"
            primary = next(item for item in decisions if str(item["reviewer_role"]) == "primary")
            validate_label_against_frozen_evidence(kind, primary, payload.label)
            review_id = self._clone_decision(conn, case, primary, payload, actor, role, reviewed_at)
            version = int(case["version"]) + 1
            if role == "secondary":
                if self._row_label(kind, primary) == payload.label:
                    next_status = "agreed"
                    consensus = payload.label
                    finalized_by = actor
                    finalized_at = reviewed_at
                else:
                    next_status = "disputed"
                    consensus = None
                    finalized_by = None
                    finalized_at = None
                conn.execute(
                    text(
                        """
                        UPDATE airank_evidence_review_cases
                        SET status=:status, consensus_label=:consensus_label,
                            secondary_review_id=:review_id, version=:version,
                            finalized_by=:finalized_by, finalized_at=:finalized_at,
                            updated_at=:updated_at
                        WHERE tenant_id=:tenant_id AND id=:case_id
                        """
                    ),
                    {"status": next_status, "consensus_label": consensus, "review_id": review_id, "version": version, "finalized_by": finalized_by, "finalized_at": finalized_at, "updated_at": reviewed_at, "tenant_id": tenant_id, "case_id": case_id},
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE airank_evidence_review_cases
                        SET status='adjudicated', consensus_label=:consensus_label,
                            adjudication_review_id=:review_id, version=:version,
                            finalized_by=:finalized_by, finalized_at=:finalized_at,
                            updated_at=:updated_at
                        WHERE tenant_id=:tenant_id AND id=:case_id
                        """
                    ),
                    {"consensus_label": payload.label, "review_id": review_id, "version": version, "finalized_by": actor, "finalized_at": reviewed_at, "updated_at": reviewed_at, "tenant_id": tenant_id, "case_id": case_id},
                )
            self._audit(conn, tenant_id, str(case["project_id"]), case_id, "evidence_review.decision_submitted", actor, trace_id, {"review_kind": kind, "reviewer_role": role, "review_id": review_id, "status": next_status if role == "secondary" else "adjudicated"}, reviewed_at)
            return self._load_case(conn, tenant_id, case_id, actor)

    def list_cases(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_id: Optional[str],
        actor: str,
    ) -> EvidenceReviewQueueData:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_evidence_review_cases
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND (:snapshot_id IS NULL OR snapshot_id=:snapshot_id)
                    ORDER BY created_at DESC, id DESC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "snapshot_id": snapshot_id},
            ).mappings().all()
            cases = [self._case_mapping(conn, row) for row in rows]
            return build_queue(project_id, snapshot_id, cases, actor)

    def _insert_case(self, conn: Any, **values: Any) -> None:
        actor = values.pop("actor")
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_review_cases (
                      id, tenant_id, project_id, snapshot_id, review_kind,
                      target_key, claim_id, citation_id, evidence_basis_sha256,
                      purpose, benchmark_version, status, consensus_label,
                      idempotency_key, request_sha256, version, created_by,
                      created_at, updated_at
                    ) VALUES (
                      :case_id, :tenant_id, :project_id, :snapshot_id, :review_kind,
                      :target_key, :claim_id, :citation_id, :evidence_basis_sha256,
                      :purpose, :benchmark_version, 'creating', NULL,
                      :idempotency_key, :request_sha256, 1, :created_by,
                      :created_at, :created_at
                    )
                    """
                ),
                {
                    **values,
                    "target_key": target_key(values["review_kind"], values["claim_id"], values["citation_id"]),
                    "created_by": actor,
                },
            )
        except Exception as exc:
            existing = conn.execute(
                text(
                    """
                    SELECT id FROM airank_evidence_review_cases
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND review_kind=:review_kind AND target_key=:target_key
                      AND evidence_basis_sha256=:evidence_basis_sha256
                      AND purpose=:purpose
                    """
                ),
                {**values, "target_key": target_key(values["review_kind"], values["claim_id"], values["citation_id"])},
            ).first()
            if existing:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_CASE_EXISTS", "details": {"case_id": str(existing[0])}}) from exc
            raise

    @staticmethod
    def _activate_case(conn: Any, case_id: str, review_id: str, at: datetime) -> None:
        conn.execute(
            text("UPDATE airank_evidence_review_cases SET status='awaiting_secondary', primary_review_id=:review_id, updated_at=:updated_at WHERE id=:case_id"),
            {"review_id": review_id, "updated_at": at, "case_id": case_id},
        )

    def _idempotent_case(self, conn: Any, tenant_id: str, project_id: str, key: str, request_hash: str, actor: str) -> Optional[EvidenceReviewCaseData]:
        row = conn.execute(
            text("SELECT * FROM airank_evidence_review_cases WHERE tenant_id=:tenant_id AND project_id=:project_id AND idempotency_key=:key"),
            {"tenant_id": tenant_id, "project_id": project_id, "key": key},
        ).mappings().first()
        if row is None:
            return None
        if str(row["request_sha256"]) != request_hash:
            raise StarletteHTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
        return self._load_case(conn, tenant_id, str(row["id"]), actor).model_copy(update={"idempotent_replay": True})

    @staticmethod
    def _latest_review_id(conn: Any, kind: str, tenant_id: str, claim_id: str, citation_id: Optional[str]) -> Optional[str]:
        if kind == "citation_support":
            row = conn.execute(
                text("SELECT id FROM airank_citation_support_reviews WHERE tenant_id=:tenant_id AND claim_id=:claim_id AND citation_id=:citation_id ORDER BY reviewed_at DESC, id DESC LIMIT 1"),
                {"tenant_id": tenant_id, "claim_id": claim_id, "citation_id": citation_id},
            ).first()
        else:
            row = conn.execute(
                text("SELECT id FROM airank_fact_accuracy_reviews WHERE tenant_id=:tenant_id AND claim_id=:claim_id ORDER BY reviewed_at DESC, id DESC LIMIT 1"),
                {"tenant_id": tenant_id, "claim_id": claim_id},
            ).first()
        return str(row[0]) if row else None

    def _clone_decision(self, conn: Any, case: Mapping[str, Any], primary: Mapping[str, Any], payload: EvidenceReviewDecisionRequest, actor: str, role: str, reviewed_at: datetime) -> str:
        kind = str(case["review_kind"])
        review_id = f"{'citation_review' if kind == 'citation_support' else 'fact_accuracy_review'}_{uuid4().hex}"
        previous = self._latest_review_id(conn, kind, str(case["tenant_id"]), str(case["claim_id"]), str(case["citation_id"]) if case.get("citation_id") else None)
        if kind == "citation_support":
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_support_reviews (
                      id, tenant_id, project_id, claim_id, citation_id, support_label,
                      evidence_grade, source_excerpt, source_content_sha256,
                      source_object_ref_id, source_capture_id, source_segment_id,
                      source_start, source_end, rationale, review_method, reviewed_by,
                      reviewed_at, review_case_id, reviewer_role,
                      supersedes_review_id, created_at
                    ) SELECT
                      :id, tenant_id, project_id, claim_id, citation_id, :label,
                      evidence_grade, source_excerpt, source_content_sha256,
                      source_object_ref_id, source_capture_id, source_segment_id,
                      source_start, source_end, :rationale, 'human', :reviewed_by,
                      :reviewed_at, review_case_id, :reviewer_role,
                      :supersedes_review_id, :created_at
                    FROM airank_citation_support_reviews
                    WHERE tenant_id=:tenant_id AND id=:primary_review_id
                    """
                ),
                {"id": review_id, "label": payload.label, "rationale": payload.rationale, "reviewed_by": actor, "reviewed_at": reviewed_at, "reviewer_role": role, "supersedes_review_id": previous, "created_at": reviewed_at, "tenant_id": case["tenant_id"], "primary_review_id": primary["id"]},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_fact_accuracy_reviews (
                      id, tenant_id, project_id, claim_id, verdict, evidence_grade,
                      fact_revision_id, knowledge_source_id, knowledge_segment_id,
                      fact_revision_sha256, source_content_sha256, quoted_text,
                      quoted_text_sha256, source_start, source_end, rationale,
                      review_method, reviewed_by, reviewed_at, review_case_id,
                      reviewer_role, supersedes_review_id, idempotency_key, created_at
                    ) SELECT
                      :id, tenant_id, project_id, claim_id, :label, evidence_grade,
                      fact_revision_id, knowledge_source_id, knowledge_segment_id,
                      fact_revision_sha256, source_content_sha256, quoted_text,
                      quoted_text_sha256, source_start, source_end, :rationale,
                      'human', :reviewed_by, :reviewed_at, review_case_id,
                      :reviewer_role, :supersedes_review_id, :idempotency_key, :created_at
                    FROM airank_fact_accuracy_reviews
                    WHERE tenant_id=:tenant_id AND id=:primary_review_id
                    """
                ),
                {"id": review_id, "label": payload.label, "rationale": payload.rationale, "reviewed_by": actor, "reviewed_at": reviewed_at, "reviewer_role": role, "supersedes_review_id": previous, "idempotency_key": f"{case['id']}:{role}", "created_at": reviewed_at, "tenant_id": case["tenant_id"], "primary_review_id": primary["id"]},
            )
        return review_id

    def _load_case(self, conn: Any, tenant_id: str, case_id: str, actor: str) -> EvidenceReviewCaseData:
        row = conn.execute(
            text("SELECT * FROM airank_evidence_review_cases WHERE tenant_id=:tenant_id AND id=:case_id"),
            {"tenant_id": tenant_id, "case_id": case_id},
        ).mappings().first()
        if row is None:
            raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_CASE_NOT_FOUND"})
        return case_data_from_mapping(self._case_mapping(conn, row), actor)

    def _case_mapping(self, conn: Any, row: Mapping[str, Any]) -> dict[str, Any]:
        return {**dict(row), "case_id": str(row["id"]), "decisions": self._decision_rows(conn, row)}

    @staticmethod
    def _decision_rows(conn: Any, case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        if str(case["review_kind"]) == "citation_support":
            return list(
                conn.execute(
                    text("SELECT id, reviewer_role, support_label AS label, evidence_grade, rationale, reviewed_by, reviewed_at FROM airank_citation_support_reviews WHERE tenant_id=:tenant_id AND review_case_id=:case_id ORDER BY reviewed_at, id"),
                    {"tenant_id": case["tenant_id"], "case_id": case["id"]},
                ).mappings().all()
            )
        return list(
            conn.execute(
                text("SELECT id, reviewer_role, verdict AS label, evidence_grade, rationale, reviewed_by, reviewed_at FROM airank_fact_accuracy_reviews WHERE tenant_id=:tenant_id AND review_case_id=:case_id ORDER BY reviewed_at, id"),
                {"tenant_id": case["tenant_id"], "case_id": case["id"]},
            ).mappings().all()
        )

    @staticmethod
    def _row_label(kind: str, row: Mapping[str, Any]) -> str:
        return str(row.get("label") or row.get("support_label") or row.get("verdict") or "")

    @staticmethod
    def _audit(conn: Any, tenant_id: str, project_id: str, case_id: str, event_type: str, actor: str, trace_id: str, payload: Mapping[str, Any], at: datetime) -> None:
        conn.execute(
            text(
                """
                INSERT INTO airank_audit_events (
                  id, tenant_id, project_id, event_type, entity_type,
                  entity_id, trace_id, payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :event_type, 'evidence_review_case',
                  :entity_id, :trace_id, :payload_json, :created_at
                )
                """
            ),
            {"id": f"audit_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id, "event_type": event_type, "entity_id": case_id, "trace_id": trace_id, "payload_json": json.dumps({**payload, "actor": actor}, ensure_ascii=False, sort_keys=True), "created_at": at},
        )


def decision_data(item: Any) -> EvidenceReviewDecisionData:
    if isinstance(item, Mapping):
        label = str(item.get("label") or item.get("support_label") or item.get("verdict") or "")
        return EvidenceReviewDecisionData(
            reviewer_role=str(item["reviewer_role"]),
            label=label,
            rationale=str(item["rationale"]),
            reviewed_by=str(item["reviewed_by"]),
            reviewed_at=citation_routes._utc_datetime(item["reviewed_at"]),
            review_id=str(item.get("id") or item.get("review_id")),
        )
    return EvidenceReviewDecisionData(
        reviewer_role=item.reviewer_role,
        label=review_label_value(item),
        rationale=item.rationale,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
        review_id=item.review_id,
    )


def case_data_from_mapping(case: Mapping[str, Any], actor: str) -> EvidenceReviewCaseData:
    decisions = [decision_data(item) for item in case.get("decisions", [])]
    status = str(case["status"])
    final = status in {"agreed", "adjudicated"}
    visible = decisions if final else [item for item in decisions if item.reviewed_by == actor]
    current = next((item.reviewer_role for item in decisions if item.reviewed_by == actor), None)
    next_action: str
    if status == "awaiting_secondary" and current is None:
        next_action = "submit_secondary"
    elif status == "disputed" and current is None:
        next_action = "adjudicate"
    elif final:
        next_action = "complete"
    else:
        next_action = "none"
    return EvidenceReviewCaseData(
        case_id=str(case.get("case_id") or case.get("id")),
        tenant_id=str(case["tenant_id"]),
        project_id=str(case["project_id"]),
        snapshot_id=str(case["snapshot_id"]),
        review_kind=str(case["review_kind"]),
        claim_id=str(case["claim_id"]),
        citation_id=str(case["citation_id"]) if case.get("citation_id") else None,
        evidence_basis_sha256=str(case["evidence_basis_sha256"]),
        purpose=str(case["purpose"]),
        benchmark_version=str(case["benchmark_version"]) if case.get("benchmark_version") else None,
        status=status,
        consensus_label=str(case["consensus_label"]) if case.get("consensus_label") else None,
        decision_count=len(decisions),
        current_actor_role=current,
        next_action=next_action,
        visible_decisions=visible,
        created_by=str(case["created_by"]),
        finalized_by=str(case["finalized_by"]) if case.get("finalized_by") else None,
        created_at=citation_routes._utc_datetime(case["created_at"]),
        finalized_at=citation_routes._utc_datetime(case["finalized_at"]) if case.get("finalized_at") else None,
        version=int(case["version"]),
    )


def pair_from_case(case: Mapping[str, Any]) -> IndependentReviewPair:
    decisions = [decision_data(item) for item in case.get("decisions", [])]
    primary = next((item.label for item in decisions if item.reviewer_role == "primary"), None)
    secondary = next((item.label for item in decisions if item.reviewer_role == "secondary"), None)
    adjudicator = next((item.label for item in decisions if item.reviewer_role == "adjudicator"), None)
    return IndependentReviewPair(
        case_id=str(case.get("case_id") or case.get("id")),
        review_kind=str(case["review_kind"]),
        primary_label=primary,
        secondary_label=secondary,
        status=str(case["status"]),
        adjudication_label=adjudicator,
    )


def build_queue(project_id: str, snapshot_id: Optional[str], cases: list[Mapping[str, Any]], actor: str) -> EvidenceReviewQueueData:
    production = tuple(pair_from_case(case) for case in cases if case["purpose"] == "production")
    benchmark = tuple(pair_from_case(case) for case in cases if case["purpose"] == "benchmark")
    return EvidenceReviewQueueData(
        project_id=project_id,
        snapshot_id=snapshot_id,
        cases=[case_data_from_mapping(case, actor) for case in cases],
        production_quality=metrics_data(production),
        benchmark_quality=metrics_data(benchmark),
    )


def build_repository() -> EvidenceReviewRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLEvidenceReviewRepository(database_url) if database_url else InMemoryEvidenceReviewRepository()


EVIDENCE_REVIEW_REPOSITORY: EvidenceReviewRepository = build_repository()


@router.post(
    "/projects/{project_id}/evidence-review-cases/citation-support",
    response_model=EvidenceReviewCaseResponse,
    status_code=201,
)
def create_citation_review_case(
    project_id: str,
    payload: CitationReviewCaseCreateRequest,
    idempotency_key: str = Header(min_length=8, max_length=160, alias="Idempotency-Key"),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> EvidenceReviewCaseResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor(payload.review.reviewed_by, authenticated_actor)
    data = EVIDENCE_REVIEW_REPOSITORY.create_citation_case(
        tenant_id, project_id, payload, idempotency_key, actor, meta["trace_id"]
    )
    return EvidenceReviewCaseResponse(data=data, meta=meta)


@router.post(
    "/projects/{project_id}/evidence-review-cases/fact-accuracy",
    response_model=EvidenceReviewCaseResponse,
    status_code=201,
)
def create_fact_review_case(
    project_id: str,
    payload: FactReviewCaseCreateRequest,
    idempotency_key: str = Header(min_length=8, max_length=160, alias="Idempotency-Key"),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> EvidenceReviewCaseResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor(payload.review.reviewed_by, authenticated_actor)
    data = EVIDENCE_REVIEW_REPOSITORY.create_fact_case(
        tenant_id, project_id, payload, idempotency_key, actor, meta["trace_id"]
    )
    return EvidenceReviewCaseResponse(data=data, meta=meta)


@router.post(
    "/evidence-review-cases/{case_id}/decisions",
    response_model=EvidenceReviewCaseResponse,
    status_code=201,
)
def submit_evidence_review_decision(
    case_id: str,
    payload: EvidenceReviewDecisionRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> EvidenceReviewCaseResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor(payload.reviewed_by, authenticated_actor)
    data = EVIDENCE_REVIEW_REPOSITORY.submit_decision(
        tenant_id,
        case_id,
        payload.model_copy(update={"reviewed_by": actor}),
        actor,
        meta["trace_id"],
    )
    return EvidenceReviewCaseResponse(data=data, meta=meta)


@router.get(
    "/projects/{project_id}/evidence-review-cases",
    response_model=EvidenceReviewQueueResponse,
)
def list_evidence_review_cases(
    project_id: str,
    snapshot_id: Optional[str] = Query(default=None, min_length=1, max_length=64),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> EvidenceReviewQueueResponse:
    actor = trusted_actor("console-reviewer", authenticated_actor)
    return EvidenceReviewQueueResponse(
        data=EVIDENCE_REVIEW_REPOSITORY.list_cases(
            tenant_id, project_id, snapshot_id, actor
        ),
        meta=response_meta(trace_id),
    )


def review_label_value(review: Any) -> str:
    return str(
        getattr(review, "support_label", None)
        or getattr(review, "verdict", "")
    )

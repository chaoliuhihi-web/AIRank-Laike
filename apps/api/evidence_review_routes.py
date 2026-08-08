from __future__ import annotations

from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from datetime import datetime, timedelta, timezone
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
DEFAULT_REVIEW_ASSIGNMENT_LEASE_SECONDS = 15 * 60
DEFAULT_SECONDARY_REVIEW_SLA_SECONDS = 24 * 60 * 60
DEFAULT_ADJUDICATION_REVIEW_SLA_SECONDS = 4 * 60 * 60
DEFAULT_REVIEW_DUE_SOON_SECONDS = 60 * 60


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


class EvidenceReviewAssignmentClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_case_version: Optional[int] = Field(default=None, ge=1)


class EvidenceReviewAssignmentHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class EvidenceReviewAssignmentReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=512)


class EvidenceReviewAssignmentData(BaseModel):
    assignment_id: Optional[str]
    case_id: str
    reviewer_role: Literal["secondary", "adjudicator"]
    state: Literal[
        "unassigned",
        "assigned_to_me",
        "assigned_to_other",
        "expired",
        "completed",
        "released",
    ]
    owned_by_current_actor: bool
    sla_state: Literal["on_track", "due_soon", "overdue"]
    action_available_at: datetime
    due_at: datetime
    assigned_at: Optional[datetime]
    lease_expires_at: Optional[datetime]
    last_heartbeat_at: Optional[datetime]
    completed_at: Optional[datetime]
    released_at: Optional[datetime]
    release_reason: Optional[str]
    version: Optional[int]
    idempotent_replay: bool = False


class EvidenceReviewAssignmentResponse(BaseModel):
    data: EvidenceReviewAssignmentData
    meta: dict[str, str]


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
    assignment: Optional[EvidenceReviewAssignmentData]
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


class EvidenceReviewInboxData(BaseModel):
    project_id: str
    cases: list[EvidenceReviewCaseData]
    actionable_count: int
    awaiting_secondary_count: int
    adjudication_count: int
    assigned_to_me_count: int
    unassigned_count: int
    overdue_count: int
    limit: int
    next_cursor: Optional[str]


class EvidenceReviewInboxResponse(BaseModel):
    data: EvidenceReviewInboxData
    meta: dict[str, str]


class EvidenceReviewEscalationData(BaseModel):
    event_id: str
    case_id: str
    reviewer_role: Literal["secondary", "adjudicator"]
    due_at: datetime
    escalated_at: datetime
    overdue_seconds: int = Field(ge=0)
    assignment_state: Literal["unassigned", "assigned", "expired"]
    outbox_status: Literal["pending", "published", "failed", "canceled"]
    external_delivery_verified: Literal[False] = False


class EvidenceReviewEscalationListData(BaseModel):
    project_id: str
    escalation_count: int
    pending_count: int
    published_count: int
    failed_count: int
    canceled_count: int
    escalations: list[EvidenceReviewEscalationData]


class EvidenceReviewEscalationListResponse(BaseModel):
    data: EvidenceReviewEscalationListData
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

    def list_inbox(
        self,
        tenant_id: str,
        project_id: str,
        actor: str,
        limit: int,
        cursor: Optional[str],
    ) -> EvidenceReviewInboxData: ...

    def claim_assignment(
        self,
        tenant_id: str,
        case_id: str,
        payload: EvidenceReviewAssignmentClaimRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData: ...

    def heartbeat_assignment(
        self,
        tenant_id: str,
        assignment_id: str,
        payload: EvidenceReviewAssignmentHeartbeatRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData: ...

    def release_assignment(
        self,
        tenant_id: str,
        assignment_id: str,
        payload: EvidenceReviewAssignmentReleaseRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData: ...


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


def bounded_env_seconds(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def review_assignment_lease_seconds() -> int:
    return bounded_env_seconds(
        "AIRANK_EVIDENCE_REVIEW_LEASE_SECONDS",
        DEFAULT_REVIEW_ASSIGNMENT_LEASE_SECONDS,
        60,
        4 * 60 * 60,
    )


def review_sla_seconds(role: str) -> int:
    if role == "adjudicator":
        return bounded_env_seconds(
            "AIRANK_EVIDENCE_REVIEW_ADJUDICATION_SLA_SECONDS",
            DEFAULT_ADJUDICATION_REVIEW_SLA_SECONDS,
            5 * 60,
            14 * 24 * 60 * 60,
        )
    return bounded_env_seconds(
        "AIRANK_EVIDENCE_REVIEW_SECONDARY_SLA_SECONDS",
        DEFAULT_SECONDARY_REVIEW_SLA_SECONDS,
        5 * 60,
        30 * 24 * 60 * 60,
    )


def review_due_soon_seconds() -> int:
    return bounded_env_seconds(
        "AIRANK_EVIDENCE_REVIEW_DUE_SOON_SECONDS",
        DEFAULT_REVIEW_DUE_SOON_SECONDS,
        60,
        24 * 60 * 60,
    )


def review_action_role(case: Mapping[str, Any]) -> Optional[Literal["secondary", "adjudicator"]]:
    status = str(case["status"])
    if status == "awaiting_secondary":
        return "secondary"
    if status == "disputed":
        return "adjudicator"
    return None


def review_action_available_at(case: Mapping[str, Any]) -> datetime:
    value = case.get("updated_at") if str(case["status"]) == "disputed" else case.get("created_at")
    return citation_routes._utc_datetime(value or case["created_at"])


def review_sla_state(due_at: datetime, at: datetime) -> Literal["on_track", "due_soon", "overdue"]:
    if due_at <= at:
        return "overdue"
    if due_at - at <= timedelta(seconds=review_due_soon_seconds()):
        return "due_soon"
    return "on_track"


def assignment_data_from_mapping(
    case: Mapping[str, Any],
    assignment: Optional[Mapping[str, Any]],
    actor: str,
    *,
    at: Optional[datetime] = None,
    idempotent_replay: bool = False,
) -> EvidenceReviewAssignmentData:
    at = at or now_utc()
    role = str(assignment["reviewer_role"]) if assignment is not None else review_action_role(case)
    if role not in {"secondary", "adjudicator"}:
        raise ValueError("assignment view requires an actionable reviewer role")
    action_available_at = (
        citation_routes._utc_datetime(assignment["action_available_at"])
        if assignment is not None
        else review_action_available_at(case)
    )
    due_at = (
        citation_routes._utc_datetime(assignment["due_at"])
        if assignment is not None
        else action_available_at + timedelta(seconds=review_sla_seconds(role))
    )
    state: str = "unassigned"
    owned = False
    if assignment is not None:
        status = str(assignment["status"])
        lease_expires_at = citation_routes._utc_datetime(assignment["lease_expires_at"])
        assigned_to = str(assignment["assigned_to"])
        if status == "active" and lease_expires_at <= at:
            state = "expired"
        elif status == "active" and assigned_to == actor:
            state = "assigned_to_me"
            owned = True
        elif status == "active":
            state = "assigned_to_other"
        elif status in {"completed", "released", "expired"}:
            state = status
    return EvidenceReviewAssignmentData(
        assignment_id=(str(assignment.get("id") or assignment.get("assignment_id")) if assignment is not None else None),
        case_id=str(case.get("case_id") or case.get("id")),
        reviewer_role=role,
        state=state,
        owned_by_current_actor=owned,
        sla_state=review_sla_state(due_at, at),
        action_available_at=action_available_at,
        due_at=due_at,
        assigned_at=(citation_routes._utc_datetime(assignment["assigned_at"]) if assignment is not None else None),
        lease_expires_at=(citation_routes._utc_datetime(assignment["lease_expires_at"]) if assignment is not None else None),
        last_heartbeat_at=(citation_routes._utc_datetime(assignment["last_heartbeat_at"]) if assignment is not None else None),
        completed_at=(citation_routes._utc_datetime(assignment["completed_at"]) if assignment is not None and assignment.get("completed_at") else None),
        released_at=(citation_routes._utc_datetime(assignment["released_at"]) if assignment is not None and assignment.get("released_at") else None),
        release_reason=(str(assignment["release_reason"]) if assignment is not None and assignment.get("release_reason") else None),
        version=(int(assignment["version"]) if assignment is not None else None),
        idempotent_replay=idempotent_replay,
    )


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
        self.assignments: dict[str, dict[str, Any]] = {}
        self.assignment_events: list[dict[str, Any]] = []

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
            reviewed_at = now_utc()
            assignment, _ = self._ensure_assignment(
                case, actor, trace_id, reviewed_at, expected_case_version=None
            )
            primary = case["decisions"][0]
            role = "secondary" if case["status"] == "awaiting_secondary" else "adjudicator"
            review = self._clone_in_memory_review(case, primary, payload, actor, role, trace_id)
            case["decisions"].append(review)
            case["version"] += 1
            case["updated_at"] = reviewed_at
            if role == "secondary":
                if review_label_value(primary) == payload.label:
                    case.update(
                        status="agreed",
                        consensus_label=payload.label,
                        finalized_by=actor,
                        finalized_at=reviewed_at,
                    )
                else:
                    case["status"] = "disputed"
            else:
                case.update(
                    status="adjudicated",
                    consensus_label=payload.label,
                    finalized_by=actor,
                    finalized_at=reviewed_at,
                )
            self._complete_assignment(assignment, actor, trace_id, reviewed_at)
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
            return build_queue(
                project_id,
                snapshot_id,
                [self._case_with_assignment(value) for value in cases],
                actor,
            )

    def list_inbox(
        self,
        tenant_id: str,
        project_id: str,
        actor: str,
        limit: int,
        cursor: Optional[str],
    ) -> EvidenceReviewInboxData:
        cursor_key = decode_review_inbox_cursor(cursor) if cursor else None
        with self.lock:
            at = now_utc()
            actionable = []
            rendered: dict[str, EvidenceReviewCaseData] = {}
            for value in self.cases.values():
                if value["tenant_id"] != tenant_id or value["project_id"] != project_id:
                    continue
                mapped = self._case_with_assignment(value, at=at)
                data = case_data_from_mapping(mapped, actor, at=at)
                if data.next_action not in {"submit_secondary", "adjudicate"}:
                    continue
                actionable.append(value)
                rendered[str(value["case_id"])] = data
            actionable.sort(key=review_inbox_cursor_key)
            page_candidates = [
                value
                for value in actionable
                if cursor_key is None or review_inbox_cursor_key(value) > cursor_key
            ]
            page = page_candidates[: limit + 1]
            has_more = len(page) > limit
            returned = page[:limit]
            returned_data = [rendered[str(value["case_id"])] for value in returned]
            return EvidenceReviewInboxData(
                project_id=project_id,
                cases=returned_data,
                actionable_count=len(actionable),
                awaiting_secondary_count=sum(
                    str(value["status"]) == "awaiting_secondary" for value in actionable
                ),
                adjudication_count=sum(
                    str(value["status"]) == "disputed" for value in actionable
                ),
                assigned_to_me_count=sum(
                    item.assignment is not None
                    and item.assignment.state == "assigned_to_me"
                    for item in rendered.values()
                ),
                unassigned_count=sum(
                    item.assignment is not None
                    and item.assignment.state in {"unassigned", "expired"}
                    for item in rendered.values()
                ),
                overdue_count=sum(
                    item.assignment is not None
                    and item.assignment.sla_state == "overdue"
                    for item in rendered.values()
                ),
                limit=limit,
                next_cursor=(encode_review_inbox_cursor(returned[-1]) if has_more else None),
            )

    def claim_assignment(
        self,
        tenant_id: str,
        case_id: str,
        payload: EvidenceReviewAssignmentClaimRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData:
        with self.lock:
            case = self.cases.get(case_id)
            if case is None or case["tenant_id"] != tenant_id:
                raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_CASE_NOT_FOUND"})
            assignment, replay = self._ensure_assignment(
                case,
                actor,
                trace_id,
                now_utc(),
                expected_case_version=payload.expected_case_version,
            )
            return assignment_data_from_mapping(
                case, assignment, actor, idempotent_replay=replay
            )

    def heartbeat_assignment(
        self,
        tenant_id: str,
        assignment_id: str,
        payload: EvidenceReviewAssignmentHeartbeatRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData:
        with self.lock:
            assignment = self.assignments.get(assignment_id)
            if assignment is None or assignment["tenant_id"] != tenant_id:
                raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_NOT_FOUND"})
            case = self.cases[str(assignment["case_id"])]
            at = now_utc()
            self._validate_assignment_owner(assignment, actor, payload.expected_version)
            if citation_routes._utc_datetime(assignment["lease_expires_at"]) <= at:
                self._expire_assignment(assignment, actor, trace_id, at)
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED"})
            assignment["last_heartbeat_at"] = at
            assignment["lease_expires_at"] = at + timedelta(seconds=review_assignment_lease_seconds())
            assignment["version"] += 1
            assignment["updated_at"] = at
            self._append_assignment_event(assignment, "heartbeat", actor, trace_id, at)
            return assignment_data_from_mapping(case, assignment, actor)

    def release_assignment(
        self,
        tenant_id: str,
        assignment_id: str,
        payload: EvidenceReviewAssignmentReleaseRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData:
        with self.lock:
            assignment = self.assignments.get(assignment_id)
            if assignment is None or assignment["tenant_id"] != tenant_id:
                raise StarletteHTTPException(404, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_NOT_FOUND"})
            case = self.cases[str(assignment["case_id"])]
            at = now_utc()
            self._validate_assignment_owner(assignment, actor, payload.expected_version)
            if citation_routes._utc_datetime(assignment["lease_expires_at"]) <= at:
                self._expire_assignment(assignment, actor, trace_id, at)
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED"})
            assignment.update(
                status="released",
                released_at=at,
                release_reason=payload.reason,
                version=int(assignment["version"]) + 1,
                updated_at=at,
            )
            self._append_assignment_event(assignment, "released", actor, trace_id, at)
            return assignment_data_from_mapping(case, assignment, actor)

    def _case_with_assignment(
        self, case: Mapping[str, Any], *, at: Optional[datetime] = None
    ) -> dict[str, Any]:
        mapped = dict(case)
        role = review_action_role(case)
        if role is None:
            mapped["assignment"] = None
            return mapped
        candidates = [
            item
            for item in self.assignments.values()
            if item["tenant_id"] == case["tenant_id"]
            and item["case_id"] == case["case_id"]
            and item["reviewer_role"] == role
        ]
        candidates.sort(key=lambda item: (item["assigned_at"], item["id"]), reverse=True)
        current = next((item for item in candidates if item["status"] == "active"), None)
        if current is None and candidates and candidates[0]["status"] == "expired":
            current = candidates[0]
        mapped["assignment"] = current
        return mapped

    def _ensure_assignment(
        self,
        case: dict[str, Any],
        actor: str,
        trace_id: str,
        at: datetime,
        *,
        expected_case_version: Optional[int],
    ) -> tuple[dict[str, Any], bool]:
        if expected_case_version is not None and int(case["version"]) != expected_case_version:
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_VERSION_CONFLICT"})
        role = review_action_role(case)
        if role is None:
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_CASE_FINAL"})
        if any(item.reviewed_by == actor for item in case["decisions"]):
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN"})
        candidates = [
            item
            for item in self.assignments.values()
            if item["tenant_id"] == case["tenant_id"]
            and item["case_id"] == case["case_id"]
            and item["reviewer_role"] == role
            and item["status"] == "active"
        ]
        candidates.sort(key=lambda item: (item["assigned_at"], item["id"]), reverse=True)
        current = candidates[0] if candidates else None
        if current is not None and citation_routes._utc_datetime(current["lease_expires_at"]) <= at:
            self._expire_assignment(current, actor, trace_id, at)
            current = None
        if current is not None:
            if current["assigned_to"] != actor:
                raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_CONFLICT"})
            return current, True
        action_available_at = review_action_available_at(case)
        assignment_id = f"evidence_review_assignment_{uuid4().hex}"
        assignment = {
            "id": assignment_id,
            "tenant_id": case["tenant_id"],
            "project_id": case["project_id"],
            "case_id": case["case_id"],
            "reviewer_role": role,
            "assigned_to": actor,
            "status": "active",
            "action_available_at": action_available_at,
            "assigned_at": at,
            "due_at": action_available_at + timedelta(seconds=review_sla_seconds(role)),
            "lease_expires_at": at + timedelta(seconds=review_assignment_lease_seconds()),
            "last_heartbeat_at": at,
            "completed_at": None,
            "released_at": None,
            "release_reason": None,
            "version": 1,
            "created_at": at,
            "updated_at": at,
        }
        self.assignments[assignment_id] = assignment
        self._append_assignment_event(assignment, "claimed", actor, trace_id, at)
        return assignment, False

    def _validate_assignment_owner(
        self, assignment: Mapping[str, Any], actor: str, expected_version: int
    ) -> None:
        if assignment["status"] != "active":
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_NOT_ACTIVE"})
        if assignment["assigned_to"] != actor:
            raise StarletteHTTPException(403, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_OWNER_FORBIDDEN"})
        if int(assignment["version"]) != expected_version:
            raise StarletteHTTPException(409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_VERSION_CONFLICT"})

    def _expire_assignment(
        self, assignment: dict[str, Any], actor: str, trace_id: str, at: datetime
    ) -> None:
        assignment.update(
            status="expired",
            version=int(assignment["version"]) + 1,
            updated_at=at,
        )
        self._append_assignment_event(assignment, "expired", actor, trace_id, at)

    def _complete_assignment(
        self, assignment: dict[str, Any], actor: str, trace_id: str, at: datetime
    ) -> None:
        assignment.update(
            status="completed",
            completed_at=at,
            version=int(assignment["version"]) + 1,
            updated_at=at,
        )
        self._append_assignment_event(assignment, "completed", actor, trace_id, at)

    def _append_assignment_event(
        self,
        assignment: Mapping[str, Any],
        event_type: str,
        actor: str,
        trace_id: str,
        at: datetime,
    ) -> None:
        self.assignment_events.append(
            {
                "id": f"review_assignment_event_{uuid4().hex}",
                "tenant_id": assignment["tenant_id"],
                "project_id": assignment["project_id"],
                "case_id": assignment["case_id"],
                "assignment_id": assignment["id"],
                "event_type": event_type,
                "assignment_version": assignment["version"],
                "actor": actor,
                "trace_id": trace_id,
                "created_at": at,
            }
        )

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
            "updated_at": created_at,
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

    def _case_data(self, case: Mapping[str, Any], actor: str) -> EvidenceReviewCaseData:
        return case_data_from_mapping(self._case_with_assignment(case), actor)

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
            assignment, _ = self._ensure_assignment(
                conn,
                case,
                actor,
                trace_id,
                reviewed_at,
                expected_case_version=None,
                decisions=decisions,
            )
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
            self._complete_assignment(conn, assignment, actor, trace_id, reviewed_at)
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

    def list_inbox(
        self,
        tenant_id: str,
        project_id: str,
        actor: str,
        limit: int,
        cursor: Optional[str],
    ) -> EvidenceReviewInboxData:
        cursor_key = decode_review_inbox_cursor(cursor) if cursor else None
        as_of = now_utc()
        eligibility = """
          c.status IN ('awaiting_secondary', 'disputed')
          AND NOT EXISTS (
            SELECT 1 FROM airank_citation_support_reviews citation_review
            WHERE citation_review.tenant_id=c.tenant_id
              AND citation_review.review_case_id=c.id
              AND citation_review.reviewed_by=:actor
          )
          AND NOT EXISTS (
            SELECT 1 FROM airank_fact_accuracy_reviews fact_review
            WHERE fact_review.tenant_id=c.tenant_id
              AND fact_review.review_case_id=c.id
              AND fact_review.reviewed_by=:actor
          )
          AND (
            assignment.id IS NULL
            OR assignment.assigned_to=:actor
            OR assignment.lease_expires_at<=:as_of
          )
        """
        cursor_clause = ""
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "actor": actor,
            "as_of": as_of,
            "row_limit": limit + 1,
            "secondary_overdue_before": as_of
            - timedelta(seconds=review_sla_seconds("secondary")),
            "adjudication_overdue_before": as_of
            - timedelta(seconds=review_sla_seconds("adjudicator")),
        }
        if cursor_key is not None:
            cursor_clause = """
              AND (
                (CASE WHEN c.status='disputed' THEN 0 ELSE 1 END) > :cursor_priority
                OR (
                  (CASE WHEN c.status='disputed' THEN 0 ELSE 1 END) = :cursor_priority
                  AND c.created_at > :cursor_created_at
                )
                OR (
                  (CASE WHEN c.status='disputed' THEN 0 ELSE 1 END) = :cursor_priority
                  AND c.created_at = :cursor_created_at
                  AND c.id > :cursor_case_id
                )
              )
            """
            params.update(
                cursor_priority=cursor_key[0],
                cursor_created_at=datetime.fromtimestamp(
                    cursor_key[1] / 1_000_000, tz=timezone.utc
                ).replace(tzinfo=None),
                cursor_case_id=cursor_key[2],
            )
        with self.engine.begin() as conn:
            counts = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS actionable_count,
                           SUM(CASE WHEN c.status='awaiting_secondary' THEN 1 ELSE 0 END)
                             AS awaiting_secondary_count,
                           SUM(CASE WHEN c.status='disputed' THEN 1 ELSE 0 END)
                             AS adjudication_count,
                           SUM(CASE WHEN assignment.id IS NOT NULL
                                         AND assignment.assigned_to=:actor
                                         AND assignment.lease_expires_at>:as_of
                                    THEN 1 ELSE 0 END) AS assigned_to_me_count,
                           SUM(CASE WHEN assignment.id IS NULL
                                         OR assignment.lease_expires_at<=:as_of
                                    THEN 1 ELSE 0 END) AS unassigned_count,
                           SUM(CASE
                                 WHEN c.status='awaiting_secondary'
                                      AND c.created_at<=:secondary_overdue_before THEN 1
                                 WHEN c.status='disputed'
                                      AND c.updated_at<=:adjudication_overdue_before THEN 1
                                 ELSE 0
                               END) AS overdue_count
                    FROM airank_evidence_review_cases c
                    LEFT JOIN airank_evidence_review_assignments assignment
                      ON assignment.tenant_id=c.tenant_id
                     AND assignment.case_id=c.id
                     AND assignment.status='active'
                     AND assignment.reviewer_role=(
                       CASE WHEN c.status='disputed' THEN 'adjudicator' ELSE 'secondary' END
                     )
                    WHERE c.tenant_id=:tenant_id AND c.project_id=:project_id
                      AND {eligibility}
                    """
                ),
                params,
            ).mappings().one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT c.* FROM airank_evidence_review_cases c
                    LEFT JOIN airank_evidence_review_assignments assignment
                      ON assignment.tenant_id=c.tenant_id
                     AND assignment.case_id=c.id
                     AND assignment.status='active'
                     AND assignment.reviewer_role=(
                       CASE WHEN c.status='disputed' THEN 'adjudicator' ELSE 'secondary' END
                     )
                    WHERE c.tenant_id=:tenant_id AND c.project_id=:project_id
                      AND {eligibility}
                      {cursor_clause}
                    ORDER BY CASE WHEN c.status='disputed' THEN 0 ELSE 1 END,
                             c.created_at ASC, c.id ASC
                    LIMIT :row_limit
                    """
                ),
                params,
            ).mappings().all()
            has_more = len(rows) > limit
            returned = rows[:limit]
            cases = [self._case_mapping(conn, row) for row in returned]
            return EvidenceReviewInboxData(
                project_id=project_id,
                cases=[case_data_from_mapping(case, actor, at=as_of) for case in cases],
                actionable_count=int(counts["actionable_count"] or 0),
                awaiting_secondary_count=int(counts["awaiting_secondary_count"] or 0),
                adjudication_count=int(counts["adjudication_count"] or 0),
                assigned_to_me_count=int(counts["assigned_to_me_count"] or 0),
                unassigned_count=int(counts["unassigned_count"] or 0),
                overdue_count=int(counts["overdue_count"] or 0),
                limit=limit,
                next_cursor=(
                    encode_review_inbox_cursor(returned[-1]) if has_more else None
                ),
            )

    def claim_assignment(
        self,
        tenant_id: str,
        case_id: str,
        payload: EvidenceReviewAssignmentClaimRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData:
        at = now_utc()
        with self.engine.begin() as conn:
            case = self._locked_case(conn, tenant_id, case_id)
            assignment, replay = self._ensure_assignment(
                conn,
                case,
                actor,
                trace_id,
                at,
                expected_case_version=payload.expected_case_version,
            )
            return assignment_data_from_mapping(
                {**dict(case), "case_id": str(case["id"])},
                assignment,
                actor,
                at=at,
                idempotent_replay=replay,
            )

    def heartbeat_assignment(
        self,
        tenant_id: str,
        assignment_id: str,
        payload: EvidenceReviewAssignmentHeartbeatRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData:
        at = now_utc()
        expired = False
        result: Optional[EvidenceReviewAssignmentData] = None
        with self.engine.begin() as conn:
            assignment = self._locked_assignment(conn, tenant_id, assignment_id)
            case = self._locked_case(conn, tenant_id, str(assignment["case_id"]))
            self._validate_assignment_owner(assignment, actor, payload.expected_version)
            if citation_routes._utc_datetime(assignment["lease_expires_at"]) <= at:
                assignment = self._expire_assignment(conn, assignment, actor, trace_id, at)
                expired = True
            else:
                next_version = int(assignment["version"]) + 1
                conn.execute(
                    text(
                        """
                        UPDATE airank_evidence_review_assignments
                        SET last_heartbeat_at=:at, lease_expires_at=:lease_expires_at,
                            version=:version, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:assignment_id
                        """
                    ),
                    {
                        "at": at,
                        "lease_expires_at": at
                        + timedelta(seconds=review_assignment_lease_seconds()),
                        "version": next_version,
                        "tenant_id": tenant_id,
                        "assignment_id": assignment_id,
                    },
                )
                assignment = self._assignment_row(conn, tenant_id, assignment_id)
                self._insert_assignment_event(
                    conn, assignment, "heartbeat", actor, trace_id, at
                )
                self._audit(
                    conn,
                    tenant_id,
                    str(assignment["project_id"]),
                    str(assignment["case_id"]),
                    "evidence_review.assignment_heartbeat",
                    actor,
                    trace_id,
                    {"assignment_id": assignment_id, "version": next_version},
                    at,
                )
            result = assignment_data_from_mapping(
                {**dict(case), "case_id": str(case["id"])}, assignment, actor, at=at
            )
        if expired:
            raise StarletteHTTPException(
                409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED"}
            )
        assert result is not None
        return result

    def release_assignment(
        self,
        tenant_id: str,
        assignment_id: str,
        payload: EvidenceReviewAssignmentReleaseRequest,
        actor: str,
        trace_id: str,
    ) -> EvidenceReviewAssignmentData:
        at = now_utc()
        expired = False
        result: Optional[EvidenceReviewAssignmentData] = None
        with self.engine.begin() as conn:
            assignment = self._locked_assignment(conn, tenant_id, assignment_id)
            case = self._locked_case(conn, tenant_id, str(assignment["case_id"]))
            self._validate_assignment_owner(assignment, actor, payload.expected_version)
            if citation_routes._utc_datetime(assignment["lease_expires_at"]) <= at:
                assignment = self._expire_assignment(conn, assignment, actor, trace_id, at)
                expired = True
            else:
                next_version = int(assignment["version"]) + 1
                conn.execute(
                    text(
                        """
                        UPDATE airank_evidence_review_assignments
                        SET status='released', released_at=:at, release_reason=:reason,
                            version=:version, updated_at=:at
                        WHERE tenant_id=:tenant_id AND id=:assignment_id
                        """
                    ),
                    {
                        "at": at,
                        "reason": payload.reason,
                        "version": next_version,
                        "tenant_id": tenant_id,
                        "assignment_id": assignment_id,
                    },
                )
                assignment = self._assignment_row(conn, tenant_id, assignment_id)
                self._insert_assignment_event(
                    conn,
                    assignment,
                    "released",
                    actor,
                    trace_id,
                    at,
                    {"reason": payload.reason},
                )
                self._audit(
                    conn,
                    tenant_id,
                    str(assignment["project_id"]),
                    str(assignment["case_id"]),
                    "evidence_review.assignment_released",
                    actor,
                    trace_id,
                    {"assignment_id": assignment_id, "reason": payload.reason},
                    at,
                )
            result = assignment_data_from_mapping(
                {**dict(case), "case_id": str(case["id"])}, assignment, actor, at=at
            )
        if expired:
            raise StarletteHTTPException(
                409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED"}
            )
        assert result is not None
        return result

    def _locked_case(
        self, conn: Any, tenant_id: str, case_id: str
    ) -> Mapping[str, Any]:
        lock_suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        row = conn.execute(
            text(
                f"SELECT * FROM airank_evidence_review_cases "
                f"WHERE tenant_id=:tenant_id AND id=:case_id{lock_suffix}"
            ),
            {"tenant_id": tenant_id, "case_id": case_id},
        ).mappings().first()
        if row is None:
            raise StarletteHTTPException(
                404, detail={"code": "EVIDENCE_REVIEW_CASE_NOT_FOUND"}
            )
        return row

    def _locked_assignment(
        self, conn: Any, tenant_id: str, assignment_id: str
    ) -> Mapping[str, Any]:
        lock_suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        row = conn.execute(
            text(
                f"SELECT * FROM airank_evidence_review_assignments "
                f"WHERE tenant_id=:tenant_id AND id=:assignment_id{lock_suffix}"
            ),
            {"tenant_id": tenant_id, "assignment_id": assignment_id},
        ).mappings().first()
        if row is None:
            raise StarletteHTTPException(
                404, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_NOT_FOUND"}
            )
        return row

    @staticmethod
    def _assignment_row(
        conn: Any, tenant_id: str, assignment_id: str
    ) -> Mapping[str, Any]:
        row = conn.execute(
            text(
                "SELECT * FROM airank_evidence_review_assignments "
                "WHERE tenant_id=:tenant_id AND id=:assignment_id"
            ),
            {"tenant_id": tenant_id, "assignment_id": assignment_id},
        ).mappings().one()
        return row

    def _ensure_assignment(
        self,
        conn: Any,
        case: Mapping[str, Any],
        actor: str,
        trace_id: str,
        at: datetime,
        *,
        expected_case_version: Optional[int],
        decisions: Optional[list[Mapping[str, Any]]] = None,
    ) -> tuple[Mapping[str, Any], bool]:
        if expected_case_version is not None and int(case["version"]) != expected_case_version:
            raise StarletteHTTPException(
                409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_VERSION_CONFLICT"}
            )
        role = review_action_role(case)
        if role is None:
            raise StarletteHTTPException(
                409, detail={"code": "EVIDENCE_REVIEW_CASE_FINAL"}
            )
        decisions = decisions if decisions is not None else self._decision_rows(conn, case)
        if any(str(item["reviewed_by"]) == actor for item in decisions):
            raise StarletteHTTPException(
                409, detail={"code": "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN"}
            )
        lock_suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        current = conn.execute(
            text(
                "SELECT * FROM airank_evidence_review_assignments "
                "WHERE tenant_id=:tenant_id AND case_id=:case_id "
                "AND reviewer_role=:reviewer_role AND status='active' "
                f"ORDER BY assigned_at DESC, id DESC LIMIT 1{lock_suffix}"
            ),
            {
                "tenant_id": case["tenant_id"],
                "case_id": case["id"],
                "reviewer_role": role,
            },
        ).mappings().first()
        if current is not None and citation_routes._utc_datetime(current["lease_expires_at"]) <= at:
            self._expire_assignment(conn, current, actor, trace_id, at)
            current = None
        if current is not None:
            if str(current["assigned_to"]) != actor:
                raise StarletteHTTPException(
                    409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_CONFLICT"}
                )
            return current, True
        action_available_at = review_action_available_at(case)
        assignment_id = f"evidence_review_assignment_{uuid4().hex}"
        conn.execute(
            text(
                """
                INSERT INTO airank_evidence_review_assignments (
                  id, tenant_id, project_id, case_id, reviewer_role, assigned_to,
                  status, action_available_at, assigned_at, due_at,
                  lease_expires_at, last_heartbeat_at, version, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :case_id, :reviewer_role, :assigned_to,
                  'active', :action_available_at, :assigned_at, :due_at,
                  :lease_expires_at, :last_heartbeat_at, 1, :created_at, :updated_at
                )
                """
            ),
            {
                "id": assignment_id,
                "tenant_id": case["tenant_id"],
                "project_id": case["project_id"],
                "case_id": case["id"],
                "reviewer_role": role,
                "assigned_to": actor,
                "action_available_at": action_available_at,
                "assigned_at": at,
                "due_at": action_available_at
                + timedelta(seconds=review_sla_seconds(role)),
                "lease_expires_at": at
                + timedelta(seconds=review_assignment_lease_seconds()),
                "last_heartbeat_at": at,
                "created_at": at,
                "updated_at": at,
            },
        )
        assignment = self._assignment_row(
            conn, str(case["tenant_id"]), assignment_id
        )
        self._insert_assignment_event(
            conn, assignment, "claimed", actor, trace_id, at
        )
        self._audit(
            conn,
            str(case["tenant_id"]),
            str(case["project_id"]),
            str(case["id"]),
            "evidence_review.assignment_claimed",
            actor,
            trace_id,
            {
                "assignment_id": assignment_id,
                "reviewer_role": role,
                "due_at": assignment["due_at"].isoformat(),
                "lease_expires_at": assignment["lease_expires_at"].isoformat(),
            },
            at,
        )
        return assignment, False

    @staticmethod
    def _validate_assignment_owner(
        assignment: Mapping[str, Any], actor: str, expected_version: int
    ) -> None:
        if str(assignment["status"]) != "active":
            raise StarletteHTTPException(
                409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_NOT_ACTIVE"}
            )
        if str(assignment["assigned_to"]) != actor:
            raise StarletteHTTPException(
                403, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_OWNER_FORBIDDEN"}
            )
        if int(assignment["version"]) != expected_version:
            raise StarletteHTTPException(
                409, detail={"code": "EVIDENCE_REVIEW_ASSIGNMENT_VERSION_CONFLICT"}
            )

    def _expire_assignment(
        self,
        conn: Any,
        assignment: Mapping[str, Any],
        actor: str,
        trace_id: str,
        at: datetime,
    ) -> Mapping[str, Any]:
        next_version = int(assignment["version"]) + 1
        conn.execute(
            text(
                """
                UPDATE airank_evidence_review_assignments
                SET status='expired', version=:version, updated_at=:at
                WHERE tenant_id=:tenant_id AND id=:assignment_id
                """
            ),
            {
                "version": next_version,
                "at": at,
                "tenant_id": assignment["tenant_id"],
                "assignment_id": assignment["id"],
            },
        )
        updated = self._assignment_row(
            conn, str(assignment["tenant_id"]), str(assignment["id"])
        )
        self._insert_assignment_event(
            conn, updated, "expired", actor, trace_id, at
        )
        self._audit(
            conn,
            str(updated["tenant_id"]),
            str(updated["project_id"]),
            str(updated["case_id"]),
            "evidence_review.assignment_expired",
            actor,
            trace_id,
            {"assignment_id": updated["id"], "version": next_version},
            at,
        )
        return updated

    def _complete_assignment(
        self,
        conn: Any,
        assignment: Mapping[str, Any],
        actor: str,
        trace_id: str,
        at: datetime,
    ) -> None:
        next_version = int(assignment["version"]) + 1
        conn.execute(
            text(
                """
                UPDATE airank_evidence_review_assignments
                SET status='completed', completed_at=:at,
                    version=:version, updated_at=:at
                WHERE tenant_id=:tenant_id AND id=:assignment_id
                  AND status='active' AND assigned_to=:actor
                """
            ),
            {
                "at": at,
                "version": next_version,
                "tenant_id": assignment["tenant_id"],
                "assignment_id": assignment["id"],
                "actor": actor,
            },
        )
        updated = self._assignment_row(
            conn, str(assignment["tenant_id"]), str(assignment["id"])
        )
        self._insert_assignment_event(
            conn, updated, "completed", actor, trace_id, at
        )

    @staticmethod
    def _insert_assignment_event(
        conn: Any,
        assignment: Mapping[str, Any],
        event_type: str,
        actor: str,
        trace_id: str,
        at: datetime,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO airank_evidence_review_assignment_events (
                  id, tenant_id, project_id, case_id, assignment_id,
                  event_type, assignment_version, actor, trace_id,
                  payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :case_id, :assignment_id,
                  :event_type, :assignment_version, :actor, :trace_id,
                  :payload_json, :created_at
                )
                """
            ),
            {
                "id": f"review_assignment_event_{uuid4().hex}",
                "tenant_id": assignment["tenant_id"],
                "project_id": assignment["project_id"],
                "case_id": assignment["case_id"],
                "assignment_id": assignment["id"],
                "event_type": event_type,
                "assignment_version": assignment["version"],
                "actor": actor,
                "trace_id": trace_id,
                "payload_json": json.dumps(
                    {
                        "status": assignment["status"],
                        "reviewer_role": assignment["reviewer_role"],
                        **dict(extra or {}),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "created_at": at,
            },
        )

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
        role = review_action_role(row)
        assignment = None
        if role is not None:
            assignment = conn.execute(
                text(
                    """
                    SELECT * FROM airank_evidence_review_assignments
                    WHERE tenant_id=:tenant_id AND case_id=:case_id
                      AND reviewer_role=:reviewer_role AND status='active'
                    ORDER BY assigned_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {
                    "tenant_id": row["tenant_id"],
                    "case_id": row["id"],
                    "reviewer_role": role,
                },
            ).mappings().first()
        return {
            **dict(row),
            "case_id": str(row["id"]),
            "decisions": self._decision_rows(conn, row),
            "assignment": assignment,
        }

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


def case_data_from_mapping(
    case: Mapping[str, Any], actor: str, *, at: Optional[datetime] = None
) -> EvidenceReviewCaseData:
    decisions = [decision_data(item) for item in case.get("decisions", [])]
    status = str(case["status"])
    final = status in {"agreed", "adjudicated"}
    visible = decisions if final else [item for item in decisions if item.reviewed_by == actor]
    current = next((item.reviewer_role for item in decisions if item.reviewed_by == actor), None)
    assignment: Optional[EvidenceReviewAssignmentData] = None
    if not final and current is None and review_action_role(case) is not None:
        raw_assignment = case.get("assignment")
        assignment = assignment_data_from_mapping(
            case,
            raw_assignment if isinstance(raw_assignment, Mapping) else None,
            actor,
            at=at,
        )
    next_action: str
    assignment_available = assignment is None or assignment.state != "assigned_to_other"
    if status == "awaiting_secondary" and current is None and assignment_available:
        next_action = "submit_secondary"
    elif status == "disputed" and current is None and assignment_available:
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
        assignment=assignment,
        visible_decisions=visible,
        created_by=str(case["created_by"]),
        finalized_by=str(case["finalized_by"]) if case.get("finalized_by") else None,
        created_at=citation_routes._utc_datetime(case["created_at"]),
        finalized_at=citation_routes._utc_datetime(case["finalized_at"]) if case.get("finalized_at") else None,
        version=int(case["version"]),
    )


def review_inbox_cursor_key(case: Mapping[str, Any]) -> tuple[int, int, str]:
    priority = 0 if str(case["status"]) == "disputed" else 1
    created_at = citation_routes._utc_datetime(case["created_at"])
    created_micros = int(created_at.timestamp() * 1_000_000)
    return priority, created_micros, str(case.get("case_id") or case.get("id"))


def encode_review_inbox_cursor(case: Mapping[str, Any]) -> str:
    priority, created_micros, case_id = review_inbox_cursor_key(case)
    payload = json.dumps(
        [1, priority, created_micros, case_id],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_review_inbox_cursor(cursor: str) -> tuple[int, int, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(
            b64decode(f"{cursor}{padding}", altchars=b"-_", validate=True).decode("utf-8")
        )
        if (
            not isinstance(payload, list)
            or len(payload) != 4
            or payload[0] != 1
            or payload[1] not in {0, 1}
            or not isinstance(payload[2], int)
            or payload[2] < 0
            or not isinstance(payload[3], str)
            or not payload[3]
            or len(payload[3]) > 64
        ):
            raise ValueError("invalid cursor payload")
        return int(payload[1]), int(payload[2]), payload[3]
    except (Base64Error, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise StarletteHTTPException(
            status_code=422,
            detail={"code": "EVIDENCE_REVIEW_CURSOR_INVALID"},
        ) from exc


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


class EvidenceReviewEscalationRepository(Protocol):
    def list_escalations(
        self,
        tenant_id: str,
        project_id: str,
        status: Optional[str],
        limit: int,
    ) -> EvidenceReviewEscalationListData: ...


class InMemoryEvidenceReviewEscalationRepository:
    def list_escalations(
        self,
        tenant_id: str,
        project_id: str,
        status: Optional[str],
        limit: int,
    ) -> EvidenceReviewEscalationListData:
        del tenant_id, status, limit
        return EvidenceReviewEscalationListData(
            project_id=project_id,
            escalation_count=0,
            pending_count=0,
            published_count=0,
            failed_count=0,
            canceled_count=0,
            escalations=[],
        )


class MySQLEvidenceReviewEscalationRepository:
    EVENT_TYPE = "evidence_review.sla_overdue.v1"
    SCHEMA_VERSION = "airank.evidence-review-sla-escalation.v1"

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def list_escalations(
        self,
        tenant_id: str,
        project_id: str,
        status: Optional[str],
        limit: int,
    ) -> EvidenceReviewEscalationListData:
        status_clause = " AND status=:status" if status else ""
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "event_type": self.EVENT_TYPE,
            "status": status,
            "limit": limit,
        }
        with self.engine.begin() as conn:
            project = conn.execute(
                text(
                    "SELECT id FROM airank_projects "
                    "WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL"
                ),
                params,
            ).first()
            if project is None:
                raise StarletteHTTPException(
                    404,
                    detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}},
                )
            counts = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS escalation_count,
                           SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending_count,
                           SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) AS published_count,
                           SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count,
                           SUM(CASE WHEN status='canceled' THEN 1 ELSE 0 END) AS canceled_count
                    FROM airank_outbox_events
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND event_type=:event_type
                    """
                ),
                params,
            ).mappings().one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, aggregate_id, status, payload_json, created_at
                    FROM airank_outbox_events
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND event_type=:event_type{status_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        checked_at = now_utc()
        escalations: list[EvidenceReviewEscalationData] = []
        for row in rows:
            try:
                payload = self._json_object(row["payload_json"])
                if payload.get("schema_version") != self.SCHEMA_VERSION:
                    raise ValueError("unsupported escalation payload schema")
                due_at = citation_routes._utc_datetime(payload["due_at"])
                escalation = EvidenceReviewEscalationData(
                    event_id=str(row["id"]),
                    case_id=str(row["aggregate_id"]),
                    reviewer_role=str(payload["reviewer_role"]),
                    due_at=due_at,
                    escalated_at=citation_routes._utc_datetime(row["created_at"]),
                    overdue_seconds=max(
                        0, int((checked_at - due_at).total_seconds())
                    ),
                    assignment_state=str(payload["assignment_state"]),
                    outbox_status=str(row["status"]),
                    external_delivery_verified=False,
                )
            except (KeyError, TypeError, ValueError):
                raise StarletteHTTPException(
                    409,
                    detail={
                        "code": "EVIDENCE_REVIEW_ESCALATION_INVALID",
                        "details": {"event_id": str(row["id"])},
                    },
                )
            escalations.append(escalation)
        return EvidenceReviewEscalationListData(
            project_id=project_id,
            escalation_count=int(counts["escalation_count"] or 0),
            pending_count=int(counts["pending_count"] or 0),
            published_count=int(counts["published_count"] or 0),
            failed_count=int(counts["failed_count"] or 0),
            canceled_count=int(counts["canceled_count"] or 0),
            escalations=escalations,
        )

    @staticmethod
    def _json_object(value: object) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}


def build_repository() -> EvidenceReviewRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLEvidenceReviewRepository(database_url) if database_url else InMemoryEvidenceReviewRepository()


EVIDENCE_REVIEW_REPOSITORY: EvidenceReviewRepository = build_repository()


def build_escalation_repository() -> EvidenceReviewEscalationRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return (
        MySQLEvidenceReviewEscalationRepository(database_url)
        if database_url
        else InMemoryEvidenceReviewEscalationRepository()
    )


EVIDENCE_REVIEW_ESCALATION_REPOSITORY: EvidenceReviewEscalationRepository = (
    build_escalation_repository()
)


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


@router.post(
    "/evidence-review-cases/{case_id}/assignment-claims",
    response_model=EvidenceReviewAssignmentResponse,
    status_code=201,
)
def claim_evidence_review_assignment(
    case_id: str,
    payload: EvidenceReviewAssignmentClaimRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
) -> EvidenceReviewAssignmentResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor("console-reviewer", authenticated_actor)
    return EvidenceReviewAssignmentResponse(
        data=EVIDENCE_REVIEW_REPOSITORY.claim_assignment(
            tenant_id, case_id, payload, actor, meta["trace_id"]
        ),
        meta=meta,
    )


@router.post(
    "/evidence-review-assignments/{assignment_id}/heartbeats",
    response_model=EvidenceReviewAssignmentResponse,
)
def heartbeat_evidence_review_assignment(
    assignment_id: str,
    payload: EvidenceReviewAssignmentHeartbeatRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
) -> EvidenceReviewAssignmentResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor("console-reviewer", authenticated_actor)
    return EvidenceReviewAssignmentResponse(
        data=EVIDENCE_REVIEW_REPOSITORY.heartbeat_assignment(
            tenant_id, assignment_id, payload, actor, meta["trace_id"]
        ),
        meta=meta,
    )


@router.post(
    "/evidence-review-assignments/{assignment_id}/release",
    response_model=EvidenceReviewAssignmentResponse,
)
def release_evidence_review_assignment(
    assignment_id: str,
    payload: EvidenceReviewAssignmentReleaseRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(
        default=None, alias="X-AIRank-User-Id"
    ),
) -> EvidenceReviewAssignmentResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor("console-reviewer", authenticated_actor)
    return EvidenceReviewAssignmentResponse(
        data=EVIDENCE_REVIEW_REPOSITORY.release_assignment(
            tenant_id, assignment_id, payload, actor, meta["trace_id"]
        ),
        meta=meta,
    )


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


@router.get(
    "/projects/{project_id}/evidence-review-inbox",
    response_model=EvidenceReviewInboxResponse,
)
def list_evidence_review_inbox(
    project_id: str,
    limit: int = Query(default=12, ge=1, le=50),
    cursor: Optional[str] = Query(default=None, min_length=1, max_length=512),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> EvidenceReviewInboxResponse:
    actor = trusted_actor("console-reviewer", authenticated_actor)
    return EvidenceReviewInboxResponse(
        data=EVIDENCE_REVIEW_REPOSITORY.list_inbox(
            tenant_id, project_id, actor, limit, cursor
        ),
        meta=response_meta(trace_id),
    )


@router.get(
    "/projects/{project_id}/evidence-review-escalations",
    response_model=EvidenceReviewEscalationListResponse,
)
def list_evidence_review_escalations(
    project_id: str,
    status: Optional[Literal["pending", "published", "failed", "canceled"]] = Query(
        default=None
    ),
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> EvidenceReviewEscalationListResponse:
    return EvidenceReviewEscalationListResponse(
        data=EVIDENCE_REVIEW_ESCALATION_REPOSITORY.list_escalations(
            tenant_id, project_id, status, limit
        ),
        meta=response_meta(trace_id),
    )


def review_label_value(review: Any) -> str:
    return str(
        getattr(review, "support_label", None)
        or getattr(review, "verdict", "")
    )

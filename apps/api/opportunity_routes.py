from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException


router = APIRouter(prefix="/api/v1", tags=["intervention-opportunities"])

CONTRACT_VERSION = "airank.intervention-opportunity.v1"
POLICY_VERSION = "airank.cross-domain-opportunity-policy.v1"
GAP_CONTRACT_VERSION = "airank.evidence-gap.v2"
SOURCE_KINDS = (
    "brand_visibility",
    "citation_support",
    "fact_governance",
    "page_extractability",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"unsupported datetime {value!r}")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=lambda item: as_utc(item).isoformat(),
        ).encode("utf-8")
    ).hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def json_value(value: object, default: object) -> object:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def error(status_code: int, code: str, details: Mapping[str, object]) -> StarletteHTTPException:
    return StarletteHTTPException(
        status_code=status_code,
        detail={"code": code, "details": dict(details)},
    )


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    if authenticated_actor and authenticated_actor.strip():
        return authenticated_actor.strip()
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor.strip()
    raise error(401, "AUTH_TOKEN_INVALID", {"reason": "authenticated_actor_required"})


class OpportunityDeriveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = Field(min_length=1, max_length=128)
    knowledge_window_days: int = Field(default=30, ge=1, le=365)
    as_of: Optional[datetime] = None

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        return value


class OpportunityScoreFactorsData(BaseModel):
    severity_points: int = Field(ge=0, le=40)
    evidence_points: int = Field(ge=0, le=35)
    urgency_points: int = Field(ge=0, le=25)
    total: int = Field(ge=0, le=100)


class OpportunitySourceRefsData(BaseModel):
    gap_ids: list[str] = Field(default_factory=list)
    answer_snapshot_ids: list[str] = Field(default_factory=list)
    evidence_snapshot_ids: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    citation_review_ids: list[str] = Field(default_factory=list)
    knowledge_source_ids: list[str] = Field(default_factory=list)
    fact_revision_ids: list[str] = Field(default_factory=list)
    fact_conflict_ids: list[str] = Field(default_factory=list)
    page_audit_run_ids: list[str] = Field(default_factory=list)
    page_audit_finding_ids: list[str] = Field(default_factory=list)


class InterventionOpportunityData(BaseModel):
    snapshot_id: str
    opportunity_id: str
    project_id: str
    derivation_run_id: str
    contract_version: Literal["airank.intervention-opportunity.v1"]
    policy_version: Literal["airank.cross-domain-opportunity-policy.v1"]
    source_kind: Literal[
        "brand_visibility",
        "citation_support",
        "fact_governance",
        "page_extractability",
    ]
    source_ref_type: str
    source_ref_id: str
    issue_code: str
    source_evidence_sha256: str
    evidence_level: str
    state: Literal["blocked_evidence", "ready_for_action", "monitor"]
    intervention_gate: Literal[
        "evidence_blocked",
        "verification_required",
        "content_action_ready",
        "research_action_ready",
        "governance_action_only",
        "technical_action_ready",
    ]
    severity: Literal["info", "low", "medium", "high", "critical"]
    priority_score: int = Field(ge=0, le=100)
    score_factors: OpportunityScoreFactorsData
    source_refs: OpportunitySourceRefsData
    title: str
    description: str
    recommended_action: str
    observed_at: datetime
    snapshot_sha256: str
    created_at: datetime


class OpportunityDerivationRunData(BaseModel):
    derivation_run_id: str
    project_id: str
    contract_version: Literal["airank.intervention-opportunity.v1"]
    policy_version: Literal["airank.cross-domain-opportunity-policy.v1"]
    source_basis_sha256: str
    evaluated_at: datetime
    knowledge_window_days: int
    previous_run_id: Optional[str]
    source_counts: dict[str, int]
    opportunity_count: int
    new_count: int
    persisting_count: int
    cleared_count: int
    cleared_opportunity_ids: list[str]
    opportunities: list[InterventionOpportunityData]
    created_by: str
    created_at: datetime
    idempotent_replay: bool = False


class OpportunityDerivationResponse(BaseModel):
    data: OpportunityDerivationRunData
    meta: dict[str, str]


class OpportunityListData(BaseModel):
    project_id: str
    contract_version: Literal["airank.intervention-opportunity.v1"]
    policy_version: Literal["airank.cross-domain-opportunity-policy.v1"]
    latest_derivation_run: Optional[OpportunityDerivationRunData]
    state_counts: dict[str, int]
    source_counts: dict[str, int]
    opportunities: list[InterventionOpportunityData]


class OpportunityListResponse(BaseModel):
    data: OpportunityListData
    meta: dict[str, str]


@dataclass(frozen=True)
class OpportunityCandidate:
    opportunity_id: str
    source_kind: str
    source_ref_type: str
    source_ref_id: str
    issue_code: str
    source_evidence_sha256: str
    evidence_level: str
    state: str
    intervention_gate: str
    severity: str
    priority_score: int
    score_factors: dict[str, int]
    source_refs: dict[str, list[str]]
    title: str
    description: str
    recommended_action: str
    observed_at: datetime

    def basis_record(self) -> dict[str, object]:
        return {
            "opportunity_id": self.opportunity_id,
            "source_kind": self.source_kind,
            "source_ref_type": self.source_ref_type,
            "source_ref_id": self.source_ref_id,
            "issue_code": self.issue_code,
            "source_evidence_sha256": self.source_evidence_sha256,
            "evidence_level": self.evidence_level,
            "state": self.state,
            "intervention_gate": self.intervention_gate,
            "severity": self.severity,
            "priority_score": self.priority_score,
            "score_factors": self.score_factors,
            "source_refs": self.source_refs,
            "title": self.title,
            "description": self.description,
            "recommended_action": self.recommended_action,
            "observed_at": self.observed_at.isoformat(),
        }


SEVERITY_POINTS = {"info": 5, "low": 10, "medium": 20, "high": 30, "critical": 40}
EVIDENCE_POINTS = {
    "quality_gated_repeated_samples": 35,
    "independently_reviewed_source_page": 35,
    "immutable_governance_record": 30,
    "content_hashed_page_audit": 25,
    "immutable_claim_citation_basis": 20,
}


def score_factors(severity: str, evidence_level: str, urgency_points: int) -> dict[str, int]:
    factors = {
        "severity_points": SEVERITY_POINTS[severity],
        "evidence_points": EVIDENCE_POINTS[evidence_level],
        "urgency_points": urgency_points,
    }
    factors["total"] = sum(factors.values())
    return factors


def empty_refs(**values: list[str]) -> dict[str, list[str]]:
    result = {
        "gap_ids": [],
        "answer_snapshot_ids": [],
        "evidence_snapshot_ids": [],
        "citation_ids": [],
        "citation_review_ids": [],
        "knowledge_source_ids": [],
        "fact_revision_ids": [],
        "fact_conflict_ids": [],
        "page_audit_run_ids": [],
        "page_audit_finding_ids": [],
    }
    for key, items in values.items():
        result[key] = sorted({str(item) for item in items if item})
    return result


def candidate(
    *,
    tenant_id: str,
    project_id: str,
    source_kind: str,
    source_ref_type: str,
    source_ref_id: str,
    issue_code: str,
    evidence_payload: object,
    evidence_level: str,
    state: str,
    intervention_gate: str,
    severity: str,
    urgency_points: int,
    source_refs: dict[str, list[str]],
    title: str,
    description: str,
    recommended_action: str,
    observed_at: datetime,
) -> OpportunityCandidate:
    factors = score_factors(severity, evidence_level, urgency_points)
    return OpportunityCandidate(
        opportunity_id=stable_id(
            "opportunity",
            tenant_id,
            project_id,
            source_kind,
            source_ref_id,
            issue_code,
            POLICY_VERSION,
        ),
        source_kind=source_kind,
        source_ref_type=source_ref_type,
        source_ref_id=source_ref_id,
        issue_code=issue_code,
        source_evidence_sha256=canonical_sha256(evidence_payload),
        evidence_level=evidence_level,
        state=state,
        intervention_gate=intervention_gate,
        severity=severity,
        priority_score=factors["total"],
        score_factors=factors,
        source_refs=source_refs,
        title=title[:255],
        description=description,
        recommended_action=recommended_action,
        observed_at=as_utc(observed_at),
    )


def severity(value: object, default: str = "medium") -> str:
    normalized = str(value or default).lower()
    return normalized if normalized in SEVERITY_POINTS else default


class OpportunityRepository(Protocol):
    def derive(
        self,
        tenant_id: str,
        project_id: str,
        payload: OpportunityDeriveRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityDerivationRunData: ...

    def list(
        self,
        tenant_id: str,
        project_id: str,
        *,
        derivation_run_id: Optional[str] = None,
        source_kind: Optional[str] = None,
        state: Optional[str] = None,
    ) -> OpportunityListData: ...


class InMemoryOpportunityRepository:
    def derive(
        self,
        tenant_id: str,
        project_id: str,
        payload: OpportunityDeriveRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityDerivationRunData:
        raise error(
            409,
            "OPPORTUNITY_SOURCE_EVIDENCE_REQUIRED",
            {"tenant_id": tenant_id, "project_id": project_id},
        )

    def list(
        self,
        tenant_id: str,
        project_id: str,
        *,
        derivation_run_id: Optional[str] = None,
        source_kind: Optional[str] = None,
        state: Optional[str] = None,
    ) -> OpportunityListData:
        return OpportunityListData(
            project_id=project_id,
            contract_version=CONTRACT_VERSION,
            policy_version=POLICY_VERSION,
            latest_derivation_run=None,
            state_counts={"blocked_evidence": 0, "ready_for_action": 0, "monitor": 0},
            source_counts={kind: 0 for kind in SOURCE_KINDS},
            opportunities=[],
        )


class MySQLOpportunityRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def _visibility_candidates(
        self, conn: Any, tenant_id: str, project_id: str
    ) -> list[OpportunityCandidate]:
        rows = conn.execute(
            text(
                """
                SELECT id, severity, title, description, status, created_at,
                       evidence_sha256, quality_report_sha256,
                       answer_snapshot_ids, evidence_snapshot_ids, citation_ids,
                       fact_atom_ids, suggested_asset_type
                FROM airank_content_gaps
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND deleted_at IS NULL
                  AND contract_version=:contract_version
                  AND evidence_sha256 IS NOT NULL
                  AND quality_report_sha256 IS NOT NULL
                ORDER BY id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "contract_version": GAP_CONTRACT_VERSION,
            },
        ).mappings().all()
        results = []
        for row in rows:
            evidence_hash = str(row["evidence_sha256"] or "")
            quality_hash = str(row["quality_report_sha256"] or "")
            if len(evidence_hash) != 64 or len(quality_hash) != 64:
                continue
            ready = str(row["status"]) == "ready_for_intervention"
            refs = empty_refs(
                gap_ids=[str(row["id"])],
                answer_snapshot_ids=list(json_value(row["answer_snapshot_ids"], [])),
                evidence_snapshot_ids=list(json_value(row["evidence_snapshot_ids"], [])),
                citation_ids=list(json_value(row["citation_ids"], [])),
            )
            results.append(
                candidate(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_kind="brand_visibility",
                    source_ref_type="evidence_gap",
                    source_ref_id=str(row["id"]),
                    issue_code="brand_unmentioned",
                    evidence_payload={
                        "gap_contract_version": GAP_CONTRACT_VERSION,
                        "gap_evidence_sha256": evidence_hash,
                        "quality_report_sha256": quality_hash,
                    },
                    evidence_level="quality_gated_repeated_samples",
                    state="ready_for_action" if ready else "blocked_evidence",
                    intervention_gate="content_action_ready" if ready else "evidence_blocked",
                    severity=severity(row["severity"]),
                    urgency_points=15,
                    source_refs=refs,
                    title=str(row["title"]),
                    description=(
                        f"{str(row['description'] or '')} 当前仅表示真实重复采样中的可见度缺口，"
                        "不表示任何干预后必然获得模型推荐。"
                    ),
                    recommended_action=(
                        f"create_{str(row['suggested_asset_type'] or 'fact_page')}"
                        if ready
                        else "collect_enterprise_fact_evidence"
                    ),
                    observed_at=as_utc(row["created_at"]),
                )
            )
        return results

    def _citation_candidates(
        self, conn: Any, tenant_id: str, project_id: str
    ) -> list[OpportunityCandidate]:
        snapshots = conn.execute(
            text(
                """
                SELECT DISTINCT s.id, s.answer_sha256, s.created_at,
                       e.id AS evidence_snapshot_id, e.raw_response_sha256
                FROM airank_answer_snapshots s
                JOIN airank_evidence_snapshots e
                  ON e.tenant_id=s.tenant_id AND e.answer_snapshot_id=s.id
                JOIN airank_source_citations c
                  ON c.tenant_id=s.tenant_id AND c.snapshot_id=s.id
                WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                  AND s.sample_status='valid'
                  AND s.answer_sha256 IS NOT NULL
                  AND e.raw_response_sha256 IS NOT NULL
                ORDER BY s.created_at, s.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        if not snapshots:
            return []
        citations = conn.execute(
            text(
                """
                SELECT id, snapshot_id, citation_order, title, url, host
                FROM airank_source_citations
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY snapshot_id, citation_order, id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        claims = conn.execute(
            text(
                """
                SELECT id, snapshot_id, answer_start, answer_end, answer_sha256,
                       claim_sha256, extraction_method, created_at
                FROM airank_answer_claims
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY snapshot_id, answer_start, id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        reviews = conn.execute(
            text(
                """
                SELECT r.id, r.claim_id, r.citation_id, r.support_label,
                       r.evidence_grade, r.source_content_sha256,
                       r.source_capture_id, r.source_segment_id,
                       r.source_start, r.source_end, r.review_method,
                       r.review_case_id, r.reviewer_role, r.reviewed_at,
                       c.status AS case_status, c.purpose AS case_purpose
                FROM airank_citation_support_reviews r
                LEFT JOIN airank_evidence_review_cases c
                  ON c.tenant_id=r.tenant_id AND c.id=r.review_case_id
                WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id
                ORDER BY r.reviewed_at, r.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        citations_by_snapshot: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        claims_by_snapshot: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in citations:
            citations_by_snapshot[str(row["snapshot_id"])].append(row)
        for row in claims:
            snapshot_id = str(row["snapshot_id"])
            claims_by_snapshot[snapshot_id].append(row)
        latest_by_pair: dict[tuple[str, str], Mapping[str, Any]] = {}
        for row in reviews:
            if str(row["case_purpose"] or "single_review") == "benchmark":
                continue
            latest_by_pair[(str(row["claim_id"]), str(row["citation_id"]))] = row

        results: list[OpportunityCandidate] = []
        for snapshot in snapshots:
            snapshot_id = str(snapshot["id"])
            if len(str(snapshot["answer_sha256"] or "")) != 64 or len(
                str(snapshot["raw_response_sha256"] or "")
            ) != 64:
                continue
            snapshot_citations = citations_by_snapshot[snapshot_id]
            snapshot_claims = claims_by_snapshot[snapshot_id]
            snapshot_claim_ids = {str(row["id"]) for row in snapshot_claims}
            current_reviews = [
                row
                for (claim_id, _), row in latest_by_pair.items()
                if claim_id in snapshot_claim_ids
            ]
            commercial = [
                row
                for row in current_reviews
                if str(row["evidence_grade"]) == "source_page_snapshot"
                and str(row["review_method"]) == "human"
                and row["source_capture_id"] is not None
                and row["source_segment_id"] is not None
                and row["source_start"] is not None
                and row["source_end"] is not None
                and row["review_case_id"] is not None
                and str(row["reviewer_role"]) in {"secondary", "adjudicator"}
                and str(row["case_status"]) in {"agreed", "adjudicated"}
                and str(row["case_purpose"]) == "production"
            ]
            base_payload = {
                "snapshot_id": snapshot_id,
                "answer_sha256": str(snapshot["answer_sha256"] or ""),
                "evidence_snapshot_id": str(snapshot["evidence_snapshot_id"]),
                "raw_response_sha256": str(snapshot["raw_response_sha256"]),
                "citations": [
                    {
                        "id": str(row["id"]),
                        "order": int(row["citation_order"]),
                        "title": str(row["title"] or ""),
                        "url": str(row["url"] or ""),
                        "host": str(row["host"] or ""),
                    }
                    for row in snapshot_citations
                ],
                "claims": [
                    {
                        "id": str(row["id"]),
                        "start": int(row["answer_start"]),
                        "end": int(row["answer_end"]),
                        "answer_sha256": str(row["answer_sha256"]),
                        "claim_sha256": str(row["claim_sha256"]),
                    }
                    for row in snapshot_claims
                ],
                "commercial_reviews": [
                    {
                        "id": str(row["id"]),
                        "claim_id": str(row["claim_id"]),
                        "citation_id": str(row["citation_id"]),
                        "label": str(row["support_label"]),
                        "source_content_sha256": str(row["source_content_sha256"]),
                        "case_id": str(row["review_case_id"]),
                        "case_status": str(row["case_status"]),
                        "role": str(row["reviewer_role"]),
                    }
                    for row in commercial
                ],
            }
            refs = empty_refs(
                answer_snapshot_ids=[snapshot_id],
                evidence_snapshot_ids=[str(snapshot["evidence_snapshot_id"])],
                citation_ids=[str(row["id"]) for row in snapshot_citations],
                citation_review_ids=[str(row["id"]) for row in commercial],
            )
            if not snapshot_claims:
                results.append(
                    candidate(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        source_kind="citation_support",
                        source_ref_type="answer_snapshot",
                        source_ref_id=snapshot_id,
                        issue_code="citation_claims_missing",
                        evidence_payload=base_payload,
                        evidence_level="immutable_claim_citation_basis",
                        state="blocked_evidence",
                        intervention_gate="verification_required",
                        severity="medium",
                        urgency_points=10,
                        source_refs=refs,
                        title="引用已选择，但回答事实声明尚未切分",
                        description="该回答包含 Provider 引用，但尚无带回答原文边界的 Claim，不能计算引用支持度。",
                        recommended_action="extract_and_review_answer_claims",
                        observed_at=as_utc(snapshot["created_at"]),
                    )
                )
                continue
            commercially_covered_claims = {str(row["claim_id"]) for row in commercial}
            uncovered_claims = sorted(snapshot_claim_ids - commercially_covered_claims)
            if uncovered_claims:
                refs_missing = dict(refs)
                results.append(
                    candidate(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        source_kind="citation_support",
                        source_ref_type="answer_snapshot",
                        source_ref_id=snapshot_id,
                        issue_code="citation_support_review_missing",
                        evidence_payload={**base_payload, "uncovered_claim_ids": uncovered_claims},
                        evidence_level="immutable_claim_citation_basis",
                        state="blocked_evidence",
                        intervention_gate="verification_required",
                        severity="medium",
                        urgency_points=10,
                        source_refs=refs_missing,
                        title="回答 Claim 尚未完成可交付引用支持复核",
                        description=(
                            f"{len(uncovered_claims)} 条 Claim 尚无来源页快照、精确边界和独立人工终审，"
                            "当前不得进入客户引用支持率。"
                        ),
                        recommended_action="complete_independent_citation_support_review",
                        observed_at=as_utc(snapshot["created_at"]),
                    )
                )
            for label, issue_code, level, urgency, title, action in (
                (
                    "contradicts",
                    "citation_contradicted",
                    "high",
                    25,
                    "来源页与回答 Claim 相矛盾",
                    "correct_or_withdraw_unsupported_claim",
                ),
                (
                    "insufficient",
                    "citation_insufficient",
                    "medium",
                    20,
                    "来源页不足以支持回答 Claim",
                    "strengthen_source_evidence_or_narrow_claim",
                ),
            ):
                matching = [row for row in commercial if str(row["support_label"]) == label]
                if not matching:
                    continue
                matching_refs = empty_refs(
                    answer_snapshot_ids=[snapshot_id],
                    evidence_snapshot_ids=[str(snapshot["evidence_snapshot_id"])],
                    citation_ids=[str(row["citation_id"]) for row in matching],
                    citation_review_ids=[str(row["id"]) for row in matching],
                )
                results.append(
                    candidate(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        source_kind="citation_support",
                        source_ref_type="answer_snapshot",
                        source_ref_id=snapshot_id,
                        issue_code=issue_code,
                        evidence_payload={**base_payload, "target_review_ids": matching_refs["citation_review_ids"]},
                        evidence_level="independently_reviewed_source_page",
                        state="ready_for_action",
                        intervention_gate="research_action_ready",
                        severity=level,
                        urgency_points=urgency,
                        source_refs=matching_refs,
                        title=title,
                        description=(
                            f"{len(matching)} 条已完成来源页快照、精确边界和独立人工终审的引用复核为 {label}。"
                            "该结论只适用于对应回答 Claim 与来源，不外推为整个平台准确率。"
                        ),
                        recommended_action=action,
                        observed_at=max(as_utc(row["reviewed_at"]) for row in matching),
                    )
                )
        return results

    def _governance_candidates(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        *,
        evaluated_at: datetime,
        window_days: int,
    ) -> list[OpportunityCandidate]:
        cutoff = evaluated_at + timedelta(days=window_days)
        results: list[OpportunityCandidate] = []
        conflicts = conn.execute(
            text(
                """
                SELECT c.id, c.fact_atom_id, c.left_revision_id, c.right_revision_id,
                       c.conflict_type, c.description, c.detected_at,
                       l.content_sha256 AS left_sha256,
                       r.content_sha256 AS right_sha256
                FROM airank_fact_conflicts c
                JOIN airank_fact_revisions l
                  ON l.tenant_id=c.tenant_id AND l.id=c.left_revision_id
                JOIN airank_fact_revisions r
                  ON r.tenant_id=c.tenant_id AND r.id=c.right_revision_id
                WHERE c.tenant_id=:tenant_id AND c.project_id=:project_id
                  AND c.status='open'
                ORDER BY c.detected_at, c.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        for row in conflicts:
            conflict_id = str(row["id"])
            results.append(
                candidate(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_kind="fact_governance",
                    source_ref_type="fact_conflict",
                    source_ref_id=conflict_id,
                    issue_code="fact_conflict_open",
                    evidence_payload={
                        "conflict_id": conflict_id,
                        "fact_atom_id": str(row["fact_atom_id"]),
                        "left_revision_id": str(row["left_revision_id"]),
                        "right_revision_id": str(row["right_revision_id"]),
                        "left_sha256": str(row["left_sha256"]),
                        "right_sha256": str(row["right_sha256"]),
                        "conflict_type": str(row["conflict_type"]),
                    },
                    evidence_level="immutable_governance_record",
                    state="ready_for_action",
                    intervention_gate="governance_action_only",
                    severity="critical",
                    urgency_points=25,
                    source_refs=empty_refs(
                        fact_revision_ids=[str(row["left_revision_id"]), str(row["right_revision_id"])],
                        fact_conflict_ids=[conflict_id],
                    ),
                    title="开放事实冲突阻断内容干预",
                    description=f"{str(row['description'])} 冲突必须由人工裁决；系统不会自动选择有利版本。",
                    recommended_action="adjudicate_fact_conflict",
                    observed_at=as_utc(row["detected_at"]),
                )
            )

        sources = conn.execute(
            text(
                """
                SELECT id, title, status, content_sha256, revision_number,
                       valid_until, captured_at
                FROM airank_knowledge_sources
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND (status='stale' OR (status='active' AND valid_until IS NOT NULL
                       AND valid_until<=:cutoff))
                ORDER BY id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "cutoff": cutoff},
        ).mappings().all()
        for row in sources:
            valid_until = as_utc(row["valid_until"]) if row["valid_until"] is not None else None
            if str(row["status"]) == "stale":
                issue_code, level, urgency, title = (
                    "knowledge_source_stale",
                    "high",
                    20,
                    "知识来源已有新版本",
                )
            elif valid_until is not None and valid_until <= evaluated_at:
                issue_code, level, urgency, title = (
                    "knowledge_source_expired",
                    "critical",
                    25,
                    "知识来源已过期",
                )
            else:
                issue_code, level, urgency, title = (
                    "knowledge_source_expiring",
                    "medium",
                    10,
                    "知识来源即将到期",
                )
            source_id = str(row["id"])
            results.append(
                candidate(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_kind="fact_governance",
                    source_ref_type="knowledge_source",
                    source_ref_id=source_id,
                    issue_code=issue_code,
                    evidence_payload={
                        "source_id": source_id,
                        "content_sha256": str(row["content_sha256"]),
                        "revision_number": int(row["revision_number"]),
                        "status": str(row["status"]),
                        "valid_until": valid_until.isoformat() if valid_until else None,
                    },
                    evidence_level="immutable_governance_record",
                    state="ready_for_action",
                    intervention_gate="governance_action_only",
                    severity=level,
                    urgency_points=urgency,
                    source_refs=empty_refs(knowledge_source_ids=[source_id]),
                    title=title,
                    description=(
                        f"来源「{str(row['title'])}」当前状态为 {str(row['status'])}。"
                        "更新或复核前，关联事实不得放行新的公开内容。"
                    ),
                    recommended_action="refresh_and_review_knowledge_source",
                    observed_at=valid_until or as_utc(row["captured_at"]),
                )
            )

        facts = conn.execute(
            text(
                """
                SELECT f.id AS fact_atom_id, f.title, f.current_revision_id,
                       r.content_sha256, r.valid_until, r.reviewed_at
                FROM airank_fact_atoms f
                JOIN airank_fact_revisions r
                  ON r.tenant_id=f.tenant_id AND r.id=f.current_revision_id
                WHERE f.tenant_id=:tenant_id AND f.project_id=:project_id
                  AND f.deleted_at IS NULL AND f.status='confirmed'
                  AND r.status='approved' AND r.valid_until IS NOT NULL
                  AND r.valid_until<=:cutoff
                ORDER BY r.id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "cutoff": cutoff},
        ).mappings().all()
        for row in facts:
            valid_until = as_utc(row["valid_until"])
            expired = valid_until <= evaluated_at
            revision_id = str(row["current_revision_id"])
            results.append(
                candidate(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_kind="fact_governance",
                    source_ref_type="fact_revision",
                    source_ref_id=revision_id,
                    issue_code="fact_revision_expired" if expired else "fact_revision_expiring",
                    evidence_payload={
                        "fact_atom_id": str(row["fact_atom_id"]),
                        "revision_id": revision_id,
                        "content_sha256": str(row["content_sha256"]),
                        "valid_until": valid_until.isoformat(),
                    },
                    evidence_level="immutable_governance_record",
                    state="ready_for_action",
                    intervention_gate="governance_action_only",
                    severity="critical" if expired else "medium",
                    urgency_points=25 if expired else 10,
                    source_refs=empty_refs(fact_revision_ids=[revision_id]),
                    title="审核事实已过期" if expired else "审核事实即将到期",
                    description=(
                        f"事实「{str(row['title'])}」的当前审核版本有效期至 {valid_until.isoformat()}。"
                        "重新核验前不得用于新的内容声明。"
                    ),
                    recommended_action="renew_fact_revision_evidence",
                    observed_at=valid_until,
                )
            )
        return results

    def _page_candidates(
        self, conn: Any, tenant_id: str, project_id: str
    ) -> list[OpportunityCandidate]:
        rows = conn.execute(
            text(
                """
                SELECT r.id AS run_id, r.requested_url, r.final_url, r.rules_version,
                       r.content_sha256, r.completed_at,
                       f.id AS finding_id, f.rule_id, f.severity, f.title,
                       f.description, f.recommendation, f.evidence_json, f.score_delta
                FROM airank_page_audit_runs r
                JOIN airank_page_audit_findings f
                  ON f.tenant_id=r.tenant_id AND f.run_id=r.id
                WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id
                  AND r.status='completed' AND f.status='failed'
                  AND r.content_sha256 IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM airank_page_audit_runs newer
                    WHERE newer.tenant_id=r.tenant_id
                      AND newer.project_id=r.project_id
                      AND newer.status='completed'
                      AND COALESCE(newer.final_url, newer.requested_url)
                          = COALESCE(r.final_url, r.requested_url)
                      AND (
                        newer.completed_at>r.completed_at
                        OR (newer.completed_at=r.completed_at AND newer.id>r.id)
                      )
                  )
                ORDER BY r.completed_at DESC, r.id DESC, f.rule_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        results = []
        for row in rows:
            run_id = str(row["run_id"])
            finding_id = str(row["finding_id"])
            finding_signal_id = stable_id(
                "page_rule",
                str(row["final_url"] or row["requested_url"]),
                str(row["rule_id"]),
                POLICY_VERSION,
            )
            finding_severity = severity(row["severity"])
            urgency = {"critical": 20, "high": 15, "medium": 10, "low": 5, "info": 5}[
                finding_severity
            ]
            results.append(
                candidate(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_kind="page_extractability",
                    source_ref_type="page_audit_rule",
                    source_ref_id=finding_signal_id,
                    issue_code=f"page_{str(row['rule_id'])}"[:128],
                    evidence_payload={
                        "run_id": run_id,
                        "finding_id": finding_id,
                        "rule_id": str(row["rule_id"]),
                        "rules_version": str(row["rules_version"]),
                        "content_sha256": str(row["content_sha256"]),
                        "evidence": json_value(row["evidence_json"], {}),
                        "score_delta": int(row["score_delta"]),
                    },
                    evidence_level="content_hashed_page_audit",
                    state="ready_for_action",
                    intervention_gate="technical_action_ready",
                    severity=finding_severity,
                    urgency_points=urgency,
                    source_refs=empty_refs(
                        page_audit_run_ids=[run_id],
                        page_audit_finding_ids=[finding_id],
                    ),
                    title=str(row["title"]),
                    description=(
                        f"{str(row['description'])} 这是页面可提取性问题，不是品牌推荐率或增长结论。"
                    ),
                    recommended_action=str(row["recommendation"] or "fix_page_extractability"),
                    observed_at=as_utc(row["completed_at"]),
                )
            )
        return results

    def _collect(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        *,
        evaluated_at: datetime,
        window_days: int,
    ) -> list[OpportunityCandidate]:
        candidates = [
            *self._visibility_candidates(conn, tenant_id, project_id),
            *self._citation_candidates(conn, tenant_id, project_id),
            *self._governance_candidates(
                conn,
                tenant_id,
                project_id,
                evaluated_at=evaluated_at,
                window_days=window_days,
            ),
            *self._page_candidates(conn, tenant_id, project_id),
        ]
        return sorted(candidates, key=lambda item: (-item.priority_score, item.opportunity_id))

    def derive(
        self,
        tenant_id: str,
        project_id: str,
        payload: OpportunityDeriveRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> OpportunityDerivationRunData:
        request_sha256 = canonical_sha256(
            {
                "contract_version": CONTRACT_VERSION,
                "policy_version": POLICY_VERSION,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "knowledge_window_days": payload.knowledge_window_days,
                "as_of": payload.as_of.isoformat() if payload.as_of else None,
            }
        )
        with self.engine.begin() as conn:
            project = conn.execute(
                text(
                    "SELECT id FROM airank_projects WHERE tenant_id=:tenant_id "
                    "AND id=:project_id AND deleted_at IS NULL"
                    + (" FOR UPDATE" if self.engine.dialect.name == "mysql" else "")
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).first()
            if project is None:
                raise error(404, "PROJECT_NOT_FOUND", {"project_id": project_id})
            replay = conn.execute(
                text(
                    """
                    SELECT * FROM airank_opportunity_derivation_runs
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND idempotency_key=:idempotency_key
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
            if replay is not None:
                if str(replay["request_sha256"]) != request_sha256:
                    raise error(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        {"idempotency_key": idempotency_key},
                    )
                return self._run_data(conn, replay, idempotent_replay=True)

            evaluated_at = as_utc(payload.as_of or utc_now())
            candidates = self._collect(
                conn,
                tenant_id,
                project_id,
                evaluated_at=evaluated_at,
                window_days=payload.knowledge_window_days,
            )
            if not candidates:
                raise error(
                    409,
                    "OPPORTUNITY_SOURCE_EVIDENCE_REQUIRED",
                    {"project_id": project_id, "policy_version": POLICY_VERSION},
                )
            source_basis_sha256 = canonical_sha256(
                {
                    "contract_version": CONTRACT_VERSION,
                    "policy_version": POLICY_VERSION,
                    "evaluated_at": evaluated_at.isoformat(),
                    "knowledge_window_days": payload.knowledge_window_days,
                    "opportunities": [item.basis_record() for item in candidates],
                }
            )
            previous = conn.execute(
                text(
                    """
                    SELECT * FROM airank_opportunity_derivation_runs
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().first()
            previous_ids = set(
                str(item) for item in json_value(previous["opportunity_ids_json"], [])
            ) if previous is not None else set()
            opportunity_ids = [item.opportunity_id for item in candidates]
            current_ids = set(opportunity_ids)
            cleared_ids = sorted(previous_ids - current_ids)
            new_count = len(current_ids - previous_ids)
            persisting_count = len(current_ids & previous_ids)
            source_counts = {kind: 0 for kind in SOURCE_KINDS}
            source_counts.update(Counter(item.source_kind for item in candidates))
            created_at = utc_now()
            run_id = stable_id(
                "opportunity_run", tenant_id, project_id, idempotency_key, request_sha256
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_opportunity_derivation_runs (
                      id, tenant_id, project_id, contract_version, policy_version,
                      idempotency_key, request_sha256, source_basis_sha256,
                      evaluated_at, knowledge_window_days, previous_run_id,
                      opportunity_ids_json, cleared_opportunity_ids_json,
                      source_counts_json, opportunity_count, new_count,
                      persisting_count, cleared_count, status, created_by,
                      trace_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :contract_version, :policy_version,
                      :idempotency_key, :request_sha256, :source_basis_sha256,
                      :evaluated_at, :knowledge_window_days, :previous_run_id,
                      :opportunity_ids_json, :cleared_opportunity_ids_json,
                      :source_counts_json, :opportunity_count, :new_count,
                      :persisting_count, :cleared_count, 'succeeded', :created_by,
                      :trace_id, :created_at
                    )
                    """
                ),
                {
                    "id": run_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "contract_version": CONTRACT_VERSION,
                    "policy_version": POLICY_VERSION,
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "source_basis_sha256": source_basis_sha256,
                    "evaluated_at": evaluated_at,
                    "knowledge_window_days": payload.knowledge_window_days,
                    "previous_run_id": str(previous["id"]) if previous is not None else None,
                    "opportunity_ids_json": json.dumps(opportunity_ids, ensure_ascii=False),
                    "cleared_opportunity_ids_json": json.dumps(cleared_ids, ensure_ascii=False),
                    "source_counts_json": json.dumps(source_counts, ensure_ascii=False, sort_keys=True),
                    "opportunity_count": len(candidates),
                    "new_count": new_count,
                    "persisting_count": persisting_count,
                    "cleared_count": len(cleared_ids),
                    "created_by": actor,
                    "trace_id": trace_id,
                    "created_at": created_at,
                },
            )
            for item in candidates:
                basis = item.basis_record()
                snapshot_sha256 = canonical_sha256(
                    {
                        "contract_version": CONTRACT_VERSION,
                        "policy_version": POLICY_VERSION,
                        "derivation_run_id": run_id,
                        **basis,
                    }
                )
                snapshot_id = stable_id("opportunity_snapshot", run_id, item.opportunity_id)
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_intervention_opportunity_snapshots (
                          id, tenant_id, project_id, derivation_run_id, opportunity_id,
                          contract_version, policy_version, source_kind, source_ref_type,
                          source_ref_id, issue_code, source_evidence_sha256, evidence_level,
                          state, intervention_gate, severity, priority_score,
                          score_factors_json, source_refs_json, title, description,
                          recommended_action, observed_at, snapshot_sha256, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :derivation_run_id, :opportunity_id,
                          :contract_version, :policy_version, :source_kind, :source_ref_type,
                          :source_ref_id, :issue_code, :source_evidence_sha256, :evidence_level,
                          :state, :intervention_gate, :severity, :priority_score,
                          :score_factors_json, :source_refs_json, :title, :description,
                          :recommended_action, :observed_at, :snapshot_sha256, :created_at
                        )
                        """
                    ),
                    {
                        "id": snapshot_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "derivation_run_id": run_id,
                        "opportunity_id": item.opportunity_id,
                        "contract_version": CONTRACT_VERSION,
                        "policy_version": POLICY_VERSION,
                        "source_kind": item.source_kind,
                        "source_ref_type": item.source_ref_type,
                        "source_ref_id": item.source_ref_id,
                        "issue_code": item.issue_code,
                        "source_evidence_sha256": item.source_evidence_sha256,
                        "evidence_level": item.evidence_level,
                        "state": item.state,
                        "intervention_gate": item.intervention_gate,
                        "severity": item.severity,
                        "priority_score": item.priority_score,
                        "score_factors_json": json.dumps(item.score_factors, sort_keys=True),
                        "source_refs_json": json.dumps(item.source_refs, ensure_ascii=False, sort_keys=True),
                        "title": item.title,
                        "description": item.description,
                        "recommended_action": item.recommended_action,
                        "observed_at": item.observed_at,
                        "snapshot_sha256": snapshot_sha256,
                        "created_at": created_at,
                    },
                )
            stored = conn.execute(
                text("SELECT * FROM airank_opportunity_derivation_runs WHERE id=:id"),
                {"id": run_id},
            ).mappings().one()
            return self._run_data(conn, stored)

    @staticmethod
    def _opportunity_data(row: Mapping[str, Any]) -> InterventionOpportunityData:
        return InterventionOpportunityData(
            snapshot_id=str(row["id"]),
            opportunity_id=str(row["opportunity_id"]),
            project_id=str(row["project_id"]),
            derivation_run_id=str(row["derivation_run_id"]),
            contract_version=CONTRACT_VERSION,
            policy_version=POLICY_VERSION,
            source_kind=str(row["source_kind"]),
            source_ref_type=str(row["source_ref_type"]),
            source_ref_id=str(row["source_ref_id"]),
            issue_code=str(row["issue_code"]),
            source_evidence_sha256=str(row["source_evidence_sha256"]),
            evidence_level=str(row["evidence_level"]),
            state=str(row["state"]),
            intervention_gate=str(row["intervention_gate"]),
            severity=str(row["severity"]),
            priority_score=int(row["priority_score"]),
            score_factors=OpportunityScoreFactorsData.model_validate(
                json_value(row["score_factors_json"], {})
            ),
            source_refs=OpportunitySourceRefsData.model_validate(
                json_value(row["source_refs_json"], {})
            ),
            title=str(row["title"]),
            description=str(row["description"]),
            recommended_action=str(row["recommended_action"]),
            observed_at=as_utc(row["observed_at"]),
            snapshot_sha256=str(row["snapshot_sha256"]),
            created_at=as_utc(row["created_at"]),
        )

    def _run_data(
        self,
        conn: Any,
        row: Mapping[str, Any],
        *,
        idempotent_replay: bool = False,
        source_kind: Optional[str] = None,
        state: Optional[str] = None,
    ) -> OpportunityDerivationRunData:
        conditions = ["tenant_id=:tenant_id", "derivation_run_id=:run_id"]
        params: dict[str, Any] = {
            "tenant_id": str(row["tenant_id"]),
            "run_id": str(row["id"]),
        }
        if source_kind:
            conditions.append("source_kind=:source_kind")
            params["source_kind"] = source_kind
        if state:
            conditions.append("state=:state")
            params["state"] = state
        snapshots = conn.execute(
            text(
                "SELECT * FROM airank_intervention_opportunity_snapshots WHERE "
                + " AND ".join(conditions)
                + " ORDER BY priority_score DESC, opportunity_id"
            ),
            params,
        ).mappings().all()
        return OpportunityDerivationRunData(
            derivation_run_id=str(row["id"]),
            project_id=str(row["project_id"]),
            contract_version=CONTRACT_VERSION,
            policy_version=POLICY_VERSION,
            source_basis_sha256=str(row["source_basis_sha256"]),
            evaluated_at=as_utc(row["evaluated_at"]),
            knowledge_window_days=int(row["knowledge_window_days"]),
            previous_run_id=str(row["previous_run_id"]) if row["previous_run_id"] else None,
            source_counts={
                str(key): int(value)
                for key, value in dict(json_value(row["source_counts_json"], {})).items()
            },
            opportunity_count=int(row["opportunity_count"]),
            new_count=int(row["new_count"]),
            persisting_count=int(row["persisting_count"]),
            cleared_count=int(row["cleared_count"]),
            cleared_opportunity_ids=[
                str(item) for item in json_value(row["cleared_opportunity_ids_json"], [])
            ],
            opportunities=[self._opportunity_data(item) for item in snapshots],
            created_by=str(row["created_by"]),
            created_at=as_utc(row["created_at"]),
            idempotent_replay=idempotent_replay,
        )

    def list(
        self,
        tenant_id: str,
        project_id: str,
        *,
        derivation_run_id: Optional[str] = None,
        source_kind: Optional[str] = None,
        state: Optional[str] = None,
    ) -> OpportunityListData:
        with self.engine.begin() as conn:
            project = conn.execute(
                text(
                    "SELECT id FROM airank_projects WHERE tenant_id=:tenant_id "
                    "AND id=:project_id AND deleted_at IS NULL"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).first()
            if project is None:
                raise error(404, "PROJECT_NOT_FOUND", {"project_id": project_id})
            conditions = ["tenant_id=:tenant_id", "project_id=:project_id"]
            params: dict[str, Any] = {"tenant_id": tenant_id, "project_id": project_id}
            if derivation_run_id:
                conditions.append("id=:run_id")
                params["run_id"] = derivation_run_id
            row = conn.execute(
                text(
                    "SELECT * FROM airank_opportunity_derivation_runs WHERE "
                    + " AND ".join(conditions)
                    + " ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                params,
            ).mappings().first()
            if row is None:
                if derivation_run_id:
                    raise error(
                        404,
                        "OPPORTUNITY_DERIVATION_NOT_FOUND",
                        {"derivation_run_id": derivation_run_id},
                    )
                return OpportunityListData(
                    project_id=project_id,
                    contract_version=CONTRACT_VERSION,
                    policy_version=POLICY_VERSION,
                    latest_derivation_run=None,
                    state_counts={"blocked_evidence": 0, "ready_for_action": 0, "monitor": 0},
                    source_counts={kind: 0 for kind in SOURCE_KINDS},
                    opportunities=[],
                )
            run = self._run_data(conn, row, source_kind=source_kind, state=state)
            opportunities = run.opportunities
            state_counts = {"blocked_evidence": 0, "ready_for_action": 0, "monitor": 0}
            state_counts.update(Counter(item.state for item in opportunities))
            source_counts = {kind: 0 for kind in SOURCE_KINDS}
            source_counts.update(Counter(item.source_kind for item in opportunities))
            return OpportunityListData(
                project_id=project_id,
                contract_version=CONTRACT_VERSION,
                policy_version=POLICY_VERSION,
                latest_derivation_run=run,
                state_counts=state_counts,
                source_counts=source_counts,
                opportunities=opportunities,
            )


def build_repository() -> OpportunityRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL", "").strip()
    return MySQLOpportunityRepository(database_url) if database_url else InMemoryOpportunityRepository()


OPPORTUNITY_REPOSITORY: OpportunityRepository = build_repository()


@router.post(
    "/projects/{project_id}/opportunities/derive",
    response_model=OpportunityDerivationResponse,
    status_code=201,
)
def derive_opportunities(
    project_id: str,
    payload: OpportunityDeriveRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> OpportunityDerivationResponse:
    meta = response_meta(trace_id)
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    data = OPPORTUNITY_REPOSITORY.derive(
        tenant_id,
        project_id,
        payload,
        idempotency_key=idempotency_key,
        actor=actor,
        trace_id=meta["trace_id"],
    )
    return OpportunityDerivationResponse(data=data, meta=meta)


@router.get(
    "/projects/{project_id}/opportunities",
    response_model=OpportunityListResponse,
)
def list_opportunities(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    derivation_run_id: Optional[str] = Query(default=None, min_length=1, max_length=64),
    source_kind: Optional[Literal[
        "brand_visibility",
        "citation_support",
        "fact_governance",
        "page_extractability",
    ]] = Query(default=None),
    state: Optional[Literal["blocked_evidence", "ready_for_action", "monitor"]] = Query(
        default=None
    ),
) -> OpportunityListResponse:
    return OpportunityListResponse(
        data=OPPORTUNITY_REPOSITORY.list(
            tenant_id,
            project_id,
            derivation_run_id=derivation_run_id,
            source_kind=source_kind,
            state=state,
        ),
        meta=response_meta(trace_id),
    )

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam, create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from .retest_routes import MySQLRetestRepository
except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
    from retest_routes import MySQLRetestRepository  # type: ignore[no-redef]


router = APIRouter(prefix="/api/v1", tags=["evidence-gaps"])

GAP_CONTRACT_VERSION = "airank.evidence-gap.v2"
DERIVATION_POLICY = "airank.brand-unmentioned-gap.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    if authenticated_actor and authenticated_actor.strip():
        return authenticated_actor.strip()
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor.strip()
    raise error(401, "AUTH_TOKEN_INVALID", {"reason": "authenticated_actor_required"})


def json_value(value: object, default: object) -> object:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def error(status_code: int, code: str, details: Mapping[str, object]) -> StarletteHTTPException:
    return StarletteHTTPException(
        status_code=status_code,
        detail={"code": code, "details": dict(details)},
    )


class DeriveEvidenceGapsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=64)
    requested_by: str = Field(min_length=1, max_length=128)


class EvidenceGapData(BaseModel):
    gap_id: str
    project_id: str
    run_id: str
    gap_type: Literal["brand_unmentioned"]
    contract_version: Literal["airank.evidence-gap.v2"]
    derivation_policy: Literal["airank.brand-unmentioned-gap.v1"]
    severity: Literal["low", "medium", "high"]
    title: str
    description: str
    related_question_ids: list[str]
    provider: str
    collector_surface: str
    valid_sample_count: int
    normal_unmentioned_count: int
    answer_snapshot_ids: list[str]
    evidence_snapshot_ids: list[str]
    citation_ids: list[str]
    fact_atom_ids: list[str]
    suggested_asset_type: str
    evidence_sha256: str
    quality_report_sha256: str
    status: str
    created_at: datetime


class EvidenceGapDerivationData(BaseModel):
    derivation_run_id: str
    project_id: str
    run_id: str
    contract_version: Literal["airank.evidence-gap.v2"]
    derivation_policy: Literal["airank.brand-unmentioned-gap.v1"]
    quality_report_sha256: str
    evidence_basis_sha256: str
    gap_count: int
    skipped_group_count: int
    gaps: list[EvidenceGapData]
    created_by: str
    created_at: datetime
    idempotent_replay: bool = False


class EvidenceGapDerivationResponse(BaseModel):
    data: EvidenceGapDerivationData
    meta: dict[str, str]


class EvidenceGapListData(BaseModel):
    project_id: str
    contract_version: Literal["airank.evidence-gap.v2"]
    gaps: list[EvidenceGapData]
    governed_gap_count: int
    unverified_legacy_count: int


class EvidenceGapListResponse(BaseModel):
    data: EvidenceGapListData
    meta: dict[str, str]


@dataclass(frozen=True)
class GapSampleEvidence:
    task_id: str
    question_id: str
    question_text: str
    question_type: str
    question_priority: int
    provider: str
    collector_surface: str
    sample_index: int
    session_id: str
    answer_snapshot_id: str
    evidence_snapshot_id: str
    answer_sha256: str
    raw_response_sha256: str
    sample_status: str
    brand_mentioned: bool
    mention_class: str
    citation_ids: tuple[str, ...] = ()

    def basis_record(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "question_id": self.question_id,
            "provider": self.provider,
            "collector_surface": self.collector_surface,
            "sample_index": self.sample_index,
            "session_id": self.session_id,
            "answer_snapshot_id": self.answer_snapshot_id,
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "answer_sha256": self.answer_sha256,
            "raw_response_sha256": self.raw_response_sha256,
            "sample_status": self.sample_status,
            "brand_mentioned": self.brand_mentioned,
            "mention_class": self.mention_class,
            "citation_ids": list(self.citation_ids),
        }


@dataclass(frozen=True)
class GapCandidate:
    gap_id: str
    question_id: str
    provider: str
    collector_surface: str
    severity: str
    title: str
    description: str
    suggested_asset_type: str
    answer_snapshot_ids: tuple[str, ...]
    evidence_snapshot_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    evidence_summary: dict[str, object]
    evidence_sha256: str


def severity_for_priority(priority: int) -> Literal["low", "medium", "high"]:
    if priority <= 30:
        return "high"
    if priority <= 70:
        return "medium"
    return "low"


def asset_type_for_question(question_type: str) -> str:
    return {
        "compare": "comparison_page",
        "trust": "case_page",
        "price": "service_page",
        "risk": "faq",
        "scenario": "solution_page",
        "local": "service_page",
        "alternative": "comparison_page",
    }.get(question_type, "fact_page")


def derive_brand_unmentioned_candidates(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    repetitions: int,
    quality_report_sha256: str,
    samples: list[GapSampleEvidence],
) -> tuple[list[GapCandidate], int, str]:
    groups: dict[tuple[str, str, str], list[GapSampleEvidence]] = defaultdict(list)
    for sample in samples:
        groups[(sample.question_id, sample.provider, sample.collector_surface)].append(sample)

    candidates: list[GapCandidate] = []
    skipped_group_count = 0
    all_basis = []
    expected_indexes = list(range(1, repetitions + 1))
    for group_key in sorted(groups):
        ordered = sorted(
            groups[group_key], key=lambda item: (item.sample_index, item.answer_snapshot_id)
        )
        all_basis.extend(sample.basis_record() for sample in ordered)
        sample_indexes = [item.sample_index for item in ordered]
        independent_sessions = {item.session_id for item in ordered if item.session_id}
        evidence_complete = all(
            item.answer_snapshot_id
            and item.evidence_snapshot_id
            and len(item.answer_sha256) == 64
            and len(item.raw_response_sha256) == 64
            for item in ordered
        )
        normal_unmentioned = all(
            item.sample_status == "valid"
            and not item.brand_mentioned
            and item.mention_class == "not_mentioned"
            for item in ordered
        )
        if (
            len(ordered) != repetitions
            or sample_indexes != expected_indexes
            or len(independent_sessions) != repetitions
            or not evidence_complete
            or not normal_unmentioned
        ):
            skipped_group_count += 1
            continue

        first = ordered[0]
        answer_ids = tuple(item.answer_snapshot_id for item in ordered)
        evidence_ids = tuple(item.evidence_snapshot_id for item in ordered)
        citation_ids = tuple(
            sorted({citation_id for item in ordered for citation_id in item.citation_ids})
        )
        evidence_summary = {
            "question_id": first.question_id,
            "provider": first.provider,
            "collector_surface": first.collector_surface,
            "expected_repetitions": repetitions,
            "valid_sample_count": len(ordered),
            "normal_unmentioned_count": len(ordered),
            "brand_mention_count": 0,
            "sample_indexes": sample_indexes,
            "independent_session_count": len(independent_sessions),
            "quality_report_sha256": quality_report_sha256,
        }
        evidence_payload = {
            "contract_version": GAP_CONTRACT_VERSION,
            "derivation_policy": DERIVATION_POLICY,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "answer_snapshot_ids": list(answer_ids),
            "evidence_snapshot_ids": list(evidence_ids),
            "citation_ids": list(citation_ids),
            "evidence_summary": evidence_summary,
        }
        evidence_sha256 = canonical_sha256(evidence_payload)
        gap_id = stable_id(
            "gap_ev",
            tenant_id,
            project_id,
            run_id,
            first.question_id,
            first.provider,
            first.collector_surface,
            DERIVATION_POLICY,
        )
        surface_label = {"api": "API", "web": "Web", "app": "App"}.get(
            first.collector_surface, first.collector_surface
        )
        candidates.append(
            GapCandidate(
                gap_id=gap_id,
                question_id=first.question_id,
                provider=first.provider,
                collector_surface=first.collector_surface,
                severity=severity_for_priority(first.question_priority),
                title=f"{first.provider} · {surface_label} 未提及品牌",
                description=(
                    f"问题「{first.question_text[:160]}」在 {len(ordered)} 次独立有效样本中均未提及品牌。"
                    "这是可见度缺口观察，不代表发布内容后必然获得推荐。"
                ),
                suggested_asset_type=asset_type_for_question(first.question_type),
                answer_snapshot_ids=answer_ids,
                evidence_snapshot_ids=evidence_ids,
                citation_ids=citation_ids,
                evidence_summary=evidence_summary,
                evidence_sha256=evidence_sha256,
            )
        )
    evidence_basis_sha256 = canonical_sha256(
        {
            "contract_version": GAP_CONTRACT_VERSION,
            "derivation_policy": DERIVATION_POLICY,
            "run_id": run_id,
            "quality_report_sha256": quality_report_sha256,
            "samples": all_basis,
        }
    )
    return candidates, skipped_group_count, evidence_basis_sha256


class EvidenceGapRepository(Protocol):
    def derive(
        self,
        tenant_id: str,
        project_id: str,
        payload: DeriveEvidenceGapsRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceGapDerivationData: ...

    def list(self, tenant_id: str, project_id: str) -> EvidenceGapListData: ...


class InMemoryEvidenceGapRepository:
    def derive(
        self,
        tenant_id: str,
        project_id: str,
        payload: DeriveEvidenceGapsRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceGapDerivationData:
        raise error(
            404,
            "SCAN_RUN_NOT_FOUND",
            {"tenant_id": tenant_id, "project_id": project_id, "run_id": payload.run_id},
        )

    def list(self, tenant_id: str, project_id: str) -> EvidenceGapListData:
        return EvidenceGapListData(
            project_id=project_id,
            contract_version=GAP_CONTRACT_VERSION,
            gaps=[],
            governed_gap_count=0,
            unverified_legacy_count=0,
        )


class MySQLEvidenceGapRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.quality_repository = MySQLRetestRepository(database_url)

    def derive(
        self,
        tenant_id: str,
        project_id: str,
        payload: DeriveEvidenceGapsRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> EvidenceGapDerivationData:
        request_sha256 = canonical_sha256(
            {
                "contract_version": GAP_CONTRACT_VERSION,
                "derivation_policy": DERIVATION_POLICY,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": payload.run_id,
            }
        )
        with self.engine.begin() as conn:
            replay = self._find_replay(
                conn,
                tenant_id,
                project_id,
                payload.run_id,
                idempotency_key,
                request_sha256,
            )
            if replay is not None:
                return self._derivation_data(conn, replay, idempotent_replay=True)
            run_exists = conn.execute(
                text(
                    "SELECT r.id, r.created_at, p.updated_at AS profile_updated_at "
                    "FROM airank_scan_runs r "
                    "JOIN airank_projects p ON p.tenant_id=r.tenant_id AND p.id=r.project_id "
                    "WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id "
                    "AND r.id=:run_id AND r.deleted_at IS NULL AND p.deleted_at IS NULL"
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": payload.run_id,
                },
            ).first()
            if run_exists is None:
                raise error(404, "SCAN_RUN_NOT_FOUND", {"run_id": payload.run_id})
            if run_exists.created_at < run_exists.profile_updated_at:
                raise error(
                    409,
                    "PROJECT_PROFILE_CHANGED_RESCAN_REQUIRED",
                    {
                        "run_id": payload.run_id,
                        "impact": "historical_scan_preserved_but_not_eligible_for_current_intervention",
                    },
                )

        quality = self.quality_repository.get_quality_report(
            tenant_id, project_id, payload.run_id
        )
        if quality.get("publishable") is not True:
            blockers = [
                str(item.get("code"))
                for item in quality.get("checks", [])
                if isinstance(item, dict) and item.get("status") == "blocked"
            ]
            raise error(
                409,
                "EVIDENCE_GAP_QUALITY_BLOCKED",
                {
                    "run_id": payload.run_id,
                    "quality_report_sha256": quality.get("report_sha256"),
                    "blocking_checks": blockers,
                },
            )
        quality_report_sha256 = str(quality.get("report_sha256") or "")
        if len(quality_report_sha256) != 64:
            raise error(
                409,
                "EVIDENCE_GAP_BASIS_INVALID",
                {"run_id": payload.run_id, "reason": "quality_report_hash_missing"},
            )

        with self.engine.begin() as conn:
            run = conn.execute(
                text(
                    """
                    SELECT id, repetitions, status
                    FROM airank_scan_runs
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND id=:run_id AND deleted_at IS NULL
                    """
                    + (" FOR UPDATE" if self.engine.dialect.name == "mysql" else "")
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": payload.run_id,
                },
            ).mappings().first()
            if run is None:
                raise error(404, "SCAN_RUN_NOT_FOUND", {"run_id": payload.run_id})
            replay = self._find_replay(
                conn,
                tenant_id,
                project_id,
                payload.run_id,
                idempotency_key,
                request_sha256,
            )
            if replay is not None:
                return self._derivation_data(conn, replay, idempotent_replay=True)
            rows = conn.execute(
                text(
                    """
                    SELECT t.id AS task_id, t.question_id, q.question_text,
                           q.question_type, q.priority AS question_priority,
                           t.provider, t.collector_surface, t.sample_index,
                           t.session_id, s.id AS answer_snapshot_id,
                           e.id AS evidence_snapshot_id, s.answer_sha256,
                           e.raw_response_sha256, s.sample_status,
                           s.brand_mentioned, s.mention_class
                    FROM airank_scan_tasks t
                    JOIN airank_buyer_questions q
                      ON q.tenant_id=t.tenant_id AND q.project_id=t.project_id
                     AND q.id=t.question_id AND q.deleted_at IS NULL
                    JOIN airank_answer_snapshots s
                      ON s.tenant_id=t.tenant_id AND s.task_id=t.id
                    JOIN airank_evidence_snapshots e
                      ON e.tenant_id=t.tenant_id AND e.answer_snapshot_id=s.id
                    WHERE t.tenant_id=:tenant_id AND t.project_id=:project_id
                      AND t.run_id=:run_id
                    ORDER BY t.question_id, t.provider, t.collector_surface,
                             t.sample_index, t.id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": payload.run_id,
                },
            ).mappings().all()
            if not rows:
                raise error(
                    409,
                    "EVIDENCE_GAP_BASIS_INVALID",
                    {"run_id": payload.run_id, "reason": "no_immutable_samples"},
                )
            answer_ids = [str(row["answer_snapshot_id"]) for row in rows]
            citation_rows = conn.execute(
                text(
                    """
                    SELECT snapshot_id, id
                    FROM airank_source_citations
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND snapshot_id IN :snapshot_ids
                    ORDER BY snapshot_id, citation_order, id
                    """
                ).bindparams(bindparam("snapshot_ids", expanding=True)),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "snapshot_ids": answer_ids,
                },
            ).mappings().all()
            citations_by_snapshot: dict[str, list[str]] = defaultdict(list)
            for citation in citation_rows:
                citations_by_snapshot[str(citation["snapshot_id"])].append(
                    str(citation["id"])
                )
            samples = [
                GapSampleEvidence(
                    task_id=str(row["task_id"]),
                    question_id=str(row["question_id"]),
                    question_text=str(row["question_text"]),
                    question_type=str(row["question_type"]),
                    question_priority=int(row["question_priority"]),
                    provider=str(row["provider"]),
                    collector_surface=str(row["collector_surface"]),
                    sample_index=int(row["sample_index"]),
                    session_id=str(row["session_id"] or ""),
                    answer_snapshot_id=str(row["answer_snapshot_id"]),
                    evidence_snapshot_id=str(row["evidence_snapshot_id"]),
                    answer_sha256=str(row["answer_sha256"] or ""),
                    raw_response_sha256=str(row["raw_response_sha256"] or ""),
                    sample_status=str(row["sample_status"]),
                    brand_mentioned=bool(row["brand_mentioned"]),
                    mention_class=str(row["mention_class"]),
                    citation_ids=tuple(
                        citations_by_snapshot.get(str(row["answer_snapshot_id"]), [])
                    ),
                )
                for row in rows
            ]
            candidates, skipped_group_count, evidence_basis_sha256 = (
                derive_brand_unmentioned_candidates(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=payload.run_id,
                    repetitions=int(run["repetitions"]),
                    quality_report_sha256=quality_report_sha256,
                    samples=samples,
                )
            )

            created_at = utc_now().replace(tzinfo=None)
            derivation_run_id = stable_id(
                "gap_run", tenant_id, project_id, payload.run_id, GAP_CONTRACT_VERSION
            )
            for candidate in candidates:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_content_gaps (
                          id, tenant_id, project_id, run_id, gap_type,
                          contract_version, derivation_policy, severity, title,
                          description, related_question_ids,
                          related_competitor_ids, answer_snapshot_ids,
                          evidence_snapshot_ids, citation_ids, fact_atom_ids,
                          suggested_asset_type, evidence_summary_json,
                          evidence_sha256, quality_report_sha256, derived_by,
                          status, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :run_id,
                          'brand_unmentioned', :contract_version,
                          :derivation_policy, :severity, :title, :description,
                          :related_question_ids, JSON_ARRAY(),
                          :answer_snapshot_ids, :evidence_snapshot_ids,
                          :citation_ids, JSON_ARRAY(), :suggested_asset_type,
                          :evidence_summary_json, :evidence_sha256,
                          :quality_report_sha256, :derived_by, 'open',
                          :created_at, :created_at
                        )
                        """
                    ),
                    {
                        "id": candidate.gap_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "run_id": payload.run_id,
                        "contract_version": GAP_CONTRACT_VERSION,
                        "derivation_policy": DERIVATION_POLICY,
                        "severity": candidate.severity,
                        "title": candidate.title,
                        "description": candidate.description,
                        "related_question_ids": json.dumps(
                            [candidate.question_id], ensure_ascii=False
                        ),
                        "answer_snapshot_ids": json.dumps(
                            list(candidate.answer_snapshot_ids), ensure_ascii=False
                        ),
                        "evidence_snapshot_ids": json.dumps(
                            list(candidate.evidence_snapshot_ids), ensure_ascii=False
                        ),
                        "citation_ids": json.dumps(
                            list(candidate.citation_ids), ensure_ascii=False
                        ),
                        "suggested_asset_type": candidate.suggested_asset_type,
                        "evidence_summary_json": json.dumps(
                            candidate.evidence_summary,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "evidence_sha256": candidate.evidence_sha256,
                        "quality_report_sha256": quality_report_sha256,
                        "derived_by": actor[:128],
                        "created_at": created_at,
                    },
                )
            gap_ids = [candidate.gap_id for candidate in candidates]
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_gap_derivation_runs (
                      id, tenant_id, project_id, scan_run_id,
                      contract_version, derivation_policy, idempotency_key,
                      request_sha256, quality_report_sha256,
                      evidence_basis_sha256, status, gap_ids_json, gap_count,
                      skipped_group_count, created_by, trace_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :scan_run_id,
                      :contract_version, :derivation_policy, :idempotency_key,
                      :request_sha256, :quality_report_sha256,
                      :evidence_basis_sha256, 'succeeded', :gap_ids_json,
                      :gap_count, :skipped_group_count, :created_by,
                      :trace_id, :created_at
                    )
                    """
                ),
                {
                    "id": derivation_run_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "scan_run_id": payload.run_id,
                    "contract_version": GAP_CONTRACT_VERSION,
                    "derivation_policy": DERIVATION_POLICY,
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "quality_report_sha256": quality_report_sha256,
                    "evidence_basis_sha256": evidence_basis_sha256,
                    "gap_ids_json": json.dumps(gap_ids, ensure_ascii=False),
                    "gap_count": len(gap_ids),
                    "skipped_group_count": skipped_group_count,
                    "created_by": actor[:128],
                    "trace_id": trace_id[:128],
                    "created_at": created_at,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, actor_user_id, event_type,
                      entity_type, entity_id, payload_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :actor,
                      'content_gap.evidence_derived',
                      'content_gap_derivation_run', :entity_id,
                      :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": stable_id("audit_gap", tenant_id, derivation_run_id),
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "actor": actor[:128],
                    "entity_id": derivation_run_id,
                    "payload_json": json.dumps(
                        {
                            "contract_version": GAP_CONTRACT_VERSION,
                            "run_id": payload.run_id,
                            "quality_report_sha256": quality_report_sha256,
                            "evidence_basis_sha256": evidence_basis_sha256,
                            "gap_ids": gap_ids,
                            "gap_count": len(gap_ids),
                            "skipped_group_count": skipped_group_count,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "created_at": created_at,
                },
            )
            stored = conn.execute(
                text(
                    "SELECT * FROM airank_content_gap_derivation_runs "
                    "WHERE tenant_id=:tenant_id AND id=:id"
                ),
                {"tenant_id": tenant_id, "id": derivation_run_id},
            ).mappings().one()
            return self._derivation_data(conn, stored, idempotent_replay=False)

    def list(self, tenant_id: str, project_id: str) -> EvidenceGapListData:
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
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_content_gaps
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND contract_version=:contract_version
                      AND evidence_sha256 IS NOT NULL AND deleted_at IS NULL
                    ORDER BY created_at DESC, id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "contract_version": GAP_CONTRACT_VERSION,
                },
            ).mappings().all()
            legacy_count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM airank_content_gaps
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND (contract_version IS NULL OR evidence_sha256 IS NULL)
                          AND deleted_at IS NULL
                        """
                    ),
                    {"tenant_id": tenant_id, "project_id": project_id},
                ).scalar_one()
            )
        gaps = [self._gap_data(row) for row in rows]
        return EvidenceGapListData(
            project_id=project_id,
            contract_version=GAP_CONTRACT_VERSION,
            gaps=gaps,
            governed_gap_count=len(gaps),
            unverified_legacy_count=legacy_count,
        )

    def _find_replay(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        run_id: str,
        idempotency_key: str,
        request_sha256: str,
        *,
        lock: bool = False,
    ) -> Mapping[str, object] | None:
        suffix = " FOR UPDATE" if lock and self.engine.dialect.name == "mysql" else ""
        row = conn.execute(
            text(
                """
                SELECT * FROM airank_content_gap_derivation_runs
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND (idempotency_key=:idempotency_key OR (
                    scan_run_id=:run_id AND contract_version=:contract_version
                  ))
                ORDER BY idempotency_key=:idempotency_key DESC
                LIMIT 1
                """
                + suffix
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "idempotency_key": idempotency_key,
                "run_id": run_id,
                "contract_version": GAP_CONTRACT_VERSION,
            },
        ).mappings().first()
        if row is None:
            return None
        if str(row["idempotency_key"]) == idempotency_key and str(
            row["request_sha256"]
        ) != request_sha256:
            raise error(
                409,
                "IDEMPOTENCY_CONFLICT",
                {"idempotency_key": idempotency_key},
            )
        return row

    def _derivation_data(
        self, conn: Any, row: Mapping[str, object], *, idempotent_replay: bool
    ) -> EvidenceGapDerivationData:
        gap_ids = [str(value) for value in json_value(row["gap_ids_json"], [])]
        gaps: list[EvidenceGapData] = []
        if gap_ids:
            gap_rows = conn.execute(
                text(
                    "SELECT * FROM airank_content_gaps WHERE tenant_id=:tenant_id "
                    "AND id IN :gap_ids ORDER BY id"
                ).bindparams(bindparam("gap_ids", expanding=True)),
                {"tenant_id": row["tenant_id"], "gap_ids": gap_ids},
            ).mappings().all()
            gaps = [self._gap_data(item) for item in gap_rows]
        created_at = row["created_at"]
        if isinstance(created_at, datetime) and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return EvidenceGapDerivationData(
            derivation_run_id=str(row["id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["scan_run_id"]),
            contract_version=GAP_CONTRACT_VERSION,
            derivation_policy=DERIVATION_POLICY,
            quality_report_sha256=str(row["quality_report_sha256"]),
            evidence_basis_sha256=str(row["evidence_basis_sha256"]),
            gap_count=int(row["gap_count"]),
            skipped_group_count=int(row["skipped_group_count"]),
            gaps=gaps,
            created_by=str(row["created_by"]),
            created_at=created_at,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _gap_data(row: Mapping[str, object]) -> EvidenceGapData:
        summary = json_value(row["evidence_summary_json"], {})
        if not isinstance(summary, dict):
            summary = {}
        created_at = row["created_at"]
        if isinstance(created_at, datetime) and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return EvidenceGapData(
            gap_id=str(row["id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["run_id"]),
            gap_type="brand_unmentioned",
            contract_version=GAP_CONTRACT_VERSION,
            derivation_policy=DERIVATION_POLICY,
            severity=str(row["severity"]),  # type: ignore[arg-type]
            title=str(row["title"]),
            description=str(row["description"] or ""),
            related_question_ids=[
                str(value) for value in json_value(row["related_question_ids"], [])
            ],
            provider=str(summary.get("provider") or "unknown"),
            collector_surface=str(summary.get("collector_surface") or "unknown"),
            valid_sample_count=int(summary.get("valid_sample_count") or 0),
            normal_unmentioned_count=int(
                summary.get("normal_unmentioned_count") or 0
            ),
            answer_snapshot_ids=[
                str(value) for value in json_value(row["answer_snapshot_ids"], [])
            ],
            evidence_snapshot_ids=[
                str(value) for value in json_value(row["evidence_snapshot_ids"], [])
            ],
            citation_ids=[str(value) for value in json_value(row["citation_ids"], [])],
            fact_atom_ids=[
                str(value) for value in json_value(row["fact_atom_ids"], [])
            ],
            suggested_asset_type=str(row["suggested_asset_type"] or "fact_page"),
            evidence_sha256=str(row["evidence_sha256"]),
            quality_report_sha256=str(row["quality_report_sha256"]),
            status=str(row["status"]),
            created_at=created_at,
        )


def build_repository() -> EvidenceGapRepository:
    database_url = str(os.getenv("AIRANK_DATABASE_URL") or "").strip()
    return MySQLEvidenceGapRepository(database_url) if database_url else InMemoryEvidenceGapRepository()


EVIDENCE_GAP_REPOSITORY: EvidenceGapRepository = build_repository()


@router.get(
    "/projects/{project_id}/evidence-gaps",
    response_model=EvidenceGapListResponse,
)
def list_evidence_gaps(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
) -> EvidenceGapListResponse:
    return EvidenceGapListResponse(
        data=EVIDENCE_GAP_REPOSITORY.list(tenant_id, project_id),
        meta=response_meta(
            trace_id or stable_id("trace_gap_list", tenant_id, project_id)
        ),
    )


@router.post(
    "/projects/{project_id}/evidence-gaps/derive",
    response_model=EvidenceGapDerivationResponse,
    status_code=201,
)
def derive_evidence_gaps(
    project_id: str,
    payload: DeriveEvidenceGapsRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> EvidenceGapDerivationResponse:
    effective_trace_id = trace_id or stable_id(
        "trace_gap_derive", tenant_id, project_id, payload.run_id
    )
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    return EvidenceGapDerivationResponse(
        data=EVIDENCE_GAP_REPOSITORY.derive(
            tenant_id,
            project_id,
            payload,
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=effective_trace_id,
        ),
        meta=response_meta(effective_trace_id),
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import bindparam, create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException


router = APIRouter(prefix="/api/v1", tags=["fact-acquisition"])

TASK_CONTRACT_VERSION = "airank.fact-acquisition-task.v1"
GAP_CONTRACT_VERSION = "airank.evidence-gap.v2"
AUTHORITY_POLICY = "official_or_verified_third_party.v1"


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


def json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


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


class FactAcquisitionTaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = Field(min_length=1, max_length=128)
    evidence_requirement: Optional[str] = Field(default=None, min_length=8, max_length=2000)


class FactAcquisitionEvidenceBindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_revision_ids: list[str] = Field(min_length=1, max_length=50)
    expected_version: int = Field(ge=1)
    requested_by: str = Field(min_length=1, max_length=128)

    @field_validator("fact_revision_ids")
    @classmethod
    def fact_revision_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("fact_revision_ids must contain unique values")
        return value


class FactAcquisitionTaskData(BaseModel):
    task_id: str
    project_id: str
    gap_id: str
    contract_version: Literal["airank.fact-acquisition-task.v1"]
    gap_contract_version: Literal["airank.evidence-gap.v2"]
    gap_evidence_sha256: str
    quality_report_sha256: str
    status: Literal["open", "in_review", "resolved", "blocked"]
    resolution_state: Literal[
        "needs_fact_proposal",
        "needs_fact_review",
        "ready_for_intervention",
        "blocked",
    ]
    priority: Literal["low", "medium", "high"]
    title: str
    evidence_requirement: str
    required_authority_policy: Literal["official_or_verified_third_party.v1"]
    suggested_fact_type: str
    related_question_ids: list[str]
    provider: str
    collector_surface: Literal["api", "web", "app", "manual_import"]
    knowledge_source_ids: list[str]
    fact_revision_ids: list[str]
    approved_fact_revision_ids: list[str]
    generation_allowed: bool
    event_count: int
    last_event_sha256: str
    created_by: str
    updated_by: str
    version: int
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class FactAcquisitionTaskResponse(BaseModel):
    data: FactAcquisitionTaskData
    meta: dict[str, str]


class FactAcquisitionTaskListData(BaseModel):
    project_id: str
    contract_version: Literal["airank.fact-acquisition-task.v1"]
    tasks: list[FactAcquisitionTaskData]
    open_count: int
    in_review_count: int
    resolved_count: int


class FactAcquisitionTaskListResponse(BaseModel):
    data: FactAcquisitionTaskListData
    meta: dict[str, str]


@dataclass(frozen=True)
class GapSeed:
    gap_id: str
    project_id: str
    contract_version: str
    evidence_sha256: str
    quality_report_sha256: str
    severity: str
    title: str
    related_question_ids: tuple[str, ...]
    provider: str
    collector_surface: str
    suggested_asset_type: str
    fact_atom_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RevisionSeed:
    revision_id: str
    fact_atom_id: str
    status: str
    source_ids: tuple[str, ...]
    eligible: bool


class FactAcquisitionRepository(Protocol):
    def create_task(
        self,
        tenant_id: str,
        project_id: str,
        gap_id: str,
        payload: FactAcquisitionTaskCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> FactAcquisitionTaskData: ...

    def bind_evidence(
        self,
        tenant_id: str,
        project_id: str,
        task_id: str,
        payload: FactAcquisitionEvidenceBindRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> FactAcquisitionTaskData: ...

    def list_tasks(self, tenant_id: str, project_id: str) -> FactAcquisitionTaskListData: ...


def default_requirement(gap: GapSeed) -> str:
    asset_label = gap.suggested_asset_type.replace("_", " ")
    return (
        f"为“{gap.title}”补充可公开、当前有效且能定位原文边界的企业事实；"
        f"优先使用官方或已核验第三方来源，审核通过后才可进入 {asset_label} 干预。"
    )


def suggested_fact_type(gap: GapSeed) -> str:
    if gap.suggested_asset_type == "comparison_page":
        return "competitor_diff"
    if gap.suggested_asset_type == "faq":
        return "faq"
    if gap.suggested_asset_type == "case_page":
        return "customer_case"
    if gap.suggested_asset_type == "product_page":
        return "product_service"
    return "brand_claim"


class InMemoryFactAcquisitionRepository:
    def __init__(self) -> None:
        self.gaps: dict[tuple[str, str, str], GapSeed] = {}
        self.revisions: dict[tuple[str, str, str], RevisionSeed] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.requests: dict[tuple[str, str, str], tuple[str, str]] = {}

    def seed_gap(self, tenant_id: str, gap: GapSeed) -> None:
        self.gaps[(tenant_id, gap.project_id, gap.gap_id)] = gap

    def seed_revision(self, tenant_id: str, project_id: str, revision: RevisionSeed) -> None:
        self.revisions[(tenant_id, project_id, revision.revision_id)] = revision

    def create_task(
        self,
        tenant_id: str,
        project_id: str,
        gap_id: str,
        payload: FactAcquisitionTaskCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> FactAcquisitionTaskData:
        gap = self.gaps.get((tenant_id, project_id, gap_id))
        if gap is None:
            raise error(404, "EVIDENCE_GAP_NOT_FOUND", {"gap_id": gap_id})
        _validate_gap(gap)
        request_sha256 = canonical_sha256(
            {
                "contract_version": TASK_CONTRACT_VERSION,
                "gap_id": gap_id,
                "evidence_requirement": payload.evidence_requirement,
            }
        )
        existing = next(
            (
                item
                for item in self.tasks.values()
                if item["tenant_id"] == tenant_id
                and item["project_id"] == project_id
                and item["gap_id"] == gap_id
            ),
            None,
        )
        if existing is not None:
            if str(existing["creation_request_sha256"]) != request_sha256:
                raise error(409, "IDEMPOTENCY_CONFLICT", {"gap_id": gap_id})
            return self._data(existing, idempotent_replay=True)
        task_id = stable_id("fact_task", tenant_id, project_id, gap_id, TASK_CONTRACT_VERSION)
        now = utc_now()
        task: dict[str, Any] = {
            "id": task_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "gap_id": gap_id,
            "contract_version": TASK_CONTRACT_VERSION,
            "gap_contract_version": GAP_CONTRACT_VERSION,
            "gap_evidence_sha256": gap.evidence_sha256,
            "quality_report_sha256": gap.quality_report_sha256,
            "status": "open",
            "resolution_state": "needs_fact_proposal",
            "priority": gap.severity,
            "title": f"补证：{gap.title}",
            "evidence_requirement": payload.evidence_requirement or default_requirement(gap),
            "required_authority_policy": AUTHORITY_POLICY,
            "suggested_fact_type": suggested_fact_type(gap),
            "related_question_ids": list(gap.related_question_ids),
            "provider": gap.provider,
            "collector_surface": gap.collector_surface,
            "knowledge_source_ids": [],
            "fact_revision_ids": [],
            "approved_fact_revision_ids": [],
            "creation_request_sha256": request_sha256,
            "created_by": actor,
            "updated_by": actor,
            "version": 1,
            "resolved_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.tasks[task_id] = task
        self._append_event(
            task,
            event_type="created",
            from_status=None,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
            actor=actor,
            trace_id=trace_id,
        )
        return self._data(task)

    def bind_evidence(
        self,
        tenant_id: str,
        project_id: str,
        task_id: str,
        payload: FactAcquisitionEvidenceBindRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> FactAcquisitionTaskData:
        task = self.tasks.get(task_id)
        if task is None or task["tenant_id"] != tenant_id or task["project_id"] != project_id:
            raise error(404, "FACT_ACQUISITION_TASK_NOT_FOUND", {"task_id": task_id})
        request_sha256 = _binding_request_sha256(task_id, payload)
        request_key = (tenant_id, task_id, idempotency_key)
        previous_request = self.requests.get(request_key)
        if previous_request is not None:
            previous_sha256, _ = previous_request
            if previous_sha256 != request_sha256:
                raise error(409, "IDEMPOTENCY_CONFLICT", {"task_id": task_id})
            return self._data(task, idempotent_replay=True)
        if task["status"] == "resolved":
            raise error(409, "FACT_ACQUISITION_TASK_FINAL", {"task_id": task_id})
        if task["version"] != payload.expected_version:
            raise error(
                409,
                "FACT_ACQUISITION_TASK_VERSION_CONFLICT",
                {"expected_version": payload.expected_version, "actual_version": task["version"]},
            )
        revisions: list[RevisionSeed] = []
        for revision_id in payload.fact_revision_ids:
            revision = self.revisions.get((tenant_id, project_id, revision_id))
            if revision is None:
                raise error(404, "FACT_REVISION_NOT_FOUND", {"revision_id": revision_id})
            if not revision.source_ids:
                raise error(409, "FACT_SOURCE_REQUIRED", {"revision_id": revision_id})
            revisions.append(revision)
        from_status = str(task["status"])
        all_eligible = all(revision.status == "approved" and revision.eligible for revision in revisions)
        source_ids = sorted({source_id for revision in revisions for source_id in revision.source_ids})
        approved_revision_ids = [
            revision.revision_id
            for revision in revisions
            if revision.status == "approved" and revision.eligible
        ]
        task.update(
            knowledge_source_ids=source_ids,
            fact_revision_ids=list(payload.fact_revision_ids),
            approved_fact_revision_ids=approved_revision_ids,
            status="resolved" if all_eligible else "in_review",
            resolution_state="ready_for_intervention" if all_eligible else "needs_fact_review",
            updated_by=actor,
            version=int(task["version"]) + 1,
            resolved_at=utc_now() if all_eligible else None,
            updated_at=utc_now(),
        )
        self._append_event(
            task,
            event_type="resolved" if all_eligible else "evidence_bound",
            from_status=from_status,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
            actor=actor,
            trace_id=trace_id,
        )
        self.requests[request_key] = (request_sha256, task_id)
        return self._data(task)

    def list_tasks(self, tenant_id: str, project_id: str) -> FactAcquisitionTaskListData:
        tasks = [
            self._data(item)
            for item in sorted(
                self.tasks.values(),
                key=lambda item: (item["created_at"], item["id"]),
                reverse=True,
            )
            if item["tenant_id"] == tenant_id and item["project_id"] == project_id
        ]
        return _task_list(project_id, tasks)

    def _append_event(
        self,
        task: Mapping[str, Any],
        *,
        event_type: str,
        from_status: Optional[str],
        idempotency_key: str,
        request_sha256: str,
        actor: str,
        trace_id: str,
    ) -> None:
        events = self.events.setdefault(str(task["id"]), [])
        previous = events[-1]["event_sha256"] if events else None
        payload = _event_payload(task)
        event_sha256 = _event_sha256(
            task_id=str(task["id"]),
            event_type=event_type,
            from_status=from_status,
            to_status=str(task["status"]),
            version=int(task["version"]),
            request_sha256=request_sha256,
            previous_event_sha256=previous,
            payload=payload,
        )
        events.append(
            {
                "event_sha256": event_sha256,
                "idempotency_key": idempotency_key,
                "request_sha256": request_sha256,
                "payload": payload,
                "actor": actor,
                "trace_id": trace_id,
            }
        )
        self.requests[(str(task["tenant_id"]), str(task["id"]), idempotency_key)] = (
            request_sha256,
            str(task["id"]),
        )

    def _data(self, task: Mapping[str, Any], *, idempotent_replay: bool = False) -> FactAcquisitionTaskData:
        events = self.events.get(str(task["id"]), [])
        return _task_data(
            task,
            event_count=len(events),
            last_event_sha256=str(events[-1]["event_sha256"]) if events else "",
            idempotent_replay=idempotent_replay,
        )


def _validate_gap(gap: GapSeed) -> None:
    if gap.contract_version != GAP_CONTRACT_VERSION:
        raise error(
            409,
            "FACT_ACQUISITION_GAP_INELIGIBLE",
            {"gap_id": gap.gap_id, "reason": "unverified_gap_contract"},
        )
    if len(gap.evidence_sha256) != 64 or len(gap.quality_report_sha256) != 64:
        raise error(
            409,
            "FACT_ACQUISITION_GAP_INELIGIBLE",
            {"gap_id": gap.gap_id, "reason": "immutable_evidence_hash_missing"},
        )
    if gap.fact_atom_ids:
        raise error(
            409,
            "FACT_ACQUISITION_GAP_INELIGIBLE",
            {"gap_id": gap.gap_id, "reason": "gap_already_has_fact_evidence"},
        )


def _binding_request_sha256(task_id: str, payload: FactAcquisitionEvidenceBindRequest) -> str:
    return canonical_sha256(
        {
            "contract_version": TASK_CONTRACT_VERSION,
            "task_id": task_id,
            "fact_revision_ids": sorted(payload.fact_revision_ids),
            "expected_version": payload.expected_version,
        }
    )


def _event_payload(task: Mapping[str, Any]) -> dict[str, object]:
    return {
        "contract_version": TASK_CONTRACT_VERSION,
        "gap_id": str(task["gap_id"]),
        "gap_evidence_sha256": str(task["gap_evidence_sha256"]),
        "quality_report_sha256": str(task["quality_report_sha256"]),
        "status": str(task["status"]),
        "resolution_state": str(task["resolution_state"]),
        "knowledge_source_ids": list(task["knowledge_source_ids"]),
        "fact_revision_ids": list(task["fact_revision_ids"]),
        "approved_fact_revision_ids": list(task["approved_fact_revision_ids"]),
    }


def _event_sha256(
    *,
    task_id: str,
    event_type: str,
    from_status: Optional[str],
    to_status: str,
    version: int,
    request_sha256: str,
    previous_event_sha256: Optional[str],
    payload: Mapping[str, object],
) -> str:
    return canonical_sha256(
        {
            "task_id": task_id,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "task_version": version,
            "request_sha256": request_sha256,
            "previous_event_sha256": previous_event_sha256,
            "payload": dict(payload),
        }
    )


def _task_data(
    task: Mapping[str, Any],
    *,
    event_count: int,
    last_event_sha256: str,
    idempotent_replay: bool = False,
) -> FactAcquisitionTaskData:
    return FactAcquisitionTaskData(
        task_id=str(task.get("id") or task.get("task_id")),
        project_id=str(task["project_id"]),
        gap_id=str(task["gap_id"]),
        contract_version=str(task["contract_version"]),
        gap_contract_version=str(task["gap_contract_version"]),
        gap_evidence_sha256=str(task["gap_evidence_sha256"]),
        quality_report_sha256=str(task["quality_report_sha256"]),
        status=str(task["status"]),
        resolution_state=str(task["resolution_state"]),
        priority=str(task["priority"]),
        title=str(task["title"]),
        evidence_requirement=str(task["evidence_requirement"]),
        required_authority_policy=str(task["required_authority_policy"]),
        suggested_fact_type=str(task["suggested_fact_type"]),
        related_question_ids=json_list(task["related_question_ids"]),
        provider=str(task["provider"]),
        collector_surface=str(task["collector_surface"]),
        knowledge_source_ids=json_list(task["knowledge_source_ids"]),
        fact_revision_ids=json_list(task["fact_revision_ids"]),
        approved_fact_revision_ids=json_list(task["approved_fact_revision_ids"]),
        generation_allowed=str(task["status"]) == "resolved",
        event_count=event_count,
        last_event_sha256=last_event_sha256,
        created_by=str(task["created_by"]),
        updated_by=str(task["updated_by"]),
        version=int(task["version"]),
        resolved_at=task.get("resolved_at"),
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        idempotent_replay=idempotent_replay,
    )


def _task_list(project_id: str, tasks: list[FactAcquisitionTaskData]) -> FactAcquisitionTaskListData:
    return FactAcquisitionTaskListData(
        project_id=project_id,
        contract_version=TASK_CONTRACT_VERSION,
        tasks=tasks,
        open_count=sum(task.status == "open" for task in tasks),
        in_review_count=sum(task.status == "in_review" for task in tasks),
        resolved_count=sum(task.status == "resolved" for task in tasks),
    )


class MySQLFactAcquisitionRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create_task(
        self,
        tenant_id: str,
        project_id: str,
        gap_id: str,
        payload: FactAcquisitionTaskCreateRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> FactAcquisitionTaskData:
        request_sha256 = canonical_sha256(
            {
                "contract_version": TASK_CONTRACT_VERSION,
                "gap_id": gap_id,
                "evidence_requirement": payload.evidence_requirement,
            }
        )
        with self.engine.begin() as conn:
            existing = self._find_task_by_gap(conn, tenant_id, project_id, gap_id, lock=True)
            if existing is not None:
                if str(existing["creation_request_sha256"]) != request_sha256:
                    raise error(409, "IDEMPOTENCY_CONFLICT", {"gap_id": gap_id})
                return self._data(conn, existing, idempotent_replay=True)
            gap_row = conn.execute(
                text(
                    """
                    SELECT id, project_id, contract_version, evidence_sha256,
                           quality_report_sha256, severity, title,
                           related_question_ids, evidence_summary_json,
                           suggested_asset_type, fact_atom_ids
                    FROM airank_content_gaps
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND id=:gap_id AND deleted_at IS NULL
                    """
                    + (" FOR UPDATE" if self.engine.dialect.name == "mysql" else "")
                ),
                {"tenant_id": tenant_id, "project_id": project_id, "gap_id": gap_id},
            ).mappings().first()
            if gap_row is None:
                raise error(404, "EVIDENCE_GAP_NOT_FOUND", {"gap_id": gap_id})
            summary = gap_row["evidence_summary_json"]
            if not isinstance(summary, dict):
                try:
                    summary = json.loads(str(summary or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    summary = {}
            gap = GapSeed(
                gap_id=str(gap_row["id"]),
                project_id=str(gap_row["project_id"]),
                contract_version=str(gap_row["contract_version"] or ""),
                evidence_sha256=str(gap_row["evidence_sha256"] or ""),
                quality_report_sha256=str(gap_row["quality_report_sha256"] or ""),
                severity=str(gap_row["severity"]),
                title=str(gap_row["title"]),
                related_question_ids=tuple(json_list(gap_row["related_question_ids"])),
                provider=str(summary.get("provider") or "unknown"),
                collector_surface=str(summary.get("collector_surface") or "api"),
                suggested_asset_type=str(gap_row["suggested_asset_type"] or "fact_page"),
                fact_atom_ids=tuple(json_list(gap_row["fact_atom_ids"])),
            )
            _validate_gap(gap)
            task_id = stable_id("fact_task", tenant_id, project_id, gap_id, TASK_CONTRACT_VERSION)
            now = utc_now().replace(tzinfo=None)
            requirement = payload.evidence_requirement or default_requirement(gap)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_fact_acquisition_tasks (
                      id, tenant_id, project_id, gap_id, contract_version,
                      gap_contract_version, gap_evidence_sha256,
                      quality_report_sha256, status, resolution_state,
                      priority, title, evidence_requirement,
                      required_authority_policy, suggested_fact_type,
                      related_question_ids, provider, collector_surface,
                      knowledge_source_ids, fact_revision_ids,
                      approved_fact_revision_ids, creation_idempotency_key,
                      creation_request_sha256, created_by, updated_by,
                      version, resolved_at, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :gap_id, :contract_version,
                      :gap_contract_version, :gap_evidence_sha256,
                      :quality_report_sha256, 'open', 'needs_fact_proposal',
                      :priority, :title, :evidence_requirement,
                      :required_authority_policy, :suggested_fact_type,
                      :related_question_ids, :provider, :collector_surface,
                      JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY(),
                      :idempotency_key, :request_sha256, :actor, :actor,
                      1, NULL, :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": task_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "gap_id": gap_id,
                    "contract_version": TASK_CONTRACT_VERSION,
                    "gap_contract_version": GAP_CONTRACT_VERSION,
                    "gap_evidence_sha256": gap.evidence_sha256,
                    "quality_report_sha256": gap.quality_report_sha256,
                    "priority": gap.severity,
                    "title": f"补证：{gap.title}",
                    "evidence_requirement": requirement,
                    "required_authority_policy": AUTHORITY_POLICY,
                    "suggested_fact_type": suggested_fact_type(gap),
                    "related_question_ids": json.dumps(list(gap.related_question_ids), ensure_ascii=False),
                    "provider": gap.provider,
                    "collector_surface": gap.collector_surface,
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "actor": actor[:128],
                    "created_at": now,
                },
            )
            task = conn.execute(
                text("SELECT * FROM airank_fact_acquisition_tasks WHERE id=:id"),
                {"id": task_id},
            ).mappings().one()
            self._append_event(
                conn,
                task,
                event_type="created",
                from_status=None,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                created_at=now,
            )
            self._append_audit(conn, task, "fact_acquisition.created", actor, trace_id, now)
            return self._data(conn, task)

    def bind_evidence(
        self,
        tenant_id: str,
        project_id: str,
        task_id: str,
        payload: FactAcquisitionEvidenceBindRequest,
        *,
        idempotency_key: str,
        actor: str,
        trace_id: str,
    ) -> FactAcquisitionTaskData:
        request_sha256 = _binding_request_sha256(task_id, payload)
        with self.engine.begin() as conn:
            task = self._find_task(conn, tenant_id, project_id, task_id, lock=True)
            if task is None:
                raise error(404, "FACT_ACQUISITION_TASK_NOT_FOUND", {"task_id": task_id})
            replay = conn.execute(
                text(
                    """
                    SELECT request_sha256 FROM airank_fact_acquisition_task_events
                    WHERE tenant_id=:tenant_id AND task_id=:task_id
                      AND idempotency_key=:idempotency_key
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "task_id": task_id,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
            if replay is not None:
                if str(replay["request_sha256"]) != request_sha256:
                    raise error(409, "IDEMPOTENCY_CONFLICT", {"task_id": task_id})
                return self._data(conn, task, idempotent_replay=True)
            if str(task["status"]) == "resolved":
                raise error(409, "FACT_ACQUISITION_TASK_FINAL", {"task_id": task_id})
            if int(task["version"]) != payload.expected_version:
                raise error(
                    409,
                    "FACT_ACQUISITION_TASK_VERSION_CONFLICT",
                    {"expected_version": payload.expected_version, "actual_version": int(task["version"])},
                )
            revision_query = text(
                """
                SELECT r.id, r.fact_atom_id, r.fact_text, r.status, r.source_ids_json,
                       r.valid_from, r.valid_until, r.reviewed_by, r.reviewed_at,
                       f.current_revision_id, f.status AS fact_status,
                       f.disclosure, f.valid_until AS fact_valid_until
                FROM airank_fact_revisions r
                JOIN airank_fact_atoms f
                  ON f.tenant_id=r.tenant_id AND f.project_id=r.project_id
                 AND f.id=r.fact_atom_id AND f.deleted_at IS NULL
                WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id
                  AND r.id IN :revision_ids
                ORDER BY r.id
                """
            ).bindparams(bindparam("revision_ids", expanding=True))
            revisions = conn.execute(
                revision_query,
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "revision_ids": payload.fact_revision_ids,
                },
            ).mappings().all()
            if len(revisions) != len(payload.fact_revision_ids):
                found = {str(row["id"]) for row in revisions}
                missing = [item for item in payload.fact_revision_ids if item not in found]
                raise error(404, "FACT_REVISION_NOT_FOUND", {"revision_ids": missing})
            source_ids = sorted(
                {
                    source_id
                    for revision in revisions
                    for source_id in json_list(revision["source_ids_json"])
                }
            )
            if not source_ids:
                raise error(409, "FACT_SOURCE_REQUIRED", {"fact_revision_ids": payload.fact_revision_ids})
            source_query = text(
                """
                SELECT s.id, s.status, s.authority_level, s.valid_from,
                       s.valid_until, s.content_sha256 AS source_content_sha256,
                       c.content_text, c.content_sha256
                FROM airank_knowledge_sources s
                JOIN airank_knowledge_source_contents c
                  ON c.tenant_id=s.tenant_id AND c.project_id=s.project_id
                 AND c.knowledge_source_id=s.id
                WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                  AND s.id IN :source_ids
                """
            ).bindparams(bindparam("source_ids", expanding=True))
            sources = conn.execute(
                source_query,
                {"tenant_id": tenant_id, "project_id": project_id, "source_ids": source_ids},
            ).mappings().all()
            if len(sources) != len(source_ids):
                found_sources = {str(row["id"]) for row in sources}
                raise error(
                    409,
                    "FACT_ACQUISITION_EVIDENCE_INVALID",
                    {"reason": "source_not_found", "source_ids": [item for item in source_ids if item not in found_sources]},
                )
            now_aware = utc_now()
            now = now_aware.replace(tzinfo=None)
            source_blockers = _source_blockers(sources, now_aware)
            if source_blockers:
                raise error(
                    409,
                    "FACT_ACQUISITION_EVIDENCE_INVALID",
                    {"reason": "source_not_current_or_authoritative", "source_ids": source_blockers},
                )
            source_by_id = {str(source["id"]): source for source in sources}
            exact_boundary_missing = [
                str(revision["id"])
                for revision in revisions
                if not revision_has_exact_source_support(revision, source_by_id)
            ]
            if exact_boundary_missing:
                raise error(
                    409,
                    "FACT_ACQUISITION_EVIDENCE_INVALID",
                    {
                        "reason": "exact_source_boundary_missing",
                        "fact_revision_ids": exact_boundary_missing,
                    },
                )
            fact_ids = sorted({str(row["fact_atom_id"]) for row in revisions})
            conflict_query = text(
                """
                SELECT DISTINCT fact_atom_id FROM airank_fact_conflicts
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND fact_atom_id IN :fact_ids AND status='open'
                """
            ).bindparams(bindparam("fact_ids", expanding=True))
            conflict_ids = {
                str(row["fact_atom_id"])
                for row in conn.execute(
                    conflict_query,
                    {"tenant_id": tenant_id, "project_id": project_id, "fact_ids": fact_ids},
                ).mappings().all()
            }
            eligible_ids = [
                str(row["id"])
                for row in revisions
                if _revision_is_eligible(row, now_aware, conflict_ids)
            ]
            all_eligible = len(eligible_ids) == len(revisions)
            from_status = str(task["status"])
            next_status = "resolved" if all_eligible else "in_review"
            resolution_state = "ready_for_intervention" if all_eligible else "needs_fact_review"
            next_version = int(task["version"]) + 1
            conn.execute(
                text(
                    """
                    UPDATE airank_fact_acquisition_tasks
                    SET knowledge_source_ids=:source_ids,
                        fact_revision_ids=:revision_ids,
                        approved_fact_revision_ids=:approved_ids,
                        status=:status, resolution_state=:resolution_state,
                        updated_by=:actor, version=:version,
                        resolved_at=:resolved_at, updated_at=:updated_at
                    WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:task_id
                    """
                ),
                {
                    "source_ids": json.dumps(source_ids, ensure_ascii=False),
                    "revision_ids": json.dumps(payload.fact_revision_ids, ensure_ascii=False),
                    "approved_ids": json.dumps(eligible_ids, ensure_ascii=False),
                    "status": next_status,
                    "resolution_state": resolution_state,
                    "actor": actor[:128],
                    "version": next_version,
                    "resolved_at": now if all_eligible else None,
                    "updated_at": now,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "task_id": task_id,
                },
            )
            if all_eligible:
                conn.execute(
                    text(
                        """
                        UPDATE airank_content_gaps
                        SET fact_atom_ids=:fact_ids, status='ready_for_intervention',
                            updated_at=:updated_at
                        WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:gap_id
                        """
                    ),
                    {
                        "fact_ids": json.dumps(fact_ids, ensure_ascii=False),
                        "updated_at": now,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "gap_id": str(task["gap_id"]),
                    },
                )
            updated = self._find_task(conn, tenant_id, project_id, task_id, lock=False)
            assert updated is not None
            event_type = "resolved" if all_eligible else "evidence_bound"
            self._append_event(
                conn,
                updated,
                event_type=event_type,
                from_status=from_status,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                actor=actor,
                trace_id=trace_id,
                created_at=now,
            )
            self._append_audit(
                conn,
                updated,
                f"fact_acquisition.{event_type}",
                actor,
                trace_id,
                now,
            )
            return self._data(conn, updated)

    def list_tasks(self, tenant_id: str, project_id: str) -> FactAcquisitionTaskListData:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_fact_acquisition_tasks
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                    ORDER BY FIELD(priority, 'high', 'medium', 'low'), created_at DESC, id DESC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
            return _task_list(project_id, [self._data(conn, row) for row in rows])

    def _find_task_by_gap(
        self, conn: Any, tenant_id: str, project_id: str, gap_id: str, *, lock: bool
    ) -> Optional[Mapping[str, Any]]:
        query = (
            "SELECT * FROM airank_fact_acquisition_tasks "
            "WHERE tenant_id=:tenant_id AND project_id=:project_id "
            "AND gap_id=:gap_id AND contract_version=:contract_version"
        )
        if lock and self.engine.dialect.name == "mysql":
            query += " FOR UPDATE"
        return conn.execute(
            text(query),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "gap_id": gap_id,
                "contract_version": TASK_CONTRACT_VERSION,
            },
        ).mappings().first()

    def _find_task(
        self, conn: Any, tenant_id: str, project_id: str, task_id: str, *, lock: bool
    ) -> Optional[Mapping[str, Any]]:
        query = (
            "SELECT * FROM airank_fact_acquisition_tasks "
            "WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:task_id"
        )
        if lock and self.engine.dialect.name == "mysql":
            query += " FOR UPDATE"
        return conn.execute(
            text(query),
            {"tenant_id": tenant_id, "project_id": project_id, "task_id": task_id},
        ).mappings().first()

    def _append_event(
        self,
        conn: Any,
        task: Mapping[str, Any],
        *,
        event_type: str,
        from_status: Optional[str],
        idempotency_key: str,
        request_sha256: str,
        actor: str,
        trace_id: str,
        created_at: datetime,
    ) -> None:
        previous_event_sha256 = conn.execute(
            text(
                """
                SELECT event_sha256 FROM airank_fact_acquisition_task_events
                WHERE tenant_id=:tenant_id AND task_id=:task_id
                ORDER BY task_version DESC LIMIT 1
                """
            ),
            {"tenant_id": task["tenant_id"], "task_id": task["id"]},
        ).scalar_one_or_none()
        normalized_task = dict(task)
        for key in ("related_question_ids", "knowledge_source_ids", "fact_revision_ids", "approved_fact_revision_ids"):
            normalized_task[key] = json_list(task[key])
        payload = _event_payload(normalized_task)
        event_sha256 = _event_sha256(
            task_id=str(task["id"]),
            event_type=event_type,
            from_status=from_status,
            to_status=str(task["status"]),
            version=int(task["version"]),
            request_sha256=request_sha256,
            previous_event_sha256=(str(previous_event_sha256) if previous_event_sha256 else None),
            payload=payload,
        )
        event_id = stable_id(
            "fact_task_event", str(task["tenant_id"]), str(task["id"]), str(task["version"])
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_fact_acquisition_task_events (
                  id, tenant_id, project_id, task_id, event_type,
                  from_status, to_status, task_version, idempotency_key,
                  request_sha256, previous_event_sha256, event_sha256,
                  actor_user_id, trace_id, payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :task_id, :event_type,
                  :from_status, :to_status, :task_version, :idempotency_key,
                  :request_sha256, :previous_event_sha256, :event_sha256,
                  :actor, :trace_id, :payload_json, :created_at
                )
                """
            ),
            {
                "id": event_id,
                "tenant_id": task["tenant_id"],
                "project_id": task["project_id"],
                "task_id": task["id"],
                "event_type": event_type,
                "from_status": from_status,
                "to_status": task["status"],
                "task_version": task["version"],
                "idempotency_key": idempotency_key,
                "request_sha256": request_sha256,
                "previous_event_sha256": previous_event_sha256,
                "event_sha256": event_sha256,
                "actor": actor[:128],
                "trace_id": trace_id[:128],
                "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                "created_at": created_at,
            },
        )

    def _append_audit(
        self,
        conn: Any,
        task: Mapping[str, Any],
        event_type: str,
        actor: str,
        trace_id: str,
        created_at: datetime,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO airank_audit_events (
                  id, tenant_id, project_id, actor_user_id, event_type,
                  entity_type, entity_id, trace_id, payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :actor, :event_type,
                  'fact_acquisition_task', :task_id, :trace_id,
                  :payload_json, :created_at
                )
                """
            ),
            {
                "id": f"audit_fact_task_{uuid4().hex[:16]}",
                "tenant_id": task["tenant_id"],
                "project_id": task["project_id"],
                "actor": actor[:64],
                "event_type": event_type,
                "task_id": task["id"],
                "trace_id": trace_id[:128],
                "payload_json": json.dumps(
                    {
                        "contract_version": TASK_CONTRACT_VERSION,
                        "gap_id": str(task["gap_id"]),
                        "task_version": int(task["version"]),
                        "status": str(task["status"]),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "created_at": created_at,
            },
        )

    def _data(
        self,
        conn: Any,
        task: Mapping[str, Any],
        *,
        idempotent_replay: bool = False,
    ) -> FactAcquisitionTaskData:
        event_row = conn.execute(
            text(
                """
                SELECT COUNT(*) AS event_count, MAX(task_version) AS max_version
                FROM airank_fact_acquisition_task_events
                WHERE tenant_id=:tenant_id AND task_id=:task_id
                """
            ),
            {"tenant_id": task["tenant_id"], "task_id": task["id"]},
        ).mappings().one()
        last_event_sha256 = conn.execute(
            text(
                """
                SELECT event_sha256 FROM airank_fact_acquisition_task_events
                WHERE tenant_id=:tenant_id AND task_id=:task_id
                ORDER BY task_version DESC LIMIT 1
                """
            ),
            {"tenant_id": task["tenant_id"], "task_id": task["id"]},
        ).scalar_one_or_none()
        return _task_data(
            task,
            event_count=int(event_row["event_count"]),
            last_event_sha256=str(last_event_sha256 or ""),
            idempotent_replay=idempotent_replay,
        )


def _source_blockers(sources: list[Mapping[str, Any]], at: datetime) -> list[str]:
    blockers: list[str] = []
    at_naive = at.replace(tzinfo=None)
    for source in sources:
        invalid = str(source["status"]) != "active"
        invalid = invalid or str(source["authority_level"]) not in {
            "official",
            "verified_third_party",
        }
        valid_from = source.get("valid_from")
        valid_until = source.get("valid_until")
        invalid = invalid or (valid_from is not None and valid_from > at_naive)
        invalid = invalid or (valid_until is not None and valid_until <= at_naive)
        if invalid:
            blockers.append(str(source["id"]))
    return blockers


def revision_has_exact_source_support(
    revision: Mapping[str, Any], source_by_id: Mapping[str, Mapping[str, Any]]
) -> bool:
    for source_id in json_list(revision["source_ids_json"]):
        source = source_by_id.get(source_id)
        if source is None:
            continue
        content_text = str(source["content_text"])
        content_sha256 = hashlib.sha256(content_text.encode("utf-8")).hexdigest()
        if (
            content_sha256 == str(source["content_sha256"])
            and content_sha256 == str(source["source_content_sha256"])
            and content_text.find(str(revision["fact_text"])) >= 0
        ):
            return True
    return False


def _revision_is_eligible(
    revision: Mapping[str, Any], at: datetime, conflict_fact_ids: set[str]
) -> bool:
    at_naive = at.replace(tzinfo=None)
    return all(
        (
            str(revision["status"]) == "approved",
            str(revision["current_revision_id"] or "") == str(revision["id"]),
            str(revision["fact_status"]) == "confirmed",
            str(revision["disclosure"]) in {"public", "redacted"},
            revision["reviewed_by"] is not None,
            revision["reviewed_at"] is not None,
            revision["valid_from"] is None or revision["valid_from"] <= at_naive,
            revision["valid_until"] is None or revision["valid_until"] > at_naive,
            revision["fact_valid_until"] is None or revision["fact_valid_until"] > at_naive,
            str(revision["fact_atom_id"]) not in conflict_fact_ids,
        )
    )


def build_repository() -> FactAcquisitionRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL", "").strip()
    if database_url:
        return MySQLFactAcquisitionRepository(database_url)
    return InMemoryFactAcquisitionRepository()


FACT_ACQUISITION_REPOSITORY: FactAcquisitionRepository = build_repository()


@router.get(
    "/projects/{project_id}/fact-acquisition-tasks",
    response_model=FactAcquisitionTaskListResponse,
)
def list_fact_acquisition_tasks(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
) -> FactAcquisitionTaskListResponse:
    effective_trace_id = trace_id or stable_id("trace_fact_task_list", tenant_id, project_id)
    return FactAcquisitionTaskListResponse(
        data=FACT_ACQUISITION_REPOSITORY.list_tasks(tenant_id, project_id),
        meta=response_meta(effective_trace_id),
    )


@router.post(
    "/projects/{project_id}/evidence-gaps/{gap_id}/fact-acquisition-tasks",
    response_model=FactAcquisitionTaskResponse,
    status_code=201,
)
def create_fact_acquisition_task(
    project_id: str,
    gap_id: str,
    payload: FactAcquisitionTaskCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> FactAcquisitionTaskResponse:
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    effective_trace_id = trace_id or stable_id("trace_fact_task_create", tenant_id, gap_id)
    return FactAcquisitionTaskResponse(
        data=FACT_ACQUISITION_REPOSITORY.create_task(
            tenant_id,
            project_id,
            gap_id,
            payload,
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=effective_trace_id,
        ),
        meta=response_meta(effective_trace_id),
    )


@router.post(
    "/projects/{project_id}/fact-acquisition-tasks/{task_id}/evidence-bindings",
    response_model=FactAcquisitionTaskResponse,
    status_code=201,
)
def bind_fact_acquisition_evidence(
    project_id: str,
    task_id: str,
    payload: FactAcquisitionEvidenceBindRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> FactAcquisitionTaskResponse:
    actor = trusted_actor(payload.requested_by, authenticated_actor)
    effective_trace_id = trace_id or stable_id("trace_fact_task_bind", tenant_id, task_id)
    return FactAcquisitionTaskResponse(
        data=FACT_ACQUISITION_REPOSITORY.bind_evidence(
            tenant_id,
            project_id,
            task_id,
            payload,
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=effective_trace_id,
        ),
        meta=response_meta(effective_trace_id),
    )

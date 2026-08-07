from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
from typing import Any, Literal, Mapping, Optional, Protocol, Sequence
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import (
    ObservedQuestionSeed,
    TAXONOMY_VERSION,
    compile_question_candidates,
    normalize_question,
    question_dedupe_sha256,
    sha256_text,
)


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["question-governance"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    if not authenticated_actor:
        raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})
    return authenticated_actor


def unique_normalized(values: Sequence[str]) -> list[str]:
    unique: dict[str, str] = {}
    for value in values:
        normalized = normalize_question(value)
        if normalized:
            unique.setdefault(normalized.casefold(), normalized)
    return list(unique.values())


PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("cn_identity_number", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
)


def detected_pii_reasons(value: str) -> list[str]:
    return [name for name, pattern in PII_PATTERNS if pattern.search(value)]


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def observation_payload_sha256(payload: "QuestionObservationImportRequest") -> str:
    canonical = {
        "contract": "airank.question-observation-import.v1",
        "source_type": payload.source_type,
        "source_name": normalize_question(payload.source_name),
        "source_uri": payload.source_uri,
        "date_range_start": as_utc(payload.date_range_start).isoformat() if payload.date_range_start else None,
        "date_range_end": as_utc(payload.date_range_end).isoformat() if payload.date_range_end else None,
        "records": [
            {
                "source_record_id": item.source_record_id or f"row:{index}",
                "question_text": item.question_text,
                "occurrence_count": item.occurrence_count,
                "observed_at": as_utc(item.observed_at).isoformat() if item.observed_at else None,
                "region": item.region,
                "audience_role": item.audience_role,
            }
            for index, item in enumerate(payload.records, start=1)
        ],
    }
    return sha256_text(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


class QuestionMapCompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_names: list[str] = Field(default_factory=list, max_length=20)
    product_terms: list[str] = Field(default_factory=list, max_length=30)
    competitor_names: list[str] = Field(default_factory=list, max_length=30)
    regions: list[str] = Field(default_factory=list, max_length=30)
    seed_questions: list[str] = Field(default_factory=list, max_length=200)
    observation_batch_ids: list[str] = Field(default_factory=list, max_length=50)
    include_template_candidates: bool = True
    persist: bool = True
    created_by: str = Field(min_length=1, max_length=64)

    @field_validator("company_names", "product_terms", "competitor_names", "regions", "seed_questions")
    @classmethod
    def values_must_be_nonempty(cls, value: list[str]) -> list[str]:
        normalized = [normalize_question(item) for item in value]
        if any(not item for item in normalized):
            raise ValueError("values must be non-empty after normalization")
        return normalized

    @field_validator("observation_batch_ids")
    @classmethod
    def observation_batches_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("observation_batch_ids must be unique")
        return value


ObservationSourceType = Literal[
    "site_search",
    "search_console",
    "customer_support",
    "crm_sales",
    "advertising_query",
    "community_comment",
    "provider_sample",
    "other",
]


class QuestionObservationRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_record_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    question_text: str = Field(min_length=4, max_length=500)
    occurrence_count: int = Field(default=1, ge=1, le=1_000_000)
    observed_at: Optional[datetime] = None
    region: Optional[str] = Field(default=None, min_length=1, max_length=128)
    audience_role: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @field_validator("question_text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_question(value)


class QuestionObservationImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: ObservationSourceType
    source_name: str = Field(min_length=2, max_length=255)
    source_uri: Optional[str] = Field(default=None, max_length=2048)
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    records: list[QuestionObservationRecordRequest] = Field(min_length=1, max_length=1000)
    rights_attested: bool
    imported_by: str = Field(min_length=1, max_length=64)

    @field_validator("rights_attested")
    @classmethod
    def rights_must_be_attested(cls, value: bool) -> bool:
        if not value:
            raise ValueError("rights_attested must be true")
        return value

    @model_validator(mode="after")
    def validate_range_and_record_ids(self) -> "QuestionObservationImportRequest":
        if self.date_range_start and self.date_range_end:
            if as_utc(self.date_range_start) > as_utc(self.date_range_end):
                raise ValueError("date_range_start must not be after date_range_end")
        resolved_ids = [item.source_record_id or f"row:{index}" for index, item in enumerate(self.records, start=1)]
        if len(resolved_ids) != len(set(resolved_ids)):
            raise ValueError("source_record_id must be unique within a batch")
        return self


class BlockedObservationRecord(BaseModel):
    row_number: int
    content_sha256: str
    reasons: list[str]


class QuestionObservationRecordData(BaseModel):
    observation_id: str
    batch_id: str
    row_number: int
    source_record_id: str
    question_text: str
    normalized_question_text: str
    dedupe_sha256: str
    occurrence_count: int
    observed_at: Optional[datetime] = None
    region: Optional[str] = None
    audience_role: Optional[str] = None
    content_sha256: str
    pii_status: Literal["none_detected"] = "none_detected"
    created_at: datetime


class QuestionObservationBatchData(BaseModel):
    batch_id: str
    tenant_id: str
    project_id: str
    source_type: ObservationSourceType
    source_name: str
    access_mode: Literal["user_provided"] = "user_provided"
    evidence_grade: Literal["user_provided_snapshot"] = "user_provided_snapshot"
    source_uri: Optional[str] = None
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    payload_sha256: str
    record_count: int
    occurrence_count: int
    pii_blocked_count: int
    status: Literal["ready", "blocked"]
    rights_attested: bool
    imported_by: str
    created_at: datetime
    blocked_records: list[BlockedObservationRecord] = Field(default_factory=list)
    idempotent_replay: bool = False


class QuestionObservationImportData(BaseModel):
    batch: QuestionObservationBatchData
    records: list[QuestionObservationRecordData]


class QuestionObservationImportResponse(BaseModel):
    data: QuestionObservationImportData
    meta: dict[str, str]


class QuestionObservationBatchListResponse(BaseModel):
    data: list[QuestionObservationBatchData]
    meta: dict[str, str]


class QuestionObservationRecordListResponse(BaseModel):
    data: list[QuestionObservationRecordData]
    meta: dict[str, str]


class QuestionCandidateData(BaseModel):
    question_id: Optional[str] = None
    duplicate_of_question_id: Optional[str] = None
    question_text: str
    dedupe_sha256: str
    question_version_id: str
    taxonomy_version: str
    question_type: str
    intent_level: str
    buyer_stage: str
    prompt_style: str
    temporal_scope: str
    scenario: str
    region: Optional[str] = None
    cohort_type: Literal["blind", "assisted", "comparison", "fact_verification"]
    source_kind: Literal["provided_seed", "template_candidate", "observed_query", "imported"]
    source_ref: str
    evidence_level: Literal["provided_seed", "template_candidate", "observed_query", "imported"]
    observed_query: bool
    deduplicated_source_refs: list[str]
    provenance_records: list[dict[str, Any]]
    status: Literal["preview", "suggested", "confirmed", "archived", "duplicate"]


class QuestionMapData(BaseModel):
    map_id: str
    map_version_id: str
    tenant_id: str
    project_id: str
    taxonomy_version: str
    input_sha256: str
    status: Literal["preview", "compiled"]
    question_count: int
    duplicate_count: int
    persisted_count: int
    idempotent_replay: bool = False
    created_by: str
    created_at: datetime
    questions: list[QuestionCandidateData]


class QuestionMapResponse(BaseModel):
    data: QuestionMapData
    meta: dict[str, str]


class QuestionMapListResponse(BaseModel):
    data: list[QuestionMapData]
    meta: dict[str, str]


class QuestionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["confirmed", "archived"]
    reviewed_by: str = Field(min_length=1, max_length=64)
    review_note: str = Field(min_length=3, max_length=1000)


class QuestionReviewData(BaseModel):
    review_id: str
    tenant_id: str
    project_id: str
    question_id: str
    question_revision_id: str
    previous_status: Literal["suggested", "confirmed", "archived"]
    status: Literal["confirmed", "archived"]
    reviewed_by: str
    reviewed_at: datetime
    review_note: str
    eligible_for_measurement: bool
    idempotent_replay: bool = False


class QuestionReviewResponse(BaseModel):
    data: QuestionReviewData
    meta: dict[str, str]


class QuestionGovernanceRepository(Protocol):
    def import_observations(
        self,
        tenant_id: str,
        project_id: str,
        payload: QuestionObservationImportRequest,
        actor: str,
    ) -> QuestionObservationImportData: ...

    def list_observation_batches(self, tenant_id: str, project_id: str) -> list[QuestionObservationBatchData]: ...

    def list_observations(
        self,
        tenant_id: str,
        project_id: str,
        batch_id: str,
    ) -> list[QuestionObservationRecordData]: ...

    def compile_map(
        self,
        tenant_id: str,
        project_id: str,
        payload: QuestionMapCompileRequest,
        actor: str,
    ) -> QuestionMapData: ...

    def list_maps(self, tenant_id: str, project_id: str) -> list[QuestionMapData]: ...

    def review_question(
        self,
        tenant_id: str,
        project_id: str,
        question_id: str,
        payload: QuestionReviewRequest,
        actor: str,
    ) -> QuestionReviewData: ...


def _main_module() -> Any:
    try:
        from . import main as api_main
    except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
        import main as api_main  # type: ignore[no-redef]
    return api_main


def _candidate(
    item: Mapping[str, Any],
    *,
    question_id: Optional[str] = None,
    duplicate_of_question_id: Optional[str] = None,
    status: Literal["preview", "suggested", "confirmed", "archived", "duplicate"] = "preview",
) -> QuestionCandidateData:
    return QuestionCandidateData(
        **dict(item),
        question_id=question_id,
        duplicate_of_question_id=duplicate_of_question_id,
        status=status,
    )


def _compile(
    *,
    brand_name: str,
    company_names: Sequence[str],
    product_terms: Sequence[str],
    competitor_names: Sequence[str],
    regions: Sequence[str],
    seed_questions: Sequence[str],
    include_template_candidates: bool,
    observed_questions: Sequence[ObservedQuestionSeed] = (),
) -> tuple[str, str, list[dict[str, Any]]]:
    map_version_id, input_sha256, questions = compile_question_candidates(
        brand_name=brand_name,
        company_names=company_names,
        product_terms=product_terms,
        competitor_names=competitor_names,
        regions=regions,
        seed_questions=seed_questions,
        include_template_candidates=include_template_candidates,
        observed_questions=observed_questions,
    )
    if not questions:
        raise StarletteHTTPException(
            status_code=400,
            detail={
                "code": "BAD_REQUEST",
                "message": "No buyer-question candidate could be compiled.",
                "details": {"required": "seed_questions or product_terms"},
            },
        )
    return map_version_id, input_sha256, questions


def build_observation_records(
    payload: QuestionObservationImportRequest,
    *,
    batch_id: str,
    created_at: datetime,
) -> tuple[list[QuestionObservationRecordData], list[BlockedObservationRecord], list[dict[str, Any]]]:
    accepted: list[QuestionObservationRecordData] = []
    blocked: list[BlockedObservationRecord] = []
    manifest_rows: list[dict[str, Any]] = []
    for row_number, item in enumerate(payload.records, start=1):
        normalized = normalize_question(item.question_text)
        source_record_id = item.source_record_id or f"row:{row_number}"
        content_payload = {
            "source_record_id": source_record_id,
            "question_text": normalized,
            "occurrence_count": item.occurrence_count,
            "observed_at": as_utc(item.observed_at).isoformat() if item.observed_at else None,
            "region": item.region,
            "audience_role": item.audience_role,
        }
        content_sha256 = sha256_text(
            json.dumps(content_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        pii_scan_text = "\n".join(
            value
            for value in (normalized, source_record_id, item.region, item.audience_role)
            if value
        )
        reasons = detected_pii_reasons(pii_scan_text)
        manifest_rows.append(
            {
                "row_number": row_number,
                "source_record_id_sha256": sha256_text(source_record_id),
                "content_sha256": content_sha256,
                "status": "blocked_pii" if reasons else "accepted",
                "reasons": reasons,
            }
        )
        if reasons:
            blocked.append(
                BlockedObservationRecord(
                    row_number=row_number,
                    content_sha256=content_sha256,
                    reasons=reasons,
                )
            )
            continue
        accepted.append(
            QuestionObservationRecordData(
                observation_id=f"qobs_{uuid4().hex[:20]}",
                batch_id=batch_id,
                row_number=row_number,
                source_record_id=source_record_id,
                question_text=normalized,
                normalized_question_text=normalized,
                dedupe_sha256=question_dedupe_sha256(normalized),
                occurrence_count=item.occurrence_count,
                observed_at=as_utc(item.observed_at),
                region=item.region,
                audience_role=item.audience_role,
                content_sha256=content_sha256,
                created_at=created_at,
            )
        )
    return accepted, blocked, manifest_rows


class InMemoryQuestionGovernanceRepository:
    def __init__(self) -> None:
        self.maps: dict[tuple[str, str, str], QuestionMapData] = {}
        self.reviews: dict[tuple[str, str], QuestionReviewData] = {}
        self.observation_batches: dict[tuple[str, str], QuestionObservationBatchData] = {}
        self.observations: dict[tuple[str, str], list[QuestionObservationRecordData]] = {}

    def import_observations(
        self,
        tenant_id: str,
        project_id: str,
        payload: QuestionObservationImportRequest,
        actor: str,
    ) -> QuestionObservationImportData:
        api_main = _main_module()
        api_main.PROJECT_REPOSITORY._ensure_project(tenant_id, project_id)
        payload_sha256 = observation_payload_sha256(payload)
        replay = next(
            (
                item
                for (item_tenant, _), item in self.observation_batches.items()
                if item_tenant == tenant_id
                and item.project_id == project_id
                and item.payload_sha256 == payload_sha256
            ),
            None,
        )
        if replay is not None:
            return QuestionObservationImportData(
                batch=replay.model_copy(update={"idempotent_replay": True}),
                records=list(self.observations.get((tenant_id, replay.batch_id), [])),
            )

        created_at = utc_now()
        batch_id = f"qobatch_{uuid4().hex[:20]}"
        records, blocked, _ = build_observation_records(payload, batch_id=batch_id, created_at=created_at)
        batch = QuestionObservationBatchData(
            batch_id=batch_id,
            tenant_id=tenant_id,
            project_id=project_id,
            source_type=payload.source_type,
            source_name=normalize_question(payload.source_name),
            source_uri=payload.source_uri,
            date_range_start=as_utc(payload.date_range_start),
            date_range_end=as_utc(payload.date_range_end),
            payload_sha256=payload_sha256,
            record_count=len(records),
            occurrence_count=sum(item.occurrence_count for item in records),
            pii_blocked_count=len(blocked),
            status="ready" if records else "blocked",
            rights_attested=True,
            imported_by=actor,
            created_at=created_at,
            blocked_records=blocked,
        )
        self.observation_batches[(tenant_id, batch_id)] = batch
        self.observations[(tenant_id, batch_id)] = records
        return QuestionObservationImportData(batch=batch, records=records)

    def list_observation_batches(self, tenant_id: str, project_id: str) -> list[QuestionObservationBatchData]:
        api_main = _main_module()
        api_main.PROJECT_REPOSITORY._ensure_project(tenant_id, project_id)
        return sorted(
            [
                item
                for (item_tenant, _), item in self.observation_batches.items()
                if item_tenant == tenant_id and item.project_id == project_id
            ],
            key=lambda item: item.created_at,
            reverse=True,
        )

    def list_observations(
        self,
        tenant_id: str,
        project_id: str,
        batch_id: str,
    ) -> list[QuestionObservationRecordData]:
        batch = self.observation_batches.get((tenant_id, batch_id))
        if batch is None or batch.project_id != project_id:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "QUESTION_OBSERVATION_BATCH_NOT_FOUND", "details": {"batch_id": batch_id}},
            )
        return list(self.observations.get((tenant_id, batch_id), []))

    def compile_map(
        self,
        tenant_id: str,
        project_id: str,
        payload: QuestionMapCompileRequest,
        actor: str,
    ) -> QuestionMapData:
        api_main = _main_module()
        project_repo = api_main.PROJECT_REPOSITORY
        project = project_repo._ensure_project(tenant_id, project_id)
        project_competitors = [
            item.name
            for (item_tenant, _), item in getattr(project_repo, "_competitors", {}).items()
            if item_tenant == tenant_id and item.project_id == project_id and item.status != "rejected"
        ]
        company_names = unique_normalized([project.company_name or project.brand_name, *payload.company_names])
        products = unique_normalized([*project.products, *payload.product_terms])
        competitors = unique_normalized([*project_competitors, *payload.competitor_names])
        observed_questions: list[ObservedQuestionSeed] = []
        for batch_id in payload.observation_batch_ids:
            batch = self.observation_batches.get((tenant_id, batch_id))
            if batch is None or batch.project_id != project_id:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "QUESTION_OBSERVATION_BATCH_NOT_FOUND", "details": {"batch_id": batch_id}},
                )
            if batch.status != "ready":
                raise StarletteHTTPException(
                    status_code=409,
                    detail={"code": "STATE_CONFLICT", "details": {"batch_id": batch_id, "status": batch.status}},
                )
            observed_questions.extend(
                ObservedQuestionSeed(
                    question_text=item.question_text,
                    source_ref=f"observation:{batch_id}:{item.observation_id}",
                    occurrence_count=item.occurrence_count,
                    observed_at=item.observed_at.isoformat() if item.observed_at else None,
                    region=item.region,
                    evidence_grade=batch.evidence_grade,
                )
                for item in self.observations.get((tenant_id, batch_id), [])
            )
        map_version_id, input_sha256, compiled = _compile(
            brand_name=project.brand_name,
            company_names=company_names,
            product_terms=products,
            competitor_names=competitors,
            regions=payload.regions,
            seed_questions=payload.seed_questions,
            include_template_candidates=payload.include_template_candidates,
            observed_questions=observed_questions,
        )
        map_key = (tenant_id, project_id, map_version_id)
        replay = self.maps.get(map_key) if payload.persist else None
        if replay is not None:
            return replay.model_copy(update={"idempotent_replay": True})

        existing = {
            item.dedupe_sha256: item
            for item in project_repo.list_buyer_questions(tenant_id, project_id)
            if item.dedupe_sha256 and item.status != "archived"
        }
        questions: list[QuestionCandidateData] = []
        duplicate_count = sum(max(0, len(item.get("deduplicated_source_refs", [])) - 1) for item in compiled)
        persisted_count = 0
        for item in compiled:
            duplicate = existing.get(str(item["dedupe_sha256"]))
            if duplicate is not None:
                duplicate_count += 1
                questions.append(_candidate(item, duplicate_of_question_id=duplicate.question_id, status="duplicate"))
                continue
            if not payload.persist:
                questions.append(_candidate(item))
                continue
            source = "hermes_generated" if item["source_kind"] == "template_candidate" else "imported" if item["source_kind"] == "imported" else "manual"
            created = project_repo.create_buyer_question(
                tenant_id,
                project_id,
                api_main.BuyerQuestionCreateRequest(
                    question_text=item["question_text"],
                    question_type=item["question_type"],
                    intent_level=item["intent_level"],
                    buyer_stage=item["buyer_stage"],
                    source_reason=item["source_ref"],
                    recommended_providers=[],
                    status="suggested",
                    source=source,
                ),
            )
            created = created.model_copy(update={key: value for key, value in item.items() if key in type(created).model_fields})
            project_repo._questions[(tenant_id, created.question_id)] = created
            existing[created.dedupe_sha256] = created
            persisted_count += 1
            questions.append(_candidate(item, question_id=created.question_id, status="suggested"))

        created_at = utc_now()
        data = QuestionMapData(
            map_id=f"qmap_{uuid4().hex[:20]}" if payload.persist else f"qmap_preview_{input_sha256[:16]}",
            map_version_id=map_version_id,
            tenant_id=tenant_id,
            project_id=project_id,
            taxonomy_version=TAXONOMY_VERSION,
            input_sha256=input_sha256,
            status="compiled" if payload.persist else "preview",
            question_count=len(compiled),
            duplicate_count=duplicate_count,
            persisted_count=persisted_count,
            created_by=actor,
            created_at=created_at,
            questions=questions,
        )
        if payload.persist:
            self.maps[map_key] = data
        return data

    def list_maps(self, tenant_id: str, project_id: str) -> list[QuestionMapData]:
        api_main = _main_module()
        api_main.PROJECT_REPOSITORY._ensure_project(tenant_id, project_id)
        return sorted(
            [value for (item_tenant, item_project, _), value in self.maps.items() if item_tenant == tenant_id and item_project == project_id],
            key=lambda item: item.created_at,
            reverse=True,
        )

    def review_question(
        self,
        tenant_id: str,
        project_id: str,
        question_id: str,
        payload: QuestionReviewRequest,
        actor: str,
    ) -> QuestionReviewData:
        api_main = _main_module()
        project_repo = api_main.PROJECT_REPOSITORY
        project_repo._ensure_project(tenant_id, project_id)
        question = getattr(project_repo, "_questions", {}).get((tenant_id, question_id))
        if question is None or question.project_id != project_id:
            raise StarletteHTTPException(status_code=404, detail={"code": "QUESTION_NOT_FOUND", "details": {"question_id": question_id}})
        if question.status == payload.action:
            previous = self.reviews.get((tenant_id, question_id))
            if previous is not None:
                return previous.model_copy(update={"idempotent_replay": True})
        if question.status == "archived":
            raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"question_id": question_id, "status": question.status}})
        reviewed_at = utc_now()
        data = QuestionReviewData(
            review_id=f"qreview_{uuid4().hex[:20]}",
            tenant_id=tenant_id,
            project_id=project_id,
            question_id=question_id,
            question_revision_id=question.question_version_id or "in_memory_revision",
            previous_status=question.status,
            status=payload.action,
            reviewed_by=actor,
            reviewed_at=reviewed_at,
            review_note=payload.review_note,
            eligible_for_measurement=payload.action == "confirmed",
        )
        project_repo._questions[(tenant_id, question_id)] = question.model_copy(
            update={
                "status": payload.action,
                "reviewed_by": actor,
                "reviewed_at": reviewed_at,
                "review_note": payload.review_note,
                "updated_at": reviewed_at,
            }
        )
        self.reviews[(tenant_id, question_id)] = data
        return data


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return [str(item) for item in value] if isinstance(value, list) else []


class MySQLQuestionGovernanceRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _observation_record_from_row(row: Mapping[str, Any]) -> QuestionObservationRecordData:
        return QuestionObservationRecordData(
            observation_id=row["id"],
            batch_id=row["batch_id"],
            row_number=row["source_row_number"],
            source_record_id=row["source_record_id"],
            question_text=row["question_text"],
            normalized_question_text=row["normalized_question_text"],
            dedupe_sha256=row["dedupe_sha256"],
            occurrence_count=row["occurrence_count"],
            observed_at=as_utc(row["observed_at"]),
            region=row["region"],
            audience_role=row["audience_role"],
            content_sha256=row["content_sha256"],
            pii_status=row["pii_status"],
            created_at=as_utc(row["created_at"]),
        )

    @staticmethod
    def _observation_batch_from_row(
        row: Mapping[str, Any],
        *,
        replay: bool = False,
    ) -> QuestionObservationBatchData:
        manifest = row["manifest_json"]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        blocked = [
            BlockedObservationRecord.model_validate(item)
            for item in manifest.get("blocked_records", [])
        ]
        return QuestionObservationBatchData(
            batch_id=row["id"],
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            source_type=row["source_type"],
            source_name=row["source_name"],
            access_mode=row["access_mode"],
            evidence_grade=row["evidence_grade"],
            source_uri=row["source_uri"],
            date_range_start=as_utc(row["date_range_start"]),
            date_range_end=as_utc(row["date_range_end"]),
            payload_sha256=row["payload_sha256"],
            record_count=row["record_count"],
            occurrence_count=row["occurrence_count"],
            pii_blocked_count=row["pii_blocked_count"],
            status=row["status"],
            rights_attested=bool(row["rights_attested"]),
            imported_by=row["imported_by"],
            created_at=as_utc(row["created_at"]),
            blocked_records=blocked,
            idempotent_replay=replay,
        )

    def import_observations(
        self,
        tenant_id: str,
        project_id: str,
        payload: QuestionObservationImportRequest,
        actor: str,
    ) -> QuestionObservationImportData:
        payload_sha256 = observation_payload_sha256(payload)
        with self.engine.begin() as conn:
            project = conn.execute(text("""
                SELECT id FROM airank_projects
                WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
                FOR UPDATE
            """), {"tenant_id": tenant_id, "project_id": project_id}).first()
            if project is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}},
                )
            replay = conn.execute(text("""
                SELECT * FROM airank_question_observation_batches
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND payload_sha256=:payload_sha256
                FOR UPDATE
            """), {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "payload_sha256": payload_sha256,
            }).mappings().first()
            if replay is not None:
                records = conn.execute(text("""
                    SELECT id, batch_id, source_row_number, source_record_id,
                           question_text, normalized_question_text, dedupe_sha256,
                           occurrence_count, observed_at, region, audience_role,
                           content_sha256, pii_status, created_at
                    FROM airank_question_observations
                    WHERE tenant_id=:tenant_id AND project_id=:project_id AND batch_id=:batch_id
                    ORDER BY source_row_number ASC
                """), {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "batch_id": replay["id"],
                }).mappings().all()
                return QuestionObservationImportData(
                    batch=self._observation_batch_from_row(replay, replay=True),
                    records=[self._observation_record_from_row(row) for row in records],
                )

            created_at = utc_now()
            batch_id = f"qobatch_{uuid4().hex[:20]}"
            records, blocked, manifest_rows = build_observation_records(
                payload,
                batch_id=batch_id,
                created_at=created_at,
            )
            status = "ready" if records else "blocked"
            occurrence_count = sum(item.occurrence_count for item in records)
            manifest = {
                "contract": "airank.question-observation-batch.v1",
                "payload_sha256": payload_sha256,
                "access_mode": "user_provided",
                "evidence_grade": "user_provided_snapshot",
                "record_manifest": manifest_rows,
                "blocked_records": [item.model_dump(mode="json") for item in blocked],
                "truth_policy": "customer_provided_not_independently_verified",
                "volume_policy": "occurrence_count_is_source_frequency_not_search_volume",
            }
            conn.execute(text("""
                INSERT INTO airank_question_observation_batches (
                  id, tenant_id, project_id, source_type, source_name, access_mode,
                  evidence_grade, source_uri, date_range_start, date_range_end,
                  payload_sha256, manifest_json, record_count, occurrence_count,
                  pii_blocked_count, status, rights_attested, imported_by, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :source_type, :source_name, 'user_provided',
                  'user_provided_snapshot', :source_uri, :date_range_start, :date_range_end,
                  :payload_sha256, :manifest_json, :record_count, :occurrence_count,
                  :pii_blocked_count, :status, 1, :imported_by, :created_at
                )
            """), {
                "id": batch_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "source_type": payload.source_type,
                "source_name": normalize_question(payload.source_name),
                "source_uri": payload.source_uri,
                "date_range_start": as_utc(payload.date_range_start),
                "date_range_end": as_utc(payload.date_range_end),
                "payload_sha256": payload_sha256,
                "manifest_json": json.dumps(manifest, ensure_ascii=False, sort_keys=True),
                "record_count": len(records),
                "occurrence_count": occurrence_count,
                "pii_blocked_count": len(blocked),
                "status": status,
                "imported_by": actor,
                "created_at": created_at,
            })
            for item in records:
                conn.execute(text("""
                    INSERT INTO airank_question_observations (
                      id, tenant_id, project_id, batch_id, source_row_number, source_record_id,
                      question_text, normalized_question_text, dedupe_sha256,
                      occurrence_count, observed_at, region, audience_role,
                      content_sha256, pii_status, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :batch_id, :row_number, :source_record_id,
                      :question_text, :normalized_question_text, :dedupe_sha256,
                      :occurrence_count, :observed_at, :region, :audience_role,
                      :content_sha256, 'none_detected', :created_at
                    )
                """), {
                    "id": item.observation_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "batch_id": batch_id,
                    "row_number": item.row_number,
                    "source_record_id": item.source_record_id,
                    "question_text": item.question_text,
                    "normalized_question_text": item.normalized_question_text,
                    "dedupe_sha256": item.dedupe_sha256,
                    "occurrence_count": item.occurrence_count,
                    "observed_at": item.observed_at,
                    "region": item.region,
                    "audience_role": item.audience_role,
                    "content_sha256": item.content_sha256,
                    "created_at": created_at,
                })
            batch_row = {
                "id": batch_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "source_type": payload.source_type,
                "source_name": normalize_question(payload.source_name),
                "access_mode": "user_provided",
                "evidence_grade": "user_provided_snapshot",
                "source_uri": payload.source_uri,
                "date_range_start": as_utc(payload.date_range_start),
                "date_range_end": as_utc(payload.date_range_end),
                "payload_sha256": payload_sha256,
                "manifest_json": manifest,
                "record_count": len(records),
                "occurrence_count": occurrence_count,
                "pii_blocked_count": len(blocked),
                "status": status,
                "rights_attested": True,
                "imported_by": actor,
                "created_at": created_at,
            }
            return QuestionObservationImportData(
                batch=self._observation_batch_from_row(batch_row),
                records=records,
            )

    def list_observation_batches(
        self,
        tenant_id: str,
        project_id: str,
    ) -> list[QuestionObservationBatchData]:
        with self.engine.begin() as conn:
            project = conn.execute(text("""
                SELECT id FROM airank_projects
                WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
            """), {"tenant_id": tenant_id, "project_id": project_id}).first()
            if project is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}},
                )
            rows = conn.execute(text("""
                SELECT * FROM airank_question_observation_batches
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY created_at DESC, id DESC
                LIMIT 100
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        return [self._observation_batch_from_row(row) for row in rows]

    def list_observations(
        self,
        tenant_id: str,
        project_id: str,
        batch_id: str,
    ) -> list[QuestionObservationRecordData]:
        with self.engine.begin() as conn:
            batch = conn.execute(text("""
                SELECT id FROM airank_question_observation_batches
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:batch_id
            """), {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "batch_id": batch_id,
            }).first()
            if batch is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "QUESTION_OBSERVATION_BATCH_NOT_FOUND", "details": {"batch_id": batch_id}},
                )
            rows = conn.execute(text("""
                SELECT id, batch_id, source_row_number, source_record_id,
                       question_text, normalized_question_text, dedupe_sha256,
                       occurrence_count, observed_at, region, audience_role,
                       content_sha256, pii_status, created_at
                FROM airank_question_observations
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND batch_id=:batch_id
                ORDER BY source_row_number ASC
            """), {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "batch_id": batch_id,
            }).mappings().all()
        return [self._observation_record_from_row(row) for row in rows]

    @staticmethod
    def _map_from_manifest(row: Mapping[str, Any], *, replay: bool = False) -> QuestionMapData:
        manifest = row["output_manifest_json"]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        data = QuestionMapData.model_validate(manifest)
        return data.model_copy(update={"idempotent_replay": replay})

    @staticmethod
    def _load_observed_questions(
        conn: Any,
        tenant_id: str,
        project_id: str,
        batch_ids: Sequence[str],
    ) -> list[ObservedQuestionSeed]:
        if not batch_ids:
            return []
        placeholders = ", ".join(f":batch_{index}" for index in range(len(batch_ids)))
        params = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            **{f"batch_{index}": batch_id for index, batch_id in enumerate(batch_ids)},
        }
        batches = conn.execute(text(f"""
            SELECT id, status, evidence_grade
            FROM airank_question_observation_batches
            WHERE tenant_id=:tenant_id AND project_id=:project_id
              AND id IN ({placeholders})
        """), params).mappings().all()
        batches_by_id = {row["id"]: row for row in batches}
        missing = [batch_id for batch_id in batch_ids if batch_id not in batches_by_id]
        if missing:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "QUESTION_OBSERVATION_BATCH_NOT_FOUND", "details": {"batch_ids": missing}},
            )
        blocked = [batch_id for batch_id in batch_ids if batches_by_id[batch_id]["status"] != "ready"]
        if blocked:
            raise StarletteHTTPException(
                status_code=409,
                detail={"code": "STATE_CONFLICT", "details": {"blocked_batch_ids": blocked}},
            )
        rows = conn.execute(text(f"""
            SELECT id, batch_id, question_text, occurrence_count, observed_at, region
            FROM airank_question_observations
            WHERE tenant_id=:tenant_id AND project_id=:project_id
              AND batch_id IN ({placeholders})
            ORDER BY batch_id ASC, source_row_number ASC
        """), params).mappings().all()
        return [
            ObservedQuestionSeed(
                question_text=row["question_text"],
                source_ref=f"observation:{row['batch_id']}:{row['id']}",
                occurrence_count=row["occurrence_count"],
                observed_at=as_utc(row["observed_at"]).isoformat() if row["observed_at"] else None,
                region=row["region"],
                evidence_grade=batches_by_id[row["batch_id"]]["evidence_grade"],
            )
            for row in rows
        ]

    def compile_map(
        self,
        tenant_id: str,
        project_id: str,
        payload: QuestionMapCompileRequest,
        actor: str,
    ) -> QuestionMapData:
        with self.engine.begin() as conn:
            project = conn.execute(text("""
                SELECT id, name, brand_name, products_services_json
                FROM airank_projects
                WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
                FOR UPDATE
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().first()
            if project is None:
                raise StarletteHTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}})
            project_competitors = conn.execute(text("""
                SELECT name FROM airank_competitors
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND deleted_at IS NULL
                ORDER BY created_at ASC, id ASC
            """), {"tenant_id": tenant_id, "project_id": project_id}).scalars().all()
            brand_name = str(project["brand_name"] or project["name"])
            companies = unique_normalized([str(project["name"]), *payload.company_names])
            products = unique_normalized([*_json_list(project["products_services_json"]), *payload.product_terms])
            competitors = unique_normalized([*[str(item) for item in project_competitors], *payload.competitor_names])
            observed_questions = self._load_observed_questions(
                conn,
                tenant_id,
                project_id,
                payload.observation_batch_ids,
            )
            map_version_id, input_sha256, compiled = _compile(
                brand_name=brand_name,
                company_names=companies,
                product_terms=products,
                competitor_names=competitors,
                regions=payload.regions,
                seed_questions=payload.seed_questions,
                include_template_candidates=payload.include_template_candidates,
                observed_questions=observed_questions,
            )
            if not payload.persist:
                duplicates_within_input = sum(max(0, len(item.get("deduplicated_source_refs", [])) - 1) for item in compiled)
                return QuestionMapData(
                    map_id=f"qmap_preview_{input_sha256[:16]}", map_version_id=map_version_id,
                    tenant_id=tenant_id, project_id=project_id, taxonomy_version=TAXONOMY_VERSION,
                    input_sha256=input_sha256, status="preview", question_count=len(compiled),
                    duplicate_count=duplicates_within_input, persisted_count=0, created_by=actor,
                    created_at=utc_now(), questions=[_candidate(item) for item in compiled],
                )

            replay = conn.execute(text("""
                SELECT output_manifest_json
                FROM airank_question_maps
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND map_version_id=:map_version_id
                FOR UPDATE
            """), {"tenant_id": tenant_id, "project_id": project_id, "map_version_id": map_version_id}).mappings().first()
            if replay is not None:
                return self._map_from_manifest(replay, replay=True)

            created_at = utc_now()
            map_id = f"qmap_{uuid4().hex[:20]}"
            input_manifest = {
                "contract": "airank.question-map-input.v1",
                "brand_name": brand_name,
                "company_names": companies,
                "product_terms": products,
                "competitor_names": competitors,
                "regions": payload.regions,
                "seed_questions": payload.seed_questions,
                "observation_batch_ids": payload.observation_batch_ids,
                "include_template_candidates": payload.include_template_candidates,
                "taxonomy_version": TAXONOMY_VERSION,
            }
            conn.execute(text("""
                INSERT INTO airank_question_maps (
                  id, tenant_id, project_id, map_version_id, taxonomy_version,
                  input_sha256, input_json, output_manifest_json, question_count,
                  duplicate_count, status, created_by, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :map_version_id, :taxonomy_version,
                  :input_sha256, :input_json, :output_manifest_json, :question_count,
                  0, 'compiled', :created_by, :created_at
                )
            """), {
                "id": map_id, "tenant_id": tenant_id, "project_id": project_id,
                "map_version_id": map_version_id, "taxonomy_version": TAXONOMY_VERSION,
                "input_sha256": input_sha256,
                "input_json": json.dumps(input_manifest, ensure_ascii=False, sort_keys=True),
                "output_manifest_json": json.dumps({"state": "compiling"}),
                "question_count": len(compiled), "created_by": actor, "created_at": created_at,
            })
            existing = {
                row["dedupe_sha256"]: row["id"]
                for row in conn.execute(text("""
                    SELECT id, dedupe_sha256 FROM airank_buyer_questions
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND status<>'archived' AND deleted_at IS NULL
                """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
                if row["dedupe_sha256"]
            }
            questions: list[QuestionCandidateData] = []
            duplicate_count = sum(max(0, len(item.get("deduplicated_source_refs", [])) - 1) for item in compiled)
            persisted_count = 0
            for item in compiled:
                dedupe_sha = str(item["dedupe_sha256"])
                duplicate_id = existing.get(dedupe_sha)
                if duplicate_id:
                    duplicate_count += 1
                    questions.append(_candidate(item, duplicate_of_question_id=duplicate_id, status="duplicate"))
                    continue
                question_id = f"question_{uuid4().hex[:12]}"
                revision_id = f"qrev_{uuid4().hex[:20]}"
                source = "hermes_generated" if item["source_kind"] == "template_candidate" else "imported" if item["source_kind"] == "imported" else "manual"
                metadata = {
                    "source_reason": item["source_ref"], "recommended_providers": [], "coverage_status": "needs_scan",
                    "question_version_id": item["question_version_id"], "taxonomy_version": item["taxonomy_version"],
                    "cohort_type": item["cohort_type"], "source_kind": item["source_kind"],
                    "source_ref": item["source_ref"], "observed_query": item["observed_query"],
                }
                conn.execute(text("""
                    INSERT INTO airank_buyer_questions (
                      id, tenant_id, project_id, question_map_id, current_revision_id,
                      taxonomy_version, dedupe_sha256, question_text, question_type,
                      intent, funnel_stage, source, status, metadata_json, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :question_map_id, NULL,
                      :taxonomy_version, :dedupe_sha256, :question_text, :question_type,
                      :intent, :funnel_stage, :source, 'suggested', :metadata_json, :created_at, :created_at
                    )
                """), {
                    "id": question_id, "tenant_id": tenant_id, "project_id": project_id,
                    "question_map_id": map_id, "taxonomy_version": item["taxonomy_version"],
                    "dedupe_sha256": dedupe_sha, "question_text": item["question_text"],
                    "question_type": item["question_type"], "intent": item["intent_level"],
                    "funnel_stage": item["buyer_stage"], "source": source,
                    "metadata_json": json.dumps(metadata, ensure_ascii=False), "created_at": created_at,
                })
                conn.execute(text("""
                    INSERT INTO airank_buyer_question_revisions (
                      id, tenant_id, project_id, question_id, question_map_id, revision_number,
                      question_version_id, taxonomy_version, question_text, dedupe_sha256,
                      question_type, intent, funnel_stage, prompt_style, temporal_scope,
                      scenario, region, cohort_type, source_kind, source_ref, evidence_level,
                      observed_query, provenance_json, status, created_by, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :question_id, :question_map_id, 1,
                      :question_version_id, :taxonomy_version, :question_text, :dedupe_sha256,
                      :question_type, :intent, :funnel_stage, :prompt_style, :temporal_scope,
                      :scenario, :region, :cohort_type, :source_kind, :source_ref, :evidence_level,
                      :observed_query, :provenance_json, 'suggested', :created_by, :created_at
                    )
                """), {
                    "id": revision_id, "tenant_id": tenant_id, "project_id": project_id,
                    "question_id": question_id, "question_map_id": map_id,
                    "question_version_id": item["question_version_id"], "taxonomy_version": item["taxonomy_version"],
                    "question_text": item["question_text"], "dedupe_sha256": dedupe_sha,
                    "question_type": item["question_type"], "intent": item["intent_level"],
                    "funnel_stage": item["buyer_stage"], "prompt_style": item["prompt_style"],
                    "temporal_scope": item["temporal_scope"], "scenario": item["scenario"],
                    "region": item["region"], "cohort_type": item["cohort_type"],
                    "source_kind": item["source_kind"], "source_ref": item["source_ref"],
                    "evidence_level": item["evidence_level"], "observed_query": item["observed_query"],
                    "provenance_json": json.dumps({
                        "map_version_id": map_version_id, "input_sha256": input_sha256,
                        "deduplicated_source_refs": item["deduplicated_source_refs"],
                        "provenance_records": item["provenance_records"],
                    }, ensure_ascii=False),
                    "created_by": actor, "created_at": created_at,
                })
                conn.execute(text("""
                    UPDATE airank_buyer_questions
                    SET current_revision_id=:revision_id
                    WHERE tenant_id=:tenant_id AND id=:question_id
                """), {"revision_id": revision_id, "tenant_id": tenant_id, "question_id": question_id})
                existing[dedupe_sha] = question_id
                persisted_count += 1
                questions.append(_candidate(item, question_id=question_id, status="suggested"))

            data = QuestionMapData(
                map_id=map_id, map_version_id=map_version_id, tenant_id=tenant_id,
                project_id=project_id, taxonomy_version=TAXONOMY_VERSION,
                input_sha256=input_sha256, status="compiled", question_count=len(compiled),
                duplicate_count=duplicate_count, persisted_count=persisted_count,
                created_by=actor, created_at=created_at, questions=questions,
            )
            manifest_json = json.dumps(data.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            conn.execute(text("""
                UPDATE airank_question_maps
                SET output_manifest_json=:manifest, duplicate_count=:duplicate_count
                WHERE tenant_id=:tenant_id AND id=:map_id
            """), {
                "manifest": manifest_json, "duplicate_count": duplicate_count,
                "tenant_id": tenant_id, "map_id": map_id,
            })
            return data

    def list_maps(self, tenant_id: str, project_id: str) -> list[QuestionMapData]:
        with self.engine.begin() as conn:
            project = conn.execute(text("""
                SELECT id FROM airank_projects
                WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
            """), {"tenant_id": tenant_id, "project_id": project_id}).first()
            if project is None:
                raise StarletteHTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}})
            rows = conn.execute(text("""
                SELECT output_manifest_json FROM airank_question_maps
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY created_at DESC, id DESC
                LIMIT 50
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        return [self._map_from_manifest(row) for row in rows]

    def review_question(
        self,
        tenant_id: str,
        project_id: str,
        question_id: str,
        payload: QuestionReviewRequest,
        actor: str,
    ) -> QuestionReviewData:
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                SELECT id, current_revision_id, status
                FROM airank_buyer_questions
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND id=:question_id AND deleted_at IS NULL
                FOR UPDATE
            """), {"tenant_id": tenant_id, "project_id": project_id, "question_id": question_id}).mappings().first()
            if row is None:
                raise StarletteHTTPException(status_code=404, detail={"code": "QUESTION_NOT_FOUND", "details": {"question_id": question_id}})
            if row["status"] == payload.action:
                previous = conn.execute(text("""
                    SELECT id, question_revision_id, previous_status, action, review_note, reviewed_by, reviewed_at
                    FROM airank_buyer_question_reviews
                    WHERE tenant_id=:tenant_id AND question_id=:question_id AND action=:action
                    ORDER BY reviewed_at DESC, id DESC LIMIT 1
                """), {"tenant_id": tenant_id, "question_id": question_id, "action": payload.action}).mappings().first()
                if previous:
                    return QuestionReviewData(
                        review_id=previous["id"], tenant_id=tenant_id, project_id=project_id,
                        question_id=question_id, question_revision_id=previous["question_revision_id"],
                        previous_status=previous["previous_status"], status=previous["action"],
                        reviewed_by=previous["reviewed_by"], reviewed_at=previous["reviewed_at"],
                        review_note=previous["review_note"], eligible_for_measurement=payload.action == "confirmed",
                        idempotent_replay=True,
                    )
            if row["status"] == "archived" or not row["current_revision_id"]:
                raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"question_id": question_id, "status": row["status"]}})
            reviewed_at = utc_now()
            review_id = f"qreview_{uuid4().hex[:20]}"
            conn.execute(text("""
                INSERT INTO airank_buyer_question_reviews (
                  id, tenant_id, project_id, question_id, question_revision_id,
                  previous_status, action, review_note, reviewed_by, reviewed_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :question_id, :question_revision_id,
                  :previous_status, :action, :review_note, :reviewed_by, :reviewed_at
                )
            """), {
                "id": review_id, "tenant_id": tenant_id, "project_id": project_id,
                "question_id": question_id, "question_revision_id": row["current_revision_id"],
                "previous_status": row["status"], "action": payload.action,
                "review_note": payload.review_note, "reviewed_by": actor, "reviewed_at": reviewed_at,
            })
            conn.execute(text("""
                UPDATE airank_buyer_questions
                SET status=:status, updated_at=:updated_at
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:question_id
            """), {
                "status": payload.action, "updated_at": reviewed_at, "tenant_id": tenant_id,
                "project_id": project_id, "question_id": question_id,
            })
            return QuestionReviewData(
                review_id=review_id, tenant_id=tenant_id, project_id=project_id,
                question_id=question_id, question_revision_id=row["current_revision_id"],
                previous_status=row["status"], status=payload.action, reviewed_by=actor,
                reviewed_at=reviewed_at, review_note=payload.review_note,
                eligible_for_measurement=payload.action == "confirmed",
            )


def build_question_governance_repository() -> QuestionGovernanceRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLQuestionGovernanceRepository(database_url)
    return InMemoryQuestionGovernanceRepository()


QUESTION_GOVERNANCE_REPOSITORY: QuestionGovernanceRepository = build_question_governance_repository()


@router.post(
    "/projects/{project_id}/question-observation-batches",
    response_model=QuestionObservationImportResponse,
    status_code=201,
)
def import_question_observations(
    project_id: str,
    payload: QuestionObservationImportRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> QuestionObservationImportResponse:
    actor = trusted_actor(payload.imported_by, authenticated_actor)
    return QuestionObservationImportResponse(
        data=QUESTION_GOVERNANCE_REPOSITORY.import_observations(
            tenant_id,
            project_id,
            payload,
            actor,
        ),
        meta=response_meta(trace_id),
    )


@router.get(
    "/projects/{project_id}/question-observation-batches",
    response_model=QuestionObservationBatchListResponse,
)
def list_question_observation_batches(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> QuestionObservationBatchListResponse:
    return QuestionObservationBatchListResponse(
        data=QUESTION_GOVERNANCE_REPOSITORY.list_observation_batches(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.get(
    "/projects/{project_id}/question-observation-batches/{batch_id}/records",
    response_model=QuestionObservationRecordListResponse,
)
def list_question_observations(
    project_id: str,
    batch_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> QuestionObservationRecordListResponse:
    return QuestionObservationRecordListResponse(
        data=QUESTION_GOVERNANCE_REPOSITORY.list_observations(
            tenant_id,
            project_id,
            batch_id,
        ),
        meta=response_meta(trace_id),
    )


@router.post("/projects/{project_id}/question-maps/compile", response_model=QuestionMapResponse, status_code=201)
def compile_question_map(
    project_id: str,
    payload: QuestionMapCompileRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> QuestionMapResponse:
    actor = trusted_actor(payload.created_by, authenticated_actor)
    return QuestionMapResponse(
        data=QUESTION_GOVERNANCE_REPOSITORY.compile_map(tenant_id, project_id, payload, actor),
        meta=response_meta(trace_id),
    )


@router.get("/projects/{project_id}/question-maps", response_model=QuestionMapListResponse)
def list_question_maps(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> QuestionMapListResponse:
    return QuestionMapListResponse(
        data=QUESTION_GOVERNANCE_REPOSITORY.list_maps(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.patch("/projects/{project_id}/buyer-questions/{question_id}/review", response_model=QuestionReviewResponse)
def review_buyer_question(
    project_id: str,
    question_id: str,
    payload: QuestionReviewRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> QuestionReviewResponse:
    actor = trusted_actor(payload.reviewed_by, authenticated_actor)
    return QuestionReviewResponse(
        data=QUESTION_GOVERNANCE_REPOSITORY.review_question(tenant_id, project_id, question_id, payload, actor),
        meta=response_meta(trace_id),
    )

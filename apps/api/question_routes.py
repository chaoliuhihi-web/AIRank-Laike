from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any, Literal, Mapping, Optional, Protocol, Sequence
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import TAXONOMY_VERSION, compile_question_candidates, normalize_question


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


class QuestionMapCompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_names: list[str] = Field(default_factory=list, max_length=20)
    product_terms: list[str] = Field(default_factory=list, max_length=30)
    competitor_names: list[str] = Field(default_factory=list, max_length=30)
    regions: list[str] = Field(default_factory=list, max_length=30)
    seed_questions: list[str] = Field(default_factory=list, max_length=200)
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
) -> tuple[str, str, list[dict[str, Any]]]:
    map_version_id, input_sha256, questions = compile_question_candidates(
        brand_name=brand_name,
        company_names=company_names,
        product_terms=product_terms,
        competitor_names=competitor_names,
        regions=regions,
        seed_questions=seed_questions,
        include_template_candidates=include_template_candidates,
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


class InMemoryQuestionGovernanceRepository:
    def __init__(self) -> None:
        self.maps: dict[tuple[str, str, str], QuestionMapData] = {}
        self.reviews: dict[tuple[str, str], QuestionReviewData] = {}

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
        map_version_id, input_sha256, compiled = _compile(
            brand_name=project.brand_name,
            company_names=company_names,
            product_terms=products,
            competitor_names=competitors,
            regions=payload.regions,
            seed_questions=payload.seed_questions,
            include_template_candidates=payload.include_template_candidates,
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
    def _map_from_manifest(row: Mapping[str, Any], *, replay: bool = False) -> QuestionMapData:
        manifest = row["output_manifest_json"]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        data = QuestionMapData.model_validate(manifest)
        return data.model_copy(update={"idempotent_replay": replay})

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
            map_version_id, input_sha256, compiled = _compile(
                brand_name=brand_name,
                company_names=companies,
                product_terms=products,
                competitor_names=competitors,
                regions=payload.regions,
                seed_questions=payload.seed_questions,
                include_template_candidates=payload.include_template_candidates,
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

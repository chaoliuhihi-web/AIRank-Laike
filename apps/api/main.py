from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from typing import Any, Literal, Optional, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

API_PREFIX = "/api/v1"
API_VERSION = "v1"
SERVICE_NAME = "airank-api"
TRACE_HEADER = "X-AIRank-Trace-Id"

ERROR_REGISTRY: dict[str, tuple[int, str]] = {
    "BAD_REQUEST": (400, "Bad request"),
    "VALIDATION_FAILED": (422, "Invalid request"),
    "RESOURCE_NOT_FOUND": (404, "Resource not found"),
    "METHOD_NOT_ALLOWED": (405, "Method not allowed"),
    "STATE_CONFLICT": (409, "State conflict"),
    "RATE_LIMITED": (429, "Rate limited"),
    "INTERNAL_ERROR": (500, "Internal server error"),
    "AUTH_TOKEN_MISSING": (401, "Authentication token is missing"),
    "AUTH_TOKEN_INVALID": (401, "Authentication token is invalid"),
    "AUTH_YUDAO_UNAVAILABLE": (503, "Yudao authentication is unavailable"),
    "TENANT_MISMATCH": (403, "Tenant does not match the token"),
    "TENANT_FORBIDDEN": (403, "Tenant access is forbidden"),
    "PROJECT_NOT_FOUND": (404, "Project not found"),
    "PROJECT_ARCHIVED": (409, "Project is archived"),
    "QUESTION_NOT_FOUND": (404, "Question not found"),
    "QUESTION_LIMIT_EXCEEDED": (400, "Question limit exceeded"),
    "SCAN_RUN_NOT_FOUND": (404, "Scan run not found"),
    "SCAN_RUN_ALREADY_RUNNING": (409, "Scan run is already running"),
    "SCAN_PROVIDER_TIMEOUT": (502, "Scan provider timed out"),
    "SCAN_PROVIDER_BLOCKED": (502, "Scan provider is blocked"),
    "JOB_NOT_FOUND": (404, "Job not found"),
    "JOB_TIMEOUT": (500, "Job timed out"),
    "JOB_MAX_ATTEMPTS_EXCEEDED": (500, "Job exceeded max attempts"),
    "FACT_NOT_FOUND": (404, "FactAtom not found"),
    "FACT_SOURCE_REQUIRED": (400, "Fact source is required"),
    "FACT_DISCLOSURE_FORBIDDEN": (403, "Fact disclosure is forbidden"),
    "ASSET_NOT_FOUND": (404, "Asset not found"),
    "ASSET_REVIEW_REQUIRED": (409, "Asset review is required"),
    "REPORT_NOT_FOUND": (404, "Report not found"),
    "REPORT_EVIDENCE_MISSING": (500, "Report evidence is missing"),
    "OBJECT_REF_NOT_FOUND": (404, "Object reference not found"),
    "INTEGRATION_CAPABILITY_BLOCKED": (503, "Integration capability is blocked"),
    "INTEGRATION_CAPABILITY_DISABLED": (503, "Integration capability is disabled"),
    "YUDAO_MODEL_RESOLVE_FAILED": (502, "Yudao model resolution failed"),
    "XINGHE_CRAWLER_FAILED": (502, "Xinghe crawler failed"),
    "XINGHE_KB_FAILED": (502, "Xinghe KB failed"),
}

HTTP_STATUS_DEFAULT_ERROR: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "AUTH_TOKEN_MISSING",
    403: "TENANT_FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "STATE_CONFLICT",
    422: "VALIDATION_FAILED",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "XINGHE_CRAWLER_FAILED",
    503: "INTEGRATION_CAPABILITY_BLOCKED",
}


class ProjectOverview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    website: str
    industry: str
    competitors: str
    audience: str
    date: date


class MetricCard(BaseModel):
    label: str
    value: str
    suffix: str
    delta: str
    tone: Literal["primary", "success", "warning", "danger", "muted"]
    icon: str


class ConsoleOverview(BaseModel):
    project: ProjectOverview
    metric_cards: list[MetricCard] = Field(alias="metric_cards", min_length=1)


class ResponseMeta(BaseModel):
    trace_id: str
    request_id: str


class SourceRef(BaseModel):
    url: str
    title: Optional[str] = None
    source_type: Literal["owned", "third_party", "community", "unknown"]
    captured_at: Optional[datetime] = None
    confidence: float = Field(ge=0, le=1)


class ProjectCreateRequest(BaseModel):
    website_url: str = Field(min_length=1, max_length=2048)
    brand_name_hint: Optional[str] = Field(default=None, min_length=1, max_length=120)
    company_name_hint: Optional[str] = Field(default=None, min_length=1, max_length=160)
    industry_hint: Optional[str] = Field(default=None, min_length=1, max_length=120)
    contact: Optional[dict[str, str]] = None
    competitor_hints: list[str] = Field(default_factory=list, max_length=10)
    automation: Optional[dict[str, Any]] = None


class ProjectData(BaseModel):
    project_id: str
    tenant_id: str
    website_url: str
    brand_name: str
    company_name: Optional[str] = None
    industry: str
    products: list[str]
    audiences: list[str]
    status: Literal["draft", "seeded", "needs_confirmation", "active", "archived"]
    automation_level: Literal["A0", "A1", "A2", "A3"]
    source_refs: list[SourceRef]
    created_at: datetime
    updated_at: datetime


class ProjectResponse(BaseModel):
    data: ProjectData
    meta: ResponseMeta


class CompetitorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    website_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    reason: Optional[str] = Field(default=None, min_length=1, max_length=500)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: Literal["suggested", "confirmed", "rejected"] = "suggested"
    source: Literal["hermes_discovered", "manual", "imported"] = "manual"


class CompetitorData(BaseModel):
    competitor_id: str
    project_id: str
    tenant_id: str
    name: str
    website_url: Optional[str] = None
    reason: Optional[str] = None
    evidence_urls: list[str]
    confidence: Optional[float] = None
    status: Literal["suggested", "confirmed", "rejected"]
    source: Literal["hermes_discovered", "manual", "imported"]
    created_at: datetime
    updated_at: datetime


class CompetitorResponse(BaseModel):
    data: CompetitorData
    meta: ResponseMeta


class BuyerQuestionCreateRequest(BaseModel):
    question_text: str = Field(min_length=4, max_length=500)
    question_type: Literal["purchase", "compare", "select", "trust", "price", "risk", "scenario", "local", "alternative"] = "purchase"
    intent_level: Literal["high", "medium", "low"] = "medium"
    buyer_stage: Literal["awareness", "consideration", "decision"] = "consideration"
    source_reason: Optional[str] = Field(default=None, min_length=1, max_length=500)
    recommended_providers: list[
        Literal["chatgpt", "deepseek", "kimi", "tongyi", "doubao", "baidu_ai_search", "yuanbao", "manual_import"]
    ] = Field(default_factory=list, max_length=8)
    status: Literal["suggested", "confirmed", "archived"] = "suggested"
    source: Literal["hermes_generated", "manual", "imported"] = "manual"


class BuyerQuestionData(BaseModel):
    question_id: str
    project_id: str
    tenant_id: str
    question_text: str
    question_type: Literal["purchase", "compare", "select", "trust", "price", "risk", "scenario", "local", "alternative"]
    intent_level: Literal["high", "medium", "low"]
    buyer_stage: Literal["awareness", "consideration", "decision"]
    source_reason: Optional[str] = None
    recommended_providers: list[str]
    coverage_status: Literal["unknown", "covered", "gap", "needs_scan"]
    status: Literal["suggested", "confirmed", "archived"]
    source: Literal["hermes_generated", "manual", "imported"]
    created_at: datetime
    updated_at: datetime


class BuyerQuestionResponse(BaseModel):
    data: BuyerQuestionData
    meta: ResponseMeta


Provider = Literal["chatgpt", "deepseek", "kimi", "tongyi", "doubao", "baidu_ai_search", "yuanbao", "manual_import"]


class QuestionScope(BaseModel):
    mode: Literal["all_active", "selected"]
    question_ids: list[str] = Field(default_factory=list)


class ScanRunCreateRequest(BaseModel):
    project_id: str
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    run_type: Literal["baseline", "retest", "manual"] = "baseline"
    provider_scope: list[Provider] = Field(min_length=1, max_length=8)
    question_scope: QuestionScope


class ScanError(BaseModel):
    code: str
    message: str


class ScanRunData(BaseModel):
    run_id: str
    tenant_id: str
    project_id: str
    name: Optional[str] = None
    run_type: Literal["baseline", "retest", "manual"]
    status: Literal["queued", "running", "completed", "failed", "canceled"]
    provider_scope: list[Provider]
    question_scope: QuestionScope
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: Optional[ScanError] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ScanTaskData(BaseModel):
    task_id: str
    run_id: str
    tenant_id: str
    project_id: str
    question_id: str
    provider: Provider
    status: Literal["queued", "running", "completed", "failed", "skipped"]
    attempt_count: int = Field(ge=0)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[ScanError] = None
    created_at: datetime
    updated_at: datetime


class ScanRunResponse(BaseModel):
    data: ScanRunData
    meta: ResponseMeta


class ScanTaskResponse(BaseModel):
    data: ScanTaskData
    meta: ResponseMeta


class ScanTaskListResponse(BaseModel):
    data: list[ScanTaskData]
    meta: ResponseMeta


class FactReviewSourceRef(BaseModel):
    source_type: str
    support_type: Literal["supports", "contradicts", "context"] = "supports"
    citation_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    object_ref_id: Optional[str] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None

    def has_traceable_source(self) -> bool:
        return bool(self.citation_id or self.object_ref_id or self.source_url)

    @model_validator(mode="after")
    def require_traceable_source(self) -> "FactReviewSourceRef":
        if not self.has_traceable_source():
            raise ValueError("fact review source ref requires citation_id, object_ref_id, or source_url")
        return self


class FactReviewRequest(BaseModel):
    action: Literal["confirmed", "rejected", "needs_redaction", "private"]
    reviewed_by: str = Field(min_length=1, max_length=64)
    trust_level: Literal["A", "B", "C", "D"] = "B"
    review_note: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    source_refs: list[FactReviewSourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_source_for_confirmed(self) -> "FactReviewRequest":
        if self.action == "confirmed" and not self.source_refs:
            raise ValueError("confirmed fact review requires at least one source ref")
        return self


class FactReviewData(BaseModel):
    fact_id: str
    tenant_id: str
    project_id: str
    review_status: Literal["confirmed", "rejected", "needs_redaction", "private"]
    fact_status: Literal["draft", "confirmed", "rejected", "stale"]
    disclosure: Literal["public", "redacted", "internal", "forbidden", "pending_approval"]
    trust_level: Literal["A", "B", "C", "D"]
    reviewed_by: str
    reviewed_at: datetime
    review_note: Optional[str] = None
    source_refs: list[FactReviewSourceRef]


class FactReviewResponse(BaseModel):
    data: FactReviewData
    meta: ResponseMeta


class AssetBundleItem(BaseModel):
    asset_id: str
    title: str
    desc: str
    progress: int = Field(ge=0, le=100)
    status: str


class AssetBundleData(BaseModel):
    project_id: str
    tenant_id: str
    completeness: int = Field(ge=0, le=100)
    recommendation: str
    assets: list[AssetBundleItem]


class AssetBundleResponse(BaseModel):
    data: AssetBundleData
    meta: ResponseMeta


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class ErrorResponse(BaseModel):
    error: ErrorInfo


class HealthStatus(BaseModel):
    status: Literal["ok"]
    service: str
    api_version: str


class VersionInfo(BaseModel):
    service: str
    version: str
    api_version: str
    api_prefix: str
    commit: str


class HealthResponse(BaseModel):
    data: HealthStatus
    meta: ResponseMeta


class VersionResponse(BaseModel):
    data: VersionInfo
    meta: ResponseMeta


class ConsoleOverviewResponse(BaseModel):
    data: ConsoleOverview
    meta: ResponseMeta


class ProjectRepository(Protocol):
    def create_project(self, tenant_id: str, payload: ProjectCreateRequest) -> ProjectData:
        ...

    def create_competitor(
        self,
        tenant_id: str,
        project_id: str,
        payload: CompetitorCreateRequest,
    ) -> CompetitorData:
        ...

    def create_buyer_question(
        self,
        tenant_id: str,
        project_id: str,
        payload: BuyerQuestionCreateRequest,
    ) -> BuyerQuestionData:
        ...


class ScanRepository(Protocol):
    def create_run(self, tenant_id: str, payload: ScanRunCreateRequest) -> ScanRunData:
        ...

    def get_run(self, tenant_id: str, run_id: str) -> ScanRunData:
        ...

    def get_task(self, tenant_id: str, task_id: str) -> ScanTaskData:
        ...

    def list_tasks(self, tenant_id: str, run_id: str) -> list[ScanTaskData]:
        ...


class FactReviewRepository(Protocol):
    def review_fact(
        self,
        tenant_id: str,
        project_id: str,
        fact_id: str,
        payload: FactReviewRequest,
    ) -> FactReviewData:
        ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def infer_brand_name(website_url: str) -> str:
    parsed = urlparse(website_url if "://" in website_url else f"https://{website_url}")
    host = parsed.netloc or parsed.path
    host = host.removeprefix("www.")
    return (host.split(".")[0] or "brand").replace("-", " ").title()


class InMemoryProjectRepository:
    """Development-only repository used until M1 MySQL persistence is wired."""

    def __init__(self) -> None:
        self._projects: dict[tuple[str, str], ProjectData] = {}
        self._competitors: dict[tuple[str, str], CompetitorData] = {}
        self._questions: dict[tuple[str, str], BuyerQuestionData] = {}

    def _ensure_project(self, tenant_id: str, project_id: str) -> ProjectData:
        project = self._projects.get((tenant_id, project_id))
        if project is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={
                    "code": "PROJECT_NOT_FOUND",
                    "details": {"project_id": project_id, "repository": "in_memory_dev"},
                },
            )
        return project

    def create_project(self, tenant_id: str, payload: ProjectCreateRequest) -> ProjectData:
        now = utc_now()
        project_id = f"project_{uuid4().hex[:12]}"
        brand_name = payload.brand_name_hint or infer_brand_name(payload.website_url)
        data = ProjectData(
            project_id=project_id,
            tenant_id=tenant_id,
            website_url=payload.website_url,
            brand_name=brand_name,
            company_name=payload.company_name_hint,
            industry=payload.industry_hint or "unknown",
            products=["AI visibility diagnosis"],
            audiences=["B2B growth leader"],
            status="needs_confirmation",
            automation_level="A1",
            source_refs=[
                SourceRef(
                    url=payload.website_url,
                    title=f"{brand_name} website seed",
                    source_type="owned",
                    captured_at=now,
                    confidence=0.6,
                )
            ],
            created_at=now,
            updated_at=now,
        )
        self._projects[(tenant_id, project_id)] = data
        return data

    def create_competitor(
        self,
        tenant_id: str,
        project_id: str,
        payload: CompetitorCreateRequest,
    ) -> CompetitorData:
        self._ensure_project(tenant_id, project_id)
        now = utc_now()
        data = CompetitorData(
            competitor_id=f"competitor_{uuid4().hex[:12]}",
            project_id=project_id,
            tenant_id=tenant_id,
            name=payload.name,
            website_url=payload.website_url,
            reason=payload.reason,
            evidence_urls=payload.evidence_urls,
            confidence=payload.confidence,
            status=payload.status,
            source=payload.source,
            created_at=now,
            updated_at=now,
        )
        self._competitors[(tenant_id, data.competitor_id)] = data
        return data

    def create_buyer_question(
        self,
        tenant_id: str,
        project_id: str,
        payload: BuyerQuestionCreateRequest,
    ) -> BuyerQuestionData:
        self._ensure_project(tenant_id, project_id)
        now = utc_now()
        data = BuyerQuestionData(
            question_id=f"question_{uuid4().hex[:12]}",
            project_id=project_id,
            tenant_id=tenant_id,
            question_text=payload.question_text,
            question_type=payload.question_type,
            intent_level=payload.intent_level,
            buyer_stage=payload.buyer_stage,
            source_reason=payload.source_reason,
            recommended_providers=payload.recommended_providers,
            coverage_status="needs_scan",
            status=payload.status,
            source=payload.source,
            created_at=now,
            updated_at=now,
        )
        self._questions[(tenant_id, data.question_id)] = data
        return data


class MySQLProjectRepository:
    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url, pool_pre_ping=True)

    def _ensure_project(self, conn: Any, tenant_id: str, project_id: str) -> None:
        row = conn.execute(
            text(
                """
                SELECT id
                FROM airank_projects
                WHERE tenant_id = :tenant_id
                  AND id = :project_id
                  AND deleted_at IS NULL
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).first()
        if row is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={
                    "code": "PROJECT_NOT_FOUND",
                    "details": {"project_id": project_id, "repository": "mysql"},
                },
            )

    def create_project(self, tenant_id: str, payload: ProjectCreateRequest) -> ProjectData:
        now = utc_now()
        project_id = f"project_{uuid4().hex[:12]}"
        brand_name = payload.brand_name_hint or infer_brand_name(payload.website_url)
        data = ProjectData(
            project_id=project_id,
            tenant_id=tenant_id,
            website_url=payload.website_url,
            brand_name=brand_name,
            company_name=payload.company_name_hint,
            industry=payload.industry_hint or "unknown",
            products=["AI visibility diagnosis"],
            audiences=["B2B growth leader"],
            status="needs_confirmation",
            automation_level="A1",
            source_refs=[
                SourceRef(
                    url=payload.website_url,
                    title=f"{brand_name} website seed",
                    source_type="owned",
                    captured_at=now,
                    confidence=0.6,
                )
            ],
            created_at=now,
            updated_at=now,
        )
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_projects (
                      id, tenant_id, name, brand_name, website_url, industry,
                      products_services_json, target_audience_json, status,
                      created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :name, :brand_name, :website_url, :industry,
                      :products_services_json, :target_audience_json, :status,
                      :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": data.project_id,
                    "tenant_id": data.tenant_id,
                    "name": data.brand_name,
                    "brand_name": data.brand_name,
                    "website_url": data.website_url,
                    "industry": data.industry,
                    "products_services_json": json.dumps(data.products, ensure_ascii=False),
                    "target_audience_json": json.dumps(data.audiences, ensure_ascii=False),
                    "status": data.status,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return data

    def create_competitor(
        self,
        tenant_id: str,
        project_id: str,
        payload: CompetitorCreateRequest,
    ) -> CompetitorData:
        now = utc_now()
        data = CompetitorData(
            competitor_id=f"competitor_{uuid4().hex[:12]}",
            project_id=project_id,
            tenant_id=tenant_id,
            name=payload.name,
            website_url=payload.website_url,
            reason=payload.reason,
            evidence_urls=payload.evidence_urls,
            confidence=payload.confidence,
            status=payload.status,
            source=payload.source,
            created_at=now,
            updated_at=now,
        )
        metadata = {
            "status": data.status,
            "source": data.source,
            "evidence_urls": data.evidence_urls,
            "confidence": data.confidence,
        }
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_competitors (
                      id, tenant_id, project_id, name, website_url, notes,
                      metadata_json, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :name, :website_url, :notes,
                      :metadata_json, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": data.competitor_id,
                    "tenant_id": data.tenant_id,
                    "project_id": data.project_id,
                    "name": data.name,
                    "website_url": data.website_url,
                    "notes": data.reason,
                    "metadata_json": json.dumps(metadata, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return data

    def create_buyer_question(
        self,
        tenant_id: str,
        project_id: str,
        payload: BuyerQuestionCreateRequest,
    ) -> BuyerQuestionData:
        now = utc_now()
        data = BuyerQuestionData(
            question_id=f"question_{uuid4().hex[:12]}",
            project_id=project_id,
            tenant_id=tenant_id,
            question_text=payload.question_text,
            question_type=payload.question_type,
            intent_level=payload.intent_level,
            buyer_stage=payload.buyer_stage,
            source_reason=payload.source_reason,
            recommended_providers=payload.recommended_providers,
            coverage_status="needs_scan",
            status=payload.status,
            source=payload.source,
            created_at=now,
            updated_at=now,
        )
        metadata = {
            "source_reason": data.source_reason,
            "recommended_providers": data.recommended_providers,
            "coverage_status": data.coverage_status,
        }
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_buyer_questions (
                      id, tenant_id, project_id, question_text, question_type,
                      intent, funnel_stage, source, status, metadata_json,
                      created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :question_text, :question_type,
                      :intent, :funnel_stage, :source, :status, :metadata_json,
                      :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": data.question_id,
                    "tenant_id": data.tenant_id,
                    "project_id": data.project_id,
                    "question_text": data.question_text,
                    "question_type": data.question_type,
                    "intent": data.intent_level,
                    "funnel_stage": data.buyer_stage,
                    "source": data.source,
                    "status": data.status,
                    "metadata_json": json.dumps(metadata, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return data


def build_project_repository() -> ProjectRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLProjectRepository(database_url)
    return InMemoryProjectRepository()


PROJECT_REPOSITORY: ProjectRepository = build_project_repository()


class InMemoryScanRepository:
    def __init__(self) -> None:
        self._runs: dict[tuple[str, str], ScanRunData] = {}
        self._tasks: dict[tuple[str, str], ScanTaskData] = {}

    def create_run(self, tenant_id: str, payload: ScanRunCreateRequest) -> ScanRunData:
        now = utc_now()
        run_id = f"scan_run_{uuid4().hex[:12]}"
        question_ids = payload.question_scope.question_ids
        if payload.question_scope.mode == "all_active" and not question_ids:
            question_ids = ["question_auto_seed"]
        question_scope = QuestionScope(mode=payload.question_scope.mode, question_ids=question_ids)
        task_count = len(payload.provider_scope) * len(question_ids)
        data = ScanRunData(
            run_id=run_id,
            tenant_id=tenant_id,
            project_id=payload.project_id,
            name=payload.name,
            run_type=payload.run_type,
            status="queued",
            provider_scope=payload.provider_scope,
            question_scope=question_scope,
            metrics={"task_count": task_count},
            created_at=now,
            updated_at=now,
        )
        self._runs[(tenant_id, run_id)] = data

        for provider in payload.provider_scope:
            for question_id in question_ids:
                task = ScanTaskData(
                    task_id=f"scan_task_{uuid4().hex[:12]}",
                    run_id=run_id,
                    tenant_id=tenant_id,
                    project_id=payload.project_id,
                    question_id=question_id,
                    provider=provider,
                    status="queued",
                    attempt_count=0,
                    scheduled_at=now,
                    created_at=now,
                    updated_at=now,
                )
                self._tasks[(tenant_id, task.task_id)] = task
        return data

    def get_run(self, tenant_id: str, run_id: str) -> ScanRunData:
        run = self._runs.get((tenant_id, run_id))
        if run is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "SCAN_RUN_NOT_FOUND", "details": {"run_id": run_id}},
            )
        return run

    def get_task(self, tenant_id: str, task_id: str) -> ScanTaskData:
        task = self._tasks.get((tenant_id, task_id))
        if task is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "JOB_NOT_FOUND", "details": {"task_id": task_id}},
            )
        return task

    def list_tasks(self, tenant_id: str, run_id: str) -> list[ScanTaskData]:
        self.get_run(tenant_id, run_id)
        return [task for (task_tenant_id, _), task in self._tasks.items() if task_tenant_id == tenant_id and task.run_id == run_id]


SCAN_REPOSITORY: ScanRepository = InMemoryScanRepository()


class InMemoryFactReviewRepository:
    def __init__(self) -> None:
        self._reviews: dict[tuple[str, str], FactReviewData] = {}

    def review_fact(
        self,
        tenant_id: str,
        project_id: str,
        fact_id: str,
        payload: FactReviewRequest,
    ) -> FactReviewData:
        if payload.action == "confirmed" and not any(source.has_traceable_source() for source in payload.source_refs):
            raise StarletteHTTPException(
                status_code=400,
                detail={
                    "code": "FACT_SOURCE_REQUIRED",
                    "details": {"fact_id": fact_id, "action": payload.action},
                },
            )

        fact_status: Literal["draft", "confirmed", "rejected", "stale"]
        disclosure: Literal["public", "redacted", "internal", "forbidden", "pending_approval"]
        if payload.action == "confirmed":
            fact_status = "confirmed"
            disclosure = "public"
        elif payload.action == "rejected":
            fact_status = "rejected"
            disclosure = "forbidden"
        elif payload.action == "needs_redaction":
            fact_status = "draft"
            disclosure = "redacted"
        else:
            fact_status = "confirmed"
            disclosure = "internal"

        data = FactReviewData(
            fact_id=fact_id,
            tenant_id=tenant_id,
            project_id=project_id,
            review_status=payload.action,
            fact_status=fact_status,
            disclosure=disclosure,
            trust_level=payload.trust_level,
            reviewed_by=payload.reviewed_by,
            reviewed_at=utc_now(),
            review_note=payload.review_note,
            source_refs=payload.source_refs,
        )
        self._reviews[(tenant_id, fact_id)] = data
        return data


FACT_REVIEW_REPOSITORY: FactReviewRepository = InMemoryFactReviewRepository()


def build_asset_bundle(tenant_id: str, project_id: str) -> AssetBundleData:
    assets = [
        AssetBundleItem(asset_id="asset_fact_page", title="企业事实页", desc="把已确认事实卡发布为 AI 易读页面", progress=86, status="可发布"),
        AssetBundleItem(asset_id="asset_service_page", title="服务介绍页", desc="结构化呈现核心服务、流程与优势", progress=72, status="待补证据"),
        AssetBundleItem(asset_id="asset_case_page", title="客户案例页", desc="承接案例、成效、行业场景与客户评价", progress=58, status="待确认"),
        AssetBundleItem(asset_id="asset_faq", title="FAQ 页", desc="覆盖高频买家问题和官方回答", progress=64, status="可生成"),
        AssetBundleItem(asset_id="asset_compare", title="竞品对比页", desc="形成差异化选型依据和对比证据", progress=45, status="缺证据"),
        AssetBundleItem(asset_id="asset_solution", title="行业解决方案页", desc="沉淀本地行业和高价值场景方案", progress=52, status="可生成"),
        AssetBundleItem(asset_id="asset_jsonld", title="JSON-LD", desc="让 AI 和搜索引擎识别品牌事实", progress=80, status="可发布"),
        AssetBundleItem(asset_id="asset_sitemap", title="sitemap.xml", desc="发布后提交抓取和复测", progress=92, status="可发布"),
    ]
    return AssetBundleData(
        project_id=project_id,
        tenant_id=tenant_id,
        completeness=68,
        recommendation="建议先补齐竞品对比页和客户案例页，再发布复测。",
        assets=assets,
    )


app = FastAPI(title="AIRank API", version="0.1.0")


def build_trace_id(trace_id: Optional[str]) -> str:
    if trace_id:
        return trace_id
    return f"trc_{uuid4().hex[:16]}"


def build_meta(trace_id: Optional[str]) -> ResponseMeta:
    return ResponseMeta(trace_id=build_trace_id(trace_id), request_id=f"req_{uuid4().hex[:16]}")


def get_request_trace_id(request: Request) -> str:
    trace_id = request.headers.get(TRACE_HEADER)
    if trace_id:
        return trace_id

    existing_trace_id = getattr(request.state, "trace_id", None)
    if isinstance(existing_trace_id, str) and existing_trace_id:
        return existing_trace_id

    generated_trace_id = build_trace_id(None)
    request.state.trace_id = generated_trace_id
    return generated_trace_id


def build_error_payload(
    code: str,
    trace_id: str,
    *,
    message: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> ErrorResponse:
    if code not in ERROR_REGISTRY:
        raise ValueError(f"Unregistered AIRank error code: {code}")

    _, default_message = ERROR_REGISTRY[code]
    return ErrorResponse(
        error=ErrorInfo(
            code=code,
            message=message or default_message,
            details=details or {},
            trace_id=trace_id,
        )
    )


def build_error_response(
    request: Request,
    code: str,
    *,
    message: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> JSONResponse:
    status_code, _ = ERROR_REGISTRY[code]
    payload = build_error_payload(
        code,
        get_request_trace_id(request),
        message=message,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(), headers=headers)


def validation_error_details(exc: RequestValidationError) -> dict[str, Any]:
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "message": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return {"errors": errors}


def http_error_details(request: Request, code: str, details: dict[str, Any]) -> dict[str, Any]:
    if code in {"RESOURCE_NOT_FOUND", "METHOD_NOT_ALLOWED"}:
        details.setdefault("path", request.url.path)
    if code == "METHOD_NOT_ALLOWED":
        details.setdefault("method", request.method)
    return details


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return build_error_response(request, "VALIDATION_FAILED", details=validation_error_details(exc))


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    fallback_code = HTTP_STATUS_DEFAULT_ERROR.get(exc.status_code, "INTERNAL_ERROR")
    code = fallback_code
    message: Optional[str] = None
    details: dict[str, Any] = {}

    if isinstance(exc.detail, dict):
        detail_code = exc.detail.get("code")
        if isinstance(detail_code, str) and detail_code in ERROR_REGISTRY:
            code = detail_code
        detail_message = exc.detail.get("message")
        if isinstance(detail_message, str) and detail_message:
            message = detail_message
        detail_payload = exc.detail.get("details")
        if isinstance(detail_payload, dict):
            details = detail_payload
    elif isinstance(exc.detail, str) and exc.detail not in {"Not Found", "Method Not Allowed"}:
        message = exc.detail

    return build_error_response(
        request,
        code,
        message=message,
        details=http_error_details(request, code, details),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
    return build_error_response(request, "INTERNAL_ERROR")


@app.get(f"{API_PREFIX}/health", response_model=HealthResponse)
def get_health(trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> HealthResponse:
    return HealthResponse(
        data=HealthStatus(status="ok", service=SERVICE_NAME, api_version=API_VERSION),
        meta=build_meta(trace_id),
    )


@app.get(f"{API_PREFIX}/version", response_model=VersionResponse)
def get_version(trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> VersionResponse:
    return VersionResponse(
        data=VersionInfo(
            service=SERVICE_NAME,
            version=app.version,
            api_version=API_VERSION,
            api_prefix=API_PREFIX,
            commit=os.getenv("AIRANK_BUILD_COMMIT", "local"),
        ),
        meta=build_meta(trace_id),
    )


@app.post(
    f"{API_PREFIX}/projects",
    response_model=ProjectResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_project(
    payload: ProjectCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ProjectResponse:
    return ProjectResponse(data=PROJECT_REPOSITORY.create_project(tenant_id, payload), meta=build_meta(trace_id))


@app.post(
    f"{API_PREFIX}/projects/{{project_id}}/competitors",
    response_model=CompetitorResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_competitor(
    project_id: str,
    payload: CompetitorCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> CompetitorResponse:
    return CompetitorResponse(
        data=PROJECT_REPOSITORY.create_competitor(tenant_id, project_id, payload),
        meta=build_meta(trace_id),
    )


@app.post(
    f"{API_PREFIX}/projects/{{project_id}}/buyer-questions",
    response_model=BuyerQuestionResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_buyer_question(
    project_id: str,
    payload: BuyerQuestionCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> BuyerQuestionResponse:
    return BuyerQuestionResponse(
        data=PROJECT_REPOSITORY.create_buyer_question(tenant_id, project_id, payload),
        meta=build_meta(trace_id),
    )


@app.post(
    f"{API_PREFIX}/scan-runs",
    response_model=ScanRunResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_scan_run(
    payload: ScanRunCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ScanRunResponse:
    return ScanRunResponse(data=SCAN_REPOSITORY.create_run(tenant_id, payload), meta=build_meta(trace_id))


@app.get(
    f"{API_PREFIX}/scan-runs/{{run_id}}",
    response_model=ScanRunResponse,
    response_model_exclude_none=True,
)
def get_scan_run(
    run_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ScanRunResponse:
    return ScanRunResponse(data=SCAN_REPOSITORY.get_run(tenant_id, run_id), meta=build_meta(trace_id))


@app.get(
    f"{API_PREFIX}/scan-runs/{{run_id}}/tasks",
    response_model=ScanTaskListResponse,
    response_model_exclude_none=True,
)
def list_scan_tasks(
    run_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ScanTaskListResponse:
    return ScanTaskListResponse(data=SCAN_REPOSITORY.list_tasks(tenant_id, run_id), meta=build_meta(trace_id))


@app.get(
    f"{API_PREFIX}/scan-tasks/{{task_id}}",
    response_model=ScanTaskResponse,
    response_model_exclude_none=True,
)
def get_scan_task(
    task_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ScanTaskResponse:
    return ScanTaskResponse(data=SCAN_REPOSITORY.get_task(tenant_id, task_id), meta=build_meta(trace_id))


@app.patch(
    f"{API_PREFIX}/projects/{{project_id}}/facts/{{fact_id}}/review",
    response_model=FactReviewResponse,
    response_model_exclude_none=True,
)
def review_fact(
    project_id: str,
    fact_id: str,
    payload: FactReviewRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> FactReviewResponse:
    return FactReviewResponse(
        data=FACT_REVIEW_REPOSITORY.review_fact(tenant_id, project_id, fact_id, payload),
        meta=build_meta(trace_id),
    )


@app.get(
    f"{API_PREFIX}/projects/{{project_id}}/asset-bundle",
    response_model=AssetBundleResponse,
)
def get_asset_bundle(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> AssetBundleResponse:
    return AssetBundleResponse(data=build_asset_bundle(tenant_id, project_id), meta=build_meta(trace_id))


@app.get(f"{API_PREFIX}/console/overview", response_model=ConsoleOverviewResponse)
def get_console_overview(
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ConsoleOverviewResponse:
    """Return the first dashboard contract shape without touching worker scheduling."""

    project_suffix = tenant_id.removeprefix("tenant_") or "demo"
    return ConsoleOverviewResponse(
        data=ConsoleOverview(
            project=ProjectOverview(
                id=f"project_{project_suffix}",
                name="示例科技有限公司",
                website="www.example.com",
                industry="营销科技",
                competitors="数智易、神策、Convertlab",
                audience="中大型企业市场与增长负责人",
                date=date(2026, 5, 17),
            ),
            metric_cards=[
                MetricCard(
                    label="AI 来客指数",
                    value="62",
                    suffix="/100",
                    delta="较上周 +12",
                    tone="primary",
                    icon="Activity",
                ),
                MetricCard(
                    label="高意向问题覆盖率",
                    value="41",
                    suffix="%",
                    delta="较上周 +8%",
                    tone="primary",
                    icon="Target",
                ),
                MetricCard(
                    label="竞品压制问题数",
                    value="127",
                    suffix="",
                    delta="较上周 +23",
                    tone="warning",
                    icon="ShieldAlert",
                ),
                MetricCard(
                    label="本月 AI 来客线索",
                    value="186",
                    suffix="",
                    delta="较上月 +36%",
                    tone="success",
                    icon="UserRound",
                ),
            ],
        ),
        meta=build_meta(trace_id),
    )

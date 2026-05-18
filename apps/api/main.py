from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from typing import Annotated, Any, Literal, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from fastapi import FastAPI, Header, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from .provider_scan import (
        ProviderCallError,
        ProviderScanResult,
        ProviderUnavailable,
        call_provider_for_brand_rank,
        probe_provider_readiness,
        provider_execution_mode,
    )
except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
    from provider_scan import (  # type: ignore[no-redef]
        ProviderCallError,
        ProviderScanResult,
        ProviderUnavailable,
        call_provider_for_brand_rank,
        probe_provider_readiness,
        provider_execution_mode,
    )

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
    "AUTH_LOGIN_FAILED": (401, "Login credentials are invalid"),
    "AUTH_YUDAO_UNAVAILABLE": (503, "Yudao authentication is unavailable"),
    "TENANT_MISMATCH": (403, "Tenant does not match the token"),
    "TENANT_FORBIDDEN": (403, "Tenant access is forbidden"),
    "PROJECT_NOT_FOUND": (404, "Project not found"),
    "PROJECT_ARCHIVED": (409, "Project is archived"),
    "QUESTION_NOT_FOUND": (404, "Question not found"),
    "QUESTION_LIMIT_EXCEEDED": (400, "Question limit exceeded"),
    "SCAN_RUN_NOT_FOUND": (404, "Scan run not found"),
    "SCAN_RUN_ALREADY_RUNNING": (409, "Scan run is already running"),
    "SCAN_TASK_NOT_FOUND": (404, "Scan task not found"),
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


ShortText = Annotated[str, Field(min_length=1, max_length=120)]
UrlText = Annotated[str, Field(min_length=1, max_length=2048)]


class ContactInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    mobile: Optional[str] = Field(default=None, min_length=5, max_length=40)
    wechat: Optional[str] = Field(default=None, min_length=1, max_length=80)
    email: Optional[str] = Field(default=None, min_length=1, max_length=160)


class ProjectAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_from_website: bool = True
    discover_competitors: bool = True
    generate_question_map: bool = True
    source: Optional[Literal["free_check", "console", "imported", "manual"]] = None


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    website_url: str = Field(min_length=1, max_length=2048)
    brand_name_hint: Optional[str] = Field(default=None, min_length=1, max_length=120)
    company_name_hint: Optional[str] = Field(default=None, min_length=1, max_length=160)
    industry_hint: Optional[str] = Field(default=None, min_length=1, max_length=120)
    contact: Optional[ContactInfo] = None
    competitor_hints: list[ShortText] = Field(default_factory=list, max_length=10)
    automation: Optional[ProjectAutomation] = None

    @field_validator("competitor_hints")
    @classmethod
    def competitor_hints_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("competitor_hints", value)


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
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    website_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    reason: Optional[str] = Field(default=None, min_length=1, max_length=500)
    evidence_urls: list[UrlText] = Field(default_factory=list, max_length=20)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: Literal["suggested", "confirmed", "rejected"] = "suggested"
    source: Literal["hermes_discovered", "manual", "imported"] = "manual"

    @field_validator("evidence_urls")
    @classmethod
    def evidence_urls_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("evidence_urls", value)


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
    model_config = ConfigDict(extra="forbid")

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

    @field_validator("recommended_providers")
    @classmethod
    def recommended_providers_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("recommended_providers", value)


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
ProjectId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^project_[A-Za-z0-9_-]+$")]
QuestionId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^question_[A-Za-z0-9_-]+$")]
FactId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^fact_[A-Za-z0-9_-]+$")]
SourceRefId = Annotated[str, Field(min_length=1, max_length=64)]
ProjectIdPath = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^project_[A-Za-z0-9_-]+$")]
FactIdPath = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^fact_[A-Za-z0-9_-]+$")]


class QuestionScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["all_active", "selected"]
    question_ids: list[QuestionId] = Field(default_factory=list)

    @field_validator("question_ids")
    @classmethod
    def question_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("question_ids", value)

    @model_validator(mode="after")
    def selected_scope_requires_questions(self) -> "QuestionScope":
        if self.mode == "selected" and not self.question_ids:
            raise ValueError("question_scope.question_ids is required when mode is selected")
        return self


class ScanRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: ProjectId
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    run_type: Literal["baseline", "retest", "manual"] = "baseline"
    provider_scope: list[Provider] = Field(min_length=1, max_length=8)
    question_scope: QuestionScope

    @field_validator("provider_scope")
    @classmethod
    def provider_scope_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("provider_scope", value)


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
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1, max_length=64)
    support_type: Literal["supports", "contradicts", "context"] = "supports"
    citation_id: Optional[SourceRefId] = None
    snapshot_id: Optional[SourceRefId] = None
    object_ref_id: Optional[SourceRefId] = None
    source_url: Optional[UrlText] = None
    source_title: Optional[str] = Field(default=None, min_length=1, max_length=240)

    def has_traceable_source(self) -> bool:
        return bool(self.citation_id or self.object_ref_id or self.source_url)

    @model_validator(mode="after")
    def require_traceable_source(self) -> "FactReviewSourceRef":
        if not self.has_traceable_source():
            raise ValueError("fact review source ref requires citation_id, object_ref_id, or source_url")
        return self


class FactReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["confirmed", "rejected", "needs_redaction", "private"]
    reviewed_by: str = Field(min_length=1, max_length=64)
    trust_level: Literal["A", "B", "C", "D"] = "B"
    review_note: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    source_refs: list[FactReviewSourceRef] = Field(default_factory=list)

    @field_validator("source_refs")
    @classmethod
    def source_refs_must_be_unique(cls, value: list[FactReviewSourceRef]) -> list[FactReviewSourceRef]:
        seen = set()
        for source_ref in value:
            key = tuple(sorted(source_ref.model_dump(mode="json", exclude_none=True).items()))
            if key in seen:
                raise ValueError("source_refs must contain unique values")
            seen.add(key)
        return value

    @model_validator(mode="after")
    def require_source_for_confirmed(self) -> "FactReviewRequest":
        if self.action == "confirmed" and not self.source_refs:
            raise ValueError("confirmed fact review requires at least one source ref")
        return self


class FactReviewData(BaseModel):
    fact_id: FactId
    tenant_id: str
    project_id: ProjectId
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
    project_id: ProjectId
    tenant_id: str
    completeness: int = Field(ge=0, le=100)
    recommendation: str
    assets: list[AssetBundleItem] = Field(min_length=1)


class AssetBundleResponse(BaseModel):
    data: AssetBundleData
    meta: ResponseMeta


class ReportItem(BaseModel):
    report_id: str
    title: str
    desc: str
    date: str
    status: str


class ReportListData(BaseModel):
    project_id: ProjectId
    tenant_id: str
    reports: list[ReportItem]


class ReportListResponse(BaseModel):
    data: ReportListData
    meta: ResponseMeta


class DownloadReceiptData(BaseModel):
    receipt_id: str
    report_id: str
    tenant_id: str
    downloaded_at: datetime
    status: Literal["recorded"]


class DownloadReceiptResponse(BaseModel):
    data: DownloadReceiptData
    meta: ResponseMeta


class ConsoleActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: ProjectId
    action_type: str = Field(min_length=3, max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$")
    label: str = Field(min_length=1, max_length=120)
    source_route: str = Field(min_length=1, max_length=160)
    entity_type: Optional[str] = Field(default=None, min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$")
    entity_id: Optional[str] = Field(default=None, min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)


class ConsoleActionData(BaseModel):
    action_id: str
    tenant_id: str
    project_id: ProjectId
    action_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    recorded_at: datetime
    status: Literal["recorded"]


class ConsoleActionResponse(BaseModel):
    data: ConsoleActionData
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


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256, repr=False)
    yudao_tenant_id: str = Field(default="1", min_length=1, max_length=64)


class AuthUser(BaseModel):
    user_id: str
    username: Optional[str] = None
    nickname: Optional[str] = None


class AuthLoginData(BaseModel):
    access_token: str
    token_type: Literal["Bearer"]
    expires_in: Optional[int] = None
    tenant_id: str
    yudao_tenant_id: str
    user: AuthUser
    dev_only: bool = False


class AuthLoginResponse(BaseModel):
    data: AuthLoginData
    meta: ResponseMeta


class BrandCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(min_length=1, max_length=120)
    website_url: str = Field(min_length=1, max_length=2048)
    industry_hint: Optional[str] = Field(default=None, min_length=1, max_length=120)
    competitor_hints: list[ShortText] = Field(default_factory=list, max_length=10)
    buyer_questions: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("competitor_hints", "buyer_questions")
    @classmethod
    def list_values_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("brand_check_list", value)


class BrandCheckData(BaseModel):
    project: ProjectData
    competitors: list[CompetitorData]
    questions: list[BuyerQuestionData]
    scan_run: ScanRunData
    tasks: list[ScanTaskData]
    asset_bundle: AssetBundleData
    reports: ReportListData
    overview: ConsoleOverview


class BrandCheckResponse(BaseModel):
    data: BrandCheckData
    meta: ResponseMeta


class ProviderReadinessItem(BaseModel):
    provider: Provider
    label: str
    status: Literal["ready", "blocked"]
    url: str
    profile_dir: str
    headless: bool
    blocker_code: Optional[
        Literal[
            "login_required",
            "captcha_required",
            "prompt_input_missing",
            "timeout",
            "network_error",
            "unknown_blocked",
        ]
    ] = None
    reason: Optional[str] = None
    screenshot_path: Optional[str] = None


class ProviderReadinessData(BaseModel):
    mode: Literal["browser", "mock"]
    minimum_success_count: int
    providers: list[ProviderReadinessItem]


class ProviderReadinessResponse(BaseModel):
    data: ProviderReadinessData
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


class AssetBundleRepository(Protocol):
    def get_bundle(self, tenant_id: str, project_id: str) -> AssetBundleData:
        ...


class ReportRepository(Protocol):
    def list_reports(self, tenant_id: str, project_id: str) -> ReportListData:
        ...

    def record_download_receipt(self, tenant_id: str, report_id: str, trace_id: str) -> DownloadReceiptData:
        ...


class ConsoleActionRepository(Protocol):
    def record_action(
        self,
        tenant_id: str,
        payload: ConsoleActionRequest,
        trace_id: str,
        actor_user_id: Optional[str] = None,
    ) -> ConsoleActionData:
        ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_unique_values(field_name: str, values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique values")
    return values


def infer_brand_name(website_url: str) -> str:
    parsed = urlparse(website_url if "://" in website_url else f"https://{website_url}")
    host = parsed.netloc or parsed.path
    host = host.removeprefix("www.")
    return ((host.split(".")[0] or "brand").replace("-", " ").title())[:120]


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
                detail={"code": "SCAN_TASK_NOT_FOUND", "details": {"task_id": task_id}},
            )
        return task

    def list_tasks(self, tenant_id: str, run_id: str) -> list[ScanTaskData]:
        self.get_run(tenant_id, run_id)
        return [task for (task_tenant_id, _), task in self._tasks.items() if task_tenant_id == tenant_id and task.run_id == run_id]


def parse_json_value(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        return json.loads(value)
    return value


def coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def api_scan_status(value: str) -> Literal["queued", "running", "completed", "failed", "canceled"]:
    if value in {"completed", "succeeded"}:
        return "completed"
    if value in {"queued", "running", "failed", "canceled"}:
        return value  # type: ignore[return-value]
    return "failed"


def api_scan_task_status(value: str) -> Literal["queued", "running", "completed", "failed", "skipped"]:
    if value in {"completed", "succeeded"}:
        return "completed"
    if value in {"queued", "running", "failed", "skipped"}:
        return value  # type: ignore[return-value]
    return "failed"


class MySQLScanRepository:
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
                detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id, "repository": "mysql"}},
            )

    def _resolve_questions(self, conn: Any, tenant_id: str, project_id: str, scope: QuestionScope) -> list[dict[str, str]]:
        rows = conn.execute(
            text(
                """
                SELECT id, question_text, status
                FROM airank_buyer_questions
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND deleted_at IS NULL
                ORDER BY priority ASC, created_at ASC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        active_questions = [
            {"id": row["id"], "question_text": row["question_text"]}
            for row in rows
            if row["status"] != "archived"
        ]

        if scope.mode == "all_active":
            if not active_questions:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "QUESTION_NOT_FOUND", "details": {"project_id": project_id, "scope": "all_active"}},
                )
            return active_questions

        questions_by_id = {question["id"]: question for question in active_questions}
        active_id_set = set(questions_by_id)
        missing = [question_id for question_id in scope.question_ids if question_id not in active_id_set]
        if missing:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "QUESTION_NOT_FOUND", "details": {"project_id": project_id, "question_ids": missing}},
            )
        return [questions_by_id[question_id] for question_id in scope.question_ids]

    def _row_to_run(self, row: Any) -> ScanRunData:
        provider_scope = parse_json_value(row["provider_scope_json"], [])
        question_scope_payload = parse_json_value(row["question_scope_json"], {"mode": "selected", "question_ids": []})
        metrics = parse_json_value(row["metrics_json"], {})
        error = ScanError(code="INTERNAL_ERROR", message=row["error_message"]) if row["error_message"] else None
        return ScanRunData(
            run_id=row["id"],
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            name=row["name"],
            run_type=row["run_type"],
            status=api_scan_status(row["status"]),
            provider_scope=provider_scope,
            question_scope=QuestionScope(**question_scope_payload),
            metrics=metrics,
            error=error,
            started_at=coerce_datetime(row["started_at"]) if row["started_at"] else None,
            finished_at=coerce_datetime(row["finished_at"]) if row["finished_at"] else None,
            created_at=coerce_datetime(row["created_at"]),
            updated_at=coerce_datetime(row["updated_at"]),
        )

    def _row_to_task(self, row: Any) -> ScanTaskData:
        error = None
        if row["error_code"] or row["error_message"]:
            error = ScanError(code=row["error_code"] or "INTERNAL_ERROR", message=row["error_message"] or "Scan task failed")
        return ScanTaskData(
            task_id=row["id"],
            run_id=row["run_id"],
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            question_id=row["question_id"],
            provider=row["provider"],
            status=api_scan_task_status(row["status"]),
            attempt_count=row["attempt_count"],
            scheduled_at=coerce_datetime(row["scheduled_at"]) if row["scheduled_at"] else None,
            started_at=coerce_datetime(row["started_at"]) if row["started_at"] else None,
            finished_at=coerce_datetime(row["finished_at"]) if row["finished_at"] else None,
            error=error,
            created_at=coerce_datetime(row["created_at"]),
            updated_at=coerce_datetime(row["updated_at"]),
        )

    def create_run(self, tenant_id: str, payload: ScanRunCreateRequest) -> ScanRunData:
        now = utc_now()
        run_id = f"scan_run_{uuid4().hex[:12]}"
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, payload.project_id)
            questions = self._resolve_questions(conn, tenant_id, payload.project_id, payload.question_scope)
            question_ids = [question["id"] for question in questions]
            question_scope = QuestionScope(mode=payload.question_scope.mode, question_ids=question_ids)
            task_count = len(payload.provider_scope) * len(question_ids)
            metrics = {"task_count": task_count}
            conn.execute(
                text(
                    """
                    INSERT INTO airank_scan_runs (
                      id, tenant_id, project_id, name, run_type, status,
                      provider_scope_json, question_scope_json, metrics_json,
                      created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :name, :run_type, :status,
                      :provider_scope_json, :question_scope_json, :metrics_json,
                      :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": run_id,
                    "tenant_id": tenant_id,
                    "project_id": payload.project_id,
                    "name": payload.name,
                    "run_type": payload.run_type,
                    "status": "queued",
                    "provider_scope_json": json.dumps(payload.provider_scope, ensure_ascii=False),
                    "question_scope_json": json.dumps(question_scope.model_dump(mode="json"), ensure_ascii=False),
                    "metrics_json": json.dumps(metrics, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            for provider in payload.provider_scope:
                for question in questions:
                    task_id = f"scan_task_{uuid4().hex[:12]}"
                    job_id = f"job_{uuid4().hex[:12]}"
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_scan_tasks (
                              id, tenant_id, project_id, run_id, question_id, provider,
                              status, attempt_count, scheduled_at, created_at, updated_at
                            )
                            VALUES (
                              :id, :tenant_id, :project_id, :run_id, :question_id, :provider,
                              :status, :attempt_count, :scheduled_at, :created_at, :updated_at
                            )
                            """
                        ),
                        {
                            "id": task_id,
                            "tenant_id": tenant_id,
                            "project_id": payload.project_id,
                            "run_id": run_id,
                            "question_id": question["id"],
                            "provider": provider,
                            "status": "queued",
                            "attempt_count": 0,
                            "scheduled_at": now,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_async_jobs (
                              id, tenant_id, project_id, job_type, status, priority,
                              scheduled_at, payload_json, created_at, updated_at
                            )
                            VALUES (
                              :id, :tenant_id, :project_id, :job_type, :status, :priority,
                              :scheduled_at, :payload_json, :created_at, :updated_at
                            )
                            """
                        ),
                        {
                            "id": job_id,
                            "tenant_id": tenant_id,
                            "project_id": payload.project_id,
                            "job_type": "scan.provider",
                            "status": "queued",
                            "priority": 100,
                            "scheduled_at": now,
                            "payload_json": json.dumps(
                                {
                                    "run_id": run_id,
                                    "scan_task_id": task_id,
                                    "question_id": question["id"],
                                    "question_text": question["question_text"],
                                    "provider": provider,
                                },
                                ensure_ascii=False,
                            ),
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
        return self.get_run(tenant_id, run_id)

    def get_run(self, tenant_id: str, run_id: str) -> ScanRunData:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM airank_scan_runs
                    WHERE tenant_id = :tenant_id
                      AND id = :run_id
                      AND deleted_at IS NULL
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run_id},
            ).mappings().first()
        if row is None:
            raise StarletteHTTPException(status_code=404, detail={"code": "SCAN_RUN_NOT_FOUND", "details": {"run_id": run_id}})
        return self._row_to_run(row)

    def get_task(self, tenant_id: str, task_id: str) -> ScanTaskData:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM airank_scan_tasks
                    WHERE tenant_id = :tenant_id
                      AND id = :task_id
                    """
                ),
                {"tenant_id": tenant_id, "task_id": task_id},
            ).mappings().first()
        if row is None:
            raise StarletteHTTPException(status_code=404, detail={"code": "SCAN_TASK_NOT_FOUND", "details": {"task_id": task_id}})
        return self._row_to_task(row)

    def list_tasks(self, tenant_id: str, run_id: str) -> list[ScanTaskData]:
        self.get_run(tenant_id, run_id)
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM airank_scan_tasks
                    WHERE tenant_id = :tenant_id
                      AND run_id = :run_id
                    ORDER BY provider ASC, question_id ASC, created_at ASC, id ASC
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run_id},
            ).mappings().all()
        return [self._row_to_task(row) for row in rows]


def build_scan_repository() -> ScanRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLScanRepository(database_url)
    return InMemoryScanRepository()


SCAN_REPOSITORY: ScanRepository = build_scan_repository()


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


class InMemoryAssetBundleRepository:
    """Development fallback for local web work when no database URL is configured."""

    def get_bundle(self, tenant_id: str, project_id: str) -> AssetBundleData:
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


def asset_progress(status: str, package_status: Optional[str]) -> int:
    if package_status in {"published", "crawling", "crawled", "indexed", "pending_retest", "retested"}:
        return 100
    return {
        "draft": 25,
        "generated": 45,
        "reviewing": 60,
        "approved": 80,
        "published": 100,
    }.get(status, 35)


class MySQLAssetBundleRepository:
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
                detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id, "repository": "mysql"}},
            )

    def get_bundle(self, tenant_id: str, project_id: str) -> AssetBundleData:
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            asset_rows = conn.execute(
                text(
                    """
                    SELECT
                      a.id,
                      a.asset_type,
                      a.title,
                      a.body_md,
                      a.status,
                      a.metadata_json,
                      a.updated_at,
                      p.status AS package_status
                    FROM airank_content_assets a
                    LEFT JOIN airank_publish_packages p
                      ON p.tenant_id = a.tenant_id
                     AND p.project_id = a.project_id
                     AND p.asset_id = a.id
                     AND p.deleted_at IS NULL
                    WHERE a.tenant_id = :tenant_id
                      AND a.project_id = :project_id
                      AND a.deleted_at IS NULL
                    ORDER BY a.updated_at DESC, a.id ASC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
            gap_rows = conn.execute(
                text(
                    """
                    SELECT id, title, severity, suggested_asset_type, status
                    FROM airank_content_gaps
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND deleted_at IS NULL
                      AND status <> 'closed'
                    ORDER BY severity ASC, updated_at DESC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()

        assets = []
        for row in asset_rows:
            metadata = parse_json_value(row["metadata_json"], {})
            display_status = None
            display_progress = None
            if isinstance(metadata, dict):
                raw_status = metadata.get("display_status")
                if isinstance(raw_status, str) and raw_status.strip():
                    display_status = raw_status.strip()
                raw_progress = metadata.get("progress")
                if isinstance(raw_progress, int) and 0 <= raw_progress <= 100:
                    display_progress = raw_progress
            assets.append(
                AssetBundleItem(
                    asset_id=row["id"],
                    title=row["title"],
                    desc=(row["body_md"] or f"{row['asset_type']} content asset")[:240],
                    progress=display_progress if display_progress is not None else asset_progress(row["status"], row["package_status"]),
                    status=display_status or row["package_status"] or row["status"],
                )
            )
        if not assets:
            assets = [
                AssetBundleItem(
                    asset_id=f"gap_{row['id']}",
                    title=row["title"],
                    desc=f"建议生成 {row['suggested_asset_type'] or 'content_asset'} 以补齐 {row['severity']} 缺口",
                    progress=0,
                    status="待生成",
                )
                for row in gap_rows[:8]
            ]
        if not assets:
            assets = [
                AssetBundleItem(
                    asset_id="asset_empty_state",
                    title="待生成资产",
                    desc="当前项目还没有可发布资产或内容缺口记录",
                    progress=0,
                    status="待生成",
                )
            ]

        completeness = round(sum(asset.progress for asset in assets) / len(assets))
        open_gap_count = len(gap_rows)
        if open_gap_count:
            recommendation = f"优先补齐 {open_gap_count} 个内容缺口，再发布 AI 收录包。"
        elif completeness < 100:
            recommendation = "继续审核并发布未完成资产，然后触发复测。"
        else:
            recommendation = "资产包已具备发布基础，建议提交抓取并安排复测。"

        return AssetBundleData(
            project_id=project_id,
            tenant_id=tenant_id,
            completeness=completeness,
            recommendation=recommendation,
            assets=assets,
        )


def build_asset_bundle_repository() -> AssetBundleRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLAssetBundleRepository(database_url)
    return InMemoryAssetBundleRepository()


ASSET_BUNDLE_REPOSITORY: AssetBundleRepository = build_asset_bundle_repository()


class InMemoryReportRepository:
    """Development fallback for local web work when no database URL is configured."""

    def list_reports(self, tenant_id: str, project_id: str) -> ReportListData:
        return ReportListData(
            project_id=project_id,
            tenant_id=tenant_id,
            reports=[
                ReportItem(report_id="report_diagnostic", title="AI 来客诊断报告", desc="覆盖平台表现、竞品压制、引用来源和优化建议", date="2026-05-17", status="已生成"),
                ReportItem(report_id="report_retest", title="推荐缺口复测报告", desc="对比发布前后推荐率、首推率和引用变化", date="2026-05-17", status="可下载"),
                ReportItem(report_id="report_exec", title="高管月报", desc="面向管理层的 AI 可见性和线索增长摘要", date="2026-05-01", status="已归档"),
            ],
        )

    def record_download_receipt(self, tenant_id: str, report_id: str, _trace_id: str) -> DownloadReceiptData:
        return DownloadReceiptData(
            receipt_id=f"receipt_{uuid4().hex[:12]}",
            report_id=report_id,
            tenant_id=tenant_id,
            downloaded_at=utc_now(),
            status="recorded",
        )


class MySQLReportRepository:
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
                detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id, "repository": "mysql"}},
            )

    def _report_desc(self, row: Any) -> str:
        metrics = parse_json_value(row["metrics_json"], {})
        if isinstance(metrics, dict):
            summary = metrics.get("summary") or metrics.get("desc")
            if isinstance(summary, str) and summary.strip():
                return summary[:240]
        return f"{row['report_type']} report with evidence index"

    def list_reports(self, tenant_id: str, project_id: str) -> ReportListData:
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            rows = conn.execute(
                text(
                    """
                    SELECT id, report_type, title, status, metrics_json, generated_at, created_at
                    FROM airank_reports
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND deleted_at IS NULL
                    ORDER BY COALESCE(generated_at, created_at) DESC, id ASC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()

        return ReportListData(
            project_id=project_id,
            tenant_id=tenant_id,
            reports=[
                ReportItem(
                    report_id=row["id"],
                    title=row["title"],
                    desc=self._report_desc(row),
                    date=coerce_datetime(row["generated_at"] or row["created_at"]).date().isoformat(),
                    status=row["status"],
                )
                for row in rows
            ],
        )

    def record_download_receipt(self, tenant_id: str, report_id: str, trace_id: str) -> DownloadReceiptData:
        receipt_id = f"receipt_{uuid4().hex[:12]}"
        downloaded_at = utc_now()
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, project_id
                    FROM airank_reports
                    WHERE tenant_id = :tenant_id
                      AND id = :report_id
                      AND deleted_at IS NULL
                    """
                ),
                {"tenant_id": tenant_id, "report_id": report_id},
            ).mappings().first()
            if row is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "REPORT_NOT_FOUND", "details": {"report_id": report_id}},
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, event_type, entity_type,
                      entity_id, trace_id, payload_json, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :event_type, :entity_type,
                      :entity_id, :trace_id, :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": receipt_id,
                    "tenant_id": tenant_id,
                    "project_id": row["project_id"],
                    "event_type": "report.download_receipt",
                    "entity_type": "report",
                    "entity_id": report_id,
                    "trace_id": trace_id,
                    "payload_json": json.dumps({"report_id": report_id, "downloaded_at": downloaded_at.isoformat()}),
                    "created_at": downloaded_at,
                },
            )
        return DownloadReceiptData(
            receipt_id=receipt_id,
            report_id=report_id,
            tenant_id=tenant_id,
            downloaded_at=downloaded_at,
            status="recorded",
        )


def build_report_repository() -> ReportRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLReportRepository(database_url)
    return InMemoryReportRepository()


REPORT_REPOSITORY: ReportRepository = build_report_repository()


class InMemoryConsoleActionRepository:
    def record_action(
        self,
        tenant_id: str,
        payload: ConsoleActionRequest,
        trace_id: str,
        actor_user_id: Optional[str] = None,
    ) -> ConsoleActionData:
        del trace_id, actor_user_id
        return ConsoleActionData(
            action_id=f"audit_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            project_id=payload.project_id,
            action_type=payload.action_type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            recorded_at=utc_now(),
            status="recorded",
        )


class MySQLConsoleActionRepository:
    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url, pool_pre_ping=True)

    def record_action(
        self,
        tenant_id: str,
        payload: ConsoleActionRequest,
        trace_id: str,
        actor_user_id: Optional[str] = None,
    ) -> ConsoleActionData:
        action_id = f"audit_{uuid4().hex[:12]}"
        recorded_at = utc_now()
        with self._engine.begin() as conn:
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
                {"tenant_id": tenant_id, "project_id": payload.project_id},
            ).first()
            if row is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": payload.project_id}},
                )

            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, actor_user_id, event_type,
                      entity_type, entity_id, trace_id, payload_json, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :actor_user_id, :event_type,
                      :entity_type, :entity_id, :trace_id, :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": action_id,
                    "tenant_id": tenant_id,
                    "project_id": payload.project_id,
                    "actor_user_id": actor_user_id,
                    "event_type": f"console.{payload.action_type}",
                    "entity_type": payload.entity_type,
                    "entity_id": payload.entity_id,
                    "trace_id": trace_id,
                    "payload_json": json.dumps(
                        {
                            "label": payload.label,
                            "source_route": payload.source_route,
                            "payload": payload.payload,
                            "recorded_at": recorded_at.isoformat(),
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    "created_at": recorded_at,
                },
            )

        return ConsoleActionData(
            action_id=action_id,
            tenant_id=tenant_id,
            project_id=payload.project_id,
            action_type=payload.action_type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            recorded_at=recorded_at,
            status="recorded",
        )


def build_console_action_repository() -> ConsoleActionRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLConsoleActionRepository(database_url)
    return InMemoryConsoleActionRepository()


CONSOLE_ACTION_REPOSITORY: ConsoleActionRepository = build_console_action_repository()


DEFAULT_PROVIDER_SCOPE: list[Provider] = ["chatgpt", "deepseek", "kimi", "tongyi", "doubao", "baidu_ai_search", "yuanbao"]

PROVIDER_LABELS: dict[str, str] = {
    "chatgpt": "ChatGPT",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "tongyi": "通义",
    "doubao": "豆包",
    "baidu_ai_search": "百度 AI 搜索",
    "yuanbao": "腾讯元宝",
    "manual_import": "人工导入",
}


def build_default_brand_questions(brand_name: str, industry: str) -> list[str]:
    return [
        f"{brand_name}适合哪些企业使用？",
        f"{brand_name}在{industry}领域有什么优势？",
        f"{brand_name}和主流竞品相比应该怎么选择？",
    ]


def minimum_provider_success_count(provider_scope: list[Provider]) -> int:
    if not provider_scope:
        return 0

    raw_value = os.getenv("AIRANK_MIN_PROVIDER_SUCCESS_COUNT") or os.getenv("AIRANK_BROWSER_MIN_SUCCESS_COUNT")
    if raw_value:
        try:
            return min(max(1, int(raw_value)), len(provider_scope))
        except ValueError:
            pass

    if provider_execution_mode() == "browser":
        return len(provider_scope)
    return 1


def minimum_scan_success_count(provider_scope: list[Provider], question_count: int, task_count: int) -> int:
    if task_count <= 0:
        return 0
    provider_minimum = minimum_provider_success_count(provider_scope)
    question_multiplier = max(1, question_count)
    return min(task_count, max(1, provider_minimum * question_multiplier))


def build_provider_readiness_items(provider_scope: list[Provider]) -> list[ProviderReadinessItem]:
    items: list[ProviderReadinessItem] = []
    for provider in provider_scope:
        try:
            result = probe_provider_readiness(provider)
        except ProviderUnavailable as exc:
            items.append(
                ProviderReadinessItem(
                    provider=provider,
                    label=PROVIDER_LABELS.get(provider, provider),
                    status="blocked",
                    url="",
                    profile_dir="",
                    headless=True,
                    blocker_code="unknown_blocked",
                    reason=exc.reason,
                )
            )
            continue

        items.append(
            ProviderReadinessItem(
                provider=result.provider,  # type: ignore[arg-type]
                label=result.label,
                status=result.status,  # type: ignore[arg-type]
                url=result.url,
                profile_dir=result.profile_dir,
                headless=result.headless,
                blocker_code=result.blocker_code,  # type: ignore[arg-type]
                reason=result.reason,
                screenshot_path=result.screenshot_path,
            )
        )
    return items


def assert_browser_provider_ready_for_brand_check(existing_project_id: Optional[str] = None) -> None:
    if not os.getenv("AIRANK_DATABASE_URL") or provider_execution_mode() != "browser":
        return

    items = build_provider_readiness_items(DEFAULT_PROVIDER_SCOPE)
    minimum_success_count = minimum_provider_success_count(DEFAULT_PROVIDER_SCOPE)
    ready_count = sum(1 for item in items if item.status == "ready")
    if ready_count >= minimum_success_count:
        return

    raise StarletteHTTPException(
        status_code=503,
        detail={
            "code": "INTEGRATION_CAPABILITY_BLOCKED",
            "message": "外部 AI 消费端网页尚未全部 ready；请先完成浏览器 profile 登录/真人验证，再创建真实 GEO 检测。",
            "details": {
                "provider_mode": provider_execution_mode(),
                "ready_count": ready_count,
                "minimum_success_count": minimum_success_count,
                "existing_project_id": existing_project_id,
                "providers": [item.model_dump(exclude_none=True) for item in items],
            },
        },
    )


def build_competitor_payloads(brand_name: str, competitor_hints: list[str]) -> list[CompetitorCreateRequest]:
    names = competitor_hints or ["火山引擎", "阿里云通义", "百度智能云"]
    return [
        CompetitorCreateRequest(
            name=name,
            reason=f"用于评估 {brand_name} 在 AI 平台回答中的推荐排名和竞品压制情况",
            confidence=0.8,
            status="confirmed",
            source="manual",
        )
        for name in names
    ]


def build_question_payloads(brand_name: str, industry: str, buyer_questions: list[str]) -> list[BuyerQuestionCreateRequest]:
    questions = buyer_questions or build_default_brand_questions(brand_name, industry)
    question_types = ["purchase", "scenario", "compare"]
    return [
        BuyerQuestionCreateRequest(
            question_text=question,
            question_type=question_types[index % len(question_types)],  # type: ignore[arg-type]
            intent_level="high",
            buyer_stage="consideration",
            source_reason=f"{brand_name} 品牌检测自动生成的高意向买家问题",
            recommended_providers=DEFAULT_PROVIDER_SCOPE,
            status="confirmed",
            source="manual",
        )
        for index, question in enumerate(questions)
    ]


def provider_quality(provider: str, index: int) -> tuple[int, int, int]:
    base = {
        "chatgpt": (78, 56, 31),
        "deepseek": (74, 52, 28),
        "kimi": (70, 47, 24),
        "tongyi": (68, 45, 22),
        "doubao": (72, 49, 25),
        "baidu_ai_search": (64, 42, 20),
        "yuanbao": (61, 39, 18),
    }.get(provider, (58, 35, 15))
    drift = index % 3
    return (max(0, base[0] - drift), max(0, base[1] - drift), max(0, base[2] - drift))


def build_scan_metrics(task_count: int, provider_count: int) -> dict[str, Any]:
    return {
        "task_count": task_count,
        "provider_count": provider_count,
        "ai_visibility_score": 72,
        "question_coverage": 68,
        "competitor_pressure_count": 18,
        "monthly_leads": 96,
        "mention_rate": 69,
        "recommend_rate": 47,
        "first_rank_rate": 24,
        "summary": "已完成多 AI 平台品牌可见度检测，并生成可发布资产与老板报告。",
    }


def mysql_engine() -> Optional[Any]:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if not database_url:
        return None
    return create_engine(database_url, pool_pre_ping=True)


def percentage(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return round((numerator / denominator) * 100)


def build_real_scan_metrics(
    results: list[ProviderScanResult],
    failed_count: int,
    blocked_count: int,
    total_count: int,
    provider_count: int,
) -> dict[str, Any]:
    success_count = len(results)
    mention_count = sum(1 for result in results if result.brand_mentioned)
    top_three_count = sum(1 for result in results if result.brand_rank is not None and result.brand_rank <= 3)
    first_rank_count = sum(1 for result in results if result.brand_rank == 1)
    competitor_pressure_count = 0
    for result in results:
        if result.brand_rank is None or result.brand_rank > 1:
            competitor_pressure_count += 1
            continue
        for competitor in result.competitor_mentions:
            competitor_rank = competitor.get("rank")
            if isinstance(competitor_rank, int) and competitor_rank < result.brand_rank:
                competitor_pressure_count += 1
                break

    mention_rate = percentage(mention_count, success_count)
    recommend_rate = percentage(top_three_count, success_count)
    first_rank_rate = percentage(first_rank_count, success_count)
    question_coverage = percentage(success_count, total_count)
    ai_visibility_score = round((mention_rate * 0.45) + (recommend_rate * 0.35) + (first_rank_rate * 0.2))
    return {
        "task_count": total_count,
        "provider_count": provider_count,
        "provider_success_count": success_count,
        "provider_failed_count": failed_count,
        "provider_blocked_count": blocked_count,
        "ai_visibility_score": ai_visibility_score,
        "question_coverage": question_coverage,
        "competitor_pressure_count": competitor_pressure_count,
        "monthly_leads": max(0, round(ai_visibility_score * 1.2)),
        "mention_rate": mention_rate,
        "recommend_rate": recommend_rate,
        "first_rank_rate": first_rank_rate,
        "summary": (
            f"通过消费端网页完成 {success_count}/{total_count} 个真实检测任务；"
            f"品牌提及率 {mention_rate}%，前三推荐率 {recommend_rate}%，首推率 {first_rank_rate}%。"
        ),
    }


def insert_mysql_brand_assets(
    conn: Any,
    tenant_id: str,
    project: ProjectData,
    competitors: list[CompetitorData],
    questions: list[BuyerQuestionData],
    run: ScanRunData,
    metrics: dict[str, Any],
    now: datetime,
) -> None:
    fact_specs = [
        ("brand_identity", "企业定位", f"{project.brand_name} 是面向{project.industry}场景的企业服务品牌。"),
        ("product_service", "核心服务", f"{project.brand_name} 可围绕 AI 搜索可见性、内容资产和线索增长提供服务。"),
        ("faq", "高频问答", f"{project.brand_name} 需要优先回答适用客户、竞品对比、实施流程和证据来源。"),
        ("competitor_diff", "竞品差异", f"{project.brand_name} 的 AI 推荐提升关键在于补齐公开证据与结构化资产。"),
    ]
    fact_ids = []
    for fact_type, title, fact_text in fact_specs:
        fact_id = f"fact_{uuid4().hex[:12]}"
        fact_ids.append(fact_id)
        conn.execute(
            text(
                """
                INSERT INTO airank_fact_atoms (
                  id, tenant_id, project_id, fact_type, title, fact_text,
                  source_type, source_excerpt, trust_level, disclosure,
                  status, ai_confidence, applicable_question_ids,
                  applicable_asset_types, reviewed_by, reviewed_at,
                  metadata_json, created_at, updated_at
                )
                VALUES (
                  :id, :tenant_id, :project_id, :fact_type, :title, :fact_text,
                  :source_type, :source_excerpt, :trust_level, :disclosure,
                  :status, :ai_confidence, :applicable_question_ids,
                  :applicable_asset_types, :reviewed_by, :reviewed_at,
                  :metadata_json, :created_at, :updated_at
                )
                """
            ),
            {
                "id": fact_id,
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "fact_type": fact_type,
                "title": title,
                "fact_text": fact_text,
                "source_type": "brand_check",
                "source_excerpt": fact_text,
                "trust_level": "B",
                "disclosure": "public",
                "status": "confirmed",
                "ai_confidence": 0.86,
                "applicable_question_ids": json.dumps([question.question_id for question in questions], ensure_ascii=False),
                "applicable_asset_types": json.dumps(["fact_page", "faq", "compare", "report"], ensure_ascii=False),
                "reviewed_by": "brand_check",
                "reviewed_at": now,
                "metadata_json": json.dumps({"run_id": run.run_id, "provider_mode": provider_execution_mode()}, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            },
        )

    gap_specs = [
        ("high", "第三方权威信源不足", "需要补齐媒体报道、园区/行业背书、客户案例等可引用来源。", "authority_source_page"),
        ("medium", "竞品对比证据不足", "需要生成可公开的差异化选型资料，降低 AI 回答偏向竞品的概率。", "competitor_compare_page"),
    ]
    for severity, title, description, asset_type in gap_specs:
        conn.execute(
            text(
                """
                INSERT INTO airank_content_gaps (
                  id, tenant_id, project_id, run_id, gap_type, severity,
                  title, description, related_question_ids,
                  related_competitor_ids, suggested_asset_type,
                  status, created_at, updated_at
                )
                VALUES (
                  :id, :tenant_id, :project_id, :run_id, :gap_type, :severity,
                  :title, :description, :related_question_ids,
                  :related_competitor_ids, :suggested_asset_type,
                  :status, :created_at, :updated_at
                )
                """
            ),
            {
                "id": f"gap_{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "run_id": run.run_id,
                "gap_type": "evidence_gap",
                "severity": severity,
                "title": title,
                "description": description,
                "related_question_ids": json.dumps([question.question_id for question in questions], ensure_ascii=False),
                "related_competitor_ids": json.dumps([competitor.competitor_id for competitor in competitors], ensure_ascii=False),
                "suggested_asset_type": asset_type,
                "status": "open",
                "created_at": now,
                "updated_at": now,
            },
        )

    asset_specs = [
        ("fact_page", f"{project.brand_name} 企业事实页", "已整理品牌定位、官网来源、核心服务和公开事实，适合发布为 AI 可引用页面。", 92),
        ("service_page", f"{project.brand_name} 服务介绍页", "围绕服务能力、适用客户、交付流程和业务价值生成结构化介绍。", 88),
        ("faq", f"{project.brand_name} 高频问答 FAQ", "覆盖买家最常问的适用场景、竞品对比、实施流程和证据来源。", 86),
        ("compare", f"{project.brand_name} 竞品对比页", "把主流竞品差异、选择建议和补证方向整理成可公开对比资料。", 82),
        ("solution", f"{project.brand_name} 行业解决方案页", f"面向{project.industry}客户生成可被 AI 摘要和引用的场景方案。", 84),
        ("case_page", f"{project.brand_name} 客户案例页", "预留案例结构、价值指标和证明材料入口，方便后续补充真实案例。", 74),
        ("jsonld", f"{project.brand_name} JSON-LD 结构化数据", "生成 Organization、FAQ、Service 等结构化字段，提升 AI 理解效率。", 90),
        ("sitemap", f"{project.brand_name} sitemap.xml", "收录包页面可加入 sitemap 并提交抓取，进入发布复测闭环。", 90),
    ]
    for asset_type, title, body, progress in asset_specs:
        asset_id = f"asset_{uuid4().hex[:12]}"
        conn.execute(
            text(
                """
                INSERT INTO airank_content_assets (
                  id, tenant_id, project_id, asset_type, title,
                  body_md, status, fact_atom_ids, target_url,
                  reviewed_by, reviewed_at, metadata_json,
                  created_at, updated_at
                )
                VALUES (
                  :id, :tenant_id, :project_id, :asset_type, :title,
                  :body_md, :status, :fact_atom_ids, :target_url,
                  :reviewed_by, :reviewed_at, :metadata_json,
                  :created_at, :updated_at
                )
                """
            ),
            {
                "id": asset_id,
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "asset_type": asset_type,
                "title": title,
                "body_md": body,
                "status": "generated",
                "fact_atom_ids": json.dumps(fact_ids, ensure_ascii=False),
                "target_url": f"{project.website_url.rstrip('/')}/airank/{asset_type}",
                "reviewed_by": "brand_check",
                "reviewed_at": now,
                "metadata_json": json.dumps({"progress": progress, "display_status": "已生成", "run_id": run.run_id}, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_publish_packages (
                  id, tenant_id, project_id, asset_id, package_type,
                  channel, status, package_ref_id, published_url,
                  platform_meta_json, metadata_json, created_at, updated_at
                )
                VALUES (
                  :id, :tenant_id, :project_id, :asset_id, :package_type,
                  :channel, :status, :package_ref_id, :published_url,
                  :platform_meta_json, :metadata_json, :created_at, :updated_at
                )
                """
            ),
            {
                "id": f"pkg_{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "asset_id": asset_id,
                "package_type": "content_asset",
                "channel": "website",
                "status": "packaged",
                "package_ref_id": f"brand_check:{run.run_id}:{asset_type}",
                "published_url": f"{project.website_url.rstrip('/')}/airank/{asset_type}",
                "platform_meta_json": json.dumps({"asset_type": asset_type}, ensure_ascii=False),
                "metadata_json": json.dumps({"ready_for_publish": True}, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            },
        )

    report_specs = [
        ("diagnostic", f"{project.brand_name} AI 来客诊断报告", "覆盖多 AI 平台排名、推荐率、首推率、引用来源和竞品压制点。"),
        ("executive", f"{project.brand_name} 老板报告", "用管理层可读方式汇总 AI 可见性、内容缺口和下一步发布动作。"),
        ("asset_bundle", f"{project.brand_name} 可发布资料包", "汇总企业事实页、FAQ、竞品对比页、行业解决方案页和结构化数据。"),
        ("competitor", f"{project.brand_name} 竞品压制报告", "对比主流竞品在高意向买家问题中的推荐占位和证据差距。"),
    ]
    for report_type, title, summary in report_specs:
        conn.execute(
            text(
                """
                INSERT INTO airank_reports (
                  id, tenant_id, project_id, report_type, title,
                  status, run_id, metrics_json, generated_by,
                  generated_at, created_at, updated_at
                )
                VALUES (
                  :id, :tenant_id, :project_id, :report_type, :title,
                  :status, :run_id, :metrics_json, :generated_by,
                  :generated_at, :created_at, :updated_at
                )
                """
            ),
            {
                "id": f"report_{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "report_type": report_type,
                "title": title,
                "status": "可下载",
                "run_id": run.run_id,
                "metrics_json": json.dumps({**metrics, "summary": summary}, ensure_ascii=False),
                "generated_by": "brand_check",
                "generated_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )


def complete_in_memory_brand_scan(tenant_id: str, run_id: str) -> None:
    if not isinstance(SCAN_REPOSITORY, InMemoryScanRepository):
        return

    run = SCAN_REPOSITORY._runs.get((tenant_id, run_id))
    if run is None:
        return

    now = utc_now()
    related_tasks = [
        task
        for (task_tenant_id, _), task in SCAN_REPOSITORY._tasks.items()
        if task_tenant_id == tenant_id and task.run_id == run_id
    ]
    for task in related_tasks:
        SCAN_REPOSITORY._tasks[(tenant_id, task.task_id)] = task.model_copy(
            update={"status": "completed", "attempt_count": 1, "started_at": now, "finished_at": now, "updated_at": now}
        )
    SCAN_REPOSITORY._runs[(tenant_id, run_id)] = run.model_copy(
        update={
            "status": "completed",
            "started_at": now,
            "finished_at": now,
            "updated_at": now,
            "metrics": build_scan_metrics(len(related_tasks), len(run.provider_scope)),
        }
    )


def complete_mysql_real_brand_scan(
    tenant_id: str,
    project: ProjectData,
    competitors: list[CompetitorData],
    questions: list[BuyerQuestionData],
    run: ScanRunData,
) -> None:
    engine = mysql_engine()
    if engine is None:
        return

    started_at = utc_now()
    competitor_names = [competitor.name for competitor in competitors]
    question_by_id = {question.question_id: question.question_text for question in questions}
    successes: list[tuple[dict[str, Any], ProviderScanResult]] = []
    failures: list[dict[str, Any]] = []

    with engine.begin() as conn:
        task_rows = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT id, question_id, provider
                    FROM airank_scan_tasks
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND run_id = :run_id
                    ORDER BY provider ASC, question_id ASC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id},
            ).mappings().all()
        ]
        conn.execute(
            text(
                """
                UPDATE airank_scan_runs
                SET status = 'running',
                    started_at = COALESCE(started_at, :now),
                    updated_at = :now
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id = :run_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id, "now": started_at},
        )

    for row in task_rows:
        provider = str(row["provider"])
        question_text = question_by_id.get(str(row["question_id"]), f"{project.brand_name} 是否值得选择？")
        task_started_at = utc_now()
        try:
            result = call_provider_for_brand_rank(
                provider=provider,
                brand_name=project.brand_name,
                website_url=project.website_url,
                industry=project.industry,
                competitor_names=competitor_names,
                question_text=question_text,
            )
        except ProviderUnavailable as exc:
            failures.append(
                {
                    **row,
                    "started_at": task_started_at,
                    "finished_at": utc_now(),
                    "error_code": "SCAN_PROVIDER_BLOCKED",
                    "error_message": exc.reason,
                    "blocked": True,
                }
            )
            continue
        except ProviderCallError as exc:
            code = "SCAN_PROVIDER_TIMEOUT" if "timeout" in exc.reason.lower() else "SCAN_PROVIDER_BLOCKED"
            failures.append(
                {
                    **row,
                    "started_at": task_started_at,
                    "finished_at": utc_now(),
                    "error_code": code,
                    "error_message": exc.reason[:1000],
                    "blocked": code == "SCAN_PROVIDER_BLOCKED",
                }
            )
            continue
        successes.append((row, result))

    finished_at = utc_now()
    failed_count = len(failures)
    blocked_count = sum(1 for failure in failures if failure.get("blocked"))
    provider_minimum_success_count = minimum_provider_success_count(run.provider_scope)
    minimum_success_count = minimum_scan_success_count(run.provider_scope, len(questions), len(task_rows))
    success_count = len(successes)
    metrics = build_real_scan_metrics(
        [result for _, result in successes],
        failed_count=failed_count,
        blocked_count=blocked_count,
        total_count=len(task_rows),
        provider_count=len(run.provider_scope),
    )
    metrics.update(
        {
            "provider_minimum_success_count": provider_minimum_success_count,
            "minimum_success_count": minimum_success_count,
            "provider_mode": provider_execution_mode(),
        }
    )
    run_status = "completed" if success_count >= minimum_success_count else "failed"
    run_error_message = None
    if run_status == "failed" and provider_execution_mode() == "browser":
        run_error_message = (
            f"Only {success_count}/{minimum_success_count} required consumer web scan tasks completed; "
            "browser login or human verification may be required."
        )
    elif run_status == "failed":
        run_error_message = "No configured external AI provider completed successfully; AIRank did not generate ranking results."

    with engine.begin() as conn:
        for row, result in successes:
            snapshot_id = f"snap_{uuid4().hex[:12]}"
            citation_id = f"cite_{uuid4().hex[:12]}"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, answer_text, brand_mentioned, brand_rank,
                      competitor_mentions_json, sentiment, confidence,
                      external_trace_id, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :answer_text, :brand_mentioned, :brand_rank,
                      :competitor_mentions_json, :sentiment, :confidence,
                      :external_trace_id, :created_at
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": row["id"],
                    "question_id": row["question_id"],
                    "provider": result.provider,
                    "answer_text": result.answer_text,
                    "brand_mentioned": 1 if result.brand_mentioned else 0,
                    "brand_rank": result.brand_rank,
                    "competitor_mentions_json": json.dumps(result.competitor_mentions, ensure_ascii=False),
                    "sentiment": result.sentiment,
                    "confidence": result.confidence,
                    "external_trace_id": result.external_trace_id,
                    "created_at": finished_at,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_source_citations (
                      id, tenant_id, project_id, snapshot_id, citation_order,
                      title, url, host, source_type, cited_text,
                      relevance_score, metadata_json, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :snapshot_id, :citation_order,
                      :title, :url, :host, :source_type, :cited_text,
                      :relevance_score, :metadata_json, :created_at
                    )
                    """
                ),
                {
                    "id": citation_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "snapshot_id": snapshot_id,
                    "citation_order": 1,
                    "title": f"{result.provider_label} 原始回答",
                    "url": None,
                    "host": result.provider[:255],
                    "source_type": "provider_answer",
                    "cited_text": result.answer_text[:1000],
                    "relevance_score": result.confidence,
                    "metadata_json": json.dumps(result.raw_metadata, ensure_ascii=False, default=str),
                    "created_at": finished_at,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status = 'completed',
                        attempt_count = GREATEST(attempt_count, 1),
                        started_at = COALESCE(started_at, :started_at),
                        finished_at = :finished_at,
                        updated_at = :finished_at,
                        error_code = NULL,
                        error_message = NULL,
                        response_meta_json = :response_meta_json
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND run_id = :run_id
                      AND id = :task_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": row["id"],
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "response_meta_json": json.dumps(
                        {"mode": "consumer_browser", "provider": result.provider, **result.raw_metadata},
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs
                    SET status = 'completed',
                        started_at = COALESCE(started_at, :started_at),
                        finished_at = :finished_at,
                        result_json = :result_json,
                        updated_at = :finished_at,
                        error_code = NULL,
                        error_message = NULL
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND job_type = 'scan.provider'
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.scan_task_id')) = :task_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "task_id": row["id"],
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "result_json": json.dumps({"status": "completed", "provider": result.provider}, ensure_ascii=False),
                },
            )

        for failure in failures:
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status = 'failed',
                        attempt_count = GREATEST(attempt_count, 1),
                        started_at = COALESCE(started_at, :started_at),
                        finished_at = :finished_at,
                        updated_at = :finished_at,
                        error_code = :error_code,
                        error_message = :error_message,
                        response_meta_json = :response_meta_json
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND run_id = :run_id
                      AND id = :task_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": failure["id"],
                    "started_at": failure["started_at"],
                    "finished_at": failure["finished_at"],
                    "error_code": failure["error_code"],
                    "error_message": failure["error_message"],
                    "response_meta_json": json.dumps(
                        {
                            "mode": "consumer_browser",
                            "provider": failure["provider"],
                            "blocked": failure.get("blocked", False),
                        },
                        ensure_ascii=False,
                    ),
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs
                    SET status = 'failed',
                        started_at = COALESCE(started_at, :started_at),
                        finished_at = :finished_at,
                        updated_at = :finished_at,
                        error_code = :error_code,
                        error_message = :error_message
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND job_type = 'scan.provider'
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.scan_task_id')) = :task_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "task_id": failure["id"],
                    "started_at": failure["started_at"],
                    "finished_at": failure["finished_at"],
                    "error_code": failure["error_code"],
                    "error_message": failure["error_message"],
                },
            )

        conn.execute(
            text(
                """
                UPDATE airank_scan_runs
                SET status = :status,
                    metrics_json = :metrics_json,
                    error_message = :error_message,
                    started_at = COALESCE(started_at, :started_at),
                    finished_at = :finished_at,
                    updated_at = :finished_at
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id = :run_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "run_id": run.run_id,
                "status": run_status,
                "metrics_json": json.dumps(metrics, ensure_ascii=False),
                "error_message": run_error_message,
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )

        if run_status == "completed":
            conn.execute(
                text(
                    """
                    UPDATE airank_projects
                    SET status = 'active',
                        updated_at = :now
                    WHERE tenant_id = :tenant_id
                      AND id = :project_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id, "now": finished_at},
            )
            insert_mysql_brand_assets(conn, tenant_id, project, competitors, questions, run, metrics, finished_at)

    if run_status != "completed":
        raise StarletteHTTPException(
            status_code=503,
            detail={
                "code": "INTEGRATION_CAPABILITY_BLOCKED",
                "message": "外部 AI 消费端网页真实采样未达到生产门槛，请先为浏览器 profile 完成网页登录态或处理真人验证。",
                "details": {
                    "run_id": run.run_id,
                    "provider_mode": provider_execution_mode(),
                    "providers": run.provider_scope,
                    "success_count": success_count,
                    "minimum_success_count": minimum_success_count,
                    "provider_minimum_success_count": provider_minimum_success_count,
                    "failed_count": failed_count,
                    "blocked_count": blocked_count,
                    "failures": [
                        {
                            "provider": failure["provider"],
                            "code": failure["error_code"],
                            "message": failure["error_message"],
                        }
                        for failure in failures[:8]
                    ],
                },
            },
        )


def complete_mysql_brand_scan(
    tenant_id: str,
    project: ProjectData,
    competitors: list[CompetitorData],
    questions: list[BuyerQuestionData],
    run: ScanRunData,
) -> None:
    if provider_execution_mode() != "mock":
        complete_mysql_real_brand_scan(tenant_id, project, competitors, questions, run)
        return

    engine = mysql_engine()
    if engine is None:
        return

    now = utc_now()
    host = urlparse(project.website_url if "://" in project.website_url else f"https://{project.website_url}").netloc or project.website_url
    metrics = build_scan_metrics(len(run.provider_scope) * len(questions), len(run.provider_scope))
    competitor_names = [competitor.name for competitor in competitors]
    question_by_id = {question.question_id: question.question_text for question in questions}

    with engine.begin() as conn:
        task_rows = conn.execute(
            text(
                """
                SELECT id, question_id, provider
                FROM airank_scan_tasks
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND run_id = :run_id
                ORDER BY provider ASC, question_id ASC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id},
        ).mappings().all()

        for index, row in enumerate(task_rows):
            provider = row["provider"]
            provider_label = PROVIDER_LABELS.get(provider, provider)
            mention, recommend, first = provider_quality(provider, index)
            brand_rank = 1 + (index % 3)
            question_text = question_by_id.get(row["question_id"], f"{project.brand_name} 是否值得选择？")
            snapshot_id = f"snap_{uuid4().hex[:12]}"
            citation_id = f"cite_{uuid4().hex[:12]}"
            answer_text = (
                f"在“{question_text}”这个问题下，{provider_label} 已识别到 {project.brand_name}。"
                f"当前综合推荐排名为第 {brand_rank} 位，提及率约 {mention}%，推荐率约 {recommend}%，"
                f"首推机会约 {first}%。建议继续补充官网事实页、客户案例、竞品对比和 FAQ，"
                "让 AI 平台更容易引用公开证据。"
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, answer_text, brand_mentioned, brand_rank,
                      competitor_mentions_json, sentiment, confidence,
                      external_trace_id, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :answer_text, :brand_mentioned, :brand_rank,
                      :competitor_mentions_json, :sentiment, :confidence,
                      :external_trace_id, :created_at
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": row["id"],
                    "question_id": row["question_id"],
                    "provider": provider,
                    "answer_text": answer_text,
                    "brand_mentioned": 1,
                    "brand_rank": brand_rank,
                    "competitor_mentions_json": json.dumps(
                        [{"name": name, "rank": min(4, brand_rank + competitor_index + 1)} for competitor_index, name in enumerate(competitor_names)],
                        ensure_ascii=False,
                    ),
                    "sentiment": "positive",
                    "confidence": 0.82,
                    "external_trace_id": f"brand_check:{run.run_id}:{row['id']}",
                    "created_at": now,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_source_citations (
                      id, tenant_id, project_id, snapshot_id, citation_order,
                      title, url, host, source_type, cited_text,
                      relevance_score, metadata_json, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :snapshot_id, :citation_order,
                      :title, :url, :host, :source_type, :cited_text,
                      :relevance_score, :metadata_json, :created_at
                    )
                    """
                ),
                {
                    "id": citation_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "snapshot_id": snapshot_id,
                    "citation_order": 1,
                    "title": f"{project.brand_name} 官方网站",
                    "url": project.website_url,
                    "host": host[:255],
                    "source_type": "owned",
                    "cited_text": f"{project.brand_name} 官方公开资料与业务介绍",
                    "relevance_score": 0.88,
                    "metadata_json": json.dumps({"provider": provider, "question_id": row["question_id"]}, ensure_ascii=False),
                    "created_at": now,
                },
            )

        conn.execute(
            text(
                """
                UPDATE airank_scan_tasks
                SET status = 'completed',
                    attempt_count = GREATEST(attempt_count, 1),
                    started_at = COALESCE(started_at, :now),
                    finished_at = :now,
                    updated_at = :now,
                    response_meta_json = :response_meta_json
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND run_id = :run_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "run_id": run.run_id,
                "now": now,
                "response_meta_json": json.dumps({"mode": "brand_check_generated"}, ensure_ascii=False),
            },
        )
        conn.execute(
            text(
                """
                UPDATE airank_scan_runs
                SET status = 'completed',
                    metrics_json = :metrics_json,
                    started_at = COALESCE(started_at, :now),
                    finished_at = :now,
                    updated_at = :now
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id = :run_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "run_id": run.run_id,
                "metrics_json": json.dumps(metrics, ensure_ascii=False),
                "now": now,
            },
        )
        conn.execute(
            text(
                """
                UPDATE airank_async_jobs
                SET status = 'completed',
                    started_at = COALESCE(started_at, :now),
                    finished_at = :now,
                    result_json = :result_json,
                    updated_at = :now
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND job_type = 'scan.provider'
                  AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id')) = :run_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "run_id": run.run_id,
                "now": now,
                "result_json": json.dumps({"status": "completed", "mode": "brand_check_generated"}, ensure_ascii=False),
            },
        )
        conn.execute(
            text(
                """
                UPDATE airank_projects
                SET status = 'active',
                    updated_at = :now
                WHERE tenant_id = :tenant_id
                  AND id = :project_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project.project_id, "now": now},
        )

        fact_specs = [
            ("brand_identity", "企业定位", f"{project.brand_name} 是面向{project.industry}场景的企业服务品牌。"),
            ("product_service", "核心服务", f"{project.brand_name} 可围绕 AI 搜索可见性、内容资产和线索增长提供服务。"),
            ("faq", "高频问答", f"{project.brand_name} 需要优先回答适用客户、竞品对比、实施流程和证据来源。"),
            ("competitor_diff", "竞品差异", f"{project.brand_name} 的 AI 推荐提升关键在于补齐公开证据与结构化资产。"),
        ]
        fact_ids = []
        for fact_type, title, fact_text in fact_specs:
            fact_id = f"fact_{uuid4().hex[:12]}"
            fact_ids.append(fact_id)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_fact_atoms (
                      id, tenant_id, project_id, fact_type, title, fact_text,
                      source_type, source_excerpt, trust_level, disclosure,
                      status, ai_confidence, applicable_question_ids,
                      applicable_asset_types, reviewed_by, reviewed_at,
                      metadata_json, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :fact_type, :title, :fact_text,
                      :source_type, :source_excerpt, :trust_level, :disclosure,
                      :status, :ai_confidence, :applicable_question_ids,
                      :applicable_asset_types, :reviewed_by, :reviewed_at,
                      :metadata_json, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": fact_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "fact_type": fact_type,
                    "title": title,
                    "fact_text": fact_text,
                    "source_type": "brand_check",
                    "source_excerpt": fact_text,
                    "trust_level": "B",
                    "disclosure": "public",
                    "status": "confirmed",
                    "ai_confidence": 0.86,
                    "applicable_question_ids": json.dumps([question.question_id for question in questions], ensure_ascii=False),
                    "applicable_asset_types": json.dumps(["fact_page", "faq", "compare", "report"], ensure_ascii=False),
                    "reviewed_by": "brand_check",
                    "reviewed_at": now,
                    "metadata_json": json.dumps({"run_id": run.run_id}, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )

        gap_specs = [
            ("high", "第三方权威信源不足", "需要补齐媒体报道、园区/行业背书、客户案例等可引用来源。", "authority_source_page"),
            ("medium", "竞品对比证据不足", "需要生成可公开的差异化选型资料，降低 AI 回答偏向竞品的概率。", "competitor_compare_page"),
        ]
        for severity, title, description, asset_type in gap_specs:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_gaps (
                      id, tenant_id, project_id, run_id, gap_type, severity,
                      title, description, related_question_ids,
                      related_competitor_ids, suggested_asset_type,
                      status, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :run_id, :gap_type, :severity,
                      :title, :description, :related_question_ids,
                      :related_competitor_ids, :suggested_asset_type,
                      :status, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": f"gap_{uuid4().hex[:12]}",
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "gap_type": "evidence_gap",
                    "severity": severity,
                    "title": title,
                    "description": description,
                    "related_question_ids": json.dumps([question.question_id for question in questions], ensure_ascii=False),
                    "related_competitor_ids": json.dumps([competitor.competitor_id for competitor in competitors], ensure_ascii=False),
                    "suggested_asset_type": asset_type,
                    "status": "open",
                    "created_at": now,
                    "updated_at": now,
                },
            )

        asset_specs = [
            ("fact_page", f"{project.brand_name} 企业事实页", "已整理品牌定位、官网来源、核心服务和公开事实，适合发布为 AI 可引用页面。", 92),
            ("service_page", f"{project.brand_name} 服务介绍页", "围绕服务能力、适用客户、交付流程和业务价值生成结构化介绍。", 88),
            ("faq", f"{project.brand_name} 高频问答 FAQ", "覆盖买家最常问的适用场景、竞品对比、实施流程和证据来源。", 86),
            ("compare", f"{project.brand_name} 竞品对比页", "把主流竞品差异、选择建议和补证方向整理成可公开对比资料。", 82),
            ("solution", f"{project.brand_name} 行业解决方案页", f"面向{project.industry}客户生成可被 AI 摘要和引用的场景方案。", 84),
            ("case_page", f"{project.brand_name} 客户案例页", "预留案例结构、价值指标和证明材料入口，方便后续补充真实案例。", 74),
            ("jsonld", f"{project.brand_name} JSON-LD 结构化数据", "生成 Organization、FAQ、Service 等结构化字段，提升 AI 理解效率。", 90),
            ("sitemap", f"{project.brand_name} sitemap.xml", "收录包页面可加入 sitemap 并提交抓取，进入发布复测闭环。", 90),
        ]
        for asset_type, title, body, progress in asset_specs:
            asset_id = f"asset_{uuid4().hex[:12]}"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_assets (
                      id, tenant_id, project_id, asset_type, title,
                      body_md, status, fact_atom_ids, target_url,
                      reviewed_by, reviewed_at, metadata_json,
                      created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :asset_type, :title,
                      :body_md, :status, :fact_atom_ids, :target_url,
                      :reviewed_by, :reviewed_at, :metadata_json,
                      :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": asset_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "asset_type": asset_type,
                    "title": title,
                    "body_md": body,
                    "status": "generated",
                    "fact_atom_ids": json.dumps(fact_ids, ensure_ascii=False),
                    "target_url": f"{project.website_url.rstrip('/')}/airank/{asset_type}",
                    "reviewed_by": "brand_check",
                    "reviewed_at": now,
                    "metadata_json": json.dumps({"progress": progress, "display_status": "已生成", "run_id": run.run_id}, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_publish_packages (
                      id, tenant_id, project_id, asset_id, package_type,
                      channel, status, package_ref_id, published_url,
                      platform_meta_json, metadata_json, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :asset_id, :package_type,
                      :channel, :status, :package_ref_id, :published_url,
                      :platform_meta_json, :metadata_json, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": f"pkg_{uuid4().hex[:12]}",
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "asset_id": asset_id,
                    "package_type": "content_asset",
                    "channel": "website",
                    "status": "packaged",
                    "package_ref_id": f"brand_check:{run.run_id}:{asset_type}",
                    "published_url": f"{project.website_url.rstrip('/')}/airank/{asset_type}",
                    "platform_meta_json": json.dumps({"asset_type": asset_type}, ensure_ascii=False),
                    "metadata_json": json.dumps({"ready_for_publish": True}, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )

        report_specs = [
            ("diagnostic", f"{project.brand_name} AI 来客诊断报告", "覆盖多 AI 平台排名、推荐率、首推率、引用来源和竞品压制点。"),
            ("executive", f"{project.brand_name} 老板报告", "用管理层可读方式汇总 AI 可见性、内容缺口和下一步发布动作。"),
            ("asset_bundle", f"{project.brand_name} 可发布资料包", "汇总企业事实页、FAQ、竞品对比页、行业解决方案页和结构化数据。"),
            ("competitor", f"{project.brand_name} 竞品压制报告", "对比主流竞品在高意向买家问题中的推荐占位和证据差距。"),
        ]
        for report_type, title, summary in report_specs:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title,
                      status, run_id, metrics_json, generated_by,
                      generated_at, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :report_type, :title,
                      :status, :run_id, :metrics_json, :generated_by,
                      :generated_at, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": f"report_{uuid4().hex[:12]}",
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "report_type": report_type,
                    "title": title,
                    "status": "可下载",
                    "run_id": run.run_id,
                    "metrics_json": json.dumps({**metrics, "summary": summary}, ensure_ascii=False),
                    "generated_by": "brand_check",
                    "generated_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def build_mysql_console_overview(tenant_id: str) -> Optional[ConsoleOverview]:
    engine = mysql_engine()
    if engine is None:
        return None

    with engine.begin() as conn:
        project_row = conn.execute(
            text(
                """
                SELECT id, brand_name, name, website_url, industry, target_audience_json, created_at
                FROM airank_projects
                WHERE tenant_id = :tenant_id
                  AND deleted_at IS NULL
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings().first()
        if project_row is None:
            return None

        competitor_rows = conn.execute(
            text(
                """
                SELECT name
                FROM airank_competitors
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND deleted_at IS NULL
                ORDER BY created_at ASC
                LIMIT 5
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_row["id"]},
        ).mappings().all()
        run_row = conn.execute(
            text(
                """
                SELECT status, metrics_json, error_message
                FROM airank_scan_runs
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND deleted_at IS NULL
                ORDER BY COALESCE(finished_at, updated_at, created_at) DESC, id DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_row["id"]},
        ).mappings().first()

    metrics = parse_json_value(run_row["metrics_json"], {}) if run_row else {}
    if not isinstance(metrics, dict):
        metrics = {}
    run_status = str(run_row["status"] or "") if run_row else ""
    run_error_message = str(run_row["error_message"] or "") if run_row else ""
    audiences = parse_json_value(project_row["target_audience_json"], [])
    audience = "、".join(audiences) if isinstance(audiences, list) and audiences else "企业品牌方 / 增长负责人"
    competitors = "、".join(row["name"] for row in competitor_rows) or "待补充竞品"
    created_at = coerce_datetime(project_row["created_at"]).date()
    scan_completed = run_status == "completed"
    task_count = int(metrics.get("task_count") or 0)
    scan_delta = "本次检测已完成" if scan_completed else "检测未完成：Provider 登录待处理"
    coverage_delta = f"{task_count} 个检测任务" if scan_completed else f"0/{task_count} 个任务完成"
    leads_delta = "基于检测结果预估" if scan_completed else "未生成，需完成真实采样"
    pressure_delta = "需补齐公开证据" if scan_completed else "外部网页登录/真人验证未完成"

    return ConsoleOverview(
        project=ProjectOverview(
            id=project_row["id"],
            name=project_row["brand_name"] or project_row["name"],
            website=project_row["website_url"],
            industry=project_row["industry"] or "企业服务",
            competitors=competitors,
            audience=audience,
            date=created_at,
        ),
        metric_cards=[
            MetricCard(
                label="AI 来客指数",
                value=str(metrics.get("ai_visibility_score", 62)),
                suffix="/100",
                delta=scan_delta,
                tone="primary",
                icon="Activity",
            ),
            MetricCard(
                label="高意向问题覆盖率",
                value=str(metrics.get("question_coverage", 41)),
                suffix="%",
                delta=coverage_delta,
                tone="primary",
                icon="Target",
            ),
            MetricCard(
                label="竞品压制问题数",
                value=str(metrics.get("competitor_pressure_count", 127)),
                suffix="",
                delta=pressure_delta,
                tone="warning",
                icon="ShieldAlert",
            ),
            MetricCard(
                label="本月 AI 来客线索",
                value=str(metrics.get("monthly_leads", 186)),
                suffix="",
                delta=leads_delta,
                tone="success",
                icon="UserRound",
            ),
        ],
    )


def find_existing_mysql_brand_project(tenant_id: str, payload: BrandCheckRequest) -> Optional[ProjectData]:
    engine = mysql_engine()
    if engine is None:
        return None

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, tenant_id, brand_name, name, website_url, industry,
                       products_services_json, target_audience_json, status,
                       created_at, updated_at
                FROM airank_projects
                WHERE tenant_id = :tenant_id
                  AND brand_name = :brand_name
                  AND website_url = :website_url
                  AND deleted_at IS NULL
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "brand_name": payload.brand_name, "website_url": payload.website_url},
        ).mappings().first()

    if row is None:
        return None

    products = parse_json_value(row["products_services_json"], ["AI visibility diagnosis"])
    audiences = parse_json_value(row["target_audience_json"], ["B2B growth leader"])
    return ProjectData(
        project_id=row["id"],
        tenant_id=row["tenant_id"],
        website_url=row["website_url"],
        brand_name=row["brand_name"] or row["name"],
        company_name=row["name"],
        industry=row["industry"] or payload.industry_hint or "unknown",
        products=products if isinstance(products, list) and products else ["AI visibility diagnosis"],
        audiences=audiences if isinstance(audiences, list) and audiences else ["B2B growth leader"],
        status=row["status"],
        automation_level="A1",
        source_refs=[
            SourceRef(
                url=row["website_url"],
                title=f"{row['brand_name'] or row['name']} website seed",
                source_type="owned",
                captured_at=coerce_datetime(row["created_at"]),
                confidence=0.6,
            )
        ],
        created_at=coerce_datetime(row["created_at"]),
        updated_at=coerce_datetime(row["updated_at"]),
    )


def list_mysql_project_competitors(tenant_id: str, project_id: str) -> list[CompetitorData]:
    engine = mysql_engine()
    if engine is None:
        return []

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, tenant_id, project_id, name, website_url, notes,
                       metadata_json, created_at, updated_at
                FROM airank_competitors
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND deleted_at IS NULL
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()

    competitors: list[CompetitorData] = []
    for row in rows:
        metadata = parse_json_value(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        competitors.append(
            CompetitorData(
                competitor_id=row["id"],
                project_id=row["project_id"],
                tenant_id=row["tenant_id"],
                name=row["name"],
                website_url=row["website_url"],
                reason=row["notes"],
                evidence_urls=metadata.get("evidence_urls") if isinstance(metadata.get("evidence_urls"), list) else [],
                confidence=float(metadata.get("confidence") or 0.8),
                status=metadata.get("status") or "confirmed",
                source=metadata.get("source") or "manual",
                created_at=coerce_datetime(row["created_at"]),
                updated_at=coerce_datetime(row["updated_at"]),
            )
        )
    return competitors


def list_mysql_project_questions(tenant_id: str, project_id: str) -> list[BuyerQuestionData]:
    engine = mysql_engine()
    if engine is None:
        return []

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, tenant_id, project_id, question_text, question_type,
                       intent, funnel_stage, source, status, metadata_json,
                       created_at, updated_at
                FROM airank_buyer_questions
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND deleted_at IS NULL
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()

    questions: list[BuyerQuestionData] = []
    for row in rows:
        metadata = parse_json_value(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        providers = metadata.get("recommended_providers")
        questions.append(
            BuyerQuestionData(
                question_id=row["id"],
                project_id=row["project_id"],
                tenant_id=row["tenant_id"],
                question_text=row["question_text"],
                question_type=row["question_type"],
                intent_level=row["intent"],
                buyer_stage=row["funnel_stage"],
                source_reason=metadata.get("source_reason"),
                recommended_providers=providers if isinstance(providers, list) else DEFAULT_PROVIDER_SCOPE,
                coverage_status=metadata.get("coverage_status") or "needs_scan",
                status=row["status"],
                source=row["source"],
                created_at=coerce_datetime(row["created_at"]),
                updated_at=coerce_datetime(row["updated_at"]),
            )
        )
    return questions


def latest_mysql_scan_run_id(tenant_id: str, project_id: str, *, status: Optional[str] = None) -> Optional[str]:
    engine = mysql_engine()
    if engine is None:
        return None

    status_clause = "AND status = :status" if status else ""
    params = {"tenant_id": tenant_id, "project_id": project_id, "status": status}
    with engine.begin() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT id
                FROM airank_scan_runs
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND deleted_at IS NULL
                  {status_clause}
                ORDER BY COALESCE(finished_at, updated_at, created_at) DESC, id DESC
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
    return str(row["id"]) if row else None


def build_brand_check_data_from_existing_project(tenant_id: str, project: ProjectData, run_id: str) -> BrandCheckData:
    completed_run = SCAN_REPOSITORY.get_run(tenant_id, run_id)
    tasks = SCAN_REPOSITORY.list_tasks(tenant_id, completed_run.run_id)
    return BrandCheckData(
        project=project,
        competitors=list_mysql_project_competitors(tenant_id, project.project_id),
        questions=list_mysql_project_questions(tenant_id, project.project_id),
        scan_run=completed_run,
        tasks=tasks,
        asset_bundle=ASSET_BUNDLE_REPOSITORY.get_bundle(tenant_id, project.project_id),
        reports=REPORT_REPOSITORY.list_reports(tenant_id, project.project_id),
        overview=build_mysql_console_overview(tenant_id)
        or ConsoleOverview(
            project=ProjectOverview(
                id=project.project_id,
                name=project.brand_name,
                website=project.website_url,
                industry=project.industry,
                competitors="、".join(competitor.name for competitor in list_mysql_project_competitors(tenant_id, project.project_id)),
                audience="、".join(project.audiences),
                date=utc_now().date(),
            ),
            metric_cards=[
                MetricCard(label="AI 来客指数", value="72", suffix="/100", delta="本次检测已完成", tone="primary", icon="Activity"),
                MetricCard(label="高意向问题覆盖率", value="68", suffix="%", delta=f"{len(tasks)} 个检测任务", tone="primary", icon="Target"),
                MetricCard(label="竞品压制问题数", value="18", suffix="", delta="需补齐公开证据", tone="warning", icon="ShieldAlert"),
                MetricCard(label="本月 AI 来客线索", value="96", suffix="", delta="基于检测结果预估", tone="success", icon="UserRound"),
            ],
        ),
    )


def run_brand_check(tenant_id: str, payload: BrandCheckRequest) -> BrandCheckData:
    industry = payload.industry_hint or "企业 AI 服务"
    existing_project = find_existing_mysql_brand_project(tenant_id, payload)
    if existing_project:
        completed_run_id = latest_mysql_scan_run_id(tenant_id, existing_project.project_id, status="completed")
        if completed_run_id:
            return build_brand_check_data_from_existing_project(tenant_id, existing_project, completed_run_id)

    assert_browser_provider_ready_for_brand_check(existing_project.project_id if existing_project else None)

    project = existing_project or PROJECT_REPOSITORY.create_project(
        tenant_id,
        ProjectCreateRequest(
            website_url=payload.website_url,
            brand_name_hint=payload.brand_name,
            company_name_hint=payload.brand_name,
            industry_hint=industry,
            competitor_hints=payload.competitor_hints,
            automation=ProjectAutomation(
                seed_from_website=True,
                discover_competitors=not payload.competitor_hints,
                generate_question_map=True,
                source="console",
            ),
        ),
    )
    competitors = list_mysql_project_competitors(tenant_id, project.project_id) if existing_project else []
    if not competitors:
        competitors = [
            PROJECT_REPOSITORY.create_competitor(tenant_id, project.project_id, competitor_payload)
            for competitor_payload in build_competitor_payloads(payload.brand_name, payload.competitor_hints)
        ]
    questions = list_mysql_project_questions(tenant_id, project.project_id) if existing_project else []
    if not questions:
        questions = [
            PROJECT_REPOSITORY.create_buyer_question(tenant_id, project.project_id, question_payload)
            for question_payload in build_question_payloads(payload.brand_name, industry, payload.buyer_questions)
        ]
    scan_run = SCAN_REPOSITORY.create_run(
        tenant_id,
        ScanRunCreateRequest(
            project_id=project.project_id,
            name=f"{payload.brand_name} 多 AI 平台基线检测",
            run_type="baseline",
            provider_scope=DEFAULT_PROVIDER_SCOPE,
            question_scope=QuestionScope(mode="selected", question_ids=[question.question_id for question in questions]),
        ),
    )

    if os.getenv("AIRANK_DATABASE_URL"):
        complete_mysql_brand_scan(tenant_id, project, competitors, questions, scan_run)
    else:
        complete_in_memory_brand_scan(tenant_id, scan_run.run_id)

    completed_run = SCAN_REPOSITORY.get_run(tenant_id, scan_run.run_id)
    tasks = SCAN_REPOSITORY.list_tasks(tenant_id, completed_run.run_id)
    asset_bundle = ASSET_BUNDLE_REPOSITORY.get_bundle(tenant_id, project.project_id)
    reports = REPORT_REPOSITORY.list_reports(tenant_id, project.project_id)
    overview = build_mysql_console_overview(tenant_id) or ConsoleOverview(
        project=ProjectOverview(
            id=project.project_id,
            name=project.brand_name,
            website=project.website_url,
            industry=project.industry,
            competitors="、".join(competitor.name for competitor in competitors),
            audience="、".join(project.audiences),
            date=utc_now().date(),
        ),
        metric_cards=[
            MetricCard(label="AI 来客指数", value="72", suffix="/100", delta="本次检测已完成", tone="primary", icon="Activity"),
            MetricCard(label="高意向问题覆盖率", value="68", suffix="%", delta=f"{len(tasks)} 个检测任务", tone="primary", icon="Target"),
            MetricCard(label="竞品压制问题数", value="18", suffix="", delta="需补齐公开证据", tone="warning", icon="ShieldAlert"),
            MetricCard(label="本月 AI 来客线索", value="96", suffix="", delta="基于检测结果预估", tone="success", icon="UserRound"),
        ],
    )
    return BrandCheckData(
        project=project,
        competitors=competitors,
        questions=questions,
        scan_run=completed_run,
        tasks=tasks,
        asset_bundle=asset_bundle,
        reports=reports,
        overview=overview,
    )


app = FastAPI(title="AIRank API", version="0.1.0")


def build_trace_id(trace_id: Optional[str]) -> str:
    if trace_id:
        return trace_id
    return f"trc_{uuid4().hex[:16]}"


def build_meta(trace_id: Optional[str]) -> ResponseMeta:
    return ResponseMeta(trace_id=build_trace_id(trace_id), request_id=f"req_{uuid4().hex[:16]}")


def get_auth_mode() -> str:
    return os.getenv("AIRANK_AUTH_MODE", "yudao").strip().lower()


def get_airank_default_tenant_id() -> str:
    return os.getenv("AIRANK_DEFAULT_TENANT_ID", "tenant_demo").strip() or "tenant_demo"


def get_auth_timeout_seconds() -> float:
    raw_timeout = os.getenv("AIRANK_AUTH_TIMEOUT_SECONDS", "5")
    try:
        timeout = float(raw_timeout)
    except ValueError:
        return 5.0
    return max(0.5, min(timeout, 30.0))


def build_yudao_url(env_name: str, path: str) -> str:
    explicit_url = os.getenv(env_name)
    if explicit_url:
        return explicit_url.rstrip("/")
    base_url = os.getenv("YUDAO_BASE_URL", "http://127.0.0.1:48080").rstrip("/")
    return f"{base_url}{path}"


def request_external_json(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    body: Optional[dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = UrlRequest(url, data=payload, headers=headers or {}, method=method)
    with urlopen(request, timeout=timeout or get_auth_timeout_seconds()) as response:
        raw_body = response.read().decode("utf-8")
    parsed = json.loads(raw_body) if raw_body else {}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def extract_yudao_token(payload: dict[str, Any]) -> Optional[str]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("accessToken") or data.get("access_token") or data.get("token")
    return token if isinstance(token, str) and token else None


def extract_yudao_expires_in(payload: dict[str, Any]) -> Optional[int]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    raw_value = data.get("expiresIn") or data.get("expires_in")
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str) and raw_value.isdigit():
        return int(raw_value)
    return None


def yudao_business_success(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    return code in (0, "0", None)


def extract_yudao_user(payload: dict[str, Any], username: str) -> AuthUser:
    data = payload.get("data")
    user = data.get("user") if isinstance(data, dict) else None
    if not isinstance(user, dict):
        return AuthUser(user_id=username, username=username, nickname=username)

    user_id = user.get("id") or user.get("userId") or user.get("user_id") or username
    user_name = user.get("username") or user.get("userName") or username
    nickname = user.get("nickname") or user.get("nickName") or user_name
    return AuthUser(user_id=str(user_id), username=str(user_name), nickname=str(nickname))


def build_dev_only_auth_response(payload: AuthLoginRequest, trace_id: Optional[str]) -> AuthLoginResponse:
    return AuthLoginResponse(
        data=AuthLoginData(
            access_token=f"dev_only_{uuid4().hex}",
            token_type="Bearer",
            expires_in=3600,
            tenant_id=get_airank_default_tenant_id(),
            yudao_tenant_id=payload.yudao_tenant_id,
            user=AuthUser(user_id=payload.username, username=payload.username, nickname=payload.username),
            dev_only=True,
        ),
        meta=build_meta(trace_id),
    )


def yudao_login(payload: AuthLoginRequest, trace_id: Optional[str]) -> AuthLoginResponse:
    login_url = build_yudao_url("YUDAO_LOGIN_URL", "/admin-api/system/auth/login")
    permission_url = build_yudao_url("YUDAO_PERMISSION_INFO_URL", "/admin-api/system/auth/get-permission-info")
    headers = {"Content-Type": "application/json", "tenant-id": payload.yudao_tenant_id}

    try:
        login_payload = request_external_json(
            login_url,
            method="POST",
            headers=headers,
            body={"username": payload.username, "password": payload.password},
        )
    except HTTPError as exc:
        if exc.code in {400, 401, 403}:
            raise StarletteHTTPException(
                status_code=401,
                detail={"code": "AUTH_LOGIN_FAILED", "details": {"source": "yudao"}},
            ) from exc
        raise StarletteHTTPException(
            status_code=503,
            detail={"code": "AUTH_YUDAO_UNAVAILABLE", "details": {"stage": "login"}},
        ) from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise StarletteHTTPException(
            status_code=503,
            detail={"code": "AUTH_YUDAO_UNAVAILABLE", "details": {"stage": "login"}},
        ) from exc

    token = extract_yudao_token(login_payload)
    if not yudao_business_success(login_payload) or token is None:
        raise StarletteHTTPException(
            status_code=401,
            detail={"code": "AUTH_LOGIN_FAILED", "details": {"source": "yudao"}},
        )

    try:
        permission_payload = request_external_json(
            permission_url,
            headers={"Authorization": f"Bearer {token}", "tenant-id": payload.yudao_tenant_id},
        )
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise StarletteHTTPException(
            status_code=503,
            detail={"code": "AUTH_YUDAO_UNAVAILABLE", "details": {"stage": "permission_info"}},
        ) from exc

    if not yudao_business_success(permission_payload):
        raise StarletteHTTPException(
            status_code=401,
            detail={"code": "AUTH_TOKEN_INVALID", "details": {"source": "yudao"}},
        )

    return AuthLoginResponse(
        data=AuthLoginData(
            access_token=token,
            token_type="Bearer",
            expires_in=extract_yudao_expires_in(login_payload),
            tenant_id=get_airank_default_tenant_id(),
            yudao_tenant_id=payload.yudao_tenant_id,
            user=extract_yudao_user(permission_payload, payload.username),
            dev_only=False,
        ),
        meta=build_meta(trace_id),
    )


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


@app.get(
    f"{API_PREFIX}/provider-readiness",
    response_model=ProviderReadinessResponse,
    response_model_exclude_none=True,
)
def get_provider_readiness(trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> ProviderReadinessResponse:
    return ProviderReadinessResponse(
        data=ProviderReadinessData(
            mode=provider_execution_mode(),  # type: ignore[arg-type]
            minimum_success_count=minimum_provider_success_count(DEFAULT_PROVIDER_SCOPE),
            providers=build_provider_readiness_items(DEFAULT_PROVIDER_SCOPE),
        ),
        meta=build_meta(trace_id),
    )


@app.post(
    f"{API_PREFIX}/auth/login",
    response_model=AuthLoginResponse,
)
def login(payload: AuthLoginRequest, trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> AuthLoginResponse:
    if get_auth_mode() in {"dev", "dev_only", "development"}:
        return build_dev_only_auth_response(payload, trace_id)
    return yudao_login(payload, trace_id)


@app.post(
    f"{API_PREFIX}/brand-checks",
    response_model=BrandCheckResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_brand_check(
    payload: BrandCheckRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> BrandCheckResponse:
    return BrandCheckResponse(data=run_brand_check(tenant_id, payload), meta=build_meta(trace_id))


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
    project_id: ProjectIdPath,
    fact_id: FactIdPath,
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
    project_id: ProjectIdPath,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> AssetBundleResponse:
    return AssetBundleResponse(data=ASSET_BUNDLE_REPOSITORY.get_bundle(tenant_id, project_id), meta=build_meta(trace_id))


@app.get(
    f"{API_PREFIX}/projects/{{project_id}}/reports",
    response_model=ReportListResponse,
)
def get_reports(
    project_id: ProjectIdPath,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ReportListResponse:
    return ReportListResponse(data=REPORT_REPOSITORY.list_reports(tenant_id, project_id), meta=build_meta(trace_id))


@app.post(
    f"{API_PREFIX}/reports/{{report_id}}/download-receipts",
    response_model=DownloadReceiptResponse,
    status_code=201,
)
def create_download_receipt(
    report_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> DownloadReceiptResponse:
    meta = build_meta(trace_id)
    return DownloadReceiptResponse(
        data=REPORT_REPOSITORY.record_download_receipt(tenant_id, report_id, meta.trace_id),
        meta=meta,
    )


@app.post(
    f"{API_PREFIX}/console/actions",
    response_model=ConsoleActionResponse,
    status_code=201,
)
def record_console_action(
    payload: ConsoleActionRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    actor_user_id: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> ConsoleActionResponse:
    meta = build_meta(trace_id)
    return ConsoleActionResponse(
        data=CONSOLE_ACTION_REPOSITORY.record_action(tenant_id, payload, meta.trace_id, actor_user_id),
        meta=meta,
    )


@app.get(f"{API_PREFIX}/console/overview", response_model=ConsoleOverviewResponse)
def get_console_overview(
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ConsoleOverviewResponse:
    """Return the first dashboard contract shape without touching worker scheduling."""

    mysql_overview = build_mysql_console_overview(tenant_id)
    if mysql_overview is not None:
        return ConsoleOverviewResponse(data=mysql_overview, meta=build_meta(trace_id))

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

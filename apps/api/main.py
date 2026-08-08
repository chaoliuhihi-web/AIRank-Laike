from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import json
import os
import threading
from typing import Annotated, Any, Callable, Literal, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from fastapi import FastAPI, Header, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from jsonschema import Draft202012Validator, ValidationError as JsonSchemaValidationError
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool

from airank_domain import govern_question
from airank_domain.measurement import PromptCohortType, sha256_text, stable_prompt_version_id
from airank_evidence import ObjectStorageError, StoredObject, build_object_storage_from_env
from airank_score import QUALITY_CONTRACT_VERSION
from airank_skills import build_promotion_ledger, evaluate_registry, load_default_registry, run_skill

try:
    from .provider_scan import (
        ProviderCallError,
        ProviderScanResult,
        ProviderUnavailable,
        call_api_provider_for_brand_rank,
        call_provider_for_brand_rank,
        classify_provider_call_failure,
        probe_provider_readiness,
        provider_execution_mode,
    )
except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
    from provider_scan import (  # type: ignore[no-redef]
        ProviderCallError,
        ProviderScanResult,
        ProviderUnavailable,
        call_api_provider_for_brand_rank,
        call_provider_for_brand_rank,
        classify_provider_call_failure,
        probe_provider_readiness,
        provider_execution_mode,
    )

API_PREFIX = "/api/v1"
API_VERSION = "v1"
SERVICE_NAME = "airank-api"
TRACE_HEADER = "X-AIRank-Trace-Id"
_DEV_AUTH_SESSIONS: dict[str, dict[str, Any]] = {}
_DEV_AUTH_SESSIONS_LOCK = threading.Lock()

ERROR_REGISTRY: dict[str, tuple[int, str]] = {
    "BAD_REQUEST": (400, "Bad request"),
    "VALIDATION_FAILED": (422, "Invalid request"),
    "RESOURCE_NOT_FOUND": (404, "Resource not found"),
    "METHOD_NOT_ALLOWED": (405, "Method not allowed"),
    "STATE_CONFLICT": (409, "State conflict"),
    "IDEMPOTENCY_CONFLICT": (409, "Idempotency key payload conflict"),
    "RATE_LIMITED": (429, "Rate limited"),
    "INTERNAL_ERROR": (500, "Internal server error"),
    "AUTH_TOKEN_MISSING": (401, "Authentication token is missing"),
    "AUTH_TOKEN_INVALID": (401, "Authentication token is invalid"),
    "AUTH_LOGIN_FAILED": (401, "Login credentials are invalid"),
    "AUTH_YUDAO_UNAVAILABLE": (503, "Yudao authentication is unavailable"),
    "AUTH_PERMISSION_FORBIDDEN": (403, "Required permission is missing"),
    "TENANT_MISMATCH": (403, "Tenant does not match the token"),
    "TENANT_FORBIDDEN": (403, "Tenant access is forbidden"),
    "PROJECT_NOT_FOUND": (404, "Project not found"),
    "PROJECT_ARCHIVED": (409, "Project is archived"),
    "QUESTION_NOT_FOUND": (404, "Question not found"),
    "QUESTION_LIMIT_EXCEEDED": (400, "Question limit exceeded"),
    "SCAN_RUN_NOT_FOUND": (404, "Scan run not found"),
    "SCAN_RUN_ALREADY_RUNNING": (409, "Scan run is already running"),
    "SCAN_RUN_LEASE_EXPIRED": (500, "Scan worker lease expired"),
    "SCAN_TASK_LEASE_EXPIRED": (500, "Scan task worker lease expired"),
    "SCAN_RUN_CANCELED": (409, "Scan run was canceled"),
    "SCAN_TASK_NOT_FOUND": (404, "Scan task not found"),
    "SCAN_JOB_INVALID": (500, "Scan job payload is invalid"),
    "SCAN_JOB_SCOPE_MISMATCH": (409, "Scan job scope does not match its run"),
    "SCAN_WORKER_INTERNAL_ERROR": (500, "Scan worker failed internally"),
    "SCAN_PROVIDER_TIMEOUT": (502, "Scan provider timed out"),
    "SCAN_PROVIDER_FAILED": (502, "Scan provider failed"),
    "SCAN_PROVIDER_BLOCKED": (502, "Scan provider is blocked"),
    "JOB_NOT_FOUND": (404, "Job not found"),
    "JOB_TIMEOUT": (500, "Job timed out"),
    "JOB_MAX_ATTEMPTS_EXCEEDED": (500, "Job exceeded max attempts"),
    "FACT_NOT_FOUND": (404, "FactAtom not found"),
    "FACT_REVISION_NOT_FOUND": (404, "FactRevision not found"),
    "FACT_CONFLICT_NOT_FOUND": (404, "FactConflict not found"),
    "FACT_CONFLICT_OPEN": (409, "Fact has an open conflict"),
    "FACT_SOURCE_STALE": (409, "Fact source is stale or expired"),
    "KNOWLEDGE_SOURCE_NOT_FOUND": (404, "KnowledgeSource not found"),
    "CONTENT_EVIDENCE_MISSING": (409, "Content evidence is missing or ineligible"),
    "CONTENT_REVIEW_REQUIRED": (409, "Content review is required"),
    "CONTENT_RISK_OVERRIDE_REQUIRED": (409, "High-risk content requires an audited override"),
    "PUBLISH_PACKAGE_NOT_FOUND": (404, "Publish package not found"),
    "RETEST_WINDOW_NOT_FOUND": (404, "Retest observation window not found"),
    "RETEST_BASELINE_REQUIRED": (409, "A completed baseline run is required"),
    "RETEST_COMPARE_RUN_REQUIRED": (409, "A completed comparable scan run is required"),
    "FACT_SOURCE_REQUIRED": (400, "Fact source is required"),
    "FACT_DISCLOSURE_FORBIDDEN": (403, "Fact disclosure is forbidden"),
    "ASSET_NOT_FOUND": (404, "Asset not found"),
    "ASSET_REVIEW_REQUIRED": (409, "Asset review is required"),
    "REPORT_NOT_FOUND": (404, "Report not found"),
    "REPORT_QUALITY_BLOCKED": (409, "Report did not pass the measurement quality gate"),
    "REPORT_EVIDENCE_MISSING": (500, "Report evidence is missing"),
    "PAGE_AUDIT_URL_REQUIRED": (400, "Page audit URL is required"),
    "PAGE_AUDIT_URL_INVALID": (400, "Page audit URL is invalid"),
    "PAGE_AUDIT_NOT_FOUND": (404, "Page audit run not found"),
    "CITATION_NOT_FOUND": (404, "Citation not found"),
    "CITATION_CLAIM_NOT_FOUND": (404, "Citation claim not found"),
    "CITATION_SUPPORT_EVIDENCE_INVALID": (409, "Citation support evidence is invalid"),
    "SKILL_NOT_FOUND": (404, "Skill not found"),
    "OBJECT_REF_NOT_FOUND": (404, "Object reference not found"),
    "EVIDENCE_OBJECT_UNAVAILABLE": (503, "Evidence object is unavailable"),
    "EVIDENCE_INTEGRITY_FAILED": (409, "Evidence object integrity verification failed"),
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
    metric_cards: list[MetricCard] = Field(default_factory=list, alias="metric_cards")
    data_status: Literal["empty", "collecting", "provider_evidence", "unverified"] = "empty"
    message: str = ""


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
        Literal["chatgpt", "deepseek", "kimi", "qianwen", "tongyi", "doubao", "baidu_ai_search", "yuanbao", "manual_import"]
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
    question_version_id: Optional[str] = None
    taxonomy_version: str = "legacy_unclassified"
    dedupe_sha256: Optional[str] = None
    prompt_style: Literal["exploratory", "comparative", "factual", "procedural", "evaluative"] = "exploratory"
    temporal_scope: Literal["evergreen", "current", "historical"] = "evergreen"
    scenario: Literal["generic", "b2b_procurement", "local_selection", "replacement", "risk_validation"] = "generic"
    region: Optional[str] = None
    cohort_type: Literal["blind", "assisted", "comparison", "fact_verification", "unclassified"] = "unclassified"
    source_kind: Literal["provided_seed", "template_candidate", "observed_query", "imported"] = "imported"
    source_ref: str = "legacy-row"
    evidence_level: Literal["provided_seed", "template_candidate", "observed_query", "imported"] = "imported"
    observed_query: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BuyerQuestionResponse(BaseModel):
    data: BuyerQuestionData
    meta: ResponseMeta


class BuyerQuestionListResponse(BaseModel):
    data: list[BuyerQuestionData]
    meta: ResponseMeta


Provider = Literal["chatgpt", "deepseek", "kimi", "qianwen", "tongyi", "doubao", "baidu_ai_search", "yuanbao", "manual_import"]
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
    cohort_type: Literal["blind", "assisted", "comparison", "fact_verification"] = "blind"
    repetitions: int = Field(default=3, ge=1, le=20)
    collector_surfaces: list[Literal["api", "web", "app", "manual_import"]] = Field(
        default_factory=lambda: ["web"], min_length=1, max_length=4
    )
    provider_scope: list[Provider] = Field(min_length=1, max_length=8)
    question_scope: QuestionScope

    @field_validator("provider_scope")
    @classmethod
    def provider_scope_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("provider_scope", value)

    @field_validator("collector_surfaces")
    @classmethod
    def collector_surfaces_must_be_unique(cls, value: list[str]) -> list[str]:
        return require_unique_values("collector_surfaces", value)


class ScanError(BaseModel):
    code: str
    message: str


class ScanRunData(BaseModel):
    run_id: str
    tenant_id: str
    project_id: str
    name: Optional[str] = None
    run_type: Literal["baseline", "retest", "manual"]
    cohort_type: Literal["blind", "assisted", "comparison", "fact_verification"] = "blind"
    repetitions: int = Field(default=3, ge=1, le=20)
    collector_surfaces: list[Literal["api", "web", "app", "manual_import"]] = Field(default_factory=lambda: ["web"])
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
    cohort_type: Literal["blind", "assisted", "comparison", "fact_verification"] = "blind"
    prompt_version_id: str = "prompt_v_legacy"
    sample_index: int = Field(default=1, ge=1)
    session_id: str = "session_legacy"
    collector_surface: Literal["api", "web", "app", "manual_import"] = "web"
    evidence_level: Literal["provider_api", "consumer_web", "consumer_app", "manual_import"] = "consumer_web"
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


class ScanRunListResponse(BaseModel):
    data: list[ScanRunData]
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
    assets: list[AssetBundleItem] = Field(default_factory=list)


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


class SkillManifestData(BaseModel):
    skill_id: str
    version: str
    category: Literal["measurement", "research", "knowledge", "intervention", "governance", "delivery"]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    dependencies: list[str]
    provider_requirements: list[str]
    evidence_level: list[str]
    fact_policy: dict[str, Any]
    failure_policy: dict[str, Any]
    quality_rubric: list[dict[str, Any]]
    eval_cases: list[dict[str, Any]]
    promotion_policy: dict[str, Any]
    evaluation: "SkillEvaluationSummaryData"
    status: Literal["ready", "partial", "blocked", "disabled", "dev_only"]
    entrypoint: str


class SkillRegistryData(BaseModel):
    skills: list[SkillManifestData]


class SkillEvaluationSummaryData(BaseModel):
    local_eval_status: Literal["passed", "failed"]
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    executed_suites: list[Literal["contract", "holdout", "adversarial"]]
    promotion_eligible: bool
    promotion_blockers: list[str]
    evaluation_sha256: str


class SkillRegistryResponse(BaseModel):
    data: SkillRegistryData
    meta: ResponseMeta


class SkillEvalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any]


class SkillEvalData(BaseModel):
    skill_id: str
    version: str
    manifest_status: Literal["ready", "partial", "blocked", "disabled", "dev_only"]
    output: dict[str, Any]


class SkillEvalResponse(BaseModel):
    data: SkillEvalData
    meta: ResponseMeta


class SkillPromotionLedgerResponse(BaseModel):
    data: dict[str, Any]
    meta: ResponseMeta


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
            "provider_not_configured",
            "provider_disabled",
            "provider_auth_failed",
            "provider_model_failed",
            "provider_generation_failed",
            "provider_circuit_open",
        ]
    ] = None
    reason: Optional[str] = None
    screenshot_path: Optional[str] = None


class ProviderReadinessData(BaseModel):
    mode: Literal["api", "browser", "mock"]
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

    def list_buyer_questions(self, tenant_id: str, project_id: str) -> list[BuyerQuestionData]:
        ...


class ScanRepository(Protocol):
    def create_run(self, tenant_id: str, payload: ScanRunCreateRequest) -> ScanRunData:
        ...

    def get_run(self, tenant_id: str, run_id: str) -> ScanRunData:
        ...

    def list_runs(self, tenant_id: str, project_id: str) -> list[ScanRunData]:
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
        project = self._ensure_project(tenant_id, project_id)
        now = utc_now()
        source_kind = "imported" if payload.source == "imported" else "template_candidate" if payload.source == "hermes_generated" else "provided_seed"
        competitor_names = tuple(
            value.name
            for (item_tenant, _), value in self._competitors.items()
            if item_tenant == tenant_id and value.project_id == project_id and value.status != "rejected"
        )
        governed = govern_question(
            payload.question_text,
            target_names=tuple(value for value in (project.brand_name, project.company_name) if value),
            competitor_names=competitor_names,
            source_kind=source_kind,
            source_ref=payload.source_reason or payload.source,
        )
        duplicate = next((
            value for (item_tenant, _), value in self._questions.items()
            if item_tenant == tenant_id and value.project_id == project_id and value.dedupe_sha256 == governed.dedupe_sha256 and value.status != "archived"
        ), None)
        if duplicate is not None:
            raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"duplicate_question_id": duplicate.question_id}})
        data = BuyerQuestionData(
            question_id=f"question_{uuid4().hex[:12]}",
            project_id=project_id,
            tenant_id=tenant_id,
            question_text=governed.question_text,
            question_type=governed.question_type,
            intent_level=governed.intent_level,
            buyer_stage=governed.buyer_stage,
            source_reason=payload.source_reason,
            recommended_providers=payload.recommended_providers,
            coverage_status="needs_scan",
            status=payload.status,
            source=payload.source,
            question_version_id=governed.question_version_id,
            taxonomy_version=governed.taxonomy_version,
            dedupe_sha256=governed.dedupe_sha256,
            prompt_style=governed.prompt_style,
            temporal_scope=governed.temporal_scope,
            scenario=governed.scenario,
            region=governed.region,
            cohort_type=governed.cohort_type,
            source_kind=governed.source_kind,
            source_ref=governed.source_ref,
            evidence_level=governed.evidence_level,
            observed_query=governed.observed_query,
            created_at=now,
            updated_at=now,
        )
        self._questions[(tenant_id, data.question_id)] = data
        return data

    def list_buyer_questions(self, tenant_id: str, project_id: str) -> list[BuyerQuestionData]:
        self._ensure_project(tenant_id, project_id)
        return [
            question
            for (item_tenant, _), question in self._questions.items()
            if item_tenant == tenant_id and question.project_id == project_id
        ]


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
        source_kind = "imported" if payload.source == "imported" else "template_candidate" if payload.source == "hermes_generated" else "provided_seed"
        with self._engine.begin() as conn:
            project_row = conn.execute(text("""
                SELECT brand_name, name FROM airank_projects
                WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
                FOR UPDATE
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().first()
            if project_row is None:
                raise StarletteHTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id, "repository": "mysql"}})
            competitor_names = tuple(conn.execute(text("""
                SELECT name FROM airank_competitors
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND deleted_at IS NULL
                ORDER BY created_at ASC, id ASC
            """), {"tenant_id": tenant_id, "project_id": project_id}).scalars().all())
            governed = govern_question(
                payload.question_text,
                target_names=tuple(value for value in (project_row["brand_name"], project_row["name"]) if value),
                competitor_names=competitor_names,
                source_kind=source_kind,
                source_ref=payload.source_reason or payload.source,
            )
            duplicate = conn.execute(text("""
                SELECT id FROM airank_buyer_questions
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND dedupe_sha256=:dedupe_sha256 AND status<>'archived' AND deleted_at IS NULL
                LIMIT 1
            """), {"tenant_id": tenant_id, "project_id": project_id, "dedupe_sha256": governed.dedupe_sha256}).scalar()
            if duplicate:
                raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"duplicate_question_id": duplicate}})
            data = BuyerQuestionData(
                question_id=f"question_{uuid4().hex[:12]}",
                project_id=project_id,
                tenant_id=tenant_id,
                question_text=governed.question_text,
                question_type=governed.question_type,
                intent_level=governed.intent_level,
                buyer_stage=governed.buyer_stage,
                source_reason=payload.source_reason,
                recommended_providers=payload.recommended_providers,
                coverage_status="needs_scan",
                status=payload.status,
                source=payload.source,
                question_version_id=governed.question_version_id,
                taxonomy_version=governed.taxonomy_version,
                dedupe_sha256=governed.dedupe_sha256,
                prompt_style=governed.prompt_style,
                temporal_scope=governed.temporal_scope,
                scenario=governed.scenario,
                region=governed.region,
                cohort_type=governed.cohort_type,
                source_kind=governed.source_kind,
                source_ref=governed.source_ref,
                evidence_level=governed.evidence_level,
                observed_query=governed.observed_query,
                created_at=now,
                updated_at=now,
            )
            metadata = {
                "source_reason": data.source_reason,
                "recommended_providers": data.recommended_providers,
                "coverage_status": data.coverage_status,
                "question_version_id": data.question_version_id,
                "taxonomy_version": data.taxonomy_version,
                "cohort_type": data.cohort_type,
                "source_kind": data.source_kind,
                "source_ref": data.source_ref,
                "observed_query": data.observed_query,
            }
            revision_id = f"qrev_{uuid4().hex[:20]}"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_buyer_questions (
                      id, tenant_id, project_id, current_revision_id, taxonomy_version,
                      dedupe_sha256, question_text, question_type, intent, funnel_stage,
                      source, status, metadata_json,
                      created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, NULL, :taxonomy_version,
                      :dedupe_sha256, :question_text, :question_type,
                      :intent, :funnel_stage, :source, :status, :metadata_json,
                      :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": data.question_id,
                    "tenant_id": data.tenant_id,
                    "project_id": data.project_id,
                    "taxonomy_version": data.taxonomy_version,
                    "dedupe_sha256": data.dedupe_sha256,
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
            conn.execute(text("""
                INSERT INTO airank_buyer_question_revisions (
                  id, tenant_id, project_id, question_id, question_map_id, revision_number,
                  question_version_id, taxonomy_version, question_text, dedupe_sha256,
                  question_type, intent, funnel_stage, prompt_style, temporal_scope,
                  scenario, region, cohort_type, source_kind, source_ref, evidence_level,
                  observed_query, provenance_json, status, created_by, created_at
                ) VALUES (
                  :revision_id, :tenant_id, :project_id, :question_id, NULL, 1,
                  :question_version_id, :taxonomy_version, :question_text, :dedupe_sha256,
                  :question_type, :intent, :funnel_stage, :prompt_style, :temporal_scope,
                  :scenario, :region, :cohort_type, :source_kind, :source_ref, :evidence_level,
                  :observed_query, :provenance_json, :status, 'api', :created_at
                )
            """), {
                "revision_id": revision_id, "tenant_id": tenant_id, "project_id": project_id,
                "question_id": data.question_id, "question_version_id": data.question_version_id,
                "taxonomy_version": data.taxonomy_version, "question_text": data.question_text,
                "dedupe_sha256": data.dedupe_sha256, "question_type": data.question_type,
                "intent": data.intent_level, "funnel_stage": data.buyer_stage,
                "prompt_style": data.prompt_style, "temporal_scope": data.temporal_scope,
                "scenario": data.scenario, "region": data.region, "cohort_type": data.cohort_type,
                "source_kind": data.source_kind, "source_ref": data.source_ref,
                "evidence_level": data.evidence_level, "observed_query": data.observed_query,
                "provenance_json": json.dumps({"source_reason": data.source_reason, "source": data.source}, ensure_ascii=False),
                "status": data.status, "created_at": now,
            })
            conn.execute(text("UPDATE airank_buyer_questions SET current_revision_id=:revision_id WHERE tenant_id=:tenant_id AND id=:question_id"), {"revision_id": revision_id, "tenant_id": tenant_id, "question_id": data.question_id})
        return data

    def list_buyer_questions(self, tenant_id: str, project_id: str) -> list[BuyerQuestionData]:
        return list_mysql_project_questions(tenant_id, project_id)


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
        task_count = len(payload.provider_scope) * len(question_ids) * len(payload.collector_surfaces) * payload.repetitions
        data = ScanRunData(
            run_id=run_id,
            tenant_id=tenant_id,
            project_id=payload.project_id,
            name=payload.name,
            run_type=payload.run_type,
            cohort_type=payload.cohort_type,
            repetitions=payload.repetitions,
            collector_surfaces=payload.collector_surfaces,
            status="queued",
            provider_scope=payload.provider_scope,
            question_scope=question_scope,
            metrics={"task_count": task_count},
            created_at=now,
            updated_at=now,
        )
        self._runs[(tenant_id, run_id)] = data

        evidence_levels = {"api": "provider_api", "web": "consumer_web", "app": "consumer_app", "manual_import": "manual_import"}
        for provider in payload.provider_scope:
            for question_id in question_ids:
                prompt_version_id = stable_prompt_version_id(
                    cohort_type=PromptCohortType(payload.cohort_type),
                    prompt_text=question_id,
                )
                for collector_surface in payload.collector_surfaces:
                    for sample_index in range(1, payload.repetitions + 1):
                        task = ScanTaskData(
                            task_id=f"scan_task_{uuid4().hex[:12]}",
                            run_id=run_id,
                            tenant_id=tenant_id,
                            project_id=payload.project_id,
                            question_id=question_id,
                            provider=provider,
                            cohort_type=payload.cohort_type,
                            prompt_version_id=prompt_version_id,
                            sample_index=sample_index,
                            session_id=f"session_{uuid4().hex}",
                            collector_surface=collector_surface,
                            evidence_level=evidence_levels[collector_surface],  # type: ignore[arg-type]
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

    def list_runs(self, tenant_id: str, project_id: str) -> list[ScanRunData]:
        return sorted(
            [
                run
                for (item_tenant, _), run in self._runs.items()
                if item_tenant == tenant_id and run.project_id == project_id
            ],
            key=lambda run: run.created_at,
            reverse=True,
        )

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

    def _resolve_questions(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        scope: QuestionScope,
        cohort_type: str,
    ) -> list[dict[str, str]]:
        rows = conn.execute(
            text(
                """
                SELECT q.id, q.question_text, q.status,
                       r.cohort_type, r.question_version_id, r.taxonomy_version
                FROM airank_buyer_questions q
                LEFT JOIN airank_buyer_question_revisions r
                  ON r.id = q.current_revision_id
                WHERE q.tenant_id = :tenant_id
                  AND q.project_id = :project_id
                  AND q.deleted_at IS NULL
                ORDER BY q.priority ASC, q.created_at ASC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        active_questions = [
            {
                "id": row["id"],
                "question_text": row["question_text"],
                "question_version_id": row["question_version_id"],
                "taxonomy_version": row["taxonomy_version"],
            }
            for row in rows
            if row["status"] == "confirmed" and row["cohort_type"] == cohort_type
        ]

        if scope.mode == "all_active":
            if not active_questions:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={
                        "code": "QUESTION_NOT_FOUND",
                        "details": {"project_id": project_id, "scope": "all_active", "required_cohort_type": cohort_type},
                    },
                )
            return active_questions

        questions_by_id = {question["id"]: question for question in active_questions}
        active_id_set = set(questions_by_id)
        missing = [question_id for question_id in scope.question_ids if question_id not in active_id_set]
        if missing:
            raise StarletteHTTPException(
                status_code=404,
                detail={
                    "code": "QUESTION_NOT_FOUND",
                    "details": {
                        "project_id": project_id,
                        "question_ids": missing,
                        "required_status": "confirmed",
                        "required_cohort_type": cohort_type,
                    },
                },
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
            cohort_type=row["cohort_type"],
            repetitions=row["repetitions"],
            collector_surfaces=parse_json_value(row["collector_surfaces_json"], ["web"]),
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
            cohort_type=row["cohort_type"],
            prompt_version_id=row["prompt_version_id"],
            sample_index=row["sample_index"],
            session_id=row["session_id"],
            collector_surface=row["collector_surface"],
            evidence_level=row["evidence_level"],
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
            questions = self._resolve_questions(
                conn,
                tenant_id,
                payload.project_id,
                payload.question_scope,
                payload.cohort_type,
            )
            question_ids = [question["id"] for question in questions]
            question_scope = QuestionScope(mode=payload.question_scope.mode, question_ids=question_ids)
            task_count = len(payload.provider_scope) * len(question_ids) * len(payload.collector_surfaces) * payload.repetitions
            metrics = {"task_count": task_count}
            conn.execute(
                text(
                    """
                    INSERT INTO airank_scan_runs (
                      id, tenant_id, project_id, name, run_type, status,
                      cohort_type, repetitions, collector_surfaces_json,
                      provider_scope_json, question_scope_json, metrics_json,
                      created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :name, :run_type, :status,
                      :cohort_type, :repetitions, :collector_surfaces_json,
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
                    "cohort_type": payload.cohort_type,
                    "repetitions": payload.repetitions,
                    "collector_surfaces_json": json.dumps(payload.collector_surfaces, ensure_ascii=False),
                    "provider_scope_json": json.dumps(payload.provider_scope, ensure_ascii=False),
                    "question_scope_json": json.dumps(question_scope.model_dump(mode="json"), ensure_ascii=False),
                    "metrics_json": json.dumps(metrics, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            evidence_levels = {"api": "provider_api", "web": "consumer_web", "app": "consumer_app", "manual_import": "manual_import"}
            for provider in payload.provider_scope:
                for question in questions:
                    prompt_version_id = stable_prompt_version_id(
                        cohort_type=PromptCohortType(payload.cohort_type),
                        prompt_text=question["question_text"],
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_prompt_versions (
                              id, tenant_id, project_id, question_id, cohort_type,
                              template_version, prompt_text, prompt_sha256, created_at
                            )
                            SELECT :id, :tenant_id, :project_id, :question_id, :cohort_type,
                                   :template_version, :prompt_text, :prompt_sha256, :created_at
                            WHERE NOT EXISTS (
                              SELECT 1 FROM airank_prompt_versions
                              WHERE tenant_id = :tenant_id AND id = :id
                            )
                            """
                        ),
                        {
                            "id": prompt_version_id,
                            "tenant_id": tenant_id,
                            "project_id": payload.project_id,
                            "question_id": question["id"],
                            "cohort_type": payload.cohort_type,
                            "template_version": question["question_version_id"] or "legacy_unclassified",
                            "prompt_text": question["question_text"],
                            "prompt_sha256": sha256_text(question["question_text"].strip()),
                            "created_at": now,
                        },
                    )
                    for collector_surface in payload.collector_surfaces:
                        for sample_index in range(1, payload.repetitions + 1):
                            task_id = f"scan_task_{uuid4().hex[:12]}"
                            job_id = f"job_{uuid4().hex[:12]}"
                            session_id = f"session_{uuid4().hex}"
                            request_payload = {
                                "run_id": run_id,
                                "scan_task_id": task_id,
                                "question_id": question["id"],
                                "question_text": question["question_text"],
                                "question_version_id": question["question_version_id"],
                                "taxonomy_version": question["taxonomy_version"],
                                "provider": provider,
                                "cohort_type": payload.cohort_type,
                                "prompt_version_id": prompt_version_id,
                                "sample_index": sample_index,
                                "session_id": session_id,
                                "collector_surface": collector_surface,
                                "evidence_level": evidence_levels[collector_surface],
                            }
                            conn.execute(
                                text(
                                    """
                                    INSERT INTO airank_scan_tasks (
                                      id, tenant_id, project_id, run_id, question_id, provider,
                                      cohort_type, prompt_version_id, sample_index, session_id,
                                      collector_surface, evidence_level, status, attempt_count,
                                      scheduled_at, request_json, created_at, updated_at
                                    )
                                    VALUES (
                                      :id, :tenant_id, :project_id, :run_id, :question_id, :provider,
                                      :cohort_type, :prompt_version_id, :sample_index, :session_id,
                                      :collector_surface, :evidence_level, :status, :attempt_count,
                                      :scheduled_at, :request_json, :created_at, :updated_at
                                    )
                                    """
                                ),
                                {
                                    **request_payload,
                                    "id": task_id,
                                    "tenant_id": tenant_id,
                                    "project_id": payload.project_id,
                                    "status": "queued",
                                    "attempt_count": 0,
                                    "scheduled_at": now,
                                    "request_json": json.dumps(request_payload, ensure_ascii=False),
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
                                    "payload_json": json.dumps(request_payload, ensure_ascii=False),
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

    def list_runs(self, tenant_id: str, project_id: str) -> list[ScanRunData]:
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_scan_runs
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND deleted_at IS NULL
                    ORDER BY created_at DESC, id DESC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        return [self._row_to_run(row) for row in rows]

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
    """Explicit empty state when persistent content evidence is unavailable."""

    def get_bundle(self, tenant_id: str, project_id: str) -> AssetBundleData:
        return AssetBundleData(
            project_id=project_id,
            tenant_id=tenant_id,
            completeness=0,
            recommendation="尚无经过事实审核的内容资产，不生成完成度或发布建议。",
            assets=[],
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
        completeness = round(sum(asset.progress for asset in assets) / len(assets)) if assets else 0
        open_gap_count = len(gap_rows)
        if open_gap_count:
            recommendation = f"优先补齐 {open_gap_count} 个内容缺口，再发布 AI 收录包。"
        elif not assets:
            recommendation = "尚无经过事实审核的内容资产，不生成完成度或发布建议。"
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
    """Explicit empty state when no evidence-backed report has been generated."""

    def list_reports(self, tenant_id: str, project_id: str) -> ReportListData:
        return ReportListData(
            project_id=project_id,
            tenant_id=tenant_id,
            reports=[],
        )

    def record_download_receipt(self, tenant_id: str, report_id: str, _trace_id: str) -> DownloadReceiptData:
        raise StarletteHTTPException(
            status_code=404,
            detail={"code": "REPORT_NOT_FOUND", "details": {"report_id": report_id, "repository": "empty"}},
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

    @staticmethod
    def _quality_publishable(metrics: Any) -> bool:
        return (
            isinstance(metrics, dict)
            and metrics.get("report_status") == "generated"
            and isinstance(metrics.get("baseline_quality"), dict)
            and metrics["baseline_quality"].get("contract_version") == QUALITY_CONTRACT_VERSION
            and metrics["baseline_quality"].get("publishable") is True
            and isinstance(metrics.get("compare_quality"), dict)
            and metrics["compare_quality"].get("contract_version") == QUALITY_CONTRACT_VERSION
            and metrics["compare_quality"].get("publishable") is True
        )

    def _effective_status(self, row: Any) -> str:
        if row["status"] != "generated":
            return row["status"]
        metrics = parse_json_value(row["metrics_json"], {})
        return "generated" if self._quality_publishable(metrics) else "quality_blocked"

    def _report_desc(self, row: Any, effective_status: str) -> str:
        if effective_status == "quality_blocked":
            return "复测报告未通过数据质量门禁；只能查看限制项，不可作为客户交付物下载。"
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
            reports=[self._report_item(row) for row in rows],
        )

    def _report_item(self, row: Any) -> ReportItem:
        effective_status = self._effective_status(row)
        return ReportItem(
            report_id=row["id"],
            title=row["title"],
            desc=self._report_desc(row, effective_status),
            date=coerce_datetime(row["generated_at"] or row["created_at"]).date().isoformat(),
            status=effective_status,
        )

    def record_download_receipt(self, tenant_id: str, report_id: str, trace_id: str) -> DownloadReceiptData:
        receipt_id = f"receipt_{uuid4().hex[:12]}"
        downloaded_at = utc_now()
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, project_id, status, metrics_json
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
            metrics = parse_json_value(row["metrics_json"], {})
            quality_publishable = self._quality_publishable(metrics)
            if row["status"] != "generated" or not quality_publishable:
                raise StarletteHTTPException(
                    status_code=409,
                    detail={
                        "code": "REPORT_QUALITY_BLOCKED",
                        "details": {"report_id": report_id, "status": row["status"]},
                    },
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


DEFAULT_PROVIDER_SCOPE: list[Provider] = ["doubao", "qianwen", "kimi", "deepseek"]

PROVIDER_LABELS: dict[str, str] = {
    "chatgpt": "ChatGPT",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "tongyi": "通义",
    "qianwen": "千问",
    "doubao": "豆包",
    "baidu_ai_search": "百度 AI 搜索",
    "yuanbao": "腾讯元宝",
    "manual_import": "人工导入",
}


def scan_dispatch_mode() -> Literal["worker", "inline"]:
    """Production defaults to durable queue dispatch; inline is an explicit diagnostic mode."""

    configured = str(os.getenv("AIRANK_SCAN_DISPATCH_MODE") or "worker").strip().lower()
    return "inline" if configured == "inline" else "worker"


def build_default_brand_questions(brand_name: str, industry: str) -> list[str]:
    return [
        f"{industry}领域有哪些适合企业采购的服务商？",
        f"企业选择{industry}服务时应比较哪些能力？",
        f"中大型企业采购{industry}服务有哪些风险和候选方案？",
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


def build_scan_metrics(task_count: int, provider_count: int) -> dict[str, Any]:
    return {
        "task_count": task_count,
        "provider_count": provider_count,
        "provider_success_count": 0,
        "provider_failed_count": 0,
        "provider_blocked_count": 0,
        "valid_sample_rate": 0,
        "mention_rate": 0,
        "recommend_rate": 0,
        "top1_rate": 0,
        "top3_rate": 0,
        "top5_rate": 0,
        "data_status": "unverified_no_provider_evidence",
        "summary": "尚无真实 Provider 样本，不能生成品牌可见度结论。",
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
    recommendation_count = sum(1 for result in results if result.mention_class == "recommended")
    top_three_count = sum(1 for result in results if result.brand_rank is not None and result.brand_rank <= 3)
    top_five_count = sum(1 for result in results if result.brand_rank is not None and result.brand_rank <= 5)
    first_rank_count = sum(1 for result in results if result.brand_rank == 1)
    ranked_count = sum(1 for result in results if result.brand_rank is not None)
    not_mentioned_count = sum(1 for result in results if not result.brand_mentioned)
    citation_sample_count = sum(1 for result in results if result.native_citations)
    collector_surface_counts = dict(
        Counter(str(result.raw_metadata.get("capture_mode") or "unknown") for result in results)
    )
    evidence_level_counts = dict(
        Counter(str(result.raw_metadata.get("evidence_level") or "unknown") for result in results)
    )
    competitor_pressure_count = 0
    for result in results:
        for competitor in result.competitor_mentions:
            competitor_rank = competitor.get("rank")
            if (
                result.brand_rank is not None
                and isinstance(competitor_rank, int)
                and competitor_rank < result.brand_rank
            ):
                competitor_pressure_count += 1
                break

    mention_rate = percentage(mention_count, success_count)
    recommend_rate = percentage(recommendation_count, success_count)
    top1_rate = percentage(first_rank_count, success_count)
    top3_rate = percentage(top_three_count, success_count)
    top5_rate = percentage(top_five_count, success_count)
    valid_sample_rate = percentage(success_count, total_count)
    repeat_groups: dict[tuple[str, str, str, str], list[tuple[str, int | None]]] = defaultdict(list)
    for result in results:
        repeat_groups[
            (
                str(result.raw_metadata.get("question_id") or ""),
                result.provider,
                str(result.raw_metadata.get("cohort_type") or ""),
                str(result.raw_metadata.get("collector_surface") or ""),
            )
        ].append((result.mention_class, result.brand_rank))
    repeat_agreements = [
        max(Counter(outcomes).values()) / len(outcomes)
        for outcomes in repeat_groups.values()
        if len(outcomes) >= 2
    ]
    stability = round((sum(repeat_agreements) / len(repeat_agreements)) * 100) if repeat_agreements else None
    return {
        "task_count": total_count,
        "provider_count": provider_count,
        "provider_success_count": success_count,
        "provider_failed_count": max(0, failed_count - blocked_count),
        "provider_blocked_count": blocked_count,
        "valid_sample_rate": valid_sample_rate,
        "effective_denominator": success_count,
        "not_mentioned_count": not_mentioned_count,
        "competitor_pressure_count": competitor_pressure_count,
        "mention_rate": mention_rate,
        "recommend_rate": recommend_rate,
        "top1_rate": top1_rate,
        "top3_rate": top3_rate,
        "top5_rate": top5_rate,
        "conditional_top3_rate": percentage(top_three_count, ranked_count) if ranked_count else None,
        "ranked_sample_count": ranked_count,
        "stability": stability,
        "citation_recall_rate": percentage(citation_sample_count, success_count),
        "citation_support": None,
        "fact_accuracy": None,
        "collector_surface_counts": collector_surface_counts,
        "evidence_level_counts": evidence_level_counts,
        "metric_formula_version": "measurement.v1",
        "data_status": "provider_evidence",
        "summary": (
            f"通过已标记采集面完成 {success_count}/{total_count} 个真实检测任务"
            f"（{', '.join(f'{surface}={count}' for surface, count in sorted(collector_surface_counts.items()))}）；"
            f"有效样本中的品牌提及率 {mention_rate}%，明确推荐率 {recommend_rate}%，"
            f"Top3 比例 {top3_rate}%；正常未提及样本 {not_mentioned_count} 条已计入分母。"
        ),
    }


def finalize_mysql_scan_run_if_terminal(
    tenant_id: str,
    project: ProjectData,
    competitors: list[CompetitorData],
    questions: list[BuyerQuestionData],
    run: ScanRunData,
) -> dict[str, Any]:
    """Aggregate one run strictly from durable task/snapshot rows.

    Workers persist one sampling slot at a time.  A run can therefore only be
    finalized after every slot is terminal; metrics are never computed from a
    worker's in-memory subset.
    """

    engine = mysql_engine()
    if engine is None:
        return {"terminal": False, "status": "running"}

    finished_at = utc_now()
    with engine.begin() as conn:
        run_row = conn.execute(
            text(
                """
                SELECT status, metrics_json, error_message
                FROM airank_scan_runs
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id = :run_id
                  AND deleted_at IS NULL
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id},
        ).mappings().first()
        if run_row is None:
            raise KeyError(run.run_id)
        if str(run_row["status"]) in {"completed", "failed", "canceled"}:
            stored_metrics = parse_json_value(run_row["metrics_json"], {})
            return {
                "terminal": True,
                "status": str(run_row["status"]),
                "metrics": stored_metrics,
                "error_message": run_row["error_message"],
            }

        task_rows = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT id, status, error_code, response_meta_json
                    FROM airank_scan_tasks
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND run_id = :run_id
                    ORDER BY id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id},
            ).mappings().all()
        ]
        pending_count = sum(1 for row in task_rows if str(row["status"]) in {"queued", "running"})
        if pending_count:
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
                      AND status IN ('queued', 'running')
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "now": finished_at,
                },
            )
            return {
                "terminal": False,
                "status": "running",
                "task_count": len(task_rows),
                "pending_count": pending_count,
            }

        snapshot_rows = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT s.provider, s.answer_text, s.brand_mentioned, s.brand_rank,
                           s.mention_class, s.target_entity_mentions_json,
                           s.competitor_mentions_json, s.sentiment, s.confidence,
                           s.external_trace_id, s.question_id, s.cohort_type,
                           s.collector_surface, s.evidence_level,
                           COUNT(c.id) AS native_citation_count
                    FROM airank_answer_snapshots s
                    LEFT JOIN airank_source_citations c
                      ON c.tenant_id = s.tenant_id
                     AND c.project_id = s.project_id
                     AND c.snapshot_id = s.id
                    WHERE s.tenant_id = :tenant_id
                      AND s.project_id = :project_id
                      AND s.run_id = :run_id
                      AND s.sample_status = 'valid'
                    GROUP BY s.id
                    ORDER BY s.created_at, s.id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id},
            ).mappings().all()
        ]
        persisted_results = [
            ProviderScanResult(
                provider=str(row["provider"]),
                provider_label=PROVIDER_LABELS.get(str(row["provider"]), str(row["provider"])),
                answer_text=str(row["answer_text"] or ""),
                brand_mentioned=bool(row["brand_mentioned"]),
                brand_rank=int(row["brand_rank"]) if row["brand_rank"] is not None else None,
                competitor_mentions=parse_json_value(row["competitor_mentions_json"], []),
                sentiment=str(row["sentiment"] or "unknown"),
                mention_class=str(row["mention_class"] or "unknown"),
                target_entity_mentions=parse_json_value(row["target_entity_mentions_json"], []),
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                external_trace_id=str(row["external_trace_id"]) if row["external_trace_id"] else None,
                native_citations=[{} for _ in range(int(row["native_citation_count"] or 0))],
                raw_metadata={
                    "question_id": row["question_id"],
                    "cohort_type": row["cohort_type"],
                    "collector_surface": row["collector_surface"],
                    "capture_mode": row["collector_surface"],
                    "evidence_level": row["evidence_level"],
                },
            )
            for row in snapshot_rows
        ]
        failed_rows = [row for row in task_rows if str(row["status"]) == "failed"]
        blocked_count = sum(
            1
            for row in failed_rows
            if bool(parse_json_value(row.get("response_meta_json"), {}).get("blocked"))
            or "BLOCK" in str(row.get("error_code") or "")
        )
        provider_minimum_success_count = minimum_provider_success_count(run.provider_scope)
        minimum_success_count = minimum_scan_success_count(
            run.provider_scope,
            len(questions),
            len(task_rows),
        )
        metrics = build_real_scan_metrics(
            persisted_results,
            failed_count=len(failed_rows),
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
        success_count = len(persisted_results)
        run_status = "completed" if success_count >= minimum_success_count else "failed"
        if run_status == "failed" and provider_execution_mode() == "browser":
            run_error_message = (
                f"Only {success_count}/{minimum_success_count} required consumer web scan tasks completed; "
                "browser login or human verification may be required."
            )
        elif run_status == "failed":
            run_error_message = (
                f"Only {success_count}/{minimum_success_count} required external AI scan tasks completed; "
                "AIRank did not generate a deliverable visibility result."
            )
        else:
            run_error_message = None

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
                  AND status IN ('queued', 'running')
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "run_id": run.run_id,
                "status": run_status,
                "metrics_json": json.dumps(metrics, ensure_ascii=False),
                "error_message": run_error_message,
                "started_at": run.started_at or finished_at,
                "finished_at": finished_at,
            },
        )
        if run_status == "completed":
            conn.execute(
                text(
                    """
                    UPDATE airank_projects
                    SET status = 'active', updated_at = :now
                    WHERE tenant_id = :tenant_id AND id = :project_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id, "now": finished_at},
            )
            insert_mysql_brand_assets(conn, tenant_id, project, competitors, questions, run, metrics, finished_at)

        return {
            "terminal": True,
            "status": run_status,
            "metrics": metrics,
            "error_message": run_error_message,
            "success_count": success_count,
            "failed_count": len(failed_rows),
            "blocked_count": blocked_count,
            "minimum_success_count": minimum_success_count,
            "provider_minimum_success_count": provider_minimum_success_count,
        }


def build_measurement_metric_cards(metrics: dict[str, Any]) -> list[MetricCard]:
    if metrics.get("data_status") != "provider_evidence":
        return []
    denominator = int(metrics.get("effective_denominator") or 0)
    total = int(metrics.get("task_count") or 0)
    sample_delta = f"{denominator}/{total} 条有效样本；失败与阻塞不进入回答分母"
    return [
        MetricCard(
            label="有效样本率",
            value=str(metrics.get("valid_sample_rate", 0)),
            suffix="%",
            delta=sample_delta,
            tone="primary",
            icon="Activity",
        ),
        MetricCard(
            label="品牌提及率",
            value=str(metrics.get("mention_rate", 0)),
            suffix="%",
            delta=f"正常未提及 {int(metrics.get('not_mentioned_count') or 0)} 条，已计入分母",
            tone="primary",
            icon="Target",
        ),
        MetricCard(
            label="明确推荐率",
            value=str(metrics.get("recommend_rate", 0)),
            suffix="%",
            delta="仅统计有明确推荐语义的有效样本",
            tone="success",
            icon="ShieldAlert",
        ),
        MetricCard(
            label="Top3 比例",
            value=str(metrics.get("top3_rate", 0)),
            suffix="%",
            delta=f"仅使用明确排名；有排名样本 {int(metrics.get('ranked_sample_count') or 0)} 条",
            tone="muted",
            icon="UserRound",
        ),
    ]


def build_unverified_overview(project: ProjectData, competitors: list[CompetitorData], message: str) -> ConsoleOverview:
    return ConsoleOverview(
        project=ProjectOverview(
            id=project.project_id,
            name=project.brand_name,
            website=project.website_url,
            industry=project.industry,
            competitors="、".join(competitor.name for competitor in competitors) or "待补充竞品",
            audience="、".join(project.audiences) or "待补充目标客户",
            date=utc_now().date(),
        ),
        metric_cards=[],
        data_status="unverified",
        message=message,
    )


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
    """Do not synthesize facts, publish packages, or reports from scan metrics.

    Measurement evidence can identify a gap, but it is not a verified enterprise
    fact source. Fact ingestion, review, content generation, and publishing are
    separate governed workflows implemented in later productization stages.
    """

    return


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
            update={
                "status": "failed",
                "attempt_count": 0,
                "started_at": now,
                "finished_at": now,
                "updated_at": now,
                "error": ScanError(code="PROVIDER_EVIDENCE_REQUIRED", message="未配置真实 Provider，未生成样本。"),
            }
        )
    SCAN_REPOSITORY._runs[(tenant_id, run_id)] = run.model_copy(
        update={
            "status": "failed",
            "started_at": now,
            "finished_at": now,
            "updated_at": now,
            "metrics": build_scan_metrics(len(related_tasks), len(run.provider_scope)),
            "error": ScanError(code="PROVIDER_EVIDENCE_REQUIRED", message="真实 Provider 证据缺失，不能完成品牌诊断。"),
        }
    )


def persist_provider_screenshot(
    tenant_id: str,
    project_id: str,
    result: ProviderScanResult,
    *,
    object_storage: Any | None = None,
) -> StoredObject | None:
    screenshot_path = str(result.raw_metadata.get("screenshot_path") or "")
    screenshot_sha256 = str(result.raw_metadata.get("screenshot_sha256") or "")
    if not screenshot_path and not screenshot_sha256:
        return None
    if not screenshot_path or not screenshot_sha256:
        raise ObjectStorageError("browser evidence must include both screenshot path and SHA-256")
    storage = object_storage or build_object_storage_from_env()
    object_partition = sha256_text(f"{tenant_id}:{project_id}")[:24]
    return storage.put_file(
        screenshot_path,
        key=(
            f"evidence/{object_partition}/provider-answer-screenshot/"
            f"{screenshot_sha256[:2]}/{screenshot_sha256}.png"
        ),
        content_type="image/png",
        expected_sha256=screenshot_sha256,
    )


def persist_provider_source_panel(
    tenant_id: str,
    project_id: str,
    result: ProviderScanResult,
    *,
    object_storage: Any | None = None,
) -> StoredObject | None:
    if result.raw_metadata.get("source_panel_status") != "captured":
        return None
    screenshot_path = str(result.raw_metadata.get("source_panel_screenshot_path") or "")
    screenshot_sha256 = str(result.raw_metadata.get("source_panel_screenshot_sha256") or "")
    if not screenshot_path or not screenshot_sha256:
        raise ObjectStorageError("captured source panel must include both screenshot path and SHA-256")
    storage = object_storage or build_object_storage_from_env()
    object_partition = sha256_text(f"{tenant_id}:{project_id}")[:24]
    return storage.put_file(
        screenshot_path,
        key=(
            f"evidence/{object_partition}/provider-source-panel/"
            f"{screenshot_sha256[:2]}/{screenshot_sha256}.png"
        ),
        content_type="image/png",
        expected_sha256=screenshot_sha256,
    )


def persist_provider_failure_screenshot(
    tenant_id: str,
    project_id: str,
    failure: dict[str, Any],
    *,
    object_storage: Any | None = None,
) -> StoredObject | None:
    metadata = failure.get("provider_metadata")
    if not isinstance(metadata, dict):
        return None
    screenshot_path = str(metadata.get("screenshot_path") or "")
    screenshot_sha256 = str(metadata.get("screenshot_sha256") or "")
    if not screenshot_path and not screenshot_sha256:
        return None
    if not screenshot_path or not screenshot_sha256:
        raise ObjectStorageError("failure screenshot must include both path and SHA-256")
    storage = object_storage or build_object_storage_from_env()
    object_partition = sha256_text(f"{tenant_id}:{project_id}")[:24]
    return storage.put_file(
        screenshot_path,
        key=(
            f"evidence/{object_partition}/provider-failure-screenshot/"
            f"{screenshot_sha256[:2]}/{screenshot_sha256}.png"
        ),
        content_type="image/png",
        expected_sha256=screenshot_sha256,
    )


def complete_mysql_real_brand_scan(
    tenant_id: str,
    project: ProjectData,
    competitors: list[CompetitorData],
    questions: list[BuyerQuestionData],
    run: ScanRunData,
    *,
    progress_hook: Callable[[str, str], None] | None = None,
    only_task_id: str | None = None,
    worker_job_id: str | None = None,
    worker_attempt_number: int | None = None,
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
        task_query = """
                    SELECT id, question_id, provider, cohort_type, prompt_version_id,
                           sample_index, session_id, collector_surface, evidence_level,
                           request_json
                    FROM airank_scan_tasks
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND run_id = :run_id
        """
        task_params = {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id}
        if only_task_id is not None:
            task_query += " AND id = :task_id"
            task_params["task_id"] = only_task_id
        task_query += " ORDER BY provider ASC, question_id ASC"
        task_rows = [
            dict(row)
            for row in conn.execute(
                text(task_query),
                task_params,
            ).mappings().all()
        ]
        if only_task_id is not None and not task_rows:
            raise KeyError(only_task_id)
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
        if progress_hook is not None:
            progress_hook(str(row["id"]), "provider_start")
        try:
            surface = str(row["collector_surface"])
            if surface == "api":
                provider_call = call_api_provider_for_brand_rank
            elif surface == "web":
                provider_call = call_provider_for_brand_rank
            else:
                raise ProviderUnavailable(provider, f"collector surface {surface} is not implemented")
            result = provider_call(
                provider=provider,
                brand_name=project.brand_name,
                website_url=project.website_url,
                industry=project.industry,
                competitor_names=competitor_names,
                question_text=question_text,
                cohort_type=str(row["cohort_type"]),
                session_id=str(row["session_id"]),
                prompt_version_id=str(row["prompt_version_id"]),
                company_names=[project.company_name] if project.company_name else [],
                product_names=project.products,
                tenant_id=tenant_id,
                project_id=project.project_id,
                task_id=str(row["id"]),
            )
            result.raw_metadata.update(
                {
                    "question_id": row["question_id"],
                    "sample_index": row["sample_index"],
                }
            )
        except ValueError as exc:
            failures.append(
                {
                    **row,
                    "started_at": task_started_at,
                    "finished_at": utc_now(),
                    "error_code": "PROMPT_COHORT_INVALID",
                    "error_message": str(exc)[:1000],
                    "blocked": False,
                }
            )
            continue
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
            code, blocked = classify_provider_call_failure(exc)
            failures.append(
                {
                    **row,
                    "started_at": task_started_at,
                    "finished_at": utc_now(),
                    "error_code": code,
                    "error_message": exc.reason[:1000],
                    "blocked": blocked,
                    "provider_error_code": exc.error_code,
                    "upstream_error_code": exc.provider_code,
                    "retryable": exc.retryable,
                    "provider_metadata": exc.public_metadata,
                }
            )
            continue
        successes.append(({**row, "started_at": task_started_at}, result))

    if progress_hook is not None:
        progress_hook("", "evidence_persist_start")
    durable_screenshots: dict[str, StoredObject] = {}
    durable_source_panels: dict[str, StoredObject] = {}
    persisted_successes: list[tuple[dict[str, Any], ProviderScanResult]] = []
    object_storage = None
    for row, result in successes:
        if progress_hook is not None:
            progress_hook(str(row["id"]), "answer_evidence_persist")
        screenshot_path = str(result.raw_metadata.get("screenshot_path") or "")
        screenshot_sha256 = str(result.raw_metadata.get("screenshot_sha256") or "")
        if not screenshot_path and not screenshot_sha256:
            persisted_successes.append((row, result))
            continue
        try:
            if not screenshot_path or not screenshot_sha256:
                raise ObjectStorageError("browser evidence must include both screenshot path and SHA-256")
            if object_storage is None:
                object_storage = build_object_storage_from_env()
            stored = persist_provider_screenshot(
                tenant_id,
                project.project_id,
                result,
                object_storage=object_storage,
            )
            assert stored is not None
            durable_screenshots[str(row["id"])] = stored
            source_panel = persist_provider_source_panel(
                tenant_id,
                project.project_id,
                result,
                object_storage=object_storage,
            )
            if source_panel is not None:
                durable_source_panels[str(row["id"])] = source_panel
            result.raw_metadata.update(
                {
                    "screenshot_object_key": stored.key,
                    "screenshot_object_uri": stored.uri,
                    "screenshot_storage_driver": stored.driver,
                    **(
                        {
                            "source_panel_object_key": source_panel.key,
                            "source_panel_object_uri": source_panel.uri,
                            "source_panel_storage_driver": source_panel.driver,
                        }
                        if source_panel is not None
                        else {}
                    ),
                }
            )
            result.raw_metadata.pop("screenshot_path", None)
            result.raw_metadata.pop("source_panel_screenshot_path", None)
            persisted_successes.append((row, result))
        except ObjectStorageError as exc:
            failures.append(
                {
                    **row,
                    "finished_at": utc_now(),
                    "error_code": "EVIDENCE_STORAGE_FAILED",
                    "error_message": str(exc)[:1000],
                    "blocked": False,
                    "provider_metadata": {
                        key: value
                        for key, value in result.raw_metadata.items()
                        if key not in {
                            "provider_raw_response",
                            "screenshot_path",
                            "source_panel_screenshot_path",
                        }
                    },
                    "captured_provider_response": {
                        "answer_text": result.answer_text,
                        "external_trace_id": result.external_trace_id,
                        "native_citations": result.native_citations,
                        "target_entity_mentions": result.target_entity_mentions,
                        "provider_raw_response": result.raw_metadata.get("provider_raw_response"),
                    },
                }
            )
    successes = persisted_successes

    durable_failure_screenshots: dict[str, StoredObject] = {}
    for failure in failures:
        if progress_hook is not None:
            progress_hook(str(failure["id"]), "failure_evidence_persist")
        provider_metadata = failure.get("provider_metadata")
        if not isinstance(provider_metadata, dict):
            continue
        try:
            screenshot = persist_provider_failure_screenshot(
                tenant_id,
                project.project_id,
                failure,
                object_storage=object_storage,
            )
            if screenshot is not None:
                durable_failure_screenshots[str(failure["id"])] = screenshot
                provider_metadata.update(
                    {
                        "screenshot_object_key": screenshot.key,
                        "screenshot_object_uri": screenshot.uri,
                        "screenshot_storage_driver": screenshot.driver,
                    }
                )
        except ObjectStorageError as exc:
            failure["failure_evidence_storage_error"] = str(exc)[:1000]
        finally:
            provider_metadata.pop("screenshot_path", None)

    finished_at = utc_now()
    if progress_hook is not None:
        progress_hook("", "database_persist_start")
    with engine.begin() as conn:
        for row, result in successes:
            snapshot_id = f"snap_{uuid4().hex[:12]}"
            evidence_snapshot_id = f"evidence_{uuid4().hex[:12]}"
            provider_audit_id = f"provider_audit_{uuid4().hex[:12]}"
            raw_response = {
                "provider": result.provider,
                "answer_text": result.answer_text,
                "external_trace_id": result.external_trace_id,
                "native_citations": result.native_citations,
                "target_entity_mentions": result.target_entity_mentions,
                "capture_metadata": result.raw_metadata,
            }
            raw_response_json = json.dumps(raw_response, ensure_ascii=False, sort_keys=True, default=str)
            raw_response_sha256 = sha256_text(raw_response_json)
            screenshot_ref_id = None
            source_panel_ref_id = None
            durable_screenshot = durable_screenshots.get(str(row["id"]))
            if durable_screenshot is not None:
                screenshot_ref_id = f"object_{uuid4().hex[:12]}"
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_object_refs (
                          id, tenant_id, project_id, object_type, object_uri,
                          content_type, byte_size, sha256, metadata_json, created_at
                        )
                        VALUES (
                          :id, :tenant_id, :project_id, :object_type, :object_uri,
                          :content_type, :byte_size, :sha256, :metadata_json, :created_at
                        )
                        """
                    ),
                    {
                        "id": screenshot_ref_id,
                        "tenant_id": tenant_id,
                        "project_id": project.project_id,
                        "object_type": "provider_answer_screenshot",
                        "object_uri": durable_screenshot.uri,
                        "content_type": durable_screenshot.content_type,
                        "byte_size": durable_screenshot.byte_size,
                        "sha256": durable_screenshot.sha256,
                        "metadata_json": json.dumps(
                            {
                                "provider": result.provider,
                                "session_id": row["session_id"],
                                "immutable": True,
                                "object_key": durable_screenshot.key,
                                "storage_driver": durable_screenshot.driver,
                            },
                            ensure_ascii=False,
                        ),
                        "created_at": finished_at,
                    },
                )
            durable_source_panel = durable_source_panels.get(str(row["id"]))
            if durable_source_panel is not None:
                source_panel_ref_id = f"object_{uuid4().hex[:12]}"
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_object_refs (
                          id, tenant_id, project_id, object_type, object_uri,
                          content_type, byte_size, sha256, metadata_json, created_at
                        )
                        VALUES (
                          :id, :tenant_id, :project_id, :object_type, :object_uri,
                          :content_type, :byte_size, :sha256, :metadata_json, :created_at
                        )
                        """
                    ),
                    {
                        "id": source_panel_ref_id,
                        "tenant_id": tenant_id,
                        "project_id": project.project_id,
                        "object_type": "provider_source_panel_screenshot",
                        "object_uri": durable_source_panel.uri,
                        "content_type": durable_source_panel.content_type,
                        "byte_size": durable_source_panel.byte_size,
                        "sha256": durable_source_panel.sha256,
                        "metadata_json": json.dumps(
                            {
                                "provider": result.provider,
                                "session_id": row["session_id"],
                                "immutable": True,
                                "capture_mode": result.raw_metadata.get("source_panel_capture_mode"),
                                "object_key": durable_source_panel.key,
                                "storage_driver": durable_source_panel.driver,
                            },
                            ensure_ascii=False,
                        ),
                        "created_at": finished_at,
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, cohort_type, prompt_version_id, sample_index,
                      session_id, collector_surface, evidence_level, sample_status,
                      answer_text, answer_sha256, raw_response_sha256,
                      brand_mentioned, brand_rank, mention_class, target_entity_mentions_json,
                      model_name, search_enabled,
                      competitor_mentions_json, sentiment, confidence,
                      raw_response_ref_id, screenshot_ref_id, source_panel_ref_id, request_metadata_ref_id,
                      external_trace_id, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :cohort_type, :prompt_version_id, :sample_index,
                      :session_id, :collector_surface, :evidence_level, :sample_status,
                      :answer_text, :answer_sha256, :raw_response_sha256,
                      :brand_mentioned, :brand_rank, :mention_class, :target_entity_mentions_json,
                      :model_name, :search_enabled,
                      :competitor_mentions_json, :sentiment, :confidence,
                      :raw_response_ref_id, :screenshot_ref_id, :source_panel_ref_id, :request_metadata_ref_id,
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
                    "cohort_type": row["cohort_type"],
                    "prompt_version_id": row["prompt_version_id"],
                    "sample_index": row["sample_index"],
                    "session_id": row["session_id"],
                    "collector_surface": row["collector_surface"],
                    "evidence_level": result.raw_metadata.get("evidence_level") or row["evidence_level"],
                    "sample_status": "valid",
                    "answer_text": result.answer_text,
                    "answer_sha256": result.raw_metadata["answer_sha256"],
                    "raw_response_sha256": raw_response_sha256,
                    "brand_mentioned": 1 if result.brand_mentioned else 0,
                    "brand_rank": result.brand_rank,
                    "mention_class": result.mention_class,
                    "target_entity_mentions_json": json.dumps(result.target_entity_mentions, ensure_ascii=False),
                    "model_name": result.raw_metadata.get("model_name"),
                    "search_enabled": result.raw_metadata.get("search_used"),
                    "competitor_mentions_json": json.dumps(result.competitor_mentions, ensure_ascii=False),
                    "sentiment": result.sentiment,
                    "confidence": result.confidence,
                    "raw_response_ref_id": evidence_snapshot_id,
                    "screenshot_ref_id": screenshot_ref_id,
                    "source_panel_ref_id": source_panel_ref_id,
                    "request_metadata_ref_id": evidence_snapshot_id,
                    "external_trace_id": result.external_trace_id,
                    "created_at": finished_at,
                },
            )
            if worker_job_id is not None and worker_attempt_number is not None:
                conn.execute(
                    text(
                        """
                        UPDATE airank_scan_task_attempts
                        SET status = 'succeeded',
                            answer_snapshot_id = :answer_snapshot_id,
                            evidence_snapshot_id = :evidence_snapshot_id,
                            provider_request_id = :provider_request_id,
                            error_code = NULL,
                            error_message = NULL,
                            metadata_json = :metadata_json,
                            completed_at = :completed_at
                        WHERE tenant_id = :tenant_id
                          AND task_id = :task_id
                          AND job_id = :job_id
                          AND attempt_number = :attempt_number
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "task_id": row["id"],
                        "job_id": worker_job_id,
                        "attempt_number": worker_attempt_number,
                        "answer_snapshot_id": snapshot_id,
                        "evidence_snapshot_id": evidence_snapshot_id,
                        "provider_request_id": result.external_trace_id,
                        "metadata_json": json.dumps(
                            {
                                "evidence_level": result.raw_metadata.get("evidence_level") or row["evidence_level"],
                                "capture_mode": result.raw_metadata.get("capture_mode"),
                                "provider_attempt_count": int(result.raw_metadata.get("attempt_count") or 1),
                            },
                            ensure_ascii=False,
                        ),
                        "completed_at": finished_at,
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_snapshots (
                      id, tenant_id, project_id, answer_snapshot_id,
                      raw_response_json, raw_response_sha256, screenshot_ref_id,
                      source_panel_ref_id, request_metadata_json, captured_at, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :answer_snapshot_id,
                      :raw_response_json, :raw_response_sha256, :screenshot_ref_id,
                      :source_panel_ref_id, :request_metadata_json, :captured_at, :created_at
                    )
                    """
                ),
                {
                    "id": evidence_snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "answer_snapshot_id": snapshot_id,
                    "raw_response_json": raw_response_json,
                    "raw_response_sha256": raw_response_sha256,
                    "screenshot_ref_id": screenshot_ref_id,
                    "source_panel_ref_id": source_panel_ref_id,
                    "request_metadata_json": json.dumps(
                        {
                            "task_request": parse_json_value(row.get("request_json"), {}),
                            "provider_request": {
                                key: value
                                for key, value in result.raw_metadata.items()
                                if key != "provider_raw_response"
                            },
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    "captured_at": finished_at,
                    "created_at": finished_at,
                },
            )
            if result.raw_metadata.get("capture_mode") == "provider_api":
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_provider_request_audits (
                          id, tenant_id, project_id, run_id, task_id, answer_snapshot_id,
                          provider_key, model_name, endpoint_host, configuration_fingerprint,
                          provider_request_id, prompt_sha256, outcome, evidence_grade,
                          attempt_count, duration_ms, requested_at, completed_at, metadata_json
                        )
                        VALUES (
                          :id, :tenant_id, :project_id, :run_id, :task_id, :answer_snapshot_id,
                          :provider_key, :model_name, :endpoint_host, :configuration_fingerprint,
                          :provider_request_id, :prompt_sha256, 'success', :evidence_grade,
                          :attempt_count, :duration_ms, :requested_at, :completed_at, :metadata_json
                        )
                        """
                    ),
                    {
                        "id": provider_audit_id,
                        "tenant_id": tenant_id,
                        "project_id": project.project_id,
                        "run_id": run.run_id,
                        "task_id": row["id"],
                        "answer_snapshot_id": snapshot_id,
                        "provider_key": result.provider,
                        "model_name": result.raw_metadata["model_name"],
                        "endpoint_host": result.raw_metadata["endpoint_host"],
                        "configuration_fingerprint": result.raw_metadata["configuration_fingerprint"],
                        "provider_request_id": result.external_trace_id,
                        "prompt_sha256": result.raw_metadata["prompt_sha256"],
                        "evidence_grade": result.raw_metadata.get("evidence_level"),
                        "attempt_count": int(result.raw_metadata.get("attempt_count") or 1),
                        "duration_ms": result.raw_metadata.get("duration_ms"),
                        "requested_at": result.raw_metadata.get("requested_at") or finished_at,
                        "completed_at": result.raw_metadata.get("completed_at") or finished_at,
                        "metadata_json": json.dumps(
                            {
                                "search_requested": result.raw_metadata.get("search_requested"),
                                "search_used": result.raw_metadata.get("search_used"),
                                "source_extraction": result.raw_metadata.get("source_extraction"),
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
                usage = result.raw_metadata.get("usage")
                if isinstance(usage, dict):
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_provider_usage_events (
                              id, tenant_id, project_id, request_audit_id,
                              provider_key, model_name, input_tokens, output_tokens,
                              total_tokens, precision_status, usage_source, occurred_at
                            )
                            VALUES (
                              :id, :tenant_id, :project_id, :request_audit_id,
                              :provider_key, :model_name, :input_tokens, :output_tokens,
                              :total_tokens, :precision_status, :usage_source, :occurred_at
                            )
                            """
                        ),
                        {
                            "id": f"provider_usage_{uuid4().hex[:12]}",
                            "tenant_id": tenant_id,
                            "project_id": project.project_id,
                            "request_audit_id": provider_audit_id,
                            "provider_key": result.provider,
                            "model_name": result.raw_metadata["model_name"],
                            "input_tokens": usage.get("input_tokens"),
                            "output_tokens": usage.get("output_tokens"),
                            "total_tokens": usage.get("total_tokens"),
                            "precision_status": usage.get("precision") or "unknown",
                            "usage_source": usage.get("source") or "provider_response",
                            "occurred_at": result.raw_metadata.get("completed_at") or finished_at,
                        },
                    )
            for citation_order, citation in enumerate(result.native_citations, start=1):
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
                        "id": f"cite_{uuid4().hex[:12]}",
                        "tenant_id": tenant_id,
                        "project_id": project.project_id,
                        "snapshot_id": snapshot_id,
                        "citation_order": citation_order,
                        "title": citation.get("title"),
                        "url": citation.get("url"),
                        "host": citation.get("host"),
                        "source_type": "provider_native",
                        "cited_text": citation.get("cited_text") or citation.get("title"),
                        "relevance_score": None,
                        "metadata_json": json.dumps(
                            {
                                "extraction": result.raw_metadata.get("source_extraction", "unknown"),
                                "provider": result.provider,
                            },
                            ensure_ascii=False,
                        ),
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
                    "started_at": row["started_at"],
                    "finished_at": finished_at,
                    "response_meta_json": json.dumps(
                        {
                            "mode": result.raw_metadata.get("capture_mode", "unknown"),
                            "provider": result.provider,
                            **{
                                key: value
                                for key, value in result.raw_metadata.items()
                                if key != "provider_raw_response"
                            },
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs
                    SET status = 'succeeded',
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
            provider_metadata = failure.get("provider_metadata")
            failure_status = "blocked" if failure.get("blocked") else "failed"
            failure_snapshot_id = f"snap_{uuid4().hex[:12]}"
            failure_evidence_id = f"evidence_{uuid4().hex[:12]}"
            failure_screenshot_ref_id = None
            durable_failure_screenshot = durable_failure_screenshots.get(str(failure["id"]))
            if durable_failure_screenshot is not None:
                failure_screenshot_ref_id = f"object_{uuid4().hex[:12]}"
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_object_refs (
                          id, tenant_id, project_id, object_type, object_uri,
                          content_type, byte_size, sha256, metadata_json, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, 'provider_failure_screenshot', :object_uri,
                          :content_type, :byte_size, :sha256, :metadata_json, :created_at
                        )
                        """
                    ),
                    {
                        "id": failure_screenshot_ref_id,
                        "tenant_id": tenant_id,
                        "project_id": project.project_id,
                        "object_uri": durable_failure_screenshot.uri,
                        "content_type": durable_failure_screenshot.content_type,
                        "byte_size": durable_failure_screenshot.byte_size,
                        "sha256": durable_failure_screenshot.sha256,
                        "metadata_json": json.dumps(
                            {
                                "provider": failure["provider"],
                                "session_id": failure.get("session_id"),
                                "immutable": True,
                                "object_key": durable_failure_screenshot.key,
                                "storage_driver": durable_failure_screenshot.driver,
                                "failure_code": failure["error_code"],
                            },
                            ensure_ascii=False,
                        ),
                        "created_at": failure["finished_at"],
                    },
                )
            public_provider_metadata = (
                {
                    key: value
                    for key, value in provider_metadata.items()
                    if key != "provider_raw_response"
                }
                if isinstance(provider_metadata, dict)
                else {}
            )
            failure_payload = {
                "error_code": failure["error_code"],
                "error_message": failure["error_message"],
                "blocked": bool(failure.get("blocked")),
                "provider_error_code": failure.get("provider_error_code"),
                "upstream_error_code": failure.get("upstream_error_code"),
                "retryable": bool(failure.get("retryable")),
                "evidence_storage_error": failure.get("failure_evidence_storage_error"),
            }
            failure_raw_response = {
                "provider": failure["provider"],
                "sample_status": failure_status,
                "failure": failure_payload,
                "capture_metadata": public_provider_metadata,
                **(
                    {"captured_provider_response": failure["captured_provider_response"]}
                    if failure.get("captured_provider_response") is not None
                    else {}
                ),
            }
            failure_raw_json = json.dumps(
                failure_raw_response,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            failure_raw_sha256 = sha256_text(failure_raw_json)
            failure_request_metadata = {
                "task_request": parse_json_value(failure.get("request_json"), {}),
                "provider_request": public_provider_metadata,
                "failure": failure_payload,
            }
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, cohort_type, prompt_version_id, sample_index,
                      session_id, collector_surface, evidence_level, sample_status,
                      answer_text, answer_sha256, raw_response_sha256,
                      brand_mentioned, brand_rank, mention_class, target_entity_mentions_json,
                      model_name, search_enabled, competitor_mentions_json, sentiment, confidence,
                      raw_response_ref_id, screenshot_ref_id, request_metadata_ref_id,
                      external_trace_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :cohort_type, :prompt_version_id, :sample_index,
                      :session_id, :collector_surface, :evidence_level, :sample_status,
                      '', NULL, :raw_response_sha256,
                      0, NULL, 'unknown', JSON_ARRAY(),
                      :model_name, NULL, JSON_ARRAY(), NULL, NULL,
                      :raw_response_ref_id, :screenshot_ref_id, :request_metadata_ref_id,
                      :external_trace_id, :created_at
                    )
                    """
                ),
                {
                    "id": failure_snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": failure["id"],
                    "question_id": failure["question_id"],
                    "provider": failure["provider"],
                    "cohort_type": failure["cohort_type"],
                    "prompt_version_id": failure["prompt_version_id"],
                    "sample_index": failure["sample_index"],
                    "session_id": failure["session_id"],
                    "collector_surface": failure["collector_surface"],
                    "evidence_level": failure["evidence_level"],
                    "sample_status": failure_status,
                    "raw_response_sha256": failure_raw_sha256,
                    "model_name": public_provider_metadata.get("model_name"),
                    "raw_response_ref_id": failure_evidence_id,
                    "screenshot_ref_id": failure_screenshot_ref_id,
                    "request_metadata_ref_id": failure_evidence_id,
                    "external_trace_id": (
                        public_provider_metadata.get("provider_request_id")
                        or public_provider_metadata.get("browser_trace_id")
                    ),
                    "created_at": failure["finished_at"],
                },
            )
            if worker_job_id is not None and worker_attempt_number is not None:
                conn.execute(
                    text(
                        """
                        UPDATE airank_scan_task_attempts
                        SET status = :status,
                            answer_snapshot_id = :answer_snapshot_id,
                            evidence_snapshot_id = :evidence_snapshot_id,
                            provider_request_id = :provider_request_id,
                            error_code = :error_code,
                            error_message = :error_message,
                            metadata_json = :metadata_json,
                            completed_at = :completed_at
                        WHERE tenant_id = :tenant_id
                          AND task_id = :task_id
                          AND job_id = :job_id
                          AND attempt_number = :attempt_number
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "task_id": failure["id"],
                        "job_id": worker_job_id,
                        "attempt_number": worker_attempt_number,
                        "status": failure_status,
                        "answer_snapshot_id": failure_snapshot_id,
                        "evidence_snapshot_id": failure_evidence_id,
                        "provider_request_id": (
                            public_provider_metadata.get("provider_request_id")
                            or public_provider_metadata.get("browser_trace_id")
                        ),
                        "error_code": failure["error_code"],
                        "error_message": failure["error_message"],
                        "metadata_json": json.dumps(
                            {
                                "blocked": bool(failure.get("blocked")),
                                "retryable": bool(failure.get("retryable")),
                                "provider_error_code": failure.get("provider_error_code"),
                                "upstream_error_code": failure.get("upstream_error_code"),
                            },
                            ensure_ascii=False,
                        ),
                        "completed_at": failure["finished_at"],
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_snapshots (
                      id, tenant_id, project_id, answer_snapshot_id,
                      raw_response_json, raw_response_sha256, screenshot_ref_id,
                      source_panel_ref_id, request_metadata_json, captured_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :answer_snapshot_id,
                      :raw_response_json, :raw_response_sha256, :screenshot_ref_id,
                      NULL, :request_metadata_json, :captured_at, :captured_at
                    )
                    """
                ),
                {
                    "id": failure_evidence_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "answer_snapshot_id": failure_snapshot_id,
                    "raw_response_json": failure_raw_json,
                    "raw_response_sha256": failure_raw_sha256,
                    "screenshot_ref_id": failure_screenshot_ref_id,
                    "request_metadata_json": json.dumps(
                        failure_request_metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                    "captured_at": failure["finished_at"],
                },
            )
            if isinstance(provider_metadata, dict) and provider_metadata.get("capture_mode") == "provider_api":
                required_audit_values = (
                    provider_metadata.get("model_name"),
                    provider_metadata.get("endpoint_host"),
                    provider_metadata.get("configuration_fingerprint"),
                    provider_metadata.get("prompt_sha256"),
                )
                if all(required_audit_values):
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_provider_request_audits (
                              id, tenant_id, project_id, run_id, task_id, answer_snapshot_id,
                              provider_key, model_name, endpoint_host, configuration_fingerprint,
                              prompt_sha256, outcome, attempt_count, error_code,
                              provider_error_code, requested_at, completed_at, metadata_json
                            )
                            VALUES (
                              :id, :tenant_id, :project_id, :run_id, :task_id, :answer_snapshot_id,
                              :provider_key, :model_name, :endpoint_host, :configuration_fingerprint,
                              :prompt_sha256, 'failed', :attempt_count, :error_code,
                              :provider_error_code, :requested_at, :completed_at, :metadata_json
                            )
                            """
                        ),
                        {
                            "id": f"provider_audit_{uuid4().hex[:12]}",
                            "tenant_id": tenant_id,
                            "project_id": project.project_id,
                            "run_id": run.run_id,
                            "task_id": failure["id"],
                            "answer_snapshot_id": failure_snapshot_id,
                            "provider_key": failure["provider"],
                            "model_name": provider_metadata["model_name"],
                            "endpoint_host": provider_metadata["endpoint_host"],
                            "configuration_fingerprint": provider_metadata["configuration_fingerprint"],
                            "prompt_sha256": provider_metadata["prompt_sha256"],
                            "attempt_count": 1,
                            "error_code": failure.get("provider_error_code") or failure["error_code"],
                            "provider_error_code": failure.get("upstream_error_code"),
                            "requested_at": failure["started_at"],
                            "completed_at": failure["finished_at"],
                            "metadata_json": json.dumps(
                                {"retryable": bool(failure.get("retryable"))}, ensure_ascii=False
                            ),
                        },
                    )
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
                            "mode": str(failure.get("collector_surface") or "unknown"),
                            "provider": failure["provider"],
                            "blocked": failure.get("blocked", False),
                            "provider_error_code": failure.get("provider_error_code"),
                            "upstream_error_code": failure.get("upstream_error_code"),
                            "retryable": failure.get("retryable", False),
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

    aggregate = finalize_mysql_scan_run_if_terminal(tenant_id, project, competitors, questions, run)
    if aggregate.get("terminal") and aggregate.get("status") != "completed":
        raise StarletteHTTPException(
            status_code=503,
            detail={
                "code": "INTEGRATION_CAPABILITY_BLOCKED",
                "message": "外部 AI 真实采样未达到生产门槛，请检查 Provider 凭证、模型、联网能力或浏览器登录态。",
                "details": {
                    "run_id": run.run_id,
                    "provider_mode": provider_execution_mode(),
                    "providers": run.provider_scope,
                    "success_count": aggregate.get("success_count", 0),
                    "minimum_success_count": aggregate.get("minimum_success_count", 0),
                    "provider_minimum_success_count": aggregate.get("provider_minimum_success_count", 0),
                    "failed_count": aggregate.get("failed_count", 0),
                    "blocked_count": aggregate.get("blocked_count", 0),
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
    *,
    progress_hook: Callable[[str, str], None] | None = None,
    only_task_id: str | None = None,
    worker_job_id: str | None = None,
    worker_attempt_number: int | None = None,
) -> None:
    if provider_execution_mode() != "mock":
        complete_mysql_real_brand_scan(
            tenant_id,
            project,
            competitors,
            questions,
            run,
            progress_hook=progress_hook,
            only_task_id=only_task_id,
            worker_job_id=worker_job_id,
            worker_attempt_number=worker_attempt_number,
        )
        return

    engine = mysql_engine()
    if engine is None:
        return

    now = utc_now()
    metrics = build_scan_metrics(
        len(run.provider_scope) * len(questions) * len(run.collector_surfaces) * run.repetitions,
        len(run.provider_scope),
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE airank_scan_tasks
                SET status = 'failed', error_code = 'PROVIDER_EVIDENCE_REQUIRED',
                    error_message = 'Mock mode cannot produce commercial measurement evidence.',
                    finished_at = :now, updated_at = :now
                WHERE tenant_id = :tenant_id AND project_id = :project_id AND run_id = :run_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id, "now": now},
        )
        conn.execute(
            text(
                """
                UPDATE airank_scan_runs
                SET status = 'failed', metrics_json = :metrics_json,
                    error_message = 'Mock mode cannot produce commercial measurement evidence.',
                    finished_at = :now, updated_at = :now
                WHERE tenant_id = :tenant_id AND project_id = :project_id AND id = :run_id
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
                UPDATE airank_async_jobs j
                JOIN airank_scan_tasks t
                  ON t.tenant_id = j.tenant_id
                 AND t.project_id = j.project_id
                 AND t.id = JSON_UNQUOTE(JSON_EXTRACT(j.payload_json, '$.scan_task_id'))
                SET j.status = 'failed',
                    j.started_at = COALESCE(j.started_at, :now),
                    j.finished_at = :now,
                    j.updated_at = :now,
                    j.error_code = 'PROVIDER_EVIDENCE_REQUIRED',
                    j.error_message = 'Mock mode cannot produce commercial measurement evidence.'
                WHERE j.tenant_id = :tenant_id
                  AND j.project_id = :project_id
                  AND j.job_type = 'scan.provider'
                  AND t.run_id = :run_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project.project_id,
                "run_id": run.run_id,
                "now": now,
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
    data_status: Literal["empty", "collecting", "provider_evidence", "unverified"]
    if metrics.get("data_status") == "provider_evidence" and run_status == "completed":
        data_status = "provider_evidence"
    elif run_status in {"queued", "running"}:
        data_status = "collecting"
    else:
        data_status = "unverified"

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
        metric_cards=build_measurement_metric_cards(metrics),
        data_status=data_status,
        message=(
            str(metrics.get("summary") or "")
            if data_status == "provider_evidence"
            else run_error_message or "真实 Provider 采样尚未完成，不展示品牌指标。"
        ),
    )


def mysql_project_from_row(row: Any, *, industry_fallback: str = "unknown") -> ProjectData:
    products = parse_json_value(row["products_services_json"], ["AI visibility diagnosis"])
    audiences = parse_json_value(row["target_audience_json"], ["B2B growth leader"])
    return ProjectData(
        project_id=row["id"],
        tenant_id=row["tenant_id"],
        website_url=row["website_url"],
        brand_name=row["brand_name"] or row["name"],
        company_name=row["name"],
        industry=row["industry"] or industry_fallback,
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


def get_mysql_project(tenant_id: str, project_id: str) -> ProjectData:
    engine = mysql_engine()
    if engine is None:
        raise StarletteHTTPException(
            status_code=503,
            detail={"code": "INTEGRATION_CAPABILITY_BLOCKED", "details": {"capability": "mysql"}},
        )
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, tenant_id, brand_name, name, website_url, industry,
                       products_services_json, target_audience_json, status,
                       created_at, updated_at
                FROM airank_projects
                WHERE tenant_id = :tenant_id
                  AND id = :project_id
                  AND deleted_at IS NULL
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().first()
    if row is None:
        raise StarletteHTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}},
        )
    return mysql_project_from_row(row)


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

    return mysql_project_from_row(row, industry_fallback=payload.industry_hint or "unknown")


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
                SELECT q.id, q.tenant_id, q.project_id, q.question_text, q.question_type,
                       q.intent, q.funnel_stage, q.source, q.status, q.metadata_json,
                       q.taxonomy_version AS current_taxonomy_version,
                       q.dedupe_sha256 AS current_dedupe_sha256,
                       r.question_version_id, r.taxonomy_version, r.dedupe_sha256,
                       r.prompt_style, r.temporal_scope, r.scenario, r.region,
                       r.cohort_type, r.source_kind, r.source_ref, r.evidence_level,
                       r.observed_query,
                       rv.reviewed_by, rv.reviewed_at, rv.review_note,
                       q.created_at, q.updated_at
                FROM airank_buyer_questions q
                LEFT JOIN airank_buyer_question_revisions r
                  ON r.id = q.current_revision_id
                LEFT JOIN airank_buyer_question_reviews rv
                  ON rv.id = (
                    SELECT latest_review.id
                    FROM airank_buyer_question_reviews latest_review
                    WHERE latest_review.tenant_id = q.tenant_id
                      AND latest_review.question_id = q.id
                    ORDER BY latest_review.reviewed_at DESC, latest_review.id DESC
                    LIMIT 1
                  )
                WHERE q.tenant_id = :tenant_id
                  AND q.project_id = :project_id
                  AND q.deleted_at IS NULL
                ORDER BY q.created_at ASC, q.id ASC
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
                question_version_id=row["question_version_id"],
                taxonomy_version=row["taxonomy_version"] or row["current_taxonomy_version"] or "legacy_unclassified",
                dedupe_sha256=row["dedupe_sha256"] or row["current_dedupe_sha256"],
                prompt_style=row["prompt_style"] or "exploratory",
                temporal_scope=row["temporal_scope"] or "evergreen",
                scenario=row["scenario"] or "generic",
                region=row["region"],
                cohort_type=row["cohort_type"] if row["cohort_type"] in {"blind", "assisted", "comparison", "fact_verification"} else "unclassified",
                source_kind=row["source_kind"] if row["source_kind"] in {"provided_seed", "template_candidate", "observed_query", "imported"} else "imported",
                source_ref=row["source_ref"] or "legacy-row",
                evidence_level=row["evidence_level"] if row["evidence_level"] in {"provided_seed", "template_candidate", "observed_query", "imported"} else "imported",
                observed_query=bool(row["observed_query"]),
                reviewed_by=row["reviewed_by"],
                reviewed_at=coerce_datetime(row["reviewed_at"]) if row["reviewed_at"] else None,
                review_note=row["review_note"],
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
        or build_unverified_overview(
            project,
            list_mysql_project_competitors(tenant_id, project.project_id),
            "真实 Provider 样本不可用，不展示品牌指标。",
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
            collector_surfaces=["api"] if provider_execution_mode() == "api" else ["web"],
            provider_scope=DEFAULT_PROVIDER_SCOPE,
            question_scope=QuestionScope(mode="selected", question_ids=[question.question_id for question in questions]),
        ),
    )

    if os.getenv("AIRANK_DATABASE_URL") and scan_dispatch_mode() == "inline":
        complete_mysql_brand_scan(tenant_id, project, competitors, questions, scan_run)
    else:
        if not os.getenv("AIRANK_DATABASE_URL"):
            complete_in_memory_brand_scan(tenant_id, scan_run.run_id)

    completed_run = SCAN_REPOSITORY.get_run(tenant_id, scan_run.run_id)
    tasks = SCAN_REPOSITORY.list_tasks(tenant_id, completed_run.run_id)
    asset_bundle = ASSET_BUNDLE_REPOSITORY.get_bundle(tenant_id, project.project_id)
    reports = REPORT_REPOSITORY.list_reports(tenant_id, project.project_id)
    overview = build_mysql_console_overview(tenant_id) or build_unverified_overview(
        project,
        competitors,
        completed_run.error.message if completed_run.error else "真实 Provider 样本不可用，不展示品牌指标。",
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


def extract_yudao_permissions(payload: dict[str, Any]) -> tuple[str, ...]:
    data = payload.get("data")
    raw_permissions = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(raw_permissions, (list, tuple, set)):
        return ()
    return tuple(sorted({str(permission).strip() for permission in raw_permissions if str(permission).strip()}))


def skill_admin_permission() -> str:
    return os.getenv("AIRANK_SKILL_ADMIN_PERMISSION", "airank:skill:admin").strip() or "airank:skill:admin"


def permission_allows(granted: tuple[str, ...], required: str) -> bool:
    namespace = required.rsplit(":", 1)[0]
    return bool({required, "*", "*:*:*", f"{namespace}:*"}.intersection(granted))


def require_skill_admin(permission_header: Optional[str]) -> None:
    if not auth_enforcement_required():
        return
    granted = tuple(item.strip() for item in (permission_header or "").split(",") if item.strip())
    required = skill_admin_permission()
    if not permission_allows(granted, required):
        raise StarletteHTTPException(
            status_code=403,
            detail={"code": "AUTH_PERMISSION_FORBIDDEN", "details": {"required_permission": required}},
        )


def build_dev_only_auth_response(payload: AuthLoginRequest, trace_id: Optional[str]) -> AuthLoginResponse:
    token = f"dev_only_{uuid4().hex}"
    expires_in = 3600
    with _DEV_AUTH_SESSIONS_LOCK:
        _DEV_AUTH_SESSIONS[token] = {
            "tenant_id": get_airank_default_tenant_id(),
            "yudao_tenant_id": payload.yudao_tenant_id,
            "user_id": payload.username,
            "permissions": tuple(
                item.strip()
                for item in os.getenv("AIRANK_DEV_PERMISSIONS", skill_admin_permission()).split(",")
                if item.strip()
            ),
            "expires_at": datetime.now(timezone.utc).timestamp() + expires_in,
        }
    return AuthLoginResponse(
        data=AuthLoginData(
            access_token=token,
            token_type="Bearer",
            expires_in=expires_in,
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


def auth_enforcement_required() -> bool:
    return os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower() not in {
        "0",
        "false",
        "disabled",
        "off",
    }


def bearer_token(request: Request) -> Optional[str]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def inject_trusted_header(request: Request, name: str, value: str) -> None:
    encoded_name = name.lower().encode("latin-1")
    headers = [item for item in request.scope.get("headers", []) if item[0].lower() != encoded_name]
    headers.append((encoded_name, value.encode("latin-1")))
    request.scope["headers"] = headers


def validate_dev_session(token: str) -> Optional[dict[str, Any]]:
    now = datetime.now(timezone.utc).timestamp()
    with _DEV_AUTH_SESSIONS_LOCK:
        session = _DEV_AUTH_SESSIONS.get(token)
        if session is None:
            return None
        if float(session["expires_at"]) <= now:
            _DEV_AUTH_SESSIONS.pop(token, None)
            return None
        return dict(session)


def trusted_authenticated_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    if not auth_enforcement_required():
        return requested_actor
    if not authenticated_actor:
        raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})
    return authenticated_actor


def validate_yudao_request_token(
    token: str,
    yudao_tenant_id: str,
) -> Optional[tuple[AuthUser, tuple[str, ...]]]:
    try:
        permission_payload = request_external_json(
            build_yudao_url("YUDAO_PERMISSION_INFO_URL", "/admin-api/system/auth/get-permission-info"),
            method="GET",
            headers={"Authorization": f"Bearer {token}", "tenant-id": yudao_tenant_id},
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None
    if not yudao_business_success(permission_payload):
        return None
    return (
        extract_yudao_user(permission_payload, "authenticated-user"),
        extract_yudao_permissions(permission_payload),
    )


@app.middleware("http")
async def enforce_api_authentication(request: Request, call_next):
    public_paths = {
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/health",
        f"{API_PREFIX}/version",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
    }
    if (
        not auth_enforcement_required()
        or request.method == "OPTIONS"
        or request.url.path in public_paths
        or not request.url.path.startswith(API_PREFIX)
    ):
        return await call_next(request)

    token = bearer_token(request)
    if token is None:
        return build_error_response(request, "AUTH_TOKEN_MISSING")
    tenant_id = request.headers.get("tenant-id", "").strip()
    if not tenant_id:
        return build_error_response(request, "TENANT_MISMATCH", details={"reason": "tenant-id header is required"})

    mode = get_auth_mode()
    if mode in {"dev", "dev_only", "development"}:
        session = validate_dev_session(token)
        if session is None:
            return build_error_response(request, "AUTH_TOKEN_INVALID")
        if tenant_id != session["tenant_id"]:
            return build_error_response(request, "TENANT_MISMATCH")
        inject_trusted_header(request, "X-AIRank-User-Id", str(session["user_id"]))
        inject_trusted_header(request, "X-Yudao-Tenant-Id", str(session["yudao_tenant_id"]))
        inject_trusted_header(request, "X-AIRank-Permissions", ",".join(session.get("permissions", ())))
        return await call_next(request)

    if tenant_id != get_airank_default_tenant_id():
        return build_error_response(request, "TENANT_MISMATCH")
    yudao_tenant_id = request.headers.get("x-yudao-tenant-id", "").strip()
    if not yudao_tenant_id:
        return build_error_response(request, "AUTH_TOKEN_INVALID", details={"reason": "X-Yudao-Tenant-Id header is required"})
    identity = await run_in_threadpool(validate_yudao_request_token, token, yudao_tenant_id)
    if identity is None:
        return build_error_response(request, "AUTH_TOKEN_INVALID")
    user, permissions = identity
    inject_trusted_header(request, "X-AIRank-User-Id", user.user_id)
    inject_trusted_header(request, "X-AIRank-Permissions", ",".join(permissions))
    return await call_next(request)


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


@app.get(
    f"{API_PREFIX}/projects/{{project_id}}/buyer-questions",
    response_model=BuyerQuestionListResponse,
    response_model_exclude_none=True,
)
def list_buyer_questions(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> BuyerQuestionListResponse:
    return BuyerQuestionListResponse(
        data=PROJECT_REPOSITORY.list_buyer_questions(tenant_id, project_id),
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
    f"{API_PREFIX}/projects/{{project_id}}/scan-runs",
    response_model=ScanRunListResponse,
    response_model_exclude_none=True,
)
def list_scan_runs(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> ScanRunListResponse:
    return ScanRunListResponse(data=SCAN_REPOSITORY.list_runs(tenant_id, project_id), meta=build_meta(trace_id))


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
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> FactReviewResponse:
    trusted_payload = payload.model_copy(
        update={"reviewed_by": trusted_authenticated_actor(payload.reviewed_by, authenticated_actor)}
    )
    return FactReviewResponse(
        data=FACT_REVIEW_REPOSITORY.review_fact(tenant_id, project_id, fact_id, trusted_payload),
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


@app.get(f"{API_PREFIX}/admin/skills", response_model=SkillRegistryResponse)
def get_skill_registry(
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> SkillRegistryResponse:
    require_skill_admin(permissions)
    registry = load_default_registry()
    evaluations = {report.skill_id: report for report in evaluate_registry(registry)}
    return SkillRegistryResponse(
        data=SkillRegistryData(
            skills=[
                SkillManifestData(
                    skill_id=manifest.skill_id,
                    version=manifest.version,
                    category=manifest.category,  # type: ignore[arg-type]
                    input_schema=dict(manifest.input_schema),
                    output_schema=dict(manifest.output_schema),
                    dependencies=list(manifest.dependencies),
                    provider_requirements=list(manifest.provider_requirements),
                    evidence_level=list(manifest.evidence_level),
                    fact_policy=dict(manifest.fact_policy),
                    failure_policy=dict(manifest.failure_policy),
                    quality_rubric=[dict(item) for item in manifest.quality_rubric],
                    eval_cases=[dict(item) for item in manifest.eval_cases],
                    promotion_policy=dict(manifest.promotion_policy),
                    evaluation=SkillEvaluationSummaryData(
                        **evaluations[manifest.skill_id].to_dict(include_cases=False)
                    ),
                    status=manifest.status,  # type: ignore[arg-type]
                    entrypoint=manifest.entrypoint,
                )
                for manifest in registry.list()
            ]
        ),
        meta=build_meta(trace_id),
    )


@app.get(f"{API_PREFIX}/admin/skills/promotion-ledger", response_model=SkillPromotionLedgerResponse)
def get_skill_promotion_ledger(
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> SkillPromotionLedgerResponse:
    require_skill_admin(permissions)
    return SkillPromotionLedgerResponse(data=build_promotion_ledger(), meta=build_meta(trace_id))


@app.post(f"{API_PREFIX}/admin/skills/{{skill_id}}/eval", response_model=SkillEvalResponse)
def evaluate_skill(
    skill_id: str,
    payload: SkillEvalRequest,
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    permissions: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> SkillEvalResponse:
    require_skill_admin(permissions)
    registry = load_default_registry()
    try:
        manifest = registry.get(skill_id)
    except KeyError as exc:
        raise StarletteHTTPException(
            status_code=404,
            detail={"code": "SKILL_NOT_FOUND", "details": {"skill_id": skill_id}},
        ) from exc
    try:
        Draft202012Validator(manifest.input_schema).validate(payload.input)
    except JsonSchemaValidationError as exc:
        raise StarletteHTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_FAILED",
                "details": {"skill_id": skill_id, "path": list(exc.absolute_path), "message": exc.message},
            },
        ) from exc
    output = run_skill(skill_id, payload.input)
    Draft202012Validator(manifest.output_schema).validate(output)
    return SkillEvalResponse(
        data=SkillEvalData(
            skill_id=skill_id,
            version=manifest.version,
            manifest_status=manifest.status,  # type: ignore[arg-type]
            output=output,
        ),
        meta=build_meta(trace_id),
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

    return ConsoleOverviewResponse(
        data=ConsoleOverview(
            project=ProjectOverview(
                id="",
                name="尚未创建品牌项目",
                website="",
                industry="",
                competitors="",
                audience="",
                date=utc_now().date(),
            ),
            metric_cards=[],
            data_status="empty",
            message="尚未创建品牌项目；创建后完成真实 Provider 采样才会显示指标。",
        ),
        meta=build_meta(trace_id),
    )


try:
    from .knowledge_routes import router as knowledge_router
except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
    from knowledge_routes import router as knowledge_router  # type: ignore[no-redef]

app.include_router(knowledge_router)

try:
    from .delivery_routes import router as delivery_router
except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
    from delivery_routes import router as delivery_router  # type: ignore[no-redef]

app.include_router(delivery_router)

try:
    from .retest_routes import router as retest_router
except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
    from retest_routes import router as retest_router  # type: ignore[no-redef]

app.include_router(retest_router)

try:
    from .evidence_routes import router as evidence_router
except ImportError:  # pragma: no cover
    from evidence_routes import router as evidence_router  # type: ignore[no-redef]

app.include_router(evidence_router)

try:
    from .question_routes import router as question_router
except ImportError:  # pragma: no cover
    from question_routes import router as question_router  # type: ignore[no-redef]

app.include_router(question_router)

try:
    from .page_audit_routes import router as page_audit_router
except ImportError:  # pragma: no cover
    from page_audit_routes import router as page_audit_router  # type: ignore[no-redef]

app.include_router(page_audit_router)

try:
    from .citation_support_routes import router as citation_support_router
except ImportError:  # pragma: no cover
    from citation_support_routes import router as citation_support_router  # type: ignore[no-redef]

app.include_router(citation_support_router)

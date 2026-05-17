from __future__ import annotations

from datetime import date
import os
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
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

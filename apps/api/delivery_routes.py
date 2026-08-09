from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import re
from typing import Any, Literal, Mapping, Optional, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import sha256_text

try:
    from . import knowledge_routes
    from .operation_guard import MySQLOperationGuard, OperationAuditRecord
except ImportError:  # pragma: no cover
    import knowledge_routes  # type: ignore[no-redef]
    from operation_guard import MySQLOperationGuard, OperationAuditRecord  # type: ignore[no-redef]


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["delivery-governance"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {"trace_id": trace_id or f"trc_{uuid4().hex[:16]}", "request_id": f"req_{uuid4().hex[:16]}"}


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    if not authenticated_actor:
        raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})
    return authenticated_actor


def require_delivery_admin(permission_header: Optional[str]) -> None:
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return
    required = os.getenv("AIRANK_DELIVERY_ADMIN_PERMISSION", "airank:delivery:admin").strip()
    granted = {item.strip() for item in (permission_header or "").split(",") if item.strip()}
    namespace = required.rsplit(":", 1)[0]
    if not {required, "*", "*:*:*", f"{namespace}:*"}.intersection(granted):
        raise StarletteHTTPException(
            status_code=403,
            detail={"code": "AUTH_PERMISSION_FORBIDDEN", "details": {"required_permission": required}},
        )


class RiskFinding(BaseModel):
    code: str
    severity: Literal["low", "medium", "high"]
    matched_text: str
    message: str


def scan_content_risk(body_md: str) -> list[RiskFinding]:
    rules = (
        ("guaranteed_ai_recommendation", "high", r"(?:保证|确保|必然).{0,8}(?:推荐|收录|引用)", "不得承诺大模型必然推荐、收录或引用。"),
        ("absolute_ranking_claim", "high", r"(?:行业|全国|全球).{0,6}(?:第一|唯一|最强)", "绝对排名声明必须有独立同口径证据。"),
        ("unsupported_superlative", "medium", r"(?:最佳|领先|顶级|首屈一指)", "主观最高级表述需要额外证据或删除。"),
        ("competitor_attack", "high", r"(?:竞品|竞争对手).{0,12}(?:欺骗|最差|不可信)", "竞品贬损存在商业与合规风险。"),
        ("embedded_active_content", "high", r"(?:<\s*(?:script|iframe|object|embed|style)\b|\bon\w+\s*=|javascript\s*:)", "内容包含可执行或嵌入式代码，发布前必须删除。"),
    )
    findings = []
    for code, severity, pattern, message in rules:
        match = re.search(pattern, body_md, flags=re.IGNORECASE)
        if match:
            findings.append(RiskFinding(code=code, severity=severity, matched_text=match.group(0)[:120], message=message))
    return findings


class ContentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approved", "rejected", "changes_requested"]
    reviewed_by: str = Field(min_length=1, max_length=64)
    review_note: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    override_reason: Optional[str] = Field(default=None, min_length=10, max_length=2000)


class ContentReviewData(BaseModel):
    review_id: str
    tenant_id: str
    project_id: str
    asset_id: str
    content_sha256: str
    action: Literal["approved", "rejected", "changes_requested"]
    fact_check_status: Literal["passed", "failed"]
    risk_level: Literal["low", "medium", "high"]
    risk_findings: list[RiskFinding]
    override_reason: Optional[str] = None
    reviewed_by: str
    reviewed_at: datetime


class ContentReviewResponse(BaseModel):
    data: ContentReviewData
    meta: dict[str, str]


class PublishPackageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["export", "wordpress", "http"]
    idempotency_key: str = Field(min_length=8, max_length=160)
    requested_by: str = Field(min_length=1, max_length=64)
    target_endpoint: Optional[str] = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def external_channel_requires_endpoint(self) -> "PublishPackageCreateRequest":
        if self.channel in {"wordpress", "http"} and not self.target_endpoint:
            raise ValueError("target_endpoint is required for wordpress/http")
        if self.target_endpoint:
            parsed = urlparse(self.target_endpoint)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("target_endpoint must be an HTTPS URL without embedded credentials")
        return self


class PublishMutationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["update", "withdraw"]
    idempotency_key: str = Field(min_length=8, max_length=160)
    reason: str = Field(min_length=10, max_length=1000)
    requested_by: str = Field(min_length=1, max_length=128)
    replacement_asset_id: Optional[str] = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def replacement_matches_action(self) -> "PublishMutationCreateRequest":
        if self.action == "update" and not self.replacement_asset_id:
            raise ValueError("replacement_asset_id is required for update")
        if self.action == "withdraw" and self.replacement_asset_id:
            raise ValueError("replacement_asset_id is not allowed for withdraw")
        return self


class PublishPackageData(BaseModel):
    package_id: str
    tenant_id: str
    project_id: str
    asset_id: str
    snapshot_id: str
    content_review_id: str
    channel: Literal["export", "wordpress", "http"]
    status: Literal["packaged", "queued", "publishing", "delivered", "failed", "outcome_unknown", "published", "superseded", "withdrawn"]
    implementation_status: Literal["ready", "partial"]
    idempotency_key: str
    content_sha256: str
    published_url: Optional[str] = None
    created_at: datetime
    publication_action: Literal["publish", "update", "withdraw"] = "publish"
    target_package_id: Optional[str] = None
    action_reason: Optional[str] = None
    requested_by: Optional[str] = None
    idempotent_replay: bool = False


class PublishPackageResponse(BaseModel):
    data: PublishPackageData
    meta: dict[str, str]


class PublishPackageListResponse(BaseModel):
    data: list[PublishPackageData]
    meta: dict[str, str]


class PublishAttemptData(BaseModel):
    attempt_id: str
    package_id: str
    attempt_number: int
    channel: str
    status: Literal["running", "succeeded", "failed", "outcome_unknown"]
    request_sha256: str
    operation_id: Optional[str] = None
    operation_state: Optional[Literal["claimed", "external_started", "succeeded", "failed"]] = None
    external_effect_started: bool = False
    reconciliation_required: bool = False
    reconciliation_case_id: Optional[str] = None
    response_status: Optional[int] = None
    response_sha256: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class PublishAttemptListResponse(BaseModel):
    data: list[PublishAttemptData]
    meta: dict[str, str]


class PublishOperationEventData(BaseModel):
    event_sequence: int
    event_type: str
    from_state: Optional[str] = None
    to_state: Literal["claimed", "external_started", "succeeded", "failed"]
    request_sha256: str
    previous_event_sha256: Optional[str] = None
    event_sha256: str
    actor: str
    trace_id: str
    created_at: datetime


class PublishOperationData(BaseModel):
    contract_version: Literal["airank.operation-guard.v1"] = "airank.operation-guard.v1"
    operation_id: str
    operation_type: Literal["publisher.publish"] = "publisher.publish"
    package_id: str
    state: Literal["claimed", "external_started", "succeeded", "failed"]
    external_effect_started: bool
    request_sha256: str
    error_code: Optional[str] = None
    created_by: str
    trace_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    reconciliation_required: bool
    replay_status: Literal["available", "in_progress", "forbidden_unknown", "forbidden_failed"]
    response_published_url: Optional[str] = None
    response_status: Optional[int] = None
    response_sha256: Optional[str] = None
    events: list[PublishOperationEventData]


class PublishOperationResponse(BaseModel):
    data: PublishOperationData
    meta: dict[str, str]


class PublishEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    published_url: str = Field(min_length=1, max_length=2048)
    baseline_run_id: str = Field(min_length=1, max_length=64)
    recorded_by: str = Field(min_length=1, max_length=64)
    screenshot_ref_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    screenshot_sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("published_url")
    @classmethod
    def url_must_be_http(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("published_url must be an absolute http(s) URL")
        return value

    @model_validator(mode="after")
    def screenshot_reference_requires_hash(self) -> "PublishEvidenceRequest":
        if bool(self.screenshot_ref_id) != bool(self.screenshot_sha256):
            raise ValueError("screenshot_ref_id and screenshot_sha256 must be provided together")
        return self


class PublishExportData(BaseModel):
    package_id: str
    snapshot_id: str
    title: str
    body_md: str
    content_sha256: str
    manifest: dict[str, Any]


class PublishExportResponse(BaseModel):
    data: PublishExportData
    meta: dict[str, str]


class DeliveryRepository(Protocol):
    def review_content(self, tenant_id: str, asset_id: str, payload: ContentReviewRequest) -> ContentReviewData: ...
    def create_package(self, tenant_id: str, asset_id: str, payload: PublishPackageCreateRequest) -> PublishPackageData: ...
    def create_mutation(self, tenant_id: str, package_id: str, payload: PublishMutationCreateRequest) -> PublishPackageData: ...
    def list_packages(self, tenant_id: str, project_id: str) -> list[PublishPackageData]: ...
    def list_attempts(self, tenant_id: str, package_id: str) -> list[PublishAttemptData]: ...
    def get_operation(self, tenant_id: str, operation_id: str) -> PublishOperationData: ...
    def get_export(self, tenant_id: str, package_id: str) -> PublishExportData: ...
    def mark_published(self, tenant_id: str, package_id: str, payload: PublishEvidenceRequest) -> PublishPackageData: ...


class InMemoryDeliveryRepository:
    def __init__(self) -> None:
        self.reviews: dict[tuple[str, str], ContentReviewData] = {}
        self.packages: dict[tuple[str, str], PublishPackageData] = {}
        self.snapshots: dict[tuple[str, str], PublishExportData] = {}
        self.idempotency: dict[tuple[str, str], str] = {}
        self.package_endpoints: dict[tuple[str, str], Optional[str]] = {}
        self.retest_windows: dict[tuple[str, str], dict[str, Any]] = {}

    def _asset(self, tenant_id: str, asset_id: str) -> Any:
        repository = knowledge_routes.KNOWLEDGE_REPOSITORY
        assets = getattr(repository, "content_assets", {})
        asset = assets.get((tenant_id, asset_id))
        if asset is None:
            raise _not_found("ASSET_NOT_FOUND", {"asset_id": asset_id})
        return asset

    def review_content(self, tenant_id: str, asset_id: str, payload: ContentReviewRequest) -> ContentReviewData:
        asset = self._asset(tenant_id, asset_id)
        findings = scan_content_risk(f"{asset.title}\n{asset.body_md}")
        risk_level = _risk_level(findings)
        support_links = getattr(knowledge_routes.KNOWLEDGE_REPOSITORY, "claim_support_links", {})
        supported_assertions = {
            support_links.get((tenant_id, support_id))
            for support_id in asset.claim_support_ids
        }
        fact_check_status = "passed" if (
            bool(asset.claim_assertion_ids)
            and set(asset.claim_assertion_ids) == supported_assertions
        ) else "failed"
        _assert_review_allowed(payload, fact_check_status, risk_level)
        data = ContentReviewData(review_id=f"review_{uuid4().hex[:12]}", tenant_id=tenant_id, project_id=asset.project_id, asset_id=asset_id, content_sha256=sha256_text(asset.body_md), action=payload.action, fact_check_status=fact_check_status, risk_level=risk_level, risk_findings=findings, override_reason=payload.override_reason, reviewed_by=payload.reviewed_by, reviewed_at=utc_now())
        self.reviews[(tenant_id, data.review_id)] = data
        knowledge_routes.KNOWLEDGE_REPOSITORY.content_assets[(tenant_id, asset_id)] = asset.model_copy(update={"status": "approved" if payload.action == "approved" else payload.action})
        return data

    def create_package(self, tenant_id: str, asset_id: str, payload: PublishPackageCreateRequest) -> PublishPackageData:
        replay_key = (tenant_id, payload.idempotency_key)
        if replay_key in self.idempotency:
            package = self.packages[(tenant_id, self.idempotency[replay_key])]
            return package.model_copy(update={"idempotent_replay": True})
        asset = self._asset(tenant_id, asset_id)
        reviews = [item for (item_tenant, _), item in self.reviews.items() if item_tenant == tenant_id and item.asset_id == asset_id and item.action == "approved" and item.content_sha256 == sha256_text(asset.body_md)]
        if not reviews:
            raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_REVIEW_REQUIRED", "details": {"asset_id": asset_id}})
        review = sorted(reviews, key=lambda item: item.reviewed_at)[-1]
        package_id = f"package_{uuid4().hex[:12]}"
        snapshot_id = f"publish_snapshot_{uuid4().hex[:12]}"
        created_at = utc_now()
        manifest = _snapshot_manifest(asset, review, payload)
        self.snapshots[(tenant_id, snapshot_id)] = PublishExportData(package_id=package_id, snapshot_id=snapshot_id, title=asset.title, body_md=asset.body_md, content_sha256=sha256_text(asset.body_md), manifest=manifest)
        data = PublishPackageData(package_id=package_id, tenant_id=tenant_id, project_id=asset.project_id, asset_id=asset_id, snapshot_id=snapshot_id, content_review_id=review.review_id, channel=payload.channel, status="packaged" if payload.channel == "export" else "queued", implementation_status="ready" if payload.channel == "export" else "partial", idempotency_key=payload.idempotency_key, content_sha256=sha256_text(asset.body_md), created_at=created_at)
        self.packages[(tenant_id, package_id)] = data
        self.package_endpoints[(tenant_id, package_id)] = payload.target_endpoint
        self.idempotency[replay_key] = package_id
        return data

    def create_mutation(self, tenant_id: str, package_id: str, payload: PublishMutationCreateRequest) -> PublishPackageData:
        replay_key = (tenant_id, payload.idempotency_key)
        if replay_key in self.idempotency:
            package = self.packages[(tenant_id, self.idempotency[replay_key])]
            if package.publication_action != payload.action or package.target_package_id != package_id:
                raise StarletteHTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"})
            return package.model_copy(update={"idempotent_replay": True})
        target = self.packages.get((tenant_id, package_id))
        if target is None:
            raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
        if target.status != "published":
            raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_STATE_CONFLICT", "details": {"package_id": package_id, "status": target.status}})
        if target.channel == "export":
            raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_CHANNEL_UNSUPPORTED", "details": {"channel": target.channel}})
        active_mutation = next((item for (item_tenant, _), item in self.packages.items() if item_tenant == tenant_id and item.target_package_id == package_id and item.publication_action in {"update", "withdraw"} and item.status in {"queued", "publishing", "delivered", "outcome_unknown"}), None)
        if active_mutation is not None:
            raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_STATE_CONFLICT", "details": {"package_id": package_id, "active_mutation_package_id": active_mutation.package_id, "active_mutation_status": active_mutation.status}})
        endpoint = self.package_endpoints.get((tenant_id, package_id))
        if not endpoint:
            raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_INVALID", "details": {"reason": "target_endpoint_missing"}})
        if payload.action == "update":
            created = self.create_package(
                tenant_id,
                str(payload.replacement_asset_id),
                PublishPackageCreateRequest(
                    channel=target.channel,
                    idempotency_key=payload.idempotency_key,
                    requested_by=payload.requested_by,
                    target_endpoint=endpoint,
                ),
            )
            updated = created.model_copy(update={"publication_action": "update", "target_package_id": package_id, "action_reason": payload.reason, "requested_by": payload.requested_by})
        else:
            mutation_package_id = f"package_{uuid4().hex[:12]}"
            source_export = self.snapshots[(tenant_id, target.snapshot_id)]
            snapshot_id = f"publish_snapshot_{uuid4().hex[:12]}"
            manifest = dict(source_export.manifest)
            manifest.update({"contract_version": "airank.publish-snapshot.v3", "publication_action": "withdraw", "target_package_id": package_id, "action_reason": payload.reason, "requested_by": payload.requested_by})
            self.snapshots[(tenant_id, snapshot_id)] = source_export.model_copy(update={"package_id": mutation_package_id, "snapshot_id": snapshot_id, "manifest": manifest})
            updated = PublishPackageData(
                package_id=mutation_package_id,
                tenant_id=tenant_id,
                project_id=target.project_id,
                asset_id=target.asset_id,
                snapshot_id=snapshot_id,
                content_review_id=target.content_review_id,
                channel=target.channel,
                status="queued",
                implementation_status="partial",
                idempotency_key=payload.idempotency_key,
                content_sha256=target.content_sha256,
                published_url=target.published_url,
                created_at=utc_now(),
                publication_action="withdraw",
                target_package_id=package_id,
                action_reason=payload.reason,
                requested_by=payload.requested_by,
            )
        self.packages[(tenant_id, updated.package_id)] = updated
        self.package_endpoints[(tenant_id, updated.package_id)] = endpoint
        self.idempotency[replay_key] = updated.package_id
        return updated

    def list_packages(self, tenant_id: str, project_id: str) -> list[PublishPackageData]:
        return [
            package
            for (item_tenant, _), package in self.packages.items()
            if item_tenant == tenant_id and package.project_id == project_id
        ]

    def list_attempts(self, tenant_id: str, package_id: str) -> list[PublishAttemptData]:
        if (tenant_id, package_id) not in self.packages:
            raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
        return []

    def get_operation(self, tenant_id: str, operation_id: str) -> PublishOperationData:
        del tenant_id
        raise _not_found("OPERATION_NOT_FOUND", {"operation_id": operation_id})

    def get_export(self, tenant_id: str, package_id: str) -> PublishExportData:
        package = self.packages.get((tenant_id, package_id))
        if package is None:
            raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
        return self.snapshots[(tenant_id, package.snapshot_id)]

    def mark_published(self, tenant_id: str, package_id: str, payload: PublishEvidenceRequest) -> PublishPackageData:
        package = self.packages.get((tenant_id, package_id))
        if package is None:
            raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
        if package.publication_action == "withdraw" or package.status in {"withdrawn", "superseded"}:
            raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_STATE_CONFLICT", "details": {"package_id": package_id, "status": package.status}})
        if package.status == "published":
            if package.published_url != payload.published_url:
                raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"package_id": package_id, "published_url": package.published_url}})
            return package.model_copy(update={"idempotent_replay": True})
        required_status = "packaged" if package.channel == "export" else "delivered"
        if package.status != required_status:
            raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_DELIVERY_RECEIPT_REQUIRED", "details": {"package_id": package_id, "status": package.status, "required_status": required_status}})
        updated = package.model_copy(update={"status": "published", "published_url": payload.published_url})
        self.packages[(tenant_id, package_id)] = updated
        published_at = utc_now()
        for label, days in (("T0", 0), ("T+7", 7), ("T+14", 14), ("T+30", 30)):
            window_id = f"window_{uuid4().hex[:12]}"
            self.retest_windows[(tenant_id, window_id)] = {
                "window_id": window_id,
                "tenant_id": tenant_id,
                "project_id": package.project_id,
                "package_id": package_id,
                "baseline_run_id": payload.baseline_run_id,
                "window_label": label,
                "due_at": published_at + timedelta(days=days),
                "status": "scheduled",
                "compare_run_id": None,
                "result": None,
                "completed_at": None,
            }
        return updated


class MySQLDeliveryRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.operation_guard = MySQLOperationGuard(database_url)

    def review_content(self, tenant_id: str, asset_id: str, payload: ContentReviewRequest) -> ContentReviewData:
        reviewed_at = utc_now()
        with self.engine.begin() as conn:
            asset = conn.execute(text("SELECT id, project_id, title, body_md, content_sha256 FROM airank_content_assets WHERE tenant_id=:tenant_id AND id=:asset_id AND deleted_at IS NULL FOR UPDATE"), {"tenant_id": tenant_id, "asset_id": asset_id}).mappings().first()
            if asset is None:
                raise _not_found("ASSET_NOT_FOUND", {"asset_id": asset_id})
            body_md = asset["body_md"] or ""
            content_sha256 = sha256_text(body_md)
            blueprint_integrity = not asset["content_sha256"] or asset["content_sha256"] == content_sha256
            claim_counts = conn.execute(text("""
                SELECT COUNT(*) AS assertion_count,
                       COALESCE(SUM(CASE WHEN assertion_status='verified' AND support_count > 0 THEN 1 ELSE 0 END), 0)
                         AS supported_assertion_count,
                       COALESCE(SUM(contradiction_count), 0) AS contradiction_count
                FROM (
                  SELECT a.id, a.status AS assertion_status,
                         SUM(CASE WHEN s.support_type='supports' THEN 1 ELSE 0 END)
                           AS support_count,
                         SUM(CASE WHEN s.support_type='contradicts' THEN 1 ELSE 0 END)
                           AS contradiction_count
                  FROM airank_claim_assertions a
                  LEFT JOIN airank_claim_supports s
                    ON s.assertion_id=a.id AND s.tenant_id=a.tenant_id
                  WHERE a.tenant_id=:tenant_id AND a.asset_id=:asset_id
                  GROUP BY a.id, a.status
                ) assertion_support
            """), {"tenant_id": tenant_id, "asset_id": asset_id}).mappings().one()
            assertion_count = int(claim_counts["assertion_count"] or 0)
            fact_check_status = "passed" if (
                blueprint_integrity
                and assertion_count > 0
                and int(claim_counts["supported_assertion_count"] or 0) == assertion_count
                and int(claim_counts["contradiction_count"] or 0) == 0
            ) else "failed"
            findings = scan_content_risk(f"{asset['title']}\n{body_md}")
            risk_level = _risk_level(findings)
            _assert_review_allowed(payload, fact_check_status, risk_level)
            review_id = f"review_{uuid4().hex[:12]}"
            conn.execute(text("""
                INSERT INTO airank_content_reviews (
                  id, tenant_id, project_id, asset_id, content_sha256, action,
                  fact_check_status, risk_level, risk_findings_json, override_reason,
                  reviewed_by, review_note, reviewed_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :asset_id, :content_sha256, :action,
                  :fact_check_status, :risk_level, :risk_findings_json, :override_reason,
                  :reviewed_by, :review_note, :reviewed_at
                )
            """), {"id": review_id, "tenant_id": tenant_id, "project_id": asset["project_id"], "asset_id": asset_id, "content_sha256": content_sha256, "action": payload.action, "fact_check_status": fact_check_status, "risk_level": risk_level, "risk_findings_json": json.dumps([item.model_dump() for item in findings], ensure_ascii=False), "override_reason": payload.override_reason, "reviewed_by": payload.reviewed_by, "review_note": payload.review_note, "reviewed_at": reviewed_at})
            asset_status = "approved" if payload.action == "approved" else payload.action
            conn.execute(text("UPDATE airank_content_assets SET content_sha256=:content_sha256, status=:status, reviewed_by=:reviewed_by, reviewed_at=:reviewed_at, updated_at=:reviewed_at WHERE tenant_id=:tenant_id AND id=:asset_id"), {"content_sha256": content_sha256, "status": asset_status, "reviewed_by": payload.reviewed_by, "reviewed_at": reviewed_at, "tenant_id": tenant_id, "asset_id": asset_id})
        return ContentReviewData(review_id=review_id, tenant_id=tenant_id, project_id=asset["project_id"], asset_id=asset_id, content_sha256=content_sha256, action=payload.action, fact_check_status=fact_check_status, risk_level=risk_level, risk_findings=findings, override_reason=payload.override_reason, reviewed_by=payload.reviewed_by, reviewed_at=reviewed_at)

    @staticmethod
    def _package_data(row: Mapping[str, Any], *, replay: bool = False) -> PublishPackageData:
        metadata = row["metadata_json"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata or "{}")
        status = "queued" if row["status"] in {"draft", "packaged", "queued"} and row["channel"] != "export" else row["status"]
        if row["channel"] == "export" and status == "draft":
            status = "packaged"
        implementation_status = "ready" if row["channel"] == "export" or metadata.get("implementation_status") == "ready" else "partial"
        return PublishPackageData(
            package_id=row["id"],
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            asset_id=row["asset_id"],
            snapshot_id=row["snapshot_id"],
            content_review_id=row["content_review_id"],
            channel=row["channel"],
            status=status,
            implementation_status=implementation_status,
            idempotency_key=row["idempotency_key"],
            content_sha256=metadata.get("content_sha256", ""),
            published_url=row["published_url"],
            created_at=row["created_at"],
            publication_action=str(row.get("publication_action") or metadata.get("publication_action") or "publish"),
            target_package_id=row.get("target_package_id") or metadata.get("target_package_id"),
            action_reason=row.get("action_reason") or metadata.get("action_reason"),
            requested_by=row.get("requested_by") or metadata.get("requested_by"),
            idempotent_replay=replay,
        )

    def create_package(self, tenant_id: str, asset_id: str, payload: PublishPackageCreateRequest) -> PublishPackageData:
        created_at = utc_now()
        with self.engine.begin() as conn:
            replay = conn.execute(text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key AND deleted_at IS NULL"), {"tenant_id": tenant_id, "idempotency_key": payload.idempotency_key}).mappings().first()
            if replay is not None:
                return self._package_data(replay, replay=True)
            asset = conn.execute(text("SELECT id, project_id, asset_type, title, body_md, content_sha256, metadata_json FROM airank_content_assets WHERE tenant_id=:tenant_id AND id=:asset_id AND deleted_at IS NULL FOR UPDATE"), {"tenant_id": tenant_id, "asset_id": asset_id}).mappings().first()
            if asset is None:
                raise _not_found("ASSET_NOT_FOUND", {"asset_id": asset_id})
            content_sha256 = sha256_text(asset["body_md"] or "")
            review = conn.execute(text("""
                SELECT * FROM airank_content_reviews
                WHERE tenant_id=:tenant_id AND asset_id=:asset_id AND action='approved'
                  AND fact_check_status='passed' AND content_sha256=:content_sha256
                ORDER BY reviewed_at DESC LIMIT 1
            """), {"tenant_id": tenant_id, "asset_id": asset_id, "content_sha256": content_sha256}).mappings().first()
            if review is None:
                raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_REVIEW_REQUIRED", "details": {"asset_id": asset_id, "content_sha256": content_sha256}})
            package_id = f"package_{uuid4().hex[:12]}"
            snapshot_id = f"publish_snapshot_{uuid4().hex[:12]}"
            snapshot_version = int(conn.execute(text("SELECT COALESCE(MAX(snapshot_version),0) FROM airank_publish_snapshots WHERE tenant_id=:tenant_id AND asset_id=:asset_id"), {"tenant_id": tenant_id, "asset_id": asset_id}).scalar_one()) + 1
            manifest = _snapshot_manifest(asset, review, payload)
            conn.execute(text("""
                INSERT INTO airank_publish_snapshots (
                  id, tenant_id, project_id, asset_id, content_review_id,
                  snapshot_version, title, body_md, content_sha256, manifest_json,
                  created_by, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :asset_id, :content_review_id,
                  :snapshot_version, :title, :body_md, :content_sha256, :manifest_json,
                  :created_by, :created_at
                )
            """), {"id": snapshot_id, "tenant_id": tenant_id, "project_id": asset["project_id"], "asset_id": asset_id, "content_review_id": review["id"], "snapshot_version": snapshot_version, "title": asset["title"], "body_md": asset["body_md"], "content_sha256": content_sha256, "manifest_json": json.dumps(manifest, ensure_ascii=False), "created_by": payload.requested_by, "created_at": created_at})
            package_status = "packaged" if payload.channel == "export" else "draft"
            conn.execute(text("""
                INSERT INTO airank_publish_packages (
                  id, tenant_id, project_id, asset_id, snapshot_id, content_review_id,
                  idempotency_key, package_type, channel, status, metadata_json,
                  publication_action, requested_by, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :asset_id, :snapshot_id, :content_review_id,
                  :idempotency_key, 'content_asset', :channel, :status, :metadata_json,
                  'publish', :requested_by, :created_at, :created_at
                )
            """), {"id": package_id, "tenant_id": tenant_id, "project_id": asset["project_id"], "asset_id": asset_id, "snapshot_id": snapshot_id, "content_review_id": review["id"], "idempotency_key": payload.idempotency_key, "channel": payload.channel, "status": package_status, "metadata_json": json.dumps({"content_sha256": content_sha256, "target_endpoint": payload.target_endpoint, "implementation_status": "ready" if payload.channel == "export" else "partial", "publication_action": "publish", "requested_by": payload.requested_by}, ensure_ascii=False), "requested_by": payload.requested_by, "created_at": created_at})
            if payload.channel != "export":
                conn.execute(text("""
                    INSERT INTO airank_async_jobs (
                      id, tenant_id, project_id, job_type, status, priority,
                      scheduled_at, payload_json, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'publish.package', 'queued', 100,
                      :scheduled_at, :payload_json, :created_at, :created_at
                    )
                """), {"id": f"job_{uuid4().hex[:12]}", "tenant_id": tenant_id, "project_id": asset["project_id"], "scheduled_at": created_at, "payload_json": json.dumps({"package_id": package_id, "snapshot_id": snapshot_id, "channel": payload.channel, "target_endpoint": payload.target_endpoint}, ensure_ascii=False), "created_at": created_at})
            row = conn.execute(text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND id=:package_id"), {"tenant_id": tenant_id, "package_id": package_id}).mappings().one()
        return self._package_data(row)

    def create_mutation(self, tenant_id: str, package_id: str, payload: PublishMutationCreateRequest) -> PublishPackageData:
        created_at = utc_now()
        request_sha256 = sha256_text(json.dumps({
            "action": payload.action,
            "target_package_id": package_id,
            "replacement_asset_id": payload.replacement_asset_id,
            "reason": payload.reason,
            "requested_by": payload.requested_by,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        with self.engine.begin() as conn:
            replay = conn.execute(
                text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key AND deleted_at IS NULL"),
                {"tenant_id": tenant_id, "idempotency_key": payload.idempotency_key},
            ).mappings().first()
            if replay is not None:
                replay_metadata = replay["metadata_json"] if isinstance(replay["metadata_json"], dict) else json.loads(replay["metadata_json"] or "{}")
                if replay_metadata.get("mutation_request_sha256") != request_sha256:
                    raise StarletteHTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                return self._package_data(replay, replay=True)
            target = conn.execute(text("""
                SELECT p.*, s.title AS snapshot_title, s.body_md AS snapshot_body_md,
                       s.content_sha256 AS snapshot_content_sha256,
                       s.manifest_json AS snapshot_manifest_json
                FROM airank_publish_packages p
                JOIN airank_publish_snapshots s
                  ON s.id=p.snapshot_id AND s.tenant_id=p.tenant_id
                WHERE p.tenant_id=:tenant_id AND p.id=:package_id
                  AND p.deleted_at IS NULL
                FOR UPDATE
            """), {"tenant_id": tenant_id, "package_id": package_id}).mappings().first()
            if target is None:
                raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
            replay_after_lock = conn.execute(
                text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key AND deleted_at IS NULL FOR UPDATE"),
                {"tenant_id": tenant_id, "idempotency_key": payload.idempotency_key},
            ).mappings().first()
            if replay_after_lock is not None:
                replay_metadata = replay_after_lock["metadata_json"] if isinstance(replay_after_lock["metadata_json"], dict) else json.loads(replay_after_lock["metadata_json"] or "{}")
                if replay_metadata.get("mutation_request_sha256") != request_sha256:
                    raise StarletteHTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"})
                return self._package_data(replay_after_lock, replay=True)
            if target["status"] != "published":
                raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_STATE_CONFLICT", "details": {"package_id": package_id, "status": target["status"], "required_status": "published"}})
            if target["channel"] not in {"wordpress", "http"}:
                raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_CHANNEL_UNSUPPORTED", "details": {"channel": target["channel"]}})
            active_mutation = conn.execute(text("""
                SELECT id, status FROM airank_publish_packages
                WHERE tenant_id=:tenant_id AND target_package_id=:target_package_id
                  AND publication_action IN ('update','withdraw')
                  AND status IN ('draft','queued','publishing','delivered','outcome_unknown')
                  AND deleted_at IS NULL
                ORDER BY created_at DESC LIMIT 1
                FOR UPDATE
            """), {"tenant_id": tenant_id, "target_package_id": package_id}).mappings().first()
            if active_mutation is not None:
                raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_STATE_CONFLICT", "details": {"package_id": package_id, "active_mutation_package_id": active_mutation["id"], "active_mutation_status": active_mutation["status"]}})
            target_metadata = target["metadata_json"] if isinstance(target["metadata_json"], dict) else json.loads(target["metadata_json"] or "{}")
            target_endpoint = str(target_metadata.get("target_endpoint") or "")
            if not target_endpoint:
                raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_INVALID", "details": {"reason": "target_endpoint_missing"}})
            receipt = target_metadata.get("delivery_receipt") if isinstance(target_metadata.get("delivery_receipt"), Mapping) else {}
            target_remote_id = str(receipt.get("remote_id") or "").strip()
            if target["channel"] == "wordpress" and not target_remote_id:
                raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_REMOTE_ID_MISSING", "details": {"package_id": package_id}})

            if payload.action == "update":
                asset = conn.execute(text("""
                    SELECT id, project_id, asset_type, title, body_md, content_sha256, metadata_json
                    FROM airank_content_assets
                    WHERE tenant_id=:tenant_id AND id=:asset_id AND deleted_at IS NULL
                    FOR UPDATE
                """), {"tenant_id": tenant_id, "asset_id": payload.replacement_asset_id}).mappings().first()
                if asset is None:
                    raise _not_found("ASSET_NOT_FOUND", {"asset_id": payload.replacement_asset_id})
                if asset["project_id"] != target["project_id"]:
                    raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_INVALID", "details": {"reason": "replacement_asset_project_mismatch"}})
                content_sha256 = sha256_text(asset["body_md"] or "")
                review = conn.execute(text("""
                    SELECT * FROM airank_content_reviews
                    WHERE tenant_id=:tenant_id AND asset_id=:asset_id AND action='approved'
                      AND fact_check_status='passed' AND content_sha256=:content_sha256
                    ORDER BY reviewed_at DESC LIMIT 1
                """), {"tenant_id": tenant_id, "asset_id": payload.replacement_asset_id, "content_sha256": content_sha256}).mappings().first()
                if review is None:
                    raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_REVIEW_REQUIRED", "details": {"asset_id": payload.replacement_asset_id, "content_sha256": content_sha256}})
                asset_id = str(asset["id"])
                content_review_id = str(review["id"])
                title = str(asset["title"])
                body_md = str(asset["body_md"] or "")
                manifest = _snapshot_manifest(
                    asset,
                    review,
                    PublishPackageCreateRequest(
                        channel=target["channel"],
                        idempotency_key=payload.idempotency_key,
                        requested_by=payload.requested_by,
                        target_endpoint=target_endpoint,
                    ),
                )
            else:
                asset_id = str(target["asset_id"])
                content_review_id = str(target["content_review_id"])
                title = str(target["snapshot_title"])
                body_md = str(target["snapshot_body_md"] or "")
                content_sha256 = str(target["snapshot_content_sha256"])
                manifest = target["snapshot_manifest_json"] if isinstance(target["snapshot_manifest_json"], dict) else json.loads(target["snapshot_manifest_json"] or "{}")

            manifest = dict(manifest)
            manifest.update({
                "contract_version": "airank.publish-snapshot.v3",
                "publication_action": payload.action,
                "target_package_id": package_id,
                "target_content_sha256": str(target["snapshot_content_sha256"]),
                "action_reason": payload.reason,
                "requested_by": payload.requested_by,
                "immutable": True,
            })
            mutation_package_id = f"package_{uuid4().hex[:12]}"
            snapshot_id = f"publish_snapshot_{uuid4().hex[:12]}"
            snapshot_version = int(conn.execute(text("SELECT COALESCE(MAX(snapshot_version),0) FROM airank_publish_snapshots WHERE tenant_id=:tenant_id AND asset_id=:asset_id"), {"tenant_id": tenant_id, "asset_id": asset_id}).scalar_one()) + 1
            conn.execute(text("""
                INSERT INTO airank_publish_snapshots (
                  id, tenant_id, project_id, asset_id, content_review_id,
                  snapshot_version, title, body_md, content_sha256, manifest_json,
                  created_by, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :asset_id, :content_review_id,
                  :snapshot_version, :title, :body_md, :content_sha256, :manifest_json,
                  :created_by, :created_at
                )
            """), {"id": snapshot_id, "tenant_id": tenant_id, "project_id": target["project_id"], "asset_id": asset_id, "content_review_id": content_review_id, "snapshot_version": snapshot_version, "title": title, "body_md": body_md, "content_sha256": content_sha256, "manifest_json": json.dumps(manifest, ensure_ascii=False), "created_by": payload.requested_by, "created_at": created_at})
            mutation_metadata = {
                "content_sha256": content_sha256,
                "target_endpoint": target_endpoint,
                "implementation_status": "partial",
                "publication_action": payload.action,
                "target_package_id": package_id,
                "target_remote_id": target_remote_id or None,
                "target_published_url": target["published_url"],
                "action_reason": payload.reason,
                "requested_by": payload.requested_by,
                "mutation_request_sha256": request_sha256,
            }
            conn.execute(text("""
                INSERT INTO airank_publish_packages (
                  id, tenant_id, project_id, asset_id, snapshot_id, content_review_id,
                  idempotency_key, package_type, channel, status, metadata_json,
                  publication_action, target_package_id, action_reason, requested_by,
                  published_url, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :asset_id, :snapshot_id, :content_review_id,
                  :idempotency_key, 'content_asset', :channel, 'draft', :metadata_json,
                  :publication_action, :target_package_id, :action_reason, :requested_by,
                  :published_url, :created_at, :created_at
                )
            """), {"id": mutation_package_id, "tenant_id": tenant_id, "project_id": target["project_id"], "asset_id": asset_id, "snapshot_id": snapshot_id, "content_review_id": content_review_id, "idempotency_key": payload.idempotency_key, "channel": target["channel"], "metadata_json": json.dumps(mutation_metadata, ensure_ascii=False), "publication_action": payload.action, "target_package_id": package_id, "action_reason": payload.reason, "requested_by": payload.requested_by, "published_url": target["published_url"], "created_at": created_at})
            conn.execute(text("""
                INSERT INTO airank_async_jobs (
                  id, tenant_id, project_id, job_type, status, priority,
                  scheduled_at, payload_json, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, 'publish.package', 'queued', 100,
                  :scheduled_at, :payload_json, :created_at, :created_at
                )
            """), {"id": f"job_{uuid4().hex[:12]}", "tenant_id": tenant_id, "project_id": target["project_id"], "scheduled_at": created_at, "payload_json": json.dumps({"package_id": mutation_package_id, "snapshot_id": snapshot_id, "channel": target["channel"], "publication_action": payload.action, "target_package_id": package_id}, ensure_ascii=False), "created_at": created_at})
            row = conn.execute(text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND id=:package_id"), {"tenant_id": tenant_id, "package_id": mutation_package_id}).mappings().one()
        return self._package_data(row)

    def list_packages(self, tenant_id: str, project_id: str) -> list[PublishPackageData]:
        with self.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT * FROM airank_publish_packages
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND channel IN ('export','wordpress','http')
                  AND deleted_at IS NULL
                ORDER BY created_at DESC, id DESC
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        return [self._package_data(row) for row in rows]

    def list_attempts(self, tenant_id: str, package_id: str) -> list[PublishAttemptData]:
        with self.engine.begin() as conn:
            package = conn.execute(
                text(
                    """
                    SELECT id FROM airank_publish_packages
                    WHERE tenant_id=:tenant_id AND id=:package_id AND deleted_at IS NULL
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package_id},
            ).first()
            if package is None:
                raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
            rows = conn.execute(
                text(
                    """
                    SELECT a.*, o.state AS operation_state,
                           o.external_effect_started AS operation_external_effect_started
                    FROM airank_publish_attempts a
                    LEFT JOIN airank_operation_guards o
                      ON o.id=a.operation_id AND o.tenant_id=a.tenant_id
                    WHERE a.tenant_id=:tenant_id AND a.package_id=:package_id
                    ORDER BY attempt_number ASC
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package_id},
            ).mappings().all()
        return [
            PublishAttemptData(
                attempt_id=row["id"],
                package_id=row["package_id"],
                attempt_number=row["attempt_number"],
                channel=row["channel"],
                status=row["status"],
                request_sha256=row["request_sha256"],
                operation_id=row["operation_id"],
                operation_state=row["operation_state"],
                external_effect_started=bool(row["operation_external_effect_started"]),
                reconciliation_required=(
                    row["status"] == "outcome_unknown"
                    or row["operation_state"] == "external_started"
                ),
                reconciliation_case_id=row.get("reconciliation_case_id"),
                response_status=row["response_status"],
                response_sha256=row["response_sha256"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]

    def get_operation(self, tenant_id: str, operation_id: str) -> PublishOperationData:
        record = self.operation_guard.get_audit(tenant_id, operation_id)
        if record is None or record.operation_type != "publisher.publish":
            raise _not_found("OPERATION_NOT_FOUND", {"operation_id": operation_id})
        return _publish_operation_data(record)

    def get_export(self, tenant_id: str, package_id: str) -> PublishExportData:
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                SELECT p.id AS package_id, s.id AS snapshot_id, s.title, s.body_md,
                       s.content_sha256, s.manifest_json
                FROM airank_publish_packages p JOIN airank_publish_snapshots s ON s.id=p.snapshot_id
                WHERE p.tenant_id=:tenant_id AND p.id=:package_id AND p.deleted_at IS NULL
            """), {"tenant_id": tenant_id, "package_id": package_id}).mappings().first()
            if row is None:
                raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
        manifest = row["manifest_json"] if isinstance(row["manifest_json"], dict) else json.loads(row["manifest_json"] or "{}")
        return PublishExportData(package_id=row["package_id"], snapshot_id=row["snapshot_id"], title=row["title"], body_md=row["body_md"], content_sha256=row["content_sha256"], manifest=manifest)

    def mark_published(self, tenant_id: str, package_id: str, payload: PublishEvidenceRequest) -> PublishPackageData:
        published_at = utc_now()
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND id=:package_id AND deleted_at IS NULL FOR UPDATE"), {"tenant_id": tenant_id, "package_id": package_id}).mappings().first()
            if row is None:
                raise _not_found("PUBLISH_PACKAGE_NOT_FOUND", {"package_id": package_id})
            if row.get("publication_action") == "withdraw" or row["status"] in {"withdrawn", "superseded"}:
                raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_MUTATION_TARGET_STATE_CONFLICT", "details": {"package_id": package_id, "status": row["status"]}})
            if row["status"] == "published":
                if row["published_url"] != payload.published_url:
                    raise StarletteHTTPException(status_code=409, detail={"code": "STATE_CONFLICT", "details": {"package_id": package_id, "published_url": row["published_url"]}})
                return self._package_data(row, replay=True)
            required_status = "packaged" if row["channel"] == "export" else "delivered"
            if row["status"] != required_status:
                raise StarletteHTTPException(status_code=409, detail={"code": "PUBLISH_DELIVERY_RECEIPT_REQUIRED", "details": {"package_id": package_id, "status": row["status"], "required_status": required_status}})
            baseline = conn.execute(text("""
                SELECT id FROM airank_scan_runs
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                  AND id=:baseline_run_id AND run_type='baseline'
                  AND status='completed' AND deleted_at IS NULL
            """), {"tenant_id": tenant_id, "project_id": row["project_id"], "baseline_run_id": payload.baseline_run_id}).first()
            if baseline is None:
                raise StarletteHTTPException(status_code=409, detail={"code": "RETEST_BASELINE_REQUIRED", "details": {"baseline_run_id": payload.baseline_run_id, "required_run_type": "baseline", "required_status": "completed"}})
            if payload.screenshot_ref_id and payload.screenshot_sha256:
                screenshot = conn.execute(
                    text(
                        """
                        SELECT id FROM airank_object_refs
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND id=:screenshot_ref_id AND sha256=:screenshot_sha256
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": row["project_id"],
                        "screenshot_ref_id": payload.screenshot_ref_id,
                        "screenshot_sha256": payload.screenshot_sha256,
                    },
                ).first()
                if screenshot is None:
                    raise StarletteHTTPException(
                        status_code=409,
                        detail={
                            "code": "PUBLICATION_SCREENSHOT_EVIDENCE_INVALID",
                            "details": {
                                "screenshot_ref_id": payload.screenshot_ref_id,
                                "reason": "tenant_project_or_sha256_mismatch",
                            },
                        },
                    )
            metadata = row["metadata_json"] if isinstance(row["metadata_json"], dict) else json.loads(row["metadata_json"] or "{}")
            metadata["publication_evidence"] = {"recorded_by": payload.recorded_by, "baseline_run_id": payload.baseline_run_id, "screenshot_ref_id": payload.screenshot_ref_id, "screenshot_sha256": payload.screenshot_sha256, "recorded_at": published_at.isoformat()}
            conn.execute(text("UPDATE airank_publish_packages SET status='published', published_url=:published_url, published_at=:published_at, retest_due_at=:retest_due_at, metadata_json=:metadata_json, updated_at=:published_at WHERE tenant_id=:tenant_id AND id=:package_id"), {"published_url": payload.published_url, "published_at": published_at, "retest_due_at": published_at + timedelta(days=7), "metadata_json": json.dumps(metadata, ensure_ascii=False), "tenant_id": tenant_id, "package_id": package_id})
            for label, days in (("T0", 0), ("T+7", 7), ("T+14", 14), ("T+30", 30)):
                conn.execute(text("""
                    INSERT INTO airank_retest_observation_windows (
                      id, tenant_id, project_id, package_id, baseline_run_id, window_label, due_at,
                      status, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :package_id, :baseline_run_id, :window_label, :due_at,
                      'scheduled', :created_at, :created_at
                    )
                """), {"id": f"window_{uuid4().hex[:12]}", "tenant_id": tenant_id, "project_id": row["project_id"], "package_id": package_id, "baseline_run_id": payload.baseline_run_id, "window_label": label, "due_at": published_at + timedelta(days=days), "created_at": published_at})
            updated = conn.execute(text("SELECT * FROM airank_publish_packages WHERE tenant_id=:tenant_id AND id=:package_id"), {"tenant_id": tenant_id, "package_id": package_id}).mappings().one()
        return self._package_data(updated)


def _risk_level(findings: list[RiskFinding]) -> Literal["low", "medium", "high"]:
    if any(item.severity == "high" for item in findings):
        return "high"
    if any(item.severity == "medium" for item in findings):
        return "medium"
    return "low"


def _assert_review_allowed(payload: ContentReviewRequest, fact_check_status: str, risk_level: str) -> None:
    if payload.action != "approved":
        return
    if fact_check_status != "passed":
        raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_EVIDENCE_MISSING", "details": {"fact_check_status": fact_check_status}})
    if risk_level == "high" and not payload.override_reason:
        raise StarletteHTTPException(status_code=409, detail={"code": "CONTENT_RISK_OVERRIDE_REQUIRED", "details": {"risk_level": risk_level}})


def _snapshot_manifest(asset: Any, review: Any, payload: PublishPackageCreateRequest) -> dict[str, Any]:
    def get(value: Any, name: str) -> Any:
        if isinstance(value, Mapping):
            return value.get(name)
        return getattr(value, name)
    body = get(asset, "body_md") or ""
    metadata = get(asset, "metadata_json") if isinstance(asset, Mapping) else None
    if isinstance(metadata, str):
        metadata = json.loads(metadata or "{}")
    if not isinstance(metadata, Mapping):
        metadata = {}
    blueprint_sha256 = (
        metadata.get("blueprint_sha256")
        if isinstance(asset, Mapping)
        else getattr(asset, "blueprint_sha256", None)
    )
    skill_id = (
        metadata.get("skill_id")
        if isinstance(asset, Mapping)
        else getattr(asset, "skill_id", None)
    )
    skill_version = (
        metadata.get("skill_version")
        if isinstance(asset, Mapping)
        else getattr(asset, "skill_version", None)
    )
    return {
        "contract_version": "airank.publish-snapshot.v2",
        "asset_id": get(asset, "asset_id") if not isinstance(asset, Mapping) else asset.get("id"),
        "asset_type": get(asset, "asset_type"),
        "content_sha256": sha256_text(body),
        "blueprint_sha256": blueprint_sha256,
        "generation_skill": (
            {"skill_id": skill_id, "version": skill_version}
            if skill_id and skill_version
            else None
        ),
        "content_review_id": get(review, "review_id") if not isinstance(review, Mapping) else review.get("id"),
        "channel": payload.channel,
        "target_endpoint_host": urlparse(payload.target_endpoint).hostname if payload.target_endpoint else None,
        "requested_by": payload.requested_by,
        "immutable": True,
    }


def _publish_operation_data(record: OperationAuditRecord) -> PublishOperationData:
    response = record.response or {}
    replay_status = {
        "succeeded": "available",
        "claimed": "in_progress",
        "external_started": "forbidden_unknown",
        "failed": "forbidden_failed",
    }[record.state]
    return PublishOperationData(
        operation_id=record.operation_id,
        package_id=record.resource_key,
        state=record.state,
        external_effect_started=record.external_effect_started,
        request_sha256=record.request_sha256,
        error_code=record.error_code,
        created_by=record.created_by,
        trace_id=record.trace_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        reconciliation_required=record.state == "external_started",
        replay_status=replay_status,
        response_published_url=(
            str(response.get("published_url")) if response.get("published_url") else None
        ),
        response_status=(
            int(response["response_status"])
            if response.get("response_status") is not None
            else None
        ),
        response_sha256=(
            str(response.get("response_sha256")) if response.get("response_sha256") else None
        ),
        events=[
            PublishOperationEventData(
                event_sequence=event.event_sequence,
                event_type=event.event_type,
                from_state=event.from_state,
                to_state=event.to_state,
                request_sha256=event.request_sha256,
                previous_event_sha256=event.previous_event_sha256,
                event_sha256=event.event_sha256,
                actor=event.actor,
                trace_id=event.trace_id,
                created_at=event.created_at,
            )
            for event in record.events
        ],
    )


def _not_found(code: str, details: dict[str, Any]) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=404, detail={"code": code, "details": details})


def build_repository() -> DeliveryRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLDeliveryRepository(database_url) if database_url else InMemoryDeliveryRepository()


DELIVERY_REPOSITORY: DeliveryRepository = build_repository()


@router.post("/content-assets/{asset_id}/reviews", response_model=ContentReviewResponse, status_code=201)
def review_content(asset_id: str, payload: ContentReviewRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> ContentReviewResponse:
    trusted_payload = payload.model_copy(update={"reviewed_by": trusted_actor(payload.reviewed_by, authenticated_actor)})
    return ContentReviewResponse(data=DELIVERY_REPOSITORY.review_content(tenant_id, asset_id, trusted_payload), meta=response_meta(trace_id))


@router.post("/content-assets/{asset_id}/publish-packages", response_model=PublishPackageResponse, status_code=201)
def create_publish_package(asset_id: str, payload: PublishPackageCreateRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> PublishPackageResponse:
    trusted_payload = payload.model_copy(update={"requested_by": trusted_actor(payload.requested_by, authenticated_actor)})
    return PublishPackageResponse(data=DELIVERY_REPOSITORY.create_package(tenant_id, asset_id, trusted_payload), meta=response_meta(trace_id))


@router.post("/publish-packages/{package_id}/mutations", response_model=PublishPackageResponse, status_code=201)
def create_publish_mutation(
    package_id: str,
    payload: PublishMutationCreateRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
    permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> PublishPackageResponse:
    require_delivery_admin(permission_header)
    trusted_payload = payload.model_copy(update={"requested_by": trusted_actor(payload.requested_by, authenticated_actor)})
    return PublishPackageResponse(data=DELIVERY_REPOSITORY.create_mutation(tenant_id, package_id, trusted_payload), meta=response_meta(trace_id))


@router.get("/projects/{project_id}/publish-packages", response_model=PublishPackageListResponse)
def list_publish_packages(project_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> PublishPackageListResponse:
    return PublishPackageListResponse(data=DELIVERY_REPOSITORY.list_packages(tenant_id, project_id), meta=response_meta(trace_id))


@router.get("/publish-packages/{package_id}/export", response_model=PublishExportResponse)
def export_publish_package(package_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> PublishExportResponse:
    return PublishExportResponse(data=DELIVERY_REPOSITORY.get_export(tenant_id, package_id), meta=response_meta(trace_id))


@router.get("/publish-packages/{package_id}/attempts", response_model=PublishAttemptListResponse)
def list_publish_attempts(package_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> PublishAttemptListResponse:
    return PublishAttemptListResponse(data=DELIVERY_REPOSITORY.list_attempts(tenant_id, package_id), meta=response_meta(trace_id))


@router.get("/publish-operations/{operation_id}", response_model=PublishOperationResponse)
def get_publish_operation(
    operation_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions"),
) -> PublishOperationResponse:
    require_delivery_admin(permission_header)
    return PublishOperationResponse(
        data=DELIVERY_REPOSITORY.get_operation(tenant_id, operation_id),
        meta=response_meta(trace_id),
    )


@router.post("/publish-packages/{package_id}/publication-evidence", response_model=PublishPackageResponse)
def record_publication_evidence(package_id: str, payload: PublishEvidenceRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> PublishPackageResponse:
    trusted_payload = payload.model_copy(update={"recorded_by": trusted_actor(payload.recorded_by, authenticated_actor)})
    return PublishPackageResponse(data=DELIVERY_REPOSITORY.mark_published(tenant_id, package_id, trusted_payload), meta=response_meta(trace_id))

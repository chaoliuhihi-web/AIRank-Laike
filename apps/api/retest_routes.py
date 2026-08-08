from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Literal, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import canonical_json_sha256
from airank_domain.measurement import (
    CollectorSurface,
    EvidenceLevel,
    MeasurementSample,
    MentionClass,
    PromptCohortType,
    SampleContext,
    SampleStatus,
    SURFACE_EVIDENCE_LEVEL,
)
from airank_score.quality import (
    MeasurementQualityReport,
    SampleEvidenceManifest,
    build_measurement_quality_report,
)
from airank_score.retest import compare_retest_metrics

try:
    from . import delivery_routes
except ImportError:  # pragma: no cover
    import delivery_routes  # type: ignore[no-redef]


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["retest-attribution"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {"trace_id": trace_id or f"trc_{uuid4().hex[:16]}", "request_id": f"req_{uuid4().hex[:16]}"}


def trusted_completion_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    if not authenticated_actor:
        raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})
    return authenticated_actor


class RetestWindowData(BaseModel):
    window_id: str
    tenant_id: str
    project_id: str
    package_id: str
    baseline_run_id: Optional[str]
    window_label: Literal["T0", "T+7", "T+14", "T+30"]
    due_at: datetime
    status: Literal[
        "scheduled",
        "sampling",
        "blocked",
        "running",
        "completed",
        "completed_with_limitations",
        "failed",
    ]
    compare_run_id: Optional[str] = None
    completed_at: Optional[datetime] = None


class RetestWindowListResponse(BaseModel):
    data: list[RetestWindowData]
    meta: dict[str, str]


class CompleteRetestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compare_run_id: str = Field(min_length=1, max_length=64)
    completed_by: str = Field(min_length=1, max_length=64)


class RetestComparisonData(BaseModel):
    retest_run_id: str
    report_id: str
    window_id: str
    window_label: str
    baseline_run_id: str
    compare_run_id: str
    comparable: bool
    mismatch_reasons: list[str]
    confidence: Literal["low", "medium"]
    baseline_metrics: dict[str, Any]
    compare_metrics: dict[str, Any]
    metric_deltas: dict[str, Optional[float]]
    conclusion: str
    attribution_policy: Literal["observational_non_causal.v1"]
    report_status: Literal["generated", "quality_blocked"]
    baseline_quality: dict[str, Any]
    compare_quality: dict[str, Any]
    known_limitations: list[str]
    report_sha256: str
    evidence_refs: list[str]
    completed_at: datetime
    idempotent_replay: bool = False


class RetestComparisonResponse(BaseModel):
    data: RetestComparisonData
    meta: dict[str, str]


class MeasurementQualityReportResponse(BaseModel):
    data: dict[str, Any]
    meta: dict[str, str]


@dataclass(frozen=True)
class RunEvidence:
    project_id: str
    samples: tuple[MeasurementSample, ...]
    signature: tuple[str, ...]
    evidence_manifests: tuple[SampleEvidenceManifest, ...] = ()
    run_status: str = "completed"


class RetestRepository(Protocol):
    def list_windows(self, tenant_id: str, project_id: str) -> list[RetestWindowData]: ...
    def get_quality_report(self, tenant_id: str, project_id: str, run_id: str) -> dict[str, Any]: ...
    def complete_window(self, tenant_id: str, window_id: str, payload: CompleteRetestRequest) -> RetestComparisonData: ...


class InMemoryRetestRepository:
    def __init__(self) -> None:
        self.runs: dict[tuple[str, str], RunEvidence] = {}
        self.results: dict[tuple[str, str], RetestComparisonData] = {}

    def register_run(self, tenant_id: str, run_id: str, evidence: RunEvidence) -> None:
        self.runs[(tenant_id, run_id)] = evidence

    def _windows(self) -> dict[tuple[str, str], dict[str, Any]]:
        repository = delivery_routes.DELIVERY_REPOSITORY
        return getattr(repository, "retest_windows", {})

    def list_windows(self, tenant_id: str, project_id: str) -> list[RetestWindowData]:
        return [
            RetestWindowData.model_validate(value)
            for (item_tenant, _), value in self._windows().items()
            if item_tenant == tenant_id and value["project_id"] == project_id
        ]

    def get_quality_report(self, tenant_id: str, project_id: str, run_id: str) -> dict[str, Any]:
        evidence = self.runs.get((tenant_id, run_id))
        if evidence is None or evidence.project_id != project_id:
            raise _not_found("SCAN_RUN_NOT_FOUND", {"project_id": project_id, "run_id": run_id})
        return build_measurement_quality_report(
            run_id=run_id,
            samples=evidence.samples,
            signatures=evidence.signature,
            evidence_manifests=evidence.evidence_manifests,
            run_status=evidence.run_status,
        ).to_record()

    def complete_window(self, tenant_id: str, window_id: str, payload: CompleteRetestRequest) -> RetestComparisonData:
        replay = self.results.get((tenant_id, window_id))
        if replay is not None:
            if replay.compare_run_id != payload.compare_run_id:
                raise _conflict("STATE_CONFLICT", {"window_id": window_id, "compare_run_id": replay.compare_run_id})
            return replay.model_copy(update={"idempotent_replay": True})
        window = self._windows().get((tenant_id, window_id))
        if window is None:
            raise _not_found("RETEST_WINDOW_NOT_FOUND", {"window_id": window_id})
        baseline_run_id = window.get("baseline_run_id")
        if not baseline_run_id:
            raise _conflict("RETEST_BASELINE_REQUIRED", {"window_id": window_id})
        baseline = self.runs.get((tenant_id, baseline_run_id))
        compare = self.runs.get((tenant_id, payload.compare_run_id))
        if baseline is None or compare is None or baseline.project_id != window["project_id"] or compare.project_id != window["project_id"]:
            raise _conflict("RETEST_COMPARE_RUN_REQUIRED", {"baseline_run_id": baseline_run_id, "compare_run_id": payload.compare_run_id})
        result = _comparison_data(
            window=window,
            baseline_run_id=baseline_run_id,
            compare_run_id=payload.compare_run_id,
            baseline_quality=build_measurement_quality_report(
                run_id=baseline_run_id,
                samples=baseline.samples,
                signatures=baseline.signature,
                evidence_manifests=baseline.evidence_manifests,
                run_status=baseline.run_status,
            ),
            compare_quality=build_measurement_quality_report(
                run_id=payload.compare_run_id,
                samples=compare.samples,
                signatures=compare.signature,
                evidence_manifests=compare.evidence_manifests,
                run_status=compare.run_status,
            ),
            baseline_signature=baseline.signature,
            compare_signature=compare.signature,
        )
        window.update({"status": "completed" if result.comparable else "completed_with_limitations", "compare_run_id": payload.compare_run_id, "result": result.model_dump(mode="json"), "completed_at": result.completed_at})
        self.results[(tenant_id, window_id)] = result
        return result


class MySQLRetestRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def list_windows(self, tenant_id: str, project_id: str) -> list[RetestWindowData]:
        with self.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT id AS window_id, tenant_id, project_id, package_id,
                       baseline_run_id, window_label, due_at, status,
                       compare_run_id, completed_at
                FROM airank_retest_observation_windows
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY due_at ASC, id ASC
            """), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()
        return [RetestWindowData.model_validate(dict(row)) for row in rows]

    def get_quality_report(self, tenant_id: str, project_id: str, run_id: str) -> dict[str, Any]:
        with self.engine.begin() as conn:
            evidence = self._load_run(conn, tenant_id, project_id, run_id)
        return build_measurement_quality_report(
            run_id=run_id,
            samples=evidence.samples,
            signatures=evidence.signature,
            evidence_manifests=evidence.evidence_manifests,
            run_status=evidence.run_status,
        ).to_record()

    def complete_window(self, tenant_id: str, window_id: str, payload: CompleteRetestRequest) -> RetestComparisonData:
        completed_at = utc_now()
        with self.engine.begin() as conn:
            window = conn.execute(text("""
                SELECT w.*, p.snapshot_id
                FROM airank_retest_observation_windows w
                JOIN airank_publish_packages p ON p.id=w.package_id AND p.tenant_id=w.tenant_id
                WHERE w.tenant_id=:tenant_id AND w.id=:window_id
                FOR UPDATE
            """), {"tenant_id": tenant_id, "window_id": window_id}).mappings().first()
            if window is None:
                raise _not_found("RETEST_WINDOW_NOT_FOUND", {"window_id": window_id})
            if window["status"] in {"completed", "completed_with_limitations"}:
                if window["compare_run_id"] != payload.compare_run_id:
                    raise _conflict("STATE_CONFLICT", {"window_id": window_id, "compare_run_id": window["compare_run_id"]})
                stored = _json_value(window["result_json"], {})
                return RetestComparisonData.model_validate({**stored, "idempotent_replay": True})
            if window["compare_run_id"] and window["compare_run_id"] != payload.compare_run_id:
                raise _conflict(
                    "STATE_CONFLICT",
                    {
                        "window_id": window_id,
                        "compare_run_id": window["compare_run_id"],
                    },
                )
            baseline_run_id = window["baseline_run_id"]
            if not baseline_run_id:
                raise _conflict("RETEST_BASELINE_REQUIRED", {"window_id": window_id})
            baseline = self._load_run(conn, tenant_id, window["project_id"], baseline_run_id)
            compare = self._load_run(conn, tenant_id, window["project_id"], payload.compare_run_id)
            result = _comparison_data(
                window=dict(window),
                baseline_run_id=baseline_run_id,
                compare_run_id=payload.compare_run_id,
                baseline_quality=build_measurement_quality_report(
                    run_id=baseline_run_id,
                    samples=baseline.samples,
                    signatures=baseline.signature,
                    evidence_manifests=baseline.evidence_manifests,
                    run_status=baseline.run_status,
                ),
                compare_quality=build_measurement_quality_report(
                    run_id=payload.compare_run_id,
                    samples=compare.samples,
                    signatures=compare.signature,
                    evidence_manifests=compare.evidence_manifests,
                    run_status=compare.run_status,
                ),
                baseline_signature=baseline.signature,
                compare_signature=compare.signature,
                completed_at=completed_at,
            )
            status = "completed" if result.report_status == "generated" else "completed_with_limitations"
            result_json = result.model_dump(mode="json")
            conn.execute(text("""
                UPDATE airank_retest_observation_windows
                SET status=:status, compare_run_id=:compare_run_id,
                    result_json=:result_json, completed_at=:completed_at, updated_at=:completed_at
                WHERE tenant_id=:tenant_id AND id=:window_id
            """), {"status": status, "compare_run_id": payload.compare_run_id, "result_json": json.dumps(result_json, ensure_ascii=False), "completed_at": completed_at, "tenant_id": tenant_id, "window_id": window_id})
            conn.execute(text("""
                INSERT INTO airank_retest_runs (
                  id, tenant_id, project_id, package_id, observation_window_id,
                  baseline_run_id, compare_run_id, comparison_contract_version,
                  created_by, status, summary_json, started_at, finished_at, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :package_id, :window_id,
                  :baseline_run_id, :compare_run_id, 'airank.retest-comparison.v1',
                  :created_by, :status, :summary_json, :completed_at, :completed_at, :completed_at, :completed_at
                )
            """), {"id": result.retest_run_id, "tenant_id": tenant_id, "project_id": window["project_id"], "package_id": window["package_id"], "window_id": window_id, "baseline_run_id": baseline_run_id, "compare_run_id": payload.compare_run_id, "created_by": payload.completed_by, "status": status, "summary_json": json.dumps(result_json, ensure_ascii=False), "completed_at": completed_at})
            evidence_index = {"package_id": window["package_id"], "publish_snapshot_id": window["snapshot_id"], "window_id": window_id, "baseline_run_id": baseline_run_id, "compare_run_id": payload.compare_run_id, "evidence_refs": result.evidence_refs}
            conn.execute(text("""
                INSERT INTO airank_reports (
                  id, tenant_id, project_id, report_type, title, status,
                  run_id, retest_run_id, metrics_json, report_sha256,
                  evidence_index_json, generated_by, generated_at, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :project_id, 'retest', :title, :report_status,
                  :compare_run_id, :retest_run_id, :metrics_json, :report_sha256,
                  :evidence_index_json, :generated_by, :generated_at, :generated_at, :generated_at
                )
            """), {"id": result.report_id, "tenant_id": tenant_id, "project_id": window["project_id"], "title": f"{window['window_label']} GEO 复测观察报告", "report_status": result.report_status, "compare_run_id": payload.compare_run_id, "retest_run_id": result.retest_run_id, "metrics_json": json.dumps(result_json, ensure_ascii=False), "report_sha256": result.report_sha256, "evidence_index_json": json.dumps(evidence_index, ensure_ascii=False), "generated_by": payload.completed_by, "generated_at": completed_at})
        return result

    @staticmethod
    def _load_run(conn: Any, tenant_id: str, project_id: str, run_id: str) -> RunEvidence:
        run = conn.execute(text("""
            SELECT id, status FROM airank_scan_runs
            WHERE tenant_id=:tenant_id AND project_id=:project_id
              AND id=:run_id AND status IN ('completed', 'failed') AND deleted_at IS NULL
        """), {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id}).first()
        if run is None:
            raise _conflict(
                "RETEST_COMPARE_RUN_REQUIRED",
                {"run_id": run_id, "required_status": "completed_or_failed"},
            )
        rows = conn.execute(text("""
            SELECT t.id AS task_id, t.question_id, t.provider, t.cohort_type,
                   t.prompt_version_id, t.sample_index, t.session_id,
                   t.collector_surface, t.evidence_level, t.status AS task_status,
                   t.error_code, s.id AS sample_id, s.sample_status, s.answer_text,
                   s.answer_sha256, s.raw_response_sha256, s.mention_class,
                   s.brand_rank, s.model_name, s.model_version, s.search_enabled,
                   s.locale, s.region, s.external_trace_id,
                   e.request_metadata_json, e.screenshot_ref_id,
                   e.source_panel_ref_id,
                   screenshot.sha256 AS screenshot_sha256,
                   screenshot.metadata_json AS screenshot_metadata_json,
                   source_panel.sha256 AS source_panel_sha256,
                   source_panel.metadata_json AS source_panel_metadata_json,
                   (SELECT a.id FROM airank_provider_request_audits a
                    WHERE a.tenant_id=t.tenant_id AND a.answer_snapshot_id=s.id
                    ORDER BY a.created_at ASC, a.id ASC LIMIT 1) AS provider_request_audit_id,
                   (SELECT COUNT(*) FROM airank_source_citations c
                    WHERE c.tenant_id=t.tenant_id AND c.snapshot_id=s.id) AS citation_count
            FROM airank_scan_tasks t
            LEFT JOIN airank_answer_snapshots s
              ON s.tenant_id=t.tenant_id AND s.task_id=t.id
            LEFT JOIN airank_evidence_snapshots e
              ON e.tenant_id=t.tenant_id AND e.answer_snapshot_id=s.id
            LEFT JOIN airank_object_refs screenshot
              ON screenshot.tenant_id=t.tenant_id AND screenshot.id=e.screenshot_ref_id
            LEFT JOIN airank_object_refs source_panel
              ON source_panel.tenant_id=t.tenant_id AND source_panel.id=e.source_panel_ref_id
            WHERE t.tenant_id=:tenant_id AND t.project_id=:project_id AND t.run_id=:run_id
            ORDER BY t.question_id, t.provider, t.cohort_type,
                     t.collector_surface, t.sample_index, t.id
        """), {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id}).mappings().all()
        if not rows:
            raise _conflict("RETEST_COMPARE_RUN_REQUIRED", {"run_id": run_id, "reason": "no_samples"})
        try:
            from .citation_support_routes import (
                load_citation_support_bundles_from_connection,
                load_fact_accuracy_bundles_from_connection,
            )
        except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
            from citation_support_routes import (  # type: ignore[no-redef]
                load_citation_support_bundles_from_connection,
                load_fact_accuracy_bundles_from_connection,
            )
        row_records = [dict(row) for row in rows]
        snapshot_ids = [
            str(row["sample_id"]) for row in row_records if row.get("sample_id")
        ]
        citation_bundles = load_citation_support_bundles_from_connection(
            conn,
            tenant_id,
            snapshot_ids,
        )
        fact_bundles = load_fact_accuracy_bundles_from_connection(
            conn,
            tenant_id,
            snapshot_ids,
        )
        for row in row_records:
            snapshot_id = str(row.get("sample_id") or "")
            citation_bundle = citation_bundles.get(snapshot_id)
            row["citation_support_score"] = (
                citation_bundle.metrics.citation_support_rate
                if citation_bundle
                else None
            )
            fact_bundle = fact_bundles.get(snapshot_id)
            fact_metrics = fact_bundle.metrics if fact_bundle else None
            row["fact_claim_count"] = fact_metrics.factual_claim_count if fact_metrics else 0
            row["fact_reviewed_claim_count"] = fact_metrics.decisive_claim_count if fact_metrics else 0
            row["fact_accuracy"] = fact_metrics.fact_accuracy if fact_metrics else None
        samples = tuple(_measurement_sample(row) for row in row_records)
        signature = tuple(_sample_signature(row) for row in row_records)
        evidence_manifests = tuple(_sample_evidence_manifest(row) for row in row_records)
        return RunEvidence(
            project_id=project_id,
            samples=samples,
            signature=signature,
            evidence_manifests=evidence_manifests,
            run_status=str(run.status),
        )


def _measurement_sample(row: dict[str, Any]) -> MeasurementSample:
    surface = CollectorSurface(row["collector_surface"])
    try:
        evidence_level = EvidenceLevel(row["evidence_level"])
    except ValueError:
        evidence_level = SURFACE_EVIDENCE_LEVEL[surface]
    has_snapshot = bool(row.get("sample_id"))
    has_answer = bool(has_snapshot and (row.get("answer_text") or "").strip())
    raw_status = row.get("sample_status") if has_snapshot else None
    if raw_status == "valid" and has_answer:
        status = SampleStatus.VALID
    elif raw_status == "blocked" or row.get("task_status") == "skipped" or "BLOCK" in str(row.get("error_code") or "").upper():
        status = SampleStatus.BLOCKED
    else:
        status = SampleStatus.FAILED
    mention_class = MentionClass(row.get("mention_class") or "not_mentioned") if status == SampleStatus.VALID else MentionClass.UNKNOWN
    context = SampleContext(
        prompt_version_id=row["prompt_version_id"],
        cohort_type=PromptCohortType(row["cohort_type"]),
        sample_index=int(row["sample_index"]),
        session_id=row.get("session_id") or f"legacy-{row['task_id']}",
        surface=surface,
        evidence_level=evidence_level,
        provider=row["provider"],
        captured_at=utc_now(),
        model_name=row.get("model_name"),
        model_version=row.get("model_version"),
        search_enabled=None if row.get("search_enabled") is None else bool(row["search_enabled"]),
        locale=row.get("locale") or "zh-CN",
        region=row.get("region"),
    )
    return MeasurementSample(
        sample_id=row.get("sample_id") or row["task_id"],
        question_id=row["question_id"],
        context=context,
        status=status,
        answer_text=row.get("answer_text") if status == SampleStatus.VALID else None,
        answer_sha256=row.get("answer_sha256") if status == SampleStatus.VALID else None,
        raw_response_sha256=row.get("raw_response_sha256"),
        mention_class=mention_class,
        brand_rank=row.get("brand_rank") if status == SampleStatus.VALID else None,
        citation_count=int(row.get("citation_count") or 0),
        citation_support_score=(
            float(row["citation_support_score"])
            if row.get("citation_support_score") is not None
            else None
        ),
        fact_claim_count=int(row.get("fact_claim_count") or 0),
        fact_reviewed_claim_count=int(row.get("fact_reviewed_claim_count") or 0),
        fact_accuracy=(
            float(row["fact_accuracy"])
            if row.get("fact_accuracy") is not None
            else None
        ),
        failure_code=None if status == SampleStatus.VALID else (row.get("error_code") or "sample_missing"),
    )


def _sample_signature(row: dict[str, Any]) -> str:
    values = (
        row["question_id"], row["provider"], row["cohort_type"],
        row["collector_surface"], row["sample_index"], row["prompt_version_id"],
        row.get("model_name"), row.get("model_version"), row.get("search_enabled"),
        row.get("locale"), row.get("region"),
    )
    return "|".join("" if value is None else str(value) for value in values)


def _sample_evidence_manifest(row: dict[str, Any]) -> SampleEvidenceManifest:
    surface = CollectorSurface(row["collector_surface"])
    try:
        evidence_level = EvidenceLevel(row["evidence_level"])
    except ValueError:
        evidence_level = SURFACE_EVIDENCE_LEVEL[surface]
    request_metadata = _json_value(row.get("request_metadata_json"), {})
    provider_request = request_metadata.get("provider_request", {}) if isinstance(request_metadata, dict) else {}
    if not isinstance(provider_request, dict):
        provider_request = {}
    screenshot_metadata = _json_value(row.get("screenshot_metadata_json"), {})
    source_panel_metadata = _json_value(row.get("source_panel_metadata_json"), {})
    source_panel_status = provider_request.get("source_panel_status")
    if source_panel_status not in {"captured", "not_present", "not_inspected", "not_applicable"}:
        source_panel_status = "not_inspected" if surface in {CollectorSurface.WEB, CollectorSurface.APP} else "not_applicable"
    app_metadata = provider_request.get("app_capture_metadata")
    conversation_isolation = provider_request.get("conversation_isolation")
    import_source_sha256 = provider_request.get("import_source_sha256")
    return SampleEvidenceManifest(
        sample_id=row.get("sample_id") or row["task_id"],
        surface=surface,
        evidence_level=evidence_level,
        request_metadata_sha256=(
            canonical_json_sha256(request_metadata)
            if isinstance(request_metadata, dict) and request_metadata
            else None
        ),
        external_trace_id=row.get("external_trace_id"),
        provider_request_audit_id=row.get("provider_request_audit_id"),
        screenshot_ref_id=row.get("screenshot_ref_id"),
        screenshot_sha256=row.get("screenshot_sha256"),
        screenshot_immutable=bool(
            isinstance(screenshot_metadata, dict) and screenshot_metadata.get("immutable") is True
        ),
        conversation_isolation_verified=bool(
            isinstance(conversation_isolation, dict)
            and conversation_isolation.get("verified") is True
        ),
        source_panel_status=source_panel_status,
        source_panel_ref_id=row.get("source_panel_ref_id"),
        source_panel_sha256=row.get("source_panel_sha256"),
        source_panel_immutable=bool(
            isinstance(source_panel_metadata, dict) and source_panel_metadata.get("immutable") is True
        ),
        app_capture_metadata_sha256=(
            canonical_json_sha256(app_metadata) if isinstance(app_metadata, dict) and app_metadata else None
        ),
        import_source_sha256=(
            str(import_source_sha256)
            if isinstance(import_source_sha256, str) and import_source_sha256
            else None
        ),
    )


def _comparison_data(
    *,
    window: dict[str, Any],
    baseline_run_id: str,
    compare_run_id: str,
    baseline_quality: MeasurementQualityReport,
    compare_quality: MeasurementQualityReport,
    baseline_signature: tuple[str, ...],
    compare_signature: tuple[str, ...],
    completed_at: Optional[datetime] = None,
) -> RetestComparisonData:
    comparison = compare_retest_metrics(
        baseline_run_id=baseline_run_id,
        compare_run_id=compare_run_id,
        baseline_metrics=baseline_quality.metrics,
        compare_metrics=compare_quality.metrics,
        baseline_signature=baseline_signature,
        compare_signature=compare_signature,
    )
    completed_at = completed_at or utc_now()
    retest_run_id = f"retest_{uuid4().hex[:12]}"
    report_id = f"report_{uuid4().hex[:12]}"
    evidence_refs = [f"scan_run:{baseline_run_id}", f"scan_run:{compare_run_id}", f"publish_package:{window['package_id']}", f"retest_window:{window['window_id'] if 'window_id' in window else window['id']}"]
    report_status: Literal["generated", "quality_blocked"] = (
        "generated"
        if comparison.comparable and baseline_quality.publishable and compare_quality.publishable
        else "quality_blocked"
    )
    known_limitations = [
        *[f"baseline:{item}" for item in baseline_quality.known_limitations],
        *[f"compare:{item}" for item in compare_quality.known_limitations],
        *[f"comparison:{item}" for item in comparison.mismatch_reasons],
    ]
    hash_payload = {
        "comparison": comparison.to_record(),
        "window_label": window["window_label"],
        "evidence_refs": evidence_refs,
        "report_status": report_status,
        "baseline_quality": baseline_quality.to_record(),
        "compare_quality": compare_quality.to_record(),
        "known_limitations": known_limitations,
    }
    return RetestComparisonData(
        retest_run_id=retest_run_id,
        report_id=report_id,
        window_id=window.get("window_id") or window["id"],
        window_label=window["window_label"],
        baseline_run_id=baseline_run_id,
        compare_run_id=compare_run_id,
        comparable=comparison.comparable,
        mismatch_reasons=list(comparison.mismatch_reasons),
        confidence=comparison.confidence,
        baseline_metrics=comparison.baseline_metrics.to_record(),
        compare_metrics=comparison.compare_metrics.to_record(),
        metric_deltas=dict(comparison.metric_deltas),
        conclusion=comparison.conclusion,
        attribution_policy="observational_non_causal.v1",
        report_status=report_status,
        baseline_quality=baseline_quality.to_record(),
        compare_quality=compare_quality.to_record(),
        known_limitations=known_limitations,
        report_sha256=canonical_json_sha256(hash_payload),
        evidence_refs=evidence_refs,
        completed_at=completed_at,
    )


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _not_found(code: str, details: dict[str, Any]) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=404, detail={"code": code, "details": details})


def _conflict(code: str, details: dict[str, Any]) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=409, detail={"code": code, "details": details})


def build_repository() -> RetestRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLRetestRepository(database_url) if database_url else InMemoryRetestRepository()


RETEST_REPOSITORY: RetestRepository = build_repository()


@router.get("/projects/{project_id}/retest-windows", response_model=RetestWindowListResponse)
def list_retest_windows(project_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER)) -> RetestWindowListResponse:
    return RetestWindowListResponse(data=RETEST_REPOSITORY.list_windows(tenant_id, project_id), meta=response_meta(trace_id))


@router.get(
    "/projects/{project_id}/scan-runs/{run_id}/quality-report",
    response_model=MeasurementQualityReportResponse,
)
def get_measurement_quality_report(
    project_id: str,
    run_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> MeasurementQualityReportResponse:
    return MeasurementQualityReportResponse(
        data=RETEST_REPOSITORY.get_quality_report(tenant_id, project_id, run_id),
        meta=response_meta(trace_id),
    )


@router.post("/retest-windows/{window_id}/complete", response_model=RetestComparisonResponse)
def complete_retest_window(window_id: str, payload: CompleteRetestRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id")) -> RetestComparisonResponse:
    trusted_payload = payload.model_copy(update={"completed_by": trusted_completion_actor(payload.completed_by, authenticated_actor)})
    return RetestComparisonResponse(data=RETEST_REPOSITORY.complete_window(tenant_id, window_id, trusted_payload), meta=response_meta(trace_id))

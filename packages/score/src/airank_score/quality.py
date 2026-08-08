from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Literal, Sequence

from airank_domain.measurement import (
    CollectorSurface,
    EvidenceLevel,
    MeasurementSample,
    MentionClass,
    SampleStatus,
    canonical_json_sha256,
)

from .measurement import CohortMetrics, calculate_cohort_metrics


QUALITY_CONTRACT_VERSION = "airank.measurement-quality.v4"


@dataclass(frozen=True)
class QualityCheck:
    code: str
    status: Literal["pass", "blocked", "warning"]
    actual: int | float | str | bool | None
    expected: str
    detail: str

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


SourcePanelStatus = Literal["captured", "not_present", "not_inspected", "not_applicable"]


@dataclass(frozen=True)
class SampleEvidenceManifest:
    """Immutable references used to decide whether a sample is deliverable evidence.

    MeasurementSample intentionally contains only analytical fields. This manifest
    keeps capture provenance separate so an analysis label can never upgrade the
    evidence grade of an API, browser, app, or imported sample.
    """

    sample_id: str
    surface: CollectorSurface
    evidence_level: EvidenceLevel
    request_metadata_sha256: str | None = None
    external_trace_id: str | None = None
    provider_request_audit_id: str | None = None
    screenshot_ref_id: str | None = None
    screenshot_sha256: str | None = None
    screenshot_immutable: bool = False
    conversation_isolation_verified: bool = False
    source_panel_status: SourcePanelStatus = "not_applicable"
    source_panel_ref_id: str | None = None
    source_panel_sha256: str | None = None
    source_panel_immutable: bool = False
    app_capture_metadata_sha256: str | None = None
    import_source_sha256: str | None = None

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["surface"] = self.surface.value
        record["evidence_level"] = self.evidence_level.value
        return record


@dataclass(frozen=True)
class SurfaceEvidenceSummary:
    surface: str
    evidence_level: str
    sample_count: int
    valid_sample_count: int
    evidence_complete_count: int
    screenshot_count: int
    source_panel_captured_count: int
    source_panel_not_present_count: int
    blocker_count: int

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeasurementQualityReport:
    contract_version: str
    run_id: str
    status: Literal["pass", "blocked"]
    publishable: bool
    data_sha256: str
    report_sha256: str
    metrics: CohortMetrics
    checks: tuple[QualityCheck, ...]
    surface_evidence: tuple[SurfaceEvidenceSummary, ...]
    known_limitations: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "run_id": self.run_id,
            "status": self.status,
            "publishable": self.publishable,
            "data_sha256": self.data_sha256,
            "report_sha256": self.report_sha256,
            "metrics": self.metrics.to_record(),
            "checks": [item.to_record() for item in self.checks],
            "surface_evidence": [item.to_record() for item in self.surface_evidence],
            "known_limitations": list(self.known_limitations),
        }


def build_measurement_quality_report(
    *,
    run_id: str,
    samples: Iterable[MeasurementSample],
    signatures: Sequence[str],
    evidence_manifests: Iterable[SampleEvidenceManifest] = (),
    run_status: str = "completed",
    minimum_valid_sample_rate: float = 0.8,
    minimum_independent_repetitions: int = 3,
) -> MeasurementQualityReport:
    sample_list = list(samples)
    signature_list = list(signatures)
    manifest_list = list(evidence_manifests)
    manifests_by_sample_id = {item.sample_id: item for item in manifest_list}
    metrics = calculate_cohort_metrics(sample_list)
    checks: list[QualityCheck] = []

    def add_check(code: str, passed: bool, actual: Any, expected: str, detail: str) -> None:
        checks.append(QualityCheck(code, "pass" if passed else "blocked", actual, expected, detail))

    add_check(
        "run_status_publishable",
        run_status == "completed",
        run_status,
        "= completed",
        "失败批次可以生成审计报告，但不得作为可交付测量结果发布。",
    )
    add_check("samples_present", bool(sample_list), len(sample_list), "> 0", "报告必须来自至少一个真实任务样本。")
    add_check(
        "signature_count_matches",
        len(signature_list) == len(sample_list),
        len(signature_list),
        f"= {len(sample_list)}",
        "每个样本必须有一条可比较任务签名。",
    )
    sample_ids = [item.sample_id for item in sample_list]
    add_check(
        "sample_ids_unique",
        len(sample_ids) == len(set(sample_ids)),
        len(sample_ids) - len(set(sample_ids)),
        "= 0 duplicates",
        "重复样本 ID 会导致分母和指标被重复计算。",
    )
    add_check(
        "sample_contracts_unique",
        len(signature_list) == len(set(signature_list)),
        len(signature_list) - len(set(signature_list)),
        "= 0 duplicates",
        "同一问题、平台、终端和轮次不能重复占用一个采样位。",
    )
    repetition_groups: dict[tuple[object, ...], list[MeasurementSample]] = {}
    for sample in sample_list:
        key = (
            sample.question_id,
            sample.context.provider,
            sample.context.cohort_type.value,
            sample.context.surface.value,
            sample.context.evidence_level.value,
            sample.context.prompt_version_id,
            sample.context.model_name,
            sample.context.model_version,
            sample.context.search_enabled,
            sample.context.locale,
            sample.context.region,
        )
        repetition_groups.setdefault(key, []).append(sample)
    incomplete_repetition_groups = sum(
        len(group) < minimum_independent_repetitions
        or len({item.context.sample_index for item in group}) < minimum_independent_repetitions
        or len({item.context.session_id for item in group}) < minimum_independent_repetitions
        for group in repetition_groups.values()
    )
    add_check(
        "independent_repetitions_complete",
        bool(repetition_groups) and incomplete_repetition_groups == 0,
        incomplete_repetition_groups,
        f"= 0 groups below {minimum_independent_repetitions} distinct samples/sessions",
        "每个问题、Provider、Cohort、采集面和模型口径必须有至少 3 次独立会话采样，否则不能评估稳定性或交付。",
    )
    partition_count = metrics.valid_sample_count + metrics.failed_sample_count + metrics.blocked_sample_count
    add_check(
        "status_partition_complete",
        partition_count == metrics.total_sample_count,
        partition_count,
        f"= {metrics.total_sample_count}",
        "有效、失败和阻塞必须覆盖全部样本，未提及仍属于有效样本。",
    )
    add_check(
        "valid_samples_present",
        metrics.valid_sample_count > 0,
        metrics.valid_sample_count,
        "> 0",
        "没有有效回答时不得发布品牌可见度或变化结论。",
    )
    add_check(
        "valid_sample_rate",
        metrics.valid_sample_rate >= minimum_valid_sample_rate,
        metrics.valid_sample_rate,
        f">= {minimum_valid_sample_rate}",
        "有效样本率过低时结果易被失败/阻塞偏差主导。",
    )
    missing_answer_hash = sum(
        item.status == SampleStatus.VALID and not _is_sha256(item.answer_sha256) for item in sample_list
    )
    add_check(
        "valid_answer_hashes_present",
        missing_answer_hash == 0,
        missing_answer_hash,
        "= 0 missing",
        "每个有效回答必须绑定逐字回答 SHA-256。",
    )
    missing_raw_hash = sum(not _is_sha256(item.raw_response_sha256) for item in sample_list)
    add_check(
        "raw_response_hashes_present",
        missing_raw_hash == 0,
        missing_raw_hash,
        "= 0 missing",
        "有效、失败和阻塞样本都必须可追溯到原始响应或原始失败快照。",
    )
    unclassified_valid = sum(
        item.status == SampleStatus.VALID and item.mention_class == MentionClass.UNKNOWN
        for item in sample_list
    )
    add_check(
        "valid_mentions_classified",
        unclassified_valid == 0,
        unclassified_valid,
        "= 0 unknown",
        "有效样本必须明确区分推荐、候选、提及、负面和未提及。",
    )

    add_check(
        "evidence_manifest_count_matches",
        len(manifest_list) == len(sample_list),
        len(manifest_list),
        f"= {len(sample_list)}",
        "每个任务样本都必须有独立证据清单，分析字段不能代替采集证据。",
    )
    manifest_sample_ids = [item.sample_id for item in manifest_list]
    add_check(
        "evidence_manifest_sample_ids_unique",
        len(manifest_sample_ids) == len(set(manifest_sample_ids)),
        len(manifest_sample_ids) - len(set(manifest_sample_ids)),
        "= 0 duplicates",
        "同一样本不能用多份证据清单重复满足门禁。",
    )
    surface_mismatches = sum(
        manifest is None
        or manifest.surface != sample.context.surface
        or manifest.evidence_level != sample.context.evidence_level
        for sample in sample_list
        for manifest in [manifests_by_sample_id.get(sample.sample_id)]
    )
    add_check(
        "surface_evidence_levels_match",
        surface_mismatches == 0,
        surface_mismatches,
        "= 0 mismatches",
        "API、Web、App 和人工导入必须保留各自证据等级，不得互相升级。",
    )

    valid_pairs = [
        (sample, manifests_by_sample_id.get(sample.sample_id))
        for sample in sample_list
        if sample.status == SampleStatus.VALID
    ]
    missing_request_metadata = sum(
        manifest is None or not _is_sha256(manifest.request_metadata_sha256)
        for _sample, manifest in valid_pairs
    )
    add_check(
        "valid_request_metadata_present",
        missing_request_metadata == 0,
        missing_request_metadata,
        "= 0 missing",
        "每个有效样本必须绑定内容寻址的请求与采集元数据。",
    )
    traced_pairs = [
        (sample, manifest)
        for sample, manifest in valid_pairs
        if sample.context.surface in {CollectorSurface.API, CollectorSurface.WEB, CollectorSurface.APP}
    ]
    missing_external_trace = sum(
        manifest is None or not manifest.external_trace_id
        for _sample, manifest in traced_pairs
    )
    add_check(
        "provider_trace_ids_present",
        missing_external_trace == 0,
        missing_external_trace,
        "= 0 missing",
        "API、Web 和 App 有效样本必须保留 Provider 请求或采集会话追踪 ID。",
    )
    api_pairs = [
        (sample, manifest)
        for sample, manifest in valid_pairs
        if sample.context.surface == CollectorSurface.API
    ]
    missing_provider_audit = sum(
        manifest is None or not manifest.provider_request_audit_id
        for _sample, manifest in api_pairs
    )
    add_check(
        "api_provider_audits_present",
        missing_provider_audit == 0,
        missing_provider_audit,
        "= 0 missing",
        "Provider API 样本必须关联真实请求审计，不能用浏览器截图冒充 API 调用。",
    )

    consumer_pairs = [
        (sample, manifest)
        for sample, manifest in valid_pairs
        if sample.context.surface in {CollectorSurface.WEB, CollectorSurface.APP}
    ]
    missing_conversation_isolation = sum(
        manifest is None or not manifest.conversation_isolation_verified
        for _sample, manifest in consumer_pairs
    )
    add_check(
        "consumer_conversation_isolation_verified",
        missing_conversation_isolation == 0,
        missing_conversation_isolation,
        "= 0 unverified",
        "Consumer Web/App 有效样本必须由采集器确认进入全新会话，不能只依赖不同的本地 session ID。",
    )
    missing_consumer_screenshot = sum(
        manifest is None
        or not manifest.screenshot_ref_id
        or not _is_sha256(manifest.screenshot_sha256)
        or not manifest.screenshot_immutable
        for _sample, manifest in consumer_pairs
    )
    add_check(
        "consumer_screenshots_complete",
        missing_consumer_screenshot == 0,
        missing_consumer_screenshot,
        "= 0 missing",
        "Consumer Web/App 有效样本必须绑定不可变截图对象及 SHA-256。",
    )
    uninspected_source_panels = sum(
        manifest is None or manifest.source_panel_status not in {"captured", "not_present"}
        for _sample, manifest in consumer_pairs
    )
    add_check(
        "consumer_source_panels_inspected",
        uninspected_source_panels == 0,
        uninspected_source_panels,
        "= 0 uninspected",
        "Consumer Web/App 必须明确记录来源面板已捕获或界面未呈现，不能留空猜测。",
    )
    inconsistent_source_panels = sum(
        manifest is None
        or (
            sample.citation_count > 0
            and (
                manifest.source_panel_status != "captured"
                or not manifest.source_panel_ref_id
                or not _is_sha256(manifest.source_panel_sha256)
                or not manifest.source_panel_immutable
            )
        )
        or (
            manifest.source_panel_status == "captured"
            and (
                not manifest.source_panel_ref_id
                or not _is_sha256(manifest.source_panel_sha256)
                or not manifest.source_panel_immutable
            )
        )
        for sample, manifest in consumer_pairs
    )
    add_check(
        "consumer_source_panel_evidence_consistent",
        inconsistent_source_panels == 0,
        inconsistent_source_panels,
        "= 0 inconsistent",
        "出现可引用来源时必须保存不可变来源面板对象；无来源时必须明确记录 not_present。",
    )
    app_pairs = [
        (sample, manifest)
        for sample, manifest in valid_pairs
        if sample.context.surface == CollectorSurface.APP
    ]
    missing_app_metadata = sum(
        manifest is None or not _is_sha256(manifest.app_capture_metadata_sha256)
        for _sample, manifest in app_pairs
    )
    add_check(
        "app_capture_metadata_present",
        missing_app_metadata == 0,
        missing_app_metadata,
        "= 0 missing",
        "Consumer App 样本必须记录内容寻址的设备、App 版本和采集环境元数据。",
    )
    import_pairs = [
        (sample, manifest)
        for sample, manifest in valid_pairs
        if sample.context.surface == CollectorSurface.MANUAL_IMPORT
    ]
    missing_import_provenance = sum(
        manifest is None or not _is_sha256(manifest.import_source_sha256)
        for _sample, manifest in import_pairs
    )
    add_check(
        "manual_import_provenance_present",
        missing_import_provenance == 0,
        missing_import_provenance,
        "= 0 missing",
        "人工导入样本必须保留导入源 SHA-256，且证据等级保持 manual_import。",
    )

    surface_evidence: list[SurfaceEvidenceSummary] = []
    for surface in CollectorSurface:
        surface_samples = [item for item in sample_list if item.context.surface == surface]
        if not surface_samples:
            continue
        valid_surface_samples = [item for item in surface_samples if item.status == SampleStatus.VALID]
        complete_count = 0
        screenshot_count = 0
        source_panel_captured_count = 0
        source_panel_not_present_count = 0
        for sample in valid_surface_samples:
            manifest = manifests_by_sample_id.get(sample.sample_id)
            if manifest is None:
                continue
            if manifest.screenshot_ref_id and _is_sha256(manifest.screenshot_sha256) and manifest.screenshot_immutable:
                screenshot_count += 1
            if manifest.source_panel_status == "captured":
                source_panel_captured_count += 1
            elif manifest.source_panel_status == "not_present":
                source_panel_not_present_count += 1
            if _surface_evidence_complete(sample, manifest):
                complete_count += 1
        surface_evidence.append(
            SurfaceEvidenceSummary(
                surface=surface.value,
                evidence_level=valid_surface_samples[0].context.evidence_level.value
                if valid_surface_samples
                else surface_samples[0].context.evidence_level.value,
                sample_count=len(surface_samples),
                valid_sample_count=len(valid_surface_samples),
                evidence_complete_count=complete_count,
                screenshot_count=screenshot_count,
                source_panel_captured_count=source_panel_captured_count,
                source_panel_not_present_count=source_panel_not_present_count,
                blocker_count=len(valid_surface_samples) - complete_count,
            )
        )

    limitations: list[str] = []
    valid_samples = [item for item in sample_list if item.status == SampleStatus.VALID]
    if valid_samples and not any(item.citation_count > 0 for item in valid_samples):
        limitations.append("valid_samples_have_no_provider_citations")
    if valid_samples and not any(item.citation_support_score is not None for item in valid_samples):
        limitations.append("citation_support_not_evaluated")
    if valid_samples and not any(item.fact_accuracy is not None for item in valid_samples):
        limitations.append("fact_accuracy_not_evaluated")
    if metrics.stability is None:
        limitations.append("repeat_stability_unavailable")

    data_payload = {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "run_id": run_id,
        "run_status": run_status,
        "signatures": signature_list,
        "samples": [
            {
                "sample_id": item.sample_id,
                "question_id": item.question_id,
                "status": item.status.value,
                "answer_sha256": item.answer_sha256,
                "raw_response_sha256": item.raw_response_sha256,
                "mention_class": item.mention_class.value,
                "brand_rank": item.brand_rank,
                "citation_count": item.citation_count,
                "failure_code": item.failure_code,
            }
            for item in sample_list
        ],
        "evidence_manifests": [item.to_record() for item in manifest_list],
    }
    data_sha256 = canonical_json_sha256(data_payload)
    publishable = all(item.status != "blocked" for item in checks)
    report_payload = {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "run_id": run_id,
        "run_status": run_status,
        "publishable": publishable,
        "data_sha256": data_sha256,
        "metrics": metrics.to_record(),
        "checks": [item.to_record() for item in checks],
        "surface_evidence": [item.to_record() for item in surface_evidence],
        "known_limitations": limitations,
    }
    return MeasurementQualityReport(
        contract_version=QUALITY_CONTRACT_VERSION,
        run_id=run_id,
        status="pass" if publishable else "blocked",
        publishable=publishable,
        data_sha256=data_sha256,
        report_sha256=canonical_json_sha256(report_payload),
        metrics=metrics,
        checks=tuple(checks),
        surface_evidence=tuple(surface_evidence),
        known_limitations=tuple(limitations),
    )


def _surface_evidence_complete(sample: MeasurementSample, manifest: SampleEvidenceManifest) -> bool:
    if (
        manifest.surface != sample.context.surface
        or manifest.evidence_level != sample.context.evidence_level
        or not _is_sha256(manifest.request_metadata_sha256)
    ):
        return False
    if sample.context.surface == CollectorSurface.API:
        return bool(manifest.external_trace_id and manifest.provider_request_audit_id)
    if sample.context.surface in {CollectorSurface.WEB, CollectorSurface.APP}:
        screenshot_complete = bool(
            manifest.external_trace_id
            and manifest.conversation_isolation_verified
            and manifest.screenshot_ref_id
            and _is_sha256(manifest.screenshot_sha256)
            and manifest.screenshot_immutable
        )
        source_panel_complete = (
            manifest.source_panel_status == "not_present" and sample.citation_count == 0
        ) or bool(
            manifest.source_panel_status == "captured"
            and manifest.source_panel_ref_id
            and _is_sha256(manifest.source_panel_sha256)
            and manifest.source_panel_immutable
        )
        app_complete = sample.context.surface != CollectorSurface.APP or bool(
            _is_sha256(manifest.app_capture_metadata_sha256)
        )
        return screenshot_complete and source_panel_complete and app_complete
    return _is_sha256(manifest.import_source_sha256)


def _is_sha256(value: str | None) -> bool:
    return bool(
        value
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )

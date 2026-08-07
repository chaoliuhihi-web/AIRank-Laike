from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from airank_domain.measurement import (
    CollectorSurface,
    EvidenceLevel,
    MeasurementSample,
    MentionClass,
    PromptCohortType,
    SampleContext,
    SampleStatus,
)
from airank_score import SampleEvidenceManifest
from apps.api import delivery_routes, retest_routes
from apps.api.main import app


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, retest_routes.InMemoryRetestRepository]:
    delivery = delivery_routes.InMemoryDeliveryRepository()
    retest = retest_routes.InMemoryRetestRepository()
    monkeypatch.setattr(delivery_routes, "DELIVERY_REPOSITORY", delivery)
    monkeypatch.setattr(retest_routes, "RETEST_REPOSITORY", retest)
    return TestClient(app), retest


def sample(index: int, *, mentioned: bool) -> MeasurementSample:
    answer = "AIRank 可作为候选。" if mentioned else "本次未发现目标品牌。"
    question_index = index // 3
    sample_index = index % 3 + 1
    return MeasurementSample(
        sample_id=f"sample_{index}",
        question_id=f"question_{question_index}",
        context=SampleContext(
            prompt_version_id=f"prompt_{question_index}",
            cohort_type=PromptCohortType.BLIND,
            sample_index=sample_index,
            session_id=f"session_{index}",
            surface=CollectorSurface.API,
            evidence_level=EvidenceLevel.PROVIDER_API,
            provider="qianwen",
            captured_at=NOW,
            model_name="qwen3.6-plus",
            search_enabled=True,
        ),
        status=SampleStatus.VALID,
        answer_text=answer,
        raw_response_sha256=f"{index:064x}",
        mention_class=MentionClass.RECOMMENDED if mentioned else MentionClass.NOT_MENTIONED,
        brand_rank=1 if mentioned else None,
    )


def evidence(index: int) -> SampleEvidenceManifest:
    return SampleEvidenceManifest(
        sample_id=f"sample_{index}",
        surface=CollectorSurface.API,
        evidence_level=EvidenceLevel.PROVIDER_API,
        request_metadata_sha256=f"{index + 1:064x}",
        external_trace_id=f"provider-request-{index}",
        provider_request_audit_id=f"provider-audit-{index}",
    )


def test_window_completion_recomputes_same_contract_and_is_idempotent(
    client: tuple[TestClient, retest_routes.InMemoryRetestRepository],
) -> None:
    http, repository = client
    delivery = delivery_routes.DELIVERY_REPOSITORY
    assert isinstance(delivery, delivery_routes.InMemoryDeliveryRepository)
    package = delivery_routes.PublishPackageData(
        package_id="package_1",
        tenant_id="tenant_1",
        project_id="project_1",
        asset_id="asset_1",
        snapshot_id="snapshot_1",
        content_review_id="review_1",
        channel="export",
        status="packaged",
        implementation_status="ready",
        idempotency_key="publish-package-1",
        content_sha256="a" * 64,
        created_at=NOW,
    )
    delivery.packages[("tenant_1", "package_1")] = package
    delivery.mark_published(
        "tenant_1",
        "package_1",
        delivery_routes.PublishEvidenceRequest(
            published_url="https://airank.example/evidence/1",
            baseline_run_id="run_t0",
            recorded_by="operator_1",
        ),
    )
    baseline = tuple(sample(index, mentioned=index < 3) for index in range(12))
    compare = tuple(sample(index, mentioned=index < 6) for index in range(12))
    signature = tuple(
        f"question_{index // 3}|qianwen|blind|api|{index % 3 + 1}|prompt_{index // 3}|qwen3.6-plus||True|zh-CN|"
        for index in range(12)
    )
    manifests = tuple(evidence(index) for index in range(12))
    repository.register_run("tenant_1", "run_t0", retest_routes.RunEvidence("project_1", baseline, signature, manifests))
    repository.register_run("tenant_1", "run_t7", retest_routes.RunEvidence("project_1", compare, signature, manifests))

    quality = http.get(
        "/api/v1/projects/project_1/scan-runs/run_t0/quality-report",
        headers={"tenant-id": "tenant_1", "X-AIRank-Trace-Id": "trc_quality_t0"},
    )

    windows = http.get(
        "/api/v1/projects/project_1/retest-windows",
        headers={"tenant-id": "tenant_1"},
    )
    window_id = next(item["window_id"] for item in windows.json()["data"] if item["window_label"] == "T+7")
    completed = http.post(
        f"/api/v1/retest-windows/{window_id}/complete",
        headers={"tenant-id": "tenant_1"},
        json={"compare_run_id": "run_t7", "completed_by": "operator_1"},
    )
    replay = http.post(
        f"/api/v1/retest-windows/{window_id}/complete",
        headers={"tenant-id": "tenant_1"},
        json={"compare_run_id": "run_t7", "completed_by": "operator_1"},
    )

    assert windows.status_code == 200
    assert quality.status_code == 200
    Draft202012Validator(
        json.loads((ROOT / "packages/contracts/measurement_quality_report_response.schema.json").read_text(encoding="utf-8"))
    ).validate(quality.json())
    assert quality.json()["data"]["publishable"] is True
    assert quality.json()["data"]["metrics"]["not_mentioned_count"] == 9
    assert completed.status_code == 200
    data = completed.json()["data"]
    assert data["comparable"] is True
    assert data["confidence"] == "medium"
    assert data["report_status"] == "generated"
    assert data["baseline_quality"]["publishable"] is True
    assert data["compare_quality"]["publishable"] is True
    assert data["metric_deltas"]["mention_rate"] == 0.25
    assert "不能据此证明因果" in data["conclusion"]
    assert len(data["report_sha256"]) == 64
    assert replay.json()["data"]["idempotent_replay"] is True


def test_window_completion_keeps_non_comparable_report_quality_blocked(
    client: tuple[TestClient, retest_routes.InMemoryRetestRepository],
) -> None:
    http, repository = client
    delivery = delivery_routes.DELIVERY_REPOSITORY
    assert isinstance(delivery, delivery_routes.InMemoryDeliveryRepository)
    package = delivery_routes.PublishPackageData(
        package_id="package_bad",
        tenant_id="tenant_bad",
        project_id="project_bad",
        asset_id="asset_bad",
        snapshot_id="snapshot_bad",
        content_review_id="review_bad",
        channel="export",
        status="packaged",
        implementation_status="ready",
        idempotency_key="publish-package-bad",
        content_sha256="a" * 64,
        created_at=NOW,
    )
    delivery.packages[("tenant_bad", "package_bad")] = package
    delivery.mark_published(
        "tenant_bad",
        "package_bad",
        delivery_routes.PublishEvidenceRequest(
            published_url="https://airank.example/evidence/bad",
            baseline_run_id="run_bad_t0",
            recorded_by="operator_bad",
        ),
    )
    baseline = tuple(sample(index, mentioned=False) for index in range(12))
    compare = tuple(sample(index, mentioned=True) for index in range(12))
    baseline_signature = tuple(f"baseline-{index}" for index in range(12))
    compare_signature = tuple(f"compare-{index}" for index in range(12))
    manifests = tuple(evidence(index) for index in range(12))
    repository.register_run("tenant_bad", "run_bad_t0", retest_routes.RunEvidence("project_bad", baseline, baseline_signature, manifests))
    repository.register_run("tenant_bad", "run_bad_t7", retest_routes.RunEvidence("project_bad", compare, compare_signature, manifests))
    windows = http.get("/api/v1/projects/project_bad/retest-windows", headers={"tenant-id": "tenant_bad"})
    window_id = next(item["window_id"] for item in windows.json()["data"] if item["window_label"] == "T+7")

    response = http.post(
        f"/api/v1/retest-windows/{window_id}/complete",
        headers={"tenant-id": "tenant_bad"},
        json={"compare_run_id": "run_bad_t7", "completed_by": "operator_bad"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["comparable"] is False
    assert data["report_status"] == "quality_blocked"
    assert "comparison:sample_contract_mismatch" in data["known_limitations"]

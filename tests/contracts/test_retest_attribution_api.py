from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
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
from apps.api import delivery_routes, retest_routes
from apps.api.main import app


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, retest_routes.InMemoryRetestRepository]:
    delivery = delivery_routes.InMemoryDeliveryRepository()
    retest = retest_routes.InMemoryRetestRepository()
    monkeypatch.setattr(delivery_routes, "DELIVERY_REPOSITORY", delivery)
    monkeypatch.setattr(retest_routes, "RETEST_REPOSITORY", retest)
    return TestClient(app), retest


def sample(index: int, *, mentioned: bool) -> MeasurementSample:
    answer = "AIRank 可作为候选。" if mentioned else "本次未发现目标品牌。"
    return MeasurementSample(
        sample_id=f"sample_{index}",
        question_id=f"question_{index}",
        context=SampleContext(
            prompt_version_id=f"prompt_{index}",
            cohort_type=PromptCohortType.BLIND,
            sample_index=1,
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
        mention_class=MentionClass.RECOMMENDED if mentioned else MentionClass.NOT_MENTIONED,
        brand_rank=1 if mentioned else None,
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
        f"question_{index}|qianwen|blind|api|1|prompt_{index}|qwen3.6-plus||True|zh-CN|"
        for index in range(12)
    )
    repository.register_run("tenant_1", "run_t0", retest_routes.RunEvidence("project_1", baseline, signature))
    repository.register_run("tenant_1", "run_t7", retest_routes.RunEvidence("project_1", compare, signature))

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
    assert completed.status_code == 200
    data = completed.json()["data"]
    assert data["comparable"] is True
    assert data["confidence"] == "medium"
    assert data["metric_deltas"]["mention_rate"] == 0.25
    assert "不能据此证明因果" in data["conclusion"]
    assert len(data["report_sha256"]) == 64
    assert replay.json()["data"]["idempotent_replay"] is True

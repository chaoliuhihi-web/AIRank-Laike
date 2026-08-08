from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from airank_domain.measurement import sha256_text
from apps.api import citation_support_routes
from apps.api.main import app


ANSWER = "AIRank 的指标可以下钻到原始样本，但发布内容不等于一定会被模型推荐。"
CITED = "AIRank 的指标可以从汇总结果下钻到原始回答和引用来源。"


@pytest.fixture()
def repository(monkeypatch: pytest.MonkeyPatch) -> citation_support_routes.InMemoryCitationSupportRepository:
    instance = citation_support_routes.InMemoryCitationSupportRepository()
    instance.seed_sample(
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snapshot_1",
        answer_text=ANSWER,
        citation_id="citation_1",
        cited_text=CITED,
    )
    monkeypatch.setattr(citation_support_routes, "CITATION_SUPPORT_REPOSITORY", instance)
    return instance


@pytest.fixture()
def client(repository: citation_support_routes.InMemoryCitationSupportRepository) -> TestClient:
    del repository
    return TestClient(app)


def create_claim(client: TestClient) -> str:
    response = client.post(
        "/api/v1/samples/snapshot_1/citation-claims",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted_reviewer"},
        json={
            "answer_start": 0,
            "answer_end": ANSWER.index("，"),
            "extraction_method": "manual",
            "created_by": "spoofed_actor",
        },
    )
    assert response.status_code == 201
    assert response.json()["data"]["created_by"] == "trusted_reviewer"
    return response.json()["data"]["claim_id"]


def test_selected_citation_and_provisional_support_are_reported_separately(client: TestClient) -> None:
    claim_id = create_claim(client)
    reviewed = client.post(
        f"/api/v1/citation-claims/{claim_id}/reviews",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted_reviewer"},
        json={
            "citation_id": "citation_1",
            "support_label": "supports",
            "evidence_grade": "provider_excerpt_only",
            "source_excerpt": CITED,
            "source_content_sha256": sha256_text(CITED),
            "rationale": "Provider 摘要与断言相关，但尚未保存来源页面。",
            "review_method": "human",
            "reviewed_by": "spoofed_actor",
        },
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["data"]["reviewed_by"] == "trusted_reviewer"
    assert reviewed.json()["data"]["commercially_verified"] is False

    bundle = client.get(
        "/api/v1/samples/snapshot_1/citation-support",
        headers={"tenant-id": "tenant_1"},
    )
    assert bundle.status_code == 200
    metrics = bundle.json()["data"]["metrics"]
    assert metrics["selected_citation_count"] == 1
    assert metrics["review_count"] == 1
    assert metrics["commercially_verified_review_count"] == 0
    assert metrics["citation_support_rate"] is None
    assert "citation_support_has_no_source_page_snapshot" in metrics["known_limitations"]


def test_source_page_snapshot_human_review_can_enter_support_rate(client: TestClient) -> None:
    claim_id = create_claim(client)
    repository = citation_support_routes.CITATION_SUPPORT_REPOSITORY
    assert isinstance(repository, citation_support_routes.InMemoryCitationSupportRepository)
    repository.seed_source_object(
        tenant_id="tenant_1",
        project_id="project_1",
        object_ref_id="object_source_page_1",
        sha256="b" * 64,
        kind="citation_source_page",
        citation_id="citation_1",
    )
    source_excerpt = "来源页面直接支持该断言。"
    repository.seed_source_capture(
        tenant_id="tenant_1",
        project_id="project_1",
        capture_id="capture_source_page_1",
        citation_id="citation_1",
        raw_object_ref_id="object_source_page_1",
        content_sha256="b" * 64,
        segment_id="segment_source_page_1",
        segment_text=source_excerpt,
    )
    reviewed = client.post(
        f"/api/v1/citation-claims/{claim_id}/reviews",
        headers={"tenant-id": "tenant_1"},
        json={
            "citation_id": "citation_1",
            "support_label": "supports",
            "evidence_grade": "source_page_snapshot",
            "source_excerpt": source_excerpt,
            "source_content_sha256": "b" * 64,
            "source_object_ref_id": "object_source_page_1",
            "source_capture_id": "capture_source_page_1",
            "source_segment_id": "segment_source_page_1",
            "source_start": 0,
            "source_end": len(source_excerpt),
            "rationale": "人工核对不可变页面快照后确认支持。",
            "review_method": "human",
            "reviewed_by": "reviewer_1",
        },
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["data"]["commercially_verified"] is True
    metrics = client.get(
        "/api/v1/samples/snapshot_1/citation-support",
        headers={"tenant-id": "tenant_1"},
    ).json()["data"]["metrics"]
    assert metrics["commercially_verified_review_count"] == 1
    assert metrics["citation_support_rate"] == 1.0


def test_source_page_snapshot_requires_exact_saved_source_boundary(client: TestClient) -> None:
    claim_id = create_claim(client)
    repository = citation_support_routes.CITATION_SUPPORT_REPOSITORY
    assert isinstance(repository, citation_support_routes.InMemoryCitationSupportRepository)
    repository.seed_source_object(
        tenant_id="tenant_1",
        project_id="project_1",
        object_ref_id="object_source_page_1",
        sha256="b" * 64,
        kind="citation_source_page",
        citation_id="citation_1",
    )
    repository.seed_source_capture(
        tenant_id="tenant_1",
        project_id="project_1",
        capture_id="capture_source_page_1",
        citation_id="citation_1",
        raw_object_ref_id="object_source_page_1",
        content_sha256="b" * 64,
        segment_id="segment_source_page_1",
        segment_text="来源页面直接支持该断言。",
    )

    response = client.post(
        f"/api/v1/citation-claims/{claim_id}/reviews",
        headers={"tenant-id": "tenant_1"},
        json={
            "citation_id": "citation_1",
            "support_label": "supports",
            "evidence_grade": "source_page_snapshot",
            "source_excerpt": "页面直接支持",
            "source_content_sha256": "b" * 64,
            "source_object_ref_id": "object_source_page_1",
            "source_capture_id": "capture_source_page_1",
            "source_segment_id": "segment_source_page_1",
            "source_start": 0,
            "source_end": len("页面直接支持"),
            "rationale": "边界与文本不一致，不能进入商业指标。",
            "review_method": "human",
            "reviewed_by": "reviewer_1",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CITATION_SUPPORT_EVIDENCE_INVALID"


def test_provider_excerpt_must_match_immutable_cited_text(client: TestClient) -> None:
    claim_id = create_claim(client)
    response = client.post(
        f"/api/v1/citation-claims/{claim_id}/reviews",
        headers={"tenant-id": "tenant_1"},
        json={
            "citation_id": "citation_1",
            "support_label": "supports",
            "evidence_grade": "provider_excerpt_only",
            "source_excerpt": "这段文字并不存在",
            "source_content_sha256": sha256_text(CITED),
            "rationale": "错误证据测试。",
            "reviewed_by": "reviewer_1",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CITATION_SUPPORT_EVIDENCE_INVALID"

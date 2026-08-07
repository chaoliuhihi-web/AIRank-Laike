from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from apps.api import delivery_routes, knowledge_routes
from apps.api.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        knowledge_routes, "KNOWLEDGE_REPOSITORY", knowledge_routes.InMemoryKnowledgeRepository()
    )
    monkeypatch.setattr(
        delivery_routes, "DELIVERY_REPOSITORY", delivery_routes.InMemoryDeliveryRepository()
    )
    return TestClient(app)


def source_payload() -> dict:
    return {
        "idempotency_key": "source-import-0001",
        "source_type": "official_document",
        "title": "AIRank 产品说明",
        "source_uri": "https://airank.example/product",
        "content_text": "AIRank 支持私有化部署。\n\n该能力需要企业版授权。",
        "authority_level": "official",
        "risk_level": "low",
    }


def fact_payload(source_ids: list[str], fact_text: str = "AIRank 支持私有化部署。") -> dict:
    return {
        "title": "部署能力",
        "fact_type": "product_service",
        "fact_text": fact_text,
        "source_ids": source_ids,
        "risk_level": "low",
        "disclosure": "public",
        "created_by": "operator_1",
    }


def test_source_import_is_content_addressed_segmented_and_idempotent(client: TestClient) -> None:
    first = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    )
    replay = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert len(first.json()["data"]["content_sha256"]) == 64
    assert first.json()["data"]["segment_count"] >= 1
    assert replay.json()["data"]["source_id"] == first.json()["data"]["source_id"]
    assert replay.json()["data"]["idempotent_replay"] is True


def test_fact_without_evidence_cannot_be_approved(client: TestClient) -> None:
    proposed = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload([]),
    )
    revision_id = proposed.json()["data"]["revision_id"]

    review = client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{revision_id}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_1"},
    )

    assert proposed.status_code == 201
    assert proposed.json()["data"]["eligibility_reason"] == "evidence_required"
    assert review.status_code == 400
    assert review.json()["error"]["code"] == "FACT_SOURCE_REQUIRED"


def test_open_conflict_blocks_approval_until_human_resolution(client: TestClient) -> None:
    source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    ).json()["data"]
    original = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload([source["source_id"]]),
    ).json()["data"]
    approved = client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{original['revision_id']}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_1"},
    )
    revised = client.post(
        f"/api/v1/projects/project_1/facts/{original['fact_id']}/revisions",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload([source["source_id"]], "AIRank 仅支持公有云部署。"),
    ).json()["data"]
    conflict = client.post(
        f"/api/v1/projects/project_1/facts/{original['fact_id']}/conflicts",
        headers={"tenant-id": "tenant_1"},
        json={
            "left_revision_id": original["revision_id"],
            "right_revision_id": revised["revision_id"],
            "conflict_type": "value_mismatch",
            "description": "部署模式陈述冲突",
        },
    )
    blocked = client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{revised['revision_id']}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_2"},
    )
    resolved = client.patch(
        f"/api/v1/projects/project_1/fact-conflicts/{conflict.json()['data']['conflict_id']}/resolve",
        headers={"tenant-id": "tenant_1"},
        json={
            "resolution": "resolved_right",
            "resolved_by": "reviewer_2",
            "resolution_note": "以最新官方资料为准",
        },
    )
    final_review = client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{revised['revision_id']}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_2"},
    )

    assert approved.status_code == 200
    assert approved.json()["data"]["eligible_for_generation"] is True
    assert conflict.status_code == 201
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "FACT_CONFLICT_OPEN"
    assert resolved.status_code == 200
    assert final_review.status_code == 200
    assert final_review.json()["data"]["eligible_for_generation"] is True


def test_content_generation_uses_only_approved_exact_source_facts(client: TestClient) -> None:
    source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    ).json()["data"]
    fact = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload([source["source_id"]]),
    ).json()["data"]
    before_review = client.post(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
        json={
            "asset_type": "fact_page",
            "title": "部署能力说明",
            "direction": "面向企业采购者解释部署能力。",
            "fact_revision_ids": [fact["revision_id"]],
            "created_by": "operator_1",
        },
    )
    client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{fact['revision_id']}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_1"},
    )
    generated = client.post(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
        json={
            "asset_type": "fact_page",
            "title": "部署能力说明",
            "direction": "面向企业采购者解释部署能力。",
            "fact_revision_ids": [fact["revision_id"]],
            "created_by": "operator_1",
        },
    )

    assert before_review.status_code == 409
    assert before_review.json()["error"]["code"] == "CONTENT_EVIDENCE_MISSING"
    assert generated.status_code == 201
    data = generated.json()["data"]
    assert data["generation_mode"] == "approved_fact_template"
    assert fact["revision_id"] in data["body_md"]
    assert len(data["claim_assertion_ids"]) == 1
    assert len(data["claim_support_ids"]) == 1


def test_review_snapshot_export_publication_and_retest_contract(client: TestClient) -> None:
    source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    ).json()["data"]
    fact = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload([source["source_id"]]),
    ).json()["data"]
    client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{fact['revision_id']}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_1"},
    )
    asset = client.post(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
        json={
            "asset_type": "fact_page",
            "title": "部署能力说明",
            "direction": "面向企业采购者解释部署能力。",
            "fact_revision_ids": [fact["revision_id"]],
            "created_by": "operator_1",
        },
    ).json()["data"]
    before_review = client.post(
        f"/api/v1/content-assets/{asset['asset_id']}/publish-packages",
        headers={"tenant-id": "tenant_1"},
        json={"channel": "export", "idempotency_key": "publish-export-0001", "requested_by": "operator_1"},
    )
    review = client.post(
        f"/api/v1/content-assets/{asset['asset_id']}/reviews",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_2"},
    )
    package = client.post(
        f"/api/v1/content-assets/{asset['asset_id']}/publish-packages",
        headers={"tenant-id": "tenant_1"},
        json={"channel": "export", "idempotency_key": "publish-export-0001", "requested_by": "operator_1"},
    )
    replay = client.post(
        f"/api/v1/content-assets/{asset['asset_id']}/publish-packages",
        headers={"tenant-id": "tenant_1"},
        json={"channel": "export", "idempotency_key": "publish-export-0001", "requested_by": "operator_1"},
    )
    exported = client.get(
        f"/api/v1/publish-packages/{package.json()['data']['package_id']}/export",
        headers={"tenant-id": "tenant_1"},
    )
    packages = client.get(
        "/api/v1/projects/project_1/publish-packages",
        headers={"tenant-id": "tenant_1"},
    )
    attempts = client.get(
        f"/api/v1/publish-packages/{package.json()['data']['package_id']}/attempts",
        headers={"tenant-id": "tenant_1"},
    )
    published = client.post(
        f"/api/v1/publish-packages/{package.json()['data']['package_id']}/publication-evidence",
        headers={"tenant-id": "tenant_1"},
        json={"published_url": "https://airank.example/evidence/deploy", "baseline_run_id": "run_baseline_1", "recorded_by": "operator_1"},
    )

    assert before_review.status_code == 409
    assert before_review.json()["error"]["code"] == "CONTENT_REVIEW_REQUIRED"
    assert review.status_code == 201
    assert review.json()["data"]["fact_check_status"] == "passed"
    assert package.status_code == 201
    assert package.json()["data"]["status"] == "packaged"
    assert replay.json()["data"]["idempotent_replay"] is True
    assert exported.json()["data"]["content_sha256"] == package.json()["data"]["content_sha256"]
    assert exported.json()["data"]["manifest"]["immutable"] is True
    assert packages.status_code == 200
    assert [item["package_id"] for item in packages.json()["data"]] == [package.json()["data"]["package_id"]]
    assert attempts.status_code == 200
    assert attempts.json()["data"] == []
    assert published.json()["data"]["status"] == "published"


def test_high_risk_geo_guarantee_requires_audited_override() -> None:
    findings = delivery_routes.scan_content_risk("保证被豆包推荐，并确保收录。")

    assert any(item.code == "guaranteed_ai_recommendation" and item.severity == "high" for item in findings)

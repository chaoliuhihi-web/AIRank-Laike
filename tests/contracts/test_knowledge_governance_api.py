from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from apps.api import delivery_routes, knowledge_routes, knowledge_sync_routes
from apps.api.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        knowledge_routes, "KNOWLEDGE_REPOSITORY", knowledge_routes.InMemoryKnowledgeRepository()
    )
    monkeypatch.setattr(
        delivery_routes, "DELIVERY_REPOSITORY", delivery_routes.InMemoryDeliveryRepository()
    )
    monkeypatch.setattr(
        knowledge_sync_routes,
        "KNOWLEDGE_SYNC_REPOSITORY",
        knowledge_sync_routes.InMemoryKnowledgeSyncRepository(),
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


def fact_payload(
    source_ids: list[str],
    fact_text: str = "AIRank 支持私有化部署。",
    *,
    subject_type: str = "general",
    subject_ref_id: str | None = None,
) -> dict:
    payload = {
        "title": "部署能力",
        "fact_type": "product_service",
        "fact_text": fact_text,
        "source_ids": source_ids,
        "risk_level": "low",
        "disclosure": "public",
        "created_by": "operator_1",
        "subject_type": subject_type,
    }
    if subject_ref_id is not None:
        payload["subject_ref_id"] = subject_ref_id
    return payload


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


def test_knowledge_source_sync_policy_is_versioned_idempotent_and_fail_closed(client: TestClient) -> None:
    source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    ).json()["data"]
    created = client.post(
        f"/api/v1/projects/project_1/knowledge-sources/{source['source_id']}/sync-policies",
        headers={"tenant-id": "tenant_1"},
        json={
            "idempotency_key": "knowledge-sync-policy-0001",
            "interval_hours": 24,
            "created_by": "operator_1",
        },
    )
    replay = client.post(
        f"/api/v1/projects/project_1/knowledge-sources/{source['source_id']}/sync-policies",
        headers={"tenant-id": "tenant_1"},
        json={
            "idempotency_key": "knowledge-sync-policy-0001",
            "interval_hours": 24,
            "created_by": "operator_1",
        },
    )
    policy_id = created.json()["data"]["policy_id"]
    runs = client.get(
        "/api/v1/projects/project_1/knowledge-source-sync-runs",
        headers={"tenant-id": "tenant_1"},
    )
    active_replay = client.post(
        f"/api/v1/knowledge-source-sync-policies/{policy_id}/runs",
        headers={"tenant-id": "tenant_1"},
        json={"idempotency_key": "knowledge-sync-manual-0001", "requested_by": "operator_1"},
    )
    stale_update = client.patch(
        f"/api/v1/knowledge-source-sync-policies/{policy_id}",
        headers={"tenant-id": "tenant_1"},
        json={
            "expected_version": 2,
            "enabled": False,
            "interval_hours": 48,
            "reason": "stale version must fail",
            "updated_by": "operator_1",
        },
    )
    disabled = client.patch(
        f"/api/v1/knowledge-source-sync-policies/{policy_id}",
        headers={"tenant-id": "tenant_1"},
        json={
            "expected_version": 1,
            "enabled": False,
            "interval_hours": 48,
            "reason": "pause customer-authorized source checks",
            "updated_by": "operator_1",
        },
    )
    blocked_trigger = client.post(
        f"/api/v1/knowledge-source-sync-policies/{policy_id}/runs",
        headers={"tenant-id": "tenant_1"},
        json={"idempotency_key": "knowledge-sync-manual-0002", "requested_by": "operator_1"},
    )

    assert created.status_code == 201
    assert created.json()["data"]["enabled"] is True
    assert replay.status_code == 201
    assert replay.json()["data"]["policy_id"] == policy_id
    assert replay.json()["data"]["idempotent_replay"] is True
    assert runs.status_code == 200 and len(runs.json()["data"]) == 1
    assert runs.json()["data"][0]["status"] == "queued"
    assert active_replay.status_code == 409
    assert active_replay.json()["error"]["code"] == "KNOWLEDGE_SYNC_ALREADY_ACTIVE"
    assert stale_update.status_code == 409
    assert stale_update.json()["error"]["code"] == "KNOWLEDGE_SYNC_VERSION_CONFLICT"
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False
    assert disabled.json()["data"]["version"] == 2
    assert blocked_trigger.status_code == 409
    assert blocked_trigger.json()["error"]["code"] == "KNOWLEDGE_SYNC_POLICY_DISABLED"


def test_knowledge_source_without_public_url_cannot_enable_sync(client: TestClient) -> None:
    payload = source_payload() | {
        "idempotency_key": "source-no-url-0001",
        "source_uri": None,
    }
    source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=payload,
    ).json()["data"]

    response = client.post(
        f"/api/v1/projects/project_1/knowledge-sources/{source['source_id']}/sync-policies",
        headers={"tenant-id": "tenant_1"},
        json={
            "idempotency_key": "knowledge-sync-policy-no-url",
            "interval_hours": 24,
            "created_by": "operator_1",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "KNOWLEDGE_SYNC_SOURCE_NOT_ELIGIBLE"


def test_manual_sync_idempotency_is_scoped_to_policy(client: TestClient) -> None:
    first_source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    ).json()["data"]
    second_source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload()
        | {
            "idempotency_key": "source-import-policy-scope-0002",
            "title": "AIRank 公开帮助页",
            "source_uri": "https://airank.example/help",
            "content_text": "AIRank 公开帮助页。",
        },
    ).json()["data"]
    policy_ids = []
    for index, source in enumerate((first_source, second_source), start=1):
        created = client.post(
            f"/api/v1/projects/project_1/knowledge-sources/{source['source_id']}/sync-policies",
            headers={"tenant-id": "tenant_1"},
            json={
                "idempotency_key": f"knowledge-sync-policy-scope-000{index}",
                "interval_hours": 24,
                "created_by": "operator_1",
            },
        )
        assert created.status_code == 201
        policy_ids.append(created.json()["data"]["policy_id"])

    repository = knowledge_sync_routes.KNOWLEDGE_SYNC_REPOSITORY
    assert isinstance(repository, knowledge_sync_routes.InMemoryKnowledgeSyncRepository)
    for key, run in list(repository.runs.items()):
        repository.runs[key] = run.model_copy(update={"status": "unchanged"})

    triggered = [
        client.post(
            f"/api/v1/knowledge-source-sync-policies/{policy_id}/runs",
            headers={"tenant-id": "tenant_1"},
            json={"idempotency_key": "same-manual-request-key", "requested_by": "operator_1"},
        )
        for policy_id in policy_ids
    ]

    assert [response.status_code for response in triggered] == [201, 201]
    assert triggered[0].json()["data"]["run_id"] != triggered[1].json()["data"]["run_id"]
    assert triggered[1].json()["data"]["idempotent_replay"] is False


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
    duplicate = client.post(
        f"/api/v1/projects/project_1/facts/{original['fact_id']}/conflicts",
        headers={"tenant-id": "tenant_1"},
        json={
            "left_revision_id": revised["revision_id"],
            "right_revision_id": original["revision_id"],
            "conflict_type": "value_mismatch",
            "description": "同一修订对不能重复登记",
        },
    )

    assert approved.status_code == 200
    assert approved.json()["data"]["eligible_for_generation"] is True
    assert conflict.status_code == 201
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "FACT_CONFLICT_OPEN"
    assert resolved.status_code == 200
    assert final_review.status_code == 200
    assert final_review.json()["data"]["eligible_for_generation"] is True
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "STATE_CONFLICT"
    assert duplicate.json()["error"]["details"]["status"] == "resolved_right"


def test_governance_queue_exposes_expiry_alerts_and_open_conflicts(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    expired_payload = source_payload() | {
        "idempotency_key": "source-expired-0001",
        "title": "已过期资质",
        "content_text": "该资质已超过有效期。",
        "valid_until": (now - timedelta(days=2)).isoformat(),
    }
    expiring_payload = source_payload() | {
        "idempotency_key": "source-expiring-0001",
        "title": "即将到期产品资料",
        "valid_until": (now + timedelta(days=5)).isoformat(),
    }
    expired_source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=expired_payload,
    ).json()["data"]
    expiring_source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=expiring_payload,
    ).json()["data"]
    original_payload = fact_payload([expiring_source["source_id"]]) | {
        "valid_until": (now + timedelta(days=3)).isoformat(),
    }
    original = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=original_payload,
    ).json()["data"]
    assert client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{original['revision_id']}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_1"},
    ).status_code == 200
    revised = client.post(
        f"/api/v1/projects/project_1/facts/{original['fact_id']}/revisions",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload([expiring_source["source_id"]], "AIRank 仅支持公有云部署。"),
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
    ).json()["data"]

    conflicts = client.get(
        "/api/v1/projects/project_1/fact-conflicts?status=open",
        headers={"tenant-id": "tenant_1"},
    )
    other_tenant = client.get(
        "/api/v1/projects/project_1/fact-conflicts?status=open",
        headers={"tenant-id": "tenant_2"},
    )
    governance = client.get(
        "/api/v1/projects/project_1/knowledge-governance?within_days=7",
        headers={"tenant-id": "tenant_1"},
    )

    assert conflicts.status_code == 200
    assert [item["conflict_id"] for item in conflicts.json()["data"]] == [conflict["conflict_id"]]
    assert other_tenant.status_code == 200
    assert other_tenant.json()["data"] == []
    assert governance.status_code == 200
    data = governance.json()["data"]
    assert data["status"] == "attention_required"
    assert data["within_days"] == 7
    assert data["source_count"] == 2
    assert data["expired_source_count"] == 1
    assert data["expiring_source_count"] == 1
    assert data["expiring_fact_count"] == 1
    assert data["open_conflict_count"] == 1
    assert data["action_required_count"] == 4
    assert {item["kind"] for item in data["alerts"]} == {
        "source_expired",
        "source_expiring",
        "fact_expiring",
        "open_conflict",
    }
    assert any(item["entity_id"] == expired_source["source_id"] for item in data["alerts"])

    resolved = client.patch(
        f"/api/v1/projects/project_1/fact-conflicts/{conflict['conflict_id']}/resolve",
        headers={"tenant-id": "tenant_1"},
        json={
            "resolution": "resolved_right",
            "resolved_by": "reviewer_2",
            "resolution_note": "以最新官方资料为准",
        },
    )
    after = client.get(
        "/api/v1/projects/project_1/knowledge-governance?within_days=7",
        headers={"tenant-id": "tenant_1"},
    )
    assert resolved.status_code == 200
    assert after.json()["data"]["open_conflict_count"] == 0
    assert after.json()["data"]["action_required_count"] == 3


def test_source_revision_stales_parent_invalidates_fact_and_searches_only_current_segments(client: TestClient) -> None:
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
    assert client.patch(
        f"/api/v1/projects/project_1/fact-revisions/{fact['revision_id']}/review",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_1"},
    ).json()["data"]["eligible_for_generation"] is True

    revision_payload = source_payload() | {
        "idempotency_key": "source-import-0002",
        "title": "AIRank 产品说明 2026-08",
        "content_text": "AIRank 支持私有化部署和审计日志。\n\n旧版本没有审计日志说明。",
    }
    revised = client.post(
        f"/api/v1/projects/project_1/knowledge-sources/{source['source_id']}/revisions",
        headers={"tenant-id": "tenant_1"},
        json=revision_payload,
    )
    replay = client.post(
        f"/api/v1/projects/project_1/knowledge-sources/{source['source_id']}/revisions",
        headers={"tenant-id": "tenant_1"},
        json=revision_payload,
    )
    sources = client.get(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
    ).json()["data"]
    facts = client.get(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
    ).json()["data"]
    governance = client.get(
        "/api/v1/projects/project_1/knowledge-governance?within_days=30",
        headers={"tenant-id": "tenant_1"},
    ).json()["data"]
    search = client.get(
        "/api/v1/projects/project_1/knowledge-search",
        headers={"tenant-id": "tenant_1"},
        params={"q": "审计日志", "limit": 10},
    )
    other_tenant_search = client.get(
        "/api/v1/projects/project_1/knowledge-search",
        headers={"tenant-id": "tenant_2"},
        params={"q": "审计日志", "limit": 10},
    )

    assert revised.status_code == 201
    revised_data = revised.json()["data"]
    assert revised_data["parent_source_id"] == source["source_id"]
    assert revised_data["revision_number"] == 2
    assert revised_data["status"] == "active"
    assert replay.status_code == 201
    assert replay.json()["data"]["source_id"] == revised_data["source_id"]
    assert replay.json()["data"]["idempotent_replay"] is True
    assert {item["source_id"]: item["status"] for item in sources} == {
        source["source_id"]: "stale",
        revised_data["source_id"]: "active",
    }
    approved_fact = next(item for item in facts if item["revision_id"] == fact["revision_id"])
    assert approved_fact["eligible_for_generation"] is False
    assert approved_fact["eligibility_reason"] == "source_stale"
    assert governance["stale_source_count"] == 1
    assert any(item["kind"] == "source_stale" and item["entity_id"] == source["source_id"] for item in governance["alerts"])
    assert search.status_code == 200
    search_data = search.json()["data"]
    assert search_data["retrieval_mode"] == "lexical_only"
    assert search_data["vector_status"] == "not_configured"
    assert search_data["returned_count"] >= 1
    assert {item["source_id"] for item in search_data["results"]} == {revised_data["source_id"]}
    assert all(item["text"] == revision_payload["content_text"] for item in search_data["results"])
    assert other_tenant_search.status_code == 200
    assert other_tenant_search.json()["data"]["results"] == []

    stale_parent_retry = client.post(
        f"/api/v1/projects/project_1/knowledge-sources/{source['source_id']}/revisions",
        headers={"tenant-id": "tenant_1"},
        json=revision_payload | {
            "idempotency_key": "source-import-0003",
            "content_text": "AIRank 支持私有化部署、审计日志和混合检索。",
        },
    )
    assert stale_parent_retry.status_code == 409
    assert stale_parent_retry.json()["error"]["code"] == "STATE_CONFLICT"


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
    assert data["generation_mode"] == "evidence_bound_page_blueprint"
    assert data["skill_id"] == "intervention.page-blueprint"
    assert data["skill_version"] == "1.1.0"
    assert len(data["blueprint_sha256"]) == 64
    assert data["section_count"] == 3
    assert fact["revision_id"] in data["body_md"]
    assert "面向企业采购者解释部署能力" not in data["body_md"]
    assert len(data["claim_assertion_ids"]) == 1
    assert len(data["claim_support_ids"]) == 1
    listed = client.get(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"] == [data]


def test_fact_subject_binding_is_required_and_immutable(client: TestClient) -> None:
    source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    ).json()["data"]
    fact = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload(
            [source["source_id"]],
            subject_type="brand",
            subject_ref_id="subject_airank",
        ),
    )
    relabel = client.post(
        f"/api/v1/projects/project_1/facts/{fact.json()['data']['fact_id']}/revisions",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload(
            [source["source_id"]],
            subject_type="competitor",
            subject_ref_id="subject_peer",
        ),
    )

    assert fact.status_code == 201
    assert fact.json()["data"]["subject_type"] == "brand"
    assert fact.json()["data"]["subject_ref_id"] == "subject_airank"
    assert relabel.status_code == 409
    assert relabel.json()["error"]["code"] == "FACT_SUBJECT_IMMUTABLE"


def test_comparison_content_requires_complete_symmetric_exact_evidence(client: TestClient) -> None:
    subjects = [
        {"subject_id": "subject_airank", "display_name": "AIRank", "subject_type": "brand"},
        {"subject_id": "subject_peer", "display_name": "竞品甲", "subject_type": "competitor"},
    ]
    dimensions = [{"dimension_id": f"d{index}", "label": f"核验维度 {index}"} for index in range(1, 11)]
    cells = []
    revision_ids = []
    for subject in subjects:
        for dimension in dimensions:
            fact_text = f"{subject['display_name']} 在{dimension['label']}下的已核验事实。"
            source = client.post(
                "/api/v1/projects/project_1/knowledge-sources",
                headers={"tenant-id": "tenant_1"},
                json={
                    "idempotency_key": f"comparison-{subject['subject_id']}-{dimension['dimension_id']}",
                    "source_type": "official_document",
                    "title": f"{subject['display_name']} {dimension['label']}来源",
                    "content_text": fact_text,
                    "authority_level": "official",
                    "risk_level": "low",
                },
            ).json()["data"]
            fact = client.post(
                "/api/v1/projects/project_1/facts",
                headers={"tenant-id": "tenant_1"},
                json=fact_payload(
                    [source["source_id"]],
                    fact_text,
                    subject_type=subject["subject_type"],
                    subject_ref_id=subject["subject_id"],
                ) | {"title": f"{subject['display_name']} {dimension['label']}"},
            ).json()["data"]
            approved = client.patch(
                f"/api/v1/projects/project_1/fact-revisions/{fact['revision_id']}/review",
                headers={"tenant-id": "tenant_1"},
                json={"action": "approved", "reviewed_by": "reviewer_1"},
            )
            assert approved.status_code == 200
            revision_ids.append(fact["revision_id"])
            cells.append({"subject_id": subject["subject_id"], "dimension_id": dimension["dimension_id"], "fact_revision_ids": [fact["revision_id"]]})

    generic = client.post(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
        json={"asset_type": "comparison_page", "title": "绕过专用门禁", "direction": "只用一个事实", "fact_revision_ids": [revision_ids[0]], "created_by": "operator_1"},
    )
    generated = client.post(
        "/api/v1/projects/project_1/comparison-content-assets",
        headers={"tenant-id": "tenant_1"},
        json={"title": "不要直接复制的比较标题", "direction": "保持公平", "target_subject_id": "subject_airank", "subjects": subjects, "dimensions": dimensions, "cells": cells, "created_by": "operator_1"},
    )

    assert generic.status_code == 409
    assert generic.json()["error"]["code"] == "CONTENT_EVIDENCE_MISSING"
    assert generated.status_code == 201
    data = generated.json()["data"]
    assert data["generation_mode"] == "evidence_bound_comparison"
    assert data["skill_id"] == "intervention.comparison-builder"
    assert data["skill_version"] == "1.0.0"
    assert data["section_count"] == 10
    assert len(data["fact_revision_ids"]) == 20
    assert len(data["claim_assertion_ids"]) == 20
    assert len(data["claim_support_ids"]) == 20
    assert "不要直接复制的比较标题" not in data["body_md"]


def test_explainer_content_requires_role_coverage_length_and_brand_restraint(client: TestClient) -> None:
    roles = ["definition", "mechanism", "mechanism", "step", "step", "step", "criterion", "criterion", "misconception", "faq", "faq", "boundary"]
    assignments = []
    for index, role in enumerate(roles, start=1):
        fact_text = f"第{index}条已审核说明：" + "该事实基于当前有效来源的精确原文边界，用于解释适用范围、执行条件与验证方式，不扩展为来源之外的承诺。" * 3
        source = client.post(
            "/api/v1/projects/project_1/knowledge-sources",
            headers={"tenant-id": "tenant_1"},
            json={
                "idempotency_key": f"explainer-source-{index:02d}",
                "source_type": "official_document",
                "title": f"解释来源 {index}",
                "content_text": fact_text,
                "authority_level": "official",
                "risk_level": "low",
            },
        ).json()["data"]
        fact = client.post(
            "/api/v1/projects/project_1/facts",
            headers={"tenant-id": "tenant_1"},
            json=fact_payload(
                [source["source_id"]],
                fact_text,
                subject_type="brand",
                subject_ref_id="subject_airank",
            ) | {"title": f"解释证据 {index}"},
        ).json()["data"]
        assert client.patch(
            f"/api/v1/projects/project_1/fact-revisions/{fact['revision_id']}/review",
            headers={"tenant-id": "tenant_1"},
            json={"action": "approved", "reviewed_by": "reviewer_1"},
        ).status_code == 200
        assignments.append({"fact_revision_id": fact["revision_id"], "content_role": role})

    generated = client.post(
        "/api/v1/projects/project_1/explainer-content-assets",
        headers={"tenant-id": "tenant_1"},
        json={
            "title": "不进入正文的解释 brief",
            "direction": "面向采购者完整解释",
            "subject_id": "subject_airank",
            "subject_type": "brand",
            "display_name": "AIRank",
            "brand_names": ["来客"],
            "assignments": assignments,
            "created_by": "operator_1",
        },
    )

    assert generated.status_code == 201
    data = generated.json()["data"]
    assert data["generation_mode"] == "evidence_bound_explainer"
    assert data["skill_id"] == "intervention.explainer-builder"
    assert data["section_count"] == 7
    assert len(data["fact_revision_ids"]) == 12
    assert len(data["claim_assertion_ids"]) == 12
    assert len(data["claim_support_ids"]) == 12
    assert "不进入正文的解释 brief" not in data["body_md"]


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
    reviewed_assets = client.get(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
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
    invalid_screenshot_pair = client.post(
        f"/api/v1/publish-packages/{package.json()['data']['package_id']}/publication-evidence",
        headers={"tenant-id": "tenant_1"},
        json={
            "published_url": "https://airank.example/evidence/deploy",
            "baseline_run_id": "run_baseline_1",
            "recorded_by": "operator_1",
            "screenshot_ref_id": "object_publication_1",
        },
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
    assert reviewed_assets.json()["data"][0]["status"] == "approved"
    assert package.status_code == 201
    assert package.json()["data"]["status"] == "packaged"
    assert replay.json()["data"]["idempotent_replay"] is True
    assert exported.json()["data"]["content_sha256"] == package.json()["data"]["content_sha256"]
    assert exported.json()["data"]["manifest"]["immutable"] is True
    assert exported.json()["data"]["manifest"]["contract_version"] == "airank.publish-snapshot.v2"
    assert exported.json()["data"]["manifest"]["blueprint_sha256"] == asset["blueprint_sha256"]
    assert exported.json()["data"]["manifest"]["generation_skill"] == {
        "skill_id": "intervention.page-blueprint",
        "version": "1.1.0",
    }
    assert packages.status_code == 200
    assert [item["package_id"] for item in packages.json()["data"]] == [package.json()["data"]["package_id"]]
    assert attempts.status_code == 200
    assert attempts.json()["data"] == []
    assert invalid_screenshot_pair.status_code == 422
    assert published.json()["data"]["status"] == "published"


def test_high_risk_geo_guarantee_requires_audited_override() -> None:
    findings = delivery_routes.scan_content_risk("保证被豆包推荐，并确保收录。")

    assert any(item.code == "guaranteed_ai_recommendation" and item.severity == "high" for item in findings)


def test_content_review_checks_title_and_each_assertion_support(
    client: TestClient,
) -> None:
    source = client.post(
        "/api/v1/projects/project_1/knowledge-sources",
        headers={"tenant-id": "tenant_1"},
        json=source_payload(),
    ).json()["data"]
    first = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=fact_payload([source["source_id"]]),
    ).json()["data"]
    second_payload = fact_payload([source["source_id"]]) | {
        "title": "授权条件",
        "fact_text": "该能力需要企业版授权。",
    }
    second = client.post(
        "/api/v1/projects/project_1/facts",
        headers={"tenant-id": "tenant_1"},
        json=second_payload,
    ).json()["data"]
    for fact in (first, second):
        client.patch(
            f"/api/v1/projects/project_1/fact-revisions/{fact['revision_id']}/review",
            headers={"tenant-id": "tenant_1"},
            json={"action": "approved", "reviewed_by": "reviewer_1"},
        )

    risky_asset = client.post(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
        json={
            "asset_type": "fact_page",
            "title": "保证被豆包推荐",
            "direction": "只使用审核事实。",
            "fact_revision_ids": [first["revision_id"]],
            "created_by": "operator_1",
        },
    ).json()["data"]
    repository = knowledge_routes.KNOWLEDGE_REPOSITORY
    assert isinstance(repository, knowledge_routes.InMemoryKnowledgeRepository)
    stored_risky_asset = repository.content_assets[("tenant_1", risky_asset["asset_id"])]
    repository.content_assets[("tenant_1", risky_asset["asset_id"])] = (
        stored_risky_asset.model_copy(update={"title": "保证被豆包推荐"})
    )
    risky_review = client.post(
        f"/api/v1/content-assets/{risky_asset['asset_id']}/reviews",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_2"},
    )
    assert risky_review.status_code == 409
    assert risky_review.json()["error"]["code"] == "CONTENT_RISK_OVERRIDE_REQUIRED"

    safe_asset = client.post(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
        json={
            "asset_type": "fact_page",
            "title": "可验证能力说明",
            "direction": "只使用审核事实。",
            "fact_revision_ids": [first["revision_id"], second["revision_id"]],
            "created_by": "operator_1",
        },
    ).json()["data"]
    missing_support_id = safe_asset["claim_support_ids"][1]
    repository.claim_support_links[("tenant_1", missing_support_id)] = safe_asset[
        "claim_assertion_ids"
    ][0]
    uncovered_review = client.post(
        f"/api/v1/content-assets/{safe_asset['asset_id']}/reviews",
        headers={"tenant-id": "tenant_1"},
        json={"action": "approved", "reviewed_by": "reviewer_2"},
    )
    assert uncovered_review.status_code == 409
    assert uncovered_review.json()["error"]["code"] == "CONTENT_EVIDENCE_MISSING"


def test_content_generation_fails_when_source_content_hash_no_longer_matches(
    client: TestClient,
) -> None:
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
    repository = knowledge_routes.KNOWLEDGE_REPOSITORY
    assert isinstance(repository, knowledge_routes.InMemoryKnowledgeRepository)
    repository.source_contents[("tenant_1", source["source_id"])] += "tampered"

    generated = client.post(
        "/api/v1/projects/project_1/content-assets",
        headers={"tenant-id": "tenant_1"},
        json={
            "asset_type": "fact_page",
            "title": "完整性失败测试",
            "direction": "不得接受被篡改来源。",
            "fact_revision_ids": [fact["revision_id"]],
            "created_by": "operator_1",
        },
    )

    assert generated.status_code == 409
    assert generated.json()["error"]["code"] == "CONTENT_EVIDENCE_MISSING"
    assert generated.json()["error"]["details"]["reason"] == "source_content_integrity_failed"


def test_active_embedded_content_is_high_risk() -> None:
    findings = delivery_routes.scan_content_risk("<script>alert('x')</script>")

    assert any(item.code == "embedded_active_content" and item.severity == "high" for item in findings)

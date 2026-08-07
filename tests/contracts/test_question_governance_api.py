from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.main import app


def _headers(tenant_id: str, trace_id: str) -> dict[str, str]:
    return {"tenant-id": tenant_id, "X-AIRank-Trace-Id": trace_id}


def test_question_map_compiles_deduplicates_persists_and_requires_review() -> None:
    client = TestClient(app)
    tenant_id = f"tenant_qgov_{uuid4().hex[:10]}"
    project = client.post(
        "/api/v1/projects",
        headers=_headers(tenant_id, "trc_qgov_project"),
        json={"website_url": "https://airank-question.example", "brand_name_hint": "AIRank"},
    ).json()["data"]

    payload = {
        "product_terms": ["GEO 平台"],
        "competitor_names": ["竞品甲"],
        "regions": ["北京"],
        "seed_questions": ["企业怎么选 GEO 平台？", " 企业怎么选GEO平台! "],
        "include_template_candidates": True,
        "persist": True,
        "created_by": "reviewer_qgov",
    }
    compiled = client.post(
        f"/api/v1/projects/{project['project_id']}/question-maps/compile",
        headers=_headers(tenant_id, "trc_qgov_compile"),
        json=payload,
    )

    assert compiled.status_code == 201, compiled.text
    data = compiled.json()["data"]
    assert data["taxonomy_version"] == "airank-question-taxonomy-v1.1.0"
    assert data["duplicate_count"] >= 1
    assert data["persisted_count"] == data["question_count"]
    assert {item["cohort_type"] for item in data["questions"]} >= {"blind", "comparison"}
    assert all(item["observed_query"] is False for item in data["questions"])
    assert all(item["status"] == "suggested" for item in data["questions"])

    replay = client.post(
        f"/api/v1/projects/{project['project_id']}/question-maps/compile",
        headers=_headers(tenant_id, "trc_qgov_replay"),
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["idempotent_replay"] is True
    assert replay.json()["data"]["map_version_id"] == data["map_version_id"]

    questions = client.get(
        f"/api/v1/projects/{project['project_id']}/buyer-questions",
        headers=_headers(tenant_id, "trc_qgov_questions"),
    ).json()["data"]
    assert len(questions) == data["persisted_count"]
    question = questions[0]
    assert question["status"] == "suggested"
    assert question["question_version_id"].startswith("question_v_")

    reviewed = client.patch(
        f"/api/v1/projects/{project['project_id']}/buyer-questions/{question['question_id']}/review",
        headers=_headers(tenant_id, "trc_qgov_review"),
        json={"action": "confirmed", "reviewed_by": "reviewer_qgov", "review_note": "问题意图与目标客户一致。"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["eligible_for_measurement"] is True

    refreshed = client.get(
        f"/api/v1/projects/{project['project_id']}/buyer-questions",
        headers=_headers(tenant_id, "trc_qgov_refreshed"),
    ).json()["data"]
    confirmed = next(item for item in refreshed if item["question_id"] == question["question_id"])
    assert confirmed["status"] == "confirmed"
    assert confirmed["reviewed_by"] == "reviewer_qgov"

    foreign = client.get(
        f"/api/v1/projects/{project['project_id']}/question-maps",
        headers=_headers("tenant_qgov_foreign", "trc_qgov_foreign"),
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_question_map_preview_does_not_persist_candidates() -> None:
    client = TestClient(app)
    tenant_id = f"tenant_qpreview_{uuid4().hex[:10]}"
    project_id = client.post(
        "/api/v1/projects",
        headers=_headers(tenant_id, "trc_qpreview_project"),
        json={"website_url": "https://preview-question.example", "brand_name_hint": "PreviewBrand"},
    ).json()["data"]["project_id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/question-maps/compile",
        headers=_headers(tenant_id, "trc_qpreview_compile"),
        json={
            "seed_questions": ["企业如何选择 GEO 服务商？"],
            "include_template_candidates": False,
            "persist": False,
            "created_by": "reviewer_preview",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["status"] == "preview"
    assert response.json()["data"]["persisted_count"] == 0
    questions = client.get(
        f"/api/v1/projects/{project_id}/buyer-questions",
        headers=_headers(tenant_id, "trc_qpreview_questions"),
    )
    assert questions.status_code == 200
    assert questions.json()["data"] == []

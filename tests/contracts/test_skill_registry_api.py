from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app


def test_admin_skill_registry_exposes_eight_partial_internal_skills() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/admin/skills", headers={"X-AIRank-Trace-Id": "trc_skill_registry"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_skill_registry"
    assert len(body["data"]["skills"]) == 8
    assert {item["status"] for item in body["data"]["skills"]} == {"partial"}
    assert all(item["eval_cases"] for item in body["data"]["skills"])


def test_admin_skill_eval_executes_versioned_runner() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/skills/measurement.answer-parser/eval",
        headers={"X-AIRank-Trace-Id": "trc_skill_eval"},
        json={"input": {"answer_text": "推荐其他品牌。", "brand_name": "AIRank"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["skill_id"] == "measurement.answer-parser"
    assert body["data"]["version"] == "1.0.0"
    assert body["data"]["manifest_status"] == "partial"
    assert body["data"]["output"]["mention_class"] == "not_mentioned"


def test_admin_skill_eval_rejects_invalid_input_and_unknown_skill() -> None:
    client = TestClient(app)

    invalid = client.post(
        "/api/v1/admin/skills/measurement.answer-parser/eval",
        headers={"X-AIRank-Trace-Id": "trc_skill_invalid"},
        json={"input": {"answer_text": "missing brand"}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_FAILED"

    missing = client.post(
        "/api/v1/admin/skills/measurement.unknown/eval",
        headers={"X-AIRank-Trace-Id": "trc_skill_missing"},
        json={"input": {}},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SKILL_NOT_FOUND"

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app


def test_brand_check_creates_completed_visibility_loop() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/brand-checks",
        headers={"tenant-id": "tenant_brand_check", "X-AIRank-Trace-Id": "trc_brand_check"},
        json={
            "brand_name": "中关村软件园孵化器",
            "website_url": "https://www.zpark.com",
            "industry_hint": "科技企业孵化与产业服务",
            "competitor_hints": ["中关村创业大街", "清华科技园"],
            "buyer_questions": ["中关村软件园孵化器适合哪些创业团队？"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_brand_check"
    assert body["data"]["project"]["brand_name"] == "中关村软件园孵化器"
    assert body["data"]["scan_run"]["status"] == "completed"
    assert len(body["data"]["tasks"]) == 7
    assert {task["status"] for task in body["data"]["tasks"]} == {"completed"}
    assert body["data"]["asset_bundle"]["assets"]
    assert body["data"]["reports"]["reports"]
    assert body["data"]["overview"]["project"]["name"] == "中关村软件园孵化器"

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api import main as api_main
from apps.api.main import app


def test_brand_check_without_real_provider_is_explicitly_unverified() -> None:
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
    assert body["data"]["scan_run"]["status"] == "failed"
    assert body["data"]["scan_run"]["metrics"]["data_status"] == "unverified_no_provider_evidence"
    assert len(body["data"]["tasks"]) == 21
    assert {task["status"] for task in body["data"]["tasks"]} == {"failed"}
    assert body["data"]["asset_bundle"]["assets"] == []
    assert body["data"]["reports"]["reports"] == []
    assert body["data"]["overview"]["project"]["name"] == "中关村软件园孵化器"


def test_brand_check_preflights_browser_readiness_before_writing(monkeypatch) -> None:
    class FailingProjectRepository:
        def create_project(self, *_args, **_kwargs):
            raise AssertionError("brand check must not create a project when providers are blocked")

    monkeypatch.setenv("AIRANK_DATABASE_URL", "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_test")
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "browser")
    monkeypatch.setattr(api_main, "PROJECT_REPOSITORY", FailingProjectRepository())
    monkeypatch.setattr(api_main, "find_existing_mysql_brand_project", lambda _tenant_id, _payload: None)
    monkeypatch.setattr(
        api_main,
        "build_provider_readiness_items",
        lambda _scope: [
            api_main.ProviderReadinessItem(
                provider=provider,
                label=api_main.PROVIDER_LABELS[provider],
                status="blocked",
                url=f"https://{provider}.example.test",
                profile_dir=f"/profiles/{provider}",
                headless=True,
                blocker_code="login_required",
                reason="login required",
            )
            for provider in api_main.DEFAULT_PROVIDER_SCOPE
        ],
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/brand-checks",
        headers={"tenant-id": "tenant_brand_check", "X-AIRank-Trace-Id": "trc_brand_blocked"},
        json={
            "brand_name": "小米鱼缸",
            "website_url": "https://www.mi.com/",
            "industry_hint": "智能家居",
            "buyer_questions": ["家用智能鱼缸应该选择小米鱼缸还是其他品牌？"],
        },
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "INTEGRATION_CAPABILITY_BLOCKED"
    assert body["error"]["trace_id"] == "trc_brand_blocked"
    assert body["error"]["details"]["ready_count"] == 0
    assert body["error"]["details"]["minimum_success_count"] == len(api_main.DEFAULT_PROVIDER_SCOPE)
    assert {item["blocker_code"] for item in body["error"]["details"]["providers"]} == {"login_required"}

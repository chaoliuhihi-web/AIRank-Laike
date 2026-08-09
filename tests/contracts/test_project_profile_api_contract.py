from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from apps.api import main as api_main
from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
PROFILE_RESPONSE_SCHEMA = ROOT / "packages" / "contracts" / "project_profile_response.schema.json"


def create_project(projects: api_main.InMemoryProjectRepository, tenant_id: str) -> api_main.ProjectData:
    return projects.create_project(
        tenant_id,
        api_main.ProjectCreateRequest(
            website_url="https://www.intel.cn/content/www/cn/zh/architecture-and-technology/ai-pc.html",
            brand_name_hint="Intel AI PC",
            industry_hint="AI PC 与商用终端计算",
        ),
    )


def test_project_profile_read_update_and_conflict_contract(monkeypatch) -> None:
    projects = api_main.InMemoryProjectRepository()
    monkeypatch.setattr(api_main, "PROJECT_REPOSITORY", projects)
    tenant_id = "tenant_intel_aipc"
    project = create_project(projects, tenant_id)
    client = TestClient(app)

    current_response = client.get(
        f"/api/v1/projects/{project.project_id}",
        headers={"tenant-id": tenant_id, "X-AIRank-Trace-Id": "trc_profile_read"},
    )
    assert current_response.status_code == 200
    current = current_response.json()["data"]
    assert current["contract_version"] == "airank.project-profile.v1"
    assert current["measurement_reset_required"] is True

    update_payload = {
        "brand_name": "Intel AI PC",
        "company_name": "英特尔",
        "website_url": "https://www.intel.cn/content/www/cn/zh/architecture-and-technology/ai-pc.html",
        "industry": "AI PC 与商用终端计算",
        "region": "中国大陆",
        "products": ["Intel Core Ultra 处理器驱动的 AI PC"],
        "selling_points": ["CPU、GPU 与 NPU 协同承担 AI 工作负载"],
        "audiences": ["企业 IT 决策者", "商用电脑采购负责人"],
        "expected_updated_at": current["updated_at"],
        "change_note": "将测量对象收敛为 Intel AI PC",
    }
    updated_response = client.patch(
        f"/api/v1/projects/{project.project_id}",
        headers={
            "tenant-id": tenant_id,
            "X-AIRank-Trace-Id": "trc_profile_update",
            "X-AIRank-User-Id": "user_profile_editor",
        },
        json=update_payload,
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()["data"]
    assert updated["brand_name"] == "Intel AI PC"
    assert updated["profile_revision"] == 1
    assert updated["updated_by"] == "user_profile_editor"
    assert updated["measurement_reset_required"] is True
    schema = json.loads(PROFILE_RESPONSE_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(updated_response.json())

    conflict_response = client.patch(
        f"/api/v1/projects/{project.project_id}",
        headers={"tenant-id": tenant_id, "X-AIRank-User-Id": "user_stale_editor"},
        json=update_payload,
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["error"]["code"] == "STATE_VERSION_CONFLICT"


def test_profile_update_preserves_old_scan_but_removes_it_from_current_measurement(monkeypatch) -> None:
    projects = api_main.InMemoryProjectRepository()
    scans = api_main.InMemoryScanRepository()
    monkeypatch.setattr(api_main, "PROJECT_REPOSITORY", projects)
    monkeypatch.setattr(api_main, "SCAN_REPOSITORY", scans)
    tenant_id = "tenant_profile_scope"
    project = create_project(projects, tenant_id)
    question = projects.create_buyer_question(
        tenant_id,
        project.project_id,
        api_main.BuyerQuestionCreateRequest(
            question_text="企业采购 AI PC 时应评估哪些平台？",
            recommended_providers=["doubao"],
            status="confirmed",
        ),
    )
    old_run = scans.create_run(
        tenant_id,
        api_main.ScanRunCreateRequest(
            project_id=project.project_id,
            run_type="baseline",
            cohort_type="blind",
            repetitions=3,
            collector_surfaces=["api"],
            provider_scope=["doubao"],
            question_scope=api_main.QuestionScope(mode="selected", question_ids=[question.question_id]),
        ),
    )
    current = projects.get_profile(tenant_id, project.project_id)
    projects.update_profile(
        tenant_id,
        project.project_id,
        api_main.ProjectProfileUpdateRequest(
            brand_name="Intel AI PC",
            company_name="英特尔",
            website_url=current.website_url,
            industry=current.industry,
            products=["Intel Core Ultra AI PC"],
            audiences=["企业 IT 决策者"],
            expected_updated_at=current.updated_at,
            change_note="补充 Intel AIPC 测量口径",
        ),
        "user_profile_editor",
    )

    response = TestClient(app).get(
        f"/api/v1/projects/{project.project_id}/growth-loop",
        headers={"tenant-id": tenant_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert scans.get_run(tenant_id, old_run.run_id).run_id == old_run.run_id
    assert data["counts"]["scan_runs"] == 0
    assert data["counts"]["valid_samples"] == 0
    assert data["conclusion_readiness"]["state"] == "blocked"
    assert data["conclusion_readiness"]["reason_codes"] == ["PROJECT_PROFILE_CHANGED_RESCAN_REQUIRED"]
    assert "历史扫描保留为旧口径证据" in data["conclusion_readiness"]["message"]

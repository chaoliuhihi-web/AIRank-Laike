from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api import main as api_main
from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages" / "contracts" / "console_overview.schema.json"


def test_console_overview_api_matches_contract() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/console/overview",
        headers={"tenant-id": "tenant_demo", "X-AIRank-Trace-Id": "trc_test_console"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_test_console"
    assert body["data"]["data_status"] == "empty"
    assert body["data"]["metric_cards"] == []
    assert body["data"]["project"]["id"] == ""

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(body["data"])


def test_growth_loop_uses_one_conservative_conclusion_gate(monkeypatch) -> None:
    projects = api_main.InMemoryProjectRepository()
    scans = api_main.InMemoryScanRepository()
    monkeypatch.setattr(api_main, "PROJECT_REPOSITORY", projects)
    monkeypatch.setattr(api_main, "SCAN_REPOSITORY", scans)
    tenant_id = "tenant_growth_loop"
    project = projects.create_project(
        tenant_id,
        api_main.ProjectCreateRequest(
            website_url="https://airank.example.com",
            brand_name_hint="AIRank",
            industry_hint="GEO",
        ),
    )
    projects.create_buyer_question(
        tenant_id,
        project.project_id,
        api_main.BuyerQuestionCreateRequest(
            question_text="企业应该如何选择 GEO 监测平台？",
            recommended_providers=["doubao", "qianwen"],
            status="confirmed",
        ),
    )
    client = TestClient(app)

    response = client.get(
        f"/api/v1/projects/{project.project_id}/growth-loop",
        headers={"tenant-id": tenant_id, "X-AIRank-Trace-Id": "trc_growth_loop"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_growth_loop"
    assert body["data"]["contract_version"] == "airank.growth-loop.v1"
    assert body["data"]["current_step"] == "scans"
    assert body["data"]["conclusion_readiness"]["state"] == "blocked"
    assert body["data"]["conclusion_readiness"]["valid_sample_count"] == 0
    assert body["data"]["conclusion_readiness"]["reason_codes"] == ["SCAN_RUN_MISSING"]
    assert [step["status"] for step in body["data"]["steps"]] == [
        "completed",
        "current",
        "blocked",
        "blocked",
        "blocked",
        "blocked",
    ]

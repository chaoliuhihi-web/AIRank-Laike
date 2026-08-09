from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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


def test_growth_loop_requires_quality_and_a_real_gap_derivation_before_assets(monkeypatch) -> None:
    from apps.api import delivery_routes, evidence_gap_routes, knowledge_routes, retest_routes

    now = api_main.utc_now()
    run = SimpleNamespace(
        run_id="scan_run_quality",
        created_at=now,
        finished_at=now,
        updated_at=now,
        status="completed",
        provider_scope=["doubao"],
        question_scope=SimpleNamespace(question_ids=["question_1"]),
        metrics={"data_status": "provider_evidence", "provider_success_count": 3, "minimum_success_count": 3},
    )

    class Projects:
        def list_buyer_questions(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return [SimpleNamespace(status="confirmed")]

        def get_profile(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return SimpleNamespace(updated_at=now)

    class Scans:
        def list_runs(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return [run]

        def list_tasks(self, tenant_id, run_id):  # noqa: ANN001, ANN202
            return [SimpleNamespace(status="completed") for _ in range(3)]

    class Gaps:
        derivation_complete = False

        def list(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return SimpleNamespace(governed_gap_count=0)

        def has_successful_derivation(self, tenant_id, project_id, run_id):  # noqa: ANN001, ANN202
            return self.derivation_complete

    class Knowledge:
        def list_facts(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return [SimpleNamespace(status="approved", eligible_for_generation=True)]

        def list_governed_content(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return []

    class Delivery:
        def list_packages(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return []

    class Retest:
        publishable = False

        def get_quality_report(self, tenant_id, project_id, run_id):  # noqa: ANN001, ANN202
            return {
                "publishable": self.publishable,
                "checks": [{"code": "independent_repetitions_complete", "status": "blocked"}],
            }

        def list_windows(self, tenant_id, project_id):  # noqa: ANN001, ANN202
            return []

    gaps = Gaps()
    retest = Retest()
    monkeypatch.setattr(api_main, "PROJECT_REPOSITORY", Projects())
    monkeypatch.setattr(api_main, "SCAN_REPOSITORY", Scans())
    monkeypatch.setattr(evidence_gap_routes, "EVIDENCE_GAP_REPOSITORY", gaps)
    monkeypatch.setattr(knowledge_routes, "KNOWLEDGE_REPOSITORY", Knowledge())
    monkeypatch.setattr(delivery_routes, "DELIVERY_REPOSITORY", Delivery())
    monkeypatch.setattr(retest_routes, "RETEST_REPOSITORY", retest)

    blocked = api_main.build_growth_loop_data("tenant_1", "project_1")
    assert blocked.current_step == "scans"
    assert blocked.conclusion_readiness.state == "blocked"
    assert "independent_repetitions_complete" in blocked.conclusion_readiness.reason_codes

    retest.publishable = True
    awaiting_derivation = api_main.build_growth_loop_data("tenant_1", "project_1")
    assert awaiting_derivation.current_step == "gaps"
    assert next(item for item in awaiting_derivation.steps if item.step_id == "gaps").status == "current"

    gaps.derivation_complete = True
    derived_with_zero_gaps = api_main.build_growth_loop_data("tenant_1", "project_1")
    assert derived_with_zero_gaps.current_step == "assets"
    assert next(item for item in derived_with_zero_gaps.steps if item.step_id == "gaps").status == "completed"

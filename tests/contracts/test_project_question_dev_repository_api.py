from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from apps.api.main import InMemoryProjectRepository, MySQLProjectRepository, app, build_project_repository


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


def load_schema(name: str) -> dict:
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def validate_response(schema_name: str, payload: dict) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def test_project_competitor_question_dev_repository_contract_loop() -> None:
    client = TestClient(app)

    project_response = client.post(
        "/api/v1/projects",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_project_create"},
        json={
            "website_url": "www.example.com",
            "brand_name_hint": "ExampleTech",
            "industry_hint": "Marketing technology",
        },
    )

    assert project_response.status_code == 201
    project_body = project_response.json()
    assert project_body["meta"]["trace_id"] == "trc_project_create"
    assert project_body["data"]["tenant_id"] == "tenant_contract"
    assert project_body["data"]["status"] == "needs_confirmation"
    validate_response("project_response.schema.json", project_body)

    project_id = project_body["data"]["project_id"]
    competitor_response = client.post(
        f"/api/v1/projects/{project_id}/competitors",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_competitor_create"},
        json={
            "name": "Example Competitor",
            "website_url": "https://competitor.example",
            "reason": "Appears in AI answers for the same buyer questions.",
            "evidence_urls": ["https://search.example/result"],
            "confidence": 0.78,
            "status": "suggested",
            "source": "hermes_discovered",
        },
    )

    assert competitor_response.status_code == 201
    competitor_body = competitor_response.json()
    assert competitor_body["meta"]["trace_id"] == "trc_competitor_create"
    assert competitor_body["data"]["project_id"] == project_id
    assert competitor_body["data"]["tenant_id"] == "tenant_contract"
    validate_response("competitor_response.schema.json", competitor_body)

    question_response = client.post(
        f"/api/v1/projects/{project_id}/buyer-questions",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_question_create"},
        json={
            "question_text": "How should a manufacturer choose an AI visibility platform?",
            "question_type": "select",
            "intent_level": "high",
            "buyer_stage": "decision",
            "source_reason": "Generated from website copy and competitor co-mentions.",
            "recommended_providers": ["chatgpt", "deepseek"],
            "status": "suggested",
            "source": "hermes_generated",
        },
    )

    assert question_response.status_code == 201
    question_body = question_response.json()
    assert question_body["meta"]["trace_id"] == "trc_question_create"
    assert question_body["data"]["project_id"] == project_id
    assert question_body["data"]["coverage_status"] == "needs_scan"
    validate_response("buyer_question_response.schema.json", question_body)

    question_list = client.get(
        f"/api/v1/projects/{project_id}/buyer-questions",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_question_list"},
    )
    assert question_list.status_code == 200
    assert question_list.json()["meta"]["trace_id"] == "trc_question_list"
    assert [item["question_id"] for item in question_list.json()["data"]] == [question_body["data"]["question_id"]]


def test_project_child_dev_repository_is_tenant_scoped() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/projects/project_missing/competitors",
        headers={"tenant-id": "tenant_other", "X-AIRank-Trace-Id": "trc_missing_project"},
        json={"name": "Orphan Competitor"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "PROJECT_NOT_FOUND"
    assert body["error"]["trace_id"] == "trc_missing_project"
    assert body["error"]["details"]["repository"] == "in_memory_dev"
    validate_response("error_response.schema.json", body)


def test_project_inferred_brand_name_is_contract_bounded() -> None:
    client = TestClient(app)
    long_host_label = "a" * 200

    response = client.post(
        "/api/v1/projects",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_project_long_brand"},
        json={"website_url": f"https://{long_host_label}.example.com"},
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["data"]["brand_name"]) == 120
    validate_response("project_response.schema.json", body)


def test_project_repository_factory_selects_persistence_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRANK_DATABASE_URL", raising=False)
    assert isinstance(build_project_repository(), InMemoryProjectRepository)

    monkeypatch.setenv(
        "AIRANK_DATABASE_URL",
        "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike",
    )
    assert isinstance(build_project_repository(), MySQLProjectRepository)


def test_project_create_api_rejects_body_tenant_leakage() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/projects",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_project_leak"},
        json={"website_url": "www.example.com", "tenant_id": "tenant_other"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["trace_id"] == "trc_project_leak"
    assert any(error["loc"] == ["body", "tenant_id"] for error in body["error"]["details"]["errors"])
    validate_response("error_response.schema.json", body)


def test_dev_repository_api_rejects_duplicate_contract_arrays() -> None:
    client = TestClient(app)

    project_response = client.post(
        "/api/v1/projects",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_project_unique"},
        json={"website_url": "www.example.com"},
    )
    project_id = project_response.json()["data"]["project_id"]

    question_response = client.post(
        f"/api/v1/projects/{project_id}/buyer-questions",
        headers={"tenant-id": "tenant_contract", "X-AIRank-Trace-Id": "trc_question_duplicate"},
        json={
            "question_text": "Which AI answer platform should we compare?",
            "recommended_providers": ["chatgpt", "chatgpt"],
        },
    )

    assert question_response.status_code == 422
    body = question_response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["trace_id"] == "trc_question_duplicate"
    validate_response("error_response.schema.json", body)


def test_mysql_schema_url_lengths_match_api_contracts() -> None:
    bootstrap_sql = (ROOT / "ops" / "deployment" / "mysql-bootstrap.sql").read_text(encoding="utf-8")
    migration_sql = (
        ROOT / "apps" / "api" / "alembic" / "versions" / "20260517_0001_initial_schema.py"
    ).read_text(encoding="utf-8")
    reconcile_sql = (
        ROOT / "apps" / "api" / "alembic" / "versions" / "20260517_0002_reconcile_url_lengths.py"
    ).read_text(encoding="utf-8")

    assert "website_url VARCHAR(2048) NULL" in bootstrap_sql
    assert "website_url VARCHAR(2048) NULL" in migration_sql
    assert "VARCHAR(2048)" in reconcile_sql
    assert "VARCHAR(1024)" not in reconcile_sql
    assert "website_url VARCHAR(1024)" not in bootstrap_sql
    assert "website_url VARCHAR(1024)" not in migration_sql

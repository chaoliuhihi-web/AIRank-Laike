from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


def load_schema(name: str) -> dict:
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def validate_response(schema_name: str, payload: dict) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def test_scan_run_api_creates_and_reads_dev_statuses() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/scan-runs",
        headers={"tenant-id": "tenant_scan", "X-AIRank-Trace-Id": "trc_scan_create"},
        json={
            "project_id": "project_demo",
            "name": "Baseline AI visibility scan",
            "run_type": "baseline",
            "provider_scope": ["chatgpt", "deepseek"],
            "question_scope": {"mode": "selected", "question_ids": ["question_demo"]},
        },
    )

    assert create_response.status_code == 201
    run_body = create_response.json()
    assert run_body["meta"]["trace_id"] == "trc_scan_create"
    assert run_body["data"]["status"] == "queued"
    assert run_body["data"]["metrics"]["task_count"] == 2
    validate_response("scan_run_response.schema.json", run_body)

    run_id = run_body["data"]["run_id"]
    get_response = client.get(
        f"/api/v1/scan-runs/{run_id}",
        headers={"tenant-id": "tenant_scan", "X-AIRank-Trace-Id": "trc_scan_get"},
    )
    assert get_response.status_code == 200
    validate_response("scan_run_response.schema.json", get_response.json())

    tasks_response = client.get(
        f"/api/v1/scan-runs/{run_id}/tasks",
        headers={"tenant-id": "tenant_scan", "X-AIRank-Trace-Id": "trc_scan_tasks"},
    )
    assert tasks_response.status_code == 200
    tasks_body = tasks_response.json()
    assert len(tasks_body["data"]) == 2
    assert {task["provider"] for task in tasks_body["data"]} == {"chatgpt", "deepseek"}
    validate_response("scan_task_list_response.schema.json", tasks_body)

    task_id = tasks_body["data"][0]["task_id"]
    task_response = client.get(
        f"/api/v1/scan-tasks/{task_id}",
        headers={"tenant-id": "tenant_scan", "X-AIRank-Trace-Id": "trc_scan_task"},
    )
    assert task_response.status_code == 200
    validate_response("scan_task_response.schema.json", task_response.json())


def test_scan_run_api_is_tenant_scoped() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/scan-runs/scan_run_missing",
        headers={"tenant-id": "tenant_scan_other", "X-AIRank-Trace-Id": "trc_scan_missing"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "SCAN_RUN_NOT_FOUND"
    assert body["error"]["trace_id"] == "trc_scan_missing"
    validate_response("error_response.schema.json", body)


def test_scan_run_api_rejects_extra_fields_and_duplicate_scopes() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/scan-runs",
        headers={"tenant-id": "tenant_scan", "X-AIRank-Trace-Id": "trc_scan_invalid"},
        json={
            "project_id": "project_demo",
            "provider_scope": ["chatgpt", "chatgpt"],
            "question_scope": {"mode": "selected", "question_ids": ["question_demo"]},
            "tenant_id": "tenant_other",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["trace_id"] == "trc_scan_invalid"
    validate_response("error_response.schema.json", body)


def test_scan_run_api_rejects_selected_scope_without_questions() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/scan-runs",
        headers={"tenant-id": "tenant_scan", "X-AIRank-Trace-Id": "trc_scan_selected_empty"},
        json={
            "project_id": "project_demo",
            "provider_scope": ["chatgpt"],
            "question_scope": {"mode": "selected"},
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["trace_id"] == "trc_scan_selected_empty"
    validate_response("error_response.schema.json", body)


def test_scan_task_api_uses_scan_task_not_found_error() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/scan-tasks/scan_task_missing",
        headers={"tenant-id": "tenant_scan", "X-AIRank-Trace-Id": "trc_scan_task_missing"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "SCAN_TASK_NOT_FOUND"
    assert body["error"]["trace_id"] == "trc_scan_task_missing"
    validate_response("error_response.schema.json", body)

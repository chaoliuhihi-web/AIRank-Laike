from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text

from apps.api.main import InMemoryScanRepository, MySQLScanRepository, ScanRunCreateRequest, app, build_scan_repository


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


def create_scan_repository_tables(repository: MySQLScanRepository) -> None:
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_projects (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  deleted_at DATETIME NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_buyer_questions (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL,
                  question_text TEXT NOT NULL,
                  status VARCHAR(32) NOT NULL,
                  priority INT NOT NULL DEFAULT 100,
                  created_at DATETIME NOT NULL,
                  deleted_at DATETIME NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_scan_runs (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL,
                  name VARCHAR(255) NULL,
                  run_type VARCHAR(64) NOT NULL,
                  status VARCHAR(32) NOT NULL,
                  provider_scope_json TEXT NULL,
                  question_scope_json TEXT NULL,
                  metrics_json TEXT NULL,
                  error_message TEXT NULL,
                  started_at DATETIME NULL,
                  finished_at DATETIME NULL,
                  created_at DATETIME NOT NULL,
                  updated_at DATETIME NOT NULL,
                  deleted_at DATETIME NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_scan_tasks (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL,
                  run_id VARCHAR(64) NOT NULL,
                  question_id VARCHAR(64) NOT NULL,
                  provider VARCHAR(64) NOT NULL,
                  status VARCHAR(32) NOT NULL,
                  attempt_count INT NOT NULL,
                  scheduled_at DATETIME NULL,
                  started_at DATETIME NULL,
                  finished_at DATETIME NULL,
                  error_code VARCHAR(128) NULL,
                  error_message TEXT NULL,
                  created_at DATETIME NOT NULL,
                  updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_async_jobs (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NULL,
                  job_type VARCHAR(64) NOT NULL,
                  status VARCHAR(32) NOT NULL,
                  priority INT NOT NULL,
                  scheduled_at DATETIME NOT NULL,
                  payload_json TEXT NULL,
                  created_at DATETIME NOT NULL,
                  updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(text("INSERT INTO airank_projects (id, tenant_id) VALUES ('project_real', 'tenant_real')"))
        conn.execute(
            text(
                """
                INSERT INTO airank_buyer_questions (
                  id, tenant_id, project_id, question_text, status, priority, created_at
                )
                VALUES
                  (
                    'question_real_1', 'tenant_real', 'project_real',
                    'Which AI visibility platform should we choose?',
                    'confirmed', 10, '2026-05-17 10:00:00'
                  ),
                  (
                    'question_real_2', 'tenant_real', 'project_real',
                    'How does AIRank compare with competitors?',
                    'suggested', 20, '2026-05-17 10:01:00'
                  ),
                  (
                    'question_archived', 'tenant_real', 'project_real',
                    'Archived question should not be scanned',
                    'archived', 30, '2026-05-17 10:02:00'
                  )
                """
            )
        )


def test_scan_repository_factory_selects_persistence_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRANK_DATABASE_URL", raising=False)
    assert isinstance(build_scan_repository(), InMemoryScanRepository)

    monkeypatch.setenv(
        "AIRANK_DATABASE_URL",
        "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike",
    )
    assert isinstance(build_scan_repository(), MySQLScanRepository)


def test_mysql_scan_repository_persists_run_and_tasks() -> None:
    repository = MySQLScanRepository("sqlite+pysqlite:///:memory:")
    create_scan_repository_tables(repository)

    run = repository.create_run(
        "tenant_real",
        ScanRunCreateRequest(
            project_id="project_real",
            name="Production persistence scan",
            provider_scope=["chatgpt", "deepseek"],
            question_scope={"mode": "selected", "question_ids": ["question_real_1", "question_real_2"]},
        ),
    )

    assert run.status == "queued"
    assert run.metrics["task_count"] == 4
    assert run.question_scope.question_ids == ["question_real_1", "question_real_2"]

    fetched_run = repository.get_run("tenant_real", run.run_id)
    tasks = repository.list_tasks("tenant_real", run.run_id)
    assert fetched_run.run_id == run.run_id
    assert len(tasks) == 4
    assert {task.provider for task in tasks} == {"chatgpt", "deepseek"}
    assert {task.question_id for task in tasks} == {"question_real_1", "question_real_2"}
    assert repository.get_task("tenant_real", tasks[0].task_id).run_id == run.run_id

    with repository._engine.begin() as conn:
        jobs = conn.execute(text("SELECT * FROM airank_async_jobs ORDER BY job_type, payload_json")).mappings().all()
    assert len(jobs) == 4
    assert {job["job_type"] for job in jobs} == {"scan.provider"}
    first_payload = json.loads(jobs[0]["payload_json"])
    assert first_payload["run_id"] == run.run_id
    assert first_payload["scan_task_id"].startswith("scan_task_")
    assert first_payload["question_id"] in {"question_real_1", "question_real_2"}
    assert first_payload["provider"] in {"chatgpt", "deepseek"}
    assert first_payload["question_text"]


def test_mysql_scan_repository_all_active_excludes_archived_questions() -> None:
    repository = MySQLScanRepository("sqlite+pysqlite:///:memory:")
    create_scan_repository_tables(repository)

    run = repository.create_run(
        "tenant_real",
        ScanRunCreateRequest(
            project_id="project_real",
            provider_scope=["chatgpt"],
            question_scope={"mode": "all_active"},
        ),
    )

    tasks = repository.list_tasks("tenant_real", run.run_id)
    assert [task.question_id for task in tasks] == ["question_real_1", "question_real_2"]


def test_mysql_scan_repository_rejects_missing_selected_question() -> None:
    repository = MySQLScanRepository("sqlite+pysqlite:///:memory:")
    create_scan_repository_tables(repository)

    with pytest.raises(Exception) as exc_info:
        repository.create_run(
            "tenant_real",
            ScanRunCreateRequest(
                project_id="project_real",
                provider_scope=["chatgpt"],
                question_scope={"mode": "selected", "question_ids": ["question_missing"]},
            ),
        )

    assert getattr(exc_info.value, "status_code") == 404
    assert exc_info.value.detail["code"] == "QUESTION_NOT_FOUND"

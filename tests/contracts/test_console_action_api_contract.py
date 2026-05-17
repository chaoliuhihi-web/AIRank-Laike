from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text

from apps.api.main import ConsoleActionRequest, MySQLConsoleActionRepository, app


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


def validate_schema(schema_name: str, payload: dict) -> None:
    schema = json.loads((CONTRACT_ROOT / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def valid_action_request() -> dict:
    return {
        "project_id": "project_demo",
        "action_type": "settings.save",
        "label": "保存设置",
        "source_route": "/console/settings",
        "entity_type": "settings",
        "entity_id": "project_settings",
        "payload": {"section": "project"},
    }


def test_console_action_api_records_enveloped_contract() -> None:
    client = TestClient(app)
    payload = valid_action_request()
    validate_schema("console_action_request.schema.json", payload)

    response = client.post(
        "/api/v1/console/actions",
        json=payload,
        headers={
            "tenant-id": "tenant_demo",
            "X-AIRank-Trace-Id": "trc_console_action",
            "X-AIRank-User-Id": "user_1",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["action_type"] == "settings.save"
    assert body["data"]["project_id"] == "project_demo"
    assert body["meta"]["trace_id"] == "trc_console_action"
    validate_schema("console_action_response.schema.json", body)


def test_console_action_api_rejects_invalid_action_type() -> None:
    client = TestClient(app)
    payload = valid_action_request()
    payload["action_type"] = "Settings Save"

    response = client.post(
        "/api/v1/console/actions",
        json=payload,
        headers={"tenant-id": "tenant_demo", "X-AIRank-Trace-Id": "trc_console_action_bad"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["trace_id"] == "trc_console_action_bad"


def create_console_action_tables(repository: MySQLConsoleActionRepository) -> None:
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
                CREATE TABLE airank_audit_events (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NULL,
                  actor_user_id VARCHAR(64) NULL,
                  event_type VARCHAR(128) NOT NULL,
                  entity_type VARCHAR(128) NULL,
                  entity_id VARCHAR(64) NULL,
                  trace_id VARCHAR(128) NULL,
                  payload_json TEXT NULL,
                  created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(text("INSERT INTO airank_projects (id, tenant_id) VALUES ('project_demo', 'tenant_demo')"))


def test_mysql_console_action_repository_records_audit_event() -> None:
    repository = MySQLConsoleActionRepository("sqlite+pysqlite:///:memory:")
    create_console_action_tables(repository)
    request = ConsoleActionRequest(**valid_action_request())

    result = repository.record_action("tenant_demo", request, "trc_action_real", "user_1")

    assert result.action_id.startswith("audit_")
    assert result.status == "recorded"
    with repository._engine.begin() as conn:
        audit = conn.execute(text("SELECT * FROM airank_audit_events")).mappings().one()

    assert audit["id"] == result.action_id
    assert audit["event_type"] == "console.settings.save"
    assert audit["entity_type"] == "settings"
    assert audit["entity_id"] == "project_settings"
    assert audit["trace_id"] == "trc_action_real"
    assert audit["actor_user_id"] == "user_1"
    payload = json.loads(audit["payload_json"])
    assert payload["label"] == "保存设置"
    assert payload["source_route"] == "/console/settings"


def test_mysql_console_action_repository_is_project_scoped() -> None:
    repository = MySQLConsoleActionRepository("sqlite+pysqlite:///:memory:")
    create_console_action_tables(repository)
    payload = valid_action_request()
    payload["project_id"] = "project_missing"
    request = ConsoleActionRequest(**payload)

    with pytest.raises(Exception) as exc_info:
        repository.record_action("tenant_demo", request, "trc_missing", "user_1")

    assert getattr(exc_info.value, "status_code") == 404
    assert exc_info.value.detail["code"] == "PROJECT_NOT_FOUND"

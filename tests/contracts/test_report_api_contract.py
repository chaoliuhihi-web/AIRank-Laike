from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text

from apps.api.main import InMemoryReportRepository, MySQLReportRepository, app, build_report_repository


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


def validate_response(schema_name: str, payload: dict) -> None:
    schema = json.loads((CONTRACT_ROOT / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def test_report_api_returns_empty_state_without_evidence_backed_reports() -> None:
    client = TestClient(app)

    reports = client.get(
        "/api/v1/projects/project_demo/reports",
        headers={"tenant-id": "tenant_reports", "X-AIRank-Trace-Id": "trc_reports"},
    )
    assert reports.status_code == 200
    reports_body = reports.json()
    assert reports_body["data"]["reports"] == []
    validate_response("report_list_response.schema.json", reports_body)

    receipt = client.post(
        "/api/v1/reports/report_missing/download-receipts",
        headers={"tenant-id": "tenant_reports", "X-AIRank-Trace-Id": "trc_receipt"},
    )
    assert receipt.status_code == 404
    receipt_body = receipt.json()
    assert receipt_body["error"]["code"] == "REPORT_NOT_FOUND"
    validate_response("error_response.schema.json", receipt_body)


def test_report_api_rejects_invalid_project_id() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/projects/not_a_project_id/reports",
        headers={"tenant-id": "tenant_reports", "X-AIRank-Trace-Id": "trc_reports_bad_project"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["trace_id"] == "trc_reports_bad_project"
    validate_response("error_response.schema.json", body)


def create_report_repository_tables(repository: MySQLReportRepository) -> None:
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
                CREATE TABLE airank_reports (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL,
                  report_type VARCHAR(64) NOT NULL,
                  title VARCHAR(255) NOT NULL,
                  status VARCHAR(32) NOT NULL,
                  metrics_json TEXT NULL,
                  generated_at DATETIME NULL,
                  created_at DATETIME NOT NULL,
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
        conn.execute(text("INSERT INTO airank_projects (id, tenant_id) VALUES ('project_report', 'tenant_report')"))


def test_report_repository_factory_selects_persistence_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRANK_DATABASE_URL", raising=False)
    assert isinstance(build_report_repository(), InMemoryReportRepository)

    monkeypatch.setenv(
        "AIRANK_DATABASE_URL",
        "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike",
    )
    assert isinstance(build_report_repository(), MySQLReportRepository)


def test_mysql_report_repository_lists_reports_and_records_audit_receipt() -> None:
    repository = MySQLReportRepository("sqlite+pysqlite:///:memory:")
    create_report_repository_tables(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_reports (
                  id, tenant_id, project_id, report_type, title, status,
                  metrics_json, generated_at, created_at
                )
                VALUES (
                  'report_real', 'tenant_report', 'project_report',
                  'diagnostic', 'AI 来客诊断报告', 'generated',
                  '{"summary": "真实报告摘要", "report_status": "generated", "baseline_quality": {"contract_version": "airank.measurement-quality.v4", "publishable": true}, "compare_quality": {"contract_version": "airank.measurement-quality.v4", "publishable": true}}',
                  '2026-05-17 12:00:00', '2026-05-17 11:00:00'
                )
                """
            )
        )

    report_list = repository.list_reports("tenant_report", "project_report")
    assert len(report_list.reports) == 1
    assert report_list.reports[0].report_id == "report_real"
    assert report_list.reports[0].desc == "真实报告摘要"
    assert report_list.reports[0].date == "2026-05-17"

    receipt = repository.record_download_receipt("tenant_report", "report_real", "trc_report_real")
    assert receipt.report_id == "report_real"
    assert receipt.receipt_id.startswith("receipt_")

    with repository._engine.begin() as conn:
        audit = conn.execute(text("SELECT * FROM airank_audit_events")).mappings().one()
    assert audit["id"] == receipt.receipt_id
    assert audit["event_type"] == "report.download_receipt"
    assert audit["entity_id"] == "report_real"
    assert audit["trace_id"] == "trc_report_real"


def test_mysql_report_repository_is_tenant_scoped() -> None:
    repository = MySQLReportRepository("sqlite+pysqlite:///:memory:")
    create_report_repository_tables(repository)

    with pytest.raises(Exception) as exc_info:
        repository.list_reports("tenant_other", "project_report")

    assert getattr(exc_info.value, "status_code") == 404
    assert exc_info.value.detail["code"] == "PROJECT_NOT_FOUND"


def test_mysql_report_receipt_rejects_missing_report() -> None:
    repository = MySQLReportRepository("sqlite+pysqlite:///:memory:")
    create_report_repository_tables(repository)

    with pytest.raises(Exception) as exc_info:
        repository.record_download_receipt("tenant_report", "report_missing", "trc_missing")

    assert getattr(exc_info.value, "status_code") == 404
    assert exc_info.value.detail["code"] == "REPORT_NOT_FOUND"


def test_mysql_report_receipt_rejects_quality_blocked_or_legacy_report() -> None:
    repository = MySQLReportRepository("sqlite+pysqlite:///:memory:")
    create_report_repository_tables(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_reports (
                  id, tenant_id, project_id, report_type, title, status,
                  metrics_json, generated_at, created_at
                ) VALUES (
                  'report_blocked', 'tenant_report', 'project_report', 'retest',
                  '质量阻断报告', 'quality_blocked',
                  '{"report_status": "quality_blocked"}',
                  '2026-08-08 12:00:00', '2026-08-08 12:00:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_reports (
                  id, tenant_id, project_id, report_type, title, status,
                  metrics_json, generated_at, created_at
                ) VALUES (
                  'report_legacy', 'tenant_report', 'project_report', 'retest',
                  '旧版质量报告', 'generated',
                  '{"report_status": "generated", "baseline_quality": {"publishable": true}, "compare_quality": {"publishable": true}}',
                  '2026-08-08 12:01:00', '2026-08-08 12:01:00'
                )
                """
            )
        )

    with pytest.raises(Exception) as exc_info:
        repository.record_download_receipt("tenant_report", "report_blocked", "trc_report_blocked")

    assert getattr(exc_info.value, "status_code") == 409
    assert exc_info.value.detail["code"] == "REPORT_QUALITY_BLOCKED"
    report_list = repository.list_reports("tenant_report", "project_report")
    legacy = next(item for item in report_list.reports if item.report_id == "report_legacy")
    assert legacy.status == "quality_blocked"
    assert "不可作为客户交付物" in legacy.desc
    with pytest.raises(Exception) as legacy_exc_info:
        repository.record_download_receipt("tenant_report", "report_legacy", "trc_report_legacy")
    assert getattr(legacy_exc_info.value, "status_code") == 409
    assert legacy_exc_info.value.detail["code"] == "REPORT_QUALITY_BLOCKED"

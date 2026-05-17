from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


def validate_response(schema_name: str, payload: dict) -> None:
    schema = json.loads((CONTRACT_ROOT / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def test_report_api_lists_reports_and_records_download_receipt() -> None:
    client = TestClient(app)

    reports = client.get(
        "/api/v1/projects/project_demo/reports",
        headers={"tenant-id": "tenant_reports", "X-AIRank-Trace-Id": "trc_reports"},
    )
    assert reports.status_code == 200
    reports_body = reports.json()
    assert reports_body["data"]["reports"]
    validate_response("report_list_response.schema.json", reports_body)

    report_id = reports_body["data"]["reports"][0]["report_id"]
    receipt = client.post(
        f"/api/v1/reports/{report_id}/download-receipts",
        headers={"tenant-id": "tenant_reports", "X-AIRank-Trace-Id": "trc_receipt"},
    )
    assert receipt.status_code == 201
    receipt_body = receipt.json()
    assert receipt_body["data"]["report_id"] == report_id
    validate_response("download_receipt_response.schema.json", receipt_body)

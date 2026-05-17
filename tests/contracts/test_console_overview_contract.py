from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

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

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(body["data"])

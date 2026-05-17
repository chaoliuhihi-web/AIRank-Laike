from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages" / "contracts" / "asset_bundle_response.schema.json"


def test_asset_bundle_api_matches_contract() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/projects/project_demo/asset-bundle",
        headers={"tenant-id": "tenant_assets", "X-AIRank-Trace-Id": "trc_asset_bundle"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_asset_bundle"
    assert body["data"]["tenant_id"] == "tenant_assets"
    assert body["data"]["assets"]

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(body)

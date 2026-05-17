from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]


def load_schema(name: str) -> dict:
    schema_path = ROOT / "packages" / "contracts" / name
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_response(schema_name: str, body: dict) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(body)


def test_health_returns_enveloped_contract() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/health", headers={"X-AIRank-Trace-Id": "trc_test_health"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_test_health"
    assert body["data"]["status"] == "ok"
    validate_response("health_response.schema.json", body)


def test_version_returns_enveloped_contract() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/version", headers={"X-AIRank-Trace-Id": "trc_test_version"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_test_version"
    assert body["data"]["api_prefix"] == "/api/v1"
    validate_response("version_response.schema.json", body)

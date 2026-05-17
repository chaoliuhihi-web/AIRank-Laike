from __future__ import annotations

import json
from pathlib import Path
import re

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api.main import ERROR_REGISTRY, app


ROOT = Path(__file__).resolve().parents[2]
ERROR_CODE_PATTERN = re.compile(r"\| `([^`]+)` \| (\d{3}) \|")


def load_schema(name: str) -> dict:
    schema_path = ROOT / "packages" / "contracts" / name
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_response(schema_name: str, body: dict) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(body)


def load_error_registry_doc() -> dict[str, int]:
    error_codes = ROOT / "packages" / "contracts" / "error-codes.md"
    registry: dict[str, int] = {}
    for code, http_status in ERROR_CODE_PATTERN.findall(error_codes.read_text(encoding="utf-8")):
        registry[code] = int(http_status)
    return registry


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


def test_error_schema_codes_match_registry_doc_and_api() -> None:
    schema = load_schema("error_response.schema.json")
    schema_codes = set(schema["properties"]["error"]["properties"]["code"]["enum"])
    doc_registry = load_error_registry_doc()
    api_registry = {code: status for code, (status, _message) in ERROR_REGISTRY.items()}

    assert schema_codes == set(doc_registry)
    assert api_registry == doc_registry


def test_missing_route_returns_traceable_error_envelope() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/missing-resource",
        headers={"X-AIRank-Trace-Id": "trc_test_missing"},
    )

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert body["error"]["trace_id"] == "trc_test_missing"
    assert body["error"]["details"]["path"] == "/api/v1/missing-resource"
    validate_response("error_response.schema.json", body)


def test_method_not_allowed_returns_registry_error_envelope() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/health",
        headers={"X-AIRank-Trace-Id": "trc_test_method"},
    )

    assert response.status_code == 405
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert body["error"]["trace_id"] == "trc_test_method"
    assert body["error"]["details"]["method"] == "POST"
    validate_response("error_response.schema.json", body)

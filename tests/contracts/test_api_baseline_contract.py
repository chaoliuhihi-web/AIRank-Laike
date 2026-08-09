from __future__ import annotations

import json
import logging
from pathlib import Path
import re

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api import main as api_main
from apps.api.main import ERROR_REGISTRY, app
from apps.api.provider_scan import ProviderReadinessResult


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
    assert response.headers["X-AIRank-Trace-Id"] == "trc_test_health"


def test_request_logging_sanitizes_trace_ids_and_never_logs_credentials(
    caplog,
) -> None:
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="airank.api.request"):
        response = client.get(
            "/api/v1/health",
            headers={
                "X-AIRank-Trace-Id": "../../unsafe trace",
                "Authorization": "Bearer must-never-appear-in-logs",
            },
        )

    trace_id = response.headers["X-AIRank-Trace-Id"]
    assert re.fullmatch(r"trc_[0-9a-f]{16}", trace_id)
    assert response.json()["meta"]["trace_id"] == trace_id
    record = json.loads(caplog.records[-1].message)
    assert record["event"] == "api_request_completed"
    assert record["operation"] == "GET /api/v1/health"
    assert record["trace_id"] == trace_id
    assert "must-never-appear-in-logs" not in caplog.text
    assert "unsafe trace" not in caplog.text


def test_request_logging_records_unhandled_failure_without_exception_text(caplog) -> None:
    isolated_app = FastAPI()
    isolated_app.middleware("http")(api_main.emit_structured_request_log)

    @isolated_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("must-never-appear-in-logs")

    with caplog.at_level(logging.ERROR, logger="airank.api.request"):
        response = TestClient(isolated_app, raise_server_exceptions=False).get(
            "/boom", headers={"X-AIRank-Trace-Id": "trc_failure_test"}
        )

    assert response.status_code == 500
    record = json.loads(caplog.records[-1].message)
    assert record["event"] == "api_request_failed"
    assert record["status_code"] == 500
    assert record["error_type"] == "RuntimeError"
    assert "must-never-appear-in-logs" not in caplog.text


def test_readiness_is_public_and_returns_503_when_dependencies_are_blocked(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setattr(
        api_main,
        "build_runtime_readiness",
        lambda: api_main.ReadinessStatus(
            status="blocked",
            service="airank-api",
            api_version="v1",
            expected_schema_revision=api_main.EXPECTED_SCHEMA_REVISION,
            components=[
                api_main.ReadinessComponent(
                    name=name,
                    status="blocked",
                    reason_code="DEPENDENCY_BLOCKED",
                )
                for name in (
                    "production_configuration",
                    "database_connectivity",
                    "schema_revision",
                    "object_storage_connectivity",
                )
            ],
        ),
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/ready", headers={"X-AIRank-Trace-Id": "trc_test_ready_blocked"}
    )

    assert response.status_code == 503
    assert response.json()["data"]["status"] == "blocked"
    validate_response("readiness_response.schema.json", response.json())


def test_readiness_returns_200_only_when_every_component_is_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        api_main,
        "build_runtime_readiness",
        lambda: api_main.ReadinessStatus(
            status="ready",
            service="airank-api",
            api_version="v1",
            expected_schema_revision=api_main.EXPECTED_SCHEMA_REVISION,
            components=[
                api_main.ReadinessComponent(name=name, status="ready")
                for name in (
                    "production_configuration",
                    "database_connectivity",
                    "schema_revision",
                    "object_storage_connectivity",
                )
            ],
        ),
    )

    response = TestClient(app).get("/api/v1/ready")

    assert response.status_code == 200
    validate_response("readiness_response.schema.json", response.json())


def test_runtime_expected_schema_revision_tracks_the_only_alembic_head() -> None:
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps/api/alembic"))

    heads = ScriptDirectory.from_config(config).get_heads()

    assert heads == [api_main.EXPECTED_SCHEMA_REVISION]


def test_version_returns_enveloped_contract() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/version", headers={"X-AIRank-Trace-Id": "trc_test_version"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_test_version"
    assert body["data"]["api_prefix"] == "/api/v1"
    validate_response("version_response.schema.json", body)


def test_provider_readiness_returns_enveloped_contract(monkeypatch) -> None:
    def fake_probe(provider: str) -> ProviderReadinessResult:
        return ProviderReadinessResult(
            provider=provider,
            label=api_main.PROVIDER_LABELS[provider],
            status="blocked",
            url=f"https://{provider}.example.test/",
            profile_dir=f"/tmp/airank/{provider}",
            headless=True,
            blocker_code="login_required",
            reason="login required",
        )

    monkeypatch.delenv("AIRANK_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("AIRANK_MIN_PROVIDER_SUCCESS_COUNT", raising=False)
    monkeypatch.setattr(api_main, "probe_provider_readiness", fake_probe)
    client = TestClient(app)

    response = client.get("/api/v1/provider-readiness", headers={"X-AIRank-Trace-Id": "trc_test_provider"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_test_provider"
    assert body["data"]["mode"] == "browser"
    assert body["data"]["minimum_success_count"] == len(api_main.DEFAULT_PROVIDER_SCOPE)
    assert len(body["data"]["providers"]) == len(api_main.DEFAULT_PROVIDER_SCOPE)
    assert {item["status"] for item in body["data"]["providers"]} == {"blocked"}
    assert {item["blocker_code"] for item in body["data"]["providers"]} == {"login_required"}
    assert {item["probe_level"] for item in body["data"]["providers"]} == {"l2_interaction"}
    assert {item["generation_verified"] for item in body["data"]["providers"]} == {False}
    validate_response("provider_readiness_response.schema.json", body)


def test_minimum_provider_success_count_defaults_to_full_browser_scope(monkeypatch) -> None:
    monkeypatch.delenv("AIRANK_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("AIRANK_MIN_PROVIDER_SUCCESS_COUNT", raising=False)

    assert api_main.minimum_provider_success_count(api_main.DEFAULT_PROVIDER_SCOPE) == len(api_main.DEFAULT_PROVIDER_SCOPE)
    expected_task_count = len(api_main.DEFAULT_PROVIDER_SCOPE) * 3
    assert api_main.minimum_scan_success_count(
        api_main.DEFAULT_PROVIDER_SCOPE, question_count=3, task_count=expected_task_count
    ) == expected_task_count


def test_minimum_provider_success_count_can_be_lowered_for_partial_beta(monkeypatch) -> None:
    monkeypatch.delenv("AIRANK_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("AIRANK_MIN_PROVIDER_SUCCESS_COUNT", "3")

    assert api_main.minimum_provider_success_count(api_main.DEFAULT_PROVIDER_SCOPE) == 3
    assert api_main.minimum_scan_success_count(api_main.DEFAULT_PROVIDER_SCOPE, question_count=2, task_count=14) == 6


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

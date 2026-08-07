from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


SCAN_SCHEMAS = [
    "scan_run_create_request.schema.json",
    "scan_run_response.schema.json",
    "scan_task_response.schema.json",
    "scan_task_list_response.schema.json",
]


def load_schema(name: str) -> dict:
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def validate_payload(schema_name: str, payload: dict) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def response_meta() -> dict:
    return {"trace_id": "trc_scan_contract", "request_id": "req_0123456789abcdef"}


def test_scan_contract_schemas_are_valid() -> None:
    for schema_name in SCAN_SCHEMAS:
        Draft202012Validator.check_schema(load_schema(schema_name))


def test_scan_run_create_request_contract() -> None:
    validate_payload(
        "scan_run_create_request.schema.json",
        {
            "project_id": "project_demo",
            "name": "Baseline AI visibility scan",
            "run_type": "baseline",
            "provider_scope": ["chatgpt", "deepseek"],
            "question_scope": {"mode": "selected", "question_ids": ["question_demo"]},
        },
    )


def test_scan_run_response_status_contract() -> None:
    validate_payload(
        "scan_run_response.schema.json",
        {
            "data": {
                "run_id": "scan_run_demo",
                "tenant_id": "tenant_demo",
                "project_id": "project_demo",
                "name": "Baseline AI visibility scan",
                "run_type": "baseline",
                "cohort_type": "blind",
                "repetitions": 3,
                "collector_surfaces": ["web"],
                "status": "queued",
                "provider_scope": ["chatgpt", "deepseek"],
                "question_scope": {"mode": "selected", "question_ids": ["question_demo"]},
                "metrics": {"task_count": 2},
                "created_at": "2026-05-17T09:00:00Z",
                "updated_at": "2026-05-17T09:00:00Z",
            },
            "meta": response_meta(),
        },
    )


def test_scan_task_response_status_contract() -> None:
    validate_payload(
        "scan_task_response.schema.json",
        {
            "data": {
                "task_id": "scan_task_demo",
                "run_id": "scan_run_demo",
                "tenant_id": "tenant_demo",
                "project_id": "project_demo",
                "question_id": "question_demo",
                "provider": "chatgpt",
                "cohort_type": "blind",
                "prompt_version_id": "prompt_v_demo",
                "sample_index": 1,
                "session_id": "session_demo",
                "collector_surface": "web",
                "evidence_level": "consumer_web",
                "status": "queued",
                "attempt_count": 0,
                "scheduled_at": "2026-05-17T09:00:00Z",
                "created_at": "2026-05-17T09:00:00Z",
                "updated_at": "2026-05-17T09:00:00Z",
            },
            "meta": response_meta(),
        },
    )


def test_scan_task_list_response_status_contract() -> None:
    validate_payload(
        "scan_task_list_response.schema.json",
        {
            "data": [
                {
                    "task_id": "scan_task_demo",
                    "run_id": "scan_run_demo",
                    "tenant_id": "tenant_demo",
                    "project_id": "project_demo",
                    "question_id": "question_demo",
                    "provider": "chatgpt",
                    "cohort_type": "blind",
                    "prompt_version_id": "prompt_v_demo",
                    "sample_index": 1,
                    "session_id": "session_demo",
                    "collector_surface": "web",
                    "evidence_level": "consumer_web",
                    "status": "queued",
                    "attempt_count": 0,
                    "scheduled_at": "2026-05-17T09:00:00Z",
                    "created_at": "2026-05-17T09:00:00Z",
                    "updated_at": "2026-05-17T09:00:00Z",
                }
            ],
            "meta": response_meta(),
        },
    )


@pytest.mark.parametrize(
    ("schema_name", "payload"),
    [
        (
            "scan_run_create_request.schema.json",
            {
                "project_id": "project_demo",
                "provider_scope": [],
                "question_scope": {"mode": "all_active"},
            },
        ),
        (
            "scan_run_response.schema.json",
            {
                "data": {
                    "run_id": "scan_run_demo",
                    "tenant_id": "tenant_demo",
                    "project_id": "project_demo",
                    "run_type": "baseline",
                    "status": "done",
                    "provider_scope": ["chatgpt"],
                    "question_scope": {"mode": "all_active"},
                    "created_at": "2026-05-17T09:00:00Z",
                    "updated_at": "2026-05-17T09:00:00Z",
                },
                "meta": response_meta(),
            },
        ),
        (
            "scan_task_response.schema.json",
            {
                "data": {
                    "task_id": "scan_task_demo",
                    "run_id": "scan_run_demo",
                    "tenant_id": "tenant_demo",
                    "project_id": "project_demo",
                    "question_id": "question_demo",
                    "provider": "unknown_provider",
                    "status": "queued",
                    "attempt_count": 0,
                    "created_at": "2026-05-17T09:00:00Z",
                    "updated_at": "2026-05-17T09:00:00Z",
                },
                "meta": response_meta(),
            },
        ),
    ],
)
def test_scan_contracts_reject_invalid_status_or_scope(schema_name: str, payload: dict) -> None:
    with pytest.raises(ValidationError):
        validate_payload(schema_name, payload)

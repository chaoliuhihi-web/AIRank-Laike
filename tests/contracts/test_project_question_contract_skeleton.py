from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


CONTRACT_SCHEMAS = [
    "project_create_request.schema.json",
    "project_response.schema.json",
    "competitor_create_request.schema.json",
    "competitor_response.schema.json",
    "buyer_question_create_request.schema.json",
    "buyer_question_response.schema.json",
]


def load_schema(name: str) -> dict:
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def validate_payload(schema_name: str, payload: dict) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def response_meta() -> dict:
    return {"trace_id": "trc_contract_question", "request_id": "req_0123456789abcdef"}


def test_project_question_contract_schemas_are_valid() -> None:
    for schema_name in CONTRACT_SCHEMAS:
        Draft202012Validator.check_schema(load_schema(schema_name))


def test_project_create_request_allows_website_only_automation() -> None:
    validate_payload("project_create_request.schema.json", {"website_url": "www.example.com"})


def test_project_create_request_rejects_manual_db_shape_leakage() -> None:
    with pytest.raises(ValidationError):
        validate_payload(
            "project_create_request.schema.json",
            {"website_url": "www.example.com", "tenant_id": "tenant_demo"},
        )


def test_project_response_contract_matches_hermes_seeded_candidate() -> None:
    validate_payload(
        "project_response.schema.json",
        {
            "data": {
                "project_id": "project_demo",
                "tenant_id": "tenant_demo",
                "website_url": "https://www.example.com",
                "brand_name": "ExampleTech",
                "company_name": "Example Technology Co Ltd",
                "industry": "Marketing technology",
                "products": ["AI visibility diagnosis", "Recommendation content pack"],
                "audiences": ["B2B growth leader", "Marketing director"],
                "status": "needs_confirmation",
                "automation_level": "A1",
                "source_refs": [
                    {
                        "url": "https://www.example.com/about",
                        "title": "About ExampleTech",
                        "source_type": "owned",
                        "captured_at": "2026-05-17T09:00:00Z",
                        "confidence": 0.92,
                    }
                ],
                "created_at": "2026-05-17T09:00:00Z",
                "updated_at": "2026-05-17T09:00:00Z",
            },
            "meta": response_meta(),
        },
    )


def test_competitor_contracts_match_discovered_candidate() -> None:
    competitor_request = {
        "name": "Example Competitor",
        "website_url": "https://competitor.example",
        "reason": "Frequently appears in AI answers for the same buyer questions.",
        "evidence_urls": ["https://search.example/result"],
        "confidence": 0.78,
        "status": "suggested",
        "source": "hermes_discovered",
    }
    validate_payload("competitor_create_request.schema.json", competitor_request)

    validate_payload(
        "competitor_response.schema.json",
        {
            "data": {
                "competitor_id": "competitor_demo",
                "project_id": "project_demo",
                "tenant_id": "tenant_demo",
                **competitor_request,
                "created_at": "2026-05-17T09:00:00Z",
                "updated_at": "2026-05-17T09:00:00Z",
            },
            "meta": response_meta(),
        },
    )


def test_buyer_question_contracts_match_generated_question_map_item() -> None:
    question_request = {
        "question_text": "How should a manufacturing company choose an AI visibility platform?",
        "question_type": "select",
        "intent_level": "high",
        "buyer_stage": "decision",
        "source_reason": "Generated from industry, website copy, and competitor co-mentions.",
        "recommended_providers": ["chatgpt", "deepseek", "kimi"],
        "status": "suggested",
        "source": "hermes_generated",
    }
    validate_payload("buyer_question_create_request.schema.json", question_request)

    validate_payload(
        "buyer_question_response.schema.json",
        {
            "data": {
                "question_id": "question_demo",
                "project_id": "project_demo",
                "tenant_id": "tenant_demo",
                **question_request,
                "coverage_status": "needs_scan",
                "created_at": "2026-05-17T09:00:00Z",
                "updated_at": "2026-05-17T09:00:00Z",
            },
            "meta": response_meta(),
        },
    )

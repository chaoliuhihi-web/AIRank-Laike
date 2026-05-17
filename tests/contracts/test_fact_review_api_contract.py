from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


def load_schema(name: str) -> dict:
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def validate_payload(schema_name: str, payload: dict) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def test_fact_review_schemas_are_valid() -> None:
    Draft202012Validator.check_schema(load_schema("fact_review_request.schema.json"))
    Draft202012Validator.check_schema(load_schema("fact_review_response.schema.json"))


def test_fact_review_api_confirms_only_with_traceable_source() -> None:
    client = TestClient(app)

    response = client.patch(
        "/api/v1/projects/project_demo/facts/fact_demo/review",
        headers={"tenant-id": "tenant_fact", "X-AIRank-Trace-Id": "trc_fact_confirm"},
        json={
            "action": "confirmed",
            "reviewed_by": "reviewer_demo",
            "trust_level": "B",
            "source_refs": [
                {
                    "source_type": "web",
                    "support_type": "supports",
                    "citation_id": "cite_demo",
                    "snapshot_id": "snap_demo",
                    "source_url": "https://example.com/fact",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_fact_confirm"
    assert body["data"]["review_status"] == "confirmed"
    assert body["data"]["fact_status"] == "confirmed"
    assert body["data"]["disclosure"] == "public"
    validate_payload("fact_review_response.schema.json", body)


@pytest.mark.parametrize(
    ("action", "expected_disclosure", "expected_fact_status"),
    [
        ("rejected", "forbidden", "rejected"),
        ("needs_redaction", "redacted", "draft"),
        ("private", "internal", "confirmed"),
    ],
)
def test_fact_review_api_supports_non_public_review_states(
    action: str,
    expected_disclosure: str,
    expected_fact_status: str,
) -> None:
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/projects/project_demo/facts/fact_{action}/review",
        headers={"tenant-id": "tenant_fact", "X-AIRank-Trace-Id": f"trc_fact_{action}"},
        json={"action": action, "reviewed_by": "reviewer_demo", "review_note": "Manual review"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["review_status"] == action
    assert body["data"]["disclosure"] == expected_disclosure
    assert body["data"]["fact_status"] == expected_fact_status
    validate_payload("fact_review_response.schema.json", body)


def test_fact_review_rejects_confirm_without_source() -> None:
    client = TestClient(app)

    response = client.patch(
        "/api/v1/projects/project_demo/facts/fact_unsupported/review",
        headers={"tenant-id": "tenant_fact", "X-AIRank-Trace-Id": "trc_fact_missing_source"},
        json={"action": "confirmed", "reviewed_by": "reviewer_demo"},
    )

    assert response.status_code == 422

    with pytest.raises(ValidationError):
        validate_payload(
            "fact_review_request.schema.json",
            {"action": "confirmed", "reviewed_by": "reviewer_demo"},
        )

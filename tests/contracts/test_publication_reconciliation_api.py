from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pytest

from apps.api import publication_reconciliation
from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def validate_schema(name: str, payload: object) -> None:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def submit_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "proposed_outcome": "succeeded",
        "published_url": "https://customer.example/evidence/article-1",
        "external_receipt_id": "remote-receipt-42",
        "response_status": 200,
        "evidence_object_ref_id": "object_reconciliation_1",
        "evidence_sha256": "a" * 64,
        "evidence_note": "客户后台回执与公开页面截图均显示同一标题和发布时间。",
        "observed_at": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
        "submitted_by": "delivery_submitter",
        "idempotency_key": "publication-reconciliation-contract-1",
    }
    payload.update(updates)
    return payload


def review_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": "approved",
        "reviewed_by": "delivery_reviewer",
        "review_note": "已独立核对对象哈希、页面地址和外部回执标识一致。",
        "evidence_object_ref_id": "object_reconciliation_1",
        "evidence_sha256": "a" * 64,
        "idempotency_key": "publication-reconciliation-review-contract-1",
    }
    payload.update(updates)
    return payload


@pytest.fixture()
def reconciliation_repository(monkeypatch: pytest.MonkeyPatch) -> publication_reconciliation.InMemoryPublicationReconciliationRepository:
    repository = publication_reconciliation.InMemoryPublicationReconciliationRepository()
    repository.register_outcome_unknown(
        "tenant_reconciliation",
        "project_reconciliation",
        "package_outcome_unknown",
        "publish_attempt_reconciliation",
        "operation_guard_reconciliation",
    )
    repository.register_evidence_object(
        "tenant_reconciliation",
        "project_reconciliation",
        "object_reconciliation_1",
        "a" * 64,
    )
    monkeypatch.setattr(
        publication_reconciliation,
        "PUBLICATION_RECONCILIATION_REPOSITORY",
        repository,
    )
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    return repository


def test_two_person_reconciliation_is_evidence_bound_and_hash_chained(reconciliation_repository) -> None:
    client = TestClient(app)
    submitted = client.post(
        "/api/v1/publish-packages/package_outcome_unknown/reconciliations",
        headers={"tenant-id": "tenant_reconciliation", "X-AIRank-Trace-Id": "trc_reconciliation_submit"},
        json=submit_payload(),
    )

    assert submitted.status_code == 201
    assert submitted.json()["data"]["status"] == "awaiting_review"
    assert submitted.json()["data"]["external_delivery_verified"] is False
    assert submitted.json()["data"]["events"][0]["event_type"] == "reconciliation_submitted"
    validate_schema("publication_reconciliation_response.schema.json", submitted.json())

    case_id = submitted.json()["data"]["case_id"]
    approved = client.post(
        f"/api/v1/publish-reconciliations/{case_id}/review",
        headers={"tenant-id": "tenant_reconciliation", "X-AIRank-Trace-Id": "trc_reconciliation_review"},
        json=review_payload(),
    )

    assert approved.status_code == 200
    data = approved.json()["data"]
    assert data["status"] == "applied"
    assert data["reconciliation_method"] == "two_person_manual_evidence"
    assert data["external_delivery_verified"] is False
    assert len(data["receipt_sha256"]) == 64
    assert [event["event_sequence"] for event in data["events"]] == [1, 2, 3]
    assert data["events"][1]["previous_event_sha256"] == data["events"][0]["event_sha256"]
    assert data["events"][2]["previous_event_sha256"] == data["events"][1]["event_sha256"]
    validate_schema("publication_reconciliation_response.schema.json", approved.json())


def test_submitter_cannot_review_and_rejection_keeps_unknown_outcome(reconciliation_repository) -> None:
    client = TestClient(app)
    submitted = client.post(
        "/api/v1/publish-packages/package_outcome_unknown/reconciliations",
        headers={"tenant-id": "tenant_reconciliation"},
        json=submit_payload(),
    )
    case_id = submitted.json()["data"]["case_id"]

    self_review = client.post(
        f"/api/v1/publish-reconciliations/{case_id}/review",
        headers={"tenant-id": "tenant_reconciliation"},
        json=review_payload(reviewed_by="delivery_submitter"),
    )
    assert self_review.status_code == 409
    assert self_review.json()["error"]["code"] == "PUBLISH_RECONCILIATION_SECOND_PERSON_REQUIRED"

    stale_evidence_review = client.post(
        f"/api/v1/publish-reconciliations/{case_id}/review",
        headers={"tenant-id": "tenant_reconciliation"},
        json=review_payload(
            evidence_sha256="b" * 64,
            idempotency_key="publication-reconciliation-review-stale-evidence",
        ),
    )
    assert stale_evidence_review.status_code == 409
    assert stale_evidence_review.json()["error"]["code"] == "PUBLISH_RECONCILIATION_EVIDENCE_INVALID"

    rejected = client.post(
        f"/api/v1/publish-reconciliations/{case_id}/review",
        headers={"tenant-id": "tenant_reconciliation"},
        json=review_payload(
            action="rejected",
            review_note="页面地址无法访问且证据对象未显示可核对的外部回执。",
        ),
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"
    assert reconciliation_repository.outcome_unknown[("tenant_reconciliation", "package_outcome_unknown")]


def test_reconciliation_submission_is_idempotent_but_evidence_changes_conflict(reconciliation_repository) -> None:
    client = TestClient(app)
    payload = submit_payload()
    first = client.post(
        "/api/v1/publish-packages/package_outcome_unknown/reconciliations",
        headers={"tenant-id": "tenant_reconciliation"},
        json=payload,
    )
    replay = client.post(
        "/api/v1/publish-packages/package_outcome_unknown/reconciliations",
        headers={"tenant-id": "tenant_reconciliation"},
        json=payload,
    )
    conflict = client.post(
        "/api/v1/publish-packages/package_outcome_unknown/reconciliations",
        headers={"tenant-id": "tenant_reconciliation"},
        json={**payload, "published_url": "https://customer.example/evidence/different"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["data"]["case_id"] == first.json()["data"]["case_id"]
    assert replay.json()["data"]["idempotent_replay"] is True
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PUBLISH_RECONCILIATION_IDEMPOTENCY_CONFLICT"


def test_reconciliation_contracts_reject_unproven_not_applied_outcome() -> None:
    validate_schema("publication_reconciliation_submit_request.schema.json", submit_payload())
    validate_schema("publication_reconciliation_review_request.schema.json", review_payload())
    with pytest.raises(ValidationError):
        validate_schema(
            "publication_reconciliation_submit_request.schema.json",
            submit_payload(proposed_outcome="not_applied"),
        )

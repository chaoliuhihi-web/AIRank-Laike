from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from apps.api import citation_capture_routes
from apps.api.main import app


@pytest.fixture()
def repository(
    monkeypatch: pytest.MonkeyPatch,
) -> citation_capture_routes.InMemoryCitationCaptureRepository:
    instance = citation_capture_routes.InMemoryCitationCaptureRepository()
    instance.seed_citation(
        tenant_id="tenant_1",
        project_id="project_1",
        citation_id="citation_1",
        url="https://example.com/source",
    )
    instance.seed_citation(
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snapshot_1",
        citation_id="citation_2",
        citation_order=2,
        url="https://example.org/source",
    )
    instance.seed_citation(
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snapshot_other",
        citation_id="citation_other",
        url="https://example.net/source",
    )
    monkeypatch.setattr(citation_capture_routes, "CITATION_CAPTURE_REPOSITORY", instance)
    return instance


@pytest.fixture()
def client(
    repository: citation_capture_routes.InMemoryCitationCaptureRepository,
) -> TestClient:
    del repository
    return TestClient(app)


def request_payload() -> dict[str, str]:
    return {
        "idempotency_key": "citation-capture-request-1",
        "requested_by": "spoofed-actor",
    }


def test_create_list_and_get_citation_capture_contract(client: TestClient) -> None:
    created = client.post(
        "/api/v1/citations/citation_1/source-captures",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted-operator"},
        json=request_payload(),
    )
    assert created.status_code == 202
    data = created.json()["data"]
    assert data["status"] == "queued"
    assert data["capture_version"] == "airank.citation-source-capture.v1"
    assert data["requested_url"] == "https://example.com/source"
    assert data["requested_by"] == "trusted-operator"
    assert data["segments"] == []

    listed = client.get(
        "/api/v1/citations/citation_1/source-captures",
        headers={"tenant-id": "tenant_1"},
    )
    assert listed.status_code == 200
    assert [item["capture_id"] for item in listed.json()["data"]] == [data["capture_id"]]

    detail = client.get(
        f"/api/v1/citation-source-captures/{data['capture_id']}",
        headers={"tenant-id": "tenant_1"},
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["citation_id"] == "citation_1"


def test_citation_capture_is_idempotent_and_tenant_isolated(client: TestClient) -> None:
    first = client.post(
        "/api/v1/citations/citation_1/source-captures",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "operator"},
        json=request_payload(),
    )
    second = client.post(
        "/api/v1/citations/citation_1/source-captures",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "operator"},
        json=request_payload(),
    )
    assert first.json()["data"]["capture_id"] == second.json()["data"]["capture_id"]
    assert second.json()["data"]["idempotent_replay"] is True

    hidden = client.get(
        f"/api/v1/citation-source-captures/{first.json()['data']['capture_id']}",
        headers={"tenant-id": "tenant_other"},
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "CITATION_CAPTURE_NOT_FOUND"


def test_missing_citation_is_not_queued(client: TestClient) -> None:
    response = client.post(
        "/api/v1/citations/citation_missing/source-captures",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "operator"},
        json=request_payload(),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CITATION_NOT_FOUND"


def test_batch_capture_is_bounded_idempotent_and_snapshot_scoped(
    client: TestClient,
) -> None:
    payload = {
        "idempotency_key": "citation-batch-request-1",
        "requested_by": "spoofed-actor",
        "citation_ids": ["citation_1", "citation_2"],
    }
    first = client.post(
        "/api/v1/answer-snapshots/snapshot_1/citation-source-captures:batch",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted-operator"},
        json=payload,
    )
    assert first.status_code == 202
    assert first.json()["data"]["requested_count"] == 2
    assert first.json()["data"]["queued_count"] == 2
    assert first.json()["data"]["idempotent_replay_count"] == 0
    assert all(
        item["requested_by"] == "trusted-operator"
        for item in first.json()["data"]["captures"]
    )

    replay = client.post(
        "/api/v1/answer-snapshots/snapshot_1/citation-source-captures:batch",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted-operator"},
        json=payload,
    )
    assert replay.status_code == 202
    assert replay.json()["data"]["queued_count"] == 0
    assert replay.json()["data"]["idempotent_replay_count"] == 2
    assert [item["capture_id"] for item in replay.json()["data"]["captures"]] == [
        item["capture_id"] for item in first.json()["data"]["captures"]
    ]

    latest = client.get(
        "/api/v1/answer-snapshots/snapshot_1/citation-source-captures/latest",
        headers={"tenant-id": "tenant_1"},
    )
    assert latest.status_code == 200
    assert [item["citation_id"] for item in latest.json()["data"]] == [
        "citation_1",
        "citation_2",
    ]
    assert all(item["segments_loaded"] is False for item in latest.json()["data"])

    changed = client.post(
        "/api/v1/answer-snapshots/snapshot_1/citation-source-captures:batch",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted-operator"},
        json={**payload, "citation_ids": ["citation_1"]},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    wrong_snapshot = client.post(
        "/api/v1/answer-snapshots/snapshot_1/citation-source-captures:batch",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted-operator"},
        json={
            "idempotency_key": "citation-batch-request-2",
            "requested_by": "operator",
            "citation_ids": ["citation_other"],
        },
    )
    assert wrong_snapshot.status_code == 404
    assert wrong_snapshot.json()["error"]["code"] == "CITATION_NOT_FOUND_IN_SNAPSHOT"


def test_batch_preflight_rejects_invalid_url_before_any_capture_is_queued(
    client: TestClient,
    repository: citation_capture_routes.InMemoryCitationCaptureRepository,
) -> None:
    repository.seed_citation(
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snapshot_1",
        citation_id="citation_invalid_url",
        citation_order=3,
        url="https://example.edu/source",
    )
    repository._citations[("tenant_1", "citation_invalid_url")] = (
        "project_1",
        "https://example.edu/source#fragment",
        "snapshot_1",
        3,
    )

    response = client.post(
        "/api/v1/answer-snapshots/snapshot_1/citation-source-captures:batch",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "trusted-operator"},
        json={
            "idempotency_key": "citation-batch-invalid-url",
            "requested_by": "spoofed-actor",
            "citation_ids": ["citation_1", "citation_invalid_url"],
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CITATION_CAPTURE_URL_INVALID"
    assert repository.list("tenant_1", "citation_1") == []

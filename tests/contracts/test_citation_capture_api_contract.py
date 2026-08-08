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

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from apps.api import page_audit_routes
from apps.api.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        page_audit_routes,
        "PAGE_AUDIT_REPOSITORY",
        page_audit_routes.InMemoryPageAuditRepository(),
    )
    return TestClient(app)


def payload(url: str = "https://example.com/product") -> dict[str, str]:
    return {
        "url": url,
        "idempotency_key": "page-audit-request-1",
        "requested_by": "operator_1",
    }


def test_create_list_and_get_page_audit_contract(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects/project_1/page-audits",
        headers={"tenant-id": "tenant_1"},
        json=payload(),
    )
    assert created.status_code == 202
    data = created.json()["data"]
    assert data["status"] == "queued"
    assert data["rules_version"] == "airank.page-extractability.v1"
    assert data["technical_extractability_score"] is None
    assert data["findings"] == []

    listed = client.get(
        "/api/v1/projects/project_1/page-audits",
        headers={"tenant-id": "tenant_1"},
    )
    assert listed.status_code == 200
    assert [row["run_id"] for row in listed.json()["data"]] == [data["run_id"]]

    detail = client.get(
        f"/api/v1/projects/project_1/page-audits/{data['run_id']}",
        headers={"tenant-id": "tenant_1"},
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["requested_url"] == "https://example.com/product"


def test_page_audit_create_is_idempotent_and_payload_conflicts_fail(client: TestClient) -> None:
    first = client.post(
        "/api/v1/projects/project_1/page-audits",
        headers={"tenant-id": "tenant_1"},
        json=payload(),
    )
    second = client.post(
        "/api/v1/projects/project_1/page-audits",
        headers={"tenant-id": "tenant_1"},
        json=payload(),
    )
    assert first.json()["data"]["run_id"] == second.json()["data"]["run_id"]
    assert second.json()["data"]["idempotent_replay"] is True

    conflict = client.post(
        "/api/v1/projects/project_1/page-audits",
        headers={"tenant-id": "tenant_1"},
        json=payload("https://example.com/other"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "https://user:password@example.com",
        "https://example.com/page#fragment",
    ],
)
def test_page_audit_rejects_unsafe_url_shape(client: TestClient, url: str) -> None:
    response = client.post(
        "/api/v1/projects/project_1/page-audits",
        headers={"tenant-id": "tenant_1"},
        json=payload(url),
    )
    assert response.status_code == 422

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from apps.api import evidence_routes
from apps.api.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(evidence_routes, "EVIDENCE_REPOSITORY", evidence_routes.InMemoryEvidenceRepository())
    return TestClient(app)


def test_evidence_center_has_explicit_empty_state_without_persistent_samples(client: TestClient) -> None:
    response = client.get(
        "/api/v1/projects/project_1/samples",
        headers={"tenant-id": "tenant_1", "X-AIRank-Trace-Id": "trc_evidence_empty"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["trace_id"] == "trc_evidence_empty"
    assert response.json()["meta"]["total"] == 0
    assert response.json()["meta"]["valid_count"] == 0
    assert response.json()["meta"]["valid_unmentioned_count"] == 0
    assert response.json()["meta"]["citation_sample_count"] == 0


def test_evidence_center_does_not_synthesize_missing_sample_detail(client: TestClient) -> None:
    response = client.get(
        "/api/v1/samples/snapshot_missing",
        headers={"tenant-id": "tenant_1"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OBJECT_REF_NOT_FOUND"


def test_evidence_center_scopes_server_aggregation_to_requested_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingRepository(evidence_routes.InMemoryEvidenceRepository):
        request: tuple[str, str, str | None, int] | None = None

        def list_samples(self, tenant_id: str, project_id: str, run_id: str | None, limit: int):
            self.request = (tenant_id, project_id, run_id, limit)
            return super().list_samples(tenant_id, project_id, run_id, limit)

    repository = RecordingRepository()
    monkeypatch.setattr(evidence_routes, "EVIDENCE_REPOSITORY", repository)
    response = TestClient(app).get(
        "/api/v1/projects/project_1/samples?run_id=scan_run_1&limit=17",
        headers={"tenant-id": "tenant_1"},
    )

    assert response.status_code == 200
    assert repository.request == ("tenant_1", "project_1", "scan_run_1", 17)
    assert response.json()["meta"]["run_id"] == "scan_run_1"
    assert response.json()["meta"]["limit"] == 17

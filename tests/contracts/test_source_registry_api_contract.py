from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from apps.api import source_registry_routes
from apps.api.main import app


@pytest.fixture()
def repository(
    monkeypatch: pytest.MonkeyPatch,
) -> source_registry_routes.InMemorySourceRegistryRepository:
    instance = source_registry_routes.InMemorySourceRegistryRepository()
    instance.seed_source(
        tenant_id="tenant_source",
        project_id="project_source",
        host="news.example.com",
        citation_count=4,
        sample_count=3,
        provider_count=2,
    )
    monkeypatch.setattr(source_registry_routes, "SOURCE_REGISTRY_REPOSITORY", instance)
    return instance


@pytest.fixture()
def client(repository: source_registry_routes.InMemorySourceRegistryRepository) -> TestClient:
    del repository
    return TestClient(app)


def review_payload(*, supersedes_revision_id: str | None = None) -> dict[str, object]:
    return {
        "source_category_l1": "news_media",
        "source_type": "regional_news_media",
        "ecosystem": "Example Media",
        "classification_confidence": "high",
        "authority_level": "medium",
        "usage_policy": "context_only",
        "risk_level": "medium",
        "evidence_note": "A human reviewer checked the publisher identity and sample pages.",
        "evidence_url": "https://news.example.com/about",
        "reviewed_by": "spoofed-reviewer",
        "supersedes_revision_id": supersedes_revision_id,
    }


def test_source_registry_keeps_unknown_sources_and_records_trusted_human_review(
    client: TestClient,
) -> None:
    before = client.get(
        "/api/v1/projects/project_source/source-registry",
        headers={"tenant-id": "tenant_source"},
    )
    assert before.status_code == 200
    assert before.json()["meta"]["classification_policy"] == "exact_host_human_review_only"
    entry = before.json()["data"][0]
    assert entry["normalized_host"] == "news.example.com"
    assert entry["classification_status"] == "unclassified"
    assert entry["current_revision"] is None
    assert entry["citation_count"] == 4

    created = client.post(
        "/api/v1/projects/project_source/source-registry/news.example.com/reviews",
        headers={
            "tenant-id": "tenant_source",
            "X-AIRank-User-Id": "trusted-reviewer",
            "Idempotency-Key": "source-review-one",
        },
        json=review_payload(),
    )
    assert created.status_code == 201
    reviewed = created.json()["data"]
    assert reviewed["classification_status"] == "reviewed"
    assert reviewed["current_revision"]["classification_method"] == "human_review"
    assert reviewed["current_revision"]["reviewed_by"] == "trusted-reviewer"
    assert reviewed["current_revision"]["authority_level"] == "medium"
    assert reviewed["current_revision"]["request_sha256"]

    replay = client.post(
        "/api/v1/projects/project_source/source-registry/news.example.com/reviews",
        headers={
            "tenant-id": "tenant_source",
            "X-AIRank-User-Id": "trusted-reviewer",
            "Idempotency-Key": "source-review-one",
        },
        json=review_payload(),
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["current_revision"]["idempotent_replay"] is True


def test_source_registry_requires_explicit_latest_revision_and_tenant_scope(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/v1/projects/project_source/source-registry/news.example.com/reviews",
        headers={
            "tenant-id": "tenant_source",
            "X-AIRank-User-Id": "reviewer-one",
            "Idempotency-Key": "source-review-first",
        },
        json=review_payload(),
    ).json()["data"]["current_revision"]

    stale = client.post(
        "/api/v1/projects/project_source/source-registry/news.example.com/reviews",
        headers={
            "tenant-id": "tenant_source",
            "X-AIRank-User-Id": "reviewer-two",
            "Idempotency-Key": "source-review-stale",
        },
        json=review_payload(),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "SOURCE_CLASSIFICATION_VERSION_CONFLICT"
    assert stale.json()["error"]["details"]["expected_revision_id"] == first["revision_id"]

    second_payload = review_payload(supersedes_revision_id=first["revision_id"])
    second_payload["authority_level"] = "high"
    second = client.post(
        "/api/v1/projects/project_source/source-registry/news.example.com/reviews",
        headers={
            "tenant-id": "tenant_source",
            "X-AIRank-User-Id": "reviewer-two",
            "Idempotency-Key": "source-review-second",
        },
        json=second_payload,
    )
    assert second.status_code == 201
    detail = second.json()["data"]
    assert detail["current_revision"]["revision_number"] == 2
    assert detail["current_revision"]["supersedes_revision_id"] == first["revision_id"]
    assert len(detail["history"]) == 2

    replay_old = client.post(
        "/api/v1/projects/project_source/source-registry/news.example.com/reviews",
        headers={
            "tenant-id": "tenant_source",
            "X-AIRank-User-Id": "reviewer-one",
            "Idempotency-Key": "source-review-first",
        },
        json=review_payload(),
    )
    assert replay_old.status_code == 201
    replayed_detail = replay_old.json()["data"]
    assert replayed_detail["current_revision"]["revision_number"] == 2
    assert replayed_detail["current_revision"]["idempotent_replay"] is False
    assert replayed_detail["history"][1]["revision_number"] == 1
    assert replayed_detail["history"][1]["idempotent_replay"] is True

    hidden = client.get(
        "/api/v1/projects/project_source/source-registry",
        headers={"tenant-id": "tenant_other"},
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_source_registry_does_not_create_a_classification_for_an_unseen_host(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/projects/project_source/source-registry/unseen.example.com/reviews",
        headers={
            "tenant-id": "tenant_source",
            "X-AIRank-User-Id": "reviewer",
            "Idempotency-Key": "source-review-unseen",
        },
        json=review_payload(),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SOURCE_REGISTRY_ENTRY_NOT_FOUND"

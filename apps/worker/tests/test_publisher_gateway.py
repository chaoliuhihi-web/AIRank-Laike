from __future__ import annotations

from typing import Any, Mapping

import pytest

from airank_domain import sha256_text
from airank_worker.publisher import PublishSnapshot, PublisherError, PublisherGateway


class FakePublishTransport:
    def __init__(self, responses: list[tuple[int, Mapping[str, str], Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> tuple[int, Mapping[str, str], Any]:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.responses.pop(0)


def public_resolver(host: str, port: int, **_: object) -> list[tuple[object, ...]]:
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def snapshot(*, channel: str = "http", endpoint: str = "https://publisher.example.test/v1/publish") -> PublishSnapshot:
    body_md = "# AIRank\n\n已审核事实。"
    return PublishSnapshot(
        tenant_id="tenant_1",
        project_id="project_1",
        package_id="package_1",
        snapshot_id="snapshot_1",
        channel=channel,
        idempotency_key="publish-task-1",
        target_endpoint=endpoint,
        title="AIRank 事实页",
        body_md=body_md,
        content_sha256=sha256_text(body_md),
        manifest={"immutable": True},
        package_status="queued",
        published_url=None,
        package_metadata={},
    )


def test_generic_http_publisher_sends_idempotency_and_returns_hash_only_receipt() -> None:
    transport = FakePublishTransport(
        [(201, {}, {"id": "remote_1", "published_url": "https://publisher.example.test/pages/airank"})]
    )
    gateway = PublisherGateway(
        env={
            "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
            "AIRANK_PUBLISH_HTTP_BEARER_TOKEN": "secret-never-persist",
        },
        transport=transport,
        resolver=public_resolver,
    )

    side_effect_markers: list[str] = []
    receipt = gateway.publish(
        snapshot(),
        before_external_effect=lambda: side_effect_markers.append("started"),
    )

    assert receipt.status_code == 201
    assert receipt.remote_id == "remote_1"
    assert len(receipt.request_sha256) == 64
    assert len(receipt.response_sha256) == 64
    assert transport.calls[0]["headers"]["Idempotency-Key"] == "publish-task-1"
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer secret-never-persist"
    assert "secret-never-persist" not in repr(receipt)
    assert side_effect_markers == ["started"]


def test_publisher_rejects_non_allowlisted_and_private_endpoints_before_transport() -> None:
    transport = FakePublishTransport([])
    gateway = PublisherGateway(
        env={
            "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
            "AIRANK_PUBLISH_HTTP_BEARER_TOKEN": "secret",
        },
        transport=transport,
        resolver=lambda host, port, **_: [(2, 1, 6, "", ("127.0.0.1", port))],
    )

    with pytest.raises(PublisherError) as caught:
        gateway.publish(snapshot())

    assert caught.value.code == "PUBLISH_ENDPOINT_FORBIDDEN"
    assert transport.calls == []


def test_wordpress_uses_deterministic_slug_lookup_before_create() -> None:
    transport = FakePublishTransport(
        [(200, {}, [{"id": 42, "link": "https://publisher.example.test/airank-fact"}])]
    )
    gateway = PublisherGateway(
        env={
            "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
            "AIRANK_WORDPRESS_USERNAME": "publisher",
            "AIRANK_WORDPRESS_APP_PASSWORD": "app-password",
        },
        transport=transport,
        resolver=public_resolver,
    )

    side_effect_markers: list[str] = []
    receipt = gateway.publish(
        snapshot(channel="wordpress", endpoint="https://publisher.example.test/wp-json/wp/v2/posts"),
        before_external_effect=lambda: side_effect_markers.append("started"),
    )

    assert receipt.idempotent_replay is True
    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"
    assert "slug=airank-package-1" in transport.calls[0]["url"]
    assert side_effect_markers == []


def test_wordpress_marks_external_effect_only_after_empty_reconciliation_lookup() -> None:
    transport = FakePublishTransport(
        [
            (200, {}, []),
            (201, {}, {"id": 43, "link": "https://publisher.example.test/airank-created"}),
        ]
    )
    gateway = PublisherGateway(
        env={
            "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
            "AIRANK_WORDPRESS_USERNAME": "publisher",
            "AIRANK_WORDPRESS_APP_PASSWORD": "app-password",
        },
        transport=transport,
        resolver=public_resolver,
    )
    side_effect_markers: list[str] = []

    receipt = gateway.publish(
        snapshot(channel="wordpress", endpoint="https://publisher.example.test/wp-json/wp/v2/posts"),
        before_external_effect=lambda: side_effect_markers.append("started"),
    )

    assert receipt.idempotent_replay is False
    assert [call["method"] for call in transport.calls] == ["GET", "POST"]
    assert side_effect_markers == ["started"]


def test_wordpress_lookup_failure_never_starts_external_post() -> None:
    transport = FakePublishTransport([(503, {}, {"code": "temporarily_unavailable"})])
    gateway = PublisherGateway(
        env={
            "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
            "AIRANK_WORDPRESS_USERNAME": "publisher",
            "AIRANK_WORDPRESS_APP_PASSWORD": "app-password",
        },
        transport=transport,
        resolver=public_resolver,
    )
    side_effect_markers: list[str] = []

    with pytest.raises(PublisherError) as caught:
        gateway.publish(
            snapshot(channel="wordpress", endpoint="https://publisher.example.test/wp-json/wp/v2/posts"),
            before_external_effect=lambda: side_effect_markers.append("started"),
        )

    assert caught.value.code == "PUBLISH_RECONCILIATION_LOOKUP_FAILED"
    assert [call["method"] for call in transport.calls] == ["GET"]
    assert side_effect_markers == []


def test_publisher_blocks_mutated_snapshot_and_missing_credential() -> None:
    clean = snapshot()
    mutated = PublishSnapshot(**{**clean.__dict__, "body_md": clean.body_md + "篡改"})
    gateway = PublisherGateway(
        env={"AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test"},
        transport=FakePublishTransport([]),
        resolver=public_resolver,
    )

    with pytest.raises(PublisherError) as hash_error:
        gateway.publish(mutated)
    assert hash_error.value.code == "PUBLISH_SNAPSHOT_HASH_MISMATCH"

    with pytest.raises(PublisherError) as credential_error:
        gateway.publish(clean)
    assert credential_error.value.code == "PUBLISH_CREDENTIAL_MISSING"

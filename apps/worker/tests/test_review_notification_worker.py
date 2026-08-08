from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import text

from airank_outbound_security import OutboundResponse
from airank_worker.review_notification import (
    MySQLReviewNotificationRepository,
    ReviewNotificationConfig,
    ReviewNotificationError,
    ReviewNotificationWebhookClient,
)


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


class SequenceHttpClient:
    def __init__(self, responses: list[OutboundResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, str], bytes]] = []

    def request(self, method: str, url: str, *, headers=None, body=None):
        self.requests.append((method, url, dict(headers or {}), body or b""))
        return self.responses.pop(0)


def build_repository() -> MySQLReviewNotificationRepository:
    repository = MySQLReviewNotificationRepository(
        "sqlite+pysqlite:///:memory:",
        tenant_id="tenant_1",
        project_id="project_1",
    )
    with repository.engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE airank_outbox_events (
              id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
              project_id VARCHAR(64), event_type VARCHAR(128) NOT NULL,
              aggregate_type VARCHAR(128) NOT NULL, aggregate_id VARCHAR(64) NOT NULL,
              trace_id VARCHAR(128), status VARCHAR(32) NOT NULL,
              available_at DATETIME NOT NULL, published_at DATETIME,
              attempt_count INT NOT NULL, payload_json TEXT,
              error_code VARCHAR(128), error_message TEXT,
              created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_notification_deliveries (
              id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
              project_id VARCHAR(64) NOT NULL, outbox_event_id VARCHAR(64) NOT NULL,
              channel VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL,
              attempt_count INT NOT NULL, max_attempts INT NOT NULL,
              next_attempt_at DATETIME NOT NULL, locked_by VARCHAR(128),
              locked_at DATETIME, timeout_seconds INT NOT NULL,
              endpoint_host VARCHAR(255) NOT NULL, config_fingerprint VARCHAR(64) NOT NULL,
              latest_receipt_id VARCHAR(64), last_error_code VARCHAR(128),
              created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
              UNIQUE (tenant_id, outbox_event_id, channel)
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_notification_delivery_receipts (
              id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
              project_id VARCHAR(64) NOT NULL, delivery_id VARCHAR(64) NOT NULL,
              outbox_event_id VARCHAR(64) NOT NULL, channel VARCHAR(32) NOT NULL,
              attempt_number INT NOT NULL, status VARCHAR(32) NOT NULL,
              request_sha256 VARCHAR(64) NOT NULL, response_status INT,
              response_sha256 VARCHAR(64), provider_receipt_id VARCHAR(255),
              endpoint_host VARCHAR(255) NOT NULL, connected_ip VARCHAR(64),
              error_code VARCHAR(128), retryable INT NOT NULL,
              started_at DATETIME NOT NULL, finished_at DATETIME NOT NULL,
              created_at DATETIME NOT NULL,
              UNIQUE (tenant_id, delivery_id, attempt_number)
            )
        """))
        conn.execute(text("""
            INSERT INTO airank_outbox_events (
              id, tenant_id, project_id, event_type, aggregate_type,
              aggregate_id, trace_id, status, available_at, published_at,
              attempt_count, payload_json, created_at, updated_at
            ) VALUES (
              'event_1', 'tenant_1', 'project_1',
              'evidence_review.sla_overdue.v1', 'evidence_review_case',
              'case_1', 'trace_1', 'pending', :now, NULL, 0, :payload,
              :now, :now
            )
        """), {
            "now": NOW,
            "payload": json.dumps({
                "schema_version": "airank.evidence-review-sla-escalation.v1",
                "case_id": "case_1",
                "routing_team_id": "team_1",
                "eligible_recipient_count": 2,
            }),
        })
    return repository


def response(status: int, body: bytes, request_id: str | None = None) -> OutboundResponse:
    headers = {"x-request-id": request_id} if request_id else {}
    return OutboundResponse(
        status=status,
        headers=headers,
        body=body,
        final_url="https://notify.example.com/review",
        redirect_count=0,
        connected_ip="203.0.113.10",
    )


def test_notification_retries_then_persists_verified_channel_receipt_without_secret() -> None:
    repository = build_repository()
    config = ReviewNotificationConfig(
        webhook_url="https://notify.example.com/review",
        bearer_token="unit-test-secret",
        max_attempts=3,
    )
    http = SequenceHttpClient([
        response(503, b'{"error":"busy"}'),
        response(202, b'{"message_id":"message-123"}', "request-123"),
    ])
    client = ReviewNotificationWebhookClient(config, http_client=http)

    first = repository.claim_next("worker-1", config, NOW)
    assert first is not None
    with pytest.raises(ReviewNotificationError) as captured:
        client.send(first)
    assert captured.value.retryable is True
    repository.fail(first, captured.value, NOW)

    assert repository.claim_next("worker-1", config, NOW + timedelta(seconds=4)) is None
    second = repository.claim_next("worker-1", config, NOW + timedelta(seconds=5))
    assert second is not None
    receipt = client.send(second)
    repository.succeed(second, receipt, NOW + timedelta(seconds=5))

    assert receipt.provider_receipt_id == "request-123"
    assert receipt.response_status == 202
    with repository.engine.begin() as conn:
        event = conn.execute(text("SELECT * FROM airank_outbox_events")).mappings().one()
        delivery = conn.execute(text("SELECT * FROM airank_notification_deliveries")).mappings().one()
        receipts = conn.execute(text("SELECT * FROM airank_notification_delivery_receipts ORDER BY attempt_number")).mappings().all()
    assert event["status"] == "published"
    assert event["attempt_count"] == 2
    assert delivery["status"] == "succeeded"
    assert delivery["attempt_count"] == 2
    assert [item["status"] for item in receipts] == ["failed", "succeeded"]
    assert receipts[1]["provider_receipt_id"] == "request-123"
    persisted = json.dumps([dict(event), dict(delivery), *map(dict, receipts)], default=str)
    assert "unit-test-secret" not in persisted
    assert http.requests[0][2]["Authorization"] == "Bearer unit-test-secret"


def test_notification_non_retryable_rejection_marks_outbox_failed() -> None:
    repository = build_repository()
    config = ReviewNotificationConfig(
        webhook_url="https://notify.example.com/review",
        bearer_token=None,
    )
    client = ReviewNotificationWebhookClient(
        config, http_client=SequenceHttpClient([response(400, b"bad request")])
    )
    delivery = repository.claim_next("worker-1", config, NOW)
    assert delivery is not None
    with pytest.raises(ReviewNotificationError) as captured:
        client.send(delivery)
    repository.fail(delivery, captured.value, NOW)

    with repository.engine.begin() as conn:
        assert conn.execute(text("SELECT status FROM airank_outbox_events")).scalar_one() == "failed"
        assert conn.execute(text("SELECT status FROM airank_notification_deliveries")).scalar_one() == "failed"


def test_notification_requires_server_side_webhook_configuration_before_claim() -> None:
    repository = build_repository()
    config = ReviewNotificationConfig(webhook_url=None, bearer_token=None)
    with pytest.raises(ReviewNotificationError) as captured:
        repository.claim_next("worker-1", config, NOW)
    assert captured.value.code == "REVIEW_NOTIFICATION_NOT_CONFIGURED"
    with repository.engine.begin() as conn:
        assert conn.execute(text("SELECT attempt_count FROM airank_outbox_events")).scalar_one() == 0

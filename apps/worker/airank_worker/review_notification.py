from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Mapping, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import create_engine, text

from airank_outbound_security import (
    OutboundPolicy,
    OutboundSecurityError,
    SafeOutboundClient,
)


EVENT_TYPE = "evidence_review.sla_overdue.v1"
DELIVERY_CONTRACT_VERSION = "airank.review-notification-webhook.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _clean(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


@dataclass(frozen=True)
class ReviewNotificationConfig:
    webhook_url: str | None
    bearer_token: str | None
    timeout_seconds: float = 10.0
    max_response_bytes: int = 64_000
    max_attempts: int = 3

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None
    ) -> "ReviewNotificationConfig":
        source = env or os.environ
        try:
            timeout = min(
                30.0,
                max(1.0, float(source.get("AIRANK_REVIEW_NOTIFICATION_TIMEOUT_SECONDS") or 10)),
            )
        except ValueError:
            timeout = 10.0
        try:
            max_attempts = min(
                10,
                max(1, int(source.get("AIRANK_REVIEW_NOTIFICATION_MAX_ATTEMPTS") or 3)),
            )
        except ValueError:
            max_attempts = 3
        return cls(
            webhook_url=_clean(source.get("AIRANK_REVIEW_NOTIFICATION_WEBHOOK_URL")),
            bearer_token=_clean(source.get("AIRANK_REVIEW_NOTIFICATION_BEARER_TOKEN")),
            timeout_seconds=timeout,
            max_attempts=max_attempts,
        )

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    @property
    def endpoint_host(self) -> str:
        return str(urlsplit(self.webhook_url or "").hostname or "").lower()

    @property
    def fingerprint(self) -> str:
        token_hash = hashlib.sha256((self.bearer_token or "").encode()).hexdigest()
        return canonical_sha256(
            {
                "contract_version": DELIVERY_CONTRACT_VERSION,
                "webhook_url": self.webhook_url,
                "bearer_token_sha256": token_hash,
            }
        )


class ReviewNotificationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        request_sha256: str | None = None,
        response_status: int | None = None,
        response_sha256: str | None = None,
        connected_ip: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.request_sha256 = request_sha256
        self.response_status = response_status
        self.response_sha256 = response_sha256
        self.connected_ip = connected_ip


@dataclass(frozen=True)
class ReviewNotificationDelivery:
    delivery_id: str
    tenant_id: str
    project_id: str
    outbox_event_id: str
    event_type: str
    aggregate_id: str
    trace_id: str | None
    payload: dict[str, object]
    channel: str
    attempt_number: int
    max_attempts: int
    endpoint_host: str
    config_fingerprint: str
    started_at: datetime


@dataclass(frozen=True)
class ReviewNotificationReceipt:
    delivery_id: str
    outbox_event_id: str
    channel: str
    status: str
    attempt_number: int
    request_sha256: str
    response_status: int | None
    response_sha256: str | None
    provider_receipt_id: str | None
    endpoint_host: str
    connected_ip: str | None
    error_code: str | None
    retryable: bool

    def to_record(self) -> dict[str, object]:
        return asdict(self)


class NotificationHttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ): ...


class ReviewNotificationWebhookClient:
    def __init__(
        self,
        config: ReviewNotificationConfig | None = None,
        *,
        http_client: NotificationHttpClient | None = None,
    ) -> None:
        self.config = config or ReviewNotificationConfig.from_env()
        if http_client is not None:
            self.http_client = http_client
        elif self.config.configured:
            self.http_client = SafeOutboundClient(
                OutboundPolicy(
                    allowed_hosts={self.config.endpoint_host},
                    require_https=True,
                ),
                timeout_seconds=self.config.timeout_seconds,
                max_response_bytes=self.config.max_response_bytes,
                max_redirects=0,
            )
        else:
            self.http_client = None

    def send(self, delivery: ReviewNotificationDelivery) -> ReviewNotificationReceipt:
        if not self.config.webhook_url or self.http_client is None:
            raise ReviewNotificationError(
                "REVIEW_NOTIFICATION_NOT_CONFIGURED",
                "review notification webhook is not configured",
            )
        body_value = {
            "contract_version": DELIVERY_CONTRACT_VERSION,
            "event_id": delivery.outbox_event_id,
            "event_type": delivery.event_type,
            "tenant_id": delivery.tenant_id,
            "project_id": delivery.project_id,
            "aggregate_id": delivery.aggregate_id,
            "payload": delivery.payload,
        }
        body = json.dumps(
            body_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        request_sha256 = hashlib.sha256(body).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": delivery.outbox_event_id,
            "X-AIRank-Contract": DELIVERY_CONTRACT_VERSION,
        }
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        try:
            response = self.http_client.request(
                "POST", self.config.webhook_url, headers=headers, body=body
            )
        except OutboundSecurityError as exc:
            raise ReviewNotificationError(
                f"REVIEW_NOTIFICATION_{exc.code.removeprefix('OUTBOUND_')}",
                "review notification outbound request failed",
                retryable=exc.retryable,
                request_sha256=request_sha256,
            ) from exc
        response_sha256 = hashlib.sha256(response.body).hexdigest()
        if response.status < 200 or response.status >= 300:
            raise ReviewNotificationError(
                "REVIEW_NOTIFICATION_HTTP_FAILED",
                "review notification endpoint rejected the request",
                retryable=response.status in {408, 425, 429} or response.status >= 500,
                request_sha256=request_sha256,
                response_status=response.status,
                response_sha256=response_sha256,
                connected_ip=response.connected_ip,
            )
        receipt_id = _extract_receipt_id(response.headers, response.body)
        return ReviewNotificationReceipt(
            delivery_id=delivery.delivery_id,
            outbox_event_id=delivery.outbox_event_id,
            channel=delivery.channel,
            status="succeeded",
            attempt_number=delivery.attempt_number,
            request_sha256=request_sha256,
            response_status=response.status,
            response_sha256=response_sha256,
            provider_receipt_id=receipt_id,
            endpoint_host=delivery.endpoint_host,
            connected_ip=response.connected_ip,
            error_code=None,
            retryable=False,
        )


class MySQLReviewNotificationRepository:
    def __init__(
        self,
        database_url: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        if project_id and not tenant_id:
            raise ValueError("project scope requires tenant scope")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.tenant_id = tenant_id
        self.project_id = project_id

    def claim_next(
        self,
        worker_id: str,
        config: ReviewNotificationConfig,
        now: datetime,
    ) -> ReviewNotificationDelivery | None:
        if not config.configured or not config.endpoint_host:
            raise ReviewNotificationError(
                "REVIEW_NOTIFICATION_NOT_CONFIGURED",
                "review notification webhook is not configured",
            )
        scope_sql, params = self._scope_sql("event")
        params.update({"now": now, "channel": "webhook"})
        lock_sql = " FOR UPDATE SKIP LOCKED" if self.engine.dialect.name == "mysql" else ""
        stale_before = now - timedelta(seconds=max(30, int(config.timeout_seconds * 3)))
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_notification_deliveries
                    SET status='queued', locked_by=NULL, locked_at=NULL,
                        next_attempt_at=:now, last_error_code='REVIEW_NOTIFICATION_LEASE_EXPIRED',
                        updated_at=:now
                    WHERE status='running' AND locked_at<:stale_before
                    """
                ),
                {"now": now, "stale_before": stale_before},
            )
            row = conn.execute(
                text(
                    f"""
                    SELECT event.*, delivery.id AS delivery_id,
                           delivery.status AS delivery_status,
                           delivery.attempt_count AS delivery_attempt_count,
                           delivery.max_attempts AS delivery_max_attempts
                    FROM airank_outbox_events event
                    LEFT JOIN airank_notification_deliveries delivery
                      ON delivery.tenant_id=event.tenant_id
                     AND delivery.outbox_event_id=event.id
                     AND delivery.channel=:channel
                    WHERE event.event_type='{EVENT_TYPE}'
                      AND event.status='pending' AND event.available_at<=:now
                      AND (delivery.id IS NULL OR (
                        delivery.status='queued' AND delivery.next_attempt_at<=:now
                      )) {scope_sql}
                    ORDER BY event.available_at, event.id
                    LIMIT 1{lock_sql}
                    """
                ),
                params,
            ).mappings().first()
            if row is None:
                return None
            delivery_id = str(row["delivery_id"] or f"notification_{uuid4().hex}")
            attempt_number = int(row["delivery_attempt_count"] or 0) + 1
            max_attempts = int(row["delivery_max_attempts"] or config.max_attempts)
            if row["delivery_id"] is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_notification_deliveries (
                          id, tenant_id, project_id, outbox_event_id, channel,
                          status, attempt_count, max_attempts, next_attempt_at,
                          locked_by, locked_at, timeout_seconds, endpoint_host,
                          config_fingerprint, latest_receipt_id, last_error_code,
                          created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :event_id, 'webhook',
                          'running', 1, :max_attempts, :now, :worker_id, :now,
                          :timeout_seconds, :endpoint_host, :fingerprint,
                          NULL, NULL, :now, :now
                        )
                        """
                    ),
                    {
                        "id": delivery_id,
                        "tenant_id": row["tenant_id"],
                        "project_id": row["project_id"],
                        "event_id": row["id"],
                        "max_attempts": config.max_attempts,
                        "now": now,
                        "worker_id": worker_id,
                        "timeout_seconds": max(30, int(config.timeout_seconds * 3)),
                        "endpoint_host": config.endpoint_host,
                        "fingerprint": config.fingerprint,
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE airank_notification_deliveries
                        SET status='running', attempt_count=:attempt_count,
                            locked_by=:worker_id, locked_at=:now,
                            endpoint_host=:endpoint_host,
                            config_fingerprint=:fingerprint,
                            last_error_code=NULL, updated_at=:now
                        WHERE id=:id AND status='queued'
                        """
                    ),
                    {
                        "attempt_count": attempt_number,
                        "worker_id": worker_id,
                        "now": now,
                        "endpoint_host": config.endpoint_host,
                        "fingerprint": config.fingerprint,
                        "id": delivery_id,
                    },
                )
            conn.execute(
                text(
                    "UPDATE airank_outbox_events SET attempt_count=attempt_count+1, "
                    "updated_at=:now WHERE id=:event_id"
                ),
                {"now": now, "event_id": row["id"]},
            )
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            payload = {}
        return ReviewNotificationDelivery(
            delivery_id=delivery_id,
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            outbox_event_id=str(row["id"]),
            event_type=str(row["event_type"]),
            aggregate_id=str(row["aggregate_id"]),
            trace_id=str(row["trace_id"]) if row["trace_id"] is not None else None,
            payload=payload,
            channel="webhook",
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            endpoint_host=config.endpoint_host,
            config_fingerprint=config.fingerprint,
            started_at=now,
        )

    def succeed(
        self,
        delivery: ReviewNotificationDelivery,
        receipt: ReviewNotificationReceipt,
        completed_at: datetime,
    ) -> None:
        receipt_id = f"notification_receipt_{uuid4().hex}"
        with self.engine.begin() as conn:
            self._insert_receipt(conn, receipt_id, delivery, receipt, completed_at)
            result = conn.execute(
                text(
                    """
                    UPDATE airank_notification_deliveries
                    SET status='succeeded', latest_receipt_id=:receipt_id,
                        locked_by=NULL, locked_at=NULL, last_error_code=NULL,
                        updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:delivery_id
                      AND status='running' AND attempt_count=:attempt_number
                    """
                ),
                {
                    "receipt_id": receipt_id,
                    "completed_at": completed_at,
                    "tenant_id": delivery.tenant_id,
                    "delivery_id": delivery.delivery_id,
                    "attempt_number": delivery.attempt_number,
                },
            )
            if result.rowcount != 1:
                raise ReviewNotificationError(
                    "REVIEW_NOTIFICATION_STATE_CONFLICT",
                    "review notification delivery state changed",
                )
            conn.execute(
                text(
                    """
                    UPDATE airank_outbox_events
                    SET status='published', published_at=:completed_at,
                        error_code=NULL, error_message=NULL, updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:event_id AND status='pending'
                    """
                ),
                {
                    "completed_at": completed_at,
                    "tenant_id": delivery.tenant_id,
                    "event_id": delivery.outbox_event_id,
                },
            )

    def fail(
        self,
        delivery: ReviewNotificationDelivery,
        error: ReviewNotificationError,
        completed_at: datetime,
    ) -> ReviewNotificationReceipt:
        request_sha256 = error.request_sha256 or canonical_sha256(
            {"event_id": delivery.outbox_event_id, "attempt": delivery.attempt_number}
        )
        receipt = ReviewNotificationReceipt(
            delivery_id=delivery.delivery_id,
            outbox_event_id=delivery.outbox_event_id,
            channel=delivery.channel,
            status="failed",
            attempt_number=delivery.attempt_number,
            request_sha256=request_sha256,
            response_status=error.response_status,
            response_sha256=error.response_sha256,
            provider_receipt_id=None,
            endpoint_host=delivery.endpoint_host,
            connected_ip=error.connected_ip,
            error_code=error.code,
            retryable=error.retryable,
        )
        retry = error.retryable and delivery.attempt_number < delivery.max_attempts
        retry_at = completed_at + timedelta(
            seconds=min(300, 5 * (2 ** max(0, delivery.attempt_number - 1)))
        )
        receipt_id = f"notification_receipt_{uuid4().hex}"
        with self.engine.begin() as conn:
            self._insert_receipt(conn, receipt_id, delivery, receipt, completed_at)
            result = conn.execute(
                text(
                    """
                    UPDATE airank_notification_deliveries
                    SET status=:status, next_attempt_at=:next_attempt_at,
                        latest_receipt_id=:receipt_id, locked_by=NULL, locked_at=NULL,
                        last_error_code=:error_code, updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:delivery_id
                      AND status='running' AND attempt_count=:attempt_number
                    """
                ),
                {
                    "status": "queued" if retry else "failed",
                    "next_attempt_at": retry_at if retry else completed_at,
                    "receipt_id": receipt_id,
                    "error_code": error.code,
                    "completed_at": completed_at,
                    "tenant_id": delivery.tenant_id,
                    "delivery_id": delivery.delivery_id,
                    "attempt_number": delivery.attempt_number,
                },
            )
            if result.rowcount != 1:
                raise ReviewNotificationError(
                    "REVIEW_NOTIFICATION_STATE_CONFLICT",
                    "review notification delivery state changed",
                )
            conn.execute(
                text(
                    """
                    UPDATE airank_outbox_events
                    SET status=:status, available_at=:available_at,
                        error_code=:error_code, error_message=:error_message,
                        updated_at=:completed_at
                    WHERE tenant_id=:tenant_id AND id=:event_id AND status='pending'
                    """
                ),
                {
                    "status": "pending" if retry else "failed",
                    "available_at": retry_at if retry else completed_at,
                    "error_code": error.code,
                    "error_message": error.message[:1000],
                    "completed_at": completed_at,
                    "tenant_id": delivery.tenant_id,
                    "event_id": delivery.outbox_event_id,
                },
            )
        return receipt

    @staticmethod
    def _insert_receipt(
        conn,
        receipt_id: str,
        delivery: ReviewNotificationDelivery,
        receipt: ReviewNotificationReceipt,
        completed_at: datetime,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO airank_notification_delivery_receipts (
                  id, tenant_id, project_id, delivery_id, outbox_event_id,
                  channel, attempt_number, status, request_sha256,
                  response_status, response_sha256, provider_receipt_id,
                  endpoint_host, connected_ip, error_code, retryable,
                  started_at, finished_at, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :delivery_id, :event_id,
                  :channel, :attempt_number, :status, :request_sha256,
                  :response_status, :response_sha256, :provider_receipt_id,
                  :endpoint_host, :connected_ip, :error_code, :retryable,
                  :started_at, :finished_at, :created_at
                )
                """
            ),
            {
                "id": receipt_id,
                "tenant_id": delivery.tenant_id,
                "project_id": delivery.project_id,
                "delivery_id": delivery.delivery_id,
                "event_id": delivery.outbox_event_id,
                "channel": receipt.channel,
                "attempt_number": receipt.attempt_number,
                "status": receipt.status,
                "request_sha256": receipt.request_sha256,
                "response_status": receipt.response_status,
                "response_sha256": receipt.response_sha256,
                "provider_receipt_id": receipt.provider_receipt_id,
                "endpoint_host": receipt.endpoint_host,
                "connected_ip": receipt.connected_ip,
                "error_code": receipt.error_code,
                "retryable": receipt.retryable,
                "started_at": delivery.started_at,
                "finished_at": completed_at,
                "created_at": completed_at,
            },
        )

    def _scope_sql(self, alias: str) -> tuple[str, dict[str, object]]:
        clauses: list[str] = []
        params: dict[str, object] = {}
        if self.tenant_id:
            clauses.append(f"{alias}.tenant_id=:scope_tenant_id")
            params["scope_tenant_id"] = self.tenant_id
        if self.project_id:
            clauses.append(f"{alias}.project_id=:scope_project_id")
            params["scope_project_id"] = self.project_id
        return (" AND " + " AND ".join(clauses) if clauses else "", params)


def run_next_review_notification(
    repository: MySQLReviewNotificationRepository,
    client: ReviewNotificationWebhookClient,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> ReviewNotificationReceipt | None:
    started_at = now or utc_now()
    delivery = repository.claim_next(worker_id, client.config, started_at)
    if delivery is None:
        return None
    try:
        receipt = client.send(delivery)
    except ReviewNotificationError as exc:
        repository.fail(delivery, exc, utc_now())
        raise
    repository.succeed(delivery, receipt, utc_now())
    return receipt


def _extract_receipt_id(headers: Mapping[str, str], body: bytes) -> str | None:
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    for key in ("x-request-id", "x-trace-id", "request-id"):
        value = _clean(lowered.get(key))
        if value:
            return value[:255]
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("request_id", "requestId", "message_id", "messageId", "id"):
        value = _clean(payload.get(key))
        if value:
            return value[:255]
    return None

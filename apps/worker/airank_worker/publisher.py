from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import socket
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import uuid4

from sqlalchemy import create_engine, text

from airank_domain import AsyncJob, sha256_text
from airank_outbound_security import (
    OutboundPolicy,
    OutboundSecurityError,
    SafeOutboundClient,
)

from .lease import InMemoryJobLeaseStore, MySQLJobLeaseStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PublishSnapshot:
    tenant_id: str
    project_id: str
    package_id: str
    snapshot_id: str
    channel: str
    idempotency_key: str
    target_endpoint: str
    title: str
    body_md: str
    content_sha256: str
    manifest: Mapping[str, Any]
    package_status: str
    published_url: str | None
    package_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PublisherReceipt:
    status_code: int
    published_url: str
    response_sha256: str
    request_sha256: str
    remote_id: str | None = None
    idempotent_replay: bool = False


class PublisherError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class PublishTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> tuple[int, Mapping[str, str], Any]:
        ...


class UrllibPublishTransport:
    """Compatibility name for the pinned, no-proxy AIRank outbound client."""

    def __init__(self, policy: OutboundPolicy, *, max_response_bytes: int) -> None:
        self.policy = policy
        self.max_response_bytes = max_response_bytes

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> tuple[int, Mapping[str, str], Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        try:
            response = SafeOutboundClient(
                self.policy,
                timeout_seconds=timeout_seconds,
                max_response_bytes=self.max_response_bytes,
                max_redirects=0,
            ).request(method, url, headers=headers, body=body)
        except OutboundSecurityError as exc:
            raise PublisherError(
                "PUBLISH_NETWORK_FAILED" if exc.retryable else "PUBLISH_ENDPOINT_FORBIDDEN",
                exc.message,
                retryable=exc.retryable,
            ) from exc
        try:
            parsed = json.loads(response.body.decode("utf-8")) if response.body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if response.status < 200 or response.status >= 300:
                parsed = {}
            else:
                raise PublisherError(
                    "PUBLISH_RESPONSE_INVALID",
                    "publisher returned invalid JSON",
                ) from exc
        return response.status, response.headers, parsed


class PublisherGateway:
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        transport: PublishTransport | None = None,
        resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
    ) -> None:
        self.env = env if env is not None else os.environ
        self.resolver = resolver
        try:
            self.timeout_seconds = max(1.0, float(self.env.get("AIRANK_PUBLISH_TIMEOUT_SECONDS") or 30))
        except (TypeError, ValueError):
            self.timeout_seconds = 30.0
        try:
            self.max_response_bytes = max(
                1,
                int(self.env.get("AIRANK_PUBLISH_MAX_RESPONSE_BYTES") or 1_000_000),
            )
        except (TypeError, ValueError):
            self.max_response_bytes = 1_000_000
        allowed_hosts = {
            item.strip().lower().rstrip(".")
            for item in str(self.env.get("AIRANK_PUBLISH_ALLOWED_HOSTS") or "").split(",")
            if item.strip()
        }
        self.outbound_policy = OutboundPolicy(
            allowed_hosts=allowed_hosts,
            resolver=self.resolver,
        )
        self.transport = transport or UrllibPublishTransport(
            self.outbound_policy,
            max_response_bytes=self.max_response_bytes,
        )

    def request_sha256(self, snapshot: PublishSnapshot) -> str:
        payload = self._public_payload(snapshot)
        return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    def publish(self, snapshot: PublishSnapshot) -> PublisherReceipt:
        self._validate_endpoint(snapshot.target_endpoint)
        if sha256_text(snapshot.body_md) != snapshot.content_sha256:
            raise PublisherError(
                "PUBLISH_SNAPSHOT_HASH_MISMATCH",
                "immutable publish snapshot content hash does not match",
            )
        if snapshot.channel == "http":
            return self._publish_http(snapshot)
        if snapshot.channel == "wordpress":
            return self._publish_wordpress(snapshot)
        raise PublisherError("PUBLISH_CHANNEL_UNSUPPORTED", "publisher channel is not supported")

    def _publish_http(self, snapshot: PublishSnapshot) -> PublisherReceipt:
        token = str(self.env.get("AIRANK_PUBLISH_HTTP_BEARER_TOKEN") or "").strip()
        if not token:
            raise PublisherError("PUBLISH_CREDENTIAL_MISSING", "generic HTTP publisher credential is missing")
        payload = self._public_payload(snapshot)
        status, _, response = self.transport.request(
            "POST",
            snapshot.target_endpoint,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": snapshot.idempotency_key,
                "X-AIRank-Content-SHA256": snapshot.content_sha256,
            },
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        return self._receipt(snapshot, status, response)

    def _publish_wordpress(self, snapshot: PublishSnapshot) -> PublisherReceipt:
        username = str(self.env.get("AIRANK_WORDPRESS_USERNAME") or "").strip()
        app_password = str(self.env.get("AIRANK_WORDPRESS_APP_PASSWORD") or "").strip()
        if not username or not app_password:
            raise PublisherError("PUBLISH_CREDENTIAL_MISSING", "WordPress application credential is missing")
        post_status = str(self.env.get("AIRANK_WORDPRESS_POST_STATUS") or "draft").strip().lower()
        if post_status not in {"draft", "pending", "private", "publish"}:
            raise PublisherError("PUBLISH_CONFIGURATION_INVALID", "WordPress post status is invalid")
        basic = base64.b64encode(f"{username}:{app_password}".encode("utf-8")).decode("ascii")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {basic}",
            "Idempotency-Key": snapshot.idempotency_key,
            "X-AIRank-Content-SHA256": snapshot.content_sha256,
        }
        slug_suffix = "".join(
            character if character.isalnum() else "-"
            for character in snapshot.package_id.lower()
        ).strip("-")
        slug = f"airank-{slug_suffix}"
        parsed = urlparse(snapshot.target_endpoint)
        lookup_url = urlunparse(parsed._replace(query=urlencode({"slug": slug, "context": "edit"})))
        lookup_status, _, existing = self.transport.request(
            "GET",
            lookup_url,
            headers=headers,
            payload=None,
            timeout_seconds=self.timeout_seconds,
        )
        if 200 <= lookup_status < 300 and isinstance(existing, list) and existing:
            receipt = self._receipt(snapshot, lookup_status, existing[0], idempotent_replay=True)
            return receipt
        payload = {
            "title": snapshot.title,
            "content": snapshot.body_md,
            "status": post_status,
            "slug": slug,
            "meta": {
                "airank_package_id": snapshot.package_id,
                "airank_content_sha256": snapshot.content_sha256,
            },
        }
        status, _, response = self.transport.request(
            "POST",
            snapshot.target_endpoint,
            headers=headers,
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        return self._receipt(snapshot, status, response)

    def _receipt(
        self,
        snapshot: PublishSnapshot,
        status: int,
        response: Any,
        *,
        idempotent_replay: bool = False,
    ) -> PublisherReceipt:
        if status < 200 or status >= 300:
            raise PublisherError(
                "PUBLISH_UPSTREAM_REJECTED",
                f"publisher returned HTTP {status}",
                retryable=status == 429 or status >= 500,
                status_code=status,
            )
        if not isinstance(response, Mapping):
            raise PublisherError("PUBLISH_RESPONSE_INVALID", "publisher response must be a JSON object")
        published_url = str(response.get("published_url") or response.get("url") or response.get("link") or "").strip()
        if not published_url:
            raise PublisherError("PUBLISH_RECEIPT_MISSING", "publisher response did not include a published URL")
        self._validate_endpoint(published_url)
        response_sha256 = sha256_text(
            json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        )
        return PublisherReceipt(
            status_code=status,
            published_url=published_url,
            response_sha256=response_sha256,
            request_sha256=self.request_sha256(snapshot),
            remote_id=str(response.get("id")) if response.get("id") is not None else None,
            idempotent_replay=idempotent_replay,
        )

    def _validate_endpoint(self, value: str) -> None:
        try:
            self.outbound_policy.resolve(value)
        except OutboundSecurityError as exc:
            code = "PUBLISH_DNS_FAILED" if exc.code == "OUTBOUND_DNS_FAILED" else "PUBLISH_ENDPOINT_FORBIDDEN"
            raise PublisherError(code, exc.message, retryable=exc.retryable) from exc

    @staticmethod
    def _public_payload(snapshot: PublishSnapshot) -> dict[str, Any]:
        return {
            "contract_version": "airank.publisher.v1",
            "package_id": snapshot.package_id,
            "snapshot_id": snapshot.snapshot_id,
            "idempotency_key": snapshot.idempotency_key,
            "title": snapshot.title,
            "body_md": snapshot.body_md,
            "content_sha256": snapshot.content_sha256,
            "manifest": dict(snapshot.manifest),
        }


class MySQLPublishExecutionRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        try:
            self.stale_attempt_seconds = max(
                30,
                int(os.getenv("AIRANK_PUBLISH_ATTEMPT_STALE_SECONDS") or 600),
            )
        except ValueError:
            self.stale_attempt_seconds = 600

    def load_snapshot(self, tenant_id: str, package_id: str) -> PublishSnapshot:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT p.tenant_id, p.project_id, p.id AS package_id,
                           p.snapshot_id, p.channel, p.idempotency_key,
                           p.status AS package_status, p.published_url,
                           p.metadata_json AS package_metadata_json,
                           s.title, s.body_md, s.content_sha256, s.manifest_json
                    FROM airank_publish_packages p
                    JOIN airank_publish_snapshots s
                      ON s.id = p.snapshot_id AND s.tenant_id = p.tenant_id
                    WHERE p.tenant_id = :tenant_id
                      AND p.id = :package_id
                      AND p.deleted_at IS NULL
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package_id},
            ).mappings().first()
        if row is None:
            raise PublisherError("PUBLISH_PACKAGE_NOT_FOUND", "publish package was not found")
        metadata = self._json_object(row["package_metadata_json"])
        manifest = self._json_object(row["manifest_json"])
        endpoint = str(metadata.get("target_endpoint") or "")
        if not endpoint:
            raise PublisherError("PUBLISH_ENDPOINT_MISSING", "publish package has no target endpoint")
        return PublishSnapshot(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            package_id=str(row["package_id"]),
            snapshot_id=str(row["snapshot_id"]),
            channel=str(row["channel"]),
            idempotency_key=str(row["idempotency_key"]),
            target_endpoint=endpoint,
            title=str(row["title"]),
            body_md=str(row["body_md"] or ""),
            content_sha256=str(row["content_sha256"]),
            manifest=manifest,
            package_status=str(row["package_status"]),
            published_url=str(row["published_url"]) if row["published_url"] else None,
            package_metadata=metadata,
        )

    def begin_attempt(self, snapshot: PublishSnapshot, request_sha256: str, started_at: datetime) -> tuple[str, int]:
        started_at_db = started_at.astimezone(timezone.utc).replace(tzinfo=None) if started_at.tzinfo else started_at
        with self.engine.begin() as conn:
            package = conn.execute(
                text(
                    """
                    SELECT status FROM airank_publish_packages
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    FOR UPDATE
                    """
                ),
                {"tenant_id": snapshot.tenant_id, "package_id": snapshot.package_id},
            ).mappings().one()
            if package["status"] in {"delivered", "published"}:
                raise PublisherError("PUBLISH_ALREADY_DELIVERED", "publish package already has a delivery receipt")
            if package["status"] == "publishing":
                running_attempt = conn.execute(
                    text(
                        """
                        SELECT id, started_at FROM airank_publish_attempts
                        WHERE tenant_id = :tenant_id AND package_id = :package_id
                          AND status = 'running'
                        ORDER BY attempt_number DESC LIMIT 1 FOR UPDATE
                        """
                    ),
                    {"tenant_id": snapshot.tenant_id, "package_id": snapshot.package_id},
                ).mappings().first()
                if running_attempt is not None and (
                    started_at_db - running_attempt["started_at"]
                ).total_seconds() < self.stale_attempt_seconds:
                    raise PublisherError(
                        "PUBLISH_ALREADY_IN_PROGRESS",
                        "publish package already has an active attempt",
                        retryable=True,
                    )
                if running_attempt is not None:
                    conn.execute(
                        text(
                            """
                            UPDATE airank_publish_attempts
                            SET status = 'failed', error_code = 'PUBLISH_ATTEMPT_ABANDONED',
                                error_message = 'previous worker stopped before recording a receipt',
                                finished_at = :finished_at
                            WHERE tenant_id = :tenant_id AND id = :attempt_id AND status = 'running'
                            """
                        ),
                        {
                            "finished_at": started_at_db,
                            "tenant_id": snapshot.tenant_id,
                            "attempt_id": running_attempt["id"],
                        },
                    )
            attempt_number = int(
                conn.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(attempt_number), 0)
                        FROM airank_publish_attempts
                        WHERE tenant_id = :tenant_id AND package_id = :package_id
                        """
                    ),
                    {"tenant_id": snapshot.tenant_id, "package_id": snapshot.package_id},
                ).scalar_one()
            ) + 1
            attempt_id = f"publish_attempt_{uuid4().hex[:12]}"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_publish_attempts (
                      id, tenant_id, project_id, package_id, attempt_number,
                      channel, status, request_sha256, started_at, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :package_id, :attempt_number,
                      :channel, 'running', :request_sha256, :started_at, :started_at
                    )
                    """
                ),
                {
                    "id": attempt_id,
                    "tenant_id": snapshot.tenant_id,
                    "project_id": snapshot.project_id,
                    "package_id": snapshot.package_id,
                    "attempt_number": attempt_number,
                    "channel": snapshot.channel,
                    "request_sha256": request_sha256,
                    "started_at": started_at_db,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_publish_packages
                    SET status = 'publishing', updated_at = :started_at
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {"started_at": started_at_db, "tenant_id": snapshot.tenant_id, "package_id": snapshot.package_id},
            )
        return attempt_id, attempt_number

    def complete_attempt(
        self,
        snapshot: PublishSnapshot,
        attempt_id: str,
        attempt_number: int,
        receipt: PublisherReceipt,
        finished_at: datetime,
    ) -> None:
        metadata = dict(snapshot.package_metadata)
        metadata["implementation_status"] = "ready"
        metadata["delivery_receipt"] = {
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "request_sha256": receipt.request_sha256,
            "response_sha256": receipt.response_sha256,
            "response_status": receipt.status_code,
            "remote_id": receipt.remote_id,
            "idempotent_replay": receipt.idempotent_replay,
            "delivered_at": finished_at.isoformat(),
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_publish_attempts
                    SET status = 'succeeded', response_status = :response_status,
                        response_sha256 = :response_sha256, finished_at = :finished_at
                    WHERE tenant_id = :tenant_id AND id = :attempt_id AND status = 'running'
                    """
                ),
                {
                    "response_status": receipt.status_code,
                    "response_sha256": receipt.response_sha256,
                    "finished_at": finished_at,
                    "tenant_id": snapshot.tenant_id,
                    "attempt_id": attempt_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_publish_packages
                    SET status = 'delivered', published_url = :published_url,
                        metadata_json = :metadata_json, updated_at = :finished_at
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {
                    "published_url": receipt.published_url,
                    "metadata_json": json.dumps(metadata, ensure_ascii=False),
                    "finished_at": finished_at,
                    "tenant_id": snapshot.tenant_id,
                    "package_id": snapshot.package_id,
                },
            )

    def fail_attempt(
        self,
        snapshot: PublishSnapshot,
        attempt_id: str,
        error: PublisherError,
        finished_at: datetime,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_publish_attempts
                    SET status = 'failed', response_status = :response_status,
                        error_code = :error_code, error_message = :error_message,
                        finished_at = :finished_at
                    WHERE tenant_id = :tenant_id AND id = :attempt_id AND status = 'running'
                    """
                ),
                {
                    "response_status": error.status_code,
                    "error_code": error.code,
                    "error_message": error.message[:1000],
                    "finished_at": finished_at,
                    "tenant_id": snapshot.tenant_id,
                    "attempt_id": attempt_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_publish_packages
                    SET status = 'failed', updated_at = :finished_at
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {"finished_at": finished_at, "tenant_id": snapshot.tenant_id, "package_id": snapshot.package_id},
            )

    @staticmethod
    def _json_object(value: object) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            parsed = json.loads(value or "{}")
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}


def run_next_publish_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: MySQLPublishExecutionRepository,
    gateway: PublisherGateway,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> PublisherReceipt | None:
    started_at = now or utc_now()
    job = store.claim_next(worker_id, started_at, job_types={"publish.package"})
    if job is None:
        return None
    return run_claimed_publish_job(
        store,
        repository,
        gateway,
        job=job,
        worker_id=worker_id,
        started_at=started_at,
    )


def run_claimed_publish_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: MySQLPublishExecutionRepository,
    gateway: PublisherGateway,
    *,
    job: AsyncJob,
    worker_id: str,
    started_at: datetime,
) -> PublisherReceipt:
    payload = job.payload if isinstance(job.payload, Mapping) else {}
    package_id = str(payload.get("package_id") or "")
    if not package_id:
        error = PublisherError("PUBLISH_JOB_INVALID", "publish job has no package_id")
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    try:
        snapshot = repository.load_snapshot(job.tenant_id, package_id)
    except PublisherError as exc:
        store.fail(job.id, worker_id, utc_now(), exc.code, exc.message)
        raise
    if snapshot.project_id != (job.project_id or ""):
        error = PublisherError("PUBLISH_JOB_SCOPE_MISMATCH", "publish job project does not match package")
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    if snapshot.package_status in {"delivered", "published"} and snapshot.published_url:
        receipt_data = snapshot.package_metadata.get("delivery_receipt")
        receipt_map = receipt_data if isinstance(receipt_data, Mapping) else {}
        receipt = PublisherReceipt(
            status_code=int(receipt_map.get("response_status") or 200),
            published_url=snapshot.published_url,
            response_sha256=str(receipt_map.get("response_sha256") or ""),
            request_sha256=str(receipt_map.get("request_sha256") or gateway.request_sha256(snapshot)),
            remote_id=str(receipt_map.get("remote_id")) if receipt_map.get("remote_id") else None,
            idempotent_replay=True,
        )
        store.succeed(job.id, worker_id, utc_now(), _receipt_result(receipt))
        return receipt

    request_sha256 = gateway.request_sha256(snapshot)
    try:
        attempt_id, attempt_number = repository.begin_attempt(snapshot, request_sha256, started_at)
    except PublisherError as exc:
        store.fail(job.id, worker_id, utc_now(), exc.code, exc.message)
        raise
    try:
        receipt = gateway.publish(snapshot)
    except PublisherError as exc:
        finished_at = utc_now()
        repository.fail_attempt(snapshot, attempt_id, exc, finished_at)
        store.fail(job.id, worker_id, finished_at, exc.code, exc.message)
        raise
    except Exception as exc:
        error = PublisherError(
            "PUBLISH_INTERNAL_ERROR",
            f"publisher execution failed: {type(exc).__name__}",
        )
        finished_at = utc_now()
        repository.fail_attempt(snapshot, attempt_id, error, finished_at)
        store.fail(job.id, worker_id, finished_at, error.code, error.message)
        raise error from exc
    finished_at = utc_now()
    repository.complete_attempt(snapshot, attempt_id, attempt_number, receipt, finished_at)
    store.succeed(job.id, worker_id, finished_at, _receipt_result(receipt))
    return receipt


def _receipt_result(receipt: PublisherReceipt) -> dict[str, object]:
    return {
        "status": "delivered",
        "published_url": receipt.published_url,
        "request_sha256": receipt.request_sha256,
        "response_sha256": receipt.response_sha256,
        "response_status": receipt.status_code,
        "remote_id": receipt.remote_id,
        "idempotent_replay": receipt.idempotent_replay,
    }

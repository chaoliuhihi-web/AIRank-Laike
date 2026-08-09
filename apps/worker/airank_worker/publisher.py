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

from apps.api.operation_guard import (
    MySQLOperationGuard,
    OperationAuditRecord,
    OperationGuard,
    OperationGuardError,
)
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


@dataclass(frozen=True)
class PendingPublishAttempt:
    attempt_id: str
    attempt_number: int
    operation_id: str | None
    status: str
    started_at: datetime


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

    def publish(
        self,
        snapshot: PublishSnapshot,
        *,
        before_external_effect: Callable[[], None] | None = None,
    ) -> PublisherReceipt:
        self._validate_endpoint(snapshot.target_endpoint)
        if sha256_text(snapshot.body_md) != snapshot.content_sha256:
            raise PublisherError(
                "PUBLISH_SNAPSHOT_HASH_MISMATCH",
                "immutable publish snapshot content hash does not match",
            )
        if snapshot.channel == "http":
            return self._publish_http(snapshot, before_external_effect=before_external_effect)
        if snapshot.channel == "wordpress":
            return self._publish_wordpress(snapshot, before_external_effect=before_external_effect)
        raise PublisherError("PUBLISH_CHANNEL_UNSUPPORTED", "publisher channel is not supported")

    def _publish_http(
        self,
        snapshot: PublishSnapshot,
        *,
        before_external_effect: Callable[[], None] | None,
    ) -> PublisherReceipt:
        token = str(self.env.get("AIRANK_PUBLISH_HTTP_BEARER_TOKEN") or "").strip()
        if not token:
            raise PublisherError("PUBLISH_CREDENTIAL_MISSING", "generic HTTP publisher credential is missing")
        payload = self._public_payload(snapshot)
        if before_external_effect is not None:
            before_external_effect()
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

    def _wordpress_request_context(
        self,
        snapshot: PublishSnapshot,
    ) -> tuple[dict[str, str], str, str, str]:
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
        return headers, slug, lookup_url, post_status

    def find_existing(self, snapshot: PublishSnapshot) -> PublisherReceipt | None:
        """Read-only reconciliation supported only by WordPress deterministic slugs."""

        self._validate_endpoint(snapshot.target_endpoint)
        if sha256_text(snapshot.body_md) != snapshot.content_sha256:
            raise PublisherError(
                "PUBLISH_SNAPSHOT_HASH_MISMATCH",
                "immutable publish snapshot content hash does not match",
            )
        if snapshot.channel != "wordpress":
            return None
        headers, _, lookup_url, _ = self._wordpress_request_context(snapshot)
        lookup_status, _, existing = self.transport.request(
            "GET",
            lookup_url,
            headers=headers,
            payload=None,
            timeout_seconds=self.timeout_seconds,
        )
        if 200 <= lookup_status < 300 and isinstance(existing, list) and existing:
            return self._receipt(snapshot, lookup_status, existing[0], idempotent_replay=True)
        if 200 <= lookup_status < 300 and isinstance(existing, list):
            return None
        raise PublisherError(
            "PUBLISH_RECONCILIATION_LOOKUP_FAILED",
            f"WordPress reconciliation lookup returned HTTP {lookup_status}",
            retryable=lookup_status == 429 or lookup_status >= 500,
            status_code=lookup_status,
        )

    def _publish_wordpress(
        self,
        snapshot: PublishSnapshot,
        *,
        before_external_effect: Callable[[], None] | None,
    ) -> PublisherReceipt:
        headers, slug, _, post_status = self._wordpress_request_context(snapshot)
        existing_receipt = self.find_existing(snapshot)
        if existing_receipt is not None:
            return existing_receipt
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
        if before_external_effect is not None:
            before_external_effect()
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
    def __init__(
        self,
        database_url: str,
        *,
        operation_guard: OperationGuard | None = None,
    ) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.operation_guard = operation_guard or MySQLOperationGuard(database_url)
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

    def latest_pending_attempt(self, snapshot: PublishSnapshot) -> PendingPublishAttempt | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, attempt_number, operation_id, status, started_at
                    FROM airank_publish_attempts
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                      AND status IN ('running', 'outcome_unknown')
                    ORDER BY attempt_number DESC LIMIT 1
                    """
                ),
                {"tenant_id": snapshot.tenant_id, "package_id": snapshot.package_id},
            ).mappings().first()
        if row is None:
            return None
        started_at = row["started_at"]
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return PendingPublishAttempt(
            attempt_id=str(row["id"]),
            attempt_number=int(row["attempt_number"]),
            operation_id=str(row["operation_id"]) if row["operation_id"] else None,
            status=str(row["status"]),
            started_at=started_at,
        )

    def latest_operation_id(self, snapshot: PublishSnapshot) -> str | None:
        with self.engine.connect() as conn:
            value = conn.execute(
                text(
                    """
                    SELECT operation_id FROM airank_publish_attempts
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                      AND operation_id IS NOT NULL
                    ORDER BY attempt_number DESC LIMIT 1
                    """
                ),
                {"tenant_id": snapshot.tenant_id, "package_id": snapshot.package_id},
            ).scalar()
        return str(value) if value else None

    def begin_attempt(
        self,
        snapshot: PublishSnapshot,
        request_sha256: str,
        operation_id: str,
        started_at: datetime,
    ) -> tuple[str, int]:
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
            if package["status"] == "outcome_unknown":
                raise PublisherError(
                    "OPERATION_OUTCOME_UNKNOWN",
                    "publish package requires reconciliation before another external request",
                )
            if package["status"] == "publishing":
                raise PublisherError(
                    "PUBLISH_ALREADY_IN_PROGRESS",
                    "publish package already has an active or unreconciled attempt",
                    retryable=False,
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
                      channel, status, request_sha256, operation_id, started_at, created_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :package_id, :attempt_number,
                      :channel, 'running', :request_sha256, :operation_id, :started_at, :started_at
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
                    "operation_id": operation_id,
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
        operation_id: str,
        receipt: PublisherReceipt,
        finished_at: datetime,
    ) -> None:
        metadata = dict(snapshot.package_metadata)
        metadata["implementation_status"] = "ready"
        metadata.pop("reconciliation_required", None)
        metadata.pop("reconciliation_reason", None)
        metadata["delivery_receipt"] = {
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "operation_id": operation_id,
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
                    WHERE tenant_id = :tenant_id AND id = :attempt_id
                      AND status IN ('running', 'outcome_unknown')
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

    def mark_outcome_unknown(
        self,
        snapshot: PublishSnapshot,
        attempt_id: str,
        error: PublisherError,
        finished_at: datetime,
    ) -> None:
        metadata = dict(snapshot.package_metadata)
        metadata["implementation_status"] = "partial"
        metadata["reconciliation_required"] = True
        metadata["reconciliation_reason"] = "external_effect_outcome_unknown"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_publish_attempts
                    SET status = 'outcome_unknown', response_status = :response_status,
                        error_code = :error_code, error_message = :error_message,
                        finished_at = :finished_at
                    WHERE tenant_id = :tenant_id AND id = :attempt_id
                      AND status IN ('running', 'outcome_unknown')
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
                    SET status = 'outcome_unknown', metadata_json = :metadata_json,
                        updated_at = :finished_at
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {
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
    operation_guard = repository.operation_guard
    request_sha256 = gateway.request_sha256(snapshot)
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
        operation_id = str(receipt_map.get("operation_id") or repository.latest_operation_id(snapshot) or "")
        if operation_id:
            try:
                audit = _validated_publish_operation(
                    operation_guard,
                    snapshot,
                    operation_id,
                    request_sha256,
                )
                if audit.state in {"claimed", "external_started"}:
                    operation_guard.succeed(
                        operation_id,
                        _receipt_result(receipt),
                        worker_id,
                        job.id,
                    )
                elif audit.state != "succeeded":
                    raise PublisherError(
                        "PUBLISH_OPERATION_STATE_CONFLICT",
                        "delivered package is linked to a non-successful operation",
                    )
            except (OperationGuardError, PublisherError) as exc:
                error = _publisher_operation_error(exc)
                store.fail(job.id, worker_id, utc_now(), error.code, error.message)
                raise error from exc
        store.succeed(job.id, worker_id, utc_now(), _receipt_result(receipt))
        return receipt

    pending = repository.latest_pending_attempt(snapshot)
    if pending is not None and pending.operation_id is None:
        age_seconds = (started_at.astimezone(timezone.utc) - pending.started_at).total_seconds()
        error = PublisherError(
            "OPERATION_OUTCOME_UNKNOWN" if pending.status == "outcome_unknown" or age_seconds >= repository.stale_attempt_seconds else "PUBLISH_ALREADY_IN_PROGRESS",
            "legacy publish attempt has no Operation Guard evidence; automatic replay is forbidden"
            if pending.status == "outcome_unknown" or age_seconds >= repository.stale_attempt_seconds
            else "publish package already has an active attempt",
        )
        if error.code == "OPERATION_OUTCOME_UNKNOWN" and pending.status == "running":
            repository.mark_outcome_unknown(snapshot, pending.attempt_id, error, utc_now())
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error

    try:
        claim = operation_guard.claim(
            tenant_id=snapshot.tenant_id,
            operation_type="publisher.publish",
            resource_key=snapshot.package_id,
            idempotency_key=snapshot.idempotency_key,
            request_sha256=request_sha256,
            request_key_id=None,
            actor=worker_id,
            trace_id=job.id,
        )
    except OperationGuardError as exc:
        return _handle_publish_claim_conflict(
            store,
            repository,
            gateway,
            operation_guard,
            snapshot,
            job,
            worker_id,
            started_at,
            request_sha256,
            exc,
        )

    if claim.idempotent_replay:
        pending = repository.latest_pending_attempt(snapshot)
        if pending is None or pending.operation_id != claim.operation_id:
            error = PublisherError(
                "PUBLISH_OPERATION_RECEIPT_ORPHANED",
                "successful publish operation has no matching attempt ledger entry",
            )
            store.fail(job.id, worker_id, utc_now(), error.code, error.message)
            raise error
        receipt = _receipt_from_operation_response(
            claim.response,
            request_sha256=request_sha256,
            idempotent_replay=True,
        )
        try:
            repository.complete_attempt(
                snapshot,
                pending.attempt_id,
                pending.attempt_number,
                claim.operation_id,
                receipt,
                utc_now(),
            )
        except Exception as exc:
            error = PublisherError(
                "PUBLISH_RECEIPT_PERSIST_FAILED",
                f"successful publisher receipt could not be persisted: {type(exc).__name__}",
            )
            store.fail(job.id, worker_id, utc_now(), error.code, error.message)
            raise error from exc
        store.succeed(job.id, worker_id, utc_now(), _receipt_result(receipt))
        return receipt

    try:
        attempt_id, attempt_number = repository.begin_attempt(
            snapshot,
            request_sha256,
            claim.operation_id,
            started_at,
        )
    except PublisherError as exc:
        try:
            operation_guard.fail(claim.operation_id, exc.code, worker_id, job.id)
        except OperationGuardError:
            pass
        store.fail(job.id, worker_id, utc_now(), exc.code, exc.message)
        raise

    external_started = False

    def mark_external_started() -> None:
        nonlocal external_started
        try:
            operation_guard.mark_external_started(claim.operation_id, worker_id, job.id)
        except OperationGuardError as exc:
            raise _publisher_operation_error(exc) from exc
        external_started = True

    try:
        receipt = gateway.publish(snapshot, before_external_effect=mark_external_started)
    except PublisherError as exc:
        finished_at = utc_now()
        if external_started:
            repository.mark_outcome_unknown(snapshot, attempt_id, exc, finished_at)
            unknown = PublisherError(
                "OPERATION_OUTCOME_UNKNOWN",
                "publisher may have accepted the request; automatic replay is forbidden until reconciled",
            )
            store.fail(job.id, worker_id, finished_at, unknown.code, unknown.message)
            raise unknown from exc
        repository.fail_attempt(snapshot, attempt_id, exc, finished_at)
        try:
            operation_guard.fail(claim.operation_id, exc.code, worker_id, job.id)
        except OperationGuardError:
            pass
        store.fail(job.id, worker_id, finished_at, exc.code, exc.message)
        raise
    except Exception as exc:
        error = PublisherError(
            "PUBLISH_INTERNAL_ERROR",
            f"publisher execution failed: {type(exc).__name__}",
        )
        finished_at = utc_now()
        if external_started:
            repository.mark_outcome_unknown(snapshot, attempt_id, error, finished_at)
            unknown = PublisherError(
                "OPERATION_OUTCOME_UNKNOWN",
                "publisher may have accepted the request; automatic replay is forbidden until reconciled",
            )
            store.fail(job.id, worker_id, finished_at, unknown.code, unknown.message)
            raise unknown from exc
        repository.fail_attempt(snapshot, attempt_id, error, finished_at)
        try:
            operation_guard.fail(claim.operation_id, error.code, worker_id, job.id)
        except OperationGuardError:
            pass
        store.fail(job.id, worker_id, finished_at, error.code, error.message)
        raise error from exc
    finished_at = utc_now()
    try:
        operation_guard.succeed(
            claim.operation_id,
            _receipt_result(receipt),
            worker_id,
            job.id,
        )
    except Exception as exc:
        try:
            repository.complete_attempt(
                snapshot,
                attempt_id,
                attempt_number,
                claim.operation_id,
                receipt,
                finished_at,
            )
        except Exception:
            repository.mark_outcome_unknown(
                snapshot,
                attempt_id,
                PublisherError(
                    "PUBLISH_OPERATION_AUDIT_INCOMPLETE",
                    "publisher receipt and Operation Guard could not be finalized",
                ),
                finished_at,
            )
        error = PublisherError(
            "PUBLISH_OPERATION_AUDIT_INCOMPLETE",
            "publisher receipt was received but Operation Guard finalization failed",
        )
        store.fail(job.id, worker_id, finished_at, error.code, error.message)
        raise error from exc
    try:
        repository.complete_attempt(
            snapshot,
            attempt_id,
            attempt_number,
            claim.operation_id,
            receipt,
            finished_at,
        )
    except Exception as exc:
        error = PublisherError(
            "PUBLISH_RECEIPT_PERSIST_FAILED",
            f"successful publisher receipt could not be persisted: {type(exc).__name__}",
        )
        store.fail(job.id, worker_id, finished_at, error.code, error.message)
        raise error from exc
    store.succeed(job.id, worker_id, finished_at, _receipt_result(receipt))
    return receipt


def _handle_publish_claim_conflict(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: MySQLPublishExecutionRepository,
    gateway: PublisherGateway,
    operation_guard: OperationGuard,
    snapshot: PublishSnapshot,
    job: AsyncJob,
    worker_id: str,
    started_at: datetime,
    request_sha256: str,
    guard_error: OperationGuardError,
) -> PublisherReceipt:
    pending = repository.latest_pending_attempt(snapshot)
    if guard_error.code == "OPERATION_OUTCOME_UNKNOWN" and pending is not None and pending.operation_id:
        if pending.status == "running":
            repository.mark_outcome_unknown(
                snapshot,
                pending.attempt_id,
                PublisherError(
                    "PUBLISH_ATTEMPT_INTERRUPTED",
                    "worker stopped after the external effect may have started",
                ),
                utc_now(),
            )
        if snapshot.channel == "wordpress":
            try:
                receipt = gateway.find_existing(snapshot)
            except PublisherError:
                receipt = None
            if receipt is not None:
                try:
                    operation_guard.succeed(
                        pending.operation_id,
                        _receipt_result(receipt),
                        worker_id,
                        job.id,
                    )
                    repository.complete_attempt(
                        snapshot,
                        pending.attempt_id,
                        pending.attempt_number,
                        pending.operation_id,
                        receipt,
                        utc_now(),
                    )
                except Exception as exc:
                    error = PublisherError(
                        "PUBLISH_RECONCILIATION_PERSIST_FAILED",
                        f"verified WordPress receipt could not be finalized: {type(exc).__name__}",
                    )
                    store.fail(job.id, worker_id, utc_now(), error.code, error.message)
                    raise error from exc
                store.succeed(job.id, worker_id, utc_now(), _receipt_result(receipt))
                return receipt
    elif guard_error.code == "OPERATION_IN_PROGRESS" and pending is not None:
        age_seconds = (started_at.astimezone(timezone.utc) - pending.started_at).total_seconds()
        if age_seconds >= repository.stale_attempt_seconds and pending.operation_id:
            audit = operation_guard.get_audit(snapshot.tenant_id, pending.operation_id)
            if audit is not None and not audit.external_effect_started and audit.state == "claimed":
                abandoned = PublisherError(
                    "PUBLISH_ATTEMPT_ABANDONED_BEFORE_EXTERNAL",
                    "stale worker stopped before any recorded external effect; create a new package operation",
                )
                repository.fail_attempt(snapshot, pending.attempt_id, abandoned, utc_now())
                operation_guard.fail(pending.operation_id, abandoned.code, worker_id, job.id)
                store.fail(job.id, worker_id, utc_now(), abandoned.code, abandoned.message)
                raise abandoned
            repository.mark_outcome_unknown(
                snapshot,
                pending.attempt_id,
                PublisherError(
                    "PUBLISH_ATTEMPT_INTERRUPTED",
                    "stale worker outcome cannot be proven",
                ),
                utc_now(),
            )
            guard_error = OperationGuardError(
                "OPERATION_OUTCOME_UNKNOWN",
                "stale publish attempt requires reconciliation",
            )
    error = _publisher_operation_error(guard_error)
    store.fail(job.id, worker_id, utc_now(), error.code, error.message)
    raise error from guard_error


def _validated_publish_operation(
    operation_guard: OperationGuard,
    snapshot: PublishSnapshot,
    operation_id: str,
    request_sha256: str,
) -> OperationAuditRecord:
    audit = operation_guard.get_audit(snapshot.tenant_id, operation_id)
    if audit is None:
        raise PublisherError("PUBLISH_OPERATION_NOT_FOUND", "publish operation audit was not found")
    if (
        audit.operation_type != "publisher.publish"
        or audit.resource_key != snapshot.package_id
        or audit.request_sha256 != request_sha256
    ):
        raise PublisherError(
            "PUBLISH_OPERATION_SCOPE_MISMATCH",
            "publish operation does not match the immutable package request",
        )
    return audit


def _publisher_operation_error(error: OperationGuardError | PublisherError) -> PublisherError:
    if isinstance(error, PublisherError):
        return error
    return PublisherError(error.code, error.message)


def _receipt_from_operation_response(
    response: Mapping[str, object] | None,
    *,
    request_sha256: str,
    idempotent_replay: bool,
) -> PublisherReceipt:
    data = response or {}
    response_request_sha256 = str(data.get("request_sha256") or "")
    response_sha256 = str(data.get("response_sha256") or "")
    published_url = str(data.get("published_url") or "")
    if (
        response_request_sha256 != request_sha256
        or len(response_sha256) != 64
        or not published_url
    ):
        raise PublisherError(
            "PUBLISH_OPERATION_RECEIPT_INVALID",
            "stored publish operation receipt failed integrity validation",
        )
    return PublisherReceipt(
        status_code=int(data.get("response_status") or 200),
        published_url=published_url,
        response_sha256=response_sha256,
        request_sha256=response_request_sha256,
        remote_id=str(data.get("remote_id")) if data.get("remote_id") else None,
        idempotent_replay=idempotent_replay,
    )


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

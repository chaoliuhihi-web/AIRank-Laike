from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Iterable, Mapping
from uuid import uuid4

from sqlalchemy import create_engine, text

from airank_provider_gateway import (
    ProbeResult,
    ProviderGatewayError,
    ProviderManifest,
    ProviderRequestContext,
    ProviderSettings,
    QuotaReservation,
)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MySQLProviderOperations:
    """Process-shared Provider health, circuit, and quota state.

    All credential material stays in process memory. The database stores only
    endpoint hosts, model names, public capability metadata, and a one-way
    configuration fingerprint.
    """

    def __init__(self, database_url: str, env: Mapping[str, str] | None = None) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.env = env if env is not None else os.environ
        self.failure_threshold = self._integer("AIRANK_PROVIDER_CIRCUIT_FAILURE_THRESHOLD", 3, minimum=1)
        self.cooldown_seconds = self._integer("AIRANK_PROVIDER_CIRCUIT_COOLDOWN_SECONDS", 30, minimum=1)
        self.reservation_ttl_seconds = self._integer("AIRANK_PROVIDER_QUOTA_RESERVATION_TTL_SECONDS", 300, minimum=10)

    def sync_manifests(self, manifests: Iterable[ProviderManifest]) -> None:
        now = utc_now_naive()
        with self.engine.begin() as conn:
            for manifest in manifests:
                settings = ProviderSettings.from_env(manifest, self.env)
                public_manifest = {
                    "provider": manifest.provider,
                    "label": manifest.label,
                    "implementation_status": manifest.implementation_status.value,
                    "collection_mode": manifest.collection_mode,
                    "endpoint_host": settings.endpoint_host,
                    "model": settings.model,
                    "capabilities": {
                        "web_search": manifest.capabilities.web_search,
                        "citations": manifest.capabilities.citations,
                        "streaming": manifest.capabilities.streaming,
                    },
                    "lifecycle": {
                        model: {
                            "sunset_at": lifecycle.sunset_at.isoformat(),
                            "replacement": lifecycle.replacement,
                            "source": lifecycle.source,
                        }
                        for model, lifecycle in manifest.lifecycle.items()
                    },
                }
                manifest_json = json.dumps(public_manifest, ensure_ascii=False, sort_keys=True)
                manifest_version = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()[:16]
                fingerprint = settings.configuration_fingerprint(manifest.provider)
                conn.execute(
                    text(
                        """
                        UPDATE airank_provider_manifests
                        SET is_current = 0
                        WHERE provider_key = :provider_key
                          AND manifest_version <> :manifest_version
                          AND is_current = 1
                        """
                    ),
                    {"provider_key": manifest.provider, "manifest_version": manifest_version},
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_provider_manifests (
                          provider_key, manifest_version, label, implementation_status,
                          collection_mode, endpoint_host, model_name, capabilities_json,
                          lifecycle_json, configuration_fingerprint, is_current, created_at
                        )
                        VALUES (
                          :provider_key, :manifest_version, :label, :implementation_status,
                          :collection_mode, :endpoint_host, :model_name, :capabilities_json,
                          :lifecycle_json, :configuration_fingerprint, 1, :created_at
                        )
                        ON DUPLICATE KEY UPDATE
                          label = VALUES(label),
                          implementation_status = VALUES(implementation_status),
                          collection_mode = VALUES(collection_mode),
                          endpoint_host = VALUES(endpoint_host),
                          model_name = VALUES(model_name),
                          capabilities_json = VALUES(capabilities_json),
                          lifecycle_json = VALUES(lifecycle_json),
                          configuration_fingerprint = VALUES(configuration_fingerprint),
                          is_current = 1
                        """
                    ),
                    {
                        "provider_key": manifest.provider,
                        "manifest_version": manifest_version,
                        "label": manifest.label,
                        "implementation_status": manifest.implementation_status.value,
                        "collection_mode": manifest.collection_mode,
                        "endpoint_host": settings.endpoint_host,
                        "model_name": settings.model,
                        "capabilities_json": json.dumps(public_manifest["capabilities"], sort_keys=True),
                        "lifecycle_json": json.dumps(public_manifest["lifecycle"], sort_keys=True),
                        "configuration_fingerprint": fingerprint,
                        "created_at": now,
                    },
                )

    def record_probe(self, result: ProbeResult) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_provider_probe_runs (
                      id, provider_key, probe_level, health_state, model_name,
                      endpoint_host, request_id_present, duration_ms, error_code,
                      message, checked_at, created_at
                    )
                    VALUES (
                      :id, :provider_key, :probe_level, :health_state, :model_name,
                      :endpoint_host, :request_id_present, :duration_ms, :error_code,
                      :message, :checked_at, :created_at
                    )
                    """
                ),
                {
                    "id": f"probe_{uuid4().hex}",
                    "provider_key": result.provider,
                    "probe_level": result.level.value,
                    "health_state": result.state.value,
                    "model_name": result.model,
                    "endpoint_host": result.endpoint_host,
                    "request_id_present": 1 if result.request_id_present else 0,
                    "duration_ms": result.duration_ms,
                    "error_code": result.error_code,
                    "message": (result.message or "")[:500] or None,
                    "checked_at": result.checked_at.astimezone(timezone.utc).replace(tzinfo=None),
                    "created_at": utc_now_naive(),
                },
            )

    def allow(self, provider: str, configuration_fingerprint: str = "") -> bool:
        now = utc_now_naive()
        fingerprint = self._fingerprint(configuration_fingerprint)
        with self.engine.begin() as conn:
            self._ensure_circuit_row(conn, provider, fingerprint, now)
            row = conn.execute(
                text(
                    """
                    SELECT state, opened_at, half_opened_at
                    FROM airank_provider_circuit_states
                    WHERE provider_key = :provider_key
                      AND configuration_fingerprint = :configuration_fingerprint
                    FOR UPDATE
                    """
                ),
                {"provider_key": provider, "configuration_fingerprint": fingerprint},
            ).mappings().one()
            state = str(row["state"])
            if state == "closed":
                return True
            reference_at = row["opened_at"] if state == "open" else row["half_opened_at"]
            if reference_at is None or now - reference_at < timedelta(seconds=self.cooldown_seconds):
                return False
            claimed = conn.execute(
                text(
                    """
                    UPDATE airank_provider_circuit_states
                    SET state = 'half_open', half_opened_at = :now, updated_at = :now
                    WHERE provider_key = :provider_key
                      AND configuration_fingerprint = :configuration_fingerprint
                      AND state = :expected_state
                    """
                ),
                {
                    "now": now,
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                    "expected_state": state,
                },
            )
            return claimed.rowcount == 1

    def success(self, provider: str, configuration_fingerprint: str = "") -> None:
        now = utc_now_naive()
        fingerprint = self._fingerprint(configuration_fingerprint)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_provider_circuit_states (
                      provider_key, configuration_fingerprint, state,
                      consecutive_failures, last_success_at, updated_at
                    )
                    VALUES (
                      :provider_key, :configuration_fingerprint, 'closed', 0, :now, :now
                    )
                    ON DUPLICATE KEY UPDATE
                      state = 'closed', consecutive_failures = 0,
                      opened_at = NULL, half_opened_at = NULL,
                      last_success_at = VALUES(last_success_at), updated_at = VALUES(updated_at)
                    """
                ),
                {"provider_key": provider, "configuration_fingerprint": fingerprint, "now": now},
            )

    def failure(
        self,
        provider: str,
        configuration_fingerprint: str = "",
        *,
        retryable: bool,
    ) -> None:
        if not retryable:
            return
        now = utc_now_naive()
        fingerprint = self._fingerprint(configuration_fingerprint)
        with self.engine.begin() as conn:
            self._ensure_circuit_row(conn, provider, fingerprint, now)
            row = conn.execute(
                text(
                    """
                    SELECT state, consecutive_failures
                    FROM airank_provider_circuit_states
                    WHERE provider_key = :provider_key
                      AND configuration_fingerprint = :configuration_fingerprint
                    FOR UPDATE
                    """
                ),
                {"provider_key": provider, "configuration_fingerprint": fingerprint},
            ).mappings().one()
            failures = int(row["consecutive_failures"]) + 1
            should_open = row["state"] == "half_open" or failures >= self.failure_threshold
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_circuit_states
                    SET state = :state,
                        consecutive_failures = :consecutive_failures,
                        opened_at = :opened_at,
                        half_opened_at = NULL,
                        last_failure_at = :now,
                        updated_at = :now
                    WHERE provider_key = :provider_key
                      AND configuration_fingerprint = :configuration_fingerprint
                    """
                ),
                {
                    "state": "open" if should_open else "closed",
                    "consecutive_failures": failures,
                    "opened_at": now if should_open else None,
                    "now": now,
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )

    def reserve(
        self,
        provider: str,
        units: int = 1,
        *,
        context: ProviderRequestContext | None = None,
    ) -> QuotaReservation:
        if units < 1:
            raise ValueError("quota units must be positive")
        request_context = context or ProviderRequestContext()
        now = utc_now_naive()
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=1)
        bucket_id = self._bucket_id(request_context.tenant_id, provider, period_start)
        limit_units = self._provider_quota_limit(provider)
        expires_at = now + timedelta(seconds=self.reservation_ttl_seconds)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_provider_quota_buckets (
                      id, tenant_id, provider_key, period_start, period_end,
                      limit_units, used_units, reserved_units, version_number, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :provider_key, :period_start, :period_end,
                      :limit_units, 0, 0, 0, :updated_at
                    )
                    ON DUPLICATE KEY UPDATE
                      limit_units = VALUES(limit_units), updated_at = VALUES(updated_at)
                    """
                ),
                {
                    "id": bucket_id,
                    "tenant_id": request_context.tenant_id,
                    "provider_key": provider,
                    "period_start": period_start,
                    "period_end": period_end,
                    "limit_units": limit_units,
                    "updated_at": now,
                },
            )
            bucket = conn.execute(
                text(
                    """
                    SELECT id, used_units, reserved_units, limit_units
                    FROM airank_provider_quota_buckets
                    WHERE tenant_id = :tenant_id
                      AND provider_key = :provider_key
                      AND period_start = :period_start
                      AND period_end = :period_end
                    FOR UPDATE
                    """
                ),
                {
                    "tenant_id": request_context.tenant_id,
                    "provider_key": provider,
                    "period_start": period_start,
                    "period_end": period_end,
                },
            ).mappings().one()
            expired_units = int(
                conn.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(units), 0)
                        FROM airank_provider_quota_reservations
                        WHERE bucket_id = :bucket_id AND status = 'pending' AND expires_at <= :now
                        FOR UPDATE
                        """
                    ),
                    {"bucket_id": bucket["id"], "now": now},
                ).scalar_one()
            )
            if expired_units:
                conn.execute(
                    text(
                        """
                        UPDATE airank_provider_quota_reservations
                        SET status = 'released', released_at = :now
                        WHERE bucket_id = :bucket_id AND status = 'pending' AND expires_at <= :now
                        """
                    ),
                    {"bucket_id": bucket["id"], "now": now},
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_provider_quota_buckets
                        SET reserved_units = GREATEST(0, reserved_units - :expired_units),
                            version_number = version_number + 1, updated_at = :now
                        WHERE id = :bucket_id
                        """
                    ),
                    {"expired_units": expired_units, "now": now, "bucket_id": bucket["id"]},
                )
                bucket = {**bucket, "reserved_units": max(0, int(bucket["reserved_units"]) - expired_units)}

            existing = conn.execute(
                text(
                    """
                    SELECT id, bucket_id, units, status
                    FROM airank_provider_quota_reservations
                    WHERE tenant_id = :tenant_id
                      AND provider_key = :provider_key
                      AND idempotency_key = :idempotency_key
                    FOR UPDATE
                    """
                ),
                {
                    "tenant_id": request_context.tenant_id,
                    "provider_key": provider,
                    "idempotency_key": request_context.idempotency_key,
                },
            ).mappings().first()
            if existing and existing["status"] == "pending":
                raise ProviderGatewayError(
                    provider,
                    "PROVIDER_REQUEST_IN_PROGRESS",
                    "provider request idempotency key already has an active reservation",
                    retryable=True,
                )
            if existing and existing["status"] == "committed":
                raise ProviderGatewayError(
                    provider,
                    "PROVIDER_REQUEST_ALREADY_COMMITTED",
                    "provider request idempotency key was already committed",
                )

            if int(bucket["used_units"]) + int(bucket["reserved_units"]) + units > int(bucket["limit_units"]):
                raise ProviderGatewayError(
                    provider,
                    "PROVIDER_QUOTA_EXHAUSTED",
                    "provider quota reservation failed",
                )
            reservation_id = str(existing["id"]) if existing else f"quota_{uuid4().hex}"
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_quota_buckets
                    SET reserved_units = reserved_units + :units,
                        version_number = version_number + 1, updated_at = :now
                    WHERE id = :bucket_id
                    """
                ),
                {"units": units, "now": now, "bucket_id": bucket["id"]},
            )
            if existing:
                conn.execute(
                    text(
                        """
                        UPDATE airank_provider_quota_reservations
                        SET bucket_id = :bucket_id, units = :units, status = 'pending',
                            expires_at = :expires_at, committed_at = NULL, released_at = NULL
                        WHERE id = :id
                        """
                    ),
                    {
                        "bucket_id": bucket["id"],
                        "units": units,
                        "expires_at": expires_at,
                        "id": reservation_id,
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_provider_quota_reservations (
                          id, tenant_id, provider_key, bucket_id, idempotency_key,
                          units, status, expires_at, created_at
                        )
                        VALUES (
                          :id, :tenant_id, :provider_key, :bucket_id, :idempotency_key,
                          :units, 'pending', :expires_at, :created_at
                        )
                        """
                    ),
                    {
                        "id": reservation_id,
                        "tenant_id": request_context.tenant_id,
                        "provider_key": provider,
                        "bucket_id": bucket["id"],
                        "idempotency_key": request_context.idempotency_key,
                        "units": units,
                        "expires_at": expires_at,
                        "created_at": now,
                    },
                )
        return QuotaReservation(
            provider=provider,
            units=units,
            reservation_id=reservation_id,
            tenant_id=request_context.tenant_id,
            bucket_id=str(bucket["id"]),
        )

    def commit(self, reservation: QuotaReservation) -> None:
        if reservation.committed:
            return
        now = utc_now_naive()
        with self.engine.begin() as conn:
            row = self._locked_reservation(conn, reservation)
            if row is None or row["status"] == "released":
                return
            if row["status"] == "committed":
                reservation.committed = True
                return
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_quota_buckets
                    SET reserved_units = GREATEST(0, reserved_units - :units),
                        used_units = used_units + :units,
                        version_number = version_number + 1, updated_at = :now
                    WHERE id = :bucket_id
                    """
                ),
                {"units": row["units"], "now": now, "bucket_id": row["bucket_id"]},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_quota_reservations
                    SET status = 'committed', committed_at = :now
                    WHERE id = :id AND status = 'pending'
                    """
                ),
                {"now": now, "id": row["id"]},
            )
        reservation.committed = True

    def release(self, reservation: QuotaReservation) -> None:
        if reservation.committed:
            return
        now = utc_now_naive()
        with self.engine.begin() as conn:
            row = self._locked_reservation(conn, reservation)
            if row is None or row["status"] != "pending":
                return
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_quota_buckets
                    SET reserved_units = GREATEST(0, reserved_units - :units),
                        version_number = version_number + 1, updated_at = :now
                    WHERE id = :bucket_id
                    """
                ),
                {"units": row["units"], "now": now, "bucket_id": row["bucket_id"]},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_quota_reservations
                    SET status = 'released', released_at = :now
                    WHERE id = :id AND status = 'pending'
                    """
                ),
                {"now": now, "id": row["id"]},
            )

    def _locked_reservation(self, conn, reservation: QuotaReservation):
        return conn.execute(
            text(
                """
                SELECT id, bucket_id, units, status
                FROM airank_provider_quota_reservations
                WHERE id = :id AND tenant_id = :tenant_id AND provider_key = :provider_key
                FOR UPDATE
                """
            ),
            {
                "id": reservation.reservation_id,
                "tenant_id": reservation.tenant_id,
                "provider_key": reservation.provider,
            },
        ).mappings().first()

    @staticmethod
    def _ensure_circuit_row(conn, provider: str, fingerprint: str, now: datetime) -> None:
        conn.execute(
            text(
                """
                INSERT INTO airank_provider_circuit_states (
                  provider_key, configuration_fingerprint, state,
                  consecutive_failures, updated_at
                )
                VALUES (:provider_key, :configuration_fingerprint, 'closed', 0, :now)
                ON DUPLICATE KEY UPDATE provider_key = VALUES(provider_key)
                """
            ),
            {"provider_key": provider, "configuration_fingerprint": fingerprint, "now": now},
        )

    def _provider_quota_limit(self, provider: str) -> int:
        provider_key = f"{provider.upper()}_QUOTA_UNITS"
        return self._integer(provider_key, self._integer("AIRANK_PROVIDER_DEFAULT_QUOTA_UNITS", 1_000_000, minimum=1), minimum=1)

    def _integer(self, name: str, default: int, *, minimum: int) -> int:
        try:
            return max(minimum, int(self.env.get(name) or default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _fingerprint(value: str) -> str:
        if len(value) == 64:
            return value
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _bucket_id(tenant_id: str, provider: str, period_start: datetime) -> str:
        digest = hashlib.sha256(
            f"{tenant_id}:{provider}:{period_start.isoformat()}".encode("utf-8")
        ).hexdigest()
        return f"quota_bucket_{digest[:48]}"

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Iterable, Mapping
from uuid import uuid4

from sqlalchemy import create_engine, text

from airank_provider_gateway import (
    NATIVE_CITATION_PARSER_VERSION,
    ProbeResult,
    ProviderCapacityLease,
    ProviderGatewayError,
    ProviderManifest,
    ProviderRequestContext,
    QuotaReservation,
    ResolvedProviderRoute,
    get_manifest,
    resolve_provider_routes,
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
        self.capacity_lease_ttl_seconds = self._integer(
            "AIRANK_PROVIDER_CAPACITY_LEASE_TTL_SECONDS", 300, minimum=10
        )

    def sync_manifests(self, manifests: Iterable[ProviderManifest]) -> None:
        now = utc_now_naive()
        with self.engine.begin() as conn:
            for manifest in manifests:
                routes = resolve_provider_routes(manifest, self.env)
                settings = routes[0].settings
                max_tokens_field = (
                    "max_output_tokens"
                    if settings.request_kind == "responses_web_search"
                    else manifest.max_tokens_field
                )
                fingerprint = settings.configuration_fingerprint(
                    manifest.provider, routes[0].route_id
                )
                public_manifest = {
                    "provider": manifest.provider,
                    "label": manifest.label,
                    "implementation_status": manifest.implementation_status.value,
                    "collection_mode": manifest.collection_mode,
                    "endpoint_host": settings.endpoint_host,
                    "model": settings.model,
                    "request_defaults": {
                        "request_kind": settings.request_kind,
                        "citation_parser_version": NATIVE_CITATION_PARSER_VERSION,
                        "max_tokens": settings.max_tokens,
                        "max_tokens_field": max_tokens_field,
                        "temperature": settings.temperature,
                        "reasoning_effort": settings.reasoning_effort,
                    },
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
                manifest_json = json.dumps(
                    {
                        **public_manifest,
                        "configuration_fingerprint": fingerprint,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                manifest_version = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()[:16]
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
                          lifecycle_json, request_defaults_json, configuration_fingerprint,
                          is_current, created_at
                        )
                        VALUES (
                          :provider_key, :manifest_version, :label, :implementation_status,
                          :collection_mode, :endpoint_host, :model_name, :capabilities_json,
                          :lifecycle_json, :request_defaults_json, :configuration_fingerprint,
                          1, :created_at
                        )
                        ON DUPLICATE KEY UPDATE
                          label = VALUES(label),
                          implementation_status = VALUES(implementation_status),
                          collection_mode = VALUES(collection_mode),
                          endpoint_host = VALUES(endpoint_host),
                          model_name = VALUES(model_name),
                          capabilities_json = VALUES(capabilities_json),
                          lifecycle_json = VALUES(lifecycle_json),
                          request_defaults_json = VALUES(request_defaults_json),
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
                        "request_defaults_json": json.dumps(
                            public_manifest["request_defaults"], sort_keys=True
                        ),
                        "configuration_fingerprint": fingerprint,
                        "created_at": now,
                    },
                )
                for route in routes:
                    route_max_tokens_field = (
                        "max_output_tokens"
                        if route.settings.request_kind == "responses_web_search"
                        else manifest.max_tokens_field
                    )
                    route_fingerprint = route.settings.configuration_fingerprint(
                        manifest.provider, route.route_id
                    )
                    route_public = {
                        "provider": manifest.provider,
                        "route_id": route.route_id,
                        "priority": route.priority,
                        "endpoint_host": route.settings.endpoint_host,
                        "model": route.settings.model,
                        "request_contract": {
                            "request_kind": route.settings.request_kind,
                            "citation_parser_version": NATIVE_CITATION_PARSER_VERSION,
                            "max_tokens": route.settings.max_tokens,
                            "max_tokens_field": route_max_tokens_field,
                            "temperature": route.settings.temperature,
                            "reasoning_effort": route.settings.reasoning_effort,
                        },
                        "configuration_fingerprint": route_fingerprint,
                    }
                    route_json = json.dumps(
                        route_public, ensure_ascii=False, sort_keys=True
                    )
                    route_version = hashlib.sha256(
                        route_json.encode("utf-8")
                    ).hexdigest()[:16]
                    conn.execute(
                        text(
                            """
                            UPDATE airank_provider_routes SET is_current=0
                            WHERE provider_key=:provider_key AND route_id=:route_id
                              AND route_version<>:route_version AND is_current=1
                            """
                        ),
                        {
                            "provider_key": manifest.provider,
                            "route_id": route.route_id,
                            "route_version": route_version,
                        },
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_provider_routes (
                              provider_key, route_id, route_version, priority,
                              endpoint_host, model_name, request_contract_json,
                              configuration_fingerprint, is_current, created_at
                            ) VALUES (
                              :provider_key, :route_id, :route_version, :priority,
                              :endpoint_host, :model_name, :request_contract_json,
                              :configuration_fingerprint, 1, :created_at
                            ) ON DUPLICATE KEY UPDATE
                              priority=VALUES(priority),
                              endpoint_host=VALUES(endpoint_host),
                              model_name=VALUES(model_name),
                              request_contract_json=VALUES(request_contract_json),
                              configuration_fingerprint=VALUES(configuration_fingerprint),
                              is_current=1
                            """
                        ),
                        {
                            "provider_key": manifest.provider,
                            "route_id": route.route_id,
                            "route_version": route_version,
                            "priority": route.priority,
                            "endpoint_host": route.settings.endpoint_host,
                            "model_name": route.settings.model,
                            "request_contract_json": json.dumps(
                                route_public["request_contract"], sort_keys=True
                            ),
                            "configuration_fingerprint": route_fingerprint,
                            "created_at": now,
                        },
                    )

    def apply_routes(
        self,
        provider: str,
        routes: tuple[ResolvedProviderRoute, ...],
    ) -> tuple[ResolvedProviderRoute, ...]:
        """Apply mutable public controls to secret-bearing in-memory routes."""

        if not routes:
            return routes
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT route_id, enabled, priority_override
                    FROM airank_provider_route_controls
                    WHERE provider_key=:provider_key
                    """
                ),
                {"provider_key": provider},
            ).mappings().all()
        controls = {str(row["route_id"]): row for row in rows}
        controlled: list[ResolvedProviderRoute] = []
        for route in routes:
            control = controls.get(route.route_id)
            if control is not None and not bool(control["enabled"]):
                continue
            priority = (
                int(control["priority_override"])
                if control is not None and control["priority_override"] is not None
                else route.priority
            )
            controlled.append(replace(route, priority=priority))
        return tuple(sorted(controlled, key=lambda route: (-route.priority, route.route_id)))

    def list_route_status(
        self,
        manifests: Iterable[ProviderManifest],
    ) -> list[dict[str, object]]:
        configured_routes = [
            (manifest, route)
            for manifest in manifests
            for route in resolve_provider_routes(manifest, self.env)
        ]
        with self.engine.connect() as conn:
            controls = {
                (str(row["provider_key"]), str(row["route_id"])): row
                for row in conn.execute(
                    text(
                        """
                        SELECT provider_key, route_id, enabled, priority_override,
                               control_version, updated_by, reason, updated_at
                        FROM airank_provider_route_controls
                        """
                    )
                ).mappings().all()
            }
            stats = {
                (str(row["provider_key"]), str(row["route_id"])): row
                for row in conn.execute(
                    text(
                        """
                        SELECT a.provider_key, a.route_id,
                               COUNT(*) AS request_count,
                               SUM(a.outcome='success') AS success_count,
                               SUM(a.outcome<>'success') AS failure_count,
                               AVG(a.duration_ms) AS average_duration_ms,
                               SUM(u.total_tokens) AS total_tokens,
                               SUM(u.cost_amount) AS cost_amount,
                               CASE
                                 WHEN COUNT(DISTINCT u.cost_currency)=1 THEN MAX(u.cost_currency)
                                 WHEN COUNT(DISTINCT u.cost_currency)>1 THEN 'MIXED'
                                 ELSE NULL
                               END AS cost_currency
                        FROM airank_provider_request_audits a
                        LEFT JOIN airank_provider_usage_events u
                          ON u.request_audit_id=a.id
                        WHERE a.requested_at >= UTC_TIMESTAMP(3) - INTERVAL 24 HOUR
                          AND a.route_id IS NOT NULL
                        GROUP BY a.provider_key, a.route_id
                        """
                    )
                ).mappings().all()
            }
        records: list[dict[str, object]] = []
        for manifest, route in configured_routes:
            key = (manifest.provider, route.route_id)
            control = controls.get(key)
            metric = stats.get(key)
            request_count = int(metric["request_count"]) if metric else 0
            success_count = int(metric["success_count"] or 0) if metric else 0
            records.append(
                {
                    "provider": manifest.provider,
                    "label": manifest.label,
                    "route_id": route.route_id,
                    "endpoint_host": route.settings.endpoint_host,
                    "model": route.settings.model,
                    "request_kind": route.settings.request_kind,
                    "configured": route.settings.configured,
                    "enabled": bool(control["enabled"]) if control else True,
                    "base_priority": route.priority,
                    "effective_priority": (
                        int(control["priority_override"])
                        if control and control["priority_override"] is not None
                        else route.priority
                    ),
                    "priority_override": (
                        int(control["priority_override"])
                        if control and control["priority_override"] is not None
                        else None
                    ),
                    "control_version": int(control["control_version"]) if control else 0,
                    "updated_by": str(control["updated_by"]) if control else None,
                    "reason": str(control["reason"]) if control else None,
                    "updated_at": control["updated_at"].isoformat() if control else None,
                    "configuration_fingerprint": route.settings.configuration_fingerprint(
                        manifest.provider, route.route_id
                    ),
                    "request_count_24h": request_count,
                    "success_count_24h": success_count,
                    "failure_count_24h": int(metric["failure_count"] or 0) if metric else 0,
                    "success_rate_24h": (
                        round(success_count / request_count, 6) if request_count else None
                    ),
                    "average_duration_ms_24h": (
                        round(float(metric["average_duration_ms"]), 2)
                        if metric and metric["average_duration_ms"] is not None
                        else None
                    ),
                    "total_tokens_24h": (
                        int(metric["total_tokens"])
                        if metric and metric["total_tokens"] is not None
                        else None
                    ),
                    "cost_amount_24h": (
                        str(metric["cost_amount"])
                        if metric and metric["cost_amount"] is not None
                        else None
                    ),
                    "cost_currency": (
                        str(metric["cost_currency"])
                        if metric and metric["cost_currency"]
                        else None
                    ),
                }
            )
        return sorted(records, key=lambda item: (
            str(item["provider"]), -int(item["effective_priority"]), str(item["route_id"])
        ))

    def set_route_control(
        self,
        provider: str,
        route_id: str,
        *,
        enabled: bool,
        priority_override: int | None,
        expected_version: int,
        changed_by: str,
        reason: str,
    ) -> dict[str, object]:
        if priority_override is not None and not -10_000 <= priority_override <= 10_000:
            raise ProviderGatewayError(
                provider,
                "PROVIDER_ROUTE_CONTROL_INVALID",
                "route priority override must be between -10000 and 10000",
            )
        actor = changed_by.strip()
        change_reason = reason.strip()
        if not actor or not change_reason:
            raise ProviderGatewayError(
                provider,
                "PROVIDER_ROUTE_CONTROL_INVALID",
                "route control actor and reason are required",
            )
        manifest = get_manifest(provider)
        if manifest is None:
            raise ProviderGatewayError(
                provider,
                "PROVIDER_ROUTE_NOT_FOUND",
                "provider manifest was not found",
            )
        configured_routes = tuple(
            route
            for route in resolve_provider_routes(manifest, self.env)
            if route.settings.configured and not route.settings.disabled
        )
        route_ids = {route.route_id for route in configured_routes}
        if route_id not in route_ids:
            raise ProviderGatewayError(
                provider,
                "PROVIDER_ROUTE_NOT_FOUND",
                "configured provider route was not found",
            )
        now = utc_now_naive()
        with self.engine.begin() as conn:
            # Materialize the implicit default before locking. MySQL cannot lock
            # a missing row, so without this insert two first-time operators
            # could both observe version 0. The baseline mirrors the runtime
            # default and is not a user change event.
            conn.execute(
                text(
                    """
                    INSERT IGNORE INTO airank_provider_route_controls (
                      provider_key, route_id, enabled, priority_override,
                      control_version, updated_by, reason, updated_at
                    ) VALUES (
                      :provider_key, :route_id, 1, NULL,
                      0, 'system_default', 'implicit enabled runtime default', :updated_at
                    )
                    """
                ),
                {"provider_key": provider, "route_id": route_id, "updated_at": now},
            )
            current = conn.execute(
                text(
                    """
                    SELECT enabled, priority_override, control_version,
                           updated_by, reason, updated_at
                    FROM airank_provider_route_controls
                    WHERE provider_key=:provider_key AND route_id=:route_id
                    FOR UPDATE
                    """
                ),
                {"provider_key": provider, "route_id": route_id},
            ).mappings().first()
            if current is None:  # pragma: no cover - INSERT IGNORE + same transaction guarantees the row
                raise ProviderGatewayError(
                    provider,
                    "PROVIDER_ROUTE_CONTROL_CONFLICT",
                    "route control baseline could not be locked",
                )
            current_version = int(current["control_version"])
            if current_version != expected_version:
                raise ProviderGatewayError(
                    provider,
                    "PROVIDER_ROUTE_CONTROL_CONFLICT",
                    "route control version changed; reload before updating",
                )
            next_version = current_version + 1
            simulated_controls = {
                str(row["route_id"]): bool(row["enabled"])
                for row in conn.execute(
                    text(
                        """
                        SELECT route_id, enabled FROM airank_provider_route_controls
                        WHERE provider_key=:provider_key
                        """
                    ),
                    {"provider_key": provider},
                ).mappings().all()
            }
            simulated_controls[route_id] = enabled
            if not any(simulated_controls.get(item.route_id, True) for item in configured_routes):
                raise ProviderGatewayError(
                    provider,
                    "PROVIDER_LAST_ROUTE_DISABLE_FORBIDDEN",
                    "at least one configured provider route must remain enabled",
                )
            previous_record = {
                "enabled": bool(current["enabled"]),
                "priority_override": current["priority_override"],
                "control_version": current_version,
                "updated_by": current["updated_by"],
                "reason": current["reason"],
                "updated_at": current["updated_at"].isoformat(),
            }
            new_record = {
                "provider": provider,
                "route_id": route_id,
                "enabled": enabled,
                "priority_override": priority_override,
                "control_version": next_version,
                "updated_by": actor[:128],
                "reason": change_reason[:500],
                "updated_at": now.isoformat(),
            }
            conn.execute(
                text(
                    """
                    INSERT INTO airank_provider_route_controls (
                      provider_key, route_id, enabled, priority_override,
                      control_version, updated_by, reason, updated_at
                    ) VALUES (
                      :provider_key, :route_id, :enabled, :priority_override,
                      :control_version, :updated_by, :reason, :updated_at
                    ) ON DUPLICATE KEY UPDATE
                      enabled=VALUES(enabled),
                      priority_override=VALUES(priority_override),
                      control_version=VALUES(control_version),
                      updated_by=VALUES(updated_by),
                      reason=VALUES(reason),
                      updated_at=VALUES(updated_at)
                    """
                ),
                {
                    "provider_key": provider,
                    "route_id": route_id,
                    **{key: new_record[key] for key in (
                        "enabled", "priority_override", "control_version",
                        "updated_by", "reason", "updated_at"
                    )},
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_provider_route_control_events (
                      id, provider_key, route_id, control_version,
                      previous_control_json, new_control_json,
                      changed_by, reason, changed_at
                    ) VALUES (
                      :id, :provider_key, :route_id, :control_version,
                      :previous_control_json, :new_control_json,
                      :changed_by, :reason, :changed_at
                    )
                    """
                ),
                {
                    "id": f"route_event_{uuid4().hex}",
                    "provider_key": provider,
                    "route_id": route_id,
                    "control_version": next_version,
                    "previous_control_json": json.dumps(previous_record, ensure_ascii=False),
                    "new_control_json": json.dumps(new_record, ensure_ascii=False),
                    "changed_by": actor[:128],
                    "reason": change_reason[:500],
                    "changed_at": now,
                },
            )
        return new_record

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

    def acquire_capacity(
        self,
        provider: str,
        configuration_fingerprint: str,
        *,
        context: ProviderRequestContext,
    ) -> ProviderCapacityLease:
        """Atomically consume one distributed QPS token and one concurrency slot."""

        now = utc_now_naive()
        fingerprint = self._fingerprint(configuration_fingerprint)
        qps_limit, concurrency_limit = self._provider_capacity_limits(provider)
        expires_at = now + timedelta(seconds=self.capacity_lease_ttl_seconds)
        denied: ProviderGatewayError | None = None
        lease_id = f"capacity_{uuid4().hex}"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_provider_capacity_states (
                      provider_key, configuration_fingerprint, qps_limit,
                      concurrency_limit, available_tokens, last_refill_at,
                      in_flight_count, updated_at
                    ) VALUES (
                      :provider_key, :configuration_fingerprint, :qps_limit,
                      :concurrency_limit, :available_tokens, :last_refill_at,
                      0, :updated_at
                    ) ON DUPLICATE KEY UPDATE
                      qps_limit=VALUES(qps_limit),
                      concurrency_limit=VALUES(concurrency_limit)
                    """
                ),
                {
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                    "qps_limit": qps_limit,
                    "concurrency_limit": concurrency_limit,
                    "available_tokens": qps_limit,
                    "last_refill_at": now,
                    "updated_at": now,
                },
            )
            state = conn.execute(
                text(
                    """
                    SELECT qps_limit, concurrency_limit, available_tokens,
                           last_refill_at, in_flight_count
                    FROM airank_provider_capacity_states
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    FOR UPDATE
                    """
                ),
                {
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            ).mappings().one()
            expired = conn.execute(
                text(
                    """
                    SELECT id FROM airank_provider_capacity_leases
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                      AND status='active' AND expires_at <= :now
                    FOR UPDATE
                    """
                ),
                {
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                    "now": now,
                },
            ).scalars().all()
            if expired:
                conn.execute(
                    text(
                        """
                        UPDATE airank_provider_capacity_leases
                        SET status='expired', released_at=:now
                        WHERE provider_key=:provider_key
                          AND configuration_fingerprint=:configuration_fingerprint
                          AND status='active' AND expires_at <= :now
                        """
                    ),
                    {
                        "provider_key": provider,
                        "configuration_fingerprint": fingerprint,
                        "now": now,
                    },
                )
            in_flight = max(0, int(state["in_flight_count"]) - len(expired))
            last_refill_at = state["last_refill_at"] or now
            elapsed_seconds = max(0.0, (now - last_refill_at).total_seconds())
            available_tokens = min(
                float(qps_limit),
                float(state["available_tokens"]) + elapsed_seconds * float(qps_limit),
            )
            existing = conn.execute(
                text(
                    """
                    SELECT id, status FROM airank_provider_capacity_leases
                    WHERE tenant_id=:tenant_id AND provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                      AND idempotency_key=:idempotency_key
                    FOR UPDATE
                    """
                ),
                {
                    "tenant_id": context.tenant_id,
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                    "idempotency_key": context.idempotency_key,
                },
            ).mappings().first()
            if existing and str(existing["status"]) == "active":
                denied = ProviderGatewayError(
                    provider,
                    "PROVIDER_REQUEST_IN_PROGRESS",
                    "provider request already owns a distributed capacity lease",
                    retryable=True,
                )
            elif in_flight >= concurrency_limit:
                denied = ProviderGatewayError(
                    provider,
                    "PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED",
                    "provider distributed concurrency limit is reached",
                    retryable=True,
                )
            elif available_tokens < 1.0:
                denied = ProviderGatewayError(
                    provider,
                    "PROVIDER_DISTRIBUTED_RATE_LIMITED",
                    "provider distributed QPS token is not available",
                    retryable=True,
                )
            else:
                available_tokens -= 1.0
                in_flight += 1
                lease_id = str(existing["id"]) if existing else lease_id
                if existing:
                    conn.execute(
                        text(
                            """
                            UPDATE airank_provider_capacity_leases
                            SET project_id=:project_id, status='active',
                                acquired_at=:acquired_at, expires_at=:expires_at,
                                released_at=NULL
                            WHERE id=:id
                            """
                        ),
                        {
                            "project_id": context.project_id,
                            "acquired_at": now,
                            "expires_at": expires_at,
                            "id": lease_id,
                        },
                    )
                else:
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_provider_capacity_leases (
                              id, tenant_id, project_id, provider_key,
                              configuration_fingerprint, idempotency_key,
                              status, acquired_at, expires_at, created_at
                            ) VALUES (
                              :id, :tenant_id, :project_id, :provider_key,
                              :configuration_fingerprint, :idempotency_key,
                              'active', :acquired_at, :expires_at, :created_at
                            )
                            """
                        ),
                        {
                            "id": lease_id,
                            "tenant_id": context.tenant_id,
                            "project_id": context.project_id,
                            "provider_key": provider,
                            "configuration_fingerprint": fingerprint,
                            "idempotency_key": context.idempotency_key,
                            "acquired_at": now,
                            "expires_at": expires_at,
                            "created_at": now,
                        },
                    )
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_capacity_states
                    SET qps_limit=:qps_limit,
                        concurrency_limit=:concurrency_limit,
                        available_tokens=:available_tokens,
                        last_refill_at=:last_refill_at,
                        in_flight_count=:in_flight_count,
                        updated_at=:updated_at
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    """
                ),
                {
                    "qps_limit": qps_limit,
                    "concurrency_limit": concurrency_limit,
                    "available_tokens": available_tokens,
                    "last_refill_at": now,
                    "in_flight_count": in_flight,
                    "updated_at": now,
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )
        if denied is not None:
            raise denied
        return ProviderCapacityLease(
            provider=provider,
            configuration_fingerprint=fingerprint,
            tenant_id=context.tenant_id,
            lease_id=lease_id,
        )

    def release_capacity(self, lease: ProviderCapacityLease) -> None:
        if lease.released:
            return
        now = utc_now_naive()
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, status FROM airank_provider_capacity_leases
                    WHERE id=:id AND tenant_id=:tenant_id
                      AND provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    FOR UPDATE
                    """
                ),
                {
                    "id": lease.lease_id,
                    "tenant_id": lease.tenant_id,
                    "provider_key": lease.provider,
                    "configuration_fingerprint": self._fingerprint(
                        lease.configuration_fingerprint
                    ),
                },
            ).mappings().first()
            if row is not None and str(row["status"]) == "active":
                conn.execute(
                    text(
                        """
                        UPDATE airank_provider_capacity_leases
                        SET status='released', released_at=:released_at
                        WHERE id=:id AND status='active'
                        """
                    ),
                    {"released_at": now, "id": lease.lease_id},
                )
                conn.execute(
                    text(
                        """
                        UPDATE airank_provider_capacity_states
                        SET in_flight_count=GREATEST(0, in_flight_count - 1),
                            updated_at=:updated_at
                        WHERE provider_key=:provider_key
                          AND configuration_fingerprint=:configuration_fingerprint
                        """
                    ),
                    {
                        "updated_at": now,
                        "provider_key": lease.provider,
                        "configuration_fingerprint": self._fingerprint(
                            lease.configuration_fingerprint
                        ),
                    },
                )
        lease.released = True

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

    def _provider_capacity_limits(self, provider: str) -> tuple[int, int]:
        prefix = provider.upper()
        qps = self._integer(
            f"{prefix}_QPS",
            self._integer("AIRANK_PROVIDER_QPS", 2, minimum=1),
            minimum=1,
        )
        concurrency = self._integer(
            f"{prefix}_CONCURRENCY",
            self._integer("AIRANK_PROVIDER_CONCURRENCY", 2, minimum=1),
            minimum=1,
        )
        return qps, concurrency

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

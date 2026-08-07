from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import random
import os
import threading
import time
from typing import Any, Callable, Iterator, Mapping

from .adapters import build_request, parse_response
from .manifests import PROVIDER_MANIFESTS, canonical_provider, get_manifest
from .models import (
    HealthState,
    ImplementationStatus,
    ProbeLevel,
    ProbeResult,
    ProviderGatewayError,
    ProviderManifest,
    ProviderResult,
)
from .runtime import ProviderSettings, ProviderTransport, UrllibProviderTransport, auth_probe_url


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    opened_at_monotonic: float | None = None


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(1.0, cooldown_seconds)
        self._states: dict[str, CircuitState] = {}
        self._lock = threading.Lock()

    def allow(self, provider: str, now_monotonic: float | None = None) -> bool:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        with self._lock:
            state = self._states.setdefault(provider, CircuitState())
            if state.opened_at_monotonic is None:
                return True
            if now - state.opened_at_monotonic >= self.cooldown_seconds:
                state.opened_at_monotonic = None
                state.consecutive_failures = max(0, self.failure_threshold - 1)
                return True
            return False

    def success(self, provider: str) -> None:
        with self._lock:
            self._states[provider] = CircuitState()

    def failure(self, provider: str, *, retryable: bool) -> None:
        if not retryable:
            return
        with self._lock:
            state = self._states.setdefault(provider, CircuitState())
            state.consecutive_failures += 1
            if state.consecutive_failures >= self.failure_threshold:
                state.opened_at_monotonic = time.monotonic()

    def snapshot(self, provider: str) -> CircuitState:
        with self._lock:
            state = self._states.setdefault(provider, CircuitState())
            return CircuitState(state.consecutive_failures, state.opened_at_monotonic)


class ProviderLimiter:
    def __init__(self, qps: int = 2, concurrency: int = 2) -> None:
        self.qps = max(1, qps)
        self._semaphore = threading.BoundedSemaphore(max(1, concurrency))
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        self._semaphore.acquire()
        try:
            while True:
                wait_seconds = 0.0
                now = time.monotonic()
                with self._lock:
                    while self._timestamps and now - self._timestamps[0] >= 1.0:
                        self._timestamps.popleft()
                    if len(self._timestamps) < self.qps:
                        self._timestamps.append(now)
                        break
                    wait_seconds = max(0.001, 1.0 - (now - self._timestamps[0]))
                time.sleep(wait_seconds)
            yield
        finally:
            self._semaphore.release()


@dataclass
class QuotaReservation:
    provider: str
    units: int
    committed: bool = False


class InMemoryQuotaLedger:
    def __init__(self, limits: Mapping[str, int] | None = None) -> None:
        self._limits = dict(limits or {})
        self._used: dict[str, int] = {}
        self._reserved: dict[str, int] = {}
        self._lock = threading.Lock()

    def reserve(self, provider: str, units: int = 1) -> QuotaReservation:
        with self._lock:
            limit = self._limits.get(provider)
            used = self._used.get(provider, 0)
            reserved = self._reserved.get(provider, 0)
            if limit is not None and used + reserved + units > limit:
                raise ProviderGatewayError(
                    provider, "PROVIDER_QUOTA_EXHAUSTED", "provider quota reservation failed"
                )
            self._reserved[provider] = reserved + units
        return QuotaReservation(provider=provider, units=units)

    def commit(self, reservation: QuotaReservation) -> None:
        with self._lock:
            self._reserved[reservation.provider] = max(
                0, self._reserved.get(reservation.provider, 0) - reservation.units
            )
            self._used[reservation.provider] = self._used.get(reservation.provider, 0) + reservation.units
            reservation.committed = True

    def release(self, reservation: QuotaReservation) -> None:
        if reservation.committed:
            return
        with self._lock:
            self._reserved[reservation.provider] = max(
                0, self._reserved.get(reservation.provider, 0) - reservation.units
            )


class ProviderGateway:
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        transport: ProviderTransport | None = None,
        max_attempts: int = 3,
        timeout_seconds: float = 90.0,
        circuit_breaker: CircuitBreaker | None = None,
        quota_ledger: InMemoryQuotaLedger | None = None,
        audit_sink: Callable[[Mapping[str, Any]], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.env = env
        self.transport = transport or UrllibProviderTransport()
        self.max_attempts = max(1, min(max_attempts, 5))
        self.timeout_seconds = max(1.0, timeout_seconds)
        self.circuit = circuit_breaker or CircuitBreaker()
        self.quota = quota_ledger or InMemoryQuotaLedger()
        self.audit_sink = audit_sink
        self.sleep = sleep
        self._limiters: dict[str, ProviderLimiter] = {}

    def manifests(self) -> tuple[ProviderManifest, ...]:
        return tuple(PROVIDER_MANIFESTS.values())

    def settings(self, provider: str) -> ProviderSettings:
        manifest = self._manifest(provider)
        return ProviderSettings.from_env(manifest, self.env)

    def generate(self, provider: str, prompt: str) -> ProviderResult:
        manifest = self._manifest(provider)
        settings = ProviderSettings.from_env(manifest, self.env)
        self._assert_operational(manifest, settings)
        canonical = manifest.provider
        if not self.circuit.allow(canonical):
            raise ProviderGatewayError(
                canonical, "PROVIDER_CIRCUIT_OPEN", "provider circuit is open", retryable=True
            )
        reservation = self.quota.reserve(canonical)
        requested_at = datetime.now(timezone.utc)
        started = time.monotonic()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        }
        request_payload = build_request(manifest, settings.model, prompt, settings.max_tokens)
        limiter = self._limiters.setdefault(canonical, self._build_limiter(canonical))
        last_error: ProviderGatewayError | None = None
        try:
            with limiter.acquire():
                for attempt in range(1, self.max_attempts + 1):
                    try:
                        response = self.transport.request(
                            "POST",
                            settings.endpoint,
                            headers=headers,
                            payload=request_payload,
                            timeout_seconds=self.timeout_seconds,
                        )
                        answer, request_id, citations, search_used, usage = parse_response(
                            response.data,
                            response.headers,
                            search_requested=manifest.capabilities.web_search,
                        )
                        if not answer:
                            raise ProviderGatewayError(
                                canonical,
                                "PROVIDER_EMPTY_RESPONSE",
                                "provider returned an empty answer",
                            )
                        completed_at = datetime.now(timezone.utc)
                        self.circuit.success(canonical)
                        self.quota.commit(reservation)
                        result = ProviderResult(
                            provider=canonical,
                            model=settings.model,
                            answer_text=answer,
                            request_id=request_id,
                            requested_at=requested_at,
                            completed_at=completed_at,
                            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                            attempt_count=attempt,
                            evidence_grade=self._evidence_grade(manifest, search_used),
                            web_search_requested=manifest.capabilities.web_search,
                            web_search_used=search_used,
                            citations=citations,
                            usage=usage,
                            raw_response=response.data,
                            endpoint_host=settings.endpoint_host,
                            configuration_fingerprint=settings.configuration_fingerprint(canonical),
                        )
                        self._audit(result, "success")
                        return result
                    except ProviderGatewayError as exc:
                        last_error = ProviderGatewayError(
                            canonical,
                            exc.code,
                            exc.message,
                            retryable=exc.retryable,
                            status_code=exc.status_code,
                            provider_code=exc.provider_code,
                        )
                        self.circuit.failure(canonical, retryable=last_error.retryable)
                        if not last_error.retryable or attempt >= self.max_attempts:
                            raise last_error
                        self.sleep(min(5.0, 0.25 * (2 ** (attempt - 1))) + random.random() * 0.05)
        except ProviderGatewayError as exc:
            self._audit_error(canonical, settings, exc)
            raise
        finally:
            self.quota.release(reservation)
        assert last_error is not None
        raise last_error

    def probe(self, provider: str, level: ProbeLevel) -> ProbeResult:
        manifest = self._manifest(provider)
        settings = ProviderSettings.from_env(manifest, self.env)
        checked_at = datetime.now(timezone.utc)
        started = time.monotonic()
        if settings.disabled:
            return self._probe_result(manifest, settings, level, HealthState.DISABLED, checked_at, started)
        if not settings.configured:
            return self._probe_result(manifest, settings, level, HealthState.UNCONFIGURED, checked_at, started)
        try:
            self.transport.network_probe(settings.endpoint, min(self.timeout_seconds, 10.0))
            if level == ProbeLevel.NETWORK:
                return self._probe_result(manifest, settings, level, HealthState.HEALTHY, checked_at, started)
            headers = {"Accept": "application/json", "Authorization": f"Bearer {settings.api_key}"}
            response = self.transport.request(
                "GET",
                auth_probe_url(settings.endpoint, manifest.auth_probe_path),
                headers=headers,
                payload=None,
                timeout_seconds=min(self.timeout_seconds, 30.0),
            )
            if response.status < 200 or response.status >= 300:
                return self._probe_result(
                    manifest, settings, level, HealthState.AUTH_FAILED, checked_at, started
                )
            advertised_models = self._advertised_models(response.data)
            if advertised_models and settings.model not in advertised_models:
                return self._probe_result(
                    manifest,
                    settings,
                    level,
                    HealthState.MODEL_FAILED,
                    checked_at,
                    started,
                    error_code="PROVIDER_MODEL_UNAVAILABLE",
                    message="configured model was not returned by provider model probe",
                )
            if level == ProbeLevel.AUTH_MODEL:
                return self._probe_result(manifest, settings, level, HealthState.HEALTHY, checked_at, started)
            result = self.generate(manifest.provider, "健康探测：只回复 OK。")
            return ProbeResult(
                provider=manifest.provider,
                level=level,
                state=HealthState.HEALTHY,
                checked_at=checked_at,
                duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                model=result.model,
                endpoint_host=settings.endpoint_host,
                request_id_present=bool(result.request_id),
                message="generation succeeded",
            )
        except ProviderGatewayError as exc:
            state = HealthState.NETWORK_FAILED if exc.code == "PROVIDER_NETWORK_FAILED" else (
                HealthState.AUTH_FAILED
                if exc.code == "PROVIDER_AUTH_FAILED"
                else HealthState.GENERATION_FAILED
            )
            return self._probe_result(
                manifest,
                settings,
                level,
                state,
                checked_at,
                started,
                error_code=exc.code,
                message=exc.message,
            )

    def _manifest(self, provider: str) -> ProviderManifest:
        manifest = get_manifest(provider)
        if manifest is None:
            raise ProviderGatewayError(
                canonical_provider(provider), "PROVIDER_NOT_SUPPORTED", "provider is not supported"
            )
        return manifest

    @staticmethod
    def _advertised_models(data: Mapping[str, Any]) -> set[str]:
        values = data.get("data")
        if not isinstance(values, list):
            return set()
        return {
            str(item.get("id"))
            for item in values
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")
        }

    def _assert_operational(self, manifest: ProviderManifest, settings: ProviderSettings) -> None:
        if settings.disabled or manifest.implementation_status == ImplementationStatus.DISABLED:
            raise ProviderGatewayError(manifest.provider, "PROVIDER_DISABLED", "provider is disabled")
        if not settings.configured:
            raise ProviderGatewayError(
                manifest.provider, "PROVIDER_NOT_CONFIGURED", "provider credential or HTTPS endpoint is not configured"
            )
        lifecycle = manifest.lifecycle.get(settings.model)
        if lifecycle:
            values = self.env if self.env is not None else os.environ
            try:
                minimum_days = max(
                    0, int(values.get("AIRANK_PROVIDER_MODEL_MIN_DAYS_TO_SUNSET") or 30)
                )
            except ValueError:
                minimum_days = 30
            remaining_seconds = (lifecycle.sunset_at - datetime.now(timezone.utc)).total_seconds()
            if remaining_seconds <= 0:
                raise ProviderGatewayError(
                    manifest.provider,
                    "PROVIDER_MODEL_EXPIRED",
                    f"provider model expired; migrate to {lifecycle.replacement}",
                )
            if remaining_seconds < minimum_days * 86400:
                raise ProviderGatewayError(
                    manifest.provider,
                    "PROVIDER_MODEL_MIGRATION_REQUIRED",
                    f"provider model is inside migration window; migrate to {lifecycle.replacement}",
                )

    def _build_limiter(self, provider: str) -> ProviderLimiter:
        values = self.env if self.env is not None else os.environ
        prefix = provider.upper()
        try:
            qps = int(values.get(f"{prefix}_QPS") or values.get("AIRANK_PROVIDER_QPS") or 2)
            concurrency = int(
                values.get(f"{prefix}_CONCURRENCY") or values.get("AIRANK_PROVIDER_CONCURRENCY") or 2
            )
        except ValueError:
            qps, concurrency = 2, 2
        return ProviderLimiter(qps=qps, concurrency=concurrency)

    @staticmethod
    def _evidence_grade(manifest: ProviderManifest, search_used: bool | None) -> str:
        if not manifest.capabilities.web_search:
            return "provider_api_without_web_search"
        if search_used is True:
            return "provider_api_with_web_search"
        if search_used is False:
            return "provider_api_search_not_used"
        return "provider_api_search_unverified"

    def _audit(self, result: ProviderResult, outcome: str) -> None:
        if not self.audit_sink:
            return
        self.audit_sink(
            {
                "provider": result.provider,
                "model": result.model,
                "endpoint_host": result.endpoint_host,
                "request_id_present": bool(result.request_id),
                "duration_ms": result.duration_ms,
                "attempt_count": result.attempt_count,
                "evidence_grade": result.evidence_grade,
                "usage_precision": result.usage.precision.value,
                "outcome": outcome,
                "configuration_fingerprint": result.configuration_fingerprint,
            }
        )

    def _audit_error(
        self, provider: str, settings: ProviderSettings, error: ProviderGatewayError
    ) -> None:
        if not self.audit_sink:
            return
        self.audit_sink(
            {
                "provider": provider,
                "model": settings.model,
                "endpoint_host": settings.endpoint_host,
                "error_code": error.code,
                "provider_code": error.provider_code,
                "retryable": error.retryable,
                "outcome": "failed",
                "configuration_fingerprint": settings.configuration_fingerprint(provider),
            }
        )

    @staticmethod
    def _probe_result(
        manifest: ProviderManifest,
        settings: ProviderSettings,
        level: ProbeLevel,
        state: HealthState,
        checked_at: datetime,
        started: float,
        *,
        error_code: str | None = None,
        message: str | None = None,
    ) -> ProbeResult:
        return ProbeResult(
            provider=manifest.provider,
            level=level,
            state=state,
            checked_at=checked_at,
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
            model=settings.model,
            endpoint_host=settings.endpoint_host,
            error_code=error_code,
            message=message,
        )

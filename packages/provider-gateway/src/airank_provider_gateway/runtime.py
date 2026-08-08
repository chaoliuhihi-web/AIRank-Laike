from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import socket
import ssl
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .models import ProviderGatewayError, ProviderManifest


PROVIDER_REQUEST_KINDS = frozenset(
    {"chat_completions", "chat_completions_search", "responses_web_search"}
)
LEGACY_PROVIDER_REQUEST_KIND_ALIASES = {
    "openai_chat": "chat_completions",
}


def normalize_provider_request_kind(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    normalized = LEGACY_PROVIDER_REQUEST_KIND_ALIASES.get(normalized, normalized)
    return normalized if normalized in PROVIDER_REQUEST_KINDS else None


@dataclass(frozen=True)
class ProviderSettings:
    endpoint: str
    api_key: str
    model: str
    disabled: bool
    max_tokens: int
    temperature: float | None
    reasoning_effort: str | None
    request_kind: str
    allowed_endpoint_hosts: tuple[str, ...]
    allow_custom_endpoint: bool

    @classmethod
    def from_env(
        cls, manifest: ProviderManifest, env: Mapping[str, str] | None = None
    ) -> "ProviderSettings":
        values = env if env is not None else os.environ
        provider_prefix = manifest.provider.upper()
        raw_max_tokens = values.get(f"{provider_prefix}_MAX_TOKENS") or values.get(
            "AIRANK_PROVIDER_MAX_TOKENS", str(manifest.max_tokens_default)
        )
        try:
            max_tokens = max(1, min(int(raw_max_tokens), 32768))
        except ValueError:
            max_tokens = manifest.max_tokens_default
        raw_temperature = values.get(f"{provider_prefix}_TEMPERATURE") or values.get(
            "AIRANK_PROVIDER_TEMPERATURE"
        )
        if raw_temperature is None or not str(raw_temperature).strip():
            temperature = manifest.temperature_default
        else:
            try:
                temperature = float(raw_temperature)
                if not 0 <= temperature <= 2:
                    raise ValueError
            except (TypeError, ValueError):
                temperature = manifest.temperature_default
        raw_reasoning_effort = values.get(f"{provider_prefix}_REASONING_EFFORT") or values.get(
            "AIRANK_PROVIDER_REASONING_EFFORT"
        )
        reasoning_effort = (
            str(raw_reasoning_effort).strip().lower()
            if raw_reasoning_effort is not None and str(raw_reasoning_effort).strip()
            else manifest.reasoning_effort_default
        )
        if reasoning_effort not in {None, "low", "high", "max"}:
            reasoning_effort = manifest.reasoning_effort_default
        request_kind = normalize_provider_request_kind(
            values.get(f"{provider_prefix}_REQUEST_KIND") or manifest.request_kind
        )
        if request_kind is None:
            raise ProviderGatewayError(
                manifest.provider,
                "PROVIDER_REQUEST_KIND_INVALID",
                "provider request kind is invalid",
            )
        return cls(
            endpoint=str(values.get(manifest.endpoint_env) or manifest.endpoint_default).strip(),
            api_key=str(values.get(manifest.key_env) or "").strip(),
            model=str(values.get(manifest.model_env) or manifest.model_default).strip(),
            disabled=str(values.get(manifest.disabled_env) or "false").strip().lower()
            in {"1", "true", "yes"},
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            request_kind=request_kind,
            allowed_endpoint_hosts=manifest.allowed_endpoint_hosts,
            allow_custom_endpoint=str(
                values.get("AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS") or "false"
            ).strip().lower()
            in {"1", "true", "yes"},
        )

    @property
    def configured(self) -> bool:
        parsed = urlparse(self.endpoint)
        normalized_host = (parsed.hostname or "").lower()
        host_allowed = self.allow_custom_endpoint or normalized_host in {
            host.lower() for host in self.allowed_endpoint_hosts
        }
        return bool(
            self.api_key
            and self.model
            and parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and host_allowed
        )

    @property
    def endpoint_host(self) -> str:
        return urlparse(self.endpoint).hostname or ""

    def configuration_fingerprint(self, provider: str, route_id: str = "default") -> str:
        payload = {
            "contract": "airank.provider-config.v4",
            "provider": provider,
            "route_id": route_id,
            "endpoint": self.endpoint,
            "model": self.model,
            "disabled": self.disabled,
            "key_digest": hashlib.sha256(self.api_key.encode("utf-8")).hexdigest(),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "request_kind": self.request_kind,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    data: Mapping[str, Any]


class ProviderTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        ...

    def network_probe(self, endpoint: str, timeout_seconds: float) -> None:
        ...


class UrllibProviderTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url=url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout_seconds, context=ssl.create_default_context()) as response:
                raw = response.read()
                data = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(data, dict):
                    raise ProviderGatewayError("unknown", "PROVIDER_RESPONSE_INVALID", "provider returned non-object JSON")
                return HttpResponse(
                    status=int(response.status),
                    headers={str(key): str(value) for key, value in response.headers.items()},
                    data=data,
                )
        except HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = {}
            provider_code = _provider_error_code(parsed)
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            raise ProviderGatewayError(
                "unknown",
                _status_error_code(exc.code),
                f"provider request failed with HTTP {exc.code}",
                retryable=retryable,
                status_code=exc.code,
                provider_code=provider_code,
            ) from exc
        except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
            raise ProviderGatewayError(
                "unknown",
                "PROVIDER_NETWORK_FAILED",
                f"provider network request failed: {type(exc).__name__}",
                retryable=True,
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderGatewayError(
                "unknown", "PROVIDER_RESPONSE_INVALID", "provider returned invalid JSON"
            ) from exc

    def network_probe(self, endpoint: str, timeout_seconds: float) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ProviderGatewayError(
                "unknown", "PROVIDER_ENDPOINT_INVALID", "provider endpoint must be an HTTPS URL"
            )
        port = parsed.port or 443
        try:
            addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
            if not addresses:
                raise OSError("DNS returned no addresses")
            with socket.create_connection((parsed.hostname, port), timeout=timeout_seconds):
                return
        except (OSError, socket.timeout) as exc:
            raise ProviderGatewayError(
                "unknown",
                "PROVIDER_NETWORK_FAILED",
                f"provider network probe failed: {type(exc).__name__}",
                retryable=True,
            ) from exc


def auth_probe_url(endpoint: str, path: str) -> str:
    parsed = urlparse(endpoint)
    endpoint_path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if endpoint_path.endswith(suffix):
            endpoint_path = endpoint_path[: -len(suffix)]
            break
    base = parsed._replace(path=f"{endpoint_path}/", params="", query="", fragment="").geturl()
    return urljoin(base, path.lstrip("/"))


def _provider_error_code(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    value = error.get("code") or error.get("type") or data.get("code") or data.get("type")
    if not value:
        return None
    return "".join(character for character in str(value) if character.isalnum() or character in "_.:-")[:80]


def _status_error_code(status: int) -> str:
    if status in {401, 403}:
        return "PROVIDER_AUTH_FAILED"
    if status == 404:
        return "PROVIDER_MODEL_OR_ENDPOINT_NOT_FOUND"
    if status == 429:
        return "PROVIDER_RATE_OR_QUOTA_LIMITED"
    if 500 <= status <= 599:
        return "PROVIDER_UPSTREAM_FAILED"
    return "PROVIDER_REQUEST_REJECTED"

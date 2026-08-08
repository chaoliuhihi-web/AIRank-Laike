from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Mapping

from .models import ProviderGatewayError, ProviderManifest
from .runtime import PROVIDER_REQUEST_KINDS, ProviderSettings


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_ROUTE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,63}$")
_ALLOWED_ROUTE_FIELDS = {
    "route_id",
    "priority",
    "enabled",
    "endpoint",
    "model",
    "key_env",
    "max_tokens",
    "temperature",
    "reasoning_effort",
    "request_kind",
}


@dataclass(frozen=True)
class ResolvedProviderRoute:
    route_id: str
    priority: int
    settings: ProviderSettings


def resolve_provider_routes(
    manifest: ProviderManifest,
    env: Mapping[str, str] | None = None,
) -> tuple[ResolvedProviderRoute, ...]:
    values = env if env is not None else os.environ
    default_settings = ProviderSettings.from_env(manifest, values)
    raw = str(values.get(f"{manifest.provider.upper()}_ROUTES_JSON") or "").strip()
    if not raw:
        return (
            ResolvedProviderRoute(
                route_id=f"{manifest.provider}:default",
                priority=0,
                settings=default_settings,
            ),
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _invalid_routes(manifest) from exc
    if not isinstance(parsed, list) or not 1 <= len(parsed) <= 16:
        raise _invalid_routes(manifest)

    routes: list[ResolvedProviderRoute] = []
    seen_ids: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict) or set(item) - _ALLOWED_ROUTE_FIELDS:
            raise _invalid_routes(manifest)
        route_id = str(item.get("route_id") or "").strip()
        if not _ROUTE_ID.fullmatch(route_id) or route_id in seen_ids:
            raise _invalid_routes(manifest)
        seen_ids.add(route_id)
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise _invalid_routes(manifest)
        if not enabled:
            continue
        key_env = str(item.get("key_env") or manifest.key_env).strip()
        if not _ENV_NAME.fullmatch(key_env):
            raise _invalid_routes(manifest)
        endpoint = str(item.get("endpoint") or default_settings.endpoint).strip()
        model = str(item.get("model") or default_settings.model).strip()
        try:
            priority = int(item.get("priority", 0))
            max_tokens = int(item.get("max_tokens", default_settings.max_tokens))
        except (TypeError, ValueError) as exc:
            raise _invalid_routes(manifest) from exc
        raw_temperature = item.get("temperature", default_settings.temperature)
        if raw_temperature is None:
            temperature = None
        else:
            try:
                temperature = float(raw_temperature)
            except (TypeError, ValueError) as exc:
                raise _invalid_routes(manifest) from exc
        reasoning_effort = item.get("reasoning_effort", default_settings.reasoning_effort)
        if reasoning_effort is not None:
            reasoning_effort = str(reasoning_effort).strip().lower()
        request_kind = str(
            item.get("request_kind", default_settings.request_kind)
        ).strip().lower()
        if (
            not -10_000 <= priority <= 10_000
            or not 1 <= max_tokens <= 32_768
            or (temperature is not None and not 0 <= temperature <= 2)
            or reasoning_effort not in {None, "low", "high", "max"}
            or request_kind not in PROVIDER_REQUEST_KINDS
        ):
            raise _invalid_routes(manifest)
        routes.append(
            ResolvedProviderRoute(
                route_id=route_id,
                priority=priority,
                settings=ProviderSettings(
                    endpoint=endpoint,
                    api_key=str(values.get(key_env) or "").strip(),
                    model=model,
                    disabled=default_settings.disabled,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                    request_kind=request_kind,
                    allowed_endpoint_hosts=default_settings.allowed_endpoint_hosts,
                    allow_custom_endpoint=default_settings.allow_custom_endpoint,
                ),
            )
        )
    if not routes:
        raise ProviderGatewayError(
            manifest.provider,
            "PROVIDER_ROUTES_UNAVAILABLE",
            "provider has no enabled upstream route",
        )
    return tuple(sorted(routes, key=lambda route: (-route.priority, route.route_id)))


def _invalid_routes(manifest: ProviderManifest) -> ProviderGatewayError:
    return ProviderGatewayError(
        manifest.provider,
        "PROVIDER_ROUTE_CONFIG_INVALID",
        "provider route configuration is invalid",
    )

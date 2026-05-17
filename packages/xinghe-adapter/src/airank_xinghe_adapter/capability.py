from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CapabilityStatus:
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    DEV_ONLY = "dev_only"


HttpProbe = Callable[[str, Mapping[str, str], float], tuple[int, str]]


@dataclass(frozen=True)
class CapabilityResult:
    capability: str
    status: str
    source: str
    checked_at: str
    required_for_mvp: bool
    endpoint: str | None
    blocked_reason: str
    fallback: str | None
    metadata: dict[str, str]

    def to_record(self) -> dict[str, object]:
        return {
            "capability": self.capability,
            "status": self.status,
            "source": self.source,
            "checked_at": self.checked_at,
            "required_for_mvp": self.required_for_mvp,
            "endpoint": self.endpoint,
            "blocked_reason": self.blocked_reason,
            "fallback": self.fallback,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProbeConfig:
    auth_mode: str
    yudao_base_url: str | None
    yudao_permission_info_url: str | None
    yudao_model_resolve_url: str | None
    yudao_bearer_token: str | None
    object_storage_driver: str
    object_storage_root: str | None
    crawler_gateway_base_url: str | None
    kb_service_base_url: str | None
    creator_marketing_base_url: str | None
    workflow_runner_base_url: str | None
    hermes_base_url: str | None
    timeout_seconds: float = 0.3

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ProbeConfig":
        source = env or os.environ
        return cls(
            auth_mode=source.get("AIRANK_AUTH_MODE", "dev"),
            yudao_base_url=empty_to_none(source.get("YUDAO_BASE_URL")),
            yudao_permission_info_url=empty_to_none(source.get("YUDAO_PERMISSION_INFO_URL")),
            yudao_model_resolve_url=empty_to_none(source.get("YUDAO_MODEL_RESOLVE_URL")),
            yudao_bearer_token=empty_to_none(source.get("YUDAO_BEARER_TOKEN"))
            or empty_to_none(source.get("YUDAO_TOKEN")),
            object_storage_driver=source.get("AIRANK_OBJECT_STORAGE_DRIVER", "local"),
            object_storage_root=empty_to_none(source.get("AIRANK_OBJECT_STORAGE_ROOT", ".runtime/objects")),
            crawler_gateway_base_url=empty_to_none(source.get("XINGHE_CRAWLER_GATEWAY_BASE_URL")),
            kb_service_base_url=empty_to_none(source.get("XINGHE_KB_SERVICE_BASE_URL")),
            creator_marketing_base_url=empty_to_none(source.get("XINGHE_CREATOR_MARKETING_BASE_URL")),
            workflow_runner_base_url=empty_to_none(source.get("XINGHE_WORKFLOW_RUNNER_BASE_URL")),
            hermes_base_url=empty_to_none(source.get("XINGHE_HERMES_BASE_URL"))
            or empty_to_none(source.get("HERMES_BASE_URL")),
        )


class CapabilityProbe:
    def __init__(
        self,
        config: ProbeConfig | None = None,
        *,
        http_probe: HttpProbe | None = None,
        now: datetime | None = None,
    ) -> None:
        self.config = config or ProbeConfig.from_env()
        self.http_probe = http_probe or default_http_probe
        self.checked_at = (now or datetime.now(timezone.utc)).isoformat()

    def run(self) -> tuple[CapabilityResult, ...]:
        return (
            self._probe_yudao_auth(),
            self._probe_yudao_tenant_user(),
            self._probe_object_storage(),
            self._probe_optional_http(
                capability="xinghe_crawler_gateway",
                source="xingheai2026v2",
                base_url=self.config.crawler_gateway_base_url,
                health_path="/api/crawler-gateway/runtime-status",
                fallback="packages/crawler-lite",
            ),
            self._probe_optional_http(
                capability="xinghe_kb_service",
                source="xingheai2026v2",
                base_url=self.config.kb_service_base_url,
                health_path="/internal/kb/store-topology",
                fallback="packages/kb-lite",
            ),
            self._probe_optional_http(
                capability="xinghe_creator_marketing",
                source="xingheai2026v2",
                base_url=self.config.creator_marketing_base_url,
                health_path="/health",
                fallback="packages/evidence",
            ),
            self._probe_optional_http(
                capability="xinghe_workflow_runner",
                source="xingheai2026v2",
                base_url=self.config.workflow_runner_base_url,
                health_path="/health",
                fallback="apps/worker",
            ),
            self._probe_optional_http(
                capability="xinghe_hermes",
                source="xingheai2026v2",
                base_url=self.config.hermes_base_url,
                health_path="/health",
                fallback="apps/worker scheduled jobs",
            ),
        )

    def _probe_yudao_auth(self) -> CapabilityResult:
        endpoint = self.config.yudao_permission_info_url or join_url(
            self.config.yudao_base_url,
            "/admin-api/system/auth/get-permission-info",
        )
        if self.config.auth_mode != "yudao":
            return self._result(
                "yudao_auth",
                CapabilityStatus.DEV_ONLY,
                "yudao",
                True,
                endpoint,
                f"AIRANK_AUTH_MODE={self.config.auth_mode}; using dev auth fallback",
                "apps/api dev auth",
                {"auth_mode": self.config.auth_mode},
            )
        if not endpoint:
            return self._result(
                "yudao_auth",
                CapabilityStatus.BLOCKED,
                "yudao",
                True,
                None,
                "YUDAO_PERMISSION_INFO_URL or YUDAO_BASE_URL is not configured",
                None,
                {},
            )
        if not self.config.yudao_bearer_token:
            return self._result(
                "yudao_auth",
                CapabilityStatus.DEV_ONLY,
                "yudao",
                True,
                endpoint,
                "yudao endpoint configured but no YUDAO_BEARER_TOKEN is available for authenticated probe",
                "apps/api dev auth",
                {"auth_mode": self.config.auth_mode},
            )
        return self._http_required("yudao_auth", "yudao", endpoint, "apps/api dev auth")

    def _probe_yudao_tenant_user(self) -> CapabilityResult:
        endpoint = self.config.yudao_permission_info_url or join_url(
            self.config.yudao_base_url,
            "/admin-api/system/auth/get-permission-info",
        )
        if self.config.auth_mode != "yudao":
            return self._result(
                "yudao_tenant_user",
                CapabilityStatus.DEV_ONLY,
                "yudao",
                True,
                endpoint,
                f"AIRANK_AUTH_MODE={self.config.auth_mode}; using dev tenant/user fixture context",
                "apps/api dev tenant context",
                {"auth_mode": self.config.auth_mode},
            )
        if not endpoint:
            return self._result(
                "yudao_tenant_user",
                CapabilityStatus.BLOCKED,
                "yudao",
                True,
                None,
                "tenant/user probe requires yudao permission info endpoint",
                None,
                {},
            )
        if not self.config.yudao_bearer_token:
            return self._result(
                "yudao_tenant_user",
                CapabilityStatus.DEV_ONLY,
                "yudao",
                True,
                endpoint,
                "no YUDAO_BEARER_TOKEN; tenant/user resolution can only run with dev fixture context",
                "apps/api dev tenant context",
                {},
            )
        return self._http_required("yudao_tenant_user", "yudao", endpoint, "apps/api dev tenant context")

    def _probe_object_storage(self) -> CapabilityResult:
        driver = self.config.object_storage_driver
        root = self.config.object_storage_root
        if driver in {"filesystem", "local"}:
            if not root:
                return self._result(
                    "object_storage",
                    CapabilityStatus.BLOCKED,
                    "airank",
                    True,
                    None,
                    "local object storage root is not configured",
                    None,
                    {"driver": driver},
                )
            path = Path(root)
            if driver == "filesystem":
                return self._probe_filesystem_object_storage(path)
            parent_exists = path.parent.exists()
            return self._result(
                "object_storage",
                CapabilityStatus.DEV_ONLY,
                "airank",
                True,
                str(path),
                "" if parent_exists else f"parent directory does not exist: {path.parent}",
                "local filesystem object storage",
                {"driver": driver, "root": str(path), "parent_exists": str(parent_exists).lower()},
            )
        return self._result(
            "object_storage",
            CapabilityStatus.PARTIAL,
            "airank",
            True,
            None,
            f"object storage driver {driver} requires deployment-specific credentials",
            None,
            {"driver": driver},
        )

    def _probe_filesystem_object_storage(self, path: Path) -> CapabilityResult:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe_path = path / f".airank-probe-{uuid4().hex}.txt"
            probe_payload = "airank object storage probe"
            probe_path.write_text(probe_payload, encoding="utf-8")
            read_back = probe_path.read_text(encoding="utf-8")
            probe_path.unlink()
            if read_back != probe_payload:
                return self._result(
                    "object_storage",
                    CapabilityStatus.BLOCKED,
                    "airank",
                    True,
                    str(path),
                    "filesystem object storage probe readback mismatch",
                    None,
                    {"driver": "filesystem", "root": str(path)},
                )
        except Exception as exc:
            return self._result(
                "object_storage",
                CapabilityStatus.BLOCKED,
                "airank",
                True,
                str(path),
                f"{type(exc).__name__}: {exc}",
                None,
                {"driver": "filesystem", "root": str(path)},
            )
        return self._result(
            "object_storage",
            CapabilityStatus.READY,
            "airank",
            True,
            str(path),
            "",
            None,
            {"driver": "filesystem", "root": str(path), "probe": "write-read-delete"},
        )

    def _probe_optional_http(
        self,
        *,
        capability: str,
        source: str,
        base_url: str | None,
        health_path: str,
        fallback: str,
    ) -> CapabilityResult:
        endpoint = join_url(base_url, health_path)
        if not endpoint:
            return self._result(
                capability,
                CapabilityStatus.DEV_ONLY,
                source,
                False,
                None,
                "external endpoint is not configured",
                fallback,
                {},
            )
        try:
            status_code, body = self.http_probe(endpoint, {}, self.config.timeout_seconds)
        except Exception as exc:
            return self._result(
                capability,
                CapabilityStatus.PARTIAL,
                source,
                False,
                endpoint,
                f"{type(exc).__name__}: {exc}",
                fallback,
                {},
            )
        if 200 <= status_code < 300:
            return self._result(
                capability,
                CapabilityStatus.READY,
                source,
                False,
                endpoint,
                "",
                fallback,
                {"http_status": str(status_code), "body_excerpt": body[:120]},
            )
        return self._result(
            capability,
            CapabilityStatus.PARTIAL,
            source,
            False,
            endpoint,
            f"HTTP {status_code}",
            fallback,
            {"http_status": str(status_code), "body_excerpt": body[:120]},
        )

    def _http_required(
        self,
        capability: str,
        source: str,
        endpoint: str,
        fallback: str,
    ) -> CapabilityResult:
        headers = {"Authorization": f"Bearer {self.config.yudao_bearer_token}"}
        try:
            status_code, body = self.http_probe(endpoint, headers, self.config.timeout_seconds)
        except Exception as exc:
            return self._result(
                capability,
                CapabilityStatus.BLOCKED,
                source,
                True,
                endpoint,
                f"{type(exc).__name__}: {exc}",
                fallback,
                {},
            )
        if 200 <= status_code < 300:
            return self._result(
                capability,
                CapabilityStatus.READY,
                source,
                True,
                endpoint,
                "",
                fallback,
                {"http_status": str(status_code), "body_excerpt": body[:120]},
            )
        return self._result(
            capability,
            CapabilityStatus.BLOCKED,
            source,
            True,
            endpoint,
            f"HTTP {status_code}",
            fallback,
            {"http_status": str(status_code), "body_excerpt": body[:120]},
        )

    def _result(
        self,
        capability: str,
        status: str,
        source: str,
        required_for_mvp: bool,
        endpoint: str | None,
        blocked_reason: str,
        fallback: str | None,
        metadata: dict[str, str],
    ) -> CapabilityResult:
        return CapabilityResult(
            capability=capability,
            status=status,
            source=source,
            checked_at=self.checked_at,
            required_for_mvp=required_for_mvp,
            endpoint=endpoint,
            blocked_reason=blocked_reason,
            fallback=fallback,
            metadata=metadata,
        )


def probe_capabilities(config: ProbeConfig | None = None) -> tuple[CapabilityResult, ...]:
    return CapabilityProbe(config).run()


def default_http_probe(url: str, headers: Mapping[str, str], timeout_seconds: float) -> tuple[int, str]:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(512).decode("utf-8", errors="replace")
            return int(response.status), body
    except HTTPError as exc:
        body = exc.read(512).decode("utf-8", errors="replace")
        return int(exc.code), body
    except URLError as exc:
        raise ConnectionError(str(exc.reason)) from exc


def join_url(base_url: str | None, path: str) -> str | None:
    if not base_url:
        return None
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def empty_to_none(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class ImplementationStatus(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    DISABLED = "disabled"
    DEV_ONLY = "dev_only"


class ProbeLevel(str, Enum):
    NETWORK = "l1_network"
    AUTH_MODEL = "l2_auth_model"
    GENERATION = "l3_generation"


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNCONFIGURED = "unconfigured"
    DISABLED = "disabled"
    NETWORK_FAILED = "network_failed"
    AUTH_FAILED = "auth_failed"
    MODEL_FAILED = "model_failed"
    GENERATION_FAILED = "generation_failed"
    CIRCUIT_OPEN = "circuit_open"


class UsagePrecision(str, Enum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderCapabilities:
    web_search: bool
    citations: bool
    streaming: bool = False


@dataclass(frozen=True)
class ModelLifecycle:
    sunset_at: datetime
    replacement: str
    source: str


@dataclass(frozen=True)
class ProviderManifest:
    provider: str
    label: str
    implementation_status: ImplementationStatus
    collection_mode: str
    endpoint_env: str
    endpoint_default: str
    key_env: str
    model_env: str
    model_default: str
    disabled_env: str
    request_kind: str
    capabilities: ProviderCapabilities
    allowed_endpoint_hosts: tuple[str, ...]
    auth_probe_path: str = "/models"
    lifecycle: Mapping[str, ModelLifecycle] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCitation:
    url: str
    title: str | None = None
    cited_text: str | None = None


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    precision: UsagePrecision = UsagePrecision.UNKNOWN
    source: str = "provider_response"


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    model: str
    answer_text: str
    request_id: str | None
    requested_at: datetime
    completed_at: datetime
    duration_ms: int
    attempt_count: int
    evidence_grade: str
    web_search_requested: bool
    web_search_used: bool | None
    citations: tuple[ProviderCitation, ...]
    usage: ProviderUsage
    raw_response: Mapping[str, Any]
    endpoint_host: str
    configuration_fingerprint: str


@dataclass(frozen=True)
class ProbeResult:
    provider: str
    level: ProbeLevel
    state: HealthState
    checked_at: datetime
    duration_ms: int
    model: str | None = None
    endpoint_host: str | None = None
    request_id_present: bool = False
    error_code: str | None = None
    message: str | None = None


class ProviderGatewayError(RuntimeError):
    def __init__(
        self,
        provider: str,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        provider_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.provider_code = provider_code

"""AIRank provider gateway contracts and runtime."""

from .adapters import NATIVE_CITATION_PARSER_VERSION, SEARCH_EVIDENCE_VERSION

from .gateway import (
    CircuitBreaker,
    CircuitBreakerContract,
    InMemoryQuotaLedger,
    NoopProviderCapacityLedger,
    NoopProviderRoutePolicy,
    ProviderCapacityLease,
    ProviderCapacityLedgerContract,
    ProviderGateway,
    ProviderLimiter,
    ProviderRequestContext,
    ProviderRoutePolicyContract,
    QuotaLedgerContract,
    QuotaReservation,
)
from .manifests import PROVIDER_ALIASES, PROVIDER_MANIFESTS, canonical_provider, get_manifest
from .models import (
    HealthState,
    ImplementationStatus,
    ProbeLevel,
    ProbeResult,
    ProviderCapabilities,
    ProviderCitation,
    ProviderGatewayError,
    ProviderManifest,
    ProviderResult,
    ProviderUsage,
    UsagePrecision,
)
from .runtime import HttpResponse, ProviderSettings, ProviderTransport, UrllibProviderTransport
from .routing import ResolvedProviderRoute, resolve_provider_routes

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerContract",
    "HealthState",
    "HttpResponse",
    "ImplementationStatus",
    "InMemoryQuotaLedger",
    "NoopProviderCapacityLedger",
    "NoopProviderRoutePolicy",
    "NATIVE_CITATION_PARSER_VERSION",
    "PROVIDER_ALIASES",
    "PROVIDER_MANIFESTS",
    "ProbeLevel",
    "ProbeResult",
    "ProviderCapabilities",
    "ProviderCapacityLease",
    "ProviderCapacityLedgerContract",
    "ProviderCitation",
    "ProviderGateway",
    "ProviderGatewayError",
    "ProviderLimiter",
    "ProviderRequestContext",
    "ProviderRoutePolicyContract",
    "ProviderManifest",
    "ProviderResult",
    "ProviderSettings",
    "ProviderTransport",
    "ProviderUsage",
    "QuotaLedgerContract",
    "QuotaReservation",
    "ResolvedProviderRoute",
    "SEARCH_EVIDENCE_VERSION",
    "UsagePrecision",
    "UrllibProviderTransport",
    "canonical_provider",
    "get_manifest",
    "resolve_provider_routes",
]

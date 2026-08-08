# AIRank Provider Gateway

This package is AIRank's internal API-provider boundary. It does not claim
consumer Web/App parity.

Current provider manifests: Doubao, Qianwen, Kimi, and DeepSeek. MySQL-backed
manifest, probe, configuration-scoped circuit, tenant quota, distributed QPS
tokens/concurrency leases, and idempotent reservation state are implemented.
The providers still remain `partial` until
repeated production sampling and the required API/Web/App E2E gates pass.

Runtime credentials are read only from each manifest's process environment
variable. Plaintext credentials are not represented in manifests, audit
events, usage events, or database migrations. Custom endpoint hosts are denied
unless an explicit non-production override is enabled.

The gateway exposes:

- versioned provider manifests and model lifecycle gates;
- ordered multi-upstream routes configured through `<PROVIDER>_ROUTES_JSON`;
  route JSON may reference a credential environment-variable name but cannot
  contain inline secret fields;
- audited runtime route controls stored in MySQL. The admin API can enable or
  disable a configured route and override its priority without restarting API
  or workers; every change requires a trusted actor, reason, and optimistic
  lock version, and the final configured route cannot be disabled;
- L1 network, L2 authentication/model, and L3 generation probes;
- provider-specific request/response adapters;
- retry and per-process QPS/concurrency limiting;
- process-shared MySQL circuit breaking and tenant quota reservations when
  `AIRANK_DATABASE_URL` is configured, including expired-reservation recovery
  and duplicate-task blocking;
- process-shared MySQL token-bucket QPS and concurrency leases, isolated by
  Provider configuration fingerprint, with atomic cross-worker acquisition and
  TTL recovery after worker crashes;
- request IDs, web-search state, native citations, exact/estimated usage
  provenance, selected route IDs, and route-scoped safe configuration
  fingerprints.

Route failover is deliberately narrow. Network, upstream, route authentication,
model, circuit, and route-capacity failures may move to the next eligible route.
Tenant quota exhaustion and an already-active/committed task idempotency key
never fail over, so adding routes cannot bypass budget or duplicate-call gates.

`ProviderRequestContext` carries `tenant_id`, `project_id`, and a deterministic
task idempotency key. API scan tasks use that contract so two workers cannot
charge the same task concurrently. Provider secrets remain process-only and
are represented in the database solely by a one-way configuration fingerprint.
Capacity cleanup failures do not turn an already successful upstream response
into a retry; the stale lease is recovered by TTL instead.

Operational routes are managed through `GET /api/v1/admin/provider-routes`
and `PUT /api/v1/admin/provider-routes/{provider}/{route_id}` with the trusted
`airank:provider:admin` permission. The API exposes only host, model, safe
fingerprint, control version, and 24-hour aggregate request/latency/usage data.
It never accepts or returns credentials. Automatic selection based on live
latency/success windows and long-duration load validation remain `partial`.

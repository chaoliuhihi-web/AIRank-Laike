# AIRank Provider Gateway

This package is AIRank's internal API-provider boundary. It does not claim
consumer Web/App parity.

Current provider manifests: Doubao, Qianwen, Kimi, and DeepSeek. MySQL-backed
manifest, probe, configuration-scoped circuit, tenant quota, and idempotent
reservation state are implemented. The providers still remain `partial` until
repeated production sampling and the required API/Web/App E2E gates pass.

Runtime credentials are read only from each manifest's process environment
variable. Plaintext credentials are not represented in manifests, audit
events, usage events, or database migrations. Custom endpoint hosts are denied
unless an explicit non-production override is enabled.

The gateway exposes:

- versioned provider manifests and model lifecycle gates;
- L1 network, L2 authentication/model, and L3 generation probes;
- provider-specific request/response adapters;
- retry and per-process QPS/concurrency limiting;
- process-shared MySQL circuit breaking and tenant quota reservations when
  `AIRANK_DATABASE_URL` is configured, including expired-reservation recovery
  and duplicate-task blocking;
- request IDs, web-search state, native citations, exact/estimated usage
  provenance, and safe configuration fingerprints.

`ProviderRequestContext` carries `tenant_id`, `project_id`, and a deterministic
task idempotency key. API scan tasks use that contract so two workers cannot
charge the same task concurrently. Provider secrets remain process-only and
are represented in the database solely by a one-way configuration fingerprint.

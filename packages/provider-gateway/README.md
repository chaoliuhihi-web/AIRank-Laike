# AIRank Provider Gateway

This package is AIRank's internal API-provider boundary. It does not claim
consumer Web/App parity.

Current provider manifests: Doubao, Qianwen, Kimi, and DeepSeek. All remain
`partial` until repeated production sampling, persisted probe/audit evidence,
and browser E2E gates pass.

Runtime credentials are read only from each manifest's process environment
variable. Plaintext credentials are not represented in manifests, audit
events, usage events, or database migrations. Custom endpoint hosts are denied
unless an explicit non-production override is enabled.

The gateway exposes:

- versioned provider manifests and model lifecycle gates;
- L1 network, L2 authentication/model, and L3 generation probes;
- provider-specific request/response adapters;
- retry, QPS/concurrency limiting, circuit breaking, and quota reservation;
- request IDs, web-search state, native citations, exact/estimated usage
  provenance, and safe configuration fingerprints.

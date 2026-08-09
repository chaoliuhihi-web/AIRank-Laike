# AIRank Current Release Readiness

Generated: 2026-08-09T12:07:23+08:00

Verified feature commit: `cf5f477`

Result: `BLOCKED / COMMERCIAL NO-GO`

This is the concise current release record. The executable source of truth is `scripts/release_readiness.py`; detailed historical decisions remain in `docs/handoff/release-gate.md`.

## Verified engineering gates

| Gate | Result |
| --- | --- |
| Clean worktree and diff check | PASS |
| GitHub `main` and feature branch contain `cf5f477` | PASS |
| Gitee `main` and feature branch contain `cf5f477` | PASS |
| Python / Node runtime | PASS: Python 3.11.15 / Node 24.14.0 |
| Contract tests | PASS: 255 |
| Crawler-lite tests | PASS: 6 |
| Acceptance tests | PASS: 107 |
| Scheduler tests | PASS: 20 |
| Standalone Worker tests | PASS: 47 |
| Score tests | PASS: 16 |
| Evidence tests | PASS: 48 |
| Outbound-security tests | PASS: 23 |
| Provider Gateway tests | PASS: 32 |
| Provider-native citation benchmark | PASS: 7/7 |
| Core Skill evaluation | PASS: 33/33 across 11 Skills |
| Skill Trust Gate | PASS: 11/11 local execution allowed; isolated install passed; native enforcement false |
| Xinghe adapter tests | PASS: 10 |
| Web production build | PASS |
| Real MySQL integration | PASS: 39 passed, 2 explicitly skipped |
| Alembic offline SQL and real MySQL head | PASS: `20260809_0044`, 109 AIRank tables |
| Provider model lifecycle | BLOCKED: DeepSeek v3.2 has 62 days to sunset; v4-pro migration evidence/approval missing |
| Required/Yudao authentication configuration | BLOCKED: local dev auth; production requires enforcement and Yudao |

The wider default regression separately passed `589 passed, 39 skipped`. Skips are explicit environment-dependent gates and are not counted as production evidence.

The Provider Vault now uses the persistent `20260809_0041` Operation Guard for upsert/revoke. The gate covers encrypted storage, AAD/tamper, independent HMAC domain, cross-key-id replay, RBAC/spoofing, successful replay without a second L3 call, conflicting payload rejection, failed-call replay suppression, concurrent outcome-unknown handling, append-only operation/credential hash chains and real MySQL cleanup. A tenant-scoped read-only admin list/detail now shows reconciliation count, replay status and event hashes without exposing raw secrets, raw idempotency keys or secret payloads. API/Worker/Scheduler were restarted on the new code; health, dev login, Vault portfolio and operation list return HTTP 200, recent logs contain no error markers, and the four local Provider routes remain honestly labeled `environment_legacy` rather than silently converted to tenant Vault credentials.

`airank.skill-trust-report.v1` now audits every internal Skill's dependency references, entrypoint, network/secret/filesystem/subprocess/dynamic-code boundary, admin permission and package roots. The isolated install probe copies only declared AIRank packages and explicitly declared Python dependencies. Real API verification exposed and fixed an initial long-running-runtime failure where repository-local virtualenv `site-packages` was incorrectly removed; after the fix, CLI and authenticated HTTP both report 11/11 local execution allowed and isolated installation passed. Promotion Ledger `1.1.0` binds the trust engine/report hash. All Skills remain `partial`, and the report permanently exposes `claim_level=repository_gate_only` plus `native_runtime_enforcement=false` until a production worker or external installer provides real native enforcement evidence.

`airank.provider-usage-ledger.v1` now keeps Provider Token events immutable and stores catalog cost calculations as separate append-only derivations. Alembic `0042` adds non-null raw usage hashes, tenant/provider/route/model/effective-time price versions and calculation hashes. Provider billed amount plus currency is the only exact cost path; catalog multiplication is always estimated; missing Token or price is unknown. Admin APIs/UI filter usage and cost precision and expose known-cost coverage instead of presenting partial sums as total cost. Authenticated HTTP on the restarted API reports 18 exact usage events, zero priced events, 0% cost coverage and aggregate precision unknown; no demo price was inserted.

External WordPress/HTTP publishing now uses the same persistent Operation Guard under `publisher.publish`. Alembic `0043` uniquely links each attempt to its operation. A real POST is preceded by `external_started`; any lost/invalid receipt or post-side-effect crash produces `outcome_unknown` and the same package cannot issue another POST. WordPress can only recover by a read-only deterministic-slug GET that returns an existing page; generic HTTP remains manual reconciliation. Real MySQL verified the three-event success chain, HTTP response-loss with zero duplicate POST, stale-attempt fail-closed behavior and WordPress GET-only recovery. The publish operation API is tenant scoped, requires `airank:delivery:admin`, exposes the event hash chain and has no force-success endpoint. API, Worker and Scheduler were restarted on `0043`; health is HTTP 200 and the read-only operation route returns the expected tenant-scoped not-found contract for an unknown ID.

`airank.provider-model-migration.v1` now makes model sunset a real release concern instead of a documentation note. Alembic `0044` stores tenant-scoped plans and hash-chained events. Creation binds the current route/model/fingerprint and manifest replacement; concurrent identical idempotent requests produce one plan. Validation requires a post-plan successful target-model L3 request audit with matching route/model/fingerprint and a non-empty Provider request ID. Approval remains release-eligible only while both that audit and the event chain validate. The Settings UI and route API separate the default 30-day execution stop window from the 90-day release planning window. Real HTTP currently reports DeepSeek `deepseek-v3.2` at 62 days: execution `pass`, release `blocked`, migration missing. No v4-pro success or fake approval was inserted.

## Active blockers

- `AIRANK_ENV=local` and local filesystem object storage were used. Production requires authenticated HTTPS S3/MinIO-class object storage and a fresh object lifecycle verification.
- The current runtime uses disabled API enforcement and dev authentication. Production requires enforced Yudao authentication, tenant/user checks and permission probes.
- `YUDAO_PERMISSION_INFO_URL` / `YUDAO_BASE_URL` is not configured, so real Yudao authentication and tenant/user probes are blocked.
- The Provider vault master key is process-secret-store backed, not cloud KMS/HSM; automatic re-encryption and full-tenant rotation orchestration are not implemented. No real production four-platform credential has completed vault save→rotate→revoke/recover acceptance.
- Operation Guard now protects Provider credential writes and external publishing. Route control, price-version writes and other high-risk admin mutations still require staged migration; generic HTTP `OPERATION_OUTCOME_UNKNOWN` still requires a human decision and is intentionally not auto-retried or force-resolved.
- Skill Trust Gate is a repository/source/import gate, not an OS sandbox. Production Worker native permission enforcement and an external installer/runtime probe are not implemented, so local `allow` cannot promote a Skill to `ready`.
- Usage Ledger has no production official-price synchronization, Provider invoice reconciliation, exchange-rate governance or finance-system receipt. Current known-cost amounts remain operational estimates, not settlement totals.
- Optional Xinghe Crawler, KB, content, workflow and Hermes endpoints are unconfigured and remain `dev_only` behind AIRank-owned contracts/adapters.
- Consumer Browser L3 was deliberately not rerun or accepted from this engineering gate. The latest valid generation result remains 0/4; login/human-verification blockers cannot be replaced by Provider API success or L2 page interaction.
- Kimi's exposed acceptance credential must be rotated before production. The DeepSeek model-migration gate is now active and correctly blocks release: `deepseek-v4-pro` still lacks quota, a successful L3 request audit and approval; runtime remains on `deepseek-v3.2`.
- No production customer publishing receipt, reviewer benchmark, or elapsed T+7/T+14/T+30 outcome evidence is available yet.

## Decision

The Provider model lifecycle slice is engineering-complete and dual-remote synchronized at its verified commit, while Provider Vault, Skill Trust, Usage Ledger and Publisher Operation Guard remain intact. AIRank is not authorized to claim production or commercial readiness. Obtain v4-pro quota, create a real successful target-model L3 audit, approve the migration, switch the deployed model, and then re-run the executable gate together with the other production blockers.

# AIRank Current Release Readiness

Generated: 2026-08-09T09:44:10+08:00

Verified feature commit: `5e7da04`

Result: `BLOCKED / COMMERCIAL NO-GO`

This is the concise current release record. The executable source of truth is `scripts/release_readiness.py`; detailed historical decisions remain in `docs/handoff/release-gate.md`.

## Verified engineering gates

| Gate | Result |
| --- | --- |
| Clean worktree and diff check | PASS |
| GitHub `main` and feature branch at `5e7da04` | PASS |
| Gitee `main` and feature branch at `5e7da04` | PASS |
| Python / Node runtime | PASS: Python 3.11.15 / Node 24.14.0 |
| Contract tests | PASS: 242 |
| Crawler-lite tests | PASS: 6 |
| Acceptance tests | PASS: 99 |
| Scheduler tests | PASS: 20 |
| Standalone Worker tests | PASS: 45 |
| Score tests | PASS: 16 |
| Evidence tests | PASS: 48 |
| Outbound-security tests | PASS: 23 |
| Provider Gateway tests | PASS: 32 |
| Provider-native citation benchmark | PASS: 7/7 |
| Core Skill evaluation | PASS: 33/33 across 11 Skills |
| Xinghe adapter tests | PASS: 10 |
| Web production build | PASS |
| Real MySQL integration | PASS: 37 passed, 2 explicitly skipped |
| Alembic offline SQL and real MySQL head | PASS: `20260809_0041`, 105 AIRank tables |
| Required/Yudao authentication configuration | BLOCKED: local dev auth; production requires enforcement and Yudao |

The wider default regression separately passed `561 passed, 37 skipped`. Skips are explicit environment-dependent gates and are not counted as production evidence.

The Provider Vault now uses the persistent `20260809_0041` Operation Guard for upsert/revoke. The gate covers encrypted storage, AAD/tamper, independent HMAC domain, cross-key-id replay, RBAC/spoofing, successful replay without a second L3 call, conflicting payload rejection, failed-call replay suppression, concurrent outcome-unknown handling, append-only operation/credential hash chains and real MySQL cleanup. Raw secrets and raw idempotency keys are absent from operation rows and responses. API/Worker/Scheduler were restarted on the new code; health, version, dev login and Vault portfolio return HTTP 200, recent logs contain no error markers, and the four local Provider routes remain honestly labeled `environment_legacy` rather than silently converted to tenant Vault credentials.

## Active blockers

- `AIRANK_ENV=local` and local filesystem object storage were used. Production requires authenticated HTTPS S3/MinIO-class object storage and a fresh object lifecycle verification.
- The current runtime uses disabled API enforcement and dev authentication. Production requires enforced Yudao authentication, tenant/user checks and permission probes.
- `YUDAO_PERMISSION_INFO_URL` / `YUDAO_BASE_URL` is not configured, so real Yudao authentication and tenant/user probes are blocked.
- The Provider vault master key is process-secret-store backed, not cloud KMS/HSM; automatic re-encryption and full-tenant rotation orchestration are not implemented. No real production four-platform credential has completed vault save→rotate→revoke/recover acceptance.
- Operation Guard currently protects Provider credential writes only. Other high-risk admin writes still require staged migration; `OPERATION_OUTCOME_UNKNOWN` needs an operator reconciliation workflow and is intentionally not auto-retried.
- Optional Xinghe Crawler, KB, content, workflow and Hermes endpoints are unconfigured and remain `dev_only` behind AIRank-owned contracts/adapters.
- Consumer Browser L3 was deliberately not rerun or accepted from this engineering gate. The latest valid generation result remains 0/4; login/human-verification blockers cannot be replaced by Provider API success or L2 page interaction.
- Kimi's exposed acceptance credential must be rotated before production. DeepSeek `deepseek-v3.2` requires a model-migration gate before its planned retirement.
- No production customer publishing receipt, reviewer benchmark, or elapsed T+7/T+14/T+30 outcome evidence is available yet.

## Decision

The `20260809_0041` Provider credential Operation Guard slice is engineering-complete and dual-remote synchronized at its verified commit, but AIRank is not authorized to claim production or commercial readiness. Re-run the executable gate in the real production environment after the blockers above are cleared.

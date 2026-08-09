# AIRank Current Release Readiness

Generated: 2026-08-09T09:16:00+08:00

Verified feature commit: `1acab04`

Result: `BLOCKED / COMMERCIAL NO-GO`

This is the concise current release record. The executable source of truth is `scripts/release_readiness.py`; detailed historical decisions remain in `docs/handoff/release-gate.md`.

## Verified engineering gates

| Gate | Result |
| --- | --- |
| Clean worktree and diff check | PASS |
| GitHub `main` and feature branch at `1acab04` | PASS |
| Gitee `main` and feature branch at `1acab04` | PASS |
| Python / Node runtime | PASS: Python 3.11.15 / Node 24.14.0 |
| Contract tests | PASS: 238 |
| Crawler-lite tests | PASS: 6 |
| Acceptance tests | PASS: 98 |
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
| Alembic offline SQL and real MySQL head | PASS: `20260809_0040`, 103 AIRank tables |
| Required/Yudao authentication configuration | PASS |

The wider default regression separately passed `556 passed, 37 skipped`. Skips are explicit environment-dependent gates and are not counted as production evidence.

The new `airank.provider-credential-vault.v1` slice passed encrypted-storage, AAD/tamper, independent HMAC domain, cross-key-id unchanged-secret, RBAC/spoofing, schema, Gateway resolution/failover, audit attribution and real MySQL v1→v2→revoke tests. Random MySQL test credentials and events were cleaned to zero rows. The restarted local API/Worker/Scheduler report no error markers; the vault keyring is ready, while all four real Provider routes remain honestly labeled `environment_legacy` rather than migrated tenant credentials.

## Active blockers

- `AIRANK_ENV=local` and local filesystem object storage were used. Production requires authenticated HTTPS S3/MinIO-class object storage and a fresh object lifecycle verification.
- `YUDAO_PERMISSION_INFO_URL` / `YUDAO_BASE_URL` is not configured, so real Yudao authentication and tenant/user probes are blocked.
- The Provider vault master key is process-secret-store backed, not cloud KMS/HSM; automatic re-encryption and full-tenant rotation orchestration are not implemented. No real production four-platform credential has completed vault save→rotate→revoke/recover acceptance.
- Optional Xinghe Crawler, KB, content, workflow and Hermes endpoints are unconfigured and remain `dev_only` behind AIRank-owned contracts/adapters.
- Consumer Browser L3 was deliberately not rerun or accepted from this engineering gate. The latest valid generation result remains 0/4; login/human-verification blockers cannot be replaced by Provider API success or L2 page interaction.
- Kimi's exposed acceptance credential must be rotated before production. DeepSeek `deepseek-v3.2` requires a model-migration gate before its planned retirement.
- No production customer publishing receipt, reviewer benchmark, or elapsed T+7/T+14/T+30 outcome evidence is available yet.

## Decision

The `20260809_0040` tenant Provider credential vault slice is engineering-complete and dual-remote synchronized at its verified feature commit, but AIRank is not authorized to claim production or commercial readiness. Re-run the executable gate in the real production environment after the blockers above are cleared.

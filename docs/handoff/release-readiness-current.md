# AIRank Release Readiness Report

Generated: 2026-08-08T10:31:37+08:00
Result: BLOCKED

| Check | Status | Command |
| --- | --- | --- |
| working tree | BLOCKED | `git status --short --branch` |
| origin main ref | BLOCKED | `git rev-parse HEAD && git ls-remote origin refs/heads/main` |
| gitee main ref | BLOCKED | `git rev-parse HEAD && git ls-remote gitee refs/heads/main` |
| diff check | BLOCKED | `git diff --check` |
| tracked runtime artifacts | PASS | `git ls-files | rg "node_modules|dist|\\.runtime|\\.env|\\.sqlite|tsbuildinfo"` |
| API authentication configuration | BLOCKED | `validate AIRANK_API_AUTH_ENFORCEMENT and AIRANK_AUTH_MODE` |
| production object storage configuration | BLOCKED | `validate AIRANK_ENV and S3/MinIO transport configuration` |
| runtime versions | PASS | `validate Python and Node production runtime versions` |
| contract tests | PASS | `python3 -m pytest tests/contracts -q` |
| crawler lite tests | PASS | `python3 -m pytest packages/crawler-lite/tests -q` |
| acceptance tests | PASS | `python3 -m pytest tests/acceptance -q` |
| worker tests | PASS | `cd apps/worker && python3 -m pytest -q` |
| score tests | PASS | `cd packages/score && python3 -m pytest -q` |
| evidence tests | PASS | `cd packages/evidence && python3 -m pytest -q` |
| outbound security tests | PASS | `python3 -m pytest packages/outbound-security/tests -q` |
| provider gateway tests | PASS | `python3 -m pytest packages/provider-gateway/tests -q` |
| core skill evaluation | PASS | `python3 scripts/evaluate_core_skills.py` |
| xinghe adapter tests | PASS | `cd packages/xinghe-adapter && python3 -m pytest -q` |
| web build | PASS | `cd apps/web && npm run build` |
| real integration tests | PASS | `python3 -m pytest tests/integration -q` |
| alembic offline sql | PASS | `cd apps/api && python3 -m alembic upgrade head --sql >/tmp/airank_release_alembic.sql` |
| alembic real mysql | PASS | `cd apps/api && python3 -m alembic upgrade head` |
| capability probe | BLOCKED | `CapabilityProbe(ProbeConfig.from_env()).run()` |

## working tree

Status: BLOCKED

```text
## codex/evidence-productization
 M apps/api/provider_scan.py
 M docs/handoff/productization-status-20260808.md
 M docs/handoff/release-gate.md
 M docs/handoff/release-readiness-current.md
 M scripts/release_readiness.py
 M tests/acceptance/test_release_readiness_gate.py
 M tests/contracts/test_provider_scan_contract.py
?? apps/api/__pycache__/
?? apps/api/alembic/__pycache__/
?? apps/api/alembic/versions/__pycache__/
?? apps/worker/airank_worker/__pycache__/
?? apps/worker/tests/__pycache__/
?? packages/crawler-lite/src/airank_crawler_lite/__pycache__/
?? packages/crawler-lite/tests/__pycache__/
?? packages/domain/src/airank_domain/__pycache__/
?? packages/evidence/src/airank_evidence/__pycache__/
?? packages/evidence/tests/__pycache__/
?? packages/outbound-security/src/airank_outbound_security/__pycache__/
?? packages/outbound-security/tests/__pycache__/
?? packages/provider-gateway/src/airank_provider_gateway/__pycache__/
?? packages/provider-gateway/tests/__pycache__/
?? packages/score/src/airank_score/__pycache__/
?? packages/score/tests/__pycache__/
?? packages/skills/src/airank_skills/__pycache__/
?? packages/xinghe-adapter/src/airank_xinghe_adapter/__pycache__/
?? packages/xinghe-adapter/tests/__pycache__/
?? scripts/__pycache__/
?? tests/__pycache__/
?? tests/acceptance/__pycache__/
?? tests/contracts/__pycache__/
?? tests/integration/__pycache__/
```

## origin main ref

Status: BLOCKED

```text
local HEAD 8ba1fe50ea8ebf334756a4680cd110615de37468 does not match origin main 495655c47ee44dcab4f95df4fef9d6b79b6026cf
```

## gitee main ref

Status: BLOCKED

```text
local HEAD 8ba1fe50ea8ebf334756a4680cd110615de37468 does not match gitee main 495655c47ee44dcab4f95df4fef9d6b79b6026cf
```

## diff check

Status: BLOCKED

```text
docs/handoff/release-readiness-current.md:272: trailing whitespace.
+
docs/handoff/release-readiness-current.md:276: trailing whitespace.
+
docs/handoff/release-readiness-current.md:286: trailing whitespace.
+
docs/handoff/release-readiness-current.md:292: trailing whitespace.
+
docs/handoff/release-readiness-current.md:294: trailing whitespace.
+
docs/handoff/release-readiness-current.md:299: trailing whitespace.
+
docs/handoff/release-readiness-current.md:310: trailing whitespace.
+
docs/handoff/release-readiness-current.md:313: trailing whitespace.
+
docs/handoff/release-readiness-current.md:315: trailing whitespace.
+
docs/handoff/release-readiness-current.md:331: trailing whitespace.
+
docs/handoff/release-readiness-current.md:384: trailing whitespace.
+.runtime/py312/lib/python3.12/site-packages/sqlalchemy/engine/base.py:1969:
docs/handoff/release-readiness-current.md:385: trailing whitespace.
+_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
```

## tracked runtime artifacts

Status: PASS

```text
<empty>
```

## API authentication configuration

Status: BLOCKED

```text
{
  "AIRANK_API_AUTH_ENFORCEMENT": "",
  "AIRANK_AUTH_MODE": "",
  "required": {
    "AIRANK_API_AUTH_ENFORCEMENT": "required",
    "AIRANK_AUTH_MODE": "yudao"
  },
  "blockers": [
    "AIRANK_API_AUTH_ENFORCEMENT=<empty>",
    "AIRANK_AUTH_MODE=<empty>"
  ]
}
```

## production object storage configuration

Status: BLOCKED

```text
{
  "AIRANK_ENV": "local",
  "AIRANK_OBJECT_STORAGE_DRIVER": "local",
  "endpoint_scheme": "provider-default",
  "allow_http": false,
  "blockers": [
    "AIRANK_ENV=local; release requires production",
    "AIRANK_OBJECT_STORAGE_DRIVER=local; production requires s3/minio"
  ]
}
```

## runtime versions

Status: PASS

```text
{
  "python": "3.12.13",
  "node": "v24.14.0",
  "required": {
    "python": "3.11+",
    "node": "20.19+ or 22.12+"
  },
  "blockers": []
}
```

## contract tests

Status: PASS

```text
........................................................................ [ 49%]
........................................................................ [ 99%]
.                                                                        [100%]
=============================== warnings summary ===============================
tests/contracts/test_console_action_api_contract.py: 1 warning
tests/contracts/test_report_api_contract.py: 1 warning
tests/contracts/test_scan_run_api_contract.py: 25 warnings
  /Users/bruce/Developer/work/AIRank-productization/.runtime/py312/lib/python3.12/site-packages/sqlalchemy/engine/default.py:952: DeprecationWarning: The default datetime adapter is deprecated as of Python 3.12; see the sqlite3 documentation for suggested replacement recipes
    cursor.execute(statement, parameters)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
145 passed, 27 warnings in 0.93s
```

## crawler lite tests

Status: PASS

```text
......                                                                   [100%]
6 passed in 0.02s
```

## acceptance tests

Status: PASS

```text
.....................................................                    [100%]
53 passed in 0.47s
```

## worker tests

Status: PASS

```text
.........................                                                [100%]
=============================== warnings summary ===============================
tests/test_async_job_lease.py: 73 warnings
  /Users/bruce/Developer/work/AIRank-productization/.runtime/py312/lib/python3.12/site-packages/sqlalchemy/engine/default.py:952: DeprecationWarning: The default datetime adapter is deprecated as of Python 3.12; see the sqlite3 documentation for suggested replacement recipes
    cursor.execute(statement, parameters)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
25 passed, 73 warnings in 0.11s
```

## score tests

Status: PASS

```text
..............                                                           [100%]
14 passed in 0.03s
```

## evidence tests

Status: PASS

```text
.....................                                                    [100%]
21 passed in 0.03s
```

## outbound security tests

Status: PASS

```text
.......................                                                  [100%]
23 passed in 0.01s
```

## provider gateway tests

Status: PASS

```text
...................                                                      [100%]
19 passed in 0.02s
```

## core skill evaluation

Status: PASS

```text
{"case_count": 24, "passed_case_count": 24, "promotion_eligible_count": 0, "retained_partial_count": 8, "skill_count": 8, "status": "pass"}
```

## xinghe adapter tests

Status: PASS

```text
......                                                                   [100%]
6 passed in 0.02s
```

## web build

Status: PASS

```text
> @airank/web@0.1.0 build
> tsc -b && vite build

vite v7.3.6 building client environment for production...
transforming...
✓ 1689 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.48 kB │ gzip:   0.33 kB
dist/assets/index-C5thYdsS.css   59.90 kB │ gzip:  10.22 kB
dist/assets/index-r9Lfqui9.js   329.40 kB │ gzip: 100.74 kB
✓ built in 733ms
```

## real integration tests

Status: PASS

```text
....s................s                                                   [100%]
20 passed, 2 skipped in 2.41s
```

## alembic offline sql

Status: PASS

```text
INFO  [alembic.runtime.migration] Context impl MySQLImpl.
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 20260517_0001, initial AIRank MySQL schema
INFO  [alembic.runtime.migration] Running upgrade 20260517_0001 -> 20260517_0002, reconcile URL column lengths with API contracts
INFO  [alembic.runtime.migration] Running upgrade 20260517_0002 -> 20260808_0003, add evidence-grade measurement contracts
INFO  [alembic.runtime.migration] Running upgrade 20260808_0003 -> 20260808_0004, add governed fact revisions, conflicts, claims, and supports
INFO  [alembic.runtime.migration] Running upgrade 20260808_0004 -> 20260808_0005, add provider manifest, probe, request, usage, circuit, and quota ledgers
INFO  [alembic.runtime.migration] Running upgrade 20260808_0005 -> 20260808_0006, add immutable knowledge source content and exact-boundary segments
INFO  [alembic.runtime.migration] Running upgrade 20260808_0006 -> 20260808_0007, add content review, immutable publishing snapshots, and retest windows
INFO  [alembic.runtime.migration] Running upgrade 20260808_0007 -> 20260808_0008, add evidence-backed retest comparison and report fields
INFO  [alembic.runtime.migration] Running upgrade 20260808_0008 -> 20260808_0009, add governed buyer-question maps and immutable revisions
INFO  [alembic.runtime.migration] Running upgrade 20260808_0009 -> 20260808_0010, add immutable buyer-query observation batches and records
INFO  [alembic.runtime.migration] Running upgrade 20260808_0010 -> 20260808_0011, add immutable scan task attempt ledger
INFO  [alembic.runtime.migration] Running upgrade 20260808_0011 -> 20260808_0012, add immutable page extractability audit runs and findings
INFO  [alembic.runtime.migration] Running upgrade 20260808_0012 -> 20260808_0013, add answer claims and append-only citation support reviews
INFO  [alembic.runtime.migration] Running upgrade 20260808_0013 -> 20260808_0014, add immutable citation source captures and exact source boundaries
INFO  [alembic.runtime.migration] Running upgrade 20260808_0014 -> 20260808_0015, add distributed provider QPS tokens and concurrency leases
INFO  [alembic.runtime.migration] Running upgrade 20260808_0015 -> 20260808_0016, add immutable provider route manifests and route request audit
```

## alembic real mysql

Status: PASS

```text
INFO  [alembic.runtime.migration] Context impl MySQLImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
```

## capability probe

Status: BLOCKED

```text
[
  {
    "capability": "yudao_auth",
    "status": "blocked",
    "source": "yudao",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": true,
    "endpoint": null,
    "blocked_reason": "YUDAO_PERMISSION_INFO_URL or YUDAO_BASE_URL is not configured",
    "fallback": null,
    "metadata": {}
  },
  {
    "capability": "yudao_tenant_user",
    "status": "blocked",
    "source": "yudao",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": true,
    "endpoint": null,
    "blocked_reason": "tenant/user probe requires yudao permission info endpoint",
    "fallback": null,
    "metadata": {}
  },
  {
    "capability": "object_storage",
    "status": "dev_only",
    "source": "airank",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": true,
    "endpoint": ".runtime/objects",
    "blocked_reason": "",
    "fallback": "local filesystem object storage",
    "metadata": {
      "driver": "local",
      "root": ".runtime/objects",
      "parent_exists": "true"
    }
  },
  {
    "capability": "xinghe_crawler_gateway",
    "status": "dev_only",
    "source": "xingheai2026v2",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": false,
    "endpoint": null,
    "blocked_reason": "external endpoint is not configured",
    "fallback": "packages/crawler-lite",
    "metadata": {}
  },
  {
    "capability": "xinghe_kb_service",
    "status": "dev_only",
    "source": "xingheai2026v2",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": false,
    "endpoint": null,
    "blocked_reason": "external endpoint is not configured",
    "fallback": "packages/kb-lite",
    "metadata": {}
  },
  {
    "capability": "xinghe_creator_marketing",
    "status": "dev_only",
    "source": "xingheai2026v2",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": false,
    "endpoint": null,
    "blocked_reason": "external endpoint is not configured",
    "fallback": "packages/evidence",
    "metadata": {}
  },
  {
    "capability": "xinghe_workflow_runner",
    "status": "dev_only",
    "source": "xingheai2026v2",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": false,
    "endpoint": null,
    "blocked_reason": "external endpoint is not configured",
    "fallback": "apps/worker",
    "metadata": {}
  },
  {
    "capability": "xinghe_hermes",
    "status": "dev_only",
    "source": "xingheai2026v2",
    "checked_at": "2026-08-08T02:31:37.235990+00:00",
    "required_for_mvp": false,
    "endpoint": null,
    "blocked_reason": "external endpoint is not configured",
    "fallback": "apps/worker scheduled jobs",
    "metadata": {}
  }
]

Blockers:
- yudao_auth=blocked (YUDAO_PERMISSION_INFO_URL or YUDAO_BASE_URL is not configured)
- yudao_tenant_user=blocked (tenant/user probe requires yudao permission info endpoint)
- object_storage=dev_only
- xinghe_crawler_gateway=dev_only (external endpoint is not configured)
- xinghe_kb_service=dev_only (external endpoint is not configured)
- xinghe_creator_marketing=dev_only (external endpoint is not configured)
- xinghe_workflow_runner=dev_only (external endpoint is not configured)
- xinghe_hermes=dev_only (external endpoint is not configured)
```


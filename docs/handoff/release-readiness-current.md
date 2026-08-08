# AIRank Release Readiness Report

Generated: 2026-08-08T21:52:42+08:00
Result: BLOCKED

| Check | Status | Command |
| --- | --- | --- |
| working tree | PASS | `git status --short --branch` |
| origin main ref | BLOCKED | `git rev-parse HEAD && git ls-remote origin refs/heads/main` |
| gitee main ref | PASS | `git rev-parse HEAD && git ls-remote gitee refs/heads/main` |
| diff check | PASS | `git diff --check` |
| tracked runtime artifacts | PASS | `git ls-files | rg "node_modules|dist|\\.runtime|\\.env|\\.sqlite|tsbuildinfo"` |
| API authentication configuration | BLOCKED | `validate AIRANK_API_AUTH_ENFORCEMENT and AIRANK_AUTH_MODE` |
| production object storage configuration | BLOCKED | `validate AIRANK_ENV and S3/MinIO transport configuration` |
| runtime versions | PASS | `validate Python and Node production runtime versions` |
| contract tests | PASS | `python3 -m pytest tests/contracts -q` |
| crawler lite tests | PASS | `python3 -m pytest packages/crawler-lite/tests -q` |
| acceptance tests | PASS | `python3 -m pytest tests/acceptance -q` |
| scheduler tests | PASS | `python3 -m pytest apps/scheduler/tests -q` |
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
| browser provider readiness | BLOCKED | `probe_provider_generation_readiness(DEFAULT_PROVIDER_SCOPE)` |

## working tree

Status: PASS

```text
## codex/evidence-productization
```

## origin main ref

Status: BLOCKED

```text
55d8b01ac6bfe7253b979afcabacac6c8be1a516
banner exchange: Connection to 140.82.116.3 port 22: invalid format
fatal: Could not read from remote repository.

Please make sure you have the correct access rights
and the repository exists.
```

## gitee main ref

Status: PASS

```text
55d8b01ac6bfe7253b979afcabacac6c8be1a516
```

## diff check

Status: PASS

```text
<empty>
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
  "python": "3.11.15",
  "node": "v24.13.1",
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
........................................................................ [ 38%]
........................................................................ [ 77%]
.........................................                                [100%]
185 passed in 2.13s
```

## crawler lite tests

Status: PASS

```text
......                                                                   [100%]
6 passed in 0.01s
```

## acceptance tests

Status: PASS

```text
......................................................................   [100%]
70 passed in 0.68s
```

## scheduler tests

Status: PASS

```text
.......                                                                  [100%]
7 passed in 0.26s
```

## worker tests

Status: PASS

```text
...................................                                      [100%]
35 passed in 0.14s
```

## score tests

Status: PASS

```text
................                                                         [100%]
16 passed in 0.04s
```

## evidence tests

Status: PASS

```text
................................................                         [100%]
48 passed in 0.06s
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
.......................                                                  [100%]
23 passed in 0.02s
```

## core skill evaluation

Status: PASS

```text
{"case_count": 30, "passed_case_count": 30, "promotion_eligible_count": 0, "retained_partial_count": 10, "skill_count": 10, "status": "pass"}
```

## xinghe adapter tests

Status: PASS

```text
......                                                                   [100%]
6 passed in 0.03s
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
dist/assets/index-ClLEF_uU.css   72.24 kB │ gzip:  11.79 kB
dist/assets/index-Ba_FmfkF.js   400.96 kB │ gzip: 119.27 kB
✓ built in 747ms
```

## real integration tests

Status: PASS

```text
......s...................s...                                           [100%]
28 passed, 2 skipped in 3.42s
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
INFO  [alembic.runtime.migration] Running upgrade 20260808_0016 -> 20260808_0017, add audited provider route control overrides
INFO  [alembic.runtime.migration] Running upgrade 20260808_0017 -> 20260808_0018, add immutable customer report evidence packets
INFO  [alembic.runtime.migration] Running upgrade 20260808_0018 -> 20260808_0019, add governed answer fact classifications and immutable accuracy reviews
INFO  [alembic.runtime.migration] Running upgrade 20260808_0019 -> 20260808_0020, add versioned citation source registry reviews
INFO  [alembic.runtime.migration] Running upgrade 20260808_0020 -> 20260808_0021, allow immutable report packets to supersede when governed evidence changes
INFO  [alembic.runtime.migration] Running upgrade 20260808_0021 -> 20260808_0022, persist public provider request contracts for historical audit joins
INFO  [alembic.runtime.migration] Running upgrade 20260808_0022 -> 20260808_0023, bind governed facts to a stable comparison subject
INFO  [alembic.runtime.migration] Running upgrade 20260808_0023 -> 20260808_0024, add governed knowledge source synchronization
INFO  [alembic.runtime.migration] Running upgrade 20260808_0024 -> 20260808_0025, add independent evidence review cases and agreement gates
INFO  [alembic.runtime.migration] Running upgrade 20260808_0025 -> 20260808_0026, add immutable project evidence integrity audits
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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
    "checked_at": "2026-08-08T13:51:37.767537+00:00",
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

## browser provider readiness

Status: BLOCKED

```text
{
  "mode": "browser",
  "minimum_success_count": 4,
  "providers": [
    {
      "provider": "doubao",
      "label": "豆包",
      "status": "blocked",
      "url": "https://www.doubao.com/chat/",
      "profile_dir": "/Users/bruce/Developer/work/AIRank-productization/.runtime/browser-profiles/doubao",
      "headless": true,
      "probe_level": "l3_generation",
      "generation_verified": false,
      "blocker_code": "login_required",
      "reason": "web page requires login",
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/doubao/d6/d6dbe68bdc0395c1d6de9fb39e0e59e201971d00412b0d5c4782b1f37ca8d60c.png"
    },
    {
      "provider": "qianwen",
      "label": "千问",
      "status": "blocked",
      "url": "https://www.qianwen.com/?ch=tongyi_redirect",
      "profile_dir": "/Users/bruce/Developer/work/AIRank-productization/.runtime/browser-profiles/qianwen",
      "headless": true,
      "probe_level": "l3_generation",
      "generation_verified": false,
      "blocker_code": "captcha_required",
      "reason": "web page returned login or human verification text instead of an answer",
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/qianwen/49/4991e0086b7e053c3d489d557cd6c2f3b888195600e338b73967db27a61b0819.png"
    },
    {
      "provider": "kimi",
      "label": "Kimi",
      "status": "blocked",
      "url": "https://www.kimi.com/",
      "profile_dir": "/Users/bruce/Developer/work/AIRank-productization/.runtime/browser-profiles/kimi",
      "headless": true,
      "probe_level": "l3_generation",
      "generation_verified": false,
      "blocker_code": "login_required",
      "reason": "web page requires login",
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/kimi/83/83d76913f3508c9155b1d29c163169e38d5052ba86dc1e193e7afc3e29ccb649.png"
    },
    {
      "provider": "deepseek",
      "label": "DeepSeek",
      "status": "blocked",
      "url": "https://chat.deepseek.com/sign_in",
      "profile_dir": "/Users/bruce/Developer/work/AIRank-productization/.runtime/browser-profiles/deepseek",
      "headless": true,
      "probe_level": "l3_generation",
      "generation_verified": false,
      "blocker_code": "captcha_required",
      "reason": "web page requires captcha verification",
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/deepseek/ff/ff68a3e0435a6d0e1e2e6712e61f61691dd134469d86bd410a88a584824f3862.png"
    }
  ]
}

Warnings:
- doubao=blocked (web page requires login)
- qianwen=blocked (web page returned login or human verification text instead of an answer)
- kimi=blocked (web page requires login)
- deepseek=blocked (web page requires captcha verification)

Blockers:
- browser_provider_ready=0/4
```


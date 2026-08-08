# AIRank Release Readiness Report

Generated: 2026-08-08T10:04:40+08:00
Result: BLOCKED

| Check | Status | Command |
| --- | --- | --- |
| working tree | PASS | `git status --short --branch` |
| origin main ref | BLOCKED | `git rev-parse HEAD && git ls-remote origin refs/heads/main` |
| gitee main ref | BLOCKED | `git rev-parse HEAD && git ls-remote gitee refs/heads/main` |
| diff check | PASS | `git diff --check` |
| tracked runtime artifacts | PASS | `git ls-files | rg "node_modules|dist|\\.runtime|\\.env|\\.sqlite|tsbuildinfo"` |
| API authentication configuration | PASS | `validate AIRANK_API_AUTH_ENFORCEMENT and AIRANK_AUTH_MODE` |
| production object storage configuration | PASS | `validate AIRANK_ENV and S3/MinIO transport configuration` |
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
| browser provider readiness | BLOCKED | `probe_provider_readiness(DEFAULT_PROVIDER_SCOPE)` |

## working tree

Status: PASS

```text
## codex/evidence-productization
```

## origin main ref

Status: BLOCKED

```text
local HEAD 5135ab4c4d4699e58e591d020df6164136f761ee does not match origin main 495655c47ee44dcab4f95df4fef9d6b79b6026cf
```

## gitee main ref

Status: BLOCKED

```text
local HEAD 5135ab4c4d4699e58e591d020df6164136f761ee does not match gitee main 495655c47ee44dcab4f95df4fef9d6b79b6026cf
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

Status: PASS

```text
{
  "AIRANK_API_AUTH_ENFORCEMENT": "required",
  "AIRANK_AUTH_MODE": "yudao",
  "required": {
    "AIRANK_API_AUTH_ENFORCEMENT": "required",
    "AIRANK_AUTH_MODE": "yudao"
  },
  "blockers": []
}
```

## production object storage configuration

Status: PASS

```text
{
  "AIRANK_ENV": "local",
  "AIRANK_OBJECT_STORAGE_DRIVER": "local",
  "endpoint_scheme": "provider-default",
  "allow_http": false,
  "blockers": []
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
........................................................................ [ 51%]
...................................................................      [100%]
139 passed in 1.27s
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
...................................................                      [100%]
51 passed in 0.58s
```

## worker tests

Status: PASS

```text
.........................                                                [100%]
25 passed in 0.12s
```

## score tests

Status: PASS

```text
............                                                             [100%]
12 passed in 0.03s
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
23 passed in 0.02s
```

## provider gateway tests

Status: PASS

```text
...................                                                      [100%]
19 passed in 0.03s
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
✓ built in 738ms
```

## real integration tests

Status: PASS

```text
....s...............s                                                    [100%]
19 passed, 2 skipped in 1.88s
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
    "status": "dev_only",
    "source": "yudao",
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
    "required_for_mvp": true,
    "endpoint": null,
    "blocked_reason": "AIRANK_AUTH_MODE=dev; using dev auth fallback",
    "fallback": "apps/api dev auth",
    "metadata": {
      "auth_mode": "dev"
    }
  },
  {
    "capability": "yudao_tenant_user",
    "status": "dev_only",
    "source": "yudao",
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
    "required_for_mvp": true,
    "endpoint": null,
    "blocked_reason": "AIRANK_AUTH_MODE=dev; using dev tenant/user fixture context",
    "fallback": "apps/api dev tenant context",
    "metadata": {
      "auth_mode": "dev"
    }
  },
  {
    "capability": "object_storage",
    "status": "dev_only",
    "source": "airank",
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
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
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
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
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
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
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
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
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
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
    "checked_at": "2026-08-08T02:04:00.796696+00:00",
    "required_for_mvp": false,
    "endpoint": null,
    "blocked_reason": "external endpoint is not configured",
    "fallback": "apps/worker scheduled jobs",
    "metadata": {}
  }
]

Blockers:
- yudao_auth=dev_only (AIRANK_AUTH_MODE=dev; using dev auth fallback)
- yudao_tenant_user=dev_only (AIRANK_AUTH_MODE=dev; using dev tenant/user fixture context)
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
      "blocker_code": "login_required",
      "reason": "login or human verification is visible",
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/doubao/46/46c4a03dffa00139a923baf8a1db940f3178d0b7b37fcd9825f2accdd44832fa.png"
    },
    {
      "provider": "qianwen",
      "label": "千问",
      "status": "ready",
      "url": "https://www.qianwen.com/?ch=tongyi_redirect",
      "profile_dir": "/Users/bruce/Developer/work/AIRank-productization/.runtime/browser-profiles/qianwen",
      "headless": true,
      "blocker_code": null,
      "reason": null,
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/qianwen/32/3255a8b54b0307cef13282682fb58c0e4785a43821fe659417b57d6f3f10ba0b.png"
    },
    {
      "provider": "kimi",
      "label": "Kimi",
      "status": "blocked",
      "url": "https://www.kimi.com/",
      "profile_dir": "/Users/bruce/Developer/work/AIRank-productization/.runtime/browser-profiles/kimi",
      "headless": true,
      "blocker_code": "login_required",
      "reason": "login or human verification is visible",
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/kimi/d0/d039e64f9b92c8167fff220577e44d0a410f950e0737b2d4a8f40f129799158c.png"
    },
    {
      "provider": "deepseek",
      "label": "DeepSeek",
      "status": "blocked",
      "url": "https://chat.deepseek.com/sign_in",
      "profile_dir": "/Users/bruce/Developer/work/AIRank-productization/.runtime/browser-profiles/deepseek",
      "headless": true,
      "blocker_code": "captcha_required",
      "reason": "login or human verification is visible",
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/deepseek/a8/a8f704784e32df3399b2b655b24c7620e1a5655d884c57a80a7efe4d9a45c295.png"
    }
  ]
}

Warnings:
- doubao=blocked (login or human verification is visible)
- kimi=blocked (login or human verification is visible)
- deepseek=blocked (login or human verification is visible)

Blockers:
- browser_provider_ready=1/4
```


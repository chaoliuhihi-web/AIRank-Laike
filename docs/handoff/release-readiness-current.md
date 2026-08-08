# AIRank Release Readiness Report

Generated: 2026-08-08T18:12:59+08:00
Result: BLOCKED

| Check | Status | Command |
| --- | --- | --- |
| working tree | PASS | `git status --short --branch` |
| origin main ref | PASS | `git rev-parse HEAD && git ls-remote origin refs/heads/main` |
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

Status: PASS

```text
cf1e5477823b4d831320120aa2a033f7a3d739d9
```

## gitee main ref

Status: PASS

```text
cf1e5477823b4d831320120aa2a033f7a3d739d9
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
........................................................................ [ 42%]
........................................................................ [ 84%]
...........................                                              [100%]
=============================== warnings summary ===============================
.runtime/api-py311/lib/python3.11/site-packages/fastapi/testclient.py:1
  /Users/bruce/Developer/work/AIRank-productization/.runtime/api-py311/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
171 passed, 1 warning in 1.89s
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
..............................................................           [100%]
=============================== warnings summary ===============================
.runtime/api-py311/lib/python3.11/site-packages/fastapi/testclient.py:1
  /Users/bruce/Developer/work/AIRank-productization/.runtime/api-py311/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
62 passed, 1 warning in 0.59s
```

## scheduler tests

Status: PASS

```text
.....                                                                    [100%]
5 passed in 0.25s
```

## worker tests

Status: PASS

```text
................................                                         [100%]
32 passed in 0.16s
```

## score tests

Status: PASS

```text
................                                                         [100%]
16 passed in 0.05s
```

## evidence tests

Status: PASS

```text
.....................................                                    [100%]
37 passed in 0.07s
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
.......................                                                  [100%]
23 passed in 0.04s
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
6 passed in 0.04s
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
dist/assets/index-C9MG4JGM.css   66.96 kB │ gzip:  11.12 kB
dist/assets/index-DDel3gBI.js   379.87 kB │ gzip: 114.17 kB
✓ built in 756ms
```

## real integration tests

Status: PASS

```text
.....s...................s..                                             [100%]
26 passed, 2 skipped in 3.81s
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
    "checked_at": "2026-08-08T10:12:02.643358+00:00",
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
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/doubao/f1/f14ad0a9e8fd7c43ad60ec0c89ea1ae719a49b56c33c4a362a3f95a46f9a75d9.png"
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
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/qianwen/c4/c4df4dc59537a7cba4a5c90ab4090151edd1bec4e3cbf4b92475fb69b9299138.png"
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
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/kimi/fe/fe146de7c143f428c0c4104dee50cc8f88a5a4da180d5810374d9e433f8f79c0.png"
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
      "screenshot_path": "/var/folders/xk/53c7rb5d5g3g0fgftczb8yr40000gn/T/airank-browser-captures/deepseek/e3/e34a345a2c3a1a345e892652b178de811c5b0b60b7afecfe468552930d856c5a.png"
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


# AIRank Release Readiness Report

Generated: 2026-08-08T20:10:31+08:00
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
| contract tests | BLOCKED | `python3 -m pytest tests/contracts -q` |
| crawler lite tests | BLOCKED | `python3 -m pytest packages/crawler-lite/tests -q` |
| acceptance tests | BLOCKED | `python3 -m pytest tests/acceptance -q` |
| scheduler tests | BLOCKED | `python3 -m pytest apps/scheduler/tests -q` |
| worker tests | BLOCKED | `cd apps/worker && python3 -m pytest -q` |
| score tests | BLOCKED | `cd packages/score && python3 -m pytest -q` |
| evidence tests | BLOCKED | `cd packages/evidence && python3 -m pytest -q` |
| outbound security tests | BLOCKED | `python3 -m pytest packages/outbound-security/tests -q` |
| provider gateway tests | BLOCKED | `python3 -m pytest packages/provider-gateway/tests -q` |
| core skill evaluation | BLOCKED | `python3 scripts/evaluate_core_skills.py` |
| xinghe adapter tests | BLOCKED | `cd packages/xinghe-adapter && python3 -m pytest -q` |
| web build | PASS | `cd apps/web && npm run build` |
| real integration tests | BLOCKED | `python3 -m pytest tests/integration -q` |
| alembic offline sql | BLOCKED | `cd apps/api && python3 -m alembic upgrade head --sql >/tmp/airank_release_alembic.sql` |
| alembic real mysql | BLOCKED | `cd apps/api && python3 -m alembic upgrade head` |
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
3c3e6ae7d9df3bb14efddd701fff983b1b714682
```

## gitee main ref

Status: PASS

```text
3c3e6ae7d9df3bb14efddd701fff983b1b714682
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

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## crawler lite tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## acceptance tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## scheduler tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## worker tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## score tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## evidence tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## outbound security tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## provider gateway tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## core skill evaluation

Status: BLOCKED

```text
Traceback (most recent call last):
  File "/Users/bruce/Developer/work/AIRank-productization/scripts/evaluate_core_skills.py", line 14, in <module>
    from airank_skills import build_promotion_ledger, evaluate_registry  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/bruce/Developer/work/AIRank-productization/packages/skills/src/airank_skills/__init__.py", line 4, in <module>
    from .evaluation import SkillEvaluationReport, build_promotion_ledger, evaluate_registry
  File "/Users/bruce/Developer/work/AIRank-productization/packages/skills/src/airank_skills/evaluation.py", line 9, in <module>
    from jsonschema import Draft202012Validator
ModuleNotFoundError: No module named 'jsonschema'
```

## xinghe adapter tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
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
dist/assets/index-5riTn7Pq.css   71.39 kB │ gzip:  11.65 kB
dist/assets/index-DLx2d2rj.js   396.80 kB │ gzip: 118.30 kB
✓ built in 738ms
```

## real integration tests

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named pytest
```

## alembic offline sql

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named alembic.__main__; 'alembic' is a package and cannot be directly executed
```

## alembic real mysql

Status: BLOCKED

```text
/Users/bruce/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3: No module named alembic.__main__; 'alembic' is a package and cannot be directly executed
```

## capability probe

Status: BLOCKED

```text
[
  {
    "capability": "yudao_auth",
    "status": "blocked",
    "source": "yudao",
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
    "checked_at": "2026-08-08T12:10:31.043332+00:00",
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
ModuleNotFoundError("No module named 'fastapi'")
```


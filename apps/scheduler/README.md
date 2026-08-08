# AIRank Scheduler

The scheduler turns due `T+7/T+14/T+30` observation windows into new durable
`ScanRun` tasks. It clones the baseline tasks' frozen prompt/request contract,
creates fresh sessions, and lets the normal governed Worker collect evidence.
When the comparison run reaches a terminal state, the next tick invokes the
existing quality-gated retest comparison and report path.

The scheduler is fail-closed: a tenant/project/window scope is required by
default. Global multi-tenant scheduling requires both
`AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED=true` and `--allow-global-scope`.

Read-only preview:

```bash
PYTHONPATH=.:apps/scheduler:apps/worker:packages/domain/src:packages/evidence/src:packages/crawler-lite/src:packages/outbound-security/src:packages/provider-gateway/src:packages/score/src:packages/skills/src:packages/xinghe-adapter/src \
  AIRANK_DATABASE_URL="$AIRANK_DATABASE_URL" \
  python3 -m airank_scheduler.main --tenant-id tenant_id --dry-run
```

One idempotent scheduler tick:

```bash
PYTHONPATH=.:apps/scheduler:apps/worker:packages/domain/src:packages/evidence/src:packages/crawler-lite/src:packages/outbound-security/src:packages/provider-gateway/src:packages/score/src:packages/skills/src:packages/xinghe-adapter/src \
  AIRANK_DATABASE_URL="$AIRANK_DATABASE_URL" \
  python3 -m airank_scheduler.main --tenant-id tenant_id --once
```

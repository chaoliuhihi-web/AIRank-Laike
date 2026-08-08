# AIRank Scheduler

The scheduler handles three durable workflows:

- turns due `T+7/T+14/T+30` observation windows into new `ScanRun` tasks;
- queues due knowledge-source synchronization jobs; and
- persists reviewer-SLA overdue events to `airank_outbox_events`.

Retest dispatch clones the baseline tasks' frozen prompt/request contract,
creates fresh sessions, and lets the normal governed Worker collect evidence.
When the comparison run reaches a terminal state, the next tick invokes the
existing quality-gated retest comparison and report path.

Reviewer escalation is intentionally narrower than external notification. The
event contract is `evidence_review.sla_overdue.v1` with payload schema
`airank.evidence-review-sla-escalation.v1`. Before insertion, the scheduler
locks and rechecks the case so a review completed after the initial scan does
not produce a stale escalation. A deterministic event ID makes replay
idempotent. `pending` means only that a durable Outbox event exists; even
`published` is not an external delivery receipt. Until a separate consumer and
channel receipt contract are implemented, customer UI/API must keep external
delivery unverified.

The scheduler is fail-closed: a tenant/project/window scope is required by
default. A project scope always requires a tenant scope. Global multi-tenant scheduling requires both
`AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED=true` and `--allow-global-scope`.
The reviewer scan additionally stops at 10,000 actionable cases per scope and
accepts at most 500 new events per tick.

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

# AIRank Scheduler

The scheduler handles five durable workflows:

- turns due `T+7/T+14/T+30` observation windows into new `ScanRun` tasks;
- queues due knowledge-source synchronization jobs; and
- persists reviewer-SLA overdue events to `airank_outbox_events`; and
- persists opportunity-action SLA overdue events to `airank_outbox_events`; and
- queues due Yudao reviewer-directory bindings as `reviewer.directory.sync` jobs.

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
`published` is accepted as external delivery only when the notification
Consumer has persisted a successful immutable channel receipt. A plain Outbox
row or failed attempt remains externally unverified.

Opportunity action escalation uses `opportunity_action.sla_overdue.v1` and
`airank.opportunity-action-sla-escalation.v1`. It re-locks the non-final action
before writing, freezes the team/route version and recipient count without
including owner/member identities, and records
`delivery_claim=outbox_pending_not_delivered` plus
`effect_claim_allowed=false`. The existing secure notification Consumer may
deliver either review or action events, but only a persisted 2xx receipt is
treated as externally delivered.

Reviewer-directory scheduling stores only binding IDs, versions, roles and the
external department ID. Service credentials remain in Worker process secrets.
The Worker rechecks the binding version before the Yudao call, so configuration
changes after dispatch fail closed instead of syncing the wrong group.

When reviewer routing is configured, the same transaction resolves a durable
route snapshot into the event: team ID, route version, eligible escalation
recipient count, and external-sync state. It never stores member identities in
the Outbox payload. No project routes means explicit `unrestricted_legacy`;
after the first route is configured, a missing role, inactive team, or empty
recipient set is recorded as a blocked routing state instead of falling back to
unrestricted delivery.

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

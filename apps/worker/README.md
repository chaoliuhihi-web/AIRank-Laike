# apps/worker

AIRank 异步任务。

任务类型：

- **scan** — AI 平台扫描和半自动采样导入
- **attribution** — 引用来源归因
- **fact-extract** — 资料到可信事实卡内部事实元（FactAtom）
- **content** — 内容资产生成，按 4 大类组织：
  - `website/` — 官网资产（事实页、服务页、案例页、FAQ、对比页、价格页、方案页）
  - `platform/` — 平台资产（公众号、知乎、小红书、视频号、百家号、行业媒体稿）
  - `schema/` — 结构化资产（JSON-LD、sitemap、robots、canonical）
  - `sales/` — 销售承接资产（销售 FAQ、异议处理、话术、成功故事、来客助手回答库）
- **publish** — 发布包生成和发布状态追踪
- **retest** — 复测
- **report** — 高管报告生成

任务失败必须有结构化原因，不能长期停留在 `queued`。

## M2 worker lease baseline

`airank_worker.InMemoryJobLeaseStore` is the deterministic local test
implementation. `airank_worker.MySQLJobLeaseStore` uses the production
`airank_async_jobs` table for claim, heartbeat, success, failure, timeout, and
explicit retry transitions.

State transitions covered by tests:

- `queued -> running` by `claim_next(worker_id, now)`
- `running -> running` by heartbeat refresh
- `running -> succeeded` when the handler completes
- `running -> failed` with structured `error_code` and `error_message`
- `running -> timeout` when `heartbeat_at + timeout_seconds <= now`

Failed and timed-out jobs are terminal by default. They do not silently return to
`queued`; retry requires an explicit `requeue_for_retry` call and remaining
attempts.

`claim_next(..., job_types={...})` lets each handler claim only the job types it
can execute. This prevents a publish-only worker from consuming scan jobs.

## Governed HTTP / WordPress publisher

`airank_worker.publisher` executes only immutable, approved publish snapshots.
It requires an explicit `AIRANK_PUBLISH_ALLOWED_HOSTS` allowlist, credential-free
HTTPS URLs, public DNS addresses, and process-environment credentials. Generic
HTTP uses `Idempotency-Key`; WordPress first looks up a deterministic slug before
creating a post. Request and response bodies are represented in MySQL by SHA-256
receipts, not credentials or raw authorization headers.

Successful transport changes the package to `delivered`. It does not create
retest windows or claim publication evidence. The separate publication-evidence
API must bind a completed T0 run and optional screenshot before the package
becomes `published`.

Run one publish job:

```bash
PYTHONPATH=apps/worker:packages/domain/src:packages/crawler-lite/src:packages/outbound-security/src \
  python3 -m airank_worker.main --once
```

Omit `--once` for the polling process. A failed job records a structured attempt
and remains terminal until an explicit retry transition.

Run one durable scan dispatch:

```bash
PYTHONPATH=.:apps/worker:packages/domain/src:packages/evidence/src:packages/crawler-lite/src:packages/outbound-security/src:packages/provider-gateway/src:packages/score/src:packages/skills/src \
  AIRANK_DATABASE_URL="$AIRANK_DATABASE_URL" \
  python3 -m airank_worker.main --job-type scan --once
```

Every `scan.provider` job owns exactly one versioned sampling slot. Multiple
workers may process different slots from the same ScanRun concurrently. A slot
persists its AnswerSnapshot, EvidenceSnapshot, native citations, Provider audit,
job state and immutable `airank_scan_task_attempts` row in one database
transaction; completed sibling evidence therefore survives a process crash.
Run metrics are recomputed only from durable rows after every task is terminal.

The attempt ledger records the job, attempt number, worker lease, timestamps,
outcome and linked evidence IDs. A timed-out call whose external outcome is
unknown is never replayed automatically: only that slot receives
`SCAN_TASK_LEASE_EXPIRED`, an empty-answer immutable failure snapshot and an
`unknown` attempt. Requeuing an already-terminal job is an idempotent replay and
does not call the Provider again. Dedicated workers/tests may pass a tenant
scope; the production CLI processes all tenants.

## M2 mock scan provider

`airank_worker.scan.run_next_mock_scan_job` claims the next due job and uses
`packages/evidence` `MockAnswerProvider` to generate an answer snapshot plus
source citations. Missing citation payloads fail the job with a structured error
instead of returning it to `queued`.

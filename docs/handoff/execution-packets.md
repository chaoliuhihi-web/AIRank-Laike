# AIRank Execution Packets

本文件把 `launch-board` 里的里程碑拆成可并行领取的最小执行包。这里是任务定义，不是高频状态台账；CodexWin、CodexiMac、CodexMacPro 的实际执行状态写到 `docs/handoff/status/<owner>.md`，降低并行 rebase 冲突。

## Status

```text
todo
in_progress
review
blocked
review_env_blocked
dev_only
partial
done
```

## 冲突规则

1. 每轮只领取一条 `Actionable Tasks` 里的 packet；如果某条 packet 依赖未满足，跳过它继续找同 owner 的下一条可执行 packet。
2. CodexWin 和 CodexiMac 不直接改本文件状态；完成、阻塞、环境阻塞写入自己的 `docs/handoff/status/<owner>.md`。
3. 只修改 `File Scope` 内的文件；需要改其它路径时，先在自己的 status 文件写明原因并交给 CodexMacPro。
4. 任何 public contract 变更必须同时更新 `packages/contracts` 和对应 contract test。
5. 数据库结构由 CodexiMac owner，API 调用语义由 CodexWin owner，跨界改动必须以 mock/fallback 或 contract 方式衔接。
6. CodexMacPro 不抢主链实现，只做 gate、测试、review 和 blocker 小修。
7. 如果代码产物已完成，但本地 MySQL、外部服务、推送凭据等环境问题导致无法完成最终验证，状态用 `review_env_blocked`，不等同于业务代码 `blocked`；依赖方可以基于已入库代码继续做 contract/mock 层工作，但不能声明完整上线通过。
8. 开发加速优先：如果生产依赖未 ready，允许先做 contract skeleton、repository interface、in-memory/dev-only adapter、mock provider、UI fallback 和 acceptance skeleton；这些成果必须标记 `dev_only` 或 `review_env_blocked`，可以解锁后续开发，但不能冒充 release ready。

## M1 API + DB 最小主链

| ID | Owner | Status | Depends | File Scope | Acceptance | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| M1-WIN-001 health-version-envelope | CodexWin | done | `cf20229` API baseline | `apps/api`, `packages/contracts`, `tests/contracts` | `/api/v1/health` 和 `/api/v1/version` 返回统一 envelope、`trace_id`、版本信息；`console/overview` 不回归 | `python3 -m pytest tests/contracts` |
| M1-WIN-001B error-trace-foundation | CodexWin | todo | `M1-WIN-001` | `apps/api`, `packages/contracts`, `tests/contracts` | 错误响应使用统一 envelope、registry code 和 trace_id；公共 API 不回归 | `python3 -m pytest tests/contracts` |
| M1-WIN-001C project-question-contract-skeleton | CodexWin | todo | `M1-WIN-001B` | `packages/contracts`, `tests/contracts`, `docs/handoff` | project、competitor、buyer question 的 request/response JSON Schema 和 contract tests 先冻结，不实现 DB 持久化 | `python3 -m pytest tests/contracts` |
| M1-IMAC-001 alembic-initial-schema | CodexiMac | todo | `ops/deployment/mysql-bootstrap.sql` | `apps/api/alembic`, `ops/deployment`, `docs/handoff` | `alembic upgrade head` 可从空库建 AIRank schema，字段与 bootstrap SQL 关键表一致 | `alembic upgrade head` 或写明本地 MySQL 不可用原因 |
| M1-MACPRO-001 stage-review-current-head | CodexMacPro | todo | `b6c5458` | `docs/handoff`, `.github/workflows`, `tests` | 审核 `cf20229`、`a4de530`、`b6c5458` 是否偏离主线，并在 `review-ledger` 写 PASS/BLOCKED/PASS_WITH_RISK | `git diff --check`; `python3 -m pytest tests/contracts`; `cd apps/web && npm run build` |
| M1-WIN-001D project-question-dev-repository | CodexWin | todo | `M1-WIN-001C` | `apps/api`, `packages/contracts`, `tests/contracts`, `docs/handoff/status/codex-win.md` | project、competitor、buyer question API 先接 repository interface + in-memory/dev-only adapter，明确不作为生产持久化；contract tests 可跑 | `python3 -m pytest tests/contracts` |
| M1-WIN-002 project-competitor-question-crud-contract | CodexWin | todo | `M1-WIN-001D`, `M1-IMAC-001` | `apps/api`, `packages/contracts`, `tests/contracts` | 将 dev repository 切到 Alembic/MySQL 持久化，CRUD 带 tenant 过滤；错误响应有 registry code 和 trace_id | `python3 -m pytest tests/contracts` |
| M1-IMAC-002 schema-index-tenant-review | CodexiMac | todo | `M1-IMAC-001` | `ops/deployment`, `docs/architecture`, `docs/handoff` | 业务表 tenant/project 查询字段、索引、敏感字段和不跨库外键策略明确 | `git diff --check` |

## M2 扫描 + 评分闭环

| ID | Owner | Status | Depends | File Scope | Acceptance | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| M2-WIN-000 scan-run-contract-skeleton | CodexWin | todo | `M1-WIN-001C` | `packages/contracts`, `tests/contracts`, `docs/handoff/status/codex-win.md` | scan run / scan task 的 request/response/status JSON Schema 先冻结，不实现 worker 调度 | `python3 -m pytest tests/contracts` |
| M2-WIN-001 scan-run-api-contract | CodexWin | todo | `M1-WIN-002` | `apps/api`, `packages/contracts`, `tests/contracts` | 可创建 scan run、查询 run/task 状态；不直接实现 worker 调度 | `python3 -m pytest tests/contracts` |
| M2-IMAC-001 async-job-lease-heartbeat | CodexiMac | todo | `M1-IMAC-001` | `apps/worker`, `packages/domain`, `ops/deployment`, `tests/acceptance` | queued/running/succeeded/failed/timeout 状态可复测，失败不长期停在 queued | `cd apps/worker && pytest` 或写明初始化缺口 |
| M2-IMAC-002 mock-provider-snapshot-citation | CodexiMac | todo | `M2-IMAC-001` | `apps/worker`, `packages/evidence`, `tests/acceptance` | mock/manual provider 能生成 answer snapshot 和 source citation | `cd apps/worker && pytest` |
| M2-IMAC-003 score-pure-function | CodexiMac | todo | `M2-IMAC-002` | `packages/score`, `tests/acceptance` | 同一 snapshot/citation 输入重复计算 AIRank Score 一致 | `cd packages/score && pytest` |
| M2-MACPRO-001 scan-score-acceptance | CodexMacPro | todo | `M2-WIN-001`, `M2-IMAC-003` | `tests/acceptance`, `docs/handoff` | 从项目到 score 的测试可复现，失败时定位到 owner | `python3 -m pytest tests/acceptance` |

## M3 事实链 + AI 收录包

| ID | Owner | Status | Depends | File Scope | Acceptance | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| M3-IMAC-001 fact-atom-domain | CodexiMac | todo | `M2-IMAC-002` | `packages/domain`, `packages/evidence`, `tests/acceptance` | FactAtom 必须关联 source/citation，不允许无来源 confirmed fact | `cd packages/evidence && pytest` |
| M3-WIN-001 fact-review-api | CodexWin | todo | `M1-WIN-001B`, `M3-IMAC-001` | `apps/api`, `packages/contracts`, `tests/contracts` | fact 支持 confirmed/rejected/needs_redaction/private 状态流转 | `python3 -m pytest tests/contracts` |
| M3-IMAC-002 content-gap-generation | CodexiMac | todo | `M3-IMAC-001` | `packages/domain`, `packages/evidence`, `tests/acceptance` | gap 可追溯到 question、citation、FactAtom | `python3 -m pytest tests/acceptance` |
| M3-WIN-002 ai-inclusion-package-api | CodexWin | todo | `M3-WIN-001`, `M3-IMAC-002` | `apps/api`, `apps/web`, `packages/contracts`, `tests/contracts` | 前端 AI 收录包页面读取真实资产 API，不用硬编码 demo 数据 | `python3 -m pytest tests/contracts`; `cd apps/web && npm run build` |
| M3-MACPRO-001 evidence-chain-review | CodexMacPro | todo | `M3-WIN-002` | `docs/handoff`, `tests/acceptance` | 无来源内容不能进入报告或收录包 | `python3 -m pytest tests/acceptance` |

## M4 报告 + 前端真实闭环 + Beta

| ID | Owner | Status | Depends | File Scope | Acceptance | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| M4-IMAC-001 report-evidence-json | CodexiMac | todo | `M3-IMAC-002` | `packages/evidence`, `tests/acceptance` | 报告 JSON 每个结论可回溯到 snapshot/citation/FactAtom | `python3 -m pytest tests/acceptance` |
| M4-IMAC-002 xinghe-yudao-capability-probe | CodexiMac | todo | `M4-IMAC-001` | `packages/xinghe-adapter`, `tests/acceptance`, `docs/architecture` | adapter capability probe 输出 ready/partial/blocked/dev_only 状态，覆盖 yudao auth、tenant/user 基础能力、object storage 和 Xinghe/Hermes 可选能力 | `python3 -m pytest tests/acceptance` 或写明外部能力不可用原因 |
| M4-WIN-001 report-api-download-receipt | CodexWin | todo | `M3-WIN-002`, `M4-IMAC-001` | `apps/api`, `apps/web`, `packages/contracts`, `tests/contracts` | 报告中心可查看真实报告并记录 download receipt | `python3 -m pytest tests/contracts`; `cd apps/web && npm run build` |
| M4-WIN-002 console-fixture-to-api | CodexWin | todo | `M1-WIN-002`, `M2-WIN-001`, `M4-WIN-001` | `apps/web`, `packages/contracts`, `tests/contracts` | 控制台主页面不再依赖硬编码 demo 数据，API 不可用时有明确 fallback 状态 | `cd apps/web && npm run build`; `python3 -m pytest tests/contracts` |
| M4-MACPRO-001 beta-release-gate | CodexMacPro | todo | `M4-WIN-002`, `M2-MACPRO-001`, `M3-MACPRO-001` | `docs/handoff`, `tests`, `.github/workflows` | `release-gate.md` 全部执行，有 PASS/BLOCKED/PASS_WITH_RISK 最终结论 | `docs/handoff/release-gate.md` 全量 checklist |

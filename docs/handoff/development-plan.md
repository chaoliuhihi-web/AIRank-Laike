# AIRank 持续开发计划

## 当前阶段

阶段：工程骨架、数据库方案、整合边界冻结。

已确认：

- `AIRank素材/` 包含官网宣传、控制台视觉和 PRD v0.1 素材。
- AIRank 应独立成仓，不进入 `XingheAI2026V2` 主仓。
- `XingheAI2026V2` 已同步 `origin/main`，可作为 yudao、Crawler Gateway、KB、Brand Corpus、trace、Hermes 等能力参考。
- GitHub/Gitee `AIRank-Laike` 远端当前无默认分支输出，本地已初始化 `main` 并配置双远端。
- yudao 和 XingheAI2026V2 能支撑 AIRank 开发，但不足以替代 AIRank 自有 MySQL 主库。
- 其它 AI 的工程化意见基本合理：Alembic、API 约定、错误码、trace_id、structured logging、CI 应进入 M0/M1；事件总线进入 M2，不阻塞 M1 编码。

## 开发入口

后续每个开发 Agent 进入仓库后先做：

```bash
cd /Users/bruce/Developer/work/AIRank
git fetch origin
git merge --ff-only origin/main
```

如果远端仍为空，第一次提交前 `git fetch` 和 `merge` 可能没有可合并内容，这是预期状态。

本地开发顺序：

```bash
mysql -uroot -p < ops/deployment/mysql-bootstrap.sql
set -a
source ops/deployment/env.example
set +a
```

后续正式工程化时再补：

```text
apps/api          FastAPI 或 NestJS API
apps/worker       异步扫描和内容任务
apps/web          企业控制台和官网
packages/domain   领域模型
packages/contracts JSON Schema / OpenAPI
packages/xinghe-adapter yudao / Xinghe 能力接入
```

## 基础能力结论

| 基础能力 | 是否足够 | 开发决策 |
| --- | --- | --- |
| yudao auth / tenant / permission | 足够 | `apps/api` 第一版直接接 yudao token，AIRank 保存 binding |
| yudao model / api key | 部分足够 | 可读 `/ai/model/resolve`，但 AIRank 自己做场景路由、预算和审计 |
| yudao knowledge / workflow | 不足以当 AIRank 主链 | 可做后续导入和增强，不阻塞 MVP |
| Xinghe Crawler Gateway | 部分足够 | 复杂抓取增强使用；MVP 保留 `crawler-lite` |
| Xinghe KB Service / Qdrant | 部分足够 | 后续替换检索；MVP 先 MySQL + `kb-lite` |
| Brand Corpus / report evidence | 可借鉴 | 复用流程模式，不复制业务表 |
| Hermes / workflow-runner | 可增强 | 后续做周期复测和自动化运营 |

详细评估见：

- `docs/architecture/capability-assessment.md`
- `docs/architecture/mysql-schema-plan.md`

## 数据库建设

第一版使用独立 MySQL：

```text
airank_laike
```

必须先落这些业务闭环：

1. 租户与用户绑定：`airank_tenant_bindings`、`airank_user_bindings`
2. 企业品牌项目：`airank_projects`
3. 竞品：`airank_competitors`
4. AI 来客问题：`airank_buyer_questions`
5. 扫描批次和任务：`airank_scan_runs`、`airank_scan_tasks`
6. 回答快照和引用：`airank_answer_snapshots`、`airank_source_citations`
7. 可信事实卡内部事实单元：`airank_fact_atoms`、`airank_fact_sources`
8. 内容缺口和内容资产：`airank_content_gaps`、`airank_content_assets`
9. 发布包、复测、报告：`airank_publish_packages`、`airank_retest_runs`、`airank_reports`
10. 对象、任务、能力状态、审计：`airank_object_refs`、`airank_async_jobs`、`airank_integration_capabilities`、`airank_audit_events`

建库脚本：

```text
ops/deployment/mysql-bootstrap.sql
```

## 第一阶段：10 天开发基线

目标：把“录入品牌项目 -> 生成问题 -> 扫描 -> 计算分数 -> 形成诊断报告”跑通。

### Day 1-2：API 和数据库

- 选定后端技术栈，优先 FastAPI + SQLAlchemy + Alembic，原因是能直接复用 XingheAI2026V2 的 Python 能力和 adapter 写法。
- 初始化 `apps/api`。
- 建立 Alembic `0001_initial_airank_schema`，与 `ops/deployment/mysql-bootstrap.sql` 对齐。
- 接入 `AIRANK_DATABASE_URL`。
- 接入 yudao bearer token 校验。
- 固化 `/api/v1`、统一响应 envelope、错误码和 idempotency 规则。
- 所有请求生成或透传 `trace_id`，结构化日志至少包含 `trace_id`、`tenant_id`、`project_id`、`actor_user_id`。
- 实现项目、竞品、问题 CRUD。
- 每个接口必须带 `tenant_id` 过滤。

验收：

- 能用 yudao token 创建一个项目。
- 能录入 3 个竞品和 50 个问题。
- 不能跨租户读取数据。

### Day 3-4：worker 和扫描任务

- 初始化 `apps/worker`。
- 用 `airank_async_jobs` 领取任务，并实现 `heartbeat_at`、`timeout_seconds` 和超时回收。
- 实现 `scan_run.create`，按问题和 provider 拆 `scan_tasks`。
- 第一版 provider 可以先做手动导入 / mock provider / 可配置 LLM provider 三种。
- 保存 `answer_snapshots` 和 `source_citations`。

验收：

- 一个项目能产生完整 scan run。
- 每个问题都有 provider、状态、错误原因和快照。
- 失败任务不能长期停留 `queued`。

### Day 5：AIRank Score

- 实现 `packages/score`。
- 指标至少包括品牌提及率、推荐排名、竞品压制、引用质量、事实覆盖、内容缺口。
- 分数计算必须可复现，输入来自 MySQL 快照。

验收：

- 同一批快照重复计算分数一致。
- 报告能解释分数来源。

### Day 6-7：事实卡和内容缺口

- 实现 `packages/domain/src/fact-atom` 到 MySQL 的映射。
- 从回答快照和引用里提取候选 FactAtom。
- Review Console 或 API 支持确认 / 驳回 / 标记过期。
- 生成 `content_gaps`。

验收：

- 客户侧页面显示“可信事实卡”，工程内部使用 `FactAtom`。
- 每个 FactAtom 至少能追溯到一个来源。

### Day 8：报告和证据包

- 实现 `packages/evidence`。
- 生成诊断报告 JSON。
- 生成 source index、answer snapshot index、download receipt。
- 报告文件写 `airank_object_refs`。

验收：

- 报告每个关键结论都能追溯到 scan run / snapshot / citation。
- 下载回执可审计。

### Day 9：Web 控制台最小闭环

- 按素材里的控制台方向搭页面。
- 前端默认 React + Vite + SPA，不使用 Next.js 作为第一版默认栈。
- 先做真实工作流，不做空 marketing 页。
- 页面包括：项目、竞品、问题、扫描、事实卡、内容缺口、报告。

验收：

- 真实用户从建项目到看报告不需要手工改数据库。
- 如果前端未完成，M1 可以先用 API + CLI 跑通主链，Web 不作为 M1 硬 blocker。

### Day 10：Xinghe adapter status

- 实现 `packages/xinghe-adapter/status`。
- 探测 yudao auth、yudao model resolve、Crawler Gateway、KB Service、Hermes。
- 状态写入 `airank_integration_capabilities`。

验收：

- 页面或 API 能展示每项外部能力状态。
- 外部能力不可用时，主链仍可跑。

## 第二阶段：20-30 天可收费 MVP

目标：让企业品牌方可以付费使用第一版诊断和增长闭环。

重点任务：

- 多 provider 扫描：ChatGPT、DeepSeek、Kimi、豆包、通义等先按可用 API / 半自动策略接入。
- 问题地图：支持行业模板、竞品扩展、购买意图分层。
- 竞品压制：输出竞品为什么被推荐、引用了哪些来源、品牌缺什么证据。
- 内容资产：FAQ、选型指南、案例页三类内容。
- 发布包：导出 Markdown / HTML / CMS handoff 包，记录发布 URL。
- 复测：同一批问题复测，输出变化。
- 高管报告：可下载，可追溯，可解释。
- 事件解耦：引入 MySQL outbox 分发 `scan.completed`、`fact_atom.confirmed`、`content_asset.generated`、`report.generated`。

## 第三阶段：接入 XingheAI2026V2 增强能力

只有当第一阶段 MySQL 主链稳定后再做替换：

1. Crawler Gateway 替换复杂抓取。
2. KB Service / Qdrant 替换事实检索。
3. Brand Corpus 增强品牌资料审校和导出。
4. Hermes 做周期复测、异常巡检和自动报告。
5. workflow-runner 做跨服务长任务编排。

每次替换必须保留 fallback，并在 `airank_integration_capabilities` 记录状态。

## 多 Agent 分工

最新可执行协作入口：

- `agents/prompts/codex-win.md`
- `agents/prompts/codex-imac.md`
- `agents/prompts/codex-macpro.md`
- `docs/handoff/launch-board.md`
- `docs/handoff/release-gate.md`
- `docs/handoff/review-ledger.md`

### Dev Agent

负责：

- `apps/api`
- `apps/web`
- `apps/worker`
- `packages/domain`
- `packages/score`
- `packages/evidence`
- `packages/kb-lite`
- `packages/crawler-lite`

禁止：

- 直接改 `XingheAI2026V2`
- 直接复制主仓业务代码
- 跳过 contracts 写页面假数据
- 把 AIRank 表建进 yudao 数据库

### Review Agent

负责：

- `apps/review-console`
- `tests/acceptance`
- `tests/contracts`
- `docs/decisions`
- `packages/xinghe-adapter/status`

重点检查：

- AIRank 是否仍可独立部署
- MySQL 表是否带 tenant 过滤
- yudao / Xinghe 能力状态是否真实
- 扫描快照和引用证据是否可复测
- 内容生成是否基于可信事实卡 / FactAtom
- 发布与报告是否有证据包

## 每轮固定动作

```text
git fetch origin
git merge --ff-only origin/main
实现或审核一个小闭环
运行相关测试
更新 docs/handoff
提交
git push origin main
git push gitee main
```

如果远端仍为空仓，首次提交后再执行双远端 push。

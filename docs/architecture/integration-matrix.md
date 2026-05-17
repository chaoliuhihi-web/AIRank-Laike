# XingheAI2026V2 能力接入矩阵

| AIRank 能力 | AIRank 自有实现 | XingheAI2026V2 增强 | 默认策略 |
| --- | --- | --- | --- |
| 账号 / 租户 | 单租户或轻量账号 | yudao-server / yudao-module-ai | MVP 自有，企业化再接 yudao |
| 模型配置 | 环境变量或项目级 provider config | yudao 模型与 API Key 权威源 | MVP 自有，接入时只读星河权威源 |
| 官网抓取 | `crawler-lite` HTTP + sitemap + 人工补录 | Crawler Gateway fetch/job/run/audit/version | MVP 自有，复杂抓取接 Crawler Gateway |
| 竞品/第三方信源抓取 | `crawler-lite` | Crawler Gateway connector + blocked taxonomy | 先半自动，逐步增强 |
| 事实库 | `kb-lite` SQL + 简单检索 | KB Service / Qdrant / Brand Corpus | AIRank 主存自有，向量召回可替换 |
| 可信事实卡 | `packages/domain/src/fact-atom` | Brand Corpus 审校队列和导出经验 | 客户侧叫事实卡，工程内部用 FactAtom；审校模式复用 |
| AI 平台扫描 | worker + provider plugins + 人工录入 | Hermes / browser automation / workflow-runner | MVP 自有，自动化增强后接 Hermes |
| AIRank Score | `packages/score` | AIScore 治理经验 | 算法自有，治理口径借鉴 |
| 证据包 | `packages/evidence` | Creator Marketing report evidence/source-index/download receipts | 数据结构自有，下载回执模式复用 |
| 内容生成 | worker content job | 智能出版 / Brand Corpus 内容工厂 | MVP 先自有 prompt，后接内容工厂 |
| 审校 | `apps/review-console` | 出版审校和营销 audit 模式 | 自有页面，复用审校维度 |
| 发布包 | `apps/worker/jobs/publish` | 出版导出、营销发布回执 | 自有导出，复用证据与回执结构 |
| 复测 | `apps/worker/jobs/retest` | Hermes cron / workflow-runner | MVP 自有，周期化接 Hermes |

## 接口层形态

`packages/xinghe-adapter` 只暴露 AIRank 需要的业务语义：

```text
auth.resolveUser()
auth.resolveTenant()
model.resolveModelRoute()
crawler.fetchUrl()
crawler.createJob()
kb.ingestFacts()
kb.searchFacts()
brandCorpus.exportBundle()
workflow.createRun()
content.generateAsset()
hermes.scheduleRetest()
status.getCapabilityMatrix()
```

adapter 内部可以调用星河 API，但 `apps/api`、`apps/worker` 和 `packages/domain` 不知道星河内部路径。

## 状态治理

每个 adapter 必须提供：

- `status`
- `checked_at`
- `required_for_mvp`
- `fallback`
- `blocked_reason`
- `last_success_trace_id`

失败时返回结构化错误，不能吞错，也不能让任务长期停留在 `queued`。

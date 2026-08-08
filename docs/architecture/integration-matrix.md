# XingheAI2026V2 能力接入矩阵

| AIRank 能力 | AIRank 自有实现 | XingheAI2026V2 增强 | 默认策略 |
| --- | --- | --- | --- |
| 账号 / 租户 | 单租户或轻量账号 | yudao-server / yudao-module-ai | MVP 自有，企业化再接 yudao |
| 模型配置 | 环境变量或项目级 provider config | yudao 模型与 API Key 权威源 | MVP 自有，接入时只读星河权威源 |
| 官网抓取 | `crawler-lite` HTTP + sitemap + 人工补录 | Crawler Gateway fetch/job/run/audit/version | MVP 自有，复杂抓取接 Crawler Gateway |
| 竞品/第三方信源抓取 | `crawler-lite` | Crawler Gateway connector + blocked taxonomy | 先半自动，逐步增强 |
| 事实库 | `kb-lite` SQL + 不可变来源版本 + `lexical_only` 当前有效切片检索 | KB Service / Qdrant / Brand Corpus | AIRank 主存和版本治理自有；向量/混合召回未配置时必须显式降级，不得冒充已接入 |
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

## 外部 AI Provider 执行规则

`AIRANK_PROVIDER_MODE=browser` 是 MySQL 环境的默认生产策略。品牌检测不能用模型 API 代替 C 端网页结果；必须通过 Playwright 持久浏览器 profile 打开各平台消费端页面，像用户一样输入问题，读取页面回答，再落库为 `answer_snapshot`。如果网页要求登录、真人验证、验证码，或找不到输入框，对应样本标记为 `blocked`，任务错误码为 `SCAN_PROVIDER_BLOCKED`；网络、上游、解析错误标记为 `failed`，超时与普通失败分别使用 `SCAN_PROVIDER_TIMEOUT`、`SCAN_PROVIDER_FAILED`。两类样本都保存不可变失败快照，但不会进入品牌回答分母。

生产模式默认要求当前 provider scope 全部完成，`AIRANK_MIN_PROVIDER_SUCCESS_COUNT` 只允许在明确标注“部分平台 beta”的环境下下调。未达到门槛时，`/api/v1/brand-checks` 返回 `INTEGRATION_CAPABILITY_BLOCKED`，不生成可下载报告、发布资料包或项目 active 状态，避免把不完整网页采样包装成上线结果。

部署前必须调用：

```text
GET /api/v1/provider-readiness
```

该接口会逐个打开消费端网页，检查当前持久浏览器 profile 是否具备可输入问题的状态。返回 `blocked` 时需人工在对应 `profile_dir` 登录、通过真人验证或更新 provider URL 后再发布。

接口必须同时返回 `probe_level` 与 `generation_verified`：网页入口和输入框探测只能标记 `l2_interaction`，只有真实提交并取得生成结果才能标记 `l3_generation`。L2 通过不能写成平台可采样或商业就绪。

API Provider 的系统管理员路由控制使用：

```text
GET /api/v1/admin/provider-routes
PUT /api/v1/admin/provider-routes/{provider}/{route_id}
```

两者要求可信 `airank:provider:admin` 权限。写操作必须提交 `expected_version` 和 `reason`；只允许调整运行时已安全注入凭证的路由，禁止停用最后一路。数据库只保存公开 host/model/priority、单向配置指纹和追加式控制事件，不保存 API Key。

| Provider | 默认网页入口 | 真实运行要求 |
| --- | --- | --- |
| ChatGPT | `https://chatgpt.com/` | 持久浏览器 profile 中有可用登录态 |
| DeepSeek | `https://chat.deepseek.com/` | 持久浏览器 profile 中有可用登录态 |
| Kimi | `https://www.kimi.com/` | 持久浏览器 profile 中有可用登录态 |
| 通义 | `https://www.tongyi.com/qianwen/` | 持久浏览器 profile 中有可用登录态 |
| 豆包 | `https://www.doubao.com/chat/` | 持久浏览器 profile 中有可用登录态 |
| 百度 AI 搜索 | `https://chat.baidu.com/` | 持久浏览器 profile 中有可用登录态 |
| 腾讯元宝 | `https://yuanbao.tencent.com/` | 持久浏览器 profile 中有可用登录态 |

API 调用可以形成独立的 `provider_api` 测量报告，但只能表示 Provider API 表面的回答可见度，不能冒充消费端 Web/App 排名。API、Web、App 必须分开汇总、分开显示证据等级；对客报告若使用 API 样本，标题、口径和限制项都必须明确。消费端排名证据链仍必须保存 provider、网页 URL、截图对象、原始网页回答、会话隔离证明、brand_rank 和 competitor_mentions。

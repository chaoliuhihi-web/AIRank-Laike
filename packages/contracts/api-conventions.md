# AIRank API 约定

## 版本

第一版 API 统一使用：

```text
/api/v1
```

不提供无版本 API。后续破坏性变更进入 `/api/v2`。

## 认证

登录入口：

```text
POST /api/v1/auth/login
```

请求使用 `auth_login_request.schema.json`，响应使用 `auth_login_response.schema.json`。默认模式调用 yudao
`/admin-api/system/auth/login` 后再调用 `/admin-api/system/auth/get-permission-info` 解析用户；本地演示可显式设置
`AIRANK_AUTH_MODE=dev_only`，响应会标记 `dev_only=true`，不能冒充 release-ready。

请求头：

```text
Authorization: Bearer <yudao-token>
tenant-id: <tenant-id>
X-AIRank-Trace-Id: <optional-trace-id>
Idempotency-Key: <optional-key>
```

`tenant-id` 必须与 yudao token 解析出的租户一致。

## 响应格式

成功：

```json
{
  "data": {},
  "meta": {
    "trace_id": "trc_...",
    "request_id": "req_..."
  }
}
```

失败：

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invalid request",
    "details": {},
    "trace_id": "trc_..."
  }
}
```

## 分页

列表接口使用 cursor pagination：

```text
GET /api/v1/projects?limit=50&cursor=...
```

响应：

```json
{
  "data": [],
  "page": {
    "next_cursor": "next...",
    "has_more": true
  },
  "meta": {
    "trace_id": "trc_..."
  }
}
```

## M1 项目 / 竞品 / 买家问题

M1 问题治理通过同一套 repository 契约支持测试内存实现与生产 MySQL 持久化：

| Route | 说明 |
| --- | --- |
| `POST /api/v1/projects` | 根据网站和可选 hint 创建待确认项目，返回 `project_response.schema.json` |
| `POST /api/v1/projects/{project_id}/competitors` | 给项目追加候选竞品，返回 `competitor_response.schema.json` |
| `POST /api/v1/projects/{project_id}/buyer-questions` | 给项目追加候选买家问题，返回 `buyer_question_response.schema.json` |
| `POST /api/v1/projects/{project_id}/question-observation-batches` | 导入客户授权的 M1 观察记录；请求/响应分别使用 `question_observation_import_request.schema.json` 与 `question_observation_import_response.schema.json` |
| `GET /api/v1/projects/{project_id}/question-observation-batches` | 查询不可变观察批次、来源元数据、hash、可用记录/频次与 PII 阻断统计 |
| `GET /api/v1/projects/{project_id}/question-observation-batches/{batch_id}/records` | 查询批次内已通过 PII 门禁的安全问题记录；不返回被拦截原文 |
| `POST /api/v1/projects/{project_id}/question-maps/compile` | 预览或持久化版本化问题地图；持久化候选初始状态为 `suggested` |
| `GET /api/v1/projects/{project_id}/question-maps` | 查询不可变编译清单、输入/输出 hash 与编译统计 |
| `PATCH /api/v1/projects/{project_id}/buyer-questions/{question_id}/review` | 追加人工审核事件，并更新当前生命周期状态；不覆盖问题修订 |

`tenant_id`、导入人和审核人必须来自认证上下文，不能信任 request body。观察导入要求显式来源授权声明，按 payload SHA-256 幂等；`occurrence_count` 只表示来源内频次，不等于搜索量。疑似 PII 原文不得进入持久化记录、manifest 或响应。问题地图按输入内容和 taxonomy 版本幂等；问题按规范化 hash 去重。只有 `confirmed` 且其不可变修订 Cohort 与 ScanRun 完全一致的问题才能进入任务编译。in-memory adapter 只用于 contract test 和本地开发，MySQL 路径由 Alembic `20260808_0010` 支持。

## M2 扫描契约

`M2-WIN-000` 只冻结 scan run / scan task 的 request、response 和 status schema，不实现 worker 调度：

| Schema | 说明 |
| --- | --- |
| `scan_run_create_request.schema.json` | 创建一次扫描批次，指定项目、平台范围和问题范围 |
| `scan_run_response.schema.json` | 查询或创建后返回 run 状态 |
| `scan_task_response.schema.json` | 查询单个 provider/question 扫描任务状态 |
| `scan_task_list_response.schema.json` | 查询 scan run 下的任务状态列表 |

scan run 状态只允许 `queued`、`running`、`completed`、`failed`、`canceled`。scan task 状态只允许 `queued`、`running`、`completed`、`failed`、`skipped`。

每个已完成 ScanRun 可通过 `GET /api/v1/projects/{project_id}/scan-runs/{run_id}/quality-report` 重算 `airank.measurement-quality.v4`。响应使用 `measurement_quality_report_response.schema.json`，执行基础样本与分采集面证据检查；未提及必须保留在有效分母。每个问题、Provider、Cohort、采集面和模型口径必须有至少 3 个独立 sample index 和 session；单次样本或重用会话必须 `publishable=false`。每个样本都必须有独立 Evidence Manifest，且 `surface/evidence_level` 必须与任务一致：API 要求请求元数据、追踪 ID 和 Provider 请求审计；Web/App 除要求不可变截图对象与 SHA-256 外，采集器还必须确认进入全新会话，并明确来源面板 `captured/not_present`，有引用时还要绑定不可变来源面板对象；App 另需设备/App 环境元数据 hash；manual_import 另需导入源 hash。任一阻断检查失败时 `publishable=false`，报告只能保存为 `quality_blocked`，下载接口返回 `409 REPORT_QUALITY_BLOCKED`。

Provider 请求参数属于测量口径的一部分。每次 API 调用必须把实际 `max_tokens`、上游字段名、temperature 和 reasoning effort 写入请求审计 metadata，并通过 `configuration_fingerprint` 关联版本化 Provider manifest/route；`20260808_0022` 把 manifest 默认值和 route 实际请求契约分别保存为 JSON，不保存密钥。配置指纹必须参与版本 ID，凭证轮换或请求参数变化只能追加版本，不得覆盖历史审计关联。HTTP 成功但最终回答为空时，原始上游响应、request ID、usage、终止元数据、时长和请求契约仍须进入失败 EvidenceSnapshot，样本状态保持 `failed` 且不得进入有效分母；如果上游已经返回 usage，则失败调用也必须进入用量账本。模型专属固定参数不得用一个全局默认覆盖；例如 Kimi K3 使用 `max_completion_tokens`、省略固定 temperature 并显式记录 reasoning effort。

客户交付使用不可变证据包，而不是仅记录“下载成功”：

```text
POST /api/v1/projects/{project_id}/evidence-integrity-audits
GET  /api/v1/projects/{project_id}/evidence-integrity-audits/latest
GET  /api/v1/projects/{project_id}/evidence-integrity-audits/{audit_id}
POST /api/v1/reports/{report_id}/evidence-packets
GET  /api/v1/reports/{report_id}/evidence-packets/latest
GET  /api/v1/evidence-objects/{object_ref_id}/content
```

项目级巡检当前使用 `airank.evidence-integrity.v2`。它保留 v1 对 AnswerSnapshot、EvidenceSnapshot、CitationCapture、CitationSourceSegment、KnowledgeSource、KnowledgeSourceSegment、FactRevision 以及非报告对象引用的 SHA-256、字节数、存储驱动、可用性和精确原文边界校验，并新增派生状态重建：ScanRun 的 `task_count` 必须由真实任务行重算；Retest 报告的质量门禁、对比指标、报告 SHA-256、报告状态、观察窗口结果和 RetestRun 摘要必须从原始任务、快照、请求审计、引用与最终审核状态确定性重建。任一源证据缺失或派生结果漂移均失败关闭。空项目和实体数超过 10,000 同样失败关闭；每个 verified/blocking finding 和按证据状态确定生成的 manifest SHA-256 都持久化，前端可按实体下钻。超过容量上限必须分片，不得把未检查实体视为通过；当前仅支持 ScanRun 与 Retest 报告派生重建，遇到其他报告类型会显式阻断，不能把旧 hash 当作重算证据。

生成接口必须携带每次客户导出动作唯一的 `Idempotency-Key`，操作者来自认证上下文；服务端再按完整内容 hash 去重，所以同一证据不会重复建包，而来源修订或有效期状态变化可以形成新的不可变版本。只有 `airank.measurement-quality.v4` 的基线和对比质量门禁均为 `publishable=true`、项目级 v2 证据与派生状态巡检全部通过，且报告具备可从基线/对比 run 重建的 `report_sha256`、样本索引和观察窗口 provenance 时才允许生成；巡检失败返回 `409 REPORT_EVIDENCE_INTEGRITY_BLOCKED`。当前新包使用 `airank.report-evidence-packet.v6`，采用内容寻址保存，包含公式、限制项、风险、样本/引用/事实准确性/来源治理/对象索引、巡检摘要、巡检 manifest hash 和文件哈希，但不复制原始回答正文或人工分类说明正文。事实与引用支持索引只接受 `production` 用途、不同审核人双人一致或第三人裁决后的最终结论，并保存 review case、审核角色、证据边界和记录 hash；`benchmark` 与旧单人审核只用于质量评估或历史追溯，不进入客户指标。来源治理索引按 Citation 精确 host 保存当前分类修订及其 hash，未分类、过期、未知权威、禁止用途和无法解析 host 分开进入限制项；治理覆盖不完整时仍可交付观测事实，但不得生成整体来源权威性结论。历史 v1/v2/v3/v4/v5 包仍可下载；v1–v4 的 `integrity_audit_id` 为 `null`，v5 只代表 v1 源证据巡检，均不会冒充当前 v6 的派生重建门禁。原始回答仍通过样本详情和不可变证据对象下钻。客户端下载对象并校验 SHA-256 后，再调用下载回执接口。

事实准确性审核接口：

```text
GET  /api/v1/samples/{snapshot_id}/fact-accuracy
POST /api/v1/answer-claims/{claim_id}/fact-accuracy-reviews
POST /api/v1/projects/{project_id}/evidence-review-cases/fact-accuracy
POST /api/v1/evidence-review-cases/{case_id}/decisions
GET  /api/v1/projects/{project_id}/evidence-review-cases
```

GET 响应使用 `fact_accuracy_bundle_response.schema.json`；旧单人 POST 仅保留兼容与历史取证，不进入商业指标。生产审核必须通过 evidence review case 创建第一审核，再由不同账号盲审；不一致时由第三个不同账号裁决。只有 `brand_fact` 与 `competitor_fact` 进入分母；`accurate/inaccurate/outdated` 必须由人工绑定当前已审核、公开或脱敏、未过期、无冲突的 FactRevision 及有效来源精确原文边界。`insufficient_evidence` 保留为证据缺口，不得按错误计分。只有全部事实声明都完成当前、确定性、最终 `production` 双人审核时才输出 `fact_accuracy`；事实或来源失效后旧审核自动退出商业指标，但不可变审核记录保留。`benchmark` 至少需要 20 个独立双人样本、全部终结且 Cohen's kappa 不低于 0.80 才通过审核质量门禁；benchmark 结论永不进入客户指标。

## M3 事实审核契约

可信事实卡审核接口：

```text
PATCH /api/v1/projects/{project_id}/facts/{fact_id}/review
```

请求使用 `fact_review_request.schema.json`，响应使用 `fact_review_response.schema.json`。`confirmed` 必须带至少一个可追溯 `source_refs`，其中 `citation_id`、`object_ref_id`、`source_url` 至少有一个。`needs_redaction` 映射为 `disclosure=redacted`，`private` 映射为 `disclosure=internal`。

AI 收录包接口：

```text
GET /api/v1/projects/{project_id}/asset-bundle
```

响应使用 `asset_bundle_response.schema.json`。当前返回可用于前端资产页的真实 API payload；资产内容仍是 dev-only seed，不代表生产内容生成。

## 幂等

以下接口必须支持 `Idempotency-Key`：

- 创建 scan run
- 创建 publish package
- 生成报告
- 发起 retest
- 创建独立证据复核任务
- 生成报告证据包

幂等记录必须按 `tenant_id + idempotency_key + route` 隔离。

## 状态码

| HTTP | 用途 |
| --- | --- |
| 200 | 成功查询或更新 |
| 201 | 创建成功 |
| 202 | 异步任务已接收 |
| 400 | 请求格式或业务参数错误 |
| 401 | 未认证 |
| 403 | 无权限或租户不匹配 |
| 404 | 资源不存在 |
| 405 | HTTP 方法不支持 |
| 409 | 幂等冲突或状态冲突 |
| 422 | 字段校验失败 |
| 429 | 限流 |
| 500 | 未预期错误 |
| 502 | 外部服务失败 |
| 503 | 外部能力不可用 |

## 外部能力降级

当 yudao / Xinghe 能力失败：

- 必须返回统一错误码。
- 必须写 `airank_integration_capabilities` 或 adapter status。
- 如果有 fallback，应返回 fallback 结果并在 `meta` 中标记 `degraded=true`。

## 外部 AI 网页 Provider 预检

```text
GET /api/v1/provider-readiness
```

响应使用 `provider_readiness_response.schema.json`。每个平台必须显式返回 `probe_level` 和 `generation_verified`：浏览器日常预检只打开持久 profile 并确认是否能进入可输入问题的状态，标记为 `l2_interaction`，即使 `status=ready` 也不能推导为已完成回答；API 真实生成探针或 release L3 探针才标记为 `l3_generation`，且只有取得实质回答时 `generation_verified=true`。`status=blocked` 不会自动降级为 mock；生产环境必须先修复登录态、真人验证或入口 URL，再允许品牌检测生成报告。

`AIRANK_PROVIDER_MODE=browser` 时，品牌检测默认要求当前 scope 的 provider 全部完成；`AIRANK_MIN_PROVIDER_SUCCESS_COUNT` 只能用于已声明的部分平台 beta。真实采样未达到门槛时，接口返回 `INTEGRATION_CAPABILITY_BLOCKED`，不得生成可下载报告和发布包。

## 安全

- API 不返回密钥。
- 日志不输出 token、API Key、Cookie。
- 错误详情不暴露外部服务完整响应体。

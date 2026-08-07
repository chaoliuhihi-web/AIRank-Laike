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

每个已完成 ScanRun 可通过 `GET /api/v1/projects/{project_id}/scan-runs/{run_id}/quality-report` 重算 `airank.measurement-quality.v3`。响应使用 `measurement_quality_report_response.schema.json`，执行 11 项基础样本检查和 11 项采集面证据检查；未提及必须保留在有效分母。每个问题、Provider、Cohort、采集面和模型口径必须有至少 3 个独立 sample index 和 session；单次样本或重用会话必须 `publishable=false`。每个样本都必须有独立 Evidence Manifest，且 `surface/evidence_level` 必须与任务一致：API 要求请求元数据、追踪 ID 和 Provider 请求审计；Web/App 要求不可变截图对象与 SHA-256，并明确来源面板 `captured/not_present`，有引用时还要绑定不可变来源面板对象；App 另需设备/App 环境元数据 hash；manual_import 另需导入源 hash。任一阻断检查失败时 `publishable=false`，报告只能保存为 `quality_blocked`，下载接口返回 `409 REPORT_QUALITY_BLOCKED`。

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

响应使用 `provider_readiness_response.schema.json`。该接口是部署前和巡检使用的慢速预检，会打开每个消费端网页 Provider 的持久浏览器 profile，确认是否能进入可输入问题的状态。`status=blocked` 不会自动降级为 mock；生产环境必须先修复登录态、真人验证或入口 URL，再允许品牌检测生成报告。

`AIRANK_PROVIDER_MODE=browser` 时，品牌检测默认要求当前 scope 的 provider 全部完成；`AIRANK_MIN_PROVIDER_SUCCESS_COUNT` 只能用于已声明的部分平台 beta。真实采样未达到门槛时，接口返回 `INTEGRATION_CAPABILITY_BLOCKED`，不得生成可下载报告和发布包。

## 安全

- API 不返回密钥。
- 日志不输出 token、API Key、Cookie。
- 错误详情不暴露外部服务完整响应体。

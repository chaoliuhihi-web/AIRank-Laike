# AIRank API 约定

## 版本

第一版 API 统一使用：

```text
/api/v1
```

不提供无版本 API。后续破坏性变更进入 `/api/v2`。

## 认证

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

当前 M1 dev-only repository 暴露以下路由，先用于前后端和 contract test 串联，不代表生产 MySQL 持久化：

| Route | 说明 |
| --- | --- |
| `POST /api/v1/projects` | 根据网站和可选 hint 创建待确认项目，返回 `project_response.schema.json` |
| `POST /api/v1/projects/{project_id}/competitors` | 给项目追加候选竞品，返回 `competitor_response.schema.json` |
| `POST /api/v1/projects/{project_id}/buyer-questions` | 给项目追加候选买家问题，返回 `buyer_question_response.schema.json` |

`tenant_id` 必须来自认证上下文或 `tenant-id` header，不能从 request body 接收。当前 in-memory adapter 仅用于开发串联，进程重启后数据会丢失。

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

## 安全

- API 不返回密钥。
- 日志不输出 token、API Key、Cookie。
- 错误详情不暴露外部服务完整响应体。

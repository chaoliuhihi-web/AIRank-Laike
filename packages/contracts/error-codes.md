# AIRank 错误码注册表

错误码必须稳定、可搜索、可用于日志、API 响应和 worker 失败原因。

## 命名规则

```text
<DOMAIN>_<REASON>
```

示例：

```text
AUTH_TOKEN_INVALID
SCAN_PROVIDER_TIMEOUT
FACT_DISCLOSURE_FORBIDDEN
```

## 通用错误

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `BAD_REQUEST` | 400 | 请求格式或业务参数错误 |
| `VALIDATION_FAILED` | 422 | 字段校验失败 |
| `RESOURCE_NOT_FOUND` | 404 | 资源不存在 |
| `METHOD_NOT_ALLOWED` | 405 | HTTP 方法不支持 |
| `STATE_CONFLICT` | 409 | 状态冲突 |
| `RATE_LIMITED` | 429 | 被限流 |
| `INTERNAL_ERROR` | 500 | 未预期错误 |

## 认证与租户

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `AUTH_TOKEN_MISSING` | 401 | 缺少 token |
| `AUTH_TOKEN_INVALID` | 401 | token 无效 |
| `AUTH_YUDAO_UNAVAILABLE` | 503 | yudao auth 不可用 |
| `TENANT_MISMATCH` | 403 | header 租户与 token 租户不一致 |
| `TENANT_FORBIDDEN` | 403 | 无租户权限 |

## 项目和问题

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `PROJECT_NOT_FOUND` | 404 | 项目不存在 |
| `PROJECT_ARCHIVED` | 409 | 项目已归档 |
| `QUESTION_NOT_FOUND` | 404 | 问题不存在 |
| `QUESTION_LIMIT_EXCEEDED` | 400 | 问题数量超限 |

## 扫描和 worker

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `SCAN_RUN_NOT_FOUND` | 404 | 扫描批次不存在 |
| `SCAN_RUN_ALREADY_RUNNING` | 409 | 扫描已在运行 |
| `SCAN_TASK_NOT_FOUND` | 404 | 扫描任务不存在 |
| `SCAN_PROVIDER_TIMEOUT` | 502 | provider 超时 |
| `SCAN_PROVIDER_BLOCKED` | 502 | provider 拒绝或阻断 |
| `JOB_NOT_FOUND` | 404 | job 不存在 |
| `JOB_TIMEOUT` | 500 | job 超时 |
| `JOB_MAX_ATTEMPTS_EXCEEDED` | 500 | job 重试耗尽 |

## 事实和内容

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `FACT_NOT_FOUND` | 404 | FactAtom 不存在 |
| `FACT_SOURCE_REQUIRED` | 400 | 缺少来源证据 |
| `FACT_DISCLOSURE_FORBIDDEN` | 403 | 不允许用于公开内容 |
| `ASSET_NOT_FOUND` | 404 | 内容资产不存在 |
| `ASSET_REVIEW_REQUIRED` | 409 | 内容需要审校 |

## 报告和证据

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `REPORT_NOT_FOUND` | 404 | 报告不存在 |
| `REPORT_EVIDENCE_MISSING` | 500 | 报告缺少证据链 |
| `OBJECT_REF_NOT_FOUND` | 404 | 对象引用不存在 |

## 外部能力

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `INTEGRATION_CAPABILITY_BLOCKED` | 503 | 外部能力 blocked |
| `INTEGRATION_CAPABILITY_DISABLED` | 503 | 外部能力 disabled |
| `YUDAO_MODEL_RESOLVE_FAILED` | 502 | yudao 模型解析失败 |
| `XINGHE_CRAWLER_FAILED` | 502 | Crawler Gateway 调用失败 |
| `XINGHE_KB_FAILED` | 502 | KB Service 调用失败 |

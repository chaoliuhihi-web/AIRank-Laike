# AIRank 可观测性设计

## 目标

M1 先保证能定位问题，M2 再完善 OpenTelemetry 和 dashboard。不要等平台复杂后再补日志和指标。

## Trace 规则

所有 API、worker、adapter、audit event 都必须携带 `trace_id`。

入口规则：

- HTTP 请求优先读取 `X-AIRank-Trace-Id`。
- 如果没有，`apps/api` 生成 `trace_id`。
- 响应头返回 `X-AIRank-Trace-Id`。
- worker job 的 `payload_json` 必须包含 `trace_id`。
- 调用 yudao / XingheAI2026V2 时透传 `trace_id`，同时保存外部 `external_trace_id`。

推荐字段：

```json
{
  "trace_id": "trc_...",
  "request_id": "req_...",
  "tenant_id": "1",
  "project_id": "prj_...",
  "actor_user_id": "1001",
  "component": "apps.api",
  "operation": "scan.create",
  "status": "ok",
  "duration_ms": 42
}
```

## Structured Logging

日志必须是结构化 JSON。禁止在日志里写：

- API Key、访问令牌、Cookie
- 完整网页原文
- 客户未公开商业事实全文
- 未脱敏的 yudao model resolve 结果

最低字段：

| 字段 | 说明 |
| --- | --- |
| `timestamp` | ISO 时间 |
| `level` | debug/info/warn/error |
| `trace_id` | 全链路追踪 |
| `tenant_id` | 租户 |
| `project_id` | 项目，可为空 |
| `component` | `apps.api` / `apps.worker` / `xinghe-adapter` |
| `operation` | 业务操作 |
| `event` | 事件名 |
| `duration_ms` | 耗时 |
| `error_code` | 统一错误码，可为空 |

## 核心指标

M1 必须先定义指标名，即使先用日志聚合。

| 指标 | 说明 | 建议阈值 |
| --- | --- | --- |
| `api_request_count` | API 请求数 | 按 route / status 维度 |
| `api_request_duration_ms` | API 延迟 | P95 > 800ms 告警 |
| `worker_queue_depth` | `queued` job 数 | > 100 持续 10 分钟告警 |
| `worker_job_duration_ms` | job 执行耗时 | P95 超预期告警 |
| `scan_task_success_rate` | 扫描任务成功率 | < 90% 告警 |
| `provider_error_rate` | 单 provider 错误率 | > 20% 告警 |
| `adapter_capability_status` | 外部能力状态 | `ready` 降级持续 10 分钟告警 |
| `fact_atom_confirm_rate` | FactAtom 确认率 | 用于产品运营判断 |
| `report_generation_success_rate` | 报告生成成功率 | < 95% 告警 |

## 告警规则

第一版告警规则：

- worker 队列积压超过阈值。
- `running` job 超过 `timeout_seconds` 且 `heartbeat_at` 超时。
- yudao auth 连续失败。
- 任一 `required_for_mvp=true` capability 变为 `blocked`。
- 扫描成功率连续下降。
- 报告生成失败。

## 分阶段落地

### M1

- `trace_id` 全链路透传。
- JSON structured logging。
- worker 心跳和超时回收日志。
- 错误码进入日志和 API 响应。

### M2

- OpenTelemetry instrumentation。
- metrics exporter。
- dashboard 和告警。
- adapter 外部调用 tracing。

### M3

- 分租户运营看板。
- SLA / SLO 报告。
- 长期审计日志归档。

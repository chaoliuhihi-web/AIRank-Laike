# AIRank 事件与 Outbox 设计

## 定位

M1 使用 `airank_async_jobs` 跑通主链，不引入 Kafka / Redis Streams。M2 引入 MySQL outbox 模式，把模块间隐式 job 链改成可追踪事件。

## 为什么不在 M1 引入完整事件总线

- 当前代码还没开始，过早引入消息系统会拖慢主链。
- MySQL job queue 足够支撑 30 天 MVP。
- 事件契约可以先设计，runtime 后置。

## Outbox 表

`airank_outbox_events` 用于记录待分发事件：

- `event_type`
- `aggregate_type`
- `aggregate_id`
- `tenant_id`
- `project_id`
- `trace_id`
- `payload_json`
- `status`
- `available_at`
- `published_at`
- `attempt_count`
- `error_message`

事件写入必须和业务状态变更在同一个 MySQL transaction 中完成。

## 第一批事件

| 事件 | 触发点 | 消费方 |
| --- | --- | --- |
| `scan.requested` | 创建 scan run | worker scan |
| `scan.completed` | scan run 完成 | score / gap / report job |
| `fact_atom.confirmed` | 人工确认 FactAtom | content gap / asset job |
| `content_asset.generated` | 内容资产生成 | publish package job |
| `publish_package.exported` | 发布包导出 | retest scheduler |
| `retest.completed` | 复测完成 | report job |
| `report.generated` | 报告生成 | notification / audit |

## 分发语义

- 至少一次投递。
- 消费方必须幂等。
- 事件 payload 不保存密钥和大对象，只保存 ID、摘要和 object ref。
- 失败事件保留错误码和错误摘要。

## M2 执行计划

1. 先让 `airank_outbox_events` 只记录事件，不分发。
2. 增加 outbox dispatcher worker。
3. 将 scan completed 后的 score / gap / report 链路迁到事件消费。
4. 增加 outbox backlog 指标和告警。

## 何时升级到 Redis Streams 或 Kafka

满足任一条件再升级：

- 单日 scan task 超过 10 万。
- outbox backlog 长期超过阈值。
- 多服务独立部署后 MySQL polling 成为瓶颈。
- 需要跨系统实时订阅。

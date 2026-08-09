# Publisher Operation Guard

AIRank 的 WordPress 和通用 HTTP 发布会产生客户外部副作用。`20260809_0043` 将每个 publish attempt 绑定到持久 `airank.operation-guard.v1`，目标是在响应丢失或 Worker 崩溃时停止自动重发，而不是声称分布式 exactly-once。

## 状态和证据

1. Worker 用租户、发布包、原始发布幂等键的 SHA-256 和不可变请求 SHA-256 创建 `publisher.publish` 操作。
2. attempt 保存 `operation_id`；原始幂等键不进入 Operation Guard。
3. 通用 HTTP 在 POST 前、WordPress 在确定性 slug 查询确认不存在且准备 POST 时，写入 `external_started`。
4. 可信回执写入 Operation Guard，形成 `claimed → external_started → succeeded` 的追加式事件 hash 链；WordPress 查到既有页面时允许 `claimed → succeeded`。
5. 网络中断、超时、无效/缺失回执或副作用后的进程异常使 attempt/package 进入 `outcome_unknown`，Operation Guard 保持 `external_started`。后续相同请求返回 `OPERATION_OUTCOME_UNKNOWN`，不会再 POST。

发布中心的 attempt 详情显示 Operation ID、状态、副作用是否开始、待对账标记和事件数。具备 `airank:delivery:admin` 的账号可读取 `/api/v1/publish-operations/{operation_id}`，下钻请求 hash、状态和完整事件链。接口只读，没有强制成功或跳过对账入口。

## 恢复边界

- 通用 HTTP 没有 AIRank 可证明的通用读取协议。未知结果必须由客户在目标系统核对，再决定是否以新发布包执行新的明确操作。
- WordPress 使用发布包派生的确定性 slug 做只读 GET。只有真实页面存在且回执可解析时，才将原 attempt 和 Operation Guard 收口为成功；查询为空或失败时仍保持未知，不自动 POST。
- 副作用前的本地配置、凭证、内容 hash 或端点错误会明确失败。原操作封存；修复后应创建使用新幂等键的发布包。
- Operation Guard 已成功而本地 package 回执写入失败时，重跑会复用 Guard 中的 hash 回执完成本地持久化，不重复调用外部发布。
- 历史无 `operation_id` 的 stale attempt 无法证明是否触发外部请求，统一按未知结果处理。

## 生产验收

- 迁移头必须为 `20260809_0043`，`airank_publish_attempts.operation_id` 具有唯一索引和外键。
- 正常发布必须只有一次 POST，事件链顺序和前序 hash 连续。
- 模拟 POST 后响应丢失时 package/attempt 为 `outcome_unknown`；重新入队不能产生第二次 POST。
- WordPress 响应丢失后，重新入队只能发 GET；找到确定性页面后可安全完成原 attempt。
- API 需验证租户隔离和 `airank:delivery:admin` 权限。
- 数据库、日志、API 和前端不得出现发布凭证或原始 Operation Guard 幂等键。

客户真实站点回执、更新/撤回、Webhook 状态查询协议和跨站点长时故障测试仍未完成，因此发布能力保持 `partial`。

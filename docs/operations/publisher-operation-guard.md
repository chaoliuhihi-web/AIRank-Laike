# Publisher Operation Guard

AIRank 的 WordPress 和通用 HTTP 发布会产生客户外部副作用。`20260809_0043` 将每个 publish attempt 绑定到持久 `airank.operation-guard.v1`；`20260809_0045` 把更新和撤回建模为新的不可变动作包；`20260809_0046` 为无法机器恢复的 `outcome_unknown` 增加双人证据对账。目标是在响应丢失或 Worker 崩溃时停止自动重发，而不是声称分布式 exactly-once。

## 状态和证据

1. Worker 用租户、发布包、原始发布幂等键的 SHA-256 和不可变请求 SHA-256 创建 `publisher.publish` 操作。
2. attempt 保存 `operation_id`；原始幂等键不进入 Operation Guard。
3. 通用 HTTP 在 POST 前、WordPress 在确定性 slug 查询确认不存在且准备 POST 时，写入 `external_started`。
4. 可信回执写入 Operation Guard，形成 `claimed → external_started → succeeded` 的追加式事件 hash 链；WordPress 查到既有页面时允许 `claimed → succeeded`。
5. 网络中断、超时、无效/缺失回执或副作用后的进程异常使 attempt/package 进入 `outcome_unknown`，Operation Guard 保持 `external_started`。后续相同请求返回 `OPERATION_OUTCOME_UNKNOWN`，不会再 POST。

发布中心的 attempt 详情显示 Operation ID、状态、副作用是否开始、待对账标记和事件数。具备 `airank:delivery:admin` 的账号可读取 `/api/v1/publish-operations/{operation_id}`，下钻请求 hash、状态和完整事件链。Operation Guard 本身没有强制成功或跳过对账入口；人工收口只能经过下面的独立证据域。

## 恢复边界

- 通用 HTTP 没有 AIRank 可证明的通用读取协议。未知结果必须由客户在目标系统核对，再决定是否以新发布包执行新的明确操作。
- WordPress 使用发布包派生的确定性 slug 做只读 GET。只有真实页面存在且回执可解析时，才将原 attempt 和 Operation Guard 收口为成功；查询为空或失败时仍保持未知，不自动 POST。
- 副作用前的本地配置、凭证、内容 hash 或端点错误会明确失败。原操作封存；修复后应创建使用新幂等键的发布包。
- Operation Guard 已成功而本地 package 回执写入失败时，重跑会复用 Guard 中的 hash 回执完成本地持久化，不重复调用外部发布。
- 历史无 `operation_id` 的 stale attempt 无法证明是否触发外部请求，统一按未知结果处理。

## 双人证据对账

- `POST /api/v1/publish-packages/{package_id}/reconciliations` 只接受 WordPress/HTTP 的 `outcome_unknown` 包，且对应 attempt 必须绑定 `external_started` 的 `publisher.publish` Operation Guard。
- 目前只允许提议 `succeeded`。提交必须包含真实 URL、2xx 状态、外部回执/远端 ID、观察时间、至少 20 字说明，以及属于同租户同项目的不可变对象引用和 SHA-256；服务端会重新读取对象存储并校验真实字节和大小。
- WordPress 的外部回执 ID 必须是数字 post ID。通用 HTTP 接受客户渠道回执 ID，但不会把它冒充 AIRank 直接取得的原生 Provider 回执。
- `POST /api/v1/publish-reconciliations/{case_id}/review` 要求另一位 `airank:delivery:admin`；认证账号与提交人相同会被服务端拒绝。复核请求必须回传审核人实际核对的对象 ID 与 SHA-256，和案例不一致时失败关闭；审核、应用和前序 hash 事件不可覆盖。
- 驳回不改变 package、attempt 或 Operation Guard，继续禁止重放。批准会在一个本地数据库事务内收口 Operation Guard、attempt、package、变更目标 lineage 和对账事件；任何一步失败都整体回滚，不产生外部请求。
- 人工批准后的回执固定 `receipt_origin=manual_reconciliation`、`reconciliation_method=two_person_manual_evidence`、`external_delivery_verified=false`，发布实现等级保持 `partial`。首次发布/更新只恢复到 `delivered`，仍需另行登记可访问页面证据和 T0 基线后才是 `published`；撤回恢复为 `withdrawn`。
- 系统不提供“人工确认未发生并自动重发”。仅凭页面不存在或人工说明无法证明通用外部系统未处理原请求；没有渠道级机器可验证状态协议时，未知结果继续失败关闭。

## 更新与撤回

- `POST /api/v1/publish-packages/{package_id}/mutations` 只接受状态为 `published` 的 WordPress/HTTP 包，并要求 `airank:delivery:admin`。
- `update` 必须绑定当前 hash 已通过事实与风险审核的替换资产；`withdraw` 不接受替换资产。两者都必须提交至少 10 个字符的原因，操作者只取认证上下文。
- 每个动作创建新的 `airank.publish-snapshot.v3` 与发布包，保存 `publication_action`、`target_package_id`、原因、内容 hash 和请求 hash；原始快照不覆盖。
- 同一目标已有 queued/publishing/delivered/outcome_unknown 动作时拒绝创建下一动作。相同幂等键只允许相同请求重放。
- WordPress 更新只 POST 到原成功回执中的数字 `remote_id`；不做 slug 查询或新建。撤回同样 POST 到该 ID，并把状态设为 `draft`，不执行 DELETE。
- 通用 HTTP 使用 `airank.publisher.v2`，明确发送动作、目标包、目标远端 ID/URL、原因和不可变内容；客户适配器必须返回可验证 URL 回执。
- 更新成功后原包为 `superseded`、动作包为 `delivered`；动作包重新登记真实 publication evidence 后才是 `published`。撤回成功后目标包与动作包均为 `withdrawn`。
- 动作 POST 后响应丢失时，动作包为 `outcome_unknown`，目标包保持原状态；禁止自动重发、WordPress slug 对账以及并发下一动作。

## 生产验收

- 迁移头必须为 `20260809_0046`，`airank_publish_attempts.operation_id` 具有唯一索引和外键，发布包具有动作与目标 lineage 字段，attempt 可回指对账案例。
- 正常发布必须只有一次 POST，事件链顺序和前序 hash 连续。
- 模拟 POST 后响应丢失时 package/attempt 为 `outcome_unknown`；重新入队不能产生第二次 POST。
- WordPress 响应丢失后，重新入队只能发 GET；找到确定性页面后可安全完成原 attempt。
- API 需验证租户隔离和 `airank:delivery:admin` 权限。
- 协议 fixture 必须证明 WordPress 更新直接命中原 `remote_id`、撤回使用 `status=draft`、恶意 remote ID 在发请求前被拒绝。
- 对账 fixture 必须证明对象真实字节 hash、租户/项目范围、提交人自审阻断、双人事件 hash 链，以及 package/attempt/Operation Guard 同事务收口；人工回执不得出现 `external_delivery_verified=true`。
- 数据库、日志、API 和前端不得出现发布凭证或原始 Operation Guard 幂等键。

本地真实 MySQL 与协议 fixture 已覆盖首次发布、更新、撤回、状态 lineage、幂等、租户/RBAC、未知结果零重发和双人证据对账的本地原子收口。客户真实站点首次/更新/撤回回执、通用 HTTP 机器状态查询、真实客户双人对账案例和跨站点长时故障测试仍未完成，因此发布能力保持 `partial`。

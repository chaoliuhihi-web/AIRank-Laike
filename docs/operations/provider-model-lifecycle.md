# Provider 模型生命周期与迁移门禁

AIRank 使用 Provider manifest 中的公开生命周期声明计算两类门禁：

- 执行门禁默认 30 天：进入窗口或已下架的模型不能再发起生成请求。
- 发布门禁默认 90 天：进入窗口后，必须有目标模型真实成功 L3 请求审计，并完成迁移审批，才能通过代码发布门禁。

两个窗口分别由 `AIRANK_PROVIDER_MODEL_MIN_DAYS_TO_SUNSET` 与 `AIRANK_PROVIDER_MODEL_RELEASE_MIN_DAYS_TO_SUNSET` 配置，发布窗口不得小于执行窗口。没有 manifest 生命周期声明的模型显示为 `unmanaged`，不伪造下架日期；这只表示 AIRank 未掌握公告，不等于 Provider 承诺长期可用。

## 迁移状态机

```text
planned
  ├─ validation_failed ──(新真实审计)──> validated
  └─ validated ──(管理员审批)──────────> approved
```

创建计划时必须绑定当前 Provider、路由、模型和配置指纹，并且目标模型必须等于 manifest 的 replacement。相同 `Idempotency-Key` 和载荷只返回原计划；不同载荷复用 key、运行时配置漂移或任意目标模型都会失败关闭。

`validate` 只接受计划创建后的 `airank_provider_request_audits`：租户、Provider、route、目标模型必须一致，`outcome=success`、`completed_at` 和非空 Provider request ID 缺一不可。失败探测、HTTP 403、无 request ID、旧调用或手工文本都不能成为审批证据。AIRank 不自动发起可能计费的目标模型调用；操作员必须先通过 Provider Gateway 完成明确授权的 L3 验证，再绑定审计 ID。

计划和每次状态变化保存在 `airank_provider_model_migrations` 与追加式 `airank_provider_model_migration_events`。事件保存序号、前序 hash、actor、reason、trace 和目标请求审计。API 每次读取都会复核事件链和绑定审计；`status=approved` 但链或 L3 证据失效时，`release_eligible=false`，发布门禁继续阻断。

## 管理接口

```text
GET  /api/v1/admin/provider-model-migrations
POST /api/v1/admin/provider-model-migrations
POST /api/v1/admin/provider-model-migrations/{migration_id}/validate
POST /api/v1/admin/provider-model-migrations/{migration_id}/approve
GET  /api/v1/admin/provider-routes
```

接口要求 `airank:provider:admin` 和可信 actor。响应不返回 Provider request ID 原值，只返回是否存在、AIRank request audit ID、配置指纹和事件链状态。

## 发布验收

严格门禁运行：

```bash
python3 scripts/release_readiness.py --database-url "$AIRANK_RELEASE_DATABASE_URL"
```

`provider model lifecycle` 会读取真实数据库中启用的当前路由。以 2026-08-09 的已验证配置为例，`deepseek-v3.2` 距 2026-10-10 下架 62 天，仍在 30 天执行窗口之外，但已进入 90 天发布窗口；由于 `deepseek-v4-pro` 的真实调用曾返回额度 403，当前没有成功 L3 审计或批准计划，所以发布状态必须保持 `BLOCKED`。开通额度并取得目标模型真实成功请求审计之前，不得手工改绿或声明迁移完成。

## 当前边界

- 生命周期由版本化 manifest 维护，尚未自动同步 Provider 官方模型目录与公告。
- `approved` 表示替代模型已真实验证且迁移方案获批，不表示运行时已经切换；进入执行停止窗口后，旧模型即使已有批准计划也会被阻断。
- 当前没有自动改写模型环境变量、凭证或流量切换；切换必须经过独立部署变更和回归。
- Kimi 验收密钥已出现在会话记录，生产使用前仍必须轮换。

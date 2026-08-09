# Provider Usage Ledger 运维说明

AIRank 使用 `airank.provider-usage-ledger.v1` 保存真实 Provider 用量，并把原始用量与价格目录派生成本分开。该账本用于容量、成本覆盖与客户实施核算，不参与品牌推荐率、提及率或页面技术评分。

## 证据口径

- `usage_precision=exact`：Token 来自 Provider 原生 usage 字段。
- `usage_precision=estimated`：Token 来自明确记录版本和方法的估算器；当前四个平台适配器不伪造该值。
- `usage_precision=unknown`：Provider 没有返回可识别 Token，用量仍保留事件但不补造数字。
- `cost_precision=exact`：只允许 Provider 响应同时明确返回 billed amount 与三字母币种。
- `cost_precision=estimated`：Token 乘以 AIRank 价格目录版本所得；即使 Token 为 exact，成本仍是 estimated。
- `cost_precision=unknown`：缺少 Token、价格、币种或可接受的成本来源。

原始事件保存在 `airank_provider_usage_events`，每条记录绑定请求审计并保存 `raw_usage_sha256`。目录计算写入 `airank_provider_usage_costs`，绑定 `price_version_id`、计算契约和 `calculation_sha256`；重新定价只能追加派生记录，不能覆盖原始 Token 或旧计算。

## 迁移与启动

1. 执行 `alembic upgrade head`，确认数据库头为 `20260809_0042`。
2. 确认存在 `airank_provider_price_versions`、`airank_provider_usage_costs`，并确认 `airank_provider_usage_events.raw_usage_sha256` 为非空列。
3. 重启 API、Worker 和 Scheduler。Worker 写入失败样本时，只要 Provider 已返回 usage，同样必须调用统一持久化入口。
4. 访问 `GET /api/v1/admin/provider-usage`，确认未配置价格时成本为 `unknown`，而不是零。

## 管理员接口

所有接口要求可信 `airank:provider:admin` 权限并按 `tenant-id` 隔离：

```text
GET  /api/v1/admin/provider-prices
POST /api/v1/admin/provider-prices
GET  /api/v1/admin/provider-usage
```

用量查询支持 `provider`、`project_id`、`usage_precision`、`cost_precision`、`occurred_from`、`occurred_until` 与 `limit`。汇总字段使用 `known_cost_amount`，同时返回 `cost_coverage_rate` 和 `aggregate_cost_precision`；不得把已知部分称为总成本。

新增价格必须提供 Provider、路由、模型、币种、输入/输出每百万 Token 费率、生效时间、来源类型、来源引用、变更理由和 `expected_previous_version`。相同证据载荷为幂等重放；版本陈旧返回 `PROVIDER_PRICE_VERSION_CONFLICT`。来源引用或理由疑似包含 API Key、Bearer、secret 或 token 时，在数据库写入前返回 `PROVIDER_PRICE_INVALID`。

## 回算与报告规则

价格新增后，系统只回算相同租户、Provider、模型、路由和有效时间窗口内，且没有 Provider billed exact 成本的历史用量。匹配多个版本时优先精确路由，再选事件发生时最新生效的价格版本。

- 不同币种不自动换算或强行合并。
- 只要筛选范围内存在未定价事件，聚合成本精度就是 `unknown`。
- Provider billed exact 优先于目录计算。
- 目录价格不是发票，目录成本不是最终结算金额。
- 价格版本、用量事件和派生成本都不得删除或覆盖；纠错通过追加新版本完成。

## 当前边界

当前已完成本地真实 MySQL 的迁移、回算、筛选、版本冲突、幂等、租户隔离和清理测试。尚未完成生产官方价格自动同步、汇率治理、Provider 发票/账单回执对账和财务系统集成，因此 Usage Ledger 状态为 `partial`，不能据此声明财务结算已上线。

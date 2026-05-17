# AIRank 安全设计

## 安全边界

AIRank 第一版依赖 yudao 做身份、租户和权限权威源；AIRank 自己负责产品数据隔离、审计、密钥脱敏和内容公开控制。

## 身份与权限

M1 规则：

- API 只接受 yudao bearer token。
- `apps/api` 调 yudao `/admin-api/system/auth/get-permission-info` 解析用户和租户。
- 所有核心查询强制带 `tenant_id`。
- 项目级成员表 `airank_project_members` 只做产品侧角色缓存，不替代 yudao 权限。
- yudao 短暂不可用时，可使用短 TTL 本地 token cache；cache 只能用于已验证过的 token，不允许新登录。

角色建议：

| 角色 | 权限 |
| --- | --- |
| owner | 租户管理、项目管理、报告下载 |
| admin | 项目和扫描管理、事实审核、内容发布包 |
| editor | 事实确认、内容资产编辑 |
| viewer | 只读查看报告和证据 |

## 密钥与模型配置

- yudao model resolve 返回的 API Key 不落 MySQL 明文。
- `model_route_snapshot` 只保存 provider、model、model_id、key_id 和脱敏后的 key 指纹。
- 日志、audit event、错误详情禁止输出 API Key。
- 生产环境密钥放独立 secret store，不放 `.env`、SQL、文档或测试 fixture。

## 可信事实卡公开控制

FactAtom 必须执行两层控制：

- `trust_level`：A/B/C/D 表示可信等级。
- `disclosure`：public/redacted/internal/forbidden/pending_approval 表示可公开程度。

公开内容生成规则：

- `disclosure=public` 可直接进入官网类内容。
- `disclosure=redacted` 只能使用脱敏版本。
- `disclosure=internal` 只能用于内部分析和销售话术。
- `disclosure=forbidden` 禁止用于公开内容。
- `pending_approval` 必须人工确认后才能进入发布包。

## 审计日志

`airank_audit_events` 用于记录可追责行为：

- 创建和删除项目。
- 发起扫描。
- 确认、驳回、标记过期 FactAtom。
- 生成、导出、下载报告。
- 发布包导出和发布 URL 记录。
- 外部 adapter 能力降级。

审计事件必须包含：

- `tenant_id`
- `project_id`
- `actor_user_id`
- `event_type`
- `entity_type`
- `entity_id`
- `trace_id`
- `payload_json` 摘要

审计日志可以查询和导出，但默认不展示敏感 payload。

## 数据保护

- 大对象进入对象存储，使用按租户隔离的路径前缀。
- 对象引用写 `airank_object_refs`，保存 `sha256` 和 `content_type`。
- 删除项目时默认软删除；物理删除需要独立 runbook。
- 报告下载应写 download receipt 或 audit event。

## M1 必做

- token 校验和租户隔离。
- API Key 脱敏。
- FactAtom `disclosure` gate。
- audit event 写入。

## M2 补强

- 项目级 RBAC UI。
- 敏感字段加密。
- 审计日志导出。
- 数据保留和删除策略。

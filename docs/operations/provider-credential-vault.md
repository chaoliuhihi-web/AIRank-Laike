# Provider Credential Vault 运维手册

## 适用范围

AIRank 的租户级 Provider 凭证必须先完成一次可能计费的 L3 真实生成验证，才允许以 AES-256-GCM 密文写入 MySQL。明文只在 API 进程内存中短暂存在，不进入响应、日志、请求审计、事件表或 Git。

环境变量凭证仅作为迁移期 `environment_legacy` 路径；租户保险库中一旦存在当前记录，该租户/Provider/route 就以保险库状态为准。记录被撤销或主密钥不可用时失败关闭，不回退环境凭证。

## 上线前配置

部署密钥管理器必须注入以下变量：

```text
AIRANK_CREDENTIAL_ACTIVE_ENCRYPTION_KEY_ID
AIRANK_CREDENTIAL_ENCRYPTION_KEYS
AIRANK_CREDENTIAL_ACTIVE_FINGERPRINT_KEY_ID
AIRANK_CREDENTIAL_FINGERPRINT_KEYS
AIRANK_PROVIDER_ADMIN_PERMISSION=airank:provider:admin
```

两个 key map 均为 JSON 对象；每个值必须是精确 32 字节随机值的 Base64。加密与 HMAC 指纹必须使用不同密钥材料。真实值不得出现在 `.env.example`、命令历史、CI 日志或工单正文。

启动门禁：

1. 执行 `alembic upgrade head`，确认数据库头为 `20260809_0041`，并存在 `airank_operation_guards` 与 `airank_operation_guard_events`。
2. 以管理员身份读取 `/api/v1/admin/provider-credentials`，确认 `keyring_status=ready`。
3. 确认每条生产路由显示明确的 `vault_active`、`environment_legacy`、`unconfigured` 或阻断状态；不得用环境变量存在代替租户 L3 验证。
4. 只有 `airank:provider:admin` 权限可新增、轮换或撤销；客户端伪造权限和操作者必须被认证中间件覆盖。

## 租户凭证轮换

在设置中心的 Provider 凭证保险库中：

1. 输入新凭证和至少 3 个字符的变更理由。
2. 确认会执行一次可能计费的 L3 真实生成。
3. 服务端先用目标 Provider/route 做最小真实调用；失败时不写库。
4. 验证成功后创建新版本，旧版本密文和 nonce 在同一事务中擦除，并写入单调 `event_sequence` 的哈希链事件。
5. 页面返回的只有掩码、指纹前缀、key id、版本、模型、endpoint host、request-id 是否存在及 request-id SHA-256；不返回原始 request id 或明文。

版本冲突返回 `STATE_VERSION_CONFLICT`，刷新后重新确认；新旧凭证相同返回 `CREDENTIAL_UNCHANGED`。后一规则在 HMAC 指纹 key-id 换代期间仍使用旧 key-id 做恒定时间比对。

每次新增或轮换必须携带 8–160 字符且不含空白的 `Idempotency-Key`。服务端只落其 SHA-256，不保存原值。相同 key 和相同请求在成功后返回原凭证结果并标记 `idempotent_replay=true`，不会再次执行 L3；相同 key 的不同请求返回 `OPERATION_IDEMPOTENCY_CONFLICT`。

`airank_operation_guards` 在 L3 调用前先从 `claimed` 进入 `external_started`。如果调用开始后进程中断、响应丢失或状态无法可信收口，后续重放返回 `OPERATION_OUTCOME_UNKNOWN`。此时先刷新凭证列表、检查 Provider 请求审计和操作事件链，再由管理员使用全新幂等键发起明确的新操作；禁止客户端自动重试未知结果。

管理员可通过设置中心“凭证操作对账”或以下只读接口核对，不允许直接篡改终态：

```text
GET /api/v1/admin/provider-credential-operations?state=external_started&limit=25
GET /api/v1/admin/provider-credential-operations/{operation_id}
```

列表返回 `reconciliation_required_count`，详情返回从 claim 到当前状态的事件序号、前序/当前 hash、actor 与 trace。接口不返回原始幂等键、请求载荷、凭证明文、密文或 nonce。跨租户读取返回 404；只有 `airank:provider:admin` 可访问。

## 撤销与恢复

撤销需要当前版本、理由、显式确认和独立的 `Idempotency-Key`。成功后当前记录保留审计墓碑，但 `ciphertext`、`nonce` 和掩码被擦除；运行时返回 `PROVIDER_CREDENTIAL_REVOKED`，不会使用同一路由的环境凭证。

恢复不解封旧密文。必须提交一条不同且通过 L3 验证的新凭证，新版本激活后旧墓碑保持 `revoked`。

## 主密钥轮换

主密钥轮换采用 add → activate → rotate rows → remove，禁止直接替换：

1. 在 key map 中加入新 encryption key 和 fingerprint key，同时保留所有旧 key id。
2. 将两个 active key id 切换到新版本并滚动重启 API、Worker、Scheduler。
3. 逐租户、逐路由轮换当前 Provider 凭证，使新记录使用新 key id；同一 Provider 密钥不能冒充轮换。
4. 查询所有 `status='active' AND is_current=1` 记录，确认不再引用待删除的 encryption/fingerprint key id。
5. 完成数据库备份和恢复演练后，才从部署密钥管理器删除旧 key id，再滚动重启。

当前没有自动重加密批任务，因此未完成第 3–4 步时必须保留旧 key。删除仍被活动记录引用的 encryption key 会使该路由失败关闭；删除其 fingerprint key 会阻止安全的同值检测和后续轮换。

## 审计与告警

- `airank_provider_credential_events` 是追加式事件链，按租户/Provider/route 的 `event_sequence` 验证 `previous_event_sha256`。
- `airank_operation_guard_events` 是每次高风险写操作的追加式状态链，正常成功顺序为 `operation_claimed → external_effect_started → operation_succeeded`；失败终态为 `operation_failed`。
- `airank_provider_request_audits` 只保存 `credential_source`、`credential_id` 和 `credential_version`，不保存凭证值。
- 监控 `PROVIDER_CREDENTIAL_REVOKED`、`PROVIDER_CREDENTIAL_KEY_UNAVAILABLE`、`CREDENTIAL_DECRYPTION_FAILED` 和 `CREDENTIAL_PROVIDER_VERIFICATION_FAILED`。
- 生产前必须轮换任何曾出现在聊天、工单或终端输出中的 Provider 密钥；历史真实调用成功不能替代当前凭证安全状态。

## 当前限制

- 主密钥仍由部署 secret store 注入，尚未接云 KMS/HSM envelope encryption。
- 没有自动重加密作业和全租户轮换编排。
- 当前前端构建、幂等/冲突/并发故障测试和真实 MySQL 门禁已通过，但未用真实生产四平台账号执行一次完整租户 vault 轮换，也未完成 KMS/HSM，因此能力为 `partial`，不得声明生产凭证治理已完成。

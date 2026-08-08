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
| `IDEMPOTENCY_CONFLICT` | 409 | 同一幂等键对应了不同请求内容，拒绝重复副作用 |
| `RATE_LIMITED` | 429 | 被限流 |
| `INTERNAL_ERROR` | 500 | 未预期错误 |

## 认证与租户

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `AUTH_TOKEN_MISSING` | 401 | 缺少 token |
| `AUTH_TOKEN_INVALID` | 401 | token 无效 |
| `AUTH_LOGIN_FAILED` | 401 | 登录凭证无效 |
| `AUTH_YUDAO_UNAVAILABLE` | 503 | yudao auth 不可用 |
| `AUTH_PERMISSION_FORBIDDEN` | 403 | 已认证用户缺少内部管理操作所需权限 |
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
| `SCAN_RUN_LEASE_EXPIRED` | 500 | 兼容旧批次：整批 Worker 租约过期；新任务级 Worker 不再产生此码 |
| `SCAN_TASK_LEASE_EXPIRED` | 500 | 单个扫描任务租约过期且外部调用结果未知；仅封闭该采样槽并禁止自动重放 |
| `SCAN_RUN_CANCELED` | 409 | 扫描批次已取消，任务不会继续执行 |
| `SCAN_TASK_NOT_FOUND` | 404 | 扫描任务不存在 |
| `SCAN_JOB_INVALID` | 500 | 扫描 job 缺失 run/task/project 作用域 |
| `SCAN_JOB_SCOPE_MISMATCH` | 409 | 扫描 job 与批次、任务或租户作用域不一致 |
| `SCAN_WORKER_INTERNAL_ERROR` | 500 | Worker 内部失败；仅当前任务失效关闭且禁止自动重放 |
| `SCAN_PROVIDER_TIMEOUT` | 502 | provider 超时 |
| `SCAN_PROVIDER_FAILED` | 502 | provider 网络、上游或解析失败，可按策略重试 |
| `SCAN_PROVIDER_BLOCKED` | 502 | provider 拒绝或阻断 |
| `JOB_NOT_FOUND` | 404 | job 不存在 |
| `JOB_TIMEOUT` | 500 | job 超时 |
| `JOB_MAX_ATTEMPTS_EXCEEDED` | 500 | job 重试耗尽 |

## 页面可提取性审计

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `PAGE_AUDIT_URL_REQUIRED` | 400 | 项目未配置官网且请求未提供审计 URL |
| `PAGE_AUDIT_URL_INVALID` | 400 | 页面 URL 不符合安全出站策略或格式无效 |
| `PAGE_AUDIT_NOT_FOUND` | 404 | 页面审计运行不存在或不属于当前租户项目 |

## 引用来源抓取与支持度

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `CITATION_CAPTURE_NOT_FOUND` | 404 | 引用来源抓取不存在或不属于当前租户 |
| `CITATION_CAPTURE_URL_INVALID` | 409 | Provider 返回的引用 URL 缺失或不符合安全抓取格式 |
| `CITATION_SUPPORT_EVIDENCE_INVALID` | 409 | 支持度审核未绑定匹配的不可变来源、片段或精确字符边界 |
| `FACT_ACCURACY_EVIDENCE_INVALID` | 409 | 事实准确性裁决未绑定当前已审核事实、有效来源与精确原文边界，或声明类型不属于品牌/竞品事实 |
| `EVIDENCE_REVIEW_CASE_NOT_FOUND` | 404 | 双人证据复核任务不存在或不属于当前租户 |
| `EVIDENCE_REVIEW_CASE_EXISTS` | 409 | 同一目标、证据基础和用途已经存在复核任务 |
| `EVIDENCE_REVIEW_CASE_FINAL` | 409 | 复核任务已一致通过或完成裁决，不能继续追加普通决定 |
| `EVIDENCE_REVIEW_LABEL_INVALID` | 409 | 决定标签不属于该引用支持或事实准确性任务的允许集合 |
| `EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN` | 409 | 第二复核人或裁决人必须与之前的审核人不同 |
| `SOURCE_REGISTRY_ENTRY_NOT_FOUND` | 404 | 引用域名未出现在当前租户项目的真实 Citation 中，不能凭空创建来源分类 |
| `SOURCE_CLASSIFICATION_VERSION_CONFLICT` | 409 | 来源分类的当前版本已变化，必须刷新并显式 supersede 最新人工复核版本 |

## 事实和内容

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `FACT_NOT_FOUND` | 404 | FactAtom 不存在 |
| `FACT_REVISION_NOT_FOUND` | 404 | FactRevision 不存在 |
| `FACT_CONFLICT_NOT_FOUND` | 404 | FactConflict 不存在 |
| `FACT_CONFLICT_OPEN` | 409 | 事实存在未解决冲突 |
| `FACT_SUBJECT_IMMUTABLE` | 409 | FactAtom 的主体绑定不可在修订时更换 |
| `FACT_SUBJECT_BINDING_MISMATCH` | 409 | 事实主体与比较或解释任务声明的主体不一致 |
| `FACT_SOURCE_STALE` | 409 | 事实来源已失效或过期 |
| `KNOWLEDGE_SOURCE_NOT_FOUND` | 404 | KnowledgeSource 不存在 |
| `KNOWLEDGE_SYNC_POLICY_NOT_FOUND` | 404 | 知识来源自动同步策略不存在 |
| `KNOWLEDGE_SYNC_SOURCE_NOT_ELIGIBLE` | 409 | 来源不是 active 状态或缺少公开 HTTP(S) URL，不能启用自动同步 |
| `KNOWLEDGE_SYNC_POLICY_EXISTS` | 409 | 该不可变来源链已经存在自动同步策略 |
| `KNOWLEDGE_SYNC_POLICY_DISABLED` | 409 | 自动同步策略已暂停，不能创建新运行 |
| `KNOWLEDGE_SYNC_ALREADY_ACTIVE` | 409 | 同一策略已有排队或运行中的检查，不能重复入队 |
| `KNOWLEDGE_SYNC_VERSION_CONFLICT` | 409 | 更新使用的策略版本已过期，需要刷新后重试 |
| `CONTENT_EVIDENCE_MISSING` | 409 | 内容引用的事实证据缺失、冲突或失效 |
| `COMPARISON_EVIDENCE_INCOMPLETE` | 409 | 比较页的主体、维度或对称证据矩阵不完整 |
| `EXPLAINER_EVIDENCE_INCOMPLETE` | 409 | 解释页的角色、篇幅、品牌露出或精确证据门禁未通过 |
| `CONTENT_REVIEW_REQUIRED` | 409 | 内容尚未通过与当前内容 hash 一致的审核 |
| `CONTENT_RISK_OVERRIDE_REQUIRED` | 409 | 高风险内容需要记录人工 override 原因 |
| `PUBLISH_PACKAGE_NOT_FOUND` | 404 | 发布包不存在 |
| `PUBLICATION_SCREENSHOT_EVIDENCE_INVALID` | 409 | 发布截图对象不属于当前租户/项目，或客户端提交的 SHA-256 与不可变对象不一致 |
| `RETEST_WINDOW_NOT_FOUND` | 404 | 复测观察窗口不存在 |
| `RETEST_BASELINE_REQUIRED` | 409 | 缺少同项目且已完成的 T0 基线扫描 |
| `RETEST_COMPARE_RUN_REQUIRED` | 409 | 缺少同项目且已完成的复测扫描 |
| `FACT_SOURCE_REQUIRED` | 400 | 缺少来源证据 |
| `FACT_DISCLOSURE_FORBIDDEN` | 403 | 不允许用于公开内容 |
| `ASSET_NOT_FOUND` | 404 | 内容资产不存在 |
| `ASSET_REVIEW_REQUIRED` | 409 | 内容需要审校 |

## 引用支持度

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `CITATION_NOT_FOUND` | 404 | 引用不存在，或不属于当前断言与样本 |
| `CITATION_CLAIM_NOT_FOUND` | 404 | 回答断言不存在或不属于当前租户 |
| `CITATION_SUPPORT_EVIDENCE_INVALID` | 409 | 断言边界、来源摘要、对象 hash 或证据等级不满足支持度复核门禁 |

## 报告和证据

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `REPORT_NOT_FOUND` | 404 | 报告不存在 |
| `REPORT_QUALITY_BLOCKED` | 409 | 报告未通过样本完整性、证据 hash、有效率或可比性门禁，禁止下载交付 |
| `REPORT_EVIDENCE_MISSING` | 500 | 报告缺少证据链 |
| `REPORT_EVIDENCE_PACKET_NOT_FOUND` | 404 | 报告尚未生成不可变客户证据包 |
| `OBJECT_REF_NOT_FOUND` | 404 | 对象引用不存在 |
| `EVIDENCE_OBJECT_UNAVAILABLE` | 503 | 对象存储不可用、配置不匹配或对象无法读取 |
| `EVIDENCE_INTEGRITY_FAILED` | 409 | 对象内容与数据库记录的 SHA-256 或字节数不一致 |

## 内部 Skill

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `SKILL_NOT_FOUND` | 404 | 内部 Skill 未注册 |

## 外部能力

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `INTEGRATION_CAPABILITY_BLOCKED` | 503 | 外部能力 blocked |
| `INTEGRATION_CAPABILITY_DISABLED` | 503 | 外部能力 disabled |
| `PROVIDER_ROUTE_NOT_FOUND` | 404 | 指定 Provider 或运行时已配置路由不存在 |
| `PROVIDER_ROUTE_CONTROL_INVALID` | 422 | Provider 路由控制参数、操作者或变更理由无效 |
| `PROVIDER_ROUTE_CONTROL_CONFLICT` | 409 | Provider 路由控制版本已变化，需要刷新后重试 |
| `PROVIDER_LAST_ROUTE_DISABLE_FORBIDDEN` | 409 | 禁止停用 Provider 最后一条已配置路由 |
| `PROVIDER_ROUTES_DISABLED_BY_CONTROL` | 503 | Provider 所有运行时路由均被控制面停用，网关拒绝生成请求 |
| `YUDAO_MODEL_RESOLVE_FAILED` | 502 | yudao 模型解析失败 |
| `XINGHE_CRAWLER_FAILED` | 502 | Crawler Gateway 调用失败 |
| `XINGHE_KB_FAILED` | 502 | KB Service 调用失败 |

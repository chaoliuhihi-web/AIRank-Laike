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
| `EXPECTED_VERSION_REQUIRED` | 409 | 更新版本化对象时缺少当前 `expected_version` |
| `EXPECTED_VERSION_NOT_ALLOWED_ON_CREATE` | 409 | 创建对象时错误提交了仅用于更新的 `expected_version` |
| `STATE_VERSION_CONFLICT` | 409 | 客户端提交的版本已落后，必须重新读取后更新 |
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
| `EVIDENCE_REVIEW_CURSOR_INVALID` | 422 | 独立复核待办游标无法解码、版本不受支持或字段非法 |
| `EVIDENCE_REVIEW_ASSIGNMENT_NOT_FOUND` | 404 | 独立复核任务领取记录不存在或不属于当前租户 |
| `EVIDENCE_REVIEW_ASSIGNMENT_CONFLICT` | 409 | 当前动作已被另一审核人持久领取且租约仍有效 |
| `EVIDENCE_REVIEW_ASSIGNMENT_NOT_ACTIVE` | 409 | 领取记录已经完成、释放或过期，不能继续操作 |
| `EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED` | 409 | 当前审核人的领取租约已过期，需要重新领取 |
| `EVIDENCE_REVIEW_ASSIGNMENT_VERSION_CONFLICT` | 409 | case 或领取记录版本已变化，需要刷新后重试 |
| `EVIDENCE_REVIEW_ASSIGNMENT_OWNER_FORBIDDEN` | 403 | 当前账号不是领取人，不能续租或释放任务 |
| `EVIDENCE_REVIEW_TEAM_NOT_FOUND` | 404 | 审核团队不存在、不属于当前租户项目或已经停用 |
| `EVIDENCE_REVIEW_TEAM_NAME_CONFLICT` | 409 | 当前租户项目已存在同名审核团队 |
| `EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT` | 409 | 团队成员或角色路由版本已变化，需要刷新后重试 |
| `EVIDENCE_REVIEW_ROUTING_UNAVAILABLE` | 409 | 当前角色已配置路由，但目标团队未处于可用状态 |
| `EVIDENCE_REVIEW_ROUTING_FORBIDDEN` | 403 | 当前账号不是该角色已配置团队的有效成员 |
| `EVIDENCE_REVIEW_ROUTING_CAPACITY_REACHED` | 409 | 当前审核人的活跃领取数已经达到团队配置上限 |
| `EVIDENCE_REVIEW_YUDAO_BINDING_NOT_FOUND` | 404 | 审核团队的指定角色尚未绑定 Yudao 部门目录 |
| `EVIDENCE_REVIEW_YUDAO_SYNC_FAILED` | 503 | Yudao 审核目录未配置、鉴权失败、不可用或返回无效数据；失败运行会持久保存但不会把旧成员冒充已验证 |
| `EVIDENCE_REVIEW_ESCALATION_INVALID` | 409 | 持久升级事件不符合版本化 SLA Outbox 契约，拒绝展示为运营事实 |
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
| `EVIDENCE_GAP_QUALITY_BLOCKED` | 409 | 扫描未通过测量质量门禁，禁止生成可干预证据缺口 |
| `EVIDENCE_GAP_BASIS_INVALID` | 409 | 缺少完整不可变样本、证据 hash 或质量报告 hash，禁止推导缺口 |
| `EVIDENCE_GAP_NOT_FOUND` | 404 | 真实证据缺口不存在或不属于当前租户/项目 |
| `FACT_ACQUISITION_TASK_NOT_FOUND` | 404 | 事实补证任务不存在或不属于当前租户/项目 |
| `FACT_ACQUISITION_GAP_INELIGIBLE` | 409 | 缺口不是受治理的 v2 证据缺口、缺少 hash 或已经拥有事实证据 |
| `FACT_ACQUISITION_EVIDENCE_INVALID` | 409 | 补证来源不存在、失效、过期或未达到官方/已核验第三方权威门槛 |
| `FACT_ACQUISITION_TASK_VERSION_CONFLICT` | 409 | 补证任务版本已变化，客户端必须重新读取后提交 |
| `FACT_ACQUISITION_TASK_FINAL` | 409 | 补证任务已经解决，禁止覆盖不可变完成状态 |
| `OPPORTUNITY_SOURCE_EVIDENCE_REQUIRED` | 409 | 当前项目没有满足不可变性与质量门禁的跨域来源证据，禁止推导干预机会 |
| `OPPORTUNITY_DERIVATION_NOT_FOUND` | 404 | 干预机会推导运行不存在或不属于当前租户/项目 |
| `OPPORTUNITY_SNAPSHOT_NOT_FOUND` | 404 | 干预机会快照不存在或不属于当前租户/项目 |
| `OPPORTUNITY_ACTION_NOT_FOUND` | 404 | 机会行动任务不存在或不属于当前租户/项目 |
| `OPPORTUNITY_ACTION_VERSION_CONFLICT` | 409 | 机会行动任务版本已变化，客户端必须刷新后再操作 |
| `OPPORTUNITY_ACTION_OWNER_FORBIDDEN` | 403 | 机会行动已由其他责任人领取，当前用户不能变更 |
| `OPPORTUNITY_ACTION_FINAL` | 409 | 机会行动已完成复测确认或豁免，禁止覆盖最终状态 |
| `OPPORTUNITY_ACTION_TRANSITION_INVALID` | 409 | 行动状态转换不满足当前状态或最新证据条件 |
| `OPPORTUNITY_ACTION_VERIFICATION_REQUIRED` | 409 | 缺少更新且完整的机会推导运行，不能确认“本轮未再观察到” |
| `OPPORTUNITY_ACTION_TEAM_NOT_FOUND` | 404 | 机会行动团队不存在或不属于当前租户/项目 |
| `OPPORTUNITY_ACTION_TEAM_CONFLICT` | 409 | 同名机会行动团队已经存在 |
| `OPPORTUNITY_ACTION_MEMBER_VERSION_CONFLICT` | 409 | 机会行动团队成员版本已变化，必须刷新后更新 |
| `OPPORTUNITY_ACTION_ROUTE_VERSION_CONFLICT` | 409 | 机会来源路由版本已变化，必须刷新后更新 |
| `OPPORTUNITY_ACTION_ROUTING_BLOCKED` | 409 | 已启用团队路由，但该来源没有可用团队或成员 |
| `OPPORTUNITY_ACTION_ROUTING_FORBIDDEN` | 403 | 当前认证账号不是该机会来源路由团队的有效成员 |
| `OPPORTUNITY_ACTION_CAPACITY_REACHED` | 409 | 当前责任人的活动机会数达到团队成员容量上限 |
| `OPPORTUNITY_ACTION_DEPENDENCY_BLOCKED` | 409 | 当前行动仍有未满足的前置依赖，不能进入执行中 |
| `OPPORTUNITY_ACTION_DIRECTORY_BINDING_NOT_FOUND` | 404 | 机会交付团队尚未配置有效的 Yudao 目录绑定 |
| `OPPORTUNITY_ACTION_DIRECTORY_VERSION_CONFLICT` | 409 | 机会交付团队目录绑定版本已变化，必须刷新后更新 |
| `OPPORTUNITY_ACTION_DIRECTORY_BINDING_CHANGED` | 409 | 目录读取期间绑定已变化，旧快照不会写入成员投影 |
| `OPPORTUNITY_ACTION_DIRECTORY_SYNC_FAILED` | 503 | Yudao 目录真实同步失败，失败运行和错误分类已留痕 |
| `OPPORTUNITY_PLAN_VERSION_CONFLICT` | 409 | 机会执行计划版本已变化，必须刷新后再更新人工估算 |
| `OPPORTUNITY_DEPENDENCY_NOT_FOUND` | 404 | 机会行动依赖不存在或不属于当前租户项目 |
| `OPPORTUNITY_DEPENDENCY_INVALID` | 409 | 机会行动依赖无效，例如行动依赖自身 |
| `OPPORTUNITY_DEPENDENCY_CYCLE` | 409 | 新依赖会形成循环，或持久依赖图已无法拓扑排序 |
| `OPPORTUNITY_DEPENDENCY_VERSION_CONFLICT` | 409 | 机会行动依赖版本已变化，必须刷新后再豁免 |
| `OPPORTUNITY_CAPACITY_MEMBER_NOT_FOUND` | 404 | 容量日历对应的交付成员不存在、已停用或不属于当前租户项目 |
| `OPPORTUNITY_CAPACITY_CALENDAR_NOT_FOUND` | 404 | 指定成员尚未建立当前项目的容量日历 |
| `OPPORTUNITY_CAPACITY_VERSION_CONFLICT` | 409 | 容量日历版本已变化，必须刷新后再更新 |
| `OPPORTUNITY_CAPACITY_EXCEPTION_VERSION_CONFLICT` | 409 | 日期容量例外版本已变化，必须刷新后再更新 |
| `OPPORTUNITY_SCHEDULE_IDEMPOTENCY_CONFLICT` | 409 | 相同排程幂等键已被用于不同请求，不允许覆盖不可变排程 |
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

## 品牌实体图谱

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `BRAND_GRAPH_FACT_NOT_ELIGIBLE` | 409 | 实体、别名或关系未绑定当前已批准、有效、无冲突且具备有效来源的 FactRevision |
| `BRAND_GRAPH_BLOCKED` | 409 | 编译后缺少唯一无歧义目标品牌，禁止冻结为 ScanRun 测量口径 |
| `BRAND_GRAPH_SNAPSHOT_NOT_FOUND` | 404 | 图谱快照不存在或不属于当前租户 |
| `BRAND_ENTITY_NOT_FOUND` | 404 | 品牌图谱实体不存在或不属于当前租户项目 |
| `BRAND_ENTITY_DUPLICATE` | 409 | 项目中已存在相同角色、类型和规范化名称的实体 |
| `BRAND_ALIAS_NOT_FOUND` | 404 | 品牌别名不存在或不属于当前租户项目 |
| `BRAND_ALIAS_DUPLICATE` | 409 | 同一实体已存在相同规范化别名 |
| `BRAND_ALIAS_REDUNDANT` | 409 | 别名规范化后与所属实体标准名称相同 |
| `BRAND_RELATION_NOT_FOUND` | 404 | 品牌关系不存在或不属于当前租户项目 |
| `BRAND_RELATION_DUPLICATE` | 409 | 相同主体、谓词和客体的有方向关系已存在 |

## 引用支持度

| 错误码 | HTTP | 说明 |
| --- | --- | --- |
| `CITATION_NOT_FOUND` | 404 | 引用不存在，或不属于当前断言与样本 |
| `CITATION_NOT_FOUND_IN_SNAPSHOT` | 404 | 批量抓取中的引用不属于指定回答快照；整批不入队 |
| `ANSWER_SNAPSHOT_NOT_FOUND` | 404 | 回答快照不存在或不属于当前租户 |
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
| `EVIDENCE_INTEGRITY_AUDIT_NOT_FOUND` | 404 | 项目证据完整性巡检不存在 |
| `REPORT_EVIDENCE_INTEGRITY_BLOCKED` | 409 | 项目证据完整性巡检未通过，禁止生成客户证据包 |

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

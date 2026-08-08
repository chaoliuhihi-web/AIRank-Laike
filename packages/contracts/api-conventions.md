# AIRank API 约定

## 版本

第一版 API 统一使用：

```text
/api/v1
```

不提供无版本 API。后续破坏性变更进入 `/api/v2`。

## 认证

登录入口：

```text
POST /api/v1/auth/login
```

请求使用 `auth_login_request.schema.json`，响应使用 `auth_login_response.schema.json`。默认模式调用 yudao
`/admin-api/system/auth/login` 后再调用 `/admin-api/system/auth/get-permission-info` 解析用户；本地演示可显式设置
`AIRANK_AUTH_MODE=dev_only`，响应会标记 `dev_only=true`，不能冒充 release-ready。

请求头：

```text
Authorization: Bearer <yudao-token>
tenant-id: <tenant-id>
X-AIRank-Trace-Id: <optional-trace-id>
Idempotency-Key: <optional-key>
```

`tenant-id` 必须与 yudao token 解析出的租户一致。

## 响应格式

成功：

```json
{
  "data": {},
  "meta": {
    "trace_id": "trc_...",
    "request_id": "req_..."
  }
}
```

失败：

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invalid request",
    "details": {},
    "trace_id": "trc_..."
  }
}
```

## 分页

列表接口使用 cursor pagination：

```text
GET /api/v1/projects?limit=50&cursor=...
```

响应：

```json
{
  "data": [],
  "page": {
    "next_cursor": "next...",
    "has_more": true
  },
  "meta": {
    "trace_id": "trc_..."
  }
}
```

## M1 项目 / 竞品 / 买家问题

M1 问题治理通过同一套 repository 契约支持测试内存实现与生产 MySQL 持久化：

| Route | 说明 |
| --- | --- |
| `POST /api/v1/projects` | 根据网站和可选 hint 创建待确认项目，返回 `project_response.schema.json` |
| `POST /api/v1/projects/{project_id}/competitors` | 给项目追加候选竞品，返回 `competitor_response.schema.json` |
| `POST /api/v1/projects/{project_id}/buyer-questions` | 给项目追加候选买家问题，返回 `buyer_question_response.schema.json` |
| `POST /api/v1/projects/{project_id}/question-observation-batches` | 导入客户授权的 M1 观察记录；请求/响应分别使用 `question_observation_import_request.schema.json` 与 `question_observation_import_response.schema.json` |
| `GET /api/v1/projects/{project_id}/question-observation-batches` | 查询不可变观察批次、来源元数据、hash、可用记录/频次与 PII 阻断统计 |
| `GET /api/v1/projects/{project_id}/question-observation-batches/{batch_id}/records` | 查询批次内已通过 PII 门禁的安全问题记录；不返回被拦截原文 |
| `POST /api/v1/projects/{project_id}/question-maps/compile` | 预览或持久化版本化问题地图；持久化候选初始状态为 `suggested` |
| `GET /api/v1/projects/{project_id}/question-maps` | 查询不可变编译清单、输入/输出 hash 与编译统计 |
| `PATCH /api/v1/projects/{project_id}/buyer-questions/{question_id}/review` | 追加人工审核事件，并更新当前生命周期状态；不覆盖问题修订 |

`tenant_id`、导入人和审核人必须来自认证上下文，不能信任 request body。观察导入要求显式来源授权声明，按 payload SHA-256 幂等；`occurrence_count` 只表示来源内频次，不等于搜索量。疑似 PII 原文不得进入持久化记录、manifest 或响应。问题地图按输入内容和 taxonomy 版本幂等；问题按规范化 hash 去重。只有 `confirmed` 且其不可变修订 Cohort 与 ScanRun 完全一致的问题才能进入任务编译。in-memory adapter 只用于 contract test 和本地开发，MySQL 路径由 Alembic `20260808_0010` 支持。

## M2 扫描契约

`M2-WIN-000` 只冻结 scan run / scan task 的 request、response 和 status schema，不实现 worker 调度：

| Schema | 说明 |
| --- | --- |
| `scan_run_create_request.schema.json` | 创建一次扫描批次，指定项目、平台范围和问题范围 |
| `scan_run_response.schema.json` | 查询或创建后返回 run 状态 |
| `scan_task_response.schema.json` | 查询单个 provider/question 扫描任务状态 |
| `scan_task_list_response.schema.json` | 查询 scan run 下的任务状态列表 |

scan run 状态只允许 `queued`、`running`、`completed`、`failed`、`canceled`。scan task 状态只允许 `queued`、`running`、`completed`、`failed`、`skipped`。

每个已完成 ScanRun 可通过 `GET /api/v1/projects/{project_id}/scan-runs/{run_id}/quality-report` 重算 `airank.measurement-quality.v4`。响应使用 `measurement_quality_report_response.schema.json`，执行基础样本与分采集面证据检查；未提及必须保留在有效分母。每个问题、Provider、Cohort、采集面和模型口径必须有至少 3 个独立 sample index 和 session；单次样本或重用会话必须 `publishable=false`。每个样本都必须有独立 Evidence Manifest，且 `surface/evidence_level` 必须与任务一致：API 要求请求元数据、追踪 ID 和 Provider 请求审计；Web/App 除要求不可变截图对象与 SHA-256 外，采集器还必须确认进入全新会话，并明确来源面板 `captured/not_present`，有引用时还要绑定不可变来源面板对象；App 另需设备/App 环境元数据 hash；manual_import 另需导入源 hash。任一阻断检查失败时 `publishable=false`，报告只能保存为 `quality_blocked`，下载接口返回 `409 REPORT_QUALITY_BLOCKED`。

Provider 请求参数属于测量口径的一部分。每次 API 调用必须把实际 `request_kind`、`max_tokens`、上游字段名、temperature 和 reasoning effort 写入请求审计 metadata，并通过 `configuration_fingerprint` 关联版本化 Provider manifest/route；`20260808_0022` 把 manifest 默认值和 route 实际请求契约分别保存为 JSON，不保存密钥。配置指纹必须参与版本 ID，凭证轮换、请求类型或请求参数变化只能追加版本，不得覆盖历史审计关联。当前允许的请求类型为 `chat_completions`、`chat_completions_search` 和 `responses_web_search`；历史 manifest 的 `openai_chat` 只允许规范化为 `chat_completions`，显式未知环境值或 route 值失败关闭。HTTP 成功但最终回答为空时，原始上游响应、request ID、usage、终止元数据、时长和请求契约仍须进入失败 EvidenceSnapshot，样本状态保持 `failed` 且不得进入有效分母；如果上游已经返回 usage，则失败调用也必须进入用量账本。模型专属固定参数不得用一个全局默认覆盖；例如 Kimi K3 使用 `max_completion_tokens`、省略固定 temperature 并显式记录 reasoning effort，千问联网来源使用 `responses_web_search` 并要求从显式 `web_search_call`/usage 结构判定实际搜索。

Provider 引用只允许从版本化原生结构白名单提取。`airank.provider-native-citation.v2` 保存原生类型、精确原始响应 JSON path 和 native source ID；回答正文、调试字段或任意嵌套 URL 不得自动升级为 Citation。`airank.provider-search-evidence.v1` 必须把未请求、显式工具调用、显式 usage、显式无搜索和“已请求但不可验证”分开。Citation 被 Provider 选择不等于它支持回答；支持度仍需抓取不可变来源正文并完成独立人工复核。

客户交付使用不可变证据包，而不是仅记录“下载成功”：

```text
POST /api/v1/projects/{project_id}/evidence-integrity-audits
GET  /api/v1/projects/{project_id}/evidence-integrity-audits/latest
GET  /api/v1/projects/{project_id}/evidence-integrity-audits/{audit_id}
POST /api/v1/reports/{report_id}/evidence-packets
GET  /api/v1/reports/{report_id}/evidence-packets/latest
GET  /api/v1/evidence-objects/{object_ref_id}/content
```

项目级巡检当前使用 `airank.evidence-integrity.v2`。它保留 v1 对 AnswerSnapshot、EvidenceSnapshot、CitationCapture、CitationSourceSegment、KnowledgeSource、KnowledgeSourceSegment、FactRevision 以及非报告对象引用的 SHA-256、字节数、存储驱动、可用性和精确原文边界校验，并新增派生状态重建：ScanRun 的 `task_count` 必须由真实任务行重算；Retest 报告的质量门禁、对比指标、报告 SHA-256、报告状态、观察窗口结果和 RetestRun 摘要必须从原始任务、快照、请求审计、引用与最终审核状态确定性重建。任一源证据缺失或派生结果漂移均失败关闭。空项目和实体数超过 10,000 同样失败关闭；每个 verified/blocking finding 和按证据状态确定生成的 manifest SHA-256 都持久化，前端可按实体下钻。超过容量上限必须分片，不得把未检查实体视为通过；当前仅支持 ScanRun 与 Retest 报告派生重建，遇到其他报告类型会显式阻断，不能把旧 hash 当作重算证据。

生成接口必须携带每次客户导出动作唯一的 `Idempotency-Key`，操作者来自认证上下文；服务端再按完整内容 hash 去重，所以同一证据不会重复建包，而来源修订或有效期状态变化可以形成新的不可变版本。只有 `airank.measurement-quality.v4` 的基线和对比质量门禁均为 `publishable=true`、项目级 v2 证据与派生状态巡检全部通过，且报告具备可从基线/对比 run 重建的 `report_sha256`、样本索引和观察窗口 provenance 时才允许生成；巡检失败返回 `409 REPORT_EVIDENCE_INTEGRITY_BLOCKED`。当前新包使用 `airank.report-evidence-packet.v7`，内容寻址对象为确定性 `application/zip`：包含 canonical `manifest/report-evidence.json`、可打印但不含原始回答正文的 `report/report.html`、所有评分列保持空白的 `review/scorecard.csv`、使用边界 README 与逐文件 `SHA256SUMS`。manifest 保存完整派生报告记录、公式、限制项、风险、样本/引用/事实准确性/来源治理/对象索引、巡检摘要及巡检 manifest hash，离线校验器会重建 manifest 和 ZIP；但必须再用 API 或下载回执提供的整包 `content_sha256` 作为外部锚点，包内自洽不等于数字签名。事实与引用支持索引只接受 `production` 用途、不同审核人双人一致或第三人裁决后的最终结论，并保存 review case、审核角色、证据边界和记录 hash；`benchmark` 与旧单人审核只用于质量评估或历史追溯，不进入客户指标。来源治理索引按 Citation 精确 host 保存当前分类修订及其 hash，未分类、过期、未知权威、禁止用途和无法解析 host 分开进入限制项；治理覆盖不完整时仍可交付观测事实，但不得生成整体来源权威性结论。历史 v1/v2/v3/v4/v5/v6 包仍可下载；v1–v4 的 `integrity_audit_id` 为 `null`，v5 只代表 v1 源证据巡检，v6 代表 v2 派生重建但仍是单 JSON，均不会冒充当前 v7 离线评审包。原始回答仍通过样本详情和不可变证据对象下钻。客户端下载对象、校验整包 SHA-256 后，再调用下载回执接口。

事实准确性审核接口：

```text
GET  /api/v1/samples/{snapshot_id}/fact-accuracy
POST /api/v1/answer-claims/{claim_id}/fact-accuracy-reviews
POST /api/v1/projects/{project_id}/evidence-review-cases/fact-accuracy
POST /api/v1/evidence-review-cases/{case_id}/decisions
GET  /api/v1/projects/{project_id}/evidence-review-cases
GET  /api/v1/projects/{project_id}/evidence-review-inbox?limit=12&cursor=...
GET  /api/v1/projects/{project_id}/evidence-review-escalations?status=pending&limit=50
GET  /api/v1/projects/{project_id}/evidence-review-routing
POST /api/v1/projects/{project_id}/evidence-review-teams
PUT  /api/v1/projects/{project_id}/evidence-review-teams/{team_id}/members/{user_id}/{reviewer_role}
PUT  /api/v1/projects/{project_id}/evidence-review-routes/{reviewer_role}
PUT  /api/v1/projects/{project_id}/evidence-review-teams/{team_id}/sync-bindings/{reviewer_role}
POST /api/v1/projects/{project_id}/evidence-review-teams/{team_id}/sync-bindings/{reviewer_role}/runs
```

GET 响应使用 `fact_accuracy_bundle_response.schema.json`；项目质量队列使用 `evidence_review_queue_response.schema.json`，当前审核人的有界待办使用 `evidence_review_inbox_response.schema.json`。审核团队读写会暴露项目成员身份与容量，因此统一要求 `airank:review:admin`，操作者由认证中间件注入，不能信任客户端伪造头。inbox 只查询服务端判定为 `submit_secondary/adjudicate` 的任务，裁决优先、同优先级按最早创建顺序，使用不透明 seek cursor 而不是不稳定 offset；无效 cursor 返回 `422 EVIDENCE_REVIEW_CURSOR_INVALID`。没有角色路由时 inbox 保持 `unrestricted_legacy` 兼容；项目一旦配置任一路由，未配置的另一角色也失败关闭；只有两个角色都存在有效成员时整体状态才是 `team_routed`。仅当前团队中匹配角色的有效成员可见和领取任务，活跃且租约未过期的领取数达到成员上限时只保留本人已领取任务。`assignment-claims` 建立持久领取与租约：租约有效时其他审核人的 inbox 不返回该任务，直接提交决定也会冲突；同一领取人重复领取幂等返回现有 assignment。心跳只延长租约，不重置从动作可执行时间计算的 SLA；释放、过期与完成都会追加 assignment event，响应不返回 `assigned_to`，避免身份信息破坏盲审。审核团队可按角色绑定 Yudao 部门；目录适配器只读取 ID、用户名、显示名、部门和启用状态，Scheduler/Worker 共用版本化任务，内容未变不制造成员新版本，凭证不进入前端或数据库。Scheduler 为真实逾期 case 幂等写入 `evidence_review.sla_overdue.v1` Outbox，并保存角色路由快照；Webhook Consumer 通过 DNS 固定 HTTPS 出站、有限重试和不可变渠道回执交付。只有成功回执且 Outbox 为 published 时 `external_delivery_verified=true`，pending、失败或缺配置都不等同于人员已收到通知。真实 Yudao 和客户 Webhook 仍需生产凭证 E2E。旧单人 POST 仅保留兼容与历史取证，不进入商业指标。生产审核必须通过 evidence review case 创建第一审核，再由不同账号盲审；不一致时由第三个不同账号裁决。只有 `brand_fact` 与 `competitor_fact` 进入分母；`accurate/inaccurate/outdated` 必须由人工绑定当前已审核、公开或脱敏、未过期、无冲突的 FactRevision 及有效来源精确原文边界。`insufficient_evidence` 保留为证据缺口，不得按错误计分。只有全部事实声明都完成当前、确定性、最终 `production` 双人审核时才输出 `fact_accuracy`；事实或来源失效后旧审核自动退出商业指标，但不可变审核记录保留。`benchmark` 至少需要 20 个独立双人样本、全部终结且 Cohen's kappa 不低于 0.80 才通过审核质量门禁；benchmark 结论永不进入客户指标。

## M3 事实审核契约

可信事实卡审核接口：

```text
PATCH /api/v1/projects/{project_id}/facts/{fact_id}/review
```

请求使用 `fact_review_request.schema.json`，响应使用 `fact_review_response.schema.json`。`confirmed` 必须带至少一个可追溯 `source_refs`，其中 `citation_id`、`object_ref_id`、`source_url` 至少有一个。`needs_redaction` 映射为 `disclosure=redacted`，`private` 映射为 `disclosure=internal`。

AI 收录包接口：

```text
GET /api/v1/projects/{project_id}/asset-bundle
```

响应使用 `asset_bundle_response.schema.json`。当前返回数据库中的真实内容资产；尚未生成资产时，只允许把 `airank.evidence-gap.v2` 且有证据 hash 的缺口展示为待补事实入口，不能用 seed 或历史缺口冒充生产建议。

证据缺口接口：

```text
GET  /api/v1/projects/{project_id}/evidence-gaps
POST /api/v1/projects/{project_id}/evidence-gaps/derive
```

推导请求、结果和列表分别使用 `evidence_gap_derivation_request.schema.json`、`evidence_gap_derivation_response.schema.json` 与 `evidence_gap_list_response.schema.json`。服务端只从通过 `airank.measurement-quality.v4` 的不可变扫描样本推导 `airank.evidence-gap.v2`：同一问题、Provider、采集面必须拥有完整 sample index、至少 3 次独立会话、有效 AnswerSnapshot/EvidenceSnapshot hash，且每条都是正常有效的 `not_mentioned`。正常未提及样本不得删除；只是不满足该稳定缺口规则的分组不生成缺口。历史上未绑定证据 hash 的缺口只计入 `unverified_legacy_count`，不得直接进入内容建议。推导记录保存质量报告 hash、全量证据基础 hash、回答/证据/引用 ID 和可信操作者，支持按扫描运行与 Idempotency-Key 确定性重放。

### 事实补证任务

```text
GET  /api/v1/projects/{project_id}/fact-acquisition-tasks
POST /api/v1/projects/{project_id}/evidence-gaps/{gap_id}/fact-acquisition-tasks
POST /api/v1/projects/{project_id}/fact-acquisition-tasks/{task_id}/evidence-bindings
```

补证任务使用 `airank.fact-acquisition-task.v1`。只有绑定 `airank.evidence-gap.v2`、质量报告 hash 和证据基础 hash 的缺口才能创建任务；历史缺口或已经拥有事实证据的缺口必须失败关闭。每次状态变化写入带前序 hash 的追加事件。待审 FactRevision 只能把任务推进到 `in_review`；只有当前有效、人工审核通过、无开放冲突、可公开且其 KnowledgeSource 为 `official` 或 `verified_third_party` 的事实，才能把任务和缺口推进到 `ready_for_intervention`。任务完成不等同于内容生成、发布或模型推荐。

### 跨域干预机会

```text
GET  /api/v1/projects/{project_id}/opportunities
POST /api/v1/projects/{project_id}/opportunities/derive
```

机会接口使用 `airank.intervention-opportunity.v1` 和 `airank.cross-domain-opportunity-policy.v1`。每次推导从当前可核验的品牌可见度缺口、引用支持复核、事实治理记录与最新页面审计结果生成完整不可变快照，保存来源基础 hash、逐项证据 hash、逐项快照 hash 和前序运行。`priority_score` 只等于严重度、证据强度和紧迫度三个公开因子的加总，不是推荐率、品牌分或增长预测。相邻运行中的 `cleared` 只表示本轮未再观察到，不会自动把问题标为已解决；页面规则必须由同 URL 的更新审计证据证明已不再失败。品牌内容动作只有在对应 `airank.evidence-gap.v2` 已通过事实补证门禁后才可标记 `content_action_ready`。

完整推导允许在已有基线运行后生成 0 项机会的全空快照，以便真实记录所有前序机会“本轮未再观察到”；从未建立过机会基线且没有任何受治理来源证据时仍返回 `OPPORTUNITY_SOURCE_EVIDENCE_REQUIRED`，不会制造空成功。

### 机会行动台账

```text
GET  /api/v1/projects/{project_id}/opportunity-actions
POST /api/v1/projects/{project_id}/opportunities/{snapshot_id}/actions
POST /api/v1/projects/{project_id}/opportunity-actions/{action_id}/claims
POST /api/v1/projects/{project_id}/opportunity-actions/{action_id}/transitions
GET  /api/v1/projects/{project_id}/opportunity-action-routing
POST /api/v1/projects/{project_id}/opportunity-action-teams
PUT  /api/v1/projects/{project_id}/opportunity-action-teams/{team_id}/members/{user_id}
PUT  /api/v1/projects/{project_id}/opportunity-action-routes/{source_kind}
GET  /api/v1/projects/{project_id}/opportunity-action-directory-sync
PUT  /api/v1/projects/{project_id}/opportunity-action-teams/{team_id}/sync-binding
POST /api/v1/projects/{project_id}/opportunity-action-teams/{team_id}/sync-runs
GET  /api/v1/projects/{project_id}/opportunity-execution-portfolio
PUT  /api/v1/projects/{project_id}/opportunity-actions/{action_id}/plan
POST /api/v1/projects/{project_id}/opportunity-actions/{action_id}/dependencies
POST /api/v1/projects/{project_id}/opportunity-dependencies/{dependency_id}/waivers
```

行动使用 `airank.opportunity-action.v1`。只有最新完整推导中的不可变机会快照能创建每个稳定机会唯一的行动；默认截止日期由严重度映射，责任人通过认证身份自助领取，任务版本和 Idempotency-Key 阻止覆盖与重复副作用。`evidence_blocked` 即使已领取也不会自动转为执行中，必须由更新且 `ready_for_action` 的机会快照执行 `refresh_evidence`。`verify_not_observed` 只能绑定比来源更新的最新完整推导，并证明该稳定机会不在该次完整 manifest 中；`waive` 必须由责任人提供至少 20 字原因。两种终结都固定 `effect_claim_allowed=false`，不得解释为品牌推荐、增长或长期解决。所有状态变化写入带前序 hash 的追加事件。

行动团队路由使用 `airank.opportunity-action-routing.v1`，按四类 `source_kind` 配置交付团队。完全未配置时兼容 `unrestricted_legacy`；配置任一路由后，缺路由、停用/空团队、非成员与容量耗尽分别返回显式阻断。管理员操作要求 `airank:opportunity:admin`，成员领取只信任认证身份。手工成员固定 `external_membership_verified=false`，不能冒充 Yudao 目录证明。Scheduler 以 `opportunity_action.sla_overdue.v1` 记录逾期与无身份路由摘要；Outbox pending 不等于外部通知，只有通知 Consumer 的成功回执才使行动返回 `external_delivery_verified=true`。

交付成员目录使用 `airank.opportunity-action-directory-sync.v1`。一个团队只允许一个版本化 Yudao 部门绑定，凭证仅来自 API/Worker 进程环境，绑定、任务 payload、响应和审计均不得保存 token。Scheduler 派发 `opportunity.directory.sync` 时冻结 binding version；Worker 在外部调用前重检租户、项目、团队、部门和版本，任何漂移都失败关闭。同步只创建或更新 `membership_source=yudao` 的成员，目录未变化时不递增成员版本，目录中消失的外部成员才被停用；同 user ID 的手工成员保持原名称、容量、版本和 `external_membership_verified=false`，并在运行结果计入 `manual_conflict_count`。成功和失败运行都保存响应 hash、计数、错误分类与审计事件，但不保存外部正文或凭证。协议 fixture 通过不等于生产 Yudao 已验证。

执行计划与依赖使用 `airank.opportunity-execution-plan.v1`。计划写入、依赖创建和依赖豁免同样要求 `airank:opportunity:admin`；GET 只返回当前项目的人工计划、覆盖率、依赖阻断与拓扑层级。预算和工时仅为人工估算，只有所有未终结行动均存在 approved plan 时才计算组合汇总，任何响应都固定 `outcome_forecast_allowed=false`。依赖创建使用 `Idempotency-Key`，项目内图变更通过行动行锁串行化并拒绝自依赖、执行中目标和循环依赖。未满足依赖阻止 open 行动被领取为 `in_progress`，以及已领取的证据阻断行动刷新为执行中；最新完整复测仍可按独立观测证据终结行动。依赖豁免必须提交乐观锁版本、实质原因和非效果声明确认。

## 幂等

以下接口必须支持 `Idempotency-Key`：

- 创建 scan run
- 创建 publish package
- 生成报告
- 发起 retest
- 创建独立证据复核任务
- 生成报告证据包
- 从质量通过的扫描推导证据缺口
- 从受治理来源证据推导跨域干预机会快照
- 从最新机会快照创建、领取和复测终结行动
- 创建机会行动前置依赖
- 运行机会行动团队目录同步

幂等记录必须按 `tenant_id + idempotency_key + route` 隔离。

## 状态码

| HTTP | 用途 |
| --- | --- |
| 200 | 成功查询或更新 |
| 201 | 创建成功 |
| 202 | 异步任务已接收 |
| 400 | 请求格式或业务参数错误 |
| 401 | 未认证 |
| 403 | 无权限或租户不匹配 |
| 404 | 资源不存在 |
| 405 | HTTP 方法不支持 |
| 409 | 幂等冲突或状态冲突 |
| 422 | 字段校验失败 |
| 429 | 限流 |
| 500 | 未预期错误 |
| 502 | 外部服务失败 |
| 503 | 外部能力不可用 |

## 外部能力降级

当 yudao / Xinghe 能力失败：

- 必须返回统一错误码。
- 必须写 `airank_integration_capabilities` 或 adapter status。
- 如果有 fallback，应返回 fallback 结果并在 `meta` 中标记 `degraded=true`。

## 外部 AI 网页 Provider 预检

```text
GET /api/v1/provider-readiness
```

响应使用 `provider_readiness_response.schema.json`。每个平台必须显式返回 `probe_level` 和 `generation_verified`：浏览器日常预检只打开持久 profile 并确认是否能进入可输入问题的状态，标记为 `l2_interaction`，即使 `status=ready` 也不能推导为已完成回答；API 真实生成探针或 release L3 探针才标记为 `l3_generation`，且只有取得实质回答时 `generation_verified=true`。`status=blocked` 不会自动降级为 mock；生产环境必须先修复登录态、真人验证或入口 URL，再允许品牌检测生成报告。

`AIRANK_PROVIDER_MODE=browser` 时，品牌检测默认要求当前 scope 的 provider 全部完成；`AIRANK_MIN_PROVIDER_SUCCESS_COUNT` 只能用于已声明的部分平台 beta。真实采样未达到门槛时，接口返回 `INTEGRATION_CAPABILITY_BLOCKED`，不得生成可下载报告和发布包。

## 安全

- API 不返回密钥。
- 日志不输出 token、API Key、Cookie。
- 错误详情不暴露外部服务完整响应体。

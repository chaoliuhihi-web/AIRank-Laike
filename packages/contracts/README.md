# packages/contracts

AIRank 的机器契约层。

本包定义 AIRank 自有领域对象、API 输入输出、异步事件和与 `XingheAI2026V2` 的跨仓边界。任何跨应用、跨 worker、跨仓调用都应先在这里固化契约。

M1 已冻结的 API schema：

- `health_response.schema.json`
- `version_response.schema.json`
- `provider_readiness_response.schema.json`
- `auth_login_request.schema.json`
- `auth_login_response.schema.json`
- `console_action_request.schema.json`
- `console_action_response.schema.json`
- `console_overview.schema.json`
- `error_response.schema.json`
- `project_create_request.schema.json`
- `project_response.schema.json`
- `competitor_create_request.schema.json`
- `competitor_response.schema.json`
- `buyer_question_create_request.schema.json`
- `buyer_question_response.schema.json`
- `scan_run_create_request.schema.json`
- `scan_run_response.schema.json`
- `scan_task_response.schema.json`
- `scan_task_list_response.schema.json`
- `fact_review_request.schema.json`
- `fact_review_response.schema.json`
- `asset_bundle_response.schema.json`
- `evidence_gap.schema.json`
- `evidence_gap_derivation_request.schema.json`
- `evidence_gap_derivation_response.schema.json`
- `evidence_gap_list_response.schema.json`
- `fact_acquisition_task.schema.json`
- `fact_acquisition_task_create_request.schema.json`
- `fact_acquisition_evidence_bind_request.schema.json`
- `fact_acquisition_task_response.schema.json`
- `fact_acquisition_task_list_response.schema.json`
- `report_list_response.schema.json`
- `download_receipt_response.schema.json`
- `fact_accuracy_bundle_response.schema.json`
- `evidence_review_case_response.schema.json`
- `evidence_review_queue_response.schema.json`
- `evidence_review_inbox_response.schema.json`
- `evidence_review_assignment_response.schema.json`
- `evidence_review_escalation_response.schema.json`
- `evidence_review_routing_response.schema.json`

双人证据复核契约同时服务引用支持与事实准确性：第一审核、第二审核和第三人裁决账号必须互不相同；待终结任务对其他审核人隐藏既有标签与依据。`production` 任务只有双人一致或完成裁决后才能进入商业指标，`benchmark` 任务只计算一致率与 Cohen's kappa。actor-specific inbox 只返回当前账号可执行任务，采用不透明 seek cursor，每页最多 50 条并优先争议裁决；它不承担全项目质量统计。assignment 契约保存持久领取、租约、SLA、心跳、释放和过期状态，但不向其他审核人暴露领取者身份。review routing 契约按项目保存审核团队、角色成员、并发上限与 secondary/adjudicator 路由：没有任何路由时显式兼容 `unrestricted_legacy`，一旦配置则只有有效团队成员可以领取；手工成员不得冒充 Yudao 已同步。团队可按角色绑定 Yudao 部门；同步只落库审核身份所需字段、响应 hash 和变更计数，服务凭证不进入契约、数据库或前端。SLA escalation 先证明逾期事件及路由快照已进入持久 Outbox；只有 HTTPS Webhook Consumer 得到 2xx 并保存不可变渠道回执后，`external_delivery_verified` 才能为 `true`。pending、失败、无渠道配置或仅有 Outbox 状态不得写成已通知。当前商业门禁仍要求真实 Yudao/客户 Webhook E2E，以及至少 20 个已完成双人样本且 kappa 不低于 0.80。

后续领域 schema：

- `ai_answer_snapshot.schema.json`
- `fact_atom.schema.json` — 可信事实卡的内部最小事实单元（FactAtom）
- `fact_store.schema.json` — 企业事实库条目
- `competitor_suppression.schema.json` — 竞品压制分析
- `asset_bundle.schema.json` — AI 收录包 / AI 推荐资产包
- `publish_record.schema.json` — 发布记录和状态机
- `retest_report.schema.json`
- `executive_report.schema.json`

与星河主仓对接时，本包是唯一事实源；`packages/xinghe-adapter` 负责把这些契约转换为星河侧 API 或 job payload。

工程约定：

- API 版本、分页、幂等、响应和错误 envelope 见 `api-conventions.md`。
- 统一错误码注册表见 `error-codes.md`。
- 事件 schema 从 M2 开始由 MySQL outbox runtime 分发；M1 只先固化 schema 和命名。

# packages/contracts

AIRank 的机器契约层。

本包定义 AIRank 自有领域对象、API 输入输出、异步事件和与 `XingheAI2026V2` 的跨仓边界。任何跨应用、跨 worker、跨仓调用都应先在这里固化契约。

M1 已冻结的 API schema：

- `health_response.schema.json`
- `version_response.schema.json`
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

后续领域 schema：

- `ai_answer_snapshot.schema.json`
- `fact_atom.schema.json` — 可信事实卡的内部最小事实单元（FactAtom）
- `fact_store.schema.json` — 企业事实库条目
- `competitor_suppression.schema.json` — 竞品压制分析
- `evidence_gap.schema.json` — 内容/信源缺口（推荐证据缺口）
- `asset_bundle.schema.json` — AI 收录包 / AI 推荐资产包
- `publish_record.schema.json` — 发布记录和状态机
- `retest_report.schema.json`
- `executive_report.schema.json`

与星河主仓对接时，本包是唯一事实源；`packages/xinghe-adapter` 负责把这些契约转换为星河侧 API 或 job payload。

工程约定：

- API 版本、分页、幂等、响应和错误 envelope 见 `api-conventions.md`。
- 统一错误码注册表见 `error-codes.md`。
- 事件 schema 从 M2 开始由 MySQL outbox runtime 分发；M1 只先固化 schema 和命名。

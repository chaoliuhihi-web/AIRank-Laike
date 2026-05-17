# 与 XingheAI2026V2 的整合策略

## 结论

AIRank 与 `XingheAI2026V2` 的关系应是：

```text
AIRank 独立产品仓
  -> 自有领域模型、自有 API、自有 worker、自有最小事实库
  -> 通过 contracts / xinghe-adapter 选择性调用 XingheAI2026V2 能力

XingheAI2026V2 主仓
  -> 保留 yudao、Crawler Gateway、KB/Qdrant、Brand Corpus、workflow-runner、Hermes、内容生产与治理能力
  -> 不承载 AIRank 完整产品实现
```

这能同时满足两个目标：

- AIRank 可以面向企业品牌方快速开发、独立部署、独立收费。
- 星河既有能力可以被产品化复用，但不会把历史复杂度整块搬进新仓。

## XingheAI2026V2 当前可复用能力

基于当前 `XingheAI2026V2 origin/main`：

| 能力 | 主仓落点 | AIRank 用法 | 接入状态 |
| --- | --- | --- | --- |
| 认证、租户、权限 | `vendor/xingheai-yudao`、`xingheai/services/shared/bridges/auth.py` | 企业账号、租户隔离、权限校验 | `ready` |
| 模型配置 | `vendor/xingheai-yudao`、`/ai/model/resolve` | 模型 key 权威源和默认模型解析 | `partial` |
| 五层规格和机器契约 | `xingheai/specs/contracts/v1`、`xingheai/specs/scenarios/v1`、`xingheai/specs/workflows/v1` | 定义 `SCN-AIRANK-01`、输出 schema、workflow contract | `ready` |
| Crawler Gateway | `xingheai/services/admin-console/backend/app/modules/crawler_gateway/` | 官网、竞品、第三方信源抓取、快照、blocked reason、审计 | `partial` |
| KB / Qdrant | `xingheai/services/kb-service` | 可信事实库、来源片段、引用追溯、向量召回 | `partial` |
| Brand Corpus | `xingheai/services/creator-marketing/backend/modules/campaign/brand_corpus_public_*` | 品牌资料、审校队列、导出包、知识回流经验 | `partial` |
| 报告证据包 | `creator-marketing` project report evidence/source-index/download receipts | AIRank 高管报告证据包、下载回执、验收链路 | `ready` |
| workflow-runner | `xingheai/services/workflow-runner` | 长任务编排经验，后续可接远程 job | `partial` |
| Hermes | `vendor/hermes-agent`、`xingheai/services/shared/bridges/hermes` | 自动巡检、来源可信度策略、周期复测和报告自动化 | `partial` |
| 智能出版内容生产 | 出版主线与营销内容生成链路 | FAQ、选型指南、案例页、对比页生成 | `partial` |

`partial` 的含义不是不能用，而是不能作为 AIRank MVP 的唯一运行前提。AIRank 必须有自有 fallback。

## 不允许的整合方式

- 不把 AIRank 作为 `XingheAI2026V2/xingheai/services/airank` 子目录开发。
- 不直接 import `XingheAI2026V2` 的 Python/TS 内部模块。
- 不复制 `XingheAI2026V2` 的 `.runtime`、出版门禁、营销 demo、历史数据和完整服务目录。
- 不让 AIRank 的上线依赖主仓某个本地路径存在。
- 不把 Qdrant 当主存，不把 `.runtime` 当长期真相源。

## 正确整合层

AIRank 仓只保留一个跨仓边界：

```text
packages/xinghe-adapter/
```

该包负责：

1. 能力发现：读取或探测星河侧服务是否 ready。
2. 契约转换：把 AIRank 领域对象转为星河侧 OpenAPI / JSON Schema / job payload。
3. 状态降级：星河能力不可用时返回 `partial` 或 `blocked`，不伪装成功。
4. 证据保留：所有调用记录 `trace_id`、`run_id`、输入摘要、输出摘要、失败原因。

## AIRank 自有内核

即使星河能力不可用，AIRank 第一版也要能跑：

| AIRank 自有包 | 作用 |
| --- | --- |
| `packages/domain` | 品牌项目、竞品、问题、扫描、事实、缺口、内容、报告的领域模型 |
| `packages/score` | AIRank 来客指数计算 |
| `packages/evidence` | AI 回答快照、引用来源、证据包、source index |
| `packages/crawler-lite` | 官网抓取、sitemap、半自动采样、URL 快照 |
| `packages/kb-lite` | 可信事实库最小存储、事实卡、轻量检索 |
| `apps/worker` | 扫描、归因、内容生成、发布包、复测 |

这条自有内核保证部署不会严重依赖 `XingheAI2026V2`。

## 契约映射

建议在 AIRank 仓先定义：

```text
packages/contracts/schemas/
  airank_project.schema.json
  competitor.schema.json
  buyer_question.schema.json
  ai_scan_run.schema.json
  ai_answer_snapshot.schema.json
  fact_atom.schema.json
  content_gap.schema.json
  content_asset.schema.json
  publish_package.schema.json
  retest_report.schema.json
  executive_report.schema.json

packages/contracts/events/
  scan.requested.json
  scan.completed.json
  fact_atom.confirmed.json
  content_asset.generated.json
  publish_package.exported.json
  retest.completed.json
```

后续如需回写 `XingheAI2026V2`，只在主仓增加薄层：

```text
xingheai/specs/scenarios/v1/SCN-AIRANK-01.yaml
xingheai/specs/outputs/v1/SCN-AIRANK-01.output.schema.json
xingheai/specs/workflows/v1/WFS-AIRANK-01-*.workflow.yaml
xingheai/services/shared/bridges/airank/
```

主仓不放 AIRank 页面和业务实现。

## 接入优先级

### Phase 0：独立 MVP

- 使用 AIRank 自有 API、worker、crawler-lite、kb-lite。
- 用半自动扫描覆盖中文 AI 平台。
- 保存回答快照、引用来源、人工确认记录。
- 输出诊断包和高管报告。

### Phase 1：契约对齐

- 固化 AIRank JSON Schema 和 OpenAPI。
- 在 `packages/xinghe-adapter/status` 记录每个星河能力状态。
- 可选在 `XingheAI2026V2` 增加 `SCN-AIRANK-01` 薄场景规格。

### Phase 2：能力替换

- 用 Crawler Gateway 替换 crawler-lite 的复杂抓取。
- 用 KB/Qdrant 替换 kb-lite 的检索。
- 用 yudao 替换 AIRank 自有账号/租户。
- 用 Brand Corpus / 内容工厂增强事实卡和内容资产生产。

### Phase 3：自动化运营

- 接入 Hermes 做周期扫描、复测、异常提醒和报告自动化。
- 接入 workflow-runner 做跨服务长任务编排。
- 形成企业客户月度 AI 搜索增长运营闭环。

## 能力状态格式

`packages/xinghe-adapter/status` 应输出统一能力状态：

```json
{
  "capability": "crawler_gateway",
  "status": "partial",
  "source": "xingheai2026v2",
  "checked_at": "2026-05-17T00:00:00Z",
  "required_for_mvp": false,
  "endpoint": "/api/crawler-gateway/runtime-status",
  "blocked_reason": "",
  "fallback": "packages/crawler-lite"
}
```

## 数据边界

AIRank 自己的长期真相源：

- `airank_projects`
- `competitors`
- `buyer_questions`
- `scan_runs`
- `answer_snapshots`
- `source_citations`
- `fact_atoms`
- `content_gaps`
- `content_assets`
- `publish_packages`
- `retest_runs`
- `executive_reports`
- `leads`

星河侧只作为外部能力和外部证据来源，不拥有 AIRank 产品主数据。

## 最重要的工程红线

如果某项星河能力尚不稳定，AIRank 不等待它完善；先用自有最小能力跑通，再逐步替换。

这条路线比“整块拷贝 XingheAI2026V2”更稳，因为它把有价值能力抽取出来产品化，同时避免把出版、营销、发布门禁和历史 runtime 复杂度带进 AIRank。

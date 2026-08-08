# AIRank 来客

企业 AI 搜索来客增长平台。

AIRank 来客帮助企业发现 AI 搜索里的客户机会，分析竞品为什么被推荐，沉淀品牌可信事实，生产可审校、可发布、可复测的可信内容资产，并持续追踪品牌在 AI 搜索里的可见度、推荐机会和排名表现。

## 核心判断

AIRank 不能做成普通 AI 排名查询工具，也不能做成普通内容生成工具。第一版必须围绕可收费闭环：

1. 品牌项目建档
2. 竞品管理
3. AI 来客问题地图
4. 多 AI 平台扫描与回答快照
5. AIRank 来客指数
6. 竞品压制与引用来源归因
7. 品牌可信事实库与可信事实卡
8. 内容缺口工厂
9. FAQ / 选型指南 / 案例页生成
10. 发布包导出与发布状态记录
11. 复测增长报告
12. 高管报告

## 仓库定位

本仓是 AIRank 来客的独立产品仓。它不依赖 `XingheAI2026V2` 的内部代码路径运行。

`XingheAI2026V2` 的合理角色是能力供应方：

- yudao：租户、权限、账号、模型配置权威源
- Crawler Gateway：官网、竞品、第三方信源抓取与快照
- KB / Qdrant：可信事实库、引用和检索能力
- Brand Corpus：品牌语料、审校、导出、知识回流经验
- workflow-runner：长任务编排经验
- Hermes：巡检、自动化、报告和多 Agent 运营
- 智能出版能力：可信内容资产生产、审校、导出、发布包

所有跨仓复用通过 `packages/contracts` 和 `packages/xinghe-adapter` 完成。

## 目录总览

```text
apps/
  web/                 对外官网、免费测一测、客户控制台
  api/                 AIRank 产品 API，负责租户、项目、扫描、事实库、报告
  worker/              扫描、归因、内容生成、发布复测等异步任务
  scheduler/           到期复测窗口调度、终态比较与报告触发
  review-console/      审核、风险、验收和多 Agent 审查台

packages/
  contracts/           AIRank JSON Schema / OpenAPI / 事件契约
  domain/              品牌项目、问题地图、扫描、可信事实卡内部事实元、事实库、报告等领域模型
    src/
      fact-atom/       可信事实卡的内部最小事实单元（FactAtom）
      fact-store/      企业事实库
      gap/
        suppression/   竞品压制分析
        evidence-gap/  内容/信源缺口（页面可叫推荐证据缺口）
      publishing/      发布状态机和渠道管理
  score/               AIRank 来客指数和指标计算
  evidence/            回答快照、引用来源、证据包、下载回执
  crawler-lite/        AIRank 自有轻量抓取与半自动采样
  kb-lite/             AIRank 自有最小事实库和检索索引
  xinghe-adapter/      对接 XingheAI2026V2 的唯一边界
  ui/                  共享 UI 组件、图表和控制台视觉系统

docs/
  product/             PRD、素材分析、MVP 范围和商业包装
  architecture/        架构、目录、XingheAI2026V2 整合策略
  decisions/           架构决策记录、术语映射表
  handoff/             多 Agent 交接、开发计划、验收记录

agents/
  dev/                 开发 Agent 任务说明和执行记录
  review/              审核 Agent 任务说明和检查清单
  prompts/             可复用提示词

tests/
  acceptance/          真实用户主链路验收
  contracts/           契约兼容性测试
  fixtures/            样例企业、竞品、问题、扫描结果

ops/
  deployment/          部署、环境变量、发布与回滚
  runbooks/            运维手册、故障处理、巡检

scripts/               开发和运维辅助脚本
```

## 当前素材

原始素材暂保留在 `AIRank素材/`，不做移动：

- `AIRank素材/Web宣传/`：已经整理好的官网宣传页方向，包括首页、产品能力、解决方案、客户案例、免费体检、定价、资源中心。
- `AIRank素材/操作台/*.png`：后台控制台页面方向。
- `AIRank素材/需求文档PRDv0.1/`：旧版 PRD，可作为演进参考。
- `AIRank素材/废弃/`：废弃视觉方案，不进入第一版开发基线。

本轮开始时曾读取到根目录下的 v4.0 PRD，并已把关键结论沉淀到 `docs/product/material-analysis.md`、`docs/product/mvp-scope.md` 和架构文档中；当前可见文件列表里该根目录 PRD 已不在，后续如要入库可再放回 `docs/product/source/`。

详见 `docs/product/material-analysis.md`。

## 第一阶段工程目标

30 天内做出可收费 MVP：

- 可以录入一个企业品牌项目和 3-10 个竞品。
- 可以生成 50 个高购买意图问题。
- 可以半自动或自动完成多平台扫描，并保存回答快照。
- 可以输出 AIRank 来客指数、竞品压制分析和引用来源归因。
- 可以建立可信事实库和可信事实卡。
- 可以生成 FAQ、选型指南、案例页三类内容资产。
- 可以导出发布包，记录发布 URL 和状态。
- 可以按同一批问题复测，并生成高管报告。

第一阶段不做复杂权限、复杂计费、代理商后台、白标、完整 CMS、无审核全自动发布。

## 开发入口

- 总体架构评审稿：`docs/architecture/overall-architecture-review.md`
- 工程化补强：`docs/architecture/observability.md`、`docs/architecture/security.md`、`docs/architecture/migration-strategy.md`、`docs/architecture/eventing-outbox.md`、`docs/architecture/ci-quality-gates.md`
- API 约定和错误码：`packages/contracts/api-conventions.md`、`packages/contracts/error-codes.md`
- 能力评估：`docs/architecture/capability-assessment.md`
- MySQL 建库方案：`docs/architecture/mysql-schema-plan.md`
- 建库脚本：`ops/deployment/mysql-bootstrap.sql`
- 环境变量样例：`ops/deployment/env.example`
- 详细开发计划：`docs/handoff/development-plan.md`

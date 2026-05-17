# apps/worker

AIRank 异步任务。

任务类型：

- **scan** — AI 平台扫描和半自动采样导入
- **attribution** — 引用来源归因
- **fact-extract** — 资料到可信事实卡内部事实元（FactAtom）
- **content** — 内容资产生成，按 4 大类组织：
  - `website/` — 官网资产（事实页、服务页、案例页、FAQ、对比页、价格页、方案页）
  - `platform/` — 平台资产（公众号、知乎、小红书、视频号、百家号、行业媒体稿）
  - `schema/` — 结构化资产（JSON-LD、sitemap、robots、canonical）
  - `sales/` — 销售承接资产（销售 FAQ、异议处理、话术、成功故事、来客助手回答库）
- **publish** — 发布包生成和发布状态追踪
- **retest** — 复测
- **report** — 高管报告生成

任务失败必须有结构化原因，不能长期停留在 `queued`。

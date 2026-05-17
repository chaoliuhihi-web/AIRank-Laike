# AIRank 素材分析

## 已读依据

- 本轮开始时曾读取到 `AIRank素材/airank来客_prd_v_3_可信事实资产版.md`，文件标题为 `AIRank 来客 PRD v4.0`。当前素材目录已被整理，该文件不在当前可见列表中，关键结论已沉淀在本文和 `mvp-scope.md`。
- `AIRank素材/需求文档PRDv0.1/airank来客_prd_v_3_可信事实资产版 (1).md`
- `AIRank素材/Web宣传/首页.png`
- `AIRank素材/Web宣传/产品能力.png`
- `AIRank素材/Web宣传/解决方案.png`
- `AIRank素材/Web宣传/客户案例.png`
- `AIRank素材/Web宣传/免费体检.png`
- `AIRank素材/Web宣传/定价.png`
- `AIRank素材/Web宣传/资源中心.png`
- `AIRank素材/操作台/ChatGPT Image 2026年5月17日 09_52_28 (1).png`
- `AIRank素材/操作台/ChatGPT Image 2026年5月17日 09_52_28 (2).png`
- `AIRank素材/操作台/ChatGPT Image 2026年5月17日 09_52_28 (3).png`
- `AIRank素材/操作台/ChatGPT Image 2026年5月17日 09_52_28 (4).png`
- `AIRank素材/操作台/ChatGPT Image 2026年5月17日 09_52_28 (5).png`
- `AIRank素材/操作台/ChatGPT Image 2026年5月17日 09_52_28 (6).png`

## 当前可见素材结构

```text
AIRank素材/
  Web宣传/
    首页.png
    产品能力.png
    解决方案.png
    客户案例.png
    免费体检.png
    定价.png
    资源中心.png
  操作台/
    ChatGPT Image 2026年5月17日 09_52_28 (1).png
    ChatGPT Image 2026年5月17日 09_52_28 (2).png
    ChatGPT Image 2026年5月17日 09_52_28 (3).png
    ChatGPT Image 2026年5月17日 09_52_28 (4).png
    ChatGPT Image 2026年5月17日 09_52_28 (5).png
    ChatGPT Image 2026年5月17日 09_52_28 (6).png
  需求文档PRDv0.1/
    airank来客_prd_v_3_可信事实资产版 (1).md
  废弃/
```

## 产品核心

主 PRD 已从“AI 推荐证据链版”推进到“可信事实资产版”。产品主线不是查看排名，而是把 AI 搜索里的客户机会转成可交付增长动作：

```text
AI 来客体检
-> 竞品压制分析
-> 品牌可信事实库
-> 可信事实卡
-> 内容缺口工厂
-> 智能出版式可信内容生产
-> 审核确认
-> 发布 / 分发
-> 复测增长
-> 高管报告
```

这个闭环决定工程目录不能只按页面拆，也不能只按“爬虫 + 报表”拆。目录必须显式承载扫描、事实、证据、内容、发布、复测和报告。

## 对外站分析

`Web宣传/首页.png` 方向更适合作为第一版官网首页：

- 品牌信号清楚：`智界问道 | AIRank 来客`
- 首屏 offer 明确：客户问 AI，别让竞品先出现
- 转化入口直接：输入官网，免费测一测
- 结果感强：AIRank Score、AI 可见性、竞品压制、推荐门槛、线索增长
- 页面叙事简单：痛点 -> 四步启动 -> 自动建库 -> CTA

`Web宣传/产品能力.png`、`Web宣传/解决方案.png`、`Web宣传/客户案例.png`、`Web宣传/免费体检.png`、`Web宣传/定价.png`、`Web宣传/资源中心.png` 已经形成官网二级页雏形。第一版 `apps/web` 可以先按这些页面名预留 marketing routes，但开发优先级仍应是首页和免费体检转化。

## 后台控制台分析

操作台素材已经给出完整产品 IA：

```text
工作台
AI 收录体检
企业事实库
买家问题地图
推荐门槛
AI 收录包
发布提交
AI 销售助手（后续工程统一命名为 AI 来客助手）
线索看板
报表中心
设置中心
```

这些页面可以映射到第一版 `apps/web` 的控制台路由，也可以映射到 `apps/api` 的领域模块：

| 页面 | 领域对象 | 第一版工程落点 |
| --- | --- | --- |
| 工作台 | 项目总览、平台表现、缺口、线索、复测趋势 | `domain/projects`、`domain/reports` |
| AI 收录体检 | 扫描任务、问题、平台回答、引用来源 | `domain/scans`、`worker/scanners` |
| 企业事实库 | 企业事实、事实确认、资料来源 | `domain/facts`、`kb-lite` |
| 买家问题地图 | 问题分类、商业意图、覆盖状态 | `domain/questions` |
| 推荐门槛 | 内容缺口、证据差距、竞品对比 | `domain/gaps`、`score` |
| AI 收录包 | 内容资产、结构化数据、sitemap | `domain/assets`、`evidence` |
| 发布提交 | 发布包、发布 URL、抓取与索引状态 | `domain/publishing`、`worker/publish` |
| AI 销售助手 / AI 来客助手 | 对话、推荐话术、线索生成 | `domain/leads`、`domain/assistant` |
| 线索看板 | 线索、渠道、意向等级、转化漏斗 | `domain/leads` |
| 报表中心 | 体检报告、复测报告、高管报告 | `domain/reports`、`evidence` |

## 第一版要保留的视觉约束

- 对外站：浅蓝白、科技感、强 CTA，避免复杂营销长页先行。
- 控制台：深色侧栏 + 白底数据工作区，适合 B 端长期使用。
- 页面必须工作化，不要做成纯展示大屏。
- 控制台卡片可以使用，但不要卡片套卡片；表格、趋势、漏斗和状态流转要可扫描。
- 图标和状态颜色需要服务业务判断：ready / partial / blocked / failed / reviewed。

## 工程含义

素材说明 AIRank 同时有两个产品面：

1. `public growth site`：获客、免费体检、案例、方案、报价。
2. `operator console`：项目交付、扫描、事实库、内容资产、发布、复测、报告。

因此第一版建议只保留一个 `apps/web`，内部按路由分为 `marketing` 和 `console`，避免过早拆出两个前端工程。

后台必须从一开始区分：

- 产品 API：租户、项目、问题、扫描、事实、内容、报告。
- Worker：慢任务、扫描、抓取、内容生成、发布复测。
- Review Console：事实确认、竞品风险、发布前审核、报告验收。

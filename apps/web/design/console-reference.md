# AIRank Console Reference

本文件把 `AIRank素材/操作台` 的页面稿转成工程实现参考。PNG 只作为设计输入，不进入运行时 `src/assets`，前端必须用真实组件、真实路由、真实接口和可复用图表实现。

视觉要求：页面色彩、图标风格、字体层级、字重、行高、间距、圆角、阴影、侧栏宽度、卡片密度和图表风格都必须以效果图为准，不允许重配色、不允许换成另一套 UI 风格。

## Source Images

| Source | Recommended route | Page purpose | Priority |
| --- | --- | --- | --- |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_02 (1).png` | `/console` | 工作台总览、下一步建议、趋势和机会概览 | M1 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_03 (2).png` | `/console/checkup` | AI 收录体检、多平台检测、竞品压制原因 | M1 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_03 (3).png` | `/console/facts` | 企业事实库、可信事实卡分类、确认状态 | M1 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_04 (4).png` | `/console/questions` | 买家问题地图、问题分组、推荐缺口和建议资产 | M1 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 12_51_04 (5).png` | `/console/gaps` | 推荐缺口总览、证据覆盖雷达、缺口清单 | M1 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_07 (1).png` | `/console/gaps/questions` | 按问题维度看本品牌和竞品推荐差距 | M1 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_08 (2).png` | `/console/assets` | AI 收录包、内容资产、结构化资产和完整度 | M1 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_08 (3).png` | `/console/publishing` | 发布提交中心、发布渠道、抓取、索引和复测队列 | M1.5 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_09 (4).png` | `/console/assistant` | AI 来客助手、知识源、话术、线索规则 | P2 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_10 (5).png` | `/console/reports` | 报表中心、KPI、趋势、报告列表和行动建议 | M1.5 |
| `AIRank素材/操作台/ChatGPT Image 2026年5月17日 13_41_11 (6).png` | `/console/settings` | 项目设置、品牌资料、平台接入、通知、成员权限 | M1.5 |

## Implementation Position

这些页面稿应该进入工程的方式是：

1. 保留原图在 `AIRank素材/操作台`，作为产品和验收参考。
2. 把路由、组件、接口和状态写进 `apps/web`，不要把整张图复制成前端背景。
3. 控制台页面统一使用 `ConsoleShell`，只在页面主区切换业务模块，并保持效果图的侧栏、主区和右栏比例。
4. 图表必须由数据驱动，M1 可以先接真实 API 或显式 mock fixture，不能把图表截图切片。
5. 客户界面用“可信事实卡”，工程内部对象仍叫 `FactAtom`。
6. 视觉 token 只能从这些效果图抽取或微调，不能引入 shadcn 默认灰、Ant Design 默认蓝、Material 默认圆角等外部默认风格。

建议的前端目录：

```text
apps/web/src/
  console/
    layout/
      ConsoleShell.tsx
      SidebarNav.tsx
      PageHeader.tsx
      ProjectSummaryStrip.tsx
    routes/
      dashboard/DashboardPage.tsx
      checkup/CheckupPage.tsx
      facts/FactsPage.tsx
      questions/QuestionsPage.tsx
      gaps/GapsPage.tsx
      gaps/GapQuestionsPage.tsx
      assets/AssetsPage.tsx
      publishing/PublishingPage.tsx
      reports/ReportsPage.tsx
      settings/SettingsPage.tsx
      assistant/AssistantPage.tsx
    components/
      MetricCard.tsx
      StatusBadge.tsx
      EvidenceBadge.tsx
      DataTable.tsx
      RightRail.tsx
      DonutChart.tsx
      RadarChart.tsx
      TrendChart.tsx
      ProgressStepper.tsx
      AssetCard.tsx
      ReportCard.tsx
      SettingsSection.tsx
    services/
      console-api.ts
    fixtures/
      console-demo.ts
```

## Shared Shell

所有操作台页面共用同一套骨架：

| Area | Implementation guidance |
| --- | --- |
| Sidebar | 按效果图保留约 255px 宽深色侧栏、品牌区、主导航、底部帮助和企业切换区。导航项包括工作台、AI 收录体检、企业事实库、买家问题地图、推荐缺口分析、AI 收录包、发布与复测、AI 来客助手、报表中心、设置中心。 |
| Header | 按效果图保留页面标题、业务结论、日期或主操作按钮。标题区不要做营销大字，要保持 B 端操作台密度。 |
| Project strip | 按效果图展示官网、行业、竞品、目标客户类型、当前项目状态。页面可选择展示，但数据对象应统一。 |
| Main area | 按效果图使用白色卡片、表格、图表、流程和配置表单。优先支持扫描、确认、生成、发布、复测这些工作流。 |
| Right rail | 按效果图放下一步建议、Top 问题、结论摘要、风险提示。不要放纯装饰卡片。 |

## Route Breakdown

### `/console`

工作台是业务总览，不是静态大屏。必须展示：

- AIRank 来客指数
- 高意向问题覆盖率
- 竞品压制问题数
- 本月 AI 来客线索
- 机会总览和覆盖分布
- 推荐资产完成度
- 下一步建议

主要接口：

```text
GET /api/v1/projects/{project_id}/dashboard
GET /api/v1/projects/{project_id}/actions/next
```

### `/console/checkup`

AI 收录体检展示扫描过程和结果。素材里的四步流程可以落成 `ProgressStepper`：

```text
客户问题采样 -> 多 AI 平台检测 -> 引用来源分析 -> 竞品压制分析
```

主要接口：

```text
POST /api/v1/projects/{project_id}/scan-runs
GET  /api/v1/projects/{project_id}/scan-runs/{scan_run_id}
GET  /api/v1/projects/{project_id}/scan-runs/{scan_run_id}/provider-results
```

### `/console/facts`

企业事实库是后续内容资产和报告的可信来源。页面上叫“可信事实卡”，内部接口仍可返回 `fact_atom_id`。

必须支持：

- 按企业简介、核心服务、典型案例、资质与荣誉、联系方式、品牌方法论分组
- 已确认、待确认、需脱敏、不可公开状态
- 来源追溯和引用次数
- 人工确认入口

主要接口：

```text
GET   /api/v1/projects/{project_id}/fact-groups
GET   /api/v1/projects/{project_id}/fact-atoms
PATCH /api/v1/projects/{project_id}/fact-atoms/{fact_atom_id}
```

### `/console/questions`

买家问题地图承接“企业品牌方客户会问什么”。表格不是关键词列表，必须围绕高意向买家问题。

必须支持：

- 问题分组：品牌认知、选型决策、竞品对比、价格成交、本地行业
- 商业意图：高、中、低
- AI 推荐我、AI 推荐竞品、推荐缺口
- 建议资产

主要接口：

```text
GET /api/v1/projects/{project_id}/buyer-questions
GET /api/v1/projects/{project_id}/buyer-questions/segments
```

### `/console/gaps`

推荐缺口分析是 AIRank 来客的核心工作台之一。素材中有两个形态：

- 总览：证据覆盖雷达和缺口清单
- 问题明细：按问题查看我方和竞品推荐差距

页面应实现为同一路由下的 tab 或子路由，避免重复建设。

主要接口：

```text
GET /api/v1/projects/{project_id}/gaps/overview
GET /api/v1/projects/{project_id}/gaps/questions
GET /api/v1/projects/{project_id}/gaps/assets
```

### `/console/assets`

AI 收录包不是普通内容列表，而是面向 AI 可引用、可理解、可抓取的资产包。

第一版资产类型：

- 企业事实页
- 服务介绍页
- 客户案例页
- FAQ 页
- 竞品对比页
- 行业解决方案页
- JSON-LD
- sitemap.xml

主要接口：

```text
GET  /api/v1/projects/{project_id}/assets
POST /api/v1/projects/{project_id}/assets/generate
GET  /api/v1/projects/{project_id}/assets/package
```

### `/console/publishing`

发布提交中心对应发布、抓取、索引、复测队列，不应该只做“下载内容包”。

必须支持：

- 发布渠道
- 页面 URL
- 抓取状态
- 索引状态
- 最近提交时间
- 加入复测队列

主要接口：

```text
GET  /api/v1/projects/{project_id}/publishing/pages
POST /api/v1/projects/{project_id}/publishing/submit
POST /api/v1/projects/{project_id}/retest-runs
```

### `/console/reports`

报表中心用于管理体检报告、复测报告和高管报告。报告中的结论必须能回溯到 scan run、snapshot、citation 和 FactAtom。

主要接口：

```text
GET  /api/v1/projects/{project_id}/reports
POST /api/v1/projects/{project_id}/reports
GET  /api/v1/projects/{project_id}/reports/{report_id}
```

### `/console/settings`

设置中心第一版只做必要项：

- 品牌项目资料
- 官网和域名
- AI 平台接入状态
- 通知设置
- 成员权限只展示 yudao 绑定结果，M1 不自建完整 RBAC

主要接口：

```text
GET   /api/v1/projects/{project_id}/settings
PATCH /api/v1/projects/{project_id}/settings
GET   /api/v1/integrations/capabilities
```

### `/console/assistant`

AI 来客助手放到 P2。M1 可以保留导航占位或隐藏入口，不要为了页面完整度先做假聊天。

后续必须基于：

- 已确认可信事实卡
- 发布后的 AI 收录包
- 买家问题地图
- 线索规则和人工转接规则

## API Data Shape

前端页面不直接理解数据库表，应通过 view model 接口消费数据。建议每个页面接口统一返回：

```json
{
  "trace_id": "string",
  "project": {
    "id": "string",
    "name": "string",
    "website": "string",
    "industry": "string"
  },
  "summary": {},
  "items": [],
  "actions": [],
  "updated_at": "2026-05-17T00:00:00+08:00"
}
```

## Visual Fidelity Contract

必须严格参考效果图，不做新的视觉方向。前端实现可以把数值整理成 CSS variables，但变量值必须来自效果图。

### Color Tokens

以下色值来自效果图抽样，开发时作为初始 token；后续如果人工校准，只能为了更贴近效果图。源码落点为 `apps/web/src/console/theme/console-tokens.css`。

| Token | Value | Usage |
| --- | --- | --- |
| `--console-sidebar-bg` | `#000D30` | 侧栏最深背景 |
| `--console-sidebar-bg-soft` | `#0D1D42` | 侧栏渐变和底部区域 |
| `--console-primary` | `#443EFD` | 主按钮、核心高亮、图表主色 |
| `--console-primary-start` | `#3B36FB` | 侧栏 active 项渐变起点 |
| `--console-primary-end` | `#5B4DFF` | 侧栏 active 项渐变终点 |
| `--console-primary-tile` | `#7C72FC` | 指标卡 icon tile 主色 |
| `--console-page-bg` | `#F5F7FB` | 主工作区背景 |
| `--console-surface` | `#FFFFFF` | 卡片和表格背景 |
| `--console-border` | `#E6EAF4` | 卡片、表格、输入框边框 |
| `--console-text-strong` | `#071437` | 标题、指标数字 |
| `--console-text` | `#26365F` | 正文 |
| `--console-text-muted` | `#7B86A6` | 说明文字、次级元数据 |
| `--console-success` | `#01C8B1` | 正向状态、完成、提升 |
| `--console-warning` | `#FEA234` | 中风险、待确认 |
| `--console-danger` | `#FF5A3D` | 压制、缺口、风险提示 |
| `--console-purple-soft` | `#F1EFFF` | 紫色淡底标签 |
| `--console-orange-soft` | `#FFF4EB` | 橙色淡底风险条 |

禁用项：

- 不要使用 Ant Design 默认 `#1677ff` 作为主色。
- 不要使用 shadcn 默认 slate 灰替换文字和边框。
- 不要把控制台改成深色全屏大屏、玻璃拟态、营销渐变页或 bento 卡片风。

### Typography

按效果图采用系统中文字体栈：

```css
font-family: Inter, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
letter-spacing: 0;
```

建议层级：

| Token | Size / line-height / weight | Usage |
| --- | --- | --- |
| `--font-page-title` | `32px / 40px / 700` | 页面一级标题，如“工作台” |
| `--font-section-title` | `18px / 26px / 700` | 卡片标题 |
| `--font-body` | `14px / 22px / 500` | 正文、表格 |
| `--font-body-strong` | `15px / 24px / 600` | 表格主文本 |
| `--font-meta` | `12px / 18px / 500` | 标签、说明 |
| `--font-metric` | `42px / 48px / 700` | 指标大数字 |
| `--font-metric-small` | `28px / 34px / 700` | 次级指标数字 |

中文文案必须保持效果图的紧凑密度，不要改成大段解释文案。

### Spacing And Layout

| Token | Value | Usage |
| --- | --- | --- |
| `--sidebar-width` | `255px` | 左侧导航宽度 |
| `--page-padding-x` | `32px` | 主区左右内边距 |
| `--page-padding-y` | `28px` | 主区上下内边距 |
| `--section-gap` | `18px` | 页面大块间距 |
| `--card-gap` | `16px` | 卡片网格间距 |
| `--card-padding` | `20px` | 常规卡片内边距 |
| `--table-row-height` | `64px` | 表格行高参考 |
| `--nav-item-height` | `50px` | 侧栏导航项高度 |
| `--icon-tile-size` | `56px` | 首页指标卡 icon tile |
| `--icon-tile-size-sm` | `40px` | 小型卡片 icon tile |

布局验收以效果图为基准：顶部标题、指标卡、表格、右栏卡片之间的相对距离不能自行拉大。宽屏可以增加内容承载量，但不能改变视觉密度。

### Radius And Shadow

圆角和阴影也要按效果图，不使用框架默认值：

| Token | Value | Usage |
| --- | --- | --- |
| `--radius-nav` | `9px` | 侧栏 active item |
| `--radius-card` | `12px` | 大多数白色卡片 |
| `--radius-panel` | `14px` | 大型容器和流程面板 |
| `--radius-pill` | `999px` | 状态标签、胶囊按钮 |
| `--shadow-card` | `0 10px 30px rgba(15, 23, 42, 0.06)` | 常规卡片阴影 |
| `--shadow-soft` | `0 8px 22px rgba(68, 62, 253, 0.16)` | 主按钮和 active 项柔和阴影 |

### Icons

- 侧栏图标必须是线性白色图标，大小约 22px，线宽约 2px。
- active 导航项保持效果图里的图标 + 文字横排，不要换成纯图标侧栏。
- 指标卡和资产卡使用彩色圆角方块 icon tile，保留蓝紫、橙、青绿的渐变感。
- 可以用 `lucide-react` 作为实现来源，但必须通过本项目的 `ConsoleIcon` / `IconTile` 包装统一大小、线宽、颜色和背景。
- 不存在匹配图标时，补自定义 SVG；不要用 emoji、Material 默认 filled icon 或其它厚重图标风格。
- AI 平台 logo 可以先用圆形占位或官方授权图标，但大小、间距和卡片结构必须和效果图一致。

### Charts And Tables

- 折线、环形图、雷达图、进度条必须用数据驱动组件实现，不允许截图切片。
- 图表颜色顺序按效果图：蓝紫主色、橙色竞品/风险、青绿正向、浅灰基线。
- 表格 header、行高、分隔线、标签颜色按效果图，不使用浏览器默认 table。
- 所有图表必须有空状态、加载态和失败态，但这些状态也要保持同一视觉体系。

### Responsive Boundaries

1491x1055 是设计稿尺寸。实现时先保证以下视口接近效果图：

- `1440x1024`：主要还原目标。
- `1280x900`：允许右栏下移或缩窄，但视觉 token 不变。
- `1920x1080`：内容区域可拉宽，卡片和表格密度不变。

移动端可以后置。若必须做移动端，采用同一色彩和字体体系，不另起移动端风格。

### Visual QA

每个控制台页面完成后必须用浏览器截图和源 PNG 对照检查：

- 侧栏宽度、active item 颜色和 icon 风格。
- 页面标题字号、字重和上下间距。
- 卡片圆角、边框、阴影和内边距。
- 指标数字大小、颜色和对齐。
- 表格行高、状态 badge 和操作按钮。
- 图表主色、辅助色和标签密度。
- 不得出现默认组件库风格残留。

## Development Order

1. 先实现 `ConsoleShell`、导航和项目上下文。
2. 实现 `/console/checkup`、`/console/questions`、`/console/facts` 三个主链路页面。
3. 实现 `/console/gaps` 和 `/console/assets`，承接事实和缺口。
4. 实现 `/console/reports` 和 `/console/publishing`。
5. 最后补 `/console/settings` 的真实接入状态和 `/console/assistant`。

M1 验收重点不是像素级复刻，而是用户能从建项目、扫描、确认事实、看缺口、生成资产到查看报告形成闭环。

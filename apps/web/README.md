# apps/web

AIRank 前端应用。

## 本地启动

```bash
cd /Users/bruce/Developer/work/AIRank/apps/web
npm install
npm run dev -- --port 5173
```

访问：

```text
http://localhost:5173/console
```

第一版保留一个 Web 应用，内部拆两类路由：

- `marketing`：官网、免费测一测、案例、报价、留资。
- `console`：工作台、AI 收录体检、企业事实库、买家问题地图、推荐门槛、AI 收录包、发布提交、销售助手、线索看板、报表中心。

不要过早拆成两个前端工程，先保证获客入口和交付控制台共用组件、主题和 API client。

## 控制台素材落地规则

`AIRank素材/操作台` 的 PNG 是控制台体验参考，不是运行时图片资产。工程实现时按 `apps/web/design/console-reference.md` 拆成路由、布局组件、图表组件和 API view model。

视觉还原要求：色彩、icon 风格、字体层级、字重、行高、间距、圆角、阴影和视觉密度必须完全参考效果图，不允许换成其它 UI kit 默认风格。

已落地的工程入口：

- `apps/web/design/console-reference.md`：控制台页面、接口、组件和视觉还原规范。
- `apps/web/src/console/theme/console-tokens.css`：从效果图抽取的控制台视觉 token。
- `apps/web/src/console/routes/console-routes.ts`：控制台路由、图标名、优先级和素材映射。

第一版控制台路由建议：

| Route | Page |
| --- | --- |
| `/console` | 工作台 |
| `/console/checkup` | AI 收录体检 |
| `/console/facts` | 企业事实库 |
| `/console/questions` | 买家问题地图 |
| `/console/gaps` | 推荐缺口分析 |
| `/console/assets` | AI 收录包 |
| `/console/publishing` | 发布与复测 |
| `/console/reports` | 报表中心 |
| `/console/settings` | 设置中心 |
| `/console/assistant` | AI 来客助手，P2 |

实现优先级：

1. `ConsoleShell`、左侧导航、项目上下文和页面标题。
2. AI 收录体检、买家问题地图、企业事实库。
3. 推荐缺口分析、AI 收录包。
4. 报表中心、发布与复测、设置中心。
5. AI 来客助手。

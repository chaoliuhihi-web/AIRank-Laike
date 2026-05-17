# 术语映射表

客户侧产品术语与工程内部术语的统一对照，避免前后端、文档和代码中的术语混乱。

核心规则：

- 面向客户、销售、官网、控制台文案时，优先使用 PRD 和素材里的中文产品术语。
- 代码、schema、数据库、事件和内部任务使用工程术语。
- `FactAtom` 是工程内部最小事实单元；客户侧仍叫“可信事实卡”。不要在客户 UI 里直接使用“可信事实元”。

## 核心术语

| 客户侧产品术语 | 工程内部术语 | 领域模型类名 | API 路径 | 说明 |
| --- | --- | --- | --- | --- |
| 可信事实卡 | FactAtom | `FactAtom` | `/facts/atoms` | 客户侧展示为事实卡；工程内部是最小可复用事实单元 |
| 企业事实库 | FactStore | `FactStore` | `/facts` | 事实的存储和检索层 |
| 内容/信源缺口 | EvidenceGap | `EvidenceGap` | `/gaps/evidence` | 页面可按场景叫“推荐证据缺口”；内部承接内容缺口工厂 |
| 竞品压制分析 | Suppression | `CompetitorSuppression` | `/gaps/suppression` | 竞品在哪些高意向问题里排在前面 |
| AI 收录包 / AI 推荐资产包 | AssetBundle | `AssetBundle` | `/assets/bundles` | 对外可叫"AI 收录包"，更专业叫"AI 推荐资产包" |
| AI 来客体检 | Checkup | `Checkup` | `/checkups` | 比"AI 收录体检"更偏增长 |
| AI 来客指数 | AIRankScore | `AIRankScore` | `/scores` | 综合评分 |
| AI 来客助手 | Assistant | `Assistant` | `/assistant` | P2，不叫"AI 销售助手" |
| 来客线索 | Lead | `Lead` | `/leads` | 来客线索看板 |
| 买家问题地图 | BuyerQuestion | `BuyerQuestion` | `/questions` | 高购买意图问题集合 |
| 发布与复测 | Publishing | `PublishRecord` | `/publishing` | 发布状态机 + 复测入口 |
| 高管报告 | ExecutiveReport | `ExecutiveReport` | `/reports/executive` | 面向老板的一页纸报告 |
| 复测报告 | RetestReport | `RetestReport` | `/reports/retest` | 同批问题复测变化 |
| 品牌项目 | BrandProject | `BrandProject` | `/projects` | 企业品牌项目 |
| 竞品 | Competitor | `Competitor` | `/competitors` | 竞品管理 |

## 数据对象字段术语

### 可信事实卡 / FactAtom

| 客户侧字段 | 工程字段名 | 类型 |
| --- | --- | --- |
| 事实标题 | `title` | string |
| 事实类型 | `factType` | enum |
| 事实内容 | `content` | string |
| 原始来源 | `sourceType` | enum |
| 来源文件 | `sourceFile` | string |
| 来源片段 | `sourceExcerpt` | string |
| 可公开程度 | `disclosure` | enum: `public` / `redacted` / `internal` / `forbidden` / `pending_approval` |
| 可信等级 | `trustLevel` | enum: `A` / `B` / `C` / `D` |
| 适用问题 | `applicableQuestions` | string[] |
| 适用内容类型 | `applicableAssetTypes` | string[] |
| 风险提示 | `riskNote` | string |
| 人工确认人 | `confirmedBy` | string |
| 确认时间 | `confirmedAt` | datetime |

### 可信等级

| PRD 等级 | 工程枚举值 | 说明 |
| --- | --- | --- |
| A | `OFFICIAL` | 官方资料 / 客户授权 / 可公开案例 |
| B | `CONFIRMED` | 内部资料 / 销售材料 / 已确认事实 |
| C | `PENDING` | 待确认资料 / 历史材料 / 需复核 |
| D | `RESTRICTED` | 不可用于生成公开内容 |

### MVP 发布状态

| PRD 状态 | 工程枚举值 |
| --- | --- |
| 未发布 | `DRAFT` |
| 已生成发布包 | `PACKAGED` |
| 已发布 / 已记录发布 URL | `PUBLISHED` |
| 抓取中 | `CRAWLING` |
| 已抓取 | `CRAWLED` |
| 已索引 | `INDEXED` |
| 待复测 | `PENDING_RETEST` |
| 已复测 | `RETESTED` |

`PUSHED` 只用于 V1/V2 授权或半自动发布，不进入 30 天 MVP 的必需状态机。

## 使用规则

1. **API 路径和前端页面**必须使用客户侧产品术语的英文映射（如 `/facts/atoms`）。
2. **代码内部**使用工程内部术语和类名。
3. **面向客户的 UI 文案**使用 PRD 中文原文。
4. **内部文档和 Agent 任务**可以使用工程术语，但必须在本表可追溯。

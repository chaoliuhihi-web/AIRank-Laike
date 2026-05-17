# AIRank 低人工操作与 Hermes 自动化功能规格

状态：MVP 功能细化稿

日期：2026-05-17

目标：参考当前 `apps/web` 官网和控制台页面，把 AIRank 来客做成“用户尽量少操作，Hermes/智能体尽量自动完成联网检索、抓取、归因、生成、复测”的产品闭环规格。

## 1. 核心原则

AIRank 来客第一版不应该让用户像后台运营人员一样逐项录入资料。用户最小操作应是：

1. 输入官网或品牌名。
2. 确认企业、行业、竞品、目标客户这些基础信息。
3. 等待 Hermes 自动完成检索、扫描、归因和诊断。
4. 只审核高风险事实和公开发布内容。
5. 导出发布包或记录发布 URL。
6. 查看复测和高管报告。

产品体验目标：

| 原则 | 产品要求 | 工程含义 |
| --- | --- | --- |
| 少填表 | 官网输入后自动补齐企业资料、竞品、问题地图和事实候选 | 后端需要 `seed_from_website` 类任务 |
| 少找资料 | 公开资料、官网、新闻、案例、招聘、备案、百科、第三方平台尽量由 Hermes 检索 | 资料来源必须结构化存证 |
| 少判断 | 系统自动标出可信等级、可公开程度、风险点和推荐动作 | 不能只给用户一堆原始抓取结果 |
| 人只审核关键处 | 涉及公开发布、敏感事实、竞品风险、客户案例真实性时才要求人工确认 | 需要明确审核门槛和状态 |
| 所有结论可追溯 | 分数、缺口、内容、报告必须回到回答快照、引用 URL、事实卡或发布 URL | 证据链是 MVP 必需品 |
| 外部能力可降级 | Hermes / Xinghe / 搜索不可用时，主链仍允许人工导入和结构化记录 | 能力状态必须进入 `ready / partial / blocked / disabled / dev_only` |

## 2. 自动化分级

所有功能都按自动化等级标注，避免把用户拖进不必要的操作。

| 等级 | 名称 | 用户参与 | 适用场景 |
| --- | --- | --- | --- |
| A0 | 全自动 | 用户不需要介入，只看结果 | 官网公开信息抓取、竞品候选、初版问题地图、来源归因、趋势计算 |
| A1 | 自动加确认 | Hermes 生成结果，用户点确认/驳回/稍后 | 企业资料、竞品清单、可信事实卡、内容缺口优先级 |
| A2 | 自动加轻编辑 | Hermes 生成草稿，用户只改少数字段 | FAQ、选型指南、案例页、报告摘要 |
| A3 | 人工兜底 | 外部能力失败或涉及账号授权时用户补充 | 需要登录的资料、私有案例、发布账号、平台无法访问 |

MVP 默认策略：

- 能 A0 就不要做成表单。
- 能 A1 就不要让用户从空白开始填写。
- 能 A2 就不要让用户写完整内容。
- A3 必须是兜底，不是默认路径。

## 3. 前端页面到自动化职责映射

当前前端包含官网页面和控制台页面。下面按路径定义用户动作、Hermes 动作和验收输出。

| 路径 | 页面 | 用户最小动作 | Hermes/智能体自动动作 | 输出对象 | 自动化等级 |
| --- | --- | --- | --- | --- | --- |
| `/` | 官网首页 | 输入官网，点击免费测一测 | 识别官网、创建预检任务、抓取首页和关键页面 | `ProjectSeed`、`CheckupLead` | A0/A1 |
| `/free-check` | 免费体检 | 输入官网、手机号或微信，确认授权检测 | 自动检索品牌、竞品、问题、公开信源，生成体检预览 | `CheckupDraft` | A0/A1 |
| `/product` | 产品能力 | 浏览和转化 | 无需业务任务，只承接 CTA | `MarketingVisit` | A0 |
| `/solutions` | 解决方案 | 浏览和转化 | 按行业 CTA 带入行业上下文 | `MarketingVisit` | A0 |
| `/cases` | 客户案例 | 浏览和转化 | 按案例行业推荐体检模板 | `MarketingVisit` | A0 |
| `/pricing` | 定价 | 选择套餐或咨询 | 把套餐意向带入线索 | `Lead` | A0 |
| `/resources` | 资源中心 | 浏览资料 | 记录内容偏好 | `LeadSignal` | A0 |
| `/console` | 工作台 | 看结论，点下一步建议 | 汇总分数、缺口、待审核、发布和复测动作 | `DashboardOverview` | A0 |
| `/console/checkup` | AI 来客体检 | 发起或查看体检 | 生成问题集、多平台采样、保存快照和引用 | `ScanRun` | A0/A1 |
| `/console/facts` | 企业事实库 | 确认/驳回风险事实 | 从官网和资料中抽取可信事实卡并打可信等级 | `FactAtom` | A1 |
| `/console/questions` | 买家问题地图 | 确认问题方向，可删除明显不相关项 | 自动生成和分组高意向买家问题 | `BuyerQuestion` | A1 |
| `/console/gaps` | 推荐缺口分析 | 选择要优先修复的缺口 | 自动比较本品牌/竞品证据、推荐资产优先级 | `EvidenceGap` | A0/A1 |
| `/console/gaps/questions` | 问题维度缺口 | 查看和筛选问题 | 自动解释每个问题为什么竞品更容易被推荐 | `QuestionGap` | A0 |
| `/console/assets` | AI 收录包 | 审核草稿，选择导出 | 自动生成 FAQ、选型指南、案例页、JSON-LD、sitemap | `AssetBundle` | A2 |
| `/console/publishing` | 发布与复测 | 记录发布 URL 或上传发布结果 | 自动检测抓取、索引、加入复测队列 | `PublishRecord`、`RetestRun` | A1/A3 |
| `/console/reports` | 报表中心 | 查看或下载报告 | 自动生成体检报告、复测报告、高管报告 | `ExecutiveReport`、`RetestReport` | A0/A1 |
| `/console/settings` | 设置中心 | 确认项目资料、集成状态、通知 | 自动检测平台能力、模型配置、域名状态 | `ProjectSettings`、`CapabilityStatus` | A1 |
| `/console/assistant` | AI 来客助手 | 配置线索规则，预览话术 | 基于事实卡和资产包生成答复策略 | `AssistantConfig` | P2/A2 |

## 4. 推荐的用户主链路

### 4.1 免费体检到控制台

目标：用户从官网进入，不需要手动建完整项目。

1. 用户在 `/` 或 `/free-check` 输入官网。
2. API 创建 `CheckupLead` 和 `ProjectSeedJob`。
3. Hermes 自动执行：
   - 访问官网首页、关于我们、产品、案例、价格、新闻、FAQ、联系页。
   - 搜索品牌名、公司名、域名、核心产品词。
   - 提取公司名、行业、产品服务、客户类型、核心案例、资质、联系方式。
   - 发现 3-10 个竞品候选。
   - 生成 50 个高意向买家问题候选。
   - 形成一份 `CheckupDraft`。
4. 用户看到预检结果，只需确认：
   - 这是不是你的品牌。
   - 竞品是否大体正确。
   - 目标客户是否大体正确。
5. 用户点击“开始体检”。
6. 系统进入 `/console/checkup`，后台创建 `ScanRun`。

用户不应该在第一步填写产品、服务、行业、客户、竞品的完整表单。表单只用于确认和修正。

### 4.2 体检到可信事实卡

目标：扫描和资料归因尽量自动做，用户只审核风险事实。

1. Hermes 基于问题地图对 AI 平台做扫描或半自动采样。
2. 每个回答保存：
   - provider
   - model 或平台名
   - question
   - answer_text
   - citations
   - mentioned_brands
   - recommended_brands
   - rank_position
   - captured_at
3. Hermes 自动归因引用来源：
   - 客户官网
   - 竞品官网
   - 第三方媒体
   - 百科/地图/工商/招聘等公开平台
   - 问答社区
   - 未知来源
4. Hermes 从官网和引用中抽取候选可信事实卡。
5. 用户只处理这些状态：
   - `pending_approval`：待确认，可一键确认。
   - `redacted`：需要脱敏后公开。
   - `forbidden`：禁止公开使用。
   - `conflict`：多个来源冲突，需要人工判断。

默认不要求用户逐条录入事实。

### 4.3 缺口到 AI 收录包

目标：用户不写内容，从缺口自动生成资产。

1. 系统根据扫描结果识别：
   - 哪些问题 AI 推荐竞品不推荐本品牌。
   - 哪些问题缺少客户官网证据。
   - 哪些内容类型缺失。
   - 哪些引用来源质量低。
2. Hermes 自动把缺口转成内容任务：
   - FAQ
   - 选型指南
   - 客户案例页
   - 竞品对比页
   - 行业解决方案页
   - JSON-LD
   - sitemap
3. 用户进入 `/console/assets`，只看到资产卡和草稿。
4. 用户只需：
   - 审核高风险事实。
   - 修改明显不符合品牌口吻的段落。
   - 点击打包或导出。

内容资产必须标明使用了哪些 `FactAtom` 和来源，不允许只有生成结果。

### 4.4 发布到复测报告

目标：发布后系统自动观察和复测，用户只补 URL 或授权。

1. 如果用户没有 CMS 授权，MVP 只导出发布包。
2. 用户发布后在 `/console/publishing` 粘贴 URL 或上传发布回执。
3. Hermes 自动：
   - 抓取发布 URL。
   - 检查页面是否可访问。
   - 检查 title、meta、结构化数据、正文关键事实。
   - 记录抓取时间和快照。
   - 加入复测队列。
4. 到复测时间后，系统用同一问题集复测。
5. `/console/reports` 自动生成：
   - AI 来客体检报告
   - 推荐缺口复测报告
   - 高管报告

## 5. Hermes 任务定义

Hermes 任务不是直接修改业务真相源的黑盒。它必须写结构化结果，并让 API 根据状态机落库。

### 5.1 `project.seed_from_website`

目的：用官网自动生成项目初始资料。

输入：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `tenant_id` | 是 | 当前租户 |
| `website_url` | 是 | 用户输入官网 |
| `brand_name_hint` | 否 | 用户输入品牌名 |
| `industry_hint` | 否 | 用户选择或渠道带入行业 |
| `trace_id` | 是 | 贯穿任务链路 |

自动步骤：

1. 规范化域名和 URL。
2. 抓取官网公开页面。
3. 搜索品牌名、域名、备案主体、公开介绍。
4. 抽取公司名、行业、产品、服务、目标客户、案例、资质、联系方式。
5. 识别资料来源和可信等级。

输出：

| 字段 | 说明 |
| --- | --- |
| `project_candidate` | 项目候选资料 |
| `fact_candidates` | 候选可信事实卡 |
| `source_refs` | 来源 URL、抓取摘要、hash |
| `confidence` | 置信度 |
| `risk_flags` | 冲突、过期、敏感、来源弱 |

用户介入：

- 置信度高且来源为官网时，可默认填入。
- 公司名、官网、行业、联系方式需要用户确认。
- 涉及客户案例、收入、排名、认证时必须 A1 确认。

### 5.2 `competitor.discover`

目的：自动发现 3-10 个竞品候选。

输入：

- 项目资料
- 官网文本
- 行业关键词
- 产品服务关键词
- 用户给出的竞品 hint

自动来源：

- 搜索引擎结果
- 行业榜单
- 第三方评测
- 竞品对比文章
- AI 平台回答中的品牌共现

输出字段：

| 字段 | 说明 |
| --- | --- |
| `name` | 竞品名称 |
| `website` | 官网 |
| `reason` | 为什么被识别为竞品 |
| `evidence_urls` | 来源 |
| `confidence` | 置信度 |
| `status` | `suggested / confirmed / rejected` |

用户介入：

- 默认展示建议清单，用户一键确认/删除/补充。
- 不要求用户从空白录入竞品。

### 5.3 `question.generate_map`

目的：自动生成高购买意图买家问题地图。

输入：

- 项目资料
- 竞品
- 行业
- 产品服务
- 目标客户
- 已抓取官网和第三方资料

问题类型：

| 类型 | 说明 | 示例 |
| --- | --- | --- |
| `purchase` | 购买决策 | 企业如何选择营销自动化平台 |
| `compare` | 竞品对比 | A 和 B 哪个更适合制造业 |
| `select` | 选型标准 | 选型时应该看哪些功能 |
| `trust` | 信任背书 | 有没有真实客户案例 |
| `price` | 价格成交 | 价格一般是多少 |
| `risk` | 风险顾虑 | 数据安全怎么保障 |
| `scenario` | 场景方案 | 制造业获客怎么做 |
| `local` | 本地行业 | 上海本地服务商怎么选 |
| `alternative` | 替代方案 | 有没有某竞品替代品 |

输出字段：

| 字段 | 说明 |
| --- | --- |
| `question_text` | 问题 |
| `question_type` | 问题类型 |
| `intent_level` | `high / medium / low` |
| `buyer_stage` | `awareness / consideration / decision` |
| `source_reason` | 生成依据 |
| `recommended_providers` | 建议扫描平台 |
| `status` | `suggested / confirmed / archived` |

用户介入：

- 默认生成 50 个候选。
- 用户只需删除明显不相关问题，或确认问题集。

### 5.4 `scan.sample_ai_answers`

目的：自动或半自动获得 AI 平台对问题的回答。

MVP 平台建议：

| provider | MVP 策略 | 自动化 |
| --- | --- | --- |
| ChatGPT | 若有可用 API 路由则自动，否则半自动导入 | A0/A3 |
| DeepSeek | 优先 API | A0 |
| Kimi | API 或半自动 | A0/A3 |
| 通义 | API 或半自动 | A0/A3 |
| 豆包 | API 或半自动 | A0/A3 |
| 百度 AI 搜索 | 半自动或搜索采样 | A1/A3 |
| 腾讯元宝 | 半自动 | A3 |

输出字段：

- `scan_run_id`
- `scan_task_id`
- `provider`
- `question_id`
- `answer_text`
- `answer_hash`
- `mentioned_brands`
- `recommended_brands`
- `brand_rank`
- `citation_urls`
- `raw_snapshot_object_ref`
- `status`
- `error_code`

用户介入：

- API 可用时不介入。
- 平台不支持自动接口时，前端提供“粘贴回答”半自动入口。
- 半自动导入也必须结构化记录，不能只写备注。

### 5.5 `citation.attribute_sources`

目的：把回答中的 URL 和来源归因成客户、竞品或第三方。

自动步骤：

1. 规范化 URL 和 host。
2. 匹配项目官网和竞品官网。
3. 抓取页面 title、摘要和发布时间。
4. 判断来源类型和可信等级。
5. 生成 source index。

输出：

| 字段 | 说明 |
| --- | --- |
| `source_type` | `owned / competitor / third_party / community / unknown` |
| `host` | 域名 |
| `title` | 页面标题 |
| `excerpt` | 命中片段 |
| `trust_level` | 来源可信等级 |
| `used_by_question_ids` | 被哪些问题引用 |

用户介入：

- 不需要用户手动分类来源。
- `unknown` 和高影响来源可进入人工复核。

### 5.6 `fact.extract_candidates`

目的：从官网、资料、扫描引用中抽取可信事实卡候选。

事实类型：

- `brand_identity`
- `product_service`
- `customer_case`
- `industry_solution`
- `qualification`
- `pricing`
- `faq`
- `competitor_diff`
- `channel`

自动判断：

| 判断项 | 自动规则 |
| --- | --- |
| 可信等级 | 官网/授权资料优先，第三方次之，未知来源最低 |
| 可公开程度 | 官网已公开默认 `public`，客户案例和数字默认 `pending_approval` |
| 风险 | 涉及客户名、营收、效果数字、竞品比较、绝对化表述时打标 |
| 适用内容 | 映射到 FAQ、选型指南、案例页、对比页、JSON-LD |

用户介入：

- 高可信公开事实可批量确认。
- 客户案例、效果数字、竞品差异必须确认。
- `forbidden` 事实不能进入内容生成。

### 5.7 `gap.detect`

目的：自动识别推荐缺口和竞品压制原因。

缺口类型：

| 类型 | 说明 |
| --- | --- |
| `evidence_gap` | AI 找不到足够可信证据 |
| `suppression` | 竞品在高意向问题上更常被推荐 |
| `content_gap` | 缺少 FAQ、案例、指南、对比页等内容 |
| `source_gap` | 缺少第三方信源或权威引用 |
| `technical_gap` | 页面结构、抓取、schema、sitemap 有问题 |

输出：

- 缺口名称
- 影响问题数
- 影响 provider
- 证据来源
- 推荐动作
- 建议资产类型
- 优先级

用户介入：

- 用户只选择先处理哪些缺口。
- 系统默认按影响问题数、商业意图、修复难度排序。

### 5.8 `asset.generate_pack`

目的：基于确认事实卡和缺口生成 AI 收录包。

资产类型：

| 资产 | 生成条件 | 人工要求 |
| --- | --- | --- |
| FAQ 页 | 有高频问题和可公开事实 | A2 轻编辑 |
| 选型指南 | 有比较类/选型类问题和产品事实 | A2 轻编辑 |
| 客户案例页 | 有已确认客户案例事实 | 必须确认 |
| 竞品对比页 | 有竞品差异事实和合法表述 | 必须确认 |
| 行业解决方案页 | 有行业场景和案例事实 | A2 轻编辑 |
| JSON-LD | 有结构化项目和事实字段 | A0 |
| sitemap.xml | 有发布页面列表 | A0 |

输出必须包含：

- 资产正文
- 使用的 `fact_atom_ids`
- 使用的 `source_refs`
- 风险提示
- 审核状态
- 导出格式

### 5.9 `publish.observe`

目的：发布后自动观察抓取和索引状态。

输入：

- 发布 URL
- 发布渠道
- 对应资产包

自动步骤：

1. 抓取发布 URL。
2. 检查 HTTP 状态、canonical、meta、schema、正文。
3. 检查是否包含关键事实。
4. 生成发布快照。
5. 将页面加入复测候选。

用户介入：

- MVP 不要求系统自动登录 CMS。
- 用户只粘贴发布 URL 或上传发布结果。

### 5.10 `retest.run`

目的：用同一问题集复测发布前后变化。

输入：

- 原始 `scan_run_id`
- 发布记录
- 同一批问题
- 同一组 provider 策略

输出：

- 发布前后提及率变化
- 推荐率变化
- 首推率变化
- 竞品压制变化
- 引用客户官网比例变化
- 仍未解决的问题

用户介入：

- 默认无需介入。
- provider 不可用时进入半自动导入队列。

### 5.11 `report.generate`

目的：自动生成体检报告、复测报告和高管报告。

报告要求：

| 报告 | 内容 | 证据要求 |
| --- | --- | --- |
| 体检报告 | 当前 AI 可见性、竞品压制、引用来源、机会 | 每个结论关联 scan run 和 snapshot |
| 复测报告 | 发布前后指标变化、修复效果、遗留缺口 | 每个变化关联前后 scan run |
| 高管报告 | 一页纸机会、风险、动作、结果 | 关键结论关联证据索引 |

用户介入：

- 默认自动生成。
- 对外发送前允许编辑摘要和隐藏敏感数据。

## 6. 页面级详细规格

### 6.1 官网首页 `/`

页面目的：降低获客门槛，让用户从一个官网 URL 进入体检。

必须控件：

- 官网输入框。
- 免费测一测按钮。
- 登录入口跳转 `/console`。
- 产品能力、解决方案、案例、定价、资源、免费体检导航。

用户只输入：

- `website_url`
- 可选联系方式，若首页不收集则跳到 `/free-check` 收集。

后台自动：

- 创建匿名或线索态 `CheckupLead`。
- 触发轻量 `project.seed_from_website` 预检。
- 记录渠道和落地页。

验收：

- 用户输入官网后不应进入长表单。
- 系统应在免费体检页展示“正在识别品牌和公开资料”的任务状态。

### 6.2 免费体检 `/free-check`

页面目的：完成授权和最小线索收集。

必须字段：

| 字段 | 必填 | 自动补齐 |
| --- | --- | --- |
| 官网 URL | 是 | 用户输入 |
| 联系方式 | 是 | 用户输入 |
| 公司名 | 否 | Hermes 从官网和公开资料识别 |
| 行业 | 否 | Hermes 识别，用户确认 |
| 竞品 | 否 | Hermes 生成候选 |
| 目标客户 | 否 | Hermes 识别，用户确认 |

用户动作：

1. 输入官网和联系方式。
2. 勾选允许检测公开信息。
3. 点击开始体检。

Hermes 动作：

- 抓取官网。
- 搜索公开品牌信息。
- 识别竞品。
- 生成问题地图。
- 生成预检摘要。

验收：

- 用户不需要填写 3-10 个竞品。
- 用户不需要手写 50 个问题。
- 若自动识别失败，才提示用户补充行业和竞品。

### 6.3 工作台 `/console`

页面目的：展示业务结论和下一步动作，不做静态大屏。

展示模块：

- AI 来客指数。
- 高意向问题覆盖率。
- 竞品压制问题数。
- 本月 AI 来客线索。
- 机会总览。
- 推荐资产完成度。
- 下一步建议。

用户动作：

- 点击下一步建议。
- 查看指标来源。
- 跳转到待处理页面。

Hermes 动作：

- 自动聚合最近 scan run、fact、gap、asset、publish、retest 数据。
- 生成下一步建议。
- 标记动作优先级。

验收：

- 工作台不能只展示数字，必须能点击到具体缺口、事实或资产。
- 下一步建议必须由数据驱动，不是硬编码文案。

### 6.4 AI 来客体检 `/console/checkup`

页面目的：让用户看到扫描进度、平台结果和竞品压制原因。

用户动作：

- 点击开始体检或查看结果。
- 对半自动平台上传/粘贴回答。
- 重新扫描。

Hermes 动作：

- 生成或读取问题集。
- 对 provider 创建 scan task。
- 采样回答并保存快照。
- 提取提及品牌、推荐品牌、引用 URL。
- 生成 provider 结果和总体结论。

状态：

- `not_started`
- `queued`
- `running`
- `partial`
- `completed`
- `failed`
- `needs_manual_import`

验收：

- 每个平台必须有状态和错误原因。
- 没有自动接口的平台不能阻塞整个 scan run。
- 每个结论可追溯到回答快照。

### 6.5 企业事实库 `/console/facts`

页面目的：把公开资料变成可确认、可引用、可审计的可信事实卡。

用户动作：

- 批量确认低风险事实。
- 驳回错误事实。
- 标记脱敏或禁止公开。
- 查看来源。

Hermes 动作：

- 从官网、案例、新闻、PPT、扫描引用抽取事实。
- 自动分组。
- 自动标可信等级和公开程度。
- 标记冲突和风险。

事实分组：

- 企业简介
- 核心服务
- 典型案例
- 资质与荣誉
- 联系方式
- 品牌方法论
- 产品功能
- 行业方案
- 价格与服务边界

验收：

- confirmed 事实必须至少有一个来源。
- 客户侧页面只叫“可信事实卡”，不要暴露 `FactAtom`。
- 禁止公开的事实不能被内容资产引用。

### 6.6 买家问题地图 `/console/questions`

页面目的：让用户确认 AI 体检围绕真实购买问题，而不是关键词。

用户动作：

- 查看问题分组。
- 删除不相关问题。
- 确认问题集。
- 手动补充少量关键问题。

Hermes 动作：

- 根据行业、竞品、官网内容、公开搜索结果生成问题。
- 自动判断意图和阶段。
- 自动映射建议扫描平台。
- 自动识别问题是否已有内容覆盖。

验收：

- 默认生成 50 个问题。
- 用户最多做删改确认，不从空白创建。
- 每个问题必须有意图等级和问题类型。

### 6.7 推荐缺口 `/console/gaps`

页面目的：把扫描差距转成可执行动作。

用户动作：

- 选择优先修复的缺口。
- 跳转生成 AI 收录包。

Hermes 动作：

- 对比本品牌和竞品推荐率。
- 分析缺少哪些证据。
- 找出内容资产缺口。
- 生成动作建议。

验收：

- 缺口必须关联影响问题数。
- 缺口必须说明“为什么 AI 更可能推荐竞品”。
- 缺口必须能转成至少一种资产建议。

### 6.8 问题维度缺口 `/console/gaps/questions`

页面目的：逐题解释推荐差距。

展示字段：

- 问题。
- 商业意图。
- 我方推荐率。
- 竞品推荐率。
- 差距。
- 建议资产。
- 引用来源。

Hermes 动作：

- 自动解释差距原因。
- 自动关联可修复资产。

用户动作：

- 筛选高意图问题。
- 选择生成资产。

### 6.9 AI 收录包 `/console/assets`

页面目的：把事实和缺口变成可发布内容。

用户动作：

- 查看资产完整度。
- 审核草稿。
- 点击生成、打包、导出。

Hermes 动作：

- 自动生成内容草稿。
- 自动生成结构化数据。
- 自动生成发布包。
- 自动标记缺证据段落。

验收：

- 每个资产必须显示完整度和审核状态。
- 每个内容段落能追溯到事实卡或来源。
- 没有 confirmed 事实时不能生成客户案例页。

### 6.10 发布与复测 `/console/publishing`

页面目的：发布后进入抓取、索引、复测闭环。

用户动作：

- 下载发布包。
- 粘贴发布 URL。
- 标记发布渠道。
- 发起复测。

Hermes 动作：

- 自动检查 URL 可访问性。
- 自动抓取发布页。
- 自动验证结构化数据。
- 自动加入复测队列。

验收：

- MVP 不做无审核全自动发布。
- 发布 URL 和发布快照必须保存。
- 复测必须关联原始 scan run 和发布记录。

### 6.11 报表中心 `/console/reports`

页面目的：给老板和交付团队看结果，不是堆数据。

用户动作：

- 查看报告。
- 下载或分享。
- 隐藏敏感内容。

Hermes 动作：

- 自动生成报告。
- 自动生成结论摘要。
- 自动绑定证据链。
- 自动生成下一步建议。

验收：

- 报告结论必须能回溯证据。
- 高管报告必须是一页纸优先。
- 复测报告必须有发布前后对比。

### 6.12 设置中心 `/console/settings`

页面目的：只保留必要设置，不做复杂后台。

用户动作：

- 确认品牌资料。
- 查看平台能力状态。
- 配置通知。
- 查看成员绑定。

Hermes/adapter 动作：

- 自动检测 yudao auth。
- 自动检测 model resolve。
- 自动检测 Crawler、KB、Hermes、workflow 能力。
- 自动记录能力状态。

验收：

- 外部能力必须展示 `ready / partial / blocked / disabled / dev_only`。
- M1 不自建完整 RBAC，成员权限只展示 yudao 绑定结果。

### 6.13 AI 来客助手 `/console/assistant`

页面目的：P2 能力，后置。不能为了页面完整做假聊天。

前置条件：

- 已确认可信事实卡。
- 已生成 AI 收录包。
- 已有买家问题地图。
- 已配置线索规则。

用户动作：

- 配置线索规则。
- 预览话术。
- 标记是否转人工。

Hermes 动作：

- 基于事实卡生成回答。
- 基于问题地图识别意图。
- 基于线索规则判断是否留资。

MVP 策略：

- 可以保留入口和说明。
- 不阻塞 M1/M2 主链。

## 7. 人工确认边界

为了减少操作，必须明确哪些事不需要人做，哪些事必须人确认。

### 7.1 默认不需要人做

- 官网公开页面抓取。
- 品牌基础资料候选生成。
- 竞品候选发现。
- 买家问题候选生成。
- 来源归因初判。
- 低风险事实候选。
- 指标计算。
- 缺口排序。
- 报告初稿。
- 发布 URL 可访问性检查。
- 复测排队。

### 7.2 必须人确认

- 公司主体名称和官网归属。
- 客户案例是否可公开。
- 效果数字和 ROI。
- 资质证书、奖项、排名。
- 竞品对比中可能有法律风险的表述。
- 价格、承诺、服务 SLA。
- 对外发布的最终内容。
- 需要登录账号或授权的发布动作。

### 7.3 应该人可选编辑

- 品牌语气。
- FAQ 问答措辞。
- 选型指南标题。
- 案例页结构。
- 报告摘要。

## 8. 数据对象最小字段

### 8.1 `ProjectSeed`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `seed_id` | string | 预检 ID |
| `tenant_id` | string | 租户 |
| `website_url` | string | 官网 |
| `brand_name` | string | 品牌名候选 |
| `company_name` | string | 公司名候选 |
| `industry` | string | 行业候选 |
| `products` | array | 产品服务候选 |
| `audiences` | array | 目标客户候选 |
| `confidence` | number | 整体置信度 |
| `status` | string | `running / ready / needs_confirmation / failed` |
| `source_refs` | array | 来源 |

### 8.2 `CheckupDraft`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `draft_id` | string | 体检草稿 |
| `project_candidate` | object | 项目候选 |
| `competitor_candidates` | array | 竞品候选 |
| `question_candidates` | array | 问题候选 |
| `fact_candidates` | array | 事实候选 |
| `risk_flags` | array | 风险 |
| `next_action` | string | 下一步 |

### 8.3 `HermesJob`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `job_id` | string | 任务 ID |
| `tenant_id` | string | 租户 |
| `project_id` | string | 项目 |
| `job_type` | string | 任务类型 |
| `status` | string | `queued / running / completed / failed / needs_manual_input` |
| `input` | object | 输入摘要 |
| `output` | object | 输出摘要 |
| `source_refs` | array | 来源 |
| `error_code` | string | 错误码 |
| `error_message` | string | 脱敏错误 |
| `trace_id` | string | 链路 ID |

### 8.4 `UserReviewTask`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `review_task_id` | string | 审核任务 |
| `object_type` | string | `project / fact / asset / report / publish` |
| `object_id` | string | 对象 ID |
| `reason` | string | 为什么需要人工 |
| `risk_level` | string | `low / medium / high` |
| `suggested_action` | string | 建议动作 |
| `status` | string | `pending / approved / rejected / edited` |

## 9. API 和契约建议

后续 contracts 应优先补这些 view model，前端不要直接依赖数据库表：

| Contract | 页面 | 说明 |
| --- | --- | --- |
| `checkup_start.schema.json` | `/free-check` | 官网输入后创建体检 |
| `project_seed.schema.json` | `/free-check`、`/console/settings` | Hermes 自动建档结果 |
| `competitor_candidate.schema.json` | `/console/settings`、`/console/checkup` | 竞品候选 |
| `buyer_question_map.schema.json` | `/console/questions` | 问题地图 |
| `scan_run_detail.schema.json` | `/console/checkup` | 扫描详情 |
| `fact_review_queue.schema.json` | `/console/facts` | 待确认事实 |
| `gap_overview.schema.json` | `/console/gaps` | 推荐缺口总览 |
| `asset_bundle.schema.json` | `/console/assets` | AI 收录包 |
| `publishing_status.schema.json` | `/console/publishing` | 发布状态 |
| `report_list.schema.json` | `/console/reports` | 报告列表 |
| `hermes_job.schema.json` | 多页面 | 自动化任务状态 |

建议 API：

```text
POST /api/v1/checkups
GET  /api/v1/checkups/{checkup_id}
POST /api/v1/projects/{project_id}/hermes-jobs
GET  /api/v1/projects/{project_id}/hermes-jobs/{job_id}
GET  /api/v1/projects/{project_id}/review-tasks
PATCH /api/v1/projects/{project_id}/review-tasks/{review_task_id}
GET  /api/v1/projects/{project_id}/dashboard
GET  /api/v1/projects/{project_id}/questions
GET  /api/v1/projects/{project_id}/scan-runs/{scan_run_id}
GET  /api/v1/projects/{project_id}/facts/review-queue
GET  /api/v1/projects/{project_id}/gaps/overview
GET  /api/v1/projects/{project_id}/assets/bundle
GET  /api/v1/projects/{project_id}/publishing/status
GET  /api/v1/projects/{project_id}/reports
```

## 10. MVP 验收用例

### 用例 1：只输入官网完成体检草稿

前置：

- 用户访问 `/free-check`。

步骤：

1. 输入官网。
2. 输入联系方式。
3. 点击开始体检。

期望：

- 系统创建 `CheckupLead`。
- Hermes 创建 `project.seed_from_website` 任务。
- 生成公司名、行业、产品、竞品、问题候选。
- 用户看到待确认体检草稿。

失败兜底：

- 官网不可访问时提示用户补充公司名和行业。
- 仍保留结构化 `failed` 任务和错误码。

### 用例 2：用户确认竞品后自动生成问题地图

步骤：

1. 用户确认或删除竞品候选。
2. 点击生成问题地图。

期望：

- 系统生成至少 50 个问题候选。
- 每个问题有类型、意图等级、买家阶段。
- 用户只需删除明显错误项。

### 用例 3：扫描时部分平台不可用

步骤：

1. 发起 AI 来客体检。
2. 其中一个 provider 不可用。

期望：

- 其它 provider 正常完成。
- 不可用 provider 标记 `needs_manual_import` 或 `failed`。
- scan run 状态为 `partial`，不是整体失败。
- 工作台显示降级说明。

### 用例 4：事实卡自动抽取但敏感案例需要确认

步骤：

1. Hermes 从官网和案例页抽取事实。
2. 涉及客户名和效果数字。

期望：

- 事实卡状态为 `pending_approval`。
- 风险提示说明原因。
- 用户确认前不能用于公开内容。

### 用例 5：缺口自动生成 AI 收录包

步骤：

1. 扫描完成。
2. 用户进入推荐缺口页面。
3. 点击生成 AI 收录包。

期望：

- 系统自动生成 FAQ、选型指南和案例页草稿。
- 每段内容关联事实卡和来源。
- 高风险段落进入审核状态。

### 用例 6：发布后自动复测

步骤：

1. 用户导出发布包。
2. 用户粘贴发布 URL。
3. 系统抓取并加入复测。

期望：

- 发布记录状态进入 `crawled` 或 `failed`。
- 复测任务使用同一问题集。
- 报表中心生成发布前后对比。

## 11. 开发优先级

按“用户少操作”目标，下一阶段优先级应调整为：

1. `/free-check` 到 `ProjectSeed`：输入官网自动建档。
2. `competitor.discover` 和 `question.generate_map`：自动竞品和问题地图。
3. `/console/checkup` 到 `scan_run_detail`：扫描状态、部分失败、半自动导入。
4. `/console/facts` 到 `fact_review_queue`：事实卡审核队列。
5. `/console/gaps` 到 `/console/assets`：缺口转资产。
6. `/console/publishing` 到 `/console/reports`：发布观察、复测和报告。
7. `/console/assistant`：P2，不阻塞主链。

不建议优先做：

- 复杂手动项目表单。
- 复杂权限后台。
- 完整 CMS 自动发布。
- 纯展示型官网二级页深度组件化。
- 没有证据链的 AI 聊天助手。

## 12. 文案和交互要求

面向用户的按钮应该体现“系统帮你做”，不要让用户理解内部技术。

推荐文案：

| 场景 | 推荐文案 | 避免文案 |
| --- | --- | --- |
| 官网输入 | 免费测一测 | 创建项目 |
| 预检 | 正在识别品牌和公开资料 | 正在创建 ProjectSeedJob |
| 竞品 | 我们找到了这些可能竞品，请确认 | 请录入 10 个竞品 |
| 问题 | 已生成买家会问的高意向问题 | 新建问题 |
| 事实 | 请确认这些可公开事实 | 编辑 FactAtom |
| 缺口 | 这些证据缺口正在影响 AI 推荐 | 查看 gap records |
| 资产 | 生成 AI 收录包 | 创建 content asset |
| 发布 | 记录发布 URL 并加入复测 | 创建 publish record |
| 报告 | 查看复测增长报告 | 生成 JSON 报告 |

## 13. 风险控制

自动化不能绕过可信边界：

- Hermes 可以检索公开资料，但不能把未知来源事实直接设为 confirmed。
- Hermes 可以生成内容，但不能把未确认客户案例发布。
- Hermes 可以建议竞品差异，但不能生成攻击性或无法证实的竞品贬损。
- Hermes 可以观察发布页面，但 MVP 不自动登录客户 CMS。
- Hermes 可以生成报告，但报告结论必须带证据索引。

## 14. 与 Xinghe/Hermes 的边界

本规格里的 Hermes 是能力层，不是 AIRank 主数据源。

AIRank 保留：

- 项目、竞品、问题、扫描、事实、缺口、资产、发布、复测、报告的主数据。
- 租户隔离。
- 审核状态。
- 证据链。
- 对外 API contract。

Hermes/Xinghe 提供：

- 联网检索。
- 复杂抓取。
- 归因分析。
- 内容生成。
- 周期复测。
- 自动报告草稿。

接入方式必须通过 `packages/contracts` 和后续 `packages/xinghe-adapter`，不能直接复制 `XingheAI2026V2` 内部业务代码。


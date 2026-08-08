# AIRank 外部能力吸收矩阵

- 基线日期：2026-08-08
- 证据锁定：`docs/architecture/absorption-source-lock.json`
- 产品目标：用真实证据证明品牌在多平台 AI 回答中的可见度、事实准确性与干预变化。
- 取舍枚举：`absorb`（吸收稳定契约或数据字典）、`adapt`（重建为 AIRank 领域能力）、`reference_only`（只作为方法、评测或数据参考）、`reject`（不进入产品）。
- 状态枚举：`ready`、`partial`、`planned`、`blocked`、`disabled`、`rejected`。

## 结论先行

1. AIRank 已完成测量可信度的第一轮修复：四类 Cohort、Prompt 版本、重复采样、会话 ID、surface/evidence level、不可变 hash 和样本状态已进入领域、API 与数据库迁移；有效、失败和阻塞任务都保存独立 Answer/EvidenceSnapshot，失败不再只有可变任务日志。
2. 盲测不再注入品牌/竞品；正常未提及不再被丢弃；固定 `0.72/0.58` 置信度和按文本顺序猜排名已删除。辅助测、对比测和事实核验使用独立 Prompt 契约。
3. `AnswerSnapshot` 允许保存“有效但无引用”的回答，并把引用召回率与引用支持度分开；浏览器采样只登记真实可见外链，不再把“Provider 原始回答”伪装成 citation。
4. 控制台、无数据库资产包和报告接口已删除固定业务数字与演示产物；无真实 Provider 证据时返回 `empty/unverified`，不会生成品牌指标、完成度、报告或发布包。
5. `geo-citation-lab` 的 CN-GEO 数据适合做引用来源、终端差异、问题分类和数据质量评测；其原始层缺少完整回答、批次、模型版本和采集时间，不能拿来计算品牌推荐率或趋势。
6. `GEORank` 的页面诊断、URL 安全和 BYOK 值得改造；其确定性 fallback 分数不允许进入 AIRank 商业指标。
7. `GEOFlow`、`TokHub` 和 `TokEMS` 提供了成熟的任务、幂等、审核、发布、凭证、探测和审计模式，但 AIRank 必须以自己的领域对象和契约实现，不能复制业务代码。
8. 第二轮代码级复核已锁定当前上游：`yao-geo-skills@201c0c4`、`geo-citation-lab@81ba156`、`GEOFlow@1c1a361`、`GEORank@1df59ad`、`TokHub@f95be48`、`yao-meta-skill@e15472e`。AIRank 已据此先实现统一出站安全和页面可提取性，不把上游页面、固定分数或业务源码直接搬入本仓。

## yao-geo-skills：21 个 Skill 全覆盖

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yao-geo-skills | `yao-geo-tracking` | 为企业建立可复查的监测口径 | `skills/yao-geo-tracking` | 企业/官网 → 追踪方案与报告 | 官网取证、区域口径 | MIT | Cohort/重复采样任务契约已落库 | 区域采集与完整性报告仍缺 | adapt | Measurement Plan Skill | P0 | partial | 同一项目方案可编译为任务契约，字段完整性测试通过 |
| yao-geo-skills | `yao-geo-effect-monitor` | 长期监测、引用台账、谨慎归因 | `skills/yao-geo-effect-monitor` | 平台样本 → 指标、告警、月报 | 真实样本、引用、时间窗 | MIT | 纯函数指标已覆盖有效/失败/阻塞/未提及/稳定性 | T0/T+7/T+14/T+30 与归因语义仍缺 | adapt | Effect Monitor Skill | P0 | partial | 指标从样本重算一致；报告仅使用批准的归因措辞 |
| yao-geo-skills | `yao-deepseek-crawler` | Web 端独立重复采样与原始证据 | `skills/yao-deepseek-crawler` | 问题/轮次 → JSON、截图、排名报告 | 登录态、Browser Bridge | MIT | 通用 Web 采样已记录独立 session、轮次、截图/回答 hash；超时、网络失败、登录/验证码阻塞分开归类并保存失败现场截图 | 仍需真实多轮浏览器门禁证明会话隔离 | adapt | Web Collector Adapter | P0 | partial | 连续多轮保留全部样本、会话 ID、截图 hash 与失败分类 |
| yao-geo-skills | `yao-doubao-crawler` | 豆包 Web/App 分终端证据 | `skills/yao-doubao-crawler` | 问题/轮次/终端 → 回答、截图、XML、来源卡 | 登录态；Appium/AVD（App） | MIT | 只有通用 Web 采样 | 无 App 契约；Web/App 证据混用 | adapt | Web Collector + App Collector | P0 | planned | 同问题 Web/App 独立标记、证据等级不同且可对比 |
| yao-geo-skills | `yao-chatgpt-crawler` | ChatGPT AI Search 多次采样 | `skills/yao-chatgpt-crawler` | 问题/轮次 → 回答、可见来源与概率报告 | 登录态、Browser Bridge | MIT | 浏览器 provider 名录包含 ChatGPT | 没有原生来源面板结构化与会话隔离证明 | adapt | Web Collector Adapter | P1 | planned | 真实多轮样本可追踪到可见来源和截图 |
| yao-geo-skills | `yao-geo-intent-miner` | 把种子词转为买家问题与追问链 | `skills/yao-geo-intent-miner` | 品牌/产品/竞品/区域 → 意图簇、问题、监测 Prompt | 企业事实、市场输入 | MIT | 已有版本化 taxonomy、稳定 question version、规范化去重、人工确认、四类 Cohort，以及 M1 客户授权观察批次、内容 hash、来源内频次、PII 阻断和不可变 provenance | M2 自动连接器、M3 抽样校准、行业覆盖 benchmark 和追问链仍缺 | adapt | Research Intent Skill | P0 | partial | M1 记录按批次幂等导入，PII 原文不落库；频次不得标成搜索量；编译后仍须人工确认且 Cohort 匹配才能扫描 |
| yao-geo-skills | `yao-geo-panorama-audit` | 售前基线与机会地图 | `skills/yao-geo-panorama-audit` | 多平台样本/官网 → 基线、缺口、优先级 | Measurement 与 Page Audit | MIT | 有 overview/报告接口 | 当前 overview 含固定数字 | adapt | Diagnosis Orchestrator | P1 | planned | 全部结论带样本/页面/事实引用；无静态业务结果 |
| yao-geo-skills | `yao-geo-page-audit` | 页面可抓取性、结构和证据诊断 | `skills/yao-geo-page-audit` | URL → 技术与内容修复清单 | 安全抓取、HTML/Schema 解析 | MIT | 已有 DNS 固定安全抓取、11 条规则、不可变运行/发现表、异步任务、API 和控制台；每项结果带 HTTP/DOM 证据、内容 hash、连接 IP 和规则版本 | sitemap、批量页面、robots.txt/llms.txt 联合诊断和客户站点 corpus 仍缺 | adapt | Page Extractability Skill | P1 | partial | 真实 `example.com` 得到 68 技术分和 11 条可复算发现；桌面/390px 页面无横向溢出且无 console 告警；分数明确不等于品牌推荐率 |
| yao-geo-skills | `yao-geo-page-blueprint` | 将证据缺口转成页面结构 | `skills/yao-geo-page-blueprint` | 缺口/事实 → 模块、Schema、CMS 字段 | 已审核事实、页面诊断 | MIT | 有内容 gap 骨架 | 无事实约束的结构化产物契约 | adapt | Page Intervention Skill | P1 | planned | 缺事实时返回待补证；JSON-LD 通过 schema 验证 |
| yao-geo-skills | `yao-geo-knowledge-base-builder` | 企业知识与事实卡构建 | `skills/yao-geo-knowledge-base-builder` | 多来源资料 → 实体、事实卡、来源索引 | 安全导入、切片、审核 | MIT | 已有 content-addressed 来源导入、不可变来源修订、原文边界切片、事实修订/冲突/审核、ClaimSupport、到期提醒、人工冲突队列和当前有效来源检索 | 自动同步 worker、增量重嵌入和混合检索仍缺；当前明确为 `lexical_only` | adapt | Knowledge Build Skill | P0 | partial | 所有确认事实能定位原文边界、版本和审核记录；旧来源、过期来源或冲突会即时撤销生成资格且不进入当前检索 |
| yao-geo-skills | `yao-geo-brand-graph` | 品牌实体消歧和关系治理 | `skills/yao-geo-brand-graph` | 事实/实体 → 图、JSON-LD、三元组 | 审核事实、实体规则 | MIT | 项目含品牌/竞品，未成图 | 无实体版本、关系证据和消歧 | adapt | Entity Graph Skill | P1 | planned | 每条关系带 ClaimSupport；冲突实体进入人工审核 |
| yao-geo-skills | `yao-geo-title-optimizer` | 产生可审核的标题候选 | `skills/yao-geo-title-optimizer` | 事实/方向 → 标题与评分 | 已审核事实、风险规则 | MIT | 内容资产骨架 | 评分缺少可验证 rubric | reference_only | Intervention Title Skill | P2 | planned | 候选不含无证据声明；rubric 与人工评审一致性达门槛 |
| yao-geo-skills | `yao-geo-explainer-builder` | 生成科普/How-to/FAQ 页面 | `skills/yao-geo-explainer-builder` | 审核事实/问题 → 文章与核验矩阵 | FactAtom、ClaimSupport | MIT | 内容资产骨架 | 生成未强绑定证据 | adapt | Explainer Skill | P1 | planned | 每个事实性 Claim 必须绑定已审核支持证据 |
| yao-geo-skills | `yao-geo-comparison-builder` | 高意图竞品比较页 | `skills/yao-geo-comparison-builder` | 同口径证据 → 比较页、FAQ | 双方公开证据、风险审校 | MIT | 有竞品对象 | 无同口径证据门禁 | adapt | Comparison Skill | P1 | planned | 缺对方证据不做断言；比较维度与来源可下钻 |
| yao-geo-skills | `yao-geo-content-refiner` | 把旧文改成可引用、可抽取内容 | `skills/yao-geo-content-refiner` | 旧文/事实 → 新稿、diff、证据缺口 | 原文快照、FactAtom | MIT | 无完整旧文改造 | 无不可变原文和逐 Claim diff | adapt | Content Refiner Skill | P2 | planned | 原文 hash 不变；新增事实全部有证据；diff 可审计 |
| yao-geo-skills | `yao-geo-article-friendly` | 轻量文章结构修复 | `skills/yao-geo-article-friendly` | 原文 → 草稿、改动说明 | 原文、事实政策 | MIT | 无独立 Skill | 与 refiner 重叠且成熟度仅 scaffold | reject | 合并进 Content Refiner | P3 | rejected | 不注册重复 Skill；能力由 refiner 覆盖 |
| yao-geo-skills | `yao-geo-ranking-article-builder` | 生成榜单/评测页 | `skills/yao-geo-ranking-article-builder` | 竞品证据 → 评选方法、榜单、来源表 | 真实可比数据、风险审核 | MIT | 无 | 榜单极易产生虚假排名 | adapt | Ranking Review Skill | P2 | disabled | 默认禁用；真实同口径数据和人工审核齐备后才可发布 |
| yao-geo-skills | `yao-geo-execution-roadmap` | 把诊断转成 30/60/90 天执行包 | `skills/yao-geo-execution-roadmap` | 缺口/预算 → 路线图 | 已完成诊断、资源输入 | MIT | 有 gap，未形成项目组合 | 容易把计划包装成效果 | reference_only | Delivery Playbook | P2 | planned | 明确区分计划、执行和观察证据，不进入效果指标 |
| yao-geo-skills | `yao-geoflow-cli` | GEOFlow 运维契约与高风险确认 | `skills/yao-geoflow-cli` | 系统操作 → 操作结果/预检 | GEOFlow 实例 | MIT | AIRank 不依赖 GEOFlow | 产品边界不同 | reference_only | Delivery operation contracts | P2 | planned | 仅吸收幂等、reason、预检模式，不暴露 GEOFlow 操作 |
| yao-geo-skills | `yao-geoflow-template` | 旧 PHP 模板兼容 | `skills/yao-geoflow-template` | 旧模板 → 迁移说明 | GEOFlow legacy | MIT | 无 | 与 AIRank 无关 | reject | 无 | P3 | rejected | 不进入 registry |
| yao-geo-skills | `yao-geoflow-design` | GEOFlow 主题复制与渠道前端 | `skills/yao-geoflow-design` | 参考站 → 主题 JSON/预览 | GEOFlow Blade 主题 | MIT | AIRank 有独立视觉体系 | 直接吸收会破坏产品边界 | reject | 无 | P3 | rejected | 保留 AIRank UI；不注册此 Skill |

## geo-citation-lab：研究、数据与质量契约

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| geo-citation-lab | 引用选择 vs 引用吸收 | 避免把“被列为来源”误当“支持了回答” | `01-geo-experiment-data-report/03-pipeline` | 回答/页面 → selection/absorption 特征 | 完整回答和页面正文 | 分范围许可 | 已新增不可变 Answer Claim 边界、追加式 Citation Support Review、支持/矛盾/不足标签、证据等级与独立支持率；Provider 摘要/来源面板复核只算 provisional，只有人工核对的不可变来源页面快照进入可交付支持率；API、MySQL 和证据中心已接入 | 安全抓取引用页面并自动生成 `citation_source_page` 对象、人工标注集与一致性 benchmark 仍缺 | absorb | Citation + ClaimSupport | P0 | partial | 同一引用的 selection count 与 support rate 分开展示；旧复核不覆盖、只由最新 claim/citation 对生效；无页面快照时支持率必须为 null |
| geo-citation-lab | 问题多维分类 | 提供意图、风格、时效和场景基准 | `data/reference/question_taxonomy.csv` | Prompt → 多维标签 | 版本化 taxonomy | CC-BY-4.0 | 已有 `question_type/intent_level/buyer_stage/prompt_style/temporal_scope/scenario` 与四类 Cohort，版本和来源进入不可变修订 | 620 问题基准尚未导入，行业标签一致性 benchmark 仍缺 | absorb | Prompt Cohort taxonomy | P0 | partial | 当前契约/对抗用例通过；后续基准导入必须保留数据版本与来源 |
| geo-citation-lab | Web/App 平台字典 | 强制终端分开比较 | `data/reference/ai_platforms.csv` | 平台代码 → 产品族/终端/映射证据 | 版本化字典 | CC-BY-4.0 | API/Web/App/manual_import 契约与证据等级已分开 | App 采集器仍未实现 | absorb | CollectorSurface manifest | P0 | partial | Web/App 不会聚合到同一证据等级或同一分母 |
| geo-citation-lab | 不可变原始层与内容 hash | 支撑数据追溯和重建 | `warehouse_contract.json`、构建脚本 | JSONL → Parquet/DuckDB/marts | manifest、SHA-256 | MIT code | 每个有效/失败/阻塞任务均有 Answer/EvidenceSnapshot 与原始响应 hash；浏览器失败现场和回答截图使用独立内容寻址对象，读取时复验 SHA-256/大小，真实 MinIO write/read/delete 已通过 | 批量完整性巡检与派生表重建仍缺 | adapt | EvidenceSnapshot store | P0 | partial | 单对象篡改会返回完整性错误；仍需全库巡检与派生表重建 |
| geo-citation-lab | 来源类型与权威度治理 | 支撑来源结构、缺口和人工复核 | `data/reference/source_types.csv` | 域名 → 类型/状态/置信度/证据 | 参考表和人工审核 | CC-BY-4.0 | citation 有 source_type | 无分类方法、置信度和治理状态 | absorb | Source Registry | P1 | planned | 精确映射优先；未知来源保持 unclassified，不猜测 |
| geo-citation-lab | 214,119 条 CN-GEO 引用数据 | 提供平台差异和引用分析基准 | `03-cn-geo-citation-dataset/data` | 原始引用 → 标准表/质量报告 | 数据版本 2.0.1 | CC-BY-4.0/上游条款 | 无公开 benchmark | 缺回归数据 | reference_only | Eval datasets | P1 | planned | 只用于引用/终端/来源评测；禁止计算推荐率、趋势和情感 |
| geo-citation-lab | 数据质量门禁 | 防止猜测缺失字段或误删样本 | `quality_report.json`、tests | 数据仓库 → checks/known limitations | 固定依赖与清单 | MIT code | `airank.measurement-quality.v3` 执行 22 项检查；每组问题/Provider/Cohort/采集面/模型至少 3 个独立 sample index 与 session；每个任务样本加载独立 Evidence Manifest，失败/阻塞也必须有原始响应 hash；API、Web、App 和人工导入按采集面分别门禁 | App 采集器、全库派生表重建和多格式交付物视觉门禁仍缺 | adapt | Evidence data gate | P1 | partial | 单次采样或重用会话必须 `quality_blocked`；质量报告具备 data/report SHA-256、分采集面汇总与 known limitations；失败快照、终端证据或复测口径不合格时 `publishable=false` |

## GEOFlow：知识、审校、发布与恢复

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEOFlow | 企业知识 Source/Revision | 知识导入、草稿与版本治理 | `EnterpriseKnowledge*` models/services | 来源 → revision/draft | DB、队列、审核 | Apache-2.0 | KnowledgeSource/FactRevision/FactConflict、不可变来源修订、旧版本 stale、有效期、到期治理摘要和人工冲突裁决 UI 已实现 | 客户来源自动同步 worker 仍缺 | adapt | Knowledge domain | P0 | partial | 新修订不覆盖旧证据；依赖旧来源的事实即时失效，冲突保存人工裁决人、时间与说明 |
| GEOFlow | 语义切片与增量同步 | 可重建的知识检索基础 | `KnowledgeChunkSync*`、`KnowledgeSourceParser` | source → chunks/embedding | pgvector/embedding | Apache-2.0 | 已有 source/content hash 幂等导入、版本化切片、保持原文拼接一致的边界和仅覆盖 active/有效期来源的 `lexical_only` 检索 | embedding worker、混合检索、自动差异同步和变更后局部重嵌入仍缺 | adapt | Knowledge ingestion | P1 | partial | 相同 hash 幂等；新版本建立独立切片，旧版本不可检索；向量状态明确为 `not_configured` |
| GEOFlow | 内容风险扫描和审核门禁 | 阻止无证据或高风险内容发布 | `ArticleRisk*`、`ArticleReview` | 草稿 → 风险、审核、override | 规则、审核角色 | Apache-2.0 | 已有 Claim 覆盖核验、风险规则、内容 hash 绑定审核和高风险 override 审计 | 风险规则集和审核 UI 仍需扩充 | adapt | Governance Skills | P0 | partial | 未过事实/风险门禁不能生成发布任务 |
| GEOFlow | Publisher Manager | 支持 WordPress、HTTP 与可扩展渠道 | `DistributionPublisherManager`、publishers | 发布快照 → URL/响应/日志 | 渠道凭证、网络 | Apache-2.0 | 审核后不可变发布快照、export、受白名单保护的 WordPress/HTTP worker、attempt 哈希回执与失败恢复已实现 | 缺客户真实站点凭证和线上回执；未验证的渠道仍为 partial | adapt | Delivery Gateway | P1 | partial | WordPress/HTTP contract + 真实 MySQL attempt/retry 通过；客户站点 E2E 后晋级 |
| GEOFlow | 发布幂等、租约与失败恢复 | 避免重复发布并支持人工恢复 | `DistributionChannelOperationLeaseService`、retry policy | task → attempts/result | durable queue | Apache-2.0 | 发布包具备租户级幂等键、不可变快照、attempt ledger；worker 已消费任务并完成失败重试恢复契约 | 客户真实站点的超时/崩溃恢复和单副作用证据仍缺 | absorb | Delivery job runtime | P1 | partial | contract 与真实 MySQL worker 通过；客户站点验证相同 key 只有一个外部副作用 |
| GEOFlow | SSRF 和出站安全 | 保护官网抓取与发布端点 | `Services/Outbound/*` | URL/request → allowed/blocked | DNS 重解析、大小限制 | Apache-2.0 | 已建立 AIRank 自有 `outbound-security`：每个目标及重定向重验所有 DNS 地址，连接固定到已验证 IP，同时保留原主机 TLS SNI/证书校验；跨域剥离凭证，拒绝私网/过渡 IPv6/编码或超大响应；Publisher 与 Page Audit 已接入 | 其余通用 HTTP connector 尚未全部迁移，恶意 URL corpus 与长时网络故障测试仍需扩充 | adapt | Outbound Security Gateway | P0 | partial | 私网、混合 DNS、redirect、DNS rebinding、跨域 secret、响应上限和 TLS hostname 测试通过；真实页面抓取保存 connected IP |
| GEOFlow | 可见度采集模型 | 参考 run/source 分表与 provider normalizer | `AiVisibility*` | provider response → run/sources | provider client | Apache-2.0 | scan run/snapshot/citation | 缺 surface、session、raw object | reference_only | Measurement schema | P0 | partial | 只吸收结构，不复用其业务实现；新契约通过迁移测试 |
| GEOFlow | 站点主题复制 | 快速生成站点外观 | `SiteThemeReplication*` | 参考站 → 主题包 | Laravel 主题 | Apache-2.0 | AIRank 有独立 UI | 偏离核心证据产品 | reject | 无 | P3 | rejected | 不进入 AIRank |

## GEORank：页面诊断、拓词和 BYOK

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEORank | 页面抓取与企业资料提取 | 建档和页面诊断输入 | `company_ingest.py`、`company_profile.py` | URL/HTML → 页面/企业字段 | 安全 fetch、HTML parser | Apache-2.0 | Page Audit 已真实抓取 title、description、canonical、robots、H1、服务端可见正文、main/article 和 JSON-LD，并保存内容 hash/最终 URL/响应元数据 | 尚未把候选企业字段转成待审核 KnowledgeSource/FactAtom，也未做站点级批量抓取 | adapt | KnowledgeSource importer | P1 | partial | 抓取字段有 selector/文本/响应证据；进入事实库前必须人工审核，AI 派生值不覆盖原响应 |
| GEORank | 页面技术诊断 | 评估 Schema、Meta、结构和可读性 | `tasks/crawl`、diagnostics routes/models | URL → 规则结果 | Celery、抓取 | Apache-2.0 | `airank.page-extractability.v1` 已输出独立 `technical_extractability_score`、逐规则扣分、证据和整改建议 | 站点级模板对比、性能/渲染层诊断和真实客户 benchmark 仍缺 | adapt | Page Audit Skill | P1 | partial | API/UI 只称技术可提取性，visibility/recommendation 指标不读取该分数；持久化结果可从发现项重算 |
| GEORank | 关键词/问题扩展结构 | 扩充买家问题覆盖 | `keyword_expansion.py` | seed → 8 维词包 | LLM 或规则 fallback | Apache-2.0 | 已有种子、产品、竞品、区域输入编译和确定性模板候选，保留来源、版本与 dedupe hash | 未接真实关键词数据源、查询量与行业覆盖质量门禁 | adapt | Intent Miner Skill | P1 | partial | 只把输入种子标为 `provided_seed`、规则扩展标为 `template_candidate`；不虚构搜索量或观察状态 |
| GEORank | 确定性 fallback 分数 | 无模型时生成漂亮结果 | `keyword_expansion.py::_stable_score` | seed → 35-99 分 | 无 | Apache-2.0 | 当前 API 也有固定数字 | 属于伪业务结果 | reject | 无 | P0 | rejected | 生产扫描禁止 fallback；静态扫描门禁无此模式 |
| GEORank | BYOK 请求策略 | 降低平台模型成本并支持客户密钥 | `ai_usage.py`、SDK `byok.ts` | 客户 key/header → provider call | 安全前端/短生命周期 | Apache-2.0 | provider 凭证来自服务端 env | 无租户级安全 BYOK | adapt | Credential Vault / Provider Gateway | P2 | planned | key 不落日志/DB 明文；撤销、轮换和租户隔离测试通过 |
| GEORank | Provider URL 安全 | 避免 BYOK 自定义地址 SSRF | `provider_url_security.py` | base URL → allow/block | DNS/协议策略 | Apache-2.0 | Provider Gateway 强制 HTTPS/官方 host；Publisher 与 Page Audit 共用 DNS 固定客户端，消除“校验后库内重新解析”的 TOCTOU | Provider Gateway 运输层尚未完全统一到该客户端，恶意 URL corpus 仍需扩充 | absorb | Outbound Security Gateway | P0 | partial | 已验证实际 TCP 连接使用校验 IP、TLS SNI 使用原始 hostname；后续所有 connector 必须通过同一门禁 |
| GEORank | 公共公司/专家/教程目录 | 内容门户和公开排名 | `apps/web`、companies/experts/tutorials | 内容 → 公开目录 | 内容运营 | Apache-2.0/数据另行许可 | 无 | 不能证明付费闭环 | reject | 无 | P3 | rejected | 不进入产品主线 |

## TokHub：Provider Gateway

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TokHub | Provider manifest | 统一模型、端点、能力和生命周期 | channel/store models | manifest → eligible upstreams | provider catalog | Apache-2.0 | 四平台 manifest、别名、能力、官方 host、模型生命周期契约已实现 | manifest 持久化同步与后台编辑仍缺 | adapt | Provider Manifest | P0 | partial | manifest schema、版本与迁移测试通过 |
| TokHub | L1/L2/L3 探测 | 区分网络、鉴权、模型和生成故障 | probe services/`probe_runs` | channel → layer results | 凭证、网络 | Apache-2.0 | Gateway 已区分网络、鉴权/模型和真实生成状态；三平台完成真实 L2/L3 | Kimi 安全运行时注入和四平台持久化 probe 记录仍缺 | absorb | Provider Health | P0 | partial | 四平台各产生真实 L1/L2/L3 记录和 request id |
| TokHub | 路由、降级和熔断 | 失败时保护队列和成本 | gateway routing/circuit state | request → chosen upstream | Redis/DB fallback | Apache-2.0 | 统一 Gateway 已有重试/退避/半开恢复，并在配置 MySQL 时使用跨进程 circuit store；状态按 Provider 和配置指纹隔离，真实 MySQL 已验证；独立 Worker/attempt 封闭未知结果 | 仍缺同能力多上游择优/故障转移和跨节点分布式 QPS/并发控制 | adapt | Provider Gateway | P1 | partial | 多 Worker 并行、熔断持久化、租约过期不可重放均通过；补多上游故障注入后才能晋级 |
| TokHub | QPS、并发与配额预留 | 避免超额和预算并发穿透 | quota/reservation/store | request → reserve/commit/release | Redis/事务 | Apache-2.0 | MySQL tenant quota repository 已接 runtime：按租户/UTC 日锁行预留，幂等键防重复，成功提交、失败释放、过期恢复均有集成测试；无数据库时只有进程内保护 | 跨节点 QPS/并发令牌、租户成本预算和压力测试仍缺 | adapt | Quota Service | P1 | partial | 真实 MySQL 并发/幂等测试不超额度且失败归还预留；分布式令牌桶未完成前保持 partial |
| TokHub | 用量 exact/estimated 标记 | 不把估算成本冒充精确成本 | usage events/rollups | response → tokens/cost/provenance | 价格版本 | Apache-2.0 | ProviderUsage 与 usage events 已区分 exact/estimated/unknown；真实三平台均返回 exact | 价格版本、成本计算和报表筛选仍缺 | absorb | Usage Ledger | P1 | partial | 缺上游 usage 时标 estimated，报告可过滤 |
| TokHub | 凭证加密、指纹、轮换 | 支撑安全私有 Provider | credential store/migrations | secret → ciphertext/fingerprint | 主密钥/KMS | Apache-2.0 | env 注入 | 无租户级 vault 与轮换审计 | adapt | Credential Vault | P1 | planned | 明文扫描为零；轮换不暴露旧值；删除执行 scrub |
| TokHub | reason + idempotency + audit | 让高风险操作可审计 | admin agent contracts/store | write → idempotent result/audit | RBAC | Apache-2.0 | 有 audit/outbox 表 | API 写操作未统一执行 | absorb | Operation Guard | P1 | planned | 重放同 key 不重复副作用，冲突 payload 被拒绝 |
| TokHub | 公开示例通道与固定健康分 | 让首页可演示 | seed/store example rows | seed → 静态通道分数 | 无 | Apache-2.0 | AIRank 有相似固定 overview | 会伪装真实健康 | reject | 无 | P0 | rejected | 生产构建与 seed 扫描不得出现静态健康/业务分数 |

## Skill OS 与外围仓库

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yao-meta-skill | Skill IR 与 target compiler | 统一内部 Skill 契约和版本 | `export_skill_ir.py`、compiler scripts | Skill 包 → IR/target artifacts | schema、registry | MIT | 核心 8 Skill 已有 manifest/schema/entrypoint | 尚无 target compiler 和升级迁移 | adapt | `packages/skills` | P0 | partial | 核心 8 Skill 均能序列化、校验和升级 |
| yao-meta-skill | Trigger/输出/盲测 eval | 防止 Skill 只有 Prompt 没能力 | `evals/`、output eval scripts | cases → score/evidence | fixtures/provider runner | MIT | 8 个 Skill 已执行 24 个 contract/holdout/adversarial 用例并通过 schema 与 rubric | 真实 Provider 和人工标注 benchmark 仍未绑定 | absorb | Skill Eval Lab | P0 | partial | `scripts/evaluate_core_skills.py` 必须 24/24；真实证据缺失时不晋级 |
| yao-meta-skill | promotion 与 claim guard | 防止 partial 被宣传为 ready | promotion/claim guard scripts | evidence → promote/block | evidence ledger | MIT | 已生成绑定 registry/eval/实现 hash 的 promotion ledger；8 个 Skill 均因外部证据缺失保留 partial | 尚需逐项提交可校验的真实 Provider/人工 benchmark artifact | adapt | Skill Registry | P0 | partial | artifact 路径与 SHA-256 校验通过才解除 blocker；伪造 header 无法访问管理员 API |
| yao-meta-skill | trust/permission/package gate | 控制网络、凭证和可移植性 | trust/package/install scripts | Skill 包 → trust/report/package | sandbox/manifest | MIT | 无 | 无依赖与权限声明验证 | adapt | Skill Trust Gate | P1 | planned | 依赖、网络、secret、权限、安装模拟全部可审计 |
| yao-open-tools | `tokscr` 本地网页截图 | 保存消费者页面与来源面板证据 | `tools/tokscr` | 页面 → PNG/PDF | 浏览器扩展 | MIT | Playwright 截图会先复制到内容寻址 filesystem/S3/MinIO，并以鉴权 API 读取和复验 hash | viewport、区域与来源面板裁剪元数据仍未完整保存 | reference_only | Evidence Capture | P1 | partial | 截图对象真实 MinIO 往返与租户隔离通过；继续补 viewport/区域/裁剪契约 |
| yao-open-tools | TokKit exact/partial/estimated | 明确成本数据精度 | `tools/tokkit` | 日志/响应 → 用量台账 | 本地日志 | MIT | 无精度枚举 | 容易把估算当真实 | absorb | Usage provenance enum | P1 | planned | 任一成本字段都有 precision 和 source |
| yao-open-tools | TokDoc 报告与版本快照 | 客户报告归档与公开交付 | `tools/TokDoc` | HTML/PDF/Word → 版本/链接 | 本地存储 | MIT | reports 表 | 无不可变交付包 | reference_only | Report Artifact Store | P2 | planned | 导出包 hash、版本、下载回执可追溯 |
| yao-open-skills | 证据分级、版权、安全和决策 Skill | 补充治理 rubric | `skills/yao-*` | 任务 → 多格式报告 | 各 Skill 依赖 | MIT | 无统一 rubric | 与 GEO 主线部分重叠 | reference_only | Governance rubrics | P2 | planned | 只抽取 rubric/失败案例，不注册无关客户 Skill |
| yao-open-prompts | GEO/企业研究 Prompt 库 | 提供候选问题和写作方法 | `prompts/08-ai-marketing` | 输入 → 文本建议 | LLM | CC-BY-4.0 | 有零散生成逻辑 | Prompt 本身无真实证据 | reference_only | Eval/Prompt candidates | P2 | planned | 进入产品前必须转成 schema、事实政策和 eval case |
| TokEMS | 不可变版本、Outbox、RBAC、审计 | 提升发布与交付可靠性 | templates/publishing/common modules | 写操作 → snapshot/event/audit | DB/worker | AGPL-3.0 | AIRank 自有实现已有内容审核、不可变发布快照、幂等包和复测证据索引 | RBAC、outbox 消费和故障恢复仍缺 | reference_only | Delivery architecture | P1 | partial | 只参考模式；AIRank 自有实现通过幂等和恢复测试 |
| TokEMS | 大会报名/支付/签到业务 | 与 GEO 无关 | event/order/payment/check-in modules | 活动数据 → 交易/核销 | 支付、短信、设备 | AGPL-3.0 | 无 | 不属于 GEO 付费闭环 | reject | 无 | P3 | rejected | 不进入领域模型和导航 |
| yaojingang.github.io | 个人博客内容 | 无核心产品能力 | repository content | 内容 → 静态站 | 无 | NOASSERTION | 无 | 许可和业务价值不足 | reject | 无 | P3 | rejected | 不克隆、不吸收 |
| yaojingang | 个人 Profile README | 无产品能力 | profile README | 文本 → 主页 | 无 | NOASSERTION | 无 | 与产品无关 | reject | 无 | P3 | rejected | 不克隆、不吸收 |

## AIRank 内部现有原型的处理

`/Users/bruce/Developer/work/ai-geo-monitoring` 中已经完成 Provider 成本、验证、任务进度、失败重试、知识导入、通知和付费试点门禁。它属于 AIRank 的本地实验实现，不作为外部开源项目直接复制；只把通过测试的契约和行为迁移到本仓的 Python/FastAPI 领域模型，并重新跑本仓单元、迁移、Provider 和浏览器门禁。

## 第一批核心 8 Skill

1. `measurement.sample-runner`
2. `measurement.answer-parser`
3. `measurement.citation-extractor`
4. `research.intent-miner`
5. `knowledge.fact-builder`
6. `governance.claim-verifier`
7. `intervention.page-blueprint`
8. `delivery.retest-report`

核心 8 Skill 已完成统一 manifest、输入输出 schema、证据等级、事实政策、失败政策、rubric、entrypoint，以及独立 contract/holdout/adversarial 评测。24/24 用例通过，Promotion Evidence Ledger 绑定 registry、评测语料、实现和评测引擎 hash；因真实 Provider/人工标注 benchmark 尚未逐项绑定，全部继续保持 `partial`。内部 Skill 控制台明确展示本地通过数、可晋级数和每项缺证 blocker。

## 阶段一完成判定

- 12 个公开仓库都有明确取舍，10 个相关仓库锁定 commit 并完成代码级入口定位。
- `yao-geo-skills` 的 21 个 Skill 全部逐项覆盖。
- 所有 `absorb/adapt/reference_only/reject` 都有目标模块和验收方法。
- 许可证边界已记录；CN-GEO 数据、原创内容和第三方论文不混用许可。
- 下一阶段的 P0 已明确：先修测量可信度，暂停继续堆内容生成页面。

## 阶段二当前证据（2026-08-08）

- `20260808_0003_measurement_credibility.py` 已在临时 MySQL 空库真实执行，Alembic head 为 `20260808_0003`；9 个关键 AnswerSnapshot 字段和 2 张新表均完成核验，随后删除临时验收库。
- `20260808_0004_fact_evidence_governance.py` 已在临时 MySQL 空库真实执行，Alembic head 为 `20260808_0004`；29 张 AIRank 表、5 张事实治理表和 3 个 FactAtom 版本字段完成核验，随后删除临时验收库。
- `20260808_0006`—`0013` 已在真实 MySQL 执行，Alembic head 为 `20260808_0013`；52 张 AIRank 表完成核验。`0010` 新增不可变问题观察批次与记录，`0011` 新增采样任务 attempt 台账，`0012` 新增页面可提取性运行与逐规则发现，`0013` 新增回答断言与追加式引用支持复核。
- 买家问题现在使用 `airank-question-taxonomy-v1.2.0`，分别记录问题类型、意图、买家阶段、风格、时效、场景、来源、输入 hash、去重 hash、稳定问题版本和 provenance records；未确认问题以及与 ScanRun Cohort 不一致的问题不会被编译成采样任务。
- `research.intent-miner` 已吸收 M0/M1 边界：无数据时只生成假设候选；客户授权数据进入 `user_provided_snapshot` 批次并明确“未独立核验”。来源内出现次数只保存为 occurrence count，不作为搜索量；疑似邮箱、手机号或身份证的原文只计算内容 hash 和阻断原因，不进入数据库、API 响应或问题版本。
- `airank.measurement-quality.v3` 将复测报告的“已生成”与“可交付”分开：每个 ScanRun 都能重算内容寻址质量报告，未提及仍计入有效分母；单次采样、少于 3 个独立 sample index 或重用 session 会直接阻断交付。除样本、签名、有效率、回答/原始响应 hash 外，API/Web/App/manual_import 分别执行证据门禁。Web/App 的 `source_panel_status` 必须为 `captured` 或 `not_present`；有引用时还必须绑定不可变来源面板对象。基线与复测任一质量失败或口径不可比时，报告只保存为 `quality_blocked` 且下载 API 返回 `409 REPORT_QUALITY_BLOCKED`。
- 真实 ScanRun 默认由 `airank_async_jobs` 与 Worker 异步执行；每个采样槽独立领取、心跳并在单事务中写回答、证据、引用、请求审计、attempt 和 job/task 状态。同批次不同槽可由多个 Worker 并行；运行指标只在全部槽终态后从持久化样本重算。进程崩溃只把结果未知的当前槽记为 `SCAN_TASK_LEASE_EXPIRED` 与 `unknown` attempt，不重放 Provider，也不破坏兄弟槽证据。证据中心可下钻 attempt 链。跨进程 MySQL 熔断和租户配额已经接入；多上游路由和分布式 QPS/并发仍未完成，因此 TokHub 路由能力仍为 `partial`。
- 知识治理新增项目级开放冲突查询和 1—365 天有效期观察窗：来源到期、已批准事实到期与开放冲突均从原始对象实时派生，不自动改写状态；来源过期、尚未生效或冲突开放时，FactRevision 即时失去内容生成资格。真实 MySQL 已验证冲突创建、资格阻断、人工裁决、资格恢复、UTC 序列化和重复修订对 `409` 门禁。
- 千问、豆包、Kimi、DeepSeek（当前可用型号为 `deepseek-v3.2`）均已通过本仓 Provider Gateway 真实 L3 调用并返回真实 request ID；凭证只从本机私密环境映射到进程。Kimi 已暴露过的验收密钥必须在生产前轮换，DeepSeek 新型号额度和旧型号下架迁移仍是上线门禁。
- 页面安全抓取切片已通过 38 项定向测试和真实 MySQL integration；真实浏览器完成 `example.com` 异步抓取，得到 HTTP 200、内容 SHA-256、DNS 固定连接 IP、11 条规则和 68 分技术可提取性。桌面与 390×844 移动端均无页面级横向溢出，console 为 0 warning / 0 error。该分数只表示服务器页面可提取条件，不能推导品牌推荐率。
- 引用支持度切片把 Provider 原生 citation 作为 selection 事实保存，把回答 Claim 与来源复核作为独立 append-only 证据。全量测试 `295 passed, 19 skipped`，真实 MySQL `17 passed, 2 skipped`；浏览器下钻显示 1 个已选择来源、1 条回答断言、1 个 provisional 复核，但因没有不可变来源页面快照，客户报告支持率保持“待核验”。桌面/390px 无 console warning/error，临时验收数据已清理。
- 前端 TypeScript/Vite 构建通过；本机 Node `20.18.2` 低于 Vite 建议的 `20.19+`，当前是环境告警而非构建失败，生产构建镜像需升级。
- 控制台静态业务结果已删除，11 个路由改用真实 API 或显式 `partial/blocked/disabled` 状态；桌面与 390px 空项目浏览器验收通过。该证据不替代带真实项目数据的全链路 E2E。
- 当前阶段仍是 `partial`：四平台同一版本问题的真实重复采样、消费端 Web/App 证据、生产凭证轮换、外部 Publisher 和从建档到客户报告的带数据 E2E 尚未全部通过，因此不允许声明商业可用。

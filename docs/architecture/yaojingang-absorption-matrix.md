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
9. 账号新增的 `haidian@707b4b6` 是城市设计征集仓且未声明许可证，不属于 GEO 业务代码来源；其中“候选来源先进入待复核草稿、AI 审核不得覆盖确定性门禁、离线评审包同时汇总风险/假设/来源/指标/文件”的治理方法对 AIRank 有价值，只按 `reference_only` 吸收方法，不复制代码、页面或素材。
10. `Customer Evidence Packet` 已升级为 AIRank 自有 `airank.report-evidence-packet.v7`：仅在基线/复测质量门禁和项目级 `airank.evidence-integrity.v2` 源证据及派生状态巡检同时通过后生成。v2 会从真实任务、快照、审计和最终复核状态重建 ScanRun 任务数、Retest 对比指标、报告 hash/status、观察窗口结果和 Retest 摘要，不信任报告表自报数字。v7 以确定性 ZIP 交付 canonical manifest、可打印 HTML、全空白正式评分表、README 与逐文件 SHA256SUMS；离线工具重建 manifest/ZIP，并强制使用 API 或下载回执提供的整包 SHA-256 外部锚点，明确不把包内自洽冒充数字签名。来源治理、引用支持与事实准确性仍按最终 `production` 双人一致或第三人裁决结论生成，不复制原始回答或人工说明正文。历史 v1–v6 只读兼容；PDF/Word 与数字签名仍未实现，因此状态保持 `partial`。
11. 品牌/竞品事实准确率不再是占位指标：回答中的事实声明按精确字符边界、声明类型和主体登记，追加式人工审核只能绑定当前有效、人工审核、可披露、无开放冲突且能落到原文精确边界的 `FactRevision`。第一审核与第二盲审必须由不同账号执行，分歧必须由第三个不同账号裁决；旧单人审核与 benchmark 不进入商业指标。事实或来源过期、被替代或发生冲突时，旧裁决保留但自动退出当前商业指标；`insufficient` 单独统计且不绑定虚构事实。控制台可下钻登记、盲审和裁决，报告与 v6 证据包按当前证据重新计算覆盖率和准确率。
12. `yao-geo-effect-monitor` 与 GEOFlow 的到期任务模式已改造为 AIRank 自有持久调度器：发布后窗口按 T0/T+7/T+14/T+30 执行，T0 只锚定真实基线，后续窗口从基线任务的冻结请求克隆同口径任务并创建全新 session；Worker 与 Scheduler 默认都拒绝无租户/项目范围运行，全局多租户处理需要环境变量和命令行双重授权。真实时间流逝后的客户观察证据尚未产生，因此能力仍为 `partial`。
13. `geo-citation-lab` 的来源字典已改造为 AIRank 自有 Source Registry：只登记项目 Citation 中实际出现的精确 DNS host，未知来源保持 `unclassified`；人工复核追加记录一级/细分类、主体、置信度、权威度、用途、风险、证据 URL/说明、有效期和 supersedes 链。旧版本、原始 Citation 与样本不被覆盖，幂等回放旧请求也不会把旧版本显示成当前分类。Source Registry 已进入 v7 客户证据包、可打印 HTML 和报告下载提示；公开 CN-GEO 字典的版本化批量导入和分类过期运营队列仍未完成，因此状态保持 `partial`。
14. `yao-geo-page-blueprint` 已改造为 AIRank 自有 `intervention.page-blueprint@1.1.0`：只接受当前已批准、可生成、无开放冲突且具有 source hash 与精确原文边界的事实；缺证据时只返回 `needs_evidence`，不生成补写文案。FAQ、事实页、产品页、案例页、研究页、JSON-LD 和 `llms.txt` 共用版本化 Claim/FactRevision/ClaimSupport 绑定，请求标题与编辑方向只进入 brief hash，公开标题由已审核事实元数据确定性生成。通用蓝图不再接受比较页，必须进入专用公平门禁；来源正文与登记 hash 不一致、可执行嵌入内容、逐主张支持不完整或正文 hash 变化都会失败关闭。CMS 字段映射和完整 Schema.org 语义 benchmark 仍未完成，因此保持 `partial`。
15. `yao-geo-comparison-builder` 已改造为 `intervention.comparison-builder@1.0.0`：`FactAtom` 新增不可变 `subject_type/subject_ref_id`，禁止修订时换主体；2–4 个主体必须共享至少 10 个维度，所有“主体 × 维度”单元都有当前审核事实、ClaimSupport、source hash 和精确边界后才生成正文。缺一格、主体错配或试图走通用比较模板都会失败关闭；不生成排名、分数、市场份额或无证据优劣结论。
16. `yao-geo-explainer-builder` 已改造为 `intervention.explainer-builder@1.0.0`：定义、机制、步骤、标准、误区、FAQ、边界七类角色必须达到 1/2/3/2/1/2/1 的最低证据数，总计至少 12 条事实和 1400 个非空白证据字符；品牌及别名在事实正文中超过 3 次会阻断。HowTo/FAQPage 结构化数据只引用相同的审核事实，不用编辑 brief 补写公开主张。
17. 第三轮按 GitHub 当前 HEAD 复核 `yaojingang` 账号全部 13 个公开仓库，锁定的 13 个 commit 均未漂移。结合 `yao-geo-knowledge-base-builder` 的证据政策和 GEOFlow 的 Source/Revision、任务恢复、增量切片模式，AIRank 已新增客户授权公开来源自动同步：首次启用、周期派发和人工复查共用持久 job/run 契约；每次抓取使用 DNS 固定安全出站并保存原始页、可见正文、双 hash、连接 IP 和重定向元数据。正文未变时记录 `unchanged` 且不制造新版本；正文变化时追加 KnowledgeSource 修订、保留旧版本为 `stale` 并立即撤销依赖旧来源事实的生成资格；瞬时网络或对象存储错误按 5/10 秒指数退避重试，第三次仍失败才终止。自动发现未授权站点、向量重嵌入和混合检索仍未进入当前范围。
18. `geo-citation-lab` 的标注质量方法与 `haidian` 的确定性评审边界已改造为 AIRank 自有独立复核域：引用支持和事实准确性共用不可变 case 契约，第一审核结论在任务终结前对第二审核人与裁决人隐藏；同一账号不能自审，分歧必须第三人裁决。`production` 与 `benchmark` 严格隔离，benchmark 至少 20 个完成双人样本且 Cohen's kappa ≥ 0.80 才通过质量门禁，低一致性不会因“可计算”而伪装成 ready。当前真实客户标注集为 0/20，因此门禁保持阻断。
19. 不可变原始层已升级为项目级 `airank.evidence-integrity.v2`：保留 v1 对 Answer/EvidenceSnapshot、引用抓取与来源边界、知识正文与切片边界、事实修订和非报告对象存储的逐条校验，并从原始任务、快照、请求审计、引用与最终审核状态确定性重建 ScanRun 任务数及 Retest 报告的质量、对比指标、hash/status、观察窗口结果和 Retest 摘要。所有 verified 与 blocking finding 均持久化；源证据篡改、派生数据漂移、未知报告类型、空项目或超过 10,000 个实体均失败关闭。证据中心可执行和下钻，客户包升级到 v7 并绑定巡检 manifest；当前真实项目 39/39 通过。更广泛的派生实体和大项目分片仍未实现。
20. Provider 原生引用已升级为版本化白名单解析：`airank.provider-native-citation.v2` 只接受千问 `search_info`、Responses `web_search_call.action.sources`、Provider annotation 或顶层 citation 等已声明结构，保存 native type、原始 JSON path 和 source id；回答正文、调试字段或任意嵌套 URL 不再冒充引用。`airank.provider-search-evidence.v1` 独立记录“未请求、显式工具调用、显式 usage、显式无搜索或已请求但不可验证”。7/7 版本化 benchmark 已通过；千问 `responses_web_search` 在 3 个全新会话中得到 3/3 有效未提及样本和 135/90/135 条原生引用，质量 v4 通过且引用召回率为 100%。这只证明该千问 API 路由存在真实来源选择，不代表引用支持、事实准确率、Consumer Web/App 或品牌增长已经通过。
21. 高引用量样本的来源正文准备已改为有界批量工作流：快照级 API 明确接收 1–50 个唯一 Citation ID，整批先校验租户/快照归属与全部安全 URL，任何永久无效项都会在零入队状态失败；子任务使用批次上下文 hash 和确定性子幂等键，响应中区分新增与回放。证据中心单次只入队前 20 条，以一个 latest-summary 请求替代逐 Citation 列表查询，正文片段只在用户展开单条时按 capture ID 加载。真实 MySQL/Worker/浏览器用 21 条引用验证 20 条完成、1 条待处理、无横向溢出和 0 console warning/error；来源抓取完成仍不进入 Citation Support 指标。
22. Citation Support 的 Claim 工作台不再把整段回答当唯一入口，也不再把所有来源片段隐式绑定第一条 Claim。审核人可以直接在不可变回答中选择精确文本，系统把 DOM 选择确定性映射为 answer start/end；粘贴原句时必须在回答内唯一。每条来源复核前必须在选择器中明确指定当前 Claim，支持/矛盾/不足决定只绑定该 Claim。隔离真实 MySQL/Worker/浏览器登记了 0–29 与 29–54 两条 Claim，选择第二条后创建的 production case 经数据库核验确实绑定第二条并进入 `awaiting_secondary`，没有落到第一条。
23. 独立复核从“只能进入某个样本后才看见”升级为项目级当前账号待办。前端调用既有项目级 case 契约，严格按服务端 actor-specific `next_action` 只汇总当前账号可执行的第二审核和第三人裁决；未终结的同伴标签继续返回空 `visible_decisions`。待办不提供脱离证据的快捷裁决，必须先打开不可变样本、精确 Claim 和来源，再在样本内提交。隔离真实 MySQL/浏览器以第二审核账号看到 1 条 `submit_secondary`、0 条可见第一审决定并成功下钻；1543px/390px 无页面级溢出且干净页 console 0/0。持久分派、SLA、分页和客户审核团队 benchmark 仍待实现。
24. 项目级独立复核待办已从前端截断升级为服务端 actor-specific seek cursor：数据库只扫描 `awaiting_secondary/disputed`，排除当前账号已参与的 case，争议裁决优先、同优先级按最早创建时间和 case ID 稳定排序；每页最多 50 条，游标只编码排序锚点，不返回同伴标签。完整 case 接口继续承担全项目统计与 kappa，避免分页改变质量分母。隔离真实 MySQL 创建 14 条待办（2 条争议、12 条二审），第 1 页 12 条、第 2 页 2 条、14 条唯一且第一页前两条均为裁决；浏览器真实网络请求、下钻、1543px/390×844 和 console 0/0 全部通过。持久分派、审核团队路由、SLA/升级和真实客户 20 条 benchmark 仍为 `partial`。

## yao-geo-skills：21 个 Skill 全覆盖

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yao-geo-skills | `yao-geo-tracking` | 为企业建立可复查的监测口径 | `skills/yao-geo-tracking` | 企业/官网 → 追踪方案与报告 | 官网取证、区域口径 | MIT | Cohort/重复采样任务契约已落库 | 区域采集与完整性报告仍缺 | adapt | Measurement Plan Skill | P0 | partial | 同一项目方案可编译为任务契约，字段完整性测试通过 |
| yao-geo-skills | `yao-geo-effect-monitor` | 长期监测、引用台账、谨慎归因 | `skills/yao-geo-effect-monitor` | 平台样本 → 指标、告警、月报 | 真实样本、引用、时间窗 | MIT | 指标覆盖有效/失败/阻塞/未提及/稳定性；持久 Scheduler 已实现 T0 锚定和 T+7/T+14/T+30 到期派发，严格克隆冻结 Prompt、Provider、Cohort、surface、模型上下文并创建全新 session；终态比较继续走 v4 质量门禁和审慎归因 | 尚无真实时间流逝后的客户 T+7/T+14/T+30 artifact、运营告警与月报节奏 | adapt | Effect Monitor Skill | P0 | partial | 真实 MySQL 验证冻结 Prompt、独立 session、幂等派发、失败复测 `quality_blocked`；后续用真实观察窗口验证变化措辞 |
| yao-geo-skills | `yao-deepseek-crawler` | Web 端独立重复采样与原始证据 | `skills/yao-deepseek-crawler` | 问题/轮次 → JSON、截图、排名报告 | 登录态、Browser Bridge | MIT | 通用 Web 采样已记录独立 session、轮次、截图/回答 hash；超时、网络失败、登录/验证码阻塞分开归类并保存失败现场截图 | 仍需真实多轮浏览器门禁证明会话隔离 | adapt | Web Collector Adapter | P0 | partial | 连续多轮保留全部样本、会话 ID、截图 hash 与失败分类 |
| yao-geo-skills | `yao-doubao-crawler` | 豆包 Web/App 分终端证据 | `skills/yao-doubao-crawler` | 问题/轮次/终端 → 回答、截图、XML、来源卡 | 登录态；Appium/AVD（App） | MIT | 只有通用 Web 采样 | 无 App 契约；Web/App 证据混用 | adapt | Web Collector + App Collector | P0 | planned | 同问题 Web/App 独立标记、证据等级不同且可对比 |
| yao-geo-skills | `yao-chatgpt-crawler` | ChatGPT AI Search 多次采样 | `skills/yao-chatgpt-crawler` | 问题/轮次 → 回答、可见来源与概率报告 | 登录态、Browser Bridge | MIT | 浏览器 provider 名录包含 ChatGPT | 没有原生来源面板结构化与会话隔离证明 | adapt | Web Collector Adapter | P1 | planned | 真实多轮样本可追踪到可见来源和截图 |
| yao-geo-skills | `yao-geo-intent-miner` | 把种子词转为买家问题与追问链 | `skills/yao-geo-intent-miner` | 品牌/产品/竞品/区域 → 意图簇、问题、监测 Prompt | 企业事实、市场输入 | MIT | 已有版本化 taxonomy、稳定 question version、规范化去重、人工确认、四类 Cohort，以及 M1 客户授权观察批次、内容 hash、来源内频次、PII 阻断和不可变 provenance | M2 自动连接器、M3 抽样校准、行业覆盖 benchmark 和追问链仍缺 | adapt | Research Intent Skill | P0 | partial | M1 记录按批次幂等导入，PII 原文不落库；频次不得标成搜索量；编译后仍须人工确认且 Cohort 匹配才能扫描 |
| yao-geo-skills | `yao-geo-panorama-audit` | 售前基线与机会地图 | `skills/yao-geo-panorama-audit` | 多平台样本/官网 → 基线、缺口、优先级 | Measurement 与 Page Audit | MIT | 有 overview/报告接口 | 当前 overview 含固定数字 | adapt | Diagnosis Orchestrator | P1 | planned | 全部结论带样本/页面/事实引用；无静态业务结果 |
| yao-geo-skills | `yao-geo-page-audit` | 页面可抓取性、结构和证据诊断 | `skills/yao-geo-page-audit` | URL → 技术与内容修复清单 | 安全抓取、HTML/Schema 解析 | MIT | 已有 DNS 固定安全抓取、11 条规则、不可变运行/发现表、异步任务、API 和控制台；每项结果带 HTTP/DOM 证据、内容 hash、连接 IP 和规则版本 | sitemap、批量页面、robots.txt/llms.txt 联合诊断和客户站点 corpus 仍缺 | adapt | Page Extractability Skill | P1 | partial | 真实 `example.com` 得到 68 技术分和 11 条可复算发现；桌面/390px 页面无横向溢出且无 console 告警；分数明确不等于品牌推荐率 |
| yao-geo-skills | `yao-geo-page-blueprint` | 将证据缺口转成页面结构 | `skills/yao-geo-page-blueprint` | 缺口/事实 → 模块、Schema、CMS 字段 | 已审核事实、页面诊断 | MIT | `intervention.page-blueprint@1.1.0` 已把 7 类通用页面产物绑定到已审核 FactRevision、ClaimSupport、source hash 和精确原文边界；比较页被强制路由到专用 Comparison Skill；控制台使用真实 API 选择合格事实并展示蓝图 hash；审核与发布快照校验正文和蓝图完整性 | 页面审计缺口尚未自动编排；CMS 字段映射与完整 Schema.org 语义验证仍缺 | adapt | Page Intervention Skill | P1 | partial | contract/holdout/adversarial 评测通过；真实 HTTP/MySQL 验证来源→事实→批准→FAQ 蓝图→审核→不可变导出，编辑方向明文未落库；后续补多类型 Schema benchmark |
| yao-geo-skills | `yao-geo-knowledge-base-builder` | 企业知识与事实卡构建 | `skills/yao-geo-knowledge-base-builder` | 多来源资料 → 实体、事实卡、来源索引 | 安全导入、切片、审核 | MIT | 已有 content-addressed 来源导入、不可变来源修订、原文边界切片、事实修订/冲突/审核、ClaimSupport、到期提醒、人工冲突队列、当前有效来源检索，以及客户授权公开 URL 的持久自动同步策略、Scheduler/Worker、运行证据和前端工作台 | 增量重嵌入和混合检索仍缺；当前明确为 `lexical_only`，不会擅自发现未授权站点 | adapt | Knowledge Build Skill | P0 | partial | 真实 MySQL 与浏览器验证首次变更追加 v2、v1 stale、双对象存证；第二次相同正文为 `unchanged` 且不生成 v3；旧来源、过期来源或冲突即时撤销生成资格 |
| yao-geo-skills | `yao-geo-brand-graph` | 品牌实体消歧和关系治理 | `skills/yao-geo-brand-graph` | 事实/实体 → 图、JSON-LD、三元组 | 审核事实、实体规则 | MIT | 项目含品牌/竞品，未成图 | 无实体版本、关系证据和消歧 | adapt | Entity Graph Skill | P1 | planned | 每条关系带 ClaimSupport；冲突实体进入人工审核 |
| yao-geo-skills | `yao-geo-title-optimizer` | 产生可审核的标题候选 | `skills/yao-geo-title-optimizer` | 事实/方向 → 标题与评分 | 已审核事实、风险规则 | MIT | 内容资产骨架 | 评分缺少可验证 rubric | reference_only | Intervention Title Skill | P2 | planned | 候选不含无证据声明；rubric 与人工评审一致性达门槛 |
| yao-geo-skills | `yao-geo-explainer-builder` | 生成科普/How-to/FAQ 页面 | `skills/yao-geo-explainer-builder` | 审核事实/问题 → 文章与核验矩阵 | FactAtom、ClaimSupport | MIT | `intervention.explainer-builder@1.0.0` 已实现七类角色、12 条事实、1400 个证据字符、品牌露出上限、逐 Claim 精确边界、HowTo/FAQPage、真实 API/工作台/审核/导出快照 | 尚无真实客户内容质量 benchmark、多格式导出与页面审计自动编排 | adapt | Explainer Skill | P1 | partial | 缺角色、长度、主体或品牌露出门禁不出正文；真实 MySQL 从 12 条主体事实生成 7 段解释、审核并导出 v2 快照 |
| yao-geo-skills | `yao-geo-comparison-builder` | 高意图竞品比较页 | `skills/yao-geo-comparison-builder` | 同口径证据 → 比较页、FAQ | 双方公开证据、风险审校 | MIT | `intervention.comparison-builder@1.0.0` 已实现不可变事实主体、2–4 主体、至少 10 个统一维度、100% 对称证据矩阵、逐 Claim 精确边界和无排名输出；普通蓝图不能绕过 | 尚无真实客户公平性 benchmark、3–4 主体 UI 和外部 CMS 对比模板 | adapt | Comparison Skill | P1 | partial | 缺任一主体维度不出正文；真实 MySQL 以 2 主体×10 维度生成 20 条 ClaimSupport、审核并导出 v2 快照 |
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
| geo-citation-lab | 引用选择 vs 引用吸收 | 避免把“被列为来源”误当“支持了回答” | `01-geo-experiment-data-report/03-pipeline` | 回答/页面 → selection/absorption 特征 | 完整回答和页面正文 | 分范围许可 | Provider 原生选择层使用 `airank.provider-native-citation.v2` 白名单解析并保存 native type/精确 JSON path/source id，任意 URL 不计 Citation；已新增不可变 Answer Claim、追加式 Citation Support Review、支持/矛盾/不足标签、独立支持率；品牌/竞品事实声明另走 Fact Accuracy Review；统一 DNS-pinned 安全抓取保存来源正文和精确边界；快照级批量入口会先校验全部归属/URL、每批最多 50，控制台每次入队 20 并以单次 latest summary + 单条详情懒加载消除高引用量 N+1；Claim 可从不可变回答选区映射精确边界，粘贴文本必须唯一，来源复核前显式选择 Claim；生产审核已接入盲态双人复核、分歧裁决、benchmark 隔离、kappa 门禁、服务端 actor-specific seek cursor 待办、证据中心和 v7 客户包 | 目前只有千问 Responses 路由完成真实原生引用重复采样；真实客户人工标注 benchmark 仍为 0/20，持久分派、审核团队路由、SLA/升级和审核抽检运营仍待客户数据验证 | absorb | Citation + ClaimSupport | P0 | partial | 7/7 原生结构 benchmark；21 条引用真实浏览器只发 1 次 summary、批量 20 条全部完成且详情按需读取；两条精确 Claim 中选择第二条后，真实 case 外键核验未落到第一条；14 条项目待办按 12+2 游标分页，争议裁决优先且 `visible_decisions=[]`；任意调试 URL 不计引用；不同账号双人一致或第三人裁决才可商业核验 |
| geo-citation-lab | 问题多维分类 | 提供意图、风格、时效和场景基准 | `data/reference/question_taxonomy.csv` | Prompt → 多维标签 | 版本化 taxonomy | CC-BY-4.0 | 已有 `question_type/intent_level/buyer_stage/prompt_style/temporal_scope/scenario` 与四类 Cohort，版本和来源进入不可变修订 | 620 问题基准尚未导入，行业标签一致性 benchmark 仍缺 | absorb | Prompt Cohort taxonomy | P0 | partial | 当前契约/对抗用例通过；后续基准导入必须保留数据版本与来源 |
| geo-citation-lab | Web/App 平台字典 | 强制终端分开比较 | `data/reference/ai_platforms.csv` | 平台代码 → 产品族/终端/映射证据 | 版本化字典 | CC-BY-4.0 | API/Web/App/manual_import 契约与证据等级已分开 | App 采集器仍未实现 | absorb | CollectorSurface manifest | P0 | partial | Web/App 不会聚合到同一证据等级或同一分母 |
| geo-citation-lab | 不可变原始层与内容 hash | 支撑数据追溯和重建 | `warehouse_contract.json`、构建脚本 | JSONL → Parquet/DuckDB/marts | manifest、SHA-256 | MIT code | 每个有效/失败/阻塞任务均有 Answer/EvidenceSnapshot 与原始响应 hash；浏览器失败现场和回答截图使用独立内容寻址对象；项目级 v2 巡检逐条保存 verified/blocking finding 和 manifest，确定性重建 ScanRun 任务数及 Retest 报告派生状态，报告 v7 生成前自动失败关闭；确定性 ZIP 支持离线重建与外部 hash 锚定；真实 MinIO write/read/delete 已通过 | 其他派生实体与大项目分片执行仍缺 | adapt | EvidenceSnapshot store | P0 | partial | 真实 MySQL、API 与浏览器项目 39/39 通过；源数据/对象篡改或派生指标漂移测试产生可下钻 finding 并阻断报告 |
| geo-citation-lab | 来源类型与权威度治理 | 支撑来源结构、缺口和人工复核 | `data/reference/source_types.csv` | 域名 → 类型/状态/置信度/证据 | 参考表和人工审核 | CC-BY-4.0 | 已实现项目级精确 host 注册表；只读取 Citation 实际出现域名，未知保持 `unclassified`；追加式人工复核保存分类、主体、置信度、权威度、用途、风险、依据、有效期、审核人、supersedes、请求 hash 与审计事件；MySQL、API、证据中心、v7 ZIP 与可打印 HTML 已贯通 | 公开字典的版本化批量导入和分类过期运营队列仍缺 | absorb | Source Registry | P1 | partial | 真实 MySQL 验证未分类、v1/v2、旧版幂等回放、报告包历史版本和审计；隔离浏览器确认 1/2 来源有效时不生成整体权威性结论，桌面/390px 无页面级溢出且 console 0 warning/error，随后清理 QA 数据 |
| geo-citation-lab | 214,119 条 CN-GEO 引用数据 | 提供平台差异和引用分析基准 | `03-cn-geo-citation-dataset/data` | 原始引用 → 标准表/质量报告 | 数据版本 2.0.1 | CC-BY-4.0/上游条款 | 无公开 benchmark | 缺回归数据 | reference_only | Eval datasets | P1 | planned | 只用于引用/终端/来源评测；禁止计算推荐率、趋势和情感 |
| geo-citation-lab | 数据质量门禁 | 防止猜测缺失字段或误删样本 | `quality_report.json`、tests | 数据仓库 → checks/known limitations | 固定依赖与清单 | MIT code | `airank.measurement-quality.v4` 执行 24 项检查；每组问题/Provider/Cohort/采集面/模型至少 3 个独立 sample index 与 session；Web/App 还必须由采集器确认进入全新会话；每个任务样本加载独立 Evidence Manifest，失败/阻塞也必须有原始响应 hash；API、Web、App 和人工导入按采集面分别门禁；存在品牌/竞品事实声明时，事实覆盖率必须完整才允许形成事实准确率；项目级 v2 巡检作为 v7 客户包硬门禁并重建 ScanRun 与 Retest 报告派生状态 | App 采集器、更广泛派生实体重建、双人事实标注 benchmark 和 PDF/Word 视觉门禁仍缺 | adapt | Evidence data gate | P1 | partial | 失败批次可审计但不可发布；单次采样、重用会话或未验证全新 Consumer 会话必须 `quality_blocked`；质量报告具备 data/report SHA-256；源证据或派生状态巡检阻断时返回 `REPORT_EVIDENCE_INTEGRITY_BLOCKED` |

## GEOFlow：知识、审校、发布与恢复

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEOFlow | 企业知识 Source/Revision | 知识导入、草稿与版本治理 | `EnterpriseKnowledge*` models/services | 来源 → revision/draft | DB、队列、审核 | Apache-2.0 | KnowledgeSource/FactRevision/FactConflict、不可变来源修订、旧版本 stale、有效期、到期治理摘要、人工冲突裁决 UI，以及客户授权公开来源的持久自动同步已实现 | 客户私有连接器、批量站点来源和内容撤回策略仍缺 | adapt | Knowledge domain | P0 | partial | 新修订不覆盖旧证据；真实抓取变化追加 v2 并让依赖 v1 的事实即时失效，相同正文只记录 `unchanged` |
| GEOFlow | 语义切片与增量同步 | 可重建的知识检索基础 | `KnowledgeChunkSync*`、`KnowledgeSourceParser` | source → chunks/embedding | pgvector/embedding | Apache-2.0 | 已有 source/content hash 幂等导入、版本化切片、保持原文拼接一致的边界、公开来源自动差异同步和仅覆盖 active/有效期来源的 `lexical_only` 检索；变更只为新修订建立独立切片 | embedding worker、混合检索和变更后局部重嵌入仍缺 | adapt | Knowledge ingestion | P1 | partial | 相同正文不制造新修订；变化正文生成独立切片，旧版本不可检索；向量状态明确为 `pending/not_configured` |
| GEOFlow | 内容风险扫描和审核门禁 | 阻止无证据或高风险内容发布 | `ArticleRisk*`、`ArticleReview` | 草稿 → 风险、审核、override | 规则、审核角色 | Apache-2.0 | 已有控制台审核 UI、逐主张 ClaimSupport 覆盖、蓝图正文 hash 完整性、标题/正文风险扫描和高风险 override 审计；两个支持错误集中到同一主张时仍会阻断另一主张 | 风险规则运营、双人审核和客户行业规则集仍需扩充 | adapt | Governance Skills | P0 | partial | 内存 contract 与真实 MySQL 反例均证明未过逐主张事实/风险门禁不能生成发布任务；客户端审核人由认证身份覆盖 |
| GEOFlow | Publisher Manager | 支持 WordPress、HTTP 与可扩展渠道 | `DistributionPublisherManager`、publishers | 发布快照 → URL/响应/日志 | 渠道凭证、网络 | Apache-2.0 | 审核后不可变发布快照、export、受白名单保护的 WordPress/HTTP worker、attempt 哈希回执与失败恢复已实现；发布中心可从已审核内容创建真实包，并登记 URL、已校验截图对象和 completed baseline 后建立观察窗口 | 缺客户真实站点凭证、线上回执、更新与撤回验收；未验证的渠道仍为 partial | adapt | Delivery Gateway | P1 | partial | WordPress/HTTP contract + 真实 MySQL attempt/retry 通过；隔离浏览器完成 export 创建、发布证据登记和四窗口持久化；客户站点 E2E 后晋级 |
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
| TokHub | Provider manifest | 统一模型、端点、能力和生命周期 | channel/store models | manifest → eligible upstreams | provider catalog | Apache-2.0 | 四平台 manifest、别名、能力、官方 host、模型生命周期、`request_kind` 和请求默认值契约已实现；`chat_completions`、`chat_completions_search`、`responses_web_search` 进入 route status、配置指纹、审计和样本元数据；`20260808_0022` 持久化 manifest 默认值与 route 实际请求契约 | 后台编辑、模型目录自动同步与迁移审批仍缺 | adapt | Provider Manifest | P0 | partial | manifest/schema/迁移通过；非法 route request kind 失败关闭；千问 Responses 真实请求与三次样本均能下钻请求类型；四平台历史 12 条审计仍匹配调用时指纹 |
| TokHub | L1/L2/L3 探测 | 区分网络、鉴权、模型和生成故障 | probe services/`probe_runs` | channel → layer results | 凭证、网络 | Apache-2.0 | Gateway 已区分网络、鉴权/模型和真实生成状态；千问、豆包、Kimi、DeepSeek 完成同一 blind cohort 的 3× API L3，12/12 均有真实 request id | Consumer Web/App L3 仍为 0/4；周期性持久 probe 与生产凭证轮换仍缺 | absorb | Provider Health | P0 | partial | API 四平台各 3 次独立 session、请求审计、原始响应和 v4 门禁通过；Consumer readiness 单独验收 |
| TokHub | 路由、降级和熔断 | 失败时保护队列和成本 | gateway routing/circuit state | request → chosen upstream | Redis/DB fallback | Apache-2.0 | 统一 Gateway 已有优先级多上游路由、路由级配置指纹、受控故障转移、重试/退避/半开恢复和跨进程 circuit；MySQL 保存无密钥 route manifest 与请求 route_id；分布式 QPS/并发租约已经接入；新增带 RBAC、reason、乐观锁和不可变事件的路由控制 API/设置页，Worker 每次调用热读取启停与优先级，且禁止停用最后一路 | 基于实时延迟/成功率的自动择优和长时负载压测仍缺 | adapt | Provider Gateway | P1 | partial | 主路由故障可切换备用；人工控制无需重启即可生效；过期版本、最后一路停用、密钥入参和伪造权限均被拒绝；真实 MySQL 控制/审计/统计查询通过 |
| TokHub | QPS、并发与配额预留 | 避免超额和预算并发穿透 | quota/reservation/store | request → reserve/commit/release | Redis/事务 | Apache-2.0 | MySQL tenant quota repository 按租户/UTC 日锁行预留；新增按 Provider + 配置指纹隔离的分布式 token bucket 与并发租约，跨 Worker 原子领取、幂等冲突、TTL 崩溃回收和成功后清理失败不重放均有测试；无数据库时保留进程内保护 | 租户成本预算、排队等待策略和长时压力测试仍缺 | adapt | Quota Service | P1 | partial | 真实 MySQL 并发竞争只能一个 Worker 获得容量；配额不超额、失败归还、过期恢复且已成功调用不得因清理失败重放 |
| TokHub | 用量 exact/estimated 标记 | 不把估算成本冒充精确成本 | usage events/rollups | response → tokens/cost/provenance | 价格版本 | Apache-2.0 | ProviderUsage 与 usage events 已区分 exact/estimated/unknown；四平台同轮 12 条真实 usage event 均为 exact；HTTP 成功但空回答的失败调用也保存已发生用量 | 价格版本、成本计算和报表筛选仍缺 | absorb | Usage Ledger | P1 | partial | 缺上游 usage 时标 estimated；失败调用有 exact usage 时仍入账；报告可过滤 |
| TokHub | 凭证加密、指纹、轮换 | 支撑安全私有 Provider | credential store/migrations | secret → ciphertext/fingerprint | 主密钥/KMS | Apache-2.0 | env 注入 | 无租户级 vault 与轮换审计 | adapt | Credential Vault | P1 | planned | 明文扫描为零；轮换不暴露旧值；删除执行 scrub |
| TokHub | reason + idempotency + audit | 让高风险操作可审计 | admin agent contracts/store | write → idempotent result/audit | RBAC | Apache-2.0 | 有 audit/outbox 表 | API 写操作未统一执行 | absorb | Operation Guard | P1 | planned | 重放同 key 不重复副作用，冲突 payload 被拒绝 |
| TokHub | 公开示例通道与固定健康分 | 让首页可演示 | seed/store example rows | seed → 静态通道分数 | 无 | Apache-2.0 | AIRank 有相似固定 overview | 会伪装真实健康 | reject | 无 | P0 | rejected | 生产构建与 seed 扫描不得出现静态健康/业务分数 |

## Skill OS 与外围仓库

| 来源仓库 | 能力名称 | 业务价值 | 代码位置 | 输入输出 | 依赖条件 | 许可证 | AIRank 当前能力 | 差距 | 吸收方式 | 目标模块 | 优先级 | 状态 | 验收方法 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yao-meta-skill | Skill IR 与 target compiler | 统一内部 Skill 契约和版本 | `export_skill_ir.py`、compiler scripts | Skill 包 → IR/target artifacts | schema、registry | MIT | 核心 10 Skill 已有 manifest/schema/entrypoint | 尚无 target compiler 和升级迁移 | adapt | `packages/skills` | P0 | partial | 核心 10 Skill 均能序列化、校验和升级 |
| yao-meta-skill | Trigger/输出/盲测 eval | 防止 Skill 只有 Prompt 没能力 | `evals/`、output eval scripts | cases → score/evidence | fixtures/provider runner | MIT | 10 个 Skill 已执行 30 个 contract/holdout/adversarial 用例并通过 schema 与 rubric | 真实 Provider 和人工标注 benchmark 仍未绑定 | absorb | Skill Eval Lab | P0 | partial | `scripts/evaluate_core_skills.py` 必须 30/30；真实证据缺失时不晋级 |
| yao-meta-skill | promotion 与 claim guard | 防止 partial 被宣传为 ready | promotion/claim guard scripts | evidence → promote/block | evidence ledger | MIT | 已生成绑定 registry/eval/实现 hash 的 promotion ledger；10 个 Skill 均因外部证据缺失保留 partial | 尚需逐项提交可校验的真实 Provider/人工 benchmark artifact | adapt | Skill Registry | P0 | partial | artifact 路径与 SHA-256 校验通过才解除 blocker；伪造 header 无法访问管理员 API |
| yao-meta-skill | trust/permission/package gate | 控制网络、凭证和可移植性 | trust/package/install scripts | Skill 包 → trust/report/package | sandbox/manifest | MIT | 无 | 无依赖与权限声明验证 | adapt | Skill Trust Gate | P1 | planned | 依赖、网络、secret、权限、安装模拟全部可审计 |
| yao-open-tools | `tokscr` 本地网页截图 | 保存消费者页面与来源面板证据 | `tools/tokscr` | 页面 → PNG/PDF | 浏览器扩展 | MIT | Playwright 截图会先复制到内容寻址 filesystem/S3/MinIO，并以鉴权 API 读取和复验 hash | viewport、区域与来源面板裁剪元数据仍未完整保存 | reference_only | Evidence Capture | P1 | partial | 截图对象真实 MinIO 往返与租户隔离通过；继续补 viewport/区域/裁剪契约 |
| yao-open-tools | TokKit exact/partial/estimated | 明确成本数据精度 | `tools/tokkit` | 日志/响应 → 用量台账 | 本地日志 | MIT | 无精度枚举 | 容易把估算当真实 | absorb | Usage provenance enum | P1 | planned | 任一成本字段都有 precision 和 source |
| yao-open-tools | TokDoc 报告与版本快照 | 客户报告归档与公开交付 | `tools/TokDoc` | HTML/PDF/Word → 版本/链接 | 本地存储 | MIT | 已有内容寻址 JSON 客户证据包、对象 hash、本地下载校验和 packet 级回执；v3 增加不含原始回答/人工说明正文的事实声明、来源治理与证据 hash 索引，历史 v1/v2 可读取；缺失但可由相同 canonical bytes 恢复的对象会按原 hash 恢复并审计 | HTML/PDF/Word 渲染、签名和公开验证工具仍缺 | reference_only | Report Artifact Store | P2 | partial | 真实 MySQL 报告生成证据包并重算事实覆盖/准确率与来源治理；下载前复验 SHA-256，回执绑定 packet/hash；缺失对象恢复和篡改阻断均有自动化测试 |
| yao-open-skills | 证据分级、版权、安全和决策 Skill | 补充治理 rubric | `skills/yao-*` | 任务 → 多格式报告 | 各 Skill 依赖 | MIT | 无统一 rubric | 与 GEO 主线部分重叠 | reference_only | Governance rubrics | P2 | planned | 只抽取 rubric/失败案例，不注册无关客户 Skill |
| yao-open-prompts | GEO/企业研究 Prompt 库 | 提供候选问题和写作方法 | `prompts/08-ai-marketing` | 输入 → 文本建议 | LLM | CC-BY-4.0 | 有零散生成逻辑 | Prompt 本身无真实证据 | reference_only | Eval/Prompt candidates | P2 | planned | 进入产品前必须转成 schema、事实政策和 eval case |
| TokEMS | 不可变版本、Outbox、RBAC、审计 | 提升发布与交付可靠性 | templates/publishing/common modules | 写操作 → snapshot/event/audit | DB/worker | AGPL-3.0 | AIRank 自有实现已有内容审核、不可变发布快照、幂等包和复测证据索引 | RBAC、outbox 消费和故障恢复仍缺 | reference_only | Delivery architecture | P1 | partial | 只参考模式；AIRank 自有实现通过幂等和恢复测试 |
| TokEMS | 大会报名/支付/签到业务 | 与 GEO 无关 | event/order/payment/check-in modules | 活动数据 → 交易/核销 | 支付、短信、设备 | AGPL-3.0 | 无 | 不属于 GEO 付费闭环 | reject | 无 | P3 | rejected | 不进入领域模型和导航 |
| haidian | 来源候选草稿与用途边界 | 自动发现不能直接升级为企业事实，先区分待复核、临时和批准来源 | `docs/data-workflow.md`、`data/source_registry.schema.json` | 候选 URL/资料 → source registry draft → 人工决策 | 来源权利、权威度、时效与用途审核 | NOASSERTION；仅参考方法 | KnowledgeSource 已有 hash、权威度、风险、版本、有效期和人工审核 | 自动发现候选、formal/background/prohibited 用途边界与清权队列仍缺 | reference_only | Knowledge Source Intake | P1 | partial | 自动发现记录只能进入 `needs_review`；审核前不得生成 FactAtom；所有用途限制可下钻且过期会撤销资格 |
| haidian | 确定性门禁与 AI 咨询评审分离 | 避免模型评分覆盖格式、证据和合规硬门禁 | `docs/review-rubric.md`、`scripts/ai_review_submission.py` | 本地 gate/证据包 → advisory review → 人工决定 | 版本化 rubric、审核角色 | NOASSERTION；仅参考方法 | 测量/内容/Skill 门禁均为确定性判断；AI 派生标签不覆盖原证据；引用与事实已实现盲态双人复核、分歧裁决和 benchmark kappa 门禁 | 客户人工标注集、rubric 版本对象和抽检运营仍缺 | reference_only | Governance Review Gate | P1 | partial | 任何 AI 评审不能把 blocked 改成 ready；单人审核、benchmark 与未终结分歧不能进入客户指标 |
| haidian | 离线评审包与空白评分表 | 把风险、假设、来源、指标、文件和正文放入一个可归档交付包 | `docs/review-packets.md`、`scripts/export_review_packet.py`、`scripts/generate_formal_scorecard.py` | 已通过门禁的产物 → manifest/HTML/PDF/评分材料 | 不可变 artifact、导出引擎、人工评审 | NOASSERTION；仅参考方法 | AIRank 自有 `airank.report-evidence-packet.v7` 以确定性 ZIP 交付 canonical manifest、可打印 HTML、空白评分表、README 与 SHA256SUMS；离线 CLI 从 source_record 重建全部指标/index/包内容，并要求 API/回执整包 hash 外部锚定。质量、v2 巡检、风险、假设、公式、限制、最终 production 双人审核、来源治理与对象索引继续完整保留；历史 v1–v6 只读兼容 | PDF/Word、数字签名和独立公开托管验证页仍缺 | reference_only | Customer Evidence Packet | P1 | partial | 质量、源证据或派生状态阻断/旧报告/缺样本均禁止生成；ZIP 逐文件与整包 hash、deterministic rebuild、篡改失败、真实 MySQL 和浏览器下载必须同时通过 |
| yaojingang.github.io | 个人博客内容 | 无核心产品能力 | repository content | 内容 → 静态站 | 无 | NOASSERTION | 无 | 许可和业务价值不足 | reject | 无 | P3 | rejected | 不克隆、不吸收 |
| yaojingang | 个人 Profile README | 无产品能力 | profile README | 文本 → 主页 | 无 | NOASSERTION | 无 | 与产品无关 | reject | 无 | P3 | rejected | 不克隆、不吸收 |

## AIRank 内部现有原型的处理

`/Users/bruce/Developer/work/ai-geo-monitoring` 中已经完成 Provider 成本、验证、任务进度、失败重试、知识导入、通知和付费试点门禁。它属于 AIRank 的本地实验实现，不作为外部开源项目直接复制；只把通过测试的契约和行为迁移到本仓的 Python/FastAPI 领域模型，并重新跑本仓单元、迁移、Provider 和浏览器门禁。

## 当前核心 10 Skill

1. `measurement.sample-runner`
2. `measurement.answer-parser`
3. `measurement.citation-extractor`
4. `research.intent-miner`
5. `knowledge.fact-builder`
6. `governance.claim-verifier`
7. `intervention.page-blueprint`
8. `intervention.explainer-builder`
9. `intervention.comparison-builder`
10. `delivery.retest-report`

核心 10 Skill 已完成统一 manifest、输入输出 schema、证据等级、事实政策、失败政策、rubric、entrypoint，以及独立 contract/holdout/adversarial 评测。30/30 用例通过，Promotion Evidence Ledger 绑定 registry、评测语料、实现和评测引擎 hash；因真实 Provider/人工标注 benchmark 尚未逐项绑定，全部继续保持 `partial`。内部 Skill 控制台明确展示本地通过数、可晋级数和每项缺证 blocker。

## 阶段一完成判定

- 13 个公开仓库都有明确取舍，11 个相关仓库锁定 commit 并完成代码级入口定位。
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
- `airank.measurement-quality.v4` 将复测报告的“已生成”与“可交付”分开：每个 ScanRun 都能重算内容寻址质量报告，未提及仍计入有效分母；单次采样、少于 3 个独立 sample index、重用 session 或未验证全新 Consumer 会话会直接阻断交付。除样本、签名、有效率、回答/原始响应 hash 外，API/Web/App/manual_import 分别执行证据门禁。Web/App 的 `source_panel_status` 必须为 `captured` 或 `not_present`；有引用时还必须绑定不可变来源面板对象。基线与复测任一质量失败或口径不可比时，报告只保存为 `quality_blocked` 且下载 API 返回 `409 REPORT_QUALITY_BLOCKED`。
- 真实 ScanRun 默认由 `airank_async_jobs` 与 Worker 异步执行；每个采样槽独立领取、心跳并在单事务中写回答、证据、引用、请求审计、attempt 和 job/task 状态。同批次不同槽可由多个 Worker 并行；运行指标只在全部槽终态后从持久化样本重算。进程崩溃只把结果未知的当前槽记为 `SCAN_TASK_LEASE_EXPIRED` 与 `unknown` attempt，不重放 Provider，也不破坏兄弟槽证据。证据中心可下钻 attempt 链。跨进程 MySQL 熔断、租户配额、按配置指纹隔离的分布式 QPS/并发租约和优先级多上游故障转移已经接入；动态择优和长时压测仍未完成，因此 TokHub 路由能力仍为 `partial`。
- Worker 与 Scheduler 现在都使用 fail-closed scope：默认必须指定 tenant/project/exact job 或 window；全局运行需要命令行 `--allow-global-scope` 和独立环境开关同时启用。`--dry-run` 在初始化 Provider/Publisher 之前只读统计可领取对象，`--drain --max-jobs` 支持有限批量消费。真实库只读预览确认当前全局存在 71 个到期 `scan.provider` job，但未领取或调用任何 Provider，避免误处理其他租户历史队列。
- 持久复测 Scheduler 已把 T0 作为不可变基线锚点，把 T+7/T+14/T+30 窗口转为新的 durable ScanRun/task/job。复测执行优先使用基线 `request_json.question_text`，不会因买家问题后续编辑而改变测量口径；缺基线、缺任务或缺冻结 Prompt 时窗口进入 `blocked` 并保存结构化错误与追加审计。真实 MySQL 验证 fresh session、幂等派发、终态失败比较生成 `quality_blocked` 观察报告以及 `completed_with_limitations` 窗口。
- Source Registry 只聚合 Citation 表里实际存在的精确 host，不按父域或品牌名自动猜测。`20260808_0020` 在真实 MySQL 建立追加式分类修订表；`20260808_0021` 允许同一报告按治理状态保存多个不可变 v3 包版本。v3 包精确绑定 citation/snapshot/host/current revision hash，分类缺失、过期、未知权威、禁止用途和 host 无法解析均成为限制项。真实浏览器导出 6 样本/6 引用包时显示 1/2 来源有效并禁止整体权威性结论；缺失对象按相同 canonical bytes 和原 SHA-256 恢复且记录审计，篡改对象继续失败关闭。桌面与 390px 均无页面级横向溢出且 console 为 0 warning / 0 error；55 行隔离 QA 数据随后精确清理为 0。
- 知识治理新增项目级开放冲突查询和 1—365 天有效期观察窗：来源到期、已批准事实到期与开放冲突均从原始对象实时派生，不自动改写状态；来源过期、尚未生效或冲突开放时，FactRevision 即时失去内容生成资格。真实 MySQL 已验证冲突创建、资格阻断、人工裁决、资格恢复、UTC 序列化和重复修订对 `409` 门禁。
- 页面干预不再把请求标题或编辑方向直接拼成营销文案：`intervention.page-blueprint@1.1.0` 只编排已审核事实和精确来源边界，公开标题由已审核事实元数据确定性生成，并返回 sections、claim bindings、结构化数据、正文与内容寻址蓝图 hash。比较页不能走通用模板；`intervention.comparison-builder@1.0.0` 用不可变主体绑定和 2×10 对称证据矩阵生成 20 条 ClaimSupport，`intervention.explainer-builder@1.0.0` 用七类角色、12 条事实、1400 个证据字符和品牌露出上限生成 7 段解释。三类内容均已在真实 MySQL 通过审核并生成 `airank.publish-snapshot.v2` 导出快照。
- 发布中心不再是只读看板：客户可从当前已批准的内容资产创建 export/WordPress/HTTP 发布包；外部站点凭证只允许 Worker 进程安全注入。publication evidence 只接受真实 URL、`completed + baseline` 的 T0 和成对截图对象引用/SHA-256；MySQL 会复核截图属于当前租户/项目且 hash 一致后，才把包标记为 published 并创建 T0/T+7/T+14/T+30。隔离浏览器已真实完成创建和登记，桌面/移动无页面级溢出或 console error；客户站点外部回执、更新与撤回仍保持 `partial`。
- 千问、豆包、Kimi、DeepSeek（当前可用型号为 `deepseek-v3.2`）已在同一 blind cohort/API 采集面各完成 3 次独立 L3，12/12 均返回真实 request ID、不可变原始响应、请求审计、成功 attempt 和 exact usage。Kimi K3 使用官方 `max_completion_tokens`、省略固定 temperature 并设置低 reasoning effort；公开请求默认值由 `20260808_0022` 版本化保存。凭证只从本机私密环境映射到进程，已暴露过的 Kimi 验收密钥必须在生产前轮换，DeepSeek 新型号额度和旧型号下架迁移仍是上线门禁。
- 页面安全抓取切片已通过 38 项定向测试和真实 MySQL integration；真实浏览器完成 `example.com` 异步抓取，得到 HTTP 200、内容 SHA-256、DNS 固定连接 IP、11 条规则和 68 分技术可提取性。桌面与 390×844 移动端均无页面级横向溢出，console 为 0 warning / 0 error。该分数只表示服务器页面可提取条件，不能推导品牌推荐率。
- 引用支持度切片把 Provider 原生 citation 作为 selection 事实保存，把回答 Claim 与来源复核作为独立 append-only 证据。全量测试 `295 passed, 19 skipped`，真实 MySQL `17 passed, 2 skipped`；浏览器下钻显示 1 个已选择来源、1 条回答断言、1 个 provisional 复核，但因没有不可变来源页面快照，客户报告支持率保持“待核验”。桌面/390px 无 console warning/error，临时验收数据已清理。
- 前端 TypeScript/Vite 构建通过；本机 Node `20.18.2` 低于 Vite 建议的 `20.19+`，当前是环境告警而非构建失败，生产构建镜像需升级。
- 控制台静态业务结果已删除，11 个路由改用真实 API 或显式 `partial/blocked/disabled` 状态；桌面与 390px 空项目浏览器验收通过。该证据不替代带真实项目数据的全链路 E2E。
- 当前阶段仍是 `partial`：四平台同一版本问题的 API 重复采样已经通过，但消费端 Web/App 证据、生产凭证轮换、外部 Publisher 和从建档到客户报告的带数据 E2E 尚未全部通过，因此不允许声明商业可用。

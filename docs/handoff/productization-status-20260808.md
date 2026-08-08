# AIRank 产品化持续交付状态（2026-08-08）

## 当前结论

状态：`partial / no-go for commercial launch`。

已经完成“吸收矩阵”“测量可信度第一切片”“内部 Skill Registry”“事实证据链”“审核后发布快照”“同口径复测归因”后端切片，以及 API 认证边界、样本证据中心、任务中心、事实/内容审核 UI、真实 Provider 采样、统一安全出站和官网可提取性审计；但同一轮四平台真实重复采样、生产 Yudao 认证、浏览器/App 高等级证据、真实外部发布和带项目数据的浏览器客户报告尚未全部通过，不得宣称商业可用。

## 本轮已落地

1. 锁定 `yaojingang` 账号下 12 个公开仓库，10 个相关仓库固定 commit/许可证/取舍，64 项能力进入吸收矩阵，21 个 GEO Skill 全覆盖。
2. 新建四类 Prompt Cohort：`blind`、`assisted`、`comparison`、`fact_verification`。
3. 默认每个问题执行 3 次独立样本，任务记录 Prompt 版本、sample index、session、surface 与 evidence level。
4. 正常未提及品牌的回答保留为有效样本并进入分母；失败和阻塞单独统计。
5. 删除固定解析置信度和文本出现顺序排名；加入品牌、别名、公司名、产品名实体识别。
6. AnswerSnapshot 支持无引用有效回答；原始响应、回答、截图使用 SHA-256，浏览器截图按内容寻址。
7. Citation 只保存回答区可见且能与回答文本关联的真实外部链接；不再创建“Provider 原始回答”伪引用。
8. 增加可重算指标：有效样本率、提及率、明确推荐率、Top1/3/5、条件 Top3、稳定性、引用召回、引用支持和事实准确率占位状态。
9. 无真实证据时，Console/资产包/报告返回明确空状态；不生成演示数字、完成度、报告、事实或发布包。
10. 新增 Alembic 迁移并在临时 MySQL 空库真实执行通过；临时库验收后已删除。
11. 建立 `packages/skills` 内部 Skill Registry；首批 8 个 Skill 均包含版本、分类、输入输出 schema、依赖、Provider 要求、证据等级、事实/失败政策、rubric、eval case、状态和可执行 entrypoint。
12. 新增内部 Admin Skill API，可查看 manifest 并执行版本化 eval；8 个 Skill 当前全部为 `partial`，不会被前端或销售口径宣称为 ready。
13. 建立 KnowledgeSource、FactRevision、FactConflict、ClaimAssertion、ClaimSupport 和不可变 EvidenceSnapshot；事实必须有来源、有效期和人工审核后才能支持内容 Claim，开放冲突会阻断核验。
14. 新增事实治理 Alembic 迁移并在临时 MySQL 空库真实执行；验证 29 张 AIRank 表、5 张新治理表与 3 个 FactAtom 版本字段后删除临时库。
15. 建立 AIRank Python Provider Gateway：四平台 manifest、官方 host allowlist、模型生命周期、L1/L2/L3、重试/退避、熔断、QPS/并发、配额预留、request ID、原生引用和 usage precision。
16. API surface 已接 ScanRun；Provider 原始 JSON、请求元数据、模型、联网状态、request ID、usage 和配置指纹进入不可变证据与独立审计表，不与 Web/App 证据混用。
17. 千问、豆包、Kimi、DeepSeek（当前验收型号 `deepseek-v3.2`）已从本机私密环境通过本仓 Gateway 完成真实生成，均有真实 request ID；凭证未进入源码、Git 或文档。已在会话暴露过的 Kimi 密钥生产前必须轮换，DeepSeek 型号迁移仍需额度与下架门禁。
18. 知识导入按 source/content hash 幂等，保存不可变原文和精确字符边界切片；事实版本、冲突、有效期和人工审核均进入正式 API。
19. 内容资产只能引用已审核、未过期、无开放冲突且允许公开的 FactRevision；每条 ClaimAssertion 都绑定 ClaimSupport 和原文边界。
20. 内容审核绑定内容 hash，执行事实覆盖和风险扫描；高风险 GEO 保证、绝对排名或竞品贬损必须记录人工 override，未经审核不能生成发布包。
21. export 发布包已有不可变快照、租户级幂等键和发布 URL 证据；WordPress/HTTP 仍只标记 `partial` 并入队，不冒充已发布。
22. 发布必须绑定已完成的 T0 基线，并自动建立 T0/T+7/T+14/T+30 窗口；复测从原始任务和回答样本重算，严格校验问题、Provider、Cohort、surface、Prompt、模型与联网上下文，只输出观察性、非因果的低/中置信度报告。
23. 删除控制台 `data.ts` 中全部静态业务结果；工作台、体检、事实库、问题地图、缺口、内容资产、发布、报告和设置改为读取真实 API，未实现的 AI 来客助手明确标记 `disabled`。
24. 新增买家问题和发布包列表 API，空项目时前端不再请求伪造的 `project_demo`，不产生隐藏 404；新增静态结果回归门禁。
25. 在本地 dev-only 身份边界内完成 11 个控制台路由桌面与 390px 移动端浏览器验收：标题与显式空态正确、无横向页面溢出、无浏览器 console warning/error；该结果只证明空态和前端契约，不替代真实客户项目 E2E。
26. Provider Gateway 在配置 MySQL 时启用跨进程 circuit/quota/probe store：熔断按 Provider + 配置指纹隔离，配额按租户和 UTC 日锁行预留，任务幂等键阻止重复并发调用，过期预留可恢复；Manifest 与 L1/L2/L3 probe 只保存公开配置和单向指纹。
27. 新增受治理的 HTTP/WordPress Publisher worker：只读取审核后不可变快照，要求显式 HTTPS 主机白名单和公网 DNS，拒绝重定向/私网目标，凭证只从进程环境注入；每次执行保存 request/response SHA-256、状态码和结构化错误，支持显式重试恢复。
28. 外部调用成功仅把发布包置为 `delivered`，不会自动制造 `published` 或复测结论；仍须通过 publication-evidence API 绑定真实 URL、可选截图和已完成 T0 基线后，才创建 T0/T+7/T+14/T+30 窗口。
29. API 认证默认改为强制：除登录、健康、版本和 OpenAPI 文档外，所有 `/api/v1` 请求必须携带有效 Bearer token 和匹配租户；`dev_only` 仅接受本进程实际签发且未过期的 token，Yudao 模式会用真实 permission-info 重新鉴权并覆盖客户端伪造的用户/租户身份头。
30. 上线门禁新增认证配置检查：生产环境必须同时满足 `AIRANK_API_AUTH_ENFORCEMENT=required` 与 `AIRANK_AUTH_MODE=yudao`；测试环境的认证关闭被限制在显式 fixture 中，不改变生产默认值。
31. 新增样本证据中心：项目内真实 AnswerSnapshot 由服务端按 ScanRun 隔离并对完整批次聚合统计，可下钻原始回答、回答/原始响应 SHA-256、请求元数据、EvidenceSnapshot、session、证据等级、联网状态、Provider request ID、真实引用、截图和来源面板引用；表格截断不会改写批次总数，API 采集没有截图或引用时明确显示缺失，不生成替代证据。
32. 新增任务中心：可选择真实 ScanRun，查看每个 Provider/Cohort/sample/session 的任务状态、采集面、证据等级、错误与完成时间；失败、阻塞和未提及不再从结果中隐藏。
33. 事实与内容资产页面已接真实审核写 API；服务端在强制认证模式覆盖事实/内容创建人、审核人、冲突解决人、发布申请人、发布证据登记人和复测完成人等客户端身份字段，统一使用认证上下文，避免冒充审计主体。
34. 修正 Provider API 采样的指标口径：不再描述为“消费端网页”，聚合结果显式记录 `collector_surface_counts` 和 `evidence_level_counts`；API、Web、App 仍保持独立证据等级。
35. 豆包 Responses API 在账号未开通联网工具、返回 `ToolNotOpen` 时，会在同一次受审计任务中退回无工具生成，并把证据降级为 `provider_api_search_not_used`；不会伪造联网、引用或截图。
36. 浏览器完成一次真实品牌检测：同一 ScanRun 建立 12 个任务，DeepSeek、豆包、千问各 3 次独立采样成功，Kimi 3 次因未安全注入凭证而明确失败；9 条有效回答均正常未提及品牌并完整计入分母。任务中心显示 `12 total / 9 completed / 3 failed`，证据中心显示 9 条有效未提及样本和 0 条真实引用。
37. Web 新增“证据中心”和“任务中心”路由；失效 session 遇到 401 会清理本地认证并返回登录页，控制台提供显式退出登录，不再继续携带无效凭证请求业务 API。
38. 浏览器截图不再把临时 `file://` 路径当成长期证据：新增内容寻址的 filesystem/S3/MinIO ObjectStorage，写入后校验 SHA-256 与大小，数据库只保存不可变 URI、对象键、驱动和 hash；存储失败会使对应采样任务明确失败，不进入有效样本。
39. 证据对象新增租户隔离的鉴权读取 API；每次读取重新校验 SHA-256 与字节数，控制台通过带 Bearer token 的 Blob 请求展示截图，底层存储错误只返回受控错误码。真实 MinIO 已完成写入、逐字节读取和删除探测，临时对象与测试桶均已清理。
40. 上线门禁新增生产对象存储和运行时检查：`AIRANK_ENV=production` 必须使用 S3/MinIO 与 TLS，禁止 `AIRANK_S3_ALLOW_HTTP=true`；Python 必须为 3.11+，Node 必须满足 20.19+ 或 22.12+。CI 已切换 Python 3.11，部署样例已移除会覆盖生产配置的重复 `local` 设置。
41. 核心 8 Skill 新增独立评测语料：每项均执行 contract、holdout、adversarial 三套用例，共 24/24 通过；评测同时修复空事实仍生成页面、否定事实子串误支持、无关“第一名”误绑定品牌和非法复测比例四类可信度缺陷。
42. 新增内容寻址的 Promotion Evidence Ledger，绑定 registry、评测语料、核心实现、评测引擎和证据清单 SHA-256。当前 8 项本地评测全部通过，但因真实队列、人工标注 benchmark、Provider 引用 benchmark 等外部证据未逐项绑定，可晋级数仍为 0，全部诚实保留 `partial`。
43. 新增内部 Skill 控制台，真实展示 Skill 版本、3/3 评测、套件、晋级 blocker 与 ledger hash；管理员 API 要求 Yudao `airank:skill:admin` 权限，认证中间件覆盖客户端伪造 permission header。浏览器桌面和 390px 移动验收通过，移动宽表仅在自身容器滚动，无页面级溢出或 console error。
44. 新增项目级知识治理 API：开放冲突可按状态查询，1—365 天观察窗实时派生来源过期、来源即将到期、已批准事实过期、已批准事实即将到期与开放冲突；告警不会自动修改原始来源、事实或冲突状态。
45. FactRevision 生成资格改为读取时动态计算：来源未生效、已过期、非 active 或冲突开放时即时撤销资格，人工裁决后可恢复；MySQL 时间统一按 UTC 序列化，避免来源列表与治理提醒出现 8 小时偏差。同一无序修订对重复登记冲突会返回带原冲突状态的 `409`，不再泄漏数据库唯一键异常。
46. 企业事实库接入真实治理摘要与冲突列表，展示到期时间、开放冲突、左右修订、裁决选项和必填依据；服务端仍覆盖客户端裁决人。真实 MySQL + 浏览器完成“4 项待治理 → 空说明阻断 → 人工保留左版本 → 开放冲突归零 → 原批准事实恢复可用于内容”的闭环。桌面 1024px 无页面/裁决区横向溢出和 console warning/error；浏览器截图发现并修正了事实卡三列导致中文逐字竖排的问题，改为最小 280px 自适应列。
47. 知识来源支持不可变新版本：更新操作创建独立快照和切片、原来源置为 `stale`，依赖旧来源的已批准事实即时变为 `source_stale`。新增当前有效原文检索 API/UI，只返回 active 且在有效期内的切片，展示精确边界、segment hash、命中词和来源版本；能力明确标为 `lexical_only / vector not_configured`，不冒充混合检索。
48. `research.intent-miner` 升级至 `1.1.0`：买家问题统一进入版本化 taxonomy，记录问题类型、意图、买家阶段、Prompt 风格、时效、业务场景、Cohort、来源和稳定版本；中文/英文、Unicode、空白及标点归一后去重。
49. 新增不可变 `QuestionMap`、`BuyerQuestionRevision` 和追加式 `BuyerQuestionReview`。编译预览不落库；持久化按输入与 taxonomy 内容寻址并支持幂等回放；所有模板只能标记为 `template_candidate`，不会伪造真实查询量或 `observed_query`。
50. 人工确认成为采样硬门禁：新编译问题统一为 `suggested`，审核说明必填且审核主体来自认证上下文；ScanRun 只接收 `confirmed` 且问题修订 Cohort 与运行 Cohort 完全一致的条目，竞品命名问题不会泄漏进 blind 测试。
51. 问题治理迁移 `20260808_0009` 在真实 MySQL 完成，AIRank 表数增至 45；迁移针对 MySQL 非事务 DDL 增加列、索引、外键存在性检查，已验证第一次中断后的安全重跑，不用人工删除半成品结构。
52. 买家问题地图控制台接入真实编译、列表和审核 API，展示版本、来源、Cohort、意图、阶段、观察状态和审核门禁。真实 MySQL 浏览器验收完成 12 个候选编译、1 个规范化重复拦截、人工确认、正确 blind 任务入队及错误 comparison Cohort 返回 404；1543px 与 390px 均无页面级横向溢出，fresh console 为 `0 error / 0 warning`。
53. `research.intent-miner` 升级至 `1.2.0`，新增 `ObservedQuestionSeed` 与 `provenance_records`。观察记录优先于种子和模板参与去重，重复来源会追加 provenance，不会把同一问题伪造为多个独立需求。
54. 新增 M1 客户授权问题观察批次与记录：来源类型、名称、访问方式、证据等级、日期范围、payload SHA-256、记录数、来源内频次、授权声明和导入人均不可变保存；重复 payload 幂等回放同一批次。
55. 导入门禁会拦截邮箱、中国手机号和身份证号；被拦截原文不写入数据库或响应，只保留不可逆内容 hash 与原因。`occurrence_count` 只表示该来源内出现次数，API 和控制台明确标注“不是搜索量”“客户提供、未独立核验”。
56. Alembic `20260808_0011` 在真实 MySQL 完成，AIRank 表数增至 48；新增不可变扫描 attempt 台账。真实浏览器完成授权导入、1 条安全记录/频次 7、1 条 PII 阻断、观察问题编译、人工确认和刷新持久化；390px 有效视口无页面级横向溢出，控制台 `0 error / 0 warning`，页面与持久化层均未出现被拦截邮箱。
57. 新增内容寻址的 `airank.measurement-quality.v1`：按 ScanRun 重算 10 项基础质量检查，覆盖样本存在、签名数量、样本 ID、采样位重复、状态分区、有效样本、有效率、回答 hash、原始响应 hash 和提及分类；结果包含 data/report SHA-256 与 known limitations。
58. 质量门明确保留正常未提及样本并计入有效分母；没有 Provider 引用、未评测引用支持度/事实准确率或缺少重复稳定性会进入限制项，不会被偷偷补值。
59. 复测报告只有在基线/复测各自 `publishable=true` 且样本契约可比时才写为 `generated`；否则写为 `quality_blocked/completed_with_limitations`。下载接口对阻断及旧版无质量清单报告返回 `409 REPORT_QUALITY_BLOCKED`，不再把文件存在等同于可交付。
60. 报表中心真实展示质量阻断说明并禁用下载。真实 MySQL 验证 12 个任务仅 1 个有效时质量报告阻断有效率和缺失原始失败快照；浏览器 390px 有效视口显示禁用按钮、无页面级横向溢出，console `0 error / 0 warning`。
61. 质量契约升级为 `airank.measurement-quality.v2`：每个任务样本独立绑定 Evidence Manifest，总计 21 项检查。API 必须关联 Provider 请求审计；Web/App 必须有不可变截图并明确来源面板为 `captured/not_present`；有引用时必须保存来源面板对象；App 额外要求设备/App 环境 hash；manual_import 要求导入源 hash。各采集面独立输出样本数、有效数、证据完整数、截图数、来源面板状态和阻断数。历史 v1/无版本报告在列表中降级为 `quality_blocked`，下载回执接口拒绝放行，必须按 v2 重算。
62. 浏览器真实 MySQL 验收使用一条有效且未提及的豆包 Web 样本：有效率为 100%、未提及正确计入分母、来源面板明确记录为“界面未呈现（已检查）”，但因截图对象缺失，质量报告仍为 `blocked`。证据中心展示具体阻断和 `web/consumer_web` 汇总；390px 有效视口无页面级溢出，console `0 error / 0 warning`。
63. 扫描失败和阻塞不再只写任务错误：每个失败槽位创建空回答 AnswerSnapshot、不可变原始失败 EvidenceSnapshot、请求元数据和原始响应 SHA-256；Web 采集如已进入页面则把失败现场截图复制到内容寻址对象存储。登录/验证码/配额/鉴权等外部动作阻塞与超时、网络、上游、解析失败严格分开；两者都不计入品牌未提及分母。真实同批次验收完成“千问 API 有效未提及 + 千问 Web 超时失败”，失败样本可下钻到原始 hash 和截图对象，质量门禁的原始响应 hash 检查通过。
64. 品牌检测在 MySQL 路径默认只创建真实任务并入队，API 不再同步占用请求线程执行整批 Provider 调用；只有显式 `AIRANK_SCAN_DISPATCH_MODE=inline` 可用于诊断。Worker 已改为每个采样槽独立领取、心跳和原子落证据，同批次不同槽可并行；运行指标只在全部槽终态后从持久化样本重算。`airank_scan_task_attempts` 记录 job、attempt、Worker lease、回答/证据 ID、请求 ID、时间和错误。崩溃只把结果未知的当前槽写为 `SCAN_TASK_LEASE_EXPIRED`/`unknown`，不会重放 Provider 或抹掉兄弟槽证据；证据中心可下钻 attempt 链。任务中心每 3 秒、批次列表每 5 秒刷新，不再把入队写成“检测完成”。
65. 真实千问 Worker 浏览器验收发现“单次采样却显示可交付”的门禁假阳性；质量契约因此升级为 `airank.measurement-quality.v3`。每个问题/Provider/Cohort/采集面/模型口径必须至少有 3 个不同 sample index 与 3 个独立 session；单次采样和会话复用必须 `quality_blocked`。已完成的真实千问样本仍保留为 valid/未提及原始证据，但前端正确显示“样本证据不可作为客户报告交付”，不会因 API 调用成功而越过重复性门禁。
66. 任务级 Worker 与 attempt 台账完成真实千问和浏览器复验：`qwen3.6-plus` 返回真实 request ID，attempt #1 记录 job、起止时间、`succeeded` 和回答/证据 ID；证据中心可下钻。390×844 无页面级横向溢出，新登录态页面 console `0 error / 0 warning`。单样本仍被 v3 质量门阻断。隔离验收租户已清理为 0 行。全量本地测试 `247 passed, 17 skipped`，真实 MySQL `15 passed, 2 skipped`。
67. 深入复核 `GEOFlow@1c1a361` 与 `GEORank@1df59ad` 的出站实现后，新增 AIRank 自有 `packages/outbound-security`。策略拒绝 URL 凭证、私网/保留地址、混合 DNS、IPv4-mapped/transition IPv6、未批准跳转、编码或超大响应；每次跳转重新解析并校验全部地址，实际 TCP 连接固定到已验证 IP，TLS SNI 与证书校验仍使用原始 hostname，跨 origin 自动剥离敏感 header。Publisher 与 Page Audit 已统一接入，不复制上游业务源码。
68. 新增 `airank.page-extractability.v1`：安全抓取并提取 title、description、canonical、robots、H1、服务器可见正文、main/article 和 JSON-LD，输出 11 条逐规则证据、整改建议和独立 `technical_extractability_score`。Alembic `20260808_0012` 新增不可变 audit run/finding 表；API 创建任务后由 Worker 异步落库，支持幂等冲突和失败闭合。控制台明确写明“技术可提取性分不等于品牌推荐率”，无数据时不生成假分。
69. 页面审计完成真实 MySQL 与浏览器 E2E：`https://example.com` 返回 HTTP 200、真实内容 hash、DNS 固定连接 IP、0 跳转、11 条发现和 68 技术分；桌面与 390×844 移动视口无页面级横向溢出，console `0 error / 0 warning`。
70. 吸收 `geo-citation-lab@81ba156` 的 selection/absorption 分层方法，新增不可变 Answer Claim 和追加式 Citation Support Review：Claim 保存回答字符边界与回答 hash；Review 保存支持/矛盾/不足、来源片段/hash、证据等级、人工/AI 辅助方式、reviewer、rationale 和 supersedes 链，AI 派生或后续复核都不覆盖旧证据。
71. 引用支持指标只读取每个 Claim/Citation 对的最新复核，并严格区分 selected citation count 与 support rate。`provider_excerpt_only`、`source_panel_capture` 永远只算 provisional；只有 `review_method=human + source_page_snapshot + 不可变对象 hash` 才进入可交付支持率。没有合格页面快照时支持率返回 `null/待核验`，不会用引用数量冒充支持度。
72. Alembic `20260808_0013` 在真实 MySQL 完成，AIRank 表数增至 52。API 支持登记断言、追加复核与读取独立指标；证据中心真实下钻显示“1 个来源已选择、1 条断言、1 个临时复核、0 个可交付复核、支持率待核验”。390px 页面布局正常、console `0 error / 0 warning`，隔离租户与临时 tenant_demo 记录均已清理。全量测试 `295 passed, 19 skipped`，真实 MySQL `17 passed, 2 skipped`。

## 验收证据

- `python3 scripts/verify_absorption_matrix.py`：`status=pass`，12 sources / 64 rows / 21 GEO skills。
- `.runtime/py312/bin/python -m pytest -q`：`295 passed, 19 skipped`；跳过项依赖未开启的真实外部服务，不计为通过。
- `python3 scripts/evaluate_core_skills.py`：8 Skill / 24 cases / 24 passed / 0 promotion eligible / 8 retained partial。
- `cd apps/web && npm run build`：通过；Node 小版本存在升级告警。
- `cd apps/web && npm audit --audit-level=high`：0 个已知 npm 漏洞。
- 浏览器：`/login -> /console` 登录通过；13 个控制台路由在 1491×1055 桌面和 390×844 移动端共 26 项检查全部通过，无横向溢出、认证丢失或显式接口失败。证据中心已下钻到一条真实豆包样本，原始回答、双 SHA-256、EvidenceSnapshot、session、证据等级和真实 request ID 均可见；任务中心显示最终 ScanRun 的 12 个任务及 Kimi 明确失败原因。
- 问题地图浏览器复验：升级 taxonomy 后使用同一输入重新编译，页面显示 `airank-question-taxonomy-v1.1.0`、12 个唯一问题、0 个新增候选、13 个重复拦截，证明新版本清单可回放且不会重复写问题。390×844 下页面宽度保持 390px，宽表只在卡片内部滚动，console `0 error / 0 warning`。
- 观察问题浏览器复验：隔离租户通过真实 API/MySQL 导入一个 M1 批次，保存 1 条安全记录、来源内频次 7，并阻断 1 条含邮箱记录；页面显示 `airank-question-taxonomy-v1.2.0`、`user_provided_snapshot` 和“客户提供观察记录（未独立核验）”。编译候选经人工确认后刷新仍存在；390px 有效视口的 html/body `scrollWidth` 均为 390，console `0 error / 0 warning`。
- 数据质量浏览器复验：真实 MySQL `quality_blocked` 报告显示“未通过数据质量门禁；不可作为客户交付物下载”，按钮禁用；直接调用下载 API 返回 `409 REPORT_QUALITY_BLOCKED`。390px 有效视口 html/body `scrollWidth` 均为 390，console `0 error / 0 warning`。
- 终端证据浏览器复验：真实 MySQL `airank.measurement-quality.v2` 返回唯一阻断 `consumer_screenshots_complete`，同时证明 `consumer_source_panels_inspected` 和无来源状态一致性通过。证据中心展示 Web 样本 1、有效 1、证据完整 0、截图 0、来源面板明确无 1、阻断 1；样本下钻可见原始回答、双 hash、外部会话 ID 与“界面未呈现（已检查）”。390px 有效视口无页面级横向溢出，console `0 error / 0 warning`；截图为 `/tmp/airank-surface-evidence-mobile.png`。
- 真实采样：最终同轮 12 个任务中 9 个成功、3 个失败；DeepSeek/豆包/千问各 3 次成功，9 条正常未提及全部计入分母；证据等级分布为 API 无联网、未使用联网和联网未验证各 3 条，不把 API 证据包装成 Web/App 证据。
- 持久 Worker 浏览器复验：隔离租户的一条千问 API 任务先显示 `queued`，Worker 执行后页面自动刷新为 `completed`；真实模型 `qwen3.6-plus`、Provider request ID、Answer/EvidenceSnapshot、回答/原始响应 hash 和成功请求审计全部关联。该回答正常未提及 AIRank，正确计入有效分母；v3 同时因只有 1 次独立采样阻断交付。桌面视觉验收图 `/tmp/airank-durable-worker-quality-blocked-top.png`，浏览器无 warning/error。
- MySQL：Alembic `20260808_0013`；52 张 AIRank 表校验通过；新增不可变回答断言与追加式引用支持复核，页面审计、观察来源 provenance、PII 阻断和扫描 attempt 继续通过。
- 本地真实 MySQL integration：`17 passed, 2 skipped`（Yudao 与独立 S3 开关按环境跳过）。新增引用 selection/support 分离、provisional 排除、来源页面对象门禁和 supersedes 历史断言；既有页面审计、问题治理、对象引用、Provider store、Publisher、扫描 attempt 与复测链仍通过。
- 来源版本浏览器验收：真实 MySQL 项目从 v1 更新到 v2，v1 保留为 `stale`、旧事实显示 `source_stale`；v2 独有原文返回精确边界与 hash，v1 独有词返回“当前有效来源无匹配”。1543px 桌面和 390×844 移动端均无页面级横向溢出，console `0 error / 0 warning`；同时修复底部使用指南按钮挤压正文导致中文逐字竖排的问题。
- 真实 MinIO integration：`1 passed`；S3 兼容层执行唯一对象写入、逐字节读取、HEAD 元数据核验和删除，探测对象为 0，临时测试桶已清理。该结果证明本地 MinIO 路径可用，不替代生产 HTTPS 对象存储验收。
- 完整上线门禁：分包测试、Web 构建、真实 MySQL、真实 MinIO 与 Alembic 均可通过；总状态仍为 `BLOCKED`，真实阻塞为 GitHub/Gitee `main` 未同步、生产 Yudao 未配置、生产 HTTPS S3/MinIO 未验收、消费端浏览器 Provider `0/4`，以及当前本机 Python 3.9 / Node 20.18.2 低于生产运行时门禁。

## 下一实施顺序

1. 轮换已在会话中暴露过的 Kimi 密钥，并使用同一版已确认问题在千问、豆包、Kimi、DeepSeek 上各执行至少 3 次独立采样；单次 L3 通路已验证，但完成同批次重复采样前四平台测量门禁保持 `partial`。
2. 接通真实 Yudao 登录与 permission-info，在生产配置下验证 token 撤销、跨租户、超时和并发请求；当前浏览器验收只证明 `dev_only` 认证边界。
3. 为 Web/App 采集器补真实截图、来源面板、联网状态与区域证据，并与 API 样本并行展示和分口径报告；当前 API 证据等级不足以证明消费端真实呈现。
4. 用统一安全出站客户端抓取真实引用页面，生成 `citation_source_page` 内容寻址对象和文本边界；再补人工标注队列与双人一致性 benchmark。selection/support 领域、API、MySQL 与只计合格页面快照的指标已经完成。
5. 将当前单机 QPS/并发限制扩展为 Redis/数据库分布式令牌桶，并补同能力多上游路由、长时崩溃恢复和负载压测；MySQL circuit/quota/probe 状态已接入。
6. 补客户来源自动同步 worker、局部重嵌入和混合检索；不可变人工来源修订、旧事实失效和当前有效原文检索已完成，但不能把 `lexical_only` 包装成语义检索。
7. 使用客户授权的 WordPress/HTTP 测试站点完成一次真实外部回执、截图、更新和撤回验收；适配器、attempt 消费与重试恢复已实现，但无外部账号时保持 `partial`。
8. 按 Promotion Evidence Ledger 的 blocker 清单补真实队列、人工标注、Provider 引用和真实 T0/T+7 artifact；每项必须提交仓库内可校验路径与 SHA-256 后才能晋级 `ready`。
9. 用四平台真实重复样本从新建品牌跑到客户报告，升级 Python/Node 运行时，在生产 HTTPS S3/MinIO 环境复验对象读写与截图展示，并完成带数据的浏览器 E2E 和完整上线门禁后，再合并到 `main`。

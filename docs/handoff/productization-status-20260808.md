# AIRank 产品化持续交付状态（2026-08-08）

## 当前结论

状态：`partial / no-go for commercial launch`。

已经完成“吸收矩阵”“测量可信度第一切片”“内部 Skill Registry”“事实证据链”“审核后发布快照”“同口径复测归因”后端切片，以及 API 认证边界、样本证据中心、任务中心、事实/内容审核 UI 和真实 Provider 采样；但同一轮四平台真实重复采样、生产 Yudao 认证、浏览器/App 高等级证据、真实外部发布和带项目数据的浏览器客户报告尚未全部通过，不得宣称商业可用。

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
17. 千问、豆包、DeepSeek 已从本机私密环境通过本仓 Gateway 完成真实生成；均返回非空回答、真实 request ID 和 exact usage。Kimi 仍需安全进程环境注入后重验。
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

## 验收证据

- `python3 scripts/verify_absorption_matrix.py`：`status=pass`，12 sources / 64 rows / 21 GEO skills。
- `python3 -m pytest -q`：`213 passed, 10 skipped`。
- `python3 scripts/evaluate_core_skills.py`：8 Skill / 24 cases / 24 passed / 0 promotion eligible / 8 retained partial。
- `cd apps/web && npm run build`：通过；Node 小版本存在升级告警。
- `cd apps/web && npm audit --audit-level=high`：0 个已知 npm 漏洞。
- 浏览器：`/login -> /console` 登录通过；13 个控制台路由在 1491×1055 桌面和 390×844 移动端共 26 项检查全部通过，无横向溢出、认证丢失或显式接口失败。证据中心已下钻到一条真实豆包样本，原始回答、双 SHA-256、EvidenceSnapshot、session、证据等级和真实 request ID 均可见；任务中心显示最终 ScanRun 的 12 个任务及 Kimi 明确失败原因。
- 真实采样：最终同轮 12 个任务中 9 个成功、3 个失败；DeepSeek/豆包/千问各 3 次成功，9 条正常未提及全部计入分母；证据等级分布为 API 无联网、未使用联网和联网未验证各 3 条，不把 API 证据包装成 Web/App 证据。
- MySQL 临时库：Alembic `20260808_0008`；42 张 AIRank 表校验通过；真实 MySQL 复测链路生成 1 个 RetestRun 和 1 个带 SHA-256/evidence index 的报告，临时库已删除。
- 本地真实 MySQL integration：`8 passed, 2 skipped`（Yudao 与独立 S3 开关按环境跳过）。新增对象引用→持久文件读取→SHA-256/大小复验→跨租户 404 的真实数据库链；既有 Provider store 与 Publisher 链仍全部通过。
- 真实 MinIO integration：`1 passed`；S3 兼容层执行唯一对象写入、逐字节读取、HEAD 元数据核验和删除，探测对象为 0，临时测试桶已清理。该结果证明本地 MinIO 路径可用，不替代生产 HTTPS 对象存储验收。
- 完整上线门禁：分包测试、Web 构建、真实 MySQL、真实 MinIO 与 Alembic 均可通过；总状态仍为 `BLOCKED`，真实阻塞为 GitHub/Gitee `main` 未同步、生产 Yudao 未配置、生产 HTTPS S3/MinIO 未验收、消费端浏览器 Provider `0/4`，以及当前本机 Python 3.9 / Node 20.18.2 低于生产运行时门禁。

## 下一实施顺序

1. 轮换已在会话中暴露过的 Kimi 密钥，再以不落盘、不入日志的运行时方式注入，用本仓 Gateway 重跑 L1/L2/L3 和同一 ScanRun 的 3 次独立采样；完成前四平台门禁保持 `blocked`。
2. 接通真实 Yudao 登录与 permission-info，在生产配置下验证 token 撤销、跨租户、超时和并发请求；当前浏览器验收只证明 `dev_only` 认证边界。
3. 为 Web/App 采集器补真实截图、来源面板、联网状态与区域证据，并与 API 样本并行展示和分口径报告；当前 API 证据等级不足以证明消费端真实呈现。
4. 将当前单机 QPS/并发限制扩展为 Redis/数据库分布式令牌桶，并补长时崩溃恢复和负载压测；MySQL circuit/quota/probe 状态已接入。
5. 按 Promotion Evidence Ledger 的 blocker 清单补真实队列、人工标注、Provider 引用和真实 T0/T+7 artifact；每项必须提交仓库内可校验路径与 SHA-256 后才能晋级 `ready`。
6. 补知识增量重嵌入、混合检索、过期提醒和事实冲突处置 UI。
7. 使用客户授权的 WordPress/HTTP 测试站点完成一次真实外部回执、截图、更新和撤回验收；适配器、attempt 消费与重试恢复已实现，但无外部账号时保持 `partial`。
8. 用四平台真实重复样本从新建品牌跑到客户报告，升级 Python/Node 运行时，在生产 HTTPS S3/MinIO 环境复验对象读写与截图展示，并完成带数据的浏览器 E2E 和完整上线门禁后，再合并到 `main`。

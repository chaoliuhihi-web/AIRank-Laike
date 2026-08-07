# AIRank 产品化持续交付状态（2026-08-08）

## 当前结论

状态：`partial / no-go for commercial launch`。

已经完成“吸收矩阵”“测量可信度第一切片”“内部 Skill Registry”“事实证据链”“审核后发布快照”“同口径复测归因”后端切片，以及控制台静态业务结果清理和真实 API/显式能力状态改造；但四平台真实重复采样、审核操作 UI、真实外部发布和带项目数据的浏览器客户报告尚未全部通过，不得宣称商业可用。

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

## 验收证据

- `python3 scripts/verify_absorption_matrix.py`：`status=pass`，12 sources / 64 rows / 21 GEO skills。
- `python3 -m pytest -q`：`178 passed, 7 skipped`。
- `cd apps/web && npm run build`：通过；Node 小版本存在升级告警。
- 浏览器：`/login -> /console` 登录通过；11 个控制台路由完成桌面/390px 空态验收，无横向溢出、无 console warning/error；发布报告按钮明确提示未开放，AI 来客助手显示 `disabled`。
- MySQL 临时库：Alembic `20260808_0008`；42 张 AIRank 表校验通过；真实 MySQL 复测链路生成 1 个 RetestRun 和 1 个带 SHA-256/evidence index 的报告，临时库已删除。
- 本地真实 MySQL integration：`6 passed, 1 skipped`（仅 Yudao 外部服务跳过）；两个独立 Provider store 实例通过共享熔断、重复幂等阻断、并发配额竞争（仅一个成功）、commit 记账和 probe 落库测试；未使用真实 Provider 凭证。

## 下一实施顺序

1. 为 Kimi 完成不落盘、不入日志的运行时凭证注入，并用本仓 Gateway 重跑 L1/L2/L3；四平台 probe 结果写入持久化 ledger。
2. 将当前单机 QPS/并发限制扩展为 Redis/数据库分布式令牌桶，并补长时崩溃恢复和负载压测；MySQL circuit/quota/probe 状态已接入。
3. 为首批 8 个内部 Skill 补 holdout/对抗/真实 Provider eval 和 promotion evidence ledger。
4. 补知识增量重嵌入、混合检索、过期提醒与冲突审核 UI。
5. 实现安全的 WordPress/HTTP Publisher adapter、attempt 消费、重试/恢复和真实外部回执门禁。
6. 补事实审核、冲突处理、内容审核、发布执行和样本下钻等可写 UI；所有写操作绑定真实 API、权限、审计和失败恢复。
7. 用四平台真实重复样本从新建品牌跑到客户报告，完成带数据的浏览器 E2E 和上线门禁后再同步 GitHub/Gitee。

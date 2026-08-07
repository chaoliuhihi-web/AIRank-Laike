# AIRank 产品化持续交付状态（2026-08-08）

## 当前结论

状态：`partial / no-go for commercial launch`。

已经完成“吸收矩阵”“测量可信度第一切片”“内部 Skill Registry”和“事实证据链领域切片”，但四平台真实重复采样、知识导入与审核 UI、发布复测与客户报告尚未全部通过，不得宣称商业可用。

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

## 验收证据

- `python3 scripts/verify_absorption_matrix.py`：`status=pass`，12 sources / 64 rows / 21 GEO skills。
- `python3 -m pytest -q`：`159 passed, 6 skipped`。
- `cd apps/web && npm run build`：通过；Node 小版本存在升级告警。
- MySQL 临时库：Alembic `20260808_0005`；36 张 AIRank 表、7 张 Provider 运维表校验通过。

## 下一实施顺序

1. 为 Kimi 完成不落盘、不入日志的运行时凭证注入，并用本仓 Gateway 重跑 L1/L2/L3；四平台 probe 结果写入持久化 ledger。
2. 把进程内 circuit/quota 接到 MySQL/Redis repository，补多 worker 并发和故障恢复门禁。
3. 为首批 8 个内部 Skill 补 holdout/对抗/真实 Provider eval 和 promotion evidence ledger。
4. 实现知识安全导入、原文边界切片、增量同步、冲突审核 API/UI 与过期提醒。
5. 事实审核通过后再恢复内容生成；随后实现发布快照、WordPress/HTTP/导出包和 T0/T+7/T+14/T+30 复测。
6. 清理剩余前端静态业务页面，全部接真实 API 或明确 `empty/partial/blocked/disabled` 状态。
7. 用四平台真实重复样本从新建品牌跑到客户报告，完成浏览器 E2E 和上线门禁后再同步 GitHub/Gitee。

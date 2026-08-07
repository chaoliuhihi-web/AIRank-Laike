# AIRank 产品化持续交付状态（2026-08-08）

## 当前结论

状态：`partial / no-go for commercial launch`。

已经完成“吸收矩阵”和“测量可信度第一切片”，但四平台真实重复采样、Skill 平台、事实治理、发布复测与客户报告尚未全部通过，不得宣称商业可用。

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

## 验收证据

- `python3 scripts/verify_absorption_matrix.py`：`status=pass`，12 sources / 64 rows / 21 GEO skills。
- `python3 -m pytest -q`：`134 passed, 6 skipped`。
- `cd apps/web && npm run build`：通过；Node 小版本存在升级告警。
- MySQL 临时库：Alembic `20260808_0003`；9 个 AnswerSnapshot 关键字段、2 张新表校验通过。

## 下一实施顺序

1. 把已在本机验证的豆包、千问、Kimi、DeepSeek API 调用改造成 AIRank Provider Gateway；凭证只从进程环境注入。
2. 实现 L1/L2/L3 健康探测、路由、退避、熔断、QPS/配额、usage precision 与模型迁移门禁。
3. 注册首批 8 个内部 Skill，补 manifest、schema、事实/失败政策、rubric 和 eval cases。
4. 建立 KnowledgeSource/FactRevision/FactConflict/ClaimSupport/Citation/EvidenceSnapshot 正式事实链。
5. 事实审核通过后再恢复内容生成；随后实现发布快照、WordPress/HTTP/导出包和 T0/T+7/T+14/T+30 复测。
6. 清理剩余前端静态业务页面，全部接真实 API 或明确 `empty/partial/blocked/disabled` 状态。
7. 用四平台真实重复样本从新建品牌跑到客户报告，完成浏览器 E2E 和上线门禁后再同步 GitHub/Gitee。

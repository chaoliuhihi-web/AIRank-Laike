# Low Touch Hermes Spec Handoff - 2026-05-17

## 本轮目标

补齐“参考前端页面功能，尽量操作简单，联网检索和智能体执行尽量交给 Hermes”的产品规格。

## 新增文档

- `docs/product/low-touch-hermes-functional-spec.md`

该文档把当前 Web 页面拆成两类：

- 官网获客入口：`/`、`/free-check`、`/product`、`/solutions`、`/cases`、`/pricing`、`/resources`
- 控制台主链：`/console`、`/console/checkup`、`/console/facts`、`/console/questions`、`/console/gaps`、`/console/gaps/questions`、`/console/assets`、`/console/publishing`、`/console/reports`、`/console/settings`、`/console/assistant`

每个页面都定义了：

- 用户最小动作
- Hermes/智能体自动动作
- 输出对象
- 自动化等级
- 验收条件

## 关键产品结论

MVP 默认不是让用户手工建复杂表单，而是：

```text
输入官网
-> Hermes 自动建档、找竞品、生成问题、检索公开证据
-> 用户确认项目/竞品/高风险事实
-> Hermes 扫描、归因、识别缺口、生成资产和报告
-> 用户审核公开内容并记录发布 URL
-> Hermes 自动观察发布、复测并生成报告
```

## 开发影响

下一批 contract/API 应优先支持：

- `checkup_start`
- `project_seed`
- `competitor_candidate`
- `buyer_question_map`
- `scan_run_detail`
- `fact_review_queue`
- `gap_overview`
- `asset_bundle`
- `publishing_status`
- `report_list`
- `hermes_job`

## 边界

本轮只补文档，没有实现 worker 深层调度，也没有接入或复制 `XingheAI2026V2` 代码。Hermes 被定义为能力层，AIRank 仍保留自己的 contracts、API、MySQL 主数据和审核状态。


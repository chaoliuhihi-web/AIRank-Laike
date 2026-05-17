# packages/domain

AIRank 核心领域模型。

## 领域对象优先级

1. BrandProject — 品牌项目
2. Competitor — 竞品
3. BuyerQuestion — 买家问题地图
4. AIScanRun — AI 平台扫描运行
5. AIAnswerSnapshot — AI 回答快照
6. SourceCitation — 引用来源
7. **FactAtom** — 可信事实卡的内部最小事实单元
8. FactStore — 企业事实库
9. CompetitorSuppression — 竞品压制分析
10. EvidenceGap — 内容/信源缺口（页面可叫推荐证据缺口）
11. AssetBundle — AI 收录包 / AI 推荐资产包
12. PublishRecord — 发布记录和状态机
13. RetestRun — 复测运行
14. ExecutiveReport — 高管报告
15. Lead — 来客线索

## 子模块结构

```text
src/
  project/          品牌项目
  competitor/       竞品管理
  question/         买家问题地图
  scan/             AI 平台扫描记录和回答快照
  fact-atom/        可信事实卡的内部最小事实单元（FactAtom）
  fact-store/       企业事实库
  gap/
    suppression/    竞品压制分析
    evidence-gap/   内容/信源缺口（页面可叫推荐证据缺口）
  asset/            AI 收录包 / 推荐资产包
  publishing/       发布状态机和渠道管理
  report/           体检报告、复测报告、高管报告
  lead/             来客线索
  assistant/        AI 来客助手（P2 占位）
```

## 术语映射

详见 `docs/decisions/terminology.md`。

## 依赖规则

本包不依赖 `packages/xinghe-adapter`，保证 AIRank 领域模型独立。

## M2 async job domain

`packages/domain/src/airank_domain/async_job.py` defines the first AIRank async
job state machine used by worker tests:

```text
queued -> running -> succeeded
queued -> running -> failed
queued -> running -> timeout
```

Worker code must not leave failed provider calls in `queued`. Retries are explicit
state transitions so later MySQL persistence can distinguish fresh work from
failed or timed-out work.

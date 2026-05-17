# ADR 0001: 独立产品仓 + Xinghe Adapter

## 状态

Accepted

## 背景

AIRank 来客需要复用 `XingheAI2026V2` 的 yudao、Crawler Gateway、KB/Qdrant、Brand Corpus、workflow-runner、Hermes 和内容生产经验。但 AIRank 面向企业品牌方，是新 SaaS 产品线，需要独立部署、独立迭代、独立收费。

## 决策

AIRank 保持独立仓库和独立运行内核。

`XingheAI2026V2` 只作为外部能力供应方，AIRank 通过 `packages/contracts` 和 `packages/xinghe-adapter` 接入，不直接 import 主仓内部代码，不复制主仓完整目录。

## 后果

好处：

- AIRank MVP 不被主仓历史复杂度拖住。
- 领域模型更清楚，适合企业品牌方。
- 后续可按能力成熟度逐项替换自有实现。
- 主仓只需维护薄 contract / bridge，不承载新产品全量代码。

代价：

- 第一阶段需要在 AIRank 自己实现 crawler-lite、kb-lite、score、evidence 等最小能力。
- 需要维护 adapter 契约和能力状态矩阵。
- 跨仓能力变更必须通过 contract test 防止漂移。

## 红线

- 不跨仓直接 import 内部模块。
- 不复制 `.runtime` 和历史数据。
- 不把主仓能力标记为 ready，除非有可复测接口和验收证据。

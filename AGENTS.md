# AIRank Agent Instructions

你是全球顶级的 IT 系统架构师和技术工程师，必须从产品、架构、工程、交付和长期维护角度全面考虑问题。

## 仓库同步

- 默认先从 GitHub 同步最新代码。
- 当前 GitHub 远端：`origin=https://github.com/chaoliuhihi-web/AIRank-Laike.git`
- 当前 Gitee 远端：`gitee=https://gitee.com/xinghetech/AIRank-Laike.git`
- 如果需要推送代码，必须同时推送到 GitHub 和 Gitee。

## XingheAI2026V2 整合原则

- AIRank 来客是独立 SaaS 产品仓，不放进 `XingheAI2026V2` 主仓做子模块。
- `XingheAI2026V2` 只作为能力供应方和契约源，提供 yudao、Crawler Gateway、KB/Qdrant、Brand Corpus、workflow-runner、Hermes、内容生产和治理经验。
- AIRank 不允许直接 import 或复制 `XingheAI2026V2` 内部业务代码路径。
- 所有复用必须经过 `packages/contracts` 和 `packages/xinghe-adapter`，以 OpenAPI、JSON Schema、SDK adapter 或异步 job contract 方式连接。
- 每个接入能力必须标注状态：`ready`、`partial`、`blocked`、`disabled`、`dev_only`。

## 开发约束

- 第一阶段优先保证 AIRank 自己可以独立跑通最小闭环。
- 不为了复用旧底座而牺牲 AIRank 的独立部署、清晰领域模型和客户交付速度。
- 不直接整块复制 `XingheAI2026V2` 的出版、营销、门禁、`.runtime` 历史复杂度。
- 与星河整合时优先抽取可产品化能力：可信事实库、证据链、抓取/引用、内容生产、审校、发布包、复测报告。

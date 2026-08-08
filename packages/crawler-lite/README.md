# packages/crawler-lite

AIRank 自有轻量采集能力。

当前已实现：

- 指定公开 HTTP(S) URL 的 DNS 固定安全抓取；
- HTML 标题、meta、canonical、robots、H1、正文、语义容器和 JSON-LD 提取；
- 规则级证据、修复建议、内容 hash、最终 URL、响应状态与连接 IP；
- 独立命名的 `technical_extractability_score`，禁止与品牌提及率或推荐率合并。

下一步：官网 sitemap 增量抓取、手动补录失败页、队列批量调度和证据对象存储。

复杂动态页、登录态、队列、connector、版本审计后续通过 `packages/xinghe-adapter/crawler` 接入 `XingheAI2026V2` Crawler Gateway。

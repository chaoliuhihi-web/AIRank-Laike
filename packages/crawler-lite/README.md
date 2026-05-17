# packages/crawler-lite

AIRank 自有轻量采集能力。

MVP 只需要：

- 官网首页和 sitemap 抓取
- 指定 URL 抓取
- HTML 标题、正文、meta、结构化数据提取
- 手动补录抓取失败页面
- 保存 blocked reason

复杂动态页、登录态、队列、connector、版本审计后续通过 `packages/xinghe-adapter/crawler` 接入 `XingheAI2026V2` Crawler Gateway。

# packages/evidence

证据链、回答快照、source index 和下载回执。

AIRank 的报告必须可复盘：

- 每个 AI 回答保存原文、平台、模型、问题、时间和 run_id。
- 每个引用来源保存 URL、来源类型、所属方、抓取状态和快照。
- 每个报告保存 source index 和 evidence bundle。
- 下载导出需要有 receipt，方便交付验收。

该包复用 `XingheAI2026V2` creator-marketing 的 report evidence 思路，但不复制其内部实现。

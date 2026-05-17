# Review Agent

审核 Agent 负责质量、契约、风险和验收。

检查重点：

- 是否保持 AIRank 独立部署
- 是否所有跨仓调用经过 `packages/xinghe-adapter`
- 是否保存 AI 回答快照和引用来源
- 是否有可信事实卡 / FactAtom 支撑内容生成
- 是否有报告证据包和下载回执
- 是否真实标注星河能力状态

上线审核以 `docs/handoff/release-gate.md` 为强制门禁。每次审核结论必须写入 `docs/handoff/review-ledger.md`，状态只能是：

```text
PASS
PASS_WITH_RISK
BLOCKED
```

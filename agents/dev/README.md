# Dev Agent

开发 Agent 负责产品主链实现。

优先级：

1. contracts
2. domain
3. api
4. web
5. worker
6. score
7. evidence
8. crawler-lite
9. kb-lite

开发 Agent 不直接修改 `XingheAI2026V2`，也不直接复制主仓代码。

当前三 AI 分工以 `docs/handoff/launch-board.md` 为准：

- CodexWin：产品主链、API、Web、contracts。
- CodexiMac：数据、worker、score、evidence、adapter。
- CodexMacPro：审核、测试、CI、release gate。

每轮结束必须更新 `docs/handoff/review-ledger.md`。

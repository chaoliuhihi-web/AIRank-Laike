# Packet Status Files

这些文件是三 AI 并行执行时的低冲突状态区。`execution-packets.md` 定义任务，通常只由 CodexMacPro 调整；CodexWin、CodexiMac、CodexMacPro 各自只更新自己的状态文件。

## Rules

1. 每个 AI 只改自己的 status 文件。
2. packet 状态以 status 文件为准；同一个 packet 出现多次时，文件里靠后的记录覆盖靠前记录。
3. 详细复盘可以写在本文件下方的 run log；全局上线结论仍由 CodexMacPro 汇总到 `review-ledger.md`。
4. 可用状态：`todo`、`in_progress`、`review`、`review_env_blocked`、`blocked`、`done`。

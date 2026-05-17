# CodexWin Prompt

你负责 AIRank 来客产品主链开发，是产品闭环 owner。

## 固定启动

每轮开始先执行：

```bash
cd /Users/bruce/Developer/work/AIRank
git fetch origin
git merge --ff-only origin/main
python3 scripts/agent_control.py next codex-win --write
```

然后读取 `docs/handoff/next-prompts/codex-win.md`，按自动生成的第一条 open task 执行。不要从聊天记录复制旧 prompt。

如果合并失败，先判断冲突类型：

- 只冲突中心 handoff 文件：运行 `python3 scripts/agent_control.py recover-handoff --write`，再运行 `GIT_EDITOR=true git rebase --continue` 或 PowerShell 的 `$env:GIT_EDITOR='true'; git rebase --continue`，然后继续。
- 冲突业务代码文件：停止编码，报告冲突文件和建议 owner。

## 你的 Owner 范围

优先负责：

- `apps/api`
- `apps/web`
- `packages/contracts`
- `tests/contracts`
- 与上述代码直接相关的 `docs/handoff`

当前主目标：

```text
建项目 -> 录竞品 -> 录买家问题 -> 创建 scan run -> 展示扫描结果 -> 展示 AIRank Score -> 展示推荐缺口 -> 生成报告
```

## 禁止事项

- 不直接修改 `apps/worker` 深层任务调度，除非 CodexiMac 已明确交接。
- 不直接修改 `packages/score` 的核心计算，除非只是在 API 层调用。
- 不复制 `XingheAI2026V2` 内部业务代码。
- 不把 AIRank 表建进 yudao 数据库。
- 不绕过 `packages/contracts` 直接让前端猜接口。
- 不为了页面好看继续写假数据而不推进真实 API。

## 每轮任务形态

每轮只完成一个可验证小闭环，例如：

- 一个 OpenAPI/JSON Schema 契约 + 一个 API endpoint + 一个前端调用。
- 一个页面从 fixture 切换到 API。
- 一个 CRUD 主链 + contract test。
- 一个报告 view model + 页面展示。

不要一轮同时做 API、worker、score、UI 大面积重构。

## 必跑验证

按修改范围选择，至少执行：

```bash
git diff --check
cd apps/web && npm run build
```

后端初始化后继续加：

```bash
cd apps/api && pytest
python3 -m pytest tests/contracts
```

## 交付记录

每轮结束必须更新：

- `docs/handoff/status/codex-win.md`：更新你负责的 packet 状态、commit、验证结果和风险。
- 不直接更新 `docs/handoff/execution-packets.md` 或 `docs/handoff/review-ledger.md`，除非 CodexMacPro 明确要求你解决冲突。
- 如果你处于 rebase 冲突状态，先读 `docs/handoff/rebase-recovery.md`。

## 提交和推送

确认测试通过后：

```bash
git status --short
git add <本轮相关文件>
git commit -m "<type>: <short summary>"
git push origin main
git push gitee main
```

提交信息必须具体，避免 `update`、`fix stuff`。

## 完成后继续

完成一轮后不要停止在泛泛总结。继续从 `docs/handoff/launch-board.md` 领取下一个 CodexWin owner 的 `todo`，重复以上流程。

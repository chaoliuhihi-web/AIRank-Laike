# AIRank Rebase Recovery Playbook

CodexMacPro 负责把三 AI 的冲突恢复规则固化成可执行命令。目标是：保留业务代码，减少中心 handoff 文件冲突，让 Win/iMac 能继续跑。

## 原则

1. `docs/handoff/execution-packets.md`、`docs/handoff/review-ledger.md`、`docs/handoff/launch-board.md`、`docs/handoff/agent-control.md` 是中心 handoff 文件，由 CodexMacPro 统一治理。
2. CodexWin / CodexiMac 的运行状态写到 `docs/handoff/status/<owner>.md`。
3. rebase 时如果只冲突中心 handoff 文件，保留当前 `origin/main` 版本，不保留开发 AI 本地提交里的旧中心文件改动。
4. rebase 时如果冲突业务代码文件，停止并交回 CodexMacPro。

## 当前 CodexiMac 恢复步骤

CodexiMac 当前处于 rebase in progress，冲突文件是：

```text
docs/handoff/execution-packets.md
docs/handoff/review-ledger.md
```

这类冲突按中心 handoff 规则恢复：

```bash
python3 scripts/agent_control.py recover-handoff --write
GIT_EDITOR=true git rebase --continue
```

PowerShell：

```powershell
python scripts/agent_control.py recover-handoff --write
$env:GIT_EDITOR='true'; git rebase --continue
```

如果当前 rebase 中的脚本版本还没有 `recover-handoff` 命令，使用等价 Git 命令：

```bash
git restore --source=HEAD -- docs/handoff/execution-packets.md docs/handoff/review-ledger.md
git add docs/handoff/execution-packets.md docs/handoff/review-ledger.md
GIT_EDITOR=true git rebase --continue
```

PowerShell：

```powershell
git restore --source=HEAD -- docs/handoff/execution-packets.md docs/handoff/review-ledger.md
git add docs/handoff/execution-packets.md docs/handoff/review-ledger.md
$env:GIT_EDITOR='true'; git rebase --continue
```

## CodexiMac Rebase 完成后

1. 同步最新 main：

```bash
git fetch origin
git rebase origin/main
```

2. 把 Alembic packet 状态写入：

```text
docs/handoff/status/codex-imac.md
```

如果 Alembic 文件、`upgrade head --sql`、22/22 table parity 都通过，但本地 MySQL 权限失败，状态写：

```text
| M1-IMAC-001 | review_env_blocked | <commit> | Alembic files/sql/parity passed; local MySQL access denied. |
```

3. 验证：

```bash
python3 scripts/agent_control.py gate --write
git diff --check
cd apps/api && python3 -m alembic upgrade head --sql
```

4. 推送：

```bash
git push origin main
git push gitee main
```

## 后续规则

CodexWin / CodexiMac 不再把运行日志追加到 `review-ledger.md`，也不直接改 `execution-packets.md`。它们只更新自己的 status 文件。CodexMacPro 定期读取 status 文件，再汇总到全局 review ledger。

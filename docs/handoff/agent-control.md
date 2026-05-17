# AIRank Agent Control Mechanism

目标：让 CodexMacPro、CodexWin、CodexiMac 三个 AI 可以持续协作，不靠每轮手动复制长 prompt，不跑偏，并且用机制约束质量。

## 控制原则

1. `docs/handoff/launch-board.md` 是唯一任务事实源。
2. CodexMacPro 是总控，不只是 reviewer；它必须分析 Win/iMac 阶段性提交，更新方向和下一轮任务。
3. CodexWin / CodexiMac 只能执行自己 lane 的任务，不能自行扩大范围。
4. 所有阶段性结论必须写入 `docs/handoff/review-ledger.md`。
5. 上线判断只看 `docs/handoff/release-gate.md`，不能凭感觉说可上线。
6. 自动 prompt 由脚本生成，避免每轮从聊天记录复制旧提示词。

## 自动生成下一轮 Prompt

CodexWin：

```bash
cd /Users/bruce/Developer/work/AIRank
git fetch origin
git merge --ff-only origin/main
python3 scripts/agent_control.py next codex-win --write
```

然后读取 `docs/handoff/next-prompts/codex-win.md`。

CodexiMac：

```bash
cd /Users/bruce/Developer/work/AIRank
git fetch origin
git merge --ff-only origin/main
python3 scripts/agent_control.py next codex-imac --write
```

然后读取 `docs/handoff/next-prompts/codex-imac.md`。

CodexMacPro：

```bash
cd /Users/bruce/Developer/work/AIRank
git fetch origin
git merge --ff-only origin/main
python3 scripts/agent_control.py director --write
```

然后读取：

```text
docs/handoff/director-brief.md
docs/handoff/next-prompts/codex-macpro.md
```

## CodexMacPro 总控职责

CodexMacPro 每轮必须：

1. 读取最近提交：`git log --oneline -5`
2. 查看阶段性变更：`git show --stat --oneline HEAD`
3. 运行基础 gate：`python3 scripts/agent_control.py gate --write`
   - `docs/handoff/agent-gate-report.md` 是本地生成文件，不入库；审核结论必须写入 `docs/handoff/review-ledger.md`。
4. 判断 Win/iMac 是否偏离 v0.1 beta 主链、修改非 owner 文件、引入不可追溯结论、跳过 tenant/trace/error/evidence 约束。
5. 更新 `docs/handoff/launch-board.md` 和 `docs/handoff/review-ledger.md`。
6. 重新生成三台 AI 的下一轮 prompt：`python3 scripts/agent_control.py director --write`

## 防跑偏机制

| 风险 | 机制 |
| --- | --- |
| 三个 AI 抢同一块代码 | `launch-board` owner lane + generated prompt 只分配本 owner task |
| 只做 UI 不做主链 | Release Gate 要求 API、DB、worker、score、evidence 全通过 |
| 代码看起来能跑但不可上线 | CodexMacPro 每轮写 `PASS/BLOCKED/PASS_WITH_RISK` |
| 手动 prompt 过期 | `scripts/agent_control.py director --write` 每轮重生成 |
| 跨仓依赖失控 | Gate 检查只能通过 `packages/xinghe-adapter` |
| fixture 冒充真实数据 | Launch Board 明确 `前端 fixture 切 API` 是 release blocker |
| bug 越积越多 | 每轮只做小闭环，必须写验证命令和结果 |
| 双远端不同步 | 每轮提交后强制 `git push origin main && git push gitee main` |

## 自动化能力边界

当前自动化是本仓脚本级机制，不是后台 daemon。它解决：

- 自动生成下一轮 prompt。
- 自动读取当前任务看板。
- 自动把 owner task、验证命令、最近风险写进 prompt。
- 自动生成 MacPro director brief。
- 自动跑基础 gate report。

它不解决自动打开三个 Codex 客户端。后续如果需要更强自动化，可以把 `scripts/agent_control.py director --write` 接到本地定时任务或 Codex automation。

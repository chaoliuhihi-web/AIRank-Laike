# CodexiMac Prompt

你负责 AIRank 来客数据主链、worker、score、evidence 和 Xinghe/yudao adapter，是系统能力 owner。

## 固定启动

每轮开始先执行：

```bash
cd /Users/bruce/Developer/work/AIRank
git fetch origin
git merge --ff-only origin/main
python3 scripts/agent_control.py next codex-imac --write
```

然后读取 `docs/handoff/next-prompts/codex-imac.md`，按自动生成的第一条 open task 执行。不要从聊天记录复制旧 prompt。

如果合并失败，先判断冲突类型：

- 只冲突中心 handoff 文件：运行 `python3 scripts/agent_control.py recover-handoff --write`，再运行 `GIT_EDITOR=true git rebase --continue` 或 PowerShell 的 `$env:GIT_EDITOR='true'; git rebase --continue`，然后继续。
- 冲突业务代码文件：停止编码，报告冲突文件和建议 owner。

## 你的 Owner 范围

优先负责：

- `apps/worker`
- `packages/domain`
- `packages/score`
- `packages/evidence`
- `packages/kb-lite`
- `packages/crawler-lite`
- `packages/xinghe-adapter`
- `ops/deployment`
- `tests/acceptance`
- 与上述代码直接相关的 `docs/handoff`

当前主目标：

```text
MySQL schema/Alembic -> scan job -> answer snapshot -> citation -> FactAtom -> content gap -> AIRank Score -> report evidence package
```

## 禁止事项

- 不直接改 `apps/web` 页面布局和视觉，除非只补 API 字段消费说明。
- 不直接改 CodexWin 正在实现的 API endpoint 行为，除非先在 `docs/handoff/status/codex-imac.md` 写明 contract 风险并交给 CodexMacPro。
- 不直接依赖 `XingheAI2026V2` 内部路径。
- 不把 Xinghe/yudao 不可用当 blocker；必须提供 local fallback / mock provider / manual import。
- 不写无法追溯来源的分数、结论或报告。

## 每轮任务形态

每轮只完成一个可验证小闭环，例如：

- Alembic 初始迁移 + schema 校验。
- scan job 领取 + heartbeat + timeout 回收。
- mock provider 生成 answer snapshot/citation。
- AIRank Score 纯函数 + fixture 测试。
- FactAtom 提取/确认状态流转。
- report evidence package + download receipt。
- adapter capability status 探测。

## 必跑验证

按修改范围选择，至少执行：

```bash
git diff --check
```

Python 工程初始化后继续加：

```bash
cd apps/worker && pytest
cd packages/score && pytest
cd packages/evidence && pytest
```

如果改数据库：

```bash
mysql -uroot -p < ops/deployment/mysql-bootstrap.sql
```

如果 Alembic 已建立，改跑：

```bash
cd apps/api && alembic upgrade head
```

## 交付记录

每轮结束必须更新：

- `docs/handoff/status/codex-imac.md`：更新你负责的 packet 状态、commit、验证结果、风险和 fallback 状态。
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

## 完成后继续

完成一轮后继续从 `docs/handoff/launch-board.md` 领取下一个 CodexiMac owner 的 `todo`，重复以上流程。

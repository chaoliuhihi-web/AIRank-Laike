# AIRank Review Ledger

本文件记录每轮三 AI 协作的变更、验证和审核结论。所有 owner 每轮结束必须追加记录。

## Status Values

```text
PASS
PASS_WITH_RISK
BLOCKED
TODO
```

## Entry Template

```text
## YYYY-MM-DD HH:mm +08:00 - <CodexWin|CodexiMac|CodexMacPro>

Scope:
-

Changed:
-

Validation:
- command:
- result:

Review:
- status:
- reviewer:
- notes:

Risks:
-

Next owner:
-
```

## 2026-05-17 - Codex

Scope:
- 建立三 AI 协作机制、上线看板、Release Gate 和 Review Ledger。

Changed:
- `agents/prompts/codex-win.md`
- `agents/prompts/codex-imac.md`
- `agents/prompts/codex-macpro.md`
- `docs/handoff/launch-board.md`
- `docs/handoff/release-gate.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `git diff --check`
- result: pass
- command: `cd apps/web && npm run build`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: Codex
- notes: 协作机制和文档门禁已建立；下一轮应由 CodexMacPro 执行 release gate 基础检查，并补 CI。

Risks:
- 当前只有前端 fixture 原型，后端、worker、迁移和报告证据链仍未实现。

Next owner:
- CodexWin 初始化 API。
- CodexiMac 初始化 Alembic。
- CodexMacPro 初始化 CI。

## 2026-05-17 - Codex

Scope:
- 按用户要求升级协作机制：CodexMacPro 对整体方向负责，自动生成三台 AI 下一轮 prompt，减少手动复制粘贴。

Changed:
- `scripts/agent_control.py`
- `.github/workflows/ci.yml`
- `.gitignore`
- `apps/api/requirements-dev.txt`
- `apps/api/main.py`
- `docs/handoff/agent-control.md`
- `docs/handoff/launch-board.md`
- `docs/handoff/release-gate.md`
- `agents/prompts/codex-macpro.md`
- `agents/prompts/codex-win.md`
- `agents/prompts/codex-imac.md`

Validation:
- command: `python3 scripts/agent_control.py director --write`
- result: pass
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this change
- command: `python3 -m pytest tests/contracts`
- result: initially blocked by Python 3.9 `str | None` annotation in `apps/api/main.py`; fixed and rerun passed
- command: `cd apps/web && npm run build`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: Codex
- notes: 自动 prompt 和 MacPro director brief 可生成；Prompt 任务解析已过滤非任务表；CI 已加入 diff check、Python 3.9 API contract test、Node 22 Web build；同时验证发现并修复 `cf20229` 的 Python 3.9 兼容性问题。

Risks:
- 当前机制是脚本级自动化，不是 daemon；仍需要每台 Codex 启动时执行固定短命令。

Next owner:
- CodexMacPro 按生成的下一轮 prompt 审核 `cf20229` / `a4de530` 阶段提交，并继续推进 release gate。

## 2026-05-17 - Codex

Scope:
- 复核当前资料是否足够支撑三 AI 同步推进，并补齐最小执行包粒度。

Changed:
- `docs/handoff/execution-packets.md`
- `.gitignore`
- `docs/handoff/agent-control.md`
- `docs/handoff/launch-board.md`
- `scripts/agent_control.py`
- `docs/handoff/director-brief.md` removed from tracked generated files
- `docs/handoff/next-prompts/*.md` removed from tracked generated files

Validation:
- command: `python3 scripts/agent_control.py director --write`
- result: pass
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this change
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts`
- result: pass
- command: `cd apps/web && npm run build`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: Codex
- notes: 原有资料能约束方向，但任务颗粒度仍偏粗；已新增 packet ID、owner、depends、file scope、acceptance、validation，并让自动 prompt 从 execution packets 读取。生成 prompt 已改为本地缓存，不再作为入库事实源，避免提交后 HEAD 过期。

Risks:
- 仍不是后台 daemon；需要三台 Codex 每轮执行固定启动命令。跨 packet 依赖完成情况还需要 owner 手动把 status 改为 `done`。

Next owner:
- CodexWin 领取 `M1-WIN-001`。
- CodexiMac 领取 `M1-IMAC-001`。
- CodexMacPro 领取 `M1-MACPRO-001`。

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

## 2026-05-17 - Codex

Scope:
- 处理 CodexWin Windows/PowerShell 环境反馈，修复 `agent_control.py gate` 依赖 `/bin/bash` 的跨平台问题。

Changed:
- `scripts/agent_control.py`
- `docs/handoff/review-ledger.md`

Validation:
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this change
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts`
- result: pass
- command: `cd apps/web && npm run build`
- result: pass

Review:
- status: PASS
- reviewer: Codex
- notes: `tracked_runtime_artifacts` 检查已改为 Python 原生实现，不再依赖 `bash` 或 `rg`，适合 Windows、macOS、Linux。

Risks:
- CodexWin 当前 Windows 工作区有未提交 Web 官网改动，执行 `M1-WIN-001` 时必须 path-limited add/commit，不能把旧 Web 改动混入 API baseline 提交。

Next owner:
- CodexWin 先同步到包含 execution packets 和 Windows gate fix 的最新 HEAD，再执行 `M1-WIN-001`。

## 2026-05-17 15:54 +08:00 - CodexWin

Scope:
- 完成 `M1-WIN-001 health-version-envelope`。
- 在 FastAPI baseline 中补齐 `/api/v1/health`、`/api/v1/version` 和统一 success envelope helper。
- 为 health/version 增加 full-response JSON Schema 和 contract tests，确认 `console/overview` 不回归。

Changed:
- `apps/api/main.py`
- `packages/contracts/health_response.schema.json`
- `packages/contracts/version_response.schema.json`
- `tests/contracts/test_api_baseline_contract.py`
- `docs/handoff/execution-packets.md`
- `docs/handoff/launch-board.md`

Validation:
- command: `$env:PYTHONUTF8='1'; python scripts/agent_control.py gate --write`
- result: pass with expected dirty Web website worktree outside this packet
- command: `python -m pytest tests/contracts -q`
- result: pass, 3 tests
- command: `git diff --check`
- result: pass
- command: `cd apps/web && npm run build`
- result: pass

Review:
- status: PASS
- reviewer: CodexWin
- notes: Health/version endpoints now return `{ data, meta }` with caller-provided `X-AIRank-Trace-Id` propagated and `request_id` generated. Version response includes service, API version, prefix, app version, and build commit fallback. `M1-WIN-001` marked `done`.

Risks:
- Existing uncommitted Web website work remains in the workspace and was deliberately excluded from this packet commit.
- `M1-WIN-002` still depends on `M1-IMAC-001 alembic-initial-schema`; CodexWin should not start CRUD persistence until that dependency is complete.

Next owner:
- CodexiMac for `M1-IMAC-001 alembic-initial-schema`.
- CodexMacPro can review `M1-WIN-001` and current gate output.

## 2026-05-17 15:56 +08:00 - CodexWin

Scope:
- Continued CodexWin packet loop after `M1-WIN-001`.
- Evaluated first open CodexWin packet: `M1-WIN-002 project-competitor-question-crud-contract`.

Changed:
- `docs/handoff/review-ledger.md`

Validation:
- command: `git fetch origin && git merge --ff-only origin/main && git rev-parse --short HEAD`
- result: pass, HEAD `e2e240b`
- command: `python scripts/agent_control.py next codex-win --write`
- result: pass

Review:
- status: BLOCKED
- reviewer: CodexWin
- notes: `M1-WIN-002` depends on `M1-WIN-001` and `M1-IMAC-001`. `M1-WIN-001` is done, but `M1-IMAC-001 alembic-initial-schema` remains `todo` in `docs/handoff/execution-packets.md`. CodexWin should not implement project/competitor/question CRUD persistence or fake DB behavior before the Alembic/schema dependency is available.

Risks:
- Starting CRUD contracts now would either bypass the DB owner lane or create mock semantics that may conflict with the upcoming Alembic schema.
- Existing uncommitted Web website work remains outside this block record and was not touched.

Next owner:
- CodexiMac should complete `M1-IMAC-001 alembic-initial-schema`.
- After that, CodexWin can resume at `M1-WIN-002`.

## 2026-05-17 - Codex

Scope:
- 分析 CodexWin 停止原因，并补充等待 Alembic 时仍可执行的 CodexWin packet。

Changed:
- `docs/handoff/execution-packets.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `git diff --check`
- result: pass
- command: `python3 scripts/agent_control.py next codex-win --write`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: Codex
- notes: CodexWin 停止是因为 `M1-WIN-002` 正确等待 `M1-IMAC-001`；为减少空等，新增 `M1-WIN-001B error-trace-foundation` 和 `M1-WIN-001C project-question-contract-skeleton`，让 CodexWin 在不碰数据库持久化的情况下继续推进。

Risks:
- `M1-WIN-001C` 只能冻结 contracts，不能实现假 DB CRUD；真正持久化仍必须等 `M1-IMAC-001`。

Next owner:
- CodexWin 继续领取 `M1-WIN-001B`。
- CodexiMac 继续领取 `M1-IMAC-001`。

## 2026-05-17 - Codex

Scope:
- 调整持续执行逻辑：自动 prompt 区分可执行任务和依赖阻塞任务，避免 AI 被第一条 blocked packet 停死。

Changed:
- `scripts/agent_control.py`
- `docs/handoff/execution-packets.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `python3 scripts/agent_control.py next codex-win --write`
- result: pass; `M1-WIN-001B` correctly appears as actionable after dependency parser fix
- command: `python3 scripts/agent_control.py next codex-imac --write`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: Codex
- notes: 生成 prompt 现在输出 `Actionable Tasks` 和 `Waiting Or Blocked Tasks`，依赖未满足的 packet 会被自动降到等待区；新增 `review_env_blocked` 状态，用于区分代码完成但外部环境未验证。

Risks:
- `review_env_blocked` 只表示可继续 contract/mock 层工作，不允许声明 release gate 通过。

Next owner:
- CodexWin 领取 `M1-WIN-001B`。
- CodexiMac 修复 remote 推送后推送 `0efcbb5`，若仅 MySQL 权限失败但 migration SQL/parity 已通过，应把 `M1-IMAC-001` 改为 `review_env_blocked` 而不是 `blocked`。

## 2026-05-17 - CodexMacPro

Scope:
- 处理 CodexiMac rebase 冲突反馈，降低三 AI 并行时中心 handoff 文件冲突概率。

Changed:
- `scripts/agent_control.py`
- `docs/handoff/status/README.md`
- `docs/handoff/status/codex-win.md`
- `docs/handoff/status/codex-imac.md`
- `docs/handoff/status/codex-macpro.md`
- `docs/handoff/execution-packets.md`
- `docs/handoff/agent-control.md`
- `docs/handoff/launch-board.md`
- `agents/prompts/codex-win.md`
- `agents/prompts/codex-imac.md`

Validation:
- command: `python3 scripts/agent_control.py next codex-win --write`
- result: pass; prompt shows `M1-WIN-001B` as actionable and uses `docs/handoff/status/codex-win.md`
- command: `python3 scripts/agent_control.py next codex-imac --write`
- result: pass; prompt uses `docs/handoff/status/codex-imac.md`
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this change
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: `execution-packets.md` is now treated as task definition, while per-owner packet state and run logs go to `docs/handoff/status/<owner>.md`. `agent_control.py` reads these status files as overrides, so dev agents no longer need to edit the same central files every round.

Risks:
- CodexiMac still needs to finish its interrupted rebase locally; this change prevents future repeats but does not automatically resolve its local conflict state.

Next owner:
- CodexiMac should resolve or abort/retry its current rebase using the instructions from CodexMacPro, then update only `docs/handoff/status/codex-imac.md`.
- CodexWin should sync latest and continue `M1-WIN-001B`.

## 2026-05-17 - CodexMacPro

Scope:
- 补齐 CodexMacPro 的实际协调能力：中心 handoff 冲突可自动恢复，开发 AI 不再只能停下汇报。

Changed:
- `scripts/agent_control.py`
- `docs/handoff/rebase-recovery.md`
- `docs/handoff/agent-control.md`
- `agents/prompts/codex-win.md`
- `agents/prompts/codex-imac.md`
- `agents/prompts/codex-macpro.md`

Validation:
- command: `python3 scripts/agent_control.py recover-handoff`
- result: pass
- command: `python3 scripts/agent_control.py next codex-win --write`
- result: pass
- command: `python3 scripts/agent_control.py next codex-imac --write`
- result: pass
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: 新增 `recover-handoff` 命令，中心 handoff 文件冲突时可自动恢复为当前 upstream 版本并继续 rebase；当前 CodexiMac 冲突可按 `rebase-recovery.md` 处理。

Risks:
- 业务代码冲突仍必须人工处理；该命令只处理中心 handoff 文件，不处理 Alembic/API/worker 源码冲突。

Next owner:
- CodexiMac 运行 `python3 scripts/agent_control.py recover-handoff --write` 或等价 Git 命令，继续 rebase 后推送 `0efcbb5`。

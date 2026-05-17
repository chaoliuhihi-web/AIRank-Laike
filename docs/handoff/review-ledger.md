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
- command: `cd apps/web && npm run build`
- result: pass
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this packet

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
- command: `cd apps/web && npm run build`
- result: pass
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this packet

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

## 2026-05-17 16:47 +08:00 - CodexMacPro

Scope:
- 修正三 AI 调度机制过度保守的问题，让开发 AI 遇到 DB、环境、外部服务或依赖 blocker 时继续推进可验证中间成果。

Changed:
- `scripts/agent_control.py`
- `docs/handoff/execution-packets.md`
- `docs/handoff/agent-control.md`
- `docs/handoff/launch-board.md`
- `docs/handoff/status/README.md`
- `docs/handoff/status/codex-macpro.md`
- `agents/prompts/codex-win.md`
- `agents/prompts/codex-imac.md`
- `agents/prompts/codex-macpro.md`

Validation:
- command: `python3 scripts/agent_control.py next codex-win --write`
- result: pass; next actionable task is `M1-WIN-001B error-trace-foundation`
- command: `python3 scripts/agent_control.py next codex-imac --write`
- result: pass; after syncing `25069c7`, next actionable task is `M4-IMAC-002 xinghe-yudao-capability-probe`
- command: `python3 scripts/agent_control.py director --write`
- result: pass
- command: `python3 -m py_compile scripts/agent_control.py`
- result: pass
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 3 tests
- command: `cd apps/worker && python3 -m pytest -q`
- result: pass, 6 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 6 tests
- command: `cd packages/score && python3 -m pytest -q`
- result: pass, 2 tests
- command: `cd packages/evidence && python3 -m pytest -q`
- result: pass, 6 tests
- command: `cd apps/web && npm run build`
- result: pass
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this change

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: `dev_only` is now treated as a development-satisfied status, not a release-ready status. Auto next prompts now include Development Acceleration Candidates so agents do not stop simply because production persistence or an external dependency is not ready.

Risks:
- This improves throughput but requires CodexMacPro to keep release gate strict: `dev_only` and `review_env_blocked` work can unblock development, but cannot be counted as beta release completion.

Next owner:
- CodexWin should sync and execute `M1-WIN-001B`, then continue `M1-WIN-001C` / `M1-WIN-001D` without waiting for DB persistence.
- CodexiMac should sync and execute `M4-IMAC-002`; MySQL real upgrade remains a release blocker, not a development stop sign.

## 2026-05-17 17:24 +08:00 - CodexMacPro

Scope:
- Director review after CodexiMac completed `M4-IMAC-002`.
- Sync launch board with owner status files so next prompts do not resend completed CodexiMac work.

Changed:
- `docs/handoff/launch-board.md`
- `docs/handoff/review-ledger.md`
- `docs/handoff/status/codex-macpro.md`

Validation:
- command: `git fetch origin`
- result: pass
- command: `git merge --ff-only origin/main`
- result: pass before remote advanced; after CodexWin pushed `442ca7b`, local commit was rebased cleanly onto `origin/main`
- command: `python3 scripts/agent_control.py director --write`
- result: pass
- command: `python3 scripts/agent_control.py next codex-macpro --write`
- result: pass; MacPro release tasks remain blocked by CodexWin API/report dependencies
- command: `python3 scripts/agent_control.py next codex-imac --write`
- result: pass; no remaining CodexiMac actionable or waiting tasks
- command: `python3 scripts/agent_control.py next codex-win --write`
- result: pass; after rebasing over `442ca7b`, next actionable task is `M1-WIN-001C`
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 6 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 7 tests
- command: `cd apps/web && npm run build`
- result: pass after local `npm ci` restored ignored `node_modules`
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this handoff update

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: CodexiMac Data/Worker/Evidence lane is development-complete through `M4-IMAC-002`. CodexWin `M1-WIN-001B` is now in review at `442ca7b`, so the Product/API/Web critical path moves to contract skeleton work.

Risks:
- `M1-IMAC-001` remains `review_env_blocked` until real MySQL credentials allow `alembic upgrade head`.
- `M4-IMAC-002` is `dev_only`; no real yudao/Xinghe/Hermes readiness has been proven.
- CodexWin API/web chain is still the active critical path, starting with `M1-WIN-001C`.

Next owner:
- CodexWin should execute `M1-WIN-001C project-question-contract-skeleton`, then `M1-WIN-001D`.
- CodexMacPro should keep release gate strict and split new work only when a same-lane dev-only or contract slice is needed.

## 2026-05-17 18:08 +08:00 - CodexMacPro

Release Gate: BLOCKED
Commit: `1a1def6`
Reviewer: CodexMacPro

Scope:
- Executed v0.1 beta release gate after CodexWin, CodexiMac, and MacPro packets reached review/dev_only/review_env_blocked.

Validation:
- `python3 -m pytest tests/contracts -q`: pass, 33 tests
- `python3 -m pytest tests/acceptance -q`: pass, 9 tests
- `cd apps/web && npm run build`: pass
- `cd apps/worker && python3 -m pytest -q`: pass, 6 tests
- `cd packages/score && python3 -m pytest -q`: pass, 2 tests
- `cd packages/evidence && python3 -m pytest -q`: pass, 6 tests
- `cd packages/xinghe-adapter && python3 -m pytest -q`: pass, 2 tests
- `cd apps/api && python3 -m alembic upgrade head --sql`: pass, offline SQL generated
- real `alembic upgrade head`: blocked by MySQL `(1045) Access denied for user 'airank'@'192.168.65.1'`

Residual risks:
- Real MySQL migration and MySQL-backed CRUD are not verified.
- yudao/Xinghe/Hermes capability matrix remains `dev_only`; no authenticated external integration readiness is proven.
- AI 收录包 and report payloads are API-backed but still dev-only seed content, not production-generated assets.

Next owner:
- CodexMacPro or human operator must fix MySQL grants / rerun bootstrap and rerun the real migration.
- Integration owner must provide real yudao/Xinghe/Hermes credentials or explicitly approve dev_only beta scope.

## 2026-05-17 18:14 +08:00 - CodexMacPro

Scope:
- Director cleanup after the beta release gate and push of `1a56c75`.
- Fixed stale auto-next routing that re-issued completed CodexWin launch-board tasks after status overrides marked all execution packets non-open.

Changed:
- `scripts/agent_control.py`
- `docs/handoff/launch-board.md`
- `docs/handoff/status/codex-macpro.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `git fetch origin && git merge --ff-only origin/main && git rev-parse --short HEAD`
- result: pass, HEAD `1a56c75`
- command: `python3 -m py_compile scripts/agent_control.py`
- result: pass
- command: `python3 scripts/agent_control.py director --write`
- result: pass; regenerated Win/iMac/MacPro prompts with no false CodexWin actionable task
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 33 tests
- command: `cd apps/web && npm run build`
- result: pass
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this handoff update

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: `agent_control.py` now only falls back to launch-board parsing for owners that have no execution-packet definitions. CodexWin, CodexiMac, and CodexMacPro all have packet definitions, so completed status-file overrides no longer produce duplicate old launch-board tasks.

Risks:
- Release remains blocked. This is a control-plane cleanup only; it does not make MySQL migration, MySQL-backed CRUD, yudao/Xinghe/Hermes, AI asset bundles, or report payloads release-ready.

Next owner:
- CodexMacPro should regenerate prompts and verify there are no false actionable tasks.
- Human/integration owner must fix real MySQL grants and provide real external capability credentials, or explicitly approve a dev_only beta scope.

## 2026-05-17 18:20 +08:00 - CodexMacPro

Scope:
- Reduced the MySQL release blocker by making the local bootstrap repair stale dev-user credentials and common host grants.
- Documented the remaining root-MySQL verification step instead of treating local Access denied as a code failure.

Changed:
- `ops/deployment/mysql-bootstrap.sql`
- `ops/deployment/README.md`
- `docs/handoff/release-gate.md`
- `docs/handoff/status/codex-macpro.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `mysql --version`
- result: blocked locally; `mysql` client is not installed in this shell
- command: CI bootstrap grep checks for required AIRank tables and worker fields
- result: pass
- command: `git diff --check`
- result: pass
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 33 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 9 tests

Review:
- status: REVIEW_ENV_BLOCKED
- reviewer: CodexMacPro
- notes: Bootstrap now creates/repairs `airank` for `%`, `localhost`, `127.0.0.1`, and Docker Desktop `192.168.65.%`. This should fix stale-password or missing-host local dev setups once a root-capable MySQL shell reruns the bootstrap.

Risks:
- If MySQL has an even more-specific `airank` host record, an operator still needs to inspect `mysql.user` and fix that exact host.
- Real `alembic upgrade head` remains unproven in this environment until MySQL client/root access is available.

Next owner:
- Human/CodexMacPro with root MySQL access should rerun `mysql -uroot -p < ops/deployment/mysql-bootstrap.sql`, then run `cd apps/api && AIRANK_DATABASE_URL=... python3 -m alembic upgrade head`.
- Integration owner still must provide real yudao/Xinghe/Hermes config or approve dev_only beta scope.

## 2026-05-17 18:34 +08:00 - CodexMacPro

Scope:
- Continued release hardening under the rule that dev_only cannot satisfy上线标准.
- Upgraded `M2-WIN-001 scan-run-api-contract` from in-memory-only behavior to a MySQL-backed scan repository path.

Changed:
- `apps/api/main.py`
- `tests/contracts/test_scan_run_api_contract.py`
- `docs/handoff/launch-board.md`
- `docs/handoff/status/codex-win.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `python3 -m pytest tests/contracts/test_scan_run_api_contract.py -q`
- result: pass, 9 tests
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 48 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 9 tests
- command: `python3 -m py_compile apps/api/main.py`
- result: pass
- command: `git diff --check`
- result: pass
- command: `cd apps/web && npm run build`
- result: pass
- command: `python3 scripts/agent_control.py gate --write`
- result: pass with expected dirty worktree during this packet
- command: `cd apps/worker && python3 -m pytest -q`
- result: pass, 7 tests
- command: `cd packages/score && python3 -m pytest -q`
- result: pass, 3 tests
- command: `cd packages/evidence && python3 -m pytest -q`
- result: pass, 9 tests
- command: `cd packages/xinghe-adapter && python3 -m pytest -q`
- result: pass, 2 tests
- command: `cd apps/api && AIRANK_DATABASE_URL=mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4 python3 -m alembic upgrade head`
- result: blocked by MySQL `(1045) Access denied for user 'airank'@'192.168.65.1'`

Review:
- status: REVIEW_ENV_BLOCKED
- reviewer: CodexMacPro
- notes: When `AIRANK_DATABASE_URL` is configured, scan run creation now verifies project/question rows, persists scan run/task rows, and enqueues `airank_async_jobs` rows for worker consumption. No-env mode remains in-memory only for local tests.

Risks:
- Real MySQL migration and API DB path still require root MySQL grant repair before they can be proven against the target database.
- Enqueued jobs now exist in the production schema, but real provider execution and status reconciliation still need integration verification.

Next owner:
- CodexMacPro should continue eliminating dev_only report/asset paths or run the real MySQL gate once credentials are fixed.
- CodexiMac/worker owner should verify DB-backed worker claim/complete behavior against `airank_async_jobs` after MySQL access is available.

## 2026-05-17 18:45 +08:00 - CodexMacPro

Scope:
- Continued release hardening for `M3-WIN-002 AI 收录包 API`.
- Replaced the production code path for asset bundles with a MySQL-backed repository while keeping no-env fallback for local web development.

Changed:
- `apps/api/main.py`
- `tests/contracts/test_asset_bundle_api_contract.py`
- `docs/handoff/launch-board.md`
- `docs/handoff/status/codex-win.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `python3 -m pytest tests/contracts/test_asset_bundle_api_contract.py -q`
- result: pass, 6 tests
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 52 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 9 tests
- command: `python3 -m py_compile apps/api/main.py`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: REVIEW_ENV_BLOCKED
- reviewer: CodexMacPro
- notes: When `AIRANK_DATABASE_URL` is configured, `GET /projects/{project_id}/asset-bundle` now verifies tenant/project scope and derives assets from `airank_content_assets`, `airank_content_gaps`, and `airank_publish_packages`. It returns a real empty/gap state when no generated assets exist instead of fixed production seed content.

Risks:
- Real MySQL execution remains blocked by the same `airank` access denied issue.
- Asset generation itself still depends on upstream evidence/content generation and publication jobs; this patch only makes the API read the production tables.

Next owner:
- Continue with `M4-WIN-001 report API` production hardening, then rerun the full release gate once MySQL grants are fixed.

## 2026-05-17 18:56 +08:00 - CodexMacPro

Scope:
- Continued release hardening for `M4-WIN-001 report API + download receipt`.
- Replaced the production code path for reports with a MySQL-backed repository and persistent audit receipt writes.

Changed:
- `apps/api/main.py`
- `tests/contracts/test_report_api_contract.py`
- `docs/handoff/launch-board.md`
- `docs/handoff/status/codex-win.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `python3 -m pytest tests/contracts/test_report_api_contract.py -q`
- result: pass, 6 tests
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 56 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 9 tests
- command: `python3 -m py_compile apps/api/main.py`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: REVIEW_ENV_BLOCKED
- reviewer: CodexMacPro
- notes: When `AIRANK_DATABASE_URL` is configured, report listing now reads tenant-scoped `airank_reports`; download receipt creation verifies the report and inserts a `report.download_receipt` audit row into `airank_audit_events`.

Risks:
- Real MySQL execution remains blocked by the same `airank` access denied issue.
- Report generation still depends on upstream evidence/report jobs populating `airank_reports`; this patch makes the API read/write production tables rather than seed payloads.

Next owner:
- Fix MySQL grants and rerun real migration/API DB-path smoke tests.
- Continue external yudao/Xinghe/Hermes capability verification.

## 2026-05-17 17:38 +08:00 - CodexMacPro

Scope:
- Review and corrective patch for CodexWin/CodexiMac recent code, focusing on error-code consistency, evidence-chain integrity, and score edge cases.

Changed:
- `packages/domain/src/airank_domain/async_job.py`
- `apps/worker/airank_worker/scan.py`
- `packages/evidence/src/airank_evidence/snapshot.py`
- `packages/domain/src/airank_domain/content_gap.py`
- `packages/evidence/src/airank_evidence/gap.py`
- `packages/score/src/airank_score/calculator.py`
- `apps/api/main.py`
- `apps/api/alembic/versions/20260517_0001_initial_schema.py`
- `ops/deployment/mysql-bootstrap.sql`
- `apps/worker/tests/test_async_job_lease.py`
- `apps/worker/tests/test_mock_provider_scan.py`
- `packages/evidence/tests/test_snapshot.py`
- `packages/evidence/tests/test_content_gap.py`
- `packages/score/tests/test_calculator.py`
- `tests/contracts/test_project_question_dev_repository_api.py`
- `docs/handoff/status/codex-macpro.md`

Validation:
- command: `cd apps/worker && python3 -m pytest -q`
- result: pass, 7 tests
- command: `cd packages/evidence && python3 -m pytest -q`
- result: pass, 9 tests
- command: `cd packages/score && python3 -m pytest -q`
- result: pass, 3 tests
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 19 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 7 tests
- command: `cd packages/xinghe-adapter && python3 -m pytest -q`
- result: pass, 2 tests
- command: `cd apps/web && npm run build`
- result: pass
- command: `cd apps/api && python3 -m alembic upgrade head --sql`
- result: pass after installing `apps/api/requirements-dev.txt` locally; generated SQL uses `website_url VARCHAR(2048)` for projects and competitors
- command: `python3 -m py_compile apps/api/main.py scripts/agent_control.py packages/domain/src/airank_domain/*.py packages/evidence/src/airank_evidence/*.py packages/score/src/airank_score/*.py apps/worker/airank_worker/*.py packages/xinghe-adapter/src/airank_xinghe_adapter/*.py`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: Project/competitor/question request models now forbid extra body fields and enforce unique arrays to match JSON Schema contracts; inferred brand names are bounded to the response contract; MySQL bootstrap/Alembic URL columns now match the 2048-char API contract; worker failures now use registered AIRank error codes; AnswerSnapshot rejects citation tenant/project/snapshot mismatch; content gap generation now requires FactAtom source citation alignment; score no longer rewards invalid raw `brand_rank=0`.

Risks:
- CodexWin contract skeleton is still schema-only; API and repository behavior remain the active critical path.
- `M4-IMAC-002` remains `dev_only`; no live yudao/Xinghe/Hermes readiness is proven.
- Live MySQL `alembic upgrade head` still depends on valid local DB credentials; SQL generation is verified in this review.

Next owner:
- CodexWin should continue `M1-WIN-001D project-question-dev-repository`.
- CodexMacPro should review CodexWin's first API repository implementation before it becomes the base for CRUD and scan APIs.

## 2026-05-17 17:57 +08:00 - CodexMacPro

Scope:
- Review and corrective patch after CodexWin/CodexiMac remote advanced with scan run contract/status API.
- Keep scan API behavior aligned with JSON Schema contracts before worker scheduling depends on it.

Changed:
- `apps/api/main.py`
- `packages/contracts/scan_run_create_request.schema.json`
- `packages/contracts/scan_run_response.schema.json`
- `packages/contracts/error-codes.md`
- `packages/contracts/error_response.schema.json`
- `tests/contracts/test_scan_run_api_contract.py`
- `docs/handoff/status/codex-macpro.md`

Validation:
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 32 tests
- command: `cd apps/worker && python3 -m pytest -q`
- result: pass, 7 tests
- command: `cd packages/evidence && python3 -m pytest -q`
- result: pass, 9 tests
- command: `cd packages/score && python3 -m pytest -q`
- result: pass, 3 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 7 tests
- command: `cd packages/xinghe-adapter && python3 -m pytest -q`
- result: pass, 2 tests
- command: `cd apps/web && npm run build`
- result: pass
- command: `cd apps/api && python3 -m alembic upgrade head --sql`
- result: pass; generated SQL keeps project/competitor `website_url VARCHAR(2048)`
- command: `python3 -m py_compile apps/api/main.py scripts/agent_control.py packages/domain/src/airank_domain/*.py packages/evidence/src/airank_evidence/*.py packages/score/src/airank_score/*.py apps/worker/airank_worker/*.py packages/xinghe-adapter/src/airank_xinghe_adapter/*.py`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: Scan run request models now forbid extra fields, enforce project/question ID patterns, reject duplicate provider/question scopes, and require non-empty selected question scope. Scan task lookup now uses registered `SCAN_TASK_NOT_FOUND` instead of unrelated `JOB_NOT_FOUND`.

Risks:
- Scan run API is still in-memory development status; it does not yet persist to MySQL or enqueue real worker jobs.
- Live MySQL `alembic upgrade head` still depends on valid local DB credentials; SQL generation is verified.

Next owner:
- CodexWin should continue the Product/API/Web critical path by wiring scan run persistence/worker queue behind the now stricter API contract.
- CodexMacPro should keep reviewing each API-to-worker bridge before it becomes release baseline.

## 2026-05-17 18:02 +08:00 - CodexMacPro

Scope:
- Review and corrective patch after CodexWin/CodexiMac remote advanced with fact review and asset bundle APIs.
- Keep API path/body validation aligned with `additionalProperties: false`, ID patterns, and traceable-source contract rules.

Changed:
- `apps/api/main.py`
- `tests/contracts/test_fact_review_api_contract.py`
- `tests/contracts/test_asset_bundle_api_contract.py`
- `docs/handoff/status/codex-macpro.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 42 tests
- command: `cd apps/worker && python3 -m pytest -q`
- result: pass, 7 tests
- command: `cd packages/evidence && python3 -m pytest -q`
- result: pass, 9 tests
- command: `cd packages/score && python3 -m pytest -q`
- result: pass, 3 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 7 tests
- command: `cd packages/xinghe-adapter && python3 -m pytest -q`
- result: pass, 2 tests
- command: `cd apps/web && npm run build`
- result: pass
- command: `cd apps/api && python3 -m alembic upgrade head --sql`
- result: pass; generated SQL keeps project/competitor `website_url VARCHAR(2048)`
- command: `python3 -m py_compile apps/api/main.py`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: Fact review request/source models now forbid extra fields, enforce source ID/title/url lengths, reject duplicate `source_refs`, and keep fact/project path IDs contract-shaped. Asset bundle now rejects invalid project IDs instead of returning a contract-invalid payload.

Risks:
- Fact review and asset bundle APIs are still development/in-memory slices; they do not yet read or persist real FactAtom/asset records.
- These endpoints are acceptable for frontend/API contract wiring, but not a release-ready evidence workflow until backed by MySQL and evidence stores.

Next owner:
- CodexWin should wire these endpoints to real repositories only after preserving the current validation and error-envelope behavior.
- CodexMacPro should continue reviewing every new API surface for schema/runtime drift before it reaches release gate.

## 2026-05-17 18:07 +08:00 - CodexMacPro

Scope:
- Review and corrective patch after CodexWin/CodexiMac remote advanced with report list and download receipt API.
- Keep report list path validation aligned with `report_list_response.schema.json`.

Changed:
- `apps/api/main.py`
- `tests/contracts/test_report_api_contract.py`
- `docs/handoff/status/codex-macpro.md`
- `docs/handoff/review-ledger.md`

Validation:
- command: `python3 -m pytest tests/contracts -q`
- result: pass, 44 tests
- command: `cd apps/worker && python3 -m pytest -q`
- result: pass, 7 tests
- command: `cd packages/evidence && python3 -m pytest -q`
- result: pass, 9 tests
- command: `cd packages/score && python3 -m pytest -q`
- result: pass, 3 tests
- command: `python3 -m pytest tests/acceptance -q`
- result: pass, 9 tests
- command: `cd packages/xinghe-adapter && python3 -m pytest -q`
- result: pass, 2 tests
- command: `cd apps/web && npm run build`
- result: pass
- command: `cd apps/api && python3 -m alembic upgrade head --sql`
- result: pass; generated SQL keeps project/competitor `website_url VARCHAR(2048)`
- command: `python3 -m py_compile apps/api/main.py`
- result: pass
- command: `git diff --check`
- result: pass

Review:
- status: PASS_WITH_RISK
- reviewer: CodexMacPro
- notes: Report list now validates `project_id` at the route boundary so invalid path IDs return the standard validation envelope instead of producing contract-invalid report payloads.

Risks:
- Report list and download receipt are still development seed APIs; receipts are not persisted and reports are not loaded from MySQL/object storage yet.

Next owner:
- CodexWin should preserve route-level validation when replacing seeded report payloads with real repository-backed data.

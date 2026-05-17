# CodexWin Packet Status

| Packet | Status | Commit | Notes |
| --- | --- | --- | --- |
| M1-WIN-001 | done | e2e240b | Health/version envelope completed and contract tests passed. |
| M1-WIN-001B | review | this commit | Unified API error envelope now uses the contract error registry and preserves `trace_id` for HTTP/validation/unexpected errors. |
| M1-WIN-001C | review | this commit | Project, competitor, and buyer question request/response JSON Schemas are frozen without DB persistence. |

## Run Log

- 2026-05-17: `M1-WIN-001` completed by CodexWin.
- 2026-05-17: `M1-WIN-001B` implemented in a clean CodexWin worktree because the original Windows main worktree is diverged and contains local website edits that must not be reset/stashed. Scope: `apps/api`, `packages/contracts`, `tests/contracts`. Validation: `python -m pytest tests/contracts -q` passed 6 tests; `git diff --check` passed; `cd apps/web && npm run build` passed after `npm ci` restored local ignored `node_modules`; `PYTHONUTF8=1 python scripts/agent_control.py gate --write` passed.
- 2026-05-17: `M1-WIN-001C` froze contract skeletons for low-touch project creation, Hermes-discovered competitors, and Hermes-generated buyer questions. Scope: `packages/contracts`, `tests/contracts`, `docs/handoff/status/codex-win.md`. Validation: `python -m pytest tests/contracts -q` passed 12 tests; `git diff --check` passed; `cd apps/web && npm run build` passed; `PYTHONUTF8=1 python scripts/agent_control.py gate --write` passed.

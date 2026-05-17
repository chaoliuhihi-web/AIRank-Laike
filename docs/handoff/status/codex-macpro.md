# CodexMacPro Packet Status

| Packet | Status | Commit | Notes |
| --- | --- | --- | --- |
| M1-MACPRO-001 | review | this commit | Added development acceleration rules, `dev_only` scheduling semantics, and refreshed launch-board next actions. |
| M4-MACPRO-DIRECTOR | review | this commit | Synced launch-board with CodexiMac status through `M4-IMAC-002 dev_only`; next critical path is CodexWin `M1-WIN-001C`. |

## Run Log

- 2026-05-17: Status files introduced to reduce handoff merge conflicts.
- 2026-05-17: CodexMacPro changed the control loop so dependency/environment blockers become contract/mock/dev-only packets instead of stopping CodexWin or CodexiMac.
- 2026-05-17: Director review confirmed CodexiMac has no remaining open packet in the current board; `M4-IMAC-002` is `dev_only`, not release-ready. After `M1-WIN-001B`, CodexWin `M1-WIN-001C` is the active blocker chain.

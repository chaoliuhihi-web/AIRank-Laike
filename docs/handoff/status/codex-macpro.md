# CodexMacPro Packet Status

| Packet | Status | Commit | Notes |
| --- | --- | --- | --- |
| M1-MACPRO-001 | review | this commit | Added development acceleration rules, `dev_only` scheduling semantics, and refreshed launch-board next actions. |

## Run Log

- 2026-05-17: Status files introduced to reduce handoff merge conflicts.
- 2026-05-17: CodexMacPro changed the control loop so dependency/environment blockers become contract/mock/dev-only packets instead of stopping CodexWin or CodexiMac.

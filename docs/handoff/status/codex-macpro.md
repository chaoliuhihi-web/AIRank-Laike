# CodexMacPro Packet Status

| Packet | Status | Commit | Notes |
| --- | --- | --- | --- |
| M1-MACPRO-001 | review | this commit | Added development acceleration rules, `dev_only` scheduling semantics, and refreshed launch-board next actions. |
| M4-MACPRO-DIRECTOR | review | this commit | Synced launch-board with CodexiMac status through `M4-IMAC-002 dev_only`; next critical path is CodexWin `M1-WIN-001C`. |
| M2-MACPRO-001 | review | this commit | Added acceptance coverage from project creation through scan run/task status to deterministic score calculation. |
| M3-MACPRO-001 | review | this commit | Added evidence-chain gate coverage rejecting unsourced confirmed facts and report conclusions missing snapshot/citation/FactAtom refs. |

## Run Log

- 2026-05-17: Status files introduced to reduce handoff merge conflicts.
- 2026-05-17: CodexMacPro changed the control loop so dependency/environment blockers become contract/mock/dev-only packets instead of stopping CodexWin or CodexiMac.
- 2026-05-17: Director review confirmed CodexiMac has no remaining open packet in the current board; `M4-IMAC-002` is `dev_only`, not release-ready. After `M1-WIN-001B`, CodexWin `M1-WIN-001C` is the active blocker chain.
- 2026-05-17: `M2-MACPRO-001` added `tests/acceptance/test_scan_score_chain.py` to verify project/question API, scan run/task status API, evidence snapshot, and deterministic scoring connect without worker scheduling. Validation: `python3 -m pytest tests/acceptance -q` passed 8 tests; `python3 -m pytest tests/contracts -q` passed 33 tests; `git diff --check` passed; `python3 scripts/agent_control.py gate --write` passed.
- 2026-05-17: `M3-MACPRO-001` added `tests/acceptance/test_evidence_chain_gate.py` to make unsourced confirmed facts and report conclusions without snapshot/citation/FactAtom evidence fail fast. Validation: `python3 -m pytest tests/acceptance -q` passed 9 tests; `python3 -m pytest tests/contracts -q` passed 33 tests; `git diff --check` passed; `python3 scripts/agent_control.py gate --write` passed.

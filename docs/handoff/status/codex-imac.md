# CodexiMac Packet Status

| Packet | Status | Commit | Notes |
| --- | --- | --- | --- |
| M1-IMAC-001 | review_env_blocked | ac2f8d5 | Alembic files/sql/parity passed; local MySQL access denied. |
| M1-IMAC-002 | review | ea56c7c | Tenant/project query fields, index coverage, sensitive fields, and no-cross-db-FK policy documented; `git diff --check` passed. |
| M2-IMAC-001 | review | 182f5c6 | Async job lease/heartbeat state machine covers queued/running/succeeded/failed/timeout; `python3 -m pytest` passed in apps/worker. |
| M2-IMAC-002 | review | 3ad8bdd | Mock provider generates answer snapshot with required source citations; worker marks missing-citation jobs failed. |
| M2-IMAC-003 | review | 6e6c615 | Deterministic score pure function returns identical results for identical snapshot/citation input. |
| M3-IMAC-001 | review | 4bbb2b6 | Confirmed FactAtom requires citation/object/source provenance; evidence bridge converts citations to FactSourceRef. |
| M3-IMAC-002 | review | e469ed0 | ContentGap generation requires question, citation, and FactAtom traceability. |
| M4-IMAC-001 | review | 86e2f65 | Report JSON conclusions require snapshot, citation, and FactAtom refs. |

## Run Log

- 2026-05-17: CodexiMac local Alembic commit `0efcbb5` is not pushed yet due sync conflict and remote credential issues.
- 2026-05-17: Rebased Alembic migration onto `origin/main`; kept central handoff files from origin. `cd apps/api && python3 -m alembic upgrade head --sql` and 22/22 bootstrap table parity passed; real upgrade remains environment-blocked by local MySQL access denied.
- 2026-05-17: Started `M1-IMAC-002` schema/index tenant review after `M1-IMAC-001` entered `review_env_blocked` with Alembic code and offline validation in main.
- 2026-05-17: Completed `M1-IMAC-002` docs review in `docs/architecture/mysql-schema-plan.md`; validation `python3 scripts/agent_control.py gate --write` and `git diff --check` passed.
- 2026-05-17: Started `M2-IMAC-001` async job lease/heartbeat baseline using pure domain transitions and an in-memory worker store before MySQL persistence.
- 2026-05-17: Completed `M2-IMAC-001` worker baseline. Direct `cd apps/worker && pytest` is environment-blocked because `pytest` is not in PATH, but `cd apps/worker && python3 -m pytest` passed 4 tests and `python3 -m pytest tests/acceptance` passed 1 test.
- 2026-05-17: Started `M2-IMAC-002` mock provider snapshot/citation path using `packages/evidence` models and worker scan handler.
- 2026-05-17: Completed `M2-IMAC-002`; validation `cd apps/worker && python3 -m pytest` passed 6 tests, `python3 -m pytest tests/acceptance` passed 2 tests, `python3 scripts/agent_control.py gate --write` and `git diff --check` passed.
- 2026-05-17: Started `M2-IMAC-003` deterministic AIRank Score pure function based on answer snapshot and citation inputs.
- 2026-05-17: Completed `M2-IMAC-003`; validation `cd packages/score && python3 -m pytest` passed 2 tests, `python3 -m pytest tests/acceptance` passed 3 tests, `python3 scripts/agent_control.py gate --write` and `git diff --check` passed.
- 2026-05-17: Started `M3-IMAC-001` FactAtom source rule so confirmed facts require citation/object/URL provenance.
- 2026-05-17: Completed `M3-IMAC-001`; validation `cd packages/evidence && python3 -m pytest` passed 2 tests, `python3 -m pytest tests/acceptance` passed 4 tests, `python3 scripts/agent_control.py gate --write` and `git diff --check` passed.
- 2026-05-17: Started `M3-IMAC-002` content gap generation with required question/citation/FactAtom traceability.
- 2026-05-17: Completed `M3-IMAC-002`; validation `cd packages/evidence && python3 -m pytest` passed 4 tests, `python3 -m pytest tests/acceptance` passed 5 tests, `python3 scripts/agent_control.py gate --write` and `git diff --check` passed.
- 2026-05-17: Started `M4-IMAC-001` report evidence JSON so every conclusion carries snapshot/citation/FactAtom refs.
- 2026-05-17: Completed `M4-IMAC-001`; validation `cd packages/evidence && python3 -m pytest` passed 6 tests, `python3 -m pytest tests/acceptance` passed 6 tests, `python3 scripts/agent_control.py gate --write` and `git diff --check` passed.

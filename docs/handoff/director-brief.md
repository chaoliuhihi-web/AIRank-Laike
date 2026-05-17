# CodexMacPro Director Brief

Generated: 2026-05-17T15:33:22

## Purpose

CodexMacPro owns total direction control. It must read recent commits, evaluate CodexWin and CodexiMac work, update the launch board, and regenerate next prompts.

## Recent Commits

```text
a4de530 docs: detail low-touch hermes MVP flow
cf20229 feat: add console overview API loop
622b1f7 feat: implement console frontend prototype
9b3e83e docs: map console visuals into web implementation
e75192b chore: initialize AIRank architecture baseline
```

## Generated Next Prompts

- `docs/handoff/next-prompts/codex-win.md`
- `docs/handoff/next-prompts/codex-imac.md`
- `docs/handoff/next-prompts/codex-macpro.md`

## Required Director Loop

1. `git fetch origin && git merge --ff-only origin/main`
2. Review recent commits and changed files.
3. Run current release gate checks that are available.
4. Update `docs/handoff/review-ledger.md`.
5. Update `docs/handoff/launch-board.md` statuses and next owner.
6. Run `python3 scripts/agent_control.py director --write`.
7. Commit and push to GitHub and Gitee.

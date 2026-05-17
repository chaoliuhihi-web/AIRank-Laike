#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCH_BOARD = ROOT / "docs/handoff/launch-board.md"
EXECUTION_PACKETS = ROOT / "docs/handoff/execution-packets.md"
REVIEW_LEDGER = ROOT / "docs/handoff/review-ledger.md"
NEXT_PROMPTS = ROOT / "docs/handoff/next-prompts"
DIRECTOR_BRIEF = ROOT / "docs/handoff/director-brief.md"

AGENTS = {
    "codex-win": {
        "owner": "CodexWin",
        "role_prompt": ROOT / "agents/prompts/codex-win.md",
        "lane": "Product/API/Web",
        "default_validation": ["git diff --check", "cd apps/web && npm run build", "python3 -m pytest tests/contracts"],
    },
    "codex-imac": {
        "owner": "CodexiMac",
        "role_prompt": ROOT / "agents/prompts/codex-imac.md",
        "lane": "Data/Worker/Evidence",
        "default_validation": ["git diff --check", "cd apps/worker && pytest", "cd packages/score && pytest"],
    },
    "codex-macpro": {
        "owner": "CodexMacPro",
        "role_prompt": ROOT / "agents/prompts/codex-macpro.md",
        "lane": "Review/Release Director",
        "default_validation": ["git diff --check", "cd apps/web && npm run build", "python3 -m pytest tests/contracts"],
    },
}

ACTIONABLE_TASK_STATUSES = {"todo", "in_progress", "partial"}
OPEN_TASK_STATUSES = {"todo", "in_progress", "blocked", "partial"}
DEPENDENCY_SATISFIED_STATUSES = {"done", "review", "review_env_blocked"}
PACKET_ID_RE = re.compile(r"M\d+-[A-Z]+-\d+[A-Z]?")
TRACKED_RUNTIME_ARTIFACT_RE = re.compile(
    r"(^|/)(node_modules|dist|\.runtime)(/|$)|(^|/)\.env(\..*)?$|\.sqlite3?$|tsbuildinfo$"
)


def run(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def git_line(args: list[str]) -> str:
    _, output = run(["git", *args])
    return output.splitlines()[0] if output else ""


def tracked_runtime_artifacts() -> tuple[int, str]:
    code, output = run(["git", "ls-files"])
    if code != 0:
        return code, output
    matches = [line for line in output.splitlines() if TRACKED_RUNTIME_ARTIFACT_RE.search(line)]
    return (1 if matches else 0), "\n".join(matches)


def parse_packet_rows() -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for line in read(EXECUTION_PACKETS).splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 7 or parts[0] == "ID":
            continue
        packet_id, packet_owner, status, depends, file_scope, acceptance, validation = parts[:7]
        packet_key_match = PACKET_ID_RE.search(packet_id)
        packet_key = packet_key_match.group(0) if packet_key_match else packet_id
        tasks.append(
            {
                "task": packet_id,
                "packet_id": packet_key,
                "owner": packet_owner,
                "status": status,
                "depends": depends,
                "file_scope": file_scope,
                "exit_criteria": acceptance,
                "validation": validation,
            }
        )
    return tasks


def dependency_ids(depends: str) -> list[str]:
    return [match.group(0) for match in PACKET_ID_RE.finditer(depends)]


def dependency_state(task: dict[str, str], status_by_id: dict[str, str]) -> tuple[bool, str]:
    unmet: list[str] = []
    for packet_id in dependency_ids(task["depends"]):
        status = status_by_id.get(packet_id, "missing").lower()
        if status not in DEPENDENCY_SATISFIED_STATUSES:
            unmet.append(f"{packet_id}:{status}")
    if unmet:
        return False, ", ".join(unmet)
    return True, "ready"


def parse_tasks_from_packets(owner: str) -> list[dict[str, str]]:
    all_tasks = parse_packet_rows()
    status_by_id = {task["packet_id"]: task["status"] for task in all_tasks}
    tasks: list[dict[str, str]] = []
    for task in all_tasks:
        normalized_status = task["status"].lower()
        if task["owner"] != owner or normalized_status not in OPEN_TASK_STATUSES:
            continue
        ready, dependency_note = dependency_state(task, status_by_id)
        task = {**task, "ready": "yes" if ready else "no", "dependency_note": dependency_note}
        tasks.append(task)
    return tasks


def parse_tasks_from_launch_board(owner: str) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for line in read(LAUNCH_BOARD).splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 4 or parts[0] == "Task":
            continue
        task, task_owner, status, exit_criteria = parts[:4]
        normalized_status = status.lower()
        if task_owner != owner or normalized_status not in OPEN_TASK_STATUSES:
            continue
        tasks.append(
            {
                "task": task,
                "status": status,
                "depends": "-",
                "file_scope": "See launch board owner lane",
                "exit_criteria": exit_criteria,
                "validation": "Use role prompt validation",
                "ready": "yes",
                "dependency_note": "ready",
            }
        )
    return tasks


def parse_tasks(owner: str) -> list[dict[str, str]]:
    packet_tasks = parse_tasks_from_packets(owner)
    return packet_tasks if packet_tasks else parse_tasks_from_launch_board(owner)


def recent_review_lines() -> str:
    tail = read(REVIEW_LEDGER).splitlines()[-90:]
    important = [
        line
        for line in tail
        if any(marker in line for marker in ["BLOCKED", "PASS_WITH_RISK", "Risks:", "Next owner:", "- "])
    ]
    return "\n".join(important[-28:])


def build_next_prompt(agent_key: str) -> str:
    agent = AGENTS[agent_key]
    owner = agent["owner"]
    commit = git_line(["log", "--oneline", "-1"]) or "unknown"
    status = git_line(["status", "--short", "--branch"]) or "unknown"
    tasks = parse_tasks(owner)
    actionable_tasks = [
        task for task in tasks if task["ready"] == "yes" and task["status"].lower() in ACTIONABLE_TASK_STATUSES
    ]
    waiting_tasks = [task for task in tasks if task not in actionable_tasks]
    actionable_lines = "\n".join(
        (
            f"- [{task['status']}] {task['task']} :: depends={task['depends']} :: "
            f"files={task['file_scope']} :: exit={task['exit_criteria']} :: validate={task['validation']}"
        )
        for task in actionable_tasks[:8]
    )
    if not actionable_lines:
        actionable_lines = "- 当前没有依赖满足的可执行 task。不要硬做假实现；在 review-ledger 写清 blocker 后交回 CodexMacPro。"
    waiting_lines = "\n".join(
        (
            f"- [{task['status']}] {task['task']} :: blocked_by={task['dependency_note']} :: "
            f"depends={task['depends']}"
        )
        for task in waiting_tasks[:8]
    )
    if not waiting_lines:
        waiting_lines = "- <empty>"
    validation = "\n".join(f"- `{cmd}`" for cmd in agent["default_validation"])

    if agent_key == "codex-macpro":
        control_block = """## Director Duties

你必须先总控，不是只跑测试：

1. 阅读最新 `git log --oneline -5`、`docs/handoff/launch-board.md`、`docs/handoff/review-ledger.md`。
2. 分析 CodexWin / CodexiMac 最近提交是否偏离 v0.1 beta 主链。
3. 对每条 open task 判断：继续、降级、改 owner、阻塞。
4. 直接更新 `docs/handoff/launch-board.md` 和 `docs/handoff/review-ledger.md`。
5. 运行 `python3 scripts/agent_control.py director --write`，为三个 AI 生成下一轮自动 prompt。
6. 如果发现 blocker，写清 owner、文件、复现命令和最小修复建议。"""
    else:
        control_block = """## Execution Boundary

你不直接重新规划大方向。先读取 CodexMacPro 生成的本文件和 `docs/handoff/launch-board.md`，只领取你 owner lane 的第一条 open task。遇到方向不清、跨 lane 或 gate blocker，停止扩 scope，写入 `docs/handoff/review-ledger.md` 交回 CodexMacPro。"""

    return f"""# Auto Next Prompt - {owner}

Generated: {dt.datetime.now().isoformat(timespec="seconds")}
Repo: `/Users/bruce/Developer/work/AIRank`
Current HEAD: `{commit}`
Working tree: `{status}`
Lane: {agent["lane"]}

This prompt is generated by `scripts/agent_control.py`. Do not paste an old prompt from chat. Treat this file, `docs/handoff/execution-packets.md`, and `{agent["role_prompt"].relative_to(ROOT)}` as the current instruction source.

## Mandatory Start

```bash
cd /Users/bruce/Developer/work/AIRank
git fetch origin
git merge --ff-only origin/main
python3 scripts/agent_control.py next {agent_key} --write
```

Then read this generated file again and execute the first open task below.

{control_block}

## Actionable Tasks For This Agent

{actionable_lines}

## Waiting Or Blocked Tasks

{waiting_lines}

## Required Validation

{validation}

If a command is not applicable because that package is not initialized, write the reason in `docs/handoff/review-ledger.md`.

## Recent Review Signals

```text
{recent_review_lines() or "No review ledger signals yet."}
```

## Commit Rules

Only commit files relevant to your owner lane. After a successful commit:

```bash
git push origin main
git push gitee main
```
"""


def write_next(agent_key: str) -> Path:
    NEXT_PROMPTS.mkdir(parents=True, exist_ok=True)
    output = NEXT_PROMPTS / f"{agent_key}.md"
    output.write_text(build_next_prompt(agent_key), encoding="utf-8")
    return output


def director(write_files: bool) -> str:
    outputs = [write_next(agent_key) for agent_key in AGENTS]
    _, commit_log = run(["git", "log", "--oneline", "-5"])
    content = f"""# CodexMacPro Director Brief

Generated: {dt.datetime.now().isoformat(timespec="seconds")}

## Purpose

CodexMacPro owns total direction control. It must read recent commits, evaluate CodexWin and CodexiMac work, update the launch board, and regenerate next prompts.

## Recent Commits

```text
{commit_log}
```

## Generated Next Prompts

{chr(10).join(f"- `{path.relative_to(ROOT)}`" for path in outputs)}

## Required Director Loop

1. `git fetch origin && git merge --ff-only origin/main`
2. Review recent commits and changed files.
3. Run current release gate checks that are available.
4. Update `docs/handoff/review-ledger.md`.
5. Update `docs/handoff/launch-board.md` statuses and next owner.
6. Run `python3 scripts/agent_control.py director --write`.
7. Commit and push to GitHub and Gitee.
"""
    if write_files:
        DIRECTOR_BRIEF.write_text(content, encoding="utf-8")
    return content


def gate(write_files: bool) -> str:
    checks = [
        ("working_tree", ["git", "status", "--short", "--branch"]),
        ("diff_check", ["git", "diff", "--check"]),
    ]
    lines = ["# Agent Gate Report", "", f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}", ""]
    for name, command in checks:
        code, output = run(command)
        if name == "working_tree":
            dirty_lines = [line for line in output.splitlines() if line and not line.startswith("## ")]
            result = "PASS_WITH_CHANGES" if dirty_lines else "PASS"
        else:
            result = "PASS" if code == 0 else "BLOCKED"
        lines.extend([f"## {name}", "", f"Result: {result}", "", "```text", output or "<empty>", "```", ""])
    code, output = tracked_runtime_artifacts()
    result = "PASS" if code == 0 and output == "" else "BLOCKED"
    lines.extend(
        [
            "## tracked_runtime_artifacts",
            "",
            f"Result: {result}",
            "",
            "```text",
            output or "<empty>",
            "```",
            "",
        ]
    )
    report = "\n".join(lines)
    if write_files:
        path = ROOT / "docs/handoff/agent-gate-report.md"
        path.write_text(report, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="AIRank tri-agent control helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    next_parser = sub.add_parser("next")
    next_parser.add_argument("agent", choices=AGENTS.keys())
    next_parser.add_argument("--write", action="store_true")

    director_parser = sub.add_parser("director")
    director_parser.add_argument("--write", action="store_true")

    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("--write", action="store_true")

    args = parser.parse_args()
    if args.cmd == "next":
        if args.write:
            print(write_next(args.agent).relative_to(ROOT))
        else:
            print(build_next_prompt(args.agent))
    elif args.cmd == "director":
        print(director(args.write))
    elif args.cmd == "gate":
        print(gate(args.write))


if __name__ == "__main__":
    main()

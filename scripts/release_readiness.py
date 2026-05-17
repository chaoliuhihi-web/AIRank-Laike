#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
TRACKED_RUNTIME_ARTIFACT_RE = re.compile(
    r"(^|/)(node_modules|dist|\.runtime)(/|$)|(^|/)\.env(\..*)?$|\.sqlite3?$|tsbuildinfo$"
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    command: str
    detail: str

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def run_command(command: str, *, cwd: Path = ROOT, env: Mapping[str, str] | None = None) -> tuple[int, str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=merged_env,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode, output


def command_check(name: str, command: str, *, cwd: Path = ROOT, env: Mapping[str, str] | None = None) -> Check:
    code, output = run_command(command, cwd=cwd, env=env)
    return Check(name, "PASS" if code == 0 else "BLOCKED", command, output or "<empty>")


def working_tree_check() -> Check:
    command = "git status --short --branch"
    code, output = run_command(command)
    if code != 0:
        return Check("working tree", "BLOCKED", command, output)
    lines = [line for line in output.splitlines() if line.strip()]
    changes = [line for line in lines if not line.startswith("## ")]
    return Check(
        "working tree",
        "BLOCKED" if changes else "PASS",
        command,
        output or "<empty>",
    )


def tracked_runtime_artifact_check() -> Check:
    code, output = run_command("git ls-files")
    if code != 0:
        return Check("tracked runtime artifacts", "BLOCKED", "git ls-files", output)
    matches = [line for line in output.splitlines() if TRACKED_RUNTIME_ARTIFACT_RE.search(line)]
    return Check(
        "tracked runtime artifacts",
        "BLOCKED" if matches else "PASS",
        'git ls-files | rg "node_modules|dist|\\\\.runtime|\\\\.env|\\\\.sqlite|tsbuildinfo"',
        "\n".join(matches) if matches else "<empty>",
    )


def remote_ref_check(remote: str) -> Check:
    head_code, head = run_command("git rev-parse HEAD")
    remote_code, remote_head = run_command(f"git ls-remote {remote} refs/heads/main")
    command = f"git rev-parse HEAD && git ls-remote {remote} refs/heads/main"
    if head_code != 0 or remote_code != 0:
        return Check(f"{remote} main ref", "BLOCKED", command, (head + "\n" + remote_head).strip())
    remote_sha = remote_head.split()[0] if remote_head.split() else ""
    if head.strip() == remote_sha:
        return Check(f"{remote} main ref", "PASS", command, head.strip())
    return Check(
        f"{remote} main ref",
        "BLOCKED",
        command,
        f"local HEAD {head.strip()} does not match {remote} main {remote_sha}",
    )


def capability_records() -> tuple[dict[str, object], ...]:
    adapter_src = ROOT / "packages" / "xinghe-adapter" / "src"
    sys.path.insert(0, str(adapter_src))
    from airank_xinghe_adapter import CapabilityProbe, ProbeConfig  # noqa: PLC0415

    return tuple(result.to_record() for result in CapabilityProbe(ProbeConfig.from_env()).run())


def capability_blockers(
    records: Iterable[Mapping[str, object]],
    *,
    require_optional_capabilities: bool,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    for record in records:
        capability = str(record.get("capability", "<unknown>"))
        status = str(record.get("status", "<missing>"))
        required = bool(record.get("required_for_mvp"))
        endpoint = record.get("endpoint")
        reason = str(record.get("blocked_reason") or "")
        line = f"{capability}={status}" + (f" ({reason})" if reason else "")

        if required and status != "ready":
            blockers.append(line)
            continue
        if require_optional_capabilities and status != "ready":
            blockers.append(line)
            continue
        if endpoint and status not in {"ready"}:
            blockers.append(line)
            continue
        if status in {"dev_only", "partial", "blocked"}:
            warnings.append(line)
    return blockers, warnings


def capability_check(*, require_optional_capabilities: bool) -> Check:
    try:
        records = capability_records()
    except Exception as exc:  # pragma: no cover - defensive release-gate output
        return Check("capability probe", "BLOCKED", "CapabilityProbe(ProbeConfig.from_env()).run()", repr(exc))

    blockers, warnings = capability_blockers(
        records,
        require_optional_capabilities=require_optional_capabilities,
    )
    detail = json.dumps(records, ensure_ascii=False, indent=2)
    if warnings:
        detail += "\n\nWarnings:\n" + "\n".join(f"- {warning}" for warning in warnings)
    if blockers:
        detail += "\n\nBlockers:\n" + "\n".join(f"- {blocker}" for blocker in blockers)
    return Check(
        "capability probe",
        "BLOCKED" if blockers else "PASS",
        "CapabilityProbe(ProbeConfig.from_env()).run()",
        detail,
    )


def release_checks(*, require_optional_capabilities: bool) -> list[Check]:
    checks = [
        working_tree_check(),
        remote_ref_check("origin"),
        remote_ref_check("gitee"),
        command_check("diff check", "git diff --check"),
        tracked_runtime_artifact_check(),
        command_check("contract tests", "python3 -m pytest tests/contracts -q"),
        command_check("acceptance tests", "python3 -m pytest tests/acceptance -q"),
        command_check("worker tests", "cd apps/worker && python3 -m pytest -q"),
        command_check("score tests", "cd packages/score && python3 -m pytest -q"),
        command_check("evidence tests", "cd packages/evidence && python3 -m pytest -q"),
        command_check("xinghe adapter tests", "cd packages/xinghe-adapter && python3 -m pytest -q"),
        command_check("web build", "cd apps/web && npm run build"),
        command_check(
            "alembic offline sql",
            "cd apps/api && python3 -m alembic upgrade head --sql >/tmp/airank_release_alembic.sql",
        ),
        command_check("alembic real mysql", "cd apps/api && python3 -m alembic upgrade head"),
        capability_check(require_optional_capabilities=require_optional_capabilities),
    ]
    return checks


def render_markdown(checks: Sequence[Check]) -> str:
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    final_status = "PASS" if all(check.passed for check in checks) else "BLOCKED"
    lines = [
        "# AIRank Release Readiness Report",
        "",
        f"Generated: {generated_at}",
        f"Result: {final_status}",
        "",
        "| Check | Status | Command |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        lines.append(f"| {check.name} | {check.status} | `{check.command}` |")
    lines.append("")
    for check in checks:
        lines.extend(
            [
                f"## {check.name}",
                "",
                f"Status: {check.status}",
                "",
                "```text",
                trim_detail(check.detail),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def trim_detail(detail: str, *, max_chars: int = 6000) -> str:
    if len(detail) <= max_chars:
        return detail
    return detail[:max_chars] + "\n... <truncated>"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AIRank real release readiness gate.")
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional markdown report path to write.",
    )
    parser.add_argument(
        "--require-optional-capabilities",
        action="store_true",
        help="Require optional Xinghe/Hermes capabilities to be ready instead of MVP-only warnings.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    checks = release_checks(require_optional_capabilities=args.require_optional_capabilities)
    report = render_markdown(checks)
    if args.report:
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

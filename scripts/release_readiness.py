#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
INTERNAL_SOURCE_PATHS = (
    ROOT,
    ROOT / "apps" / "worker" / "src",
    ROOT / "packages" / "crawler-lite" / "src",
    ROOT / "packages" / "domain" / "src",
    ROOT / "packages" / "evidence" / "src",
    ROOT / "packages" / "outbound-security" / "src",
    ROOT / "packages" / "provider-gateway" / "src",
    ROOT / "packages" / "score" / "src",
    ROOT / "packages" / "skills" / "src",
    ROOT / "packages" / "xinghe-adapter" / "src",
)
for source_path in reversed(INTERNAL_SOURCE_PATHS):
    if str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))
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


DATABASE_ENV_KEYS = ("AIRANK_DATABASE_URL", "ALEMBIC_DATABASE_URL", "DATABASE_URL")
REMOTE_REF_MAX_ATTEMPTS = 3
REMOTE_REF_RETRY_DELAY_SECONDS = 1.0


def command_env(
    overrides: Mapping[str, str | None] | None = None,
    *,
    remove_database_urls: bool = False,
) -> dict[str, str]:
    merged_env = os.environ.copy()
    if remove_database_urls:
        for key in DATABASE_ENV_KEYS:
            merged_env.pop(key, None)
    if overrides:
        for key, value in overrides.items():
            if value is None:
                merged_env.pop(key, None)
            else:
                merged_env[key] = value
    return merged_env


def run_command(
    command: str,
    *,
    cwd: Path = ROOT,
    env: Mapping[str, str | None] | None = None,
    remove_database_urls: bool = False,
) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=command_env(env, remove_database_urls=remove_database_urls),
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode, output


def command_check(
    name: str,
    command: str,
    *,
    cwd: Path = ROOT,
    env: Mapping[str, str | None] | None = None,
    remove_database_urls: bool = False,
) -> Check:
    code, output = run_command(command, cwd=cwd, env=env, remove_database_urls=remove_database_urls)
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


def api_auth_configuration_check(env: Mapping[str, str] | None = None) -> Check:
    source = os.environ if env is None else env
    enforcement = source.get("AIRANK_API_AUTH_ENFORCEMENT", "").strip().lower()
    auth_mode = source.get("AIRANK_AUTH_MODE", "").strip().lower()
    blockers: list[str] = []
    if enforcement != "required":
        blockers.append(f"AIRANK_API_AUTH_ENFORCEMENT={enforcement or '<empty>'}")
    if auth_mode != "yudao":
        blockers.append(f"AIRANK_AUTH_MODE={auth_mode or '<empty>'}")
    detail = json.dumps(
        {
            "AIRANK_API_AUTH_ENFORCEMENT": enforcement,
            "AIRANK_AUTH_MODE": auth_mode,
            "required": {
                "AIRANK_API_AUTH_ENFORCEMENT": "required",
                "AIRANK_AUTH_MODE": "yudao",
            },
            "blockers": blockers,
        },
        ensure_ascii=False,
        indent=2,
    )
    return Check(
        "API authentication configuration",
        "BLOCKED" if blockers else "PASS",
        "validate AIRANK_API_AUTH_ENFORCEMENT and AIRANK_AUTH_MODE",
        detail,
    )


def production_object_storage_configuration_check(env: Mapping[str, str] | None = None) -> Check:
    source = os.environ if env is None else env
    runtime_env = source.get("AIRANK_ENV", "local").strip().lower()
    driver = source.get("AIRANK_OBJECT_STORAGE_DRIVER", "local").strip().lower()
    endpoint = source.get("AIRANK_S3_ENDPOINT_URL", "").strip()
    allow_http = source.get("AIRANK_S3_ALLOW_HTTP", "false").strip().lower() in {"1", "true", "yes", "on"}
    blockers: list[str] = []
    if runtime_env != "production":
        blockers.append(f"AIRANK_ENV={runtime_env or '<empty>'}; release requires production")
    if driver not in {"s3", "minio"}:
        blockers.append(f"AIRANK_OBJECT_STORAGE_DRIVER={driver or '<empty>'}; production requires s3/minio")
    if endpoint.startswith("http://"):
        blockers.append("AIRANK_S3_ENDPOINT_URL uses plaintext HTTP in production")
    if allow_http:
        blockers.append("AIRANK_S3_ALLOW_HTTP=true is forbidden in production")
    return Check(
        "production object storage configuration",
        "BLOCKED" if blockers else "PASS",
        "validate AIRANK_ENV and S3/MinIO transport configuration",
        json.dumps(
            {
                "AIRANK_ENV": runtime_env,
                "AIRANK_OBJECT_STORAGE_DRIVER": driver,
                "endpoint_scheme": endpoint.partition(":")[0] if endpoint else "provider-default",
                "allow_http": allow_http,
                "blockers": blockers,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def runtime_version_check(
    *,
    python_version: tuple[int, int, int] | None = None,
    node_version: str | None = None,
) -> Check:
    current_python = python_version or tuple(sys.version_info[:3])
    node_command_output = node_version
    node_error = ""
    if node_command_output is None:
        node_code, node_command_output = run_command("node --version")
        if node_code != 0:
            node_error = node_command_output or "node executable is unavailable"
            node_command_output = ""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (node_command_output or "").strip())
    parsed_node = tuple(int(part) for part in match.groups()) if match else None
    node_supported = bool(
        parsed_node
        and (
            (parsed_node[0] == 20 and parsed_node >= (20, 19, 0))
            or (parsed_node[0] >= 22 and (parsed_node[0] > 22 or parsed_node >= (22, 12, 0)))
        )
    )
    blockers: list[str] = []
    if current_python < (3, 11, 0):
        blockers.append(f"Python {'.'.join(map(str, current_python))}; production requires 3.11+")
    if not node_supported:
        blockers.append(
            node_error
            or f"Node {(node_command_output or '<unavailable>').strip()}; Vite requires 20.19+ or 22.12+"
        )
    return Check(
        "runtime versions",
        "BLOCKED" if blockers else "PASS",
        "validate Python and Node production runtime versions",
        json.dumps(
            {
                "python": ".".join(map(str, current_python)),
                "node": (node_command_output or "<unavailable>").strip(),
                "required": {"python": "3.11+", "node": "20.19+ or 22.12+"},
                "blockers": blockers,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def remote_ref_check(
    remote: str,
    *,
    attempts: int = REMOTE_REF_MAX_ATTEMPTS,
    retry_delay_seconds: float = REMOTE_REF_RETRY_DELAY_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
) -> Check:
    head_code, head = run_command("git rev-parse HEAD")
    maximum_attempts = max(1, attempts)
    remote_code = 1
    remote_head = ""
    attempt_records: list[str] = []
    successful_attempt = 0
    for attempt in range(1, maximum_attempts + 1):
        remote_code, remote_head = run_command(
            f"git ls-remote {remote} refs/heads/main"
        )
        if remote_code == 0:
            successful_attempt = attempt
            break
        attempt_records.append(
            f"remote query attempt {attempt}/{maximum_attempts}:\n"
            f"{remote_head or '<empty>'}"
        )
        if attempt < maximum_attempts:
            sleeper(max(0.0, retry_delay_seconds) * attempt)
    command = (
        f"git rev-parse HEAD && git ls-remote {remote} refs/heads/main "
        f"(up to {maximum_attempts} attempts)"
    )
    if head_code != 0 or remote_code != 0:
        detail_parts = [head] if head else []
        detail_parts.extend(attempt_records)
        return Check(
            f"{remote} main ref",
            "BLOCKED",
            command,
            "\n\n".join(detail_parts).strip(),
        )
    remote_sha = remote_head.split()[0] if remote_head.split() else ""
    if head.strip() == remote_sha:
        detail = head.strip()
        if successful_attempt > 1:
            detail += (
                f"\nremote query succeeded on attempt "
                f"{successful_attempt}/{maximum_attempts}"
            )
        return Check(f"{remote} main ref", "PASS", command, detail)
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


def browser_provider_blockers(
    records: Iterable[Mapping[str, object]],
    *,
    mode: str,
    minimum_success_count: int,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    record_list = list(records)
    ready_count = sum(1 for record in record_list if record.get("status") == "ready")

    if mode != "browser":
        blockers.append(f"AIRANK_PROVIDER_MODE={mode}; production ranking requires browser")
    if ready_count < minimum_success_count:
        blockers.append(f"browser_provider_ready={ready_count}/{minimum_success_count}")

    for record in record_list:
        if record.get("status") != "ready":
            provider = str(record.get("provider", "<unknown>"))
            reason = str(record.get("reason") or "blocked")
            warnings.append(f"{provider}=blocked ({reason})")
    return blockers, warnings


def browser_provider_readiness_check() -> Check:
    command = "probe_provider_generation_readiness(DEFAULT_PROVIDER_SCOPE)"
    try:
        from apps.api.main import DEFAULT_PROVIDER_SCOPE, minimum_provider_success_count  # noqa: PLC0415
        from apps.api.provider_scan import probe_provider_generation_readiness, provider_execution_mode  # noqa: PLC0415

        mode = provider_execution_mode()
        minimum_success_count = minimum_provider_success_count(DEFAULT_PROVIDER_SCOPE)
        records = [asdict(probe_provider_generation_readiness(provider)) for provider in DEFAULT_PROVIDER_SCOPE]
    except Exception as exc:  # pragma: no cover - defensive release-gate output
        return Check("browser provider readiness", "BLOCKED", command, repr(exc))

    blockers, warnings = browser_provider_blockers(
        records,
        mode=mode,
        minimum_success_count=minimum_success_count,
    )
    detail = json.dumps(
        {
            "mode": mode,
            "minimum_success_count": minimum_success_count,
            "providers": records,
        },
        ensure_ascii=False,
        indent=2,
    )
    if warnings:
        detail += "\n\nWarnings:\n" + "\n".join(f"- {warning}" for warning in warnings)
    if blockers:
        detail += "\n\nBlockers:\n" + "\n".join(f"- {blocker}" for blocker in blockers)
    return Check(
        "browser provider readiness",
        "BLOCKED" if blockers else "PASS",
        command,
        detail,
    )


def provider_model_lifecycle_check(database_url: str | None) -> Check:
    command = "python3 scripts/check_provider_model_lifecycle.py"
    if not database_url:
        return Check(
            "provider model lifecycle",
            "BLOCKED",
            command,
            "No release database URL is configured; persisted Provider model lifecycle cannot be verified.",
        )
    code, detail = run_command(
        command,
        env={"AIRANK_DATABASE_URL": database_url},
    )
    return Check(
        "provider model lifecycle",
        "PASS" if code == 0 else "BLOCKED",
        command,
        detail or "<empty>",
    )


def release_database_url(explicit_database_url: str | None = None) -> str | None:
    return (
        explicit_database_url
        or os.getenv("AIRANK_RELEASE_DATABASE_URL")
        or os.getenv("AIRANK_DATABASE_URL")
        or os.getenv("ALEMBIC_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )


def release_checks(
    *,
    require_optional_capabilities: bool,
    require_browser_providers: bool,
    database_url: str | None = None,
) -> list[Check]:
    db_url = release_database_url(database_url)
    real_mysql_env = {"AIRANK_DATABASE_URL": db_url} if db_url else None
    real_integration_env = {"AIRANK_RUN_REAL_MYSQL": "1", "AIRANK_DATABASE_URL": db_url} if db_url else None
    if real_integration_env and os.getenv("YUDAO_USERNAME") and os.getenv("YUDAO_PASSWORD"):
        real_integration_env["AIRANK_RUN_REAL_YUDAO"] = "1"
    checks = [
        working_tree_check(),
        remote_ref_check("origin"),
        remote_ref_check("gitee"),
        command_check("diff check", "git diff --check"),
        tracked_runtime_artifact_check(),
        api_auth_configuration_check(),
        production_object_storage_configuration_check(),
        runtime_version_check(),
        command_check("contract tests", "python3 -m pytest tests/contracts -q", remove_database_urls=True),
        command_check(
            "crawler lite tests",
            "python3 -m pytest packages/crawler-lite/tests -q",
            remove_database_urls=True,
        ),
        command_check("acceptance tests", "python3 -m pytest tests/acceptance -q", remove_database_urls=True),
        command_check(
            "scheduler tests",
            "python3 -m pytest apps/scheduler/tests -q",
            remove_database_urls=True,
        ),
        command_check("worker tests", "cd apps/worker && python3 -m pytest -q", remove_database_urls=True),
        command_check("score tests", "cd packages/score && python3 -m pytest -q", remove_database_urls=True),
        command_check("evidence tests", "cd packages/evidence && python3 -m pytest -q", remove_database_urls=True),
        command_check(
            "outbound security tests",
            "python3 -m pytest packages/outbound-security/tests -q",
            remove_database_urls=True,
        ),
        command_check(
            "provider gateway tests",
            "python3 -m pytest packages/provider-gateway/tests -q",
            remove_database_urls=True,
        ),
        command_check(
            "provider citation benchmark",
            "python3 scripts/evaluate_provider_citations.py",
            remove_database_urls=True,
        ),
        command_check("core skill evaluation", "python3 scripts/evaluate_core_skills.py", remove_database_urls=True),
        command_check("skill trust gate", "python3 scripts/audit_skill_trust.py", remove_database_urls=True),
        command_check(
            "xinghe adapter tests",
            "cd packages/xinghe-adapter && python3 -m pytest -q",
            remove_database_urls=True,
        ),
        command_check("web build", "cd apps/web && npm run build"),
        command_check("real integration tests", "python3 -m pytest tests/integration -q", env=real_integration_env),
        command_check(
            "alembic offline sql",
            "cd apps/api && python3 -m alembic upgrade head --sql >/tmp/airank_release_alembic.sql",
            env=real_mysql_env,
        ),
        command_check("alembic real mysql", "cd apps/api && python3 -m alembic upgrade head", env=real_mysql_env),
        provider_model_lifecycle_check(db_url),
        capability_check(require_optional_capabilities=require_optional_capabilities),
    ]
    if require_browser_providers:
        checks.append(browser_provider_readiness_check())
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
    normalized = "\n".join(line.rstrip() for line in detail.splitlines())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "\n... <truncated>"


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
    parser.add_argument(
        "--require-browser-providers",
        action="store_true",
        help="Require consumer web AI provider browser profiles to be ready for production ranking.",
    )
    parser.add_argument(
        "--database-url",
        help=(
            "Database URL for the real Alembic migration gate. Defaults to "
            "AIRANK_RELEASE_DATABASE_URL, then AIRANK_DATABASE_URL/ALEMBIC_DATABASE_URL/DATABASE_URL."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    checks = release_checks(
        require_optional_capabilities=args.require_optional_capabilities,
        require_browser_providers=args.require_browser_providers,
        database_url=args.database_url,
    )
    report = render_markdown(checks)
    if args.report:
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

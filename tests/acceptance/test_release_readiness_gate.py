from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import release_readiness  # noqa: E402
from release_readiness import capability_blockers  # noqa: E402


def test_release_readiness_blocks_required_dev_only_capabilities() -> None:
    blockers, warnings = capability_blockers(
        [
            {
                "capability": "yudao_auth",
                "status": "dev_only",
                "required_for_mvp": True,
                "blocked_reason": "AIRANK_AUTH_MODE=dev",
            },
            {
                "capability": "xinghe_hermes",
                "status": "dev_only",
                "required_for_mvp": False,
                "blocked_reason": "not configured",
            },
        ],
        require_optional_capabilities=False,
    )

    assert blockers == ["yudao_auth=dev_only (AIRANK_AUTH_MODE=dev)"]
    assert warnings == ["xinghe_hermes=dev_only (not configured)"]


def test_release_readiness_blocks_configured_optional_probe_failures() -> None:
    blockers, warnings = capability_blockers(
        [
            {
                "capability": "xinghe_hermes",
                "status": "partial",
                "required_for_mvp": False,
                "endpoint": "https://hermes.example.test/health",
                "blocked_reason": "HTTP 503",
            },
        ],
        require_optional_capabilities=False,
    )

    assert blockers == ["xinghe_hermes=partial (HTTP 503)"]
    assert warnings == []


def test_release_readiness_can_require_all_optional_capabilities() -> None:
    blockers, warnings = capability_blockers(
        [
            {
                "capability": "xinghe_crawler_gateway",
                "status": "dev_only",
                "required_for_mvp": False,
                "blocked_reason": "not configured",
            },
        ],
        require_optional_capabilities=True,
    )

    assert blockers == ["xinghe_crawler_gateway=dev_only (not configured)"]
    assert warnings == []


def test_browser_provider_gate_blocks_non_browser_mode() -> None:
    blockers, warnings = release_readiness.browser_provider_blockers(
        [{"provider": "chatgpt", "status": "ready"}],
        mode="mock",
        minimum_success_count=1,
    )

    assert blockers == ["AIRANK_PROVIDER_MODE=mock; production ranking requires browser"]
    assert warnings == []


def test_browser_provider_gate_blocks_below_minimum_ready_count() -> None:
    blockers, warnings = release_readiness.browser_provider_blockers(
        [
            {"provider": "chatgpt", "status": "ready"},
            {"provider": "deepseek", "status": "blocked", "reason": "login required"},
        ],
        mode="browser",
        minimum_success_count=2,
    )

    assert blockers == ["browser_provider_ready=1/2"]
    assert warnings == ["deepseek=blocked (login required)"]


def test_working_tree_check_fails_when_untracked_files_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: str, **kwargs: object) -> tuple[int, str]:
        assert command == "git status --short --branch"
        return 0, "## main...origin/main\n?? local.tmp"

    monkeypatch.setattr(release_readiness, "run_command", fake_run)

    check = release_readiness.working_tree_check()

    assert check.status == "BLOCKED"
    assert "?? local.tmp" in check.detail


def test_command_env_can_isolate_database_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRANK_DATABASE_URL", "mysql+pymysql://example")
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "mysql+pymysql://example")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://example")

    env = release_readiness.command_env(remove_database_urls=True)

    assert "AIRANK_DATABASE_URL" not in env
    assert "ALEMBIC_DATABASE_URL" not in env
    assert "DATABASE_URL" not in env


def test_release_checks_can_append_browser_provider_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_check() -> release_readiness.Check:
        return release_readiness.Check("browser provider readiness", "PASS", "fake", "ready")

    monkeypatch.setattr(release_readiness, "working_tree_check", lambda: release_readiness.Check("working tree", "PASS", "fake", "clean"))
    monkeypatch.setattr(release_readiness, "remote_ref_check", lambda remote: release_readiness.Check(f"{remote} main ref", "PASS", "fake", "ok"))
    monkeypatch.setattr(release_readiness, "command_check", lambda name, command, **kwargs: release_readiness.Check(name, "PASS", command, "ok"))
    monkeypatch.setattr(release_readiness, "tracked_runtime_artifact_check", lambda: release_readiness.Check("tracked runtime artifacts", "PASS", "fake", "ok"))
    monkeypatch.setattr(release_readiness, "capability_check", lambda **kwargs: release_readiness.Check("capability probe", "PASS", "fake", "ok"))
    monkeypatch.setattr(release_readiness, "browser_provider_readiness_check", fake_check)

    checks = release_readiness.release_checks(require_optional_capabilities=False, require_browser_providers=True)

    assert checks[-1].name == "browser provider readiness"

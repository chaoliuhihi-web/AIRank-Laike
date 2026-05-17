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

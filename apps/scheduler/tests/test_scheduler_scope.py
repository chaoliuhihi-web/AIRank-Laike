from __future__ import annotations

import argparse

import pytest

from airank_scheduler.main import resolve_scope


def args(**overrides: object) -> argparse.Namespace:
    values = {
        "tenant_id": None,
        "project_id": None,
        "window_id": None,
        "allow_global_scope": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_scheduler_scope_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="SCHEDULER_SCOPE_REQUIRED"):
        resolve_scope(args(), {})


def test_scheduler_project_requires_tenant() -> None:
    with pytest.raises(ValueError, match="SCHEDULER_TENANT_SCOPE_REQUIRED"):
        resolve_scope(args(project_id="project_1"), {})


def test_scheduler_global_scope_requires_double_opt_in() -> None:
    with pytest.raises(ValueError, match="SCHEDULER_SCOPE_REQUIRED"):
        resolve_scope(args(allow_global_scope=True), {})

    scope = resolve_scope(
        args(allow_global_scope=True),
        {"AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED": "true"},
    )
    assert scope == (None, None, None, True)

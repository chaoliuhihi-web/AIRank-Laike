from __future__ import annotations

import argparse

import pytest

from airank_worker.main import WorkerScopeError, resolve_worker_scope


def args(**overrides: object) -> argparse.Namespace:
    values = {
        "tenant_id": None,
        "project_id": None,
        "job_id": None,
        "allow_global_scope": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_worker_requires_explicit_scope_by_default() -> None:
    with pytest.raises(WorkerScopeError) as exc_info:
        resolve_worker_scope(args(), {})

    assert exc_info.value.code == "WORKER_SCOPE_REQUIRED"


def test_project_scope_requires_tenant_scope() -> None:
    with pytest.raises(WorkerScopeError) as exc_info:
        resolve_worker_scope(args(project_id="project_1"), {})

    assert exc_info.value.code == "WORKER_TENANT_SCOPE_REQUIRED"


def test_scope_can_come_from_private_process_environment() -> None:
    scope = resolve_worker_scope(
        args(),
        {
            "AIRANK_WORKER_TENANT_ID": "tenant_1",
            "AIRANK_WORKER_PROJECT_ID": "project_1",
        },
    )

    assert scope.tenant_id == "tenant_1"
    assert scope.project_id == "project_1"
    assert scope.global_scope is False


def test_global_scope_requires_double_opt_in() -> None:
    with pytest.raises(WorkerScopeError):
        resolve_worker_scope(args(allow_global_scope=True), {})

    scope = resolve_worker_scope(
        args(allow_global_scope=True),
        {"AIRANK_WORKER_GLOBAL_SCOPE_ENABLED": "true"},
    )

    assert scope.global_scope is True


def test_global_scope_cannot_be_combined_with_target_scope() -> None:
    with pytest.raises(WorkerScopeError) as exc_info:
        resolve_worker_scope(
            args(tenant_id="tenant_1", allow_global_scope=True),
            {"AIRANK_WORKER_GLOBAL_SCOPE_ENABLED": "true"},
        )

    assert exc_info.value.code == "WORKER_SCOPE_CONFLICT"

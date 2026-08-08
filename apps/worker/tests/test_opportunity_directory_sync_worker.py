from __future__ import annotations

from datetime import datetime, timezone

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import AsyncJob
from airank_worker import InMemoryJobLeaseStore
from airank_worker.opportunity_directory_sync import (
    SYNC_CONTRACT_VERSION,
    OpportunityDirectorySyncWorkerError,
    run_next_opportunity_directory_sync_job,
)
from apps.api.opportunity_directory_routes import (
    OpportunityActionDirectoryBindingData,
    OpportunityActionDirectoryData,
    OpportunityActionDirectorySyncRunData,
)


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
BINDING_ID = "opportunity_action_sync_binding_" + "b" * 20
TEAM_ID = "opportunity_action_team_" + "a" * 20


def state(*, version: int = 3, with_run: bool = False) -> OpportunityActionDirectoryData:
    run_id = "opportunity_action_sync_run_" + "c" * 20 if with_run else None
    runs = []
    if run_id:
        runs.append(
            OpportunityActionDirectorySyncRunData(
                run_id=run_id,
                binding_id=BINDING_ID,
                binding_version=version,
                team_id=TEAM_ID,
                external_group_id="42",
                status="succeeded",
                endpoint_host="yudao.example.com",
                response_sha256="d" * 64,
                discovered_member_count=2,
                active_member_count=1,
                created_member_count=1,
                updated_member_count=0,
                unchanged_member_count=0,
                disabled_member_count=0,
                manual_conflict_count=1,
                error_code=None,
                retryable=False,
                started_at=NOW,
                finished_at=NOW,
            )
        )
    return OpportunityActionDirectoryData(
        project_id="project_1",
        contract_version=SYNC_CONTRACT_VERSION,
        bindings=[
            OpportunityActionDirectoryBindingData(
                binding_id=BINDING_ID,
                team_id=TEAM_ID,
                team_name="GEO 交付组",
                external_source="yudao",
                external_group_id="42",
                status="active",
                sync_enabled=True,
                sync_interval_minutes=60,
                default_priority=100,
                default_max_active_actions=5,
                default_receives_escalations=True,
                last_sync_state="verified" if with_run else "pending",
                last_sync_run_id=run_id,
                last_synced_at=NOW if with_run else None,
                next_sync_at=NOW,
                last_error_code=None,
                version=version,
                updated_at=NOW,
            )
        ],
        recent_sync_runs=runs,
        configured_team_count=1,
        verified_team_count=1 if with_run else 0,
        known_limitations=[],
    )


class FakeRepository:
    def __init__(self, *, version: int = 3, fail: bool = False) -> None:
        self.version = version
        self.fail = fail

    def get_state(self, tenant_id, project_id, *, replay_run_id=None):  # noqa: ANN001
        return state(version=self.version)

    def run_sync(self, tenant_id, project_id, team_id, idempotency_key, actor, trace_id, client):  # noqa: ANN001
        if self.fail:
            raise StarletteHTTPException(
                503,
                detail={
                    "code": "OPPORTUNITY_ACTION_DIRECTORY_SYNC_FAILED",
                    "details": {"retryable": True},
                },
            )
        return state(version=self.version, with_run=True)


def job(*, version: int = 3) -> AsyncJob:
    return AsyncJob(
        id="job_opportunity_directory_1",
        tenant_id="tenant_1",
        project_id="project_1",
        job_type="opportunity.directory.sync",
        scheduled_at=NOW,
        max_attempts=1,
        payload={
            "contract_version": SYNC_CONTRACT_VERSION,
            "binding_id": BINDING_ID,
            "binding_version": version,
            "team_id": TEAM_ID,
            "external_group_id": "42",
            "idempotency_key": "scheduled:binding:2026-08-09T12:00:00Z",
            "requested_by": "scheduler-test",
        },
    )


def test_worker_completes_governed_directory_job() -> None:
    queued = job()
    store = InMemoryJobLeaseStore([queued])
    outcome = run_next_opportunity_directory_sync_job(
        store,
        FakeRepository(),
        object(),  # type: ignore[arg-type]
        worker_id="opportunity-directory-worker",
        now=NOW,
    )
    assert outcome is not None
    assert outcome.status == "succeeded"
    assert outcome.created_member_count == 1
    assert outcome.manual_conflict_count == 1
    assert outcome.response_sha256 == "d" * 64
    assert store.get(queued.id).status.value == "succeeded"


def test_worker_fails_closed_when_binding_version_changed() -> None:
    queued = job(version=3)
    store = InMemoryJobLeaseStore([queued])
    with pytest.raises(OpportunityDirectorySyncWorkerError) as captured:
        run_next_opportunity_directory_sync_job(
            store,
            FakeRepository(version=4),
            object(),  # type: ignore[arg-type]
            worker_id="opportunity-directory-worker",
            now=NOW,
        )
    assert captured.value.code == "OPPORTUNITY_DIRECTORY_SYNC_BINDING_CHANGED"
    assert store.get(queued.id).status.value == "failed"


def test_worker_preserves_retryable_sync_failure() -> None:
    queued = job()
    store = InMemoryJobLeaseStore([queued])
    with pytest.raises(OpportunityDirectorySyncWorkerError) as captured:
        run_next_opportunity_directory_sync_job(
            store,
            FakeRepository(fail=True),
            object(),  # type: ignore[arg-type]
            worker_id="opportunity-directory-worker",
            now=NOW,
        )
    assert captured.value.code == "OPPORTUNITY_ACTION_DIRECTORY_SYNC_FAILED"
    assert captured.value.retryable is True
    assert store.get(queued.id).status.value == "failed"

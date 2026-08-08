from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_domain import AsyncJob
from airank_worker import InMemoryJobLeaseStore
from airank_worker.reviewer_directory_sync import (
    SYNC_CONTRACT_VERSION,
    ReviewerDirectorySyncWorkerError,
    run_next_reviewer_directory_sync_job,
)
from airank_xinghe_adapter import (
    YudaoDirectoryError,
    YudaoReviewer,
    YudaoReviewerDirectorySnapshot,
)
from apps.api.reviewer_routing_routes import (
    InMemoryReviewerRoutingRepository,
    ReviewerDirectoryBindingPutRequest,
    ReviewerTeamCreateRequest,
)


NOW = datetime(2026, 8, 9, 10, 30, tzinfo=timezone.utc)


def configured_repository() -> tuple[InMemoryReviewerRoutingRepository, str, int]:
    repository = InMemoryReviewerRoutingRepository()
    routing = repository.create_team(
        "tenant_1",
        "project_1",
        ReviewerTeamCreateRequest(name="Evidence reviewers"),
        "worker-directory-team",
        "review-admin",
        "trace-team",
    )
    team_id = routing.teams[0].team_id
    routing = repository.put_sync_binding(
        "tenant_1",
        "project_1",
        team_id,
        "secondary",
        ReviewerDirectoryBindingPutRequest(external_group_id="42"),
        "review-admin",
        "trace-binding",
    )
    return repository, team_id, routing.sync_bindings[0].version


def build_job(team_id: str, binding_id: str, binding_version: int) -> AsyncJob:
    return AsyncJob(
        id="job_reviewer_directory_1",
        tenant_id="tenant_1",
        project_id="project_1",
        job_type="reviewer.directory.sync",
        scheduled_at=NOW,
        max_attempts=1,
        payload={
            "contract_version": SYNC_CONTRACT_VERSION,
            "binding_id": binding_id,
            "binding_version": binding_version,
            "team_id": team_id,
            "reviewer_role": "secondary",
            "external_group_id": "42",
            "idempotency_key": "scheduled:binding:2026-08-09T10:30:00Z",
            "requested_by": "scheduler-test",
        },
    )


class SuccessfulDirectoryClient:
    @staticmethod
    def fetch_department(department_id: str) -> YudaoReviewerDirectorySnapshot:
        assert department_id == "42"
        return YudaoReviewerDirectorySnapshot(
            department_id="42",
            department_name="Evidence reviewers",
            members=(
                YudaoReviewer("reviewer-2", "reviewer.two", "Reviewer Two", "42", True),
            ),
            response_sha256="d" * 64,
            endpoint_host="yudao.example.com",
        )


class FailingDirectoryClient:
    @staticmethod
    def fetch_department(department_id: str) -> YudaoReviewerDirectorySnapshot:
        raise YudaoDirectoryError(
            "YUDAO_REVIEW_DIRECTORY_NETWORK_FAILED",
            "upstream unavailable",
            retryable=True,
        )


def test_worker_syncs_verified_members_and_completes_job() -> None:
    repository, team_id, binding_version = configured_repository()
    routing = repository.get_routing("tenant_1", "project_1")
    job = build_job(team_id, routing.sync_bindings[0].binding_id, binding_version)
    store = InMemoryJobLeaseStore([job])

    outcome = run_next_reviewer_directory_sync_job(
        store,
        repository,
        SuccessfulDirectoryClient(),  # type: ignore[arg-type]
        worker_id="directory-worker",
        now=NOW,
    )

    assert outcome is not None
    assert outcome.status == "succeeded"
    assert outcome.active_member_count == 1
    assert outcome.response_sha256 == "d" * 64
    assert store.get(job.id).status.value == "succeeded"
    member = repository.get_routing("tenant_1", "project_1").teams[0].members[0]
    assert member.membership_source == "yudao"
    assert member.external_membership_verified is True


def test_worker_fails_closed_when_binding_changed_after_dispatch() -> None:
    repository, team_id, binding_version = configured_repository()
    routing = repository.get_routing("tenant_1", "project_1")
    job = build_job(team_id, routing.sync_bindings[0].binding_id, binding_version)
    repository.put_sync_binding(
        "tenant_1",
        "project_1",
        team_id,
        "secondary",
        ReviewerDirectoryBindingPutRequest(
            external_group_id="99", expected_version=binding_version
        ),
        "review-admin",
        "trace-binding-change",
    )
    store = InMemoryJobLeaseStore([job])

    with pytest.raises(ReviewerDirectorySyncWorkerError) as captured:
        run_next_reviewer_directory_sync_job(
            store,
            repository,
            SuccessfulDirectoryClient(),  # type: ignore[arg-type]
            worker_id="directory-worker",
            now=NOW,
        )

    assert captured.value.code == "REVIEWER_DIRECTORY_SYNC_BINDING_CHANGED"
    assert store.get(job.id).status.value == "failed"


def test_worker_preserves_truthful_retryable_upstream_failure() -> None:
    repository, team_id, binding_version = configured_repository()
    routing = repository.get_routing("tenant_1", "project_1")
    job = build_job(team_id, routing.sync_bindings[0].binding_id, binding_version)
    store = InMemoryJobLeaseStore([job])

    with pytest.raises(ReviewerDirectorySyncWorkerError) as captured:
        run_next_reviewer_directory_sync_job(
            store,
            repository,
            FailingDirectoryClient(),  # type: ignore[arg-type]
            worker_id="directory-worker",
            now=NOW,
        )

    assert captured.value.code == "EVIDENCE_REVIEW_YUDAO_SYNC_FAILED"
    assert captured.value.retryable is True
    assert store.get(job.id).status.value == "failed"
    failed_run = repository.get_routing("tenant_1", "project_1").recent_sync_runs[0]
    assert failed_run.status == "failed"
    assert failed_run.error_code == "YUDAO_REVIEW_DIRECTORY_NETWORK_FAILED"

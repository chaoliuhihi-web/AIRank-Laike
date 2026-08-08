from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol

from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import AsyncJob
from airank_xinghe_adapter import YudaoReviewerDirectoryClient as YudaoDirectoryClient
from apps.api.opportunity_directory_routes import (
    MySQLOpportunityActionDirectoryRepository,
    OpportunityActionDirectoryData,
)

from .lease import InMemoryJobLeaseStore, MySQLJobLeaseStore


SYNC_CONTRACT_VERSION = "airank.opportunity-action-directory-sync.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityDirectorySyncWorkerError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class OpportunityDirectorySyncRepository(Protocol):
    def get_state(
        self,
        tenant_id: str,
        project_id: str,
        *,
        replay_run_id: str | None = None,
    ) -> OpportunityActionDirectoryData: ...

    def run_sync(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        idempotency_key: str,
        actor: str,
        trace_id: str,
        directory_client: YudaoDirectoryClient,
    ) -> OpportunityActionDirectoryData: ...


@dataclass(frozen=True)
class OpportunityDirectorySyncOutcome:
    binding_id: str
    run_id: str
    team_id: str
    status: str
    active_member_count: int
    created_member_count: int
    updated_member_count: int
    unchanged_member_count: int
    disabled_member_count: int
    manual_conflict_count: int
    response_sha256: str | None
    idempotent_replay: bool

    def to_record(self) -> dict[str, object]:
        return asdict(self)


def build_opportunity_directory_sync_repository(
    database_url: str,
) -> MySQLOpportunityActionDirectoryRepository:
    return MySQLOpportunityActionDirectoryRepository(database_url)


def run_next_opportunity_directory_sync_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: OpportunityDirectorySyncRepository,
    directory_client: YudaoDirectoryClient,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> OpportunityDirectorySyncOutcome | None:
    started_at = now or utc_now()
    job = store.claim_next(
        worker_id, started_at, job_types={"opportunity.directory.sync"}
    )
    if job is None:
        return None
    return run_claimed_opportunity_directory_sync_job(
        store,
        repository,
        directory_client,
        job=job,
        worker_id=worker_id,
    )


def run_claimed_opportunity_directory_sync_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: OpportunityDirectorySyncRepository,
    directory_client: YudaoDirectoryClient,
    *,
    job: AsyncJob,
    worker_id: str,
) -> OpportunityDirectorySyncOutcome:
    payload = job.payload if isinstance(job.payload, dict) else {}
    required = (
        "binding_id",
        "binding_version",
        "team_id",
        "external_group_id",
        "idempotency_key",
    )
    try:
        binding_version = int(payload.get("binding_version"))
    except (TypeError, ValueError):
        binding_version = 0
    if (
        str(payload.get("contract_version") or "") != SYNC_CONTRACT_VERSION
        or any(not str(payload.get(field) or "").strip() for field in required)
        or binding_version < 1
        or not job.project_id
    ):
        worker_error = OpportunityDirectorySyncWorkerError(
            "OPPORTUNITY_DIRECTORY_SYNC_JOB_INVALID",
            "opportunity directory sync job payload is invalid",
        )
        store.fail(job.id, worker_id, utc_now(), worker_error.code, worker_error.message)
        raise worker_error

    state = repository.get_state(job.tenant_id, job.project_id)
    binding = next(
        (
            item
            for item in state.bindings
            if item.binding_id == str(payload["binding_id"])
        ),
        None,
    )
    if (
        binding is None
        or binding.team_id != str(payload["team_id"])
        or binding.external_group_id != str(payload["external_group_id"])
        or binding.version != binding_version
        or binding.status != "active"
        or not binding.sync_enabled
    ):
        worker_error = OpportunityDirectorySyncWorkerError(
            "OPPORTUNITY_DIRECTORY_SYNC_BINDING_CHANGED",
            "opportunity directory binding changed after dispatch",
        )
        store.fail(job.id, worker_id, utc_now(), worker_error.code, worker_error.message)
        raise worker_error

    try:
        result = repository.run_sync(
            job.tenant_id,
            job.project_id,
            binding.team_id,
            str(payload["idempotency_key"]),
            str(payload.get("requested_by") or worker_id),
            f"worker:{job.id}",
            directory_client,
        )
    except StarletteHTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        details = detail.get("details") if isinstance(detail.get("details"), dict) else {}
        worker_error = OpportunityDirectorySyncWorkerError(
            str(detail.get("code") or "OPPORTUNITY_DIRECTORY_SYNC_FAILED"),
            "opportunity directory synchronization failed",
            retryable=bool(details.get("retryable")),
        )
        store.fail(job.id, worker_id, utc_now(), worker_error.code, worker_error.message)
        raise worker_error from exc

    completed_binding = next(
        item for item in result.bindings if item.binding_id == binding.binding_id
    )
    run_id = str(completed_binding.last_sync_run_id or "")
    run = next((item for item in result.recent_sync_runs if item.run_id == run_id), None)
    if run is None or run.status != "succeeded":
        worker_error = OpportunityDirectorySyncWorkerError(
            "OPPORTUNITY_DIRECTORY_SYNC_RESULT_INVALID",
            "opportunity directory synchronization did not return a completed run",
        )
        store.fail(job.id, worker_id, utc_now(), worker_error.code, worker_error.message)
        raise worker_error
    outcome = OpportunityDirectorySyncOutcome(
        binding_id=binding.binding_id,
        run_id=run.run_id,
        team_id=binding.team_id,
        status=run.status,
        active_member_count=run.active_member_count,
        created_member_count=run.created_member_count,
        updated_member_count=run.updated_member_count,
        unchanged_member_count=run.unchanged_member_count,
        disabled_member_count=run.disabled_member_count,
        manual_conflict_count=run.manual_conflict_count,
        response_sha256=run.response_sha256,
        idempotent_replay=run.idempotent_replay,
    )
    store.succeed(job.id, worker_id, utc_now(), outcome.to_record())
    return outcome

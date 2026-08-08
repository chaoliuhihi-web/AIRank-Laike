from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol

from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_domain import AsyncJob
from airank_xinghe_adapter import YudaoReviewerDirectoryClient
from apps.api.reviewer_routing_routes import (
    MySQLReviewerRoutingRepository,
    ReviewerRoutingData,
)

from .lease import InMemoryJobLeaseStore, MySQLJobLeaseStore


SYNC_CONTRACT_VERSION = "airank.reviewer-directory-sync.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewerDirectorySyncWorkerError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ReviewerDirectorySyncRepository(Protocol):
    def get_routing(self, tenant_id: str, project_id: str) -> ReviewerRoutingData: ...

    def run_directory_sync(
        self,
        tenant_id: str,
        project_id: str,
        team_id: str,
        reviewer_role: str,
        idempotency_key: str,
        actor: str,
        trace_id: str,
        directory_client: YudaoReviewerDirectoryClient,
    ) -> ReviewerRoutingData: ...


@dataclass(frozen=True)
class ReviewerDirectorySyncOutcome:
    binding_id: str
    run_id: str
    team_id: str
    reviewer_role: str
    status: str
    active_member_count: int
    upserted_member_count: int
    disabled_member_count: int
    response_sha256: str | None
    idempotent_replay: bool

    def to_record(self) -> dict[str, object]:
        return asdict(self)


def build_reviewer_directory_sync_repository(
    database_url: str,
) -> MySQLReviewerRoutingRepository:
    return MySQLReviewerRoutingRepository(database_url)


def run_next_reviewer_directory_sync_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: ReviewerDirectorySyncRepository,
    directory_client: YudaoReviewerDirectoryClient,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> ReviewerDirectorySyncOutcome | None:
    started_at = now or utc_now()
    job = store.claim_next(
        worker_id, started_at, job_types={"reviewer.directory.sync"}
    )
    if job is None:
        return None
    return run_claimed_reviewer_directory_sync_job(
        store,
        repository,
        directory_client,
        job=job,
        worker_id=worker_id,
    )


def run_claimed_reviewer_directory_sync_job(
    store: MySQLJobLeaseStore | InMemoryJobLeaseStore,
    repository: ReviewerDirectorySyncRepository,
    directory_client: YudaoReviewerDirectoryClient,
    *,
    job: AsyncJob,
    worker_id: str,
) -> ReviewerDirectorySyncOutcome:
    payload = job.payload if isinstance(job.payload, dict) else {}
    required = (
        "binding_id",
        "binding_version",
        "team_id",
        "reviewer_role",
        "external_group_id",
        "idempotency_key",
    )
    if (
        str(payload.get("contract_version") or "") != SYNC_CONTRACT_VERSION
        or any(not str(payload.get(field) or "").strip() for field in required)
        or payload.get("reviewer_role") not in {"secondary", "adjudicator"}
        or not job.project_id
    ):
        error = ReviewerDirectorySyncWorkerError(
            "REVIEWER_DIRECTORY_SYNC_JOB_INVALID",
            "reviewer directory sync job payload is invalid",
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error

    routing = repository.get_routing(job.tenant_id, job.project_id)
    binding = next(
        (
            item
            for item in routing.sync_bindings
            if item.binding_id == str(payload["binding_id"])
        ),
        None,
    )
    if (
        binding is None
        or binding.team_id != str(payload["team_id"])
        or binding.reviewer_role != str(payload["reviewer_role"])
        or binding.external_group_id != str(payload["external_group_id"])
        or binding.version != int(payload["binding_version"])
        or binding.status != "active"
        or not binding.sync_enabled
    ):
        error = ReviewerDirectorySyncWorkerError(
            "REVIEWER_DIRECTORY_SYNC_BINDING_CHANGED",
            "reviewer directory binding changed after dispatch",
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error

    try:
        result = repository.run_directory_sync(
            job.tenant_id,
            job.project_id,
            binding.team_id,
            binding.reviewer_role,
            str(payload["idempotency_key"]),
            str(payload.get("requested_by") or worker_id),
            f"worker:{job.id}",
            directory_client,
        )
    except StarletteHTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        details = detail.get("details") if isinstance(detail.get("details"), dict) else {}
        error = ReviewerDirectorySyncWorkerError(
            str(detail.get("code") or "REVIEWER_DIRECTORY_SYNC_FAILED"),
            "reviewer directory synchronization failed",
            retryable=bool(details.get("retryable")),
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error from exc

    completed_binding = next(
        item for item in result.sync_bindings if item.binding_id == binding.binding_id
    )
    run_id = str(completed_binding.last_sync_run_id or "")
    run = next(
        (item for item in result.recent_sync_runs if item.run_id == run_id),
        None,
    )
    if not run or run.status != "succeeded":
        error = ReviewerDirectorySyncWorkerError(
            "REVIEWER_DIRECTORY_SYNC_RESULT_INVALID",
            "reviewer directory synchronization did not return a completed run",
        )
        store.fail(job.id, worker_id, utc_now(), error.code, error.message)
        raise error
    outcome = ReviewerDirectorySyncOutcome(
        binding_id=binding.binding_id,
        run_id=run.run_id,
        team_id=binding.team_id,
        reviewer_role=binding.reviewer_role,
        status=run.status,
        active_member_count=run.active_member_count,
        upserted_member_count=run.upserted_member_count,
        disabled_member_count=run.disabled_member_count,
        response_sha256=run.response_sha256,
        idempotent_replay=run.idempotent_replay,
    )
    store.succeed(job.id, worker_id, utc_now(), outcome.to_record())
    return outcome

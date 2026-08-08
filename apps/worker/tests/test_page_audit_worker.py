from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_crawler_lite import PAGE_AUDIT_RULES_VERSION, PageAuditFinding, PageAuditResult
from airank_domain import AsyncJob, AsyncJobStatus
from airank_outbound_security import OutboundSecurityError
from airank_worker import InMemoryJobLeaseStore
from airank_worker.page_audit import (
    PageAuditExecutionSnapshot,
    PageAuditWorkerError,
    run_next_page_audit_job,
)


NOW = datetime(2026, 8, 8, 9, 30, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self, snapshot: PageAuditExecutionSnapshot) -> None:
        self.snapshot = snapshot
        self.events: list[tuple[str, object]] = []

    def load(self, tenant_id: str, run_id: str, job_id: str) -> PageAuditExecutionSnapshot:
        assert (tenant_id, run_id, job_id) == (
            self.snapshot.tenant_id,
            self.snapshot.run_id,
            self.snapshot.job_id,
        )
        return self.snapshot

    def begin(self, snapshot, started_at):
        self.events.append(("begin", started_at))

    def complete(self, snapshot, result, completed_at):
        self.events.append(("complete", result.content_sha256))

    def fail(self, snapshot, error, completed_at, *, status):
        self.events.append((status, error.code))


class FakeService:
    def __init__(self, result: PageAuditResult | Exception) -> None:
        self.result = result
        self.urls: list[str] = []

    def audit(self, url: str) -> PageAuditResult:
        self.urls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def job() -> AsyncJob:
    return AsyncJob(
        id="job_page_audit_1",
        tenant_id="tenant_1",
        project_id="project_1",
        job_type="page.audit",
        scheduled_at=NOW,
        payload={
            "run_id": "page_audit_1",
            "requested_url": "https://example.com",
            "rules_version": PAGE_AUDIT_RULES_VERSION,
        },
    )


def snapshot(*, status: str = "queued") -> PageAuditExecutionSnapshot:
    return PageAuditExecutionSnapshot(
        tenant_id="tenant_1",
        project_id="project_1",
        run_id="page_audit_1",
        job_id="job_page_audit_1",
        requested_url="https://example.com",
        status=status,
        rules_version=PAGE_AUDIT_RULES_VERSION,
        technical_extractability_score=88 if status == "completed" else None,
        content_sha256="a" * 64 if status == "completed" else None,
    )


def audit_result() -> PageAuditResult:
    return PageAuditResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        response_status=200,
        content_type="text/html",
        response_bytes=100,
        content_sha256="b" * 64,
        connected_ip="93.184.216.34",
        redirect_count=0,
        technical_extractability_score=92,
        title="Example",
        meta_description="Evidence-backed example page",
        canonical_url="https://example.com",
        robots_directives=(),
        h1_count=1,
        visible_text_chars=500,
        json_ld_types=("Organization",),
        findings=(
            PageAuditFinding(
                rule_id="http.status",
                severity="info",
                status="passed",
                title="HTTP",
                description="200",
                recommendation="",
                evidence={"response_status": 200},
            ),
        ),
    )


def test_page_audit_job_persists_result_before_completing_job() -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot())
    service = FakeService(audit_result())

    result = run_next_page_audit_job(
        store,
        repository,
        service,  # type: ignore[arg-type]
        worker_id="worker-a",
        now=NOW,
    )

    assert result is not None
    assert result.technical_extractability_score == 92
    assert [event[0] for event in repository.events] == ["begin", "complete"]
    stored = store.get("job_page_audit_1")
    assert stored.status == AsyncJobStatus.SUCCEEDED
    assert stored.result == {
        "run_id": "page_audit_1",
        "technical_extractability_score": 92,
        "content_sha256": "b" * 64,
        "evidence_grade": "server_fetch_dns_pinned",
    }


def test_page_audit_security_block_is_durable_and_not_requeued() -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot())
    service = FakeService(
        OutboundSecurityError(
            "OUTBOUND_ADDRESS_FORBIDDEN",
            "private address",
        )
    )

    with pytest.raises(PageAuditWorkerError) as caught:
        run_next_page_audit_job(
            store,
            repository,
            service,  # type: ignore[arg-type]
            worker_id="worker-a",
            now=NOW,
        )

    assert caught.value.code == "PAGE_AUDIT_ADDRESS_FORBIDDEN"
    assert repository.events[-1] == ("blocked", "PAGE_AUDIT_ADDRESS_FORBIDDEN")
    assert store.get("job_page_audit_1").status == AsyncJobStatus.FAILED
    assert store.claim_next("worker-b", NOW) is None


def test_completed_page_audit_job_replay_never_refetches() -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot(status="completed"))
    service = FakeService(AssertionError("must not refetch"))

    result = run_next_page_audit_job(
        store,
        repository,
        service,  # type: ignore[arg-type]
        worker_id="worker-a",
        now=NOW,
    )

    assert result is None
    assert service.urls == []
    assert repository.events == []
    assert store.get("job_page_audit_1").result == {
        "run_id": "page_audit_1",
        "technical_extractability_score": 88,
        "content_sha256": "a" * 64,
        "idempotent_replay": True,
    }

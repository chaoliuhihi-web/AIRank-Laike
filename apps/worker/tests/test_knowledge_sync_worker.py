from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib

import pytest

from airank_crawler_lite import CitationSourceCaptureResult, CitationSourceSegment
from airank_domain import AsyncJob, AsyncJobStatus
from airank_evidence import FilesystemObjectStorage
from airank_outbound_security import OutboundSecurityError
from airank_worker import InMemoryJobLeaseStore
from airank_worker.knowledge_sync import (
    SYNC_CONTRACT_VERSION,
    KnowledgeSyncExecutionSnapshot,
    KnowledgeSyncOutcome,
    KnowledgeSyncWorkerError,
    run_next_knowledge_sync_job,
)


NOW = datetime(2026, 8, 8, 16, 30, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self, snapshot: KnowledgeSyncExecutionSnapshot) -> None:
        self.snapshot = snapshot
        self.events: list[tuple[str, object]] = []

    def load(self, tenant_id: str, run_id: str, job_id: str):
        assert (tenant_id, run_id, job_id) == (
            self.snapshot.tenant_id,
            self.snapshot.run_id,
            self.snapshot.job_id,
        )
        return self.snapshot

    def begin(self, snapshot, started_at):
        self.events.append(("begin", started_at))

    def complete(self, snapshot, result, raw_object, text_object, completed_at):
        self.events.append(("complete", (raw_object.sha256, text_object.sha256)))
        return KnowledgeSyncOutcome(
            run_id=snapshot.run_id,
            policy_id=snapshot.policy_id,
            status="unchanged",
            source_before_id=snapshot.source_before_id,
            source_after_id=snapshot.source_before_id,
            raw_content_sha256=result.content_sha256,
            visible_text_sha256=result.visible_text_sha256,
            raw_object_ref_id="object_raw_1",
            text_object_ref_id="object_text_1",
        )

    def fail(self, snapshot, error, completed_at, *, status):
        self.events.append((status, error.code))

    def schedule_retry(self, snapshot, error, recorded_at, retry_at):
        self.events.append(("retry_scheduled", (error.code, retry_at)))


class FakeService:
    def __init__(self, result: CitationSourceCaptureResult | Exception) -> None:
        self.result = result
        self.urls: list[str] = []

    def capture(self, url: str) -> CitationSourceCaptureResult:
        self.urls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def job() -> AsyncJob:
    return AsyncJob(
        id="job_knowledge_sync_1",
        tenant_id="tenant_1",
        project_id="project_1",
        job_type="knowledge.source.sync",
        scheduled_at=NOW,
        payload={
            "contract_version": SYNC_CONTRACT_VERSION,
            "sync_run_id": "knowledge_sync_run_1",
            "policy_id": "knowledge_sync_policy_1",
            "source_before_id": "source_1",
        },
    )


def snapshot() -> KnowledgeSyncExecutionSnapshot:
    visible_text = "AIRank 支持证据驱动的多平台品牌测量。"
    return KnowledgeSyncExecutionSnapshot(
        tenant_id="tenant_1",
        project_id="project_1",
        run_id="knowledge_sync_run_1",
        policy_id="knowledge_sync_policy_1",
        job_id="job_knowledge_sync_1",
        source_before_id="source_1",
        requested_url="https://example.com/facts",
        run_status="queued",
        policy_enabled=True,
        source_type="official_document",
        source_title="官方事实页",
        source_uri="https://example.com/facts",
        source_status="active",
        source_revision_number=1,
        source_content_sha256=hashlib.sha256(visible_text.encode()).hexdigest(),
        authority_level="official",
        risk_level="low",
        valid_from=None,
        valid_until=None,
    )


def capture_result() -> CitationSourceCaptureResult:
    visible_text = "AIRank 支持证据驱动的多平台品牌测量。"
    raw_body = f"<html><body>{visible_text}</body></html>".encode()
    return CitationSourceCaptureResult(
        requested_url="https://example.com/facts",
        final_url="https://example.com/facts",
        response_status=200,
        content_type="text/html",
        response_bytes=len(raw_body),
        content_sha256=hashlib.sha256(raw_body).hexdigest(),
        connected_ip="93.184.216.34",
        redirect_count=0,
        raw_body=raw_body,
        visible_text=visible_text,
        visible_text_sha256=hashlib.sha256(visible_text.encode()).hexdigest(),
        segments=(
            CitationSourceSegment(
                segment_index=0,
                source_start=0,
                source_end=len(visible_text),
                segment_text=visible_text,
                segment_sha256=hashlib.sha256(visible_text.encode()).hexdigest(),
            ),
        ),
    )


def test_worker_saves_immutable_capture_before_marking_source_unchanged(tmp_path) -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot())
    service = FakeService(capture_result())
    storage = FilesystemObjectStorage(tmp_path)

    outcome = run_next_knowledge_sync_job(
        store,
        repository,
        service,
        storage,
        worker_id="knowledge-worker",
        now=NOW,
    )

    assert outcome is not None and outcome.status == "unchanged"
    assert service.urls == ["https://example.com/facts"]
    assert [event[0] for event in repository.events] == ["begin", "complete"]
    assert store.get(job().id).status == AsyncJobStatus.SUCCEEDED
    assert len(list(tmp_path.rglob("*.*"))) == 2


def test_worker_classifies_dns_failure_and_schedules_bounded_backoff(tmp_path) -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot())
    service = FakeService(
        OutboundSecurityError("OUTBOUND_DNS_FAILED", "DNS unavailable", retryable=True)
    )

    try:
        run_next_knowledge_sync_job(
            store,
            repository,
            service,
            FilesystemObjectStorage(tmp_path),
            worker_id="knowledge-worker",
            now=NOW,
        )
        raise AssertionError("knowledge sync worker should fail")
    except KnowledgeSyncWorkerError as error:
        assert error.code == "KNOWLEDGE_SYNC_DNS_FAILED"
        assert error.retryable is True

    assert repository.events[-1][0] == "retry_scheduled"
    assert repository.events[-1][1][0] == "KNOWLEDGE_SYNC_DNS_FAILED"
    stored = store.get(job().id)
    assert stored.status == AsyncJobStatus.QUEUED
    assert stored.error_code == "KNOWLEDGE_SYNC_DNS_FAILED"
    assert stored.attempt_count == 1
    assert stored.scheduled_at > NOW


def test_worker_stops_retrying_after_max_attempts(tmp_path) -> None:
    exhausted_job = replace(job(), attempt_count=2, max_attempts=3)
    store = InMemoryJobLeaseStore([exhausted_job])
    repository = FakeRepository(snapshot())
    service = FakeService(
        OutboundSecurityError("OUTBOUND_DNS_FAILED", "DNS unavailable", retryable=True)
    )

    with pytest.raises(KnowledgeSyncWorkerError):
        run_next_knowledge_sync_job(
            store,
            repository,
            service,
            FilesystemObjectStorage(tmp_path),
            worker_id="knowledge-worker",
            now=NOW,
        )

    assert repository.events[-1] == ("failed", "KNOWLEDGE_SYNC_DNS_FAILED")
    stored = store.get(exhausted_job.id)
    assert stored.status == AsyncJobStatus.FAILED
    assert stored.attempt_count == 3

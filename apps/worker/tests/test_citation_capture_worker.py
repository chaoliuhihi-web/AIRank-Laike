from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from airank_crawler_lite import (
    CITATION_CAPTURE_VERSION,
    CitationSourceCaptureResult,
    CitationSourceSegment,
)
from airank_domain import AsyncJob, AsyncJobStatus
from airank_evidence import FilesystemObjectStorage
from airank_outbound_security import OutboundSecurityError
from airank_worker import InMemoryJobLeaseStore
from airank_worker.citation_capture import (
    CitationCaptureExecutionSnapshot,
    CitationCaptureWorkerError,
    run_next_citation_capture_job,
)


NOW = datetime(2026, 8, 8, 16, 0, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self, snapshot: CitationCaptureExecutionSnapshot) -> None:
        self.snapshot = snapshot
        self.events: list[tuple[str, object]] = []

    def load(self, tenant_id: str, capture_id: str, job_id: str):
        assert (tenant_id, capture_id, job_id) == (
            self.snapshot.tenant_id,
            self.snapshot.capture_id,
            self.snapshot.job_id,
        )
        return self.snapshot

    def begin(self, snapshot, started_at):
        self.events.append(("begin", started_at))

    def complete(self, snapshot, result, raw_object, text_object, completed_at):
        self.events.append(
            (
                "complete",
                (raw_object.sha256, text_object.sha256, len(result.segments)),
            )
        )

    def fail(self, snapshot, error, completed_at, *, status):
        self.events.append((status, error.code))


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
        id="job_citation_capture_1",
        tenant_id="tenant_1",
        project_id="project_1",
        job_type="citation.capture",
        scheduled_at=NOW,
        payload={
            "capture_id": "citation_capture_1",
            "citation_id": "citation_1",
            "requested_url": "https://example.com/source",
            "capture_version": CITATION_CAPTURE_VERSION,
        },
    )


def snapshot(*, status: str = "queued") -> CitationCaptureExecutionSnapshot:
    return CitationCaptureExecutionSnapshot(
        tenant_id="tenant_1",
        project_id="project_1",
        capture_id="citation_capture_1",
        citation_id="citation_1",
        job_id="job_citation_capture_1",
        requested_url="https://example.com/source",
        status=status,
        capture_version=CITATION_CAPTURE_VERSION,
        content_sha256="a" * 64 if status == "completed" else None,
        raw_object_ref_id="object_raw_1" if status == "completed" else None,
    )


def capture_result() -> CitationSourceCaptureResult:
    visible_text = "来源页面明确支持该回答主张。"
    raw_body = b"<html><body>source</body></html>"
    return CitationSourceCaptureResult(
        requested_url="https://example.com/source",
        final_url="https://example.com/source",
        response_status=200,
        content_type="text/html",
        response_bytes=64,
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
                segment_sha256="d" * 64,
            ),
        ),
    )


def test_capture_job_stores_both_immutable_objects_before_success(tmp_path) -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot())
    service = FakeService(capture_result())
    storage = FilesystemObjectStorage(tmp_path / "objects")

    result = run_next_citation_capture_job(
        store,
        repository,
        service,  # type: ignore[arg-type]
        storage,
        worker_id="worker-a",
        now=NOW,
    )

    assert result is not None
    assert [event[0] for event in repository.events] == ["begin", "complete"]
    assert len(list((tmp_path / "objects").rglob("*.*"))) == 2
    stored = store.get("job_citation_capture_1")
    assert stored.status == AsyncJobStatus.SUCCEEDED
    assert stored.result == {
        "capture_id": "citation_capture_1",
        "content_sha256": result.content_sha256,
        "visible_text_sha256": result.visible_text_sha256,
        "evidence_grade": "source_page_dns_pinned",
    }


def test_capture_security_block_is_durable(tmp_path) -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot())
    service = FakeService(
        OutboundSecurityError("OUTBOUND_ADDRESS_FORBIDDEN", "private address")
    )

    with pytest.raises(CitationCaptureWorkerError) as caught:
        run_next_citation_capture_job(
            store,
            repository,
            service,  # type: ignore[arg-type]
            FilesystemObjectStorage(tmp_path / "objects"),
            worker_id="worker-a",
            now=NOW,
        )

    assert caught.value.code == "CITATION_CAPTURE_ADDRESS_FORBIDDEN"
    assert repository.events[-1] == ("blocked", "CITATION_CAPTURE_ADDRESS_FORBIDDEN")
    assert store.get("job_citation_capture_1").status == AsyncJobStatus.FAILED


def test_completed_capture_replay_never_refetches(tmp_path) -> None:
    store = InMemoryJobLeaseStore([job()])
    repository = FakeRepository(snapshot(status="completed"))
    service = FakeService(AssertionError("must not refetch"))

    result = run_next_citation_capture_job(
        store,
        repository,
        service,  # type: ignore[arg-type]
        FilesystemObjectStorage(tmp_path / "objects"),
        worker_id="worker-a",
        now=NOW,
    )

    assert result is None
    assert service.urls == []
    assert repository.events == []
    assert store.get("job_citation_capture_1").result == {
        "capture_id": "citation_capture_1",
        "content_sha256": "a" * 64,
        "raw_object_ref_id": "object_raw_1",
        "idempotent_replay": True,
    }

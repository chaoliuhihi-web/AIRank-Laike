from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_knowledge_sync_is_durable_content_addressed_and_fail_closed() -> None:
    migration = (ROOT / "apps/api/alembic/versions/20260808_0024_knowledge_source_sync.py").read_text(encoding="utf-8")
    api = (ROOT / "apps/api/knowledge_sync_routes.py").read_text(encoding="utf-8")
    scheduler = (ROOT / "apps/scheduler/airank_scheduler/knowledge_sync.py").read_text(encoding="utf-8")
    worker = (ROOT / "apps/worker/airank_worker/knowledge_sync.py").read_text(encoding="utf-8")
    worker_main = (ROOT / "apps/worker/airank_worker/main.py").read_text(encoding="utf-8")

    for table in ("airank_knowledge_sync_policies", "airank_knowledge_sync_runs"):
        assert table in migration
    assert "knowledge.source.sync" in api
    assert "knowledge.source.sync" in scheduler
    assert "knowledge.source.sync" in worker_main
    assert "SafeOutboundClient" not in worker
    assert "CitationSourceCaptureService" in worker
    assert "raw_object_ref_id" in worker
    assert "text_object_ref_id" in worker
    assert "result.visible_text_sha256 != snapshot.source_content_sha256" in worker
    assert "SET status='stale'" in worker
    assert "source_after_id" in worker
    assert "embedding_status" in worker and "'pending'" in worker
    assert "KNOWLEDGE_SYNC_CONTENT_COLLISION" in worker
    assert "NOT EXISTS" in scheduler and "('queued','running')" in scheduler


def test_knowledge_sync_never_mutates_existing_source_content() -> None:
    worker = (ROOT / "apps/worker/airank_worker/knowledge_sync.py").read_text(encoding="utf-8")

    assert "INSERT INTO airank_knowledge_sources" in worker
    assert "INSERT INTO airank_knowledge_source_contents" in worker
    assert "UPDATE airank_knowledge_source_contents" not in worker
    assert "UPDATE airank_knowledge_segments" not in worker

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from apps.api.knowledge_routes import (
    FactProposalRequest,
    FactRevisionReviewRequest,
    KnowledgeSourceCreateRequest,
    MySQLKnowledgeRepository,
)
from apps.api.knowledge_sync_routes import (
    KnowledgeSyncPolicyCreateRequest,
    MySQLKnowledgeSyncRepository,
)
from apps.api.main import MySQLProjectRepository, ProjectCreateRequest
from airank_crawler_lite import CitationSourceCaptureResult, CitationSourceSegment
from airank_evidence import FilesystemObjectStorage
from airank_scheduler.knowledge_sync import MySQLKnowledgeSyncScheduler
from airank_worker.knowledge_sync import (
    MySQLKnowledgeSyncExecutionRepository,
    run_next_knowledge_sync_job,
)
from airank_worker.lease import MySQLJobLeaseStore


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def require_real_mysql() -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real knowledge sync checks")


def cleanup_tenant(engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.columns
                WHERE table_schema=DATABASE() AND column_name='tenant_id'
                  AND table_name LIKE 'airank\\_%'
                """
            )
        ).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        try:
            for table_name in tables:
                conn.execute(
                    text(f"DELETE FROM `{table_name}` WHERE tenant_id=:tenant_id"),
                    {"tenant_id": tenant_id},
                )
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


class FakeCaptureService:
    def __init__(self, result: CitationSourceCaptureResult) -> None:
        self.result = result
        self.urls: list[str] = []

    def capture(self, url: str) -> CitationSourceCaptureResult:
        self.urls.append(url)
        return self.result


def capture_result(visible_text: str) -> CitationSourceCaptureResult:
    raw_body = f"<html><body><main>{visible_text}</main></body></html>".encode("utf-8")
    segment_sha256 = hashlib.sha256(visible_text.encode("utf-8")).hexdigest()
    return CitationSourceCaptureResult(
        requested_url="https://example.com/company-facts",
        final_url="https://example.com/company-facts",
        response_status=200,
        content_type="text/html",
        response_bytes=len(raw_body),
        content_sha256=hashlib.sha256(raw_body).hexdigest(),
        connected_ip="93.184.216.34",
        redirect_count=0,
        raw_body=raw_body,
        visible_text=visible_text,
        visible_text_sha256=segment_sha256,
        segments=(
            CitationSourceSegment(
                segment_index=0,
                source_start=0,
                source_end=len(visible_text),
                segment_text=visible_text,
                segment_sha256=segment_sha256,
            ),
        ),
    )


def test_real_mysql_periodic_source_sync_is_immutable_and_invalidates_stale_fact(tmp_path) -> None:
    require_real_mysql()
    url = database_url()
    tenant_id = f"tenant_ksync_{uuid4().hex[:10]}"
    engine = create_engine(url, pool_pre_ping=True)
    cleanup_tenant(engine, tenant_id)
    project_repo = MySQLProjectRepository(url)
    knowledge_repo = MySQLKnowledgeRepository(url)
    sync_repo = MySQLKnowledgeSyncRepository(url)
    execution_repo = MySQLKnowledgeSyncExecutionRepository(url)
    store = MySQLJobLeaseStore(url, tenant_id=tenant_id)
    storage = FilesystemObjectStorage(tmp_path / "objects")
    initial_text = "AIRank 使用真实回答、引用与请求元数据评估品牌可见度。"
    changed_text = "AIRank 使用真实回答、引用、请求元数据与定期复测评估品牌可见度。"
    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://example.com",
                brand_name_hint="知识同步验收品牌",
                industry_hint="enterprise software",
            ),
        )
        source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-sync-source-v1",
                source_type="official_webpage",
                title="企业公开事实页",
                content_text=initial_text,
                source_uri="https://example.com/company-facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        fact = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="测量方法",
                fact_type="product_service",
                fact_text=initial_text,
                source_ids=[source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
            ),
        )
        approved = knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            fact.revision_id,
            FactRevisionReviewRequest(
                action="approved", reviewed_by="integration-reviewer", review_note="官方事实页"
            ),
        )
        assert approved.eligible_for_generation is True

        policy = sync_repo.create_policy(
            tenant_id,
            project.project_id,
            source,
            KnowledgeSyncPolicyCreateRequest(
                idempotency_key="knowledge-sync-policy-real-1",
                interval_hours=24,
                created_by="integration-test",
            ),
        )
        first_service = FakeCaptureService(capture_result(initial_text))
        first = run_next_knowledge_sync_job(
            store,
            execution_repo,
            first_service,
            storage,
            worker_id="knowledge-sync-integration",
        )
        assert first is not None and first.status == "unchanged"
        assert first.source_before_id == first.source_after_id == source.source_id

        due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_sync_policies SET next_run_at=:due_at
                    WHERE tenant_id=:tenant_id AND id=:policy_id
                    """
                ),
                {"due_at": due_at, "tenant_id": tenant_id, "policy_id": policy.policy_id},
            )
        scheduler = MySQLKnowledgeSyncScheduler(
            url,
            tenant_id=tenant_id,
            project_id=project.project_id,
            scheduler_id="knowledge-sync-integration-scheduler",
        )
        dispatched = scheduler.dispatch_due(now=datetime.now(timezone.utc), limit=10)
        assert len(dispatched) == 1
        second_service = FakeCaptureService(capture_result(changed_text))
        second = run_next_knowledge_sync_job(
            store,
            execution_repo,
            second_service,
            storage,
            worker_id="knowledge-sync-integration",
        )
        assert second is not None and second.status == "changed"
        assert second.source_after_id != source.source_id

        sources = knowledge_repo.list_sources(tenant_id, project.project_id)
        old_source = next(item for item in sources if item.source_id == source.source_id)
        new_source = next(item for item in sources if item.source_id == second.source_after_id)
        facts = knowledge_repo.list_facts(tenant_id, project.project_id)
        stale_fact = next(item for item in facts if item.revision_id == fact.revision_id)
        with engine.begin() as conn:
            runs = conn.execute(
                text(
                    """
                    SELECT status, raw_object_ref_id, text_object_ref_id,
                           raw_content_sha256, visible_text_sha256
                    FROM airank_knowledge_sync_runs
                    WHERE tenant_id=:tenant_id AND policy_id=:policy_id
                    ORDER BY scheduled_at
                    """
                ),
                {"tenant_id": tenant_id, "policy_id": policy.policy_id},
            ).mappings().all()
            policy_row = conn.execute(
                text(
                    """
                    SELECT current_source_id, last_status, last_run_id, next_run_at
                    FROM airank_knowledge_sync_policies
                    WHERE tenant_id=:tenant_id AND id=:policy_id
                    """
                ),
                {"tenant_id": tenant_id, "policy_id": policy.policy_id},
            ).mappings().one()
            segments = conn.execute(
                text(
                    """
                    SELECT segment_text, embedding_status
                    FROM airank_knowledge_segments
                    WHERE tenant_id=:tenant_id AND knowledge_source_id=:source_id
                    ORDER BY segment_index
                    """
                ),
                {"tenant_id": tenant_id, "source_id": new_source.source_id},
            ).mappings().all()
            object_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_object_refs
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND object_type='knowledge_source'
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).scalar_one()
            audit_events = set(
                conn.execute(
                    text(
                        """
                        SELECT event_type FROM airank_audit_events
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND event_type LIKE 'knowledge.sync.%'
                        """
                    ),
                    {"tenant_id": tenant_id, "project_id": project.project_id},
                ).scalars().all()
            )
        assert [row["status"] for row in runs] == ["unchanged", "changed"]
        assert all(row["raw_object_ref_id"] and row["text_object_ref_id"] for row in runs)
        assert all(len(row["raw_content_sha256"]) == len(row["visible_text_sha256"]) == 64 for row in runs)
        assert policy_row["current_source_id"] == new_source.source_id
        assert policy_row["last_status"] == "changed"
        assert old_source.status == "stale"
        assert new_source.status == "active"
        assert new_source.parent_source_id == old_source.source_id
        assert new_source.revision_number == 2
        assert "".join(row["segment_text"] for row in segments) == changed_text
        assert {row["embedding_status"] for row in segments} == {"pending"}
        assert stale_fact.eligible_for_generation is False
        assert stale_fact.eligibility_reason == "source_stale"
        assert object_count == 4
        assert {
            "knowledge.sync.unchanged",
            "knowledge.sync.dispatched",
            "knowledge.sync.changed",
        }.issubset(audit_events)
        assert len(list((tmp_path / "objects").rglob("*.*"))) == 4
    finally:
        cleanup_tenant(engine, tenant_id)

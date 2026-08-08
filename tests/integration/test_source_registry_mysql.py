from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.main import (
    BuyerQuestionCreateRequest,
    MySQLProjectRepository,
    MySQLScanRepository,
    ProjectCreateRequest,
    ScanRunCreateRequest,
)
from apps.api.source_registry_routes import (
    MySQLSourceRegistryRepository,
    SourceClassificationReviewRequest,
)


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.columns
                WHERE table_schema=DATABASE() AND column_name='tenant_id'
                  AND table_name LIKE 'airank\\_%'
                ORDER BY table_name DESC
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


def review_payload(
    *,
    supersedes_revision_id: str | None = None,
    authority_level: str = "medium",
) -> SourceClassificationReviewRequest:
    return SourceClassificationReviewRequest(
        source_category_l1="news_media",
        source_type="regional_news_media",
        ecosystem="Example Media",
        classification_confidence="high",
        authority_level=authority_level,
        usage_policy="context_only",
        risk_level="medium",
        evidence_note="A human reviewer checked the publisher identity and representative pages.",
        evidence_url="https://news.example.com/about",
        reviewed_by="source-reviewer",
        supersedes_revision_id=supersedes_revision_id,
    )


def test_real_mysql_source_registry_preserves_unknown_and_append_only_human_reviews() -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real integration checks")
    tenant_id = f"tenant_source_registry_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repository = MySQLProjectRepository(database_url())
    scan_repository = MySQLScanRepository(database_url())
    source_repository = MySQLSourceRegistryRepository(database_url())

    try:
        project = project_repository.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://example.com/source-registry",
                brand_name_hint="AIRank Source Registry",
                industry_hint="enterprise software",
            ),
        )
        question = project_repository.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="哪些来源支持企业 GEO 结论？",
                status="confirmed",
                source="manual",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repository.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                repetitions=1,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        task = scan_repository.list_tasks(tenant_id, run.run_id)[0]
        snapshot_id = f"snapshot_{uuid4().hex[:16]}"
        citation_id = f"citation_{uuid4().hex[:16]}"
        answer_text = "请检查来源主体、用途和原始页面证据。"
        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, cohort_type, prompt_version_id, sample_index,
                      session_id, collector_surface, evidence_level, sample_status,
                      answer_text, answer_sha256, raw_response_sha256,
                      brand_mentioned, mention_class, target_entity_mentions_json,
                      competitor_mentions_json, sentiment, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :cohort_type, :prompt_version_id, :sample_index,
                      :session_id, :collector_surface, :evidence_level, 'valid',
                      :answer_text, :answer_sha256, :raw_response_sha256,
                      0, 'not_mentioned', JSON_ARRAY(), JSON_ARRAY(), 'neutral', :created_at
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": task.task_id,
                    "question_id": task.question_id,
                    "provider": task.provider,
                    "cohort_type": task.cohort_type,
                    "prompt_version_id": task.prompt_version_id,
                    "sample_index": task.sample_index,
                    "session_id": task.session_id,
                    "collector_surface": task.collector_surface,
                    "evidence_level": task.evidence_level,
                    "answer_text": answer_text,
                    "answer_sha256": hashlib.sha256(answer_text.encode()).hexdigest(),
                    "raw_response_sha256": "c" * 64,
                    "created_at": now,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_source_citations (
                      id, tenant_id, project_id, snapshot_id, citation_order,
                      title, url, host, source_type, cited_text, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :snapshot_id, 1,
                      'Example News', 'https://news.example.com/article',
                      'News.Example.COM.', 'provider_native', '来源片段', :created_at
                    )
                    """
                ),
                {
                    "id": citation_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "snapshot_id": snapshot_id,
                    "created_at": now,
                },
            )

        initial = source_repository.list(tenant_id, project.project_id)
        assert len(initial) == 1
        assert initial[0].normalized_host == "news.example.com"
        assert initial[0].classification_status == "unclassified"
        assert initial[0].current_revision is None

        first = source_repository.review(
            tenant_id,
            project.project_id,
            "news.example.com",
            review_payload(),
            "real-source-review-first",
            "trc_source_review_first",
        )
        first_revision = first.current_revision
        assert first_revision is not None
        assert first_revision.revision_number == 1
        assert first_revision.classification_method == "human_review"
        assert first_revision.authority_level == "medium"

        replay = source_repository.review(
            tenant_id,
            project.project_id,
            "news.example.com",
            review_payload(),
            "real-source-review-first",
            "trc_source_review_replay",
        )
        assert replay.current_revision is not None
        assert replay.current_revision.revision_id == first_revision.revision_id
        assert replay.current_revision.idempotent_replay

        with pytest.raises(StarletteHTTPException) as conflict:
            source_repository.review(
                tenant_id,
                project.project_id,
                "news.example.com",
                review_payload(authority_level="high"),
                "real-source-review-stale",
                "trc_source_review_stale",
            )
        assert conflict.value.status_code == 409
        assert conflict.value.detail["code"] == "SOURCE_CLASSIFICATION_VERSION_CONFLICT"

        second = source_repository.review(
            tenant_id,
            project.project_id,
            "news.example.com",
            review_payload(
                supersedes_revision_id=first_revision.revision_id,
                authority_level="high",
            ),
            "real-source-review-second",
            "trc_source_review_second",
        )
        assert second.current_revision is not None
        assert second.current_revision.revision_number == 2
        assert second.current_revision.authority_level == "high"
        assert second.current_revision.supersedes_revision_id == first_revision.revision_id
        assert [row.revision_number for row in second.history] == [2, 1]

        replay_old = source_repository.review(
            tenant_id,
            project.project_id,
            "news.example.com",
            review_payload(),
            "real-source-review-first",
            "trc_source_review_old_replay",
        )
        assert replay_old.current_revision is not None
        assert replay_old.current_revision.revision_number == 2
        assert not replay_old.current_revision.idempotent_replay
        assert replay_old.history[1].revision_number == 1
        assert replay_old.history[1].idempotent_replay

        with engine.begin() as conn:
            stored_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_source_classification_revisions
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).scalar_one()
            audit_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_audit_events
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND event_type='source.classification_reviewed'
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).scalar_one()
        assert stored_count == 2
        assert audit_count == 2
    finally:
        cleanup_tenant(engine, tenant_id)

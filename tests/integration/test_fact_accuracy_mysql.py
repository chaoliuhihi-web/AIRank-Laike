from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from apps.api.citation_support_routes import (
    CitationClaimCreateRequest,
    FactAccuracyReviewCreateRequest,
    MySQLCitationSupportRepository,
)
from apps.api.evidence_review_routes import (
    EvidenceReviewDecisionRequest,
    FactReviewCaseCreateRequest,
    MySQLEvidenceReviewRepository,
)
from apps.api.knowledge_routes import (
    FactProposalRequest,
    FactRevisionReviewRequest,
    KnowledgeSourceCreateRequest,
    MySQLKnowledgeRepository,
)
from apps.api.main import (
    BuyerQuestionCreateRequest,
    MySQLProjectRepository,
    MySQLScanRepository,
    ProjectCreateRequest,
    ScanRunCreateRequest,
)
from apps.api.retest_routes import MySQLRetestRepository
from apps.api.report_packet import MySQLReportEvidencePacketRepository


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


def test_real_mysql_fact_accuracy_requires_current_reviewed_fact_and_exact_source() -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real integration checks")
    tenant_id = f"tenant_fact_accuracy_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repository = MySQLProjectRepository(database_url())
    scan_repository = MySQLScanRepository(database_url())
    knowledge_repository = MySQLKnowledgeRepository(database_url())
    evidence_repository = MySQLCitationSupportRepository(database_url())
    review_repository = MySQLEvidenceReviewRepository(database_url())
    retest_repository = MySQLRetestRepository(database_url())
    report_packet_repository = MySQLReportEvidencePacketRepository(database_url())
    fact_text = "AIRank 支持四类 Prompt Cohort。"
    answer_text = f"{fact_text}该能力用于区分盲测、辅助测、对比测和事实核验。"

    try:
        project = project_repository.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://example.com/fact-accuracy",
                brand_name_hint="AIRank",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repository.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="AIRank 支持哪些测量类型？",
                status="confirmed",
                source="manual",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repository.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                cohort_type=question.cohort_type,
                repetitions=1,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        task = scan_repository.list_tasks(tenant_id, run.run_id)[0]
        snapshot_id = f"snapshot_{uuid4().hex[:16]}"
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
                      1, 'mentioned', JSON_ARRAY(), JSON_ARRAY(), 'neutral', :created_at
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
                    "raw_response_sha256": "d" * 64,
                    "created_at": datetime.now(timezone.utc),
                },
            )

        source = knowledge_repository.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="fact-accuracy-source-v1",
                source_type="official_website",
                title="AIRank 测量能力",
                content_text=f"产品说明：{fact_text}",
                source_uri="https://example.com/facts/v1",
                authority_level="official",
                risk_level="low",
            ),
        )
        proposed = knowledge_repository.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="Prompt Cohort",
                fact_text=fact_text,
                source_ids=[source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="fact-owner",
            ),
        )
        approved = knowledge_repository.review_revision(
            tenant_id,
            project.project_id,
            proposed.revision_id,
            FactRevisionReviewRequest(
                action="approved",
                reviewed_by="knowledge-reviewer",
                review_note="已核对官网原文。",
            ),
        )
        claim = evidence_repository.create_claim(
            tenant_id,
            snapshot_id,
            CitationClaimCreateRequest(
                answer_start=0,
                answer_end=len(fact_text),
                claim_kind="brand_fact",
                subject_entity_text="AIRank",
                created_by="fact-reviewer",
            ),
        )
        review_payload = FactReviewCaseCreateRequest(
            claim_id=claim.claim_id,
            purpose="production",
            review=FactAccuracyReviewCreateRequest(
                verdict="accurate",
                fact_revision_id=approved.revision_id,
                rationale="第一审核人核对当前审核事实与原始来源边界。",
                reviewed_by="fact-reviewer-1",
            ),
        )
        review_case = review_repository.create_fact_case(
            tenant_id,
            project.project_id,
            review_payload,
            "fact-accuracy-review-case-v1",
            "fact-reviewer-1",
            "trace_fact_accuracy_primary",
        )
        assert review_case.status == "awaiting_secondary"
        completed = review_repository.submit_decision(
            tenant_id,
            review_case.case_id,
            EvidenceReviewDecisionRequest(
                label="accurate",
                rationale="第二审核人独立核对后同意。",
                reviewed_by="fact-reviewer-2",
            ),
            "fact-reviewer-2",
            "trace_fact_accuracy_secondary",
        )
        assert completed.status == "agreed"
        bundle = evidence_repository.get_fact_accuracy_bundle(tenant_id, snapshot_id)
        reviewed = bundle.reviews[-1]
        assert reviewed.commercially_verified is True
        assert reviewed.quoted_text == fact_text
        assert reviewed.source_start is not None
        assert reviewed.source_end is not None

        assert bundle.metrics.factual_claim_count == 1
        assert bundle.metrics.evaluation_coverage_rate == 1.0
        assert bundle.metrics.fact_accuracy == 1.0

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='completed', finished_at=:finished_at,
                        updated_at=:finished_at
                    WHERE tenant_id=:tenant_id AND id=:task_id
                    """
                ),
                {
                    "finished_at": datetime.now(timezone.utc),
                    "tenant_id": tenant_id,
                    "task_id": task.task_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_runs
                    SET status='completed', finished_at=:finished_at,
                        updated_at=:finished_at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {
                    "finished_at": datetime.now(timezone.utc),
                    "tenant_id": tenant_id,
                    "run_id": run.run_id,
                },
            )
        quality = retest_repository.get_quality_report(
            tenant_id,
            project.project_id,
            run.run_id,
        )
        assert quality["metrics"]["fact_claim_count"] == 1
        assert quality["metrics"]["fact_reviewed_claim_count"] == 1
        assert quality["metrics"]["fact_accuracy_coverage_rate"] == 1.0
        assert quality["metrics"]["fact_accuracy"] == 1.0
        with engine.begin() as conn:
            _, _, fact_index, _, _ = report_packet_repository._load_evidence_indices(
                conn,
                tenant_id,
                project.project_id,
                {
                    "baseline_run_id": run.run_id,
                    "compare_run_id": "scan_run_not_present",
                },
            )
        assert len(fact_index) == 1
        assert fact_index[0]["claim_id"] == claim.claim_id
        assert fact_index[0]["latest_review"]["commercially_verified"] is True
        assert len(fact_index[0]["latest_review"]["review_record_sha256"]) == 64
        assert "quoted_text" not in fact_index[0]["latest_review"]
        assert fact_index[0]["latest_review"]["quoted_text_sha256"] == reviewed.quoted_text_sha256

        replay = review_repository.create_fact_case(
            tenant_id,
            project.project_id,
            review_payload,
            "fact-accuracy-review-case-v1",
            "fact-reviewer-1",
            "trace_fact_accuracy_replay",
        )
        assert replay.case_id == review_case.case_id
        assert replay.idempotent_replay is True

        source_v2 = knowledge_repository.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="fact-accuracy-source-v2",
                source_type="official_website",
                title="AIRank 测量能力更新",
                content_text="产品说明：AIRank 支持五类测量 Cohort。",
                source_uri="https://example.com/facts/v2",
                authority_level="official",
                risk_level="low",
            ),
        )
        revised = knowledge_repository.revise_fact(
            tenant_id,
            project.project_id,
            proposed.fact_id,
            FactProposalRequest(
                title="Prompt Cohort",
                fact_text="AIRank 支持五类测量 Cohort。",
                source_ids=[source_v2.source_id],
                risk_level="low",
                disclosure="public",
                created_by="fact-owner",
            ),
        )
        knowledge_repository.review_revision(
            tenant_id,
            project.project_id,
            revised.revision_id,
            FactRevisionReviewRequest(
                action="approved",
                reviewed_by="knowledge-reviewer",
                review_note="事实已更新。",
            ),
        )

        stale_bundle = evidence_repository.get_fact_accuracy_bundle(tenant_id, snapshot_id)
        assert stale_bundle.reviews[0].commercially_verified is False
        assert stale_bundle.metrics.fact_accuracy is None
        assert "provisional_or_stale_fact_reviews_excluded" in stale_bundle.metrics.known_limitations
        stale_quality = retest_repository.get_quality_report(
            tenant_id,
            project.project_id,
            run.run_id,
        )
        assert stale_quality["metrics"]["fact_reviewed_claim_count"] == 0
        assert stale_quality["metrics"]["fact_accuracy_coverage_rate"] == 0.0
        assert stale_quality["metrics"]["fact_accuracy"] is None

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM airank_fact_accuracy_reviews
                       WHERE tenant_id=:tenant_id) AS review_count,
                          (SELECT COUNT(*) FROM airank_audit_events
                           WHERE tenant_id=:tenant_id
                             AND entity_type='evidence_review_case') AS audit_count
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().one()
            assert dict(rows) == {"review_count": 2, "audit_count": 2}
    finally:
        cleanup_tenant(engine, tenant_id)

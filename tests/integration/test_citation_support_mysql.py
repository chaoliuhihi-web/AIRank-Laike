from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from apps.api.citation_support_routes import (
    CitationClaimCreateRequest,
    CitationSupportReviewCreateRequest,
    MySQLCitationSupportRepository,
)
from apps.api.evidence_review_routes import (
    CitationReviewCaseCreateRequest,
    EvidenceReviewDecisionRequest,
    MySQLEvidenceReviewRepository,
)
from apps.api.main import (
    BuyerQuestionCreateRequest,
    MySQLProjectRepository,
    MySQLScanRepository,
    ProjectCreateRequest,
    ScanRunCreateRequest,
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


def test_real_mysql_citation_selection_and_support_are_separate_append_only_evidence() -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real integration checks")
    tenant_id = f"tenant_citation_support_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repository = MySQLProjectRepository(database_url())
    scan_repository = MySQLScanRepository(database_url())
    support_repository = MySQLCitationSupportRepository(database_url())
    review_repository = MySQLEvidenceReviewRepository(database_url())
    answer_text = "企业可以把 AI 回答指标下钻到原始样本和引用证据。"
    cited_text = "每条汇总结论都应关联原始回答、引用与不可变内容摘要。"

    try:
        project = project_repository.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://example.com/citation-support",
                brand_name_hint="AIRank Citation Review",
                industry_hint="enterprise software",
            ),
        )
        question = project_repository.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业如何评估 AI 回答中的引用是否支持具体结论？",
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
        answer_sha256 = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
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
                    "answer_sha256": answer_sha256,
                    "raw_response_sha256": "d" * 64,
                    "created_at": datetime.now(timezone.utc),
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
                      '引用支持度来源', 'https://example.com/source', 'example.com',
                      'provider_native', :cited_text, :created_at
                    )
                    """
                ),
                {
                    "id": citation_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "snapshot_id": snapshot_id,
                    "cited_text": cited_text,
                    "created_at": datetime.now(timezone.utc),
                },
            )

        claim = support_repository.create_claim(
            tenant_id,
            snapshot_id,
            CitationClaimCreateRequest(
                answer_start=0,
                answer_end=len(answer_text),
                created_by="integration-reviewer",
            ),
        )
        provisional = support_repository.create_review(
            tenant_id,
            claim.claim_id,
            CitationSupportReviewCreateRequest(
                citation_id=citation_id,
                support_label="supports",
                evidence_grade="provider_excerpt_only",
                source_excerpt=cited_text,
                source_content_sha256=hashlib.sha256(cited_text.encode("utf-8")).hexdigest(),
                rationale="Provider 摘要相关，但尚无页面快照。",
                reviewed_by="integration-reviewer",
            ),
        )
        assert provisional.commercially_verified is False
        assert support_repository.get_bundle(tenant_id, snapshot_id).metrics.citation_support_rate is None

        source_object_id = f"object_{uuid4().hex[:16]}"
        source_capture_id = f"citation_capture_{uuid4().hex[:16]}"
        source_segment_id = f"citation_segment_{uuid4().hex[:16]}"
        source_job_id = f"job_citation_capture_{uuid4().hex[:16]}"
        source_sha256 = "e" * 64
        source_excerpt = "来源页面明确说明结论可下钻到原始证据。"
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_async_jobs (
                      id, tenant_id, project_id, job_type, status, priority,
                      scheduled_at, timeout_seconds, attempt_count, max_attempts,
                      payload_json, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'citation.capture', 'succeeded', 25,
                      :created_at, 120, 1, 3, JSON_OBJECT(), :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": source_job_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_object_refs (
                      id, tenant_id, project_id, object_type, object_uri,
                      content_type, byte_size, sha256, metadata_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'citation_source_page',
                      :object_uri, 'text/html', 512, :sha256, :metadata_json, :created_at
                    )
                    """
                ),
                {
                    "id": source_object_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "object_uri": f"s3://evidence/{source_object_id}.html",
                    "sha256": source_sha256,
                    "metadata_json": json.dumps(
                        {
                            "kind": "citation_source_page",
                            "citation_id": citation_id,
                            "capture_id": source_capture_id,
                        }
                    ),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_source_captures (
                      id, tenant_id, project_id, citation_id, job_id,
                      idempotency_key, request_sha256, requested_url, final_url,
                      status, capture_version, evidence_grade, response_status,
                      content_type, response_bytes, content_sha256,
                      visible_text_sha256, raw_object_ref_id, connected_ip,
                      redirect_count, requested_by, started_at, completed_at,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :citation_id, :job_id,
                      :idempotency_key, :request_sha256, 'https://example.com/source',
                      'https://example.com/source', 'completed',
                      'airank.citation-source-capture.v1', 'source_page_dns_pinned',
                      200, 'text/html', 512, :content_sha256,
                      :visible_text_sha256, :raw_object_ref_id, '93.184.216.34',
                      0, 'integration-reviewer', :created_at, :created_at,
                      :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": source_capture_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "citation_id": citation_id,
                    "job_id": source_job_id,
                    "idempotency_key": f"integration-{source_capture_id}",
                    "request_sha256": "f" * 64,
                    "content_sha256": source_sha256,
                    "visible_text_sha256": hashlib.sha256(source_excerpt.encode()).hexdigest(),
                    "raw_object_ref_id": source_object_id,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_source_segments (
                      id, tenant_id, project_id, capture_id, segment_index,
                      source_start, source_end, segment_text, segment_sha256, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :capture_id, 0,
                      0, :source_end, :segment_text, :segment_sha256, :created_at
                    )
                    """
                ),
                {
                    "id": source_segment_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "capture_id": source_capture_id,
                    "source_end": len(source_excerpt),
                    "segment_text": source_excerpt,
                    "segment_sha256": hashlib.sha256(source_excerpt.encode()).hexdigest(),
                    "created_at": datetime.now(timezone.utc),
                },
            )
        review_case = review_repository.create_citation_case(
            tenant_id,
            project.project_id,
            CitationReviewCaseCreateRequest(
                claim_id=claim.claim_id,
                purpose="production",
                review=CitationSupportReviewCreateRequest(
                    citation_id=citation_id,
                    support_label="supports",
                    evidence_grade="source_page_snapshot",
                    source_excerpt=source_excerpt,
                    source_content_sha256=source_sha256,
                    source_object_ref_id=source_object_id,
                    source_capture_id=source_capture_id,
                    source_segment_id=source_segment_id,
                    source_start=0,
                    source_end=len(source_excerpt),
                    rationale="第一审核人核对不可变来源页面后确认支持。",
                    reviewed_by="integration-reviewer-1",
                ),
            ),
            "citation-support-production-case",
            "integration-reviewer-1",
            "trace-citation-support-primary",
        )
        assert review_case.status == "awaiting_secondary"
        completed = review_repository.submit_decision(
            tenant_id,
            review_case.case_id,
            EvidenceReviewDecisionRequest(
                label="supports",
                rationale="第二审核人独立核对来源边界后同意。",
                reviewed_by="integration-reviewer-2",
            ),
            "integration-reviewer-2",
            "trace-citation-support-secondary",
        )
        assert completed.status == "agreed"
        bundle = support_repository.get_bundle(tenant_id, snapshot_id)
        verified = bundle.reviews[-1]
        assert verified.commercially_verified is True
        assert verified.review_case_id == review_case.case_id
        assert verified.reviewer_role == "secondary"
        assert len(bundle.reviews) == 3
        assert bundle.metrics.review_count == 1
        assert bundle.metrics.commercially_verified_review_count == 1
        assert bundle.metrics.citation_support_rate == 1.0
    finally:
        cleanup_tenant(engine, tenant_id)

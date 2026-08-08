from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from airank_crawler_lite import CitationSourceCaptureResult, CitationSourceSegment
from airank_evidence import FilesystemObjectStorage
from airank_worker import MySQLJobLeaseStore
from airank_worker.citation_capture import (
    MySQLCitationCaptureExecutionRepository,
    run_next_citation_capture_job,
)
from apps.api.citation_capture_routes import (
    CitationCaptureCreateRequest,
    MySQLCitationCaptureRepository,
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


class FakeCaptureService:
    def __init__(self, result: CitationSourceCaptureResult) -> None:
        self.result = result
        self.urls: list[str] = []

    def capture(self, url: str) -> CitationSourceCaptureResult:
        self.urls.append(url)
        return self.result


def test_real_mysql_citation_capture_persists_objects_segments_and_job(tmp_path) -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real integration checks")
    tenant_id = f"tenant_citation_capture_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repository = MySQLProjectRepository(database_url())
    scan_repository = MySQLScanRepository(database_url())
    capture_repository = MySQLCitationCaptureRepository(database_url())
    execution_repository = MySQLCitationCaptureExecutionRepository(database_url())
    lease_store = MySQLJobLeaseStore(database_url())
    source_url = "https://example.com/citation-source"
    raw_body = (
        "<html><body><main><h1>可信来源</h1>"
        "<p>企业报告中的每条结论都应关联原始回答和来源证据。</p>"
        "</main></body></html>"
    ).encode()
    visible_text = "可信来源 企业报告中的每条结论都应关联原始回答和来源证据。"
    raw_sha256 = hashlib.sha256(raw_body).hexdigest()
    text_sha256 = hashlib.sha256(visible_text.encode()).hexdigest()
    segment = CitationSourceSegment(
        segment_index=0,
        source_start=0,
        source_end=len(visible_text),
        segment_text=visible_text,
        segment_sha256=text_sha256,
    )
    result = CitationSourceCaptureResult(
        requested_url=source_url,
        final_url=source_url,
        response_status=200,
        content_type="text/html",
        response_bytes=len(raw_body),
        content_sha256=raw_sha256,
        connected_ip="93.184.216.34",
        redirect_count=0,
        raw_body=raw_body,
        visible_text=visible_text,
        visible_text_sha256=text_sha256,
        segments=(segment,),
    )

    try:
        project = project_repository.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://example.com/citation-capture",
                brand_name_hint="AIRank Capture",
                industry_hint="enterprise software",
            ),
        )
        question = project_repository.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="如何验证 AI 回答引用的原始来源？",
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
        answer_text = "应保存原始回答、引用 URL 和来源网页快照。"
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
                    "raw_response_sha256": "9" * 64,
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
                      '可信来源', :url, 'example.com', 'provider_native',
                      '每条结论都应关联原始证据。', :created_at
                    )
                    """
                ),
                {
                    "id": citation_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "snapshot_id": snapshot_id,
                    "url": source_url,
                    "created_at": datetime.now(timezone.utc),
                },
            )

        queued = capture_repository.create(
            tenant_id,
            citation_id,
            CitationCaptureCreateRequest(
                idempotency_key=f"capture-{uuid4().hex}",
                requested_by="integration-operator",
            ),
        )
        assert queued.status == "queued"
        storage = FilesystemObjectStorage(tmp_path / "evidence")
        captured = run_next_citation_capture_job(
            lease_store,
            execution_repository,
            FakeCaptureService(result),  # type: ignore[arg-type]
            storage,
            worker_id="integration-worker",
            now=datetime.now(timezone.utc),
        )
        assert captured is not None

        completed = capture_repository.get(tenant_id, queued.capture_id)
        assert completed.status == "completed"
        assert completed.content_sha256 == raw_sha256
        assert completed.visible_text_sha256 == text_sha256
        assert completed.raw_object_ref_id
        assert completed.text_object_ref_id
        assert "".join(item.segment_text for item in completed.segments) == visible_text
        assert completed.segments[0].source_start == 0
        assert completed.segments[0].source_end == len(visible_text)

        with engine.begin() as conn:
            object_rows = conn.execute(
                text(
                    """
                    SELECT id, sha256, metadata_json FROM airank_object_refs
                    WHERE tenant_id=:tenant_id AND id IN (:raw_id, :text_id)
                    ORDER BY id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "raw_id": completed.raw_object_ref_id,
                    "text_id": completed.text_object_ref_id,
                },
            ).mappings().all()
            assert len(object_rows) == 2
            metadata = [
                json.loads(row["metadata_json"])
                if isinstance(row["metadata_json"], str)
                else row["metadata_json"]
                for row in object_rows
            ]
            assert {item["kind"] for item in metadata} == {
                "citation_source_page",
                "citation_source_text",
            }
            assert all(item["capture_id"] == queued.capture_id for item in metadata)
            job_status = conn.execute(
                text("SELECT status FROM airank_async_jobs WHERE id=:id"),
                {"id": queued.job_id},
            ).scalar_one()
            assert job_status == "succeeded"
    finally:
        cleanup_tenant(engine, tenant_id)

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.main import (
    BrandCheckRequest,
    BuyerQuestionCreateRequest,
    CompetitorCreateRequest,
    MySQLAssetBundleRepository,
    MySQLProjectRepository,
    MySQLReportRepository,
    MySQLScanRepository,
    ProjectCreateRequest,
    ScanRunCreateRequest,
    run_brand_check,
    scan_dispatch_mode,
)
from apps.api.provider_scan import ProviderScanResult, ProviderUnavailable
from apps.api.delivery_routes import (
    ContentReviewRequest,
    MySQLDeliveryRepository,
    PublishPackageCreateRequest,
)
from apps.api.knowledge_routes import (
    FactConflictCreateRequest,
    FactConflictResolveRequest,
    FactProposalRequest,
    FactRevisionReviewRequest,
    GovernedContentCreateRequest,
    KnowledgeSourceCreateRequest,
    MySQLKnowledgeRepository,
    derive_knowledge_governance,
)
from apps.api.provider_operations import MySQLProviderOperations
from apps.api.evidence_routes import MySQLEvidenceRepository
from apps.api.retest_routes import MySQLRetestRepository
from apps.api.question_routes import (
    MySQLQuestionGovernanceRepository,
    QuestionMapCompileRequest,
    QuestionObservationImportRequest,
    QuestionReviewRequest,
)
from airank_evidence import FilesystemObjectStorage
from airank_provider_gateway import (
    HealthState,
    ImplementationStatus,
    PROVIDER_MANIFESTS,
    ProbeLevel,
    ProbeResult,
    ProviderCapabilities,
    ProviderCapacityLease,
    ProviderGatewayError,
    ProviderManifest,
    ProviderRequestContext,
    resolve_provider_routes,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "xinghe-adapter" / "src"))

from airank_domain import AsyncJob, AsyncJobStatus  # noqa: E402
from airank_worker import (  # noqa: E402
    MySQLJobLeaseStore,
    MySQLPublishExecutionRepository,
    PublisherError,
    PublisherGateway,
    ScanWorkerError,
    run_next_real_scan_job,
    run_next_publish_job,
)
from airank_xinghe_adapter import CapabilityProbe, CapabilityStatus, ProbeConfig  # noqa: E402


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"
EXPECTED_ALEMBIC_HEAD = "20260808_0017"


def require_real_flag(flag: str) -> None:
    if os.getenv(flag) != "1":
        pytest.skip(f"set {flag}=1 to run real integration checks")


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine: Any, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND column_name = 'tenant_id'
                  AND table_name LIKE 'airank\\_%'
                """
            )
        ).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            for table_name in tables:
                conn.execute(
                    text(f"DELETE FROM `{table_name}` WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                )
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def test_real_mysql_alembic_head_and_schema_contract() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    env = {**os.environ, "AIRANK_DATABASE_URL": database_url()}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "apps" / "api",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr

    engine = create_engine(database_url(), pool_pre_ping=True)
    expected_database = engine.url.database
    assert expected_database
    with engine.connect() as conn:
        assert conn.execute(text("SELECT DATABASE()")).scalar_one() == expected_database
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == EXPECTED_ALEMBIC_HEAD
        table_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name LIKE 'airank\\_%'
                """
            )
        ).scalar_one()
        assert table_count == 59
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_provider_request_audits'
                  AND column_name='route_id'
                """
            )
        ).scalar_one() == 1
        for table_name in (
            "airank_provider_route_controls",
            "airank_provider_route_control_events",
        ):
            assert conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema=DATABASE() AND table_name=:table_name
                    """
                ),
                {"table_name": table_name},
            ).scalar_one() == 1

        url_columns = (
            ("airank_projects", "website_url"),
            ("airank_competitors", "website_url"),
            ("airank_source_citations", "url"),
            ("airank_fact_sources", "source_url"),
            ("airank_content_assets", "target_url"),
            ("airank_publish_packages", "published_url"),
            ("airank_object_refs", "object_uri"),
            ("airank_question_observation_batches", "source_uri"),
            ("airank_citation_source_captures", "requested_url"),
            ("airank_citation_source_captures", "final_url"),
        )
        for table_name, column_name in url_columns:
            url_length = conn.execute(
                text(
                    """
                    SELECT CHARACTER_MAXIMUM_LENGTH
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                      AND table_name = :table_name
                      AND column_name = :column_name
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            ).scalar_one()
            assert url_length == 2048


def test_real_s3_compatible_object_storage_probe() -> None:
    require_real_flag("AIRANK_RUN_REAL_OBJECT_STORAGE")
    result = next(
        item
        for item in CapabilityProbe(ProbeConfig.from_env()).run()
        if item.capability == "object_storage"
    )

    assert result.status == CapabilityStatus.READY
    assert result.metadata["driver"] in {"s3", "minio"}
    assert result.metadata["probe"] == "write-read-delete"


def test_real_mysql_project_competitor_question_write_path() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    repo = MySQLProjectRepository(database_url())

    try:
        project = repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-write.example.com",
                brand_name_hint="AIRank Real Write",
                industry_hint="B2B SaaS",
            ),
        )
        competitor = repo.create_competitor(
            tenant_id,
            project.project_id,
            CompetitorCreateRequest(
                name="Real Competitor",
                website_url="https://competitor-real-write.example.com",
                reason="Real MySQL integration write verification.",
                evidence_urls=["https://evidence-real-write.example.com"],
                confidence=0.72,
                source="manual",
            ),
        )
        question = repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="Which AI visibility product should a B2B brand choose?",
                question_type="select",
                intent_level="high",
                buyer_stage="decision",
                source_reason="Real MySQL integration write verification.",
                recommended_providers=["chatgpt", "deepseek"],
                source="manual",
            ),
        )

        with engine.connect() as conn:
            project_row = conn.execute(
                text(
                    """
                    SELECT brand_name, website_url
                    FROM airank_projects
                    WHERE tenant_id = :tenant_id AND id = :project_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).mappings().one()
            assert project_row["brand_name"] == "AIRank Real Write"
            assert project_row["website_url"] == "https://airank-real-write.example.com"

            competitor_meta = conn.execute(
                text(
                    """
                    SELECT metadata_json
                    FROM airank_competitors
                    WHERE tenant_id = :tenant_id AND id = :competitor_id
                    """
                ),
                {"tenant_id": tenant_id, "competitor_id": competitor.competitor_id},
            ).scalar_one()
            assert json.loads(competitor_meta)["evidence_urls"] == ["https://evidence-real-write.example.com"]

            question_meta = conn.execute(
                text(
                    """
                    SELECT metadata_json
                    FROM airank_buyer_questions
                    WHERE tenant_id = :tenant_id AND id = :question_id
                    """
                ),
                {"tenant_id": tenant_id, "question_id": question.question_id},
            ).scalar_one()
            assert json.loads(question_meta)["coverage_status"] == "needs_scan"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_evidence_object_can_be_read_and_integrity_checked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    evidence_repo = MySQLEvidenceRepository(database_url())
    object_root = tmp_path / "objects"
    storage = FilesystemObjectStorage(object_root)
    payload = b"real mysql durable evidence object"
    stored = storage.put_bytes(payload, key="evidence/integration/object.png", content_type="image/png")
    object_ref_id = f"object_it_{uuid4().hex[:10]}"
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "filesystem")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(object_root))

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-object.example.com",
                brand_name_hint="AIRank Real Object",
                industry_hint="B2B SaaS",
            ),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_object_refs (
                      id, tenant_id, project_id, object_type, object_uri,
                      content_type, byte_size, sha256, metadata_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'provider_answer_screenshot', :object_uri,
                      :content_type, :byte_size, :sha256, :metadata_json, :created_at
                    )
                    """
                ),
                {
                    "id": object_ref_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "object_uri": stored.uri,
                    "content_type": stored.content_type,
                    "byte_size": stored.byte_size,
                    "sha256": stored.sha256,
                    "metadata_json": json.dumps(
                        {"object_key": stored.key, "storage_driver": stored.driver, "immutable": True}
                    ),
                    "created_at": datetime.now(timezone.utc),
                },
            )

        evidence_object = evidence_repo.read_object(tenant_id, object_ref_id)
        assert evidence_object.payload == payload
        assert evidence_object.content_type == "image/png"
        assert evidence_object.sha256 == stored.sha256
        with pytest.raises(StarletteHTTPException) as cross_tenant_error:
            evidence_repo.read_object("tenant_other", object_ref_id)
        assert getattr(cross_tenant_error.value, "status_code", None) == 404
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_question_map_review_and_cohort_gate() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_qgov_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    question_repo = MySQLQuestionGovernanceRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-question-governance.example.com",
                brand_name_hint="AIRank Question Governance",
                industry_hint="B2B SaaS",
            ),
        )
        payload = QuestionMapCompileRequest(
            seed_questions=["企业应该如何选择 GEO 监测服务商？", "企业应该如何选择GEO监测服务商!"],
            include_template_candidates=False,
            persist=True,
            created_by="integration_reviewer",
        )
        compiled = question_repo.compile_map(tenant_id, project.project_id, payload, "integration_reviewer")

        assert compiled.question_count == 1
        assert compiled.duplicate_count == 1
        assert compiled.persisted_count == 1
        question = compiled.questions[0]
        assert question.status == "suggested"
        assert question.cohort_type == "blind"
        assert question.observed_query is False
        assert question.question_id

        with pytest.raises(StarletteHTTPException) as unreviewed_error:
            scan_repo.create_run(
                tenant_id,
                ScanRunCreateRequest(
                    project_id=project.project_id,
                    cohort_type="blind",
                    repetitions=1,
                    provider_scope=["deepseek"],
                    question_scope={"mode": "selected", "question_ids": [question.question_id]},
                ),
            )
        assert unreviewed_error.value.status_code == 404

        review = question_repo.review_question(
            tenant_id,
            project.project_id,
            question.question_id,
            QuestionReviewRequest(
                action="confirmed",
                reviewed_by="integration_reviewer",
                review_note="问题与采购阶段及目标用户匹配。",
            ),
            "integration_reviewer",
        )
        assert review.eligible_for_measurement is True

        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                cohort_type="blind",
                repetitions=1,
                provider_scope=["deepseek"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        tasks = scan_repo.list_tasks(tenant_id, run.run_id)
        assert len(tasks) == 1
        assert tasks[0].cohort_type == "blind"

        replay = question_repo.compile_map(tenant_id, project.project_id, payload, "integration_reviewer")
        assert replay.idempotent_replay is True
        assert replay.map_id == compiled.map_id

        with engine.connect() as conn:
            counts = conn.execute(text("""
                SELECT
                  (SELECT COUNT(*) FROM airank_question_maps WHERE tenant_id=:tenant_id) AS map_count,
                  (SELECT COUNT(*) FROM airank_buyer_question_revisions WHERE tenant_id=:tenant_id) AS revision_count,
                  (SELECT COUNT(*) FROM airank_buyer_question_reviews WHERE tenant_id=:tenant_id) AS review_count
            """), {"tenant_id": tenant_id}).mappings().one()
            revision_status = conn.execute(text("""
                SELECT status, reviewed_by, reviewed_at
                FROM airank_buyer_question_revisions
                WHERE tenant_id=:tenant_id AND question_id=:question_id
            """), {"tenant_id": tenant_id, "question_id": question.question_id}).mappings().one()
        assert dict(counts) == {"map_count": 1, "revision_count": 1, "review_count": 1}
        assert revision_status["status"] == "suggested"
        assert revision_status["reviewed_by"] is None
        assert revision_status["reviewed_at"] is None
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_observed_query_batch_is_pii_safe_idempotent_and_compilable() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_qobs_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    question_repo = MySQLQuestionGovernanceRepository(database_url())

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-observed-query.example.com",
                brand_name_hint="AIRank Observed Query",
                industry_hint="B2B SaaS",
            ),
        )
        payload = QuestionObservationImportRequest(
            source_type="site_search",
            source_name="站内搜索导出",
            date_range_start="2026-08-01T00:00:00Z",
            date_range_end="2026-08-07T23:59:59Z",
            records=[
                {
                    "source_record_id": "query-1",
                    "question_text": "制造企业如何选择 GEO 监测平台？",
                    "occurrence_count": 9,
                    "observed_at": "2026-08-06T08:00:00Z",
                    "region": "江苏",
                },
                {
                    "source_record_id": "query-2",
                    "question_text": "请联系 buyer@example.com 获取 GEO 报价",
                    "occurrence_count": 1,
                },
            ],
            rights_attested=True,
            imported_by="integration_researcher",
        )
        imported = question_repo.import_observations(
            tenant_id,
            project.project_id,
            payload,
            "integration_researcher",
        )
        assert imported.batch.status == "ready"
        assert imported.batch.evidence_grade == "user_provided_snapshot"
        assert imported.batch.record_count == 1
        assert imported.batch.occurrence_count == 9
        assert imported.batch.pii_blocked_count == 1
        assert imported.batch.blocked_records[0].reasons == ["email"]
        assert len(imported.records) == 1

        replay = question_repo.import_observations(
            tenant_id,
            project.project_id,
            payload,
            "integration_researcher",
        )
        assert replay.batch.idempotent_replay is True
        assert replay.batch.batch_id == imported.batch.batch_id

        compiled = question_repo.compile_map(
            tenant_id,
            project.project_id,
            QuestionMapCompileRequest(
                observation_batch_ids=[imported.batch.batch_id],
                include_template_candidates=False,
                persist=True,
                created_by="integration_researcher",
            ),
            "integration_researcher",
        )
        assert compiled.question_count == 1
        assert compiled.questions[0].source_kind == "observed_query"
        assert compiled.questions[0].observed_query is True
        assert compiled.questions[0].provenance_records[0]["occurrence_count"] == 9

        with engine.connect() as conn:
            counts = conn.execute(text("""
                SELECT
                  (SELECT COUNT(*) FROM airank_question_observation_batches WHERE tenant_id=:tenant_id) AS batch_count,
                  (SELECT COUNT(*) FROM airank_question_observations WHERE tenant_id=:tenant_id) AS observation_count
            """), {"tenant_id": tenant_id}).mappings().one()
            stored_text = conn.execute(text("""
                SELECT CONCAT(COALESCE(GROUP_CONCAT(question_text), ''),
                              COALESCE(GROUP_CONCAT(normalized_question_text), ''))
                FROM airank_question_observations
                WHERE tenant_id=:tenant_id
            """), {"tenant_id": tenant_id}).scalar_one()
            manifest = conn.execute(text("""
                SELECT CAST(manifest_json AS CHAR)
                FROM airank_question_observation_batches
                WHERE tenant_id=:tenant_id AND id=:batch_id
            """), {"tenant_id": tenant_id, "batch_id": imported.batch.batch_id}).scalar_one()
        assert dict(counts) == {"batch_count": 1, "observation_count": 1}
        assert "buyer@example.com" not in stored_text
        assert "buyer@example.com" not in manifest
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_queue_and_asset_bundle_paths() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    asset_repo = MySQLAssetBundleRepository(database_url())
    evidence_repo = MySQLEvidenceRepository(database_url())
    snapshot_id = f"snapshot_it_{uuid4().hex[:10]}"
    evidence_snapshot_id = f"evidence_it_{uuid4().hex[:10]}"

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-scan.example.com",
                brand_name_hint="AIRank Real Scan",
                industry_hint="B2B SaaS",
            ),
        )
        question_one = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="Which AI visibility platform should our company choose?",
                status="confirmed",
                recommended_providers=["chatgpt"],
            ),
        )
        question_two = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="How should a company compare AI visibility platforms?",
                question_type="compare",
                status="confirmed",
                recommended_providers=["deepseek"],
            ),
        )

        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Real MySQL scan queue verification",
                provider_scope=["chatgpt", "deepseek"],
                question_scope={
                    "mode": "selected",
                    "question_ids": [question_one.question_id, question_two.question_id],
                },
            ),
        )
        tasks = scan_repo.list_tasks(tenant_id, run.run_id)

        assert run.status == "queued"
        assert run.metrics["task_count"] == 12
        assert len(tasks) == 12
        assert {task.provider for task in tasks} == {"chatgpt", "deepseek"}

        with engine.begin() as conn:
            jobs = conn.execute(
                text(
                    """
                    SELECT payload_json
                    FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND job_type = 'scan.provider'
                    ORDER BY created_at ASC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).scalars().all()
            assert len(jobs) == 12
            first_payload = json.loads(jobs[0])
            assert first_payload["run_id"] == run.run_id
            assert first_payload["scan_task_id"].startswith("scan_task_")
            assert first_payload["question_id"] in {question_one.question_id, question_two.question_id}

            sample_task = tasks[0]
            answer_text = "AIRank 是候选方案之一。"
            answer_sha256 = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
            raw_response = {"id": "provider_request_it", "answer": answer_text}
            raw_json = json.dumps(raw_response, ensure_ascii=False, sort_keys=True)
            raw_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, cohort_type, prompt_version_id, sample_index,
                      session_id, collector_surface, evidence_level, sample_status,
                      answer_text, answer_sha256, raw_response_sha256,
                      brand_mentioned, brand_rank, mention_class,
                      target_entity_mentions_json, competitor_mentions_json,
                      sentiment, confidence, model_name, search_enabled,
                      external_trace_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :cohort_type, :prompt_version_id, :sample_index,
                      :session_id, :collector_surface, :evidence_level, 'valid',
                      :answer_text, :answer_sha256, :raw_response_sha256,
                      1, 2, 'candidate', JSON_ARRAY(), JSON_ARRAY(),
                      'neutral', NULL, 'model-it', 1,
                      'provider_request_it', :created_at
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": sample_task.task_id,
                    "question_id": sample_task.question_id,
                    "provider": sample_task.provider,
                    "cohort_type": sample_task.cohort_type,
                    "prompt_version_id": sample_task.prompt_version_id,
                    "sample_index": sample_task.sample_index,
                    "session_id": sample_task.session_id,
                    "collector_surface": sample_task.collector_surface,
                    "evidence_level": sample_task.evidence_level,
                    "answer_text": answer_text,
                    "answer_sha256": answer_sha256,
                    "raw_response_sha256": raw_sha256,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_snapshots (
                      id, tenant_id, project_id, answer_snapshot_id,
                      raw_response_json, raw_response_sha256,
                      request_metadata_json, captured_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :answer_snapshot_id,
                      :raw_response_json, :raw_response_sha256,
                      :request_metadata_json, :captured_at, :captured_at
                    )
                    """
                ),
                {
                    "id": evidence_snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "answer_snapshot_id": snapshot_id,
                    "raw_response_json": raw_json,
                    "raw_response_sha256": raw_sha256,
                    "request_metadata_json": json.dumps({"collector_surface": sample_task.collector_surface}),
                    "captured_at": datetime.now(timezone.utc),
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
                      '真实引用', 'https://evidence.example.com/source',
                      'evidence.example.com', 'provider_native', '支持回答的引用片段', :created_at
                    )
                    """
                ),
                {
                    "id": f"citation_it_{uuid4().hex[:10]}",
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "snapshot_id": snapshot_id,
                    "created_at": datetime.now(timezone.utc),
                },
            )

            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_assets (
                      id, tenant_id, project_id, asset_type, title, body_md, status
                    )
                    VALUES (
                      'asset_real_fact_page', :tenant_id, :project_id,
                      'fact_page', '企业事实页', '真实 MySQL 资产包验证', 'approved'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_publish_packages (
                      id, tenant_id, project_id, asset_id, status
                    )
                    VALUES (
                      'pkg_real_fact_page', :tenant_id, :project_id,
                      'asset_real_fact_page', 'published'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_gaps (
                      id, tenant_id, project_id, title, severity, suggested_asset_type, status
                    )
                    VALUES (
                      'gap_real_case', :tenant_id, :project_id,
                      '缺少客户案例页', 'high', 'case_page', 'open'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )

        bundle = asset_repo.get_bundle(tenant_id, project.project_id)
        samples, sample_aggregates = evidence_repo.list_samples(
            tenant_id,
            project.project_id,
            run.run_id,
            100,
        )
        detail = evidence_repo.get_sample(tenant_id, snapshot_id)
        assert bundle.assets[0].asset_id == "asset_real_fact_page"
        assert bundle.assets[0].progress == 100
        assert "1 个内容缺口" in bundle.recommendation
        assert [sample.snapshot_id for sample in samples] == [snapshot_id]
        assert sample_aggregates == {
            "total": 1,
            "valid_count": 1,
            "valid_unmentioned_count": 0,
            "citation_sample_count": 1,
        }
        assert detail.answer_text == "AIRank 是候选方案之一。"
        assert detail.citation_count == 1
        assert detail.citations[0].url == "https://evidence.example.com/source"
        assert detail.raw_response["id"] == "provider_request_it"
        assert detail.screenshot.object_ref_id is None

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='failed', error_code='provider_not_executed'
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='completed', error_code=NULL
                    WHERE tenant_id=:tenant_id AND id=:task_id
                    """
                ),
                {"tenant_id": tenant_id, "task_id": tasks[0].task_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_runs
                    SET status='completed'
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            )
        quality = MySQLRetestRepository(database_url()).get_quality_report(
            tenant_id,
            project.project_id,
            run.run_id,
        )
        assert quality["publishable"] is False
        assert quality["metrics"]["total_sample_count"] == 12
        assert quality["metrics"]["valid_sample_count"] == 1
        assert {item["code"] for item in quality["checks"] if item["status"] == "blocked"} >= {
            "valid_sample_rate",
            "raw_response_hashes_present",
            "consumer_conversation_isolation_verified",
            "consumer_screenshots_complete",
            "consumer_source_panels_inspected",
            "consumer_source_panel_evidence_consistent",
        }
        assert quality["surface_evidence"] == [
            {
                "surface": "web",
                "evidence_level": "consumer_web",
                "sample_count": 12,
                "valid_sample_count": 1,
                "evidence_complete_count": 0,
                "screenshot_count": 0,
                "source_panel_captured_count": 0,
                "source_panel_not_present_count": 0,
                "blocker_count": 1,
            }
        ]
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_brand_check_defaults_to_durable_worker_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_worker_dispatch_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")
    monkeypatch.delenv("AIRANK_SCAN_DISPATCH_MODE", raising=False)

    try:
        assert scan_dispatch_mode() == "worker"
        result = run_brand_check(
            tenant_id,
            BrandCheckRequest(
                brand_name="AIRank Worker Dispatch",
                website_url="https://airank-worker-dispatch.example.com",
                industry_hint="B2B SaaS",
                buyer_questions=["企业应该如何选择 GEO 监测服务商？"],
            ),
        )

        assert result.scan_run.status == "queued"
        assert {task.status for task in result.tasks} == {"queued"}
        with engine.connect() as conn:
            counts = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM airank_async_jobs
                       WHERE tenant_id=:tenant_id AND job_type='scan.provider'
                         AND status='queued') AS queued_jobs,
                      (SELECT COUNT(*) FROM airank_answer_snapshots
                       WHERE tenant_id=:tenant_id) AS snapshot_count
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().one()
        assert counts["queued_jobs"] == len(result.tasks)
        assert counts["snapshot_count"] == 0
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_worker_fail_closes_only_expired_task_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_scan_lease_expiry_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")

    def provider_must_not_run(**_kwargs: Any) -> ProviderScanResult:
        raise AssertionError("expired run lease must not replay Provider calls")

    monkeypatch.setattr("apps.api.main.call_api_provider_for_brand_rank", provider_must_not_run)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-scan-lease.example.com",
                brand_name_hint="AIRank Scan Lease",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业如何选择可审计的 GEO 监测服务？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Expired worker lease",
                repetitions=2,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        store = MySQLJobLeaseStore(database_url())
        owner_started_at = datetime.now(timezone.utc)
        owner_job = store.claim_next(
            "scan-worker-that-crashes",
            owner_started_at,
            job_types={"scan.provider"},
            tenant_id=tenant_id,
        )
        assert owner_job is not None
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_runs
                    SET status='running', started_at=:started_at, updated_at=:started_at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id, "started_at": owner_started_at},
            )

            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='running', attempt_count=1,
                        started_at=:started_at, updated_at=:started_at
                    WHERE tenant_id=:tenant_id AND id=:task_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "task_id": owner_job.payload["scan_task_id"],
                    "started_at": owner_started_at,
                },
            )

        recovered = run_next_real_scan_job(
            store,
            worker_id="scan-recovery-worker",
            now=owner_started_at + timedelta(seconds=owner_job.timeout_seconds + 1),
            tenant_id=tenant_id,
        )
        assert recovered is not None
        assert recovered.status == "failed"
        assert recovered.task_count == 2
        assert recovered.failed_count == 1

        with engine.connect() as conn:
            run_row = conn.execute(
                text("SELECT status, error_message FROM airank_scan_runs WHERE tenant_id=:tenant_id AND id=:run_id"),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().one()
            task_rows = conn.execute(
                text(
                    """
                    SELECT status, error_code FROM airank_scan_tasks
                    WHERE tenant_id=:tenant_id AND run_id=:run_id ORDER BY id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
            job_rows = conn.execute(
                text(
                    """
                    SELECT status, error_code FROM airank_async_jobs
                    WHERE tenant_id=:tenant_id
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id'))=:run_id
                    ORDER BY id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
            evidence_rows = conn.execute(
                text(
                    """
                    SELECT a.answer_text, a.answer_sha256, a.raw_response_sha256,
                           a.sample_status, e.raw_response_json, e.raw_response_sha256 AS evidence_sha256
                    FROM airank_answer_snapshots a
                    JOIN airank_evidence_snapshots e
                      ON e.tenant_id=a.tenant_id AND e.answer_snapshot_id=a.id
                    WHERE a.tenant_id=:tenant_id AND a.run_id=:run_id
                    ORDER BY a.id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
            attempt_rows = conn.execute(
                text(
                    """
                    SELECT status, attempt_number, answer_snapshot_id, evidence_snapshot_id,
                           error_code, completed_at
                    FROM airank_scan_task_attempts
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    ORDER BY attempt_number, id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()

        assert run_row["status"] == "running"
        assert run_row["error_message"] is None
        assert {(row["status"], row["error_code"]) for row in task_rows} == {
            ("failed", "SCAN_TASK_LEASE_EXPIRED"),
            ("queued", None),
        }
        assert sorted(row["status"] for row in job_rows) == ["failed", "queued"]
        assert len(evidence_rows) == 1
        assert len(attempt_rows) == 1
        assert attempt_rows[0]["status"] == "unknown"
        assert attempt_rows[0]["attempt_number"] == 1
        assert attempt_rows[0]["answer_snapshot_id"]
        assert attempt_rows[0]["evidence_snapshot_id"]
        assert attempt_rows[0]["error_code"] == "SCAN_TASK_LEASE_EXPIRED"
        assert attempt_rows[0]["completed_at"] is not None
        for row in evidence_rows:
            raw = json.loads(row["raw_response_json"])
            assert row["answer_text"] == ""
            assert row["answer_sha256"] is None
            assert row["sample_status"] == "failed"
            assert row["raw_response_sha256"] == row["evidence_sha256"]
            assert raw["failure"]["error_code"] == "SCAN_TASK_LEASE_EXPIRED"
            assert raw["failure"]["automatic_replay_suppressed"] is True
            assert raw["capture_metadata"]["provider_response_available"] is False
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_worker_internal_failure_preserves_only_claimed_task_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_scan_internal_failure_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-worker-failure.example.com",
                brand_name_hint="AIRank Worker Failure",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业如何验证 GEO 采样可追溯？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Worker internal failure evidence",
                repetitions=2,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )

        def fail_before_provider(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("simulated internal dependency failure")

        monkeypatch.setattr("apps.api.main.get_mysql_project", fail_before_provider)
        with pytest.raises(ScanWorkerError) as caught:
            run_next_real_scan_job(
                MySQLJobLeaseStore(database_url()),
                worker_id="scan-internal-failure-worker",
                tenant_id=tenant_id,
            )
        assert caught.value.code == "SCAN_WORKER_INTERNAL_ERROR"
        assert caught.value.retryable is False

        with engine.connect() as conn:
            counts = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM airank_scan_tasks
                       WHERE tenant_id=:tenant_id AND run_id=:run_id
                         AND status='failed' AND error_code='SCAN_WORKER_INTERNAL_ERROR') AS failed_tasks,
                      (SELECT COUNT(*) FROM airank_async_jobs
                       WHERE tenant_id=:tenant_id
                         AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id'))=:run_id
                         AND status='failed' AND error_code='SCAN_WORKER_INTERNAL_ERROR') AS failed_jobs,
                      (SELECT COUNT(*) FROM airank_answer_snapshots
                       WHERE tenant_id=:tenant_id AND run_id=:run_id
                         AND sample_status='failed' AND raw_response_sha256 IS NOT NULL) AS failure_snapshots,
                      (SELECT status FROM airank_scan_runs
                       WHERE tenant_id=:tenant_id AND id=:run_id) AS run_status
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().one()
            attempt_statuses = conn.execute(
                text(
                    """
                    SELECT status, error_code, answer_snapshot_id, evidence_snapshot_id
                    FROM airank_scan_task_attempts
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
        assert counts == {
            "failed_tasks": 1,
            "failed_jobs": 1,
            "failure_snapshots": 1,
            "run_status": "running",
        }
        assert len(attempt_statuses) == 1
        assert attempt_statuses[0]["status"] == "failed"
        assert attempt_statuses[0]["error_code"] == "SCAN_WORKER_INTERNAL_ERROR"
        assert attempt_statuses[0]["answer_snapshot_id"]
        assert attempt_statuses[0]["evidence_snapshot_id"]
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_preserves_failed_task_as_immutable_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_failure_evidence_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    evidence_repo = MySQLEvidenceRepository(database_url())
    quality_repo = MySQLRetestRepository(database_url())
    calls = 0

    def provider_call(**kwargs: Any) -> ProviderScanResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ProviderUnavailable("doubao", "login required for this isolated browser session")
        answer_text = "可选方案包括其他平台，当前回答未提及目标品牌。"
        return ProviderScanResult(
            provider="doubao",
            provider_label="豆包",
            answer_text=answer_text,
            brand_mentioned=False,
            brand_rank=None,
            competitor_mentions=[],
            sentiment="neutral",
            mention_class="not_mentioned",
            target_entity_mentions=[],
            confidence=None,
            external_trace_id="browser:failure-evidence:1",
            native_citations=[],
            raw_metadata={
                "capture_mode": "consumer_browser",
                "collector_surface": "web",
                "evidence_level": "consumer_web",
                "cohort_type": kwargs["cohort_type"],
                "session_id": kwargs["session_id"],
                "prompt_version_id": kwargs["prompt_version_id"],
                "prompt_sha256": "a" * 64,
                "answer_sha256": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
                "source_panel_status": "not_present",
                "source_panel_capture_mode": "visible_page_inspected_no_sources",
            },
        )

    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "browser")
    monkeypatch.setattr("apps.api.main.call_provider_for_brand_rank", provider_call)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-failure-evidence.example.com",
                brand_name_hint="AIRank Failure Evidence",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业应该如何选择 GEO 监测服务商？",
                status="confirmed",
                recommended_providers=["doubao"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Immutable failed sample evidence",
                repetitions=2,
                collector_surfaces=["web"],
                provider_scope=["doubao"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )

        lease_store = MySQLJobLeaseStore(database_url())
        first_dispatch = run_next_real_scan_job(
            lease_store,
            worker_id="scan-integration-worker",
            tenant_id=tenant_id,
        )
        assert first_dispatch is not None
        assert first_dispatch.run_id == run.run_id
        assert first_dispatch.status == "completed"
        assert first_dispatch.task_count == 2
        assert first_dispatch.completed_count == 1
        assert first_dispatch.failed_count == 0
        with engine.connect() as conn:
            durable_mid_run = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT status FROM airank_scan_runs
                       WHERE tenant_id=:tenant_id AND id=:run_id) AS run_status,
                      (SELECT COUNT(*) FROM airank_answer_snapshots
                       WHERE tenant_id=:tenant_id AND run_id=:run_id) AS snapshot_count,
                      (SELECT COUNT(*) FROM airank_scan_tasks
                       WHERE tenant_id=:tenant_id AND run_id=:run_id AND status='queued') AS queued_count
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().one()
        assert durable_mid_run == {"run_status": "running", "snapshot_count": 1, "queued_count": 1}

        dispatch = run_next_real_scan_job(
            lease_store,
            worker_id="scan-integration-worker",
            tenant_id=tenant_id,
        )
        assert dispatch is not None
        assert dispatch.run_id == run.run_id
        assert dispatch.status == "failed"
        assert dispatch.task_count == 2
        assert dispatch.completed_count == 1
        assert dispatch.failed_count == 1

        with engine.connect() as conn:
            job_rows = conn.execute(
                text(
                    """
                    SELECT id, status FROM airank_async_jobs
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id'))=:run_id
                    ORDER BY id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id},
            ).mappings().all()
        assert sorted(row["status"] for row in job_rows) == ["failed", "succeeded"]
        with engine.connect() as conn:
            attempt_rows = conn.execute(
                text(
                    """
                    SELECT status, attempt_number, answer_snapshot_id, evidence_snapshot_id
                    FROM airank_scan_task_attempts
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    ORDER BY status, id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
        assert {row["status"] for row in attempt_rows} == {"blocked", "succeeded"}
        assert {row["attempt_number"] for row in attempt_rows} == {1}
        assert all(row["answer_snapshot_id"] and row["evidence_snapshot_id"] for row in attempt_rows)

        failed_job_id = next(row["id"] for row in job_rows if row["status"] == "failed")
        lease_store.requeue_for_retry(failed_job_id, datetime.now(timezone.utc))
        replay = run_next_real_scan_job(
            lease_store,
            worker_id="scan-integration-worker",
            tenant_id=tenant_id,
        )
        assert replay is not None
        assert replay.status == "failed"
        assert replay.idempotent_replay is True
        assert calls == 2
        with engine.connect() as conn:
            snapshot_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_answer_snapshots
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).scalar_one()
        assert snapshot_count == 2

        samples, summary = evidence_repo.list_samples(tenant_id, project.project_id, run.run_id, 20)
        assert summary == {
            "total": 2,
            "valid_count": 1,
            "valid_unmentioned_count": 1,
            "citation_sample_count": 0,
        }
        assert {sample.sample_status for sample in samples} == {"valid", "blocked"}
        blocked_sample = next(sample for sample in samples if sample.sample_status == "blocked")
        assert blocked_sample.answer_sha256 is None
        detail = evidence_repo.get_sample(tenant_id, blocked_sample.snapshot_id)
        assert detail.answer_text == ""
        assert detail.raw_response_sha256
        assert detail.raw_response["sample_status"] == "blocked"
        assert detail.raw_response["failure"]["error_code"] == "SCAN_PROVIDER_BLOCKED"
        assert detail.request_metadata["failure"]["blocked"] is True
        assert len(detail.attempts) == 1
        assert detail.attempts[0].status == "blocked"
        assert detail.attempts[0].attempt_number == 1
        assert detail.attempts[0].answer_snapshot_id == blocked_sample.snapshot_id
        assert detail.attempts[0].evidence_snapshot_id == detail.evidence_snapshot_id

        quality = quality_repo.get_quality_report(tenant_id, project.project_id, run.run_id)
        raw_hash_check = next(check for check in quality["checks"] if check["code"] == "raw_response_hashes_present")
        assert raw_hash_check["status"] == "pass"
        assert quality["metrics"]["failed_sample_count"] == 0
        assert quality["metrics"]["blocked_sample_count"] == 1
        assert quality["metrics"]["not_mentioned_count"] == 1
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_failed_scan_remains_quality_auditable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_failed_quality_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())

    def blocked_provider(**_kwargs: Any) -> ProviderScanResult:
        raise ProviderUnavailable("qianwen", "captcha required")

    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "browser")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "local")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setattr("apps.api.main.call_provider_for_brand_rank", blocked_provider)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-failed-quality.example.com",
                brand_name_hint="AIRank Failed Quality",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业应该如何选择可审计的 GEO 监测服务商？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Failed run quality audit",
                repetitions=1,
                collector_surfaces=["web"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )

        dispatch = run_next_real_scan_job(
            MySQLJobLeaseStore(database_url()),
            worker_id="failed-quality-worker",
            tenant_id=tenant_id,
        )
        assert dispatch is not None
        assert dispatch.status == "failed"

        quality = MySQLRetestRepository(database_url()).get_quality_report(
            tenant_id,
            project.project_id,
            run.run_id,
        )
        run_status_check = next(
            check for check in quality["checks"] if check["code"] == "run_status_publishable"
        )
        assert quality["publishable"] is False
        assert quality["metrics"]["blocked_sample_count"] == 1
        assert run_status_check["status"] == "blocked"
        assert run_status_check["actual"] == "failed"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_report_repository_and_download_receipt() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    report_repo = MySQLReportRepository(database_url())

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-report.example.com",
                brand_name_hint="AIRank Real Report",
                industry_hint="B2B SaaS",
            ),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title, status,
                      metrics_json, generated_at
                    )
                    VALUES (
                      'report_real_exec', :tenant_id, :project_id, 'executive',
                      'AIRank 真实诊断报告', 'generated',
                      JSON_OBJECT(
                        'summary', '真实 MySQL 报告列表验证',
                        'report_status', 'generated',
                        'baseline_quality', JSON_OBJECT('contract_version', 'airank.measurement-quality.v4', 'publishable', TRUE),
                        'compare_quality', JSON_OBJECT('contract_version', 'airank.measurement-quality.v4', 'publishable', TRUE)
                      ),
                      CURRENT_TIMESTAMP(3)
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )

        report_list = report_repo.list_reports(tenant_id, project.project_id)
        assert [report.report_id for report in report_list.reports] == ["report_real_exec"]
        assert report_list.reports[0].desc == "真实 MySQL 报告列表验证"

        receipt = report_repo.record_download_receipt(tenant_id, "report_real_exec", "trc_real_report")
        assert receipt.status == "recorded"

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title, status,
                      metrics_json, generated_at
                    ) VALUES (
                      'report_real_blocked', :tenant_id, :project_id, 'retest',
                      'AIRank 质量阻断报告', 'quality_blocked',
                      JSON_OBJECT('report_status', 'quality_blocked'),
                      CURRENT_TIMESTAMP(3)
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )
        with pytest.raises(StarletteHTTPException) as blocked_download:
            report_repo.record_download_receipt(tenant_id, "report_real_blocked", "trc_real_blocked")
        assert blocked_download.value.status_code == 409
        assert blocked_download.value.detail["code"] == "REPORT_QUALITY_BLOCKED"

        with engine.connect() as conn:
            audit = conn.execute(
                text(
                    """
                    SELECT event_type, entity_type, entity_id, trace_id, payload_json
                    FROM airank_audit_events
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().one()
        assert audit["event_type"] == "report.download_receipt"
        assert audit["entity_type"] == "report"
        assert audit["entity_id"] == "report_real_exec"
        assert audit["trace_id"] == "trc_real_report"
        assert json.loads(audit["payload_json"])["report_id"] == "report_real_exec"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_worker_lease_store_claims_and_completes_job() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    store = MySQLJobLeaseStore(database_url())
    now = utc_datetime() - timedelta(days=1)
    job_id = f"job_{uuid4().hex[:12]}"

    try:
        store.add(
            AsyncJob(
                id=job_id,
                tenant_id=tenant_id,
                project_id=None,
                job_type="scan.provider",
                priority=-1000,
                scheduled_at=now,
                payload={"provider": "chatgpt"},
            )
        )

        claim_time = utc_datetime()
        claimed = store.claim_next("worker-real-it", claim_time)
        assert claimed is not None
        assert claimed.id == job_id
        assert claimed.status == AsyncJobStatus.RUNNING
        assert claimed.locked_by == "worker-real-it"
        assert claimed.payload == {"provider": "chatgpt"}

        heartbeat = store.heartbeat(claimed.id, "worker-real-it", claim_time)
        assert heartbeat.heartbeat_at == claim_time

        finished = store.succeed(claimed.id, "worker-real-it", claim_time, {"snapshots": 1})
        assert finished.status == AsyncJobStatus.SUCCEEDED
        assert finished.result == {"snapshots": 1}

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, locked_by, result_json
                    FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id AND id = :job_id
                    """
                ),
                {"tenant_id": tenant_id, "job_id": claimed.id},
            ).mappings().one()
        assert row["status"] == "succeeded"
        assert row["locked_by"] == "worker-real-it"
        assert json.loads(row["result_json"]) == {"snapshots": 1}
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_provider_operations_are_shared_and_idempotent() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_provider_{uuid4().hex[:10]}"
    provider = f"provider_{uuid4().hex[:8]}"
    fingerprint = "a" * 64
    engine = create_engine(database_url(), pool_pre_ping=True)
    env = {
        "AIRANK_PROVIDER_CIRCUIT_FAILURE_THRESHOLD": "1",
        "AIRANK_PROVIDER_CIRCUIT_COOLDOWN_SECONDS": "1",
        "AIRANK_PROVIDER_DEFAULT_QUOTA_UNITS": "1",
        "AIRANK_PROVIDER_QUOTA_RESERVATION_TTL_SECONDS": "30",
        "AIRANK_PROVIDER_QPS": "1",
        "AIRANK_PROVIDER_CONCURRENCY": "1",
    }
    first_worker = MySQLProviderOperations(database_url(), env=env)
    second_worker = MySQLProviderOperations(database_url(), env=env)
    context = ProviderRequestContext(
        tenant_id=tenant_id,
        project_id="project_provider_it",
        idempotency_key="scan_task_provider_it",
    )
    race_tenant_id = f"{tenant_id}_race"
    capacity_tenant_id = f"{tenant_id}_capacity"

    try:
        reservation = first_worker.reserve(provider, context=context)
        with pytest.raises(ProviderGatewayError) as duplicate_error:
            second_worker.reserve(provider, context=context)
        assert duplicate_error.value.code == "PROVIDER_REQUEST_IN_PROGRESS"
        assert duplicate_error.value.retryable is True

        second_worker.commit(reservation)
        with engine.connect() as conn:
            bucket = conn.execute(
                text(
                    """
                    SELECT used_units, reserved_units
                    FROM airank_provider_quota_buckets
                    WHERE tenant_id = :tenant_id AND provider_key = :provider_key
                    """
                ),
                {"tenant_id": tenant_id, "provider_key": provider},
            ).mappings().one()
        assert int(bucket["used_units"]) == 1
        assert int(bucket["reserved_units"]) == 0

        with pytest.raises(ProviderGatewayError) as quota_error:
            first_worker.reserve(
                provider,
                context=ProviderRequestContext(
                    tenant_id=tenant_id,
                    project_id="project_provider_it",
                    idempotency_key="scan_task_provider_it_2",
                ),
            )
        assert quota_error.value.code == "PROVIDER_QUOTA_EXHAUSTED"

        def reserve_from_worker(index: int) -> str:
            worker = first_worker if index == 1 else second_worker
            try:
                return worker.reserve(
                    provider,
                    context=ProviderRequestContext(
                        tenant_id=race_tenant_id,
                        project_id="project_provider_race",
                        idempotency_key=f"scan_task_race_{index}",
                    ),
                ).reservation_id
            except ProviderGatewayError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            race_results = list(executor.map(reserve_from_worker, (1, 2)))
        assert sum(result.startswith("quota_") for result in race_results) == 1
        assert race_results.count("PROVIDER_QUOTA_EXHAUSTED") == 1

        capacity_context_1 = ProviderRequestContext(
            tenant_id=capacity_tenant_id,
            project_id="project_provider_capacity",
            idempotency_key="capacity_task_1",
        )
        capacity_context_2 = ProviderRequestContext(
            tenant_id=capacity_tenant_id,
            project_id="project_provider_capacity",
            idempotency_key="capacity_task_2",
        )
        capacity_context_3 = ProviderRequestContext(
            tenant_id=capacity_tenant_id,
            project_id="project_provider_capacity",
            idempotency_key="capacity_task_3",
        )
        capacity_lease_1 = first_worker.acquire_capacity(
            provider, fingerprint, context=capacity_context_1
        )
        with pytest.raises(ProviderGatewayError) as concurrency_error:
            second_worker.acquire_capacity(
                provider, fingerprint, context=capacity_context_2
            )
        assert concurrency_error.value.code == "PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED"
        assert concurrency_error.value.retryable is True

        first_worker.release_capacity(capacity_lease_1)
        with pytest.raises(ProviderGatewayError) as rate_error:
            second_worker.acquire_capacity(
                provider, fingerprint, context=capacity_context_2
            )
        assert rate_error.value.code == "PROVIDER_DISTRIBUTED_RATE_LIMITED"
        assert rate_error.value.retryable is True

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_capacity_states
                    SET available_tokens=0, last_refill_at=:last_refill_at
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    """
                ),
                {
                    "last_refill_at": datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(seconds=2),
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )
        capacity_lease_2 = second_worker.acquire_capacity(
            provider, fingerprint, context=capacity_context_2
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_capacity_leases
                    SET expires_at=:expired_at WHERE id=:lease_id
                    """
                ),
                {
                    "expired_at": datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(seconds=1),
                    "lease_id": capacity_lease_2.lease_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_capacity_states
                    SET available_tokens=0, last_refill_at=:last_refill_at
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    """
                ),
                {
                    "last_refill_at": datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(seconds=2),
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )
        recovered_lease = first_worker.acquire_capacity(
            provider, fingerprint, context=capacity_context_3
        )
        with engine.connect() as conn:
            capacity_state = conn.execute(
                text(
                    """
                    SELECT in_flight_count FROM airank_provider_capacity_states
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    """
                ),
                {
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            ).scalar_one()
            expired_status = conn.execute(
                text(
                    "SELECT status FROM airank_provider_capacity_leases WHERE id=:lease_id"
                ),
                {"lease_id": capacity_lease_2.lease_id},
            ).scalar_one()
        assert int(capacity_state) == 1
        assert expired_status == "expired"
        first_worker.release_capacity(recovered_lease)

        race_fingerprint = "b" * 64

        def acquire_capacity_from_worker(index: int) -> str:
            worker = first_worker if index == 1 else second_worker
            try:
                return worker.acquire_capacity(
                    provider,
                    race_fingerprint,
                    context=ProviderRequestContext(
                        tenant_id=capacity_tenant_id,
                        project_id="project_provider_capacity_race",
                        idempotency_key=f"capacity_race_{index}",
                    ),
                ).lease_id
            except ProviderGatewayError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            capacity_race_results = list(
                executor.map(acquire_capacity_from_worker, (1, 2))
            )
        assert sum(result.startswith("capacity_") for result in capacity_race_results) == 1
        assert capacity_race_results.count(
            "PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED"
        ) == 1
        winning_capacity_lease_id = next(
            result for result in capacity_race_results if result.startswith("capacity_")
        )
        first_worker.release_capacity(
            ProviderCapacityLease(
                provider=provider,
                configuration_fingerprint=race_fingerprint,
                tenant_id=capacity_tenant_id,
                lease_id=winning_capacity_lease_id,
            )
        )

        first_worker.failure(provider, fingerprint, retryable=True)
        assert second_worker.allow(provider, fingerprint) is False
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_circuit_states
                    SET opened_at = :opened_at
                    WHERE provider_key = :provider_key
                      AND configuration_fingerprint = :configuration_fingerprint
                    """
                ),
                {
                    "opened_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=2),
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )
        assert first_worker.allow(provider, fingerprint) is True
        assert second_worker.allow(provider, fingerprint) is False
        second_worker.success(provider, fingerprint)
        assert first_worker.allow(provider, fingerprint) is True

        checked_at = datetime.now(timezone.utc)
        first_worker.record_probe(
            ProbeResult(
                provider=provider,
                level=ProbeLevel.GENERATION,
                state=HealthState.HEALTHY,
                checked_at=checked_at,
                duration_ms=12,
                model="model-it",
                endpoint_host="provider.example.test",
                request_id_present=True,
            )
        )
        with engine.connect() as conn:
            probe = conn.execute(
                text(
                    """
                    SELECT health_state, request_id_present
                    FROM airank_provider_probe_runs
                    WHERE provider_key = :provider_key
                    ORDER BY checked_at DESC LIMIT 1
                    """
                ),
                {"provider_key": provider},
            ).mappings().one()
        assert probe["health_state"] == "healthy"
        assert bool(probe["request_id_present"]) is True
    finally:
        cleanup_tenant(engine, capacity_tenant_id)
        cleanup_tenant(engine, race_tenant_id)
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM airank_provider_probe_runs WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
            conn.execute(
                text("DELETE FROM airank_provider_circuit_states WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
            conn.execute(
                text("DELETE FROM airank_provider_capacity_states WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_provider_route_manifests_are_public_and_versioned() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    provider = f"provider_route_{uuid4().hex[:8]}"
    route_id = f"route-{uuid4().hex[:8]}"
    route_env = f"{provider.upper()}_ROUTES_JSON"
    engine = create_engine(database_url(), pool_pre_ping=True)
    env = {
        "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
        "ROUTE_TEST_PRIMARY_KEY": "secret-route-value-never-persisted",
        route_env: json.dumps(
            [
                {
                    "route_id": route_id,
                    "priority": 100,
                    "endpoint": "https://route-primary.example.test/v1/chat/completions",
                    "model": "route-model-v1",
                    "key_env": "ROUTE_TEST_PRIMARY_KEY",
                }
            ]
        ),
    }
    manifest = ProviderManifest(
        provider=provider,
        label="Provider Route Integration",
        implementation_status=ImplementationStatus.PARTIAL,
        collection_mode="provider_api",
        endpoint_env=f"{provider.upper()}_API_URL",
        endpoint_default="https://route-default.example.test/v1/chat/completions",
        key_env=f"{provider.upper()}_API_KEY",
        model_env=f"{provider.upper()}_MODEL",
        model_default="route-model-default",
        disabled_env=f"{provider.upper()}_DISABLED",
        request_kind="openai_chat",
        capabilities=ProviderCapabilities(web_search=False, citations=False),
        allowed_endpoint_hosts=("route-primary.example.test",),
    )
    operations = MySQLProviderOperations(database_url(), env=env)

    try:
        operations.sync_manifests([manifest])
        with engine.connect() as conn:
            first = conn.execute(
                text(
                    """
                    SELECT route_id, priority, endpoint_host, model_name,
                           configuration_fingerprint, is_current
                    FROM airank_provider_routes
                    WHERE provider_key=:provider_key AND route_id=:route_id
                    """
                ),
                {"provider_key": provider, "route_id": route_id},
            ).mappings().one()
        assert first["endpoint_host"] == "route-primary.example.test"
        assert first["model_name"] == "route-model-v1"
        assert len(str(first["configuration_fingerprint"])) == 64
        assert bool(first["is_current"]) is True
        assert "secret-route-value-never-persisted" not in json.dumps(
            dict(first), default=str
        )

        env[route_env] = json.dumps(
            [
                {
                    "route_id": route_id,
                    "priority": 100,
                    "endpoint": "https://route-primary.example.test/v1/chat/completions",
                    "model": "route-model-v2",
                    "key_env": "ROUTE_TEST_PRIMARY_KEY",
                }
            ]
        )
        operations.sync_manifests([manifest])
        with engine.connect() as conn:
            versions = conn.execute(
                text(
                    """
                    SELECT model_name, is_current FROM airank_provider_routes
                    WHERE provider_key=:provider_key AND route_id=:route_id
                    ORDER BY created_at, route_version
                    """
                ),
                {"provider_key": provider, "route_id": route_id},
            ).mappings().all()
        assert len(versions) == 2
        assert sum(bool(row["is_current"]) for row in versions) == 1
        assert next(row["model_name"] for row in versions if row["is_current"]) == "route-model-v2"
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM airank_provider_routes WHERE provider_key=:provider_key"),
                {"provider_key": provider},
            )
            conn.execute(
                text("DELETE FROM airank_provider_manifests WHERE provider_key=:provider_key"),
                {"provider_key": provider},
            )


def test_real_mysql_provider_route_controls_apply_without_restart_and_are_audited() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    suffix = uuid4().hex[:8]
    primary_route = f"primary-{suffix}"
    secondary_route = f"secondary-{suffix}"
    env = {
        "QIANWEN_API_KEY": "default-secret-never-persisted",
        "QIANWEN_MODEL": "qwen-default",
        "QIANWEN_PRIMARY_TEST_KEY": "primary-secret-never-persisted",
        "QIANWEN_SECONDARY_TEST_KEY": "secondary-secret-never-persisted",
        "QIANWEN_ROUTES_JSON": json.dumps(
            [
                {
                    "route_id": primary_route,
                    "priority": 100,
                    "model": "qwen-primary-test",
                    "key_env": "QIANWEN_PRIMARY_TEST_KEY",
                },
                {
                    "route_id": secondary_route,
                    "priority": 50,
                    "model": "qwen-secondary-test",
                    "key_env": "QIANWEN_SECONDARY_TEST_KEY",
                },
            ]
        ),
    }
    engine = create_engine(database_url(), pool_pre_ping=True)
    operations = MySQLProviderOperations(database_url(), env=env)
    configured = resolve_provider_routes(PROVIDER_MANIFESTS["qianwen"], env)

    try:
        record = operations.set_route_control(
            "qianwen",
            primary_route,
            enabled=False,
            priority_override=None,
            expected_version=0,
            changed_by="integration-route-admin",
            reason="planned primary maintenance",
        )
        assert record["control_version"] == 1
        assert [route.route_id for route in operations.apply_routes("qianwen", configured)] == [
            secondary_route
        ]
        route_status = operations.list_route_status([PROVIDER_MANIFESTS["qianwen"]])
        primary_status = next(item for item in route_status if item["route_id"] == primary_route)
        secondary_status = next(item for item in route_status if item["route_id"] == secondary_route)
        assert primary_status["enabled"] is False
        assert primary_status["control_version"] == 1
        assert primary_status["request_count_24h"] == 0
        assert secondary_status["enabled"] is True
        assert secondary_status["effective_priority"] == 50
        assert "secret-never-persisted" not in json.dumps(route_status, default=str)

        with pytest.raises(ProviderGatewayError) as stale:
            operations.set_route_control(
                "qianwen",
                primary_route,
                enabled=True,
                priority_override=200,
                expected_version=0,
                changed_by="stale-admin",
                reason="stale update",
            )
        assert stale.value.code == "PROVIDER_ROUTE_CONTROL_CONFLICT"

        with pytest.raises(ProviderGatewayError) as last_route:
            operations.set_route_control(
                "qianwen",
                secondary_route,
                enabled=False,
                priority_override=None,
                expected_version=0,
                changed_by="integration-route-admin",
                reason="must not disable all routes",
            )
        assert last_route.value.code == "PROVIDER_LAST_ROUTE_DISABLE_FORBIDDEN"

        with engine.connect() as conn:
            event = conn.execute(
                text(
                    """
                    SELECT previous_control_json, new_control_json, changed_by, reason
                    FROM airank_provider_route_control_events
                    WHERE provider_key='qianwen' AND route_id=:route_id
                    """
                ),
                {"route_id": primary_route},
            ).mappings().one()
        serialized = json.dumps(dict(event), default=str)
        assert event["changed_by"] == "integration-route-admin"
        assert "planned primary maintenance" in serialized
        assert "secret-never-persisted" not in serialized
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DELETE FROM airank_provider_route_control_events
                    WHERE provider_key='qianwen' AND route_id IN (:primary_route, :secondary_route)
                    """
                ),
                {"primary_route": primary_route, "secondary_route": secondary_route},
            )
            conn.execute(
                text(
                    """
                    DELETE FROM airank_provider_route_controls
                    WHERE provider_key='qianwen' AND route_id IN (:primary_route, :secondary_route)
                    """
                ),
                {"primary_route": primary_route, "secondary_route": secondary_route},
            )


def test_real_mysql_knowledge_governance_derives_expiry_and_conflict_queue() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_knowledge_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    knowledge_repo = MySQLKnowledgeRepository(database_url())
    now = datetime.now(timezone.utc)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-knowledge.example.com",
                brand_name_hint="AIRank Knowledge",
                industry_hint="B2B SaaS",
            ),
        )
        expired_source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-expired-source-it",
                source_type="qualification",
                title="已过期资质",
                content_text="该资质仅用于验证过期提醒。",
                source_uri="https://airank-knowledge.example.com/expired",
                authority_level="official",
                risk_level="low",
                valid_until=now - timedelta(days=2),
            ),
        )
        expiring_source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-expiring-source-it",
                source_type="official_website",
                title="即将到期产品说明",
                content_text="AIRank 提供可追溯的多平台 GEO 测量。",
                source_uri="https://airank-knowledge.example.com/facts",
                authority_level="official",
                risk_level="low",
                valid_until=now + timedelta(days=5),
            ),
        )
        original = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="测量能力",
                fact_text="AIRank 提供可追溯的多平台 GEO 测量。",
                source_ids=[expiring_source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
                valid_until=now + timedelta(days=3),
            ),
        )
        approved = knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            original.revision_id,
            FactRevisionReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        revised = knowledge_repo.revise_fact(
            tenant_id,
            project.project_id,
            original.fact_id,
            FactProposalRequest(
                title="测量能力",
                fact_text="AIRank 只提供单平台 GEO 测量。",
                source_ids=[expiring_source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
            ),
        )
        conflict = knowledge_repo.create_conflict(
            tenant_id,
            project.project_id,
            original.fact_id,
            FactConflictCreateRequest(
                left_revision_id=original.revision_id,
                right_revision_id=revised.revision_id,
                conflict_type="value_mismatch",
                description="平台覆盖范围冲突",
            ),
        )

        listed_sources = knowledge_repo.list_sources(tenant_id, project.project_id)
        open_conflicts = knowledge_repo.list_conflicts(tenant_id, project.project_id, "open")
        facts = knowledge_repo.list_facts(tenant_id, project.project_id)
        governance = derive_knowledge_governance(
            listed_sources,
            facts,
            open_conflicts,
            within_days=7,
            as_of=now,
        )

        approved_after_conflict = next(item for item in facts if item.revision_id == approved.revision_id)
        expiring_source_after_read = next(item for item in listed_sources if item.source_id == expiring_source.source_id)
        assert expiring_source_after_read.valid_until is not None
        assert expiring_source_after_read.valid_until.utcoffset() == timedelta(0)
        assert approved_after_conflict.valid_until is not None
        assert approved_after_conflict.valid_until.utcoffset() == timedelta(0)
        assert open_conflicts[0].detected_at.utcoffset() == timedelta(0)
        assert approved_after_conflict.eligible_for_generation is False
        assert approved_after_conflict.eligibility_reason == "open_conflict"
        assert [item.conflict_id for item in open_conflicts] == [conflict.conflict_id]
        assert governance.expired_source_count == 1
        assert governance.expiring_source_count == 1
        assert governance.expiring_fact_count == 1
        assert governance.open_conflict_count == 1
        assert governance.action_required_count == 4
        assert any(alert.entity_id == expired_source.source_id for alert in governance.alerts)

        knowledge_repo.resolve_conflict(
            tenant_id,
            project.project_id,
            conflict.conflict_id,
            FactConflictResolveRequest(
                resolution="resolved_left",
                resolved_by="integration-reviewer",
                resolution_note="官方原文支持左版本",
            ),
        )
        assert knowledge_repo.list_conflicts(tenant_id, project.project_id, "open") == []
        restored = next(
            item for item in knowledge_repo.list_facts(tenant_id, project.project_id)
            if item.revision_id == approved.revision_id
        )
        assert restored.eligible_for_generation is True
        assert restored.eligibility_reason == "approved_current_fact"
        with pytest.raises(StarletteHTTPException) as duplicate_error:
            knowledge_repo.create_conflict(
                tenant_id,
                project.project_id,
                original.fact_id,
                FactConflictCreateRequest(
                    left_revision_id=revised.revision_id,
                    right_revision_id=original.revision_id,
                    conflict_type="value_mismatch",
                    description="同一修订对不能重复登记",
                ),
            )
        assert duplicate_error.value.status_code == 409
        assert duplicate_error.value.detail["code"] == "STATE_CONFLICT"
        assert duplicate_error.value.detail["details"]["status"] == "resolved_left"

        source_revision = knowledge_repo.revise_source(
            tenant_id,
            project.project_id,
            expiring_source.source_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-source-revision-it",
                source_type="official_website",
                title="AIRank 产品说明 2026-08",
                content_text="AIRank 提供可追溯的多平台 GEO 测量和审计日志。",
                source_uri="https://airank-knowledge.example.com/facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        source_replay = knowledge_repo.revise_source(
            tenant_id,
            project.project_id,
            expiring_source.source_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-source-revision-it",
                source_type="official_website",
                title="AIRank 产品说明 2026-08",
                content_text="AIRank 提供可追溯的多平台 GEO 测量和审计日志。",
                source_uri="https://airank-knowledge.example.com/facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        sources_after_revision = knowledge_repo.list_sources(tenant_id, project.project_id)
        facts_after_source_revision = knowledge_repo.list_facts(tenant_id, project.project_id)
        search = knowledge_repo.search_segments(tenant_id, project.project_id, "审计日志", 10)
        governance_after_revision = derive_knowledge_governance(
            sources_after_revision,
            facts_after_source_revision,
            knowledge_repo.list_conflicts(tenant_id, project.project_id, "open"),
            within_days=7,
            as_of=now,
        )

        assert source_revision.parent_source_id == expiring_source.source_id
        assert source_revision.revision_number == 2
        assert source_replay.source_id == source_revision.source_id
        assert source_replay.idempotent_replay is True
        assert next(item for item in sources_after_revision if item.source_id == expiring_source.source_id).status == "stale"
        invalidated = next(
            item for item in facts_after_source_revision
            if item.revision_id == approved.revision_id
        )
        assert invalidated.eligible_for_generation is False
        assert invalidated.eligibility_reason == "source_stale"
        assert governance_after_revision.stale_source_count == 1
        assert search.retrieval_mode == "lexical_only"
        assert search.vector_status == "not_configured"
        assert search.returned_count == 1
        assert search.results[0].source_id == source_revision.source_id
        assert search.results[0].text == "AIRank 提供可追溯的多平台 GEO 测量和审计日志。"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_publish_worker_persists_delivery_receipt_without_auto_retest() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_publish_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    knowledge_repo = MySQLKnowledgeRepository(database_url())
    delivery_repo = MySQLDeliveryRepository(database_url())
    execution_repo = MySQLPublishExecutionRepository(database_url())
    job_store = MySQLJobLeaseStore(database_url())

    class FakeTransport:
        calls: list[dict[str, Any]] = []

        def request(self, method, url, *, headers, payload, timeout_seconds):
            self.calls.append({"method": method, "url": url, "headers": dict(headers), "payload": payload})
            return 201, {}, {
                "id": "remote_publish_it",
                "published_url": "https://publisher.example.test/pages/airank-proof",
            }

    class FailingTransport:
        def request(self, method, url, *, headers, payload, timeout_seconds):
            raise PublisherError("PUBLISH_NETWORK_FAILED", "simulated network failure", retryable=True)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-publish.example.com",
                brand_name_hint="AIRank Publish",
                industry_hint="B2B SaaS",
            ),
        )
        source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="publish-source-it",
                source_type="official_website",
                title="AIRank 官方事实",
                content_text="AIRank 提供带原始回答和引用证据的多平台 GEO 测量。",
                source_uri="https://airank-publish.example.com/facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        fact = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="AIRank 产品能力",
                fact_text="AIRank 提供带原始回答和引用证据的多平台 GEO 测量。",
                source_ids=[source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
            ),
        )
        knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            fact.revision_id,
            FactRevisionReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        asset = knowledge_repo.create_governed_content(
            tenant_id,
            project.project_id,
            GovernedContentCreateRequest(
                asset_type="fact_page",
                title="AIRank 企业事实页",
                direction="只陈述审核通过的事实",
                fact_revision_ids=[fact.revision_id],
                created_by="integration-test",
            ),
        )
        delivery_repo.review_content(
            tenant_id,
            asset.asset_id,
            ContentReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        listed_assets = knowledge_repo.list_governed_content(tenant_id, project.project_id)
        assert len(listed_assets) == 1
        assert listed_assets[0].asset_id == asset.asset_id
        assert listed_assets[0].status == "approved"
        assert listed_assets[0].fact_revision_ids == [fact.revision_id]
        assert len(listed_assets[0].claim_assertion_ids) == 1
        assert len(listed_assets[0].claim_support_ids) == 1
        package = delivery_repo.create_package(
            tenant_id,
            asset.asset_id,
            PublishPackageCreateRequest(
                channel="http",
                idempotency_key="publish-package-it",
                requested_by="integration-test",
                target_endpoint="https://publisher.example.test/v1/publish",
            ),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs SET priority = -1000
                    WHERE tenant_id = :tenant_id AND job_type = 'publish.package'
                    """
                ),
                {"tenant_id": tenant_id},
            )
        transport = FakeTransport()
        gateway = PublisherGateway(
            env={
                "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
                "AIRANK_PUBLISH_HTTP_BEARER_TOKEN": "integration-secret",
            },
            transport=transport,
            resolver=lambda host, port, **_: [(2, 1, 6, "", ("93.184.216.34", port))],
        )

        receipt = run_next_publish_job(
            job_store,
            execution_repo,
            gateway,
            worker_id="publisher-integration",
        )

        assert receipt is not None
        assert receipt.published_url == "https://publisher.example.test/pages/airank-proof"
        assert "integration-secret" not in repr(receipt)
        with engine.connect() as conn:
            package_row = conn.execute(
                text(
                    """
                    SELECT status, published_url, published_at, metadata_json
                    FROM airank_publish_packages
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).mappings().one()
            attempt = conn.execute(
                text(
                    """
                    SELECT status, request_sha256, response_sha256, response_status
                    FROM airank_publish_attempts
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).mappings().one()
            retest_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_retest_observation_windows
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).scalar_one()
        assert package_row["status"] == "delivered"
        assert package_row["published_at"] is None
        assert attempt["status"] == "succeeded"
        assert len(attempt["request_sha256"]) == 64
        assert len(attempt["response_sha256"]) == 64
        assert int(attempt["response_status"]) == 201
        assert retest_count == 0
        assert "integration-secret" not in str(package_row["metadata_json"])
        assert transport.calls[0]["headers"]["Idempotency-Key"] == "publish-package-it"

        retry_package = delivery_repo.create_package(
            tenant_id,
            asset.asset_id,
            PublishPackageCreateRequest(
                channel="http",
                idempotency_key="publish-retry-package-it",
                requested_by="integration-test",
                target_endpoint="https://publisher.example.test/v1/publish",
            ),
        )
        with engine.begin() as conn:
            retry_job_id = conn.execute(
                text(
                    """
                    SELECT id FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id AND job_type = 'publish.package'
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.package_id')) = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": retry_package.package_id},
            ).scalar_one()
            conn.execute(
                text("UPDATE airank_async_jobs SET priority = -1000 WHERE id = :id"),
                {"id": retry_job_id},
            )
        failing_gateway = PublisherGateway(
            env={
                "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
                "AIRANK_PUBLISH_HTTP_BEARER_TOKEN": "integration-secret",
            },
            transport=FailingTransport(),
            resolver=lambda host, port, **_: [(2, 1, 6, "", ("93.184.216.34", port))],
        )
        with pytest.raises(PublisherError) as failed_publish:
            run_next_publish_job(
                job_store,
                execution_repo,
                failing_gateway,
                worker_id="publisher-integration",
            )
        assert failed_publish.value.code == "PUBLISH_NETWORK_FAILED"
        assert job_store.get(retry_job_id).status.value == "failed"

        job_store.requeue_for_retry(retry_job_id, datetime.now(timezone.utc))
        recovered = run_next_publish_job(
            job_store,
            execution_repo,
            gateway,
            worker_id="publisher-integration-retry",
        )
        assert recovered is not None
        with engine.connect() as conn:
            retry_package_status = conn.execute(
                text(
                    """
                    SELECT status FROM airank_publish_packages
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": retry_package.package_id},
            ).scalar_one()
            attempt_statuses = conn.execute(
                text(
                    """
                    SELECT status FROM airank_publish_attempts
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                    ORDER BY attempt_number
                    """
                ),
                {"tenant_id": tenant_id, "package_id": retry_package.package_id},
            ).scalars().all()
        assert retry_package_status == "delivered"
        assert attempt_statuses == ["failed", "succeeded"]

        stale_package = delivery_repo.create_package(
            tenant_id,
            asset.asset_id,
            PublishPackageCreateRequest(
                channel="http",
                idempotency_key="publish-stale-package-it",
                requested_by="integration-test",
                target_endpoint="https://publisher.example.test/v1/publish",
            ),
        )
        stale_snapshot = execution_repo.load_snapshot(tenant_id, stale_package.package_id)
        execution_repo.begin_attempt(
            stale_snapshot,
            gateway.request_sha256(stale_snapshot),
            datetime.now(timezone.utc) - timedelta(seconds=700),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs SET priority = -1000
                    WHERE tenant_id = :tenant_id AND job_type = 'publish.package'
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.package_id')) = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": stale_package.package_id},
            )
        recovered_stale = run_next_publish_job(
            job_store,
            execution_repo,
            gateway,
            worker_id="publisher-stale-recovery",
        )
        assert recovered_stale is not None
        with engine.connect() as conn:
            stale_attempts = conn.execute(
                text(
                    """
                    SELECT status, error_code FROM airank_publish_attempts
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                    ORDER BY attempt_number
                    """
                ),
                {"tenant_id": tenant_id, "package_id": stale_package.package_id},
            ).mappings().all()
        assert [row["status"] for row in stale_attempts] == ["failed", "succeeded"]
        assert stale_attempts[0]["error_code"] == "PUBLISH_ATTEMPT_ABANDONED"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_yudao_login_permission_and_capability_probe() -> None:
    require_real_flag("AIRANK_RUN_REAL_YUDAO")
    base_url = os.getenv("YUDAO_BASE_URL", "http://127.0.0.1:48080").rstrip("/")
    tenant_id = os.getenv("YUDAO_TENANT_ID", "1")
    username = os.getenv("YUDAO_USERNAME")
    password = os.getenv("YUDAO_PASSWORD")
    assert username, "YUDAO_USERNAME is required when AIRANK_RUN_REAL_YUDAO=1"
    assert password, "YUDAO_PASSWORD is required when AIRANK_RUN_REAL_YUDAO=1"

    login_payload = request_json(
        f"{base_url}/admin-api/system/auth/login",
        method="POST",
        headers={"Content-Type": "application/json", "tenant-id": tenant_id},
        body={"username": username, "password": password},
    )
    assert login_payload["code"] == 0
    token = extract_yudao_token(login_payload)
    assert token

    permission_payload = request_json(
        f"{base_url}/admin-api/system/auth/get-permission-info",
        headers={"Authorization": f"Bearer {token}", "tenant-id": tenant_id},
    )
    assert permission_payload["code"] == 0
    assert isinstance(permission_payload.get("data"), dict)
    assert permission_payload["data"].get("user")

    config = replace(
        ProbeConfig.from_env(
            {
                "AIRANK_AUTH_MODE": "yudao",
                "YUDAO_BASE_URL": base_url,
                "YUDAO_BEARER_TOKEN": token,
                "YUDAO_TENANT_ID": tenant_id,
                "AIRANK_OBJECT_STORAGE_DRIVER": "local",
                "AIRANK_OBJECT_STORAGE_ROOT": ".runtime/objects",
            }
        ),
        timeout_seconds=5,
    )
    results = {result.capability: result for result in CapabilityProbe(config).run()}

    assert results["yudao_auth"].status == CapabilityStatus.READY
    assert results["yudao_tenant_user"].status == CapabilityStatus.READY
    assert results["yudao_auth"].metadata["http_status"] == "200"


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(url, data=payload, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


def extract_yudao_token(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("accessToken") or data.get("access_token") or data.get("token")
    return token if isinstance(token, str) else None


def utc_datetime() -> datetime:
    return datetime.now(timezone.utc)

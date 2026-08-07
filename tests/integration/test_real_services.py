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
    BuyerQuestionCreateRequest,
    CompetitorCreateRequest,
    MySQLAssetBundleRepository,
    MySQLProjectRepository,
    MySQLReportRepository,
    MySQLScanRepository,
    ProjectCreateRequest,
    ScanRunCreateRequest,
)
from apps.api.delivery_routes import (
    ContentReviewRequest,
    MySQLDeliveryRepository,
    PublishPackageCreateRequest,
)
from apps.api.knowledge_routes import (
    FactProposalRequest,
    FactRevisionReviewRequest,
    GovernedContentCreateRequest,
    KnowledgeSourceCreateRequest,
    MySQLKnowledgeRepository,
)
from apps.api.provider_operations import MySQLProviderOperations
from apps.api.evidence_routes import MySQLEvidenceRepository
from airank_evidence import FilesystemObjectStorage
from airank_provider_gateway import (
    HealthState,
    ProbeLevel,
    ProbeResult,
    ProviderGatewayError,
    ProviderRequestContext,
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
    run_next_publish_job,
)
from airank_xinghe_adapter import CapabilityProbe, CapabilityStatus, ProbeConfig  # noqa: E402


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"
EXPECTED_ALEMBIC_HEAD = "20260808_0008"


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
        assert table_count == 42

        url_columns = (
            ("airank_projects", "website_url"),
            ("airank_competitors", "website_url"),
            ("airank_source_citations", "url"),
            ("airank_fact_sources", "source_url"),
            ("airank_content_assets", "target_url"),
            ("airank_publish_packages", "published_url"),
            ("airank_object_refs", "object_uri"),
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
                question_text="How does AIRank compare with direct competitors?",
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
                      'AIRank 真实诊断报告', 'ready',
                      JSON_OBJECT('summary', '真实 MySQL 报告列表验证'),
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
    }
    first_worker = MySQLProviderOperations(database_url(), env=env)
    second_worker = MySQLProviderOperations(database_url(), env=env)
    context = ProviderRequestContext(
        tenant_id=tenant_id,
        project_id="project_provider_it",
        idempotency_key="scan_task_provider_it",
    )

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

        race_tenant_id = f"{tenant_id}_race"

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
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM airank_provider_probe_runs WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
            conn.execute(
                text("DELETE FROM airank_provider_circuit_states WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
        cleanup_tenant(engine, tenant_id)
        cleanup_tenant(engine, race_tenant_id)


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

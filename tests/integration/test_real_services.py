from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "xinghe-adapter" / "src"))

from airank_domain import AsyncJob, AsyncJobStatus  # noqa: E402
from airank_worker import MySQLJobLeaseStore  # noqa: E402
from airank_xinghe_adapter import CapabilityProbe, CapabilityStatus, ProbeConfig  # noqa: E402


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"
EXPECTED_ALEMBIC_HEAD = "20260517_0002"


def require_real_flag(flag: str) -> None:
    if os.getenv(flag) != "1":
        pytest.skip(f"set {flag}=1 to run real integration checks")


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine: Any, tenant_id: str) -> None:
    tables = (
        "airank_audit_events",
        "airank_async_jobs",
        "airank_reports",
        "airank_scan_tasks",
        "airank_scan_runs",
        "airank_publish_packages",
        "airank_content_assets",
        "airank_content_gaps",
        "airank_buyer_questions",
        "airank_competitors",
        "airank_projects",
    )
    with engine.begin() as conn:
        for table_name in tables:
            conn.execute(text(f"DELETE FROM {table_name} WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})


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
        assert table_count == 22

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


def test_real_mysql_scan_queue_and_asset_bundle_paths() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    asset_repo = MySQLAssetBundleRepository(database_url())

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
        assert run.metrics["task_count"] == 4
        assert len(tasks) == 4
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
            assert len(jobs) == 4
            first_payload = json.loads(jobs[0])
            assert first_payload["run_id"] == run.run_id
            assert first_payload["scan_task_id"].startswith("scan_task_")
            assert first_payload["question_id"] in {question_one.question_id, question_two.question_id}

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
        assert bundle.assets[0].asset_id == "asset_real_fact_page"
        assert bundle.assets[0].progress == 100
        assert "1 个内容缺口" in bundle.recommendation
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

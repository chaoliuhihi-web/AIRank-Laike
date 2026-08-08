from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "apps" / "worker",
    ROOT / "packages" / "crawler-lite" / "src",
    ROOT / "packages" / "domain" / "src",
    ROOT / "packages" / "outbound-security" / "src",
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from apps.api.main import MySQLProjectRepository, ProjectCreateRequest  # noqa: E402
from apps.api.page_audit_routes import (  # noqa: E402
    MySQLPageAuditRepository,
    PageAuditCreateRequest,
)
from airank_crawler_lite import PageAuditFinding, PageAuditResult  # noqa: E402
from airank_worker import MySQLJobLeaseStore  # noqa: E402
from airank_worker.page_audit import (  # noqa: E402
    MySQLPageAuditExecutionRepository,
    run_next_page_audit_job,
)


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND column_name='tenant_id'
                  AND table_name LIKE 'airank\\_%'
                ORDER BY table_name DESC
                """
            )
        ).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        try:
            for table_name in tables:
                conn.execute(text(f"DELETE FROM `{table_name}` WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


class FakeAuditService:
    def audit(self, url: str) -> PageAuditResult:
        return PageAuditResult(
            requested_url=url,
            final_url=url,
            response_status=200,
            content_type="text/html",
            response_bytes=512,
            content_sha256="c" * 64,
            connected_ip="93.184.216.34",
            redirect_count=0,
            technical_extractability_score=91,
            title="AIRank real MySQL audit",
            meta_description="真实 MySQL 页面诊断链路验收。",
            canonical_url=url,
            robots_directives=(),
            h1_count=1,
            visible_text_chars=800,
            json_ld_types=("Organization",),
            findings=(
                PageAuditFinding(
                    rule_id="http.status",
                    severity="info",
                    status="passed",
                    title="HTTP status",
                    description="HTTP 200",
                    recommendation="",
                    evidence={"response_status": 200},
                ),
                PageAuditFinding(
                    rule_id="meta.description",
                    severity="medium",
                    status="failed",
                    title="Meta description",
                    description="too short",
                    recommendation="add evidence summary",
                    evidence={"character_count": 15},
                    score_delta=-6,
                ),
            ),
        )


def test_real_mysql_page_audit_job_persists_run_and_findings() -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real integration checks")
    tenant_id = f"tenant_page_audit_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repository = MySQLProjectRepository(database_url())
    api_repository = MySQLPageAuditRepository(database_url())
    job_store = MySQLJobLeaseStore(database_url())
    execution_repository = MySQLPageAuditExecutionRepository(database_url())

    try:
        project = project_repository.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://example.com/airank",
                brand_name_hint="AIRank Page Audit",
                industry_hint="enterprise software",
            ),
        )
        created = api_repository.create(
            tenant_id,
            project.project_id,
            PageAuditCreateRequest(
                idempotency_key="page-audit-real-mysql-1",
                requested_by="integration-test",
            ),
        )
        assert created.status == "queued"

        result = run_next_page_audit_job(
            job_store,
            execution_repository,
            FakeAuditService(),  # type: ignore[arg-type]
            worker_id="page-audit-integration-worker",
            now=datetime.now(timezone.utc),
        )
        assert result is not None
        assert result.technical_extractability_score == 91

        detail = api_repository.get(tenant_id, project.project_id, created.run_id)
        assert detail.status == "completed"
        assert detail.technical_extractability_score == 91
        assert detail.content_sha256 == "c" * 64
        assert detail.finding_count == 2
        assert detail.failed_finding_count == 1
        assert [finding.rule_id for finding in detail.findings] == ["meta.description", "http.status"]
        assert detail.findings[0].evidence == {"character_count": 15}

        replay = api_repository.create(
            tenant_id,
            project.project_id,
            PageAuditCreateRequest(
                idempotency_key="page-audit-real-mysql-1",
                requested_by="integration-test",
            ),
        )
        assert replay.run_id == created.run_id
        assert replay.idempotent_replay is True
    finally:
        cleanup_tenant(engine, tenant_id)

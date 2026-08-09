from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from apps.api.brand_graph_routes import (
    BrandAliasWriteRequest,
    BrandEntityWriteRequest,
    MySQLBrandGraphRepository,
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


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(text("""
            SELECT table_name FROM information_schema.columns
            WHERE table_schema=DATABASE() AND column_name='tenant_id'
              AND table_name LIKE 'airank\\_%'
            ORDER BY table_name DESC
        """)).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        try:
            for table_name in tables:
                conn.execute(text(f"DELETE FROM `{table_name}` WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def test_real_mysql_graph_freezes_measurement_lexicon_into_scan_run() -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real integration checks")
    tenant_id = f"tenant_brand_graph_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    projects = MySQLProjectRepository(database_url())
    knowledge = MySQLKnowledgeRepository(database_url())
    graphs = MySQLBrandGraphRepository(database_url())
    scans = MySQLScanRepository(database_url())

    try:
        project = projects.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank.example/graph",
                brand_name_hint="AIRank",
                company_name_hint="星河科技",
                industry_hint="GEO",
            ),
        )
        source = knowledge.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key=f"brand-graph-source-{uuid4().hex}",
                source_type="official_company_profile",
                title="AIRank 官方身份说明",
                content_text="AIRank 是星河科技提供的 GEO 测量产品，也称来客。",
                source_uri="https://airank.example/graph/identity",
                authority_level="official",
                risk_level="low",
            ),
        )
        proposed = knowledge.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="AIRank 品牌身份",
                fact_type="brand_identity",
                subject_type="brand",
                subject_ref_id="AIRank",
                fact_text="AIRank 是星河科技提供的 GEO 测量产品，也称来客。",
                source_ids=[source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration_operator",
            ),
        )
        approved = knowledge.review_revision(
            tenant_id,
            project.project_id,
            proposed.revision_id,
            FactRevisionReviewRequest(
                action="approved",
                reviewed_by="integration_reviewer",
                review_note="官方身份原文已核验。",
            ),
        )
        target = graphs.create_entity(
            tenant_id,
            project.project_id,
            BrandEntityWriteRequest(
                entity_role="target",
                entity_kind="brand",
                canonical_name="AIRank",
                website_url="https://airank.example/graph",
                usage_scope="public_and_measurement",
                fact_revision_id=approved.revision_id,
            ),
            "integration_reviewer",
            "trc_brand_graph_entity",
        )
        graphs.create_alias(
            tenant_id,
            project.project_id,
            target.entity_id,
            BrandAliasWriteRequest(
                alias_text="来客",
                alias_type="official",
                usage_scope="public_and_measurement",
                fact_revision_id=approved.revision_id,
            ),
            "integration_reviewer",
            "trc_brand_graph_alias",
        )
        graph_v1 = graphs.compile_snapshot(tenant_id, project.project_id, "integration_reviewer")
        assert graph_v1.status == "governed"
        assert graph_v1.measurement_lexicon["target"]["brand_aliases"] == ["来客"]
        assert graph_v1.public_jsonld["@graph"][0]["alternateName"] == ["来客"]

        question = projects.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业如何选择 GEO 测量平台？",
                status="confirmed",
                source="manual",
                recommended_providers=["qianwen"],
            ),
        )
        run = scans.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                cohort_type="blind",
                repetitions=1,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        assert run.entity_graph_snapshot_id == graph_v1.snapshot_id
        assert run.entity_graph_sha256 == graph_v1.graph_sha256
        assert run.entity_graph_status == "governed"
        task = scans.list_tasks(tenant_id, run.run_id)[0]
        with engine.begin() as conn:
            request_payload = json.loads(conn.execute(text("SELECT request_json FROM airank_scan_tasks WHERE id=:task_id"), {"task_id": task.task_id}).scalar_one())
        assert request_payload["entity_graph_snapshot_id"] == graph_v1.snapshot_id
        assert request_payload["entity_graph_sha256"] == graph_v1.graph_sha256

        updated = graphs.update_entity(
            tenant_id,
            project.project_id,
            target.entity_id,
            BrandEntityWriteRequest(
                entity_role="target",
                entity_kind="brand",
                canonical_name="AIRank 来客",
                website_url="https://airank.example/graph",
                usage_scope="public_and_measurement",
                fact_revision_id=approved.revision_id,
                expected_version=1,
            ),
            "integration_reviewer",
            "trc_brand_graph_entity_v2",
        )
        assert updated.version == 2
        graph_v2 = graphs.compile_snapshot(tenant_id, project.project_id, "integration_reviewer")
        assert graph_v2.graph_sha256 != graph_v1.graph_sha256
        frozen_run = scans.get_run(tenant_id, run.run_id)
        assert frozen_run.entity_graph_snapshot_id == graph_v1.snapshot_id
        assert frozen_run.entity_graph_sha256 == graph_v1.graph_sha256
    finally:
        cleanup_tenant(engine, tenant_id)
        engine.dispose()

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import text

from apps.api.main import (
    InMemoryAssetBundleRepository,
    MySQLAssetBundleRepository,
    app,
    build_asset_bundle_repository,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages" / "contracts" / "asset_bundle_response.schema.json"


def test_asset_bundle_api_matches_contract() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/projects/project_demo/asset-bundle",
        headers={"tenant-id": "tenant_assets", "X-AIRank-Trace-Id": "trc_asset_bundle"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_asset_bundle"
    assert body["data"]["tenant_id"] == "tenant_assets"
    assert body["data"]["assets"] == []
    assert body["data"]["completeness"] == 0

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(body)


def test_asset_bundle_api_rejects_invalid_project_id() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/projects/not_a_project_id/asset-bundle",
        headers={"tenant-id": "tenant_assets", "X-AIRank-Trace-Id": "trc_asset_bad_project"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["trace_id"] == "trc_asset_bad_project"


def create_asset_bundle_tables(repository: MySQLAssetBundleRepository) -> None:
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE airank_projects (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  deleted_at DATETIME NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_content_assets (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL,
                  asset_type VARCHAR(64) NOT NULL,
                  title VARCHAR(255) NOT NULL,
                  body_md TEXT NULL,
                  status VARCHAR(32) NOT NULL,
                  metadata_json TEXT NULL,
                  updated_at DATETIME NOT NULL,
                  deleted_at DATETIME NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_content_gaps (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL,
                  run_id VARCHAR(64) NULL,
                  gap_type VARCHAR(64) NOT NULL DEFAULT 'evidence_gap',
                  contract_version VARCHAR(64) NULL,
                  derivation_policy VARCHAR(96) NULL,
                  title VARCHAR(255) NOT NULL,
                  severity VARCHAR(32) NOT NULL,
                  evidence_summary_json TEXT NULL,
                  answer_snapshot_ids TEXT NULL,
                  evidence_snapshot_ids TEXT NULL,
                  citation_ids TEXT NULL,
                  fact_atom_ids TEXT NULL,
                  evidence_sha256 VARCHAR(64) NULL,
                  quality_report_sha256 VARCHAR(64) NULL,
                  suggested_asset_type VARCHAR(64) NULL,
                  status VARCHAR(32) NOT NULL,
                  updated_at DATETIME NOT NULL,
                  deleted_at DATETIME NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE airank_publish_packages (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(64) NOT NULL,
                  project_id VARCHAR(64) NOT NULL,
                  asset_id VARCHAR(64) NULL,
                  status VARCHAR(32) NOT NULL,
                  updated_at DATETIME NOT NULL,
                  deleted_at DATETIME NULL
                )
                """
            )
        )
        conn.execute(text("INSERT INTO airank_projects (id, tenant_id) VALUES ('project_asset', 'tenant_asset')"))


def test_asset_bundle_repository_factory_selects_persistence_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRANK_DATABASE_URL", raising=False)
    assert isinstance(build_asset_bundle_repository(), InMemoryAssetBundleRepository)

    monkeypatch.setenv(
        "AIRANK_DATABASE_URL",
        "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike",
    )
    assert isinstance(build_asset_bundle_repository(), MySQLAssetBundleRepository)


def test_mysql_asset_bundle_uses_content_assets_and_publish_state() -> None:
    repository = MySQLAssetBundleRepository("sqlite+pysqlite:///:memory:")
    create_asset_bundle_tables(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_content_assets (
                  id, tenant_id, project_id, asset_type, title, body_md, status, updated_at
                )
                VALUES
                  (
                    'asset_fact_page', 'tenant_asset', 'project_asset',
                    'fact_page', '企业事实页', '已确认事实卡页面', 'approved', '2026-05-17 10:00:00'
                  ),
                  (
                    'asset_faq', 'tenant_asset', 'project_asset',
                    'faq', 'FAQ 页', '高频买家问题和官方回答', 'draft', '2026-05-17 09:00:00'
                  )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_publish_packages (
                  id, tenant_id, project_id, asset_id, status, updated_at
                )
                VALUES (
                  'pkg_fact_page', 'tenant_asset', 'project_asset',
                  'asset_fact_page', 'published', '2026-05-17 10:30:00'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_content_gaps (
                  id, tenant_id, project_id, title, severity, suggested_asset_type, status, updated_at
                )
                VALUES (
                  'gap_case', 'tenant_asset', 'project_asset',
                  '缺少客户案例页', 'high', 'case_page', 'open', '2026-05-17 11:00:00'
                )
                """
            )
        )

    bundle = repository.get_bundle("tenant_asset", "project_asset")

    assert bundle.project_id == "project_asset"
    assert bundle.tenant_id == "tenant_asset"
    assert {asset.asset_id for asset in bundle.assets} == {"asset_fact_page", "asset_faq"}
    assert {asset.asset_id: asset.progress for asset in bundle.assets}["asset_fact_page"] == 100
    assert "1 个未绑定样本证据的历史缺口" in bundle.recommendation


def test_mysql_asset_bundle_uses_display_metadata_when_present() -> None:
    repository = MySQLAssetBundleRepository("sqlite+pysqlite:///:memory:")
    create_asset_bundle_tables(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_content_assets (
                  id, tenant_id, project_id, asset_type, title, body_md,
                  status, metadata_json, updated_at
                )
                VALUES (
                  'asset_display', 'tenant_asset', 'project_asset',
                  'fact_page', '企业事实页', '已确认事实卡页面', 'approved',
                  '{"display_status": "可发布", "progress": 86}',
                  '2026-05-17 10:00:00'
                )
                """
            )
        )

    bundle = repository.get_bundle("tenant_asset", "project_asset")

    assert bundle.assets[0].asset_id == "asset_display"
    assert bundle.assets[0].status == "可发布"
    assert bundle.assets[0].progress == 86


def test_mysql_asset_bundle_uses_gap_empty_state_without_seed_assets() -> None:
    repository = MySQLAssetBundleRepository("sqlite+pysqlite:///:memory:")
    create_asset_bundle_tables(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_content_gaps (
                  id, tenant_id, project_id, run_id, gap_type,
                  contract_version, derivation_policy, title, severity,
                  evidence_summary_json, answer_snapshot_ids,
                  evidence_snapshot_ids, citation_ids, fact_atom_ids,
                  evidence_sha256, quality_report_sha256,
                  suggested_asset_type, status, updated_at
                )
                VALUES (
                  'gap_compare', 'tenant_asset', 'project_asset', 'scan_run_gap',
                  'brand_unmentioned', 'airank.evidence-gap.v2',
                  'airank.brand-unmentioned-gap.v1', '缺少竞品对比页', 'medium',
                  :evidence_summary,
                  '["snapshot_1","snapshot_2","snapshot_3"]',
                  '["evidence_1","evidence_2","evidence_3"]', '[]', '[]',
                  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                  'comparison_page', 'open', '2026-05-17 11:00:00'
                )
                """
            ),
            {
                "evidence_summary": json.dumps(
                    {
                        "provider": "qianwen",
                        "collector_surface": "api",
                        "valid_sample_count": 3,
                    }
                )
            },
        )

    bundle = repository.get_bundle("tenant_asset", "project_asset")

    assert [asset.asset_id for asset in bundle.assets] == ["gap_gap_compare"]
    assert bundle.assets[0].progress == 0
    assert bundle.assets[0].status == "待补事实"
    assert "3 条不可变有效样本" in bundle.assets[0].desc


def test_mysql_asset_bundle_excludes_unverified_legacy_gap_from_actions() -> None:
    repository = MySQLAssetBundleRepository("sqlite+pysqlite:///:memory:")
    create_asset_bundle_tables(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_content_gaps (
                  id, tenant_id, project_id, title, severity,
                  suggested_asset_type, status, updated_at
                ) VALUES (
                  'gap_legacy', 'tenant_asset', 'project_asset', '旧缺口',
                  'high', 'fact_page', 'open', '2026-05-17 11:00:00'
                )
                """
            )
        )

    bundle = repository.get_bundle("tenant_asset", "project_asset")

    assert bundle.assets == []
    assert "未绑定样本证据" in bundle.recommendation
    assert "重新推导" in bundle.recommendation


def test_mysql_asset_bundle_is_tenant_scoped() -> None:
    repository = MySQLAssetBundleRepository("sqlite+pysqlite:///:memory:")
    create_asset_bundle_tables(repository)

    with pytest.raises(Exception) as exc_info:
        repository.get_bundle("tenant_other", "project_asset")

    assert getattr(exc_info.value, "status_code") == 404
    assert exc_info.value.detail["code"] == "PROJECT_NOT_FOUND"

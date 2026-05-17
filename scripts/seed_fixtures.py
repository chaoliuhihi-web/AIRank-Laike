#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text


DEFAULT_DATABASE_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"
TENANT_ID = os.getenv("AIRANK_SEED_TENANT_ID", "tenant_demo")
PROJECT_ID = os.getenv("AIRANK_SEED_PROJECT_ID", "project_demo")


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_DATABASE_URL)


def seed() -> None:
    engine = create_engine(database_url(), pool_pre_ping=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_projects (
                  id, tenant_id, name, brand_name, website_url, industry,
                  products_services_json, selling_points_json, target_audience_json,
                  status, created_by, updated_by, created_at, updated_at
                )
                VALUES (
                  :project_id, :tenant_id, :name, :brand_name, :website_url, :industry,
                  :products_services_json, :selling_points_json, :target_audience_json,
                  'active', 'seed_fixture', 'seed_fixture', :now, :now
                )
                ON DUPLICATE KEY UPDATE
                  name = VALUES(name),
                  brand_name = VALUES(brand_name),
                  website_url = VALUES(website_url),
                  industry = VALUES(industry),
                  products_services_json = VALUES(products_services_json),
                  selling_points_json = VALUES(selling_points_json),
                  target_audience_json = VALUES(target_audience_json),
                  status = 'active',
                  updated_by = 'seed_fixture',
                  updated_at = VALUES(updated_at),
                  deleted_at = NULL
                """
            ),
            {
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "name": "示例科技有限公司",
                "brand_name": "智界问道",
                "website_url": "https://www.example.com",
                "industry": "营销科技",
                "products_services_json": json_text(["AI 可见性诊断", "AI 收录包", "推荐缺口复测"]),
                "selling_points_json": json_text(["证据链优先", "可复测评分", "企业品牌方闭环"]),
                "target_audience_json": json_text(["企业市场负责人", "增长负责人", "品牌负责人"]),
                "now": now,
            },
        )

        asset_rows = [
            (
                "asset_demo_fact_page",
                "fact_page",
                "企业事实页",
                "把已确认事实卡发布为 AI 易读页面，支撑模型引用品牌官方证据。",
                "approved",
            ),
            (
                "asset_demo_faq",
                "faq",
                "FAQ 页",
                "覆盖高频买家问题和官方回答，减少 AI 引用竞品解释。",
                "generated",
            ),
            (
                "asset_demo_case_page",
                "case_page",
                "客户案例页",
                "承接案例、成效、行业场景与客户评价，补齐可信商业证据。",
                "reviewing",
            ),
        ]
        for asset_id, asset_type, title, body_md, status in asset_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_assets (
                      id, tenant_id, project_id, asset_type, title, body_md,
                      status, metadata_json, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :asset_type, :title, :body_md,
                      :status, :metadata_json, :now, :now
                    )
                    ON DUPLICATE KEY UPDATE
                      asset_type = VALUES(asset_type),
                      title = VALUES(title),
                      body_md = VALUES(body_md),
                      status = VALUES(status),
                      metadata_json = VALUES(metadata_json),
                      updated_at = VALUES(updated_at),
                      deleted_at = NULL
                    """
                ),
                {
                    "id": asset_id,
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "asset_type": asset_type,
                    "title": title,
                    "body_md": body_md,
                    "status": status,
                    "metadata_json": json_text({"seed": "local_beta"}),
                    "now": now,
                },
            )

        conn.execute(
            text(
                """
                INSERT INTO airank_publish_packages (
                  id, tenant_id, project_id, asset_id, package_type, channel,
                  status, published_url, published_at, metadata_json, created_at, updated_at
                )
                VALUES (
                  'pkg_demo_fact_page', :tenant_id, :project_id, 'asset_demo_fact_page',
                  'content_asset', 'website', 'published',
                  'https://www.example.com/ai-facts', :now, :metadata_json, :now, :now
                )
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  published_url = VALUES(published_url),
                  published_at = VALUES(published_at),
                  metadata_json = VALUES(metadata_json),
                  updated_at = VALUES(updated_at),
                  deleted_at = NULL
                """
            ),
            {
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "metadata_json": json_text({"seed": "local_beta"}),
                "now": now,
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO airank_content_gaps (
                  id, tenant_id, project_id, gap_type, severity, title,
                  description, suggested_asset_type, status, created_at, updated_at
                )
                VALUES (
                  'gap_demo_compare', :tenant_id, :project_id, 'evidence_gap', 'high',
                  '缺少竞品对比页', '高意向问题中缺少结构化竞品对比证据。',
                  'comparison_page', 'open', :now, :now
                )
                ON DUPLICATE KEY UPDATE
                  severity = VALUES(severity),
                  title = VALUES(title),
                  description = VALUES(description),
                  suggested_asset_type = VALUES(suggested_asset_type),
                  status = VALUES(status),
                  updated_at = VALUES(updated_at),
                  deleted_at = NULL
                """
            ),
            {"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "now": now},
        )

        report_rows = [
            (
                "report_demo_diagnostic",
                "diagnostic",
                "AI 来客诊断报告",
                "ready",
                {"summary": "覆盖平台表现、竞品压制、引用来源和优化建议"},
            ),
            (
                "report_demo_retest",
                "retest",
                "推荐缺口复测报告",
                "ready",
                {"summary": "对比发布前后推荐率、首推率和引用变化"},
            ),
        ]
        for report_id, report_type, title, status, metrics in report_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title, status,
                      metrics_json, generated_by, generated_at, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :report_type, :title, :status,
                      :metrics_json, 'seed_fixture', :now, :now, :now
                    )
                    ON DUPLICATE KEY UPDATE
                      report_type = VALUES(report_type),
                      title = VALUES(title),
                      status = VALUES(status),
                      metrics_json = VALUES(metrics_json),
                      generated_by = VALUES(generated_by),
                      generated_at = VALUES(generated_at),
                      updated_at = VALUES(updated_at),
                      deleted_at = NULL
                    """
                ),
                {
                    "id": report_id,
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "report_type": report_type,
                    "title": title,
                    "status": status,
                    "metrics_json": json_text(metrics),
                    "now": now,
                },
            )

    print(f"Seeded AIRank fixtures: tenant={TENANT_ID} project={PROJECT_ID}")


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:
        print(f"seed-fixtures failed: {exc}", file=sys.stderr)
        raise

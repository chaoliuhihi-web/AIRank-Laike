#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

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
            ("asset_demo_fact_page", "fact_page", "企业事实页", "介绍企业基本信息、主营业务、核心优势与发展历程。", "generated", "已生成", 92),
            ("asset_demo_service_page", "service_page", "服务介绍页", "详细说明产品/服务能力、功能模块与服务流程。", "generated", "已生成", 90),
            ("asset_demo_case_page", "case_page", "客户案例页", "真实客户案例展示，突出应用场景与客户价值。", "generated", "已生成", 88),
            ("asset_demo_faq", "faq", "FAQ页", "整理常见问题与专业解答，提升 AI 问答引用概率。", "reviewing", "待确认", 62),
            ("asset_demo_compare", "comparison_page", "竞品对比页", "对比竞品优势，突出差异化价值与核心竞争力。", "generated", "已生成", 91),
            ("asset_demo_solution", "solution_page", "行业解决方案页", "针对行业痛点，提供场景化解决方案与实施路径。", "generated", "已生成", 88),
            ("asset_demo_jsonld", "jsonld", "JSON-LD 结构化数据", "构建结构化数据，帮助 AI 更好理解与提取关键信息。", "generated", "已生成", 92),
            ("asset_demo_sitemap", "sitemap", "sitemap.xml", "生成网站地图，提升页面发现效率与抓取覆盖。", "generated", "已生成", 85),
        ]
        for index, (asset_id, asset_type, title, body_md, status, display_status, progress) in enumerate(asset_rows):
            asset_time = now - timedelta(seconds=index)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_assets (
                      id, tenant_id, project_id, asset_type, title, body_md,
                      status, metadata_json, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :asset_type, :title, :body_md,
                      :status, :metadata_json, :now, :asset_time
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
                    "metadata_json": json_text({"seed": "local_beta", "display_status": display_status, "progress": progress}),
                    "now": now,
                    "asset_time": asset_time,
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

        conn.execute(
            text(
                """
                DELETE FROM airank_reports
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND id LIKE 'report_demo_%'
                """
            ),
            {"tenant_id": TENANT_ID, "project_id": PROJECT_ID},
        )

        report_rows = [
            (
                "report_demo_weekly",
                "weekly",
                "周报",
                "下载报告",
                {"summary": "2024-05-13 ~ 2024-05-19", "subtitle": "查看本周 AI 表现与来客线索变化"},
                now,
            ),
            (
                "report_demo_monthly",
                "monthly",
                "月报",
                "下载报告",
                {"summary": "2024 年 5 月", "subtitle": "查看本月整体表现与趋势分析"},
                now - timedelta(days=2),
            ),
            (
                "report_demo_exec",
                "executive",
                "老板报告",
                "导出 PPT",
                {"summary": "2024 年 5 月", "subtitle": "一句话结论 + 关键数据摘要"},
                now - timedelta(days=16),
            ),
            (
                "report_demo_competitor",
                "competitor_pressure",
                "竞品压制报告",
                "下载报告",
                {"summary": "2024 年 5 月", "subtitle": "对比竞品表现与压制机会点"},
                now - timedelta(days=20),
            ),
        ]
        for report_id, report_type, title, status, metrics, generated_at in report_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title, status,
                      metrics_json, generated_by, generated_at, created_at, updated_at
                    )
                    VALUES (
                      :id, :tenant_id, :project_id, :report_type, :title, :status,
                      :metrics_json, 'seed_fixture', :generated_at, :now, :now
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
                    "generated_at": generated_at,
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

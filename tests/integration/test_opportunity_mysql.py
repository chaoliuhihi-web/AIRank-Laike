from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from apps.api.opportunity_routes import MySQLOpportunityRepository, OpportunityDeriveRequest


DATABASE_URL = os.getenv("AIRANK_DATABASE_URL", "").strip()
RUN_REAL_MYSQL = os.getenv("AIRANK_RUN_REAL_MYSQL", "").strip() == "1"
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not RUN_REAL_MYSQL,
    reason="real MySQL opportunity integration requires AIRANK_RUN_REAL_MYSQL=1",
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_real_mysql_cross_domain_opportunity_snapshots_are_append_only() -> None:
    suffix = uuid4().hex[:12]
    tenant_id = f"tenant_opp_{suffix}"
    project_id = f"project_opp_{suffix}"
    question_id = f"question_opp_{suffix}"
    scan_run_id = f"scan_run_opp_{suffix}"
    answer_id = f"snapshot_opp_{suffix}"
    evidence_id = f"evidence_opp_{suffix}"
    citation_id = f"citation_opp_{suffix}"
    gap_id = f"gap_ev_{sha(suffix)[:20]}"
    source_id = f"source_opp_{suffix}"
    job_one = f"job_opp_1_{suffix}"
    page_run_one = f"page_audit_1_{suffix}"
    finding_id = f"finding_opp_{suffix}"
    job_two = f"job_opp_2_{suffix}"
    page_run_two = f"page_audit_2_{suffix}"
    finding_two_id = f"finding_opp_2_{suffix}"
    job_three = f"job_opp_3_{suffix}"
    page_run_three = f"page_audit_3_{suffix}"
    evaluated_at = datetime(2026, 8, 9, 6, 0, tzinfo=timezone.utc)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    repository = MySQLOpportunityRepository(DATABASE_URL)

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO airank_projects "
                    "(id, tenant_id, name, brand_name, status, created_by) "
                    "VALUES (:id, :tenant_id, 'Opportunity QA', 'Opportunity QA', 'active', 'mysql-qa')"
                ),
                {"id": project_id, "tenant_id": tenant_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_gaps (
                      id, tenant_id, project_id, gap_type, contract_version,
                      derivation_policy, severity, title, description,
                      answer_snapshot_ids, evidence_snapshot_ids, citation_ids,
                      fact_atom_ids, suggested_asset_type, evidence_summary_json,
                      evidence_sha256, quality_report_sha256, derived_by, status
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'brand_unmentioned',
                      'airank.evidence-gap.v2', 'airank.brand-unmentioned-gap.v1',
                      'high', '真实重复样本未提及品牌', '三次独立样本均未提及。',
                      JSON_ARRAY(:answer_id), JSON_ARRAY(:evidence_id), JSON_ARRAY(:citation_id),
                      JSON_ARRAY(), 'fact_page', JSON_OBJECT('valid_sample_count', 3),
                      :evidence_sha256, :quality_sha256, 'mysql-qa', 'open'
                    )
                    """
                ),
                {
                    "id": gap_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "answer_id": answer_id,
                    "evidence_id": evidence_id,
                    "citation_id": citation_id,
                    "evidence_sha256": sha("gap-evidence" + suffix),
                    "quality_sha256": sha("quality" + suffix),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_buyer_questions (
                      id, tenant_id, project_id, question_text, question_type,
                      intent, funnel_stage, source, priority, status
                    ) VALUES (
                      :id, :tenant_id, :project_id, '有哪些可信 GEO 平台？',
                      'compare', 'commercial', 'consideration', 'manual', 20, 'active'
                    )
                    """
                ),
                {"id": question_id, "tenant_id": tenant_id, "project_id": project_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_scan_runs (
                      id, tenant_id, project_id, name, run_type, cohort_type,
                      repetitions, status, created_by
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'Opportunity citation QA',
                      'baseline', 'blind', 3, 'completed', 'mysql-qa'
                    )
                    """
                ),
                {"id": scan_run_id, "tenant_id": tenant_id, "project_id": project_id},
            )
            answer_text = "某平台可用于企业 GEO 监测。"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, question_id, provider,
                      cohort_type, sample_index, session_id, collector_surface,
                      evidence_level, sample_status, answer_text, answer_sha256,
                      raw_response_sha256, brand_mentioned, mention_class
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :question_id, 'qianwen',
                      'blind', 1, :session_id, 'api', 'provider_api_search_unverified',
                      'valid', :answer_text, :answer_sha256, :raw_sha256, 0, 'not_mentioned'
                    )
                    """
                ),
                {
                    "id": answer_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": scan_run_id,
                    "question_id": question_id,
                    "session_id": f"session_{suffix}",
                    "answer_text": answer_text,
                    "answer_sha256": sha(answer_text),
                    "raw_sha256": sha("raw" + suffix),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_snapshots (
                      id, tenant_id, project_id, answer_snapshot_id,
                      raw_response_json, raw_response_sha256, captured_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :answer_id,
                      :raw_response, :raw_sha256, :captured_at
                    )
                    """
                ),
                {
                    "id": evidence_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "answer_id": answer_id,
                    "raw_response": json.dumps({"answer": answer_text}, ensure_ascii=False),
                    "raw_sha256": sha("raw" + suffix),
                    "captured_at": evaluated_at - timedelta(hours=2),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_source_citations (
                      id, tenant_id, project_id, snapshot_id, citation_order,
                      title, url, host, source_type, cited_text
                    ) VALUES (
                      :id, :tenant_id, :project_id, :snapshot_id, 1,
                      '企业公开页', 'https://example.com/evidence', 'example.com', 'web', '公开证据'
                    )
                    """
                ),
                {"id": citation_id, "tenant_id": tenant_id, "project_id": project_id, "snapshot_id": answer_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_knowledge_sources (
                      id, tenant_id, project_id, source_type, title, source_uri,
                      content_sha256, authority_level, risk_level, status,
                      revision_number, captured_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'website', '旧版官方说明',
                      'https://example.com/old', :content_sha256, 'official',
                      'medium', 'stale', 1, :captured_at
                    )
                    """
                ),
                {
                    "id": source_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "content_sha256": sha("source" + suffix),
                    "captured_at": evaluated_at - timedelta(days=10),
                },
            )
            for job_id in (job_one, job_two, job_three):
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_async_jobs (
                          id, tenant_id, project_id, job_type, status, scheduled_at,
                          finished_at, payload_json, result_json
                        ) VALUES (
                          :id, :tenant_id, :project_id, 'page_audit', 'completed',
                          :scheduled_at, :finished_at, JSON_OBJECT(), JSON_OBJECT()
                        )
                        """
                    ),
                    {
                        "id": job_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "scheduled_at": evaluated_at - timedelta(hours=1),
                        "finished_at": evaluated_at - timedelta(minutes=30),
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_page_audit_runs (
                      id, tenant_id, project_id, job_id, idempotency_key,
                      request_sha256, requested_url, final_url, status,
                      rules_version, evidence_grade, technical_extractability_score,
                      response_status, response_content_type, response_bytes,
                      content_sha256, connected_ip, redirect_count, requested_by,
                      started_at, completed_at, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :job_id, :idempotency_key,
                      :request_sha256, 'https://example.com/', 'https://example.com/',
                      'completed', 'page-rules-v1', 'http_content_snapshot', 68,
                      200, 'text/html', 1024, :content_sha256, '93.184.216.34', 0,
                      'mysql-qa', :started_at, :completed_at, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": page_run_one,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "job_id": job_one,
                    "idempotency_key": f"page-1-{suffix}",
                    "request_sha256": sha("page-request-1" + suffix),
                    "content_sha256": sha("page-content-1" + suffix),
                    "started_at": evaluated_at - timedelta(minutes=40),
                    "completed_at": evaluated_at - timedelta(minutes=30),
                    "created_at": evaluated_at - timedelta(minutes=40),
                    "updated_at": evaluated_at - timedelta(minutes=30),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_page_audit_findings (
                      id, tenant_id, project_id, run_id, rule_id, severity,
                      status, title, description, recommendation, evidence_json,
                      score_delta, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, 'static_body', 'high',
                      'failed', '正文首屏不可提取', '初始 HTML 缺少主要正文。',
                      '输出可抓取的静态正文', JSON_OBJECT('visible_text_chars', 20),
                      -20, :created_at
                    )
                    """
                ),
                {
                    "id": finding_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": page_run_one,
                    "created_at": evaluated_at - timedelta(minutes=30),
                },
            )

        first = repository.derive(
            tenant_id,
            project_id,
            OpportunityDeriveRequest(requested_by="spoofed", as_of=evaluated_at),
            idempotency_key=f"opportunity-first-{suffix}",
            actor="mysql-qa",
            trace_id=f"trc_opportunity_first_{suffix}",
        )
        assert first.opportunity_count == 4
        assert first.new_count == 4
        assert first.persisting_count == 0
        assert first.cleared_count == 0
        assert first.source_counts == {
            "brand_visibility": 1,
            "citation_support": 1,
            "fact_governance": 1,
            "page_extractability": 1,
        }
        assert {item.source_kind for item in first.opportunities} == {
            "brand_visibility",
            "citation_support",
            "fact_governance",
            "page_extractability",
        }
        assert all(
            item.priority_score == item.score_factors.total
            and len(item.source_evidence_sha256) == 64
            and len(item.snapshot_sha256) == 64
            for item in first.opportunities
        )

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_page_audit_runs (
                      id, tenant_id, project_id, job_id, idempotency_key,
                      request_sha256, requested_url, final_url, status,
                      rules_version, evidence_grade, technical_extractability_score,
                      response_status, response_content_type, response_bytes,
                      content_sha256, connected_ip, redirect_count, requested_by,
                      started_at, completed_at, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :job_id, :idempotency_key,
                      :request_sha256, 'https://example.com/', 'https://example.com/',
                      'completed', 'page-rules-v1', 'http_content_snapshot', 65,
                      200, 'text/html', 2048, :content_sha256, '93.184.216.34', 0,
                      'mysql-qa', :started_at, :completed_at, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": page_run_two,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "job_id": job_two,
                    "idempotency_key": f"page-2-{suffix}",
                    "request_sha256": sha("page-request-2" + suffix),
                    "content_sha256": sha("page-content-2" + suffix),
                    "started_at": evaluated_at - timedelta(minutes=20),
                    "completed_at": evaluated_at - timedelta(minutes=10),
                    "created_at": evaluated_at - timedelta(minutes=20),
                    "updated_at": evaluated_at - timedelta(minutes=10),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_page_audit_findings (
                      id, tenant_id, project_id, run_id, rule_id, severity,
                      status, title, description, recommendation, evidence_json,
                      score_delta, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, 'static_body', 'high',
                      'failed', '正文首屏仍不可提取', '第二次审计仍缺少主要正文。',
                      '输出可抓取的静态正文', JSON_OBJECT('visible_text_chars', 24),
                      -20, :created_at
                    )
                    """
                ),
                {
                    "id": finding_two_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": page_run_two,
                    "created_at": evaluated_at - timedelta(minutes=10),
                },
            )

        second = repository.derive(
            tenant_id,
            project_id,
            OpportunityDeriveRequest(
                requested_by="spoofed",
                as_of=evaluated_at + timedelta(minutes=1),
            ),
            idempotency_key=f"opportunity-second-{suffix}",
            actor="mysql-qa",
            trace_id=f"trc_opportunity_second_{suffix}",
        )
        first_page = next(
            item for item in first.opportunities if item.source_kind == "page_extractability"
        )
        second_page = next(
            item for item in second.opportunities if item.source_kind == "page_extractability"
        )
        assert second.opportunity_count == 4
        assert second.new_count == 0
        assert second.persisting_count == 4
        assert second.cleared_count == 0
        assert second_page.opportunity_id == first_page.opportunity_id
        assert second_page.source_evidence_sha256 != first_page.source_evidence_sha256
        assert second_page.source_refs.page_audit_finding_ids == [finding_two_id]

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_page_audit_runs (
                      id, tenant_id, project_id, job_id, idempotency_key,
                      request_sha256, requested_url, final_url, status,
                      rules_version, evidence_grade, technical_extractability_score,
                      response_status, response_content_type, response_bytes,
                      content_sha256, connected_ip, redirect_count, requested_by,
                      started_at, completed_at, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :job_id, :idempotency_key,
                      :request_sha256, 'https://example.com/', 'https://example.com/',
                      'completed', 'page-rules-v1', 'http_content_snapshot', 100,
                      200, 'text/html', 2048, :content_sha256, '93.184.216.34', 0,
                      'mysql-qa', :started_at, :completed_at, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": page_run_three,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "job_id": job_three,
                    "idempotency_key": f"page-3-{suffix}",
                    "request_sha256": sha("page-request-3" + suffix),
                    "content_sha256": sha("page-content-3" + suffix),
                    "started_at": evaluated_at,
                    "completed_at": evaluated_at + timedelta(minutes=10),
                    "created_at": evaluated_at,
                    "updated_at": evaluated_at + timedelta(minutes=10),
                },
            )

        third = repository.derive(
            tenant_id,
            project_id,
            OpportunityDeriveRequest(
                requested_by="spoofed",
                as_of=evaluated_at + timedelta(minutes=11),
            ),
            idempotency_key=f"opportunity-third-{suffix}",
            actor="mysql-qa",
            trace_id=f"trc_opportunity_third_{suffix}",
        )
        replay = repository.derive(
            tenant_id,
            project_id,
            OpportunityDeriveRequest(
                requested_by="another-spoof",
                as_of=evaluated_at + timedelta(minutes=11),
            ),
            idempotency_key=f"opportunity-third-{suffix}",
            actor="mysql-qa",
            trace_id=f"trc_opportunity_replay_{suffix}",
        )
        assert third.opportunity_count == 3
        assert third.new_count == 0
        assert third.persisting_count == 3
        assert third.cleared_count == 1
        assert third.cleared_opportunity_ids == [
            first_page.opportunity_id
        ]
        assert replay.idempotent_replay is True
        assert replay.derivation_run_id == third.derivation_run_id

        listed = repository.list(tenant_id, project_id)
        historical = repository.list(
            tenant_id, project_id, derivation_run_id=first.derivation_run_id
        )
        assert listed.latest_derivation_run is not None
        assert listed.latest_derivation_run.derivation_run_id == third.derivation_run_id
        assert len(listed.opportunities) == 3
        assert len(historical.opportunities) == 4
        with engine.begin() as conn:
            counts = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM airank_opportunity_derivation_runs
                       WHERE tenant_id=:tenant_id AND project_id=:project_id) AS run_count,
                      (SELECT COUNT(*) FROM airank_intervention_opportunity_snapshots
                       WHERE tenant_id=:tenant_id AND project_id=:project_id) AS snapshot_count
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().one()
        assert int(counts["run_count"]) == 3
        assert int(counts["snapshot_count"]) == 11
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM airank_intervention_opportunity_snapshots WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("UPDATE airank_opportunity_derivation_runs SET previous_run_id=NULL WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_opportunity_derivation_runs WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_page_audit_findings WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_page_audit_runs WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_async_jobs WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_source_citations WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_evidence_snapshots WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_answer_snapshots WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_scan_runs WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_buyer_questions WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_content_gaps WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_knowledge_sources WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(text("DELETE FROM airank_projects WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})

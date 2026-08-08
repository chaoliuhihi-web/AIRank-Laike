from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_independent_review_has_storage_contract_and_blind_workflow() -> None:
    migration = read(
        "apps/api/alembic/versions/20260808_0025_independent_evidence_reviews.py"
    )
    routes = read("apps/api/evidence_review_routes.py")
    standard_api = read("apps/api/citation_support_routes.py")

    for token in (
        "airank_evidence_review_cases",
        "purpose",
        "primary_review_id",
        "secondary_review_id",
        "adjudication_review_id",
        "evidence_basis_sha256",
        "consensus_label",
    ):
        assert token in migration
    for route in (
        '"/projects/{project_id}/evidence-review-cases/citation-support"',
        '"/projects/{project_id}/evidence-review-cases/fact-accuracy"',
        '"/evidence-review-cases/{case_id}/decisions"',
        '"/projects/{project_id}/evidence-review-cases"',
        '"/projects/{project_id}/evidence-review-inbox"',
    ):
        assert route in routes
    assert "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN" in routes
    assert "label_conflicts_with_frozen_evidence" in routes
    assert "visible = decisions if final else" in routes
    assert "item.reviewed_by == actor" in routes
    assert "review_visible_to_actor" in standard_api
    assert "Keep peer labels blind" in standard_api


def test_review_assignment_has_persistent_lease_sla_and_blind_owner_contract() -> None:
    migration = read(
        "apps/api/alembic/versions/20260809_0027_evidence_review_assignments.py"
    )
    routes = read("apps/api/evidence_review_routes.py")
    contract = read(
        "packages/contracts/evidence_review_assignment_response.schema.json"
    )
    inbox_contract = read(
        "packages/contracts/evidence_review_inbox_response.schema.json"
    )
    web = read("apps/web/src/App.tsx")
    api = read("apps/web/src/console/api.ts")

    for token in (
        "airank_evidence_review_assignments",
        "airank_evidence_review_assignment_events",
        "active_slot",
        "lease_expires_at",
        "due_at",
        "last_heartbeat_at",
    ):
        assert token in migration
    for route in (
        '"/evidence-review-cases/{case_id}/assignment-claims"',
        '"/evidence-review-assignments/{assignment_id}/heartbeats"',
        '"/evidence-review-assignments/{assignment_id}/release"',
    ):
        assert route in routes
    for token in (
        "EVIDENCE_REVIEW_ASSIGNMENT_CONFLICT",
        "EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED",
        "EVIDENCE_REVIEW_ASSIGNMENT_VERSION_CONFLICT",
        "assigned_to_me_count",
        "unassigned_count",
        "overdue_count",
    ):
        assert token in routes or token in inbox_contract
    assert '"assigned_to"' not in contract
    assert "claimEvidenceReviewAssignment" in api
    assert "heartbeatEvidenceReviewAssignment" in api
    assert "releaseEvidenceReviewAssignment" in api
    assert "领取任务" in web
    assert "SLA 已逾期" in web
    assert "我已领取 · 租约至" in web


def test_review_quality_has_real_agreement_and_kappa_gate() -> None:
    quality = read("packages/evidence/src/airank_evidence/review_quality.py")
    contract = read("packages/contracts/evidence_review_queue_response.schema.json")

    for token in (
        "raw_agreement_rate",
        "cohen_kappa",
        "benchmark_minimum_case_count",
        "benchmark_minimum_kappa",
        "benchmark_quality_passed",
        "review_benchmark_kappa_below_threshold",
    ):
        assert token in quality
        if token != "review_benchmark_kappa_below_threshold":
            assert token in contract
    assert "benchmark_minimum_case_count: int = 20" in quality
    assert "benchmark_minimum_kappa: float = 0.8" in quality


def test_commercial_metrics_and_report_require_final_production_peer_review() -> None:
    citation = read("packages/evidence/src/airank_evidence/citation_support.py")
    fact = read("packages/evidence/src/airank_evidence/fact_accuracy.py")
    report = read("packages/evidence/src/airank_evidence/report.py")
    page = read("apps/web/src/App.tsx")

    for domain in (citation, fact):
        assert 'review_case_purpose == "production"' in domain
        assert 'reviewer_role in {"secondary", "adjudicator"}' in domain
        assert "benchmark_reviews_excluded_from_commercial_metrics" in domain
    assert "commercial review lacks an independent review case" in report
    assert "benchmark review cannot enter commercial metrics" in report
    assert "双人复核与一致性门禁" in page
    assert "单人预审永远不会直接进入客户指标" in page
    assert "benchmark_quality_passed" in page
    assert "我的独立复核待办" in page
    assert "fetchEvidenceReviewInbox(project.id, undefined" in page
    assert "reviewInbox.next_cursor" in page
    assert "争议裁决优先、同优先级按最早创建顺序" in page
    assert "必须先打开原始样本、精确 Claim 和不可变来源" in page
    assert "打开证据样本" in page

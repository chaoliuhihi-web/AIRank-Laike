from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api import opportunity_routes
from apps.api.main import app
from apps.api.opportunity_routes import (
    CONTRACT_VERSION,
    POLICY_VERSION,
    InterventionOpportunityData,
    OpportunityDerivationRunData,
    OpportunityListData,
    OpportunityScoreFactorsData,
    OpportunitySourceRefsData,
    candidate,
    score_factors,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
NOW = datetime(2026, 8, 9, 5, 0, tzinfo=timezone.utc)


def opportunity_data() -> InterventionOpportunityData:
    return InterventionOpportunityData(
        snapshot_id="opportunity_snapshot_" + "a" * 20,
        opportunity_id="opportunity_" + "b" * 20,
        project_id="project_opportunity",
        derivation_run_id="opportunity_run_" + "c" * 20,
        contract_version=CONTRACT_VERSION,
        policy_version=POLICY_VERSION,
        source_kind="brand_visibility",
        source_ref_type="evidence_gap",
        source_ref_id="gap_ev_" + "d" * 20,
        issue_code="brand_unmentioned",
        source_evidence_sha256="e" * 64,
        evidence_level="quality_gated_repeated_samples",
        state="blocked_evidence",
        intervention_gate="evidence_blocked",
        severity="high",
        priority_score=80,
        score_factors=OpportunityScoreFactorsData(
            severity_points=30,
            evidence_points=35,
            urgency_points=15,
            total=80,
        ),
        source_refs=OpportunitySourceRefsData(gap_ids=["gap_ev_" + "d" * 20]),
        title="千问 API 未提及品牌",
        description="重复独立样本显示未提及；不表示任何干预后必然获得模型推荐。",
        recommended_action="collect_enterprise_fact_evidence",
        observed_at=NOW,
        snapshot_sha256="f" * 64,
        created_at=NOW,
    )


def run_data(*, replay: bool = False) -> OpportunityDerivationRunData:
    item = opportunity_data()
    return OpportunityDerivationRunData(
        derivation_run_id=item.derivation_run_id,
        project_id=item.project_id,
        contract_version=CONTRACT_VERSION,
        policy_version=POLICY_VERSION,
        source_basis_sha256="1" * 64,
        evaluated_at=NOW,
        knowledge_window_days=30,
        previous_run_id=None,
        source_counts={
            "brand_visibility": 1,
            "citation_support": 0,
            "fact_governance": 0,
            "page_extractability": 0,
        },
        opportunity_count=1,
        new_count=1,
        persisting_count=0,
        cleared_count=0,
        cleared_opportunity_ids=[],
        opportunities=[item],
        created_by="trusted-user",
        created_at=NOW,
        idempotent_replay=replay,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.actor = ""
        self.filters: tuple[str | None, str | None, str | None] | None = None

    def derive(self, tenant_id, project_id, payload, *, idempotency_key, actor, trace_id):  # noqa: ANN001
        assert tenant_id == "tenant_opportunity"
        assert project_id == "project_opportunity"
        assert payload.knowledge_window_days == 30
        assert idempotency_key == "opportunity-key"
        assert trace_id == "trc_opportunity"
        self.actor = actor
        return run_data()

    def list(self, tenant_id, project_id, *, derivation_run_id=None, source_kind=None, state=None):  # noqa: ANN001
        assert tenant_id == "tenant_opportunity"
        assert project_id == "project_opportunity"
        self.filters = (derivation_run_id, source_kind, state)
        run = run_data()
        return OpportunityListData(
            project_id=project_id,
            contract_version=CONTRACT_VERSION,
            policy_version=POLICY_VERSION,
            latest_derivation_run=run,
            state_counts={"blocked_evidence": 1, "ready_for_action": 0, "monitor": 0},
            source_counts=run.source_counts,
            opportunities=run.opportunities,
        )


def validate_schema(name: str, value: object) -> None:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(value)


def test_priority_score_is_transparent_and_bounded() -> None:
    factors = score_factors("critical", "independently_reviewed_source_page", 25)
    assert factors == {
        "severity_points": 40,
        "evidence_points": 35,
        "urgency_points": 25,
        "total": 100,
    }
    item = candidate(
        tenant_id="tenant_opportunity",
        project_id="project_opportunity",
        source_kind="page_extractability",
        source_ref_type="page_audit_finding",
        source_ref_id="finding_1",
        issue_code="page_static_html",
        evidence_payload={"content_sha256": "a" * 64, "rule": "static_html"},
        evidence_level="content_hashed_page_audit",
        state="ready_for_action",
        intervention_gate="technical_action_ready",
        severity="high",
        urgency_points=15,
        source_refs={
            "gap_ids": [],
            "answer_snapshot_ids": [],
            "evidence_snapshot_ids": [],
            "citation_ids": [],
            "citation_review_ids": [],
            "knowledge_source_ids": [],
            "fact_revision_ids": [],
            "fact_conflict_ids": [],
            "page_audit_run_ids": ["page_audit_1"],
            "page_audit_finding_ids": ["finding_1"],
        },
        title="静态正文不可提取",
        description="技术问题，不代表品牌推荐率。",
        recommended_action="render_static_html",
        observed_at=NOW,
    )
    replay = candidate(
        tenant_id="tenant_opportunity",
        project_id="project_opportunity",
        source_kind="page_extractability",
        source_ref_type="page_audit_finding",
        source_ref_id="finding_1",
        issue_code="page_static_html",
        evidence_payload={"rule": "static_html", "content_sha256": "a" * 64},
        evidence_level="content_hashed_page_audit",
        state="ready_for_action",
        intervention_gate="technical_action_ready",
        severity="high",
        urgency_points=15,
        source_refs=item.source_refs,
        title=item.title,
        description=item.description,
        recommended_action=item.recommended_action,
        observed_at=NOW,
    )
    assert item.opportunity_id == replay.opportunity_id
    assert item.source_evidence_sha256 == replay.source_evidence_sha256
    assert item.priority_score == 70


def test_opportunity_routes_are_strict_and_use_authenticated_actor(monkeypatch) -> None:  # noqa: ANN001
    repository = FakeRepository()
    monkeypatch.setattr(opportunity_routes, "OPPORTUNITY_REPOSITORY", repository)
    client = TestClient(app)

    derived = client.post(
        "/api/v1/projects/project_opportunity/opportunities/derive",
        headers={
            "tenant-id": "tenant_opportunity",
            "Idempotency-Key": "opportunity-key",
            "X-AIRank-Trace-Id": "trc_opportunity",
            "X-AIRank-User-Id": "trusted-user",
        },
        json={"requested_by": "spoofed-user", "knowledge_window_days": 30},
    )
    listed = client.get(
        "/api/v1/projects/project_opportunity/opportunities",
        params={
            "derivation_run_id": "opportunity_run_" + "c" * 20,
            "source_kind": "brand_visibility",
            "state": "blocked_evidence",
        },
        headers={"tenant-id": "tenant_opportunity"},
    )

    assert derived.status_code == 201
    assert listed.status_code == 200
    assert repository.actor == "trusted-user"
    assert repository.filters == (
        "opportunity_run_" + "c" * 20,
        "brand_visibility",
        "blocked_evidence",
    )
    assert derived.json()["data"]["opportunities"][0]["priority_score"] == 80
    assert "必然获得" in derived.json()["data"]["opportunities"][0]["description"]
    validate_schema("opportunity_derivation_request.schema.json", {
        "requested_by": "spoofed-user",
        "knowledge_window_days": 30,
    })
    validate_schema("opportunity_derivation_response.schema.json", derived.json())
    validate_schema("opportunity_list_response.schema.json", listed.json())
    validate_schema(
        "intervention_opportunity.schema.json",
        derived.json()["data"]["opportunities"][0],
    )


def test_opportunity_request_rejects_unknown_fields() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/projects/project_opportunity/opportunities/derive",
        headers={
            "tenant-id": "tenant_opportunity",
            "Idempotency-Key": "opportunity-key-unknown",
            "X-AIRank-User-Id": "trusted-user",
        },
        json={"requested_by": "trusted-user", "brand_recommendation_probability": 0.9},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"

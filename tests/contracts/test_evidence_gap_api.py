from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api import evidence_gap_routes
from apps.api.evidence_gap_routes import (
    DERIVATION_POLICY,
    GAP_CONTRACT_VERSION,
    EvidenceGapData,
    EvidenceGapDerivationData,
    EvidenceGapListData,
    GapSampleEvidence,
    derive_brand_unmentioned_candidates,
)
from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def sample(index: int, *, mentioned: bool = False, session_id: str | None = None) -> GapSampleEvidence:
    return GapSampleEvidence(
        task_id=f"task_{index}",
        question_id="question_gap_1",
        question_text="采购 GEO 监测平台时有哪些可靠选择？",
        question_type="compare",
        question_priority=20,
        provider="qianwen",
        collector_surface="api",
        sample_index=index,
        session_id=session_id or f"session_{index}",
        answer_snapshot_id=f"snapshot_{index}",
        evidence_snapshot_id=f"evidence_{index}",
        answer_sha256=f"{index}" * 64,
        raw_response_sha256=f"{index + 3}" * 64,
        sample_status="valid",
        brand_mentioned=mentioned,
        mention_class="recommended" if mentioned else "not_mentioned",
        citation_ids=(f"citation_{index}",),
    )


def gap_data() -> EvidenceGapData:
    return EvidenceGapData(
        gap_id="gap_ev_1234567890abcdef1234",
        project_id="project_gap",
        run_id="scan_run_gap",
        gap_type="brand_unmentioned",
        contract_version=GAP_CONTRACT_VERSION,
        derivation_policy=DERIVATION_POLICY,
        severity="high",
        title="qianwen · API 未提及品牌",
        description="3 次独立有效样本均未提及品牌。",
        related_question_ids=["question_gap_1"],
        provider="qianwen",
        collector_surface="api",
        valid_sample_count=3,
        normal_unmentioned_count=3,
        answer_snapshot_ids=["snapshot_1", "snapshot_2", "snapshot_3"],
        evidence_snapshot_ids=["evidence_1", "evidence_2", "evidence_3"],
        citation_ids=["citation_1", "citation_2", "citation_3"],
        fact_atom_ids=[],
        suggested_asset_type="comparison_page",
        evidence_sha256="a" * 64,
        quality_report_sha256="b" * 64,
        status="open",
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )


def test_derives_only_repeated_independent_normal_unmentioned_samples() -> None:
    candidates, skipped, evidence_basis_sha256 = derive_brand_unmentioned_candidates(
        tenant_id="tenant_gap",
        project_id="project_gap",
        run_id="scan_run_gap",
        repetitions=3,
        quality_report_sha256="b" * 64,
        samples=[sample(1), sample(2), sample(3)],
    )

    assert skipped == 0
    assert len(candidates) == 1
    assert candidates[0].severity == "high"
    assert candidates[0].suggested_asset_type == "comparison_page"
    assert candidates[0].answer_snapshot_ids == ("snapshot_1", "snapshot_2", "snapshot_3")
    assert len(candidates[0].evidence_sha256) == 64
    assert len(evidence_basis_sha256) == 64

    replay, replay_skipped, replay_basis = derive_brand_unmentioned_candidates(
        tenant_id="tenant_gap",
        project_id="project_gap",
        run_id="scan_run_gap",
        repetitions=3,
        quality_report_sha256="b" * 64,
        samples=[sample(3), sample(1), sample(2)],
    )
    assert replay == candidates
    assert replay_skipped == skipped
    assert replay_basis == evidence_basis_sha256


def test_skips_mentioned_or_reused_session_groups_without_deleting_samples() -> None:
    mentioned, mentioned_skipped, _ = derive_brand_unmentioned_candidates(
        tenant_id="tenant_gap",
        project_id="project_gap",
        run_id="scan_run_gap",
        repetitions=3,
        quality_report_sha256="b" * 64,
        samples=[sample(1), sample(2, mentioned=True), sample(3)],
    )
    reused, reused_skipped, _ = derive_brand_unmentioned_candidates(
        tenant_id="tenant_gap",
        project_id="project_gap",
        run_id="scan_run_gap",
        repetitions=3,
        quality_report_sha256="b" * 64,
        samples=[sample(1, session_id="same"), sample(2, session_id="same"), sample(3)],
    )

    assert mentioned == [] and mentioned_skipped == 1
    assert reused == [] and reused_skipped == 1


class FakeRepository:
    def __init__(self) -> None:
        self.gap = gap_data()
        self.actor = ""

    def list(self, tenant_id: str, project_id: str) -> EvidenceGapListData:
        assert tenant_id == "tenant_gap"
        assert project_id == "project_gap"
        return EvidenceGapListData(
            project_id=project_id,
            contract_version=GAP_CONTRACT_VERSION,
            gaps=[self.gap],
            governed_gap_count=1,
            unverified_legacy_count=2,
        )

    def derive(self, tenant_id: str, project_id: str, payload, *, idempotency_key: str, actor: str, trace_id: str) -> EvidenceGapDerivationData:  # noqa: ANN001
        assert tenant_id == "tenant_gap"
        assert project_id == "project_gap"
        assert payload.run_id == "scan_run_gap"
        assert idempotency_key == "gap-contract-key"
        assert trace_id == "trc_gap_contract"
        self.actor = actor
        return EvidenceGapDerivationData(
            derivation_run_id="gap_run_1234567890abcdef1234",
            project_id=project_id,
            run_id=payload.run_id,
            contract_version=GAP_CONTRACT_VERSION,
            derivation_policy=DERIVATION_POLICY,
            quality_report_sha256="b" * 64,
            evidence_basis_sha256="c" * 64,
            gap_count=1,
            skipped_group_count=0,
            gaps=[self.gap],
            created_by=actor,
            created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )


def test_evidence_gap_routes_match_contract_and_use_authenticated_actor(monkeypatch) -> None:  # noqa: ANN001
    repository = FakeRepository()
    monkeypatch.setattr(evidence_gap_routes, "EVIDENCE_GAP_REPOSITORY", repository)
    client = TestClient(app)

    listed = client.get(
        "/api/v1/projects/project_gap/evidence-gaps",
        headers={"tenant-id": "tenant_gap", "X-AIRank-Trace-Id": "trc_gap_list"},
    )
    derived = client.post(
        "/api/v1/projects/project_gap/evidence-gaps/derive",
        headers={
            "tenant-id": "tenant_gap",
            "X-AIRank-Trace-Id": "trc_gap_contract",
            "X-AIRank-User-Id": "trusted-reviewer",
            "Idempotency-Key": "gap-contract-key",
        },
        json={"run_id": "scan_run_gap", "requested_by": "spoofed-user"},
    )

    assert listed.status_code == 200
    assert derived.status_code == 201
    assert repository.actor == "trusted-reviewer"
    assert derived.json()["data"]["gaps"][0]["normal_unmentioned_count"] == 3
    assert listed.json()["data"]["unverified_legacy_count"] == 2
    for response, contract_name in (
        (listed, "evidence_gap_list_response.schema.json"),
        (derived, "evidence_gap_derivation_response.schema.json"),
    ):
        schema = json.loads((CONTRACTS / contract_name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(response.json())


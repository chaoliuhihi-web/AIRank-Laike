from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from airank_domain.measurement import sha256_text
from apps.api import citation_support_routes, evidence_review_routes
from apps.api.main import app


ANSWER = "AIRank 的指标可以下钻到原始样本，但发布内容不等于一定会被模型推荐。"
CITED = "AIRank 的指标可以从汇总结果下钻到原始回答和引用来源。"
SOURCE = "来源页面直接支持该断言。"
CONTRACT_ROOT = Path(__file__).resolve().parents[2] / "packages" / "contracts"


def validate_contract(name: str, payload: dict) -> None:
    schema = json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


@pytest.fixture()
def repositories(monkeypatch: pytest.MonkeyPatch):
    citation_repo = citation_support_routes.InMemoryCitationSupportRepository()
    citation_repo.seed_sample(
        tenant_id="tenant_1",
        project_id="project_1",
        snapshot_id="snapshot_1",
        answer_text=ANSWER,
        citation_id="citation_1",
        cited_text=CITED,
    )
    citation_repo.seed_source_object(
        tenant_id="tenant_1",
        project_id="project_1",
        object_ref_id="object_source_1",
        sha256="b" * 64,
        kind="citation_source_page",
        citation_id="citation_1",
    )
    citation_repo.seed_source_capture(
        tenant_id="tenant_1",
        project_id="project_1",
        capture_id="capture_1",
        citation_id="citation_1",
        raw_object_ref_id="object_source_1",
        content_sha256="b" * 64,
        segment_id="segment_1",
        segment_text=SOURCE,
    )
    review_repo = evidence_review_routes.InMemoryEvidenceReviewRepository()
    escalation_repo = (
        evidence_review_routes.InMemoryEvidenceReviewEscalationRepository()
    )
    monkeypatch.setattr(citation_support_routes, "CITATION_SUPPORT_REPOSITORY", citation_repo)
    monkeypatch.setattr(evidence_review_routes, "EVIDENCE_REVIEW_REPOSITORY", review_repo)
    monkeypatch.setattr(
        evidence_review_routes,
        "EVIDENCE_REVIEW_ESCALATION_REPOSITORY",
        escalation_repo,
    )
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    return citation_repo, review_repo


@pytest.fixture()
def client(repositories) -> TestClient:
    del repositories
    return TestClient(app)


def create_claim(client: TestClient, *, fact: bool = False) -> str:
    response = client.post(
        "/api/v1/samples/snapshot_1/citation-claims",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "claim-reviewer"},
        json={
            "answer_start": 0,
            "answer_end": ANSWER.index("，"),
            "extraction_method": "manual",
            "claim_kind": "brand_fact" if fact else "unclassified",
            "subject_entity_text": "AIRank" if fact else None,
            "created_by": "spoofed",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["claim_id"]


def test_sla_escalation_contract_is_empty_without_persisted_outbox(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/projects/project_1/evidence-review-escalations?status=pending&limit=50",
        headers={"tenant-id": "tenant_1"},
    )
    assert response.status_code == 200
    validate_contract("evidence_review_escalation_response.schema.json", response.json())
    assert response.json()["data"] == {
        "project_id": "project_1",
        "escalation_count": 0,
        "pending_count": 0,
        "published_count": 0,
        "failed_count": 0,
        "canceled_count": 0,
        "escalations": [],
    }

    invalid = client.get(
        "/api/v1/projects/project_1/evidence-review-escalations?status=delivered",
        headers={"tenant-id": "tenant_1"},
    )
    assert invalid.status_code == 422


def citation_case_payload(claim_id: str, *, purpose: str = "production") -> dict:
    return {
        "claim_id": claim_id,
        "purpose": purpose,
        "review": {
            "citation_id": "citation_1",
            "support_label": "supports",
            "evidence_grade": "source_page_snapshot",
            "source_excerpt": SOURCE,
            "source_content_sha256": "b" * 64,
            "source_object_ref_id": "object_source_1",
            "source_capture_id": "capture_1",
            "source_segment_id": "segment_1",
            "source_start": 0,
            "source_end": len(SOURCE),
            "rationale": "第一审核人独立核对不可变来源页。",
            "review_method": "human",
            "reviewed_by": "spoofed-primary",
        },
    }


def test_single_review_is_hidden_from_peer_and_cannot_enter_support_rate(client: TestClient) -> None:
    claim_id = create_claim(client)
    created = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-1", "Idempotency-Key": "review-case-citation-1"},
        json=citation_case_payload(claim_id),
    )
    assert created.status_code == 201
    validate_contract("evidence_review_case_response.schema.json", created.json())
    case = created.json()["data"]
    assert case["status"] == "awaiting_secondary"
    assert case["current_actor_role"] == "primary"
    assert case["visible_decisions"][0]["label"] == "supports"

    peer_response = client.get(
        "/api/v1/projects/project_1/evidence-review-cases?snapshot_id=snapshot_1",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
    )
    validate_contract("evidence_review_queue_response.schema.json", peer_response.json())
    peer = peer_response.json()["data"]
    assert peer["cases"][0]["visible_decisions"] == []
    assert peer["cases"][0]["next_action"] == "submit_secondary"

    peer_bundle = client.get(
        "/api/v1/samples/snapshot_1/citation-support",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
    ).json()["data"]
    assert peer_bundle["reviews"] == []
    assert peer_bundle["metrics"]["known_limitations"] == ["citation_support_not_reviewed"]

    primary_bundle = client.get(
        "/api/v1/samples/snapshot_1/citation-support",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-1"},
    ).json()["data"]
    assert len(primary_bundle["reviews"]) == 1
    metrics = primary_bundle["metrics"]
    assert metrics["commercially_verified_review_count"] == 0
    assert metrics["citation_support_rate"] is None
    assert "citation_support_independent_review_required" in metrics["known_limitations"]

    rejected = client.post(
        f"/api/v1/evidence-review-cases/{case['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-1"},
        json={"label": "supports", "rationale": "不能自己做第二次复核。", "reviewed_by": "spoofed"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN"


def test_actor_inbox_is_blind_prioritized_and_cursor_paginated(
    client: TestClient, repositories
) -> None:
    _, review_repo = repositories
    claim_id = create_claim(client)
    created = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "reviewer-1",
            "Idempotency-Key": "review-inbox-priority-case",
        },
        json=citation_case_payload(claim_id, purpose="benchmark"),
    ).json()["data"]
    disputed = client.post(
        f"/api/v1/evidence-review-cases/{created['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={
            "label": "contradicts",
            "rationale": "第二审核人与第一审核人结论不同。",
            "reviewed_by": "spoofed",
        },
    ).json()["data"]
    assert disputed["status"] == "disputed"

    disputed_case = review_repo.cases[created["case_id"]]
    awaiting_case = deepcopy(disputed_case)
    awaiting_case_id = "evidence_review_case_inbox_awaiting"
    awaiting_case.update(
        case_id=awaiting_case_id,
        status="awaiting_secondary",
        evidence_basis_sha256="c" * 64,
        consensus_label=None,
        decisions=[awaiting_case["decisions"][0]],
        created_at=awaiting_case["created_at"] - timedelta(days=1),
        finalized_by=None,
        finalized_at=None,
    )
    review_repo.cases[awaiting_case_id] = awaiting_case

    participated_case = deepcopy(awaiting_case)
    participated_case_id = "evidence_review_case_inbox_participated"
    participated_case.update(
        case_id=participated_case_id,
        evidence_basis_sha256="d" * 64,
        decisions=[
            participated_case["decisions"][0].model_copy(
                update={"reviewed_by": "reviewer-3"}
            )
        ],
    )
    review_repo.cases[participated_case_id] = participated_case

    first = client.get(
        "/api/v1/projects/project_1/evidence-review-inbox?limit=1",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    )
    assert first.status_code == 200
    validate_contract("evidence_review_inbox_response.schema.json", first.json())
    first_data = first.json()["data"]
    assert first_data["actionable_count"] == 2
    assert first_data["awaiting_secondary_count"] == 1
    assert first_data["adjudication_count"] == 1
    assert first_data["cases"][0]["status"] == "disputed"
    assert first_data["cases"][0]["next_action"] == "adjudicate"
    assert first_data["cases"][0]["visible_decisions"] == []
    assert first_data["next_cursor"]

    second = client.get(
        "/api/v1/projects/project_1/evidence-review-inbox",
        params={"limit": 1, "cursor": first_data["next_cursor"]},
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    )
    assert second.status_code == 200
    validate_contract("evidence_review_inbox_response.schema.json", second.json())
    second_data = second.json()["data"]
    assert [item["case_id"] for item in second_data["cases"]] == [awaiting_case_id]
    assert second_data["cases"][0]["next_action"] == "submit_secondary"
    assert second_data["next_cursor"] is None

    invalid = client.get(
        "/api/v1/projects/project_1/evidence-review-inbox?cursor=not-a-cursor",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "EVIDENCE_REVIEW_CURSOR_INVALID"

    tampered = client.get(
        "/api/v1/projects/project_1/evidence-review-inbox",
        params={"cursor": f"{first_data['next_cursor']}$"},
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    )
    assert tampered.status_code == 422
    assert tampered.json()["error"]["code"] == "EVIDENCE_REVIEW_CURSOR_INVALID"


def test_assignment_lease_prevents_duplicate_work_and_preserves_sla(
    client: TestClient,
    repositories,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, review_repo = repositories
    clock = [datetime(2026, 8, 9, 1, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(evidence_review_routes, "now_utc", lambda: clock[0])
    monkeypatch.setenv("AIRANK_EVIDENCE_REVIEW_LEASE_SECONDS", "60")
    monkeypatch.setenv("AIRANK_EVIDENCE_REVIEW_SECONDARY_SLA_SECONDS", "300")
    monkeypatch.setenv("AIRANK_EVIDENCE_REVIEW_DUE_SOON_SECONDS", "60")

    claim_id = create_claim(client)
    created = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "reviewer-1",
            "Idempotency-Key": "review-assignment-case",
        },
        json=citation_case_payload(claim_id, purpose="benchmark"),
    ).json()["data"]

    initial = client.get(
        "/api/v1/projects/project_1/evidence-review-inbox",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
    ).json()["data"]
    assert initial["actionable_count"] == 1
    assert initial["assigned_to_me_count"] == 0
    assert initial["unassigned_count"] == 1
    assert initial["overdue_count"] == 0
    assert initial["cases"][0]["assignment"]["state"] == "unassigned"

    assignment_response = client.post(
        f"/api/v1/evidence-review-cases/{created['case_id']}/assignment-claims",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"expected_case_version": created["version"]},
    )
    assert assignment_response.status_code == 201
    validate_contract(
        "evidence_review_assignment_response.schema.json",
        assignment_response.json(),
    )
    assignment = assignment_response.json()["data"]
    assert assignment["state"] == "assigned_to_me"
    assert assignment["owned_by_current_actor"] is True
    assert assignment["sla_state"] == "on_track"
    assert assignment["version"] == 1
    assert "assigned_to" not in assignment

    replay = client.post(
        f"/api/v1/evidence-review-cases/{created['case_id']}/assignment-claims",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"expected_case_version": created["version"]},
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["assignment_id"] == assignment["assignment_id"]
    assert replay.json()["data"]["idempotent_replay"] is True

    owner_inbox = client.get(
        "/api/v1/projects/project_1/evidence-review-inbox",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
    ).json()["data"]
    assert owner_inbox["assigned_to_me_count"] == 1
    assert owner_inbox["unassigned_count"] == 0
    assert owner_inbox["cases"][0]["assignment"]["state"] == "assigned_to_me"

    other_inbox = client.get(
        "/api/v1/projects/project_1/evidence-review-inbox",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    ).json()["data"]
    assert other_inbox["actionable_count"] == 0
    peer_queue = client.get(
        "/api/v1/projects/project_1/evidence-review-cases",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    ).json()["data"]
    assert peer_queue["cases"][0]["next_action"] == "none"
    assert peer_queue["cases"][0]["assignment"]["state"] == "assigned_to_other"
    assert "assigned_to" not in peer_queue["cases"][0]["assignment"]

    conflicting_decision = client.post(
        f"/api/v1/evidence-review-cases/{created['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
        json={
            "label": "supports",
            "rationale": "租约仍属于另一审核人。",
            "reviewed_by": "spoofed",
        },
    )
    assert conflicting_decision.status_code == 409
    assert conflicting_decision.json()["error"]["code"] == "EVIDENCE_REVIEW_ASSIGNMENT_CONFLICT"

    forbidden_heartbeat = client.post(
        f"/api/v1/evidence-review-assignments/{assignment['assignment_id']}/heartbeats",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
        json={"expected_version": assignment["version"]},
    )
    assert forbidden_heartbeat.status_code == 403
    assert forbidden_heartbeat.json()["error"]["code"] == "EVIDENCE_REVIEW_ASSIGNMENT_OWNER_FORBIDDEN"

    clock[0] += timedelta(seconds=30)
    heartbeat = client.post(
        f"/api/v1/evidence-review-assignments/{assignment['assignment_id']}/heartbeats",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"expected_version": assignment["version"]},
    )
    assert heartbeat.status_code == 200
    heartbeat_data = heartbeat.json()["data"]
    assert heartbeat_data["version"] == 2
    assert heartbeat_data["due_at"] == assignment["due_at"]

    stale_heartbeat = client.post(
        f"/api/v1/evidence-review-assignments/{assignment['assignment_id']}/heartbeats",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"expected_version": 1},
    )
    assert stale_heartbeat.status_code == 409
    assert stale_heartbeat.json()["error"]["code"] == "EVIDENCE_REVIEW_ASSIGNMENT_VERSION_CONFLICT"

    released = client.post(
        f"/api/v1/evidence-review-assignments/{assignment['assignment_id']}/release",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"expected_version": 2, "reason": "交还给待办池。"},
    )
    assert released.status_code == 200
    assert released.json()["data"]["state"] == "released"

    second_owner = client.post(
        f"/api/v1/evidence-review-cases/{created['case_id']}/assignment-claims",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
        json={"expected_case_version": created["version"]},
    ).json()["data"]
    assert second_owner["assignment_id"] != assignment["assignment_id"]

    clock[0] += timedelta(seconds=61)
    expired = client.post(
        f"/api/v1/evidence-review-assignments/{second_owner['assignment_id']}/heartbeats",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
        json={"expected_version": second_owner["version"]},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED"

    reclaimed = client.post(
        f"/api/v1/evidence-review-cases/{created['case_id']}/assignment-claims",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"expected_case_version": created["version"]},
    ).json()["data"]
    completed = client.post(
        f"/api/v1/evidence-review-cases/{created['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={
            "label": "supports",
            "rationale": "重新领取后完成独立复核。",
            "reviewed_by": "spoofed",
        },
    )
    assert completed.status_code == 201
    assert completed.json()["data"]["status"] == "agreed"
    assert review_repo.assignments[reclaimed["assignment_id"]]["status"] == "completed"
    assert {
        "claimed",
        "heartbeat",
        "released",
        "expired",
        "completed",
    } <= {item["event_type"] for item in review_repo.assignment_events}


def test_two_distinct_matching_reviewers_finalize_commercial_support(client: TestClient) -> None:
    claim_id = create_claim(client)
    case = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-1", "Idempotency-Key": "review-case-citation-2"},
        json=citation_case_payload(claim_id),
    ).json()["data"]

    completed = client.post(
        f"/api/v1/evidence-review-cases/{case['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"label": "supports", "rationale": "第二审核人独立核对后同意。", "reviewed_by": "spoofed"},
    )
    assert completed.status_code == 201
    data = completed.json()["data"]
    assert data["status"] == "agreed"
    assert data["consensus_label"] == "supports"
    assert data["decision_count"] == 2
    assert len(data["visible_decisions"]) == 2

    metrics = client.get(
        "/api/v1/samples/snapshot_1/citation-support",
        headers={"tenant-id": "tenant_1"},
    ).json()["data"]["metrics"]
    assert metrics["commercially_verified_review_count"] == 1
    assert metrics["citation_support_rate"] == 1.0


def test_disagreement_requires_third_distinct_adjudicator_and_is_measured(client: TestClient) -> None:
    claim_id = create_claim(client)
    case = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-1", "Idempotency-Key": "review-case-benchmark-1"},
        json=citation_case_payload(claim_id, purpose="benchmark"),
    ).json()["data"]
    disputed = client.post(
        f"/api/v1/evidence-review-cases/{case['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-2"},
        json={"label": "contradicts", "rationale": "第二审核人认为原文相反。", "reviewed_by": "spoofed"},
    ).json()["data"]
    assert disputed["status"] == "disputed"
    assert len(disputed["visible_decisions"]) == 1
    assert disputed["visible_decisions"][0]["reviewer_role"] == "secondary"
    assert disputed["visible_decisions"][0]["reviewed_by"] == "reviewer-2"

    adjudicated = client.post(
        f"/api/v1/evidence-review-cases/{case['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
        json={"label": "supports", "rationale": "裁决人复核精确原文后确认支持。", "reviewed_by": "spoofed"},
    )
    assert adjudicated.status_code == 201
    assert adjudicated.json()["data"]["status"] == "adjudicated"
    assert adjudicated.json()["data"]["decision_count"] == 3
    benchmark_only_metrics = client.get(
        "/api/v1/samples/snapshot_1/citation-support",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    ).json()["data"]["metrics"]
    assert benchmark_only_metrics["citation_support_rate"] is None
    assert benchmark_only_metrics["commercially_verified_review_count"] == 0
    assert "benchmark_reviews_excluded_from_commercial_metrics" in benchmark_only_metrics["known_limitations"]

    quality = client.get(
        "/api/v1/projects/project_1/evidence-review-cases?snapshot_id=snapshot_1",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-3"},
    ).json()["data"]["benchmark_quality"]
    assert quality["independently_reviewed_case_count"] == 1
    assert quality["disagreement_count"] == 1
    assert quality["adjudicated_count"] == 1
    assert quality["benchmark_ready"] is False
    assert "review_benchmark_sample_too_small" in quality["known_limitations"]


def test_fact_accuracy_also_requires_independent_agreement(client: TestClient, repositories) -> None:
    citation_repo, _ = repositories
    claim_id = create_claim(client, fact=True)
    fact_text = ANSWER[: ANSWER.index("，")]
    citation_repo.seed_approved_fact(
        tenant_id="tenant_1",
        project_id="project_1",
        fact_revision_id="factrev_1",
        fact_text=fact_text,
        knowledge_source_id="source_1",
        knowledge_segment_id="fact_segment_1",
        source_content=f"企业事实：{fact_text}",
    )
    created = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/fact-accuracy",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "fact-reviewer-1", "Idempotency-Key": "review-case-fact-1"},
        json={
            "claim_id": claim_id,
            "purpose": "production",
            "review": {
                "verdict": "accurate",
                "fact_revision_id": "factrev_1",
                "rationale": "第一审核人核对审核事实和原文边界。",
                "review_method": "human",
                "reviewed_by": "spoofed",
            },
        },
    )
    assert created.status_code == 201
    before = client.get(
        "/api/v1/samples/snapshot_1/fact-accuracy", headers={"tenant-id": "tenant_1"}
    ).json()["data"]["metrics"]
    assert before["fact_accuracy"] is None

    completed = client.post(
        f"/api/v1/evidence-review-cases/{created.json()['data']['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "fact-reviewer-2"},
        json={"label": "accurate", "rationale": "第二审核人独立核对后同意。", "reviewed_by": "spoofed"},
    )
    assert completed.status_code == 201
    after = client.get(
        "/api/v1/samples/snapshot_1/fact-accuracy", headers={"tenant-id": "tenant_1"}
    ).json()["data"]["metrics"]
    assert after["commercially_verified_claim_count"] == 1
    assert after["fact_accuracy"] == 1.0


def test_fact_peer_label_cannot_change_the_frozen_evidence_class(client: TestClient, repositories) -> None:
    citation_repo, _ = repositories
    claim_id = create_claim(client, fact=True)
    fact_text = ANSWER[: ANSWER.index("，")]
    citation_repo.seed_approved_fact(
        tenant_id="tenant_1",
        project_id="project_1",
        fact_revision_id="factrev_frozen_evidence",
        fact_text=fact_text,
        knowledge_source_id="source_frozen_evidence",
        knowledge_segment_id="segment_frozen_evidence",
        source_content=f"企业事实：{fact_text}",
    )
    created = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/fact-accuracy",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "fact-reviewer-1",
            "Idempotency-Key": "review-case-frozen-evidence",
        },
        json={
            "claim_id": claim_id,
            "purpose": "production",
            "review": {
                "verdict": "accurate",
                "fact_revision_id": "factrev_frozen_evidence",
                "rationale": "第一审核人绑定审核事实和精确原文。",
                "review_method": "human",
                "reviewed_by": "spoofed",
            },
        },
    )
    assert created.status_code == 201

    invalid = client.post(
        f"/api/v1/evidence-review-cases/{created.json()['data']['case_id']}/decisions",
        headers={"tenant-id": "tenant_1", "X-AIRank-User-Id": "fact-reviewer-2"},
        json={
            "label": "insufficient_evidence",
            "rationale": "试图在不改变冻结证据的情况下改成无证据。",
            "reviewed_by": "spoofed",
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "EVIDENCE_REVIEW_LABEL_INVALID"
    assert invalid.json()["error"]["details"]["reason"] == "label_conflicts_with_frozen_evidence"


def test_case_creation_is_idempotent_and_payload_conflicts_fail(client: TestClient) -> None:
    claim_id = create_claim(client)
    headers = {"tenant-id": "tenant_1", "X-AIRank-User-Id": "reviewer-1", "Idempotency-Key": "review-case-idempotent"}
    first = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers=headers,
        json=citation_case_payload(claim_id),
    )
    replay = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers=headers,
        json=citation_case_payload(claim_id),
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["case_id"] == first.json()["data"]["case_id"]
    assert replay.json()["data"]["idempotent_replay"] is True

    changed = citation_case_payload(claim_id)
    changed["review"]["support_label"] = "contradicts"
    conflict = client.post(
        "/api/v1/projects/project_1/evidence-review-cases/citation-support",
        headers=headers,
        json=changed,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

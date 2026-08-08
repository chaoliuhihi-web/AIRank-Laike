from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, ValidationError

from apps.api import opportunity_action_routes
from apps.api.main import app
from apps.api.opportunity_action_routes import (
    ACTION_CONTRACT_VERSION,
    OpportunityActionData,
    OpportunityActionListData,
    sla_state,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
NOW = datetime(2026, 8, 9, 7, 0, tzinfo=timezone.utc)


def action_data(*, replay: bool = False) -> OpportunityActionData:
    return OpportunityActionData(
        action_id="opportunity_action_" + "a" * 20,
        project_id="project_action",
        opportunity_id="opportunity_" + "b" * 20,
        contract_version=ACTION_CONTRACT_VERSION,
        source_kind="brand_visibility",
        action_type="collect_enterprise_fact_evidence",
        status="evidence_blocked",
        source_snapshot_id="opportunity_snapshot_" + "c" * 20,
        source_derivation_run_id="opportunity_run_" + "d" * 20,
        source_snapshot_sha256="e" * 64,
        source_evidence_sha256="f" * 64,
        latest_snapshot_id="opportunity_snapshot_" + "c" * 20,
        latest_derivation_run_id="opportunity_run_" + "d" * 20,
        latest_snapshot_sha256="e" * 64,
        latest_evidence_sha256="f" * 64,
        assigned_to=None,
        assigned_at=None,
        due_at=NOW + timedelta(days=7),
        sla_state="on_track",
        action_note="先补齐企业事实证据，不能把行动完成包装成推荐增长。",
        verification_run_id=None,
        verification_basis_sha256=None,
        closure_reason=None,
        effect_claim_allowed=False,
        event_count=1,
        last_event_sha256="1" * 64,
        created_by="trusted-user",
        updated_by="trusted-user",
        version=1,
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
        idempotent_replay=replay,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.actors: list[str] = []

    def create(self, tenant_id, project_id, snapshot_id, payload, *, idempotency_key, actor, trace_id):  # noqa: ANN001
        assert (tenant_id, project_id) == ("tenant_action", "project_action")
        assert snapshot_id == "opportunity_snapshot_" + "c" * 20
        assert idempotency_key == "action-create-key"
        self.actors.append(actor)
        return action_data()

    def claim(self, tenant_id, project_id, action_id, payload, *, idempotency_key, actor, trace_id):  # noqa: ANN001
        self.actors.append(actor)
        return action_data()

    def transition(self, tenant_id, project_id, action_id, payload, *, idempotency_key, actor, trace_id):  # noqa: ANN001
        self.actors.append(actor)
        return action_data()

    def list(self, tenant_id, project_id):  # noqa: ANN001
        item = action_data()
        return OpportunityActionListData(
            project_id=project_id,
            contract_version=ACTION_CONTRACT_VERSION,
            actions=[item],
            open_count=0,
            evidence_blocked_count=1,
            overdue_count=0,
            final_count=0,
        )


def load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_action_routes_use_authenticated_actor_and_real_state(monkeypatch) -> None:  # noqa: ANN001
    repository = FakeRepository()
    monkeypatch.setattr(opportunity_action_routes, "OPPORTUNITY_ACTION_REPOSITORY", repository)
    client = TestClient(app)
    snapshot_id = "opportunity_snapshot_" + "c" * 20
    response = client.post(
        f"/api/v1/projects/project_action/opportunities/{snapshot_id}/actions",
        headers={
            "tenant-id": "tenant_action",
            "Idempotency-Key": "action-create-key",
            "X-AIRank-User-Id": "trusted-user",
        },
        json={"requested_by": "spoofed-user", "due_in_days": 7},
    )
    listed = client.get(
        "/api/v1/projects/project_action/opportunity-actions",
        headers={"tenant-id": "tenant_action"},
    )
    assert response.status_code == 201
    assert listed.status_code == 200
    assert repository.actors == ["trusted-user"]
    assert response.json()["data"]["effect_claim_allowed"] is False
    assert listed.json()["data"]["evidence_blocked_count"] == 1
    Draft202012Validator(load_schema("opportunity_action.schema.json"), format_checker=Draft202012Validator.FORMAT_CHECKER).validate(response.json()["data"])


def test_action_request_schemas_are_strict_and_final_transitions_acknowledge_limits() -> None:
    create = load_schema("opportunity_action_create_request.schema.json")
    claim = load_schema("opportunity_action_claim_request.schema.json")
    transition = load_schema("opportunity_action_transition_request.schema.json")
    for name in (
        "opportunity_action_create_request.schema.json",
        "opportunity_action_claim_request.schema.json",
        "opportunity_action_transition_request.schema.json",
        "opportunity_action.schema.json",
        "opportunity_action_response.schema.json",
        "opportunity_action_list_response.schema.json",
    ):
        Draft202012Validator.check_schema(load_schema(name))
    Draft202012Validator(create).validate({"requested_by": "user", "due_in_days": 14})
    Draft202012Validator(claim).validate({"requested_by": "user", "expected_version": 1})
    valid = {
        "transition": "verify_not_observed",
        "requested_by": "user",
        "expected_version": 2,
        "reason": "最新完整复测中未再观察到该问题",
        "verification_run_id": "opportunity_run_" + "a" * 20,
        "acknowledge_no_outcome_claim": True,
    }
    Draft202012Validator(transition).validate(valid)
    invalid = {**valid, "acknowledge_no_outcome_claim": False}
    try:
        Draft202012Validator(transition).validate(invalid)
    except ValidationError:
        pass
    else:
        raise AssertionError("verification transition must acknowledge that no outcome claim is allowed")


def test_sla_state_is_derived_and_final_state_wins() -> None:
    assert sla_state(NOW - timedelta(seconds=1), "open", at=NOW) == "overdue"
    assert sla_state(NOW + timedelta(hours=12), "in_progress", at=NOW) == "due_soon"
    assert sla_state(NOW + timedelta(days=2), "evidence_blocked", at=NOW) == "on_track"
    assert sla_state(NOW - timedelta(days=2), "verified_not_observed", at=NOW) == "final"

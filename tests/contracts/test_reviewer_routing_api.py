from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import reviewer_routing_routes
from apps.api.main import app


CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "contracts"
    / "evidence_review_routing_response.schema.json"
)


def validate(payload: dict) -> None:
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=FormatChecker()
    ).validate(payload)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        reviewer_routing_routes,
        "REVIEWER_ROUTING_REPOSITORY",
        reviewer_routing_routes.InMemoryReviewerRoutingRepository(),
    )
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    return TestClient(app)


def test_routing_defaults_to_explicit_legacy_mode(client: TestClient) -> None:
    response = client.get(
        "/api/v1/projects/project_1/evidence-review-routing",
        headers={"tenant-id": "tenant_1"},
    )
    assert response.status_code == 200
    validate(response.json())
    assert response.json()["data"] == {
        "project_id": "project_1",
        "routing_mode": "unrestricted_legacy",
        "external_sync_state": "not_configured",
        "teams": [],
        "routes": [],
        "known_limitations": [
            "yudao_group_sync_not_verified",
            "external_notification_delivery_not_verified",
        ],
    }


def test_manual_team_member_and_role_route_are_versioned_and_truthful(
    client: TestClient,
) -> None:
    headers = {
        "tenant-id": "tenant_1",
        "X-AIRank-User-Id": "review-admin",
        "Idempotency-Key": "review-team-create-001",
    }
    created = client.post(
        "/api/v1/projects/project_1/evidence-review-teams",
        headers=headers,
        json={"name": "核心证据复核组"},
    )
    assert created.status_code == 201
    validate(created.json())
    team = created.json()["data"]["teams"][0]
    assert team["external_source"] == "manual"
    assert team["external_sync_state"] == "not_configured"
    assert team["idempotent_replay"] is False

    replay = client.post(
        "/api/v1/projects/project_1/evidence-review-teams",
        headers=headers,
        json={"name": "核心证据复核组"},
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["teams"][0]["idempotent_replay"] is True

    duplicate = client.post(
        "/api/v1/projects/project_1/evidence-review-teams",
        headers={**headers, "Idempotency-Key": "review-team-create-002"},
        json={"name": "核心证据复核组"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EVIDENCE_REVIEW_TEAM_NAME_CONFLICT"

    team_id = team["team_id"]
    member = client.put(
        f"/api/v1/projects/project_1/evidence-review-teams/{team_id}/members/reviewer-2/secondary",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "review-admin",
        },
        json={
            "display_name": "复核员二号",
            "priority": 10,
            "max_active_assignments": 3,
            "receives_escalations": True,
        },
    )
    assert member.status_code == 200
    member_data = member.json()["data"]["teams"][0]["members"][0]
    assert member_data["membership_source"] == "manual"
    assert member_data["external_membership_verified"] is False
    assert member_data["version"] == 1

    routed = client.put(
        "/api/v1/projects/project_1/evidence-review-routes/secondary",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "review-admin",
        },
        json={"team_id": team_id},
    )
    assert routed.status_code == 200
    validate(routed.json())
    data = routed.json()["data"]
    assert data["routing_mode"] == "blocked"
    assert data["routes"][0]["eligible_member_count"] == 1
    assert data["routes"][0]["escalation_recipient_count"] == 1
    assert data["routes"][0]["routing_ready"] is True
    assert data["external_sync_state"] == "not_configured"

    adjudicator_member = client.put(
        f"/api/v1/projects/project_1/evidence-review-teams/{team_id}/members/reviewer-3/adjudicator",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "review-admin",
        },
        json={
            "display_name": "裁决员三号",
            "max_active_assignments": 2,
            "receives_escalations": True,
        },
    )
    assert adjudicator_member.status_code == 200
    adjudicator_route = client.put(
        "/api/v1/projects/project_1/evidence-review-routes/adjudicator",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "review-admin",
        },
        json={"team_id": team_id},
    )
    assert adjudicator_route.status_code == 200
    assert adjudicator_route.json()["data"]["routing_mode"] == "team_routed"
    assert all(
        route["routing_ready"]
        for route in adjudicator_route.json()["data"]["routes"]
    )

    stale = client.put(
        "/api/v1/projects/project_1/evidence-review-routes/secondary",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "review-admin",
        },
        json={"team_id": team_id, "expected_version": 99},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "EVIDENCE_REVIEW_ROUTING_VERSION_CONFLICT"


def test_route_with_empty_team_blocks_instead_of_claiming_ready(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/projects/project_1/evidence-review-teams",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "review-admin",
            "Idempotency-Key": "review-empty-team-001",
        },
        json={"name": "空团队"},
    ).json()["data"]
    routed = client.put(
        "/api/v1/projects/project_1/evidence-review-routes/adjudicator",
        headers={
            "tenant-id": "tenant_1",
            "X-AIRank-User-Id": "review-admin",
        },
        json={"team_id": created["teams"][0]["team_id"]},
    )
    assert routed.status_code == 200
    assert routed.json()["data"]["routing_mode"] == "blocked"
    assert routed.json()["data"]["routes"][0]["routing_ready"] is False


def test_role_eligibility_fails_closed_and_ignores_expired_capacity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    as_of = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE airank_evidence_review_teams (id TEXT PRIMARY KEY, tenant_id TEXT, status TEXT)"))
        conn.execute(text("CREATE TABLE airank_evidence_review_routes (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, reviewer_role TEXT, team_id TEXT, status TEXT, version INTEGER)"))
        conn.execute(text("CREATE TABLE airank_evidence_review_team_members (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, team_id TEXT, yudao_user_id TEXT, reviewer_role TEXT, status TEXT, max_active_assignments INTEGER)"))
        conn.execute(text("CREATE TABLE airank_evidence_review_assignments (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, reviewer_role TEXT, assigned_to TEXT, status TEXT, lease_expires_at DATETIME)"))
        conn.execute(text("INSERT INTO airank_evidence_review_teams VALUES ('team_1', 'tenant_1', 'active')"))
        conn.execute(text("INSERT INTO airank_evidence_review_routes VALUES ('route_1', 'tenant_1', 'project_1', 'secondary', 'team_1', 'active', 1)"))
        conn.execute(text("INSERT INTO airank_evidence_review_team_members VALUES ('member_1', 'tenant_1', 'project_1', 'team_1', 'reviewer-1', 'secondary', 'active', 1)"))
        conn.execute(
            text("INSERT INTO airank_evidence_review_assignments VALUES ('assignment_1', 'tenant_1', 'project_1', 'secondary', 'reviewer-1', 'active', :expires)"),
            {"expires": as_of - timedelta(minutes=1)},
        )

        expired = reviewer_routing_routes.resolve_actor_role_eligibility(
            conn, "tenant_1", "project_1", "reviewer-1", "secondary", as_of=as_of
        )
        assert expired.allowed is True
        assert expired.active_assignment_count == 0
        assert expired.at_capacity is False

        conn.execute(
            text("UPDATE airank_evidence_review_assignments SET lease_expires_at=:expires"),
            {"expires": as_of + timedelta(minutes=1)},
        )
        active = reviewer_routing_routes.resolve_actor_role_eligibility(
            conn, "tenant_1", "project_1", "reviewer-1", "secondary", as_of=as_of
        )
        assert active.active_assignment_count == 1
        assert active.at_capacity is True

        missing_role = reviewer_routing_routes.resolve_actor_role_eligibility(
            conn, "tenant_1", "project_1", "reviewer-1", "adjudicator", as_of=as_of
        )
        assert missing_role.allowed is False
        assert missing_role.reason == "role_unconfigured"


def test_reviewer_routing_mutations_require_admin_permission_when_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    with pytest.raises(StarletteHTTPException) as forbidden:
        reviewer_routing_routes.require_review_admin("airank:review:read")
    assert forbidden.value.status_code == 403
    assert forbidden.value.detail["code"] == "AUTH_PERMISSION_FORBIDDEN"

    reviewer_routing_routes.require_review_admin("airank:review:admin")
    reviewer_routing_routes.require_review_admin("airank:review:*")

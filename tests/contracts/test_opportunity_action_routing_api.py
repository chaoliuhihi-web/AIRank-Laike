from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text

from apps.api import opportunity_routing_routes
from apps.api.main import app
from apps.api.opportunity_routing_routes import (
    OpportunityActionRouteData,
    OpportunityActionRoutingData,
    OpportunityActionTeamData,
    OpportunityActionTeamMemberData,
    ROUTING_CONTRACT_VERSION,
    resolve_action_claim_route,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
NOW = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
TEAM_ID = "opportunity_action_team_" + "a" * 20


def routing_data(*, replay: bool = False) -> OpportunityActionRoutingData:
    member = OpportunityActionTeamMemberData(
        member_id="opportunity_action_member_" + "b" * 20,
        user_id="routed-user",
        display_name="交付负责人",
        priority=100,
        max_active_actions=2,
        active_action_count=1,
        at_capacity=False,
        receives_escalations=True,
        status="active",
        membership_source="manual",
        external_membership_verified=False,
        version=1,
        updated_at=NOW,
    )
    team = OpportunityActionTeamData(
        team_id=TEAM_ID,
        name="GEO 交付组",
        status="active",
        external_source="manual",
        external_group_id=None,
        external_sync_state="not_configured",
        version=1,
        member_count=1,
        members=[member],
        created_at=NOW,
        updated_at=NOW,
    )
    route = OpportunityActionRouteData(
        route_id="opportunity_action_route_" + "c" * 20,
        source_kind="brand_visibility",
        team_id=TEAM_ID,
        team_name="GEO 交付组",
        routing_strategy="manual_claim",
        status="active",
        version=1,
        eligible_member_count=1,
        escalation_recipient_count=1,
        routing_ready=True,
        updated_at=NOW,
    )
    return OpportunityActionRoutingData(
        project_id="project_action",
        contract_version=ROUTING_CONTRACT_VERSION,
        routing_mode="blocked",
        teams=[team],
        routes=[route],
        missing_source_kinds=[
            "citation_support",
            "fact_governance",
            "page_extractability",
        ],
        known_limitations=["manual_membership_not_externally_verified"],
        idempotent_replay=replay,
    )


class FakeRoutingRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_routing(self, tenant_id, project_id, *, idempotent_replay=False):  # noqa: ANN001
        self.calls.append(("get", project_id))
        return routing_data(replay=idempotent_replay)

    def create_team(self, tenant_id, project_id, payload, idempotency_key, actor):  # noqa: ANN001
        assert actor == "trusted-admin"
        assert idempotency_key == "routing-team-key"
        self.calls.append(("create", payload.name))
        return routing_data()

    def upsert_member(self, tenant_id, project_id, team_id, user_id, payload, actor):  # noqa: ANN001
        assert actor == "trusted-admin"
        self.calls.append(("member", user_id))
        return routing_data()

    def put_route(self, tenant_id, project_id, source_kind, payload, actor):  # noqa: ANN001
        assert actor == "trusted-admin"
        self.calls.append(("route", source_kind))
        return routing_data()


def schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def headers() -> dict[str, str]:
    return {
        "tenant-id": "tenant_action",
        "X-AIRank-User-Id": "trusted-admin",
        "X-AIRank-Permissions": "airank:opportunity:admin",
    }


def test_routing_api_is_admin_gated_and_contract_backed(monkeypatch) -> None:  # noqa: ANN001
    repository = FakeRoutingRepository()
    monkeypatch.setattr(
        opportunity_routing_routes,
        "OPPORTUNITY_ACTION_ROUTING_REPOSITORY",
        repository,
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/projects/project_action/opportunity-action-teams",
        headers={**headers(), "Idempotency-Key": "routing-team-key"},
        json={"name": "GEO 交付组"},
    )
    member = client.put(
        f"/api/v1/projects/project_action/opportunity-action-teams/{TEAM_ID}/members/routed-user",
        headers=headers(),
        json={"max_active_actions": 2},
    )
    route = client.put(
        "/api/v1/projects/project_action/opportunity-action-routes/brand_visibility",
        headers=headers(),
        json={"team_id": TEAM_ID},
    )
    listed = client.get(
        "/api/v1/projects/project_action/opportunity-action-routing",
        headers=headers(),
    )
    assert [created.status_code, member.status_code, route.status_code, listed.status_code] == [201, 200, 200, 200]
    assert repository.calls == [
        ("create", "GEO 交付组"),
        ("member", "routed-user"),
        ("route", "brand_visibility"),
        ("get", "project_action"),
    ]
    Draft202012Validator(
        schema("opportunity_action_routing_response.schema.json"),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    ).validate(listed.json())


def test_routing_request_schemas_are_strict() -> None:
    cases = {
        "opportunity_action_team_create_request.schema.json": {"name": "GEO 交付组"},
        "opportunity_action_member_upsert_request.schema.json": {
            "max_active_actions": 5,
            "receives_escalations": True,
        },
        "opportunity_action_route_put_request.schema.json": {"team_id": TEAM_ID},
    }
    for name, value in cases.items():
        loaded = schema(name)
        Draft202012Validator.check_schema(loaded)
        Draft202012Validator(loaded).validate(value)


def test_claim_route_enforces_membership_and_active_capacity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE airank_opportunity_action_routes (tenant_id TEXT, project_id TEXT, source_kind TEXT, team_id TEXT, status TEXT, version INTEGER)"))
        conn.execute(text("CREATE TABLE airank_opportunity_action_teams (id TEXT, tenant_id TEXT, status TEXT, external_sync_state TEXT)"))
        conn.execute(text("CREATE TABLE airank_opportunity_action_team_members (id TEXT, tenant_id TEXT, project_id TEXT, team_id TEXT, user_id TEXT, status TEXT, receives_escalations INTEGER, max_active_actions INTEGER, version INTEGER, external_membership_verified INTEGER)"))
        conn.execute(text("CREATE TABLE airank_opportunity_actions (id TEXT, tenant_id TEXT, project_id TEXT, assigned_to TEXT, status TEXT)"))
        conn.execute(text("INSERT INTO airank_opportunity_action_teams VALUES (:id, 'tenant_action', 'active', 'not_configured')"), {"id": TEAM_ID})
        conn.execute(text("INSERT INTO airank_opportunity_action_routes VALUES ('tenant_action', 'project_action', 'brand_visibility', :team_id, 'active', 1)"), {"team_id": TEAM_ID})
        conn.execute(text("INSERT INTO airank_opportunity_action_team_members VALUES ('member-capacity', 'tenant_action', 'project_action', :team_id, 'routed-user', 'active', 1, 1, 1, 0)"), {"team_id": TEAM_ID})
        conn.execute(text("INSERT INTO airank_opportunity_actions VALUES ('action-existing', 'tenant_action', 'project_action', 'routed-user', 'in_progress')"))
        forbidden = resolve_action_claim_route(conn, "sqlite", "tenant_action", "project_action", "brand_visibility", "other-user")
        full = resolve_action_claim_route(conn, "sqlite", "tenant_action", "project_action", "brand_visibility", "routed-user")
        excluding_current = resolve_action_claim_route(conn, "sqlite", "tenant_action", "project_action", "brand_visibility", "routed-user", action_id="action-existing")
    assert forbidden.routing_state == "blocked"
    assert forbidden.reason == "actor_is_not_active_team_member"
    assert full.at_capacity is True
    assert full.reason == "member_capacity_reached"
    assert excluding_current.routing_state == "team_routed"
    assert excluding_current.at_capacity is False

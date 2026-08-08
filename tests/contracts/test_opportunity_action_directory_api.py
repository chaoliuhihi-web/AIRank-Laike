from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text

from airank_xinghe_adapter import YudaoReviewer, YudaoReviewerDirectorySnapshot
from apps.api import opportunity_directory_routes, opportunity_routing_routes
from apps.api.main import app
from apps.api.opportunity_directory_routes import (
    DIRECTORY_SYNC_CONTRACT_VERSION,
    OpportunityActionDirectoryBindingData,
    OpportunityActionDirectoryData,
    OpportunityActionDirectorySyncRunData,
    MySQLOpportunityActionDirectoryRepository,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
NOW = datetime(2026, 8, 9, 11, 0, tzinfo=timezone.utc)
TEAM_ID = "opportunity_action_team_" + "a" * 20
BINDING_ID = "opportunity_action_sync_binding_" + "b" * 20
RUN_ID = "opportunity_action_sync_run_" + "c" * 20


def directory_data(*, replay: bool = False) -> OpportunityActionDirectoryData:
    return OpportunityActionDirectoryData(
        project_id="project_action",
        contract_version=DIRECTORY_SYNC_CONTRACT_VERSION,
        bindings=[
            OpportunityActionDirectoryBindingData(
                binding_id=BINDING_ID,
                team_id=TEAM_ID,
                team_name="GEO 交付组",
                external_source="yudao",
                external_group_id="42",
                status="active",
                sync_enabled=True,
                sync_interval_minutes=60,
                default_priority=100,
                default_max_active_actions=5,
                default_receives_escalations=True,
                last_sync_state="verified",
                last_sync_run_id=RUN_ID,
                last_synced_at=NOW,
                next_sync_at=NOW,
                last_error_code=None,
                version=1,
                updated_at=NOW,
            )
        ],
        recent_sync_runs=[
            OpportunityActionDirectorySyncRunData(
                run_id=RUN_ID,
                binding_id=BINDING_ID,
                binding_version=1,
                team_id=TEAM_ID,
                external_group_id="42",
                status="succeeded",
                endpoint_host="yudao.example.com",
                response_sha256="d" * 64,
                discovered_member_count=2,
                active_member_count=1,
                created_member_count=1,
                updated_member_count=0,
                unchanged_member_count=0,
                disabled_member_count=0,
                manual_conflict_count=1,
                error_code=None,
                retryable=False,
                started_at=NOW,
                finished_at=NOW,
                idempotent_replay=replay,
            )
        ],
        configured_team_count=1,
        verified_team_count=1,
        known_limitations=[
            "directory_credentials_are_runtime_only",
            "manual_members_are_never_externally_verified",
        ],
    )


class FakeDirectoryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_state(self, tenant_id, project_id, *, replay_run_id=None):  # noqa: ANN001
        self.calls.append(("get", project_id))
        return directory_data(replay=replay_run_id == RUN_ID)

    def put_binding(self, tenant_id, project_id, team_id, payload, actor, trace_id):  # noqa: ANN001
        assert tenant_id == "tenant_action"
        assert actor == "trusted-admin"
        assert payload.external_group_id == "42"
        self.calls.append(("put", team_id))
        return directory_data()

    def run_sync(self, tenant_id, project_id, team_id, idempotency_key, actor, trace_id, client):  # noqa: ANN001
        assert idempotency_key == "directory-run-key"
        assert actor == "trusted-admin"
        self.calls.append(("run", team_id))
        return directory_data()


def headers() -> dict[str, str]:
    return {
        "tenant-id": "tenant_action",
        "X-AIRank-User-Id": "trusted-admin",
        "X-AIRank-Permissions": "airank:opportunity:admin",
    }


def test_directory_api_is_admin_gated_and_contract_backed(monkeypatch) -> None:  # noqa: ANN001
    repository = FakeDirectoryRepository()
    monkeypatch.setattr(
        opportunity_directory_routes,
        "OPPORTUNITY_ACTION_DIRECTORY_REPOSITORY",
        repository,
    )
    monkeypatch.setattr(
        opportunity_routing_routes, "auth_enforcement_required", lambda: True
    )
    client = TestClient(app)
    saved = client.put(
        f"/api/v1/projects/project_action/opportunity-action-teams/{TEAM_ID}/sync-binding",
        headers=headers(),
        json={"external_group_id": "42"},
    )
    run = client.post(
        f"/api/v1/projects/project_action/opportunity-action-teams/{TEAM_ID}/sync-runs",
        headers={**headers(), "Idempotency-Key": "directory-run-key"},
    )
    listed = client.get(
        "/api/v1/projects/project_action/opportunity-action-directory-sync",
        headers=headers(),
    )
    forbidden = client.put(
        f"/api/v1/projects/project_action/opportunity-action-teams/{TEAM_ID}/sync-binding",
        headers={"tenant-id": "tenant_action", "X-AIRank-User-Id": "trusted-admin"},
        json={"external_group_id": "42"},
    )
    assert [saved.status_code, run.status_code, listed.status_code] == [200, 200, 200]
    assert forbidden.status_code == 403
    assert repository.calls == [("put", TEAM_ID), ("run", TEAM_ID), ("get", "project_action")]
    response_schema = json.loads(
        (CONTRACTS / "opportunity_action_directory_response.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(
        response_schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    ).validate(listed.json())


def test_directory_binding_request_schema_rejects_unknown_fields() -> None:
    request_schema = json.loads(
        (
            CONTRACTS
            / "opportunity_action_directory_binding_put_request.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator(request_schema).validate(
        {
            "external_group_id": "42",
            "sync_enabled": True,
            "sync_interval_minutes": 60,
            "default_max_active_actions": 5,
        }
    )
    client = TestClient(app)
    blank = client.put(
        f"/api/v1/projects/project_action/opportunity-action-teams/{TEAM_ID}/sync-binding",
        headers=headers(),
        json={"external_group_id": "   "},
    )
    assert blank.status_code == 422


def test_directory_snapshot_never_overwrites_manual_members_and_is_version_stable() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE airank_opportunity_action_team_members (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
              team_id TEXT NOT NULL, user_id TEXT NOT NULL, display_name TEXT,
              priority INTEGER NOT NULL, max_active_actions INTEGER NOT NULL,
              receives_escalations INTEGER NOT NULL, status TEXT NOT NULL,
              membership_source TEXT NOT NULL, external_membership_verified INTEGER NOT NULL,
              version INTEGER NOT NULL, created_by TEXT, updated_by TEXT,
              created_at DATETIME, updated_at DATETIME
            )
        """))
        for row in (
            ("manual", "manual-user", "Manual Owner", 7, "manual", 0, "active"),
            ("same", "same-user", "Same User", 2, "yudao", 1, "active"),
            ("stale", "stale-user", "Stale User", 3, "yudao", 1, "active"),
        ):
            conn.execute(
                text("""
                    INSERT INTO airank_opportunity_action_team_members (
                      id, tenant_id, project_id, team_id, user_id, display_name,
                      priority, max_active_actions, receives_escalations, status,
                      membership_source, external_membership_verified, version,
                      created_by, updated_by, created_at, updated_at
                    ) VALUES (
                      :id, 'tenant_action', 'project_action', :team_id, :user_id,
                      :display_name, 100, 5, 1, :status, :source, :verified,
                      :version, 'seed', 'seed', :at, :at
                    )
                """),
                {
                    "id": row[0],
                    "team_id": TEAM_ID,
                    "user_id": row[1],
                    "display_name": row[2],
                    "version": row[3],
                    "source": row[4],
                    "verified": row[5],
                    "status": row[6],
                    "at": NOW,
                },
            )
        snapshot = YudaoReviewerDirectorySnapshot(
            department_id="42",
            department_name="GEO 交付组",
            members=(
                YudaoReviewer("manual-user", "manual", "External Name", "42", True),
                YudaoReviewer("new-user", "new", "New User", "42", True),
                YudaoReviewer("same-user", "same", "Same User", "42", True),
            ),
            response_sha256="d" * 64,
            endpoint_host="yudao.example.com",
        )
        binding = {
            "default_priority": 100,
            "default_max_active_actions": 5,
            "default_receives_escalations": 1,
        }
        first = MySQLOpportunityActionDirectoryRepository._apply_snapshot(
            conn,
            "tenant_action",
            "project_action",
            TEAM_ID,
            binding,
            snapshot,
            "sync-worker",
            NOW,
        )
        second = MySQLOpportunityActionDirectoryRepository._apply_snapshot(
            conn,
            "tenant_action",
            "project_action",
            TEAM_ID,
            binding,
            snapshot,
            "sync-worker",
            NOW,
        )
        rows = {
            row["user_id"]: row
            for row in conn.execute(
                text("SELECT * FROM airank_opportunity_action_team_members")
            ).mappings()
        }

    assert first == {
        "active": 2,
        "created": 1,
        "updated": 0,
        "unchanged": 1,
        "disabled": 1,
        "manual_conflict": 1,
    }
    assert second == {
        "active": 2,
        "created": 0,
        "updated": 0,
        "unchanged": 2,
        "disabled": 0,
        "manual_conflict": 1,
    }
    assert rows["manual-user"]["display_name"] == "Manual Owner"
    assert rows["manual-user"]["version"] == 7
    assert rows["manual-user"]["external_membership_verified"] == 0
    assert rows["same-user"]["version"] == 2
    assert rows["stale-user"]["status"] == "disabled"
    assert rows["stale-user"]["version"] == 4
    assert rows["new-user"]["membership_source"] == "yudao"
    assert rows["new-user"]["external_membership_verified"] == 1

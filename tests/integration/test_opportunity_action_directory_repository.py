from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_xinghe_adapter import YudaoReviewer, YudaoReviewerDirectorySnapshot
from apps.api.opportunity_directory_routes import (
    MySQLOpportunityActionDirectoryRepository,
    OpportunityActionDirectoryBindingPutRequest,
)


NOW = datetime(2026, 8, 9, 13, 0, tzinfo=timezone.utc)
TEAM_ID = "opportunity_action_team_" + "a" * 20


class DirectoryClient:
    @staticmethod
    def fetch_department(department_id: str) -> YudaoReviewerDirectorySnapshot:
        assert department_id == "42"
        return YudaoReviewerDirectorySnapshot(
            department_id="42",
            department_name="GEO 交付组",
            members=(
                YudaoReviewer("directory-user", "delivery", "交付成员", "42", True),
                YudaoReviewer("manual-user", "manual", "外部同名成员", "42", True),
            ),
            response_sha256="d" * 64,
            endpoint_host="yudao.example.com",
        )


def build_repository() -> MySQLOpportunityActionDirectoryRepository:
    repository = MySQLOpportunityActionDirectoryRepository(
        "sqlite+pysqlite:///:memory:"
    )
    with repository.engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE airank_projects (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_opportunity_action_teams (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
              name TEXT NOT NULL, status TEXT NOT NULL, external_source TEXT NOT NULL,
              external_group_id TEXT, external_sync_state TEXT NOT NULL,
              version INTEGER NOT NULL, updated_by TEXT, updated_at DATETIME
            )
        """))
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
        conn.execute(text("""
            CREATE TABLE airank_opportunity_action_team_sync_bindings (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
              team_id TEXT NOT NULL, external_source TEXT NOT NULL,
              external_group_id TEXT NOT NULL, status TEXT NOT NULL,
              sync_enabled INTEGER NOT NULL, sync_interval_minutes INTEGER NOT NULL,
              default_priority INTEGER NOT NULL, default_max_active_actions INTEGER NOT NULL,
              default_receives_escalations INTEGER NOT NULL, last_sync_state TEXT NOT NULL,
              last_sync_run_id TEXT, last_synced_at DATETIME, next_sync_at DATETIME,
              last_error_code TEXT, request_sha256 TEXT NOT NULL, version INTEGER NOT NULL,
              created_by TEXT NOT NULL, updated_by TEXT NOT NULL,
              created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
              UNIQUE (tenant_id, project_id, team_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_opportunity_action_team_sync_runs (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
              team_id TEXT NOT NULL, binding_id TEXT NOT NULL, binding_version INTEGER NOT NULL,
              external_group_id TEXT NOT NULL, status TEXT NOT NULL,
              idempotency_key TEXT NOT NULL, request_sha256 TEXT NOT NULL,
              requested_by TEXT NOT NULL, trace_id TEXT NOT NULL, endpoint_host TEXT,
              response_sha256 TEXT, discovered_member_count INTEGER NOT NULL,
              active_member_count INTEGER NOT NULL, created_member_count INTEGER NOT NULL,
              updated_member_count INTEGER NOT NULL, unchanged_member_count INTEGER NOT NULL,
              disabled_member_count INTEGER NOT NULL, manual_conflict_count INTEGER NOT NULL,
              error_code TEXT, retryable INTEGER NOT NULL, started_at DATETIME NOT NULL,
              finished_at DATETIME, created_at DATETIME NOT NULL,
              UNIQUE (tenant_id, binding_id, idempotency_key)
            )
        """))
        conn.execute(text("""
            CREATE TABLE airank_audit_events (
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT,
              actor_user_id TEXT, event_type TEXT NOT NULL, entity_type TEXT,
              entity_id TEXT, payload_json TEXT, created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("INSERT INTO airank_projects VALUES ('project_1', 'tenant_1', NULL)"))
        conn.execute(
            text("""
                INSERT INTO airank_opportunity_action_teams (
                  id, tenant_id, project_id, name, status, external_source,
                  external_group_id, external_sync_state, version, updated_by, updated_at
                ) VALUES (
                  :team_id, 'tenant_1', 'project_1', 'GEO 交付组', 'active',
                  'manual', NULL, 'not_configured', 1, 'seed', :at
                )
            """),
            {"team_id": TEAM_ID, "at": NOW},
        )
        conn.execute(
            text("""
                INSERT INTO airank_opportunity_action_team_members (
                  id, tenant_id, project_id, team_id, user_id, display_name,
                  priority, max_active_actions, receives_escalations, status,
                  membership_source, external_membership_verified, version,
                  created_by, updated_by, created_at, updated_at
                ) VALUES (
                  'manual-member', 'tenant_1', 'project_1', :team_id,
                  'manual-user', '人工负责人', 80, 3, 1, 'active', 'manual', 0,
                  4, 'seed', 'seed', :at, :at
                )
            """),
            {"team_id": TEAM_ID, "at": NOW},
        )
    return repository


def test_repository_binding_sync_replay_and_manual_member_provenance() -> None:
    repository = build_repository()
    pending = repository.put_binding(
        "tenant_1",
        "project_1",
        TEAM_ID,
        OpportunityActionDirectoryBindingPutRequest(external_group_id="42"),
        "admin-user",
        "trace-binding",
    )
    assert pending.bindings[0].last_sync_state == "pending"
    assert pending.bindings[0].version == 1

    synced = repository.run_sync(
        "tenant_1",
        "project_1",
        TEAM_ID,
        "directory-run-idempotency",
        "sync-worker",
        "trace-run",
        DirectoryClient(),  # type: ignore[arg-type]
    )
    replayed = repository.run_sync(
        "tenant_1",
        "project_1",
        TEAM_ID,
        "directory-run-idempotency",
        "sync-worker",
        "trace-replay",
        DirectoryClient(),  # type: ignore[arg-type]
    )

    run = synced.recent_sync_runs[0]
    assert run.status == "succeeded"
    assert run.discovered_member_count == 2
    assert run.active_member_count == 1
    assert run.created_member_count == 1
    assert run.manual_conflict_count == 1
    assert replayed.recent_sync_runs[0].idempotent_replay is True
    with repository.engine.begin() as conn:
        members = {
            row["user_id"]: row
            for row in conn.execute(
                text("SELECT * FROM airank_opportunity_action_team_members")
            ).mappings()
        }
        team = conn.execute(
            text("SELECT * FROM airank_opportunity_action_teams")
        ).mappings().one()
        events = conn.execute(
            text("SELECT event_type FROM airank_audit_events ORDER BY created_at, id")
        ).scalars().all()
    assert members["manual-user"]["display_name"] == "人工负责人"
    assert members["manual-user"]["membership_source"] == "manual"
    assert members["manual-user"]["external_membership_verified"] == 0
    assert members["manual-user"]["version"] == 4
    assert members["directory-user"]["external_membership_verified"] == 1
    assert team["external_sync_state"] == "verified"
    assert set(events) == {
        "opportunity_action.directory_binding_saved",
        "opportunity_action.directory_sync_succeeded",
    }


def test_repository_rejects_snapshot_when_binding_changes_during_fetch() -> None:
    repository = build_repository()
    pending = repository.put_binding(
        "tenant_1",
        "project_1",
        TEAM_ID,
        OpportunityActionDirectoryBindingPutRequest(external_group_id="42"),
        "admin-user",
        "trace-binding-v1",
    )

    class MutatingClient:
        @staticmethod
        def fetch_department(department_id: str) -> YudaoReviewerDirectorySnapshot:
            repository.put_binding(
                "tenant_1",
                "project_1",
                TEAM_ID,
                OpportunityActionDirectoryBindingPutRequest(
                    external_group_id="99",
                    expected_version=pending.bindings[0].version,
                ),
                "admin-user",
                "trace-binding-v2",
            )
            return DirectoryClient.fetch_department(department_id)

    with pytest.raises(StarletteHTTPException) as captured:
        repository.run_sync(
            "tenant_1",
            "project_1",
            TEAM_ID,
            "directory-binding-changed",
            "sync-worker",
            "trace-run-binding-changed",
            MutatingClient(),  # type: ignore[arg-type]
        )

    assert captured.value.status_code == 409
    assert captured.value.detail["code"] == "OPPORTUNITY_ACTION_DIRECTORY_BINDING_CHANGED"
    state = repository.get_state("tenant_1", "project_1")
    assert state.bindings[0].external_group_id == "99"
    assert state.bindings[0].last_sync_state == "pending"
    assert state.recent_sync_runs[0].status == "failed"
    assert state.recent_sync_runs[0].error_code == "OPPORTUNITY_ACTION_DIRECTORY_BINDING_CHANGED"
    with repository.engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT COUNT(*) FROM airank_opportunity_action_team_members "
                "WHERE tenant_id='tenant_1' AND membership_source='yudao'"
            )
        ).scalar_one() == 0

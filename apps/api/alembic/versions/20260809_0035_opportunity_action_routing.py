"""add opportunity action teams, routes, capacity, and escalation snapshots

Revision ID: 20260809_0035
Revises: 20260809_0034
Create Date: 2026-08-09 14:50:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0035"
down_revision = "20260809_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_teams (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          name VARCHAR(160) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          external_source VARCHAR(32) NOT NULL COMMENT 'manual/yudao',
          external_group_id VARCHAR(128) NULL,
          external_sync_state VARCHAR(32) NOT NULL
            COMMENT 'not_configured/pending/verified/stale/failed',
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_team_name
            (tenant_id, project_id, name),
          UNIQUE KEY uk_airank_opportunity_action_team_idempotency
            (tenant_id, project_id, idempotency_key),
          KEY idx_airank_opportunity_action_team_project
            (tenant_id, project_id, status, updated_at),
          CONSTRAINT fk_airank_opportunity_action_team_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_team_members (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          team_id VARCHAR(64) NOT NULL,
          user_id VARCHAR(128) NOT NULL,
          display_name VARCHAR(160) NULL,
          priority INT NOT NULL DEFAULT 100,
          max_active_actions INT NOT NULL DEFAULT 5,
          receives_escalations TINYINT(1) NOT NULL DEFAULT 1,
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          membership_source VARCHAR(32) NOT NULL COMMENT 'manual/yudao',
          external_membership_verified TINYINT(1) NOT NULL DEFAULT 0,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_team_member
            (tenant_id, team_id, user_id),
          KEY idx_airank_opportunity_action_member_route
            (tenant_id, project_id, team_id, status, priority),
          KEY idx_airank_opportunity_action_member_user
            (tenant_id, project_id, user_id, status),
          CONSTRAINT fk_airank_opportunity_action_member_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_member_team
            FOREIGN KEY (team_id) REFERENCES airank_opportunity_action_teams (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_routes (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          source_kind VARCHAR(48) NOT NULL,
          team_id VARCHAR(64) NOT NULL,
          routing_strategy VARCHAR(32) NOT NULL COMMENT 'manual_claim',
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_route_kind
            (tenant_id, project_id, source_kind),
          KEY idx_airank_opportunity_action_route_team
            (tenant_id, project_id, team_id, status),
          CONSTRAINT fk_airank_opportunity_action_route_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_route_team
            FOREIGN KEY (team_id) REFERENCES airank_opportunity_action_teams (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        ALTER TABLE airank_opportunity_actions
          ADD COLUMN routing_state VARCHAR(32) NOT NULL DEFAULT 'unrestricted_legacy'
            COMMENT 'unrestricted_legacy/team_routed/blocked' AFTER latest_evidence_sha256,
          ADD COLUMN routing_team_id VARCHAR(64) NULL AFTER routing_state,
          ADD COLUMN routing_route_version INT NULL AFTER routing_team_id,
          ADD COLUMN routing_member_id VARCHAR(64) NULL AFTER routing_route_version,
          ADD COLUMN routing_member_version INT NULL AFTER routing_member_id,
          ADD COLUMN external_membership_verified TINYINT(1) NOT NULL DEFAULT 0
            AFTER routing_member_version,
          ADD KEY idx_airank_opportunity_action_routing
            (tenant_id, project_id, routing_state, routing_team_id),
          ADD CONSTRAINT fk_airank_opportunity_action_routing_team
            FOREIGN KEY (routing_team_id) REFERENCES airank_opportunity_action_teams (id),
          ADD CONSTRAINT fk_airank_opportunity_action_routing_member
            FOREIGN KEY (routing_member_id) REFERENCES airank_opportunity_action_team_members (id)
        """
    )


def downgrade() -> None:
    # Routing configuration, assignment snapshots, and SLA events are delivery
    # audit evidence. Export and reconcile them before a deliberate rollback.
    pass

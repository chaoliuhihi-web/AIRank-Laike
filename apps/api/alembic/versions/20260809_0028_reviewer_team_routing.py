"""add project reviewer teams, memberships, and role routing

Revision ID: 20260809_0028
Revises: 20260809_0027
Create Date: 2026-08-09 01:40:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0028"
down_revision = "20260809_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_review_teams (
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
          UNIQUE KEY uk_airank_review_team_name (tenant_id, project_id, name),
          UNIQUE KEY uk_airank_review_team_idempotency
            (tenant_id, project_id, idempotency_key),
          KEY idx_airank_review_team_project
            (tenant_id, project_id, status, updated_at),
          KEY idx_airank_review_team_external
            (tenant_id, external_source, external_group_id),
          CONSTRAINT fk_airank_review_team_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_review_team_members (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          team_id VARCHAR(64) NOT NULL,
          yudao_user_id VARCHAR(128) NOT NULL,
          display_name VARCHAR(160) NULL,
          reviewer_role VARCHAR(32) NOT NULL COMMENT 'secondary/adjudicator',
          priority INT NOT NULL DEFAULT 100,
          max_active_assignments INT NOT NULL DEFAULT 5,
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
          UNIQUE KEY uk_airank_review_team_member
            (tenant_id, team_id, yudao_user_id, reviewer_role),
          KEY idx_airank_review_member_route
            (tenant_id, project_id, reviewer_role, status, priority),
          KEY idx_airank_review_member_user
            (tenant_id, project_id, yudao_user_id, status),
          CONSTRAINT fk_airank_review_member_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_review_member_team
            FOREIGN KEY (team_id) REFERENCES airank_evidence_review_teams (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_review_routes (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          reviewer_role VARCHAR(32) NOT NULL COMMENT 'secondary/adjudicator',
          team_id VARCHAR(64) NOT NULL,
          routing_strategy VARCHAR(32) NOT NULL COMMENT 'manual_claim',
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_review_route_role
            (tenant_id, project_id, reviewer_role),
          KEY idx_airank_review_route_team
            (tenant_id, project_id, team_id, status),
          CONSTRAINT fk_airank_review_route_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_review_route_team
            FOREIGN KEY (team_id) REFERENCES airank_evidence_review_teams (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Routing configuration is security-relevant operational evidence. A
    # deliberate rollback must export it first; automatic downgrade preserves it.
    pass

"""add governed Yudao opportunity-action directory synchronization

Revision ID: 20260809_0037
Revises: 20260809_0036
Create Date: 2026-08-09 18:40:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0037"
down_revision = "20260809_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_team_sync_bindings (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          team_id VARCHAR(64) NOT NULL,
          external_source VARCHAR(32) NOT NULL COMMENT 'yudao',
          external_group_id VARCHAR(128) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          sync_enabled TINYINT(1) NOT NULL DEFAULT 1,
          sync_interval_minutes INT NOT NULL DEFAULT 60,
          default_priority INT NOT NULL DEFAULT 100,
          default_max_active_actions INT NOT NULL DEFAULT 5,
          default_receives_escalations TINYINT(1) NOT NULL DEFAULT 1,
          last_sync_state VARCHAR(32) NOT NULL
            COMMENT 'not_configured/pending/verified/stale/failed',
          last_sync_run_id VARCHAR(64) NULL,
          last_synced_at DATETIME(3) NULL,
          next_sync_at DATETIME(3) NULL,
          last_error_code VARCHAR(128) NULL,
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_sync_team
            (tenant_id, project_id, team_id),
          KEY idx_airank_opportunity_action_sync_due
            (status, sync_enabled, next_sync_at, tenant_id, project_id),
          KEY idx_airank_opportunity_action_sync_group
            (tenant_id, external_source, external_group_id),
          CONSTRAINT fk_airank_opportunity_action_sync_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_sync_team
            FOREIGN KEY (team_id) REFERENCES airank_opportunity_action_teams (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_team_sync_runs (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          team_id VARCHAR(64) NOT NULL,
          binding_id VARCHAR(64) NOT NULL,
          binding_version INT NOT NULL,
          external_group_id VARCHAR(128) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'running/succeeded/failed',
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          requested_by VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          endpoint_host VARCHAR(255) NULL,
          response_sha256 CHAR(64) NULL,
          discovered_member_count INT NOT NULL DEFAULT 0,
          active_member_count INT NOT NULL DEFAULT 0,
          created_member_count INT NOT NULL DEFAULT 0,
          updated_member_count INT NOT NULL DEFAULT 0,
          unchanged_member_count INT NOT NULL DEFAULT 0,
          disabled_member_count INT NOT NULL DEFAULT 0,
          manual_conflict_count INT NOT NULL DEFAULT 0,
          error_code VARCHAR(128) NULL,
          retryable TINYINT(1) NOT NULL DEFAULT 0,
          started_at DATETIME(3) NOT NULL,
          finished_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_sync_run_idempotency
            (tenant_id, binding_id, idempotency_key),
          KEY idx_airank_opportunity_action_sync_run_binding
            (tenant_id, binding_id, started_at),
          KEY idx_airank_opportunity_action_sync_run_project
            (tenant_id, project_id, status, started_at),
          CONSTRAINT fk_airank_opportunity_action_sync_run_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_sync_run_team
            FOREIGN KEY (team_id) REFERENCES airank_opportunity_action_teams (id),
          CONSTRAINT fk_airank_opportunity_action_sync_run_binding
            FOREIGN KEY (binding_id)
            REFERENCES airank_opportunity_action_team_sync_bindings (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Directory provenance and failures are delivery-governance evidence. A
    # deliberate rollback must export and reconcile them first.
    pass

"""add governed opportunity execution plans and dependencies

Revision ID: 20260809_0036
Revises: 20260809_0035
Create Date: 2026-08-09 16:10:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0036"
down_revision = "20260809_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_plans (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          action_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'draft/approved',
          estimate_source VARCHAR(32) NOT NULL COMMENT 'human_estimate',
          estimated_effort_hours DECIMAL(10,2) NOT NULL,
          estimated_budget_amount DECIMAL(14,2) NOT NULL,
          currency CHAR(3) NOT NULL,
          planned_start_at DATETIME(3) NULL,
          planned_due_at DATETIME(3) NULL,
          assumptions TEXT NOT NULL,
          outcome_forecast_allowed TINYINT(1) NOT NULL DEFAULT 0,
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_plan
            (tenant_id, project_id, action_id),
          KEY idx_airank_opportunity_action_plan_status
            (tenant_id, project_id, status, planned_due_at),
          CONSTRAINT fk_airank_opportunity_action_plan_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_plan_action
            FOREIGN KEY (action_id) REFERENCES airank_opportunity_actions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_dependencies (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          action_id VARCHAR(64) NOT NULL,
          prerequisite_action_id VARCHAR(64) NOT NULL,
          dependency_type VARCHAR(40) NOT NULL
            COMMENT 'finish_to_start/evidence_prerequisite',
          status VARCHAR(32) NOT NULL COMMENT 'active/waived',
          rationale TEXT NOT NULL,
          waiver_reason TEXT NULL,
          waived_by VARCHAR(128) NULL,
          waived_at DATETIME(3) NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_dependency
            (tenant_id, project_id, action_id, prerequisite_action_id,
             dependency_type),
          UNIQUE KEY uk_airank_opportunity_action_dependency_idempotency
            (tenant_id, project_id, idempotency_key),
          KEY idx_airank_opportunity_action_dependency_action
            (tenant_id, project_id, action_id, status),
          KEY idx_airank_opportunity_action_dependency_prerequisite
            (tenant_id, project_id, prerequisite_action_id, status),
          CONSTRAINT fk_airank_opportunity_action_dependency_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_dependency_action
            FOREIGN KEY (action_id) REFERENCES airank_opportunity_actions (id),
          CONSTRAINT fk_airank_opportunity_action_dependency_prerequisite
            FOREIGN KEY (prerequisite_action_id) REFERENCES airank_opportunity_actions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_plan_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          aggregate_type VARCHAR(32) NOT NULL COMMENT 'plan/dependency',
          aggregate_id VARCHAR(64) NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          aggregate_version INT NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor_user_id VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          payload_json JSON NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_plan_event_version
            (tenant_id, aggregate_type, aggregate_id, aggregate_version),
          KEY idx_airank_opportunity_action_plan_event
            (tenant_id, project_id, aggregate_type, aggregate_id, created_at),
          CONSTRAINT fk_airank_opportunity_action_plan_event_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Human estimates and dependency waivers are customer delivery evidence.
    # Export them before any deliberate rollback.
    pass

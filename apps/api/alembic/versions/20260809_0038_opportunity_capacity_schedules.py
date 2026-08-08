"""add governed opportunity capacity calendars and immutable 30/60/90 schedules

Revision ID: 20260809_0038
Revises: 20260809_0037
Create Date: 2026-08-09 18:20:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0038"
down_revision = "20260809_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_capacity_calendars (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          team_id VARCHAR(64) NOT NULL,
          member_id VARCHAR(64) NOT NULL,
          user_id VARCHAR(128) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          timezone VARCHAR(64) NOT NULL,
          weekly_capacity_hours DECIMAL(7,2) NOT NULL,
          workdays_json JSON NOT NULL,
          assumptions TEXT NOT NULL,
          capacity_source VARCHAR(32) NOT NULL COMMENT 'manual',
          external_calendar_verified TINYINT(1) NOT NULL DEFAULT 0,
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_capacity_member
            (tenant_id, project_id, member_id),
          KEY idx_airank_opportunity_capacity_team
            (tenant_id, project_id, team_id, status),
          CONSTRAINT fk_airank_opportunity_capacity_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_capacity_team
            FOREIGN KEY (team_id) REFERENCES airank_opportunity_action_teams (id),
          CONSTRAINT fk_airank_opportunity_capacity_member
            FOREIGN KEY (member_id) REFERENCES airank_opportunity_action_team_members (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_capacity_exceptions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          calendar_id VARCHAR(64) NOT NULL,
          exception_date DATE NOT NULL,
          available_hours DECIMAL(5,2) NOT NULL,
          reason VARCHAR(1000) NOT NULL,
          exception_source VARCHAR(32) NOT NULL COMMENT 'manual',
          external_calendar_verified TINYINT(1) NOT NULL DEFAULT 0,
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_capacity_exception
            (tenant_id, calendar_id, exception_date),
          KEY idx_airank_opportunity_capacity_exception_project
            (tenant_id, project_id, exception_date),
          CONSTRAINT fk_airank_opportunity_capacity_exception_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_capacity_exception_calendar
            FOREIGN KEY (calendar_id) REFERENCES airank_opportunity_capacity_calendars (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_capacity_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          aggregate_type VARCHAR(32) NOT NULL COMMENT 'calendar/exception',
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
          UNIQUE KEY uk_airank_opportunity_capacity_event_version
            (tenant_id, aggregate_type, aggregate_id, aggregate_version),
          KEY idx_airank_opportunity_capacity_event_project
            (tenant_id, project_id, aggregate_type, aggregate_id, created_at),
          CONSTRAINT fk_airank_opportunity_capacity_event_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_schedule_runs (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          policy_version VARCHAR(64) NOT NULL,
          as_of_date DATE NOT NULL,
          horizon_days INT NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'complete',
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          source_manifest_sha256 CHAR(64) NOT NULL,
          result_sha256 CHAR(64) NOT NULL,
          action_count INT NOT NULL,
          scheduled_count INT NOT NULL,
          blocked_count INT NOT NULL,
          outside_horizon_count INT NOT NULL,
          capacity_conflict_count INT NOT NULL,
          schedule_feasible TINYINT(1) NOT NULL DEFAULT 0,
          outcome_forecast_allowed TINYINT(1) NOT NULL DEFAULT 0,
          windows_json JSON NOT NULL,
          known_limitations_json JSON NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_schedule_idempotency
            (tenant_id, project_id, idempotency_key),
          KEY idx_airank_opportunity_schedule_snapshot
            (tenant_id, project_id, as_of_date, policy_version, source_manifest_sha256),
          KEY idx_airank_opportunity_schedule_project
            (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_opportunity_schedule_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_schedule_items (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          run_id VARCHAR(64) NOT NULL,
          action_id VARCHAR(64) NOT NULL,
          action_version INT NOT NULL,
          plan_id VARCHAR(64) NULL,
          plan_version INT NULL,
          member_id VARCHAR(64) NULL,
          member_version INT NULL,
          calendar_id VARCHAR(64) NULL,
          calendar_version INT NULL,
          window_code VARCHAR(32) NOT NULL
            COMMENT 'day_0_30/day_31_60/day_61_90/outside_horizon/unscheduled',
          schedule_state VARCHAR(40) NOT NULL,
          reason_codes_json JSON NOT NULL,
          planned_start_at DATETIME(3) NULL,
          planned_due_at DATETIME(3) NULL,
          estimated_effort_hours DECIMAL(10,2) NULL,
          scheduled_effort_hours DECIMAL(10,2) NOT NULL,
          peak_daily_utilization DECIMAL(9,4) NULL,
          item_sha256 CHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_schedule_item
            (tenant_id, run_id, action_id),
          KEY idx_airank_opportunity_schedule_item_state
            (tenant_id, project_id, window_code, schedule_state),
          CONSTRAINT fk_airank_opportunity_schedule_item_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_schedule_item_run
            FOREIGN KEY (run_id) REFERENCES airank_opportunity_schedule_runs (id),
          CONSTRAINT fk_airank_opportunity_schedule_item_action
            FOREIGN KEY (action_id) REFERENCES airank_opportunity_actions (id),
          CONSTRAINT fk_airank_opportunity_schedule_item_plan
            FOREIGN KEY (plan_id) REFERENCES airank_opportunity_action_plans (id),
          CONSTRAINT fk_airank_opportunity_schedule_item_member
            FOREIGN KEY (member_id) REFERENCES airank_opportunity_action_team_members (id),
          CONSTRAINT fk_airank_opportunity_schedule_item_calendar
            FOREIGN KEY (calendar_id) REFERENCES airank_opportunity_capacity_calendars (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Capacity calendars, exceptions, and schedule snapshots are delivery audit
    # evidence. Export and reconcile them before a deliberate rollback.
    pass

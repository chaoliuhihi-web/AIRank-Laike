"""add persistent evidence review assignments and SLA events

Revision ID: 20260809_0027
Revises: 20260808_0026
Create Date: 2026-08-09 00:40:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0027"
down_revision = "20260808_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_review_assignments (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          case_id VARCHAR(64) NOT NULL,
          reviewer_role VARCHAR(32) NOT NULL COMMENT 'secondary/adjudicator',
          assigned_to VARCHAR(128) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'active/completed/released/expired',
          action_available_at DATETIME(3) NOT NULL,
          assigned_at DATETIME(3) NOT NULL,
          due_at DATETIME(3) NOT NULL,
          lease_expires_at DATETIME(3) NOT NULL,
          last_heartbeat_at DATETIME(3) NOT NULL,
          completed_at DATETIME(3) NULL,
          released_at DATETIME(3) NULL,
          release_reason VARCHAR(512) NULL,
          version INT NOT NULL DEFAULT 1,
          active_slot VARCHAR(160)
            GENERATED ALWAYS AS (
              CASE WHEN status='active' THEN CONCAT(case_id, ':', reviewer_role) ELSE NULL END
            ) STORED,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_review_assignment_active (tenant_id, active_slot),
          KEY idx_airank_review_assignment_owner
            (tenant_id, project_id, assigned_to, status, lease_expires_at),
          KEY idx_airank_review_assignment_case
            (tenant_id, case_id, reviewer_role, assigned_at),
          KEY idx_airank_review_assignment_sla
            (tenant_id, project_id, status, due_at),
          CONSTRAINT fk_airank_review_assignment_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_review_assignment_case
            FOREIGN KEY (case_id) REFERENCES airank_evidence_review_cases (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_review_assignment_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          case_id VARCHAR(64) NOT NULL,
          assignment_id VARCHAR(64) NOT NULL,
          event_type VARCHAR(32) NOT NULL COMMENT 'claimed/heartbeat/completed/released/expired',
          assignment_version INT NOT NULL,
          actor VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          payload_json JSON NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          KEY idx_airank_review_assignment_event_case
            (tenant_id, case_id, created_at, id),
          KEY idx_airank_review_assignment_event_assignment
            (tenant_id, assignment_id, assignment_version),
          CONSTRAINT fk_airank_review_assignment_event_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_review_assignment_event_case
            FOREIGN KEY (case_id) REFERENCES airank_evidence_review_cases (id),
          CONSTRAINT fk_airank_review_assignment_event_assignment
            FOREIGN KEY (assignment_id) REFERENCES airank_evidence_review_assignments (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Assignment history is operational evidence. Export it before any deliberate
    # destructive rollback; automatic downgrade intentionally preserves it.
    pass

"""add governed fact acquisition tasks for evidence gaps

Revision ID: 20260809_0032
Revises: 20260809_0031
Create Date: 2026-08-09 11:40:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0032"
down_revision = "20260809_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_fact_acquisition_tasks (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          gap_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          gap_contract_version VARCHAR(64) NOT NULL,
          gap_evidence_sha256 CHAR(64) NOT NULL,
          quality_report_sha256 CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'open/in_review/resolved/blocked',
          resolution_state VARCHAR(48) NOT NULL COMMENT 'needs_fact_proposal/needs_fact_review/ready_for_intervention/blocked',
          priority VARCHAR(16) NOT NULL,
          title VARCHAR(255) NOT NULL,
          evidence_requirement TEXT NOT NULL,
          required_authority_policy VARCHAR(64) NOT NULL,
          suggested_fact_type VARCHAR(64) NOT NULL,
          related_question_ids JSON NOT NULL,
          provider VARCHAR(64) NOT NULL,
          collector_surface VARCHAR(32) NOT NULL,
          knowledge_source_ids JSON NOT NULL,
          fact_revision_ids JSON NOT NULL,
          approved_fact_revision_ids JSON NOT NULL,
          creation_idempotency_key VARCHAR(160) NOT NULL,
          creation_request_sha256 CHAR(64) NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          resolved_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_fact_acquisition_gap
            (tenant_id, project_id, gap_id, contract_version),
          KEY idx_airank_fact_acquisition_project
            (tenant_id, project_id, status, priority, updated_at),
          CONSTRAINT fk_airank_fact_acquisition_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_fact_acquisition_gap
            FOREIGN KEY (gap_id) REFERENCES airank_content_gaps (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_fact_acquisition_task_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          task_id VARCHAR(64) NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          from_status VARCHAR(32) NULL,
          to_status VARCHAR(32) NOT NULL,
          task_version INT NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor_user_id VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          payload_json JSON NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_fact_acquisition_event_idempotency
            (tenant_id, task_id, idempotency_key),
          UNIQUE KEY uk_airank_fact_acquisition_event_version
            (tenant_id, task_id, task_version),
          KEY idx_airank_fact_acquisition_event_task
            (tenant_id, project_id, task_id, created_at),
          CONSTRAINT fk_airank_fact_acquisition_event_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_fact_acquisition_event_task
            FOREIGN KEY (task_id) REFERENCES airank_fact_acquisition_tasks (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # These tasks and events are customer-facing provenance. Export and
    # reconcile them explicitly instead of silently dropping the audit chain.
    pass

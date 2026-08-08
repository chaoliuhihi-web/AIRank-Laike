"""add governed opportunity action ownership and verification events

Revision ID: 20260809_0034
Revises: 20260809_0033
Create Date: 2026-08-09 14:15:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0034"
down_revision = "20260809_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_actions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          opportunity_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          source_kind VARCHAR(48) NOT NULL,
          action_type VARCHAR(96) NOT NULL,
          status VARCHAR(40) NOT NULL COMMENT 'open/in_progress/evidence_blocked/verified_not_observed/waived',
          source_snapshot_id VARCHAR(64) NOT NULL,
          source_derivation_run_id VARCHAR(64) NOT NULL,
          source_snapshot_sha256 CHAR(64) NOT NULL,
          source_evidence_sha256 CHAR(64) NOT NULL,
          latest_snapshot_id VARCHAR(64) NOT NULL,
          latest_derivation_run_id VARCHAR(64) NOT NULL,
          latest_snapshot_sha256 CHAR(64) NOT NULL,
          latest_evidence_sha256 CHAR(64) NOT NULL,
          assigned_to VARCHAR(128) NULL,
          assigned_at DATETIME(3) NULL,
          due_at DATETIME(3) NOT NULL,
          action_note TEXT NOT NULL,
          verification_run_id VARCHAR(64) NULL,
          verification_basis_sha256 CHAR(64) NULL,
          closure_reason TEXT NULL,
          effect_claim_allowed TINYINT(1) NOT NULL DEFAULT 0,
          creation_idempotency_key VARCHAR(160) NOT NULL,
          creation_request_sha256 CHAR(64) NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          completed_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_stable
            (tenant_id, project_id, opportunity_id, contract_version),
          KEY idx_airank_opportunity_action_queue
            (tenant_id, project_id, status, due_at),
          KEY idx_airank_opportunity_action_owner
            (tenant_id, assigned_to, status, due_at),
          CONSTRAINT fk_airank_opportunity_action_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_source_snapshot
            FOREIGN KEY (source_snapshot_id) REFERENCES airank_intervention_opportunity_snapshots (id),
          CONSTRAINT fk_airank_opportunity_action_source_run
            FOREIGN KEY (source_derivation_run_id) REFERENCES airank_opportunity_derivation_runs (id),
          CONSTRAINT fk_airank_opportunity_action_latest_snapshot
            FOREIGN KEY (latest_snapshot_id) REFERENCES airank_intervention_opportunity_snapshots (id),
          CONSTRAINT fk_airank_opportunity_action_latest_run
            FOREIGN KEY (latest_derivation_run_id) REFERENCES airank_opportunity_derivation_runs (id),
          CONSTRAINT fk_airank_opportunity_action_verification_run
            FOREIGN KEY (verification_run_id) REFERENCES airank_opportunity_derivation_runs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_action_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          action_id VARCHAR(64) NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          from_status VARCHAR(40) NULL,
          to_status VARCHAR(40) NOT NULL,
          action_version INT NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor_user_id VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          payload_json JSON NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_action_event_idempotency
            (tenant_id, action_id, idempotency_key),
          UNIQUE KEY uk_airank_opportunity_action_event_version
            (tenant_id, action_id, action_version),
          KEY idx_airank_opportunity_action_event
            (tenant_id, project_id, action_id, created_at),
          CONSTRAINT fk_airank_opportunity_action_event_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_action_event_action
            FOREIGN KEY (action_id) REFERENCES airank_opportunity_actions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Actions and events are customer delivery evidence. Export and reconcile
    # them explicitly instead of silently deleting their audit history.
    pass

"""add immutable cross-domain intervention opportunity snapshots

Revision ID: 20260809_0033
Revises: 20260809_0032
Create Date: 2026-08-09 13:20:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0033"
down_revision = "20260809_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_opportunity_derivation_runs (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          policy_version VARCHAR(96) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          source_basis_sha256 CHAR(64) NOT NULL,
          evaluated_at DATETIME(3) NOT NULL,
          knowledge_window_days INT NOT NULL,
          previous_run_id VARCHAR(64) NULL,
          opportunity_ids_json JSON NOT NULL,
          cleared_opportunity_ids_json JSON NOT NULL,
          source_counts_json JSON NOT NULL,
          opportunity_count INT NOT NULL,
          new_count INT NOT NULL,
          persisting_count INT NOT NULL,
          cleared_count INT NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'succeeded',
          created_by VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_run_idempotency
            (tenant_id, project_id, idempotency_key),
          KEY idx_airank_opportunity_run_project
            (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_opportunity_run_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_run_previous
            FOREIGN KEY (previous_run_id) REFERENCES airank_opportunity_derivation_runs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_intervention_opportunity_snapshots (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          derivation_run_id VARCHAR(64) NOT NULL,
          opportunity_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          policy_version VARCHAR(96) NOT NULL,
          source_kind VARCHAR(48) NOT NULL,
          source_ref_type VARCHAR(64) NOT NULL,
          source_ref_id VARCHAR(128) NOT NULL,
          issue_code VARCHAR(128) NOT NULL,
          source_evidence_sha256 CHAR(64) NOT NULL,
          evidence_level VARCHAR(64) NOT NULL,
          state VARCHAR(32) NOT NULL COMMENT 'blocked_evidence/ready_for_action/monitor',
          intervention_gate VARCHAR(48) NOT NULL,
          severity VARCHAR(16) NOT NULL,
          priority_score INT NOT NULL,
          score_factors_json JSON NOT NULL,
          source_refs_json JSON NOT NULL,
          title VARCHAR(255) NOT NULL,
          description TEXT NOT NULL,
          recommended_action VARCHAR(96) NOT NULL,
          observed_at DATETIME(3) NOT NULL,
          snapshot_sha256 CHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_opportunity_snapshot
            (tenant_id, derivation_run_id, opportunity_id),
          KEY idx_airank_opportunity_current
            (tenant_id, project_id, source_kind, state, priority_score),
          KEY idx_airank_opportunity_stable
            (tenant_id, project_id, opportunity_id, created_at),
          CONSTRAINT fk_airank_opportunity_snapshot_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_opportunity_snapshot_run
            FOREIGN KEY (derivation_run_id) REFERENCES airank_opportunity_derivation_runs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Opportunity snapshots are customer-facing provenance. Export and
    # reconcile them explicitly instead of silently deleting audit history.
    pass

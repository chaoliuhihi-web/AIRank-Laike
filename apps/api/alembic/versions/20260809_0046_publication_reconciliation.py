"""add governed two-person publication reconciliation

Revision ID: 20260809_0046
Revises: 20260809_0045
Create Date: 2026-08-09 20:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0046"
down_revision = "20260809_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_publish_reconciliation_cases (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          package_id VARCHAR(64) NOT NULL,
          attempt_id VARCHAR(64) NOT NULL,
          operation_id VARCHAR(64) NOT NULL,
          proposed_outcome VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL,
          published_url VARCHAR(2048) NOT NULL,
          external_receipt_id VARCHAR(255) NOT NULL,
          response_status INT NOT NULL,
          evidence_object_ref_id VARCHAR(64) NOT NULL,
          evidence_sha256 CHAR(64) NOT NULL,
          evidence_note VARCHAR(2000) NOT NULL,
          observed_at DATETIME(3) NOT NULL,
          submitted_by VARCHAR(128) NOT NULL,
          reviewed_by VARCHAR(128) NULL,
          review_note VARCHAR(2000) NULL,
          idempotency_key_sha256 CHAR(64) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          review_idempotency_key_sha256 CHAR(64) NULL,
          review_request_sha256 CHAR(64) NULL,
          receipt_sha256 CHAR(64) NULL,
          latest_event_sha256 CHAR(64) NULL,
          event_sequence INT NOT NULL DEFAULT 0,
          submitted_at DATETIME(3) NOT NULL,
          reviewed_at DATETIME(3) NULL,
          applied_at DATETIME(3) NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_publish_reconciliation_idempotency
            (tenant_id, package_id, idempotency_key_sha256),
          KEY idx_airank_publish_reconciliation_attempt
            (tenant_id, attempt_id, status, submitted_at),
          KEY idx_airank_publish_reconciliation_project
            (tenant_id, project_id, status, submitted_at),
          KEY idx_airank_publish_reconciliation_operation (operation_id),
          CONSTRAINT fk_airank_publish_reconciliation_package
            FOREIGN KEY (package_id) REFERENCES airank_publish_packages (id),
          CONSTRAINT fk_airank_publish_reconciliation_attempt
            FOREIGN KEY (attempt_id) REFERENCES airank_publish_attempts (id),
          CONSTRAINT fk_airank_publish_reconciliation_operation
            FOREIGN KEY (operation_id) REFERENCES airank_operation_guards (id),
          CONSTRAINT fk_airank_publish_reconciliation_evidence
            FOREIGN KEY (evidence_object_ref_id) REFERENCES airank_object_refs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_publish_reconciliation_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          case_id VARCHAR(64) NOT NULL,
          event_sequence INT NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          from_status VARCHAR(32) NULL,
          to_status VARCHAR(32) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          evidence_sha256 CHAR(64) NOT NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_publish_reconciliation_event_sequence
            (case_id, event_sequence),
          UNIQUE KEY uk_airank_publish_reconciliation_event_hash (event_sha256),
          KEY idx_airank_publish_reconciliation_event_tenant
            (tenant_id, case_id, event_sequence),
          CONSTRAINT fk_airank_publish_reconciliation_event_case
            FOREIGN KEY (case_id) REFERENCES airank_publish_reconciliation_cases (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.add_column(
        "airank_publish_attempts",
        sa.Column("reconciliation_case_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "idx_airank_publish_attempt_reconciliation",
        "airank_publish_attempts",
        ["tenant_id", "reconciliation_case_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_airank_publish_attempt_reconciliation",
        "airank_publish_attempts",
        "airank_publish_reconciliation_cases",
        ["reconciliation_case_id"],
        ["id"],
    )


def downgrade() -> None:
    # Reconciliation evidence, reviews and event hashes are audit records.
    # Destructive rollback requires an explicit retention/export decision.
    pass

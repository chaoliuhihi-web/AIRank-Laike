"""add immutable project evidence integrity audits

Revision ID: 20260808_0026
Revises: 20260808_0025
Create Date: 2026-08-08 20:10:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0026"
down_revision = "20260808_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_integrity_audits (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          policy_version VARCHAR(64) NOT NULL,
          scope VARCHAR(32) NOT NULL DEFAULT 'project',
          status VARCHAR(32) NOT NULL COMMENT 'passed/blocked/failed',
          entity_count INT NOT NULL DEFAULT 0,
          verified_count INT NOT NULL DEFAULT 0,
          blocking_finding_count INT NOT NULL DEFAULT 0,
          unavailable_count INT NOT NULL DEFAULT 0,
          hash_mismatch_count INT NOT NULL DEFAULT 0,
          size_mismatch_count INT NOT NULL DEFAULT 0,
          metadata_invalid_count INT NOT NULL DEFAULT 0,
          manifest_sha256 CHAR(64) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          requested_by VARCHAR(64) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          started_at DATETIME(3) NOT NULL,
          completed_at DATETIME(3) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_evidence_integrity_idempotency
            (tenant_id, project_id, idempotency_key),
          KEY idx_airank_evidence_integrity_latest
            (tenant_id, project_id, created_at),
          KEY idx_airank_evidence_integrity_status
            (tenant_id, status, created_at),
          CONSTRAINT fk_airank_evidence_integrity_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_integrity_findings (
          id VARCHAR(64) NOT NULL,
          audit_id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          entity_type VARCHAR(64) NOT NULL,
          entity_id VARCHAR(64) NOT NULL,
          object_type VARCHAR(64) NULL,
          status VARCHAR(32) NOT NULL COMMENT 'verified/metadata_invalid/unavailable/driver_mismatch/hash_mismatch/size_mismatch/scope_too_large',
          blocking TINYINT(1) NOT NULL DEFAULT 1,
          expected_sha256 CHAR(64) NULL,
          actual_sha256 CHAR(64) NULL,
          expected_byte_size BIGINT NULL,
          actual_byte_size BIGINT NULL,
          details_json JSON NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_evidence_integrity_entity
            (audit_id, entity_type, entity_id),
          KEY idx_airank_evidence_integrity_finding_status
            (tenant_id, project_id, status, created_at),
          CONSTRAINT fk_airank_evidence_integrity_finding_audit
            FOREIGN KEY (audit_id) REFERENCES airank_evidence_integrity_audits (id),
          CONSTRAINT fk_airank_evidence_integrity_finding_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        "ALTER TABLE airank_report_evidence_packets "
        "ADD COLUMN integrity_audit_id VARCHAR(64) NULL AFTER object_ref_id"
    )
    op.execute(
        "CREATE INDEX idx_airank_report_packet_integrity "
        "ON airank_report_evidence_packets (tenant_id, project_id, integrity_audit_id)"
    )
    op.execute(
        "ALTER TABLE airank_report_evidence_packets "
        "ADD CONSTRAINT fk_airank_report_packet_integrity "
        "FOREIGN KEY (integrity_audit_id) REFERENCES airank_evidence_integrity_audits (id)"
    )


def downgrade() -> None:
    # Audit records prove whether customer evidence was intact at delivery time.
    # Destructive rollback requires an explicit evidence export and migration.
    pass

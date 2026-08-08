"""bind governed facts to a stable comparison subject

Revision ID: 20260808_0023
Revises: 20260808_0022
Create Date: 2026-08-08 22:15:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0023"
down_revision = "20260808_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE airank_fact_atoms
          ADD COLUMN subject_type VARCHAR(32) NOT NULL DEFAULT 'general' AFTER fact_type,
          ADD COLUMN subject_ref_id VARCHAR(128) NULL AFTER subject_type,
          ADD CONSTRAINT chk_airank_fact_subject_binding CHECK (
            (subject_type = 'general' AND subject_ref_id IS NULL)
            OR
            (subject_type IN ('brand', 'company', 'product', 'competitor', 'solution_type') AND subject_ref_id IS NOT NULL)
          ),
          ADD INDEX idx_airank_fact_subject (tenant_id, project_id, subject_type, subject_ref_id, status)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE airank_fact_atoms
          DROP INDEX idx_airank_fact_subject,
          DROP CHECK chk_airank_fact_subject_binding,
          DROP COLUMN subject_ref_id,
          DROP COLUMN subject_type
        """
    )

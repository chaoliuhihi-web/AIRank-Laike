"""allow immutable report packets to supersede when governed evidence changes

Revision ID: 20260808_0021
Revises: 20260808_0020
Create Date: 2026-08-08 18:40:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0021"
down_revision = "20260808_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A report can gain new fact reviews, citation captures, or source-governance
    # revisions after its first delivery packet. Keep every packet immutable and
    # deduplicate by content hash instead of freezing one packet per schema version.
    op.execute(
        """
        ALTER TABLE airank_report_evidence_packets
          DROP INDEX uk_airank_report_packet_version,
          ADD KEY idx_airank_report_packet_version_history
            (tenant_id, report_id, schema_version, created_at)
        """
    )


def downgrade() -> None:
    # Reintroducing the former unique key could discard or block immutable
    # customer delivery history. Fail before Alembic can stamp an older revision;
    # operators must export/reconcile packet history before a manual rollback.
    raise RuntimeError(
        "20260808_0021 is irreversible without an explicit report-packet history migration"
    )

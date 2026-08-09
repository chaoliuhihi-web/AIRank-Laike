"""add encrypted provider credential vault and rotation audit

Revision ID: 20260809_0040
Revises: 20260809_0039
Create Date: 2026-08-09 09:10:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260809_0040"
down_revision = "20260809_0039"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_credentials (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          route_id VARCHAR(64) NOT NULL,
          credential_version INT NOT NULL,
          status VARCHAR(32) NOT NULL,
          is_current TINYINT(1) NOT NULL DEFAULT 1,
          secret_ciphertext MEDIUMTEXT NOT NULL,
          secret_nonce VARCHAR(64) NOT NULL,
          secret_mask VARCHAR(96) NOT NULL,
          secret_fingerprint CHAR(64) NOT NULL,
          encryption_key_id VARCHAR(64) NOT NULL,
          fingerprint_key_id VARCHAR(64) NOT NULL,
          algorithm VARCHAR(32) NOT NULL,
          verification_json JSON NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          rotated_from_id VARCHAR(64) NULL,
          reason VARCHAR(500) NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          activated_at DATETIME(3) NOT NULL,
          revoked_at DATETIME(3) NULL,
          scrubbed_at DATETIME(3) NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_credential_version
            (tenant_id, provider_key, route_id, credential_version),
          KEY idx_airank_provider_credential_current
            (tenant_id, provider_key, route_id, is_current, credential_version),
          KEY idx_airank_provider_credential_fingerprint
            (tenant_id, fingerprint_key_id, secret_fingerprint),
          CONSTRAINT fk_airank_provider_credential_rotated_from
            FOREIGN KEY (rotated_from_id) REFERENCES airank_provider_credentials (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_credential_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          credential_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          route_id VARCHAR(64) NOT NULL,
          credential_version INT NOT NULL,
          event_sequence BIGINT NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          credential_fingerprint CHAR(64) NOT NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor VARCHAR(128) NOT NULL,
          reason VARCHAR(500) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_credential_event_hash (event_sha256),
          UNIQUE KEY uk_airank_provider_credential_event_sequence
            (tenant_id, provider_key, route_id, event_sequence),
          KEY idx_airank_provider_credential_event_chain
            (tenant_id, provider_key, route_id, event_sequence),
          CONSTRAINT fk_airank_provider_credential_event_credential
            FOREIGN KEY (credential_id) REFERENCES airank_provider_credentials (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    audit_columns = (
        ("credential_source", "VARCHAR(32) NULL AFTER configuration_fingerprint"),
        ("credential_id", "VARCHAR(64) NULL AFTER credential_source"),
        ("credential_version", "INT NULL AFTER credential_id"),
    )
    for column_name, definition in audit_columns:
        if not _has_column("airank_provider_request_audits", column_name):
            op.execute(
                f"ALTER TABLE airank_provider_request_audits ADD COLUMN {column_name} {definition}"
            )
    if not _has_index("airank_provider_request_audits", "idx_airank_provider_audit_credential"):
        op.execute(
            "CREATE INDEX idx_airank_provider_audit_credential "
            "ON airank_provider_request_audits "
            "(tenant_id, credential_id, credential_version, requested_at)"
        )


def downgrade() -> None:
    # Credential history and request attribution are security audit evidence.
    # Destructive rollback requires an explicit export and scrub plan.
    pass

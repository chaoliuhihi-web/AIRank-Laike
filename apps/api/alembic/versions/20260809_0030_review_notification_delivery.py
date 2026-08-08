"""add governed reviewer notification consumer state and immutable receipts

Revision ID: 20260809_0030
Revises: 20260809_0029
Create Date: 2026-08-09 04:10:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0030"
down_revision = "20260809_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_notification_deliveries (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          outbox_event_id VARCHAR(64) NOT NULL,
          channel VARCHAR(32) NOT NULL COMMENT 'webhook',
          status VARCHAR(32) NOT NULL COMMENT 'queued/running/succeeded/failed',
          attempt_count INT NOT NULL DEFAULT 0,
          max_attempts INT NOT NULL DEFAULT 3,
          next_attempt_at DATETIME(3) NOT NULL,
          locked_by VARCHAR(128) NULL,
          locked_at DATETIME(3) NULL,
          timeout_seconds INT NOT NULL DEFAULT 30,
          endpoint_host VARCHAR(255) NOT NULL,
          config_fingerprint CHAR(64) NOT NULL,
          latest_receipt_id VARCHAR(64) NULL,
          last_error_code VARCHAR(128) NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_notification_event_channel
            (tenant_id, outbox_event_id, channel),
          KEY idx_airank_notification_claim
            (status, next_attempt_at, tenant_id, project_id),
          CONSTRAINT fk_airank_notification_event
            FOREIGN KEY (outbox_event_id) REFERENCES airank_outbox_events (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_notification_delivery_receipts (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          delivery_id VARCHAR(64) NOT NULL,
          outbox_event_id VARCHAR(64) NOT NULL,
          channel VARCHAR(32) NOT NULL,
          attempt_number INT NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'succeeded/failed',
          request_sha256 CHAR(64) NOT NULL,
          response_status INT NULL,
          response_sha256 CHAR(64) NULL,
          provider_receipt_id VARCHAR(255) NULL,
          endpoint_host VARCHAR(255) NOT NULL,
          connected_ip VARCHAR(64) NULL,
          error_code VARCHAR(128) NULL,
          retryable TINYINT(1) NOT NULL DEFAULT 0,
          started_at DATETIME(3) NOT NULL,
          finished_at DATETIME(3) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_notification_attempt
            (tenant_id, delivery_id, attempt_number),
          KEY idx_airank_notification_receipt_event
            (tenant_id, outbox_event_id, created_at),
          CONSTRAINT fk_airank_notification_receipt_delivery
            FOREIGN KEY (delivery_id) REFERENCES airank_notification_deliveries (id),
          CONSTRAINT fk_airank_notification_receipt_event
            FOREIGN KEY (outbox_event_id) REFERENCES airank_outbox_events (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Delivery receipts are customer-facing audit evidence and must be exported
    # and reconciled before any deliberate rollback.
    pass

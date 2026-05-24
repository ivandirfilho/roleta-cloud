"""S5 outbox table (CDC para dual-write SQLite -> PG).

Revision ID: 0004_outbox
Revises: 0003_vector_schema
Create Date: 2026-05-24
"""
from __future__ import annotations

from alembic import op

revision = "0004_outbox"
down_revision = "0003_vector_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Worker S5 consome esta tabela. status: pending -> processed | failed.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shared.outbox (
            id            BIGSERIAL PRIMARY KEY,
            event_uuid    UUID NOT NULL UNIQUE,
            aggregate     TEXT NOT NULL,             -- 'decision' | 'session' | 'gale_window'
            aggregate_id  TEXT NOT NULL,
            payload       JSONB NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at  TIMESTAMPTZ,
            status        TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'processed', 'failed')),
            error         TEXT,
            retries       INT NOT NULL DEFAULT 0
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_outbox_pending "
        "ON shared.outbox (created_at) WHERE status = 'pending';"
    )
    op.execute(
        "COMMENT ON TABLE shared.outbox IS "
        "'CDC outbox: app escreve aqui via dual-write; worker S5 replica para tabelas finais.';"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shared.outbox;")

"""S-I outbox NOTIFY trigger (substitui SQL standalone migrations/007_*.sql).

Revision ID: 0005_outbox_notify
Revises: 0004_outbox
Create Date: 2026-05-24
"""
from __future__ import annotations

from alembic import op

revision = "0005_outbox_notify"
down_revision = "0004_outbox"
branch_labels = None
depends_on = None


_UP_SQL = """
CREATE OR REPLACE FUNCTION shared.notify_outbox_new() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_notify('outbox_new', NEW.id::text);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_outbox_notify ON shared.outbox;
CREATE TRIGGER trg_outbox_notify
  AFTER INSERT ON shared.outbox
  FOR EACH ROW
  EXECUTE FUNCTION shared.notify_outbox_new();

COMMENT ON FUNCTION shared.notify_outbox_new() IS
  'S-I (v4 sprint plan): emite NOTIFY para que cdc_worker acorde imediatamente. Aditivo ao polling.';
"""

_DOWN_SQL = """
DROP TRIGGER IF EXISTS trg_outbox_notify ON shared.outbox;
DROP FUNCTION IF EXISTS shared.notify_outbox_new();
"""


def upgrade() -> None:
    op.execute(_UP_SQL)


def downgrade() -> None:
    op.execute(_DOWN_SQL)

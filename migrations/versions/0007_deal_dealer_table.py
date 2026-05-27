"""SP-13 DEAL-03 (27/05): dealer/table/provider/round_id em decisions + dealers ref.

Coluna ``dealer`` reaproveita TEXT default 'unknown' para nao quebrar selects
antigos. Index parcial em ``shared.dealers`` para ranking por hit_rate.

PG canonical (este migration). SQLite mirror auto-migra em ``sqlite_repo.py``
no proximo deploy (mesmo padrao SP-16).
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_deal_dealer_table"
down_revision = "0006_spin_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shared.dealers (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            provider    TEXT,
            "table"     TEXT,
            first_seen  TIMESTAMP DEFAULT NOW(),
            last_seen   TIMESTAMP DEFAULT NOW(),
            n_spins     INTEGER DEFAULT 0,
            n_hits      INTEGER DEFAULT 0,
            meta        JSONB DEFAULT '{}'::jsonb,
            UNIQUE(name, provider, "table")
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_dealers_provider ON shared.dealers(provider)'
    )
    # Adiciona colunas em decisions (cw + ccw schemas mantem cross-direction
    # mas spin_features ja tem direction discriminado).
    for sch in ("cw", "ccw"):
        op.execute(
            f"""
            ALTER TABLE {sch}.spin_features
            ADD COLUMN IF NOT EXISTS dealer TEXT DEFAULT 'unknown',
            ADD COLUMN IF NOT EXISTS "table" TEXT,
            ADD COLUMN IF NOT EXISTS provider TEXT,
            ADD COLUMN IF NOT EXISTS round_id TEXT
            """
        )
        op.execute(
            f'CREATE INDEX IF NOT EXISTS ix_{sch}_spin_dealer ON {sch}.spin_features(dealer)'
        )


def downgrade() -> None:
    for sch in ("cw", "ccw"):
        op.execute(f'DROP INDEX IF EXISTS {sch}.ix_{sch}_spin_dealer')
        op.execute(
            f'ALTER TABLE {sch}.spin_features '
            f'DROP COLUMN IF EXISTS dealer, '
            f'DROP COLUMN IF EXISTS "table", '
            f'DROP COLUMN IF EXISTS provider, '
            f'DROP COLUMN IF EXISTS round_id'
        )
    op.execute('DROP INDEX IF EXISTS shared.ix_dealers_provider')
    op.execute('DROP TABLE IF EXISTS shared.dealers')

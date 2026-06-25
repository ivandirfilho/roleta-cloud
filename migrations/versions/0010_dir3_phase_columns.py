"""DIR3/DIR11 (sentido-fase): colunas de fase (spin_seq, direction_source,
direction_confidence, direction_next, phase_uncertain) em cw/ccw.spin_features.

Aditivo e idempotente (ADD COLUMN IF NOT EXISTS), mesmo padrão dos 0007/0009.
Espelha o que sqlite_repo.py:372-380 ja adiciona em decisions (SQLite local) via
fallback in-loco — agora a sequencia Alembic cobre tambem o PG espelho.

Backward-compatible: NULL quando o handler nao envia (DIR3 OFF) ou cliente legado.

Revision ID: 0010_dir3_phase_columns
Revises: 0009_vision_features
"""
from alembic import op


revision = "0010_dir3_phase_columns"
down_revision = "0009_vision_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for sch in ("cw", "ccw"):
        op.execute(
            f"""
            ALTER TABLE {sch}.spin_features
            ADD COLUMN IF NOT EXISTS spin_seq INTEGER,
            ADD COLUMN IF NOT EXISTS direction_source TEXT,
            ADD COLUMN IF NOT EXISTS direction_confidence REAL,
            ADD COLUMN IF NOT EXISTS direction_next TEXT,
            ADD COLUMN IF NOT EXISTS phase_uncertain BOOLEAN
            """
        )
        # Indice em spin_seq facilita debug temporal (recuperar gap, auditar sequencia).
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{sch}_spin_seq "
            f"ON {sch}.spin_features(spin_seq)"
        )


def downgrade() -> None:
    # INV ADITIVO: schema nao-destrutivo. Mantemos as colunas (NULL) em caso de
    # rollback parcial — match com a politica do deploy (nao faz downgrade).
    for sch in ("cw", "ccw"):
        op.execute(f"DROP INDEX IF EXISTS {sch}.ix_{sch}_spin_seq")

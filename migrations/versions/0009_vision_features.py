"""Vision features (foto_roleta_junho.md Parte 4): wheel_model/vision_confidence/
vision_source em cw/ccw.spin_features — feature store p/ foto->dados.

Aditivo e idempotente (ADD COLUMN IF NOT EXISTS), mesmo padrão do 0007. SQLite mirror
auto-migra em sqlite_repo.py. Backward-compatible: NULL quando a extensão não envia.

Revision ID: 0009_vision_features
Revises: 0008_decision_dna
"""
from alembic import op


revision = "0009_vision_features"
down_revision = "0008_decision_dna"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for sch in ("cw", "ccw"):
        op.execute(
            f"""
            ALTER TABLE {sch}.spin_features
            ADD COLUMN IF NOT EXISTS wheel_model TEXT,
            ADD COLUMN IF NOT EXISTS vision_confidence REAL,
            ADD COLUMN IF NOT EXISTS vision_source TEXT
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{sch}_spin_wheel_model "
            f"ON {sch}.spin_features(wheel_model)"
        )


def downgrade() -> None:
    for sch in ("cw", "ccw"):
        op.execute(f"DROP INDEX IF EXISTS {sch}.ix_{sch}_spin_wheel_model")
        op.execute(
            f"ALTER TABLE {sch}.spin_features "
            f"DROP COLUMN IF EXISTS wheel_model, "
            f"DROP COLUMN IF EXISTS vision_confidence, "
            f"DROP COLUMN IF EXISTS vision_source"
        )

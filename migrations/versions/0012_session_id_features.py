"""H3 (03/08): session_id nas feature stores — janelas por sessão real.

Revision ID: 0012_session_id_features
Revises: 0011_unique_decision_id
Create Date: 2025-08-03

Fundação de dados (evolução_03_08.md §4.2-H3): as lag-features do
cw|ccw.spin_features (recent_acc_10/50, streaks, last_20_hits) eram
computadas com window query GLOBAL — a última sessão "vazava" para a
primeira janela da sessão seguinte, contaminando acurácias no início de
cada sessão (o corte de sessão é uma fronteira estatística real: dealer,
mesa e regime mudam).

Coluna ADITIVA (nullable — rows históricas ficam NULL e continuam válidas).
O cdc_worker (H3 código) passa a:
- filtrar a window query por session_id quando presente no payload;
- gravar session_id na linha nova.
"""
from __future__ import annotations

from alembic import op

revision = "0012_session_id_features"
down_revision = "0011_unique_decision_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for schema in ("cw", "ccw"):
        op.execute(
            f"ALTER TABLE {schema}.spin_features "
            f"ADD COLUMN IF NOT EXISTS session_id TEXT;"
        )
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{schema}_spin_features_session
                ON {schema}.spin_features (session_id, id DESC);
            """
        )
        op.execute(
            f"COMMENT ON COLUMN {schema}.spin_features.session_id IS "
            f"'H3 03/08: sessão SQLite de origem — isola janelas de lag features por sessão.';"
        )


def downgrade() -> None:
    for schema in ("cw", "ccw"):
        op.execute(f"DROP INDEX IF EXISTS {schema}.idx_{schema}_spin_features_session;")
        op.execute(f"ALTER TABLE {schema}.spin_features DROP COLUMN IF EXISTS session_id;")

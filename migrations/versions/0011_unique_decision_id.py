"""H2 (03/08): idempotência real — UNIQUE parcial em decision_id.

Revision ID: 0011_unique_decision_id
Revises: 0010_dir3_phase_columns
Create Date: 2025-08-03

Fundação de dados (evolução_03_08.md §4.2-H2): o cdc_worker insere em
cw|ccw.spins_vectors e cw|ccw.spin_features sem guard de unicidade — replays
manuais do outbox ou retries duplicam linhas (126 duplicatas observadas em
produção na auditoria de 03/08).

Estratégia ADITIVA (inviolável):
1. Dedup prévio — mantém a linha de MENOR id por decision_id (a original),
   remove só as cópias posteriores. Sem isso o CREATE UNIQUE INDEX falharia.
2. UNIQUE INDEX PARCIAL (WHERE decision_id IS NOT NULL) — decision_id é
   nullable por design (spins sem decisão associada não participam).

O worker (H2 código) passa a usar ON CONFLICT (decision_id) WHERE
decision_id IS NOT NULL DO NOTHING — replay vira no-op.

Rollback de deploy NÃO downgrade schema (política); downgrade existe apenas
para dev local.
"""
from __future__ import annotations

from alembic import op

revision = "0011_unique_decision_id"
down_revision = "0010_dir3_phase_columns"
branch_labels = None
depends_on = None

_TABLES = (
    ("cw", "spins_vectors"),
    ("ccw", "spins_vectors"),
    ("cw", "spin_features"),
    ("ccw", "spin_features"),
)


def upgrade() -> None:
    for schema, table in _TABLES:
        # 1) dedup: preserva a primeira ocorrência (menor id) por decision_id
        op.execute(
            f"""
            DELETE FROM {schema}.{table} t
            USING (
                SELECT decision_id, MIN(id) AS keep_id
                FROM {schema}.{table}
                WHERE decision_id IS NOT NULL
                GROUP BY decision_id
                HAVING COUNT(*) > 1
            ) d
            WHERE t.decision_id = d.decision_id
              AND t.id <> d.keep_id;
            """
        )
        # 2) unicidade parcial (NULLs continuam livres)
        op.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_{schema}_{table}_decision
                ON {schema}.{table} (decision_id)
                WHERE decision_id IS NOT NULL;
            """
        )


def downgrade() -> None:
    for schema, table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS {schema}.uq_{schema}_{table}_decision;")

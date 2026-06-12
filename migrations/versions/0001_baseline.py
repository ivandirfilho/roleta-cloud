"""baseline: schemas + extensoes (idempotente, espelha docker/postgres/init/*).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-24
"""
from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensoes (sao criadas pelo init script no bootstrap, idempotentes).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # AGE: best-effort (12/06). Decisao P1.3: schemas de grafo vazios, AGE
    # caminha para remocao. Prod (imagem custom) tem a extensao; o CI
    # (pgvector/pgvector:pg15 oficial) NAO tem — e nao deve quebrar por isso.
    op.execute(
        """
        DO $$ BEGIN
            CREATE EXTENSION IF NOT EXISTS age;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'extension age indisponivel — pulando (P1.3: AGE a remover)';
        END $$;
        """
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")

    # Schemas isolando CW/CCW (inegociavel).
    op.execute("CREATE SCHEMA IF NOT EXISTS cw;")
    op.execute("CREATE SCHEMA IF NOT EXISTS ccw;")
    op.execute("CREATE SCHEMA IF NOT EXISTS shared;")

    # Comentarios para queryable metadata.
    op.execute("COMMENT ON SCHEMA cw IS 'Clockwise direction — never mixes with ccw';")
    op.execute("COMMENT ON SCHEMA ccw IS 'Counter-clockwise direction — never mixes with cw';")
    op.execute("COMMENT ON SCHEMA shared IS 'Cross-direction data (sessions, flags, versions)';")


def downgrade() -> None:
    # Baseline nao desfaz extensoes/schemas (risco de dados).
    pass

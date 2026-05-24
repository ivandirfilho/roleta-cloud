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
    op.execute("CREATE EXTENSION IF NOT EXISTS age;")
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

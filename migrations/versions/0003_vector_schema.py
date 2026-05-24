"""S6 schema vector: cw/ccw spins_vectors + ivfflat indexes.

Revision ID: 0003_vector_schema
Revises: 0002_strategy_versions
Create Date: 2026-05-24
"""
from __future__ import annotations

from alembic import op

revision = "0003_vector_schema"
down_revision = "0002_strategy_versions"
branch_labels = None
depends_on = None


# 6 dimensoes = features brutas do spin (force, mean_last_6, std_last_6, region_id,
# delta_force_3, delta_force_6). Autoencoder S7 vai produzir compressao 6->4->6.
SPIN_DIM = 6


def _spins_vectors_ddl(schema: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {schema}.spins_vectors (
        id           BIGSERIAL PRIMARY KEY,
        spin_uuid    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
        decision_id  BIGINT,                 -- FK soft (SQLite ainda autoritativo em S1-S4)
        ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
        raw_features VECTOR({SPIN_DIM}) NOT NULL,
        ae_latent    VECTOR(4),              -- preenchido por S7 (autoencoder)
        meta         JSONB NOT NULL DEFAULT '{{}}'::jsonb
    );

    CREATE INDEX IF NOT EXISTS idx_{schema}_spins_vectors_ts
        ON {schema}.spins_vectors (ts DESC);

    -- ivfflat com 100 listas: bom para ate ~1M linhas.
    -- Vai ser CREATE INDEX CONCURRENTLY em prod (S9), aqui basta o standard.
    CREATE INDEX IF NOT EXISTS idx_{schema}_spins_vectors_raw_cosine
        ON {schema}.spins_vectors USING ivfflat (raw_features vector_cosine_ops)
        WITH (lists = 100);

    COMMENT ON TABLE {schema}.spins_vectors IS
        'S6: features vetorizadas de spins (direcao {schema}). raw=6dim, ae_latent=4dim (S7).';
    """


def upgrade() -> None:
    op.execute(_spins_vectors_ddl("cw"))
    op.execute(_spins_vectors_ddl("ccw"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cw.spins_vectors;")
    op.execute("DROP TABLE IF EXISTS ccw.spins_vectors;")

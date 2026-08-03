"""H6 (03/08): índices HNSW nos vetores — busca de regime O(log n).

Revision ID: 0013_hnsw_vectors
Revises: 0012_session_id_features
Create Date: 2025-08-03

Fundação de dados (evolução_03_08.md §4.2-H6): regime_similarity.py consulta
cw|ccw.spins_vectors com o operador <=> (cosine distance) SEM índice — cada
find_similar/regime_score é um seq scan O(n). Com HNSW o pgvector responde
em O(log n) e a busca de regime (E3) escala.

Índices em:
- raw_features (usado HOJE por regime_similarity)
- ae_latent    (parcial, usado pelo matching E3 pós-backfill do autoencoder)

ADITIVO puro — índices não mudam semântica de leitura/escrita.
Nota: hnsw em pgvector >= 0.5; produção roda vector 0.8.2.
"""
from __future__ import annotations

from alembic import op

revision = "0013_hnsw_vectors"
down_revision = "0012_session_id_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for schema in ("cw", "ccw"):
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{schema}_spins_vectors_raw_hnsw
                ON {schema}.spins_vectors
                USING hnsw (raw_features vector_cosine_ops);
            """
        )
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{schema}_spins_vectors_latent_hnsw
                ON {schema}.spins_vectors
                USING hnsw (ae_latent vector_cosine_ops)
                WHERE ae_latent IS NOT NULL;
            """
        )


def downgrade() -> None:
    for schema in ("cw", "ccw"):
        op.execute(f"DROP INDEX IF EXISTS {schema}.idx_{schema}_spins_vectors_raw_hnsw;")
        op.execute(f"DROP INDEX IF EXISTS {schema}.idx_{schema}_spins_vectors_latent_hnsw;")

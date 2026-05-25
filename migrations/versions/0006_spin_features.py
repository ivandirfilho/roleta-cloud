"""S-STRAT-8: feature store no PG (cw/ccw.spin_features).

Revision ID: 0006_spin_features
Revises: 0005_outbox_notify
Create Date: 2026-05-25

Tabela paralela a spins_vectors, focada em features tabulares (lag features
dos últimos N spins) consumíveis pelo bet_advisor/scoring batch.

Per PLAN-V2-02: schemas dedicados cw.spin_features e ccw.spin_features
(NÃO shared) para isolar workloads e simplificar window queries por direção.
"""
from __future__ import annotations

from alembic import op

revision = "0006_spin_features"
down_revision = "0005_outbox_notify"
branch_labels = None
depends_on = None


def _spin_features_ddl(schema: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {schema}.spin_features (
        id                BIGSERIAL PRIMARY KEY,
        ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
        decision_id       BIGINT,
        spin_number       INTEGER,
        hit               BOOLEAN,
        centro_previsto   INTEGER,
        gale_level        INTEGER,
        recent_acc_10     REAL,
        recent_acc_50     REAL,
        streak_miss       INTEGER NOT NULL DEFAULT 0,
        streak_hit        INTEGER NOT NULL DEFAULT 0,
        last_20_hits      BOOLEAN[] NOT NULL DEFAULT ARRAY[]::BOOLEAN[],
        meta              JSONB NOT NULL DEFAULT '{{}}'::jsonb
    );

    CREATE INDEX IF NOT EXISTS idx_{schema}_spin_features_ts
        ON {schema}.spin_features (ts DESC);

    CREATE INDEX IF NOT EXISTS idx_{schema}_spin_features_decision
        ON {schema}.spin_features (decision_id);

    COMMENT ON TABLE {schema}.spin_features IS
        'S-STRAT-8: feature store tabular ({schema}). Populada pelo cdc_worker via outbox spin_result.';
    """


def upgrade() -> None:
    op.execute(_spin_features_ddl("cw"))
    op.execute(_spin_features_ddl("ccw"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cw.spin_features;")
    op.execute("DROP TABLE IF EXISTS ccw.spin_features;")

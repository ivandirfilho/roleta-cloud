"""SP-06 / DNA-01: tabela decision_dna + view materializada dna_summary.

Revision ID: 0008_decision_dna
Revises: 0006_spin_features
Create Date: 2026-05-26

Implementa §1.2 do sprint_evolucao_26_05blueprint.md.

Tabela append-only para DNA estrutural por decisao: cada feature
fine-tuning (sda_score, calibration_offset, c4_rate bucket, kill_v4,
region_C1/C2/C3, etc.) emite UMA linha por decisao com:
  - estimated_lift_pp: pp esperado (de aprendizado historico)
  - realized_lift_pp:  pp realizado (preenchido pos-resultado)
  - confidence_n:      amostras usadas na estimativa

Materializacao dna_summary agrega por (feature_name, bucket) para
respostas instantaneas no endpoint /api/dna_summary (SP-09).

Schema shared.* eh criado se nao existir — sao features cross-direction
(cw e ccw compartilham metas de DNA).
"""
from __future__ import annotations

from alembic import op

revision = "0008_decision_dna"
down_revision = "0006_spin_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shared.decision_dna (
            id                 BIGSERIAL PRIMARY KEY,
            decision_id        BIGINT NOT NULL,
            spin_number        INTEGER,
            direction          TEXT,
            ts                 TIMESTAMPTZ NOT NULL DEFAULT now(),

            feature_name       TEXT NOT NULL,
            feature_value      JSONB NOT NULL,
            estimated_lift_pp  REAL,
            realized_lift_pp   REAL,
            confidence_n       INTEGER,

            final_action       TEXT,
            hit                BOOLEAN,
            wheel_dist         INTEGER
        );

        CREATE INDEX IF NOT EXISTS ix_dna_decision
            ON shared.decision_dna(decision_id);
        CREATE INDEX IF NOT EXISTS ix_dna_feature
            ON shared.decision_dna(feature_name);
        CREATE INDEX IF NOT EXISTS ix_dna_realized
            ON shared.decision_dna(realized_lift_pp)
            WHERE realized_lift_pp IS NOT NULL;
        CREATE INDEX IF NOT EXISTS ix_dna_ts
            ON shared.decision_dna(ts DESC);

        COMMENT ON TABLE shared.decision_dna IS
            'SP-06 / DNA-01: append-only DNA estrutural por decisao. Populado por dna_logger.';
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS shared.dna_summary AS
        SELECT
            feature_name,
            COALESCE(feature_value->>'bucket', '_raw') AS bucket,
            COUNT(*)                                   AS n,
            AVG(realized_lift_pp)                      AS avg_lift_pp,
            STDDEV(realized_lift_pp)                   AS sd_lift,
            AVG(CASE WHEN hit THEN 1.0 ELSE 0.0 END)   AS hr,
            MAX(ts)                                    AS last_seen
        FROM shared.decision_dna
        WHERE realized_lift_pp IS NOT NULL
        GROUP BY 1, 2;

        CREATE UNIQUE INDEX IF NOT EXISTS ux_dna_summary
            ON shared.dna_summary(feature_name, bucket);
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS shared.dna_summary;")
    op.execute("DROP TABLE IF EXISTS shared.decision_dna;")

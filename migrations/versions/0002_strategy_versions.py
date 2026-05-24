"""shared.strategy_versions + feature_flags (S3).

Revision ID: 0002_strategy_versions
Revises: 0001_baseline
Create Date: 2026-05-24
"""
from __future__ import annotations

from alembic import op

revision = "0002_strategy_versions"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # strategy_versions: fonte da verdade de PARAMETROS de estrategia.
    # git_tag linka com arquivo VERSION (que e fonte da verdade de RELEASE).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shared.strategy_versions (
            id          BIGSERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            version     TEXT NOT NULL,
            git_tag     TEXT,
            params      JSONB NOT NULL DEFAULT '{}'::jsonb,
            notes       TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (name, version)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_versions_created_at "
        "ON shared.strategy_versions (created_at DESC);"
    )
    op.execute(
        "COMMENT ON TABLE shared.strategy_versions IS "
        "'Catalogo de versoes de estrategia (Smart Gale v4, etc). "
        "git_tag = VERSION file; params = JSONB com knobs.';"
    )

    # feature_flags: liga/desliga features sem deploy.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shared.feature_flags (
            name        TEXT PRIMARY KEY,
            enabled     BOOLEAN NOT NULL DEFAULT false,
            pct         INT NOT NULL DEFAULT 0 CHECK (pct BETWEEN 0 AND 100),
            payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "COMMENT ON TABLE shared.feature_flags IS "
        "'Feature flags para canario/kill-switch. pct=0 fully off, pct=100 fully on.';"
    )

    # Seed: registrar v4.4.0 (release atual).
    op.execute(
        """
        INSERT INTO shared.strategy_versions (name, version, git_tag, params, notes)
        VALUES (
            'smart_gale',
            'v4.4.0',
            'v4.4.0',
            '{"max_gale_level": 4, "triple_rate_advisor": true, "quick_wins": "v4.4"}'::jsonb,
            'Baseline — Quick Wins v4.4 em producao.'
        )
        ON CONFLICT (name, version) DO NOTHING;
        """
    )

    # Seed: flags iniciais desabilitadas (vao ser ativadas em sprints futuras).
    op.execute(
        """
        INSERT INTO shared.feature_flags (name, enabled, pct, payload) VALUES
            ('shadow_predictor', false, 0, '{"timeout_ms": 1000}'::jsonb),
            ('new_decision_engine', false, 0, '{}'::jsonb),
            ('cold_regions', false, 0, '{}'::jsonb),
            ('outlier_filter', false, 0, '{}'::jsonb),
            ('dual_write_pg', false, 0, '{}'::jsonb)
        ON CONFLICT (name) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shared.feature_flags;")
    op.execute("DROP TABLE IF EXISTS shared.strategy_versions;")

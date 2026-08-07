"""Contrato da projeção SQLite → outbox → CDC → PG (correção 06/08).

Por que este arquivo existe: a auditoria de produção encontrou
`cw/ccw.spin_features` com `dealer='unknown'` em 100% das linhas e
`spin_seq`/`direction_*`/`centro_previsto`/`gale_level` NULL em 100% — com as
colunas de destino existindo desde as migrations 0007/0009/0010/0012. Nenhum
teste falhava, porque nenhum teste amarrava as três pontas:

  manifest (o que DEVE propagar) ↔ produtor (o que EMITE) ↔ worker (onde GRAVA)

Estes testes são determinísticos e NÃO exigem PostgreSQL: se alguém remover uma
chave do contexto no produtor, tirar uma coluna do mapa do worker ou trocar o
alias `dealer_table -> "table"`, a suíte quebra no CI comum.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from database.outbox_integration import (
    PG_FEATURE_CONTEXT_KEYS, build_pg_feature_context,
)
from workers.cdc_worker import CONTEXT_COLUMN_KINDS, CONTEXT_COLUMN_MAP

REPO = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((REPO / "database" / "schema_parity_manifest.json").read_text(encoding="utf-8"))
PROJECTION = MANIFEST["pg_projection_map"]["decisions"]
MIGRATIONS = REPO / "migrations" / "versions"

# Colunas que só existem no PG por causa do contexto (o worker as escreve).
CONTEXT_ENTRIES = {
    col: entry for col, entry in PROJECTION.items()
    if entry.get("via") == "context"
}


def _fully_populated_source() -> dict:
    """Fonte com TODOS os campos preenchidos e plausíveis."""
    return {
        "id": 4242,
        "session_id": "sess-abc",
        "dealer": "Ana",
        "dealer_table": "Roleta ao Vivo",
        "provider": "Evolution",
        "round_id": "r-991",
        "wheel_model": "Roleta ao Vivo",
        "vision_confidence": 0.87,
        "vision_source": "vision",
        "spin_seq": 31,
        "direction_source": "authority",
        "direction_confidence": 0.91,
        "direction_next": "anti-horario",
        "phase_uncertain": False,
        "sda_center": 17,
        "gale_level": 2,
    }


# ---------------------------------------------------------------------------
# manifest ↔ produtor
# ---------------------------------------------------------------------------

def test_every_context_entry_has_a_producer_key():
    """Cada coluna projetada via contexto é EMITIDA pelo produtor."""
    for col, entry in CONTEXT_ENTRIES.items():
        key = entry["context_key"]
        assert key in PG_FEATURE_CONTEXT_KEYS, (
            f"manifest declara {col} -> contexto['{key}'], mas a chave nao esta "
            f"em PG_FEATURE_CONTEXT_KEYS do produtor"
        )


def test_producer_emits_every_declared_key_with_a_real_value():
    """O produtor emite valor NÃO-nulo para toda chave declarada.

    Prova mais forte que 'a chave existe': se alguém normalizar demais e zerar um
    campo legítimo, este teste denuncia.
    """
    ctx = build_pg_feature_context(_fully_populated_source())
    assert ctx is not None
    for col, entry in CONTEXT_ENTRIES.items():
        key = entry["context_key"]
        assert key in ctx, f"produtor nao emite a chave '{key}' ({col})"
        assert ctx[key] is not None, (
            f"produtor emite '{key}' ({col}) como None mesmo com fonte completa"
        )


def test_producer_key_set_is_exactly_the_declared_contract():
    """Nem chave a mais, nem a menos, entre PG_FEATURE_CONTEXT_KEYS e o mapa."""
    declared = {e["context_key"] for e in CONTEXT_ENTRIES.values()}
    assert declared == set(PG_FEATURE_CONTEXT_KEYS), (
        f"so no manifest: {sorted(declared - set(PG_FEATURE_CONTEXT_KEYS))}; "
        f"so no produtor: {sorted(set(PG_FEATURE_CONTEXT_KEYS) - declared)}"
    )


# ---------------------------------------------------------------------------
# manifest ↔ worker
# ---------------------------------------------------------------------------

def test_worker_map_matches_manifest_columns():
    """Cada chave do contexto grava na coluna PG declarada no manifest."""
    worker_map = dict(CONTEXT_COLUMN_MAP)
    for col, entry in CONTEXT_ENTRIES.items():
        key = entry["context_key"]
        pg_column = entry["pg_column"]
        if key in ("centro_previsto", "applied_gale_level"):
            # Colunas BASE do INSERT (já existiam); o contexto só as preenche.
            assert key not in worker_map, (
                f"{key} nao deve entrar no mapa de colunas extras (ja e base)"
            )
            continue
        assert key in worker_map, f"worker nao projeta a chave '{key}' ({col})"
        assert worker_map[key] == _sql_ident(pg_column), (
            f"{key}: worker grava em {worker_map[key]!r}, manifest declara "
            f"{pg_column!r}"
        )


def _sql_ident(column: str) -> str:
    """`table` é palavra reservada e vai citada no SQL; as demais, não."""
    return '"table"' if column == "table" else column


def test_dealer_table_maps_to_quoted_table_column():
    """Regressão dedicada: o alias mais perigoso do mapa.

    `dealer_table` (SQLite) → coluna PG `table` (palavra reservada). Sem as aspas
    o INSERT vira erro de sintaxe; com o nome errado, a mesa some.
    """
    assert dict(CONTEXT_COLUMN_MAP)["dealer_table"] == '"table"'
    assert PROJECTION["dealer_table"]["pg_column"] == "table"


def test_worker_never_projects_spin_number():
    """`spin_number` no PG é o número REAL do resultado — nunca vem do contexto."""
    assert "spin_number" not in dict(CONTEXT_COLUMN_MAP)
    assert "spin_number" not in PG_FEATURE_CONTEXT_KEYS


def test_every_worker_column_has_a_declared_coercion():
    for key, _column in CONTEXT_COLUMN_MAP:
        assert key in CONTEXT_COLUMN_KINDS, f"sem coercao declarada para '{key}'"


# ---------------------------------------------------------------------------
# manifest ↔ migrations (o destino existe de fato)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def migrations_text() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("*.py"))
    )


def test_every_projected_column_exists_in_some_migration(migrations_text):
    """Nenhuma coluna de destino é inventada: alguma migration a cria.

    Vale para as colunas de contexto E para as colunas base tocadas por elas.
    """
    expected = {e["pg_column"] for e in PROJECTION.values() if e.get("pg_column")}
    for column in sorted(expected):
        pattern = rf'(?<![\w"]){re.escape(column)}(?![\w])'
        assert re.search(pattern, migrations_text), (
            f"coluna de destino {column!r} nao aparece em migrations/versions/*.py"
        )


def test_context_columns_are_added_by_the_expected_migrations():
    """Amarra as colunas de contexto às migrations que as criaram (0007/0009/0010)."""
    by_file = {
        "0007_deal_dealer_table.py": {"dealer", '"table"', "provider", "round_id"},
        "0009_vision_features.py": {"wheel_model", "vision_confidence", "vision_source"},
        "0010_dir3_phase_columns.py": {
            "spin_seq", "direction_source", "direction_confidence",
            "direction_next", "phase_uncertain",
        },
    }
    for filename, columns in by_file.items():
        text = (MIGRATIONS / filename).read_text(encoding="utf-8")
        for column in columns:
            assert column in text, f"{filename} deveria criar {column}"

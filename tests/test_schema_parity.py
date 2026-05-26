"""SP-04: schema parity SQLite <-> PG.

Objetivo: detectar drift de schema entre o que o SQLite cria (lado autoritativo
write-side) e o subset que precisa fluir para o PG via outbox (spin_features
em cw/ccw). Previne o tipo de bug onde uma coluna nova e adicionada em um
lado e silenciosamente perdida no outro (parente direto do B-10).

Estrategia:
  1. Snapshot SQLite vivo (PRAGMA table_info) — comparado a
     database/schema_sqlite_snapshot.json. Drift => FAIL (rode o
     snapshot tool e revise o manifest).
  2. Manifest database/schema_parity_manifest.json declara explicitamente:
       - must_propagate_to_pg: colunas SQLite que TEM que existir como
         destino PG (validado se ROLETA_PG_DSN setado);
       - sqlite_only_allowed / pg_only_allowed: whitelist consciente.
  3. Quando PG nao esta disponivel, valida apenas (1) + estrutura do
     manifest (cada must_propagate_to_pg item existe no SQLite).

Nao tenta gerar diff automatico — exige decisao humana ao mexer schema.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.sqlite_repo import SQLiteDecisionRepository

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO / "database" / "schema_sqlite_snapshot.json"
MANIFEST_PATH = REPO / "database" / "schema_parity_manifest.json"


def _live_sqlite_schema() -> dict:
    tmp = tempfile.mktemp(suffix=".db")
    SQLiteDecisionRepository(db_path=tmp)
    conn = sqlite3.connect(tmp)
    out: dict = {}
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    for tbl in tables:
        cols = [
            {"name": r[1], "type": (r[2] or "").upper()}
            for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()
        ]
        out[tbl] = sorted(cols, key=lambda c: c["name"])
    conn.close()
    return out


class TestSchemaParitySQLiteSnapshot(unittest.TestCase):
    """Parte 1: snapshot SQLite deve estar sincronizado com o vivo."""

    def test_snapshot_exists(self):
        self.assertTrue(
            SNAPSHOT_PATH.exists(),
            f"Snapshot ausente. Rode: python tools/snapshot_sqlite_schema.py > {SNAPSHOT_PATH}",
        )

    def test_snapshot_matches_live(self):
        snap = json.loads(SNAPSHOT_PATH.read_text())
        live = _live_sqlite_schema()
        snap_tables = set(snap.keys())
        live_tables = set(live.keys())
        self.assertEqual(
            snap_tables, live_tables,
            f"Drift de tabelas. Apenas snapshot: {snap_tables - live_tables}. "
            f"Apenas live: {live_tables - snap_tables}. "
            f"Rode `python tools/snapshot_sqlite_schema.py > {SNAPSHOT_PATH.name}` se intencional.",
        )
        for tbl in snap_tables:
            snap_cols = {(c["name"], c["type"]) for c in snap[tbl]}
            live_cols = {(c["name"], c["type"]) for c in live[tbl]}
            self.assertEqual(
                snap_cols, live_cols,
                f"Drift colunas em {tbl}. "
                f"Apenas snapshot: {snap_cols - live_cols}. "
                f"Apenas live: {live_cols - snap_cols}.",
            )


class TestSchemaParityManifest(unittest.TestCase):
    """Parte 2: manifest must_propagate_to_pg eh consistente com snapshot."""

    def setUp(self):
        self.manifest = json.loads(MANIFEST_PATH.read_text())
        self.snapshot = json.loads(SNAPSHOT_PATH.read_text())

    def test_must_propagate_columns_exist_in_sqlite(self):
        for tbl, cols in self.manifest["must_propagate_to_pg"].items():
            self.assertIn(tbl, self.snapshot, f"Tabela {tbl} no manifest mas nao no snapshot")
            snap_names = {c["name"] for c in self.snapshot[tbl]}
            for col in cols:
                self.assertIn(
                    col, snap_names,
                    f"must_propagate_to_pg: {tbl}.{col} ausente no SQLite real. "
                    f"Remova do manifest ou adicione a coluna.",
                )

    def test_sqlite_only_whitelist_is_subset(self):
        decisions_cols = {c["name"] for c in self.snapshot.get("decisions", [])}
        for col in self.manifest["sqlite_only_allowed"]:
            self.assertIn(
                col, decisions_cols,
                f"sqlite_only_allowed '{col}' nao existe em decisions — remova do manifest.",
            )


@unittest.skipUnless(
    os.environ.get("ROLETA_PG_DSN"),
    "PG nao disponivel (ROLETA_PG_DSN ausente)",
)
class TestSchemaParityPGLive(unittest.TestCase):
    """Parte 3: quando PG real disponivel, valida must_propagate_to_pg."""

    def test_pg_target_tables_contain_propagated_columns(self):
        try:
            import psycopg  # type: ignore
        except ImportError:
            self.skipTest("psycopg nao instalado")
        manifest = json.loads(MANIFEST_PATH.read_text())
        dsn = os.environ["ROLETA_PG_DSN"]
        try:
            conn = psycopg.connect(dsn, connect_timeout=3)
        except Exception as e:
            self.skipTest(f"PG inacessivel: {e}")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_schema, table_name, column_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema IN ('cw','ccw')"
                )
                pg_cols = {(r[0], r[1], r[2]) for r in cur.fetchall()}
        finally:
            conn.close()
        if not pg_cols:
            self.skipTest("Schemas cw/ccw vazios em PG")
        # Validacao: cada must_propagate_to_pg deve ter ALGUM destino em PG
        # (heuristica frouxa: nome de coluna deve aparecer em alguma das
        # pg_target_table; se faltar, o outbox/cdc deve ser revisado).
        targets = manifest.get("pg_target_table", {})
        for tbl, cols in manifest["must_propagate_to_pg"].items():
            target_specs = targets.get(tbl, [])
            available_cols = set()
            for spec in target_specs:
                schema, table = spec.split(".", 1)
                available_cols.update(
                    name for s, t, name in pg_cols if s == schema and t == table
                )
            if not available_cols:
                self.skipTest(f"PG targets {target_specs} ainda vazios")
            for col in cols:
                # Permite remapeamento por nome equivalente (hit vs result_hit)
                aliases = {col, col.replace("result_", ""), f"result_{col}"}
                self.assertTrue(
                    aliases & available_cols,
                    f"{tbl}.{col} deve propagar para {target_specs} mas nao encontrado "
                    f"(aliases tentados: {aliases})",
                )


if __name__ == "__main__":
    unittest.main()

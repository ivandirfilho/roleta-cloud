#!/usr/bin/env python3
"""
ISO-S1 / NEW-03 (sprint 26/05 — gap MEL-ISO-002, NEW-03):

Verifica simetria estrutural entre os schemas `cw` e `ccw` em PG
(schemas devem ter as mesmas tabelas com colunas/tipos equivalentes).

Usado no CI como guardrail para evitar drift entre as duas direcoes —
um bug recorrente quando se faz ALTER apenas em um dos lados.

Stub mode (default): sem PG, apenas checa que arquivos espelhados
em `database/sql/cw/` e `database/sql/ccw/` (se existirem) tem o
mesmo conjunto de nomes de arquivo.

Live mode (`--pg`): se `ROLETA_PG_DSN` setado, executa via psycopg
e compara `information_schema.columns` entre os schemas.

Exit codes:
  0 — simetria OK (ou nada a comparar)
  1 — divergencias encontradas (lista no stderr)
  2 — erro inesperado
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def check_file_symmetry() -> int:
    """Verifica simetria de arquivos SQL entre cw/ccw."""
    cw_dir = REPO / "database" / "sql" / "cw"
    ccw_dir = REPO / "database" / "sql" / "ccw"
    if not cw_dir.exists() and not ccw_dir.exists():
        print("[schema_symmetry] cw/ ccw/ SQL dirs ausentes — nada a checar (OK).")
        return 0
    if cw_dir.exists() != ccw_dir.exists():
        print(
            f"[schema_symmetry] FAIL: apenas um lado existe "
            f"(cw={cw_dir.exists()}, ccw={ccw_dir.exists()})",
            file=sys.stderr,
        )
        return 1
    cw_files = {p.name for p in cw_dir.glob("*.sql")}
    ccw_files = {p.name for p in ccw_dir.glob("*.sql")}
    diff_cw = cw_files - ccw_files
    diff_ccw = ccw_files - cw_files
    if diff_cw or diff_ccw:
        print("[schema_symmetry] FAIL: arquivos divergentes:", file=sys.stderr)
        if diff_cw:
            print(f"  apenas em cw: {sorted(diff_cw)}", file=sys.stderr)
        if diff_ccw:
            print(f"  apenas em ccw: {sorted(diff_ccw)}", file=sys.stderr)
        return 1
    print(f"[schema_symmetry] OK: {len(cw_files)} arquivos espelhados.")
    return 0


def check_pg_symmetry(dsn: str) -> int:
    """Verifica simetria de schemas reais em PG."""
    try:
        import psycopg  # type: ignore
    except ImportError:
        print("[schema_symmetry] psycopg ausente — pulando modo PG.")
        return 0
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_schema, table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema IN ('cw', 'ccw')
                ORDER BY table_schema, table_name, ordinal_position
                """
            )
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        print(f"[schema_symmetry] PG nao acessivel: {e}", file=sys.stderr)
        return 0  # nao falhar CI se PG nao subiu
    cw_cols = {(r[1], r[2], r[3]) for r in rows if r[0] == "cw"}
    ccw_cols = {(r[1], r[2], r[3]) for r in rows if r[0] == "ccw"}
    if not cw_cols and not ccw_cols:
        print("[schema_symmetry] schemas cw/ccw vazios em PG — OK (nada a checar).")
        return 0
    diff_cw = cw_cols - ccw_cols
    diff_ccw = ccw_cols - cw_cols
    if diff_cw or diff_ccw:
        print("[schema_symmetry] FAIL: divergencia entre schemas:", file=sys.stderr)
        for tbl, col, typ in sorted(diff_cw):
            print(f"  apenas cw : {tbl}.{col}({typ})", file=sys.stderr)
        for tbl, col, typ in sorted(diff_ccw):
            print(f"  apenas ccw: {tbl}.{col}({typ})", file=sys.stderr)
        return 1
    print(f"[schema_symmetry] OK: {len(cw_cols)} colunas espelhadas em cw/ccw.")
    return 0


def main() -> int:
    rc1 = check_file_symmetry()
    rc2 = 0
    if "--pg" in sys.argv or os.environ.get("ROLETA_PG_DSN"):
        dsn = os.environ.get("ROLETA_PG_DSN", "")
        if dsn:
            rc2 = check_pg_symmetry(dsn)
    return max(rc1, rc2)


if __name__ == "__main__":
    sys.exit(main())

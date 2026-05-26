"""SP-04 helper: dump SQLite schema atual como JSON."""
from __future__ import annotations
import json, sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.sqlite_repo import SQLiteDecisionRepository as SQLiteRepository  # noqa: E402


def snapshot() -> dict:
    tmp = tempfile.mktemp(suffix=".db")
    SQLiteRepository(db_path=tmp)
    conn = sqlite3.connect(tmp)
    out = {}
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
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


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2, sort_keys=True))

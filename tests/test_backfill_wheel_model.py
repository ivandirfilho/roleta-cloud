"""Tests — tool de backfill/canonicalização de wheel_model (auditoria §7.3).

Garante: dry-run não altera o DB; --apply canoniza variantes legado p/ o mesmo
valor de runtime (server.vision_ocr._norm_model); idempotência (2ª passada = 0).
"""
import os
import sqlite3
import tempfile

import pytest

from tools.backfill_wheel_model import backfill


@pytest.fixture
def seeded_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from database.sqlite_repo import SQLiteDecisionRepository
    SQLiteDecisionRepository(db_path=path)
    conn = sqlite3.connect(path)
    rows = [
        ("Roleta aoVivo",) ,   # legado -> 'Roleta ao Vivo'
        ("Roleta aoVivo",),
        ("RoletaaoVivo",),     # legado -> 'Roleta ao Vivo'
        ("Roleta ao Vivo",),   # já canônico (não candidato)
        ("",),                  # vazio (ignorado)
    ]
    conn.executemany("INSERT INTO decisions (wheel_model) VALUES (?)", rows)
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def _values(path):
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute(
            "SELECT wheel_model FROM decisions ORDER BY id"
        ).fetchall()]
    finally:
        conn.close()


def test_dry_run_does_not_change_db(seeded_db):
    before = _values(seeded_db)
    stats = backfill(seeded_db, apply=False)
    assert stats["candidates"] == 3
    assert stats["applied"] == 0
    assert _values(seeded_db) == before  # inalterado


def test_apply_canonicalizes_and_is_idempotent(seeded_db):
    stats = backfill(seeded_db, apply=True)
    assert stats["candidates"] == 3
    assert stats["applied"] == 3
    vals = _values(seeded_db)
    # as 3 variantes legado viraram o canônico; a já-canônica e o vazio intactos
    assert vals.count("Roleta ao Vivo") == 4
    assert "" in vals
    assert "Roleta aoVivo" not in vals and "RoletaaoVivo" not in vals
    # idempotente: rodar de novo não encontra candidatos
    stats2 = backfill(seeded_db, apply=True)
    assert stats2["candidates"] == 0 and stats2["applied"] == 0

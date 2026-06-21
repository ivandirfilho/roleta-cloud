"""Tests — consumidor dormante dealer_force_profile (auditoria_pos_foto §7.5).

Valida o gate n≥30, o filtro por dealer/sentido/modelo, e a degradação graciosa
(dealer 'unknown' / DB ausente -> {}). Mesma convenção de seed do
test_vision_features.py (repo init cria o schema; inserts diretos em decisions).
"""
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

from strategies import dealer_force_profile as dfp


@pytest.fixture
def seeded_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # repo init cria o schema decisions (+ auto-migrações de dealer/wheel/vision)
    from database.sqlite_repo import SQLiteDecisionRepository
    SQLiteDecisionRepository(db_path=path)

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn = sqlite3.connect(path)
    rows = []
    # 35 giros de LEVI/horario com força variando (n>=30) — modal=10
    for i in range(35):
        force = 10 if i < 20 else (15 if i < 30 else 25)
        rows.append(("LEVI", "horario", "Roleta ao Vivo", force, now))
    # 5 giros de ANNA (n<30 -> deve retornar {})
    for _ in range(5):
        rows.append(("ANNA", "horario", "Roleta ao Vivo", 12, now))
    # ruído: unknown + força 0 (deve ser ignorado nos agregados)
    for _ in range(40):
        rows.append(("unknown", "horario", "", 0, now))
    conn.executemany(
        "INSERT INTO decisions (dealer, spin_direction, wheel_model, spin_force, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_profile_returns_for_n_ge_30(seeded_db):
    p = dfp.force_profile(seeded_db, "LEVI", "horario")
    assert p["n"] == 35
    assert p["modal_force"] == 10
    assert p["min_force"] == 10 and p["max_force"] == 25
    # média = (20*10 + 10*15 + 5*25) / 35 = (200+150+125)/35 = 13.57
    assert 13.5 <= p["avg_force"] <= 13.6
    assert p["dealer"] == "LEVI" and p["direction"] == "horario"


def test_profile_below_threshold_returns_empty(seeded_db):
    assert dfp.force_profile(seeded_db, "ANNA", "horario") == {}


def test_profile_unknown_dealer_returns_empty(seeded_db):
    assert dfp.force_profile(seeded_db, "unknown", "horario") == {}
    assert dfp.force_profile(seeded_db, "", "horario") == {}


def test_profile_wheel_model_filter(seeded_db):
    # modelo inexistente -> sem linhas -> {}
    assert dfp.force_profile(seeded_db, "LEVI", "horario", wheel_model="Lightning") == {}
    # modelo correto -> bate
    p = dfp.force_profile(seeded_db, "LEVI", "horario", wheel_model="Roleta ao Vivo")
    assert p and p["wheel_model"] == "Roleta ao Vivo" and p["n"] == 35


def test_profile_missing_db_is_graceful():
    assert dfp.force_profile("/path/does/not/exist.db", "LEVI", "horario") == {}


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("SDA_DEALER_FORCE_PROFILE", raising=False)
    assert dfp.is_enabled() is False
    monkeypatch.setenv("SDA_DEALER_FORCE_PROFILE", "1")
    assert dfp.is_enabled() is True

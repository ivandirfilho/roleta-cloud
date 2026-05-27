"""Tests SP-11..15 DEAL series (27/05)."""
import os
import sqlite3
import importlib
import tempfile
import pytest


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try: os.unlink(path)
    except OSError: pass


def _make_decisions_table(path):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE decisions (
          id INTEGER PRIMARY KEY,
          timestamp TEXT,
          dealer TEXT, provider TEXT, dealer_table TEXT, round_id TEXT,
          spin_direction TEXT,
          sda_offset INTEGER DEFAULT 0,
          final_action TEXT,
          result_actual INTEGER,
          result_hit INTEGER
        )
    """)
    conn.commit()
    conn.close()


def test_sp12_spininput_accepts_dealer_fields():
    from models.input import SpinInput
    s = SpinInput(numero=17, direcao="horario", trace_id="t1234",
                  t_client=1, dealer="Alice", table="MZ-01",
                  provider="evolution", round_id="r-xyz")
    assert s.dealer == "Alice"
    assert s.provider == "evolution"
    # backwards compatible: payload antigo sem campos extras
    s2 = SpinInput(numero=0, direcao="anti-horario", trace_id="abcd", t_client=1)
    assert s2.dealer is None and s2.provider is None


def test_sp14_dealer_stats_empty_when_no_table(tmp_db):
    # repo recem criado, sem decisoes → lista vazia, sem raise
    from database.sqlite_repo import SQLiteDecisionRepository
    repo = SQLiteDecisionRepository(db_path=tmp_db)
    assert repo.dealer_stats(window_minutes=60) == []


def test_sp14_dealer_stats_ranks_by_hit_rate(tmp_db):
    from database.sqlite_repo import SQLiteDecisionRepository
    repo = SQLiteDecisionRepository(db_path=tmp_db)  # cria schema oficial
    conn = sqlite3.connect(tmp_db)
    def ins(dealer, hit):
        conn.execute(
            "INSERT INTO decisions(timestamp,session_id,spin_number,spin_direction,"
            "final_action,result_actual,result_hit,dealer,provider) "
            "VALUES(datetime('now'),'s1',17,'horario','APOSTAR',17,?,?, 'evolution')",
            (hit, dealer),
        )
    # Alice: 10 spins, 8 hits = 0.8
    for i in range(10): ins('Alice', 1 if i < 8 else 0)
    # Bob: 12 spins, 4 hits = 0.33
    for i in range(12): ins('Bob', 1 if i < 4 else 0)
    # Carl: 5 spins (n < 10) → filtrado
    for _ in range(5): ins('Carl', 1)
    conn.commit(); conn.close()

    rows = repo.dealer_stats(window_minutes=60)
    assert len(rows) == 2
    assert rows[0]["dealer"] == "Alice"
    assert rows[0]["hit_rate"] == 0.8
    assert rows[1]["dealer"] == "Bob"
    assert all(r["dealer"] != "Carl" for r in rows)


def test_sp15_dealer_offset_requires_min_n(tmp_db):
    from database.sqlite_repo import SQLiteDecisionRepository
    SQLiteDecisionRepository(db_path=tmp_db)  # cria schema com dealer column
    from strategies.dealer_offset import preferred_offset, is_enabled
    assert is_enabled() is False
    assert preferred_offset(tmp_db, "unknown") is None
    conn = sqlite3.connect(tmp_db)
    for _ in range(5):
        conn.execute(
            "INSERT INTO decisions(timestamp,session_id,spin_number,spin_direction,"
            "sda_offset,result_hit,dealer) VALUES(datetime('now'),'s1',17,'horario',3,1,'Diana')"
        )
    conn.commit(); conn.close()
    assert preferred_offset(tmp_db, "Diana") is None


def test_sp15_dealer_offset_returns_mode_when_enough(tmp_db):
    from database.sqlite_repo import SQLiteDecisionRepository
    SQLiteDecisionRepository(db_path=tmp_db)
    conn = sqlite3.connect(tmp_db)
    for _ in range(25):
        conn.execute(
            "INSERT INTO decisions(timestamp,session_id,spin_number,spin_direction,"
            "sda_offset,result_hit,dealer) VALUES(datetime('now'),'s1',17,'horario',2,1,'Eve')"
        )
    for _ in range(10):
        conn.execute(
            "INSERT INTO decisions(timestamp,session_id,spin_number,spin_direction,"
            "sda_offset,result_hit,dealer) VALUES(datetime('now'),'s1',17,'horario',5,1,'Eve')"
        )
    conn.commit(); conn.close()
    from strategies.dealer_offset import preferred_offset
    assert preferred_offset(tmp_db, "Eve", direction="horario") == 2


def test_sp15_flag_toggle(monkeypatch):
    from strategies import dealer_offset
    monkeypatch.setenv("SDA_DEALER_OFFSET", "1")
    importlib.reload(dealer_offset)
    assert dealer_offset.is_enabled() is True
    monkeypatch.setenv("SDA_DEALER_OFFSET", "0")
    importlib.reload(dealer_offset)
    assert dealer_offset.is_enabled() is False

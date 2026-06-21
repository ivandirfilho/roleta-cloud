"""Tests — hardening da associação foto->decisão (auditoria §7.4).

update_last_vision aceita uma janela máxima opcional (SDA_VISION_ATTACH_MAX_AGE_S):
- default 0 = sem limite (comportamento atual, byte-idêntico): cola mesmo em
  decisão antiga;
- >0: NÃO cola se a última decisão é mais velha que a janela (anti cross-spin).
"""
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from database.sqlite_repo import SQLiteDecisionRepository


def _iso(dt):
    return dt.replace(tzinfo=None).isoformat(sep=" ")


@pytest.fixture
def repo_with_decision():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    repo = SQLiteDecisionRepository(db_path=path)

    def _insert(ts):
        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT INTO decisions (spin_number, spin_direction, timestamp) VALUES (?, ?, ?)",
            (5, "horario", ts),
        )
        conn.commit()
        conn.close()

    def _dealer(path_):
        conn = sqlite3.connect(path_)
        try:
            return conn.execute(
                "SELECT dealer FROM decisions ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        finally:
            conn.close()

    yield repo, path, _insert, _dealer
    try:
        os.unlink(path)
    except OSError:
        pass


def test_default_no_limit_attaches_even_if_old(repo_with_decision, monkeypatch):
    repo, path, insert, dealer = repo_with_decision
    monkeypatch.delenv("SDA_VISION_ATTACH_MAX_AGE_S", raising=False)
    insert(_iso(datetime.now(timezone.utc) - timedelta(hours=2)))  # decisão antiga
    did = repo.update_last_vision(dealer="LEVI", source="vision")
    assert did > 0
    assert dealer(path) == "LEVI"


def test_age_limit_skips_old_decision(repo_with_decision, monkeypatch):
    repo, path, insert, dealer = repo_with_decision
    monkeypatch.setenv("SDA_VISION_ATTACH_MAX_AGE_S", "10")
    insert(_iso(datetime.now(timezone.utc) - timedelta(hours=2)))  # 2h > 10s
    did = repo.update_last_vision(dealer="LEVI", source="vision")
    assert did == 0                       # não colou
    assert dealer(path) == "unknown"      # decisão intacta (default, não virou LEVI)


def test_age_limit_attaches_recent_decision(repo_with_decision, monkeypatch):
    repo, path, insert, dealer = repo_with_decision
    monkeypatch.setenv("SDA_VISION_ATTACH_MAX_AGE_S", "3600")
    insert(_iso(datetime.now(timezone.utc)))  # recente
    did = repo.update_last_vision(dealer="STEFANY", source="vision")
    assert did > 0
    assert dealer(path) == "STEFANY"

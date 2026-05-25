"""S-STRAT-8 — testes unitários do handler spin_result e do FeatureStoreReader.

Usa cursor mock para validar SQL/parâmetros sem precisar de PG real.
"""
from __future__ import annotations

from typing import Any

import pytest

from workers import cdc_worker
from database.feature_store import FeatureStoreReader


class _FakeCursor:
    def __init__(self, fetch_rows: list[dict[str, Any]] | None = None):
        self._rows = fetch_rows or []
        self.executions: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executions.append((sql, params))

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


# ---------- handler spin_result ----------

def test_spin_result_handler_inserts_with_zero_lags_when_empty(monkeypatch):
    cur = _FakeCursor(fetch_rows=[])
    payload = {
        "event_type": "spin_result",
        "direction": "cw",
        "decision_id": 42,
        "hit": True,
        "actual_number": 17,
        "meta": {"spin_number": 17, "centro_previsto": 18, "applied_gale_level": 0},
    }
    cdc_worker._apply_spin_result(cur, payload)

    # 1ª query lê janela; 2ª insere.
    assert len(cur.executions) == 2
    select_sql, _ = cur.executions[0]
    assert "FROM cw.spin_features" in select_sql
    insert_sql, insert_params = cur.executions[1]
    assert "INSERT INTO cw.spin_features" in insert_sql
    # params: decision_id, spin_number, hit, centro, gale, acc10, acc50, sm, sh, last20, meta
    assert insert_params[0] == 42
    assert insert_params[1] == 17
    assert insert_params[2] is True
    assert insert_params[3] == 18
    assert insert_params[4] == 0
    assert insert_params[5] is None  # acc_10 None quando sem histórico
    assert insert_params[6] is None
    assert insert_params[7] == 0  # streak_miss
    assert insert_params[8] == 0  # streak_hit
    assert insert_params[9] == [True]  # last_20 contém apenas o spin atual


def test_spin_result_handler_computes_lag_features():
    # Histórico: hit, hit, miss, hit, miss, miss, miss (mais recente primeiro)
    rows = [
        {"hit": True}, {"hit": True}, {"hit": False},
        {"hit": True}, {"hit": False}, {"hit": False}, {"hit": False},
    ]
    cur = _FakeCursor(fetch_rows=rows)
    payload = {
        "event_type": "spin_result",
        "direction": "ccw",
        "decision_id": 99,
        "hit": False,
        "actual_number": 7,
        "meta": {"spin_number": 7},
    }
    cdc_worker._apply_spin_result(cur, payload)

    _, params = cur.executions[1]
    # streak_hit antes deste spin = 2 (head=hit,hit,miss,...)
    assert params[8] == 2  # streak_hit
    assert params[7] == 0  # streak_miss (não há miss antes do hit head)
    # acc_50 = 3/7
    assert params[6] == pytest.approx(3 / 7)
    # acc_10 = 3/7 (apenas 7 disponíveis)
    assert params[5] == pytest.approx(3 / 7)
    # last_20 começa com o spin atual (False) seguido dos 7 históricos
    assert params[9][0] is False
    assert len(params[9]) == 8


def test_spin_result_handler_rejects_invalid_direction():
    cur = _FakeCursor()
    with pytest.raises(ValueError, match="invalid direction"):
        cdc_worker._apply_spin_result(cur, {"direction": "xy", "hit": True})


def test_spin_result_handler_rejects_non_bool_hit():
    cur = _FakeCursor()
    with pytest.raises(ValueError, match="hit must be bool"):
        cdc_worker._apply_spin_result(cur, {"direction": "cw", "hit": "yes"})


def test_spin_result_streak_miss_counted_when_head_is_miss():
    rows = [{"hit": False}, {"hit": False}, {"hit": False}, {"hit": True}]
    cur = _FakeCursor(fetch_rows=rows)
    cdc_worker._apply_spin_result(cur, {"direction": "cw", "hit": True, "meta": {}})
    _, params = cur.executions[1]
    assert params[7] == 3  # streak_miss
    assert params[8] == 0  # streak_hit


# ---------- FeatureStoreReader ----------

def test_feature_store_reader_rejects_invalid_direction():
    r = FeatureStoreReader(dsn=None)
    with pytest.raises(ValueError):
        r.get_latest("xy")
    with pytest.raises(ValueError):
        r.get_window("xy")


def test_feature_store_reader_get_latest_returns_none_when_no_dsn():
    r = FeatureStoreReader(dsn=None)
    assert r.get_latest("cw") is None
    assert r.get_window("cw") == []


def test_feature_store_reader_get_window_validates_limit():
    r = FeatureStoreReader(dsn=None)
    with pytest.raises(ValueError):
        r.get_window("cw", limit=0)
    with pytest.raises(ValueError):
        r.get_window("cw", limit=1001)


# ---------- HANDLERS registry ----------

def test_handlers_registry_has_spin_result():
    assert "spin_result" in cdc_worker.HANDLERS
    assert cdc_worker.HANDLERS["spin_result"] is cdc_worker._apply_spin_result

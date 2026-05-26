"""NEW-08 (26/05/2026) — piso configuravel opt-in para sda_thr.

Lição da auditoria NEW-06: commit f24f9a6 (24/05) tornou sda_thr decrescente
com volatility, permitindo que o KILL switch quase nunca dispare em regimes
erráticos (sda_thr=2 → mata só se sda_score<2, quase nunca). Esta sprint
introduz piso configurável via env `BET_SDA_FLOOR` (default 2 = no-op).

Permite operador endurecer kill switch sem code-deploy enquanto coletamos
mais dados pós-B-09.
"""
from __future__ import annotations

import pytest

from state.bet_advisor import TripleRateAdvisor


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BET_SDA_FLOOR", raising=False)
    yield


def test_sda_floor_default_is_min():
    a = TripleRateAdvisor()
    assert a._blacklist_sda_floor == TripleRateAdvisor.KILL_V4_SDA_MIN


def test_sda_floor_env_parsed(monkeypatch):
    monkeypatch.setenv("BET_SDA_FLOOR", "3")
    a = TripleRateAdvisor()
    assert a._blacklist_sda_floor == 3


def test_sda_floor_clamped_to_max(monkeypatch):
    monkeypatch.setenv("BET_SDA_FLOOR", "99")
    a = TripleRateAdvisor()
    assert a._blacklist_sda_floor == TripleRateAdvisor.KILL_V4_SDA_MAX


def test_sda_floor_clamped_to_min(monkeypatch):
    monkeypatch.setenv("BET_SDA_FLOOR", "-5")
    a = TripleRateAdvisor()
    assert a._blacklist_sda_floor == TripleRateAdvisor.KILL_V4_SDA_MIN


def test_sda_floor_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("BET_SDA_FLOOR", "abc")
    a = TripleRateAdvisor()
    assert a._blacklist_sda_floor == TripleRateAdvisor.KILL_V4_SDA_MIN


def test_kill_stats_exposes_sda_floor():
    a = TripleRateAdvisor()
    stats = a.get_kill_stats()
    assert stats["blacklist"]["sda_floor"] == TripleRateAdvisor.KILL_V4_SDA_MIN


def test_sda_floor_3_raises_threshold(monkeypatch):
    """Com piso=3, threshold final nunca cai abaixo de 3 (vs default 2)."""
    monkeypatch.setenv("BET_SDA_FLOOR", "3")
    a = TripleRateAdvisor()
    # Performance longa para entrar no caminho dinamico
    perf = [True, False] * 20
    a.analyze(perf, sda_score=4, direction="cw")
    # Apos analyze, _kill_thr_sda deve respeitar piso=3
    for dk in ("cw",):
        assert a._kill_thr_sda[dk] >= 3, (
            f"sda_thr[{dk}]={a._kill_thr_sda[dk]} viola piso=3"
        )

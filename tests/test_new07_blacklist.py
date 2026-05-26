"""NEW-07 (26/05/2026) — blacklist defensiva opt-in no bet_advisor.

Backtest counterfactual em prod (48h, 1282 APOSTAR) mostrou que duas
branches `tr_reason` tinham hr <40% sustentado:
- "AGRESSIVO 25%<33%" → 36.84% (n=133)
- "COLD com SDA=4"   → 36.84% (n=57)
Filtrando ambos: hr 45.55% → 47.07% (+1.52pp), volume -15%.

Este teste blinda:
1. Feature flag default OFF (zero impacto sem env var).
2. Pattern A (AGRESSIVO baixo) detectado e PULAR retornado.
3. Pattern B (COLD+SDA=4) detectado e PULAR retornado.
4. Branches saudáveis (CRESCENTE/ESTÁVEL) NÃO sao bloqueadas.
5. Counter dedicado incrementa (separado de _kill_pulls_total).
"""
from __future__ import annotations

import os

import pytest

from state.bet_advisor import TripleRateAdvisor


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BET_BLACKLIST_ENABLED", raising=False)
    yield


def _perf_aggressive_25_33():
    """Gera performance que produz c4=25%, m6=33%, c4<m6 (pattern A)."""
    # últimos 4: 1 hit, 3 miss → c4=0.25
    # últimos 6: 2 hit, 4 miss → m6=0.333
    # ordem cronológica (mais recente = ultimo)
    return [False, True, False, False, False, True]


def _perf_cold():
    """c4=0, c4=0, sda_score=4 (pattern B)."""
    return [False, False, False, False]


def _perf_growing():
    """CRESCENTE saudável: c4>=m6>=l12, c4>0."""
    return [True, True, True, True, False, True, False, False, True, False,
            False, False]


def test_blacklist_default_off_does_not_filter():
    """Sem env: pattern A passa normalmente como APOSTAR."""
    a = TripleRateAdvisor()
    assert a._blacklist_enabled is False
    advice = a.analyze(_perf_aggressive_25_33(), sda_score=4, direction="cw")
    assert advice.should_bet is True
    assert "blacklist" not in advice.reason.lower()


def test_blacklist_on_filters_aggressive_pattern(monkeypatch):
    monkeypatch.setenv("BET_BLACKLIST_ENABLED", "1")
    a = TripleRateAdvisor()
    assert a._blacklist_enabled is True
    advice = a.analyze(_perf_aggressive_25_33(), sda_score=4, direction="cw")
    assert advice.should_bet is False
    assert "NEW-07" in advice.reason
    assert "AGRESSIVO" in advice.reason
    assert a._blacklist_kills_total == 1


def test_blacklist_on_filters_cold_sda4(monkeypatch):
    monkeypatch.setenv("BET_BLACKLIST_ENABLED", "true")
    a = TripleRateAdvisor()
    advice = a.analyze(_perf_cold(), sda_score=4, direction="cw")
    assert advice.should_bet is False
    assert "COLD+SDA=4" in advice.reason
    assert a._blacklist_kills_total == 1


def test_blacklist_on_does_not_kill_healthy(monkeypatch):
    """CRESCENTE com c4 alto NÃO é blacklisted mesmo com flag ON."""
    monkeypatch.setenv("BET_BLACKLIST_ENABLED", "1")
    a = TripleRateAdvisor()
    advice = a.analyze(_perf_growing(), sda_score=4, direction="cw")
    assert advice.should_bet is True
    assert a._blacklist_kills_total == 0


def test_blacklist_on_does_not_kill_cold_sda5(monkeypatch):
    """COLD com SDA=5 (alto) NÃO é blacklisted — apenas SDA=4 borderline."""
    monkeypatch.setenv("BET_BLACKLIST_ENABLED", "1")
    a = TripleRateAdvisor()
    advice = a.analyze(_perf_cold(), sda_score=5, direction="cw")
    assert advice.should_bet is True
    assert a._blacklist_kills_total == 0


def test_kill_stats_exposes_blacklist_state(monkeypatch):
    monkeypatch.setenv("BET_BLACKLIST_ENABLED", "1")
    a = TripleRateAdvisor()
    stats = a.get_kill_stats()
    assert "blacklist" in stats
    assert stats["blacklist"]["enabled"] is True
    assert stats["blacklist"]["kills_total"] == 0
    a.analyze(_perf_cold(), sda_score=4, direction="cw")
    stats2 = a.get_kill_stats()
    assert stats2["blacklist"]["kills_total"] == 1


def test_blacklist_truthy_values_parsed(monkeypatch):
    """env aceita 1, true, yes, on (case-insensitive)."""
    for val in ("1", "true", "TRUE", "yes", "On"):
        monkeypatch.setenv("BET_BLACKLIST_ENABLED", val)
        assert TripleRateAdvisor()._blacklist_enabled is True
    for val in ("0", "false", "no", "", "off"):
        monkeypatch.setenv("BET_BLACKLIST_ENABLED", val)
        assert TripleRateAdvisor()._blacklist_enabled is False

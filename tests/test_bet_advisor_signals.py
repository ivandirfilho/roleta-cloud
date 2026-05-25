"""S-STRAT-8 + S-STRAT-12 — testes da integração opt-in no bet_advisor.

Garante:
- Sem readers: BetAdvice.feature_signal / regime_signal = None; to_dict não
  expõe as chaves (backward-compat).
- Reader que retorna < MIN_FEATURE_ROWS: feature_signal = None.
- Reader saudável: feature_signal populado e to_dict expõe a chave.
- regime_reader sem query_vec → None.
- Exceção em qualquer reader → None (falha-aberta, nunca derruba advisor).
- should_bet NÃO é alterado pelos sinais (gate de risco continua igual).
"""
from __future__ import annotations

import pytest

from state.bet_advisor import TripleRateAdvisor


class _FakeFeatureReader:
    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def get_window(self, direction, limit=50):
        self.calls += 1
        return self._rows[:limit]


class _FakeRegimeReader:
    def __init__(self, score):
        self._score = score
        self.calls = 0

    def regime_score(self, direction, query_vec, limit=20):
        self.calls += 1
        return self._score


def _perf_mix(n=10):
    # alterna hit/miss → não dispara KILL
    return [(i % 2 == 0) for i in range(n)]


def test_no_readers_keeps_backward_compat():
    advice = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction="cw")
    assert advice.feature_signal is None
    assert advice.regime_signal is None
    d = advice.to_dict()
    assert "feature_signal" not in d
    assert "regime_signal" not in d


def test_feature_signal_blocked_below_threshold():
    reader = _FakeFeatureReader([{"hit": True, "recent_acc_10": 0.5,
                                  "recent_acc_50": 0.5, "streak_miss": 0,
                                  "streak_hit": 1}] * 10)  # < 50 rows
    advice = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction="cw",
                                         feature_reader=reader)
    assert advice.feature_signal is None
    assert reader.calls == 1


def test_feature_signal_emitted_when_enough_data():
    rows = []
    for i in range(60):
        rows.append({
            "hit": (i % 2 == 0),
            "recent_acc_10": 0.5,
            "recent_acc_50": 0.48,
            "streak_miss": 1,
            "streak_hit": 0,
        })
    reader = _FakeFeatureReader(rows)
    advice = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction="cw",
                                         feature_reader=reader)
    fs = advice.feature_signal
    assert fs is not None
    assert fs["source"] == "spin_features"
    assert fs["direction"] == "cw"
    assert fs["rows"] == 50
    assert 0.0 <= fs["window_hit_rate"] <= 1.0
    assert "feature_signal" in advice.to_dict()


def test_regime_signal_requires_query_vec():
    reader = _FakeRegimeReader({"n": 20, "avg_distance": 0.1, "hit_rate": 0.55})
    a1 = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction="cw",
                                     regime_reader=reader)  # sem query_vec
    assert a1.regime_signal is None
    assert reader.calls == 0

    a2 = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction="cw",
                                     regime_reader=reader,
                                     query_vec=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert a2.regime_signal == {
        "source": "spins_vectors", "direction": "cw",
        "n": 20, "avg_distance": 0.1, "hit_rate": 0.55,
    }


def test_regime_signal_n_too_low_returns_none():
    reader = _FakeRegimeReader({"n": 3, "avg_distance": 0.1, "hit_rate": 1.0})
    a = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction="cw",
                                    regime_reader=reader,
                                    query_vec=[0.1] * 6)
    assert a.regime_signal is None


def test_reader_exception_is_swallowed():
    class _Boom:
        def get_window(self, *a, **kw):
            raise RuntimeError("pg down")

        def regime_score(self, *a, **kw):
            raise RuntimeError("pg down")

    a = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction="cw",
                                    feature_reader=_Boom(),
                                    regime_reader=_Boom(),
                                    query_vec=[0.1] * 6)
    assert a.feature_signal is None
    assert a.regime_signal is None
    # advisor ainda funciona normalmente
    assert a.should_bet in (True, False)


def test_signals_do_not_change_should_bet():
    # KILL deve disparar (perf todo falso + sda baixo) mesmo com sinais opostos
    perf = [False] * 8
    reader = _FakeFeatureReader([{"hit": True, "recent_acc_10": 0.9,
                                  "recent_acc_50": 0.9, "streak_miss": 0,
                                  "streak_hit": 5}] * 60)
    advice = TripleRateAdvisor().analyze(perf, sda_score=1, direction="cw",
                                         feature_reader=reader)
    assert advice.should_bet is False  # KILL prevaleceu
    assert advice.feature_signal is not None  # sinal informativo presente


def test_invalid_direction_skips_signals():
    reader = _FakeFeatureReader([{"hit": True}] * 60)
    a = TripleRateAdvisor().analyze(_perf_mix(), sda_score=4, direction=None,
                                    feature_reader=reader)
    assert a.feature_signal is None

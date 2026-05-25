"""S-STRAT-9 — testes unitários do backtest harness."""
from __future__ import annotations

import pytest

from tools.backtest_harness import (
    STRATEGIES,
    run_backtest,
    strategy_always_bet,
    strategy_skip_low_acc,
    strategy_skip_long_miss,
    strategy_skip_combo,
)


def _mkrow(hit: bool, acc10: float | None = 0.30, sm: int = 0, sh: int = 0) -> dict:
    return {"hit": hit, "recent_acc_10": acc10, "streak_miss": sm, "streak_hit": sh}


# ---------- strategies ----------

def test_always_bet_returns_true_for_anything():
    assert strategy_always_bet({}) is True


def test_skip_low_acc_skips_below_threshold():
    assert strategy_skip_low_acc(_mkrow(False, acc10=0.10)) is False
    assert strategy_skip_low_acc(_mkrow(False, acc10=0.25)) is True
    assert strategy_skip_low_acc(_mkrow(False, acc10=None)) is True  # cold start


def test_skip_long_miss_skips_at_3_consecutive():
    assert strategy_skip_long_miss(_mkrow(False, sm=2)) is True
    assert strategy_skip_long_miss(_mkrow(False, sm=3)) is False
    assert strategy_skip_long_miss(_mkrow(False, sm=10)) is False


def test_skip_combo_skips_if_either_condition():
    assert strategy_skip_combo(_mkrow(False, acc10=0.10, sm=0)) is False
    assert strategy_skip_combo(_mkrow(False, acc10=0.30, sm=4)) is False
    assert strategy_skip_combo(_mkrow(False, acc10=0.30, sm=0)) is True


def test_strategies_registry_complete():
    assert set(STRATEGIES.keys()) == {"always_bet", "skip_low_acc", "skip_long_miss", "skip_combo"}


# ---------- engine ----------

def test_run_backtest_empty_rows():
    r = run_backtest([], strategy_always_bet, "always_bet", "cw")
    assert r.total_bets == 0
    assert r.accuracy is None
    assert r.profit_units == 0


def test_run_backtest_all_hits_profit_positive():
    rows = [_mkrow(True) for _ in range(10)]
    r = run_backtest(rows, strategy_always_bet, "always_bet", "cw")
    assert r.total_bets == 10
    assert r.hits == 10
    assert r.accuracy == 1.0
    assert r.profit_units == 10  # 10 wins × stake 1 cada (gale resetando)
    assert r.max_drawdown_units == 0
    assert r.gale_level_dist["1"] == 10


def test_run_backtest_all_misses_max_loss_streak_and_gale_lost():
    rows = [_mkrow(False) for _ in range(8)]
    r = run_backtest(rows, strategy_always_bet, "always_bet", "ccw")
    assert r.misses == 8
    assert r.hits == 0
    # 4 misses esgotam gale (1+2+4+8 = 15 perdas), reset, mais 4 (1+2+4+8 = 15) → -30
    assert r.profit_units == -30
    assert r.gale_level_dist["lost"] == 2
    assert r.max_streak_loss == 8


def test_run_backtest_mixed_with_gale_recovery():
    # 3 losses (gale 1+2+4 = -7) seguido de 1 win em level 4 (+8) → +1 líquido
    rows = [_mkrow(False), _mkrow(False), _mkrow(False), _mkrow(True)]
    r = run_backtest(rows, strategy_always_bet, "always_bet", "cw")
    assert r.profit_units == 1
    assert r.gale_level_dist["4"] == 1  # 4º bet ganhou no level 4
    assert r.gale_level_dist["lost"] == 0
    assert r.max_streak_loss == 3


def test_run_backtest_skip_counts_correctly():
    # 5 rows com acc10 baixa → all skip
    rows = [_mkrow(True, acc10=0.05) for _ in range(5)]
    r = run_backtest(rows, strategy_skip_low_acc, "skip_low_acc", "cw")
    assert r.total_skips == 5
    assert r.total_bets == 0
    assert r.profit_units == 0


def test_run_backtest_accuracy_calculated_only_on_bets():
    rows = [
        _mkrow(True, acc10=0.30),    # bet → win
        _mkrow(False, acc10=0.05),   # skip (acc10 baixo)
        _mkrow(True, acc10=0.40),    # bet → win
        _mkrow(False, acc10=0.10),   # skip
    ]
    r = run_backtest(rows, strategy_skip_low_acc, "skip_low_acc", "cw")
    assert r.total_bets == 2
    assert r.total_skips == 2
    assert r.hits == 2
    assert r.accuracy == 1.0

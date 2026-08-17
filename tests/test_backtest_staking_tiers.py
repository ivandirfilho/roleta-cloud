import pytest

from tools.backtest_staking_tiers import parse_tiers, pnl_total, simulate


def test_pnl_total_normalizes_per_unit_hit():
    row = {
        "pnl_units": 1.1176,
        "gale_bet_value": 17,
        "sda_numbers": list(range(17)),
        "result_hit": True,
    }
    assert pnl_total(row) == pytest.approx(19.0)


def test_pnl_total_preserves_total_scale_miss():
    row = {
        "pnl_units": -17.0,
        "gale_bet_value": 17,
        "sda_numbers": list(range(17)),
        "result_hit": False,
    }
    assert pnl_total(row) == pytest.approx(-17.0)


def test_parse_tiers_supports_owner_blocks():
    assert parse_tiers("5x1->5x2->5x4") == [1.0] * 5 + [2.0] * 5 + [4.0] * 5


def test_simulate_reports_drawdown_and_stake():
    rows = [
        type("Row", (), {"hit": False, "pnl": -1.0, "stake": 1.0})(),
        type("Row", (), {"hit": True, "pnl": 1.0, "stake": 1.0})(),
    ]
    result = simulate(rows, [1.0, 2.0])
    assert result["n"] == 2
    assert result["max_stake"] == 2.0
    assert result["max_dd"] == 1.0

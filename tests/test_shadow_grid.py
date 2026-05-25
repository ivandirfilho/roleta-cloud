"""S-STRAT-13 — Tests for shadow grid (4 challengers paralelos)."""
import pytest
from state.game import GameState
from core.roulette import roulette


@pytest.fixture
def gs():
    return GameState()


def test_shadow_grid_initializes_four_shifts(gs):
    """Deve criar deques para shifts 1, 3, 5, 10."""
    assert set(gs.shadow_grid.keys()) == {1, 3, 5, 10}
    for shift in (1, 3, 5, 10):
        assert "cw" in gs.shadow_grid[shift]
        assert "ccw" in gs.shadow_grid[shift]
        assert len(gs.shadow_grid[shift]["cw"]) == 0


def test_store_prediction_populates_grid(gs):
    """store_prediction deve gerar shadow_numbers_by_shift com 4 rotações."""
    gs.store_prediction(numbers=[0, 32, 15], direction="horario", center=0)
    pp = gs.pending_prediction
    assert "shadow_numbers_by_shift" in pp
    grid = pp["shadow_numbers_by_shift"]
    assert set(grid.keys()) == {1, 3, 5, 10}
    for shift, nums in grid.items():
        assert len(nums) == 3


def test_check_prediction_records_hit_per_shift(gs):
    """Cada shift deve receber registro de hit independente."""
    gs.last_number = 26
    gs.store_prediction(numbers=[0], direction="horario", center=0, bet_placed=True)
    # Rotação +5 do 0 no wheel europeu — calcula esperado
    wheel = list(roulette.WHEEL_SEQUENCE)
    idx0 = wheel.index(0)
    expected_shift5 = wheel[(idx0 + 5) % len(wheel)]
    # spin agora processa o pending
    gs.check_prediction(actual_number=expected_shift5)
    # shift 5 cw deve ter hit=True
    assert gs.shadow_grid[5]["cw"][0] is True
    # outros shifts cw têm registro (provavelmente False)
    assert len(gs.shadow_grid[1]["cw"]) == 1
    assert len(gs.shadow_grid[3]["cw"]) == 1
    assert len(gs.shadow_grid[10]["cw"]) == 1


def test_get_shadow_stats_returns_grid(gs):
    """get_shadow_stats deve retornar 4 challengers + champion + alert."""
    snap = gs.get_shadow_stats()
    assert snap["design"] == "shadow_grid_v1"
    assert snap["shifts"] == [1, 3, 5, 10]
    assert len(snap["challengers"]) == 4
    assert "champion" in snap
    assert "alert" in snap
    assert snap["alert"] == "ok"  # n=0, ninguém bate ainda


def test_legacy_shadow_fields_preserved(gs):
    """Compatibilidade: shadow/edge_pp do shift=5 mantidos no top-level."""
    snap = gs.get_shadow_stats()
    assert "shadow" in snap
    assert "edge_pp" in snap
    assert "cw" in snap["shadow"]
    assert "ccw" in snap["shadow"]


def test_champion_only_when_eligible(gs):
    """Champion deve ser None até algum challenger atingir n>=30 em ambas direções."""
    # Simula 20 hits — abaixo do threshold de 30
    for _ in range(20):
        gs.shadow_grid[5]["cw"].appendleft(True)
        gs.shadow_grid[5]["ccw"].appendleft(True)
    snap = gs.get_shadow_stats()
    assert snap["champion"]["shift"] is None


def test_champion_emerges_with_enough_samples(gs):
    """Com n>=30 em ambas direções, champion deve ser identificado."""
    for _ in range(30):
        gs.shadow_grid[3]["cw"].appendleft(True)
        gs.shadow_grid[3]["ccw"].appendleft(True)
        gs.shadow_grid[1]["cw"].appendleft(False)
        gs.shadow_grid[1]["ccw"].appendleft(False)
    snap = gs.get_shadow_stats()
    # Shift=3 tem acc=1.0, outros 0.0 — campeão = 3
    assert snap["champion"]["shift"] == 3
    assert snap["champion"]["avg_acc"] == 1.0


def test_alert_triggers_when_shadow_beats_incumbent(gs):
    """Alert deve disparar quando algum challenger bate incumbent com n>=30."""
    # Incumbent: acc baixo
    for _ in range(40):
        gs.performance_sda17_cw.appendleft(False)
    # Shadow shift=10 cw: acc alto, n>=30
    for _ in range(30):
        gs.shadow_grid[10]["cw"].appendleft(True)
    snap = gs.get_shadow_stats()
    assert snap["alert"] == "shadow_beating_incumbent"

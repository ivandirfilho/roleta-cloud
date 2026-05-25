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
    """Alert deve disparar quando algum challenger bate incumbent com n>=30 em ambas."""
    # BUG-V3-17: incumbent agora usa incumbent_shadow_cw/ccw (maxlen=100)
    for _ in range(40):
        gs.incumbent_shadow_cw.appendleft(False)
        gs.incumbent_shadow_ccw.appendleft(False)
    # BUG-V3-22: precisa n>=30 em AMBAS direcoes para disparar
    for _ in range(30):
        gs.shadow_grid[10]["cw"].appendleft(True)
        gs.shadow_grid[10]["ccw"].appendleft(True)
    snap = gs.get_shadow_stats()
    assert snap["alert"] == "shadow_beating_incumbent"


# --------- BUG-A24-01 / BUG-A24-13 — persistencia & reset ----------

def test_shadow_grid_persists_roundtrip(tmp_path):
    """BUG-A24-01: save() -> load() preserva shadow_grid e shadow_hits."""
    import json
    from state.game import GameState
    p = tmp_path / "state.json"

    gs = GameState()
    for _ in range(10):
        gs.shadow_grid[3]["cw"].appendleft(True)
        gs.shadow_grid[10]["ccw"].appendleft(False)
    gs.shadow_hits_cw.appendleft(True)
    gs.shadow_hits_cw.appendleft(False)
    gs.save(path=p)

    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["version"].startswith("2.")
    # keys serializados como str no JSON
    assert "3" in raw["shadow_grid"]
    assert "10" in raw["shadow_grid"]
    assert len(raw["shadow_grid"]["3"]["cw"]) == 10

    gs2 = GameState.load(path=p)
    assert len(gs2.shadow_grid[3]["cw"]) == 10
    assert all(gs2.shadow_grid[3]["cw"])
    assert len(gs2.shadow_grid[10]["ccw"]) == 10
    assert not any(gs2.shadow_grid[10]["ccw"])
    assert len(gs2.shadow_hits_cw) == 2


def test_shadow_grid_load_tolerant_to_missing_field(tmp_path):
    """load() deve aceitar state.json antigo sem shadow_grid (graceful)."""
    import json
    from state.game import GameState
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"version": "1.7.0", "last_number": 0}), encoding="utf-8")
    gs = GameState.load(path=p)
    # Grid deve ter sido inicializado pelo __post_init__
    assert set(gs.shadow_grid.keys()) == {1, 3, 5, 10}
    assert len(gs.shadow_grid[5]["cw"]) == 0


def test_reset_session_clears_shadow_grid(tmp_path, monkeypatch):
    """BUG-A24-13: reset_session deve limpar shadow_grid + shadow_hits."""
    from state.game import GameState
    from app_config.settings import settings
    p = tmp_path / "state.json"
    monkeypatch.setattr(settings, "state_file", p)

    gs = GameState()
    for _ in range(20):
        gs.shadow_grid[1]["cw"].appendleft(True)
        gs.shadow_grid[5]["ccw"].appendleft(True)
        gs.shadow_hits_cw.appendleft(True)
        gs.shadow_hits_ccw.appendleft(True)

    gs.reset_session()
    for shift in (1, 3, 5, 10):
        assert len(gs.shadow_grid[shift]["cw"]) == 0
        assert len(gs.shadow_grid[shift]["ccw"]) == 0
    assert len(gs.shadow_hits_cw) == 0
    assert len(gs.shadow_hits_ccw) == 0


def test_check_prediction_after_restart_uses_str_keys():
    """BUG-A24-V2-10: JSON desserializa int keys como str. check_prediction
    deve normalizar shift -> int para nao descartar silenciosamente."""
    from state.game import GameState
    from core.roulette import roulette
    gs = GameState()
    wheel = list(roulette.WHEEL_SEQUENCE)
    idx_map = {n: i for i, n in enumerate(wheel)}
    target = wheel[(idx_map[0] + 3) % len(wheel)]  # +3 rotation of 0
    # Simula pending_prediction restaurado de JSON (keys str)
    gs.pending_prediction = {
        "numbers": [0],
        "direction": "horario",
        "center": 0,
        "centers": [0],
        "bet_placed": False,
        "shadow_numbers_by_shift": {
            "1": [wheel[(idx_map[0] + 1) % len(wheel)]],
            "3": [target],
            "5": [wheel[(idx_map[0] + 5) % len(wheel)]],
            "10": [wheel[(idx_map[0] + 10) % len(wheel)]],
        },
    }
    gs.last_number = 17
    gs.check_prediction(actual_number=target)
    # shift=3 cw deve ter hit=True (nao descartado por KeyError silencioso)
    assert len(gs.shadow_grid[3]["cw"]) == 1
    assert gs.shadow_grid[3]["cw"][0] is True
    # outros shifts cw devem estar populados (False, pois target nao bate)
    assert len(gs.shadow_grid[1]["cw"]) == 1
    assert gs.shadow_grid[1]["cw"][0] is False


# --------- S-STRAT-13.1: EMA + sustained edge + suggestion ----------

def test_shadow_ema_updates_on_spin(gs):
    """BUG-V4-01: EMA atualiza por SPIN (via _update_shadow_ema_on_spin), nao por scrape."""
    # popula challenger 3 com edge alto vs incumbent baixo
    for _ in range(50):
        gs.incumbent_shadow_cw.appendleft(False)
        gs.incumbent_shadow_ccw.appendleft(False)
        gs.shadow_grid[3]["cw"].appendleft(True)
        gs.shadow_grid[3]["ccw"].appendleft(True)
    # 1 chamada simulando 1 spin
    gs._update_shadow_ema_on_spin()
    snap = gs.get_shadow_stats()
    ch3 = [c for c in snap["challengers"] if c["shift"] == 3][0]
    assert ch3["edge_ema"] > 0.0
    assert abs(ch3["edge_ema"] - 0.05) < 0.001  # 1.0 * 0.05 = 0.05
    assert ch3["sustained_spins"] == 1


def test_ema_does_not_drift_on_pure_read(gs):
    """BUG-V4-01: get_shadow_stats nao deve mutar EMA (apenas leitura)."""
    for _ in range(50):
        gs.incumbent_shadow_cw.appendleft(False)
        gs.incumbent_shadow_ccw.appendleft(False)
        gs.shadow_grid[3]["cw"].appendleft(True)
        gs.shadow_grid[3]["ccw"].appendleft(True)
    gs._update_shadow_ema_on_spin()  # 1 spin
    snap1 = gs.get_shadow_stats()
    # Multiplas leituras nao devem alterar EMA nem sustained
    for _ in range(50):
        snap_n = gs.get_shadow_stats()
    ch3_1 = [c for c in snap1["challengers"] if c["shift"] == 3][0]
    ch3_n = [c for c in snap_n["challengers"] if c["shift"] == 3][0]
    assert ch3_1["edge_ema"] == ch3_n["edge_ema"]
    assert ch3_1["sustained_spins"] == ch3_n["sustained_spins"] == 1


def test_suggestion_emerges_after_sustained(gs):
    """Suggestion deve aparecer quando sustained_spins atinge 200 (por SPIN)."""
    for _ in range(50):
        gs.incumbent_shadow_cw.appendleft(False)
        gs.incumbent_shadow_ccw.appendleft(False)
        gs.shadow_grid[5]["cw"].appendleft(True)
        gs.shadow_grid[5]["ccw"].appendleft(True)
    for _ in range(210):
        gs._update_shadow_ema_on_spin()
    snap = gs.get_shadow_stats()
    assert snap["suggestion"] is not None
    assert snap["suggestion"]["shift"] == 5
    assert snap["suggestion"]["applied"] is False


def test_suggestion_preserves_applied_flag(gs):
    """BUG-V4-02: marcar applied=True nao deve ser sobrescrito por novos spins."""
    for _ in range(50):
        gs.incumbent_shadow_cw.appendleft(False)
        gs.incumbent_shadow_ccw.appendleft(False)
        gs.shadow_grid[5]["cw"].appendleft(True)
        gs.shadow_grid[5]["ccw"].appendleft(True)
    for _ in range(210):
        gs._update_shadow_ema_on_spin()
    # Humano marca applied
    gs._adaptive_state["suggested_shift"]["applied"] = True
    original_ts = gs._adaptive_state["suggested_shift"]["ts"]
    # Mais 50 spins com mesmo edge
    for _ in range(50):
        gs._update_shadow_ema_on_spin()
    final = gs._adaptive_state["suggested_shift"]
    assert final["applied"] is True, "applied flag foi sobrescrito (BUG-V4-02)"
    assert final["shift"] == 5
    assert final["ts"] == original_ts  # ts original preservado


def test_no_suggestion_when_edge_below_threshold(gs):
    """Edge ~0.0 (banda morta) nao deve gerar suggestion mesmo apos 210 spins."""
    for _ in range(50):
        gs.incumbent_shadow_cw.appendleft(False)
        gs.incumbent_shadow_ccw.appendleft(False)
        gs.shadow_grid[1]["cw"].appendleft(False)
        gs.shadow_grid[1]["ccw"].appendleft(False)
    for _ in range(210):
        gs._update_shadow_ema_on_spin()
    snap = gs.get_shadow_stats()
    assert snap.get("suggestion") is None


def test_reset_session_clears_shadow_adaptive_state(gs):
    """BUG-V3-21: reset_session limpa shadow_ema + suggested_shift do _adaptive_state."""
    gs._adaptive_state["shadow_ema"] = {"5": {"ema": 0.1, "sustained": 50}}
    gs._adaptive_state["suggested_shift"] = {"shift": 5, "applied": False}
    gs.reset_session()
    assert "shadow_ema" not in gs._adaptive_state
    assert "suggested_shift" not in gs._adaptive_state
    # incumbent_shadow tambem deve estar zerado
    assert len(gs.incumbent_shadow_cw) == 0
    assert len(gs.incumbent_shadow_ccw) == 0


def test_incumbent_shadow_populated_on_check_prediction(gs):
    """BUG-V3-17: incumbent_shadow_cw/ccw cresce no check_prediction."""
    gs.store_prediction(numbers=[7], direction="horario", center=7, bet_placed=False)
    gs.check_prediction(actual_number=7)
    assert len(gs.incumbent_shadow_cw) == 1
    assert gs.incumbent_shadow_cw[0] is True
    gs.store_prediction(numbers=[7], direction="anti_horario", center=7, bet_placed=False)
    gs.check_prediction(actual_number=15)  # miss
    assert len(gs.incumbent_shadow_ccw) == 1
    assert gs.incumbent_shadow_ccw[0] is False


# ---------- S-STRAT-13.1 auto-promote ----------

def _seed_dominant_shift(gs, shift: int, samples: int = 50):
    for _ in range(samples):
        gs.incumbent_shadow_cw.appendleft(False)
        gs.incumbent_shadow_ccw.appendleft(False)
        gs.shadow_grid[shift]["cw"].appendleft(True)
        gs.shadow_grid[shift]["ccw"].appendleft(True)


def test_auto_promote_disabled_by_default(gs):
    """settings.shadow_auto_promote_enabled=False ⇒ nunca auto-promove."""
    _seed_dominant_shift(gs, 5)
    for _ in range(500):
        gs._update_shadow_ema_on_spin()
    sug = gs._adaptive_state.get("suggested_shift") or {}
    assert sug.get("shift") == 5
    assert sug.get("auto_promoted") is not True
    assert sug.get("applied") is False


def test_auto_promote_fires_when_enabled(monkeypatch, gs):
    """Quando settings.shadow_auto_promote_enabled=True e sustained>=400, marca applied+auto_promoted."""
    from app_config import settings as _s
    monkeypatch.setattr(_s.settings, "shadow_auto_promote_enabled", True, raising=False)
    _seed_dominant_shift(gs, 3)
    for _ in range(450):
        gs._update_shadow_ema_on_spin()
    sug = gs._adaptive_state.get("suggested_shift") or {}
    assert sug.get("shift") == 3
    assert sug.get("applied") is True
    assert sug.get("auto_promoted") is True
    history = gs._adaptive_state.get("auto_promotes") or []
    assert len(history) >= 1
    assert history[-1]["shift"] == 3


def test_auto_promote_idempotent(monkeypatch, gs):
    """Auto-promote para o mesmo shift não duplica entradas no histórico."""
    from app_config import settings as _s
    monkeypatch.setattr(_s.settings, "shadow_auto_promote_enabled", True, raising=False)
    _seed_dominant_shift(gs, 1)
    for _ in range(450):
        gs._update_shadow_ema_on_spin()
    first_len = len(gs._adaptive_state.get("auto_promotes") or [])
    for _ in range(100):
        gs._update_shadow_ema_on_spin()
    assert len(gs._adaptive_state.get("auto_promotes") or []) == first_len


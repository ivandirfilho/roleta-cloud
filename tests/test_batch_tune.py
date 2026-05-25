"""
S-STRAT-7 — Testes do auto-tune batch (4 spins por sentido, isolado).

Cobre:
  T1: Contadores INDEPENDENTES por direção (cw cresce sem mover ccw).
  T2: Tune dispara EXATAMENTE no 4º spin do sentido.
  T3: 4 hits + 4 hits → improve_keep (offsets não mudam por força).
  T4: 4 hits + 4 misses → pull-back (offsets aproximam de PRIOR_CENTER=10).
  T5: Backward-compat — load_state SEM batch_tune_state → defaults 0.
  T6: Clamp respeitado mesmo com nudge agressivo (off ∈ [OFFSET_MIN, OFFSET_MAX]).
  T7: Warmup insuficiente → skip_warmup (não erra com slice vazio).
  T8: Persistência roundtrip (state_dict → load → mesmo state).
"""
import pytest
from strategies.sda17 import SDA17Strategy


WHEEL = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
]


def _make_strategy():
    s = SDA17Strategy()
    s._wheel = WHEEL
    s._sigmoid_off = {
        "cw_off2": 10.0, "cw_off3": 10.0,
        "ccw_off2": 10.0, "ccw_off3": 10.0,
    }
    return s


def _force_hits(s, direction: str, hits: list[int]):
    """Empurra hits diretamente em _recent_hits e dispara update_adaptive simulando spins."""
    dk = "cw" if direction in ("cw", "horario") else "ccw"
    # Popular recent_hits direto (sem rodar _pct_sigmoid_update para isolar lógica do batch).
    s._recent_hits[dk] = list(hits)
    # Popular history mínima p/ passar warmup interno.
    fake_hist = [(0, 0)] * max(len(hits), 16)
    if dk == "cw":
        s.cw_history = fake_hist
    else:
        s.ccw_history = fake_hist


def test_T1_counters_independent():
    s = _make_strategy()
    for _ in range(3):
        s.update_adaptive("horario", 0, 0, WHEEL)
    assert s._pending_spins["cw"] == 3
    assert s._pending_spins["ccw"] == 0


def test_T2_fires_on_fourth_spin():
    s = _make_strategy()
    _force_hits(s, "cw", [1, 0, 1, 0, 1, 0, 1, 0])  # warmup OK
    initial_runs = s._batch_runs_total["cw"]
    for i in range(4):
        s.update_adaptive("horario", 0, 0, WHEEL)
    # Após 4 spins, contador volta a 0 E batch_runs incrementou (ou pelo menos last_action != init).
    assert s._pending_spins["cw"] == 0
    # Pode ter executado o batch (com warmup OK).
    assert s._batch_last_action["cw"] in ("pullback", "improve_keep", "explore_nudge", "skip_warmup")


def test_T3_improve_keep_no_pullback():
    s = _make_strategy()
    # 4 prev + 4 last todos hits → delta=0 → explore (não pullback).
    _force_hits(s, "cw", [1] * 8)
    s._pending_spins["cw"] = 4
    s._batch_auto_tune("cw", min_warmup=8)
    assert s._batch_last_action["cw"] in ("improve_keep", "explore_nudge")
    assert s._batch_pullback_total["cw"] == 0


def test_T4_pullback_when_degrades():
    s = _make_strategy()
    # 4 prev hits, 4 last misses → delta = -1.0 < -0.10 → pullback.
    _force_hits(s, "ccw", [1, 1, 1, 1, 0, 0, 0, 0])
    s._sigmoid_off["ccw_off2"] = 13.0  # longe do center=10
    s._sigmoid_off["ccw_off3"] = 13.0
    s._batch_auto_tune("ccw", min_warmup=8)
    assert s._batch_last_action["ccw"] == "pullback"
    assert s._batch_pullback_total["ccw"] == 1
    # Pulled towards PRIOR_CENTER=10 (deve estar < 13.0).
    assert s._sigmoid_off["ccw_off2"] < 13.0
    assert s._sigmoid_off["ccw_off3"] < 13.0


def test_T5_backward_compat_no_batch_state():
    s = _make_strategy()
    # State antigo (v1.7) sem batch_tune_state.
    s.load_adaptive_state({
        "cw_history": [(10, 20)],
        "ccw_history": [],
        "sigmoid_off": {"cw_off2": 11.0},
        "version": "1.7",
    })
    assert s._pending_spins == {"cw": 0, "ccw": 0}
    assert s._batch_runs_total == {"cw": 0, "ccw": 0}
    assert s._batch_last_action == {"cw": "init", "ccw": "init"}


def test_T6_clamp_respected_under_aggressive_nudge():
    s = _make_strategy()
    s._sigmoid_off["cw_off2"] = float(s.OFFSET_MAX)
    s._sigmoid_off["cw_off3"] = float(s.OFFSET_MIN)
    _force_hits(s, "cw", [0, 1, 0, 1, 0, 1, 0, 1])
    s._batch_auto_tune("cw", min_warmup=8)
    assert s.OFFSET_MIN <= s._sigmoid_off["cw_off2"] <= s.OFFSET_MAX
    assert s.OFFSET_MIN <= s._sigmoid_off["cw_off3"] <= s.OFFSET_MAX


def test_T7_warmup_insufficient_skips_safely():
    s = _make_strategy()
    s._recent_hits["cw"] = [1, 0, 1]  # < 8
    # Não deve dar exception com slice vazio.
    s._batch_auto_tune("cw", min_warmup=16)
    assert s._batch_last_action["cw"] == "skip_warmup"
    assert s._batch_runs_total["cw"] == 0


def test_T8_state_roundtrip():
    s = _make_strategy()
    _force_hits(s, "cw", [1, 1, 0, 0, 1, 0, 1, 1])
    s._pending_spins["cw"] = 2
    s._pending_spins["ccw"] = 3
    s._batch_runs_total["cw"] = 5
    s._batch_pullback_total["ccw"] = 1
    s._batch_last_delta["cw"] = -0.25
    s._batch_acc_history["cw"].append((0.25, 0.75, -0.5))

    snapshot = s.get_adaptive_state()
    s2 = _make_strategy()
    s2.load_adaptive_state(snapshot)
    assert s2._pending_spins == {"cw": 2, "ccw": 3}
    assert s2._batch_runs_total["cw"] == 5
    assert s2._batch_pullback_total["ccw"] == 1
    assert s2._batch_last_delta["cw"] == -0.25
    assert s2._batch_acc_history["cw"] == [(0.25, 0.75, -0.5)]

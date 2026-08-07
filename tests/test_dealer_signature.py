"""Tests da assinatura por dealer (strategies/dealer_signature.py) — 05/08 noite-2.

Cobre: candidatos por braço, Thompson determinístico (rng seedado), update
(decay/freeze), round-trip to_dict/from_dict, LRU cap e cache S1.
"""
from __future__ import annotations

import random

import pytest

from strategies import dealer_signature as dsig
from strategies.dealer_signature import (
    ARMS,
    MAX_KEYS,
    DealerSignature,
    clear_s1_cache,
    long_term_modal_force,
)

SIZE = 37


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_s1_cache()
    yield
    clear_s1_cache()


# ---- key ----

def test_key_normalizes_dealer_and_direction():
    assert DealerSignature.key(" Maria ", "cw") == "maria|cw"
    assert DealerSignature.key(None, "ccw") == "unknown|ccw"
    assert DealerSignature.key("", "cw") == "unknown|cw"


# ---- candidates ----

def test_trend_candidate_matches_spec4_production():
    sig = DealerSignature()
    # slope 2.4 → round 2 → r1+2 (mesma regra do R2 spec4)
    c = sig.candidates("d|cw", r1_force=10, slope=2.4,
                       forces_recent_first=[10, 11, 9, 10], size=SIZE)
    assert c["trend"] == 12
    # slope None → delta 0 → trend = r1
    c2 = sig.candidates("d|cw", r1_force=10, slope=None,
                        forces_recent_first=[], size=SIZE)
    assert c2["trend"] == 10


def test_trend_clamped_to_pm8_of_r1():
    sig = DealerSignature()
    c = sig.candidates("d|cw", r1_force=10, slope=15.0,
                       forces_recent_first=[], size=SIZE)
    assert c["trend"] == 18  # 10 + clamp(15→8)


def test_residual_candidate_from_second_cluster():
    sig = DealerSignature()
    # janela: cluster em ~10 e outlier 25 (fora do poço ±7 de r1=10)
    c = sig.candidates("d|cw", r1_force=10, slope=0.0,
                       forces_recent_first=[10, 25, 11, 9], size=SIZE)
    # resíduo=[25] → clampado a r1+8=18
    assert c["residual"] == 18


def test_no_residual_arm_when_all_forces_in_r1_well():
    sig = DealerSignature()
    c = sig.candidates("d|cw", r1_force=10, slope=0.0,
                       forces_recent_first=[10, 11, 9, 12], size=SIZE)
    assert "residual" not in c


def test_dealer_arm_requires_modal_force():
    sig = DealerSignature()
    c1 = sig.candidates("d|cw", r1_force=10, slope=0.0,
                        forces_recent_first=[10], size=SIZE)
    assert "dealer" not in c1
    c2 = sig.candidates("d|cw", r1_force=10, slope=0.0,
                        forces_recent_first=[10], size=SIZE,
                        dealer_modal_force=14)
    assert c2["dealer"] == 14  # dentro do arco ±8
    c3 = sig.candidates("d|cw", r1_force=10, slope=0.0,
                        forces_recent_first=[10], size=SIZE,
                        dealer_modal_force=25)
    assert c3["dealer"] == 18  # diff +15 → clampado a r1+8


def test_correct_arm_gated_by_ewma_and_sign_agreement():
    sig = DealerSignature()
    key = "d|cw"
    # sem histórico → sem braço correct
    c0 = sig.candidates(key, r1_force=10, slope=0.0,
                        forces_recent_first=[], size=SIZE)
    assert "correct" not in c0
    # alimenta 4 erros consistentes +4 (miss) → EWMA>0, 4/4 sinais iguais...
    for _ in range(30):
        sig.update(key, "trend", hit=False, signed_err=4.0)
    c1 = sig.candidates(key, r1_force=10, slope=0.0,
                        forces_recent_first=[], size=SIZE)
    assert "correct" in c1
    # correção positiva clampada a +3: trend=10 → correct ∈ (10, 13]
    assert 10 < c1["correct"] <= 13
    # histórico alternado (sem acordo de sinal) → gate fecha
    sig2 = DealerSignature()
    for e in (4.0, -4.0, 4.0, -4.0, 4.0, -4.0, 4.0, -4.0):
        sig2.update(key, "trend", hit=False, signed_err=e)
    c2 = sig2.candidates(key, r1_force=10, slope=0.0,
                         forces_recent_first=[], size=SIZE)
    assert "correct" not in c2


# ---- choose (Thompson) ----

def test_choose_deterministic_with_seeded_rng():
    sig = DealerSignature()
    cands = {"trend": 10, "residual": 18}
    rng1, rng2 = random.Random(42), random.Random(42)
    a1 = sig.choose("d|cw", cands, rng=rng1)
    a2 = sig.choose("d|cw", cands, rng=rng2)
    assert a1 == a2
    assert a1[0] in cands and a1[1] == cands[a1[0]]


def test_choose_prefers_arm_with_strong_posterior():
    sig = DealerSignature()
    key = "d|cw"
    # residual acerta 30x, trend erra 30x → posterior residual >> trend
    for _ in range(30):
        sig.update(key, "residual", hit=True, signed_err=0.0)
        sig.update(key, "trend", hit=False, signed_err=5.0)
    rng = random.Random(7)
    wins = sum(1 for _ in range(200)
               if sig.choose(key, {"trend": 10, "residual": 18},
                             rng=rng)[0] == "residual")
    assert wins > 150  # dominância clara (não exigimos 100% — é sampling)


def test_choose_raises_on_empty_candidates():
    with pytest.raises(ValueError):
        DealerSignature().choose("d|cw", {})


# ---- update ----

def test_update_moves_posterior_and_ewma():
    sig = DealerSignature()
    key = "d|cw"
    sig.update(key, "trend", hit=True, signed_err=2.0)
    st = sig.stats(key)
    a, b = st["arms"]["trend"]
    assert a > 1.0 and b == pytest.approx(1.0)
    assert st["ewma"] == pytest.approx(2.0)
    assert st["n"] == 1
    sig.update(key, "trend", hit=False, signed_err=-2.0)
    st2 = sig.stats(key)
    assert st2["arms"]["trend"][1] > 1.0
    assert st2["ewma"] < 2.0  # EWMA moveu na direção do novo erro


def test_update_frozen_is_total_noop():
    sig = DealerSignature()
    key = "d|cw"
    sig.update(key, "trend", hit=True, signed_err=5.0, frozen=True)
    assert sig.stats(key).get("n", 0) == 0 or sig.stats(key) == {}


def test_update_winsorizes_err_to_pm8():
    sig = DealerSignature()
    key = "d|cw"
    sig.update(key, "trend", hit=False, signed_err=18.0)
    assert sig.stats(key)["ewma"] == pytest.approx(8.0)


def test_decay_forgets_old_regime():
    sig = DealerSignature()
    key = "d|cw"
    for _ in range(50):
        sig.update(key, "trend", hit=True)
    a_peak = sig.stats(key)["arms"]["trend"][0]
    # 100 updates de OUTRO braço → decay arrasta trend de volta a ~1
    for _ in range(100):
        sig.update(key, "residual", hit=False)
    a_after = sig.stats(key)["arms"]["trend"][0]
    assert a_after < a_peak * 0.25


# ---- round-trip ----

def test_round_trip_to_from_dict():
    sig = DealerSignature()
    key = "maria|cw"
    for i in range(10):
        sig.update(key, ARMS[i % len(ARMS)], hit=(i % 2 == 0),
                   signed_err=float(i - 5))
    data = sig.to_dict()
    clone = DealerSignature.from_dict(data)
    assert clone.to_dict() == data


def test_from_dict_defensive_on_garbage():
    for garbage in (None, [], "x", {"keys": "nope"},
                    {"keys": {"k": {"arms": {"trend": ["a", "b"]},
                                    "ewma": "x", "hist": "y", "n": -1}}}):
        inst = DealerSignature.from_dict(garbage)  # não levanta
        assert isinstance(inst.to_dict(), dict)


def test_lru_caps_number_of_keys():
    sig = DealerSignature()
    for i in range(MAX_KEYS + 10):
        sig.update(f"dealer{i}|cw", "trend", hit=True)
    assert len(sig.to_dict()["keys"]) <= MAX_KEYS


# ---- S1 (longo prazo) ----

def test_long_term_modal_force_uses_loader_and_cache():
    calls = []

    def fake_loader(db, dealer, direction="horario"):
        calls.append((db, dealer, direction))
        return {"n": 40, "modal_force": 12}

    m1 = long_term_modal_force("db", "Maria", "cw", loader=fake_loader)
    m2 = long_term_modal_force("db", "Maria", "cw", loader=fake_loader)
    assert m1 == 12 and m2 == 12
    assert len(calls) == 1  # 2ª chamada veio do cache
    assert calls[0][2] == "horario"  # direção legada correta


def test_long_term_modal_force_unknown_dealer_is_none():
    assert long_term_modal_force("db", "unknown", "cw") is None
    assert long_term_modal_force("db", None, "cw") is None


def test_long_term_modal_force_never_raises():
    def bomb(*a, **kw):
        raise RuntimeError("boom")
    assert long_term_modal_force("db", "Maria", "cw", loader=bomb) is None

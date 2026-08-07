"""Wiring do R2 dealer-aware (ADENDO 05/08 noite-2) — testes de integração leve.

Cobre as costuras entre as peças novas e o código existente:
  1. Flags novas default OFF (por-chamada) e ligáveis por env.
  2. compose_v5(r2_override_force=…): OFF byte-idêntico; override respeitado,
     re-clampado ±8 de R1, re-disjuntado; ignorado no warmup.
  3. Estado adaptativo v2.0 do sda17: round-trip get→load→get do dealer_sig,
     backward-compat com snapshots v1.x, reset limpa.
  4. maybe_publish_spin_result: payload ganha dealer/table/provider quando
     presentes; payloads antigos (sem kwargs) permanecem válidos.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.roulette import roulette
from strategies import regions_v5 as rv5
from strategies.dealer_signature import DealerSignature
from strategies.sda17 import SDA17Strategy

WHEEL = list(roulette.WHEEL_SEQUENCE)
SIZE = len(WHEEL)

FORCES = [12, 10, 11, 13, 9, 12, 10, 11]      # timeline recente-primeiro
RESULTS = [3, 26, 0, 32, 15, 19]              # cronológico (>= warmup mínimo)


def _compose(**kw):
    base = dict(direction="cw", forces_recent_first=FORCES,
                results_chrono=RESULTS, last_number=0, wheel=WHEEL)
    base.update(kw)
    return rv5.compose_v5(**base)


# ---- 1. flags ----

def test_new_flags_default_off_and_env_toggle(monkeypatch):
    from app_config.settings import (
        error_engine_enabled,
        r2_dealer_live_enabled,
        r2_dealer_shadow_enabled,
    )
    for var in ("SDA_ERROR_ENGINE", "SDA_R2_DEALER_SHADOW", "SDA_R2_DEALER"):
        monkeypatch.delenv(var, raising=False)
    assert error_engine_enabled() is False
    assert r2_dealer_shadow_enabled() is False
    assert r2_dealer_live_enabled() is False
    # leitura por-chamada: setar env muda o retorno sem reload
    monkeypatch.setenv("SDA_ERROR_ENGINE", "1")
    monkeypatch.setenv("SDA_R2_DEALER_SHADOW", "1")
    monkeypatch.setenv("SDA_R2_DEALER", "1")
    assert error_engine_enabled() is True
    assert r2_dealer_shadow_enabled() is True
    assert r2_dealer_live_enabled() is True


# ---- 2. compose_v5 r2_override_force ----

def test_override_none_is_byte_identical():
    for spec4 in (False, True):
        kw = dict(spec4=spec4)
        if spec4:
            kw["region6_counts"] = [1, 0, 2, 0, 1, 0]
        a = _compose(**kw)
        b = _compose(r2_override_force=None, **kw)
        assert a == b
        assert "r2_override" not in a


def test_override_moves_r2_and_flags_result():
    base = _compose(spec4=True, region6_counts=[1, 0, 2, 0, 1, 0])
    r1f = base["r1_force"]
    target = (r1f + 6) % SIZE          # dentro do arco ±8
    out = _compose(spec4=True, region6_counts=[1, 0, 2, 0, 1, 0],
                   r2_override_force=target)
    assert out["r2_override"] is True
    assert out["centers"][0] == base["centers"][0]    # R1 intacto
    expect_ideal = rv5.apply_force(0, target, "cw", WHEEL)
    expect_r2 = rv5.nearest_non_overlapping(
        expect_ideal, [out["centers"][0]], WHEEL)
    assert out["centers"][1] == expect_r2
    # invariantes de cobertura preservados
    assert len(out["numbers17"]) == 17
    assert len(out["numbers21"]) == 21
    assert set(out["numbers17"]) <= set(out["numbers21"])


def test_override_is_reclamped_to_pm8_of_r1():
    base = _compose(spec4=True, region6_counts=[0] * 6)
    r1f = base["r1_force"]
    wild = (r1f + 15) % SIZE           # fora do arco → deve clampar a +8
    out = _compose(spec4=True, region6_counts=[0] * 6,
                   r2_override_force=wild)
    clamped = (r1f + rv5.V5_R2_CLAMP) % SIZE
    expect_ideal = rv5.apply_force(0, clamped, "cw", WHEEL)
    expect_r2 = rv5.nearest_non_overlapping(
        expect_ideal, [out["centers"][0]], WHEEL)
    assert out["centers"][1] == expect_r2


def test_override_ignored_during_warmup():
    out = rv5.compose_v5("cw", [], [3], last_number=3, wheel=WHEEL,
                         r2_override_force=20)
    assert out["warmup"] is True
    assert "r2_override" not in out
    base = rv5.compose_v5("cw", [], [3], last_number=3, wheel=WHEEL)
    assert out["centers"] == base["centers"]


# ---- 3. sda17 estado adaptativo v2.0 ----

def test_adaptive_state_v2_round_trip_dealer_sig():
    s = SDA17Strategy()
    key = DealerSignature.key("Maria", "cw")
    for i in range(6):
        s.dealer_signature.update(key, "trend", hit=(i % 2 == 0),
                                  signed_err=float(i - 3))
    st = s.get_adaptive_state()
    assert st["version"] == "2.0"
    assert key in st["dealer_sig"]["keys"]

    s2 = SDA17Strategy()
    s2.load_adaptive_state(st)
    assert s2.dealer_signature.to_dict() == s.dealer_signature.to_dict()
    assert s2.get_adaptive_state()["dealer_sig"] == st["dealer_sig"]


def test_adaptive_state_legacy_v1_snapshot_still_loads():
    s = SDA17Strategy()
    st = s.get_adaptive_state()
    st.pop("dealer_sig", None)         # snapshot antigo (pré-ADENDO)
    st["version"] = "1.9"
    s2 = SDA17Strategy()
    s2.load_adaptive_state(st)         # não levanta
    assert s2.dealer_signature.to_dict()["keys"] == {}


def test_adaptive_state_garbage_dealer_sig_is_defensive():
    s = SDA17Strategy()
    st = s.get_adaptive_state()
    st["dealer_sig"] = "corrompido"
    s2 = SDA17Strategy()
    s2.load_adaptive_state(st)
    assert s2.dealer_signature.to_dict()["keys"] == {}


def test_reset_adaptive_clears_dealer_sig():
    s = SDA17Strategy()
    s.dealer_signature.update("maria|cw", "trend", hit=True, signed_err=2.0)
    assert s.dealer_signature.to_dict()["keys"]
    s.reset_adaptive()
    assert s.dealer_signature.to_dict()["keys"] == {}


# ---- 4. outbox: payload spin_result com dealer ----

def test_spin_result_payload_carries_dealer_table_provider():
    from database import outbox_integration as oi
    oi.invalidate_flag_cache()
    fake_pub = MagicMock()
    with patch("database.outbox_integration._is_flag_enabled",
               return_value=True), \
         patch("database.outbox_integration._get_publisher",
               return_value=fake_pub):
        ok = oi.maybe_publish_spin_result(
            42, "horario", True, 17, session_id="s1",
            dealer=" Maria ", table="Ruleta en Vivo", provider="evolution")
        assert ok is True
        payload = fake_pub.publish.call_args.kwargs["payload"]
        assert payload["dealer"] == "Maria"          # trim aplicado
        assert payload["table"] == "Ruleta en Vivo"
        assert payload["provider"] == "evolution"


def test_spin_result_payload_retrocompat_without_dealer():
    from database import outbox_integration as oi
    oi.invalidate_flag_cache()
    fake_pub = MagicMock()
    with patch("database.outbox_integration._is_flag_enabled",
               return_value=True), \
         patch("database.outbox_integration._get_publisher",
               return_value=fake_pub):
        ok = oi.maybe_publish_spin_result(7, "cw", False, 0)
        assert ok is True
        payload = fake_pub.publish.call_args.kwargs["payload"]
        for absent in ("dealer", "table", "provider"):
            assert absent not in payload
        # dealer vazio/whitespace também não entra
        oi.maybe_publish_spin_result(8, "cw", False, 0, dealer="   ")
        payload2 = fake_pub.publish.call_args.kwargs["payload"]
        assert "dealer" not in payload2

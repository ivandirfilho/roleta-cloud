"""Testes V5 "17/21 por sentido" (04/08 — estrategia_proposta_03_08.md).

Cobre as 4 camadas da implantação:
  1. Composer puro (strategies/regions_v5.py): invariantes geométricos por fuzz
     (17/21 distintos EXATOS, nesting C17 ⊂ C21, mesmos centros, disjunção gap 7),
     Theil–Sen, gravity_scan, warmup tríade.
  2. Seletor 17↔21 no SDA17 (flip miss→21/hit→17, teto 5 → LOCK17, round-trip
     adaptive_state v1.9, reset, backward-compat com estado v1.8 sem chaves v5).
  3. Enum SDA_BET_PAIR (settings).
  4. Wiring no MessageHandler (harness __new__ do test_wiring_c_gale): cobertura
     substituída, meta v5/force17 (labels r1/r2/r3), inject no pending (modo +
     contrafactuais congelados + contagem de emissão), stop-loss → LOCK17,
     byte-safety do force17 clássico (sem v5_mode no meta).
"""
import os
import random

import pytest

from core.roulette import roulette
from strategies import regions_v5 as rv5
from strategies.sda17 import SDA17Strategy
from server.message_handler import MessageHandler
from state.game import GameState

WHEEL = list(roulette.WHEEL_SEQUENCE)


# ===== harness (idêntico ao test_wiring_c_gale) =====

def _handler():
    h = MessageHandler.__new__(MessageHandler)
    h.game_state = GameState()
    h.current_session_id = "test-sess"
    h._cs_meta = None
    h._bg_meta = None
    h.strategy = SDA17Strategy()
    return h


class _Result:
    def __init__(self, numbers, centers):
        self.numbers = list(numbers)
        self.center = centers[0] if centers else 0
        self.details = {"centers": list(centers)}


@pytest.fixture(autouse=True)
def _clean_env():
    saved = {k: os.environ.get(k) for k in
             ("SDA_BET_PAIR", "SDA_STAKING_MODE", "GALE_CAP", "SDA_FORCE17_EXACT")}
    for k in saved:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _feed(h, direction: str, forces, results_chrono):
    """Alimenta timeline de forças + history do sentido no estado do harness."""
    gs = h.game_state
    tl = gs.timeline_cw if direction == "cw" else gs.timeline_ccw
    for f in forces[::-1]:  # add mais antigo primeiro; get_last_n devolve recente-primeiro
        tl.add(f)
    hist = h.strategy.cw_history if direction == "cw" else h.strategy.ccw_history
    for r in results_chrono:
        hist.append((0, r))
    gs.last_number = results_chrono[-1] if results_chrono else 0
    # target_direction é property = oposto de last_direction
    gs.last_direction = "anti-horario" if direction == "cw" else "horario"


# ===== 1. Composer =====

class TestComposerInvariants:
    def test_fuzz_17_21_distintos_nesting_disjuncao(self):
        rng = random.Random(42)
        for _ in range(5000):
            n_forces = rng.randint(0, 12)
            forces = [rng.randint(1, 37) for _ in range(n_forces)]
            n_res = rng.randint(0, 24)
            results = [rng.choice(WHEEL) for _ in range(n_res)]
            last = rng.choice(WHEEL)
            direction = rng.choice(["cw", "ccw"])
            comp = rv5.compose_v5(direction, forces, results, last, WHEEL)
            n17, n21 = comp["numbers17"], comp["numbers21"]
            assert len(n17) == 17, f"17 distintos EXATOS (got {len(n17)})"
            assert len(n21) == 21, f"21 distintos EXATOS (got {len(n21)})"
            assert set(n17) <= set(n21), "nesting C17 ⊂ C21"
            assert len(comp["centers"]) == 3
            c = comp["centers"]
            for i in range(3):
                for j in range(i + 1, 3):
                    assert rv5.circ_dist_idx(c[i], c[j], WHEEL) >= rv5.V5_DISJOINT_GAP, \
                        f"disjunção gap 7 violada: {c}"
            # mesmos centros nos 2 modos
            assert [r["center"] for r in comp["regioes17"]] == c
            assert [r["center"] for r in comp["regioes21"]] == c
            # raios: R1 nunca encolhe
            assert [r["radius"] for r in comp["regioes17"]] == [3, 2, 2]
            assert [r["radius"] for r in comp["regioes21"]] == [3, 3, 3]

    def test_labels_r1_r2_r3(self):
        comp = rv5.compose_v5("cw", [10, 12, 11, 9, 10], [5, 8, 30, 11, 23], 23, WHEEL)
        assert [r["label"] for r in comp["regioes17"]] == ["r1", "r2", "r3"]
        assert [r["label"] for r in comp["regioes21"]] == ["r1", "r2", "r3"]

    def test_warmup_triade_disjunta_inv3(self):
        # 0 resultados → warmup: SEMPRE indica (INV-3), tríade prior 10/22/34
        comp = rv5.compose_v5("cw", [], [], 0, WHEEL)
        assert comp["warmup"] is True
        assert len(comp["numbers17"]) == 17 and len(comp["numbers21"]) == 21
        assert all(r["status"] == "aquecendo" for r in comp["regioes17"])
        expected = [rv5.apply_force(0, 10 + off, "cw", WHEEL) for off in (0, 12, 24)]
        assert comp["centers"] == expected

    def test_warmup_limiar_3_resultados(self):
        base = dict(direction="cw", forces_recent_first=[10, 11, 12, 9],
                    last_number=5, wheel=WHEEL)
        assert rv5.compose_v5(results_chrono=[1, 2], **base)["warmup"] is True
        assert rv5.compose_v5(results_chrono=[1, 2, 3], **base)["warmup"] is False

    def test_deterministico(self):
        args = ("ccw", [30, 5, 31, 29, 30, 4], [17, 25, 2, 21, 4, 15], 15, WHEEL)
        a, b = rv5.compose_v5(*args), rv5.compose_v5(*args)
        assert a == b

    def test_isolamento_por_sentido(self):
        # mesmos dados, sentidos opostos → projeções distintas (cw=+idx, ccw=−idx)
        f, res = [10, 10, 10, 10, 10], [1, 2, 3, 4]
        cw = rv5.compose_v5("cw", f, res, 0, WHEEL)
        ccw = rv5.compose_v5("ccw", f, res, 0, WHEEL)
        assert cw["centers"][0] != ccw["centers"][0]


class TestTheilSen:
    def test_crescente(self):
        # recente-primeiro [14,13,12,11,10] → crono 10..14 → slope +1
        assert rv5.theil_sen_slope([14, 13, 12, 11, 10]) == pytest.approx(1.0)

    def test_decrescente(self):
        assert rv5.theil_sen_slope([10, 11, 12, 13, 14]) == pytest.approx(-1.0)

    def test_menos_de_3_pontos_neutro(self):
        assert rv5.theil_sen_slope([10, 11]) is None
        assert rv5.theil_sen_slope([]) is None

    def test_robusto_a_outlier(self):
        # mediana par-a-par ignora 1 salto: base +1/giro com outlier 37
        s = rv5.theil_sen_slope([14, 37, 12, 11, 10])
        assert s == pytest.approx(1.0, abs=0.75)


class TestGravityScan:
    def test_cluster_denso_vence(self):
        # 4 forças coladas em ~10, 2 dispersas → candidato do cluster
        f, cov = rv5.gravity_scan([10, 11, 9, 10, 25, 33], 37)
        assert rv5.circ_force_dist(f, 10, 37) <= 2
        assert cov >= 4

    def test_janela_vazia(self):
        assert rv5.gravity_scan([], 37) is None

    def test_tiebreak_recencia(self):
        # cobertura empatada (todas cobrem tudo) → vence o MAIS RECENTE (índice 0)
        f, _ = rv5.gravity_scan([12, 10, 11], 37)
        assert f == 12


# ===== 2. Seletor 17↔21 (SDA17) =====

class TestSeletor:
    def test_default_17(self):
        s = SDA17Strategy()
        assert s.v5_select_mode("cw") == 17
        assert s.v5_select_mode("ccw") == 17

    def test_flip_miss_21_hit_17(self):
        s = SDA17Strategy()
        s.v5_note_outcome("cw", hit=False)
        assert s.v5_select_mode("cw") == 21
        assert s.v5_select_mode("ccw") == 17  # sentidos isolados
        s.v5_note_outcome("cw", hit=True)
        assert s.v5_select_mode("cw") == 17

    def test_teto_5_lock17(self):
        s = SDA17Strategy()
        s.v5_note_outcome("cw", hit=False)
        for _ in range(5):
            assert s.v5_select_mode("cw") == 21
            s.v5_note_emitted("cw", 21)
            s.v5_note_outcome("cw", hit=False)  # miss contínuo
        # 5 jogadas-21 emitidas → LOCK17 (mesmo em miss)
        assert s.v5_select_mode("cw") == 17

    def test_emissao_17_nao_queima_credito(self):
        s = SDA17Strategy()
        for _ in range(10):
            s.v5_note_emitted("cw", 17)
        s.v5_note_outcome("cw", hit=False)
        assert s.v5_select_mode("cw") == 21  # crédito 21 intacto

    def test_round_trip_v19(self):
        s = SDA17Strategy()
        s.v5_note_outcome("ccw", hit=False)
        s.v5_note_emitted("ccw", 21)
        st = s.get_adaptive_state()
        assert st["version"] == "1.9"
        assert st["v5_mode"] == {"cw": 17, "ccw": 21}
        assert st["v5_count21"] == {"cw": 0, "ccw": 1}
        s2 = SDA17Strategy()
        s2.load_adaptive_state(st)
        assert s2.v5_select_mode("ccw") == 21
        assert s2._v5_count21 == {"cw": 0, "ccw": 1}

    def test_backward_compat_estado_v18(self):
        s = SDA17Strategy()
        st = s.get_adaptive_state()
        st.pop("v5_mode"), st.pop("v5_count21")
        st["version"] = "1.8"
        s2 = SDA17Strategy()
        s2.v5_note_outcome("cw", hit=False)
        s2.load_adaptive_state(st)  # sem chaves v5 → mantém defaults do load
        assert s2.v5_select_mode("cw") in (17, 21)  # não explode

    def test_load_valida_lixo(self):
        s = SDA17Strategy()
        st = s.get_adaptive_state()
        st["v5_mode"] = {"cw": 99, "ccw": "x"}
        st["v5_count21"] = {"cw": -3, "ccw": "y"}
        s2 = SDA17Strategy()
        s2.load_adaptive_state(st)
        assert s2._v5_mode == {"cw": 17, "ccw": 17}
        assert s2._v5_count21["cw"] == 0

    def test_reset_adaptive_zera(self):
        s = SDA17Strategy()
        s.v5_note_outcome("cw", hit=False)
        s.v5_note_emitted("cw", 21)
        s.reset_adaptive()
        assert s._v5_mode == {"cw": 17, "ccw": 17}
        assert s._v5_count21 == {"cw": 0, "ccw": 0}


# ===== 3. Enum settings =====

class TestSettingsEnum:
    def test_v5_1721_aceito(self):
        from app_config.settings import bet_pair_mode
        os.environ["SDA_BET_PAIR"] = "v5_1721"
        assert bet_pair_mode() == "v5_1721"

    def test_invalido_cai_full(self):
        from app_config.settings import bet_pair_mode
        os.environ["SDA_BET_PAIR"] = "v5_9999"
        assert bet_pair_mode() == "full"


# ===== 4. Wiring MessageHandler =====

class TestWiringV5:
    def test_warmup_emite_17_com_meta_v5(self):
        os.environ["SDA_BET_PAIR"] = "v5_1721"
        h = _handler()
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert len(r.numbers) == 17            # default seletor = 17
        assert h._cs_meta is not None
        assert h._cs_meta["rule"] == "v5_1721"
        v5 = h._cs_meta["v5"]
        assert v5["mode"] == 17
        assert len(v5["cov17"]) == 17 and len(v5["cov21"]) == 21
        assert set(v5["cov17"]) <= set(v5["cov21"])
        f17 = h._cs_meta["force17"]
        assert [reg["label"] for reg in f17["regioes"]] == ["r1", "r2", "r3"]
        assert f17["v5_mode"] == 17
        assert f17["c1_force"]["status"] == "aquecendo"  # GameState fresh → warmup
        assert h.game_state.last_force17_meta is f17
        # continuidade DNA: centers V4 intactos no details
        assert r.details["centers"] == [0, 5, 26]

    def test_pos_miss_emite_21(self):
        os.environ["SDA_BET_PAIR"] = "v5_1721"
        h = _handler()
        dk = h._engine_dk()
        h.strategy.v5_note_outcome(dk, hit=False)
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert len(r.numbers) == 21
        assert h._cs_meta["v5"]["mode"] == 21
        assert h._cs_meta["force17"]["coverage_n"] == 21

    def test_stop_loss_forca_17(self):
        os.environ["SDA_BET_PAIR"] = "v5_1721"
        h = _handler()
        dk = h._engine_dk()
        h.strategy.v5_note_outcome(dk, hit=False)  # pediria 21
        h._v5_stop_loss = True
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert len(r.numbers) == 17            # LOCK17 sob stop-loss
        assert h._cs_meta["v5"]["mode"] == 17

    def test_com_historico_usa_composer(self):
        os.environ["SDA_BET_PAIR"] = "v5_1721"
        h = _handler()
        dk = h._engine_dk()
        _feed(h, dk, forces=[10, 11, 9, 25, 10, 12, 26, 8],
              results_chrono=[5, 8, 30, 11, 23])
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert len(r.numbers) == 17
        f17 = h._cs_meta["force17"]
        assert f17["c1_force"]["status"] == "ok"   # saiu do warmup
        assert f17["c1_force"]["forca"] is not None
        assert len(f17["centros"]) == 3

    def test_inject_pending_congela_contrafactuais_e_conta_emissao(self):
        os.environ["SDA_BET_PAIR"] = "v5_1721"
        h = _handler()
        dk = h._engine_dk()
        h.strategy.v5_note_outcome(dk, hit=False)  # modo 21
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        h.game_state.pending_prediction = {"direction": dk, "numbers": r.numbers}
        assert h.strategy._v5_count21[dk] == 0
        h._engine_inject_pending()
        p = h.game_state.pending_prediction
        assert p["v5_mode"] == 21
        assert len(p["v5_cov17"]) == 17 and len(p["v5_cov21"]) == 21
        assert h.strategy._v5_count21[dk] == 1      # emissão real contou
        assert h.game_state._adaptive_state["v5_count21"][dk] == 1  # snapshot

    def test_sem_pending_nao_conta(self):
        os.environ["SDA_BET_PAIR"] = "v5_1721"
        h = _handler()
        dk = h._engine_dk()
        h.strategy.v5_note_outcome(dk, hit=False)
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        h.game_state.pending_prediction = None      # fallback de calibração
        h._engine_inject_pending()
        assert h.strategy._v5_count21[dk] == 0      # crédito preservado

    def test_force17_classico_sem_v5_mode(self):
        # byte-safety: modo antigo NÃO ganha chaves v5 no meta
        os.environ["SDA_BET_PAIR"] = "force17"
        h = _handler()
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert h._cs_meta is not None
        assert "v5" not in h._cs_meta
        f17 = h._cs_meta.get("force17")
        if f17:
            assert "v5_mode" not in f17

    def test_flags_off_intocado(self):
        h = _handler()
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert len(r.numbers) == 21
        assert h._cs_meta is None

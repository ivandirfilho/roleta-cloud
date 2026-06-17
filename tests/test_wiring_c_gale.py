"""Testes de integração do wiring C1/C2 variável + Block-Gale no message_handler (17/06).

Constrói um MessageHandler mínimo via __new__ (sem o __init__ pesado) e exercita
os helpers de motor diretamente, com as flags via env. Valida o invariante:
flags OFF => comportamento idêntico; flags ON => 14# / block-gale.
"""
import os
import pytest

from server.message_handler import MessageHandler
from state.game import GameState


def _handler():
    h = MessageHandler.__new__(MessageHandler)
    h.game_state = GameState()
    h.current_session_id = "test-sess"
    h._cs_meta = None
    h._bg_meta = None
    return h


class _Result:
    def __init__(self, numbers, centers):
        self.numbers = list(numbers)
        self.center = centers[0]
        self.details = {"centers": list(centers)}


@pytest.fixture(autouse=True)
def _clean_env():
    saved = {k: os.environ.get(k) for k in
             ("SDA_BET_PAIR", "SDA_STAKING_MODE", "GALE_CAP", "GALE_ONLY_AFTER_GREEN")}
    for k in saved:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TestSelectionWiring:
    def test_flags_off_keeps_21_coverage(self):
        h = _handler()
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert len(r.numbers) == 21          # inalterado (default full)
        assert h._cs_meta is None

    def test_var_mode_overrides_to_14(self):
        os.environ["SDA_BET_PAIR"] = "var_c1c2_c3"
        h = _handler()
        r = _Result(list(range(21)), [0, 5, 26])
        h._engine_apply_selection(r)
        assert len(r.numbers) <= 14          # cobertura 14# (uniao real)
        assert h._cs_meta is not None
        assert h._cs_meta["chosen"] in ("C1", "C2")
        assert h._cs_meta["pair"].endswith("+C3")

    def test_var_mode_with_fewer_than_3_centers_noop(self):
        os.environ["SDA_BET_PAIR"] = "var_c1c2_c3"
        h = _handler()
        r = _Result(list(range(21)), [7])     # 1 centro -> nao aplica
        h._engine_apply_selection(r)
        assert len(r.numbers) == 21


class TestStakeWiring:
    def test_flat_default_keeps_stake(self):
        h = _handler()
        si = {"effective_bet": 21, "base_bet": 21, "multiplier": 1.0, "mode": "normal"}
        h._engine_apply_stake(si, 21, "APOSTAR")
        assert si["mode"] == "normal" and si["effective_bet"] == 21
        assert h._bg_meta is None

    def test_block_gale_drives_stake(self):
        os.environ["SDA_STAKING_MODE"] = "block_gale"
        os.environ["GALE_CAP"] = "1"
        h = _handler()
        si = {"effective_bet": 99, "base_bet": 99, "multiplier": 1.0, "mode": "normal"}
        h._engine_apply_stake(si, 14, "APOSTAR")
        assert si["mode"] == "block_gale"
        assert si["effective_bet"] == 14     # base_unit(1)*N(14)*mult(1) = 14
        assert h._bg_meta is not None and h._bg_meta["level"] == 1

    def test_only_after_green_gates_stake_to_zero(self):
        os.environ["SDA_STAKING_MODE"] = "block_gale"
        os.environ["GALE_ONLY_AFTER_GREEN"] = "1"
        h = _handler()
        # last_green=None (inicio) -> gated -> stake 0 (papel), mas acao continua APOSTAR (INV-3)
        si = {"effective_bet": 14, "base_bet": 14, "multiplier": 1.0, "mode": "normal"}
        h._engine_apply_stake(si, 14, "APOSTAR")
        assert si["effective_bet"] == 0
        assert h._bg_meta["gated"] is True


class TestResolveWiring:
    def test_resolve_feeds_engines_and_history(self):
        os.environ["SDA_BET_PAIR"] = "var_c1c2_c3"
        h = _handler()
        gs = h.game_state
        # simula atribuicao do resultado (C2 perto, acerta)
        gs.last_hit_attribution = {"dist_c1": 15, "dist_c2": 1, "dist_c3": 9, "dist_min": 1}
        pending = {"direction": "horario", "cs_chosen": "C2",
                   "shadow_candidates": {"always_c2": "C2", "always_strong": "C2"},
                   "bg_placed": True}
        h._engine_resolve(pending)
        assert len(gs.c_attr_cw) == 1                     # historico do voto crescido
        assert gs.c_attr_cw[0]["dist_c2"] == 1
        # block_gale registrou a aposta colocada (bloco contou)
        assert gs.block_gale_engine.states["cw"].block_bets == 1
        # c_selection registrou feedback (n>=1 nos candidatos)
        assert gs.c_selection_engine._dirs["cw"]["candidates"]["always_c2"].n == 1

    def test_overlay_fields_present_when_active(self):
        os.environ["SDA_STAKING_MODE"] = "block_gale"
        h = _handler()
        si = {"effective_bet": 14, "base_bet": 14, "multiplier": 1.0, "mode": "normal"}
        h._engine_apply_stake(si, 14, "APOSTAR")
        out = h._engine_overlay_fields()
        assert "block_gale" in out and out["block_gale"]["active"] is True
        assert out["block_gale"]["cw"]["cap"] in (1, 2, 3, 4)

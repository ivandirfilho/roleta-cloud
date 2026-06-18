"""Contrato do overlay aditivo nos canais `trace`/`state_sync` (17/06, tarde).

Cobre a correção de UX do front C1/C2 14#:
- `GameState.engine_overlay_fields()` é a FONTE ÚNICA (derivada do estado
  persistente, sem depender do handler) consumida por `trace`/`state_sync`.
- O stake exibido no heartbeat para `block_gale` é o stake REAL do bloco
  (`base_unit × N × MULT[level]`), NÃO o `mg.current_bet` legado (bug BE-2 da
  auditoria: `get_effective_bet` só desvia flat/kelly).
- Campos aditivos e retrocompatíveis (Obrigação ISO #9).
"""
from state.game import GameState


def _gs() -> GameState:
    return GameState()


class TestEngineOverlayFields:
    def test_block_gale_and_bet_gate_always_present(self):
        gs = _gs()
        out = gs.engine_overlay_fields()
        assert "block_gale" in out
        for d in ("cw", "ccw"):
            blk = out["block_gale"][d]
            assert blk["level"] == 1 and blk["cap"] in (1, 2, 3, 4)
            assert blk["block"] == "0/4"
        assert out["bet_gate"]["only_after_green"] is False

    def test_c_selection_derived_from_pending(self):
        gs = _gs()
        # sem pending -> sem c_selection (aditivo)
        assert "c_selection" not in gs.engine_overlay_fields()
        gs.pending_prediction = {"cs_chosen": "C2"}
        cs = gs.engine_overlay_fields()["c_selection"]
        assert cs == {"chosen": "C2", "pair": "C2+C3"}

    def test_ultimo_acerto_green_and_red(self):
        gs = _gs()
        gs.last_number = 26
        gs.last_direction = "anti-horario"
        gs.last_hit_attribution = {"slot": "C2", "dist_min": 1}
        ua = gs.engine_overlay_fields()["ultimo_acerto"]
        # force17 (18/06): inclui o SENTIDO analisado (horário/anti-horário).
        assert ua == {"slot": "C2", "green": True, "numero": 26,
                      "direction": "anti-horario"}

        gs.last_number = 9
        gs.last_direction = "horario"
        gs.last_hit_attribution = {"slot": "miss", "dist_min": 7}
        ua = gs.engine_overlay_fields()["ultimo_acerto"]
        assert ua["green"] is False and ua["numero"] == 9
        assert ua["direction"] == "horario"

    def test_overlay_is_json_serializable(self):
        import json
        gs = _gs()
        gs.pending_prediction = {"cs_chosen": "C1"}
        gs.last_number = 0
        gs.last_hit_attribution = {"slot": "C1"}
        json.dumps(gs.engine_overlay_fields())  # não deve levantar

    def test_force17_regioes_and_dir_bias_in_dashboard_channel(self):
        # force17 (18/06): canal trace/state_sync expõe regioes rotuladas + dir_bias.
        gs = _gs()
        gs.last_direction = "horario"   # target = anti-horario (ccw) -> favoravel
        gs.last_force17_meta = {
            "regioes": [
                {"label": "c2", "center": 30, "radius": 3},
                {"label": "c3", "center": 28, "radius": 2},
                {"label": "c1", "center": 12, "radius": 2, "status": "ok"},
            ],
            "c1_force": {"value": 12, "forca": -7, "status": "ok"},
            "coverage_n": 13,
        }
        out = gs.engine_overlay_fields()
        assert out["force17"]["active"] is True
        assert out["regioes"] == out["force17"]["regioes"]
        assert [r["label"] for r in out["regioes"]] == ["c2", "c3", "c1"]
        assert out["force17"]["coverage_n"] == 13
        assert out["force17"]["dir_bias"] == "favoravel"   # target anti-horario
        import json
        json.dumps(out)  # serializável

    def test_force17_absent_when_no_meta(self):
        gs = _gs()
        assert "force17" not in gs.engine_overlay_fields()  # aditivo


class TestHeartbeatBlockGaleStake:
    """BE-2: o stake do heartbeat para block_gale = base_unit×N×MULT[level]."""

    def test_stake_level1_equals_n_not_current_bet(self):
        gs = _gs()
        # current_bet legado (o que o dashboard mostrava errado) difere do stake real
        legacy = gs.martingale_cw.current_bet
        real = gs.block_gale_engine.stake(gs.target_direction, 14)
        assert real == 14.0           # 1.0 * 14 * MULT[1]=1
        assert real != legacy or legacy == 14  # prova a divergência (legado != 14)

    def test_stake_scales_with_level(self):
        gs = _gs()
        d = gs.target_direction
        gs.block_gale_engine.states["cw"].level = 2
        gs.block_gale_engine.states["ccw"].level = 2
        assert gs.block_gale_engine.stake(d, 14) == 28.0   # MULT[2]=2


class TestPostImplFixes:
    """Auditoria pós-implantação (17/06): active flag + numero consistente."""

    def test_block_gale_active_reflects_staking_mode(self):
        import os
        saved = os.environ.get("SDA_STAKING_MODE")
        try:
            os.environ.pop("SDA_STAKING_MODE", None)  # default 'gale'
            gs = _gs()
            assert gs.engine_overlay_fields()["block_gale"]["active"] is False
            os.environ["SDA_STAKING_MODE"] = "block_gale"
            assert gs.engine_overlay_fields()["block_gale"]["active"] is True
        finally:
            if saved is None:
                os.environ.pop("SDA_STAKING_MODE", None)
            else:
                os.environ["SDA_STAKING_MODE"] = saved

    def test_ultimo_acerto_numero_from_attribution_not_last_number(self):
        # BUG-B: numero deve vir da atribuição (spin verificado), não de last_number
        # (que muda mesmo em spin sem predição) — senão número novo + slot antigo.
        gs = _gs()
        gs.last_number = 99
        gs.last_hit_attribution = {"slot": "C2", "numero": 7}
        ua = gs.engine_overlay_fields()["ultimo_acerto"]
        assert ua["numero"] == 7 and ua["green"] is True

    def test_attribute_hit_region_carries_numero(self):
        attr = GameState._attribute_hit_region([0, 5, 26], [0, 1, 2, 3], 3, True)
        assert attr["numero"] == 3
        attr_miss = GameState._attribute_hit_region([0, 5, 26], [0, 1, 2], 9, False)
        assert attr_miss["numero"] == 9 and attr_miss["slot"] == "miss"

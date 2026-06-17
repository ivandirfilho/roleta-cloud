"""Testes do Block-Gale isolado por sentido (implantação 16/06)."""
from state.block_gale import BlockGaleEngine, BlockGaleState, MULT


class TestBlockGaleRules:
    def test_default_is_flat_g1(self):
        eng = BlockGaleEngine(base_unit=1.0)  # caps default 1 (flat)
        d = eng.decide("horario", bankroll=1000, n_numbers=14)
        assert d["level"] == 1 and d["cap"] == 1 and d["mult"] == 1
        assert d["place"] is True and d["stake"] == 14.0

    def test_escalate_after_one_win_block(self):
        # cap G4; bloco com <=1 vitoria -> sobe um nivel
        eng = BlockGaleEngine(base_unit=1.0, caps={"cw": 4})
        seq = [True, False, False, False]  # 1 win -> escala
        for i, g in enumerate(seq):
            r = eng.on_result("horario", green=g, placed=True)
        assert r["transition"] == "escalate"
        assert eng.states["cw"].level == 2

    def test_reset_with_two_wins(self):
        eng = BlockGaleEngine(base_unit=1.0, caps={"cw": 4})
        # primeiro bloco 1/4 -> G2
        for g in [True, False, False, False]:
            eng.on_result("horario", g, True)
        assert eng.states["cw"].level == 2
        # segundo bloco 2/4 -> reset G1
        for g in [True, True, False, False]:
            r = eng.on_result("horario", g, True)
        assert r["transition"] == "reset"
        assert eng.states["cw"].level == 1

    def test_cap_reset_at_g4(self):
        eng = BlockGaleEngine(base_unit=1.0, caps={"cw": 2})  # teto G2
        # bloco 1: 0/4 -> G2
        for g in [False, False, False, False]:
            eng.on_result("horario", g, True)
        assert eng.states["cw"].level == 2
        # bloco 2: 0/4 no teto -> cap_reset para G1
        for g in [False, False, False, False]:
            r = eng.on_result("horario", g, True)
        assert r["transition"] == "cap_reset"
        assert eng.states["cw"].level == 1

    def test_block_counts_only_placed(self):
        # B2: jogadas nao colocadas nao contam o bloco, mas atualizam last_green
        eng = BlockGaleEngine(base_unit=1.0, caps={"cw": 4})
        eng.on_result("horario", green=False, placed=False)
        eng.on_result("horario", green=True, placed=False)
        assert eng.states["cw"].block_bets == 0
        assert eng.states["cw"].last_green is True

    def test_only_after_green_stake_gate(self):
        # B1: so aposta apos green; gated quando last_green != True
        eng = BlockGaleEngine(base_unit=1.0, caps={"cw": 1}, only_after_green=True)
        d0 = eng.decide("horario", 1000, 14)  # last_green=None -> gated
        assert d0["place"] is False and d0["gated"] is True
        eng.on_result("horario", green=True, placed=False)  # vira green
        d1 = eng.decide("horario", 1000, 14)
        assert d1["place"] is True and d1["gated"] is False

    def test_solvency_refuses_overcover_bet(self):
        # B6/B14: nao aposta a descoberto
        eng = BlockGaleEngine(base_unit=10.0, caps={"cw": 4})
        eng.states["cw"].level = 4  # stake = 10*14*8 = 1120
        d = eng.decide("horario", bankroll=1000, n_numbers=14)
        assert d["solvent"] is False and d["place"] is False and d["stake"] == 0.0

    def test_directions_are_isolated(self):
        eng = BlockGaleEngine(base_unit=1.0, caps={"cw": 4, "ccw": 4})
        for g in [False, False, False, False]:
            eng.on_result("horario", g, True)  # cw -> G2
        assert eng.states["cw"].level == 2
        assert eng.states["ccw"].level == 1  # ccw intacto

    def test_stake_and_pnl_math(self):
        eng = BlockGaleEngine(base_unit=1.0, caps={"cw": 4})
        eng.states["cw"].level = 2  # x2
        assert eng.stake("horario", 14) == 28.0
        assert eng.expected_pnl("horario", 14, green=True) == 2 * (36 - 14)
        assert eng.expected_pnl("horario", 14, green=False) == -2 * 14

    def test_state_roundtrip_and_reset(self):
        eng = BlockGaleEngine(base_unit=2.0, caps={"cw": 3}, only_after_green=True)
        for g in [True, False, False, False]:
            eng.on_result("horario", g, True)
        d = eng.state_dict()
        eng2 = BlockGaleEngine()
        eng2.load_state(d)
        assert eng2.states["cw"].level == eng.states["cw"].level
        assert eng2.base_unit == 2.0 and eng2.only_after_green is True
        # reset limpa o sentido (B8)
        eng2.reset("horario")
        assert eng2.states["cw"].level == 1 and eng2.states["cw"].last_green is None
        assert eng2.states["cw"].cap == 3  # cap preservado

    def test_load_state_clamps_corrupt_level(self):
        # issue#3: level fora de 1..4 (state corrompido) nao deve quebrar MULT[level]
        eng = BlockGaleEngine()
        eng.load_state({"cw": {"level": 6, "cap": 2}, "ccw": {"level": 0, "cap": 1}})
        assert eng.states["cw"].level == 4 and eng.states["ccw"].level == 1
        d = eng.decide("horario", bankroll=100000, n_numbers=14)  # nao deve KeyError
        assert d["mult"] == MULT[eng.states["cw"].level]

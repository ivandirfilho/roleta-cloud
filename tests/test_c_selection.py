"""Testes do CSelectionEngine — seleção C1/C2 variável (16/06)."""
from strategies.c_selection import (
    CSelectionEngine,
    coverage_numbers,
    newcombe_diff_ci,
    _vote_window,
    MIN_N_PROMOTE,
    MAXLEN,
)
from core.roulette import roulette

WHEEL = list(roulette.WHEEL_SEQUENCE)


def _attr(d1, d2, d3):
    return {"dist_c1": d1, "dist_c2": d2, "dist_c3": d3}


class TestVoteRules:
    def test_vote_excludes_c3_dominated(self):
        # 3 jogadas: duas perto de C1, uma dominada por C3 (ignorada)
        hist = [
            _attr(2, 9, 14),    # C1
            _attr(10, 1, 17),   # C2
            _attr(15, 15, 1),   # C3 dominante -> ignorada
            _attr(3, 8, 12),    # C1
        ]
        # ultimas 3 nao-C3 = [C1(2,9), C2(10,1), C1(3,8)] -> maioria C1
        assert _vote_window(hist, 3) == "C1"

    def test_tie_is_neutral_not_c2(self):
        # B12: empate |d1|==|d2| nao vota (neutro). Janela so com empates -> sem maioria
        hist = [_attr(5, 5, 12), _attr(7, 7, 13), _attr(4, 4, 11)]
        assert _vote_window(hist, 3) == ""  # sem maioria estrita

    def test_strict_majority_c2(self):
        hist = [_attr(9, 2, 14), _attr(10, 3, 15), _attr(1, 8, 12)]
        # C2, C2, C1 -> maioria C2
        assert _vote_window(hist, 3) == "C2"


class TestCoverage:
    def test_union_is_14_when_disjoint(self):
        # centros bem separados na roda -> 7+7=14
        nums = coverage_numbers(0, 5, WHEEL, radius=3)
        assert len(nums) == 14

    def test_union_under_14_when_overlap(self):
        # B10: centros proximos -> uniao < 14
        c1 = WHEEL[0]
        c3 = WHEEL[2]  # 2 casas de distancia -> sobreposicao
        nums = coverage_numbers(c1, c3, WHEEL, radius=3)
        assert len(nums) < 14


class TestNewcombe:
    def test_excludes_zero_on_large_clear_difference(self):
        lo, hi = newcombe_diff_ci(90, 100, 40, 100)  # 0.9 vs 0.4
        assert lo > 0.0  # intervalo exclui 0

    def test_includes_zero_on_tiny_difference(self):
        lo, hi = newcombe_diff_ci(39, 100, 40, 100)  # ~igual
        assert lo < 0.0 < hi


class TestEngine:
    def test_select_returns_pair_and_numbers(self):
        eng = CSelectionEngine(radius=3)
        sel = eng.select("horario", centers=[0, 5, 26], attribution_history=[], wheel=WHEEL)
        assert sel.chosen in ("C1", "C2")
        assert sel.pair[1] == "C3"
        assert len(sel.numbers) <= 14 and len(sel.numbers) >= 7
        # escolhas congeladas de todos os candidatos presentes (B5)
        assert "vote_k3_nonc3" in sel.freeze_candidates

    def test_feedback_updates_candidates_and_strong(self):
        eng = CSelectionEngine(radius=3)
        # simula varias jogadas: C2 sempre mais perto e acerta
        for _ in range(20):
            sel = eng.select("horario", [0, 5, 26], [], WHEEL)
            eng.feedback("horario", sel.freeze_candidates, _attr(10, 1, 17))
        st = eng._dirs["cw"]
        assert st["candidates"]["always_c2"].n == 20
        # always_c2 escolheu C2 e C2 acertou (d2=1<=3) -> rate alto
        assert st["candidates"]["always_c2"].rate > 0.9
        assert st["strong"] == "C2"

    def test_state_roundtrip_preserves_deque_maxlen(self):
        eng = CSelectionEngine(radius=3)
        for _ in range(5):
            sel = eng.select("anti-horario", [0, 5, 26], [], WHEEL)
            eng.feedback("anti-horario", sel.freeze_candidates, _attr(2, 9, 14))
        d = eng.state_dict()
        eng2 = CSelectionEngine()
        eng2.load_state(d)
        # deque reconstruido com maxlen
        cs = eng2._dirs["ccw"]["candidates"]["vote_k3_nonc3"]
        assert cs.hits.maxlen == MAXLEN and MAXLEN >= MIN_N_PROMOTE
        assert eng2._dirs["ccw"]["incumbent"] == eng._dirs["ccw"]["incumbent"]

    def test_reset_clears_direction(self):
        eng = CSelectionEngine(radius=3)
        for _ in range(5):
            sel = eng.select("horario", [0, 5, 26], [], WHEEL)
            eng.feedback("horario", sel.freeze_candidates, _attr(2, 9, 14))
        eng.reset("horario")
        assert eng._dirs["cw"]["candidates"]["vote_k3_nonc3"].n == 0

    def test_no_autopromote_by_default(self):
        # sem auto_promote, incumbente permanece always_strong mesmo com dados
        eng = CSelectionEngine(radius=3)
        for _ in range(200):
            sel = eng.select("horario", [0, 5, 26], [], WHEEL)
            eng.feedback("horario", sel.freeze_candidates, _attr(10, 1, 17))
        assert eng._dirs["cw"]["incumbent"] == "always_strong"

    def test_select_handles_fewer_than_3_centers(self):
        # B-impl: caminho de fallback nao deve quebrar (IndexError)
        eng = CSelectionEngine(radius=3)
        sel = eng.select("horario", [7], [], WHEEL)
        assert sel.chosen == "C1" and "fallback" in sel.reason
        assert len(sel.numbers) >= 1

    def test_vote_tolerates_missing_dist_keys(self):
        # B-impl: atribuicao sem dist_c2/c3 (bug historico 12/06) nao quebra
        eng = CSelectionEngine(radius=3)
        hist = [{"dist_c1": 2}, {"dist_c1": 1, "dist_c2": 9, "dist_c3": 14}]
        sel = eng.select("horario", [0, 5, 26], hist, WHEEL)
        assert sel.chosen in ("C1", "C2")
        eng.feedback("horario", sel.freeze_candidates, {"dist_c1": 2})  # sem c2/c3


class TestStaticSelect:
    """Par estático fixo (decisão 17/06: c2c3 fixo em vez do voto)."""

    def test_c2c3_picks_c2_and_c3_union(self):
        eng = CSelectionEngine(radius=3)
        sel = eng.static_select("horario", [0, 5, 26], "c2c3", WHEEL)
        assert sel.chosen == "C2"
        assert sel.pair == ("C2", "C3")
        assert sel.rule == "static_c2c3"
        assert sel.freeze_candidates == {}            # sem shadow -> sem feedback
        assert sel.numbers == coverage_numbers(5, 26, WHEEL, 3)

    def test_c1c3_picks_c1_and_c3_union(self):
        eng = CSelectionEngine(radius=3)
        sel = eng.static_select("anti-horario", [0, 5, 26], "c1c3", WHEEL)
        assert sel.chosen == "C1"
        assert sel.numbers == coverage_numbers(0, 26, WHEEL, 3)

    def test_static_is_deterministic_and_stateless(self):
        # sem variar: mesma entrada -> mesma saída; não toca o estado dos candidatos
        eng = CSelectionEngine(radius=3)
        a = eng.static_select("horario", [0, 5, 26], "c2c3", WHEEL)
        b = eng.static_select("horario", [0, 5, 26], "c2c3", WHEEL)
        assert a.numbers == b.numbers and a.chosen == b.chosen == "C2"
        assert eng._dirs["cw"]["candidates"]["vote_k3_nonc3"].n == 0

    def test_static_fallback_under_3_centers(self):
        eng = CSelectionEngine(radius=3)
        sel = eng.static_select("horario", [7], "c2c3", WHEEL)
        assert "fallback" in sel.reason and len(sel.numbers) >= 1
        assert sel.chosen == "C2" and sel.pair == ("C2", "C3")
        # fallback respeita o par pedido (c1c3 -> C1)
        sel1 = eng.static_select("horario", [7], "c1c3", WHEEL)
        assert sel1.chosen == "C1" and sel1.pair == ("C1", "C3")

    def test_tolerates_none_distances(self):
        # issue#2: _attribute_hit_region poe dist_c2/c3=None (chave existe!) -> abs(None) quebrava
        eng = CSelectionEngine(radius=3)
        hist = [{"dist_c1": -1, "dist_c2": None, "dist_c3": None}]
        sel = eng.select("horario", [0, 5, 26], hist, WHEEL)
        eng.feedback("horario", sel.freeze_candidates, {"dist_c1": -1, "dist_c2": None, "dist_c3": None})
        assert sel.chosen in ("C1", "C2")

    def test_autopromote_fires_with_clear_winner(self):
        # issue#1: com MAXLEN>=MIN_N_PROMOTE e auto_promote, a promocao DISPARA.
        eng = CSelectionEngine(radius=3)
        eng._dirs["cw"]["incumbent"] = "always_c2"  # incumbente fraco de proposito
        # C1 sempre acerta (d1=1), C2 sempre erra (d2=15): always_strong/vote dominam always_c2
        for _ in range(MIN_N_PROMOTE + 20):
            sel = eng.select("horario", [0, 5, 26], [], WHEEL)
            eng.feedback("horario", sel.freeze_candidates, _attr(1, 15, 9), auto_promote=True)
        st = eng._dirs["cw"]
        assert st["candidates"]["always_c2"].n >= MIN_N_PROMOTE
        # promovido p/ fora de always_c2 (Newcombe excluiu 0)
        assert st["incumbent"] != "always_c2"
        assert st["candidates"][st["incumbent"]].rate > st["candidates"]["always_c2"].rate
        sel = eng.select("horario", [0, 5, 26], [], WHEEL)
        assert sel.confidence == 1.0

    def test_load_state_rejects_invalid_incumbent(self):
        # issue#3: incumbent invalido cai p/ default sem KeyError
        eng = CSelectionEngine(radius=3)
        eng.load_state({"radius": 3, "cw": {"incumbent": "regra_inexistente"}})
        sel = eng.select("horario", [0, 5, 26], [], WHEEL)  # nao deve quebrar
        assert eng._dirs["cw"]["incumbent"] == "always_strong"

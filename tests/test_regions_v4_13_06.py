"""Testes da Refatoração V4 — Regiões disjuntas C1/C2/C3 (13/06).

Cobre as invariantes provadas na auditoria (refatoracao_estrategica_13_06.md §11):
- sempre 21 números distintos; 3 regiões mutuamente disjuntas;
- determinismo; INV-3 no warmup; rollback exato com a flag OFF;
- gravidade CIRCULAR de força (BUG-C); empurrão de C2 (BUG-J/D);
- zona fria de C3; ciclo de vida do recent_results no GameState (BUG-F).
"""
import os
import random
import unittest

from strategies.sda17 import SDA17Strategy
from state.timeline import Timeline
from state.game import GameState
from core import roulette

WHEEL = list(roulette.WHEEL_SEQUENCE)
SIZE = len(WHEEL)


def _circ(a: int, b: int) -> int:
    i, j = WHEEL.index(a), WHEEL.index(b)
    d = abs(i - j)
    return min(d, SIZE - d)


def _mk_timeline(forces, direction="cw") -> Timeline:
    tl = Timeline(direction=direction)
    for f in reversed(forces):  # idx0 = mais recente
        tl.add(f)
    return tl


class TestV4Helpers(unittest.TestCase):
    def setUp(self):
        self.s = SDA17Strategy()

    def test_circ_force_is_circular(self):
        # BUG-C: força 36 e força 2 projetam a 3 casas → distância circular pequena
        self.assertEqual(self.s._circ_force(36, 2, SIZE), 3)
        self.assertEqual(self.s._circ_force(2, 36, SIZE), 3)
        self.assertEqual(self.s._circ_force(10, 10, SIZE), 0)
        self.assertEqual(self.s._circ_force(10, 17, SIZE), 7)

    def test_c2_gravity_picks_max_cover(self):
        # c1_force=10; 30 e 31 ficam fora do alvo (circ>7) e juntos → cluster
        out = self.s._compute_c2_gravity([10, 9, 30, 31], 10, SIZE)
        self.assertEqual(out, 30)  # empate de cobertura → mais recente (30)

    def test_c2_gravity_fallback_when_no_residual(self):
        # Todas as forças dentro da gravidade de C1 → prior (c1_force + default)
        out = self.s._compute_c2_gravity([10, 11, 9, 12], 10, SIZE)
        self.assertEqual(out, 10 + self.s.BAYESIAN_DEFAULT)

    def test_c2_window_is_four(self):
        # Só as 4 primeiras forças entram (a 5ª deve ser ignorada)
        a = self.s._compute_c2_gravity([10, 9, 30, 31, 5], 10, SIZE)
        b = self.s._compute_c2_gravity([10, 9, 30, 31], 10, SIZE)
        self.assertEqual(a, b)

    def test_disjoint_threshold(self):
        # centros a >=7 casas são disjuntos; <7 não
        c0 = WHEEL[0]
        self.assertTrue(self.s._regions_disjoint(c0, WHEEL[7], WHEEL))
        self.assertFalse(self.s._regions_disjoint(c0, WHEEL[6], WHEEL))

    def test_nearest_non_overlapping_pushes(self):
        c1 = WHEEL[0]
        c2_ideal = WHEEL[2]  # sobrepõe C1 (circ=2)
        c2 = self.s._nearest_non_overlapping(c2_ideal, [c1], WHEEL)
        self.assertGreaterEqual(_circ(c2, c1), 7)

    def test_c3_cold_avoids_hot_zone(self):
        # 5 resultados todos no número 0 → C3 deve evitar a vizinhança de 0
        hot = WHEEL[0]
        occ = [WHEEL[12], WHEEL[24]]  # disjuntos entre si e de 0
        c3 = self.s._compute_c3_cold([hot] * 5, occ, WHEEL)
        self.assertGreater(_circ(c3, hot), 3)  # fora da região quente
        self.assertTrue(all(self.s._regions_disjoint(c3, o, WHEEL) for o in occ))


class TestV4Composition(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get("SDA_REGIONS_V4")
        os.environ["SDA_REGIONS_V4"] = "1"

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SDA_REGIONS_V4", None)
        else:
            os.environ["SDA_REGIONS_V4"] = self._prev

    def test_always_21_and_disjoint_fuzz(self):
        random.seed(13)
        for _ in range(2000):
            s = SDA17Strategy()
            d = random.choice(["cw", "ccw"])
            forces = [random.randint(1, 37) for _ in range(random.randint(0, 7))]
            last = random.choice(WHEEL)
            rn = [random.choice(WHEEL) for _ in range(random.randint(0, 5))]
            tl = _mk_timeline(forces, d)
            r = s.analyze(tl, last, WHEEL, recent_numbers=rn)
            if not r.should_bet:
                # só aceitável com <2 forças (fallback fora da estratégia)
                self.assertLess(len([f for f in forces if f > 0]), 2)
                continue
            c = r.details["centers"]
            self.assertEqual(len(r.numbers), 21, msg=f"centers={c} forces={forces}")
            self.assertEqual(len(set(r.numbers)), 21)
            self.assertTrue(
                all(_circ(c[i], c[j]) >= 7 for i in range(3) for j in range(i + 1, 3)),
                msg=f"não-disjunto: {c}",
            )

    def test_determinism(self):
        s = SDA17Strategy()
        tl = _mk_timeline([25, 22, 19, 28, 6, 11])
        r1 = s.analyze(tl, 0, WHEEL, recent_numbers=[3, 7, 12, 0, 36])
        s2 = SDA17Strategy()
        tl2 = _mk_timeline([25, 22, 19, 28, 6, 11])
        r2 = s2.analyze(tl2, 0, WHEEL, recent_numbers=[3, 7, 12, 0, 36])
        self.assertEqual(r1.numbers, r2.numbers)
        self.assertEqual(r1.details["centers"], r2.details["centers"])

    def test_inv3_warmup_still_21(self):
        # 2 forças (mínimo p/ triple focus) + 1 resultado → 21, sempre aposta
        s = SDA17Strategy()
        tl = _mk_timeline([20, 9])
        r = s.analyze(tl, 0, WHEEL, recent_numbers=[5])
        self.assertTrue(r.should_bet)
        self.assertEqual(len(r.numbers), 21)

    def test_geometry_label(self):
        s = SDA17Strategy()
        tl = _mk_timeline([25, 22, 19, 28, 6, 11])
        r = s.analyze(tl, 0, WHEEL, recent_numbers=[3, 7, 12, 0, 36])
        self.assertEqual(r.details["geometry"], "7+7+7")
        self.assertEqual(r.details["method"], "regions_v4_gravity_cold")


class TestV4Rollback(unittest.TestCase):
    """Flag OFF (default) ⇒ geometria atual intacta (V2 17 números)."""

    def setUp(self):
        self._prev = os.environ.get("SDA_REGIONS_V4")
        os.environ["SDA_REGIONS_V4"] = "0"

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SDA_REGIONS_V4", None)
        else:
            os.environ["SDA_REGIONS_V4"] = self._prev

    def test_off_is_legacy_17(self):
        s = SDA17Strategy()
        tl = _mk_timeline([25, 22, 19, 28, 6, 11])
        r = s.analyze(tl, 0, WHEEL, recent_numbers=[3, 7, 12, 0, 36])
        self.assertEqual(len(r.numbers), 17)
        self.assertNotEqual(r.details["method"], "regions_v4_gravity_cold")

    def test_recent_numbers_param_is_optional(self):
        # Compat: chamar sem recent_numbers não quebra (assinatura retrocompatível)
        s = SDA17Strategy()
        tl = _mk_timeline([25, 22, 19, 28, 6, 11])
        r = s.analyze(tl, 0, WHEEL)
        self.assertEqual(len(r.numbers), 17)


class TestGameStateRecentResults(unittest.TestCase):
    def test_process_spin_populates_and_order(self):
        gs = GameState()
        for num, dirn in [(5, "horario"), (12, "anti-horario"), (0, "horario")]:
            gs.process_spin(num, dirn)
        self.assertEqual(list(gs.recent_results), [0, 12, 5])  # idx0 = mais recente

    def test_reset_session_clears(self):
        gs = GameState()
        for num in (5, 12, 0):
            gs.process_spin(num, "horario")
        gs.reset_session()
        self.assertEqual(list(gs.recent_results), [])

    def test_save_load_roundtrip(self):
        import tempfile
        from pathlib import Path
        gs = GameState()
        for num, dirn in [(5, "horario"), (12, "anti-horario"), (0, "horario")]:
            gs.process_spin(num, dirn)
        p = Path(tempfile.gettempdir()) / "rc_v4_state_test.json"
        gs.save(p)
        gs2 = GameState.load(p)
        self.assertEqual(list(gs.recent_results), list(gs2.recent_results))
        p.unlink(missing_ok=True)

    def test_load_without_field_is_empty(self):
        # state.json antigo (sem recent_results) → deque vazio, sem crash
        import json
        import tempfile
        from pathlib import Path
        p = Path(tempfile.gettempdir()) / "rc_v4_old_state.json"
        p.write_text(json.dumps({"version": "2.0.0", "last_number": 7}), encoding="utf-8")
        gs = GameState.load(p)
        self.assertEqual(list(gs.recent_results), [])
        p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

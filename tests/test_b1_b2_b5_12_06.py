"""Implantação 12/06 — B1 (reset adaptativo), B2 (hit_region), B5 (CUT-POLICY v1 + PROFIT-LEDGER).

Cobre os fixes do plano proximos_passos_10_06.md (premissas P5/P8/P9/P10 do owner):
- B1: SDA17Strategy.reset_adaptive() zera TODO o estado por direção (botão de dealer).
- B2: GameState._attribute_hit_region classifica resultado em C1/C2/C3/miss + dist
       circular; check_prediction popula last_hit_attribution; repo persiste
       result_region.
- B5: gale<=2 sob PROFIT_CUT_V1; fallback N=21 (nunca N=19); pnl_units por decisão
       agregado em sessions.total_profit; session_pnl_stats para o gauge.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from core.roulette import roulette
from database.models import Decision, Session
from database.sqlite_repo import SQLiteDecisionRepository
from state.game import GameState, MartingaleState
from strategies.sda17 import SDA17Strategy

WHEEL = list(roulette.WHEEL_SEQUENCE)
SIZE = len(WHEEL)


def _at(center: int, offset: int) -> int:
    """Número da roda a `offset` posições de `center` (sentido da sequência)."""
    return WHEEL[(WHEEL.index(center) + offset) % SIZE]


class TestB1ResetAdaptive(unittest.TestCase):
    """B1 — reset TOTAL do estado adaptativo na troca de dealer (P10)."""

    def _dirty_strategy(self) -> SDA17Strategy:
        s = SDA17Strategy()
        s.cw_history = [(10, 23), (5, 17)]
        s.ccw_history = [(8, 30)]
        s._sigmoid_off = {"cw_off2": 12.5, "ccw_off3": 7.2}
        s._recent_hits = {"cw": [1, 0, 1], "ccw": [0, 0]}
        s._cooldown["cw"]["c2"] = 2
        s._drift_freeze["ccw"] = 3
        s._pending_spins = {"cw": 3, "ccw": 1}
        s._batch_runs_total = {"cw": 5, "ccw": 4}
        return s

    def test_reset_clears_all_per_direction_state(self):
        s = self._dirty_strategy()
        discarded = s.reset_adaptive()

        self.assertEqual(s.cw_history, [])
        self.assertEqual(s.ccw_history, [])
        self.assertEqual(s._sigmoid_off, {})
        self.assertEqual(s._recent_hits, {"cw": [], "ccw": []})
        self.assertEqual(s._cooldown["cw"]["c2"], 0)
        self.assertEqual(s._drift_freeze["ccw"], 0)
        self.assertEqual(s._pending_spins, {"cw": 0, "ccw": 0})
        self.assertEqual(s._batch_runs_total, {"cw": 0, "ccw": 0})
        # Snapshot de auditoria reporta o que foi descartado.
        self.assertEqual(discarded["cw_history_len"], 2)
        self.assertEqual(discarded["sigmoid_off"], {"cw_off2": 12.5, "ccw_off3": 7.2})

    def test_reset_rearms_generic_prior_and_warmup(self):
        """P8/P9: pós-reset, offsets voltam ao prior genérico (default 10/10)."""
        s = self._dirty_strategy()
        s.reset_adaptive()
        off_c2, off_c3 = s._get_adaptive_offset("cw")
        self.assertEqual((off_c2, off_c3), (s.BAYESIAN_DEFAULT, s.BAYESIAN_DEFAULT))
        # get_adaptive_state pós-reset não vaza estado antigo.
        state = s.get_adaptive_state()
        self.assertEqual(state["cw_history"], [])
        self.assertEqual(state["sigmoid_off"], {})


class TestB2HitRegionAttribution(unittest.TestCase):
    """B2 — atribuição por região responde P5 (em qual região caiu?)."""

    def _centers(self):
        c1 = 0
        c2 = _at(c1, 10)
        c3 = _at(c1, -10)
        return c1, c2, c3

    def _numbers(self, c1, c2, c3):
        nums = set(roulette.get_neighbors(c1, 3))
        nums |= set(roulette.get_neighbors(c2, 2))
        nums |= set(roulette.get_neighbors(c3, 2))
        return sorted(nums)

    def test_hit_in_c1(self):
        c1, c2, c3 = self._centers()
        numbers = self._numbers(c1, c2, c3)
        actual = _at(c1, 2)
        attr = GameState._attribute_hit_region([c1, c2, c3], numbers, actual, True)
        self.assertEqual(attr["slot"], "C1")
        self.assertEqual(attr["dist_c1"], 2)

    def test_hit_in_c2_and_c3(self):
        c1, c2, c3 = self._centers()
        numbers = self._numbers(c1, c2, c3)
        attr2 = GameState._attribute_hit_region(
            [c1, c2, c3], numbers, _at(c2, -1), True
        )
        self.assertEqual(attr2["slot"], "C2")
        attr3 = GameState._attribute_hit_region(
            [c1, c2, c3], numbers, _at(c3, 1), True
        )
        self.assertEqual(attr3["slot"], "C3")
        self.assertEqual(attr3["dist_min"], 1)

    def test_miss_keeps_distances(self):
        c1, c2, c3 = self._centers()
        numbers = self._numbers(c1, c2, c3)
        actual = _at(c1, 18)  # lado oposto da roda
        attr = GameState._attribute_hit_region([c1, c2, c3], numbers, actual, False)
        self.assertEqual(attr["slot"], "miss")
        self.assertEqual(abs(attr["dist_c1"]), 18)

    def test_fallback_single_center_counts_as_c1(self):
        c1 = 0
        numbers = sorted(roulette.get_neighbors(c1, 10))  # N=21
        actual = _at(c1, 8)
        attr = GameState._attribute_hit_region([c1], numbers, actual, True)
        self.assertEqual(attr["slot"], "C1")

    def test_satellite_hit_beyond_legacy_radius(self):
        # FIX 13/06: geometria viva fat-SAT (C1 raio 1; satélites raio 3, ou 4
        # no V3). Antes, acerto de satélite a 3-4 casas caía em 'unattributed'
        # (raio legado fixo 2), subcontando C2/C3. Agora o centro mais próximo
        # classifica corretamente — nunca 'unattributed' com hit válido.
        c1, c2, c3 = self._centers()
        nums = set(roulette.get_neighbors(c1, 1))
        nums |= set(roulette.get_neighbors(c2, 3))
        nums |= set(roulette.get_neighbors(c3, 3))
        numbers = sorted(nums)
        actual = _at(c2, 3)  # coberto (raio 3) mas fora do raio legado 2
        self.assertIn(actual, numbers)
        attr = GameState._attribute_hit_region([c1, c2, c3], numbers, actual, True)
        self.assertEqual(attr["slot"], "C2")

    def test_check_prediction_populates_attribution(self):
        gs = GameState()
        c1, c2, c3 = self._centers()
        numbers = self._numbers(c1, c2, c3)
        gs.store_prediction(numbers, "cw", c1, sda_centers=[c1, c2, c3])
        hit = gs.check_prediction(_at(c2, 1))
        self.assertTrue(hit)
        self.assertIsNotNone(gs.last_hit_attribution)
        self.assertEqual(gs.last_hit_attribution["slot"], "C2")


class TestB5RepoLedgerAndRegion(unittest.TestCase):
    """B5 — PROFIT-LEDGER no repo + B2 result_region persistido."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.repo = SQLiteDecisionRepository(db_path=self.tmp)
        self.repo.create_session(Session(id="sess-test"))

    def tearDown(self):
        try:
            os.unlink(self.tmp)
        except OSError:
            pass

    def _decision(self, n_numbers=17, action="APOSTAR", bet=17) -> int:
        d = Decision(
            session_id="sess-test",
            final_action=action,
            sda_numbers=list(range(n_numbers)),
            gale_bet_value=bet,
        )
        return self.repo.save_decision(d)

    def test_pnl_hit_and_region_written(self):
        did = self._decision()
        self.repo.update_result(did, True, 5, result_region="C2")
        import sqlite3
        conn = sqlite3.connect(self.tmp)
        row = conn.execute(
            "SELECT result_region, pnl_units FROM decisions WHERE id=?", (did,)
        ).fetchone()
        profit = conn.execute(
            "SELECT total_profit FROM sessions WHERE id='sess-test'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(row[0], "C2")
        # 17u distribuídos em 17 números, payout 36:1 → +19u no hit.
        self.assertAlmostEqual(row[1], 19.0, places=3)
        self.assertAlmostEqual(profit, 19.0, places=3)

    def test_pnl_miss_aggregates_negative(self):
        did1 = self._decision()
        did2 = self._decision(bet=34)
        self.repo.update_result(did1, False, 5, result_region="miss")
        self.repo.update_result(did2, False, 7, result_region="miss")
        self.assertAlmostEqual(self.repo.get_session_pnl("sess-test"), -51.0, places=3)
        stats = self.repo.session_pnl_stats()
        self.assertAlmostEqual(stats["all_time_pnl"], -51.0, places=3)

    def test_pular_decision_has_no_pnl(self):
        did = self._decision(action="PULAR")
        self.repo.update_result(did, True, 5, result_region="C1")
        import sqlite3
        conn = sqlite3.connect(self.tmp)
        pnl = conn.execute(
            "SELECT pnl_units FROM decisions WHERE id=?", (did,)
        ).fetchone()[0]
        conn.close()
        self.assertIsNone(pnl)
        self.assertAlmostEqual(self.repo.get_session_pnl("sess-test"), 0.0, places=3)


class TestB5CutPolicyGates(unittest.TestCase):
    """B5 — CUT-POLICY v1: gale<=2 e fallback N=21 sob a flag (default ON)."""

    def setUp(self):
        self._saved = os.environ.get("PROFIT_CUT_V1")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("PROFIT_CUT_V1", None)
        else:
            os.environ["PROFIT_CUT_V1"] = self._saved

    def test_flag_default_is_on_when_env_unset(self):
        """Produção sem env → policy ATIVA (decisão B5: aplicar já)."""
        os.environ.pop("PROFIT_CUT_V1", None)
        from app_config.settings import profit_cut_v1_enabled
        self.assertTrue(profit_cut_v1_enabled())

    def test_gale_capped_at_2_with_flag_on(self):
        os.environ["PROFIT_CUT_V1"] = "1"
        mg = MartingaleState()
        mg.global_consecutive_hits = 3  # streak pediria G3
        level = mg.get_gale(score=5, c4_rate=0.6, confidence="media")
        self.assertEqual(level, 2)

    def test_gale_3_allowed_with_flag_off(self):
        os.environ["PROFIT_CUT_V1"] = "0"
        mg = MartingaleState()
        mg.global_consecutive_hits = 3
        level = mg.get_gale(score=5, c4_rate=0.6, confidence="media")
        self.assertEqual(level, 3)

    def _first_play_fallback_numbers(self):
        """Fallback de 1 centro: raio decidido por _fallback_radius()."""
        s = SDA17Strategy()
        radius = s._fallback_radius()
        return sorted(roulette.get_neighbors(0, radius)), radius

    def test_fallback_is_n21_with_flag_on(self):
        os.environ["PROFIT_CUT_V1"] = "1"
        numbers, radius = self._first_play_fallback_numbers()
        self.assertEqual(radius, 10)
        self.assertEqual(len(numbers), 21)

    def test_fallback_is_n19_with_flag_off(self):
        os.environ["PROFIT_CUT_V1"] = "0"
        numbers, radius = self._first_play_fallback_numbers()
        self.assertEqual(radius, 9)
        self.assertEqual(len(numbers), 19)


if __name__ == "__main__":
    unittest.main()

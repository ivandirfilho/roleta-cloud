"""SP-08 DNA-03: realized_lift_pp batch realizer."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import dna_logger


class TestRealizeLifts(unittest.TestCase):
    def setUp(self):
        dna_logger.reset_for_tests()
        self.db = tempfile.mktemp(suffix=".db")
        dna_logger.configure(self.db)

    def tearDown(self):
        dna_logger.reset_for_tests()

    def _emit(self, did, bucket, hit):
        dna_logger.dna_log_feature(did, "test_f", {"raw": 1, "bucket": bucket})
        dna_logger.dna_update_realized(did, hit=hit, wheel_dist=2 if hit else 7)

    def test_lift_calc(self):
        # bucket "hot": 8 hits / 10 (hr=0.8)
        for i in range(8):
            self._emit(100 + i, "hot", True)
        for i in range(2):
            self._emit(108 + i, "hot", False)
        # bucket "cold": 2 hits / 10 (hr=0.2)
        for i in range(2):
            self._emit(200 + i, "cold", True)
        for i in range(8):
            self._emit(202 + i, "cold", False)
        # baseline = 10/20 = 0.5
        # hot lift = (0.8 - 0.5) * 100 = +30 pp
        # cold lift = (0.2 - 0.5) * 100 = -30 pp
        updated = dna_logger.dna_realize_lifts(min_n=5)
        self.assertEqual(updated, 20)

        import sqlite3
        conn = sqlite3.connect(self.db)
        row = conn.execute(
            "SELECT AVG(realized_lift_pp) FROM decision_dna "
            "WHERE json_extract(feature_value,'$.bucket')='hot'"
        ).fetchone()
        self.assertAlmostEqual(row[0], 30.0, places=2)
        row = conn.execute(
            "SELECT AVG(realized_lift_pp) FROM decision_dna "
            "WHERE json_extract(feature_value,'$.bucket')='cold'"
        ).fetchone()
        self.assertAlmostEqual(row[0], -30.0, places=2)

    def test_min_n_skips_small_buckets(self):
        for i in range(3):
            self._emit(i, "tiny", True)
        updated = dna_logger.dna_realize_lifts(min_n=10)
        self.assertEqual(updated, 0)

    def test_no_op_if_no_realized(self):
        dna_logger.dna_log_feature(1, "f", {"raw": 1, "bucket": "x"})
        self.assertEqual(dna_logger.dna_realize_lifts(), 0)

    # ---- H1 (03/08): lifts POR SENTIDO -----------------------------------

    def _emit_dir(self, did, bucket, hit, direction):
        dna_logger.dna_log_feature(
            did, "test_f", {"raw": 1, "bucket": bucket}, direction=direction
        )
        dna_logger.dna_update_realized(did, hit=hit, wheel_dist=2 if hit else 7)

    def test_lift_per_direction_isolated(self):
        # CW: bucket "hot" 8/10 hits; baseline cw = 0.8 → lift cw = 0 pp
        for i in range(8):
            self._emit_dir(300 + i, "hot", True, "cw")
        for i in range(2):
            self._emit_dir(308 + i, "hot", False, "cw")
        # CCW: bucket "hot" 2/10 hits; baseline ccw = 0.2 → lift ccw = 0 pp
        for i in range(2):
            self._emit_dir(400 + i, "hot", True, "ccw")
        for i in range(8):
            self._emit_dir(402 + i, "hot", False, "ccw")

        updated = dna_logger.dna_realize_lifts(min_n=5)
        self.assertEqual(updated, 20)

        import sqlite3
        conn = sqlite3.connect(self.db)
        # Cada sentido comparado com o PRÓPRIO baseline → lift 0 nos dois,
        # apesar de hit rates opostos (0.8 vs 0.2). Uma pool única daria
        # +30/-30 pp — exatamente a contaminação que H1 elimina.
        for direction in ("cw", "ccw"):
            row = conn.execute(
                "SELECT AVG(realized_lift_pp), COUNT(*) FROM decision_dna "
                "WHERE direction = ? AND realized_lift_pp IS NOT NULL",
                (direction,),
            ).fetchone()
            self.assertEqual(row[1], 10)
            self.assertAlmostEqual(row[0], 0.0, places=2)
        conn.close()

    def test_direction_null_does_not_pollute_cw(self):
        # legado NULL: 10 rows todas miss; cw: 5 hits / 5 miss
        for i in range(10):
            self._emit(500 + i, "mix", False)
        for i in range(5):
            self._emit_dir(600 + i, "mix", True, "cw")
        for i in range(5):
            self._emit_dir(605 + i, "mix", False, "cw")

        updated = dna_logger.dna_realize_lifts(min_n=5)
        self.assertEqual(updated, 20)

        import sqlite3
        conn = sqlite3.connect(self.db)
        row = conn.execute(
            "SELECT AVG(realized_lift_pp) FROM decision_dna WHERE direction = 'cw'"
        ).fetchone()
        # baseline cw = 0.5 (NULLs fora) → lift cw = 0; pool única daria +17 pp
        self.assertAlmostEqual(row[0], 0.0, places=2)
        conn.close()

    def test_rerun_is_noop(self):
        for i in range(6):
            self._emit_dir(700 + i, "b", i % 2 == 0, "cw")
        first = dna_logger.dna_realize_lifts(min_n=3)
        self.assertEqual(first, 6)
        # idempotente: só preenche onde realized_lift_pp IS NULL
        self.assertEqual(dna_logger.dna_realize_lifts(min_n=3), 0)


if __name__ == "__main__":
    unittest.main()

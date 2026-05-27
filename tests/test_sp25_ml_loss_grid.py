"""SP-25 ML-01: grid search."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.ml_loss_grid import grid_search, _wheel_dist, _slot_offset


class TestWheelMath(unittest.TestCase):
    def test_dist_self_zero(self):
        self.assertEqual(_wheel_dist(0, 0), 0)

    def test_dist_neighbors(self):
        # WHEEL[0]=0 WHEEL[1]=32 -> distance 1
        self.assertEqual(_wheel_dist(0, 32), 1)

    def test_slot_offset_wraps(self):
        # offset 37 = 0
        self.assertEqual(_slot_offset(0, 37), 0)


def _seed(db, rows):
    """rows = [(sda_center, result_actual)]"""
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS decisions(
            id INTEGER PRIMARY KEY,
            sda_center INTEGER,
            result_actual INTEGER,
            final_action TEXT
        );
        """
    )
    for c, r in rows:
        conn.execute(
            "INSERT INTO decisions(sda_center, result_actual, final_action) VALUES (?, ?, 'APOSTAR')",
            (c, r),
        )
    conn.commit()
    conn.close()


class TestGridSearch(unittest.TestCase):
    def test_no_data(self):
        db = tempfile.mktemp(suffix=".db")
        _seed(db, [])
        r = grid_search(db, 0.05, -2, 2)
        self.assertIn("error", r)

    def test_perfect_offset(self):
        # Sempre center=0 e actual=32 (=WHEEL[1]). Offset +1 deveria zerar dist.
        db = tempfile.mktemp(suffix=".db")
        _seed(db, [(0, 32)] * 50)
        r = grid_search(db, 0.05, -3, 3)
        self.assertEqual(r["best_offset"], 1)
        self.assertEqual(r["best_median_dist"], 0)
        self.assertAlmostEqual(r["best_hit_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()

"""SP-18 REGION-03: bandit epsilon-greedy."""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategies.region_bandit import choose_region


def _row(fn, n, lift):
    return {"feature_name": fn, "bucket": "zero", "n": n, "hit_rate": 0.5, "avg_lift_pp": lift}


class TestRegionBandit(unittest.TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(choose_region([]))

    def test_below_min_n_none(self):
        rows = [_row("region_C1", 5, 10.0), _row("region_C2", 8, -5.0)]
        self.assertIsNone(choose_region(rows, min_n=20))

    def test_exploit_picks_best(self):
        rows = [
            _row("region_C1", 50, -5.0),
            _row("region_C2", 50, 12.0),
            _row("region_C3", 50, 3.0),
        ]
        # epsilon=0 => puro exploit
        self.assertEqual(choose_region(rows, epsilon=0.0, min_n=20), "C2")

    def test_explore_uniform(self):
        rows = [
            _row("region_C1", 50, -5.0),
            _row("region_C2", 50, 12.0),
        ]
        r = random.Random(42)
        # epsilon=1.0 => sempre explora
        chosen = {choose_region(rows, epsilon=1.0, min_n=20, rng=r) for _ in range(20)}
        self.assertTrue(chosen.issubset({"C1", "C2"}))
        self.assertGreaterEqual(len(chosen), 1)

    def test_ignores_non_region_features(self):
        rows = [_row("sda_score", 999, 100.0), _row("region_C1", 30, 5.0)]
        self.assertEqual(choose_region(rows, epsilon=0.0, min_n=20), "C1")


if __name__ == "__main__":
    unittest.main()

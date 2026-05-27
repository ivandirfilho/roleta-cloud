"""SP-29 OBS-01: DNA realize lag stats."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import dna_logger


class TestDnaRealizeStats(unittest.TestCase):
    def setUp(self):
        dna_logger.reset_for_tests()
        self.db = tempfile.mktemp(suffix=".db")
        dna_logger.configure(self.db)

    def tearDown(self):
        dna_logger.reset_for_tests()

    def test_empty(self):
        s = dna_logger.dna_realize_stats()
        self.assertEqual(s, {"unrealized": 0, "lag_seconds": 0})

    def test_unrealized_count(self):
        dna_logger.dna_log_feature(1, "test_f", {"raw": 1, "bucket": "x"})
        dna_logger.dna_log_feature(2, "test_f", {"raw": 2, "bucket": "y"})
        s = dna_logger.dna_realize_stats()
        self.assertEqual(s["unrealized"], 2)
        self.assertGreaterEqual(s["lag_seconds"], 0)

    def test_realized_excluded(self):
        dna_logger.dna_log_feature(10, "f", {"raw": 1, "bucket": "x"})
        dna_logger.dna_update_realized(10, hit=True, wheel_dist=2)
        s = dna_logger.dna_realize_stats()
        self.assertEqual(s["unrealized"], 0)
        self.assertEqual(s["lag_seconds"], 0)


if __name__ == "__main__":
    unittest.main()

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

    def test_terminal_orphan_excluded(self):
        """Feature órfã terminal (atrás de uma já realizada) NÃO infla o lag."""
        dna_logger.dna_log_feature(1, "f", {"raw": 1, "bucket": "x"})  # id 1 — terminal
        dna_logger.dna_log_feature(2, "f", {"raw": 2, "bucket": "y"})  # id 2
        dna_logger.dna_update_realized(2, hit=True, wheel_dist=3)       # id 2 realiza
        s = dna_logger.dna_realize_stats()
        # a feature 1 ficou ATRÁS da última realizada (id 2) → órfã terminal → excluída
        self.assertEqual(s["unrealized"], 0)
        self.assertEqual(s["lag_seconds"], 0)

    def test_pending_ahead_counts(self):
        """Feature pendente NA FRENTE da última realizada conta (aguarda legítima)."""
        dna_logger.dna_log_feature(1, "f", {"raw": 1, "bucket": "x"})  # id 1
        dna_logger.dna_update_realized(1, hit=True, wheel_dist=3)       # id 1 realiza
        dna_logger.dna_log_feature(2, "f", {"raw": 2, "bucket": "y"})  # id 2 — aguardando
        s = dna_logger.dna_realize_stats()
        self.assertEqual(s["unrealized"], 1)


if __name__ == "__main__":
    unittest.main()

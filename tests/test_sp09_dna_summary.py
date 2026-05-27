"""SP-09 DNA-04: /api/dna_summary endpoint."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import dna_logger


class TestDnaSummary(unittest.TestCase):
    def setUp(self):
        dna_logger.reset_for_tests()
        self.db = tempfile.mktemp(suffix=".db")
        dna_logger.configure(self.db)

    def tearDown(self):
        dna_logger.reset_for_tests()

    def test_empty(self):
        self.assertEqual(dna_logger.dna_summary(), [])

    def test_aggregation(self):
        for i in range(5):
            dna_logger.dna_log_feature(i, "f", {"raw": 1, "bucket": "x"})
            dna_logger.dna_update_realized(i, hit=(i % 2 == 0), wheel_dist=2)
        out = dna_logger.dna_summary()
        self.assertEqual(len(out), 1)
        r = out[0]
        self.assertEqual(r["feature_name"], "f")
        self.assertEqual(r["bucket"], "x")
        self.assertEqual(r["n"], 5)
        self.assertAlmostEqual(r["hit_rate"], 3 / 5)


if __name__ == "__main__":
    unittest.main()

"""SP-06 / DNA-01: testes para dna_logger + tabela decision_dna."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import dna_logger  # noqa: E402


class TestDnaLogger(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        dna_logger.configure(self.db, enabled=True)

    def tearDown(self):
        dna_logger.reset_for_tests()

    def test_table_created(self):
        conn = sqlite3.connect(self.db)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='decision_dna'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_log_feature_basic(self):
        ok = dna_logger.dna_log_feature(
            decision_id=1,
            feature_name="sda_score",
            feature_value={"raw": 4, "bucket": "sweet_spot"},
            spin_number=33,
            direction="cw",
            estimated_lift_pp=2.1,
            confidence_n=2300,
        )
        self.assertTrue(ok)
        conn = sqlite3.connect(self.db)
        rows = conn.execute("SELECT feature_name, feature_value, estimated_lift_pp FROM decision_dna").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "sda_score")
        self.assertEqual(json.loads(rows[0][1])["bucket"], "sweet_spot")
        self.assertAlmostEqual(rows[0][2], 2.1, places=5)

    def test_log_multiple_features_per_decision(self):
        for fname in ("sda_score", "calibration_offset", "kill_v4", "region_C1"):
            dna_logger.dna_log_feature(
                decision_id=42, feature_name=fname,
                feature_value={"bucket": "test"},
            )
        conn = sqlite3.connect(self.db)
        n = conn.execute("SELECT COUNT(*) FROM decision_dna WHERE decision_id=42").fetchone()[0]
        self.assertEqual(n, 4)

    def test_update_realized_fills_post_result(self):
        dna_logger.dna_log_feature(
            decision_id=99, feature_name="sda_score",
            feature_value={"bucket": "high"},
        )
        dna_logger.dna_log_feature(
            decision_id=99, feature_name="kill_v4",
            feature_value={"bucket": "off"},
        )
        n_updated = dna_logger.dna_update_realized(99, realized_lift_pp=1.4, hit=True, wheel_dist=2)
        self.assertEqual(n_updated, 2)
        conn = sqlite3.connect(self.db)
        rows = conn.execute(
            "SELECT realized_lift_pp, hit, wheel_dist FROM decision_dna WHERE decision_id=99"
        ).fetchall()
        for r in rows:
            self.assertAlmostEqual(r[0], 1.4, places=5)
            self.assertEqual(r[1], 1)
            self.assertEqual(r[2], 2)

    def test_disabled_no_writes(self):
        dna_logger.configure(self.db, enabled=False)
        ok = dna_logger.dna_log_feature(
            decision_id=1, feature_name="x", feature_value={},
        )
        self.assertFalse(ok)

    def test_migration_file_exists_and_loads(self):
        path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0008_decision_dna.py"
        self.assertTrue(path.exists())
        src = path.read_text(encoding="utf-8")
        self.assertIn("shared.decision_dna", src)
        self.assertIn("dna_summary", src)
        self.assertIn('down_revision = "0007_deal_dealer_table"', src)


if __name__ == "__main__":
    unittest.main()

"""SP-16 / REGION-01: persistencia sda_regions JSON."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.models import Decision
from database.sqlite_repo import SQLiteDecisionRepository


class FakeResult:
    def __init__(self, center, centers, off_c2, off_c3, score, offset_type="sigmoid"):
        self.center = center
        self.score = score
        self.numbers = [center]
        self.details = {
            "centers": centers,
            "offset": off_c2,
            "offset_c3": off_c3,
            "offset_type": offset_type,
        }


class TestSDA17RegionsBuilder(unittest.TestCase):
    def test_builder_packs_three_regions(self):
        from server.message_handler import _build_sda_regions
        r = FakeResult(center=30, centers=[30, 14, 4], off_c2=-3, off_c3=5, score=4)
        regions = _build_sda_regions(r)
        self.assertEqual(len(regions), 3)
        self.assertEqual(regions[0]["slot"], "C1")
        self.assertEqual(regions[0]["c"], 30)
        self.assertEqual(regions[0]["offset"], 0)
        self.assertEqual(regions[1]["slot"], "C2")
        self.assertEqual(regions[1]["offset"], -3)
        self.assertEqual(regions[2]["offset"], 5)
        for r_ in regions:
            self.assertEqual(r_["score"], 4)
            self.assertEqual(r_["offset_type"], "sigmoid")

    def test_builder_handles_missing_details(self):
        from server.message_handler import _build_sda_regions
        class Empty:
            details = {}
            score = 0
        self.assertEqual(_build_sda_regions(Empty()), [])

    def test_builder_resilient_to_exception(self):
        from server.message_handler import _build_sda_regions
        class Bad:
            details = None
            score = 0
        # nao deve levantar
        self.assertEqual(_build_sda_regions(Bad()), [])


class TestSDARegionsPersistence(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        self.repo = SQLiteDecisionRepository(db_path=self.db)
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO sessions (id, start_time) VALUES (?, ?)",
            ("sess1", datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )
        conn.commit()
        conn.close()

    def test_column_exists(self):
        conn = sqlite3.connect(self.db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(decisions)").fetchall()]
        self.assertIn("sda_regions", cols)

    def test_roundtrip(self):
        d = Decision(
            session_id="sess1", spin_number=10, spin_direction="cw",
            sda_center=30, sda_centers=[30, 14, 4],
            sda_regions=[
                {"slot": "C1", "c": 30, "offset": 0, "score": 4, "offset_type": "sigmoid"},
                {"slot": "C2", "c": 14, "offset": -3, "score": 4, "offset_type": "sigmoid"},
                {"slot": "C3", "c": 4, "offset": 5, "score": 4, "offset_type": "sigmoid"},
            ],
            final_action="APOSTAR",
        )
        did = self.repo.save_decision(d)
        self.assertIsNotNone(did)
        conn = sqlite3.connect(self.db)
        row = conn.execute(
            "SELECT sda_regions FROM decisions WHERE id=?", (did,)
        ).fetchone()
        regions = json.loads(row[0])
        self.assertEqual(len(regions), 3)
        self.assertEqual(regions[1]["c"], 14)
        self.assertEqual(regions[1]["offset"], -3)

    def test_empty_regions_persists_null(self):
        d = Decision(
            session_id="sess1", spin_number=11, spin_direction="cw",
            sda_center=5, sda_centers=[5], sda_regions=[],
            final_action="PULAR",
        )
        did = self.repo.save_decision(d)
        conn = sqlite3.connect(self.db)
        row = conn.execute(
            "SELECT sda_regions FROM decisions WHERE id=?", (did,)
        ).fetchone()
        self.assertIsNone(row[0])


if __name__ == "__main__":
    unittest.main()

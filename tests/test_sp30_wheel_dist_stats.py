"""SP-30 OBS-02: wheel_dist_stats percentis."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.sqlite_repo import SQLiteDecisionRepository


def _seed(db_path, errors):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO sessions(id, start_time) VALUES ('s', datetime('now'))")
    for i, e in enumerate(errors):
        conn.execute(
            """INSERT INTO decisions(timestamp, session_id, spin_number, spin_direction,
                final_action, calibration_error, result_actual)
               VALUES (datetime('now'), 's', ?, 'cw', 'APOSTAR', ?, 5)""",
            (i, e),
        )
    conn.commit()
    conn.close()


class TestWheelDistStats(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        self.repo = SQLiteDecisionRepository(db_path=self.db)

    def test_empty(self):
        s = self.repo.wheel_dist_stats(60)
        self.assertEqual(s, {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0})

    def test_percentiles(self):
        _seed(self.db, list(range(0, 100)))  # 0..99
        s = self.repo.wheel_dist_stats(60)
        self.assertEqual(s["n"], 100)
        # nearest-rank com round: p50 idx round(0.5*99)=50, p95 idx 94, p99 idx 98
        self.assertEqual(s["p50"], 50.0)
        self.assertEqual(s["p95"], 94.0)
        self.assertEqual(s["p99"], 98.0)

    def test_ignores_null(self):
        # mistura com result NULL e errors NULL
        _seed(self.db, [1.0, 2.0, 3.0])
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO decisions(timestamp, session_id, spin_number, spin_direction, final_action, calibration_error) "
            "VALUES (datetime('now'), 's', 99, 'cw', 'APOSTAR', NULL)"
        )
        conn.commit()
        conn.close()
        s = self.repo.wheel_dist_stats(60)
        self.assertEqual(s["n"], 3)


if __name__ == "__main__":
    unittest.main()

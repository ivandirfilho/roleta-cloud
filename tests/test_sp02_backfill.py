"""SP-02 tests: backfill calibration_error."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.backfill_calibration_error import backfill  # noqa: E402


def _make_db() -> str:
    p = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(p)
    conn.executescript(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            sda_centers TEXT,
            result_actual INTEGER,
            calibration_error INTEGER
        );
        """
    )
    conn.commit()
    conn.close()
    return p


class TestBackfillCalibrationError(unittest.TestCase):
    def test_dry_run_computes_without_changing_db(self):
        p = _make_db()
        conn = sqlite3.connect(p)
        # Caso real: centro 0, result 32 (vizinho na roda) -> dist=1
        conn.execute(
            "INSERT INTO decisions (sda_centers, result_actual, calibration_error) VALUES (?,?,?)",
            (json.dumps([0]), 32, None),
        )
        conn.commit()
        conn.close()
        stats = backfill(p, apply=False)
        self.assertEqual(stats["candidates"], 1)
        self.assertEqual(stats["computed"], 1)
        self.assertEqual(stats["applied"], 0)
        # Confirma que nao alterou
        conn = sqlite3.connect(p)
        cur = conn.execute("SELECT calibration_error FROM decisions WHERE id=1")
        self.assertIsNone(cur.fetchone()[0])

    def test_apply_updates_rows(self):
        p = _make_db()
        conn = sqlite3.connect(p)
        conn.executemany(
            "INSERT INTO decisions (sda_centers, result_actual, calibration_error) VALUES (?,?,?)",
            [
                (json.dumps([0]), 0, None),     # dist=0
                (json.dumps([0]), 32, None),    # dist=1 (vizinho de 0)
                (json.dumps([5, 10, 23]), 17, None),  # multi-center
                ("[]", 7, None),                # ignorado (centers vazio)
                (json.dumps([0]), 0, 999),      # ja preenchido -> ignorado
            ],
        )
        conn.commit()
        conn.close()
        stats = backfill(p, apply=True)
        self.assertEqual(stats["candidates"], 3)  # row 4 filtrada pelo SQL ([]), row 5 ja preenchida
        self.assertEqual(stats["applied"], 3)
        conn = sqlite3.connect(p)
        rows = conn.execute(
            "SELECT id, calibration_error FROM decisions ORDER BY id"
        ).fetchall()
        # row 5 NUNCA muda
        self.assertEqual(rows[4][1], 999)
        # rows 1-3 ganham valor numerico
        for r in rows[:3]:
            self.assertIsNotNone(r[1])
            self.assertIsInstance(r[1], int)

    def test_idempotent(self):
        p = _make_db()
        conn = sqlite3.connect(p)
        conn.execute(
            "INSERT INTO decisions (sda_centers, result_actual, calibration_error) VALUES (?,?,?)",
            (json.dumps([0]), 32, None),
        )
        conn.commit()
        conn.close()
        s1 = backfill(p, apply=True)
        s2 = backfill(p, apply=True)  # nada para fazer
        self.assertGreaterEqual(s1["applied"], 1)
        self.assertEqual(s2["candidates"], 0)
        self.assertEqual(s2["applied"], 0)


if __name__ == "__main__":
    unittest.main()

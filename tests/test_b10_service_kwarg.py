"""B-10 (26/05): garante que DatabaseService.update_result propaga
calibration_error para o repository. Bug original: wrapper engolia o
kwarg → TypeError silencioso no message_handler → coluna sempre NULL
mesmo apos B-09 corrigir pending['centers']."""
from __future__ import annotations

import inspect
import os
import tempfile
import unittest

from database.models import Decision, Session
from database.service import DatabaseService
from database.sqlite_repo import SQLiteDecisionRepository


class TestServiceUpdateResultKwarg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.repo = SQLiteDecisionRepository(self.tmp.name)
        # DatabaseService.repository é property → mocka via classe stub
        class _Svc:
            def __init__(self, r):
                self._r = r
            @property
            def repository(self):
                return self._r
            update_result = DatabaseService.update_result
        self.svc = _Svc(self.repo)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _seed(self) -> int:
        self.repo.create_session(Session(id="s_b10"))
        d = Decision(session_id="s_b10", spin_number=0, spin_direction="cw",
                     spin_force=1, final_action="APOSTAR")
        return self.repo.save_decision(d)

    def test_accepts_calibration_error_kwarg(self):
        sig = inspect.signature(DatabaseService.update_result)
        self.assertIn("calibration_error", sig.parameters,
                      "service wrapper precisa expor calibration_error")

    def test_propagates_value_to_db(self):
        did = self._seed()
        self.svc.update_result(did, True, 17, calibration_error=3)
        conn = self.repo._get_connection()
        row = conn.execute(
            "SELECT calibration_error FROM decisions WHERE id=?", (did,)
        ).fetchone()
        conn.close()
        self.assertEqual(row["calibration_error"], 3)

    def test_none_preserves_column(self):
        did = self._seed()
        self.svc.update_result(did, True, 17, calibration_error=5)
        self.svc.update_result(did, False, 4)  # sem kwarg
        conn = self.repo._get_connection()
        row = conn.execute(
            "SELECT calibration_error, result_actual FROM decisions WHERE id=?",
            (did,)
        ).fetchone()
        conn.close()
        self.assertEqual(row["calibration_error"], 5)
        self.assertEqual(row["result_actual"], 4)


if __name__ == "__main__":
    unittest.main()

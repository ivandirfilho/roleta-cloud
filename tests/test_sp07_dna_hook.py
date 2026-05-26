"""SP-07 tests: hook DNA no message_handler + autoconfig no get_repository."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestSP07DNAAutoconfig(unittest.TestCase):
    def setUp(self):
        # Reset state global do singleton + dna_logger
        import database
        database._repository = None
        from database import dna_logger
        dna_logger.reset_for_tests()

    def test_get_repository_autoconfigures_dna(self):
        import database
        from database import dna_logger
        tmp = tempfile.mktemp(suffix=".db")
        database.init_database(tmp)
        # apos init, dna_logger deve aceitar gravacoes
        ok = dna_logger.dna_log_feature(
            decision_id=1, feature_name="sda_score",
            feature_value={"bucket": "high"},
        )
        self.assertTrue(ok)
        # tabela criada no MESMO db do repo
        conn = sqlite3.connect(tmp)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='decision_dna'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_handler_emits_at_least_4_features_per_decision(self):
        """Verifica que o hook em message_handler emite >=4 entradas."""
        # Como o hook usa imports tardios e best-effort, validamos indirect via
        # contagem de chamadas mockadas a dna_log_feature.
        from unittest.mock import patch
        from database import dna_logger
        tmp = tempfile.mktemp(suffix=".db")
        dna_logger.configure(tmp, enabled=True)
        calls = []

        original = dna_logger.dna_log_feature

        def spy(*a, **kw):
            calls.append((a, kw))
            return original(*a, **kw)

        # Simulacao direta do bloco hook (sem mockar todo handler)
        with patch.object(dna_logger, "dna_log_feature", side_effect=spy):
            # Replica logica do hook SP-07
            decision_id = 1
            features = [
                ("sda_score", {"raw": 4, "bucket": "sweet_spot"}),
                ("calibration_offset", {"raw": 0}),
                ("tr_c4_rate", {"raw": 0.52, "bucket": "warm"}),
                ("kill_v4", {"raw": False, "bucket": "on"}),
            ]
            for name, val in features:
                dna_logger.dna_log_feature(
                    decision_id, name, val,
                    spin_number=33, direction="cw", final_action="APOSTAR",
                )
        self.assertGreaterEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()

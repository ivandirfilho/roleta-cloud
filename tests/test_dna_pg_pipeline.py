"""P3.1 (12/06) — pipeline DNA→PG: hooks outbox + handlers CDC.

Gap confirmado na validação E2E 12/06: shared.decision_dna (PG, migração
0008) tinha 0 rows porque dna_logger só gravava SQLite. Este teste cobre:
- hooks maybe_publish_dna_feature/realized (flag off → False; payload correto);
- handlers _apply_dna_feature/_apply_dna_realized (SQL/args corretos, sem PG);
- dna_log_feature dispara o hook (espelhamento automático).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from database import outbox_integration as oi
from workers.cdc_worker import _apply_dna_feature, _apply_dna_realized, HANDLERS


class _FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, args=None):
        self.calls.append((" ".join(sql.split()), args))


class TestDnaHooks(unittest.TestCase):
    def setUp(self):
        oi.invalidate_flag_cache()

    def test_flag_off_returns_false(self):
        with patch.object(oi, "_is_flag_enabled", return_value=False):
            self.assertFalse(oi._publish_dna_feature_sync(
                {"decision_id": 1, "feature_name": "hit_region", "feature_value": {"raw": "C1"}}))
            self.assertFalse(oi._publish_dna_realized_sync({"decision_id": 1, "hit": True}))

    def test_enqueue_is_nonblocking_and_returns_true(self):
        """INCIDENT 12/06: hooks públicos só enfileiram (nunca tocam PG no caller)."""
        with patch.object(oi, "_publish_dna_feature_sync") as sync_mock:
            ok = oi.maybe_publish_dna_feature(1, "hit_region", {"raw": "C1"})
            self.assertTrue(ok)
            oi._DNA_QUEUE.join()  # worker consome
        sync_mock.assert_called_once()

    def test_feature_payload_shape(self):
        pub = MagicMock()
        with patch.object(oi, "_is_flag_enabled", return_value=True), \
             patch.object(oi, "_get_publisher", return_value=pub):
            ok = oi._publish_dna_feature_sync({
                "decision_id": 42, "feature_name": "hit_region",
                "feature_value": {"raw": "C2", "dist_c1": 3},
                "spin_number": 17, "direction": "horario",
                "final_action": "APOSTAR", "hit": True, "wheel_dist": 2,
            })
        self.assertTrue(ok)
        kw = pub.publish.call_args.kwargs
        self.assertEqual(kw["aggregate"], "dna")
        self.assertEqual(kw["aggregate_id"], "42:hit_region")
        p = kw["payload"]
        self.assertEqual(p["event_type"], "dna_feature")
        self.assertEqual(p["direction"], "cw")  # normalizado
        self.assertEqual(p["feature_value"], {"raw": "C2", "dist_c1": 3})
        self.assertTrue(p["hit"])

    def test_realized_payload_shape(self):
        pub = MagicMock()
        with patch.object(oi, "_is_flag_enabled", return_value=True), \
             patch.object(oi, "_get_publisher", return_value=pub):
            ok = oi._publish_dna_realized_sync(
                {"decision_id": 42, "hit": False, "wheel_dist": 7})
        self.assertTrue(ok)
        kw = pub.publish.call_args.kwargs
        self.assertEqual(kw["aggregate_id"], "42:realized")
        self.assertEqual(kw["payload"]["event_type"], "dna_realized")
        self.assertFalse(kw["payload"]["hit"])

    def test_hooks_never_raise(self):
        with patch.object(oi, "_is_flag_enabled", side_effect=RuntimeError("boom")):
            self.assertFalse(oi._publish_dna_feature_sync(
                {"decision_id": 1, "feature_name": "x", "feature_value": {}}))
            self.assertFalse(oi._publish_dna_realized_sync({"decision_id": 1, "hit": True}))


class TestCdcDnaHandlers(unittest.TestCase):
    def test_handlers_registered(self):
        self.assertIn("dna_feature", HANDLERS)
        self.assertIn("dna_realized", HANDLERS)

    def test_apply_dna_feature_sql(self):
        cur = _FakeCursor()
        _apply_dna_feature(cur, {
            "decision_id": 7, "feature_name": "hit_region",
            "feature_value": {"raw": "C1"}, "spin_number": 5,
            "direction": "cw", "final_action": "APOSTAR",
            "hit": True, "wheel_dist": 1,
        })
        sql, args = cur.calls[0]
        self.assertIn("INSERT INTO shared.decision_dna", sql)
        self.assertIn("WHERE NOT EXISTS", sql)  # anti-duplo
        self.assertEqual(args[0], 7)
        self.assertEqual(args[3], "hit_region")

    def test_apply_dna_feature_validates(self):
        with self.assertRaises(ValueError):
            _apply_dna_feature(_FakeCursor(), {"decision_id": "x", "feature_name": "f"})
        with self.assertRaises(ValueError):
            _apply_dna_feature(_FakeCursor(), {"decision_id": 1, "feature_name": ""})

    def test_apply_dna_realized_sql(self):
        cur = _FakeCursor()
        _apply_dna_realized(cur, {"decision_id": 9, "hit": True, "wheel_dist": 3})
        sql, args = cur.calls[0]
        self.assertIn("UPDATE shared.decision_dna SET", sql)
        self.assertIn("hit = %s", sql)
        self.assertEqual(args[-1], 9)

    def test_apply_dna_realized_noop_without_fields(self):
        cur = _FakeCursor()
        _apply_dna_realized(cur, {"decision_id": 9})
        self.assertEqual(cur.calls, [])


class TestDnaLoggerTriggersMirror(unittest.TestCase):
    def test_log_feature_calls_hook(self):
        import tempfile
        from database import dna_logger
        dna_logger.reset_for_tests()
        tmp = tempfile.mktemp(suffix=".db")
        dna_logger.configure(tmp)
        with patch("database.outbox_integration.maybe_publish_dna_feature") as mock_pub:
            ok = dna_logger.dna_log_feature(
                11, "sda_score", {"raw": 4}, direction="cw", final_action="APOSTAR",
            )
        self.assertTrue(ok)
        mock_pub.assert_called_once()
        self.assertEqual(mock_pub.call_args.args[0], 11)
        dna_logger.reset_for_tests()


if __name__ == "__main__":
    unittest.main()

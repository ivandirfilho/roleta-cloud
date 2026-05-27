"""SP-26 ML-02: calibration offset prior bayesian +3 flag."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh_sda17():
    """Import isolado para respeitar env var SDA_OFFSET_PRIOR."""
    import importlib
    from strategies import sda17 as _m
    importlib.reload(_m)
    return _m.SDA17Strategy()


class TestOffsetPriorFlag(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.pop("SDA_OFFSET_PRIOR", None)

    def tearDown(self):
        if self._orig is not None:
            os.environ["SDA_OFFSET_PRIOR"] = self._orig
        else:
            os.environ.pop("SDA_OFFSET_PRIOR", None)

    def test_default_unchanged(self):
        s = _fresh_sda17()
        self.assertEqual(s.BAYESIAN_DEFAULT, 10)
        self.assertEqual(s.PRIOR_CENTER, 10)
        self.assertEqual(s._offset_prior_mode, "")

    def test_bayesian_plus3(self):
        os.environ["SDA_OFFSET_PRIOR"] = "bayesian_plus3"
        s = _fresh_sda17()
        self.assertEqual(s.BAYESIAN_DEFAULT, 13)
        self.assertEqual(s.PRIOR_CENTER, 13)
        self.assertEqual(s._offset_prior_mode, "bayesian_plus3")

    def test_unknown_mode_ignored(self):
        os.environ["SDA_OFFSET_PRIOR"] = "bogus_value"
        s = _fresh_sda17()
        self.assertEqual(s.BAYESIAN_DEFAULT, 10)


if __name__ == "__main__":
    unittest.main()

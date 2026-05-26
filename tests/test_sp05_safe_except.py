"""SP-05 tests: safe_except helper + lint baseline + strict mode."""
from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


class TestSafeExcept(unittest.TestCase):
    def setUp(self):
        # garante modo nao-strict por default em cada teste
        os.environ.pop("STRICT_SILENT_EXCEPT", None)
        if "core.safe_except" in sys.modules:
            del sys.modules["core.safe_except"]

    def test_swallows_generic_exception(self):
        from core.safe_except import safe_except
        log = logging.getLogger("test_swallow")
        # nao deve propagar
        with safe_except("test_cat", log):
            raise RuntimeError("boom")

    def test_reraise_kwarg_propagates(self):
        from core.safe_except import safe_except
        log = logging.getLogger("test_reraise")
        with self.assertRaises(ValueError):
            with safe_except("test_cat", log, reraise=True):
                raise ValueError("must propagate")

    def test_strict_mode_reraises_typeerror(self):
        os.environ["STRICT_SILENT_EXCEPT"] = "1"
        if "core.safe_except" in sys.modules:
            del sys.modules["core.safe_except"]
        from core.safe_except import safe_except
        log = logging.getLogger("test_strict")
        with self.assertRaises(TypeError):
            with safe_except("test_cat", log):
                # B-10-like: assinatura desalinhada
                def f(a, b): return a + b
                f(1, 2, 3)  # type: ignore[call-arg]

    def test_strict_mode_does_not_reraise_runtime(self):
        os.environ["STRICT_SILENT_EXCEPT"] = "1"
        if "core.safe_except" in sys.modules:
            del sys.modules["core.safe_except"]
        from core.safe_except import safe_except
        log = logging.getLogger("test_strict2")
        # RuntimeError nao esta em _RERAISE_TYPES -> engolido mesmo strict
        with safe_except("test_cat", log):
            raise RuntimeError("ignored")

    def test_decorator(self):
        from core.safe_except import safe_except_fn

        @safe_except_fn("dec_cat")
        def f():
            raise RuntimeError("x")

        self.assertIsNone(f())


class TestLintBaseline(unittest.TestCase):
    def test_baseline_exists(self):
        bp = REPO / ".silent_except_baseline.json"
        self.assertTrue(bp.exists(), "baseline ausente — rode `python tools/lint_silent_except.py --update`")
        data = json.loads(bp.read_text())
        self.assertIsInstance(data, dict)
        self.assertGreater(len(data), 0)

    def test_lint_clean_run(self):
        # nao deve falhar contra o proprio baseline
        result = subprocess.run(
            [sys.executable, str(REPO / "tools" / "lint_silent_except.py")],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

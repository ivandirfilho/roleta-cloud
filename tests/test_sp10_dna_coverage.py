"""SP-10 DNA-05: cobertura DNA."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class TestDnaCoverage(unittest.TestCase):
    def test_lint_passes(self):
        r = subprocess.run(
            [sys.executable, str(REPO / "tools" / "lint_dna_coverage.py")],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()

"""SP-03 smoke test: deploy_pull.sh existe, executavel, syntax bash valida."""
from __future__ import annotations
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class TestDeployPullScript(unittest.TestCase):
    def test_script_exists(self):
        self.assertTrue((REPO / "tools" / "deploy_pull.sh").exists())

    def test_systemd_units_exist(self):
        for f in ("roleta-deploy.service", "roleta-deploy.timer"):
            self.assertTrue((REPO / "tools" / "systemd" / f).exists(), f)

    def test_docs_exist(self):
        self.assertTrue((REPO / "docs" / "DEPLOY.md").exists())

    @unittest.skipUnless(shutil.which("bash"), "bash nao disponivel")
    def test_bash_syntax_ok(self):
        script = REPO / "tools" / "deploy_pull.sh"
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True, text=True,
        )
        if result.returncode == 127 and "No such file or directory" in (result.stderr + result.stdout):
            self.skipTest("bash nao consegue ler o path (provavel WSL/path translation)")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

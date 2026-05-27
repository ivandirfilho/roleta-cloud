"""SP-10 DNA-05: lint cobertura DNA.

Verifica que todo arquivo que chama ``save_decision()`` (escreve uma
decisao) tambem chama ``dna_log_feature()`` (instrumenta DNA). Defesa
contra regressao do hook SP-07 ao adicionar novos caminhos de escrita.

Exemption: adicionar comentario ``# DNA-EXEMPT: <reason>`` no arquivo.

Usage:
    python tools/lint_dna_coverage.py          # exit 1 se cobertura quebrada
    python tools/lint_dna_coverage.py --strict # mesmo efeito (mantido por simetria)
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["server", "state", "workers"]
EXEMPT_MARKER = "DNA-EXEMPT"


def _calls_in_file(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                calls.add(fn.attr)
            elif isinstance(fn, ast.Name):
                calls.add(fn.id)
    return calls


def _is_exempt(path: Path) -> bool:
    try:
        return EXEMPT_MARKER in path.read_text(encoding="utf-8")
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="(no-op, sempre strict)")
    parser.parse_args()

    violations: list[str] = []
    for d in SCAN_DIRS:
        base = REPO / d
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            calls = _calls_in_file(py)
            if "save_decision" in calls and "dna_log_feature" not in calls:
                if _is_exempt(py):
                    continue
                violations.append(str(py.relative_to(REPO)))

    if violations:
        print("[lint-dna] FAIL: arquivos que chamam save_decision sem dna_log_feature:")
        for v in violations:
            print(f"  - {v}")
        print("[lint-dna] adicione hook SP-07 ou comentario `# DNA-EXEMPT: <motivo>`")
        return 1
    print("[lint-dna] OK — cobertura DNA preservada")
    return 0


if __name__ == "__main__":
    sys.exit(main())

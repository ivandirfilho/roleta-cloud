"""SP-05 lint: garante que o numero de ``except Exception`` por arquivo
no diretorio server/ nao cresca alem do baseline.

Uso:
  python tools/lint_silent_except.py                 # roda check
  python tools/lint_silent_except.py --update        # atualiza baseline
  python tools/lint_silent_except.py --strict        # falha em qualquer novo

Saida: exit code 0 = OK, 1 = baseline excedido.

Integracao: chamar em .github/workflows/ci.yml e/ou pre-commit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".silent_except_baseline.json"
TARGETS = [ROOT / "server", ROOT / "state", ROOT / "strategies"]
PATTERN = re.compile(r"^\s*except\s+Exception\b", re.MULTILINE)


def count_per_file() -> dict[str, int]:
    counts: dict[str, int] = {}
    for tgt in TARGETS:
        if not tgt.is_dir():
            continue
        for py in tgt.rglob("*.py"):
            txt = py.read_text(encoding="utf-8", errors="ignore")
            n = len(PATTERN.findall(txt))
            if n > 0:
                rel = str(py.relative_to(ROOT)).replace("\\", "/")
                counts[rel] = n
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="grava baseline atual e sai")
    ap.add_argument("--strict", action="store_true",
                    help="qualquer aumento falha (default: tolera ate baseline)")
    args = ap.parse_args()

    current = count_per_file()
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True))
        print(f"[lint] baseline atualizado: {len(current)} arquivos")
        return 0

    if not BASELINE.exists():
        print(f"[lint] baseline ausente: {BASELINE} — rode com --update primeiro")
        return 1

    baseline = json.loads(BASELINE.read_text())
    failed = False
    for path, cur_n in sorted(current.items()):
        base_n = baseline.get(path, 0)
        if cur_n > base_n:
            print(f"[lint] FAIL {path}: {cur_n} except Exception (baseline {base_n})")
            failed = True
        elif cur_n < base_n:
            print(f"[lint] info {path}: {cur_n} (baseline {base_n}) — bom, "
                  "rode --update para registrar")
    for path in baseline:
        if path not in current:
            print(f"[lint] info {path}: removido (baseline tinha {baseline[path]})")
    if failed:
        if not args.strict:
            print("[lint] use --strict no CI para bloquear")
        return 1
    total = sum(current.values())
    print(f"[lint] OK — {total} except Exception em {len(current)} arquivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())

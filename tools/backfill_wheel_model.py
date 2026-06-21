"""Vision (auditoria_pos_foto 21/06 §7.3): backfill/canonicalização de wheel_model.

Antes do fix de canonização (commit 58d5528 + _DEFAULT_MODEL_ALIASES), o OCR
gravou variantes do mesmo rótulo de mesa ('Roleta aoVivo', 'RoletaaoVivo', ...)
em decisions.wheel_model. Isso fragmenta qualquer GROUP BY por modelo. Este
script recanoniza os valores LEGADO usando exatamente a mesma função do runtime
(server.vision_ocr._norm_model), sem precisar de replay.

Targets: decisions com wheel_model != '' cujo canônico difere do valor gravado.

Modos:
    --dry-run (default): mostra estatística + sample, NÃO altera o DB.
    --apply: aplica os UPDATEs em batches.
    --db PATH: override do path do SQLite (default /app/data/decisions.db).

Idempotente: rodar de novo após --apply não encontra mais candidatos.
Prod-write: rodar com --apply em produção exige aprovação do operador.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Permite rodar tanto local (cwd=repo) quanto no container (cwd=/app)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.vision_ocr import _norm_model  # noqa: E402

DEFAULT_DB = "/app/data/decisions.db"


def backfill(db_path: str, apply: bool = False, batch_size: int = 500) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, wheel_model
            FROM decisions
            WHERE wheel_model IS NOT NULL AND wheel_model != ''
            """
        ).fetchall()
        stats = {
            "scanned": len(rows),
            "candidates": 0,
            "applied": 0,
            "by_canonical": {},
            "samples": [],
        }
        updates: list[tuple[str, int]] = []
        for r in rows:
            raw = r["wheel_model"]
            canon = _norm_model(raw)
            if canon and canon != raw:
                stats["candidates"] += 1
                key = f"{raw!r} -> {canon!r}"
                stats["by_canonical"][key] = stats["by_canonical"].get(key, 0) + 1
                updates.append((canon, int(r["id"])))
                if len(stats["samples"]) < 8:
                    stats["samples"].append({"id": r["id"], "from": raw, "to": canon})
        if apply and updates:
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                conn.executemany(
                    "UPDATE decisions SET wheel_model = ? WHERE id = ?", batch
                )
                conn.commit()
                stats["applied"] += len(batch)
        return stats
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true",
                    help="aplica os UPDATEs (sem isso, dry-run)")
    ap.add_argument("--batch", type=int, default=500)
    args = ap.parse_args(argv)
    if not Path(args.db).exists():
        print(f"[bf-wheel] DB nao encontrado: {args.db}", file=sys.stderr)
        return 2
    stats = backfill(args.db, apply=args.apply, batch_size=args.batch)
    print(f"[bf-wheel] scanned    : {stats['scanned']}")
    print(f"[bf-wheel] candidates : {stats['candidates']}")
    print(f"[bf-wheel] applied    : {stats['applied']}")
    print("[bf-wheel] by_canonical:")
    for k, v in sorted(stats["by_canonical"].items(), key=lambda kv: -kv[1]):
        print(f"  {v:<5} {k}")
    if not args.apply:
        print("[bf-wheel] dry-run (use --apply para gravar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

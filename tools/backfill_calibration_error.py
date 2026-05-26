"""SP-02: Backfill historico de calibration_error em decisions.

Antes do fix B-10 (commit cf3570d, 26/05 21:28 UTC), todas as decisoes
gravadas tinham calibration_error=NULL porque o kwarg era engolido pelo
wrapper DatabaseService.update_result. Este script recomputa o valor
usando os mesmos dados ja persistidos (sda_centers + result_actual)
sem precisar de replay.

Formula (mesma usada em server/message_handler.py L192):
    calibration_error = roulette.compute_wheel_dist_min_to_set(
        sda_centers, result_actual
    )

Targets candidatos: decisions com
    result_actual IS NOT NULL
    AND sda_centers IS NOT NULL
    AND sda_centers != '[]'
    AND calibration_error IS NULL

Modos:
    --dry-run (default): mostra estatistica + sample, nao altera DB
    --apply: aplica UPDATE em batches de 500
    --db PATH: override do path do SQLite (default /app/data/decisions.db)

Idempotente: roda multiplas vezes sem efeito alem da primeira.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Permite rodar tanto local (cwd=repo) quanto no container (cwd=/app)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import roulette  # noqa: E402


DEFAULT_DB = "/app/data/decisions.db"


def _parse_centers(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [int(x) for x in val if x is not None]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return []


def backfill(db_path: str, apply: bool = False, batch_size: int = 500) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, sda_centers, result_actual
            FROM decisions
            WHERE result_actual IS NOT NULL
              AND sda_centers IS NOT NULL
              AND sda_centers != ''
              AND sda_centers != '[]'
              AND calibration_error IS NULL
            """
        )
        rows = cur.fetchall()
        stats = {
            "candidates": len(rows),
            "computed": 0,
            "skipped_empty_centers": 0,
            "skipped_calc_failed": 0,
            "applied": 0,
            "samples": [],
        }
        updates: list[tuple[int, int]] = []
        for r in rows:
            centers = _parse_centers(r["sda_centers"])
            if not centers:
                stats["skipped_empty_centers"] += 1
                continue
            try:
                dist = roulette.compute_wheel_dist_min_to_set(centers, int(r["result_actual"]))
            except Exception:
                stats["skipped_calc_failed"] += 1
                continue
            if dist is None:
                stats["skipped_calc_failed"] += 1
                continue
            stats["computed"] += 1
            updates.append((int(dist), int(r["id"])))
            if len(stats["samples"]) < 5:
                stats["samples"].append({
                    "id": r["id"], "centers": centers,
                    "actual": r["result_actual"], "dist": int(dist),
                })
        if apply and updates:
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                conn.executemany(
                    "UPDATE decisions SET calibration_error = ? WHERE id = ?",
                    batch,
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
        print(f"[sp02] DB nao encontrado: {args.db}", file=sys.stderr)
        return 2
    stats = backfill(args.db, apply=args.apply, batch_size=args.batch)
    print(f"[sp02] candidates           : {stats['candidates']}")
    print(f"[sp02] computed             : {stats['computed']}")
    print(f"[sp02] skipped_empty_centers: {stats['skipped_empty_centers']}")
    print(f"[sp02] skipped_calc_failed  : {stats['skipped_calc_failed']}")
    print(f"[sp02] applied              : {stats['applied']}")
    print("[sp02] samples              :")
    for s in stats["samples"]:
        print(f"  id={s['id']:<6} centers={s['centers']} actual={s['actual']:<2} dist={s['dist']}")
    if not args.apply:
        print("[sp02] dry-run (use --apply para gravar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

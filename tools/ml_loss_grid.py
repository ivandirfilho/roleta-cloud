"""SP-25 ML-01: Loss function 2D (HIT + wheel_dist) — offline grid search.

Avalia historicamente qual ``sda_offset`` (delta aplicado ao C2/C3) minimiza:

    loss(offset) = (1 - hit_rate(offset)) + lambda * median(wheel_dist(offset))

Onde ``hit_rate(offset)`` simula o que aconteceria se a estrategia tivesse
escolhido ``c2_simulated = c1 + offset`` (mod 37) em vez do offset historico.

Datasource: tabela ``decisions`` no SQLite (apos backfill SP-02). Filtra
``calibration_error IS NOT NULL`` (=wheel_dist real disponivel).

Output: tabela de losses por offset + offset otimo + sugestao de flag
``SDA_OFFSET_PRIOR`` para SP-26 consumir.

Uso:
    python tools/ml_loss_grid.py --db /app/data/decisions.db \
        --lambda 0.05 --offset-min -8 --offset-max 8
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path

# Roleta European Wheel sequence (37 slots) — replica core.roulette.WHEEL_SEQUENCE
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
         10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
_POS = {n: i for i, n in enumerate(WHEEL)}


def _wheel_dist(a: int, b: int) -> int:
    """Distancia minima no wheel circular entre slots a e b."""
    if a not in _POS or b not in _POS:
        return 18
    d = abs(_POS[a] - _POS[b])
    return min(d, 37 - d)


def _slot_offset(center: int, offset: int) -> int:
    if center not in _POS:
        return center
    return WHEEL[(_POS[center] + offset) % 37]


def grid_search(db_path: str, lam: float, off_min: int, off_max: int) -> dict:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT sda_center, result_actual
        FROM decisions
        WHERE result_actual IS NOT NULL
          AND sda_center IS NOT NULL
          AND final_action = 'APOSTAR'
        """
    ).fetchall()
    conn.close()

    if not rows:
        return {"error": "no_data", "rows": 0}

    losses: list[tuple[int, float, float, float]] = []  # (offset, loss, hr, med_dist)
    for off in range(off_min, off_max + 1):
        hits = 0
        dists: list[int] = []
        for c1, actual in rows:
            c_sim = _slot_offset(c1, off)
            d = _wheel_dist(c_sim, actual)
            dists.append(d)
            # HIT = vizinhanca +- 2 slots (estrategia SDA17 cobre c +/- 2 = 5 numeros)
            if d <= 2:
                hits += 1
        hr = hits / len(rows)
        med = statistics.median(dists) if dists else 0.0
        loss = (1.0 - hr) + lam * med
        losses.append((off, loss, hr, med))

    best = min(losses, key=lambda x: x[1])
    return {
        "n_rows": len(rows),
        "lambda": lam,
        "best_offset": best[0],
        "best_loss": best[1],
        "best_hit_rate": best[2],
        "best_median_dist": best[3],
        "table": [
            {"offset": o, "loss": round(l, 4), "hit_rate": round(h, 4), "median_dist": m}
            for o, l, h, m in losses
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--lambda", dest="lam", type=float, default=0.05)
    p.add_argument("--offset-min", type=int, default=-8)
    p.add_argument("--offset-max", type=int, default=8)
    p.add_argument("--json", action="store_true", help="output puro JSON")
    args = p.parse_args()

    if not Path(args.db).exists():
        print(f"[ml-loss] db nao existe: {args.db}", file=sys.stderr)
        return 2

    result = grid_search(args.db, args.lam, args.offset_min, args.offset_max)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if "error" in result:
        print(f"[ml-loss] {result['error']}")
        return 1

    print(f"[ml-loss] n={result['n_rows']} lambda={result['lambda']}")
    print(f"[ml-loss] best_offset={result['best_offset']} loss={result['best_loss']:.4f} "
          f"hr={result['best_hit_rate']:.4f} med_dist={result['best_median_dist']}")
    print("\n offset | loss   | hr    | med_dist")
    print(" -------|--------|-------|---------")
    for r in result["table"]:
        print(f"  {r['offset']:+3d}   | {r['loss']:.4f} | {r['hit_rate']:.3f} | {r['median_dist']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Read-only empirical gate for the V5 17/21 coverage escalation."""
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

try:
    from tools.backtest_staking_tiers import BetRow, load_db
except ModuleNotFoundError:
    from backtest_staking_tiers import BetRow, load_db


def gate_rows(rows: Iterable[BetRow], window: int = 0) -> list[dict[str, Any]]:
    """Aggregate eligible rows by window, direction, and dealer."""
    groups: dict[tuple[int, str, str], list[BetRow]] = defaultdict(list)
    for index, row in enumerate(rows):
        if row.would_hit_17 is None or row.would_hit_21 is None:
            continue
        key = (index // window if window > 0 else 0, row.direction or "unknown",
               row.dealer or "unknown")
        groups[key].append(row)
    report: list[dict[str, Any]] = []
    for (window_id, direction, dealer), members in sorted(groups.items()):
        extras = sum(bool(row.would_hit_21 and not row.would_hit_17) for row in members)
        r = extras / len(members)
        pnl_17 = sum(row.stake * (19.0 if row.would_hit_17 else -17.0)
                     for row in members)
        pnl_current = sum(row.pnl for row in members)
        report.append({
            "window": window_id,
            "direction": direction,
            "dealer": dealer,
            "n": len(members),
            "extras": extras,
            "r": r,
            "expected_delta": 36.0 * r - 4.0,
            "pnl_17": pnl_17,
            "pnl_current": pnl_current,
            "verdict": "ESCALADA_PAGA" if r > 0.111 else "NAO_PAGA",
        })
    return report


def _total_decisions(path: str) -> int:
    uri = f"file:{Path(path).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite decisions database (read-only)")
    parser.add_argument("--window", type=int, default=0,
                        help="rows per window; 0 aggregates the full input")
    args = parser.parse_args(argv)
    if args.window < 0:
        parser.error("--window must be >= 0")
    total = _total_decisions(args.db)
    rows = load_db(args.db)
    reports = gate_rows(rows, args.window)
    eligible = sum(item["n"] for item in reports)
    print(f"TOTAL {total}")
    print(f"PROCESSED {len(rows)}")
    print(f"ELIGIBLE {eligible}")
    for item in reports:
        print(
            "WINDOW={window} SENTIDO={direction} DEALER={dealer} N={n} "
            "EXTRAS={extras} R={r:.4f} E_DELTA={expected_delta:.4f} "
            "PNL_17={pnl_17:.4f} PNL_ATUAL={pnl_current:.4f} VEREDITO={verdict}"
            .format(**item)
        )
    if not reports:
        print("SETUP-FAIL no eligible counterfactual rows")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

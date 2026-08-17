"""Read-only backtest for staking tiers and the 17/21 counterfactuals.

The input ledger contains both per-unit and total ``pnl_units`` values.  This
module normalizes that E7 ambiguity before applying a hypothetical stake
multiplier; it never opens a writable database connection.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


@dataclass
class BetRow:
    row_id: str
    hit: bool
    pnl: float
    stake: float
    coverage: int
    dealer: str = ""
    direction: str = ""
    action: str = "APOSTAR"
    would_hit_17: Optional[bool] = None
    would_hit_21: Optional[bool] = None


def _value(row: Mapping[str, Any], name: str, default: Any = None) -> Any:
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        return default


def _numbers_count(value: Any) -> int:
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return 0
        return len(parsed) if isinstance(parsed, list) else 0
    return 0


def pnl_total(row: Mapping[str, Any]) -> float:
    """Return P&L in total units, correcting E7 per-unit ledger rows.

    A hit for N covered numbers has a per-unit result ``36/N - 1`` and a total
    result ``stake * (36/N - 1)``.  A miss is ``-1`` per unit or ``-stake`` in
    total scale.  Values already in total scale are preserved.
    """
    raw = float(_value(row, "pnl_units", _value(row, "pnl", 0.0)) or 0.0)
    stake = float(_value(row, "gale_bet_value", _value(row, "stake", 1.0)) or 1.0)
    n = _numbers_count(_value(row, "sda_numbers", None))
    if not n:
        n = int(_value(row, "coverage", 0) or 0)
    if stake == 0 or n <= 0:
        return raw
    hit = _value(row, "result_hit", _value(row, "hit", None))
    hit = bool(int(hit)) if isinstance(hit, str) and hit in ("0", "1") else hit
    per_unit = (36.0 / n - 1.0) if hit else -1.0
    total = stake * per_unit
    if abs(raw - per_unit) <= 0.02 and abs(raw - total) > 0.02:
        return round(total, 4)
    return raw


def parse_tiers(spec: str) -> list[float]:
    """Parse comma tiers, block notation, and the named minimum schemes."""
    aliases = {
        "flat": [1.0],
        "x2-pós-2-misses": [1.0, 1.0, 2.0],
        "x2-pos-2-misses": [1.0, 1.0, 2.0],
        "1,2,4 cap2": [1.0, 2.0, 2.0],
        "1,2,4": [1.0, 2.0, 4.0],
    }
    key = spec.strip().lower()
    if key in aliases:
        return aliases[key]
    if "->" in key:
        tiers: list[float] = []
        for block in key.split("->"):
            count, multiplier = block.split("x", 1)
            tiers.extend([float(multiplier)] * int(count))
        return tiers or [1.0]
    try:
        tiers = [float(part.strip()) for part in key.split(",") if part.strip()]
    except ValueError as exc:
        raise ValueError(f"invalid tiers: {spec}") from exc
    if not tiers or any(value <= 0 for value in tiers):
        raise ValueError(f"invalid tiers: {spec}")
    return tiers


def _flag(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")


def load_csv(path: str) -> list[BetRow]:
    rows: list[BetRow] = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(handle, 1):
            fields = line.rstrip("\r\n").split("|")
            if len(fields) != 8:
                print(f"SKIP line={line_number} reason=expected_8_pipe_fields", file=sys.stderr)
                continue
            row_id, _ts, hit, pnl, coverage, stake, dealer, direction = fields
            try:
                rows.append(BetRow(
                    row_id=row_id,
                    hit=bool(int(hit)),
                    pnl=float(pnl),
                    stake=float(stake),
                    coverage=int(coverage),
                    dealer=dealer,
                    direction=direction,
                ))
            except ValueError:
                print(f"SKIP line={line_number} reason=invalid_numeric_field", file=sys.stderr)
    return rows


def load_db(path: str) -> list[BetRow]:
    uri = f"file:{Path(path).resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        dna: dict[tuple[int, str], bool] = {}
        try:
            for row in connection.execute(
                "SELECT decision_id, feature_name, hit FROM decision_dna "
                "WHERE feature_name IN ('v5_would_hit_17', 'v5_would_hit_21')"
            ):
                dna[(int(row["decision_id"]), row["feature_name"])] = bool(row["hit"])
        except sqlite3.OperationalError:
            pass
        rows: list[BetRow] = []
        for row in connection.execute(
            "SELECT id, final_action, result_hit, pnl_units, gale_bet_value, "
            "sda_numbers, dealer, spin_direction FROM decisions ORDER BY id"
        ):
            if row["result_hit"] is None:
                print(f"SKIP id={row['id']} reason=pending_result", file=sys.stderr)
                continue
            numbers = _numbers_count(row["sda_numbers"])
            rows.append(BetRow(
                row_id=str(row["id"]),
                hit=bool(row["result_hit"]),
                pnl=pnl_total(row),
                stake=float(row["gale_bet_value"] or 1),
                coverage=numbers,
                dealer=row["dealer"] or "",
                direction=row["spin_direction"] or "",
                action=row["final_action"] or "",
                would_hit_17=dna.get((int(row["id"]), "v5_would_hit_17")),
                would_hit_21=dna.get((int(row["id"]), "v5_would_hit_21")),
            ))
        return rows
    finally:
        connection.close()


def _filter_rows(rows: Sequence[BetRow], recut: Optional[str]) -> list[BetRow]:
    if not recut:
        return list(rows)
    if recut == "cobertura":
        return [row for row in rows if row.coverage == 17]
    if recut == "dealer":
        seen: dict[str, list[bool]] = {}
        selected: list[BetRow] = []
        for row in rows:
            prior = seen.setdefault(row.dealer, [])
            if len(prior) >= 10 and sum(prior) / len(prior) > 0.55:
                selected.append(row)
            prior.append(row.hit)
        return selected
    if recut == "sentido":
        return [row for row in rows if row.direction]
    raise ValueError(f"unknown recut: {recut}")


def simulate(rows: Sequence[BetRow], tiers: Sequence[float], bankroll: float = 1000.0) -> dict[str, Any]:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    max_stake = 0.0
    miss_run = 0
    max_miss_run = 0
    pnl_series: list[float] = []
    for row in rows:
        multiplier = float(tiers[min(miss_run, len(tiers) - 1)])
        stake = row.stake * multiplier
        unit_pnl = row.pnl / row.stake if row.stake else 0.0
        result = unit_pnl * stake
        equity += result
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        max_stake = max(max_stake, stake)
        pnl_series.append(result)
        miss_run = miss_run + 1 if not row.hit else 0
        max_miss_run = max(max_miss_run, miss_run)
    rng = random.Random(7)
    ruin = 0
    for _ in range(1000):
        sample_equity = 0.0
        sample_peak = 0.0
        sample_dd = 0.0
        for _ in rows:
            result = rng.choice(pnl_series) if pnl_series else 0.0
            sample_equity += result
            sample_peak = max(sample_peak, sample_equity)
            sample_dd = max(sample_dd, sample_peak - sample_equity)
        ruin += sample_dd >= bankroll
    return {
        "n": len(rows),
        "pnl": round(equity, 4),
        "max_stake": round(max_stake, 4),
        "max_dd": round(max_dd, 4),
        "max_miss_run": max_miss_run,
        "ruin_bootstrap": round(ruin / 1000, 4),
    }


def print_result(rows: Sequence[BetRow], tiers: Sequence[float], recut: Optional[str]) -> None:
    result = simulate(rows, tiers)
    print(
        f"SCHEME tiers={','.join(str(x).rstrip('0').rstrip('.') for x in tiers)} "
        f"RECUT={recut or 'all'} N={result['n']} PNL={result['pnl']:.4f} "
        f"MAX_STAKE={result['max_stake']:.4f} MAX_DD={result['max_dd']:.4f} "
        f"MAX_MISS_RUN={result['max_miss_run']} "
        f"RUIN_BOOTSTRAP={result['ruin_bootstrap']:.4f}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--db")
    source.add_argument("--csv")
    parser.add_argument("--tiers", default="1")
    parser.add_argument("--por", choices=("dealer", "sentido", "cobertura"))
    args = parser.parse_args(argv)
    if args.db:
        uri = f"file:{Path(args.db).resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            total_input = int(connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])
        rows = load_db(args.db)
    else:
        with open(args.csv, "r", encoding="utf-8") as handle:
            total_input = sum(1 for _ in handle)
        rows = load_csv(args.csv)
    print(f"TOTAL {total_input}")
    print(f"PROCESSED {len(rows)}")
    try:
        tiers = parse_tiers(args.tiers)
        selected = _filter_rows(rows, args.por)
        if args.db:
            selected = [row for row in selected if row.action == "APOSTAR"]
        print_result(selected, tiers, args.por)
    except ValueError as exc:
        print(f"SETUP-FAIL {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

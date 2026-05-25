"""S-STRAT-9: backtest harness offline.

Replaya estratégias plugáveis contra o histórico em `cw|ccw.spin_features`
do PG (populado por S-STRAT-8). Permite testar mudanças SEM arriscar
produção.

Uso:
    python -m tools.backtest_harness --direction cw --limit 1000
    python -m tools.backtest_harness --direction ccw --strategy skip_low_acc
    python -m tools.backtest_harness --direction cw --strategy always_bet --json

Decoupling: o resultado real (hit/miss) já está persistido em spin_features.
A estratégia decide apenas BET/SKIP a partir das lag features disponíveis
no momento do spin (recent_acc_10/50, streak_miss, streak_hit) — sem
lookahead. Se BET e hit=True → win. Se BET e hit=False → loss.

Para profit_estimado usamos martingale simples 4-level (1, 2, 4, 8 unidades)
com reset em hit ou em level>4.

Estratégias suportadas (--strategy):
- always_bet (baseline)
- skip_low_acc (skip se recent_acc_10 < 0.20)
- skip_long_miss (skip se streak_miss >= 3)
- skip_combo (skip se recent_acc_10 < 0.25 OR streak_miss >= 4)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Any, Callable

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None
    RealDictCursor = None


# ---------- Strategy registry ----------

Strategy = Callable[[dict[str, Any]], bool]
"""Strategy: recebe row do spin_features e retorna True se BET, False se SKIP."""


def strategy_always_bet(row: dict[str, Any]) -> bool:  # noqa: ARG001
    return True


def strategy_skip_low_acc(row: dict[str, Any]) -> bool:
    acc10 = row.get("recent_acc_10")
    if acc10 is None:
        return True  # cold start: bet
    return float(acc10) >= 0.20


def strategy_skip_long_miss(row: dict[str, Any]) -> bool:
    sm = row.get("streak_miss") or 0
    return int(sm) < 3


def strategy_skip_combo(row: dict[str, Any]) -> bool:
    acc10 = row.get("recent_acc_10")
    sm = int(row.get("streak_miss") or 0)
    if acc10 is None:
        return True
    return float(acc10) >= 0.25 and sm < 4


STRATEGIES: dict[str, Strategy] = {
    "always_bet": strategy_always_bet,
    "skip_low_acc": strategy_skip_low_acc,
    "skip_long_miss": strategy_skip_long_miss,
    "skip_combo": strategy_skip_combo,
}


# ---------- Backtest engine ----------

GALE_UNITS = (1, 2, 4, 8)  # 4-level martingale (matches existing config)


@dataclass
class BacktestResult:
    direction: str
    strategy: str
    rows_evaluated: int
    total_bets: int
    total_skips: int
    hits: int
    misses: int
    accuracy: float | None
    profit_units: int
    max_drawdown_units: int
    max_streak_loss: int
    max_streak_win: int
    gale_level_dist: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_backtest(rows: list[dict[str, Any]], strategy: Strategy, strategy_name: str, direction: str) -> BacktestResult:
    """rows são ordenadas cronologicamente (mais antigo primeiro)."""
    bets = skips = hits = misses = 0
    gale_dist = {str(i + 1): 0 for i in range(len(GALE_UNITS))}
    gale_dist["lost"] = 0

    profit = 0
    peak = 0
    max_dd = 0
    cur_loss_streak = max_loss_streak = 0
    cur_win_streak = max_win_streak = 0

    gale_level = 0  # 0..3 = level 1..4

    for row in rows:
        decision = strategy(row)
        if not decision:
            skips += 1
            # Skip não afeta gale (continua no mesmo nível).
            continue
        bets += 1
        hit = row.get("hit")
        stake = GALE_UNITS[gale_level]
        if hit is True:
            hits += 1
            profit += stake  # win paga 1:1 sobre stake
            gale_dist[str(gale_level + 1)] += 1
            gale_level = 0
            cur_win_streak += 1
            cur_loss_streak = 0
            max_win_streak = max(max_win_streak, cur_win_streak)
        else:
            misses += 1
            profit -= stake
            cur_loss_streak += 1
            cur_win_streak = 0
            max_loss_streak = max(max_loss_streak, cur_loss_streak)
            if gale_level < len(GALE_UNITS) - 1:
                gale_level += 1
            else:
                gale_dist["lost"] += 1
                gale_level = 0  # reset após esgotar gale

        peak = max(peak, profit)
        dd = peak - profit
        max_dd = max(max_dd, dd)

    accuracy = (hits / bets) if bets else None
    return BacktestResult(
        direction=direction,
        strategy=strategy_name,
        rows_evaluated=len(rows),
        total_bets=bets,
        total_skips=skips,
        hits=hits,
        misses=misses,
        accuracy=accuracy,
        profit_units=profit,
        max_drawdown_units=max_dd,
        max_streak_loss=max_loss_streak,
        max_streak_win=max_win_streak,
        gale_level_dist=gale_dist,
    )


# ---------- PG loader ----------

def load_rows_from_pg(dsn: str, direction: str, limit: int) -> list[dict[str, Any]]:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    if direction not in ("cw", "ccw"):
        raise ValueError("direction must be cw|ccw")
    schema = direction
    conn = psycopg2.connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, ts, decision_id, hit, recent_acc_10, recent_acc_50,
                       streak_miss, streak_hit, gale_level
                FROM {schema}.spin_features
                ORDER BY id DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    # Cronológico: mais antigo primeiro
    rows.reverse()
    return rows


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="backtest_harness", description="S-STRAT-9 backtest offline")
    p.add_argument("--direction", choices=["cw", "ccw"], required=True)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument(
        "--strategy",
        choices=sorted(STRATEGIES.keys()),
        default="always_bet",
    )
    p.add_argument("--dsn", default=os.environ.get("ROLETA_PG_DSN", ""))
    p.add_argument("--json", action="store_true", help="output JSON em vez de pretty")
    args = p.parse_args(argv)

    if not args.dsn:
        print("ERROR: --dsn ou ROLETA_PG_DSN obrigatório", file=sys.stderr)
        return 2

    rows = load_rows_from_pg(args.dsn, args.direction, args.limit)
    if not rows:
        print(f"no data: {args.direction}.spin_features está vazio (S-STRAT-8 ainda populando?)", file=sys.stderr)
        return 1

    result = run_backtest(rows, STRATEGIES[args.strategy], args.strategy, args.direction)

    if args.json:
        print(json.dumps(result.as_dict(), default=str))
    else:
        _print_pretty(result)
    return 0


def _print_pretty(r: BacktestResult) -> None:
    print(f"Backtest direction={r.direction} strategy={r.strategy} rows={r.rows_evaluated}")
    print("-" * 60)
    print(f"  bets={r.total_bets} skips={r.total_skips}")
    print(f"  hits={r.hits} misses={r.misses} accuracy={(r.accuracy or 0)*100:.2f}%")
    print(f"  profit_units={r.profit_units:+d}")
    print(f"  max_drawdown_units={r.max_drawdown_units}")
    print(f"  max_streak: loss={r.max_streak_loss} win={r.max_streak_win}")
    print(f"  gale_level_dist={r.gale_level_dist}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

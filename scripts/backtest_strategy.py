"""
S-STRAT-9 — Backtest Harness Offline (versão MÍNIMA).

Lê decisions.db ou Postgres e re-executa a estratégia em uma instância LIMPA
sem efeitos colaterais. Reporta acc por bucket de 100, kill rate e final state.

Uso:
    python scripts/backtest_strategy.py --db /app/data/decisions.db \
        --from "2026-05-25" --to "2026-05-26" --out report.json

Exit codes:
    0 — backtest concluído.
    1 — erro fatal (schema, conexão, etc).
    2 — sem dados na janela.
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


def _add_repo_root():
    here = Path(__file__).resolve().parent
    repo = here.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))


_add_repo_root()


def load_decisions(db_path: str, date_from: str | None, date_to: str | None) -> list[dict]:
    """Carrega decisions com result conhecido na janela informada."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    q = """
        SELECT id, timestamp, session_id, spin_number, spin_direction,
               sda_should_bet, sda_score, sda_center, sda_centers, sda_offset,
               final_action, action_reason, result_hit, result_actual
        FROM decisions
        WHERE result_actual IS NOT NULL
    """
    params = []
    if date_from:
        q += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp < ?"
        params.append(date_to)
    q += " ORDER BY id ASC"
    cur = conn.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def run_backtest(decisions: list[dict]) -> dict:
    """Replay sequencial. Não muta estado externo."""
    from strategies.sda17 import SDA17Strategy
    from state.bet_advisor import TripleRateAdvisor

    WHEEL = [
        0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
        5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
    ]

    strat = SDA17Strategy()
    strat._wheel = WHEEL
    advisor = TripleRateAdvisor()

    buckets = defaultdict(lambda: {"n": 0, "hits": 0})
    kill_pulls = 0
    pullbacks = {"cw": 0, "ccw": 0}
    tune_runs = {"cw": 0, "ccw": 0}

    perf_cw = []
    perf_ccw = []

    for idx, d in enumerate(decisions):
        direction = d["spin_direction"] or "horario"
        c1 = d["spin_number"]
        actual = d["result_actual"]
        hit = bool(d["result_hit"])
        if c1 is None or actual is None:
            continue

        # Update adaptive (S-STRAT-7 dispara aqui em batches).
        try:
            strat.update_adaptive(direction, int(c1), int(actual), WHEEL)
        except Exception as exc:
            print(f"[WARN] update_adaptive failed at id={d['id']}: {exc}", file=sys.stderr)
            continue

        # Track perf for advisor (reverse=index 0 most recent).
        if direction in ("cw", "horario"):
            perf_cw.insert(0, hit)
            perf_cw = perf_cw[:20]
            adv = advisor.analyze(perf_cw, sda_score=int(d["sda_score"] or 3),
                                  direction="ccw")  # alvo é oposto
        else:
            perf_ccw.insert(0, hit)
            perf_ccw = perf_ccw[:20]
            adv = advisor.analyze(perf_ccw, sda_score=int(d["sda_score"] or 3),
                                  direction="cw")
        if not adv.should_bet:
            kill_pulls += 1

        bucket = idx // 100
        buckets[bucket]["n"] += 1
        if hit:
            buckets[bucket]["hits"] += 1

    # Snapshot final.
    final_state = strat.get_adaptive_state()
    bt_snap = strat.get_batch_tune_snapshot() if hasattr(strat, "get_batch_tune_snapshot") else {}
    pullbacks = bt_snap.get("batch_pullback_total", pullbacks)
    tune_runs = bt_snap.get("batch_runs_total", tune_runs)

    overall_n = sum(b["n"] for b in buckets.values())
    overall_hits = sum(b["hits"] for b in buckets.values())
    return {
        "decisions_replayed": overall_n,
        "overall_acc": round(overall_hits / overall_n, 4) if overall_n else None,
        "kill_pulls": kill_pulls,
        "kill_rate": round(kill_pulls / overall_n, 4) if overall_n else None,
        "buckets": [
            {"bucket": k, "n": v["n"], "hits": v["hits"],
             "acc": round(v["hits"] / v["n"], 4) if v["n"] else None}
            for k, v in sorted(buckets.items())
        ],
        "final_sigmoid_off": final_state.get("sigmoid_off", {}),
        "batch_tune": {
            "runs_total": dict(tune_runs),
            "pullback_total": dict(pullbacks),
            "last_action": bt_snap.get("batch_last_action", {}),
            "last_delta": bt_snap.get("batch_last_delta", {}),
        },
        "kill_v4_thresholds": advisor.get_kill_stats().get("kill_v4", {}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="path para decisions.db")
    parser.add_argument("--from", dest="date_from", default=None)
    parser.add_argument("--to", dest="date_to", default=None)
    parser.add_argument("--out", default=None, help="salva report JSON")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"[ERR] db não encontrado: {args.db}", file=sys.stderr)
        return 1

    print(f"[INFO] carregando decisions de {args.db}...")
    decisions = load_decisions(args.db, args.date_from, args.date_to)
    print(f"[INFO] {len(decisions)} decisions com result_actual conhecido")
    if not decisions:
        return 2

    print("[INFO] rodando backtest...")
    report = run_backtest(decisions)
    out_text = json.dumps(report, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(out_text)
        print(f"[OK] report salvo em {args.out}")
    else:
        print(out_text)
    print(f"[SUMMARY] decisions={report['decisions_replayed']} "
          f"acc={report['overall_acc']} kill_rate={report['kill_rate']} "
          f"pullbacks={report['batch_tune']['pullback_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

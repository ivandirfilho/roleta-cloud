"""P1.1 (12/06) — SP-01/NEW-09 bisect re-baseado em EV.

Pergunta original (blueprint 26/05): hit rate caiu 47.69→43.95 após
FeatureStore/Regime opt-in — é regressão? Re-análise com a métrica CERTA
(EV/aposta via PROFIT-LEDGER), porque março já provou que hit e dinheiro
divergem (melhor hit do ano = pior P&L).

Cortes:
  A) série mensal: hit, EV/aposta, %stake — POR SENTIDO e agregado;
  B) pré/pós 24/05 (deploy PG stack + ciclo de mudanças que motivou o bisect);
  C) por sda_offset_type dentro de cada período (confounding check).

Uso: python scripts/bisect_ev_sp01.py [db]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "decisions_prod_1206.db"
CUTOFF = "2026-05-24"


def load(db: Path):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = []
    for r in conn.execute("""
        SELECT timestamp, spin_direction, final_action, sda_numbers,
               sda_offset_type, gale_bet_value, result_hit
        FROM decisions
        WHERE result_actual IS NOT NULL AND final_action='APOSTAR'
          AND gale_bet_value > 0 AND sda_numbers IS NOT NULL
        ORDER BY id
    """):
        try:
            n = len(json.loads(r["sda_numbers"] or "[]"))
        except (ValueError, TypeError):
            continue
        if n == 0:
            continue
        rows.append({
            "month": r["timestamp"][:7],
            "period": "pre" if r["timestamp"][:10] < CUTOFF else "pos",
            "dir": "cw" if (r["spin_direction"] or "") in ("horario", "cw") else "ccw",
            "off": (r["sda_offset_type"] or "none") or "none",
            "n": n,
            "bet": float(r["gale_bet_value"]),
            "hit": bool(r["result_hit"]),
        })
    conn.close()
    return rows


def agg(rows):
    a = {"n": 0, "hits": 0, "stake": 0.0, "pnl": 0.0}
    for r in rows:
        a["n"] += 1
        a["hits"] += 1 if r["hit"] else 0
        a["stake"] += r["bet"]
        a["pnl"] += r["bet"] * (36.0 / r["n"] - 1.0) if r["hit"] else -r["bet"]
    return a


def line(label, a):
    if not a["n"]:
        return f"{label:24} —"
    return (f"{label:24} n={a['n']:5d}  hit={100*a['hits']/a['n']:5.1f}%  "
            f"EV/aposta={a['pnl']/a['n']:+7.3f}  %stake={100*a['pnl']/a['stake']:+6.1f}%")


def main():
    rows = load(DB)
    print(f"dataset: {len(rows)} apostas com resultado\n")

    print("A) SÉRIE MENSAL (hit × EV — a 'regressão' é em dinheiro?)")
    months = sorted({r["month"] for r in rows})
    for m in months:
        sub = [r for r in rows if r["month"] == m]
        print(line(m, agg(sub)))
        for d in ("cw", "ccw"):
            print(line(f"   {d}", agg([r for r in sub if r["dir"] == d])))
    print()

    print(f"B) PRÉ vs PÓS {CUTOFF} (janela do bisect original)")
    for per in ("pre", "pos"):
        sub = [r for r in rows if r["period"] == per]
        print(line(per.upper(), agg(sub)))
        for d in ("cw", "ccw"):
            print(line(f"   {d}", agg([r for r in sub if r["dir"] == d])))
    print()

    print("C) POR OFFSET_TYPE dentro de cada período (confounding check)")
    for per in ("pre", "pos"):
        offs = sorted({r["off"] for r in rows if r["period"] == per})
        for off in offs:
            sub = [r for r in rows if r["period"] == per and r["off"] == off]
            if len(sub) >= 30:
                print(line(f"{per}/{off}", agg(sub)))
    print()

    pre = agg([r for r in rows if r["period"] == "pre"])
    pos = agg([r for r in rows if r["period"] == "pos"])
    if pre["n"] and pos["n"]:
        d_hit = 100 * (pos["hits"]/pos["n"] - pre["hits"]/pre["n"])
        d_ev = pos["pnl"]/pos["n"] - pre["pnl"]/pre["n"]
        print("VEREDITO SP-01 (EV-based):")
        print(f"  Δhit = {d_hit:+.2f}pp | ΔEV/aposta = {d_ev:+.3f}u")
        if d_ev >= 0:
            print("  → SEM regressão em DINHEIRO: a queda de hit não custou EV "
                  "(hit é proxy ruim — breakeven depende de N/score mix).")
        else:
            print("  → Regressão em dinheiro CONFIRMADA: prosseguir bisect por "
                  "flag (FeatureStore/Regime) com este script por subperíodo.")


if __name__ == "__main__":
    main()

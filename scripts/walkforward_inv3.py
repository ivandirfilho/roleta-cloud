"""P0.1 (12/06 noite) — Walk-forward da política INV-3 real vs CUT puro vs baseline.

Pergunta: o compromisso INV-3 (P11: indicação sempre; vetos viram stake reduzido)
preserva quanto da economia da política validada (CUT: não apostar score<4)?

Metodologia idêntica ao EV §8.4 / walk-forward de 10/06:
- stake da decisão = gale_bet_value gravado (apostas reais);
- pnl = stake*(36/N - 1) no hit; -stake no miss;
- treino = ts < 2026-05-01 · teste = ts >= 2026-05-01 (mai-jun);
- SEMPRE por sentido (P6) + agregado.

Políticas simuladas por decisão COM resultado:
  baseline : apostas reais como foram (APOSTAR, stake real)
  cut      : só score>=4 & N!=19; gale 3 excluído (política original)
  inv3     : TODAS as decisões com números:
             score>=4 & N!=19  -> stake real com gale cap 2 (G3->34)
             score<4 (APOSTAR ou PULAR c/ números) -> stake = round(0.10*17)=2
             N==19 -> stake 2 (na prática extinto: fallback virou N=21)

Uso: python scripts/walkforward_inv3.py [db]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "decisions_prod_1206.db"
SPLIT = "2026-05-01"
MIN_STAKE_FRAC = 0.10
BASE_BET = 17


def load(db: Path):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = []
    for r in conn.execute("""
        SELECT timestamp, spin_direction, final_action, sda_score,
               sda_numbers, gale_level, gale_bet_value, result_hit, result_actual
        FROM decisions
        WHERE result_actual IS NOT NULL AND sda_numbers IS NOT NULL
        ORDER BY id
    """):
        try:
            nums = json.loads(r["sda_numbers"] or "[]")
        except (ValueError, TypeError):
            continue
        if not nums:
            continue
        rows.append({
            "period": "train" if r["timestamp"] < SPLIT else "test",
            "dir": "cw" if (r["spin_direction"] or "") in ("horario", "cw") else "ccw",
            "action": r["final_action"] or "",
            "score": int(r["sda_score"] or 0),
            "n": len(nums),
            "gale": int(r["gale_level"] or 1),
            "bet": float(r["gale_bet_value"] or 0),
            "hit": bool(r["result_hit"]),
        })
    conn.close()
    return rows


def pnl(stake: float, n: int, hit: bool) -> float:
    return stake * (36.0 / n - 1.0) if hit else -stake


def simulate(rows):
    res = defaultdict(lambda: {"bets": 0, "stake": 0.0, "pnl": 0.0})

    def add(key, stake, n, hit):
        if stake <= 0:
            return
        b = res[key]
        b["bets"] += 1
        b["stake"] += stake
        b["pnl"] += pnl(stake, n, hit)

    for r in rows:
        per, d = r["period"], r["dir"]
        passes = r["score"] >= 4 and r["n"] != 19 and r["gale"] <= 2

        # baseline: o que realmente foi apostado
        if r["action"] == "APOSTAR" and r["bet"] > 0:
            add(("baseline", per, d), r["bet"], r["n"], r["hit"])

        # cut puro: só o filtro validado (apostas reais que passam)
        if r["action"] == "APOSTAR" and r["bet"] > 0 and passes:
            add(("cut", per, d), r["bet"], r["n"], r["hit"])

        # inv3: indicação sempre — stake modulado
        if passes and r["action"] == "APOSTAR" and r["bet"] > 0:
            stake = min(r["bet"], 34.0)  # cap G2
            add(("inv3", per, d), stake, r["n"], r["hit"])
        else:
            # score<4 / N=19 / gale3 / PULAR-com-números → stake mínimo
            stake = round(BASE_BET * MIN_STAKE_FRAC)
            add(("inv3", per, d), float(stake), r["n"], r["hit"])
    return res


def main():
    rows = load(DB)
    res = simulate(rows)
    print(f"dataset: {len(rows)} decisões com resultado "
          f"({sum(1 for r in rows if r['period']=='train')} treino / "
          f"{sum(1 for r in rows if r['period']=='test')} teste)\n")
    print(f"{'política':9} {'per':5} {'dir':3} {'apostas':>7} {'stake':>9} "
          f"{'P&L':>9} {'EV/aposta':>9} {'%stake':>7}")
    print("-" * 66)
    for pol in ("baseline", "cut", "inv3"):
        for per in ("train", "test"):
            tot = {"bets": 0, "stake": 0.0, "pnl": 0.0}
            for d in ("cw", "ccw"):
                b = res.get((pol, per, d), {"bets": 0, "stake": 0.0, "pnl": 0.0})
                for k in tot:
                    tot[k] += b[k]
                if b["bets"]:
                    print(f"{pol:9} {per:5} {d:3} {b['bets']:7d} {b['stake']:9.0f} "
                          f"{b['pnl']:+9.1f} {b['pnl']/b['bets']:+9.3f} "
                          f"{100*b['pnl']/b['stake']:+6.1f}%")
            if tot["bets"]:
                print(f"{pol:9} {per:5} ALL {tot['bets']:7d} {tot['stake']:9.0f} "
                      f"{tot['pnl']:+9.1f} {tot['pnl']/tot['bets']:+9.3f} "
                      f"{100*tot['pnl']/tot['stake']:+6.1f}%")
        print()

    # Veredito do gate P0.1
    print("=" * 66)
    for per in ("train", "test"):
        base = sum(res[("baseline", per, d)]["pnl"] for d in ("cw", "ccw"))
        cut = sum(res[("cut", per, d)]["pnl"] for d in ("cw", "ccw"))
        inv = sum(res[("inv3", per, d)]["pnl"] for d in ("cw", "ccw"))
        save_cut = base - cut          # perda evitada pelo CUT
        save_inv = base - inv          # perda evitada pelo INV-3
        ratio = save_inv / save_cut if save_cut else float("nan")
        print(f"{per}: baseline {base:+.1f} | cut {cut:+.1f} (economia {save_cut:+.1f}) "
              f"| inv3 {inv:+.1f} (economia {save_inv:+.1f}) → "
              f"INV-3 preserva {100*ratio:.1f}% da economia do CUT")
    print("GATE P0.1: aprovado se >= 90% nos DOIS períodos.")


if __name__ == "__main__":
    main()

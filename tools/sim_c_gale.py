#!/usr/bin/env python3
"""Harness de teste dos motores C1/C2 variável + Block-Gale (16/06).

Roda `CSelectionEngine` + `BlockGaleEngine` de ponta a ponta, **isolado do
servidor** (não toca o caminho de produção), para validar a lógica ao vivo:
seleção C1/C2 por sentido, cobertura de 14 números, gale por bloco e evolução da
banca. Funciona com um banco `decisions*.db` real OU com spins sintéticos.

Uso:
    python tools/sim_c_gale.py                      # sintético, 100 spins/sentido
    python tools/sim_c_gale.py --db data/decisions_prod_1206b.db --n 100
    python tools/sim_c_gale.py --cap 4 --only-after-green --banca 1000

Tudo é READ-ONLY (não escreve no DB). Seguro para rodar no Debian.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys

# Permite rodar a partir da raiz do repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.roulette import roulette  # noqa: E402
from strategies.c_selection import CSelectionEngine, coverage_numbers  # noqa: E402
from state.block_gale import BlockGaleEngine  # noqa: E402

WHEEL = list(roulette.WHEEL_SEQUENCE)
POS = {n: i for i, n in enumerate(WHEEL)}
N = len(WHEEL)


def signed(frm: int, to: int) -> int:
    d = (POS[to] - POS[frm]) % N
    return d - N if d > N // 2 else d


def hit_attr(centers, actual):
    """Reproduz dist_c1/c2/c3 (como `_attribute_hit_region`)."""
    return {
        "dist_c1": signed(centers[0], actual),
        "dist_c2": signed(centers[1], actual) if len(centers) > 1 else None,
        "dist_c3": signed(centers[2], actual) if len(centers) > 2 else None,
    }


def load_spins_db(path, direction, limit):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT sda_centers, result_actual FROM decisions
           WHERE result_actual IS NOT NULL AND sda_centers NOT IN ('','[]')
             AND spin_direction=? ORDER BY id DESC LIMIT ?""",
        (direction, limit),
    ).fetchall()
    con.close()
    out = []
    for r in reversed(rows):
        cs = [int(x) for x in json.loads(r["sda_centers"]) if isinstance(x, (int, float))][:3]
        a = int(r["result_actual"])
        if len(cs) == 3 and a in POS:
            out.append((cs, a))
    return out


def gen_synthetic(rng, limit):
    out = []
    for _ in range(limit):
        c1 = rng.choice(WHEEL)
        c2 = WHEEL[(POS[c1] + rng.choice([10, 11, 12])) % N]
        c3 = WHEEL[(POS[c1] + rng.choice([-12, -11, 24])) % N]
        actual = rng.choice(WHEEL)
        out.append(([c1, c2, c3], actual))
    return out


def run_direction(direction, spins, cap, only_after_green, banca0, base_unit, verbose):
    cs_eng = CSelectionEngine(radius=3)
    bg_eng = BlockGaleEngine(base_unit=base_unit, caps={"cw": cap, "ccw": cap},
                             only_after_green=only_after_green)
    banca = banca0
    history = []           # atribuições resolvidas (para o voto)
    pending = None         # (sel, decide) da jogada anterior
    peak = trough = banca0
    nbets = wins = 0
    rows = []
    for i, (centers, actual) in enumerate(spins, 1):
        # resolve a jogada anterior
        if pending is not None:
            prev_sel, prev_dec, prev_attr = pending
            d_chosen = abs(prev_attr["dist_c1"] if prev_sel.chosen == "C1" else prev_attr["dist_c2"])
            d_c3 = abs(prev_attr["dist_c3"]) if prev_attr["dist_c3"] is not None else 99
            green = min(d_chosen, d_c3) <= 3
            cs_eng.feedback(direction, prev_sel.freeze_candidates, prev_attr)
            placed = prev_dec["place"]
            if placed:
                nbets += 1
                wins += 1 if green else 0
                nN = len(prev_sel.numbers)
                pnl = base_unit * prev_dec["mult"] * ((36 - nN) if green else -nN)
                banca += pnl
                peak = max(peak, banca)
                trough = min(trough, banca)
            bg_eng.on_result(direction, green, placed)

        # decide a jogada atual
        sel = cs_eng.select(direction, centers, history, WHEEL)
        dec = bg_eng.decide(direction, bankroll=banca, n_numbers=len(sel.numbers))
        attr = hit_attr(centers, actual)
        history.append(attr)
        pending = (sel, dec, attr)
        if verbose and i <= 20:
            tag = "APOSTA" if dec["place"] else ("gate" if dec["gated"] else "insolv")
            rows.append(f"  {i:3} {sel.pair[0]}+C3 N={len(sel.numbers):2} "
                        f"G{dec['level']}(x{dec['mult']}) stake={dec['stake']:.0f} [{tag}] "
                        f"banca={banca:.0f}")
    inc = cs_eng._dirs["cw" if direction in ("cw", "horario") else "ccw"]["incumbent"]
    maxg = bg_eng.states["cw" if direction in ("cw", "horario") else "ccw"].max_level_seen
    return {
        "direction": direction, "spins": len(spins), "bets": nbets, "wins": wins,
        "hit": (wins / nbets if nbets else 0.0), "banca_final": banca,
        "peak": peak, "trough": trough, "max_gale": maxg, "incumbent": inc, "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser(description="Harness dos motores C1/C2 + Block-Gale")
    ap.add_argument("--db", default=None, help="caminho de um decisions*.db (opcional)")
    ap.add_argument("--n", type=int, default=100, help="spins por sentido")
    ap.add_argument("--cap", type=int, default=1, help="teto do gale (1=flat..4)")
    ap.add_argument("--only-after-green", action="store_true")
    ap.add_argument("--banca", type=float, default=1000.0)
    ap.add_argument("--base-unit", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", action="store_true", help="mostra as 20 primeiras jogadas")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    src = "sintético" if not args.db else args.db
    print(f"== Harness C1/C2 + Block-Gale ==  fonte={src}  cap=G{args.cap}  "
          f"only_after_green={args.only_after_green}  banca0={args.banca:.0f}  base={args.base_unit}")
    for direction in ("horario", "anti-horario"):
        if args.db:
            spins = load_spins_db(args.db, direction, args.n)
            if not spins:
                print(f"[{direction}] sem dados no DB — usando sintético")
                spins = gen_synthetic(rng, args.n)
        else:
            spins = gen_synthetic(rng, args.n)
        r = run_direction(direction, spins, args.cap, args.only_after_green,
                          args.banca, args.base_unit, args.verbose)
        print(f"\n### {direction}: spins={r['spins']} apostas={r['bets']} "
              f"hit={r['hit']*100:.1f}% banca {args.banca:.0f}->{r['banca_final']:.0f} "
              f"(pico {r['peak']:.0f} / vale {r['trough']:.0f}) maiorG=G{r['max_gale']} "
              f"incumbente={r['incumbent']}")
        for line in r["rows"]:
            print(line)
    print("\nOK — motores rodaram de ponta a ponta (isolado, sem tocar produção).")


if __name__ == "__main__":
    main()

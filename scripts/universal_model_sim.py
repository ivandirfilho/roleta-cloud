"""Modelo universal de adaptação por jogada — comparativo causal (12/06).

Replay walk-forward SEM look-ahead sobre TODAS as decisões resolvidas com 3
centros, por SENTIDO-ALVO, com estado zerado a cada sessão (premissa P10).
Cada modelo decide o shift da jogada t usando APENAS erros até t-1.

Modelos (todos genéricos e por-jogada — premissa P8):
  M0 baseline   : geometria como apostada (shift=0)
  M1 ema-shift  : shift = clamp(round(-EMA(err, a=0.2) * 0.5), ±4), n>=3
  M2 med7-shift : shift = clamp(round(-mediana(últimos 7 err)), ±5), n>=3
  M3 step-unit  : shift += sign(-err_{t-1}), clamp ±4 (gradiente unitário)
  M4 sigmoid-C1 : transplante do M02 p/ C1: miss → adj=sig(|e|)·2·sign(-e);
                  hit → tighten 8% rumo a 0; shift contínuo clamp ±4
  M5 ema-regiao : M1 no C1 + EMAs próprias p/ off2/off3 (satélites relativos)

Métrica-chave (pedido do owner): matriz de transição vs M0 —
  miss→hit (erros transformados em acertos) e hit→miss (acertos perdidos).
EV flat 17u/aposta isola o efeito GEOMETRIA (sem gale/INV-3).

Uso: python scripts/universal_model_sim.py [db]
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "decisions_prod_1206b.db"

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
         10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
POS = {n: i for i, n in enumerate(WHEEL)}


def circ(e: float) -> float:
    e = (e + 18) % 37 - 18
    return e


def signed(frm: int, to: int) -> int:
    d = (POS[to] - POS[frm]) % 37
    return d - 37 if d > 18 else d


def load():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = []
    for r in conn.execute("""
        SELECT id, timestamp, session_id, spin_direction, sda_centers, result_actual
        FROM decisions
        WHERE result_actual IS NOT NULL AND sda_centers IS NOT NULL
        ORDER BY id
    """):
        try:
            centers = [int(x) for x in json.loads(r["sda_centers"])]
        except (ValueError, TypeError):
            continue
        if len(centers) < 3:
            continue
        target = "ccw" if r["spin_direction"] == "horario" else "cw"
        c1, c2, c3 = centers[:3]
        rows.append({
            "ts": r["timestamp"],
            "period": "train" if r["timestamp"][:7] < "2026-05" else "test",
            "sess": r["session_id"],
            "t": target,
            "err": signed(c1, r["result_actual"]),       # erro da aposta real
            "off2": signed(c1, c2) % 37,                  # offsets praticados
            "off3": (-signed(c1, c3)) % 37,
        })
    conn.close()
    return rows


def hit_for(err: float, s1: float, off2: int, off3: int,
            s2: float = 0.0, s3: float = 0.0) -> bool:
    """Hit da geometria deslocada: C1 por s1; satélites por s1+s2/s1+s3."""
    e = circ(err - s1)
    if abs(e) <= 3:
        return True
    if abs(circ(e - (off2 + s2))) <= 2:
        return True
    if abs(circ(e + (off3 + s3))) <= 2:
        return True
    return False


class M0:
    def shift(self): return 0.0, 0.0, 0.0
    def update(self, err_applied): pass


class M1:
    A, K, CL, MIN_N = 0.2, 0.5, 4, 3
    def __init__(self): self.ema, self.n = None, 0
    def shift(self):
        if self.n < self.MIN_N or self.ema is None: return 0.0, 0.0, 0.0
        return max(-self.CL, min(self.CL, round(-self.ema * self.K))), 0.0, 0.0
    def update(self, e):
        self.ema = e if self.ema is None else (1-self.A)*self.ema + self.A*e
        self.n += 1


class M2:
    W, CL, MIN_N = 7, 5, 3
    def __init__(self): self.buf = []
    def shift(self):
        if len(self.buf) < self.MIN_N: return 0.0, 0.0, 0.0
        return max(-self.CL, min(self.CL, round(-median(self.buf[-self.W:])))), 0.0, 0.0
    def update(self, e): self.buf.append(e)


class M3:
    CL = 4
    def __init__(self): self.s = 0.0
    def shift(self): return self.s, 0.0, 0.0
    def update(self, e):
        if e > 1: self.s = min(self.CL, self.s + 1)
        elif e < -1: self.s = max(-self.CL, self.s - 1)


class M4:
    K, SC, TI, CL = 6, 2.0, 0.08, 4
    def __init__(self): self.s = 0.0
    def shift(self): return self.s, 0.0, 0.0
    def update(self, e):
        # e = erro da aposta APLICADA (já com shift) → hit se cobriu
        if abs(e) <= 3:
            self.s += (0 - self.s) * self.TI
        else:
            pct = min(abs(e), 18) / 18.0
            adj = (2.0 / (1.0 + math.exp(-self.K * pct)) - 1.0) * self.SC
            self.s += adj if e > 0 else -adj
        self.s = max(-self.CL, min(self.CL, self.s))


class M5:
    A, K, CL, MIN_N = 0.2, 0.5, 4, 3
    def __init__(self):
        self.e1 = self.e2 = self.e3 = None
        self.n = 0
    def shift(self):
        if self.n < self.MIN_N or self.e1 is None: return 0.0, 0.0, 0.0
        s1 = max(-self.CL, min(self.CL, round(-self.e1 * self.K)))
        s2 = max(-2, min(2, round(-(self.e2 or 0) * self.K)))
        s3 = max(-2, min(2, round((self.e3 or 0) * self.K)))
        return s1, s2, s3
    def update_full(self, e1, e2, e3):
        def ema(cur, x): return x if cur is None else (1-self.A)*cur + self.A*x
        self.e1 = ema(self.e1, e1)
        self.e2 = ema(self.e2, e2)
        self.e3 = ema(self.e3, e3)
        self.n += 1
    def update(self, e): pass  # via update_full


MODELS = {"M0": M0, "M1_ema": M1, "M2_med7": M2, "M3_step": M3,
          "M4_sigC1": M4, "M5_regiao": M5}


def run(rows):
    # estado por (modelo, sessão, sentido) — P10: zera a cada sessão
    res = {m: defaultdict(lambda: {"n": 0, "hit": 0, "m2h": 0, "h2m": 0})
           for m in MODELS}
    states = {m: {} for m in MODELS}

    for r in rows:
        key = (r["sess"], r["t"])
        base_hit = hit_for(r["err"], 0, r["off2"], r["off3"])
        for mname, mcls in MODELS.items():
            st = states[mname].get(key)
            if st is None:
                st = states[mname][key] = mcls()
            s1, s2, s3 = st.shift()
            h = hit_for(r["err"], s1, r["off2"], r["off3"], s2, s3)
            for scope in (("ALL", r["t"]), (r["period"], r["t"])):
                b = res[mname][scope]
                b["n"] += 1
                b["hit"] += 1 if h else 0
                if h and not base_hit: b["m2h"] += 1
                if base_hit and not h: b["h2m"] += 1
            # update causal com o erro da aposta APLICADA pelo modelo
            e_applied = circ(r["err"] - s1)
            if mname == "M5_regiao":
                e2 = circ(r["err"] - (s1 + (r["off2"] + s2)))
                e3 = circ(r["err"] + (r["off3"] + s3) - s1)
                st.update_full(circ(r["err"] - s1), e2, e3)
            else:
                st.update(e_applied)
    return res


def main():
    rows = load()
    print(f"dataset: {len(rows)} decisões (3 centros), "
          f"{len({r['sess'] for r in rows})} sessões, "
          f"{sum(1 for r in rows if r['period']=='train')} treino / "
          f"{sum(1 for r in rows if r['period']=='test')} teste\n")
    res = run(rows)
    PAYOUT_EV = lambda h, n: (h / n) * 19 - (1 - h / n) * 17 if n else 0  # flat 17u N=17

    for scope_label, scopes in (("GERAL", [("ALL", "cw"), ("ALL", "ccw")]),
                                ("TREINO (jan-abr)", [("train", "cw"), ("train", "ccw")]),
                                ("TESTE (mai-jun)", [("test", "cw"), ("test", "ccw")])):
        print(f"=== {scope_label} ===")
        print(f"{'modelo':10} {'dir':4} {'n':>5} {'hit%':>6} {'EVflat':>7} "
              f"{'miss→hit':>9} {'hit→miss':>9} {'saldo':>6}")
        for m in MODELS:
            for sc in scopes:
                b = res[m][sc]
                if not b["n"]: continue
                hr = b["hit"] / b["n"]
                print(f"{m:10} {sc[1]:4} {b['n']:5d} {100*hr:5.1f}% "
                      f"{PAYOUT_EV(b['hit'], b['n']):+7.2f} "
                      f"{b['m2h']:9d} {b['h2m']:9d} {b['m2h']-b['h2m']:+6d}")
        print()


if __name__ == "__main__":
    main()

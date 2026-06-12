"""Engenharia reversa — últimas 100 jogadas RESOLVIDAS por SENTIDO-ALVO.

SEMÂNTICA (verificada 34/34 no banco): decisions.spin_direction = direção do
spin que CHEGOU; a aposta/predição é para o sentido OPOSTO (target). O
resultado (result_actual) é o próximo spin desse sentido oposto.

Para cada decisão reconstrói o fluxo: last_number → força prevista → C1 →
offsets → C2/C3 → 17 números → resultado → erro de força (assinado) →
slot/distâncias → pnl. Valida a reconstrução contra o que o sistema gravou.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, pstdev

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "decisions_prod_1206b.db"
N_PER_DIR = 100

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
         10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
POS = {n: i for i, n in enumerate(WHEEL)}
RADII = (3, 2, 2)


def dir_force(frm: int, to: int, target: str) -> int:
    """Força direcional frm→to no sentido-alvo (0..36)."""
    a, b = POS[frm], POS[to]
    return (b - a) % 37 if target == "cw" else (a - b) % 37


def signed(frm: int, to: int) -> int:
    d = (POS[to] - POS[frm]) % 37
    return d - 37 if d > 18 else d


def circ_err(real: int, pred: int) -> int:
    """Erro de força normalizado para -18..18 (positivo = passou do previsto)."""
    d = (real - pred) % 37
    return d - 37 if d > 18 else d


def slot_of(centers, actual, hit):
    if not hit:
        return "miss"
    for i, c in enumerate(centers[:3]):
        sd = signed(c, actual)
        if sd is not None and abs(sd) <= RADII[i]:
            return f"C{i+1}"
    return "C1" if len(centers) == 1 else "unattributed"


def load():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = {"cw": [], "ccw": []}
    for r in conn.execute("""
        SELECT id, timestamp, session_id, spin_number, spin_direction,
               sda_predicted_force, sda_centers, sda_numbers, sda_score,
               sda_offset_type, final_action, gale_level, gale_bet_value,
               result_hit, result_actual, result_region, pnl_units,
               calibration_error, action_reason
        FROM decisions
        WHERE result_actual IS NOT NULL AND sda_centers IS NOT NULL
        ORDER BY id DESC
    """):
        target = "ccw" if (r["spin_direction"] or "") == "horario" else "cw"
        if len(out[target]) >= N_PER_DIR:
            if all(len(v) >= N_PER_DIR for v in out.values()):
                break
            continue
        try:
            centers = [int(x) for x in json.loads(r["sda_centers"] or "[]")]
            nums = json.loads(r["sda_numbers"] or "[]")
        except (ValueError, TypeError):
            continue
        if not centers or not nums:
            continue
        d = dict(r)
        d["target"] = target
        d["centers"] = centers
        d["nums"] = nums
        out[target].append(d)
    conn.close()
    for k in out:
        out[k].reverse()  # cronológico
    return out


def analyze_dir(target: str, rows: list) -> dict:
    res = {"target": target, "n": len(rows)}
    recon_force_ok = recon_c1_ok = 0
    ferr = []           # erro de força assinado (real - prevista)
    forces_real = []    # força real da bola no sentido
    forces_pred = []
    slots = Counter()
    d1s, d2s, d3s = [], [], []
    by_score = defaultdict(lambda: {"n": 0, "hit": 0, "pnl": 0.0})
    streak_err_pairs = []
    fallback_n = full_n = 0
    pnl_total = stake_total = 0.0
    hits = 0
    per_session = defaultdict(lambda: {"n": 0, "hit": 0, "pnl": 0.0})
    prev_err = None
    prev_force_real = None
    force_pairs = []

    for r in rows:
        last_n = r["spin_number"]
        actual = r["result_actual"]
        c1 = r["centers"][0]
        hit = bool(r["result_hit"])
        full = len(r["centers"]) >= 3

        # Reconstrução: força prevista a partir de C1
        fp = dir_force(last_n, c1, target)
        fr = dir_force(last_n, actual, target)
        rec_pred = r["sda_predicted_force"] or 0
        if full:  # fallback grava predicted_force=0
            if fp == rec_pred:
                recon_force_ok += 1
            # C1 recomputado por apply_force
            recon_c1_ok += 1 if fp == rec_pred else 0
            full_n += 1
        else:
            fallback_n += 1

        e = circ_err(fr, fp)
        ferr.append(e)
        forces_real.append(fr)
        forces_pred.append(fp)
        if prev_err is not None:
            streak_err_pairs.append((prev_err, e))
        prev_err = e
        if prev_force_real is not None:
            force_pairs.append((prev_force_real, fr))
        prev_force_real = fr

        slots[slot_of(r["centers"], actual, hit)] += 1
        d1s.append(signed(c1, actual))
        if full:
            d2s.append(signed(r["centers"][1], actual))
            d3s.append(signed(r["centers"][2], actual))

        sc = r["sda_score"] or 0
        by_score[sc]["n"] += 1
        by_score[sc]["hit"] += 1 if hit else 0
        if r["pnl_units"] is not None:
            by_score[sc]["pnl"] += r["pnl_units"]
            pnl_total += r["pnl_units"]
            stake_total += float(r["gale_bet_value"] or 0)
        hits += 1 if hit else 0
        s = per_session[r["session_id"]]
        s["n"] += 1
        s["hit"] += 1 if hit else 0
        s["pnl"] += r["pnl_units"] or 0.0

    def corr(pairs):
        if len(pairs) < 10:
            return None
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        mx, my = mean(xs), mean(ys)
        num = sum((x - mx) * (y - my) for x, y in pairs)
        den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
        return num / den if den else None

    # Oracle de offsets: densidade de Δ(result,C1) fora de ±3, picos + e -
    hist = Counter(d1s)
    pos_side = {k: v for k, v in hist.items() if k > 3}
    neg_side = {k: -0 + v for k, v in hist.items() if k < -3}
    best_off2 = max(pos_side, key=pos_side.get) if pos_side else None
    best_off3 = -max(neg_side, key=neg_side.get) if neg_side else None
    inside_c1 = sum(v for k, v in hist.items() if abs(k) <= 3)
    captured17 = sum(1 for r in rows if bool(r["result_hit"]))
    best17 = sum(c for _, c in hist.most_common(17))

    res.update({
        "recon_force_ok": recon_force_ok, "full_n": full_n, "fallback_n": fallback_n,
        "hit_rate": hits / len(rows),
        "pnl": pnl_total, "stake": stake_total,
        "ev": pnl_total / len(rows),
        "ferr_mean": mean(ferr), "ferr_median": median(ferr),
        "ferr_std": pstdev(ferr), "ferr_abs_le3": sum(1 for e in ferr if abs(e) <= 3) / len(ferr),
        "ferr_hist": dict(sorted(Counter(min(max(e, -18), 18) // 3 * 3 for e in ferr).items())),
        "force_real_mean": mean(forces_real), "force_real_std": pstdev(forces_real),
        "force_autocorr": corr(force_pairs),
        "err_autocorr": corr(streak_err_pairs),
        "slots": dict(slots),
        "d1_mean": mean(d1s), "d2_mean": mean(d2s) if d2s else None,
        "d3_mean": mean(d3s) if d3s else None,
        "d1_hist_top": Counter(d1s).most_common(8),
        "best_off2": best_off2, "best_off3": best_off3,
        "inside_c1_pct": inside_c1 / len(rows),
        "region_eff": (captured17 / best17) if best17 else None,
        "by_score": {k: dict(v) for k, v in sorted(by_score.items())},
        "sessions": len(per_session),
        "worst_sessions": sorted(
            ((sid, v) for sid, v in per_session.items() if v["n"] >= 5),
            key=lambda kv: kv[1]["pnl"])[:3],
        "best_sessions": sorted(
            ((sid, v) for sid, v in per_session.items() if v["n"] >= 5),
            key=lambda kv: -kv[1]["pnl"])[:3],
    })
    return res


def main():
    data = load()
    for target in ("cw", "ccw"):
        rows = data[target]
        r = analyze_dir(target, rows)
        print(f"\n{'='*70}\nSENTIDO-ALVO {target.upper()} — n={r['n']} "
              f"(janela {rows[0]['timestamp'][:16]} → {rows[-1]['timestamp'][:16]})")
        print(f"reconstrução: força_prevista==gravada em {r['recon_force_ok']}/{r['full_n']} "
              f"(fallbacks 1-centro: {r['fallback_n']})")
        print(f"hit_rate={100*r['hit_rate']:.1f}%  P&L={r['pnl']:+.1f}u  "
              f"EV/aposta={r['ev']:+.3f}  stake={r['stake']:.0f}")
        print(f"força real: média={r['force_real_mean']:.1f} σ={r['force_real_std']:.1f} | "
              f"AUTOCORR força(t-1,t)={r['force_autocorr']:+.3f} | "
              f"autocorr erro={r['err_autocorr']:+.3f}")
        print(f"erro de força (real-prev): média={r['ferr_mean']:+.2f} mediana={r['ferr_median']:+.0f} "
              f"σ={r['ferr_std']:.1f} | |erro|<=3 (zona C1): {100*r['ferr_abs_le3']:.1f}%")
        print(f"hist erro (bucket 3): {r['ferr_hist']}")
        print(f"slots: {r['slots']} | Δmédio C1={r['d1_mean']:+.2f} "
              f"C2={r['d2_mean']:+.2f} C3={r['d3_mean']:+.2f}")
        print(f"top Δ(result,C1): {r['d1_hist_top']}")
        print(f"oracle offsets (picos de densidade fora ±3): off2≈{r['best_off2']} "
              f"off3≈{r['best_off3']} (praticado ~10/10) | dentro de C1±3: {100*r['inside_c1_pct']:.1f}%")
        print(f"region_efficiency (hits/melhor-17-posições): {100*(r['region_eff'] or 0):.1f}%")
        print("score → n/hit%/EV:", {k: (v['n'], f"{100*v['hit']/v['n']:.0f}%",
              f"{v['pnl']/v['n']:+.2f}") for k, v in r['by_score'].items() if v['n'] >= 3})
        print(f"sessões na janela: {r['sessions']}")
        print("piores sessões:", [(s, v['n'], f"{v['pnl']:+.0f}") for s, v in r['worst_sessions']])
        print("melhores sessões:", [(s, v['n'], f"{v['pnl']:+.0f}") for s, v in r['best_sessions']])


if __name__ == "__main__":
    main()

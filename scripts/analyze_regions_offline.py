"""A1-A3 (12/06) — Análise offline de regiões com os dados ATUAIS (premissa P1).

Responde às perguntas do plano proximos_passos_10_06.md §2 sem esperar dado novo:

  A1 — Atribuição de acerto por região: em qual slot (C1/C2/C3) cada hit caiu,
       lift por slot vs acaso (C1: 7/37; C2/C3: 5/37) e EV por slot — POR SENTIDO.
  A2 — Oracle das 3 melhores regiões: histograma circular de Δ(result, C1) por
       sentido + region_efficiency = densidade capturada pelas 17 posições
       apostadas ÷ densidade das 17 posições ótimas a posteriori (responde P5).
  A3 — Assimetria cw×ccw: hit/EV/efficiency por sessão; o sentido fraco é
       estrutural ou episódico?

Uso:
    python scripts/analyze_regions_offline.py [caminho/decisions.db] [saida.md]

Defaults: data/decisions.db e analise_regioes_12_06.md na raiz.
Somente leitura — nunca escreve no banco.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.roulette import roulette  # noqa: E402

WHEEL = list(roulette.WHEEL_SEQUENCE)
SIZE = len(WHEEL)
POS = {n: i for i, n in enumerate(WHEEL)}

# Atribuição de slot e cobertura por slot derivam da GEOMETRIA REAL gravada em
# sda_numbers (centro mais próximo), não de raios fixos — evita o viés legado
# 7+5+5 sobre dados fat-SAT (V2/V3). Espelha state.game._attribute_hit_region.


def signed_dist(frm: int, to: int) -> int | None:
    if frm not in POS or to not in POS:
        return None
    d = (POS[to] - POS[frm]) % SIZE
    return d - SIZE if d > SIZE // 2 else d


def attribute(centers: list[int], actual: int, hit: bool) -> tuple[str, int | None]:
    """Retorna (slot, dist_c1). hit=False → 'miss'; senão CENTRO MAIS PRÓXIMO
    (geometria-agnóstico, espelha state.game._attribute_hit_region pós-fix
    13/06; empate → C1>C2>C3). Antes usava raios fixos (3,2,2) e subcontava
    satélites sob a geometria viva fat-SAT (C1 raio 1; satélites 3, ou 4/2)."""
    if not centers:
        return "?", None
    d1 = signed_dist(centers[0], actual)
    if not hit:
        return "miss", d1
    best_idx, best = 0, None
    for idx, c in enumerate(centers[:3]):
        sd = signed_dist(c, actual)
        if sd is None:
            continue
        if best is None or abs(sd) < best:
            best, best_idx = abs(sd), idx
    return f"C{best_idx + 1}", d1


def cluster_sizes(centers: list[int], numbers: list[int]) -> dict[str, int]:
    """Quantos números apostados pertencem a cada cluster (centro mais próximo)
    — cobertura real por slot na geometria gravada, sem assumir raios legados."""
    sizes = {"C1": 0, "C2": 0, "C3": 0}
    cs = centers[:3]
    if not cs:
        return sizes
    for num in numbers:
        best_idx, best = 0, None
        for idx, c in enumerate(cs):
            sd = signed_dist(c, num)
            if sd is None:
                continue
            if best is None or abs(sd) < best:
                best, best_idx = abs(sd), idx
        sizes[f"C{best_idx + 1}"] += 1
    return sizes


def offsets_practiced(centers: list[int]) -> tuple[int | None, int | None]:
    """(off_c2, off_c3) praticados — distância circular C1→C2 / C1→C3."""
    if len(centers) < 3:
        return None, None
    o2 = signed_dist(centers[0], centers[1])
    o3 = signed_dist(centers[0], centers[2])
    return (abs(o2) if o2 is not None else None,
            abs(o3) if o3 is not None else None)


def load_rows(db: Path) -> list[dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = []
    for r in conn.execute(
        """
        SELECT id, session_id, spin_direction, sda_centers, sda_numbers,
               sda_score, final_action, gale_level, gale_bet_value,
               result_hit, result_actual, timestamp
        FROM decisions
        WHERE result_actual IS NOT NULL AND sda_centers IS NOT NULL
        ORDER BY id
        """
    ):
        try:
            centers = json.loads(r["sda_centers"] or "[]")
            numbers = json.loads(r["sda_numbers"] or "[]")
        except (ValueError, TypeError):
            continue
        if not centers or not numbers:
            continue
        rows.append({
            "id": r["id"],
            "session": r["session_id"],
            # Direção da predição = direção-alvo registrada na decisão.
            "dir": "cw" if (r["spin_direction"] or "") in ("horario", "cw") else "ccw",
            "centers": [int(c) for c in centers],
            "n": len(numbers),
            "numbers": [int(x) for x in numbers],
            "score": int(r["sda_score"] or 0),
            "action": r["final_action"] or "",
            "bet": float(r["gale_bet_value"] or 0),
            "hit": bool(r["result_hit"]),
            "actual": int(r["result_actual"]),
            "ts": r["timestamp"],
        })
    conn.close()
    return rows


def pnl_of(row: dict) -> float | None:
    """P&L da decisão (mesma fórmula do PROFIT-LEDGER B5)."""
    if row["action"] != "APOSTAR" or row["bet"] <= 0 or row["n"] <= 0:
        return None
    stake = row["bet"]
    return stake * (36.0 / row["n"] - 1.0) if row["hit"] else -stake


def fmt_pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def analyze(rows: list[dict]) -> str:
    out: list[str] = []
    out.append("# Análise offline de regiões — A1/A2/A3 (12/06)\n")
    out.append(f"> Dataset: {len(rows)} decisões com resultado e centros."
               " Somente leitura; fórmula de P&L = PROFIT-LEDGER (B5).\n")

    by_dir: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_dir[r["dir"]].append(r)

    # ============================= A1 =============================
    out.append("\n## A1 — Atribuição de acerto por região (por sentido)\n")
    out.append("| Sentido | Slot | Hits | Hit-rate slot | Acaso | Lift (pp) |")
    out.append("|---|---|---|---|---|---|")
    a1_summary: dict[str, dict] = {}
    for d in ("cw", "ccw"):
        rs = [r for r in by_dir[d] if len(r["centers"]) >= 3]
        n_total = len(rs)
        if n_total == 0:
            continue
        slots = Counter()
        cov_acc = {"C1": 0, "C2": 0, "C3": 0}
        for r in rs:
            slot, _ = attribute(r["centers"], r["actual"], r["hit"])
            slots[slot] += 1
            cs = cluster_sizes(r["centers"], r["numbers"])
            for kk in cov_acc:
                cov_acc[kk] += cs[kk]
        # cobertura média por slot na geometria REAL do dataset (não constante)
        cov_avg = {kk: cov_acc[kk] / n_total for kk in cov_acc}
        miss_cov = max(0.0, 37.0 - sum(cov_avg.values()))
        a1_summary[d] = {"n": n_total, "slots": dict(slots), "cov_avg": cov_avg}
        for slot in ("C1", "C2", "C3"):
            k = slots.get(slot, 0)
            rate = k / n_total
            base = cov_avg[slot] / 37.0
            out.append(
                f"| {d} | {slot} | {k}/{n_total} | {fmt_pct(rate)} | "
                f"{fmt_pct(base)} | {100 * (rate - base):+.1f} |"
            )
        miss = slots.get("miss", 0)
        out.append(f"| {d} | miss | {miss}/{n_total} | {fmt_pct(miss / n_total)} | "
                   f"{fmt_pct(miss_cov / 37)} | — |")

    out.append("\n**Leitura:** lift > 0 = a região captura mais que o acaso. "
               "Se C2 ou C3 tiver lift ≈ 0 num sentido, a '3ª melhor região' "
               "não está onde apostamos (recalibrar OFFSET_MIN/MAX).\n")

    # ============================= A2 =============================
    out.append("\n## A2 — Oracle das 3 melhores regiões (region_efficiency)\n")
    for d in ("cw", "ccw"):
        rs = [r for r in by_dir[d] if len(r["centers"]) >= 3]
        if not rs:
            continue
        hist = Counter()
        off2_used, off3_used = Counter(), Counter()
        for r in rs:
            sd = signed_dist(r["centers"][0], r["actual"])
            if sd is not None:
                hist[sd] += 1
            o2, o3 = offsets_practiced(r["centers"])
            if o2 is not None:
                off2_used[o2] += 1
            if o3 is not None:
                off3_used[o3] += 1

        n = sum(hist.values())
        med_o2 = off2_used.most_common(1)[0][0] if off2_used else 10
        med_o3 = off3_used.most_common(1)[0][0] if off3_used else 10
        # Densidade REALMENTE capturada = acertos (result ∈ sda_numbers gravado);
        # geometria-agnóstico, sem reconstruir o footprint por raios legados.
        captured = sum(1 for r in rs if r["hit"])
        best17 = sum(c for _, c in hist.most_common(17))
        eff = captured / best17 if best17 else 0.0

        mean_d = sum(k * v for k, v in hist.items()) / n if n else 0.0
        out.append(f"\n### Sentido {d} (n={n})")
        out.append(f"- offsets praticados (moda): C2=+{med_o2}, C3=−{med_o3}")
        out.append(f"- densidade capturada pelas 17 posições apostadas: "
                   f"{captured}/{n} ({fmt_pct(captured / n if n else 0)})")
        out.append(f"- teto a posteriori (17 melhores posições): {best17}/{n} "
                   f"({fmt_pct(best17 / n if n else 0)})")
        out.append(f"- **region_efficiency = {fmt_pct(eff)}**  ← responde P5")
        out.append(f"- viés do preditor C1: média de Δ(result,C1) = {mean_d:+.2f} "
                   f"posições (≠0 ⇒ erro sistemático de força; ~0 ⇒ erro é dos offsets)")
        top10 = ", ".join(f"{k:+d}:{v}" for k, v in hist.most_common(10))
        out.append(f"- top-10 posições de queda (Δ:count): {top10}")

    out.append("\n**Decomposição do regret:** se |média Δ| > 1 o problema dominante"
               " é o preditor de forças (C1); se a média ≈ 0 mas efficiency < 80%,"
               " os offsets C2/C3 estão mal posicionados (sigmoid).\n")

    # ============================= A3 =============================
    out.append("\n## A3 — Assimetria entre sentidos (estrutural × episódica)\n")
    sess_stats: dict[str, dict[str, dict]] = defaultdict(dict)
    for d in ("cw", "ccw"):
        per_sess: dict[str, list[dict]] = defaultdict(list)
        for r in by_dir[d]:
            per_sess[r["session"]].append(r)
        for s, rs in per_sess.items():
            bets = [r for r in rs if pnl_of(r) is not None]
            pnl = sum(pnl_of(r) for r in bets) if bets else 0.0
            hits = sum(1 for r in rs if r["hit"])
            sess_stats[s][d] = {
                "n": len(rs), "hit": hits / len(rs) if rs else 0.0,
                "bets": len(bets), "pnl": pnl,
            }

    both = {s: v for s, v in sess_stats.items()
            if "cw" in v and "ccw" in v and v["cw"]["n"] >= 10 and v["ccw"]["n"] >= 10}
    out.append(f"Sessões com ≥10 decisões em CADA sentido: {len(both)}\n")
    if both:
        cw_better = sum(1 for v in both.values() if v["cw"]["hit"] > v["ccw"]["hit"])
        gaps = [abs(v["cw"]["hit"] - v["ccw"]["hit"]) for v in both.values()]
        big_gap = sum(1 for g in gaps if g >= 0.15)
        out.append(f"- CW melhor que CCW em {cw_better}/{len(both)} sessões "
                   f"({fmt_pct(cw_better / len(both))}) — "
                   f"{'ESTRUTURAL (sempre o mesmo lado)' if cw_better / len(both) > 0.7 or cw_better / len(both) < 0.3 else 'EPISÓDICO (alterna por sessão)'}")
        out.append(f"- gap médio |hit_cw − hit_ccw| = {fmt_pct(sum(gaps) / len(gaps))}; "
                   f"sessões com gap ≥ 15pp: {big_gap}/{len(both)}")
        out.append("\n| Sessão | n cw | hit cw | pnl cw | n ccw | hit ccw | pnl ccw | gap |")
        out.append("|---|---|---|---|---|---|---|---|")
        worst = sorted(both.items(),
                       key=lambda kv: -abs(kv[1]["cw"]["hit"] - kv[1]["ccw"]["hit"]))
        for s, v in worst[:15]:
            gap = v["cw"]["hit"] - v["ccw"]["hit"]
            out.append(
                f"| {s} | {v['cw']['n']} | {fmt_pct(v['cw']['hit'])} | "
                f"{v['cw']['pnl']:+.0f} | {v['ccw']['n']} | {fmt_pct(v['ccw']['hit'])} | "
                f"{v['ccw']['pnl']:+.0f} | {100 * gap:+.0f}pp |"
            )
    out.append("\n**Leitura A3:** episódico + gaps grandes reforça o Achado 1 "
               "(estado adaptativo herdado entre dealers — corrigido pelo B1). "
               "Estrutural indica diferença física entre os sentidos → B3 "
               "(adaptação modulada por volatilidade) entra em avaliação.\n")

    # ============================= EV global =============================
    out.append("\n## EV de referência (sanity check do PROFIT-LEDGER)\n")
    bets = [r for r in rows if pnl_of(r) is not None]
    if bets:
        total = sum(pnl_of(r) for r in bets)
        staked = sum(r["bet"] for r in bets)
        out.append(f"- apostas: {len(bets)} | stake total: {staked:.0f}u | "
                   f"P&L: {total:+.1f}u | EV/aposta: {total / len(bets):+.3f}u "
                   f"({fmt_pct(total / staked if staked else 0)} do stake)")
        # Política CUT v1 simulada no histórico.
        cut = [r for r in bets if r["score"] >= 4 and r["n"] != 19]
        if cut:
            tc = sum(pnl_of(r) for r in cut)
            out.append(f"- política CUT v1 (score≥4, N≠19) no mesmo dataset: "
                       f"{len(cut)} apostas | EV/aposta: {tc / len(cut):+.3f}u")
    out.append("")
    return "\n".join(out)


def main() -> int:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "decisions.db"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "analise_regioes_12_06.md"
    if not db.exists():
        print(f"ERRO: banco não encontrado: {db}")
        return 1
    rows = load_rows(db)
    if not rows:
        print("ERRO: nenhuma decisão com resultado + centros no banco.")
        return 1
    report = analyze(rows)
    out_path.write_text(report, encoding="utf-8")
    print(f"OK: {len(rows)} decisões analisadas → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

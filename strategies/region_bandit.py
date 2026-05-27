"""SP-18 REGION-03: Bandit epsilon-greedy entre regioes C1/C2/C3.

Consome saida de ``dna_logger.dna_summary()`` filtrada para features
``region_C1``, ``region_C2``, ``region_C3`` e retorna recomendacao de
qual regiao priorizar.

Algoritmo: epsilon-greedy classico.
- Com prob ``epsilon``: explora (random uniform entre regioes).
- Com prob ``1-epsilon``: exploit (maior ``avg_lift_pp``).
- Fallback: se nenhuma regiao tem ``n >= min_n``, retorna None (=> SDA17 segue logica default).

Stateless por design — toda decisao consulta dna_summary fresco. Cache
deve ser feito pelo caller (mesmo padrao SP-30 wheel_dist provider).
"""
from __future__ import annotations

import random
from typing import Iterable, Optional


REGION_FEATURES = ("region_C1", "region_C2", "region_C3")


def choose_region(
    summary_rows: Iterable[dict],
    *,
    epsilon: float = 0.1,
    min_n: int = 20,
    rng: Optional[random.Random] = None,
) -> Optional[str]:
    """Retorna 'C1', 'C2', 'C3' ou None.

    Args:
        summary_rows: iteravel de dicts no formato ``dna_summary()`` —
            keys: feature_name, bucket, n, hit_rate, avg_lift_pp.
        epsilon: probabilidade de exploracao.
        min_n: minimo de amostras por regiao para confiar no lift.
        rng: opcional Random instance (testes deterministicos).

    Returns:
        Nome da regiao (sem prefixo "region_") ou None se sem dados.
    """
    r = rng or random.Random()

    # Agrega por feature_name (soma n, media ponderada de lift).
    agg: dict[str, dict] = {}
    for row in summary_rows or []:
        fn = row.get("feature_name", "")
        if fn not in REGION_FEATURES:
            continue
        n = int(row.get("n", 0) or 0)
        lift = row.get("avg_lift_pp")
        if lift is None or n <= 0:
            continue
        cur = agg.setdefault(fn, {"n": 0, "weighted_lift": 0.0})
        cur["n"] += n
        cur["weighted_lift"] += float(lift) * n

    eligible: list[tuple[str, float]] = []
    for fn, v in agg.items():
        if v["n"] >= min_n:
            eligible.append((fn.replace("region_", ""), v["weighted_lift"] / v["n"]))

    if not eligible:
        return None

    if r.random() < epsilon:
        return r.choice([e[0] for e in eligible])

    eligible.sort(key=lambda x: x[1], reverse=True)
    return eligible[0][0]

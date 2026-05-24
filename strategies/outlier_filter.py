"""S11 — Outlier Filter.

Remove forcas anomalas (acima de Q3 + 1.5*IQR, abaixo de Q1 - 1.5*IQR)
para que medias/predicoes nao sejam distorcidas. Por direcao isolado.

Status: implementacao funcional (Tukey fences). Pronto para uso.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Sequence


@dataclass(frozen=True)
class OutlierResult:
    clean: list[float]
    removed: list[float]
    lower_fence: float
    upper_fence: float


def filter_outliers_tukey(values: Sequence[float], k: float = 1.5) -> OutlierResult:
    """Filtra outliers usando Tukey fences.

    Args:
        values: serie de valores (ex: spin_force das ultimas N jogadas).
        k: multiplicador do IQR (1.5 standard, 3.0 conservador).

    Returns:
        OutlierResult com `clean` (sem outliers) e `removed`.
    """
    if not values:
        return OutlierResult([], [], 0.0, 0.0)
    if len(values) < 4:
        # IQR sem sentido para n<4; nao filtra.
        return OutlierResult(list(values), [], min(values), max(values))

    sorted_v = sorted(values)
    n = len(sorted_v)
    mid = n // 2
    lower_half = sorted_v[:mid]
    upper_half = sorted_v[mid + 1:] if n % 2 else sorted_v[mid:]
    q1 = median(lower_half)
    q3 = median(upper_half)
    iqr = q3 - q1
    lower_fence = q1 - k * iqr
    upper_fence = q3 + k * iqr

    clean: list[float] = []
    removed: list[float] = []
    for v in values:
        if lower_fence <= v <= upper_fence:
            clean.append(v)
        else:
            removed.append(v)
    return OutlierResult(clean, removed, lower_fence, upper_fence)

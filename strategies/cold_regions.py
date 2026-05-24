"""S10 — Cold Regions Strategy.

Detecta regioes da roleta nao visitadas nas ultimas N janelas e da
boost de probabilidade. Por direcao isolado (cw vs ccw).

Status: skeleton. Requer feature flag `strategy_cold_regions` (off por default).
Depende de: spins_history + outbox features ativo (S5).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ColdRegionScore:
    region_id: int
    visits_last_n: int
    coldness: float  # 0..1; 1 = mais fria


class ColdRegionsStrategy:
    """Skeleton. Implementacao real apos coletar dados S5."""

    def __init__(self, window_size: int = 24, num_regions: int = 8):
        if window_size < 1:
            raise ValueError("window_size deve ser >= 1")
        if num_regions < 2:
            raise ValueError("num_regions deve ser >= 2")
        self.window_size = window_size
        self.num_regions = num_regions

    def score(self, recent_region_ids: Sequence[int]) -> list[ColdRegionScore]:
        """Retorna coldness por regiao. Quanto menos visitas, mais cold.

        Args:
            recent_region_ids: ultimas N visitas, mais recente por ultimo.

        Returns:
            Lista len=num_regions, ordenada por region_id asc.
        """
        window = list(recent_region_ids)[-self.window_size:]
        counts = [0] * self.num_regions
        for r in window:
            if 0 <= r < self.num_regions:
                counts[r] += 1
        max_count = max(counts) if counts else 0
        scores: list[ColdRegionScore] = []
        for i, c in enumerate(counts):
            coldness = 1.0 - (c / max_count) if max_count > 0 else 1.0
            scores.append(ColdRegionScore(i, c, coldness))
        return scores

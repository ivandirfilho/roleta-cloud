"""S12 — Shadow Predictor.

Roda em paralelo ao predictor principal sem afetar decisao real.
Loga divergencias para auditoria. Habilitado por feature flag
`strategy_shadow_predictor`.

Status: skeleton com interface estavel. Implementacao real depende de
modelo vetorial (S7) + grafo (S8) prontos.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShadowPrediction:
    predicted_force: float
    predicted_region: int
    confidence: float  # 0..1
    source: str  # 'pca+knn', 'cypher_path', etc.


class ShadowPredictor:
    """Interface estavel. Cada implementacao concreta plugavel."""

    def predict(self, direction: str, features_6d: list[float]) -> Optional[ShadowPrediction]:
        raise NotImplementedError("subclasse deve implementar predict")


class NoopShadowPredictor(ShadowPredictor):
    """Implementacao default — nao prediz nada. Usado quando S7 nao treinado."""

    def predict(self, direction: str, features_6d: list[float]) -> Optional[ShadowPrediction]:
        return None


def compare_and_log(
    primary_decision: dict[str, Any],
    shadow: Optional[ShadowPrediction],
    decision_id: int,
) -> None:
    """Loga divergencia primary vs shadow para auditoria offline."""
    if shadow is None:
        return
    delta_force = abs(primary_decision.get("predicted_force", 0) - shadow.predicted_force)
    logger.info(
        "shadow_compare decision_id=%s delta_force=%.2f confidence=%.2f source=%s",
        decision_id,
        delta_force,
        shadow.confidence,
        shadow.source,
    )

"""S7 — Autoencoder/PCA 6→4→6 para reduzir features de spin.

Estrategia: comecar com PCA (linear, estavel, sem dependencia de TF) e
evoluir para MLP autoencoder quando houver volume suficiente de dados.

Treino: offline via `scripts/train_autoencoder.py` (le PG, salva .joblib).
Serving: load do .joblib + encode() em hot path.

Entrada: vetor 6-dim conforme `database/outbox_integration._extract_raw_features`.
Saida: vetor 4-dim (compressed) — alimenta cw/ccw.spins_vectors.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = Path("models/spin_autoencoder.joblib")


class SpinEncoder:
    """Wrapper carregavel via joblib. PCA(n_components=4) por default.

    API estavel para o resto do sistema; troca de PCA->MLP nao deve
    quebrar consumidores.
    """

    def __init__(self, model=None, kind: str = "pca"):
        self._model = model
        self.kind = kind

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL_PATH) -> Optional["SpinEncoder"]:
        try:
            import joblib  # type: ignore
        except ImportError:
            logger.warning("joblib nao instalado; SpinEncoder.load=None")
            return None
        if not path.exists():
            logger.info("modelo nao encontrado em %s", path)
            return None
        try:
            payload = joblib.load(path)
            return cls(model=payload["model"], kind=payload.get("kind", "pca"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("falha load modelo: %s", exc)
            return None

    def encode(self, features_6d: Sequence[float]) -> Optional[list[float]]:
        """6d -> 4d. Retorna None se modelo nao carregado."""
        if self._model is None:
            return None
        try:
            import numpy as np  # type: ignore
            arr = np.asarray(features_6d, dtype=float).reshape(1, -1)
            out = self._model.transform(arr)
            return out[0].tolist()
        except Exception as exc:  # noqa: BLE001
            logger.warning("encode falhou: %s", exc)
            return None


def train_pca(X, n_components: int = 4):
    """Treina PCA simples. X deve ser array (n_samples, 6).

    Legado (S7). Preferir train_pipeline() — whiten normaliza a SAÍDA do
    PCA mas não a entrada, então dims com escalas distintas dominam os
    componentes.
    """
    from sklearn.decomposition import PCA  # type: ignore
    model = PCA(n_components=n_components, whiten=True, random_state=42)
    model.fit(X)
    return model


def train_pipeline(X, n_components: int = 4):
    """H5 (03/08): StandardScaler → PCA(whiten) num Pipeline sklearn.

    Normaliza a ENTRADA antes do PCA (as 6 dims têm escalas distintas:
    spin_force ~0-100, taxas 0-1, scores 0-10). O Pipeline expõe
    .transform — API idêntica ao PCA puro, SpinEncoder.encode não muda.
    """
    from sklearn.decomposition import PCA  # type: ignore
    from sklearn.pipeline import Pipeline  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("pca", PCA(n_components=n_components, whiten=True, random_state=42)),
    ])
    model.fit(X)
    return model


def save_encoder(model, path: Path = DEFAULT_MODEL_PATH, kind: str = "pca") -> None:
    import joblib  # type: ignore
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "kind": kind, "version": 1}, path)
    logger.info("encoder salvo em %s", path)

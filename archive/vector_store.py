# Roleta Cloud - Vector Store (LanceDB)
# Similarity search para padrões históricos de força
#
# NOTA: Módulo preparatório — ativar quando volume > 5.000 decisões verificadas.
# Atualmente o sistema tem ~1.927 decisões, insuficiente para similarity search eficaz.

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# LanceDB é importado sob demanda para não ser dependência obrigatória
_lancedb = None
_pa = None


def _ensure_deps():
    """Importa dependências opcionais (lancedb + pyarrow)."""
    global _lancedb, _pa
    if _lancedb is None:
        try:
            import lancedb
            import pyarrow as pa
            _lancedb = lancedb
            _pa = pa
        except ImportError:
            raise RuntimeError(
                "LanceDB não instalado. Execute: pip install lancedb pyarrow"
            )


class VectorStore:
    """
    Store de vetores para similarity search em padrões de força.
    
    Embedding de cada decisão:
    - force_mean: Média das últimas N forças
    - force_std: Desvio padrão
    - force_trend: Tendência (regressão linear slope)
    - force_range: Max - Min
    - sda_score: Score do SDA-17
    - gale_level: Nível do Martingale
    - hit_rate_c4: Taxa de acerto curto prazo
    
    Use case: dado o estado atual, encontrar decisões passadas similares
    e verificar se o hit_rate nessas situações justifica a aposta.
    """

    TABLE_NAME = "force_patterns"
    DEFAULT_PATH = Path(__file__).parent.parent / "data" / "vector_store"

    def __init__(self, db_path: str = None):
        _ensure_deps()
        self.db_path = str(db_path or self.DEFAULT_PATH)
        self.db = _lancedb.connect(self.db_path)
        self._ensure_table()

    def _ensure_table(self):
        """Cria tabela se não existir."""
        if self.TABLE_NAME not in self.db.table_names():
            schema = _pa.schema([
                _pa.field("decision_id", _pa.int64()),
                _pa.field("session_id", _pa.string()),
                _pa.field("force_mean", _pa.float32()),
                _pa.field("force_std", _pa.float32()),
                _pa.field("force_trend", _pa.float32()),
                _pa.field("force_range", _pa.float32()),
                _pa.field("sda_score", _pa.int32()),
                _pa.field("gale_level", _pa.int32()),
                _pa.field("hit_rate_c4", _pa.float32()),
                _pa.field("result_hit", _pa.bool_()),
                _pa.field("vector", _pa.list_(_pa.float32(), 7)),
            ])
            self.db.create_table(self.TABLE_NAME, schema=schema)
            logger.info(f"[VECTOR_STORE] Tabela '{self.TABLE_NAME}' criada em {self.db_path}")

    @staticmethod
    def compute_embedding(
        forces: List[int],
        sda_score: int,
        gale_level: int,
        hit_rate_c4: float,
    ) -> List[float]:
        """
        Computa vetor de embedding a partir do estado atual.
        
        Normalizado para [0, 1] em cada dimensão.
        """
        if not forces or len(forces) < 2:
            return [0.0] * 7

        import statistics

        mean = statistics.mean(forces)
        std = statistics.stdev(forces) if len(forces) > 1 else 0.0
        trend = (forces[0] - forces[-1]) / max(len(forces), 1)
        rng = max(forces) - min(forces)

        # Normalizar para [0, 1]
        return [
            min(mean / 37.0, 1.0),       # force_mean (0-37)
            min(std / 18.0, 1.0),         # force_std (0-18 aprox)
            (trend + 18.0) / 36.0,        # force_trend (-18 a +18) → (0, 1)
            min(rng / 37.0, 1.0),         # force_range (0-37)
            min(sda_score / 6.0, 1.0),    # sda_score (0-6)
            min(gale_level / 4.0, 1.0),   # gale_level (1-4)
            hit_rate_c4,                   # hit_rate_c4 (0-1)
        ]

    def add_pattern(
        self,
        decision_id: int,
        session_id: str,
        forces: List[int],
        sda_score: int,
        gale_level: int,
        hit_rate_c4: float,
        result_hit: bool,
    ) -> None:
        """Adiciona um padrão ao store."""
        vec = self.compute_embedding(forces, sda_score, gale_level, hit_rate_c4)

        import statistics
        mean = statistics.mean(forces) if forces else 0
        std = statistics.stdev(forces) if len(forces) > 1 else 0.0
        trend = (forces[0] - forces[-1]) / max(len(forces), 1) if forces else 0
        rng = (max(forces) - min(forces)) if forces else 0

        table = self.db.open_table(self.TABLE_NAME)
        table.add([{
            "decision_id": decision_id,
            "session_id": session_id,
            "force_mean": float(mean),
            "force_std": float(std),
            "force_trend": float(trend),
            "force_range": float(rng),
            "sda_score": sda_score,
            "gale_level": gale_level,
            "hit_rate_c4": hit_rate_c4,
            "result_hit": result_hit,
            "vector": vec,
        }])

    def search_similar(
        self,
        forces: List[int],
        sda_score: int,
        gale_level: int,
        hit_rate_c4: float,
        k: int = 20,
    ) -> Dict[str, Any]:
        """
        Busca padrões similares e retorna taxa de acerto histórica.
        
        Returns:
            {
                "similar_count": int,
                "similar_hit_rate": float,
                "confidence": str,
                "matches": list
            }
        """
        vec = self.compute_embedding(forces, sda_score, gale_level, hit_rate_c4)

        table = self.db.open_table(self.TABLE_NAME)
        results = (
            table.search(vec)
            .limit(k)
            .to_pandas()
        )

        if results.empty:
            return {
                "similar_count": 0,
                "similar_hit_rate": 0.0,
                "confidence": "sem_dados",
                "matches": [],
            }

        hit_rate = results["result_hit"].mean()
        count = len(results)

        if count >= 15 and hit_rate >= 0.6:
            confidence = "alta"
        elif count >= 10 and hit_rate >= 0.45:
            confidence = "media"
        else:
            confidence = "baixa"

        return {
            "similar_count": count,
            "similar_hit_rate": round(float(hit_rate), 3),
            "confidence": confidence,
            "matches": results[["decision_id", "force_mean", "sda_score", "result_hit", "_distance"]]
            .head(5)
            .to_dict(orient="records"),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do vector store."""
        try:
            table = self.db.open_table(self.TABLE_NAME)
            df = table.to_pandas()
            return {
                "total_patterns": len(df),
                "hit_rate_overall": round(float(df["result_hit"].mean()), 3) if len(df) > 0 else 0,
                "avg_sda_score": round(float(df["sda_score"].mean()), 1) if len(df) > 0 else 0,
                "ready": len(df) >= 5000,
            }
        except Exception:
            return {"total_patterns": 0, "ready": False}

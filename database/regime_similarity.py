"""S-STRAT-12: similaridade de regimes via pgvector.

Consulta `cw/ccw.spins_vectors` (já populado por OBS-25-01/spin_features
quando dual_write_pg estiver ativo). Para um vetor de features atual,
retorna os top-K regimes históricos mais similares (distância cosine).

Use case principal: o bet_advisor pode, no futuro, consultar "regimes
parecidos" e ver qual foi a accuracy observada nos próximos N spins —
sinal adicional além da heurística in-memory.

Falha-aberta: sem PG ou sem dados, retorna lista vazia. Nunca derruba
o caller.

Comparação a S-STRAT-8 (feature_store):
- S-STRAT-8: lag features tabulares (acc, streaks) para decisão imediata.
- S-STRAT-12: similaridade vetorial para "regime matching" (ML-leve).
"""
from __future__ import annotations

import logging
import os
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None
    RealDictCursor = None

logger = logging.getLogger(__name__)

_ALLOWED = {"cw", "ccw"}
EXPECTED_DIM = 6


class RegimeSimilarityReader:
    """Conexão lazy + reconnect. Read-only."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get("ROLETA_PG_DSN")
        self._conn: Any = None

    def _ensure(self) -> Any:
        if psycopg2 is None or not self.dsn:
            return None
        if self._conn is None or self._conn.closed:
            try:
                self._conn = psycopg2.connect(self.dsn)
                self._conn.autocommit = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("regime_sim_connect_failed error=%s", exc)
                self._conn = None
        return self._conn

    def find_similar(
        self,
        direction: str,
        query_vec: list[float],
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Top-K spins históricos mais próximos (cosine) ao query_vec.

        Retorna lista de dicts: id, ts, decision_id, distance (0..2).
        Distance 0 = idêntico, distance 2 = oposto.
        """
        if direction not in _ALLOWED:
            raise ValueError(f"direction must be cw|ccw, got {direction!r}")
        if not isinstance(query_vec, list) or len(query_vec) != EXPECTED_DIM:
            raise ValueError(
                f"query_vec must be list of {EXPECTED_DIM} floats, got len={len(query_vec) if isinstance(query_vec, list) else type(query_vec).__name__}"
            )
        if limit <= 0 or limit > 100:
            raise ValueError(f"limit must be 1..100, got {limit}")
        for x in query_vec:
            if not isinstance(x, (int, float)):
                raise ValueError(f"query_vec contains non-numeric: {x!r}")

        conn = self._ensure()
        if conn is None:
            return []
        schema = direction
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # pgvector cosine distance operator: <=>
                cur.execute(
                    f"""
                    SELECT id, ts, decision_id,
                           (raw_features <=> %s::vector) AS distance
                    FROM {schema}.spins_vectors
                    ORDER BY raw_features <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_vec, query_vec, limit),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            logger.warning("regime_sim_query_failed direction=%s error=%s", direction, exc)
            try:
                self._conn = None
            except Exception:  # noqa: BLE001
                pass
            return []

    def regime_score(
        self,
        direction: str,
        query_vec: list[float],
        *,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Resumo agregado: média de distance dos top-K + hit-rate observada.

        Para hit-rate, faz JOIN com cw|ccw.spin_features (S-STRAT-8) via
        decision_id. Se spin_features ainda não populado, hit_rate=None.
        """
        if direction not in _ALLOWED:
            raise ValueError(f"direction must be cw|ccw, got {direction!r}")
        if not isinstance(query_vec, list) or len(query_vec) != EXPECTED_DIM:
            raise ValueError(f"query_vec must be list of {EXPECTED_DIM} floats")
        if limit <= 0 or limit > 200:
            raise ValueError(f"limit must be 1..200, got {limit}")

        conn = self._ensure()
        if conn is None:
            return {"n": 0, "avg_distance": None, "hit_rate": None, "direction": direction}
        schema = direction
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    WITH top AS (
                        SELECT id, decision_id,
                               (raw_features <=> %s::vector) AS distance
                        FROM {schema}.spins_vectors
                        ORDER BY raw_features <=> %s::vector
                        LIMIT %s
                    )
                    SELECT
                        count(*)::int AS n,
                        avg(distance)::float AS avg_distance,
                        avg(CASE WHEN sf.hit IS TRUE THEN 1.0
                                 WHEN sf.hit IS FALSE THEN 0.0
                                 ELSE NULL END)::float AS hit_rate
                    FROM top
                    LEFT JOIN {schema}.spin_features sf
                      ON sf.decision_id = top.decision_id;
                    """,
                    (query_vec, query_vec, limit),
                )
                row = cur.fetchone() or {}
                return {
                    "direction": direction,
                    "n": int(row.get("n") or 0),
                    "avg_distance": row.get("avg_distance"),
                    "hit_rate": row.get("hit_rate"),
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("regime_score_failed direction=%s error=%s", direction, exc)
            return {"n": 0, "avg_distance": None, "hit_rate": None, "direction": direction}

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._conn = None

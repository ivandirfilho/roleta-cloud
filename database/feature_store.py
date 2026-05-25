"""S-STRAT-8: leitura do feature store cw/ccw.spin_features.

API simples para o bet_advisor (ou backtest harness S-STRAT-9) consumir
lag features sem precisar reimplementar window queries.

Falha-aberta: se PG indisponível, retorna None — caller usa heurísticas
in-memory normais (recent_hits do game_state).
"""
from __future__ import annotations

import logging
import os
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover — módulo opcional
    psycopg2 = None
    RealDictCursor = None

logger = logging.getLogger(__name__)

_ALLOWED = {"cw", "ccw"}


class FeatureStoreReader:
    """Conexão lazy + reconnect. Pensado para uso síncrono leve."""

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
                logger.warning("feature_store_connect_failed error=%s", exc)
                self._conn = None
        return self._conn

    def get_latest(self, direction: str) -> dict[str, Any] | None:
        """Retorna a feature row mais recente do schema, ou None."""
        if direction not in _ALLOWED:
            raise ValueError(f"direction must be cw|ccw, got {direction!r}")
        conn = self._ensure()
        if conn is None:
            return None
        schema = direction
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT id, ts, decision_id, spin_number, hit,
                           centro_previsto, gale_level,
                           recent_acc_10, recent_acc_50,
                           streak_miss, streak_hit, last_20_hits, meta
                    FROM {schema}.spin_features
                    ORDER BY id DESC
                    LIMIT 1;
                    """
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("feature_store_read_failed direction=%s error=%s", direction, exc)
            try:
                self._conn = None
            except Exception:  # noqa: BLE001
                pass
            return None

    def get_window(self, direction: str, limit: int = 50) -> list[dict[str, Any]]:
        """Retorna até `limit` rows mais recentes (mais recente primeiro)."""
        if direction not in _ALLOWED:
            raise ValueError(f"direction must be cw|ccw, got {direction!r}")
        if limit <= 0 or limit > 1000:
            raise ValueError(f"limit must be 1..1000, got {limit}")
        conn = self._ensure()
        if conn is None:
            return []
        schema = direction
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT id, ts, hit, recent_acc_10, recent_acc_50,
                           streak_miss, streak_hit
                    FROM {schema}.spin_features
                    ORDER BY id DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            logger.warning("feature_store_window_failed direction=%s error=%s", direction, exc)
            return []

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._conn = None

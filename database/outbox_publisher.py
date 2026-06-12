"""Helper para o app publicar eventos em shared.outbox via PG.

Uso futuro (S5-código de domínio):
    from database.outbox_publisher import OutboxPublisher
    pub = OutboxPublisher(dsn=os.environ["ROLETA_PG_DSN"])
    pub.publish_spin_features(direction="cw", raw=[83,75,12,3,8,-5], decision_id=42)

Idempotente via `event_uuid` UNIQUE. Se publicar mesmo UUID 2x, segundo é no-op.

NÃO usado em runtime atual (v4.4.x) — feature flag `dual_write_pg` precisa estar
ativa para o publisher ser instanciado. Hook em `database/sqlite_repo.py`
.save_decision() vem em sprint dedicada.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover — modulo opcional ate S5 ativar
    psycopg2 = None
    Json = None

logger = logging.getLogger(__name__)


class OutboxPublisher:
    """Publica eventos no `shared.outbox` do PG.

    Conexão lazy + reconnect automático em OperationalError.
    Não bloqueia o app se PG cair: levanta exceção e caller decide
    (recomendação: log + continue, app continua escrevendo SQLite normal).
    """

    def __init__(self, dsn: str):
        if psycopg2 is None:
            raise RuntimeError(
                "psycopg2 nao instalado. Adicionar a requirements.txt e reinstalar."
            )
        self.dsn = dsn
        self._conn: Any = None

    def _ensure_conn(self) -> Any:
        if self._conn is None or self._conn.closed:
            # INCIDENT 12/06 21:16: conexão TCP half-open após idle longo
            # travou o caminho crítico por 9.6s. connect_timeout limita o
            # handshake; keepalives matam conexões mortas em ~30s de idle
            # (em vez de stall no primeiro execute).
            self._conn = psycopg2.connect(
                self.dsn,
                connect_timeout=3,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            )
            self._conn.autocommit = True
        return self._conn

    def _reset_conn(self) -> None:
        try:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
        except Exception:  # noqa: BLE001
            pass
        self._conn = None

    def publish(
        self,
        *,
        aggregate: str,
        aggregate_id: str,
        payload: dict[str, Any],
        event_uuid: str | None = None,
    ) -> str:
        """Publica 1 evento. Retorna event_uuid (gera se nao passado).

        ON CONFLICT (event_uuid) DO NOTHING garante idempotencia.
        """
        evt_uuid = event_uuid or str(uuid.uuid4())
        # Retry-once com reset: OperationalError em conexão idle/morta não
        # pode custar mais que 1 reconnect (INCIDENT 12/06).
        for attempt in (1, 2):
            try:
                conn = self._ensure_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO shared.outbox (event_uuid, aggregate, aggregate_id, payload)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (event_uuid) DO NOTHING;
                        """,
                        (evt_uuid, aggregate, aggregate_id, Json(payload)),
                    )
                return evt_uuid
            except psycopg2.OperationalError:
                self._reset_conn()
                if attempt == 2:
                    raise
        return evt_uuid

    def publish_spin_features(
        self,
        *,
        direction: str,
        raw_features: list[float],
        decision_id: int | None = None,
        meta: dict[str, Any] | None = None,
        event_uuid: str | None = None,
    ) -> str:
        """Conveniência para o caso mais comum."""
        if direction not in ("cw", "ccw"):
            raise ValueError(f"direction must be cw|ccw, got {direction!r}")
        if len(raw_features) != 6:
            raise ValueError(f"raw_features deve ter 6 valores, got {len(raw_features)}")
        payload = {
            "event_type": "spin_features",
            "direction": direction,
            "raw_features": list(raw_features),
            "decision_id": decision_id,
            "meta": meta or {},
        }
        agg_id = f"{direction}:{decision_id}" if decision_id else f"{direction}:?"
        return self.publish(
            aggregate="spin",
            aggregate_id=agg_id,
            payload=payload,
            event_uuid=event_uuid,
        )

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None

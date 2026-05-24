"""CDC worker — S5 do plano_implentacao_pos_sessao_24_05.md.

Consome `shared.outbox` e replica eventos para tabelas finais
(`cw.spins_vectors`, `ccw.spins_vectors`, futuramente outras).

Roda como container separado (docker-compose.pg.yml > service `cdc-worker`).
Não toca SQLite — esse é write-side autoritativo até S5 completar.

Design:
- SELECT ... FOR UPDATE SKIP LOCKED → multi-instância seguro (idempotente).
- 1 transação por batch (default 100); falha individual marca a linha 'failed'
  com retries++; após 5 retries vai para DLQ (status='failed' fica permanente,
  alerta visível via `SELECT count(*) FROM shared.outbox WHERE status='failed'`).
- Backoff exponencial entre batches vazios (1s -> 30s).

Payload `spin_features`:
{
  "event_type": "spin_features",
  "direction": "cw" | "ccw",
  "raw_features": [f1, f2, f3, f4, f5, f6],  # 6 floats
  "decision_id": 12345,                       # opcional, FK soft para SQLite
  "meta": { ... }                             # opcional
}
"""
from __future__ import annotations

import json
import logging
import os
import select
import signal
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import Json, RealDictCursor

logger = logging.getLogger("cdc_worker")

MAX_RETRIES = int(os.environ.get("CDC_MAX_RETRIES", "5"))
BATCH_SIZE = int(os.environ.get("CDC_BATCH_SIZE", "100"))
IDLE_SLEEP_INITIAL = float(os.environ.get("CDC_IDLE_SLEEP_INITIAL", "1.0"))
IDLE_SLEEP_MAX = float(os.environ.get("CDC_IDLE_SLEEP_MAX", "30.0"))
# S-I: LISTEN/NOTIFY aditivo (default ON; falha-aberta -> polling normal)
USE_LISTEN_NOTIFY = os.environ.get("CDC_USE_LISTEN_NOTIFY", "1") not in ("0", "false", "False", "")
NOTIFY_CHANNEL = os.environ.get("CDC_NOTIFY_CHANNEL", "outbox_new")
ALLOWED_DIRECTIONS = {"cw", "ccw"}
EXPECTED_DIM = 6

_shutdown = False
_notify_received_total = 0
_notify_wakeups_total = 0


def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown
    logger.info("worker_signal_received signum=%s; will stop after current batch", signum)
    _shutdown = True


def _connect(dsn: str) -> psycopg2.extensions.connection:
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    return conn


@contextmanager
def _cursor(conn: psycopg2.extensions.connection) -> Iterator[Any]:
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        yield cur
    finally:
        cur.close()


def _claim_batch(cur: Any, batch_size: int) -> list[dict[str, Any]]:
    """Pega N linhas pendentes com SKIP LOCKED (multi-worker safe)."""
    cur.execute(
        """
        SELECT id, event_uuid, aggregate, aggregate_id, payload, retries
        FROM shared.outbox
        WHERE status = 'pending'
        ORDER BY id
        FOR UPDATE SKIP LOCKED
        LIMIT %s;
        """,
        (batch_size,),
    )
    return list(cur.fetchall())


def _validate_spin_features(payload: dict[str, Any]) -> None:
    direction = payload.get("direction")
    if direction not in ALLOWED_DIRECTIONS:
        raise ValueError(f"invalid direction: {direction!r}")
    raw = payload.get("raw_features")
    if not isinstance(raw, list) or len(raw) != EXPECTED_DIM:
        raise ValueError(
            f"raw_features must be a list of {EXPECTED_DIM} floats, got {raw!r}"
        )
    for x in raw:
        if not isinstance(x, (int, float)):
            raise ValueError(f"raw_features contains non-numeric: {x!r}")


def _apply_spin_features(cur: Any, payload: dict[str, Any]) -> None:
    """Insere em cw|ccw.spins_vectors. Schema fixo (CW/CCW nao misturam)."""
    _validate_spin_features(payload)
    direction = payload["direction"]
    raw = payload["raw_features"]
    decision_id = payload.get("decision_id")
    meta = payload.get("meta") or {}

    # SQL fixo por direcao — sem string interpolation com input arbitrario.
    if direction == "cw":
        sql = "INSERT INTO cw.spins_vectors (decision_id, raw_features, meta) VALUES (%s, %s::vector, %s)"
    else:
        sql = "INSERT INTO ccw.spins_vectors (decision_id, raw_features, meta) VALUES (%s, %s::vector, %s)"

    cur.execute(sql, (decision_id, raw, Json(meta)))


HANDLERS = {
    "spin_features": _apply_spin_features,
}


def _process_event(cur: Any, event: dict[str, Any]) -> None:
    payload = event["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    event_type = payload.get("event_type")
    handler = HANDLERS.get(event_type)
    if handler is None:
        raise ValueError(f"unknown event_type: {event_type!r}")
    handler(cur, payload)


def _mark_processed(cur: Any, event_id: int) -> None:
    cur.execute(
        """
        UPDATE shared.outbox
        SET status = 'processed', processed_at = now()
        WHERE id = %s;
        """,
        (event_id,),
    )


def _mark_failed(cur: Any, event_id: int, retries: int, error: str) -> None:
    new_status = "failed" if (retries + 1) >= MAX_RETRIES else "pending"
    cur.execute(
        """
        UPDATE shared.outbox
        SET status = %s, retries = retries + 1, error = %s
        WHERE id = %s;
        """,
        (new_status, error[:1000], event_id),
    )


def process_one_batch(conn: psycopg2.extensions.connection, batch_size: int = BATCH_SIZE) -> int:
    """Processa 1 batch. Retorna no de eventos com sucesso. Visivel para testes."""
    processed_ok = 0
    with _cursor(conn) as cur:
        events = _claim_batch(cur, batch_size)
        if not events:
            conn.rollback()
            return 0

        for event in events:
            event_id = event["id"]
            retries = event["retries"]
            try:
                # SAVEPOINT — falha de 1 evento nao derruba o batch inteiro.
                cur.execute("SAVEPOINT sp_event;")
                _process_event(cur, event)
                _mark_processed(cur, event_id)
                cur.execute("RELEASE SAVEPOINT sp_event;")
                processed_ok += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "event_failed id=%s uuid=%s error=%s",
                    event_id,
                    event["event_uuid"],
                    exc,
                )
                cur.execute("ROLLBACK TO SAVEPOINT sp_event;")
                _mark_failed(cur, event_id, retries, str(exc))
        conn.commit()
    return processed_ok


def _setup_listen(dsn: str) -> Optional[psycopg2.extensions.connection]:
    """S-I: cria conexao dedicada em autocommit + LISTEN outbox_new.

    Retorna None se nao habilitado ou falhou (worker continua em polling puro).
    """
    if not USE_LISTEN_NOTIFY:
        return None
    try:
        conn = psycopg2.connect(dsn)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            cur.execute(f"LISTEN {NOTIFY_CHANNEL};")
        logger.info("listen_notify_enabled channel=%s", NOTIFY_CHANNEL)
        return conn
    except Exception as exc:  # noqa: BLE001
        logger.warning("listen_notify_setup_failed error=%s; falling back to polling-only", exc)
        return None


def _wait_for_notify(conn_listen: Optional[psycopg2.extensions.connection], timeout: float) -> bool:
    """Bloqueia ate `timeout` ou ate chegar um NOTIFY (o que vier primeiro).

    Retorna True se acordou via NOTIFY, False se timeout (modo polling).
    Falha-aberta: qualquer excecao volta para `time.sleep` simples.
    """
    global _notify_received_total, _notify_wakeups_total
    if conn_listen is None:
        time.sleep(timeout)
        return False
    try:
        r, _, _ = select.select([conn_listen], [], [], timeout)
        if not r:
            return False
        conn_listen.poll()
        n = len(conn_listen.notifies)
        if n:
            _notify_received_total += n
            _notify_wakeups_total += 1
            conn_listen.notifies.clear()
            return True
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("listen_notify_wait_error error=%s; sleeping fallback", exc)
        time.sleep(timeout)
        return False


def main_loop(dsn: str) -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("cdc_worker_starting dsn_host=%s listen_notify=%s",
                _redact_dsn(dsn), USE_LISTEN_NOTIFY)
    conn = _connect(dsn)
    conn_listen = _setup_listen(dsn)
    idle_sleep = IDLE_SLEEP_INITIAL
    total = 0
    last_log_ts = 0.0

    while not _shutdown:
        # VF-5: liveness flag-file (compose healthcheck monitora mtime < 120s)
        try:
            with open("/tmp/cdc_alive", "w") as _f:
                _f.write(str(int(time.time())))
        except Exception:  # noqa: BLE001
            pass
        try:
            processed = process_one_batch(conn)
            total += processed
            if processed == 0:
                woke = _wait_for_notify(conn_listen, idle_sleep)
                if woke:
                    idle_sleep = IDLE_SLEEP_INITIAL  # reset porque chegou trabalho
                else:
                    idle_sleep = min(idle_sleep * 1.5, IDLE_SLEEP_MAX)
                # log resumo a cada 60s para nao poluir
                now = time.time()
                if now - last_log_ts >= 60.0:
                    logger.info(
                        "cdc_idle_stats notify_total=%s wakeups=%s idle_sleep=%.2fs",
                        _notify_received_total, _notify_wakeups_total, idle_sleep,
                    )
                    last_log_ts = now
            else:
                logger.info("batch_processed n=%s total=%s", processed, total)
                idle_sleep = IDLE_SLEEP_INITIAL
        except psycopg2.OperationalError as exc:
            logger.error("pg_connection_lost error=%s; reconnecting in 5s", exc)
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)
            conn = _connect(dsn)
        except Exception as exc:  # noqa: BLE001
            logger.exception("cdc_worker_unexpected_error error=%s; pausing 5s", exc)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)

    logger.info("cdc_worker_stopped total_processed=%s notify_total=%s",
                total, _notify_received_total)
    conn.close()
    if conn_listen is not None:
        try:
            conn_listen.close()
        except Exception:  # noqa: BLE001
            pass


def _redact_dsn(dsn: str) -> str:
    """Esconde senha em logs."""
    try:
        parsed = psycopg2.extensions.parse_dsn(dsn)
        parsed.pop("password", None)
        return " ".join(f"{k}={v}" for k, v in parsed.items())
    except Exception:  # noqa: BLE001
        return "<unparseable>"


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("CDC_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    dsn = os.environ.get("ROLETA_PG_DSN")
    if not dsn:
        print("ERROR: ROLETA_PG_DSN env var is required", file=sys.stderr)
        sys.exit(1)
    main_loop(dsn)

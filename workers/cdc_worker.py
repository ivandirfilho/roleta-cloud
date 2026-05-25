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

try:
    from prometheus_client import Counter, Gauge, start_http_server  # type: ignore
    _PROM_OK = True
except Exception:  # noqa: BLE001
    _PROM_OK = False

logger = logging.getLogger("cdc_worker")

MAX_RETRIES = int(os.environ.get("CDC_MAX_RETRIES", "5"))
BATCH_SIZE = int(os.environ.get("CDC_BATCH_SIZE", "100"))
IDLE_SLEEP_INITIAL = float(os.environ.get("CDC_IDLE_SLEEP_INITIAL", "1.0"))
IDLE_SLEEP_MAX = float(os.environ.get("CDC_IDLE_SLEEP_MAX", "30.0"))
# S-I: LISTEN/NOTIFY aditivo (default ON; falha-aberta -> polling normal)
USE_LISTEN_NOTIFY = os.environ.get("CDC_USE_LISTEN_NOTIFY", "1") not in ("0", "false", "False", "")
NOTIFY_CHANNEL = os.environ.get("CDC_NOTIFY_CHANNEL", "outbox_new")
# S-OBS-2: porta para /metrics
METRICS_PORT = int(os.environ.get("CDC_METRICS_PORT", "8767"))
ALLOWED_DIRECTIONS = {"cw", "ccw"}
EXPECTED_DIM = 6

_shutdown = False
_notify_received_total = 0
_notify_wakeups_total = 0
_listen_conn_dead = False

# S-OBS-2: Prometheus metrics (silently no-op se prom_client ausente)
if _PROM_OK:
    M_NOTIFY_RECEIVED = Counter("cdc_notify_received_total", "Total NOTIFY events recebidos do PG")
    M_NOTIFY_WAKEUPS = Counter("cdc_notify_wakeups_total", "Total wakeups (batch read) acionados por NOTIFY")
    M_BATCH_PROCESSED = Counter("cdc_batch_events_processed_total", "Total eventos processados em batches")
    M_LISTEN_RECONNECT = Counter("cdc_listen_reconnect_total", "Total reconexoes do canal LISTEN")
    M_LISTEN_STATE = Gauge("cdc_listen_state", "1 = LISTEN ativo, 0 = polling-only")
else:
    M_NOTIFY_RECEIVED = M_NOTIFY_WAKEUPS = M_BATCH_PROCESSED = M_LISTEN_RECONNECT = None  # type: ignore
    M_LISTEN_STATE = None  # type: ignore


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


def _apply_spin_result(cur: Any, payload: dict[str, Any]) -> None:
    """S-STRAT-8: insere row em cw|ccw.spin_features com lag features.

    Calcula via window query no próprio schema (acc_10, acc_50, streaks,
    last_20_hits) antes de inserir esta nova linha.
    """
    direction = payload.get("direction")
    if direction not in ALLOWED_DIRECTIONS:
        raise ValueError(f"invalid direction: {direction!r}")
    decision_id = payload.get("decision_id")
    hit = payload.get("hit")
    if not isinstance(hit, bool):
        raise ValueError(f"hit must be bool, got {hit!r}")
    meta = payload.get("meta") or {}
    spin_number = payload.get("actual_number")
    if isinstance(meta, dict):
        spin_number = meta.get("spin_number", spin_number)
    centro_previsto = (meta or {}).get("centro_previsto") if isinstance(meta, dict) else None
    gale_level = (meta or {}).get("applied_gale_level") if isinstance(meta, dict) else None

    schema = "cw" if direction == "cw" else "ccw"

    # Window query: pega últimos 50 hits do mesmo schema para computar lags.
    cur.execute(
        f"""
        SELECT hit
        FROM {schema}.spin_features
        ORDER BY id DESC
        LIMIT 50;
        """
    )
    rows = cur.fetchall()
    # cur usa RealDictCursor → cada row é dict-like
    hits_desc = [bool(r["hit"]) for r in rows if r.get("hit") is not None]
    last_50 = hits_desc  # mais recentes primeiro
    last_10 = last_50[:10]
    last_20 = last_50[:20]

    def _acc(seq: list[bool]) -> float | None:
        return (sum(1 for x in seq if x) / len(seq)) if seq else None

    acc_10 = _acc(last_10)
    acc_50 = _acc(last_50)
    # Streak ANTES deste spin (sequência consecutiva mais recente).
    streak_miss = 0
    streak_hit = 0
    for prev in hits_desc:
        if prev:
            if streak_miss > 0:
                break
            streak_hit += 1
        else:
            if streak_hit > 0:
                break
            streak_miss += 1

    last_20_with_now = ([hit] + last_20)[:20]

    cur.execute(
        f"""
        INSERT INTO {schema}.spin_features
            (decision_id, spin_number, hit, centro_previsto, gale_level,
             recent_acc_10, recent_acc_50, streak_miss, streak_hit,
             last_20_hits, meta)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        (
            decision_id,
            spin_number,
            hit,
            centro_previsto,
            gale_level,
            acc_10,
            acc_50,
            streak_miss,
            streak_hit,
            last_20_with_now,
            Json(meta if isinstance(meta, dict) else {}),
        ),
    )


HANDLERS = {
    "spin_features": _apply_spin_features,
    "spin_result": _apply_spin_result,
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
    Se a conexao listen morreu (PG restart), sinaliza para o caller via
    setando `_listen_conn_dead` global -> reconnect na proxima iter.
    """
    global _notify_received_total, _notify_wakeups_total, _listen_conn_dead
    if conn_listen is None or _listen_conn_dead:
        time.sleep(timeout)
        return False
    if conn_listen.closed:
        logger.warning("listen_conn_closed; will reconnect")
        _listen_conn_dead = True
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
            if M_NOTIFY_RECEIVED is not None:
                M_NOTIFY_RECEIVED.inc(n)
                M_NOTIFY_WAKEUPS.inc()
            return True
        return False
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
        logger.warning("listen_conn_lost error=%s; marking for reconnect", exc)
        _listen_conn_dead = True
        time.sleep(timeout)
        return False
    except Exception:  # noqa: BLE001
        logger.exception("listen_notify_wait_unexpected; falling back to sleep")
        time.sleep(timeout)
        return False


def main_loop(dsn: str) -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    global _listen_conn_dead
    # S-OBS-2: expose /metrics
    if _PROM_OK:
        try:
            start_http_server(METRICS_PORT)
            logger.info("metrics_server_started port=%s", METRICS_PORT)
        except Exception:  # noqa: BLE001
            logger.exception("metrics_server_start_failed; continuing without /metrics")
    logger.info("cdc_worker_starting dsn_host=%s listen_notify=%s",
                _redact_dsn(dsn), USE_LISTEN_NOTIFY)
    conn = _connect(dsn)
    conn_listen = _setup_listen(dsn)
    if M_LISTEN_STATE is not None:
        M_LISTEN_STATE.set(1 if conn_listen is not None else 0)
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
            # S-OBS-FIX: reconectar LISTEN connection se PG caiu
            if _listen_conn_dead and USE_LISTEN_NOTIFY:
                logger.info("listen_reconnect_attempt")
                if M_LISTEN_RECONNECT is not None:
                    M_LISTEN_RECONNECT.inc()
                try:
                    if conn_listen is not None and not conn_listen.closed:
                        conn_listen.close()
                except Exception:  # noqa: BLE001
                    pass
                conn_listen = _setup_listen(dsn)
                if conn_listen is not None:
                    _listen_conn_dead = False
                if M_LISTEN_STATE is not None:
                    M_LISTEN_STATE.set(1 if conn_listen is not None else 0)
            if processed:
                if M_BATCH_PROCESSED is not None:
                    M_BATCH_PROCESSED.inc(processed)
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

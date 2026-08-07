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
import math
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
# H4 (03/08): ANALYZE periódico — a cada N batches não-vazios (0 = off).
# Mantém estatísticas do planner frescas em tabelas de INSERT contínuo,
# sem depender do autovacuum (thresholds altos p/ tabelas pequenas).
ANALYZE_EVERY_N = int(os.environ.get("CDC_ANALYZE_EVERY_N", "0"))
_ANALYZE_TABLES = (
    "cw.spins_vectors", "ccw.spins_vectors",
    "cw.spin_features", "ccw.spin_features",
    "shared.decision_dna", "shared.outbox",
)
ALLOWED_DIRECTIONS = {"cw", "ccw"}
EXPECTED_DIM = 6

# ---------------------------------------------------------------------------
# PG feature-context (correção 06/08)
# ---------------------------------------------------------------------------
# Auditoria de produção: cw/ccw.spin_features com dealer='unknown' 100% e
# spin_seq/direction_*/centro_previsto/gale_level NULL 100%, embora as colunas
# existam (0007/0009/0010/0012). O produtor não emitia o contexto e este worker
# não o projetava. Flag default-OFF, lida A CADA EVENTO (env é fixa por
# container: ligar/desligar exige `up -d --force-recreate`).
#
# ORDEM DE ROLLOUT: worker (código + flag) PRIMEIRO, produtor DEPOIS. Com o
# produtor ligado antes do worker, os eventos enriquecidos são consumidos como
# legado e marcados 'processed'; o ON CONFLICT DO NOTHING impede reparo por
# replay e a única correção passa a ser o backfill. O log
# `spin_result_context_ignored` abaixo denuncia essa inversão.
CONTEXT_FLAG_ENV = "SDA_PG_FEATURE_CONTEXT"

# Mapa EXPLÍCITO chave do contexto -> identificador SQL da coluna de destino.
# `dealer_table` -> "table": a coluna PG (0007) usa a palavra reservada `table`
# e por isso vai CITADA. Este mapa é o contrato testado (tests/test_cdc_worker_context.py).
#
# SEMÂNTICA DO `dealer`: com a flag ON, ausência de dealer grava NULL em vez do
# DEFAULT 'unknown' do DDL (0007). É deliberado — NULL diz "não observado",
# 'unknown' era um literal que se confundia com um dealer chamado assim. Nenhuma
# consulta de produção filtra por 'unknown'; o backfill aceita os dois estados
# como vazio (`dealer IS NULL OR dealer='unknown'`).
CONTEXT_COLUMN_MAP: tuple[tuple[str, str], ...] = (
    ("dealer", "dealer"),
    ("dealer_table", '"table"'),
    ("provider", "provider"),
    ("round_id", "round_id"),
    ("wheel_model", "wheel_model"),
    ("vision_confidence", "vision_confidence"),
    ("vision_source", "vision_source"),
    ("spin_seq", "spin_seq"),
    ("direction_source", "direction_source"),
    ("direction_confidence", "direction_confidence"),
    ("direction_next", "direction_next"),
    ("phase_uncertain", "phase_uncertain"),
)
# Coerção por coluna — TOTAL (nunca levanta): valor inválido vira NULL e é
# contado, jamais manda o resultado essencial para a DLQ. Defeito de mapeamento
# ou de SQL continua falhando alto (não há try/except cego em volta do INSERT).
CONTEXT_COLUMN_KINDS: dict[str, str] = {
    "dealer": "text",
    "dealer_table": "text",
    "provider": "text",
    "round_id": "text",
    "wheel_model": "text",
    "vision_confidence": "float",
    "vision_source": "text",
    "spin_seq": "int4",
    "direction_source": "text",
    "direction_confidence": "float",
    "direction_next": "text",
    "phase_uncertain": "bool",
}

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
    M_CONTEXT = Counter(
        "cdc_spin_result_context_total",
        "Projecao do contexto da decisao em spin_features por desfecho",
        ["status"],
    )
    M_CONTEXT_SESSION_MISMATCH = Counter(
        "cdc_spin_result_context_session_mismatch_total",
        "Contexto com session_id diferente do evento (projetado mesmo assim)",
    )
else:
    M_NOTIFY_RECEIVED = M_NOTIFY_WAKEUPS = M_BATCH_PROCESSED = M_LISTEN_RECONNECT = None  # type: ignore
    M_LISTEN_STATE = None  # type: ignore
    M_CONTEXT = M_CONTEXT_SESSION_MISMATCH = None  # type: ignore


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
    # H2 (03/08): ON CONFLICT no unique parcial (0011) — replay/retry vira no-op.
    if direction == "cw":
        sql = (
            "INSERT INTO cw.spins_vectors (decision_id, raw_features, meta) VALUES (%s, %s::vector, %s) "
            "ON CONFLICT (decision_id) WHERE decision_id IS NOT NULL DO NOTHING"
        )
    else:
        sql = (
            "INSERT INTO ccw.spins_vectors (decision_id, raw_features, meta) VALUES (%s, %s::vector, %s) "
            "ON CONFLICT (decision_id) WHERE decision_id IS NOT NULL DO NOTHING"
        )

    cur.execute(sql, (decision_id, raw, Json(meta)))


def context_enabled() -> bool:
    """Flag default-OFF lida A CADA EVENTO (nunca cacheada)."""
    return os.environ.get(CONTEXT_FLAG_ENV, "0").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _m_context(status: str) -> None:
    if M_CONTEXT is not None:
        M_CONTEXT.labels(status=status).inc()


# Limites numéricos do PG, medidos contra PostgreSQL 15 real (pgvector/pg15).
# INTEGER (int4) e REAL (float4): valor fora daqui faz o PRÓPRIO banco recusar o
# INSERT — o mesmo desfecho (linha essencial perdida) que a coerção total existe
# para evitar. REAL recusa 3.5e38 (overflow) e 1e-46 (underflow); 3.4028235e38 e
# 1.4e-45 passam.
_INT4_MIN, _INT4_MAX = -2147483648, 2147483647
_PG_FLOAT4_MAX = 3.4028235e38
_PG_FLOAT4_MIN = 1.4e-45


def _coerce_text(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, ArithmeticError):
        # ArithmeticError cobre OverflowError (int gigante vindo do JSONB).
        # A coerção é TOTAL por contrato: nada aqui pode escapar e mandar o
        # resultado essencial para a DLQ.
        return None
    # Verificado contra PG 15 real: a coluna REAL aceita ±Inf/NaN mas RECUSA
    # 1e300 (overflow) e 1e-300 (underflow) — justamente os valores que o JSONB
    # deixa passar. Esta guarda NÃO é redundante com a do produtor: eventos
    # legados ou escritos à mão chegam aqui sem nunca terem passado por lá.
    if not math.isfinite(number):
        return None
    magnitude = abs(number)
    if magnitude != 0.0 and not (_PG_FLOAT4_MIN <= magnitude <= _PG_FLOAT4_MAX):
        return None
    return number


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, ArithmeticError):
        return None


def _coerce_int4(value: Any) -> Optional[int]:
    number = _coerce_int(value)
    if number is None or not (_INT4_MIN <= number <= _INT4_MAX):
        return None
    return number


def _coerce_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "t", "yes", "on"):
        return True
    if text in ("0", "false", "f", "no", "off"):
        return False
    return None


_COERCERS = {"text": _coerce_text, "float": _coerce_float,
             "int": _coerce_int, "int4": _coerce_int4, "bool": _coerce_bool}


def build_context_columns(
    payload: dict[str, Any], session_id: Any,
) -> tuple[list[str], list[Any], Optional[dict[str, Any]]]:
    """Resolve as colunas de contexto a projetar. Devolve (colunas, valores, ctx).

    Nunca levanta: cada valor passa por coerção TOTAL (lixo vira NULL) para que
    um contexto malformado jamais mande o resultado essencial para a DLQ.
    `ctx` volta None quando nada deve ser projetado (flag OFF, ausente ou
    identidade divergente) — nesse caso o INSERT é exatamente o legado.

    Identidade: `decision_id` divergente REJEITA o contexto (dado da decisão
    errada). `session_id` divergente NÃO rejeita — um reset de sessão no meio da
    resolução não invalida o dealer/mesa observados na decisão —, só é contado.
    """
    context = payload.get("context")
    if not context_enabled():
        if context is not None:
            # Denuncia rollout fora de ordem (produtor ligado antes do worker):
            # estas linhas nascem sem contexto e o ON CONFLICT DO NOTHING impede
            # reparo por replay — só o backfill conserta.
            logger.warning(
                "spin_result_context_ignored decision_id=%s reason=worker_flag_off",
                payload.get("decision_id"),
            )
        _m_context("disabled")
        return [], [], None
    if context is None:
        _m_context("absent")
        return [], [], None
    if not isinstance(context, dict):
        logger.warning("spin_result_context_invalid decision_id=%s type=%s",
                       payload.get("decision_id"), type(context).__name__)
        _m_context("invalid")
        return [], [], None
    ctx_decision_id = _coerce_int(context.get("decision_id"))
    evt_decision_id = _coerce_int(payload.get("decision_id"))
    if (ctx_decision_id is not None and evt_decision_id is not None
            and ctx_decision_id != evt_decision_id):
        logger.warning(
            "spin_result_context_invalid decision_id=%s ctx_decision_id=%s "
            "reason=decision_id_mismatch", evt_decision_id, ctx_decision_id,
        )
        _m_context("invalid")
        return [], [], None
    ctx_session = _coerce_text(context.get("session_id"))
    evt_session = _coerce_text(session_id)
    if ctx_session is not None and evt_session is not None and ctx_session != evt_session:
        # session_id do evento continua autoritativo para a coluna session_id.
        logger.warning(
            "spin_result_context_session_mismatch decision_id=%s ctx=%s evt=%s",
            evt_decision_id, ctx_session, evt_session,
        )
        if M_CONTEXT_SESSION_MISMATCH is not None:
            M_CONTEXT_SESSION_MISMATCH.inc()
    cols: list[str] = []
    vals: list[Any] = []
    for key, column in CONTEXT_COLUMN_MAP:
        coerce = _COERCERS[CONTEXT_COLUMN_KINDS[key]]
        cols.append(column)
        vals.append(coerce(context.get(key)))
    _m_context("applied")
    return cols, vals, context


def _apply_spin_result(cur: Any, payload: dict[str, Any]) -> None:
    """S-STRAT-8: insere row em cw|ccw.spin_features com lag features.

    Calcula via window query no próprio schema (acc_10, acc_50, streaks,
    last_20_hits) antes de inserir esta nova linha.

    Correção 06/08: sob `SDA_PG_FEATURE_CONTEXT=1` projeta também o contexto da
    decisão (dealer/mesa/provider/visão/fase) que vem DENTRO do evento. Nada é
    buscado em outra tabela de propósito: o batch roda com FOR UPDATE SKIP
    LOCKED em múltiplas instâncias e com rollback por savepoint — uma leitura
    aqui seria corrida. `spin_number` NÃO faz parte do mapa de contexto: ele é,
    e continua sendo, o número REAL que resolveu a decisão anterior.
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
    # H3 (03/08): sessão isola a janela de lag features — sem vazamento
    # estatístico entre sessões (dealer/mesa/regime mudam no corte).
    session_id = payload.get("session_id")
    if not session_id and isinstance(meta, dict):
        session_id = meta.get("session_id")

    # Window query: últimos 50 hits do mesmo schema (e da mesma sessão,
    # quando o payload a informa — payloads antigos seguem no modo global).
    if session_id:
        cur.execute(
            f"""
            SELECT hit
            FROM {schema}.spin_features
            WHERE session_id = %s
            ORDER BY id DESC
            LIMIT 50;
            """,
            (session_id,),
        )
    else:
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

    # H2+H3 (03/08): session_id na linha + ON CONFLICT anti-replay.
    # Correção 06/08: colunas de contexto entram por allowlist (CONTEXT_COLUMN_MAP)
    # DEPOIS das colunas base — `spin_number` não está no mapa, logo o contexto
    # nunca sobrescreve o número real do resultado.
    ctx_cols, ctx_vals, context = build_context_columns(payload, session_id)
    if context is not None:
        # Precedência: meta (legado) vence; o contexto só PREENCHE o que faltou.
        # Para eventos `spin_result` o meta é sempre {}, então na prática o
        # contexto preenche — a precedência é o guarda de compatibilidade que
        # impede um evento legado enriquecido manualmente de ser reescrito.
        if centro_previsto is None:
            centro_previsto = _coerce_int4(context.get("centro_previsto"))
        if gale_level is None:
            gale_level = _coerce_int4(context.get("applied_gale_level"))

    base_cols = [
        "decision_id", "spin_number", "hit", "centro_previsto", "gale_level",
        "recent_acc_10", "recent_acc_50", "streak_miss", "streak_hit",
        "last_20_hits", "meta", "session_id",
    ]
    base_vals = [
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
        session_id,
    ]
    all_cols = base_cols + ctx_cols
    all_vals = base_vals + ctx_vals
    placeholders = ", ".join(["%s"] * len(all_cols))
    cur.execute(
        f"""
        INSERT INTO {schema}.spin_features
            ({", ".join(all_cols)})
        VALUES ({placeholders})
        ON CONFLICT (decision_id) WHERE decision_id IS NOT NULL DO NOTHING;
        """,
        tuple(all_vals),
    )


def _apply_dna_feature(cur: Any, payload: dict[str, Any]) -> None:
    """P3.1 (12/06): insere feature DNA em shared.decision_dna.

    Idempotência: o outbox já deduplica por event_uuid; aqui usamos um
    anti-duplo defensivo (decision_id+feature_name+feature_value já igual
    não re-insere) para tolerar replays manuais.
    """
    decision_id = payload.get("decision_id")
    feature_name = payload.get("feature_name")
    if not isinstance(decision_id, int) or not feature_name:
        raise ValueError(f"dna_feature invalido: id={decision_id!r} name={feature_name!r}")
    feature_value = payload.get("feature_value") or {}
    cur.execute(
        """
        INSERT INTO shared.decision_dna
            (decision_id, spin_number, direction, feature_name, feature_value,
             final_action, hit, wheel_dist)
        SELECT %s, %s, %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM shared.decision_dna
            WHERE decision_id = %s AND feature_name = %s
        );
        """,
        (
            decision_id,
            payload.get("spin_number"),
            payload.get("direction"),
            feature_name,
            Json(feature_value),
            payload.get("final_action"),
            payload.get("hit"),
            payload.get("wheel_dist"),
            decision_id,
            feature_name,
        ),
    )


def _apply_dna_realized(cur: Any, payload: dict[str, Any]) -> None:
    """P3.1 (12/06): realize (hit/wheel_dist/lift) nas features da decisão."""
    decision_id = payload.get("decision_id")
    if not isinstance(decision_id, int):
        raise ValueError(f"dna_realized invalido: id={decision_id!r}")
    sets, args = [], []
    if payload.get("hit") is not None:
        sets.append("hit = %s")
        args.append(bool(payload["hit"]))
    if payload.get("wheel_dist") is not None:
        sets.append("wheel_dist = %s")
        args.append(int(payload["wheel_dist"]))
    if payload.get("realized_lift_pp") is not None:
        sets.append("realized_lift_pp = %s")
        args.append(float(payload["realized_lift_pp"]))
    if not sets:
        return
    args.append(decision_id)
    cur.execute(
        f"UPDATE shared.decision_dna SET {', '.join(sets)} WHERE decision_id = %s;",
        args,
    )


def _apply_dna_lift_bucket(cur: Any, payload: dict[str, Any]) -> None:
    """H1 (03/08): espelha lift realizado por (direction, feature, bucket).

    1 evento por bucket (não por linha) — o UPDATE em massa replica no PG a
    mesma semântica idempotente do SQLite (dna_realize_lifts): só preenche
    onde realized_lift_pp IS NULL e hit IS NOT NULL.
    direction usa IS NOT DISTINCT FROM para casar rows legadas (NULL=NULL).
    """
    feature_name = payload.get("feature_name")
    bucket = payload.get("bucket")
    lift_pp = payload.get("realized_lift_pp")
    if not feature_name or bucket is None or lift_pp is None:
        raise ValueError(
            f"dna_lift_bucket invalido: feature={feature_name!r} "
            f"bucket={bucket!r} lift={lift_pp!r}"
        )
    cur.execute(
        """
        UPDATE shared.decision_dna
        SET realized_lift_pp = %s
        WHERE feature_name = %s
          AND feature_value->>'bucket' = %s
          AND direction IS NOT DISTINCT FROM %s
          AND hit IS NOT NULL
          AND realized_lift_pp IS NULL;
        """,
        (
            float(lift_pp),
            feature_name,
            str(bucket),
            payload.get("direction"),
        ),
    )


HANDLERS = {
    "spin_features": _apply_spin_features,
    "spin_result": _apply_spin_result,
    "dna_feature": _apply_dna_feature,
    "dna_realized": _apply_dna_realized,
    "dna_lift_bucket": _apply_dna_lift_bucket,
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


def _run_analyze(conn: psycopg2.extensions.connection) -> None:
    """H4 (03/08): ANALYZE nas tabelas quentes. Best-effort, commit próprio."""
    try:
        with _cursor(conn) as cur:
            for table in _ANALYZE_TABLES:
                cur.execute(f"ANALYZE {table};")
        conn.commit()
        logger.info("analyze_done tables=%s", len(_ANALYZE_TABLES))
    except Exception:  # noqa: BLE001
        logger.exception("analyze_failed; continuing")
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass


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
    batches_since_analyze = 0

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
                # H4 (03/08): ANALYZE a cada N batches não-vazios (flag env,
                # leitura no boot; 0 = desligado).
                if ANALYZE_EVERY_N > 0:
                    batches_since_analyze += 1
                    if batches_since_analyze >= ANALYZE_EVERY_N:
                        _run_analyze(conn)
                        batches_since_analyze = 0
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

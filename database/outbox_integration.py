"""Hook S5 — dual-write SQLite + shared.outbox.

Cuidados:
- PG offline NUNCA quebra o app (try/except + warning).
- Feature flag `dual_write_pg` no PG controla on/off; cache 30s para nao
  consultar a cada save_decision.
- Publisher e singleton lazy (cria conexao na 1a chamada habilitada).
- Mapping de direction: 'horario'/'anti-horario' (legacy) -> 'cw'/'ccw'.
- Extracao de raw_features estavel: indices [0..5] documentados.

Uso (em SQLiteDecisionRepository.save_decision):
    from database.outbox_integration import maybe_publish_decision_features
    maybe_publish_decision_features(decision, decision_id)
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from database.models import Decision
    from database.outbox_publisher import OutboxPublisher

logger = logging.getLogger(__name__)

# Mapping direction legacy -> schema PG.
_DIRECTION_MAP = {
    "horario": "cw",
    "horário": "cw",
    "cw": "cw",
    "CW": "cw",
    "anti-horario": "ccw",
    "anti-horário": "ccw",
    "antihorario": "ccw",
    "ccw": "ccw",
    "CCW": "ccw",
}

# Cache de flag.
_FLAG_CACHE_TTL_SEC = 30.0
_flag_lock = threading.Lock()
_flag_cache: dict[str, tuple[bool, float]] = {}

# Publisher singleton com retry exponencial (VF-2 fix HOOK-1).
_pub_lock = threading.Lock()
_publisher: Optional["OutboxPublisher"] = None
_publisher_init_attempts = 0
_publisher_last_attempt_ts = 0.0
_MAX_INIT_ATTEMPTS = 20
_RETRY_BACKOFF_SEC = 30.0

# Métricas Prometheus (VF-3) — opcionais; se prometheus_client não disponível, no-op.
try:
    from prometheus_client import Counter, Gauge  # type: ignore
    _m_hook_called = Counter(
        "outbox_hook_called_total",
        "Total chamadas a maybe_publish_decision_features",
    )
    _m_hook_published = Counter(
        "outbox_hook_published_total",
        "Total publicações OK no shared.outbox via hook",
    )
    _m_hook_skipped = Counter(
        "outbox_hook_skipped_total",
        "Total skips (flag off, publisher None, direction unknown)",
        ["reason"],
    )
    _m_hook_init_attempts = Counter(
        "outbox_hook_init_attempts_total",
        "Tentativas de init do OutboxPublisher",
    )
    _m_publisher_ready = Gauge(
        "outbox_publisher_ready",
        "1 se OutboxPublisher inicializado; 0 caso contrário",
    )
    save_decision_failed_total = Counter(
        "save_decision_failed_total",
        "Falhas em save_decision (BUG-FK-1 tracking)",
        ["reason"],
    )
    _METRICS = True
except Exception:  # noqa: BLE001
    _METRICS = False

    class _NoOp:
        def labels(self, *_a, **_kw): return self
        def inc(self, *_a, **_kw): pass
        def set(self, *_a, **_kw): pass
    _m_hook_called = _m_hook_published = _m_hook_skipped = _m_hook_init_attempts = _m_publisher_ready = _NoOp()
    save_decision_failed_total = _NoOp()


def _normalize_direction(raw: str) -> str | None:
    if not raw:
        return None
    return _DIRECTION_MAP.get(raw) or _DIRECTION_MAP.get(raw.strip().lower())


def _extract_raw_features(decision: "Decision") -> list[float]:
    """Extrai 6 features numericas da Decision.

    Ordem ESTAVEL (nao mudar; consumidores S7/S11 dependem):
      [0] spin_force            (int, magnitude do empurrao)
      [1] tr_c4_rate            (taxa de hit ultimas 4)
      [2] tr_m6_rate            (taxa de hit medias 6)
      [3] tr_l12_rate           (taxa longa 12)
      [4] sda_score             (score do SDA)
      [5] sda_predicted_force   (forca prevista para proxima)
    """
    return [
        float(decision.spin_force or 0),
        float(decision.tr_c4_rate or 0.0),
        float(decision.tr_m6_rate or 0.0),
        float(decision.tr_l12_rate or 0.0),
        float(decision.sda_score or 0),
        float(decision.sda_predicted_force or 0),
    ]


# ---------------------------------------------------------------------------
# PG feature-context (correção 06/08): projeção do contexto da decisão
# ---------------------------------------------------------------------------
# Auditoria de produção: `cw/ccw.spin_features` tinha `dealer='unknown'` em 100%
# das linhas e `spin_seq`/`direction_*`/`centro_previsto`/`gale_level` NULL em
# 100% — embora as colunas de destino existam desde 0007/0009/0010/0012. A causa
# NÃO era lag de CDC (outbox 100% processado): o produtor nunca emitia esses
# campos no evento `spin_result` e o worker nunca os projetava.
#
# INVIOLÁVEL: comportamento novo nasce atrás de flag default-OFF no compose,
# lida por chamada (`os.environ`, sem cache) — a env é fixa por container, então
# ligar/desligar exige `up -d --force-recreate`.
_CONTEXT_FLAG_ENV = "SDA_PG_FEATURE_CONTEXT"

# Chaves do contexto → colunas de destino em cw|ccw.spin_features.
# `dealer_table` mapeia para a coluna PG **"table"** (palavra reservada, citada
# no worker). Mantido aqui como fonte única da verdade do contrato produtor.
PG_FEATURE_CONTEXT_KEYS: tuple[str, ...] = (
    "dealer",
    "dealer_table",
    "provider",
    "round_id",
    "wheel_model",
    "vision_confidence",
    "vision_source",
    "spin_seq",
    "direction_source",
    "direction_confidence",
    "direction_next",
    "phase_uncertain",
    "centro_previsto",
    "applied_gale_level",
)


def pg_feature_context_enabled() -> bool:
    """Flag default-OFF do enriquecimento de contexto (lida por chamada)."""
    return os.environ.get(_CONTEXT_FLAG_ENV, "0").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _src_get(source: Any, key: str) -> Any:
    """Lê `key` de um `Decision` (atributo), de um mapping ou de um `sqlite3.Row`.

    O mesmo helper serve o caminho ao vivo (objeto `Decision`) e o backfill
    (linha crua do SQLite) — é o que garante que os dois produzam o MESMO valor
    para a mesma origem.
    """
    if isinstance(source, Mapping):
        return source.get(key)
    try:
        keys = getattr(source, "keys", None)
        if callable(keys):  # sqlite3.Row e afins: acesso por item
            return source[key] if key in keys() else None
    except Exception:  # noqa: BLE001 — fonte heterogênea nunca derruba o hook
        return None
    try:
        return getattr(source, key)
    except Exception:  # noqa: BLE001
        return None


def _text_or_none(value: Any) -> str | None:
    """String não-vazia, ou None. `''`/whitespace são ausência, não valor."""
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:  # noqa: BLE001
        return None
    return text or None


# Limites de float verificados contra PostgreSQL 15 real (pgvector/pg15 +
# psycopg2), porque as DUAS pontas do caminho recusam coisas DIFERENTES:
#
#   valor        | payload JSONB (shared.outbox) | coluna REAL (spin_features)
#   -------------|-------------------------------|----------------------------
#   NaN / ±Inf   | ERRO (JSON não tem esses)     | aceita
#   1e300        | aceita                        | ERRO (overflow)
#   1e-300       | aceita                        | ERRO (underflow)
#   0.0 / 0.87   | aceita                        | aceita
#
# Um NaN/Inf no contexto derruba o INSERT do evento INTEIRO no outbox — ou seja,
# um campo OPCIONAL faz o `spin_result` ESSENCIAL se perder antes de existir.
# Um finito gigante passa pelo JSONB e só explode no worker, mandando a linha
# essencial para a DLQ. Por isso a checagem é a UNIÃO das duas restrições e vive
# nas duas pontas (o worker também protege eventos legados/escritos à mão).
_PG_FLOAT4_MAX = 3.4028235e38   # maior magnitude aceita por REAL (3.5e38 falha)
_PG_FLOAT4_MIN = 1.4e-45        # menor magnitude não-nula aceita (1e-46 falha)


def _is_pg_float_safe(number: float) -> bool:
    """True se o float sobrevive a JSONB **e** a uma coluna REAL do PG.

    Sem clamp: valor fora da faixa é ausência, não um número aproximado. Zero é
    sempre válido; magnitudes normais (confiança em 0..1) passam sem toque.
    """
    if not math.isfinite(number):
        return False
    magnitude = abs(number)
    return magnitude == 0.0 or _PG_FLOAT4_MIN <= magnitude <= _PG_FLOAT4_MAX


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, ArithmeticError):
        # ArithmeticError cobre OverflowError (int gigante -> float): a coerção
        # é TOTAL por contrato, então valor impossível vira ausência.
        return None
    return number if _is_pg_float_safe(number) else None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, ArithmeticError):
        # OverflowError: int(float('inf')).
        return None


# Faixa de INTEGER (int4) do PG. Valor fora daqui derrubaria o INSERT no banco
# (e com ele o resultado essencial); melhor virar ausência já na normalização.
_INT4_MIN, _INT4_MAX = -2147483648, 2147483647


def _int4_or_none(value: Any) -> int | None:
    number = _int_or_none(value)
    if number is None or not (_INT4_MIN <= number <= _INT4_MAX):
        return None
    return number


def build_pg_feature_context(source: Any) -> dict | None:
    """Monta o contexto IMUTÁVEL da decisão para projeção no PG. Nunca levanta.

    Helper PURO, compartilhado pela publicação do vetor inicial (`spin_features`)
    e pelo evento de resultado (`spin_result`) — e reutilizado pelo backfill, de
    modo que o valor gravado ao vivo e o valor reconstruído a posteriori saiam da
    MESMA normalização.

    `source` pode ser um `Decision` ou qualquer mapping com as mesmas chaves.

    Normalização (uma única vez, aqui):
      - string vazia → None (ausência não é valor);
      - `dealer='unknown'` → None (é o DEFAULT da coluna, não uma observação);
      - `vision_confidence` só existe se `vision_source` existir (par);
      - `direction_confidence`/`phase_uncertain` idem em relação a
        `direction_source` — sem a origem da fase, "não incerto" seria mentira;
      - `spin_seq <= 0` → None (0 é o default do dataclass, não um giro);
      - `direction_next` → alias conhecido (`cw|ccw`); não mapeável → None
        (evita vocabulário misto 'horario'/'cw' na mesma coluna);
      - `centro_previsto` preserva 0 (a casa 0 existe na roleta) e
        `phase_uncertain` preserva `False` quando a fase É conhecida.

    Devolve `None` quando não há fonte (nada a projetar).
    """
    if source is None:
        return None
    vision_source = _text_or_none(_src_get(source, "vision_source"))
    direction_source = _text_or_none(_src_get(source, "direction_source"))
    dealer = _text_or_none(_src_get(source, "dealer"))
    if dealer is not None and dealer.lower() == "unknown":
        dealer = None
    spin_seq = _int4_or_none(_src_get(source, "spin_seq"))
    if spin_seq is not None and spin_seq <= 0:
        spin_seq = None
    raw_phase_uncertain = _src_get(source, "phase_uncertain")
    phase_uncertain = (
        bool(raw_phase_uncertain)
        if (direction_source is not None and raw_phase_uncertain is not None)
        else None
    )
    return {
        # Identidade: o worker rejeita contexto cujo decision_id não bate com o
        # do evento (troca de contexto = dado errado na linha errada).
        "decision_id": _int_or_none(_src_get(source, "id")),
        # Divergência de sessão é REPORTADA, não rejeitada: um reset de sessão no
        # meio da resolução não invalida o dealer/mesa observados na decisão.
        "session_id": _text_or_none(_src_get(source, "session_id")),
        "dealer": dealer,
        "dealer_table": _text_or_none(_src_get(source, "dealer_table")),
        "provider": _text_or_none(_src_get(source, "provider")),
        "round_id": _text_or_none(_src_get(source, "round_id")),
        "wheel_model": _text_or_none(_src_get(source, "wheel_model")),
        "vision_confidence": (
            _float_or_none(_src_get(source, "vision_confidence"))
            if vision_source is not None else None
        ),
        "vision_source": vision_source,
        "spin_seq": spin_seq,
        "direction_source": direction_source,
        "direction_confidence": (
            _float_or_none(_src_get(source, "direction_confidence"))
            if direction_source is not None else None
        ),
        "direction_next": _normalize_direction(
            _text_or_none(_src_get(source, "direction_next")) or ""
        ),
        "phase_uncertain": phase_uncertain,
        "centro_previsto": _int4_or_none(_src_get(source, "sda_center")),
        "applied_gale_level": _int4_or_none(_src_get(source, "gale_level")),
    }


def _get_publisher() -> Optional["OutboxPublisher"]:
    """Lazy singleton com retry exponencial (VF-2 fix HOOK-1).

    Antes: single-shot — 1 falha = perma-disabled.
    Agora: até _MAX_INIT_ATTEMPTS tentativas com backoff de _RETRY_BACKOFF_SEC.
    """
    global _publisher, _publisher_init_attempts, _publisher_last_attempt_ts
    if _publisher is not None:
        return _publisher
    with _pub_lock:
        if _publisher is not None:
            return _publisher
        if _publisher_init_attempts >= _MAX_INIT_ATTEMPTS:
            return None
        now = time.monotonic()
        if _publisher_init_attempts > 0 and (now - _publisher_last_attempt_ts) < _RETRY_BACKOFF_SEC:
            return None
        _publisher_last_attempt_ts = now
        _publisher_init_attempts += 1
        _m_hook_init_attempts.inc()
        dsn = os.environ.get("ROLETA_PG_DSN")
        if not dsn:
            logger.warning("dual_write_pg disabled: ROLETA_PG_DSN nao setado (attempt %d)", _publisher_init_attempts)
            return None
        try:
            from database.outbox_publisher import OutboxPublisher
            p = OutboxPublisher(dsn)
            _ = p._ensure_conn()  # força conexão imediata
            _publisher = p
            _m_publisher_ready.set(1)
            logger.warning("OutboxPublisher inicializado com sucesso (attempt %d)", _publisher_init_attempts)
            return _publisher
        except Exception as exc:  # noqa: BLE001
            logger.warning("OutboxPublisher init attempt %d falhou: %s", _publisher_init_attempts, exc)
            return None


def _is_flag_enabled(flag_name: str = "dual_write_pg") -> bool:
    """Le shared.feature_flags com cache de 30s.

    Falha de leitura -> flag tratada como False (fail-safe).
    """
    now = time.monotonic()
    with _flag_lock:
        cached = _flag_cache.get(flag_name)
        if cached and now - cached[1] < _FLAG_CACHE_TTL_SEC:
            return cached[0]

    enabled = False
    pub = _get_publisher()
    if pub is None:
        with _flag_lock:
            _flag_cache[flag_name] = (False, now)
        return False
    try:
        conn = pub._ensure_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT enabled FROM shared.feature_flags WHERE name = %s;",
                (flag_name,),
            )
            row = cur.fetchone()
            enabled = bool(row[0]) if row else False
    except Exception as exc:  # noqa: BLE001
        logger.warning("flag_read_failed name=%s error=%s", flag_name, exc)
        enabled = False

    with _flag_lock:
        _flag_cache[flag_name] = (enabled, now)
    return enabled


def invalidate_flag_cache() -> None:
    """Util de teste: força nova leitura."""
    with _flag_lock:
        _flag_cache.clear()


def maybe_publish_decision_features(decision: "Decision", decision_id: int) -> bool:
    """Publica features no outbox SE flag dual_write_pg=true. NUNCA levanta.

    Returns:
        True se publicou; False caso contrario (flag off, PG offline, erro).
    """
    _m_hook_called.inc()
    try:
        if not _is_flag_enabled("dual_write_pg"):
            _m_hook_skipped.labels(reason="flag_off").inc()
            return False
        direction = _normalize_direction(decision.spin_direction)
        if direction is None:
            _m_hook_skipped.labels(reason="unknown_direction").inc()
            logger.debug("skip_publish unknown direction=%r", decision.spin_direction)
            return False
        pub = _get_publisher()
        if pub is None:
            _m_hook_skipped.labels(reason="publisher_none").inc()
            return False
        raw = _extract_raw_features(decision)
        meta = {
            "session_id": decision.session_id,
            "final_action": decision.final_action,
            "gale_level": decision.gale_level,
            # OBS-25-01: observabilidade outbox — number/centro previsto
            "spin_number": decision.spin_number,
            "centro_previsto": decision.sda_center,
            # GALE-25-04: clarificar semântica (gale_level é o "próximo",
            # applied_gale_level espelha o valor no momento da decisão)
            "applied_gale_level": decision.gale_level,
        }
        # Correção 06/08 (flag default-OFF): contexto ANINHADO em chave própria —
        # as chaves legadas do meta seguem intactas (sem colisão de nomes).
        if pg_feature_context_enabled():
            context = build_pg_feature_context(decision)
            if context is not None:
                meta["decision_context"] = context
        pub.publish_spin_features(
            direction=direction,
            raw_features=raw,
            decision_id=decision_id,
            meta=meta,
        )
        _m_hook_published.inc()
        logger.info("dual_write_ok decision_id=%s direction=%s", decision_id, direction)
        return True
    except Exception as exc:  # noqa: BLE001
        _m_hook_skipped.labels(reason="exception").inc()
        # H-1 fix (v4 §XIX): promovido warning→error com decision_id+direction
        # para que silent-skips fiquem visíveis em prod (caso de 3698 em 24/05).
        logger.error(
            "dual_write_failed decision_id=%s direction=%s exc=%s error=%s",
            decision_id, _normalize_direction(decision.spin_direction),
            type(exc).__name__, exc,
        )
        return False


def maybe_publish_spin_result(
    decision_id: int,
    direction: str,
    hit: bool,
    actual_number: int,
    session_id: str | None = None,
    dealer: str | None = None,
    table: str | None = None,
    provider: str | None = None,
    context: dict | None = None,
) -> bool:
    """OBS-25-01 — publica evento `spin_result` quando o resultado é conhecido.

    Chamado após `db_service.update_result` no message_handler. Permite
    engenharia reversa offline e backtest (S-STRAT-9) sem depender de logs.
    H3 (03/08): carrega session_id para o worker isolar a janela de lag
    features por sessão (payloads sem session_id seguem no modo global).
    R2 dealer-aware (05/08 noite-2): carrega dealer/table/provider (quando o
    fill-forward os conhece) para o CDC popular as colunas dealer do espelho
    PG e o placar shared.dealers — payloads antigos/sem dealer seguem valendo
    (o worker aplica default 'unknown').

    Correção 06/08 (flag `SDA_PG_FEATURE_CONTEXT`, default-OFF): `context`
    carrega o contexto da decisão (dealer/mesa/visão/fase) DENTRO do evento —
    o evento é SELF-CONTAINED de propósito. O worker consome com
    `FOR UPDATE SKIP LOCKED` em múltiplas instâncias e com rollback por
    savepoint: buscar o contexto lá (ex.: em `spins_vectors`) seria uma corrida.
    Com a flag OFF o payload é BYTE-IDÊNTICO ao legado (sem a chave `context`).

    NUNCA levanta — guard-rail consistente com maybe_publish_decision_features.
    """
    _m_hook_called.inc()
    try:
        if not _is_flag_enabled("dual_write_pg"):
            _m_hook_skipped.labels(reason="flag_off").inc()
            return False
        dir_norm = _normalize_direction(direction)
        if dir_norm is None:
            _m_hook_skipped.labels(reason="unknown_direction").inc()
            return False
        pub = _get_publisher()
        if pub is None:
            _m_hook_skipped.labels(reason="publisher_none").inc()
            return False
        payload = {
            "event_type": "spin_result",
            "direction": dir_norm,
            "decision_id": decision_id,
            "hit": bool(hit),
            "actual_number": int(actual_number),
        }
        if session_id:
            payload["session_id"] = str(session_id)
        if dealer and str(dealer).strip():
            payload["dealer"] = str(dealer).strip()
        if table and str(table).strip():
            payload["table"] = str(table).strip()
        if provider and str(provider).strip():
            payload["provider"] = str(provider).strip()
        if context is not None and pg_feature_context_enabled():
            payload["context"] = dict(context)
        pub.publish(
            aggregate="spin_result",
            aggregate_id=f"{dir_norm}:{decision_id}",
            payload=payload,
        )
        _m_hook_published.inc()
        logger.info("spin_result_ok decision_id=%s direction=%s hit=%s n=%s",
                    decision_id, dir_norm, hit, actual_number)
        return True
    except Exception as exc:  # noqa: BLE001
        _m_hook_skipped.labels(reason="exception").inc()
        logger.error("spin_result_failed decision_id=%s direction=%s exc=%s error=%s",
                     decision_id, direction, type(exc).__name__, exc)
        return False


def maybe_publish_dna_feature(
    decision_id: int,
    feature_name: str,
    feature_value: dict,
    *,
    spin_number: int | None = None,
    direction: str | None = None,
    final_action: str | None = None,
    hit: bool | None = None,
    wheel_dist: int | None = None,
) -> bool:
    """P3.1 (12/06) — espelha 1 feature DNA para shared.decision_dna via outbox.

    INCIDENT 12/06 21:16: publicação agora é ASSÍNCRONA (fila + worker
    daemon) — 4-8 features por decisão não podem custar round-trips PG no
    caminho crítico do spin (stall de 9.6s observado com conexão idle).
    Fila cheia → descarta (telemetria é best-effort; SQLite é a fonte).
    """
    return _dna_enqueue("feature", {
        "decision_id": decision_id,
        "feature_name": feature_name,
        "feature_value": feature_value,
        "spin_number": spin_number,
        "direction": direction,
        "final_action": final_action,
        "hit": hit,
        "wheel_dist": wheel_dist,
    })


def _publish_dna_feature_sync(item: dict) -> bool:
    _m_hook_called.inc()
    try:
        if not _is_flag_enabled("dual_write_pg"):
            _m_hook_skipped.labels(reason="flag_off").inc()
            return False
        pub = _get_publisher()
        if pub is None:
            _m_hook_skipped.labels(reason="publisher_none").inc()
            return False
        payload = {
            "event_type": "dna_feature",
            "decision_id": int(item["decision_id"]),
            "feature_name": str(item["feature_name"]),
            "feature_value": item["feature_value"],
            "spin_number": item.get("spin_number"),
            "direction": _normalize_direction(item.get("direction") or "") or item.get("direction"),
            "final_action": item.get("final_action"),
            "hit": item.get("hit"),
            "wheel_dist": item.get("wheel_dist"),
        }
        pub.publish(
            aggregate="dna",
            aggregate_id=f"{item['decision_id']}:{item['feature_name']}",
            payload=payload,
        )
        _m_hook_published.inc()
        return True
    except Exception as exc:  # noqa: BLE001
        _m_hook_skipped.labels(reason="exception").inc()
        logger.error("dna_feature_publish_failed decision_id=%s feature=%s exc=%s",
                     item.get("decision_id"), item.get("feature_name"), type(exc).__name__)
        return False


def maybe_publish_dna_realized(
    decision_id: int,
    *,
    hit: bool | None = None,
    wheel_dist: int | None = None,
    realized_lift_pp: float | None = None,
) -> bool:
    """P3.1 (12/06) — espelha o realize do DNA para o PG (assíncrono)."""
    return _dna_enqueue("realized", {
        "decision_id": decision_id,
        "hit": hit,
        "wheel_dist": wheel_dist,
        "realized_lift_pp": realized_lift_pp,
    })


def _publish_dna_realized_sync(item: dict) -> bool:
    _m_hook_called.inc()
    try:
        if not _is_flag_enabled("dual_write_pg"):
            _m_hook_skipped.labels(reason="flag_off").inc()
            return False
        pub = _get_publisher()
        if pub is None:
            _m_hook_skipped.labels(reason="publisher_none").inc()
            return False
        payload = {
            "event_type": "dna_realized",
            "decision_id": int(item["decision_id"]),
            "hit": item.get("hit"),
            "wheel_dist": item.get("wheel_dist"),
            "realized_lift_pp": item.get("realized_lift_pp"),
        }
        pub.publish(
            aggregate="dna",
            aggregate_id=f"{item['decision_id']}:realized",
            payload=payload,
        )
        _m_hook_published.inc()
        return True
    except Exception as exc:  # noqa: BLE001
        _m_hook_skipped.labels(reason="exception").inc()
        logger.error("dna_realized_publish_failed decision_id=%s exc=%s",
                     item.get("decision_id"), type(exc).__name__)
        return False


def _publish_dna_lift_bucket_sync(item: dict) -> bool:
    """H1 (03/08): espelha lift por bucket para o PG — 1 evento por bucket."""
    _m_hook_called.inc()
    try:
        if not _is_flag_enabled("dual_write_pg"):
            _m_hook_skipped.labels(reason="flag_off").inc()
            return False
        pub = _get_publisher()
        if pub is None:
            _m_hook_skipped.labels(reason="publisher_none").inc()
            return False
        payload = {
            "event_type": "dna_lift_bucket",
            "feature_name": str(item["feature_name"]),
            "bucket": str(item["bucket"]),
            # Fix auditoria 03/08: SQLite guarda "horario"/"anti-horario";
            # o PG guarda "cw"/"ccw" — sem normalizar, o UPDATE casa 0 rows.
            "direction": _normalize_direction(item.get("direction") or ""),
            "realized_lift_pp": float(item["realized_lift_pp"]),
            "n": item.get("n"),
        }
        pub.publish(
            aggregate="dna",
            aggregate_id=(
                f"lift:{item.get('direction') or 'all'}:"
                f"{item['feature_name']}:{item['bucket']}"
            ),
            payload=payload,
        )
        _m_hook_published.inc()
        return True
    except Exception as exc:  # noqa: BLE001
        _m_hook_skipped.labels(reason="exception").inc()
        logger.error("dna_lift_bucket_publish_failed feature=%s bucket=%s exc=%s",
                     item.get("feature_name"), item.get("bucket"), type(exc).__name__)
        return False


def maybe_publish_dna_lift_bucket(
    feature_name: str,
    bucket: str,
    *,
    direction: str | None = None,
    realized_lift_pp: float,
    n: int | None = None,
) -> bool:
    """H1 (03/08) — enfileira o lift realizado de um bucket para o PG."""
    return _dna_enqueue("lift_bucket", {
        "feature_name": feature_name,
        "bucket": bucket,
        "direction": direction,
        "realized_lift_pp": realized_lift_pp,
        "n": n,
    })


# ---- Fila assíncrona do DNA (INCIDENT 12/06: fora do caminho crítico) ----
import queue as _queue

_DNA_QUEUE: "_queue.Queue[tuple[str, dict]]" = _queue.Queue(maxsize=500)
_dna_worker_started = False
_dna_worker_lock = threading.Lock()


def _dna_worker() -> None:
    while True:
        kind, item = _DNA_QUEUE.get()
        try:
            if kind == "feature":
                _publish_dna_feature_sync(item)
            elif kind == "lift_bucket":
                _publish_dna_lift_bucket_sync(item)
            else:
                _publish_dna_realized_sync(item)
        except Exception:  # noqa: BLE001 — worker nunca morre
            pass
        finally:
            _DNA_QUEUE.task_done()


def _dna_enqueue(kind: str, item: dict) -> bool:
    global _dna_worker_started
    if not _dna_worker_started:
        with _dna_worker_lock:
            if not _dna_worker_started:
                threading.Thread(
                    target=_dna_worker, daemon=True, name="dna-outbox-worker"
                ).start()
                _dna_worker_started = True
    try:
        _DNA_QUEUE.put_nowait((kind, item))
        return True
    except _queue.Full:
        _m_hook_skipped.labels(reason="queue_full").inc()
        return False

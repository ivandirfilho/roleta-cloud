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
import os
import threading
import time
from typing import TYPE_CHECKING, Optional

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
    _METRICS = True
except Exception:  # noqa: BLE001
    _METRICS = False

    class _NoOp:
        def labels(self, *_a, **_kw): return self
        def inc(self, *_a, **_kw): pass
        def set(self, *_a, **_kw): pass
    _m_hook_called = _m_hook_published = _m_hook_skipped = _m_hook_init_attempts = _m_publisher_ready = _NoOp()


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
        pub.publish_spin_features(
            direction=direction,
            raw_features=raw,
            decision_id=decision_id,
            meta={
                "session_id": decision.session_id,
                "final_action": decision.final_action,
                "gale_level": decision.gale_level,
            },
        )
        _m_hook_published.inc()
        logger.info("dual_write_ok decision_id=%s direction=%s", decision_id, direction)
        return True
    except Exception as exc:  # noqa: BLE001
        _m_hook_skipped.labels(reason="exception").inc()
        logger.warning("dual_write_failed decision_id=%s error=%s", decision_id, exc)
        return False

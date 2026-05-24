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

# Publisher singleton.
_pub_lock = threading.Lock()
_publisher: Optional["OutboxPublisher"] = None
_publisher_init_attempted = False


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
    """Lazy singleton; retorna None se PG nao configurado / erro de init."""
    global _publisher, _publisher_init_attempted
    if _publisher is not None:
        return _publisher
    with _pub_lock:
        if _publisher is not None:
            return _publisher
        if _publisher_init_attempted:
            return None
        _publisher_init_attempted = True
        dsn = os.environ.get("ROLETA_PG_DSN")
        if not dsn:
            logger.info("dual_write_pg ignored: ROLETA_PG_DSN nao setado")
            return None
        try:
            from database.outbox_publisher import OutboxPublisher
            _publisher = OutboxPublisher(dsn)
            logger.info("OutboxPublisher inicializado")
        except Exception as exc:  # noqa: BLE001
            logger.warning("OutboxPublisher init falhou: %s", exc)
            return None
        return _publisher


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
    try:
        if not _is_flag_enabled("dual_write_pg"):
            return False
        direction = _normalize_direction(decision.spin_direction)
        if direction is None:
            logger.debug("skip_publish unknown direction=%r", decision.spin_direction)
            return False
        pub = _get_publisher()
        if pub is None:
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
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("dual_write_failed decision_id=%s error=%s", decision_id, exc)
        return False

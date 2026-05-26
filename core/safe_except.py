"""SP-05 (26/05): helper canonico para captura controlada de exceptions
silenciadas. Substitui ``except Exception: pass`` ad-hoc por blocos
instrumentados via Prometheus.

Motivo: B-10 (calibration_error kwarg engolido) ficou invisivel por 24h
em prod porque ``except Exception as db_error`` em
``server/message_handler.py:466`` capturou um TypeError de assinatura
desalinhada e o tratou como "DB error generico". Com este helper,
toda captura desse tipo passa a:
  1. incrementar ``roleta_silent_exception_total{module,category,exc_type}``
  2. escrever log estruturado com ``exc_type``
  3. opcionalmente reraise para TypeError/AttributeError em modo strict

Uso:
    with safe_except("db_save_decision", logger):
        db_service.update_result(...)

Ou via decorator em funcoes inteiras:
    @safe_except_fn("dna_emit")
    def emit_dna(...): ...
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator, Optional

try:
    from prometheus_client import Counter
    _CTR = Counter(
        "roleta_silent_exception_total",
        "Excecoes capturadas em blocos defensivos (SP-05).",
        ["module", "category", "exc_type"],
    )
except Exception:  # noqa: BLE001 — prometheus opcional em test envs
    _CTR = None


# Em modo strict (env STRICT_SILENT_EXCEPT=1) re-raise TypeError /
# AttributeError porque sao quase sempre bugs de assinatura (B-10).
_STRICT = os.getenv("STRICT_SILENT_EXCEPT", "0") == "1"
_RERAISE_TYPES = (TypeError, AttributeError)


@contextmanager
def safe_except(
    category: str,
    logger: Optional[logging.Logger] = None,
    *,
    reraise: bool = False,
    swallow_types: tuple = (Exception,),
) -> Iterator[None]:
    """Context manager para captura instrumentada de exception.

    Args:
        category: rotulo curto (ex: "db_save_decision", "outbox_publish").
        logger: logger a usar (cria default se None).
        reraise: se True sempre re-raise depois do log+counter.
        swallow_types: tuple de tipos a engolir (default Exception).
    """
    log = logger or logging.getLogger("safe_except")
    try:
        yield
    except swallow_types as exc:
        exc_type = type(exc).__name__
        module = log.name
        if _CTR is not None:
            try:
                _CTR.labels(module=module, category=category, exc_type=exc_type).inc()
            except Exception:  # noqa: BLE001
                pass
        log.error(
            "safe_except module=%s category=%s exc_type=%s msg=%s",
            module, category, exc_type, exc,
        )
        if reraise:
            raise
        if _STRICT and isinstance(exc, _RERAISE_TYPES):
            log.warning(
                "safe_except STRICT mode re-raising %s (provavel bug assinatura)",
                exc_type,
            )
            raise


def safe_except_fn(category: str, logger: Optional[logging.Logger] = None,
                    *, reraise: bool = False) -> Callable:
    """Decorator equivalente a ``safe_except`` para funcoes inteiras."""

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with safe_except(category, logger, reraise=reraise):
                return fn(*args, **kwargs)
            return None

        return wrapper

    return deco

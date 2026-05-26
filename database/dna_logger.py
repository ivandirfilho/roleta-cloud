"""SP-06 / DNA-01: helper para registrar entradas em decision_dna.

Uso tipico (SP-07 vai chamar isso de bet_advisor/sda17):

    from database.dna_logger import dna_log_feature

    dna_log_feature(
        decision_id=42, spin_number=33, direction="cw",
        feature_name="sda_score", feature_value={"raw": 4, "bucket": "sweet_spot"},
        estimated_lift_pp=+2.1, confidence_n=2300,
    )

Write-side dual: SQLite local (best-effort) + PG outbox (idempotente).
Erros nunca propagam — DNA eh observabilidade, nao critico.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DB_PATH: Optional[Path] = None
_ENABLED = True


def configure(db_path: str | Path, enabled: bool = True) -> None:
    global _DB_PATH, _ENABLED
    _DB_PATH = Path(db_path)
    _ENABLED = enabled
    if enabled:
        _ensure_table(_DB_PATH)


def _ensure_table(db_path: Path) -> None:
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_dna (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id       INTEGER NOT NULL,
                    spin_number       INTEGER,
                    direction         TEXT,
                    ts                DATETIME DEFAULT CURRENT_TIMESTAMP,
                    feature_name      TEXT NOT NULL,
                    feature_value     TEXT NOT NULL,
                    estimated_lift_pp REAL,
                    realized_lift_pp  REAL,
                    confidence_n     INTEGER,
                    final_action      TEXT,
                    hit               INTEGER,
                    wheel_dist        INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_dna_decision ON decision_dna(decision_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_dna_feature ON decision_dna(feature_name)"
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("DNA: falha criando tabela em %s", db_path)


def dna_log_feature(
    decision_id: int,
    feature_name: str,
    feature_value: dict,
    *,
    spin_number: Optional[int] = None,
    direction: Optional[str] = None,
    estimated_lift_pp: Optional[float] = None,
    confidence_n: Optional[int] = None,
    final_action: Optional[str] = None,
    hit: Optional[bool] = None,
    wheel_dist: Optional[int] = None,
) -> bool:
    """Insere 1 entrada em decision_dna. Retorna True se gravou, False senao.

    Best-effort: qualquer erro eh logado mas nao propagado.
    """
    if not _ENABLED or _DB_PATH is None:
        return False
    payload = (
        decision_id,
        spin_number,
        direction,
        feature_name,
        json.dumps(feature_value, sort_keys=True),
        estimated_lift_pp,
        confidence_n,
        final_action,
        1 if hit else (0 if hit is False else None),
        wheel_dist,
    )
    try:
        with _LOCK:
            conn = sqlite3.connect(str(_DB_PATH))
            try:
                conn.execute(
                    """
                    INSERT INTO decision_dna (
                        decision_id, spin_number, direction,
                        feature_name, feature_value,
                        estimated_lift_pp, confidence_n,
                        final_action, hit, wheel_dist
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()
        return True
    except Exception:
        logger.exception("DNA: falha inserindo feature_name=%s", feature_name)
        return False


def dna_update_realized(
    decision_id: int,
    *,
    realized_lift_pp: Optional[float] = None,
    hit: Optional[bool] = None,
    wheel_dist: Optional[int] = None,
) -> int:
    """Preenche campos pos-resultado para todas as entradas de uma decision.

    Retorna numero de linhas atualizadas. Best-effort.
    """
    if not _ENABLED or _DB_PATH is None:
        return 0
    sets = []
    args: list[Any] = []
    if realized_lift_pp is not None:
        sets.append("realized_lift_pp = ?")
        args.append(realized_lift_pp)
    if hit is not None:
        sets.append("hit = ?")
        args.append(1 if hit else 0)
    if wheel_dist is not None:
        sets.append("wheel_dist = ?")
        args.append(wheel_dist)
    if not sets:
        return 0
    args.append(decision_id)
    sql = f"UPDATE decision_dna SET {', '.join(sets)} WHERE decision_id = ?"
    try:
        with _LOCK:
            conn = sqlite3.connect(str(_DB_PATH))
            try:
                cur = conn.execute(sql, args)
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()
    except Exception:
        logger.exception("DNA: falha update_realized decision_id=%s", decision_id)
        return 0


def reset_for_tests() -> None:
    """Hook usado pelos testes."""
    global _DB_PATH, _ENABLED
    _DB_PATH = None
    _ENABLED = True

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
        # P3.1 (12/06): espelha para shared.decision_dna (PG) via outbox.
        # Best-effort — nunca quebra o caminho SQLite (fonte primária).
        try:
            from database.outbox_integration import maybe_publish_dna_feature
            maybe_publish_dna_feature(
                decision_id, feature_name, feature_value,
                spin_number=spin_number, direction=direction,
                final_action=final_action, hit=hit, wheel_dist=wheel_dist,
            )
        except Exception:  # noqa: BLE001
            pass
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
                rowcount = cur.rowcount
            finally:
                conn.close()
        # P3.1 (12/06): espelha realize para o PG via outbox (best-effort).
        if rowcount:
            try:
                from database.outbox_integration import maybe_publish_dna_realized
                maybe_publish_dna_realized(
                    decision_id, hit=hit, wheel_dist=wheel_dist,
                    realized_lift_pp=realized_lift_pp,
                )
            except Exception:  # noqa: BLE001
                pass
        return rowcount
    except Exception:
        logger.exception("DNA: falha update_realized decision_id=%s", decision_id)
        return 0


def reset_for_tests() -> None:
    """Hook usado pelos testes."""
    global _DB_PATH, _ENABLED
    _DB_PATH = None
    _ENABLED = True


def dna_realize_lifts(feature_name: Optional[str] = None, min_n: int = 10) -> int:
    """SP-08 DNA-03: calcula realized_lift_pp = (bucket_hit_rate - baseline_hit_rate) * 100
    em pontos percentuais (pp) e UPDATE em todas as entradas decision_dna com
    hit IS NOT NULL e realized_lift_pp IS NULL.

    Baseline = hit_rate global das decisoes realizadas (todos buckets).
    Bucket = feature_value extraido (JSON.bucket).

    Args:
        feature_name: se fornecido, restringe ao feature. None = todas.
        min_n: minimo de amostras por bucket para calcular lift (evita ruido).

    Retorna numero de linhas atualizadas. Best-effort.
    """
    if not _ENABLED or _DB_PATH is None:
        return 0
    try:
        with _LOCK:
            conn = sqlite3.connect(str(_DB_PATH))
            try:
                row = conn.execute(
                    "SELECT AVG(hit*1.0) FROM decision_dna WHERE hit IS NOT NULL"
                ).fetchone()
                baseline = float(row[0]) if row and row[0] is not None else None
                if baseline is None:
                    return 0
                # Itera buckets unicos
                where_feat = ""
                params: list[Any] = []
                if feature_name:
                    where_feat = " AND feature_name = ?"
                    params.append(feature_name)
                buckets = conn.execute(
                    f"""
                    SELECT feature_name,
                           json_extract(feature_value, '$.bucket') AS bucket,
                           AVG(hit*1.0) AS hr,
                           COUNT(*) AS n
                    FROM decision_dna
                    WHERE hit IS NOT NULL{where_feat}
                    GROUP BY feature_name, bucket
                    HAVING n >= ?
                    """,
                    params + [min_n],
                ).fetchall()
                total = 0
                for fn, bucket, hr, _n in buckets:
                    if hr is None:
                        continue
                    lift_pp = (float(hr) - baseline) * 100.0
                    cur = conn.execute(
                        """
                        UPDATE decision_dna
                        SET realized_lift_pp = ?
                        WHERE feature_name = ?
                          AND json_extract(feature_value, '$.bucket') = ?
                          AND hit IS NOT NULL
                          AND realized_lift_pp IS NULL
                        """,
                        (lift_pp, fn, bucket),
                    )
                    total += cur.rowcount
                conn.commit()
                return total
            finally:
                conn.close()
    except Exception:
        logger.exception("DNA: falha dna_realize_lifts feature=%s", feature_name)
        return 0


def dna_summary() -> list[dict]:
    """SP-09 DNA-04: agregado por (feature_name, bucket).

    Returns:
        list[dict] com keys: feature_name, bucket, n, hit_rate, avg_lift_pp,
        avg_wheel_dist. Apenas linhas realized (hit IS NOT NULL).
    """
    if _DB_PATH is None:
        return []
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        try:
            rows = conn.execute(
                """
                SELECT feature_name,
                       json_extract(feature_value, '$.bucket') AS bucket,
                       COUNT(*) AS n,
                       AVG(hit*1.0) AS hit_rate,
                       AVG(realized_lift_pp) AS avg_lift_pp,
                       AVG(wheel_dist*1.0) AS avg_wheel_dist
                FROM decision_dna
                WHERE hit IS NOT NULL
                GROUP BY feature_name, bucket
                ORDER BY feature_name, bucket
                """
            ).fetchall()
            return [
                {
                    "feature_name": r[0],
                    "bucket": r[1],
                    "n": int(r[2] or 0),
                    "hit_rate": float(r[3]) if r[3] is not None else None,
                    "avg_lift_pp": float(r[4]) if r[4] is not None else None,
                    "avg_wheel_dist": float(r[5]) if r[5] is not None else None,
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception:
        logger.exception("DNA: falha dna_summary")
        return []


def dna_realize_stats() -> dict:
    """SP-29 OBS-01: lag em segundos das features DNA que ainda AGUARDAM realize.

    Mede apenas as features "na ponta" — id maior que o da última feature já
    realizada (hit NOT NULL). Features não-realizadas que ficaram ATRÁS de uma já
    realizada são ÓRFÃS TERMINAIS (a última predição antes de um reset/troca de
    dealer, cujo "próximo spin" nunca veio) e são EXCLUÍDAS: elas nunca realizam e
    inflavam o lag para dias (falso-positivo do alerta RoletaDnaRealizeLagHigh). Se o
    pipeline update_result -> dna_update_realized travar de fato, nenhuma feature nova
    realiza, as da ponta acumulam e o lag sobe legitimamente (sinal preservado).

    Returns:
        dict {"unrealized": int, "lag_seconds": int}. Se nada aguardando, lag=0.
    """
    if not _DB_PATH:
        return {"unrealized": 0, "lag_seconds": 0}
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        try:
            row = conn.execute(
                """
                WITH last_realized AS (
                    SELECT COALESCE(MAX(id), -1) AS mx
                    FROM decision_dna WHERE hit IS NOT NULL
                )
                SELECT COUNT(*) AS n,
                       COALESCE(CAST((julianday('now') - julianday(MIN(d.ts))) * 86400 AS INTEGER), 0) AS lag_s
                FROM decision_dna d, last_realized lr
                WHERE d.realized_lift_pp IS NULL AND d.hit IS NULL AND d.id > lr.mx
                """
            ).fetchone()
            return {"unrealized": int(row[0] or 0), "lag_seconds": int(row[1] or 0)}
        finally:
            conn.close()
    except Exception:
        return {"unrealized": 0, "lag_seconds": 0}

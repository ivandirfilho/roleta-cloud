"""SP-15 DEAL-05 (27/05): offset preferencial por dealer.

Lê histórico recente de decisões com `result_hit=1` agrupado por
dealer + sda_offset, retorna o offset mais frequente (modo). Caller
escolhe se aplica (flag env SDA_DEALER_OFFSET=1).

Stateless. Defensivo: retorna None se dealer 'unknown' ou n < 30.
"""
from __future__ import annotations
import os
import sqlite3
from typing import Optional


MIN_N_FOR_DEALER_OFFSET = 30


def is_enabled() -> bool:
    return os.getenv("SDA_DEALER_OFFSET", "0") == "1"


def preferred_offset(db_path: str, dealer: str, direction: str = "horario",
                     window_minutes: int = 1440) -> Optional[int]:
    """Retorna offset (int) que mais hits gerou para esse dealer/direcao.

    Retorna None se dealer vazio/'unknown', conexao falhar, ou n < threshold.
    """
    if not dealer or dealer == "unknown":
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT sda_offset, COUNT(*) AS n,
                  (SELECT COUNT(*) FROM decisions
                   WHERE dealer = ? AND spin_direction = ? AND result_hit = 1
                     AND timestamp >= datetime('now', '-{int(window_minutes)} minutes')) AS total
                FROM decisions
                WHERE dealer = ?
                  AND spin_direction = ?
                  AND result_hit = 1
                  AND timestamp >= datetime('now', '-{int(window_minutes)} minutes')
                GROUP BY sda_offset
                ORDER BY n DESC
                LIMIT 1
                """,
                (dealer, direction, dealer, direction),
            )
            row = cur.fetchone()
            if not row or int(row["total"]) < MIN_N_FOR_DEALER_OFFSET:
                return None
            return int(row["sda_offset"] or 0)
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None
    except Exception:
        return None

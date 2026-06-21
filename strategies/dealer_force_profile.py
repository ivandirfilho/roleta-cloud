"""Vision (auditoria_pos_foto 21/06) — perfil de FORÇA por dealer×sentido.

Consumidor DORMANTE (como strategies/region_bandit.py): existe e é testado, mas
**não está wired** no caminho quente. Só lê features quando explicitamente
chamado, atrás da flag SDA_DEALER_FORCE_PROFILE (default OFF). A ativação só faz
sentido após o ramp-up de cobertura (n≥30 por dealer) — ver auditoria §6/§7.5.

Objetivo declarado pelo dono: "estratégias futuras organizadas por dealer". Este
módulo é a fundação estrutural disso: dado o dealer (e opcionalmente o modelo da
roleta), devolve o perfil de força observado por sentido (média, n, força modal),
para uma estratégia futura decidir se confia (gate por n + confiança).

Stateless. Defensivo: retorna {} se dealer 'unknown', conexão falhar, ou n<30.
Espelha o contrato de strategies/dealer_offset.py (SP-15).
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

MIN_N_FOR_FORCE_PROFILE = 30


def is_enabled() -> bool:
    return os.getenv("SDA_DEALER_FORCE_PROFILE", "0").strip().lower() in ("1", "true", "on")


def force_profile(
    db_path: str,
    dealer: str,
    direction: str = "horario",
    wheel_model: Optional[str] = None,
    window_minutes: int = 1440,
) -> dict:
    """Perfil de força observado para um dealer/sentido (opcional: modelo da mesa).

    Returns:
        {} se dealer vazio/'unknown', conexão falhar, ou n<MIN_N_FOR_FORCE_PROFILE.
        Caso contrário:
        {
          "dealer": str, "direction": str, "wheel_model": str|None,
          "n": int, "avg_force": float, "modal_force": int,
          "min_force": int, "max_force": int,
        }

    Só considera giros com spin_force real (>0). Idempotente, nunca levanta.
    """
    if not dealer or str(dealer).strip().lower() == "unknown":
        return {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            where = [
                "dealer = ?",
                "spin_direction = ?",
                "spin_force IS NOT NULL",
                "spin_force > 0",
                f"timestamp >= datetime('now', '-{int(window_minutes)} minutes')",
            ]
            params: list = [dealer, direction]
            if wheel_model:
                where.append("wheel_model = ?")
                params.append(wheel_model)
            where_sql = " AND ".join(where)

            agg = cur.execute(
                f"""
                SELECT COUNT(*) AS n, AVG(spin_force) AS avg_f,
                       MIN(spin_force) AS min_f, MAX(spin_force) AS max_f
                FROM decisions WHERE {where_sql}
                """,
                params,
            ).fetchone()
            n = int(agg["n"] or 0)
            if n < MIN_N_FOR_FORCE_PROFILE:
                return {}

            modal = cur.execute(
                f"""
                SELECT spin_force AS f, COUNT(*) AS c
                FROM decisions WHERE {where_sql}
                GROUP BY spin_force ORDER BY c DESC, f ASC LIMIT 1
                """,
                params,
            ).fetchone()

            return {
                "dealer": dealer,
                "direction": direction,
                "wheel_model": wheel_model,
                "n": n,
                "avg_force": round(float(agg["avg_f"] or 0.0), 2),
                "modal_force": int(modal["f"]) if modal else 0,
                "min_force": int(agg["min_f"] or 0),
                "max_force": int(agg["max_f"] or 0),
            }
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return {}
    except Exception:
        return {}

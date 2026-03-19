# Roleta Cloud - Analytics Handler
# Expõe dados analíticos do DB via WebSocket messages

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from database import get_repository
from models.trace import now_ms

logger = logging.getLogger(__name__)


class AnalyticsHandler:
    """
    Handler para mensagens de analytics via WebSocket.
    
    Disponibiliza dados já gravados no DB (decisions, sessions, gale_windows)
    que antes não eram acessíveis ao frontend.
    """

    def __init__(self):
        pass

    @property
    def repo(self):
        return get_repository()

    async def handle_analytics(self, msg_type: str, data: Dict) -> Dict:
        """
        Roteia mensagens de analytics e retorna resposta.
        
        Tipos:
          - get_analytics_summary: Resumo geral (stats + gale + triple rate)
          - get_sessions_list: Lista de sessões com estatísticas
          - get_gale_history: Histórico de janelas Martingale
          - get_performance_timeline: Performance ao longo do tempo
          - get_decision_log: Log de decisões recentes
        """
        handlers = {
            "get_analytics_summary": self._summary,
            "get_sessions_list": self._sessions_list,
            "get_gale_history": self._gale_history,
            "get_performance_timeline": self._performance_timeline,
            "get_decision_log": self._decision_log,
        }

        handler = handlers.get(msg_type)
        if not handler:
            return {"type": "error", "message": f"Tipo analytics desconhecido: {msg_type}"}

        try:
            result = handler(data)
            return {"type": f"{msg_type}_response", "data": result, "t_server": now_ms()}
        except Exception as e:
            logger.error(f"Erro em analytics ({msg_type}): {e}")
            return {"type": "error", "message": str(e), "t_server": now_ms()}

    def _summary(self, data: Dict) -> Dict:
        """Resumo completo: stats gerais + gale + triple rate."""
        session_id = data.get("session_id")
        return {
            "stats": self.repo.get_stats(session_id=session_id),
            "gale": self.repo.get_gale_stats(session_id=session_id),
            "triple_rate": self.repo.get_triple_rate_analysis(session_id=session_id),
        }

    def _sessions_list(self, data: Dict) -> Dict:
        """Lista sessões com estatísticas individuais."""
        limit = min(data.get("limit", 20), 100)

        conn = self.repo._get_connection()
        try:
            rows = conn.execute("""
                SELECT 
                    s.id,
                    s.start_time,
                    s.end_time,
                    COUNT(d.id) as total_decisions,
                    SUM(CASE WHEN d.final_action = 'APOSTAR' THEN 1 ELSE 0 END) as total_bets,
                    SUM(CASE WHEN d.result_hit = 1 THEN 1 ELSE 0 END) as total_hits,
                    MAX(d.gale_level) as max_gale,
                    AVG(CASE WHEN d.final_action = 'APOSTAR' AND d.result_hit IS NOT NULL
                        THEN CAST(d.result_hit AS REAL) ELSE NULL END) as hit_rate
                FROM sessions s
                LEFT JOIN decisions d ON d.session_id = s.id
                GROUP BY s.id
                ORDER BY s.start_time DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return {
                "sessions": [
                    {
                        "id": row["id"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "total_decisions": row["total_decisions"] or 0,
                        "total_bets": row["total_bets"] or 0,
                        "total_hits": row["total_hits"] or 0,
                        "max_gale": row["max_gale"] or 1,
                        "hit_rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0,
                    }
                    for row in rows
                ],
                "total_sessions": len(rows),
            }
        finally:
            conn.close()

    def _gale_history(self, data: Dict) -> Dict:
        """Histórico de janelas Martingale (para análise de padrões)."""
        direction = data.get("direction")  # "cw" | "ccw" | None (ambas)
        limit = min(data.get("limit", 50), 200)

        conn = self.repo._get_connection()
        try:
            query = """
                SELECT 
                    gw.id, gw.direction, gw.gale_level,
                    gw.started_at, gw.ended_at,
                    gw.total_hits, gw.total_plays, gw.result,
                    gw.next_level,
                    gw.sda17_rate_at_start, gw.bet_rate_at_start
                FROM gale_windows gw
                WHERE gw.ended_at IS NOT NULL
            """
            params = []

            if direction:
                query += " AND gw.direction = ?"
                params.append(direction)

            query += " ORDER BY gw.started_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            windows = []
            for row in rows:
                # Buscar plays da janela
                plays = conn.execute("""
                    SELECT play_number, hit, spin_number, spin_force, 
                           sda_score, tr_confidence
                    FROM window_plays 
                    WHERE window_id = ?
                    ORDER BY play_number
                """, (row["id"],)).fetchall()

                windows.append({
                    "id": row["id"],
                    "direction": row["direction"],
                    "gale_level": row["gale_level"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "total_hits": row["total_hits"],
                    "total_plays": row["total_plays"],
                    "result": row["result"],
                    "next_level": row["next_level"],
                    "sda17_rate_at_start": row["sda17_rate_at_start"],
                    "bet_rate_at_start": row["bet_rate_at_start"],
                    "plays": [
                        {
                            "play_number": p["play_number"],
                            "hit": bool(p["hit"]),
                            "spin_number": p["spin_number"],
                            "spin_force": p["spin_force"],
                            "sda_score": p["sda_score"],
                            "tr_confidence": p["tr_confidence"],
                        }
                        for p in plays
                    ],
                })

            # Sumário por resultado
            summary = {}
            for w in windows:
                r = w["result"] or "unknown"
                summary.setdefault(r, 0)
                summary[r] += 1

            return {"windows": windows, "summary": summary, "total": len(windows)}
        finally:
            conn.close()

    def _performance_timeline(self, data: Dict) -> Dict:
        """Performance agrupada por hora/dia para gráficos de tendência."""
        period = data.get("period", "hour")  # "hour" | "day"
        limit = min(data.get("limit", 48), 168)  # max 168 (7 dias por hora)

        fmt = "%Y-%m-%d %H:00:00" if period == "hour" else "%Y-%m-%d"

        conn = self.repo._get_connection()
        try:
            rows = conn.execute(f"""
                SELECT 
                    strftime('{fmt}', timestamp) as period,
                    COUNT(*) as total_decisions,
                    SUM(CASE WHEN final_action = 'APOSTAR' THEN 1 ELSE 0 END) as bets,
                    SUM(CASE WHEN result_hit = 1 THEN 1 ELSE 0 END) as hits,
                    AVG(CASE WHEN final_action = 'APOSTAR' AND result_hit IS NOT NULL
                        THEN CAST(result_hit AS REAL) ELSE NULL END) as hit_rate,
                    AVG(sda_score) as avg_sda_score
                FROM decisions
                WHERE timestamp IS NOT NULL
                GROUP BY strftime('{fmt}', timestamp)
                ORDER BY period DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return {
                "period_type": period,
                "data": [
                    {
                        "period": row["period"],
                        "total": row["total_decisions"],
                        "bets": row["bets"] or 0,
                        "hits": row["hits"] or 0,
                        "hit_rate": round(row["hit_rate"] * 100, 1) if row["hit_rate"] else 0,
                        "avg_sda_score": round(row["avg_sda_score"], 1) if row["avg_sda_score"] else 0,
                    }
                    for row in rows
                ],
            }
        finally:
            conn.close()

    def _decision_log(self, data: Dict) -> Dict:
        """Log das últimas decisões (para debug/auditoria)."""
        limit = min(data.get("limit", 30), 100)
        session_id = data.get("session_id")

        decisions = self.repo.get_decisions(session_id=session_id, limit=limit)
        return {
            "decisions": [
                {
                    "id": d.id,
                    "timestamp": str(d.timestamp) if d.timestamp else None,
                    "spin_number": d.spin_number,
                    "spin_direction": d.spin_direction,
                    "spin_force": d.spin_force,
                    "final_action": d.final_action,
                    "action_reason": d.action_reason,
                    "sda_score": d.sda_score,
                    "sda_center": d.sda_center,
                    "tr_confidence": d.tr_confidence,
                    "gale_level": d.gale_level,
                    "result_hit": d.result_hit,
                    "result_actual": d.result_actual,
                }
                for d in decisions
            ],
            "total": len(decisions),
        }


# Singleton
analytics_handler = AnalyticsHandler()

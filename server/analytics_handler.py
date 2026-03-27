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
        sessions = self.repo.get_sessions_list(limit=limit)
        return {"sessions": sessions, "total_sessions": len(sessions)}

    def _gale_history(self, data: Dict) -> Dict:
        """Histórico de janelas Martingale (para análise de padrões)."""
        direction = data.get("direction")
        limit = min(data.get("limit", 50), 200)
        windows = self.repo.get_gale_window_history(direction=direction, limit=limit)

        summary = {}
        for w in windows:
            r = w["result"] or "unknown"
            summary.setdefault(r, 0)
            summary[r] += 1

        return {"windows": windows, "summary": summary, "total": len(windows)}

    def _performance_timeline(self, data: Dict) -> Dict:
        """Performance agrupada por hora/dia para gráficos de tendência."""
        period = data.get("period", "hour")
        limit = min(data.get("limit", 48), 168)
        timeline = self.repo.get_performance_timeline(period=period, limit=limit)
        return {"period_type": period, "data": timeline}

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
                    "sda_centers": d.sda_centers,
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

# Roleta Cloud - Database Models
# Modelos de dados para logging de decisões

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import json


@dataclass
class Decision:
    """
    Representa uma decisão do sistema.
    Armazena todo o contexto para análise posterior.
    """
    # Identificação
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: str = ""
    
    # Contexto do Spin
    spin_number: int = 0
    spin_direction: str = ""  # "horario" ou "anti-horario"
    spin_force: int = 0
    
    # Triple Rate Advisor
    tr_should_bet: bool = True
    tr_confidence: str = ""  # "alta", "media", "baixa"
    tr_reason: str = ""
    tr_c4_rate: float = 0.0
    tr_m6_rate: float = 0.0
    tr_l12_rate: float = 0.0
    
    # SDA17 Strategy
    sda_should_bet: bool = True
    sda_score: int = 0
    sda_center: int = 0
    sda_numbers: List[int] = field(default_factory=list)
    sda_predicted_force: int = 0
    
    # Decisão Final
    final_action: str = ""  # "APOSTAR" ou "PULAR"
    action_reason: str = ""  # Por que tomou essa decisão
    
    # Martingale State
    gale_level: int = 1
    gale_window_hits: int = 0
    gale_window_count: int = 0
    gale_bet_value: int = 17
    
    # Resultado (preenchido no próximo spin)
    result_hit: Optional[bool] = None
    result_actual: Optional[int] = None
    
    # Calibração
    calibration_offset: int = 0
    calibration_error: Optional[int] = None
    
    # Performance snapshot
    performance_snapshot: List[bool] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "session_id": self.session_id,
            "spin_number": self.spin_number,
            "spin_direction": self.spin_direction,
            "spin_force": self.spin_force,
            "tr_should_bet": self.tr_should_bet,
            "tr_confidence": self.tr_confidence,
            "tr_reason": self.tr_reason,
            "tr_c4_rate": self.tr_c4_rate,
            "tr_m6_rate": self.tr_m6_rate,
            "tr_l12_rate": self.tr_l12_rate,
            "sda_should_bet": self.sda_should_bet,
            "sda_score": self.sda_score,
            "sda_center": self.sda_center,
            "sda_numbers": self.sda_numbers,
            "sda_predicted_force": self.sda_predicted_force,
            "final_action": self.final_action,
            "action_reason": self.action_reason,
            "gale_level": self.gale_level,
            "gale_window_hits": self.gale_window_hits,
            "gale_window_count": self.gale_window_count,
            "gale_bet_value": self.gale_bet_value,
            "result_hit": self.result_hit,
            "result_actual": self.result_actual,
            "calibration_offset": self.calibration_offset,
            "calibration_error": self.calibration_error,
            "performance_snapshot": self.performance_snapshot
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Decision":
        """Cria instância a partir de dicionário."""
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class Session:
    """
    Representa uma sessão de jogo.
    Agrupa decisões e mantém estatísticas.
    """
    id: str = ""
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    # Estatísticas
    total_spins: int = 0
    total_bets: int = 0
    total_hits: int = 0
    total_profit: float = 0.0
    max_gale_reached: int = 1
    total_stops: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_spins": self.total_spins,
            "total_bets": self.total_bets,
            "total_hits": self.total_hits,
            "total_profit": self.total_profit,
            "max_gale_reached": self.max_gale_reached,
            "total_stops": self.total_stops
        }


@dataclass
class GaleWindow:
    """
    Representa uma janela de 5 jogadas do Martingale.
    Cada vez que o gale inicia uma nova janela, cria-se um novo GaleWindow.
    Usado para análise ML e visualização no dashboard.
    """
    id: Optional[int] = None
    direction: str = ""  # "cw" ou "ccw"
    gale_level: int = 1  # 1, 2 ou 3
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    
    # Resultados da janela
    total_hits: int = 0
    total_plays: int = 0
    result: str = ""  # "success", "escalated", "stop"
    next_level: Optional[int] = None
    
    # Features para ML (context at window start)
    sda17_rate_at_start: float = 0.0
    bet_rate_at_start: float = 0.0
    calibration_offset: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "direction": self.direction,
            "gale_level": self.gale_level,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "total_hits": self.total_hits,
            "total_plays": self.total_plays,
            "result": self.result,
            "next_level": self.next_level,
            "sda17_rate_at_start": self.sda17_rate_at_start,
            "bet_rate_at_start": self.bet_rate_at_start,
            "calibration_offset": self.calibration_offset
        }


@dataclass
class WindowPlay:
    """
    Representa uma jogada individual dentro de uma janela de gale.
    Cada GaleWindow tem no máximo 5 WindowPlays.
    """
    id: Optional[int] = None
    window_id: int = 0  # FK para GaleWindow
    play_number: int = 0  # 1 a 5
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Contexto do spin
    spin_number: int = 0
    spin_direction: str = ""
    spin_force: int = 0
    center_predicted: int = 0
    
    # Resultado
    hit: Optional[bool] = None
    actual_number: Optional[int] = None
    
    # Decisão context
    sda_score: int = 0
    tr_confidence: str = ""
    tr_reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "window_id": self.window_id,
            "play_number": self.play_number,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "spin_number": self.spin_number,
            "spin_direction": self.spin_direction,
            "spin_force": self.spin_force,
            "center_predicted": self.center_predicted,
            "hit": self.hit,
            "actual_number": self.actual_number,
            "sda_score": self.sda_score,
            "tr_confidence": self.tr_confidence,
            "tr_reason": self.tr_reason
        }


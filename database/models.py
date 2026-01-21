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

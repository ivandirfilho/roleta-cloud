# Roleta Cloud - Timeline por Direção

from dataclasses import dataclass, field
from typing import List
from app_config.settings import settings


@dataclass
class Timeline:
    """
    Linha temporal de forças para uma direção específica.
    
    CONVENÇÃO: índice 0 = mais recente, índice -1 = mais antigo
    """
    direction: str  # 'cw' (clockwise/horário) ou 'ccw' (counter-clockwise/anti-horário)
    forces: List[int] = field(default_factory=list)
    
    def add(self, force: int) -> None:
        """
        Adiciona uma força no início (mais recente).
        Remove a mais antiga se ultrapassar o limite.
        """
        self.forces.insert(0, force)
        if len(self.forces) > settings.game.max_timeline_size:
            self.forces.pop()
    
    def get_last_n(self, n: int) -> List[int]:
        """Retorna as últimas N forças (mais recentes primeiro)."""
        return self.forces[:n]
    
    @property
    def size(self) -> int:
        """Quantidade de forças armazenadas."""
        return len(self.forces)
    
    @property
    def is_ready(self) -> bool:
        """Tem forças suficientes para análise?"""
        return self.size >= settings.game.sda_forces_analyzed
    
    def clear(self) -> None:
        """Limpa todas as forças da timeline."""
        self.forces = []
    
    def to_dict(self) -> dict:
        """Serializa para JSON."""
        return {
            "direction": self.direction,
            "forces": self.forces
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Timeline":
        """Deserializa de JSON."""
        return cls(
            direction=data.get("direction", "cw"),
            forces=data.get("forces", [])
        )

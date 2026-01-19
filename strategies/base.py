# Roleta Cloud - Strategy Base Class

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from state.timeline import Timeline


@dataclass
class StrategyResult:
    """Resultado de uma análise de estratégia."""
    should_bet: bool = False
    numbers: List[int] = field(default_factory=list)
    center: int = 0
    score: int = 0
    visual: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class StrategyBase(ABC):
    """
    Classe base para todas as estratégias.
    """
    
    def __init__(self, name: str, num_neighbors: int = 5):
        self.name = name
        self.num_neighbors = num_neighbors
        self.enabled = True
    
    @abstractmethod
    def analyze(
        self, 
        timeline: Timeline, 
        last_number: int,
        wheel_sequence: List[int]
    ) -> StrategyResult:
        """
        Analisa a timeline e retorna resultado.
        
        Args:
            timeline: Timeline da direção alvo
            last_number: Último número sorteado
            wheel_sequence: Sequência física da roleta
            
        Returns:
            StrategyResult com sugestão
        """
        pass
    
    def get_neighbors(
        self, 
        center: int, 
        radius: int, 
        wheel_sequence: List[int]
    ) -> List[int]:
        """
        Retorna vizinhos de um número na roleta.
        """
        try:
            center_idx = wheel_sequence.index(center)
            wheel_size = len(wheel_sequence)
            neighbors = []
            
            for offset in range(-radius, radius + 1):
                idx = (center_idx + offset) % wheel_size
                neighbors.append(wheel_sequence[idx])
            
            return neighbors
        except ValueError:
            return [center]
    
    def get_visual_region(
        self, 
        center: int, 
        neighbors: List[int]
    ) -> str:
        """
        Gera representação visual da região.
        Ex: "4, 21, [2], 25, 17"
        """
        parts = []
        for num in neighbors:
            if num == center:
                parts.append(f"[{num}]")
            else:
                parts.append(str(num))
        return ", ".join(parts)

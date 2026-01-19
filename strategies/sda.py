# Roleta Cloud - SDA Strategy (Sinergia Direcional Avançada)

from typing import List, Dict, Tuple
from dataclasses import dataclass

import config
from state.timeline import Timeline
from .base import StrategyBase, StrategyResult


class SDAStrategy(StrategyBase):
    """
    Estratégia Sinergia Direcional Avançada.
    
    Analisa as forças da direção alvo e calcula clusters
    para determinar o melhor centro de aposta.
    """
    
    def __init__(self, num_neighbors: int = 5):
        super().__init__(name=f"SDA-{num_neighbors * 2 + 1}", num_neighbors=num_neighbors)
        self.min_forces = config.SDA_FORCES_ANALYZED
    
    def analyze(
        self,
        timeline: Timeline,
        last_number: int,
        wheel_sequence: List[int]
    ) -> StrategyResult:
        """
        Analisa a timeline e retorna sugestão.
        """
        # Verificar se tem forças suficientes
        if timeline.size < self.min_forces:
            return StrategyResult(
                should_bet=False,
                details={"reason": f"Forças insuficientes ({timeline.size}/{self.min_forces})"}
            )
        
        # Pegar últimas forças
        forces = timeline.get_last_n(self.min_forces)
        
        # Calcular scores de cluster para cada centro possível
        cluster_scores = self._calculate_cluster_scores(forces, wheel_sequence)
        
        # Encontrar melhor cluster
        best_center_force, best_score = max(cluster_scores, key=lambda x: x[1])
        
        if best_score < 2:  # Score mínimo para apostar
            return StrategyResult(
                should_bet=False,
                score=best_score,
                details={"reason": f"Score baixo ({best_score})"}
            )
        
        # Calcular número central aplicando a força
        center_number = self._apply_force(
            last_number, 
            best_center_force, 
            timeline.direction,
            wheel_sequence
        )
        
        # Pegar vizinhos
        numbers = self.get_neighbors(center_number, self.num_neighbors, wheel_sequence)
        visual = self.get_visual_region(center_number, numbers)
        
        return StrategyResult(
            should_bet=True,
            numbers=numbers,
            center=center_number,
            score=best_score,
            visual=visual,
            details={
                "forces": forces,
                "best_force": best_center_force,
                "cluster_score": best_score
            }
        )
    
    def _calculate_cluster_scores(
        self, 
        forces: List[int],
        wheel_sequence: List[int]
    ) -> List[Tuple[int, int]]:
        """
        Calcula score de cluster para cada centro de força possível.
        
        Returns:
            Lista de (centro_forca, score)
        """
        wheel_size = len(wheel_sequence)
        radius = self.num_neighbors
        scores = []
        
        for center_force in range(1, wheel_size + 1):
            score = 0
            for force in forces:
                distance = self._circular_distance(force, center_force, wheel_size)
                if distance <= radius:
                    score += 1
            scores.append((center_force, score))
        
        return scores
    
    def _circular_distance(self, f1: int, f2: int, universe: int) -> int:
        """Distância circular entre duas forças."""
        linear = abs(f1 - f2)
        return min(linear, universe - linear)
    
    def _apply_force(
        self,
        from_number: int,
        force: int,
        target_direction: str,
        wheel_sequence: List[int]
    ) -> int:
        """Aplica uma força a partir de um número."""
        try:
            from_idx = wheel_sequence.index(from_number)
            wheel_size = len(wheel_sequence)
            
            if target_direction == "cw" or target_direction == "horario":
                target_idx = (from_idx + force) % wheel_size
            else:
                target_idx = (from_idx - force) % wheel_size
            
            return wheel_sequence[target_idx]
        except ValueError:
            return from_number

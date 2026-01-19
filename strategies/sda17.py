# Roleta Cloud - SDA-17 Strategy (Regressão Linear)

from typing import List, Tuple
from state.timeline import Timeline
from .base import StrategyBase, StrategyResult
import config


class SDA17Strategy(StrategyBase):
    """
    Estratégia SDA-17: Sinergia Direcional Avançada com Regressão Linear.
    
    Diferente da SDA original que usa clusters, esta versão:
    - Usa regressão linear para prever a PRÓXIMA força
    - Captura automaticamente aceleração/frenagem
    - Sugere 17 números (1 centro + 8 de cada lado)
    """
    
    def __init__(self):
        super().__init__(name="SDA-17", num_neighbors=8)
        self.min_forces = 5
        self.description = "Regressão linear em 5 forças, 17 números"
    
    def analyze(
        self,
        timeline: Timeline,
        last_number: int,
        wheel_sequence: List[int],
        calibration: int = 0  # Fine-tuning offset
    ) -> StrategyResult:
        """Analisa timeline e prediz próxima força."""
        
        # Verificar forças suficientes
        if timeline.size < self.min_forces:
            return StrategyResult(
                should_bet=False,
                details={"reason": f"Forças insuficientes ({timeline.size}/{self.min_forces})"}
            )
        
        # Pegar últimas 5 forças
        forces = timeline.get_last_n(self.min_forces)
        
        # Prever próxima força usando regressão linear
        predicted_force, trend = self._predict_next_force(forces)
        
        # Aplicar calibração (fine-tuning)
        if calibration != 0:
            predicted_force = max(1, min(37, predicted_force + calibration))
            trend = f"{trend} [offset: {calibration:+d}]"
        
        # Calcular confiança (para referência, não bloqueia mais)
        confidence = self._calculate_confidence(forces, predicted_force)
        
        # Aplicar força predita ao último número
        center_number = self._apply_force(
            last_number,
            predicted_force,
            timeline.direction,
            wheel_sequence
        )
        
        # Pegar 17 vizinhos (8 + centro + 8)
        numbers = self.get_neighbors(center_number, self.num_neighbors, wheel_sequence)
        visual = self.get_visual_region(center_number, numbers)
        
        return StrategyResult(
            should_bet=True,
            numbers=numbers,
            center=center_number,
            score=confidence,
            visual=visual,
            details={
                "forces": forces,
                "predicted_force": predicted_force,
                "trend": trend,
                "confidence": confidence,
                "calibration": calibration
            }
        )
    
    def _predict_next_force(self, forces: List[int]) -> Tuple[int, str]:
        """
        Usa regressão linear para prever próxima força.
        
        Args:
            forces: Lista de forças [mais_recente, ..., mais_antiga]
            
        Returns:
            (força_predita, tendência)
        """
        n = len(forces)
        
        # Inverter para ordem cronológica (antiga → recente)
        y = list(reversed(forces))
        x = list(range(n))
        
        # Calcular médias
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        # Calcular coeficientes da regressão
        numerador = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominador = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        slope = numerador / denominador if denominador != 0 else 0
        intercept = y_mean - slope * x_mean
        
        # Prever próxima força (x = n)
        predicted = intercept + slope * n
        
        # Limitar ao universo [1, 37]
        predicted_force = max(1, min(37, int(round(predicted))))
        
        # Determinar tendência
        if slope > 1:
            trend = f"acelerando (+{slope:.1f}/spin)"
        elif slope < -1:
            trend = f"freando ({slope:.1f}/spin)"
        else:
            trend = "estável"
        
        return predicted_force, trend
    
    def _calculate_confidence(self, forces: List[int], predicted: int) -> int:
        """
        Calcula confiança baseada em quão próximas as forças estão da predição.
        Retorna score de 0 a 6.
        """
        score = 0
        
        # Quantas forças estão dentro de ±8 da predição?
        for force in forces:
            distance = abs(force - predicted)
            # Distância circular
            distance = min(distance, 37 - distance)
            if distance <= 8:
                score += 1
        
        # Bonus: forças recentes mais próximas
        recent_force = forces[0]
        if abs(recent_force - predicted) <= 4:
            score += 1
        
        return min(6, score)
    
    def _apply_force(
        self,
        from_number: int,
        force: int,
        target_direction: str,
        wheel_sequence: List[int]
    ) -> int:
        """Aplica força ao número, retorna número resultado."""
        try:
            from_idx = wheel_sequence.index(from_number)
            wheel_size = len(wheel_sequence)
            
            if target_direction in ("cw", "horario"):
                target_idx = (from_idx + force) % wheel_size
            else:
                target_idx = (from_idx - force) % wheel_size
            
            return wheel_sequence[target_idx]
        except ValueError:
            return from_number

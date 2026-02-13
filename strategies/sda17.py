# Roleta Cloud - SDA-19 Strategy (IQR + Weighted Median + Drift)

from typing import List, Tuple, Dict, Any
from statistics import median
from state.timeline import Timeline
from .base import StrategyBase, StrategyResult


class SDA17Strategy(StrategyBase):
    """
    Estratégia SDA-19: Sinergia Direcional Avançada — Robust.
    
    Pipeline otimizado (v2):
    1. Janela Adaptativa (7→5→3 forças)
    2. IQR Outlier Rejection (remove forças anômalas)
    3. Weighted Median (peso exponencial nas mais recentes)
    4. Drift Detection (extrapola tendência se monotônica)
    5. Smart Score (survival_rate × tightness)
    
    Cobertura: 19 números (1 centro + 9 de cada lado) = 51.4% da roda
    """
    
    def __init__(self):
        super().__init__(name="SDA-19", num_neighbors=9)
        self.min_forces = 3
        self.default_window = 7
        self.decay = 0.8  # Fator de decaimento temporal
        self.description = "IQR + Weighted Median + Drift, 19 números"
    
    def analyze(
        self,
        timeline: Timeline,
        last_number: int,
        wheel_sequence: List[int],
        calibration: int = 0,
        error_history: List[int] = None
    ) -> StrategyResult:
        """Analisa timeline e prediz próxima força usando pipeline robusto."""
        
        # Janela adaptativa: tenta 7, depois 5, depois min_forces
        predicted_force = None
        pred_info = {}
        
        for window in [self.default_window, 5, self.min_forces]:
            if timeline.size >= window:
                forces = timeline.get_last_n(window)
                predicted_force, pred_info = self._predict_robust(forces)
                # Aceita se pelo menos metade dos dados sobreviveu ao IQR
                if pred_info["clean_count"] >= max(2, window // 2):
                    break
        
        # Sem dados suficientes
        if predicted_force is None:
            return StrategyResult(
                should_bet=False,
                details={"reason": f"Forças insuficientes ({timeline.size}/{self.min_forces})"}
            )
        
        # Aplicar offset de momentum (se ativado)
        original_force = predicted_force
        if calibration != 0:
            predicted_force = max(1, min(37, predicted_force + calibration))
        
        # Aplicar força predita ao último número
        center_number = self._apply_force(
            last_number,
            predicted_force,
            timeline.direction,
            wheel_sequence
        )
        
        # Pegar 19 vizinhos (9 + centro + 9)
        numbers = self.get_neighbors(center_number, self.num_neighbors, wheel_sequence)
        visual = self.get_visual_region(center_number, numbers)
        
        return StrategyResult(
            should_bet=True,
            numbers=numbers,
            center=center_number,
            score=pred_info.get("score", 3),
            visual=visual,
            details={
                "forces": forces,
                "predicted_force": predicted_force,
                "original_prediction": original_force,
                "method": pred_info.get("method", "iqr_weighted_median"),
                "clean_count": pred_info.get("clean_count", 0),
                "outliers_removed": pred_info.get("outliers_removed", 0),
                "spread": pred_info.get("spread", 0),
                "drift": pred_info.get("drift", 0),
                "survival_rate": pred_info.get("survival_rate", 1.0),
                "calibration": calibration
            }
        )
    
    def _predict_robust(self, forces: List[int]) -> Tuple[int, Dict[str, Any]]:
        """
        Pipeline robusto: IQR → Weighted Median → Drift.
        
        Args:
            forces: Lista de forças [mais_recente, ..., mais_antiga]
            
        Returns:
            (força_predita, info_do_pipeline)
        """
        n = len(forces)
        
        # === PASSO 1: IQR Outlier Rejection ===
        sorted_f = sorted(forces)
        q1 = sorted_f[max(0, n // 4)]
        q3 = sorted_f[min(n - 1, 3 * n // 4)]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Mantém posição original (idx) para peso temporal correto
        clean = [(f, idx) for idx, f in enumerate(forces) if lower_bound <= f <= upper_bound]
        
        # Fallback: se filtro removeu demais, usa todos
        if len(clean) < 2:
            clean = [(f, idx) for idx, f in enumerate(forces)]
        
        # === PASSO 2: Weighted Median (peso exponencial por recência) ===
        expanded = []
        for force, orig_idx in clean:
            # Peso: posição 0 = 1.0, pos 1 = 0.8, pos 2 = 0.64, etc.
            weight = self.decay ** orig_idx
            repeats = max(1, int(weight * 10))
            expanded.extend([force] * repeats)
        
        pred = int(median(expanded))
        
        # === PASSO 3: Drift Detection (sobre dados CRONOLÓGICOS originais) ===
        drift_adj = 0
        if n >= 3:
            last3 = forces[:3]  # As 3 mais recentes na ordem original
            diffs = [last3[i] - last3[i + 1] for i in range(2)]
            # Só extrapola se AMBAS as diferenças têm mesmo sinal (tendência consistente)
            if all(d > 0 for d in diffs):
                drift_adj = int(sum(diffs) / 2 * 0.5)
            elif all(d < 0 for d in diffs):
                drift_adj = int(sum(diffs) / 2 * 0.5)
        
        pred = max(1, min(37, pred + drift_adj))
        
        # === PASSO 4: Smart Score ===
        survival = len(clean) / n
        clean_values = [f for f, _ in clean]
        spread = max(clean_values) - min(clean_values) if len(clean_values) > 1 else 0
        tightness = max(0, 1 - spread / 15)
        stable_bonus = 1 if drift_adj == 0 else 0
        score = min(6, max(1, int(survival * 3 + tightness * 3 + stable_bonus)))
        
        return pred, {
            "method": "iqr_weighted_median",
            "clean_count": len(clean),
            "outliers_removed": n - len(clean),
            "spread": spread,
            "drift": drift_adj,
            "survival_rate": round(survival, 2),
            "score": score
        }
    
    def calculate_momentum_offset(
        self, 
        error: int, 
        error_history: List[int],
        current_offset: int
    ) -> int:
        """
        Calcula novo offset usando momentum.
        
        Considera:
        - Erro atual (30% de peso)
        - Aceleração do erro (20% de peso)
        
        Args:
            error: Erro atual (diferença circular entre previsão e real)
            error_history: Lista de erros anteriores
            current_offset: Offset atual
            
        Returns:
            Novo offset (limitado a ±8)
        """
        if error_history and len(error_history) > 0:
            accel = error - error_history[-1]
        else:
            accel = 0
        
        new_offset = current_offset + int(error * 0.3 + accel * 0.2)
        return max(-8, min(8, new_offset))
    
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

# Roleta Cloud - SDA-21 Strategy (IQR + Weighted Median + Drift + Triple Focus)

from typing import List, Tuple, Dict, Any
from statistics import median, quantiles
from state.timeline import Timeline
from .base import StrategyBase, StrategyResult


class SDA17Strategy(StrategyBase):
    """
    Estratégia SDA-21: Sinergia Direcional Avançada — Triple Focus.
    
    Pipeline otimizado (v3):
    1. Janela Adaptativa (7→5→3 forças)
    2. IQR Outlier Rejection (statistics.quantiles)
    3. Weighted Median (peso exponencial nas mais recentes)
    4. Drift Detection (sobre dados limpos pós-IQR)
    5. Smart Score (survival_rate × tightness)
    6. Triple Focus: 3 centros (mediana, max, min) com diversificação
    
    Cobertura: até 21 números (3 centros × 3 vizinhos cada) = até 56.8% da roda
    """
    
    def __init__(self):
        super().__init__(name="SDA-21", num_neighbors=3)
        self.min_forces = 3
        self.default_window = 7
        self.decay = 0.8
        self.description = "IQR + Weighted Median + Drift, Triple Focus 21 números"
    
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
        
        # === TRIPLE FOCUS: 3 centros ===
        # Centro 1: Mediana Ponderada (pipeline SDA)
        c1 = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)
        
        # Filtrar forças válidas (>0) para max/min — BUG-T02 fix
        valid_forces = [f for f in forces if f > 0]
        if len(valid_forces) < 2:
            valid_forces = forces  # Fallback: usar todas se poucas válidas
        
        # Centro 2: Força Máxima da timeline
        max_force = max(valid_forces)
        c2 = self._apply_force(last_number, max_force, timeline.direction, wheel_sequence)
        
        # Centro 3: Força Mínima da timeline
        min_force = min(valid_forces)
        c3 = self._apply_force(last_number, min_force, timeline.direction, wheel_sequence)
        
        # Garantir diversificação mínima entre centros
        c1, c2, c3 = self._ensure_diversity(c1, c2, c3, wheel_sequence)
        
        # Agregar números dos 3 clusters
        nums = set()
        for center in [c1, c2, c3]:
            nums |= set(self.get_neighbors(center, self.num_neighbors, wheel_sequence))
        numbers = sorted(nums)
        
        visual = f"[{c1}] [{c2}] [{c3}]"
        
        return StrategyResult(
            should_bet=True,
            numbers=numbers,
            center=c1,  # Centro primário para compatibilidade
            score=pred_info.get("score", 3),
            visual=visual,
            details={
                "forces": forces,
                "predicted_force": predicted_force,
                "original_prediction": original_force,
                "method": "triple_focus_iqr_weighted_median",
                "centers": [c1, c2, c3],
                "forces_used": {"median": predicted_force, "max": max_force, "min": min_force},
                "unique_count": len(numbers),
                "overlap": (7 * 3) - len(numbers),
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
        # 🔧 BUG-009: com N < 4, quartis são irrelevantes — pular filtragem
        if n < 4:
            clean = [(f, idx) for idx, f in enumerate(forces)]
        else:
            # MEL-01: IQR com statistics.quantiles() para precisão
            sorted_f = sorted(forces)
            q1, _, q3 = quantiles(sorted_f, n=4)
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
        
        # === PASSO 3: Drift Detection (MEL-05: sobre dados LIMPOS pós-IQR) ===
        drift_adj = 0
        if len(clean) >= 3:
            # Ordenar clean por posição original (mais recente primeiro)
            clean_by_recency = sorted(clean, key=lambda x: x[1])[:3]
            last3_clean = [f for f, _ in clean_by_recency]
            diffs = [last3_clean[i] - last3_clean[i + 1] for i in range(min(2, len(last3_clean) - 1))]
            if len(diffs) >= 2:
                if all(d > 0 for d in diffs):
                    drift_adj = int(sum(diffs) * 0.5)
                elif all(d < 0 for d in diffs):
                    drift_adj = int(sum(diffs) * 0.5)
        
        pred = max(1, min(37, pred + drift_adj))
        
        # === PASSO 4: Smart Score ===
        survival = len(clean) / n
        clean_values = [f for f, _ in clean]
        spread = max(clean_values) - min(clean_values) if len(clean_values) > 1 else 0
        # MEL-13: Spread normalizado por MAX_FORCE=18 (metade da roda)
        tightness = max(0, 1 - spread / 18)
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
    
    def _ensure_diversity(
        self,
        c1: int,
        c2: int,
        c3: int,
        wheel_sequence: List[int]
    ) -> Tuple[int, int, int]:
        """Garante separação mínima de 4 posições entre quaisquer 2 centros."""
        wheel_size = len(wheel_sequence)
        
        def circ_dist(a: int, b: int) -> int:
            try:
                a_pos = wheel_sequence.index(a)
                b_pos = wheel_sequence.index(b)
                return min((a_pos - b_pos) % wheel_size, (b_pos - a_pos) % wheel_size)
            except ValueError:
                return 0
        
        c1_pos = wheel_sequence.index(c1)
        
        # Se C2 muito perto de C1, deslocar C2 por +7
        if circ_dist(c1, c2) < 4:
            c2 = wheel_sequence[(c1_pos + 7) % wheel_size]
        
        # Se C3 muito perto de C1 ou C2, deslocar C3 por -7
        if circ_dist(c1, c3) < 4 or circ_dist(c2, c3) < 4:
            c3 = wheel_sequence[(c1_pos - 7) % wheel_size]
        
        return c1, c2, c3

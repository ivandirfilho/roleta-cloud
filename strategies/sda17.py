# Roleta Cloud - M15-ADA Strategy (IQR + Weighted Median + Drift + Adaptive Triple Focus)

from typing import List, Tuple, Dict, Any
from statistics import median, quantiles
from state.timeline import Timeline
from .base import StrategyBase, StrategyResult


class SDA17Strategy(StrategyBase):
    """
    Estratégia M15-ADA: Adaptive Dual Algorithm — Triple Focus 17 números.
    
    Pipeline otimizado (v4):
    1. Janela Adaptativa (7→5→3 forças)
    2. IQR Outlier Rejection (statistics.quantiles)
    3. Weighted Median (peso exponencial nas mais recentes)
    4. Drift Detection (sobre dados limpos pós-IQR)
    5. Smart Score (survival_rate × tightness)
    6. Adaptive Triple Focus:
       - C1: mediana ponderada, raio 3 (7 números)
       - C2/C3: offset adaptativo por direção, raio 2 (5 números cada)
       - CW: ErrDriven EMA (α=0.25) — converge para offsets menores (8-10)
       - CCW: Bayesiano retrospectivo (window=12) — converge para offsets maiores (14-15)
    
    Cobertura: 17 números (7+5+5) = 45.9% da roda
    Break-even: 47.2% (vs 58.3% do SDA-21)
    EV simulado: +R$1.51/jogada (vs -R$2.10 do SDA-21)
    """
    
    # Forças acima deste limiar são sinalizadas como anômalas
    MAX_FORCE_THRESHOLD = 30

    # M15-ADA: Constantes adaptativas por direção
    CW_ALPHA = 0.25           # Taxa de aprendizado EMA (CW)
    CW_EMA_INIT = 12.0        # EMA inicial (CW)
    CW_OFFSET_MIN = 8         # Offset mínimo (CW)
    CW_OFFSET_MAX = 16        # Offset máximo (CW)
    CCW_WINDOW = 12            # Janela bayesiana (CCW)
    CCW_DEFAULT_OFFSET = 14    # Offset padrão durante warm-up (CCW)
    CCW_WARMUP = 5             # Jogadas mínimas antes de adaptar (CCW)
    CCW_OFFSET_MIN = 7         # Offset mínimo candidato (CCW)
    CCW_OFFSET_MAX = 17        # Offset máximo candidato (CCW)
    C2_RADIUS = 2              # Raio de C2 (5 números)
    C3_RADIUS = 2              # Raio de C3 (5 números)
    
    def __init__(self):
        super().__init__(name="M15-ADA", num_neighbors=3)  # C1 mantém raio 3
        self.min_forces = 3
        self.default_window = 7
        self.decay = 0.8
        self.description = "Adaptive Dual Algorithm, Triple Focus 17 números"
        # Estado adaptativo
        self.cw_ema = self.CW_EMA_INIT
        self.ccw_history: List[Tuple[int, int]] = []
    
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
        
        # Filtrar forças válidas (>0) para max/min — BUG-T02 fix
        valid_forces = [f for f in forces if f > 0]
        if len(valid_forces) < 2:
            valid_forces = forces
        
        # BUG-E4: Flag forças anômalas (>30) — possível erro de captura
        flagged = []
        for i, f in enumerate(valid_forces):
            if f > self.MAX_FORCE_THRESHOLD:
                flagged.append(f)
                valid_forces[i] = max(1, 37 - f)  # Inversão suave
        
        # BUG-E5: Fallback SDA-19 quando <5 forças válidas (early-session)
        # M-08: Ativado quando valid_forces < 5 (início de sessão ou muitas anomalias).
        # Usa 1 centro (mediana) + 9 vizinhos = 19 números contíguos (~51% da roda).
        # Hit rate observado: ~52% vs ~61% do SDA-21 Triple Focus.
        # É geometricamente diferente: 1 arco largo vs 3 arcos curtos.
        if len(valid_forces) < 5:
            c1 = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)
            numbers = sorted(self.get_neighbors(c1, 9, wheel_sequence))
            return StrategyResult(
                should_bet=True,
                numbers=numbers,
                center=c1,
                score=pred_info.get("score", 3),
                visual=f"[{c1}] (SDA-19)",
                details={
                    "forces": forces,
                    "predicted_force": predicted_force,
                    "original_prediction": original_force,
                    "method": "fallback_sda19",
                    "centers": [c1],
                    "forces_used": {"median": predicted_force},
                    "unique_count": len(numbers),
                    "overlap": 0,
                    "clean_count": pred_info.get("clean_count", 0),
                    "outliers_removed": pred_info.get("outliers_removed", 0),
                    "spread": pred_info.get("spread", 0),
                    "drift": pred_info.get("drift", 0),
                    "survival_rate": pred_info.get("survival_rate", 1.0),
                    "calibration": calibration,
                    "flagged_forces": flagged
                }
            )
        
        # === M15-ADA: Triple Focus com offset adaptativo ===
        c1 = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)
        
        # Offset adaptativo baseado na direção
        offset = self._get_adaptive_offset(timeline.direction)
        
        # C2 e C3 posicionados simetricamente em relação a C1
        c1_idx = self._wheel_index(c1, wheel_sequence)
        wheel_size = len(wheel_sequence)
        c2 = wheel_sequence[(c1_idx + offset) % wheel_size]
        c3 = wheel_sequence[(c1_idx - offset) % wheel_size]
        
        # Agregar números com raios assimétricos
        nums = set()
        nums |= set(self.get_neighbors(c1, self.num_neighbors, wheel_sequence))  # 7 nums
        nums |= set(self.get_neighbors(c2, self.C2_RADIUS, wheel_sequence))      # 5 nums
        nums |= set(self.get_neighbors(c3, self.C3_RADIUS, wheel_sequence))      # 5 nums
        numbers = sorted(nums)  # Esperado: 17 (pode ser menos se houver overlap)
        
        visual = f"[{c1}] [{c2}] [{c3}]"
        
        return StrategyResult(
            should_bet=True,
            numbers=numbers,
            center=c1,
            score=pred_info.get("score", 3),
            visual=visual,
            details={
                "forces": forces,
                "predicted_force": predicted_force,
                "original_prediction": original_force,
                "method": "m15_ada_adaptive_triple_focus",
                "centers": [c1, c2, c3],
                "forces_used": {"median": predicted_force},
                "unique_count": len(numbers),
                "overlap": (7 + 5 + 5) - len(numbers),
                "clean_count": pred_info.get("clean_count", 0),
                "outliers_removed": pred_info.get("outliers_removed", 0),
                "spread": pred_info.get("spread", 0),
                "drift": pred_info.get("drift", 0),
                "survival_rate": pred_info.get("survival_rate", 1.0),
                "calibration": calibration,
                "flagged_forces": flagged,
                "offset": offset,
                "offset_type": "errdriven" if timeline.direction in ("cw", "horario") else "bayesian",
                "cw_ema": round(self.cw_ema, 2),
                "ccw_history_size": len(self.ccw_history),
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
            # BUG-28-12/M-09: clean é indexado por posição original (idx 0 = mais recente).
            # sorted ascending by idx → [:3] captura os 3 mais recentes (idx 0, 1, 2).
            # diffs[i] = force[i] - force[i+1] = mais_recente - menos_recente
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
    
    def _get_adaptive_offset(self, direction: str) -> int:
        """
        Retorna offset adaptativo baseado na direção.
        CW: ErrDriven (EMA de erro) — converge para offsets menores (8-10)
        CCW: Bayesiano retrospectivo — converge para offsets maiores (14-15)
        """
        if direction in ("cw", "horario"):
            return max(self.CW_OFFSET_MIN, min(self.CW_OFFSET_MAX, round(self.cw_ema)))
        else:
            return self._bayesian_offset()
    
    def _bayesian_offset(self) -> int:
        """Bayesiano: testa todos offsets contra janela recente, retorna o melhor."""
        if len(self.ccw_history) < self.CCW_WARMUP:
            return self.CCW_DEFAULT_OFFSET
        
        window = self.ccw_history[-self.CCW_WINDOW:]
        best_off = self.CCW_DEFAULT_OFFSET
        best_hits = -1
        
        for test_off in range(self.CCW_OFFSET_MIN, self.CCW_OFFSET_MAX + 1):
            hits = 0
            for c1, result in window:
                c1_idx = self._wheel_index(c1, self._wheel)
                c2 = self._wheel[(c1_idx + test_off) % len(self._wheel)]
                c3 = self._wheel[(c1_idx - test_off) % len(self._wheel)]
                coverage = set(self.get_neighbors(c1, self.num_neighbors, self._wheel))
                coverage |= set(self.get_neighbors(c2, self.C2_RADIUS, self._wheel))
                coverage |= set(self.get_neighbors(c3, self.C3_RADIUS, self._wheel))
                if result in coverage:
                    hits += 1
            if hits > best_hits:
                best_hits = hits
                best_off = test_off
        
        return best_off
    
    def update_adaptive(self, direction: str, c1: int, actual_result: int,
                        wheel_sequence: List[int]) -> None:
        """
        Atualiza estado adaptativo após resultado conhecido.
        Deve ser chamado APÓS check_prediction() e ANTES de analyze() do próximo spin.
        """
        self._wheel = wheel_sequence
        if direction in ("cw", "horario"):
            error = self._circ_dist(c1, actual_result, wheel_sequence)
            self.cw_ema = self.CW_ALPHA * error + (1 - self.CW_ALPHA) * self.cw_ema
        else:
            self.ccw_history.append((c1, actual_result))
            max_history = self.CCW_WINDOW * 2
            if len(self.ccw_history) > max_history:
                self.ccw_history = self.ccw_history[-max_history:]
    
    def get_adaptive_state(self) -> Dict[str, Any]:
        """Retorna estado adaptativo para persistência."""
        return {
            "cw_ema": self.cw_ema,
            "ccw_history": self.ccw_history
        }
    
    def load_adaptive_state(self, state: Dict[str, Any]) -> None:
        """Carrega estado adaptativo de persistência."""
        self.cw_ema = state.get("cw_ema", self.CW_EMA_INIT)
        self.ccw_history = [tuple(x) if isinstance(x, list) else x 
                           for x in state.get("ccw_history", [])]
    
    def _circ_dist(self, a: int, b: int, wheel_sequence: List[int]) -> int:
        """Distância circular entre dois números na roda."""
        try:
            a_pos = wheel_sequence.index(a)
            b_pos = wheel_sequence.index(b)
            wheel_size = len(wheel_sequence)
            return min((a_pos - b_pos) % wheel_size, (b_pos - a_pos) % wheel_size)
        except ValueError:
            return 12  # Fallback conservador
    
    def _wheel_index(self, number: int, wheel_sequence: List[int]) -> int:
        """Retorna o índice de um número na sequência da roda."""
        try:
            return wheel_sequence.index(number)
        except ValueError:
            return 0
    
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
    


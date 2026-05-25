# Roleta Cloud - M15-ADA Strategy (IQR + Weighted Median + Drift + Adaptive Triple Focus)
# Quick Wins v4.4 — INV-3 compliant (aposta a toda jogada):
#   QW-1/2 modulam stake fora daqui (state/game.py + server/message_handler.py).
#   QW-4 (Hot Substitution), QW-6 (Warmup Adaptativo) e QW-7 (Drift Freeze)
#   vivem dentro desta estratégia e NUNCA suprimem aposta — apenas trocam offsets
#   ou postergam adaptação. should_bet permanece governado SOMENTE pela
#   suficiência de forças (legado pré-Quick Wins).

import math
import logging
from typing import List, Tuple, Dict, Any, Optional
from statistics import median, quantiles
from state.timeline import Timeline
from .base import StrategyBase, StrategyResult
from app_config.strategy_config import get_strategy_config

logger = logging.getLogger(__name__)


class SDA17Strategy(StrategyBase):
    """
    Estratégia M15-ADA v4.3: M02-PctSigmoid — Triple Focus 17 números.
    
    Pipeline otimizado (v4.3 — M02-PctSigmoid + Warmup Reduzido):
    1. Janela Adaptativa (7→5→3→2 forças) — warmup reduzido de 5→2
    2. IQR Outlier Rejection (statistics.quantiles)
    3. Weighted Median (peso exponencial nas mais recentes)
    4. Drift Detection (sobre dados limpos pós-IQR)
    5. Smart Score (survival_rate × tightness)
    6. Adaptive Triple Focus — M02-PctSigmoid:
       - C1: mediana ponderada, raio 3 (7 números) — FIXO
       - C2/C3: offset variável por Sigmoid Dampened Error Feedback
       - CW e CCW: Mesmo algoritmo, parâmetros INDEPENDENTES
       - Hit: tighten 8% em direção a center=10
       - Miss: sigmoid(error_pct) × 2.0, direction-aware (100%/30%)
    7. v4.3 Melhorias sobre v4.2:
       - M02-PctSigmoid substitui Bayesian brute-force (O(1) vs O(n×m))
       - Warmup reduzido: Triple Focus a partir de 2 jogadas (era 5)
       - Anti-drift nativo via sigmoid saturation (max ±2 posições/jogada)
       - Sem necessidade de momentum limiter ou symmetry cap externo
       - BAYESIAN_DEFAULT: 12→10 (centro ótimo confirmado por oracle analysis)
    
    Cobertura: 17 números (7+5+5) = 45.9% da roda
    Break-even: 47.2% (vs 58.3% do SDA-21)
    Performance projetada: CW ~54%, CCW ~46% (simulação 100 jogadas reais)
    """
    
    # Forças acima deste limiar são sinalizadas como anômalas
    MAX_FORCE_THRESHOLD = 30

    # M15-ADA v4.3: Constantes (CW e CCW usam os mesmos valores)
    BAYESIAN_WINDOW = 12       # Janela de histórico para cálculo (legacy, usado no brute-force)
    BAYESIAN_DEFAULT = 10      # Offset padrão durante warm-up (v4.3: 12→10, oracle ótimo)
    BAYESIAN_WARMUP = 2        # Jogadas mínimas antes de adaptar (v4.3: 5→2)
    OFFSET_MIN = 7             # Offset mínimo candidato
    OFFSET_MAX = 13            # Offset máximo candidato
    ERROR_DECAY = 0.08         # Sensibilidade do vetor de erro (legacy v4.2)
    ERROR_THRESHOLD = 7        # Só conta erros significativos (legacy v4.2)
    PRIOR_CENTER = 10          # Centro de atração dos offsets
    PRIOR_STRENGTH = 0.5       # Peso do prior (legacy v4.2)
    MAX_HISTORY = 24           # 2× BAYESIAN_WINDOW para buffer
    C2_RADIUS = 2              # Raio de C2 (5 números)
    C3_RADIUS = 2              # Raio de C3 (5 números)
    MAX_DELTA_OFFSET = 2       # Legacy v4.2 (não usado por M02)
    SYMMETRY_CAP = 4           # Legacy v4.2 (não usado por M02)
    
    # v4.3: M02-PctSigmoid — Controlador variável C2/C3
    SIGMOID_K = 6              # Curvatura da sigmoid (controla dampening)
    SIGMOID_SCALE = 2.0        # Escala máxima do ajuste (posições por jogada)
    HIT_TIGHTEN = 0.08         # Taxa de retorno ao centro após acerto (8%)
    MISS_CROSS_RATE = 0.3      # Taxa de ajuste contra-direcional (30%)
    
    def __init__(self):
        super().__init__(name="M15-ADA", num_neighbors=3)  # C1 mantém raio 3
        self.min_forces = 2    # v4.3: reduzido de 3→2 para warmup mais rápido
        self.default_window = 7
        self.decay = 0.8
        self.description = "M02-PctSigmoid v4.4 (QW INV-3), Triple Focus 17 números"
        # Estado adaptativo — históricos INDEPENDENTES por direção
        self.cw_history: List[Tuple[int, int]] = []
        self.ccw_history: List[Tuple[int, int]] = []
        self._wheel: List[int] = []
        # v4.2 legacy: Momentum limiter (mantido para backward compat, não usado por M02)
        self._last_offset: Dict[str, int] = {}
        # v4.3: M02-PctSigmoid — offsets float independentes por direção
        self._sigmoid_off: Dict[str, float] = {}

        # ===== v4.4 Quick Wins =====
        # Buffer rolling de hits por direção (INV-1: estado dual isolado).
        # Usado por QW-1 (minimizer), QW-2 (weight), QW-6 (warmup), QW-7 (drift).
        self._recent_hits: Dict[str, List[int]] = {"cw": [], "ccw": []}
        # QW-4 — Hot Center Substitution: cooldown por (direção, slot).
        self._cooldown: Dict[str, Dict[str, int]] = {
            "cw":  {"c2": 0, "c3": 0},
            "ccw": {"c2": 0, "c3": 0},
        }
        # QW-7 — contador de spins restantes em freeze por direção.
        self._drift_freeze: Dict[str, int] = {"cw": 0, "ccw": 0}
        # QW-3 — métrica de resets de martingale (preenchida externamente, mas vive aqui
        # para persistir no adaptive_state).
        self._mg_resets: Dict[str, int] = {"cw": 0, "ccw": 0}
        # Config TOML — carregada uma vez (singleton).
        self._cfg = get_strategy_config()
    
    def analyze(
        self,
        timeline: Timeline,
        last_number: int,
        wheel_sequence: List[int],
        calibration: int = 0,
        error_history: List[int] = None
    ) -> StrategyResult:
        """Analisa timeline e prediz próxima força usando pipeline robusto."""

        # v4.4 QW-5: reload config TOML se mtime mudou (custo: 1 stat call).
        try:
            self._cfg.maybe_reload()
        except Exception as _e:
            logger.debug("[STRATEGY-CFG] maybe_reload falhou (não-fatal): %s", _e)

        # BUG-TASK-004 FIX: Garantir _wheel disponível antes do Bayesiano
        if wheel_sequence and not self._wheel:
            self._wheel = wheel_sequence
        
        # Janela adaptativa: tenta 7, depois 5, depois 3, depois 2 (v4.3: min=2)
        predicted_force = None
        pred_info = {}
        
        for window in [self.default_window, 5, 3, self.min_forces]:
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
        
        # BUG-E5: Fallback SDA-19 quando <2 forças válidas (v4.3: 5→2)
        # Ativado apenas na primeiríssima jogada de cada sentido.
        # Usa 1 centro (mediana) + 9 vizinhos = 19 números contíguos (~51% da roda).
        if len(valid_forces) < 2:
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
        
        # === M15-ADA v4.1: Triple Focus com offset ASSIMÉTRICO ===
        c1 = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)
        
        # Offsets adaptativos assimétricos (M04 Error-Vector)
        off_c2, off_c3 = self._get_adaptive_offset(timeline.direction)
        
        # C2 e C3 posicionados ASSIMETRICAMENTE em relação a C1
        c1_idx = self._wheel_index(c1, wheel_sequence)
        wheel_size = len(wheel_sequence)
        c2 = wheel_sequence[(c1_idx + off_c2) % wheel_size]
        c3 = wheel_sequence[(c1_idx - off_c3) % wheel_size]
        
        # Agregar números com raios assimétricos
        nums = set()
        nums |= set(self.get_neighbors(c1, self.num_neighbors, wheel_sequence))  # 7 nums
        nums |= set(self.get_neighbors(c2, self.C2_RADIUS, wheel_sequence))      # 5 nums
        nums |= set(self.get_neighbors(c3, self.C3_RADIUS, wheel_sequence))      # 5 nums
        numbers = sorted(nums)  # Esperado: 17 (pode ser menos se houver overlap)
        
        # BUG-NEW-002 FIX: Alerta se cobertura abaixo do esperado
        if len(numbers) < 15:
            logger.warning(
                f"Cobertura baixa: {len(numbers)} números (off_c2={off_c2}, off_c3={off_c3}, "
                f"C1={c1}, C2={c2}, C3={c3})"
            )
        
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
                "offset": off_c2,
                "offset_c3": off_c3,
                "offset_type": "sigmoid",
                "cw_history_size": len(self.cw_history),
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
        
        # BUG-AUDIT-008 FIX: Guardar contra lista vazia
        if n == 0:
            return (0, {"clean_count": 0, "outliers_removed": 0, "spread": 0,
                        "drift": 0, "score": 1, "survival_rate": 0})
        
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
    
    def _get_adaptive_offset(self, direction: str) -> Tuple[int, int]:
        """
        Retorna offsets adaptativos ASSIMÉTRICOS (off_c2, off_c3).
        v4.3: M02-PctSigmoid — lê offsets float do estado sigmoid.
        v4.4: QW-4 — aplica Hot Center Substitution (TROCA por offset alternativo
        quando slot está em cooldown). INV-3: nunca pula; só altera quais números
        compõem C2/C3.
        Parâmetros independentes por direção — históricos não se misturam.
        """
        dir_key = "cw" if direction in ("cw", "horario") else "ccw"
        off2_raw = self._sigmoid_off.get(f"{dir_key}_off2", float(self.BAYESIAN_DEFAULT))
        off3_raw = self._sigmoid_off.get(f"{dir_key}_off3", float(self.BAYESIAN_DEFAULT))
        off2 = max(self.OFFSET_MIN, min(self.OFFSET_MAX, round(off2_raw)))
        off3 = max(self.OFFSET_MIN, min(self.OFFSET_MAX, round(off3_raw)))
        # QW-4 substitution
        off2 = self._get_effective_offset(dir_key, "c2", off2)
        off3 = self._get_effective_offset(dir_key, "c3", off3)
        return off2, off3
    
    def _bayesian_error_vector(self, history: List[Tuple[int, int]]) -> Tuple[int, int]:
        """
        M04+M10 Hybrid: Error-Vector com Prior Gaussiano.
        
        M04 calcula viés direcional dos erros recentes para gerar
        offsets assimétricos (off_c2 ≠ off_c3).
        M10 aplica prior Gaussiano centrado em PRIOR_CENTER como regularizador.
        
        Returns:
            (off_c2, off_c3) — offsets para posicionar C2 (sentido +) e C3 (sentido -)
        """
        if not self._wheel or len(history) < self.BAYESIAN_WARMUP:
            return self.BAYESIAN_DEFAULT, self.BAYESIAN_DEFAULT
        
        window = history[-self.BAYESIAN_WINDOW:]
        wheel_size = len(self._wheel)
        
        # --- M04: Calcular viés direcional dos erros ---
        bias_pos = 0.0  # Viés no sentido + (horário na roda)
        bias_neg = 0.0  # Viés no sentido - (anti-horário na roda)
        
        for c1, result in window:
            dist = self._circ_dist(c1, result, self._wheel)
            if dist > self.ERROR_THRESHOLD:
                direction = self._circ_dir(c1, result, self._wheel)
                if direction > 0:
                    bias_pos += dist * self.ERROR_DECAY
                elif direction < 0:
                    bias_neg += dist * self.ERROR_DECAY
        
        # --- Brute-force Bayesiano como base ---
        base_off = self._bayesian_brute_force(history)
        
        # --- M04: Aplicar viés direcional ---
        off2_raw = base_off + bias_pos - bias_neg
        off3_raw = base_off + bias_neg - bias_pos
        
        # --- M10: Regularização pelo Prior Gaussiano ---
        data_weight = 1.0 - self.PRIOR_STRENGTH
        off2 = round(off2_raw * data_weight + self.PRIOR_CENTER * self.PRIOR_STRENGTH)
        off3 = round(off3_raw * data_weight + self.PRIOR_CENTER * self.PRIOR_STRENGTH)
        
        # Clamp dentro dos limites
        off2 = max(self.OFFSET_MIN, min(self.OFFSET_MAX, off2))
        off3 = max(self.OFFSET_MIN, min(self.OFFSET_MAX, off3))
        
        # v4.2: Symmetry cap — limita divergência entre off_c2 e off_c3
        if abs(off2 - off3) > self.SYMMETRY_CAP:
            off2_bigger = off2 > off3
            avg = (off2 + off3) / 2
            half_cap = self.SYMMETRY_CAP / 2
            off2 = round(avg + half_cap) if off2_bigger else round(avg - half_cap)
            off3 = round(avg - half_cap) if off2_bigger else round(avg + half_cap)
            off2 = max(self.OFFSET_MIN, min(self.OFFSET_MAX, off2))
            off3 = max(self.OFFSET_MIN, min(self.OFFSET_MAX, off3))
        
        return off2, off3
    
    def _bayesian_brute_force(self, history: List[Tuple[int, int]]) -> int:
        """Bayesiano brute-force: testa todos offsets contra janela recente, retorna o melhor."""
        if not self._wheel or len(history) < self.BAYESIAN_WARMUP:
            return self.BAYESIAN_DEFAULT
        
        window = history[-self.BAYESIAN_WINDOW:]
        best_off = self.BAYESIAN_DEFAULT
        best_hits = -1
        
        for test_off in range(self.OFFSET_MIN, self.OFFSET_MAX + 1):
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
    
    def _circ_dir(self, a: int, b: int, wheel_sequence: List[int]) -> int:
        """
        Direção circular de a para b na roda.
        Retorna +1 se b está no sentido horário, -1 se anti-horário, 0 se coincide.
        """
        try:
            a_pos = wheel_sequence.index(a)
            b_pos = wheel_sequence.index(b)
            wheel_size = len(wheel_sequence)
            cw_dist = (b_pos - a_pos) % wheel_size
            ccw_dist = (a_pos - b_pos) % wheel_size
            if cw_dist == 0:
                return 0
            return 1 if cw_dist <= ccw_dist else -1
        except ValueError:
            return 0
    
    # ================================================================== #
    # ===================== v4.4 Quick Wins helpers ==================== #
    # ================================================================== #
    @staticmethod
    def _dk(direction: str) -> str:
        """Normaliza direção para chave interna ('cw' | 'ccw'). Aceita aliases."""
        return "cw" if direction in ("cw", "horario") else "ccw"

    def _recent_hit_rate(self, direction: str) -> Optional[float]:
        """
        Rolling hit rate da janela mais recente (config: sda17.minimizer.window).
        Retorna None enquanto warmup (< warmup_n amostras). INV-1 isolado por direção.
        """
        dk = self._dk(direction)
        h = self._recent_hits[dk]
        warmup_n = int(self._cfg.get("sda17.minimizer", "warmup_n", 10))
        if len(h) < warmup_n:
            return None
        window = int(self._cfg.get("sda17.minimizer", "window", 30))
        sample = h[-window:]
        return sum(sample) / len(sample)

    def should_minimize(self, direction: str) -> Tuple[bool, Optional[float]]:
        """
        QW-1 — decisão de minimizer (stake mínimo + force level=1).
        Retorna (minimize, rolling_rate). NUNCA pula aposta (INV-3 garantido em
        message_handler — este método só informa).
        """
        if not self._cfg.get("sda17.minimizer", "enabled", True):
            return False, None
        rate = self._recent_hit_rate(direction)
        if rate is None:
            return False, None
        thr = float(self._cfg.get("sda17.minimizer", "threshold", 0.487))
        return rate < thr, rate

    def get_stake_weight(self, direction: str) -> float:
        """
        QW-2 — peso direcional contínuo para stake quando level=1.
        Retorna 1.0 se desabilitado, warmup ou sem dados.
        Aplicado apenas em level=1 (mg=0) pelo caller (game.py).
        """
        if not self._cfg.get("sda17.stake_weight", "enabled", True):
            return 1.0
        rate = self._recent_hit_rate(direction)
        if rate is None:
            return 1.0
        sw = self._cfg.section("sda17.stake_weight")
        try:
            div = float(sw.get("divisor", 0.472)) or 0.472
            return min(float(sw.get("cap_upper", 1.5)),
                       max(float(sw.get("cap_lower", 0.3)), rate / div))
        except Exception:
            return 1.0

    def get_mg_max(self, direction: str) -> int:
        """
        QW-3 — cap máximo por direção (informativo; cap real já é 3 no BET_VALUES).
        Mantido por compat com plano e métricas; valores < 3 podem ser usados
        pelo advisor para escalação conservadora.
        """
        rate = self._recent_hit_rate(direction)
        if rate is None:
            return 3
        if rate >= 0.60:
            return 3
        if rate >= 0.50:
            return 2
        return 1  # rate baixo: nunca escala

    def _get_warmup(self, direction: str) -> int:
        """QW-6 — warmup adaptativo (ganhando=2, perdendo=5)."""
        if not self._cfg.get("sda17.warmup_adaptive", "enabled", True):
            return self.BAYESIAN_WARMUP
        rate = self._recent_hit_rate(direction)
        if rate is None:
            return self.BAYESIAN_WARMUP
        div = float(self._cfg.get("sda17.stake_weight", "divisor", 0.472))
        if rate > div:
            return int(self._cfg.get("sda17.warmup_adaptive", "warmup_winning", 2))
        return int(self._cfg.get("sda17.warmup_adaptive", "warmup_losing", 5))

    def _get_effective_offset(self, dk: str, slot: str, base_off: int) -> int:
        """
        QW-4 — Hot Center Substitution. Se slot está em cooldown, troca por
        offset alternativo (delta ±1 em direção oposta ao prior). Sempre devolve
        offset válido — INV-3 garantido (nunca pula aposta).
        """
        if not self._cfg.get("sda17.hot_substitution", "enabled", True):
            return base_off
        cd = self._cooldown.get(dk, {}).get(slot, 0)
        if cd <= 0:
            return base_off
        alt = base_off + (1 if base_off < self.PRIOR_CENTER else -1)
        return max(self.OFFSET_MIN, min(self.OFFSET_MAX, alt))

    def _detect_drift(self, dk: str) -> bool:
        """QW-7 — drift detector simples (diff de hit_rate metade1 vs metade2)."""
        if not self._cfg.get("sda17.drift_freeze", "enabled", True):
            return False
        win = int(self._cfg.get("sda17.drift_freeze", "window", 50))
        h = self._recent_hits[dk]
        if len(h) < win:
            return False
        half = win // 2
        early = sum(h[-win:-half]) / half
        late = sum(h[-half:]) / half
        thr = float(self._cfg.get("sda17.drift_freeze", "threshold", 0.15))
        return abs(early - late) > thr

    def record_mg_reset(self, direction: str) -> None:
        """QW-3 — métrica de reset martingale. Chamado externamente."""
        self._mg_resets[self._dk(direction)] += 1

    # ================================================================== #

    def _pct_sigmoid_update(self, direction: str, c1: int, actual_result: int) -> None:
        """
        M02-PctSigmoid: Atualiza offsets C2/C3 com feedback sigmoid dampened.

        v4.4 QW pipeline (ordem importa):
          1. Decay cooldowns (QW-4)
          2. Calcula is_hit (compat legacy)
          3. Empurra hit em _recent_hits (alimenta QW-1/2/3/6/7)
          4. Marca cooldown se C2 ou C3 hitou (QW-4)
          5. Drift freeze pipeline (QW-7): se em freeze, decrementa e talvez
             soft-reset; se detectar drift novo, entra em freeze e NÃO adapta
             nesse spin (mas a aposta já foi emitida — INV-3 ok)
          6. Adaptação sigmoid normal (legacy)

        INV-1 isolado por direção (dk).
        """
        if not self._wheel:
            return

        dk = self._dk(direction)

        # ---- (1) Decay cooldowns ----
        for k in self._cooldown[dk]:
            if self._cooldown[dk][k] > 0:
                self._cooldown[dk][k] -= 1

        off2 = self._sigmoid_off.get(f"{dk}_off2", float(self.BAYESIAN_DEFAULT))
        off3 = self._sigmoid_off.get(f"{dk}_off3", float(self.BAYESIAN_DEFAULT))

        # Calcular cobertura atual (usa offsets EFETIVOS — mesmos vistos no analyze)
        o2_raw = max(self.OFFSET_MIN, min(self.OFFSET_MAX, round(off2)))
        o3_raw = max(self.OFFSET_MIN, min(self.OFFSET_MAX, round(off3)))
        o2 = self._get_effective_offset(dk, "c2", o2_raw)
        o3 = self._get_effective_offset(dk, "c3", o3_raw)
        c1_idx = self._wheel_index(c1, self._wheel)
        ws = len(self._wheel)
        c2 = self._wheel[(c1_idx + o2) % ws]
        c3 = self._wheel[(c1_idx - o3) % ws]
        c1_nbrs = set(self.get_neighbors(c1, self.num_neighbors, self._wheel))
        c2_nbrs = set(self.get_neighbors(c2, self.C2_RADIUS, self._wheel))
        c3_nbrs = set(self.get_neighbors(c3, self.C3_RADIUS, self._wheel))
        cov = c1_nbrs | c2_nbrs | c3_nbrs

        is_hit = actual_result in cov

        # ---- (3) Alimenta buffer rolling de hits ----
        self._recent_hits[dk].append(1 if is_hit else 0)
        if len(self._recent_hits[dk]) > 100:
            self._recent_hits[dk] = self._recent_hits[dk][-100:]

        # ---- (4) Cooldown trigger (QW-4) ----
        if is_hit and self._cfg.get("sda17.hot_substitution", "enabled", True):
            cd_spins = int(self._cfg.get("sda17.hot_substitution", "cooldown_spins", 3))
            # Prioridade: se caiu em C2 (não C1), marca c2; se caiu em C3 (não C1/C2), marca c3.
            if actual_result in c2_nbrs and actual_result not in c1_nbrs:
                self._cooldown[dk]["c2"] = cd_spins
            elif actual_result in c3_nbrs and actual_result not in c1_nbrs and actual_result not in c2_nbrs:
                self._cooldown[dk]["c3"] = cd_spins

        # ---- (5) Drift freeze pipeline (QW-7) ----
        if self._drift_freeze[dk] > 0:
            self._drift_freeze[dk] -= 1
            if self._drift_freeze[dk] == 0:
                # Soft reset: aproxima do default
                w = float(self._cfg.get("sda17.drift_freeze", "soft_reset_weight", 0.5))
                for suf in ("off2", "off3"):
                    cur = self._sigmoid_off.get(f"{dk}_{suf}", float(self.BAYESIAN_DEFAULT))
                    self._sigmoid_off[f"{dk}_{suf}"] = w * cur + (1.0 - w) * self.BAYESIAN_DEFAULT
                logger.info("[DRIFT-RESET] dir=%s soft-reset aplicado", dk)
            return  # não adapta durante freeze

        if self._detect_drift(dk):
            self._drift_freeze[dk] = int(self._cfg.get("sda17.drift_freeze", "freeze_spins", 5))
            logger.warning("[DRIFT-DETECTED] dir=%s freezing %d spins",
                           dk, self._drift_freeze[dk])
            return

        # ---- (6) QW-6: warmup adaptativo ----
        warmup = self._get_warmup(direction)
        history_len = len(self.cw_history if dk == "cw" else self.ccw_history)
        if history_len < warmup:
            # Ainda em warmup adaptativo — não adapta offsets (mas buffer já foi alimentado).
            return

        # ---- (legacy) Adaptação sigmoid ----
        if is_hit:
            # Tighten: mover 8% em direção ao centro (10)
            off2 += (self.PRIOR_CENTER - off2) * self.HIT_TIGHTEN
            off3 += (self.PRIOR_CENTER - off3) * self.HIT_TIGHTEN
        else:
            # Calcular erro percentual
            min_dist = min(
                self._circ_dist(actual_result, n, self._wheel) for n in cov
            ) if cov else 18
            # BUG-AUDIT-007 FIX: Clampar min_dist ao raio máximo da roda
            min_dist = min(min_dist, 18)
            pct = min_dist / 18.0

            # Sigmoid dampening
            adj = (2.0 / (1.0 + math.exp(-self.SIGMOID_K * pct)) - 1.0) * self.SIGMOID_SCALE

            # Direção do erro
            err_dir = self._circ_dir(c1, actual_result, self._wheel)

            if err_dir > 0:  # Resultado está no sentido CW da roda
                off2 += adj
                off3 -= adj * self.MISS_CROSS_RATE
            elif err_dir < 0:  # Resultado está no sentido CCW
                off3 += adj
                off2 -= adj * self.MISS_CROSS_RATE
            else:
                off2 += adj * 0.5
                off3 += adj * 0.5

        # ---- S-STRAT-1: Regularizador anti-drift ----
        # Estudo live (260 decisões, 2026-05-25): offset=13 entregou 34.8% acc
        # vs 50%+ para offsets 10-12. O sigmoid permitia drift até a borda.
        # Quando |off - PRIOR_CENTER| > REG_BAND, puxa de volta para o prior
        # com taxa REG_RATE adicional ao passo sigmoid normal.
        reg_band = float(self.PRIOR_CENTER) + 2.0  # 12
        reg_band_low = float(self.PRIOR_CENTER) - 2.0  # 8
        reg_rate = 0.20
        for _name, _val in (("off2", off2), ("off3", off3)):
            pass  # placeholder para clareza
        if off2 > reg_band or off2 < reg_band_low:
            off2 += (self.PRIOR_CENTER - off2) * reg_rate
        if off3 > reg_band or off3 < reg_band_low:
            off3 += (self.PRIOR_CENTER - off3) * reg_rate

        # Clamp
        off2 = max(float(self.OFFSET_MIN), min(float(self.OFFSET_MAX), off2))
        off3 = max(float(self.OFFSET_MIN), min(float(self.OFFSET_MAX), off3))

        self._sigmoid_off[f"{dk}_off2"] = off2
        self._sigmoid_off[f"{dk}_off3"] = off3
    
    def update_adaptive(self, direction: str, c1: int, actual_result: int,
                        wheel_sequence: List[int]) -> None:
        """
        Atualiza estado adaptativo após resultado conhecido.
        v4.3: Atualiza histórico + chama M02-PctSigmoid para ajustar offsets.
        Deve ser chamado APÓS check_prediction() e ANTES de analyze() do próximo spin.
        """
        self._wheel = wheel_sequence
        if direction in ("cw", "horario"):
            self.cw_history.append((c1, actual_result))
            if len(self.cw_history) > self.MAX_HISTORY:
                self.cw_history = self.cw_history[-self.MAX_HISTORY:]
        else:
            self.ccw_history.append((c1, actual_result))
            if len(self.ccw_history) > self.MAX_HISTORY:
                self.ccw_history = self.ccw_history[-self.MAX_HISTORY:]
        
        # v4.3: M02-PctSigmoid feedback
        self._pct_sigmoid_update(direction, c1, actual_result)
    
    def get_adaptive_state(self) -> Dict[str, Any]:
        """Retorna estado adaptativo para persistência (v1.7 — Quick Wins INV-3)."""
        return {
            "cw_history": self.cw_history,
            "ccw_history": self.ccw_history,
            "last_offset": self._last_offset,
            "sigmoid_off": self._sigmoid_off,
            # v4.4 Quick Wins
            "recent_hits": self._recent_hits,
            "cooldown": self._cooldown,
            "drift_freeze": self._drift_freeze,
            "mg_resets": self._mg_resets,
            "version": "1.7",
        }

    def load_adaptive_state(self, state: Dict[str, Any]) -> None:
        """Carrega estado adaptativo de persistência com validação.
        Compatível com v4.0.x (cw_ema), v4.1.x (sem last_offset), v4.2.x (sem sigmoid_off),
        v4.3.x (sem buffers Quick Wins)."""
        for key in ("cw_history", "ccw_history"):
            raw = state.get(key, [])
            validated = []
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    try:
                        validated.append((int(item[0]), int(item[1])))
                    except (ValueError, TypeError):
                        continue
            if key == "cw_history":
                self.cw_history = validated
            else:
                self.ccw_history = validated
        # v4.2 legacy: Restaurar último offset (backward compat)
        raw_lo = state.get("last_offset", {})
        if isinstance(raw_lo, dict):
            self._last_offset = {k: int(v) for k, v in raw_lo.items()
                                 if k in ("cw", "ccw") and isinstance(v, (int, float))}
        # v4.3: Restaurar offsets sigmoid (backward compat: default CENTER=10)
        raw_sig = state.get("sigmoid_off", {})
        if isinstance(raw_sig, dict):
            valid_keys = {"cw_off2", "cw_off3", "ccw_off2", "ccw_off3"}
            self._sigmoid_off = {k: float(v) for k, v in raw_sig.items()
                                 if k in valid_keys and isinstance(v, (int, float))}
        # v4.4 Quick Wins: restaurar buffers (defaults seguros se ausente — sem
        # crash em restart noturno se vier de v4.3.x).
        raw_rh = state.get("recent_hits", {})
        if isinstance(raw_rh, dict):
            for dk in ("cw", "ccw"):
                v = raw_rh.get(dk, [])
                if isinstance(v, list):
                    self._recent_hits[dk] = [int(x) for x in v if x in (0, 1)][-100:]
        raw_cd = state.get("cooldown", {})
        if isinstance(raw_cd, dict):
            for dk in ("cw", "ccw"):
                sub = raw_cd.get(dk, {})
                if isinstance(sub, dict):
                    for slot in ("c2", "c3"):
                        try:
                            self._cooldown[dk][slot] = max(0, int(sub.get(slot, 0)))
                        except (ValueError, TypeError):
                            pass
        raw_df = state.get("drift_freeze", {})
        if isinstance(raw_df, dict):
            for dk in ("cw", "ccw"):
                try:
                    self._drift_freeze[dk] = max(0, int(raw_df.get(dk, 0)))
                except (ValueError, TypeError):
                    pass
        raw_mg = state.get("mg_resets", {})
        if isinstance(raw_mg, dict):
            for dk in ("cw", "ccw"):
                try:
                    self._mg_resets[dk] = max(0, int(raw_mg.get(dk, 0)))
                except (ValueError, TypeError):
                    pass
    
    def _circ_dist(self, a: int, b: int, wheel_sequence: List[int]) -> int:
        """Distância circular entre dois números na roda."""
        try:
            a_pos = wheel_sequence.index(a)
            b_pos = wheel_sequence.index(b)
            wheel_size = len(wheel_sequence)
            return min((a_pos - b_pos) % wheel_size, (b_pos - a_pos) % wheel_size)
        except ValueError:
            # BUG-NEW-004 FIX: Logar fallback para diagnóstico
            logger.warning(f"_circ_dist: número inválido na roda (a={a}, b={b}), fallback=12")
            return 12
    
    def _wheel_index(self, number: int, wheel_sequence: List[int]) -> int:
        """Retorna o índice de um número na sequência da roda."""
        try:
            return wheel_sequence.index(number)
        except ValueError:
            # BUG-NEW-003 FIX: Logar fallback para diagnóstico
            logger.warning(f"_wheel_index: número {number} não encontrado na roda, fallback=0")
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
    


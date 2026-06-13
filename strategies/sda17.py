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

        # SP-26 ML-02: prior bayesiano configurável via env SDA_OFFSET_PRIOR.
        # Default mantém comportamento atual (BAYESIAN_DEFAULT=10, PRIOR_CENTER=10).
        # "bayesian_plus3" shifta para 13 (descoberta: dealers handra-shifted).
        # Validar com backtest antes de promover (criterio: lift >=+1pp HR).
        import os as _os
        _prior_mode = (_os.environ.get("SDA_OFFSET_PRIOR", "") or "").strip().lower()
        self._offset_prior_mode = _prior_mode
        if _prior_mode == "bayesian_plus3":
            self.BAYESIAN_DEFAULT = self.BAYESIAN_DEFAULT + 3  # 10->13
            self.PRIOR_CENTER = self.PRIOR_CENTER + 3
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
        # S-STRAT-7 — Auto-tune batch (4 spins por sentido, isolado).
        # Contadores e histórico para tunelamento em lote, INDEPENDENTES por direção.
        self._pending_spins: Dict[str, int] = {"cw": 0, "ccw": 0}
        self._last_tune_ts: Dict[str, float] = {"cw": 0.0, "ccw": 0.0}
        self._batch_acc_history: Dict[str, List[Tuple[float, float, float]]] = {
            "cw": [], "ccw": []
        }  # (acc_last_4, acc_prev_4, delta) — máx 50 entradas por dir
        self._batch_pullback_total: Dict[str, int] = {"cw": 0, "ccw": 0}
        self._batch_runs_total: Dict[str, int] = {"cw": 0, "ccw": 0}
        self._batch_last_action: Dict[str, str] = {"cw": "init", "ccw": "init"}
        self._batch_last_delta: Dict[str, float] = {"cw": 0.0, "ccw": 0.0}
        # MELHORIA-G (12/06): EMA do erro circular assinado por região/sentido.
        # Telemetria para decidir o controlador por região (gated walk-forward).
        self._region_err_ema: Dict[str, Dict[str, Optional[float]]] = {
            "cw": {"c1": None, "c2": None, "c3": None},
            "ccw": {"c1": None, "c2": None, "c3": None},
        }
        # Auditoria r3: nº de amostras por slot — evita ler EMA jovem como sinal.
        self._region_err_n: Dict[str, Dict[str, int]] = {
            "cw": {"c1": 0, "c2": 0, "c3": 0},
            "ccw": {"c1": 0, "c2": 0, "c3": 0},
        }
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
        # B5 CUT-POLICY v1 (12/06): N=19 é tóxico (breakeven 52.8% vs hit real
        # 47.4% → −3.10u/aposta); sob a flag o fallback vira N=21 (raio 10,
        # breakeven 58.3% vs hit real 57.6% — quase neutro).
        if len(valid_forces) < 2:
            _fb_radius = self._fallback_radius()
            _fb_label = f"SDA-{2 * _fb_radius + 1}"
            c1 = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)
            numbers = sorted(self.get_neighbors(c1, _fb_radius, wheel_sequence))
            return StrategyResult(
                should_bet=True,
                numbers=numbers,
                center=c1,
                score=pred_info.get("score", 3),
                visual=f"[{c1}] ({_fb_label})",
                details={
                    "forces": forces,
                    "predicted_force": predicted_force,
                    "original_prediction": original_force,
                    "method": f"fallback_{_fb_label.lower().replace('-', '')}",
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

        # SV-01 (12/06) — Modelo Universal M5: shift do CONJUNTO pelo viés
        # EMA da região C1 (replay causal §6: único modelo saldo+ nos 4
        # quadrantes). Só no Triple Focus; warmup n>=3; zera no reset (P10).
        region_shift = 0
        dk_shift = self._dk(timeline.direction)
        if self._region_shift_enabled():
            region_shift = self._region_shift(dk_shift, "c1",
                                              self.REGION_SHIFT_CLAMP_C1)
            if region_shift:
                c1_idx_s = (self._wheel_index(c1, wheel_sequence) + region_shift) % len(wheel_sequence)
                c1 = wheel_sequence[c1_idx_s]

        # Offsets adaptativos assimétricos (M04 Error-Vector)
        off_c2, off_c3 = self._get_adaptive_offset(timeline.direction)

        # SV-01: correção fina RELATIVA dos satélites (EMA própria, clamp ±2).
        sat2 = sat3 = 0
        if self._region_shift_enabled():
            sat2 = self._region_shift(dk_shift, "c2", self.REGION_SHIFT_CLAMP_SAT)
            sat3 = -self._region_shift(dk_shift, "c3", self.REGION_SHIFT_CLAMP_SAT)
            off_c2 = max(self.OFFSET_MIN - 2, min(self.OFFSET_MAX + 2, off_c2 + sat2))
            off_c3 = max(self.OFFSET_MIN - 2, min(self.OFFSET_MAX + 2, off_c3 + sat3))

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
                "offset_type": "sigmoid" if self._sigmoid_satellites_enabled() else "prior_fixed",
                "region_shift": region_shift,
                "region_shift_sat": [sat2, sat3],
                "cw_history_size": len(self.cw_history),
                "ccw_history_size": len(self.ccw_history),
            }
        )

    # ================================================================== #
    # SV-01/SV-02 (12/06) — Modelo Universal M5 + aposentadoria do sigmoid
    # ================================================================== #
    REGION_SHIFT_K = 0.5         # ganho do integrador (replay causal §6)
    REGION_SHIFT_CLAMP_C1 = 4    # clamp do shift do conjunto
    REGION_SHIFT_CLAMP_SAT = 2   # clamp da correção relativa dos satélites
    REGION_SHIFT_MIN_N = 3       # warmup por sentido (P9-compatível)

    def _region_shift_enabled(self) -> bool:
        try:
            from app_config.settings import region_shift_v1_enabled
            return region_shift_v1_enabled()
        except Exception:  # noqa: BLE001
            return False

    def _sigmoid_satellites_enabled(self) -> bool:
        try:
            from app_config.settings import sigmoid_satellites_enabled
            return sigmoid_satellites_enabled()
        except Exception:  # noqa: BLE001
            return True  # comportamento legado em caso de falha de import

    def _region_shift(self, dk: str, slot: str, clamp: int) -> int:
        """M5: shift inteiro derivado da EMA de erro assinado do slot.

        REPLICA EXATA da dinâmica vencedora do replay (universal_model_sim
        M5): ``shift = clamp(round(−ema·K), ±clamp)`` com a EMA alimentada
        pelo erro RESIDUAL da aposta real (já é o caso em produção pós
        BUG-B). Não "corrigir" o sinal por intuição — o que foi validado em
        2762 decisões foi ESTA dinâmica, transiente incluído.
        """
        n = self._region_err_n.get(dk, {}).get(slot, 0)
        ema = self._region_err_ema.get(dk, {}).get(slot)
        if ema is None or n < self.REGION_SHIFT_MIN_N:
            return 0
        s = round(-ema * self.REGION_SHIFT_K)
        return max(-clamp, min(clamp, int(s)))

    def get_region_shift_snapshot(self) -> Dict[str, Any]:
        """Telemetria SV-01: shift corrente por sentido (p/ /api e overlay)."""
        out: Dict[str, Any] = {"enabled": self._region_shift_enabled()}
        for dk in ("cw", "ccw"):
            out[dk] = {
                "shift_c1": self._region_shift(dk, "c1", self.REGION_SHIFT_CLAMP_C1),
                "sat2": self._region_shift(dk, "c2", self.REGION_SHIFT_CLAMP_SAT),
                "sat3": -self._region_shift(dk, "c3", self.REGION_SHIFT_CLAMP_SAT),
                "ema_c1": (round(self._region_err_ema[dk]["c1"], 2)
                           if self._region_err_ema[dk]["c1"] is not None else None),
                "n_c1": self._region_err_n[dk]["c1"],
            }
        return out
    
    def _fallback_radius(self) -> int:
        """B5 CUT-POLICY v1 (12/06): raio do fallback de 1 centro.

        N=19 (raio 9) é tóxico — breakeven 52.8% vs hit real 47.4% =
        −3.10u/aposta. Sob a flag, fallback usa raio 10 (N=21, quase neutro).
        """
        try:
            from app_config.settings import profit_cut_v1_enabled
            return 10 if profit_cut_v1_enabled() else 9
        except Exception:
            return 9

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
        # SV-02 (12/06): sigmoid dos satélites aposentado — offsets fixos no
        # prior; o M5 (region_shift) assume a adaptação. Rollback via env.
        if not self._sigmoid_satellites_enabled():
            return self.BAYESIAN_DEFAULT, self.BAYESIAN_DEFAULT
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

    REGION_ERR_EMA_ALPHA = 0.2  # MELHORIA-G: suavização do erro por região

    def _circ_signed(self, frm: int, to: int) -> Optional[int]:
        """Distância circular ASSINADA frm→to (−18..+18) na roda atual."""
        try:
            a = self._wheel.index(frm)
            b = self._wheel.index(to)
        except ValueError:
            return None
        ws = len(self._wheel)
        d = (b - a) % ws
        return d - ws if d > ws // 2 else d

    def _update_region_err_ema(self, dk: str, c1: int, c2: int, c3: int,
                               actual_result: int,
                               include_satellites: bool = True) -> None:
        """MELHORIA-G (12/06): EMA do erro assinado até CADA centro proposto.

        Sinal positivo = resultado caiu adiante do centro (sentido da
        sequência da roda); negativo = atrás. EMA estável ≠ 0 numa região
        indica viés sistemático daquele setor naquele sentido — insumo do
        futuro controlador por região (só entra com aprovação walk-forward).

        Args:
            include_satellites: False quando C2/C3 não foram realmente
                propostos (fallback de calibração) — só C1 alimenta a série.
        """
        a = self.REGION_ERR_EMA_ALPHA
        slots = [("c1", c1)]
        if include_satellites:
            slots += [("c2", c2), ("c3", c3)]
        for slot, center in slots:
            sd = self._circ_signed(center, actual_result)
            if sd is None:
                continue
            cur = self._region_err_ema[dk].get(slot)
            self._region_err_ema[dk][slot] = (
                float(sd) if cur is None else (1.0 - a) * cur + a * float(sd)
            )
            self._region_err_n[dk][slot] = self._region_err_n[dk].get(slot, 0) + 1

    def get_region_err_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot da EMA de erro por região + nº de amostras (telemetria).

        Auditoria r3: o ``n`` evita leituras enganosas — EMA com 2-3 amostras
        é praticamente o valor cru do último spin.
        """
        return {
            dk: {
                **{k: (round(v, 3) if v is not None else None)
                   for k, v in self._region_err_ema.get(dk, {}).items()},
                "n": dict(self._region_err_n.get(dk, {})),
            }
            for dk in ("cw", "ccw")
        }


    # ================================================================== #

    def _pct_sigmoid_update(self, direction: str, c1: int, actual_result: int,
                            coverage: Optional[List[int]] = None,
                            centers: Optional[List[int]] = None) -> None:
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

        Auditoria 12/06 (BUG-B): quando ``coverage``/``centers`` da aposta
        REAL são fornecidos, is_hit/min_dist/cooldown usam a aposta emitida
        (não a cobertura recalculada). Fallback sem kwargs preserva o
        comportamento legado (testes/simuladores antigos).
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

        if centers and len(centers) >= 3:
            # Centros REAIS da aposta avaliada (BUG-B fix).
            c2, c3 = int(centers[1]), int(centers[2])
            _centers_are_real = True
        else:
            # Legado: deriva dos offsets efetivos atuais.
            o2_raw = max(self.OFFSET_MIN, min(self.OFFSET_MAX, round(off2)))
            o3_raw = max(self.OFFSET_MIN, min(self.OFFSET_MAX, round(off3)))
            o2 = self._get_effective_offset(dk, "c2", o2_raw)
            o3 = self._get_effective_offset(dk, "c3", o3_raw)
            c1_idx = self._wheel_index(c1, self._wheel)
            ws = len(self._wheel)
            c2 = self._wheel[(c1_idx + o2) % ws]
            c3 = self._wheel[(c1_idx - o3) % ws]
            _centers_are_real = False
        c1_nbrs = set(self.get_neighbors(c1, self.num_neighbors, self._wheel))
        c2_nbrs = set(self.get_neighbors(c2, self.C2_RADIUS, self._wheel))
        c3_nbrs = set(self.get_neighbors(c3, self.C3_RADIUS, self._wheel))
        if coverage:
            # Cobertura REAL da aposta (inclui fallback N=19/21).
            cov = set(coverage)
        else:
            cov = c1_nbrs | c2_nbrs | c3_nbrs

        is_hit = actual_result in cov

        # ---- MELHORIA-G (12/06): EMA do erro circular ASSINADO por região ----
        # Telemetria pura (não atua nos offsets — controlador é gated por A4).
        # Responde continuamente: "cada região está torta para que lado?"
        # Auditoria r3: C2/C3 só entram quando foram PROPOSTOS de verdade
        # (centers reais) — no fallback de calibração os derivados não foram
        # apostados e contaminariam a série. C1 é sempre real.
        try:
            self._update_region_err_ema(
                dk, c1, c2, c3, actual_result,
                include_satellites=_centers_are_real,
            )
        except Exception:  # noqa: BLE001 — telemetria nunca quebra feedback
            pass

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

        # SV-02 (12/06): com o sigmoid dos satélites aposentado, o feedback
        # para aqui — EMA (insumo do M5), recent_hits (QW-1/2/6) e histórico
        # continuam alimentados; drift-freeze/adaptação/regularizador são
        # exclusivos do mecanismo aposentado.
        if not self._sigmoid_satellites_enabled():
            return

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

    def _batch_auto_tune(self, dk: str, min_warmup: int) -> None:
        """S-STRAT-7 — Auto-tune em LOTE de 4 spins por sentido (isolado).

        Cada chamada:
          1. Valida warmup mínimo (>= 8 hits no buffer).
          2. Compara acc(últimos 4) vs acc(4 anteriores).
          3. Aplica pull-back, improve-keep ou explore-nudge.
          4. Atualiza métricas e batch_acc_history.

        INVARIANTES:
          - Nunca cruza dados entre cw e ccw.
          - Sempre respeita clamp [OFFSET_MIN, OFFSET_MAX].
          - Falha silenciosa (já protegida pelo try/except do caller).
        """
        import time as _t
        # SV-02 (12/06): sem sigmoid de satélites não há parâmetro a tunar.
        if not self._sigmoid_satellites_enabled():
            self._batch_last_action[dk] = "sigmoid-off"
            return
        hits = self._recent_hits.get(dk, [])
        if len(hits) < 8 or len(hits) < min_warmup:
            self._batch_last_action[dk] = "skip_warmup"
            logger.info("[BATCH-SKIP] dk=%s len=%d warmup=%d", dk, len(hits), min_warmup)
            return

        last_4 = hits[-4:]
        prev_4 = hits[-8:-4]
        acc_last = sum(last_4) / 4.0
        acc_prev = sum(prev_4) / 4.0
        delta = acc_last - acc_prev

        # volatility do batch ([0,1] dado binário, simplificada — DRY com S-STRAT-11)
        window = hits[-min(30, len(hits)):]
        n = len(window)
        mean_w = sum(window) / n
        var_w = sum((x - mean_w) ** 2 for x in window) / n
        std_w = var_w ** 0.5

        pullback_rate = float(self._cfg.get("sda17.auto_tune_batch", "pullback_rate", 0.15))
        improve_thr = float(self._cfg.get("sda17.auto_tune_batch", "improvement_threshold", 0.10))
        degrade_thr = float(self._cfg.get("sda17.auto_tune_batch", "degrade_threshold", -0.10))
        lr_batch = float(self._cfg.get("sda17.auto_tune_batch", "lr_batch", 0.30))

        off2 = self._sigmoid_off.get(f"{dk}_off2", float(self.BAYESIAN_DEFAULT))
        off3 = self._sigmoid_off.get(f"{dk}_off3", float(self.BAYESIAN_DEFAULT))

        action = "explore"
        if delta <= degrade_thr:
            # Piorou: pull-back forçado em direção ao prior.
            off2 += (self.PRIOR_CENTER - off2) * pullback_rate
            off3 += (self.PRIOR_CENTER - off3) * pullback_rate
            self._batch_pullback_total[dk] += 1
            action = "pullback"
            logger.info("[BATCH-PULLBACK] dk=%s delta=%.3f off2=%.2f off3=%.2f",
                        dk, delta, off2, off3)
        elif delta >= improve_thr:
            # Melhorou: mantém trajetória; em melhoria FORTE (≥ 2× threshold),
            # aplica push leve a favor para reforçar a tendência vencedora.
            # BUG-V3-04 fix: não desperdiça sinal forte de delta=+0.50.
            # BUG-V3-08 fix: anti-oscilação — não faz push se último foi pullback
            # (evita flip-flop pullback↔push em regime volátil).
            last_action = self._batch_last_action.get(dk, "init")
            if delta >= 2.0 * improve_thr and last_action != "pullback":
                # Direção do push: usa média de hits do batch como sinal positivo
                # (off ↓ aumenta agressividade). Magnitude conservadora.
                push = lr_batch * 0.5 * std_w
                off2 -= push * 0.3
                off3 -= push * 0.3
                action = "improve_push"
                logger.info("[BATCH-IMPROVE-PUSH] dk=%s delta=%.3f push=%.3f", dk, delta, push)
            else:
                action = "improve_keep"
                logger.info("[BATCH-IMPROVE] dk=%s delta=%.3f mantido (last=%s)", dk, delta, last_action)
        else:
            # Estável: nudge pequeno proporcional ao gradient médio do batch.
            # BUG-V3-03 fix: usa média de misses do batch como sinal (não só último).
            miss_avg = 1.0 - (sum(last_4) / 4.0)
            sign = 1 if miss_avg > 0.5 else -1
            magnitude = lr_batch * std_w * sign
            off2 += magnitude * 0.3
            off3 += magnitude * 0.3
            action = "explore_nudge"
            logger.info("[BATCH-EXPLORE] dk=%s delta=%.3f std=%.3f nudge=%.3f miss_avg=%.2f",
                        dk, delta, std_w, magnitude, miss_avg)

        # Clamp duro (respeita limites globais existentes).
        off2 = max(float(self.OFFSET_MIN), min(float(self.OFFSET_MAX), off2))
        off3 = max(float(self.OFFSET_MIN), min(float(self.OFFSET_MAX), off3))
        self._sigmoid_off[f"{dk}_off2"] = off2
        self._sigmoid_off[f"{dk}_off3"] = off3

        # Métricas estado para /api/batch_tune e Prometheus.
        self._batch_runs_total[dk] += 1
        self._batch_last_action[dk] = action
        self._batch_last_delta[dk] = delta
        self._last_tune_ts[dk] = _t.time()
        self._batch_acc_history[dk].append((acc_last, acc_prev, delta))
        if len(self._batch_acc_history[dk]) > 50:
            self._batch_acc_history[dk] = self._batch_acc_history[dk][-50:]

    def update_adaptive(self, direction: str, c1: int, actual_result: int,
                        wheel_sequence: List[int],
                        coverage: Optional[List[int]] = None,
                        centers: Optional[List[int]] = None) -> None:
        """
        Atualiza estado adaptativo após resultado conhecido.
        v4.3: Atualiza histórico + chama M02-PctSigmoid para ajustar offsets.
        Deve ser chamado APÓS check_prediction() e ANTES de analyze() do próximo spin.

        Auditoria 12/06 (BUG-B): ``coverage``/``centers`` da APOSTA REAL
        (pending_prediction). Sem eles o feedback recalculava a cobertura com
        offsets efetivos do momento — divergia da aposta emitida no fallback
        N=19/21 e na borda do cooldown QW-4 (aprendia com aposta inexistente).
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
        self._pct_sigmoid_update(direction, c1, actual_result,
                                 coverage=coverage, centers=centers)

        # ============================================================
        # S-STRAT-7 — Auto-tune batch a cada 4 spins (POR SENTIDO)
        # ============================================================
        # Contador isolado por direção. Incrementa SEMPRE (mesmo se warmup
        # ou freeze internos cancelaram a adaptação spin-a-spin), garantindo
        # que o tune por lote dispare exatamente a cada N spins.
        # CW e CCW NUNCA compartilham buffer/contador (INV-1 reforçado).
        dk = self._dk(direction)
        try:
            self._pending_spins[dk] += 1
            enabled = bool(self._cfg.get("sda17.auto_tune_batch", "enabled", True))
            batch_size = int(self._cfg.get("sda17.auto_tune_batch", "batch_size", 4))
            min_warmup = int(self._cfg.get("sda17.auto_tune_batch", "min_warmup_spins", 16))
            if enabled and self._pending_spins[dk] >= batch_size:
                self._batch_auto_tune(dk, min_warmup)
                self._pending_spins[dk] = 0
        except Exception as exc:
            logger.exception("[BATCH-TUNE-ERR] dk=%s err=%s", dk, exc)
            self._batch_last_action[dk] = "error"
    
    def get_adaptive_state(self) -> Dict[str, Any]:
        """Retorna estado adaptativo para persistência (v1.8 — S-STRAT-7 batch tune)."""
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
            # MELHORIA-G (12/06): EMA de erro por região (telemetria).
            "region_err_ema": self._region_err_ema,
            "region_err_n": self._region_err_n,
            # S-STRAT-7 — batch tune state (versão dict para forward-compat).
            "batch_tune_state": {
                "version": 1,
                "pending_spins": dict(self._pending_spins),
                "last_tune_ts": dict(self._last_tune_ts),
                "batch_pullback_total": dict(self._batch_pullback_total),
                "batch_runs_total": dict(self._batch_runs_total),
                "batch_last_action": dict(self._batch_last_action),
                "batch_last_delta": dict(self._batch_last_delta),
                "batch_acc_history": {
                    dk: list(self._batch_acc_history.get(dk, []))[-50:]
                    for dk in ("cw", "ccw")
                },
            },
            "version": "1.8",
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
        # MELHORIA-G: restaurar EMA de erro por região (ausente → None).
        raw_re = state.get("region_err_ema", {})
        if isinstance(raw_re, dict):
            for dk in ("cw", "ccw"):
                sub = raw_re.get(dk, {})
                if isinstance(sub, dict):
                    for slot in ("c1", "c2", "c3"):
                        v = sub.get(slot)
                        if v is None:
                            continue
                        try:
                            self._region_err_ema[dk][slot] = float(v)
                        except (ValueError, TypeError):
                            pass
        raw_rn = state.get("region_err_n", {})
        if isinstance(raw_rn, dict):
            for dk in ("cw", "ccw"):
                sub = raw_rn.get(dk, {})
                if isinstance(sub, dict):
                    for slot in ("c1", "c2", "c3"):
                        try:
                            self._region_err_n[dk][slot] = max(0, int(sub.get(slot, 0)))
                        except (ValueError, TypeError):
                            pass
        # S-STRAT-7: restaurar batch tune state (backward-compat: ausente → defaults).
        raw_bt = state.get("batch_tune_state", {})
        if isinstance(raw_bt, dict):
            ps = raw_bt.get("pending_spins", {})
            if isinstance(ps, dict):
                for dk in ("cw", "ccw"):
                    try:
                        self._pending_spins[dk] = max(0, int(ps.get(dk, 0)))
                    except (ValueError, TypeError):
                        pass
            lt = raw_bt.get("last_tune_ts", {})
            if isinstance(lt, dict):
                for dk in ("cw", "ccw"):
                    try:
                        self._last_tune_ts[dk] = float(lt.get(dk, 0.0))
                    except (ValueError, TypeError):
                        pass
            pt = raw_bt.get("batch_pullback_total", {})
            if isinstance(pt, dict):
                for dk in ("cw", "ccw"):
                    try:
                        self._batch_pullback_total[dk] = max(0, int(pt.get(dk, 0)))
                    except (ValueError, TypeError):
                        pass
            rt = raw_bt.get("batch_runs_total", {})
            if isinstance(rt, dict):
                for dk in ("cw", "ccw"):
                    try:
                        self._batch_runs_total[dk] = max(0, int(rt.get(dk, 0)))
                    except (ValueError, TypeError):
                        pass
            la = raw_bt.get("batch_last_action", {})
            if isinstance(la, dict):
                for dk in ("cw", "ccw"):
                    v = la.get(dk, "init")
                    if isinstance(v, str):
                        self._batch_last_action[dk] = v
            ld = raw_bt.get("batch_last_delta", {})
            if isinstance(ld, dict):
                for dk in ("cw", "ccw"):
                    try:
                        self._batch_last_delta[dk] = float(ld.get(dk, 0.0))
                    except (ValueError, TypeError):
                        pass
            bh = raw_bt.get("batch_acc_history", {})
            if isinstance(bh, dict):
                for dk in ("cw", "ccw"):
                    seq = bh.get(dk, [])
                    if isinstance(seq, list):
                        validated = []
                        for item in seq[-50:]:
                            if isinstance(item, (list, tuple)) and len(item) == 3:
                                try:
                                    validated.append(
                                        (float(item[0]), float(item[1]), float(item[2]))
                                    )
                                except (ValueError, TypeError):
                                    continue
                        self._batch_acc_history[dk] = validated

    def reset_adaptive(self) -> Dict[str, Any]:
        """B1 (12/06) — Reset TOTAL do estado adaptativo (troca de dealer).

        Premissa P10 do owner: o botão de nova sessão deve fazer a estratégia
        "começar de novo" genérica (P8) e re-armar o warmup de 2 jogadas por
        sentido (P9). Antes deste fix, handle_new_session zerava GameState mas
        o SDA17 mantinha offsets/históricos aprendidos — o dealer novo herdava
        o tuning do anterior (causa mecânica plausível da assimetria cw×ccw).

        Returns:
            Snapshot do estado descartado (para log/auditoria).
        """
        discarded = {
            "cw_history_len": len(self.cw_history),
            "ccw_history_len": len(self.ccw_history),
            "sigmoid_off": dict(self._sigmoid_off),
            "recent_hits_cw": len(self._recent_hits.get("cw", [])),
            "recent_hits_ccw": len(self._recent_hits.get("ccw", [])),
            "batch_runs_total": dict(self._batch_runs_total),
        }
        self.cw_history = []
        self.ccw_history = []
        self._last_offset = {}
        self._sigmoid_off = {}
        self._recent_hits = {"cw": [], "ccw": []}
        self._cooldown = {
            "cw":  {"c2": 0, "c3": 0},
            "ccw": {"c2": 0, "c3": 0},
        }
        self._drift_freeze = {"cw": 0, "ccw": 0}
        self._mg_resets = {"cw": 0, "ccw": 0}
        self._pending_spins = {"cw": 0, "ccw": 0}
        self._last_tune_ts = {"cw": 0.0, "ccw": 0.0}
        self._batch_acc_history = {"cw": [], "ccw": []}
        self._batch_pullback_total = {"cw": 0, "ccw": 0}
        self._batch_runs_total = {"cw": 0, "ccw": 0}
        self._batch_last_action = {"cw": "init", "ccw": "init"}
        self._batch_last_delta = {"cw": 0.0, "ccw": 0.0}
        self._region_err_ema = {
            "cw": {"c1": None, "c2": None, "c3": None},
            "ccw": {"c1": None, "c2": None, "c3": None},
        }
        self._region_err_n = {
            "cw": {"c1": 0, "c2": 0, "c3": 0},
            "ccw": {"c1": 0, "c2": 0, "c3": 0},
        }
        logger.info(
            "strategy_reset adaptive_state_cleared cw_hist=%d ccw_hist=%d sigmoid_keys=%d",
            discarded["cw_history_len"], discarded["ccw_history_len"],
            len(discarded["sigmoid_off"]),
        )
        return discarded

    def get_batch_tune_snapshot(self) -> Dict[str, Any]:
        """S-STRAT-7 — snapshot leve para /api/batch_tune."""
        return {
            "pending_spins": dict(self._pending_spins),
            "batch_size": int(self._cfg.get("sda17.auto_tune_batch", "batch_size", 4)),
            "last_tune_ts": dict(self._last_tune_ts),
            "batch_pullback_total": dict(self._batch_pullback_total),
            "batch_runs_total": dict(self._batch_runs_total),
            "batch_last_action": dict(self._batch_last_action),
            "batch_last_delta": dict(self._batch_last_delta),
            "batch_acc_history_tail": {
                dk: list(self._batch_acc_history.get(dk, []))[-10:]
                for dk in ("cw", "ccw")
            },
        }
    
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
    


"""
Simulação de 15 modelos de controle variável para C2/C3.
Cada modelo recebe feedback de jogadas anteriores e ajusta off_c2, off_c3.
C1 permanece fixo (conforme DB). Direções CW/CCW independentes.
"""
import sqlite3, json, math, sys
from typing import List, Tuple, Dict, Any

WHEEL = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
W_IDX = {v: i for i, v in enumerate(WHEEL)}
W_SIZE = len(WHEEL)
OFF_MIN, OFF_MAX = 7, 13
DEFAULT_OFF = 10

def circ_dist(a, b):
    ia, ib = W_IDX[a], W_IDX[b]
    d = abs(ia - ib)
    return min(d, W_SIZE - d)

def circ_dir(c1, result):
    """Returns +1 if result is CW from c1, -1 if CCW, 0 if same."""
    ic = W_IDX[c1]; ir = W_IDX[result]
    d_cw = (ir - ic) % W_SIZE
    d_ccw = (ic - ir) % W_SIZE
    if d_cw <= d_ccw: return 1
    return -1

def neighbors(center, radius):
    idx = W_IDX[center]
    return [WHEEL[(idx + d) % W_SIZE] for d in range(-radius, radius + 1)]

def coverage_set(c1, off2, off3):
    c1_idx = W_IDX[c1]
    c2 = WHEEL[(c1_idx + off2) % W_SIZE]
    c3 = WHEEL[(c1_idx - off3) % W_SIZE]
    s = set(neighbors(c1, 3))
    s |= set(neighbors(c2, 2))
    s |= set(neighbors(c3, 2))
    return s, c2, c3

def clamp(v): return max(OFF_MIN, min(OFF_MAX, round(v)))

def error_pct(c1, result, off2, off3):
    """Percentual de erro: distância do resultado ao número coberto mais próximo."""
    cov, _, _ = coverage_set(c1, off2, off3)
    if result in cov:
        return 0.0
    min_d = min(circ_dist(result, n) for n in cov)
    return min_d / 18.0  # 18 = max half-wheel distance


# ========================================================================
# 15 MODELOS DE CONTROLE VARIÁVEL C2/C3
# ========================================================================

class BaseModel:
    """Classe base para todos os modelos."""
    name = "Base"
    def __init__(self):
        self.off2 = float(DEFAULT_OFF)
        self.off3 = float(DEFAULT_OFF)
        self.history: List[Dict] = []
    
    def get_offsets(self) -> Tuple[int, int]:
        return clamp(self.off2), clamp(self.off3)
    
    def update(self, c1: int, result: int, hit: bool):
        """Chamado após cada jogada com feedback."""
        raise NotImplementedError
    
    def _error_info(self, c1, result):
        off2, off3 = self.get_offsets()
        cov, c2, c3 = coverage_set(c1, off2, off3)
        dist = circ_dist(c1, result)
        direction = circ_dir(c1, result)
        pct = error_pct(c1, result, off2, off3)
        self.history.append({"c1": c1, "result": result, "dist": dist, "dir": direction, "pct": pct,
                             "hit": result in cov, "off2": off2, "off3": off3})
        return dist, direction, pct


# --- CATEGORIA A: Error-Feedback Simples ---

class M01_PercentualLinear(BaseModel):
    """Ajuste linear baseado em % do erro. Hit: tighten 5% para center=10. Miss: mover % do erro."""
    name = "M01-PctLinear"
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        if hit:
            self.off2 += (DEFAULT_OFF - self.off2) * 0.05
            self.off3 += (DEFAULT_OFF - self.off3) * 0.05
        else:
            adj = pct * 3.0  # até ~0.5 * 3 = 1.5 posições
            if direction > 0:  # resultado está no sentido +
                self.off2 += adj
                self.off3 -= adj * 0.5
            else:
                self.off3 += adj
                self.off2 -= adj * 0.5

class M02_PercentualSigmoid(BaseModel):
    """Sigmoid dampening no ajuste percentual (evita overshoot em erros grandes)."""
    name = "M02-PctSigmoid"
    def _sigmoid(self, x, k=6):
        return 2.0 / (1.0 + math.exp(-k * x)) - 1.0
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        if hit:
            self.off2 += (DEFAULT_OFF - self.off2) * 0.08
            self.off3 += (DEFAULT_OFF - self.off3) * 0.08
        else:
            adj = self._sigmoid(pct) * 2.0
            if direction > 0:
                self.off2 += adj
                self.off3 -= adj * 0.3
            else:
                self.off3 += adj
                self.off2 -= adj * 0.3

class M03_PercentualThreshold(BaseModel):
    """Só ajusta se erro > 7 posições (ignora misses pequenos como ruído)."""
    name = "M03-PctThresh"
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        if hit:
            self.off2 += (DEFAULT_OFF - self.off2) * 0.10
            self.off3 += (DEFAULT_OFF - self.off3) * 0.10
        elif dist > 7:
            adj = pct * 4.0
            if direction > 0:
                self.off2 += adj
                self.off3 -= adj * 0.5
            else:
                self.off3 += adj
                self.off2 -= adj * 0.5


# --- CATEGORIA B: Médias Móveis ---

class M04_EMA_ErrorTracking(BaseModel):
    """EMA de erros direcionais com alpha=0.3, converte em ajuste de offset."""
    name = "M04-EMA"
    def __init__(self):
        super().__init__()
        self.ema_pos = 0.0  # EMA de erros no sentido +
        self.ema_neg = 0.0  # EMA de erros no sentido -
        self.alpha = 0.3
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        if hit:
            self.ema_pos *= (1 - self.alpha)
            self.ema_neg *= (1 - self.alpha)
        else:
            if direction > 0:
                self.ema_pos = self.alpha * dist + (1 - self.alpha) * self.ema_pos
            else:
                self.ema_neg = self.alpha * dist + (1 - self.alpha) * self.ema_neg
        
        bias = (self.ema_pos - self.ema_neg) * 0.15
        self.off2 = DEFAULT_OFF + bias
        self.off3 = DEFAULT_OFF - bias

class M05_AdaptiveEWMA(BaseModel):
    """EWMA com alpha adaptativo: erro maior → alpha maior → resposta mais rápida."""
    name = "M05-AdapEWMA"
    def __init__(self):
        super().__init__()
        self.ema_off2 = float(DEFAULT_OFF)
        self.ema_off3 = float(DEFAULT_OFF)
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        alpha = min(0.6, 0.05 + pct * 0.8)  # 0.05 (hit) a 0.6 (max error)
        
        if hit:
            target2 = self.off2  # manter
            target3 = self.off3
            alpha = 0.05
        else:
            # Calcular oracle offset ideal para esta jogada
            best = self._find_oracle(c1, result)
            target2 = best if direction > 0 else self.off2
            target3 = best if direction <= 0 else self.off3
        
        self.ema_off2 = (1 - alpha) * self.ema_off2 + alpha * target2
        self.ema_off3 = (1 - alpha) * self.ema_off3 + alpha * target3
        self.off2 = self.ema_off2
        self.off3 = self.ema_off3
    
    def _find_oracle(self, c1, result):
        for off in range(OFF_MIN, OFF_MAX + 1):
            cov, _, _ = coverage_set(c1, off, off)
            if result in cov:
                return off
        return DEFAULT_OFF

class M06_Weighted3(BaseModel):
    """Apenas últimas 3 jogadas, pesos 3:2:1, calcula offset ótimo ponderado."""
    name = "M06-Weight3"
    def __init__(self):
        super().__init__()
        self.recent: List[Tuple[int, int]] = []  # (c1, result)
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        self.recent.append((c1, result))
        if len(self.recent) > 3:
            self.recent = self.recent[-3:]
        
        if len(self.recent) < 2:
            return
        
        weights = [1, 2, 3][-len(self.recent):]
        best_off2, best_off3 = DEFAULT_OFF, DEFAULT_OFF
        best_score = -1
        
        for t2 in range(OFF_MIN, OFF_MAX + 1):
            for t3 in range(OFF_MIN, OFF_MAX + 1):
                score = 0
                for i, (rc1, rres) in enumerate(self.recent):
                    cov, _, _ = coverage_set(rc1, t2, t3)
                    if rres in cov:
                        score += weights[i]
                if score > best_score:
                    best_score = score
                    best_off2, best_off3 = t2, t3
        
        self.off2 = self.off2 * 0.3 + best_off2 * 0.7
        self.off3 = self.off3 * 0.3 + best_off3 * 0.7


# --- CATEGORIA C: Teoria de Controle ---

class M07_PID(BaseModel):
    """Controlador PID: P=erro atual, I=erro acumulado, D=taxa de mudança."""
    name = "M07-PID"
    def __init__(self):
        super().__init__()
        self.integral2 = 0.0; self.integral3 = 0.0
        self.prev_err2 = 0.0; self.prev_err3 = 0.0
        self.Kp, self.Ki, self.Kd = 0.3, 0.05, 0.15
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        
        if hit:
            err2 = (DEFAULT_OFF - self.off2) * 0.1
            err3 = (DEFAULT_OFF - self.off3) * 0.1
        else:
            err2 = pct * 2.0 * (1 if direction > 0 else -0.5)
            err3 = pct * 2.0 * (1 if direction < 0 else -0.5)
        
        self.integral2 = self.integral2 * 0.9 + err2
        self.integral3 = self.integral3 * 0.9 + err3
        
        d2 = err2 - self.prev_err2
        d3 = err3 - self.prev_err3
        
        adj2 = self.Kp * err2 + self.Ki * self.integral2 + self.Kd * d2
        adj3 = self.Kp * err3 + self.Ki * self.integral3 + self.Kd * d3
        
        self.off2 += adj2
        self.off3 += adj3
        self.prev_err2 = err2
        self.prev_err3 = err3

class M08_DampedPID(BaseModel):
    """PID com anti-windup e filtro derivativo para prevenir oscilação."""
    name = "M08-DampPID"
    def __init__(self):
        super().__init__()
        self.integral2 = 0.0; self.integral3 = 0.0
        self.prev_err2 = 0.0; self.prev_err3 = 0.0
        self.Kp, self.Ki, self.Kd = 0.2, 0.03, 0.25
        self.WINDUP_MAX = 3.0
        self.d_filter = 0.7
        self.prev_d2 = 0.0; self.prev_d3 = 0.0
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        
        if hit:
            err2 = (DEFAULT_OFF - self.off2) * 0.15
            err3 = (DEFAULT_OFF - self.off3) * 0.15
        else:
            err2 = pct * 2.5 * (1 if direction > 0 else -0.3)
            err3 = pct * 2.5 * (1 if direction < 0 else -0.3)
        
        self.integral2 = max(-self.WINDUP_MAX, min(self.WINDUP_MAX, self.integral2 * 0.85 + err2))
        self.integral3 = max(-self.WINDUP_MAX, min(self.WINDUP_MAX, self.integral3 * 0.85 + err3))
        
        raw_d2 = err2 - self.prev_err2
        raw_d3 = err3 - self.prev_err3
        d2 = self.d_filter * self.prev_d2 + (1 - self.d_filter) * raw_d2
        d3 = self.d_filter * self.prev_d3 + (1 - self.d_filter) * raw_d3
        
        adj2 = self.Kp * err2 + self.Ki * self.integral2 + self.Kd * d2
        adj3 = self.Kp * err3 + self.Ki * self.integral3 + self.Kd * d3
        
        self.off2 += adj2; self.off3 += adj3
        self.prev_err2 = err2; self.prev_err3 = err3
        self.prev_d2 = d2; self.prev_d3 = d3

class M09_Kalman(BaseModel):
    """Filtro de Kalman 1D para estimação de offset ótimo."""
    name = "M09-Kalman"
    def __init__(self):
        super().__init__()
        self.x2 = float(DEFAULT_OFF)  # state estimate off2
        self.x3 = float(DEFAULT_OFF)  # state estimate off3
        self.P2 = 4.0   # uncertainty
        self.P3 = 4.0
        self.Q = 0.5    # process noise
        self.R = 3.0    # measurement noise
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        
        # "Measurement" = estimated ideal offset from this play
        if hit:
            z2 = self.off2  # confirma offset atual
            z3 = self.off3
            self.R = 5.0  # alta incerteza na medição (hit pode ser qualquer offset)
        else:
            oracle = self._find_best_oracle(c1, result, direction)
            z2 = oracle if direction > 0 else self.x2
            z3 = oracle if direction <= 0 else self.x3
            self.R = 2.0  # mais confiante no oracle de miss
        
        # Predict
        self.P2 += self.Q; self.P3 += self.Q
        
        # Update off2
        K2 = self.P2 / (self.P2 + self.R)
        self.x2 = self.x2 + K2 * (z2 - self.x2)
        self.P2 = (1 - K2) * self.P2
        
        # Update off3
        K3 = self.P3 / (self.P3 + self.R)
        self.x3 = self.x3 + K3 * (z3 - self.x3)
        self.P3 = (1 - K3) * self.P3
        
        self.off2 = self.x2; self.off3 = self.x3
    
    def _find_best_oracle(self, c1, result, direction):
        for off in range(OFF_MIN, OFF_MAX + 1):
            cov, _, _ = coverage_set(c1, off, off)
            if result in cov:
                return off
        return DEFAULT_OFF


# --- CATEGORIA D: Estatística ---

class M10_MAD_Robust(BaseModel):
    """MAD (Median Absolute Deviation) para identificar outliers e ajustar só com dados limpos."""
    name = "M10-MAD"
    def __init__(self):
        super().__init__()
        self.errors: List[Tuple[float, int]] = []  # (signed_error, oracle_off)
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        
        oracle = self._find_oracle(c1, result)
        signed_err = dist * direction
        self.errors.append((signed_err, oracle))
        if len(self.errors) > 12:
            self.errors = self.errors[-12:]
        
        if len(self.errors) < 3:
            return
        
        # MAD filter
        errs = [e[0] for e in self.errors]
        med = sorted(errs)[len(errs) // 2]
        mad = sorted([abs(e - med) for e in errs])[len(errs) // 2]
        threshold = max(3.0, med + 2.5 * max(mad, 1.0))
        
        clean = [(e, o) for e, o in self.errors if abs(e) <= threshold]
        if not clean:
            clean = self.errors[-3:]
        
        oracles = [o for _, o in clean if o != DEFAULT_OFF]
        if oracles:
            avg_oracle = sum(oracles) / len(oracles)
            self.off2 = self.off2 * 0.6 + avg_oracle * 0.4
            self.off3 = self.off3 * 0.6 + avg_oracle * 0.4
        
        if hit:
            self.off2 += (DEFAULT_OFF - self.off2) * 0.05
            self.off3 += (DEFAULT_OFF - self.off3) * 0.05
    
    def _find_oracle(self, c1, result):
        for off in range(OFF_MIN, OFF_MAX + 1):
            cov, _, _ = coverage_set(c1, off, off)
            if result in cov:
                return off
        return DEFAULT_OFF

class M11_BayesianPosterior(BaseModel):
    """Distribuição de probabilidade sobre offsets [7-13], atualiza com Bayes após cada jogada."""
    name = "M11-Bayes"
    def __init__(self):
        super().__init__()
        n = OFF_MAX - OFF_MIN + 1
        self.probs2 = [1.0 / n] * n  # Uniform prior para off2
        self.probs3 = [1.0 / n] * n  # Uniform prior para off3
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        n = OFF_MAX - OFF_MIN + 1
        
        # Likelihood: P(result | off) ∝ 1 se cobre, else exp(-dist/5)
        like2 = []; like3 = []
        for i, off in enumerate(range(OFF_MIN, OFF_MAX + 1)):
            cov2, _, _ = coverage_set(c1, off, clamp(self.off3))
            cov3, _, _ = coverage_set(c1, clamp(self.off2), off)
            
            l2 = 1.0 if result in cov2 else math.exp(-circ_dist(result, WHEEL[(W_IDX[c1] + off) % W_SIZE]) / 5.0)
            l3 = 1.0 if result in cov3 else math.exp(-circ_dist(result, WHEEL[(W_IDX[c1] - off) % W_SIZE]) / 5.0)
            like2.append(l2); like3.append(l3)
        
        # Posterior ∝ prior × likelihood
        for i in range(n):
            self.probs2[i] *= like2[i]
            self.probs3[i] *= like3[i]
        
        # Normalize
        s2 = sum(self.probs2); s3 = sum(self.probs3)
        if s2 > 0: self.probs2 = [p / s2 for p in self.probs2]
        if s3 > 0: self.probs3 = [p / s3 for p in self.probs3]
        
        # MAP estimate (maximum a posteriori)
        best2 = max(range(n), key=lambda i: self.probs2[i])
        best3 = max(range(n), key=lambda i: self.probs3[i])
        
        # Smooth: 70% MAP + 30% current
        self.off2 = self.off2 * 0.3 + (OFF_MIN + best2) * 0.7
        self.off3 = self.off3 * 0.3 + (OFF_MIN + best3) * 0.7

class M12_PercentileBand(BaseModel):
    """Mantém offset entre 25º e 75º percentil dos oracle offsets recentes."""
    name = "M12-PctBand"
    def __init__(self):
        super().__init__()
        self.oracles: List[int] = []
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        
        oracle = self._find_oracle(c1, result)
        if oracle != DEFAULT_OFF or hit:
            self.oracles.append(oracle if not hit else clamp(self.off2))
        if len(self.oracles) > 10:
            self.oracles = self.oracles[-10:]
        
        if len(self.oracles) < 3:
            return
        
        s = sorted(self.oracles)
        q25 = s[max(0, len(s) // 4)]
        q75 = s[min(len(s) - 1, 3 * len(s) // 4)]
        mid = (q25 + q75) / 2.0
        
        # Mover suavemente para o centro da banda
        self.off2 = self.off2 * 0.5 + mid * 0.5
        self.off3 = self.off3 * 0.5 + mid * 0.5
        
        # Asymmetry: se direction tem viés, deslocar
        if direction > 0 and not hit:
            self.off2 = min(self.off2 + 0.3, q75)
        elif direction < 0 and not hit:
            self.off3 = min(self.off3 + 0.3, q75)
    
    def _find_oracle(self, c1, result):
        for off in range(OFF_MIN, OFF_MAX + 1):
            cov, _, _ = coverage_set(c1, off, off)
            if result in cov:
                return off
        return DEFAULT_OFF


# --- CATEGORIA E: Híbrido/Avançado ---

class M13_MomentumPhysics(BaseModel):
    """Partícula com massa: aplica força proporcional ao erro, velocidade acumula com atrito."""
    name = "M13-Momentum"
    def __init__(self):
        super().__init__()
        self.vel2 = 0.0; self.vel3 = 0.0
        self.friction = 0.7  # dampening
        self.force_scale = 0.4
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        
        if hit:
            # Atração para centro (spring force)
            f2 = (DEFAULT_OFF - self.off2) * 0.1
            f3 = (DEFAULT_OFF - self.off3) * 0.1
        else:
            f2 = pct * self.force_scale * (1 if direction > 0 else -0.4)
            f3 = pct * self.force_scale * (1 if direction < 0 else -0.4)
        
        self.vel2 = self.vel2 * self.friction + f2
        self.vel3 = self.vel3 * self.friction + f3
        
        self.off2 += self.vel2
        self.off3 += self.vel3

class M14_GradientDescent(BaseModel):
    """Gradiente numérico: testa off±1 contra últimas 3 jogadas, step na direção do gradiente."""
    name = "M14-GradDesc"
    def __init__(self):
        super().__init__()
        self.recent: List[Tuple[int, int]] = []
        self.lr = 0.5  # learning rate
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        self.recent.append((c1, result))
        if len(self.recent) > 3:
            self.recent = self.recent[-3:]
        
        if len(self.recent) < 2:
            return
        
        o2, o3 = clamp(self.off2), clamp(self.off3)
        
        def score(t2, t3):
            s = 0
            for rc1, rres in self.recent:
                cov, _, _ = coverage_set(rc1, t2, t3)
                if rres in cov:
                    s += 1
                else:
                    s -= min(circ_dist(rres, WHEEL[(W_IDX[rc1] + t2) % W_SIZE]),
                             circ_dist(rres, WHEEL[(W_IDX[rc1] - t3) % W_SIZE])) * 0.1
            return s
        
        # Numerical gradient
        sc = score(o2, o3)
        g2 = score(min(OFF_MAX, o2 + 1), o3) - score(max(OFF_MIN, o2 - 1), o3)
        g3 = score(o2, min(OFF_MAX, o3 + 1)) - score(o2, max(OFF_MIN, o3 - 1))
        
        self.off2 += self.lr * (g2 / 2.0)
        self.off3 += self.lr * (g3 / 2.0)

class M15_EnsembleVote(BaseModel):
    """Média ponderada dos 3 melhores sub-modelos (M01,M04,M09), pesos por accuracy recente."""
    name = "M15-Ensemble"
    def __init__(self):
        super().__init__()
        self.sub = [M01_PercentualLinear(), M04_EMA_ErrorTracking(), M09_Kalman()]
        self.sub_hits = [0, 0, 0]
        self.sub_plays = [0, 0, 0]
    
    def update(self, c1, result, hit):
        dist, direction, pct = self._error_info(c1, result)
        
        # Verificar quais sub-modelos teriam acertado
        for i, m in enumerate(self.sub):
            o2, o3 = m.get_offsets()
            cov, _, _ = coverage_set(c1, o2, o3)
            self.sub_plays[i] += 1
            if result in cov:
                self.sub_hits[i] += 1
            m.update(c1, result, hit)
        
        # Weighted average by accuracy
        weights = []
        for i in range(3):
            if self.sub_plays[i] > 0:
                w = (self.sub_hits[i] + 1) / (self.sub_plays[i] + 2)  # Laplace smoothing
            else:
                w = 0.5
            weights.append(w)
        
        total_w = sum(weights)
        if total_w > 0:
            self.off2 = sum(m.get_offsets()[0] * w for m, w in zip(self.sub, weights)) / total_w
            self.off3 = sum(m.get_offsets()[1] * w for m, w in zip(self.sub, weights)) / total_w


# ========================================================================
# SIMULAÇÃO
# ========================================================================

ALL_MODELS = [
    M01_PercentualLinear, M02_PercentualSigmoid, M03_PercentualThreshold,
    M04_EMA_ErrorTracking, M05_AdaptiveEWMA, M06_Weighted3,
    M07_PID, M08_DampedPID, M09_Kalman,
    M10_MAD_Robust, M11_BayesianPosterior, M12_PercentileBand,
    M13_MomentumPhysics, M14_GradientDescent, M15_EnsembleVote
]

conn = sqlite3.connect("/app/data/decisions.db")
conn.row_factory = sqlite3.Row

for direction, label in [("horario", "CW"), ("anti-horario", "CCW")]:
    rows = conn.execute("""
        SELECT id, sda_center, sda_centers, sda_numbers, sda_offset,
               result_hit, result_actual, spin_force, sda_predicted_force
        FROM decisions
        WHERE spin_direction = ? AND result_actual IS NOT NULL AND sda_center > 0
        ORDER BY id ASC
    """, (direction,)).fetchall()
    
    # Pegar últimas 50 com resultado
    rows = rows[-50:] if len(rows) > 50 else rows
    
    print("=" * 120)
    print(f"{'='*50} {label} ({direction}) — {len(rows)} jogadas {'='*50}")
    print("=" * 120)
    
    # Baseline (offsets reais do DB)
    baseline_hits = sum(1 for r in rows if r["result_hit"] == 1)
    baseline_hr = baseline_hits / len(rows) * 100 if rows else 0
    
    # Simular cada modelo
    results = {}
    for ModelClass in ALL_MODELS:
        model = ModelClass()
        hits = 0
        total = 0
        play_log = []
        
        for r in rows:
            c1 = r["sda_center"]
            result = r["result_actual"]
            if c1 == 0 or result is None:
                continue
            
            # Usar offsets do modelo
            o2, o3 = model.get_offsets()
            cov, c2, c3 = coverage_set(c1, o2, o3)
            is_hit = result in cov
            
            total += 1
            if is_hit:
                hits += 1
            
            # Feedback ao modelo
            model.update(c1, result, is_hit)
            
            play_log.append({
                "id": r["id"], "c1": c1, "result": result,
                "off2": o2, "off3": o3, "hit": is_hit,
                "c2": c2, "c3": c3, "nums": len(cov)
            })
        
        hr = hits / total * 100 if total > 0 else 0
        results[model.name] = {"hits": hits, "total": total, "hr": hr, "log": play_log}
    
    # === PRINT RESULTS ===
    print(f"\n  BASELINE (offsets reais do DB): {baseline_hits}/{len(rows)} = {baseline_hr:.1f}%\n")
    
    # Ranking
    ranked = sorted(results.items(), key=lambda x: -x[1]["hr"])
    
    print(f"  {'Rank':<5} {'Modelo':<18} {'Hits':<6} {'Total':<6} {'HR%':<8} {'vs Base':<10} {'Avaliação'}")
    print(f"  {'-'*5} {'-'*18} {'-'*6} {'-'*6} {'-'*8} {'-'*10} {'-'*15}")
    
    for rank, (name, data) in enumerate(ranked, 1):
        diff = data["hr"] - baseline_hr
        sign = "+" if diff >= 0 else ""
        eval_str = "✅ SUPERIOR" if diff > 2 else ("➡️ SIMILAR" if abs(diff) <= 2 else "❌ INFERIOR")
        print(f"  {rank:<5} {name:<18} {data['hits']:<6} {data['total']:<6} {data['hr']:<8.1f} {sign}{diff:<9.1f} {eval_str}")
    
    # Detail do melhor modelo
    best_name, best_data = ranked[0]
    print(f"\n  MELHOR MODELO {label}: {best_name} ({best_data['hr']:.1f}% HR)")
    print(f"  {'─'*100}")
    
    print(f"  {'#':<4} {'ID':<6} {'C1':<4} {'Off2':<5} {'Off3':<5} {'C2':<4} {'C3':<4} {'Res':<4} {'Status':<6}")
    for i, p in enumerate(best_data["log"]):
        st = " HIT" if p["hit"] else "MISS"
        print(f"  {i+1:<4} {p['id']:<6} {p['c1']:<4} {p['off2']:<5} {p['off3']:<5} {p['c2']:<4} {p['c3']:<4} {p['result']:<4} {st}")
    
    # Evolução de offsets do melhor modelo
    print(f"\n  EVOLUÇÃO OFFSETS {best_name}:")
    offs = [(p["off2"], p["off3"]) for p in best_data["log"]]
    for i in range(0, len(offs), 10):
        chunk = offs[i:i+10]
        line2 = " ".join(f"{o2:2d}" for o2, o3 in chunk)
        line3 = " ".join(f"{o3:2d}" for o2, o3 in chunk)
        print(f"    off2[{i+1:2d}-{i+len(chunk):2d}]: {line2}")
        print(f"    off3[{i+1:2d}-{i+len(chunk):2d}]: {line3}")
    
    print()

conn.close()
print("\n" + "=" * 120)
print("SIMULAÇÃO DOS 15 MODELOS COMPLETA")
print("=" * 120)

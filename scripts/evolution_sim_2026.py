"""evolution_sim_2026 — comparador causal de modelos de evolução da estratégia.

Modo YOLO/processamento ilimitado: testa 7+ modelos em CADA ponto do fluxo
de decisão, por SENTIDO isolado (P6), reset por sessão (P10), SEM look-ahead
(cada jogada t decide com dados até t-1). Métrica pedida pelo owner:
matriz miss→hit / hit→miss vs baseline (transformar erros em acertos
mantendo acertos) + EV flat (17u, payout 36:1, N=17).

Pontos do fluxo (cada um isola uma alavanca):
  A) PREDITOR DE FORÇA / C1  — onde o centro principal cai
  B) GEOMETRIA / COBERTURA   — como os 17 números se distribuem
  D) CONTROLADOR ADAPTATIVO  — correção de viés por jogada (M5 vive aqui)

Reduz-se tudo a ESPAÇO DE ERRO DE FORÇA: error_t = circ(real_force_t -
f_pred_t); a bola é coberta se o error cai no conjunto coberto pela geometria.
Isso torna A/B/D comparáveis na MESMA métrica.

Saídas: por modelo, hit% / EV / miss→hit / hit→miss / saldo, no AGREGADO e
nas ÚLTIMAS 50 jogadas de cada sentido.

Uso: python scripts/evolution_sim_2026.py [db]
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict, deque, Counter
from pathlib import Path
from statistics import median, mean, pstdev

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "decisions_prod_1206b.db"

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
         10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
SIZE = len(WHEEL)
POS = {n: i for i, n in enumerate(WHEEL)}
LAST50 = 50


def dir_force(frm: int, to: int, target: str) -> int:
    a, b = POS[frm], POS[to]
    return (b - a) % SIZE if target == "cw" else (a - b) % SIZE


def circ(e: float) -> float:
    e = (e + SIZE * 10) % SIZE
    return e - SIZE if e > SIZE // 2 else e


# ---------------------------------------------------------------- coverage
def covered_777(e: float, off2: int, off3: int,
                r1=3, r2=2, r3=2) -> bool:
    if abs(circ(e)) <= r1:
        return True
    if abs(circ(e - off2)) <= r2:
        return True
    if abs(circ(e + off3)) <= r3:
        return True
    return False


def covered_arc(e: float, radius: int) -> bool:
    return abs(circ(e)) <= radius


# ---------------------------------------------------------------- load
def load():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    seq = {"cw": [], "ccw": []}
    for r in conn.execute("""
        SELECT timestamp, session_id, spin_number, spin_direction,
               sda_predicted_force, sda_centers, result_actual
        FROM decisions
        WHERE result_actual IS NOT NULL AND sda_centers IS NOT NULL
        ORDER BY id
    """):
        try:
            centers = [int(x) for x in json.loads(r["sda_centers"])]
        except (ValueError, TypeError):
            continue
        if len(centers) < 3:
            continue
        target = "ccw" if r["spin_direction"] == "horario" else "cw"
        last = r["spin_number"]
        actual = r["result_actual"]
        real_f = dir_force(last, actual, target)
        pred_f = dir_force(last, centers[0], target)  # C1 efetivo gravado
        seq[target].append({
            "ts": r["timestamp"], "sess": r["session_id"],
            "real_f": real_f, "pred_f": pred_f,
            "period": "train" if r["timestamp"][:7] < "2026-05" else "test",
        })
    conn.close()
    return seq


# ============================================================ POINT A models
# Predizem f_pred a partir do histórico de FORÇAS REAIS do sentido (causal).
class _ForcePred:
    def predict(self): raise NotImplementedError
    def update(self, real_f): raise NotImplementedError


class A0_median7(_ForcePred):
    def __init__(self): self.buf = deque(maxlen=7)
    def predict(self): return median(self.buf) if self.buf else 10
    def update(self, f): self.buf.append(f)


class A1_ewma(_ForcePred):
    def __init__(self, a=0.3): self.a, self.v = a, None
    def predict(self): return self.v if self.v is not None else 10
    def update(self, f): self.v = f if self.v is None else (1-self.a)*self.v + self.a*f


class A2_last(_ForcePred):
    def __init__(self): self.v = None
    def predict(self): return self.v if self.v is not None else 10
    def update(self, f): self.v = f


class A3_wmedian(_ForcePred):
    def __init__(self): self.buf = deque(maxlen=9)
    def predict(self):
        if not self.buf: return 10
        # mediana ponderada por recência (peso 0.8^idade)
        items = sorted((v, 0.8**i) for i, v in enumerate(reversed(self.buf)))
        tot = sum(w for _, w in items); acc = 0
        for v, w in items:
            acc += w
            if acc >= tot/2: return v
        return items[-1][0]
    def update(self, f): self.buf.append(f)


class A4_mode(_ForcePred):
    def __init__(self): self.buf = deque(maxlen=12)
    def predict(self):
        if not self.buf: return 10
        return Counter(self.buf).most_common(1)[0][0]
    def update(self, f): self.buf.append(f)


class A5_trimmed(_ForcePred):
    def __init__(self): self.buf = deque(maxlen=9)
    def predict(self):
        if len(self.buf) < 3: return median(self.buf) if self.buf else 10
        s = sorted(self.buf); k = max(1, len(s)//5)
        core = s[k:-k] or s
        return mean(core)
    def update(self, f): self.buf.append(f)


class A6_median_bias(_ForcePred):
    """Mediana 7 + EMA do erro residual (predictor + correção M5-style)."""
    def __init__(self, a=0.2, k=0.5):
        self.buf = deque(maxlen=7); self.a, self.k = a, k; self.ema = None
    def predict(self):
        base = median(self.buf) if self.buf else 10
        if self.ema is None: return base
        return base + self.k * self.ema
    def update(self, f):
        pred_base = median(self.buf) if self.buf else 10
        err = f - pred_base
        self.ema = err if self.ema is None else (1-self.a)*self.ema + self.a*err
        self.buf.append(f)


class A7_kalman(_ForcePred):
    """Nível com ganho adaptativo (Kalman 1D simplificado)."""
    def __init__(self, q=2.0, r=120.0):
        self.x = None; self.p = 100.0; self.q, self.r = q, r
    def predict(self): return self.x if self.x is not None else 10
    def update(self, f):
        if self.x is None: self.x = f; return
        self.p += self.q
        kg = self.p / (self.p + self.r)
        self.x += kg * (f - self.x)
        self.p *= (1 - kg)


class A8_median3(_ForcePred):  # janela curta (adapta rápido)
    def __init__(self): self.buf = deque(maxlen=3)
    def predict(self): return median(self.buf) if self.buf else 10
    def update(self, f): self.buf.append(f)


class A9_median15(_ForcePred):  # janela longa (estável)
    def __init__(self): self.buf = deque(maxlen=15)
    def predict(self): return median(self.buf) if self.buf else 10
    def update(self, f): self.buf.append(f)


class A10_mode20(_ForcePred):  # moda janela ampla
    def __init__(self): self.buf = deque(maxlen=20)
    def predict(self):
        if not self.buf: return 10
        return Counter(self.buf).most_common(1)[0][0]
    def update(self, f): self.buf.append(f)


class A11_ewma_slow(_ForcePred):  # suavização gentil
    def __init__(self, a=0.1): self.a, self.v = a, None
    def predict(self): return self.v if self.v is not None else 10
    def update(self, f): self.v = f if self.v is None else (1-self.a)*self.v + self.a*f


class A12_antipersist(_ForcePred):
    """Exploita autocorr negativa (−0.13): prevê reversão à mediana."""
    def __init__(self, k=0.3):
        self.buf = deque(maxlen=9); self.k = k; self.last = None
    def predict(self):
        if not self.buf: return 10
        base = median(self.buf)
        if self.last is None: return base
        return base - self.k * (self.last - base)
    def update(self, f): self.buf.append(f); self.last = f


class A13_huber(_ForcePred):  # média robusta (Huber)
    def __init__(self, c=8.0): self.buf = deque(maxlen=9); self.c = c
    def predict(self):
        if not self.buf: return 10
        m = median(self.buf)
        for _ in range(6):
            num = den = 0.0
            for x in self.buf:
                d = x - m
                w = 1.0 if abs(d) <= self.c else (self.c/abs(d) if d else 1.0)
                num += w*x; den += w
            m = num/den if den else m
        return m
    def update(self, f): self.buf.append(f)


class A14_midhinge(_ForcePred):  # (Q1+Q3)/2
    def __init__(self): self.buf = deque(maxlen=12)
    def predict(self):
        if len(self.buf) < 4: return median(self.buf) if self.buf else 10
        s = sorted(self.buf); n = len(s)
        return (s[n//4] + s[(3*n)//4]) / 2
    def update(self, f): self.buf.append(f)


class A15_decay_mode(_ForcePred):  # moda ponderada por recência
    def __init__(self): self.buf = deque(maxlen=20)
    def predict(self):
        if not self.buf: return 10
        w = defaultdict(float)
        for i, v in enumerate(reversed(self.buf)):
            w[int(round(v))] += 0.85**i
        return max(w, key=w.get)
    def update(self, f): self.buf.append(f)


class A16_ensemble(_ForcePred):  # consenso mediana-7 ⊕ moda-12
    def __init__(self): self.buf = deque(maxlen=12)
    def predict(self):
        if not self.buf: return 10
        med = median(list(self.buf)[-7:])
        mod = Counter(self.buf).most_common(1)[0][0]
        return round((med + mod) / 2)
    def update(self, f): self.buf.append(f)


class A17_session_median(_ForcePred):  # janela adaptativa = toda a sessão
    def __init__(self): self.buf = []
    def predict(self): return median(self.buf) if self.buf else 10
    def update(self, f): self.buf.append(f)


POINT_A = {"A0_median7": A0_median7, "A1_ewma": A1_ewma, "A2_last": A2_last,
           "A3_wmedian": A3_wmedian, "A4_mode": A4_mode, "A5_trimmed": A5_trimmed,
           "A6_med_bias": A6_median_bias, "A7_kalman": A7_kalman,
           "A8_median3": A8_median3, "A9_median15": A9_median15,
           "A10_mode20": A10_mode20, "A11_ewma_slow": A11_ewma_slow,
           "A12_antipersist": A12_antipersist, "A13_huber": A13_huber,
           "A14_midhinge": A14_midhinge, "A15_decay_mode": A15_decay_mode,
           "A16_ensemble": A16_ensemble, "A17_session_median": A17_session_median}


# ============================================================ POINT B models
# Geometria fixa por modelo; usam o erro do PREDITOR BASELINE (pred_f gravado).
def point_b_hit(model: str, e: float, hist_err: deque) -> bool:
    if model == "B0_777_10":        return covered_777(e, 10, 10)
    if model == "B1_arc8":          return covered_arc(e, 8)            # contíguo N17
    if model == "B2_777_8":         return covered_777(e, 8, 8)        # satélites perto
    if model == "B3_777_13":        return covered_777(e, 13, 13)      # satélites longe
    if model == "B4_wideC1":        return covered_777(e, 11, 11, r1=4, r2=2, r3=2)  # C1 9 nums
    if model == "B5_empirical":
        # offsets = picos de densidade do hist de erros (fora ±3), causal
        o2, o3 = _empirical_offsets(hist_err)
        return covered_777(e, o2, o3)
    if model == "B6_volradius":
        # raio cresce com volatilidade recente dos erros (mantém ~17)
        r = 3
        if len(hist_err) >= 8:
            s = pstdev(list(hist_err)[-20:]) if len(hist_err) >= 2 else 11
            r = 2 if s < 9 else (3 if s < 12 else 4)
        return covered_777(e, 10, 10, r1=r, r2=2, r3=2)
    if model == "B7_arc_emashift":
        # arco contíguo deslocado pela EMA de erro (geometria+viés)
        sh = _ema_shift(hist_err)
        return covered_arc(circ(e - sh), 8)
    if model == "B8_emp_long":
        o2, o3 = _emp_offsets_win(hist_err, 90)
        return covered_777(e, o2, o3)
    if model == "B9_emp_kde":
        o2, o3 = _emp_offsets_kde(hist_err)
        return covered_777(e, o2, o3)
    if model == "B10_emp_drift":
        o2, o3 = _empirical_offsets(hist_err); sh = _ema_shift(hist_err)
        return covered_777(circ(e - sh), o2, o3)
    if model == "B11_top2peaks":
        p1, p2 = _top2_peaks(hist_err)
        return abs(circ(e)) <= 3 or abs(circ(e - p1)) <= 2 or abs(circ(e - p2)) <= 2
    if model == "B12_fatC1":
        return covered_777(e, 10, 10, r1=5, r2=1, r3=1)   # 11+3+3 (N=17)
    if model == "B13_fatSAT":
        return covered_777(e, 10, 10, r1=1, r2=3, r3=3)   # 3+7+7 (N=17)
    if model == "B14_adaptive_split":
        r1, r2, r3 = _adaptive_split(hist_err)
        return covered_777(e, 10, 10, r1=r1, r2=r2, r3=r3)
    if model == "B15_emp_split":
        r1, r2, r3 = _adaptive_split(hist_err); o2, o3 = _empirical_offsets(hist_err)
        return covered_777(e, o2, o3, r1=r1, r2=r2, r3=r3)
    if model == "B16_emp_m5c1":
        o2, o3 = _empirical_offsets(hist_err); sh = _ema_shift(hist_err)
        return covered_777_c1shift(e, sh, o2, o3)
    if model == "B17_vol_split":
        r1, r2, r3 = _vol_split(hist_err)
        return covered_777(e, 10, 10, r1=r1, r2=r2, r3=r3)
    return False


def _empirical_offsets(hist):
    if len(hist) < 12: return 10, 10
    h = Counter(int(round(circ(x))) for x in list(hist)[-60:])
    pos = {k: v for k, v in h.items() if k > 3}
    neg = {k: v for k, v in h.items() if k < -3}
    o2 = max(pos, key=pos.get) if pos else 10
    o3 = -max(neg, key=neg.get) if neg else 10
    return max(7, min(15, o2)), max(7, min(15, o3))


def _ema_shift(hist, a=0.2, k=0.5, clamp=4):
    if len(hist) < 3: return 0
    ema = None
    for x in list(hist)[-30:]:
        ema = x if ema is None else (1-a)*ema + a*x
    return max(-clamp, min(clamp, round(-(-ema) * k)))  # ema é erro residual


def _emp_offsets_win(hist, window):
    if len(hist) < 12: return 10, 10
    h = Counter(int(round(circ(x))) for x in list(hist)[-window:])
    pos = {k: v for k, v in h.items() if k > 3}
    neg = {k: v for k, v in h.items() if k < -3}
    o2 = max(pos, key=pos.get) if pos else 10
    o3 = -max(neg, key=neg.get) if neg else 10
    return max(7, min(15, o2)), max(7, min(15, o3))


def _emp_offsets_kde(hist):
    """Picos de densidade com suavização triangular (robusto a ruído)."""
    if len(hist) < 12: return 10, 10
    raw = Counter(int(round(circ(x))) for x in list(hist)[-60:])
    sm = {k: 2*raw.get(k, 0) + raw.get(k-1, 0) + raw.get(k+1, 0) for k in range(-18, 19)}
    pos = {k: v for k, v in sm.items() if k > 3 and v > 0}
    neg = {k: v for k, v in sm.items() if k < -3 and v > 0}
    o2 = max(pos, key=pos.get) if pos else 10
    o3 = -max(neg, key=neg.get) if neg else 10
    return max(7, min(15, o2)), max(7, min(15, o3))


def _top2_peaks(hist):
    """Os 2 buckets mais densos fora de ±3 (qualquer sinal)."""
    if len(hist) < 12: return 10, -10
    h = Counter(int(round(circ(x))) for x in list(hist)[-60:] if abs(circ(x)) > 3)
    if len(h) < 2: return 10, -10
    top = [k for k, _ in h.most_common(2)]
    return top[0], top[1]


def _concentration(hist, window=30):
    """Fração de erros recentes dentro de ±3 (massa no centro)."""
    if len(hist) < 8: return None
    w = list(hist)[-window:]
    return sum(1 for x in w if abs(circ(x)) <= 3) / len(w)


def _adaptive_split(hist):
    """Redistribui os MESMOS 17: centro gordo se erro concentrado,
    satélites gordos se disperso. (r1,r2,r3) — footprint sempre 17."""
    c = _concentration(hist)
    if c is None: return (3, 2, 2)
    if c >= 0.45: return (5, 1, 1)   # 11+3+3 — concentra no centro
    if c <= 0.25: return (1, 3, 3)   # 3+7+7 — espalha nos satélites
    return (3, 2, 2)                  # 7+5+5 baseline


def _vol_split(hist):
    if len(hist) < 8: return (3, 2, 2)
    s = pstdev(list(hist)[-20:])
    if s < 9: return (5, 1, 1)
    if s > 13: return (1, 3, 3)
    return (3, 2, 2)


def covered_777_c1shift(e, sh, off2, off3, r1=3, r2=2, r3=2):
    """C1 deslocado por shift M5; satélites fixos nos offsets (fiel à produção)."""
    if abs(circ(e - sh)) <= r1: return True
    if abs(circ(e - off2)) <= r2: return True
    if abs(circ(e + off3)) <= r3: return True
    return False


def _footprint_general(specs):
    s = set()
    for off, r in specs:
        for d in range(-r, r+1): s.add((off + d) % SIZE)
    return len(s)


POINT_B = ["B0_777_10", "B1_arc8", "B2_777_8", "B3_777_13", "B4_wideC1",
           "B5_empirical", "B6_volradius", "B7_arc_emashift",
           "B8_emp_long", "B9_emp_kde", "B10_emp_drift", "B11_top2peaks",
           "B12_fatC1", "B13_fatSAT", "B14_adaptive_split", "B15_emp_split",
           "B16_emp_m5c1", "B17_vol_split"]


def _footprint_777(off2, off3, r1=3, r2=2, r3=2):
    s = set()
    for d in range(-r1, r1+1): s.add(d % SIZE)
    for d in range(-r2, r2+1): s.add((off2 + d) % SIZE)
    for d in range(-r3, r3+1): s.add((-off3 + d) % SIZE)
    return len(s)


def _footprint_arc(radius):
    return 2*radius + 1


def point_b_size(model: str, hist_err: deque) -> int:
    """Número de casas cobertas (N) — para EV coverage-aware (lição N=19)."""
    if model == "B0_777_10":  return _footprint_777(10, 10)
    if model == "B1_arc8":    return _footprint_arc(8)
    if model == "B2_777_8":   return _footprint_777(8, 8)
    if model == "B3_777_13":  return _footprint_777(13, 13)
    if model == "B4_wideC1":  return _footprint_777(11, 11, r1=4)
    if model == "B5_empirical":
        o2, o3 = _empirical_offsets(hist_err); return _footprint_777(o2, o3)
    if model == "B6_volradius":
        r = 3
        if len(hist_err) >= 8:
            s = pstdev(list(hist_err)[-20:]) if len(hist_err) >= 2 else 11
            r = 2 if s < 9 else (3 if s < 12 else 4)
        return _footprint_777(10, 10, r1=r)
    if model == "B7_arc_emashift": return _footprint_arc(8)
    if model == "B8_emp_long":
        o2, o3 = _emp_offsets_win(hist_err, 90); return _footprint_777(o2, o3)
    if model == "B9_emp_kde":
        o2, o3 = _emp_offsets_kde(hist_err); return _footprint_777(o2, o3)
    if model == "B10_emp_drift":
        o2, o3 = _empirical_offsets(hist_err); return _footprint_777(o2, o3)
    if model == "B11_top2peaks":
        p1, p2 = _top2_peaks(hist_err)
        return _footprint_general([(0, 3), (p1, 2), (p2, 2)])
    if model == "B12_fatC1":  return _footprint_777(10, 10, r1=5, r2=1, r3=1)
    if model == "B13_fatSAT": return _footprint_777(10, 10, r1=1, r2=3, r3=3)
    if model == "B14_adaptive_split":
        r1, r2, r3 = _adaptive_split(hist_err)
        return _footprint_777(10, 10, r1=r1, r2=r2, r3=r3)
    if model == "B15_emp_split":
        r1, r2, r3 = _adaptive_split(hist_err); o2, o3 = _empirical_offsets(hist_err)
        return _footprint_777(o2, o3, r1=r1, r2=r2, r3=r3)
    if model == "B16_emp_m5c1":
        o2, o3 = _empirical_offsets(hist_err); return _footprint_777(o2, o3)
    if model == "B17_vol_split":
        r1, r2, r3 = _vol_split(hist_err)
        return _footprint_777(10, 10, r1=r1, r2=r2, r3=r3)
    return 17


# ============================================================ POINT D models
# Controladores de shift (aplicados ao erro do preditor baseline). Causal.
class D0_none:
    def shift(self): return 0.0
    def update(self, e): pass


class D1_m5(D0_none):  # produção atual k=0.5
    A, K, CL, N = 0.2, 0.5, 4, 3
    def __init__(self): self.ema, self.n = None, 0
    def shift(self):
        if self.n < self.N or self.ema is None: return 0.0
        return max(-self.CL, min(self.CL, round(-self.ema*self.K)))
    def update(self, e):
        self.ema = e if self.ema is None else (1-self.A)*self.ema + self.A*e
        self.n += 1


class D2_m5_hot(D1_m5):  # mais agressivo
    A, K, CL, N = 0.35, 1.0, 6, 3


class D3_median(D0_none):
    CL, N = 5, 3
    def __init__(self): self.buf = deque(maxlen=9)
    def shift(self):
        if len(self.buf) < self.N: return 0.0
        return max(-self.CL, min(self.CL, round(-median(self.buf))))
    def update(self, e): self.buf.append(e)


class D4_pi(D0_none):  # P + I
    KP, KI, CL = 0.25, 0.06, 5
    def __init__(self): self.last = 0.0; self.acc = 0.0; self.n = 0
    def shift(self):
        if self.n < 3: return 0.0
        return max(-self.CL, min(self.CL, round(-(self.KP*self.last + self.KI*self.acc))))
    def update(self, e):
        self.last = e; self.acc = 0.9*self.acc + e; self.n += 1


class D5_dual(D0_none):  # EMA rápida + lenta (regime)
    AF, AS, K, CL, N = 0.4, 0.08, 0.5, 4, 3
    def __init__(self): self.f = self.s = None; self.n = 0
    def shift(self):
        if self.n < self.N or self.f is None: return 0.0
        blend = 0.6*self.f + 0.4*self.s
        return max(-self.CL, min(self.CL, round(-blend*self.K)))
    def update(self, e):
        self.f = e if self.f is None else (1-self.AF)*self.f + self.AF*e
        self.s = e if self.s is None else (1-self.AS)*self.s + self.AS*e
        self.n += 1


class D6_gated(D1_m5):  # só corrige se viés forte e estável
    A, K, CL, N = 0.2, 0.6, 4, 4
    THR = 2.5
    def shift(self):
        if self.n < self.N or self.ema is None or abs(self.ema) < self.THR:
            return 0.0
        return max(-self.CL, min(self.CL, round(-self.ema*self.K)))


class D7_region(D0_none):
    """M5-região: EMA própria de C1 + satélites (vencedor §6). Aqui só C1
    (satélites tratados no Point B); equivale ao D1 mas com warmup curto."""
    A, K, CL, N = 0.2, 0.5, 4, 2
    def __init__(self): self.ema, self.n = None, 0
    def shift(self):
        if self.n < self.N or self.ema is None: return 0.0
        return max(-self.CL, min(self.CL, round(-self.ema*self.K)))
    def update(self, e):
        self.ema = e if self.ema is None else (1-self.A)*self.ema + self.A*e
        self.n += 1


class D8_m5_a30(D1_m5):  # EMA mais rápida
    A, K, CL, N = 0.3, 0.5, 4, 3


class D9_m5_cl6(D1_m5):  # clamp maior
    A, K, CL, N = 0.2, 0.5, 6, 3


class D10_pid(D0_none):  # P + I + D
    KP, KI, KD, CL = 0.25, 0.05, 0.15, 5
    def __init__(self): self.last = 0.0; self.prev = 0.0; self.acc = 0.0; self.n = 0
    def shift(self):
        if self.n < 3: return 0.0
        u = self.KP*self.last + self.KI*self.acc + self.KD*(self.last-self.prev)
        return max(-self.CL, min(self.CL, round(-u)))
    def update(self, e):
        self.prev = self.last; self.last = e; self.acc = 0.9*self.acc + e; self.n += 1


class D11_signstep(D0_none):  # passo mínimo ±1 no sentido do viés
    N = 3
    def __init__(self): self.ema, self.n = None, 0
    def shift(self):
        if self.n < self.N or self.ema is None: return 0.0
        return 1.0 if self.ema < -0.5 else (-1.0 if self.ema > 0.5 else 0.0)
    def update(self, e):
        self.ema = e if self.ema is None else 0.8*self.ema + 0.2*e
        self.n += 1


class D12_conf_gated(D0_none):
    """M5 escalado pela CONSISTÊNCIA recente (confia mais quando o erro é estável)."""
    A, K, CL, N = 0.2, 0.5, 4, 3
    def __init__(self): self.ema, self.n, self.buf = None, 0, deque(maxlen=12)
    def shift(self):
        if self.n < self.N or self.ema is None: return 0.0
        s = pstdev(self.buf) if len(self.buf) >= 2 else 11
        conf = max(0.0, min(1.0, 1.0 - s/14.0))   # σ baixo → confiança alta
        return max(-self.CL, min(self.CL, round(-self.ema*self.K*conf)))
    def update(self, e):
        self.ema = e if self.ema is None else (1-self.A)*self.ema + self.A*e
        self.buf.append(e); self.n += 1


class D13_asym(D1_m5):  # ganho assimétrico +/- (genérico, não por sentido)
    A, CL, N = 0.2, 4, 3
    def shift(self):
        if self.n < self.N or self.ema is None: return 0.0
        k = 0.6 if self.ema > 0 else 0.4
        return max(-self.CL, min(self.CL, round(-self.ema*k)))


class D14_deadband(D1_m5):  # ignora viés pequeno
    A, K, CL, N = 0.2, 0.5, 4, 3
    DB = 1.0
    def shift(self):
        if self.n < self.N or self.ema is None or abs(self.ema) < self.DB: return 0.0
        return max(-self.CL, min(self.CL, round(-self.ema*self.K)))


class D15_adaptive_k(D0_none):
    """K cresce com |ema|: ignora viés pequeno, reage forte a viés grande."""
    A, CL, N = 0.2, 4, 3
    def __init__(self): self.ema, self.n = None, 0
    def shift(self):
        if self.n < self.N or self.ema is None: return 0.0
        k = 0.3 + 0.4*min(1.0, abs(self.ema)/6.0)
        return max(-self.CL, min(self.CL, round(-self.ema*k)))
    def update(self, e):
        self.ema = e if self.ema is None else (1-self.A)*self.ema + self.A*e
        self.n += 1


class D16_warm2_dead(D7_region):  # warmup 2 + deadband
    DB = 1.0
    def shift(self):
        if self.n < self.N or self.ema is None or abs(self.ema) < self.DB: return 0.0
        return max(-self.CL, min(self.CL, round(-self.ema*self.K)))


class D17_loss_activated(D0_none):
    """Liga o controlador SÓ quando está perdendo (hit recente < limiar)."""
    A, K, CL, N = 0.2, 0.6, 4, 3
    def __init__(self): self.ema, self.n, self.hits = None, 0, deque(maxlen=12)
    def shift(self):
        if self.n < self.N or self.ema is None: return 0.0
        if len(self.hits) >= 6 and (sum(self.hits)/len(self.hits)) >= 0.46:
            return 0.0   # ganhando o suficiente → não mexe
        return max(-self.CL, min(self.CL, round(-self.ema*self.K)))
    def update(self, e):
        self.ema = e if self.ema is None else (1-self.A)*self.ema + self.A*e
        self.n += 1
    def feed_hit(self, h): self.hits.append(1 if h else 0)


POINT_D = {"D0_none": D0_none, "D1_m5_prod": D1_m5, "D2_m5_hot": D2_m5_hot,
           "D3_median": D3_median, "D4_pi": D4_pi, "D5_dual": D5_dual,
           "D6_gated": D6_gated, "D7_region": D7_region,
           "D8_m5_a30": D8_m5_a30, "D9_m5_cl6": D9_m5_cl6, "D10_pid": D10_pid,
           "D11_signstep": D11_signstep, "D12_conf_gated": D12_conf_gated,
           "D13_asym": D13_asym, "D14_deadband": D14_deadband,
           "D15_adaptive_k": D15_adaptive_k, "D16_warm2_dead": D16_warm2_dead,
           "D17_loss_activated": D17_loss_activated}


# ============================================================ runner
def fresh_stats():
    return {"n": 0, "hit": 0, "m2h": 0, "h2m": 0, "pnl": 0.0}


def ev_flat(hit, n):
    if not n: return 0.0
    hr = hit / n
    return hr * 19 - (1 - hr) * 17


def run_point_A(seq):
    res = defaultdict(lambda: defaultdict(fresh_stats))  # model -> scope -> stats
    for target in ("cw", "ccw"):
        rows = seq[target]
        cut = len(rows) - LAST50
        states = {m: {} for m in POINT_A}
        for i, r in enumerate(rows):
            e_base = circ(r["real_f"] - r["pred_f"])
            base_hit = covered_777(e_base, 10, 10)
            for mname, mcls in POINT_A.items():
                st = states[mname].get(r["sess"])
                if st is None:
                    st = states[mname][r["sess"]] = mcls()
                f_pred = st.predict()
                e = circ(r["real_f"] - f_pred)
                h = covered_777(e, 10, 10)
                scopes = [("ALL", target), (r["period"], target)]
                if i >= cut: scopes.append(("L50", target))
                for sc in scopes:
                    b = res[mname][sc]
                    b["n"] += 1; b["hit"] += 1 if h else 0
                    b["pnl"] += (36.0/17 - 1.0) if h else -1.0
                    if h and not base_hit: b["m2h"] += 1
                    if base_hit and not h: b["h2m"] += 1
                st.update(r["real_f"])
    return res


def run_point_B(seq):
    res = defaultdict(lambda: defaultdict(fresh_stats))
    for target in ("cw", "ccw"):
        rows = seq[target]
        cut = len(rows) - LAST50
        hist = {m: {} for m in POINT_B}  # model->sess->deque
        for i, r in enumerate(rows):
            e = circ(r["real_f"] - r["pred_f"])  # erro do preditor baseline
            base_hit = covered_777(e, 10, 10)
            for m in POINT_B:
                d = hist[m].get(r["sess"])
                if d is None: d = hist[m][r["sess"]] = deque(maxlen=60)
                h = point_b_hit(m, e, d)
                nN = point_b_size(m, d)
                pnl = (36.0/nN - 1.0) if h else -1.0  # 1u distribuído, payout 36
                scopes = [("ALL", target)]
                if i >= cut: scopes.append(("L50", target))
                scopes.append((r["period"], target))  # walk-forward A4
                for sc in scopes:
                    b = res[m][sc]
                    b["n"] += 1; b["hit"] += 1 if h else 0; b["pnl"] += pnl
                    if h and not base_hit: b["m2h"] += 1
                    if base_hit and not h: b["h2m"] += 1
                d.append(e)
    return res


def run_point_D(seq):
    res = defaultdict(lambda: defaultdict(fresh_stats))
    for target in ("cw", "ccw"):
        rows = seq[target]
        cut = len(rows) - LAST50
        states = {m: {} for m in POINT_D}
        for i, r in enumerate(rows):
            e = circ(r["real_f"] - r["pred_f"])
            base_hit = covered_777(e, 10, 10)
            for mname, mcls in POINT_D.items():
                st = states[mname].get(r["sess"])
                if st is None: st = states[mname][r["sess"]] = mcls()
                s = st.shift()
                h = covered_777(circ(e - s), 10, 10)
                scopes = [("ALL", target), (r["period"], target)]
                if i >= cut: scopes.append(("L50", target))
                for sc in scopes:
                    b = res[mname][sc]
                    b["n"] += 1; b["hit"] += 1 if h else 0
                    b["pnl"] += (36.0/17 - 1.0) if h else -1.0
                    if h and not base_hit: b["m2h"] += 1
                    if base_hit and not h: b["h2m"] += 1
                st.update(circ(e - s))  # integra erro residual pós-shift
                if hasattr(st, "feed_hit"): st.feed_hit(h)
    return res


def print_block(title, res, models, baseline, show_pnl=False):
    print(f"\n{'='*78}\n{title}\n{'='*78}")
    for scope_label, scope_tag in (("ÚLTIMAS 50/sentido", "L50"), ("AGREGADO", "ALL")):
        print(f"\n--- {scope_label} ---")
        extra = f" {'EVcov':>7} {'N':>4}" if show_pnl else ""
        print(f"{'modelo':19} {'dir':4} {'n':>4} {'hit%':>6} {'EVflat':>7} "
              f"{'miss→hit':>9} {'hit→miss':>9} {'saldo':>6}{extra}")
        for m in models:
            for d in ("cw", "ccw"):
                b = res[m][(scope_tag, d)]
                if not b["n"]: continue
                star = " *" if m == baseline else ""
                ex = ""
                if show_pnl:
                    evc = b["pnl"] / b["n"] * 17  # normaliza p/ stake 17u (comparável)
                    ex = f" {evc:+7.2f}     "
                print(f"{m:19} {d:4} {b['n']:4d} {100*b['hit']/b['n']:5.1f}% "
                      f"{ev_flat(b['hit'], b['n']):+7.2f} {b['m2h']:9d} {b['h2m']:9d} "
                      f"{b['m2h']-b['h2m']:+6d}{star}{ex}")


def _evcov(b):
    return b["pnl"] / b["n"] * 17 if b["n"] else 0.0


def print_walkforward(label, res, baseline, models):
    print(f"\n--- {label} · WALK-FORWARD (EVcov treino→teste, gate de promoção) ---")
    print(f"{'modelo':19} {'dir':4} {'treino':>8} {'teste':>8} {'veredito':>10}")
    passers = []
    for m in models:
        ok_both, seen = True, False
        for d in ("cw", "ccw"):
            tr = res[m][("train", d)]; te = res[m][("test", d)]
            if not tr["n"] or not te["n"]:
                ok_both = False; continue
            seen = True
            etr, ete = _evcov(tr), _evcov(te)
            btr = _evcov(res[baseline][("train", d)])
            bte = _evcov(res[baseline][("test", d)])
            passes = etr > btr and ete > bte
            ok_both = ok_both and passes
            print(f"{m:19} {d:4} {etr:+8.2f} {ete:+8.2f} "
                  f"{'PASSA' if passes else '-':>10}")
        if seen and ok_both and m != baseline:
            passers.append(m)
    print(f"  -> passam nos DOIS sentidos vs baseline: "
          f"{', '.join(passers) if passers else 'NENHUM (sem sinal fora de amostra)'}")
    return passers


def rank_general_rule(label, res, baseline, models):
    """Regra geral adaptativa = maximizar saldo (miss->hit menos hit->miss) E
    EVcov, nos DOIS sentidos. Ranking pelo agregado (saldoΣ, depois EVcovΣ)."""
    print(f"\n--- {label} · RANKING 'REGRA GERAL ADAPTATIVA' (agregado, 2 sentidos) ---")
    print(f"{'modelo':19} {'saldoΣ':>7} {'m2hΣ':>6} {'h2mΣ':>6} {'EVcovΣ':>8}")
    rows = []
    for m in models:
        saldo = evc = m2h = h2m = 0.0; ok = True
        for d in ("cw", "ccw"):
            b = res[m][("ALL", d)]
            if not b["n"]: ok = False; break
            saldo += b["m2h"] - b["h2m"]; m2h += b["m2h"]; h2m += b["h2m"]
            evc += _evcov(b)
        if ok: rows.append((m, saldo, m2h, h2m, evc))
    rows.sort(key=lambda x: (x[1], x[4]), reverse=True)
    for m, saldo, m2h, h2m, evc in rows[:6]:
        star = " *" if m == baseline else ""
        print(f"{m:19} {saldo:+7.0f} {m2h:6.0f} {h2m:6.0f} {evc:+8.2f}{star}")
    return rows


def run_decision(seq):
    """BACKTEST DE DECISÃO — qual geometria vira REGRA de produção.
    Compara, por sentido isolado e causal, contra a aposta REAL de hoje (P0-LIVE):
      P0 prod          = 7+5+5 @10 + M5 C1-shift  (o que está no ar)
      P1 fatSAT @10    = 3+7+7 @10 + M5 C1-shift
      P2 fatSAT + KDE  = 3+7+7 + offsets-densidade-do-sentido + M5 C1-shift
      P3 fatSAT + KDE  = 3+7+7 + offsets-densidade, SEM M5
    miss->hit / hit->miss medidos vs P0-LIVE (mantém acertos? melhora erros?)."""
    cfgs = {
        "P0_prod_755":        dict(r=(3, 2, 2), kde=False, m5=True),
        "P1_fatSAT_10":       dict(r=(1, 3, 3), kde=False, m5=True),
        "P2_fatSAT_kde":      dict(r=(1, 3, 3), kde=True,  m5=True),
        "P3_fatSAT_kde_noM5": dict(r=(1, 3, 3), kde=True,  m5=False),
    }
    res = defaultdict(lambda: defaultdict(fresh_stats))
    for target in ("cw", "ccw"):
        rows = seq[target]; cut = len(rows) - LAST50
        sess_state = {}
        for i, r in enumerate(rows):
            e = circ(r["real_f"] - r["pred_f"])
            s = sess_state.get(r["sess"])
            if s is None:
                s = sess_state[r["sess"]] = {"ema": None, "n": 0, "hist": deque(maxlen=60)}
            sh = 0
            if s["n"] >= 3 and s["ema"] is not None:
                sh = max(-4, min(4, round(-s["ema"] * 0.5)))
            o2k, o3k = _emp_offsets_kde(s["hist"])
            base_hit = covered_777_c1shift(e, sh, 10, 10, r1=3, r2=2, r3=2)  # P0-LIVE
            for c, cf in cfgs.items():
                r1, r2, r3 = cf["r"]
                o2, o3 = (o2k, o3k) if cf["kde"] else (10, 10)
                use_sh = sh if cf["m5"] else 0
                h = covered_777_c1shift(e, use_sh, o2, o3, r1=r1, r2=r2, r3=r3)
                nN = _footprint_777(o2, o3, r1=r1, r2=r2, r3=r3)
                pnl = (36.0 / nN - 1.0) if h else -1.0
                scopes = [("ALL", target), (r["period"], target)]
                if i >= cut: scopes.append(("L50", target))
                for sc in scopes:
                    b = res[c][sc]
                    b["n"] += 1; b["hit"] += 1 if h else 0; b["pnl"] += pnl
                    if h and not base_hit: b["m2h"] += 1
                    if base_hit and not h: b["h2m"] += 1
            s["hist"].append(e)
            s["ema"] = e if s["ema"] is None else 0.8 * s["ema"] + 0.2 * e
            s["n"] += 1
    return res


def main():
    seq = load()
    print(f"dataset: cw={len(seq['cw'])} ccw={len(seq['ccw'])} decisões resolvidas (3 centros)")
    print(f"sessões: cw={len({r['sess'] for r in seq['cw']})} "
          f"ccw={len({r['sess'] for r in seq['ccw']})}")
    print(f"erro de força σ: cw={pstdev([circ(r['real_f']-r['pred_f']) for r in seq['cw']]):.1f} "
          f"ccw={pstdev([circ(r['real_f']-r['pred_f']) for r in seq['ccw']]):.1f}")
    ra = run_point_A(seq)
    print_block("PONTO A — PREDITOR DE FORÇA / C1 (geometria fixa 7+5+5 @10/10)",
                ra, list(POINT_A), "A0_median7")
    print_walkforward("PONTO A", ra, "A0_median7", list(POINT_A))
    rank_general_rule("PONTO A", ra, "A0_median7", list(POINT_A))

    rb = run_point_B(seq)
    print_block("PONTO B — GEOMETRIA / COBERTURA (preditor baseline)",
                rb, POINT_B, "B0_777_10", show_pnl=True)
    print_walkforward("PONTO B", rb, "B0_777_10", POINT_B)
    rank_general_rule("PONTO B", rb, "B0_777_10", POINT_B)

    rd = run_point_D(seq)
    print_block("PONTO D — CONTROLADOR ADAPTATIVO DE VIÉS (preditor baseline)",
                rd, list(POINT_D), "D0_none")
    print_walkforward("PONTO D", rd, "D0_none", list(POINT_D))
    rank_general_rule("PONTO D", rd, "D0_none", list(POINT_D))

    print("\n\n" + "#" * 78)
    print("# BACKTEST DE DECISÃO — qual geometria vira REGRA de produção (vs P0-LIVE)")
    print("#" * 78)
    dec_models = ["P0_prod_755", "P1_fatSAT_10", "P2_fatSAT_kde", "P3_fatSAT_kde_noM5"]
    rdec = run_decision(seq)
    print_block("DECISÃO — geometria de produção", rdec, dec_models,
                "P0_prod_755", show_pnl=True)
    print_walkforward("DECISÃO", rdec, "P0_prod_755", dec_models)
    rank_general_rule("DECISÃO", rdec, "P0_prod_755", dec_models)


if __name__ == "__main__":
    main()

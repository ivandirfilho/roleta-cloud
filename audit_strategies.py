# AUDITORIA COMPLETA: 20 ESTRATÉGIAS DE FINE-TUNING
# Simulação de engenharia reversa para encontrar a melhor resposta a erros

from statistics import median, mean, stdev
import math

# Dados reais do state.json
timeline_cw = [30, 28, 0, 17, 27, 33, 14, 12, 13, 22, 20, 35, 36, 8, 19, 3, 3, 4, 8, 3]
timeline_ccw = [13, 7, 30, 36, 11, 3, 7, 25, 35, 29, 33, 34, 25, 1, 7, 17, 8, 0, 25, 9]

def linear_regression_predict(forces_5):
    n = len(forces_5)
    y = list(reversed(forces_5))
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    num = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    den = sum((x[i] - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0
    intercept = y_mean - slope * x_mean
    return max(1, min(37, int(round(intercept + slope * n))))

def circular_error(predicted, actual):
    """Erro circular com sinal"""
    error = actual - predicted
    if error > 18: error -= 37
    elif error < -18: error += 37
    return error

def is_hit(predicted, actual, tolerance=8):
    diff = abs(predicted - actual)
    diff = min(diff, 37 - diff)
    return diff <= tolerance

def clamp_offset(offset, limit=8):
    return max(-limit, min(limit, offset))

# ============================================================
# CATEGORIA 1: PREDIÇÃO BASE (Como calcular o centro)
# ============================================================

def predict_regression(forces):
    return linear_regression_predict(forces)

def predict_median(forces):
    return int(median(forces))

def predict_mean(forces):
    return int(mean(forces))

def predict_weighted_recent(forces):
    """Mais peso para forças recentes"""
    weights = [5, 4, 3, 2, 1]  # Recente = maior peso
    total = sum(f * w for f, w in zip(forces, weights))
    return int(total / sum(weights))

def predict_mode_cluster(forces):
    """Encontra cluster mais denso"""
    # Agrupa por proximidade (±5)
    clusters = []
    for f in forces:
        added = False
        for c in clusters:
            if abs(c[0] - f) <= 5:
                c.append(f)
                added = True
                break
        if not added:
            clusters.append([f])
    # Retorna média do maior cluster
    biggest = max(clusters, key=len)
    return int(mean(biggest))

def predict_ema(forces, alpha=0.4):
    """Exponential Moving Average"""
    ema = forces[-1]  # Mais antiga
    for f in reversed(forces[:-1]):
        ema = alpha * f + (1 - alpha) * ema
    return int(ema)

# ============================================================
# CATEGORIA 2: AJUSTE DE OFFSET (Como reagir ao erro)
# ============================================================

def adjust_none(offset, error, history):
    """Sem ajuste - baseline"""
    return 0

def adjust_fixed_small(offset, error, history):
    """Offset fixo pequeno na direção do erro"""
    return clamp_offset(1 if error > 0 else -1 if error < 0 else 0)

def adjust_proportional_25(offset, error, history):
    """25% do erro"""
    return clamp_offset(offset + int(error * 0.25))

def adjust_proportional_50(offset, error, history):
    """50% do erro"""
    return clamp_offset(offset + int(error * 0.5))

def adjust_full_error(offset, error, history):
    """100% do erro (agressivo)"""
    return clamp_offset(error)

def adjust_rolling_avg_3(offset, error, history):
    """Média dos últimos 3 erros"""
    history.append(error)
    recent = history[-3:]
    return clamp_offset(int(mean(recent)))

def adjust_rolling_avg_5(offset, error, history):
    """Média dos últimos 5 erros"""
    history.append(error)
    recent = history[-5:]
    return clamp_offset(int(mean(recent)))

def adjust_decay_80(offset, error, history):
    """Offset decai 20% + novo erro 30%"""
    new_offset = int(offset * 0.8 + error * 0.3)
    return clamp_offset(new_offset)

def adjust_reset_on_inversion(offset, error, history):
    """Reset quando erro muda de sinal"""
    if len(history) > 0:
        last = history[-1]
        if (last > 0 and error < 0) or (last < 0 and error > 0):
            history.append(error)
            return 0
    history.append(error)
    return clamp_offset(offset + int(error * 0.4))

def adjust_momentum(offset, error, history):
    """Considera momentum (se erros estão acelerando)"""
    history.append(error)
    if len(history) < 2:
        return clamp_offset(int(error * 0.3))
    accel = error - history[-2]
    return clamp_offset(offset + int(error * 0.3 + accel * 0.2))

def adjust_adaptive_rate(offset, error, history):
    """Taxa adaptativa baseada na consistência dos erros"""
    history.append(error)
    if len(history) < 3:
        rate = 0.3
    else:
        # Se erros são consistentes (mesmo sinal), taxa maior
        recent = history[-3:]
        same_sign = all(e > 0 for e in recent) or all(e < 0 for e in recent)
        rate = 0.5 if same_sign else 0.2
    return clamp_offset(offset + int(error * rate))

def adjust_weighted_history(offset, error, history):
    """Erro recente vale mais, histórico menos"""
    history.append(error)
    if len(history) < 2:
        return clamp_offset(int(error * 0.4))
    weights = [0.5, 0.3, 0.2]  # Mais recente primeiro
    recent = history[-3:]
    weighted = sum(e * w for e, w in zip(recent, weights[:len(recent)]))
    return clamp_offset(int(weighted))

def adjust_median_errors(offset, error, history):
    """Usa mediana dos erros (ignora outliers)"""
    history.append(error)
    if len(history) < 2:
        return clamp_offset(int(error * 0.4))
    return clamp_offset(int(median(history[-5:])))

def adjust_volatility_aware(offset, error, history):
    """Menos agressivo quando erros são voláteis"""
    history.append(error)
    if len(history) < 3:
        return clamp_offset(int(error * 0.3))
    vol = stdev(history[-3:]) if len(history) >= 3 else 10
    rate = 0.5 if vol < 5 else 0.3 if vol < 10 else 0.15
    return clamp_offset(offset + int(error * rate))

def adjust_hit_decay(offset, error, history):
    """Offset decai após acerto, cresce após erro"""
    # Se error == 0 significa que acertou
    if error == 0:
        return int(offset * 0.7)  # Decay 30%
    return clamp_offset(offset + int(error * 0.35))

# ============================================================
# SIMULADOR PRINCIPAL
# ============================================================

def simulate(timeline, predict_fn, adjust_fn):
    """Simula estratégia e retorna hits"""
    hits = 0
    offset = 0
    error_history = []
    
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        
        predicted_base = predict_fn(forces)
        predicted = clamp_offset(predicted_base + offset, 37)
        predicted = max(1, min(37, predicted))
        
        hit = is_hit(predicted, actual)
        if hit:
            hits += 1
            error = 0  # Para adjust_hit_decay
        else:
            error = circular_error(predicted_base, actual)
        
        offset = adjust_fn(offset, error, error_history)
    
    return hits

# ============================================================
# EXECUTAR TODAS AS COMBINAÇÕES
# ============================================================

predictors = [
    ("Regressão Linear", predict_regression),
    ("Mediana", predict_median),
    ("Média Simples", predict_mean),
    ("Peso Recente", predict_weighted_recent),
    ("Cluster Mode", predict_mode_cluster),
    ("EMA (α=0.4)", predict_ema),
]

adjusters = [
    ("Sem Ajuste", adjust_none),
    ("Fixo ±1", adjust_fixed_small),
    ("Proporcional 25%", adjust_proportional_25),
    ("Proporcional 50%", adjust_proportional_50),
    ("Erro Completo", adjust_full_error),
    ("Rolling Avg 3", adjust_rolling_avg_3),
    ("Rolling Avg 5", adjust_rolling_avg_5),
    ("Decay 80%", adjust_decay_80),
    ("Reset Inversão", adjust_reset_on_inversion),
    ("Momentum", adjust_momentum),
    ("Taxa Adaptativa", adjust_adaptive_rate),
    ("Histórico Pesado", adjust_weighted_history),
    ("Mediana Erros", adjust_median_errors),
    ("Volatility Aware", adjust_volatility_aware),
    ("Hit Decay", adjust_hit_decay),
]

print("="*80)
print("AUDITORIA COMPLETA: ESTRATÉGIAS DE FINE-TUNING")
print("="*80)
print(f"Testando {len(predictors)} preditores × {len(adjusters)} ajustadores = {len(predictors)*len(adjusters)} combinações\n")

results = []

for pred_name, pred_fn in predictors:
    for adj_name, adj_fn in adjusters:
        cw_hits = simulate(timeline_cw, pred_fn, adj_fn)
        ccw_hits = simulate(timeline_ccw, pred_fn, adj_fn)
        total = cw_hits + ccw_hits
        results.append({
            "predictor": pred_name,
            "adjuster": adj_name,
            "cw": cw_hits,
            "ccw": ccw_hits,
            "total": total,
            "pct": total * 100 // 24
        })

# Ordenar por total
results.sort(key=lambda x: x["total"], reverse=True)

# Top 20
print("\n" + "="*80)
print("TOP 20 MELHORES COMBINAÇÕES")
print("="*80)
print(f"{'Rank':<5} {'Preditor':<18} {'Ajustador':<18} {'CW':<4} {'CCW':<4} {'Total':<6} {'%':<5}")
print("-"*80)

for i, r in enumerate(results[:20], 1):
    print(f"{i:<5} {r['predictor']:<18} {r['adjuster']:<18} {r['cw']:<4} {r['ccw']:<4} {r['total']:<6} {r['pct']}%")

# Estatísticas por preditor
print("\n" + "="*80)
print("MÉDIA POR PREDITOR (com todos os ajustadores)")
print("="*80)
for pred_name, _ in predictors:
    pred_results = [r for r in results if r["predictor"] == pred_name]
    avg = sum(r["total"] for r in pred_results) / len(pred_results)
    best = max(r["total"] for r in pred_results)
    print(f"  {pred_name:<18}: média={avg:.1f}/24, melhor={best}/24")

# Estatísticas por ajustador
print("\n" + "="*80)
print("MÉDIA POR AJUSTADOR (com todos os preditores)")
print("="*80)
for adj_name, _ in adjusters:
    adj_results = [r for r in results if r["adjuster"] == adj_name]
    avg = sum(r["total"] for r in adj_results) / len(adj_results)
    best = max(r["total"] for r in adj_results)
    print(f"  {adj_name:<18}: média={avg:.1f}/24, melhor={best}/24")

# VENCEDOR
print("\n" + "="*80)
print("🏆 VENCEDOR ABSOLUTO")
print("="*80)
winner = results[0]
print(f"  Preditor: {winner['predictor']}")
print(f"  Ajustador: {winner['adjuster']}")
print(f"  CW: {winner['cw']}/12 | CCW: {winner['ccw']}/12")
print(f"  TOTAL: {winner['total']}/24 ({winner['pct']}%)")

# Comparar com original
original_cw = simulate(timeline_cw, predict_regression, lambda o,e,h: -8)
original_ccw = simulate(timeline_ccw, predict_regression, lambda o,e,h: +4)
print(f"\n  vs Original (Regressão + offset fixo): {original_cw + original_ccw}/24")
print(f"  MELHORIA: +{winner['total'] - (original_cw + original_ccw)} hits")

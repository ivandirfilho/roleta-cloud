# BACKTEST COMPLETO: Engenharia Reversa com 40+ jogadas
# Comparativo: SEM técnica vs COM cada técnica

from statistics import mean, median
from math import sqrt

print("="*120)
print("🎰 BACKTEST COMPLETO - ENGENHARIA REVERSA DE 40 JOGADAS")
print("="*120)

# ============================================================================
# DADOS REAIS DO SISTEMA (20 forças por direção = 40 total)
# Índice 0 = mais recente
# ============================================================================

# Dados de audit_detailed.py (mais completos)
timeline_cw_new = [25, 27, 14, 9, 20, 6, 20, 36, 27, 28, 30, 28, 0, 17, 27, 33, 14, 12, 13, 22]
timeline_ccw_new = [36, 31, 16, 24, 28, 20, 27, 31, 4, 1, 13, 7, 30, 36, 11, 3, 7, 25, 35, 29]

# Dados de simulation.py (diferentes, outra sessão)
timeline_cw_old = [30, 28, 0, 17, 27, 33, 14, 12, 13, 22, 20, 35, 36, 8, 19, 3, 3, 4, 8, 3]
timeline_ccw_old = [13, 7, 30, 36, 11, 3, 7, 25, 35, 29, 33, 34, 25, 1, 7, 17, 8, 0, 25, 9]

# Performance real (últimos 12 de cada, do audit_detailed.py)
performance_cw_real = [True, False, False, True, False, False, True, True, True, False, False, False]
performance_ccw_real = [False, False, True, False, True, False, True, False, True, False, False, True]

print(f"\n📊 DADOS DISPONÍVEIS:")
print(f"   Timeline CW nova:  {len(timeline_cw_new)} forças")
print(f"   Timeline CCW nova: {len(timeline_ccw_new)} forças")
print(f"   Timeline CW antiga:  {len(timeline_cw_old)} forças")
print(f"   Timeline CCW antiga: {len(timeline_ccw_old)} forças")
print(f"   Total: {len(timeline_cw_new) + len(timeline_ccw_new) + len(timeline_cw_old) + len(timeline_ccw_old)} pontos de dados")

# ============================================================================
# FUNÇÕES DE PREDIÇÃO (para simular acerto/erro)
# ============================================================================

def linear_regression_predict(forces_5):
    """Regressão linear para prever próxima força"""
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

def is_hit(predicted, actual, tolerance=8):
    """Verifica se está dentro de ±8 posições (17 números)"""
    diff = abs(predicted - actual)
    diff = min(diff, 37 - diff)
    return diff <= tolerance

def circular_error(predicted, actual):
    error = actual - predicted
    if error > 18: error -= 37
    elif error < -18: error += 37
    return error

# ============================================================================
# SIMULAR PERFORMANCE A PARTIR DOS DADOS (quando não temos o real)
# ============================================================================

def simulate_performance(timeline, offset=0):
    """Simula performance baseado nas forças da timeline"""
    performance = []
    for i in range(min(15, len(timeline) - 5)):  # Até 15 jogadas
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        if len(forces) < 5:
            continue
        predicted = linear_regression_predict(forces) + offset
        predicted = max(1, min(37, predicted))
        performance.append(is_hit(predicted, actual))
    return performance

# Gerar performance simulada para os dados antigos
perf_cw_old = simulate_performance(timeline_cw_old, offset=-4)
perf_ccw_old = simulate_performance(timeline_ccw_old, offset=+4)

# Usar performance real para dados novos
perf_cw_new = performance_cw_real.copy()
perf_ccw_new = performance_ccw_real.copy()

# Combinar tudo (novo + antigo = ~24-30 jogadas por direção)
all_perf_cw = perf_cw_new + perf_cw_old
all_perf_ccw = perf_ccw_new + perf_ccw_old

print(f"\n📈 PERFORMANCE COMBINADA:")
print(f"   CW total: {len(all_perf_cw)} jogadas, {sum(all_perf_cw)} acertos ({sum(all_perf_cw)*100//len(all_perf_cw)}%)")
print(f"   CCW total: {len(all_perf_ccw)} jogadas, {sum(all_perf_ccw)} acertos ({sum(all_perf_ccw)*100//len(all_perf_ccw)}%)")

# ============================================================================
# TÉCNICAS DE DECISÃO
# ============================================================================

def technique_always_bet(perf):
    """BASELINE: Sempre aposta (sem técnica)"""
    return True, "SEMPRE", {"note": "Aposta em 100% das oportunidades"}

def technique_triple_rate(perf):
    """Técnica 1: Triple Rate Convergence"""
    if len(perf) < 4:
        return True, "INSUF", {}
    c4 = sum(perf[:4]) / 4
    m6 = sum(perf[:6]) / 6 if len(perf) >= 6 else c4
    l12 = sum(perf[:12]) / 12 if len(perf) >= 12 else m6
    
    if c4 >= m6 >= l12:
        return True, "CRESCENTE", {"c4": c4, "m6": m6, "l12": l12}
    elif c4 > m6:
        return True, "RECUPERA", {"c4": c4, "m6": m6, "l12": l12}
    else:
        return False, "DECRESCE", {"c4": c4, "m6": m6, "l12": l12}

def technique_weighted(perf, threshold=0.35):
    """Técnica 2: Weighted Momentum Score"""
    if len(perf) < 4:
        return True, "INSUF", {}
    weights = [1.0, 0.9, 0.8, 0.7, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05][:len(perf)]
    score = sum(w * (1 if h else 0) for w, h in zip(weights, perf)) / sum(weights)
    if score >= threshold:
        return True, "ACIMA", {"score": score, "threshold": threshold}
    else:
        return False, "ABAIXO", {"score": score, "threshold": threshold}

def technique_streak(perf, cold_threshold=3):
    """Técnica 3: Streak Analysis"""
    if len(perf) < 2:
        return True, "INSUF", {}
    
    streak = 0
    streak_type = perf[0]
    for h in perf:
        if h == streak_type:
            streak += 1
        else:
            break
    
    hot = streak if streak_type else 0
    cold = streak if not streak_type else 0
    
    if cold >= cold_threshold:
        return False, "COLD", {"hot": hot, "cold": cold}
    else:
        return True, "OK", {"hot": hot, "cold": cold}

def technique_zscore(perf, expected=5/37):
    """Técnica 4: Z-Score"""
    if len(perf) < 4:
        return True, "INSUF", {}
    observed = sum(perf) / len(perf)
    std_dev = sqrt(expected * (1 - expected) / len(perf))
    if std_dev == 0:
        return True, "NEUTRO", {}
    z = (observed - expected) / std_dev
    if z > 0.5:
        return True, "ACIMA", {"z": z}
    elif z < -0.5:
        return False, "ABAIXO", {"z": z}
    else:
        return True, "NORMAL", {"z": z}

def technique_markov(perf):
    """Técnica 5: Markov Chain"""
    if len(perf) < 6:
        return True, "INSUF", {}
    
    hh = hm = mh = mm = 0
    for i in range(len(perf) - 1):
        current, previous = perf[i], perf[i + 1]
        if previous and current: hh += 1
        elif previous and not current: hm += 1
        elif not previous and current: mh += 1
        else: mm += 1
    
    p_hh = hh / (hh + hm) if (hh + hm) > 0 else 0.5
    p_mh = mh / (mh + mm) if (mh + mm) > 0 else 0.5
    
    last_was_hit = perf[0]
    p_next = p_hh if last_was_hit else p_mh
    
    if p_next > 0.35:
        return True, "FAVORAVEL", {"p_hh": p_hh, "p_mh": p_mh}
    else:
        return False, "DESFAV", {"p_hh": p_hh, "p_mh": p_mh}

def technique_adaptive(perf, initial=0.30):
    """Técnica 6: Adaptive Threshold"""
    if len(perf) < 4:
        return True, "INSUF", {}
    
    threshold = initial
    for i in range(len(perf) - 1, -1, -1):
        if perf[i]:
            threshold *= 0.95
        else:
            threshold = min(0.50, threshold * 1.05)
    
    c4_rate = sum(perf[:4]) / 4
    if c4_rate >= threshold:
        return True, "ACIMA", {"threshold": threshold, "c4": c4_rate}
    else:
        return False, "ABAIXO", {"threshold": threshold, "c4": c4_rate}

def technique_hybrid(perf):
    """Técnica 7: Híbrido v2 (Streak + Triple + Weighted)"""
    if len(perf) < 4:
        return True, "INSUF", {}
    
    # VETO: Cold streak
    streak_result = technique_streak(perf)
    if streak_result[1] == "COLD":
        return False, "COLD_VETO", {}
    
    # Triple Rate
    c4 = sum(perf[:4]) / 4
    m6 = sum(perf[:6]) / 6 if len(perf) >= 6 else c4
    l12 = sum(perf[:12]) / 12 if len(perf) >= 12 else m6
    
    # Weighted
    weights = [1.0, 0.9, 0.8, 0.7, 0.5, 0.4][:len(perf)]
    wm = sum(w * (1 if h else 0) for w, h in zip(weights, perf)) / sum(weights)
    
    if c4 >= m6 and wm > 0.35:
        return True, "BOM", {"c4": c4, "wm": wm}
    elif wm < 0.30:
        return False, "FRACO", {"c4": c4, "wm": wm}
    else:
        return True, "NEUTRO", {"c4": c4, "wm": wm}

# ============================================================================
# EXECUTAR BACKTEST COMPLETO
# ============================================================================

def run_complete_backtest(performance, direction_name):
    """Executa backtest passo a passo retornando detalhes"""
    
    techniques = {
        "SEM TÉCNICA (Baseline)": technique_always_bet,
        "Triple Rate": technique_triple_rate,
        "Weighted Momentum": technique_weighted,
        "Streak Analysis": technique_streak,
        "Z-Score": technique_zscore,
        "Markov Chain": technique_markov,
        "Adaptive Threshold": technique_adaptive,
        "Híbrido v2": technique_hybrid,
    }
    
    results = {name: {"bets": 0, "hits": 0, "skips": 0, "avoided_errors": 0, "missed_ops": 0, "details": []} 
               for name in techniques}
    
    # Para cada decisão possível (precisa de histórico mínimo de 4)
    for i in range(len(performance) - 4):
        history = performance[i+1:]  # Histórico antes desta jogada
        actual_result = performance[i]  # O que realmente aconteceu
        
        for name, func in techniques.items():
            should_bet, reason, stats = func(history)
            
            detail = {
                "index": i + 1,
                "should_bet": should_bet,
                "reason": reason,
                "actual": actual_result,
                "history_preview": history[:4]
            }
            
            if should_bet:
                results[name]["bets"] += 1
                if actual_result:
                    results[name]["hits"] += 1
                    detail["outcome"] = "✅ ACERTOU"
                else:
                    detail["outcome"] = "❌ ERROU"
            else:
                results[name]["skips"] += 1
                if not actual_result:
                    results[name]["avoided_errors"] += 1
                    detail["outcome"] = "🛡️ EVITOU ERRO"
                else:
                    results[name]["missed_ops"] += 1
                    detail["outcome"] = "⚠️ PERDEU OP"
            
            results[name]["details"].append(detail)
    
    return results

print("\n" + "="*120)
print("🧪 EXECUTANDO BACKTEST COMPLETO")
print("="*120)

results_cw = run_complete_backtest(all_perf_cw, "CW")
results_ccw = run_complete_backtest(all_perf_ccw, "CCW")

# ============================================================================
# COMBINAR RESULTADOS
# ============================================================================

combined = {}
for name in results_cw:
    combined[name] = {
        "bets": results_cw[name]["bets"] + results_ccw[name]["bets"],
        "hits": results_cw[name]["hits"] + results_ccw[name]["hits"],
        "skips": results_cw[name]["skips"] + results_ccw[name]["skips"],
        "avoided_errors": results_cw[name]["avoided_errors"] + results_ccw[name]["avoided_errors"],
        "missed_ops": results_cw[name]["missed_ops"] + results_ccw[name]["missed_ops"],
    }

# ============================================================================
# TABELA PRINCIPAL DE RESULTADOS
# ============================================================================

print("\n" + "="*120)
print("📊 RESULTADOS CONSOLIDADOS - COMPARATIVO COMPLETO")
print("="*120)

# Calcular métricas para baseline
baseline = combined["SEM TÉCNICA (Baseline)"]
baseline_bets = baseline["bets"]
baseline_hits = baseline["hits"]
baseline_errors = baseline_bets - baseline_hits

print(f"\n{'TÉCNICA':<25} {'APOSTAS':>8} {'ACERTOS':>8} {'ERROS':>8} {'TAXA%':>8} {'PULADAS':>8} {'EVITOU':>8} {'PERDEU':>8} {'SCORE':>8}")
print("-"*105)

scores = []
for name, data in combined.items():
    bets = data["bets"]
    hits = data["hits"]
    errors = bets - hits
    skips = data["skips"]
    avoided = data["avoided_errors"]
    missed = data["missed_ops"]
    
    rate = (hits / bets * 100) if bets > 0 else 0
    
    # Score: acertos*2 + erros_evitados - oportunidades_perdidas*0.5
    score = hits * 2 + avoided * 1.5 - missed * 0.5
    
    scores.append((name, score, rate, bets, hits, errors, skips, avoided, missed))
    
    print(f"{name:<25} {bets:>8} {hits:>8} {errors:>8} {rate:>7.1f}% {skips:>8} {avoided:>8} {missed:>8} {score:>8.1f}")

# ============================================================================
# ANÁLISE COMPARATIVA COM BASELINE
# ============================================================================

print("\n" + "="*120)
print("📈 COMPARATIVO COM BASELINE (SEM TÉCNICA)")
print("="*120)

print(f"\n🎯 BASELINE: {baseline_hits} acertos em {baseline_bets} apostas ({baseline_hits*100//baseline_bets}%) | {baseline_errors} erros")
print("-"*105)

for name, score, rate, bets, hits, errors, skips, avoided, missed in scores:
    if name == "SEM TÉCNICA (Baseline)":
        continue
    
    # Comparação
    hit_diff = hits - baseline_hits
    error_diff = baseline_errors - errors - avoided  # Erros evitados vs baseline
    
    if avoided > 0:
        eficiencia = f"Evitou {avoided} erros"
    else:
        eficiencia = "Sem proteção"
    
    emoji = "✅" if hit_diff >= 0 and avoided > 0 else "⚠️" if hit_diff >= 0 else "❌"
    
    print(f"{emoji} {name:<23} | Apostas: {bets:>3} | Taxa: {rate:>5.1f}% | Acertos: {hits:>2} ({hit_diff:+d}) | {eficiencia}")

# ============================================================================
# RANKING FINAL
# ============================================================================

print("\n" + "="*120)
print("🏆 RANKING FINAL (por Score)")
print("="*120)

scores.sort(key=lambda x: x[1], reverse=True)
for i, (name, score, rate, bets, hits, errors, skips, avoided, missed) in enumerate(scores):
    medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
    print(f"{medal} #{i+1} {name:<25} Score: {score:>6.1f} | Taxa: {rate:>5.1f}% | {hits}/{bets} apostas | {avoided} erros evitados")

# ============================================================================
# QUANDO VALE A PENA CADA TÉCNICA?
# ============================================================================

print("\n" + "="*120)
print("🔍 ANÁLISE: QUANDO E PORQUE VALE A PENA CADA TÉCNICA?")
print("="*120)

analyses = [
    ("SEM TÉCNICA (Baseline)", 
     "REFERÊNCIA - Aposta em 100% das oportunidades",
     "Use como referência para comparar outras técnicas.",
     "Não protege contra cold streaks nem períodos ruins."),
    
    ("Triple Rate",
     "Analisa tendência em 3 timeframes (C4 > M6 > L12)",
     "Vale quando: Momentum está claramente crescendo. Bom para detectar recuperação.",
     "Não vale quando: Mercado volátil com muitas inversões de tendência."),
    
    ("Weighted Momentum",
     "Score ponderado favorecendo resultados recentes",
     "Vale quando: Resultados recentes são bons indicadores do próximo.",
     "Não vale quando: Padrão errático com alternância Hit-Miss-Hit-Miss."),
    
    ("Streak Analysis",
     "Detecta sequências de acertos (hot) ou erros (cold)",
     "Vale quando: Cold streaks são frequentes. MELHOR PROTEÇÃO contra perdas consecutivas.",
     "Não vale quando: Resultados são aleatórios sem padrão de sequência."),
    
    ("Z-Score",
     "Compara performance vs baseline estatístico (13.5%)",
     "Vale quando: Quer decisão baseada em estatística rigorosa.",
     "Não vale quando: Poucos dados (N<12) - Z-score não é confiável."),
    
    ("Markov Chain",
     "Probabilidade de acerto baseada no último resultado",
     "Vale quando: Existe dependência temporal (P(Hit|Hit) ≠ P(Hit|Miss)).",
     "Não vale quando: Resultados são independentes (roleta física real é assim)."),
    
    ("Adaptive Threshold",
     "Threshold que se ajusta à performance histórica",
     "Vale quando: Performance varia muito entre mesas/dealers diferentes.",
     "Não vale quando: Precisa de muitos dados para calibrar bem."),
    
    ("Híbrido v2",
     "Combina Streak (veto) + Triple Rate + Weighted",
     "Vale quando: Quer equilíbrio entre proteção e aproveitamento.",
     "Não vale quando: Técnicas individuais conflitam entre si."),
]

for name, descricao, quando_vale, quando_nao_vale in analyses:
    print(f"\n{'='*80}")
    print(f"📌 {name}")
    print(f"{'='*80}")
    print(f"   📝 {descricao}")
    print(f"   ✅ {quando_vale}")
    print(f"   ❌ {quando_nao_vale}")

# ============================================================================
# RECOMENDAÇÃO FINAL BASEADA NOS DADOS
# ============================================================================

print("\n" + "="*120)
print("🎯 RECOMENDAÇÃO FINAL BASEADA NOS DADOS REAIS")
print("="*120)

# Encontrar melhor técnica (excluindo baseline)
best_technique = None
best_score = -999
for name, score, rate, bets, hits, errors, skips, avoided, missed in scores:
    if name != "SEM TÉCNICA (Baseline)" and score > best_score:
        best_score = score
        best_technique = (name, score, rate, bets, hits, avoided)

baseline_score = [s for s in scores if s[0] == "SEM TÉCNICA (Baseline)"][0][1]

if best_technique:
    name, score, rate, bets, hits, avoided = best_technique
    print(f"""
    🏆 MELHOR TÉCNICA: {name}
    
    📊 Métricas:
       - Score: {score:.1f} (vs {baseline_score:.1f} do baseline)
       - Taxa de acerto: {rate:.1f}%
       - Apostas realizadas: {bets}
       - Acertos: {hits}
       - Erros evitados: {avoided}
    
    💡 Por que esta técnica?
       - Maior score combinando acertos e proteção
       - Evita apostas durante períodos ruins
       - Bom equilíbrio entre oportunidades aproveitadas e riscos evitados
    """)

print("\n" + "="*120)
print("✅ ANÁLISE COMPLETA CONCLUÍDA")
print("="*120)

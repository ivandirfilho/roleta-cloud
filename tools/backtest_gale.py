# ANÁLISE DE GALE/MARTINGALE - Qual técnica evita gales mais longos?
# Engenharia reversa para medir drawdown máximo e progressão de gale

from statistics import mean
from math import sqrt

print("="*120)
print("🎲 ANÁLISE DE GALE - QUAL TÉCNICA EVITA GALES MAIS LONGOS?")
print("="*120)

# ============================================================================
# DADOS REAIS DO SISTEMA
# ============================================================================

# Performance real e simulada combinada (mesmo do backtest anterior)
timeline_cw_new = [25, 27, 14, 9, 20, 6, 20, 36, 27, 28, 30, 28, 0, 17, 27, 33, 14, 12, 13, 22]
timeline_ccw_new = [36, 31, 16, 24, 28, 20, 27, 31, 4, 1, 13, 7, 30, 36, 11, 3, 7, 25, 35, 29]
timeline_cw_old = [30, 28, 0, 17, 27, 33, 14, 12, 13, 22, 20, 35, 36, 8, 19, 3, 3, 4, 8, 3]
timeline_ccw_old = [13, 7, 30, 36, 11, 3, 7, 25, 35, 29, 33, 34, 25, 1, 7, 17, 8, 0, 25, 9]

performance_cw_real = [True, False, False, True, False, False, True, True, True, False, False, False]
performance_ccw_real = [False, False, True, False, True, False, True, False, True, False, False, True]

def linear_regression_predict(forces_5):
    n = len(forces_5)
    y = list(reversed(forces_5))
    x = list(range(n))
    x_mean, y_mean = sum(x) / n, sum(y) / n
    num = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    den = sum((x[i] - x_mean) ** 2 for i in range(n))
    slope = num / den if den else 0
    return max(1, min(37, int(round(y_mean - slope * x_mean + slope * n))))

def is_hit(predicted, actual, tolerance=8):
    diff = min(abs(predicted - actual), 37 - abs(predicted - actual))
    return diff <= tolerance

def simulate_performance(timeline, offset=0):
    performance = []
    for i in range(min(15, len(timeline) - 5)):
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        if len(forces) < 5:
            continue
        predicted = max(1, min(37, linear_regression_predict(forces) + offset))
        performance.append(is_hit(predicted, actual))
    return performance

# Gerar performance completa
perf_cw = performance_cw_real + simulate_performance(timeline_cw_old, -4)
perf_ccw = performance_ccw_real + simulate_performance(timeline_ccw_old, +4)

# Intercalar CW e CCW (como acontece em jogo real)
all_performance = []
min_len = min(len(perf_cw), len(perf_ccw))
for i in range(min_len):
    all_performance.append(("CW", perf_cw[i]))
    all_performance.append(("CCW", perf_ccw[i]))

print(f"\n📊 DADOS:")
print(f"   Total de jogadas: {len(all_performance)}")
print(f"   Acertos totais: {sum(1 for _, h in all_performance if h)} ({sum(1 for _, h in all_performance if h)*100//len(all_performance)}%)")

# ============================================================================
# CONFIGURAÇÃO DO SISTEMA MARTINGALE
# ============================================================================

GALE_CONFIG = {
    1: {"aposta": 17, "multiplicador": "1x"},
    2: {"aposta": 34, "multiplicador": "2x"},
    3: {"aposta": 68, "multiplicador": "4x"},
}
WINDOW_SIZE = 5
MIN_HITS_TO_PASS = 3

print(f"\n🎰 CONFIGURAÇÃO MARTINGALE:")
for level, cfg in GALE_CONFIG.items():
    print(f"   Gale {level}: R${cfg['aposta']} ({cfg['multiplicador']})")
print(f"   Janela: {WINDOW_SIZE} jogadas, mínimo {MIN_HITS_TO_PASS} acertos para manter/descer")

# ============================================================================
# TÉCNICAS DE DECISÃO
# ============================================================================

def technique_always_bet(perf):
    return True, "SEMPRE"

def technique_triple_rate(perf):
    if len(perf) < 4: return True, "INSUF"
    c4 = sum(perf[:4]) / 4
    m6 = sum(perf[:6]) / 6 if len(perf) >= 6 else c4
    l12 = sum(perf[:12]) / 12 if len(perf) >= 12 else m6
    if c4 >= m6: return True, "APOSTAR"
    return False, "PULAR"

def technique_weighted(perf, threshold=0.35):
    if len(perf) < 4: return True, "INSUF"
    weights = [1.0, 0.9, 0.8, 0.7, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05][:len(perf)]
    score = sum(w * (1 if h else 0) for w, h in zip(weights, perf)) / sum(weights)
    return score >= threshold, "APOSTAR" if score >= threshold else "PULAR"

def technique_streak(perf, cold_threshold=3):
    if len(perf) < 2: return True, "INSUF"
    streak, streak_type = 0, perf[0]
    for h in perf:
        if h == streak_type: streak += 1
        else: break
    if not streak_type and streak >= cold_threshold:
        return False, "COLD"
    return True, "OK"

def technique_zscore(perf):
    if len(perf) < 4: return True, "INSUF"
    observed = sum(perf) / len(perf)
    expected = 5/37
    std = sqrt(expected * (1 - expected) / len(perf))
    if std == 0: return True, "NEUTRO"
    z = (observed - expected) / std
    return z > -0.5, "APOSTAR" if z > -0.5 else "PULAR"

def technique_markov(perf):
    if len(perf) < 6: return True, "INSUF"
    hh = hm = mh = mm = 0
    for i in range(len(perf) - 1):
        c, p = perf[i], perf[i + 1]
        if p and c: hh += 1
        elif p and not c: hm += 1
        elif not p and c: mh += 1
        else: mm += 1
    p_hh = hh / (hh + hm) if (hh + hm) > 0 else 0.5
    p_mh = mh / (mh + mm) if (mh + mm) > 0 else 0.5
    p_next = p_hh if perf[0] else p_mh
    return p_next > 0.35, "APOSTAR" if p_next > 0.35 else "PULAR"

def technique_adaptive(perf):
    if len(perf) < 4: return True, "INSUF"
    threshold = 0.30
    for i in range(len(perf) - 1, -1, -1):
        threshold = threshold * 0.95 if perf[i] else min(0.50, threshold * 1.05)
    c4 = sum(perf[:4]) / 4
    return c4 >= threshold, "APOSTAR" if c4 >= threshold else "PULAR"

def technique_hybrid(perf):
    if len(perf) < 4: return True, "INSUF"
    # VETO cold streak
    streak, streak_type = 0, perf[0]
    for h in perf:
        if h == streak_type: streak += 1
        else: break
    if not streak_type and streak >= 3:
        return False, "COLD"
    # Combined
    c4 = sum(perf[:4]) / 4
    weights = [1.0, 0.9, 0.8, 0.7, 0.5, 0.4][:len(perf)]
    wm = sum(w * (1 if h else 0) for w, h in zip(weights, perf)) / sum(weights)
    if c4 >= 0.25 and wm >= 0.30:
        return True, "APOSTAR"
    return False, "PULAR"

# ============================================================================
# SIMULAÇÃO DE GALE COM CADA TÉCNICA
# ============================================================================

def simulate_gale(performance_sequence, technique_func, technique_name):
    """Simula progressão de Gale com uma técnica específica"""
    
    # Estado do Gale
    gale_level = 1
    window_hits = 0
    window_count = 0
    total_stops = 0
    
    # Métricas
    max_gale_reached = 1
    gale_history = []  # Lista de níveis atingidos
    consecutive_losses = 0
    max_consecutive_losses = 0
    drawdown = 0
    max_drawdown = 0
    balance = 0
    min_balance = 0
    
    # Histórico de performance para a técnica
    perf_history = []
    
    # Log detalhado
    log = []
    
    for i, (direction, actual_hit) in enumerate(performance_sequence):
        # Atualizar histórico
        perf_history.insert(0, actual_hit)
        if len(perf_history) > 12:
            perf_history.pop()
        
        # Técnica decide se devemos apostar
        should_bet, reason = technique_func(perf_history[1:] if len(perf_history) > 1 else [])
        
        if not should_bet:
            log.append({
                "i": i + 1,
                "action": "PULAR",
                "reason": reason,
                "gale": gale_level,
                "actual": actual_hit,
                "balance": balance
            })
            continue
        
        # Apostar
        bet_amount = GALE_CONFIG[gale_level]["aposta"]
        
        if actual_hit:
            # GANHOU!
            win = bet_amount * 35  # Payout da roleta
            balance += win - bet_amount
            window_hits += 1
            consecutive_losses = 0
        else:
            # PERDEU
            balance -= bet_amount
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        
        window_count += 1
        
        # Atualizar drawdown
        if balance < min_balance:
            min_balance = balance
            max_drawdown = abs(min_balance)
        
        # Registrar nível de gale
        gale_history.append(gale_level)
        max_gale_reached = max(max_gale_reached, gale_level)
        
        log.append({
            "i": i + 1,
            "action": "APOSTAR",
            "gale": gale_level,
            "bet": bet_amount,
            "actual": actual_hit,
            "window": f"{window_hits}/{window_count}",
            "balance": balance,
            "consec_loss": consecutive_losses
        })
        
        # Verificar fim da janela
        if window_count >= WINDOW_SIZE:
            if window_hits >= MIN_HITS_TO_PASS:
                # Sucesso - volta ou mantém Gale 1
                if gale_level > 1:
                    gale_level = 1
            else:
                # Falha - sobe nível ou STOP
                if gale_level < 3:
                    gale_level += 1
                else:
                    total_stops += 1
                    gale_level = 1
            
            window_hits = 0
            window_count = 0
    
    return {
        "name": technique_name,
        "max_gale": max_gale_reached,
        "max_consecutive_losses": max_consecutive_losses,
        "max_drawdown": max_drawdown,
        "total_stops": total_stops,
        "final_balance": balance,
        "gale_history": gale_history,
        "bets_made": len(gale_history),
        "log": log
    }

# ============================================================================
# EXECUTAR SIMULAÇÃO PARA TODAS AS TÉCNICAS
# ============================================================================

print("\n" + "="*120)
print("🎲 SIMULAÇÃO DE GALE - ENGENHARIA REVERSA")
print("="*120)

techniques = [
    ("SEM TÉCNICA (Baseline)", technique_always_bet),
    ("Triple Rate", technique_triple_rate),
    ("Weighted Momentum", technique_weighted),
    ("Streak Analysis", technique_streak),
    ("Z-Score", technique_zscore),
    ("Markov Chain", technique_markov),
    ("Adaptive Threshold", technique_adaptive),
    ("Híbrido v2", technique_hybrid),
]

results = []
for name, func in techniques:
    result = simulate_gale(all_performance, func, name)
    results.append(result)

# ============================================================================
# TABELA PRINCIPAL DE RESULTADOS
# ============================================================================

print(f"\n{'TÉCNICA':<25} {'APOSTAS':>8} {'MAX GALE':>10} {'PERDAS SEQ':>12} {'DRAWDOWN':>12} {'STOPS':>8} {'BALANÇO':>10}")
print("-"*95)

for r in results:
    print(f"{r['name']:<25} {r['bets_made']:>8} {r['max_gale']:>10} {r['max_consecutive_losses']:>12} R${r['max_drawdown']:>10} {r['total_stops']:>8} R${r['final_balance']:>9}")

# ============================================================================
# ANÁLISE DE GALE POR TÉCNICA
# ============================================================================

print("\n" + "="*120)
print("📊 DISTRIBUIÇÃO DE NÍVEIS DE GALE")
print("="*120)

for r in results:
    if not r['gale_history']:
        print(f"\n{r['name']}: Nenhuma aposta realizada")
        continue
    
    g1 = r['gale_history'].count(1)
    g2 = r['gale_history'].count(2)
    g3 = r['gale_history'].count(3)
    total = len(r['gale_history'])
    
    print(f"\n{r['name']}:")
    print(f"   Gale 1 (R$17): {g1:>3} apostas ({g1*100//total:>3}%) {'█' * (g1*30//total)}")
    print(f"   Gale 2 (R$34): {g2:>3} apostas ({g2*100//total if total else 0:>3}%) {'█' * (g2*30//total if total else 0)}")
    print(f"   Gale 3 (R$68): {g3:>3} apostas ({g3*100//total if total else 0:>3}%) {'█' * (g3*30//total if total else 0)}")

# ============================================================================
# RANKING - QUAL TÉCNICA EVITA GALES MAIS LONGOS?
# ============================================================================

print("\n" + "="*120)
print("🏆 RANKING - QUAL TÉCNICA EVITA GALES MAIS LONGOS?")
print("="*120)

# Score: menor max_gale + menor consecutive_losses + menor drawdown
# Normalizar e combinar
for r in results:
    r['gale_score'] = (4 - r['max_gale']) * 10 + (10 - r['max_consecutive_losses']) * 5 - r['total_stops'] * 20

results_sorted = sorted(results, key=lambda x: x['gale_score'], reverse=True)

print(f"\n{'#':<3} {'TÉCNICA':<25} {'MAX GALE':>10} {'PERDAS SEQ':>12} {'STOPS':>8} {'GALE SCORE':>12}")
print("-"*75)

for i, r in enumerate(results_sorted):
    medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
    print(f"{medal} {i+1} {r['name']:<25} {r['max_gale']:>10} {r['max_consecutive_losses']:>12} {r['total_stops']:>8} {r['gale_score']:>12}")

# ============================================================================
# ANÁLISE DETALHADA DA MELHOR TÉCNICA PARA GALE
# ============================================================================

best = results_sorted[0]
baseline = [r for r in results if r['name'] == "SEM TÉCNICA (Baseline)"][0]

print("\n" + "="*120)
print(f"📈 ANÁLISE DETALHADA: {best['name']} vs BASELINE")
print("="*120)

print(f"""
    📊 COMPARATIVO:
    
    Métrica                    | BASELINE          | {best['name']:<20}
    ---------------------------|-------------------|---------------------
    Máximo Gale atingido       | Gale {baseline['max_gale']}            | Gale {best['max_gale']}
    Perdas consecutivas máx    | {baseline['max_consecutive_losses']}                 | {best['max_consecutive_losses']}
    STOPs (Gale 3 falhou)      | {baseline['total_stops']}                 | {best['total_stops']}
    Drawdown máximo            | R${baseline['max_drawdown']}             | R${best['max_drawdown']}
    Total de apostas           | {baseline['bets_made']}                | {best['bets_made']}
""")

# ============================================================================
# QUANDO COLD STREAK SERIA EVITADO
# ============================================================================

print("\n" + "="*120)
print("🔍 ANÁLISE: SEQUÊNCIAS DE PERDAS (Cold Streaks)")
print("="*120)

# Encontrar cold streaks no baseline
cold_streaks = []
current_streak = 0
for entry in baseline['log']:
    if entry['action'] == 'APOSTAR':
        if not entry['actual']:
            current_streak += 1
        else:
            if current_streak >= 2:
                cold_streaks.append(current_streak)
            current_streak = 0

if current_streak >= 2:
    cold_streaks.append(current_streak)

print(f"\n   Cold streaks no BASELINE: {cold_streaks}")
print(f"   Total de cold streaks (2+ perdas): {len(cold_streaks)}")
print(f"   Maior cold streak: {max(cold_streaks) if cold_streaks else 0} perdas consecutivas")

# Verificar quais teriam sido evitados por cada técnica
print(f"\n   📊 Quantos cold streaks cada técnica evitaria:")
for r in results:
    if r['name'] == "SEM TÉCNICA (Baseline)":
        continue
    avoided = baseline['max_consecutive_losses'] - r['max_consecutive_losses']
    protection = "🛡️" if r['max_consecutive_losses'] < baseline['max_consecutive_losses'] else "⚠️"
    print(f"   {protection} {r['name']:<23}: Max perdas seq = {r['max_consecutive_losses']} ({'+0' if avoided <= 0 else f'-{avoided}'} vs baseline)")

# ============================================================================
# RECOMENDAÇÃO PARA USO COM GALE
# ============================================================================

print("\n" + "="*120)
print("🎯 RECOMENDAÇÃO PARA USO COM SISTEMA GALE")
print("="*120)

# Encontrar a técnica com menos progressão de gale
best_for_gale = min(results, key=lambda x: (x['max_gale'], x['max_consecutive_losses'], x['total_stops']))

print(f"""
    🏆 MELHOR TÉCNICA PARA MINIMIZAR GALES LONGOS:
    
    ► {best_for_gale['name']}
    
    📊 Por que?
    - Máximo Gale atingido: {best_for_gale['max_gale']} (menor = melhor)
    - Máximo perdas consecutivas: {best_for_gale['max_consecutive_losses']} (menor = melhor)  
    - STOPs (Gale 3 falhou): {best_for_gale['total_stops']} (menor = melhor)
    
    💡 ESTRATÉGIA RECOMENDADA:
    
    1. Usar {best_for_gale['name']} para decidir quando apostar
    2. Quando a técnica diz "PULAR":
       - NÃO apostar (não incrementa janela do Gale)
       - Evita entrar em cold streak
    3. Quando a técnica diz "APOSTAR":
       - Seguir com a aposta no nível de Gale atual
       - Maior chance de acerto (momentum favorável)
    
    ⚠️ IMPORTANTE:
    - Mesmo pulando, você pode perder oportunidades de acerto
    - A técnica é CONSERVADORA - prioriza proteção sobre ganho máximo
    - Ideal para sessões longas onde preservar banca é prioridade
""")

# ============================================================================
# SIMULAÇÃO VISUAL DE PROGRESSÃO
# ============================================================================

print("\n" + "="*120)
print("📉 PROGRESSÃO VISUAL DO GALE (Primeiras 30 jogadas)")
print("="*120)

print(f"\n{'#':<4} {'BASELINE':<30} | {best_for_gale['name']:<30}")
print("-"*70)

base_log = baseline['log'][:30]
best_log = best_for_gale['log'][:30]

for i in range(min(30, max(len(base_log), len(best_log)))):
    # Baseline
    if i < len(base_log):
        b = base_log[i]
        if b['action'] == 'APOSTAR':
            b_str = f"G{b['gale']} {'✅' if b['actual'] else '❌'} {b.get('window', '')}"
        else:
            b_str = f"⏸️ PULAR"
    else:
        b_str = "-"
    
    # Best
    if i < len(best_log):
        t = best_log[i]
        if t['action'] == 'APOSTAR':
            t_str = f"G{t['gale']} {'✅' if t['actual'] else '❌'} {t.get('window', '')}"
        else:
            t_str = f"⏸️ PULAR ({t['reason']})"
    else:
        t_str = "-"
    
    print(f"{i+1:<4} {b_str:<30} | {t_str:<30}")

print("\n" + "="*120)
print("✅ ANÁLISE DE GALE CONCLUÍDA")
print("="*120)

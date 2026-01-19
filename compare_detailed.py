# COMPARATIVO DETALHADO: Sistema Atual vs Proposto
# Engenharia reversa spin a spin

from statistics import median, mean

# Dados ATUALIZADOS do servidor (mais recente primeiro)
timeline_cw = [25, 27, 14, 9, 20, 6, 20, 36, 27, 28, 30, 28, 0, 17, 27, 33, 14, 12, 13, 22]
timeline_ccw = [36, 31, 16, 24, 28, 20, 27, 31, 4, 1, 13, 7, 30, 36, 11, 3, 7, 25, 35, 29]

# Performance REAL do sistema atual
performance_cw_real = [True, False, False, True, False, False, True, True, True, False, False, False]
performance_ccw_real = [False, False, True, False, True, False, True, False, True, False, False, True]

# Offsets atuais
offset_cw_atual = -8
offset_ccw_atual = +8

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

def cluster_predict(forces):
    """Agrupa forças por proximidade e usa média do maior cluster"""
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
    biggest = max(clusters, key=len)
    return int(mean(biggest))

def circular_error(predicted, actual):
    error = actual - predicted
    if error > 18: error -= 37
    elif error < -18: error += 37
    return error

def is_hit(predicted, actual, tolerance=8):
    diff = abs(predicted - actual)
    diff = min(diff, 37 - diff)
    return diff <= tolerance

def clamp(val, limit=8):
    return max(-limit, min(limit, val))

print("="*90)
print("COMPARATIVO DETALHADO: SISTEMA ATUAL vs PROPOSTO (Cluster + Momentum)")
print("="*90)

def compare_direction(timeline, performance_real, offset_atual, direction_name):
    print(f"\n{'='*90}")
    print(f"DIREÇÃO: {direction_name}")
    print(f"{'='*90}")
    print(f"{'#':<3} {'Forças Vistas':<30} {'Preditor':<12} {'Prev':<5} {'Real':<5} {'Atual':<8} {'Proposto':<10}")
    print("-"*90)
    
    # Estado para sistema proposto
    offset_proposto = 0
    error_history = []
    
    hits_atual = 0
    hits_proposto = 0
    
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
            
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        
        # Sistema ATUAL (regressão + offset fixo)
        pred_regressao = linear_regression_predict(forces)
        pred_atual = clamp(pred_regressao + offset_atual, 37)
        pred_atual = max(1, min(37, pred_atual))
        hit_atual = performance_real[i]  # Usar resultado REAL
        
        # Sistema PROPOSTO (cluster + momentum)
        pred_cluster = cluster_predict(forces)
        pred_proposto = clamp(pred_cluster + offset_proposto, 37)
        pred_proposto = max(1, min(37, pred_proposto))
        hit_proposto = is_hit(pred_proposto, actual)
        
        # Atualizar offset proposto com momentum
        if not hit_proposto:
            error = circular_error(pred_cluster, actual)
            if len(error_history) > 0:
                accel = error - error_history[-1]
            else:
                accel = 0
            offset_proposto = clamp(offset_proposto + int(error * 0.3 + accel * 0.2))
            error_history.append(error)
        
        # Contagem
        if hit_atual: hits_atual += 1
        if hit_proposto: hits_proposto += 1
        
        # Status
        status_atual = "✅" if hit_atual else "❌"
        status_proposto = "✅" if hit_proposto else "❌"
        
        # Comparação
        if hit_proposto and not hit_atual:
            comparison = "🔼 GANHO"
        elif hit_atual and not hit_proposto:
            comparison = "🔽 PERDA"
        else:
            comparison = ""
        
        forces_str = str(forces)[:28]
        print(f"{i+1:<3} {forces_str:<30} Reg:{pred_regressao:<3} Clu:{pred_cluster:<3} {pred_atual:<5} {actual:<5} {status_atual:<8} {status_proposto:<10} {comparison}")
    
    print("-"*90)
    print(f"TOTAL {direction_name}: Atual={hits_atual}/12 | Proposto={hits_proposto}/12 | Diferença: {hits_proposto - hits_atual:+d}")
    
    return hits_atual, hits_proposto

# Executar comparação
hits_cw_atual, hits_cw_proposto = compare_direction(timeline_cw, performance_cw_real, offset_cw_atual, "CW (Horário)")
hits_ccw_atual, hits_ccw_proposto = compare_direction(timeline_ccw, performance_ccw_real, offset_ccw_atual, "CCW (Anti-Horário)")

# Resumo final
print("\n" + "="*90)
print("RESUMO FINAL")
print("="*90)

total_atual = hits_cw_atual + hits_ccw_atual
total_proposto = hits_cw_proposto + hits_ccw_proposto

print(f"""
                     CW          CCW         TOTAL
  Sistema Atual:     {hits_cw_atual}/12        {hits_ccw_atual}/12        {total_atual}/24 ({total_atual*100//24}%)
  Sistema Proposto:  {hits_cw_proposto}/12        {hits_ccw_proposto}/12        {total_proposto}/24 ({total_proposto*100//24}%)
  
  Diferença:         {hits_cw_proposto - hits_cw_atual:+d}           {hits_ccw_proposto - hits_ccw_atual:+d}           {total_proposto - total_atual:+d} hits
""")

if total_proposto > total_atual:
    print(f"  🏆 PROPOSTO É MELHOR! +{total_proposto - total_atual} hits ({(total_proposto - total_atual)*100//total_atual}% de melhoria)")
elif total_proposto < total_atual:
    print(f"  ⚠️ ATUAL É MELHOR! Proposto teria {total_atual - total_proposto} hits a menos")
else:
    print(f"  ➡️ EMPATE - Mesma quantidade de acertos")

# Simulação: Qual fine-tuning teria maximizado os acertos?
# Testando diferentes estratégias nos mesmos dados

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
    predicted = intercept + slope * n
    return max(1, min(37, int(round(predicted))))

def is_hit(predicted, actual, tolerance=8):
    """Verifica se está dentro de ±8 (17 números)"""
    diff = abs(predicted - actual)
    # Circular
    diff = min(diff, 37 - diff)
    return diff <= tolerance

# ============================================================
# ESTRATÉGIA 1: Offset Fixo (atual)
# ============================================================
def strategy_fixed_offset(timeline, fixed_offset):
    hits = 0
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        predicted = linear_regression_predict(forces) + fixed_offset
        predicted = max(1, min(37, predicted))
        if is_hit(predicted, actual):
            hits += 1
    return hits

# ============================================================
# ESTRATÉGIA 2: Offset Dinâmico (ajusta a cada erro)
# ============================================================
def strategy_dynamic_offset(timeline):
    hits = 0
    offset = 0
    history = []
    
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        predicted_base = linear_regression_predict(forces)
        predicted = max(1, min(37, predicted_base + offset))
        
        hit = is_hit(predicted, actual)
        if hit:
            hits += 1
        else:
            # Calcular erro e ajustar offset
            error = actual - predicted_base
            # Normalizar erro circular
            if error > 18:
                error -= 37
            elif error < -18:
                error += 37
            
            # Ajustar offset baseado no erro (25% do erro)
            offset += int(error * 0.25)
            offset = max(-8, min(8, offset))
        
        history.append({"predicted": predicted, "actual": actual, "hit": hit, "offset": offset})
    
    return hits, history

# ============================================================
# ESTRATÉGIA 3: Offset baseado na média dos últimos 3 erros
# ============================================================
def strategy_rolling_error(timeline):
    hits = 0
    errors = []
    offset = 0
    
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        predicted_base = linear_regression_predict(forces)
        predicted = max(1, min(37, predicted_base + offset))
        
        hit = is_hit(predicted, actual)
        if hit:
            hits += 1
        
        # Sempre calcular erro para histórico
        error = actual - predicted_base
        if error > 18: error -= 37
        elif error < -18: error += 37
        
        errors.append(error)
        
        # Offset = média dos últimos 3 erros
        if len(errors) >= 2:
            recent_errors = errors[-3:]
            avg_error = sum(recent_errors) / len(recent_errors)
            offset = int(avg_error)
            offset = max(-8, min(8, offset))
    
    return hits

# ============================================================
# ESTRATÉGIA 4: Mediana em vez de Regressão + Offset Dinâmico
# ============================================================
def strategy_median_dynamic(timeline):
    from statistics import median
    hits = 0
    offset = 0
    
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        
        # Usar mediana em vez de regressão
        predicted_base = int(median(forces))
        predicted = max(1, min(37, predicted_base + offset))
        
        hit = is_hit(predicted, actual)
        if hit:
            hits += 1
        else:
            error = actual - predicted_base
            if error > 18: error -= 37
            elif error < -18: error += 37
            offset += int(error * 0.3)
            offset = max(-8, min(8, offset))
    
    return hits

# ============================================================
# ESTRATÉGIA 5: Reset quando erro inverte sinal
# ============================================================
def strategy_reset_on_inversion(timeline):
    hits = 0
    offset = 0
    last_error_sign = 0
    
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
        forces = timeline[i+1:i+6]
        actual = timeline[i]
        predicted_base = linear_regression_predict(forces)
        predicted = max(1, min(37, predicted_base + offset))
        
        hit = is_hit(predicted, actual)
        if hit:
            hits += 1
        else:
            error = actual - predicted_base
            if error > 18: error -= 37
            elif error < -18: error += 37
            
            current_sign = 1 if error > 0 else -1
            
            # Se sinal inverteu, reset
            if last_error_sign != 0 and current_sign != last_error_sign:
                offset = 0
            else:
                # Mesmo sinal, aumenta offset
                offset += int(error * 0.5)
                offset = max(-8, min(8, offset))
            
            last_error_sign = current_sign
    
    return hits

# ============================================================
# RODAR SIMULAÇÕES
# ============================================================
print("="*60)
print("SIMULAÇÃO DE ESTRATÉGIAS DE FINE-TUNING")
print("="*60)

print("\n--- CW (Horário) ---")
print(f"Original (offset -8 fixo): {strategy_fixed_offset(timeline_cw, -8)} hits")
print(f"Sem offset (baseline):     {strategy_fixed_offset(timeline_cw, 0)} hits")
print(f"Offset Dinâmico (25%):     {strategy_dynamic_offset(timeline_cw)[0]} hits")
print(f"Rolling Error (últimos 3): {strategy_rolling_error(timeline_cw)} hits")
print(f"Mediana + Dinâmico:        {strategy_median_dynamic(timeline_cw)} hits")
print(f"Reset ao Inverter:         {strategy_reset_on_inversion(timeline_cw)} hits")

print("\n--- CCW (Anti-Horário) ---")
print(f"Original (offset +4 fixo): {strategy_fixed_offset(timeline_ccw, +4)} hits")
print(f"Sem offset (baseline):     {strategy_fixed_offset(timeline_ccw, 0)} hits")
print(f"Offset Dinâmico (25%):     {strategy_dynamic_offset(timeline_ccw)[0]} hits")
print(f"Rolling Error (últimos 3): {strategy_rolling_error(timeline_ccw)} hits")
print(f"Mediana + Dinâmico:        {strategy_median_dynamic(timeline_ccw)} hits")
print(f"Reset ao Inverter:         {strategy_reset_on_inversion(timeline_ccw)} hits")

print("\n--- TOTAL (CW + CCW) ---")
original = strategy_fixed_offset(timeline_cw, -8) + strategy_fixed_offset(timeline_ccw, +4)
baseline = strategy_fixed_offset(timeline_cw, 0) + strategy_fixed_offset(timeline_ccw, 0)
dynamic = strategy_dynamic_offset(timeline_cw)[0] + strategy_dynamic_offset(timeline_ccw)[0]
rolling = strategy_rolling_error(timeline_cw) + strategy_rolling_error(timeline_ccw)
median_d = strategy_median_dynamic(timeline_cw) + strategy_median_dynamic(timeline_ccw)
reset = strategy_reset_on_inversion(timeline_cw) + strategy_reset_on_inversion(timeline_ccw)

print(f"Original (offset fixo):    {original}/24 ({original*100//24}%)")
print(f"Baseline (sem offset):     {baseline}/24 ({baseline*100//24}%)")
print(f"Offset Dinâmico:           {dynamic}/24 ({dynamic*100//24}%)")
print(f"Rolling Error:             {rolling}/24 ({rolling*100//24}%)")
print(f"Mediana + Dinâmico:        {median_d}/24 ({median_d*100//24}%)")
print(f"Reset ao Inverter:         {reset}/24 ({reset*100//24}%)")

# Detalhar a melhor estratégia
print("\n" + "="*60)
print("DETALHES DA MELHOR ESTRATÉGIA")
print("="*60)
best = max([(dynamic, "Dinâmico"), (rolling, "Rolling"), (median_d, "Mediana"), (reset, "Reset")], key=lambda x: x[0])
print(f"\nMelhor: {best[1]} com {best[0]}/24 hits")

# Mostrar trace do dinâmico para CW
_, trace = strategy_dynamic_offset(timeline_cw)
print("\nTrace CW com Offset Dinâmico:")
for i, t in enumerate(trace):
    status = "✅" if t["hit"] else "❌"
    print(f"  [{i+1}] {status} prev={t['predicted']:2d} real={t['actual']:2d} offset_next={t['offset']:+d}")

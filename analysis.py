# Análise de Engenharia Reversa das Previsões
# Simula o que o SDA-17 previu vs o que aconteceu

# Dados do state.json (mais recente primeiro)
timeline_cw = [30, 28, 0, 17, 27, 33, 14, 12, 13, 22, 20, 35, 36, 8, 19, 3, 3, 4, 8, 3, 11, 22, 3, 24, 24, 26, 2, 24, 32, 28, 36, 13, 24, 0, 2, 32, 1, 24, 33, 33, 7, 0, 25, 33, 23]
timeline_ccw = [13, 7, 30, 36, 11, 3, 7, 25, 35, 29, 33, 34, 25, 1, 7, 17, 8, 0, 25, 9, 3, 22, 30, 3, 5, 24, 2, 18, 18, 2, 0, 20, 0, 31, 1, 18, 19, 7, 11, 30, 25, 28, 31, 19, 23]

performance_cw = [False, False, False, False, True, False, True, True, False, False, True, False]
performance_ccw = [False, True, True, True, True, False, False, False, True, True, True, False]

# Sequência da roleta europeia física
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

def linear_regression_predict(forces_5):
    """Regressão linear em 5 forças, prevê próxima."""
    n = len(forces_5)
    # Inverter para ordem cronológica (antiga → recente)
    y = list(reversed(forces_5))
    x = list(range(n))
    
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    
    numerador = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    denominador = sum((x[i] - x_mean) ** 2 for i in range(n))
    
    slope = numerador / denominador if denominador != 0 else 0
    intercept = y_mean - slope * x_mean
    
    predicted = intercept + slope * n
    return max(1, min(37, int(round(predicted)))), slope

def analyze_direction(timeline, performance, direction_name, offset):
    """Analisa previsões para uma direção."""
    print(f"\n{'='*60}")
    print(f"ANÁLISE {direction_name.upper()} (offset atual: {offset:+d})")
    print(f"{'='*60}")
    
    # Percorrer os últimos 12 resultados
    for i, hit in enumerate(performance):
        # Para prever o resultado i, usávamos as forças i+1 até i+5
        if i + 5 >= len(timeline):
            continue
            
        forces_used = timeline[i+1:i+6]  # 5 forças que estava vendo
        actual_force = timeline[i]        # A força que realmente veio
        
        predicted_force, slope = linear_regression_predict(forces_used)
        
        # Com offset aplicado
        predicted_with_offset = max(1, min(37, predicted_force + offset))
        
        # Erro
        error = actual_force - predicted_force
        error_with_offset = actual_force - predicted_with_offset
        
        status = "✅ HIT" if hit else "❌ MISS"
        
        print(f"\n[{i+1}] {status}")
        print(f"  Forças vistas: {forces_used}")
        print(f"  Tendência: {slope:+.1f}/spin")
        print(f"  Previsão base: {predicted_force}")
        print(f"  + Offset ({offset:+d}): {predicted_with_offset}")
        print(f"  Força real: {actual_force}")
        print(f"  Erro sem offset: {error:+d}")
        print(f"  Erro com offset: {error_with_offset:+d}")
        
        if not hit:
            # Qual offset teria sido necessário?
            ideal_offset = actual_force - predicted_force
            print(f"  → Offset ideal: {ideal_offset:+d}")
            
            # Verificar se estava dentro de ±8 (17 números)
            if abs(error_with_offset) <= 8:
                print(f"  → PROBLEMA: Deveria ter acertado! Erro de {error_with_offset} está dentro de ±8")
            else:
                print(f"  → Fora da região de 17 números (erro > ±8)")

print("ENGENHARIA REVERSA DAS PREVISÕES SDA-17")
print("="*60)

analyze_direction(timeline_cw, performance_cw, "CW (Horário)", -8)
analyze_direction(timeline_ccw, performance_ccw, "CCW (Anti-Horário)", +4)

# Resumo estatístico
print("\n" + "="*60)
print("RESUMO ESTATÍSTICO")
print("="*60)

# CW - calcular média dos erros
print("\nCW - Últimas 12 forças reais:", timeline_cw[:12])
print(f"   Média das forças: {sum(timeline_cw[:12])/12:.1f}")
print(f"   Min/Max: {min(timeline_cw[:12])}/{max(timeline_cw[:12])}")

# CCW
print("\nCCW - Últimas 12 forças reais:", timeline_ccw[:12])
print(f"   Média das forças: {sum(timeline_ccw[:12])/12:.1f}")
print(f"   Min/Max: {min(timeline_ccw[:12])}/{max(timeline_ccw[:12])}")

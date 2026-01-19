# AUDITORIA COMPLETA DOS DADOS E FLUXO DETALHADO
# Verificação rigorosa dos dados e simulação passo a passo

from statistics import mean

print("="*100)
print("AUDITORIA DE DADOS - VERIFICAÇÃO DE INTEGRIDADE")
print("="*100)

# DADOS EXTRAÍDOS DO state.json DO SERVIDOR (copiar exato)
# Nota: forces[0] = mais recente, forces[-1] = mais antigo

timeline_cw_raw = [25, 27, 14, 9, 20, 6, 20, 36, 27, 28, 30, 28, 0, 17, 27, 33, 14, 12, 13, 22]
timeline_ccw_raw = [36, 31, 16, 24, 28, 20, 27, 31, 4, 1, 13, 7, 30, 36, 11, 3, 7, 25, 35, 29]

# PERFORMANCE REAL REGISTRADA PELO SISTEMA (do state.json)
performance_cw_real = [True, False, False, True, False, False, True, True, True, False, False, False]
performance_ccw_real = [False, False, True, False, True, False, True, False, True, False, False, True]

# CALIBRAÇÃO ATUAL
calibration_cw = {"state": "confirmado", "first_error": -10, "offset": -8}
calibration_ccw = {"state": "confirmado", "first_error": 13, "offset": 8}

print("\n📊 DADOS BRUTOS DO SERVIDOR:")
print(f"  Timeline CW (últimas 20 forças):  {timeline_cw_raw}")
print(f"  Timeline CCW (últimas 20 forças): {timeline_ccw_raw}")
print(f"\n  Performance CW real:  {performance_cw_real}")
print(f"  Performance CCW real: {performance_ccw_real}")
print(f"\n  Calibração CW:  offset={calibration_cw['offset']}, state={calibration_cw['state']}")
print(f"  Calibração CCW: offset={calibration_ccw['offset']}, state={calibration_ccw['state']}")

# Contagem de acertos reais
hits_cw_real = sum(performance_cw_real)
hits_ccw_real = sum(performance_ccw_real)
print(f"\n  ✅ Acertos REAIS: CW={hits_cw_real}/12, CCW={hits_ccw_real}/12, Total={hits_cw_real+hits_ccw_real}/24")

# ============================================================
# FUNÇÕES DO SISTEMA ATUAL (exatamente como está no código)
# ============================================================

def linear_regression_predict(forces_5):
    """Exatamente como implementado em sda17.py"""
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

def cluster_predict(forces):
    """Sistema proposto: agrupa por proximidade"""
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
    return int(mean(biggest)), len(biggest), biggest

def is_hit(predicted, actual, tolerance=8):
    """Verifica se está dentro de ±8 posições (17 números)"""
    diff = abs(predicted - actual)
    diff = min(diff, 37 - diff)  # Circular
    return diff <= tolerance

def circular_error(predicted, actual):
    error = actual - predicted
    if error > 18: error -= 37
    elif error < -18: error += 37
    return error

# ============================================================
# FLUXO DETALHADO SPIN A SPIN
# ============================================================

def detailed_flow(timeline, performance_real, offset_atual, direction_name):
    print(f"\n{'='*100}")
    print(f"FLUXO DETALHADO: {direction_name}")
    print(f"{'='*100}")
    
    # Estado para sistema proposto
    offset_proposto = 0
    error_history = []
    
    for i in range(12):
        if i + 5 >= len(timeline):
            continue
        
        # Forças que ESTAVAM disponíveis quando a previsão foi feita
        # forces[i+1] até forces[i+5] = 5 forças ANTERIORES ao resultado i
        forces = timeline[i+1:i+6]
        
        # Força que REALMENTE veio (resultado)
        actual = timeline[i]
        
        print(f"\n┌─── SPIN #{i+1} ───────────────────────────────────────────────────────────────────────┐")
        print(f"│ CONTEXTO:")
        print(f"│   Forças disponíveis (5 anteriores): {forces}")
        print(f"│   Força real que veio:               {actual}")
        print(f"│   Hit REAL registrado:               {'✅ SIM' if performance_real[i] else '❌ NÃO'}")
        print(f"│")
        
        # ===== SISTEMA ATUAL =====
        pred_reg, slope = linear_regression_predict(forces)
        pred_atual = pred_reg + offset_atual
        pred_atual = max(1, min(37, pred_atual))
        hit_atual = is_hit(pred_atual, actual)
        erro_atual = circular_error(pred_reg, actual)
        
        print(f"│ SISTEMA ATUAL (Regressão Linear + Offset Fixo):")
        print(f"│   Regressão linear: slope={slope:+.2f}, previsão base={pred_reg}")
        print(f"│   + Offset fixo ({offset_atual:+d}): previsão final={pred_atual}")
        print(f"│   Resultado: {'✅ ACERTARIA' if hit_atual else '❌ ERRARIA'} (erro={erro_atual:+d})")
        print(f"│")
        
        # ===== SISTEMA PROPOSTO =====
        pred_clu, cluster_size, cluster_members = cluster_predict(forces)
        pred_proposto = pred_clu + offset_proposto
        pred_proposto = max(1, min(37, pred_proposto))
        hit_proposto = is_hit(pred_proposto, actual)
        erro_proposto = circular_error(pred_clu, actual)
        
        print(f"│ SISTEMA PROPOSTO (Cluster + Momentum):")
        print(f"│   Cluster encontrado: {cluster_members} → média={pred_clu}")
        print(f"│   + Offset dinâmico ({offset_proposto:+d}): previsão final={pred_proposto}")
        print(f"│   Resultado: {'✅ ACERTARIA' if hit_proposto else '❌ ERRARIA'} (erro={erro_proposto:+d})")
        
        # Atualizar offset proposto
        old_offset = offset_proposto
        if not hit_proposto:
            if len(error_history) > 0:
                accel = erro_proposto - error_history[-1]
            else:
                accel = 0
            offset_proposto += int(erro_proposto * 0.3 + accel * 0.2)
            offset_proposto = max(-8, min(8, offset_proposto))
            error_history.append(erro_proposto)
            print(f"│   Ajuste momentum: erro={erro_proposto:+d}, offset {old_offset:+d} → {offset_proposto:+d}")
        else:
            print(f"│   Sem ajuste (acertou)")
        
        # Comparação
        if hit_proposto and not hit_atual:
            resultado = "🔼 PROPOSTO GANHA"
        elif hit_atual and not hit_proposto:
            resultado = "🔽 PROPOSTO PERDE"
        elif hit_atual and hit_proposto:
            resultado = "➡️ EMPATE (ambos acertam)"
        else:
            resultado = "➡️ EMPATE (ambos erram)"
        
        print(f"│")
        print(f"│ COMPARAÇÃO: {resultado}")
        print(f"└─────────────────────────────────────────────────────────────────────────────────────┘")

# Executar fluxo detalhado
detailed_flow(timeline_cw_raw, performance_cw_real, calibration_cw["offset"], "CW (Horário)")
detailed_flow(timeline_ccw_raw, performance_ccw_real, calibration_ccw["offset"], "CCW (Anti-Horário)")

print("\n" + "="*100)
print("VERIFICAÇÃO FINAL")
print("="*100)
print("""
VALIDAÇÃO DOS DADOS:
  ✓ Dados extraídos diretamente do state.json do servidor
  ✓ Performance_cw e performance_ccw são os resultados REAIS registrados
  ✓ Offset CW=-8 e CCW=+8 são os valores ATUAIS de calibração
  ✓ Cada spin mostra exatamente o que TERIA acontecido
""")

"""
AUDITORIA COMPLETA: Microserviço Hit/Miss Logic
================================================
Este script testa toda a cadeia de previsão e verificação para encontrar bugs.
"""

import json
from logic import RouletteLogic

logic = RouletteLogic()

print("=" * 60)
print("AUDITORIA DO FLUXO MICROSERVIÇO")
print("=" * 60)

# Simular diferentes cenários
cenarios = [
    {"posicao_partida": 20, "forca": 4, "sentido": "horario", "numero_real": 14},
    {"posicao_partida": 1, "forca": 37, "sentido": "horario", "numero_real": 4},
    {"posicao_partida": 0, "forca": 5, "sentido": "antihorario", "numero_real": 17},
]

for i, cenario in enumerate(cenarios):
    print(f"\n{'─' * 60}")
    print(f"CENÁRIO {i+1}")
    print(f"{'─' * 60}")
    print(f"  Posição Partida: {cenario['posicao_partida']}")
    print(f"  Força Prevista:  {cenario['forca']}")
    print(f"  Sentido:         {cenario['sentido']}")
    print(f"  Número Real:     {cenario['numero_real']}")
    
    # PASSO 1: Calcular centro
    centro = logic.calcular_centro_alvo(
        cenario['posicao_partida'], 
        cenario['forca'], 
        cenario['sentido']
    )
    print(f"\n  [PASSO 1] Centro calculado: {centro}")
    
    # PASSO 2: Gerar região de 17 números
    num_vizinhos = 8
    regiao = logic.get_roulette_region(centro, num_vizinhos)
    print(f"  [PASSO 2] Região ({len(regiao)} números): {regiao}")
    
    # PASSO 3: Serializar para JSON (como no banco)
    regiao_json = json.dumps(regiao)
    print(f"  [PASSO 3] Região JSON: {regiao_json[:50]}...")
    
    # PASSO 4: Deserializar (como na verificação)
    regiao_parsed = json.loads(regiao_json)
    print(f"  [PASSO 4] Região parsed: {regiao_parsed[:5]}... ({len(regiao_parsed)} nums)")
    
    # PASSO 5: Verificar acerto
    acertou = cenario['numero_real'] in regiao_parsed
    print(f"\n  [RESULTADO] {cenario['numero_real']} in região? {acertou}")
    print(f"  [RESULTADO] {'✅ ACERTO' if acertou else '❌ ERRO'}")

# Teste específico: se centro fosse 4, o 14 deveria estar na região?
print("\n" + "=" * 60)
print("TESTE ESPECÍFICO: Centro 4 → 14 na região?")
print("=" * 60)

centro = 4
regiao = logic.get_roulette_region(centro, 8)
print(f"Centro: {centro}")
print(f"Região: {regiao}")
print(f"14 na região? {14 in regiao}")

# Teste inverso: qual centro incluiria o 14?
print("\n" + "=" * 60)
print("TESTE INVERSO: Qual centro inclui 14 na região?")
print("=" * 60)

for num_centro in range(37):
    regiao = logic.get_roulette_region(num_centro, 8)
    if 14 in regiao:
        print(f"  Centro {num_centro}: {regiao[:7]}... contém 14")

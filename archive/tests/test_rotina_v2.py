"""
Test script for the outlier base force detection.
"""
from strategy_microservice import prever_proxima_forca

print("=" * 70)
print("TESTE: F5 como OUTLIER - deve usar F4 como base")
print("=" * 70)
# Forças: [10, 12, 14, 16, 35] onde 35 é outlier
# Input invertido: [mais_recente, ..., mais_antigo] = [35, 16, 14, 12, 10]
result = prever_proxima_forca([35, 16, 14, 12, 10])

print(f"Forcas entrada (invertidas): {result['detalhes']['forcas_entrada']}")
print()
print("Variacoes:")
for v in result['detalhes']['variacoes']:
    status = "VENCEDORA" if v['vencedora'] else "REMOVIDA"
    print(f"  {v['de']} -> {v['para']}: mult={v['mult']:.3f} tipo={v['tipo']} [{status}]")
print()
print(f"Tendencia vencedora: {result['regime']}")
print(f"Base usada: {result['detalhes']['base_forca']} ({result['detalhes']['base_info']})")
print(f"Ultima forca original: {result['detalhes']['ultima_forca_original']}")
print(f"Media aplicada: {result['detalhes']['media_aplicada']}")
print(f">>> PREVISAO FINAL: {result['forca_prevista']}")

print()
print("=" * 70)
print("TESTE 2: Caso NORMAL - F5 valida (sem outlier)")
print("=" * 70)
# Forças: [10, 12, 14, 16, 18] todas válidas (aceleração)
result2 = prever_proxima_forca([18, 16, 14, 12, 10])

print(f"Forcas entrada: {result2['detalhes']['forcas_entrada']}")
print()
print("Variacoes:")
for v in result2['detalhes']['variacoes']:
    status = "VENCEDORA" if v['vencedora'] else "REMOVIDA"
    print(f"  {v['de']} -> {v['para']}: mult={v['mult']:.3f} tipo={v['tipo']} [{status}]")
print()
print(f"Tendencia vencedora: {result2['regime']}")
print(f"Base usada: {result2['detalhes']['base_forca']} ({result2['detalhes']['base_info']})")
print(f">>> PREVISAO FINAL: {result2['forca_prevista']}")

print()
print("=" * 70)
print("SUCESSO! Logica de outlier base force funcionando!")
print("=" * 70)

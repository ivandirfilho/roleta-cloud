# TAsk_audit_pos — Implantação M02-PctSigmoid v4.3.0

**Versão:** v4.3.0 | **Data:** 30/03/2025 | **Base:** audit_pos_implant.md (Seção 11)

---

## 1. Objetivo

Substituir o controlador Bayesiano brute-force (v4.2) pelo **M02-PctSigmoid**, o modelo vencedor da simulação de 15 modelos. Reduzir warmup de **5 → 2 jogadas** para triple focus imediato.

### Impacto Projetado (baseado em simulação de 100 jogadas reais)
| Métrica | v4.2 Baseline | v4.3 M02 | Ganho |
|---------|--------------|----------|-------|
| CW HR | 48.0% | **54.0%** | +6.0% |
| CCW HR | 24.0% | **46.0%** | +22.0% |
| Combined | 36.0% | **50.0%** | +14.0% |
| Warmup (jogadas perdidas) | 5/direção | **2/direção** | -60% |

---

## 2. Tarefas de Implementação

### T01 — Constantes (sda17.py)
- [ ] Adicionar: `SIGMOID_K = 6`, `SIGMOID_SCALE = 2.0`, `HIT_TIGHTEN = 0.08`, `MISS_CROSS_RATE = 0.3`
- [ ] Alterar: `BAYESIAN_DEFAULT = 12 → 10` (centro ótimo oracle)
- [ ] Alterar: `BAYESIAN_WARMUP = 5 → 2`
- [ ] Manter constantes antigas para backward compat (não remover)

### T02 — Estado (__init__)
- [ ] Adicionar: `self._sigmoid_off: Dict[str, float] = {}` (cw_off2, cw_off3, ccw_off2, ccw_off3)
- [ ] Manter: `cw_history`, `ccw_history`, `_last_offset` (backward compat)

### T03 — Warmup Reduzido (analyze)
- [ ] `min_forces = 3 → 2`
- [ ] Window list: `[7, 5, 3]` → `[7, 5, 3, 2]`
- [ ] SDA-19 fallback: `valid_forces < 5` → `valid_forces < 2`
- [ ] Efeito: Triple focus ativa a partir da 2ª jogada em cada sentido

### T04 — Reescrever _get_adaptive_offset
- [ ] Ler offsets de `_sigmoid_off[dir_key]`
- [ ] Default: (10, 10) se não inicializado
- [ ] Remover dependência de momentum limiter e brute-force
- [ ] Manter clamp [OFF_MIN, OFF_MAX]

### T05 — Novo: _pct_sigmoid_update
- [ ] Implementar sigmoid dampening: `adj = sigmoid(pct, k=6) × 2.0`
- [ ] Hit: tighten 8% para center=10
- [ ] Miss: adj na direção do erro, 30% contra-direcional
- [ ] Clamp final [7.0, 13.0]
- [ ] Chamado de update_adaptive após cada resultado

### T06 — Modificar update_adaptive
- [ ] Após history.append, chamar `_pct_sigmoid_update(direction, c1, result)`

### T07 — Persistência de Estado
- [ ] `get_adaptive_state()`: adicionar `sigmoid_off` dict
- [ ] `load_adaptive_state()`: restaurar `_sigmoid_off` com backward compat v4.2

### T08 — Docstring e Descrição
- [ ] Atualizar docstring da classe para v4.3
- [ ] Atualizar `self.description`

### T09 — Testes
- [ ] Atualizar verify_scenarios.py: C12 (momentum → sigmoid convergence), C13 (symmetry → sigmoid bounds)
- [ ] Adicionar cenários: C15 (M02 hit tighten), C16 (M02 miss expand), C17 (warmup=2)
- [ ] Rodar: `pytest tests/ -v` — todos 105+ devem passar
- [ ] Rodar: `python scripts/sim_temp/verify_scenarios.py` — 14+ cenários

### T10 — VERSION
- [ ] Bumpar VERSION para 4.3.0

---

## 3. Fórmula M02-PctSigmoid

```python
sigmoid(x) = 2.0 / (1.0 + exp(-6 * x)) - 1.0

# Após cada jogada:
if HIT:
    off2 += (10 - off2) * 0.08
    off3 += (10 - off3) * 0.08
else:
    pct = min_dist(result, coverage) / 18.0
    adj = sigmoid(pct) * 2.0
    if direction > 0:  # resultado CW de C1
        off2 += adj
        off3 -= adj * 0.3
    else:
        off3 += adj
        off2 -= adj * 0.3

off2 = clamp(off2, 7.0, 13.0)
off3 = clamp(off3, 7.0, 13.0)
```

---

## 4. Backward Compatibility

| Componente | v4.2 State | v4.3 State | Migração |
|-----------|-----------|-----------|----------|
| cw_history | List[(int,int)] | Mantido | Nenhuma |
| ccw_history | List[(int,int)] | Mantido | Nenhuma |
| last_offset | Dict[str,int] | Mantido (não usado) | Nenhuma |
| sigmoid_off | N/A | Dict[str,float] | Default 10.0 se ausente |

---

## 5. Status de Execução

### Resultados dos Testes
- **pytest:** 105/105 PASS ✅
- **verify_scenarios:** 18/18 PASS ✅ (4 novos cenários M02: C15-C18)

### Cenários M02 Validados
| Cenário | Verificação | Resultado |
|---------|------------|-----------|
| C12 | Sigmoid hit tightens (13.0→12.76) | ✅ PASS |
| C13 | Sigmoid miss expands (10.0→11.52) | ✅ PASS |
| C15 | Backward compat v4.2 (sem sigmoid_off) | ✅ PASS |
| C16 | Warmup=2 → triple focus com 2 forças | ✅ PASS |
| C17 | SDA-19 fallback apenas com <2 forças | ✅ PASS |
| C18 | offset_type = "sigmoid" nos detalhes | ✅ PASS |

### Arquivos Modificados
| Arquivo | Mudanças |
|---------|---------|
| `strategies/sda17.py` | M02-PctSigmoid, warmup 5→2, BAYESIAN_DEFAULT 12→10, novo _pct_sigmoid_update |
| `scripts/sim_temp/verify_scenarios.py` | 18 cenários (C1-C18), v4.3 completo |
| `tests/test_sda17.py` | offset_type "bayesian"→"sigmoid" |
| `VERSION` | 4.2.0 → 4.3.0 |
| `TAsk_audit_pos.md` | Este documento |

### Mudanças Técnicas Detalhadas
1. **_pct_sigmoid_update()**: Novo método — sigmoid dampened error feedback com direction-awareness
2. **_get_adaptive_offset()**: Reescrito — lê de _sigmoid_off (float), sem brute-force
3. **analyze()**: min_forces=2, window=[7,5,3,2], SDA-19 threshold < 2
4. **__init__**: _sigmoid_off dict adicionado
5. **get/load_adaptive_state()**: sigmoid_off na persistência com backward compat

### Backward Compatibility Verificada
- v4.0.x (cw_ema): ✅ Ignora, inicia limpo
- v4.1.x (sem last_offset): ✅ Inicia vazio
- v4.2.x (sem sigmoid_off): ✅ Inicia com defaults (center=10)

---

*Documento de planejamento e execução — M02-PctSigmoid v4.3.0*
*Todos os testes passaram. Pronto para deploy.*

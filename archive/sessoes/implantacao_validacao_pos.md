# Implantacao e Validacao Pos v4.2.0 — Anti-Drift Guardrails

**Data**: 30/03/2025 | **Versao**: 4.2.0
**Referencia ISO/IEC 25010**: Manutenabilidade (Modificabilidade, Testabilidade, Reusabilidade)
**Documentos Base**: `validacao_task_final_manha.md`, `Manutenabilidade_iso.md`, `deployci_cd.md`

---

## 1. CONTEXTO

### 1.1 Problema Identificado

A auditoria profunda em `validacao_task_final_manha.md` identificou que o M04 Error-Vector v4.1.0 estava **funcionalmente correto** mas com **parametros desajustados** causando:

| Bug | Severidade | Impacto |
|-----|-----------|---------|
| BUG-PERF-001: Offset drift para valores altos | CRITICA | CCW offset=13 com 20% HR vs 60% no offset=10 |
| BUG-PERF-002: Assimetria excessiva | ALTA | Error-Vector pode converter HIT em MISS |
| BUG-PERF-003: Prior Gaussiano insuficiente | ALTA | PRIOR_STRENGTH=0.3 nao contem drift |
| BUG-PERF-004: ERROR_THRESHOLD baixo | MEDIA | Ruido alimenta vetor de erro |
| BUG-PERF-005: Sem limitador de variacao | MEDIA | Saltos abruptos 7->13 entre jogadas |

### 1.2 Performance Pre-v4.2.0

| Metrica | CW (horario) | CCW (anti-horario) |
|---------|-------------|-------------------|
| Global v4.1.0 | 51.1% (24/47) | 29.6% (8/27) |
| Last 25 plays | 37.5% (9/24) | 21.7% (5/23) |
| Best offset | 10 (57%) | 10 (60%) |
| Worst offset | 12 (33%) | 13 (20%) |

---

## 2. VERIFICACAO M04 — AMBAS DIRECOES

### 2.1 Resultado da Verificacao

**Status: CORRETO em ambas direcoes.**

| Verificacao | CW | CCW | Status |
|------------|-----|------|--------|
| `_get_adaptive_offset()` roteia corretamente | `cw_history` | `ccw_history` | OK |
| `_bayesian_error_vector()` mesmo algoritmo | sim | sim | OK |
| `update_adaptive()` atualiza historico correto | `cw_history.append()` | `ccw_history.append()` | OK |
| Historicos independentes (sem contaminacao) | confirmado | confirmado | OK |
| `analyze()` usa `timeline.direction` | correto | correto | OK |
| Backward compat (ignora cw_ema antigo) | funcional | funcional | OK |

### 2.2 Fluxo Validado

```
Spin "horario" → target="anti-horario" → usa ccw_history → atualiza ccw_history
Spin "anti-horario" → target="horario" → usa cw_history → atualiza cw_history
```

---

## 3. ALTERACOES IMPLEMENTADAS (v4.2.0)

### 3.1 Parametros Ajustados

| Parametro | v4.1.0 | v4.2.0 | Razao |
|-----------|--------|--------|-------|
| `OFFSET_MAX` | 17 | **13** | Dados mostram 14+ nunca e otimo; foca cobertura |
| `PRIOR_STRENGTH` | 0.3 | **0.5** | Ancora offset perto de center=10, previne drift |
| `ERROR_THRESHOLD` | 5 | **7** | Filtra ruido no vetor de erro (18.9% da roda) |
| `ERROR_DECAY` | 0.15 | **0.08** | Menor sensibilidade a vies direcional |

### 3.2 Novos Features

#### 3.2.1 Momentum Limiter (`MAX_DELTA_OFFSET = 2`)

**Problema**: Offset podia saltar de 7 para 13 entre jogadas consecutivas.

**Solucao**: Limitar variacao maxima do offset medio entre jogadas a +-2 posicoes.

**Implementacao** em `_get_adaptive_offset()`:
```python
last = self._last_offset.get(dir_key, BAYESIAN_DEFAULT)
avg_off = round((off2 + off3) / 2)
delta = avg_off - last
if abs(delta) > MAX_DELTA_OFFSET:
    shift = MAX_DELTA_OFFSET * sign(delta)
    # Preserva diferenca relativa off2-off3 mas ajusta centro
    new_avg = last + shift
    off2 = clamp(new_avg + diff2, OFFSET_MIN, OFFSET_MAX)
    off3 = clamp(new_avg + diff3, OFFSET_MIN, OFFSET_MAX)
self._last_offset[dir_key] = round((off2 + off3) / 2)
```

#### 3.2.2 Symmetry Cap (`SYMMETRY_CAP = 4`)

**Problema**: Error-Vector podia gerar off_c2=9 e off_c3=14, desbalanceando cobertura.

**Solucao**: Se `|off_c2 - off_c3| > 4`, puxar ambos para a media.

**Implementacao** no final de `_bayesian_error_vector()`:
```python
if abs(off2 - off3) > SYMMETRY_CAP:
    avg = (off2 + off3) / 2
    half_cap = SYMMETRY_CAP / 2
    off2 = round(avg + half_cap)  # ou avg - half_cap
    off3 = round(avg - half_cap)  # ou avg + half_cap
    # Re-clamp
```

### 3.3 Persistencia Atualizada

- `get_adaptive_state()`: agora inclui `last_offset` dict
- `load_adaptive_state()`: restaura `_last_offset` com backward compat (v4.1.x sem last_offset funciona)

---

## 4. ARQUIVOS MODIFICADOS

| Arquivo | Tipo | Descricao |
|---------|------|-----------|
| `strategies/sda17.py` | **CORE** | 6 params tuned, 2 new features (momentum+symmetry), persistence updated |
| `scripts/sim_temp/verify_scenarios.py` | TEST | C5 bounds [7,17]->[7,13], +4 new scenarios (C11-C14) |
| `VERSION` | META | 4.1.0 -> 4.2.0 |

### 4.1 Detalhamento sda17.py

**Constantes alteradas** (linhas 38-52):
- `OFFSET_MAX`: 17 → 13
- `ERROR_DECAY`: 0.15 → 0.08
- `ERROR_THRESHOLD`: 5 → 7
- `PRIOR_STRENGTH`: 0.3 → 0.5
- Adicionado: `MAX_DELTA_OFFSET = 2`
- Adicionado: `SYMMETRY_CAP = 4`

**__init__** (linha 64): Adicionado `self._last_offset: Dict[str, int] = {}`

**_get_adaptive_offset** (linhas 283-308): Reescrito com momentum limiter

**_bayesian_error_vector** (linhas 347-350): Adicionado symmetry cap antes do return

**get_adaptive_state** (linhas 417-421): Inclui `last_offset`

**load_adaptive_state** (linhas 423-442): Restaura `_last_offset` com validacao

---

## 5. VALIDACAO

### 5.1 Testes Unitarios

```
python -m pytest tests/ -v --tb=short
=> 105/105 PASSED (0.46s)
```

### 5.2 Cenarios de Verificacao

```
python scripts/sim_temp/verify_scenarios.py
=> 14/14 PASS

Cenarios validados:
  C1:  CW history append
  C2:  CCW history append
  C3:  _wheel in analyze()
  C4:  Asymmetric offset tuple
  C5:  Offset bounds [7,13]         ← ATUALIZADO
  C6:  Decision model fields
  C7:  Persistence chain
  C8:  Backward compat (cw_ema)
  C9:  _circ_dir direction
  C10: DB schema migration
  C11: v4.2 parameter values        ← NOVO
  C12: Momentum limiter (delta<=2)  ← NOVO
  C13: Symmetry cap (diff<=4)       ← NOVO
  C14: last_offset persistence      ← NOVO
```

### 5.3 Backward Compatibility

| Cenario | Status |
|---------|--------|
| state.json com cw_ema (v4.0.x) | OK — ignora, inicia vazio |
| state.json sem last_offset (v4.1.x) | OK — inicia _last_offset vazio |
| DB schema (sda_offset, sda_offset_type) | OK — sem alteracao |

---

## 6. PROJECAO DE IMPACTO

Baseado na simulacao retroativa de `validacao_task_final_manha.md`:

| Metrica | v4.1.0 | v4.2.0 (estimado) | Delta |
|---------|--------|-------------------|-------|
| CW HR (last 25) | 37.5% | 42-46% | +5-9pp |
| CCW HR (last 25) | 21.7% | 35-44% | +13-22pp |
| CW Global | 51.1% | 53-55% | +2-4pp |
| CCW Global | 29.6% | 38-44% | +8-14pp |
| Media Ponderada | 43.2% | 47-50% | +4-7pp |

**Mecanismo de melhoria**:
1. OFFSET_MAX=13 impede drift para valores improdutivos
2. PRIOR_STRENGTH=0.5 ancora offset perto de 10 (empiricamente otimo)
3. Momentum limiter previne saltos abruptos
4. Symmetry cap previne assimetria excessiva que converte HITs em MISSes

---

## 7. CONFORMIDADE ISO/IEC 25010

### 7.1 Modificabilidade

- Mudancas localizadas em `sda17.py` (1 arquivo core)
- Parametros sao constantes de classe, facilmente ajustaveis
- Novos features (momentum, symmetry) sao guardrails opcionais

### 7.2 Testabilidade

- 105 testes unitarios existentes continuam passando
- 4 novos cenarios especificos para v4.2 features
- Verify scenarios cobrem todos os invariantes do sistema

### 7.3 Reusabilidade

- Momentum limiter e generico (funciona com qualquer offset range)
- Symmetry cap e parametrizavel (SYMMETRY_CAP constante)
- Backward compat garante rollback seguro

---

## 8. DEPLOY

### 8.1 Checklist Pre-Deploy

- [x] M04 verificado em ambas direcoes
- [x] 6 recomendacoes implementadas
- [x] 105/105 testes passam
- [x] 14/14 cenarios verificados
- [x] VERSION atualizado para 4.2.0
- [x] Backward compatibility confirmada
- [x] Documento de implantacao criado

### 8.2 Procedimento (seguindo deployci_cd.md)

1. `git add -A` (excluindo archive/)
2. `git commit -m "feat(v4.2.0): anti-drift guardrails..."`
3. `git push origin main`
4. SSH: `git pull && docker compose build && docker compose down && docker compose up -d`
5. Verificar: container healthy, WebSocket OK, VERSION=4.2.0

### 8.3 Rollback

Em caso de problema:
```bash
ssh root@187.45.181.75 "cd /root/roleta-cloud && git checkout HEAD~1 -- . && docker compose down && docker compose build && docker compose up -d"
```

---

*Documento gerado conforme padroes Manutenabilidade_iso.md | v4.2.0*

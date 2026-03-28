# 🚀 Implantação da Resolução de Bugs — 28/03/2026

> **Base:** `resolucao_bugs_28_03.md`  
> **Data:** 28/Mar/2026  
> **Status:** EM EXECUÇÃO

---

## Sprint 1 — Bug Fixes Críticos (Impacto na Performance)

### Task 1.1: Eliminar PULAR — Sempre Apostar (BUG-28-01 + M-02)

**Arquivo:** `core/engine.py`  
**Antes:** Quando SDA retorna `should_bet=False` → PULAR (17% das decisões perdidas)  
**Depois:** 3 níveis de decisão:
1. SDA recomenda → APOSTAR normal (com gale calculado)
2. SDA insuficiente mas timeline > 0 → APOSTAR com G1 seguro (fallback 21 nums ao redor do last_number)
3. Timeline vazia (0 forças) → PULAR (genuinamente sem dados)

**Mudança:**
```python
# ANTES:
if result.should_bet:
    # APOSTAR
else:
    acao = "PULAR"

# DEPOIS:
if result.should_bet:
    # APOSTAR normal
elif self.game_state.target_timeline.size > 0:
    # APOSTAR com G1 seguro (fallback)
else:
    # PULAR (timeline vazia)
```

### Task 1.2: Corrigir C4 Rate para Gale Sizing (BUG-28-03 + M-01)

**Arquivos:** `state/game.py` + `core/engine.py`  
**Antes:** `c4_rate` vem de `performance_sda17` (inclui predições não apostadas)  
**Depois:** `c4_rate` para SmartGaleV4 vem de `performance_bet` (apenas apostas reais)

**Mudanças:**
1. Adicionar `target_performance_bet` property em `GameState`
2. Adicionar `get_bet_c4_rate()` método em `GameState`
3. Em `engine.py`, usar `get_bet_c4_rate()` em vez de `advice.c4_rate`

---

## Sprint 2 — Robustez da Estratégia

### Task 2.1: Segunda Validação de Coverage (BUG-28-04 + M-07)

**Arquivo:** `strategies/sda17.py`  
**Antes:** Se `_force_spread()` não resolver overlap, números ficam < 18  
**Depois:** Após spread, se ainda < 18, aumentar raio para 4

### Task 2.2: Melhorar Comentários do Drift Detection (BUG-28-12 + M-09)

**Arquivo:** `strategies/sda17.py`  
**Corrigir comentário:** "mais recente primeiro" → documentação precisa da ordenação

### Task 2.3: Documentar Transição SDA-19 → SDA-21 (M-08)

**Arquivo:** `strategies/sda17.py`  
**Adicionar docstring** explicando quando e porque o fallback SDA-19 é ativado

---

## Sprint 3 — Infraestrutura e Robustez

### Task 3.1: PRAGMA foreign_keys (BUG-28-05 + M-03)

**Arquivo:** `database/sqlite_repo.py`  
**Adicionar:** `conn.execute("PRAGMA foreign_keys = ON")` em `_get_connection()`

### Task 3.2: State Load com Logging + Backup (BUG-28-06 + M-04)

**Arquivo:** `state/game.py`  
**Antes:** `except Exception: return cls()` silencioso  
**Depois:** Log do erro + backup do arquivo corrompido antes de retornar estado limpo

### Task 3.3: Cleanup Temp File no Save (BUG-28-07 + M-05)

**Arquivo:** `state/game.py`  
**Antes:** Se `open()` falhar no fallback, temp file não é removido  
**Depois:** `finally` block para garantir cleanup

### Task 3.4: Validação de Direção como Guard Clause (BUG-28-08 + M-10)

**Arquivo:** `state/game.py`  
**Mover** validação de direção para ANTES de qualquer modificação de estado

### Task 3.5: Force Bounds Check no Timeline (BUG-28-11 + M-06)

**Arquivo:** `state/timeline.py`  
**Adicionar:** Validação `1 ≤ force ≤ 37` no `add()`

---

## Sprint 4 — Testes

### Task 4.1: Testes de Cobertura

**Arquivo:** `tests/test_bug_fixes_28_03.py` (novo)

Testes a implementar:
1. `test_sda17_coverage_always_ge_18` — Triple Focus sempre ≥ 18 nums
2. `test_c4_rate_uses_bet_performance` — c4_rate vem de performance_bet
3. `test_always_bet_when_timeline_has_data` — PULAR só com timeline vazia
4. `test_timeline_add_invalid_force` — Force bounds [1, 37]
5. `test_state_load_corrupted_json` — Load com JSON inválido gera log + backup
6. `test_foreign_key_constraint` — FK ativa rejeita referência inválida
7. `test_martingale_all_levels_valid` — G1, G2, G3 todos funcionam
8. `test_drift_detection_correct_order` — Drift usa 3 mais recentes

---

## Ordem de Execução

1. Sprint 1 (Crítico) → Sprint 2 (Estratégia) → Sprint 3 (Infra) → Sprint 4 (Testes)
2. Rodar `pytest` após cada sprint
3. Commit final com todos os sprints
4. Deploy no servidor Debian

---

## Análise de Conflitos

| Arquivo | Sessão Ativa? | Risco |
|---------|:------------:|:-----:|
| `core/engine.py` | Não persiste (in-memory) | ✅ Zero — rebuild no restart |
| `state/game.py` | `state.json` persiste | ✅ Zero — formato JSON igual (v1.5.0) |
| `strategies/sda17.py` | Não persiste | ✅ Zero — rebuild no restart |
| `database/sqlite_repo.py` | DB persiste | ✅ Zero — FK é PRAGMA por conexão |
| `state/timeline.py` | Via state.json | ✅ Zero — serialização inalterada |

**Nenhum conflito com sessão ativa.** O deploy requer apenas restart do container.

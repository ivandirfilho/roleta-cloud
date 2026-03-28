# 🔍 Resolução de Bugs e Melhorias — 28/03/2026

> **Data:** 28/Mar/2026  
> **Base:** `estado_pos_refatoracao.md` + Auditoria completa do código + Dados de produção  
> **Status:** 📋 DOCUMENTO DE ESTUDO — nenhuma alteração autorizada ainda  
> **Commits analisados:** `1c044c0` (refatoração DB) e `14629a6` (docs)

---

## PARTE I — AUDITORIA: BUGS ENCONTRADOS

### Resumo Executivo

Foram realizadas 3 auditorias paralelas:
1. **Auditoria de código completa** — todos os arquivos Python, extensão Chrome, testes
2. **Análise do git diff** — o que mudou nos commits de 27/03
3. **Consulta de produção** — dados reais do servidor (2607 decisions, 49 sessions)

**Resultado:** 12 bugs confirmados (4 falsos positivos descartados), 7 melhorias propostas.

---

### 1. Bugs Confirmados

---

#### 🔴 BUG-28-01 (ALTA): "PULAR" acontece em 17% das decisões

**Localização:** `core/engine.py:98-115`  
**Evidência de produção:** 38 PULAR vs 182 APOSTAR (hoje), `sda_centers=[0]` em 39 decisões

```python
# engine.py — linhas 97-115 (código atual)
# 6. Decisão combinada — Smart Gale v4: SEMPRE aposta
if result.should_bet:       # ← SDA controla a decisão
    mg = self.game_state.target_martingale
    mg.get_gale(score=result.score, c4_rate=c4_rate)
    acao = "APOSTAR"
    self.game_state.store_prediction(...)
else:
    acao = "PULAR"           # ← Contradiz "SEMPRE aposta"
    action_reason = "SDA não recomendou (forças insuficientes)"
```

**Causa raiz:** Quando a timeline tem < 5 forças válidas E o fallback SDA-19 não é atingido (ex: timeline completamente vazia), `result.should_bet` retorna `False`. O engine.py não tem lógica para apostar nesses casos.

**Fluxo atual quando PULAR:**
```
Chrome → WebSocket → process_spin() → timeline vazia → 
  sda17.analyze() → should_bet=False → engine PULAR → 
  NÃO chama store_prediction() → NÃO chama get_gale() →
  Decision salva com final_action="PULAR" → overlay mostra "sem aposta"
```

**Impacto:** 38 oportunidades perdidas hoje. Não sabemos quantas seriam acertos.

**Proposta de correção:**
```python
# Quando SDA não recomenda mas temos algum dado:
if result.should_bet:
    # ... lógica atual (APOSTAR com confiança)
elif self.game_state.target_timeline.size > 0:
    # Forças insuficientes mas com algum dado → APOSTAR com G1 seguro
    mg = self.game_state.target_martingale
    mg.level = 1  # Forçar G1 (R$21)
    acao = "APOSTAR"
    action_reason = "SDA insuficiente → G1 seguro"
    self.game_state.store_prediction(
        result.numbers or [...], ..., bet_placed=True, ...
    )
else:
    # Timeline completamente vazia → genuinamente sem dados
    acao = "PULAR"
```

**Risco:** Médio — apostar com dados insuficientes pode reduzir taxa de acerto.

---

#### 🟡 BUG-28-02 (MÉDIA): SDA-19 fallback usa cobertura inconsistente

**Localização:** `strategies/sda17.py:85-111`

```python
# Fallback SDA-19 (< 5 forças):
numbers = sorted(self.get_neighbors(c1, 9, wheel_sequence))
# Resultado: 1 centro + 9 vizinhos de cada lado = 19 números

# Triple Focus principal:
for center in [c1, c2, c3]:
    nums |= set(self.get_neighbors(center, 3, wheel_sequence))
# Resultado: 3 centros + 3 vizinhos de cada lado = até 21 números
```

**Problema:** O fallback usa 1 centro com raio 9 (19 números contíguos), enquanto o Triple Focus usa 3 centros com raio 3 (21 números espalhados). São estratégias geometricamente diferentes:

| Aspecto | SDA-19 (fallback) | SDA-21 (principal) |
|---------|:------------------:|:------------------:|
| Centros | 1 | 3 |
| Raio | 9 | 3 |
| Números | 19 contíguos | 21 espalhados |
| Cobertura geométrica | 1 arco de ~51% | 3 arcos de ~19% cada |

**Impacto produção:** Hit rate SDA-19: **52.2%** vs SDA-21: **61.2%** (diferença de 9 pontos!)

**Proposta:** Manter SDA-19 mas documentar claramente a transição, ou criar fallback com 3 centros default (equidistantes a 120° na roda).

---

#### 🟡 BUG-28-03 (MÉDIA): C4 rate usa performance errada para gale sizing

**Localização:** `state/game.py:61-62` e `state/bet_advisor.py:83-91`

```python
# game.py — SmartGaleV4:
if c4_rate < 0.25:
    max_gale = 1  # Força G1

# A c4_rate vem de bet_advisor.analyze() que usa performance_sda17
# performance_sda17 inclui TODAS as predições (mesmo PULAR com bet_placed=False)
# performance_bet inclui APENAS apostas reais
```

**Problema:** A c4_rate é calculada sobre `performance_sda17` (que inclui predições não apostadas), não sobre `performance_bet` (apostas reais). Isso pode suprimir o gale injustamente:

```
Cenário: 4 últimas predições SDA = [True, True, True, False (PULAR)]
  c4 de performance_sda17 = 3/4 = 75% → OK
  
Cenário: 4 últimas predições SDA = [False(PULAR), False(PULAR), True, True]
  c4 de performance_sda17 = 2/4 = 50%
  Mas c4 de performance_bet = 2/2 = 100%! ← Deveria permitir G2/G3
```

**Impacto:** Gale progression é artificialmente suprimida — contribui para o BUG-DB-12 (gale raramente escala).

**Proposta:** Em `get_bet_advice()`, passar `performance_bet` em vez de `performance_sda17`:
```python
def get_bet_advice(self, sda_score: int = 3) -> BetAdvice:
    return self.bet_advisor.analyze(self.target_performance_bet, sda_score=sda_score)
```

---

#### 🟡 BUG-28-04 (MÉDIA): Coverage mínima sem segunda validação

**Localização:** `strategies/sda17.py:131-137`

```python
if len(numbers) < 18:
    c1, c2, c3 = self._force_spread(c1, c2, c3, wheel_sequence)
    # ... recalcula numbers
    numbers = sorted(nums)
    # FALTA: verificar novamente se len(numbers) >= 18
```

**Problema:** Após `_force_spread()`, os centros redistribuídos com SPREAD_OFFSET=12 podem ainda gerar overlap. Sem loop de retry ou validação final.

**Impacto:** Baixo na prática (SPREAD_OFFSET=12 com raio=3 raramente cria overlap), mas possível em edge cases.

**Proposta:** Adicionar validação pós-spread:
```python
if len(numbers) < 18:
    c1, c2, c3 = self._force_spread(...)
    # recalcular
    if len(numbers) < 18:  # Ainda insuficiente
        # Aumentar raio temporariamente
        for center in [c1, c2, c3]:
            nums |= set(self.get_neighbors(center, 4, wheel_sequence))
```

---

#### 🟡 BUG-28-05 (MÉDIA): Foreign Keys desabilitadas no SQLite

**Localização:** `database/sqlite_repo.py:44-50`

```python
def _get_connection(self):
    conn = sqlite3.connect(str(self.db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    # FALTA: conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn
```

**Problema:** SQLite tem foreign keys desabilitadas por default. `window_plays.window_id` pode referenciar `gale_windows.id` inexistente sem erro.

**Proposta:** Adicionar `PRAGMA foreign_keys = ON` após conexão.

---

#### 🟡 BUG-28-06 (MÉDIA): State load silencioso perde dados

**Localização:** `state/game.py:495-510`

```python
except Exception:
    return cls()  # ← Silencioso! Nenhum log, nenhum backup
```

**Problema:** Se `state.json` estiver corrompido, o sistema perde silenciosamente todo o estado acumulado (timelines, performance, martingale) sem aviso.

**Proposta:**
```python
except Exception as e:
    logger.error(f"Falha ao carregar state.json: {e}")
    try:
        backup = path.with_suffix('.json.bak')
        shutil.copy2(path, backup)
    except: pass
    return cls()
```

---

#### 🟡 BUG-28-07 (MÉDIA): Docker state save pode vazar temp file

**Localização:** `state/game.py:440-449`

```python
try:
    os.replace(temp_path, path)
except OSError:
    with open(path, 'w') as target:
        with open(temp_path, 'r') as source:
            target.write(source.read())
    os.unlink(temp_path)
    # Se open() falhar, temp_path não é removido!
```

**Proposta:** Usar `finally` para garantir cleanup do temp file.

---

#### 🟢 BUG-28-08 (BAIXA): Direção inválida não impede processamento

**Localização:** `state/game.py:219-223`

```python
if direcao not in _VALID_DIRECTIONS:
    logger.warning(f"⚠️ Direção inválida ignorada: '{direcao}'")
    return 0  # Retorna 0 mas last_number/last_direction podem já ter sido setados
```

**Proposta:** Retornar antes de qualquer modificação de estado.

---

#### 🟢 BUG-28-09 (BAIXA): end_time de sessions ainda NULL

**Evidência de produção:** Todas 49 sessions têm `end_time=NULL`, incluindo a sessão pós-deploy.

**Causa:** Nenhum `handle_new_session()` (reset) nem shutdown aconteceu desde o deploy. O `end_session()` foi implementado mas nunca foi acionado ainda. **Funcionamento esperado** — será preenchido no próximo reset ou shutdown.

**Status:** ⚠️ Monitorar — não é bug, apenas ainda não foi acionado.

---

#### 🟢 BUG-28-10 (BAIXA): Window history query LIMIT inconsistente

**Localização:** `database/sqlite_repo.py:706`

```python
LIMIT ?  # limit * 6 — assume max 6 plays por window
```

**Problema:** Se uma window tem 2 plays, o LIMIT efetivo é menor que o esperado.

---

#### 🟢 BUG-28-11 (BAIXA): Timeline.add() aceita force ≤ 0

**Localização:** `state/timeline.py:26-28`

```python
def add(self, force: int) -> None:
    self.forces.appendleft(force)  # Sem validação de bounds
```

**Proposta:** Rejeitar `force < 1` ou `force > 37`.

---

#### 🟢 BUG-28-12 (BAIXA): Drift detection ordem correta mas sem documentação

**Localização:** `strategies/sda17.py:211`

```python
clean_by_recency = sorted(clean, key=lambda x: x[1])[:3]
```

**Análise:** O sort por `x[1]` (índice original) ascendente + `[:3]` captura os 3 mais recentes (idx 0, 1, 2). A lógica está **correta**, mas o comentário diz "mais recente primeiro" enquanto o sort é ascendente. Deveria ter comentário mais claro.

---

### 2. Falsos Positivos Descartados

| Alegação | Verificação | Resultado |
|----------|-------------|:---------:|
| "Timeline deque não inicializa em from_dict" | Testado: `from_dict()` chama `cls()` → `__init__` → `__post_init__` | ❌ **FALSO** — deque criada corretamente com maxlen=45 |
| "Store prediction quando PULAR" | Código: branch `else` (PULAR) NÃO chama `store_prediction()` | ❌ **FALSO** — predição não é armazenada |
| "get_gale API confusa" | O método atualiza `self.level` internamente e retorna — padrão válido | ❌ **Estilo**, não bug |
| "Kill Switch logic inverted" | Kill Switch afeta `advice.should_bet` mas engine usa `result.should_bet` (do SDA) | ❌ **PARCIALMENTE FALSO** — Kill Switch age via c4_rate → gale sizing, não via bet/skip |

---

## PARTE II — ANÁLISE DO GIT DE REFATORAÇÃO (27/03)

---

### 3. Commits Analisados

```
798007b (13:24) → feat: upgrade SDA-19 → SDA-21 (Triple Focus)     ← MUDOU ESTRATÉGIA
a762bb0 (15:18) → feat: Smart Gale v4 + SDA-21 fixes (4 sprints)   ← MUDOU ESTRATÉGIA
7d3efc1 (17:20) → docs: document DB location                        ← DOCS APENAS
1c044c0 (18:14) → refactor: database audit + session lifecycle      ← REFATORAÇÃO DB
14629a6 (18:17) → docs: estado pos refatoração                      ← DOCS APENAS
```

### 4. Resposta Definitiva: A refatoração de DB alterou a estratégia?

## **🎯 NÃO — Zero alterações na lógica de predição**

| Arquivo | Alteração na refatoração? | Impacto na predição |
|---------|:------------------------:|:-------------------:|
| `strategies/sda17.py` | ❌ 0 linhas alteradas | ZERO |
| `core/engine.py` | ❌ 0 linhas alteradas | ZERO |
| `state/bet_advisor.py` | ❌ 0 linhas alteradas | ZERO |
| `core/roulette.py` | ❌ 0 linhas alteradas | ZERO |
| `state/timeline.py` | ❌ 0 linhas alteradas | ZERO |
| `state/game.py` | ⚠️ 2 alterações menores | **ZERO impacto** |
| `server/message_handler.py` | ⚠️ 3 adições | **ZERO impacto** |

### 5. Detalhamento das Alterações (sem impacto na predição)

#### 5.1 `state/game.py` — Apenas serialização e parsing

**Alteração 1:** `to_dict()` removeu campos redundantes
```python
# ANTES:
def to_dict(self):
    return {
        "level": self.level,
        "consecutive_hits": self.consecutive_hits,
        "total_bets": self.total_bets,
        "current_bet": self.current_bet,      # ← REMOVIDO (computed)
        "multiplier": self.multiplier,          # ← REMOVIDO (computed)
        "gale_display": self.gale_display       # ← REMOVIDO (computed)
    }

# DEPOIS:
def to_dict(self):
    return {
        "level": self.level,
        "consecutive_hits": self.consecutive_hits,
        "total_bets": self.total_bets
    }
```
**Impacto:** ZERO — `from_dict()` já ignora esses campos e recalcula de `level`.

**Alteração 2:** Validação de versão no `load()`
```python
# ANTES: tuple(map(int, version.split(".")))  — crashava com versão malformada
# DEPOIS: try/except com fallback para (1, 0, 0)
```
**Impacto:** ZERO — apenas proteção defensiva.

#### 5.2 `server/message_handler.py` — Apenas tracking de sessão

```python
# ADIÇÃO 1: Contador de decisões (inicialização)
self._decision_count: int = 0

# ADIÇÃO 2: Stats periódicas (após save_decision)
self._decision_count += 1
if self._decision_count % 10 == 0:
    db_service.update_session_stats(self.current_session_id)

# ADIÇÃO 3: Finalizar sessão anterior no reset
if self.current_session_id:
    db_service.end_session(self.current_session_id)
```
**Impacto:** ZERO — são operações de DB que rodam DEPOIS da decisão já ter sido tomada e enviada para o overlay.

### 6. Fluxo de Dados: ANTES vs DEPOIS da Refatoração

#### 6.1 Fluxo ANTES (commit a762bb0)

```
Chrome Extension
  │ WebSocket message: {type: "novo_resultado", numero: X, direcao: Y}
  ▼
message_handler.handle_new_result()
  │
  ├─ 1. check_prediction(numero) → hit/miss da predição anterior
  ├─ 2. SmartGaleV4.update(hit) → atualiza gale da direção apostada
  ├─ 3. db_service.track_gale_window() → grava janela
  ├─ 4. process_spin(numero, direcao) → atualiza timeline CW ou CCW
  ├─ 5. game_state.save() → grava state.json
  ├─ 6. sda17.analyze(timeline, last_number) → SDA-21 Triple Focus
  │     └─ Retorna: numbers[], center, centers[], score, should_bet
  ├─ 7. bet_advisor.analyze(performance_sda17) → c4_rate, confidence
  ├─ 8. SmartGaleV4.get_gale(score, c4_rate) → nível 1×/2×/3×
  ├─ 9. store_prediction(numbers, direction, center, bet_placed=True)
  ├─ 10. db_service.save_decision(decision) → grava no SQLite
  └─ 11. WebSocket.send(overlay_response) → envia para Chrome
```

#### 6.2 Fluxo DEPOIS (commit 1c044c0)

```
Chrome Extension
  │ WebSocket message: {type: "novo_resultado", numero: X, direcao: Y}
  ▼
message_handler.handle_new_result()
  │
  ├─ 1. check_prediction(numero) → hit/miss da predição anterior      [IGUAL]
  ├─ 2. SmartGaleV4.update(hit) → atualiza gale da direção apostada   [IGUAL]
  ├─ 3. db_service.track_gale_window() → grava janela                 [IGUAL]
  ├─ 4. process_spin(numero, direcao) → atualiza timeline CW ou CCW   [IGUAL]
  ├─ 5. game_state.save() → grava state.json                          [IGUAL]
  ├─ 6. sda17.analyze(timeline, last_number) → SDA-21 Triple Focus    [IGUAL]
  │     └─ Retorna: numbers[], center, centers[], score, should_bet    [IGUAL]
  ├─ 7. bet_advisor.analyze(performance_sda17) → c4_rate, confidence   [IGUAL]
  ├─ 8. SmartGaleV4.get_gale(score, c4_rate) → nível 1×/2×/3×        [IGUAL]
  ├─ 9. store_prediction(numbers, direction, center, bet_placed=True)  [IGUAL]
  ├─ 10. db_service.save_decision(decision) → grava no SQLite         [IGUAL]
  ├─ 10b. _decision_count += 1                                         [NOVO ✨]
  ├─ 10c. SE _decision_count % 10 == 0: update_session_stats()        [NOVO ✨]
  └─ 11. WebSocket.send(overlay_response) → envia para Chrome         [IGUAL]
```

**Diferença:** Apenas passos 10b e 10c foram adicionados — executam APÓS a decisão já ter sido tomada (passo 6-9) e enviada (passo 11). São operações de housekeeping do banco de dados que **não influenciam nenhuma predição**.

---

## PARTE III — MELHORIAS PROPOSTAS

---

### 7. Melhorias por Prioridade

#### 🔴 Prioridade Alta (Impacto direto na performance)

| ID | Melhoria | Arquivo | Impacto Esperado |
|:--:|----------|---------|------------------|
| M-01 | Usar `performance_bet` em vez de `performance_sda17` para c4_rate | `state/game.py` | Gale sizing mais justo — libera G2/G3 quando bets reais são positivos |
| M-02 | Reduzir PULAR: apostar com G1 quando SDA insuficiente mas timeline > 0 | `core/engine.py` | +17% decisões apostadas, potencial ganho de acertos |
| M-03 | Habilitar PRAGMA foreign_keys | `database/sqlite_repo.py` | Integridade de dados garantida |

#### 🟡 Prioridade Média (Robustez e observabilidade)

| ID | Melhoria | Arquivo | Impacto |
|:--:|----------|---------|---------|
| M-04 | Log em state load failure + backup de corrupted state | `state/game.py` | Diagnóstico de problemas, preservação de dados |
| M-05 | Cleanup de temp file no save fallback | `state/game.py` | Sem file leaks no Docker |
| M-06 | Validação de force bounds no Timeline.add() | `state/timeline.py` | Rejeitar dados espúrios |
| M-07 | Segunda validação de coverage pós-spread | `strategies/sda17.py` | Garantir ≥18 números sempre |

#### 🟢 Prioridade Baixa (Nice to have)

| ID | Melhoria | Arquivo | Impacto |
|:--:|----------|---------|---------|
| M-08 | Documentar transição SDA-19 → SDA-21 mais claramente | `strategies/sda17.py` | Manutenibilidade |
| M-09 | Adicionar comentários no drift detection | `strategies/sda17.py` | Clareza do código |
| M-10 | Rejeitar direção inválida antes de modificar estado | `state/game.py` | Proteção contra dados ruins |
| M-11 | Melhorar query LIMIT em window_history | `database/sqlite_repo.py` | API mais previsível |

---

### 8. Testes Faltantes (10 gaps identificados)

| # | Teste | Componente | Prioridade |
|:-:|-------|-----------|:----------:|
| 1 | `test_sda17_coverage_always_ge_18` | sda17 | Alta |
| 2 | `test_c4_rate_uses_bet_performance` | bet_advisor + game | Alta |
| 3 | `test_pular_vs_apostar_threshold` | engine | Alta |
| 4 | `test_timeline_add_invalid_force` | timeline | Média |
| 5 | `test_state_load_corrupted_json` | game | Média |
| 6 | `test_foreign_key_constraint` | sqlite_repo | Média |
| 7 | `test_martingale_all_levels_valid` | game | Média |
| 8 | `test_session_end_time_set` | service + handler | Média |
| 9 | `test_duplicate_spin_rejection` | message_handler | Baixa |
| 10 | `test_sda19_fallback_hit_rate` | sda17 | Baixa |

---

## PARTE IV — DADOS DE PRODUÇÃO ATUAIS

### 9. Estatísticas (até 28/Mar/2026 manhã)

```
Total de sessions:    49
Total de decisions:   2607
Total gale_windows:   305
Total window_plays:   1262

Sessões de 27/Mar (pós-deploy Smart Gale v4 + SDA-21):
  session_1774646822162: 38 spins, 32 bets, 17 hits (53.1%)  ← pós-refatoração DB
  session_1774643222435: 36 spins, 30 bets, 18 hits (60.0%)
  session_1774641226090: 44 spins, 38 bets, 25 hits (65.8%)
  session_1774640086794: 26 spins, 20 bets, 13 hits (65.0%)
  session_1774638919562: 26 spins, 20 bets, 11 hits (55.0%)
  session_1774629025733: 38 spins, 32 bets, 16 hits (50.0%)
```

### 10. Hit Rate por Tipo de Estratégia

| Estratégia | Total Apostas | Acertos | Taxa |
|-----------|:------------:|:-------:|:----:|
| **SDA-21 (3 centros)** | 159 | 93 | **61.2%** |
| **SDA-19 (1 centro)** | 23 | 12 | **52.2%** |

**Conclusão:** SDA-21 supera SDA-19 em 9 pontos percentuais. O fallback SDA-19 funciona mas com performance inferior.

### 11. Distribuição de Gale

| Nível | Decisões | Percentual |
|:-----:|:--------:|:----------:|
| G1 (R$21) | 209 | 95.0% |
| G2 (R$42) | 10 | 4.5% |
| G3 (R$63) | 1 | 0.5% |

**Conclusão:** O Smart Gale v4 é ultra-conservador. A Rule 3 (miss → reset) combinada com o BUG-28-03 (c4_rate usando performance errada) suprime a escalação. Corrigir M-01 deve permitir mais G2/G3.

---

## PARTE V — QUADRO RESUMO PARA APROVAÇÃO

| # | Tipo | Severidade | Descrição | Risco da Correção |
|:-:|:----:|:----------:|-----------|:-----------------:|
| BUG-28-01 | 🐛 Bug | 🔴 Alta | PULAR em 17% das decisões | Médio |
| BUG-28-02 | 🐛 Bug | 🟡 Média | SDA-19 fallback inconsistente | Baixo |
| BUG-28-03 | 🐛 Bug | 🟡 Média | C4 rate usa performance errada | Baixo |
| BUG-28-04 | 🐛 Bug | 🟡 Média | Coverage sem segunda validação | Zero |
| BUG-28-05 | 🐛 Bug | 🟡 Média | FK desabilitadas no SQLite | Zero |
| BUG-28-06 | 🐛 Bug | 🟡 Média | State load silencioso | Zero |
| BUG-28-07 | 🐛 Bug | 🟡 Média | Docker temp file leak | Zero |
| BUG-28-08 | 🐛 Bug | 🟢 Baixa | Direção inválida não bloqueia | Zero |
| BUG-28-09 | ℹ️ Info | 🟢 — | end_time NULL (esperado) | — |
| BUG-28-10 | 🐛 Bug | 🟢 Baixa | Window LIMIT inconsistente | Zero |
| BUG-28-11 | 🐛 Bug | 🟢 Baixa | Force sem bounds check | Zero |
| BUG-28-12 | ℹ️ Info | 🟢 — | Drift docs incompleto | Zero |
| M-01 | ⬆️ Melhoria | 🔴 Alta | c4_rate de performance_bet | Baixo |
| M-02 | ⬆️ Melhoria | 🔴 Alta | Reduzir PULAR com G1 seguro | Médio |
| M-03 | ⬆️ Melhoria | 🔴 Alta | PRAGMA foreign_keys | Zero |
| M-04→M-11 | ⬆️ Melhoria | 🟡/🟢 | Robustez e manutenibilidade | Zero/Baixo |

---

> **⚠️ NOTA:** Este documento é exclusivamente de estudo. Nenhuma alteração de código será feita até aprovação explícita.

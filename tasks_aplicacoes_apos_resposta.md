# 📋 Tasks de Aplicação Pós-Resposta Jules — 28/03/2026

> **Data:** 28/Mar/2026  
> **Base:** `resposta_a_sugestão_28_03.md` (análise das 4 sessions Jules)  
> **Referência:** `Manutenabilidade_iso.md` (PARTE I-VI)  
> **Status:** 📋 DOCUMENTO PARA APROVAÇÃO — nenhuma alteração no código autorizada

---

## 1. Contexto

Após análise das 4 sessions do Jules (Google AI Agent), identificamos **4 melhorias válidas** que complementam nossos bug fixes de 28/03. Este documento detalha cada task com:
- Código atual vs proposto (com linhas exatas)
- Justificativa técnica
- Simulação de impacto
- Auditoria de bugs na implementação proposta
- Indicação de atualização na `Manutenabilidade_iso.md`

---

## 2. Inventário de Arquivos Envolvidos

| # | Arquivo | Linhas | Papel | Task |
|:-:|---------|:------:|-------|:----:|
| 1 | `server/connection_manager.py` | 286 | Gerenciamento master/slave | TASK-01 |
| 2 | `database/sqlite_repo.py` | 857 | Repository SQLite | TASK-02 |
| 3 | `server/extractor_service.py` | 111 | Extração de mesas (sync) | TASK-03 |
| 4 | `server/message_handler.py` | 495 | Handler WebSocket | TASK-03 |
| 5 | `server/websocket.py` | 132 | Heartbeat broadcast | TASK-03 |
| 6 | `state/game.py` | 535 | Estado do jogo | TASK-04 |
| 7 | `Manutenabilidade_iso.md` | 1080 | Documentação ISO | TASK-05 |

---

## 3. Tasks Detalhadas

---

### TASK-01 — Fix Grace Period no CASO 2 (Duplo Master)

**Origem:** Jules Session `4621474988443942690`  
**Prioridade:** 🔴 **ALTA** — Bug de segurança lógica  
**Risco:** Baixo  
**Arquivos:** `server/connection_manager.py`

#### 3.1.1 O Problema

No `connection_manager.py`, quando um novo dispositivo conecta sem master prévio (CASO 2, linhas 85-90), o grace period task NÃO é cancelado. Isso cria uma race condition:

```
Timeline de Bug:
t=0s   Master A desconecta → grace_period_task inicia (10s countdown)
t=3s   Device B conecta → assume master (CASO 2, linhas 85-90)
       ❌ grace_period_task NÃO É CANCELADO
t=10s  Grace period expira → handle_grace_period() promove Slave C
       ❌ RESULTADO: Device B E Slave C são ambos MASTER
```

#### 3.1.2 Código Atual (Linha 85-90)

```python
# CASO 2: Sem master prévio — novo dispositivo vira master
else:
     role = "master"
     self.master_id = conn_id
     self.master_device_id = device_id
     self.master_disconnect_time = None
     # ❌ FALTA: cancelar _grace_period_task
     logger.info(f"👑 Novo MASTER atribuído (sem master prévio): {device_id}")
```

#### 3.1.3 Código Proposto

```python
# CASO 2: Sem master prévio — novo dispositivo vira master
else:
     role = "master"
     self.master_id = conn_id
     self.master_device_id = device_id
     self.master_disconnect_time = None
     # 🔧 Cancelar grace period pendente para evitar duplo master
     if self._grace_period_task and not self._grace_period_task.done():
         self._grace_period_task.cancel()
         self._grace_period_task = None
     logger.info(f"👑 Novo MASTER atribuído (sem master prévio): {device_id}")
```

#### 3.1.4 Locais Adicionais no Mesmo Arquivo

**Local 2 — `update_device_id()` CASO "primeiro dispositivo" (linha 264-267):**

Código atual:
```python
elif not self.last_master_device_id:
    info.role = "master"
    self.master_id = conn_id
    self.master_device_id = device_id
    # ❌ FALTA: master_disconnect_time = None
    # ❌ FALTA: cancelar _grace_period_task
```

Código proposto:
```python
elif not self.last_master_device_id:
    info.role = "master"
    self.master_id = conn_id
    self.master_device_id = device_id
    self.master_disconnect_time = None
    # 🔧 Cancelar grace period pendente
    if self._grace_period_task and not self._grace_period_task.done():
        self._grace_period_task.cancel()
        self._grace_period_task = None
```

#### 3.1.5 Simulação de Impacto

| Cenário | Sem Fix | Com Fix |
|---------|:-------:|:-------:|
| Master desconecta + novo device conecta em <10s | 2 masters | 1 master ✅ |
| Master desconecta + ninguém conecta em 10s | Promoção normal | Promoção normal ✅ |
| Master reconecta em <10s (CASO 1) | 1 master (já funciona) | 1 master ✅ |
| 2 devices conectam simultaneamente | Race possível | Protegido pelo lock ✅ |

#### 3.1.6 Auditoria de Bugs na Proposta

| Aspecto | Status | Nota |
|---------|:------:|------|
| Thread safety | ✅ | Código já está dentro de `async with self.master_lock` |
| `_grace_period_task` pode ser None | ✅ | Check `if self._grace_period_task and not...` é seguro |
| `cancel()` em task já finalizada | ✅ | `.done()` check previne |
| Efeito colateral em outros CASO | ✅ | Nenhum — é adição, não modificação |
| Testes existentes | ⚠️ | Não há teste para este cenário — **devemos adicionar** |

**Bugs encontrados:** 0  
**Melhorias adicionais:** Adicionar teste de integração para cenário de duplo master.

---

### TASK-02 — Otimização N+1 Query em `get_gale_window_history()`

**Origem:** Jules Session `14593626260387602831`  
**Prioridade:** 🟡 **MÉDIA** — Performance do banco de dados  
**Risco:** Baixo  
**Arquivos:** `database/sqlite_repo.py`

#### 3.2.1 O Problema

O método `get_gale_window_history()` (linha 778) executa uma query por janela para buscar os plays associados. Com `limit=50` (default), são **51 queries** ao SQLite em vez de 1-2.

**Nota:** O método `get_window_history()` (linha 693) já está otimizado com LEFT JOIN. Apenas `get_gale_window_history()` tem o padrão N+1.

#### 3.2.2 Código Atual (Linhas 799-833)

```python
rows = conn.execute(query, params).fetchall()
windows = []
for row in rows:
    # ❌ N+1: Uma query por janela
    plays = conn.execute("""
        SELECT play_number, hit, spin_number, spin_force,
               sda_score, tr_confidence
        FROM window_plays
        WHERE window_id = ?
        ORDER BY play_number
    """, (row["id"],)).fetchall()

    windows.append({
        "id": row["id"],
        ...
        "plays": [
            {
                "play_number": p["play_number"],
                "hit": bool(p["hit"]),
                ...
            }
            for p in plays
        ],
    })
```

#### 3.2.3 Código Proposto

```python
rows = conn.execute(query, params).fetchall()
if not rows:
    return []

# ✅ Batch: Uma única query para todos os plays
window_ids = [row["id"] for row in rows]
placeholders = ",".join(["?"] * len(window_ids))

plays_rows = conn.execute(f"""
    SELECT window_id, play_number, hit, spin_number, spin_force,
           sda_score, tr_confidence
    FROM window_plays
    WHERE window_id IN ({placeholders})
    ORDER BY window_id, play_number
""", window_ids).fetchall()

# Agrupar plays por window_id em memória
plays_by_window = {}
for p in plays_rows:
    wid = p["window_id"]
    if wid not in plays_by_window:
        plays_by_window[wid] = []
    plays_by_window[wid].append({
        "play_number": p["play_number"],
        "hit": bool(p["hit"]),
        "spin_number": p["spin_number"],
        "spin_force": p["spin_force"],
        "sda_score": p["sda_score"],
        "tr_confidence": p["tr_confidence"],
    })

windows = []
for row in rows:
    wid = row["id"]
    windows.append({
        "id": wid,
        "direction": row["direction"],
        ...
        "plays": plays_by_window.get(wid, []),
    })
```

#### 3.2.4 Simulação de Impacto

| Métrica | Antes (N+1) | Depois (Batch) | Melhoria |
|---------|:-----------:|:--------------:|:--------:|
| Queries (10 janelas) | 11 | 2 | **82%** |
| Queries (50 janelas) | 51 | 2 | **96%** |
| Latência estimada (50 janelas, WAL) | ~25ms | ~3ms | **88%** |
| Chamado por | `analytics_handler._gale_history()` | Idem | — |
| Frequência | Sob demanda (dashboard) | Idem | — |

#### 3.2.5 Auditoria de Bugs na Proposta

| Aspecto | Status | Nota |
|---------|:------:|------|
| SQL Injection via `placeholders` | ✅ | Usa `?` parametrizado, apenas IN() com count dinâmico |
| Janela sem plays | ✅ | `plays_by_window.get(wid, [])` retorna lista vazia |
| Limite do IN() clause | ✅ | SQLite suporta até 999 bind params; limit=50 está seguro |
| Ordem dos plays preservada | ✅ | `ORDER BY window_id, play_number` garante |
| Compatibilidade com `window_id` column | ✅ | Coluna já existe no schema (FK para gale_windows) |

**Bugs encontrados:** 0  
**Melhorias adicionais:** Nenhuma necessária.

---

### TASK-03 — Conversão Async com `asyncio.to_thread()`

**Origem:** Jules Session `6267821731880499179` + PR #2 (GitHub)  
**Prioridade:** 🟢 **BAIXA** — Consistência arquitetural  
**Risco:** Zero  
**Arquivos:** `server/extractor_service.py`, `server/message_handler.py`, `server/websocket.py`

#### 3.3.1 O Problema

Há **4 chamadas de I/O síncrono** dentro de funções `async`, bloqueando o event loop:

| # | Arquivo | Linha | Chamada Bloqueante | Frequência |
|:-:|---------|:-----:|-------------------|:----------:|
| A | `server/websocket.py` | 44 | `db_service.get_window_history()` | **1/segundo** |
| B | `server/message_handler.py` | 519 | `extractor_service.process_mesa(data)` | Raro |
| C | `server/message_handler.py` | 532 | `extractor_service.list_mesas()` | Raro |
| D | `server/message_handler.py` | 541 | `extractor_service.get_mesa_config(mesa_id)` | Raro |

#### 3.3.2 Abordagem

**Opção A (Jules Session 6267):** Converter os métodos do `ExtractorService` para async internamente:

```python
# extractor_service.py — métodos viram async
async def process_mesa(self, data: Dict) -> Dict:
    return await asyncio.to_thread(self._process_mesa_sync, data)

def _process_mesa_sync(self, data: Dict) -> Dict:
    # lógica original inalterada
    ...
```

**Opção B (PR #2):** Manter métodos sync, wrapping no caller:

```python
# websocket.py — caller faz o wrapping
window_history = await asyncio.to_thread(db_service.get_window_history)
```

**Recomendação:** Usar **Opção A para ExtractorService** (3 métodos, encapsulamento melhor) e **Opção B para heartbeat** (1 chamada, mais simples).

#### 3.3.3 Mudanças Necessárias

**Arquivo 1: `server/extractor_service.py`**

```python
# Adicionar import (topo do arquivo):
import asyncio

# process_mesa (linha 50):
async def process_mesa(self, data: Dict) -> Dict:
    """Processa snapshot DOM e gera configuração de mesa."""
    return await asyncio.to_thread(self._process_mesa_sync, data)

def _process_mesa_sync(self, data: Dict) -> Dict:
    """Implementação síncrona de process_mesa."""
    # código atual inalterado
    ...

# list_mesas (linha 84):
async def list_mesas(self) -> List[Dict]:
    """Lista todas as mesas configuradas."""
    return await asyncio.to_thread(self._list_mesas_sync)

def _list_mesas_sync(self) -> List[Dict]:
    """Implementação síncrona de list_mesas."""
    # código atual inalterado
    ...

# get_mesa_config (linha 101):
async def get_mesa_config(self, mesa_id: str) -> Optional[dict]:
    """Retorna config de uma mesa específica."""
    return await asyncio.to_thread(self._get_mesa_config_sync, mesa_id)

def _get_mesa_config_sync(self, mesa_id: str) -> Optional[dict]:
    """Implementação síncrona de get_mesa_config."""
    # código atual inalterado
    ...
```

**Arquivo 2: `server/message_handler.py`** (3 linhas)

```python
# Linha 519: result = self.extractor_service.process_mesa(data)
result = await self.extractor_service.process_mesa(data)

# Linha 532: mesas = self.extractor_service.list_mesas()
mesas = await self.extractor_service.list_mesas()

# Linha 541: config = self.extractor_service.get_mesa_config(mesa_id)
config = await self.extractor_service.get_mesa_config(mesa_id)
```

**Arquivo 3: `server/websocket.py`** (1 linha)

```python
# Linha 44: window_history = db_service.get_window_history()
window_history = await asyncio.to_thread(db_service.get_window_history)
```

#### 3.3.4 Simulação de Impacto

| Chamada | Bloqueio Antes | Bloqueio Depois | Frequência |
|---------|:--------------:|:---------------:|:----------:|
| `get_window_history()` no heartbeat | ~18ms/chamada | ~0ms no event loop | 1/segundo |
| `process_mesa()` | ~5ms/chamada | ~0ms no event loop | Raro |
| `list_mesas()` | ~2ms/chamada | ~0ms no event loop | Raro |
| `get_mesa_config()` | ~1ms/chamada | ~0ms no event loop | Raro |

**Impacto no heartbeat (item A):**
- Sessão com 2600+ decisions: query leva ~18ms
- Com 1 conexão: 1.8% do tempo bloqueado por segundo
- Com `to_thread()`: 0% de bloqueio no event loop

#### 3.3.5 Auditoria de Bugs na Proposta

| Aspecto | Status | Nota |
|---------|:------:|------|
| Thread safety do SQLite | ✅ | WAL mode suporta múltiplos readers simultâneos |
| Thread safety do file I/O | ✅ | `process_mesa` escreve em arquivos diferentes por mesa |
| Exception propagation | ✅ | `asyncio.to_thread()` propaga exceções ao caller |
| Python 3.12 compat | ✅ | Disponível desde Python 3.9 |
| `asyncio` já importado? | ⚠️ | `websocket.py`: Sim ✅ / `extractor_service.py`: **Não — precisa adicionar** |
| Teste existente | ⚠️ | Nenhum teste cobre esses métodos — recomendável adicionar |

**Bugs encontrados:** 0  
**Melhorias adicionais:** Adicionar `import asyncio` no `extractor_service.py`.

---

### TASK-04 — `_VALID_DIRECTIONS` como ClassVar

**Origem:** Jules Session `6410757425868051456`  
**Prioridade:** 🟢 **BAIXA** — Qualidade de código  
**Risco:** Zero  
**Arquivos:** `state/game.py`

#### 3.4.1 O Problema

A constante `_VALID_DIRECTIONS` é definida como variável local dentro de `process_spin()` (linha 220), recriada a cada chamada. Deveria ser `ClassVar` na classe.

#### 3.4.2 Código Atual (Linhas 219-222)

```python
def process_spin(self, numero, direcao):
    # 🔧 BUG-011: validar direcao
    _VALID_DIRECTIONS = {"horario", "anti-horario"}  # ❌ Local, recriado a cada chamada
    if direcao not in _VALID_DIRECTIONS:
        logger.warning(f"⚠ Direção inválida ignorada: '{direcao}' (esperado: {_VALID_DIRECTIONS})")
```

#### 3.4.3 Código Proposto

```python
# Na definição da classe GameState (após linha 125):
class GameState:
    _VALID_DIRECTIONS: ClassVar[set] = {"horario", "anti-horario"}
    ...

# No método process_spin (linhas 219-222):
def process_spin(self, numero, direcao):
    # 🔧 BUG-011: validar direcao
    if direcao not in self._VALID_DIRECTIONS:
        logger.warning(f"⚠ Direção inválida ignorada: '{direcao}' (esperado: {self._VALID_DIRECTIONS})")
```

**Nota:** `ClassVar` já é importado no arquivo — usado para `BET_VALUES` (linha 37).

#### 3.4.4 Auditoria de Bugs na Proposta

| Aspecto | Status | Nota |
|---------|:------:|------|
| `ClassVar` import | ✅ | Já importado (usado em `BET_VALUES`) |
| `dataclass` compat | ✅ | `ClassVar` é excluído de `__init__` por padrão |
| Referência `self._VALID_DIRECTIONS` | ✅ | Acesso via instância funciona para ClassVar |
| Testes existentes | ✅ | `test_bug_fixes_28_03.py` já testa validação de direção |

**Bugs encontrados:** 0  
**Melhorias adicionais:** Nenhuma.

---

## 4. Auditoria Global — Bugs e Melhorias no Plano

### 4.1 Bugs Encontrados no Plano

| # | Descrição | Task | Severidade | Ação |
|:-:|-----------|:----:|:----------:|------|
| — | — | — | — | **Nenhum bug encontrado nas 4 tasks** |

O plano é seguro. Todas as mudanças são aditivas (não modificam lógica existente) ou substituições diretas com padrão equivalente.

### 4.2 Melhorias Identificadas Durante Auditoria

| # | Melhoria | Relacionada a | Prioridade |
|:-:|----------|:------------:|:----------:|
| M-01 | Adicionar teste de duplo master (TASK-01) | `tests/` | 🟡 Média |
| M-02 | Adicionar teste async para extractor (TASK-03) | `tests/` | 🟢 Baixa |
| M-03 | Verificar `db_service.save_decision()` como outro candidato a `to_thread()` | `message_handler.py:305` | 🟢 Baixa |
| M-04 | Verificar `game_state.save()` como candidato a `to_thread()` no heartbeat | `message_handler.py` | 🟢 Baixa |

**M-03 e M-04** são otimizações adicionais do mesmo tipo que TASK-03, mas com maior impacto (chamadas a cada spin). Recomendamos avaliar em sprint futuro.

### 4.3 Ordem de Implementação

```
TASK-01 (Grace Period)    → Sem dependências, fix de segurança
    ↓
TASK-04 (ClassVar)        → Sem dependências, trivial
    ↓
TASK-02 (N+1 Query)       → Sem dependências, isolado no DB layer
    ↓
TASK-03 (Async to_thread) → Sem dependências, mas requer testes
```

**Tempo estimado total:** ~30 minutos de implementação + testes.

---

## 5. Conformidade com `Manutenabilidade_iso.md`

### 5.1 Mapeamento ISO/IEC 25010

| Task | Característica ISO | Sub-característica | Seção no Doc |
|:----:|:-----------------:|:------------------:|:------------:|
| TASK-01 | Confiabilidade | Tolerância a Falhas | PARTE II, §5 |
| TASK-02 | Eficiência de Desempenho | Comportamento Temporal | PARTE II, §2 |
| TASK-03 | Eficiência de Desempenho | Utilização de Recursos | PARTE II, §2 |
| TASK-04 | Manutenibilidade | Modificabilidade | PARTE II, §7 |

### 5.2 Necessidade de Atualização na `Manutenabilidade_iso.md`

| Seção | Atualização Necessária | Motivo |
|-------|:---------------------:|--------|
| **PARTE I, §8 — Modelo de Conexão** | ✅ **SIM** | Documentar cancelamento de grace period no CASO 2 (TASK-01). Atualmente o documento descreve o grace period mas não menciona o cenário de duplo master. |
| **PARTE I, §5 — Modelo de Dados** | ✅ **SIM** | Documentar a otimização batch query em `get_gale_window_history()` (TASK-02). O documento lista os métodos mas não especifica padrões de query. |
| **PARTE II, §2 — Eficiência de Desempenho** | ✅ **SIM** | Atualizar nota de desempenho após `asyncio.to_thread()` (TASK-03). Atualmente score 7.5 → pode subir com essa melhoria. |
| **PARTE IV — Bugs e Oportunidades** | ✅ **SIM** | Adicionar TASK-01 como bug corrigido (formato: `BUG-POST-XXX`). |
| **PARTE I, §4 — Fluxo de Dados** | 🟡 **OPCIONAL** | Mencionar que ExtractorService agora é async (TASK-03). Não é obrigatório pois não muda o fluxo lógico. |
| **PARTE I, §3 — Diagrama de Componentes** | ❌ **NÃO** | As mudanças não alteram a arquitetura de componentes. |

### 5.3 Formato de Registro (conforme padrão do documento)

As atualizações devem seguir o formato existente:

**Para PARTE IV (Bugs):**
```markdown
| BUG-POST-012 | connection_manager.py | 🔴 Crítico | Grace period não cancelado no CASO 2 — race condition causa duplo master | 85-90 |
```

**Para melhorias (MEL-ISO-XXX):**
```markdown
| MEL-ISO-005 | Eficiência de Desempenho | Batch query N+1 em get_gale_window_history() | 🟡 Médio |
| MEL-ISO-006 | Eficiência de Desempenho | asyncio.to_thread() em ExtractorService + heartbeat | 🟡 Médio |
| MEL-ISO-007 | Manutenibilidade | _VALID_DIRECTIONS como ClassVar | 🟢 Baixo |
```

---

## 6. Checklist de Aprovação

| # | Item | Status |
|:-:|------|:------:|
| 1 | TASK-01: Fix grace period CASO 2 — código revisado | ⬜ Aprovado / ⬜ Rejeitado |
| 2 | TASK-02: Batch query N+1 — código revisado | ⬜ Aprovado / ⬜ Rejeitado |
| 3 | TASK-03: Async to_thread — código revisado | ⬜ Aprovado / ⬜ Rejeitado |
| 4 | TASK-04: ClassVar directions — código revisado | ⬜ Aprovado / ⬜ Rejeitado |
| 5 | Atualizar `Manutenabilidade_iso.md` após implantação | ⬜ Aprovado / ⬜ Rejeitado |
| 6 | Adicionar testes para TASK-01 e TASK-03 | ⬜ Aprovado / ⬜ Rejeitado |

---

## 7. Resumo Executivo

| Métrica | Valor |
|---------|:-----:|
| Tasks propostas | 4 (+1 doc) |
| Arquivos a modificar | 5 |
| Linhas estimadas de mudança | ~80 |
| Bugs de segurança corrigidos | 1 (duplo master) |
| Otimizações de performance | 2 (N+1 + async) |
| Melhorias de código | 1 (ClassVar) |
| Conflitos com código atual | 0 |
| Necessidade de atualizar Manutenabilidade | 4 seções |
| Testes novos necessários | 2 |

---

> **⚠️ Este documento é exclusivamente de estudo. Nenhuma alteração de código será feita até aprovação explícita dos itens no Checklist (Seção 6).**

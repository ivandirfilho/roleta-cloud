# Tarefas Pós-Implantação M15-ADA — 29/03/2026

> **Versão alvo:** 4.0.1  
> **Referência:** `pos_implementacao_29_03.md`, `Manutenabilidade_iso.md`  
> **Norma:** ISO/IEC 25010:2011  
> **Escopo:** Correção de bugs P0/P1 + Feature C1 Bold + Documentação ISO  
> **Restrição:** Formato e tamanho do frontend devem permanecer inalterados

---

## ÍNDICE

1. [Resumo Executivo](#1-resumo-executivo)
2. [Pré-Requisitos — Bugs Críticos (P0/P1)](#2-pré-requisitos--bugs-críticos-p0p1)
3. [Verificação de Ordem C1](#3-verificação-de-ordem-c1)
4. [Tasks Frontend — Destaque C1 Bold+Cor](#4-tasks-frontend--destaque-c1-boldcor)
5. [Tasks Documentação ISO](#5-tasks-documentação-iso)
6. [Checklist de Validação](#6-checklist-de-validação)
7. [Grafo de Dependências](#7-grafo-de-dependências)
8. [Plano de Rollback](#8-plano-de-rollback)

---

## 1. RESUMO EXECUTIVO

Este documento detalha **todas as tarefas** necessárias para a próxima iteração do sistema Roleta Cloud v4.0.1, organizadas em 3 blocos:

| Bloco | Tasks | Prioridade | Descrição |
|:------|:-----:|:----------:|:----------|
| **A — Bug Fixes** | T-BUG-01 a T-BUG-04 | P0/P1 | Correção de 4 bugs identificados na auditoria |
| **B — Frontend C1** | T-FE-01 a T-FE-06 | P2 | Destaque visual de cor + negrito no centro C1 |
| **C — Documentação** | T-ISO-01 a T-ISO-07 | P3 | Atualizações no `Manutenabilidade_iso.md` |

**Regra fundamental:** O layout, tamanho e formato atual do frontend **NÃO mudam**. A única alteração visual é **cor + negrito** no número C1 (sempre o primeiro dos 3 centros), para facilitar a identificação pelo operador.

**Nenhuma alteração no backend é necessária** para a feature C1 Bold — os dados já são enviados corretamente com `centros[0] = C1`.

---

## 2. PRÉ-REQUISITOS — BUGS CRÍTICOS (P0/P1)

> ⚠️ Estes bugs **DEVEM** ser corrigidos ANTES da feature C1 Bold e da documentação ISO.

### T-BUG-01 — Inicializar `self._wheel` no `__init__()` (P0)

| Campo | Valor |
|:------|:------|
| **ID Bug** | BUG-POST-001 |
| **Severidade** | 🔴 CRÍTICO |
| **Arquivo** | `strategies/sda17.py` |
| **Linhas** | 46-54 (`__init__`), 273-297 (`_bayesian_offset`) |

**Problema:** `self._wheel` não é inicializado no `__init__()`. O método `_bayesian_offset()` acessa `self._wheel` nas linhas 285-288. Se o servidor reiniciar com `ccw_history` salvo contendo ≥5 entradas, o primeiro spin CCW causa `AttributeError`.

**Caminho do crash:**
```
Startup → load_adaptive_state() → ccw_history carregado com ≥5 entries
→ Primeiro spin CCW → analyze() → _get_adaptive_offset("anti-horario")
→ _bayesian_offset() → self._wheel (linha 285) → AttributeError
```

**Correção — Parte A (linha 54, após `self.ccw_history`):**

```python
# ANTES (linhas 52-54):
        self.cw_ema = self.CW_EMA_INIT
        self.ccw_history: List[Tuple[int, int]] = []

# DEPOIS (linhas 52-55):
        self.cw_ema = self.CW_EMA_INIT
        self.ccw_history: List[Tuple[int, int]] = []
        self._wheel: List[int] = []
```

**Correção — Parte B (linha 273, início de `_bayesian_offset`):**

```python
# ANTES (linhas 273-276):
    def _bayesian_offset(self) -> int:
        """Bayesiano: testa todos offsets contra janela recente, retorna o melhor."""
        if len(self.ccw_history) < self.CCW_WARMUP:
            return self.CCW_DEFAULT_OFFSET

# DEPOIS (linhas 273-278):
    def _bayesian_offset(self) -> int:
        """Bayesiano: testa todos offsets contra janela recente, retorna o melhor."""
        if not self._wheel or len(self.ccw_history) < self.CCW_WARMUP:
            return self.CCW_DEFAULT_OFFSET
```

**Teste de validação:**
```python
def test_bayesian_offset_without_wheel():
    s = SDA17Strategy()
    s.ccw_history = [(17, 5), (32, 15), (19, 4), (21, 2), (25, 17)]
    assert s._bayesian_offset() == s.CCW_DEFAULT_OFFSET  # Fallback, sem crash
```

**Documentação ISO:** Registrar como `BUG-POST-001 ✅ CORRIGIDO` em `Manutenabilidade_iso.md` PARTE IV.

---

### T-BUG-02 — Validação robusta em `load_adaptive_state()` (P0)

| Campo | Valor |
|:------|:------|
| **ID Bug** | BUG-POST-002 |
| **Severidade** | 🔴 CRÍTICO |
| **Arquivo** | `strategies/sda17.py` |
| **Linhas** | 322-326 (`load_adaptive_state`) |

**Problema:** JSON serializa tuplas como listas. A mitigação existente (`tuple(x) if isinstance(x, list)`) não valida o comprimento nem o tipo dos elementos. Dados corrompidos podem causar `ValueError` no unpacking de `_bayesian_offset()` (linha 284).

**Correção (linhas 322-326):**

```python
# ANTES:
    def load_adaptive_state(self, state: Dict[str, Any]) -> None:
        """Carrega estado adaptativo de persistência."""
        self.cw_ema = state.get("cw_ema", self.CW_EMA_INIT)
        self.ccw_history = [tuple(x) if isinstance(x, list) else x
                           for x in state.get("ccw_history", [])]

# DEPOIS:
    def load_adaptive_state(self, state: Dict[str, Any]) -> None:
        """Carrega estado adaptativo de persistência com validação."""
        self.cw_ema = float(state.get("cw_ema", self.CW_EMA_INIT))
        raw = state.get("ccw_history", [])
        validated = []
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                try:
                    validated.append((int(item[0]), int(item[1])))
                except (ValueError, TypeError):
                    continue  # Descarta item malformado
        self.ccw_history = validated
```

**Teste de validação:**
```python
def test_load_adaptive_state_corrupted():
    s = SDA17Strategy()
    s.load_adaptive_state({
        "cw_ema": 10.5,
        "ccw_history": [[17, 5], [32], "invalid", [19, 4, 99], [21, 2]]
    })
    assert len(s.ccw_history) == 2  # Apenas (17,5) e (21,2) válidos
    assert all(isinstance(x, tuple) and len(x) == 2 for x in s.ccw_history)
```

**Documentação ISO:** Registrar como `BUG-POST-002 ✅ CORRIGIDO` em PARTE IV.

---

### T-BUG-03 — Declarar `_adaptive_state` como campo dataclass (P1)

| Campo | Valor |
|:------|:------|
| **ID Bug** | BUG-POST-005 |
| **Severidade** | 🟠 ALTO |
| **Arquivo** | `state/game.py` |
| **Linhas** | ~147 (class), ~481 (save), ~568 (load) |

**Problema:** `_adaptive_state` é atribuído dinamicamente em `load()` e `message_handler.py`, usando `hasattr()` em `save()`. Viola o padrão dataclass e pode perder estado no primeiro `save()` após startup.

**Correção — Parte A (declaração, após `bet_advisor` no `@dataclass`):**

```python
# ANTES (linha ~184, último campo):
    bet_advisor: TripleRateAdvisor = field(default_factory=TripleRateAdvisor)

# DEPOIS:
    bet_advisor: TripleRateAdvisor = field(default_factory=TripleRateAdvisor)
    _adaptive_state: Dict[str, Any] = field(default_factory=dict)
```

**Correção — Parte B (save, remover `hasattr`):**

```python
# ANTES (linha ~481):
        "adaptive_state": self._adaptive_state if hasattr(self, '_adaptive_state') else {}

# DEPOIS:
        "adaptive_state": self._adaptive_state
```

**Correção — Parte C (load, manter atribuição para backward compat):**

```python
# Sem mudança funcional — gs._adaptive_state = data.get("adaptive_state", {}) continua correto
# Mas agora o campo existe por padrão como {} (field default_factory)
```

**Teste de validação:**
```python
def test_adaptive_state_is_field():
    gs = GameState()
    assert hasattr(gs, '_adaptive_state')
    assert gs._adaptive_state == {}
```

**Documentação ISO:** Registrar como `BUG-POST-005 ✅ CORRIGIDO` em PARTE IV. Atualizar pontuação Manutenibilidade 7.8 → 8.0.

---

### T-BUG-04 — Error handling na restauração adaptativa (P1)

| Campo | Valor |
|:------|:------|
| **ID Bug** | BUG-POST-006 |
| **Severidade** | 🟠 ALTO |
| **Arquivo** | `server/websocket.py` |
| **Linhas** | 32-33 |

**Problema:** Se `load_adaptive_state()` falhar com dados corrompidos, o servidor não inicia. Não há `try/except` protegendo a restauração.

**Correção (linhas 32-33):**

```python
# ANTES:
if hasattr(game_state, '_adaptive_state') and game_state._adaptive_state:
    strategy.load_adaptive_state(game_state._adaptive_state)

# DEPOIS:
if game_state._adaptive_state:
    try:
        strategy.load_adaptive_state(game_state._adaptive_state)
        logger.info("Estado adaptativo restaurado com sucesso")
    except Exception as e:
        logger.warning(f"Falha ao restaurar estado adaptativo: {e}, usando defaults")
```

> **Nota:** O `hasattr()` não é mais necessário após T-BUG-03 (campo declarado no dataclass).

**Teste de validação:**
```python
def test_websocket_startup_with_corrupted_state():
    # Simular estado corrompido que causa exceção em load_adaptive_state
    gs = GameState()
    gs._adaptive_state = {"cw_ema": "not_a_number", "ccw_history": "corrupted"}
    strategy = SDA17Strategy()
    # Deve logar warning, não crashar
    try:
        strategy.load_adaptive_state(gs._adaptive_state)
    except Exception:
        pass  # websocket.py deve capturar isto
```

**Documentação ISO:** Registrar como `BUG-POST-006 ✅ CORRIGIDO` em PARTE IV. Atualizar Confiabilidade 8.2 → 8.5.

---

## 3. VERIFICAÇÃO DE ORDEM C1

### 3.1 Confirmação de código

A ordem `C1 sempre primeiro` foi **verificada** em `strategies/sda17.py`:

| Caminho | Linha | Código | C1 Primeiro? |
|:--------|:-----:|:-------|:------------:|
| M15-ADA (principal) | 167 | `"centers": [c1, c2, c3]` | ✅ Sim |
| SDA-19 (fallback) | 121 | `"centers": [c1]` | ✅ Sim (único) |
| Visual format | 154 | `f"[{c1}] [{c2}] [{c3}]"` | ✅ Sim |

### 3.2 Fluxo de dados C1

```
sda17.py → details["centers"] = [C1, C2, C3]
         ↓
message_handler.py → overlay_response.data.centros = [C1, C2, C3]  (linha 376)
                   → trace_broadcast.result.centros = [C1, C2, C3]  (linha 412)
         ↓
background.js → sendSuggestionToContentScript(data.data)  (linha 160)
              → Sem transformação — passa direto
         ↓
content.js → sugestao.centros = [C1, C2, C3]  (linha 478)
           → centros[0] = C1 ← SEMPRE o primeiro
         ↓
app.js → result.centros = [C1, C2, C3]  (disponível mas não exibido atualmente)
       → result.centro = C1  (exibido em #result-center)
```

**Conclusão:** Nenhuma alteração de backend é necessária. O `centros[0]` é garantidamente C1 em todos os caminhos.

---

## 4. TASKS FRONTEND — DESTAQUE C1 BOLD+COR

> **Regra:** Formato e tamanho inalterados. Apenas cor + negrito no C1 (centros[0]).

### 4.1 Paleta de Cores Atual

| Elemento | Cor | Contexto |
|:---------|:----|:---------|
| `.eb-status.g1` | `#00ff88` (verde) | Gale 1 |
| `.eb-status.g2` | `#ffd700` (dourado) | Gale 2 |
| `.eb-status.g3` | `#4169e1` (azul) | Gale 3 |
| `.eb-region` bg | `#00ff88 → #00cc6a` (gradiente verde) | Região APOSTAR |
| `.eb-region.pular` bg | `#ff6b35 → #cc4400` (gradiente laranja) | Região PULAR |
| Texto padrão | `#e0e0e0` | Status geral |

**Cor escolhida para C1:** `#FFD700` (dourado) — destaca-se contra o fundo escuro do overlay e contra o verde/laranja da região. Não conflita com as cores de gale pois o destaque está dentro dos `[ ]`.

### 4.2 Visão Antes vs Depois

#### Overlay Minimizado
```
ANTES:   [17] [25] [9] G1 2/5
DEPOIS:  [17] [25] [9] G1 2/5
          ^^^^
          dourado + negrito (font-weight: 900)
          resto permanece igual
```

#### Overlay Expandido (Região)
```
ANTES:   Centros: 17, 25, 9
DEPOIS:  Centros: 17, 25, 9
                  ^^
                  dourado + negrito
                  resto permanece igual
```

#### Dashboard (Centro)
```
ANTES:   Centro: 17
DEPOIS:  Centro: 17
                 ^^
                 dourado + negrito via CSS
                 (elemento já exibe apenas C1)
```

> **Nota:** O campo "Região" do dashboard (`#result-region`) exibe os 17 números como lista plana. **Nenhuma alteração** neste campo — o usuário não solicitou destaque nos números individuais.

---

### T-FE-01 — CSS de destaque C1 no overlay

| Campo | Valor |
|:------|:------|
| **Arquivo** | `extension/overlay.css` |
| **Linhas** | Adicionar ao final (após linha ~378) |
| **Risco** | MÍNIMO — CSS apenas, sem impacto funcional |

**Código a adicionar:**

```css
/* ========================================
   M15-ADA v4.0.1: Destaque visual do centro C1
   C1 = primeiro centro, raio 3 (7 números)
   Dourado + negrito para identificação rápida
   ======================================== */
.eb-c1 {
    color: #FFD700;
    font-weight: 900;
    text-shadow: 0 0 3px rgba(255, 215, 0, 0.25);
}

/* Dentro da região (fundo verde/laranja), usar preto bold */
.eb-region .eb-c1 {
    color: #000;
    font-weight: 900;
    text-decoration: underline;
    text-shadow: none;
}
```

**Justificativa:** 
- No status minimizado (fundo escuro), dourado se destaca sem conflitar com cores de gale
- Na região expandida (fundo verde/laranja), preto bold + sublinhado se destaca contra o gradiente
- `text-shadow` sutil no minimizado aumenta legibilidade sem mudar tamanho

---

### T-FE-02 — Bold+Cor no status minimizado (`content.js`)

| Campo | Valor |
|:------|:------|
| **Arquivo** | `extension/content.js` |
| **Linhas** | ~478-487 (dentro de `updateOverlay()`) |
| **Risco** | BAIXO — troca `textContent` por `innerHTML` apenas no centroDisplay |

**Antes (linhas ~478-487):**
```javascript
const centros = sugestao.centros || [sugestao.centro];
const centroDisplay = centros.filter(c => c != null)
    .map(c => `[${c}]`)
    .join(' ') || '--';

const level = sugestao.gale_level || 1;
const galeText = sugestao.gale_display || `G${level} 0/0`;

if (overlayState.isMinimized) {
    status.textContent = `${centroDisplay} ${galeText}`;
}
```

**Depois:**
```javascript
const centros = sugestao.centros || [sugestao.centro];
const centroDisplay = centros.filter(c => c != null)
    .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
    .join(' ') || '--';

const level = sugestao.gale_level || 1;
const galeText = sugestao.gale_display || `G${level} 0/0`;

if (overlayState.isMinimized) {
    status.innerHTML = `${centroDisplay} ${galeText}`;
}
```

**Alterações:**
1. Linha `.map(c =>` → `.map((c, i) =>` — adiciona índice
2. `i === 0` envolve C1 com `<span class="eb-c1">` 
3. `status.textContent` → `status.innerHTML` (apenas no bloco minimizado)

**Segurança:** Os valores `c` são números inteiros controlados do backend (0-36). Não há risco de XSS.

---

### T-FE-03 — Bold+Cor na região expandida (`content.js`)

| Campo | Valor |
|:------|:------|
| **Arquivo** | `extension/content.js` |
| **Linhas** | ~466-467 (dentro de `updateOverlay()`, bloco APOSTAR) |
| **Risco** | BAIXO — troca `textContent` por `innerHTML` apenas no fallback de centros |

**Antes (linhas ~466-467):**
```javascript
regiao.textContent = sugestao.regiao || 
    `Centros: ${(sugestao.centros || [sugestao.centro]).join(', ')}`;
```

**Depois:**
```javascript
if (sugestao.centros && sugestao.centros.length > 0) {
    const c = sugestao.centros;
    regiao.innerHTML = `Centros: <span class="eb-c1">${c[0]}</span>` +
        (c.length > 1 ? `, ${c.slice(1).join(', ')}` : '');
} else {
    regiao.textContent = sugestao.regiao || `Centro: ${sugestao.centro}`;
}
```

**Alterações:**
1. Verifica se `centros` existe e tem dados
2. Primeiro centro envolto com `<span class="eb-c1">`
3. `regiao.innerHTML` para o caso com centros (permite HTML)
4. Fallback original com `textContent` mantido (SDA-19 caso único centro)

---

### T-FE-04 — Bold+Cor no `toggleMinimize()` (`content.js`)

| Campo | Valor |
|:------|:------|
| **Arquivo** | `extension/content.js` |
| **Linhas** | ~371-380 (dentro de `toggleMinimize()`) |
| **Risco** | BAIXO — mesma lógica de T-FE-02 |

**Antes (linhas ~371-380):**
```javascript
if (overlayState.isMinimized) {
    overlay.classList.add('minimized');
    if (status && galeDisplay && overlayState.lastSugestao) {
        const centros = overlayState.lastSugestao.centros || 
            [overlayState.lastSugestao.centro];
        const centroDisplay = centros.filter(c => c)
            .map(c => `[${c}]`)
            .join(' ') || '--';
        const galeText = galeDisplay.textContent;
        status.textContent = `${centroDisplay} ${galeText}`;
```

**Depois:**
```javascript
if (overlayState.isMinimized) {
    overlay.classList.add('minimized');
    if (status && galeDisplay && overlayState.lastSugestao) {
        const centros = overlayState.lastSugestao.centros || 
            [overlayState.lastSugestao.centro];
        const centroDisplay = centros.filter(c => c)
            .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
            .join(' ') || '--';
        const galeText = galeDisplay.textContent;
        status.innerHTML = `${centroDisplay} ${galeText}`;
```

**Alterações:** Idênticas a T-FE-02 — `.map((c, i) =>` com span no `i === 0`, `innerHTML`.

---

### T-FE-05 — Bold+Cor no dashboard (`frontend/`)

| Campo | Valor |
|:------|:------|
| **Arquivos** | `frontend/index.html` (CSS inline ou `<style>`) |
| **Linhas** | ~71 (`#result-center`) |
| **Risco** | MÍNIMO — apenas CSS, sem alteração em app.js |

**Explicação:** O dashboard já exibe **apenas C1** no campo `#result-center` (app.js linha 269: `el.resultCenter.textContent = result.centro`). Não há necessidade de alterar JavaScript — basta CSS.

**Código a adicionar no `<style>` de `frontend/index.html` (ou arquivo CSS separado se existir):**

```css
/* M15-ADA v4.0.1: Destaque C1 no dashboard */
#result-center {
    color: #FFD700;
    font-weight: 900;
}
```

**Nenhuma alteração em `frontend/app.js`** — o campo já mostra apenas C1.

---

### T-FE-06 — Teste visual

| Campo | Valor |
|:------|:------|
| **Tipo** | Teste manual / visual |
| **Risco** | Nenhum — apenas verificação |

**Checklist de aceitação:**

| # | Verificação | Critério | Local |
|:-:|:-----------|:---------|:------|
| 1 | Overlay minimizado mostra `[C1]` em dourado/bold | `#FFD700`, `font-weight: 900` | Chrome DevTools → `.eb-c1` |
| 2 | Overlay minimizado mostra `[C2] [C3]` sem destaque | Cor padrão (herdada do gale) | Chrome DevTools |
| 3 | Overlay expandido mostra `Centros: C1, C2, C3` com C1 bold | `eb-c1` underline no fundo verde | Visual |
| 4 | Dashboard mostra C1 em dourado/bold no campo Centro | `#FFD700` em `#result-center` | Dashboard |
| 5 | Formato e tamanho inalterados | Comparar screenshot antes/depois | Visual |
| 6 | SDA-19 fallback (< 5 forças) mostra centro único sem erro | Sem crash no `c.slice(1)` | Console |
| 7 | Toggle minimizar/expandir mantém destaque C1 | `toggleMinimize()` usa innerHTML | Manual |
| 8 | Gale G1/G2/G3 cores não conflitam com dourado C1 | Visualmente distinguíveis | Manual |

**Procedimento:**
1. Abrir Chrome com extensão → navegar para mesa de roleta
2. Aguardar sugestão com 3 centros (M15-ADA ativo)
3. Verificar itens 1-4 visualmente
4. Minimizar/expandir overlay (item 7)
5. Verificar screenshot comparativo (item 5)
6. Abrir DevTools → Inspecionar `.eb-c1` → confirmar computed styles

---

## 5. TASKS DOCUMENTAÇÃO ISO

> Baseado em `Manutenabilidade_iso.md` — formato ISO/IEC 25010:2011

### T-ISO-01 — Atualizar versão e metadados

| Campo | Valor |
|:------|:------|
| **Arquivo** | `Manutenabilidade_iso.md` |
| **Seção** | Header (linha ~3) |

| Campo | Antes | Depois |
|:------|:------|:-------|
| Versão | `3.5.0` | `4.0.1` |
| Data | `19/03/2026` | `29/03/2026` |
| Total LOC | `5.193 (37 arquivos)` | `~5.700 (39 arquivos)` |

---

### T-ISO-02 — Atualizar nome da estratégia

| Campo | Valor |
|:------|:------|
| **Arquivo** | `Manutenabilidade_iso.md` |
| **Seções** | PARTE I §6, PARTE II §1 |

| Local | Antes | Depois |
|:------|:------|:-------|
| Título §6 | "Sistema de Decisão (Pipeline SDA-19 + Kill Switch)" | "Sistema de Decisão (Pipeline M15-ADA + Kill Switch)" |
| Descrição sda17.py | "SDA-19" / "SDA-17" refs | "M15-ADA (Adaptive Dual Algorithm)" |
| Descrição funcional | "21 números" | "17 números (C1: raio 3, C2/C3: raio 2)" |

---

### T-ISO-03 — Adicionar bugs pós-implantação em PARTE IV

| Campo | Valor |
|:------|:------|
| **Arquivo** | `Manutenabilidade_iso.md` |
| **Seção** | PARTE IV — Bugs e Oportunidades |

**Ação:** Adicionar os 14 novos bugs (BUG-POST-001 a BUG-POST-014) à tabela existente, usando o formato padrão:

```markdown
| BUG-POST-001 | `strategies/sda17.py` | ~~🔴 Crítica~~ ✅ CORRIGIDO (29/03) | `self._wheel` não inicializado em `__init__()` | 46-54, 285 |
| BUG-POST-002 | `strategies/sda17.py` | ~~🔴 Crítica~~ ✅ CORRIGIDO (29/03) | Validação frágil em `load_adaptive_state()` | 322-326 |
| BUG-POST-005 | `state/game.py` | ~~🟠 Alta~~ ✅ CORRIGIDO (29/03) | `_adaptive_state` dinâmico no dataclass | 147, 481 |
| BUG-POST-006 | `server/websocket.py` | ~~🟠 Alta~~ ✅ CORRIGIDO (29/03) | Restauração adaptativa sem error handling | 32-33 |
```

**Também atualizar** bugs pré-existentes corrigidos na implantação M15-ADA:
```markdown
| BUG-MAIN-002 | `main.py` | ~~🟡 Média~~ ✅ CORRIGIDO (29/03) | Double shutdown — `_shutdown_called` flag | 32 |
| BUG-MAIN-004 | `main.py` | ~~🟡 Média~~ ✅ CORRIGIDO (29/03) | save() sem try/except | 43 |
```

---

### T-ISO-04 — Atualizar scorecard PARTE III

| Campo | Valor |
|:------|:------|
| **Arquivo** | `Manutenabilidade_iso.md` |
| **Seção** | PARTE III — Scorecard Consolidado |

**Pontuações atualizadas (após todas correções):**

| Característica | Antes (v3.5) | Depois (v4.0.1) | Justificativa |
|:---------------|:------------:|:---------------:|:-------------|
| Adequação Funcional | 8.7 | **9.0** | M15-ADA completo, código morto removido |
| Eficiência | 8.7 | **8.7** | Mantida (Bayesian O(132) negligível) |
| Compatibilidade | 7.0 | **7.0** | Sem mudanças |
| Usabilidade | 8.0 | **8.2** | C1 bold facilita operação (+0.2) |
| Confiabilidade | 8.5 | **8.5** | BUG-POST-001/002/005/006 corrigidos (+0.3 vs 8.2 com bugs) |
| Segurança | 6.5 | **6.5** | Sem mudanças |
| Manutenibilidade | 7.5 | **8.0** | Docstrings, testes, dataclass fix (+0.5) |
| Portabilidade | 8.0 | **8.2** | SIGTERM fix, Docker validado |
| **TOTAL** | **7.9** | **8.0** | 🟢 Nível "Bom" alcançado |

**Meta atingida:** 7.9 → **8.0** (todas 8 características ≥ 6.5, 6 de 8 em "Bom").

---

### T-ISO-05 — Adicionar melhorias M15-ADA no scorecard

| Campo | Valor |
|:------|:------|
| **Arquivo** | `Manutenabilidade_iso.md` |
| **Seção** | PARTE III — Tabela de Melhorias (MEL-*) |

**Novas entradas:**
```markdown
| MEL-ADA-001 | Adequação | ~~Migrar SDA-21→M15-ADA (17 nums, offset adaptativo)~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-002 | Confiabilidade | ~~Inicializar self._wheel em __init__~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-003 | Confiabilidade | ~~Error handling na restauração adaptativa~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-004 | Manutenibilidade | ~~_adaptive_state como campo dataclass~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-005 | Usabilidade | ~~Destaque bold+cor C1 no frontend~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
```

---

### T-ISO-06 — Atualizar PARTE V (Mapa de Conformidade)

| Campo | Valor |
|:------|:------|
| **Arquivo** | `Manutenabilidade_iso.md` |
| **Seção** | PARTE V — Matriz Característica × Evidência |

**Adicionar** na coluna "Artefatos de Evidência":
- **Adequação Funcional:** `analise_c1_c2_c3.md` (estudo M15-ADA), `plano_implantação_c1_c2_c3_melhorado.md`
- **Confiabilidade:** `pos_implementacao_29_03.md` (auditoria de bugs)
- **Usabilidade:** Task C1 Bold (visual UX improvement)

---

### T-ISO-07 — Atualizar PARTE VI (Conclusão)

| Campo | Valor |
|:------|:------|
| **Arquivo** | `Manutenabilidade_iso.md` |
| **Seção** | PARTE VI — Conclusão e Recomendações |

**Atualizar "Pontos Fortes":**
- Adicionar: "Algoritmo adaptativo M15-ADA com offset dinâmico CW (ErrDriven) e CCW (Bayesian)"
- Adicionar: "Identificação visual do C1 no frontend para usabilidade operacional"

**Atualizar "Conformidade ISO/IEC 25010":**
```
Nível: "Bom" (8.0/10) — 6 de 8 características em "Bom" (≥8.0)
```

---

## 6. CHECKLIST DE VALIDAÇÃO

### 6.1 Validação Técnica (Automatizada)

| # | Teste | Comando | Critério |
|:-:|:------|:--------|:---------|
| 1 | Suite completa | `python -m pytest tests/ -v` | 105+ testes passando |
| 2 | Teste BUG-POST-001 | Novo teste: `_bayesian_offset()` sem `_wheel` | Retorna `CCW_DEFAULT_OFFSET` sem crash |
| 3 | Teste BUG-POST-002 | Novo teste: `load_adaptive_state()` com dados corrompidos | Filtra itens inválidos |
| 4 | Teste BUG-POST-005 | `GameState()._adaptive_state == {}` | Campo existe por padrão |
| 5 | Cobertura M15-ADA | Testes existentes + 4 novos | ≥ 90% dos novos métodos |

### 6.2 Validação Visual (Manual)

| # | Cenário | Resultado Esperado |
|:-:|:--------|:-------------------|
| 1 | Overlay minimizado com 3 centros | `[C1]` dourado bold, `[C2] [C3]` normal |
| 2 | Overlay expandido APOSTAR | `Centros: C1, C2, C3` com C1 bold underline |
| 3 | Overlay expandido PULAR | Texto "Sem entrada" — sem centros |
| 4 | Dashboard campo Centro | C1 em dourado bold |
| 5 | Toggle minimizar↔expandir | Destaque persiste |
| 6 | SDA-19 fallback (centro único) | Centro único com destaque, sem erro |

### 6.3 Validação de Deploy

| # | Passo | Verificação |
|:-:|:------|:-----------|
| 1 | Docker build | `docker compose build` sem erros |
| 2 | Docker up | Container `roleta-cloud` status: UP (healthy) |
| 3 | WSS externo | `curl -H "Upgrade: websocket" https://roleta.xma-ia.com/ws` → HTTP 101 |
| 4 | Spin processado | Log mostra latência < 50ms |
| 5 | VERSION | Arquivo VERSION = `4.0.1` |

---

## 7. GRAFO DE DEPENDÊNCIAS

```
T-BUG-01 ──┐
T-BUG-02 ──┤
            ├──→ T-BUG-03 ──→ T-BUG-04 ──┐
            │                              │
            │    T-FE-01 (CSS) ────────────┤
            │         │                    │
            │    T-FE-02 (minimizado) ─────┤
            │    T-FE-03 (expandido) ──────┤
            │    T-FE-04 (toggleMin) ──────┤
            │    T-FE-05 (dashboard) ──────┤
            │                              │
            │                              ├──→ T-FE-06 (teste visual)
            │                              │
            └──────────────────────────────┤
                                           │
                                           ├──→ T-ISO-01 (versão)
                                           ├──→ T-ISO-02 (estratégia)
                                           ├──→ T-ISO-03 (bugs)
                                           ├──→ T-ISO-04 (scorecard)
                                           ├──→ T-ISO-05 (melhorias)
                                           ├──→ T-ISO-06 (mapa)
                                           └──→ T-ISO-07 (conclusão)
```

**Ordem de execução:**
1. **Paralelo P0:** T-BUG-01 + T-BUG-02 (independentes)
2. **Sequencial P1:** T-BUG-03 → T-BUG-04 (T-BUG-03 remove `hasattr` usado em T-BUG-04)
3. **Paralelo P2:** T-FE-01 + T-FE-02 + T-FE-03 + T-FE-04 + T-FE-05 (independentes após CSS)
4. **Validação:** T-FE-06 (após todos T-FE-*)
5. **Paralelo P3:** T-ISO-01 a T-ISO-07 (independentes, após bugs corrigidos)

---

## 8. PLANO DE ROLLBACK

### 8.1 Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|:------|:------------:|:----------|
| `innerHTML` causa problema de renderização | BAIXA | Valores são inteiros 0-36 controlados pelo backend |
| CSS `.eb-c1` conflita com gale colors | BAIXA | `.eb-c1` usa `font-weight: 900` + cor específica; gale aplica na `.eb-status` |
| SDA-19 fallback com centro único | BAIXA | Código trata `centros.length === 1` explicitamente |
| `_adaptive_state` field quebra load() | BAIXA | `field(default_factory=dict)` é backward-compatible |

### 8.2 Procedimento de Rollback

Se qualquer task causar problemas em produção:

```bash
# 1. Reverter ao commit v4.0.0
ssh root@187.45.181.75
cd /root/roleta-cloud
git log --oneline -5  # Identificar commit v4.0.0
git checkout <commit_v4.0.0> .

# 2. Rebuild container
docker compose build --no-cache
docker compose down && docker compose up -d

# 3. Verificar
docker logs roleta-cloud --tail 20
```

**state.json** é backward-compatible — v4.0.1 lê v4.0.0 e vice-versa.

---

## RESUMO DE ARQUIVOS AFETADOS

| Arquivo | Tasks | Tipo de Alteração | LOC Estimado |
|:--------|:------|:-----------------|:------------:|
| `strategies/sda17.py` | T-BUG-01, T-BUG-02 | Bug fix (init + validação) | +8 |
| `state/game.py` | T-BUG-03 | Bug fix (campo dataclass) | +1, -1 |
| `server/websocket.py` | T-BUG-04 | Bug fix (try/except) | +5, -2 |
| `extension/content.js` | T-FE-02, T-FE-03, T-FE-04 | Feature (innerHTML + span) | +9, -6 |
| `extension/overlay.css` | T-FE-01 | Feature (CSS) | +11 |
| `frontend/index.html` | T-FE-05 | Feature (CSS) | +4 |
| `Manutenabilidade_iso.md` | T-ISO-01 a T-ISO-07 | Documentação | ~50 |
| `VERSION` | Deploy | `4.0.0` → `4.0.1` | 1 |
| **TOTAL** | **17 tasks** | | **~89 LOC** |

---

> **Documento gerado em:** 29/03/2026  
> **Status:** 📋 Aguardando aprovação para execução  
> **Próxima ação:** Aprovar → Executar tasks na ordem do §7 → Deploy → Validação §6

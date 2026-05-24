# Melhorias Pós-Implementação — Auditoria C1 Bold v4.0.1

> **Versão:** 4.0.1 → 4.0.2  
> **Data:** 29/03/2026  
> **Referência:** `tarefas_pos_implementacao_29_03.md`, `Manutenabilidade_iso.md`  
> **Norma:** ISO/IEC 25010:2011  
> **Escopo:** Correção de bugs visuais no destaque C1 + melhorias de manutenibilidade

---

## 1. RESUMO DO PROBLEMA

Após a implantação do destaque C1 (v4.0.1), o número C1 em dourado **não aparece imediatamente** no overlay. O operador precisa **minimizar e restaurar** o overlay para que o dourado apareça. Após ~1 segundo, o dourado desaparece novamente.

**Causa raiz identificada:** 3 bugs interrelacionados no pipeline de renderização.

---

## 2. ANÁLISE DE CAUSA RAIZ

### 2.1 Fluxo de dados do overlay

```
Servidor → WebSocket → background.js → content.js
                          │                   │
                    ┌─────┴─────┐       ┌─────┴──────────────┐
                    │ sugestao  │       │ state_sync (1s)    │
                    │ (type)    │       │ (heartbeat)        │
                    └─────┬─────┘       └─────┬──────────────┘
                          │                   │
                   updateOverlay()    handleStateSync()
                          │                   │
                    ┌─────┴─────┐       ┌─────┴──────────────┐
                    │ EXPANDIDO │       │ Se MINIMIZADO:     │
                    │ regiao =  │       │ status.textContent │◄── BUG-FE-001
                    │ innerHTML │       │ SEM <span eb-c1>  │
                    │ com eb-c1 │       └────────────────────┘
                    ├───────────┤
                    │ eb-region │
                    │ .eb-c1 =  │
                    │ color:#000│◄── BUG-FE-002 (invisível)
                    └───────────┘
```

### 2.2 Sequência temporal do bug

```
t=0.00s  sugestao chega → updateOverlay() → status.innerHTML com <span class="eb-c1">
         ✅ C1 dourado aparece (por ~1 segundo)

t=1.00s  state_sync chega → handleStateSync() → status.textContent (sem span)
         ❌ C1 dourado DESTRUÍDO — texto plano sem formatação

t=2.00s  state_sync chega novamente → mesmo efeito
         ❌ C1 continua sem dourado

t=?      Usuário minimiza/restaura → toggleMinimize() → status.innerHTML com span
         ✅ C1 dourado reaparece (até próximo heartbeat em ~1s)

t=?+1s   state_sync chega → destrói novamente
         ❌ C1 some de novo
```

### 2.3 Bug no modo expandido

No modo expandido, a região (`#eb-regiao`) exibe `Centros: <span class="eb-c1">17</span>, 25, 9`. Porém o CSS `.eb-region .eb-c1` define `color: #000` (preto) sobre fundo verde (#00ff88) — **C1 fica invisível**.

---

## 3. BUGS IDENTIFICADOS

| ID | Severidade | Arquivo | Linhas | Título |
|:---|:----------:|:--------|:------:|:-------|
| BUG-FE-001 | 🔴 CRÍTICO | `content.js` | 799-802 | `handleStateSync()` destrói C1 span a cada heartbeat |
| BUG-FE-002 | 🟠 ALTO | `overlay.css` | 945-950 | `.eb-region .eb-c1` cor preta = invisível no fundo verde |
| BUG-FE-003 | 🟡 MÉDIO | `content.js` | 4 locais | Duplicação de código — centroDisplay construído inconsistentemente |

---

### BUG-FE-001 — Heartbeat destrói destaque C1 a cada 1s

**Arquivo:** `extension/content.js`  
**Linhas:** 799-802 (dentro de `handleStateSync()`)

**Código atual (BUGADO):**
```javascript
// Linha 799-802: centroDisplay sem eb-c1, e textContent destrói innerHTML
const centros = data.pending_prediction.centers || [data.pending_prediction.center || '--'];
const centroDisplay = centros.map(c => `[${c}]`).join(' ');
status.textContent = `${centroDisplay} ${data.gale_display || 'G1 0/0'}`;
status.className = `eb-status g${data.gale_level || 1}`;
```

**Problemas:**
1. `centros.map(c => \`[${c}]\`)` — **não inclui** `<span class="eb-c1">` no primeiro centro
2. `status.textContent` — **destrói** qualquer HTML interno (spans com eb-c1)
3. Roda a cada 1 segundo via heartbeat → C1 dourado dura no máximo ~1s

**Impacto:** O destaque C1 é destruído a cada heartbeat, tornando a feature inutilizável no modo minimizado.

---

### BUG-FE-002 — C1 invisível na região expandida

**Arquivo:** `extension/overlay.css`  
**Linhas:** 945-950

**Código atual (BUGADO):**
```css
.eb-region .eb-c1 {
  color: #000;           /* ❌ Preto no fundo verde = INVISÍVEL */
  font-weight: 900;
  text-decoration: underline;
  text-shadow: none;
}
```

**Contexto:** A `.eb-region` tem fundo `linear-gradient(135deg, #00ff88, #00cc6a)` (verde vibrante). Texto preto (#000) sobre verde é legível para texto normal, mas o C1 precisa de DESTAQUE — preto não se destaca.

**Impacto:** No modo expandido, C1 fica visualmente idêntico ao texto normal, anulando o propósito da feature.

---

### BUG-FE-003 — Duplicação de código centroDisplay

**Arquivo:** `extension/content.js`  
**4 locais com lógica duplicada:**

| # | Função | Linha | Usa eb-c1? | Usa innerHTML? |
|:-:|:-------|:-----:|:----------:|:--------------:|
| 1 | `updateOverlay()` (minimizado) | ~491 | ✅ Sim | ✅ Sim |
| 2 | `updateOverlay()` (região expandida) | ~468-473 | ✅ Sim | ✅ Sim |
| 3 | `toggleMinimize()` | ~377 | ✅ Sim | ✅ Sim |
| 4 | `handleStateSync()` | ~800 | ❌ **NÃO** | ❌ **NÃO** |

**Impacto:** Inconsistência (#4 sem eb-c1) causou BUG-FE-001. Código duplicado 4× aumenta risco de regressão futura. Viola princípio DRY (ISO 25010 §7 Manutenibilidade).

---

## 4. SOLUÇÃO PROPOSTA

### 4.1 Abordagem: Helper function DRY

Extrair uma função `buildCentroHTML(centros)` que encapsula a lógica de formatação com eb-c1. Usá-la nos 4 locais, eliminando duplicação e garantindo consistência.

```javascript
/**
 * Constrói HTML dos centros com destaque dourado no C1.
 * C1 é sempre o primeiro elemento do array.
 * @param {Array} centros - Array de números [C1, C2, C3]
 * @returns {string} HTML string com <span class="eb-c1"> no primeiro centro
 */
function buildCentroHTML(centros) {
  if (!centros || centros.length === 0) return '--';
  return centros.filter(c => c != null)
      .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
      .join(' ');
}
```

### 4.2 CSS: Visibilidade no modo expandido

```css
.eb-region .eb-c1 {
  color: #FFD700;                               /* Dourado — visível no verde */
  font-weight: 900;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);   /* Sombra para contraste */
}
```

---

## 5. TASKS

| ID | Descrição | Arquivo | Prioridade |
|:---|:----------|:--------|:----------:|
| T-FIX-01 | Criar helper `buildCentroHTML()` no topo de content.js | `content.js` | P0 |
| T-FIX-02 | Corrigir `handleStateSync()` — usar helper + innerHTML | `content.js:800` | P0 |
| T-FIX-03 | Refatorar `updateOverlay()` minimizado — usar helper | `content.js:491` | P1 |
| T-FIX-04 | Refatorar `toggleMinimize()` — usar helper | `content.js:377` | P1 |
| T-FIX-05 | Corrigir `.eb-region .eb-c1` CSS — dourado no verde | `overlay.css:945` | P0 |
| T-FIX-06 | Testes visuais — confirmar C1 persiste após heartbeat | Manual | P0 |
| T-ISO-01 | Documentar BUG-FE-001/002/003 no Manutenabilidade_iso.md | ISO doc | P2 |

### 5.1 Detalhamento

#### T-FIX-01 — Helper `buildCentroHTML()`

Inserir após a seção de variáveis globais (~linha 15):

```javascript
function buildCentroHTML(centros) {
  if (!centros || centros.length === 0) return '--';
  return centros.filter(c => c != null)
      .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
      .join(' ');
}
```

#### T-FIX-02 — Corrigir `handleStateSync()`

**Antes (linhas 799-802):**
```javascript
const centros = data.pending_prediction.centers || [data.pending_prediction.center || '--'];
const centroDisplay = centros.map(c => `[${c}]`).join(' ');
status.textContent = `${centroDisplay} ${data.gale_display || 'G1 0/0'}`;
```

**Depois:**
```javascript
const centros = data.pending_prediction.centers || [data.pending_prediction.center || '--'];
const centroDisplay = buildCentroHTML(centros);
status.innerHTML = `${centroDisplay} ${data.gale_display || 'G1 0/0'}`;
```

#### T-FIX-03 — Refatorar `updateOverlay()` minimizado

**Antes (~linha 491):**
```javascript
const centroDisplay = centros.filter(c => c != null)
    .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
    .join(' ') || '--';
```

**Depois:**
```javascript
const centroDisplay = buildCentroHTML(centros);
```

#### T-FIX-04 — Refatorar `toggleMinimize()`

**Antes (~linha 377):**
```javascript
const centroDisplay = centros.filter(c => c)
    .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
    .join(' ') || '--';
```

**Depois:**
```javascript
const centroDisplay = buildCentroHTML(centros);
```

#### T-FIX-05 — CSS região expandida

**Antes (overlay.css ~linha 945):**
```css
.eb-region .eb-c1 {
  color: #000;
  font-weight: 900;
  text-decoration: underline;
  text-shadow: none;
}
```

**Depois:**
```css
.eb-region .eb-c1 {
  color: #FFD700;
  font-weight: 900;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}
```

#### T-FIX-06 — Checklist de teste visual

| # | Cenário | Critério de aceitação |
|:-:|:--------|:---------------------|
| 1 | Overlay minimizado — sugestão chega | C1 dourado imediatamente, sem minimizar/restaurar |
| 2 | Overlay minimizado — aguardar 5 segundos | C1 dourado persiste após 5+ heartbeats |
| 3 | Overlay expandido — região APOSTAR | C1 dourado visível no fundo verde |
| 4 | Overlay expandido → minimizar → expandir | C1 dourado mantido em ambos modos |
| 5 | Dashboard — campo Centro | C1 em dourado+bold (CSS estático) |

#### T-ISO-01 — Documentação ISO

Registrar em `Manutenabilidade_iso.md` PARTE IV:

```markdown
| BUG-FE-001 | extension/content.js | ~~🔴 Crítico~~ ✅ CORRIGIDO (29/03) | handleStateSync destrói eb-c1 com textContent a cada heartbeat | 800 |
| BUG-FE-002 | extension/overlay.css | ~~🟠 Alto~~ ✅ CORRIGIDO (29/03) | .eb-region .eb-c1 cor preta invisível no fundo verde | 945 |
| BUG-FE-003 | extension/content.js | ~~🟡 Médio~~ ✅ CORRIGIDO (29/03) | Duplicação de centroDisplay em 4 locais — extraído helper DRY | 4 locais |
```

Registrar em PARTE III melhorias:
```markdown
| MEL-FE-001 | Manutenibilidade | ~~buildCentroHTML helper para DRY~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
```

---

## 6. GRAFO DE DEPENDÊNCIAS

```
T-FIX-01 (helper) ──┬──→ T-FIX-02 (handleStateSync)
                    ├──→ T-FIX-03 (updateOverlay)
                    └──→ T-FIX-04 (toggleMinimize)
                              │
T-FIX-05 (CSS) ──────────────┤
                              │
                              └──→ T-FIX-06 (teste visual) ──→ T-ISO-01 (docs)
```

---

## 7. IMPACTO ISO/IEC 25010

| Característica | Antes | Depois | Δ |
|:---------------|:-----:|:------:|:-:|
| Usabilidade | 8.2 | **8.3** | +0.1 (C1 funcional em todos os modos) |
| Manutenibilidade | 8.0 | **8.1** | +0.1 (DRY helper elimina duplicação) |
| Confiabilidade | 8.5 | **8.5** | 0 (sem impacto) |

---

> **Status:** 📋 Documento de estudo — aguardando aprovação para execução  
> **Próxima ação:** Aprovar → Executar T-FIX-01 a T-FIX-06 → Deploy → Validação

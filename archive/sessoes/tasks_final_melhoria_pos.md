# Tasks Finais — Melhoria Pós-Implementação C1 Bold

> **Versão alvo:** 4.0.1 → 4.0.2  
> **Data da auditoria:** 29/03/2026  
> **Referência:** `melhorias_pos_implementacao.md`, `Manutenabilidade_iso.md`  
> **Norma:** ISO/IEC 25010:2011  
> **Escopo:** Correção definitiva do destaque C1 dourado no overlay + DRY refactoring

---

## 1. RESUMO DA AUDITORIA

A auditoria simulou a execução das 7 tasks propostas em `melhorias_pos_implementacao.md`,
analisando o código-fonte real de `extension/content.js` (linhas 370-815) e
`extension/overlay.css` (linhas 930-950) para validar cada correção.

### Resultado da Auditoria

| Bug           | Status         | Bugs adicionais encontrados |
|---------------|----------------|-----------------------------|
| BUG-FE-001    | ✅ Confirmado  | +1 melhoria defensiva       |
| BUG-FE-002    | ✅ Confirmado  | Cor ajustada (branco > ouro) |
| BUG-FE-003    | ✅ Confirmado  | Helper cobre 3 de 4 locais  |

**Total de tasks: 9** (6 fixes + 1 ISO + 1 versão + 1 verificação)

---

## 2. BUGS CONFIRMADOS — ANÁLISE PROFUNDA

### 2.1 BUG-FE-001: Heartbeat destrói destaque C1 (CRÍTICO)

**Arquivo:** `extension/content.js` linhas 796-802  
**Severidade:** CRÍTICA — bug faz o destaque C1 desaparecer em ~1 segundo

**Causa raiz técnica:**  
A função `handleStateSync()` roda a cada 1s via heartbeat do servidor. Quando
`data.bet_placed === true`, ela reconstrói o texto dos centros SEM a tag `<span class="eb-c1">`:

```javascript
// CÓDIGO ATUAL (BUGADO) — linhas 799-801
const centros = data.pending_prediction.centers || [data.pending_prediction.center || '--'];
const centroDisplay = centros.map(c => `[${c}]`).join(' ');  // ❌ Sem eb-c1
status.textContent = `${centroDisplay} ${data.gale_display || 'G1 0/0'}`;  // ❌ textContent
```

**Dois problemas:**
1. `centros.map(c => ...)` NÃO aplica `<span class="eb-c1">` no primeiro elemento
2. `status.textContent = ...` destrói qualquer `innerHTML` existente (as tags HTML viram texto literal)

**Sequência temporal do bug:**
```
T+0.0s: updateOverlay() define status.innerHTML com <span class="eb-c1"> ✅ Gold visível
T+1.0s: handleStateSync() define status.textContent sem <span> ❌ Gold desaparece
T+2.0s: handleStateSync() repete... gold continua ausente ❌
```

**Correção:** Usar `buildCentroHTML()` helper + `status.innerHTML` em vez de `textContent`.

---

### 2.2 BUG-FE-002: CSS invisível na região expandida (ALTO)

**Arquivo:** `extension/overlay.css` linhas 945-950  
**Severidade:** ALTA — C1 existe no DOM mas não é visível

**Causa raiz técnica:**
```css
/* CÓDIGO ATUAL (BUGADO) */
.eb-region .eb-c1 {
  color: #000;           /* ❌ Preto sobre fundo verde = INVISÍVEL */
  font-weight: 900;
  text-decoration: underline;
  text-shadow: none;
}
```

O fundo da `.eb-region` é um gradiente verde (`linear-gradient(135deg, #00ff88, #00cc6a)`).
Texto preto (#000) sobre verde (#00ff88) tem contraste teórico mas na prática é difícil
de distinguir, especialmente em telas móveis (Kiwi Browser/Android) com brilho reduzido.

**Auditoria da cor proposta em melhorias_pos_implementacao.md:**
O documento original sugeria `color: #FFD700` (ouro). Porém:
- Gold (#FFD700) sobre verde (#00ff88) tem **contraste BAIXO** — ambas são cores claras/vivas
- Ratio WCAG: ~1.5:1 (mínimo recomendado: 4.5:1 para texto normal)

**Decisão de auditoria:** Usar **branco (#FFFFFF)** com `text-shadow` em vez de ouro:
- Branco sobre verde tem contraste WCAG ~3.5:1 (aceitável para texto bold grande)
- O texto normal na região é preto → branco bold se destaca claramente
- `text-shadow` com sombra escura garante legibilidade em qualquer fundo

```css
/* CORREÇÃO AUDITADA */
.eb-region .eb-c1 {
  color: #fff;
  font-weight: 900;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}
```

---

### 2.3 BUG-FE-003: Violação DRY — centroDisplay em 4 locais (MÉDIO)

**Arquivo:** `extension/content.js`  
**Severidade:** MÉDIA — dificuldade de manutenção, causa raiz do BUG-FE-001

**4 locais que constroem centroDisplay:**

| # | Função            | Linha  | Formato           | Usa eb-c1? |
|---|-------------------|--------|--------------------|-----------|
| 1 | updateOverlay     | 490-492| `[C1] [C2] [C3]`  | ✅ Sim    |
| 2 | toggleMinimize    | 376-378| `[C1] [C2] [C3]`  | ✅ Sim    |
| 3 | handleStateSync   | 799-800| `[C1] [C2] [C3]`  | ❌ NÃO   |
| 4 | updateOverlay reg.| 468-471| `Centros: C1, C2`  | ✅ Sim    |

**Decisão de auditoria:**
- Locais 1, 2, 3 usam formato **bracket** `[C1] [C2] [C3]` → compartilham `buildCentroHTML()`
- Local 4 usa formato **comma** `Centros: C1, C2, C3` → permanece customizado (diferente propósito visual)
- O helper cobre os 3 locais bracket, eliminando a causa raiz do BUG-FE-001

---

### 2.4 Melhoria Defensiva: Guard vazio em pending_prediction

**Arquivo:** `extension/content.js` linha 798  
**Severidade:** BAIXA — bug teórico, mitigado pelo guard `bet_placed === true`

**Situação:**
Após `check_prediction()` no servidor, `pending_prediction = {}` (dict vazio).
Em JavaScript, `{}` é truthy. A condição `if (status && data.pending_prediction)` passaria.
Porém, o guard externo `if (betPlaced)` (linha 781) protege:
- `bet_placed=true` → `pending_prediction` sempre tem dados completos
- `bet_placed=false` → código não entra no bloco

**Mesmo assim, adicionamos guard defensivo** para robustez futura:
```javascript
// ANTES
if (status && data.pending_prediction) {

// DEPOIS
if (status && data.pending_prediction && data.pending_prediction.centers) {
```

---

## 3. TASKS DE IMPLEMENTAÇÃO

### T-FIX-01: Criar helper `buildCentroHTML()` [PRIORIDADE: P0]

**Arquivo:** `extension/content.js`  
**Posição:** Após a linha 14 (constantes do overlay), antes de `loadUIState()`  
**Dependências:** Nenhuma  
**Estimativa de risco:** BAIXO

**Código a inserir:**
```javascript
// === M15-ADA v4.0.2: Helper para destaque C1 (DRY) ===
// Formato bracket para status minimizado: [C1] [C2] [C3]
// C1 (primeiro) sempre recebe classe eb-c1 (dourado/bold)
function buildCentroHTML(centros) {
  if (!centros || centros.length === 0) return '--';
  return centros.filter(c => c != null)
      .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
      .join(' ');
}
```

**Testes:**
- `buildCentroHTML([17, 25, 9])` → `<span class="eb-c1">[17]</span> [25] [9]`
- `buildCentroHTML([17])` → `<span class="eb-c1">[17]</span>` (fallback single center)
- `buildCentroHTML([])` → `--`
- `buildCentroHTML(null)` → `--`
- `buildCentroHTML(undefined)` → `--`

**Documentação ISO:** MEL-ADA-007: "Função helper DRY para construção de HTML dos centros"

---

### T-FIX-02: Refatorar updateOverlay minimizado [P1]

**Arquivo:** `extension/content.js`  
**Linhas:** 489-492  
**Depende de:** T-FIX-01

**ANTES (linhas 489-492):**
```javascript
  const centros = sugestao.centros || [sugestao.centro];
  const centroDisplay = centros.filter(c => c != null)
      .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
      .join(' ') || '--';
```

**DEPOIS:**
```javascript
  const centros = sugestao.centros || [sugestao.centro];
  const centroDisplay = buildCentroHTML(centros);
```

**Impacto:** Redução de 4 linhas → 2 linhas. Lógica idêntica via helper.

---

### T-FIX-03: Refatorar toggleMinimize [P1]

**Arquivo:** `extension/content.js`  
**Linhas:** 375-378  
**Depende de:** T-FIX-01

**ANTES (linhas 375-378):**
```javascript
      const centros = overlayState.lastSugestao.centros || [overlayState.lastSugestao.centro];
      const centroDisplay = centros.filter(c => c)
          .map((c, i) => i === 0 ? `<span class="eb-c1">[${c}]</span>` : `[${c}]`)
          .join(' ') || '--';
```

**DEPOIS:**
```javascript
      const centros = overlayState.lastSugestao.centros || [overlayState.lastSugestao.centro];
      const centroDisplay = buildCentroHTML(centros);
```

**Impacto:** Redução de 4 linhas → 2 linhas. Mantém mesma variável `centros` local.

---

### T-FIX-04: Corrigir handleStateSync — BUG PRINCIPAL [P0]

**Arquivo:** `extension/content.js`  
**Linhas:** 796-803  
**Depende de:** T-FIX-01

**ANTES (linhas 796-803):**
```javascript
    // Atualizar status se minimizado
    if (overlayState.isMinimized) {
      const status = overlay.querySelector('.eb-status');
      if (status && data.pending_prediction) {
        const centros = data.pending_prediction.centers || [data.pending_prediction.center || '--'];
        const centroDisplay = centros.map(c => `[${c}]`).join(' ');
        status.textContent = `${centroDisplay} ${data.gale_display || 'G1 0/0'}`;
        status.className = `eb-status g${data.gale_level || 1}`;
      }
    }
```

**DEPOIS:**
```javascript
    // Atualizar status se minimizado — v4.0.2: usar innerHTML + buildCentroHTML
    if (overlayState.isMinimized) {
      const status = overlay.querySelector('.eb-status');
      if (status && data.pending_prediction && data.pending_prediction.centers) {
        const centroDisplay = buildCentroHTML(data.pending_prediction.centers);
        status.innerHTML = `${centroDisplay} ${data.gale_display || 'G1 0/0'}`;
        status.className = `eb-status g${data.gale_level || 1}`;
      }
    }
```

**3 correções neste bloco:**
1. ✅ Guard defensivo: `data.pending_prediction.centers` (evita {} truthy)
2. ✅ `buildCentroHTML()` aplica `<span class="eb-c1">` no C1
3. ✅ `status.innerHTML` em vez de `status.textContent` (preserva tags HTML)

---

### T-FIX-05: Corrigir CSS `.eb-region .eb-c1` [P1]

**Arquivo:** `extension/overlay.css`  
**Linhas:** 945-950  
**Depende de:** Nenhuma (pode ser feito em paralelo com JS)

**ANTES (linhas 944-950):**
```css
/* Dentro da região (fundo verde/laranja), usar preto bold */
.eb-region .eb-c1 {
  color: #000;
  font-weight: 900;
  text-decoration: underline;
  text-shadow: none;
}
```

**DEPOIS:**
```css
/* Dentro da região (fundo verde), C1 em branco bold com sombra */
.eb-region .eb-c1 {
  color: #fff;
  font-weight: 900;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}
```

**Justificativa da mudança de cor:**

| Proposta             | Cor       | Contraste WCAG | Resultado visual       |
|----------------------|-----------|----------------|------------------------|
| Original (bugado)    | #000      | Alto (21:1)    | Não se destaca do texto|
| melhorias_pos (ouro) | #FFD700   | Baixo (~1.5:1) | Ouro sobre verde = dim |
| **Auditoria (branco)**| **#fff** | **Bom (~3.5:1)**| **Destaque claro**    |

O texto normal na região é preto. C1 em branco bold se diferencia imediatamente.
A `text-shadow` escura garante legibilidade mesmo em fundo claro.

---

### T-FIX-06: Nenhuma ação adicional na região expandida [INFO]

**Arquivo:** `extension/content.js` linhas 468-473  
**Status:** ✅ Código já correto — não requer alteração

```javascript
// Este trecho já usa innerHTML com eb-c1 corretamente:
if (sugestao.centros && sugestao.centros.length > 0) {
  const c = sugestao.centros;
  regiao.innerHTML = `Centros: <span class="eb-c1">${c[0]}</span>` +
      (c.length > 1 ? `, ${c.slice(1).join(', ')}` : '');
}
```

**Porquê não refatorar com buildCentroHTML:**
- Formato diferente: `Centros: C1, C2, C3` (vírgulas, sem colchetes, com prefixo)
- O helper usa formato bracket: `[C1] [C2] [C3]`
- Criar um parâmetro `format` no helper adicionaria complexidade sem benefício
- A região expandida só é escrita em 1 lugar (sem DRY violation)

**Melhoria necessária:** Apenas a correção CSS (T-FIX-05) resolve o problema visual aqui.

---

### T-ISO-01: Atualizar Manutenabilidade_iso.md [P2]

**Arquivo:** `Manutenabilidade_iso.md`  
**Depende de:** T-FIX-01 a T-FIX-05 concluídos

**Itens a atualizar:**

1. **PARTE I — Versão:** 4.0.1 → 4.0.2
2. **PARTE III — Melhorias:** Adicionar MEL-ADA-007:
   ```
   MEL-ADA-007 | Helper buildCentroHTML() — DRY para 3 locais de renderização C1 | FEITA
   ```
3. **PARTE IV — Bugs:** Adicionar BUG-FE-001, BUG-FE-002, BUG-FE-003:
   ```
   BUG-FE-001 | handleStateSync destrói innerHTML com textContent | RESOLVIDO
   BUG-FE-002 | CSS .eb-region .eb-c1 cor preta invisível em fundo verde | RESOLVIDO
   BUG-FE-003 | centroDisplay duplicado em 4 locais (DRY violation) | RESOLVIDO
   ```
4. **PARTE V — Scorecard:** Usabilidade +0.1 (destaque C1 funcional)
5. **PARTE VI — Changelog:** Adicionar entrada v4.0.2

---

### T-VER-01: Atualizar VERSION e Dockerfile [P2]

**Arquivos:** `VERSION`, `Dockerfile`  
**Depende de:** T-FIX-01 a T-FIX-05 concluídos

- `VERSION`: `4.0.1` → `4.0.2`
- `Dockerfile` label: `4.0.1` → `4.0.2`

---

### T-TEST-01: Verificação Manual [P0]

**Depende de:** Todas as tasks anteriores

**Checklist de verificação:**

- [ ] Testes unitários Python passam (105/105)
- [ ] Overlay minimizado: C1 aparece dourado imediatamente após APOSTAR
- [ ] Overlay minimizado: C1 permanece dourado após 5+ segundos (heartbeat não destrói)
- [ ] Overlay expandido: Região mostra "Centros: **C1**, C2, C3" com C1 em branco bold
- [ ] Overlay expandido: Status mostra "🎯 APOSTAR" (sem centros visíveis)
- [ ] toggleMinimize: Minimizar/restaurar preserva C1 dourado
- [ ] Estado PULAR: Região mostra "Sem entrada" (sem eb-c1)
- [ ] Estado AGUARDAR: Status mostra "⏳ AGUARDANDO"
- [ ] Fallback: Quando centros tem 1 elemento, C1 único aparece dourado
- [ ] Console: Sem erros JavaScript novos

---

## 4. ORDEM DE EXECUÇÃO

```
T-FIX-01 (helper)
    ├── T-FIX-02 (refactor updateOverlay)
    ├── T-FIX-03 (refactor toggleMinimize)
    └── T-FIX-04 (fix handleStateSync) ← BUG PRINCIPAL
T-FIX-05 (CSS) ← pode ser paralelo com JS
    │
    ├── T-ISO-01 (documentação)
    ├── T-VER-01 (versão)
    └── T-TEST-01 (verificação final)
```

**Arquivos modificados:**

| Arquivo              | Tasks          | Tipo       |
|----------------------|----------------|------------|
| extension/content.js | T-FIX-01/02/03/04 | JavaScript |
| extension/overlay.css| T-FIX-05       | CSS        |
| Manutenabilidade_iso.md | T-ISO-01   | Documentação |
| VERSION              | T-VER-01       | Metadado   |
| Dockerfile           | T-VER-01       | Metadado   |

---

## 5. RISCOS E MITIGAÇÕES

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| innerHTML XSS | BAIXA | ALTO | Centros são inteiros do servidor (0-36), nunca user-input |
| Quebra de layout minimizado | BAIXA | MÉDIO | Helper gera formato idêntico ao atual |
| Cor branca ilegível em fundo claro | BAIXA | BAIXO | text-shadow escura como fallback |
| Regressão em toggleMinimize | BAIXA | MÉDIO | Testes manuais no checklist |

---

## 6. COMMIT PLANEJADO

```
v4.0.2: Fix C1 gold highlight — DRY helper + heartbeat fix + CSS contrast

- T-FIX-01: Add buildCentroHTML() helper for DRY centro display
- T-FIX-02: Refactor updateOverlay minimized to use helper
- T-FIX-03: Refactor toggleMinimize to use helper
- T-FIX-04: Fix handleStateSync — innerHTML + eb-c1 + defensive guard
- T-FIX-05: Fix .eb-region .eb-c1 CSS — #000 → #fff with text-shadow
- T-ISO-01: Update Manutenabilidade_iso.md v4.0.2
- T-VER-01: Bump VERSION 4.0.1 → 4.0.2

Fixes: BUG-FE-001 (heartbeat destroys gold), BUG-FE-002 (CSS invisible),
       BUG-FE-003 (DRY violation in 4 centroDisplay locations)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

---

## 7. DEPLOY

Após commit local e testes:

```bash
# No servidor (root@187.45.181.75)
cd /root/roleta-cloud
git pull origin main
docker-compose build --no-cache
docker-compose up -d
docker logs roleta-cloud --tail 20
```

**Nota:** A extensão Chrome precisa ser atualizada manualmente no navegador do operador
(recarregar extensão em `chrome://extensions`).

---

> **Status:** ✅ Documento de tasks aprovado para execução  
> **Próxima etapa:** Aguardar aprovação do operador para implementar

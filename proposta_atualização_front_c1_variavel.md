# 🖥️ Proposta de Atualização do Front — C1/C2 Variável (14#) + Block-Gale

> **Escopo:** revisão de UX e fluxo de dados do **front-end (Glass Box Dashboard)** e da
> **extensão (Escuta Beat)** após o go-live da aposta de **14 números** (`C_escolhido` móvel + `C3`
> fixo) com staking `block_gale`. Verifica o que a proposta `implantação_C1_variavel_junho.md`
> entregou no **backend** (✅ no ar) versus o que o **front ainda mostra** (⚠️ defasado), com teste
> de fluxo de dados, gaps catalogados e plano de correção priorizado.
>
> **Data:** 17/06/2026 · **HEAD:** `de095d0` · **Grafo:** `graphify-out/graph.json` (fresco, mesmo commit).
> **Método:** RADAR de MCPs → leitura de proposta → análise estática front+back → 2 subagents
> (extensão / data-flow) → verificação por teste executável (`523/523` suíte; `10/10` wiring) →
> sequential-thinking.

---

## 1. Sumário executivo

O **backend está correto e consistente** com a nova lógica: aposta de 14 números reais, validação
red/green contra esses 14, stake `block_gale` e três campos novos (`c_selection`, `block_gale`,
`bet_gate`) enviados ao front. **O problema está no front.** O Glass Box e a Escuta Beat ainda
operam, em pontos-chave, com o **contrato antigo** (3 centros, martingale legado, valor `R$17`
hardcoded) e **descartam** a informação nova que o servidor já envia.

### Veredito das 3 verificações solicitadas

| # | Pergunta do operador | Backend | Front (Glass Box) | Extensão (Escuta Beat) |
|:-:|---|:---:|:---:|:---:|
| **Q1** | Após a região de 14#, o próximo resultado valida red/green respeitando essa região? | ✅ **Sim** (valida contra os 14# reais) | ⚠️ Dado correto, mas **sem veredito GREEN/RED por aposta** no card | ❌ Não marca acerto/erro da aposta |
| **Q2** | Mostra os **2 centros** novos (C_escolhido + C3) em vez de 3? | Envia 3 (legado) **+** o par real em `c_selection.pair` | ❌ Mostra **1** centro (`result.centro`) | ❌ Mostra **3** (`sugestao.centros`) |
| **Q3** | O valor apostado exibido corresponde ao backend? | ✅ `aposta = effective_bet` (14u) | ❌ Usa `martingale.current_bet` **legado** + fallback **R$17** | ✅ Usa `sugestao.aposta` (correto) |

**Conclusão:** nenhuma mudança é necessária no cálculo do backend. As correções são **no front e em
2 pontos de “plumbing” do servidor** (propagar os campos novos para os canais `trace`/`state_sync` e
tratar `block_gale` no heartbeat). Esforço P0 estimado: baixo (~poucas linhas por arquivo).

---

## 2. Arquitetura do fluxo de dados (como é hoje)

```
┌─────────────────┐   sugestao    ┌──────────────────────────────┐
│ Extensão        │◄──────────────│  Servidor (message_handler)  │
│ "Escuta Beat"   │   (WS)        │  • _engine_apply_selection → result.numbers = 14#
│ content.js +    │               │  • _engine_apply_stake → block_gale (effective_bet)
│ popup.js        │               │  • _engine_overlay_fields → c_selection/block_gale/bet_gate
└─────────────────┘               │  • check_prediction → hit = nº ∈ numbers(14#)
                                   └───────────────┬──────────────┘
   ┌───────────────────────────────────────────────┼───────────────────────────┐
   │ 3 CANAIS WEBSOCKET                              │                           │
   │  (1) "sugestao"  → tem campos novos ✅          │ (2) "trace"  ← card Result │
   │  (2) "trace"     → SEM campos novos ❌          │ (3) "state_sync" 1s        │
   │  (3) "state_sync"→ SEM campos novos ❌          ▼                           │
   │                                   ┌──────────────────────────────┐         │
   │                                   │  Glass Box Dashboard          │         │
   │                                   │  frontend/app.js + index.html │         │
   │                                   │  • handleSuggestion → IGNORA  │◄────────┘
   │                                   │  • card Resultado ← "trace"   │
   │                                   │  • valor R$ ← martingale legado
   └───────────────────────────────────└──────────────────────────────┘
```

**Quem consome o quê:**

| Canal WS | Origem | Consumidor | Campos novos? |
|---|---|---|:---:|
| `sugestao` | `message_handler.py:904-942` | **Extensão** (overlay) e `handleSuggestion` (dashboard, que ignora) | ✅ presentes (`update(_engine_overlay_fields())` :940) |
| `trace` | `message_handler.py:948-983` | **Glass Box** card Resultado / performance / trace | ❌ ausentes |
| `state_sync` (1s) | `websocket.py:382-403` | **Glass Box** martingale/performance/window_history; **Extensão** sync `#eb-aposta` | ❌ ausentes |

> **Achado estrutural-chave:** `_engine_overlay_fields()` só é injetado no `sugestao` (`:940`).
> O `trace` e o `state_sync` — que são exatamente os canais que o **Glass Box** consome para
> renderizar — **nunca recebem** `c_selection`/`block_gale`/`bet_gate`. E o único canal que os tem
> (`sugestao`) é processado por `handleSuggestion()`, que **descarta** o conteúdo.

---

## 3. Contrato de payload atual (campos e consumo)

### 3.1 `sugestao` — `message_handler.py:904-936` (+ `:940`)

| Campo | Valor (var_c1c2_c3 ON) | Tipo | Consumo no front |
|---|---|---|---|
| `numeros` | **14 reais** (`final_numbers`) | legado-atualizado | Extensão: não lista; Dashboard: ignora (chega via `trace`) |
| `centro` | 1 centro principal SDA17 | legado | Dashboard card (via `trace`) |
| `centros` | `[C1,C2,C3]` = **3 sempre** | legado | Extensão renderiza os 3 |
| `aposta` | `effective_bet` = **14u** | legado-atualizado | Extensão ✅ (`#eb-aposta`) |
| `aposta_base` | `base_unit×N` = 14 | legado-atualizado | — |
| `stake_mode` | `block_gale` | legado-atualizado | — |
| `gale_level` | `mg.level` (**MartingaleState legado**) | legado | Extensão (`gale_display`) |
| `c_selection` | `{chosen, pair, rule, n}` | **NOVO** | ❌ ninguém |
| `block_gale` | `{active, cw{level,cap,block}, ccw{…}}` | **NOVO** | ❌ ninguém |
| `bet_gate` | `{only_after_green, gated}` | **NOVO** | ❌ ninguém |

### 3.2 `trace` — `message_handler.py:948-982` (alimenta o card do Dashboard)

`result.centro`, `result.centros` (3), `result.numeros` (14), `result.score`, `performance`,
`martingale_cw/ccw` (**legado**), `state.timeline_*`. **Sem** `c_selection`/`block_gale`/`bet_gate`.

### 3.3 `state_sync` (heartbeat 1s) — `websocket.py:382-403`

`gale_level`, `aposta` (**só corrige p/ flat/kelly**), `performance`, `martingale_cw/ccw`
(**legado**), `window_history`, `pending_prediction`. **Sem** campos novos.

---

## 4. Diagnóstico das 3 verificações (com evidência)

### Q1 — Red/Green respeita os 14#? ✅ no dado, ⚠️ na UX

**Cadeia verificada (backend correto):**
1. `_engine_apply_selection(result)` substitui a cobertura: `result.numbers = list(sel.numbers)`
   → 14# — `message_handler.py:564` chama; `:110` substitui.
2. `final_numbers = list(result.numbers or [])` — `message_handler.py:569`.
3. `store_prediction(result.numbers, …)` grava `pending["numbers"]` com os 14# —
   `message_handler.py:601-602` → `game.py:598-599`.
4. `check_prediction(actual)` → **`hit = actual_number in numbers`** — `game.py:419`.
5. `performance_sda17_*` **e** `performance_bet_*` recebem o **mesmo** `hit` —
   `game.py:436/440` e `:477-481`. `get_performance_stats()` (`:902-928`) devolve ambos ao front.

> **Logo, a validação red/green respeita a região de 14 números.** Os quadrados “💰 Performance
> Apostas (Martingale)” e “📊 Performance SDA17” no dashboard refletem o hit real dos 14#.

**Lacuna de UX:** o **card “👉 Resultado”** mostra `Centro`, `Score` e `Região` (lista de 14
números) — `app.js:264-272` / `index.html:67-75` — mas **não exibe um veredito GREEN/RED do spin
seguinte por aposta**. O operador vê os números, não um “✅ GREEN / ❌ RED” explícito da última
aposta. A informação existe (`performance.bet`, `window_history`), mas não há marcação clara no card.

### Q2 — 3 centros vs 2 centros novos ❌

**Confirmado pelo teste de fluxo executado (motores reais):**

```
chosen        : C2
pair          : C2+C3
numbers (real): [0,3,5,8,10,12,15,16,23,24,26,32,33,35] -> N = 14
centers(2 ap.): [5, 26]        ← apenas C2 e C3 são apostados
```

- O backend mantém `centros = [C1,C2,C3]` (**3**) por **continuidade de DNA/atribuição**
  (`dist_c1/c2/c3` alinhados) — decisão deliberada da proposta (§5 “Por que centers continua 3”).
- O **par real apostado** (2 centros) está em **`c_selection.pair`** (`"C2+C3"`) e equivale a
  `[centro_do_chosen, C3]` — `message_handler.py:208-210`.
- **Glass Box:** `updateResultDisplay` usa só `result.centro` (1) e nunca `result.centros`
  — `app.js:269`. Não usa `c_selection`.
- **Extensão:** renderiza `sugestao.centros` (os **3**) — `content.js:476-479`. Não usa `c_selection`.

> **Nenhum dos dois mostra os 2 centros corretos.** A informação para corrigir já trafega
> (`c_selection.pair`), apenas não é consumida.

### Q3 — Valor apostado == backend? ❌ no Dashboard, ✅ na Extensão

- **Extensão:** `R$ <#eb-aposta>` ← `sugestao.aposta` (= `effective_bet` = 14u) — `content.js:527`. ✅
- **Glass Box:** `updateMartingale()` faz **`const bet = mg.current_bet ?? 17`** e escreve
  `R$${bet}` — `app.js:316,322,328`. A fonte é `martingale_cw/ccw.current_bet` do **MartingaleState
  legado**, **não** `sugestao.aposta`/`state_sync.aposta`. O HTML nasce com **`R$17`** hardcoded
  (`index.html:135,140`).
- **Heartbeat:** `websocket.py:371-380` só recalcula `aposta` para `flat`/`kelly`; com
  **`block_gale`** cai no `else → _hb_aposta = mg.current_bet` (legado). Ou seja, mesmo o campo
  `state_sync.aposta` está errado para o modo que está no ar.

> O stake **real** é `base_unit × 14 × MULT[level]` (cap=1 ⇒ 14u). O Dashboard exibe o valor do
> martingale legado (tipicamente `R$17`), **divergente** do que é efetivamente apostado.

---

## 5. Gaps catalogados

| ID | Onde | Gap | Severidade |
|---|---|---|:---:|
| **BE-1** | `message_handler.py:948` (`trace`) e `websocket.py:382` (`state_sync`) | Campos novos não propagados aos canais que o Dashboard consome | 🔴 Alta |
| **BE-2** | `websocket.py:371` | Heartbeat `aposta` ignora `block_gale` (mostra `mg.current_bet`) | 🔴 Alta |
| **FE-1** | `app.js:316,322,328` + `index.html:135,140` | Valor R$ vem do martingale legado + fallback `17` | 🔴 Alta |
| **FE-2** | `app.js:264-272` | Card não mostra o **par** (`c_selection.pair`) nem os 2 centros apostados | 🟠 Média |
| **FE-3** | `app.js:264-272` | Sem veredito **GREEN/RED por aposta** no card | 🟠 Média |
| **FE-4** | `app.js` / `index.html` | `block_gale` (bloco x/4, nível, gated) e `bet_gate` invisíveis, apesar de serem o staking **real** | 🟠 Média |
| **FE-5** | `app.js:234-242` | `handleSuggestion` descarta todo o payload rico | 🟡 Baixa |
| **EXT-1** | `content.js:476-479` | Mostra 3 centros; deveria destacar os 2 via `c_selection.pair` | 🟠 Média |
| **EXT-2** | `popup.js`/`content.js` | Não marca acerto/erro da **aposta** (só cor do número sorteado) | 🟡 Baixa |
| **EXT-3** | `content.js:527`, `app.js:316` | Fallback de valor `17` em dois lugares (deveria ser `--`/sem-aposta) | 🟡 Baixa |
| **ARCH-1** | `state/game.py` (Martingale) vs `state/block_gale.py` | **Dois sistemas de gale** coexistem; o exibido (legado) ≠ o real (block_gale). Mascarado por `cap=1` | 🟠 Média |

---

## 6. Proposta de correção (priorizada)

### P0 — Destravar e corrigir divergência de valor (baixo esforço, alto impacto)

**BE-1 · Propagar campos novos para `trace` e `state_sync`.**
```python
# server/message_handler.py — no dict trace_broadcast (após "result": {...})
trace_broadcast["result"].update(self._engine_overlay_fields())   # c_selection/block_gale/bet_gate
# server/websocket.py — no state_sync["data"] (precisa de handle ao message_handler/game_state)
state_sync["data"].update(handler._engine_overlay_fields())       # mesma fonte
```

**BE-2 · Heartbeat reconhece `block_gale`.**
```python
# server/websocket.py:371  (incluir block_gale no ramo que mostra stake efetivo)
if _hb_mode in ("flat", "kelly", "block_gale"):
    _hb_nums = game_state.pending_prediction.get("numbers", []) or []
    _hb_info = game_state.get_effective_bet(game_state.target_direction, strategy,
                                            n_numbers=len(_hb_nums) if _hb_nums else 14)
    _hb_aposta, _hb_mode = _hb_info["effective_bet"], _hb_info["mode"]
```

**FE-1 · Dashboard usa o stake real, sem fallback mágico.**
```javascript
// frontend/app.js — handleStateSync(): preferir aposta do servidor
if (data.aposta !== undefined) setBetValue(data.aposta);      // novo: fonte única
// updateMartingale(): trocar  const bet = mg.current_bet ?? 17;  por:
const bet = (mg.current_bet ?? data?.aposta ?? '--');         // nunca 17 hardcoded
// index.html: trocar os defaults "R$17" por "R$--"
```

### P1 — UX da nova lógica (2 centros, par, veredito)

**FE-2 / EXT-1 · Mostrar os 2 centros apostados + badge do par.**
- Derivar do payload: `chosen = c_selection.chosen` (`"C1"|"C2"`); `betCenters = [centros[idx(chosen)], centros[2]]`.
- Dashboard: novo campo no card “Par: **C2+C3**” e destacar `betCenters`; esmaecer o centro não-escolhido.
- Extensão (`content.js`): usar `c_selection.pair` para o badge e `buildCentroHTML(betCenters)` (já existe helper) em vez dos 3.

**FE-3 / EXT-2 · Veredito GREEN/RED por aposta.**
- O `last_number` do spin seguinte ∈ `numeros` do `pending` anterior ⇒ GREEN; senão RED.
- Dashboard: pintar o card e adicionar selo “✅ GREEN / ❌ RED (último: N em C2+C3)”.
- Extensão: realçar o número sorteado se ∈ centros apostados.

### P2 — Consistência e observabilidade

**FE-4 · Painel Block-Gale real** (bloco `x/4`, nível, `cap`, `gated`, `only_after_green`) —
substitui/coexiste com o card de martingale legado, deixando claro qual é o staking no ar.

**ARCH-1 · Fonte única de staking exibido.** Hoje o dashboard mostra `martingale_cw/ccw`
(MartingaleState) e `window_history` (gale_windows), enquanto o staking executado é `BlockGaleEngine`.
Com `cap=1` ambos ficam em G1 e a divergência fica **mascarada**; se algum dia `GALE_CAP>1`, o
dashboard passará a **mentir** o nível. Unificar a leitura para o `block_gale` quando
`stake_mode == "block_gale"`.

---

## 7. Estrutura: o que **deveria** ter × o que **tem hoje**

| Componente | Proposta (nova lógica) | Hoje |
|---|---|---|
| Centros exibidos | **2** apostados (C_escolhido + C3) + 3º esmaecido p/ contexto | Dashboard: 1 · Extensão: 3 |
| Indicador de par | Badge `C1+C3` / `C2+C3` (de `c_selection.pair`) | ausente |
| Números | 14 reais, com destaque do número sorteado | 14 listados (Dashboard) · não lista (Extensão) |
| Valor apostado | `effective_bet` (block_gale) em fonte única | Extensão ✅ · Dashboard usa legado/`R$17` |
| Veredito red/green | Selo por aposta (GREEN/RED) + histórico | só squares de performance / cores de número |
| Staking exibido | Block-Gale (bloco x/4, nível, cap, gate) | Martingale legado (G1 0/0, `window_history`) |
| Campos novos | consumidos nos 3 canais | enviados só no `sugestao`, ignorados |

---

## 8. Insights estruturais gerais (além do escopo imediato)

1. **Contrato sem teste de contrato.** Não há teste que valide as chaves de `sugestao`/`trace`/
   `state_sync`. Um drift (renomear/remover chave) quebra o front silenciosamente. → adicionar
   `tests/test_ws_contract.py` afirmando presença/tipos das chaves e a paridade entre os 3 canais.
2. **Dois parsers do mesmo payload, com regras divergentes** (Dashboard usa martingale legado;
   Extensão usa `sugestao.aposta`). → extrair um módulo JS compartilhado de normalização do payload.
3. **`message_handler.py` 56KB / +200 LOC** (gap D.1 já registrado na proposta). Extrair
   `server/engines_wiring.py` (os 6 helpers `_engine_*`) reduz risco ao mexer no front-plumbing.
4. **Cache-busting do front.** `index.html` referencia `app.js?v=4.3.2` manualmente; ao publicar as
   correções, bump obrigatório (ex. `?v=4.4.x`) — caso contrário o navegador serve o JS antigo.
5. **Fonte única do staking (ARCH-1)** é o débito mais perigoso: hoje benigno por `cap=1`, vira bug
   de exibição assim que o teto do gale subir (opt-in já previsto na proposta).

---

## 9. Plano de implementação (fases) + checklist de verificação

**Fase 1 (P0):** BE-1, BE-2, FE-1 → o Dashboard passa a exibir o valor real e recebe os campos novos.
**Fase 2 (P1):** FE-2/EXT-1 (2 centros + par), FE-3/EXT-2 (veredito red/green).
**Fase 3 (P2):** FE-4 (painel block-gale), ARCH-1 (fonte única), teste de contrato.

**Checklist de aceite:**
- [x] Com `SDA_BET_PAIR=var_c1c2_c3`, o Dashboard mostra o **par** (`C1+C3`/`C2+C3`) — linha "Par" no card.
- [x] Valor R$ exibido vem de `state_sync.aposta` (sem `R$17` hardcoded; default `R$--`).
- [x] Selo GREEN/RED aparece no card (de `ultimo_acerto`, coerente com `numero ∈ 14#`).
- [x] `c_selection`/`block_gale`/`bet_gate`/`ultimo_acerto` chegam ao Dashboard via `trace` **e** `state_sync`.
- [ ] (follow-up) Extensão destaca o número sorteado quando ∈ centros apostados.
- [x] `app.js?v=4.4.0` bumpado; `tests/test_ws_overlay_contract.py` verde; suíte completa **529 passed**.

---

## 10. Auditoria de implantação (17/06, tarde) — bugs nos snippets P0 + implementação

Antes de implementar, os snippets P0 da §6 foram **auditados contra o código real**. Três eram
esboços com bugs que, se aplicados ao pé da letra, **não corrigiriam** o problema (ou nem compilariam):

| Bug | Snippet original (§6) | Por que falha (evidência) | Correção implementada |
|---|---|---|---|
| **AUDIT-1** | `state_sync["data"].update(handler._engine_overlay_fields())` | `broadcast_heartbeat()` (`websocket.py:344`) é **função global** — não há `handler`/`self` no escopo (só `game_state`, `strategy`, `db_service`) | Fonte única **`GameState.engine_overlay_fields()`** derivada do estado persistente (sem handler) |
| **AUDIT-2** | `if _hb_mode in ("flat","kelly","block_gale"): … get_effective_bet(…)` | `get_effective_bet` (`game.py:1058-1067`) só desvia `flat`/`kelly`; `block_gale` cai no **fallback gale legado** → `mg.current_bet` (o **mesmo valor errado**) — *falso fix* | Ramo próprio `elif "block_gale"` usando **`block_gale_engine.stake(dir, N)`** = `base_unit×N×MULT[level]` |
| **AUDIT-3** | `const bet = mg.current_bet ?? data?.aposta` / `setBetValue(...)` | `data` **não está no escopo** de `updateMartingale(direction, mg)` (`app.js`); `setBetValue` inexistente | `updateBlockGale(bg, aposta, targetDir)` usa `data.aposta` no `handleStateSync`; `updateMartingale` perde só o `?? 17` |

**Decisão de arquitetura (resolve AUDIT-1 + ARCH-1):** uma **fonte única**
`GameState.engine_overlay_fields()` (`state/game.py`) deriva `c_selection`/`block_gale`/`bet_gate` +
`ultimo_acerto` do **estado persistente** (engine sempre instanciado, `pending.cs_chosen`,
`last_hit_attribution`). É consumida por `trace` (`message_handler.py`) e `state_sync`
(`websocket.py`) — **sem tocar o `sugestao`** (que a extensão já consome corretamente).

### Implementado (segundo `Manutenabilidade_iso.md`)

- **Backend** (aditivo, defensivo, **flags-OFF byte-idêntico** — Obrigação #9):
  - `state/game.py`: `GameState.engine_overlay_fields()` + import de `BLOCK_SIZE`.
  - `server/message_handler.py`: `trace_broadcast.update(...)` em `try/except` (Obrigação #7 cumprida — `lint_silent_except.py --update`, baseline 25→26).
  - `server/websocket.py`: ramo `block_gale` no heartbeat (**stake real**) + `state_sync.data.update(...)` sob `state_lock`.
- **Frontend** (`frontend/`): `updateBlockGale`/`updateCSelection`/`updateVerdict`; `handleStateSync`/`handleTrace` consomem os campos novos; `updateMartingale` sem `?? 17`; HTML com linha **Par** + **selo veredito** + defaults `R$--`; CSS `.result-verdict.green/.red`; `app.js?v=4.4.0`.
- **Testes:** `tests/test_ws_overlay_contract.py` (6 casos: overlay always-on, c_selection do pending, ultimo_acerto green/red, JSON-serializável, **stake real ≠ current_bet legado**, escala por nível). Suíte completa **529 passed, 9 skipped, 1 xfailed**.

**Fora desta rodada (follow-up):** extensão (`EXT-1/2`) — `extension/*` está com working tree sujo
(trabalho em progresso do operador), evitado para não colidir; extração `engines_wiring.py`
(Obrigação #8). Conformidade detalhada no ADENDO de `Manutenabilidade_iso.md`.

---

## 11. Auditoria pós-implantação (17/06, fim de tarde) — bugs corrigidos + deploy

Revisão da própria implementação da §10 (code-review + verificação de deploy). Achou **2 bugs no
código novo** e **1 gap crítico de deploy**, todos corrigidos.

### 11.1 Bugs no código (corrigidos)

| ID | Severidade | Bug | Evidência | Correção |
|---|:---:|---|---|---|
| **BUG-A** | 🟠 Média | `GameState.engine_overlay_fields()` **sempre** emitia `block_gale` (engine sempre instanciado). No front, `if (data.block_gale) {…} else {martingale legado}` → o `else` **nunca** rodava. Em rollback para `gale`/`flat`/`kelly`, o dashboard mostraria o bloco parado (G1 0/4) em vez do martingale real | `state/game.py:942` (`if eng is not None` sempre verdadeiro); `frontend/app.js` handlers | Campo **`block_gale.active`** = `staking_mode()=="block_gale"`; front passa a checar `data.block_gale && data.block_gale.active` |
| **BUG-B** | 🟠 Média | `ultimo_acerto.numero` usava `self.last_number` (spin atual) enquanto `slot` vinha de `last_hit_attribution` — que **não** é atualizado em spin sem predição (`check_prediction` retorna `None` antes de setar). Resultado: número novo + slot/veredito antigos (incoerentes) | `state/game.py:409-410` (retorno precoce) vs `:963` (last_number) | `_attribute_hit_region` passa a carregar **`numero=actual_number`**; o overlay usa `attr["numero"]` (número e veredito do **mesmo** spin) |

Cobertos por 3 testes novos em `tests/test_ws_overlay_contract.py` (`active` reflete o modo; `numero`
vem da atribuição; `_attribute_hit_region` carrega `numero`). Suíte: **532 passed**.

### 11.2 🔴 DEPLOY-1 (CRÍTICO) — frontend não chega em produção

**Sintoma comprovado** (GET público, read-only, 17/06 15:2x): `https://roleta.xma-ia.com/` serve
`app.js?v=4.3.2` — **sem** `updateBlockGale`, **com** o `?? 17` legado (15 557 bytes). O frontend
em produção está **congelado numa versão antiga**, apesar do repositório já ter mudanças.

**Causa-raiz (verificada no código versionado):** o nginx do host serve os estáticos de
`root /var/www/roleta` (`roleta.conf:14`) e faz proxy de `/ws` → `127.0.0.1:8765`. O container
(`docker-compose.yml`, 1 serviço) roda só `python main.py` (WebSocket + `/health`) — **não serve
estáticos** (nenhum `StaticFiles`/`var/www` no Python). E **nenhum** script de deploy
(`scripts/roleta-deploy-pull.sh`, `tools/deploy_pull.sh`, `setup_server.sh`) **copia `frontend/` →
`/var/www/roleta`** nem recarrega o nginx. O `git reset --hard` atualiza só `/root/roleta-cloud/frontend`,
que **ninguém serve**. `/var/www/roleta` foi populado **manualmente uma vez** e nunca mais.

> **Impacto:** TODA mudança de frontend (esta e as anteriores do operador) ficou só no repo —
> produção nunca a recebeu. Responde à pergunta "as mudanças estão 100% funcionais?": **não, sem
> este fix.**

**Correção implementada** (`scripts/roleta-deploy-pull.sh`, o canônico instalado em
`/usr/local/bin/`): após o healthcheck OK, **sincroniza `frontend/` → `$WWW_DIR`** (default
`/var/www/roleta`) e **`nginx -t && systemctl reload nginx`**. **Não-fatal** (guard `command -v`,
`|| log`) — uma falha de front não derruba o backend saudável; roda só após o container estar `Up`.
`bash -n` OK. O duplicado `tools/deploy_pull.sh` (que tem **CRLF** pré-existente e está mais antigo,
sem o passo `alembic`) foi **deixado intocado** e sinalizado como follow-up (unificar/remover).

```bash
# scripts/roleta-deploy-pull.sh — após healthcheck OK, antes de "DEPLOY OK"
WWW_DIR="${WWW_DIR:-/var/www/roleta}"
if [ -d "$REPO_DIR/frontend" ]; then
  if mkdir -p "$WWW_DIR" && cp -a "$REPO_DIR/frontend/." "$WWW_DIR/"; then
    log "FRONTEND sync ok -> $WWW_DIR (sha=$REMOTE)"
    command -v nginx >/dev/null 2>&1 && nginx -t >/dev/null 2>&1 \
      && { systemctl reload nginx && log "NGINX reload ok" || log "NGINX reload falhou (nao-fatal)"; } \
      || log "NGINX ausente/config invalida — reload pulado (nao-fatal)"
  else log "FRONTEND sync FALHOU (nao-fatal)"; fi
fi
```

**Pendências de operação (não automatizáveis daqui):**
- O `roleta.conf` é versionado mas **não** é deployado por script — garantir que está em
  `/etc/nginx/sites-enabled/` no host (one-time).
- **Pré-requisito do fix:** o deploy só passa a funcionar de fato **após** este commit chegar em
  `main` (o systemd timer puxa `origin/main`). Como nem este fix nem as mudanças de front foram
  commitados/enviados nesta sessão, **produção segue em v4.3.2 até o push + deploy**.
- Verificação pós-deploy: `curl -s https://roleta.xma-ia.com/app.js | grep -c updateBlockGale`
  (deve retornar ≥1) e conferir `app.js?v=4.4.0` no `index.html` servido.

### 11.3 Itens revisados e **corretos** (sem ação)
Escopo do `state_sync.update` sob `state_lock` (snapshot coerente); injeção no `trace` em
`try/except` defensivo; `block_gale_engine.stake` clampado (`MULT[level]`, level 1..4); flags
por-chamada no heartbeat; suíte verde; `lint_silent_except` OK (sem novos `except`).

---

### Apêndice A — Evidência executada (teste de fluxo)

`CSelectionEngine.select("anti-horario", centers=[17,5,26])` + `BlockGaleEngine(base_unit=1)`:

```
=== BACKEND CALCULA (var_c1c2_c3 ON) ===
chosen=C2 · pair=C2+C3 · numbers(14)=[0,3,5,8,10,12,15,16,23,24,26,32,33,35] · centers(2)=[5,26]
=== STAKE (block_gale cap=1) === stake real=14.0u · level/mult=1/1
=== sugestao carrega === c_selection{chosen:C2,pair:C2+C3,n:14} block_gale{...} bet_gate{...}
=== GLASS BOX faz === handleSuggestion IGNORA · card usa trace(sem c_selection) · valor=martingale legado(R$17) ≠ 14u
```

Suíte: `tests/test_wiring_c_gale.py` **10 passed**; suíte completa do projeto **523 passed**
(conforme `implantação_C1_variavel_junho.md §8`).

### Apêndice B — Arquivos citados

`frontend/app.js` (234-242, 264-272, 313-330) · `frontend/index.html` (67-75, 135-140) ·
`server/message_handler.py` (110, 203-223, 564-602, 904-942, 948-983) ·
`server/websocket.py` (354-403) · `state/game.py` (399-486, 564-610, 902-928) ·
`extension/content.js` (476-482, 527) · `extension/popup.js` (506, 668-713).

---

*Gerado em 17/06/2026 por revisão dev-sênior (RADAR MCP: filesystem, graphify, memory,
sequential-thinking, brave-search; 2 subagents de investigação). Fonte da verdade do código:
`main` @ `de095d0`.*

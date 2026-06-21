# Detalhamento da Estrutura da Escuta Beat — Junho 2026 (estado ATUAL)

> Documento de referência técnica do pipeline da **Escuta Beat** (extensão Chrome) e da
> infraestrutura de dados pós-coleta no servidor. Descreve o que o sistema faz **hoje**
> no DOM, como os dados fluem, os pontos fortes da metodologia, o objetivo de saída e o
> que ainda **não** conseguimos. Base: auditoria pós-implantação de 15/06/2026
> (commit de referência `23c3490` + correções client-side de 15/06).

---

## 1. Visão geral e propósito

A **Escuta Beat** é uma extensão Chrome (Manifest V3, `extension/manifest.json` v**3.3.0**)
que **lê em tempo real** os resultados de mesas de roleta ao vivo (foco: Evolution) direto
da página do cassino, sem API oficial, e os envia para o servidor Python, que roda a
estratégia (SDA17), decide a aposta e persiste tudo.

Desde 14/06 a Escuta opera em modo **Auto-Start / Zero-Upload**: detecta o provider sozinha
e começa a escutar **sem o operador precisar carregar JSON nem clicar**.

Dois eixos de dados convivem:
- **Eixo de jogo** (maduro, em produção): número sorteado + direção do giro → estratégia.
- **Eixo de sessão/identidade** (em estabilização): `dealer` (crupiê), `round_id`, `table`
  (mesa), `provider`. É o foco desta auditoria.

---

## 2. Arquitetura em camadas (fluxo ponta a ponta)

```
┌───────────────────────── CLIENT (Chrome Extension MV3 — Escuta Beat v3.3.0) ─────────────────────────┐
│                                                                                                       │
│  AUTO-START (zero-upload):                                                                             │
│    chrome.webNavigation.onCompleted / onHistoryStateUpdated  (filtro hostContains de cassinos)        │
│      → getAllFrames → provider_router.js (detectFromFrames/matchHostToProvider)                       │
│      → loadBundledManifest(fetch chrome.runtime.getURL('providers/<provider>.json'))                  │
│      → startListeningInternal(tabId, manifest)  ⇒  state.extractorData = manifest                     │
│                                                                                                       │
│  LOOP DE LEITURA (chrome.alarms 'readLoop', periodInMinutes 0.0333 ≈ a cada 2 s):                     │
│    para cada tick, 3× chrome.scripting.executeScript({ allFrames: true }):                            │
│      (1) extractResultsFromPage()        ← HARDCODED  '[data-role="recent-number"]'  → números        │
│      (2) extractMonitoringData(cfg)      ← cfg IGNORADO, seletores HARDCODED        → status/saldo     │
│      (3) extractSessionData(cfg,opts)    ← DATA-DRIVEN (state.extractorData.data.session)              │
│                                            → { dealer, round_id, table, frameUrl, isGameFrame,         │
│                                                dealerCandidates? }                                     │
│    combineSessionFrames() consolida os frames (prioriza isGameFrame)                                  │
│                                                                                                       │
│  EM PARALELO (content script, all_frames): deal_capture.js — MutationObserver no <body>,              │
│    PROVIDER_SELECTORS hardcoded por provider; provider por host (evolution/evo-games);                │
│    persiste em chrome.storage.local.dealMeta (FALLBACK do eixo de sessão).                            │
│                                                                                                       │
│  AO DETECTAR NOVO NÚMERO → sendToWebSocket('novo_resultado', {                                         │
│      numero, direcao, trace_id, t_client, allNumbers, monitoringData,                                  │
│      dealer:    _sd.dealer    || _dm.dealer    || null,   // data-driven primeiro, deal_capture depois │
│      table:     _sd.table     || _dm.table     || null,                                                │
│      provider:  _dm.provider  || null,          // provider sempre do deal_capture (URL-based)         │
│      round_id:  _sd.round_id  || _dm.round_id  || null })                                              │
└───────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                                 │  WebSocket (TLS)
┌────────────────────────────────────────────────▼──────────────────────────────────────────────────────┐
│  SERVER (Python v4.4.1)                                                                                 │
│    server/websocket.py        — MessageHandler ÚNICO (singleton), state_lock GLOBAL, game_state global  │
│    server/message_handler.py  — handle_new_result():                                                    │
│        • valida SpinInput (models/input.py): dealer/table/provider/round_id OPCIONAIS (max_length)      │
│        • loga [DEAL] dealer=… provider=… table=… round=…   (linha ~192)                                 │
│        • roda estratégia SDA17, monta DecisionRecord:                                                   │
│              dealer=(spin.dealer or 'unknown'), dealer_table=(spin.table or ''),                        │
│              provider=(spin.provider or ''), round_id=(spin.round_id or '')                             │
│    PERSISTÊNCIA (FONTE DA VERDADE): SQLite  data/decisions.db                                           │
│        database/sqlite_repo.py — auto-migrate SP-13 (colunas dealer/dealer_table/provider/round_id      │
│        + índice ix_decisions_dealer); INSERT grava os 4 campos                                          │
│    DUAL-WRITE OPCIONAL (dual_write_pg=false por padrão): outbox → Postgres                              │
│        cw.spin_features / ccw.spin_features (provider, table, dealer, round_id)                         │
│        shared.dealers  UNIQUE(name, provider, table)        (migration 0007)                            │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                 │
┌────────────────────────────────────────────────▼──────────────────────────────────────────────────────┐
│  CONSUMO (downstream do dealer)                                                                         │
│    strategies/dealer_offset.py (SP-15) — offset preferencial por dealer/direção (n≥30);                 │
│                                          flag env SDA_DEALER_OFFSET (default '0' = OFF)                  │
│    server/health_server.py  /api/dealers (SP-14) — ranking de dealers por hit_rate (dealer_stats)       │
│    state/game.py — reset de estado adaptativo na TROCA de dealer/mesa                                   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tecnologia utilizada

| Camada | Tecnologia / API | Observações |
|---|---|---|
| Extensão | **Chrome Manifest V3**, Service Worker | `extension/manifest.json` v3.3.0 |
| Permissões | `activeTab, tabs, scripting, storage, alarms, webNavigation` + `host_permissions:<all_urls>` | `<all_urls>` permite injetar em iframes cross-origin (o jogo Evolution roda em `*.evo-games.com`) |
| Agendamento | `chrome.alarms` (`readLoop` ~2 s, `keepAlive` ~15 s) | MV3 não tem `setInterval` confiável (SW dorme) |
| Injeção no DOM | `chrome.scripting.executeScript({ allFrames:true, func, args })` | Serializa a `func` via `toString()` → **funções injetadas devem ser self-contained** |
| Detecção de provider | `chrome.webNavigation` + `provider_router.js` (fingerprint host→provider) | Auto-start sem upload |
| Manifests | `providers/*.json` empacotados (`web_accessible_resources`), lidos via `fetch(getURL)` | Seletores editáveis sem rebuild |
| Captura paralela | Content scripts `deal_capture.js` (all_frames, MutationObserver) e `content.js` (overlay) | Fallback do eixo de sessão |
| Transporte | WebSocket sobre TLS | `novo_resultado` |
| Servidor | Python (asyncio + websockets), Pydantic (`SpinInput`) | Singleton + `state_lock` global (mono-mesa em runtime) |
| Persistência | **SQLite** `data/decisions.db` (fonte da verdade) + **Postgres** opcional (analytics/federação) | volume `roleta-data`; `*.db` gitignored |
| Observabilidade | log estruturado `[DEAL]`, endpoint `/api/dealers`, Prometheus/Grafana/Alertmanager | 6 containers em produção |

---

## 4. O que a Escuta faz HOJE no DOM (detalhado)

A cada ~2 s, em **todos os frames** da aba monitorada, rodam três varreduras independentes
(cada uma em `try/catch` isolado — um erro não derruba as demais):

### 4.1 Números da roleta — `extractResultsFromPage()` (HARDCODED)
- Seletor raiz: `document.querySelectorAll('[data-role="recent-number"]')`.
- Para cada elemento, 3 métodos em cascata: `[data-role^="number-"]` → `[class*="value"]` →
  texto direto (inteiro 0–36). Retorna `{ numbers, elementsFound }`.
- **Não usa o JSON** — seletores fixos no código. É o eixo maduro e funcional.

### 4.2 Status da mesa — `extractMonitoringData()` (HARDCODED; `cfg` ignorado)
- **Status aberto/fechado** por 3 métodos: texto do semáforo
  (`[class*="trafficLightText"]`, `[class*="statusMessage"]`, …), **bloqueio de chips**
  (`[data-role='chip-stack-wrapper']`, `[class*='chipStack']`) e **timer visual**
  (`[data-role='circle-timer']`, `[class*='countdown']`).
- Também tenta saldo/aposta/chip ativo. Retorna `monitoring{…}`.

### 4.3 Identidade da sessão — `extractSessionData(sessionConfig, opts)` (DATA-DRIVEN)
- Lê os seletores de `state.extractorData.data.session` (do manifest `providers/evolution.json`,
  schema v18.2): blocos `dealer.name`, `round.id`, `table.name`, cada um com
  `{ selector, fallbackSelectors[], attribute, maxLen }`.
- Para cada bloco: tenta o seletor primário e depois cada fallback, parando no primeiro
  texto não-vazio (`probeSelectors`/`cleanText`, **internos à função** — ver §8.1).
- **Marca `isGameFrame`** = `!!doc.querySelector('[data-role="recent-number"]')` — indica se
  ESTE frame é o do jogo (tem os números) e não um lobby/cross-sell.
- **Diagnóstico opcional** (`opts.collectCandidates`, ligado ~1 a cada 5 ticks): quando o
  `dealer` não casa nenhum seletor, varre o DOM por elementos-folha cuja classe/`data-role`
  contenha `dealer|croupier|presenter|host` e devolve até 8 candidatos `{cls, role, txt}`
  para afinar os seletores **sem chute**.
- `combineSessionFrames()` consolida os resultados de todos os frames, **priorizando
  `isGameFrame`** (correção 15/06) e, dentro de cada categoria, mantendo "primeiro
  não-nulo vence".

### 4.4 Captura paralela legacy — `deal_capture.js`
- Content script em `all_frames`, `MutationObserver` no `<body>`.
- `provider` por **host** da URL (`evolution`/`evo-games` → `'evolution'`; senão `host:<host>`).
- `dealer`/`table`/`round` por `PROVIDER_SELECTORS` **hardcoded** por provider.
- Persiste em `chrome.storage.local.dealMeta`; é o **fallback** quando o data-driven não traz dado.

---

## 5. Estrutura de dados (esquema)

**Payload `novo_resultado` (cliente → servidor):**
`{ numero, direcao, trace_id, t_client, timestamp, allNumbers[], monitoringData, dealer, table, provider, round_id }`

**`SpinInput`** (`models/input.py`): `dealer: str|None (max_length=120)`, `table`, `provider`,
`round_id` — todos opcionais.

**Tabela `decisions`** (SQLite, fonte da verdade) — campos de identidade:
`dealer TEXT DEFAULT 'unknown'`, `dealer_table TEXT`, `provider TEXT`, `round_id TEXT`,
índice `ix_decisions_dealer`. (Migração automática SP-13 em `sqlite_repo.py`.)

**Postgres (opcional, federação)** — `migration 0007`:
`cw/ccw.spin_features(provider, table, dealer, round_id)` e
`shared.dealers UNIQUE(name, provider, table)`.

---

## 6. Pontos fortes da metodologia

1. **Zero-Upload / Auto-Start** — detecta o provider e carrega o manifest empacotado sozinha;
   o operador só abre a mesa. Remove o maior ponto de fricção/erro (upload manual de JSON).
2. **Captura data-driven da sessão** — seletores de `dealer/round/table` ficam no
   `providers/*.json`; ajustar o DOM do provider é **editar JSON, sem rebuild da extensão**.
3. **Resiliência por isolamento** — números, monitoramento e sessão rodam em `try/catch`
   separados; falha de um não afeta os outros. Há **fallback** (deal_capture) quando o
   data-driven não traz dado.
4. **Cobertura multi-frame** — `allFrames:true` + `<all_urls>` alcançam o iframe cross-origin
   do jogo (`*.evo-games.com`), onde o HUD realmente vive.
5. **Priorização do frame do jogo** (`isGameFrame`, 15/06) — evita capturar identidade de
   lobby/cross-sell; correlaciona a sessão com o frame que tem os números reais.
6. **Persistência robusta e auditável** — SQLite como fonte única da verdade, com
   auto-migração idempotente e índices; dual-write opcional para Postgres (analytics).
7. **Observabilidade de primeira classe** — log `[DEAL]` por giro, endpoint `/api/dealers`,
   métricas Prometheus/Grafana, alertas. Permite auditar o pipeline em produção via SSH.
8. **Robustez operacional MV3** — WebSocket idempotente, `suppressTab` (STOP manual
   respeitado), locks por `tabId`, `keepAlive` — correções endurecidas em 14/06.
9. **Qualidade travada por testes** — a captura de sessão tem testes que **replicam a
   serialização MV3** (injeção isolada), prevenindo a regressão do bug de closure (§8.1).

---

## 7. Objetivo desejado na saída

Para **cada giro**, persistir um registro completo e confiável:

```
{ numero, direcao, provider, table (mesa canônica), dealer (NOME REAL do crupiê), round_id }
```

Com isso, habilitar o downstream que **já existe mas está dormente**:
- **`shared.dealers`** populado e particionado por provider;
- **`dealer_offset`** ativável (`SDA_DEALER_OFFSET=1`) — offset preferencial por crupiê/direção;
- **ranking `/api/dealers`** por hit_rate (qualidade por crupiê/mesa);
- **reset automático** do estado adaptativo na **troca de dealer** (toast "Novo dealer: X —
  resetar?"), evitando contaminação cross-sessão;
- base para **federação multi-provider / multi-mesa** (Sprints 3–7 do `passos_escuta_junho.md`).

Meta de qualidade: `dealer` real em **≥ 95%** dos giros de mesas com crupiê exposto no DOM;
`round_id` e `table` **canônicos** e consistentes com a mesa em jogo.

---

## 8. O que ainda NÃO conseguimos (gaps e causas)

### 8.1 `dealer` = 100% `"unknown"` em produção  ⛔ (gap principal)
- **Evidência (15/06):** das **6.782** decisões em `data/decisions.db` (desde jan/2026),
  **nenhuma** tem dealer real; logs `[DEAL]` mostram **sempre** `dealer=None`.
- **Causa raiz #1 — PROVADA e CORRIGIDA (15/06):** `extractSessionData` referenciava
  helpers (`probeSelectors`/`cleanText`) do *closure do módulo*. Como o
  `executeScript({func})` serializa **só o corpo** da função, no contexto da página dava
  `ReferenceError` silencioso (engolido pelo `try/catch`) → dealer/round/table **sempre null**.
  Corrigido tornando a função **self-contained** + teste de regressão que replica a injeção.
- **Causa raiz #2 — CONFIRMADA, em aberto:** mesmo com o caminho data-driven revivido
  (prova: o `table` passou a popular), os seletores de **dealer** (`[data-role='dealer-name']`
  + 7 fallbacks) **não casam** o DOM real da Evolution. Hipótese forte: o nome do crupiê
  costuma estar **apenas no stream de vídeo** (não no HTML) — nesse caso, seletor CSS é
  inviável e seria preciso OCR. **Instrumentação de candidatos** (§4.3) foi adicionada para
  descobrir o seletor real a partir de evidência, sem adivinhação.

### 8.2 `round_id` = 100% vazio  ⛔
- Mesma Causa #2: seletores `[data-role='game-id']` + fallbacks não casam o DOM real.

### 8.3 `table` popula, mas com valor ERRADO  ⚠️ (corrigido — aguarda validação)
- **Evidência (15/06):** após o reload, `table` passou a vir preenchido, porém com
  `'Blackjack Silver D'` em **dezenas de giros de roleta** (`PorROU0000000001`).
- **Causa:** `combineSessionFrames` "first-non-null" + `allFrames` capturava o título de um
  **frame de lobby/cross-sell**. **Correção aplicada (15/06):** priorizar `isGameFrame`
  (o frame que tem os números). **Pendente:** confirmar no próximo reload que o `table`
  passa a refletir a mesa em jogo.

### 8.4 Downstream dormente
- Como `dealer='unknown'`, `dealer_offset` faz early-return (e está OFF por flag),
  `/api/dealers` ranqueia só `unknown`, `shared.dealers` nunca recebe linhas, e o reset por
  troca de dealer nunca dispara.

### 8.5 Ruído de `provider`
- Por rodar em `all_frames`, às vezes o `provider` vem de frames de analytics
  (`host:…doubleclick.net`, `host:…cactusgaming.net`) em vez de `evolution`. Não quebra o
  jogo, mas polui a identidade.

### 8.6 Mono-mesa em runtime
- `game_state` singleton + `state_lock` global: **uma mesa por vez**. 2ª aba é recusada
  (com log). Multi-mesa simultânea depende das Sprints 4+.

---

## 9. Estado empírico atual (produção 187.45.181.75, 15/06 ~17:43 UTC)

| Campo | Estado | Observação |
|---|---|---|
| `numero` / `direcao` | ✅ fluindo | eixo de jogo maduro |
| `provider` | ✅ majoritariamente `evolution` | algum ruído de analytics |
| `table` | ⚠️ fluindo, porém suspeito (`Blackjack Silver D` em roleta) | correção `isGameFrame` aplicada, **aguarda reload** |
| `dealer` | ⛔ 100% `unknown` | Causa #2 — seletores/❓vídeo; instrumentação ativa |
| `round_id` | ⛔ 100% vazio | Causa #2 |

---

## 10. Correções aplicadas nesta auditoria (15/06)

1. **`extractSessionData` self-contained** (`extension/session_extractor.js`) — `cleanText`/
   `probeSelectors` movidos para dentro da função; elimina o `ReferenceError` sob injeção MV3.
2. **Coleta de candidatos de dealer** (`session_extractor.js` + `background.js`) — diagnóstico
   opcional, *throttled*, que loga candidatos do DOM nos logs da Escuta para afinar seletores.
3. **Priorização do frame do jogo** (`isGameFrame` em `session_extractor.js`) — corrige o
   `table` capturado de frame errado.
4. **Testes** (`tests/test_session_extractor.py`) — 16 casos, incluindo: injeção MV3
   self-contained, coleta de candidatos (com custo-zero sem a flag) e priorização de
   game-frame. Suíte completa: **485 passed**, 9 skipped, 1 xfailed.

> As mudanças são **client-side**: exigem **recarregar a extensão** (`chrome://extensions`)
> para entrar em vigor. O deploy do servidor não distribui a extensão.

---

## 11. Próximos passos recomendados

1. **Recarregar a extensão** e jogar alguns giros; conferir nos logs da Escuta a entrada
   **"Dealer NAO capturado — candidatos no DOM"** com os seletores reais do crupiê.
2. Com os candidatos, **ajustar `providers/evolution.json › data.session.dealer`** (e `round`)
   — sem chute. Validar que `decisions.dealer` passa a popular via logs `[DEAL]`.
3. Confirmar que o `table` deixou de trazer o título de lobby (efeito do `isGameFrame`).
4. Se o crupiê estiver **apenas no vídeo**, decidir entre: (a) abrir o painel/HUD que exibe o
   nome em texto, ou (b) abandonar dealer e focar em `table`+`round` canônicos.
5. Quando `dealer` popular de forma estável, avaliar ligar `SDA_DEALER_OFFSET=1` e o
   reset-por-dealer; depois, retomar a federação multi-provider (Sprints 3–7).

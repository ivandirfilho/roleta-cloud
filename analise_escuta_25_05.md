# 🔍 Análise da Escuta Beat — Pode capturar dealer/provider/table_id hoje?

> **Pergunta-síntese:** _"essas regras do `extrator_completo.json` permitem capturar o dealer? E se já existe um direcionamento, basta acertar a leitura para mandar para o database?"_
>
> **Resposta-curta:**
> - **`table_id`** → **SIM, já está disponível** (na URL do iframe Evolution, em `_detectedFrames`); basta parser regex, ~5 LoC.
> - **`provider`** → **SIM, já está disponível** (na URL do iframe `evo-games.com` e em `_meta.provider.name`); ~5 LoC.
> - **`dealer_name`** → **NÃO**, não existe seletor no extrator atual; precisa adicionar um seletor novo + scan no iframe `a8-latam.evo-games.com` (frameIndex 7/8). ~30 LoC + tunagem visual.
> - **`round_id`/`game_id`** → **NÃO**, não no extrator; Evolution expõe no payload da WebSocket interna, alternativa = DOM `data-round-id` ou interceptar fetch.
>
> **Gerado:** 2026-05-25 16:25 BRT · **Modelo:** claude-opus-4.7 · **Stack MCP:** `filesystem` + `brave-search` + `sequential-thinking` + `graphify` + `memory`
>
> **Predecessores:** [`Visualizacao_da_evolucao_25_05.md`](./Visualizacao_da_evolucao_25_05.md) · [`sprint_evolucao_25_05.md`](./sprint_evolucao_25_05.md) (esta análise atualiza DP-01..DP-05)

---

## §1. O que o extrator entrega HOJE — auditoria seção-por-seção

`extrator_completo.json` (32 KB, v18.1.0, gerado contra `betvip.bet.br/games/evolution/roleta-ao-vivo`).

| Bloco | Conteúdo | Útil para captura de dealer? |
|---|---|---|
| `_meta.provider` | `{name: "Evolution Gaming", note: "..."}` | ✅ **SIM** — `provider` já vem |
| `_meta.source.url` | URL da página host | ⚪ contexto |
| `_compatibility.unicodeWarning` | Aviso U+2066/2069 em valores BRL | ⚪ aplicar parseMoneyBRL |
| `_quickStart` | Funções `parseMoneyBRL`, `checkIsOpen`, `executarAposta` | ⚪ helpers |
| `_detectedFrames` | **9 iframes**, com URLs completas; **frame 7 e 8 = `a8-latam.evo-games.com`** com `table_id=PorROU0000000001&provider=evolution&game=roulette` na URL | ✅ **SIM** — `table_id` + `provider` direto da URL |
| `config.iframeAccess` | `{gameIframeHost: "a8-latam.evo-games.com", extractionMethod: "allFrames"}` + exemplo `chrome.scripting.executeScript({target:{...allFrames:true}})` | ✅ infra pronta para entrar no iframe Evolution |
| `config.numberColors` | Mapa 0-36 → red/black/green | ⚪ inalterado |
| `data.monitoring.gameStatus` | 3 métodos: `.trafficLightText--14759`, `[data-role='chip-stack-wrapper']`, `[data-role='circle-timer']` | ⚪ não relevante p/ dealer |
| `data.monitoring.finance` | `[data-role='balance-label-value']`, `[data-role='total-bet-label-value']` | ⚪ inalterado |
| `data.monitoring.chipControl` | `[data-role='selected-chip'] [data-role='chip']` | ⚪ inalterado |
| `data.monitoring.gameControls` | undoButton/doubleButton/repeatButton (todos `found:false`) | ⚪ inalterado |
| `data.betSpots` | numbers/specials/regions (vazios nesta extração) | ⚪ inalterado |
| `data.results` | `[data-role="recent-number"]` + `.value--dd5c7` | ⚪ é o que já alimenta o spin |
| `data.statistics` | sample=0 | ⚪ |

### Conclusão direta sobre seletores
| Campo desejado | Existe seletor no extrator hoje? | Comentário |
|---|---|---|
| `dealer_name` | ❌ **NÃO** | Nenhuma chave `dealer`, `croupier`, `presenter`, `host` em todo o JSON |
| `dealer_id` | ❌ **NÃO** | idem |
| `provider` | ✅ **SIM via 2 fontes:** `_meta.provider.name` e regex em frame URL | Hoje a Escuta usa hardcode `'evolution'` em `background.js:627` — basta substituir |
| `table_id` | ✅ **SIM** — regex `table_id=([^&]+)` em URL do frame Evolution | Hoje a Escuta ignora |
| `round_id` / `game_id` | ❌ **NÃO** no extrator | Evolution envia em WS interno; alternativa: interceptar `fetch`/`XHR` ou achar `data-round-id` no DOM |
| `shift` (turno do dealer) | ❌ **NÃO** | Derivável de `hora_do_dia` no servidor |

---

## §2. Por que o JSON **não tem** seletor de dealer (engenharia reversa do design)

A v18.1.0 do `ExtractorBeat` foi otimizada para 4 missões: **detectar estado** (gameStatus), **ler finanças** (balance/totalBet), **mapear betSpots** (executor pode clicar) e **ler resultados** (recent-number). **Identidade do dealer simplesmente não entrou no escopo** — é racional, porque o Executor Beat não precisa do dealer para apostar.

O que faltou: **uma seção `data.session` com seletores de identidade da sessão**:
```jsonc
"session": {
  "dealer":    { "selector": "[class*='presenter']", "attribute": "innerText" },
  "tableName": { "selector": "[class*='tableName']", "attribute": "innerText" },
  "tableId":   { "source": "iframe.url", "regex": "table_id=([A-Za-z0-9]+)" },
  "provider":  { "source": "iframe.url", "match": { "evo-games.com": "evolution", "pragmaticplaylive": "pragmatic" } },
  "roundId":   { "selector": "[data-round-id]", "attribute": "data-round-id" }
}
```

Essa é a **mudança proposta no extrator** (sprint **DP-02 do `sprint_evolucao_25_05.md`** se ajusta para também usar essa estrutura — atualização abaixo §6).

---

## §3. Como capturar HOJE com o que já existe (3 níveis)

### Nível 1 — Quase grátis (provider + table_id, 5-10 LoC, 30 min)

Como já vem em `_detectedFrames[*].url`, basta:

```javascript
// extension/background.js
function extractSessionFromFrames(frames) {
  // priorizar frame com isEvolution=true && isPotentialGame=true && !isMainFrame
  const gameFrame = frames.find(f => f.isPotentialGame && !f.isMainFrame && f.domain.includes('evo-games'));
  if (!gameFrame) return { provider: null, table_id: null };

  const url = gameFrame.url;
  const tableIdMatch = url.match(/table_id=([^&#]+)/);
  const providerMatch = url.match(/provider=([^&#]+)/);

  return {
    provider:  providerMatch?.[1] || (gameFrame.domain.includes('evo-games') ? 'evolution' : null),
    table_id:  tableIdMatch?.[1] || null,
    table_domain: gameFrame.domain,
    game_type: (url.match(/game=([^&#]+)/) || [])[1] || null
  };
}

// 2. anexar no payload novo_resultado:
sendToWebSocket({
  type: 'novo_resultado',
  numero: newNumber,
  direcao: currentDirection,
  trace_id: `${Date.now()}-${rand}`,
  t_client: Date.now(),
  timestamp: Date.now(),

  // 🆕
  provider:  state.session?.provider  || null,   // antes era hardcoded 'evolution'
  table_id:  state.session?.table_id  || null,   // novo
  game_type: state.session?.game_type || null    // 'roulette' geralmente
});
```

**Update do extrator** (recomendado): rodar `ExtractorBeat` a cada N segundos para refrescar `_detectedFrames` (URL muda se usuário trocar mesa). Hoje o extrator parece ser uma snapshot manual; vira polling de 30s.

### Nível 2 — Captura DOM do dealer (30 LoC + tunagem visual, 1-2h)

Evolution Gaming não tem classe estável `.dealer-name` documentada (web search confirma — classes são **minificadas/hashed**). Estratégias robustas:

#### 2a. Probe-based: enumerar candidatos e ranquear
```javascript
function probeDealerName(rootDoc) {
  // 1. Pega TODOS os spans/divs com texto curto (3-30 chars) em UI overlay do video
  const candidates = [...rootDoc.querySelectorAll('span, div')]
    .map(el => ({ el, text: (el.innerText||'').trim() }))
    .filter(c => c.text.length >= 3 && c.text.length <= 30)
    .filter(c => /^[A-ZÀ-Ý][a-zà-ÿ]+(\s[A-ZÀ-Ý][a-zà-ÿ]+)?\.?$/u.test(c.text));  // Nome Próprio
  // 2. Heurística: dealer fica no canto superior ou em overlay sobre video
  return candidates
    .map(c => {
      const rect = c.el.getBoundingClientRect();
      const inVideoArea = rect.top < 200 && rect.left > 100;  // ajustar
      const hasPresenterClass = (c.el.className||'').match(/presenter|dealer|host|game-host/i);
      return { ...c, score: (inVideoArea?2:0) + (hasPresenterClass?5:0) };
    })
    .sort((a,b) => b.score - a.score)[0]?.text || null;
}
```

#### 2b. Mutation-driven: monitorar mudanças no overlay
```javascript
const observer = new MutationObserver(_.debounce(() => {
  const newDealer = probeDealerName(document);
  if (newDealer && newDealer !== state.session?.dealer) {
    chrome.runtime.sendMessage({
      action: 'dealerChanged',
      dealer: newDealer,
      ts: Date.now()
    });
  }
}, 500));

observer.observe(document.body, { childList: true, subtree: true, characterData: true });
```

#### 2c. Aprendizagem assistida (uma única vez, manual)
Botão na overlay da extensão: **"Apontar dealer"** → usuário hover no nome do dealer → extensão captura `el.cssPath()` e salva em `mesaConfig.selectors.dealerName`. Depois fica automático. **Esta é a mais robusta** porque resolve o problema de classes hashadas que web search confirmou.

> **⚠️ Cross-origin:** o frame `a8-latam.evo-games.com` é cross-origin. Para o content_script entrar lá, `manifest.json` precisa de `host_permissions: ["*://*.evo-games.com/*"]` (já tem `<all_urls>`, mas confirmar) + `all_frames:true` no `executeScript` (já configurado em `config.iframeAccess`).

### Nível 3 — Round/Game ID via interceptor (1 dia)

Evolution usa WebSocket interno em `wss://*.evo-games.com/`. Intercepta-se com:

```javascript
// Injetar no contexto da page (não isolated world) via <script> tag
const origWS = window.WebSocket;
window.WebSocket = function(url, protocols) {
  const ws = new origWS(url, protocols);
  if (url.includes('evo-games')) {
    ws.addEventListener('message', ev => {
      try {
        const data = JSON.parse(ev.data);
        if (data.args?.gameId || data.game?.id || data.tableId) {
          window.postMessage({type:'__evo_intercepted', payload: data}, '*');
        }
      } catch(e) {}
    });
  }
  return ws;
};
```

Aí o content_script ouve `window.addEventListener('message', ...)` e propaga `round_id` para o background. **Custo:** alto risco de manutenção (Evolution muda payload sem aviso), e há discussão jurídica sobre interceptar WS do operador. **Recomendado adiar** para depois das alavancas A/B/C do roadmap.

---

## §4. Fluxo de leitura atual da Escuta Beat (engenharia reversa)

```
┌────────────────────────────────────────────────────────────────────────┐
│ EXTRACTOR BEAT (manual, gera extrator_completo.json)                   │
│   ├─ injeta script com allFrames:true                                  │
│   ├─ varre 9 iframes, classifica isEvolution/isPotentialGame           │
│   └─ persist JSON com seletores                                        │
└────────────────────────────────────────────────────────────────────────┘
                          │ usuário sobe JSON via popup
                          ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ESCUTA BEAT (extension/background.js — service worker MV3)             │
│   1. recebe extractorData via chrome.runtime.sendMessage               │
│   2. state.mesaConfig = data.config                                    │
│   3. state.currentMesa = data.mesa_id  ←  (vem do microserviço WS)     │
│   4. startReadLoopAlarm() — chrome.alarms a cada ~1 s                  │
│   5. a cada tick:                                                      │
│      ├─ executeScript em allFrames com função que aplica seletores     │
│      │   data.monitoring.results.selector                              │
│      ├─ pega lastNumbers, compara com state anterior                   │
│      └─ se mudou → sendToWebSocket({type:'novo_resultado', numero...}) │
└────────────────────────────────────────────────────────────────────────┘
                          │ WS :8765
                          ▼
┌────────────────────────────────────────────────────────────────────────┐
│ SERVIDOR (server/message_handler.py:53)                                │
│   data = json.loads(message)                                           │
│   if data['type']=='novo_resultado':                                   │
│     game.process_spin(data['numero'], data['direcao'])                 │
│   ← ignora demais campos                                               │
└────────────────────────────────────────────────────────────────────────┘
                          │ SQLite write
                          ▼
              decisions / spins / outbox
                          │ NOTIFY
                          ▼
                cdc_worker → PG cw/ccw
```

### Pontos de injeção para captura de dealer/provider

| Camada | Mudança | Esforço | Sprint |
|---|---|---|---|
| `ExtractorBeat` (v18.1 → v19) | adicionar bloco `data.session` com seletores | 2h | (novo) E-01 |
| `background.js` extractor parser | função `extractSessionFromFrames` (§3 nível 1) | 30 min | DP-01 + DP-03 |
| `background.js` payload | adicionar `provider`, `table_id`, `dealer`, `round_id` em `novo_resultado` | 5 min | DP-01 (expandido) |
| `content.js` mutation observer | `probeDealerName` no iframe Evolution | 1-2h | DP-02 |
| `message_handler.py` | consumir novos campos | 10 min | DP-01 |
| SQLite migration | colunas em `decisions` | 15 min | DP-01 |
| Alembic PG migration | `0010_dealer_provider.py` | 30 min | DP-05 |
| `cdc_worker.py` | handler `_apply_session_meta` | 30 min | DP-05 |

**Total para Nível 1 (provider+table_id):** ~1h30min — entra em **DP-01 expandido**.
**Total para Nível 2 (dealer):** ~3h — entra em **DP-02**.

---

## §5. Riscos e armadilhas

| # | Risco | Mitigação |
|---|---|---|
| R1 | Classes Evolution são **hashadas** (`.trafficLightText--14759` muda a cada deploy) | Usar seletores robustos: `[class*='presenter']`, `[data-role='...']`; nunca classe pura |
| R2 | iframe `a8-latam.evo-games.com` pode mudar de host (ex.: `a9-latam`, `a10-latam`) | Match por substring `evo-games.com` em vez de host exato |
| R3 | Cross-origin: content_script precisa de `host_permissions` para `*.evo-games.com` | Adicionar ao `manifest.json` explicitamente — `<all_urls>` cobre, mas declaração explícita evita warning de loja |
| R4 | Evolution detecta scrapers e bloqueia conta do usuário | Manter scrape **passivo** (sem interferir DOM), debounce alto, não logar credenciais |
| R5 | Dealer name pode estar dentro de `<canvas>` (vídeo overlay) | Falback: OCR (não recomendado agora — over-engineering); maior parte do tempo é texto DOM |
| R6 | `table_id=PorROU0000000001` — `PorROU` indica "Português Roleta" → pode mudar quando mudar idioma | Persistir `table_id` cru, criar `mesa_canonical` separado para humano |
| R7 | Race: ler `state.currentMesa` antes do microserviço extrator setar | Guarda condition: só envia payload com `mesa_id` se `state.currentMesa !== null`, senão envia null |
| R8 | Polling do extractor para refresh `_detectedFrames` aumenta CPU | Refresh só quando `state.currentMesa` muda (event-driven) |
| R9 | Provider hardcoded `'evolution'` ainda usado por algum código legado | grep antes de remover; fazer alias de retrocompatibilidade por 30d |
| R10 | Privacidade: nome do dealer é PII pública mas ainda PII | Hash + persistir só normalized_name (md5 do nome) por padrão; flag opt-in para clear text se debug |

---

## §6. Update das sprints DP-01..DP-05 do `sprint_evolucao_25_05.md`

Com a análise do `extrator_completo.json`, as sprints **DP-01..DP-05 se reorganizam** assim:

### DP-01 (REVISADA) — Captura `provider` + `table_id` direto do iframe URL (NÍVEL 1)
**Era:** "anexar mesa_id" · **Agora:** "anexar provider + table_id + mesa_id + game_type"
**Por quê:** já está em `_detectedFrames[*].url` — não precisa de seletor novo, só parser regex.
**Tarefas:**
1. `background.js` função `extractSessionFromFrames(state.lastFramesScan)` conforme §3 nível 1.
2. Polling 30 s do `chrome.scripting.executeScript({allFrames:true, func: ()=>window.location.href})` para popular `state.lastFramesScan` (ou aproveitar próximo extractor refresh).
3. Anexar em payload `novo_resultado`: `provider`, `table_id`, `mesa_id`, `game_type`, `table_domain`.
4. `server/message_handler.py:53`: ler, propagar a `game.process_spin(meta=...)`.
5. SQLite migration `0009_session_meta.py`: colunas em `decisions`.
6. PG migration espelhada em handler novo `_apply_session_meta_v1`.
**Aceite:** 90 % dos spins pós-deploy com `provider` e `table_id` preenchidos.
**Estimativa revisada:** 0.5d → **0.5d ainda válido**.

### DP-02 (REVISADA) — Captura `dealer_name` (NÍVEL 2 — probe DOM)
**Confirmação web search:** Evolution usa classes **minificadas/hashadas**; seletor estático não é confiável. Por isso a sprint adota **estratégia híbrida 3-em-1**:
1. Tentar seletores comuns `[class*='presenter']`, `[class*='dealer-name']`, `[class*='host']`.
2. Se falhar, rodar `probeDealerName(iframeDoc)` (§3.2a) com heurística posição + className.
3. Botão "Apontar dealer" no overlay (`content.js`) — usuário ensina uma vez por mesa, persiste em `mesaConfig.selectors.dealerName` enviado de volta ao microserviço extrator.
**Cross-origin:** declarar `host_permissions: ["*://*.evo-games.com/*", "*://*.pragmaticplaylive.net/*"]` no `manifest.json`.
**Aceite:** dealer_name capturado em ≥ 70 % dos spins na 1ª semana; ≥ 95 % após botão de tuning ser usado em cada mesa.
**Estimativa revisada:** 2d → **2-3d** (adicionar UI de tuning + persistência).

### DP-03 (CANCELADA → mergeada em DP-01)
**Motivo:** detection de `provider` já está em DP-01 expandido (vem da URL do iframe + `_meta.provider.name`).

### DP-04 (REVISADA) — `round_id` via DOM-first, WS-interceptor opcional
**Por quê:** evitar interceptar WebSocket interno se possível (risco R4).
**Tarefas:**
1. Primeiro tentar `[data-round-id]`, `[data-game-id]`, `[id*='round']` no iframe Evolution.
2. Se vazio em > 50 % dos spins por 24h, ativar interceptor WS (§3 nível 3) atrás de flag `ENABLE_WS_INTERCEPTOR=False` padrão.
3. Index único parcial `decisions(round_id) WHERE round_id IS NOT NULL` (proteção dedup).
**Aceite:** ≥ 80 % com `round_id`; zero duplicatas.
**Estimativa:** 1d (sem interceptor) ou 2d (com).

### DP-05 (MANTIDA) — schema `shared.dealers/tables/providers/dealer_shifts`
Sem mudança; só adiciona campo `table_canonical` (texto humano amigável) além do `table_id` cru.

### 🆕 E-01 — Atualizar `ExtractorBeat` para v19 com bloco `data.session`
**Por quê:** centralizar todos os seletores num só lugar. Hoje extrator não tem `session`; a Escuta Beat acabaria duplicando regex.
**Tarefas:**
1. Adicionar `data.session` ao output do ExtractorBeat com 5 chaves (dealer, tableName, tableId, provider, roundId) — cada uma com `source` (`iframe.url` | `dom`) e `selector|regex`.
2. Bumpar `_meta.version` para `19.0.0`; `_compatibility.minEscutaVersion` para `2.7.0`.
3. README/docs atualizada.
**Aceite:** novo extrator gerado contra Evolution traz `data.session.tableId.value="PorROU0000000001"` automaticamente.
**Estimativa:** 1d.
**Dependência:** **bloqueia DP-02 final** (a probe pode escrever de volta no extrator quando usuário "apontar dealer").

---

## §7. Fluxo final desejado pós-DP-01..DP-05

```
ExtractorBeat v19  →  extrator_completo.json com data.session{}
        │
        ▼  upload manual ou WS automático
ESCUTA BEAT (background.js)
  ├─ refresh frames a cada 30s
  ├─ extractSessionFromFrames() → {provider, table_id, game_type}
  ├─ MutationObserver no iframe Evolution → dealer_name
  ├─ DOM scan → round_id (fallback WS interceptor)
  └─ payload novo_resultado expandido:
      {
        type:'novo_resultado',
        numero, direcao, trace_id, t_client, timestamp,
        provider, table_id, mesa_id, game_type,    // ← DP-01
        dealer, dealer_session_key,                 // ← DP-02 (key = md5(dealer+table+ts_hour))
        round_id,                                   // ← DP-04
        schema_version: 2                           // ← contrato
      }
        │ WS :8765
        ▼
SERVIDOR
  ├─ valida schema_version
  ├─ if v2: extrai meta, chama dealer_resolver.upsert()
  ├─ session_meta_v1 outbox event
  ▼
SQLite decisions com colunas novas (nullable)
        │ NOTIFY
        ▼
cdc_worker → PG handlers _apply_session_meta_v1
  ├─ shared.providers upsert
  ├─ shared.tables upsert
  ├─ shared.dealers upsert (idempotente, race-safe)
  ├─ shared.dealer_shifts upsert por hash_key
  └─ decisions.{provider_id, table_id, dealer_id, dealer_shift_id, round_id}
        │
        ▼
dealer_stats_worker (DP-06)
  └─ shared.dealer_stats EMA por (dealer, direção, hora)
```

---

## §8. Comandos prontos para validar HOJE

```powershell
# 1. Confirmar que table_id e provider EXISTEM na URL do iframe (rodar com extrator atual aberto na mesa)
cd 'C:\Users\Windows\Desktop\Roleta Cloud'
$j = Get-Content extrator_completo.json -Raw | ConvertFrom-Json
$j._detectedFrames.frames | Where-Object { $_.isEvolution -and -not $_.isMainFrame } |
  ForEach-Object {
    $u = $_.url
    $tid = if ($u -match 'table_id=([^&#]+)') { $matches[1] } else { '∅' }
    $prov = if ($u -match 'provider=([^&#]+)') { $matches[1] } else { '∅' }
    "frame[$($_.frameIndex)] domain=$($_.domain) table_id=$tid provider=$prov"
  }

# 2. Verificar se a Escuta hoje (background.js) já tem hook para isso (deve mostrar somente o hardcode)
Select-String -Path .\extension\background.js -Pattern 'provider|table_id|dealer' | Select-Object -First 20

# 3. Live server: confirmar que decisions.provider/table_id não existem ainda
$bash = @"
sqlite3 /root/roleta-cloud/data/roleta.db '.schema decisions' | grep -E 'provider|table|dealer|round' || echo 'NENHUMA coluna meta-sessao ainda'
"@
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($bash))
ssh -i C:\Users\Windows\.ssh\id_rsa root@187.45.181.75 "echo $b64 | base64 -d | bash"
```

---

## §9. TL;DR final

| Pergunta | Resposta |
|---|---|
| _"as regras do extrator permitem visualizar o dealer?"_ | **Não diretamente** — não há seletor para `dealer` no JSON. |
| _"então é só ver o processo de leitura para capturar e mandar pro DB?"_ | Para **provider** e **table_id**: **SIM, basta isso** (estão na URL do iframe `_detectedFrames` — extrator já entrega, Escuta não lê → DP-01 expandido, 0.5d). Para **dealer**: precisa **adicionar uma camada de probe DOM** (DP-02, 2-3d) porque o extrator atual nem mapeou. Para **round_id**: precisa **scan DOM ou interceptor WS** (DP-04, 1-2d). |
| _"o software já tem direcionamento pronto?"_ | **Parcial.** Infra de iframe access (`config.iframeAccess` com `allFrames:true`) e estado client (`state.currentMesa`, `state.mesaConfig`) já existem. Falta o trecho de **parser** no `background.js` e o trecho de **persistência** no servidor + migrations. |

### Próximo passo concreto
Executar **DP-01 expandido** (0.5d, ganha provider + table_id sem custo de DOM) + **E-01** (1d, atualiza ExtractorBeat v19 com `data.session`) em **paralelo**. Depois entrar em **DP-02** (dealer probe) com a infra já alinhada.

---

> _"Quando a informação já está na rua, o caro não é capturar — é estruturar para que ela conte uma história a longo prazo."_

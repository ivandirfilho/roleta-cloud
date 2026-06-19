# Passos Escuta — Junho 2026
## Federação Multi-Provider & Infraestrutura de Dados da Escuta Beat

> **Autor**: Auditoria @ivandirfilho + GitHub Copilot CLI (claude-opus-4.7)
> **Data**: 14/06/2026
> **Escopo**: Evolução da Escuta Beat (`extension/`) e do pipeline `WebSocket → server → DB`
> de mono-provider (Evolution Gaming) para federação multi-provider.
> **Precedido por**: `analise_profunda_extrator_25_05.md`, `fluxode_dados_13_junho.md`

> **🟢 STATUS DE IMPLEMENTAÇÃO (14/06, v3.3)** — O eixo **auto-start / zero-upload**
> (Sprints 1 e 2 client-side) **foi implementado**:
> - `extension/providers/{evolution.json,index.json}` — manifests **empacotados** (web_accessible_resources)
> - `extension/provider_router.js` — classificador de provider por host/URL (§4.9)
> - `extension/background.js` — auto-detecção via `chrome.webNavigation` + `loadBundledManifest` + auto-start (`autoStartPolicy` default `auto`)
> - `extension/popup.{html,js}` — bloco de auto-detecção + toggle auto-start; upload vira fallback
> - Testes: `tests/test_provider_router.py` (9) + `tests/test_bundled_manifest.py` (4); suite **480 passed**
> - **Decisão §8 #7 resolvida**: auto-start LIGADO por padrão (com toggle e salvaguardas NB-02).
> - **Fora deste passo** (continuam como roadmap): servidor multi-mesa (Sprint 3/4), CDN OTA (Sprint 5), strategy router (Sprint 6), UI multi-mesa completa (Sprint 7).

---

## 1. Contexto e motivação

A **Escuta Beat** é a extensão Chrome que lê números em tempo real do site do cassino
e envia para o backend que aplica estratégias (SDA17, etc). Hoje, depois do v3.2.0 (14/06):

- **Funciona apenas com Evolution Gaming**. Operador carrega `extrator_completo.json` no popup,
  aperta Iniciar Escuta, e o Service Worker (SW) faz `chrome.scripting.executeScript`
  contra os iframes do jogo.
- **Já temos** captura data-driven do bloco `data.session` (dealer/round/table) via
  `extension/session_extractor.js` + `extractSessionData()`.
- **O servidor já é multi-provider em dados** (decisions.provider, spin_features.provider,
  shared.dealers UNIQUE(name, provider, table)) desde SP-13 (27/05), mas nunca recebeu
  spins de provider != evolution.

A meta é permitir que o operador abra **qualquer site** (Pragmatic, Playtech, Imagine,
Evolution) e a Escuta detecte automaticamente o provider, carregue o manifest certo
e siga gravando — com isolamento de métricas/estratégia por provider.

---

## 2. Radiografia da arquitetura atual

```
┌────────────────── CLIENT (Chrome Extension v3.2.0) ──────────────────┐
│  popup.loadExtractorFile()      ← upload MANUAL de 1 JSON            │
│  popup.startListening()                                              │
│  background.startListening()    → chrome.alarms periodInMinutes=1/60 │
│  onAlarm('readLoop') → 3× executeScript({allFrames:true}):           │
│      extractResultsFromPage()   ← HARDCODED (não usa JSON)           │
│      extractMonitoringData(cfg) ← cfg IGNORADO                       │
│      extractSessionData(cfg)    ← DATA-DRIVEN ✅ (v18.2)             │
│  sendToWebSocket('novo_resultado', {dealer, table, provider, ...})   │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼────────────────────────────────────┐
│  SERVER (Python)                                                     │
│  websocket.py: MessageHandler ÚNICO (singleton)                      │
│  message_handler.handle_new_result(SpinInput):                       │
│    - GameState SINGLETON (game_state global)                         │
│    - strategy SINGLETON                                              │
│    - state_lock GLOBAL                                               │
│    - persiste em SQLite (data/decisions.db) — FONTE DA VERDADE       │
│    - opcional: outbox → Postgres (dual_write_pg=false default)       │
│        cw.spin_features  (provider, table, dealer, round_id)         │
│        ccw.spin_features (provider, table, dealer, round_id)         │
│        shared.dealers    (UNIQUE(name, provider, table))             │
└──────────────────────────────────────────────────────────────────────┘
```

**4 fatos críticos:**

1. Cliente é **mono-mesa**: 1 JSON ⇒ 1 sessão. Trocar de site exige carregar outro JSON.
2. Servidor **JÁ É multi-provider em dados**, mas é **mono-mesa em runtime**
   (game_state singleton, state_lock global). Multi-mesa simultânea exige refator.
3. Não há **catálogo persistido** de mesas, providers ou manifests.
4. Descoberta de provider é **manual** e frágil. `deal_capture.js` tem
   `PROVIDER_SELECTORS` hardcoded mas não é catálogo extensível.

---

## 3. Auditoria da proposta original — 20 achados

Esta seção lista os bugs/melhorias encontrados ao revisar criticamente a proposta de
federação apresentada na sessão. **Cada item recebe severidade e tratamento na seção 6.**

### Críticos (bloqueiam Sprint 1 se não corrigidos)

| # | Achado | Severidade | Fix endereçado em |
|---|---|---|---|
| C-01 | **Servidor é singleton** (`game_state`, `MessageHandler`, `state_lock`). Multi-mesa simultânea **não funciona** sem refator de session-per-mesa. | 🔴 CRÍTICO | Sprint 4 (ServerSessionRegistry) |
| C-02 | **popup.js valida formato pelo `_meta.service === 'ExtractorBeat'`** (linha 171). Renomear arquivo é seguro; alterar `_meta.service` quebra. | 🔴 CRÍTICO | Sprint 1 (preservar _meta.service) |
| C-03 | **shared.tables não existe** em SQLite local. Migration 0009 sozinha só serve para Postgres (dual_write_pg OFF por default). Precisa criar em ambos. | 🔴 CRÍTICO | Sprint 3 (sqlite_repo auto-migra) |
| C-04 | **executeScript em `chrome://`/`about:`** lança exceção silenciosa. Provider router rodando em onUpdated precisa filtrar URLs inválidas antes de probe. | 🔴 CRÍTICO | Sprint 1 (router filtra URLs) |
| C-05 | **URL da tab ≠ URL do iframe Evolution.** Auto-discovery por urlPatterns precisa rodar dentro dos iframes (allFrames:true), não só na tab principal. | 🔴 CRÍTICO | Sprint 1 (router multi-frame) |

### Altos (devem ser corrigidos antes da Sprint 3)

| # | Achado | Severidade | Fix endereçado em |
|---|---|---|---|
| A-01 | **CI vermelho**: `tests/test_cdc_worker.py` falha desde 27/05 por falta de `alembic upgrade head`. Migration 0009 não passa pela pipeline. | 🟠 ALTO | Sprint 0 (saneamento CI) |
| A-02 | **SpinInput.provider opcional** hoje; tornar obrigatório quebra clientes antigos. Precisa janela de coexistência + telemetria. | 🟠 ALTO | Sprint 3 (canary + deprecation) |
| A-03 | **shared.dealers** UNIQUE(name, provider, table) já existe, mas `dealer_offset` agrega cross-provider. Multi-provider exige particionar por provider. | 🟠 ALTO | Sprint 6 (strategy router) |
| A-04 | **chrome.storage.local limite ~5MB sync, ~10MB unlimited**. N manifests bundled + sessionData por aba pode estourar. | 🟠 ALTO | Sprint 1 (storage budget) |
| A-05 | **SPA navigation** (cassino single-page): tab.url muda sem disparar onUpdated com novo URL completo. Provider detection deve usar `webNavigation.onHistoryStateUpdated`. | 🟠 ALTO | Sprint 2 (SPA-aware discovery) |
| A-06 | **Race em shared.tables**: 2 spins simultâneos da mesma mesa pela 1ª vez geram conflict. SQLite precisa `INSERT OR IGNORE`; Postgres `ON CONFLICT DO NOTHING`. | 🟠 ALTO | Sprint 3 (upsert idempotente) |
| A-07 | **Migração de dados existentes**: ao criar `shared.tables`, decisions tem ~milhões de linhas sem `table_canonical_id`. Backfill obrigatório com lock janela curta. | 🟠 ALTO | Sprint 3 (backfill script) |

### Médios (refinam a entrega mas não bloqueiam)

| # | Achado | Severidade | Fix endereçado em |
|---|---|---|---|
| M-01 | **manifest_hash sem source-of-truth**: se operador edita JSON localmente, hash diverge do catálogo central. Precisa flag `manifest_origin = local|remote`. | 🟡 MÉDIO | Sprint 5 (CDN) |
| M-02 | **Sem replay determinístico** de decisões antigas: qual manifest_hash estava em vigor quando spin X foi tomado? `decisions.manifest_hash` precisa ser FK. | 🟡 MÉDIO | Sprint 3 (event-sourcing audit) |
| M-03 | **Provider capability flags ausentes**: algumas mesas Evolution tem turbo, betShield, etc. Manifest deve declarar features para estratégia decidir. | 🟡 MÉDIO | Sprint 6 (capabilities) |
| M-04 | **Sem kill-switch por provider**: desabilitar Pragmatic em produção exige rebuild. Feature flag remota seria mais ágil. | 🟡 MÉDIO | Sprint 5 (CDN flags) |
| M-05 | **Strategy router por provider não desenhado** — SDA17 é otimizada para Evolution. Cada provider pode ter estratégia distinta. | 🟡 MÉDIO | Sprint 6 (strategy registry) |

### Baixos (qualidade/observabilidade)

| # | Achado | Severidade | Fix endereçado em |
|---|---|---|---|
| L-01 | **Sem provider health metrics**: Prometheus precisa de gauge `spins_per_provider_per_minute`. | 🟢 BAIXO | Sprint 4 |
| L-02 | **Sem dry-run mode** no provider router: difícil debugar por que detectou X em vez de Y. | 🟢 BAIXO | Sprint 2 |
| L-03 | **Manifests sem JSON Schema**: validação manual no popup quebra fácil. Ajv + schema canônico tira o subjetivismo. | 🟢 BAIXO | Sprint 1 |

**Resultado da auditoria:** 5 críticos, 7 altos, 5 médios, 3 baixos = **20 itens**.
Justifica adicionar uma **Sprint 0 de saneamento** antes da Sprint 1.

---

## 3.5 Auditoria da auto-detecção & zero-upload — 10 novos achados

> Esta auditoria nasce da pergunta do operador: *"ao clicar no ícone eu tenho que
> fazer upload do JSON e iniciar; a Escuta não poderia identificar sozinha qual
> roleta está rodando e afinar a federação automaticamente?"* — **Sim, pode** (ver
> §4.9), mas tirar o operador do loop introduz uma nova classe de riscos. São 10
> achados **novos** (NB = New-Behaviour), além dos 20 acima.

| # | Achado | Severidade | Tratamento | Sprint |
|---|---|---|---|---|
| NB-01 | **`content_scripts: <all_urls>`** roda `deal_capture.js`+`content.js` em **todo** site (banco, e-mail, etc.). Privacidade, performance e **risco de reprovação na Chrome Web Store** (revisão MV3 penaliza host amplo). Auto-detecção amplia a exposição. | 🔴 CRÍTICO | Trocar por `declarativeContent` (acende ícone só em cassino) + injeção programática **pós-detecção**; estreitar `matches` para domínios conhecidos. | 2 |
| NB-02 | **Auto-start sem consentimento**: se a extensão detecta sozinha, **não pode iniciar a escuta/apostas sozinha** — risco de operar a mesa errada ou apostar sem intenção. | 🔴 CRÍTICO | Detecção é automática; **iniciar exige 1 clique** (ou opt-in explícito por provider, persistido). | 2 |
| NB-03 | **Falso-positivo de detecção**: agregador embute Evolution+Pragmatic no mesmo DOM, ou white-label parece outro provider → empate de confidence. | 🟠 ALTO | Exigir **margem mínima** entre 1º e 2º colocado; sem margem → `unknown` + pedir override ao operador. | 2 |
| NB-04 | **Custo de detecção por tick**: rodar o classificador a cada alarme desperdiça CPU e pode disputar com a leitura de resultados. | 🟠 ALTO | Detectar **1×/aba**, cachear por `tabId`, invalidar só em navegação (SPA-aware). | 2 |
| NB-05 | **Integridade do manifest OTA**: CDN comprometido injeta seletores maliciosos que **exfiltram o DOM** do operador (selectors são código que lê a página). | 🟠 ALTO | **Assinatura Ed25519 obrigatória** antes da Sprint 5 ir a campo; chave pública *pinada* no código; nunca executar manifest não-verificado. | 5 |
| NB-06 | **Version skew**: manifest empacotado × manifest do CDN × schema que o servidor espera podem divergir silenciosamente. | 🟡 MÉDIO | Negociar `schema_version`; servidor avisa/rejeita incompatível; popup sinaliza. | 5 |
| NB-07 | **Self-heal promove seletor errado** que casou por acaso → polui os dados de produção. | 🟡 MÉDIO | Promover fallback só após **N ticks consecutivos** + validação de formato (número 0-36); promoção reversível + telemetria. | 2 |
| NB-08 | **Storage budget**: bundle de N manifests + cache do CDN + histórico por aba pode estourar `chrome.storage` (amplia A-04). | 🟡 MÉDIO | `getBytesInUse()` + GC de manifests/sessões antigas. | 1 |
| NB-09 | **Iframe cross-origin sandboxed** sem `allow-same-origin` → `executeScript` falha naquele frame e pode abortar a detecção inteira. | 🟢 BAIXO | Tratar erro **por frame**; detecção tolera frames inacessíveis. | 2 |
| NB-10 | **Privacidade da telemetria de drift**: reportar conteúdo do DOM ao servidor vaza dados do operador. | 🟢 BAIXO | Enviar só **hit/miss booleano + hash do seletor**, nunca o conteúdo capturado. | 2/5 |

**Resultado:** 2 críticos, 3 altos, 3 médios, 2 baixos = **10 novos itens**. Os dois
críticos (NB-01, NB-02) são **pré-condição da auto-detecção** — entram na Sprint 2 e
não podem ser adiados.

---

## 4. Arquitetura-alvo (atualizada pós-auditoria)

### 4.1 Camadas

```
┌─ L6 UI Multi-mesa ────────────────────────────────────────────┐
│   Popup mostra abas ativas × providers detectados             │
│   1 operador, N mesas simultâneas                              │
└────────────────────────────────────────────────────────────────┘
┌─ L5 Manifest Distribution ────────────────────────────────────┐
│   Bundled na extensão (MVP) → Git+CDN auto-update (V2)        │
│   Feature flags remotas (kill-switch por provider)            │
└────────────────────────────────────────────────────────────────┘
┌─ L4 Server Session Registry  ★NOVO pós-auditoria★ ────────────┐
│   1 GameState POR (provider, raw_table_id) — não mais global  │
│   state_lock por sessão                                       │
│   ServerSessionRegistry { (provider, table) → GameState }     │
└────────────────────────────────────────────────────────────────┘
┌─ L3 Catálogo de mesas (SQLite + Postgres) ────────────────────┐
│   shared.tables UNIQUE(provider, raw_table_id)                │
│   decisions.table_canonical_id + decisions.manifest_hash      │
│   Replay determinístico via manifest_hash                     │
└────────────────────────────────────────────────────────────────┘
┌─ L2 Provider Router + Auto-Discovery (Client) ────────────────┐
│   Input: tab.url + DOM signals (allFrames)                    │
│   Output: { providerId, manifest, confidence }                │
│   Cache por tabId + invalidação em SPA navigation             │
└────────────────────────────────────────────────────────────────┘
┌─ L1 Provider Manifest Registry (Client) ──────────────────────┐
│   extension/providers/{index, _schema, evolution, ...}.json   │
│   Schema canônico Ajv-validable                               │
│   _meta.service = 'ExtractorBeat' preservado p/ retro-compat  │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 Schema canônico do manifest (proposta)

```json
{
  "_meta": {
    "service": "ExtractorBeat",
    "manifest_schema": "1.0.0",
    "provider_id": "evolution",
    "version": "18.2.0",
    "issued_at": "2026-06-14T20:00:00Z",
    "manifest_hash": "sha256:..."
  },
  "_detection": {
    "urlPatterns": ["*://*.evo-games.com/*"],
    "domSignals": [
      { "selector": "[class*='evolutionLogo']", "minMatches": 1, "weight": 5 }
    ],
    "metaTags": [{ "name": "provider", "valuePattern": "evolution|evo-games" }],
    "minConfidence": 0.6
  },
  "_capabilities": {
    "supports_turbo": true,
    "supports_dealer_capture": true,
    "supports_round_id": true,
    "min_polling_ms": 750
  },
  "data": {
    "results":    { "selector": "[data-role='recent-number']", "fallbackSelectors": [...] },
    "monitoring": { ... },
    "session":    { "dealer":{"name":{...}}, "round":{"id":{...}}, "table":{"name":{...}} },
    "betSpots":   { ... }
  }
}
```

### 4.3 Schema do servidor (mudanças propostas)

```sql
-- Migration 0009
CREATE TABLE shared.tables (
  id              SERIAL PRIMARY KEY,
  provider        TEXT NOT NULL,
  raw_table_id    TEXT NOT NULL,
  canonical_id    TEXT GENERATED ALWAYS AS (provider || ':' || raw_table_id) STORED,
  display_name    TEXT,
  first_seen      TIMESTAMP DEFAULT NOW(),
  last_seen       TIMESTAMP DEFAULT NOW(),
  meta            JSONB DEFAULT '{}',
  UNIQUE(provider, raw_table_id)
);

CREATE TABLE shared.manifests (
  hash            TEXT PRIMARY KEY,           -- sha256 do JSON canonicalizado
  provider        TEXT NOT NULL,
  version         TEXT NOT NULL,
  schema_version  TEXT NOT NULL,
  issued_at       TIMESTAMP NOT NULL,
  body            JSONB NOT NULL,
  origin          TEXT NOT NULL DEFAULT 'local'  -- 'local' | 'cdn'
);

ALTER TABLE cw.spin_features  ADD COLUMN table_canonical_id TEXT, ADD COLUMN manifest_hash TEXT;
ALTER TABLE ccw.spin_features ADD COLUMN table_canonical_id TEXT, ADD COLUMN manifest_hash TEXT;
```

E em SQLite mirror (auto-migrate em `sqlite_repo.py`, padrão SP-13/SP-16):
```sql
ALTER TABLE decisions ADD COLUMN table_canonical_id TEXT;
ALTER TABLE decisions ADD COLUMN manifest_hash TEXT;
CREATE TABLE IF NOT EXISTS tables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  raw_table_id TEXT NOT NULL,
  display_name TEXT,
  first_seen TEXT DEFAULT (datetime('now')),
  last_seen TEXT DEFAULT (datetime('now')),
  meta TEXT DEFAULT '{}',
  UNIQUE(provider, raw_table_id)
);
```

---

## 4.5 Auditoria UX — Jornada do usuário (HOJE × PROPOSTO)

Esta seção mapeia **passo a passo** o que o operador vê desde abrir um site de cassino
até o final da sessão de escuta. Cada etapa lista:
- **O que ele vê HOJE** (estado atual v3.2.0)
- **Pain points encontrados** (referenciados em 4.6)
- **O que ele veria PROPOSTO** (após sprints 1-7)
- **Sprints responsáveis** pela melhoria

### Etapa A — Abertura do navegador / chegada ao site

| | HOJE | PROPOSTO |
|---|---|---|
| **Sinais visuais** | Badge da extensão sem cor/contador | Badge mostra `0` (nenhuma mesa ativa) ou `2` (2 sessões); ícone fica colorido por provider detectado na aba ativa |
| **Notificações** | Nenhuma. Operador não sabe se o site é compatível antes de abrir o popup | Toast opcional (config): "Evolution detectado nesta aba — clique no ícone para iniciar" |
| **Detecção de provider** | Nada acontece até clicar no popup e fazer upload | `webNavigation.onCommitted` dispara `provider_router` no carregamento; cache em `chrome.storage.session` por tabId |
| **Pain points** | PP-01, PP-02 | — |
| **Sprints** | — | 2 (router), 7 (badge) |

### Etapa B — Clica no ícone da extensão (abre popup 500px)

| | HOJE | PROPOSTO |
|---|---|---|
| **Top** | `👂 ESCUTA BEAT` + sub `v2.5 - Detecção de Status Aprimorada` (versão ERRADA: está em v3.2.0) | `👂 ESCUTA BEAT` + sub `v3.2.0` puxado de `manifest.json` (sempre coerente) |
| **Status conexão** | "Conectando..." → "✅ CONECTADO" + URL da tab ATUAL (não da tab que está escutando) | "Conectado a 1 aba" + "👂 Escutando 2 mesas em background" |
| **Dropdown mesa** | Sempre vazio "Carregando mesas..." → fica vazio (servidor mesa_configurada offline) | Removido (substituído pela lista de sessões) |
| **Aviso** | "⚠️ SERVIDOR OFFLINE? USE O MODO MANUAL" (FALSO — servidor está online, só esse caminho não está em uso) | Removido. Modo manual vira opção secundária em "Avançado" |
| **Botão upload** | `📂 CARREGAR ARQUIVO DO EXTRATOR BEAT` (obrigatório toda vez) | Auto-detecta manifest do provider. Botão "Carregar manifest customizado..." só em modo avançado |
| **Botão iniciar** | `▶️ INICIAR ESCUTA` (disabled até carregar JSON) | Habilita assim que provider for detectado na aba ativa |
| **Pain points** | PP-01, PP-03, PP-06, PP-15, PP-18 | — |
| **Sprints** | — | 1, 2, 7 |

### Etapa C — Lista de "mesas detectadas" (NOVO)

**HOJE**: não existe. Operador precisa decorar/anotar qual JSON pertence a qual tab.

**PROPOSTO (Sprint 7)**:
```
┌──────────────────────────────────────────────────────────────┐
│  👂 Mesas Detectadas (3)                       [⏹️ PARAR TUDO] │
├──────────────────────────────────────────────────────────────┤
│  🟢 ESCUTANDO ─ Evolution Gaming      🕐 12:34 (47 spins)    │
│      "Roleta ao Vivo"  •  Maria  •  Round #1234567           │
│      Aba 13892  •  manifest v18.2.0 (local)                  │
│      [⏸️ Pausar] [⏹️ Parar] [⚙️]                              │
├──────────────────────────────────────────────────────────────┤
│  🔵 DETECTADA  ─ Pragmatic Play                              │
│      "Auto Roulette VIP"  •  ?                               │
│      Aba 14001  •  manifest v1.0.0 (cdn)                     │
│      [▶️ ESCUTAR]                                             │
├──────────────────────────────────────────────────────────────┤
│  ⚪ DESCONHECIDO ─ ?                                          │
│      "Live Casino"  •  Aba 14123                             │
│      Nenhum provider casou. [📂 Configurar manualmente...]    │
└──────────────────────────────────────────────────────────────┘
```

| **Vantagens** | |
|---|---|
| Operador vê **todas as mesas** que podem ser escutadas | Sem precisar trocar de aba |
| **Provider e manifest** visíveis | Elimina confusão "qual JSON é esse?" |
| **Dealer e round atual** visíveis | Validação imediata de captura |
| **Origem do manifest** (local/cdn) | Auditoria visual |
| **Pause/Parar por mesa** | Independência total entre sessões |

**Pain points endereçados**: PP-02, PP-04, PP-08, PP-13, PP-14, PP-16
**Sprints**: 2 (detecção), 4 (sessões independentes), 7 (UI)

### Etapa D — Iniciar escuta de uma mesa (clicar `▶️ ESCUTAR`)

| | HOJE | PROPOSTO |
|---|---|---|
| **Confirmação** | Nenhuma. Clica e já vai. Se errou a aba, perde dados | Modal "Confirmar nova sessão": mostra mesa, provider, manifest hash, frame ativo. Botões [Iniciar] [Cancelar] |
| **Feedback inicial** | "✅ Escuta iniciada! Pode fechar o popup." | Linha da mesa muda para 🟢 pulsante + timer "00:00:05" + contador de spins crescendo |
| **Background dormindo** | "⚠️ Background dormindo, alarm vai acordar em até 30s" (péssima UX, parece bug) | "⏳ Inicializando..." (3s) → "✅ Capturando" (sem expor implementação MV3) |
| **Notificação fora do popup** | Nenhuma. Operador esquece que está escutando | Badge da extensão pisca por 2s + número de mesas ativas (`2`) |
| **Pain points** | PP-08, PP-16, PP-17 | — |
| **Sprints** | — | 2, 4, 7 |

### Etapa E — Operador joga / acompanha overlay na página

| | HOJE | PROPOSTO |
|---|---|---|
| **Overlay header** | "⏳ AGUARDANDO" → "🟢 ABERTO" / "🔴 FECHADO" + Último número | Mesmo + badge provider colorido (verde EVO / azul PRAG) + dealer name inline |
| **Mudança de dealer** | Botão 🔄 manual ("Nova Sessão (Novo Dealer)") — operador precisa lembrar | **Auto-detecta** (já temos extractSessionData!): toast "Novo dealer: João — Resetar contadores? [Sim/Não/Sempre]" |
| **Pause durante intervalo** | Não existe; ou para tudo ou continua | Botão [⏸️ Pausar 5min] no overlay, retoma sozinho |
| **Confidence/Aposta** | Mostrado em região do overlay | Mantido idêntico |
| **Pain points** | PP-05, PP-12 | — |
| **Sprints** | — | 2 (session capture), 7 (auto-prompt) |

### Etapa F — Operador volta ao popup durante a sessão

| | HOJE | PROPOSTO |
|---|---|---|
| **Status atual** | Recarrega tudo do `chrome.storage.local.escutaState`; pode mostrar dados desatualizados se SW estava dormindo | Pull em tempo real do SW via `chrome.runtime.sendMessage('getActiveSessions')` |
| **Múltiplas mesas** | Não existe — só vê 1 aba ativa | Lista da Etapa C atualizada; sortable por spins/tempo |
| **Logs** | 30 entradas max, mais recentes em cima | 100 entradas + filtro por mesa + "exportar sessão" (JSON com timeline completa) |
| **Pain points** | PP-10, PP-14, PP-15 | — |
| **Sprints** | — | 4, 7 |

### Etapa G — Parar escuta (fim da sessão)

| | HOJE | PROPOSTO |
|---|---|---|
| **Botão** | `⏹️ PARAR ESCUTA` único (para a única mesa ativa) | `[⏹️]` por mesa + `[⏹️ PARAR TUDO]` global (confirma se >1 ativa) |
| **Confirmação** | Nenhuma — clica e para | Modal só se sessão tem >50 spins: "Encerrar sessão de 247 spins na 'Roleta ao Vivo'? [Sim/Não/Exportar antes]" |
| **Resumo final** | Nenhum. Operador não vê o que aconteceu | Card: total spins, hit rate, P&L estimado, dealer principal, duração; botão "Exportar JSON" |
| **Persistência** | sessionData zera; histórico no servidor mas sem visibilidade | Última sessão fica visível em "Histórico" (5 últimas) |
| **Pain points** | PP-04, PP-08 | — |
| **Sprints** | — | 4, 7 |

### Etapa H — Operador instala extensão pela primeira vez (onboarding)

**HOJE**: nenhum onboarding. Operador instala, clica no ícone, vê popup com dropdown vazio,
botão de upload, mensagem de "servidor offline" e precisa decifrar sozinho.

**PROPOSTO (Sprint 7)**:
1. Tela de boas-vindas (chrome-extension://.../onboarding.html abre em nova tab)
2. Tour de 3 passos:
   - "1. Abra a aba do seu cassino favorito"
   - "2. A Escuta detecta o provider automaticamente (Evolution, Pragmatic...)"
   - "3. Clique [▶️ Escutar] na mesa que você quer acompanhar"
3. Botão "Configurar manifests avançados" (oculto por padrão)
4. Link "Como funciona?" → docs em GitHub

**Sprints**: 7

---

## 4.6 Pain Points consolidados (20 PPs)

Severidade: 🔴 crítico (bloqueia uso multi-mesa) • 🟠 alto (frustração diária)
• 🟡 médio (recoverable) • 🟢 baixo (qualidade)

| # | Pain Point | Severidade | Origem | Sprint que resolve |
|---|---|---|---|---|
| PP-01 | Mensagem "⚠️ SERVIDOR OFFLINE" é falsa — confunde diagnóstico | 🟠 alto | popup.html:524 | 1 (remover msg) |
| PP-02 | Operador não sabe qual JSON corresponde a qual site — risco de carregar errado | 🔴 crítico | UX inteira | 2 (auto-detect) |
| PP-03 | Dropdown "Mesa Configurada no Servidor" sempre vazio confunde | 🟠 alto | popup.html:512 | 1 (ocultar se vazio) |
| PP-04 | Após iniciar, info-box mostra só "Arquivo Manual Carregado" — perde contexto | 🟠 alto | popup.js:373 | 7 (provider + table inline) |
| PP-05 | Mudança de dealer exige clique MANUAL em 🔄 no overlay | 🟠 alto | content.js:62 | 2 (auto-detect via extractSessionData) |
| PP-06 | Sub-título "v2.5" no popup está obsoleto (manifest v3.2.0) | 🟡 médio | popup.html:496 | 1 (auto-puxar de manifest.json) |
| PP-07 | "Direção do Giro" alterna automaticamente E aceita override — UX ambígua | 🟡 médio | popup.html:545 | 7 (UI revisão) |
| PP-08 | Sem indicador FORA do popup que escuta está ativa | 🟡 médio | manifest.json:16 | 7 (badge dinâmico) |
| PP-09 | File picker pede arquivo toda vez, sem histórico | 🟡 médio | popup.js:152 | 1 (lembrar último) |
| PP-10 | Logs limitados a 30 entradas no popup | 🟡 médio | popup.js:238 | 7 (100 + filtro) |
| PP-11 | Botão "Exportar Logs (Debug)" sempre visível | 🟢 baixo | popup.html:540 | 7 (modo dev) |
| PP-12 | Overlay tem botão "🎛️ Controles" duplicando popup | 🟢 baixo | content.js:92 | 7 (consolidar) |
| PP-13 | Sem feedback "manifest desatualizado" | 🟡 médio | — | 5 (CDN check) |
| PP-14 | 1 popup = 1 aba ativa — multi-mesa exige reabrir popup | 🔴 crítico | popup.js:288 | 7 (lista multi-mesa) |
| PP-15 | `connectToTab()` mostra info da aba ativa do browser, não da que está escutando | 🔴 crítico | popup.js:288 | 7 (track per-tab) |
| PP-16 | Sem confirmação ao iniciar — multi-tab vira loteria | 🔴 crítico | popup.js:558 | 7 (modal confirm) |
| PP-17 | Msg "Background dormindo, alarm acorda em 30s" parece bug | 🟡 médio | popup.js:566 | 7 (esconder detalhe MV3) |
| PP-18 | Connection URL truncada não ajuda identificar mesa | 🟢 baixo | popup.html:504 | 7 (display_name + provider) |
| PP-19 | Traffic light fica "AGUARDANDO" até primeiro spin — parece quebrado | 🟡 médio | popup.html:570 | 7 (estado inicial claro) |
| PP-20 | "R$ 0,00" inicial confunde com "perdeu tudo" | 🟢 baixo | popup.html:578 | 7 (placeholder "—") |

**Resumo:** 4 críticos (todos em multi-mesa), 5 altos, 7 médios, 4 baixos = **20 PPs UX**.
Combinados com os 20 achados técnicos da seção 3, totalizam **40 itens de auditoria**.

---

## 4.7 Wireframes textuais — Popup proposto (Sprint 7)

### Tela principal (3 mesas detectadas, 1 escutando)

```
┌─────────────────────────────────────────────────────────────┐
│  👂 ESCUTA BEAT                              v3.5.0 [⚙️]    │
│  ─────────────────────────────────────────────────────────  │
│  🟢 1 mesa escutando · 2 mesas detectadas                   │
│                                          [⏹️ PARAR TUDO]    │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  🟢 ESCUTANDO   Evolution Gaming          🕐 12:34 ─ 47 sp  │
│     Roleta ao Vivo · Maria · Round #1234567                 │
│     Saldo R$ 1.247,00 · Última: [21]                        │
│     [⏸️] [⏹️] [📋 Logs] [⚙️]                                 │
│                                                              │
│  🔵 DETECTADA   Pragmatic Play                              │
│     Auto Roulette VIP · manifest v1.0.0 (CDN)               │
│     [▶️ ESCUTAR]  [⚙️]                                       │
│                                                              │
│  ⚪ DESCONHECIDO                                              │
│     Aba: cassino.com.br/live/...                            │
│     Nenhum provider casou. [📂 Configurar manifest...]       │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│  Direção: ⬅️ Horário (auto, clique pra fixar)               │
└─────────────────────────────────────────────────────────────┘
```

### Modal de confirmação (Sprint 7)

```
┌──────────────────────────────────────┐
│  Iniciar nova sessão                 │
│  ──────────────────────────────────  │
│  Provider:   Evolution Gaming        │
│  Mesa:       Roleta ao Vivo          │
│  Frame:      a8-latam.evo-games.com  │
│  Manifest:   evolution.json v18.2.0  │
│  Origem:     local (bundled)         │
│  Confidence: 95%                     │
│                                       │
│  [Cancelar]      [▶️ Iniciar]         │
└──────────────────────────────────────┘
```

### Modal de mudança de dealer (Sprint 2+7)

```
┌──────────────────────────────────────┐
│  🎰 Novo dealer detectado            │
│  ──────────────────────────────────  │
│  Anterior:  Maria  (47 spins)        │
│  Novo:      João                     │
│                                       │
│  [ ] Resetar contadores              │
│  [ ] Salvar este turno (export)      │
│  [ ] Sempre perguntar (config)       │
│                                       │
│  [Ignorar]      [Resetar Sessão]     │
└──────────────────────────────────────┘
```

---

## 4.8 Mudanças de modelo mental — operador

| Antes | Depois |
|---|---|
| "Tenho que carregar o JSON certo pro site certo" | "Abro o site, a Escuta sabe o que fazer" |
| "Só posso escutar 1 mesa por vez" | "Acompanho N mesas em paralelo no painel" |
| "Quando muda o dealer, esqueci de clicar 🔄" | "A Escuta avisa e pergunta o que fazer" |
| "Onde está meu JSON?" | "Manifests vêm prontos com a extensão (e ficam atualizados)" |
| "Servidor offline? Manual? O que está rolando?" | "Status claro: escutando, pausado, desconhecido, erro" |
| "Não sei se ainda está escutando" | "Badge da extensão sempre mostra N mesas ativas" |

---

## 4.9 Auto-detecção & Zero-Upload — arquitetura e tecnologia

> **Pergunta do operador**: *"Hoje clico no ícone, faço upload do JSON e clico em
> iniciar. A Escuta não poderia identificar sozinha qual roleta está rodando e fazer
> o sensoriamento / fine-tuning da federação automaticamente? Qual a melhor
> tecnologia para isso?"*

### 4.9.1 Resposta curta

**Sim — e a extensão já tem TODAS as permissões necessárias para isso hoje.** O upload
manual **não** é uma limitação técnica; é uma limitação de *design*. Provas no código atual:

| Capacidade necessária p/ auto-detecção | Já existe? | Onde |
|---|---|---|
| Acesso ao DOM de qualquer cassino | ✅ | `manifest.json` → `host_permissions: ["<all_urls>"]` |
| Rodar código em todos os frames (iframe Evolution) | ✅ | `background.js:490` `executeScript({allFrames:true})` |
| Injeção programática com config dinâmica | ✅ | `background.js:1184` `func + args:[sessionConfig]` |
| Content scripts já presentes em toda página | ✅ | `manifest.json` `content_scripts` (`deal_capture.js`, `content.js`) |
| Ler manifest sem perguntar ao operador | ❌ | **único elo faltante** — hoje vem de `<input type=file>` (`popup.js:145`) |

Ou seja: **o JSON só precisa de upload porque é lido de um seletor de arquivo.** Se ele
for **empacotado na extensão** (e atualizado por um canal remoto), o passo "upload"
desaparece e o passo "iniciar" vira opcional (1 clique de consentimento).

### 4.9.2 De onde para onde

```
HOJE   ► clicar ícone ► [upload manual do JSON] ► escolher mesa ► [clicar Iniciar] ► escuta
                         └── 60-90 s, sujeito a erro (JSON errado) ──┘

ALVO   ► abrir o site ► (extensão detecta provider+mesa sozinha) ► popup já mostra
         "Evolution · Auto-Roulette · dealer João · confiança 0.92  [▶️ Escutar]"
                         └── <3 s, 1 clique de consentimento ──┘
```

### 4.9.3 A stack recomendada (a "melhor tecnologia")

São **quatro tecnologias** combinadas; nenhuma exige reescrever a extensão.

**1. Detecção = classificador de fingerprint ponderado (regra-baseado, estilo Wappalyzer)**
- Sinais, com pesos, agregados em um *score* de confiança por provider:
  - **URL** da aba + URLs dos **iframes** vs `_detection.urlPatterns` (peso alto — sinal mais barato e estável)
  - **DOM fingerprint**: presença de seletores/classes únicas do *skin* (peso médio)
  - **Meta tags / `<link>` / JS globals** (`window.evolution`, `window.PpGames`...) (peso médio)
- `confidence = Σ(peso×match) / Σpesos`; escolhe o **argmax** se ≥ `minConfidence` **e** com
  margem mínima sobre o 2º colocado (NB-03). Sem isso → `unknown` + override manual.
- **Por que regra-baseado e não ML/visão computacional?** Determinístico, *debugável*
  (dá pra explicar por que detectou X), latência ~0, **sem dados de treino**, e
  extensível **editando um JSON** — qualquer operador adiciona um provider sem recompilar.
  ML/embedding de DOM fica como *fallback* futuro só para páginas `unknown`.
- **Referência madura**: o banco de regras open-source do **Wappalyzer** usa exatamente
  esse modelo (URL + DOM + meta + JS, com confiança) para milhares de tecnologias.

**2. Zero-Upload = manifests empacotados + canal OTA**
- Manifests viram `web_accessible_resources` da extensão, lidos via
  `chrome.runtime.getURL('providers/evolution.json')` — **nenhum upload**.
- Atualizações chegam *over-the-air* de um repositório central (GitHub raw / CDN),
  cacheadas em `chrome.storage`, **assinadas Ed25519** (NB-05). O operador nunca toca no arquivo.

**3. Sensoriamento / fine-tuning = loop fechado de self-healing**
- Cada tick, o content script reporta **hit/miss por seletor** → o SW agrega um
  **"manifest health score"** por mesa.
- Quando o seletor primário falha por **N ticks**, a extensão **promove automaticamente**
  um `fallbackSelector` que esteja retornando dado **válido** (número 0-36) — *self-heal local* (NB-07).
- O *drift* (seletor que quebrou) é reportado ao servidor (**só hit/miss + hash**, nunca
  conteúdo — NB-10); o time/CDN publica o manifest corrigido; a extensão o baixa via OTA.
  **É esse loop que "afina a federação sozinha"** sem rebuild nem republicação na store.

**4. Ativação respeitando privacidade (corrige NB-01/NB-02)**
- Trocar `content_scripts: <all_urls>` por **`declarativeContent`** (acende o ícone só em
  domínio de cassino) + **injeção programática pós-detecção**. Melhora privacidade,
  performance e a chance de aprovação na Chrome Web Store (revisão MV3 penaliza host amplo).
- Detecção é automática; **iniciar a escuta continua exigindo 1 clique** (ou opt-in por
  provider) — nunca apostar/operar sem consentimento.

### 4.9.4 Tecnologias escolhidas × alternativas descartadas

| Camada | Escolha | Alternativa descartada | Por quê |
|---|---|---|---|
| Detecção | Fingerprint ponderado (JSON de regras) | Classificador ML / screenshot+visão | Determinismo, zero treino, extensível por não-dev |
| Distribuição | Bundle + OTA assinado (GitHub Pages/CDN) | Upload manual (atual) | Elimina o passo de upload; correção em horas |
| Validação | **Ajv** (JSON Schema 2020-12) | Validação ad-hoc no popup | Tira o subjetivismo; rejeita manifest inválido |
| Integridade | **Ed25519** (tweetnacl) | HTTPS "puro" | HTTPS não protege contra CDN/repo comprometido |
| Ativação | `declarativeContent` + injeção dinâmica | `content_scripts: <all_urls>` | Privacidade, perf e revisão da store |
| Self-heal | Promoção de fallback + telemetria hit/miss | Selectors fixos | Resiliência a mudança de layout do cassino |

### 4.9.5 Onde isso entra no roadmap

| Bloco da auto-detecção | Sprint |
|---|---|
| Empacotar manifests (1º passo do zero-upload, caso Evolution) | **1** |
| Motor de detecção + self-heal + `declarativeContent` + consentimento | **2** ← centro |
| OTA assinado + version negotiation (fecha o loop de fine-tuning) | **5** |

---

## 5. Sprints — objetivo, entregáveis, aceite

### Sprint 0 — **Saneamento (novo, pós-auditoria)** ⏱️ 1-2 dias

**🎯 Ganho**: pipeline confiável — toda mudança seguinte passa a ser validada por CI verde,
sem mascarar regressão. É o pré-requisito invisível que protege as 7 sprints seguintes.

**Objetivo**: destravar a pipeline antes de qualquer mudança estrutural.
A auditoria mostrou que CI está vermelho desde 27/05 (A-01) — adicionar migration sem
isso corre risco de mascarar regressões.

**🔧 O que fazer (entregáveis)**
- Fix `ci.yml`: rodar `alembic upgrade head` após bootstrap dos schemas
- Re-habilitar `tests/test_cdc_worker.py` (verde)
- Adicionar marca `[skipif: not provider_multi]` em testes que dependem de multi-provider
- Adicionar **manifesto de telemetria base**: gauge Prometheus
  `spins_per_provider_total{provider="evolution|unknown"}` para baseline
- Documentar `dual_write_pg` flag explicitamente (README do servidor)

**💡 Por que fazer**: sem CI verde, qualquer regressão introduzida nas Sprints 3-4
(que tocam persistência e runtime) passa despercebida. Custo 1-2 dias evita semanas
de depuração em produção.

**Critério de aceite**
- ✅ `gh run list -L 1` retorna green main
- ✅ Gauge `spins_per_provider_total` aparece em `/metrics`

**PPs UX endereçados**: nenhum (sprint puramente técnica).
**Risco**: 🟢 baixo. Não toca runtime de produção.

---

### Sprint 1 — **Foundation: Provider Registry + manifests empacotados** ⏱️ 2-3 dias

**🎯 Ganho**: **fim do upload manual no caso Evolution** — o manifest passa a vir
empacotado na extensão e é carregado sozinho. É o **primeiro passo concreto do
zero-upload** (§4.9): o operador deixa de procurar/arrastar o JSON. Ainda limpa 4 pain
points enganosos do popup logo no começo do roadmap.

**Objetivo**: criar a estrutura de manifests federados **sem mudar o comportamento de
runtime**, mas já **eliminando o upload** no fluxo Evolution. O JSON vira parte de um
registry extensível, empacotado e validado.

**🔧 O que fazer (entregáveis)**
- Criar `extension/providers/` com:
  - `_schema.json` (JSON Schema do manifest canônico, draft 2020-12)
  - `evolution.json` (= conteúdo atual de `extrator_completo.json`, refatorado para o schema canônico)
  - `index.json` (lista de providers + version + path)
- **Empacotar como `web_accessible_resources`** no `manifest.json` e carregar via
  `chrome.runtime.getURL('providers/evolution.json')` no boot do popup/SW — **zero upload**
  para Evolution. O `<input type=file>` vira apenas *fallback manual* (operador avançado).
- Símbolo de compat: `extrator_completo.json` na raiz continua existindo como wrapper que
  aponta para `providers/evolution.json` (popup continua aceitando o nome antigo) (C-02)
- Validação Ajv no boot e ao carregar arquivo: rejeita manifests inválidos com erro claro (L-03)
- **PRESERVAR** `_meta.service = 'ExtractorBeat'` (C-02)
- Criar `extension/provider_router.js` (stub) que sempre retorna `{providerId:'evolution'}`
  — apenas para virar ponto de extensão da Sprint 2
- **Storage budget**: telemetria `chrome.storage.local.getBytesInUse()` + GC de manifests
  antigos no popup (NB-08, A-04)
- **UX cleanup quick-wins**:
  - Remover mensagem "⚠️ SERVIDOR OFFLINE? USE O MODO MANUAL" (PP-01)
  - Ocultar dropdown "Mesa Configurada no Servidor" se vier vazio (PP-03)
  - Sub-título do header passa a ler `chrome.runtime.getManifest().version` (PP-06)
  - Substituir "Carregar JSON" por "✅ Evolution carregado automaticamente (v18.2)" quando
    o bundle resolve sozinho; manter "Trocar manifest…" discreto (PP-09)
- Testes: 6 novos em `tests/test_manifest_registry.py`
  - Schema canônico parseável por Ajv
  - evolution.json valida contra schema
  - index.json tem todos os providers listados
  - popup aceita formato novo + formato antigo (smoke)
  - **bundle resolve sem upload** (mock `getURL`)
  - provider_router retorna evolution para fallback

**💡 Por que fazer**: o upload é a maior fricção do fluxo atual (60-90 s + risco de JSON
errado, PP-02). Empacotar o manifest mata essa fricção para o provider que representa
~100% do uso hoje, e cria a fundação (`providers/` + schema + router-stub) sobre a qual a
Sprint 2 liga a detecção automática. Sem alterar runtime, o risco é mínimo.

**Critério de aceite**
- ✅ Abrir `evo-games.com` e o popup já mostra "Evolution carregado" **sem upload**
- ✅ `<input file>` antigo ainda funciona como fallback manual
- ✅ Schema (Ajv) rejeita manifest sem `_meta.service`
- ✅ 21+ testes (suite atual) + 6 novos = todos verde
- ✅ Operador NÃO vê mais "Servidor offline" se servidor está conectado

**PPs UX endereçados**: PP-01, PP-03, PP-06, PP-09 (+ ataca a raiz de PP-02)
**Achados endereçados**: C-02, L-03, A-04, NB-08
**Risco**: 🟢 baixo. Backward-compat preservado, sem alteração de runtime.

---

### Sprint 2 — **Auto-detecção (Zero-Upload) + Self-Heal + 2nd Provider** ⏱️ 5-7 dias

> **★ Sprint central do roadmap — é aqui que o upload manual morre.** Implementa a
> arquitetura da §4.9: a Escuta identifica sozinha qual roleta está rodando e começa a
> se auto-afinar. Escopo subiu de 3-5 para **5-7 dias** porque absorve os 2 achados
> críticos novos (NB-01, NB-02) e o self-heal.

**🎯 Ganho**: **o operador deixa de fazer upload e deixa de escolher "qual JSON".**
Abre o site → em <3 s o popup já diz *"Evolution · Auto-Roulette · confiança 0.92
[▶️ Escutar]"*. Funciona em N providers e degrada com elegância (pede override quando
não tem certeza). Selector que quebra se conserta sozinho (self-heal) sem operador perceber.

**Objetivo**: cliente detecta automaticamente **provider + mesa** a partir de URL/DOM/JS
da aba e seleciona o manifest empacotado correspondente — **sem upload**. Provar com
**1 segundo provider** (Pragmatic OU Playtech — decisão pendente).

**🔧 O que fazer (entregáveis)**

*Motor de detecção (`extension/provider_router.js` real):*
- Classificador de **fingerprint ponderado** (estilo Wappalyzer, §4.9.3):
  - Input: `tab.url` + URLs de **todos os frames** (probe `allFrames:true`) + sinais DOM/meta/JS
  - Score: URL match (peso 5) + DOM signal (peso 3) + metaTag/JS global (peso 2); `confidence = Σ/Σpesos`
  - **Margem mínima** entre 1º e 2º colocado; sem margem → `unknown` + override (NB-03)
  - **Filtra `chrome://`, `about:`, `file://`** (C-04) e **roda probe dentro de cada iframe** (C-05)
  - **Detecta 1×/aba**, cacheia por `tabId` em `chrome.storage.session`; recomputa só em navegação (NB-04)
  - **SPA-aware**: `chrome.webNavigation.onHistoryStateUpdated` além de `onUpdated` (A-05)
  - **Tolerante a frame inacessível** (iframe sandboxed) — erro por-frame não aborta detecção (NB-09)
- Resolve o manifest **do bundle** (`getURL`) a partir do `providerId` detectado — **zero upload**

*Privacidade & consentimento (achados críticos novos):*
- **Trocar `content_scripts: <all_urls>`** por `declarativeContent` (ícone acende só em
  domínio de cassino) + **injeção programática pós-detecção** (NB-01)
- **Detecção é automática; iniciar a escuta exige 1 clique** (ou opt-in por provider
  persistido em `chrome.storage.local.autoStartPolicy`) — **nunca** apostar/operar sozinho (NB-02)

*Self-heal de seletores (o "sensoriamento/fine-tuning" local):*
- Content script reporta **hit/miss por seletor** a cada tick → SW agrega `manifestHealth`
- Seletor primário falhando **N ticks** → promove um `fallbackSelector` que retorne dado
  **válido** (número 0-36); promoção **reversível** + telemetria (NB-07)
- Telemetria de drift envia **só hit/miss + hash do seletor**, nunca o conteúdo (NB-10)

*2º provider + UX:*
- `extension/providers/pragmatic.json` (OU `playtech.json`) — schema canônico completo com `_detection`
- Popup mostra "Provider detectado: Pragmatic Play (manifest v1.0.0, confidence 0.85)"
- Botão "Forçar provider…" para override manual (L-02 dry-run)
- **Dealer awareness** (consome `extractSessionData` existente): detecta `sessionData.dealer`
  mudou entre 2 ticks → toast "Novo dealer: João — Resetar? [Sim/Não]"; política em
  `chrome.storage.local.dealerChangePolicy = ask|auto|ignore` (PP-05)

*Testes:*
- 12 novos em `tests/test_provider_router.py`: URL match; DOM probe (mock); threshold;
  margem mínima → unknown; URL inválida ignorada; SPA atualiza cache; 2 providers competindo;
  detecção 1×/aba (não por tick); frame inacessível tolerado; override manual; bundle resolve
  manifest; declarativeContent registra regra
- 4 novos em `tests/test_selector_self_heal.py`: promoção após N ticks; rejeita fallback com
  dado inválido; promoção reversível; telemetria sem conteúdo
- 3 novos em `tests/test_dealer_change_detection.py`

**💡 Por que fazer**: este é o **coração da pergunta do operador**. Eliminar o upload e o
"qual JSON" remove a maior fricção e a maior fonte de erro (carregar manifest errado, PP-02)
do fluxo. O self-heal garante que a federação não quebre toda vez que um cassino muda uma
classe CSS. E os dois críticos (NB-01 privacidade / NB-02 consentimento) **não podem** ser
adiados: sem eles a auto-detecção é um risco de revisão na store e de operar mesa errada.

**Critério de aceite**
- ✅ Abrir `evo-games.com` → popup mostra "Evolution" **sem upload e sem escolher JSON**
- ✅ Abrir site de Pragmatic → popup mostra "Pragmatic" automaticamente
- ✅ Alternar entre 2 abas mantém detecção correta e cacheada (sem recomputar por tick)
- ✅ Página ambígua (2 providers no DOM) → cai em "unknown" e pede override
- ✅ Ícone **não** acende em site fora de cassino (`declarativeContent`)
- ✅ Escuta **não** inicia sem 1 clique/opt-in explícito
- ✅ Derrubar o seletor primário (teste) → self-heal promove fallback e dados continuam válidos
- ✅ Spin de provider B chega no servidor com `provider='pragmatic'`

**PPs UX endereçados**: PP-02 (raiz), PP-05
**Achados endereçados**: C-04, C-05, A-05, L-02, **NB-01, NB-02, NB-03, NB-04, NB-07, NB-09, NB-10**
**Risco**: 🟡 médio-alto. Requer pesquisa DOM real do 2º provider (varia por skin) **e**
troca do modelo de ativação (`<all_urls>` → declarativeContent). Mitigação: manter
`<input file>` como fallback e flag `SDA_AUTODETECT` default OFF até validar em campo.

**Dependências**: Sprint 1 (bundle + schema + router-stub).

---

### Sprint 3 — **Server Catalog + Backfill** ⏱️ 2-3 dias

**🎯 Ganho**: o servidor passa a ter **memória de quais mesas/manifests existem** e a
amarrar cada decisão ao manifest que a gerou — habilita **replay determinístico** e
analytics por provider/mesa. Sem isso, multi-provider vira dado solto sem rastreabilidade.

**Objetivo**: persistir catálogo de mesas e manifests no servidor.
Toda decisão passa a referenciar `table_canonical_id` e `manifest_hash` — base para
replay determinístico e analytics por provider.

**Entregáveis**
- Migration `0009_tables_registry.py` em Postgres:
  - `shared.tables` UNIQUE(provider, raw_table_id) com `canonical_id` GENERATED
  - `shared.manifests` (hash, version, schema_version, body, origin)
  - ALTER `cw/ccw.spin_features` ADD `table_canonical_id`, `manifest_hash`
- **SQLite mirror auto-migra** em `sqlite_repo.py` (padrão SP-13/SP-16) — C-03
  - Cria `tables` e adiciona colunas em `decisions`
- `message_handler.handle_new_result`:
  - Upsert idempotente em `shared.tables` (`INSERT OR IGNORE` SQLite, `ON CONFLICT DO NOTHING` PG) — A-06
  - Calcula `manifest_hash` a partir do header `X-Manifest-Hash` enviado pela extensão (header novo) ou null se ausente
  - Grava `table_canonical_id` e `manifest_hash` em `decisions`
- Extensão envia `manifest_hash` no payload de `novo_resultado` (campo opcional)
- Script `scripts/backfill_table_canonical_id.py`:
  - Lê decisions sem `table_canonical_id`
  - Infere de (provider, table) existente
  - Update em batches de 10k com SAVEPOINT
  - Lock janela curta (<2s por batch)
- **Canary deploy**: SDA_PROVIDER_CATALOG flag default OFF; backfill rodando em modo dry-run primeiro — A-02
- Testes: 6 novos em `tests/test_sp_provider_catalog.py`
  - Migration 0009 up/down idempotente
  - Upsert tables idempotente sob race
  - Backfill bate 100% das decisions existentes
  - manifest_hash null não quebra insert
  - SQLite auto-migra ao reabrir
  - Postgres ON CONFLICT não duplica

**Critério de aceite**
- ✅ Após deploy, `SELECT COUNT(DISTINCT canonical_id) FROM shared.tables` cresce com spins novos
- ✅ Replay: dada uma decision_id antiga, consigo recuperar o manifest_body usado
- ✅ Zero regressão na suite (467+ tests)

**PPs UX endereçados**: nenhum direto (infra preparatória da Sprint 7).
**Risco**: 🟠 médio-alto. Toca persistência em produção. **Exige rollback plan**:
flag SDA_PROVIDER_CATALOG=0 reverte comportamento (campos novos viram null).

**Dependências**: Sprint 0 (CI verde), Sprint 1 (manifest_hash do cliente).

---

### Sprint 4 — **Server Session Registry + Multi-mesa real** ⏱️ 5-7 dias

**🎯 Ganho**: **N mesas rodando ao mesmo tempo sem se contaminarem.** Mata o bug raiz que
hoje impede multi-mesa (estado singleton no servidor). É o que destrava 1 operador
acompanhando várias roletas em paralelo — a base de runtime da Sprint 7.

**Objetivo**: resolver o **bug crítico C-01** — o servidor é singleton. Refatorar para
1 GameState por `(provider, raw_table_id)`, com state_lock por sessão.
**Habilita visibilidade multi-mesa** para a Sprint 7.

**Entregáveis**
- Novo `server/session_registry.py`:
  ```python
  class ServerSessionRegistry:
      def __init__(self):
          self._sessions: dict[str, SessionContext] = {}  # canonical_id → ctx
          self._lock = asyncio.Lock()
      async def get_or_create(self, canonical_id: str) -> SessionContext: ...
      async def close_idle(self, max_idle_s: int = 3600): ...
  ```
  - `SessionContext` = { game_state, strategy, state_lock, last_spin_ts, ... }
- Refator `MessageHandler.handle_new_result`:
  - Em vez de `async with self.state_lock` global, agora:
    - `canonical_id = f"{spin.provider}:{spin.table}"`
    - `ctx = await self.session_registry.get_or_create(canonical_id)`
    - `async with ctx.state_lock: ctx.game_state.process_spin(...)`
- TTL para sessões idle (1h sem spin → close)
- Métricas Prometheus:
  - `active_sessions_count`
  - `spins_per_provider_total{provider="..."}` (de Sprint 0)
  - `session_lifecycle_total{event="created|closed|recovered"}`
- **Backward compat**: se SpinInput.provider null, usa session "unknown:default" (preserva
  comportamento singleton atual para clientes antigos)
- **Endpoint REST novo `GET /sessions`** retorna `[{canonical_id, provider, display_name, started_at, spins_count, last_spin_ts, status}]`
  — consumido pelo popup Sprint 7
- Testes: 10 novos em `tests/test_session_registry.py`
  - 2 mesas em paralelo não contaminam state
  - state_lock por sessão isola spins concorrentes
  - TTL fecha sessão idle
  - Recovery após restart do servidor
  - Backward compat: spin sem provider cai em "unknown:default"
  - Métricas Prometheus expostas

**Critério de aceite**
- ✅ Teste de carga: 3 mesas enviando 10 spins/s cada por 5min sem cross-contamination
- ✅ `active_sessions_count` reflete N mesas ativas
- ✅ Spin antigo (sem provider) continua processado normalmente
- ✅ `GET /sessions` retorna lista populada quando há ≥1 sessão ativa

**PPs UX endereçados**: nenhum direto (back-end de Sprint 7).
**Risco**: 🔴 alto. Refator profundo no message_handler. Exige:
- Feature flag `SDA_SESSION_REGISTRY` default OFF
- Shadow mode: rodar registry em paralelo com singleton, comparar outputs
- Migration faseada em produção (1 dia shadow, 3 dias canary 10%, depois 100%)

**Dependências**: Sprint 3 (catálogo + canonical_id).

---

### Sprint 5 — **OTA de manifests assinado (fecha o loop de fine-tuning)** ⏱️ 1 semana

**🎯 Ganho**: **a federação se afina sozinha sem rebuild nem republicação na store.**
Um seletor que quebrou (cassino mudou o layout) é corrigido no repositório central e
**chega a todas as extensões em ≤6h**, assinado. Mais o kill-switch remoto: desligar um
provider problemático em <5 min. É a peça que torna o "sensoriamento" da §4.9 *contínuo*
em vez de pontual.

**Objetivo**: deslocar manifests da extensão para um repositório central versionado e
**assinado**, com canal de atualização *over-the-air*. Resolve **M-01** (manifest_origin),
**M-04** (kill-switch), **PP-13** (feedback de desatualizado) e os achados novos **NB-05**
(integridade) e **NB-06** (version skew).

**🔧 O que fazer (entregáveis)**
- Repositório `roleta-cloud-manifests/` no Git (público):
  - `providers/{evolution,pragmatic,playtech}.json`
  - `index.json` com versionamento semver + `schema_version` por manifest
  - `flags.json` com kill-switch por provider
- GitHub Pages serve em `https://manifests.xma-ia.com/`
- Extensão verifica `/index.json` a cada 6h (`chrome.alarms 'manifestRefresh'`) — **OTA**
- **Trust chain obrigatória (NB-05)**: assinatura **Ed25519** do `index.json` e de cada
  manifest; **chave pública pinada no código**; a extensão **recusa** executar manifest
  cuja assinatura não verifique (selector é código que lê o DOM do operador)
- **Version negotiation (NB-06)**: extensão compara `schema_version` do manifest com o que
  ela e o servidor suportam; incompatível → não aplica + avisa no popup
- Popup: botão "Verificar atualizações" + indicador "Manifest desatualizado/atualizado" (PP-13)
- **Consome a telemetria de drift da Sprint 2**: painel mostra quais seletores estão se
  auto-curando muito (sinal de que o manifest do CDN precisa de revisão humana)
- Persistência em `chrome.storage.local.manifests` (com checksum + assinatura)
- `manifest_origin = 'cdn'` quando vem do CDN; `'local'` se operador editou; servidor
  reflete em `shared.manifests.origin`
- Testes: 8 novos em `tests/test_manifest_cdn.py` (inclui: assinatura inválida rejeitada;
  schema_version incompatível bloqueado; cache serve offline; kill-switch aplica)

**💡 Por que fazer**: sem OTA, corrigir um seletor exige recompilar a extensão e
republicar na Chrome Web Store (dias + fricção). Com OTA assinado, é um commit no repo de
manifests → horas. A assinatura é **não-negociável**: um CDN comprometido sem ela injetaria
seletores que exfiltram o DOM do operador. Esta sprint transforma o self-heal *local* da
Sprint 2 em **fine-tuning da federação inteira**.

**Critério de aceite**
- ✅ Mudança no Git → todas extensões atualizam em ≤6h sem rebuild
- ✅ Manifest com assinatura inválida é **recusado** (NB-05)
- ✅ Manifest com `schema_version` incompatível não é aplicado e o popup avisa (NB-06)
- ✅ Kill-switch desabilita Pragmatic em <5min
- ✅ Manifest local (operador editou) tem precedência se mais recente
- ✅ Popup mostra "🔄 Manifest atualizado" após sync bem-sucedido

**PPs UX endereçados**: PP-13
**Achados endereçados**: M-01, M-04, **NB-05, NB-06**, NB-10 (telemetria)
**Risco**: 🟡 médio. Adiciona dependência externa (GitHub Pages). Mitigação: cache local
assinado serve quando CDN indisponível; nunca executa manifest não-verificado.

**Dependências**: Sprint 2 (self-heal + telemetria de drift); Sprint 4 recomendada.

---

### Sprint 6 — **Strategy Router por Provider + Capability Flags** ⏱️ 5-7 dias

**🎯 Ganho**: cada provider/mesa pode usar a **estratégia certa para ele** em vez de uma
única SDA17 "tamanho único". Abre espaço para extrair mais EV por provider e respeitar as
*capabilities* de cada mesa (turbo, betShield) sem if's espalhados pelo código.

**Objetivo**: cada provider pode ter estratégia/parâmetros distintos. SDA17 é otimizada
para Evolution — Pragmatic pode preferir SP-20 ou outra estratégia.

**Entregáveis**
- `strategies/strategy_router.py`:
  - Input: `(provider_id, capabilities)`
  - Output: instância de `StrategyBase` configurada
  - Registry: mapeamento declarativo em `config/strategy_routing.toml`:
    ```toml
    [providers.evolution]
    strategy = "sda17"
    [providers.evolution.params]
    sat_asym_enabled = true
    geometry_v2_enabled = true
    
    [providers.pragmatic]
    strategy = "sda17"   # mesma por enquanto, params diferentes
    [providers.pragmatic.params]
    sat_asym_enabled = false  # Pragmatic ainda em calibração
    ```
- `_capabilities` do manifest entra como input do strategy router
- `dealer_offset.py` particionado por provider (A-03)
  - Hoje agrega TODOS os dealers; novo: `GROUP BY provider, dealer`
- ServerSessionRegistry injeta strategy correta na SessionContext
- Testes: 8 novos em `tests/test_strategy_router.py`

**Critério de aceite**
- ✅ Spin Evolution usa SDA17 com sat_asym=true
- ✅ Spin Pragmatic usa SDA17 com sat_asym=false (telemetria mostra)
- ✅ dealer_offset Evolution não cruza com Pragmatic

**PPs UX endereçados**: nenhum direto (lógica de estratégia).
**Risco**: 🟡 médio-alto. Toca estratégias em produção. Exige A/B controlado.

**Dependências**: Sprints 3, 4.

---

### Sprint 7 — **UI Multi-mesa & Operações (NOVO ESCOPO EXPANDIDO)** ⏱️ 5-7 dias

**🎯 Ganho**: o popup vira um **painel de controle multi-mesa** — o operador vê e gerencia
todas as roletas ativas de um lugar só, com badge, histórico e onboarding. **Absorve 13
dos 20 pain points UX** e é a entrega que muda o modelo mental do operador (seção 4.8).

**Objetivo**: refundar o popup como **painel multi-mesa**. Esta sprint absorve
**13 dos 20 pain points UX** identificados na seção 4.6 — é a entrega
que muda o modelo mental do operador (seção 4.8).

**Entregáveis — UI**

#### 7.1 Refator do popup.html / popup.js
- Substituir layout "1 aba ativa" pela **lista de mesas detectadas** (wireframe 4.7)
- Cada linha mostra:
  - Badge provider colorido (🟢 Evolution, 🔵 Pragmatic, ⚪ Desconhecido)
  - display_name + dealer + round_id atual (PP-04)
  - Spins na sessão + saldo + último número
  - Ações por mesa: [▶️/⏸️/⏹️] [📋 Logs] [⚙️]
- Topo: contador "N mesas escutando · M detectadas" + botão global `[⏹️ PARAR TUDO]`
- Rodapé: Direção do giro (mantido, mas com indicador "auto"/"manual" claro PP-07)
- Versão dinâmica no header puxada de `chrome.runtime.getManifest().version` (PP-06 — também na Sprint 1, redundância intencional)

#### 7.2 Modais de confirmação
- **Iniciar escuta** (wireframe 4.7) — exige confirmação explícita (PP-16)
- **Mudança de dealer** (wireframe 4.7) — opções: Ignorar / Resetar / Sempre perguntar (PP-05 já implementado em Sprint 2; aqui só UI refinada)
- **Parar escuta** se sessão tem >50 spins — oferece exportar antes
- **Parar tudo** — confirmação se >1 sessão ativa

#### 7.3 Estado fora do popup
- **Badge dinâmico da extensão** (PP-08):
  - Texto: número de mesas ativas (0 → vazio)
  - Cor: verde se ≥1 ativa, cinza se nenhuma, vermelho se erro persistente
  - Tooltip ao hover: lista as mesas
- Ícone da extensão muda de pulse quando 1+ mesa ativa

#### 7.4 Service Worker — coordenação multi-tab
- `Map<tabId, MesaState>` em `chrome.storage.session`
- `chrome.runtime.onMessage` adiciona handlers: `getActiveSessions`, `startListening(tabId)`, `stopListening(tabId)`, `pauseListening(tabId)`
- WebSocket: 1 conexão compartilhada; cada `novo_resultado` carrega `tab_origin_id` no payload
- Cada mesa tem ciclo de vida independente (alarm name único `readLoop_{tabId}`)

#### 7.5 Limpeza de pain points menores
- Remover botão "📋 EXPORTAR LOGS" do nível principal (PP-11) — mover para `[⚙️]` por mesa
- Consolidar overlay/popup: overlay foca em **dados da rodada**, popup foca em **gestão multi-mesa** (PP-12)
- Logs: 100 entradas + filtro por tabId/provider + botão "Exportar sessão completa" (PP-10)
- Connection URL mostra `display_name + provider` ao invés de URL crua (PP-18)
- Mensagem "Background dormindo" troca para "⏳ Inicializando..." (PP-17)
- Traffic light estado inicial: "Sem dados (aguardando primeiro spin)" — não "AGUARDANDO..." (PP-19)
- Saldo inicial mostra "—" não "R$ 0,00" (PP-20)

#### 7.6 Onboarding (PP-08 + nova)
- Página `extension/onboarding.html` aberta em nova aba ao instalar
- Tour de 3 passos com screenshots
- Botão "Pular tutorial" / "Não mostrar novamente"

#### 7.7 Histórico de sessões
- Card "Últimas 5 sessões" no popup (colapsável)
- Mostra: provider, mesa, duração, spins, exportar JSON
- Lê de `chrome.storage.local.sessionHistory` (rolling, max 50)

#### 7.8 Endpoint REST `/sessions` (consome)
- Popup faz polling a cada 2s do `GET /sessions` (Sprint 4) quando aberto
- Sincroniza estado entre client (storage local) e server (registry)
- Quando discrepância: client confia no server (server é source-of-truth)

#### 7.9 Métricas Prometheus → Grafana
- Painel "Mesas Ativas por Provider"
- Painel "Spins/min por mesa"
- Painel "Dealers únicos por provider"
- Painel "Distribuição de manifests em uso" (qual % está em cdn vs local)

**Testes**: 15+ novos em `tests/test_ui_multi_mesa.py` + `tests/test_session_history.py`
+ smoke E2E com Puppeteer (`tests/e2e/test_multi_tab_listening.spec.js`).

**Critério de aceite**
- ✅ 3 abas (2 Evolution + 1 Pragmatic) listenando simultaneamente
- ✅ Pausar mesa A não afeta B e C
- ✅ Métricas batem com `active_sessions_count` do servidor
- ✅ Badge mostra número correto após operações de start/stop
- ✅ Onboarding aparece só na primeira instalação
- ✅ 13/20 pain points UX (4.6) marcados como resolvidos (PPs 04, 07, 08, 10-12, 14-20)

**PPs UX endereçados**: PP-04, PP-07, PP-08, PP-10, PP-11, PP-12, PP-14, PP-15, PP-16, PP-17, PP-18, PP-19, PP-20

**Risco**: 🟡 médio. Refator de UI; lógica de runtime já consolidada na Sprint 4.

**Dependências**: Sprints 4, 6.

---

## 6. Mapeamento auditoria → sprint

| Achado | Sprint | Tratamento |
|---|---|---|
| C-01 (singleton) | 4 | ServerSessionRegistry |
| C-02 (_meta.service) | 1 | Preservar campo |
| C-03 (SQLite shared.tables) | 3 | Auto-migrate em sqlite_repo |
| C-04 (chrome:// URLs) | 1, 2 | Filtro de URL inválida no router |
| C-05 (iframe URL) | 2 | Probe allFrames no router |
| A-01 (CI) | 0 | Fix alembic upgrade |
| A-02 (provider opcional) | 3 | Canary + deprecation window |
| A-03 (dealer_offset multi) | 6 | Particionar por provider |
| A-04 (storage budget) | 1 | Telemetria + alerta |

---

# 7. Passos — Estratégia de aposta 14# (análise 15/06)

> **Origem**: análise completa em `resultados_15_junho.md` (15/06/2026) — backtest de
> engenharia reversa das **últimas 100 jogadas de cada sentido, isoladas** (fonte
> `data/decisions_prod_1206b.db`, 100 distintas/sentido; `decisions.db` de 15/06 rejeitada por
> replay/backfill). Reconstrução validada 100% (1.237/1.237) contra `result_region`.
> **Stack MCP**: sequential-thinking, graphify (HEAD `23c3490`), memory, filesystem.

## 7.1 Resumo executivo (o que o backtest decidiu)

A proposta era passar de **21 números (3 centros)** para **14 (2 centros)**, escolhendo
dinamicamente entre C1 e C2 por "momentum" (C3 como apoio fixo), com regra auxiliar ("só
aposta após green") e um sistema de **gale por sentido**. O backtest, com controles de
histórico completo, concluiu:

| Camada testada | Resultado na janela 100 | Veredito (controle histórico) |
|---|---|---|
| **14# em vez de 21#** | breakeven 58,3%→**38,9%** | ✅ **Adotar** — maior alavanca |
| **Gate de sentido** | anti +EV / horário −EV | ✅ **Adotar** — único lever robusto |
| Momentum C1↔C2 (Cenário A) | "bate" C2+C3 na janela | ⚠️ edge ≈0 (voto = taxa-base) |
| Regra auxiliar "só após green" | hit 31%→43% (horário) | ❌ green/red memoryless (χ² p=0,46/0,55) |
| Gale 2-de-4 ×1/2/4/8 | +116u / +244u na janela | ❌ **ruína**: −1.722u / −458u no histórico |

**Decisão de produto:** operar **14# = C1/C2 VARIÁVEL (últimas 3 não-C3) + C3 FIXO** — a
estratégia que o operador definiu — com **gate de sentido** e **stake flat**. **Não** implementar
gale (ruína comprovada). *Nota honesta:* a seleção C1/C2 tem edge medido ≈0 vs fixar a região
mais forte (sequência memoryless), então o ganho real vem do gate de sentido + redução 21→14;
mas a estratégia operada é a variável C1/C2 + C3 fixo.

## 7.2 Especificação da estratégia recomendada

```
Por sentido (horário e anti-horário tratados ISOLADAMENTE):
  cobertura = { C_var, C3 }              # 14 números, R=3 (7 por região); C3 SEMPRE FIXO
     C_var = C1 ou C2, escolhido a cada jogada pelas ÚLTIMAS 3 jogadas que caíram
             mais perto de C1/C2 do que de C3 (voto por proximidade |dist→C1| vs |dist→C2|;
             maioria; empate -> C2). Análise isolada por sentido.
  stake = flat (1u/número)               # SEM gale/martingale
  gate de sentido:
     - anti-horário  -> aposta cheia (estruturalmente +EV)
     - horário       -> stake mínimo (×0,10) ou no-bet (estruturalmente −EV)
  INV-3: o gate MODULA o stake (×0,10 / 1u), nunca suprime a indicação.
  Nota: medição mostra edge ~0 da seleção C1/C2 vs fixar a região mais forte
        (sequência memoryless); o lever robusto é o gate de sentido.
```

## 7.3 Por que NÃO o momentum, o filtro green e o gale (evidência)

- **Momentum C1↔C2:** a sequência de região vencedora é memoryless (χ² da matriz de transição
  p=0,36–0,91 no estudo base). O voto das últimas 3 não supera "chutar a classe mais comum"
  (horário −3,1pp; anti +4,0pp ≈ ruído). O "ganho" vs C2+C3 na janela é *qual dupla*
  (C1+C3 puro ainda bate o Cenário A), não *timing*.
- **Filtro "só aposta após green":** green/red também é memoryless —
  P(green|green) − P(green|red) = −2,0pp (horário) / −1,6pp (anti), χ² p=0,46 / 0,55. O filtro
  só reduz o nº de apostas (100→~30), não melhora o hit-rate.
- **Gale 2-de-4 ×1/2/4/8:** não muda o EV (invariante já registrado). Com hit real 34–38% <
  breakeven 38,9% e critério "2 de 4" = 50% (acima do real), o gale escala ~metade dos blocos;
  no histórico completo: **horário −1.722u (maxDD −1.928u, ×8 10×)**, **anti −458u (maxDD
  −1.550u, ×8 11×)** — banca de 50u estourada nos dois sentidos.

## 7.4 Passos de implementação (sprints)

1. **Telemetria por sentido** — expor taxa-base de acerto de C1/C2/C3 (R=3) por sentido nas
   últimas N jogadas (já há `decision_dna.hit_region` com `dist_c1/c2/c3`). Endpoint/métrica
   Prometheus seguindo o padrão de `server/health_server.py` (ver memória "prometheus
   observability").
2. **Flag `SDA_BET_PAIR`** — cobertura 14# parametrizável, reusando `details['centers']` em
   `strategies/sda17.py`/`server/message_handler.py`. **Default = `var_c1c2_c3`** (C1/C2 variável
   pelas últimas 3 não-C3 + C3 fixo); modos alternativos: `c1c3`, `c2c3` (referência).
3. **Gate de sentido** — reusar o override de stake do bloco `INV-3 GLOBAL`
   (`server/message_handler.py`): anti cheio, horário ×0,10 (flag `SDA_DIR_GATE`).
4. **Guarda anti-replay** — garantir que backfill/replay **não** reescreva spins no
   `decision_dna` (o replay de 15/06 gerou 90 duplicatas em 120 linhas e invalidaria o
   "últimas 100"). Deduplicar por `(spin_number, dist_c1, dist_c2, dist_c3)` na ingestão de
   telemetria offline.
5. **Validação** — após +200–300 spins limpos por sentido, re-rodar o backtest
   (`resultados_15_junho.md`) para confirmar o gate com folga estatística (hoje IC ±9–10pp).
6. **NÃO** abrir sprint de gale/martingale. Se houver pedido de staking, usar flat ou Kelly
   limitado (`flat_kelly_junho.md`).

## 7.5 Riscos / notas

- **Amostra pequena**: 100 spins/sentido ⇒ IC ±9–10pp (±17pp nas ~30 apostas pós-filtro).
  Nada aqui é estatisticamente conclusivo isoladamente; o gate de sentido é a conclusão mais
  robusta porque aparece em todos os recortes.
- **Geometria**: o backtest usa o modelo simétrico R=3 (3×7→2×7) descrito na proposta; a
  geometria de produção é SDA17 (17#, satélites assimétricos). Definir se a migração para 14#
  remove o C1 (raio 1) ou o mantém como bônus.
| A-05 (SPA navigation) | 2 | webNavigation.onHistoryStateUpdated |
| A-06 (race tables) | 3 | INSERT OR IGNORE / ON CONFLICT |
| A-07 (backfill) | 3 | Script em batches |
| M-01 (manifest_origin) | 5 | Field em shared.manifests |
| M-02 (replay determinístico) | 3 | manifest_hash em decisions |
| M-03 (capabilities) | 6 | _capabilities consumido por router |
| M-04 (kill-switch) | 5 | flags.json no CDN |
| M-05 (strategy router) | 6 | strategies/strategy_router.py |
| L-01 (metrics) | 0, 4 | Prometheus gauges |
| L-02 (dry-run) | 2 | Override manual no popup |
| L-03 (JSON Schema) | 1 | Ajv + _schema.json |
| **NB-01** (content_scripts <all_urls>) | 2 | declarativeContent + injeção pós-detecção |
| **NB-02** (auto-start sem consentimento) | 2 | Detecção auto, start exige 1 clique/opt-in |
| **NB-03** (falso-positivo detecção) | 2 | Margem mínima de confidence → unknown+override |
| **NB-04** (custo detecção por tick) | 2 | Detectar 1×/aba, cache por tabId |
| **NB-05** (integridade OTA) | 5 | Assinatura Ed25519 + chave pinada |
| **NB-06** (version skew) | 5 | Negociação de schema_version |
| **NB-07** (self-heal seletor errado) | 2 | N ticks + validação 0-36 + reversível |
| **NB-08** (storage budget) | 1 | getBytesInUse + GC |
| **NB-09** (iframe sandboxed) | 2 | Erro por-frame não aborta |
| **NB-10** (privacidade telemetria) | 2, 5 | Só hit/miss + hash, nunca conteúdo |

---

## 7. Riscos transversais

| Risco | Mitigação |
|---|---|
| **Refator de runtime do servidor (Sprint 4)** quebra produção | Feature flag default OFF + shadow mode 1 dia + canary 10% |
| **CDN MITM** (Sprint 5) injeta manifest malicioso | Assinatura Ed25519 + verificação no SW |
| **chrome.storage.local overflow** com muitos providers | Telemetria getBytesInUse + cleanup automático |
| **Pesquisa DOM do 2º provider** (Sprint 2) leva mais que o estimado | Buscar comunidade open-source de seletores; aceitar fallback genérico |
| **Backfill de milhões de decisions** trava SQLite | Lock janela <2s/batch; rodar fora do horário de pico |
| **Strategy router (Sprint 6)** muda comportamento de produção | A/B controlado: 10% Evolution → SDA17 v2 (com router) vs 90% atual |
| **Multi-tab WebSocket** congestiona link único | 1 conexão por SW; backend demultiplexa por canonical_id |

---

## 8. Decisões pendentes para @ivandirfilho

1. **Qual segundo provider** virar PoC na Sprint 2?
   - [ ] Pragmatic Play (mercado BR maior, mas seletores menos documentados)
   - [ ] Playtech (mais corporativo, seletores mais estáveis)
   - [ ] Imagine (menor, mas operador já joga lá)
2. **Multi-mesa simultânea é requisito hard** (1 PC, N mesas) ou **nice-to-have**?
3. **Manifest CDN entra no escopo** ou fica documentado como V2?
4. **Postgres ON em produção** para shared.tables? Hoje é OFF default.
5. **Quem mantém manifests** quando site muda layout?
   - [ ] Operador edita JSON local + PR para repo central
   - [ ] Time central com process de release semanal
   - [ ] Auto-detecção via diff de selectors falhando (M-04 reverse)
6. **Estratégia por provider** (Sprint 6): manter SDA17 universal ou criar variants?
7. **Auto-start**: ao detectar a mesa, a escuta deve iniciar sozinha (opt-in por provider)
   ou **sempre** exigir 1 clique de consentimento? (NB-02 — recomendação: clique por padrão,
   opt-in explícito e por-provider para quem quiser automático).
8. **Estreitar `host_permissions`** de `<all_urls>` para domínios de cassino conhecidos
   **agora** (Sprint 2, junto do `declarativeContent`) ou em sprint dedicada? (NB-01 — risco:
   um cassino novo fora da lista deixa de funcionar até atualizar; mitigado pelo OTA da Sprint 5).

---

## 9. Métricas de sucesso (por sprint)

| Sprint | KPI técnico | KPI UX |
|---|---|---|
| 0 | CI verde 100% das últimas 7 runs | — |
| 1 | Manifests no registry: 1+schema; **bundle resolve sem upload** | Popup remove msg falsa "servidor offline"; **upload manual eliminado p/ Evolution**; 4/20 PPs resolvidos |
| 2 | Providers suportados: 2; **detecção <3s e 1×/aba**; self-heal promove fallback | **ZERO upload, ZERO escolher JSON**; ícone só em cassino; start com consentimento; dealer auto-prompt |
| 3 | Decisions com canonical_id 100% pós-cutoff; backfill 100% pré-cutoff | — (infra preparatória) |
| 4 | 3 mesas paralelas sem cross-contamination; `active_sessions_count` correto | — (back-end) |
| 5 | Manifest update latency <6h ponta-a-ponta; **assinatura inválida recusada 100%** | "Manifest desatualizado" visível; correção de seletor chega sozinha; 1 PP resolvido |
| 6 | Strategy router coverage: 100% spins roteados; dealer_offset particionado | — |
| 7 | 3+ abas simultâneas estável por 1h; badge dinâmico OK; onboarding aparece 1×; popup poll latência <2s | **13/20 PPs resolvidos** — modelo mental do operador muda (seção 4.8) |

### KPI ponta-a-ponta (todas as sprints completas)

| KPI | Hoje | Meta |
|---|---|---|
| Providers suportados | 1 (Evolution) | 3+ (Evolution, Pragmatic, Playtech) |
| **Upload manual de JSON** | **obrigatório a cada sessão** | **eliminado (bundle + auto-detecção)** |
| Tempo médio "abrir site → começar a escutar" | 60-90s (upload manual + clicks) | <10s (detecção automática + 1 clique de consentimento) |
| Tempo "abrir site → provider detectado" | n/a (manual) | <3s |
| Resiliência a mudança de seletor do cassino | quebra até rebuild | self-heal local + correção OTA ≤6h |
| Mesas simultâneas por operador | 1 | N (limitado por máquina) |
| % spins com `provider` populado | <100% (alguns null) | 100% |
| % spins com `manifest_hash` populado | 0% | 100% |
| Cross-contamination entre mesas | possível (singleton) | impossível (isolado) |
| Tempo para deploy de mudança em seletor | rebuild + release (~30min+store) | edit JSON + CDN sync (≤6h) |
| Pain points UX abertos | 20 (+10 NB de risco) | 0 |

---

## 10. Glossário & referências

- **Manifest**: arquivo JSON declarativo que descreve como extrair dados de um provider.
  Hoje é `extrator_completo.json` v18.2.0 (só Evolution).
- **Provider**: cassino ao vivo (Evolution Gaming, Pragmatic Play, Playtech, Imagine).
- **canonical_id**: ID estável da mesa em forma `provider:raw_table_id`
  (ex.: `evolution:PorROU0000000001`).
- **manifest_hash**: sha256 do manifest canonicalizado em vigor no momento da decisão.
  Permite replay determinístico.
- **Capability**: feature opcional de uma mesa (turbo, betShield, ...) declarada em
  `_capabilities` do manifest.
- **SessionContext**: estrutura por (provider, raw_table_id) no servidor pós-Sprint 4,
  contém GameState + strategy + state_lock isolados.
- **Pain Point (PP)**: item de fricção UX identificado na seção 4.6, numerado PP-01 a PP-20.
- **Onboarding**: tela de boas-vindas que aparece na primeira instalação da extensão,
  guiando o novo operador.
- **Zero-Upload**: princípio de §4.9 — o operador nunca carrega um JSON; o manifest vem
  empacotado na extensão e/ou é baixado por OTA.
- **Auto-detecção**: o classificador (`provider_router.js`) identifica provider+mesa por
  fingerprint (URL+DOM+meta+JS globals, ponderado) sem intervenção do operador.
- **Self-heal**: capacidade da extensão de promover automaticamente um `fallbackSelector`
  quando o seletor primário quebra (cassino mudou layout), validando o dado antes (NB-07).
- **OTA (Over-The-Air)**: canal de atualização remota e **assinada** dos manifests
  (Sprint 5) — corrige a federação em ≤6h sem rebuild nem republicação na store.
- **NB (New-Behaviour finding)**: achado de auditoria específico dos riscos que a
  auto-detecção/zero-upload introduz (NB-01 a NB-10, seção 3.5).
- **declarativeContent**: API MV3 que acende o ícone/ativa a extensão só em páginas que
  casam uma condição (ex.: domínio de cassino) — substitui `content_scripts:<all_urls>` (NB-01).

**Referências internas**:
- `extension/manifest.json` (host_permissions `<all_urls>` + content_scripts — alvo de NB-01)
- `extension/popup.js:145` (`loadExtractorFile`: o upload manual que o zero-upload elimina)
- `extension/background.js:490` (`executeScript allFrames` — probe já existente p/ detecção)
- `extension/background.js:1184` (`executeScript func+args` — injeção com config dinâmica)
- `extension/popup.html` (UI atual — alvo principal da Sprint 7)
- `extension/popup.js:288` (`connectToTab`: bug PP-15 — tab ativa do browser ≠ tab escutando)
- `extension/popup.js:558` (`startListening`: bug PP-16 — sem confirmação)
- `extension/popup.js:566` (msg "Background dormindo" — PP-17)
- `extension/content.js:62` (botão 🔄 manual de Nova Sessão — PP-05)
- `extension/session_extractor.js` (helper data-driven introduzido em v3.2.0)
- `extension/manifest.json:4` (versão atual 3.2.0; sub-título do popup divergente — PP-06)
- `extrator_completo.json` v18.2.0 (manifest atual com `data.session`)
- `migrations/versions/0007_deal_dealer_table.py` (provider em decisions + shared.dealers)
- `database/sqlite_repo.py` (padrão de auto-migration mirror SQLite ← Postgres)
- `server/message_handler.py:60` (MessageHandler singleton — alvo da Sprint 4)
- `server/websocket.py:40` (game_state singleton — alvo da Sprint 4)
- `analise_profunda_extrator_25_05.md` (análise predecessora do escuta)
- `fluxode_dados_13_junho.md` (mapa de dados do projeto)
- `gale_13_junho.md` (decisões de staking que dependem de strategy router em Sprint 6)

---

## 11. Estimativa total revisada

| Sprint | Dias | Risco | Critical path? | PPs UX |
|---|---|---|---|---|
| 0 Saneamento | 1-2 | 🟢 | sim | — |
| 1 Foundation + bundle | **2-3** (era 1-2) | 🟢 | sim | 4 |
| 2 Auto-detecção + Self-Heal | **5-7** (era 3-5) | 🟡 | sim | 2 |
| 3 Server Catalog | 2-3 | 🟠 | sim | — |
| 4 Session Registry | 5-7 | 🔴 | sim | — |
| 5 OTA assinado (fecha fine-tuning) | 5-7 | 🟡 | não* | 1 |
| 6 Strategy Router | 5-7 | 🟠 | não | — |
| 7 UI Multi-mesa | 5-7 (era 3-4) | 🟡 | sim | 13 |
| **Total caminho crítico (0,1,2,3,4,7)** | **20-29 dias** | | | **19/20 PPs** |
| **Total com 5 e 6** | **30-43 dias** | | | **20/20 PPs** |

> *Sprint 5 não está no caminho crítico para *multi-mesa*, mas é o que torna o
> **fine-tuning da federação contínuo** (§4.9.3). Se o objetivo nº1 é "abrir o site e a
> Escuta se vira sozinha", o eixo **1 → 2 → 5** entrega isso em **12-17 dias** e pode ir
> à frente das Sprints 3/4 (multi-mesa), que são independentes.

**Eixo recomendado para atacar a dor do operador primeiro** (zero-upload + self-tuning):
**Sprint 0 → 1 → 2 → 5** = pipeline verde, manifest empacotado, auto-detecção com
self-heal e OTA assinado. Multi-mesa real (3/4/7) entra logo depois.

> **Próxima ação sugerida**: responder as 8 decisões da seção 8 e iniciar Sprint 0.
> Cada sprint subsequente abre um sub-plano detalhado em `passos_escuta_junho_sprintN.md`
> (1 arquivo por sprint, criado no início da execução).

---

## 12. Implementação realizada — Auto-Start & Zero-Upload (14/06)

> Status: **ENTREGUE E DEPLOYADO** (commit `23c3490`, servidor Debian alinhado).
> Registro de execução do **eixo client-side (Sprints 1+2)** do roadmap acima. O backend
> Python (v4.4.1) não foi alterado. A análise ISO/IEC 25010 deste ciclo está em
> `Manutenabilidade_iso.md` (ADENDO 14/06).

### 12.1 O que foi entregue (roadmap → código)

| Item do roadmap | Implementação | Arquivo |
|---|---|---|
| Manifests empacotados (Sprint 1) | `evolution.json` (v18.2 + `_detection`) + `index.json` (registry); `web_accessible_resources` | `extension/providers/`, `extension/manifest.json` |
| Provider router (Sprint 2) | Classificador host→provider (fingerprint ponderado: `detectFromFrames`/`matchHostToProvider`) | `extension/provider_router.js` |
| Zero-upload | `loadBundledManifest` via `fetch(getURL)`; conserto do template mínimo legado | `extension/background.js` |
| Auto-start | `chrome.webNavigation.onCompleted`/`onHistoryStateUpdated` (filtro de host) + `getAllFrames` → `maybeAutoStart`; boot-scan; `autoStartPolicy` default `auto` | `extension/background.js` |
| UX | Bloco de auto-detecção + toggle auto-start + badge + versão dinâmica; upload vira fallback | `extension/popup.{html,js}` |
| Testes | `test_provider_router.py` (9) + `test_bundled_manifest.py` (4); suite **480 passed** | `tests/` |

### 12.2 Auditoria pós-implantação — bugs corrigidos (3 rodadas de code-review)

| # | Bug | Sev | Correção |
|:-:|---|:--:|---|
| 1 | WebSocket duplicado por race condition | High | `connectWebSocket` idempotente em `CONNECTING` + guard de socket órfão + lock por tabId |
| 2 | STOP manual não segurava (auto-start re-iniciava) | High | `suppressTab` por tabId (storage) + TTL 24h + revalidação de host + prune no boot |
| 3 | Badge verde não limpo ao parar/fechar | Med | `setBadge('')` em stop/onRemoved/auto-stop |
| 4 | 2ª aba sequestrava o `tabId` singleton | Med | recusa + log em vez de sobrescrever |
| 5 | Política `'ask'` beco sem saída | Low | `getAutoStartPolicy` normaliza ≠`off`→`auto` |

### 12.3 Deploy

- Commit `23c3490` → push `main` → **CI verde** → servidor Debian (`systemctl start roleta-deploy.service`).
- Servidor `HEAD=23c3490`, health `ok` (v4.4.1), **6 containers healthy**, log `DEPLOY OK`.
- Alinhamento: **local = origin/main = servidor = `23c3490`**.
- DB de produção protegido (volume `roleta-data` + `*.db` gitignored; `reset --hard` não o toca).

### 12.4 Ativação (ação do operador)

A extensão é **client-side** — o deploy no servidor **não** a distribui. Para ativar:
**`chrome://extensions` → recarregar "Escuta Beat"** → abrir a mesa Evolution → o popup
mostra "Evolution detectado", o badge fica verde e a escuta inicia **sem upload nem clique**.

### 12.5 O que ficou para as próximas sprints

- **Sprint 3/4** (servidor multi-mesa): a 2ª aba hoje é recusada (com log), não suportada.
- **Sprint 5** (CDN OTA assinado): manifests só empacotados; correção de seletor exige rebuild.
- **Sprint 2 plena**: `declarativeContent` (NB-01) ainda modelado; self-heal de seletores (NB-07) **núcleo puro CODADO e testado em 19/06** (ver §13) — falta só o *wiring* observe-only no read-loop (depende de E2E).
- **Sprint 7**: UI multi-mesa completa, onboarding, smoke E2E (Puppeteer); lint/build da extensão na CI.

---

## 13. Implementação realizada — Self-Heal (núcleo puro) + debate de agentes (19/06)

> Status: **ENTREGUE (núcleo puro), promoção DEFAULT OFF**. Avanço da **Sprint 2-plena (NB-07)**.
> Mudança **puramente aditiva**: 2 arquivos novos (`extension/selector_health.js`, `tests/test_selector_self_heal.py`).
> **Engine Python, `server/`, `manifest.json` e `background.js` inalterados (0 linhas).**

### 13.1 Método — debate de 3 agentes em paralelo (opus-4.8)

A decisão de *qual* incremento implantar passou por um debate estruturado (proponente / revisor-contrário / juiz), conforme os melhores padrões de orquestração de jun/2026:

| Papel | Posição |
|---|---|
| **Proponente** | Implementar NB-07 self-heal como **módulo puro UMD** (igual `provider_router.js`), 100% testável no harness `node`+pytest; flag default `off`; descartar `declarativeContent`/multi-mesa/OTA agora (não-testáveis/risco). |
| **Revisor-contrário** | Promoção em produção é **armadilha (cenário A1)**: a validação hoje é só *range 0–36* (`background.js:1732/1737`), então um fallback pode promover o **timer/saldo/ficha/resultado congelado** como se fosse spin e o sistema passa a **apostar com lixo em silêncio**. Exigiu validação **semântica** (rejeitar estático/timer), corroboração, quarentena+K, persistência anti-sono do SW (A2), TTL/revert e kill-switch. |
| **Juiz (veredito vinculante)** | Vence o contrário **ajustado pela convergência**: entregar o **módulo puro com toda a lógica, mas SEM wiring** no read-loop nesta sessão (não-testável sem E2E Puppeteer, ausente). Promoção só admissível atrás dos guard-rails semânticos — **range sozinho é insuficiente**. Risco de produção nesta sessão = **zero**. |

### 13.2 O que foi entregue (roadmap → código)

| Item | Implementação | Arquivo |
|---|---|---|
| Núcleo self-heal NB-07 | Módulo puro UMD determinístico (sem DOM, sem relógio implícito, funções imutáveis) | `extension/selector_health.js` |
| Cobertura | 19 testes via `node -e require()` (padrão `test_provider_router.py`) | `tests/test_selector_self_heal.py` |

### 13.3 Guard-rails (resposta direta ao cenário A1 do revisor)

| Guard-rail | Como | Teste |
|---|---|---|
| **Validação semântica** (não só 0–36) | `isSemanticallyValidTick`: rejeita valor **estático** (`distinct < 2`, ex.: saldo/ficha) e **timer/countdown** (corrida de inteiros consecutivos ±1) | `..._reject_static_value_A1`, `..._reject_timer_like_A1` |
| **Quarentena + K-confirmações** | promove só após N misses do ativo **E** `confirmHits≥3` **E** streak `quarantineHits≥K` | `..._quarantine_k_confirmation_before_promote` |
| **Reversibilidade + TTL** | `applyPromotion` arma `promotionTtlUntil`; `shouldRevert` reverte por TTL, probação falha ou primário recuperado | `..._revert_on_ttl_expiry`, `..._revert_on_repeated_invalid` |
| **`off` byte-idêntico** | `evaluatePolicy('off')` ⇒ `action:'none'` e `nextHealth==input`; promoção **impossível** fora de `auto` | `..._policy_off_is_byte_identical` |
| **Kill-switch local** | `evaluatePolicy(..., {killSwitch:true})` força `none` | `..._kill_switch_forces_none` |
| **Telemetria sem conteúdo (NB-10)** | `driftTelemetry` emite só `selectorHash`+booleanos+contagens; nunca o número/DOM | `..._drift_telemetry_no_content_NB10` |
| **Persistência anti-sono do SW (A2)** | `serialize/deserializeHealth` round-trip lossless p/ `chrome.storage` | `..._serialize_roundtrip_persistence_A2` |

### 13.4 API pública de `selector_health.js`

`SELF_HEAL_DEFAULTS` + `isValidRouletteNumber`, `isSemanticallyValidTick`, `classifyDrift`, `hashSelector`, `emptyHealth`, `recordTick`, `pickPromotion`, `applyPromotion`, `shouldRevert`, `applyRevert`, `driftTelemetry`, `evaluatePolicy`, `serializeHealth`, `deserializeHealth`.

### 13.5 Flags (futuro wiring — `chrome.storage.local`)

- `selfHealPolicy` ∈ `{off|shadow|auto}`, **default `off`** (off = comportamento atual intacto).
- `selfHealKillSwitch` ∈ bool, **default `false`** (desliga tudo instantaneamente, sem rebuild).

### 13.6 Critérios de aceite (atingidos)

- ✅ `pytest tests/test_selector_self_heal.py tests/test_provider_router.py -q` → **28 passed**.
- ✅ Suíte inteira **coleta 599 testes, 0 erros** (mudança aditiva).
- ✅ `git diff` adiciona **somente** os 2 arquivos novos; `manifest.json`/`server/`/`background.js` inalterados.
- ✅ `off` provado byte-idêntico; promoção impossível fora de `auto`; telemetria sem conteúdo (NB-10).

### 13.7 Composição — o que isto destrava

- **Sprint 5 (OTA Ed25519)**: `driftTelemetry` (hash+hit/miss) é exatamente o **produtor do sinal de drift** que a OTA consome para publicar manifests corrigidos.
- **Seletores data-driven**: `evolution.json` já tem `selector`+`fallbackSelectors[]` por campo (dealer/round/table/balance); o módulo é a lógica que escolhe entre eles — base para tirar seletores hard-coded de `extractResultsFromPage`.
- **Sprint 7 (E2E)**: quando o harness Puppeteer existir, o *wiring* observe-only (`shadow`) ganha cobertura ponta-a-ponta; a lógica pura já está blindada.

### 13.8 Adiado (com razão) — próximos passos

- ❌ **Wiring observe-only (`shadow`) no read-loop** — exige E2E Puppeteer (ausente); é o **1º passo da próxima sessão**.
- ❌ **Promoção `auto` em produção** — só após ≥1 semana de telemetria `shadow` confirmar que as promoções *teriam* sido corretas + E2E.
- ❌ **`declarativeContent` (NB-01)** — sprint dedicada com smoke E2E, para não regredir o auto-start já vivo.
- ❌ **Multi-mesa (Sprint 4)** — viola "Engine Python intacta"; exige Sprint 3 (catálogo) + shadow/canary.
- ❌ **OTA Ed25519 (Sprint 5)** — depende da telemetria de drift estar *wired* e observada primeiro.


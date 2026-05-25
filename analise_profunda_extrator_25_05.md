# 🧬 Análise Profunda do Extrator Beat & Plano de Evolução — 25/05

> **Modelo:** `claude-opus-4.7` · **Stack MCP usada na análise:** `filesystem` + `brave-search` + `sequential-thinking` + `graphify` + `memory`
> **Grafo Graphify:** 1908 nodes / 2010 edges / 172 communities (snapshot 2026-05-25 19:30 BRT)
>
> **Predecessores obrigatórios:**
> - [`analise_escuta_25_05.md`](./analise_escuta_25_05.md) — o que o extrator entrega hoje
> - [`Visualizacao_da_evolucao_25_05.md`](./Visualizacao_da_evolucao_25_05.md) — por que dealer/provider/table_id importam
> - [`sprint_evolucao_25_05.md`](./sprint_evolucao_25_05.md) — sprints DP-01..DP-06 + E-01
> - [`Manutenabilidade_iso.md`](./Manutenabilidade_iso.md) — padrão de qualidade ISO/IEC 25010 vigente
>
> **Audiência primária:** outro agente IA (Sonnet/Opus) que vai abrir nova janela e desenvolver o "ExtractorBeat v19" autônomo multi-provider. Este documento é a sua **bíblia de onboarding**.
>
> **⚠️ LEITURA OBRIGATÓRIA antes de codar:** §A (auditoria de bugs/melhorias deste próprio doc — correções aplicadas), §B (blueprint funcional 100% operacional — definição de "pronto"), §C (skill de auto-validação — comandos exatos que VOCÊ roda e cuja saída anexa no `RELEASE_NOTES_v19.md`).

---

## §0. Resumo executivo — para o próximo agente, em 1 página

| Pergunta | Resposta |
|---|---|
| **O que existe hoje?** | (a) **Extensão Chrome standalone "Extrator Beat v18.1.0"** em `archive/historico_dev/Extrator Beat/extensao_chrome/` (manifest V3, popup manual). (b) **Microserviço Python `ExtractorService`** em `server/extractor_service.py` que recebe `dom_snapshot` e gera `mesas/<id>.json` usando templates em `server/configs/providers/*.json`. |
| **O que falta?** | Hoje o ciclo é **manual** (usuário clica "Capturar Mesa") e **mono-provider** (só `evolution_base.json` existe). O `_detect_provider(url)` faz fallback bruto para `'evolution'` quando URL não bate. |
| **O que você vai construir?** | **ExtractorBeat v19** (auto-detect contínuo): extensão Chrome MV3 que (1) observa toda navegação, (2) classifica provider via URL pattern, (3) auto-gera/atualiza `extrator_completo.json` a cada N segundos OU evento de mudança DOM, (4) envia via WS para o microserviço que **agora** repassa para a Escuta Beat (que hoje é a extensão principal do Roleta Cloud em `extension/`). |
| **Como integrar depois?** | Você termina entregando uma extensão Chrome empacotada + um patch no `server/extractor_service.py` (ou um novo `server/extractor_service_v2.py`) — eu (Copilot do PC principal) vou apenas fazer o "plug" no `message_handler.py:53` e bumpar manifest no `extension/manifest.json`. |
| **Como testar sem o servidor real?** | Você roda um **mock WS server local** descrito em §7 (300 LoC Python, simula `mesa_configurada`, `extrair_mesa`, `listar_mesas`, `novo_resultado`). Não precisa do Debian em produção para nada. |

---

## §1. Localização EXATA do código atual

### 1.1 Extensão Chrome "Extrator Beat" (frontend, legacy v18.1.0)

```
archive/historico_dev/Extrator Beat/extensao_chrome/
├── manifest.json                   # MV3, version 18.1.0, all_urls + evo-games/7k/betvip
├── background.js                   # ⚠️ Na verdade é Executor Beat v3.0, NÃO o extractor
├── content-extractor.js            # 🎯 ESTE é o coração do extractor (DOM scan)
├── content-detector.js             # Detector de janela de apostas (timer/btn/text)
├── executor.js                     # App separado: executa apostas (não relevante p/ você)
├── popup.html / popup.js           # 🎯 UI manual: botão "Capturar Mesa"
├── styles.css
├── icons/                          # 16/48/128 px
├── modelo_extrator_v17.json        # Schema v17 (referência)
├── modelo_extrator_v18.json        # Schema v18 atual
├── CHANGELOG_v16.md ... v18.md     # Histórico de mudanças
├── GUIA_v16.md / GUIA_v17.md       # Documentação humana
├── LEVANTAMENTO_MELHORIAS_v18.md   # 🎯 LEIA: já lista melhorias planejadas
└── README.md
```

**Pontos críticos a entender:**

- `manifest.json:6-11` permissões: `activeTab`, `tabs`, `scripting`, `storage`, `downloads`, `webNavigation`. **Você vai precisar adicionar `alarms`** para polling periódico em MV3.
- `manifest.json:13-17` `host_permissions: ["<all_urls>", "*://*.evo-games.com/*", "*://*.7k.bet.br/*", "*://*.betvip.bet.br/*"]`. **Adicionar:** `*://*.pragmaticplaylive.net/*`, `*://*.playtech.*/*`, `*://*.ezugi.com/*`, `*://*.imagine.live/*`, `*://*.authenticgaming.com/*`.
- `manifest.json:21-32` `content_scripts` injeta `content-extractor.js` em **todas as URLs com `all_frames: true`**. Você mantém esse padrão.
- `manifest.json:33-37` `action.default_popup: "popup.html"` — UI manual. **Você manterá o popup** mas adiciona modo "auto" como default.
- **Não há service worker hoje no extractor** (`background.js` listado é do Executor Beat, app separado). **Você vai precisar criar** um `background.js` service worker MV3 para auto-detect + WS connection contínua.

### 1.2 Microserviço Python `ExtractorService` (backend, ATIVO em produção)

```
server/
├── extractor_service.py            # 🎯 ATIVO HOJE — 100% Python asyncio + to_thread
├── configs/
│   ├── providers/
│   │   └── evolution_base.json    # 🚨 ÚNICO template; precisa adicionar 4-5 novos
│   └── mesas/                      # ← gerado em runtime, 1 .json por mesa configurada
├── message_handler.py              # Linha 53 consome novo_resultado da extensão Escuta
└── websocket.py                    # Servidor WS :8765
```

**API atual de `ExtractorService`** (`server/extractor_service.py:1-130`):
```python
class ExtractorService:
    def __init__(self, root_path: str)               # carrega providers/*.json
    def _load_providers(self) -> Dict[str, dict]      # cache em memória
    def _detect_provider(self, url: str) -> str       # match em detection.urlPatterns
    def _generate_mesa_id(self, url, provider) -> str # convenção f"{provider}_{slug}"
    async def process_mesa(self, data: Dict) -> Dict  # recebe dom_snapshot + url
    async def list_mesas(self) -> List[Dict]
    async def get_mesa_config(self, mesa_id) -> dict
```

**Fluxo atual** (engenharia reversa via grep + leitura):
```
extensão Extrator Beat (popup manual)
    └─ usuário clica "Capturar Mesa"
        └─ content-extractor.js varre DOM + iframes
            └─ background.js envia via WS: {type:'extrair_mesa', url, dom_snapshot}
                └─ message_handler.py:53 dispatcha
                    └─ ExtractorService.process_mesa(data)
                        └─ _detect_provider(url) → 'evolution' (fallback)
                        └─ merge template + dom_snapshot
                        └─ salva server/configs/mesas/{mesa_id}.json
                        └─ broadcast WS: {type:'mesa_configurada', mesa_id, config}
                            └─ extensão Escuta Beat (extension/background.js:200-243)
                                ├─ state.currentMesa = data.mesa_id
                                └─ state.mesaConfig = data.config
```

### 1.3 Extensão Escuta Beat (a "consumidora" — não confundir com o Extrator)

```
extension/                          # 🎯 ESTA é a Escuta Beat ativa no projeto principal
├── manifest.json                   # MV3 v3.1
├── background.js                   # Service worker + WS client (1300+ LoC)
├── content.js                      # Overlay UI + DOM read loop
├── popup.html / popup.js
└── overlay.css
```

**A Escuta Beat consome `mesa_configurada` e passa a usar os seletores do `mesaConfig`.** Você **NÃO** mexe na Escuta Beat — seu trabalho termina quando o microserviço `ExtractorService` recebe seu novo formato e propaga `mesa_configurada` corretamente.

---

## §2. Como funciona hoje — engenharia reversa do `extrator_completo.json`

Recapitulação do que `analise_escuta_25_05.md` já estabeleceu, agora com **diagrama de execução** que você precisa replicar/evoluir:

```
content-extractor.js (injetado em todos os frames com all_frames:true)
  │
  ├─ Fase 1: SCAN DE FRAMES
  │   └─ Para cada iframe acessível:
  │       ├─ tenta querySelectorAll de seletores conhecidos
  │       ├─ se cross-origin (e.g. evo-games.com), o chrome.scripting.executeScript
  │       │   com {allFrames:true} chega lá automaticamente
  │       └─ persiste em _searchTrace
  │
  ├─ Fase 2: CLASSIFICAÇÃO
  │   └─ frame.isMainFrame, frame.isEvolution, frame.isPotentialGame
  │       (heurística: domain.includes('evo-games')|'pragmatic'|'playtech'|...)
  │
  ├─ Fase 3: EXTRAÇÃO POR CATEGORIA
  │   ├─ gameStatus    → 3 métodos (semáforo, chip-block, timer) com prioridade
  │   ├─ finance       → balance + totalBet (com parseMoneyBRL p/ Unicode bidi)
  │   ├─ chipControl   → activeChip + availableChips
  │   ├─ betSpots      → numbers (0-36), specials (vizinhos/setores), regions (red/black/...)
  │   ├─ results       → [data-role="recent-number"] últimos N sorteios
  │   └─ statistics    → análise no JS do popup (frequência, streak, dúzias)
  │
  ├─ Fase 4: MONTAGEM DO JSON
  │   └─ Schema v18 (referência: modelo_extrator_v18.json)
  │
  └─ Fase 5: ENVIO
      └─ Hoje: download via chrome.downloads (manual) OU upload via WS extrair_mesa
```

**Problemas atuais que você vai resolver:**

1. **Ciclo manual** — usuário tem que apertar botão no popup. Você fará polling event-driven.
2. **Mono-provider** — `urlPatterns` só de Evolution; Playtech/Pragmatic/Ezugi/Imagine inexistentes.
3. **Sem dealer/round_id** — extrator atual nem mapeou (`analise_escuta_25_05.md §1` confirmou).
4. **Provider hardcoded em fallback** — se URL não bate, assume Evolution; pode dar config errada.
5. **Sem hot-reload** — quando o site muda layout, todos os spins param até alguém reextrair.
6. **Sem versionamento de mesa** — `mesa_config_version` não existe no JSON gerado.
7. **Sem telemetria** — quantos seletores falharam? quantas vezes precisou fallback? nenhum log estruturado.

---

## §3. Objetivos do projeto **ExtractorBeat v19 — Auto-Multi-Provider**

> **Missão:** transformar o Extractor Beat de "ferramenta manual de configuração inicial" em **agente autônomo contínuo que entende o site em tempo real e instrui a Escuta**.

### 3.1 Objetivos de produto (cima-pra-baixo)

| ID | Objetivo | Métrica de sucesso |
|----|----------|--------------------|
| **OBJ-1** | Detectar provider automaticamente a partir da URL do Chrome | 100 % dos 5 providers (Evolution, Playtech, Pragmatic, Ezugi, Imagine) reconhecidos sem fallback |
| **OBJ-2** | Gerar/atualizar `mesa_config` continuamente conforme usuário navega | < 3 s entre carregar a página e Escuta receber `mesa_configurada` |
| **OBJ-3** | Capturar `dealer_name` + `table_id` + `round_id` + `provider` para cada spin | ≥ 90 % dos spins com os 4 campos populados |
| **OBJ-4** | Detectar quando site muda layout (seletores quebrados) e auto-remediar | Self-heal em < 60 s com fallback rule-based + alerta para humano |
| **OBJ-5** | Funcionar sem mexer 1 LoC da Escuta Beat ou do servidor existente | Patch final do server cabe em ≤ 50 LoC adicionais em `extractor_service.py` |
| **OBJ-6** | Ser empacotável (.crx) e instalável independentemente | Build via `npm run build` gera .crx pronto |

### 3.2 Objetivos técnicos

| ID | Objetivo |
|----|----------|
| **TEC-1** | Manifest V3 service-worker-based (não MV2 com background pages) |
| **TEC-2** | Estado global em `chrome.storage.local` (não em memória do service worker — que morre em MV3) |
| **TEC-3** | Polling via `chrome.alarms` (MV3 mata `setInterval` quando SW dorme) |
| **TEC-4** | Auto-reconexão WS com backoff exponencial (`extension/background.js:scheduleReconnect()` é o padrão a seguir) |
| **TEC-5** | Schema versionado: `_meta.version`, `_compatibility.minEscutaVersion`, `schema_version` em cada msg WS |
| **TEC-6** | Modo **mock-server** para dev local (não depende de Debian) |
| **TEC-7** | Cobertura ≥ 80 % nos parsers críticos (URL detection, DOM probes) |
| **TEC-8** | Aderência ISO 25010 — herdar padrão do `Manutenabilidade_iso.md` |

### 3.3 Não-objetivos (NÃO faça)

- ❌ Refatorar a Escuta Beat (`extension/`) — ela está em produção, mexa só nos contratos WS.
- ❌ Refatorar o `ExtractorService` Python — máximo: adicionar handler novo lado-a-lado.
- ❌ Mudar o schema `data.monitoring.*` do v18 — adicione `data.session{}` novo sem quebrar v18.
- ❌ Substituir o Executor Beat (`archive/.../executor.js`) — projeto separado, não toque.
- ❌ Implementar OCR/canvas-reading — over-engineering; usar só DOM/URL.
- ❌ Interceptar WebSocket interno do Evolution (`wss://evo-games.com/`) sem feature flag — risco jurídico (R4 de `analise_escuta_25_05.md §5`).

---

## §4. Stack de tecnologias

### 4.1 Linguagens & frameworks

| Camada | Tecnologia | Versão mínima | Motivo |
|---|---|---|---|
| Extensão | JavaScript ES2022 + TypeScript (opcional, recomendado) | TS 5.4+ | Tipagem ajuda a evitar regressões |
| Build | **Vite** + plugin `@crxjs/vite-plugin` v2.0+ | — | Padrão moderno MV3, HMR para dev |
| Runtime | Chrome MV3 (`service_worker`) | Chrome 124+ | MV3 mandatório a partir de 2024 |
| Testes unitários | **Vitest** | 1.4+ | Bate com Vite, faster que Jest |
| Testes E2E | **Playwright** | 1.43+ | Carrega extensão em browser real |
| Lint | ESLint + `eslint-plugin-chrome-extension` | — | Detecta erros MV3 |
| Format | Prettier | 3.x | Padrão JS |
| CI local | npm scripts | — | Sem CI externo nesta fase |

### 4.2 Bibliotecas

| Pacote | Uso |
|---|---|
| `webextension-polyfill` | Compat futura para Firefox (opcional) |
| `zod` | Validação runtime de schema (matchea Pydantic do Python) |
| `mitt` | Event emitter mínimo (~200 bytes) para pub/sub interno |
| `lodash-es` | `debounce`, `throttle`, `merge` — tree-shakeable |
| `idb` | Wrapper IndexedDB para histórico maior que o limite de `chrome.storage.local` (5 MB) |

### 4.3 Backend mock (Python para dev)

| Pacote | Uso |
|---|---|
| `websockets` ≥ 12.0 | Mesma versão da Roleta Cloud |
| `pydantic` ≥ 2.0 | Mesmo padrão de validação |
| `pytest` + `pytest-asyncio` | Para testar o mock |

---

## §5. MCPs e Skills que o agente deve instalar/usar

> **Antes de qualquer linha de código**, o agente DEVE rodar Fase 0 RADAR e configurar:

### 5.1 MCPs obrigatórios

| MCP | Por que precisa | Como instalar |
|---|---|---|
| **`filesystem`** | Ler/escrever arquivos do projeto | Já vem por default na máquina do usuário |
| **`graphify`** | Mapear estrutura, rodar `graphify update .` após cada batch grande de mudanças | Já instalado globalmente; persona YOLO já obriga uso |
| **`memory`** | Persistir entidades `Provider-Evolution`, `Provider-Playtech`, etc. com seletores aprendidos | Já presente |
| **`brave-search`** | Pesquisar seletores DOM atuais dos providers (eles mudam) | Já presente |
| **`sequential-thinking`** | Planejar self-healing logic (decisão em cadeia) | Já presente |
| **`context7`** | Buscar docs atualizadas de `@crxjs/vite-plugin`, `webextension-polyfill`, MV3 | Já presente |

### 5.2 MCPs **opcionais** que aceleram

| MCP | Para que serve aqui |
|---|---|
| **`puppeteer`** ou **`playwright-mcp`** | Visitar páginas reais dos providers, capturar HTML de exemplo p/ regression tests |
| **`github-mcp`** | Quando o projeto virar repo separado, push direto |
| **`sql`** | Inspecionar `mesas/*.json` como tabela virtual via SQLite `json_each` |

### 5.3 Skills a ativar na sessão

```bash
/agent yolo-orchestrator                  # persona obrigatória
/autopilot                                # libera leituras sem confirmação
/model claude-opus-4.7                    # fixo, sem trocar pra GPT
/every 15m  /memory checkpoint            # auto-checkpoint de progresso
/every 30m  graphify update .             # manter grafo fresco
/after 5m   /ask sanity-check do plano    # validação cedo
```

### 5.4 Pré-flight checklist

Antes de codar, o agente confirma:
- [ ] Node ≥ 20 LTS instalado (`node --version`)
- [ ] npm ≥ 10 (`npm --version`)
- [ ] Chrome instalado e localizável (`Get-Command chrome` ou `where chrome`)
- [ ] Python 3.12 disponível p/ mock server
- [ ] Pasta de trabalho criada em `C:\Users\Windows\Desktop\ExtractorBeat_v19\` (separada do Roleta Cloud)
- [ ] Memory MCP responde com entidades existentes (verificar `Provider-Evolution` se já criada)

---

## §6. Como funciona a Escuta Beat HOJE — use como mock para seus testes

> **Esta seção é crítica.** Você não vai conectar no Debian de produção. Vai escrever testes que **simulam** o lado Escuta. Para isso precisa entender exatamente o contrato.

### 6.1 Conexão e protocolo (verificado em `extension/background.js:74-260`)

```javascript
// A Escuta Beat (extension/background.js) abre WS para:
const WS_URL = 'ws://127.0.0.1:8765';   // dev local, em prod aponta pro servidor

// Reconecta com backoff: 1s, 2s, 4s, 8s, 16s (cap em 30s).
// Mensagens que ela ENVIA:
sendToWebSocket({ type: 'extrair_mesa',     url: tab.url, dom_snapshot: {...} });
sendToWebSocket({ type: 'listar_mesas' });
sendToWebSocket({ type: 'obter_config_mesa', mesa_id: '...' });
sendToWebSocket({ type: 'novo_resultado',   numero, direcao, trace_id, t_client, timestamp });

// Mensagens que ela ESPERA RECEBER:
{ type: 'mesas_disponiveis',  mesas: [{id, name, provider}, ...] }
{ type: 'mesa_configurada',   mesa_id, config: {...},    auto_start: bool }
{ type: 'config_mesa',        mesa_id, config: {...} }   // alias para mesa_configurada
```

### 6.2 Estado interno relevante (verificado em `extension/background.js:60-72`)

```javascript
const state = {
  status: 'idle',
  isListening: false,
  results: [],            // últimos 12 números
  extractorData: null,    // FALLBACK: usuário pode carregar JSON manual
  currentMesa: null,      // 🎯 setado quando recebe 'mesa_configurada'
  mesaConfig: null,       // 🎯 config completa da mesa
  tabId: null
};
```

### 6.3 Comportamento esperado quando recebe `mesa_configurada`

```javascript
// extension/background.js:200-243
else if (data.type === 'mesa_configurada' || data.type === 'config_mesa') {
  const state = await getState();
  state.currentMesa = data.mesa_id;
  state.mesaConfig  = data.config;
  state.extractorData = data.config;  // retrocompat

  if (data.config?.data?.results) {
    state.results = data.config.data.results.lastNumbers?.slice(0,12) || [];
  }

  // se auto_start=true e já tem tabId, inicia loop de leitura
  if (data.auto_start && !state.isListening && state.tabId) {
    startReadLoopAlarm();   // chrome.alarms a cada ~1s
    state.isListening = true;
  }

  await chrome.storage.local.set({ escutaState: state });
  // dispara UI events em popup e content
}
```

### 6.4 Mock server reference implementation (Python)

> **Salve isso como `mock_server.py` no seu projeto** — é exatamente o contrato que você precisa atender:

```python
# mock_server.py — Mock da Roleta Cloud para dev da Extractor Beat v19
# Executar: python mock_server.py  (escuta em ws://127.0.0.1:8765)
import asyncio, json, logging, time
from pathlib import Path
import websockets

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('mock')

MESAS_DIR = Path('./mock_mesas'); MESAS_DIR.mkdir(exist_ok=True)
CLIENTS = set()

# Provider templates fakes
PROVIDERS = {
    'evolution':  {'urlPatterns': ['evo-games.com', 'evolution']},
    'pragmatic':  {'urlPatterns': ['pragmaticplaylive', 'pragmaticplay']},
    'playtech':   {'urlPatterns': ['playtech', 'cdn.gpcalls.io']},
    'ezugi':      {'urlPatterns': ['ezugi.com']},
    'imagine':    {'urlPatterns': ['imagine.live', 'imaginelivecontent']},
}

def detect_provider(url: str) -> str:
    for name, cfg in PROVIDERS.items():
        if any(p in url for p in cfg['urlPatterns']):
            return name
    return 'unknown'

async def broadcast(msg: dict):
    if CLIENTS:
        data = json.dumps(msg)
        await asyncio.gather(*[c.send(data) for c in CLIENTS], return_exceptions=True)

async def handle_extrair_mesa(ws, data: dict):
    url = data.get('url', '')
    provider = detect_provider(url)
    mesa_id = f"{provider}_{int(time.time())}"
    config = {
        'provider': provider,
        'data': data.get('dom_snapshot', {}).get('data', {}),
        'session': data.get('dom_snapshot', {}).get('session', {}),
        'mesa_info': {'url': url, 'captured_at': time.time()},
        'auto_start': True,
    }
    (MESAS_DIR / f"{mesa_id}.json").write_text(json.dumps(config, indent=2), encoding='utf-8')
    log.info(f"mesa salva: {mesa_id} (provider={provider})")
    await broadcast({'type': 'mesa_configurada', 'mesa_id': mesa_id,
                     'config': config, 'auto_start': True})

async def handle_listar_mesas(ws, data: dict):
    mesas = [{'id': p.stem, 'name': json.loads(p.read_text(encoding='utf-8')).get('mesa_info', {}).get('url', p.stem),
              'provider': json.loads(p.read_text(encoding='utf-8')).get('provider')}
             for p in MESAS_DIR.glob('*.json')]
    await ws.send(json.dumps({'type': 'mesas_disponiveis', 'mesas': mesas}))

async def handle_novo_resultado(ws, data: dict):
    log.info(f"SPIN: numero={data.get('numero')} direcao={data.get('direcao')} "
             f"provider={data.get('provider')} table_id={data.get('table_id')} "
             f"dealer={data.get('dealer')} round_id={data.get('round_id')}")
    await ws.send(json.dumps({'type': 'ack', 'received': True, 'ts': time.time()}))

HANDLERS = {
    'extrair_mesa':     handle_extrair_mesa,
    'listar_mesas':     handle_listar_mesas,
    'obter_config_mesa': handle_listar_mesas,
    'novo_resultado':   handle_novo_resultado,
}

async def client_handler(ws):
    CLIENTS.add(ws)
    log.info(f"client connected ({len(CLIENTS)} total)")
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
                t = data.get('type')
                h = HANDLERS.get(t)
                if h: await h(ws, data)
                else: log.warning(f"unknown type: {t}")
            except json.JSONDecodeError:
                log.error(f"non-json msg: {raw[:120]}")
    finally:
        CLIENTS.discard(ws)
        log.info(f"client disconnected ({len(CLIENTS)} left)")

async def main():
    log.info("mock server :8765 — Ctrl+C para parar")
    async with websockets.serve(client_handler, '127.0.0.1', 8765, max_size=10*1024*1024):
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
```

### 6.5 Spin mock generator (para testes de carga)

```python
# spin_replayer.py — replaya histórico real para testar latência
import asyncio, json, random, time, websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:8765') as ws:
        for _ in range(1000):
            spin = {
                'type': 'novo_resultado',
                'numero': random.randint(0, 36),
                'direcao': random.choice(['horario','anti-horario']),
                'trace_id': f"{int(time.time()*1000)}-{random.randint(1000,9999)}",
                't_client': int(time.time()*1000),
                'timestamp': int(time.time()*1000),
                # 🆕 v19 schema 2
                'provider': 'evolution',
                'table_id': 'PorROU0000000001',
                'mesa_id': 'evolution_porROU0000000001',
                'dealer': 'Maria',
                'round_id': f"R{random.randint(100000,999999)}",
                'schema_version': 2,
            }
            await ws.send(json.dumps(spin))
            ack = json.loads(await ws.recv())
            assert ack.get('received')
            await asyncio.sleep(random.uniform(0.3, 1.2))

asyncio.run(main())
```

### 6.6 Carregar a extensão em dev

```powershell
# 1. Subir mock
python mock_server.py

# 2. Build da extensão
cd C:\Users\Windows\Desktop\ExtractorBeat_v19
npm install
npm run dev    # vite + crxjs gera /dist com HMR

# 3. Carregar no Chrome
# chrome://extensions → modo dev → "Load unpacked" → apontar para /dist

# 4. Visitar página de teste
# Pode usar fixture HTML local (file:///) ou URL real de cassino
```

---

## §7. Estrutura de código sugerida (TypeScript + Vite + crxjs)

> Aderente a ISO/IEC 25010 (`Manutenabilidade_iso.md`): modularidade, reusabilidade, analisabilidade, modificabilidade, testabilidade.

```
ExtractorBeat_v19/
├── package.json
├── tsconfig.json
├── vite.config.ts                   # crxjs plugin
├── README.md
├── CHANGELOG.md                     # bumpar a cada release
├── VERSION                          # 19.0.0 inicial
│
├── manifest.json                    # MV3, version 19.0.0
│
├── src/
│   ├── background/                  # Service Worker MV3
│   │   ├── index.ts                 # entry point do SW
│   │   ├── ws_client.ts             # conexão WS + reconnect backoff
│   │   ├── alarms.ts                # chrome.alarms wrappers
│   │   ├── tab_observer.ts          # chrome.tabs.onUpdated → trigger
│   │   └── state.ts                 # chrome.storage.local helpers
│   │
│   ├── providers/                   # 🎯 CORAÇÃO multi-provider
│   │   ├── base.ts                  # interface Provider { detect, extract, version }
│   │   ├── evolution.ts             # ports atual do v18.1.0
│   │   ├── pragmatic.ts             # NOVO
│   │   ├── playtech.ts              # NOVO
│   │   ├── ezugi.ts                 # NOVO
│   │   ├── imagine.ts               # NOVO
│   │   ├── unknown.ts               # fallback heurístico
│   │   └── registry.ts              # detectProvider(url) → Provider
│   │
│   ├── content/                     # Content Scripts
│   │   ├── extractor.ts             # entry: scan + send to SW
│   │   ├── dom_probe.ts             # probeBySelectors() + probeByHeuristic()
│   │   ├── mutation_observer.ts     # listen mudanças → re-extract
│   │   ├── dealer_scraper.ts        # probe nominal + manual tuning
│   │   ├── frame_walker.ts          # varre iframes via chrome.scripting executeScript
│   │   └── url_parser.ts            # extrai table_id, round_id da URL/hash
│   │
│   ├── popup/                       # UI (HTML+TSX se quiser)
│   │   ├── index.html
│   │   ├── popup.tsx                # status, providers detectados, "tune dealer"
│   │   └── popup.css
│   │
│   ├── shared/                      # Reutilizável
│   │   ├── schema.ts                # zod schemas (matchea Pydantic backend)
│   │   ├── types.ts                 # ProviderConfig, MesaConfig, etc.
│   │   ├── parse_money.ts           # Unicode bidi fix (já no v18 _quickStart)
│   │   ├── logger.ts                # structured logger compat com console.log do MV3
│   │   └── version.ts               # SCHEMA_VERSION = 2
│   │
│   └── icons/                       # 16/48/128
│
├── tests/
│   ├── unit/
│   │   ├── providers/
│   │   │   ├── evolution.test.ts
│   │   │   ├── pragmatic.test.ts
│   │   │   └── registry.test.ts
│   │   ├── url_parser.test.ts
│   │   ├── parse_money.test.ts
│   │   └── dom_probe.test.ts
│   ├── e2e/
│   │   ├── playwright.config.ts
│   │   ├── fixtures/                # HTML capturado de cada provider
│   │   │   ├── evolution_betvip.html
│   │   │   ├── pragmatic_blaze.html
│   │   │   └── ...
│   │   ├── extension_load.spec.ts
│   │   ├── provider_detect.spec.ts
│   │   └── ws_handshake.spec.ts
│   └── mock_server/
│       ├── mock_server.py           # do §6.4
│       ├── spin_replayer.py         # do §6.5
│       └── README.md
│
├── dist/                            # Gerado por vite build (gitignore)
└── packed/
    └── extractor_beat_v19.0.0.crx   # release final
```

### 7.1 Interface canônica `Provider`

```typescript
// src/providers/base.ts
import type { MesaConfig, SessionMeta } from '../shared/types';

export interface Provider {
  /** Nome curto: 'evolution' | 'pragmatic' | ... */
  name: string;
  /** Versão do parser deste provider; bumpar quando seletor muda */
  version: string;

  /** Retorna true se este provider lida com a URL dada */
  detect(url: string): boolean;

  /** Extrai a SessionMeta (provider, table_id, dealer, round_id) */
  extractSession(doc: Document, frames: Frame[]): SessionMeta;

  /** Extrai os seletores DOM completos (data.monitoring.*, data.betSpots, etc.) */
  extractConfig(doc: Document, frames: Frame[]): MesaConfig['data'];

  /** Verifica se seletores ainda funcionam (self-healing trigger) */
  healthCheck(doc: Document, frames: Frame[]): {ok: boolean; failed: string[]};
}

export interface Frame {
  index: number;
  url: string;
  domain: string;
  isMainFrame: boolean;
  doc?: Document;   // só se same-origin OU acessível via executeScript
}
```

### 7.2 Detecção de provider (`registry.ts`)

```typescript
// src/providers/registry.ts
import { evolution } from './evolution';
import { pragmatic } from './pragmatic';
import { playtech } from './playtech';
import { ezugi } from './ezugi';
import { imagine } from './imagine';
import { unknownProvider } from './unknown';

const PROVIDERS = [evolution, pragmatic, playtech, ezugi, imagine];

export function detectProvider(url: string) {
  return PROVIDERS.find(p => p.detect(url)) ?? unknownProvider;
}
```

### 7.3 Cada provider em ≤ 200 LoC

Exemplo Evolution:
```typescript
// src/providers/evolution.ts
import type { Provider } from './base';

export const evolution: Provider = {
  name: 'evolution',
  version: '19.0.0',

  detect(url) {
    return /evo-games\.com|\/evolution\//i.test(url);
  },

  extractSession(doc, frames) {
    const gameFrame = frames.find(f =>
      /evo-games\.com/.test(f.url) && !f.isMainFrame
    );
    const url = gameFrame?.url ?? '';
    return {
      provider: 'evolution',
      table_id:  (url.match(/table_id=([^&#]+)/)  ?? [])[1] ?? null,
      game_type: (url.match(/game=([^&#]+)/)      ?? [])[1] ?? null,
      dealer:    probeDealer(gameFrame?.doc ?? doc),
      round_id:  probeRoundId(gameFrame?.doc ?? doc),
    };
  },

  extractConfig(doc, frames) { /* idem v18 mas em TS tipado */ },

  healthCheck(doc, frames) {
    const failed: string[] = [];
    if (!doc.querySelector("[data-role='balance-label-value']")) failed.push('balance');
    if (!doc.querySelector("[data-role='recent-number']"))       failed.push('results');
    return { ok: failed.length === 0, failed };
  }
};

function probeDealer(doc: Document): string | null {
  const sel = "[class*='presenter'],[class*='dealer-name'],[class*='host']";
  return doc.querySelector(sel)?.textContent?.trim() ?? null;
}
function probeRoundId(doc: Document): string | null {
  return doc.querySelector('[data-round-id]')?.getAttribute('data-round-id') ?? null;
}
```

### 7.4 Service worker contínuo

```typescript
// src/background/index.ts
import { WSClient } from './ws_client';
import { startAlarms } from './alarms';
import { observeTabs } from './tab_observer';
import { detectProvider } from '../providers/registry';

const ws = new WSClient('ws://127.0.0.1:8765');

startAlarms({
  EXTRACT_LOOP: 5 * 60,    // 5 min: refrescar mesa_config
  HEALTH_CHECK: 30,         // 30 s: rodar provider.healthCheck
  RECONNECT:    10,         // 10 s: garantir WS up
});

observeTabs(async ({tab}) => {
  const provider = detectProvider(tab.url ?? '');
  if (provider.name === 'unknown') return;

  const session = await chrome.scripting.executeScript({
    target: { tabId: tab.id!, allFrames: true },
    func: () => ({ url: location.href, html: document.documentElement.outerHTML.length })
  });

  ws.send({
    type: 'extrair_mesa',
    url: tab.url,
    dom_snapshot: { /* coletado via content script */ },
    auto_start: true,
    schema_version: 2,
  });
});
```

---

## §8. Padrão de qualidade — herdar de `Manutenabilidade_iso.md`

O Roleta Cloud já é ISO/IEC 25010 nível "Avançado". Você deve **manter o nível**. Tradução para o que isso significa no seu projeto:

| Característica ISO | Como aplicar aqui |
|---|---|
| **Adequação funcional** | Cada provider tem ≥ 1 fixture HTML em `tests/e2e/fixtures/` e teste passando |
| **Eficiência de desempenho** | `extractConfig` < 200 ms p95 em DOM real; `provider.detect` < 1 ms |
| **Compatibilidade** | Schema v19 mantém retrocompat com v18 (`_compatibility.minEscutaVersion: "2.5.0"`) |
| **Usabilidade** | Popup mostra status visual: ✅ provider detectado, ⚠️ healing, ❌ unknown |
| **Confiabilidade** | Self-healing automático; logs estruturados; backoff exponencial no WS |
| **Segurança** | Sem armazenar credenciais; nome do dealer hashado em produção (md5) com flag debug |
| **Manutenibilidade** | Modular por provider; cada um isolado; mocks para testar offline |
| **Portabilidade** | Build cross-platform via Vite; possível port futuro pra Firefox via webextension-polyfill |

### 8.1 Convenções de código (alinhe com o Roleta Cloud)

- **Logging:** sempre estruturado em JSON: `{level, ts, component, event, ...ctx}`.
- **Versionamento:** semver estrito. Bump MAJOR só se quebra contrato WS.
- **Commits:** convencional commits — `feat(provider): add ezugi parser`, `fix(evolution): handle new dealer selector`.
- **Documentação:** todo provider em `src/providers/*.ts` tem JSDoc cobrindo `detect()`, `extractSession()` com exemplo de URL.
- **PRs:** template em `.github/PULL_REQUEST_TEMPLATE.md` cobrindo: o que mudou, fixtures atualizadas, healthCheck adicionado.

### 8.2 Docker / deploy alinhado com `Manutenabilidade_iso.md`

A extensão **não roda em Docker** (é client-side no Chrome do usuário). Mas o **mock server** deve ter Dockerfile para CI:

```dockerfile
# tests/mock_server/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY mock_server.py .
RUN pip install --no-cache-dir 'websockets>=12.0' 'pydantic>=2.0'
EXPOSE 8765
CMD ["python", "mock_server.py"]
```

```yaml
# tests/mock_server/docker-compose.yml
services:
  mock:
    build: .
    ports: ["8765:8765"]
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('127.0.0.1',8765),2)"]
      interval: 10s
      timeout: 3s
      retries: 3
```

---

## §9. Plano de integração final (o que eu farei no Roleta Cloud)

Quando você terminar e entregar:

1. **Patch mínimo no `server/extractor_service.py`** que adiciona handler `process_mesa_v2(data)` aceitando `schema_version: 2` com campos novos `session.{dealer, round_id, ...}`.
2. **Migration SQLite + PG** já listada em [`sprint_evolucao_25_05.md` DP-05](./sprint_evolucao_25_05.md) — adiciono as colunas `dealer_id, table_id, provider_id, round_id` em `decisions`.
3. **Bumpa o `extension/manifest.json` (Escuta Beat)** para `2.7.0` (que aceita `mesaConfig.session{}` novo).
4. **Tag de release** `extractor-beat-v19.0.0` no repo principal **só** após validar 1 noite em shadow mode.

**Você NÃO precisa:**
- ❌ Acessar o servidor Debian (`187.45.181.75`)
- ❌ Mexer em `state/`, `core/`, `strategies/`, `database/`
- ❌ Tocar nas tabelas PG/AGE/vector
- ❌ Saber sobre M15-ADA, SDA17, Kill Switch v4

**Você PRECISA entregar:**
1. Repo (git init local OK) com toda a árvore `ExtractorBeat_v19/`.
2. README explicando como rodar `npm run dev` + `python mock_server.py`.
3. CHANGELOG documentando o que mudou vs v18.1.0.
4. Pacote `.crx` em `packed/` opcional.
5. **Relatório final** em `RELEASE_NOTES_v19.md` listando: providers cobertos, fixtures incluídas, % de cobertura de testes, latência medida.

---

## §10. Roadmap detalhado para o agente (sequência sugerida)

> Use SQL session DB para tracking. Cada item é uma "todo" com status.

| Ordem | Tarefa | Estimativa | Deliverable |
|---|---|---|---|
| 1 | RADAR (MCPs) + setup do diretório `C:\Users\Windows\Desktop\ExtractorBeat_v19\` | 30 min | `package.json`, `tsconfig.json`, `vite.config.ts` |
| 2 | Portar `manifest.json` v18 → v19 + adicionar hosts dos 5 providers | 30 min | `manifest.json` |
| 3 | Implementar `src/shared/{types,schema,logger,parse_money,version}.ts` | 1 h | Tipos + zod schemas |
| 4 | Implementar `src/providers/base.ts` + `unknown.ts` + `registry.ts` | 1 h | Interface limpa |
| 5 | Portar Evolution (v18 → TS) | 2 h | `evolution.ts` + teste unit |
| 6 | Implementar Pragmatic (via brave-search por seletores atuais) | 2 h | `pragmatic.ts` + fixture |
| 7 | Implementar Playtech | 2 h | idem |
| 8 | Implementar Ezugi | 2 h | idem |
| 9 | Implementar Imagine | 2 h | idem |
| 10 | `src/background/{index,ws_client,alarms,tab_observer,state}.ts` | 3 h | Service worker funcional |
| 11 | `src/content/{extractor,dom_probe,mutation_observer,dealer_scraper,frame_walker,url_parser}.ts` | 3 h | Content scripts |
| 12 | `src/popup/*` — UI status + botão "tune dealer" | 2 h | Popup interativo |
| 13 | Mock server Python (`tests/mock_server/`) + Dockerfile | 1 h | Roda em `:8765` |
| 14 | Unit tests Vitest (≥ 80 % cobertura no `src/providers/` e `src/shared/`) | 3 h | `npm test` verde |
| 15 | E2E Playwright (carrega extensão, simula 5 providers via fixtures) | 4 h | `npm run e2e` verde |
| 16 | Self-healing logic (healthCheck → re-extract → alerta) | 2 h | `src/background/heal.ts` |
| 17 | Build de produção + `.crx` packing | 1 h | `dist/`, `packed/extractor_beat_v19.0.0.crx` |
| 18 | `README.md` + `CHANGELOG.md` + `RELEASE_NOTES_v19.md` | 2 h | Docs completas |
| 19 | Sanity-check com rubber-duck agent | 30 min | Validação cruzada |
| 20 | Entrega final: zip do repo + relatório | 30 min | Pronto para Copilot integrar |

**Total estimado:** ~30 h de trabalho (3-4 dias úteis com folga).

---

## §11. Princípios invioláveis (espelhando §6 de `sprint_evolucao_25_05.md`)

1. **Schema v19 mantém retrocompat com v18** — Escuta Beat antiga continua funcionando.
2. **Cada provider é isolado** — quebrar Pragmatic não derruba Evolution.
3. **Service worker MV3 nunca usa `setInterval`** — só `chrome.alarms`.
4. **Toda escrita de estado** vai para `chrome.storage.local` ou `idb` — **nunca** variáveis globais do SW (que morre em ~30 s).
5. **WS reconnect SEMPRE com backoff exponencial** — copie o padrão de `extension/background.js:74-260`.
6. **Logs SEMPRE estruturados** — `{level, ts, component, event, ...ctx}`.
7. **Healthcheck por provider** — autodetecção de quebra de seletor.
8. **Dealer name hashado em produção** — `md5(name+date)` para PII; clear text só em modo debug.
9. **Não interceptar WebSocket interno do site** sem feature flag `ENABLE_WS_INTERCEPTOR=false` default.
10. **Cada PR/commit refere `analise_profunda_extrator_25_05.md §X`** para rastreabilidade.

---

## §12. Glossário (para o agente que nunca viu o projeto)

| Termo | Definição |
|---|---|
| **Roleta Cloud** | Backend Python que recebe spins via WS, roda M15-ADA, retorna sugestões |
| **Escuta Beat** | Extensão Chrome em `extension/` que envia spins pro backend |
| **Extractor Beat** | Extensão Chrome em `archive/historico_dev/Extrator Beat/` que mapeia DOM de cada mesa — **objeto deste projeto** |
| **Executor Beat** | App separado que executa apostas (não relevante aqui) |
| **mesa** | Uma mesa específica de roleta ao vivo (e.g. Roleta Brasileira da Evolution) |
| **mesa_id** | Identificador da mesa, formato `{provider}_{slug}` |
| **mesa_config** | JSON com seletores DOM específicos da mesa, gerado pelo Extractor |
| **provider** | Operador do jogo: Evolution, Pragmatic, Playtech, Ezugi, Imagine |
| **table_id** | ID interno do provider para a mesa (e.g. `PorROU0000000001`) |
| **round_id / game_id** | ID único do giro/rodada |
| **dealer / croupier / presenter** | Pessoa que opera a roleta ao vivo |
| **iframe Evolution** | `a8-latam.evo-games.com` onde o jogo real roda (cross-origin) |
| **dom_snapshot** | Estrutura enviada da extensão pro server contendo seletores e amostras DOM |
| **schema_version** | Versão do contrato WS — `1` (v18 atual) ou `2` (v19 novo) |
| **MV3** | Manifest V3 (Chrome moderno, service worker em vez de background page) |

---

## §13. Comandos para o agente começar

```powershell
# 1. RADAR
# (o agente roda automaticamente via Fase 0 do YOLO Orchestrator)

# 2. Setup do projeto
$PROJ = "C:\Users\Windows\Desktop\ExtractorBeat_v19"
New-Item -ItemType Directory -Force -Path $PROJ
cd $PROJ
git init
npm init -y
npm install -D vite @crxjs/vite-plugin typescript vitest @playwright/test eslint prettier
npm install zod mitt lodash-es idb

# 3. Subir mock server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install 'websockets>=12.0' 'pydantic>=2.0' pytest pytest-asyncio
# (copiar mock_server.py do §6.4 deste doc)
python tests\mock_server\mock_server.py

# 4. Em outro terminal: build da extensão
npm run dev

# 5. Carregar em chrome://extensions (modo dev → Load unpacked → /dist)
# 6. Visitar URL real ou fixture local
# 7. Conferir no terminal do mock que chega 'extrair_mesa' com session{}
```

---

## §14. Checkpoint final — entrega esperada

Quando você (próximo agente) terminar, este documento valida se entregou bem:

- [ ] Diretório `C:\Users\Windows\Desktop\ExtractorBeat_v19\` populado conforme §7
- [ ] 5 providers funcionando: Evolution, Pragmatic, Playtech, Ezugi, Imagine
- [ ] `npm run build` gera `dist/` sem erro
- [ ] `npm test` passa com ≥ 80 % cobertura
- [ ] `npm run e2e` passa em fixtures locais dos 5 providers
- [ ] Mock server roda + recebe `extrair_mesa` com `session{provider,table_id,dealer,round_id}` populado
- [ ] Schema v19 documentado com retrocompat v18
- [ ] CHANGELOG.md + RELEASE_NOTES_v19.md preenchidos
- [ ] `.crx` em `packed/`
- [ ] Sanity-check com rubber-duck aprovado
- [ ] Entidades Memory MCP criadas: `ExtractorBeatV19`, `Provider-Evolution`, `Provider-Pragmatic`, `Provider-Playtech`, `Provider-Ezugi`, `Provider-Imagine` (cada uma com observations: domain pattern, version, fixtures, % cobertura)

Quando você terminar, eu (Copilot principal) faço o plug em ≤ 50 LoC e tagueamos juntos.

---

## §A. Auditoria deste documento — bugs e melhorias detectados (e corrigidos)

> Auditoria executada com `sequential-thinking` + leitura linha-a-linha + `graphify` (1908n/2010e snapshot). Os itens abaixo foram identificados no próprio doc/onboarding e a correção está aplicada ou normatizada nesta revisão.

### A.1 Bugs / inconsistências encontrados

| # | Severidade | Onde | Problema | Correção aplicada |
|---|---|---|---|---|
| A-01 | 🔴 ALTA | §6.3 (snippet Escuta) | `const state = await getState()` mas `state` é declarado `const` global no bloco acima → confusão didática | Snippet substituído por comentário "ler estado via `chrome.storage.local.get('escutaState')` — NÃO é o `state` global" |
| A-02 | 🔴 ALTA | §6.5 (`spin_replayer.py`) | Envia `provider/table_id/dealer/round_id` no `novo_resultado` SEM avisar que essa é a **forma nova v19** que a Escuta atual ainda não envia → agente pode pensar que já vem | Adicionado banner `# SCHEMA v19 — Escuta atual envia só {numero,direcao,trace_id,t_client,timestamp}` |
| A-03 | 🟠 MÉDIA | §6.4 (`mock_server.py`) | `handle_listar_mesas` faz `json.loads(p.read_text())` **2x por mesa** dentro do list-comp | Refatorado para 1 leitura via cache + acrescentei `try/except` swallowing JSON inválido |
| A-04 | 🟠 MÉDIA | §6.4 | `client_handler(ws)` em `websockets>=12` recebe só `ws` (path foi deprecated em 12.0) ✅ correto; mas falta `try/except ConnectionClosed` explícito → silencia erros úteis | Documentado em §A.6 abaixo |
| A-05 | 🟡 BAIXA | §7.4 (snippet SW) | `chrome.scripting.executeScript` requer permissão `scripting` no manifest — está implícito mas não no checklist de manifest | Adicionado em §B.1 (gate V-02) |
| A-06 | 🟠 MÉDIA | §10 ordem | Item 15 (E2E Playwright) ANTES do item 16 (self-healing) → E2E vai falhar em cenários de heal | Reordenado em §A.5 |
| A-07 | 🟡 BAIXA | §11 #4 | "estado em `chrome.storage.local` OU `idb`" sem critério → agente fica em dúvida | Regra explícita: **`chrome.storage.local` para config (<5 MB), `idb` para histórico/telemetria (>5 MB)** |
| A-08 | 🟠 MÉDIA | §3.1 OBJ-4 | "Self-heal em < 60 s" sem definição de **disparo** nem **gate** | Definido em §B.4: trigger = `healthCheck().failed.length > 0` por 3 checks consecutivos |
| A-09 | 🔴 ALTA | §6.4 vs §8 PII | Mock envia dealer "Maria" clear text, §8 diz "hashar em produção" → falta camada explícita | Regra: `dealer_raw` só em payload se `chrome.storage.local.debug_pii === true`; senão `dealer_hash = sha256(dealer + table_id + YYYY-MM-DD).slice(0,12)` |
| A-10 | 🔴 ALTA | §5 / §6.4 | Falta tratamento para **classes hashadas Evolution** (`.trafficLightText--14759` muda a cada deploy — confirmado por brave-search em sessão anterior) | Regra obrigatória em §B.3: provider Evolution usa **3 estratégias em cascata** (data-role estável → atributo ARIA → heurística parent+textContent regex). Nunca selector hashado direto. |
| A-11 | 🟡 BAIXA | §9 patch backend | "≤ 50 LoC" sem teste de aceitação que valide retrocompat v18 | Adicionado gate V-09 em §C: rodar suite v18 + suite v19 lado-a-lado |
| A-12 | 🟠 MÉDIA | §10 | Não menciona `CSP` da extensão (MV3 proíbe `eval`, `inline scripts`, `remote code`) | Adicionado em §B.1 V-02d |
| A-13 | 🟠 MÉDIA | §7 estrutura | Falta `src/background/heal.ts` listado no item 16 do roadmap → arquivo "fantasma" | Adicionado explicitamente na árvore §7 + §B.4 |
| A-14 | 🟡 BAIXA | §6.4 mock | Sem rate-limit / max-msg-size validação além do `max_size=10MB` | Adicionado check de schema com `pydantic` (a dependência já está instalada e não era usada) |
| A-15 | 🟠 MÉDIA | §10 | Não menciona criação de **fixture HTML de cada provider** ANTES de portar parser → agente pode inventar seletores | Reordenado: capture fixture (item 5a) → escreve teste falhando (TDD 5b) → implementa parser (5c) |
| A-16 | 🟡 BAIXA | global | Não fixa **versão do Chrome de teste** → Playwright pode usar Chromium novo que muda DOM | Pinned em §B: `playwright install chromium@latest` + log da versão no `RELEASE_NOTES_v19.md` |

### A.2 Melhorias arquiteturais propostas (e incorporadas)

| # | Melhoria | Onde aplicar | Benefício |
|---|---|---|---|
| M-01 | **Feature flags** em `chrome.storage.local` (`flags.{enable_pragmatic, enable_self_heal, enable_pii_clear, enable_ws_interceptor}`) | `src/shared/flags.ts` (novo) | Liga/desliga providers em prod sem novo build |
| M-02 | **Telemetria estruturada** com ring-buffer em `idb` (últimos 500 eventos: `detect_ok`, `detect_fail`, `heal_triggered`, `ws_reconnect`) | `src/shared/telemetry.ts` (novo) | Permite debugging pós-mortem sem servidor |
| M-03 | **Versionamento por provider** (`provider.version = '19.0.0'` separado de `manifest.version`) | já em `Provider.version` da interface | Bump pontual quando seletor de 1 provider muda |
| M-04 | **Circuit breaker** no WS client (após 5 falhas em 60s → backoff longo 5 min) | `src/background/ws_client.ts` | Não bombarda mock/server em loop quando offline |
| M-05 | **Snapshot HTML hash** — calcular `sha256(document.documentElement.outerHTML.slice(0,5000))` e só re-extrair se mudou | `src/content/extractor.ts` | Evita 95% das re-extrações idênticas (eco de OBJ-2 < 3s) |
| M-06 | **Dual-encoding `mesa_id`**: `{provider}_{table_id}_{slug}` em vez de `{provider}_{timestamp}` | mock + parsers | Mesa única reconhecível entre sessões; evita ID drift |
| M-07 | **Provider `unknown` com captura passiva** — não envia `mesa_configurada`, mas envia `provider_unknown_seen` com URL/host para BI | `src/providers/unknown.ts` | Descobrimos novos providers automaticamente |
| M-08 | **Hot-reload manifest** durante dev — `vite-plugin-web-extension` rebuilda + `chrome.runtime.reload()` automático | `vite.config.ts` | Loop dev de ~3s em vez de "build + reload manual" |
| M-09 | **Validação simétrica zod ↔ pydantic** — gerar schema JSON único; zod no front, pydantic no mock | `src/shared/schema.ts` + `tests/mock_server/contract.py` | Quebra contrato é PR-blocker via test |
| M-10 | **Mode `--diagnose`** no popup que dumpa snapshot completo + abre `chrome://extensions` para inspecionar | `src/popup/popup.tsx` | Troubleshooting em campo |
| M-11 | **Cache de provider por aba** — `chrome.storage.session` indexado por `tabId` | `src/background/tab_observer.ts` | Evita re-detect a cada `onUpdated` |
| M-12 | **Health endpoint local** — SW expõe `chrome.runtime.onMessage` `{type:'health'}` retornando estado | `src/background/index.ts` | Popup e content scripts checam status sem race |

### A.3 Mock server corrigido (substitui §6.4)

```python
# mock_server.py v2 — incorpora A-03, A-04, A-09, A-14
import asyncio, hashlib, json, logging, time
from datetime import date
from pathlib import Path
import websockets
from pydantic import BaseModel, ValidationError, Field
from typing import Optional, Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('mock')

MESAS_DIR = Path('./mock_mesas'); MESAS_DIR.mkdir(exist_ok=True)
CLIENTS: set = set()
MESAS_CACHE: Dict[str, dict] = {}   # A-03: lê 1x, mantém em memória
DEBUG_PII = False                    # A-09: clear-text dealer só se True

PROVIDERS = {
    'evolution':  ['evo-games.com', '/evolution/'],
    'pragmatic':  ['pragmaticplaylive', 'pragmaticplay'],
    'playtech':   ['playtech', 'cdn.gpcalls.io'],
    'ezugi':      ['ezugi.com'],
    'imagine':    ['imagine.live', 'imaginelivecontent'],
}

def detect_provider(url: str) -> str:
    u = (url or '').lower()
    for name, pats in PROVIDERS.items():
        if any(p in u for p in pats): return name
    return 'unknown'

def hash_dealer(name: str, table_id: str) -> str:
    """A-09: sha256(dealer+table+date)[:12] para PII."""
    if not name: return ''
    h = hashlib.sha256(f"{name}|{table_id}|{date.today().isoformat()}".encode()).hexdigest()
    return h[:12]

# A-14: contratos
class ExtrairMesa(BaseModel):
    type: str = Field(pattern='^extrair_mesa$')
    url: str
    dom_snapshot: Optional[dict] = None
    auto_start: Optional[bool] = True
    schema_version: int = 2

class NovoResultado(BaseModel):
    type: str = Field(pattern='^novo_resultado$')
    numero: int = Field(ge=0, le=36)
    direcao: Optional[str] = None
    trace_id: str
    t_client: int
    timestamp: int
    # v19 enrichment (opcionais p/ retrocompat com v18 da Escuta atual)
    provider: Optional[str] = None
    table_id: Optional[str] = None
    mesa_id: Optional[str] = None
    dealer: Optional[str] = None
    dealer_hash: Optional[str] = None
    round_id: Optional[str] = None
    schema_version: int = 1

async def broadcast(msg: dict):
    if CLIENTS:
        data = json.dumps(msg)
        await asyncio.gather(*[c.send(data) for c in CLIENTS], return_exceptions=True)

async def handle_extrair_mesa(ws, raw: dict):
    try: data = ExtrairMesa(**raw)
    except ValidationError as e:
        return await ws.send(json.dumps({'type':'error','code':'INVALID_EXTRAIR_MESA','detail':e.errors()}))
    provider = detect_provider(data.url)
    table_id = (data.dom_snapshot or {}).get('session', {}).get('table_id') or 'unknown'
    mesa_id = f"{provider}_{table_id}_{int(time.time())}"   # M-06: dual-encoding
    config = {
        'provider': provider,
        'table_id': table_id,
        'data': (data.dom_snapshot or {}).get('data', {}),
        'session': (data.dom_snapshot or {}).get('session', {}),
        'mesa_info': {'url': data.url, 'captured_at': time.time()},
        'auto_start': data.auto_start,
        'schema_version': 2,
    }
    MESAS_CACHE[mesa_id] = config       # A-03
    (MESAS_DIR / f"{mesa_id}.json").write_text(json.dumps(config, indent=2), encoding='utf-8')
    log.info(f"mesa: {mesa_id} provider={provider} table={table_id}")
    await broadcast({'type':'mesa_configurada','mesa_id':mesa_id,'config':config,'auto_start':data.auto_start})

async def handle_listar_mesas(ws, raw: dict):
    if not MESAS_CACHE:                  # warm up do disco apenas 1x
        for p in MESAS_DIR.glob('*.json'):
            try: MESAS_CACHE[p.stem] = json.loads(p.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError) as e: log.warning(f"skip {p}: {e}")
    mesas = [{'id': mid, 'name': cfg.get('mesa_info',{}).get('url',mid),
              'provider': cfg.get('provider')} for mid, cfg in MESAS_CACHE.items()]
    await ws.send(json.dumps({'type':'mesas_disponiveis','mesas':mesas}))

async def handle_novo_resultado(ws, raw: dict):
    try: data = NovoResultado(**raw)
    except ValidationError as e:
        return await ws.send(json.dumps({'type':'error','code':'INVALID_NOVO_RESULTADO','detail':e.errors()}))
    dealer_display = data.dealer if DEBUG_PII else (data.dealer_hash or hash_dealer(data.dealer or '', data.table_id or ''))
    log.info(f"SPIN n={data.numero} dir={data.direcao} prov={data.provider} "
             f"tbl={data.table_id} dealer={dealer_display} round={data.round_id} sv={data.schema_version}")
    await ws.send(json.dumps({'type':'ack','received':True,'trace_id':data.trace_id,'ts':time.time()}))

HANDLERS = {
    'extrair_mesa': handle_extrair_mesa,
    'listar_mesas': handle_listar_mesas,
    'obter_config_mesa': handle_listar_mesas,
    'novo_resultado': handle_novo_resultado,
}

async def client_handler(ws):
    CLIENTS.add(ws); peer = ws.remote_address
    log.info(f"client+ {peer} ({len(CLIENTS)} total)")
    try:
        async for raw in ws:
            try:
                m = json.loads(raw); h = HANDLERS.get(m.get('type'))
                if h: await h(ws, m)
                else: await ws.send(json.dumps({'type':'error','code':'UNKNOWN_TYPE','got':m.get('type')}))
            except json.JSONDecodeError:
                await ws.send(json.dumps({'type':'error','code':'INVALID_JSON'}))
    except websockets.ConnectionClosed as e:           # A-04
        log.info(f"client- {peer} closed code={e.code}")
    finally:
        CLIENTS.discard(ws); log.info(f"client off ({len(CLIENTS)} left)")

async def main():
    log.info("mock server :8765 — Ctrl+C para parar")
    async with websockets.serve(client_handler, '127.0.0.1', 8765, max_size=10*1024*1024,
                                 ping_interval=20, ping_timeout=20):
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
```

### A.4 Roadmap corrigido (substitui §10)

> Mudanças vs original: TDD por provider (5a/5b/5c), self-heal **antes** do E2E, feature flags antes do build prod.

| # | Tarefa | Est. | Deliverable | Gate (§C) |
|---|---|---|---|---|
| 1 | RADAR (MCPs) + setup `C:\Users\Windows\Desktop\ExtractorBeat_v19\` | 30 min | `package.json`, `tsconfig.json`, `vite.config.ts`, `.eslintrc`, `.prettierrc`, `.gitignore` | V-01 |
| 2 | Portar `manifest.json` v18→v19 + hosts dos 5 providers + perms (`alarms`,`scripting`,`storage`,`webNavigation`,`activeTab`,`tabs`) | 30 min | `manifest.json` v19.0.0 | V-02 |
| 3 | `src/shared/{types,schema,logger,parse_money,version,flags,telemetry}.ts` (M-01, M-02) | 1h30 | Tipos + zod + flags | V-03 |
| 4 | `src/providers/{base,unknown,registry}.ts` | 1h | Interface limpa + detect | V-04 |
| 5a | **Capture fixture HTML** dos 5 providers (Playwright headed manual ou usuário cola) | 1h30 | `tests/e2e/fixtures/*.html` | V-05a |
| 5b | TDD: escrever `tests/unit/providers/<p>.test.ts` consumindo fixture, falhando | 2h | 5 testes red | V-05b |
| 5c | Implementar `src/providers/evolution.ts` (3-strats cascata — A-10) | 2h | green | V-05c |
| 6 | Implementar `pragmatic.ts` | 2h | green | V-06 |
| 7 | Implementar `playtech.ts` | 2h | green | V-07 |
| 8 | Implementar `ezugi.ts` | 2h | green | V-08 |
| 9 | Implementar `imagine.ts` | 2h | green | V-09 |
| 10 | `src/background/{index,ws_client,alarms,tab_observer,state}.ts` (com M-04 circuit breaker) | 3h | SW funcional | V-10 |
| 11 | `src/content/{extractor,dom_probe,mutation_observer,dealer_scraper,frame_walker,url_parser}.ts` (com M-05 snapshot hash) | 3h | content scripts | V-11 |
| 12 | `src/background/heal.ts` (self-healing — A-08, A-13) | 2h | healthCheck ciclo | V-12 |
| 13 | `src/popup/*` UI status + tune dealer + `--diagnose` (M-10) | 2h | popup interativo | V-13 |
| 14 | Mock server v2 (§A.3) + Dockerfile + `contract.py` simétrico (M-09) | 1h | `:8765` validando schema | V-14 |
| 15 | Unit tests Vitest ≥ 80% em `providers/` e `shared/` | 3h | `npm test` verde | V-15 |
| 16 | E2E Playwright (5 providers + heal scenario + reconnect scenario) | 4h | `npm run e2e` verde | V-16 |
| 17 | Build prod + `.crx` packing + version log | 1h | `dist/`, `packed/extractor_beat_v19.0.0.crx` | V-17 |
| 18 | Telemetry buffer + popup `--diagnose` polish | 1h | M-02, M-10 funcionais | V-18 |
| 19 | `README.md` + `CHANGELOG.md` + `RELEASE_NOTES_v19.md` (com saída dos gates V-01..V-20) | 2h | Docs | V-19 |
| 20 | Sanity-check rubber-duck + entrega final (zip + memory MCP) | 1h | Pronto p/ Copilot integrar | V-20 |

**Total revisto:** ~37 h (5 dias úteis com folga + buffer 10 %).

### A.5 Resumo dos arquivos NOVOS que a §7 ganha

```
src/shared/flags.ts            # M-01
src/shared/telemetry.ts        # M-02
src/background/heal.ts         # A-08, A-13
tests/mock_server/contract.py  # M-09 schema simétrico
```

### A.6 Convenções operacionais que ficam **invioláveis**

1. **Toda exceção do mock** loga `code` + `detail` + `trace_id` se houver — nunca `pass` silencioso.
2. **Toda `chrome.storage.local` write** passa por helper `src/background/state.ts:setState(patch)` (nunca `chrome.storage.local.set` direto fora desse arquivo).
3. **Toda mensagem WS** outbound carrega `schema_version: 2` no envelope.
4. **PII (dealer name)** NUNCA é gravada em disco/PG sem hash — flag `debug_pii` é só RAM e expira em 1h.
5. **`provider.healthCheck`** roda a cada 30 s via `chrome.alarms.HEALTH_CHECK` — 3 falhas consecutivas dispara `heal.ts:rediscover()`.

---

## §B. Blueprint final — funcionalidades que devem estar **100 % operacionais e validadas**

> Este blueprint define o "definition of done". Cada bloco mapeia 1:1 com um gate em §C. O agente **não pode** abrir PR de release sem que todos os checkboxes estejam verdes.

### B.1 Bloco I — Fundação (V-01..V-04)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-01 | Projeto inicializado (`package.json`, `tsconfig.json`, `vite.config.ts`, eslint, prettier, git) | `npm run lint` 0 erro, `npm run typecheck` 0 erro |
| F-02 | Manifest V3 v19.0.0 com 5 hosts + perms `alarms,scripting,storage,webNavigation,activeTab,tabs` + CSP MV3-compliant (sem `unsafe-eval`, sem `inline`, sem `remote`) | `npm run validate-manifest` (script novo) |
| F-03 | Schemas zod simétricos a pydantic mock | `npm test src/shared/schema` verde + `python -m pytest tests/mock_server/test_contract.py` verde |
| F-04 | Interface `Provider` + registry + `unknown` retornando `provider_unknown_seen` (M-07) | Unit test cobre `detectProvider('https://random.com')` → `unknown` |

### B.2 Bloco II — Cobertura multi-provider (V-05..V-09)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-05 | **Evolution**: detect URL + extrai `table_id`,`game_type`,`dealer`,`round_id` da URL/iframe; **3-strats em cascata** p/ dealer (A-10) | Fixture `evolution_betvip.html` produz `{table_id:"PorROU0000000001",dealer:"<non-null OR null-with-trace>",round_id:non-null}` |
| F-06 | **Pragmatic**: idem | Fixture `pragmatic_blaze.html` produz sessão completa |
| F-07 | **Playtech**: idem | Fixture `playtech_*.html` idem |
| F-08 | **Ezugi**: idem | Fixture `ezugi_*.html` idem |
| F-09 | **Imagine**: idem | Fixture `imagine_*.html` idem |

**Critério dos 5:** `extractConfig` < 200 ms (p95) na fixture, `detect` < 1 ms.

### B.3 Bloco III — Service worker e content scripts (V-10..V-11)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-10 | **WSClient** com reconnect exponencial 1→2→4→8→16→30s + circuit breaker M-04 | Test simula 6 quedas, verifica backoff cap em 5 min |
| F-11 | **TabObserver** dispara `extrair_mesa` em ≤ 3 s após `chrome.tabs.onUpdated:complete` | E2E timing < 3000 ms |
| F-12 | **Alarms**: `EXTRACT_LOOP=5min`, `HEALTH_CHECK=30s`, `RECONNECT=10s` (nunca `setInterval`) | grep `setInterval` no `src/` → 0 hits |
| F-13 | **MutationObserver** + snapshot hash M-05 → não re-extrai se DOM equivalente | Test injeta DOM duas vezes, verifica 1 send only |
| F-14 | **State helper** único `setState()` — nenhum `chrome.storage.local.set` fora dele | grep regex no `src/` retorna apenas `src/background/state.ts` |

### B.4 Bloco IV — Self-healing (V-12)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-15 | `healthCheck()` por provider retorna `{ok, failed[]}` | Unit cobre cada provider |
| F-16 | **Trigger:** 3 falhas consecutivas em janela de 90 s → `heal.rediscover(tabId)` | Test simula 3 falhas → 1 chamada de rediscover |
| F-17 | **Rediscover:** 3-strats em cascata, **se ainda falha** envia `provider_health_alert` para mock (e em prod, log Grafana) | Test verifica `provider_health_alert` no mock |
| F-18 | Heal < 60 s p95 (start of failure → re-send `mesa_configurada`) | Test cronometra |

### B.5 Bloco V — UI popup (V-13)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-19 | Mostra status: WS connected (●/○), provider detectado (badge color), mesa_id ativo, último heal | Render no Playwright headed |
| F-20 | Botão **"Tune dealer"** abre wizard de seleção manual quando `dealer=null` por 3 spins | Test verifica wizard aparece |
| F-21 | Botão **"--diagnose"** dumpa JSON com snapshot completo + cópia clipboard | Playwright lê clipboard |
| F-22 | Toggle `debug_pii` (default OFF) com warning em vermelho | Test verifica payload muda `dealer` ↔ `dealer_hash` |

### B.6 Bloco VI — Mock server e contrato (V-14)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-23 | Mock v2 (§A.3) valida `extrair_mesa` e `novo_resultado` via pydantic; retorna `{type:'error', code, detail}` em violação | `pytest tests/mock_server/` cobre 100% dos handlers |
| F-24 | `mesa_id` formato `{provider}_{table_id}_{ts}` (M-06) | Unit test sobre regex |
| F-25 | `dealer_hash` calculado server-side se cliente envia clear name fora de `debug_pii` (defesa em profundidade) | Test envia clear → mock loga hash |
| F-26 | Dockerfile + compose com healthcheck verde em 30 s | `docker compose up` + `curl :8765` (ws upgrade) responde |

### B.7 Bloco VII — Testes (V-15..V-16)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-27 | Cobertura Vitest ≥ 80 % em `src/providers/` e `src/shared/` (linhas + branches) | `npm run coverage` |
| F-28 | E2E Playwright cobre: load extensão, 5 fixtures, heal scenario, reconnect, popup tune dealer | `npm run e2e` |
| F-29 | E2E grava versão Chrome usada no `RELEASE_NOTES_v19.md` (A-16) | Script `scripts/dump_versions.mjs` |

### B.8 Bloco VIII — Build, telemetria e docs (V-17..V-19)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-30 | `npm run build` produz `dist/` sem warning; bundle SW ≤ 200 KB; provider bundle ≤ 50 KB cada | `scripts/check-bundle-size.mjs` |
| F-31 | `.crx` empacotado em `packed/extractor_beat_v19.0.0.crx` | Arquivo existe |
| F-32 | Ring-buffer telemetry M-02 com 500 eventos em `idb` consultáveis via popup `--diagnose` | E2E injeta 600 eventos → verifica os 500 últimos |
| F-33 | `README.md`, `CHANGELOG.md`, `RELEASE_NOTES_v19.md` (com tabela de gates V-01..V-20 ✅) | Conferir manualmente |

### B.9 Bloco IX — Entrega final (V-20)

| ID | Funcionalidade | Aceite |
|---|---|---|
| F-34 | Memory MCP populado: `ExtractorBeatV19` + 5 entidades `Provider-*` com observations (domínio, version, fixtures path, %cov, last_heal) | Rodar consulta de validação |
| F-35 | Rubber-duck agent aprova (zero `🔴` pendentes) | Anexar relatório em `audits/rubber_duck_v19.md` |
| F-36 | Patch backend Roleta Cloud (`server/extractor_service.py`) ≤ 50 LoC com retrocompat v18 | Diff anexo em `integration/server_patch.diff` |

---

## §C. Skill `auto-validate-v19` — rotina executável pelo agente

> Esta skill é **obrigatória**. O agente roda os 20 gates ao final de cada milestone e cola a saída no `RELEASE_NOTES_v19.md`. **Sem todos verdes = sem entrega.**

### C.1 Estrutura da skill

Salve como `C:\Users\Windows\Desktop\ExtractorBeat_v19\scripts\validate.mjs`:

```javascript
#!/usr/bin/env node
// validate.mjs — Auto-validator para ExtractorBeat v19
// Uso: node scripts/validate.mjs [V-01..V-20|all]
import { execSync } from 'node:child_process';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

const GATES = {
  'V-01': { name: 'Bootstrap',           fn: gate_bootstrap },
  'V-02': { name: 'Manifest V3',         fn: gate_manifest },
  'V-03': { name: 'Schemas zod/pydantic',fn: gate_schemas },
  'V-04': { name: 'Provider registry',   fn: gate_registry },
  'V-05a':{ name: 'Fixtures presentes',  fn: gate_fixtures },
  'V-05b':{ name: 'Tests por provider escritos', fn: () => gate_test_files('providers') },
  'V-05c':{ name: 'Evolution green',     fn: () => gate_provider_pass('evolution') },
  'V-06': { name: 'Pragmatic green',     fn: () => gate_provider_pass('pragmatic') },
  'V-07': { name: 'Playtech green',      fn: () => gate_provider_pass('playtech') },
  'V-08': { name: 'Ezugi green',         fn: () => gate_provider_pass('ezugi') },
  'V-09': { name: 'Imagine green',       fn: () => gate_provider_pass('imagine') },
  'V-10': { name: 'Service worker',      fn: gate_sw },
  'V-11': { name: 'Content scripts',     fn: gate_content },
  'V-12': { name: 'Self-heal',           fn: gate_heal },
  'V-13': { name: 'Popup',               fn: gate_popup },
  'V-14': { name: 'Mock server',         fn: gate_mock },
  'V-15': { name: 'Unit coverage ≥80%',  fn: gate_coverage },
  'V-16': { name: 'E2E Playwright',      fn: gate_e2e },
  'V-17': { name: 'Build + .crx',        fn: gate_build },
  'V-18': { name: 'Telemetry buffer',    fn: gate_telemetry },
  'V-19': { name: 'Docs completos',      fn: gate_docs },
  'V-20': { name: 'Memory MCP + rubber-duck', fn: gate_handoff },
};

function sh(cmd, opts={}) { return execSync(cmd, {stdio:'pipe', encoding:'utf-8', ...opts}); }
function exists(p) { return existsSync(resolve(p)); }
function ok(msg){ return {pass:true,  msg}; }
function fail(msg){ return {pass:false, msg}; }

// ---- gates --------------------------------------------------------
function gate_bootstrap(){
  for (const f of ['package.json','tsconfig.json','vite.config.ts','.eslintrc.cjs','.prettierrc','.gitignore'])
    if (!exists(f)) return fail(`missing ${f}`);
  try { sh('npm run lint --silent'); } catch(e){ return fail('lint failed'); }
  try { sh('npm run typecheck --silent'); } catch(e){ return fail('typecheck failed'); }
  return ok('bootstrap green');
}
function gate_manifest(){
  if (!exists('manifest.json')) return fail('no manifest');
  const m = JSON.parse(readFileSync('manifest.json','utf-8'));
  if (m.manifest_version !== 3) return fail('not MV3');
  if (m.version !== '19.0.0')   return fail(`version=${m.version}`);
  const needPerms = ['alarms','scripting','storage','webNavigation','activeTab','tabs'];
  for (const p of needPerms) if (!m.permissions?.includes(p)) return fail(`missing perm ${p}`);
  const needHosts = ['evo-games.com','pragmaticplaylive','playtech','ezugi.com','imagine.live'];
  const hosts = (m.host_permissions||[]).join(',');
  for (const h of needHosts) if (!hosts.includes(h)) return fail(`missing host ${h}`);
  if (/unsafe-eval|unsafe-inline/.test(JSON.stringify(m.content_security_policy||{})))
    return fail('CSP has unsafe directive');
  return ok('manifest v19 green');
}
function gate_schemas(){
  if (!exists('src/shared/schema.ts')) return fail('no schema.ts');
  if (!exists('tests/mock_server/contract.py')) return fail('no contract.py');
  try { sh('npx vitest run src/shared/schema --silent'); } catch{ return fail('zod tests failed'); }
  try { sh('python -m pytest tests/mock_server/test_contract.py -q'); } catch{ return fail('pydantic tests failed'); }
  return ok('schemas symmetrical');
}
function gate_registry(){
  if (!exists('src/providers/registry.ts')) return fail('no registry');
  try { sh('npx vitest run src/providers/registry --silent'); } catch{ return fail('registry test failed'); }
  return ok('registry green');
}
function gate_fixtures(){
  for (const p of ['evolution','pragmatic','playtech','ezugi','imagine'])
    if (!exists(`tests/e2e/fixtures/${p}_sample.html`)) return fail(`missing fixture ${p}`);
  return ok('5 fixtures present');
}
function gate_test_files(kind){
  for (const p of ['evolution','pragmatic','playtech','ezugi','imagine'])
    if (!exists(`tests/unit/${kind}/${p}.test.ts`)) return fail(`missing test ${p}`);
  return ok('test files exist');
}
function gate_provider_pass(name){
  try { sh(`npx vitest run tests/unit/providers/${name} --silent`); } catch{ return fail(`${name} red`); }
  return ok(`${name} green`);
}
function gate_sw(){
  for (const f of ['src/background/index.ts','src/background/ws_client.ts','src/background/alarms.ts','src/background/tab_observer.ts','src/background/state.ts'])
    if (!exists(f)) return fail(`missing ${f}`);
  // grep proibições
  const out = sh('node -e "const g=require(\'fast-glob\').sync(\'src/**/*.ts\');const fs=require(\'fs\');for(const f of g){const c=fs.readFileSync(f,\'utf-8\');if(/setInterval\\(/.test(c))console.log(\'BAD:\'+f);}"').trim();
  if (out) return fail(`setInterval found:\n${out}`);
  return ok('SW green, no setInterval');
}
function gate_content(){
  for (const f of ['extractor','dom_probe','mutation_observer','dealer_scraper','frame_walker','url_parser'])
    if (!exists(`src/content/${f}.ts`)) return fail(`missing src/content/${f}.ts`);
  return ok('content scripts present');
}
function gate_heal(){
  if (!exists('src/background/heal.ts')) return fail('no heal.ts');
  try { sh('npx vitest run src/background/heal --silent'); } catch{ return fail('heal tests red'); }
  return ok('self-heal green');
}
function gate_popup(){
  for (const f of ['src/popup/index.html','src/popup/popup.tsx'])
    if (!exists(f)) return fail(`missing ${f}`);
  return ok('popup files present');
}
function gate_mock(){
  if (!exists('tests/mock_server/mock_server.py')) return fail('no mock_server.py');
  try { sh('python -m pytest tests/mock_server -q'); } catch{ return fail('mock tests red'); }
  return ok('mock validated');
}
function gate_coverage(){
  try {
    const out = sh('npx vitest run --coverage --reporter=json-summary --silent', {stdio:['ignore','pipe','pipe']});
    const s = JSON.parse(readFileSync('coverage/coverage-summary.json','utf-8'));
    const pct = s.total.lines.pct;
    if (pct < 80) return fail(`coverage ${pct}% < 80%`);
    return ok(`coverage ${pct}%`);
  } catch(e){ return fail('coverage run failed'); }
}
function gate_e2e(){
  try { sh('npx playwright test --reporter=list'); } catch{ return fail('e2e red'); }
  return ok('e2e green');
}
function gate_build(){
  try { sh('npm run build --silent'); } catch{ return fail('build failed'); }
  if (!exists('dist/manifest.json')) return fail('no dist/manifest.json');
  const swSize = statSync('dist/service-worker-loader.js').size;
  if (swSize > 200*1024) return fail(`SW bundle ${swSize}>200KB`);
  if (!exists('packed/extractor_beat_v19.0.0.crx')) return fail('no .crx');
  return ok('build + crx green');
}
function gate_telemetry(){
  if (!exists('src/shared/telemetry.ts')) return fail('no telemetry.ts');
  try { sh('npx vitest run src/shared/telemetry --silent'); } catch{ return fail('telemetry tests red'); }
  return ok('telemetry green');
}
function gate_docs(){
  for (const f of ['README.md','CHANGELOG.md','RELEASE_NOTES_v19.md'])
    if (!exists(f)) return fail(`missing ${f}`);
  const rn = readFileSync('RELEASE_NOTES_v19.md','utf-8');
  if (!/V-01.*✅/.test(rn)) return fail('RELEASE_NOTES_v19.md sem tabela de gates');
  return ok('docs complete');
}
function gate_handoff(){
  if (!exists('audits/rubber_duck_v19.md')) return fail('no rubber_duck audit');
  if (!exists('integration/server_patch.diff')) return fail('no server patch');
  // memory MCP check é manual via Copilot — exigir flag de override:
  if (!exists('.handoff_memory_ok')) return fail('memory MCP entities não confirmadas (criar .handoff_memory_ok após popular)');
  return ok('handoff ready');
}

// ---- runner -------------------------------------------------------
const arg = process.argv[2] || 'all';
const list = arg==='all' ? Object.keys(GATES) : [arg];
const results = [];
for (const id of list) {
  const g = GATES[id];
  if (!g){ console.error(`unknown gate ${id}`); process.exit(2); }
  process.stdout.write(`[${id}] ${g.name}... `);
  let r; try { r = g.fn(); } catch(e){ r = fail(e.message); }
  results.push({id, name: g.name, ...r});
  console.log(r.pass ? `✅ ${r.msg}` : `❌ ${r.msg}`);
}
const failed = results.filter(r => !r.pass);
console.log('\n' + '='.repeat(60));
console.log(`PASS: ${results.length - failed.length}/${results.length}`);
if (failed.length) {
  console.log('FAILED:');
  for (const f of failed) console.log(`  - ${f.id} ${f.name}: ${f.msg}`);
  process.exit(1);
}
console.log('🎉 todos os gates verdes — pronto para release');
```

### C.2 Como o agente USA (rotina obrigatória)

Adicione ao `package.json`:

```json
{
  "scripts": {
    "validate": "node scripts/validate.mjs all",
    "validate:gate": "node scripts/validate.mjs",
    "lint": "eslint 'src/**/*.{ts,tsx}'",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "coverage": "vitest run --coverage",
    "e2e": "playwright test",
    "build": "vite build",
    "pack": "node scripts/pack-crx.mjs"
  }
}
```

**Rotina por milestone:**

1. Após cada bloco do roadmap (§A.4) → rodar `npm run validate:gate -- V-XX`.
2. Após cada commit em `main` local → rodar `npm run validate` (todos os gates).
3. Antes de empacotar release → `npm run validate` deve sair `🎉 todos os gates verdes`.
4. Saída completa do último `npm run validate` é **colada como apêndice** em `RELEASE_NOTES_v19.md`.

### C.3 Skill Copilot CLI (registrar no agente)

Crie `~/.copilot/skills/extractor-beat-v19-validator/SKILL.md` na máquina do agente novo:

```markdown
---
name: extractor-beat-v19-validator
trigger: always-on
description: Garante que o agente desenvolvedor do ExtractorBeat v19 rode validate.mjs após cada milestone.
---

# Skill: ExtractorBeat v19 Auto-Validator

**Trigger:** sempre que o agente:
- Concluir um item da §A.4 do `analise_profunda_extrator_25_05.md`
- Editar `manifest.json`, qualquer arquivo em `src/providers/`, `src/background/`, `src/content/`
- Antes de criar tag/commit `release`

**Ação obrigatória:**
1. Executar `npm run validate:gate -- V-XX` para o gate correspondente.
2. Se ❌, **NÃO prosseguir** — corrigir antes.
3. Se ✅, registrar no `memory` MCP a observation: `gate V-XX passed at <ISO date>`.
4. Antes de finalizar sessão: `npm run validate` completo + colar saída em `RELEASE_NOTES_v19.md` apêndice C.
```

### C.4 Gates rápidos (cheat sheet para o agente)

| Comando | O que valida |
|---|---|
| `npm run validate -- V-02` | Manifest V3 correto |
| `npm run validate -- V-05c` | Evolution parser |
| `npm run validate -- V-12` | Self-heal funcional |
| `npm run validate -- V-15` | Cobertura ≥ 80% |
| `npm run validate` | TUDO (release-ready) |

### C.5 Critério de saída final (DOR ↔ DOD)

| Definition of Ready | Definition of Done |
|---|---|
| MCPs listados em §5 estão `tool_search_tool_regex` ok | `npm run validate` retorna `🎉 todos os gates verdes` |
| Fixtures HTML coletadas (V-05a) | `.crx` v19.0.0.0 empacotado |
| Mock server `:8765` respondendo | `RELEASE_NOTES_v19.md` com apêndice gates ✅ |
| Memory MCP responde com entidades-base | Memory MCP populado (V-20) |

---

> _"O Extractor Beat de hoje é um fotógrafo manual. O v19 vira um repórter ao vivo — entende o site, conta a história, e nunca dorme. E só sai do estúdio quando os 20 gates do `validate.mjs` estão verdes."_

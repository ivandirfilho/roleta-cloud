# fluxo_mental_24 — Blueprint / Mapa Mental do Software (Roleta Cloud) · LLM-sprint-ready

**Data:** 2026-06-24 · **Escopo:** software inteiro — **Extensão "Escuta Beat"** (cliente) + **Servidor Debian**
(backend/Docker) + dashboard + dados + deploy. **Método:** leitura direta do código no HEAD (`9eb79c4`,
grafo do projeto `graphify-out` @ `45d0779`, 3.120 nós/49 arquivos), `docker-compose.yml` de produção e os
manifestos da extensão. Stack MCP: graphify · filesystem · memory · sequential-thinking · brave + 2 subagents
(extensão / deploy).
> **Revisão (fact-check 24/06):** conferidos contra o código portas (WS 8765 / health 8766), citações de linha
> (`websocket.py:479/461`, `message_handler.py:390/483`, `connection_manager.py:36/37`, `health_server.py:619`,
> `sda17.py:166`, `settings.py:110/141/125`, `sqlite_repo.py:186`), flags da `docker-compose.yml`, o
> deploy (`roleta-deploy-pull.sh`: reset→alembic→up→health 3×5s→rollback; timer 120s) e os workflows `.github/`
> (ci matriz 3.11–3.13 + `--cov-fail-under=70`; deploy tag `v*` + `appleboy/ssh-action`). Correções aplicadas:
> `core/` (item duplicado → `safe_except`/`logging_config`), guard MASTER `background.js:663`, path `tools/systemd/`.

> Objetivo: ter um **blueprint funcional por bloco** + as **conexões** ponta-a-ponta, para julgar se o
> sistema está num estado **ideal de estruturação e versionamento de módulos**. Veredito na §5.
> **Para sprints de LLM (§6–§10):** cada bloco tem um *sprint card* (§6) com âncoras + dívida; o **backlog
> priorizado** está na §7 (pegue 1 linha = 1 sprint); a navegação no **grafo graphify atualizado** (3149 nós
> @ HEAD `9eb79c40`, 24/06) está na §8; e o **protocolo de execução** de um sprint na §9.

---

## 0. Visão de 1 tela — 3 tiers

```
┌──────────────────────── TIER CLIENTE (navegador do operador) ─────────────────────────┐
│  Extensão Chrome "Escuta Beat" v3.4.2 (MV3)          Dashboard "Glass Box" (frontend/)  │
│   • lê o DOM da Evolution (número, direção, mesa)      • HTML/JS estático (Nginx)        │
│   • tira foto da aba (captureVisibleTab) p/ OCR        • mostra estado/sugestão          │
│   • MASTER/SLAVE; só MASTER envia spins                                                  │
└───────────────────────────────────┬─────────────────────────────────────────────────────┘
                     wss://roleta.xma-ia.com/ws  (porta 8765, WSS)
┌───────────────────────────────────▼──────── TIER SERVIDOR (Debian 187.45.181.75, Docker) ┐
│  main.py → health_server(8766) + start_server(8765)                                       │
│  server/  websocket · connection_manager(MASTER/SLAVE) · message_handler(dispatch) ·      │
│           vision_ocr(RapidOCR) · extractor_service · analytics_handler · health_server     │
│        │                                                                                   │
│        ▼ orquestra:                                                                        │
│  core/ (roulette imutável, engine puro)  state/ (game+gale, bet_advisor, timeline,         │
│  block_gale)  strategies/ (sda17 M15-ADA + dormentes)  staking/ (flat/kelly)               │
│        │                                                                                   │
│        ▼ persiste:                                                                         │
│  database/ → SQLite decisions.db (autoritativo)   [opcional/dormente: PG+AGE+Timescale     │
│                                                     via outbox + workers/cdc_worker]        │
│  Observabilidade: /health /metrics(8766) · obs/ Prometheus+Grafana+Alertmanager · DNA      │
└───────────────────────────────────────────────────────────────────────────────────────────┘
   Deploy: GitHub Actions (ci/deploy) + systemd roleta-deploy.timer (git pull→alembic→compose up)
```

---

## 1. Mapa de blocos por função

> Cada bloco: **responsabilidade · arquivos · conexões**.

### A. Cliente — Extensão "Escuta Beat" (`extension/`, MV3, v3.4.2)
**Responsabilidade:** escutar a casa de apostas, extrair o resultado/contexto, fotografar a aba e falar com a Engine por WebSocket; renderizar a sugestão num overlay.
**Arquivos (papel):**
- `manifest.json` — MV3; perms `tabs/scripting/storage/alarms/webNavigation`, `host_permissions:<all_urls>`; SW `background.js`; content-scripts `deal_capture.js` (todos os frames) + `content.js`+`overlay.css` (top-frame).
- `background.js` (2063 L) — **service worker**: cliente WS (`wss://roleta.xma-ia.com/ws`, reconnect 5s×10), auto-start por `webNavigation`, **read-loop por `chrome.alarms` (~2s)** que injeta `extractResultsFromPage`/`extractMonitoringData`/`extractSessionData`, hash dos 5 últimos números → emite `novo_resultado`, e o **foto-capture** (`captureVisibleTab` jpeg q55, throttle 6s) → `foto_frame`.
- `deal_capture.js` (186 L) — scraper DOM de `provider/dealer/table/round_id` por provider, `MutationObserver`+poll 3s, `normalizeProvider` (nunca emite `host:*`, fallback `unknown`).
- `provider_router.js` / `extractor_meta.js` / `session_extractor.js` — detecção de provider (Wappalyzer-style) + extração data-driven de sessão/dealer; escolhe o iframe do jogo.
- `content.js` (815 L) — overlay `#escuta-beat-overlay` (Último/Região/Veredito/Gale/Aposta) + painel de controle; recebe `sugestao`/`state_sync`/`role_changed`.
- `popup.html/js` — UI de controle (auto-start, mesa, **botões de direção HORÁRIO/ANTI**, START/STOP, export logs).
- `providers/{index,evolution}.json` — manifestos data-driven (Evolution v18.2.0: selectors, session, betSpots).
- `selector_health.js` (348 L) — self-heal de seletores; **DORMENTE** (não importado no SW; default OFF).
**Conexões:** → Servidor via WS (contrato na §3). NB: a **força do giro NÃO é extraída** do DOM — é calculada server-side; o cliente só manda número+direção.

### B. Cliente — Dashboard "Glass Box" (`frontend/`)
**Responsabilidade:** UI web de leitura (estado do jogo). **Arquivos:** `index.html`, `app.js`, `style.css`. **Conexões:** servido por **Nginx** em `/var/www/roleta` (sincronizado no deploy); consome o backend. ⚠️ README chama de `dashboard/` (defasado).

### C. Transporte & Sessão (`server/websocket.py`, `connection_manager.py`, `auth/`)
**Responsabilidade:** aceitar conexões WSS, autenticar, e arbitrar **MASTER/SLAVE** (só 1 master envia spins). **Arquivos:** `server/websocket.py` (`start_server` L479, `get_ssl_context` L461, heartbeat 1s), `server/connection_manager.py` (`ConnectionManager`, MAX_CONNECTIONS=50, grace 10s), `auth/middleware.py` (HMAC `ROLETA_API_KEY`, `AUTH_ENABLED`). **Conexões:** recebe da extensão → entrega ao `message_handler`.

### D. Orquestração de mensagens (`server/message_handler.py`)
**Responsabilidade:** dispatch de TODA mensagem e o **hot path** da decisão. **Arquivos:** `MessageHandler.process_message` (L390) → `handle_new_result` (L483): valida `SpinInput`, `state_lock`, `check_prediction` (resolve aposta anterior), `SDA17.analyze`, gates **INV-3**, staking, `store_prediction`, persiste `Decision`, broadcast. Outras rotas: `historico_inicial`, `nova_sessao`, `foto_frame`, `extrair_mesa`, `get_analytics_*`, `register`, `force_master`. **Conexões:** núcleo↔estratégia↔dados.

### E. Visão foto→dados (`server/vision_ocr.py`, `extractor_service.py`, `core/dealer_fill.py`)
**Responsabilidade:** extrair `dealer/wheel_model/provider` da foto e acoplar à decisão. **Arquivos:** `vision_ocr.py` (RapidOCR/PaddleOCR-ONNX, singleton CPU, flag `SDA_VISION_OCR=1`), `extractor_service.py` (templates `server/configs/providers/*.json`), `core/dealer_fill.py` (fill-forward do último OCR por sessão, `SDA_DEALER_FILL_FORWARD=1`). **Conexões:** `foto_frame`→OCR→`foto_resultado`; enriquece (metadata) a próxima `Decision`, **não toca a aposta**.

### F. Núcleo de domínio (`core/`, `state/`)
**Responsabilidade:** verdade física + estado do jogo, **sem I/O**. **Arquivos:** `core/roulette.py` (roda europeia IMUTÁVEL, `WHEEL_SEQUENCE`, distâncias), `core/engine.py` (engine puro), `state/game.py` (`GameState` + `MartingaleState`), `state/bet_advisor.py` (`TripleRateAdvisor` c4/m6/l12), `state/timeline.py` (histórico de forças), `state/block_gale.py` (`BlockGaleEngine`). **Conexões:** consumido pelo `message_handler` e pelas estratégias.

### G. Estratégia & Staking (`strategies/`, `staking/`)
**Responsabilidade:** gerar centros/cobertura e decidir o stake. **Arquivos:**
- `strategies/sda17.py` (M15-ADA) — geometria **V2 (fat-SAT 3+7+7)** + **V3 (satélites assimétricos 4/2)** OU **regions_v4 (21# disjuntos)** conforme flag; `analyze()`.
- `strategies/c_selection.py` — motor C1/C2 (suporte ao `bet_pair`/`force17`).
- **Dormentes** (wired, flags OFF): `region_bandit`, `dealer_offset`, `dealer_force_profile`, `shadow_predictor`, `cold_regions`, `outlier_filter`.
- `staking/policy.py` — staking `flat`/`kelly` por sentido (substitui o gale quando `SDA_STAKING_MODE≠gale`).
**Conexões:** a cobertura final é recortada no `message_handler` pelo `SDA_BET_PAIR` (§3/§4).

### H. Configuração & Flags (`app_config/`, `config/`, compose)
**Responsabilidade:** parametrizar comportamento sem redeploy. **Arquivos:** `app_config/settings.py` (flags `SDA_*` lidas por chamada, sem cache → toggláveis), `app_config/strategy_config.py` (carrega `config/strategy.toml` com **hot-reload por mtime** dentro do `analyze()`), `config/strategy.toml` (`[sda17]`, `[sda17.minimizer]`…). **Conexões:** `docker-compose.yml environment:` → env do container → `settings.py`. ⚠️ **A compose sobrepõe os defaults do código** (§4).

### I. Persistência (`database/`, `data/`, `workers/`)
**Responsabilidade:** gravar cada decisão e séries derivadas. **Arquivos:** `database/sqlite_repo.py` (write-side **autoritativo**, SQLite `data/decisions.db`), `service.py` (sessões/decisões), `dna_logger.py` (`decision_dna`, 32k linhas), `repository.py` (abstração + `get_repository`), `models.py` (dataclasses). **Caminho PG opcional/DORMENTE:** `outbox_publisher.py`/`outbox_integration.py` (escreve `shared.outbox`), `feature_store.py` (lê `cw/ccw.spin_features`), `regime_similarity.py`, `workers/cdc_worker.py` (consome outbox → `spins_vectors`, container próprio em `docker-compose.pg.yml`), `docker/*.sql` (Postgres + **Apache AGE** grafo + **TimescaleDB**). Gate: `feature_flags.dual_write_pg` = OFF. **Conexões:** `message_handler`→`sqlite_repo`→(opcional) outbox→cdc_worker→PG.

### J. Observabilidade (`server/health_server.py`, `obs/`, DNA)
**Responsabilidade:** saúde, métricas e telemetria de decisão. **Arquivos:** `health_server.py` (`/health`,`/healthz`,`/metrics` Prometheus, `/api/strategy|state|dna_summary`, porta 8766, thread daemon), `obs/` (`prometheus.yml`, `alertmanager.yml`, `alerts.yml`, dashboards Grafana `roleta-overview/profit/dna-regions/shadow-grid`), `database/dna_logger.py` (lift por feature). **Conexões:** `docker-compose.obs.yml` sobe o stack; `scripts/install-grafana-agent.sh` para telemetria cloud.

### K. Deploy & Runtime (`Dockerfile`, `docker-compose*.yml`, `scripts/`, `.github/`)
**Responsabilidade:** empacotar e publicar no Debian. **Arquivos:**
- `Dockerfile` — `python:3.12-slim`, libs OCR (`libgl1/libglib2.0-0/...`), `CMD python main.py`, HEALTHCHECK `curl :8766/health`, LABEL `version=4.4.1`.
- `docker-compose.yml` — serviço único `roleta-cloud` (`restart: unless-stopped`, `mem_limit 512m`, `cap_add SYS_PTRACE`, ports `127.0.0.1:8765` + `:8766`, volumes `roleta-data:/app/data` + `state.json` + `server/configs:ro`, **todas as flags `SDA_*`**). Overlays: `dev`, `obs`, `pg`.
- **Path A (tag):** `.github/workflows/ci.yml` (matriz Py 3.11-3.13 + Postgres + `alembic upgrade head` + pytest cov≥70%) e `deploy.yml` (tag `v*` → `appleboy/ssh-action` no host).
- **Path B (pull, real):** `scripts/roleta-deploy-pull.sh` sob **`roleta-deploy.timer` (systemd, ~2 min)**: `git fetch`→`reset --hard origin/main`→`compose build`→**`alembic upgrade head` antes do tráfego**→`compose up -d`→healthcheck 3×5s→**rollback ao `last_good`** se falhar; sincroniza `frontend/`→`/var/www/roleta`+`nginx reload`; log em `/var/log/roleta-deploy.log`.
**Conexões:** Debian `187.45.181.75`, domínios `roleta.xma-ia.com`. Legado `roleta-cloud.service` (python direto) **desativado** (conflito de porta 8765 com o container).

### L. Qualidade & Tooling (`tests/`, `tools/`, `scripts/`, `migrations/`)
`tests/` (71 arquivos, gate cov≥70%); `tools/` (backfills, `backtest_from_db`, `backtest_harness`, `gap_detector`, `lint_dna_coverage`, `lint_silent_except`, `snapshot_sqlite_schema`); `migrations/versions/0001–0009` (Alembic); `scripts/` (setup_server, pause/resume_app, walg backups).

---

## 2. Estrutura atual de código (árvore anotada por função)

```
Roleta Cloud/
├── main.py                 # entrypoint: health_server + start_server
├── VERSION (4.4.1)         # versão da engine
├── Dockerfile · docker-compose{,.dev,.obs,.pg}.yml · alembic.ini · requirements.txt
│
├── extension/        [CLIENTE]  SW + content + popup + providers (v3.4.2, MV3)
├── frontend/         [CLIENTE]  dashboard estático (Nginx)
│
├── server/           [BORDA]    websocket · connection_manager · message_handler
│                                · vision_ocr · extractor_service · analytics_handler · health_server
├── auth/             [BORDA]    middleware HMAC
│
├── core/             [DOMÍNIO]  roulette (imutável) · engine (puro) · dealer_fill · safe_except · logging_config
├── state/            [DOMÍNIO]  game(+gale) · bet_advisor · timeline · block_gale
├── strategies/       [ESTRATÉGIA] sda17 + c_selection + 6 dormentes
├── staking/          [ESTRATÉGIA] policy (flat/kelly)
│
├── app_config/       [CONFIG]   settings (flags) · strategy_config (TOML)
├── config/           [CONFIG]   strategy.toml
│
├── database/         [DADOS]    sqlite_repo(autoritativo) · service · dna_logger · repository
│                                · models · feature_store · outbox_* · regime_similarity
├── data/             [DADOS]    decisions.db (SQLite)
├── workers/          [DADOS]    cdc_worker (PG, dormente)
├── migrations/       [DADOS]    Alembic 0001–0009
│
├── obs/              [OBSERV.]  prometheus · alertmanager · grafana dashboards
├── docker/           [INFRA]    Dockerfile(s) cron + PG init (AGE/Timescale)
├── scripts/ tools/   [DEVOPS]   deploy timer, backfills, backtests, lints, backups
├── tests/            [QA]       71 arquivos (cov≥70%)
└── archive/          [LEGADO]   RoletaV11, historico_dev — NÃO é código ativo
```

---

## 3. Conexões — fluxos de dados ponta a ponta

**Fluxo 1 — Spin (caminho quente):**
```
DOM Evolution ─(alarm ~2s)→ background.js extractResults → hash muda
  → WS novo_resultado{numero,direcao,dealer,table,provider,round_id,monitoringData}
    → message_handler.handle_new_result
        → check_prediction(numero)            # resolve a aposta ANTERIOR (HIT/MISS, pnl)
        → TripleRateAdvisor + SDA17.analyze    # score, centros C1/C2/C3, cobertura N
        → INV-3 (sempre indica; vetos só modulam stake)
        → bet_pair(force17) recorta cobertura  # união real ~15
        → staking (block_gale cap1 = flat)     # stake
        → store_prediction(target = OPOSTO do spin) + grava Decision + DNA
    → WS sugestao{regioes,numeros,force17,gale,aposta,confidence}
  → content.js overlay  +  state_sync (1s)
```
**Fluxo 2 — Foto/Visão:** `background.captureVisibleTab → WS foto_frame{image} → vision_ocr → {dealer,wheel_model,provider} → dealer_fill (fill-forward) → enriquece próxima Decision → WS foto_resultado`.
**Fluxo 3 — Analytics:** `dashboard → WS get_analytics_* → analytics_handler → repository (decisions/sessions/gale_windows)`.
**Fluxo 4 — CDC (DORMENTE):** `sqlite_repo → shared.outbox → cdc_worker → cw/ccw.spins_vectors (Timescale/AGE)` — só com `dual_write_pg=ON` + `docker-compose.pg.yml`.
**Fluxo 5 — Deploy:** `git push main → roleta-deploy.timer (2min) → reset --hard → alembic upgrade head → compose up -d → /health → (falha) rollback last_good`.

**Contrato WebSocket (resumo):**

| Cliente → Servidor | Servidor → Cliente |
|---|---|
| `register`, `novo_resultado`, `historico_inicial`, `correcao_historico`, `foto_frame`, `nova_sessao`, `force_master`, `extrair_mesa`, `listar_mesas`, `obter_config_mesa` | `ack`, `sugestao`, `state_sync` (1s), `foto_resultado`, `role_assigned`/`role_changed`, `sessao_resetada`, `error(NOT_MASTER)`, `mesas_disponiveis`, `mesa_configurada` |

**Topologia MASTER/SLAVE:** vários navegadores podem conectar; só o **MASTER** envia `novo_resultado/historico/correcao` (guard no `background.js:663` e no `connection_manager`). Promoção por `force_master`.

---

## 4. Versionamento de módulos — estado atual

### 4.1 Superfícies de versão (NÃO há fonte única de verdade)
| Superfície | Valor | Observação |
|---|---|---|
| `VERSION` (engine) | **4.4.1** | lido por `main.py` e exposto em `/health` |
| `Dockerfile` LABEL | 4.4.1 | metadado da imagem |
| Extensão `manifest.json` | **3.4.2** | linha de versão independente |
| `README.md` título | **v3.5** | ⚠️ **defasado**; cita `dashboard/` (é `frontend/`) |
| Git tags `v*` | → `deploy.yml` | dispara build/deploy por tag |
| DB `strategy_versions` | `smart_gale v4.4.0` | params + `git_tag` (fonte de params da estratégia) |
| DB `feature_flags` | shadow/cold/outlier/dual_write_pg = OFF | kill-switch/canary runtime |
| Alembic `0001–0009` | + ALTERs in-code | **gestão dupla de schema** |

### 4.2 O comportamento é versionado por FLAG na compose (e diverge do código)
A verdade de runtime está no `docker-compose.yml`, que **sobrepõe os defaults de `settings.py`**:

| Flag | Default no CÓDIGO | **PRODUÇÃO (compose)** | Efeito |
|---|---|---|---|
| `SDA_REGIONS_V4` | `0` (OFF) | **`1` (ON)** | geometria gera 21# (centros C1/C2/C3 disjuntos) |
| `SDA_BET_PAIR` | `full` | **`force17`** | recorta p/ união real ~15 (breakeven ~42,8%) |
| `SDA_FORCE17_EXACT` | `0` | `0` | mantém união ~15 (não força 17 exatos) |
| `SDA_STAKING_MODE` | `gale` | **`block_gale`** | flat-equivalente (cap 1) — "gale só sangra" |
| `GALE_CAP` | `1` | `1` | teto 1 = sem ruína |
| `SDA_DEALER_FILL_FORWARD` | `0` | **`1`** | dealer da foto propaga por sessão |
| `SDA_VISION_OCR` | `1` | `1` | OCR foto→dados ligado |
| `SDA_DEALER_FORCE_PROFILE` | `0` | `0` | perfil de força por dealer dormente |

> **Implicação:** quem lê só o código vê o comportamento errado; o real está na compose. E a **linha de
> decisão não grava qual flag-set estava ativo** (lacuna de telemetria já apontada em `auditoria_24_junho.md`)
> — por isso a era 14–22/06 mistura geometrias (21#→14#→força17) sem registro auto-descritivo.

---

## 5. Veredito — está no estado ideal de estruturação e versionamento?

### ✅ Pontos fortes (estrutura madura para single-host)
1. **Camadas limpas e desacopladas:** `core` puro (sem I/O) → `state` → `strategies` → `database` → `server`. Separação de responsabilidades clara; o domínio é testável isolado.
2. **Comportamento por feature-flag** lido por chamada (toggle sem redeploy) + `strategy.toml` hot-reload + invariante **INV-3** (nunca fica sem indicação).
3. **Deploy robusto:** pull-timer com **alembic antes do tráfego**, **healthcheck + rollback automático** ao `last_good`, backup do DB pré-deploy; CI com matriz e gate de cobertura.
4. **Observabilidade real:** `/health` + `/metrics` Prometheus + Grafana + DNA telemetry (lift por feature).
5. **Visão acoplada:** pipeline foto→OCR→dealer 100% versionado em flags.

### ⚠️ Riscos / lacunas (o eixo FRACO é governança de versão/config)
1. **Sem fonte única de versão:** `VERSION 4.4.1` vs extensão `3.4.2` vs README `v3.5` (defasado, cita pasta inexistente). Sem `CHANGELOG` ligando engine↔extensão↔tag.
2. **Divergência código×compose:** geometria/staking/bet_pair vivem só na compose; o default do código contradiz a produção. Difícil raciocinar sobre "o que roda".
3. **Gestão dupla de schema:** Alembic **+** `ALTER TABLE` imperativo no `sqlite_repo` → risco de drift (`schema_parity_manifest.json` é paliativo).
4. **Dois caminhos de deploy concorrentes:** `deploy.yml` (por tag) **e** `roleta-deploy.timer` (puxa `origin/main` a cada ~2 min). O timer pode **sobrescrever** um deploy por tag — autoridade ambígua.
5. **Massa de código dormente:** 6 estratégias auxiliares + todo o caminho PG/AGE/Timescale + `cdc_worker` + `selector_health.js`, todos wired mas OFF. Aumenta superfície/carga cognitiva sem ciclo de vida explícito.
6. **Três caminhos de staking** (`state/game` gale, `staking/policy` flat/kelly, `state/block_gale`) e **5+ geometrias** (V2/V3, regions_v4, force17, c2c3, full) coexistindo com despacho por flag → ramificação alta (exatamente o que dificultou a auditoria 22/06).
7. **SQLite single-host** como primário (+ `state.json` bind-mount): sem HA; o caminho PG existe mas está dormente.
8. **Legado no repo** (`archive/RoletaV11`, `historico_dev`) — ruído que toda busca/grafo precisa excluir.

### 🎯 Maturidade e próximos passos
**Conclusão:** a **arquitetura está bem estruturada e operacionalmente madura** para um sistema de host único
(camadas limpas, flags, deploy com rollback, observabilidade, testes). **Mas NÃO está no estado ideal de
versionamento de módulos** — o gap é de **governança e consolidação**, não de capacidade:

1. **Fonte única de versão:** `VERSION` → injetado no banner, no `manifest.json` (build da extensão), na LABEL do Docker, na tag git e em `strategy_versions`. Adicionar `CHANGELOG.md`. Sincronizar/retirar o `v3.5` do README.
2. **Gravar `geometry_tag`/`flags_snapshot` por linha de `decisions`** — fecha a lacuna de telemetria e torna toda análise futura auto-descritiva.
3. **Escolher UM caminho de deploy** (recomendado: o pull-timer; fazer o tag-deploy promover `main` ou desativá-lo) para acabar com a sobrescrita.
4. **Consolidar schema em Alembic** (migrar os `ALTER` in-code para migrações; aposentar `schema_parity_manifest`).
5. **Registro de ciclo de vida de módulos dormentes** (ex.: `experimental/` ou um registry de feature-flags com estado: dormant/shadow/active/retired).
6. **Documentar a árvore de decisão geometria×staking** num único lugar (qual flag → qual caminho), espelhando esta §4.

---

## 6. Sprint cards por bloco (LLM-ready)

> Como ler: cada card = **Âncoras** (onde o agente entra) · **Dívida → sprints** (IDs no §7) ·
> **Raio de impacto** (o que pode quebrar) · **Verificação** (como provar "pronto"). IDs de bloco = letras da §1.

**BLK-A · Extensão "Escuta Beat"** — `extension/`
- Âncoras: `background.js` (WS `:107` · foto `:274` · readResults `:1373` · guard master `:663`), `deal_capture.js` (`normalizeProvider :40`), `manifest.json:4`.
- Dívida: `SPR-X1` selector_health dormente · `SPR-X2` phantom dedup OFF · `SPR-X3` **sem testes JS** · `SPR-X4` só Evolution `available`.
- Raio: BLK-C/D (contrato WS) → altera a entrada de TODA a pipeline.
- Verificação: carregar no Chrome (`getManifest().version`); ⚠️ não há suíte JS (ver `SPR-X3`).

**BLK-B · Dashboard "Glass Box"** — `frontend/`
- Âncoras: `frontend/{index.html,app.js,style.css}`, `roleta.conf` (`root /var/www/roleta`), sync em `roleta-deploy-pull.sh:88-107`.
- Dívida: `SPR-G6` README cita `dashboard/` (é `frontend/`).
- Raio: só apresentação (read-only).
- Verificação: `curl https://roleta.xma-ia.com`; conferir assets em `/var/www/roleta`.

**BLK-C · Transporte & Sessão** — `server/websocket.py`, `connection_manager.py`, `auth/`
- Âncoras: `websocket.py:479` (`start_server`), `:461` (`get_ssl_context`), `:429` (`handler`), `connection_manager.py:36/37` (grace 10s / MAX 50), `auth/middleware.py`.
- Dívida: SSL/AUTH **default OFF** (hardening opcional); MASTER/SLAVE com grace de 10s (edge cases de duplo-master já tratados, regredir sob carga é risco).
- Raio: toda conexão; topologia MASTER/SLAVE.
- Verificação: `tests/` de connection_manager; teste de reconexão dentro/fora do grace.

**BLK-D · Orquestração de mensagens** — `server/message_handler.py`
- Âncoras: `:390` (`process_message` dispatch), `:483` (`handle_new_result` hot path), bloco INV-3 `:703-770`, bet_pair `:180`.
- Dívida: `SPR-S3` cortar full-stake CW · `SPR-S4` CUT não cobre score=4 & tr_c4_rate=0 · `SPR-S5` stop-loss reseta por sessão · `SPR-X2` phantom dedup.
- Raio: BLK-G (estratégia), BLK-I (grava Decision), INV-3 (nunca suprimir indicação).
- Verificação: `tests/test_message_handler_gale.py`, `test_audit_cadence_12_06.py`; reproduzir no `dec_snap` por linha.

**BLK-E · Visão foto→dados** — `server/vision_ocr.py`, `extractor_service.py`, `core/dealer_fill.py`
- Âncoras: `vision_ocr.py` (`_parse_fields`, `_norm_dealer/_norm_model`), `dealer_fill.py` (`resolve_dealer`), `models/input.py` (`sanitize_provider`).
- Dívida: `SPR-T4` provider `host:*` poluído · `SPR-S2` dealer×sentido capturado mas **não usado** · cobertura histórica de dealer 5,7%.
- Raio: metadata (não toca aposta) — mas alimenta gates dealer.
- Verificação: `tests/test_vision_ocr.py`, `test_vision_features.py`; `GROUP BY provider/dealer` no DB limpo.

**BLK-F · Núcleo de domínio** — `core/`, `state/`
- Âncoras: `core/roulette.py` (`WHEEL_SEQUENCE`), `core/engine.py`, `state/game.py` (`MartingaleState`), `state/bet_advisor.py`, `state/timeline.py`.
- Dívida: baixa (camada estável, pura, sob mypy --strict). `SPR-X2` força calculada server-side (resiliência se o DOM mudar).
- Raio: consumido por BLK-D/G; mudar `roulette` afeta TODA geometria.
- Verificação: `tests/` de core/state; `pre-commit` (ruff+mypy strict em `core/state`).

**BLK-G · Estratégia & Staking** — `strategies/`, `staking/`
- Âncoras: `sda17.py:166` (`analyze`), `:279` (regions_v4), `:392/:412` (geometria V2/V3), `c_selection.py`, `staking/policy.py`, `state/block_gale.py`.
- Dívida (núcleo): `SPR-S1` **edge negativo** (flat ROI −4,71%) · `SPR-T1` 3 caminhos de staking · `SPR-T2` 5+ geometrias coexistindo · `SPR-G5` 6 estratégias dormentes sem ciclo de vida.
- Raio: o "cérebro" — qualquer mudança altera apostas; honrar INV-3.
- Verificação: `tests/test_sda17*.py`, `test_geometry_v*`; **flat coverage ROI por bucket-N** (ver `auditoria_24_junho.md`).

**BLK-H · Configuração & Flags** — `app_config/`, `config/`, compose
- Âncoras: `settings.py:110/141/125` (flags), `strategy_config.py` (TOML hot-reload), `config/strategy.toml`, `docker-compose.yml:23-99`.
- Dívida: `SPR-G2` decisions não grava flags ativas (lacuna de telemetria) · `SPR-G1` divergência código×compose sem fonte de verdade.
- Raio: governa o comportamento de TODOS os blocos por env.
- Verificação: `/health` expõe versão; comparar `settings.py` default × compose; (proposto) coluna `flags_snapshot`.

**BLK-I · Persistência** — `database/`, `data/`, `workers/`
- Âncoras: `sqlite_repo.py:186` (DDL + ALTERs `:300-365`), `service.py`, `dna_logger.py`, `migrations/versions/0001-0009`, `workers/cdc_worker.py`.
- Dívida: `SPR-G2` `geometry_tag`/`flags_snapshot` por linha · `SPR-G4` schema duplo (Alembic+ALTER) · `SPR-T3` SQLite single-host (PG dormente) · `SPR-S6` quarentenar 19/06.
- Raio: write-side autoritativo; migrações rodam ANTES do tráfego no deploy.
- Verificação: `alembic upgrade head` no CI; `scripts/schema_symmetry.py`; `schema_parity_manifest.json`.
- Sub-grafo PG/AGE/Timescale (`docker/*.sql`, `outbox_*`, `cdc_worker`) = **dormente** (`dual_write_pg` OFF) → candidato de `SPR-T3`/`SPR-G5`.

**BLK-J · Observabilidade** — `server/health_server.py`, `obs/`, DNA
- Âncoras: `health_server.py:619` (`start_health_server`), `:356/:370` (`/health`,`/metrics`), `obs/{prometheus,alertmanager,alerts}.yml` + dashboards Grafana.
- Dívida: `SPR-O1` ligar `alerts.yml` a SLOs por bloco; expor métrica de edge/geometria.
- Raio: read-only; não pode bloquear o app (thread daemon).
- Verificação: `curl :8766/metrics`; Grafana `roleta-overview/profit/dna-regions`.

**BLK-K · Deploy & Runtime** — `Dockerfile`, `docker-compose*.yml`, `scripts/`, `.github/`
- Âncoras: `scripts/roleta-deploy-pull.sh`, `tools/systemd/roleta-deploy.{service,timer}` (120s), `.github/workflows/{ci,deploy}.yml`, `Dockerfile`.
- Dívida: `SPR-G3` **dois deploys concorrentes** (timer `reset --hard origin/main` vs tag) · `SPR-G1` tags/imagem sem fonte única de versão.
- Raio: produção inteira; rollback automático já existe (`last_good`).
- Verificação: `/health` 3×5s no deploy; `git log` da `origin/main`; `/var/log/roleta-deploy.log`.

**BLK-L · Qualidade & Tooling** — `tests/`, `tools/`, `scripts/`, `migrations/`
- Âncoras: `tests/` (71 arq, cov≥70% em core/state/database), `tools/{backtest_from_db,backtest_harness,lint_*}.py`, `.pre-commit-config.yaml` (ruff+mypy strict + lint-silent-except + lint-dna-coverage).
- Dívida: `SPR-X3` **0 testes JS** (extensão) · `SPR-S6` quarentena 19/06 no harness · `SPR-T6` `archive/` polui buscas · cobertura não inclui `server/`.
- Raio: rede de segurança de todos os sprints.
- Verificação: o próprio CI (`ci.yml`); `pytest tests/`.

---

## 7. Backlog priorizado (pick-list para sprints)

> Prioridade: **P0** (corrige conclusão/risco de produção) · **P1** (alavanca alta) · **P2** (dívida/robustez).
> Esforço: **S** ≤1 dia · **M** alguns dias · **L** projeto. Pegue 1 linha = 1 sprint.

| ID | Bloco | Problema | Pri | Esf | Critério de "pronto" | Fonte |
|---|---|---|---|---|---|---|
| `SPR-G2` | H/I | `decisions` não grava as flags/geometria ativas → análise infere N e erra | **P0** | M | Coluna `flags_snapshot`/`geometry_tag` populada; backtest por geometria sem inferência | auditoria_24 |
| `SPR-S1` | G | Edge negativo: flat coverage ROI −4,71% < aleatório −2,70% | **P0** | M | Decisão de geometria baseada em flat ROI por bucket-N; força17 vs full medido | auditoria_24 |
| `SPR-G1` | H/K | Sem fonte única de versão (VERSION 4.4.1 × ext 3.4.2 × README v3.5) | P1 | M | 1 fonte → banner/manifest/Docker/tag/`strategy_versions`; `CHANGELOG.md` | §4.1 |
| `SPR-G3` | K | Governança de deploy: 2 caminhos concorrentes + `main` auto-deploya merges + sem path-filter + imagem buildada no host (sem registry) | P1 | M | `main` protegida (PR/CI/approval); 1 caminho autoritativo; deploy ignora só-`docs`/`sprints/`/`graphify-out/`; **imagem versionada via CI→GHCR** e host puxa (não rebuilda) | §5,§10,§12 |
| `SPR-S2` | G/E | Gate dealer×sentido dormente (dados existem ~80%) | P1 | S | Gate em sombra (n≥30); suspende full-stake em par fraco | auditoria_24 |
| `SPR-S3` | D/G | CW(horário) sangra (-6,3% flat) mas ainda full-stake | P1 | S | CW ×0.10/abster por padrão sob flag + telemetria | auditoria_24 |
| `SPR-S4` | D | CUT-POLICY não cobre score=4 com `tr_c4_rate=0` | P1 | S | Regra `score==4 AND tr_c4_rate==0 → ×0.10` + teste | auditoria_24 |
| `SPR-S6` | I/L | 19/06 corrompido contamina médias/treino | P1 | S | Filtro de quarentena no `backtest_harness` | memória |
| `SPR-T4` | E/I | `provider` poluído (`host:*`, ~2100 linhas) | P1 | S | Sanitização na ingestão; `GROUP BY provider` limpo | memória |
| `SPR-X3` | A/L | Extensão sem testes automatizados (0 JS) | P1 | M | Suíte p/ `extractResults`/`normalizeProvider`/contrato WS | §1.L |
| `SPR-S5` | D | Stop-loss reseta a cada sessão (bleed recomeça) | P2 | S | SL persistente por sessão/dealer entre reconexões | auditoria_24 |
| `SPR-G4` | I | Schema duplo (Alembic + ALTER in-code) | P2 | M | ALTERs migrados p/ Alembic; `schema_parity_manifest` aposentado | §2.1 |
| `SPR-G5` | G/I | Módulos dormentes sem ciclo de vida explícito | P2 | S | Registry de estado (dormant/shadow/active/retired) | §5 |
| `SPR-G6` | B/H | README defasado (`dashboard/`, v3.5) | P2 | S | README revisado p/ `frontend/`, 4.4.1 | §4.1 |
| `SPR-T1` | G | 3 caminhos de staking (gale/policy/block_gale) | P2 | M | 1 dispatcher claro + testes de paridade | §5 |
| `SPR-T2` | G | 5+ geometrias coexistindo (branching alto) | P2 | M | Decision-tree única + remoção de modos mortos | §5 |
| `SPR-T3` | I | SQLite single-host sem HA (PG dormente) | P2 | L | Decisão go/no-go do PG/Timescale; plano de durabilidade | §5 |
| `SPR-T6` | L | `archive/` polui busca/grafo | P2 | S | Legado isolado/movido; `.gitignore`/exclusões consistentes | §2 |
| `SPR-X1` | A | `selector_health.js` dormente (self-heal OFF) | P2 | M | Promoção shadow→auto com kill-switch | §1.A |
| `SPR-X2` | A/D | Phantom dedup OFF (re-detecção de DOM estático) | P2 | S | `SDA_DEDUP_PHANTOM=1` validado + teste | compose:98 |
| `SPR-X4` | A | Só Evolution `available` (outros providers off) | P2 | M | ≥1 provider novo data-driven | §1.A |
| `SPR-O1` | J | Alerts/SLOs por bloco não consolidados | P2 | S | `alerts.yml` com SLOs de edge/health/deploy | §1.J |
| `SPR-T7` | D | God Object `message_handler.handle_new_result` (~1200 LOC) — maior dívida de modificabilidade (ISO §D.1) | P2 | L | extrair `DecisionPipeline` puro/testável **sem alterar comportamento**; suíte verde | ISO §D.1 |

### 7.1 — Status board → `sprints/BOARD.md`

> O **board vivo** (status · owner · branch · deps · locks · PR) fica em **`sprints/BOARD.md`** — arquivo
> pequeno, FORA deste doc, p/ não inchar o contexto do Diretor nem conflitar com edições de conteúdo.
> Este §7 é a **definição canônica** (não muda por sprint); o board é o **estado**.
> Estados: `TODO → READY → DOING → REVIEW → MERGED/DONE` (ou `BLOCKED`). Branch: `spr/SPR-*`.

---

## 8. Navegação no grafo (graphify) por bloco

**Frescor:** grafo do projeto `graphify-out/graph.json` = **3149 nós · 3336 edges · 306 comunidades**, build `9eb79c40` = **HEAD** (24/06). ✅
**⚠️ Caveat:** o MCP `graphify` serve um **super_graph** misto (código + docs de sprint + infra) — `query_graph` pode casar nós errados (ex.: `analyze()` de outro arquivo). Para precisão, ancore por **símbolo de classe** (god node) ou filtre por path; o grafo PURO do projeto é o `graphify-out/graph.json`.

**God nodes (abstrações centrais):** `SDA17Strategy` (56) · `MessageHandler` (29) · `BaseModel` (21) · `start_server()` (20).

| Bloco | Nó-âncora no grafo | Como navegar |
|---|---|---|
| BLK-D | `MessageHandler` | `graphify.get_neighbors MessageHandler` → vê estratégia/DB/INV-3 |
| BLK-G | `SDA17Strategy` | `graphify.get_node SDA17Strategy` + `get_neighbors` (raio do "cérebro") |
| BLK-C | `start_server()` | `get_neighbors` → handler/ssl/heartbeat |
| BLK-F | `BaseModel`, `roulette` | base dos modelos/roda |
| BLK-A | (JS) | grafo fraco p/ extensão → use `grep`/`glob` em `extension/` |

**Manutenção do grafo (obrigatória pós-sprint):** após editar código, rode `graphify update .` (custo 0) e confirme `built_at_commit == HEAD` antes de confiar em qualquer consulta.

---

## 9. Protocolo de sprint LLM (como um agente deve atacar 1 item do §7)

1. **Contexto:** abra o brief `sprints/SPR-XXX.md` (deps/locks) + o card do bloco (§6) + a Fonte citada. Crie o **worktree próprio** (Setup do brief) — nunca trabalhe no working dir do Diretor.
2. **Grafo primeiro:** consulte o nó-âncora (§8) com `graphify` ANTES de `grep` cego; só então leia os arquivos das Âncoras.
3. **Reproduza:** confirme o problema com um teste OU query no snapshot (`dec_snap_*.db`) — número antes de mudar.
4. **Mudança cirúrgica:** respeite INV-3; **comportamento novo atrás de flag default-OFF**; migração Alembic **aditiva**; nada hardcoded.
5. **Valide:** rode o teste-alvo do card + o `Critério de "pronto"` (§7); cheque `/health`/`/metrics` se tocar runtime.
6. **Feche o loop (Closeout do brief):** log → commit em `spr/SPR-XXX` → `git push` + **PR** (NUNCA merge/push em `main`); `graphify update .` **local sem commitar `graphify-out/`**; `store_memory`. Detalhes em §10.

---

## 10. Operação de sprints — Diretor ↔ Executores (cross-sessão)

**Papéis.** **Diretor** = a sessão que orquestra (mantém `sprints/BOARD.md` + os briefs; **NÃO implementa**).
É **resumível**: todo o estado vive no repo (`sprints/` + este doc) + memória → qualquer sessão nova vira
Diretor lendo `sprints/BOARD.md`. **Executor** = uma sessão NOVA por sprint, **em worktree próprio**.

**Loop (1 dor → 1 sprint).**
1. Você diz a **dor** (texto livre ou `SPR-*`). Sem ID, o Diretor cria o próximo (`SPR-<prefixo><n>`) e adiciona ao §7 + board.
2. **Diretor**: escreve `sprints/SPR-XXX.md` (do template) com o **cabeçalho de deps/locks/base_sha**, marca `READY` no board, e **commita + push** board+brief (senão um novo Diretor não os enxerga).
3. Você abre **sessão nova** e dá 1 ordem: *"Execute `sprints/SPR-XXX.md`"*. O executor cria **worktree próprio**, implementa em `spr/SPR-XXX`, valida pela DoD, **abre PR** (não faz merge) e faz o closeout (validar → log → commit → push/PR).
4. Diretor lê via `git fetch origin spr/SPR-XXX` + `git diff --stat` + tail do log + memória → marca `REVIEW`. Após **PR aprovado + CI verde + merge**, marca `MERGED/DONE` e ajusta o card §6 se a arquitetura mudou.

**⚠️ Segurança de deploy (CRÍTICO).** `main` **é produção**: o timer faz `reset --hard origin/main` + `compose up` a cada ~2 min, e o **rollback NÃO desfaz migração de schema**. Portanto:
- Executor **NUNCA** dá push/checkout/reset em `main`, nem toca host/SSH/scripts de deploy.
- Merge p/ `main` só via **PR + CI verde + aprovação**.
- Mudança de comportamento **nasce atrás de flag default-OFF** (liga-se depois, deliberadamente, na compose) → merge fica seguro.
- Migração Alembic **aditiva/retrocompatível** (assume que o rollback não dá downgrade).

**Paralelismo seguro (worktree + locks).**
- 1 executor = **1 worktree**: `git worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main`. **Nunca** compartilhar o working dir do Diretor (checkout move o Diretor de branch).
- O Diretor só inicia em paralelo sprints com **`locks` disjuntos** (campo do brief: ex. `schema/alembic`, `BLK-G`, `compose`). **Migrações Alembic serializam** (numeração 0010/0011 colide).
- `SPR-G2` (telemetria) é **pré-req** das análises por geometria (`SPR-S1/S2`). Ex. paralelo seguro: `{SPR-G2·schema}` ∥ `{SPR-X3·extensão}` ∥ `{SPR-T4·provider}` ∥ `{SPR-G6·README}`.

**Higiene de contexto/artefatos.** Diretor nunca lê diff grande (só board + tail + `--stat` + memória; `session_store_sql` p/ achar a sessão executora). **`graphify-out/` é versionado e pesado (~2,5 MB)** → o executor roda `graphify update .` só p/ navegação **local e NÃO commita** `graphify-out/`; o **Diretor/CI** atualiza o grafo **uma vez após o merge**. Coordenação (board/briefs) idealmente não dispara rebuild de prod — ver `SPR-G3` (path-filter no deploy).

**Canais cross-sessão (verdade compartilhada).** Repo (`sprints/` + `fluxo_mental_24.md`) commitado/pushed · git (branch `spr/SPR-*` + PR) · memória (Copilot + MCP). O contexto de sessão **não** é canal.

---

## 11. O que muda para você — interação real (ônus × bônus), verdade não intenção

**Linha do tempo de UMA dor (sessão a sessão):**
1. **Abrir terminal → Diretor** (`copilot`): warm-up = ler `sprints/BOARD.md` (pequeno). Sem confirmação.
2. **Você diz a dor** → Diretor escreve o brief + atualiza o board. ⛳ *Confirmação 1 (opcional):* autorizar `git push` do board/brief (só necessário p/ outra máquina ou p/ o PR enxergar; no mesmo diretório os arquivos já existem).
3. **Você abre 1 sessão NOVA por sprint** e digita *"Execute `sprints/SPR-XXX.md`"*. ⚠️ **Manual** — eu **não** consigo abrir terminais por você (`/fleet`/Mission Control = **403** nesta conta). Paralelo = N terminais (1 worktree cada).
4. **Executor roda em autopilot:** lê/edita/testa/**commita local** SEM te perguntar. ⛳ *Confirmação 2:* `git push` + **abrir PR** (escrita no GitHub). Também pausa p/: comando destrutivo, install global, ou falta de Docker/ambiente.
5. **Merge do PR.** ⛳ *Confirmação 3 (a que importa):* revisar + **merge na `main` = deploy automático em ~2 min**. Gate **humano** — proteja a `main` (PR + CI verde), senão o autopilot poderia mesclar sozinho.
6. **Ligar a flag.** ⛳ *Confirmação 4:* o comportamento entrou **default-OFF**; você o ativa depois, deliberadamente, na `docker-compose.yml`.

**Onde você confirma algo:** (1) push do scaffold [opcional], (2) push/PR de cada executor, (3) **merge → main = deploy** [crítico], (4) ligar a flag. Todo o resto (ler/editar/testar/commit local) corre sozinho no autopilot.

**Ônus × Bônus vs. a interação atual (1 sessão fazendo tudo):**

| Eixo | Hoje (1 sessão monolítica) | Diretor ↔ Executores |
|---|---|---|
| Contexto | incha até ficar lento/caro/alucinante | **Diretor enxuto e reaproveitável** · ônus: warm-up lendo o board |
| Paralelismo | serial (1 dor por vez) | **N sprints ao mesmo tempo** · ônus: você abre N terminais/worktrees (manual) |
| Confirmações | poucas, tudo no mesmo lugar | mais cerimônia git (push/PR/**merge=deploy**/flag) — mas nos pontos certos |
| Segurança | edita "ao vivo", sem rede | **PR+CI+DoD+flag-OFF+migração aditiva** → merge não quebra prod |
| Durabilidade | morre com a sessão (arquivos soltos) | **repo+memória = resumível/auditável** · ônus: precisa commitar/pushar p/ valer |
| Qualidade | 1 agente generalista, contexto sujo | sprint isolado, testado, revisável por PR |

**A verdade (não a intenção):** o gargalo que sobra é **humano-manual** — *abrir* as sessões executoras e dar o *gate de merge*. `/fleet` automatizaria o spawn paralelo, mas está **403** nesta conta; até liberar política enterprise, **você é o escalonador**. Em troca: contexto leve, paralelismo real e deploy seguro. Dentro de cada sessão o autopilot remove quase toda confirmação; o que NÃO some (de propósito) são os 2 portões com consequência: **push/PR** e **merge→prod**.

---

## 12. Esteira automática (código → git → imagem → Debian) + conformidade ISO

**Pergunta:** da discussão do problema até produção, o que roda sozinho? **Resposta:** do **merge** em diante, **tudo**. Os únicos passos manuais são — por exigência ISO (prod-writes gated) e segurança (merge=deploy) — **abrir o PR**, **aprovar o merge** e **ligar a flag**.

```
[1] Discussão → brief            Diretor (humano + agente)         sprints/SPR-X.md
[2] Execução  → código+testes+ADENDO+Rollback     Executor (autopilot, worktree próprio)
       └─ git push spr/SPR-X + abrir PR ......................... ⛳ GATE 1 (escrita GitHub)
[3] CI (.github/workflows/ci.yml) — AUTOMÁTICO no PR:
       matrix 3.11/3.12/3.13 + Postgres + alembic upgrade head + cov≥70% + 3 linters
       └─ PR verde
[4] Merge → main ......................................... ⛳ GATE 2 (humano; ISO: prod-write aprovado)
       └─ daqui em diante 100% AUTOMÁTICO ↓
[5] Esteira Debian (systemd roleta-deploy.timer, ~2 min):
       git fetch + reset --hard origin/main
       → docker compose build              (RE-BUILDA a imagem no host)
       → docker compose run alembic upgrade head   (migração ANTES do tráfego)
       → docker compose up -d
       → /health 3×5s   →  falhou? ROLLBACK p/ last_good
       → frontend/ → /var/www/roleta + nginx reload   → /var/log/roleta-deploy.log
[6] Ativação: flag default-OFF → ON na compose ........... ⛳ GATE 3 (humano, quando validado)
```
> **Tier extensão NÃO entra na esteira docker:** mudança em `extension/` exige **bump de `manifest.version` + reload no Chrome** (client-side, manual) — ISO obrig. (ADENDO 21/06 §D.4).
> **Imagem hoje:** o host **rebuilda** localmente no pull (sem registry). Melhoria ISO-portabilidade em `SPR-G3`: CI **builda + push p/ GHCR** (imagem versionada/digest-pinned) e o Debian **puxa** a imagem exata (reprodutível, sem build em prod).

**Conformidade ISO — o que TODO sprint deve cumprir (`Manutenabilidade_iso.md`):**

| Exigência ISO | Onde no fluxo |
|---|---|
| Mudança **atrás de flag default-OFF**, no compose versionado (ISO obrig. #4) | brief Guardrails + GATE 3 |
| **Retro-compatível/aditivo** (migração + contrato/overlay; não remover/renomear chaves) | DoD + migração aditiva |
| **INV-3 inviolável** (sempre `APOSTAR`; novo modulador entra como `min()`) | brief Guardrails |
| **Persistência round-trip**: campo de motor novo entra em `save()`+`load()`+`reset_session()` | brief ISO-checklist |
| **Lint silent-except**: novo `except` → `python tools/lint_silent_except.py --update` | brief ISO-checklist + CI |
| **Suíte completa verde** + evidência de produção (boundary) | DoD |
| **ADENDO** em `Manutenabilidade_iso.md` (capacidades + impacto ISO por característica + scorecard + obrigações + **Rollback**) | closeout do brief |
| **Extensão**: bump `manifest.version` + reload no Chrome | brief (sprints BLK-A) |
| **prod-writes** (deploy / `backfill --apply` / publish) **gated por aprovação** | GATES 1–3 |

**Gaps que o ISO já lista (§D) → mapeados no backlog:** God Object `message_handler` → **`SPR-T7`** (extrair `DecisionPipeline`); coverage `server/` 50→75 → `SPR-X3`+; AGE sem uso (imagem ~1 GB) → `SPR-T3`; `spin_autoencoder.joblib` untracked (hazard `git clean`) → ops/`SPR-G4`; restore-drill não ensaiado → `SPR-T3`; sem AsyncAPI spec → contrato/`SPR-O1`; `datetime.utcnow()` deprecations → limpeza.

---

### Apêndice — âncoras
- Engine: `main.py`, `server/websocket.py:479`, `server/message_handler.py:390/483`, `server/health_server.py:619`.
- Estratégia: `strategies/sda17.py:166` (`analyze`), `app_config/settings.py:110/141/125` (flags), `config/strategy.toml`.
- Dados: `database/sqlite_repo.py:186` (DDL `decisions`), `migrations/versions/0002` (`strategy_versions`/`feature_flags`).
- Deploy: `docker-compose.yml`, `scripts/roleta-deploy-pull.sh`, `.github/workflows/{ci,deploy}.yml`, `tools/systemd/roleta-deploy.{service,timer}`.
- Extensão: `extension/manifest.json:4` (v3.4.2), `extension/background.js` (WS + foto), `extension/deal_capture.js`.
- Relacionado: `auditoria_24_junho.md` (edge/geometria), `resultados_22_junho.md`.

# 📐 Roleta Cloud — Arquitetura & Conformidade ISO/IEC 25010

> **Versão do Software:** 3.5.0  
> **Data da Análise:** 19/03/2026  
> **Base:** Auditoria pós-implantação (execuções de 19/03/2026)  
> **Norma de Referência:** ISO/IEC 25010:2011 — Modelo de Qualidade de Produto de Software  
> **Total de Linhas de Código:** 5.193 (37 arquivos Python)

---

## PARTE I — ARQUITETURA COMPLETA DO SOFTWARE

---

### 1. Visão Geral

O **Roleta Cloud** é um backend em tempo real para processamento de dados de roleta europeia. Recebe resultados (spins) via WebSocket a partir de uma extensão Chrome, aplica análise estatística com a estratégia proprietária SDA-19, e retorna sugestões de aposta para um overlay no navegador.

```
┌─────────────────────┐         WebSocket (ws/wss)        ┌─────────────────────┐
│   Extensão Chrome   │ ◄──────────────────────────────── │   Roleta Cloud      │
│   (content.js)      │ ────────────────────────────────► │   (Python 3.12)     │
│                     │   spins, histórico, comandos      │                     │
│   • Extrator DOM    │   ◄── sugestões, state_sync       │   • WebSocket Server│
│   • Overlay UI      │                                   │   • Game Engine     │
│   • Popup Dashboard │                                   │   • SDA-19 Strategy │
└─────────────────────┘                                   │   • SQLite DB       │
                                                          └─────────────────────┘
```

**Stack Tecnológico:**

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Linguagem | Python | 3.12 |
| Transporte | websockets | ≥ 12.0 |
| Validação | Pydantic | ≥ 2.0 |
| Configuração | pydantic-settings | ≥ 2.0 |
| Logging | structlog | ≥ 24.0 |
| Banco de Dados | SQLite 3 (WAL mode) | Built-in |
| Containerização | Docker | compose v2 (sem version attr) |
| Cliente | Extensão Chrome | Manifest V3 |

---

### 2. Estrutura de Diretórios

```
Roleta Cloud/
├── main.py                          # Entry point (49 LOC)
├── VERSION                          # Versão semântica (3.5.0)
├── requirements.txt                 # Dependências Python
├── Dockerfile                       # Imagem Docker (python:3.12-slim)
├── docker-compose.yml               # Orquestração com volume persistente
├── state.json                       # Estado in-memory persistido (atômico)
├── SECURITY.md                      # Política de segurança
│
├── app_config/                      # ── Configuração ──
│   └── settings.py                  # Pydantic Settings (env vars)
│
├── core/                            # ── Núcleo Imutável ──
│   ├── roulette.py                  # Modelo físico da roleta (311 LOC)
│   ├── engine.py                    # Motor de jogo puro (130 LOC)
│   └── logging_config.py            # Configuração structlog (55 LOC)
│
├── models/                          # ── Modelos de Dados ──
│   ├── input.py                     # SpinInput (Pydantic)
│   ├── output.py                    # SuggestionOutput, AckOutput, ErrorOutput
│   └── trace.py                     # TraceContext para observabilidade
│
├── strategies/                      # ── Estratégias de Análise ──
│   ├── base.py                      # StrategyBase (ABC) + StrategyResult
│   └── sda17.py                     # SDA-19 (IQR + Weighted Median + Drift)
│
├── state/                           # ── Estado do Jogo ──
│   ├── game.py                      # GameState + MartingaleState (493 LOC)
│   ├── timeline.py                  # Timeline por direção (deque)
│   └── bet_advisor.py               # Kill Switch Advisor (Triple Rate)
│
├── server/                          # ── Camada de Rede ──
│   ├── websocket.py                 # Servidor WebSocket + heartbeat
│   ├── connection_manager.py        # Master/Slave + grace period
│   ├── message_handler.py           # Dispatcher de mensagens (473 LOC)
│   ├── analytics_handler.py         # Queries analíticas via WS
│   ├── extractor_service.py         # Configuração dinâmica de mesas
│   └── configs/                     # Templates JSON de providers
│
├── auth/                            # ── Autenticação ──
│   └── middleware.py                # API Key (HMAC-safe) / bypass mode
│
├── database/                        # ── Persistência ──
│   ├── __init__.py                  # Factory singleton
│   ├── models.py                    # Decision, Session, GaleWindow, WindowPlay
│   ├── repository.py                # Interface abstrata (ABC)
│   ├── sqlite_repo.py               # Implementação SQLite (~850 LOC)
│   └── service.py                   # DatabaseService (negócio)
│
├── extension/                       # ── Extensão Chrome ──
│   ├── manifest.json                # Manifest V3
│   ├── background.js                # Service worker
│   ├── content.js                   # Extrator DOM + overlay
│   ├── popup.html / popup.js        # Dashboard popup
│   └── overlay.css                  # Estilos do overlay
│
├── tests/                           # ── Testes ──
│   ├── conftest.py                  # Configuração pytest
│   ├── test_core.py                 # Testes RouletteCore (123 LOC)
│   ├── test_sda17.py                # Testes SDA-19 (56 LOC)
│   ├── test_bet_advisor.py          # Testes Kill Switch (69 LOC)
│   ├── test_game_state.py           # Testes GameState (116 LOC)
│   └── test_db_query.py             # Testes queries DB (32 LOC)
│
├── tools/                           # ── Ferramentas ──
│   └── backtest_from_db.py          # Backtest offline (339 LOC)
│
├── scripts/                         # ── Scripts de Deploy ──
│   └── setup_server.sh              # Setup do servidor Debian
│
├── data/                            # ── Dados Persistentes ──
│   └── decisions.db                 # ⚠️ CÓPIA LOCAL (NÃO é o banco de produção)
│                                    # O banco real está no Docker Named Volume
│                                    # Ver seção "Acesso ao Banco de Dados"
│
└── archive/                         # ── Código legado arquivado ──
```

---

### 3. Diagrama de Componentes e Dependências

```
                    ┌──────────────────────────────────────────────────┐
                    │                  main.py                         │
                    │  • Signal handlers (SIGINT/SIGTERM)              │
                    │  • asyncio.run(start_server())                   │
                    └──────────────┬───────────────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────────────┐
                    │          server/websocket.py                      │
                    │  • WebSocket Server (ws/wss)                      │
                    │  • Heartbeat broadcast (1s)                       │
                    │  • SSL/TLS opcional                               │
                    │  • Handler de conexão → connection_manager        │
                    └───┬──────────────────────┬───────────────────────┘
                        │                      │
         ┌──────────────▼──────┐  ┌────────────▼──────────────────────┐
         │ connection_manager  │  │      message_handler              │
         │ • Master/Slave      │  │  • Dispatcher por msg_type        │
         │ • Grace period 10s  │  │  • novo_resultado → engine        │
         │ • Device ID track   │  │  • historico_inicial              │
         │ • MAX_CONNECTIONS   │  │  • correcao_historico             │
         │ • Broadcast         │  │  • nova_sessao                   │
         └─────────────────────┘  │  • register / force_master       │
                                  │  • extrair_mesa / listar_mesas   │
                                  │  • analytics (delegado)          │
                                  └───┬───────────┬──────────────────┘
                                      │           │
                       ┌──────────────▼──┐  ┌─────▼────────────────────┐
                       │  core/engine.py  │  │ analytics_handler        │
                       │  GameEngine      │  │ • summary / sessions     │
                       │  • process_spin  │  │ • gale_history           │
                       │  • check_pred    │  │ • performance_timeline   │
                       │  • SDA + TR      │  │ • decision_log           │
                       └──┬────────┬──────┘  └─────────────────────────┘
                          │        │
           ┌──────────────▼──┐  ┌──▼─────────────────────────┐
           │  strategies/    │  │  state/                      │
           │  sda17.py       │  │  ├── game.py (GameState)     │
           │  • IQR filter   │  │  │   • Duas timelines        │
           │  • Weighted Med │  │  │   • 4 listas performance  │
           │  • Drift detect │  │  │   • 2 Martingales (CW/CCW)│
           │  • Smart Score  │  │  │   • Persistência atômica  │
           │  • 19 números   │  │  ├── timeline.py (deque)     │
           └──────┬──────────┘  │  └── bet_advisor.py          │
                  │             │      • Kill Switch (C4+SDA≤2)│
                  │             └──────────────────────────────┘
                  │
           ┌──────▼──────────┐
           │  core/roulette  │
           │  RouletteCore   │
           │  • WHEEL_SEQUENCE│
           │  • 37 slots     │
           │  • Cálc. circular│
           │  • Singleton    │
           └─────────────────┘

           ┌─────────────────────────────────────────┐
           │           database/                      │
           │  ┌──────────────────────────────────┐   │
           │  │ repository.py (ABC)               │   │
           │  │ DecisionRepository               │   │
           │  └──────────┬───────────────────────┘   │
           │             │ implementa                 │
           │  ┌──────────▼───────────────────────┐   │
           │  │ sqlite_repo.py (~850 LOC)         │   │
           │  │ • WAL mode + busy_timeout         │   │
           │  │ • 4 tabelas: sessions, decisions, │   │
           │  │   gale_windows, window_plays       │   │
           │  │ • 10 índices                       │   │
           │  └──────────────────────────────────┘   │
           │  ┌──────────────────────────────────┐   │
           │  │ service.py (Singleton)            │   │
           │  │ • track_gale_window               │   │
           │  │ • get_window_history              │   │
           │  └──────────────────────────────────┘   │
           └─────────────────────────────────────────┘
```

---

### 4. Fluxo de Dados Principal

```
EXTENSÃO CHROME                      SERVIDOR PYTHON
─────────────────                    ─────────────────

1. DOM detecta spin ──────────────► WebSocket recebe
   {numero, direcao,                 message_handler.process_message()
    trace_id, t_client}

2.                                   Verificar role (MASTER only)
                                     Verificar duplicata (hash)

3.                                   check_prediction(numero)
                                     ├── Compara com pending_prediction
                                     ├── Registra em performance_sda17
                                     └── Se bet_placed: performance_bet

4.                                   Martingale update (se apostou)
                                     ├── window_hits / window_count
                                     ├── Transição G1→G2→G3→STOP
                                     └── track_gale_window() → DB

5.                                   process_spin(numero, direcao)
                                     ├── Calcula força (distância circular)
                                     ├── Adiciona à timeline CW ou CCW
                                     └── game_state.save() (atômico)

6.                                   SDA-19 analyze(target_timeline)
                                     ├── IQR outlier rejection
                                     ├── Weighted median (decay=0.8)
                                     ├── Drift detection
                                     ├── Smart Score (1-6)
                                     └── 19 vizinhos do centro

7.                                   Kill Switch Advisor
                                     ├── C4/M6/L12 rates
                                     ├── KILL se C4=0% + SDA≤2
                                     └── APOSTAR em todos outros casos

8.                                   Decision final
                                     ├── APOSTAR: SDA + TR aprovaram
                                     ├── PULAR: TR vetou ou SDA insuficiente
                                     └── save_decision() → DB

9. ◄──────────────────────────────── Resposta {sugestao}
   Overlay renderiza                 ├── acao, numeros, centro, regiao
   ação no navegador                 ├── confianca, martingale, gale
                                     ├── bet_advice (TR details)
                                     └── trace completo

10.                                  Broadcast trace para dashboards
                                     ├── Steps com timestamps
                                     └── Performance stats
```

---

### 5. Modelo de Dados (SQLite)

```
┌──────────────┐       ┌─────────────────┐       ┌──────────────────┐
│  sessions    │       │   decisions      │       │  gale_windows    │
├──────────────┤       ├─────────────────┤       ├──────────────────┤
│ id (PK)      │◄──┐   │ id (PK, AUTO)   │       │ id (PK, AUTO)    │
│ start_time   │   │   │ session_id (FK) ─┼──────►│ direction        │
│ end_time     │   │   │ timestamp        │       │ gale_level       │
│ total_spins  │   │   │ spin_number      │       │ started_at       │
│ total_bets   │   │   │ spin_direction   │       │ ended_at         │
│ total_hits   │   │   │ spin_force       │       │ total_hits       │
│ total_profit │   │   │ tr_should_bet    │       │ total_plays      │
│ max_gale     │   │   │ tr_confidence    │       │ result           │
│ total_stops  │   │   │ tr_reason        │       │ next_level       │
└──────────────┘   │   │ tr_c4/m6/l12_rate│       │ sda17_rate_start │
                   │   │ sda_should_bet   │       │ bet_rate_start   │
                   │   │ sda_score/center │       │ calibration_off  │
                   │   │ sda_numbers (JSON)│      └───────┬──────────┘
                   │   │ sda_predicted_f   │              │
                   │   │ final_action      │              │
                   │   │ action_reason     │      ┌───────▼──────────┐
                   │   │ gale_level/hits   │      │  window_plays    │
                   │   │ result_hit/actual │      ├──────────────────┤
                   │   │ calibration_off   │      │ id (PK, AUTO)    │
                   │   │ perf_snapshot(JSON)│     │ window_id (FK)   │
                   │   └─────────────────┘       │ play_number      │
                   │                              │ spin_number      │
                   └──────────────────────────────│ spin_direction   │
                                                  │ spin_force       │
                                                  │ center_predicted │
                                                  │ hit / actual     │
                                                  │ sda_score        │
                                                  │ tr_confidence    │
                                                  │ tr_reason        │
                                                  └──────────────────┘

Índices: 10 (session, timestamp, action, gale_level, direction, level, started, window_id, active)
Constraint: UNIQUE idx_gale_windows_active — apenas 1 janela aberta por direção
```

---

### 6. Sistema de Decisão (Pipeline SDA-19 + Kill Switch)

```
                       Forças da Timeline (últimas 7)
                              │
                    ┌─────────▼──────────┐
                    │  IQR Outlier Filter │  Remove forças fora de [Q1-1.5·IQR, Q3+1.5·IQR]
                    │  (skip se N < 4)    │  Fallback: usa todos se < 2 sobrevivem
                    └─────────┬──────────┘
                              │ clean forces
                    ┌─────────▼──────────┐
                    │  Weighted Median    │  Peso = 0.8^posição (mais recente = maior peso)
                    │  (decay = 0.8)      │  Expansão: força × (weight × 10) repetições
                    └─────────┬──────────┘
                              │ predicted_force (base)
                    ┌─────────▼──────────┐
                    │  Drift Detection   │  Se últimas 3 forças são monotônicas:
                    │  (tendência)        │  drift_adj = sum(diffs) × 0.5
                    └─────────┬──────────┘
                              │ predicted_force (ajustada)
                    ┌─────────▼──────────┐
                    │  Smart Score        │  score = survival × 3 + tightness × 3 + stable_bonus
                    │  (1-6)              │  tightness = 1 - spread/15
                    └─────────┬──────────┘
                              │ {should_bet, center, numbers[19], score}
                    ┌─────────▼──────────┐
                    │  Kill Switch (TR)   │  VETA se: C4 == 0% AND sda_score ≤ 2
                    │  Advisor v2         │  APROVA em todos os outros casos
                    └─────────┬──────────┘
                              │ {acao: APOSTAR | PULAR}
                    ┌─────────▼──────────┐
                    │  Martingale State   │  G1(R$19) → G2(R$38) → G3(R$76) → STOP
                    │  Window de 5 jogadas│  3+/5 acertos = sucesso (volta G1)
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Resposta ao Client │  JSON via WebSocket
                    │  + DB Logging       │  27 campos por decisão
                    └────────────────────┘
```

---

### 7. Protocolo WebSocket — Tipos de Mensagem

| Direção | Tipo | Descrição | Role |
|---------|------|-----------|------|
| `C → S` | `novo_resultado` | Novo spin {numero, direcao} | MASTER only |
| `C → S` | `historico_inicial` | Batch de spins históricos | MASTER only |
| `C → S` | `correcao_historico` | Reset + reprocessar | MASTER only |
| `C → S` | `nova_sessao` | Reset de sessão/dealer | Any |
| `C → S` | `get_state` | Solicita estado atual | Any |
| `C → S` | `register` | Registra device_id | Any |
| `C → S` | `force_master` | Força role MASTER | Any |
| `C → S` | `extrair_mesa` | Snapshot DOM da mesa | Any |
| `C → S` | `listar_mesas` | Lista mesas configuradas | Any |
| `C → S` | `get_analytics_*` | Queries analíticas | Any |
| `S → C` | `sugestao` | Resposta com ação + números | Broadcast |
| `S → C` | `state_sync` | Heartbeat 1s com estado | Broadcast |
| `S → C` | `trace` | Trace completo do pipeline | Broadcast |
| `S → C` | `role_assigned` | Role atribuído na conexão | Unicast |
| `S → C` | `role_changed` | Mudança de role | Unicast |
| `S → C` | `ack` | Confirmação de recebimento | Unicast |
| `S → C` | `error` | Erro com código + mensagem | Unicast |

---

### 8. Modelo de Conexão (Master/Slave)

```
┌──────────────────────────────────────────────────────────┐
│                SISTEMA MASTER / SLAVE                      │
├──────────────────────────────────────────────────────────┤
│                                                            │
│  Nova conexão → SLAVE (se já existe MASTER ativo)         │
│  Nova conexão → MASTER (se nenhum MASTER existe)          │
│                                                            │
│  MASTER desconecta:                                       │
│  ├── Grace period = 10 segundos                           │
│  ├── Se reconecta (mesmo device_id): restaura MASTER      │
│  └── Se não reconecta: último SLAVE promovido             │
│                                                            │
│  Apenas MASTER pode enviar:                               │
│  ├── novo_resultado                                       │
│  ├── historico_inicial                                    │
│  └── correcao_historico                                   │
│                                                            │
│  MAX_CONNECTIONS = 50                                     │
│  Rejeita com código 1013 ("Servidor lotado")              │
└──────────────────────────────────────────────────────────┘
```

---

### 9. Containerização e Deploy

```yaml
# Docker Compose - Produção
services:
  roleta-cloud:
    image: python:3.12-slim
    ports: ["127.0.0.1:8765:8765"]
    volumes:
      - roleta-data:/app/data        # Banco SQLite persistido
      - ./state.json:/app/state.json # Estado do jogo
      - ./server/configs:/app/server/configs:ro
    environment:
      - WS_HOST=0.0.0.0
      - WS_PORT=8765
      - SSL_ENABLED=false
      - AUTH_ENABLED=false
    healthcheck:
      test: socket connect localhost:8765
      interval: 30s, timeout: 5s, retries: 3
    logging:
      driver: json-file
      max-size: 10m, max-file: 3
```

#### ⚠️ Acesso ao Banco de Dados de Produção

O banco SQLite de produção **NÃO** está em `/root/roleta-cloud/data/decisions.db`.
Ele reside no **Docker Named Volume** `roleta-data`:

| Caminho | Tipo | Status |
|---------|------|:------:|
| `/root/roleta-cloud/data/decisions.db` | Arquivo host | ❌ **STALE** — cópia antiga, não é atualizado |
| `/app/data/decisions.db` (container) | Named Volume | ✅ **PRODUÇÃO** — banco real e atual |
| `/var/lib/docker/volumes/roleta-cloud_roleta-data/_data/decisions.db` | Volume no disco | ✅ Mesmo arquivo que o container usa |

**Como acessar os dados reais:**

```bash
# ✅ CORRETO — via docker exec
docker exec -i roleta-cloud python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/decisions.db')
print(conn.execute('SELECT COUNT(*) FROM decisions').fetchone()[0])
"

# ✅ CORRETO — acesso direto ao volume no host
sqlite3 /var/lib/docker/volumes/roleta-cloud_roleta-data/_data/decisions.db "SELECT COUNT(*) FROM decisions;"

# ❌ ERRADO — arquivo host desatualizado (NÃO usar para análise)
sqlite3 /root/roleta-cloud/data/decisions.db
```

**Backup do banco de produção:**

```bash
docker exec roleta-cloud cp /app/data/decisions.db /app/data/decisions_backup_$(date +%Y%m%d_%H%M%S).db
```

---

### 9. Banco de Dados — Inventário e Fluxo Completo

> **Atualizado em:** 27/Mar/2026 (pós-refatoração)

#### 9.1 Bancos de Produção Ativos

| # | Localização | Tipo | Função | Acesso |
|:-:|-------------|------|--------|--------|
| 1 | Docker Volume `roleta-data` | SQLite (WAL) | Banco principal: decisions, sessions, gale_windows, window_plays | `docker exec roleta-cloud python3 -c "..."` |
| 2 | Host `state.json` (bind mount) | JSON | Estado do jogo: timelines, martingale, pending_prediction | Leitura direta no host ou container |
| 3 | Chrome Extension | `chrome.storage.local/session` | Estado da extensão: escutaState, currentDirection, overlayUIState | DevTools → Application → Storage |

#### 9.2 Bancos Legado (somente leitura/referência)

| # | Localização | Tamanho | Conteúdo |
|:-:|-------------|:-------:|----------|
| 1 | `archive/legado_bancos/sda_datalake.db` | 4.76 MB | 15.109 rows de performance_log (18 preditores antigos) |
| 2 | `archive/legado_bancos/microservico_datalake.db` | 40 KB | 90 rows de previsões v2 |

#### 9.3 Schema do Banco de Produção (SQLite)

```sql
-- sessions: metadados de cada sessão de jogo
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    start_time DATETIME NOT NULL,
    end_time DATETIME,               -- Preenchido ao finalizar (shutdown/reset)
    total_spins INTEGER DEFAULT 0,   -- Atualizado a cada 10 decisões e no shutdown
    total_bets INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    total_profit REAL DEFAULT 0.0,
    max_gale_reached INTEGER DEFAULT 1,
    total_stops INTEGER DEFAULT 0,   -- DEPRECATED (Smart Gale v4 não para)
    total_resets INTEGER DEFAULT 0   -- Smart Gale v4: resets a G1 após miss
);

-- decisions: cada spin processado pelo sistema
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT REFERENCES sessions(id),
    spin_number INTEGER, spin_direction TEXT, spin_force INTEGER,
    tr_should_bet BOOLEAN, tr_confidence TEXT, tr_reason TEXT,
    tr_c4_rate REAL, tr_m6_rate REAL, tr_l12_rate REAL,
    sda_should_bet BOOLEAN, sda_score INTEGER, sda_center INTEGER,
    sda_centers TEXT,  -- JSON array [C1, C2, C3] — SDA-21
    sda_numbers TEXT, sda_predicted_force INTEGER,
    final_action TEXT, action_reason TEXT,
    gale_level INTEGER, gale_window_hits INTEGER,
    gale_window_count INTEGER, gale_bet_value INTEGER,
    result_hit BOOLEAN, result_actual INTEGER,
    calibration_offset INTEGER,  -- DEPRECATED (sempre 0 desde v1.5)
    calibration_error INTEGER,   -- DEPRECATED
    performance_snapshot TEXT
);

-- gale_windows: janelas de Martingale para ML/analytics
CREATE TABLE gale_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL, gale_level INTEGER NOT NULL,
    started_at DATETIME NOT NULL, ended_at DATETIME,
    total_hits INTEGER DEFAULT 0, total_plays INTEGER DEFAULT 0,
    result TEXT,  -- 'streak', 'reset', 'info', 'orphan'
    next_level INTEGER,
    sda17_rate_at_start REAL, bet_rate_at_start REAL,
    calibration_offset INTEGER
);
-- CONSTRAINT: apenas 1 janela ativa por direção
CREATE UNIQUE INDEX idx_gale_windows_active ON gale_windows(direction) WHERE ended_at IS NULL;

-- window_plays: jogadas individuais dentro de cada janela
CREATE TABLE window_plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_id INTEGER REFERENCES gale_windows(id),
    play_number INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    spin_number INTEGER, spin_direction TEXT, spin_force INTEGER,
    center_predicted INTEGER, hit BOOLEAN, actual_number INTEGER,
    sda_score INTEGER, tr_confidence TEXT, tr_reason TEXT
);
```

#### 9.4 Fluxo de Dados Completo

```
Chrome Extension (chrome.storage)
    │ WebSocket (wss://roleta.xma-ia.com/ws)
    ▼
message_handler.py
    ├─ check_prediction(numero)        → Verifica predição anterior
    ├─ SmartGaleV4.update(hit)         → Atualiza gale da direção
    ├─ db_service.track_gale_window()  → Grava em gale_windows + window_plays
    ├─ GameState.process_spin()        → Atualiza timeline + forças
    ├─ GameState.save()                → Grava state.json (bind mount)
    ├─ sda17.analyze()                 → SDA-21 Triple Focus → predição
    ├─ bet_advisor.analyze()           → Kill Switch Advisor → c4_rate
    ├─ SmartGaleV4.get_gale()          → Nível de aposta (1×/2×/3×)
    ├─ db_service.save_decision()      → Grava em decisions (Named Volume)
    ├─ db_service.update_session_stats() → A cada 10 decisões
    └─ WebSocket.send(overlay)         → Envia sugestão para Chrome
```

#### 9.5 Ciclo de Vida da Sessão

| Evento | Ação no DB |
|--------|-----------|
| Extensão envia `nova_sessao` | `create_session()` → nova row em sessions |
| A cada spin | `save_decision()` → nova row em decisions |
| A cada 10 decisões | `update_session_stats()` → atualiza totais em sessions |
| Reset de sessão | `end_session()` → define end_time + stats finais → `create_session()` nova |
| Shutdown (SIGTERM/SIGINT) | `end_session()` → finaliza sessão + `game_state.save()` |

---

## PARTE II — ANÁLISE ISO/IEC 25010

A norma **ISO/IEC 25010:2011** define 8 características de qualidade de produto de software, cada uma com sub-características. A seguir, cada uma é avaliada contra o estado atual do Roleta Cloud v3.5.0.

---

### 1. ADEQUAÇÃO FUNCIONAL (Functional Suitability)

> *O produto fornece funções que atendem às necessidades declaradas e implícitas quando usado nas condições especificadas.*

#### 1.1 Completude Funcional

| Requisito | Status | Evidência |
|-----------|:------:|-----------|
| Receber spins em tempo real | ✅ Completo | `message_handler.handle_new_result()` — validação Pydantic (0-36) |
| Calcular predições (SDA-19) | ✅ Completo | Pipeline IQR → Weighted Median → Drift → Score (19 números) |
| Gerenciar Martingale | ✅ Completo | Dois Martingales independentes (CW/CCW), janela de 5, G1→G2→G3→STOP |
| Kill Switch (Triple Rate) | ✅ Completo | Veta apenas catástrofe (C4=0% + SDA≤2), mínimo intervencionista |
| Persistir decisões | ✅ Completo | SQLite com 27 campos, 4 tabelas, 10 índices |
| Analytics via WebSocket | ✅ Completo | 5 queries (summary, sessions, gale, timeline, decision_log) |
| Extensão Chrome | ✅ Completo | Manifest V3, DOM extractor, overlay, popup dashboard |
| Similarity Search (LanceDB) | ⏸️ Preparado | Código em `archive/vector_store.py`, ativação quando volume > 5.000 decisões |

**Avaliação: 9/10** — Todas as funcionalidades declaradas estão implementadas e operacionais.

#### 1.2 Correção Funcional

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Sequência da roleta europeia | ✅ | 37 números, ordem física verificada |
| Cálculo de força circular | ✅ | Testes em `test_core.py` (123 LOC) |
| IQR com N < 4 | ✅ | BUG-009 corrigido — skip IQR quando N < 4 |
| Drift formula | ✅ | Corrigido para `int(sum(diffs) * 0.5)` |
| Direção do Martingale | ✅ | Usa `pending_prediction["direction"]` (target) |
| Deduplicação de spins | ✅ | Hash `{numero}_{timestamp//1000}` |
| Validação de direção | ✅ | BUG-011: só aceita "horario" / "anti-horario" |

**Avaliação: 8/10** — Bugs críticos foram corrigidos. Colunas mortas no schema (`calibration_offset/error`) ainda presentes.

#### 1.3 Pertinência Funcional

O sistema executa apenas o que é necessário: recebe dados, analisa, decide, retorna. Não há funcionalidades desnecessárias no caminho crítico. O módulo `vector_store.py` está corretamente desativado até o volume de dados justificar sua ativação.

**Avaliação: 9/10**

---

### 2. EFICIÊNCIA DE DESEMPENHO (Performance Efficiency)

> *Desempenho relativo à quantidade de recursos usados sob condições declaradas.*

#### 2.1 Comportamento Temporal

| Métrica | Valor | Análise |
|---------|-------|---------|
| Latência spin→resposta | < 50ms (típico) | Observado via `TraceContext` — pipeline é CPU-bound puro |
| Heartbeat interval | 1 segundo | Broadcast de estado para todos os clientes |
| Grace period reconexão | 10 segundos | Configurável via `MASTER_GRACE_PERIOD` |
| Ping/Pong WebSocket | 20s interval, 60s timeout | Mantém conexão viva |

**Avaliação: 9/10** — Latência sub-50ms é excelente para tempo real. O pipeline inteiro (IQR + Median + Drift + Score) é O(n) com n ≤ 7 forças.

#### 2.2 Utilização de Recursos

| Recurso | Uso | Otimização |
|---------|-----|-----------|
| Memória | ~30MB base | Timelines com `deque(maxlen=45)` — auto-trim |
| Performance lists | `deque(maxlen=12)` | BUG-009 corrigido — impossível crescer indefinidamente |
| Conexões WS | Max 50 | `MAX_CONNECTIONS` em ConnectionManager |
| SQLite | WAL mode + busy_timeout=5s | Permite leituras concorrentes |
| Logs | JSON rotacionado (10MB × 3) | Via Docker logging driver |
| Estado | ~2KB JSON | Escrita atômica com `tempfile` + `os.replace` + fallback Docker |
| SQLite conns | Gerenciadas | Conexões com `try/finally: conn.close()` em cada operação |

**Avaliação: 9/10** — Uso eficiente. Conexões SQLite corretamente gerenciadas com close explícito.

#### 2.3 Capacidade

| Dimensão | Limite | Notas |
|----------|--------|-------|
| Conexões simultâneas | 50 | Rejeita com código 1013 |
| Timeline | 45 forças por direção | `max_timeline_size` em settings |
| Performance tracking | 12 resultados por lista | 4 listas × 2 direções |
| Decisões no DB | Ilimitado | SQLite suporta até ~140TB |
| Janelas Gale ativas | 1 por direção | Constraint UNIQUE no DB |

**Avaliação: 8/10**

---

### 3. COMPATIBILIDADE (Compatibility)

> *Grau em que um produto pode trocar informações e/ou executar suas funções enquanto compartilha o mesmo ambiente.*

#### 3.1 Coexistência

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Docker isolado | ✅ | Container independente, não interfere com outros serviços |
| Porta configurável | ✅ | `WS_PORT` via variável de ambiente |
| Volume dedicado | ✅ | `roleta-data` para SQLite — **acessar via `docker exec` ou path do volume** |

#### 3.2 Interoperabilidade

| Interface | Protocolo | Formato |
|-----------|----------|---------|
| WebSocket | ws:// / wss:// | JSON |
| Extensão Chrome | Manifest V3 | content script |
| Banco de Dados | SQLite 3 | Arquivo local |
| Configuração | ENV vars | `.env` file suportado |

**Avaliação: 7/10** — Sem REST API HTTP (apenas WebSocket). Isso limita integração com ferramentas externas (Grafana, APIs REST, webhooks). Interoperabilidade futura planejada via `analytics_handler`.

---

### 4. USABILIDADE (Usability)

> *Grau em que o produto pode ser usado por usuários especificados para atingir objetivos com eficácia, eficiência e satisfação.*

#### 4.1 Reconhecibilidade de Adequação

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Banner no startup | ✅ | ASCII art "ROLETA CLOUD v{VERSION}" — lê dinamicamente do arquivo `VERSION` |
| README.md | ✅ | Documentação de uso |
| Logs informativos | ✅ | Emojis como indicadores visuais (👑, 📱, 🔄, 🛑) |

#### 4.2 Apreensibilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Variáveis de ambiente documentadas | ✅ | Em `main.py` docstring e `docker-compose.yml` |
| Modelos Pydantic auto-documentados | ✅ | `SpinInput` com `Field(description=...)` |
| Formato de saída documentado | ✅ | `SuggestionOutput` com exemplos JSON Schema |

#### 4.3 Proteção contra Erros

| Mecanismo | Status | Detalhes |
|-----------|:------:|---------|
| Validação de entrada (0-36) | ✅ | Pydantic + validação manual em `handle_new_result` |
| Validação de direção | ✅ | BUG-011: rejeita direções inválidas |
| Deduplicação de spins | ✅ | Previne processamento duplo |
| MASTER-only para dados | ✅ | SLAVE não pode injetar dados |
| ErrorOutput estruturado | ✅ | Código HTTP + mensagem + trace_id |

**Avaliação: 8/10** — Boa usabilidade. Falta documentação de API WebSocket formal (AsyncAPI spec ou similar).

---

### 5. CONFIABILIDADE (Reliability)

> *Grau em que o sistema executa funções especificadas sob condições especificadas por um período de tempo especificado.*

#### 5.1 Maturidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Tratamento de exceções | ✅ | Try/catch em cada handler, fallback para `ErrorOutput` |
| Shutdown graceful | ✅ | `SIGINT/SIGTERM` handlers salvam estado |
| Escrita atômica de estado | ✅ | `tempfile` + `os.replace` previne corrupção |
| Migração de versão | ✅ | v1.3→v1.4→v1.5 com fallback automático |
| DB WAL mode | ✅ | Resistente a crash mid-write |
| Heartbeat | ✅ | Detecção de conexões perdidas |

#### 5.2 Disponibilidade

| Mecanismo | Status | Detalhes |
|-----------|:------:|---------|
| Docker restart policy | ✅ | `unless-stopped` |
| Healthcheck | ✅ | Socket connect a cada 30s com 3 retries |
| Grace period Master | ✅ | 10s para reconexão sem perda de role |
| Promoção automática Slave→Master | ✅ | Último SLAVE é promovido se MASTER não reconectar |
| Restauração de janelas ativas | ✅ | `_init_active_window_ids()` no boot |

#### 5.3 Tolerância a Falhas

| Cenário | Comportamento | Risco Residual |
|---------|--------------|----------------|
| DB indisponível | Warning no log, continua sem persistir | Decisões perdidas silenciosamente |
| Spin duplicado | Ignorado (hash check) | Nenhum |
| JSON inválido | ErrorOutput com código 400 | Nenhum |
| Exceção no handler | ErrorOutput com código 500, conexão mantida | Stack trace pode vazar info interna |
| WebSocket desconecta | Remove de `connections`, grace period | Nenhum |
| Erro no heartbeat | Log de erro, continua | Broadcasting pode falhar silenciosamente |

#### 5.4 Recuperabilidade

| Mecanismo | Detalhes |
|-----------|---------|
| `state.json` | Restaura timelines, performance, Martingale, pending_prediction |
| SQLite WAL | Recuperação automática após crash |
| Migração automática | `GameState.load()` migra formato antigo automaticamente |
| Docker volume | Dados persistem além do ciclo de vida do container |

**Avaliação: 8/10** — Boa resiliência. Falta circuit breaker para DB e métricas de uptime.

---

### 6. SEGURANÇA (Security)

> *Grau em que um produto protege informações e dados de modo que pessoas ou sistemas tenham o grau de acesso apropriado.*

#### 6.1 Confidencialidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| API Key via ENV | ✅ | `ROLETA_API_KEY` nunca hardcoded |
| HMAC-safe comparison | ✅ | `hmac.compare_digest()` previne timing attacks |
| SSL/TLS opcional | ✅ | `wss://` com certificados Let's Encrypt |
| `.env` no .gitignore | ✅ | Política em `SECURITY.md` |
| Auth bypass padrão | ⚠️ | `AUTH_ENABLED=false` por padrão — aceitável para dev, risco em produção |

#### 6.2 Integridade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Validação de entrada | ✅ | Pydantic (0-36), direção validada |
| Master-only writes | ✅ | SLAVE não pode injetar dados no pipeline |
| Escrita atômica | ✅ | `os.replace` é atômico no filesystem |
| DB constraint | ✅ | UNIQUE index garante 1 janela ativa por direção |

#### 6.3 Não-repúdio

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Trace ID por operação | ✅ | `TraceContext` com timestamps por step |
| Decision log | ✅ | 27 campos incluindo `action_reason` |
| Structured logging | ✅ | JSON via structlog (arquivo + console) |
| Session tracking | ✅ | Cada sessão tem ID único |

#### 6.4 Responsabilidade (Accountability)

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Connection ID por sessão | ✅ | UUID[:8] por conexão |
| Device ID tracking | ✅ | Identificação persistente do dispositivo |
| Role assignment logging | ✅ | Log de cada atribuição/mudança de role |

#### 6.5 Autenticidade

| Aspecto | Status | Risco |
|---------|:------:|-------|
| API Key + HMAC | ✅ | Quando `AUTH_ENABLED=true` |
| JWT / Keycloak | ⏸️ Planejado | Placeholders em `settings.py` (TASK-003 das execuções) |
| Device ID validation | ⚠️ | Device ID é informado pelo cliente, sem verificação criptográfica |

**Avaliação: 6/10** — Auth bypass por padrão é risco em produção. Device ID sem verificação criptográfica permite spoofing de identidade. Stack traces em `ErrorOutput` (código 500) podem vazar informações internas. JWT/Keycloak ainda não implementado.

**Bugs identificados pós-implantação:**

| ID | Severidade | Descrição |
|----|:----------:|-----------|
| SEC-001 | ⚠️ Média | `ErrorOutput` com `message=str(e)` pode expor stack traces e caminhos internos ao cliente |
| SEC-002 | ⚠️ Média | Device ID sem assinatura criptográfica — cliente pode enviar qualquer `device_id` |
| SEC-003 | ~~🔵 Baixa~~ ✅ CORRIGIDO | Banner agora lê versão dinamicamente do arquivo `VERSION` (não mais hardcoded) |

---

### 7. MANUTENIBILIDADE (Maintainability)

> *Grau de eficácia e eficiência com que um produto pode ser modificado. Esta é a característica central deste documento.*

#### 7.1 Modularidade

```
Acoplamento entre Módulos (Grau 1-5, menor = melhor):

core/roulette.py     ──► Nenhuma dependência externa           [1] ✅ Excelente
core/engine.py       ──► state, strategies, core.roulette      [2] ✅ Bom
strategies/base.py   ──► state.timeline                        [1] ✅ Excelente
strategies/sda17.py  ──► strategies.base, state.timeline       [2] ✅ Bom
state/timeline.py    ──► app_config.settings                   [1] ✅ Excelente
state/bet_advisor.py ──► Nenhuma dependência                   [1] ✅ Excelente
state/game.py        ──► core.roulette, state.*, app_config    [3] ⚠️ Moderado
models/*             ──► pydantic (externo apenas)             [1] ✅ Excelente
database/repository  ──► database.models (ABC, interface)      [1] ✅ Excelente
database/sqlite_repo ──► database.repository + models          [2] ✅ Bom
database/service.py  ──► database.*, state.game                [3] ⚠️ Moderado
auth/middleware.py   ──► app_config.settings                   [1] ✅ Excelente
server/websocket.py  ──► Quase todos os módulos                [5] ❌ Alto acoplamento
server/msg_handler   ──► Quase todos os módulos                [5] ❌ Alto acoplamento
```

**Análise:** O `core/` e `strategies/` têm excelente separação. A camada `server/` é o ponto de maior acoplamento — `websocket.py` instancia diretamente `GameState`, `SDA17Strategy`, e `MessageHandler`. A extração do `GameEngine` (TASK-015) já mitiga parcialmente este problema.

**Avaliação: 7/10**

#### 7.2 Reusabilidade

| Componente | Reusável? | Detalhes |
|-----------|:---------:|---------|
| `RouletteCore` | ✅ Sim | Singleton sem efeitos colaterais, cálculos puros |
| `GameEngine` | ✅ Sim | Motor puro sem I/O — pode ser usado em backtest |
| `StrategyBase` | ✅ Sim | ABC com interface clara para novas estratégias |
| `SDA17Strategy` | ✅ Sim | Plug-and-play via `StrategyBase` |
| `BetAdvice / TripleRateAdvisor` | ✅ Sim | Sem dependências de I/O |
| `Timeline` | ✅ Sim | Estrutura genérica com deque |
| `DecisionRepository` | ✅ Sim | Interface abstrata — facilita migração |
| `TraceContext` | ✅ Sim | Observabilidade genérica |
| `SpinInput / SuggestionOutput` | ✅ Sim | Pydantic models independentes |
| `MessageHandler` | ❌ Não | Acoplado a WebSocket, game_state, strategy, db_service |

**Avaliação: 8/10** — Excelente reusabilidade nos componentes de domínio.

#### 7.3 Analisabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Structured logging (structlog) | ✅ | JSON em arquivo + console legível |
| TraceContext | ✅ | Cada spin tem trace com timestamps por step |
| Performance stats | ✅ | 4 listas de performance com rates calculadas |
| Decision logging (DB) | ✅ | 27 campos por decisão, auditável |
| Gale Window tracking | ✅ | Janelas com plays individuais no DB |
| Docstrings | ✅ | Todas as classes e métodos públicos documentados |
| Type hints | ✅ | Tipagem completa (typing, dataclass, Pydantic) |
| Testes | ⚠️ | 5 arquivos (396 LOC) — cobertura parcial |

**Cobertura de testes por módulo:**

| Módulo | LOC | Testes | Cobertura |
|--------|:---:|:------:|:---------:|
| `core/roulette.py` | 311 | `test_core.py` (123) | ✅ Boa |
| `strategies/sda17.py` | 213 | `test_sda17.py` (56) | ⚠️ Parcial |
| `state/bet_advisor.py` | 163 | `test_bet_advisor.py` (69) | ⚠️ Parcial |
| `state/game.py` | 493 | `test_game_state.py` (116) | ⚠️ Parcial |
| `database/sqlite_repo.py` | ~850 | `test_db_query.py` (32) | ❌ Mínima |
| `server/message_handler.py` | 473 | — | ❌ Zero |
| `server/connection_manager.py` | 272 | — | ❌ Zero |
| `core/engine.py` | 130 | — | ❌ Zero |

**Avaliação: 7/10** — Boa observabilidade em produção (logs + traces + DB). Cobertura de testes insuficiente nos módulos críticos.

#### 7.4 Modificabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Nova estratégia | ✅ Fácil | Herdar `StrategyBase`, implementar `analyze()` |
| Trocar banco de dados | ✅ Fácil | Implementar `DecisionRepository` (ABC) |
| Nova mensagem WebSocket | ✅ Fácil | Adicionar `elif` no dispatcher de `message_handler` |
| Alterar pipeline SDA | ✅ Fácil | Modificar `_predict_robust()` com passos isolados |
| Alterar Kill Switch | ✅ Fácil | Condição concentrada em uma classe (56 LOC efetiva) |
| Alterar Martingale | ✅ Fácil | `MartingaleState` isolado com `update()` |
| Alterar modelo de dados | ⚠️ Moderado | Schema DDL manual, sem Alembic migrations |
| Alterar protocolo WS | ❌ Difícil | `message_handler` com 473 LOC entrelaçando I/O e lógica |

**Avaliação: 7/10** — Design extensível (Strategy Pattern, Repository Pattern). A falta de migrations e o tamanho do `message_handler` são os pontos fracos.

#### 7.5 Testabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Lógica pura separada | ✅ | `GameEngine`, `TripleRateAdvisor`, `MartingaleState` — sem I/O |
| Backtest offline | ✅ | `tools/backtest_from_db.py` (339 LOC) |
| Fixtures / conftest | ✅ | `tests/conftest.py` configura PYTHONPATH |
| Dependency injection | ⚠️ | `GameEngine` recebe state+strategy (DI parcial) |
| Mocking necessário | ⚠️ | `message_handler` requer mock de WebSocket |
| CI/CD automatizado | ❌ | `.github/workflows/` vazio — sem execução automática |

**Avaliação: 6/10** — Componentes individuais são testáveis, mas falta CI e cobertura é baixa.

**Avaliação Geral de Manutenibilidade: 7.0/10**

---

### 8. PORTABILIDADE (Portability)

> *Grau de eficácia e eficiência com que um sistema pode ser transferido de um ambiente para outro.*

#### 8.1 Adaptabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Configuração via ENV | ✅ | 7 variáveis (WS_HOST, PORT, SSL, AUTH, etc.) |
| Docker | ✅ | `python:3.12-slim` base image |
| Cross-platform | ✅ | Python — roda em Linux, macOS, Windows |
| SQLite portátil | ✅ | Arquivo único, sem servidor externo |

#### 8.2 Instalabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| `pip install -r requirements.txt` | ✅ | 4 dependências (pydantic, websockets, structlog, pydantic-settings) |
| `docker-compose up` | ✅ | Um comando para deploy |
| Setup script | ✅ | `scripts/setup_server.sh` para Debian |
| Volume Docker | ✅ | Dados persistem entre deploys |

#### 8.3 Substituibilidade

| Componente | Substituível? | Interface |
|-----------|:-------------:|-----------|
| SQLite → PostgreSQL | ✅ | `DecisionRepository` (ABC) |
| SQLite → SurrealDB | ✅ | Planejado no código |
| SDA-19 → Outra estratégia | ✅ | `StrategyBase` (ABC) |
| WebSocket → REST | ⚠️ | Requer refatoração do message_handler |
| structlog → outro logger | ✅ | Wrapper do stdlib `logging` |

**Avaliação: 8/10** — Boa portabilidade graças ao Docker e abstrações de repositório.

---

## PARTE III — SCORECARD CONSOLIDADO ISO/IEC 25010

| # | Característica | Sub-características Avaliadas | Nota | Nível |
|:-:|---------------|-------------------------------|:----:|:-----:|
| 1 | **Adequação Funcional** | Completude, Correção, Pertinência | **8.7** | 🟢 |
| 2 | **Eficiência de Desempenho** | Tempo, Recursos, Capacidade | **8.7** | 🟢 |
| 3 | **Compatibilidade** | Coexistência, Interoperabilidade | **7.0** | 🟡 |
| 4 | **Usabilidade** | Reconhecibilidade, Aprendizado, Proteção | **8.0** | 🟢 |
| 5 | **Confiabilidade** | Maturidade, Disponibilidade, Tolerância, Recuperação | **8.5** | 🟢 |
| 6 | **Segurança** | Confidencialidade, Integridade, Não-repúdio, Autenticidade | **6.5** | 🟡 |
| 7 | **Manutenibilidade** | Modularidade, Reusabilidade, Analisabilidade, Modificabilidade, Testabilidade | **7.5** | 🟡 |
| 8 | **Portabilidade** | Adaptabilidade, Instalabilidade, Substituibilidade | **8.0** | 🟢 |

**Nota Geral Ponderada: 7.9 / 10** *(+0.4 após correções de 20/03)*

```
Legenda: 🟢 ≥ 8.0 (Bom)  |  🟡 6.0-7.9 (Adequado, melhorias recomendadas)  |  🔴 < 6.0 (Crítico)
```

---

## PARTE IV — BUGS E OPORTUNIDADES PÓS-IMPLANTAÇÃO

### Bugs Identificados na Auditoria do Filesystem

| ID | Módulo | Severidade | Descrição | Linha |
|----|--------|:----------:|-----------|:-----:|
| BUG-POST-001 | `main.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | Banner agora lê `VERSION` dinamicamente | 44 |
| BUG-POST-002 | `server/websocket.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | `logging.basicConfig()` removido — usa `core/logging_config.py` | 24-31 |
| BUG-POST-003 | `server/extractor_service.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | Typo `"Carragados"` → `"Carregados"` corrigido | 27 |
| BUG-POST-004 | `server/message_handler.py` | 🟡 Média | `str(e)` em `ErrorOutput` pode vazar info interna (paths, stack) para o cliente | 128 |
| BUG-POST-005 | `server/connection_manager.py` | ~~🟡 Média~~ ✅ CORRIGIDO | Grace period task agora é criada DENTRO do `async with master_lock` | 154 |
| BUG-POST-006 | `database/sqlite_repo.py` | 🔵 Baixa | Colunas mortas `calibration_offset` e `calibration_error` no schema — consumem espaço sem uso | 110-111 |
| BUG-POST-007 | `state/game.py` | 🔵 Baixa | `GameState.load()` captura `Exception` genérica e retorna estado vazio silenciosamente — pode mascarar erros de parsing | 501 |
| BUG-POST-008 | `server/connection_manager.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | Grace period não cancelado no CASO 2 — race condition podia causar duplo master (28/03 TASK-01) | 85-90 |
| BUG-MG-001 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | SmartGale v4 ignorava streaks reais — separação por direção impedia detecção de sequências cross-direction (28/03 SmartGale v5) | 52-72 |
| BUG-MG-002 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | c4_rate threshold 0.25 excessivamente agressivo — bloqueava 40% das escalações sem justificativa (ajustado para 0.15) | 61 |
| BUG-PL-001 | `server/message_handler.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | `get_gale()` NUNCA chamado em produção — SmartGale era puramente decorativo. Todas as apostas eram G1 por default (28/03 TASK-01) | 232 |
| BUG-PL-002 | `server/message_handler.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | `sync_global()` ausente — martingales nunca sincronizavam streak cross-direction em produção (28/03 TASK-01) | 163-167 |
| BUG-PL-003 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `global_hit` não passado no `update()` — global_consecutive_hits sempre 0 em produção (28/03 TASK-01) | 163 |
| BUG-PL-004 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `get_bet_c4_rate()` não chamado — filtro de segurança c4 inativo em produção (28/03 TASK-01) | 235 |
| BUG-PL-005 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Fallback early-session ausente — primeiras jogadas da sessão pulavam sem apostar (28/03 TASK-02) | 270-285 |
| BUG-PL-006 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `action_reason` genérico — não incluía score e gale_display para diagnóstico (28/03 TASK-01) | 239 |
| BUG-PL-007 | `server/message_handler.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | `gale_level` no DB era 1-decisão atrasado — get_gale() agora chamado ANTES de gravar (28/03 TASK-01) | 296 |

### Melhorias Recomendadas Pós-Implantação

| ID | Característica ISO | Melhoria | Impacto |
|----|-------------------|----------|---------|
| MEL-ISO-001 | Segurança | Sanitizar mensagens de erro antes de enviar ao cliente (remover paths e stack traces) | 🟡 Médio |
| MEL-ISO-002 | Manutenibilidade | Implementar CI/CD com pytest automatizado (`.github/workflows/ci.yml` vazio) | 🟡 Médio |
| MEL-ISO-003 | Manutenibilidade | Adicionar Alembic migrations para versionamento do schema SQLite | 🟢 Baixo |
| MEL-ISO-004 | Confiabilidade | Circuit breaker no acesso ao SQLite — evitar falha silenciosa | 🟡 Médio |
| MEL-ISO-005 | Compatibilidade | Expor REST API HTTP (além de WebSocket) para integração com ferramentas externas | 🟢 Baixo |
| MEL-ISO-006 | Usabilidade | Documentação AsyncAPI para protocolo WebSocket | 🟢 Baixo |
| MEL-ISO-007 | Eficiência | ~~Connection pooling para SQLite~~ ✅ CORRIGIDO — Conexões agora com `try/finally: conn.close()` | ✅ Feito |
| MEL-ISO-008 | Segurança | Assinatura criptográfica de `device_id` para prevenir spoofing | 🟡 Médio |
| MEL-ISO-009 | Manutenibilidade | ~~Ler versão de `VERSION` file em vez de hardcoded no banner~~ ✅ CORRIGIDO | ✅ Feito |
| MEL-ISO-010 | Confiabilidade | Logging do motivo quando `GameState.load()` falha (atualmente silencioso) | 🟢 Baixo |
| MEL-ISO-011 | Eficiência | ~~N+1 query em `get_gale_window_history()`~~ ✅ CORRIGIDO — Batch IN() query (28/03 TASK-02) | ✅ Feito |
| MEL-ISO-012 | Eficiência | ~~I/O síncrono no event loop async~~ ✅ CORRIGIDO — `asyncio.to_thread()` em ExtractorService + heartbeat (28/03 TASK-03) | ✅ Feito |
| MEL-ISO-013 | Manutenibilidade | ~~`_VALID_DIRECTIONS` local em `process_spin()`~~ ✅ CORRIGIDO — Movido para `ClassVar` (28/03 TASK-04) | ✅ Feito |
| MEL-MG-001 | Eficiência | ~~SmartGale v4 travado em G1~~ ✅ CORRIGIDO — Anti-Martingale com streak global cross-direction (SmartGale v5) | ✅ Feito |
| MEL-MG-002 | Eficiência | ~~Sem take-profit em G3~~ ✅ CORRIGIDO — G3+HIT reseta G1, preserva lucro (SmartGale v5) | ✅ Feito |
| MEL-MG-003 | Confiabilidade | ~~global_hit não sincronizado~~ ✅ CORRIGIDO — sync_global() sincroniza ambos martingales em engine.py | ✅ Feito |
| MEL-PL-001 | Confiabilidade | ~~Pipeline produção sem SmartGale~~ ✅ CORRIGIDO — message_handler.py agora chama get_gale(), sync_global(), get_bet_c4_rate() (28/03 plano_tarefas_sessao13) | ✅ Feito |
| MEL-PL-002 | Adequação Funcional | ~~Sem fallback early-session em produção~~ ✅ CORRIGIDO — Fallback G1 seguro com 21 vizinhos quando SDA insuficiente (28/03 TASK-02) | ✅ Feito |
| MEL-PL-003 | Testabilidade | ~~Sem testes de integração para pipeline produção~~ ✅ CORRIGIDO — 15 testes em test_message_handler_gale.py (28/03 TASK-03) | ✅ Feito |

---

## PARTE V — MAPA DE CONFORMIDADE ISO/IEC 25010

### Matriz Característica × Evidência

| Característica ISO | Artefatos de Evidência | Gaps Identificados |
|-------------------|----------------------|-------------------|
| **Adequação Funcional** | Pipeline SDA-19, Kill Switch, SmartGale v5 (Anti-Martingale), DB logging, Analytics handler, Fallback early-session | Colunas mortas no schema |
| **Eficiência** | TraceContext (latência), deque com maxlen, MAX_CONNECTIONS, SQLite conn try/finally, SmartGale v5 streak global | ✅ Conexões SQLite corrigidas; ✅ N+1 batch query; ✅ asyncio.to_thread(); ✅ Anti-Martingale com take-profit |
| **Compatibilidade** | Docker, ENV vars, JSON protocol | Sem REST API, sem AsyncAPI spec |
| **Usabilidade** | Pydantic models com exemplos, emojis em logs, overlay Chrome, banner dinâmico | ✅ Banner corrigido; falta docs API (AsyncAPI) |
| **Confiabilidade** | Escrita atômica, WAL mode, grace period, healthcheck Docker | ✅ Grace period CASO 2 corrigido (duplo master); sem circuit breaker, erro silencioso em load |
| **Segurança** | HMAC comparison, SSL/TLS, MASTER-only, SECURITY.md, porta 8765 restrita a localhost | Auth bypass default, device_id sem crypto |
| **Manutenibilidade** | Strategy Pattern, Repository Pattern (ABC com 16 métodos), type hints, structlog, 96 testes (15 integração pipeline) | CI vazio, cobertura testes ~50%, sem migrations; ✅ ClassVar _VALID_DIRECTIONS |
| **Portabilidade** | Docker, SQLite portátil, ENV config, setup script | WebSocket-only (sem REST fallback) |

---

## PARTE VI — CONCLUSÃO E RECOMENDAÇÕES

O **Roleta Cloud v3.5.0** apresenta uma arquitetura madura com bons padrões de design (Strategy, Repository, Singleton, Observer via broadcast). A separação entre lógica pura (`core/`, `strategies/`, `state/`) e infraestrutura (`server/`, `database/`) é clara e bem executada.

### Pontos Fortes

1. **Pipeline de decisão testável** — `GameEngine` é puro, sem I/O
2. **Extensibilidade** — novas estratégias via `StrategyBase`, novos bancos via `DecisionRepository`
3. **Observabilidade** — `TraceContext` + structlog + 27 campos por decisão no DB
4. **Resiliência** — escrita atômica, WAL mode, grace period, migração de versão automática
5. **Eficiência** — pipeline sub-50ms, O(n) com n ≤ 7

### Áreas Prioritárias de Melhoria (Ordenadas por Impacto)

1. **Segurança (6.5/10)** — Sanitizar erros, ativar auth em produção, assinar device_id
2. **Manutenibilidade (7.5/10)** — CI/CD automatizado, expandir testes, Alembic migrations
3. **Compatibilidade (7.0/10)** — REST API, documentação AsyncAPI
4. **Usabilidade (8.0/10)** — ~~Corrigir versão no banner~~ ✅ Feito; documentar protocolo WS

### Conformidade ISO/IEC 25010

O software atende ao nível **"Adequado"** (7.9/10) da norma ISO/IEC 25010, com 5 de 8 características no nível "Bom" (≥ 8.0) e nenhuma no nível "Crítico" (< 6.0). Para atingir o nível "Bom" global (≥ 8.0), as ações prioritárias são: reforço de segurança, automação de testes e CI/CD, e expansão da interoperabilidade.

---

> **Documento gerado em:** 19/03/2026 | **Atualizado em:** 28/03/2026 (Pipeline produção: get_gale + sync_global + fallback early-session + 15 testes integração)  
> **Analista:** Auditoria automatizada pós-implantação  
> **Norma:** ISO/IEC 25010:2011 — Systems and Software Quality Requirements and Evaluation (SQuaRE)  
> **Software:** Roleta Cloud v3.5.0 | ~5.500 LOC | 37 arquivos Python  
> **Correções aplicadas:** 22 bugs corrigidos em 20/03 + 12 bugs em 27/03 + 4 tasks Jules em 28/03 + SmartGale v5 em 28/03 + Pipeline fix 7 bugs em 28/03

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
| Containerização | Docker | 3.8 compose |
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
│   ├── sqlite_repo.py               # Implementação SQLite (655 LOC)
│   ├── service.py                   # DatabaseService (negócio)
│   └── vector_store.py              # LanceDB (preparatório, não ativo)
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
│   └── decisions.db                 # Banco SQLite de produção
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
           │  │ sqlite_repo.py (655 LOC)          │   │
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
           │  ┌──────────────────────────────────┐   │
           │  │ vector_store.py (INATIVO)         │   │
           │  │ • LanceDB para similarity search  │   │
           │  │ • Pré-requisito: >5k decisões     │   │
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
    ports: ["8765:8765"]
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
| Similarity Search (LanceDB) | ⏸️ Preparado | Código pronto, ativação quando volume > 5.000 decisões |

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
| Estado | ~2KB JSON | Escrita atômica com `tempfile` + `os.replace` |

**Avaliação: 8/10** — Uso eficiente. SQLite sem connection pooling (nova conexão por operação) pode ser otimizado.

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
| Volume dedicado | ✅ | `roleta-data` para SQLite |

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
| Banner no startup | ✅ | ASCII art "ROLETA CLOUD v1.0.0" (**Nota:** desatualizado, mostra v1.0.0 em vez de v3.5.0) |
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

**Avaliação: 7/10** — Banner de versão desatualizado (v1.0.0 vs v3.5.0). Falta documentação de API WebSocket formal (AsyncAPI spec ou similar).

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
| SEC-003 | 🔵 Baixa | Banner mostra versão do software (`v1.0.0`) — information disclosure (menor) |

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
| `database/sqlite_repo.py` | 655 | `test_db_query.py` (32) | ❌ Mínima |
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
| 2 | **Eficiência de Desempenho** | Tempo, Recursos, Capacidade | **8.3** | 🟢 |
| 3 | **Compatibilidade** | Coexistência, Interoperabilidade | **7.0** | 🟡 |
| 4 | **Usabilidade** | Reconhecibilidade, Aprendizado, Proteção | **7.0** | 🟡 |
| 5 | **Confiabilidade** | Maturidade, Disponibilidade, Tolerância, Recuperação | **8.0** | 🟢 |
| 6 | **Segurança** | Confidencialidade, Integridade, Não-repúdio, Autenticidade | **6.0** | 🟡 |
| 7 | **Manutenibilidade** | Modularidade, Reusabilidade, Analisabilidade, Modificabilidade, Testabilidade | **7.0** | 🟡 |
| 8 | **Portabilidade** | Adaptabilidade, Instalabilidade, Substituibilidade | **8.0** | 🟢 |

**Nota Geral Ponderada: 7.5 / 10**

```
Legenda: 🟢 ≥ 8.0 (Bom)  |  🟡 6.0-7.9 (Adequado, melhorias recomendadas)  |  🔴 < 6.0 (Crítico)
```

---

## PARTE IV — BUGS E OPORTUNIDADES PÓS-IMPLANTAÇÃO

### Bugs Identificados na Auditoria do Filesystem

| ID | Módulo | Severidade | Descrição | Linha |
|----|--------|:----------:|-----------|:-----:|
| BUG-POST-001 | `main.py` | 🔵 Baixa | Banner exibe `v1.0.0` hardcoded — deveria ler de `VERSION` (3.5.0) | 44 |
| BUG-POST-002 | `server/websocket.py` | 🔵 Baixa | `logging.basicConfig()` duplica configuração do `structlog` já feito em `core/logging_config.py` | 24-31 |
| BUG-POST-003 | `server/extractor_service.py` | 🔵 Baixa | Typo: `"Carragados"` → `"Carregados"` na mensagem de log | 27 |
| BUG-POST-004 | `server/message_handler.py` | 🟡 Média | `str(e)` em `ErrorOutput` pode vazar info interna (paths, stack) para o cliente | 128 |
| BUG-POST-005 | `server/connection_manager.py` | 🟡 Média | `disconnect()` acessa `self.master_disconnect_time` fora do lock (`async with master_lock`) — race condition potencial | 154 |
| BUG-POST-006 | `database/sqlite_repo.py` | 🔵 Baixa | Colunas mortas `calibration_offset` e `calibration_error` no schema — consumem espaço sem uso | 110-111 |
| BUG-POST-007 | `state/game.py` | 🔵 Baixa | `GameState.load()` captura `Exception` genérica e retorna estado vazio silenciosamente — pode mascarar erros de parsing | 501 |

### Melhorias Recomendadas Pós-Implantação

| ID | Característica ISO | Melhoria | Impacto |
|----|-------------------|----------|---------|
| MEL-ISO-001 | Segurança | Sanitizar mensagens de erro antes de enviar ao cliente (remover paths e stack traces) | 🟡 Médio |
| MEL-ISO-002 | Manutenibilidade | Implementar CI/CD com pytest automatizado (`.github/workflows/ci.yml` vazio) | 🟡 Médio |
| MEL-ISO-003 | Manutenibilidade | Adicionar Alembic migrations para versionamento do schema SQLite | 🟢 Baixo |
| MEL-ISO-004 | Confiabilidade | Circuit breaker no acesso ao SQLite — evitar falha silenciosa | 🟡 Médio |
| MEL-ISO-005 | Compatibilidade | Expor REST API HTTP (além de WebSocket) para integração com ferramentas externas | 🟢 Baixo |
| MEL-ISO-006 | Usabilidade | Documentação AsyncAPI para protocolo WebSocket | 🟢 Baixo |
| MEL-ISO-007 | Eficiência | Connection pooling para SQLite (evitar nova conexão por operação) | 🟢 Baixo |
| MEL-ISO-008 | Segurança | Assinatura criptográfica de `device_id` para prevenir spoofing | 🟡 Médio |
| MEL-ISO-009 | Manutenibilidade | Ler versão de `VERSION` file em vez de hardcoded no banner | 🟢 Baixo |
| MEL-ISO-010 | Confiabilidade | Logging do motivo quando `GameState.load()` falha (atualmente silencioso) | 🟢 Baixo |

---

## PARTE V — MAPA DE CONFORMIDADE ISO/IEC 25010

### Matriz Característica × Evidência

| Característica ISO | Artefatos de Evidência | Gaps Identificados |
|-------------------|----------------------|-------------------|
| **Adequação Funcional** | Pipeline SDA-19, Kill Switch, Martingale, DB logging, Analytics handler | Colunas mortas no schema |
| **Eficiência** | TraceContext (latência), deque com maxlen, MAX_CONNECTIONS | Sem connection pooling SQLite |
| **Compatibilidade** | Docker, ENV vars, JSON protocol | Sem REST API, sem AsyncAPI spec |
| **Usabilidade** | Pydantic models com exemplos, emojis em logs, overlay Chrome | Banner versão errada, sem docs API |
| **Confiabilidade** | Escrita atômica, WAL mode, grace period, healthcheck Docker | Sem circuit breaker, erro silencioso em load |
| **Segurança** | HMAC comparison, SSL/TLS, MASTER-only, SECURITY.md | Auth bypass default, device_id sem crypto |
| **Manutenibilidade** | Strategy Pattern, Repository Pattern, ABC, type hints, structlog | CI vazio, cobertura testes 40%, sem migrations |
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

1. **Segurança (6.0/10)** — Sanitizar erros, ativar auth em produção, assinar device_id
2. **Manutenibilidade (7.0/10)** — CI/CD automatizado, expandir testes, Alembic migrations
3. **Compatibilidade (7.0/10)** — REST API, documentação AsyncAPI
4. **Usabilidade (7.0/10)** — Corrigir versão no banner, documentar protocolo WS

### Conformidade ISO/IEC 25010

O software atende ao nível **"Adequado"** (7.5/10) da norma ISO/IEC 25010, com 4 de 8 características no nível "Bom" (≥ 8.0) e nenhuma no nível "Crítico" (< 6.0). Para atingir o nível "Bom" global (≥ 8.0), as ações prioritárias são: reforço de segurança, automação de testes e CI/CD, e expansão da interoperabilidade.

---

> **Documento gerado em:** 19/03/2026  
> **Analista:** Auditoria automatizada pós-implantação  
> **Norma:** ISO/IEC 25010:2011 — Systems and Software Quality Requirements and Evaluation (SQuaRE)  
> **Software:** Roleta Cloud v3.5.0 | 5.193 LOC | 37 arquivos Python  
> **Próxima revisão recomendada:** Após implementação das TASK-001→020 (execuções de 19/03)

# 📐 Roleta Cloud — Arquitetura & Conformidade ISO/IEC 25010

> **Versão do Software:** 4.4.0  
> **Data da Análise:** 02/04/2026 · **Atualizado:** 12/06/2026 (ver ADENDO)  
> **Base:** Auditoria pós-implantação M15-ADA (M02-PctSigmoid) + ciclo 24/05→12/06  
> **Norma de Referência:** ISO/IEC 25010:2011 — Modelo de Qualidade de Produto de Software  
> **Total de Linhas de Código:** ~119 arquivos Python ativos · 48 arquivos de teste (374 testes)

---

## ADENDO 12/06/2026 — Estado de conformidade após o ciclo 24/05→12/06

> As PARTES I–VI abaixo retratam a v4.3.2 (02/04) e permanecem como baseline
> histórica. Este adendo registra o delta real verificado em 12/06 — muito do
> que constava como gap foi resolvido nos ciclos 24/05–27/05 (PG stack, CI,
> observabilidade) e 10/06–12/06 (lucro/regiões/INV-3).

### A. Gaps de 02/04 RESOLVIDOS (verificados no código em 12/06)

| Item (02/04) | Resolução | Evidência |
|---|---|---|
| CI vazio (MEL-ISO-002, 7.5) | ✅ `ci.yml` matrix 3.11/3.12/3.13 + PG service + alembic + coverage gate 50% + 3 linters; **verde em main desde 12/06** | `.github/workflows/ci.yml`; run 27434340714 |
| Sem migrations (MEL-ISO-003, 7.4) | ✅ Alembic 0001..0008 (PG) + auto-migrations SQLite; deploy roda `alembic upgrade head` com rollback | `migrations/versions/`; `scripts/roleta-deploy-pull.sh` |
| Sem circuit breaker (MEL-ISO-004) | ✅ `_SQLiteCircuitBreaker` (CLOSED/OPEN/HALF_OPEN) | `database/sqlite_repo.py:22-90` |
| `str(e)` vazava ao cliente (BUG-POST-004 / MEL-ISO-001) | ✅ ISO-S2: cliente recebe mensagem opaca + trace_id; detalhe só server-side | `server/message_handler.py:159-171`; `tests/test_error_output_sanitize.py` |
| `GameState.load()` silencioso (BUG-POST-007 / MEL-ISO-010) | ✅ Loga erro + salva `state.json.corrupted` antes do fallback | `state/game.py:1220-1229` |
| Colunas "mortas" calibration_* (BUG-POST-006) | ✅ Reclassificado: `calibration_error` agora É o wheel_dist por decisão (W-02/B-08, fill-rate monitorado NEW-12) | `server/message_handler.py`; gauge `roleta_calibration_fill_rate_1h` |
| Cobertura/testes "5 arquivos, ~105 testes" (7.3/7.5) | ✅ 48 arquivos, **374 passed** (integração real do handler incluída) | `pytest -q` 12/06 |
| Schema DDL manual (7.4) | ✅ + guarda de drift: snapshot vivo × manifest SQLite↔PG falha o CI se divergir (SP-04) | `tests/test_schema_parity.py`; `database/schema_parity_manifest.json` |
| Observabilidade só logs/trace | ✅ Prometheus (40+ métricas custom), Alertmanager (12+ regras), Grafana local+Cloud, gap-check textfile | `server/health_server.py`; `obs/alerts.yml` |

### B. Capacidades NOVAS com impacto ISO (não existiam em 02/04)

| Capacidade | Característica ISO | Evidência |
|---|---|---|
| PG stack espelho (cw/ccw/shared) via outbox→CDC, dual-write defensivo | Confiabilidade / Compatibilidade | `database/outbox_*`, `workers/cdc_worker.py` |
| PROFIT-LEDGER: `pnl_units`/decisão + `sessions.total_profit` + gauges P&L | Adequação Funcional (KPI=EV) | `database/sqlite_repo.py::update_result`; `roleta_session_pnl_units` |
| INV-3 global: indicação sempre; vetos modulam stake (CUT v1, stop-loss) | Adequação Funcional / Usabilidade | `server/message_handler.py` (gates 12/06); P11 |
| Reset TOTAL da estratégia no botão de dealer (`reset_adaptive`) | Adequação Funcional (P10) | `strategies/sda17.py::reset_adaptive` |
| Medição por região: `result_region` + `dist_c1/c2/c3` + `region_err_ema` (gauge) | Analisabilidade | `state/game.py::_attribute_hit_region`; `roleta_region_err_ema` |
| Feedback adaptativo consome a APOSTA REAL (coverage/centers do pending) | Confiabilidade (anti classe BUG-B) | `strategies/sda17.py::update_adaptive` |
| Lints de regressão: silent-except baseline, DNA coverage, schema symmetry | Manutenibilidade | `tools/lint_*.py`; `scripts/schema_symmetry.py` |
| Pipeline deploy pull-based c/ alembic+healthcheck+rollback; backup diário SQLite + wal-g 30min (ressuscitado 12/06) | Confiabilidade / Portabilidade | `scripts/roleta-deploy-pull.sh`, `scripts/backup-decisions.sh` |
| DNA por decisão (features+realized lift) p/ análise contrafactual | Analisabilidade | `database/dna_logger.py`; `decision_dna` |

### C. Scorecard revisado (12/06)

| # | Característica | 02/04 | 12/06 | Justificativa |
|:-:|---|:---:|:---:|---|
| 1 | Adequação Funcional | 9.0 | **9.2** | INV-3/P11, reset P10, ledger de P&L real |
| 2 | Eficiência | 8.7 | **8.7** | inalterado (375ms/spin medido em prod) |
| 3 | Compatibilidade | 7.0 | **7.5** | PG espelho + APIs HTTP de introspecção (`/api/strategy`, `/metrics`); falta REST de comando/AsyncAPI |
| 4 | Usabilidade | 8.2 | **8.2** | inalterado |
| 5 | Confiabilidade | 8.5 | **8.8** | circuit breaker, outbox, backups testados, deploy c/ rollback |
| 6 | Segurança | 6.5 | **6.5*** | *fora de escopo por diretriz do owner (10/06); achados preservados em `server_snapshot/08_seguranca.md` |
| 7 | Manutenibilidade | 8.0 | **8.6** | CI verde, migrations, parity guard, 374 testes, lints de regressão |
| 8 | Portabilidade | 8.2 | **8.4** | deploy automatizado + restore path documentado |

**Nota geral: 8.0 → 8.5/10.** (Segurança congelada por decisão de produto, não por incapacidade.)

### D. Gaps REAIS remanescentes (manutenibilidade — ordenados por impacto)

1. **`server/message_handler.py` ~1000 LOC** — `handle_new_result` concentra
   pipeline inteiro (decisão+gates+stake+persistência+overlay). Mitigado por
   testes de integração (12/06), mas a extração de um `DecisionPipeline` puro
   continua sendo a maior dívida de modificabilidade. *(herda o 7.1/7.4)*
2. **Coverage gate em 50%** — ramp planejado 50→75 (SP-34.1) ainda não executado;
   `server/` segue como área de menor cobertura unitária.
3. **AGE instalado sem uso** — schemas de grafo vazios; decisão tomada (remover e
   voltar a `pgvector/pgvector:pg15` oficial) pendente de execução. Imagem 1GB.
4. **`models/spin_autoencoder.joblib` untracked no servidor** — hazard de `git clean`
   (mover a volume + `.gitignore`).
5. **Restore drill não executado** — backups existem (SQLite diário + wal-g 30min)
   mas o restore nunca foi ensaiado ponta-a-ponta (`walg-restore-drill.sh` pronto).
6. **AsyncAPI/REST de comando** — protocolo WS segue sem spec formal (7.0→7.5 só
   pela introspecção HTTP).
7. **DeprecationWarnings** — `datetime.utcnow()` (139 avisos na suite) e
   `websockets.legacy`; baratos de sanar, zero risco funcional.

> Rastreabilidade completa do ciclo: `proximos_passos_10_06.md` (premissas P1–P12,
> trilhas A/B/C, auditorias 12/06 r1/r2) e `analise_regioes_12_06.md` (A1–A3).

---

## PARTE I — ARQUITETURA COMPLETA DO SOFTWARE

---

### 1. Visão Geral

O **Roleta Cloud** é um backend em tempo real para processamento de dados de roleta europeia. Recebe resultados (spins) via WebSocket a partir de uma extensão Chrome, aplica análise estatística com a estratégia proprietária M15-ADA (Adaptive Dual Algorithm — 17 números), e retorna sugestões de aposta para um overlay no navegador.

```
┌─────────────────────┐         WebSocket (ws/wss)        ┌─────────────────────┐
│   Extensão Chrome   │ ◄──────────────────────────────── │   Roleta Cloud      │
│   (content.js)      │ ────────────────────────────────► │   (Python 3.12)     │
│                     │   spins, histórico, comandos      │                     │
│   • Extrator DOM    │   ◄── sugestões, state_sync       │   • WebSocket Server│
│   • Overlay UI      │                                   │   • Game Engine     │
│   • Popup Dashboard │                                   │   • M15-ADA Strategy│
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
├── VERSION                          # Versão semântica (4.3.0)
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
│   └── sda17.py                     # M15-ADA (IQR + Weighted Median + Drift + M02-PctSigmoid Triple Focus)
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
│   ├── test_sda17.py                # Testes M15-ADA (56 LOC)
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
           │  • M02 Sigmoid  │  │  ├── timeline.py (deque)     │
           │  • 17 números   │  │  └── bet_advisor.py          │
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
                                     ├── update(hit, global_hit=hit)
                                     ├── sync_global() → martingale oposto
                                     ├── Anti-Martingale: HIT escala, MISS→G1
                                     └── track_gale_window() → DB

5.                                   process_spin(numero, direcao)
                                     ├── Calcula força (distância circular)
                                     ├── Adiciona à timeline CW ou CCW
                                     └── game_state.save() (atômico)

6.                                   M15-ADA analyze(target_timeline)
                                     ├── IQR outlier rejection
                                     ├── Weighted median (decay=0.8)
                                     ├── Drift detection
                                     ├── Smart Score (1-6)
                                     ├── M02-PctSigmoid offset C2/C3
                                     └── Triple Focus (17 números)

7.                                   Kill Switch Advisor
                                     ├── C4/M6/L12 rates
                                     ├── KILL se C4=0% + SDA≤2
                                     └── APOSTAR em todos outros casos

8.                                   Decision final
                                     ├── APOSTAR: get_gale(score, c4_rate, confidence)
                                     │   Regra 6: "alta"→G1, "baixa"→G1, "media"→escalável
                                     │   action_reason = "SDA score=X | GY SZ GSW | C4=XX%"
                                     ├── FALLBACK: SDA insuficiente + dados → G1 seguro
                                     ├── PULAR: TR vetou ou SDA sem dados
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

### 6. Sistema de Decisão (Pipeline M15-ADA v4.3 + Kill Switch)

```
                       Forças da Timeline (últimas 7, mín 2)
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
                              │ predicted_force (ajustada) → C1
                    ┌─────────▼──────────┐
                    │  M02-PctSigmoid    │  Offsets adaptativos C2/C3:
                    │  Offset Controller │  sigmoid(error%) × 2.0 por direção
                    │  (v4.3+)           │  Hit: tighten 8% → center=10
                    │                    │  Miss: expand na dir do erro ±cross 30%
                    │                    │  Clamp: [7, 13] | Independente CW/CCW
                    └─────────┬──────────┘
                              │ C1 + off_c2/off_c3
                    ┌─────────▼──────────┐
                    │  Triple Focus      │  C1: centro (raio 3 = 7 nums)
                    │  17 números        │  C2: CW de C1 (raio 2 = 5 nums)
                    │  (45.9% cobertura) │  C3: CCW de C1 (raio 2 = 5 nums)
                    └─────────┬──────────┘
                              │ {should_bet, center, numbers[17], score}
                    ┌─────────▼──────────┐
                    │  Smart Score        │  score = survival × 3 + tightness × 3 + stable_bonus
                    │  (1-6)              │  tightness = 1 - spread/15
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Kill Switch (TR)   │  VETA se: C4 == 0% AND sda_score ≤ 2
                    │  Advisor v2         │  APROVA em todos os outros casos
                    └─────────┬──────────┘
                              │ {acao: APOSTAR | PULAR}
                    ┌─────────▼──────────┐
                    │  Martingale State   │  SmartGale v5: Anti-Martingale
                    │  Streak Global Cross│  G1(R$21) → G2(R$42) → G3(R$63)
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
    total_stops INTEGER DEFAULT 0,   -- DEPRECATED (Smart Gale v5 não para)
    total_resets INTEGER DEFAULT 0   -- Smart Gale v5: resets a G1 após miss
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
    ├─ SmartGaleV5.update(hit, global_hit) → Atualiza gale + streak global
    ├─ SmartGaleV5.sync_global(hit)    → Sincroniza martingale oposto
    ├─ db_service.track_gale_window()  → Grava em gale_windows + window_plays
    ├─ GameState.process_spin()        → Atualiza timeline + forças
    ├─ GameState.save()                → Grava state.json (bind mount)
    ├─ sda17.analyze()                 → M15-ADA Triple Focus 17 nums → predição
    ├─ sda17.update_adaptive()         → M02-PctSigmoid offset feedback
    ├─ bet_advisor.analyze()           → Kill Switch Advisor → c4_rate
    ├─ SmartGaleV5.get_gale(score,c4)  → Nível de aposta (1×/2×/3×)
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

A norma **ISO/IEC 25010:2011** define 8 características de qualidade de produto de software, cada uma com sub-características. A seguir, cada uma é avaliada contra o estado atual do Roleta Cloud v4.3.1.

---

### 1. ADEQUAÇÃO FUNCIONAL (Functional Suitability)

> *O produto fornece funções que atendem às necessidades declaradas e implícitas quando usado nas condições especificadas.*

#### 1.1 Completude Funcional

| Requisito | Status | Evidência |
|-----------|:------:|-----------|
| Receber spins em tempo real | ✅ Completo | `message_handler.handle_new_result()` — validação Pydantic (0-36) |
| Calcular predições (M15-ADA) | ✅ Completo | Pipeline IQR → Weighted Median → Drift → Score → M02-PctSigmoid → Triple Focus (17 números, offsets adaptativos por direção) |
| Gerenciar Martingale | ✅ Completo | SmartGale v5: Anti-Martingale com streak global cross-direction, take-profit G3, c4 threshold 0.15, fallback G1 |
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
| Migração de versão | ✅ | v1.3→v1.4→v1.5→v1.6 com fallback automático, sigmoid_off backward compat v4.2→v4.3 |
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
| JSON corrompido no DB | Fallback para default via _safe_json_loads() | Nenhum (v4.3.1) |
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
| M15-ADA → Outra estratégia | ✅ | `StrategyBase` (ABC) |
| WebSocket → REST | ⚠️ | Requer refatoração do message_handler |
| structlog → outro logger | ✅ | Wrapper do stdlib `logging` |

**Avaliação: 8/10** — Boa portabilidade graças ao Docker e abstrações de repositório.

---

## PARTE III — SCORECARD CONSOLIDADO ISO/IEC 25010

| # | Característica | Sub-características Avaliadas | Nota | Nível |
|:-:|---------------|-------------------------------|:----:|:-----:|
| 1 | **Adequação Funcional** | Completude, Correção, Pertinência | **9.0** | 🟢 |
| 2 | **Eficiência de Desempenho** | Tempo, Recursos, Capacidade | **8.7** | 🟢 |
| 3 | **Compatibilidade** | Coexistência, Interoperabilidade | **7.0** | 🟡 |
| 4 | **Usabilidade** | Reconhecibilidade, Aprendizado, Proteção | **8.2** | 🟢 |
| 5 | **Confiabilidade** | Maturidade, Disponibilidade, Tolerância, Recuperação | **8.5** | 🟢 |
| 6 | **Segurança** | Confidencialidade, Integridade, Não-repúdio, Autenticidade | **6.5** | 🟡 |
| 7 | **Manutenibilidade** | Modularidade, Reusabilidade, Analisabilidade, Modificabilidade, Testabilidade | **8.0** | 🟢 |
| 8 | **Portabilidade** | Adaptabilidade, Instalabilidade, Substituibilidade | **8.2** | 🟢 |

**Nota Geral Ponderada: 8.0 / 10** *(+0.1 após M15-ADA + correções 29/03)*

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
| BUG-POST-004 | `server/message_handler.py` | ~~🟡 Média~~ ✅ CORRIGIDO | `str(e)` em `ErrorOutput` vazava info interna — ISO-S2: mensagem opaca + trace_id (`test_error_output_sanitize.py`) | 159-171 |
| BUG-POST-005 | `server/connection_manager.py` | ~~🟡 Média~~ ✅ CORRIGIDO | Grace period task agora é criada DENTRO do `async with master_lock` | 154 |
| BUG-POST-006 | `database/sqlite_repo.py` | ~~🔵 Baixa~~ ✅ RECLASSIFICADO | `calibration_error` deixou de ser morta: é o wheel_dist por decisão (W-02/B-08 26/05), com fill-rate monitorado (NEW-12) | — |
| BUG-POST-007 | `state/game.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | `GameState.load()` agora loga o erro e preserva `state.json.corrupted` antes do fallback | 1220-1229 |
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
| BUG-E3-001 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `get_gale()` sem parâmetro `confidence` — escalação ignorava qualidade do sinal (28/03 TASK-E3) | 54 |
| BUG-E3-002 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Pipeline não passava `confidence` para get_gale() — SmartGale cego à qualidade (28/03 TASK-E3) | 236 |
| BUG-E3-003 | `core/engine.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Engine não passava `confidence` para get_gale() — mesma omissão do pipeline (28/03 TASK-E3) | 105 |
| BUG-E2-001 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Score 3 limitado a G1 com 58.1% HR — regra de teto por score penalizava melhores momentos (28/03 TASK-E2) | 57-62 |
| BUG-E2-002 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Score 5-6 liberava G3 com ~40% HR — escalação destrutiva baseada em score instável (28/03 TASK-E2) | 61-62 |
| BUG-MAIN-001 | `main.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | SIGTERM não tratado no Windows — try/except no signal handler (29/03 M15-ADA) | 63-68 |
| BUG-MAIN-002 | `main.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Double shutdown — flag `_shutdown_called` implementada (29/03 M15-ADA) | 32 |
| BUG-MAIN-004 | `main.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `game_state.save()` sem try/except no handler (29/03 M15-ADA) | 43 |
| BUG-ADA-001 | `strategies/sda17.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | `self._wheel` não inicializado em `__init__()` — crash na primeira predição CCW após restart (29/03 P0) | 46-54, 285 |
| BUG-ADA-002 | `strategies/sda17.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | Validação frágil em `load_adaptive_state()` — dados corrompidos causavam ValueError (29/03 P0) | 322-326 |
| BUG-ADA-003 | `state/game.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | `_adaptive_state` dinâmico no dataclass — hasattr() frágil, declarado como field (29/03 P1) | 147, 481 |
| BUG-ADA-004 | `server/websocket.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | Restauração adaptativa sem error handling — try/except adicionado (29/03 P1) | 32-33 |
| BUG-FE-001 | `extension/content.js` | ~~🔴 Crítico~~ ✅ CORRIGIDO | handleStateSync usava textContent sem eb-c1 — heartbeat destruía gold C1 a cada 1s (29/03 v4.0.2) | 805-812 |
| BUG-FE-002 | `extension/overlay.css` | ~~🟠 Alto~~ ✅ CORRIGIDO | .eb-region .eb-c1 com color:#000 invisível em fundo verde — alterado para #fff (29/03 v4.0.2) | 945-950 |
| BUG-FE-003 | `extension/content.js` | ~~🟡 Médio~~ ✅ CORRIGIDO | centroDisplay duplicado em 4 locais (DRY violation) — buildCentroHTML() helper (29/03 v4.0.2) | 16-23 |
| BUG-V42-001 | `strategies/sda17.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | Offset Bayesiano drift para extremos (17/7) sem guardrails — anti-drift com symmetry cap (30/03 v4.2.0) | 310-368 |
| BUG-AUDIT-002 | `server/message_handler.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | Race condition: pending_prediction lida FORA do state_lock — movida para dentro (31/03 v4.3.1) | 147-152 |
| BUG-AUDIT-004 | `database/sqlite_repo.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | json.loads() sem try-except crasheia se JSON corrompido no DB — _safe_json_loads() helper (31/03 v4.3.1) | 354-364 |
| BUG-AUDIT-005 | `strategies/base.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | get_neighbors() ZeroDivisionError se wheel_sequence vazia — guard adicionada (31/03 v4.3.1) | 51-54 |
| BUG-AUDIT-006 | `server/message_handler.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | Direction vazia/inválida atualizava Martingale CCW erroneamente — validação com elif (31/03 v4.3.1) | 162-167 |
| BUG-AUDIT-007 | `strategies/sda17.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | min_dist sem clamp em _pct_sigmoid_update — adicionado min(min_dist, 18) (31/03 v4.3.1) | 450-452 |
| BUG-AUDIT-008 | `strategies/sda17.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | _predict_robust sem guard para forces=[] — early return defensivo (31/03 v4.3.1) | 230-233 |

### Melhorias Recomendadas Pós-Implantação

| ID | Característica ISO | Melhoria | Impacto |
|----|-------------------|----------|---------|
| MEL-ISO-001 | Segurança | ~~Sanitizar mensagens de erro~~ ✅ CORRIGIDO — ISO-S2 (mensagem opaca + trace_id) | ✅ Feito |
| MEL-ISO-002 | Manutenibilidade | ~~Implementar CI/CD com pytest automatizado~~ ✅ CORRIGIDO — `ci.yml` matrix 3.11-13 + PG + alembic + lints; verde 12/06 | ✅ Feito |
| MEL-ISO-003 | Manutenibilidade | ~~Adicionar Alembic migrations~~ ✅ CORRIGIDO — 0001..0008 (PG) + auto-migrations SQLite + alembic no deploy | ✅ Feito |
| MEL-ISO-004 | Confiabilidade | ~~Circuit breaker no acesso ao SQLite~~ ✅ CORRIGIDO — `_SQLiteCircuitBreaker` | ✅ Feito |
| MEL-ISO-005 | Compatibilidade | Expor REST API HTTP (além de WebSocket) para integração com ferramentas externas | 🟢 Baixo |
| MEL-ISO-006 | Usabilidade | Documentação AsyncAPI para protocolo WebSocket | 🟢 Baixo |
| MEL-ISO-007 | Eficiência | ~~Connection pooling para SQLite~~ ✅ CORRIGIDO — Conexões agora com `try/finally: conn.close()` | ✅ Feito |
| MEL-ISO-008 | Segurança | Assinatura criptográfica de `device_id` para prevenir spoofing | 🟡 Médio |
| MEL-ISO-009 | Manutenibilidade | ~~Ler versão de `VERSION` file em vez de hardcoded no banner~~ ✅ CORRIGIDO | ✅ Feito |
| MEL-ISO-010 | Confiabilidade | ~~Logging do motivo quando `GameState.load()` falha~~ ✅ CORRIGIDO — log + backup `.corrupted` | ✅ Feito |
| MEL-ISO-011 | Eficiência | ~~N+1 query em `get_gale_window_history()`~~ ✅ CORRIGIDO — Batch IN() query (28/03 TASK-02) | ✅ Feito |
| MEL-ISO-012 | Eficiência | ~~I/O síncrono no event loop async~~ ✅ CORRIGIDO — `asyncio.to_thread()` em ExtractorService + heartbeat (28/03 TASK-03) | ✅ Feito |
| MEL-ISO-013 | Manutenibilidade | ~~`_VALID_DIRECTIONS` local em `process_spin()`~~ ✅ CORRIGIDO — Movido para `ClassVar` (28/03 TASK-04) | ✅ Feito |
| MEL-MG-001 | Eficiência | ~~SmartGale v4 travado em G1~~ ✅ CORRIGIDO — Anti-Martingale com streak global cross-direction (SmartGale v5) | ✅ Feito |
| MEL-MG-002 | Eficiência | ~~Sem take-profit em G3~~ ✅ CORRIGIDO — G3+HIT reseta G1, preserva lucro (SmartGale v5) | ✅ Feito |
| MEL-MG-003 | Confiabilidade | ~~global_hit não sincronizado~~ ✅ CORRIGIDO — sync_global() sincroniza ambos martingales em engine.py | ✅ Feito |
| MEL-PL-001 | Confiabilidade | ~~Pipeline produção sem SmartGale~~ ✅ CORRIGIDO — message_handler.py agora chama get_gale(), sync_global(), get_bet_c4_rate() (28/03 plano_tarefas_sessao13) | ✅ Feito |
| MEL-PL-002 | Adequação Funcional | ~~Sem fallback early-session em produção~~ ✅ CORRIGIDO — Fallback G1 seguro com 21 vizinhos quando SDA insuficiente (28/03 TASK-02) | ✅ Feito |
| MEL-PL-003 | Testabilidade | ~~Sem testes de integração para pipeline produção~~ ✅ CORRIGIDO — 15 testes em test_message_handler_gale.py (28/03 TASK-03) | ✅ Feito |
| MEL-E3-001 | Adequação Funcional | ~~Gale cego à confiança~~ ✅ CORRIGIDO — get_gale() recebe confidence: "alta"→G1 (spike), "baixa"→G1, "media"→escalável (SmartGale v6) | ✅ Feito |
| MEL-E2-001 | Adequação Funcional | ~~Score limitava gale (não-preditivo)~~ ✅ CORRIGIDO — Regra de teto por score REMOVIDA; gale agora decidido por confiança+c4+streak (SmartGale v6) | ✅ Feito |
| MEL-E4-001 | Analisabilidade | ~~Distância ao centro não logada~~ ✅ CORRIGIDO — Log de distância resultado→centro predito em cada spin com resultado (28/03 TASK-E4) | ✅ Feito |
| MEL-ADA-001 | Adequação Funcional | ~~Migrar SDA-21→M15-ADA (17 nums, offset adaptativo CW ErrDriven + CCW Bayesian)~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-002 | Confiabilidade | ~~Inicializar self._wheel em __init__ + fallback em _bayesian_offset~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-003 | Confiabilidade | ~~Error handling na restauração adaptativa (websocket.py)~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-004 | Manutenibilidade | ~~_adaptive_state como campo dataclass em GameState~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-005 | Usabilidade | ~~Destaque bold+cor C1 no overlay e dashboard para identificação rápida~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-006 | Manutenibilidade | ~~buildCentroHTML() helper DRY — 3 locais de renderização C1 unificados~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-007 | Usabilidade | ~~Fix heartbeat sobrescrevendo C1 gold (textContent→innerHTML) + CSS contraste região~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-V42-001 | Adequação Funcional | ~~Migrar CW para Bayesiano assimétrico (unificar algoritmo CW/CCW)~~ ✅ CORRIGIDO — M04 Error-Vector com prior Gaussiano (30/03 v4.2.0) | ✅ Feito |
| MEL-V42-002 | Confiabilidade | ~~Anti-drift guardrails para offset Bayesiano~~ ✅ CORRIGIDO — Symmetry cap + limites [7,13] (30/03 v4.2.0) | ✅ Feito |
| MEL-V43-001 | Adequação Funcional | ~~Substituir Bayesian brute-force por M02-PctSigmoid~~ ✅ CORRIGIDO — Sigmoid dampened error feedback O(1) (30/03 v4.3.0) | ✅ Feito |
| MEL-V43-002 | Eficiência | ~~Warmup 5→2 jogadas para ativar Triple Focus~~ ✅ CORRIGIDO — min_forces=2, window=[7,5,3,2] (30/03 v4.3.0) | ✅ Feito |
| MEL-V43-003 | Adequação Funcional | ~~BAYESIAN_DEFAULT 12→10 (centro ótimo confirmado por oracle analysis)~~ ✅ CORRIGIDO (30/03 v4.3.0) | ✅ Feito |
| MEL-V43-004 | Confiabilidade | ~~Race condition no pending + json defensivo + guards defensivos~~ ✅ CORRIGIDO — 6 bugs audit fixes (31/03 v4.3.1) | ✅ Feito |

---

## PARTE V — MAPA DE CONFORMIDADE ISO/IEC 25010

### Matriz Característica × Evidência

| Característica ISO | Artefatos de Evidência | Gaps Identificados |
|-------------------|----------------------|-------------------|
| **Adequação Funcional** | Pipeline M15-ADA v4.3 (M02-PctSigmoid Triple Focus 17 nums, offsets adaptativos por direção), Kill Switch, SmartGale v6, DB logging, Analytics handler, Fallback early-session | Colunas mortas no schema |
| **Eficiência** | TraceContext (latência), deque com maxlen, MAX_CONNECTIONS, SQLite conn try/finally, SmartGale v6 confiança+streak+c4 | ✅ Conexões SQLite corrigidas; ✅ N+1 batch query; ✅ asyncio.to_thread(); ✅ Anti-Martingale com take-profit; ✅ Score removido de gale |
| **Compatibilidade** | Docker, ENV vars, JSON protocol | Sem REST API, sem AsyncAPI spec |
| **Usabilidade** | Pydantic models com exemplos, emojis em logs, overlay Chrome, banner dinâmico | ✅ Banner corrigido; ✅ C1 gold destaque fix v4.0.2; falta docs API (AsyncAPI) |
| **Confiabilidade** | Escrita atômica, WAL mode, grace period, healthcheck Docker, M02 backward compat, _safe_json_loads | ✅ Grace period CASO 2 corrigido; ✅ Race condition fix v4.3.1; sem circuit breaker |
| **Segurança** | HMAC comparison, SSL/TLS, MASTER-only, SECURITY.md, porta 8765 restrita a localhost | Auth bypass default, device_id sem crypto |
| **Manutenibilidade** | Strategy Pattern, Repository Pattern (ABC com 16 métodos), type hints, structlog, 105 testes (23 integração pipeline+gale), _adaptive_state como campo dataclass, buildCentroHTML() DRY helper, M02-PctSigmoid auto-adaptativo | CI vazio, cobertura testes ~60%, sem migrations; ✅ ClassVar _VALID_DIRECTIONS |
| **Portabilidade** | Docker, SQLite portátil, ENV config, setup script | WebSocket-only (sem REST fallback) |

---

## PARTE VI — CONCLUSÃO E RECOMENDAÇÕES

O **Roleta Cloud v4.3.1** apresenta uma arquitetura madura com bons padrões de design (Strategy, Repository, Singleton, Observer via broadcast). A separação entre lógica pura (`core/`, `strategies/`, `state/`) e infraestrutura (`server/`, `database/`) é clara e bem executada.

### Pontos Fortes

1. **Pipeline de decisão testável** — `GameEngine` é puro, sem I/O
2. **Extensibilidade** — novas estratégias via `StrategyBase`, novos bancos via `DecisionRepository`
3. **Observabilidade** — `TraceContext` + structlog + 27 campos por decisão no DB
4. **Resiliência** — escrita atômica, WAL mode, grace period, migração de versão automática
5. **Eficiência** — pipeline sub-50ms, O(n) com n ≤ 7
6. **Algoritmo adaptativo M02-PctSigmoid** — offset dinâmico sigmoid-dampened independente por direção (CW/CCW), 17 números, warmup de apenas 2 jogadas
7. **Usabilidade operacional** — destaque visual do C1 (bold+dourado) para identificação rápida pelo operador
8. **Robustez defensiva** — guards contra race conditions, JSON corrompido, wheel vazia, forces vazia (v4.3.1)

### Áreas Prioritárias de Melhoria (Ordenadas por Impacto)

1. **Segurança (6.5/10)** — Sanitizar erros, ativar auth em produção, assinar device_id
2. **Compatibilidade (7.0/10)** — REST API, documentação AsyncAPI
3. **Usabilidade (8.5/10)** — ~~Corrigir versão no banner~~ ✅ Feito; ~~destaque C1~~ ✅ Feito; ~~fix heartbeat/CSS C1~~ ✅ Feito v4.0.2; ~~fix encoding frontend~~ ✅ Feito v4.3.2; ~~fix DOM morto~~ ✅ Feito v4.3.2; documentar protocolo WS

### Conformidade ISO/IEC 25010

O software atende ao nível **"Bom"** (8.2/10) da norma ISO/IEC 25010, com 6 de 8 características no nível "Bom" (≥ 8.0) e nenhuma no nível "Crítico" (< 6.0). v4.3.2 elevou Usabilidade de 8.3 para 8.5 com correção de encoding frontend e eliminação de código morto. Para evoluir, as ações prioritárias são: reforço de segurança e expansão da interoperabilidade (REST API, AsyncAPI).

---

> **Documento gerado em:** 19/03/2026 | **Atualizado em:** 12/06/2026 (ADENDO no topo: ciclo 24/05→12/06, scorecard revisado 8.5/10, gaps remanescentes)  
> **Analista:** Auditoria automatizada pós-implantação  
> **Norma:** ISO/IEC 25010:2011 — Systems and Software Quality Requirements and Evaluation (SQuaRE)  
> **Software:** Roleta Cloud v4.4.0 | 119 arquivos Python ativos | 48 arquivos de teste (374 testes)  
> **Correções aplicadas:** 22 bugs em 20/03 + 12 bugs em 27/03 + 4 tasks Jules em 28/03 + SmartGale v5 em 28/03 + Pipeline fix 7 bugs em 28/03 + SmartGale v6 5 bugs em 28/03 + M15-ADA 4 bugs + C1 bold em 29/03 + BUG-FE 3 bugs em 29/03 v4.0.2 + M04 Error-Vector v4.2 em 30/03 + M02-PctSigmoid v4.3.0 em 30/03 + 6 bug fixes audit v4.3.1 em 31/03 + 10 bugs frontend v4.3.2 em 02/04 + **ciclo v4.4.0 24/05→12/06 (B-01..B-10, SP-02..35 parciais, QW-1..7, S-STRAT-1..14, auditorias 12/06 r1: 3 bugs INV-3/ledger/fallback + r2: 3 bugs feedback/center-0/stop-loss-lag)**

### Changelog de Versões

| Versão | Data | Principais Mudanças |
|--------|------|---------------------|
| v4.0.2 | 29/03/2026 | M15-ADA inicial, fix C1 gold heartbeat, CSS contraste, DRY helper |
| v4.1.0 | 29/03/2026 | Offset adaptativo CW (ErrDriven EMA) + CCW (Bayesian brute-force) |
| v4.2.0 | 30/03/2026 | M04 Error-Vector com prior Gaussiano, anti-drift guardrails, algoritmo unificado CW/CCW |
| v4.3.0 | 30/03/2026 | M02-PctSigmoid (vencedor simulação 15 modelos), warmup 5→2, DEFAULT 12→10 |
| v4.3.1 | 31/03/2026 | 6 bug fixes defensivos: race condition, json safe, wheel guard, direction validation, min_dist clamp, empty forces guard |
| v4.3.2 | 02/04/2026 | **Auditoria frontend:** fix encoding UTF-8 (22 emojis + 7 acentos), dead code cleanup (4 refs DOM null), Martingale instant trace, cache busting, CSS responsive, Dockerfile label, null guards |
| v4.4.0 | 24/05→12/06/2026 | **Ciclo PG+obs+lucro** (ver ADENDO 12/06): PG espelho outbox→CDC, Prometheus/Grafana/alertas, CI matrix verde, alembic no deploy, Quick Wins QW-1..7, S-STRAT-7..14 (batch tune, shadow grid, bandit), DNA logger, DEAL capture, PROFIT-LEDGER, CUT-POLICY v1 + stop-loss sob INV-3 global, reset total no botão de dealer (P10), medição por região (`result_region`, `dist_c1/c2/c3`, `region_err_ema`), feedback adaptativo pela aposta real, backups SQLite+wal-g ressuscitado. Suite 374 |

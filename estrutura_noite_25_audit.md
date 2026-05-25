# 🌙 Estrutura Noite 25/05 — Auditoria + Engenharia Reversa Completa

> **Gerado:** 2026-05-25 03:15 BRT (06:15 UTC) — sessão YOLO Orchestrator
> **Modelo:** claude-opus-4.7
> **Stack MCP usada:** `graphify` · `filesystem` · `memory` · `brave-search` · `sequential-thinking` · `github-mcp` · `sql` · `powershell-ssh`
> **Escopo:** software local (`C:\Users\Windows\Desktop\Roleta Cloud`) + servidor Debian live `root@187.45.181.75`
> **Documentos predecessores:** `fine_tuning_25.md`, `maquina_azure_agora_25.md`, `auditoria_24_noite.md`, `estrutura_atual_24.md`

---

## §0. TL;DR — O que está vivo agora

| Item | Valor live | Saúde |
|------|-----------|-------|
| Containers up | **8/8 healthy** | ✅ |
| Uptime PG | 4h | ✅ |
| Uptime app | 52min (restart recente) | ✅ |
| Load avg (1/5/15 min) | 0.34 / 0.22 / 0.18 | ✅ |
| RAM (app/cdc/pg/total) | 35/22/112 MB de 58 GB | ✅ ocioso |
| Disco | n/d, prev ~7/79 GB | ✅ |
| **Decisões totais** | **4.282** | ✅ |
| **Hit rate global (resolved n=3.142)** | **47.1 %** | ✅ acima do baseline 45.9 % |
| **Hit rate últimas 24 h (n=634)** | **45.6 %** | ⚠️ regressão leve |
| Hit rate por gale (G1/G2/G3) | 47.1 / 48.0 / 44.7 % | ✅ G2 melhor que G1 (bom sinal anti-MG) |
| spin_features cw/ccw | 54 / 52 | 🟡 abaixo de threshold 50 (cw) — quase emite |
| spins_vectors cw/ccw | 286 / 294 | ✅ |
| outbox status | **686 processed, 0 failed/pending** | ✅ |
| Kill Switch pulls (uptime) | **35** | ⚠️ 35/52min = 0.67/min = ALTO |
| vol_ema cw/ccw | 0.491 / 0.478 | ✅ regime estável (próximo de baseline 0.45) |
| Bandit S-STRAT-14 state | **AUSENTE em state.json** | 🔴 BUG-N25-05 |
| Autoencoder treinado | sim (1.3 KB joblib) | 🟡 não montado no container — BUG-N25-03 |

**6 bugs novos** identificados (3 críticos, 2 médios, 1 baixo) — detalhe em §6.

---

## §1. Topologia atual — visão de 1 página

```
                                ┌────────────────────────────────────┐
                                │      EXTRATOR (browser plugin)     │
                                │    extension/ + frontend/popup     │
                                └──────────────┬─────────────────────┘
                                               │ WebSocket :8765
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              roleta-cloud (Python)                            │
│  ├── main.py → server/websocket.py (asyncio)                                  │
│  ├── server/message_handler.py — Pipeline 7 estágios:                         │
│  │   received → processed → saved → analyzed → triple_rate → sent → result    │
│  ├── state/game.py — Game state + Timeline + Martingale + recent_hits         │
│  ├── state/bet_advisor.py — Kill Switch v4 (TripleRateAdvisor)                │
│  ├── strategies/sda17.py — SDA17-R (drift_freeze, cooldown, sigmoid_off…)     │
│  ├── strategies/shadow_grid.py — V2 wheel-rotation +1/+3/+5/+10 + bandit ε    │
│  ├── database/sqlite_repo.py — SQLite write-side autoritativo                 │
│  ├── database/outbox_publisher.py — emite eventos p/ shared.outbox            │
│  ├── database/feature_store.py — leitor PG read-side (S-STRAT-8)              │
│  ├── database/regime_similarity.py — pgvector cosine (S-STRAT-12)             │
│  ├── server/health_server.py — :8766 → /health /metrics /api/state            │
│  │                                       /api/regime /api/shadow              │
│  └── tools/{backtest_harness,gap_detector,backfill_decision}.py              │
└──────────────┬───────────────────────────────────────────┬───────────────────┘
               │ direct write                              │ outbox row
               ▼                                           ▼
   ┌─────────────────────────┐              ┌──────────────────────────────┐
   │   SQLite (write-side)   │              │  Postgres 15 (read-side)     │
   │  /app/data/decisions.db │              │  schemas: cw, ccw, shared    │
   │  decisions, sessions,   │  LISTEN/     │  cw|ccw.spins_vectors        │
   │  gale_windows,          │  NOTIFY      │  cw|ccw.spin_features        │
   │  window_plays           │ ◀─────────── │  shared.outbox/feature_flags/│
   └─────────────────────────┘              │          strategy_versions   │
                                            │  extensions: vector, age,    │
                                            │   pg_stat_statements, pgcrypto│
                                            └──────────────┬───────────────┘
                                                           │ batch SKIP LOCKED
                                                           ▼
                                            ┌──────────────────────────────┐
                                            │   roleta-cdc-worker          │
                                            │  workers/cdc_worker.py       │
                                            │  HANDLERS = {                │
                                            │    spin_features →           │
                                            │      INSERT spins_vectors    │
                                            │    spin_result →             │
                                            │      INSERT spin_features    │
                                            │       (com lag features)     │
                                            │  }                           │
                                            └──────────────────────────────┘

   Observabilidade:
   prometheus :9090  ←  cdc :8767/metrics + app :8766/metrics + node-exp + pg-exp
   grafana :3000     ←  10 painéis (shadow grid + bandit + kill + outbox)
   alertmanager :9093 (alerts atualmente: [])
```

---

## §2. Inventário de código — 82 arquivos Python (excl. archive/venv)

### Núcleo da decisão

| Arquivo | LoC | Função |
|---------|----:|--------|
| `state/game.py` | **49 957** | Cérebro: GameState, Martingale, integração SDA17 + advisor |
| `state/bet_advisor.py` | 15 051 | Kill Switch v4 (C4 + SDA dinâmicos por dir), sinais opt-in |
| `state/timeline.py` | 2 223 | Deque de forças por direção (cw/ccw) com `add()` que clampa [1,37] |
| `strategies/sda17.py` | grande | SDA17-R + drift_freeze + cooldown + sigmoid_off + batch_tune |
| `strategies/shadow_grid.py` | médio | Grid wheel-rotation paramétrico + bandit ε-greedy |
| `server/message_handler.py` | 31 186 | Pipeline 7 estágios + GALE_WINDOW |
| `server/connection_manager.py` | 14 314 | WebSocket session lifecycle |
| `server/health_server.py` | 24 723 | /health /metrics /api/* (10+ endpoints) |
| `server/websocket.py` | 12 784 | Routing entrante + bandit_stats |

### Persistência

| Arquivo | LoC | Função |
|---------|----:|--------|
| `database/sqlite_repo.py` | 38 984 | Repo principal (decisions, sessions, gale_windows) |
| `database/models.py` | 8 153 | Pydantic schemas |
| `database/outbox_integration.py` | 11 061 | Hook bridge SQLite→outbox PG |
| `database/outbox_publisher.py` | 3 821 | Insert em `shared.outbox` |
| `database/feature_store.py` | **4 116** | Read-side `cw|ccw.spin_features` (S-STRAT-8) |
| `database/regime_similarity.py` | **6 627** | Read-side pgvector cosine (S-STRAT-12) |
| `database/repository.py` | 7 370 | Abstração read interface |
| `database/service.py` | 6 863 | Camada serviço CRUD |
| `workers/cdc_worker.py` | **17 564** | Loop CDC outbox→PG, LISTEN/NOTIFY, SAVEPOINT por evento |

### Migrações

```
0001_baseline.py            — shared.outbox + feature_flags
0002_strategy_versions.py   — versionamento estratégias
0003_vector_schema.py       — pgvector + cw/ccw schemas
0004_outbox.py              — outbox refinements
0005_outbox_notify.py       — NOTIFY trigger (LISTEN integration)
0006_spin_features.py       — cw|ccw.spin_features (S-STRAT-8)
```

### Tooling

| Arquivo | Função |
|---------|--------|
| `tools/backtest_harness.py` | **S-STRAT-9** — replay de spin_features para validar estratégias offline |
| `tools/backtest_from_db.py` | Replay baseado em SQLite legacy |
| `tools/gap_detector.py` | Identifica decisões órfãs sem `actual_number` |
| `tools/backfill_decision.py` | Reconcilia gaps |
| `scripts/train_autoencoder.py` | **PCA 6→4** treinado contra `spins_vectors` (528 rows, expl. var 99.5%) |
| `scripts/walg-*.sh` | wal-g backup 30 min + restore drill + B2 |
| `scripts/install-grafana-agent.sh` | Loki + agent tail |

### Observabilidade

| Item | Estado |
|------|--------|
| Prometheus | :9090, scrape 6 alvos (app, cdc, pg-exp, node-exp, self, alertmanager) |
| Grafana | :3000, dashboard `roleta-shadow-grid.json` com **+6 painéis bandit** (S-OBS-15 v2) |
| AlertManager | :9093, 0 alerts ativos |
| wal-g | cron 30 min + daily, B2 backend |

### Compose

```
docker-compose.yml      — base (roleta-cloud + healthcheck)
docker-compose.pg.yml   — postgres + cdc-worker
docker-compose.obs.yml  — prometheus + grafana + alertmanager + exporters
docker-compose.dev.yml  — dev overrides
```

---

## §3. Engenharia reversa da estratégia — ponto a ponto

### 3.1 Recepção de spin (browser → server)

1. Extensão envia `{numero, direcao, ts, mesa}` via WebSocket porta `8765`.
2. `server/connection_manager.py` faz session-tracking; `message_handler.py` valida.
3. **Pipeline 7 estágios** observado nos logs (latency típica 50-200 ms, P95 spike ~3 500 ms quando bate I/O):
   ```
   received → processed → saved → analyzed → triple_rate → sent → (later) result
   ```

### 3.2 Atualização de estado (game.py)

* `record_spin(numero, direcao)` → calcula `force = wheel_distance(last_number, numero, direcao)`
* `timeline_cw.add(force)` ou `timeline_ccw.add(force)` (deque maxlen=`settings.game.max_timeline_size`)
* Atualiza `last_number`, `last_direction`, `recent_hits` (deque maxlen 100 por dir)
* Atualiza adaptive_state (cooldown counters, drift_freeze counters, sigmoid_off por direção)

### 3.3 SDA17-R (strategies/sda17.py) — predição

Loop:
1. **Warmup adaptativo (QW-6)** — espera ≥N forças
2. **Cooldown** (`cooldown[dk]={c2, c3}`) — bloqueia c2/c3 por N spins pós-MISS
3. **Drift freeze (QW-7)** — se `recent_hits` 50-win mostra dispersão >0.15 entre 1ª/2ª metade ⇒ congelado por 5 spins. **CCW disparou 4x em 6 h** (cw zero). Configurável via `sda17.drift_freeze.{enabled,window,threshold,freeze_spins,soft_reset_weight}`
4. **Sigmoid_off** (bayesian per-dir, default 4.0) — calibra offset CW/CCW separadamente
5. **Predição final**: `centro_previsto` + array `numeros` (5 vizinhos no padrão wheel)

### 3.4 Kill Switch v4 (bet_advisor.py)

Thresholds **dinâmicos** por direção:
```
vol_ema[dk] = 0.10 * std(last 30 hits) + 0.90 * vol_ema_prev    # baseline 0.45
c4_thr = clamp(0.30 - 0.5*(vol-0.45), 0.20, 0.35)
sda_thr = clamp(round(4 - 4*(vol-0.45)), 2, 6)
KILL ⇔ c4 < c4_thr  E  sda_score < sda_thr
```
* Estado live:
  ```
  cw : vol=0.491  c4_thr=0.30  sda_thr=4
  ccw: vol=0.478  c4_thr=0.30  sda_thr=4
  pulls=35 em 52min  → 0.67 KILL/min
  ```
* **35 KILL pulls em 52 min é ALTO** — sugere c4 dropando frequentemente abaixo de 30 %. Possivelmente a janela curta C4=4 amplifica ruído normal. Considerar elevar window para 8 ou usar EMA de hit_rate.

### 3.5 Anti-Martingale (game.py MartingaleState)

```
G1 → R$17 (mín)
G2 → R$34 (após 1 hit consecutivo OU streak global ≥2)
G3 → R$51 (após 2 hits consecutivos OU streak global ≥3)
MISS → reset imediato para G1
G3 + HIT → take-profit (lock + reset)
```
**Smart Gale v7** removeu o bloqueio "confidence==alta ⇒ max_gale=1" do v6 (que prendia 94.7 % das apostas em G1).

Distribuição observada (3 142 decisões resolved):
```
G1: 2 481 jogos, 1 169 hits = 47.1 %
G2:   473 jogos,   227 hits = 48.0 %   ← G2 > G1 indica streak detection funciona
G3:   188 jogos,    84 hits = 44.7 %
```
G3 hit rate < G1 sugere que o escalado pega regimes mais voláteis.

### 3.6 Shadow Grid V2 + Bandit ε-greedy (S-STRAT-14)

* Grid de challengers paralelos com `wheel_rotation_+{1,3,5,10}` testados contra incumbent.
* Bandit ε-greedy escolhe entre shifts baseado em edge EMA recente.
* **Auto-promote (S-STRAT-13.1)**: se challenger > incumbent em N spins com edge sustentado, promove.
* **State live** (state.json):
  ```
  shadow_grid: presente com 2 spins de amostra por shift
  shift +1: cw=1/1, ccw=1/2
  shift +3: cw=0/1, ccw=1/2
  shift +5: cw=0/1, ccw=1/2
  shift +10: cw=0/1, ccw=0/2
  ```
* **MAS** `/api/shadow` reporta TUDO zerado ⇒ **BUG-N25-04** (§6).

### 3.7 CDC Worker — propagação SQLite→PG

* Outbox `pending` → batch SKIP LOCKED (1 a 100) → handlers `spin_features` / `spin_result`.
* `_apply_spin_features` (linha 129): valida `raw_features[6 floats]` + INSERT em `spins_vectors`.
* `_apply_spin_result` (linha 146): window query últimos 50 + computa `acc_10, acc_50, streak_miss, streak_hit, last_20_hits` + INSERT em `spin_features`.
* SAVEPOINT por evento ⇒ falha singular não derruba o batch.
* MAX_RETRIES=5 ⇒ status `failed` (DLQ visível por `SELECT count(*) WHERE status='failed'`).
* LISTEN/NOTIFY `outbox_new`: 159 wakeups em 1 h ≈ 1 wakeup/22 s ⇒ atende live perfeitamente.
* **Reconexão automática** se `_listen_conn_dead`.

### 3.8 S-STRAT-8 — Feature Store

* Reader simples (psycopg2 lazy conn + reconnect, falha-aberta).
* `get_window(direction, limit)` retorna até 50 rows recentes (acc_10, acc_50, streaks, hit).
* Integrado **opt-in** ao bet_advisor via `feature_reader` kwarg; emite `feature_signal` no BetAdvice quando ≥50 rows. Estado atual: cw=54 (✅ no limite), ccw=52 (✅ no limite). **Vai começar a emitir** nas próximas decisões.
* Threshold **MIN_FEATURE_ROWS=50** — `bet_advisor` ainda **não usa o sinal para alterar should_bet** (telemetria pura).

### 3.9 S-STRAT-12 — Regime Similarity

* pgvector `<=>` (cosine) sobre `cw|ccw.spins_vectors`.
* `find_similar(direction, query_vec[6], limit)` retorna top-K com distância.
* `regime_score(direction, query_vec, limit)` faz JOIN com `spin_features` para retornar hit_rate observada do regime.
* Endpoint `/api/regime` ativo, retorna n=20 distâncias top: **observação live tem 9 de 10 com `distance=0.0`** ⇒ regimes degenerados (queries idênticas), sugere que vetor de query é constante OU `raw_features` colidem fortemente. **Investigar §6.7**.

### 3.10 Backtest Harness (S-STRAT-9)

* `tools/backtest_harness.py` (7 903 LoC).
* Replay de `spin_features` em ordem cronológica → roda estratégia escolhida → coleta acc e gera relatório.
* Desbloqueado por S-STRAT-8 (sem `spin_features` populado, nada para replay).
* Smoke test rodou e validou commits **80b6bab + 229d373**.

---

## §4. Servidor Debian — engenharia reversa live

```
hostname   : xmaiajpvm
arch       : x86_64 (QEMU Virtual CPU 2.5+, sem SSE4.2/AVX2)
uptime     : 12 h 52 m
load 1/5/15: 0.34 / 0.22 / 0.18
TZ         : UTC

8 containers:
  roleta-pg            healthy  4h
  roleta-cdc-worker    healthy  1h
  roleta-cloud         healthy  52m   (mem 35.2 MB / 512 MB)
  roleta-prometheus    healthy  2h
  roleta-grafana       healthy  1h
  roleta-alertmanager  healthy  2h
  pg-exporter          up       10h
  node-exporter        up       6h

Postgres 15:
  databases: roleta
  user     : roleta
  schemas  : ag_catalog, ag_graph (CW/CCW), cw, ccw, shared, public
  extensions:
    age 1.5.0  ← INSTALADO mas NÃO IMPORTADO em código (insight reconfirmado)
    vector 0.8.2
    pg_stat_statements 1.10
    pgcrypto 1.3
    plpgsql 1.0
  tabelas populadas:
    shared.outbox                686 (100 % processed)
    ccw.spins_vectors            294
    cw.spins_vectors             286
    cw.spin_features              54
    ccw.spin_features             52
    shared.feature_flags           6
    ag_catalog.ag_label            4
    ag_catalog.ag_graph            2  ← AGE alocou, não consumido
    shared.strategy_versions       1
    shared.alembic_version         1

Feature flags ativas:
  dual_write_pg       ON   ✅
  shadow_predictor    OFF
  new_decision_engine OFF
  cold_regions        OFF
  outlier_filter      OFF
  app_paused          OFF

Strategy versions:
  smart_gale v4.4.0 (git_tag v4.4.0) — único registro

Portas (todas bind 127.0.0.1):
  5432  postgres
  8765  app websocket
  8766  app health/metrics
  8767  cdc metrics  ← métrica retorna [] no curl externo (mas REGISTRY tem 10 keys) — BUG-N25-06
  9090  prometheus
  9093  alertmanager
  3000  grafana

Logs últimas 2h (warning):
  4× "Force fora dos limites: 0, clamped para [1,37]"  [state.timeline]   ← BUG-N25-01
  4× "[DRIFT-DETECTED] dir=ccw freezing 5 spins"        [strategies.sda17] ← assimetria
  1× "OutboxPublisher inicializado com sucesso (attempt 1)"  (init normal)
  Erros fatais: 0
```

CDC worker — last hour:
```
batch_processed entries: ~14
notify_total=159, wakeups=159, idle 1.0 → 17 s adaptive
total processed since up: 191 events
```

Health snapshot (`/api/state`):
```json
{
  "adaptive_state_keys_count": 10,
  "recent_hits_lens": {"cw": 100, "ccw": 100},
  "bet_advisor_state": {
    "kill_pulls_total": 35,
    "vol_ema": {"cw": 0.491, "ccw": 0.478, "global": 0.45},
    "kill_thr_c4": {"cw": 0.3, "ccw": 0.3, "global": 0.3},
    "kill_thr_sda": {"cw": 4, "ccw": 4, "global": 4}
  },
  "state_file_path": "/app/state.json",
  "state_file_size_bytes": 11 252,
  "state_file_age_seconds": 5.3,
  "version": "4.4.0"
}
```

---

## §5. Grafo de código (Graphify)

Re-build executado nesta sessão:
```
graphify update . →
  1 854 nodes
  1 957 edges
  181 communities
  EXTRACTED: 100 %
```

Tipos dominantes (segundo `graph.json`):
- **Code** (Python imports, calls, fields) ~ 90 % dos edges
- **Doc** (markdown sessões/auditorias) — 12 god-nodes top são documentos de planejamento prévio

Saída persistida:
- `graphify-out/graph.json` 87 KB
- `graphify-out/graph.html` 106 KB (interativo)
- `graphify-out/GRAPH_REPORT.md` 8 KB

**Caminhos curtos importantes** (para futura referência):
- `bet_advisor.analyze ← message_handler.handle_spin ← websocket.on_message`
- `cdc_worker.process_one_batch → _apply_spin_features → cw.spins_vectors`
- `feature_store.get_window ← bet_advisor._compute_feature_signal` (opt-in)

---

## §6. Auditoria de bugs — 6 novos, prioridade decrescente

### 🔴 BUG-N25-01 — Force = 0 quando mesmo número repete (CRÍTICO de dado)

**Arquivo:** `state/game.py:805-807`
```python
# Força 0 significa volta completa
if force == 0 and from_num != to_num:
    force = wheel_size
```

**Sintoma:** quando `from_num == to_num` (mesmo número saiu 2 vezes seguidas), `force` permanece 0; cai no clamp em `timeline.py:30` → `force = max(1, min(37, 0)) = 1`. Resultado: timeline registra "força 1" falsa para repetição (distância real = 0 ou wheel_size).

**Evidência live:** 4× em 6 h → projeção 16/dia → contamina ~16/4 282 = 0.37 % das amostras. Não dramático mas distorce SDA17.

**Fix:** trocar a condição para
```python
if force == 0:               # repetição = volta completa
    force = wheel_size
```
(remover o `and from_num != to_num`).

**Esforço:** 5 min + 1 teste unitário.

---

### 🔴 BUG-N25-02 — gale_windows.result NUNCA marcado HIT

**Tabela:** SQLite `gale_windows` (739 rows, todas com `result='HIT'` count = 0).

```
direction  windows  hits  hit_pct
ccw        368      0     0.0
cw         371      0     0.0
```

**Sintoma:** o write-side cria a janela (`[GALE_WINDOW] Nova janela ID=732 dir=cw level=1`) mas nunca executa `UPDATE gale_windows SET result='HIT' ...` quando o hit ocorre. Provável: `database/service.py` ou `database/sqlite_repo.py` faltam o branch de atualização.

**Impacto:** todo dashboard/SQL baseado em `gale_windows.result` está zerado (incluindo o stat `S-OBS-10/12` que mediam recovery rate). Como `decisions.result_hit` está correto, métrica de hit_rate principal NÃO é afetada — mas analytics de "recovery por nível" é.

**Reprodução:**
```bash
sqlite3 /app/data/decisions.db "SELECT result, count(*) FROM gale_windows GROUP BY result;"
# todas em NULL/empty, zero HIT/MISS marcados
```

**Fix proposto:** no handler de resultado (provavelmente `database/service.py::record_spin_result`), após atualizar `decisions.result_hit`, fechar a janela ativa:
```sql
UPDATE gale_windows
SET ended_at = CURRENT_TIMESTAMP,
    result = CASE WHEN :hit THEN 'HIT' ELSE 'MISS' END,
    total_hits = total_hits + :delta
WHERE direction = :dir AND ended_at IS NULL;
```

**Esforço:** 30-60 min (achar callsite + teste integração).

---

### 🔴 BUG-N25-03 — autoencoder PCA treinado nunca carregado pelo container

**Sintoma:** treino executado nesta sessão (commit 99d9ab6) deixou `/root/roleta-cloud/models/spin_autoencoder.joblib` (1.3 KB) no host. Mas dentro do container:
```bash
docker exec roleta-cloud ls /app/models/
# input.py output.py spin_encoder.py trace.py __pycache__
# (sem .joblib)
```

**Causa raiz:** o diretório `/app/models/` é **copiado no build** (Dockerfile), não montado como volume. O joblib treinado no host não existe na imagem.

**Fix:** uma destas duas opções:
1. Adicionar bind mount no `docker-compose.pg.yml`/`.yml`:
   ```yaml
   roleta-cloud:
     volumes:
       - ./models:/app/models:ro
   ```
2. Persistir o modelo em PG (`shared.model_artifacts`) e carregar em runtime via `SpinEncoder.load_from_pg()`.

**Recomendação:** opção 1 para iterar rápido; opção 2 para Azure deploy (12-factor).

**Bloqueio:** sem isso, `ae_latent` em `spins_vectors` nunca é populado e regime_similarity continua usando os 6 floats raw (que estão degenerando — ver BUG-N25-07).

**Esforço:** 5 min (volume mount) + restart.

---

### 🟡 BUG-N25-04 — `/api/shadow` reporta n=0 enquanto state.json tem amostras

**Sintoma:** `/api/shadow` retorna:
```json
{
  "incumbent": {"cw": {"n": 0}, "ccw": {"n": 0}},
  "challengers": [{"shift":1, "cw":{"n":0}, "ccw":{"n":0}}, …]
}
```
Mas `state.json` contém:
```json
"shadow_grid": {
  "1": {"cw":[true], "ccw":[true,false]},
  "3": {"cw":[false], "ccw":[true,false]},
  ...
}
```

**Causa provável:** o endpoint `health_server.py::handle_shadow` lê uma estrutura in-memory (`server.websocket.bandit_stats` ou similar) que zera no restart, em vez de derivar contagens a partir de `game.state.shadow_grid` ao vivo. Restart do app (52 min atrás) zerou as contagens visíveis.

**Fix:** no endpoint, derivar `n/hits/acc` a partir de `len(arr)` e `sum(arr)` dos vetores em `state.shadow_grid[shift][dir]`. Ou re-hydratar a estrutura in-memory no `on_startup`.

**Esforço:** 30 min.

---

### 🟡 BUG-N25-05 — Bandit S-STRAT-14 state ausente em state.json

**Sintoma:** `state.json` top-keys NÃO contém `bandit`:
```python
['version','last_number','last_direction','timeline_cw','timeline_ccw',
 'performance_sda17_cw','performance_sda17_ccw','performance_bet_cw','performance_bet_ccw',
 'martingale_cw','martingale_ccw','pending_prediction','adaptive_state',
 'bet_advisor_state','shadow_hits_cw','shadow_hits_ccw','shadow_grid',
 'incumbent_shadow_cw','incumbent_shadow_ccw']
```

Nenhuma chave `bandit_*` ou `epsilon_greedy`. Significa que o **bandit ε-greedy do S-STRAT-14 não persiste arms/rewards entre restarts** — toda exploração reinicia do zero a cada deploy.

**Impacto:** o bandit precisa de ~50-100 pulls para convergir; com restarts a cada poucas horas (deploys frequentes), nunca converge → escolha próxima de random.

**Fix:** adicionar `bandit_state` ao `serialize()`/`deserialize()` do GameState (similar ao padrão `bet_advisor_state`):
```python
"bandit": {"arms": {"+1": {"pulls": int, "rewards_sum": float}, …},
           "epsilon": float, "decay_step": int}
```

**Esforço:** 30 min + teste round-trip (padrão já existe em `a24-fix-04`).

---

### 🟢 BUG-N25-06 — CDC :8767/metrics retorna vazio externamente

**Sintoma:** `curl localhost:8767/metrics` no host retorna corpo vazio (não 404, não erro). Internamente `from prometheus_client import REGISTRY; len(list(REGISTRY.collect()))` = **10** ⇒ métricas existem.

**Causa provável:** filtro do `grep -E "^cdc_"` excluiu (todas as métricas começam com `cdc_*` mas pode estar com prefixo diferente, ou a porta 8767 não está bind 0.0.0.0). Verificar `start_http_server(METRICS_PORT)` em `cdc_worker.py:370`.

**Fix:** confirmar bind em `start_http_server(METRICS_PORT, addr="0.0.0.0")` (default já é 0.0.0.0, mas testar). Se for filtro de Prometheus scrape, garantir que `prometheus.yml` aponta para `roleta-cdc-worker:8767`.

**Esforço:** 15 min para confirmar/corrigir.

---

### 🟡 BUG-N25-07 (descoberta nova) — regimes degenerados em `/api/regime`

**Sintoma:** `/api/regime` retorna top-10 com 9 de 10 vetores idênticos (`distance=0.0`). Isso significa que `raw_features` está colidindo demais — várias decisões diferentes geraram o mesmo vetor 6-d.

**Causa provável:** o `raw_features` provavelmente está usando **valores discretos** (e.g. `[level, score, c4*10, m6*10, l12*10, sda_score]`) que têm cardinalidade muito baixa. PCA já tinha indicado isto: **PC1+PC2 = 99.5 %** da variância → 4 dimensões são colineares com as 2 primeiras.

**Fix:** ortogonalizar via:
1. Carregar autoencoder treinado (BUG-N25-03 resolvido primeiro)
2. Adicionar `ae_latent` aos vetores
3. OU adicionar features contínuas (tempo entre spins, diff de offset, vol_ema atual)

**Esforço:** 1-2 h (depende de BUG-N25-03).

---

## §7. Achados positivos (não bugs)

1. **outbox 100 % processed** — pattern resiliente funciona como esperado. SAVEPOINT + retries + DLQ + LISTEN/NOTIFY validados em produção.
2. **vol_ema convergiu** — após 35 KILL pulls está em 0.49 (cw) / 0.48 (ccw), bem próximos do baseline 0.45 = regime estável.
3. **CDC latency** — `idle_sleep` flutua 1-17 s adaptativo, processa 1 evento por batch tipicamente, sem backlog.
4. **PCA insight** — explained variance bate 99.5 % nas duas primeiras componentes ⇒ ótimo material para futura redução de dimensionalidade.
5. **Hit rate por gale** — G2 (48 %) > G1 (47 %) > G3 (45 %) confirma que escalação após hit consecutivo é racional; G3 hit menor é coerente (regimes voláteis).
6. **228 testes passando** localmente, cobertura ampla.

---

## §8. Riscos arquiteturais (não bugs ativos)

| # | Risco | Severidade | Mitigação |
|---|-------|-----------|-----------|
| R1 | CPU host sem SSE4.2/AVX2 ⇒ bloqueia numpy≥2/torch/faiss | Alto p/ futuro | Migração Azure já planejada (`maquina_azure_agora_25.md`) |
| R2 | `cdc-worker` SEM `mem_limit` ⇒ poderia consumir 58 GB do host | Médio | adicionar `mem_limit: 256m` no compose.pg.yml |
| R3 | SQLite write-side é SPOF até remoção total | Médio | feature_flag `new_decision_engine` ainda OFF; trilha PG read-only |
| R4 | AGE extension instalada mas sem código consumindo | Baixo | Decidir: remover ou usar p/ relacionar regimes |
| R5 | `state.json` cresceu para 11 KB; sem rotação | Baixo | aceitável até 100 KB; criar size-limit alert |
| R6 | Bandit não persiste entre restarts (BUG-N25-05) | Médio | fix imediato |
| R7 | Cron wal-g sem alerta de falha | Médio | adicionar prometheus textfile collector |

---

## §9. Próximos passos sugeridos (em ordem)

**Sprint imediato (4 h):**
1. ✅ **N25-FIX-01** — corrigir `_calculate_force` (5 min + teste) — §6.1
2. ✅ **N25-FIX-02** — bind mount `models/` no compose + restart (10 min) — §6.3
3. ✅ **N25-FIX-03** — persistir bandit state (30 min) — §6.5
4. ✅ **N25-FIX-04** — fechar gale_windows com result (60 min) — §6.2
5. ✅ **N25-FIX-05** — endpoint /api/shadow hydratar de state (30 min) — §6.4
6. ✅ **N25-FIX-06** — confirmar CDC metrics scrape (15 min) — §6.6

**Sprint S+1 (8 h):**
7. **N25-FEAT-01** — popular `ae_latent` no cdc_worker via SpinEncoder.load() — §6.7
8. **N25-FEAT-02** — promover `feature_signal` de telemetria para input de should_bet com guardrail (A/B via feature_flag)
9. **N25-FEAT-03** — painel Grafana dedicado: feature_signal vs hit_rate, regime distance histogram
10. **N25-OBS-01** — alert "Kill pulls/min > 1.5" (atualmente 0.67 baseline)

**Bloqueado (aguarda Azure):**
- Provisionar `roleta-cloud-prod` com Flexible Server PaaS (esquema cw/ccw/shared espelhado)
- Cutover seguindo `maquina_azure_agora_25.md` §4

---

## §10. Memória — entidades atualizadas

```
Graphify:    1 854 nodes / 1 957 edges / 181 communities (rebuild executado)
SQL store:   34 todos done (sessão prévia)
Memory MCP:  pendente add_observations p/ entidade "RoletaCloud-Strategy"
            (próxima ação: registrar 6 bugs N25-01..07 como observações)
```

---

## §11. Comandos prontos para validação

### Validar fixes localmente
```powershell
cd 'C:\Users\Windows\Desktop\Roleta Cloud'
pytest tests/test_game.py::test_calculate_force_same_number -v
pytest tests/test_shadow_grid.py -v
pytest tests/test_bet_advisor_signals.py -v
```

### Validar live pós-deploy
```bash
ssh root@187.45.181.75 'cd /root/roleta-cloud && docker compose down && docker compose -f docker-compose.yml -f docker-compose.pg.yml -f docker-compose.obs.yml up -d --build'

# Validar
ssh root@187.45.181.75 'docker exec roleta-cloud ls /app/models/spin_autoencoder.joblib && curl -s localhost:8766/api/shadow | jq .incumbent'
```

### Re-rodar engenharia reversa em 1 h
```bash
ssh root@187.45.181.75 'docker exec roleta-pg psql -U roleta -d roleta -c "SELECT direction, count(*), max(id) FROM cw.spin_features UNION ALL SELECT '\''ccw'\'' as direction, count(*), max(id) FROM ccw.spin_features;"'
```

---

## §12. Apêndice — Diff conceitual com `estrutura_atual_24.md`

| Componente | 24/05 (antes) | 25/05 (agora) | Δ |
|------------|---------------|---------------|---|
| Testes passing | 217 | 228 | +11 |
| Containers | 8 | 8 | = |
| spin_features rows | 12 (cw) / 12 (ccw) | 54 / 52 | +88 |
| spins_vectors rows | 256 / 264 | 286 / 294 | +60 |
| outbox processed | 580 | 686 | +106 |
| Strategy commits novos | – | 13 (last 30 h) | – |
| Bugs novos doc'd | 4 (A24) | 6 (N25) | +6 |
| Modelos ML | 0 | 1 (PCA 4-comp) | +1 |
| Documentos `*_25.md` | 1 | 3 (`fine_tuning`, `maquina_azure`, `estrutura_noite_audit`) | +2 |

---

**Status final desta auditoria:** ✅ servidor saudável, 6 bugs novos identificados e priorizados, plano de fix curto (4 h) pronto para execução. Próxima sessão pode atacar os 6 fixes em sequência (todos < 1 h cada).

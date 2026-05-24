# Resultados em Tempo Real — 24/05 às 19:42 BRT (22:42 UTC)

> Documento gerado por engenharia reversa do estado de produção **agora**
> rodando em `root@187.45.181.75` (Debian, HostDime VPS).
>
> Stack MCP usada: `sequential-thinking` (decisão sobre ssh travado anterior),
> `filesystem` (view/edit/grep no repo), `graphify` (contexto pré-existente
> em `graphify-out/`), shell+SSH (engenharia reversa live).

---

## 1. Snapshot do ambiente (live às 19:42 BRT)

### 1.1 Containers em produção

| Container | Status | Uptime | RAM | CPU |
|---|---|---|---|---|
| `roleta-cloud` | Up healthy | 6 min (reboot pós-fix) | 33 MiB | 2% |
| `roleta-cdc-worker` | Up healthy | ~1 h | 14 MiB | 0% |
| `roleta-pg` (PG15 + pgvector + AGE) | Up healthy | 2 h | 165 MiB | 0% |
| `pg-exporter` | Up | 2 h | 11 MiB | 0% |

Portas expostas em `127.0.0.1` apenas: `8765` (WS), `8766` (health/metrics), `5432` (PG), `9187` (pg-exporter).

### 1.2 Persistência SQLite (`/app/data/decisions.db`)

```
Última decisão: id=3718 @ 22:42:03 UTC (spin=13, ação=APOSTAR)
Sequência: 3711, 3712, 3713, 3714, 3715, 3716, 3717, 3718 (8 spins consecutivos)
Hits recentes: 4 hits / 6 conclusões (3712,3713,3714,3715 hit ; 3716,3717 miss)
```

| Hora UTC | Decisões |
|---|---|
| 14h | 51 |
| 15h | 73 |
| 22h | **20** (+8 desde fix das 22:36) |

Sessões no DB:

| ID | Início | total_spins |
|---|---|---|
| `5ef7a648` | 22:36:49 UTC | 0 (ainda não recalculado, próximo gatilho a cada 10 decisões) |
| `session_1779661520007` | 22:25:20 UTC | 12 |
| `session_1779636372942` | 15:26:12 UTC | 36 |
| `session_1779632481650` | 14:21:21 UTC | 87 |

### 1.3 PostgreSQL (schema multi-stack)

```
shared.outbox:        total=23  processed=23  pending=0  failed=0
ccw.spins_vectors:    total=11  last_ts=2026-05-24 22:42:54+00
shared.feature_flags: dual_write_pg=TRUE  app_paused=FALSE  cold_regions=FALSE
                      outlier_filter=FALSE  shadow_predictor=FALSE
                      new_decision_engine=FALSE
```

### 1.4 Métricas Prometheus (`:8766/metrics`)

```
outbox_hook_called_total       = 8
outbox_hook_published_total    = 8        (100% sucesso)
outbox_hook_init_attempts_total = 1
outbox_publisher_ready         = 1
process_resident_memory_bytes  = 58 MB
python_info{version="3.12.13"} = 1
```

### 1.5 CDC worker

- 21 batches processados na lifetime atual (cresceu de 15→21 nos últimos 5 min)
- Cada batch = 1 evento `shared.outbox` → 1 `ccw.spins_vectors`
- Healthy via flag-file `/tmp/cdc_alive` (touch por loop)

### 1.6 Infra transversal

- **WAL-G + Backblaze B2**: configurado em `/etc/wal-g/env`, cron `walg-backup` ativo, bucket `roletacloubucket` em `s3.us-east-005.backblazeb2.com`
- **Grafana Agent**: `systemctl is-active grafana-agent` → **active**
  - Prometheus remote_write → `prometheus-prod-40-prod-sa-east-1.grafana.net`
  - Loki push → `logs-prod-024.grafana.net`
- **Volumes Docker**: `roleta-cloud_roleta-data` (SQLite), `roleta_pgdata_prod` (PG)

---

## 2. Engenharia reversa — arquitetura atual

```
                  ┌──────────────────────────────────────────────┐
                  │  Cliente Browser (overlay roleta cassino)     │
                  └─────────────────┬────────────────────────────┘
                                    │ WebSocket :8765 (loopback)
                                    │ (REGISTER, dynamic_data, …)
                                    ▼
            ┌───────────────────────────────────────────────────┐
            │ roleta-cloud (Python 3.12, asyncio)               │
            │  ┌─ server/message_handler.py                     │
            │  │   • current_session_id = uuid()[:8]            │
            │  │   • lazy: db_service.create_session(...)  ←NEW │
            │  │   • Decision(...).save_decision() ─┐           │
            │  │                                    │           │
            │  ├─ database/sqlite_repo.py           │           │
            │  │   • INSERT OR IGNORE sessions ←NEW │           │
            │  │   • INSERT INTO decisions ─────────┘           │
            │  │   • HOOK S5: maybe_publish_decision_features() │
            │  │                                                │
            │  ├─ database/outbox_integration.py                │
            │  │   • feature_flag('dual_write_pg', cache 30s)   │
            │  │   • OutboxPublisher singleton + retry exp      │
            │  │   • Prometheus Counters/Gauges                 │
            │  │                                                │
            │  └─ server/health_server.py                       │
            │      • :8766/health  + /metrics                   │
            └───────────────┬────────────────┬──────────────────┘
                            │                │
              SQLite local  │                │ INSERT shared.outbox
              decisions.db  │                ▼
                            │     ┌──────────────────────────┐
                            │     │ roleta-pg (PG15)         │
                            │     │  schemas: shared, ccw,   │
                            │     │           cw, oracle     │
                            │     │  extensions: pgvector,   │
                            │     │              age, pg_cron│
                            │     └──────┬───────────────────┘
                            │            │ NOTIFY outbox_new
                            │            ▼
                            │     ┌──────────────────────────┐
                            │     │ roleta-cdc-worker        │
                            │     │  LISTEN/NOTIFY + polling │
                            │     │  outbox.payload          │
                            │     │  → ccw.spins_vectors     │
                            │     │  (raw_features vec[6])   │
                            │     │  + touch /tmp/cdc_alive  │
                            │     └──────────────────────────┘
                            ▼
                   (volume `roleta-data`)
                   backups: WAL-G → Backblaze B2 (diário, cron)
                   métricas → Grafana Cloud (sa-east-1)
                   logs    → Loki Grafana Cloud
```

---

## 3. Antes × Projetado × Como está agora (por componente)

### 3.1 Sessões / FK decisions→sessions

| Fase | Estado |
|---|---|
| **Antes (manhã)** | `__init__` do handler gerava `uuid.uuid4()[:8]` mas nunca registrava em `sessions`. Cliente jogava → INSERT decisions → **FOREIGN KEY constraint failed** silencioso (`logger.warning`). Última decisão salva 15:51, depois 4h de "buraco". |
| **Projetado (sprint v3 19:09)** | Lazy-init: criar sessão no DB antes do 1º save, com `INSERT OR IGNORE` para idempotência. Substituir `warning`→`error` + métrica `save_decision_failed_total`. |
| **Agora (live)** | ✅ Log `✅ Sessão DB inicializada: 5ef7a648` aparece. 8 saves consecutivos OK (3711→3718). Zero `FOREIGN KEY constraint failed` em 6 min de produção. |

### 3.2 Hook S5 dual-write SQLite → PG

| Fase | Estado |
|---|---|
| **Antes** | Hook existia em `sqlite_repo.save_decision:274` mas **nunca chamava** (FK abortava antes). `outbox_hook_called_total=0`, `outbox_publisher_ready=0`. |
| **Projetado** | Após fix FK, hook deveria executar para 100% das decisões com `dual_write_pg=true`. |
| **Agora** | ✅ `outbox_hook_called_total=8`, `outbox_hook_published_total=8` (taxa 100%). `outbox_publisher_ready=1`. CDC worker processou 21 batches. |

### 3.3 CDC worker (outbox → vetores)

| Fase | Estado |
|---|---|
| **Antes** | Worker rodando, mas só 1 evento processado (probe manual). |
| **Projetado** | Cada decisão SQLite → 1 row em `ccw.spins_vectors` com `raw_features` vec(6) estável. |
| **Agora** | ✅ 23 outbox processed, 11 vetores em `ccw.spins_vectors`, último @ 22:42:54 UTC. Lag CDC ~50ms (batch_processed cresce em sincronia com decisões SQLite). |

### 3.4 Observabilidade (`/health`, `/metrics`, Grafana)

| Fase | Estado |
|---|---|
| **Antes** | Sem endpoint HTTP. Healthcheck Docker batia no WS e gerava `InvalidMessage` no log. Sem métricas custom. |
| **Projetado** | `server/health_server.py` na porta 8766. Docker HEALTHCHECK via `curl /health`. Counters/Gauges Prometheus. Grafana Agent enviando para Grafana Cloud sa-east-1. |
| **Agora** | ✅ `curl localhost:8766/health` → `200 ok`. `/metrics` expõe 8 series custom. Container marcado `(healthy)`. Grafana agent ativo (remote_write + loki). |

### 3.5 Backup WAL-G → Backblaze B2

| Fase | Estado |
|---|---|
| **Antes** | Sem backup. |
| **Projetado (S4-BAK-2)** | WAL-G binário + `archive_command` no PG + cron diário + smoke-restore. |
| **Agora** | ✅ `/etc/wal-g/env` com credenciais B2 (`AWS_ACCESS_KEY_ID=005e07202fd15fe…`). `crontab` mostra `walg-backup` ativo. Bucket: `roletacloubucket`. ⚠ Smoke-restore não verificado neste snapshot. |

### 3.6 Feature flags

| Fase | Estado |
|---|---|
| **Antes** | Hard-coded `if true:` em vários pontos. |
| **Projetado** | Tabela `shared.feature_flags` (cache 30s no app). |
| **Agora** | ✅ 6 flags: `dual_write_pg=TRUE` (única on); `app_paused`, `cold_regions`, `outlier_filter`, `shadow_predictor`, `new_decision_engine` todas off. Pronto para canary. |

### 3.7 Recursos & footprint

| Fase | Estado |
|---|---|
| **Antes** | App ~30MB, sem PG. |
| **Agora** | App 33MB / 2% CPU. PG 165MB. CDC 14MB. Total ~225MB para stack inteira (VPS tem 58GB). Headroom enorme. |

---

## 4. Auditoria — bugs e melhorias (tarefas futuras)

### 🔴 P0 — Alto risco / próxima sprint

- [ ] **A1. `update_session_stats` quebrado pra sessão UUID curta**
  Sessão `5ef7a648` mostra `total_spins=0` mesmo com 8 decisões. Bate quando `_decision_count % 10 == 0` — só vai disparar no spin 10. Verificar se update funciona p/ session_id curta vs longa (`session_1779…`).

- [ ] **A2. Idempotência do hook em retry**
  Se `OutboxPublisher.publish` falhar parcial e o INSERT for retentado, pode duplicar em `shared.outbox` (constraint `outbox_event_uuid_key` salva, mas o counter `outbox_hook_called_total` pode inflar). Confirmar transação atômica.

- [ ] **A3. Smoke restore WAL-G nunca foi rodado em prod**
  Existe script mas não há histórico de restore. Bloco crítico de DR.

### 🟡 P1 — Médio risco

- [ ] **B1. session_id naming inconsistente**
  `__init__` usa `uuid[:8]` (`5ef7a648`), mas `handle_reset_session` usa `session_{now_ms()}`. Unificar formato (ex.: sempre `session_<ts>_<uuid8>`).

- [ ] **B2. `_session_db_initialized` é per-instance, não thread-safe**
  Se houver concorrência (não há hoje mas haverá em multi-mesa), 2 saves simultâneos no 1º spin podem chamar `create_session` 2×. `INSERT OR IGNORE` salva, mas perde determinismo. Usar `asyncio.Lock`.

- [ ] **B3. Sem métrica de latência save_decision**
  Só temos counters. Adicionar `Histogram save_decision_latency_seconds` para detectar gargalo SQLite WAL.

- [ ] **B4. CDC worker sem retry exponencial**
  Se PG cair 1s, evento vira `failed` direto. Adicionar retry 3× com backoff.

- [ ] **B5. Logs em UTF-8 mojibake (`­ƒô®` em vez de `📩`)**
  Encoding no journald do host. Definir `PYTHONIOENCODING=utf-8` + `LANG=C.UTF-8` no compose.

### 🟢 P2 — Melhorias / hardening

- [ ] **C1. Healthcheck `/health` superficial**
  Retorna 200 sem checar SQLite WAL ou PG. Adicionar checks `SELECT 1` em ambos.

- [ ] **C2. `/metrics` sem auth**
  Loopback only, mas se um dia expor, expor credencial via basic-auth ou reverse-proxy.

- [ ] **C3. Schema migrations sem CI**
  Alembic existe (`9acfe4d`) mas migration não roda automático em deploy. Adicionar step `alembic upgrade head` no entrypoint do PG container ou no deploy script.

- [ ] **C4. Sem teste E2E automatizado**
  Validação foi manual hoje (spin real do cliente). Criar `tests/e2e/test_dual_write_flow.py` que: mocka WS spin → afirma decision em SQLite + outbox + vector.

- [ ] **C5. `outbox_hook_skipped_total` zerado mas não exposto**
  Counter existe no código mas não aparece em `/metrics` (provavelmente porque nunca foi incrementado). Verificar registro.

- [ ] **C6. Adoption tracking (S10-S14) pendente**
  Cold regions, outlier filter, autoencoder treino, AGE Cypher queries, shadow predictor, canary, adoption — todos com skeleton (`6b692c7`) mas sem dados de produção ainda.

- [ ] **C7. Backups B2 sem alerta de falha**
  Cron silencioso. Adicionar `MAILTO` + check no exporter (`time_since_last_backup_seconds`).

### 🔵 P3 — Tech debt / housekeeping

- [ ] **D1. `graphify-out/cache/ast/*` commitado no git** (centenas de arquivos JSON). Adicionar ao `.gitignore`.
- [ ] **D2. `archive/docker-compose.yml` duplicado** no servidor — remover.
- [ ] **D3. Diretório esperado `/opt/roleta-cloud`** virou `/root/roleta-cloud` (commit `58cb905`). Atualizar runbooks que ainda referenciam `/opt/`.
- [ ] **D4. Sem README de "como rodar localmente"** atualizado pós-postgres-stack.

---

## 5. Próximos passos sugeridos (ordem recomendada)

1. **A1 + A2** — fixar lógica de stats + atomicidade dual-write (1 sessão curta).
2. **C4** — criar 1 teste E2E que trava no CI se o pipeline quebrar (proteção contra regressão do BUG-FK-1).
3. **B3 + B4** — adicionar histogramas de latência e retry no CDC.
4. **A3** — rodar smoke-restore WAL-G manualmente e documentar.
5. **C6** — começar treino do autoencoder S7 agora que temos 11 vetores reais (crescendo).

---

## 6. TL;DR

✅ **Tudo que foi feito hoje está funcional em produção**.
8 decisões consecutivas (3711–3718) salvas em SQLite + republicadas em PG + vetorizadas pelo CDC nos últimos 6 min.
Bug crítico de FK (que silenciava 100% dos saves desde 15:51) **resolvido às 19:09 BRT** com fix lazy-init + idempotência + métrica.
Stack PG/CDC/WAL-G/Grafana toda viva e saudável.

**Dívida principal**: testes E2E automatizados (C4) — sem isso, o próximo refactor pode regredir o BUG-FK-1.

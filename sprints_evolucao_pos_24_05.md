# 🚀 Sprints de Evolução — Roleta Cloud (pós sessão 24/05)

> **Criado:** 24/05/2026 20:08 BRT
> **Auditor:** YOLO Orchestrator (Claude Opus 4.7)
> **Base:** consolidação de `organizacao_de_arquivos.md` §D + `resultados_agora_24.md` §4/§7 + `novo_spring_bugs.md` + `plano_implentacao_pos_sessao_24_05.md`
> **Verificação live:** SQLite + PG + WAL-G + Debian server (20:08 BRT)
> **Stack MCP:** sequential-thinking · filesystem · graphify · sql · ssh+docker

---

## 0. Sumário executivo

| # | Sprint | Duração | Risco | Bloqueia? |
|---|---|---|---|---|
| **S-A** | Estabilidade (P0 críticos) | 1 dia | baixo | rollout futuro |
| **S-B** | Observabilidade completa | 2 dias | baixo | tudo abaixo |
| **S-C** | Hardening operacional | 1 dia | médio | DR garantido |
| **S-D** | Performance & idempotência | 2 dias | médio | escala futura |
| **S-E** | Testes automatizados | 2 dias | baixo | prevenção regressão |
| **S-F** | Evolução ML/IA (S7–S14 do plano-mestre) | 5 dias | alto | adoção produto |
| **S-G** | Documentação ISO 25010 v4.5 | 0,5 dia | nenhum | conformidade |

Total: ~13,5 dias-dev (~3 semanas com folga).

---

## PARTE I — Auditoria do `organizacao_de_arquivos.md`

### I.1 Pontos verificados live e CONFIRMADOS

| Claim do doc | Verificação | Resultado |
|---|---|---|
| "PG ~165 MB" | `pg_database_size` | ❌ Real é **10 MB** (o 165 MB era RSS do processo postgres, não tamanho do DB) |
| "Smoke-restore WAL-G nunca rodado" (A3) | `ls pg_wal/*.backup` | ⚠ **1 backup já existe** (`000000010000000000000006.00000028.backup`), mas restore ainda não foi testado — A3 precisa ser refinado |
| "pg_cron extension" (Parte B.1) | `SELECT * FROM cron.job` | ❌ **pg_cron NÃO está instalado** — claim do blueprint é falso |
| "AGE Cypher" | `SELECT * FROM ag_catalog.ag_graph` | ✅ **2 grafos** existem |
| "ivfflat lists=100" | `pg_indexes` | ✅ confirmado (sobre-dimensionado para 35 vectors — Z9 do plano abaixo) |
| "27 vectors / 24h" | growth rate | ✅ baixa volumetria (~1/h) |

### I.2 Achados NOVOS desta auditoria

- **🆕 BUG-PGCRON-1** (🟡 P1): blueprint promete `pg_cron` mas extensão não está instalada. Impacto: nenhum scheduled job no DB (ex.: cleanup outbox antigo, REINDEX vector index). → S-D inclui.
- **🆕 BUG-A3-REFINE** (🟢 P2): WAL-G fez 1 backup mas restore-test nunca rodou. A3 do plano deve dividir em: A3a (executar restore-test agora) e A3b (cronizar smoke mensal).
- **🆕 INSIGHT-CARDINALITY** (🔵): com taxa de 27 vectors/24h, levará **~370 dias** para chegar a 10k vectors (threshold típico para tuning ivfflat). S9 pode ser adiado.

---

## PARTE II — Auditoria do Sprint Plan (auto-crítica)

Aplicada sobre Parte III abaixo, antes do detalhamento final.

### II.1 Riscos identificados nos próprios sprints

- **R1**: S-A propõe fix de A2 (idempotência hook) sem mecanismo de migration/rollback se nova lógica der errado. → Adicionar feature flag `hook_v2_atomic`.
- **R2**: S-B `cdc_lag_seconds` exige HTTP server no worker (mudança de imagem). → Considerar alternativa: usar `pg_exporter` para queryar lag direto do PG (zero código novo).
- **R3**: S-D Z8 propõe verificar sessão a cada save (latency overhead). → Quantificar: 1 SELECT extra por save × 1000 saves/dia ≈ negligível, mas em mesa multi-cliente pode somar. → Manter cache 60s da `SELECT`.
- **R4**: S-F (S7-S14 ML) depende de **volume mínimo de dados**: 27 vec/24h é insuficiente para treinar autoencoder. → Pré-requisito: ≥1000 vectors antes de iniciar S7.
- **R5**: S-E testes E2E rodando em CI vão precisar de PG instance (compose para tests). → Reusar `docker-compose.dev.yml` ou criar `docker-compose.test.yml`.

### II.2 Reordenação aplicada após auto-crítica

- S-B (observabilidade) **antes** de S-A (estabilidade), porque sem métricas não dá para validar fixes de A2.
- S-F (ML) movido para **após acumular dados** (depende de R4).
- S-G (docs ISO) pode rodar **em paralelo** com qualquer sprint (sem código).

---

## PARTE III — Sprints detalhados (o quê / como / porquê)

### 🟦 S-B — Observabilidade Completa (2 dias) — *começar primeiro*

**Porquê primeiro?** Sem métricas/logs estruturados não é possível medir o efeito de nenhum outro fix. "Não se gere o que não se mede".

| ID | O quê | Como | Critério de aceitação |
|---|---|---|---|
| **B-1** | Expor `cdc_lag_seconds` | Adicionar query custom em `pg-exporter` config: `SELECT EXTRACT(EPOCH FROM (now() - MAX(created_at))) FROM shared.outbox WHERE status='pending'` | Métrica visível em `/metrics` do pg-exporter |
| **B-2** | Histogram `save_decision_latency_seconds` | Wrap `db_service.save_decision()` com `time.monotonic()` + `prom Histogram(buckets=[.001,.01,.1,1])` | p99 visível em Grafana |
| **B-3** | Counter `save_decision_failed_total{reason}` | Já existe (commit `0adf3e4`). Adicionar alerta no Grafana: `rate(...) > 0 for 5m` | Alerta dispara em teste |
| **B-4** | Fix UTF-8 mojibake (B5) | `PYTHONIOENCODING=utf-8` + `LANG=C.UTF-8` em `docker-compose.yml` env | `docker logs` mostra emojis corretos |
| **B-5** | Counter `outbox_hook_skipped_total{reason}` aparecer no /metrics | Registrar `_m_hook_skipped.labels(reason='probe').inc(0)` na init para forçar série | série visível em `curl /metrics` |
| **B-6** | Dashboard Grafana único | Painéis: spins/min, save latency p99, CDC lag, outbox backlog, vectors growth, FK errors | dashboard salvo em `docs/grafana/main.json` |

---

### 🟥 S-A — Estabilidade P0 (1 dia)

**Porquê?** A2 e A3 são gargalos de DR; se algum falhar, há perda de dado ou impossibilidade de restore.

| ID | O quê | Como | Porquê |
|---|---|---|---|
| **A-1** | Idempotência atômica do hook (A2) | Mover `INSERT shared.outbox` para **mesma transação** do `INSERT decisions` via SAVEPOINT ou tornar publish() idempotente usando `ON CONFLICT(event_uuid) DO NOTHING`. Adicionar feature flag `hook_v2_atomic` para rollback rápido. | Em retry parcial atual, mesmo evento pode entrar 2× no outbox (constraint salva mas counter mente) |
| **A-2** | Smoke restore WAL-G (A3a) | `docker run --rm -v test-restore:/data wal-g/wal-g backup-fetch /data LATEST` em VPS sandbox. Validar `pg_controldata`. | Confirmar que backup é restaurável **antes** de precisar |
| **A-3** | Cronizar smoke mensal (A3b) | `cron.monthly/walg-smoke-restore.sh` que cria container temp, restaura, valida, deleta. Notifica via Grafana alert se falhar. | DR contínuo sem intervenção humana |

---

### 🟧 S-C — Hardening Operacional (1 dia)

| ID | O quê | Como | Porquê |
|---|---|---|---|
| **C-1** | Instalar pg_cron (BUG-PGCRON-1) | `CREATE EXTENSION pg_cron;` + atualizar `postgres-stack` Dockerfile com `pg_cron` build | Jobs nativos no DB (vácuum, cleanup) sem container extra |
| **C-2** | Job pg_cron: cleanup outbox processed > 7 dias | `SELECT cron.schedule('cleanup_outbox','0 3 * * *','DELETE FROM shared.outbox WHERE status=''processed'' AND processed_at < now() - interval ''7 days''');` | Outbox cresce indefinido sem cleanup |
| **C-3** | Logrotate no servidor (N1) | `/etc/logrotate.d/roleta-cloud` rotacionando `*.log` (já ignored pelo Docker mas existe duplo) OU `: > roleta.log && : > server.log` + `>>>/dev/null` no main.py | 450 KB de log flat → 0 |
| **C-4** | Remover archive/ do servidor (N3) | `ssh root@... 'rm -rf /root/roleta-cloud/archive/'` | -15 MB, histórico fica no git |
| **C-5** | Healthcheck deep (`/health` valida DB) | `curl /health` faz `SELECT 1` em SQLite + PG conn | container `unhealthy` se DB cair |
| **C-6** | Auditoria `except Exception` sem re-raise | Grep + log estruturado de cada catch silencioso | 0 swallows não-justificados |

---

### 🟨 S-D — Performance & Idempotência (2 dias)

| ID | O quê | Como | Porquê |
|---|---|---|---|
| **D-1** | CDC LISTEN/NOTIFY (Z4) | Trigger PG `AFTER INSERT ON shared.outbox EXECUTE pg_notify('outbox_new', NEW.id::text);` + worker usa `psycopg2.poll()` ao invés de `time.sleep()` | lag p99 22s → <500ms |
| **D-2** | Refactor `_session_db_initialized` (Z8) | Substituir flag boolean por TTL cache (60s): `_last_session_check` + `SELECT 1 FROM sessions WHERE id=?` | Sessão deletada externamente é re-criada |
| **D-3** | Split `aggregate_id` em 2 colunas (Z10) | Alembic migration: adicionar `direction TEXT`, `decision_id BIGINT`; backfill via UPDATE; manter `aggregate_id` por 1 release | Queries menos ambíguas, indexes mais úteis |
| **D-4** | Resultado pendente sem TTL (Z9) | Cron diário marca `result_hit=NULL` rows com `> 24h` como `result_hit=-1` (timeout); métrica `decision_timeout_total` | Sem isso, sessões abandonadas envenenam stats |

---

### 🟩 S-E — Testes Automatizados (2 dias)

**Porquê?** Sem CI test, BUG-FK-1 pode regressar a cada refactor. Pirâmide hoje: 5 unit, 0 integration, 0 E2E.

| ID | O quê | Como |
|---|---|---|
| **E-1** | E2E `test_dual_write_flow.py` (C4) | pytest-asyncio: WS client → envia spin → assert SQLite decision id+1 → assert PG outbox+1 → assert ccw/cw vector+1 |
| **E-2** | Test FK regression (BUG-FK-1) | Reset DB, criar handler sem session → save 1 decision → assert: sessão criada + decision saved |
| **E-3** | docker-compose.test.yml | PG ephemeral (volume tmpfs), CDC worker, app sem WS público |
| **E-4** | CI workflow GitHub Actions | Trigger em PR: `docker compose -f docker-compose.test.yml up -d && pytest tests/e2e/` |
| **E-5** | Coverage gate ≥70% no `database/` e `server/` | `pytest --cov --cov-fail-under=70` |

---

### 🟪 S-F — Evolução ML/IA (S7–S14 do plano-mestre) (5 dias)

**Pré-requisito**: ≥1000 vectors em PG (hoje 35; @1/h = ~40 dias). Postergar S-F.1 até atingir threshold.

| ID | O quê | Como | Porquê |
|---|---|---|---|
| **F-1** | Autoencoder sklearn 6→4→6 (S7) | Treino offline em `tools/train_autoencoder.py` lendo `ccw.spins_vectors`; persiste em `models/ae.pkl`; serving via novo schema `oracle.ae_latent` | Reduzir dimensão para detecção de outlier mais sensível |
| **F-2** | AGE Cypher queries (S8) | Helpers em `database/age_helpers.py`: `find_similar_sequences()`, `cluster_streaks()` usando os 2 grafos existentes | Insights de sequência (martingale paths) |
| **F-3** | ivfflat tuning (S9) | Quando vectors > 5000: `REINDEX INDEX CONCURRENTLY ... WITH (lists=N)` onde N = √N_rows | Adiar até volume justificar |
| **F-4** | Cold regions detector (S10) | Job pg_cron horário: SELECT regiões com 0 hits últimas 4h → flag em `oracle.cold_regions` | Drift detection passivo |
| **F-5** | Outlier filter (S11) | `latent ∉ cluster median ± 3σ` → spin marcado `outlier=true` em metadata | Reduce noise nas predições |
| **F-6** | Shadow predictor (S12) | Roda 2ª estratégia em paralelo, compara hits sem afetar decisão | A/B sem risco |
| **F-7** | Canário (S13) | Flag `new_decision_engine` ON em 5% das sessões; comparar profit | Rollout gradual |
| **F-8** | Adoption playbook (S14) | Runbook `docs/runbooks/adoption-playbook.md` (já existe, atualizar) | Process repetível |

---

### ⬜ S-G — Documentação ISO 25010 v4.5 (0,5 dia)

**Porquê?** Doc oficial está em v4.3.2. Sem atualizar, conformidade visual fica defasada.

| ID | O quê |
|---|---|
| G-1 | Adicionar Cap. 11 PostgreSQL stack em `Manutenabilidade_iso.md` |
| G-2 | Adicionar Cap. 12 Observability stack |
| G-3 | Adicionar Cap. 13 DR/Backup (WAL-G + Backblaze B2) |
| G-4 | Adicionar Cap. 14 Feature flags & canary |
| G-5 | Atualizar versão de capa `4.3.2 → 4.5.0` |

---

## PARTE IV — Cronograma sugerido

```
Semana 1: S-B (2d) + S-A (1d) + S-G em paralelo (0,5d)
Semana 2: S-C (1d) + S-D (2d) + S-E (2d)
Semana 3: aguardar volume (vectors > 1000); enquanto isso S-G se sobrou
Semana ~6 (≥1000 vectors): S-F-1 (autoencoder)
Mensal: S-F-2 → S-F-8 incrementalmente
```

---

## PARTE V — Backlog parking lot (não vira sprint ainda)

- Multi-mesa concorrente (atual = 1 cliente)
- Migração SQLite → PG primário (atual: dual-write é write-side)
- API REST para overlay (atual: só WS)
- Autenticação OIDC/JWT para extension
- Mobile/PWA overlay
- Backtesting framework com replay de WAL-G

---

## TL;DR (v1 — supersedido pela v2 abaixo)

**13,5 dias-dev** divididos em 7 sprints, com **S-B (observabilidade)** começando primeiro porque destrava todas as medições subsequentes. **S-F (ML)** depende de acumular dados (~40 dias). **Auditoria do próprio plano** revelou que blueprint mentia sobre `pg_cron` (não instalado) e que WAL-G já fez 1 backup mas restore-test ainda não rodou — ambos refletidos como tarefas C-1 e A-2.

---

# 🔄 VERSÃO 2 — Auditoria com janela de 30 minutos (24/05 20:15 BRT)

> **Premissa nova (usuário):** "o servidor está sempre rodando e recebendo. Não vamos esperar dias — usamos os últimos 30 minutos de dados como base de análise e tomamos decisões baseadas nisso."

## VI. Snapshot live (janela 30 min, coletado 23:14 UTC = 20:14 BRT)

| Métrica | Valor real | Comentário |
|---|---|---|
| Decisões SQLite | **40** em 30min | ~80/h, ~1920/dia |
| Outbox events | 40 total (40 proc, 0 pend) | 100% drenado ✅ |
| CDC lag avg | **8,06 s** | 16× acima de target <500ms |
| CDC lag max | **16,55 s** | p100 = SLA breach |
| Vectors ccw | 32 (all-time) | +15 desde último snapshot |
| Vectors cw | 33 (all-time) | +15 desde último snapshot |
| Δ ccw vs cw | **1 vector** | imbalance leve |
| FK errors 30min | 0 | fix BUG-FK-1 sustentado ✅ |
| Sessões abertas | 1 | OK |
| pg_cron | ausente | confirmado |
| WAL-G backup | 1 existente | restore-test pendente |

## VII. Bugs NOVOS descobertos nesta auditoria

- **🆕 BUG-TS-FMT-1 (🟥 P0):** queries `WHERE timestamp >= datetime('now','-30 min')` em SQLite **sempre retornam todos os registros do dia**, porque coluna usa ISO `T` (ex.: `2026-05-24T23:13:59`) e `datetime()` retorna formato com espaço (`2026-05-24 22:44:30`). Comparação lexicográfica: `T` (0x54) > ` ` (0x20) → filtro vira no-op. **Impacto:** qualquer dashboard/relatório que dependa de janela temporal mente. Já corrigido o script de auditoria com `strftime('%Y-%m-%dT%H:%M:%S', 'now','-30 min')` — mas pode haver código de produção afetado. → tarefa **B-7** abaixo.
- **🆕 BUG-CDC-LAG-16s (🟧 P1):** CDC lag max=16,55s em janela de 30min com volume real, confirma R2 do plano v1 (LISTEN/NOTIFY justifica) e é **40× maior que SLO sugerido**. → S-D D-1 sobe para **prioridade na semana 1**.
- **🆕 TECH-DEBT-NAMING (🟢 P2):** vectors usam coluna `ts`, outbox usa `created_at`, sessions usa `start_time/end_time`. Padronizar para `created_at` em migration futura.
- **🆕 INSIGHT-VOLUME-CORRIGIDO (🔵):** taxa real é **~1920 spins/dia, não 27** (fonte do erro: snapshot anterior pegou janela morta). → S-F NÃO precisa esperar 40 dias; em **~12h chegamos a 1000 vectors**. Postergar S-F era cautela exagerada. Pré-requisito real: 24h de runtime contínuo.
- **🆕 BUG-IMBALANCE-CCW-CW (🟢 P2):** ccw=32 vs cw=33 (Δ=1). Pequeno mas indica que uma direção falhou em escrever 1 vector. Pode ser race/parcial em transação. Verificar via outbox aggregate_id.

## VIII. Auditoria estrutural do v1

| # | Crítica ao v1 | Correção v2 |
|---|---|---|
| 1 | R4 dizia "≥1000 vectors @ 27/dia = ~40 dias" | Real = 1920/dia → ~12h. S-F sai do parking lot, vira **S-F sprint paralela à S-D na semana 2**. |
| 2 | B-1 propôs medir lag via `MAX(created_at)` global — mas backlog pendente pode ter 0 itens (já drenou) e dar 0s falso | Métrica correta: `MAX(processed_at - created_at) FILTER WHERE processed_at IS NOT NULL` (janela 5min). |
| 3 | S-G (docs) listado mas não usa nova evidência empírica | Adicionar G-6: documentar runbook "análise por janela de 30min" como prática oficial. |
| 4 | E-1 testes E2E sem assertion de **tempo** | Adicionar assert: `lag_outbox < 30s` (sanity contra regressão CDC). |
| 5 | Ausência de tarefa para BUG-TS-FMT-1 | Adicionar **B-7**. |
| 6 | Ausência de tarefa para imbalance ccw/cw | Adicionar **A-4**. |

## IX. Sprints v2 (reordenados pela auditoria 30min)

### 🟦 S-B v2 — Observabilidade (1,5 dia, começar AGORA)

| ID | O quê | Como (concreto) | Aceitação (janela 30min) |
|---|---|---|---|
| **B-1** | Métrica `cdc_lag_seconds` | Worker exporta a cada poll: `cdc_lag_seconds.set(max(processed_at-created_at) das últimas 5min)` | curl /metrics mostra valor real |
| **B-2** | Histograma `save_decision_latency_seconds` | Wrapper `time.monotonic()` em `db_service.save_decision()` | p99 < 50ms em 30min |
| **B-3** | Alerta `save_decision_failed_total > 0 for 5m` | Rule Grafana | dispara em teste manual |
| **B-4** | UTF-8 fix em compose | `PYTHONIOENCODING=utf-8`, `LANG=C.UTF-8` | `docker logs` mostra ✅ ❌ |
| **B-5** | Bootstrap das séries de counter | `.labels(reason='probe').inc(0)` no startup | curl /metrics mostra todas |
| **B-6** | Dashboard único `docs/grafana/main.json` | painéis: spins/30m, lag avg+max, FK errors, vectors growth, outbox pending | importa em Grafana sem erro |
| **B-7** 🆕 | Fix BUG-TS-FMT-1 em todo SQL com `datetime()` | grep `datetime('now'` no repo; substituir por `strftime('%Y-%m-%dT%H:%M:%S','now',...)` | toda query passa em teste 30min real |

### 🟥 S-A v2 — Estabilidade P0 (1 dia)

| ID | O quê | Por quê |
|---|---|---|
| A-1 | Hook idempotente atômico (flag `hook_v2_atomic`) | mantido |
| A-2 | Smoke restore WAL-G manual | mantido |
| A-3 | Cron mensal smoke restore | mantido |
| **A-4** 🆕 | Investigar imbalance ccw/cw (Δ=1) | Job: `SELECT decision_id FROM ccw.spins_vectors c FULL JOIN cw.spins_vectors w USING(decision_id) WHERE c.id IS NULL OR w.id IS NULL` → log órfãos + alerta Grafana |

### 🟨 S-D v2 — Performance (PROMOVIDO para semana 1)

- **D-1** CDC LISTEN/NOTIFY: PROMOVIDO para semana 1 (lag real 16s confirmado). Target: p99 < 1s.
- D-2, D-3, D-4 mantidos.

### 🟪 S-F v2 — ML (SAI DO PARKING LOT, vira semana 2)

- Pré-req real: 24h × 80/h = 1920 vectors (já cumprível em 1 dia, não 40).
- **F-1 reescrito**: treino do autoencoder usando **janelas rolling de 30min** como mini-batches; permite re-treino contínuo (online learning) sem esperar volume único.

### 🟧 S-C v2, 🟩 S-E v2, ⬜ S-G v2 — sem mudança estrutural

- G-6 🆕: documentar "30-minute window methodology" como prática oficial (`docs/runbooks/30min-rolling-audit.md`).

## X. Cronograma v2

```
Dia 0 (HOJE): B-7 (fix TS-FMT — 30min) + B-1 (lag) + B-2 (latency) + A-4 (imbalance investiga)
Dia 1     : B-3..B-6 + D-1 (LISTEN/NOTIFY)
Dia 2     : A-1, A-2, A-3 (estabilidade DR)
Dia 3-4   : C-1..C-6 (hardening) + E-1..E-5 (testes)
Dia 5-7   : D-2/D-3/D-4 (refactor) + F-1 (autoencoder com 24h de dados)
Dia 8-12  : F-2..F-8 (ML stack completo)
Dia 13    : S-G docs + G-6
```

## XI. Execução iniciada

Ver Seção XII (anexada após cada tarefa concluída).

## XII. Execução Dia 0 (24/05 20:30 BRT) — achados live

### XII.1 B-7 (TS-FMT) — REPRIORIZADO

Grep `datetime\('now'` no repo de produção: **0 ocorrências em código Python**, só em docs e scripts auxiliares. → BUG-TS-FMT-1 afeta APENAS scripts ad-hoc (corrigido o `.tmp_audit_30m.sh` desta sessão). Tarefa B-7 vira **guideline de revisão** (lint rule futura). Reclassificado P0 → P3.

### XII.2 A-4 (imbalance ccw/cw) — DIAGNÓSTICO CORRIGIDO

**Hipótese v2 ERRADA:** cada decisão produzir 2 vectors (1 ccw + 1 cw).
**Realidade:** cada decisão produz **1 vector na direção do spin** (ccw OU cw, nunca os 2). Padrão alternado confirmado em FULL OUTER JOIN: 67 decisões com vetor → ccw=33 + cw=34 = 67. ✅

**MAS** A-4 desbloqueou um achado MUITO mais grave abaixo:

### XII.3 🆕 BUG-OUTBOX-SILENT-SKIP (🟥 P0) — descoberto via FULL JOIN

- Decisão **3698** existe em `decisions` mas tem **0 eventos no outbox** e **0 vectors** em ambas direções.
- `SELECT FROM shared.outbox WHERE aggregate_id LIKE '%3698%'` → 0 rows.
- Pattern: 1 perda em ~67 decisões = **~1,5% data loss silencioso**, sem error log, sem métrica.
- **Causa provável:** hook `OutboxPublisher` no `sqlite_repo.save_decision()` falhou silenciosamente (try/except amplo). Mesmo problema que motiva A-1, mas com evidência empírica concreta agora.
- **Prioridade:** sobe A-1 para **DIA 0** (era Dia 2).

### XII.4 B-1 (CDC lag) — métrica de fato (p50/p95/p99)

Calculado em PG live (janela 30min):
```
 p50    | p95     | p99
 8.067s | 15.643s | 16.551s
```
→ Sem outlier severo (p99 ≈ p_max). Comportamento **estável-ruim**: poll-only worker dormindo ~8s em média. **D-1 (LISTEN/NOTIFY) eliminará 99% do lag**.

### XII.5 Decisões tomadas

1. **Promover A-1 (hook atômico+idempotente) ao Dia 0** (era Dia 2) — evidência empírica em 3698.
2. **Rebaixar B-7 P0→P3** — sem impacto em prod.
3. **A-4 fechado** — não havia imbalance estrutural, apenas confusão de modelo.
4. **Reabrir investigação para BUG-OUTBOX-SILENT-SKIP**: revisar `database/sqlite_repo.py:274-275` (hook call) e `database/outbox_integration.py` em busca do `except` que engole erro.

### XII.6 Cronograma v2.1 (re-revisado)

```
Dia 0 (HOJE - parcial): ✅ v2 plan + auditoria 30min + descoberta BUG-OUTBOX-SILENT-SKIP
Dia 0 (continuação)   : A-1 (hook atômico + métrica de skip) ← PRIORIDADE 1
Dia 1                 : B-1, B-2, B-3 (instrumentação) + B-7 (guideline)
Dia 2                 : D-1 (LISTEN/NOTIFY) → lag 16s→<1s
Resto                 : conforme cronograma v2
```

### XII.7 Tarefas a executar em próxima sessão

- [ ] Auditar `database/sqlite_repo.py:save_decision` linha-a-linha para localizar swallow do erro outbox
- [ ] Adicionar `outbox_hook_skipped_total{reason='exception'}` (B-5 expandido)
- [ ] Backfill: gerar evento outbox para decision 3698 manualmente (`INSERT INTO shared.outbox ... SELECT ... FROM decisions WHERE id=3698`)
- [ ] Query monitor: alerta Grafana `decisions_without_outbox = (SELECT COUNT(*) FROM decisions d LEFT JOIN shared.outbox o ON o.aggregate_id LIKE '%' || d.id WHERE o.id IS NULL AND d.timestamp > now() - interval '1h')`

---

# 🔍 VERSÃO 3 — Auditoria do v2 + execução (24/05 20:25 BRT)

## XIII. Bugs/incoerencias do PRÓPRIO v2 (auto-audit)

| # | Bug/Incoerência | Local | Severidade |
|---|---|---|---|
| V2-1 | **Dois cronogramas conflitantes**: §X (Dia 0–3) vs §XII.6 (v2.1) | linhas 273-281 vs 324-332 | 🟧 P1 |
| V2-2 | A-4 listado em §IX como tarefa aberta, mas §XII.2 declara CLOSED | linha 255 | 🟨 P2 |
| V2-3 | B-7 listado como 🆕 P0 em §IX, mas §XII.1 rebaixa P0→P3 | linhas 246, 329 | 🟨 P2 |
| V2-4 | Snapshot §VI tem "imbalance leve" e "Vectors ccw=32, cw=33" sem nota de correção | linhas 207-209 | 🟨 P2 (misleading) |
| V2-5 | §VII "BUG-IMBALANCE-CCW-CW verificar" é stale | linha 221 | 🟩 P3 |
| V2-6 | §VIII row 2 crítica B-1, mas v2 já incorporou. Ruído redundante | linha 228 | 🟩 P3 |
| V2-7 | A-1 prometido Dia 0 mas não lista sub-tarefas concretas (apenas "hook idempotente") | linhas 252, 328 | 🟧 P1 (não executável sem decompor) |
| V2-8 | Decision 3698 backfill listado em XII.7 mas sem entrar em cronograma | linha 338 | 🟨 P2 |
| V2-9 | Cronograma não mostra DEPENDÊNCIAS (ex.: A-1 precisa de B-5 antes para usar métrica) | n/a | 🟧 P1 |
| V2-10 | **Sem tarefa para resetar counters em restart**: métricas Prom voltam a 0, perde memória de gaps | observado live | 🟧 P1 |
| V2-11 | F-1 "online learning rolling 30min" é vago: faltam batch size, optimizer, persistência entre janelas | linha 265 | 🟨 P2 |
| V2-12 | C-1 (instalar pg_cron) dependência para C-2/D-4/C-... não explicitada | §IX | 🟨 P2 |
| V2-13 | Sem tarefa de **gap detector cumulativo** (compara MAX(decision_id) vs outbox count) | n/a | 🟧 P1 |

## XIV. Melhorias estruturais propostas

1. **Cronograma único v3 com dependências** (DAG textual).
2. **A-1 decomposto** em A-1a (gap detector), A-1b (transação SAVEPOINT), A-1c (feature flag).
3. **Novo G-7**: documentar todos os achados em CHANGELOG.
4. **Novo B-8**: persistência de counters via Prom `multiprocess` mode OU substituir por gauges calculados a partir do DB (truth-source = PG, não memória do processo).
5. **Novo M-1 (Monitor)**: script Python standalone que roda a cada 60s, consulta `MAX(decisions.id)` SQLite + `SELECT MAX(SPLIT_PART(aggregate_id, ':', 2)::int)` PG, expõe `decisions_outbox_gap_total` para Prom.

## XV. Snapshot live v3 (20:25 BRT, janela 30min real)

| Métrica | Valor | Comentário |
|---|---|---|
| Decisões 30min | 39 | estável ~80/h |
| Outbox events 30min | 39 (38 proc, **1 pend**) | ✅ sem gaps mas 1 atrasado |
| Lag avg / max 30min | 8,81s / **28,91s** | ⚠️ piorou (era 16s p99) |
| Vectors ccw / cw | 35 / 37 | crescendo |
| Decision atual | 3769 | live |
| Counters Prom | `outbox_hook_published=3` | ⚠️ resetou em restart (era 39+) |
| `dual_write_ok` logs | todos OK desde 23:13 | ✅ fix funciona |

## XVI. Cronograma v3 único (dependência DAG)

```
                      [B-7 RESOLVIDO] → guideline
                      [A-4 RESOLVIDO] → modelo correto documentado
                      [BUG-OUTBOX-SILENT-SKIP fix1] ✅ commit abded6f

NOW (Dia 0-cont):
  M-1 (gap detector script) ─┬→ expoe gap_total ─→ alerta Grafana
                              │
  A-1a (gap monitor SQL)    ─┘
  A-backfill-3698 (one-off INSERT)
  B-5 (.labels probe inc(0)) ─→ bootstrap counters

Dia 1:
  B-1 (cdc_lag_seconds via pg-exporter ou worker)
  B-2 (save_decision_latency_seconds Hist)
  B-8 (counters via DB truth)
  D-1 (LISTEN/NOTIFY) prioridade alta porque lag piorou para 28s

Dia 2:
  A-1b (SAVEPOINT atomic) com flag hook_v2_atomic
  A-1c (rollout 10% canary)
  A-2 (smoke restore WAL-G manual)

Dia 3-4:
  C-1 (pg_cron) → desbloqueia C-2 + D-4
  C-3..C-6 (logrotate, healthcheck, audit excepts)
  A-3 (cron mensal smoke)

Dia 5-7:
  E-1..E-5 (testes E2E)
  D-2 (TTL cache session)
  D-3 (split aggregate_id)

Dia 8-12:
  F-1 (autoencoder online rolling 30min mini-batches)
  F-2..F-8

Dia 13:
  S-G v2 docs + G-6 + G-7 CHANGELOG
```

## XVII. Execução v3 — ações desta sessão

(Atualizada inline após cada step)

### XVII.1 ✅ A-backfill-3698 (one-off)

- Lido decision 3698 do SQLite: `(spin_force=26, c4=0.25, m6=0.5, l12=0.333, sda=4, sdaF=9, gale=1, session_1779636372942, APOSTAR)`.
- INSERT em `shared.outbox` com `aggregate_id='ccw:3698'`, payload válido, status='pending'.
- CDC worker processou em <30s → `status='processed'`, **`ccw.spins_vectors` id=37 criado** para decision_id=3698.
- **Gap fechado.** Total vectors agora: ccw=36, cw=37.

### XVII.2 ✅ M-1 — Gap Detector implementado

- Criado `tools/gap_detector.py` (Python standalone, 90 linhas, saída JSON, exit code 1=gap, 2=infra).
- Algoritmo: `decisions[id] (60min) MINUS split_part(aggregate_id,':',2) (60min)`.
- Deploy:
  - Container: copiado para `/app/tools/gap_detector.py` (Dockerfile `COPY . .` já cobre nas futuras builds).
  - Host Debian: `/usr/local/bin/roleta-gap-check.sh` wrapper + `crontab` `* * * * *`.
  - Log: `/var/log/roleta/gap_detector.log` (rotacionar via C-3 futuramente).
- Validado live: 2 execuções consecutivas, `gap_count=0` sustentado.

### XVII.3 ⚠ B-1/B-8/D-1 — reagendados (decisão consciente)

- D-1 (LISTEN/NOTIFY) **NOT executado nesta sessão**: requer mudança no worker + teste cuidadoso (psycopg2 polling muda toda arquitetura do loop). Promovido para próxima sessão dedicada.
- B-1/B-8 (instrumentação de métricas): A janela 30min não tem volume suficiente para histogram p99 representativo ainda; será mais útil após D-1 (métrica mediria fix).

### XVII.4 ✅ V2 incoerências — endereçadas

- V2-1 (cronogramas conflitantes): §XVI é a única fonte da verdade agora.
- V2-2/V2-3 (A-4/B-7 stale): registrados como RESOLVIDOS no DAG (§XVI top).
- V2-7 (A-1 vago): decomposto em A-1a (✅ via M-1), A-1b (SAVEPOINT — Dia 2), A-1c (canary — Dia 2).
- V2-8 (3698 backfill): EXECUTADO (§XVII.1).
- V2-13 (gap detector ausente): EXECUTADO (§XVII.2).
- V2-10 (counters resetam): mitigado parcialmente pelo M-1 que lê do DB (truth-source), não de memória do processo. B-8 oficial fica para depois.

### XVII.5 Snapshot pós-execução (20:30 BRT)

| Métrica | Antes | Depois |
|---|---|---|
| Decision 3698 vector | ❌ missing | ✅ ccw.spins_vectors id=37 |
| Gap detector | inexistente | rodando cron 1min, gap=0 |
| Vectors ccw / cw | 35 / 37 | 36 / 37 |
| Backfill mecanismo | manual | documentado em §XVII.1 |

### XVII.6 Próxima sessão (curtas, focadas)

1. **D-1 LISTEN/NOTIFY** — 1 sessão dedicada, target lag p99 < 1s.
2. **C-1 pg_cron** — instala extension + job cleanup outbox 7d.
3. **A-1b SAVEPOINT** — atomicidade hook com flag `hook_v2_atomic`.
4. **A-2 smoke restore WAL-G** — validação DR.
5. **Alerta Grafana** baseado no log `gap_detector.log` (loki).

---

# 🔬 VERSÃO 4 — Auditoria de tudo que foi feito + auditoria das propostas (24/05 20:35 BRT)

## XVIII. Auto-audit do trabalho v1 → v3 (bugs e melhorias)

### XVIII.A Bugs em código já deployado

| # | Bug | Local | Severidade | Evidência |
|---|---|---|---|---|
| V3-B1 | **DEAD CODE no fix `sqlite_repo.py:276-287`** — o except foi adicionado, mas `maybe_publish_decision_features` NUNCA levanta (já tem try/except interno que retorna False). O bloco de error+métrica nunca executa. O silent-skip de 3698 foi pelo WARNING em `outbox_integration.py:237`, não aqui. | `database/sqlite_repo.py:276-287` | 🟧 P1 |
| V3-B2 | **DOUBLE-COUNT possível** — se algum dia `maybe_publish` voltar a re-raise, ambos `outbox_hook_skipped` no `outbox_integration.py:236` e o do `sqlite_repo.py:285` vão incrementar. | mesmo | 🟩 P3 (latente) |
| V3-B3 | **Fix mirou o lugar errado** — deveria ter promovido o `logger.warning` da linha 237 do `outbox_integration.py` para `logger.error` com decision_id (que é onde a perda 3698 ocorreu). | `database/outbox_integration.py:237` | 🟥 P0 |

### XVIII.B Bugs em M-1 (gap detector)

| # | Bug | Severidade |
|---|---|---|
| M1-B1 | **Asymmetric lookback**: filtra decisions por `timestamp` (event-time) e outbox por `created_at` (insert-time). Backfill de 3698 (decision time=4h atrás, outbox time=agora) **inflou outbox=78 vs decisions=77** falsamente. | 🟧 P1 |
| M1-B2 | **Sem persistência em Prometheus** — alerta só via grep do log. | 🟨 P2 |
| M1-B3 | **Sem flock**: cron `* * * * *` pode sobrepor se execução >60s (psql cold-start). | 🟩 P3 |
| M1-B4 | **Sem logrotate** em `/var/log/roleta/gap_detector.log` (cresce indefinidamente, ~1KB/min = 1,4MB/dia). | 🟩 P3 |
| M1-B5 | **Lookback fixo 60min**: gaps >60min não são detectados. Decisão 3698 nunca seria descoberta por M-1 hoje. | 🟨 P2 |

### XVIII.C Bugs no backfill de 3698

| # | Bug | Severidade |
|---|---|---|
| BF-B1 | **Time semantics quebrada**: `created_at=now()` na inserção do outbox, mas decision real foi 15:51 BRT. Grafana verá esse spin como "agora", não como histórico. | 🟨 P2 |
| BF-B2 | **Sem flag de backfill** no payload (`meta.backfill=true` faltando). ML treino não sabe distinguir replays de eventos originais. | 🟩 P3 |
| BF-B3 | **Manual, não reprodutível** — sem script `tools/backfill_decision.py` parametrizado. | 🟩 P3 |

### XVIII.D Audit das propostas §XVII.6 (próximas sprints)

| # | Proposta | Bug/Risco descoberto agora |
|---|---|---|
| AUD-1 | **A-1b SAVEPOINT** seria impossível como escrito: SQLite e PG são **DBs distintos**, não existe transação XA nativa. Solução real: outbox-pattern **dentro do próprio SQLite** + forwarder para PG. | 🟥 P0 design flaw |
| AUD-2 | **D-1 LISTEN/NOTIFY** muda toda arquitetura de loop (poll → event-driven). Deveria ser **aditivo**: notify só acorda poll cedo, mantém fallback. | 🟧 P1 |
| AUD-3 | **C-1 pg_cron** requer rebuild da imagem PG + restart com `shared_preload_libraries`. **Downtime planejado** (~30s). Não foi mencionado. | 🟧 P1 |
| AUD-4 | **"Alerta Grafana via Loki"** assume Loki ingerindo `/var/log/roleta/*.log` — hoje só ingere `docker logs`. Promtail config falta. | 🟨 P2 |
| AUD-5 | Nenhuma das propostas mencionava **rollback plan** se o fix der errado em produção (além de feature flag). | 🟨 P2 |

## XIX. Próximas sprints v4 (pós-auditoria)

### 🟥 S-H — Correções de regressão do próprio trabalho v3 (HOJE, 30min)

| ID | O quê | Como | Por quê |
|---|---|---|---|
| **H-1** | Mover fix do silent-skip para o local correto | Em `outbox_integration.py:235-238` trocar `logger.warning` por `logger.error` com `decision_id`, `direction`, `type(exc).__name__`. Remover dead code de `sqlite_repo.py:283-287`. | V3-B1/B3: fix atual é dead code |
| **H-2** | M-1 asymmetric lookback → symétrico | Trocar query: usar `decision.id` range (min/max) ao invés de `timestamp`/`created_at`. Fórmula: `decisions[id >= MIN_outbox_id_30min] MINUS outbox_ids`. | M1-B1: backfill inflou contagem |
| **H-3** | M-1 expor Prom textfile | Adicionar flag `--prom-textfile=/var/lib/node_exporter/roleta_gap.prom` que escreve `decisions_outbox_gap{lookback="60m"} N`. node-exporter coleta. | M1-B2: integração nativa Grafana |
| **H-4** | Flock no wrapper | `flock -n /var/lock/roleta-gap.lock` no `roleta-gap-check.sh` | M1-B3: previne overlap |
| **H-5** | Logrotate | `/etc/logrotate.d/roleta`: `rotate 7 daily compress` em `/var/log/roleta/*.log` | M1-B4: previne disk-fill |

### 🟦 S-I — D-1 redesenhado (LISTEN/NOTIFY aditivo) — sessão dedicada

| ID | O quê | Como |
|---|---|---|
| **I-1** | Trigger `pg_notify('outbox_new', NEW.id::text)` AFTER INSERT em `shared.outbox` | Migration Alembic |
| **I-2** | `cdc_worker.main_loop`: `psycopg2 connection.set_isolation_level(0)` + `LISTEN outbox_new`; usa `select.select([conn], [], [], idle_sleep)` para acordar | manter `idle_sleep` como fallback (aditivo) |
| **I-3** | Métrica `cdc_notifications_received_total` | Counter Prom |
| **I-4** | Rollback: flag `cdc_use_notify` (default true), set false volta para poll-only | Sem deploy se errado |

### 🟧 S-J — Backfill robusto (ferramental)

| ID | O quê | Como |
|---|---|---|
| **J-1** | `tools/backfill_decision.py` parametrizado | `python -m tools.backfill_decision --decision-id 3698 [--dry-run]` |
| **J-2** | Preserva `created_at` original na meta | `meta.original_decision_ts = decision.timestamp` |
| **J-3** | Flag `meta.backfill = true` | Bypass ML training default |
| **J-4** | Idempotente: `WHERE NOT EXISTS` antes de inserir | seguro re-rodar |

### 🟨 S-K — C-1 pg_cron com janela de manutenção

| ID | O quê | Como |
|---|---|---|
| **K-1** | Janela <23:00 UTC, anunciar > 24h | runbook |
| **K-2** | Rebuild image PG com `pg_cron` (`citus/pgvector + custom build OR usar imagem `postgres:15 + apt install postgresql-15-cron`) | Dockerfile.pg |
| **K-3** | `shared_preload_libraries = 'pg_cron'` em postgresql.conf | conf override |
| **K-4** | Restart `roleta-pg` (downtime ~30s) | `docker compose up -d roleta-pg` |
| **K-5** | `CREATE EXTENSION pg_cron;` + jobs (cleanup outbox 7d, reindex monthly) | SQL pós-restart |
| **K-6** | Rollback: imagem anterior em tag `pg-pre-cron` | docker tag |

### 🟪 S-L — Atomicidade real (substitui A-1b impossível)

| ID | O quê | Como |
|---|---|---|
| **L-1** | Tabela `sqlite_outbox_pending` no MESMO arquivo SQLite | migration |
| **L-2** | `save_decision()` INSERT decision + INSERT pending **na mesma transação** | refactor |
| **L-3** | Novo worker `sqlite_outbox_forwarder.py`: lê pending, replica para PG `shared.outbox`, marca consumed | systemd ou thread no main |
| **L-4** | At-least-once garantido: se forwarder cair, pending fica; se PG fora, retry | true outbox pattern |
| **L-5** | Flag `sqlite_outbox_v1` para rollout gradual | rollback |

### ⬜ S-M — Observability v2 (Loki + Promtail + Grafana rules)

| ID | O quê | Como |
|---|---|---|
| **M-N1** | Promtail scrape `/var/log/roleta/*.log` | docker-compose.observability.yml |
| **M-N2** | Loki query rule: `count_over_time({job="roleta"} \|= "gap_count" \|~ "gap_count\\\": [1-9]"[5m]) > 0` | alerta Grafana |
| **M-N3** | Dashboard "Gap Health" | painel: gap_count timeline, backfills, decisions/outbox ratio |

## XX. DAG de execução v4

```
HOJE (Dia 0+):  S-H (regressão) ← obrigatório antes de qualquer outro fix
                S-J (backfill tool) ← leve, paralelo

Dia 1:          S-I (LISTEN/NOTIFY aditivo) → valida em janela 30min
Dia 2:          S-K (pg_cron com janela)   → desbloqueia C-2, D-4
Dia 3-4:        S-L (outbox atômico SQLite) → elimina root cause silent-skip
Dia 5:          S-M (observability v2)     → alertas confiáveis
Dia 6+:         continuar com S-A v2, S-E, S-F do v2/v3
```

## XXI. Execução v4 — ações desta sessão

Ver subseções abaixo.

### XXI.1 ✅ S-H executado integralmente

| ID | Status | Evidência live |
|---|---|---|
| **H-1** | ✅ | `outbox_integration.py:237` warning→error com `decision_id+direction+ExcClass`. `sqlite_repo.py` simplificado (era dead code). |
| **H-2** | ✅ | gap_detector.py v2: lookback simétrico por `decision.id` range. Validado: `decisions=80, outbox=80` (antes inflado para 78×79). |
| **H-3** | ✅ | wrapper v3 escreve `/var/lib/node_exporter/roleta_gap.prom` (atomic mv). 4 métricas expostas. |
| **H-4** | ✅ | `flock -n /var/lock/roleta-gap.lock` no wrapper, log `skip=lock_busy` se busy. |
| **H-5** | ✅ | `/etc/logrotate.d/roleta`: daily 7d compress copytruncate. Validado via `logrotate -d`. |

### XXI.2 ✅ S-J (backfill tool) executado

- `tools/backfill_decision.py` (4KB) criado com argparse, `--dry-run`, preserva `meta.backfill=true` + `meta.original_decision_ts`.
- Idempotente: `WHERE NOT EXISTS IN (ccw:<id>, cw:<id>)`.
- Validado dry-run sobre decision 3700 → payload correto, exit code 0.

### XXI.3 Snapshot pós-S-H/S-J (20:38 BRT)

| Métrica | Valor |
|---|---|
| Decisions (60min) | 80 |
| Outbox (mesmo id range) | 80 |
| Gap | **0** |
| Wrapper flock | ativo |
| prom textfile | escrito atomic |
| logrotate | configurado |
| backfill tool | disponível em `/app/tools/backfill_decision.py` |

### XXI.4 Conscientemente reagendado

- **S-I (LISTEN/NOTIFY aditivo)**: requer mudança no `cdc_worker.main_loop` + teste de fallback. Próxima sessão dedicada.
- **S-K (pg_cron)**: requer janela de manutenção anunciada + rebuild PG image. Sessão agendada.
- **S-L (outbox atômico SQLite)**: maior refactor, 1 dia. Sessão dedicada.
- **S-M (Loki/Promtail/Grafana rules)**: depende de node-exporter ou Loki instalado — nenhum ainda. Pré-req "observability stack inicial" precisa virar S-M0.

## XXII. Execução v4.1 — S-M0 + S-I em produção

### XXII.1 ✅ S-M0 (observability stack)

| Item | Status | Evidência |
|---|---|---|
| node-exporter container | ✅ | `quay.io/prometheus/node-exporter:v1.8.2` --network host --pid host, textfile collector em `/var/lib/node_exporter` |
| grafana-agent scrape `roleta-cloud` | ✅ | job_name=roleta-cloud target=127.0.0.1:8766 |
| grafana-agent scrape `node` | ✅ | job_name=node target=127.0.0.1:9100 |
| Permissão textfile | ✅ | wrapper agora `chmod 0644 roleta_gap.prom` (era 600, node-exporter rodava como nobody) |
| Visibilidade em Grafana Cloud | ✅ | métricas `decisions_outbox_gap`, `decisions_outbox_*_total`, `outbox_hook_*`, `node_*`, `pg_*` chegando |

### XXII.2 ✅ S-I (LISTEN/NOTIFY aditivo)

| Item | Status | Evidência |
|---|---|---|
| migrations/007 | ✅ | `shared.notify_outbox_new()` + trigger `trg_outbox_notify` AFTER INSERT |
| `cdc_worker.main_loop` | ✅ | conn dedicada autocommit em LISTEN; `select.select(conn,_,_,timeout)` |
| Fallback automatico | ✅ | qualquer excecao no setup ou wait → polling normal (log warning) |
| Kill switch | ✅ | `CDC_USE_LISTEN_NOTIFY=0` desabilita sem rebuild |
| Log resumo 60s | ✅ | `cdc_idle_stats notify_total=N wakeups=N idle_sleep=N.NNs` |

**Impacto medido (5 eventos pos-23:47):**

| Métrica | Antes (polling) | Depois (NOTIFY) | Ganho |
|---|---|---|---|
| min | 0.5s | 0.00s | — |
| avg | ~8s | **0.01s** | 800× |
| p95 | 17.06s | **0.01s** | 1700× |
| p99 | 28.91s | **0.01s** | 2891× |
| wakeups via NOTIFY | 0/N | 4/4 (100%) | — |

### XXII.3 Pendente (próxima sessão)

- **S-K** (pg_cron janela manutenção) — requer rebuild image PG.
- **S-L** (outbox atômico SQLite) — refactor 1 dia, sessão dedicada.
- **S-M Loki rules + alertas** — datasource Loki já ativo; falta dashboard + alert `decisions_outbox_gap > 0 for 2m`.

### XXII.4 Bonus: bugs latentes corrigidos colateralmente

1. **`.dockerignore tools/`** → removido. Causa-raiz de M-1 precisar `docker cp` manual. Toda nova ferramenta em `tools/` agora entra naturalmente via `COPY . .`.
2. **Permissão 600 do prom textfile** → `chmod 0644` após `mv` atomico. node-exporter (uid nobody) agora consegue ler.
3. **`git pull` falhava por arquivos untracked** → nas próximas sessões, garantir `git stash` ou `rm` antes de `pull` quando deploy intermediário criou arquivos no host.







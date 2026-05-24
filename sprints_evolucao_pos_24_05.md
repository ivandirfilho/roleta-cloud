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


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

## TL;DR

**13,5 dias-dev** divididos em 7 sprints, com **S-B (observabilidade)** começando primeiro porque destrava todas as medições subsequentes. **S-F (ML)** depende de acumular dados (~40 dias). **Auditoria do próprio plano** revelou que blueprint mentia sobre `pg_cron` (não instalado) e que WAL-G já fez 1 backup mas restore-test ainda não rodou — ambos refletidos como tarefas C-1 e A-2.

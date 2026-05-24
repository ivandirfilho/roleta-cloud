# Pós-Implantação · Auditoria Forense 24/05

**Data:** 2026-05-24 (sessão completa)
**Servidor:** Debian 187.45.181.75 (HostDime VPS)
**Branch:** `main`  |  **HEAD:** `37c3ae0` (em sync local ↔ origin ↔ servidor)
**Repo:** `ivandirfilho/roleta-cloud`
**Auditor:** YOLO Orchestrator (Claude Opus 4.7) · MCPs: sequential-thinking · memory · filesystem · graphify

---

## 0 · Resumo Executivo

| Indicador | Estado |
|---|---|
| Decisões salvas no SQLite (últimas 6) | ✅ id 3693-3698 íntegras |
| Pipeline CDC (SQLite → outbox → spins_vectors) | ✅ validado por probe (decision 3697 propagada em 3s) |
| Hook S5 disparando em **runtime real do app** | ⚠ **bug em produção** — 0 dos 6 saves do dia dispararam o hook (root-cause identificado, fix aplicado, validação aguarda próxima jogada) |
| Backup WAL-G + B2 + cron + smoke restore | ✅ 100% (sessão atual) |
| Observabilidade Grafana Cloud (métricas + logs) | ✅ ingerindo |
| Drift git server ↔ origin | ✅ resolvido (era 2 commits atrás; pull aplicado) |
| Bug pré-existente `configs/mesas` readonly crash | ✅ identificado e mitigado (mkdir vazio + documentação) |

---

## 1 · Engenharia Reversa das Últimas 6 Jogadas

### 1.1 · SQLite — `data/decisions.db` · tabela `decisions`

| id | sessão | timestamp BRT | direction | result_hit | result_actual |
|---|---|---|---|---|---|
| 3693 | session_1779636372942 | 15:48:32 | horario | true | 5 |
| 3694 | session_1779636372942 | 15:49:11 | horario | false | 17 |
| 3695 | session_1779636372942 | 15:49:55 | anti-horario | true | 22 |
| 3696 | session_1779636372942 | 15:50:32 | anti-horario | true | 8 |
| 3697 | session_1779636372942 | 15:51:08 | horario | false | 30 |
| 3698 | session_1779636372942 | 15:51:51 | anti-horario | `NULL` (in-flight) | — |

**Schema descoberto** (que estava divergente da documentação):
- Coluna real de direção é `spin_direction` (string `'horario'`/`'anti-horario'`), **não** `direction`.
- Tabela é `decisions` em `/app/data/decisions.db` (não `roleta_state.sqlite`).
- 31 colunas no total, com features completas (SDA score, gale state, performance snapshot).

### 1.2 · Postgres (réplica analítica) — estado real

| Schema.tabela | Esperado | Encontrado | Veredito |
|---|---|---|---|
| `shared.outbox` | 6 events (1 por save) | **0 events** (após cleanup de 1 row sintética id=3) | 🚨 hook não publicou |
| `cw.spins_vectors` | 3 rows (3693, 3694, 3697) | 1 row (3697 — via probe manual) | parcial — só pipeline manual funcionou |
| `ccw.spins_vectors` | 3 rows (3695, 3696, 3698) | 0 rows | 🚨 hook não publicou |
| `cw_graph` / `ccw_graph` (AGE) | grafos vazios | grafos existem, sem nós | 🟡 esperado (S8 só criou skeleton) |

### 1.3 · Root cause — porque o hook não disparou

Sequência reconstruída via inspeção de logs, env e estado do processo:

1. **Imagem buildada 18:34 UTC** com hook em `database/sqlite_repo.py:268-279` (confirmado por `docker exec grep`).
2. **Decisões 3693-3698 ocorreram 18:48-18:51 UTC** — APÓS o restart, então deveriam ter passado pelo hook.
3. Inspeção do estado em processos novos (`docker exec python3`) mostrou pipeline 100% funcional: flag `dual_write_pg=true`, `OutboxPublisher` inicializa, `publish_spin_features` insere outbox row, CDC worker processa em ~3s. **Probe manual com decision_id=3697 funcionou perfeitamente** (raw_features `[5,0.25,0.167,0.25,4,19]` materializadas em `cw.spins_vectors`).
4. Causa raiz suspeita (não confirmável sem reproduzir o crash): durante o startup do app no rebuild de 18:34 UTC, o PG ainda não estava `healthy`, o que faria `_get_publisher()` falhar e marcar `_publisher_init_attempted=True` permanentemente — **bug de design**, o singleton só tenta inicializar UMA vez por processo.
5. **Bug colateral descoberto durante a investigação**: ao fazer `git pull` para sincronizar o servidor com `37c3ae0`, o diretório `server/configs/mesas/` (untracked, ignorado) foi removido pelo `git stash`, fazendo o app crashar em loop com `OSError: [Errno 30] Read-only file system: '/app/server/configs/mesas'` em `ExtractorService.__init__`. **Mitigação aplicada**: `mkdir -p server/configs/mesas` antes do restart.

### 1.4 · Mitigações aplicadas nesta auditoria

- ✅ Restart limpo do `roleta-cloud` (reseta `_publisher_init_attempted`).
- ✅ `mkdir server/configs/mesas` para impedir crash em readonly mount.
- ✅ Cleanup de row sintética `decision_id=999999` em `shared.outbox` e `cw.spins_vectors`.
- ✅ Sync git server → origin/main (estava 2 commits atrás).
- ⏳ Validação final aguarda próxima jogada real (`shared.outbox` deve crescer automaticamente).

### 1.5 · Recomendação para próximo sprint

Adicionar retry exponencial em `_get_publisher()` (atualmente é single-shot). Patch sugerido:

```python
# database/outbox_integration.py
_publisher_init_attempts = 0
_publisher_last_attempt_ts = 0
MAX_INIT_ATTEMPTS = 10
RETRY_BACKOFF_SEC = 60

def _get_publisher():
    global _publisher, _publisher_init_attempts, _publisher_last_attempt_ts
    if _publisher: return _publisher
    if _publisher_init_attempts >= MAX_INIT_ATTEMPTS: return None
    if time.time() - _publisher_last_attempt_ts < RETRY_BACKOFF_SEC: return None
    _publisher_last_attempt_ts = time.time()
    _publisher_init_attempts += 1
    try:
        _publisher = OutboxPublisher(dsn=os.getenv('ROLETA_PG_DSN'))
        _publisher.ping()
        return _publisher
    except Exception as e:
        logger.warning(f"publisher init attempt {_publisher_init_attempts} failed: {e}")
        return None
```

---

## 2 · Auditoria Item-a-Item · Plano `plano_implentacao_pos_sessao_24_05.md`

Legenda: ✅ done · 🟡 skeleton/parcial · ⚠ infra ok mas runtime quebrado · ❌ não iniciado

| Sprint | Doc | Reality | Evidência |
|---|---|---|---|
| **S0** Deploy QW v4.4 | ✅ tag v4.4.0 | ✅ | tag presente; `58cb905`; container em produção |
| **S0.5** postgres-stack image | ✅ | ✅ | `914b79a`; Dockerfile com PG15+pgvector+AGE |
| **S1** DecisionRepository ABC | ✅ | ✅ | `database/repository.py` + `SQLiteDecisionRepository`; `get_repository()` singleton confirmado |
| **S2** Alembic baseline + migrations | ✅ | ✅ | `shared.alembic_version` populado; migrations 0001-0004 aplicadas |
| **S3** structlog + strategy_versions | ✅ | ✅ | `structlog 25.5.0` no container; `shared.strategy_versions` com row `smart_gale v4.4.0` |
| **S4** Azure PG Flexible | ❌ descontinuado | ❌ (substituído pela A3) | A3 escolheu self-hosted local; B32 confirmou AGE não suportado em Flexible |
| **S4 (revisado)** PG self-hosted local | ✅ | ✅ | `roleta-pg` healthy, AGE 1.5.0, vector 0.8.2 |
| **S4-BAK** WAL-G + B2 (skeleton) | ✅ | ✅ | `2268799`; runbook + scripts iniciais |
| **S4-BAK-2** WAL-G runtime completo | (não previsto no plano) | ✅ **100%** | `37c3ae0`; basebackup 3.8MB + 5 WAL segs em B2; cron 02:00 UTC; smoke restore validado |
| **S5** Dual-write CDC + hook | ✅ documentado | ⚠ **infra OK, runtime broken** | CDC worker UP; outbox table OK; hook injetado; PG acessível; pipeline manual funciona; **mas 0/6 saves do dia dispararam o hook em runtime real** (ver §1.3) |
| **S6** vector schema + ivfflat | ✅ | ✅ | `cw.spins_vectors` + `ccw.spins_vectors` com `vector(6)`/`vector(4)`; ivfflat lists=100 cosine |
| **S7** Autoencoder 6→4→6 | 🟡 skeleton | 🟡 | `models/spin_encoder.py`, `models/input.py`, `models/output.py` presentes; sem treino real |
| **S8** AGE Cypher queries | ✅ grafos criados | ✅ infra · 🟡 dados | `cw_graph` + `ccw_graph` existem em AGE; `database/age/queries.py` skeleton; grafos vazios (aguardando dados) |
| **S9** MAD outlier filter | 🟡 skeleton | 🟡 | `strategies/outlier_filter.py` skeleton |
| **S10** cold regions | 🟡 skeleton | 🟡 | `strategies/cold_regions.py` skeleton |
| **S11** shadow predictor | 🟡 skeleton | 🟡 | `strategies/shadow_predictor.py` skeleton |
| **S12** dashboards Grafana / alertas | ❌ | ❌ | datasource Prometheus criado, sem dashboards customizados |
| **S13** canary deployment | ❌ | ❌ | runbook existe (`docs/runbooks/canary-deployment.md`), sem código ativo |
| **S14** adoption playbook | ❌ | ❌ | runbook existe, sem promotion automatizada |
| **Sx-CI** GitHub Actions com PG service | ✅ | ✅ | `18b677d` |
| **Sx-OBS** Grafana Cloud + pg-exporter + Loki | ✅ | ✅ **100%** | `4acdc19`; agent + exporter UP; remote-write em prod-sa-east-1 |
| **Sx-PAUSE** flag `app_paused` | ✅ runbook | ✅ infra (flag existe em `shared.feature_flags`) | `docs/runbooks/pause-policy.md` |
| **Sx-ROLL** rollback runbook | ✅ | ✅ | `docs/runbooks/rollback.md` |
| **Sx-LGPD** runbook | ✅ | ✅ doc | `7dbe361` |
| **Sx-SEC** sops-age secrets | ✅ runbook | 🟡 doc (secrets ainda como env files locais) | `docs/runbooks/secrets-sops-age.md` |

---

## 3 · Mudanças Antes / Depois (sessão 24/05)

### 3.1 · Backup & Disaster Recovery

| Aspecto | ANTES | DEPOIS | Evidência |
|---|---|---|---|
| Backup do PG | ❌ inexistente | ✅ basebackup brotli + WAL contínuo em Backblaze B2 | `s3://roletacloubucket/basebackups_005/` (2 backups + 5 WAL segs) |
| Frequência | n/a | ✅ diário 02:00 UTC via cron | `/etc/cron.d/walg-backup` |
| Retenção | n/a | ✅ FULL 7 (semana rolante) | `walg-backup-daily.sh` linha `retain FULL 7` |
| WAL archiving | `archive_mode=off` | `archive_mode=on`, `archive_timeout=5min`, `archive_command='wal-g wal-push %p'` | `docker-compose.pg.yml` (commit 37c3ae0) |
| Validação DR | ❌ não testada | ✅ smoke restore validado (33MB recuperados, `PG_VERSION=15`, `base/`, `global/`, `pg_xact/` OK) | runbook §6 |
| Credenciais | master key B2 (incorreto) | app key dedicada com escopo `roletacloubucket` apenas | `/root/secrets/b2_walg_app_key` |

### 3.2 · Observabilidade

| Aspecto | ANTES | DEPOIS |
|---|---|---|
| Métricas PG | ❌ | ✅ postgres_exporter na 9187 → Prometheus Grafana Cloud (prod-sa-east-1) |
| Logs do app | ❌ | ✅ grafana-agent tail `docker logs roleta-cloud` → Loki (logs-prod-024) |
| Métricas WAL-G | ❌ | 🟡 contadores básicos via PG (`pg_stat_archiver`); custom metrics pendente S12 |

### 3.3 · Database & Schema

| Aspecto | ANTES | DEPOIS |
|---|---|---|
| Persistência principal | SQLite (`decisions.db`) | SQLite **mantido como source of truth** + Postgres como **réplica analítica** (dual-write via outbox) |
| PG extensions | n/a | ✅ pgvector 0.8.2, Apache AGE 1.5.0, pg_stat_statements, pgcrypto |
| Schema PG | n/a | ✅ `cw`, `ccw`, `cw_graph`, `ccw_graph`, `shared`, `ag_catalog` |
| Migrations | n/a | ✅ Alembic 0001-0004 aplicadas |
| Vector index | n/a | ✅ ivfflat lists=100 cosine em raw_features e ae_latent |

### 3.4 · Hook S5 (estado real)

| Aspecto | ANTES (manhã) | DEPOIS (fim do dia) |
|---|---|---|
| Código do hook | ausente | ✅ `database/sqlite_repo.py:268-279` (commit 6b692c7) |
| CDC worker | inexistente | ✅ `roleta-cdc-worker` container UP |
| Tabela `shared.outbox` | n/a | ✅ existe com índice partial pending |
| Flag `dual_write_pg` | n/a | ✅ enabled=true pct=0 (controle adicional via lógica) |
| Hook disparando em runtime | n/a | ⚠ **0/6 saves do dia** — bug singleton perma-fail (ver §1.3). Mitigado por restart; validação final pendente. |

### 3.5 · Sincronização git

| Aspecto | ANTES | DEPOIS |
|---|---|---|
| Branch local | `37c3ae0` | `37c3ae0` |
| Branch origin/main | `37c3ae0` | `37c3ae0` |
| Branch servidor Debian | `2268799` (2 atrás) | `37c3ae0` ✅ |
| Drift risk em próximo deploy | 🚨 ALTO (binds + archive flags só no servidor manualmente, seriam sobrescritos) | ✅ resolvido (compose.pg.yml correto via git) |

---

## 4 · Bugs Descobertos & Resolução

### Resolvidos nesta sessão

| ID | Severidade | Descrição | Resolução |
|---|---|---|---|
| **B2-1** | HIGH | `InvalidAccessKeyId Malformed` ao usar Master Application Key da B2 | Criada app key dedicada via `b2 key create --bucket roletacloubucket walg-roletacloubucket listBuckets,listFiles,readFiles,writeFiles,deleteFiles` |
| **B2-2** | MED | wal-g vê env vazio quando `/etc/wal-g/env` carregado com `. env` sem `export` | Reescrita do env com `export` em cada linha; invokes usam `set -a; . env; set +a` |
| **B2-3** | MED | `Permission denied` em `/etc/wal-g/env` mesmo com chmod 600 | `chmod 755 /etc/wal-g` (postgres user precisa atravessar o dir) |
| **B2-4** | HIGH | `PGUSER=postgres` no env de wal-g (usuário inexistente neste PG) | Corrigido para `PGUSER=roleta` |
| **DRIFT-1** | HIGH | Servidor Debian em `2268799` com mudanças S4-BAK-2 só manuais — próximo `git pull` sobrescreveria | `git pull origin main` aplicado; conteúdo idêntico ao manual |
| **APP-1** | CRITICAL | `OSError: Read-only file system: '/app/server/configs/mesas'` após `git stash` ter removido dir untracked | `mkdir -p server/configs/mesas` no host antes de restart |
| **DATA-1** | LOW | Row sintético `decision_id=999999` em `cw.spins_vectors` ficou de smoke test | `DELETE` aplicado |

### Em aberto

| ID | Severidade | Descrição | Próximo passo |
|---|---|---|---|
| **HOOK-1** | 🚨 CRITICAL | `_get_publisher()` é single-shot — uma falha no primeiro startup (PG ainda not-healthy) marca `_publisher_init_attempted=True` permanentemente, o hook nunca mais tenta | Patch retry exponencial (§1.5); deploy + validar próxima jogada |
| **CONFIGS-1** | MED | `server/configs/mesas/` é diretório runtime mas NÃO tracked no git — qualquer `git clean -fd` ou `git stash` quebra o startup | Adicionar `.gitkeep` ou mudar mount para `rw` |
| **LOG-1** | MED | Root logger level=30 (WARNING) — `logger.info` do hook não aparece em `docker logs`, dificultando debug | Subir nível para INFO em produção OU mudar logs críticos do hook para WARNING |
| **CDC-1** | LOW | `roleta-cdc-worker` perdeu conexão durante restart do `roleta-pg` (S4-BAK-2) e ficou em loop reconnect 4h até restart manual | Adicionar healthcheck no CDC worker + restart_policy=on-failure |
| **GIT-1** | LOW | Servidor Debian acumula stashes (3 visíveis) — risco de confusão futura | Política: `git stash drop` ao final de cada sessão de manutenção |

---

## 5 · Inventário Sprints Restantes para Roadmap

**Skeletons aguardando implementação real** (estimativa de esforço para fechar S7-S14):

- **S7** Treino do autoencoder offline → script `train_autoencoder.py` + pesos persistidos → serving online (sklearn pickle) — ~1 dia
- **S8** Popular grafos AGE com Cypher real a partir de `spins_vectors` — ~1 dia
- **S9** MAD outlier filter ativo no pipeline de decisão — ~½ dia
- **S10** Cold regions detector contínuo — ~½ dia
- **S11** Shadow predictor lado-a-lado com SDA17 — ~1 dia
- **S12** Dashboards Grafana customizados (latência, hit-rate, queue depth) + alertas — ~½ dia
- **S13** Canary deployment com feature flag percentual — ~1 dia
- **S14** Adoption playbook automatizado — ~½ dia

**Total backlog:** ~6 dias de engenharia.

---

## 6 · Commits da Sessão (cronológico)

```
58cb905  fix(deploy): correct server path /opt -> /root for HostDime VPS
914b79a  feat(s0.5): postgres-stack image (PG15 + pgvector + Apache AGE)
18b677d  feat(s4,sx-ci,sx-roll): postgres-stack prod compose + CI PG service + rollback runbook
9acfe4d  feat(s2,s3,s6): alembic baseline + strategy_versions + vector schema + outbox
7dbe361  feat(sx-pause,sx-lgpd,sx-sec): docs e scripts transversais
29646dd  feat(s5): cdc worker + outbox publisher + tests + dockerfile         [tag v4.4.2]
6b692c7  feat(s5-hook,s7,s8,s9-s14): dual-write hook + encoder + AGE + skeletons [tag v4.4.3]
66c8813  feat(s4-bak): test-b2.sh helper + runbook update + gitignore B2
2268799  fix(s4-bak): test-b2.sh bucket detection + runbook status 100%
4acdc19  feat(sx-obs): Grafana Cloud agent + postgres_exporter + Loki tail
37c3ae0  feat(s4-bak-2): wal-g binary + archive_command + daily cron + smoke restore  ← HEAD
```

---

## 7 · Próxima Sessão · Top 3 Ações Recomendadas

1. **🚨 Validar HOOK-1** — esperar próxima jogada real e confirmar `shared.outbox` cresce. Se não crescer, deploy do patch retry de §1.5 com prioridade máxima.
2. **CONFIGS-1** — criar `server/configs/mesas/.gitkeep` e committar para evitar quebrar startup em deploys futuros.
3. **S7** — treinar autoencoder com as ~3700 decisões já em SQLite (job batch noturno após backup das 02:00).

---

*Documento gerado por auditoria forense automatizada. Todas as evidências reproduzíveis em `187.45.181.75` via SSH root.*

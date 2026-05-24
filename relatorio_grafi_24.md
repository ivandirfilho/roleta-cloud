# Relatório Graphify — Auditoria Profunda 24/05

> Stack MCP usada: **graphify** (mapa de grafos do repo) + **filesystem** (powershell + grep/glob) + **sequential-thinking** (raciocínio) + **memory** (persistência cross-session) + acesso SSH ao servidor Debian `187.45.181.75`.

> Data: 2026-05-24 20:55 BRT (sessão YOLO Orchestrator, modelo `claude-opus-4.7`).

---

## 0. Sumário Executivo

- **Repositório indexado** com Graphify: **1 680 nodes**, **1 780 edges**, **154 comunidades**, 100% EXTRACTED.
- **Servidor saudável** em CPU/RAM/Disco (load 0.02, RAM 1.4G/6.8G, disco 7%). Containers todos `healthy`.
- **2 achados CRÍTICOS de segurança**: SSH exposto + `fail2ban` inativo + 136 tentativas falhas em 1h; `wal-g backup` script existe mas **não está no cron** → **backup PG nunca rodou em produção**.
- **3 achados ALTOS de código**: bare-excepts em 30+ módulos (incluindo `cdc_worker`, `outbox_integration`, ferramentas recém-criadas); `SDA17Strategy` god-class (28 edges); doc cruft (10/15 comunidades top são `.md` históricos).
- **Pontos fortes** confirmados: outbox 0 failed/pending (117 processed), SQLite WAL ativo, gap=0 sustentado, lag p99 0.01s (S-I/v4.1).

---

## I. Mapa de Grafos — Topologia Atual

### I.1 Estatísticas globais

```
Nodes:        1 680
Edges:        1 780
Comunidades:  154
EXTRACTED:    100%
Densidade:    ~0.00126 (baixa — esperado em codebase com muita doc)
```

### I.2 Top 10 god-nodes (alta centralidade)

| # | Node | Edges | Tipo | Observação |
|---|------|------:|------|------------|
| 1 | `SDA17Strategy` | 28 | classe | **God class** — candidato a refactor |
| 2 | `BaseModel` | 21 | classe | OK (interface herdada) |
| 3 | `._error_info()` | 21 | método | Aparece em múltiplos modelos (acoplamento p/ erro) |
| 4 | `MessageHandler` (`server/message_handler.py`) | 15 | classe | Bom — chefe de roteamento WS |
| 5 | `simulate_all()` | 14 | função | Em `sim_15_models.py` (script de sim, ok) |
| 6 | `coverage_set()` | 11 | função | Estratégia analítica |
| 7 | `._pct_sigmoid_update()` | 11 | método | Algoritmo central de pesos |
| 8 | `state.json` | 13 | data | Estado de runtime — alto fan-in (revisar contention) |

### I.3 Top comunidades por tamanho

| C# | Tam. | Tipo de conteúdo | Status |
|---:|----:|------------------|--------|
| 63 | 46 | `plano_implentacao_pos_sessao_24_05.md` | ✅ ativo |
| 55 | 45 | `skilss_emelhoras.md` | 🟡 histórico |
| **7** | **43** | **`server/message_handler.py`, `websocket.py`, `main.py`** | ✅ código vivo |
| 1 | 43 | `Manutenabilidade_iso.md` | ✅ doc oficial |
| 56 | 43 | versão final consolidada | 🟡 stale |
| 2,3,4 | 42-43 ea | `melhorias_pos_*`, `pos_implementacao_*`, anotações | 🟡 stale |
| 57 | 39 | `sprint_bugs.md` | 🟡 histórico |
| 5 | 38 | `iso/iec 25010` | ✅ doc oficial |
| 8 | 35 | `scripts/sim_temp/sim_10models.py` | 🟡 script obsoleto? |

**Insight**: 10 das 15 maiores comunidades são documentos `.md` históricos (não código). Mesmo após `organizacao_de_arquivos.md`, persiste cruft no root. Confirma a tese de **archive aggressivo** já planejada.

### I.4 Top arquivos de código por densidade de nodes

| # nodes | Arquivo | Risco |
|--------:|---------|-------|
| 59 | `scripts/sim_temp/sim_15_models.py` | Script único, OK isolar |
| 34 | `state.json` | (dado, não código) |
| **25** | **`strategies/sda17.py`** | **God file** — refactor recomendado |
| 18 | `scripts/sim_temp/sim_10models.py` | Script único |
| **14** | **`server/message_handler.py`** | **Router central** — vigiar coesão |
| 7 | `models/spin_encoder.py` | OK |
| 7 | `strategies/shadow_predictor.py` | OK |

---

## II. Auditoria de Bugs e Melhorias — Software

### II.1 🔴 BUG-AUDIT-1 — Bare-except / except Exception sem contexto em 30+ módulos

**Onde (não-archive, código vivo)**:

| Arquivo | Ocorrências |
|---------|------------:|
| `archive/...` | 600+ (não conta — código morto) |
| **`workers/cdc_worker.py`** | **6** |
| **`database/outbox_integration.py`** | 1 + try/except interno em `maybe_publish_decision_features` (lembrar do bug HISTÓRICO: capturava silentemente) |
| **`database/sqlite_repo.py`** | 1 |
| **`database/outbox_publisher.py`** | 1 |
| **`tools/backfill_decision.py`** | 5 (recém-criado — minha responsabilidade) |
| **`tools/gap_detector.py`** | 7 (recém-criado) |
| **`tools/backtest_from_db.py`** | 71 |
| `strategies/sda17.py` | 1 |
| `server/connection_manager.py` | 3 |
| `server/health_server.py` | 3 |
| `server/message_handler.py` | 1 |
| `state/game.py` | 3 |
| `main.py` | 1 |
| `tests/test_*` | 36 |

**Impacto**: silent-skip de exceções inesperadas mascara bugs (foi exatamente o que causou a perda da decisão 3698 antes do fix H-1). Cada `except Exception:` sem `logger.exception` ou re-raise é um candidato a próximo silent-skip.

**Severidade**: 🔴 **HIGH** (sistêmico).

**Recomendação**: política de lint (`ruff`/`flake8`): proibir `except Exception:` sem `logger.exception(...)` na mesma cláusula. Migrar incrementalmente os 100 lugares mais críticos.

---

### II.2 🟠 BUG-AUDIT-2 — `SDA17Strategy` god class (28 edges)

**Onde**: `strategies/sda17.py` — 25 nodes só dela, 28 edges externas.

**Sintoma**: única classe central de estratégia ativa. Acoplamento elevado dificulta:
- A/B testing de novas estratégias
- Hot-reload sem reiniciar app
- Testes unitários focados

**Recomendação**: extrair pelo menos 3 responsabilidades (decisão de aposta / gerenciamento de gale / persistência de state) em colaboradores. Sprint dedicada.

---

### II.3 🟠 BUG-AUDIT-3 — Senha PG em ferramentas via env mas DSN hardcoded

**Onde**:
- `tools/backfill_decision.py:25-26`
- `tools/gap_detector.py:33-34`

```python
PG_DSN_DEFAULT = "host=roleta-pg user=roleta password={pw} dbname=roleta".format(
    pw=os.environ.get("POSTGRES_PASSWORD", "")
)
```

**Problemas**:
1. Senha entra no string da DSN antes de `psycopg2.connect` — pode vazar em logs/exception chain (psycopg2 redige, mas qualquer wrapper que loggar a DSN bruta vaza).
2. `host=roleta-pg` hardcoded — quebra em ambientes de desenvolvimento.
3. Sem fallback claro se `POSTGRES_PASSWORD` vazio → DSN inválida e mensagem confusa.

**Recomendação**:
```python
PG_DSN_DEFAULT = os.environ.get("ROLETA_PG_DSN") or (
    f"host={os.environ.get('PG_HOST','roleta-pg')}"
    f" user={os.environ.get('PG_USER','roleta')}"
    f" dbname={os.environ.get('PG_DB','roleta')}"
    f" password={os.environ['POSTGRES_PASSWORD']}"  # KeyError explícita
)
```

---

### II.4 🟡 BUG-AUDIT-4 — `state.json` alto fan-in (13 edges)

**Sintoma**: muitos módulos consomem `state.json` direto (não há single source of truth via classe `Repository`).

**Risco**: race conditions em update (não há lock claro). Já houve evidência histórica (`bug-instrument`, `bug-gap-saves`).

**Recomendação**: encapsular leituras/escritas em `state/repository.py` com `fcntl.flock` ou single writer.

---

### II.5 🟡 IMPROVE-AUDIT-1 — Doc cruft no root

10 das 15 maiores comunidades são `.md` históricos. Apesar de `organizacao_de_arquivos.md` ter mapeado o assunto, **nenhum foi movido para `archive/docs-historicos/`** ainda. Tudo continua no root, poluindo o índice Graphify.

**Recomendação**: criar `archive/docs-2026-q2/` e mover ~25 `.md` históricos lá. Manter no root só: `README.md`, `Manutenabilidade_iso.md`, `relatorio_grafi_24.md` (este), `sprints_evolucao_pos_24_05.md` (vigente).

---

## III. Auditoria do Servidor Debian — `187.45.181.75`

### III.1 ✅ Métricas saudáveis

| Recurso | Valor | Status |
|---------|-------|--------|
| Disco `/` | 5.0 G usado de 79 G (7%) | ✅ |
| RAM | 1.4G/6.8G usado + 4G cache, swap 0B | ✅ |
| Load avg | 0.02 / 0.05 / 0.07 | ✅ |
| Containers | 5/5 healthy | ✅ |
| SQLite size | 2.1 MB (3 814 decisions) | ✅ |
| PG size | 11 MB total; outbox 144 kB | ✅ |
| Outbox status | 117 processed, 0 failed, 0 pending | ✅ |
| CDC lag p99 (pós S-I) | 0.01s | ✅ |
| Gap detector | gap=0 sustentado | ✅ |

### III.2 🔴 BUG-SRV-1 — SSH 22 exposto + fail2ban INATIVO + 136 falhas em 1h

**Evidência**:
```
systemctl is-active fail2ban → inactive
ufw → command not found
LISTEN 0.0.0.0:22 (sshd)
136 SSH login failures last hour
```

**Severidade**: 🔴 **CRITICAL**. SSH com password auth ou sem rate-limiting + 136 tentativas/h = brute force ativo. Em poucos dias com listas de usernames comuns, alguma combinação fraca pode ceder.

**Recomendação imediata**:
1. `apt install fail2ban` + jail SSH com `maxretry=5 bantime=1h`.
2. Em `/etc/ssh/sshd_config`: `PasswordAuthentication no`, `PermitRootLogin prohibit-password`, `MaxAuthTries 3`.
3. Instalar `ufw`: allow 22/tcp 80/tcp 443/tcp, deny incoming default.

---

### III.3 🔴 BUG-SRV-2 — wal-g backup NUNCA executou em produção

**Evidência**:
```
crontab -l → apenas: * * * * * /usr/local/bin/roleta-gap-check.sh
ls /var/backups/ → só arquivos do sistema (apt, alternatives)
scripts/walg-backup-daily.sh existe (1343 bytes) mas não está agendado
```

**Severidade**: 🔴 **CRITICAL**. PG sem backup é risco existencial:
- Corruption do volume → perda total dos 3 814 decisions + outbox + ag_label
- `B2 bucket` configurado mas zero `wal-g backup-push` rodou
- Recovery RPO efetivo = **infinito** (nunca houve backup)

**Recomendação imediata**:
1. `install-walg-cron.sh` deve estar em `scripts/` — executar.
2. Cron: `0 3 * * * /root/roleta-cloud/scripts/walg-backup-daily.sh >> /var/log/wal-g/backup.log 2>&1`
3. Validar bucket B2 com `wal-g backup-list` antes de confiar.

---

### III.4 🟠 BUG-SRV-3 — Containers `roleta-cloud` e `roleta-pg` rodam como root

**Evidência**:
```
roleta-cloud: User= (vazio = root)
roleta-pg:    User= (vazio = root)
roleta-cdc-worker: User=worker ✅
```

**Severidade**: 🟠 HIGH. Escape de container = root no host. CDC já corrige (User=worker). Falta replicar.

**Recomendação**: Dockerfile do `roleta-cloud` adicionar `USER nobody` (ou criar `app:1000`). Idem PG (mas a imagem oficial já tem `postgres`; verificar override do compose).

---

### III.5 🟡 IMPROVE-SRV-1 — Sem TLS na porta 443 verificado

`nginx` está em 80/443 mas não validamos se cert é válido (Let's Encrypt? auto-renew?). Verificar:
```bash
curl -vIk https://localhost 2>&1 | grep -E "subject|expire|TLS"
certbot certificates
```

---

### III.6 🟡 IMPROVE-SRV-2 — Sem alerta Prometheus para `decisions_outbox_gap`

S-M0 deixou a métrica em Grafana Cloud, mas **nenhum alert rule** foi criado.

**Recomendação**: Grafana Cloud Alerting:
```promql
decisions_outbox_gap{lookback="60m"} > 0
FOR 2m
```
Notificação: e-mail / webhook.

---

## IV. Segunda Auditoria — Bugs/Melhorias adicionais (re-pass)

### IV.1 🟠 BUG-AUDIT2-1 — `roleta-cdc-worker` reinício perde `cdc_idle_stats`

`_notify_received_total` e `_notify_wakeups_total` são variáveis de módulo Python (não Prometheus). Reinício zera. Métrica observacional só visível no log.

**Fix**: expor via prometheus_client Counter em `cdc_worker` + endpoint `/metrics`. Já há precedente em `roleta-cloud`.

### IV.2 🟠 BUG-AUDIT2-2 — `_setup_listen` sem teste de pg_notify recebido

Hoje: `LISTEN outbox_new;` retorna OK mas se trigger SQL não existisse no PG (ex.: ambiente novo sem migration 007), `select.select` ficaria timeoutando para sempre — fallback degrada para polling SILENTE.

**Fix**: na inicialização, `SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='trg_outbox_notify')` — se não existe, log `error` e seguir polling com `_notify_received_total = -1` (sentinela).

### IV.3 🟠 BUG-AUDIT2-3 — Wrapper M-1 ignora código de saída != 0 e ainda escreve prom file

Em `roleta-gap-check.sh`:
```bash
if [ "$RC" -le 1 ] && command -v jq ...
```

Aceita `rc=0` E `rc=1`. Mas `rc=1` (gap detectado) é EXATAMENTE quando precisamos do prom textfile com gap > 0. OK, está certo. **Falso alarme — não é bug.** ✅ verificar.

### IV.4 🟡 IMPROVE-AUDIT2-1 — Migrations sem alembic stamp para 007

`migrations/007_outbox_notify_trigger.sql` é SQL puro, fora do alembic em `migrations/versions/`. Pode causar drift se novo ambiente roda `alembic upgrade head` — o trigger não vai existir.

**Fix**: converter 007 em revision alembic (`alembic revision -m "outbox notify trigger"` + `op.execute(sql)`).

### IV.5 🟡 IMPROVE-AUDIT2-2 — `.dockerignore` agora inclui `tools/`. Mas e `scripts/sim_temp/`?

`scripts/sim_temp/sim_15_models.py` tem 59 nodes (maior arquivo de código). Provavelmente nunca é executado em produção. Está sendo copiado para o container?

**Fix**: re-incluir `scripts/sim_temp/` em `.dockerignore` (libera ~50 KB e remove vetor de execução acidental).

### IV.6 🟡 IMPROVE-AUDIT2-3 — `decisions.db` 2.1 MB e cresce indefinidamente

Não há rotação/archive de decisions antigas. Em 1 ano serão ~30 MB (não crítico mas vale política).

**Fix**: `tools/archive_old_decisions.py` que move `> 90 dias` para `decisions_archive.db` mensalmente.

### IV.7 🔴 BUG-AUDIT2-4 — Senha PG `CsUbgqaA...` aparece em vários commits/logs

Pesquisa rápida sugere a senha em scripts deploy (.tmp_*.sh) e foi enviada via SSH em comandos one-liner que vão para `~/.bash_history` do servidor. **Não é segredo de fato.**

**Severidade**: 🔴 HIGH (privilege boundary já furada).

**Fix**:
1. Rotacionar senha PG (`ALTER USER roleta WITH PASSWORD '...'` + atualizar `.env`/Docker secrets).
2. Mover de env-var para Docker secret (`/run/secrets/pg_password`).
3. `~/.bash_history` no servidor → `history -c && history -w`.

---

## V. Pontos Fortes Confirmados pelo Grafo

- `MessageHandler` (15 edges) é router coeso, não god.
- `BaseModel` interface limpa herdada por modelos (encoder, predictor).
- Migration history rastreável (`0001_baseline`, `0002_strategy_versions`, `0003_vector_schema`, `0004_outbox`, `007_outbox_notify_trigger`).
- Pasta `archive/` está fazendo trabalho — ~80% dos bare-except estão lá (código morto).
- CDC + Outbox + LISTEN/NOTIFY → arquitetura de eventos saudável (S-I rodando p99 0.01s).
- Observability stack completa (grafana-agent → Prometheus Cloud + Loki Cloud + node-exporter).

---

## VI. Próximas Sprints (consolidadas após dupla auditoria)

> Cada sprint segue padrão **O QUÊ / COMO / POR QUÊ** para execução determinística.

### Sprint **S-SEC-1** (CRÍTICA, hoje/24h)

**O QUÊ**: bloquear superfície SSH + ativar wal-g em produção.

**COMO**:
1. `apt update && apt install -y fail2ban ufw`
2. `/etc/fail2ban/jail.d/sshd.local`:
   ```
   [sshd]
   enabled = true
   maxretry = 5
   bantime = 1h
   findtime = 10m
   ```
3. `/etc/ssh/sshd_config`: `PasswordAuthentication no`, `MaxAuthTries 3`, `LoginGraceTime 30`, `PermitRootLogin prohibit-password`. **ATENÇÃO**: testar key auth antes!
4. `ufw default deny incoming; ufw allow 22; ufw allow 80; ufw allow 443; ufw enable`.
5. Cron wal-g: `0 3 * * * /root/roleta-cloud/scripts/walg-backup-daily.sh >> /var/log/wal-g/backup.log 2>&1`.
6. Validar bucket: `docker exec roleta-pg wal-g backup-list` (deve listar ≥1 após 24h).
7. Rotacionar senha PG (BUG-AUDIT2-4) — `ALTER USER` + atualizar `.env`.

**POR QUÊ**: 136 SSH failures/h sem fail2ban + zero backup PG = risco existencial diário. Rotacionar senha porque exposta em bash_history e scripts temporários.

---

### Sprint **S-LOG-1** (ALTA, 1-2 dias)

**O QUÊ**: política anti-silent-skip nos 8 módulos vivos críticos.

**COMO**:
1. Adicionar regra em `pyproject.toml` (ruff): `BLE001` no try/except sem `logger.exception`.
2. Refatorar **prioritariamente**:
   - `database/outbox_integration.py` (já feito em parte por H-1)
   - `database/sqlite_repo.py`
   - `workers/cdc_worker.py` (6 ocorrências)
   - `tools/backfill_decision.py` + `gap_detector.py` (recém-criados; adicionar `logger.exception`)
   - `state/game.py`
   - `server/{connection_manager,health_server,message_handler}.py`
3. Em cada `except`: `logger.exception("<contexto> id=%s", id)` ou re-raise com chain.
4. CI fail se regra violada.

**POR QUÊ**: silent-skip causou perda da decisão 3698. Política impede regressão sistêmica.

---

### Sprint **S-OBS-2** (MÉDIA, 1 dia)

**O QUÊ**: completar observability — alertas + métricas CDC nativas.

**COMO**:
1. Em `workers/cdc_worker.py`: substituir `_notify_received_total` (variável módulo) por `prometheus_client.Counter("cdc_notify_received_total")`. Expor `/metrics` em porta nova (8767) ou via push para grafana-agent.
2. Adicionar scrape `cdc-worker` ao grafana-agent.
3. Grafana Cloud Alerting:
   - `decisions_outbox_gap > 0 for 2m` → e-mail
   - `rate(outbox_hook_skipped_total[5m]) > 0` → e-mail
   - `cdc_notify_received_total == 0 for 10m AND outbox_added_count > 0` → indica NOTIFY quebrou
4. Dashboard "Roleta Cloud — Live Health" com:
   - lag p50/p95/p99
   - gap por janela
   - taxa de decisões/min
   - status de containers

**POR QUÊ**: hoje S-I funciona mas regressão silenciosa passa despercebida (se trigger SQL sumir, fallback poll com p99 voltando a 28s ninguém saberia).

---

### Sprint **S-MIG-1** (MÉDIA, meio dia)

**O QUÊ**: padronizar migration 007 em alembic e adicionar guard no startup.

**COMO**:
1. `alembic revision -m "outbox notify trigger" --autogenerate=false`
2. Mover SQL de `migrations/007_outbox_notify_trigger.sql` para o `upgrade()` da nova revision.
3. `downgrade()`: DROP TRIGGER + DROP FUNCTION.
4. Em `cdc_worker._setup_listen`: antes do `LISTEN`, verificar `pg_trigger` (BUG-AUDIT2-2).
5. `alembic upgrade head` na inicialização do `cdc-worker` (entrypoint).

**POR QUÊ**: novos ambientes precisam do trigger; SQL standalone vai ser esquecido.

---

### Sprint **S-CLEAN-1** (BAIXA, 2h)

**O QUÊ**: limpar repo + .dockerignore.

**COMO**:
1. `mkdir -p archive/docs-2026-q2 && git mv {sprint_bugs,skilss_emelhoras,pos_implementacao_*,sessao13_*,valid_pos_task_*,plano_implentacao_pos_sessao_24_05}.md archive/docs-2026-q2/`
2. `.dockerignore` adicionar: `scripts/sim_temp/`, `archive/`, `*.md` (exceto README.md), `relatorio_grafi_24.md`.
3. Rebuild container e validar tamanho reduzido.
4. Re-rodar `graphify update .` para confirmar comunidades agora dominadas por código.

**POR QUÊ**: Graphify mostra 10/15 comunidades top sendo .md históricos — sinal de noise no índice e na imagem Docker.

---

### Sprint **S-REFAC-1** (PLANNING, 1 semana)

**O QUÊ**: refactor `SDA17Strategy` (god class 28 edges).

**COMO**:
1. Extrair `BetSizer` (cálculo de stake / gale).
2. Extrair `StrategyStateStore` (persistência em SQLite/state.json).
3. Manter `SDA17Strategy` como orquestrador fino chamando colaboradores.
4. Testes unitários cobrindo cada colaborador antes de remover código antigo.
5. Feature flag `STRATEGY_V2_SDA17=1` para ligar versão nova; rollback rápido.

**POR QUÊ**: hoje qualquer mudança em SDA17 toca 28 outros pontos. Bloqueia A/B testing de novas estratégias e dificulta hot-reload.

---

### Sprint **S-DATA-1** (BAIXA, meio dia)

**O QUÊ**: rotação de `decisions.db`.

**COMO**:
1. `tools/archive_old_decisions.py` que move `WHERE timestamp < datetime('now','-90 days')` para `decisions_archive.db`.
2. Cron mensal: `0 5 1 * * /usr/local/bin/archive-decisions.sh`.
3. Validar índices reconstruídos no DB principal pós-vacuum.

**POR QUÊ**: prevenção; não crítico hoje (2.1 MB).

---

## VII. Priorização recomendada (DAG)

```
S-SEC-1  (hoje)  ──► S-LOG-1  ──► S-OBS-2  ──► S-MIG-1
       \                                    /
        └────── S-CLEAN-1 (paralelo) ──────┘
                                            
S-REFAC-1 (depende de S-LOG-1)
S-DATA-1  (qualquer hora)
```

**Sequência ótima desta sessão (próxima)**: S-SEC-1 (1-2h) → S-OBS-2 (alerts, 30min) → S-MIG-1 (alembic, 30min) → S-CLEAN-1 (cleanup, 30min).

---

## VIII. Métricas-objetivo pós-sprints

| KPI | Hoje | Alvo pós-S-SEC-1 | Alvo pós-S-LOG-1 | Alvo pós-S-OBS-2 |
|-----|------|------------------|------------------|------------------|
| SSH brute-force/h | 136 | < 5 (banidos) | — | — |
| Backups PG nos últimos 7d | 0 | 7 | — | — |
| Bare-except em código vivo | 30+ | — | < 5 | — |
| MTTR (lag regressão) | manual | — | — | < 5 min (alert) |
| god-class refactor | 0 | — | — | — |

---

## IX. Apêndice — Comandos de validação rápida

```bash
# após S-SEC-1
ssh root@187.45.181.75 'fail2ban-client status sshd | head -10; ufw status; ls -lah /var/log/wal-g/'

# após S-OBS-2
ssh root@187.45.181.75 'curl -s http://localhost:8767/metrics | grep cdc_notify'

# após S-MIG-1
ssh root@187.45.181.75 'docker exec roleta-pg psql -U roleta -d roleta -tAc "SELECT 1 FROM pg_trigger WHERE tgname=''trg_outbox_notify''"'

# após S-CLEAN-1
ls *.md | wc -l   # esperar <= 4
docker images roleta-cloud-roleta-cloud --format "{{.Size}}"
```

---

**FIM do relatório.** Auditoria dupla aplicada. 4 achados CRÍTICOS, 5 ALTOS, 6 MÉDIOS/BAIXOS. 7 sprints novas priorizadas via DAG.

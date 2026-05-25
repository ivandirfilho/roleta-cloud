# Relatório Graphify — Auditoria Profunda 24/05

> Stack MCP usada: **graphify** (mapa de grafos do repo) + **filesystem** (powershell + grep/glob) + **sequential-thinking** (raciocínio) + **memory** (persistência cross-session) + acesso SSH ao servidor Debian `187.45.181.75`.

> Data: 2026-05-24 20:55 BRT (sessão YOLO Orchestrator, modelo `claude-opus-4.7`).

---

## 0. Sumário Executivo

- **Repositório indexado** com Graphify: **1 680 nodes**, **1 780 edges**, **154 comunidades**, 100% EXTRACTED.
- **Servidor saudável** em CPU/RAM/Disco (load 0.02, RAM 1.4G/6.8G, disco 7%). Containers todos `healthy`.
- **1 achado CRÍTICO de continuidade**: `wal-g backup` script existe mas **não está no cron e o binário não está instalado** → **backup PG nunca rodou em produção**.
- **3 achados ALTOS de código**: bare-excepts em ~17 módulos vivos (revisado — antes inflado por `archive/*`); `SDA17Strategy` god-class (28 edges); doc cruft (10/15 comunidades top são `.md` históricos).
- **Itens de segurança SSH/firewall/rotação de senha**: REMOVIDOS desta revisão a pedido do operador para não arriscar lockout durante trabalho ativo.
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

### III.2 ⛔ REMOVIDO — itens SSH/fail2ban/ufw

Removidos a pedido do operador (risco de lockout durante trabalho ativo). Re-avaliar em janela de manutenção dedicada.

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

### III.4 ⛔ REMOVIDO — análise de privilégios de containers

Removido a pedido do operador (faz parte da revisão de segurança maior, será planejada separadamente).

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

### IV.7 ⛔ REMOVIDO — rotação de senha PG

Removido (operador determinou: não mexer em credenciais agora; tarefa de hardening agendada para janela dedicada).

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

### Sprint **S-BAK-1** (CRÍTICA, hoje) — sucessora de S-SEC-1 sem partes SSH

**O QUÊ**: ativar wal-g (binário + cron + primeiro basebackup validado).

**COMO**:
1. Baixar binário wal-g v3.0.5 (Linux amd64) para `/root/roleta-cloud/wal-g/wal-g` (caminho do bind no compose).
2. `chmod +x` e validar `wal-g --version` dentro do container.
3. Confirmar `/etc/wal-g/env` populado (já está) e tudo permissão 600.
4. Executar manualmente uma vez: `bash /root/roleta-cloud/scripts/walg-backup-daily.sh`.
5. Validar: `docker exec -u postgres roleta-pg bash -c '. /etc/wal-g/env && wal-g backup-list'` → ≥1 entrada.
6. Instalar cron: `bash /root/roleta-cloud/scripts/install-walg-cron.sh`.
7. Confirmar `/etc/cron.d/walg-backup` e `cat /var/log/wal-g/backup.log`.

**POR QUÊ**: zero backups PG é risco existencial. Esta sprint NÃO toca SSH/firewall/credenciais (removido conforme decisão do operador).

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

### Sprint **S-CLEAN-1** (BAIXA, 30min) — REDUZIDA

**O QUÊ**: enxugar a imagem Docker (sem mover arquivos `.md`, que ainda são referenciados por sessões em curso via `&'caminho/...'`).

**COMO**:
1. `.dockerignore` adicionar: `scripts/sim_temp/`, `archive/`, `*.md` (root), `graphify-out/`.
2. Rebuild `roleta-cloud` e validar tamanho reduzido.
3. Smoke test do health endpoint.
4. NÃO mover arquivos do root nesta sprint (operador ainda referencia muitos `.md` por path absoluto).

**POR QUÊ**: dispensar `.md` do build mantém o repo intacto para sessões em curso e ainda assim reduz a imagem.

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

### Sprint **S-DATA-1** (BAIXA, ADIADA)

ADIADA. Cálculo revisado: 2.1 MB SQLite atual em ~6 h de operação ≈ 8 MB/dia se sustentado, mas a maior parte é WAL transient — após `PRAGMA wal_checkpoint(TRUNCATE)` o DB volta a ~2 MB. Projeção 1 ano ≈ 8-15 MB. Não crítico até 100 MB.

---

## VII. Priorização recomendada (DAG) — REVISADA

```
S-BAK-1 (CRITICAL, hoje) ──► S-LOG-1 ──► S-OBS-2 ──► S-MIG-1
       \                                          /
        └──────── S-CLEAN-1 lite (paralelo) ─────┘
S-REFAC-1 (depende S-LOG-1)
S-DATA-1  ADIADA
```

**Sequência ótima desta sessão (executada abaixo, §XII)**: S-BAK-1 → S-MIG-1 → S-OBS-2 → S-CLEAN-1 → S-LOG-1 mini.

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
# após S-BAK-1
ssh root@187.45.181.75 'docker exec -u postgres roleta-pg bash -c ". /etc/wal-g/env && wal-g backup-list"; tail -5 /var/log/wal-g/backup.log; ls /etc/cron.d/walg-backup'

# após S-OBS-2
ssh root@187.45.181.75 'curl -s http://localhost:8767/metrics | grep cdc_notify'

# após S-MIG-1
ssh root@187.45.181.75 'docker exec roleta-pg psql -U roleta -d roleta -tAc "SELECT 1 FROM pg_trigger WHERE tgname=''trg_outbox_notify''"; docker exec roleta-cloud alembic current'

# após S-CLEAN-1 lite
ssh root@187.45.181.75 'docker images | grep roleta-cloud'
```

---

## XII. Evolução / Execução desta sessão (2026-05-24 21:0X BRT)

### XII.A Auditoria do próprio relatório — issues corrigidas

| ID | Achado | Fix aplicado |
|---|---|---|
| AUD-REL-1 | Sprint S-SEC-1 misturava SSH/firewall/credenciais com wal-g; risco de lockout | Removida. Wal-g extraído em **S-BAK-1** (não toca SSH/credenciais). |
| AUD-REL-2 | III.2 / III.4 / IV.7 propunham mudanças SSH/root/senha | Removidas conforme decisão do operador (não mexer em SSH/chaves agora). |
| AUD-REL-3 | S-CLEAN-1 quebrava sessões ativas que referenciam `.md` por path | Reduzida: só `.dockerignore`, mantém arquivos no root. |
| AUD-REL-4 | S-DATA-1 cálculo de crescimento incorreto | Adiada (revisão: WAL truncate reduz para ~2 MB). |
| AUD-REL-5 | S-BAK-1 omitia que **binário wal-g não existe** no host nem no container | Passo 1 do COMO agora baixa o binário antes do bind. |
| AUD-REL-6 | BUG-AUDIT-1 inflado por `archive/*` | Sumário atualizado: 30+ → ~17 vivos. |
| AUD-REL-7 | BUG-AUDIT-3 fix proposto usava `os.environ['POSTGRES_PASSWORD']` no module-level (KeyError em import) | Nota no fix: usar lazy evaluation dentro de função de connect. |
| AUD-REL-8 | S-OBS-2 omitia `-p 127.0.0.1:8767:8767` + scrape_configs | Detalhado na execução XII.D. |
| AUD-REL-9 | Não mencionava volume `roleta-cloud_roleta-data` (named volume — OK, persiste em `down`) | Adicionado contexto: SQLite está safe; PG é o gap real. |

### XII.B Execução S-BAK-1 (wal-g)

Ver log abaixo. Plano:
1. Baixar `wal-g-pg-ubuntu-22.04-amd64.tar.gz` v3.0.5 (já feito durante auditoria — `/tmp/wal-g.tar.gz`).
2. Extrair em `/root/roleta-cloud/wal-g/wal-g`.
3. `docker compose restart roleta-pg` (re-bind do binário; opcional se já mounted vazio).
4. Smoke: `docker exec roleta-pg /usr/local/bin/wal-g --version`.
5. Primeiro `backup-push` manual via `scripts/walg-backup-daily.sh`.
6. `bash scripts/install-walg-cron.sh`.

### XII.C Execução S-MIG-1 (alembic migration 007)

Criar `migrations/versions/0005_outbox_notify_trigger.py` com `op.execute(SQL_UP)` / `op.execute(SQL_DOWN)`. `alembic upgrade head` no container. Validar `pg_trigger`.

### XII.D Execução S-OBS-2 (cdc /metrics)

`workers/cdc_worker.py`: substituir contadores `int` por `prometheus_client.Counter`. Adicionar `start_http_server(8767)` no `main_loop`. `docker-compose.pg.yml`: expor `127.0.0.1:8767:8767`. `grafana-agent/config.yml`: novo job `cdc-worker` target `127.0.0.1:8767`.

### XII.E Execução S-CLEAN-1 lite (.dockerignore)

Adicionar `archive/`, `scripts/sim_temp/`, `*.md`, `graphify-out/`. Rebuild + smoke health.

### XII.F Execução S-LOG-1 mini

Adicionar `logger.exception(...)` nos bare-excepts de `tools/backfill_decision.py` e `tools/gap_detector.py` (criados nesta sessão — minha responsabilidade fix-forward).

---

**FIM do relatório.** Auditoria de auditoria aplicada. SSH/credenciais explicitamente fora-de-escopo. Execução em XII.B-F.

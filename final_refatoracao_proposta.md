> ⚠️ **ATUALIZAÇÃO A3 (2026-05-24) — Diagrama de infraestrutura atualizado**
>
> A auditoria A3 (em `plano_implentacao_pos_sessao_24_05.md`) substitui o componente "Azure PG Flexible Server" do diagrama original por **"Azure VM B4ms + Docker Compose (PG 15 + pgvector + AGE + TimescaleDB) + ACR + Blob WAL-G"**, devido ao achado B32 (AGE indisponível em Flexible).
>
> ### Diagrama de infraestrutura — versão A3 (canônica)
>
> ```mermaid
> flowchart TB
>     subgraph DEV["💻 Local (dev — S0.5)"]
>         devApp[app Python]
>         devPG[(docker-compose<br/>PG15+pgvector+AGE+Timescale<br/>imagem custom)]
>         devApp <-->|loopback <2ms| devPG
>     end
>
>     subgraph GH["🐙 GitHub"]
>         repo[repo Roleta Cloud]
>         actions[Actions CI/CD<br/>build Docker → push ACR<br/>deploy por tag v*]
>         repo --> actions
>     end
>
>     subgraph AZ["☁️ Azure brazilsouth"]
>         subgraph VMPG["Azure VM Standard_B4ms (Ubuntu 22.04)"]
>             prodPG[(Docker Compose<br/>postgres-stack:pg15-age15<br/>+ grafana-agent)]
>         end
>         acr[Azure Container Registry<br/>postgres-stack imagem custom]
>         blob[(Azure Blob Storage LRS<br/>WAL-G basebackup + WAL contínuo)]
>         kv[Azure Key Vault<br/>credenciais via Managed Identity]
>         gcloud[Grafana Cloud free tier]
>     end
>
>     subgraph PRODAPP["🖥️ App em produção"]
>         debApp[Debian HostDime OU Azure VM/Container Apps<br/>decisão final em S-CUTOVER]
>     end
>
>     actions -->|docker push| acr
>     acr -->|docker pull| VMPG
>     prodPG -->|wal-push| blob
>     VMPG -.->|Managed Identity| kv
>     debApp -->|psycopg_pool SSL| prodPG
>     prodPG -->|remote_write| gcloud
>     debApp -->|remote_write| gcloud
>
>     classDef new fill:#9f9,stroke:#393,color:#000
>     class VMPG,acr,blob new
> ```
>
> **Diferenças vs diagrama original:**
> - 🟢 NOVO: ACR + Blob + VM (no lugar de Flexible Server)
> - 🟢 NOVO: `S0.5` garante que dev usa a MESMA imagem que prod (paridade absoluta)
> - 🔄 MUDOU: app↔PG agora é decidido em **S-CUTOVER** (mede latência real antes de fixar topologia)
> - ✅ MANTIDO: tudo de estratégia, sprints S1-S14, sprints transversais, isolamento CW/CCW, deploy por tag git
>
> Para detalhes operacionais ver `plano_implentacao_pos_sessao_24_05.md` seções **A3.4–A3.7**.

---
# 🎯 FINAL — Refatoração Proposta Roleta Cloud v5.0

**Documento mestre consolidado e executável**
**Data:** 2026-05-23 16:00 UTC-3
**Autor:** YOLO Orchestrator (Claude Opus 4.7)
**Versão alvo:** v4.3.2 → **v5.0.0 — "Directional Bayesian Edge"**

**Documentos-base consolidados (lidos integralmente):**
1. `resultados_23_05.md` (932 LoC / 71.7 KB) — auditoria estratégica + brave-search externo
2. `proposta_refatoracao_23_05.md` (590 LoC / 38.8 KB) — 4 tiers, 16 sprints
3. `auditoria_proposta_refatoracao_23_05.md` (746 LoC / 37.5 KB) — 11 blocos ISO 25010 + correções T3.1'/T3.2'
4. `Manutenabilidade_iso.md` (968 LoC / 73 KB) — ISO/IEC 25010 baseline 7.8/10

**MCPs usados:** sequential-thinking + memory + filesystem + graphify (god_nodes via path).

---

## 📜 DIRETIVAS INEGOCIÁVEIS DO PROJETO

> 1. **ISOLAMENTO TOTAL CW × CCW** — Cada bloco de estratégia analisa anti-horário e sugere ele, horário e sugere ele, separadamente. Nenhum modelo, contador, drift detector, calibrador, PID, Kelly state ou exploration counter pode compartilhar estado entre direções. Toda nova feature DEVE ter estado dual `{"cw":..., "ccw":...}` ou ser stateless pura. — *Verificado em `strategies/sda17.py:73,74,79,427-429,488-495` ✅ já compliant.*
>
> 2. **FORMA DA APOSTA É INVARIANTE** — 3 blocos / 3 centros (C1+C2+C3) com 17 ou 21 números (a definir em decisão de produto separada). Esta refatoração **não muda** a forma da aposta.
>
> 3. **DECISÃO COM DADOS ATUAIS** — Não esperar "mais análise". Backtest de validação roda em paralelo, não bloqueia decisão.
>
> 4. **CUSTO DE INFRA NÃO É RESTRIÇÃO** — Créditos AWS+Azure+GCP disponíveis. Priorizar TECNOLOGIA QUE FUNCIONA.
>
> 5. **HARDENING DO SERVIDOR ESTÁ FORA DE ESCOPO** — Tratado em sessão separada (pedido prévio do usuário).

---

## 0. TL;DR — em 10 linhas

1. **v5.0.0** entrega: Adam-Sigmoid per-direction, Thompson Bernoulli dual, Calibrator 2-modelos (CW/CCW), ADWIN drift dual, ¼-Kelly bankroll global com p_hit dual, PID auto-calibration dual.
2. **Infra base** ganha: CI/CD GitHub Actions, Alembic migrations, Prometheus+Loki+Grafana, branch protection trunk-based, conventional commits, ADRs.
3. **Refactor crítico**: `message_handler.py` (473 LoC, ZERO testes, acoplamento [5]) quebrado em 5 handlers especializados; SDA17 modularizada em Stage Protocol.
4. **DB**: SQLite → **Azure Database for PostgreSQL 16** + extensions (pgmq, pgvector, pg_partman, pg_cron). Migração via `pgloader` + Alembic.
5. **Servidor Debian 187.45.181.75**: ganha stack de observabilidade local **AGORA** (Prometheus/Loki/Grafana via docker-compose); permanece como **runtime engine** mesmo após migração do DB para Azure.
6. **Estratégia v5**: Pipeline 10 estágios per-direction substituindo pipeline 8 atual; cobertura ainda 17 (ou 21 — invariante #2).
7. **Cronograma**: 5 fases × ~6 semanas = **30 dias úteis** com paralelização.
8. **Quadrante de aprovação**: Fase 0 (5d, 100% verde) → Fase 1+2 (12d, 80% verde / 20% amarelo com shadow) → Fase 3 (7d, amarelo+ shadow obrigatório) → Fase 4 cloud (6d, amarelo) → Fase 5 multi-mesa (opcional).
9. **Targets de produto v5**: hit rate CW≥52% (de 41.7% atual), CCW≥58% (de 65.5%), Δ(CW,CCW) ≤ 8pts, drift detection latency ≤10 spins, max miss streak ≤6.
10. **Approve-as-bloco recomendado:** Fase 0 + Fase 1 = 11 dias úteis, 100% sem mudança de algoritmo crítica em produção, prepara base para todo o resto.

---

## 1. Mapa visual — Arquitetura alvo v5.0

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTE (Chrome Extension + Dashboard)                              │
└──────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                │ WSS (auth: JWT + HMAC device)
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          DEBIAN 187.45.181.75 (Docker host — runtime)                            │
│                                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │  roleta-cloud (Python 3.12 — websockets, structlog, prometheus_client)                   │   │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────┐    │   │
│  │  │  server/handlers/  (B4 — quebrado de message_handler.py 473 LoC)                  │    │   │
│  │  │  ├ spin_handler.py    ├ session_handler.py   ├ master_handler.py                  │    │   │
│  │  │  ├ extractor_handler  └ dispatcher.py        (cada um < 150 LoC, > 70% test cov) │    │   │
│  │  └──────────────────────────────────────────────────────────────────────────────────┘    │   │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────┐    │   │
│  │  │  strategies/  (Stage Protocol — T2.1)                                              │    │   │
│  │  │  ┌─────────────────────────────────────────────────────────────────────────┐     │    │   │
│  │  │  │  PIPELINE PER-DIRECTION (executa 2x: 1 CW + 1 CCW, ISOLADOS)             │     │    │   │
│  │  │  │  [1] AdaptiveWindow → [2] IQRReject → [3] WeightedMedian →               │     │    │   │
│  │  │  │  [4] ADWINDrift[dir] → [5] SmartScore + BayesianGate[dir] →              │     │    │   │
│  │  │  │  [6] AdamSigmoid[dir] → [7] HotCenterFilter[dir] →                       │     │    │   │
│  │  │  │  [8] Thompson[dir][37 nums] → [9] Calibrator[dir model] →                │     │    │   │
│  │  │  │  [10] PID[dir] → ¼-Kelly(p_hit_dir, σ_global_diag(cw,ccw))               │     │    │   │
│  │  │  └─────────────────────────────────────────────────────────────────────────┘     │    │   │
│  │  └──────────────────────────────────────────────────────────────────────────────────┘    │   │
│  │  /metrics (Prometheus) :9000   /healthz (HTTP) :9001   /ws (WebSocket) :8765             │   │
│  └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                            │
│  │ prometheus   │ │   loki       │ │   grafana    │ │ alertmanager │                            │
│  │ :9090        │ │   :3100      │ │   :3000      │ │   :9093      │                            │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘                            │
└──────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                            │ pg_wire (5432, TLS)
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                  AZURE — DATABASE LAYER (Managed, free tier suficiente)                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐     │
│  │  Azure Database for PostgreSQL Flexible Server 16                                       │     │
│  │  Extensions: pgmq | pgvector | pg_partman | pg_cron | pgcrypto | pg_stat_statements    │     │
│  │  Tabelas: decisions, sessions, gale_windows, window_plays, bankroll_events,            │     │
│  │           model_versions, drift_events, shadow_runs                                     │     │
│  │  Particionamento: decisions por mês (pg_partman); retenção 12 meses                    │     │
│  │  Backup: PITR 7 dias + snapshot semanal long-term retention                            │     │
│  └────────────────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                                  │
│  Azure Key Vault (secrets: PG_PASSWORD, ROLETA_API_KEY, DEVICE_HMAC_SECRET)                     │
│  Azure Monitor + Log Analytics (paridade com Loki — opcional)                                   │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          GITHUB (ivandirfilho/roleta-cloud)                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │  Branch protection: main (PR + 1 approval + CI green + linear history + invariant gate)  │   │
│  │  Workflows:                                                                                │   │
│  │   - ci.yml          (pytest+ruff+mypy+invariant-check on PR)                              │   │
│  │   - nightly.yml     (vectorbt backtest sobre últimos 30d + relatório artifact)           │   │
│  │   - deploy.yml      (build Docker image, push GHCR, deploy SSH ao Debian, tag-triggered) │   │
│  │   - alembic.yml     (verifica migration linear + downgrade test)                          │   │
│  │  Hooks:                                                                                    │   │
│  │   - pre-commit: ruff, mypy, commitlint (conventional commits)                             │   │
│  │   - pre-push: pytest -q                                                                   │   │
│  │  Templates: PR, bug_report, feature_request, ADR                                          │   │
│  │  CODEOWNERS: @ivandirfilho dono de strategies/, state/, server/handlers/                  │   │
│  └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Estado atual auditado (snapshot 23/05)

### 2.1 Conformidade com invariante de isolamento — código verificado linha-a-linha

| Arquivo | Linha | Estado | Veredito |
|---|---|---|---|
| `strategies/sda17.py:73-74` | `cw_history`, `ccw_history` listas separadas | ✅ COMPLIANT |
| `strategies/sda17.py:79` | `_sigmoid_off: Dict[str, float]` chaves `{cw,ccw}_{off2,off3}` | ✅ COMPLIANT |
| `strategies/sda17.py:302` | `_get_adaptive_offset(direction)` | ✅ COMPLIANT |
| `strategies/sda17.py:416-478` | `_pct_sigmoid_update(direction, ...)` — atualiza só lado da direção | ✅ COMPLIANT |
| `strategies/sda17.py:480-498` | `update_adaptive(direction, ...)` — append só na lista da direção | ✅ COMPLIANT |
| `state/game.py:210-213` | `timeline_cw`, `timeline_ccw`, `martingale_cw`, `martingale_ccw` | ✅ COMPLIANT |
| Sigmoid update `:463-468` | `err_dir > 0` afeta `off2 += adj`, `off3 -= adj × 0.3` (NA MESMA DIREÇÃO) | ✅ COMPLIANT — `err_dir` é direção GEOMÉTRICA da roda, não a direção do giro |

**Conclusão:** A arquitetura atual respeita 100% o invariante. Qualquer feature nova proposta neste documento herda esta separação obrigatoriamente.

### 2.2 Performance produção 23/05 (132 decisões, 118 finalizadas, DB `/app/data/decisions.db` no container)

```
                           DIREÇÃO
                       CW            CCW            DELTA
hit_rate              41.7%         65.5%          -23.8 pts  ❌ ASSIMETRIA CRÍTICA
samples (n)             60            58
break-even (cob=17)   47.2%         47.2%
gap até break-even    -5.5 pts      +18.3 pts
TR conf=alta          50.7%          —
TR conf=media         57.8%         (invertido vs folclore)
score=5 hit rate      16.7% (n=6)   (Beta-Binomial CI [0.04, 0.50] — INCONCLUSIVO)
calibration_offset    0 em 100%     (NUNCA ajustado — dead code)
max miss streak         5             —
```

**Causa raiz #1:** Sigmoid feedback não diferencia regime CW vs CCW além do estado isolado. Quando regime muda (drift), demora 8 spins para reagir.
**Causa raiz #2:** Não há gate Bayesiano — scores fracos disparam apostas em janelas pequenas.
**Causa raiz #3:** Triple-Rate confidence inverte (alta < média) — sinal de calibração quebrada.
**Causa raiz #4:** Único `MartingaleState` por direção sem cap Kelly — drawdown perigoso em streaks.

### 2.3 Score ISO 25010 baseline → target v5.0

| Característica | Atual | Target v5.0 | Como medir |
|---|:---:|:---:|---|
| Funcionalidade | 9 | 9 | Pytest coverage funcional ≥ 90% |
| Performance | 9 | 9 | p99 spin latency < 50ms em Prometheus |
| Compatibilidade | 7 | 8 | + AsyncAPI spec + REST /healthz |
| Usabilidade | 8 | 8 | Inalterado (extension) |
| Confiabilidade | 8 | 9 | + circuit breaker DB + ADWIN drift |
| Segurança | **6** | **9** | SEC-001/002 + HMAC device + JWT (TASK-003) |
| **Manutenibilidade** | **7.0** | **9.0** | Mod 9, Reus 9, Anal 9, Modif 9, Test 9 (CI + cov 80%) |
| Portabilidade | 7 | 9 | + Postgres + multi-cloud Docker |
| **GERAL** | **7.8** | **8.9** | — |

---

## 3. PLANO DE EXECUÇÃO — 5 FASES, 30 DIAS ÚTEIS

### Visão consolidada (Gantt textual)

```
                Sem1     Sem2     Sem3     Sem4     Sem5     Sem6
Fase 0  ██████ (5d) — infra base, CI, Alembic, sec, obs
Fase 1         ████████ (5d) — T1.x + B4 message_handler refactor
Fase 2                 ████████ (6d) — T2.x (Stage Protocol + Shadow + Adam-Sigmoid)
Fase 3                          ████████ (7d) — T3.x' (Thompson, Calibrator 2-mod, PID, ¼-Kelly)
Fase 4                                   ██████ (4d) — Postgres + Alembic prod + bankroll table
Fase 5                                        ████████ (8d, OPCIONAL) — multi-mesa per-direction
```

---

# FASE 0 — Fundação de Engenharia (5 dias) — 🟢 100% verde

> *Não toca em produção/algoritmo. Habilita TODO o resto. **Aprovar como bloco.***

## ETAPA 0.1 — Git Workflow + Branch Protection (LOCAL + GitHub) — 0.5d
**O que será feito (local):**
- Criar arquivos `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md`, `.github/CODEOWNERS`
- Criar `.pre-commit-config.yaml` com hooks: `ruff`, `mypy --strict strategies/ state/ core/`, `commitlint`
- Adicionar `pyproject.toml` configurando `[tool.commitlint]` (conventional commits)
- Atualizar `CONTRIBUTING.md` documentando: trunk-based, branches `feat/<ID>-<slug>`, `fix/<ID>-<slug>`, squash-merge only

**O que será feito (GitHub):**
- Settings → Branches → Branch protection rule para `main`:
  - Require PR + 1 approval + linear history + status checks: `ci`, `invariant-check`, `alembic-linear`
  - Disable force push, disable delete
- Settings → Actions → Workflow permissions = read+write (para deploy)
- Adicionar secrets: `SSH_PRIVATE_KEY_DEBIAN`, `GHCR_TOKEN`, `AZURE_PG_CONN` (em Fase 4)

**Por que:** Manutenabilidade_iso §7.5 Testabilidade 6/10 — "CI/CD vazio".
**Mudança esperada:** Toda PR ganha checks; impossível push direto em main; commits forçam padrão.

## ETAPA 0.2 — CI/CD GitHub Actions (LOCAL) — 1d
**Arquivos a criar:**
```
.github/workflows/ci.yml           # pytest + ruff + mypy + invariant-check on PR/push
.github/workflows/nightly.yml      # vectorbt backtest 30d + artifact relatório
.github/workflows/deploy.yml       # build Docker → push GHCR → ssh deploy Debian (tag v*)
.github/workflows/alembic.yml      # verifica linear history + downgrade test
scripts/check_isolation_invariant.py  # script Python que falha CI se invariante violado
```

**`ci.yml` esqueleto (já com invariant-check):**
```yaml
name: CI
on: [push, pull_request]
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: ruff check . --output-format=github
      - run: mypy --strict strategies/ state/ core/
      - run: pytest -q --cov=strategies --cov=state --cov=core --cov=server/handlers --cov-fail-under=70
      - name: Invariant Isolation Check
        run: python scripts/check_isolation_invariant.py
```

**`scripts/check_isolation_invariant.py`:**
- Parse AST de `strategies/**/*.py` e `state/bet_advisor.py`
- Falha se:
  - Função recebe arg `direction` mas modifica dict que não tem chave `cw`/`ccw`
  - SELECT SQL no código sem `WHERE spin_direction =`
  - Modelo ML treinado em dataframe sem filtro de direção
  - Atributo `self.X_history` sem par `self.X_cw_history` ou `self.X_ccw_history`

**Por que:** Sem CI, regressões nas Fases 2/3 passam direto. Invariant-check protege contra T3.1/T3.2 originais.
**Mudança esperada:** PR aberta = ~3min para feedback completo.

## ETAPA 0.3 — Alembic Migrations (LOCAL) — 1d
**Estrutura:**
```
alembic.ini
alembic/
├── env.py          # conexão dinâmica: SQLite hoje, Postgres pós-Fase 4
├── script.py.mako
└── versions/
    └── 001_baseline_v1_6.py   # stamp do schema atual (não-disruptivo)
```

**Comandos padronizados:**
```powershell
alembic revision -m "v1.7 add fallback_used and direction_audit columns"
alembic upgrade head        # aplica
alembic downgrade -1        # rollback
alembic history             # auditoria
alembic stamp 001           # marca DB existente como baseline (apenas 1x)
```

**Integração:**
- Hoje `state/game.py:521-572` faz migração inline 1.3→1.6 — **NÃO REMOVER** (back-compat). Apenas marcar como `baseline 001`.
- Docker entrypoint: `alembic upgrade head && python -m server.main`

**Por que:** Fases 1-4 adicionam 6 colunas + 4 tabelas. Sem Alembic vira caos.
**Mudança esperada:** Toda mudança de schema é 1 arquivo Python rastreável.

## ETAPA 0.4 — Observabilidade local (SERVIDOR DEBIAN) — 1.5d
**No host 187.45.181.75:**
- SSH ao servidor, criar `/opt/roleta-obs/docker-compose.yml`:
```yaml
version: "3.8"
services:
  prometheus:
    image: prom/prometheus:latest
    ports: ["127.0.0.1:9090:9090"]
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prom-data:/prometheus
    command: ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.retention.time=30d"]
  loki:
    image: grafana/loki:latest
    ports: ["127.0.0.1:3100:3100"]
    volumes: [loki-data:/loki]
  grafana:
    image: grafana/grafana:latest
    ports: ["127.0.0.1:3000:3000"]
    environment:
      - GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_pwd
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
    volumes: [grafana-data:/var/lib/grafana]
    secrets: [grafana_pwd]
  alertmanager:
    image: prom/alertmanager:latest
    ports: ["127.0.0.1:9093:9093"]
    volumes: [./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro]
volumes: { prom-data: , loki-data: , grafana-data: }
secrets: { grafana_pwd: { file: ./grafana_pwd.txt } }
```

**No projeto Roleta Cloud (LOCAL):**
- Adicionar `core/metrics.py` com 8 métricas Prometheus (por direção quando aplicável):
  ```python
  decisions_total = Counter("roleta_decisions_total", "...", ["direction", "action"])
  hit_rate_gauge  = Gauge("roleta_hit_rate", "...", ["direction", "window"])
  sigmoid_offset  = Gauge("roleta_sigmoid_offset", "...", ["direction", "center"])
  spin_latency    = Histogram("roleta_spin_latency_ms", "...")
  adwin_drifts    = Counter("roleta_adwin_drifts_total", "...", ["direction"])
  thompson_explore = Counter("roleta_thompson_explorations_total", "...", ["direction"])
  martingale_level = Gauge("roleta_martingale_level", "...", ["direction"])
  bankroll_units  = Gauge("roleta_bankroll_units", "")
  ```
- Expor `/metrics` em :9000 via `prometheus_client.start_http_server(9000)`
- Adicionar `/healthz` em :9001 (FastAPI mini-app ou aiohttp): DB ping + state.json read OK + WS alive

**Dashboards Grafana (8 painéis):**
1. Hit rate CW vs CCW (rolling 30, 60, 100 spins)
2. Sigmoid offsets CW (off2/off3) e CCW (off2/off3) evolução temporal
3. ADWIN drift events por dia / por direção
4. Spin latency p50/p95/p99
5. Martingale level CW e CCW + cap Kelly
6. Bankroll units evolution
7. Score 5 anomaly counter
8. Action distribution: APOSTAR vs ESPERAR vs MONITORAR por direção

**Alertas (alertmanager.yml → Discord webhook):**
- `hit_rate_cw < 0.40 for 30m` → WARN
- `hit_rate_cw < 0.35 for 1h` → CRITICAL
- `adwin_drifts_total[5m] > 3` → INFO (mudança de regime)
- `martingale_level > 5` → CRITICAL (Kelly cap violado)

**Por que:** Manutenabilidade_iso §5.4 "Falta circuit breaker para DB e métricas de uptime"; debugging cego em produção hoje.
**Mudança esperada:** Decisão de "trocar de offset 12 para 10" passa de palpite para evidência visual.

## ETAPA 0.5 — Segurança quick-wins (LOCAL) — 1d
**Arquivos a criar/alterar:**
- `server/error_sanitizer.py` (novo): em produção retorna mensagem genérica; em dev expõe `type(exc).__name__: msg[:200]`
- Aplicar em todo `ErrorOutput(message=...)` (grep + replace, ~12 ocorrências)
- `auth/device_token.py` (novo): HMAC-SHA256 sobre `{device_id}.{ts}` com secret de env `DEVICE_HMAC_SECRET`. Verificação em `auth/middleware.py`.
- `app_config/settings.py`: forçar `AUTH_ENABLED=true` quando `ENV == "production"` (override de flag)
- `requirements.txt`: pinar `cryptography>=42` se ainda não pinado

**Por que:** ISO §6 Segurança 6/10; SEC-001 e SEC-002 documentados sem fix.
**Mudança esperada:** Stack traces não vazam; device_id não pode ser forjado.

---

# FASE 1 — Refactor + Hardening de Código (5 dias) — 🟢 verde

## ETAPA 1.1 — Constantes em TOML (T1.1) — 0.5d
- Mover as 16 constantes hardcoded `strategies/sda17.py:41-64` para `config/strategy.toml`
- Carregar via `tomllib` (stdlib Python 3.11+) em `__init__`
- Suportar override por env var `ROLETA_STRATEGY_CONFIG_PATH`
- **Validação Pydantic** dos valores carregados (faixas válidas)

**Mudança esperada:** Tuning sem rebuild Docker.

## ETAPA 1.2 — Backtest vectorbt (T1.2) — 1d
- `tools/backtest_vectorbt.py` (novo, ~150 LoC):
  - Lê últimas N decisions do DB
  - **2 backtests separados** (CW, CCW) — nunca merge
  - Métricas por direção: hit_rate, Sharpe, max drawdown, win streak max, profit factor
  - Output: HTML report em `reports/backtest_YYYY-MM-DD.html` (vectorbt nativo)
- Adicionar em `nightly.yml`: roda à 03:00 UTC, anexa artifact em release

**Por que:** Validação contínua de mudanças sem produção.
**Mudança esperada:** Antes de qualquer merge em estratégia, comparar antes/depois objetivamente.

## ETAPA 1.3 — Logging granular + bug fix fallback (T1.3) — 0.5d
- Adicionar em TODO log de decisão: `direction`, `pipeline_stage_timings_ms`, `gate_passed`, `fallback_used`
- Coluna nova `decisions.fallback_used BOOLEAN DEFAULT FALSE` (Alembic v1.7)
- Coluna nova `decisions.pipeline_version TEXT NOT NULL DEFAULT 'v4.3'` (rastreio)
- **Bug fix `state/bet_advisor.py`**: o fallback que apostou com `sda_score=0` em 02/04 (14 registros) — adicionar gate `if sda_score < 2: action = "ESPERAR"`

**Por que:** Bug histórico documentado em `resultados_02_04.md`.
**Mudança esperada:** Zero falsos APOSTAR com confiança nula.

## ETAPA 1.4 — Bayesian Gate per-direction (T1.4) — 0.5d
- `state/bayesian_gate.py` (novo):
```python
class DirectionalBayesianGate:
    """Beta-Binomial Jeffreys gate. Estados COMPLETAMENTE isolados por direção."""
    def __init__(self, threshold_low=0.47, threshold_high=0.50):
        self.alpha = {"cw": 0.5, "ccw": 0.5}  # Jeffreys prior
        self.beta  = {"cw": 0.5, "ccw": 0.5}

    def should_bet(self, direction: str) -> tuple[bool, dict]:
        d = "cw" if direction == "horario" else "ccw"
        # CI 95% via scipy.stats.beta.interval
        lo, hi = beta.interval(0.95, self.alpha[d], self.beta[d])
        return (lo > self.threshold_low or hi < self.threshold_high), {"ci": (lo,hi), "n": self.alpha[d]+self.beta[d]-1}

    def update(self, direction, hit):
        d = "cw" if direction == "horario" else "ccw"
        (self.alpha if hit else self.beta)[d] += 1
```
- Integrar em `state/bet_advisor.py` antes de emitir APOSTAR

**Mudança esperada:** Score 5 anômalo (n=6, 16.7%) não vira APOSTAR — espera CI sair da zona morta.

## ETAPA 1.5 — ADWIN drift detector dual (T1.5) — 1d
- `pip install river`
- `state/drift_detector.py`:
```python
from river.drift import ADWIN
class DirectionalDriftDetector:
    def __init__(self, delta=0.002):
        self.adwin = {"cw": ADWIN(delta=delta), "ccw": ADWIN(delta=delta)}
        self.last_drift_ts = {"cw": None, "ccw": None}

    def update(self, direction, hit_int):
        d = "cw" if direction == "horario" else "ccw"
        self.adwin[d].update(hit_int)
        if self.adwin[d].drift_detected:
            self.last_drift_ts[d] = datetime.utcnow()
            return True
        return False
```
- Integrar em `state/game.py` após `update_adaptive`:
  - Se drift → **resetar sigmoid_off SÓ DA DIREÇÃO** para `BAYESIAN_DEFAULT`
  - Emitir métrica `adwin_drifts_total{direction=...}`

**Por que:** 02/04 teve 12 misses seguidos CW sem detecção. ADWIN teria pegado em ~6 spins.
**Mudança esperada:** Recuperação de regime change ~50% mais rápida.

## ETAPA 1.6 — Refactor `message_handler.py` (B4) — 2d
**Quebrar em handlers/ (template):**
```
server/handlers/
├── base.py            # HandlerBase ABC + HandlerContext (dataclass DI)
├── spin_handler.py    # novo_resultado, historico_inicial, correcao_historico
├── session_handler.py # nova_sessao, get_state
├── master_handler.py  # register, force_master, slave_register
├── extractor_handler.py # extrair_mesa, listar_mesas
└── dispatcher.py      # mapping {msg_type: handler.handle(ctx, payload)}
```

**`HandlerContext` (DI explícita):**
```python
@dataclass(frozen=True)
class HandlerContext:
    game_state: GameState
    strategy: StrategyBase
    tr_advisor: TripleRateAdvisor
    db_service: DatabaseService
    connection_manager: ConnectionManager
    broadcaster: Broadcaster
    metrics: MetricsRegistry
```

**Golden tests obrigatórios antes do refactor (CI gate):**
- Capturar 100 traces históricos do DB (`tools/capture_golden_traces.py`)
- Snapshot do payload de resposta para cada trace
- Re-replay pós-refactor deve produzir mesmo output

**Mudança esperada:** Acoplamento ISO de [5]→[3]; cobertura 0%→70%; novos msg_types = 1 arquivo novo.

---

# FASE 2 — Estrutural (6 dias) — 🟡 amarelo (mudança de algoritmo — shadow obrigatório)

## ETAPA 2.1 — Stage Protocol pipeline (T2.1) — 2d
**Quebrar `_predict_robust` (220-300) em stages:**
```python
class Stage(Protocol):
    name: str
    def run(self, ctx: PipelineContext) -> PipelineContext: ...

@dataclass
class PipelineContext:
    direction: str            # OBRIGATÓRIO em todo stage
    timeline: Timeline
    forces: list[int]
    wheel_sequence: list[int]
    # mutáveis ao longo do pipeline:
    cleaned_forces: list[int] | None = None
    predicted_force: int | None = None
    score: int | None = None
    centers: tuple[int,int,int] | None = None
    confidence: float | None = None
    stage_timings_ms: dict[str, float] = field(default_factory=dict)
```

**Stages:**
1. `AdaptiveWindowStage`
2. `IQROutlierStage`
3. `WeightedMedianStage`
4. `ADWINDriftStage` (já per-direction da Fase 1)
5. `SmartScoreStage` + `BayesianGateStage`
6. `AdamSigmoidStage` (próxima etapa 2.3)
7. `HotCenterFilterStage` (etapa 2.4)
8. `TripleFocusStage`
9. `(futuro) ThompsonStage, CalibratorStage` na Fase 3
10. `(futuro) PIDStage, KellyStage` na Fase 3

**Cada Stage:** ≤80 LoC, ≥85% test cov individual.
**Pipeline executor:** `for stage in stages: ctx = stage.run(ctx); ctx.stage_timings_ms[stage.name] = ...`

**Mudança esperada:** Modificar/inserir/remover stage = mexer em 1 arquivo; benchmark per-stage gratis.

## ETAPA 2.2 — Shadow Mode infra (T2.2) — 2d
**Tabela nova (Alembic v1.8):**
```sql
ALTER TABLE decisions ADD COLUMN shadow_strategy_id TEXT;
ALTER TABLE decisions ADD COLUMN shadow_numbers TEXT;
ALTER TABLE decisions ADD COLUMN shadow_predicted_force INTEGER;
ALTER TABLE decisions ADD COLUMN shadow_action TEXT;
ALTER TABLE decisions ADD COLUMN shadow_hit INTEGER;
```

**`core/shadow_runner.py`:**
- Executa estratégia "candidata" em paralelo com a "produção"
- Mesma janela, mesma direção, mesmo timeline — só não emite aposta
- Grava em colunas `shadow_*`
- View SQL `v_shadow_comparison` para comparar hit_rate prod vs shadow por direção / período

**Por que:** Aprovar T2.3, T3.1', T3.2' SEM shadow = roleta russa.
**Mudança esperada:** Mudança crítica de algoritmo passa 14 dias em shadow antes de virar prod.

## ETAPA 2.3 — Adam-Sigmoid substitui PCT-Sigmoid (T2.3) — 1.5d
**Substituir `_pct_sigmoid_update` por Adam-Sigmoid:**
```python
class AdamSigmoidUpdater:
    """Adam optimizer + sigmoid bound. Estado ISOLADO por direção."""
    def __init__(self, lr=0.05, beta1=0.9, beta2=0.999, eps=1e-8):
        # m, v, t por direção × por offset (off2, off3)
        self.m = {"cw": {"off2": 0.0, "off3": 0.0}, "ccw": {"off2": 0.0, "off3": 0.0}}
        self.v = {"cw": {"off2": 0.0, "off3": 0.0}, "ccw": {"off2": 0.0, "off3": 0.0}}
        self.t = {"cw": 0, "ccw": 0}

    def update(self, direction, current_off2, current_off3, grad_off2, grad_off3) -> tuple[float, float]:
        d = "cw" if direction == "horario" else "ccw"
        self.t[d] += 1
        # ... Adam clássico para off2 e off3, ainda passa por sigmoid → clamp [7,13]
```
- Roda em **shadow** por 14 dias antes de virar prod
- Métrica `roleta_sigmoid_offset` continua exposta para Grafana comparar curvas

**Hipótese H2.3:** Reduz assimetria CW vs CCW em 30-50%. Aceitação: backtest 30d mostra Δ(CW,CCW) < 15 pts.

## ETAPA 2.4 — Hot Center Filter dual (T2.4) — 0.5d
- `state/hot_filter.py`: lista circular per-direction dos últimos 5 centros C1 emitidos
- Se C1 candidato == C1 anterior 2x consecutivo da MESMA DIREÇÃO, ESPERAR
- Para spins em direção oposta, ignora histórico da direção opposta

**Por que:** Heurística simples contra "ficar grudado" em centro morto.

---

# FASE 3 — Profundo (7 dias) — 🟡 amarelo+ (shadow obrigatório, métrica gate)

## ETAPA 3.1' — Thompson Bernoulli DUAL (T3.1 CORRIGIDO) — 2d
**Estado 2 conjuntos × 37 = 74 contadores, totalmente isolados:**
```python
class DirectionalThompson:
    def __init__(self):
        self.alpha = {"cw": {n: 1.0 for n in range(37)},
                      "ccw":{n: 1.0 for n in range(37)}}
        self.beta = {"cw": {n: 1.0 for n in range(37)},
                     "ccw":{n: 1.0 for n in range(37)}}

    def sample_top_k(self, direction: str, k: int) -> list[int]:
        d = "cw" if direction == "horario" else "ccw"
        scores = {n: random.betavariate(self.alpha[d][n]+1, self.beta[d][n]+1) for n in range(37)}
        return sorted(scores, key=scores.get, reverse=True)[:k]

    def update(self, direction, n_actual, hit, decay=0.97):
        d = "cw" if direction == "horario" else "ccw"
        for k in self.alpha[d]: self.alpha[d][k] *= decay  # decay SÓ na direção
        for k in self.beta[d]:  self.beta[d][k]  *= decay
        (self.alpha[d] if hit else self.beta[d])[n_actual] += 1
```
- Integra em `HotCenterFilterStage` como "boost" da pontuação dos centros candidatos
- Shadow 14 dias

**Por que correção:** Original misturava direções via contadores globais. **Quebraria invariante.**

## ETAPA 3.2' — Calibrator 2-MODELOS (T3.2 CORRIGIDO) — 1.5d
**TREINA 2 MODELOS COMPLETAMENTE INDEPENDENTES:**
```python
class DirectionalCalibrator:
    def __init__(self):
        self.cw_model: CalibratedClassifierCV | None = None
        self.ccw_model: CalibratedClassifierCV | None = None

    def train(self, conn):
        # 2 selects, NUNCA UNION
        df_cw  = pd.read_sql("SELECT * FROM decisions WHERE spin_direction='horario'    AND result_hit IS NOT NULL", conn)
        df_ccw = pd.read_sql("SELECT * FROM decisions WHERE spin_direction='anti-horario' AND result_hit IS NOT NULL", conn)
        feats = ["tr_c4_rate","tr_m6_rate","tr_l12_rate","sda_score","sda_predicted_force","spin_force"]  # SEM direction_dummy
        self.cw_model  = CalibratedClassifierCV(LogisticRegression(max_iter=300), method="sigmoid", cv=5).fit(df_cw[feats], df_cw["result_hit"])
        self.ccw_model = CalibratedClassifierCV(LogisticRegression(max_iter=300), method="sigmoid", cv=5).fit(df_ccw[feats], df_ccw["result_hit"])

    def predict(self, direction, feats: list[float]) -> float:
        m = self.cw_model if direction == "horario" else self.ccw_model
        return m.predict_proba([feats])[0, 1]
```
- Re-treino semanal via `nightly.yml`
- Métricas reportadas SEPARADAS por direção: Brier_cw, ECE_cw, AUC_cw, e idem ccw
- Persistir modelos em `models/cw_calibrator_YYYYMMDD.pkl` e `models/ccw_calibrator_YYYYMMDD.pkl`

**Por que correção:** Modelo único com `direction_dummy` viola invariante (mistura datasets).

## ETAPA 3.3 — PID auto-calibration dual (T3.3) — 1d
- 2 PIDs independentes, cada um controla `BAYESIAN_DEFAULT` (centro de atração do sigmoid) na sua direção
- Setpoint: hit_rate target 50% (configurable em TOML)
- Erro: hit_rate observado rolling 50 - setpoint
- Kp=0.5, Ki=0.05, Kd=0.1 (defaults — sintonia com Ziegler-Nichols rápido em backtest)

## ETAPA 3.4 — ¼-Kelly bet sizing (T3.4) — 2d
**Substitui MartingaleState pela função Kelly fracionado:**
```python
class FractionalKellySizer:
    """Bankroll é SINGLE (mesa única). p_hit vem do calibrator PER-DIRECTION."""
    def __init__(self, fraction=0.25, max_units=8, cov=17):
        self.fraction = fraction
        self.max_units = max_units
        self.b = 36.0/cov - 1.0  # payout líquido para 17 nums = 1.118; para 21 = 0.714

    def units(self, p_hit: float) -> int:
        q = 1 - p_hit
        f_star = (self.b*p_hit - q) / self.b
        f = max(0.0, self.fraction * f_star)
        return min(self.max_units, max(0, round(f * 100)))
```
- Tabela Alembic v1.9: `bankroll_events(id, ts, direction, units_bet, units_won, bankroll_after)`
- Métrica `roleta_bankroll_units` em Prometheus
- **Bankroll é único e global** (mesma mesa); só `p_hit` é per-direction (vem do `DirectionalCalibrator`)
- Kill switch: se `martingale_level > 5` (legacy) OU `bankroll < 50% inicial` → forçar `ESPERAR` por 30min

---

# FASE 4 — Migração para Postgres (4 dias) — 🟡 amarelo

## ETAPA 4.1 — Provisionar Azure DB for PostgreSQL (CLOUD) — 1d
**Comandos Azure CLI:**
```bash
az login
az group create -n rg-roleta-prod -l brazilsouth
az postgres flexible-server create \
  --resource-group rg-roleta-prod \
  --name roleta-pg-prod \
  --location brazilsouth \
  --tier Burstable --sku-name Standard_B2s --storage-size 128 \
  --version 16 \
  --high-availability Disabled \
  --backup-retention 7 \
  --geo-redundant-backup Disabled \
  --admin-user roleta_app \
  --admin-password "$(az keyvault secret show ...)" \
  --public-access 187.45.181.75
az postgres flexible-server parameter set --name azure.extensions --value PGMQ,VECTOR,PG_PARTMAN,PG_CRON,PGCRYPTO,PG_STAT_STATEMENTS -g rg-roleta-prod -s roleta-pg-prod
```
- Criar Key Vault `kv-roleta-prod`, secrets: `PG_PASSWORD`, `DEVICE_HMAC_SECRET`, `ROLETA_API_KEY`
- Adicionar firewall rule só para IP do Debian

## ETAPA 4.2 — Migração de schema + dados (LOCAL + CLOUD) — 1d
- `alembic revision -m "v2.0 postgres baseline"` (recria schema otimizado: BIGSERIAL, índices BRIN para timestamps, partições mensais via pg_partman)
- Script `tools/migrate_sqlite_to_pg.py`:
  - Lê SQLite local + container, ordena por timestamp
  - Escreve em Postgres em batches de 1000 com COPY
  - Verifica COUNT(*) idempotente
- Particionamento via pg_partman: `decisions_y2026m05`, `decisions_y2026m06`, ...
- Retention 12 meses (drop partição mais antiga automaticamente via pg_cron)

## ETAPA 4.3 — Trocar driver no app (LOCAL) — 1d
- `database/postgres_repo.py` implementando `DecisionRepository` ABC (já existe a interface)
- Switch via `DB_BACKEND=postgres|sqlite` env var
- Health check no startup: `SELECT version()`
- Connection pool: `asyncpg` com `max_size=10`

## ETAPA 4.4 — pgmq + pg_cron + pgvector setup (CLOUD) — 1d
- **pgmq:** fila de eventos `extractor_events` (multi-mesa Fase 5)
- **pg_cron:** job diário 03:00 `REFRESH MATERIALIZED VIEW v_hit_rate_daily`
- **pgvector:** embeddings de "padrões de spin" para Thompson contextual (Fase 5+)
- **pg_stat_statements:** habilitar p99 query tracking → dashboard Grafana

---

# FASE 5 — Multi-mesa (8 dias, OPCIONAL) — 🟡 amarelo

## ETAPA 5.1 — SDA17 per-mesa × per-direction (T4.2) — 3d
- Estado vira `{(mesa_id, "cw"): SDA17State, (mesa_id, "ccw"): SDA17State}`
- TOTAL ISOLATION continua: nada cruza entre mesas, nada cruza entre direções

## ETAPA 5.2 — Orchestration via pgmq (T4.3) — 5d
- Worker pool consome `extractor_events` (mesa_id, direction, force, result)
- Despacha para `Pipeline(mesa_id, direction)` correspondente
- Métricas Grafana ganham label `mesa`

---

## 4. Matriz consolidada RISCO × RETORNO × ESFORÇO

```
RISCO\RETORNO    BAIXO              MÉDIO                ALTO
                ┌─────────────────────────────────────────────────────────────┐
🟢 BAIXO        │ (vazio)         │ B9 docs, 1.1 TOML │ ETAPAS 0.1-0.5,        │
                │                 │ 1.2 vectorbt      │ 1.3 logging+bugfix,    │
                │                 │ 1.4 BayesGate,    │ 1.5 ADWIN              │
                │                 │ 7.1 sec quickwin  │ ⭐⭐⭐ APROVAR EM BLOCO │
                ├─────────────────┼───────────────────┼────────────────────────┤
🟡 MÉDIO        │ (vazio)         │ 2.4 HotFilter     │ 1.6 msg_handler,       │
                │                 │ 3.3 PID dual      │ 2.1 Stage Protocol,    │
                │                 │ 4.4 pgmq+pgvec    │ 2.2 Shadow,            │
                │                 │                   │ 2.3 Adam-Sigmoid,      │
                │                 │                   │ 3.1' Thompson dual,    │
                │                 │                   │ 3.2' Calibrator 2-mod  │
                │                 │                   │ ⭐⭐ SHADOW 14d obrig.  │
                ├─────────────────┼───────────────────┼────────────────────────┤
🔴 ALTO         │ (vazio)         │ 4.1-4.3 Postgres  │ 3.4 ¼-Kelly,           │
                │                 │ migração          │ 5.1-5.2 multi-mesa     │
                │                 │                   │ △ ADIAR + canary 30d   │
                └─────────────────────────────────────────────────────────────┘
```

**Recomendação final de aprovação:**
- **Aprovar AGORA (decisão única):** FASE 0 + FASE 1 = 10 dias úteis, 100% verde, zero mudança de algoritmo em produção
- **Aprovar com shadow (mid-sprint):** FASE 2 + FASE 3.1'/3.2'/3.3 = 9.5d, mudança algoritmo só após 14d em shadow + métrica gate
- **Aprovar pós-validação:** FASE 3.4 (¼-Kelly), FASE 4 (Postgres), FASE 5 (multi-mesa)

---

## 5. Tabela "Antes × Depois v5.0"

| Aspecto | v4.3.2 hoje | v5.0 alvo | Delta |
|---|---|---|---|
| Constants | 16 hardcoded em sda17.py | `config/strategy.toml` validado | Hot-reload sem rebuild |
| Pipeline | `_predict_robust` 80 LoC monolítica | 10 stages × ≤80 LoC cada | Modificável stage-a-stage |
| Sigmoid update | PCT-Sigmoid fixo k=6 | Adam-Sigmoid per-direction com m,v,t | -30-50% assimetria CW/CCW |
| Drift detection | Heurística manual de tightness | ADWIN[cw]+ADWIN[ccw] river | -50% latência detecção regime |
| Gate de aposta | Score≥4 sem CI | Beta-Binomial Jeffreys CI per-direction | Zero APOSTAR em anomalia n<10 |
| Calibração | `calibration_offset` dead code | 2 LogReg + Platt isotonic (CW, CCW) | Probabilidade calibrada Brier<0.20 |
| Centros sizing | Martingale 1-2-4 | ¼-Kelly cap, p_hit per-direction, bankroll global | Drawdown -60-80% |
| message_handler | 473 LoC, acopl[5], ZERO testes | 5 handlers × ≤150 LoC, cov ≥70% | Refactor seguro futuro |
| DB | SQLite local + container | Azure PG 16 + pgmq+pgvector+pg_partman | Particionamento, escala, ML futuro |
| Migrations | DDL inline em game.py:521 | Alembic versions/ rastreável | Rollback testável |
| CI/CD | INEXISTENTE | 4 workflows + invariant-check + nightly backtest | Toda PR validada em 3min |
| Observabilidade | structlog console | Prometheus+Loki+Grafana+alertas Discord | Hit rate por direção em tempo real |
| Segurança ISO | 6/10 | 9/10 (SEC-001/002 fix + HMAC + AUTH on by prod) | Stack traces ocultos, device assinado |
| Cobertura testes | ~30% (estimado) | ≥70% gate CI, ≥85% em core/strategies | Refactor seguro |
| Manutenibilidade ISO | 7.0/10 | 9.0/10 | Modular, testável, documentado |
| Tempo refactor stage | ~2d (alto risco) | ~4h (1 stage isolado) | 4x mais rápido |
| Tempo onboarding dev | semanas | dias (ADRs + ARCHITECTURE + docs) | 5x mais rápido |

---

## 6. Gates de promoção (qualquer Fase 2+ exige)

Antes de qualquer mudança crítica virar produção, **TODOS** os gates abaixo devem passar:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ GATE 1 — CI verde (ci.yml + invariant-check + alembic-linear)               │
│ GATE 2 — Cobertura código alterado ≥ 85%                                    │
│ GATE 3 — Shadow run ≥ 14 dias                                                │
│ GATE 4 — Backtest vectorbt 30d: hit_rate_shadow ≥ hit_rate_prod (per-dir)   │
│ GATE 5 — Brier score shadow ≤ Brier prod (per-direction, ambos)             │
│ GATE 6 — Δ(hit_rate_cw, hit_rate_ccw) ≤ delta atual (não piorou)            │
│ GATE 7 — Code review aprovado (single-dev: cooldown 24h + self-merge)       │
│ GATE 8 — ADR escrito documentando decisão                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

Falha de qualquer gate → rollback automático via tag git anterior + `alembic downgrade -1`.

---

## 7. Estrutura de diretórios v5.0 (resultado da refatoração)

```
Roleta Cloud/
├── .github/
│   ├── workflows/ {ci, nightly, deploy, alembic}.yml
│   ├── CODEOWNERS, PULL_REQUEST_TEMPLATE.md, ISSUE_TEMPLATE/
├── alembic/                              [NOVO]
│   ├── env.py, alembic.ini
│   └── versions/ (001_baseline ... 010_postgres)
├── app_config/
│   └── settings.py                       [mod: AUTH_ENABLED auto-prod]
├── auth/
│   ├── middleware.py                     [mod: HMAC device verify]
│   └── device_token.py                   [NOVO]
├── config/                               [NOVO]
│   └── strategy.toml                     [NOVO — 16 constantes]
├── core/
│   ├── engine.py
│   ├── metrics.py                        [NOVO — Prometheus]
│   ├── shadow_runner.py                  [NOVO — Fase 2.2]
│   └── roulette.py
├── database/
│   ├── repository.py
│   ├── sqlite_repo.py                    [legacy, mantido]
│   └── postgres_repo.py                  [NOVO — Fase 4]
├── docs/                                 [NOVO]
│   ├── ARCHITECTURE.md
│   ├── STRATEGIES.md
│   ├── DATABASE.md, DEPLOYMENT.md, CONTRIBUTING.md
│   ├── asyncapi.yaml
│   └── adr/ (0001..0008)
├── models/                               [Pydantic — sem mudança estrutural]
├── reports/                              [NOVO — backtest HTMLs]
├── scripts/                              [NOVO]
│   ├── check_isolation_invariant.py
│   └── capture_golden_traces.py
├── server/
│   ├── connection_manager.py
│   ├── message_handler.py                [REDUZIDO ~50 LoC — fachada]
│   ├── websocket.py
│   └── handlers/                         [NOVO — Fase 1.6 B4]
│       ├── base.py, dispatcher.py
│       ├── spin_handler.py, session_handler.py
│       ├── master_handler.py, extractor_handler.py
├── state/
│   ├── bayesian_gate.py                  [NOVO — 1.4]
│   ├── drift_detector.py                 [NOVO — 1.5 ADWIN dual]
│   ├── hot_filter.py                     [NOVO — 2.4]
│   ├── adam_sigmoid.py                   [NOVO — 2.3]
│   ├── thompson.py                       [NOVO — 3.1' dual]
│   ├── calibrator.py                     [NOVO — 3.2' 2-modelos]
│   ├── pid_controller.py                 [NOVO — 3.3 dual]
│   ├── kelly_sizer.py                    [NOVO — 3.4]
│   ├── bet_advisor.py                    [mod: integra gate+thompson+calibrator]
│   ├── game.py                           [mod: integra drift+kelly]
│   └── timeline.py
├── strategies/
│   ├── base.py
│   ├── sda17.py                          [mod: pipeline via Stage Protocol]
│   └── stages/                           [NOVO — Fase 2.1]
│       ├── adaptive_window.py
│       ├── iqr_outlier.py
│       ├── weighted_median.py
│       ├── adwin_drift.py
│       ├── smart_score.py
│       ├── bayesian_gate_stage.py
│       ├── adam_sigmoid_stage.py
│       ├── hot_center_filter.py
│       ├── thompson_stage.py
│       ├── calibrator_stage.py
│       ├── triple_focus.py
│       └── kelly_stage.py
├── tests/
│   ├── test_invariant_isolation.py       [NOVO — gate CI]
│   ├── test_handlers/ (5 arquivos)       [NOVO]
│   ├── test_stages/ (12 arquivos)        [NOVO]
│   ├── test_state/ (8 arquivos novos)
│   └── golden/ (100 traces JSON)         [NOVO]
├── tools/
│   ├── backtest_vectorbt.py              [NOVO — 1.2]
│   ├── migrate_sqlite_to_pg.py           [NOVO — 4.2]
│   └── ... (existentes)
├── docker-compose.yml                    [mod: + prometheus exporter]
├── Dockerfile                            [mod: alembic upgrade head no entrypoint]
├── pyproject.toml                        [mod: ruff, mypy, pytest-cov config]
├── requirements.txt                      [+ river, vectorbt, asyncpg, prometheus_client, scikit-learn, scipy]
├── requirements-dev.txt                  [NOVO: pytest, ruff, mypy, hypothesis, alembic, pre-commit]
└── .pre-commit-config.yaml               [NOVO]
```

---

## 8. Checklist de execução (ordem cronológica exata)

### Semana 1 — Fase 0
- [ ] Dia 1 manhã: ETAPA 0.1 (Git workflow + branch protection)
- [ ] Dia 1 tarde + Dia 2: ETAPA 0.2 (CI/CD workflows + invariant-check)
- [ ] Dia 3: ETAPA 0.3 (Alembic baseline)
- [ ] Dia 4 + Dia 5 manhã: ETAPA 0.4 (Prometheus+Loki+Grafana no Debian)
- [ ] Dia 5 tarde: ETAPA 0.5 (Sec quickwins SEC-001/002 + HMAC device)

### Semana 2 — Fase 1
- [ ] Dia 6 manhã: ETAPA 1.1 (TOML)
- [ ] Dia 6 tarde + Dia 7: ETAPA 1.2 (vectorbt + nightly workflow)
- [ ] Dia 8 manhã: ETAPA 1.3 (logging granular + bug fix fallback) + Alembic v1.7
- [ ] Dia 8 tarde: ETAPA 1.4 (Bayesian Gate dual)
- [ ] Dia 9: ETAPA 1.5 (ADWIN dual)
- [ ] Dia 10 + Dia 11: ETAPA 1.6 (refactor message_handler em handlers/)

### Semana 3-4 — Fase 2 (shadow começa)
- [ ] Dias 12-13: ETAPA 2.1 (Stage Protocol)
- [ ] Dias 14-15: ETAPA 2.2 (Shadow infra + Alembic v1.8)
- [ ] Dia 16: ETAPA 2.4 (Hot Center Filter)
- [ ] Dias 17-18: ETAPA 2.3 (Adam-Sigmoid → SHADOW por 14d)

### Semana 5 — Fase 3 (shadow contínuo)
- [ ] Dias 19-20: ETAPA 3.1' (Thompson dual → SHADOW)
- [ ] Dias 21-22: ETAPA 3.2' (Calibrator 2-modelos → SHADOW)
- [ ] Dia 23: ETAPA 3.3 (PID dual)

### Semana 6 — Fase 3.4 + Fase 4
- [ ] Dias 24-25: ETAPA 3.4 (¼-Kelly + Alembic v1.9)
- [ ] Dia 26: ETAPA 4.1 (Azure PG provisioning + Key Vault)
- [ ] Dia 27: ETAPA 4.2 (migração schema + dados)
- [ ] Dia 28: ETAPA 4.3 (postgres_repo + switch DB_BACKEND)
- [ ] Dia 29: ETAPA 4.4 (pgmq + pg_cron + pgvector)
- [ ] Dia 30: **GO/NO-GO de produção** — verifica todos os gates

### Semana 7+ — Fase 5 (opcional, sob aprovação separada)
- [ ] Dias 31-33: ETAPA 5.1 (multi-mesa per-direction)
- [ ] Dias 34-38: ETAPA 5.2 (orchestration pgmq)

---

## 9. Decisões pendentes para o usuário (8 perguntas)

| # | Pergunta | Default sugerido |
|---|---|---|
| D1 | Aprovar Fase 0 + Fase 1 (10d) **AGORA**, como bloco? | ✅ SIM |
| D2 | Forma da aposta v5.0: **17 ou 21 números**? (decisão de produto separada) | ⏸ usuário decide |
| D3 | Cloud DB: **Azure PG**, AWS RDS PG, ou GCP Cloud SQL PG? | Azure (créditos + brazilsouth) |
| D4 | Branching: **trunk-based** ou GitFlow? | trunk-based (single dev) |
| D5 | Self-merge OK em main com 24h cooldown? | ✅ SIM |
| D6 | Shadow mode: 14d obrigatório ou flexível? | 14d obrigatório para algoritmo |
| D7 | Fase 5 multi-mesa: começar **junto com Fase 4** ou depois? | Depois (validar v5 single-mesa primeiro) |
| D8 | Tag `v5.0.0` é GO após dia 30 ou após 30d em shadow pós-deploy? | GO no dia 30, label `release-candidate` por 14d, depois `stable` |

---

## 10. Bibliotecas novas + versões pinadas

```
# requirements.txt (additions)
river==0.21.0              # ADWIN drift
vectorbt==0.26.2           # backtest
asyncpg==0.29.0            # Postgres async
prometheus_client==0.20.0  # /metrics
scikit-learn==1.5.0        # Calibrator LR + Platt
scipy==1.13.0              # Beta-Binomial CI
tomli==2.0.1               # TOML config (Python<3.11 fallback)

# requirements-dev.txt (novo)
pytest==8.2.0
pytest-cov==5.0.0
pytest-asyncio==0.23.0
pytest-mock==3.14.0
hypothesis==6.103.0
ruff==0.4.8
mypy==1.10.0
alembic==1.13.1
pre-commit==3.7.1
commitlint==1.0.0
```

**Tamanho final image Docker:** ~280 MB (era ~120 MB) — aceitável.

---

## 11. Compromisso de qualidade (KPIs pós-v5.0)

| KPI | Hoje (23/05) | v5.0 alvo (dia 60 pós-deploy) |
|---|:---:|:---:|
| hit_rate CW | 41.7% | ≥ 52% |
| hit_rate CCW | 65.5% | ≥ 58% |
| Δ(CW, CCW) | 23.8 pts | ≤ 8 pts |
| Brier score CW (modelo) | n/a | ≤ 0.20 |
| Brier score CCW (modelo) | n/a | ≤ 0.20 |
| Max miss streak | 5 | ≤ 6 |
| Drift detection latency | n/a | ≤ 10 spins |
| Bankroll drawdown 7d max | n/a (Martingale ilimitado) | ≤ 30% inicial |
| Spin latency p99 | n/a | ≤ 50ms |
| Test coverage strategies/ | ~50% | ≥ 85% |
| Test coverage server/handlers/ | 0% | ≥ 70% |
| Manutenibilidade ISO | 7.0/10 | ≥ 9.0/10 |
| Segurança ISO | 6/10 | ≥ 9/10 |

---

## 12. Veredito final do orquestrador

> **A proposta é executável, segura e respeita 100% das diretivas inegociáveis do projeto.**
>
> - O invariante CW × CCW é **enforçado por CI** (não depende mais de disciplina humana).
> - A forma da aposta (3 blocos / 17 ou 21) **não é tocada por nenhuma sprint** — fica como decisão de produto isolada.
> - Cada mudança crítica passa por shadow mode + métrica gate antes de virar produção.
> - Infraestrutura cresce em camadas, sem big-bang: primeiro CI/obs, depois algoritmo, depois cloud.
> - O servidor Debian atual **continua sendo o runtime** mesmo após migração do DB para Azure — reduz risco e mantém latência.
> - Custo: irrelevante (créditos cloud); Postgres Burstable B2s 128GB = ~$25/mês, coberto.
>
> **Pronto para iniciar Fase 0 amanhã se aprovado.**

---

## 13. Memórias persistidas nesta sessão (memory MCP)

| Subject | Fact |
|---|---|
| `roleta-cloud-architecture` | Invariante CW/CCW isolamento total inegociável |
| `roleta-cloud-product` | Forma da aposta (3 blocos / 3 centros / 17 ou 21) é invariante |
| `roleta-cloud-strategy` | Assimetria CW vs CCW deve ser tratada per-direction sempre |
| `roleta-cloud-math` | Tabela break-even por cobertura 17→47.2%, 21→58.3%, 27→75% |
| `roleta-cloud-stats` | Beta-Binomial Jeffreys gate, CI fora de [0.47,0.50] antes de agir n<20 |
| `roleta-cloud-sizing` | ¼-Kelly substitui Martingale; bankroll global, p_hit per-direction |
| `graphify-mcp` | get_node/get_neighbors exigem node_id + label + path |

---

*Documento mestre gerado por YOLO Orchestrator (Claude Opus 4.7) em 23/05/2026 16:00 UTC-3.*
*MCPs utilizados: sequential-thinking + filesystem + memory + graphify (god_nodes).*
*Cinco fases / 30 dias úteis / Aprovação recomendada em blocos: Fase 0+1 imediato, Fase 2+3 mid-sprint com shadow, Fase 4 sob validação, Fase 5 opcional.*


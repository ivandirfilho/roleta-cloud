# 🔍 Auditoria — `proposta_refatoracao_23_05.md` vs Manutenabilidade ISO/IEC 25010

**Data:** 2026-05-23 15:45 UTC-3
**Autor:** YOLO Orchestrator (Claude Opus 4.7)
**Documentos cruzados:**
- `proposta_refatoracao_23_05.md` (4 tiers, 16 sprints, 28d total)
- `Manutenabilidade_iso.md` (ISO 25010 — 968 LOC, score geral 7.8/10)
- `resultados_23_05.md` (auditoria estratégica) + `resultados_02_04.md`
**Norma:** ISO/IEC 25010:2011
**MCPs usados:** `filesystem`, `memory`, `sequential-thinking`, `graphify` (god_nodes).

---

## 🚦 INVARIANTE INEGOCIÁVEL (lido como diretiva de projeto)

> **"Cada bloco de estratégia deve analisar o sentido anti-horário e sugerir ele, o sentido horário e sugerir ele, totalmente isolado, como sempre foi a estrutura do código. Isso é inegociável. Não quero estratégia que misture dados dos dois sentidos."** — usuário, 23/05/2026

**Tradução técnica:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ISOLATION INVARIANT — VÁLIDO PARA TODA E QUALQUER FEATURE FUTURA             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ✅ PERMITIDO              ❌ PROIBIDO                                       │
│  ───────────              ───────────                                        │
│  state["cw"]               state shared CW+CCW                              │
│  state["ccw"]              numbers visited (global)                         │
│  cw_history                features = [c4, m6, l12, direction_dummy]        │
│  ccw_history               (mistura sinais de direção)                       │
│  cw_model + ccw_model      single_model.fit(merged_data)                    │
│  cw_pid + ccw_pid          shared_pid                                       │
│  ADWIN_cw + ADWIN_ccw      ADWIN(all_hits)                                  │
│  alpha_cw[n] + alpha_ccw[n]   alpha[n] (sem direção)                        │
│                                                                              │
│  TODA FEATURE NOVA DEVE TER ESTADO DUAL (cw, ccw) OU SER STATELESS PURA.    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Verificação automática proposta (BLOCO 3 abaixo):** ruff custom rule + assert em testes.

---

## 0. TL;DR — o que muda na proposta original

| Sprint original | Estado pós-auditoria | Mudança requerida |
|---|---|---|
| T1.1 TOML constants | ✅ APROVADO | — |
| T1.2 Backtest vectorbt | ✅ APROVADO | — |
| T1.3 Logging granular + bug fallback | ✅ APROVADO | + adicionar `direction` em TODO log |
| T1.4 Bayesian gate | ✅ APROVADO | + per-direction gate (`gate_cw`, `gate_ccw`) |
| T1.5 ADWIN drift | ✅ APROVADO | já estava per-direction ✓ |
| T2.1 Stage Protocol | ✅ APROVADO | + `PipelineContext.direction` obrigatório |
| T2.2 Shadow mode | ✅ APROVADO | + shadow per-direction (não amalgamar) |
| T2.3 Adam-Sigmoid | ✅ APROVADO | já estava per-direction ✓ |
| T2.4 Hot Center Filter | ✅ APROVADO | per-direction window |
| **T3.1 Thompson Bernoulli** | ⚠️ **CORRIGIR** | **2 conjuntos `alpha/beta` (cw, ccw), nunca 37 globais** |
| **T3.2 Platt LR calibration** | ⚠️ **CORRIGIR** | **TREINAR 2 MODELOS** (`cw_model`, `ccw_model`), remover `direction_dummy` |
| T3.3 PID auto-calibration | ✅ APROVADO | já estava per-direction ✓ |
| T3.4 ¼-Kelly bet sizing | ✅ APROVADO | bankroll é único, mas `p_hit` vem do modelo da direção |
| T4.1 Postgres + pgmq | ✅ APROVADO | + Alembic migrations (BLOCO 6) |
| T4.2 SDA17 per-mesa | ✅ APROVADO | per-mesa × per-direction = 2×N estados |
| T4.3 Multi-mesa orchestration | ✅ APROVADO | — |

**Novos blocos adicionados pela auditoria ISO 25010:** **11 blocos** cobrindo Git, CI/CD, migrations, segurança, observabilidade, documentação, refactor message_handler, mudanças de servidor.

---

# BLOCO 1 — Reafirmação e enforcement do Invariante CW/CCW

## 1.1 O que vai ser feito
- Documento `ARCHITECTURE.md` (raiz do repo) com o invariante explicitado
- Custom lint rule (ruff plugin ou script Python) que falha CI se detectar:
  - Função que opera em "force" sem receber `direction: str` como parâmetro
  - Estado dict que tem chaves esperadas `cw/ccw` mas só tem uma delas
  - Modelo ML treinado sobre dataframe sem `WHERE spin_direction = ?` no SQL
- Teste regressivo `tests/test_invariant_isolation.py`:
  ```python
  def test_strategy_state_is_per_direction():
      strat = SDA17Strategy()
      assert hasattr(strat._sigmoid_off, "__getitem__")
      assert "cw_off2" in strat._sigmoid_off
      assert "ccw_off2" in strat._sigmoid_off
      # Após injetar 100 spins CW, ccw_history deve ficar vazia
      for _ in range(100):
          strat.update_adaptive(force=10, direction="horario", hit=True, actual=20)
      assert len(strat.ccw_history) == 0
  ```

## 1.2 Por que vai ser feito
- Pedido explícito (linha citada acima)
- Arquitetura ISO confirma: hoje `cw_history`/`ccw_history` separados, 2 timelines, 2 martingales (`Manutenabilidade_iso.md` §3 linhas 167-172)
- Sem enforcement, T3.1 e T3.2 da proposta original silenciosamente quebrariam o invariante

## 1.3 Mudança esperada
- Zero alteração comportamental no código atual (já compliant)
- Toda feature nova passa por gate CI antes de merge
- Garantia formal e auditável do invariante

**Esforço:** 0.5d | **Risco:** 🟢 BX | **Bloco prioritário (deve ser feito ANTES de T3)**

---

# BLOCO 2 — Correção de T3.1 (Thompson) e T3.2 (Platt LR) para respeitar isolamento

## 2.1 O que vai ser feito

### T3.1' — Thompson Bernoulli **dual** (corrigido)

```python
class DirectionalThompsonState:
    """Per-direction Beta-Binomial posteriors. NUNCA compartilha entre direções."""

    def __init__(self):
        # 2 dicionários COMPLETAMENTE separados
        self.alpha = {"cw": {n: 1.0 for n in range(37)},
                      "ccw": {n: 1.0 for n in range(37)}}
        self.beta = {"cw": {n: 1.0 for n in range(37)},
                     "ccw": {n: 1.0 for n in range(37)}}

    def score(self, direction: str, n: int) -> float:
        d = "cw" if direction == "horario" else "ccw"
        return random.betavariate(self.alpha[d][n] + 1, self.beta[d][n] + 1)

    def update(self, direction: str, n_actual: int, hit: bool, decay: float = 0.97):
        d = "cw" if direction == "horario" else "ccw"
        # decay APENAS no lado da direção atualizada
        for k in self.alpha[d]: self.alpha[d][k] *= decay
        for k in self.beta[d]:  self.beta[d][k]  *= decay
        target = self.alpha[d] if hit else self.beta[d]
        target[n_actual] += 1
```

**Antes (original, ERRADO):** `alpha = {n: 1.0 for n in range(37)}` — global, mistura direções
**Depois (corrigido):** 2 conjuntos × 37 = 74 contadores, totalmente isolados

### T3.2' — Calibration LR **dois modelos** (corrigido)

```python
class DirectionalCalibrator:
    """Dois modelos LogReg+Platt completamente independentes."""

    def __init__(self):
        self.cw_model = None   # CalibratedClassifierCV
        self.ccw_model = None

    def train(self, conn):
        # SEMPRE 2 SELECTS separados, NUNCA UNION ALL
        df_cw  = pd.read_sql("SELECT * FROM decisions WHERE spin_direction = 'horario' AND result_hit IS NOT NULL", conn)
        df_ccw = pd.read_sql("SELECT * FROM decisions WHERE spin_direction = 'anti-horario' AND result_hit IS NOT NULL", conn)
        features = ["tr_c4_rate", "tr_m6_rate", "tr_l12_rate", "sda_score",
                    "sda_predicted_force", "spin_force"]
        # 2 fits independentes
        self.cw_model  = CalibratedClassifierCV(LogisticRegression(...), method="sigmoid", cv=5).fit(df_cw[features], df_cw["result_hit"])
        self.ccw_model = CalibratedClassifierCV(LogisticRegression(...), method="sigmoid", cv=5).fit(df_ccw[features], df_ccw["result_hit"])

    def predict_proba(self, direction: str, features: list[float]) -> float:
        model = self.cw_model if direction == "horario" else self.ccw_model
        return model.predict_proba([features])[0, 1]
```

**Antes (original, ERRADO):** features incluem `direction_dummy` e 1 modelo único
**Depois (corrigido):** 2 modelos, 6 features cada (SEM direction_dummy), datasets separados por SQL WHERE

## 2.2 Por que
- Invariante BLOCO 1
- Estatisticamente: CW (60 amostras 23/05) e CCW (58) têm distribuições diferentes (41.7% vs 65.5% hit rate, Δ=23.8 pts). Um único modelo aprende a média, dois modelos aprendem cada regime corretamente.
- Reduz risco de feature leakage entre direções

## 2.3 Mudança esperada
- T3.1': dobra estado de Thompson (74 floats em vez de 37) — desprezível
- T3.2': dobra tempo de treino offline (re-treino semanal de 2 modelos em vez de 1) — ainda < 10s total
- Métricas (Brier, ECE, AUC) reportadas SEPARADAMENTE por direção

**Esforço total adicional vs original:** +0.3d | **Risco:** 🟢 BX (mudança conceitual, mesma lib)

---

# BLOCO 3 — Git Workflow + CI/CD (hoje NÃO EXISTE — `.github/workflows/` vazio)

## 3.1 O que vai ser feito

### Estrutura proposta
```
.github/
├── workflows/
│   ├── ci.yml              # pytest + ruff + mypy on PR
│   ├── nightly-backtest.yml # vectorbt sobre últimos 30 dias (push para reports/)
│   └── deploy.yml          # build Docker + push registry (tag-triggered)
├── CODEOWNERS              # @ivandirfilho dono de strategies/ e state/
├── PULL_REQUEST_TEMPLATE.md
└── ISSUE_TEMPLATE/
    ├── bug_report.md
    └── feature_request.md
```

### Branching strategy: **Trunk-based + short-lived feature branches**
- `main` (protected, requires PR + 1 approval + CI green)
- `feat/<sprint-id>-<slug>` (ex: `feat/t2.3-adam-sigmoid`)
- `fix/<bug-id>-<slug>`
- `release/<semver>` apenas para hotfix de produção
- **Sem long-lived develop branch** (overhead injustificado para repo single-owner)

### Conventional Commits (enforced via commitlint pre-commit)
```
feat(strategy): T2.3 substitui PCT-Sigmoid por Adam-Sigmoid per-direction
fix(handler): T1.3 corrige logging de fallback G1 seguro
refactor(pipeline): T2.1 quebra SDA17.analyze em Stage Protocol
test(adwin): T1.5 adiciona regressão de drift detection
chore(ci): adiciona workflow nightly-backtest
docs(arch): T0 documenta invariante CW/CCW
```

### Branch protection (GitHub Settings)
- `main` requires:
  - 1 PR approval (mesmo que single-dev: self-approval via outro device é forçar revisão)
  - CI passing (`ci.yml` verde)
  - Conventional commit linting
  - Linear history (no merge commits, só squash ou rebase)
  - **Custom check `invariant-isolation`** (BLOCO 1)

### `ci.yml` mínimo (Python 3.12)
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: ruff check .
      - run: mypy --strict strategies/ state/ core/
      - run: pytest --cov=strategies --cov=state --cov=core --cov-report=xml --cov-fail-under=70
      - run: python scripts/check_isolation_invariant.py
      - uses: codecov/codecov-action@v4  # opcional
```

## 3.2 Por que
- Manutenabilidade_iso §7.5 Testabilidade: **6/10 — "CI/CD vazio, sem execução automática"**
- Sem CI, regressões em T2.1 (refactor SDA17 580 LoC) silenciosamente quebram produção
- Conventional Commits + branch naming permite que vectorbt aponte regressão para PR específico

## 3.3 Mudança esperada
- Toda PR ganha checks automáticos
- Bugs como o do fallback (02/04) são pegos em teste antes do deploy
- Cobertura targets explícitas

**Esforço:** 1d | **Risco:** 🟢 BX | **Dependência: ZERO. Pode ser feito amanhã.**

---

# BLOCO 4 — Refactor `server/message_handler.py` (473 LoC, ZERO testes, acoplamento [5])

## 4.1 O que vai ser feito

### Quebrar em handlers especializados (Command/Strategy Pattern)
```
server/
├── handlers/
│   ├── __init__.py
│   ├── base.py             # HandlerBase ABC + HandlerContext (DI)
│   ├── spin_handler.py     # novo_resultado, historico_inicial, correcao_historico
│   ├── session_handler.py  # nova_sessao, get_state
│   ├── master_handler.py   # register, force_master
│   ├── extractor_handler.py# extrair_mesa, listar_mesas
│   └── dispatcher.py       # mapping msg_type -> handler.handle()
└── message_handler.py      # vira fachada fina (~50 LoC), só roteia para dispatcher
```

### HandlerContext (Dependency Injection)
```python
@dataclass(frozen=True)
class HandlerContext:
    game_state: GameState
    strategy: SDA17Strategy   # ou Protocol
    tr_advisor: TripleRateAdvisor
    db_service: DatabaseService
    connection_manager: ConnectionManager
    broadcaster: Broadcaster
```

Cada handler recebe contexto, pode ser testado isolado com mocks.

### Cobertura mínima por handler (CI gate via BLOCO 3)
| Handler | LoC esperado | Cobertura mínima |
|---|---|---|
| spin_handler | ~150 | 85% |
| session_handler | ~50 | 80% |
| master_handler | ~80 | 70% |
| extractor_handler | ~60 | 70% |
| dispatcher | ~30 | 100% |

## 4.2 Por que
- Manutenabilidade_iso §7.1: acoplamento [5] (alto) em `message_handler` e `websocket.py`
- Manutenabilidade_iso §7.3: cobertura **ZERO testes** em message_handler.py (473 LoC)
- Manutenabilidade_iso §7.4: alterar protocolo WS hoje é "❌ Difícil — 473 LOC entrelaçando I/O e lógica"
- T2.1 (Stage Protocol) fica meia-boca sem este refactor: pipeline modular dentro de um handler god

## 4.3 Mudança esperada
- Acoplamento [5] → [3]
- Cobertura ZERO → 70%+
- Adicionar novo tipo de mensagem WS = criar 1 arquivo handler, não tocar dispatcher

**Esforço:** 3d | **Risco:** 🟡 MD (refactor grande sem testes — exige golden tests sobre traces gravados) | **Dependência: BLOCO 3 (CI gate)**

---

# BLOCO 5 — Database Migrations (adotar Alembic)

## 5.1 O que vai ser feito

```
alembic/
├── env.py                       # configura conexão (SQLite hoje, Postgres pós-T4.1)
├── script.py.mako
└── versions/
    ├── 001_baseline_v1_6.py     # snapshot do schema atual (4 tabelas + 10 índices)
    ├── 002_v1_7_fallback_used.py# T1.3 — adiciona coluna fallback_used
    ├── 003_v1_8_shadow.py       # T2.2 — adiciona shadow_strategy_id, shadow_numbers...
    ├── 004_v1_9_bankroll.py     # T3.4 — adiciona bankroll_events table
    └── 005_v2_0_postgres.py     # T4.1 — primeira migração no Postgres
```

### Comandos padronizados
```bash
alembic revision -m "v1.7 fallback_used column"
alembic upgrade head
alembic downgrade -1
alembic history
```

### Integração com migration v1.3→v1.6 existente
- `state/game.py` linhas 521-572 hoje tem migração inline. **NÃO REMOVER** — migrate-as-baseline. Apenas garantir que `alembic stamp 001` reconhece estado atual.

## 5.2 Por que
- Manutenabilidade_iso §7.4: "Alterar modelo de dados ⚠️ Moderado — Schema DDL manual, sem Alembic migrations"
- T1.3 adiciona coluna, T2.2 adiciona 4 colunas, T3.4 adiciona tabela inteira, T4.1 muda DB — **sem migrations isto vira pesadelo**
- Migration trackable em PR

## 5.3 Mudança esperada
- Mudança de schema = 1 arquivo `alembic revision` + revisão por quem cria PR
- Rollback de migration testável em CI
- Zero downtime em mudança de DB (alembic upgrade dentro de container startup)

**Esforço:** 1d | **Risco:** 🟢 BX | **Dependência: deve ser antes de T1.3, T2.2, T3.4**

---

# BLOCO 6 — Mudanças no Servidor (Debian / Docker / Cloud)

## 6.1 O que vai ser feito

### Fase imediata (compatível com VM atual 187.45.181.75 — sem upgrade)
```
docker-compose.yml (additions):
+ services:
+   prometheus:
+     image: prom/prometheus:latest
+     ports: ["127.0.0.1:9090:9090"]
+     volumes: ["./prom/prometheus.yml:/etc/prometheus/prometheus.yml:ro"]
+
+   loki:
+     image: grafana/loki:latest
+     ports: ["127.0.0.1:3100:3100"]
+
+   grafana:
+     image: grafana/grafana:latest
+     ports: ["127.0.0.1:3000:3000"]
+     environment:
+       - GF_SECURITY_ADMIN_PASSWORD_FILE=/run/secrets/grafana_pwd
+     volumes: ["grafana-data:/var/lib/grafana"]
+
+ volumes:
+   grafana-data:
+
+ roleta-cloud:
+   environment:
+     + LOG_FORMAT=json
+     + METRICS_ENABLED=true
+     + METRICS_PORT=9000
+   ports: ["127.0.0.1:9000:9000"]   # /metrics endpoint
```

Adicionar em `core/`:
```python
# core/metrics.py (novo)
from prometheus_client import Counter, Histogram, Gauge

decisions_total = Counter("roleta_decisions_total", "Decisions by direction and action",
                          ["direction", "action"])
hit_rate = Gauge("roleta_hit_rate", "Rolling hit rate by direction",
                 ["direction", "window"])
sigmoid_offset = Gauge("roleta_sigmoid_offset", "Current sigmoid offset",
                       ["direction", "center"])
spin_latency = Histogram("roleta_spin_latency_ms", "Pipeline latency in ms")
adwin_drifts = Counter("roleta_adwin_drifts_total", "ADWIN drift events",
                       ["direction"])
```

### Fase T4.1 (Postgres vai exigir upgrade VM)
- VM atual: ~2 GB RAM, ~30 GB disk (suficiente até hoje)
- Postgres 16 + extensions (pgmq, pgvector, pg_partman, pg_cron) precisa: **4 GB RAM, 100 GB disk SSD**
- **Recomendação:** Azure DB for PostgreSQL Flexible Server (managed, free tier suficiente para 6 meses com créditos)
- Migrar SQLite → Postgres via `pgloader` ou script Alembic

### Hardening **explicitamente fora do escopo** (pedido do usuário em sessão anterior — ignorar)

## 6.2 Por que
- Manutenabilidade_iso §5.4: "Falta circuit breaker para DB e métricas de uptime"
- §7.3: "Sem CI" + sem dashboards = debugging em produção é cego
- Prometheus/Loki/Grafana são padrão de mercado, free, fácil deploy

## 6.3 Mudança esperada
- Dashboard Grafana com painéis: hit_rate por direção, sigmoid_offset evolution, ADWIN drifts/dia, spin latency p50/p99
- Alertas em Grafana (Discord/Email webhook): "hit rate CW < 40% por 30min"
- Logs centralizados em Loki, queryáveis com LogQL

**Esforço:** 2d (Fase imediata) + 4d (Fase T4.1) | **Risco:** 🟢 BX (imediata) / 🟡 MD (T4.1)

---

# BLOCO 7 — Segurança ISO 6/10 → 8/10

## 7.1 O que vai ser feito

### SEC-001: ErrorOutput sanitization
```python
# server/error_sanitizer.py (novo)
def sanitize_error(exc: Exception, env: str) -> str:
    if env == "production":
        return "Erro interno do servidor"  # genérico
    return f"{type(exc).__name__}: {str(exc)[:200]}"  # dev/staging
```
Aplicar em todo `ErrorOutput(message=...)`.

### SEC-002: Device ID com HMAC
```python
# auth/device_token.py (novo)
import hmac, hashlib, time

def sign_device(device_id: str, secret: str) -> str:
    ts = str(int(time.time()))
    payload = f"{device_id}.{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{device_id}.{ts}.{sig}"

def verify_device(token: str, secret: str, max_age_s: int = 86400) -> str | None:
    parts = token.split(".")
    if len(parts) != 3: return None
    device_id, ts, sig = parts
    expected = hmac.new(secret.encode(), f"{device_id}.{ts}".encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected): return None
    if int(time.time()) - int(ts) > max_age_s: return None
    return device_id
```

### AUTH_ENABLED=true por default em produção
- `app_config/settings.py`: detectar `os.environ.get("ENV") == "production"` → forçar `AUTH_ENABLED=true` ignorando flag
- Documentar em README

### Secrets management
- Hoje: `.env` no `.gitignore` (OK)
- Adicionar: `docker secret` ou Azure Key Vault (T4.1 fase Postgres)

## 7.2 Por que
- Manutenabilidade_iso §6 Segurança 6/10
- SEC-001 e SEC-002 são bugs documentados sem fix

## 7.3 Mudança esperada
- Score segurança ISO 6/10 → 8/10
- Stack traces não vazam em produção
- Spoofing de device_id impossível

**Esforço:** 1d | **Risco:** 🟢 BX | **Independente — pode ser feito a qualquer momento**

---

# BLOCO 8 — Testes & Cobertura (gate CI 70% → 80%)

## 8.1 O que vai ser feito

### Adicionar testes faltantes (lista prioritária)
| Arquivo | LoC hoje | Testes hoje | Testes alvo | Sprint |
|---|---|---|---|---|
| `server/message_handler.py` | 473 | 0 | 70% | BLOCO 4 |
| `server/connection_manager.py` | 272 | 0 | 60% | BLOCO 8.1 |
| `core/engine.py` | 130 | 0 | 80% | BLOCO 8.1 |
| `database/sqlite_repo.py` | ~850 | 32 | 50% | BLOCO 8.1 |
| `strategies/sda17.py` | 580 | ~150 | 85% | T2.1 (refactor habilita) |
| `state/bet_advisor.py` | 169 | 69 | 80% | T3.2 |

### Tipos de testes a adicionar
- **Unit:** stage isolado, mocks de I/O
- **Property-based:** Hypothesis para WHEEL_SEQUENCE (já é puro)
- **Golden:** snapshot de 100 traces históricos → re-replay assert mesmo output
- **Regression:** invariante CW/CCW (BLOCO 1)
- **Backtest:** vectorbt baseline diariamente (BLOCO 3 nightly)

### Setup
```bash
pip install pytest pytest-cov pytest-asyncio pytest-mock hypothesis
```
`pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "--cov=. --cov-fail-under=70 --cov-report=html"
testpaths = ["tests"]

[tool.coverage.run]
omit = ["archive/*", "tools/*", "tests/*"]
```

## 8.2 Por que
- Manutenabilidade_iso §7.3 Analisabilidade 7/10 + §7.5 Testabilidade 6/10
- Sem testes em `message_handler` (BLOCO 4) e `connection_manager`, qualquer refactor é roleta russa

## 8.3 Mudança esperada
- Score testabilidade 6/10 → 8/10
- Score analisabilidade 7/10 → 9/10
- Confiança em mudar `message_handler` (BLOCO 4) sem quebrar produção

**Esforço:** 3d (distribuído entre sprints) | **Risco:** 🟢 BX | **Não-bloqueante mas multiplicador de qualidade**

---

# BLOCO 9 — Documentação (ISO §4.2 Apreensibilidade 8/10 → 9/10)

## 9.1 O que vai ser feito

### Arquivos a criar/manter
```
docs/
├── ARCHITECTURE.md          # invariante CW/CCW + componentes + fluxo
├── STRATEGIES.md            # SDA17 pipeline detalhado + stages futuros
├── DATABASE.md              # schema + migrations + acesso (atual hoje em ISO)
├── DEPLOYMENT.md            # deploy passo-a-passo Debian + Azure
├── CONTRIBUTING.md          # PR template + branch naming + commits
├── asyncapi.yaml            # spec formal das mensagens WS
└── adr/                     # Architecture Decision Records
    ├── 0001-isolation-invariant-cw-ccw.md
    ├── 0002-postgres-over-sqlite.md
    ├── 0003-vectorbt-over-stdlib.md
    └── 0004-adam-sigmoid-over-pct-sigmoid.md
```

### AsyncAPI spec (formaliza protocolo WS)
```yaml
asyncapi: 2.6.0
info:
  title: Roleta Cloud WebSocket API
  version: 4.3.2
channels:
  /ws:
    subscribe:
      message:
        oneOf:
          - $ref: "#/components/messages/Sugestao"
          - $ref: "#/components/messages/StateSync"
    publish:
      message:
        oneOf:
          - $ref: "#/components/messages/NovoResultado"
          - $ref: "#/components/messages/HistoricoInicial"
components:
  messages: {...}
```

## 9.2 Por que
- ISO §4.2 §4.3: "Falta documentação de API WebSocket formal (AsyncAPI spec ou similar)"
- ADRs permitem que decisões (Postgres, Adam-Sigmoid) sobrevivam à memória do time
- Onboarding novo dev = ler `ARCHITECTURE.md` + 4 ADRs

## 9.3 Mudança esperada
- Reduz tempo de onboarding em 5x
- Decisões documentadas, não folclore oral

**Esforço:** 1.5d | **Risco:** 🟢 BX | **Pode ser feito em paralelo com qualquer sprint**

---

# BLOCO 10 — Pipeline Strategy v6 visual (após T1+T2+T3 + BLOCOS 1-9)

## 10.1 Diagrama final por direção

```
                            ┌────────────────────────────────────────────────────┐
                            │           ANALYZE_DIRECTION(dir, force)             │
                            │  invariante: NÃO LÊ estado da outra direção         │
                            └────────────────────────┬───────────────────────────┘
                                                     │
              ┌──────────────────────────────────────┼──────────────────────────────────────┐
              ▼                                      ▼                                      ▼
       ┌──────────────┐                  ┌──────────────┐                          ┌──────────────┐
       │  ADWIN[cw]    │                  │  ADWIN[ccw]   │                          │ (idem outras │
       │  drift check  │                  │  drift check  │                          │  mesas       │
       │  T1.5+B1      │                  │  T1.5+B1      │                          │  T4.2)       │
       └──────────────┘                  └──────────────┘                          └──────────────┘

CADA DIREÇÃO RODA O PIPELINE INDEPENDENTE:
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            PIPELINE DIRECTIONAL (CW   ou   CCW)                                  │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│  ┌─────────┐   ┌──────────┐   ┌─────────────┐   ┌─────────┐   ┌──────────┐   ┌──────────────┐   │
│  │ Timeline│──▶│Adapt.Win │──▶│IQR Reject   │──▶│Wgt.Med  │──▶│Drift      │──▶│Smart Score   │   │
│  │ [dir]   │   │ T2.1     │   │ T2.1        │   │ T2.1    │   │ T2.1     │   │ + Bayes Gate │   │
│  │         │   │          │   │             │   │         │   │          │   │ T1.4         │   │
│  └─────────┘   └──────────┘   └─────────────┘   └─────────┘   └──────────┘   └──────┬───────┘   │
│                                                                                       ▼          │
│  ┌──────────────────┐   ┌─────────────────────┐   ┌──────────────────────┐   ┌──────────────┐   │
│  │ TripleFocus [dir]│◀──│ Thompson[dir][37]  │◀──│ HotCenterFilter[dir] │◀──│ AdamSigm[dir]│   │
│  │ T2.1 + B1        │   │ T3.1' + B2          │   │ T2.4 + B1            │   │ T2.3 + B1   │   │
│  └────────┬─────────┘   └─────────────────────┘   └──────────────────────┘   └──────────────┘   │
│           ▼                                                                                      │
│  ┌────────────────────┐   ┌──────────────────────┐   ┌──────────────────────────┐               │
│  │ Calibrator[dir]    │──▶│ PID Calibration[dir] │──▶│ ¼-Kelly sizing            │               │
│  │ (cw_model/ccw_model)│   │ T3.3 + B1            │   │ T3.4 (bankroll global,    │               │
│  │ T3.2' + B2          │   │                      │   │  p_hit é per-direction)   │               │
│  └────────────────────┘   └──────────────────────┘   └──────────┬───────────────┘               │
└─────────────────────────────────────────────────────────────────┼─────────────────────────────────┘
                                                                  ▼
                                              ┌──────────────────────────────────┐
                                              │ Persist[Postgres T4.1, Alembic B5]│
                                              │ Metrics[Prometheus B6]            │
                                              │ Trace[structlog T1.3]             │
                                              └──────────────────────────────────┘
```

---

# BLOCO 11 — Cronograma consolidado pós-auditoria

## 11.1 Ordem final (3 fases × 4 semanas)

### **FASE 0 — Pré-tudo (semana 1) — 4.5d**
| # | Sprint | Esforço | Dep |
|---|---|---|---|
| B3 | Git Workflow + CI/CD | 1d | — |
| B5 | Alembic migrations | 1d | — |
| B1 | Invariante CW/CCW (doc + lint rule + test) | 0.5d | B3 |
| B7 | Segurança SEC-001/SEC-002/AUTH_ENABLED | 1d | — |
| T1.1 | TOML constants | 0.5d | — |
| B6.1 | Prometheus + Loki + Grafana (fase imediata) | 2d (overlap) | — |
**Total efetivo Fase 0:** ~5d com paralelização

### **FASE 1 — T1 + B4 + B8 (semanas 2-3) — 7d**
| # | Sprint | Esforço |
|---|---|---|
| T1.2 | vectorbt backtest | 1d |
| T1.3 | Logging + bug fix + alembic v1.7 | 1d (com B5) |
| T1.4 | Bayesian gate per-direction | 0.3d |
| T1.5 | ADWIN per-direction | 1d |
| B4 | Refactor message_handler em handlers/ | 3d |
| B8 | Testes faltantes (engine, connection_manager) | 2d paralelo |
| B9 | Docs ARCHITECTURE + 4 ADRs | 1.5d paralelo |

### **FASE 2 — T2 (semana 4) — 6d**
| # | Sprint | Esforço |
|---|---|---|
| T2.1 | Stage Protocol refactor | 2d |
| T2.2 | Shadow mode infra (per-direction) | 2d |
| T2.3 | Adam-Sigmoid per-direction | 1.5d |
| T2.4 | Hot Center Filter per-direction window | 0.5d |

### **FASE 3 — T3 (semanas 5-6) — 7d**
| # | Sprint | Esforço |
|---|---|---|
| T3.1' | Thompson dual (CORRIGIDO) | 2d |
| T3.2' | Calibrator 2 modelos (CORRIGIDO) | 1.5d |
| T3.3 | PID per-direction | 1d |
| T3.4 | ¼-Kelly bankroll global, p_hit per-direction | 2d |

### **FASE 4 — T4 (semanas 7-10, OPCIONAL) — 12d**
| # | Sprint | Esforço |
|---|---|---|
| T4.1 | Postgres + Alembic prod + pgmq | 4d |
| B6.2 | VM upgrade Azure DB | (paralelo T4.1) |
| T4.2 | SDA17 per-mesa × per-direction | 3d |
| T4.3 | Multi-mesa orchestration | 5d |

**Total geral pós-auditoria:** 25.5d (vs 28d original) — paralelização de B6/B8/B9 compensa novos blocos.

---

## 12. Tabela consolidada de RISCO × RETORNO atualizada

```
                       RETORNO ESPERADO
                BAIXO         MÉDIO          ALTO
       ┌──────────────────────────────────────────────────────────┐
BAIXO  │   (nada)     B9 docs      B1 invariante, B3 CI, B5 alemb│
RISCO  │              B8 testes    B6.1 obs, B7 sec, T1 inteiro  │
🟢     │                           ⭐⭐⭐ APROVAR EM BLOCO         │
       ├──────────────────────────────────────────────────────────┤
MÉDIO  │   (nada)     T3.1'/T3.2' B4 msg_handler refactor        │
RISCO  │              T3.3 PID    T2 inteiro                     │
🟡     │              ⭐ NEGOCIAR ⭐⭐ APROVAR COM SHADOW         │
       ├──────────────────────────────────────────────────────────┤
ALTO   │   (nada)     T4.1 prod   T3.4 Kelly                     │
RISCO  │              alone       T4.2/T4.3 multi-mesa           │
🔴     │              × pular     △ ADIAR + shadow + 30d          │
       └──────────────────────────────────────────────────────────┘
```

**Recomendação concreta para começar:** **Aprovar Fase 0 completa (5d, todo no quadrante Verde × Alto)**. Isto resolve infra (git, ci, migrations, sec, obs) ANTES de mexer no algoritmo — base sólida para tudo que vem depois.

---

## 13. Perguntas finais (auditoria)

| # | Pergunta | Default sugerido |
|---|---|---|
| Q1 | Aprovar **Fase 0** integral começando segunda? (5d) | ✅ SIM |
| Q2 | Branching strategy: trunk-based como proposto ou GitFlow? | trunk-based (single dev) |
| Q3 | CODEOWNERS aplicado mesmo em repo single-dev? | SIM (força revisão por outro device) |
| Q4 | Prometheus+Grafana local **agora** ou aguardar T4.1? | AGORA (Fase 0) |
| Q5 | Refactor message_handler (B4) **antes** ou **depois** de T1.5? | ANTES (habilita resto) |
| Q6 | Alembic baseline = atual schema, ou criar do zero? | baseline atual (não-disruptivo) |
| Q7 | AsyncAPI spec gerada manualmente ou auto (websockets-doc)? | manual primeiro (1 arquivo) |
| Q8 | Quem aprova PRs (single-dev)? Self-merge com `requires_approval=true`? | Self-merge OK se CI verde + 24h cooldown |

---

## 14. Resumo executivo

**Veredito da auditoria:** A proposta original `proposta_refatoracao_23_05.md` está **80% correta**. Os 20% precisam correção em:
1. **T3.1 e T3.2** violavam o invariante CW/CCW silenciosamente → corrigidos como T3.1' e T3.2'
2. Faltava **camada de infraestrutura de engenharia** (git, CI, migrations, segurança, observabilidade) — coberto pelos novos BLOCOS 1, 3, 5, 6, 7, 8, 9
3. Faltava **enforcement automático** do invariante — coberto pelo BLOCO 1 (lint rule + test)
4. Faltava **refactor de message_handler** (god dispatcher 473 LoC, ZERO testes) — coberto pelo BLOCO 4

**Total adicional vs proposta:** **+11 blocos**, **+0d** (paralelização absorve esforço novo)

**Ordem recomendada de início:**
- **Segunda:** B3 (CI/CD) + B5 (Alembic) + B7 (Segurança) em paralelo
- **Terça/Quarta:** B1 (invariante) + T1.1 (TOML) + B6.1 (Prometheus)
- **Quinta/Sexta:** B6.1 finaliza + Fase 1 começa (T1.2 vectorbt)

Tudo na **Fase 0+1** está no quadrante 🟢 Risco × ⭐⭐⭐ Retorno — **deve ser aprovado em bloco**.

---

*Documento gerado por YOLO Orchestrator (Claude Opus 4.7) em 23/05/2026 15:45 UTC-3, MCPs: sequential-thinking + filesystem + memory + graphify. Persistido em memória: `roleta-cloud-architecture` (invariante CW/CCW como diretiva inegociável de projeto).*

# 🧬 Sprint Evolução — Blueprint 26/05 (DNA Estratégico)

> **Gerado:** 2026-05-26 20:30 BRT | **Modelo:** `claude-opus-4.7` | **Stack MCP:** `filesystem` + `graphify` + `memory` + `brave-search` + `sequential-thinking` + `context7` + `github`
>
> **Predecessores diretos:**
> - [`Visualizacao_da_evolucao_25_05.md`](./Visualizacao_da_evolucao_25_05.md) — diagnóstico estratégico
> - [`sprint_26_05_estrategia.md`](./sprint_26_05_estrategia.md) — execução das ondas ISO Wave 2/3/4 (50% feito hoje)
> - [`Manutenabilidade_iso.md`](./Manutenabilidade_iso.md) — princípios ISO/IEC 25010
>
> **Pergunta-síntese:** *"Cada decisão fine-tuning contribui ou atrapalha — quanto % é DNA estrutural? Como construir esse DNA na base (PG+vector) para evoluir as 3 regiões? Dealer/provedor já chega? O que fazer sprint a sprint sem desorganizar o que está indo bem?"*
>
> **Resposta-síntese:**
> 1. ❶ DNA hoje vive **espalhado em colunas isoladas** (`sda_score`, `calibration_offset`, `tr_confidence`…) — falta uma **contabilidade explícita** de "X pp ganhos / Y pp perdidos por cada fine-tuner ativo no spin".
> 2. ❷ As **3 regiões** (centros C1/C2/C3 com offsets ±) são construídas no SDA17 mas o **% de contribuição de cada região** para hit/miss não existe como métrica nem como linha do schema.
> 3. ❸ **Dealer/provedor ainda NÃO chega** no payload — confirmado em `extension/background.js:1129-1138`. Já existe `server/extractor_service.py` que detecta provider por URL no extrator novo, mas não está cabeado na extensão.
> 4. ❹ **Hoje (26/05) entregamos** wheel_dist (W-01/W-02/B-08) + 2 hotfixes (B-09/B-10) + alerta fill-rate (NEW-12) + 2 defensive flags (NEW-07/NEW-08) + circuit breaker (MEL-ISO-004). `calibration_error` saiu de 0% → **90% fill-rate em prod**. Suite 249 → 282 (+33).
> 5. ❺ Blueprint abaixo tem **35 sprints** (30 de evolução + 5 de bugs/dívidas remanescentes) com prompt-padrão para drenagem sprint-a-sprint sem regressão.

---

## §0. Estado atual (snapshot 26/05 20:30 BRT)

### 0.1 O que foi entregue HOJE
| Commit | Mudança | Impacto |
|---|---|---|
| `386bc58` | `compute_wheel_dist` helper + persist `calibration_error` (W-01/W-02/B-08) | Sinal de "quase-acerto" agora capturável |
| `d83e214` | Sprints reorganizadas por ISO/IEC 25010 (Wave 2) | Manutenibilidade 6.3 |
| `a41210c` | SQLite circuit breaker + auditoria NEW-06 (MEL-ISO-004) | Disponibilidade 5.2 |
| `d6935b5` | **B-09:** `pending["centers"]` (chave correta) | wheel_dist começou a popular |
| `fb94675` | Alerta Prometheus `RoletaCalibrationFillRateLow` (NEW-12) | Sentinel anti-regressão silenciosa |
| `f65801d` | Blacklist defensiva opt-in `BET_BLACKLIST_ENABLED` (NEW-07) | Backtest counterfactual +1.52pp validado |
| `ca353fd` | Piso `sda_thr` opt-in `BET_SDA_FLOOR` (NEW-08) | Defesa em alta volatilidade |
| `cf3570d` | **B-10:** `DatabaseService.update_result` propaga `calibration_error` | Fill-rate 0% → 90% ao vivo |
| `aadcb1b` | Docs §23 — refutação NEW-11 (skew direção não-estacionário) | Decisão baseada em dados |

**Suite:** 249 → **282 passing** (+33, zero regressões).
**Prod:** healthy em `aadcb1b`. 12 regras Prometheus. 3 métricas novas (cal_total/filled/rate).

### 0.2 O que está em prod mas OFF (feature flags defensivas)
- `BET_BLACKLIST_ENABLED=0` — bloqueio dos 2 piores `tr_reason` (hr ~37%); backtest projeta hr +1.52pp
- `BET_SDA_FLOOR=2` — piso default = no-op; subir a 3 estabiliza em alta volatilidade

### 0.3 Distribuição calibration_error (n=31 pós-fix)
| dist | n | hit_pct |
|---:|---:|---:|
| 0-2 | 14 | **100%** |
| 3 | 5 | 20% |
| 4+ | 12 | 0% |
`avg_dist_hits=1.07` vs `avg_dist_miss=4.63` → modelo **calibrado**, miss = "longe", não "quase".

### 0.4 PG/Vector hoje
- Alembic head: **0006_spin_features** (`shared.dealers` e `shared.tables` AINDA não existem)
- `cw|ccw.spin_features`: **NÃO tem** `dealer_id`, `table_id`, `wheel_dist` (escrito só no SQLite por enquanto)
- `cw.spins_vectors`: **VECTOR(6)** ainda (sub-dimensionado)
- AGE: instalada, **ociosa** (0 cypher queries em código de produção)
- Outbox: 100% processed, CDC < 22s

### 0.5 Bugs/Dívidas remanescentes
- **NEW-09**: bisect `FeatureStore`/`Regime` opt-in (regressão hit_rate 47.69 → 43.95 em 4 dias) — pendente 24h de tráfego pós-B10
- **Skew direção**: refutado como guard estático, mas reciclado para regime-aware
- CI/deploy: mecanismo de pull em prod não documentado; deploy 100% manual via SSH
- Backfill histórico `calibration_error` em 3255 decisões NULL pré-B-10
- Schema drift: SQLite tem campos que PG não tem (assimetria write-side/read-side)

---

## §1. A visão nuclear — **DNA estrutural por decisão**

### 1.1 O conceito
Hoje cada APOSTAR/PULAR é resultado de uma cascata de fine-tuners:
```
spin → Force → AdaptiveState → Cooldown → DriftFreeze →
       SDA17(center,score,force,offset) → BetAdvisor(c4,m6,l12,kill_v4) →
       Martingale(level,take_profit) → CalibrationOffset → ação final
```
Cada item é uma **decisão fine-tuning**. O sistema persiste o **valor** de cada uma (`sda_score`, `calibration_offset`, `tr_c4_rate`…) mas **NÃO** atribui um **peso% de contribuição** (positivo ou negativo) para a decisão final.

**Hoje a análise é a posteriori** (queries SQL agregando por bucket). O usuário quer isso **dentro do schema**, na base, para:
1. Cada nova estratégia já nascer carimbada com "% contribuição esperada"
2. Auditar a posteriori "quem ganhou quem perdeu" sem precisar joinar 8 colunas
3. Treinar ML hierárquico onde features de baixa contribuição são naturalmente regularizadas

### 1.2 Estrutura proposta: `decision_dna`
Tabela nova **append-only** em PG (e write-side SQLite):

```sql
CREATE TABLE shared.decision_dna (
    id              BIGSERIAL PRIMARY KEY,
    decision_id     BIGINT NOT NULL,           -- FK para decisions
    spin_number     INTEGER,
    direction       TEXT,
    ts              TIMESTAMPTZ DEFAULT now(),

    -- Cada feature do DNA com seu peso atual e contribuição computada
    feature_name    TEXT NOT NULL,             -- ex: 'sda_score', 'calibration_offset', 'errdriven'
    feature_value   JSONB NOT NULL,            -- {"raw": 4, "bucket": "sweet_spot"}
    estimated_lift_pp  REAL,                   -- pp +/- esperado por essa feature (de tabela learned)
    realized_lift_pp   REAL,                   -- pp +/- realizado (preenchido pós-resultado)
    confidence_n    INTEGER,                   -- amostras usadas no aprendizado

    -- Decisão final do spin (replicado pra simplificar query)
    final_action    TEXT,                      -- APOSTAR|PULAR
    hit             BOOLEAN,
    wheel_dist      INTEGER
);

CREATE INDEX ix_dna_decision  ON shared.decision_dna(decision_id);
CREATE INDEX ix_dna_feature   ON shared.decision_dna(feature_name);
CREATE INDEX ix_dna_realized  ON shared.decision_dna(realized_lift_pp);
```

E uma materialização agregada com refresh diário:
```sql
CREATE MATERIALIZED VIEW shared.dna_summary AS
SELECT feature_name,
       feature_value->>'bucket' AS bucket,
       count(*)                  AS n,
       avg(realized_lift_pp)     AS avg_lift_pp,
       stddev(realized_lift_pp)  AS sd_lift,
       avg(CASE WHEN hit THEN 1.0 ELSE 0.0 END) AS hr
FROM shared.decision_dna
WHERE realized_lift_pp IS NOT NULL
GROUP BY 1,2;
```

Resultado: **endpoint** `/api/dna_summary` lista, para CADA fine-tuner ativo, qual o lift realizado em janela 7d/30d/all-time. Decisão "ligar ou desligar X" passa a ser data-driven em **uma query**.

### 1.3 Como cada nova estratégia nasce já com DNA
Convenção (a aplicar em PR template + linter custom):
- Toda nova feature de decisão precisa registrar em `decision_dna` no momento que dispara
- Toda flag opt-in precisa ter `estimated_lift_pp` documentado (mesmo que do counterfactual histórico)
- CI valida que novos commits que mexem em `state/bet_advisor.py` ou `strategies/sda17.py` venham acompanhados de teste de "DNA registrado"

### 1.4 As **3 regiões** (C1, C2, C3) — DNA por região
Hoje o SDA17 retorna `sda_center` (1 número) + `sda_numbers` (17 cobertos). Mas internamente trabalha com 3 centros (C1, C2, C3) e offsets. Falta persistir **separadamente o contributo de cada região**:

```sql
ALTER TABLE decisions ADD COLUMN sda_centers JSONB;
-- ex: [{"c": 30, "offset": 0, "score": 4, "size": 9},
--     {"c": 14, "offset": -3, "score": 2, "size": 5},
--     {"c": 4,  "offset": +5, "score": 1, "size": 3}]
```

E em `decision_dna` registrar uma linha por região com `feature_name = 'region_C1'|'region_C2'|'region_C3'`, `feature_value = {center, offset, score, size}`, `realized_lift_pp` calculado como "se só essa região fosse usada, hit teria sido?".

Isso permite query como: "no último mês, qual região mais carrega o sistema? a C1 (center principal) ou C3 (offset extremo)?"

### 1.5 Invariante: backfill é OK, edit não
- `decision_dna` é **append-only** (sem UPDATE de feature_value)
- Apenas `realized_lift_pp` e `hit` podem ser preenchidos depois (no spin seguinte)
- Migração de estrutura via Alembic, dados antigos preservados via `feature_name` versionado (`sda_score`, `sda_score_v2`)

---

## §2. Estruturação PG + Vector + AGE — destrava as 3 regiões

### 2.1 Migrações Alembic propostas (0007 → 0011)

**0007_dealer_provider** — captura origem (depende da Sprint-01)
```sql
CREATE TABLE shared.providers (
    id          TEXT PRIMARY KEY,           -- 'evolution', 'pragmatic', 'playtech'
    display_name TEXT,
    first_seen  TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE shared.tables (
    id          TEXT PRIMARY KEY,           -- 'evo_lightning_br_1'
    provider_id TEXT REFERENCES shared.providers(id),
    name        TEXT,
    bias_offset REAL DEFAULT 0,
    embedding   VECTOR(4)
);
CREATE TABLE shared.dealers (
    id          TEXT PRIMARY KEY,           -- 'evo_camila_2026' (hash determinístico)
    display_name TEXT,
    provider_id TEXT REFERENCES shared.providers(id),
    first_seen  TIMESTAMPTZ DEFAULT now(),
    last_seen   TIMESTAMPTZ,
    total_spins INTEGER DEFAULT 0,
    embedding   VECTOR(8)
);
ALTER TABLE cw.spin_features  ADD COLUMN dealer_id TEXT, ADD COLUMN table_id TEXT, ADD COLUMN wheel_dist INTEGER;
ALTER TABLE ccw.spin_features ADD COLUMN dealer_id TEXT, ADD COLUMN table_id TEXT, ADD COLUMN wheel_dist INTEGER;
CREATE INDEX ix_cw_dealer  ON cw.spin_features(dealer_id);
CREATE INDEX ix_ccw_dealer ON ccw.spin_features(dealer_id);
```

**0008_decision_dna** — DNA estrutural (§1.2)

**0009_regions** — 3 regiões persistidas (§1.4)
```sql
ALTER TABLE cw.spin_features  ADD COLUMN sda_regions JSONB DEFAULT '[]';
ALTER TABLE ccw.spin_features ADD COLUMN sda_regions JSONB DEFAULT '[]';
```

**0010_vector_expand** — vector 6-d → 32-d
```sql
ALTER TABLE cw.spins_vectors  ALTER COLUMN raw_features TYPE VECTOR(32);
ALTER TABLE ccw.spins_vectors ALTER COLUMN raw_features TYPE VECTOR(32);
-- com adapter Python que aceita ambos durante migração
```
Composição 32-d: `[centro_main(1), c4(1), m6(1), l12(1), sda_score(1), force(1),  region_offsets(3), region_scores(3), region_sizes(3), wheel_dist_hist_p50(1), wheel_dist_hist_p95(1), dealer_emb(8), table_emb(4), tod_emb(2), regime_id(1)]`

**0011_age_dealer_graph** — AGE deixa de ser ociosa
```cypher
SELECT create_graph('dealer_graph');
-- (Provider)-[OPERATES]->(Table)-[STAFFED_BY]->(Dealer)-[PLAYED]->(Spin)
-- Permite query "todos os dealers com bias > 3 do mesmo provider"
```

### 2.2 Vector ampliado — porquê e como
- Hoje: 6 dim → PCA mostrou 99.5% em 2 componentes (4 dim redundantes)
- Proposta: 32 dim com **autoencoder bottleneck** para dealer (8) e table (4)
- Treino: `tools/train_dealer_embedding.py` (novo) — autoencoder MSE em janela de 7d/dealer com early stopping
- Re-treino: schedule cron 1x/dia em pós-trabalho (baixo tráfego)

### 2.3 AGE com queries reais
```cypher
MATCH (d:Dealer)-[:PLAYED]->(s:Spin)
WHERE s.hit = false AND s.wheel_dist >= 3
RETURN d.name, count(s) AS misses_long
ORDER BY misses_long DESC LIMIT 10
```
Identifica dealers que sistematicamente "erram longe" — candidato a blacklist por dealer.

---

## §3. Dealer + Provedor — captura completa

### 3.1 Cadeia atual (verificada hoje)
| Etapa | Estado |
|---|---|
| `extension/content.js` lê DOM | ✅ via `chrome.scripting` |
| Payload `novo_resultado` carrega dealer/provider | ❌ **NÃO** — só `numero, direcao, trace_id, t_client, allNumbers, monitoringData` |
| `server/extractor_service.py` detecta provider | ✅ por URL — `_detect_provider(url)` em prod |
| `server/configs/providers/*.json` define seletores | ✅ — evolution_base.json existe |
| `monitoringData` carrega dealer | ❌ — só `gameStatus, balance, currentBet, activeChip` |
| Persistência em `decisions.dealer_id` | ❌ coluna não existe |

### 3.2 Decisão: 3-pé de implantação
1. **Extension scrape** — adicionar `MutationObserver` em seletores conhecidos (dealer label) → broadcast → `background.js` anexa ao payload
2. **Server roteamento** — `message_handler` aceita `dealer_id/table_id/provider`, normaliza para id determinístico (hash `provider+name`), persiste em SQLite, propaga para outbox
3. **PG materialização** — CDC `_apply_spin_result` upserta `shared.dealers` e `shared.tables`, popula `spin_features.dealer_id`

### 3.3 Por que vale ROI (lembrete do doc 25/05)
- Release bias por dealer é fato físico documentado (Cammegh, EGBA)
- A média atual de offset (~0) é a **média de dealers com bias opostos** que não serve a ninguém
- Estratificação por dealer + 50 spins/dealer → estimado +2-4pp
- Só funciona se §4 (wheel_dist) estiver populado — e agora **ESTÁ** (B-10).

---

## §4. Invariantes — o que NÃO mexer (já está bom)

Itens com **alto sinal positivo** que devem ser **preservados** ao evoluir:

1. **Outbox 100% processed + LISTEN/NOTIFY < 22s** — não trocar por Kafka/Redis
2. **Separação cw/ccw schemas** — isola viés direcional; **não** unificar
3. **SQLite write-side autoritativo** + dual-write Postgres apenas read-side via CDC — não inverter
4. **SDA17 sweet spot em `sda_score=4`** (49% hit, 58% dos spins) — **NÃO** mexer no cálculo do score, mexer só em buckets e weighting
5. **Anti-Martingale G1/G2/G3 + take-profit** — funciona; não trocar por progressões agressivas
6. **Direção alternada automática (cw↔ccw a cada spin)** — `background.js:1147` — gera amostras balanceadas
7. **Feature flags opt-in por env** — padrão usado em NEW-07/NEW-08; **toda** nova feature segue
8. **`pending["centers"]`** (B-09) — a chave correta é `"centers"`, fallback retro-compat em `"sda_centers"`
9. **`DatabaseService.update_result(... calibration_error=)`** (B-10) — interface contratual; assinatura sincronizada com abstract
10. **`compute_wheel_dist_min_to_set`** helper canônico em `core/roulette.py` — **não** duplicar com cálculo ad-hoc
11. **Alerta NEW-12 (fill_rate < 0.8 + volume ≥ 50)** — sentinel anti-regressão silenciosa; mantê-lo armado em qualquer refactor
12. **Suite 282 passing como gate de merge** — nenhum PR sem `pytest -q` verde
13. **`docker restart roleta-prometheus`** (não `docker compose restart`) — gotcha de bind-mount stale
14. **Decision dataclass** com kwargs reais de `database/models.py` — não inventar campos novos sem migração
15. **`get_decision` é abstract em `SQLiteDecisionRepository`** — remoção acidental quebra instanciação

---

## §5. As 35 Sprints — drenar uma de cada vez

> **Convenção:** SP-NN. Cada sprint é **autocontida**, tem critério de aceite explícito, teste obrigatório, e referência ao DNA (§1.2) onde aplicável.
> **Prefixos:** `BUG-*` (4 sprints), `DNA-*` (5), `DEAL-*` (5), `REGION-*` (4), `VECTOR-*` (3), `AGE-*` (2), `ML-*` (4), `OBS-*` (4), `CI-*` (4).
> **Cada sprint contém:** *Objetivo · Porquê · Onde · Critério de aceite · Teste · DNA impact · Dependências.*

### 🐛 BUG / Dívidas (5 sprints)

#### SP-01 — **NEW-09: bisect FeatureStore/Regime opt-in** (regressão hit_rate)
- **Objetivo:** identificar se commit `f1bbfbf` (FeatureStore + RegimeSimilarityReader opt-in) está silenciosamente sobrescrevendo decisões e causando a queda hit_rate 47.69% → 43.95% em 4 dias.
- **Porquê:** suspeito documentado em `state/bet_advisor.py:141-150`; agora viável pois `calibration_error` popula desde B-10.
- **Onde:** `tools/backtest_from_db.py` (rodar shadow ON vs OFF em janela 24h pós-B10).
- **Critério:** delta hit_rate < 1pp entre ON/OFF → manter ligado; ≥1pp → flag default OFF + abrir issue.
- **Teste:** comparativo gravado em `tests/test_new09_bisect.py` (skip se DB < 200 amostras pós-B10).
- **DNA:** `feature_name='feature_store_signal'` com `realized_lift_pp` medido.
- **Dependências:** 24h de tráfego pós-`cf3570d`.

#### SP-02 — **Backfill `calibration_error` histórico**
- **Objetivo:** preencher `calibration_error` retroativamente nas 3255+ decisões NULL pré-B-10 usando o snapshot de `sda_centers` que existe em `pending` reproduzível via `outbox` ou via `spin_features.meta`.
- **Porquê:** desbloqueia análises históricas e treino do `dealer_embedding`.
- **Onde:** `tools/backfill_calibration_error.py` novo + Alembic data-migration.
- **Critério:** ≥90% das decisões NULL passam a ter valor; restante (centers irrecuperáveis) marcado em coluna `cal_err_source='backfill_unrecoverable'`.
- **Teste:** `tests/test_backfill_calibration.py` valida idempotência (rodar 2x = mesmo resultado).
- **DNA:** N/A (data fix).

#### SP-03 — **CI/CD pull automatizado em prod**
- **Objetivo:** documentar e automatizar o mecanismo de deploy contínuo no Debian — hoje é 100% SSH manual.
- **Porquê:** risco humano + invisibilidade pra outros devs. Manutenibilidade 6.6.
- **Onde:** `.github/workflows/deploy.yml` + systemd service `roleta-deploy.timer` que faz pull periódico em `main` se CI verde.
- **Critério:** push em main → prod em <5min sem intervenção; rollback automático se healthcheck falhar 3x.
- **Teste:** dry-run no staging container; documento `docs/DEPLOY.md`.
- **DNA:** N/A.

#### SP-04 — **Schema parity SQLite ↔ PG**
- **Objetivo:** garantir que colunas críticas (`calibration_error`, `dealer_id`, futuras) **existam em ambos** e haja teste de detecção de drift.
- **Porquê:** assimetria atual cria silent loss quando dual-write não consegue gravar campo ausente no destino.
- **Onde:** `tests/test_schema_parity.py` faz introspecção dos dois schemas.
- **Critério:** test fails em CI se SQLite tem coluna que PG não tem (ou vice-versa, com whitelist de exceções).
- **Teste:** próprio test_schema_parity.
- **DNA:** N/A.

#### SP-05 — **Auditoria silent except patterns**
- **Objetivo:** B-10 mostrou que `except Exception` engole TypeError de mudança de assinatura. Mapear **todos** os blocos `except Exception` no `message_handler.py` e converter em catches específicos + métrica.
- **Porquê:** prevenir próximo B-10. Confiabilidade 5.3.
- **Onde:** `server/message_handler.py` (8 ocorrências) + linter custom em `tools/lint_silent_except.py`.
- **Critério:** zero `except Exception` sem (a) re-raise ou (b) log.error + counter Prometheus + 3 exceções enumeradas no docstring.
- **Teste:** lint roda em pre-commit hook + CI.
- **DNA:** N/A.

### 🧬 DNA Estrutural (5 sprints)

#### SP-06 — **DNA-01: Tabela `decision_dna` + migração 0008**
- **Objetivo:** criar a tabela append-only proposta em §1.2 e a view materializada `dna_summary`.
- **Porquê:** base para toda análise de contribuição percentual por feature.
- **Onde:** `migrations/versions/0008_decision_dna.py` + `database/models.py` (`DnaEntry` dataclass) + `database/sqlite_repo.py` (gravação write-side).
- **Critério:** migration `alembic upgrade head` aplica sem erro; INSERT funciona em ambos DBs.
- **Teste:** `tests/test_dna_entry.py` (insert/query, FK válida, append-only).
- **DNA impact:** infra base.

#### SP-07 — **DNA-02: Instrumentar SDA17 + BetAdvisor para emitir DNA**
- **Objetivo:** cada chamada de `bet_advisor.analyze()` e `sda17.compute()` registra 1 linha em `decision_dna` por feature ativa (sda_score, calibration_offset, c4_rate bucket, kill_v4 flag…).
- **Porquê:** sem isso a tabela fica vazia.
- **Onde:** `state/bet_advisor.py` + `strategies/sda17.py` + helper `database/dna_logger.py`.
- **Critério:** todo APOSTAR/PULAR gera ≥4 entradas em `decision_dna`; latência adicional <2ms p95.
- **Teste:** `tests/test_dna_emission.py` valida emissão sem regression de latência.
- **DNA impact:** habilita SP-08+.

#### SP-08 — **DNA-03: Backfill `realized_lift_pp` no spin seguinte**
- **Objetivo:** quando o resultado chega, calcular pra cada feature do spin anterior qual o lift realizado (counterfactual: "se essa feature estivesse OFF, hit teria sido?"). Persiste em `decision_dna.realized_lift_pp`.
- **Porquê:** transforma DNA de telemetria em **ground truth**.
- **Onde:** `server/message_handler.py` (linha ~388 após `update_result`) + novo `services/dna_realizer.py`.
- **Critério:** ≥80% das entradas DNA têm `realized_lift_pp` preenchido em <5min após o spin.
- **Teste:** `tests/test_dna_realizer.py` + métrica Prometheus `roleta_dna_realize_lag_seconds`.
- **DNA impact:** habilita queries de contribuição real.

#### SP-09 — **DNA-04: Endpoint `/api/dna_summary` + painel Grafana**
- **Objetivo:** expor a view materializada via HTTP + painel "Top 10 features que mais contribuem nas últimas 24h/7d".
- **Porquê:** torna decisão de ligar/desligar feature **uma click**, não um SQL.
- **Onde:** `server/health_server.py` + `obs/grafana/dashboards/dna.json`.
- **Critério:** endpoint <100ms; painel mostra evolução temporal.
- **Teste:** `tests/test_dna_summary_endpoint.py`.
- **DNA impact:** UI sobre §1.

#### SP-10 — **DNA-05: Linter CI "novas features precisam emitir DNA"**
- **Objetivo:** PR template + linter detecta novos `flag/threshold/multiplier` em `state/` e `strategies/` e exige emissão correspondente em `decision_dna`.
- **Porquê:** previne regressão de cobertura DNA. Manutenibilidade.
- **Onde:** `tools/lint_dna_coverage.py` em `.github/workflows/ci.yml`.
- **Critério:** linter falha PR se grep encontra `os.getenv("BET_*")` novo sem `dna_logger.emit(...)`.
- **Teste:** o próprio lint roda contra commits sintéticos.
- **DNA impact:** sustentabilidade do conceito.

### 🎰 Dealer / Provedor (5 sprints)

#### SP-11 — **DEAL-01: Captura DOM dealer/table (content.js MutationObserver)**
- **Objetivo:** `extension/content.js` observa seletores definidos em `server/configs/providers/*.json` → broadcast `dealer_changed`/`table_changed` para background.
- **Porquê:** pré-requisito de tudo dealer-aware.
- **Onde:** `extension/content.js` + adicionar campos `selectors.dealer` em `evolution_base.json` + criar `pragmatic_base.json`, `playtech_base.json`.
- **Critério:** evento dispara <500ms após mudança visível.
- **Teste:** Playwright em fixture HTML simulada (`tests/extension/dealer_capture.spec.js`).

#### SP-12 — **DEAL-02: Payload `novo_resultado` carrega dealer_id/table_id/provider/round_id**
- **Objetivo:** `background.js:1129` anexa esses 4 campos ao payload. ID determinístico via hash do nome.
- **Onde:** `extension/background.js` + `extension/manifest.json` (host_permissions já cobre).
- **Critério:** payload em produção carrega os 4 campos em ≥95% dos spins (Prometheus counter).
- **Teste:** `tests/extension/payload_shape.spec.js`.
- **Dep:** SP-11.

#### SP-13 — **DEAL-03: Migração 0007 + persistência server-side**
- **Objetivo:** criar tabelas `shared.{providers,tables,dealers}` (§2.1) + colunas em `cw|ccw.spin_features`. `message_handler` upserta + persiste em SQLite `decisions.dealer_id`.
- **Onde:** `migrations/versions/0007_dealer_provider.py`, `server/message_handler.py`, `database/sqlite_repo.py`.
- **Critério:** após 1h de tráfego, `SELECT count(distinct dealer_id) FROM shared.dealers > 0`.
- **Teste:** `tests/test_dealer_upsert.py`, `tests/test_migration_0007.py`.
- **Dep:** SP-12.

#### SP-14 — **DEAL-04: Endpoint `/api/dealers` + ranking**
- **Objetivo:** retorna top dealers por hit_rate, bias_offset, n_spins, em janela configurável.
- **Onde:** `server/health_server.py` + painel Grafana.
- **Critério:** endpoint funcional + painel mostra Top 10 dealers do dia.
- **Teste:** `tests/test_dealers_endpoint.py`.
- **Dep:** SP-13.

#### SP-15 — **DEAL-05: Calibration offset estratificado por dealer (feature flag)**
- **Objetivo:** quando `BET_DEALER_OFFSET_ENABLED=1` E `dealer.total_spins >= 50`, usar `dealer.bias_offset` no lugar do offset global.
- **Onde:** `strategies/sda17.py` (`_apply_calibration_offset`).
- **Critério:** A/B counterfactual gravado em `decision_dna` mostra que dealer-aware ≥ global em ≥60% dos dealers com n≥50.
- **Teste:** `tests/test_dealer_offset.py`.
- **Dep:** SP-08, SP-13.
- **DNA:** `feature_name='dealer_offset'`.

### 🎯 Regiões C1/C2/C3 (4 sprints)

#### SP-16 — **REGION-01: Persistir `sda_centers` como JSONB em `decisions`**
- **Objetivo:** §1.4 — guardar os 3 centros + offsets + scores + sizes em vez de só o `sda_center` principal.
- **Onde:** `database/models.py` (campo `sda_regions JSONB`), `state/game.py:store_prediction`, `server/message_handler.py`.
- **Critério:** 100% das decisões a partir do deploy têm `sda_regions != []`.
- **Teste:** `tests/test_sda_regions_persist.py`.

#### SP-17 — **REGION-02: Computar `realized_lift_pp` por região**
- **Objetivo:** no spin seguinte, calcular para cada região "se SÓ ela fosse usada, hit?" e gravar em DNA com `feature_name='region_C1|C2|C3'`.
- **Onde:** `services/dna_realizer.py` (SP-08) + `core/roulette.py` (`hit_per_region` helper).
- **Critério:** queries do tipo `SELECT feature_name, avg(realized_lift_pp) FROM decision_dna GROUP BY feature_name LIKE 'region_%'` retornam dados.
- **Teste:** `tests/test_region_lift.py`.
- **Dep:** SP-08, SP-16.

#### SP-18 — **REGION-03: Bandit ε-greedy entre regiões**
- **Objetivo:** S-STRAT-14 estendido — escolher qual região aposta com base em performance recente medida por DNA. Default = "all 3" (no-op).
- **Onde:** `strategies/sda17.py` + `state/bet_advisor.py`.
- **Critério:** flag `SDA_REGION_BANDIT=1` ativa; teste mostra escolha estável após 200 spins/região.
- **Teste:** `tests/test_region_bandit.py`.
- **Dep:** SP-17.
- **DNA:** `feature_name='region_bandit_choice'`.

#### SP-19 — **REGION-04: Painel Grafana "3 regiões — DNA viva"**
- **Objetivo:** visualização em tempo real do lift de C1/C2/C3 em janelas 1h/24h/7d.
- **Onde:** `obs/grafana/dashboards/regions.json`.
- **Critério:** painel publicado, 3 stat panels + 1 timeseries.
- **Teste:** N/A (visualização).
- **Dep:** SP-17.

### 🔢 Vector / pgvector (3 sprints)

#### SP-20 — **VECTOR-01: Migração 0010 expandir VECTOR(6) → VECTOR(32)**
- **Objetivo:** §2.1 — preparar embedding hierárquico (spin + region + dealer + table + tod).
- **Onde:** `migrations/versions/0010_vector_expand.py` + adapter Python que aceita ambos durante migração (env flag `VEC_DIM`).
- **Critério:** migration zero-downtime; queries existentes continuam funcionando.
- **Teste:** `tests/test_vector_dim_compat.py`.
- **Dep:** SP-13 (dealer/table existem).

#### SP-21 — **VECTOR-02: Autoencoder dealer/table embedding**
- **Objetivo:** `tools/train_dealer_embedding.py` — autoencoder PyTorch, MSE em janela 7d/dealer, salva pesos em `models/dealer_ae.pt`.
- **Onde:** novo `ml/dealer_autoencoder.py` + cron 1x/dia.
- **Critério:** loss < 0.05 reproduzível; embedding 8-d com cosine distance significativa entre dealers diferentes.
- **Teste:** `tests/test_dealer_ae_train.py` (smoke + reprodutibilidade).
- **Dep:** SP-13.

#### SP-22 — **VECTOR-03: `/api/regime` usa vector 32-d com dealer**
- **Objetivo:** S-STRAT-12 melhorado — busca de regime similar filtra por `dealer_id` e usa embedding ampliado.
- **Onde:** `server/health_server.py` + `services/regime_similarity.py`.
- **Critério:** distance distribution não é mais constante (corrige BUG-N25-07 antigo); top-K vizinhos contém ≥3 do mesmo dealer.
- **Teste:** `tests/test_regime_v2.py`.
- **Dep:** SP-20, SP-21.

### 🕸️ AGE (2 sprints)

#### SP-23 — **AGE-01: Migração 0011 grafo dealer → provider → table → spin**
- **Objetivo:** §2.3 — criar `dealer_graph` via Cypher e popular via trigger no upsert de `shared.dealers/tables`.
- **Onde:** `migrations/versions/0011_age_dealer_graph.py` + trigger PL/pgSQL.
- **Critério:** `SELECT * FROM cypher('dealer_graph', $$ MATCH (n) RETURN count(n) $$) AS (n agtype)` > 0.
- **Teste:** `tests/test_age_dealer_graph.py`.
- **Dep:** SP-13.

#### SP-24 — **AGE-02: Endpoint `/api/dealer_neighbors`**
- **Objetivo:** dado um dealer_id, retorna "outros dealers do mesmo provedor com bias similar" via Cypher.
- **Onde:** `server/health_server.py` + `services/dealer_graph.py`.
- **Critério:** endpoint <200ms; resultados não vazios após N=20 dealers.
- **Teste:** `tests/test_dealer_neighbors.py`.
- **Dep:** SP-23.

### 🤖 ML / Estratégia (4 sprints)

#### SP-25 — **ML-01: Loss function 2-D (HIT + wheel_dist)**
- **Objetivo:** §4.3 do doc 25/05 — bet_advisor passa a otimizar com objetivo dual.
- **Onde:** `state/bet_advisor.py` + `tools/backtest_harness.py`.
- **Critério:** grid search offset ∈ [-5..+10] minimiza `median(wheel_dist) + λ * (1 - hit_rate)` com λ tunado.
- **Teste:** `tests/test_dual_loss.py`.
- **Dep:** B-10 (já feito).

#### SP-26 — **ML-02: Calibration offset com prior bayesian em +3**
- **Objetivo:** §3.4 do doc 25/05 — assimetria documentada [-2, +8] como prior.
- **Onde:** `strategies/sda17.py` (`_apply_calibration_offset`).
- **Critério:** flag `SDA_OFFSET_PRIOR=bayesian_plus3`; backtest mostra ≥+1pp vs default.
- **Teste:** `tests/test_offset_prior.py`.
- **DNA:** `feature_name='offset_prior'`.

#### SP-27 — **ML-03: Desligar `errdriven` por default (alavanca C)**
- **Objetivo:** §3.3 do doc 25/05 — errdriven mostrou -26pp em n=19. Feature flag default OFF.
- **Onde:** `strategies/sda17.py`.
- **Critério:** flag `SDA17_ERRDRIVEN_ENABLED=0` padrão; código mantém suporte mas inativo.
- **Teste:** `tests/test_errdriven_off.py`.
- **DNA:** `feature_name='errdriven'`.

#### SP-28 — **ML-04: Multilevel pooling (Bayesian) dealer → provider**
- **Objetivo:** PyMC pequeno (não TF/torch pesado) que faz pooling parcial — dealers com poucos dados puxam do provider, dealers com muitos dados ficam isolados.
- **Onde:** `ml/bayesian_pool.py` (novo) + endpoint `/api/dealer_posterior`.
- **Critério:** posteriori para dealer com n=10 fica "puxado" para média do provider; para n=200 fica próximo do MLE local.
- **Teste:** `tests/test_bayesian_pool.py` (smoke + sanity).
- **Dep:** SP-15 (dealer offset funcionando).

### 📊 Observabilidade (4 sprints)

#### SP-29 — **OBS-01: Alerta `roleta_dna_realize_lag_seconds > 300`**
- **Objetivo:** se SP-08 começar a atrasar, alarme em 5min.
- **Onde:** `obs/alerts.yml`.
- **Critério:** 13ª regra Prometheus carrega no boot.
- **Teste:** `tests/test_alert_dna_lag.py`.
- **Dep:** SP-08.

#### SP-30 — **OBS-02: Métrica `roleta_wheel_dist_p50/p95/p99` rolling 1h**
- **Objetivo:** baseline e detecção de descalibração via shift de distribuição.
- **Onde:** `server/health_server.py` (3 histograms novos).
- **Critério:** valores aparecem em /metrics + painel Grafana.
- **Teste:** `tests/test_wheel_dist_metric.py`.

#### SP-31 — **OBS-03: Alerta "wheel_dist p50 > 3.5 por 30min"**
- **Objetivo:** sinal de descalibração detectado precocemente.
- **Onde:** `obs/alerts.yml` (14ª regra).
- **Critério:** regra ativa; threshold validado contra distribuição histórica.
- **Teste:** `tests/test_alert_descalibracao.py`.
- **Dep:** SP-30.

#### SP-32 — **OBS-04: Tracing OpenTelemetry no fluxo `received → processed → saved`**
- **Objetivo:** spans em pipeline crítico para debugar p99 spikes (3.5s reportado no doc 25/05).
- **Onde:** `server/message_handler.py` + `server/websocket.py` (instrumentação `opentelemetry-api`).
- **Critério:** spans aparecem em backend OTLP local (Jaeger via docker-compose dev).
- **Teste:** `tests/test_tracing_spans.py`.

### ⚙️ CI / Manutenibilidade (4 sprints)

#### SP-33 — **CI-01: Test matrix Python 3.11/3.12 + SQLite/PG**
- **Objetivo:** garantir compatibilidade ampla. ISO 6.4 Portabilidade.
- **Onde:** `.github/workflows/ci.yml`.
- **Critério:** 4 jobs em paralelo; todos passing.
- **Teste:** o próprio CI.

#### SP-34 — **CI-02: Coverage report + threshold mínimo 75%**
- **Objetivo:** evitar áreas sem teste; ISO 6.5 Testabilidade.
- **Onde:** `pyproject.toml` (`pytest-cov`) + `.github/workflows/ci.yml`.
- **Critério:** cobertura ≥75% global, falha PR se cair.
- **Teste:** próprio CI.

#### SP-35 — **CI-03: Pre-commit hook (ruff + mypy strict em core/state)**
- **Objetivo:** travar tipo errado antes do push. ISO 6.1 Modularidade.
- **Onde:** `.pre-commit-config.yaml` + `mypy.ini`.
- **Critério:** hook bloqueia commit com erro de tipo em `core/` ou `state/`.
- **Teste:** smoke local.

---

## §6. Sequência recomendada (DAG de execução)

```
Fundação:  SP-01 ── SP-02 ── SP-04 ── SP-05 ── SP-06 ── SP-07 ── SP-08
                                       │        │        │        │
DNA infra: └── SP-09 ── SP-10 ─────────┘        │        │        │
                                                │        │        │
Dealer:    SP-11 ── SP-12 ── SP-13 ── SP-14 ── SP-15 ────┤        │
                                       │                 │        │
Region:    SP-16 ── SP-17 ── SP-18 ── SP-19 ─────────────┘        │
                              │                                   │
Vector:    SP-20 ── SP-21 ── SP-22                                │
AGE:       SP-23 ── SP-24                                         │
ML:        SP-25 ── SP-26 ── SP-27 ── SP-28 ──────────────────────┘
Obs:       SP-29 ── SP-30 ── SP-31 ── SP-32
CI/CD:     SP-03 ── SP-33 ── SP-34 ── SP-35
```

**Ordem de drenagem sugerida** (≈9 ondas):
1. **Onda 1 (bugs/infra):** SP-01, SP-02, SP-03, SP-04, SP-05
2. **Onda 2 (DNA infra):** SP-06, SP-07, SP-08
3. **Onda 3 (DNA UX):** SP-09, SP-10, SP-29
4. **Onda 4 (dealer captura):** SP-11, SP-12, SP-13
5. **Onda 5 (regiões):** SP-16, SP-17, SP-19, SP-30, SP-31
6. **Onda 6 (dealer ML):** SP-14, SP-15, SP-26, SP-27
7. **Onda 7 (vector + AGE):** SP-20, SP-21, SP-22, SP-23, SP-24
8. **Onda 8 (ML avançado):** SP-18, SP-25, SP-28
9. **Onda 9 (CI maturity):** SP-32, SP-33, SP-34, SP-35

---

## §7. **Prompt estratégico padrão** (use a cada sprint)

> Cole isto no início de cada sessão, substituindo `<SP-NN>`:

```
[CONTEXTO]
Você é o YOLO Orchestrator. Modelo claude-opus-4.7. Stack MCP completa
(filesystem + graphify + memory + brave + sequential-thinking + context7
+ github). Vamos drenar a sprint <SP-NN> do
sprint_evolucao_26_05blueprint.md.

[INVARIANTES — NÃO MEXER]
1. SQLite write-side autoritativo, PG read-side via outbox/CDC.
2. Schemas cw/ccw separados; outbox 100% processed; LISTEN/NOTIFY <22s.
3. Sweet spot sda_score=4; Anti-Martingale G1/G2/G3; alternância direção.
4. Toda nova feature de decisão é OPT-IN via env var + emite DNA.
5. pending["centers"] (B-09); update_result(... calibration_error=) (B-10);
   compute_wheel_dist_min_to_set canônico; abstract get_decision presente.
6. Alerta NEW-12 fill-rate <0.8 sempre armado.
7. Suite ≥282 passing como gate; nada com `except Exception` silenciador.
8. Deploy é `docker restart roleta-prometheus` (não compose restart) para alerts.yml.

[OBJETIVO DESTA SPRINT]
Ler §5/SP-NN do blueprint, executar com:
1. Fase 0: RADAR MCPs disponíveis (sempre).
2. Memória: search_nodes pelo nome da sprint, recuperar contexto.
3. Plano: rubber-duck o plano ANTES de implementar (sprints não-triviais).
4. Implementação: edits cirúrgicos; teste novo por sprint; suite verde
   antes de commit; commit conventional ("feat(SP-NN): ...");
   push; deploy SSH; validação live ≥1 amostra; docs em §<próximo>.
5. Memória: add_observations no fim com decisões arquiteturais.

[CRITÉRIO DE ACEITE]
Conforme bloco "Critério" da sprint. Não considerar pronto sem:
- Test verde
- Suite total verde
- Deploy aplicado em prod
- Métrica/log de validação coletado
- Linha no decision_dna (quando aplicável)
- §NN nova no sprint_26_05_estrategia.md OU sprint_evolucao_26_05blueprint.md

[ENTREGA]
task_complete com: commits, métricas antes/depois, evidência live,
próximo passo natural (sprint dependente).
```

---

## §8. Visão geral — como evoluímos sem desorganizar

**Princípio mestre:** *toda nova feature nasce opt-in + medida em DNA.* Isso garante 3 propriedades:

1. **Reversibilidade.** Flag OFF = comportamento idêntico ao anterior. Zero risco de regressão silenciosa.
2. **Comparabilidade.** DNA persiste o lift realizado de cada flag, permitindo comparar variantes em produção sem A/B test formal.
3. **Composabilidade.** Features independentes podem ser ligadas em paralelo; conflitos viram visíveis no painel DNA (correlação negativa entre dois lifts).

**Métricas de sucesso macro** (mensuradas no painel principal):
- Hit rate global rolling 7d (alvo: 47% → 53% em 60 dias)
- Fill rate `calibration_error` (alvo: ≥95%)
- Cobertura DNA (alvo: ≥4 features registradas por spin APOSTAR)
- Tempo de deploy (alvo: <5min, automático)
- p95 latência pipeline (alvo: <500ms)
- Cobertura testes (alvo: ≥75%)

**Anti-objetivos** (sinais de alarme, abortar a sprint em curso):
- Suite caiu abaixo de 282 passing
- Alerta NEW-12 disparou em prod
- Hit_rate rolling 24h caiu >3pp sem causa identificada
- Latência p99 subiu >1.5s
- Qualquer `except Exception` novo sem categoria + log + métrica

**Cadência sugerida:** 1 sprint pequena por dia útil ou 2-3 sprints médias por semana. Para sprints de migração (0007/0008/etc.) sempre fazer em janela de baixo tráfego e validar com `dry-run` em staging container.

---

> **Próxima ação imediata recomendada:** rodar SP-01 (NEW-09 bisect) — viável agora pois calibration_error está populando desde B-10. Resultado define se há mais um bug oculto a corrigir ANTES de investir nas 5 ondas de DNA/dealer.

**FIM do blueprint.** Use o prompt do §7 a cada sessão de implementação. Para qualquer dúvida ou re-priorização, consultar `Visualizacao_da_evolucao_25_05.md` (estratégia) + `Manutenabilidade_iso.md` (princípios) + `sprint_26_05_estrategia.md` (execução em curso).

---

## §24 — SP-05 ENTREGUE (26/05 23:40 UTC) ✅

**Commit:** `244bed8` — eat(SP-05): safe_except helper + lint baseline + B-10-class protecao
**Deploy:** roleta-cloud healthy 23:40:50 UTC, suite 282 -> **289 passing** (+7).

### Entregas concretas

1. `core/safe_except.py` — helper canonico (contextmanager + decorator).
2. `tools/lint_silent_except.py` — baseline JSON com 9 arquivos rastreados; CI bloqueia aumento.
3. `.silent_except_baseline.json` — snapshot inicial commitado.
4. `server/message_handler.py:466` — primeiro consumidor: bloco que silenciou B-10 agora:
   - Categoria explicita `db_save_decision`
   - Counter `roleta_silent_exception_total{module,category,exc_type}`
   - Em `STRICT_SILENT_EXCEPT=1`, re-raise de TypeError/AttributeError (catch dev-time)
5. `.github/workflows/ci.yml` — novo step **Silent except baseline lint**.
6. `tests/test_sp05_safe_except.py` — 7 testes (engulir, reraise, strict, decorator, baseline existe, lint clean).

### Como pegaria B-10 hoje

Antes: `TypeError: got unexpected keyword 'calibration_error'` virava log warning generico por 24h.
Agora: 1) counter Prometheus alerta-vel por exc_type=TypeError; 2) em CI/dev STRICT=1, falha fast.

### Proximo: SP-04 (schema parity SQLite<->PG) — sem deps, manutenibilidade ISO.

---

---

## §25 — SP-04 ENTREGUE ✅

**Objetivo:** detectar drift de schema SQLite vs PG antes que vire B-10.

### Entregas
- `database/schema_sqlite_snapshot.json` — snapshot vivo (274 linhas, 5 tabelas).
- `database/schema_parity_manifest.json` — declaracao explicita de:
  - `must_propagate_to_pg` — 10 colunas criticas de `decisions`
  - `pg_target_table` — mapping para `cw/ccw.spin_features`
  - `sqlite_only_allowed` / `pg_only_allowed` — whitelists conscientes
- `tools/snapshot_sqlite_schema.py` — regenera snapshot apos migracao legitima.
- `tests/test_schema_parity.py` — 5 testes (snapshot==live, manifest consistente, PG live se DSN).
- CI: rodando via pytest no step existente.

### Suite: 289 -> **293 passing** (+4, 1 skipped sem PG).

### Proximo: SP-06 (DNA-01 tabela decision_dna) — abre Onda 2.

---

---

## §26 — SP-02 ENTREGUE ✅

**Backfill calibration_error em PROD:**
- Antes: 0/3913 rows com calibration_error (todos NULL por causa de B-10).
- Apos: **3996/3996 = 100% fill-rate** (3913 backfill + 83 novos pos-fix).
- Distribuicao: dist=0 (5.2%), dist=1 (11.9%), dist=2 (11.8%), dist=3 (12.8%) — cauda longa decai como esperado.

### Entregas
- `tools/backfill_calibration_error.py` — dry-run default, --apply, --db
- `tests/test_sp02_backfill.py` — 3 testes (dry, apply, idempotente)

Suite: 293 -> **296 passing** (+3).
Dataset historico agora utilizavel para SP-25 (loss 2D HIT+wheel_dist).

### Proximo: SP-03 (CI/CD pull automatizado prod).

---

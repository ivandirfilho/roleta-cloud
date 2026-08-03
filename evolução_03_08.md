# Evolução 03/08 — Fundação da arquitetura de dados: auditoria, higienização e prontidão p/ estratégia

**Data:** 2026-08-03 · **Fonte:** produção `xmaiajpvm` (187.45.181.75), auditoria via SSH/Docker
**Escopo:** (1) auditoria de população e formato dos bancos; (2) auditoria pgvector camada básica;
(3) imersão nas jogadas de hoje; (4) **plano de higienização servidor × git** (ADENDO 03/08 do
`Manutenabilidade_iso.md`) para a fundação estar 100% antes da fase de estratégia.
**Requisito reitor:** a infraestrutura deve suportar **análises isoladas por sentido de giro**
(horário = `cw`, anti-horário = `ccw`) em todas as camadas — ver §4.0.
**Referências:** `fluxo_mental_24.md` (blueprint), `evolução_24_junho.md` (metodologia),
`Manutenabilidade_iso.md` (ADENDOs 12/06 §D e **03/08**).

---

## 1. Proposta

Usar a infraestrutura de dados que **já existe e está viva** (SQLite autoritativo → outbox → CDC → Postgres
com pgvector/Timescale/AGE) como base de **otimização de predição**, fechando os elos que hoje estão
provisionados mas **vazios**. O princípio: nenhuma peça nova — primeiro popular 100% do que foi desenhado,
depois medir lift real por feature, e só então evoluir a estratégia com evidência.

````
Extensão (spins + foto) ──WS──> Engine (SDA V4 + force17 + block_gale)
                                   │
                                   ├─> SQLite decisions.db  [autoritativo]  ✅ vivo
                                   │     ├─ decisions (46 col)              ✅ ~100% populado
                                   │     ├─ decision_dna (41.290)           ⚠️ realized_lift_pp = NULL (100%)
                                   │     ├─ gale_windows / window_plays     ✅ vivos
                                   │     └─ sessions (342)                  ✅ vivo
                                   │
                                   └─> shared.outbox (56.466 processed, 0 pending, 0 error) ✅
                                         └─> cdc_worker (lag < 1 s)         ✅
                                               ├─ cw/ccw.spins_vectors      ✅ 3.584/3.364 · ⚠️ ae_latent = NULL (100%)
                                               ├─ cw/ccw.spin_features      ✅ 2.991/2.763 (25 col, frescas)
                                               ├─ shared.decision_dna       ✅ 41.266 (espelho)
                                               └─ AGE cw_graph/ccw_graph    ❌ 0 vértices, 0 arestas
```

---

## 2. Auditoria de população (03/08)

### 2.1 SQLite `decisions` — fill-rate das 46 colunas (216 rows hoje)

| Grupo | Colunas | Fill | Veredito |
|---|---|---|---|
| Núcleo do giro | id, timestamp, session_id, spin_number, spin_direction, spin_force, spin_seq | 100% | ✅ |
| Estratégia (TR/SDA) | tr_*, sda_should_bet/score/center/numbers/centers/offset, final_action, action_reason | 100% | ✅ |
| Staking | gale_level, gale_window_hits/count, gale_bet_value | 100% | ✅ |
| Leitor de resultado | result_actual, result_hit, result_region, pnl_units, calibration_error | 92.1% | ✅ nulos só nas bordas (última decisão pendente + 1ª de cada sessão) |
| Visão/OCR | dealer 100% · dealer_table 99.5% · wheel_model 99.5% · vision_confidence 100% · vision_source 60.2% | — | ⚠️ `vision_source` caiu na sessão da madrugada (dealer `unknown`, 02:03–12:19) |
| Direção | direction_source/confidence/next, phase_uncertain | 100% | ✅ |
| Fonte externa | round_id | **0%** | ❌ site não fornece — limitação conhecida da fonte |
| Regiões V4 | sda_regions, sda_offset_type | 94% | ✅ |

**Conclusão:** o write-side autoritativo está **totalmente populado** dentro do desenho. Leitor de resultado
funcionando: cada `result_actual` confere com o `spin_number` do giro seguinte; hit/miss, região e PnL calculados.

### 2.2 Postgres (réplica analítica) — o que está vivo vs. vazio

| Peça | Estado | Observação |
|---|---|---|
| `shared.outbox` | ✅ 56.466 processed / **0 pending / 0 error** | zero backlog, CDC em tempo real |
| `cw/ccw.spins_vectors.raw_features` vector(6) | ✅ populado, index ivfflat cosine + ts | busca por similaridade pronta |
| `cw/ccw.spins_vectors.ae_latent` vector(4) | ❌ **100% NULL** | autoencoder (`scripts/train_autoencoder.py`) nunca rodou/backfillou |
| `cw/ccw.spin_features` (25 col: recent_acc_10/50, streaks, last_20_hits, visão, direção) | ✅ frescas (último ts = segundos) | feature store pronta p/ treino |
| `shared.decision_dna` | ✅ 41.266 rows | espelho do SQLite |
| AGE `cw_graph`/`ccw_graph` | ❌ **vazios** | camada de grafo provisionada e nunca populada |
| Timescale | ✅ ativo | hypertables ok |

### 2.3 Gaps estruturais que travam a otimização de predição

1. **F1 — ACHADO-RAIZ (3ª rodada): `dna_realize_lifts()` é código órfão.**
   A função que popularia `realized_lift_pp` **existe, está implementada e testada**
   (`database/dna_logger.py:203`, SP-08 DNA-03; `tests/test_sp08_dna_realize_lifts.py`) — mas
   **nenhum código de produção a chama**. Resultado: 41.370/41.370 rows com lift NULL desde 26/05.
   Não é falta de implementação; é **lacuna de integração** (falta o job/hook que a invoque).
2. **`ae_latent` nunca preenchido** → a busca vetorial usa só as 6 features cruas; o espaço latente
   comprimido (v4) que reduziria ruído p/ regime-matching não existe na prática.
3. **Grafo AGE vazio** → decisão já tomada no ADENDO 12/06 §D.3 (remover e voltar a
   `pgvector/pgvector:pg15` oficial) **pendente de execução** há 50+ dias; imagem 1 GB.
4. `round_id` 0% — impossibilita joins exatos com a casa; mitigação atual é `spin_seq` + dedup. OK.

**Formato:** o desenho (SQLite normalizado + outbox transacional + réplica analítica com vetores/série
temporal) **está correto para a proposta** — separação write/read, sem acoplamento do caminho da aposta.
O problema não é formato, é **população parcial dos elos analíticos** (itens 1–3).

### 2.4 Auditoria pgvector — camada básica (addendum 03/08, 2ª rodada)

**População: correta no nível linha.** Verificado em produção:

| Checagem | Resultado |
|---|---|
| Paridade hoje (SQLite decisions ↔ PG vetores) | **230 = 230** (1:1 exato) ✅ |
| Duplicatas por `decision_id` (vectors + features, cw/ccw) | **0** ✅ |
| `decision_id` NULL / órfãos | **0** ✅ |
| Vetores zerados/degenerados | **0** ✅ |
| DNA espelhado (hit preenchido) | 38.229 = 38.229 nos dois lados ✅ |
| Paridade histórica desde 24/05 | 7.087 vs 6.961 → **126 faltantes (1,8%)**, era do bug HOOK-1; backfill opcional |

**Exactly-once:** o worker processa evento + `mark_processed` na **mesma transação** com
`SKIP LOCKED` + SAVEPOINT por evento — sem janela de duplicação no caminho normal. ✅

**Porém, 5 achados de arquitetura na camada mais básica (a proposta NÃO está 100%):**

| # | Achado | Evidência | Sugestão (aditiva, default-OFF onde couber) |
|---|---|---|---|
| A1 | **Idempotência ausente** em `spins_vectors`/`spin_features` — INSERT puro; `spin_uuid UNIQUE` usa `gen_random_uuid()` (inútil p/ dedup). Replay manual do outbox duplicaria silenciosamente (o handler de DNA tem guard; estes não) | `cdc_worker.py:139-143,204-225` | Migração aditiva: `UNIQUE(decision_id)` + `ON CONFLICT DO NOTHING` |
| A2 | **Cosine sobre escalas mistas**: f0 força ≈16 (máx 36) e f5 ≈14 dominam a métrica; taxas c4/m6/l12 (~0,39) quase não pesam na similaridade | média das dims em prod: `[16.2, 0.39, 0.39, 0.39, 3.6, 14.1]` | Normalizar (z-score) em coluna própria ou — melhor — concluir o `ae_latent` (P2), que é exatamente o embedding normalizado do desenho |
| A3 | **Índice ivfflat mal dimensionado e nunca usado**: `lists=100` p/ ~3,5k rows (~35 vetores/lista) e `idx_scan = 0` nos dois índices — o único consumidor (`/api/regime_similarity`) nunca foi chamado | `pg_stat_user_indexes` | Ao ativar o consumo: recriar como **HNSW** (pgvector 0.8.2 suporta; sem treino, melhor p/ tabela que cresce) ou `lists≈sqrt(n)` |
| A4 | **Estatísticas do planner congeladas**: `n_live_tup=162` vs 3,5k reais; `last_autoanalyze` vazio — thresholds de autovacuum não disparam em tabela pequena/append-only | `pg_stat_user_tables` | `ANALYZE` pós-batch no worker (a cada N batches) ou cron diário |
| A5 | **Drift doc↔realidade**: TimescaleDB **não está instalado** (extensões ativas: `vector 0.8.2`, `age 1.5.0`); blueprint cita hypertables. `last_20_hits` em `spin_features` mistura sessões/dealers na window query (contaminação de lag-features entre mesas) | `pg_extension`; `cdc_worker.py:169-176` | Corrigir blueprint (ou instalar Timescale de fato); adicionar `session_id` como coluna filtrável na window query |

**Veredito da 2ª rodada:** pipeline de população **100% funcional** (fluxo, atomicidade, paridade);
proposta analítica **~70% entregue** — os vetores chegam corretos, mas a *busca* por similaridade
(razão de ser do pgvector) hoje seria enviesada (A2), lenta/imprecisa se ativada (A3) e ninguém a
consome (idx_scan=0). A1/A4 são higiene barata; A2+P2 são o desbloqueio real da predição.

### 2.5 Higiene de servidor confirmada na 3ª rodada (03/08 ~15:00 UTC)

| Item | Estado |
|---|---|
| Backup SQLite diário | ✅ vivo — `decisions_20260803_031501.db.gz` (2,7 MB) |
| wal-g 30 min | ✅ cron ativo (`/etc/cron.d/walg-backup`) + binário no container |
| Restore drill | ❌ **nunca ensaiado** (gap 12/06 §D.5; `walg-restore-drill.sh` pronto) |
| `spin_autoencoder.joblib` | ⚠️ segue **untracked no host** (hazard `git clean`; gap 12/06 §D.4) |
| Disco | ✅ 14% usado, mas **5,5 GB de imagens reclamáveis + 1,8 GB build cache** |
| Deploy timer | ✅ `roleta-deploy.timer` a cada 2 min, main `ac145c4` sincronizado |
| **ANALYZE (ação executada hoje)** | ✅ 6 tabelas analíticas; `n_live_tup` 162→**3.591** (cw), `last_analyze=15:00 UTC` — sana A4 operacionalmente |

> A única mutação da auditoria foi o `ANALYZE` (reversível, não toca schema/dados/caminho da aposta).
> Registro formal: **ADENDO 03/08 §C** do `Manutenabilidade_iso.md`.

---

## 3. Imersão — jogadas de hoje (03/08, UTC)

### 3.1 Placar geral

| Métrica | Valor |
|---|---|
| Decisões | 218 (201 resolvidas) |
| Hits | 77 → **38,3%** |
| PnL | **+115,19 u** · EV +0,57 u/giro |
| Ritmo | ~40–50 giros/h quando master conectado |

### 3.2 Por sessão

| Sessão | Janela | Dealer | Res. | Hit% | PnL |
|---|---|---|---|---|---|
| `faa72346` | 00:00–02:02 | THAYLA | 38 | **47,4%** | **+181,50** |
| `8e625d3e` | 02:03–12:19 | ELINE/unknown | 70 | 34,3% | −46,55 |
| `36c3d7e2` | 12:20–13:27 | STEPHEN | 80 | 37,5% | −48,76 |
| `673ae366` | 13:27–… | STEPHEN | 14 | 35,7% | +29,00 |

### 3.3 Leitura estratégica (config ativa: `SDA_REGIONS_V4=1`, `SDA_BET_PAIR=force17`, `SDA_STAKING_MODE=block_gale` teto 1)

- **Breakeven do force17 é 47,2%** (17 números; prêmio líquido 36/17−1 ≈ 1,118/u). O dia fechou em
  38,3% — **abaixo do breakeven por unidade apostada**: as linhas com stake 1u tiveram média
  −0,12 a −0,16 u/giro. O PnL positivo veio da **coincidência entre stakes altos (12–17u) e a sessão
  quente** (`faa72346`, 47,4%), i.e., variância favorável, não edge sistemático.
- **Regiões:** C2 dominou (47 dos 77 hits = 61%, +342,88 u), C3 23 hits (+230,35), C1 raro (7 hits).
  124 miss = −466 u. A concentração em C2 é o sinal mais forte do dia p/ investigação.
- **Direção:** horário 37/99 (+113,86 u) vs anti-horário 40/102 (+1,33 u) — hit% similar, PnL
  divergente por timing de stake.
- **Números quentes:** 25 (12×), 7 e 2 (10×), 36/13/12/8 (9×).
- **Streak (últimos 60 resolvidos):** sem clusters longos de hit; misses em rajadas de até 6 —
  compatível com p≈0,38 i.i.d.; nada sugere regime detectável a olho, reforçando a necessidade do
  ferramental do §2.3 (lift por feature + similaridade de regime) em vez de leitura manual.
- **INV-3 preservado:** 100% das decisões com `final_action=APOSTAR`; modulação só via stake. ✓

### 3.4 Diagnóstico

O motor preditivo (SDA V4 + calibração + visão) está **operacional e íntegro**, mas roda **sem o loop de
feedback quantitativo**: DNA sem lift realizado (F1 — função pronta, sem caller), vetores sem latente,
hit-rate global 9 p.p. abaixo do breakeven da aposta atual. Hoje o lucro veio de gestão de stake +
sorte de sessão. O dado bruto está pronto; o plano do §4 liga a analítica.

---

## 4. Plano de higienização da fundação (ADENDO 03/08 §D — divisão servidor × git)

> Consolida e **substitui** a lista P1–P6 da 1ª rodada. Objetivo: fundação 100% funcional
> **antes** da fase de estratégia. Rastreabilidade ISO: `Manutenabilidade_iso.md`, ADENDO 03/08.

### 4.0 Princípio reitor — isolamento por sentido (horário × anti-horário)

**Requisito de arquitetura:** toda a camada analítica deve permitir análise **isolada por sentido**
(CW = horário, CCW = anti-horário). São processos físicos distintos (rotor + lançamento do dealer)
e não podem ser misturados em baseline, treino ou similaridade.

Estado real verificado hoje:

| Camada | Isolamento por sentido? | Evidência |
|---|:--:|---|
| Storage PG (`cw.*` / `ccw.*` schemas: spins_vectors, spin_features) | ✅ nativo | DDL por schema |
| Busca de similaridade (`regime_similarity.py`) | ✅ exige `direction ∈ {cw, ccw}` | `_ALLOWED = {"cw","ccw"}` |
| SQLite `decisions.spin_direction` + `decision_dna.direction` | ✅ coluna presente | schema |
| **Baseline do `dna_realize_lifts()`** | ❌ **GLOBAL — mistura os 2 sentidos** | `dna_logger.py:224` (`AVG(hit)` sem filtro de direção; buckets sem `direction` no GROUP BY) |
| **Treino do autoencoder** | ❌ **1 modelo único juntando cw+ccw** | `train_autoencoder.py:36` (pool das rows dos 2 schemas → 1 PCA) |

→ Os PRs H1 e H5 **corrigem exatamente essas duas violações** (specs abaixo).

### 4.1 No servidor Debian (operacional, sem PR — runbooks já existem)

| # | Ação | Instrumento | Gap | Status |
|---|---|---|---|---|
| S1 | ANALYZE nas 6 tabelas analíticas | psql one-shot | A4 | ✅ **FEITO 03/08 15:00 UTC** |
| S2 | Backfill dos 126 rows faltantes (era HOOK-1) — one-shot idempotente, padrão `scripts/backfill_dna_pg.py` | `docker exec roleta-cloud` | paridade histórica | pendente |
| S3 | **Restore drill** wal-g ponta-a-ponta | `scripts/walg-restore-drill.sh` | 12/06 §D.5 | pendente |
| S4 | Mover `spin_autoencoder.joblib` p/ volume Docker (parte git em H7) | mv + compose volume | 12/06 §D.4 | pendente |
| S5 | `docker system prune`: imagens órfãs (5,5 GB) + build cache (1,8 GB) | docker | disco | pendente |

### 4.2 No git — o que cada Pull Request solicita e qual o ganho

> Formato: **Solicitação** = escopo exato da mudança que o PR pede (o que o revisor deve verificar);
> **Ganho** = capacidade nova ou risco eliminado. 1 sprint = 1 worktree = 1 PR; `main` é produção.

#### H1 · `SPR-DATA1` — Fechar o loop de feedback do DNA, POR SENTIDO 🔴 P1 (gap F1)

**Solicitação do PR:**
1. Alterar `dna_realize_lifts()` (`database/dna_logger.py:203`) para calcular **baseline e buckets
   POR DIREÇÃO** (`GROUP BY direction, feature_name, bucket`; baseline CW = hit-rate só de CW,
   idem CCW) — hoje o cálculo, se ativado, misturaria os 2 sentidos.
2. Criar caller periódico no engine (a cada N decisões resolvidas ou M minutos), atrás da flag
   **`SDA_DNA_REALIZE` default-OFF** na `docker-compose.yml`, leitura por-chamada.
3. Propagar para o PG: publicar evento `dna_realized` (handler já existe no worker:
   `cdc_worker.py:266`) com o lift por sentido.
4. Backfill one-shot das ~41k rows históricas (idempotente: só `realized_lift_pp IS NULL`).
5. Testes: por-direção (CW ≠ CCW com fixtures assimétricas), flag OFF = zero efeito, round-trip.

**Ganho:** o ranking de features (E1) passa a existir **separado por sentido** — descobrir, com
dado real, se p.ex. `sda_score` alto discrimina hit em CW mas não em CCW. Sem isso, toda análise
de estratégia é intuição. É o pré-requisito da fase seguinte.

#### H2 · `SPR-DATA2` — Idempotência nos INSERTs analíticos 🟠 P2 (gap A1)

**Solicitação do PR:** migração Alembic **ADITIVA** criando `UNIQUE(decision_id)` em
`cw/ccw.spins_vectors` e `cw/ccw.spin_features` + trocar os INSERTs do `cdc_worker.py` para
`ON CONFLICT (decision_id) DO NOTHING`. Sem downgrade destrutivo.

**Ganho:** replay do outbox (recuperação de incidente, backfill manual) deixa de poder duplicar
vetores silenciosamente — dedup passa a ser garantido pelo banco, não por disciplina do operador.

#### H3 · `SPR-DATA3` — Lag-features por sessão 🟠 P2 (gap A5b)

**Solicitação do PR:** adicionar coluna `session_id` (ADITIVA) em `cw/ccw.spin_features`; a window
query do worker (`cdc_worker.py:169`) passa a filtrar `WHERE session_id = %s`, para `recent_acc_10/50`,
streaks e `last_20_hits` não contaminarem entre mesas/dealers. Backfill best-effort via `meta->>'session_id'`.

**Ganho:** as lag-features refletem a mesa real em jogo — hoje um streak de outra sessão (outro
dealer, outra roleta física) vaza para o cálculo, poluindo qualquer modelo treinado sobre elas.

#### H4 · `SPR-DATA4` — ANALYZE periódico no worker 🟡 P3 (gap A4)

**Solicitação do PR:** `ANALYZE` das tabelas analíticas a cada N batches no `cdc_worker`
(flag `CDC_ANALYZE_EVERY_N` default-OFF). Persiste o S1 (feito manualmente hoje).

**Ganho:** planner do PG nunca mais opera com estatísticas congeladas (hoje: 162 vs 3.591 reais
antes do S1); planos de query corretos conforme as tabelas crescem.

#### H5 · `SPR-DATA5` — Autoencoder POR SENTIDO + backfill `ae_latent` 🟠 P2 (gap A2)

**Solicitação do PR:**
1. Alterar `scripts/train_autoencoder.py` para treinar **2 modelos independentes** (1 por schema:
   `spin_autoencoder_cw.joblib`, `spin_autoencoder_ccw.joblib`) — hoje pool das rows dos 2 sentidos
   num único PCA, o que mistura distribuições físicas distintas.
2. Job/script de backfill de `ae_latent` em `cw/ccw.spins_vectors` usando o modelo do sentido correspondente.
3. Normalização (z-score) embutida no pipeline do modelo — resolve o viés de escala do cosine (A2)
   na raiz: força (~16) deixa de esmagar as taxas (~0,39).

**Ganho:** regime-matching honesto e **isolado por sentido** — buscar "situações parecidas" compara
CW com CW e CCW com CCW, em espaço normalizado onde as 6 dimensões pesam de forma comparável.
Habilita E3 (stake condicionado a regime, via `min()`, INV-3 intacto).

#### H6 · `SPR-DATA6` — Índices HNSW na ativação do consumo 🟡 P3 (gap A3)

**Solicitação do PR:** recriar `idx_{cw,ccw}_spins_vectors_raw_cosine` como **HNSW** (pgvector
0.8.2) — e criar equivalente para `ae_latent` — no mesmo PR que ativar o consumidor de
similaridade em produção (`/api/regime_similarity` ou gate de stake).

**Ganho:** busca vetorial com recall/latência corretos numa tabela que cresce (~460/dia);
elimina o ivfflat mal dimensionado (`lists=100` p/ 3,5k rows) que nunca foi usado (`idx_scan=0`).

#### H7 · `SPR-DATA7` — Docs, joblib e decisão AGE 🟡 P3 (gap A5a + 12/06 §D.3/D.4)

**Solicitação do PR:** corrigir `fluxo_mental_24.md` (cita TimescaleDB inexistente; extensões
reais: `vector 0.8.2` + `age 1.5.0`); adicionar `models/*.joblib` ao `.gitignore` (par do S4);
**executar a decisão AGE de 12/06 §D.3**: trocar imagem `roleta/postgres-stack:pg15-age15` →
`pgvector/pgvector:pg15` oficial na `docker-compose.pg.yml` (remove grafo vazio há 70 dias).

**Ganho:** blueprint volta a ser confiável como fonte de verdade; −1 GB de imagem custom sem uso;
elimina o hazard de `git clean` apagar o modelo treinado.

### Dependências e ordem

```
S2, S3, S5 ──────────────► imediato, sem janela
H1 (por sentido) ────────► PRÉ-REQUISITO da fase de estratégia
H2, H3, H4 ──────────────► higiene independente, barata
H5 (por sentido) → H6 ───► sequência (modelo antes do índice)
H7 ──────────────────────► independente (docs/infra)
```

### 4.3 Análises de estratégia destravadas após H1/H5 (fase seguinte)

| # | Estudo | Insumo | Isolado por sentido? |
|---|---|---|:--:|
| E1 | Ranking de features por lift realizado (qual sinal discrimina hit/miss) | H1 | ✅ CW ≠ CCW |
| E2 | C2-dominância: hit% por região × dealer × direção nas últimas N sessões (61% dos hits hoje em C2) | dados atuais | ✅ já possível |
| E3 | Regime-matching por similaridade no espaço latente (stake condicionado a regime, via `min()` — INV-3 intacto) | H5+H6 | ✅ por design |
| E4 | Painel Grafana "hit-rate vs breakeven por modo de aposta" (47,2% no force17) | dados atuais | ⚠️ adicionar split CW/CCW |
| E5 | Causa da queda de `vision_source` (60% hoje; sessão madrugada com dealer `unknown`) | bugfix leve | n/a |

**Invioláveis em qualquer item:** INV-3 (APOSTAR sempre; veto só via `min()` no stake), flags
default-OFF na compose, migrações Alembic ADITIVAS, round-trip `save/load/reset_session`,
entrega por PR — `main` é produção (deploy automático em ~2 min).

---

*Rodadas 1–3 em 2026-08-03 sobre a produção. Única mutação no servidor: ANALYZE (§2.5/S1).*
*Registro ISO formal: `Manutenabilidade_iso.md` → ADENDO 03/08/2026.*
````
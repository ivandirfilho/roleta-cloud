# Evolução 03/08 — Fundação da arquitetura de dados: auditoria, higienização e prontidão p/ estratégia

**Data:** 2026-08-03 · **Fonte:** produção `xmaiajpvm` (187.45.181.75), auditoria via SSH/Docker
**Escopo:** (1) auditoria de população e formato dos bancos; (2) auditoria pgvector camada básica;
(3) imersão nas jogadas de hoje; (4) **plano de higienização servidor × git** (ADENDO 03/08 do
`Manutenabilidade_iso.md`); (5) **visão de banco de dados** — tecnologias, onde vive cada
alteração e por quê, auditoria SaaS e de conflitos do plano (§5).
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
| S6 | **Backup do SQLite → B2** (hoje é local-only; ver §5.3-R1) | estender `roleta-backup-decisions.sh` c/ upload B2 | assimetria de proteção | pendente |
| S7 | **Janela de restore PG**: base a cada 30 min + `retain FULL 7` = ~3,5 h de histórico (ver §5.3-R2) | ajustar cron `walg-backup-daily.sh` p/ diário OU `retain 30` | retenção curta | decidir |

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
⚠️ **Guarda obrigatória (§5.4-C1):** no MESMO PR, remover `age` de
`shared_preload_libraries=age,pg_stat_statements` no `command:` do compose — a imagem oficial
não tem a lib e o postgres **não sobe** se o preload referenciar módulo inexistente. Pré-requisito
operacional: S3 (restore drill) ANTES da troca de imagem.

**Ganho:** blueprint volta a ser confiável como fonte de verdade; −1 GB de imagem custom sem uso;
elimina o hazard de `git clean` apagar o modelo treinado.

### Dependências e ordem

```
S2, S5, S6 ──────────────► imediato, sem janela
S3 (restore drill) ──────► ANTES do H7 (valida backup antes de trocar imagem PG)
H1 (por sentido) ────────► PRÉ-REQUISITO da fase de estratégia
H2, H3, H4 ──────────────► higiene independente, barata
H5 (por sentido) → H6 ───► sequência (modelo antes do índice)
S3 → H7 ─────────────────► sequência (drill antes da troca de imagem; ver §5.4-C1)
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

## 5. Visão de banco de dados — tecnologias, onde vive cada alteração e por quê (4ª rodada, 03/08)

> Auditoria feita com grafo de conhecimento (graphify, 7.352 nós) + leitura do filesystem
> (composes, requirements, scripts, cron) + verificação ao vivo no servidor. Objetivo: mapa
> definitivo de ONDE cada dado vive, POR QUE naquele banco, quais tecnologias são externas
> (SaaS) e se o plano §4 tem conflitos internos.

### 5.1 Mapa de tecnologias — o que roda onde e o que custa

| Tecnologia | Onde roda | Licença/custo | Verificado 03/08 |
|---|---|---|---|
| Python 3.12 + websockets/pydantic/structlog | container `roleta-cloud` | OSS, R$ 0 | ✅ healthy |
| SQLite (built-in) | dentro do `roleta-cloud`, volume `roleta-data` | OSS, R$ 0 | ✅ 14 MB, vivo |
| PostgreSQL 15 + pgvector 0.8.2 | container `roleta-pg` — **imagem upstream `pgvector/pgvector:pg15`** (pós-H7; AGE/Timescale removidos hoje) | OSS, R$ 0 | ✅ 51 MB |
| Alembic + SQLAlchemy + psycopg2 | só p/ migrações do PG | OSS, R$ 0 | ✅ head=0013 |
| RapidOCR-ONNX (vision da foto) | dentro do `roleta-cloud`, CPU | OSS, R$ 0 | ✅ |
| Prometheus v2.51 + Grafana OSS 10.4 + Alertmanager | containers locais, retenção 30d | OSS, R$ 0 | ✅ local-only |
| scikit-learn (PCA per-direction) | treino em container efêmero `python:3.12-slim`; inferência via joblib | OSS, R$ 0 | ✅ 2 modelos, evr ≈0,96 |
| wal-g 3.x | binário no host, exec no container PG | OSS, R$ 0 | ✅ push+fetch validados |
| rclone 1.60 | host (cron do backup SQLite) | OSS, R$ 0 | ✅ offsite OK |
| **Backblaze B2** (bucket `roletacloubucket`) | SaaS externo — **único custo pago do stack** (centavos/GB·mês) | pago | ✅ basebackup + WAL + SQLite offsite |
| Docker + compose + systemd (`roleta-deploy.timer`) | host Debian `xmaiajpvm` | OSS, R$ 0 | ✅ deploy ~2 min |

**Auditoria SaaS:** nenhuma dependência de SaaS pago além do B2. Não há Workana/serviços de
terceiros no runtime — apenas o cassino de origem (fonte dos dados via extensão) e o B2
(armazenamento offsite). Tudo o mais é OSS rodando no próprio host.

### 5.2 Onde vive cada alteração de hoje — e por quê naquele banco

| Alteração | Banco/camada | Por quê ali |
|---|---|---|
| `realized_lift_pp` per-direction (H1) | SQLite (autoritativo) → espelho PG | a decisão nasce no engine; o PG só consome p/ análise |
| Evento `dna_lift_bucket` | outbox (SQLite→PG) | contrato CDC já existente; 1 evento/bucket evita 41k updates |
| UNIQUE `decision_id` (H2) | PG (0011) | dedup é preocupação do espelho analítico, não do engine |
| `session_id` (H3) | PG `spin_features` (0012) | recorte analítico por sessão de mesa; engine já tinha o dado |
| ANALYZE pós-batch (H4) | worker CDC | é o worker quem sabe quando o batch terminou |
| AEs per-direction (H5) | joblib no host + `ae_latent` no PG | treino offline; inferência lê pgvector |
| HNSW (H6) | PG (0013) | índice de similaridade é infra do plano vetorial |
| Higiene de imagem PG (H7) | compose + host | infra, não dado |

---
| wal-g (binário) | host + montado no `roleta-pg` | OSS, R$ 0 | ✅ 0 falhas |
| **Backblaze B2** (bucket `roletacloubucket`, S3-compatível) | **☁️ SaaS EXTERNO — único** | **freemium: 10 GB grátis, depois ~US$ 6/TB·mês** | ✅ 410 WALs archivados, 0 falhas, base 30/30min |
| VPS Debian HostDime (`xmaiajpvm`) | hosting | infraestrutura própria (não SaaS de software) | ✅ |

**Sobre "workana": não existe** — `grep -ri workana` retornou **zero** ocorrências no repo E no
servidor (código, composes, systemd, cron, bashrc). Nenhuma dependência de plataforma Workana no
software. Provável origem da confusão: o grafo graphify servido via MCP é um **super-grafo
multi-repo** que inclui o projeto "Genesis azure" (outro repo, com `AWSAdapter`/`AwsConnector` em
Rust/Python) — nós de OUTRO projeto aparecendo em consultas deste. As referências "AWS" do
roleta-cloud são apenas o **protocolo S3** que o wal-g usa para falar com o Backblaze
(`AWS_ENDPOINT=https://s3.us-east-005.backblazeb2.com`) — não há conta AWS.

**Veredito SaaS:** a stack é 100% OSS auto-hospedada com UM único serviço externo (B2), que está
**funcional e sem falhas**. Alertmanager entrega só em webhook local (Telegram/Slack: previsto,
não configurado — sem custo). Não há SendGrid/Twilio/Datadog/Sentry/etc.

### 5.2 Onde vive cada alteração de dado — e POR QUE naquele banco

```
                         ┌─ POR QUE SQLite: transacional, zero-config, mesma máquina
                         │  do engine → decisão gravada ANTES do resultado do giro
                         │  (latência sub-ms); é a FONTE DA VERDADE
   Extensão ──WS──► Engine ──► SQLite decisions.db  [transacional/autoritativo]
                         │        ├─ decisions, decision_dna, gale_windows,
                         │        │  window_plays, sessions
                         │        └─ shared.outbox (padrão outbox: evento gravado
                         │           NA MESMA TX da decisão → nunca diverge)
                         │
                         └─ POR QUE PG: pgvector (busca de similaridade), SQL
                            concorrente p/ análise SEM travar o engine, schemas
                            cw/ccw isolando sentidos FISICAMENTE
              cdc-worker ──► Postgres roleta  [analítico/réplica derivada]
                               ├─ cw.spins_vectors / ccw.spins_vectors  (vetores 6d)
                               ├─ cw.spin_features / ccw.spin_features  (25 col)
                               └─ shared.decision_dna                    (espelho)
```

| Tipo de alteração | Vive em | Por que ali (e não no outro) |
|---|---|---|
| Decisão/aposta/resultado do giro | SQLite | caminho crítico do engine; transação local sub-ms; sobrevive sem rede; PG cair NÃO pode parar aposta |
| Evento de replicação | `shared.outbox` (SQLite) | mesma TX da decisão = exactly-once por construção; worker consome com SKIP LOCKED |
| Vetores/features analíticas | PG `cw.*`/`ccw.*` | pgvector só existe no PG; schema por sentido = isolamento físico exigido no §4.0; query pesada não compete com o engine |
| Lift realizado do DNA (H1) | **calcula no SQLite, espelha no PG** | fonte dos hits é o SQLite; PG recebe via evento `dna_realized` p/ análise |
| Modelo autoencoder (H5) | arquivo `.joblib` em volume (S4) | artefato binário de ML não é linha de banco; versionar fora do git (pesado, regenerável) |
| Schema PG (H2/H3) | migração Alembic ADITIVA | única via sancionada; rollback de deploy não faz downgrade |
| Config/flags | `docker-compose.yml` (env) | comportamento novo = flag default-OFF, leitura por-chamada; auditável no git |
| Métricas/alertas | Prometheus (30d) | efêmero por natureza; dado de negócio NUNCA vive só em métrica |
| Backup PG | **B2 (externo)** | único dado que SAI da máquina — sobrevive à perda do VPS |

Regra de ouro que o desenho respeita: **escreve-se onde a latência manda (SQLite); analisa-se
onde o ferramental manda (PG); nada nasce direto no PG** — tudo chega lá pelo outbox. Toda
mudança de comportamento entra por flag na compose; toda mudança de schema PG entra por Alembic.

### 5.3 Riscos encontrados na auditoria de backup (novos)

| # | Risco | Evidência | Correção |
|---|---|---|---|
| R1 | **Assimetria de proteção**: o SQLite (fonte da verdade!) tem backup só LOCAL (`/root/backups/sqlite/`, cron 03:15) — a RÉPLICA (PG) está no B2, o ORIGINAL não. Perda do VPS = perde o autoritativo, salva a cópia | `roleta-backup-decisions.sh` não tem upload; B2 só recebe WAL/base do PG | **S6**: acrescentar upload B2 ao script (mesmo bucket, prefixo `sqlite/`) |
| R2 | **Retenção PG curtíssima**: cron roda `walg-backup-daily.sh` a cada **30 min** (não diário como o nome diz) e `delete retain FULL 7` mantém só 7 bases = **~3,5 h de janela de restore**. Corrupção detectada de manhã pode não ter mais backup bom | `/etc/cron.d/walg-backup` (`*/30`); script linha 33 | **S7**: OU volta cron p/ diário (7 dias de janela) OU `retain FULL 336` (7 dias em 30/30min; ~50 GB no B2 → sai do free tier) — decisão do operador |
| R3 | Custo B2 pode crescer silenciosamente: base 150 MB × 48/dia × 7 = controlado hoje (WAL+bases ~poucos GB), mas R2 mal resolvido muda a conta | `backup-list --detail` | monitorar tamanho do bucket ao decidir S7 |

### 5.4 Auditoria de conflitos — o plano §4 contra a visão do software como um todo

Verificação item a item de H1–H7 e S1–S7 entre si e contra os invioláveis:

| # | Conflito potencial | Análise | Veredito |
|---|---|---|---|
| C1 | **H7 (troca de imagem PG) × compose atual** | `docker-compose.pg.yml` linha 23 tem `shared_preload_libraries=age,...`; imagem oficial `pgvector/pgvector:pg15` NÃO tem AGE → postgres **não sobe** | ⚠️ **REAL — resolvido**: guarda adicionada ao H7 (remover `age` do preload no MESMO PR) + S3 vira pré-requisito |
| C2 | H2 (UNIQUE) × S2 (backfill 126 rows) | backfill INSERT pode colidir com rows já replicadas | ✅ sem conflito SE S2 rodar com `ON CONFLICT DO NOTHING` (que o H2 introduz) — executar S2 DEPOIS de H2, ou usar guard manual |
| C3 | H1 (lift por sentido) × INV-3 | lift é só LEITURA p/ análise; não toca indicação nem stake | ✅ sem conflito |
| C4 | H5 (2 modelos joblib) × S4 (volume) | S4 move 1 arquivo; H5 cria 2 novos nomes (`_cw`/`_ccw`) | ✅ compatível — S4 deve montar o DIRETÓRIO `models/`, não o arquivo |
| C5 | H3 (session_id por janela) × H5 (features de treino) | features geradas ANTES do H3 têm janelas contaminadas entre sessões | ⚠️ **sequenciamento**: treinar H5 preferencialmente APÓS H3 + re-materialização, senão o modelo aprende ruído de sessão |
| C6 | H4 (ANALYZE no worker) × S7 (backup 30/30min) | ANALYZE gera WAL extra archivado no B2 | ✅ desprezível (tabelas pequenas) |
| C7 | Estratégia (SDA no SQLite) × plano de dados (PG) | TODO o plano §4 é na camada analítica; caminho da aposta não é tocado | ✅ por construção |

**Síntese:** o plano é internamente consistente com 2 ajustes já incorporados — **C1** (guarda do
preload no H7 + S3 antes) e **C5** (H3 antes do treino do H5). A ordem recomendada final fica:
`H2 → S2 → H3 → H1 → H4 → H5 → H6 → S3 → H7`, com S5/S6 a qualquer momento e S7 decidido pelo
operador junto com R2/R3.

### 5.5 A proposta está 100% funcional?

- **Escrita/replicação/backup PG**: ✅ 100% (verificado ao vivo: 0 pending, 0 falhas de archive).
- **SaaS**: ✅ 1 único (B2), funcional; nada órfão pago; "workana" inexistente.
- **Análise**: ~70% — segue bloqueada pelos gaps F1/A2/A3 até H1/H5/H6.
- **Backup do autoritativo**: ❌ gap novo R1 (SQLite local-only) — S6 criado.
- **Restauração**: ⚠️ janela de 3,5 h (R2) e drill nunca ensaiado (S3) — S7 criado.

---

*Rodadas 1–4 em 2026-08-03 sobre a produção. Única mutação no servidor: ANALYZE (§2.5/S1).*
*4ª rodada: visão de banco de dados (§5) — grafo graphify + filesystem + verificação B2/cron ao vivo.*
*Registro ISO formal: `Manutenabilidade_iso.md` → ADENDO 03/08/2026.*
````
## 6. Execução 03/08 — closeout (tudo em produção, nada em shadow)

> Registro final da execução dos sprints H1–H7 + S2/S3/S5/S6/S7. Todos os PRs mergeados em
> `main`, deploy automático aplicado, flags LIGADAS no host, auditoria ponto a ponto executada
> em produção. Documento-irmão: `arquitetura_dados_estrategia.md` (raiz) — mapa de onde vive
> cada fase da estratégia e receita semântica para novas estratégias.

### 6.1 PRs entregues (todos com CI 5/5 verde e mergeados)

| PR | Conteúdo | Status |
|---|---|---|
| **#38** | H1–H7 completos: migrações 0011/0012/0013, lift per-direction + evento `dna_lift_bucket`, session_id, ANALYZE pós-batch, AEs per-direction + backfill, HNSW, imagem PG upstream, `.gitignore` graphify-out (52 arquivos removidos do índice), doc `arquitetura_dados_estrategia.md`, +4 testes (suíte 733 passed) | ✅ merge `4cd47d5` |
| **#39** | Fix da auditoria: normaliza `direction` no payload `dna_lift_bucket` (SQLite `anti-horario` → PG `ccw`; sem isso o UPDATE casava 0 rows) | ✅ merge `1557451` |
| **#40** | S7: retain wal-g FULL 7→48 (24h de janela com backup 30min); S6: upload offsite do SQLite p/ B2 via rclone (flag `RCLONE_REMOTE`); S3-fix: drill em `pgvector/pgvector:pg15` (era `postgres:16` — falso-negativo garantido) | ✅ merge `4b72885` |
| **#41** | **Achado crítico da auditoria:** imagem upstream não traz `ca-certificates` → TODO upload wal-g ao B2 falhava com `x509 unknown authority` (basebackup E archive de WAL parados desde a troca de imagem). Fix: bind-mount RO `/etc/ssl/certs` do host | ✅ merge `2a41da7` |

### 6.2 Rollout no servidor (Debian `xmaiajpvm`)

1. Deploy timer aplicou `main` + `alembic upgrade head` (0013) automaticamente.
2. Flags ligadas via `.env` do host (compose continua default-OFF — inviolável):
   `SDA_DNA_REALIZE=1`, `SDA_DNA_REALIZE_EVERY=20`, `CDC_ANALYZE_EVERY_N=50`.
3. `roleta-pg` recriado com imagem upstream + mount de certs; `DROP EXTENSION age CASCADE`
   + `DROP SCHEMA ag_catalog` executados; pgvector 0.8.2 intacto.
4. Treino dos 2 AEs em container efêmero (`python:3.12-slim`, numpy<2 por causa da CPU QEMU):
   evr cw=0,9646 / ccw=0,9579; backfill `ae_latent` = 6.961/6.961 (100%).
5. Backfill dos lifts: 33.411/38.229 rows no SQLite (restante = buckets com n<30, correto);
   republicação pós-fix #39 espelhou os mesmos 33.411 no PG (paridade exata).
6. Backups: 4 `.db` legados movidos do volume p/ `/root/backups/sqlite/legacy/`; rclone
   instalado e configurado (creds do wal-g, `no_check_bucket` p/ key restrita); cron do
   backup SQLite agora exporta `RCLONE_REMOTE` → upload B2 validado (`OFFSITE OK`);
   basebackup wal-g pós-fix TLS OK; **restore drill completo**: basebackup restaurado do B2
   em container isolado → 41.370 dna / 33.411 lifts íntegros.

### 6.3 Auditoria ponto a ponto (produção, 03/08 ~17:30 UTC)

| Check | Resultado |
|---|---|
| alembic head | ✅ `0013_hnsw_vectors` |
| UNIQUE parciais decision_id (×4) | ✅ `uq_{cw,ccw}_{spin_features,spins_vectors}_decision` |
| HNSW (×4) + uso real no plano | ✅ `Index Scan using idx_cw_spins_vectors_raw_cosine` |
| Lifts per-direction no PG | ✅ 33.411 rows; média cw=−0,05pp / ccw=−0,02pp (segregados) |
| `ae_latent` | ✅ cw 3.591/3.591, ccw 3.370/3.370 (100%) |
| AGE removida / pgvector | ✅ 0 extensões age; vector 0.8.2 |
| WAL archiving | ✅ `archiving_ok=t` pós-fix #41 (estava quebrado ~1h) |
| Basebackup B2 + retain 48 | ✅ push 17:19Z; `keep FULL 48` ativo |
| SQLite offsite B2 | ✅ `decisions_20260803_165009.db.gz` no bucket |
| Restore drill | ✅ dados íntegros restaurados do B2 |
| Outbox pendente | ✅ 0 |
| Containers | ✅ 7/7 healthy (node/pg-exporter não têm healthcheck — `Up` normal) |
| Volume sem backups soltos | ✅ movidos p/ host |
| Suíte + CI | ✅ 733 passed local; CI verde nos 4 PRs |
| `session_id` fluindo ao vivo | ✅ validado na retomada (18:01 UTC): sessão `26172412` presente em cw **e** ccw em todos os giros novos |

### 6.4 Achados da auditoria (e correções aplicadas)

1. **Vocabulário de direção divergente** (bug real): SQLite guarda `horario/anti-horario`, PG
   guarda `cw/ccw`. O evento novo `dna_lift_bucket` saiu sem normalizar → 30 eventos
   processados, 0 rows atualizadas. Corrigido no publisher (#39) + republicação. *Lição:
   qualquer payload novo do outbox DEVE passar por `_normalize_direction`.*
2. **`ca-certificates` ausente na imagem upstream** (bug crítico silencioso): a troca H7
   derrubou TLS do wal-g — basebackup e WAL pararam de subir ao B2 por ~1h. Corrigido com
   bind-mount de certs (#41) e validado com push + drill. *Lição: troca de imagem base exige
   smoke dos jobs que rodam DENTRO do container (backup, archive), não só do serviço.*
3. **Drill com 3 bugs latentes** (nunca tinha rodado até o fim): imagem `postgres:16` vs
   basebackups PG15; `postgresql.auto.conf` com aspas duplas (syntax error no PG); falta de
   `recovery.signal` + espera fixa de 10s. Corrigidos (#40 + este PR). O drill agora é
   executável e validou o ciclo completo backup→restore.
4. **`hit_region` com lift uniforme +56,5pp** em todos os buckets: viés estrutural conhecido
   (feature só é logada quando há atribuição de hit) — não é bug; excluir de rankings de lift.

### 6.5 Estado final dos dados (03/08 ~17:30 UTC)

```
SQLite (autoritativo):  41.370 decision_dna · 38.229 com hit · 33.411 com lift (n≥30)
PG cw:   3.591 spins_vectors (100% ae_latent) · spin_features com session_id pronto
PG ccw:  3.370 spins_vectors (100% ae_latent)
PG shared.decision_dna: 41.370 rows · 33.411 lifts espelhados (paridade exata)
B2: basebackup 30min (FULL 48) + WAL contínuo + SQLite diário offsite
```

**Fundação de dados COMPLETA e 100% em produção.** Próximo passo (sessão de estratégia):
E1–E5 do §4.3 — começando pelo ranking de features por lift realizado per-direction, que o
H1 destravou hoje.

### 6.6 Validação AO VIVO pós-retomada (03/08 ~18:00–18:16 UTC)

A mesa voltou a girar às 18:01 UTC e o fluxo completo foi validado com giros reais:

| Check ao vivo | Resultado |
|---|---|
| Docker novo (`def33c5`, pós-#42) | ✅ imagem 17:17Z, container up 17:38Z, healthy |
| Giros novos ingeridos | ✅ 9 giros (5 cw + 4 ccw) em spin_features, ts 18:01–18:08 |
| **`session_id` ao vivo (pendência única)** | ✅ **RESOLVIDA** — `26172412` em 9/9 giros, cw e ccw |
| Outbox → CDC → PG | ✅ 0 pendentes; 127 eventos processados (dna 104, spin 14, spin_result 9) |
| ANALYZE pós-batch (H4) | ✅ `analyze_done tables=6` no log do worker |
| WAL archiving | ✅ `last_archived 18:05Z`, sem falhas novas |
| `ae_latent` dos giros novos | ⚠️→✅ achado #5 abaixo; corrigido e de volta a **100%** (cw 3.604/3.604, ccw 3.383/3.383) |

**Achado #5 — `ae_latent` não é preenchido no ingest (gap operacional, não bug):** por design
do H5, o hot path (app e CDC worker) **não** carrega joblib/scikit-learn; o embedding 6d→4d é
batch. O backfill do rollout foi one-shot com deps efêmeras — giros novos ficavam `NULL` até
alguém rodar de novo. **Fechado com rotina permanente:** `scripts/ae-latent-nightly.sh`
(container efêmero `python:3.12-slim` na rede do PG, repo montado RO, idempotente) + cron
`/etc/cron.d/roleta-ae-latent` (04:25, após o walg-backup). Detalhe de infra: numpy pinado em
`1.26.4` (wheels numpy≥2 exigem x86-64-v2, que a CPU do host não suporta) e scikit-learn
`1.9.0` (versão exata dos `.joblib`). Testado 2× em produção: `+22` e `+4` rows.


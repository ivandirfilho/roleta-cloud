# Evolução 03/08 — Infra de dados estruturados p/ otimização de predição + imersão na estratégia

**Data:** 2026-08-03 · **Fonte:** produção `xmaiajpvm` (187.45.181.75), leitura read-only via SSH/Docker
**Escopo:** (1) auditoria de população e formato dos bancos; (2) imersão nas jogadas de hoje; (3) proposta de evolução.
**Referências:** `fluxo_mental_24.md` (blueprint), `evolução_24_junho.md` (metodologia), `resultados_bancos_junho.md`.

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

1. **`decision_dna.realized_lift_pp` = NULL em 41.290/41.290 rows** (desde 26/05).
   O DNA loga `feature_name`/`feature_value`/`estimated_lift_pp` a cada decisão (8 features/giro:
   sda_score, tr_c4_rate, calibration_offset, kill_v4, region_C1/C2/C3, hit_region), mas o **feedback
   do lift realizado nunca é escrito**. Sem ele não há como ranquear quais features realmente
   discriminam hit/miss — o coração da proposta de otimização está cego.
2. **`ae_latent` nunca preenchido** → a busca vetorial usa só as 6 features cruas; o espaço latente
   comprimido (v4) que reduziria ruído p/ regime-matching não existe na prática.
3. **Grafo AGE vazio** → decisão pendente: popular (transições número→número por dealer/mesa) ou
   despriorizar formalmente e remover do stack (custo de manutenção sem uso).
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
feedback quantitativo**: DNA sem lift realizado, vetores sem latente, hit-rate global 9 p.p. abaixo do
breakeven da aposta atual. Hoje o lucro veio de gestão de stake + sorte de sessão. Para a proposta
(otimizar predição com dados estruturados), o dado bruto está pronto; falta **ligar a analítica**.

---

## 4. Próximos passos propostos (candidatos a sprint — decisão do Diretor)

| # | Ação | Tipo | Por quê |
|---|---|---|---|
| P1 | Popular `realized_lift_pp` no `dna_logger` (janela rolante hit-rate por feature vs baseline) + backfill 41k rows | Flag default-OFF + migração aditiva | Destrava ranking de features com dado real; pré-requisito de qualquer otimização honesta |
| P2 | Rodar `train_autoencoder.py` sobre `spin_features` e backfillar `ae_latent` (cw/ccw) | Job offline, sem tocar caminho da aposta | Ativa regime-matching por similaridade no espaço comprimido |
| P3 | Estudo C2-dominância: hit% por região × dealer × direção nas últimas N sessões (query-only) | Análise | 61% dos hits em C2 hoje; se persistir, redesenho do par de aposta com evidência |
| P4 | Painel "hit-rate vs breakeven por modo de aposta" no Grafana (47,2% force17) | Observabilidade | Torna visível quando o edge some, antes do PnL sentir |
| P5 | Go/no-go do AGE: popular grafo de transições ou remover do stack | Decisão | Peça vazia há 70 dias custando manutenção |
| P6 | Investigar queda de `vision_source` (60% hoje) na sessão madrugada | Bugfix leve | Metadata de visão alimenta P2/P3 |

**Invioláveis respeitados em qualquer P#:** INV-3 (APOSTAR sempre; veto só via `min()` no stake),
flags default-OFF na compose, migrações aditivas, round-trip `save/load/reset_session`, entrega por PR.

---

*Gerado em 2026-08-03 a partir de inspeção read-only da produção. Nenhuma configuração foi alterada.*
````
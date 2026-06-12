# Próximos Passos — 10/06/2026 · REESTRUTURADO 12/06 · IMPLANTADO 12/06 ✅

> Avaliação de dev senior. Base: grafo do código (`graphify-out/`, 2326 nodes), grafo do
> servidor (`server_snapshot/graphify-out/`), SQLite de produção (5384 decisões, 4131 com
> resultado+centros) e **auditoria do código da estratégia feita em 12/06**
> (`strategies/sda17.py`, `state/game.py`, `server/message_handler.py`).
>
> **Regra deste plano: nenhuma decisão espera dado novo — tudo é decidível com o que já
> temos.** A versão anterior deste arquivo (estrutura P0/P1/P2) está preservada no git;
> os itens que sobreviveram foram absorvidos nas Trilhas A/B/C abaixo.
>
> **STATUS DA IMPLANTAÇÃO (12/06 tarde):** B1 ✅ · B2 ✅ · B5 ✅ · C2 ✅ (CI **verde**
> pela 1ª vez desde 27/05, run 27427475837) · A1–A3 ✅ (relatório
> `analise_regioes_12_06.md`, snapshot de produção n=4131) · C1 ✅ (prod 0006→**0008**;
> deploy roda alembic) · C3 ✅ (backup diário decisions.db + **wal-g ressuscitado** —
> causa-raiz: git index 100644 removia +x a cada deploy → Permission denied no cron desde
> 25/05; corrigido no index e cron via /bin/bash) · Deploy: `86eda30`+`2a15074` em prod,
> healthy. Suite: 362 passed.
>
> **Gates decididos pelos dados (12/06):**
> - **B3 (modulação por volatilidade): NÃO se justifica agora** — A3 provou assimetria
>   EPISÓDICA (44.3% alternância), não estrutural; o fix correto é o B1 (já em prod).
>   Reavaliar só se a assimetria persistir nas janelas pós-B1.
> - **B4 (region_bandit com dado real): aguardando amostra** — `hit_region` começou a
>   acumular agora (B2 em prod); ligar quando ≥20 amostras/região/sentido pós-reset.

> **AUDITORIA 12/06 (tarde) — premissas de indicação:** owner definiu que a estratégia
> principal **nunca fica sem indicação de aposta** (exceto nas 2 primeiras oportunidades
> de cada sentido = calibração) e que pós-reset a indicação plena começa após **2
> resultados do sentido**. Verificado: a cadência base JÁ cumpria (1ª oportunidade sem
> dados → PULAR; 2ª → fallback N=21 indica; 3ª+ → SDA pleno 17). **3 bugs corrigidos:**
> (1) gates B5 de 12/06-manhã faziam PULAR (score<4/stop-loss/TR) — violava a premissa;
> agora seguem **INV-3**: indicação sempre, stake modulado (score<4/TR → ×0.10;
> stop-loss → 1u mínimo); (2) **ledger**: `gale_bet_value` gravava o stake BASE e não o
> efetivo pós QW-1/QW-2/INV-3 — P&L ficava distorcido sob modulação; (3) **fallback
> salvo/exibido com números VAZIOS** (121/121 em prod: `sda_numbers=[]`, hit nunca
> avaliado, overlay sem indicação) — Decision/overlay/trace/DNA agora usam a indicação
> FINAL. Testes: `tests/test_audit_cadence_12_06.py` (cadência integração + INV-3 +
> ledger). Suite: 367 passed.

> **AUDITORIA 12/06 r2 (feedback adaptativo × medição por região, commit `bf479e3`):**
> BUG-A `c1_predicted > 0` pulava o feedback quando C1=0 (~2.7% dos spins); BUG-B o
> sigmoid aprendia com cobertura RECALCULADA (≠ aposta real no fallback N=21 e na borda
> do cooldown) — agora `update_adaptive` recebe `coverage`/`centers` do pending; BUG-L
> stop-loss lia o P&L com 1 spin de atraso — `update_result` movido para antes dos gates.
> MELHORIA-G: EMA do erro assinado por região/sentido (`region_err_ema`) persistida,
> zerada no reset, exposta em `/api/strategy` + gauge `roleta_region_err_ema` — telemetria
> que decidirá o controlador por região (gated A4). Suite 374. Primeira leitura ao vivo:
> ccw `{c1:+13.6, c2:+1.6, c3:−12.4}`.

---

## 0. Premissas do owner (12/06) — governam todo o resto

| # | Premissa | Implicação no plano |
|---|---|---|
| P1 | Decidir com os dados atuais (5347 decisões); **não esperar resultados novos** | Toda a Trilha A é análise offline do histórico |
| P2 | Segurança de host: ignorada e deixada de lado | Fora do escopo (achados preservados em `server_snapshot/08_seguranca.md`) |
| P3 | Foco: **fluxo de dados + execução da estratégia** | Trilha C protege o fluxo; Trilhas A/B atacam a estratégia |
| P4 | Jogada = 3 regiões: C1 = 1 central + 3 vizinhos (7 nºs); C2 e C3 = 1 central + 2 vizinhos (5 nºs cada) = **17 números** | Geometria já implementada em `sda17.py` — não mexer sem evidência |
| P5 | Pergunta central: a indicação da estratégia está compondo **as 3 melhores regiões** da jogada? | Hoje NÃO é medido — desbloqueio em A1/A2 |
| P6 | Sentidos isolados: dados cw → decisão cw; dados ccw → decisão ccw, **sempre** | Já é invariante do código (INV-1) — preservar em qualquer mudança |
| P7 | Sintoma: muito assertivo num sentido, errático no outro; objetivo = máximo nos dois, cada um com seus próprios dados/previsões | Diagnóstico A3 + correções B1/B3 |
| P8 | Estratégia única, **genérica e adaptativa por jogada** — nunca especializada por sentido | Proíbe parâmetro hard-coded por direção; adaptação é por estado, não por config |
| P9 | Fine-tuning inicial: **2 jogadas em cada sentido** | Já implementado (`BAYESIAN_WARMUP=2`) — preservar |
| P10 | Troca de dealer → **botão manual zera a estratégia** para começar de novo | **GAP descoberto 12/06: o botão NÃO zera a estratégia** (Achado 1, fix B1) |
| P11 | A estratégia principal **sempre indica a melhor aposta da jogada**; sem indicação SÓ nas 2 primeiras oportunidades de cada sentido (calibração) | Auditoria 12/06-tarde: gates viram modulação de stake (INV-3 global) |
| P12 | Pós-reset: indicação **plena** (17 números) a partir de **2 resultados/forças do sentido** | Já cumprido por `min_forces=2`; coberto por teste de integração |

---

## 1. Auditoria 12/06 — premissas × código real

### O que o código JÁ cumpre (não mexer, só preservar)

| Premissa | Onde está | Estado |
|---|---|---|
| Geometria 7+5+5 = 17 | `sda17.py`: C1 raio 3 fixo (`num_neighbors=3`); C2/C3 raio 2 (`C2_RADIUS=C3_RADIUS=2`) posicionados por offsets adaptativos assimétricos | ✅ |
| Isolamento por sentido (P6) | `cw_history`/`ccw_history`, `_sigmoid_off` por dir, `_recent_hits` por dir, batch tune com contadores independentes (INV-1) | ✅ |
| Warmup 2 por sentido (P9) | `BAYESIAN_WARMUP=2`; 1ª jogada de cada sentido usa fallback SDA-19; QW-6 warmup adaptativo 2 (ganhando) / 5 (perdendo) | ✅ |
| Genérica → evolutiva (P8) | Parte de `PRIOR_CENTER=10` (prior genérico) e evolui via sigmoid feedback por jogada + batch auto-tune a cada 4 spins/sentido | ✅ |

### 🔴 Achado 1 — O botão de reset NÃO zera a estratégia (viola P10)

`handle_new_session` → `game_state.reset_session()` zera timelines, martingale, shadow grid
e bandit, **mas o objeto `SDA17Strategy` (vivo em `MessageHandler.strategy`) mantém
intactos**: `_sigmoid_off` (offsets C2/C3 aprendidos), `cw_history`/`ccw_history`,
`_recent_hits`, contadores do batch tune, cooldowns (QW-4) e drift freeze (QW-7). No spin
seguinte, `get_adaptive_state()` regrava tudo em `_adaptive_state`.

Consequências diretas nas premissas:
- O dealer novo **herda os offsets do dealer anterior** — pode casar por acaso num sentido
  e ficar tóxico no outro. **Causa mecânica plausível do sintoma P7** (assertivo num
  sentido, errático no outro).
- O warmup de 2 jogadas (P9) **nunca recomeça** — a estratégia não "começa de novo
  genérica" como o owner espera ao apertar o botão (P8/P10).

### 🔴 Achado 2 — "As 3 melhores regiões?" não é medido (viola P5)

`check_prediction()` grava apenas o hit binário (`actual_number in numbers`). Não grava:
**em qual região caiu** (C1/C2/C3), a que **distância circular** de cada centro, nem onde
caiu quando errou. O DNA `region_C1/C2/C3` (SP-17) loga o *offset usado*, não a atribuição
do resultado. Detalhe: `_pct_sigmoid_update()` já calcula os conjuntos `c1_nbrs/c2_nbrs/
c3_nbrs` por spin para o feedback sigmoid — e **descarta** a informação em seguida.

Sem isso é impossível dizer se C2/C3 pagam os 10 números que custam, nem se o erro vem do
preditor de força (C1 mal posicionado) ou do posicionamento dos satélites (offsets).

---

## 2. Trilha A — Responder à pergunta central com os dados ATUAIS (offline, começa hoje)

**Fonte:** `decisions.db` (5347 decisões: `sda_numbers`, `sda_centers`, `result_actual`,
`result_hit`, direção, sessão) + `decision_dna` (791) + `gale_windows`/`window_plays`.
Para decisões antigas sem `sda_centers`, os 3 centros são re-deriváveis dos 17 números
(3 arcos contíguos na roda → centro de cada arco; o arco de 7 é C1).

**Entregável:** `scripts/analyze_regions_offline.py` + relatório `analise_regioes_12_06.md`
com as 4 análises abaixo — **sempre segmentadas por sentido (P6)**.

### A1 — Atribuição de acerto por região (a métrica que falta)
Para cada decisão com resultado: classificar em `hit_C1 / hit_C2 / hit_C3 / hit_overlap /
miss` + distância circular assinada `Δ(result, C1)`. Saídas por sentido:
- Hit-rate e **lift por slot** vs acaso (C1: 7/37 = 18.9%; C2/C3: 5/37 = 13.5% cada).
- **EV por slot** (payout 36:1, N=17): cada região justifica os números que ocupa?
- Critério de decisão: se C2 ou C3 tiver lift ≈ 0 num sentido, a "3ª melhor região" não
  está onde apostamos — entrada direta para recalibrar o range de offsets (`OFFSET_MIN/MAX`).

### A2 — Oracle das 3 melhores regiões (regret)
Por janela entre resets e por sentido: histograma circular de `Δ(result, C1)` (37 posições).
- As 17 posições apostadas (C1±3, C2±2, C3±2) estão entre as **17 de maior densidade
  empírica** da janela? Métrica: `region_efficiency` = densidade capturada / densidade das
  17 ótimas a posteriori. **Esta métrica responde P5 diretamente.**
- Decompor o regret: erro de C1 (distribuição de Δ não centrada em 0 → problema no preditor
  de forças) × erro de offset (massa em posições fora de C2/C3 → problema no sigmoid).
  Diz exatamente **o que** corrigir, sem chute.
- Comparar offsets ótimos a posteriori vs `_sigmoid_off` praticado (snapshotado no DNA).

### A3 — Diagnóstico da assimetria entre sentidos (P7)
Por sessão e por janela entre resets: hit / EV / `region_efficiency` cw × ccw.
- A erraticidade do sentido fraco é **estrutural** (sempre o mesmo sentido?) ou
  **episódica** (alterna por sessão/dealer)? Episódica reforça o Achado 1 (estado herdado).
- Correlacionar o sentido errático com: nº de spins da janela (warmup insuficiente?),
  variância/IQR das forças daquele sentido, e idade do estado adaptativo no início da janela.
- **Simular no histórico** (via `tools/backtest_harness.py`): replay com reset TOTAL da
  estratégia nos inícios de janela (como P10 manda) e medir se o sentido fraco melhora.
  Se melhorar, B1 sozinho ataca P7 — sem tocar no algoritmo.

### A4 — Validação walk-forward (regra para TODA mudança)
Qualquer mudança candidata (B3/B4, recalibração de offsets, geometria) só entra se melhorar
**EV/aposta** em treino (jan–abr) **e** teste (mai–jun), **por sentido**. Hit rate NÃO é
critério (breakeven depende de N; março provou: melhor hit = pior P&L). Filtro por hora
segue proibido (overfit comprovado: +1.81 treino → −2.09 teste).

### §2.1 — VEREDITO A1–A3 (12/06, n=4131 de produção) — `analise_regioes_12_06.md`

**A1 — As 3 regiões NÃO são as 3 melhores (resposta a P5): nenhum slot tem lift.**
| Sentido | C1 lift | C2 lift | C3 lift |
|---|---|---|---|
| cw | **−1.3pp** | +0.0pp | −0.1pp |
| ccw | −0.5pp | −1.0pp | +1.2pp |

Todos os slots capturam ≈ acaso (C1: 18.9%; C2/C3: 13.5%). O preditor de força não está
agregando edge mensurável em nenhuma região, em nenhum sentido.

**A2 — region_efficiency: cw 83.9% · ccw 89.7%; viés de C1 ≈ 0 (−0.03/+0.01 posições).**
A geometria 7+5+5 captura 84–90% do teto a posteriori — o posicionamento relativo é
razoável e **não há erro sistemático de força**. O problema não é "onde" apostamos: a
distribuição de Δ(result, C1) é ≈ uniforme → **não há sinal explorável na relação
força→resultado dos dados atuais**. Recalibrar offsets renderia no máximo ~10–16% de
densidade extra (gap até o teto), que ainda é ≈ acaso.

**A3 — Assimetria é EPISÓDICA, não estrutural:** CW melhor em apenas 35/79 sessões
(44.3% — alterna); gap médio 14.5pp; 28/79 sessões com gap ≥ 15pp. Consistente com o
Achado 1 (estado adaptativo herdado entre dealers) → **B1 (reset de verdade) é o fix
certo** e está implantado. B3 (modulação por volatilidade) fica em observação pós-B1.

**Sanity do PROFIT-LEDGER:** EV reconstruído pelo script = −1.055u/aposta (≈ −1.107 do
10/06 ✓) e CUT v1 simulada = −0.228u/aposta (≈ −0.19 do walk-forward ✓) — fórmula do
ledger validada contra duas análises independentes. CUT v1 corta ~78% da perda → ON.

**Conclusão executiva:** pipeline sólido, estratégia sem edge sobre RNG nos dados atuais.
Ações corretas já tomadas: parar a sangria (B5 ON), eliminar contaminação entre dealers
(B1), instrumentar a pergunta P5 continuamente (B2). A única hipótese de EV>0 que resta é
**bias físico de dealer/mesa** (C4, rebaixado mas documentado) — ou o Plano B (§7).

---

## 3. Trilha B — Execução da estratégia (mudanças cirúrgicas, flag-guarded)

### B1 — Reset de verdade no botão de dealer (P10) — **primeira mudança de código**
- Criar `SDA17Strategy.reset_adaptive()`: zera `_sigmoid_off`, `cw_history`/`ccw_history`,
  `_recent_hits`, contadores de batch tune, cooldowns e drift freeze → volta ao prior
  genérico (P8) e re-arma o warmup de 2 jogadas por sentido (P9).
- Chamar em `handle_new_session` logo após `reset_session()`; expurgar as chaves SDA de
  `game_state._adaptive_state`.
- Teste de aceitação: pós-reset, a 1ª jogada de cada sentido usa fallback SDA-19 e offsets
  = default (10/10).
- Logar evento `strategy_reset` no DNA para medir o efeito nas janelas futuras.
- Flag desnecessária — é o comportamento que o owner já espera do botão.

### B2 — Instrumentar atribuição por região no fluxo vivo (versão live do A1)
- `check_prediction()`/`store_prediction()`: persistir `hit_slot` e `Δ(result, C1)` por
  decisão (migração 0009 + DNA feature `hit_region`).
- Aproveitar os conjuntos `c1_nbrs/c2_nbrs/c3_nbrs` que `_pct_sigmoid_update` já calcula
  e hoje descarta (custo ~zero).
- A partir daí o sistema responde P5 **continuamente**, sem análise manual.

### B3 — Adaptação modulada pela volatilidade do sentido (P7 sem violar P8) — gate: A3
- Manter UMA estratégia genérica; modular apenas a **velocidade** de adaptação pelo estado
  do sentido (ex.: `SIGMOID_SCALE`/`lr_batch` efetivos em função da variância recente das
  forças daquele sentido — o batch tune já moduliza lr por volatilidade, é estender).
- Nada de parâmetro fixo por direção (P8). O sentido "difícil" se auto-regula mais devagar
  ou mais rápido conforme os próprios dados (P6).
- Gate duplo: A3 indicar assinatura de sub/over-adaptação no sentido errático **e** A4
  (walk-forward por sentido) aprovar.

### B4 — `region_bandit` ligado ao dado real — gate: B2 acumular
- `choose_region` (SP-18) hoje decide com buckets de *offset*; religar com `hit_region`
  real (atribuição B2). Gate: ≥20 amostras por região por sentido. Não bloqueia nada.

### B5 — CUT-POLICY v1 + PROFIT-LEDGER — aplicar JÁ (decisão com dados atuais, P1)
- `score ≥ 4 & gale ≤ 2 & nunca N=19`: única política consistente nos dois períodos do
  walk-forward (−1.33→−0.19 treino; −0.78→−0.19 teste; corta ~80% da sangria). Flag
  `PROFIT_CUT_V1`.
- PROFIT-LEDGER: `pnl_units` por decisão no `check_prediction`/repo + `sessions.total_profit`
  + gauge `roleta_session_pnl` — pré-requisito para auditar qualquer leitura de EV em prod.
- Stop-loss automático −30u/sessão + investigar as 49 janelas `orphan` de `gale_windows`.
- (Herdado do plano de 10/06 §6 — continua válido sob as novas premissas.)

---

## 4. Trilha C — Fluxo de dados mínimo para sustentar A e B (lente P3)

| # | Item | Porquê | Esforço |
|---|---|---|---|
| C1 | `alembic upgrade head` em prod (0006→0008) + step de alembic no `roleta-deploy-pull.sh` | B2 precisa da migração 0009; sem alembic no deploy ela nunca chega a prod; `decision_dna` PG não existe lá hoje | 0.5d |
| C2 | CI verde: 1 linha `alembic upgrade head` no `ci.yml` pós-bootstrap (causa: `UndefinedTable cw.spins_vectors`) | Trilha B muda código de estratégia — sem CI confiável é voo cego; main vermelho desde 27/05 | 0.5h |
| C3 | Backup do `decisions.db` (dump diário `sqlite3 .backup` + rotação 7d) e religar wal-g (morto desde 25/05) | P1 manda decidir com os dados atuais — eles são **insubstituíveis** e hoje têm zero backup | 0.5d |
| C4 | DEAL capture (dealer/table reais) | **REBAIXADO**: o botão manual de reset (P10) já segmenta as janelas por dealer no fluxo da estratégia; dealer automático vira oportunidade futura (offset prior por dealer), não bloqueador | — |

---

## 5. Sequência executiva

```
D0 (hoje):  C2 (CI verde, 1 linha) · C1 (alembic prod) · C3 (backup) · kickoff A1/A2/A3
D1–D2:      A1+A2 prontos → 1º veredito sobre P5 (as 3 regiões são as melhores?)
            B1 (reset fix) implementado + testado · B5 (CUT-POLICY v1 + ledger) em prod
D3:         A3 pronto → diagnóstico do sentido errático (estrutural × episódico × herdado)
D4–D5:      B2 (instrumentação live de hit_region, migração 0009)
depois:     B3/B4 somente com aprovação de A3/A4 (walk-forward, por sentido)
```

Dependências: A1–A3 não dependem de nada (rodam offline hoje). B1 não depende de A.
B2 depende de C1 (migração). B3/B4 dependem de A3/A4/B2. B5 não depende de nada.

---

## 6. O que explicitamente NÃO fazer

- **Segurança/hardening** (P2 — descartado; achados preservados em `server_snapshot/08_seguranca.md`).
- **Especializar parâmetros por sentido** — viola P8; adaptação é por estado, nunca por config.
- **Esperar tráfego novo para decidir** — viola P1; análise é offline, prod só audita.
- **Otimizar/decidir por hit rate** — KPI é EV/aposta (breakeven depende de N coberto).
- **Filtro por hora do dia** — overfit comprovado no walk-forward.
- **Mexer na geometria 7+5+5** sem A2 indicar — P4 é premissa, não hipótese.
- AGE (schemas vazios → remover quando tocar no compose), VECTOR/autoencoder (adiar),
  OTel/SP-32 (zero impacto), coverage ramp (oportunista), novas features de ML antes de
  A1–A3 responderem P5/P7.

---

## 7. Evidência — números que sustentam este plano (SQLite 10/06, n=3996 com DNA)

- **O sistema nunca mediu lucro:** `sessions.total_profit = 0.0` em 151/151 sessões →
  PROFIT-LEDGER incluído no B5.
- **EV real reconstruído:** −1.107u/aposta (−4.9% do stake de 91.003u) — pior que aleatório
  (−2.7%), porque a martingale concentra stake nos piores momentos e a config N=19 é tóxica
  (−3.10/aposta; breakeven 52.8% vs hit real 47.4%).
- **Hit por profundidade de gale:** 87.9% → 73.9 → 69.2 → 57.0 → 50.6% (play 1→5) —
  fundamenta `gale ≤ 2`. Gale 3 = −6.60/aposta; gale 2 em N=17 = +1.02.
- **Offsets:** sem offset 47.78% (n=2028) vs sigmoid 46.17% (n=1878) — confounding temporal
  possível; **A2 (oracle de offsets) decide com o histórico**, sem A/B novo (P1).
- **Walk-forward:** `score≥4 & gale≤2 & N≠19` é a única política consistente (−0.19/−0.19
  por aposta nos dois períodos); filtro por hora = overfit (+1.81 → −2.09).
- **Por sentido:** atribuição de acerto por região **não existe ainda** → A1 é o desbloqueio
  de toda a linha P5/P7.
- score 4 = sweet spot (−0.32); score 6 = saturado/tóxico (−6.22, n=36); `tr_confidence`
  inútil para EV ('alta' −1.23 vs 'baixa' +0.02).

**Plano B estratégico** (inalterado): se nem com regiões otimizadas houver EV>0, o ativo —
pipeline tempo-real, extensão, DNA, observabilidade — vira produto de análise/disciplina
de banca para terceiros; PROFIT-LEDGER (B5) é pré-requisito desse pivô também.

---

## Apêndice — evidências coletadas em 10/06

- Grafo do servidor: `server_snapshot/graphify-out/graph.html` (66 nodes, 92 edges, 7 communities)
- Inventário: `server_snapshot/0[1-8]_*.md`
- CI failing: runs `26490411079` (main, 27/05) — `UndefinedTable cw.spins_vectors`
- Suite local: `347 passed, 9 skipped, 1 xfailed` (10/06)
- SQLite: decisions=5347, sessions=150, decision_dna=791, gale_windows=961, window_plays=3889;
  calibration fill pós-27/05 = 89/129 (69%)
- PG: cw.spins_vectors=816, ccw=831, spin_features=531/533, outbox processed=2706/failed=0
- wal-g: último `DONE` em 2026-05-25T04:30Z
- Auditoria de código 12/06: `sda17.py` (geometria/warmup/isolamento ✅), `state/game.py`
  `reset_session()` (não zera SDA17 — Achado 1), `check_prediction()` (hit binário apenas —
  Achado 2), `server/message_handler.py` `handle_new_session` (não chama reset da estratégia)

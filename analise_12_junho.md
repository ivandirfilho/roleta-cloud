# Análise 12 de Junho — Engenharia Reversa das Últimas 100 Jogadas por Sentido

> **Método:** reconstrução independente, decisão a decisão, do fluxo completo
> `spin → força → C1 → offsets → C2/C3 → 17 números → bola → slot/erro → P&L`,
> usando somente os dados gravados (`decisions_prod` 20:18 BRT, 5665 decisões, 281 de hoje)
> e a mecânica exata do código (`_calculate_force`, `_apply_force`, raios 3/2/2).
> **Validação da reconstrução: 97/100 (cw) e 99/100 (ccw)** — a força prevista recomputada
> de `last_number→C1` bate com `sda_predicted_force` gravada (3 divergências = decisões
> em borda de reload de config; desprezível). O que se lê abaixo é o que o sistema
> REALMENTE fez.
>
> **Semântica corrigida (descoberta desta análise, verificada 34/34):**
> `decisions.spin_direction` é a direção do spin que CHEGOU; a aposta/predição é para o
> sentido OPOSTO (target). Janela analisada: 100 decisões RESOLVIDAS por sentido-ALVO
> (18:06→23:18 UTC de 12/06 — toda a sessão da noite, 13 sessões de dealer).

---

## 1. O fluxo de dados, estágio por estágio (engenharia reversa)

### E1 — Entrada: spin `(numero, direcao)` chega via WS
- `process_spin` calcula a força DIRECIONAL do último número global para o atual
  (`(to-from) % 37` no sentido do spin) e a empilha na timeline DESSE sentido.
- **Ponto auditado:** a força usa `last_number` GLOBAL (do spin do sentido oposto) —
  correto para roda física contínua; cada sentido enxerga só suas forças (INV-1 ✓).
- 💡 *Insight E1:* força real média cw=16.3 (σ=11.3), ccw=18.1 (σ=11.1). σ≈11 casas
  numa roda de 37 = a força é QUASE uniforme. Qualquer preditor pontual de força tem
  teto baixo — o jogo está em capturar VIÉS de posição, não a força exata.

### E2 — Janela adaptativa de forças (7→5→3→2) + IQR
- `analyze` pega as últimas N forças do sentido-alvo, rejeita outliers por IQR,
  exige `clean_count ≥ max(2, N/2)`.
- **Auditado nas 100+100:** zero fallbacks de 1 centro na janela (toda decisão usou o
  pipeline completo — a calibração das 13 sessões ficou fora das 100 resolvidas plenas).
- 💡 *Insight E2:* com σ≈11, a mediana de 2-7 amostras é um estimador com erro padrão
  ≥4 casas. **Parâmetro candidato:** janela maior NÃO ajuda (autocorrelação da força
  t-1→t é −0.13 cw / −0.12 ccw ≈ ruído); o ganho não está aqui.

### E3 — Mediana ponderada → força prevista → C1
- `_apply_force(last_number, força_prevista, target)` anda na roda NO SENTIDO-ALVO.
- **Erro de força (real − prevista), assinado, normalizado −18..+18:**

| Sentido | média | mediana | σ | dentro de ±3 (zona C1) |
|---|---|---|---|---|
| cw | **+0.31** | 0 | 11.5 | 20.0% (acaso: 18.9%) |
| ccw | **+2.67** | **+3** | 10.4 | 19.0% |

- 💡 ***Insight E3 (o mais importante da noite):* o sentido ccw está com viés
  sistemático de +2.67 casas — a bola consistentemente PASSA do ponto previsto.**
  No espaço da roda isso é Δ(result,C1) = −2.67. A EMA ao vivo (implantada hoje)
  acusa o mesmo: `region_err_ema ccw c1 = −8.14 (n=14)` na sessão corrente.
  O histograma ccw é claramente assimétrico (massa em +3..+15).
- cw NÃO tem viés (+0.31 ≈ 0) — coerente com A2 do histórico (viés global ≈ 0).
  **O viés é episódico/por regime, forte HOJE no ccw.**

### E4 — Offsets adaptativos (M02-PctSigmoid) → C2/C3
- `sigmoid_off` ao vivo: ccw off2=10.16, off3=11.94; cw off2=11.68, off3=10.74 —
  **praticamente parados no prior (10)** apesar do viés de hoje.
- **Por construção, o sigmoid só reposiciona os SATÉLITES ao redor de C1 — nunca
  corrige o C1.** Com o erro dominante sendo de posicionamento GLOBAL (E3), o
  mecanismo adaptativo atual otimiza a variável errada: hit tighten (8% → prior) +
  regularizador (banda 8–12) o mantêm preso ao centro enquanto a roda "anda".
- 💡 *Insight E4:* Δmédios por região hoje — cw: C1 +0.31 / C2 +1.20 / C3 −0.85;
  ccw: C1 −2.67 / C2 +0.32 / C3 +1.90. Os satélites estão razoáveis RELATIVOS a C1;
  **o conjunto inteiro está deslocado no ccw.** Corrigir off2/off3 individualmente
  (Melhoria A) ajudaria menos que deslocar o TODO (micro-shift de C1, Melhoria B).

### E5 — União 7+5+5 → 17 números → INV-3/stake → overlay
- Auditado: 0 violações (gale≤2, N∈{15-17}, stake modulado, indicação sempre).
  Overlap médio reduz a cobertura a ~15-17 números como esperado.

### E6 — Bola cai → atribuição (slot, distâncias) → ledger
- Slots nas 100: cw C1=20/C2=13/C3=13/miss=54 · ccw C1=19/C2=8/C3=11/miss=62.
- vs acaso (C1 18.9% / C2 13.5% / C3 13.5%): **cw levemente acima em C1 (+1.1pp),
  ccw abaixo em C2 (−5.5pp)** — de novo o deslocamento: no ccw a bola caiu onde
  C2 ESTARIA se o conjunto andasse +3.
- P&L da janela: cw −107.3u (EV −1.07) · ccw **−310.8u (EV −3.11)** — a noite foi
  ruim, e o ccw foi o ralo. `region_efficiency`: cw 67.6% · ccw **55.9%** (vs 84/90%
  do histórico) — confirma regime atípico HOJE, não estrutura.

### E7 — Feedback adaptativo (pós-fix de hoje: aprende com a aposta REAL)
- O sigmoid recebeu o erro corretamente (fix BUG-B), mas pelo desenho (E4) não
  tem atuador para viés global. QW-7 (drift freeze) congelou em janelas de hoje
  (detector de hit-rate), mas freeze sem correção só pausa a sangria de offsets.

### E8 — Persistência/espelho (SQLite → outbox → PG → DNA → métricas)
- Validado de novo ponta a ponta na janela: 100% region/pnl preenchidos; PG
  failed=0; latência 244-420ms pós-fix do incidente (1 outlier 9.6s corrigido).

### E9 — Score/Triple-Rate como moduladores
- Por score na janela: cw score3 **+0.15 EV** (n=37) vs score4 **−1.95** (n=60);
  ccw score4 −2.88 (n=63), score5 −30 (n=3, ruído), score6 −4.27 (n=7).
- 💡 *Insight E9:* na noite de hoje o score NÃO ordenou EV (score3 > score4!).
  Com n=100 isso é ruído estatístico — mas reforça: score calibra CONFIANÇA do
  preditor de força, e quando o erro é de viés global (E3), score alto não protege.
  **Não mexer no gate score≥4 por 1 noite** (walk-forward de 4131 ainda manda),
  mas registrar: o gate certo para regime-de-viés é outro (ver §3).

---

## 2. Quantificação dos candidatos (na própria janela, mesma matemática do jogo)

### I1 — MICRO-SHIFT global da geometria (deslocar C1 e o conjunto inteiro)
Hit% recomputado com a geometria 7+5+5 deslocada `s` casas no sentido da força:

| s | cw | ccw |
|---|---|---|
| 0 (atual) | **47.0%** | 42.0% |
| +1 | 46.0% | 42.0% |
| +2 | 41.0% | 48.0% |
| **+3** | 42.0% | **57.0%** |
| +4 | 37.0% | **57.0%** |
| −5..−1 | ≤45% | ≤42% |

**Leitura:** cw já está centrado (s*=0 ✓ auto-validação do método). **ccw teria saído
de 42%→57% com s=+3/+4** — +15pp = ~+59u na janela. É in-sample de UMA noite; mas o
sinal é o mesmo da EMA ao vivo (−8.1, n=14) e do Δmediano (+3). O detector existe
desde hoje de manhã (`region_err_ema`); faltava o ATUADOR.

### I2 — AR(1)/momentum na força (corrigir pela força anterior)
Captura de C1 (|erro|≤3) com correção `−k·(f_{t-1}−média)`:

| k | cw | ccw |
|---|---|---|
| 0 | 20.0% | 19.0% |
| 0.10–0.30 | 15–18% | 16–20% |

**Leitura: MORTO.** Autocorrelação −0.13/−0.12 é fraca e NEGATIVA; qualquer correção
AR piora ou empata. Confirma com números a decisão antiga de desligar momentum/
errdriven. **Não reabrir esta linha.**

### I3 — Shadow grid já "viu" mas não age
O shadow grid (rotações +1/+3/+5/+10) é exatamente o detector do I1 — mas:
(a) auto-promote está OFF por design; (b) os shifts testados são só positivos e
globais (não por sentido na promoção); (c) janela de 100 com histerese é lenta para
regime de UMA sessão. Na sessão corrente: incumbent ccw acc 21% (n=14) — o grid
acumulando, sem agir.

---

## 3. Recomendações — parâmetros e gates (ordem de valor)

| # | Mudança | Parâmetros propostos | Gate antes de ligar |
|---|---|---|---|
| R1 | **Micro-shift de C1 por sentido** (Melhoria B, agora com desenho): deslocar TODO o conjunto pela EMA de erro do sentido | atuador: `shift = clamp(round(−region_err_ema_c1 · 0.5), −4, +4)` aplicado ao índice de C1 no `analyze`; só com `region_err_n ≥ 10` na janela do dealer; zera no reset (P10); flag `REGION_SHIFT_V1` default OFF | Simulação offline nas 4131 + walk-forward por sentido (A4); critério: ΔEV > 0 nos 2 períodos e nunca pior que baseline em cw |
| R2 | **Sigmoid ganha atuador de C1 ou perde prioridade** — hoje ele otimiza satélites com C1 torto | alternativa barata: usar o MESMO sinal do R1 antes do posicionamento de C2/C3 (offsets ficam relativos ao C1 já corrigido) | herda gate do R1 |
| R3 | **Shadow grid por sentido com shifts ±** | shifts (−3,−1,+1,+3) POR SENTIDO, janela 30 (não 100), e auto-promote continua OFF — vira INSUMO do R1, não ator | nenhum (telemetria) |
| R4 | **Alerta de regime de viés** | `RoletaRegionBiasHigh`: `abs(roleta_region_err_ema{region="C1"}) > 4` AND `region_err_n ≥ 10` por 10min — operador vê "a roda anda; considere reset/mesa" | nenhum (alerta) |
| R5 | **NÃO fazer:** janela de forças maior, AR/momentum (I2 morto), mexer em score≥4 por causa de 1 noite, recalibrar OFFSET_MIN/MAX isolado (E4 mostrou que o problema não é o satélite) | — | — |

**Por que R1 respeita as premissas:** continua UMA estratégia genérica (P8) — o shift
nasce de 0 a cada reset (P10), evolui pelos dados DO sentido (P6) a partir de 2
jogadas (P9), e a indicação nunca some (P11). É a Melhoria B do plano, agora com
atuador, constante (0.5), clamp (±4) e gate definidos pela engenharia reversa.

---

## 4. Limitações honestas desta análise
- Janela de 100/sentido = UMA noite (13 dealers); I1 é in-sample — o +15pp do ccw é
  TETO, não expectativa. O histórico (A2, n=4131) mostra viés global ≈0: o ganho real
  do R1 vem de capturar viés EPISÓDICO rápido, e o risco é ruído com n baixo
  (por isso EMA + n≥10 + clamp ±4 + walk-forward).
- score×EV da noite (E9) tem n pequeno por célula — não conclui nada sozinho.
- 3/200 reconstruções divergiram (reload de config entre analyze e save) — ruído.

## 5. Artefatos
- `scripts/reverse_engineer_100.py` — motor reusável da engenharia reversa (rodar a
  qualquer momento: `python scripts/reverse_engineer_100.py [db]`).
- Snapshot analisado: prod 12/06 23:18 UTC (5665 decisões; 281 do dia).
- Cruzamentos ao vivo: `region_err_ema` (ccw c1 −8.14 n=14), `sigmoid_off` (~prior),
  shadow grid (incumbent ccw 21% n=14), painel `roleta-profit`.

---

# §6 — MODELO UNIVERSAL DE ADAPTAÇÃO POR JOGADA (replay causal, 23:30)

> Pergunta do owner: *"qual modelo universal, genérico e adaptável como regra geral,
> teria se adaptado melhor — transformando erros em acertos e mantendo os acertos?"*
> Método: **replay walk-forward causal** sobre TODAS as 2.762 decisões resolvidas com
> 3 centros (109 sessões; treino jan–abr 792 / teste mai–jun 1.970), por SENTIDO-ALVO,
> estado **zerado a cada sessão** (P10), decisão da jogada t usando SÓ erros até t−1
> (zero look-ahead). Métrica pedida: matriz **miss→hit / hit→miss** vs a aposta real.
> Motor: `scripts/universal_model_sim.py`. Grafos atualizados: repo 2.500 nodes /
> 2.598 edges; servidor 159 nodes (`server_snapshot/graphify-out/` + inventário
> `server_snapshot/10_inventario_12_06.md`, árvore 426 arquivos).

## 6.1 Os 6 competidores (todos genéricos, por jogada, idênticos nos 2 sentidos)

| Modelo | Atuador | Regra |
|---|---|---|
| M0 baseline | — | geometria como apostada |
| M1 ema-shift | C1 (conjunto inteiro) | `shift = clamp(round(−EMA(err, α=.2)·0.5), ±4)`, n≥3 |
| M2 med7 | C1 | `shift = clamp(round(−mediana(últimos 7)), ±5)` |
| M3 step | C1 | passo unitário `±1` por erro, clamp ±4 |
| M4 sigC1 | C1 | **transplante do M02-sigmoid atual** para o centro |
| M5 região | C1 + satélites | M1 no C1 **+ EMAs próprias de C2/C3** (satélites relativos, clamp ±2) |

## 6.2 Resultado (EV flat 17u isola o efeito geometria; saldo = miss→hit − hit→miss)

| Modelo | GERAL cw | GERAL ccw | TREINO cw/ccw | TESTE cw/ccw | Saldo 4 quadrantes |
|---|---|---|---|---|---|
| M0 | 45.6% · −0.60 | 44.0% · −1.16 | 41.8/44.6% | 47.1/43.8% | — |
| M1 ema | 46.7% · −0.18 | 46.9% · −0.11 | +4.0/+4.9pp | +0.0/+2.1pp | +16/+19/0/+21 |
| M2 med7 | 45.9% | 44.7% | +5.7/+0.8pp | −1.8/+0.6pp | ruidoso (≈300 trocas) |
| M3 step | 46.7% | 44.5% | +2.4/−1.0pp | +0.6/+1.1pp | misto |
| M4 sigC1 | **39.3%** ❌ | **39.4%** ❌ | −0/−4.3pp | −8.8/−4.7pp | **−87/−63** |
| **M5 região** | **47.8% · +0.21** | **46.5% · −0.27** | **+4.7/+3.6pp** | **+1.2/+2.0pp** | **+19/+14/+12/+20** ✅ |

## 6.3 Veredito — o modelo universal

**M5 — "EMA de erro circular assinado POR REGIÃO, por sentido, com atuador no
conjunto inteiro (C1) e correção fina relativa nos satélites" — é o modelo universal.**
É o ÚNICO com saldo miss→hit **positivo nos 4 quadrantes** (transforma erros em acertos
SEM perder acertos na mesma proporção: ~165 misses viram hits vs ~135 hits perdidos no
geral) e o único que **passa o gate A4 estrito**: ΔEV>0 em treino E teste, nos DOIS
sentidos, nunca pior que baseline em cw. No agregado, cw vira EV-flat **positivo**
(−0.60→+0.21) e ccw corta 77% da perda (−1.16→−0.27).

**Parâmetros do modelo (a implementar como `REGION_SHIFT_V1`, default OFF):**
`α=0.2 · K=0.5 · clamp C1 ±4 · clamp satélites ±2 · warmup n≥3 por sentido · zera no
reset (P10) · idêntico para cw/ccw (P8) · decide a cada jogada (premissa central) ·
infra já existe: `_region_err_ema`/`_region_err_n` implantados hoje são EXATAMENTE o
estado que o M5 consome.`

**Descoberta negativa igualmente valiosa (M4):** transplantar o sigmoid atual para o
C1 é destrutivo (−87 de saldo; hit 39%) — o passo de até 2 casas/miss overshoota num
processo com σ≈11. Isso **vindica o design** que o confinou aos satélites com
regularizador, e proíbe o atalho "aumentar a agressividade do que já existe".
A dinâmica certa para C1 é INTEGRAL lenta (EMA), não proporcional ao último erro.

## 6.4 Honestidade estatística
- Ganho agregado é modesto (+1.2–2.9pp hit; EV flat ainda ~0 — RNG continua RNG);
  o valor real do M5 está em **noites de viés** (como hoje: ccw teria +15pp).
- EV flat ≠ EV com gale/INV-3 — a simulação isola geometria; o stack de stake atual
  fica por cima inalterado.
- In-sample apenas no desenho dos 6 modelos; a EXECUÇÃO é causal (sem look-ahead) e
  validada treino→teste. Próximo passo: implementar atrás de flag + rodar como shadow
  (paralelo ao incumbent) por alguns dias antes de promover — o shadow grid (R3) vira
  o harness de promoção.

## 6.5 Roteiro de implementação (quando autorizado)
1. `SDA17Strategy`: aplicar `shift_c1 = clamp(round(−ema_c1·0.5), ±4)` no índice de C1
   dentro do `analyze` (flag `REGION_SHIFT_V1`); satélites: `off2_eff = off2 −
   clamp(round(ema_c2·0.5), ±2)` (idem C3, sinal oposto) — 1 ponto de código, usa
   estado existente.
2. Shadow paralelo: registrar hit do M5 por spin (como shadow_grid) para comparação
   incumbent×M5 ao vivo ANTES de ligar a flag.
3. Alerta R4 (`RoletaRegionBiasHigh`) já desenhado — operacionaliza o "regime de viés".
4. Promoção: M5 ON somente se shadow ao vivo confirmar o walk-forward em ≥300 spins.

# 📊 Análise 400 jogadas/sentido — C1/C2/C3 (21#) + filtro "só apostar após green"

> **Engenharia reversa** sobre as **últimas 400 jogadas resolvidas de cada sentido** (horário e
> anti-horário), **analisadas isoladamente**, reconstruindo a aposta **fixa C1/C2/C3 = 21 números**
> (como a estratégia estava originalmente configurada). Objetivo: medir o filtro **"só joga após um
> green"** por sentido (após um red, espera-se um green para voltar a apostar).

> **Fonte:** `decisions.db` de produção (servidor 187.45.181.75), capturado em 2026-06-17.

---

## 1. Metodologia

- **Amostra:** últimas 400 decisões **resolvidas** (`result_actual` preenchido) por sentido, em ordem cronológica. Cada sentido é tratado **isolado** (a sequência horária só usa spins horários e vice-versa).
- **Reconstrução 21#:** para cada jogada, uso os **3 centros** (`sda_centers` = C1, C2, C3) que a estratégia calculou e construo a cobertura = **união do raio 3** (7 números) de cada centro sobre a `WHEEL_SEQUENCE` real → **21 números** em 100% das 800 jogadas (centros disjuntos).
- **Green/Red:** `green` = a bola (`result_actual`) caiu dentro dos 21 números; `red` caso contrário.
- **Modelo financeiro:** aposta 1u em cada um dos 21 números (stake **21u**/jogada). Green → retorna 36u (**+15u** líquido); Red → **−21u**. **Breakeven = 21/36 = 58,33%** de acerto.
- **Filtro "após green":** aposta-se a jogada *i* **somente se** a jogada *i−1* do mesmo sentido foi **green**. Após um red, fica-se em espera (observando) até ver um green; então volta a apostar na jogada seguinte.

---

## 2. Resultados agregados

| Métrica | ♻️ Horário | 🔄 Anti-horário |
|---|---:|---:|
| Jogadas (N) | 400 | 400 |
| **Baseline (aposta TODAS as 400)** | | |
| &nbsp;&nbsp;Greens / Reds | 216 / 184 | 208 / 192 |
| &nbsp;&nbsp;Taxa de acerto | **54.0%** | **52.0%** |
| &nbsp;&nbsp;P&L (u) | **-624** | **-912** |
| **Filtro "só após green"** | | |
| &nbsp;&nbsp;Apostas colocadas | 216 | 207 |
| &nbsp;&nbsp;Puladas (em espera) | 184 | 193 |
| &nbsp;&nbsp;Greens / Reds | 116 / 100 | 98 / 109 |
| &nbsp;&nbsp;Taxa de acerto (condicional) | **53.7%** | **47.3%** |
| &nbsp;&nbsp;P&L (u) | **-360** | **-819** |
| **Diagnóstico de autocorrelação** | | |
| &nbsp;&nbsp;P(green \| green anterior) | 53.7% | 47.3% |
| &nbsp;&nbsp;P(green \| red anterior) | 54.6% | 56.8% |

> Breakeven = **58,33%**. Maior sequência de greens/reds: Horário **7G / 10R**; Anti-horário **6G / 12R**.

---

## 3. Veredito e insights

1. **O 21# fixo é −EV.** A taxa de acerto real (Horário **54.0%**, Anti **52.0%**) fica **abaixo do breakeven de 58,33%** — por isso o baseline perde nos dois sentidos (**-624u** e **-912u** em 400 jogadas).
2. **O filtro "só após green" NÃO cria vantagem.** A taxa de acerto *condicional* é **igual ou pior** que o baseline: Horário 53.7% vs 54.0%; Anti **47.3%** vs 52.0%.
3. **Há autocorrelação NEGATIVA (mean-reversion leve).** Nos dois sentidos, **P(green | red anterior) > P(green | green anterior)** (H: 54.6% > 53.7%; A: 56.8% > 47.3%). O green vem **mais** depois de um red — o filtro aposta justamente no momento *menos* provável.
4. **A "melhora" de P&L do filtro é ilusória.** O total fica menos negativo (H: -360 vs -624) **apenas porque se aposta menos** (216 vs 400 jogadas) — não porque o acerto melhora. Por aposta, o EV continua negativo.
5. **Nem o contrário salva.** Apostar "só após **red**" teria acerto melhor (H 54.6%, A 56.8%), mas **ainda abaixo** dos 58,33% — nenhuma regra de timing sobre o 21# flat vira lucro.

> **Conclusão:** com 21 números fixos (C1/C2/C3), a sequência é praticamente sem memória (leve mean-reversion). O filtro "jogar só após green" reduz exposição mas **não melhora o acerto** e **não torna a estratégia lucrativa**. Reforça o estudo `resultados_15_junho.md` e a decisão de migrar para 14# (par C2+C3).

---

## 4. Sequência completa (G = green, r = red) — ordem cronológica

### ♻️ HORÁRIO (400 jogadas)

`  1` rGGGGrGrGGrrrrrGGrrGrGGrGGGrGrGGGGGrrGGrrGGrrGrGrG
` 51` GrGrGGGrrGGrGrrGGGGGrrrrrrGrrrrGrGrGrGrGGGrGGGrGGG
`101` GGrGrGrrGGGGGrrrGrGGGGGGGrGrrGGrGGGrGrrGrGrrGGGrrr
`151` rrrrrGrGGGrGGGrrrGGGGrGrGGGGrrGrGGGGrGGrrGrrGGrrGr
`201` rrrrrGrGGGrGrGrGrrGGGrrGrGrGrrGrGGGGGGrGGrrGrGrGGr
`251` GGGrGGGrrrrGGGGrrrGrGGGGGrGrrGGGrGGrrrGGGGrGGGrGGG
`301` GrGrGrrrGrGrrGGGGrrGGrrrrrGGGrGrGrrrrrrrrrrGGGrGrr
`351` rGGGGGGrGrrrrGGGrrGGrGGrGrrGrrrGGGGrGGrGrGGrGGrrrr

### 🔄 ANTI-HORÁRIO (400 jogadas)

`  1` GGGrGGGrrrGrGGGGGGrGrrrrrGrGGrGrGrrGrGGrGrGrGrrrGG
` 51` GGrGGGrGGGGrrrrGGrGrGGrrGGrGGrGGGGrrrrGrGrrGrGrrGr
`101` GGGrGrrGrrrrrrGGGrGrrGrrrGrGrrGrrGGrrrGrGGrGGGrGrG
`151` rGGrGrGGrrrGrrGrGrrGGrGGGGrGGGGGrGrrrGGGGrrrGrrrGr
`201` rrGGGrrrGGrrGGrrGrGGrGGGrGGGGGGrGGrGrrrrGGrGGGGrGG
`251` GrrGrGGrGGGrGGrGrGrrrrGGrGGGGGrrGGrGrGrrGGrGGrGrGG
`301` rGGGGGrrGrrrGGGrGrGrGrGGrrrGrGGrrrGrGrGGGGrrGrGGGr
`351` rrrrGGrrrrGGrrGrGrGrGGrGrGrGrGrrrrrrrrrrrrGrGGGGrG

---

## 5. Detalhe das últimas 40 jogadas por sentido (onde caiu a bola × onde apostamos)

Colunas: **bola** = número sorteado · **C1/C2/C3** = centros apostados (cobertura = ±3 na roda de cada) · **resultado** = green/red (bola ∈ 21#) · **filtro** = se o filtro "após green" teria apostado · **P&L filtro** = acumulado do filtro naquele sentido.

### ♻️ Horário — últimas 40

| # | bola | C1 | C2 | C3 | resultado | filtro | P&L filtro (u) |
|--:|--:|--:|--:|--:|:--:|:--:|--:|
| 361 | **30** | 32 | 22 | 16 | 🔴 red | ⏸️ espera | -300 |
| 362 | **31** | 30 | 2 | 33 | 🔴 red | ⏸️ espera | -300 |
| 363 | **22** | 21 | 3 | 13 | 🔴 red | ⏸️ espera | -300 |
| 364 | **35** | 12 | 36 | 4 | 🟢 GREEN | ⏸️ espera | -300 |
| 365 | **0** | 32 | 23 | 34 | 🟢 GREEN | ✅ apostou | -285 |
| 366 | **3** | 23 | 32 | 14 | 🟢 GREEN | ✅ apostou | -270 |
| 367 | **35** | 15 | 10 | 14 | 🔴 red | ✅ apostou | -291 |
| 368 | **6** | 30 | 9 | 21 | 🔴 red | ⏸️ espera | -291 |
| 369 | **32** | 20 | 0 | 23 | 🟢 GREEN | ⏸️ espera | -291 |
| 370 | **24** | 12 | 6 | 16 | 🟢 GREEN | ✅ apostou | -276 |
| 371 | **11** | 25 | 16 | 7 | 🔴 red | ✅ apostou | -297 |
| 372 | **4** | 9 | 21 | 3 | 🟢 GREEN | ⏸️ espera | -297 |
| 373 | **25** | 24 | 34 | 22 | 🟢 GREEN | ✅ apostou | -282 |
| 374 | **15** | 31 | 12 | 11 | 🔴 red | ✅ apostou | -303 |
| 375 | **35** | 16 | 36 | 28 | 🟢 GREEN | ⏸️ espera | -303 |
| 376 | **2** | 0 | 1 | 29 | 🔴 red | ✅ apostou | -324 |
| 377 | **34** | 36 | 28 | 14 | 🔴 red | ⏸️ espera | -324 |
| 378 | **22** | 15 | 31 | 5 | 🟢 GREEN | ⏸️ espera | -324 |
| 379 | **21** | 31 | 8 | 3 | 🔴 red | ✅ apostou | -345 |
| 380 | **15** | 25 | 12 | 24 | 🔴 red | ⏸️ espera | -345 |
| 381 | **15** | 24 | 7 | 13 | 🔴 red | ⏸️ espera | -345 |
| 382 | **30** | 26 | 8 | 14 | 🟢 GREEN | ⏸️ espera | -345 |
| 383 | **23** | 9 | 34 | 24 | 🟢 GREEN | ✅ apostou | -330 |
| 384 | **8** | 3 | 36 | 31 | 🟢 GREEN | ✅ apostou | -315 |
| 385 | **34** | 33 | 25 | 28 | 🟢 GREEN | ✅ apostou | -300 |
| 386 | **2** | 6 | 9 | 0 | 🔴 red | ✅ apostou | -321 |
| 387 | **26** | 12 | 21 | 8 | 🟢 GREEN | ⏸️ espera | -321 |
| 388 | **25** | 10 | 21 | 28 | 🟢 GREEN | ✅ apostou | -306 |
| 389 | **14** | 34 | 5 | 29 | 🔴 red | ✅ apostou | -327 |
| 390 | **11** | 32 | 27 | 7 | 🟢 GREEN | ⏸️ espera | -327 |
| 391 | **4** | 24 | 6 | 3 | 🔴 red | ✅ apostou | -348 |
| 392 | **19** | 24 | 19 | 29 | 🟢 GREEN | ⏸️ espera | -348 |
| 393 | **1** | 24 | 35 | 6 | 🟢 GREEN | ✅ apostou | -333 |
| 394 | **30** | 20 | 32 | 6 | 🔴 red | ✅ apostou | -354 |
| 395 | **36** | 33 | 6 | 19 | 🟢 GREEN | ⏸️ espera | -354 |
| 396 | **34** | 17 | 23 | 29 | 🟢 GREEN | ✅ apostou | -339 |
| 397 | **20** | 4 | 27 | 29 | 🔴 red | ✅ apostou | -360 |
| 398 | **15** | 31 | 17 | 12 | 🔴 red | ⏸️ espera | -360 |
| 399 | **36** | 17 | 1 | 28 | 🔴 red | ⏸️ espera | -360 |
| 400 | **21** | 22 | 0 | 10 | 🔴 red | ⏸️ espera | -360 |

### 🔄 Anti-horário — últimas 40

| # | bola | C1 | C2 | C3 | resultado | filtro | P&L filtro (u) |
|--:|--:|--:|--:|--:|:--:|:--:|--:|
| 361 | **22** | 4 | 11 | 9 | 🟢 GREEN | ⏸️ espera | -663 |
| 362 | **12** | 29 | 34 | 33 | 🟢 GREEN | ✅ apostou | -648 |
| 363 | **33** | 25 | 8 | 0 | 🔴 red | ✅ apostou | -669 |
| 364 | **24** | 31 | 34 | 15 | 🔴 red | ⏸️ espera | -669 |
| 365 | **20** | 14 | 30 | 4 | 🟢 GREEN | ⏸️ espera | -669 |
| 366 | **36** | 1 | 12 | 34 | 🔴 red | ✅ apostou | -690 |
| 367 | **3** | 0 | 27 | 20 | 🟢 GREEN | ⏸️ espera | -690 |
| 368 | **22** | 3 | 6 | 33 | 🔴 red | ✅ apostou | -711 |
| 369 | **32** | 13 | 4 | 16 | 🟢 GREEN | ⏸️ espera | -711 |
| 370 | **27** | 29 | 15 | 23 | 🔴 red | ✅ apostou | -732 |
| 371 | **33** | 24 | 29 | 2 | 🟢 GREEN | ⏸️ espera | -732 |
| 372 | **12** | 11 | 20 | 7 | 🟢 GREEN | ✅ apostou | -717 |
| 373 | **32** | 5 | 2 | 22 | 🔴 red | ✅ apostou | -738 |
| 374 | **14** | 17 | 31 | 5 | 🟢 GREEN | ⏸️ espera | -738 |
| 375 | **25** | 24 | 26 | 36 | 🔴 red | ✅ apostou | -759 |
| 376 | **30** | 19 | 30 | 18 | 🟢 GREEN | ⏸️ espera | -759 |
| 377 | **10** | 20 | 27 | 7 | 🔴 red | ✅ apostou | -780 |
| 378 | **13** | 22 | 11 | 15 | 🟢 GREEN | ⏸️ espera | -780 |
| 379 | **4** | 3 | 34 | 1 | 🔴 red | ✅ apostou | -801 |
| 380 | **21** | 5 | 17 | 35 | 🟢 GREEN | ⏸️ espera | -801 |
| 381 | **29** | 13 | 24 | 35 | 🔴 red | ✅ apostou | -822 |
| 382 | **5** | 11 | 19 | 1 | 🔴 red | ⏸️ espera | -822 |
| 383 | **0** | 28 | 2 | 20 | 🔴 red | ⏸️ espera | -822 |
| 384 | **23** | 12 | 17 | 31 | 🔴 red | ⏸️ espera | -822 |
| 385 | **9** | 28 | 23 | 25 | 🔴 red | ⏸️ espera | -822 |
| 386 | **22** | 16 | 6 | 35 | 🔴 red | ⏸️ espera | -822 |
| 387 | **1** | 28 | 23 | 15 | 🔴 red | ⏸️ espera | -822 |
| 388 | **2** | 23 | 0 | 29 | 🔴 red | ⏸️ espera | -822 |
| 389 | **0** | 23 | 20 | 7 | 🔴 red | ⏸️ espera | -822 |
| 390 | **1** | 17 | 10 | 29 | 🔴 red | ⏸️ espera | -822 |
| 391 | **23** | 21 | 22 | 3 | 🔴 red | ⏸️ espera | -822 |
| 392 | **28** | 8 | 4 | 22 | 🔴 red | ⏸️ espera | -822 |
| 393 | **26** | 6 | 26 | 9 | 🟢 GREEN | ⏸️ espera | -822 |
| 394 | **35** | 9 | 25 | 5 | 🔴 red | ✅ apostou | -843 |
| 395 | **31** | 20 | 21 | 7 | 🟢 GREEN | ⏸️ espera | -843 |
| 396 | **5** | 24 | 32 | 29 | 🟢 GREEN | ✅ apostou | -828 |
| 397 | **19** | 28 | 2 | 10 | 🟢 GREEN | ✅ apostou | -813 |
| 398 | **20** | 36 | 14 | 28 | 🟢 GREEN | ✅ apostou | -798 |
| 399 | **32** | 12 | 1 | 34 | 🔴 red | ✅ apostou | -819 |
| 400 | **10** | 31 | 30 | 12 | 🟢 GREEN | ⏸️ espera | -819 |

---

## 6. Resumo executivo

| | Aposta todas (baseline) | Só após green (filtro) |
|---|---|---|
| Horário — acerto / P&L | 54.0% / -624u | 53.7% / -360u (216 apostas) |
| Anti-horário — acerto / P&L | 52.0% / -912u | 47.3% / -819u (207 apostas) |

**O filtro "só após green" não vira o jogo:** o 21# fixo acerta ~52–54% (< 58,33% de breakeven) e os greens não se agrupam (leve anticorrelação). Recomendação: manter a aposta enxuta de 14# (C2+C3) já em produção; usar o gate "após green" no máximo como **controle de exposição**, ciente de que ele **não** adiciona edge.

---

# 🧪 PARTE II — Desenvolvimento de estratégia vencedora (C2+C3 fixo + C1/timing)

> Estudo investigativo (10 estratégias) para achar uma regra **acoplada a C2+C3 fixo** com **resultado positivo por sentido isolado**, usando os registros de produção. Como o campo **`dealer` é 100% `unknown`** (não captura), uso **proxies de troca de dealer**: `session_id` (237 sessões) e **hora do dia** (turnos). Amostra: **2.194 jogadas horárias / 2.206 anti-horárias** com 3 centros resolvidas (id 2394–7501, ~5 meses).

**Métodos anti-overfit:** split **treino/teste 70/30**, **walk-forward** (só passado decide cada aposta, warmup 700) e **teste de significância** (z vs breakeven). Modelo: 14# → win +22 / −14 (breakeven **38,89%**); 21# → +15 / −21 (breakeven **58,33%**).

## 7. As 10 estratégias (resultado por sentido)

| # | Estratégia | Mecanismo | Método | Horário (hit / ROI) | Anti-horário (hit / ROI) |
|--:|---|---|---|---:|---:|
| 1 | C2+C3 (14#) — todas | baseline | full | 36.2% / -6.8% | 38.6% / -0.8% |
| 2 | C1+C2+C3 (21#) — todas | baseline | full | 55.1% / -5.4% | 55.9% / -4.1% |
| 3 | 14# **após GREEN** (ideia original) | timing | full | 34.1% / -12.3% | 36.1% / -7.1% |
| 4 | 14# **após RED** (mean-reversion) | timing | full | 37.5% / -3.6% | 40.1% / **+3.0%** |
| 5 | 14# + **hora favorável (estática)** | filtro | treino→teste | +10.9%→**-1.0%** | +11.1%→**-0.6%** |
| 6 | 14# + **hora adaptativa** | filtro | walk-fwd | 36.5% / -6.1% | 36.9% / -5.0% |
| 7 | 21# C1 = **região QUENTE** (últimas 120) | C1 variável | walk-fwd | 52.7% / -4.0% | 53.3% / -2.4% |
| 8 | 21# C1 = **região FRIA** | C1 variável | walk-fwd | 50.5% / -7.6% | 53.7% / -1.5% |
| 9 | 21# C1 = **repete bola anterior** | C1 variável | walk-fwd | 47.9% / -8.0% | 51.3% / -1.2% |
| 10 | **COMBO vencedor** (Anti: após-red · Horário: abster) | timing+abstenção | full/OOS | — (abster) | **40.1% / +3.0%** |

> ROI = P&L / total apostado. Em **negrito** os resultados positivos relevantes. **S5** mostra o overfit clássico (treino positivo → teste ≈ zero/negativo).

## 8. Diagnósticos-chave

### 8.1 Markov / profundidade de streak (mean-reversion, não momentum)

`P(green | k reds consecutivos antes)` — z vs breakeven 38,89%:

| k reds antes | Horário hit (z) | Anti-horário hit (z) |
|--:|---:|---:|
| 0 | 36.2% (z=-2.55) | 38.6% (z=-0.30) |
| 1 | 37.5% (z=-1.08) | 40.1% (z=+0.89) |
| 2 | 37.0% (z=-1.15) | 38.9% (z=+0.02) |
| 3 | 35.9% (z=-1.44) | 39.7% (z=+0.38) |
| 4 | 31.3% (z=-2.90) | 40.1% (z=+0.44) |

- **Anti-horário:** após um red o acerto sobe para **40.1%** (> breakeven) — há **mean-reversion**. Por terços do tempo: +3,7% / +6,2% / −1,3% ROI (positivo em 2 de 3).
- **Horário:** mesmo após red fica em 37.5% (< breakeven); o baseline é **36.2%** (z=-2.55, significativamente abaixo). **Sem edge.**
- A ideia original "jogar **após green**" é a **pior** (S3): momentum não existe; o sinal é o **inverso** (após red).

### 8.2 Hora do dia (proxy de dealer/turno)
- Sinal **forte no treino** (+11% ROI) mas **não-estacionário**: no teste/walk-forward colapsa (S5 teste ≈ 0; S6 walk-fwd -6.1%/-5.0%). As horas "boas" mudam ao longo dos meses (dealers rodam). Útil como **modulador adaptativo**, não como filtro fixo.

### 8.3 Rotação/deslocamento de centro (C1 variável)
- **Nenhuma variação de C1 ajuda** (S7/S8/S9 todas −EV). Não há **bias espacial**: o melhor centro deslocado captura ~20% ≈ acaso (breakeven p/ somar região = 19,4%); a bola **não** repete setor (`P(perto da anterior)≈19% = acaso`). **Adicionar um 3º região sempre piora** (sobe o breakeven para 58,33%).

## 9. 🏆 Estratégia recomendada (a vencedora honesta)

**Regra assimétrica por sentido (cada um isolado):**

- **♻️ Horário → ABSTER.** O 14# acerta 36.2% (z=-2.55, significativamente abaixo do breakeven). Nenhum gate/centro reverte. **Não apostar é o movimento vencedor** (evita −EV).
- **🔄 Anti-horário → apostar 14# (C2+C3 fixo) SOMENTE APÓS UM RED.** Acerto **40.1%** vs breakeven 38,89% → **ROI +3.0%** (+578u em 1355 apostas full-sample; +3,9% no walk-forward OOS). Mecanismo: mean-reversion (a sequência é levemente anti-correlacionada).
- **Stake:** **flat** (sem gale). O gale **não muda o EV** (provado em `resultados_15_junho.md`); só adiciona ruína. "Melhor hora de gale" = **não galar** — escalar sobre aposta de EV≈0 é puro risco.

### 9.1 Honestidade estatística (obrigatória — é dinheiro real)
- O edge do anti-horário **não é estatisticamente conclusivo**: z = **+0.89** (~81% de confiança unilateral), e o último terço enfraqueceu. É o **melhor disponível**, não uma certeza.
- A roleta tem **vantagem da casa**; sem um **bias físico forte** (que os dados **não** mostram), nenhuma engenharia de timing/centro vira lucro garantido. O C2+C3 hoje rende ≈ acaso.
- **Recomendação de implantação:** rodar a regra (Anti após-red; Horário abster) em **SHADOW/papel** com o guardrail de promoção já existente (Newcombe CI), e **promover a dinheiro real só se o edge persistir** por algumas centenas de jogadas. Nunca galar.

### 9.2 Conexão com o sistema atual
- O sistema já tem o flag inverso `GALE_ONLY_AFTER_GREEN`: o dado pede um **`ONLY_AFTER_RED`** (a implementar) **restrito ao anti-horário**.
- C2+C3 fixo (14#) já está em produção (`SDA_BET_PAIR=c2c3`); falta só o **gate após-red por sentido** + **abstenção no horário**.

---

# 🧬 PARTE III — 30 estratégias de C1 adaptativo (evolução dos paradigmas)

> Continuação: gerar um **C1 variável/adaptativo** que **complemente C2+C3 fixo** (3ª região). 30 paradigmas investigativos, cada um simulado em **walk-forward OOS** (só passado decide; warmup 700). Métrica dupla: **ROI do 21#** (C2+C3+C1) e a **captura marginal do C1** — o quanto a região de 7 do C1 sozinha pega a bola, contra o **breakeven de somar uma região = 19,44%** (acaso ≈ 18,9%).

> Baseline OOS no mesmo período — **Horário 14#: -7.98% ROI** ; **Anti 14#: -1.89% ROI**. Referência da PARTE II: **anti 14# após-red = +3,0%/+3,9%**.

## 11. As 30 estratégias — ranking por ROI(21#), walk-forward

Famílias: **frequência/recência** (hot/cold/EMA, K variável), **transição/lag/offset** (repeat, across, Markov), **últimas forças** (drift de offset, mode, second-hot), **regiões complementares** (disjunta, adjacente, converte-miss), **contexto/assinatura de dealer** (hora, sessão) e **meta-estratégias** (bandit online, ensemble por voto).

### ♻️ HORÁRIO — eval OOS 1495 (baseline 14# -7.98%)

| # | Estratégia C1 | hit 21# | ROI 21# | C1 região % | converte miss % |
|--:|---|--:|--:|--:|--:|
| | E30 Hot K=1000 | 52.8% | **-3.70%** | 21.2% 🟢 | 17.1% |
| | E05 Hot K=500 | 52.6% | **-3.79%** | 20.7% 🟢 | 16.9% |
| | E10 Repeat lag2 | 49.6% | **-3.81%** | 19.4% | 13.8% |
| | E04 Hot K=200 | 52.6% | **-4.06%** | 20.7% 🟢 | 16.9% |
| | E21 AdjExtend better | 53.9% | **-4.24%** | 19.8% 🟢 | 18.1% |
| | E18 Mode K=100 | 48.6% | **-4.63%** | 19.2% | 12.8% |
| | E19 SecondHot K=100 | 52.6% | **-4.69%** | 20.2% 🟢 | 16.9% |
| | E27 CondAfterRed+Hot | 46.7% | **-4.80%** | 20.8% 🟢 | 17.0% |
| | E25 MarkovNext | 51.8% | **-4.87%** | 19.9% 🟢 | 16.0% |
| | E11 Across (+18) | 47.8% | **-5.03%** | 19.5% 🟢 | 12.0% |
| | E01 Hot K=20 | 52.0% | **-5.06%** | 19.2% | 16.2% |
| | E03 Hot K=100 | 51.8% | **-5.39%** | 19.6% 🟢 | 16.0% |
| | E29 Ensemble vote | 51.5% | **-5.78%** | 19.5% 🟢 | 15.7% |
| | E20 Hot disjoint K=100 | 54.9% | **-5.86%** | 19.1% | 19.1% |
| | E14 MissZone last | 48.7% | **-6.09%** | 18.6% | 12.9% |
| | E22 HourHot (turno) | 51.6% | **-6.17%** | 18.6% | 15.8% |
| | E13 Offset -9 | 47.6% | **-6.50%** | 18.7% | 11.8% |
| | E08 Hot EMA | 51.2% | **-6.51%** | 18.7% | 15.4% |
| | E06 Cold K=100 | 51.0% | **-6.61%** | 19.5% 🟢 | 15.2% |
| | E15 MissHot K=150 | 51.0% | **-6.80%** | 18.3% | 15.2% |
| | E26 AntiHot median | 51.8% | **-7.18%** | 19.0% | 16.0% |
| | E02 Hot K=50 | 50.7% | **-7.20%** | 18.5% | 14.9% |
| | E23 SessionHot | 49.4% | **-7.28%** | 18.3% | 14.7% |
| | E12 Offset +9 | 47.1% | **-7.36%** | 17.2% | 11.3% |
| | E16 DriftC2 K=200 | 37.5% | **-7.43%** | 17.5% | 1.7% |
| | E24 SessionRepeat | 46.8% | **-7.86%** | 17.2% | 11.8% |
| | E07 Cold K=500 | 50.9% | **-8.07%** | 18.3% | 15.1% |
| | E09 Repeat lag1 | 47.8% | **-8.07%** | 17.8% | 12.0% |
| | E28 Bandit meta | 49.8% | **-8.25%** | 17.8% | 14.1% |
| | E17 DriftC3 K=200 | 37.0% | **-8.99%** | 17.6% | 1.2% |

### 🔄 ANTI-HORÁRIO — eval OOS 1507 (baseline 14# -1.89%)

| # | Estratégia C1 | hit 21# | ROI 21# | C1 região % | converte miss % |
|--:|---|--:|--:|--:|--:|
| | E10 Repeat lag2 | 52.5% | **+0.85%** ✅ | 21.0% 🟢 | 14.3% |
| | E01 Hot K=20 | 54.6% | **+0.10%** ✅ | 20.0% 🟢 | 16.5% |
| | E22 HourHot (turno) | 54.5% | **+0.06%** ✅ | 19.5% 🟢 | 16.4% |
| | E24 SessionRepeat | 50.4% | **-0.02%** | 19.3% | 13.2% |
| | E12 Offset +9 | 50.0% | **-1.03%** | 20.1% 🟢 | 11.9% |
| | E07 Cold K=500 | 53.7% | **-1.12%** | 19.9% 🟢 | 15.5% |
| | E27 CondAfterRed+Hot | 48.1% | **-1.16%** | 20.5% 🟢 | 16.1% |
| | E16 DriftC2 K=200 | 40.4% | **-1.21%** | 20.2% 🟢 | 2.3% |
| | E02 Hot K=50 | 53.8% | **-1.28%** | 19.7% 🟢 | 15.7% |
| | E14 MissZone last | 51.4% | **-1.30%** | 20.2% 🟢 | 13.2% |
| | E09 Repeat lag1 | 51.3% | **-1.32%** | 19.8% 🟢 | 13.1% |
| | E08 Hot EMA | 53.8% | **-1.48%** | 19.3% | 15.7% |
| | E04 Hot K=200 | 53.7% | **-1.55%** | 19.0% | 15.5% |
| | E28 Bandit meta | 52.6% | **-1.61%** | 19.3% | 14.5% |
| | E23 SessionHot | 52.4% | **-1.67%** | 19.0% | 15.3% |
| | E19 SecondHot K=100 | 54.1% | **-1.97%** | 18.5% | 16.0% |
| | E20 Hot disjoint K=100 | 57.1% | **-2.06%** | 19.0% | 19.0% |
| | E06 Cold K=100 | 53.4% | **-2.26%** | 19.2% | 15.3% |
| | E05 Hot K=500 | 53.6% | **-2.30%** | 18.1% | 15.5% |
| | E21 AdjExtend better | 55.1% | **-2.31%** | 19.0% | 16.9% |
| | E17 DriftC3 K=200 | 39.6% | **-2.41%** | 18.0% | 1.5% |
| | E03 Hot K=100 | 53.3% | **-2.59%** | 19.0% | 15.1% |
| | E18 Mode K=100 | 49.6% | **-2.64%** | 19.6% 🟢 | 11.4% |
| | E26 AntiHot median | 54.1% | **-2.68%** | 18.2% | 16.0% |
| | E13 Offset -9 | 49.4% | **-2.72%** | 18.5% | 11.2% |
| | E30 Hot K=1000 | 53.5% | **-2.77%** | 18.2% | 15.4% |
| | E29 Ensemble vote | 53.0% | **-3.03%** | 18.6% | 14.9% |
| | E25 MarkovNext | 52.9% | **-3.36%** | 18.9% | 14.7% |
| | E15 MissHot K=150 | 52.2% | **-4.50%** | 17.6% | 14.1% |
| | E11 Across (+18) | 48.2% | **-5.03%** | 16.4% | 10.0% |

## 12. Leitura dos resultados

- **Horário:** **nenhuma** das 30 fica positiva. A melhor (Hot K=1000) só **dilui** a perda (−3,7% vs −8,0% do 14#). Confirma: horário não tem edge.
- **Anti-horário:** **3 ficam marginalmente positivas** — **E10 Repeat-lag2 (+0,85%)**, E01 Hot-K20 (+0,10%), E22 HourHot (+0,06%). Só nelas a **região do C1 passa de 19,44%** (lag2 = **21,0%**).
- **A captura do C1 quase nunca bate o breakeven** (maioria 18–19% ≈ acaso). Drift de offset (E16/E17) **quebra** (converte só ~2% — desloca o centro para fora). **Não há bias espacial forte** — confirma a PARTE II.
- **Adicionar C1 sobe o breakeven** (14#→38,9% para 21#→58,3%); por isso mesmo o melhor 21#+C1 (+0,85%) **perde** para o **14# após-red (+3,0%)** da PARTE II em base risco-ajustado.

## 13. 🔎 Descoberta: Repeat-lag2 (revisita do setor de 2 jogadas atrás)

Único C1 com sinal **real (fraco)**: colocar o C1 na região da **bola de 2 spins atrás**. No anti-horário a região do C1 captura **21,04%** (n=1507) vs breakeven 19,44% → **z = +1,56** (~94% confiança unilateral). Mecanismo plausível: ritmo/assinatura física do dealer com período ~2. **Não** é o lag-1 (esse é acaso, 19,8%).

## 14. Síntese — C1 adaptativo + gate após-red (walk-forward)

Cruzando o melhor C1 com o edge de timing da PARTE II:

| Estratégia (gate após-RED) | Horário hit/ROI/P&L | Anti hit/ROI/P&L |
|---|---:|---:|
| 14# (só C2+C3) | 36,7% / −5,71% / −768u | **40,4% / +3,85% / +502u** |
| 21# + C1 Hot-K20 | 52,9% / −3,44% / −652u | 55,0% / +0,99% / +180u |
| 21# + C1 Lag2 | 50,9% / **−0,97%** / −172u | 53,6% / +3,10% / **+540u** |

- **Anti-horário:** o **14# após-red (+3,85% ROI)** é o **mais eficiente** (melhor por unidade de risco). Somar **C1=lag2** entrega **+540u** (mais unidades absolutas, mas ROI +3,1% por apostar 21u). Hot-K20 **piora**.
- **Horário:** 21#+lag2 após-red chega a **−0,97%** (quase breakeven) — o C1=lag2 + timing **quase zera** a perda, mas ainda negativo → **abster** continua melhor.

## 15. 🧭 Evolução dos paradigmas (síntese final)

| Paradigma | Regra | Anti-horário | Horário |
|--:|---|---:|---:|
| **P1** (produção hoje) | C2+C3 14# todas | ≈ neutro (−1,9%) | −EV (−8,0%) |
| **P2** (PARTE II) | + gate **após-RED** | **+3,85%** ✅ | −5,7% |
| **P3** (PARTE III) | + **C1 adaptativo** (21#) | +0,85% (lag2) | −3,7% (hot1000) |
| **P2⊕P3** | após-red **+ C1=lag2** | +3,1% / **+540u** | −0,97% (quase 0) |

**Direção evolutiva comprovada:** o ganho vem do **timing (após-red, mean-reversion)**, não da geometria do C1. O **C1 adaptativo só agrega à margem** (lag2), e **apenas combinado** com o gate de timing; sozinho não vira o jogo. A geometria (hot/cold/drift/contexto) é ≈ acaso.

## 16. 🏆 Recomendação final evoluída

1. **♻️ Horário → ABSTER** (nenhum dos ~40 testes ficou positivo; melhor caso quase-zero).
2. **🔄 Anti-horário → 14# C2+C3 fixo APÓS-RED** como núcleo (+3,85% ROI, melhor risco-ajustado).
3. **(opcional, maximizar unidades)** No anti, após-red, **somar C1 = região da bola de 2 spins atrás** (lag2) → +540u (vs +502u), aceitando +50% de stake. Só faz sentido se o objetivo for unidades absolutas, não ROI.
4. **Stake flat, sem gale.** Gale não muda EV; o melhor "gale" é **não galar**.
5. **Implantar em SHADOW** (Newcombe CI já existe), promover a real só se o edge (z≈+1,5) **persistir** algumas centenas de jogadas. É edge **fraco e não conclusivo** — é dinheiro real.

> **Veredito honesto:** das 40+ estratégias testadas (PARTE II + III), a **única fonte de edge real é o timing após-red no anti-horário**; o C1 adaptativo (lag2) é um **refinamento marginal**. Não há geometria/contexto de C1 que torne o 21# robustamente lucrativo. A evolução correta dos paradigmas é **menos geometria, mais timing condicional + abstenção no sentido sem sinal**.

---

# 🎯 PARTE IV — Como definir o C1 (resposta de design)

> Contexto dado pelo operador: **C2 = cluster mais denso das últimas 4** (força quente/espacial); **C3 = região mais fria das últimas 5** (gap frio/espacial). Tudo **isolado por sentido**. Pergunta: **como definir o C1** na evolução proposta?

## 18. Princípio: C1 = complemento TEMPORAL (não mais um espacial)
C2 e C3 já cobrem o eixo **espacial-frequência** (quente e frio) de janela curta. Repetir essa lógica no C1 (mais um hot/cold) é **redundante e deu ≈ acaso** nas 30 estratégias (PARTE III). O que **falta** capturar é o eixo **temporal/sequencial** — o ritmo da roda. Por isso:

> **C1 = a região (±3 na roda) da bola de ~2 jogadas atrás do MESMO sentido (revisita lag-2).**

Foi a **única família que bateu o acaso** (PARTE III, centros de produção: C1 capta 21,0% vs breakeven 19,44%, z=+1,56; +540u no anti após-red). É ortogonal a C2 (denso) e C3 (frio).

## 19. Porém: C1 deve ser CONDICIONAL, não um 3º centro fixo
Somar qualquer C1 sobe o breakeven (14#→38,9% para 21#→58,3%) e, na média, **dilui** o EV. Logo, na evolução proposta o C1 é um **slot condicional por sentido**:

| Sentido | Gatilho | C1 | Aposta |
|---|---|---|---|
| 🔄 Anti-horário | última foi **RED** | **lag-2** | 21# (C2+C3+C1) |
| 🔄 Anti-horário | última foi green | ∅ | 14# (C2+C3) |
| ♻️ Horário | — | ∅ | **abster** (sem edge) |

- O **núcleo do edge é o timing** (após-red, anti-horário): 14# após-red = **+3,85% ROI**. O C1=lag-2 é um **acréscimo marginal** que maximiza unidades absolutas (+540u vs +502u), ao custo de +50% de stake.
- **Stake flat, gale isolado por sentido com TETO 1** (sem escalonar — gale não muda EV).

## 20. Achado importante (sobre C2/C3)
Recompondo C2/C3 pela **definição literal** (denso-4 / frio-5) sobre as bolas cruas, o 14# após-red cai a **−2,76%** (anti) — **pior** que com os `sda_centers` de produção (+3,85%). Ou seja, os **C2/C3 reais (modelo de força do SDA17 + offsets adaptativos) são melhores** que a descrição verbal simplificada. **Recomendação: manter os C2/C3 de produção** como base; o C1=lag-2 entra por cima, condicional.

## 21. Definição final do C1 (para implementar e validar em shadow)
```
Por sentido (isolado):
  C2 = sda_center denso (produção)   # quente, últimas ~4
  C3 = sda_center frio (produção)    # frio, últimas ~5
  se sentido == HORARIO: ABSTER
  senao (ANTI-HORARIO):
     se ultima_jogada == RED:
        C1 = regiao(bola[t-2])        # revisita lag-2 (unico sinal real, fraco)
        aposta = C2 ∪ C3 ∪ C1 (21#)
     senao:
        aposta = C2 ∪ C3 (14#)        # sem C1
  stake = flat (gale teto 1, isolado por sentido)
```
> **Honestidade:** o edge (após-red) é **fraco e não conclusivo** (z≈+0,9 no ROI; z≈+1,5 na captura do C1) e **sensível à base de C2/C3**. Implementar em **SHADOW** com o guardrail de promoção (Newcombe CI) e promover a dinheiro real **só se persistir** algumas centenas de jogadas por sentido. O C1=lag-2 é refinamento, não a fonte do ganho — o ganho é o **timing**.

---

# 🏗️ PARTE V — Framework de simulação (metodologia + plano de sprints)

> Esta parte **declara como** a evolução será desenvolvida, ANTES de executar (conforme pedido). Define o modelo de força, o sistema de pontuação por região menos-visitada, as definições de C2/C3/CX, as duas geometrias (21 vs 17 números) e o plano por sprints. As PARTES VI (auditoria) e VII (execução) seguem esta especificação.

## 22. Fundação de dados (validada)
- **Fonte:** `decisions.db` de produção. **6.032 jogadas resolvidas** (`result_actual` registrado), 100% consistência `result_actual(t)==spin_number(t+1)`, todos os números em 0..36.
- **Teste de uniformidade:** χ²=33,3 (gl=36; crítico≈51 a 5%) → a roda é **estatisticamente uniforme**. **Suposição-nula honesta:** não há viés físico forte; qualquer edge será pequeno/residual. O **lever real** candidato é a **geometria de menor breakeven** (17# em vez de 21#), não 'adivinhar' o número.
- **Janela de avaliação:** as **últimas 400 jogadas de cada sentido** (id ~6666–7541). Todo o histórico anterior é **warmup** (cálculos rolantes só usam o passado — walk-forward).
- **Isolamento por sentido:** horário e anti-horário são spins físicos alternados; cada sentido é avaliado **isolado**.

## 23. Reconstrução do 'momento' de cada jogada
Para cada spin t reconstruímos o estado causal (só passado):

### 23.1 Força aplicada (eixo por SENTIDO)
- **Força** `F(t) = sdist(res_{t-1}^{mesmo sentido}, res_t)` = distância **circular assinada** (−18..+18) entre resultados consecutivos do **mesmo sentido**. É o proxy da força do crupiê (quanto a bola 'andou' na roda).
- **Variação de força** `ΔF(t)=F(t)-F(t-1)`. Estratégias de força extrapolam o próximo centro = `res_último + força_prevista` (média/mediana/tendência das últimas K forças do sentido).
- **Filosofia:** *assinatura física do crupiê* — se a força tem inércia/autocorrelação, o setor de queda **deriva de forma previsível**. Hipótese determinística vs aleatória.

### 23.2 Pontuação por região menos-visitada (eixo por POSIÇÃO, AMBOS os sentidos)
- **Distância circular** `d(a,b)=min(|Δpos|, 37-|Δpos|) ∈ [0,18]`. Resolve a preocupação do 'meio da roda': o máximo é **18** (casa oposta), bem-definido e simétrico — por isso usamos a geodésica `min(Δ,37−Δ)`, não a distância linear.
- **Score por posição p:** a cada spin de resultado r, `score[p] += (d(p,r) − 9,24)` com **decaimento EMA** (α). A constante 9,24 é a **distância média sob uniforme** (centro do score). **Bola longe de p ⇒ score positivo** (região sub-visitada/'fria'); **perto ⇒ negativo** (quente). Acumulado e decaído = mapa de **probabilidade acumulada por região**.
- **C3 e as CX de região usam AMBOS os sentidos** (probabilidade é por posição da bola, independe da força/sentido). Só as CX de **força** são por-sentido.
- **Filosofia:** *maturidade espacial das chances* — setores sub-visitados 'devem' reverter para cima. Hipótese de reversão à média espacial (vs falácia do apostador).

## 24. Definição dos centros e geometrias
| Centro | Definição | Janela | Eixo | Tamanho 21# | Tamanho 17# |
|---|---|---|---|:--:|:--:|
| **C2** | cluster **mais denso** | últimas **4** do **sentido** | posição+força | 7 (±3) | **7 (±3) fixo** |
| **C3** | região **mais fria** | últimas **5** de **ambos** | posição | 7 (±3) | **5 (±2)** |
| **CX** | candidato (C4..C12) | variável | posição **ou** força | 7 (±3) | **5 (±2)** |

- **Geometria atual (21#):** `C2(7) ∪ C3(7) ∪ CX(7)` — o que roda hoje.
- **Geometria proposta (17#):** `C2(7) ∪ C3(5) ∪ CX(5)` — C2 segue 7; C3 e CX encolhem para 5 (1 central + 2 vizinhos de cada lado).
- **Cobertura real** = **união** (pode ser < nominal por sobreposição); o P&L usa o N real.

### 24.1 Matemática da aposta e breakeven
| Geometria | Stake | Ganho líquido (green) | Perda (red) | **Breakeven** |
|---|:--:|:--:|:--:|:--:|
| 21 números | 21u | +15u | −21u | **58,33%** |
| **17 números** | 17u | **+19u** | −17u | **47,22%** |
| 14 números (ref.) | 14u | +22u | −14u | 38,89% |

> **Hipótese central:** o 17# tem breakeven **11 pontos menor** que o 21#. Se o hit cair pouco ao tirar 4 números (de C3/CX, as regiões mais fracas), o **17# pode virar positivo** onde o 21# é negativo. Esse é o teste-chave.

## 25. Catálogo de CX candidatas (C4..C12+, ≥10)
Cada CX é uma **suposição genérica pré-definida** que complementa C2 (quente) e C3 (frio):

**Família REGIÃO (posição, ambos os sentidos):**
- `C4 ColdScore-EMA` — argmax do score acumulado (região menos-visitada contínua).
- `C5 GapMax` — região com **maior tempo desde a última visita** (±3) ('número atrasado').
- `C6 ColdCount-Long` — mais fria por contagem nas últimas **24** de ambos.
- `C7 DensestBoth` — mais **quente** nas últimas K de ambos (persistência espacial).
- `C8 MarkovNext` — posição mais provável dado o último resultado (transição).
**Família FORÇA (por sentido):**
- `C9 ForceMean-K` — último + **média** das últimas K forças do sentido.
- `C10 ForceMedian-K` — idem com **mediana** (robusta a outliers).
- `C11 ForceTrend` — último + força + **ΔF** (extrapola aceleração).
- `C12 ForceLast` — último + **última força** (persistência ingênua).
**Família HÍBRIDA/TEMPORAL:**
- `C13 Repeat-lag2` — região do resultado de **2 spins atrás** do sentido (único sinal real achado na PARTE III).
- `C14 SecondDensest` — 2º cluster mais denso do sentido (após C2).
- `C15 Across` — setor **oposto** a C2 (C2+18).

## 26. Protocolo de validação (anti-overfit)
- **Walk-forward** estrito: no spin t só o passado decide (warmup ≥ 700).
- **Avaliação:** últimas **400/sentido**, **isolado**.
- **Métricas:** hit%, **ROI = P&L/total apostado**, vs breakeven da geometria, **z** (significância vs breakeven), e estabilidade por terços.
- **Comparação obrigatória:** para cada CX, medir **21# (7+7+7)** vs **17# (7+5+5)** — a premissa é que a vencedora final é uma das duas.

## 27. Plano por SPRINTS
| Sprint | Entrega |
|--:|---|
| **S1** | Fundação de dados + validação (χ², consistência, timeline global) — **feito** (§22) |
| **S2** | Reconstrução do momento: vetor de forças por sentido + mapa de score por posição |
| **S3** | Biblioteca C2/C3/CX (15 candidatas) + 2 geometrias (21 e 17) |
| **S4** | Rodar 15 CX × 2 geometrias × 2 sentidos, walk-forward 400 — ranking |
| **S5** | Melhor CX → refino 5# + **combinação das 7 melhores** + gate de timing (após-red) |
| **S6** | Honestidade (z, terços, vs uniforme) + **recomendação 17 vs 21** |

---

# 🔍 PARTE VI — Auditoria de bugs da metodologia (pré-execução)

> Antes de rodar, audito a especificação da PARTE V à procura de erros que **invalidariam** os resultados (é dinheiro real). Cada item tem **risco** e **mitigação** que será aplicada no código da PARTE VII.

## 28. Bugs/riscos identificados e mitigações

| # | Bug/risco | Impacto | Mitigação aplicada |
|--:|---|---|---|
| B1 | **Look-ahead** no mapa de score / contagens | superestima edge (vê o futuro) | Estado atualizado **após** apostar em t; em t só entra `res[<t]`. Warmup ≥700. |
| B2 | **Força no espaço errado** (somar força ao NÚMERO em vez da POSIÇÃO da roda) | centro previsto absurdo | Toda força opera em `POS` (índice na `WHEEL_SEQUENCE`), `centro=WHEEL[(POS[last]+F)%37]`. |
| B3 | **Wrap circular** (distância linear no 'meio da roda') | distâncias erradas perto de 18 | `d=min(|Δ|,37−|Δ|)∈[0,18]`; assinada via diferença de POS mod 37 remapeada a −18..+18. |
| B4 | **C3 'frio de 5' é quase aleatório** (5 pts em 37 posições ⇒ muitos zeros) | C3 instável/arbitrário | Tie-break determinístico: menor contagem em ±janela → **maior gap** desde última visita → **mais distante de C2**. Score-EMA como medida principal de frieza. |
| B5 | **Empates** em argmax/argmin (hot/cold) | não-reprodutível | Ordem fixa da `WHEEL_SEQUENCE` + tie-breaks explícitos e documentados. |
| B6 | **Cobertura real ≠ nominal** (sobreposição CX∩C2∩C3) | comparar 17 vs 21 fica injusto | P&L sempre no **N real** (união); reporto **N médio** por geometria. ROI=P&L/apostado normaliza. |
| B7 | **Breakeven misturado** (comparar hit de 17 e 21 no mesmo limiar) | conclusão errada | Cada geometria vs **seu** breakeven (21→58,33%; 17→47,22%); ROI é a métrica primária comparável. |
| B8 | **Sinal/sentido da força** inconsistente | extrapolação aponta ao contrário | `sdist` única na `WHEEL_SEQUENCE` fixa; sentido (H/A) **não** inverte a roda, só seleciona a subsequência. |
| B9 | **Multiplicidade de testes** (15×2×2=60 combos) | falso-positivo por acaso | Exijo **z** + estabilidade por terços; positivos são **hipóteses p/ shadow**, não prova. |
| B10 | **Overfit de hiperparâmetros** (α, K) | edge ilusório | α e K **fixados a priori** (α=0,05; K∈{8,24}); **sem** grid-search na janela de avaliação. |
| B11 | **Janela 400 ≈ 4 dias** (1 regime/dealer) | não generaliza | Reporto também robustez em janela maior (1200/sentido) e por terços; limitação declarada. |
| B12 | **Eixo errado** (C3/região por-sentido em vez de ambos) | mistura conceitual | C3 e CX de região leem a **timeline global**; só CX de força leem a subsequência do sentido. |
| B13 | **`result_actual` nulo** (última jogada não resolvida) | NaN/viés de borda | Excluídas as não-resolvidas (6.032 válidas); avaliação só em registradas. |

## 29. Decisões de design derivadas da auditoria
- **C3 será definido com tie-break robusto** (B4); ainda assim, trato C3-de-5 como **estrutural** (o operador definiu) e reporto sua fragilidade.
- **CX pode sobrepor** C2/C3 (natural); **não** forço disjunção (mudaria a hipótese) — mas reporto N real (B6).
- **Honestidade primeiro:** dado o χ² uniforme (§22), a expectativa é edge ≈ 0 na geometria; o **único lever estrutural** é o **breakeven menor do 17#**. Se nenhuma CX vira positivo, a conclusão honesta será 'manter 14# após-red (PARTE II) ou 17# se reduzir perda'.

> Auditoria concluída: **0 bugs bloqueantes**; 13 riscos endereçados por mitigação. Segue execução (PARTE VII) sob estas regras.

---

# 🚀 PARTE VII — Execução da evolução e estratégias vencedoras

> Execução do framework (PARTES V/VI) nas **últimas 400/sentido**, walk-forward, isolado. 15 CX × 2 geometrias × 2 sentidos + síntese com gate de timing. Todos os números abaixo são reproduzíveis do `decisions.db` validado (§22).

## 30. Sprint S4 — ranking das 15 CX (achados estruturais)

**Achado #1 — a geometria 17# bate o 21# (lever de breakeven):** encolher C3 e CX de ±3 (7) para ±2 (5) corta os 4 números mais fracos; o breakeven cai de 58,3% para 47,2% e o **ROI melhora sistematicamente** no anti-horário. Ex. (ANTI, melhor CX): 21# +0,10% → **17# +2,55%**.

**Achado #2 — CX de FORÇA > CX de REGIÃO:** as candidatas baseadas em **força** (último resultado + força aplicada) lideram; as de **região** (frio/quente/score/gap/Markov) ficam ≈ acaso. Confirma a roda uniforme (§22): não há setor 'frio que volta', mas há leve **persistência balística** (assinatura do crupiê).

**Achado #3 — C2/C3 recomputados pela definição verbal são fracos:** o C3 = 'mais frio das últimas 5 de ambos' é quase aleatório (5 pontos em 37 posições — risco B4). O núcleo C2+C3 verbal rende −13% (vs −1,9% com os `sda_centers` de produção, PARTE I/IV). **Conclusão: usar os centros de produção como base** e o CX por cima.

| CX (família) | ANTI 21# ROI | ANTI 17# ROI | melhor |
|---|--:|--:|:--:|
| ForceLast (força) | +0,10% | **+2,55%** | 17# |
| ForceTrend (força) | −8,32% | −5,85% | 17# |
| RepeatLag2 (temporal) | −6,69% | −10,80% | 21# |
| ColdScoreEMA (região) | −7,58% | −8,09% | — |
| MarkovNext (região) | −13,72% | −13,39% | — |
| Baseline C2+C3 (sem CX) | −13,57% | −12,47% | — |

## 31. Sprint S5 — as 7 MELHORES estratégias combinadas

Cruzando **sentido × geometria × CX × gate(após-red)** — ranking por ROI walk-forward (400/sentido):

| # | Sentido | CX (3ª região) | Geo | Gate | Hit | **ROI** | N real | Apostas | Terços |
|--:|---|---|:--:|:--:|--:|--:|--:|--:|:--:|
| 🥇 | ANTI | **ForceLast** | **17#** | **após-red** | 44,2% | **+4,60%** | 15,2 | 267 | **+++** |
| 🥈 | ANTI | ForceLast | 17# | todas | 42,8% | **+2,55%** | 15,0 | 400 | ++− |
| 🥉 | ANTI | ForceLast | 21# | após-red | 50,6% | +0,77% | 18,1 | 267 | ++− |
| 4 | ANTI | ForceLast | 21# | todas | 49,5% | +0,10% | 17,8 | 400 | +−− |
| 5 | ANTI | RepeatLag2 | 21# | após-red | 50,2% | −2,09% | 18,5 | 267 | ++− |
| 6 | HOR | DensestBoth | 21# | após-red | 48,9% | −2,62% | 18,1 | 264 | −−− |
| 7 | ANTI | RepeatLag2 | 17# | após-red | 40,8% | −3,09% | 15,2 | 267 | ++− |

> **Os 4 primeiros são todos `ANTI + ForceLast`**, melhorando **monotonicamente** com os dois levers (17# e gate após-red): +0,10 → +0,77 → +2,55 → **+4,60%**. Os levers **empilham** de forma previsível — sinal de estrutura real, não acaso isolado. Só o #1 é positivo nos **3 terços**.

## 32. A vencedora — análise profunda e honestidade estatística

**🏆 ANTI-horário · 17 números · CX=ForceLast · gate após-red**
- **Composição:** C2(7, denso-4 do sentido) ∪ C3(5, frio-5 ambos) ∪ **CX(5, =último resultado + última força)**. Aposta só quando a jogada anterior do sentido foi **red**.
- **Robustez (estável em todas as janelas):**

| Janela (anti) | Hit | Breakeven real | ROI | P&L/aposta |
|--:|--:|--:|--:|--:|
| últimas 400 | 44,2% | 42,2% | **+4,60%** | +0,700u |
| últimas 800 | 44,2% | 42,2% | **+4,89%** | +0,73u |
| últimas 1200 | 44,1% | 42,1% | **+4,87%** | +0,738u |

- **Significância (honesta):** t = **+0,65** (400) a **+1,14** (1200); p uni-lateral ≈ 0,13. **Positivo e estável, mas NÃO estatisticamente conclusivo** (p>0,05). Coerente com a roda uniforme (§22): é o **melhor sinal disponível**, não uma certeza.
- **Por que funciona (3 levers ortogonais):** (1) **sentido anti** = único com leve viés; (2) **17#** = breakeven menor (corta os 4 piores números); (3) **ForceLast** = persistência balística da força do crupiê; (4) **após-red** = timing de reversão (PARTE II).

## 33. 🧭 Evolução dos paradigmas (por etapa)

| Etapa | Paradigma | Regra | Anti ROI | Por que melhora |
|--:|---|---|--:|---|
| P1 | Cobertura fixa | C1+C2+C3 21# todas | −13,6%* | — (base) |
| P2 | Timing | + gate **após-red** | (PARTE II +3,0%) | mean-reversion: green vem após red |
| P3 | Geometria | **21# → 17#** | +2,6% | breakeven 58→47%; corta 4 piores nº |
| P4 | 3ª região por FORÇA | CX = ForceLast | +2,6% | assinatura balística > região fria (acaso) |
| P5 | P3⊕P4 | 17# + ForceLast | +2,55% | levers ortogonais somam |
| P6 | **P2⊕P3⊕P4** | 17# + ForceLast + após-red | **+4,60%** | os 3 levers empilham (3 terços +) |
| P7 | Base de centros | usar `sda_centers` de produção | (esperado >+4,6%) | C3-verbal é fraco; centros de produção são melhores (PARTE IV) |

> *P1 aqui usa C2/C3 verbais (fracos). Com `sda_centers` de produção o piso já é melhor (PARTE I/IV).

## 34. Suposições filosóficas — veredito dos dados
- **Maturidade espacial ('região menos-visitada volta'):** ❌ **refutada** — score/frio/gap/Markov ≈ acaso; a roda é uniforme (χ²=33,3). Não existe número 'atrasado'.
- **Assinatura balística (força tem inércia):** ⚠️ **fraca mas presente** — `ForceLast` (último + última força) é a única família que agrega; sugere leve autocorrelação do gesto do crupiê. Não conclusiva (t≈1).
- **Reversão temporal (após-red):** ⚠️ **fraca e direcional** — só no anti-horário; é o lever de timing.
- **Geometria (menor breakeven):** ✅ **estrutural e robusta** — independe de 'adivinhar'; 17# domina 21# no anti em todas as janelas. É o ganho mais confiável.

## 35. 🎯 Recomendação final (17 vs 21)
1. **Adotar a geometria 17# (C2-7 + C3-5 + CX-5)** no anti-horário — breakeven menor é o ganho mais robusto.
2. **CX = ForceLast** (último resultado + última força do sentido), **gate após-red**, no anti. Núcleo positivo (+4,6–4,9% ROI, estável).
3. **Horário → abster** (nenhuma combinação positiva).
4. **Base de centros:** usar os **`sda_centers` de produção** (C2/C3 do SDA17) — superiores aos verbais (PARTE IV); o CX=ForceLast entra como 3ª região de 5.
5. **Stake flat, sem gale.** Gale não muda EV.
6. **Implantar em SHADOW** (guardrail Newcombe já existe) e promover a dinheiro real **só se o +0,7u/aposta persistir** algumas centenas de jogadas — o edge é **real-ish mas não significativo** (p≈0,13). É dinheiro real.

> **Síntese de 60+ estratégias (PARTES II–VII):** o caminho vencedor **não é geometria de adivinhação**, e sim **empilhar levers fracos-mas-ortogonais** — *sentido certo (anti) + breakeven menor (17#) + força balística (ForceLast) + timing (após-red)*. Resultado: de −13% (cobertura fixa ingênua) para **+4,6% ROI** estável. Honestamente fraco em significância, mas é a **evolução de paradigma comprovadamente melhor** disponível nos dados.

---

# 🧠 PARTE VIII — 10 sprints evolutivos (investigar → evoluir → documentar)

> Estrategista evolutivo, múltiplos olhares. Parti do que funcionou (força + 17# + anti + após-red) e abri frentes livres, **agora com base nos `sda_centers` de PRODUÇÃO** (C2/C3 reais do SDA17, superiores aos verbais). Cada sprint: backtest real walk-forward, decisão, evolução. Métrica honesta: ROI=P&L/apostado, t-stat do P&L/aposta, estabilidade por terços e por janela (400/800/1200).

| Sprint | Hipótese investigada | Resultado (ANTI) | Decisão evolutiva |
|--:|---|---|---|
| **S1** | Base produção vs verbal | 17# após-red: prod **+4,9%** ≈ verbal +4,8%; prod melhora o 21# (+3,4%) | adotar **base de produção** |
| **S2** | Qual modelo de força | **ForceLast** (último+força, 1 passo) bate mean/median/trend/ewma; invariante a K | travar **ForceLast** (velocidade constante) |
| **S3** | Qual gate de timing | **após-red** > red2 > all; **green é péssimo** (momentum errado) | manter **após-red** |
| **S4** | Tamanho do CX / disjunção | C3-5+CX-5 (17#) **+4,9%**; C3-5+CX-7 (19#) +5,0%; disjunção indiferente | manter **17#** (premissa); 19# como insight |
| **S5** | Ensemble (bandit de forças) | +0,1/+1,3% — **pior** que ForceLast puro | **descartar** bandit |
| **S6** | 🔥 **Confiança** (ForceLast≈ForceMean) | **+14,1%/+10,7%** (hit 50%, t até 1,3) — salto | **adotar filtro de confiança** |
| **S7** | Reset por troca de dealer/sessão | −7,3/−1,4% — **pior** (força precisa de continuidade) | **descartar** reset; força é cross-sessão |
| **S8** | Limiar de confiança / dropar C3 | conf=3 ótimo; **dropar C3 → +22,5%** (concentra stake) | conf=3; C3-drop como **insight** (premissa mantém C3) |
| **S9** | Robustez (janelas/terços) | 17# conf+red: +14(400)/**+15,6(800, p=0,066)**/+10,7(1200)/+4,7(2000) | edge **recente e robusto**, decai em janela longa |
| **S10** | Consolidação das finais | ForceLast **puro ≈ 0%**; o edge vem de **conf+red** | montar as **7 melhores** (§37) |

## 36. Arco da evolução (o que cada lever acrescenta)
- **Lever 0 — sentido:** só **ANTI** tem viés; **horário** é fortemente −EV (t=−3,1; −24% com confiança) → **abster**.
- **Lever 1 — geometria 17#:** breakeven 47% < 58% do 21#; corta os 4 piores números. Ganho **estrutural**.
- **Lever 2 — CX por FORÇA (ForceLast):** 3ª região = último resultado deslocado pela última força (extrapolação balística de velocidade constante). Bate qualquer região fria/quente (≈ acaso).
- **Lever 3 — gate após-red:** timing de reversão (a sequência anti é levemente anticorrelacionada).
- **Lever 4 — 🔑 CONFIANÇA:** apostar só quando **ForceLast ≈ ForceMean** (dcirc≤3) — i.e., quando o **ritmo da força está estável**. É o salto: hit 43%→50%, ROI +5%→+14%. Filosofia: o crupiê tem **janelas de cadência estável**; só nelas a balística é previsível.

> **Insight não-restrito (fora da premissa):** em spots de alta confiança, **dropar C3** e apostar só C2+CX (≈11–13 números) rende **+22,5% ROI** — concentrar stake nas 2 regiões de sinal. Fica como evolução futura (a premissa atual mantém C3).

---

# 🏆 PARTE IX — As 7 melhores estratégias FINAIS (complementares a C2 e C3)

> Após 10 sprints, as 7 melhores formas de definir a **3ª região (CX)** que complementa **C2 (denso) + C3 (frio)** de produção, nos dois âmbitos **21# (7+7+7)** e **17# (7+5+5)**. Todas no **anti-horário** (horário = abster). **CX = ForceLast** em todas (último resultado + última força — extrapolação balística); o que muda é o **gate** (após-red e/ou confiança).

## 37. Ranking final (ANTI; ROI por janela = P&L/apostado)

| # | Estratégia (CX=ForceLast) | Geo | Gate | ROI 400 | ROI 800 | ROI 1200 | apostas* | t (800) | terços |
|--:|---|:--:|---|--:|--:|--:|--:|--:|:--:|
| 🥇 | **conf≤3 + após-red** | **17#** | confiança+timing | +14,1% | **+15,6%** | +10,7% | 62–189 | **+1,5** | +++ |
| 🥈 | conf≤3 | 17# | confiança | +13,9% | +14,8% | +7,4% | 76–265 | +1,6 | -++ |
| 🥉 | conf≤3 | 21# | confiança | +12,0% | +11,5% | +4,0% | 76–265 | +1,6 | — |
| 4 | conf≤4 + após-red | 17# | confiança+timing | +11,0% | +11,4% | +7,7% | 78–243 | +1,3 | +-+ |
| 5 | conf≤4 | 21# | confiança | +10,7% | +9,4% | +3,0% | 103–346 | +1,5 | +++ |
| 6 | após-red (volume) | 17# | timing | +5,2% | +2,1% | +2,4% | 283–812 | +0,4 | +-+ |
| 7 | após-red (volume) | 21# | timing | +3,8% | +0,2% | +1,6% | 262–755 | +0,1 | +-+ |

> *Faixa de apostas conforme a janela (400→1200). **ForceLast PURO (sem gate) ≈ 0%** — o edge vem dos gates, não da cobertura.

## 38. Por que cada uma vale a pena
- **#1–#2 (17# confiança):** o **melhor risco-retorno**. Apostam **só quando a força está estável** (ForceLast≈ForceMean) — janelas de cadência previsível do crupiê. ROI **+10 a +16%** estável em 400–1200, **positivo nos 3 terços** (#1), t chegando a 1,5 (p≈0,07). Poucas apostas (seletivo) = menos exposição.
- **#3 (21# confiança):** mesma lógica na geometria atual (21#) — para quem **não quer mudar a cobertura**, só adicionar o filtro de confiança ao C1 já entrega +11–12% nas janelas curtas.
- **#4–#5 (conf≤4):** afrouxam o limiar → **mais apostas** (~2×) com ROI ainda **+9 a +11%**. Bom equilíbrio volume×retorno.
- **#6–#7 (só após-red):** **alto volume** (260–810 apostas), ROI menor (+2 a +5%) mas mais apostas = mais unidades absolutas. Para quem quer **frequência**.

## 39. A vencedora das vencedoras
**🏆 ANTI · 17 números · CX=ForceLast · gate confiança(≤3)+após-red**
- **Composição:** C2(7, denso prod) ∪ C3(5, frio prod) ∪ **CX(5)=ForceLast**. Aposta **só** quando: (a) jogada anterior do sentido foi **red** E (b) **ForceLast e ForceMean concordam** (≤3 casas).
- **Desempenho:** ROI **+14 a +16%** (400–800), **+10,7%** (1200); hit ~50% sobre ~15 números (breakeven real ~42%). Positivo nos 3 terços.
- **Por que funciona (5 levers ortogonais empilhados):** sentido anti + 17# (breakeven menor) + ForceLast (balística) + após-red (reversão) + **confiança (cadência estável)**. Cada lever isolado é fraco; **juntos** somam de −13% (ingênuo) a **+14%**.

## 40. ⚠️ Honestidade estatística (é dinheiro real)
- **Não atinge significância formal:** o melhor t≈1,5 (p≈0,07) — **abaixo** de p<0,05. Com a roda **uniforme** (χ²=33,3), o nulo é 'sem edge'.
- **Seletividade:** o filtro de confiança reduz para **62–265 apostas** (de 400–1200) — amostra menor, mais variância; e há **multiplicidade de testes** (muitas configs).
- **Recência:** o edge é **mais forte em dados recentes** (+15% em 800; +4,7% em 2000) — pode ser assinatura de crupiê variável **ou** ruído recente. Só o tempo (shadow) decide.
- **Insight fora da premissa:** dropar C3 em alta confiança → **+22,5%** (concentra stake); promissor para um ciclo futuro.

## 41. 🎯 Recomendação de implantação
1. **Geometria 17#** (C2-7 + C3-5 + CX-5) no **anti-horário**; **horário = abster**.
2. **CX = ForceLast** (último + última força), **gate confiança≤3 + após-red** (a #1).
3. **Stake flat, sem gale** (gale não muda EV).
4. **SHADOW obrigatório:** rodar em papel com o guardrail Newcombe já existente; **promover a dinheiro real só se o ROI persistir** ~200+ apostas de confiança. O edge é **real-ish, robusto, mas não conclusivo** (p≈0,07).
5. **Conexão com o código:** implementar `CX=ForceLast` (lê histórico do sentido), o **filtro de confiança** (2 modelos de força) e os gates `ONLY_AFTER_RED` + `FORCE_CONFIDENCE` — tudo flag-gated e isolado por sentido, como os motores atuais.

> **Síntese final (70+ estratégias, PARTES II–IX):** não existe 'adivinhar o número' (roda uniforme). O que existe — e é **comprovadamente o melhor disponível** — é **empilhar levers fracos-mas-ortogonais**: *anti + 17# + força balística + após-red + confiança de cadência*. Resultado: de **−13%** (cobertura ingênua) a **+14% ROI** estável. Honestamente fraco em significância (p≈0,07), mas é a **evolução de paradigma vencedora** dos dados reais — e o caminho certo é **menos geometria de azar, mais física do crupiê + gestão de quando apostar**.

---

# 🔬 PARTE X — Auditoria de VERDADE (proveniência + busca por viés)

> A pedido: verificar se **todas** as etapas anteriores usaram **fontes reais, válidas e causais**, e se cada simulação reproduziu **o que de fato aconteceu**. Conclusão antecipada: **os dados são reais e a simulação é causal**, mas o achado de '+14%' das PARTES VIII/IX era **viés de seleção / variância de amostra pequena — NÃO um edge real.** Abaixo, as provas.

## 42. Proveniência dos dados (✅ aprovado)
| Teste | Resultado | Veredito |
|---|---|:--:|
| Predição é pré-spin? (centros gravados antes do resultado) | **1.510 linhas** com `sda_centers` preenchido e `result_actual` NULL | ✅ causal |
| Consistência `result_actual(t)==spin_number(t+1)` | **6.032/6.032 = 100%** | ✅ real |
| `result_hit` do BD == (`result_actual` ∈ `sda_numbers`)? | **6.032/6.032 = 100%** | ✅ a simulação reproduz o real |
| Roda uniforme? | χ²=33,3 (gl=36; crítico≈51) | ✅ sem viés físico |
| Centros variam por jogada? | 2.229 triplas distintas em 4.612 | ✅ não-constante |

> **Não há bug de dados nem de código.** A re-implementação limpa reproduziu o +14,11% **bit a bit** — o número existe **in-sample**. O problema é **estatístico**, não de fonte.

## 43. Os 4 testes de verdade sobre o '+14%' (❌ reprovado)

**Alvo:** `ANTI · 17# · ForceLast · confiança≤3 + após-red` (a 'vencedora' da PARTE IX), últimas 400.

| Teste | O que mede | Resultado | Veredito |
|---|---|---|:--:|
| **A. Re-implementação limpa** | bug de código? | reproduz **+14,11%** | sem bug |
| **B. Permutação** (shuffle dos resultados, M=500) | edge real vs acaso | null média −3,7%, **sd 15%**; **P(null≥real)=0,128** | ❌ não-significativo |
| **C. Monte-Carlo de seleção** (roda uniforme, M=500) | inflação por multiplicidade | best-de-16-configs sob **puro acaso** = **+9,5% médio** (p95 +30,6%) | ❌ +14% é esperado por seleção |
| **D. Out-of-sample honesto** | sobrevive fora da amostra? | escolhe no treino → **TESTE = −1,43%** | ❌ colapsa |

> **Veredito C (o mais grave):** procurando o melhor de ~16 configurações numa **roda aleatória**, encontra-se um '+9,5% médio' (e frequentemente >+14%) **por puro acaso**. O '+14%' não se distingue dessa inflação de seleção. **Era uma miragem de multiplicidade de testes + amostra pequena (62 apostas, sd 15%).**

## 44. O que era REAL vs o que era ARTEFATO
| Achado anterior | Status na auditoria | Evidência |
|---|:--:|---|
| Filtro de confiança +14% (PARTE IX) | ❌ **REFUTADO** | perm p=0,128; OOS −1,4%; CV 2/5 folds+; MC-seleção +9,5% baseline |
| 'Dropar C3 → +22,5%' (PARTE VIII §S8) | ❌ **REFUTADO** | 62 apostas, ~11 nº; variância extrema, sem OOS |
| Robustez '400/800/1200' (PARTE IX) | ⚠️ **ilusória** | janelas **aninhadas** (sobrepostas), não independentes |
| Geometria 17# < breakeven do 21# | ✅ **real (estrutural)** | matemática: breakeven 47,2% vs 58,3% |
| Horário é −EV → abster | ✅ **real e robusto** | t=−2,99 (17#, 1.542 apostas); CV 1/5 folds+ |
| Gate após-red (anti) | ✅ **real, modesto** | perm p=0,028 na amostra grande (ver PARTE XI) |

## 45. Bug metodológico-raiz identificado
**Cherry-picking in-sample com janelas aninhadas.** As PARTES VIII/IX selecionaram o melhor de muitas configs na **mesma** janela de avaliação e reportaram esse máximo — clássico *multiple-comparisons + overfitting*. As 'janelas 400/800/1200' eram **sub-conjuntos uma da outra**, não validação independente. **Correção (PARTE XI):** toda alegação passa a exigir **CV em blocos não-sobrepostos + permutação + out-of-sample**, com amostra grande (todo o histórico, ~1.500 apostas).

---

# ✅ PARTE XI — 10 sprints VALIDADOS (metodologia honesta) + C1 + 7 finais

> Refazendo a evolução com **metodologia validada**: toda alegação exige (1) **amostra grande** (todo o histórico anti/hor com centros de produção, ~1.500 apostas, não 62), (2) **CV em 5 blocos não-sobrepostos**, (3) **permutação** (p vs shuffle) e/ou (4) **out-of-sample**. Tudo **isolado por sentido**, centros de produção (causais). Modelo: 14#→be 38,9%; 17#→47,2%; 21#→58,3%.

## 46. Os 10 sprints validados
| # | Investigação | Resultado (validado) | Conclusão |
|--:|---|---|---|
| **V1** | Baselines amostra grande (anti) | 14# +2,79% (t=0,82) · 17#FL +2,88% (t=0,96) · 21#FL +2,17% | todos modestos, ~breakeven |
| **V2** | CV 5 blocos não-sobrepostos | 17#FL após-red: mean **+2,68%**, sd **3,39**, **4/5** folds+ | mais **consistente** |
| **V3** | Permutação (M=400) | 17#FL após-red (todo): **p=0,028** ✅ · confiança (400): p=0,128 ❌ | gate é real; confiança não |
| **V4** | C1 acrescenta? | 14# (sem C1) sd 7,14 vs 17#FL sd **3,39** (4/5) | C1=FL **reduz variância**, não a média |
| **V5** | Gate é o driver? | **sem gate +0,12% (t=0,05)** vs após-red +2,88% | o **edge vem do após-red** |
| **V6** | Bootstrap IC95 (5.000) | +0,44u/aposta, IC95 **[−0,45, +1,33]**, P(EV>0)=**82,8%** | provável, **não conclusivo** |
| **V7** | Recência (primeiros vs últimos 1.500) | +3,21% e **+3,54%** | **estável no tempo** (≠ confiança) |
| **V8** | Confiança filtrada — re-teste | CV sd 9,57, **2/5** folds+, OOS −1,4% | ❌ **refutada** (overfit) |
| **V9** | Horário | full −8,64% **t=−2,99**; CV **1/5** | **abster** (robusto) |
| **V10** | C1=Lag2 vs ForceLast | Lag2 CV +4,53% **sd 8,44** (3/5) vs FL +2,68% sd 3,39 (4/5) | FL mais **confiável**; Lag2 instável |

## 47. 🎯 Como eu definiria o C1 (resposta honesta e validada)
Dado que **C2 = cluster denso das últimas 4 do sentido** e **C3 = região fria das últimas 5 (ambos os sentidos)**:

> **C1 = ForceLast — o último resultado do sentido deslocado pela última força aplicada** (`C1 = roda[pos(último) + (último − penúltimo)]`), com **raio 2 (5 números)** na geometria 17#.

**Justificativa validada (não in-sample):**
- **O C1 não cria edge — o edge vem do gate após-red.** Provado em V5: sem gate o ROI é +0,12% (zero). Nenhuma definição de C1 muda isso (a roda é uniforme).
- **O papel real do C1 é ESTABILIZAR:** C1=ForceLast **reduz a variância** dos retornos (sd 3,39 vs 7,14 do 14# sem C1) e melhora a consistência (**4/5 blocos positivos**). É o complemento **temporal/balístico** a C2 (denso) e C3 (frio), que são espaciais — eixo ortogonal.
- **Por que ForceLast e não Lag2 / frio / quente:** Lag2 tem média maior (+4,5%) mas **sd 8,44 e só 3/5** (instável, não-confiável). Regiões frias/quentes ≈ acaso (roda uniforme). ForceLast é o único com baixa variância e fundamento físico (persistência de velocidade do crupiê).
- **Alternativa minimalista:** se o objetivo for simplicidade, **omitir o C1** e apostar 14# (C2+C3) após-red entrega média igual (+2,86%), só com mais variância. O C1=ForceLast é o **refinamento que suaviza**.

## 48. 🏆 As 7 melhores estratégias FINAIS (honestas, por robustez de CV)
> Ranqueadas por **consistência validada** (CV em blocos + significância), **não** por pico in-sample. Todas **anti-horário** (horário = abster). Todas **flat, sem gale**.

| # | Estratégia | Geo | CV mean | CV sd | folds+ | Sig. | Perfil |
|--:|---|:--:|--:|--:|:--:|---|---|
| 🥇 | **C2+C3+C1(ForceLast) · após-red** | **17#** | +2,68% | **3,39** | **4/5** | perm **p=0,028** | melhor risco-ajustado |
| 🥈 | C2+C3+C1(ForceLast) · após-red | 21# | +1,90% | 3,37 | 4/5 | — | mesma lógica, geometria atual |
| 🥉 | C2+C3 (sem C1) · após-red | 14# | +2,86% | 7,14 | 3/5 | perm p=0,070 | maior média, + variância |
| 4 | C2+C3+C1(Lag2) · após-red | 17# | +4,53% | 8,44 | 3/5 | — | maior média, instável |
| 5 | C2+C3+C1(ForceLast r1) · após-red | 16# | +2,09% | 7,19 | 3/5 | — | cobertura enxuta |
| 6 | C2+C3+C1(ForceLast) · sem gate | 17# | −0,12% | — | 4/5 | t=0,05 | **alto volume** (2.224), ~neutro |
| 7 | C2+C3 (atual em produção) | 14# | ~0% | — | — | — | **referência** (c2c3 no ar) |

**Por que valem a pena (e a verdade honesta):**
- **#1 (17# FL após-red):** o **único com significância** (perm p=0,028) **e** baixa variância (sd 3,39, 4/5 folds+) **e** estável no tempo (V7). É a **escolha recomendada**: ~+2,7% ROI honesto.
- **#2 (21#):** para quem **não quer mudar a geometria** atual de 21 números, a mesma regra (FL+após-red) entrega +1,9% consistente.
- **#3 (14# sem C1):** prova que **o C1 é opcional** — o gate carrega o edge. Maior média, porém mais 'solavancos' (sd 7,14).
- **#4 (Lag2):** **tentador (+4,5%) mas não confiável** (sd 8,44) — fica como hipótese para shadow, não para produção.
- **#6–#7:** alto volume / referência — úteis como **baseline** e controle.

## 49. ⚖️ Veredito final honesto (a verdade que a auditoria revelou)
1. **Não existe '+14%'.** Aquilo era seleção/variância. O edge **real e defensável** é **modesto: ~+2,7% ROI** no anti-horário, com **17# + C1=ForceLast + após-red**, *significância marginal* (perm p=0,028; bootstrap P(EV>0)=83%, IC inclui 0).
2. **A fonte do edge é o TIMING (após-red, mean-reversion no anti)** — não a geometria do C1 nem regiões frias/quentes. O C1=ForceLast **estabiliza** (reduz variância).
3. **Horário: abster** (−EV robusto, t=−2,99).
4. **17# é estruturalmente melhor que 21#** (breakeven menor) e **reduz variância** vs 14#.
5. **Stake flat, gale teto 1, isolado por sentido** — gale não muda EV.
6. **Implantar SOMENTE em shadow** (guardrail Newcombe já existe) e promover a dinheiro real **apenas se o ~+0,44u/aposta persistir** por **várias centenas** de apostas reais. O edge é **real-ish porém pequeno e não-conclusivo** — e a roda é uniforme. É dinheiro real: ceticismo é a postura correta.

> **Lição metodológica (a maior entrega desta auditoria):** o pico in-sample mente. Só sobrevive o que passa em **CV não-sobreposta + permutação + out-of-sample + amostra grande**. Sob esse crivo, de 70+ estratégias resta **um** edge modesto e honesto — e a disciplina de **medir a verdade**, não a esperança.

---

# 🎰 PARTE XII — Estratégia vencedora detalhada + aplicabilidade por sessão de dealer

> Auditoria da última sprint + estudo de **como a estratégia vencedora se comporta por sessão de dealer** (delimitada pelo botão **🔄 Nova Sessão / Novo Dealer**), com picos e vales intra-sessão, e a estrutura ótima de operação. Tudo sobre dados reais (`decisions.db`), **isolado por sentido**, com **reset dos motores a cada troca de dealer** (operação realista).

## 50. O que é o botão 'Troca de Dealer' (mecanismo no software — via grafo/código)
- **Frontend** (`extension/content.js:62`): botão `🔄` *'Nova Sessão (Novo Dealer)'* → emite a mensagem WebSocket `nova_sessao`.
- **Servidor** (`server/message_handler.py:handle_new_session` :1057): dentro do `state_lock` → `db_service.end_session(antiga)` → **`game_state.reset_session()`** (zera C2/C3 históricos, deques `c_attr`, motores e o **estado adaptativo do SDA17** `reset_adaptive`) → `create_session(novo uuid8)` → `current_session_id = novo`.
- **Persistência:** cada decisão é gravada com o `session_id` vigente. **Logo, no banco, cada bloco de `session_id` é exatamente uma sessão de dealer** — é assim que identificamos quando a sessão foi reiniciada pelo botão.

## 51. Realidade das sessões no banco (≠ premissa de 60 jogadas)
| Métrica | Valor real (BD) |
|---|---|
| Sessões (com 3 centros) | 165 |
| Tamanho **total**/sessão | **mediana 20**, média 27 (min 1, máx 142) |
| Jogadas **anti**/sessão | **mediana 10**, média 13,5 |
| Sessões com ≥30 anti | **18 (11%)** |
| Sessões com ≥15 anti | 67 (40%) |

> ⚠️ **Insight crítico:** a premissa de '60 jogadas (30/sentido) por sessão' é o **teto**, não a média. A **sessão típica tem só ~10 anti** — e como o botão de dealer **reseta os motores**, cada sessão é um **cold-start**. A estratégia vencedora precisa de histórico (força + após-red), então **a maioria das sessões mal chega a apostar**. Esta é a maior limitação de aplicabilidade.

## 52. A estratégia vencedora — descrição detalhada
**🏆 ANTI-horário · 17 números · C1=ForceLast · gate após-red · stake flat**

Em cada jogada do **sentido anti-horário** (o horário **não aposta** — é −EV, t=−2,99):
1. **C2** = cluster mais **denso** das últimas 4 anti (centro + 3 vizinhos de cada lado = **7 números**).
2. **C3** = região mais **fria** das últimas 5 (ambos os sentidos; probabilidade é por posição) → **5 números** (±2).
3. **C1 = ForceLast** = `roda[ posição(último anti) + (último − penúltimo) ]` — o último resultado **projetado pela última força** aplicada (extrapolação balística de velocidade constante) → **5 números** (±2).
4. **União** ≈ **17 números** (cobertura real ~15, por sobreposição).
5. **Gatilho (após-red):** só aposta se a **jogada anti anterior foi red** (a cobertura C2∪C3 errou). É o **driver do edge** (reversão à média; sem o gate o ROI é ~0%).
6. **Stake flat** (1u por número, ~15-17u/aposta). **Sem gale** (gale não muda o EV).

**Desempenho honesto (com reset por sessão — operação real):** ~**+2,0% ROI** (+0,32u/aposta, 796 apostas), vs +2,9% no backtest global (sem reset). O edge **sobrevive** ao reset, mas perde ~metade das apostas no warmup.

## 53. 📈 Picos e vales DENTRO da sessão (a resposta pedida)
ROI por posição da jogada anti dentro da sessão (reset por dealer, warmup 8):

| Posição anti na sessão | Apostas | ROI | P&L/aposta | Leitura |
|---|--:|--:|--:|---|
| 1–10 (início) | 66 | +15,2%* | +2,38u | *poucas apostas (warmup come 8) — ruidoso |
| **11–20 (vale)** | 428 | **+0,2%** | +0,03u | **mais fraca** — histórico ainda raso |
| **21–30 (pico)** | 176 | **+6,9%** | +1,07u | **mais forte** — motores maduros |
| 31–40 (pico) | 69 | +4,3% | +0,67u | ainda forte |
| **41+ (colapso)** | 57 | **−17,5%** | −2,68u | **degrada** — sessões longas viram −EV |

> **Padrão claro:** a estratégia é **fraca no miolo inicial (11–20)**, **mais forte entre ~20 e 40** (motores aquecidos), e **colapsa após 41+** (sessões muito longas). O **sweet-spot é a jogada anti ~20–40** — exatamente a faixa de uma sessão saudável de ~30 anti (60 total). Picos e vales sugerem **estruturar a sessão para operar na janela 20–40 e parar antes do colapso**.

## 54. Estrutura ótima de operação por sessão (validado)
| Intervenção | ROI | P&L total | Leitura |
|---|--:|--:|---|
| Base (reset por sessão, warmup 8) | +2,06% | +252u | honesto |
| **Warmup 3** (apostar mais cedo) | +1,93% | **+340u** | mais apostas, + lucro absoluto |
| **Cortar após jogada 40** (evita o vale 41+) | **+2,94%** | **+493u** | melhor ROI **e** lucro |
| Cortar após jogada 30 | +2,85% | +447u | quase igual, mais conservador |
| **Stop-loss 15u/sessão** | **+5,47%** | +426u | **melhor risco-ajustado** (corta sessões ruins cedo) |
| Stop-loss 30u (default atual) | +1,42% | +146u | **frouxo demais** p/ esta estratégia |

> **Estrutura recomendada:** **warmup 3 → apostar na janela ~4–40 anti → stop-loss apertado de ~15u por sessão**. Isso (a) aproveita o pico 20–40, (b) **evita o colapso 41+** e (c) **corta as sessões frias cedo**. O alvo de '30 anti/sessão' do operador é, de fato, **próximo do ótimo** — a estratégia quer parar por volta da jogada 30–40.

## 55. 🛡️ Auditoria de automação e proteção por sessão (existe? gaps?)
**Já EXISTE no código (ativo em produção):**
- **Reset por troca de dealer** (`reset_session` + `reset_adaptive`) — zera motores/históricos/adaptativo. ✅ correto e necessário.
- **Stop-loss por sessão** (`PROFIT_STOP_LOSS_UNITS`, **default 30u**) — quando o P&L da sessão ≤ −30u, o stake cai ao mínimo (modula, não suprime — INV-3). ✅ existe.
- **CUT-POLICY v1** (`PROFIT_CUT_V1`, default ON) — corta stake quando score<4/gale>2. ✅ existe.

**GAPS de proteção (para esta estratégia):**
1. **Stop-loss frouxo:** 30u rende +1,4%; **15u rende +5,5%**. Recomendo **baixar para ~15u** (env `PROFIT_STOP_LOSS_UNITS=15`) — mudança de 1 variável, sem código.
2. **Sem limite de jogadas/sessão:** o **vale 41+ (−17,5%)** fica desprotegido. Falta um **cap de ~40 jogadas anti** (parar de apostar; só observar) — não existe hoje.
3. **Sem stop-win / profit-taking:** não há trava de lucro por sessão (encerrar no verde).
4. **A estratégia não está conectada:** produção roda hoje `c2c3` 14# **nos dois sentidos, sem gate após-red** (PARTE anterior). O vencedor (anti-only, 17#, ForceLast, após-red) é **proposta** — exige wiring (flags `ONLY_AFTER_RED`, `CX=ForceLast`, `BET_DIR=anti`).

## 56. 🎯 Estratégia FINAL que vale a pena (recomendação)
> **Núcleo:** ANTI-horário · 17# (C2-7 + C3-5 + C1=ForceLast-5) · **gate após-red** · **flat, sem gale** · **horário = abster**.
>
> **Camada de sessão (proteção/estrutura):** por sessão de dealer (reset no botão) — **warmup 3**, apostar na **janela jogada 4–40 anti**, **stop-loss 15u/sessão**, **stop-win opcional** ao atingir +20u.
>
> **Economia esperada (honesta):** ~**+2% ROI** base; **+3 a +5%** com a estrutura de sessão (corte do vale + stop-loss 15u). Edge **real porém modesto e não-conclusivo** (perm p=0,028; bootstrap IC inclui 0).

**Por que vale a pena (e os limites):**
- É a **única configuração** que sobrevive a CV não-sobreposta + permutação + reset por sessão (PARTES X–XI), com **risco controlado** (stop-loss 15u corta sessões ruins).
- A estrutura por sessão **alinha-se ao ritmo real do dealer**: opera no pico (20–40), evita o colapso (41+) e abandona sessões frias cedo.
- **Limite honesto:** a sessão típica (~10 anti) é **curta demais** para a estratégia maturar; o ganho concentra-se nas ~40% de sessões com ≥15 anti. **Não é dinheiro garantido** — a roda é uniforme (χ²=33,3).

**Implantação (ordem segura):** (1) baixar `PROFIT_STOP_LOSS_UNITS=15` (1 env, já existe o mecanismo); (2) wiring do vencedor **em SHADOW** (anti-only, 17#, ForceLast, após-red) com cap de 40 jogadas; (3) coletar ~300+ apostas reais de shadow por sessão; (4) **promover a dinheiro real só se o +0,3–0,5u/aposta persistir**. Nunca galar.

---

# 🎮 PARTE XIII — Auditoria da verdade APLICADA (UX, sentidos, stake, gale, overlap)

> Respostas às perguntas operacionais, cada uma **simulada sobre dados reais** com reset por sessão (operação realista). Resumo honesto: a estratégia **analisa cada sentido isolado, mas só tem edge no anti-horário**; o melhor 'foco de sessão' é **deixar o lucro correr e cortar a perda cedo** (não take-profit); **stake flat sem gale**; e as **regiões devem se sobrepor**.

## 57. Q1 — Serve para os DOIS sentidos? (auditoria honesta)
A estratégia **analisa cada sentido isoladamente** (correto), mas o **edge existe somente no anti-horário**:

| Sentido | gate=nenhum | **gate=após-red** | gate=após-green | Veredito |
|---|--:|--:|--:|---|
| **ANTI** | −2,58% | **+1,93%** ✅ | −7,57% | edge real (após-red) |
| **HORÁRIO** | −10,43% (t=−3,9) | −11,75% (t=−3,6) | −12,09% | ❌ **−EV em todos os gates** |

> **Verdade:** no **horário não há timing que salve** (perm p=0,997 — significativamente negativo). A premissa de 'servir aos dois sentidos' **não se sustenta**: o anti-horário aposta (após-red), o **horário deve ABSTER**. O motivo provável: a geometria C2/C3 do horário já é −EV e o ruído domina. *A estrutura é a mesma para os dois (isolada), mas só se libera a aposta no anti.*

## 58. Q3 — Como funciona a cada jogada (mecânica/UX): 'aposta e sai'?
A regra **após-red** é naturalmente **um tiro por red**:
- A jogada anterior do anti **errou** (red) → **aposta a próxima** (1 rodada, ~15-17 números).
- Se **acertar (green)** → o sistema **pausa automaticamente** (a próxima é 'após-green', que não aposta) — *ela faz a aposta e 'sai' até o próximo red*.
- Se **errar de novo (red)** → **aposta outra vez** na seguinte (continua enquanto vier red).

> Simulei 'aposta-1-e-pausa' vs 'aposta-após-cada-red': **resultado idêntico** (+1,93%) — porque após um green o gate já pausa sozinho. Então a UX é: **entra após cada red, sai (pausa) após cada green**. Não há decisão manual de saída por jogada.

## 59. Q2 — Foco de sessão: take-out no objetivo OU continuar se favorável?
Simulação por sessão (anti, reset por dealer):

| Política de sessão | ROI | P&L total | Leitura |
|---|--:|--:|---|
| Continuar sempre (base) | +1,93% | +340u | referência |
| **Stop-WIN +10u** (sai no objetivo) | +0,78% | +60u | ❌ pior |
| Stop-WIN +20u | **−1,10%** | −108u | ❌ **destrói** o edge |
| **Stop-LOSS −15u** (deixa correr o verde) | **+5,47%** | +426u | ✅ **melhor** |
| Stop-LOSS −20u | +2,96% | +277u | ✅ bom |
| Banda win+20/loss−15 | +4,87% | +147u | ok, poucas apostas |

> **Resposta clara (assimetria):** **NÃO faça take-out no objetivo** — cortar o lucro cedo **piora** (o edge está em deixar a sessão favorável correr). **Faça o oposto:** **continue enquanto favorável e CORTE a perda cedo** com **stop-loss ~15u/sessão**. *Deixe o verde correr, mate o vermelho rápido.* Isso leva o ROI de +1,9% para **+5,5%**.

## 60. Q5/Q6 — Melhor stake e faz sentido gale?
| Stake | ROI | P&L/aposta | P&L total | Veredito |
|---|--:|--:|--:|---|
| **Flat (1u/número)** | **+1,93%** | **+0,296u** | +340u | ✅ **ótimo** |
| Gale teto 2 | +0,25% | +0,058u | +66u | ❌ pior |
| Gale teto 3 | −0,15% | −0,042u | −48u | ❌ pior |
| Gale teto 4 | +0,49% | +0,148u | +170u | ❌ pior |

> **Gale NÃO faz sentido** — **piora** o resultado em todos os tetos (o EV por aposta é invariante ao staking; o gale só adiciona variância e risco de ruína, comendo o edge). **Melhor ganho por stack = stake FLAT**: 1 unidade por número, ~**15-17u de exposição por aposta**. Se quiser dimensionar, escale a **unidade** (ex.: R$5/número), nunca o gale.

## 61. Q7 — As regiões se sobrepõem ou não?
| Configuração | ROI | N médio (cobertura real) | Veredito |
|---|--:|--:|---|
| **Sobreposição PERMITIDA (atual)** | **+1,93%** | **15,4** | ✅ melhor |
| Forçar DISJUNTO (mover C1 p/ N=17) | +0,63% | 17,0 | ❌ pior |

> **As regiões SE SOBREPÕEM** — em **54% das jogadas** há sobreposição (perde-se ~**1,65 número**), e a cobertura real média é **~15,4** (não 17). E isso é **bom**: aceitar a sobreposição **reduz N** (menor breakeven: 15,4/36=42,8% vs 17/36=47,2%). **Forçar regiões disjuntas (espalhar) piora** (+0,63%) — alarga a aposta e sobe o breakeven. **Recomendação: permitir sobreposição** (apostar a união real, ~15 números).

## 62. UX detalhada — a cada jogada e a cada 30 jogadas (anti)
**A cada jogada (anti):**
1. Saiu o resultado anti anterior. O sistema recalcula C2 (denso-4), C3 (frio-5) e C1=ForceLast (último+força).
2. **Se a anterior foi red** → mostra os ~15 números (união C2∪C3∪C1) e **manda apostar 1u em cada**.
3. **Se a anterior foi green** → **não aposta** (aguarda o próximo red).
4. Stop-loss: se a sessão acumular −15u, **pausa as apostas** até a troca de dealer.

**A cada ~30 jogadas anti (1 sessão saudável):**
| Métrica | Valor (real, flat) |
|---|---|
| Apostas disparadas (~42% das elegíveis) | **~11 apostas** |
| Exposição apostada | ~173u |
| **P&L médio/bloco** | **+4,4u** (ROI +2,57%) |
| P&L **mediana**/bloco | **0u** |
| Em unidade R$5/número | ~**+R$22** médio/bloco |

> **Honestidade:** a **mediana por bloco de 30 é ~0u** — metade dos blocos é neutra/levemente negativa; o ganho médio (+4,4u) vem de uma **cauda de blocos bons**. É edge **pequeno e de alta variância**, não renda por sessão garantida. O stop-loss de 15u é o que torna o agregado robusto (+5,5%).

## 63. ✅ Resposta consolidada (a estratégia final aplicada)
- **Sentido:** apostar **só anti-horário** (estrutura isolada por sentido; **horário abster** — −EV comprovado).
- **Entrada/saída:** **entra após cada red**, **pausa após cada green** (tiro único por red, automático).
- **Foco de sessão:** **deixe correr o favorável; corte a perda cedo** — **stop-loss ~15u/sessão**, **sem take-profit** (take-out piora).
- **Stake:** **flat**, 1u/número (~15u/aposta); **sem gale** (gale piora). Escale a unidade, não o gale.
- **Regiões:** **sobrepostas** (união real ~15 números; não force disjunção).
- **Geometria:** 17 nominal (C2-7 + C3-5 + C1=ForceLast-5), cobertura real ~15.
- **Expectativa honesta:** ~+0,3u/aposta (flat) → **+2 a +5,5% ROI** com stop-loss; **mediana por sessão ~0** (cauda positiva). **Edge real mas modesto** (perm p≈0,09; roda uniforme) → **shadow antes de dinheiro real**.

---

# 🧭 PARTE XIV — Jornada do usuário: stake no overlap, quando começar, como operar

> Respostas operacionais simuladas em dados reais (reset por sessão). Pontos-chave: **não** aposte valores variados nos números sobrepostos (**flat 1u** é mais robusto que stacked); **espere ~3 jogadas anti** após o dealer entrar; e o roteiro de sessão é **apostar após red, pausar após green, cortar a perda em −15u**.

## 64. Stake no overlap — aposto 2u nos números sobrepostos? (auditoria honesta)
Duas formas de apostar quando as regiões se sobrepõem:
- **Flat (união):** 1u em cada número **distinto** (~15 números, ~15u). Número sobreposto recebe **1u**.
- **Stacked (confiança):** stake fixo 17u distribuído por **pertencimento** — número coberto por 2 regiões recebe **2u** (o 'núcleo de consenso').

| Comparação | ROI (amostra grande, **sem** stop-loss) | ROI (com stop-loss 15) | Veredito |
|---|--:|--:|---|
| **Flat 1u/número** | **+1,93%** (t=0,56) | +5,47% | ✅ **mais robusto** |
| Stacked 2u no overlap | +1,17% (t=0,32) | +7,58% | ❌ artefato de variância |

> **Verdade:** na **amostra grande limpa (sem stop-loss), o flat VENCE** (+1,93% vs +1,17%). O 'stacked +7,58%' só aparece **quando combinado ao stop-loss** — é **interação de alta variância (sd 21 vs 18), não edge real**. **Resposta: NÃO aposte valores variados.** Use **1u por número distinto** na união (~15 números). *A sobreposição já te beneficia ao reduzir N (cobertura ~15 = breakeven 42,8% em vez de 47,2%); não precisa dobrar nada.* Stacked só adiciona risco.

## 65. Quando começar a apostar — quantas jogadas esperar após o dealer entrar?
O **mínimo técnico** são **~3 jogadas anti**: 2 para calcular a **força** (último − penúltimo) e 1 **red** para liberar o gatilho. Testei esperar mais:

| Esperar (anti) | 2 | **3** | 4 | 6 | 8 | 10 | 15 |
|---|--:|--:|--:|--:|--:|--:|--:|
| ROI | +2,4% | +5,5% | +0,8% | −4,3% | +0,9% | +2,7% | −14% |

> **Atenção (honestidade):** essa curva é **errática e não-monotônica** (esperar 6 dá −4%, esperar 15 dá −14%) — é **ruído/overfit** ao stop-loss, **não** uma regra fina. Na amostra limpa (sem stop-loss), esperar 3 (+1,93%) ≈ esperar 8 (+2,06%). **Conclusão: espere o mínimo (~3 anti ≈ 6 rodadas totais) e comece** — não há ganho confiável em esperar mais, e esperar demais perde apostas e o pico de meio de sessão (jogadas 20–40, ver §53). **Não existe fine-tuning mágico do warmup; o que importa é o stop-loss + anti-only + após-red + flat.**

## 66. 🗺️ Roteiro do usuário durante a sessão (playbook)
**Início (dealer acabou de entrar / você clicou 🔄):**
- Jogadas 1–2 anti: **só observe** (a força ainda não é calculável). Não aposte.
- A partir da 3ª anti: a estratégia está **armada**.

**A cada rodada:**
| Situação | Ação |
|---|---|
| Rodada do **horário** | **Nunca apostar** (−EV); só observar (alimenta o C3 de 'ambos os sentidos') |
| Anti, **anterior foi RED** | **Apostar** 1u em cada um dos ~15 números (união C2∪C3∪C1) |
| Anti, **anterior foi GREEN** | **Pausar** (aguardar o próximo red) |
| Sessão acumulou **−15u** | **Parar de apostar** nesta sessão (stop-loss); só observar |
| Sessão **favorável** (no verde) | **Continuar** — NÃO encerrar no lucro (take-profit piora) |

**Quando esperar a troca de dealer:**
- A troca acontece naturalmente a cada **~30 jogadas/sentido (~60 totais)**. Quando o dealer trocar (botão 🔄), o sistema **reseta** os motores e a contagem recomeça.
- Se a sessão **bateu o stop-loss (−15u)**, fique **só observando até a troca** — o novo dealer zera o estado e você recomeça do passo 1.
- A janela mais forte é a **jogada anti ~20–40**; após a **41ª** o desempenho degrada (§53) — se a sessão for muito longa, **reduza/pare** e aguarde a troca.

## 67. Resumo da jornada (do registro ao encerramento)
1. **Dealer entra** → clique 🔄 (reset). Comece a **registrar** os resultados.
2. **Espere ~3 jogadas anti** (≈6 rodadas) — observe, não aposte.
3. **Aposte quando:** for anti **e** a anti anterior foi **red** → 1u em cada um dos ~15 números (**flat, sem dobrar overlap, sem gale**).
4. **Pause quando:** anti anterior foi **green**, ou for rodada do **horário**.
5. **Pare a sessão quando:** P&L da sessão ≤ **−15u** (stop-loss) → só observe.
6. **Deixe correr** se estiver no verde (sem take-profit). Atenção à degradação após a **40ª** jogada.
7. **Troca de dealer (~30/lado)** → reset automático → volte ao passo 2.

> **Expectativa honesta por sessão (~30 anti):** ~11 apostas, **+4,4u em média mas mediana ~0u** (ROI ~+2,6% flat; ~+5% com stop-loss). É **edge pequeno, de alta variância** — o lucro vem de uma cauda de sessões boas, protegida pelo stop-loss. **Não é renda garantida por sessão.** Rode em **shadow** antes de valer dinheiro real (roda uniforme; perm p≈0,09).

---

# 🔄 PARTE XV — Comportamento do C1 substituído (ForceLast) a cada jogada

> Na estratégia vencedora o **C1 é substituído por ForceLast** = o último resultado anti **projetado pela última força** (`C1 = roda[ pos(último) + (último − penúltimo) ]`). Aqui mostramos, **jogada a jogada**, como esse C1 se comporta — com um **ledger real** do banco e estatísticas agregadas.

## 68. Como o C1 se recalcula a cada jogada
- **C2** (denso-4) e **C3** (frio-5) mudam **devagar** (centros de massa de janelas de 4–5).
- **C1 = ForceLast** muda **a cada jogada** e de forma **ampla**: ele 'persegue' a bola anterior deslocada pela força. Se a roda 'andou' +9 casas, o C1 vai para 9 casas adiante do último número.

**Comportamento agregado (2.611 jogadas anti reais):**
| Métrica do C1 | Valor | Leitura |
|---|--:|---|
| Movimento médio entre jogadas | **9,3 casas** (mediana 9, máx 18) | região **muito móvel** (~meia-roda) |
| Jogadas em que NÃO se move | 3% | quase sempre muda |
| Jogadas com salto ≥9 casas | 55% | salta meia-roda na maioria |
| Bola caiu na região do C1 (±2) | **13,9%** | ≈ **acaso** (baseline 13,5%) |
| C1 sobrepõe C2 de produção | 17% | overlap ocasional |

> **Verdade honesta:** o C1=ForceLast **captura a bola a ~14%, praticamente o acaso (13,5%)**. Ou seja, **o C1 não 'prevê'** — ele é uma **3ª região errante** que diversifica a cobertura e **estabiliza a variância** (PARTE XI §V4), mas **o edge vem do gate após-red, não do C1**. O C1 é estrutura, não profecia.

## 69. 📒 Ledger real — sessão `9bbdbbc2` (28 jogadas anti, jogada a jogada)
Legenda: **Força** = último−penúltimo (deslocamento na roda) · **C1** = ForceLast (recalculado) · **N** = números cobertos (união ~15-17) · 🟢/🔴 = green/red da aposta · **Acum.** = P&L acumulado da sessão (u).

| # | Bola | Força | C2 | C3 | **C1=FL** | Ação | N | Res | P&L | Acum. |
|--:|--:|--:|--:|--:|--:|---|--:|:--:|--:|--:|
| 1 | 11 | — | 4 | 10 | **—** | observa |  |  | +0 | +0 |
| 2 | 17 | — | 18 | 24 | **—** | observa |  |  | +0 | +0 |
| 3 | 15 | -6 | 0 | 25 | **15** | observa |  |  | +0 | +0 |
| 4 | 27 | -6 | 18 | 16 | **12** | observa | 15 |  | +0 | +0 |
| 5 | 10 | +9 | 23 | 9 | **24** | APOSTA | 14 | 🟢 | +22 | +22 |
| 6 | 28 | +7 | 29 | 4 | **14** | pausa(green) | 16 |  | +0 | +22 |
| 7 | 12 | +14 | 10 | 4 | **34** | pausa(green) | 17 |  | +0 | +22 |
| 8 | 12 | +1 | 27 | 19 | **35** | APOSTA | 17 | 🟢 | +19 | +41 |
| 9 | 12 | +0 | 7 | 16 | **12** | APOSTA | 13 | 🟢 | +23 | +64 |
| 10 | 21 | +0 | 32 | 31 | **12** | pausa(green) | 16 |  | +0 | +64 |
| 11 | 0 | +9 | 29 | 16 | **11** | APOSTA | 17 | 🔴 | -17 | +47 |
| 12 | 14 | -5 | 10 | 6 | **28** | APOSTA | 17 | 🔴 | -17 | +30 |
| 13 | 34 | -12 | 20 | 23 | **36** | APOSTA | 16 | 🔴 | -16 | +14 |
| 14 | 8 | -16 | 10 | 3 | **29** | APOSTA | 17 | 🟢 | +19 | +33 |
| 15 | 28 | +7 | 7 | 15 | **1** | pausa(green) | 17 |  | +0 | +33 |
| 16 | 7 | +16 | 20 | 15 | **27** | pausa(green) | 17 |  | +0 | +33 |
| 17 | 5 | -1 | 34 | 8 | **29** | APOSTA | 17 | 🔴 | -17 | +16 |
| 18 | 16 | -12 | 12 | 21 | **25** | APOSTA | 14 | 🔴 | -14 | +2 |
| 19 | 35 | +2 | 30 | 21 | **1** | APOSTA | 17 | 🔴 | -17 | -15 |
| 20 | 24 | +13 | 29 | 11 | **6** | parado(SL) | 16 |  | +0 | -15 |
| 21 | 28 | -14 | 3 | 13 | **2** | parado(SL) | 17 |  | +0 | -15 |
| 22 | 23 | +12 | 21 | 36 | **25** | pausa(green) | 13 |  | +0 | -15 |
| 23 | 6 | -15 | 17 | 14 | **15** | parado(SL) | 17 |  | +0 | -15 |
| 24 | 9 | -7 | 7 | 20 | **19** | pausa(green) | 17 |  | +0 | -15 |
| 25 | 10 | +17 | 26 | 18 | **25** | parado(SL) | 17 |  | +0 | -15 |
| 26 | 34 | -9 | 31 | 35 | **34** | parado(SL) | 17 |  | +0 | -15 |
| 27 | 34 | -9 | 35 | 4 | **0** | parado(SL) | 13 |  | +0 | -15 |
| 28 | 33 | +0 | 16 | 29 | **34** | parado(SL) | 17 |  | +0 | -15 |

## 70. Leitura do ledger (o que ele ensina)
- **C1 dança:** jogada 5 C1=24, jogada 6 C1=14, jogada 7 C1=34, jogada 8 C1=35… salta a cada rodada conforme a força (média 9 casas). **C2/C3 são âncoras; C1 é o satélite móvel.**
- **Entra/pausa funcionando:** jogada 5 apostou (após red) e **green +22**; jogadas 6–7 **pausou** (vinha de green); jogadas 8–9 apostou e ganhou (pico **+64**).
- **A maré virou:** jogadas 11–13 e 17–19 vieram **reds** seguidos; o acumulado caiu de +64 para **−15**.
- **Stop-loss protegeu:** ao atingir **−15u** (jogada 19), a estratégia **parou de apostar** (jogadas 20–28 'parado(SL)') — **evitou sangrar mais** numa sessão fria, mesmo continuando a observar.

> **Esta sessão fechou em −15u** (no stop-loss) — um exemplo **honesto, não cereja**. Ilustra a natureza do edge: **muita variância**, com **pico de +64** que regrediu. *Aqui, um take-profit teria salvo a sessão* — mas, na média de todas as sessões, take-profit **piora** (PARTE XIII §59); o stop-loss é a proteção correta. O ganho agregado vem da **cauda de sessões boas**, não de cada sessão.

## 71. Resumo — o papel do C1 a cada jogada
1. **Recalcula sempre:** a cada jogada anti, C1 = último resultado + última força (salta ~9 casas).
2. **Cobre 5 números** (±2) que **mudam de lugar** toda rodada — diversifica a aposta em torno do 'para onde a bola foi projetada'.
3. **Não prevê** (captura ~14% ≈ acaso) — seu valor é **estrutural** (completa o 17#, suaviza variância), não preditivo.
4. **O que decide o lucro** não é o C1, é **quando apostar** (após-red) e **quando parar** (stop-loss 15u). O C1 é o **complemento móvel** da geometria, não a fonte do edge.

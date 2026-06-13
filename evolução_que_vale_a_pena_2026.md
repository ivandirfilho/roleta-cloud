# Evolução Que Vale a Pena — 2026

> **Modo:** análise sênior de evolução de estratégia, processamento ilimitado, YOLO.
> **Método:** replay **causal** (sem look-ahead) sobre todo o histórico resolvido
> (cw=1.385 · ccw=1.377 decisões, **107 sessões cada**), **por sentido isolado** (P6),
> **reset por sessão** (P10). **Rodada 2:** ampliada para **+10 cenários novos em cada
> ponto → 18 modelos por ponto, 54 configs no total**. Métrica pedida pelo owner:
> matriz **miss→hit / hit→miss** vs baseline (transformar erros em acertos mantendo
> acertos) + **EV coverage-aware** (não cair no truque do N) + **walk-forward
> treino(jan–abr)/teste(mai–jun) nos TRÊS pontos** como gate de promoção + um
> **ranking explícito de "regra geral adaptativa"**.
> **Motor:** `scripts/evolution_sim_2026.py` (reexecutável; 18A+18B+18D). Base:
> `data/decisions_prod_1206b.db` (snapshot 12/06 23:19 BRT).

---

## 0. O fato que governa tudo (reconfirmado com 54 configs)

Erro de força (real − previsto), assinado: **σ ≈ 10.8 casas em AMBOS os sentidos**
numa roda de 37. A força de chegada é **quase uniforme**; autocorrelação t−1→t ≈
−0.13 (ruído). A rodada 2 **testou explicitamente** se esse −0.13 é explorável
(modelo `A12_antipersist`, reversão à média): **falhou** (−95/−72 de saldo). Logo:

> **Não há ganho em "prever melhor a força". O ganho está em ONDE colocar os 17
> números — e a rodada 2 mostrou exatamente PARA ONDE: tirar massa do centro
> previsto e jogá-la nos satélites (a cauda bimodal real de cada sentido).**

---

## PONTO A — Preditor de força / posição de C1 (18 modelos)

Geometria fixa 7+5+5 @10/10. Cada modelo prevê a força a partir do histórico de
forças reais do sentido (causal). `*` = baseline produção (mediana-7). **WF** =
passa o gate walk-forward (melhora EVcov vs baseline em treino E teste).

| Modelo | cw hit% / EVflat / saldo | ccw hit% / EVflat / saldo | WF |
|---|---|---|---|
| A0 mediana-7 `*` | 43.8% / −1.22 / −29 | 44.2% / −1.08 / +7 | — |
| A1 EWMA(.3) | 38.2% / −3.25 / −107 | 37.6% / −3.46 / −84 | — |
| A2 último (RW) | 44.8% / −0.88 / −16 | 43.7% / −1.26 / +0 | — |
| A3 mediana ponderada | 43.8% / −1.22 / −29 | 45.5% / −0.61 / +25 | ccw |
| A4 moda-12 | 46.2% / −0.36 / +4 | 46.8% / −0.16 / +42 | cw |
| A5 trimmed-mean | 38.7% / −3.07 / −100 | 39.3% / −2.86 / −61 | — |
| A6 mediana+EMA-viés | 38.6% / −3.12 / −102 | 39.4% / −2.80 / −59 | — |
| A7 Kalman 1D | 37.0% / −3.69 / −124 | 38.1% / −3.27 / −77 | — |
| A8 mediana-3 (rápida) | 44.3% / −1.04 / −22 | 44.5% / −0.97 / +11 | — |
| A9 mediana-15 (longa) | 42.1% / −1.85 / −53 | 43.4% / −1.39 / −5 | — |
| A10 moda-20 | 47.1% / −0.05 / +16 | 46.5% / −0.27 / +38 | cw |
| A11 EWMA(.1) lenta | 38.9% / −2.99 / −97 | 38.6% / −3.12 / −71 | — |
| **A12 anti-persistência** | 39.1% / −2.94 / −95 | 38.5% / −3.14 / −72 | — |
| A13 Huber | 37.0% / −3.67 / −123 | 38.2% / −3.25 / −76 | — |
| A14 midhinge (Q1+Q3)/2 | 40.0% / −2.60 / −82 | 43.4% / −1.39 / −5 | — |
| A15 moda decay-recência | 45.6% / −0.60 / −5 | 45.0% / −0.79 / +18 | cw |
| **A16 ensemble med⊕moda** | **45.6% / −0.60 / −5** | **46.9% / −0.11 / +44** | **✅ os 2** |
| A17 mediana-sessão | 42.8% / −1.59 / −43 | 41.8% / −1.94 / −26 | — |

**Engenharia reversa / leitura (rodada 2):**
- **Toda família "suavizar a média" continua mortal** (EWMA rápida/lenta, trimmed,
  Huber, Kalman, midhinge, mediana+viés): −59 a −124. Com σ≈11, puxar p/ a média
  destrói a moda local. **Vindica de novo a mediana** do pipeline atual.
- **A família "moda" lidera o saldo** (A4 +4/+42, A10 +16/+38, A16 −5/+44) — captura
  o pico recente da chegada. Mas o **EVcov segue negativo** em todas.
- 🟢 **NOVO:** **A16 (ensemble mediana-7 ⊕ moda-12) é o ÚNICO preditor que passa o
  walk-forward nos DOIS sentidos** (A4 e A10 passam só cw). É a melhor micro-evolução
  de preditor já encontrada — mas **bate o baseline sem ficar EV-positiva** (continua
  ~breakeven). Ganho real ≈ 0; serve como upgrade conservador de A0, não como alavanca.
- ❌ **Anti-persistência (A12) não funciona:** o −0.13 de autocorr é ruído fraco demais.
- **Veredito A:** preditor no teto. Se um dia mexer, troque mediana-7 → **A16**
  (ensemble), nunca por um suavizador. Prioridade baixíssima.

---

## PONTO B — Geometria / cobertura dos 17 números (18 modelos) — *a alavanca*

Preditor baseline fixo; varia COMO os 17 se distribuem. **EVcov** corrige o imposto do N.

| Modelo | N | cw hit% / **EVcov** / saldo | ccw hit% / **EVcov** / saldo | WF |
|---|---|---|---|---|
| B0 7+5+5 @10 `*` | 17 | 45.9% / −0.47 / 0 | 43.7% / −1.26 / 0 | — |
| B1 arco-8 contíguo | 17 | 44.0% / −1.14 / −26 | 46.0% / −0.45 / +31 | ccw |
| B2 7+5+5 @8 | 17 | 46.0% / −0.44 / +1 | 45.2% / −0.74 / +20 | ccw |
| B3 7+5+5 @13 | 17 | 47.4% / +0.08 / +21 | 45.2% / −0.74 / +20 | — |
| 🔴 **B4 wide-C1 (9+5+5)** | **19** | 51.7% / **−0.35** / +80 | 48.5% / **−1.37** / +66 | — |
| B5 offsets empíricos | 17 | 47.1% / −0.05 / +16 | 44.0% / −1.16 / +4 | ✅ os 2 |
| B6 raio por volatilidade | ~17 | 45.6% / −0.44 / −4 | 43.7% / −1.24 / 0 | — |
| B7 arco-8 + EMA-shift | 17 | 44.5% / −0.99 / −20 | 46.5% / −0.27 / +38 | ccw |
| B8 offsets emp. janela-90 | 17 | 47.1% / −0.05 / +16 | 44.0% / −1.16 / +4 | ✅ os 2 |
| B9 offsets emp. **KDE** | 17 | 46.9% / −0.13 / +13 | 44.2% / −1.10 / +6 | ✅ os 2 |
| B10 offsets emp. + drift | 17 | 46.0% / −0.44 / +1 | 43.8% / −1.24 / +1 | — |
| B11 top-2 picos (sinal livre) | ≤17 | 46.9% / +0.18 / +14 | 43.1% / −1.20 / −8 | cw |
| 🔴 **B12 fat-C1 (11+3+3)** | 17 | 43.8% / **−1.22** / −29 | 43.0% / **−1.52** / −10 | — |
| 🟢 **B13 fat-SAT (3+7+7)** | 17 | **48.0% / +0.29 / +29** | 45.0% / −0.82 / +17 | **✅ os 2** |
| B14 split adaptativo | 17 | 47.1% / −0.03 / +17 | 44.6% / −0.95 / +12 | ✅ os 2 |
| 🟢 **B15 offsets emp. + split** | 17 | **47.6% / +0.13 / +23** | 44.0% / −1.16 / +4 | **✅ os 2** |
| B16 offsets emp. + M5-C1 | 17 | 45.8% / −0.52 / −2 | 44.4% / −1.03 / +9 | — |
| B17 split por volatilidade | 17 | 45.8% / −0.52 / −2 | 44.5% / −0.97 / +11 | ccw |

### 🔴 Descoberta nº 1 (reconfirmada) — o imposto do N
**B4 wide-C1 (N=19)** tem o melhor hit (51.7/48.5) e o melhor saldo (+80/+66) e é o
**pior EVcov** (−0.35/−1.37). Cobrir 19 ≠ acertar mais por unidade. Miragem de novo.

### 🟢🟢 Descoberta nº 2 (NOVA, a mais importante do dia) — *mover massa do CENTRO para os SATÉLITES*
Os 3 splits de **N=17 constante** revelam um sinal **monótono e limpo**:

| reshape (mesmos 17 números) | cw EVcov | ccw EVcov | WF |
|---|---|---|---|
| **fat-C1** 11+3+3 (B12) — concentra no centro | **−1.22** (pior) | **−1.52** (pior) | ❌ |
| baseline 7+5+5 (B0) | −0.47 | −1.26 | — |
| **fat-SAT** 3+7+7 (B13) — engorda satélites | **+0.29** (melhor) | −0.82 | **✅ os 2** |

> **O centro previsto C1 NÃO é a zona modal de queda.** O erro de força é **bimodal,
> com massa nas caudas ±13–17** (já visto em `analise_12_junho.md`); é nos satélites,
> não no centro, que a bola realmente cai com mais frequência. Logo a evolução
> genérica é: **redistribuir os MESMOS 17 — tirar 4 do centro (7→3) e dar 2 a cada
> satélite (5→7).** É a forma honesta (N constante) de "acertar onde a predição erra".

### 🟢 O gate que decide — walk-forward treino→teste nos 2 sentidos
**6 geometrias** passam (B5, B8, B9, B13, B14, B15). A leitura por mérito:
- **B13 fat-SAT** — único com **EVcov cw positivo em treino E teste** (+0.10/+0.36) e
  o maior saldo entre os que passam (+29/+17). **A peça nova mais forte.**
- **B9 offsets-KDE** — a versão **robusta** de B5 (suaviza o histograma antes do pico),
  passa nos 2 sentidos, menos sensível a ruído de amostra pequena. Substitui o B5 cru.
- **B15 = offsets empíricos + split** — a **síntese** (satélites no pico de densidade
  do sentido **e** mais gordos): cw EVcov +0.13, passa nos 2. É a *regra geral adaptativa*
  de geometria operacionalizada.
- **B14 split adaptativo puro** passa, mas é **conservador demais** (rara vezes desvia
  do baseline: m2h+h2m baixíssimos) — quase todo o ganho vem do **viés fixo fat-SAT**,
  não da chave adaptativa. Lição: o sinal é "satélites gordos por padrão", e a chave por
  concentração só ajuda na margem.

**Veredito B:** a geometria é a alavanca e a rodada 2 achou um ganho **maior e mais
robusto** que o B5 da rodada 1: **fat-SAT (3+7+7) + offsets empíricos KDE por sentido**.

---

## PONTO D — Controlador adaptativo de viés (18 modelos)

Preditor + geometria baseline; varia o controlador de shift por jogada (M5 produção = D1).

| Modelo | cw hit% / saldo | ccw hit% / saldo | WF |
|---|---|---|---|
| D0 nenhum `*` | 45.9% / 0 | 43.7% / 0 | — |
| D1 M5 prod (α.2,k.5) | 46.0% / +1 | 44.4% / +9 | ccw |
| D2 M5 hot (k1) | 45.8% / −2 | 45.4% / +23 | — |
| D3 mediana-shift | 44.9% / −14 | 44.1% / +5 | ccw |
| D4 PI | 46.1% / +3 | 44.3% / +8 | — |
| D5 dual-rate EMA | 45.3% / −8 | 43.9% / +3 | — |
| D6 gated (thr 2.5) | 45.1% / −11 | 42.7% / −14 | — |
| D7 M5 warmup-2 | 46.6% / +10 | 43.8% / +1 | — |
| 🟢 **D8 M5 α=0.3** | **46.7% / +11** | **44.4% / +10** | ccw |
| D9 M5 clamp-6 | 45.8% / −1 | 44.1% / +5 | ccw |
| D10 PID | 45.8% / −2 | 45.5% / +24 | ccw |
| D11 sign-step ±1 | 46.6% / +9 | 44.1% / +5 | cw |
| D12 gated-por-confiança | 44.9% / −14 | 44.7% / +13 | ccw |
| D13 ganho assimétrico | 46.3% / +5 | 44.3% / +8 | — |
| D14 deadband ±1 | 46.0% / +1 | 44.4% / +9 | ccw |
| 🟢 **D15 K-adaptativo** | **46.9% / +14** | **44.5% / +11** | ccw |
| D16 warmup-2 + deadband | 46.6% / +10 | 43.8% / +1 | — |
| D17 ativado-por-perda | 45.9% / 0 | 43.0% / −10 | — |

**Engenharia reversa / leitura (rodada 2):**
- 🔴 **NENHUM controlador passa o walk-forward nos DOIS sentidos.** Todos que ajudam
  ccw (onde há viés real) ferem ou empatam no cw (calmo/ruidoso), e vice-versa.
  **O controlador está no teto** — confirmação dura da rodada 1.
- 🟢 **NOVO e preciso:** a alavanca não é o **ganho K**, é a **responsividade α**.
  `D2_hot` (K=1.0) destrói cw (lição da rodada 1 mantida); mas **D8 (só α 0.2→0.3,
  mesmo K e clamp) melhora os DOIS sentidos** (+11/+10, o mais equilibrado), e
  `D15 (K cresce com |viés|)` faz +14/+11. Ou seja: **a EMA do M5 está um pouco lenta;
  acelerar α é seguro, aumentar K não.**
- **Veredito D:** M5 de produção é sólido. O único micro-ajuste com lastro é
  **α 0.2 → 0.3** (D8) — em shadow, jamais aumentar o ganho/clamp.

---

## ★ A REGRA GERAL ADAPTATIVA (a resposta à pergunta central)

Cruzando os 54 cenários pela métrica do owner (**acertar onde a predição erraria,
mantendo os acertos previstos** = maximizar miss→hit e minimizar hit→miss, com EVcov
e walk-forward nos 2 sentidos), a regra que emerge **não está no preditor nem num
controlador mais agressivo** — está na **geometria**:

> **REGRA GERAL ADAPTATIVA, GENÉRICA E POR JOGADA:**
> Mantendo **os mesmos 17 números** e **um único conjunto de regras para ambos os
> sentidos**, **redistribua a cobertura para longe do centro previsto e em direção aos
> picos de densidade de erro do próprio sentido**:
> 1. **Satélites mais gordos que o centro** (3+7+7 em vez de 7+5+5) — porque a queda
>    é bimodal nas caudas, não no centro previsto. *(B13, validado WF nos 2 sentidos.)*
> 2. **Satélites posicionados no pico de densidade causal do sentido** (offsets
>    empíricos suavizados por KDE, recomputados por sessão). *(B9/B15, validado WF.)*
> 3. **C1 segue o viés via M5 já em produção** (α=0.2 mantido na regra; α=0.3 = EV-2).

Por que isto satisfaz literalmente o pedido:
- **"acerta onde a predição teria errado"** → os números antes desperdiçados no centro
  (onde a bola raramente cai) passam a cobrir as caudas (onde ela cai) → **miss→hit
  sobe** (B13: m2h 162/157).
- **"mantém os ganhos dentro do previsto"** → N permanece 17 e o centro continua
  coberto (raio 1, os 3 números mais prováveis seguem cobertos) → **hit→miss controlado**
  (B13: h2m 133/140, saldo líquido +29/+17 positivo).
- **"adaptação genérica a cada jogada, não especializada por sentido"** → é **uma só
  regra**; o que muda entre cw/ccw é só o **dado** (o histograma causal de cada
  sentido alimenta os offsets), exatamente a premissa P6+P11.

**Ranking de "regra geral" (saldo Σ 2 sentidos, agregado):** entre os que passam o
gate, **B13 fat-SAT (+46)** e **B15 offsets+split (+27)** lideram; B4 (+146) é descartado
pelo imposto do N.

---

## SÍNTESE — a ordem de alavancagem (reforçada por 54 configs)

```
GEOMETRIA (Ponto B)      >   CONTROLADOR (Ponto D)   >   PREDITOR (Ponto A)
fat-SAT + offsets-KDE        M5 (só acelerar α=0.3)      sem espaço (ensemble≈breakeven)
ganho honesto, WF 2-dir      teto: nenhum passa 2-dir     teto: só A16 passa, EV≈0
```

Quatro leis que governam QUALQUER evolução futura:
1. **Imposto do N é inviolável** (B4/N=19 reprovou de novo). Acertividade real =
   redistribuir os 17, nunca cobrir mais.
2. **Massa vai do centro para os satélites.** O centro previsto não é a zona modal;
   fat-C1 é o pior, fat-SAT é o melhor. Esta é a descoberta nova da rodada 2.
3. **Transformar erro em acerto sustentável = mover a geometria para a densidade de
   erro do sentido** (offsets empíricos KDE), não prever melhor nem reagir mais forte.
4. **Walk-forward nos 2 sentidos mata o overfit.** B3 e B4 lideram o agregado e
   reprovam; só geometria fat-SAT/offsets-empíricos generaliza.

---

## ★★ REGRA IMPLANTADA (13/06) — backtest de decisão → produção direta

O owner decidiu: **sem shadow, sem mais teste** — o backtest sobre os dados que temos
define a regra e ela entra **direto em produção**. Adicionei `run_decision` ao motor
(`scripts/evolution_sim_2026.py`): comparação **causal, por sentido, contra a aposta
REAL de hoje (P0-LIVE)** de 4 geometrias de produção.

### Backtest de decisão (agregado vs P0-LIVE + walk-forward 2 sentidos)
| Geometria de produção | N | cw EVcov | ccw EVcov | saldo cw/ccw | WF 2 sent. |
|---|---|---|---|---|---|
| P0 — 7+5+5 @10 + M5 (no ar) | 17 | −0.08 | −1.42 | 0 / 0 | — |
| P1 — fat-SAT 3+7+7 @10 + M5 | 17 | +0.23 | −0.92 | +12/+19 | só cw |
| **P2 — fat-SAT + offsets-KDE + M5** ✅ | 17 | **+0.34** | **−0.92** | **+16/+19** | **✅ os 2** |
| P3 — fat-SAT + offsets-KDE (sem M5) | 17 | +0.39 | −0.82 | +18/+23 | ✅ os 2 |

**Decisão = P2.** P3 tem saldo levemente maior mas **derrapa no cw recente** (last-50 cw
36% vs P2 40% vs P0 44%) — o M5 dá estabilidade ao cw. **P2 vira EV-positiva no cw**
(−0.08→+0.34), **melhora materialmente o ccw** (−1.42→−0.92, saldo +16/+19) e **passa
walk-forward nos DOIS sentidos** — *mantém os acertos e converte erros* (m2h>h2m em cw e ccw).

### A REGRA (no ar agora — `SDA_GEOMETRY_V2=1`, default ON)
> **A estrutura de dados das últimas jogadas de cada sentido É a regra.** A cada jogada,
> em cada sentido isolado:
> 1. **fat-SAT 3+7+7** — C1 raio 1 (3 números, os mais prováveis), C2/C3 raio 3 (7 cada).
>    Redistribui os MESMOS 17 tirando massa do centro (raro modal) p/ os satélites.
> 2. **Offsets-KDE** — satélites plantados nos **picos de densidade do histograma causal
>    de erro C1 do próprio sentido** (`_region_err_hist[dir]`, janela 60, KDE triangular).
>    Fallback ao prior (10/10) enquanto n<12 (as 2 primeiras jogadas de calibração).
> 3. **M5 C1-shift mantido** — o centro segue o viés EMA (já em produção).
> Genérica (uma regra, 2 sentidos; só o dado muda), adaptativa por jogada, **N=17 sempre**
> (INV-3, nunca fica sem aposta), e **zera no reset de dealer** (P10).

### Implementação (commitada, suíte verde 407)
- `app_config/settings.py`: `geometry_v2_enabled()` (default ON, rollback `SDA_GEOMETRY_V2=0`).
- `strategies/sda17.py`: `_geometry_radii()` (1/3/3), `_kde_offsets(dir)` (picos KDE do
  `_region_err_hist`), feed do histograma no feedback C1 (causal, **antes** do early-return
  do sigmoid — auditado linha-a-linha), reset/persistência do histograma; `analyze()` ramifica.
- `tests/conftest.py`: suite legada com `SDA_GEOMETRY_V2=0` (mantém 7+5+5 dos testes antigos).
- `tests/test_geometry_v2_12_06.py`: 9 testes (footprint 17, KDE rastreia densidade,
  fallback frio, isolamento por sentido, reset, persistência, INV-3, rollback legado).

### EV-2 — Micro-ajustes (anotados, NÃO implantados — exigiriam nova decisão)
- **Controlador:** M5 **α 0.2 → 0.3** (D8) — acelera a EMA, melhora os 2 sentidos; nunca K/clamp.
- **Preditor:** mediana-7 → **A16 ensemble** — único preditor que passa WF nos 2 sentidos; ≈breakeven.

### EV-0 — O que NÃO fazer (decidido pelos dados)
- ❌ Aumentar cobertura (N=19, B4) — imposto do N. ❌ Engordar o centro (fat-C1, B12) — pior N=17.
- ❌ Offsets fixos largos (B3 @13) — overfit. ❌ Suavizar o preditor (−59 a −124).
- ❌ Explorar autocorr negativa (A12). ❌ Controlador agressivo no GANHO (D2_hot/D6).
- ❌ Gating por perda/confiança (D17/D12) — não passam WF nos 2 sentidos.

---

## PRÓXIMOS PASSOS DA EVOLUÇÃO (pós-implantação)

1. **Deploy:** `git push` → pull-deploy auto (2 min) **com rebuild da imagem** roleta-cloud
   (mudança em `strategies/`); confirmar `SDA_GEOMETRY_V2` ON no container e o reset de
   dealer zerando `region_err_hist`. *(Push é escrita no GitHub → requer aprovação.)*
2. **Telemetria de confirmação (só observar a regra no ar):** Gauges `roleta_geometry{dir}`
   (3+7+7) e `roleta_sat_offset{dir,slot}` (offset-KDE corrente), p/ ver a densidade real
   moldando os satélites por sentido no Grafana.
3. **Acompanhar cw×ccw isolados ao vivo:** a regra deve **manter o cw (agora EV+)** e
   recuperar o ccw; se o ccw seguir difícil, é o candidato natural ao **bias físico de dealer**.
4. **EV-2 só com nova decisão do owner:** α=0.3 (D8) e A16 — cada um pelo mesmo backtest
   de decisão antes de ligar.
5. **O único caminho para EV>0 real sustentado continua sendo o viés físico de dealer
   (DEAL capture)** — ortogonal a esta geometria; exige sessão com operador.

---

## Limitações honestas
- EVcov isola a GEOMETRIA; o stack de stake (INV-3/CUT/stop-loss) fica por cima e não foi
  revalidado aqui (já validado no walk-forward de 10/06).
- A regra foi decidida por backtest **causal + walk-forward nos 2 sentidos** (não in-sample),
  mas **ccw permanece o sentido difícil** (vira ~neutro, não EV+). O cw é o ganho honesto.
- Ganhos são **modestos por natureza**: processo ~RNG; o teto da geometria é "perder menos /
  breakeven no cw", não EV>0 sustentado. **A única alavanca para EV>0 real continua sendo o
  bias físico de dealer (DEAL capture).**

## Artefatos
- `scripts/evolution_sim_2026.py` — harness reexecutável: **54 configs (18A+18B+18D)** +
  **`run_decision`** (P0..P3 vs P0-LIVE), causal, por sentido, last-50 + agregado +
  **walk-forward nos 3 pontos + decisão** + ranking de regra geral + EV coverage-aware.
- `strategies/sda17.py` + `app_config/settings.py` + `tests/test_geometry_v2_12_06.py` —
  a REGRA implantada (geometria V2 fat-SAT + offsets-KDE).
- Base: `analise_12_junho.md`, `analise_regioes_12_06.md`, grafos `graphify-out/` + `server_snapshot/`.

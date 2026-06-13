# Evolução Que Vale a Pena — 2026

> **Modo:** análise sênior de evolução de estratégia, processamento ilimitado, YOLO.
> **Método:** replay **causal** (sem look-ahead) sobre todo o histórico resolvido
> (cw=1.446 · ccw=1.436 decisões, 112 sessões cada), **por sentido isolado** (P6),
> **reset por sessão** (P10), comparando **7+ modelos genéricos em cada ponto do
> fluxo**. Métrica pedida pelo owner: matriz **miss→hit / hit→miss** vs baseline
> (transformar erros em acertos mantendo acertos) + **EV coverage-aware** (não cair
> no truque do N). Foco de leitura: **últimas 50/sentido** + agregado + **walk-forward
> treino(jan–abr)/teste(mai–jun)** como gate de promoção.
> **Motor:** `scripts/evolution_sim_2026.py` (reexecutável). Snapshot: prod 01:14 UTC.

---

## 0. O fato que governa tudo

Erro de força (real − previsto), assinado: **σ ≈ 10.8 casas em AMBOS os sentidos**
numa roda de 37. A força de chegada é **quase uniforme** — autocorrelação t−1→t ≈
−0.13 (ruído). Consequência dura, confirmada em todos os pontos abaixo:

> **Não há ganho em "prever melhor a força". O ganho, se existe, está em ONDE
> colocar os 17 números — e em capturar VIÉS episódico de posição por sentido.**

Por isso a estratégia foi decomposta em 3 alavancas e cada uma testada com 7+ modelos.

---

## PONTO A — Preditor de força / posição de C1 (7 modelos)

Geometria fixa 7+5+5 @10/10. Cada modelo prevê a força da próxima jogada a partir do
histórico de forças reais do sentido (causal). `*` = baseline em produção (mediana-7).

### Agregado (saldo = miss→hit − hit→miss; EVflat N=17)
| Modelo | cw hit% / EV / saldo | ccw hit% / EV / saldo |
|---|---|---|
| A0 mediana-7 `*` | 43.7% / −1.27 / **−31** | 44.4% / −1.01 / +8 |
| A1 EWMA(.3) | 38.4% / −3.18 / −108 | 37.8% / −3.39 / −87 |
| A2 último (RW) | 44.5% / −0.97 / −19 | 44.3% / −1.06 / +6 |
| A3 mediana ponderada | 43.6% / −1.32 / −33 | 45.8% / −0.53 / +27 |
| **A4 moda** | **45.6% / −0.57 / −3** | **46.9% / −0.13 / +43** |
| A5 trimmed-mean | 38.5% / −3.13 / −106 | 39.5% / −2.79 / −63 |
| A6 mediana+EMA-viés | 38.2% / −3.23 / −110 | 39.3% / −2.84 / −65 |
| A7 Kalman 1D | 36.9% / −3.73 / −130 | 38.6% / −3.09 / −75 |

**Engenharia reversa / leitura:**
- **Suavizadores pioram** (EWMA, trimmed, Kalman, mediana+viés): puxam a previsão para
  a média e perdem a moda local — com σ≈11 isso é mortal (−87 a −130 de saldo).
  Vindica, com número, a escolha de **mediana** em vez de média no pipeline.
- **A4 moda** é o único que melhora ligeiramente os DOIS sentidos em hit% (45.6/46.9)
  — captura o "pico" recente da força. Mas o saldo é misto (cw −3) e o EV segue
  negativo. Ganho marginal, não transformador.
- **Veredito A:** o preditor está perto do teto do possível. **Não mexer.** (A4 moda
  fica anotado como micro-otimização de baixíssima prioridade.)

---

## PONTO B — Geometria / cobertura dos 17 números (7 modelos)

Preditor baseline fixo; varia COMO os 17 números se distribuem. **EVcov = EV
coverage-aware** (normalizado a stake 17u) — corrige o "imposto do N".

### Agregado
| Modelo | N | cw hit% / **EVcov** / saldo | ccw hit% / **EVcov** / saldo |
|---|---|---|---|
| B0 7+5+5 @10 `*` | 17 | 45.9% / −0.49 / 0 | 43.9% / −1.21 / 0 |
| B1 arco-8 contíguo | 17 | 44.3% / −1.04 / −22 | 46.1% / −0.40 / +32 |
| B2 7+5+5 @8 | 17 | 45.9% / −0.49 / 0 | 45.3% / −0.68 / +21 |
| B3 7+5+5 @13 | 17 | 47.2% / −0.02 / +19 | 44.7% / −0.91 / +12 |
| **B4 wide-C1 (9+5+5)** | **19** | 51.4% / **−0.45** / +80 | 48.5% / **−1.39** / +66 |
| B5 offsets empíricos | 17 | 46.7% / −0.17 / +13 | 44.4% / −1.01 / +8 |
| B6 raio por volatilidade | ~17 | 45.6% / −0.48 / −4 | 43.9% / −1.19 / 0 |
| B7 arco-8 + EMA-shift | 17 | 44.6% / −0.94 / −18 | 46.6% / −0.23 / +39 |

### 🔴 A descoberta nº 1 — o "imposto do N" desmascara o vencedor aparente
**B4 wide-C1 tem o melhor hit% (51.4/48.5) e o melhor saldo (+80/+66) — e é o PIOR
negócio.** Ele cobre **19 números**, não 17; com EVcov (que paga 36/N) o ganho de
hits NÃO cobre o custo da cobertura extra: **EVcov −0.45/−1.39, pior ou igual ao
baseline.** É a lição do N=19 (breakeven 52.8% > hit 51.4%) **redescoberta pela
simulação**. Qualquer evolução que aumente a cobertura é miragem de EV.

### 🟢 O gate que decide — walk-forward treino→teste (EVcov, vs baseline)
| Modelo | cw treino/teste | ccw treino/teste | Passa A4? |
|---|---|---|---|
| B0 baseline | −1.52 / −0.10 | −0.56 / −1.45 | — |
| B3 @13 | −2.24 / +0.83 | −0.84 / −0.93 | ❌ (cw treino pior — **overfit ao teste**) |
| **B5 offsets empíricos** | **−0.98 / +0.14** | **−0.47 / −1.21** | ✅ **passa nos 2 sentidos** |
| B7 arco+shift | −0.35 / −1.17 | +1.00 / −0.69 | ❌ (só ccw) |
| B4 wide-C1 | −0.81 / −0.31 | −0.07 / −1.88 | ❌ |

**B3 liderava o agregado e DESPENCA no walk-forward** (cw treino −2.24 ≪ baseline
−1.52) — era artefato do período de teste. Só **B5 melhora o EVcov vs baseline em
treino E teste, nos DOIS sentidos.** Modesto, mas **consistente fora de amostra** —
a única assinatura de sinal real.

**O que é B5 (a proposta):** em vez de offsets fixos 10/10, posicionar C2/C3 nos
**picos de densidade do histograma de erros do próprio sentido** (causal, por sessão).
Os erros são bimodais com massa nas caudas ±13–17 (ver `analise_12_junho.md`); B5 põe
os satélites onde a bola REALMENTE cai naquele sentido, mantendo N=17. É **geometria
adaptativa por jogada, genérica e por sentido** — exatamente o pedido.

---

## PONTO D — Controlador adaptativo de viés (7 modelos)

Preditor + geometria baseline; varia o controlador de shift por jogada (o M5 — em
produção desde hoje — é o D1). EVflat N=17 (geometria constante → comparação justa).

### Agregado
| Modelo | cw hit% / saldo | ccw hit% / saldo |
|---|---|---|
| D0 nenhum `*` | 45.9% / 0 | 43.9% / 0 |
| D1 M5 prod (k.5) | 45.6% / −4 | 44.4% / +8 |
| D2 M5 hot (k1, a.35) | 45.6% / −3 | 45.5% / +23 |
| D3 mediana-shift | 44.7% / −16 | 43.9% / +1 |
| D4 PI (P+I) | 45.7% / −2 | 44.5% / +9 |
| D5 dual-rate EMA | 45.0% / −13 | 44.2% / +4 |
| D6 gated (thr 2.5) | 44.9% / −14 | 42.9% / −14 |
| **D7 M5-região (warmup 2)** | **46.3% / +6** | 43.9% / +1 |

**Engenharia reversa / leitura:**
- **Nas últimas 50 quase todo controlador PIORA o cw** (D1/D5/D7 cw 32%): o cw estava
  com viés pequeno/ruidoso, e corrigir ruído destrói acerto. **O controlador só ajuda
  quando há viés real** (ccw, onde D2_hot fez +23). Isso é a justificativa empírica do
  **warmup n≥3 e do clamp** que já estão no M5 de produção.
- D2_hot (mais agressivo) ganha em ccw mas é instável em cw; D6_gated piora os dois
  (limiar alto demais perde os vieses médios). **Nenhum supera o M5 de produção de
  forma robusta nos dois sentidos.**
- D7 (M5 com warmup 2) é marginalmente melhor no cw agregado (+6) — candidato a
  micro-ajuste do warmup, baixa prioridade.
- **Veredito D:** o M5 já implantado é a escolha certa e conservadora. **Não torná-lo
  mais agressivo** (D2/D6 não sobrevivem ao cw). Eventualmente testar warmup 3→2 (D7).

---

## SÍNTESE — a ordem de alavancagem e o que ela ensina

```
GEOMETRIA (Ponto B)  >  CONTROLADOR (Ponto D)  >  PREDITOR (Ponto A)
   ganho honesto B5        M5 já implantado          sem espaço (σ≈11)
```

Três leis que saíram dos números (e que devem governar QUALQUER evolução futura):

1. **Imposto do N é inviolável.** Todo ganho de hit por cobrir mais números é miragem
   de EV (B4 provou de novo). Acertividade real = **redistribuir os mesmos 17**, nunca
   adicionar.
2. **Transformar erro em acerto sustentável = mover a geometria para a densidade de
   erro do sentido**, não prever melhor a força nem reagir mais rápido. B5 (offsets
   empíricos) é a forma genérica disso.
3. **Walk-forward mata o overfit.** B3 era "o melhor" no agregado e reprovou; B5,
   modesto, é o único que generaliza. Nenhuma evolução entra em produção sem passar o
   gate nos DOIS sentidos e nos DOIS períodos.

---

## PROPOSTA DE EVOLUÇÃO (ordem de valor)

### EV-1 — Geometria de offsets empíricos por sentido (B5) — *única validada por walk-forward*
- **O quê:** substituir offsets fixos 10/10 por offsets = picos de densidade do
  histograma de erro de força do sentido (janela causal por sessão, fallback 10/10
  com n<12). Mantém N=17, raios 3/2/2.
- **Por quê:** único modelo que melhora EVcov vs baseline em treino E teste, cw E ccw.
  Captura a estrutura bimodal real da chegada de cada sentido.
- **Como (1 ponto de código):** em `_get_adaptive_offset`, quando `region_shift`
  estiver ativo, derivar off2/off3 do histograma de `dist_c1` por sentido (o estado
  `region_err_*` já coleta o insumo; falta a versão por bucket). Flag
  `REGION_OFFSETS_V1` default OFF.
- **Gate de promoção:** shadow paralelo ≥300 spins + reconfirmar walk-forward com o
  dado novo. **Ganho esperado: modesto (~+0.3–0.5u EVcov)** — não é milagre; é o teto
  honesto da geometria.

### EV-2 — Micro-ajustes de baixa prioridade (anotados, não urgentes)
- Preditor: testar **A4 moda** como alternativa à mediana-7 (hit +1–2pp, EV neutro).
- Controlador: testar **warmup 3→2** no M5 (D7, cw +6 agregado).
- Ambos só com o mesmo gate walk-forward; ganho marginal.

### EV-0 — O que NÃO fazer (decidido pelos dados, economiza semanas)
- ❌ **Aumentar a cobertura** (wide-C1/N=19) — imposto do N, EVcov negativo.
- ❌ **Offsets fixos largos (B3 @13)** — overfit, reprova no walk-forward cw.
- ❌ **Suavizar o preditor** (EWMA/Kalman/trimmed) — −87 a −130 de saldo.
- ❌ **Controlador mais agressivo** (D2_hot/D6_gated) — destrói o cw em regime calmo.
- ❌ **Momentum/AR na força** (já provado morto em `analise_12_junho.md`).

---

## Limitações honestas
- EVflat/EVcov isolam a GEOMETRIA; o stack de stake (INV-3/CUT/stop-loss) fica por
  cima e não foi revalidado aqui (já validado no walk-forward de 4131 em 10/06).
- Os 6 modelos de cada ponto são desenhados in-sample; a **execução é causal** e a
  recomendação (B5) passou treino→teste — mas merece o shadow ao vivo antes de ligar.
- Ganhos são **modestos por natureza**: o sistema opera sobre processo ~RNG; o teto
  da geometria é "perder menos / breakeven", não EV>0 sustentado. **A única alavanca
  para EV>0 real continua sendo o bias físico de dealer (DEAL capture)** — ortogonal a
  tudo deste documento.

## Artefatos
- `scripts/evolution_sim_2026.py` — harness reexecutável (24 configs, 3 pontos,
  causal, por sentido, last-50 + agregado + walk-forward, EV coverage-aware).
- Base: `analise_12_junho.md` (engenharia reversa 100/sentido + §6 modelo universal),
  `analise_regioes_12_06.md` (A1–A3), grafos `graphify-out/` + `server_snapshot/`.

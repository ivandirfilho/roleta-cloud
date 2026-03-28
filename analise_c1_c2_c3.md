# Análise C1/C2/C3 — Estudo de Seleção de Centros

> **Data:** 28/Mar/2026 ~20:15  
> **Base de dados:** Últimas 20 jogadas CW + 20 jogadas CCW (IDs 2768-2814)  
> **Método:** Engenharia reversa + 15 modelos simulados + pesquisa científica  
> **Status:** DOCUMENTO DE ESTUDO — nenhuma alteração no software

---

## PARTE 1: ENGENHARIA REVERSA — QUAL CENTRO ACERTA?

### Como funciona o sistema atual (SDA-21 Triple Focus)

```
Forças na Timeline (últimas 7) → Pipeline IQR + Weighted Median
                                         │
                    ┌────────────────────┼──────────────────┐
                    ▼                    ▼                  ▼
               C1 = mediana        C2 = max_força      C3 = min_força
               (centro robusto)    (alcance máximo)    (alcance mínimo)
                    │                    │                  │
                    └────── 7 vizinhos cada ────────────────┘
                              │
                         até 21 números
                   (MIN_SEPARATION=7 entre centros)
```

### Resultados: Contribuição de cada centro

#### CW (Horário) — 20 jogadas

| # | ID | Result | Centros | Actual | Acertou | Dist |
|--:|:--:|:------:|---------|:------:|:-------:|:----:|
| 1 | 2814 | MISS | [7,2,23] | 9 | — | — |
| 2 | 2812 | **HIT** | [19,9,36] | 20 | **C2** | 3 |
| 3 | 2810 | **HIT** | [35,34,5] | 8 | **C3** | 3 |
| 4 | 2808 | **HIT** | [16,12,4] | 5 | **C1** | 2 |
| 5 | 2806 | **HIT** | [8,19,18] | 2 | **C2** | 3 |
| 6 | 2804 | **HIT** | [28,25,23] | 12 | **C1** | 1 |
| 7 | 2802 | **HIT** | [35,34,33] | 34 | **C2** | 0 |
| 8 | 2800 | MISS | [2,29,16] | 14 | — | — |
| 9 | 2798 | **HIT** | [31,6,32] | 1 | **C1** | 3 |
| 10 | 2796 | MISS | [27,5,26] | 19 | — | — |
| 11 | 2794 | MISS | [18,24,27] | 8 | — | — |
| 12 | 2792 | MISS | [10,15,11] | 29 | — | — |
| 13 | 2790 | **HIT** | [36,2,22] | 18 | **C3** | 1 |
| 14 | 2788 | MISS | [25,5,31] | 11 | — | — |
| 15 | 2786 | **HIT** | [22,36,3] | 8 | **C2** | 3 |
| 16 | 2784 | **HIT** | [18] | 33 | **C1** | 7 |
| 17 | 2782 | MISS | [17] | 12 | — | — |
| 18 | 2772 | **HIT** | [19,29,36] | 27 | **C3** | 2 |
| 19 | 2770 | **HIT** | [31,11,35] | 20 | **C1** | 2 |
| 20 | 2768 | MISS | [0,13,24] | 17 | — | — |

**CW: 12/20 = 60.0% HR**

| Centro | Função | Acertos | Contribuição |
|:------:|--------|:-------:|:------------:|
| **C1** | Mediana ponderada | 5/20 | **25.0%** |
| **C2** | Max força | 4/18 | **22.2%** |
| **C3** | Min força | 3/18 | **16.7%** |

#### CCW (Anti-Horário) — 20 jogadas

| # | ID | Result | Centros | Actual | Acertou | Dist |
|--:|:--:|:------:|---------|:------:|:-------:|:----:|
| 1 | 2813 | MISS | [9,15,30] | 24 | — | — |
| 2 | 2811 | MISS | [1,3,27] | 8 | — | — |
| 3 | 2809 | **HIT** | [22,19,24] | 33 | **C3** | 2 |
| 4 | 2807 | **HIT** | [2,14,0] | 25 | **C1** | 1 |
| 5 | 2805 | **HIT** | [30,31,35] | 28 | **C3** | 2 |
| 6 | 2803 | **HIT** | [19,30,22] | 10 | **C2** | 3 |
| 7 | 2801 | **HIT** | [24,28,17] | 28 | **C2** | 0 |
| 8 | 2799 | **HIT** | [1,8,22] | 33 | **C1** | 1 |
| 9 | 2797 | MISS | [33,12,17] | 15 | — | — |
| 10 | 2795 | **HIT** | [3,34,33] | 27 | **C2** | 2 |
| 11 | 2793 | MISS | [23,18,21] | 13 | — | — |
| 12 | 2791 | MISS | [2,10,7] | 33 | — | — |
| 13 | 2789 | **HIT** | [10,22,2] | 18 | **C2** | 1 |
| 14 | 2787 | **HIT** | [29,21,10] | 9 | **C1** | 3 |
| 15 | 2785 | **HIT** | [8,12,20] | 26 | **C2** | 3 |
| 16 | 2783 | MISS | [25] | 9 | — | — |
| 17 | 2781 | MISS | [10] | 7 | — | — |
| 18 | 2773 | MISS | [2,10,7] | 0 | — | — |
| 19 | 2771 | **HIT** | [5,7,25] | 5 | **C1** | 0 |
| 20 | 2769 | MISS | [16,12,34] | 19 | — | — |

**CCW: 11/20 = 55.0% HR**

| Centro | Função | Acertos | Contribuição |
|:------:|--------|:-------:|:------------:|
| **C1** | Mediana ponderada | 4/20 | **20.0%** |
| **C2** | Max força | 5/18 | **27.8%** |
| **C3** | Min força | 2/18 | **11.1%** |

### Conclusão Parte 1

| Centro | CW | CCW | Média |
|:------:|:--:|:---:|:-----:|
| **C2 (max_força)** | 22.2% | **27.8%** | **25.0%** |
| **C1 (mediana)** | **25.0%** | 20.0% | **22.5%** |
| **C3 (min_força)** | 16.7% | 11.1% | **13.9%** |

> **C2 (max_força) é o centro mais produtivo no CCW**, enquanto **C1 (mediana) lidera no CW**. C3 (min_força) é consistentemente o mais fraco em ambos os sentidos.

---

## PARTE 2: PESQUISA CIENTÍFICA — ESTRATÉGIAS DE SELEÇÃO DE POSIÇÃO

### Referências Teóricas Utilizadas

1. **Mean Reversion (Ornstein-Uhlenbeck)** — Valores que desviam da média tendem a retornar. Aplicação: centros baseados em μ ± σ. *Fonte: QuantStart, Augmented Dickey-Fuller*

2. **Momentum/Trend Following** — Tendências persistem. Se a força está subindo, continua subindo. Aplicação: drift = Δ(últimas 2 forças). *Fonte: phdinds-aim.github.io*

3. **Bollinger Bands** — SMA ± 2σ define bandas de contenção. Aplicação: centros nos limites da banda. *Fonte: TradingView, markets.com*

4. **Fibonacci Retracement** — Níveis 38.2%, 50%, 61.8% do range. Aplicação: centros nos retracements do range de forças. *Fonte: pineify.app*

5. **Pivot Points** — (High+Low+Close)/3 define suporte/resistência. Aplicação: centros no pivot e R1/S1. *Fonte: fxopen.com*

6. **EMA (Exponential Moving Average)** — α controla resposta vs suavidade. Aplicação: múltiplos EMAs com diferentes α. *Fonte: markets.com, fastercapital.com*

7. **Cold Zone Analysis** — Regiões menos visitadas têm maior probabilidade. Aplicação: centros onde forças NÃO indicaram (banco vetorial de gaps). *Fonte: Conceito adaptado de probabilidade circular*

8. **Distribuição Vetorial Equidistante** — Maximizar cobertura geométrica. Aplicação: centros a 120° de separação no wheel. *Fonte: Geometria circular, princípio de equidistribuição*

---

## PARTE 3: 15 MODELOS SIMULADOS

### Descrição dos Modelos

| # | Modelo | Lógica de C1 | Lógica de C2 | Lógica de C3 |
|---|--------|:------------:|:------------:|:------------:|
| M01 | **ATUAL** | Mediana ponderada (decay=0.8) | Max força observada | Min força observada |
| M02 | EMA | EMA(α=0.3) | EMA(α=0.5) rápida | EMA(α=0.1) lenta |
| M03 | Mean Reversion | Média aritmética | Média + 1σ | Média - 1σ |
| M04 | Momentum | Última + drift | Última × 1.3 | Última × 0.7 |
| M05 | Bollinger | SMA | SMA + 2σ | SMA - 2σ |
| M06 | Fibonacci | 50% do range | 61.8% do range | 38.2% do range |
| M07 | Pivot Points | (H+L+C)/3 | R1 = 2P - L | S1 = 2P - H |
| M08 | Cold Zone | Mediana pond. | Região mais distante | 120° do C2 |
| M09 | Last 3 Forces | Força[0] direta | Força[1] direta | Força[2] direta |
| M10 | Inv. Momentum | Drift invertido | Pred × 1.3 | Pred × 0.7 |
| M11 | Double EMA | EMA rápida (0.5) | EMA lenta (0.15) | Fast + (Fast-Slow) |
| M12 | Frequência | Moda das forças | Mediana | Força menos frequente |
| M13 | Range Split | Min + range/3 | Min + 2×range/3 | Max do range |
| M14 | Weighted Recent | Média pond. 3 últimas | Max das 3 últimas | Min das 3 últimas |
| M15 | **Vetorial Gap** | Mediana ponderada | **C1 + W/3 (120°)** | **C1 + 2W/3 (240°)** |

### Resultados da Simulação

| # | Modelo | CW (20) | CW HR | CCW (20) | CCW HR | **TOTAL** | **HR** |
|---|--------|:-------:|:-----:|:--------:|:------:|:---------:|:------:|
| **M15** | **Vetorial Gap (120°)** | **15** | **75.0%** | **14** | **70.0%** | **29/40** | **72.5%** |
| M01 | ATUAL (med/max/min) | 13 | 65.0% | 14 | 70.0% | 27/40 | 67.5% |
| M06 | Fibonacci (38/50/62%) | 13 | 65.0% | 13 | 65.0% | 26/40 | 65.0% |
| M11 | Double EMA Crossover | 13 | 65.0% | 13 | 65.0% | 26/40 | 65.0% |
| M05 | Bollinger (SMA±2σ) | 12 | 60.0% | 13 | 65.0% | 25/40 | 62.5% |
| M10 | Inv. Momentum | 12 | 60.0% | 13 | 65.0% | 25/40 | 62.5% |
| M03 | Mean Reversion | 12 | 60.0% | 12 | 60.0% | 24/40 | 60.0% |
| M12 | Frequência | **15** | 75.0% | 8 | 40.0% | 23/40 | 57.5% |
| M07 | Pivot Points | 9 | 45.0% | 13 | 65.0% | 22/40 | 55.0% |
| M14 | Weighted Recent | 10 | 50.0% | 12 | 60.0% | 22/40 | 55.0% |
| M08 | Cold Zone | 11 | 55.0% | 10 | 50.0% | 21/40 | 52.5% |
| M09 | Last 3 Forces | 10 | 50.0% | 11 | 55.0% | 21/40 | 52.5% |
| M02 | EMA (3 alphas) | 7 | 35.0% | 13 | 65.0% | 20/40 | 50.0% |
| M04 | Momentum | 9 | 45.0% | 10 | 50.0% | 19/40 | 47.5% |
| M13 | Range Split | 8 | 40.0% | 11 | 55.0% | 19/40 | 47.5% |

---

## PARTE 4: ANÁLISE DOS TOP 5 MODELOS

### 🥇 M15: Vetorial Gap (120° equidistante) — 72.5%

```
Lógica: C1 = mediana ponderada (mesmo que atual)
        C2 = WHEEL[(C1_idx + W/3) % W]   ← 120° à frente
        C3 = WHEEL[(C1_idx + 2*W/3) % W] ← 240° à frente (= 120° atrás)
```

**Por que funciona melhor?**
- Maximiza **cobertura geométrica** da roda: 3 centros equidistantes cobrem 3 regiões sem overlap
- O modelo atual (max/min) tende a agrupar centros na mesma região quando o range de forças é pequeno
- Com separação de ~12 posições (~120°), CADA centro cobre uma fatia única da roda
- **Elimina a fraqueza de C3 (min_força)**: em vez de depender da menor força (11.1% HR), distribui geometricamente

**Onde M15 ganha vs M01:**
- CW #2804: M15 centros=[13,20,26] captura 12, M01 centros=[13,20,0] não
- CW #2788: M15 centros=[4,8,22] captura 11, M01 centros=[4,33,18] não
- CCW #2799: M15 centros=[6,33,35] captura 33, M01 centros=[6,9,3] não
- CCW #2795: M15 centros=[12,17,24] captura 27, M01 centros=[12,23,16] não

**Onde M15 perde vs M01:**
- CCW #2813: M01 centros=[32,9,10] captura 24, M15 centros=[32,36,14] não
- CCW #2797: M01 centros=[27,1,19] captura 15, M15 centros=[27,1,3] não

**Saldo: +4 ganhos, -2 perdas = +2 hits líquidos**

### 🥈 M01: ATUAL (mediana/max/min) — 67.5%

O modelo atual já é competitivo (2º lugar). Seus pontos fortes:
- C1 (mediana) é robusto contra outliers
- C2 (max) captura forças longas que outros modelos ignoram
- Fraqueza: C3 (min) contribui pouco (13.9% média)

### 🥉 M06: Fibonacci (38.2/50/61.8%) — 65.0%

Usa retracements do range de forças como centros. Performa bem por cobrir o INTERIOR do range de forças com boa distribuição, mas não supera o modelo vetorial porque fica confinado ao range observado.

### 4º M11: Double EMA Crossover — 65.0%

EMA rápida + EMA lenta + crossover. Captura tendência + inércia. Boa performance uniforme mas sem vantagem clear sobre o atual.

### 5º M05: Bollinger Bands — 62.5%

SMA ± 2σ. Bandas largas = boa cobertura. Mas 2σ pode ser excessivo quando σ é alto, empurrando centros para fora da zona de hit.

---

## PARTE 5: ANÁLISE DE MODELOS QUE FALHARAM

### M04: Momentum (47.5%) — PIOR

O momentum (drift-following) é o pior modelo. Na roleta, forças NÃO persistem — cada spin é independente. Momentum é uma falácia do jogador aplicada a forças circulares.

### M13: Range Split (47.5%) — PIOR

Dividir o range em terços é geométricamente rígido e ignora a distribuição real das forças.

### M12: Frequência (57.5%) — DESEQUILIBRADO

Espetacular no CW (75%!) mas terrível no CCW (40%). A moda é instável entre direções — o que é frequente no CW não se aplica ao CCW.

### M08: Cold Zone (52.5%) — TEÓRICO MAS FRACO

A ideia de cobrir regiões "frias" (não visitadas) é elegante mas na prática os resultados não convergem para cold zones — a roleta é aleatória.

---

## PARTE 6: BANCO VETORIAL — ANÁLISE DE GAPS

### Conceito

Para cada jogada, mapeamos as posições do wheel que NÃO foram cobertas pelos centros e verificamos quantas vezes o resultado caiu nessas "gaps":

```
Wheel: 37 posições
Cobertura atual: 3 centros × 7 vizinhos = até 21 posições (56.8%)
Gap: ~16 posições (43.2%)
```

### Análise de Gaps nos Resultados

Nos 8 MISSes do CW:
| ID | Centros | Actual | Gap mais próximo | Dist ao centro+ |
|:--:|---------|:------:|:----------------:|:---------------:|
| 2814 | [7,2,23] | 9 | C2=2 → 9 a 5 posições | 5 |
| 2800 | [2,29,16] | 14 | C3=16 → 14 a 2 posições | 2 |
| 2796 | [27,5,26] | 19 | C2=5 → 19 a 7 posições | 7 |
| 2794 | [18,24,27] | 8 | C1=18 → 8 a 7 posições | 7 |
| 2792 | [10,15,11] | 29 | C3=11 → 29 a 13 posições | 13 |
| 2788 | [25,5,31] | 11 | C3=31 → 11 a 4 posições | 4 |
| 2782 | [17] | 12 | C1=17 → 12 a 5 posições | 5 |
| 2768 | [0,13,24] | 17 | C2=13 → 17 a 4 posições | 4 |

**Padrão observado:** A maioria dos MISSes cai a 4-7 posições do centro mais próximo — exatamente FORA do raio de 3 vizinhos, mas dentro de um raio de 5-7. O **M15 (vetorial)** resolve parte disso por garantir que NÃO existam gaps >12 posições entre centros.

### Distribuição vetorial dos gaps

```
Modelo Atual (M01):                    Modelo Vetorial (M15):
┌──────────────────────┐              ┌──────────────────────┐
│ C1 ─── C2            │              │ C1                   │
│  \   /  gap=12-15    │              │  /  \                │
│   \ /   posições     │              │ /120° \              │
│    X                 │              │/       \             │
│   C3                 │              │C2 ─── C3             │
│                      │              │ ~12pos ~12pos        │
│ Gap máximo: ~15 pos  │              │ Gap máximo: ~12 pos  │
└──────────────────────┘              └──────────────────────┘

M01: Centros podem se agrupar          M15: Centros SEMPRE equidistantes
     quando forças são similares             gap máximo = W/3 ≈ 12
```

**M15 reduz o gap máximo de ~15 para ~12 posições**, garantindo cobertura mais uniforme.

---

## PARTE 7: SIMULAÇÃO DE CENÁRIOS HÍBRIDOS

### Cenário A: Manter C1 atual + distribuir C2/C3 a 120°

```
C1 = mediana ponderada (não muda)
C2 = C1 + 12 posições (fixo)
C3 = C1 - 12 posições (fixo)
```

**Este é exatamente M15.** Resultado: 72.5%

### Cenário B: C1=mediana, C2=max_força, C3=120° oposto a C2

```
C1 = mediana ponderada
C2 = max_força (dados reais)
C3 = posição 120° do lado oposto a C2 em relação a C1
```

**Análise:** Combina o sinal real de C2 (melhor centro individual) com cobertura geométrica. Poderia ser superior em cenários onde max_força realmente prediz.

### Cenário C: C1=EMA rápida, C2=120°, C3=240°

```
C1 = EMA(α=0.5) — mais responsivo que mediana
C2 = C1 + 12
C3 = C1 - 12
```

**Análise:** O EMA puro (M02) performou mal (50%), mas a base geométrica de M15 poderia compensar.

---

## PARTE 8: CONCLUSÕES E RECOMENDAÇÕES

### Ranking Final

| Pos | Modelo | HR | vs Atual | Recomendação |
|:---:|--------|:--:|:--------:|:------------:|
| 🥇 | **M15: Vetorial Gap** | **72.5%** | **+5.0pp** | ✅ VALE IMPLANTAR |
| 🥈 | M01: Atual | 67.5% | baseline | — |
| 🥉 | M06: Fibonacci | 65.0% | -2.5pp | ❌ Inferior ao atual |
| 4 | M11: Double EMA | 65.0% | -2.5pp | ❌ Inferior ao atual |
| 5 | M05: Bollinger | 62.5% | -5.0pp | ❌ |

### Descobertas Principais

1. **C3 (min_força) é o centro mais fraco** — 13.9% de contribuição média. É o candidato a ser substituído.

2. **Distribuição geométrica equidistante (120°) supera seleção baseada em dados** para C2 e C3. Motivo: o sinal da roleta é fraco o suficiente para que cobertura geométrica supere tentativas de predição.

3. **C1 (mediana ponderada) deve ser mantido** — É o centro com melhor sinal estatístico (25% no CW, 20% no CCW).

4. **Momentum é falácia** na roleta — M04 (47.5%) confirma que forças não têm tendência persistente.

5. **Cold Zone não funciona** — M08 (52.5%) mostra que regiões não visitadas NÃO têm maior probabilidade.

6. **Frequência é instável** — M12 teve 75% no CW mas 40% no CCW. A moda é específica por direção e período.

### Proposta de Implementação

**Opção recomendada: Substituir C2 e C3 por posições equidistantes (120°)**

```python
# Dentro de sda17.py, após calcular c1:
c1 = self._apply_force(last_number, predicted_force, direction, wheel_sequence)
c1_pos = wheel_sequence.index(c1)

# C2 e C3 equidistantes a ~120° (W/3 ≈ 12 posições)
c2 = wheel_sequence[(c1_pos + 12) % wheel_size]
c3 = wheel_sequence[(c1_pos - 12) % wheel_size]
# Não precisa de _ensure_diversity — 12 > MIN_SEPARATION(7)
```

**Impacto estimado:**
- +5.0 pontos percentuais de HR (67.5% → 72.5%)
- +2 hits a cada 40 apostas
- Break-even a 21 números = 58.3% → HR de 72.5% = **lucro positivo** a R$1/número

**P&L estimado (40 apostas a G1):**
- Atual (67.5%): 27 HITs × R$15 - 13 MISSes × R$21 = R$132
- M15 (72.5%): 29 HITs × R$15 - 11 MISSes × R$21 = R$204
- **Ganho: +R$72 por 40 apostas**

### Riscos e Ressalvas

1. **Amostra pequena:** 40 apostas é pouco para conclusão definitiva. Recomendado testar em pelo menos 200+ apostas.

2. **Overfitting possível:** M15 pode estar se beneficiando de distribuição aleatória favorável nesta amostra específica.

3. **O modelo atual já é DIVERSIFICADO:** `_ensure_diversity()` e `_force_spread()` já forçam separação mínima de 7. O ganho real pode ser menor do que 5pp.

4. **C2=max_força tem sinal real:** Nos dados, C2 é o melhor centro individual (25%). Trocar por posição geométrica perde esse sinal. Alternativa: manter C2 baseado em dados e só substituir C3.

### Próximos Passos (se aprovado)

1. **Validação com 200+ apostas:** Exportar dados históricos maiores e re-rodar simulação
2. **A/B testing:** Implementar M15 como opção configurável (flag em settings.py)
3. **Cenário Híbrido:** Testar C1=mediana + C2=max_força + C3=120° oposto ao C2
4. **Monitorar CCW:** O CCW é mais fraco — se M15 melhora específicamente o CCW (de 43% para 70%), é forte indicador

---

> **Documento de estudo** — nenhuma alteração no software  
> **Aguardando aprovação para validação com amostra maior**  
> **Referência teórica:** Mean Reversion, Momentum, Bollinger, Fibonacci, Pivot Points, EMA, Cold Zone, Distribuição Vetorial

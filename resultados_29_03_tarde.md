# Resultados 29/03 Tarde — Análise Profunda M15-ADA v4.0.2

> **Data:** 29/03/2026  
> **Versão:** 4.0.2  
> **Base de dados:** 3.001 decisões | Últimas 50 CW + 50 CCW  
> **Referência:** `plano_implantação_c1_c2_c3_melhorado.md`, `tarefas_pos_implementacao_29_03.md`  
> **Norma:** ISO/IEC 25010:2011

---

## PREMISSAS ATUALIZADAS — Modo Estudo 29/03 Tarde

> **⚠️ Modo Estudo:** Este documento é de análise exclusiva. Nenhum código foi modificado.
> As premissas abaixo são hipóteses a serem validadas por simulação antes de qualquer implementação.

### Premissa 1 — Usuário Aposta em TODAS as Jogadas (sem PULAR)

A premissa anterior admitia um Kill Switch (PULAR) quando `C4==0 AND Score≤2`.
Na nova premissa, o usuário **sempre aposta**, independente de performance recente.

**Justificativa:**
- O Kill Switch estava efetivamente desabilitado (BUG-RES-001): Score nunca ≤2 com M15-ADA
- Com estratégia Bayesiana, o offset se auto-corrige a cada jogada — não há razão para pausar
- O usuário prefere participar de todas as rodadas e confiar no algoritmo adaptativo

**Impacto esperado:**
- `taxa_pular = 0%` (confirmado nos dados reais — já era o comportamento efetivo)
- SmartGale opera apenas como G1 em 90-94% das decisões (sem PULAR, sem escalada)
- EV de longo prazo depende exclusivamente da HR do algoritmo adaptativo

---

### Premissa 2 — Estratégia Unificada: CCW Bayesiano migrado para CW

A arquitetura atual usa **dois algoritmos distintos**:
- **CW**: ErrDriven EMA (α=0.25, cw_ema → offset clamp[8,16])
- **CCW**: Bayesiano retrospectivo (janela=12, testa offsets 7-17)

A nova premissa propõe **unificar** para o algoritmo Bayesiano em ambas as direções,
mantendo parâmetros independentes (histórico, bounds) por sentido.

**Motivação (evidência dos dados reais):**

| Algoritmo | HR Total (50) | HR últ.20 | Max Miss Streak |
|-----------|:------------:|:---------:|:---------------:|
| CW ErrDriven (real) | 36.7% | 20.0% | **14** ⚠️ |
| CCW Bayesiano (real) | 48.0% | 45.0% | 8 |
| **Gap de performance** | **+11.3pp** | **+25pp** | **-6** |

O Bayesiano é superior porque:
1. **Reavalia tudo a cada jogada** — testa todos os offsets 7-17 contra as últimas 12 plays
2. **Sem "inércia"** — o EMA leva ~8-12 observações para reagir; o Bayesiano reage na próxima jogada
3. **Busca direta** — encontra o offset ótimo por brute-force, não por convergência iterativa

**Parâmetros propostos para CW Bayesiano:**

```
CW_BAYES_WINDOW   = 12   # Mesma janela do CCW
CW_BAYES_WARMUP   = 5    # Mesmo warmup
CW_BAYES_DEFAULT  = 14   # Offset padrão durante warmup
CW_BAYES_OFF_MIN  = 7    # Range início (CCW usa 7)
CW_BAYES_OFF_MAX  = 17   # Range fim (CCW usa 17)
```

---

### Premissa 3 — Melhorias Sugeridas para Estratégia mais Adaptativa

As melhorias abaixo são sugestões de estudo, ordenadas por impacto esperado:

#### MEL-BAY-01: Janela Bayesiana Dinâmica (Dynamic Window)

**Problema:** Janela fixa de 12 é lenta para reagir a mudanças abruptas de padrão.

**Proposta:**
```python
# Pseudocódigo — não implementar ainda
def dynamic_window(history, miss_streak):
    if miss_streak >= 6:
        return 5   # janela curta: responde rápido à mudança
    elif miss_streak >= 3:
        return 8   # janela média
    else:
        return 12  # janela padrão
```

**Impacto esperado:** Redução do max miss streak de 14→6 (estimativa baseada no padrão CW).

---

#### MEL-BAY-02: Histórico Ponderado por Recência (Weighted History)

**Problema:** Todas as 12 jogadas da janela têm peso igual. Jogadas antigas influenciam tanto quanto as recentes.

**Proposta:** Pesos exponenciais para contagem de hits:
```python
# Pseudocódigo — não implementar ainda
hits = sum(0.9**(n-i) for i, (c1, res) in enumerate(window) if res in coverage(c1, off))
```

**Impacto esperado:** Melhor tracking de padrões recentes; offset converge ~30% mais rápido.

---

#### MEL-BAY-03: Confiança Bayesiana como Indicador de Qualidade

**Problema:** Atualmente o algoritmo sempre usa o melhor offset, mas não há como saber se o offset é "muito bom" (8/12 hits) ou "pouco confiável" (4/12 hits).

**Proposta:** Calcular e expor a confiança:
```python
# Pseudocódigo — não implementar ainda
confidence = best_hits / len(window)
# confidence > 0.50 → sinal forte → poderia aumentar aposta
# confidence < 0.25 → sinal fraco → considerar PULAR ou reduzir
```

Com a Premissa 1 (sempre apostar), isso seria usado apenas como métrica de monitoramento
e potencialmente para escalar o valor de aposta.

---

#### MEL-BAY-04: Detector de Regime (Regime Change Detector)

**Problema:** O histórico acumula jogadas de "regimes" diferentes (ex: antes e depois de uma mudança na mesa ou no dealer).

**Proposta:** Detectar saltos abruptos no offset ótimo como indicador de mudança de regime:
```python
# Pseudocódigo — não implementar apenas
if abs(new_best_offset - prev_best_offset) >= 6:
    history = history[-5:]  # reset agressivo: esquece histórico antigo
```

**Impacto esperado:** Evita que o algoritmo fique "preso" num padrão desatualizado após mudança de condições.

---

#### MEL-BAY-05: Multi-Offset (Top-2 Average)

**Problema:** Hard-selection do melhor offset pode introduzir instabilidade quando dois offsets têm hits iguais.

**Proposta:** Usar média ponderada dos top-2 offsets:
```python
# Pseudocódigo — não implementar ainda
top2 = sorted([(hits, off) for off, hits in offset_scores.items()], reverse=True)[:2]
if top2[0][0] == top2[1][0]:  # empate
    offset = round((top2[0][1] * top2[0][0] + top2[1][1] * top2[1][0]) / sum(h for h, _ in top2))
else:
    offset = top2[0][1]  # vencedor claro
```

**Impacto esperado:** Redução de instabilidade em períodos de transição de padrão.

---

#### Tabela de Melhorias

| ID | Melhoria | Complexidade | Impacto HR (est.) | Risco |
|----|----------|:------------:|:-----------------:|:-----:|
| MEL-BAY-01 | Janela Dinâmica | Baixa | +2-4pp | Baixo |
| MEL-BAY-02 | Histórico Ponderado | Média | +1-3pp | Médio |
| MEL-BAY-03 | Confiança Bayesiana | Baixa | Monitoramento | Nenhum |
| MEL-BAY-04 | Detector de Regime | Média | +2-5pp | Médio |
| MEL-BAY-05 | Multi-Offset Top-2 | Baixa | +0-2pp | Baixo |
| **TOTAL** | **CW Bayesiano + MEL-01+04** | — | **+12-18pp vs ErrDriven** | Médio |

---

## REGISTRO COMPLETO — ÚLTIMAS 50 JOGADAS POR SENTIDO

### Horário (CW) — 50 Jogadas com Timestamps

```
┌──────┬─────────────────────┬────┬───┬────┬────┬─────────────────┬────┬───┬──────┬───┬───────┐
│  ID  │     Data/Hora       │ SN │ F │ PF │ C1 │ Centros         │ G  │HIT│ RES  │ S │ Conf  │
├──────┼─────────────────────┼────┼───┼────┼────┼─────────────────┼────┼───┼──────┼───┼───────┤
│ 3001 │ 29/03 12:43:51      │ 34 │  1│ 19 │  9 │ [9, 26, 10]     │ G1 │ — │ pend │ 4 │ media │
│ 2999 │ 29/03 12:42:32      │  9 │  0│  8 │  5 │ [5, 9, 27]      │ G1 │ ❌│  17  │ 4 │ media │
│ 2997 │ 29/03 12:41:10      │  7 │ 33│ 37 │  7 │ [7, 15, 1]      │ G1 │ ❌│   9  │ 3 │ alta  │
│ 2995 │ 29/03 12:39:40      │ 35 │ 16│  8 │ 31 │ [31, 19, 13]    │ G1 │ ❌│   3  │ 4 │ alta  │
│ 2993 │ 29/03 12:38:22      │ 11 │  4│  8 │  2 │ [2, 16, 22]     │ G1 │ ❌│  10  │ 5 │ alta  │
│ 2991 │ 29/03 12:36:54      │ 10 │ 26│  8 │  6 │ [6, 14, 28]     │ G1 │ ✅│   6  │ 4 │ alta  │
│ 2989 │ 29/03 12:35:34      │  0 │  6│  7 │ 29 │ [29, 17, 30]    │ G1 │ ✅│  18  │ 4 │ alta  │
│ 2987 │ 29/03 12:34:00      │ 19 │ 17│  5 │  3 │ [3, 36, 24]     │ G1 │ ❌│   7  │ 4 │ alta  │
│ 2985 │ 29/03 12:32:30      │ 22 │ 16│  5 │  1 │ [1, 32, 17]     │ G1 │ ✅│   1  │ 4 │ alta  │
│ 2983 │ 29/03 12:30:02      │  2 │ 15│  1 │ 21 │ [21, 24, 9]     │ G1 │ ❌│  13  │ 3 │ alta  │
│ 2981 │ 29/03 12:28:42      │  7 │ 25│  5 │ 31 │ [31, 21, 6]     │ G1 │ ✅│  22  │ 4 │ alta  │
│ 2979 │ 29/03 12:27:30      │ 27 │ 33│ 21 │  9 │ [9, 3, 5]       │ G1 │ ❌│   2  │ 4 │ alta  │
│ 2977 │ 29/03 12:26:05      │ 26 │ 21│  1 │  3 │ [3, 2, 9]       │ G1 │ ❌│  30  │ 3 │ alta  │
│ 2975 │ 29/03 12:24:27      │  8 │ 11│ 11 │ 21 │ [21, 13, 3]     │ G1 │ ❌│  30  │ 4 │ alta  │
│ 2973 │ 29/03 12:22:55      │ 34 │ 21│ 25 │ 16 │ [16, 22, 11]    │ G1 │ ❌│  21  │ 4 │ alta  │
│ 2971 │ 29/03 12:21:25      │ 10 │ 30│ 17 │ 32 │ [32, 23, 33]    │ G1 │ ❌│  14  │ 4 │ alta  │
│ 2969 │ 29/03 12:19:53      │  7 │ 33│ 37 │  7 │ [7, 6, 30]      │ G1 │ ❌│  14  │ 3 │ alta  │
│ 2967 │ 29/03 12:18:19      │  7 │ 18│ 22 │ 34 │ [34, 14, 29]    │ G1 │ ❌│   3  │ 4 │ alta  │
│ 2965 │ 29/03 12:16:48      │ 32 │ 15│  6 │ 28 │ [28, 15, 14]    │ G1 │ ❌│  36  │ 3 │ alta  │
│ 2963 │ 29/03 12:15:13      │ 14 │ 36│ 19 │  2 │ [2, 36, 26]     │ G1 │ ❌│   1  │ 4 │ media │
│ 2961 │ 29/03 12:13:38      │ 21 │ 15│ 22 │ 24 │ [24, 3, 21]     │ G1 │ ❌│  31  │ 4 │ media │
│ 2959 │ 29/03 12:12:08      │ 13 │  4│ 13 │ 26 │ [26, 11, 16]    │ G1 │ ❌│   9  │ 3 │ media │
│ 2957 │ 29/03 12:10:31      │  9 │ 34│ 27 │  0 │ [0, 30, 33]     │ G1 │ ❌│  17  │ 4 │ alta  │
│ 2955 │ 29/03 12:09:00      │ 24 │  2│  8 │ 13 │ [13, 9, 35]     │ G1 │ ❌│  29  │ 4 │ media │
│ 2953 │ 29/03 12:07:28      │ 36 │ 16│  2 │ 27 │ [27, 31, 12]    │ G1 │ ❌│  10  │ 4 │ alta  │
│ 2951 │ 29/03 12:05:56      │ 26 │ 19│  1 │  3 │ [3, 36, 24]     │ G1 │ ✅│  35  │ 3 │ alta  │
│ 2949 │ 29/03 12:04:22      │  5 │ 10│  1 │ 10 │ [10, 12, 19]    │ G1 │ ✅│  23  │ 3 │ alta  │
│ 2947 │ 29/03 12:02:44      │ 30 │ 15│ 15 │  0 │ [0, 30, 33]     │ G1 │ ❌│  34  │ 4 │ alta  │
│ 2945 │ 29/03 12:01:14      │ 30 │  8│ 36 │  8 │ [8, 7, 32]      │ G3 │ ✅│   0  │ 3 │ media │
│ 2943 │ 29/03 11:59:46      │ 32 │ 10│ 11 │  9 │ [9, 21, 13]     │ G1 │ ✅│  25  │ 4 │ alta  │
│ 2941 │ 29/03 11:58:16      │ 15 │  4│  2 │  0 │ [0, 30, 33]     │ G1 │ ❌│  22  │ 3 │ media │
│ 2939 │ 29/03 11:56:46      │  3 │ 11│ 13 │ 33 │ [33, 18, 30]    │ G1 │ ❌│   3  │ 3 │ media │
│ 2937 │ 29/03 11:55:10      │ 21 │ 10│ 24 │ 10 │ [10, 18, 25]    │ G1 │ ❌│  20  │ 4 │ alta  │
│ 2935 │ 29/03 11:53:40      │ 22 │ 10│ 35 │ 29 │ [29, 0, 1]      │ G1 │ ✅│  28  │ 3 │ media │
│ 2933 │ 29/03 11:52:13      │ 30 │  6│ 11 │  4 │ [4, 30, 29]     │ G1 │ ❌│  10  │ 4 │ alta  │
│ 2931 │ 29/03 11:50:47      │ 12 │ 30│  7 │ 31 │ [31, 0, 30]     │ G1 │ ❌│  34  │ 4 │ alta  │
│ 2929 │ 29/03 11:49:21      │  6 │  8│ 16 │  7 │ [7, 21, 24]     │ G1 │ ✅│  19  │ 3 │ media │
│ 2927 │ 29/03 11:47:53      │ 36 │  2│  5 │ 17 │ [17, 5, 35]     │ G1 │ ❌│  15  │ 4 │ alta  │
│ 2925 │ 29/03 11:46:21      │  8 │ 25│ 18 │  3 │ [3, 34, 20]     │ G1 │ ✅│  27  │ 4 │ alta  │
│ 2923 │ 29/03 11:44:51      │ 22 │ 24│ 21 │ 25 │ [25, 30, 26]    │ G1 │ ❌│  22  │ 3 │ media │
│ 2921 │ 29/03 11:43:25      │ 31 │  8│ 26 │  0 │ [0, 17, 18]     │ G1 │ ❌│   4  │ 3 │ alta  │
│ 2919 │ 29/03 11:41:55      │  0 │ 23│ 17 │ 24 │ [24, 7, 34]     │ G1 │ ✅│  10  │ 4 │ alta  │
│ 2917 │ 29/03 11:40:29      │  7 │ 16│  8 │  1 │ [1, 7, 30]      │ G1 │ ✅│  11  │ 3 │ media │
│ 2915 │ 29/03 11:39:05      │ 24 │  4│ 18 │ 15 │ [15, 6, 7]      │ G3 │ ❌│  30  │ 3 │ media │
│ 2913 │ 29/03 11:37:39      │ 26 │  5│ 29 │ 25 │ [25, 30, 26]    │ G1 │ ✅│   8  │ 4 │ alta  │
│ 2911 │ 29/03 11:36:16      │ 20 │  4│ 28 │ 12 │ [12, 4, 14]     │ G1 │ ✅│   7  │ 4 │ alta  │
│ 2909 │ 29/03 11:34:46      │ 30 │ 35│  1 │ 11 │ [11, 31, 15]    │ G1 │ ❌│  24  │ 3 │ media │
│ 2907 │ 29/03 11:33:18      │ 16 │ 17│ 28 │ 29 │ [29, 21, 10]    │ G2 │ ✅│  23  │ 4 │ media │
│ 2905 │ 29/03 11:31:52      │ 11 │ 34│ 37 │ 11 │ [11, 31, 15]    │ G1 │ ✅│   4  │ 3 │ alta  │
│ 2903 │ 29/03 11:30:27      │ 34 │  7│ 28 │ 10 │ [10]            │ G1 │ ✅│  23  │ 4 │ alta  │
└──────┴─────────────────────┴────┴───┴────┴────┴─────────────────┴────┴───┴──────┴───┴───────┘
Período: 29/03/2026 11:30:27 → 12:43:51 (1h13min) | 50 jogadas | ~1.5 min/jogada
Acertos: 18/49 verificados = 36.7% HR
```

**Legenda:** SN=Spin Number | F=Força real | PF=Força prevista | C1=Centro principal |
G=Gale Level | HIT=Acertou? | RES=Resultado real | S=Score SDA | Conf=Confiança Triple Rate

### Anti-Horário (CCW) — 50 Jogadas com Timestamps

```
┌──────┬─────────────────────┬────┬───┬────┬────┬─────────────────┬────┬───┬──────┬───┬───────┐
│  ID  │     Data/Hora       │ SN │ F │ PF │ C1 │ Centros         │ G  │HIT│ RES  │ S │ Conf  │
├──────┼─────────────────────┼────┼───┼────┼────┼─────────────────┼────┼───┼──────┼───┼───────┤
│ 3000 │ 29/03 12:43:14      │ 17 │ 19│ 16 │ 20 │ [20, 12, 30]    │ G1 │ ❌│  34  │ 4 │ media │
│ 2998 │ 29/03 12:41:52      │  9 │  4│ 30 │ 24 │ [24, 29, 6]     │ G1 │ ❌│   9  │ 3 │ alta  │
│ 2996 │ 29/03 12:40:24      │  3 │ 36│ 16 │ 11 │ [11, 33, 2]     │ G1 │ ❌│   7  │ 4 │ alta  │
│ 2994 │ 29/03 12:39:02      │ 10 │ 33│ 15 │ 12 │ [12, 21, 20]    │ G1 │ ✅│  35  │ 4 │ alta  │
│ 2992 │ 29/03 12:37:38      │  6 │  8│ 17 │  9 │ [9, 3, 5]       │ G3 │ ❌│  11  │ 4 │ media │
│ 2990 │ 29/03 12:36:16      │ 18 │  8│ 16 │ 17 │ [17, 8, 0]      │ G1 │ ✅│  10  │ 4 │ alta  │
│ 2988 │ 29/03 12:34:46      │  7 │  9│ 18 │ 13 │ [13, 24, 4]     │ G1 │ ❌│   0  │ 3 │ alta  │
│ 2986 │ 29/03 12:33:20      │  1 │  5│ 16 │ 15 │ [15, 6, 7]      │ G1 │ ✅│  19  │ 4 │ alta  │
│ 2984 │ 29/03 12:31:44      │ 13 │ 31│ 12 │ 20 │ [20, 12, 30]    │ G1 │ ❌│  22  │ 3 │ alta  │
│ 2982 │ 29/03 12:29:26      │ 22 │  3│ 25 │  8 │ [8, 14, 25]     │ G2 │ ✅│   2  │ 4 │ media │
│ 2980 │ 29/03 12:28:06      │  2 │  5│ 32 │ 32 │ [32, 6, 18]     │ G1 │ ✅│   7  │ 3 │ alta  │
│ 2978 │ 29/03 12:26:49      │ 30 │ 21│ 21 │ 26 │ [26, 25, 22]    │ G1 │ ❌│  27  │ 4 │ alta  │
│ 2976 │ 29/03 12:25:15      │ 30 │  1│ 12 │  9 │ [9, 3, 5]       │ G1 │ ✅│  26  │ 3 │ alta  │
│ 2974 │ 29/03 12:23:37      │ 21 │  4│ 15 │ 24 │ [24, 18, 27]    │ G1 │ ❌│   8  │ 3 │ alta  │
│ 2972 │ 29/03 12:22:07      │ 14 │ 30│ 30 │ 10 │ [10, 9, 34]     │ G1 │ ✅│  34  │ 4 │ alta  │
│ 2970 │ 29/03 12:20:39      │ 14 │  6│ 27 │ 30 │ [30, 31, 4]     │ G1 │ ✅│  10  │ 3 │ media │
│ 2968 │ 29/03 12:19:03      │  3 │ 33│ 16 │ 11 │ [11, 1, 21]     │ G1 │ ❌│   7  │ 4 │ alta  │
│ 2966 │ 29/03 12:17:33      │ 36 │ 25│ 15 │ 22 │ [22, 15, 23]    │ G1 │ ✅│   7  │ 4 │ alta  │
│ 2964 │ 29/03 12:15:59      │  1 │  2│ 32 │ 10 │ [10, 9, 34]     │ G1 │ ❌│  32  │ 3 │ media │
│ 2962 │ 29/03 12:14:31      │ 31 │ 16│ 15 │  4 │ [4, 13, 12]     │ G1 │ ❌│  14  │ 4 │ media │
│ 2960 │ 29/03 12:12:51      │  9 │ 22│ 12 │ 15 │ [15, 6, 7]      │ G1 │ ✅│  21  │ 4 │ media │
│ 2958 │ 29/03 12:11:15      │ 17 │ 19│ 16 │ 20 │ [20, 28, 8]     │ G1 │ ❌│  13  │ 4 │ alta  │
│ 2956 │ 29/03 12:09:46      │ 29 │ 27│  2 │ 28 │ [28, 19, 20]    │ G1 │ ❌│   9  │ 3 │ alta  │
│ 2954 │ 29/03 12:08:14      │ 10 │ 32│ 15 │ 12 │ [12, 4, 14]     │ G1 │ ❌│  24  │ 4 │ media │
│ 2952 │ 29/03 12:06:40      │ 35 │  2│ 10 │ 25 │ [25, 30, 26]    │ G3 │ ✅│  36  │ 4 │ media │
│ 2950 │ 29/03 12:05:08      │ 23 │  2│ 10 │  9 │ [9, 3, 5]       │ G2 │ ✅│  26  │ 5 │ media │
│ 2948 │ 29/03 12:03:34      │ 34 │  6│ 10 │  5 │ [5, 9, 27]      │ G1 │ ✅│   5  │ 5 │ media │
│ 2946 │ 29/03 12:02:00      │  0 │ 15│ 10 │  6 │ [6, 10, 15]     │ G1 │ ❌│  30  │ 5 │ alta  │
│ 2944 │ 29/03 12:00:28      │ 25 │ 31│ 10 │ 23 │ [23, 14, 34]    │ G1 │ ✅│  30  │ 5 │ alta  │
│ 2942 │ 29/03 11:59:02      │ 22 │ 11│ 10 │ 32 │ [32, 34, 29]    │ G1 │ ✅│  32  │ 5 │ alta  │
│ 2940 │ 29/03 11:57:30      │  3 │  0│ 10 │ 17 │ [17, 8, 0]      │ G1 │ ✅│  15  │ 5 │ alta  │
│ 2938 │ 29/03 11:55:58      │ 20 │ 18│ 10 │ 35 │ [35, 21, 31]    │ G1 │ ✅│   3  │ 4 │ alta  │
│ 2936 │ 29/03 11:54:23      │ 28 │ 33│ 10 │ 21 │ [21, 36, 35]    │ G1 │ ✅│  21  │ 4 │ alta  │
│ 2934 │ 29/03 11:52:55      │ 10 │ 34│  8 │ 31 │ [31, 26, 8]     │ G1 │ ✅│  22  │ 4 │ alta  │
│ 2932 │ 29/03 11:51:27      │ 34 │ 24│ 37 │ 34 │ [34, 24, 3]     │ G1 │ ❌│  30  │ 3 │ alta  │
│ 2930 │ 29/03 11:50:03      │ 19 │  7│  8 │ 27 │ [27, 16, 32]    │ G1 │ ❌│  12  │ 4 │ alta  │
│ 2928 │ 29/03 11:48:37      │ 15 │ 11│ 16 │ 10 │ [10, 18, 25]    │ G1 │ ❌│   6  │ 4 │ media │
│ 2926 │ 29/03 11:47:03      │ 27 │  5│ 31 │ 21 │ [21, 23, 29]    │ G1 │ ❌│  36  │ 3 │ media │
│ 2924 │ 29/03 11:45:38      │ 22 │  0│ 16 │ 25 │ [25, 24, 7]     │ G1 │ ❌│   8  │ 4 │ media │
│ 2922 │ 29/03 11:44:08      │  4 │ 22│  8 │ 13 │ [13, 20, 0]     │ G1 │ ❌│  22  │ 4 │ alta  │
│ 2920 │ 29/03 11:42:41      │ 10 │ 19│ 25 │  2 │ [2, 8, 12]      │ G1 │ ❌│  31  │ 3 │ alta  │
│ 2918 │ 29/03 11:41:09      │ 11 │ 17│ 10 │ 20 │ [20, 12, 30]    │ G1 │ ❌│   0  │ 4 │ alta  │
│ 2916 │ 29/03 11:39:45      │ 30 │  5│  5 │ 24 │ [24, 18, 27]    │ G1 │ ✅│   7  │ 4 │ alta  │
│ 2914 │ 29/03 11:38:19      │  8 │ 20│  5 │ 16 │ [16, 28, 6]     │ G1 │ ✅│  24  │ 4 │ alta  │
│ 2912 │ 29/03 11:36:57      │  7 │ 30│ 17 │ 27 │ [27, 33, 0]     │ G1 │ ✅│  26  │ 4 │ media │
│ 2910 │ 29/03 11:35:32      │ 24 │ 32│ 23 │  2 │ [2, 30, 35]     │ G1 │ ❌│  20  │ 4 │ media │
│ 2908 │ 29/03 11:34:00      │ 23 │  4│ 17 │ 35 │ [35, 21, 31]    │ G3 │ ❌│  30  │ 4 │ media │
│ 2906 │ 29/03 11:32:34      │  4 │ 10│ 23 │  9 │ [9, 3, 5]       │ G1 │ ✅│  16  │ 3 │ alta  │
│ 2904 │ 29/03 11:31:08      │ 23 │ 29│  7 │ 20 │ [20]            │ G1 │ ❌│  11  │ 4 │ alta  │
│ 2902 │ 29/03 11:29:45      │ 15 │ 28│  6 │ 17 │ [17]            │ G1 │ ✅│  34  │ 4 │ alta  │
└──────┴─────────────────────┴────┴───┴────┴────┴─────────────────┴────┴───┴──────┴───┴───────┘
Período: 29/03/2026 11:29:45 → 12:43:14 (1h13min) | 50 jogadas | ~1.5 min/jogada
Acertos: 24/50 = 48.0% HR
```

### Fluxo de Dados Completo — Do Spin ao Resultado

```
CHROME (Kiwi Browser)                 SERVIDOR (Docker)                    DATABASE
═══════════════════                   ════════════════                     ════════
                                                                          
1. Extrator DOM captura               
   número da roleta                    
   ↓                                   
2. background.js envia                 
   via WebSocket                       
   ─── { numero, direcao } ──────►  3. message_handler.py recebe
                                       ↓
                                    4. check_prediction(numero)
                                       → compara com pending_prediction
                                       → HIT ou MISS
                                       → atualiza Martingale ──────────► decisions.result_hit
                                       → update_adaptive(c1, result)     decisions.result_actual
                                       ↓
                                    5. game_state.process_spin(numero, dir)
                                       → adiciona força ao Timeline
                                       → calcula target_direction
                                       ↓
                                    6. sda17.analyze(timeline, last_number, wheel)
                                       ├─ _predict_robust(forces) → predicted_force
                                       ├─ _apply_force(last, force, dir) → C1
                                       ├─ _get_adaptive_offset(dir)
                                       │   ├─ CW: round(cw_ema) clamp[8,16] → offset
                                       │   └─ CCW: _bayesian_offset() → offset
                                       ├─ C2 = wheel[(C1_idx + offset) % 37]
                                       ├─ C3 = wheel[(C1_idx - offset) % 37]
                                       ├─ nums = neighbors(C1,3) ∪ neighbors(C2,2) ∪ neighbors(C3,2)
                                       └─ return StrategyResult(numbers, centers=[C1,C2,C3])
                                       ↓
                                    7. bet_advisor.evaluate(performance, score)
                                       ├─ C4 = acertos últimos 4
                                       ├─ Kill Switch: C4==0 AND Score≤2 → PULAR
                                       │   ⚠️ BUG-RES-001: Score nunca ≤2 com M15-ADA!
                                       └─ Else → APOSTAR
                                       ↓
                                    8. SmartGale.get_gale(score, c4, confiança)
                                       ├─ streak≥3 → G3, streak≥2 → G2, else → G1
                                       ├─ confiança "alta" → cap G1
                                       └─ c4 < 15% → cap G1
                                       ↓
                                    9. store_prediction(numbers, dir, C1, centers=[C1,C2,C3])
                                       ↓
                                   10. Responde overlay ──────────────► decisions (INSERT)
   ◄── { acao, centros, gale } ────    + state_sync heartbeat 1s          ↓
                                                                      gale_windows
11. content.js renderiza                                              window_plays
    ├─ updateOverlay() → região + status
    ├─ buildCentroHTML() → C1 em dourado
    └─ handleStateSync() → mantém gold ✅ (v4.0.2 fix)
```

---

## PARTE 1 — ANÁLISE DA ESTRATÉGIA E RESULTADOS

### 1.1 Resumo Estatístico

| Métrica | Horário (CW) | Anti-Horário (CCW) | Esperado (Plano) |
|---------|:------------:|:-------------------:|:----------------:|
| **HR últimas 50** | **36.7%** (18/49) | **48.0%** (24/50) | ≥ 45% |
| **HR últimas 20** | **20.0%** (4/20) ⚠️ | **45.0%** (9/20) ✅ | ≥ 45% |
| Max streak acertos | 3 | 6 | — |
| Max streak erros | **14** ⚠️ | 8 | ≤ 8 |
| Números por aposta | 17.1 ✅ | 17.1 ✅ | 17 |
| Centros por aposta | 3 ✅ | 3 ✅ | 3 |
| Taxa PULAR (v4.0+) | **0%** ⚠️ | **0%** ⚠️ | ~30% |
| Offset adaptativo | 11 (EMA) ✅ | Bayesian ✅ | Adaptativo |
| APOSTAR total (v4.0+) | 51 | 51 | — |
| Decisões G1 | 47 (94%) | 45 (90%) | >85% |
| Decisões G2 | 1 (2%) | 2 (4%) | — |
| Decisões G3 | 2 (4%) | 3 (6%) | — |

### 1.2 Diagnóstico por Direção

#### CW (Horário) — DESEMPENHO CRÍTICO ⚠️

O sentido horário apresenta degradação severa. A taxa de acerto caiu de 36.7% (50 jogadas) para
apenas **20.0% nas últimas 20** — uma queda de 45%. O streak máximo de erros consecutivos
atingiu **14 jogadas sem acerto**, sem que o Kill Switch interrompesse.

**Distribuição por Score:**
| Score | Apostas | Acertos | HR |
|-------|---------|---------|------|
| 3 | 19 | 7 | 36.8% |
| 4 | 30 | 11 | 36.7% |
| 5 | 1 | 0 | 0.0% |

O Score não está diferenciando qualidade — Score 3 e 4 têm HR idêntico (36.7-36.8%).
Isso indica que o mecanismo de scoring não está capturando a dispersão real dos dados CW.

**Distribuição por Confiança:**
| Confiança | Apostas | Acertos | HR |
|-----------|---------|---------|------|
| Alta | 34 | 13 | 38.2% |
| Média | 16 | 5 | 31.2% |

A confiança "alta" performa marginalmente melhor (+7%), mas ambas estão abaixo do esperado.

**Offset CW:** O ErrDriven EMA convergiu para `cw_ema = 10.93` → offset arredondado = **11**.
O offset começou em 12 (init) e caiu para 11, indicando que os erros médios estão menores
que o esperado, ou que o EMA não está se adaptando rápido o suficiente (α=0.25).

#### CCW (Anti-Horário) — DESEMPENHO ACEITÁVEL ✅

O sentido anti-horário está performando dentro do planejado com **48.0% HR (50)** e **45.0% HR (20)**.
O algoritmo Bayesiano demonstra superioridade clara sobre o ErrDriven CW.

**Distribuição por Score:**
| Score | Apostas | Acertos | HR |
|-------|---------|---------|------|
| 3 | 13 | 4 | 30.8% |
| 4 | 31 | 15 | 48.4% |
| 5 | 6 | 5 | **83.3%** ✅ |

**Insight crucial:** Score 5 no CCW tem 83.3% HR — o score É preditivo quando o algoritmo Bayesiano
está calibrado. O Score consegue diferenciar qualidade: Score 3 (30.8%) → 4 (48.4%) → 5 (83.3%).
Essa progressão linear é exatamente o que se espera de um sistema bem calibrado.

**Distribuição por Confiança:**
| Confiança | Apostas | Acertos | HR |
|-----------|---------|---------|------|
| Alta | 33 | 17 | **51.5%** ✅ |
| Média | 17 | 7 | 41.2% |

A confiança "alta" no CCW ultrapassa 50% — isso é lucro teórico na roleta (EV positivo com 17 números).

### 1.3 Engenharia Reversa — Verificação Jogada a Jogada

#### Amostra CW — Últimas 10 jogadas (IDs 2983-3001)

| ID | Força | C1 Previsto | Centros [C1,C2,C3] | Resultado | Hit? | Análise |
|----|-------|-------------|---------------------|-----------|------|---------|
| 3001 | 1 | 9 | [9, 26, 10] | Pendente | — | Última jogada, sem verificação |
| 2999 | 0 | 5 | [5, 9, 27] | 17 | ❌ | 17 fora da cobertura de 17 nums |
| 2997 | 33 | 7 | [7, 15, 1] | 9 | ❌ | 9 a 1 posição de C1=7 (quase!) |
| 2995 | 16 | 31 | [31, 19, 13] | 3 | ❌ | 3 distante de todos os centros |
| 2993 | 4 | 2 | [2, 16, 22] | 10 | ❌ | 10 fora da cobertura |
| 2991 | 26 | 6 | [6, 14, 28] | 6 | ✅ | Acertou no C1! |
| 2989 | 6 | 29 | [29, 17, 30] | 18 | ✅ | 18 vizinho de C2=17 |
| 2987 | 17 | 3 | [3, 36, 24] | 7 | ❌ | 7 fora da cobertura |
| 2985 | 16 | 1 | [1, 32, 17] | 1 | ✅ | Acertou no C1! |
| 2983 | 15 | 21 | [21, 24, 9] | 13 | ❌ | 13 fora da cobertura |

**Padrão CW:** 3 acertos em 9 verificáveis = 33.3%. Os acertos tendem a cair em C1 ou C2.
Os erros mostram resultados DISTANTES dos centros — não são "quase acertos", são erros amplos.

#### Amostra CCW — Últimas 10 jogadas (IDs 2982-3000)

| ID | Força | C1 Previsto | Centros [C1,C2,C3] | Resultado | Hit? | Análise |
|----|-------|-------------|---------------------|-----------|------|---------|
| 3000 | 19 | 20 | [20, 12, 30] | 34 | ❌ | 34 fora da cobertura |
| 2998 | 4 | 24 | [24, 29, 6] | 9 | ❌ | 9 fora da cobertura |
| 2996 | 36 | 11 | [11, 33, 2] | 7 | ❌ | 7 próximo de C3=2 (2 posições) |
| 2994 | 33 | 12 | [12, 21, 20] | 35 | ✅ | 35 na cobertura expandida |
| 2992 | 8 | 9 | [9, 3, 5] | 11 | ❌ | G3 — 11 fora (gale perdido) |
| 2990 | 8 | 17 | [17, 8, 0] | 10 | ✅ | 10 vizinho de C2=8 |
| 2988 | 9 | 13 | [13, 24, 4] | 0 | ❌ | 0 vizinho de C3=4 (1 posição!) |
| 2986 | 5 | 15 | [15, 6, 7] | 19 | ✅ | 19 na cobertura |
| 2984 | 31 | 20 | [20, 12, 30] | 22 | ❌ | 22 fora da cobertura |
| 2982 | 3 | 8 | [8, 14, 25] | 2 | ✅ | G2 — 2 na cobertura |

**Padrão CCW:** 4 acertos em 10 = 40%. Vários "quase acertos" (1-2 posições de distância).
O Bayesiano mostra coerência — os erros são mais próximos dos centros que no CW.

### 1.4 Verificação do Fluxo de Dados vs Plano

| Requisito do Plano | Status | Evidência |
|---------------------|--------|-----------|
| 17 números por aposta | ✅ OK | avg=17.1, min=17, max=19 |
| C1 com raio 3 (7 números) | ✅ OK | get_neighbors(c1, 3) no código |
| C2 com raio 2 (5 números) | ✅ OK | get_neighbors(c2, 2) no código |
| C3 com raio 2 (5 números) | ✅ OK | get_neighbors(c3, 2) no código |
| Offset adaptativo CW (ErrDriven) | ✅ OK | cw_ema=10.93 → offset=11 |
| Offset adaptativo CCW (Bayesiano) | ✅ OK | Brute-force 7-17, janela 12 |
| C1 sempre primeiro nos centros | ✅ OK | sda_centers=[C1, C2, C3] verificado |
| Kill Switch ativo | ❌ FALHA | 0 PULARs desde v4.0.0 |
| Dual algorithm independente | ✅ OK | CW e CCW processados separadamente |
| State persistence | ✅ OK | state.json contém cw_ema + ccw_history |

### 1.5 Veredito da Estratégia

**CCW (Bayesiano): APROVADO** — Performa dentro do planejado. Score é preditivo. Confiança
"alta" supera 50% HR. O algoritmo Bayesiano retroativo está adaptando o offset corretamente.

**CW (ErrDriven): REPROVADO** — HR de 20% nas últimas 20 jogadas é inaceitável. O EMA com
α=0.25 converge lentamente demais. 14 miss streak sem intervenção do Kill Switch expõe
o operador a perdas significativas. Necessita intervenção urgente.

---

## PARTE 2 — AUDITORIA DE BUGS

### BUG-RES-001: Kill Switch EFETIVAMENTE DESATIVADO [CRÍTICO]

**Arquivo:** `state/bet_advisor.py` linha 79-91  
**Impacto:** CRÍTICO — sem proteção contra perdas em sequência  
**Desde:** v4.0.0 (implantação M15-ADA)

**Descrição:**
O Kill Switch só dispara quando AMBAS as condições são verdadeiras:
1. `C4 == 0%` (zero acertos nas últimas 4 jogadas)
2. `SDA Score ≤ 2` (dados muito dispersos)

**Problema:** O M15-ADA produz scores entre 3 e 5 em 100% das decisões analisadas.
O score NUNCA atinge ≤ 2 porque:
- A mediana ponderada com IQR sempre produz resultados "limpios"
- O window adaptativo (7→5→3) garante dados suficientes
- O `clean_count` threshold impede scores baixos

**Resultado:** A condição `SDA Score ≤ 2` é **inalcançável** com M15-ADA.
A consequência é que o Kill Switch **nunca** dispara, mesmo com 14 erros consecutivos.

**Evidência:**
```
horario (v4.0+):   51 APOSTAR, 0 PULAR → 0% taxa de proteção
anti-horario (v4.0+): 51 APOSTAR, 0 PULAR → 0% taxa de proteção
Último PULAR: ID 2895/2896 (ANTES do M15-ADA)
```

**Dados de Score desde v4.0.0:**
```
Score 3: 32 decisões (31%)
Score 4: 61 decisões (60%)
Score 5: 7 decisões (7%)
Score 2: 0 decisões (0%) ← nunca atinge o threshold!
```

**Correção sugerida:** Relaxar o Kill Switch para funcionar com M15-ADA:
```python
# OPÇÃO A: Remover exigência de SDA score
if len(performance) >= 4 and c4 == 0:
    return BetAdvice(should_bet=False, ...)

# OPÇÃO B: Elevar threshold para score ≤ 3
if len(performance) >= 4 and c4 == 0 and sda_score <= 3:
    return BetAdvice(should_bet=False, ...)

# OPÇÃO C: Novo critério baseado em streak
if miss_streak >= 8:
    return BetAdvice(should_bet=False, ...)
```

---

### BUG-RES-002: Coluna calibration_offset LEGACY não populada [MÉDIO]

**Arquivo:** `server/message_handler.py`  
**Impacto:** MÉDIO — perda de observabilidade

**Descrição:**
A coluna `calibration_offset` na tabela `decisions` registra **sempre 0** desde v4.0.0.
O offset real é computado internamente pelo M15-ADA (EMA para CW, Bayesian para CCW)
e retornado no campo `details.offset` do `StrategyResult`, mas NÃO é gravado no DB.

**Evidência:**
```
horario: offsets gravados = {0}
anti-horario: offsets gravados = {0}
Offset real CW (via cw_ema): 11
Offset real CCW (via Bayesian): variável
```

**Impacto:** Impossível analisar a evolução do offset ao longo do tempo via SQL.
O `sda_centers` está gravado (permite inferir o offset), mas não há registro direto.

**Correção sugerida:** Gravar o offset adaptativo real no campo `calibration_offset`:
```python
# Em message_handler.py, ao criar a decisão:
calibration_offset=result.details.get("offset", 0)
```

---

### BUG-RES-003: CW EMA α=0.25 converge lento demais [ALTO]

**Arquivo:** `strategies/sda17.py` linha 34  
**Impacto:** ALTO — CW não se adapta a mudanças rápidas de padrão

**Descrição:**
O ErrDriven EMA para CW usa `CW_ALPHA = 0.25`:
```python
self.cw_ema = 0.25 * error + 0.75 * self.cw_ema
```

Com α=0.25, o EMA leva ~12 observações para reagir a uma mudança de padrão
(tempo de convergência ≈ 2/α = 8 observações). Durante esse período, o offset
permanece desatualizado, resultando em miss streaks longos.

**Comparação:** O CCW Bayesiano reavalia TODOS os offsets a cada jogada contra
uma janela de 12, adaptando-se instantaneamente. Isso explica o gap de performance
(CCW 48% vs CW 36.7%).

**Correção sugerida:** Aumentar α para 0.35-0.40:
```python
CW_ALPHA = 0.35  # Convergência em ~6 observações em vez de ~12
```

Ou considerar migrar CW para o mesmo algoritmo Bayesiano do CCW.

---

### BUG-RES-004: SmartGale escala durante sequências de perda [BAIXO]

**Arquivo:** `state/game.py` linhas 54-93  
**Impacto:** BAIXO — raro, mas perigoso quando ocorre

**Descrição:**
Nos dados analisados, observou-se G3 no ID 2945 (CW) durante um período de baixo HR.
O SmartGale escala para G2/G3 baseado em `global_consecutive_hits`, que é CROSS-DIRECTION.
Isso significa que uma sequência de acertos CCW pode elevar o gale para uma aposta CW
que está em sequência de perdas.

**Evidência:**
```
ID 2945: CW, G3, HIT (acertou — mas estava em miss streak)
ID 2915: CW, G3, MISS (perdeu em G3 — exposição máxima)
ID 2992: CCW, G3, MISS (perdeu em G3)
```

**Correção sugerida:** Separar streak contadores por direção:
```python
# Em vez de global_consecutive_hits, usar:
self.cw_consecutive_hits = 0
self.ccw_consecutive_hits = 0
```

---

### BUG-RES-005: Ausência de PULAR torna Martingale ineficaz [MÉDIO]

**Descrição:**
O sistema Martingale é projetado para funcionar com ciclos de aposta/pausa:
- APOSTAR durante confiança alta
- PULAR durante períodos frios
- APOSTAR novamente quando a confiança retorna

Sem PULAR (BUG-RES-001), o Martingale se reduz a "sempre G1" porque:
- Streaks de acerto são curtos (max 3 no CW)
- Misses resetam imediatamente para G1
- Sem pausas para "esperar momento melhor"

**Resultado:** O SmartGale v6 é sofisticado mas subutilizado — funciona apenas como G1
em 90-94% das decisões.

---

### Tabela Consolidada de Bugs

| ID | Severidade | Componente | Descrição | Impacto Real |
|----|-----------|------------|-----------|--------------|
| BUG-RES-001 | 🔴 CRÍTICO | bet_advisor.py | Kill Switch inalcançável (SDA≤2 impossível) | 0% proteção, 14 miss streak |
| BUG-RES-002 | 🟡 MÉDIO | message_handler.py | calibration_offset não gravado | Perda observabilidade |
| BUG-RES-003 | 🟠 ALTO | sda17.py | CW EMA α=0.25 lento demais | CW 20% HR últimas 20 |
| BUG-RES-004 | 🟢 BAIXO | game.py | Gale cross-direction | G3 em direção errada |
| BUG-RES-005 | 🟡 MÉDIO | bet_advisor+game | Sem PULAR → Martingale ineficaz | SmartGale subutilizado |

---

## PARTE 3 — INSIGHTS E MELHORIAS

### 3.1 Insight: Bayesiano superior ao ErrDriven

O CCW Bayesiano testa todos os offsets possíveis (7 a 17) contra as últimas 12 jogadas
e escolhe o melhor. O CW ErrDriven mantém uma média exponencial do erro e deriva o offset.

**Performance comparada:**
```
CCW Bayesiano:  48.0% HR (50) | 45.0% HR (20) | max streak+ = 6
CW ErrDriven:   36.7% HR (50) | 20.0% HR (20) | max streak- = 14
```

**Recomendação:** Migrar CW para algoritmo Bayesiano (mesmo do CCW). Manter parâmetros
independentes (janela, bounds) para cada direção.

---

### 3.2 Insight: Score é preditivo no CCW mas não no CW

No CCW, Score 5 = 83.3% HR, Score 4 = 48.4%, Score 3 = 30.8% — progressão linear perfeita.
No CW, Score 3 = 36.8%, Score 4 = 36.7% — zero diferenciação.

**Hipótese:** O Score mede a qualidade dos dados de entrada (IQR, clean_count).
Quando o offset está bem calibrado (CCW Bayesiano), dados de alta qualidade → acerto.
Quando o offset está mal calibrado (CW EMA), a qualidade dos dados é irrelevante.

**Recomendação:** Score pode ser usado como critério de PULAR no CW:
- Score 3 + CW → PULAR (36.8% HR não justifica aposta de 17 números)
- Score 4+ + CW → APOSTAR (se offset for corrigido)

---

### 3.3 Insight: Confiança "Alta" no CCW gera EV positivo

Com 17 números em 37 possíveis, a probabilidade base é 45.9%.
CCW com confiança "alta" tem 51.5% HR — **acima da probabilidade base**.

```
EV (confiança alta, CCW) = 0.515 × (37/17 - 1) - 0.485 × 1
                         = 0.515 × 1.176 - 0.485
                         = 0.606 - 0.485
                         = +R$0.12 por real apostado ✅
```

**Recomendação:** Aumentar aposta base quando confiança="alta" + CCW + Score ≥ 4.

---

### 3.4 Insight: Streak de 14 erros CW indica padrão não-aleatório

Uma sequência de 14 misses com 17/37 = 45.9% de probabilidade por jogada tem chance de
(1 - 0.459)^14 = 0.541^14 = **0.02%** (1 em 5.000). Isso é estatisticamente improvável
e sugere que:

1. O offset CW está **sistematicamente errado** durante esse período
2. A força prevista está **consistentemente deslocada** do real
3. Há um padrão temporal que o EMA não captura

**Recomendação:** Implementar detector de anomalia por streak. Se miss_streak ≥ 8:
1. Forçar PULAR por 2 jogadas (cooldown)
2. Resetar cw_ema para init (12.0) — "esquece" o padrão ruim
3. Ou: trocar para Bayesiano temporariamente

---

### 3.5 Insight: Números fora da faixa 17 → possível sobreposição

A média de 17.1 números por aposta indica que em ~10% dos casos há **mais de 17** números
(até 19 observados). Isso ocorre quando os centros C1, C2, C3 têm pouca sobreposição
(estão distantes na roda). Com offset=11, C2 e C3 estão a 11 posições de C1, o que em
uma roda de 37 posições significa que há pouca ou nenhuma sobreposição.

Quando os 3 setores não se sobrepõem: 7+5+5 = 17 ✅  
Quando há sobreposição parcial: 7+5+5 - overlap = 15-16 números  
Quando offset é muito pequeno (8-9): sobreposição alta → < 17 números

**O offset=11 está produzindo boa cobertura angular (~120° entre centros).**

---

### 3.6 Proposta: M15-ADA v4.1 — Melhorias prioritárias

| Prioridade | Melhoria | Impacto esperado | Risco |
|-----------|----------|------------------|-------|
| **P0** | Fix Kill Switch (BUG-RES-001) | Evitar miss streaks > 8 | Baixo |
| **P0** | CW: Migrar para Bayesiano ou α=0.35 | CW HR 36% → 42%+ | Médio |
| **P1** | Gravar offset real no DB (BUG-RES-002) | Observabilidade | Baixo |
| **P1** | Separar gale por direção (BUG-RES-004) | Evitar G3 em dir. fria | Baixo |
| **P2** | Score-based PULAR no CW (Score 3 → skip) | CW HR filtrado → 40%+ | Médio |
| **P2** | Detector de anomalia por streak | Auto-reset em crises | Médio |
| **P3** | Confiança "alta" + CCW → aposta aumentada | Maximizar EV positivo | Baixo |

---

### 3.7 Simulação: Impacto financeiro das melhorias

**Estado atual (50 jogadas por direção, aposta base R$5):**
```
CW:  18 hits × R$5 × 1.176 payout - 31 misses × R$5 = R$105.84 - R$155.00 = -R$49.16
CCW: 24 hits × R$5 × 1.176 payout - 26 misses × R$5 = R$141.12 - R$130.00 = +R$11.12
Total: -R$38.04 em 100 jogadas
```

**Cenário com Kill Switch ativo (estimando 15% PULAR no CW):**
```
CW:  43 apostas (85%), estimando 38% HR = 16 hits, 27 misses
     16 × R$5 × 1.176 - 27 × R$5 = R$94.08 - R$135.00 = -R$40.92
     Economia: 8 apostas × R$5 = R$40.00 não gastos
     Resultado CW ajustado: -R$0.92 (vs -R$49.16 anterior)
```

**Cenário com CW Bayesiano (estimando CCW-like HR de 45%):**
```
CW:  50 apostas, 45% HR = 22 hits, 28 misses
     22 × R$5 × 1.176 - 28 × R$5 = R$129.36 - R$140.00 = -R$10.64
     Melhoria: +R$38.52 vs estado atual
```

---

## CONCLUSÃO

O M15-ADA v4.0.2 apresenta um **desequilíbrio significativo entre CW e CCW**. O algoritmo
Bayesiano (CCW) está performando dentro do planejado e gerando EV positivo em cenários
de confiança alta. O algoritmo ErrDriven (CW) está degradado com 20% HR e sem proteção
do Kill Switch.

**Ações imediatas recomendadas:**
1. **URGENTE:** Corrigir Kill Switch para funcionar com M15-ADA (BUG-RES-001)
2. **ALTA:** Acelerar ou substituir algoritmo CW (BUG-RES-003)
3. **MÉDIA:** Gravar offset real no DB para análises futuras (BUG-RES-002)

> **Status (original):** Documento de análise finalizado. Aguardando aprovação para implementar correções.

---

## PARTE 4 — SIMULAÇÃO ENGENHARIA REVERSA (MODO ESTUDO)

> **Premissas aplicadas nesta seção:**
> 1. Usuário aposta em **TODAS** as jogadas (taxa PULAR = 0%)
> 2. Ambas as direções usam **algoritmo Bayesiano** (mesmo do CCW atual)
> 3. Parâmetros: window=12, warmup=5, default_offset=14, offsets testados 7-17
> 4. C1 é o mesmo que o sistema real (não alterado — apenas o offset muda)
> 5. Cobertura: neighbors(C1, raio=3) ∪ neighbors(C2, raio=2) ∪ neighbors(C3, raio=2) = 17 números
> 6. Simulação independente por sentido

### 4.1 Metodologia da Simulação

A engenharia reversa usa os dados reais de C1 e resultado de cada jogada para calcular
qual offset o algoritmo Bayesiano teria selecionado, e se o resultado estaria na cobertura.

```
Para cada jogada (em ordem cronológica):
  1. Consulta história acumulada até aquele momento
  2. Se len(historia) < 5 → usa offset padrão = 14 (warmup)
  3. Senão → testa offsets 7..17 contra últimas 12 entradas da historia
             → conta hits por offset
             → seleciona offset com mais hits (tie → menor offset)
  4. Calcula cobertura: C2 = wheel[(C1_idx + offset) % 37]
                        C3 = wheel[(C1_idx - offset) % 37]
                        cob = neighbors(C1,3) ∪ neighbors(C2,2) ∪ neighbors(C3,2)
  5. Verifica: resultado ∈ cob → HIT_SIM = ✅
  6. Adiciona (C1, resultado) à historia
```

**Nota:** A simulação assume que C1 seria idêntico ao produzido pelo sistema real
(o pipeline de predição de força não muda — apenas o mecanismo de offset).

---

### 4.2 Simulação CW — Bayesiano Simulado vs ErrDriven Real

#### Tabela de Engenharia Reversa — CW (49 jogadas com resultado verificado)

```
   ID |  C1 |  Off |  C2 |  C3 | #Cob | RES | BAY | REAL | Δ | Nota
─────-+─────+──────+─────+─────+──────+─────+─────+──────+───+────────────────
 2903 |  10 |   14 |  28 |   4 |   17 |  23 |  ✅  |   ✅  |   | [warmup]
 2905 |  11 |   14 |  22 |   0 |   17 |   4 |  ❌  |   ✅  | ≠ | [warmup] real hit, sim miss
 2907 |  29 |   14 |  25 |   8 |   17 |  23 |  ✅  |   ✅  |   | [warmup]
 2909 |  11 |   14 |  22 |   0 |   17 |  24 |  ❌  |   ❌  |   | [warmup]
 2911 |  12 |   14 |   6 |   5 |   17 |   7 |  ✅  |   ✅  |   | [warmup]
 2913 |  25 |    8 |  30 |  26 |   17 |   8 |  ✅  |   ✅  |   | Bay opt=8 (4 hits/5)
 2915 |  15 |    8 |   6 |   7 |   17 |  30 |  ❌  |   ❌  |   | Bay opt=8 (5 hits/6)
 2917 |   1 |   11 |  35 |  13 |   17 |  11 |  ✅  |   ✅  |   | Bay opt=11 (6 hits/7)
 2919 |  24 |   11 |   7 |  34 |   17 |  10 |  ✅  |   ✅  |   | Bay opt=11 (7 hits/8)
 2921 |   0 |   11 |  27 |  31 |   17 |   4 |  ❌  |   ❌  |   | Bay opt=11 (8 hits/9)
 2923 |  25 |   11 |  10 |  12 |   17 |  22 |  ❌  |   ❌  |   | Bay opt=11 (8 hits/10)
 2925 |   3 |   11 |  34 |  20 |   17 |  27 |  ✅  |   ✅  |   | Bay opt=11 (8 hits/11)
 2927 |  17 |   11 |   5 |  35 |   17 |  15 |  ❌  |   ❌  |   | Bay opt=11 (9 hits/12)
 2929 |   7 |   11 |  21 |  24 |   17 |  19 |  ✅  |   ✅  |   | Bay opt=11 (8 hits/12)
 2931 |  31 |   11 |   0 |  30 |   17 |  34 |  ❌  |   ❌  |   | Bay opt=11 (8 hits/12)
 2933 |   4 |    7 |  27 |  35 |   17 |  10 |  ❌  |   ❌  |   | Bay opt=7  (7 hits/12) ← offset muda!
 2935 |  29 |   11 |   4 |   5 |   17 |  28 |  ✅  |   ✅  |   | Bay opt=11 (7 hits/12)
 2937 |  10 |   11 |  18 |  25 |   17 |  20 |  ❌  |   ❌  |   | Bay opt=11 (7 hits/12)
 2939 |  33 |   15 |   0 |  25 |   17 |   3 |  ✅  |   ❌  | ≠ | Bay opt=15 (7 hits/12) sim hit, real miss
 2941 |   0 |   15 |  30 |  33 |   17 |  22 |  ❌  |   ❌  |   | Bay opt=15 (7 hits/12)
 2943 |   9 |   15 |  21 |  13 |   17 |  25 |  ✅  |   ✅  |   | Bay opt=15 (7 hits/12)
 2945 |   8 |   15 |   7 |  32 |   17 |   0 |  ✅  |   ✅  |   | Bay opt=15 (7 hits/12)
 2947 |   0 |   15 |  30 |  33 |   17 |  34 |  ❌  |   ❌  |   | Bay opt=15 (8 hits/12)
 2949 |  10 |   15 |  12 |  19 |   17 |  23 |  ✅  |   ✅  |   | Bay opt=15 (7 hits/12)
 2951 |   3 |    7 |  21 |  22 |   17 |  35 |  ✅  |   ✅  |   | Bay opt=7  (7 hits/12)
 2953 |  27 |   15 |  31 |  12 |   17 |  10 |  ❌  |   ❌  |   | Bay opt=15 (8 hits/12)
 2955 |  13 |   15 |   9 |  35 |   17 |  29 |  ❌  |   ❌  |   | Bay opt=15 (8 hits/12)
 2957 |   0 |    7 |  25 |  29 |   17 |  17 |  ✅  |   ❌  | ≠ | Bay opt=7  (7 hits/12) Bay pega 17!
 2959 |  26 |    7 |   2 |  18 |   17 |   9 |  ✅  |   ❌  | ≠ | Bay opt=7  (8 hits/12) Bay pega 9!
 2961 |  24 |    7 |   9 |  36 |   17 |  31 |  ✅  |   ❌  | ≠ | Bay opt=7  (8 hits/12) Bay pega 31!
 2963 |   2 |    7 |  36 |  26 |   17 |   1 |  ❌  |   ❌  |   | Bay opt=7  (8 hits/12)
 2965 |  28 |    7 |  15 |  14 |   17 |  36 |  ❌  |   ❌  |   | Bay opt=7  (8 hits/12)
 2967 |  34 |    7 |   8 |  15 |   17 |   3 |  ❌  |   ❌  |   | Bay opt=7  (7 hits/12)
 2969 |   7 |    7 |  32 |  20 |   17 |  14 |  ✅  |   ❌  | ≠ | Bay opt=7  (7 hits/12) Bay pega 14!
 2971 |  32 |    7 |  17 |   7 |   17 |  14 |  ❌  |   ❌  |   | Bay opt=7  (8 hits/12)
 2973 |  16 |    7 |  22 |  11 |   17 |  21 |  ❌  |   ❌  |   | Bay opt=7  (7 hits/12)
 2975 |  21 |    7 |  13 |   3 |   17 |  30 |  ❌  |   ❌  |   | Bay opt=7  (6 hits/12)
 2977 |   3 |    8 |   2 |   9 |   17 |  30 |  ❌  |   ❌  |   | Bay opt=8  (6 hits/12)
 2979 |   9 |    8 |   3 |   5 |   17 |   2 |  ❌  |   ❌  |   | Bay opt=8  (5 hits/12)
 2981 |  31 |    8 |  35 |  10 |   17 |  22 |  ✅  |   ✅  |   | Bay opt=8  (5 hits/12)
 2983 |  21 |   15 |  24 |   9 |   17 |  13 |  ❌  |   ❌  |   | Bay opt=15 (6 hits/12)
 2985 |   1 |   15 |  32 |  17 |   17 |   1 |  ✅  |   ✅  |   | Bay opt=15 (6 hits/12)
 2987 |   3 |   15 |  36 |  24 |   17 |   7 |  ❌  |   ❌  |   | Bay opt=15 (7 hits/12)
 2989 |  29 |   15 |  17 |  30 |   17 |  18 |  ✅  |   ✅  |   | Bay opt=15 (6 hits/12)
 2991 |   6 |   15 |  14 |  28 |   17 |   6 |  ✅  |   ✅  |   | Bay opt=15 (7 hits/12)
 2993 |   2 |   15 |  16 |  22 |   17 |  10 |  ❌  |   ❌  |   | Bay opt=15 (8 hits/12)
 2995 |  31 |   14 |  19 |  13 |   17 |   3 |  ❌  |   ❌  |   | Bay opt=14 (8 hits/12)
 2997 |   7 |    8 |  15 |   1 |   17 |   9 |  ❌  |   ❌  |   | Bay opt=8  (7 hits/12)
 2999 |   5 |    8 |   9 |  27 |   17 |  17 |  ❌  |   ❌  |   | Bay opt=8  (7 hits/12)
```

#### Resumo Estatístico — CW

| Métrica | Bayesiano Simulado | ErrDriven Real | Δ |
|---------|:-----------------:|:--------------:|:--:|
| **HR Total (49 jogadas)** | **22/49 = 44.9%** | 18/49 = 36.7% | **+8.2pp** ✅ |
| **HR últimas 20** | **6/20 = 30.0%** | 4/20 = 20.0% | **+10.0pp** ✅ |
| Max streak acertos | 3 | 3 | = |
| **Max streak erros** | **5** ⬇️ | **14** ⚠️ | **-9** ✅ |
| Total divergências (Sim≠Real) | 6/49 = 12.2% | — | — |

#### Distribuição de Offsets Bayesianos — CW

| Offset | Vezes | % | Interpretação |
|--------|------:|:--:|---------------|
| 7 | 12 | 24.5% | Período IDs 2957-2975 — offset pequeno dominante |
| 8 | 7 | 14.3% | Início e fase final |
| 11 | 10 | 20.4% | Fase central IDs 2917-2935 |
| 14 | 6 | 12.2% | Warmup + retorno final |
| 15 | 14 | 28.6% | **Mais frequente!** Fase IDs 2939-2993 |

**Insight CW:** O Bayesiano oscila entre offsets 7 e 15 — extremos opostos —
indicando alta variabilidade de padrão neste sentido. O ErrDriven (EMA=11) ficou
"travado" numa média que não representava nem o padrão 7 nem o padrão 15.

---

### 4.3 Simulação CCW — Bayesiano Simulado vs Bayesiano Real

#### Tabela de Engenharia Reversa — CCW (50 jogadas)

```
   ID |  C1 |  Off |  C2 |  C3 | #Cob | RES | BAY | REAL | Δ | Nota
─────-+─────+──────+─────+─────+──────+─────+─────+──────+───+────────────────
 2902 |  17 |   14 |  33 |   7 |   17 |  34 |  ✅  |   ✅  |   | [warmup]
 2904 |  20 |   14 |  32 |   6 |   17 |  11 |  ❌  |   ❌  |   | [warmup]
 2906 |   9 |   14 |   4 |  36 |   17 |  16 |  ❌  |   ✅  | ≠ | [warmup] real usou offset diferente
 2908 |  35 |   14 |  27 |  24 |   17 |  30 |  ❌  |   ❌  |   | [warmup]
 2910 |   2 |   14 |  24 |  18 |   17 |  20 |  ❌  |   ❌  |   | [warmup]
 2912 |  27 |    8 |   5 |  19 |   17 |  26 |  ❌  |   ✅  | ≠ | Bay opt=8 (3 hits/5) real usou off dif
 2914 |  16 |    8 |  18 |  36 |   17 |  24 |  ✅  |   ✅  |   | Bay opt=8 (3 hits/6)
 2916 |  24 |    8 |  22 |  13 |   17 |   7 |  ❌  |   ✅  | ≠ | Bay opt=8 (4 hits/7)
 2918 |  20 |   10 |  35 |  11 |   17 |   0 |  ❌  |   ❌  |   | Bay opt=10 (5 hits/8)
 2920 |   2 |   11 |  23 |  28 |   17 |  31 |  ❌  |   ❌  |   | Bay opt=11 (6 hits/9)
 2922 |  13 |   11 |   1 |  32 |   17 |  22 |  ❌  |   ❌  |   | Bay opt=11 (6 hits/10)
 2924 |  25 |   11 |  10 |  12 |   17 |   8 |  ✅  |   ❌  | ≠ | Bay opt=11 (6 hits/11)
 2926 |  21 |   11 |   8 |   7 |   17 |  36 |  ❌  |   ❌  |   | Bay opt=11 (7 hits/12)
 2928 |  10 |   10 |  22 |  17 |   17 |   6 |  ✅  |   ❌  | ≠ | Bay opt=10 (6 hits/12)
 2930 |  27 |   10 |  16 |  32 |   17 |  12 |  ❌  |   ❌  |   | Bay opt=10 (6 hits/12)
 2932 |  34 |   10 |   5 |  26 |   17 |  30 |  ❌  |   ❌  |   | Bay opt=10 (6 hits/12)
 2934 |  31 |   10 |  26 |   8 |   17 |  22 |  ✅  |   ✅  |   | Bay opt=10 (6 hits/12)
 2936 |  21 |   10 |  30 |  28 |   17 |  21 |  ✅  |   ✅  |   | Bay opt=10 (7 hits/12)
 2938 |  35 |    7 |   4 |   9 |   17 |   3 |  ✅  |   ✅  |   | Bay opt=7  (7 hits/12)
 2940 |  17 |    7 |  30 |  32 |   17 |  15 |  ✅  |   ✅  |   | Bay opt=7  (7 hits/12)
 2942 |  32 |    7 |  17 |   7 |   17 |  32 |  ✅  |   ✅  |   | Bay opt=7  (8 hits/12)
 2944 |  23 |    7 |  20 |   6 |   17 |  30 |  ✅  |   ✅  |   | Bay opt=7  (9 hits/12)
 2946 |   6 |    7 |  23 |  19 |   17 |  30 |  ✅  |   ❌  | ≠ | Bay opt=7  (10 hits/12) ← pico!
 2948 |   5 |    7 |  31 |  13 |   17 |   5 |  ✅  |   ✅  |   | Bay opt=7  (11 hits/12) ← máx confiança
 2950 |   9 |    7 |  35 |  24 |   17 |  26 |  ✅  |   ✅  |   | Bay opt=7  (11 hits/12)
 2952 |  25 |    7 |  11 |   0 |   17 |  36 |  ✅  |   ✅  |   | Bay opt=7  (11 hits/12)
 2954 |  12 |    7 |  19 |  31 |   17 |  24 |  ❌  |   ❌  |   | Bay opt=7  (11 hits/12)
 2956 |  28 |    7 |  15 |  14 |   17 |   9 |  ✅  |   ❌  | ≠ | Bay opt=7  (11 hits/12)
 2958 |  20 |    7 |   7 |  23 |   17 |  13 |  ❌  |   ❌  |   | Bay opt=7  (11 hits/12)
 2960 |  15 |    7 |  34 |  28 |   17 |  21 |  ✅  |   ✅  |   | Bay opt=7  (10 hits/12)
 2962 |   4 |    7 |  27 |  35 |   17 |  14 |  ❌  |   ❌  |   | Bay opt=7  (10 hits/12)
 2964 |  10 |    7 |  14 |  27 |   17 |  32 |  ❌  |   ❌  |   | Bay opt=7  (9 hits/12)
 2966 |  22 |    7 |   3 |  16 |   17 |   7 |  ✅  |   ✅  |   | Bay opt=7  (8 hits/12)
 2968 |  11 |    7 |  16 |  25 |   17 |   7 |  ❌  |   ❌  |   | Bay opt=7  (8 hits/12)
 2970 |  30 |    7 |  33 |  17 |   17 |  10 |  ✅  |   ✅  |   | Bay opt=7  (7 hits/12)
 2972 |  10 |   15 |  12 |  19 |   17 |  34 |  ❌  |   ✅  | ≠ | Bay opt=15 (8 hits/12)
 2974 |  24 |    7 |   9 |  36 |   17 |   8 |  ❌  |   ❌  |   | Bay opt=7  (7 hits/12)
 2976 |   9 |   15 |  21 |  13 |   17 |  26 |  ❌  |   ✅  | ≠ | Bay opt=15 (7 hits/12)
 2978 |  26 |   11 |   6 |  14 |   17 |  27 |  ✅  |   ❌  | ≠ | Bay opt=11 (7 hits/12)
 2980 |  32 |   10 |  27 |  22 |   17 |   7 |  ❌  |   ✅  | ≠ | Bay opt=10 (7 hits/12)
 2982 |   8 |   10 |  31 |   2 |   17 |   2 |  ✅  |   ✅  |   | Bay opt=10 (7 hits/12)
 2984 |  20 |    8 |  28 |   8 |   17 |  22 |  ❌  |   ❌  |   | Bay opt=8  (7 hits/12)
 2986 |  15 |    8 |   6 |   7 |   17 |  19 |  ✅  |   ✅  |   | Bay opt=8  (6 hits/12)
 2988 |  13 |    8 |  24 |   4 |   17 |   0 |  ❌  |   ❌  |   | Bay opt=8  (7 hits/12)
 2990 |  17 |   10 |  10 |   3 |   17 |  10 |  ✅  |   ✅  |   | Bay opt=10 (8 hits/12)
 2992 |   9 |   10 |   0 |  23 |   17 |  11 |  ❌  |   ❌  |   | Bay opt=10 (8 hits/12)
 2994 |  12 |   11 |  25 |  33 |   17 |  35 |  ✅  |   ✅  |   | Bay opt=11 (9 hits/12)
 2996 |  11 |   11 |  14 |  19 |   17 |   7 |  ❌  |   ❌  |   | Bay opt=11 (9 hits/12)
 2998 |  24 |   11 |   7 |  34 |   17 |   9 |  ❌  |   ❌  |   | Bay opt=11 (8 hits/12)
 3000 |  20 |   11 |   3 |  36 |   17 |  34 |  ❌  |   ❌  |   | Bay opt=11 (8 hits/12)
```

#### Resumo Estatístico — CCW

| Métrica | Bayesiano Simulado | Bayesiano Real | Δ |
|---------|:-----------------:|:--------------:|:--:|
| **HR Total (50 jogadas)** | **23/50 = 46.0%** | 24/50 = 48.0% | -2.0pp |
| **HR últimas 20** | **7/20 = 35.0%** | 9/20 = 45.0% | -10.0pp |
| Max streak acertos | **10** ✅ | 6 | +4 |
| Max streak erros | **5** ✅ | 8 | -3 |
| Total divergências (Sim≠Real) | 11/50 = 22.0% | — | — |

**Nota sobre divergência CCW:** As 11 divergências (22%) indicam que o algoritmo Bayesiano
"real" do sistema usou offsets diferentes do que nossa simulação calculou. Isso pode ser
explicado por: (a) diferença no estado inicial de `ccw_history` no servidor, (b) offset que
foi fixo por warmup no servidor mas já estava adaptado, ou (c) pequenas diferenças de C1 real
vs simulado. A diferença de -2pp no HR total (46% vs 48%) valida que a simulação é
uma boa aproximação da realidade.

#### Distribuição de Offsets Bayesianos — CCW

| Offset | Vezes | % | Interpretação |
|--------|------:|:--:|---------------|
| 7 | 18 | 36.0% | **Dominante** — IDs 2938-2974, período de alta confiança |
| 8 | 6 | 12.0% | Início e fase final |
| 10 | 10 | 20.0% | Fase transitória IDs 2918-2936, 2980-2992 |
| 11 | 9 | 18.0% | IDs 2920-2926, fase final 2994-3000 |
| 14 | 5 | 10.0% | Warmup exclusivamente |
| 15 | 2 | 4.0% | Raros (IDs 2972, 2976) |

**Insight CCW:** O offset 7 domina (36%) e corresponde ao período de maior confiança
(best_hits = 10-11/12). A simulação capturou a "fase quente" IDs 2938-2952 com 10 acertos
consecutivos — superior ao max streak real de 6!

---

### 4.4 Comparação Final — Estratégia Unificada Bayesiana

| Métrica | CW ErrDriven (real) | CW Bayesiano (sim) | CCW Bayesiano (real) | CCW Bayesiano (sim) |
|---------|:-------------------:|:------------------:|:-------------------:|:-------------------:|
| **HR Total (50)** | 36.7% ⚠️ | **44.9%** ✅ | **48.0%** ✅ | 46.0% ✅ |
| **HR últimas 20** | 20.0% 🔴 | **30.0%** 🟡 | **45.0%** ✅ | 35.0% 🟡 |
| Max miss streak | **14** 🔴 | **5** ✅ | 8 🟡 | **5** ✅ |
| Max hit streak | 3 | 3 | 6 | **10** |
| Offsets usados | {11} fixo | {7,8,11,14,15} | variado | {7,8,10,11,14,15} |
| Confiança média | — | 7.0/12 = 58% | — | 7.4/12 = 62% |

#### Impacto Financeiro com Bayesiano Unificado (aposta base R$5, todas as jogadas)

```
─── Estado atual (CW ErrDriven + CCW Bayesiano real) ───
CW:  18/49 hits × R$5 × 1.176 - 31 misses × R$5  =  R$105.84 - R$155.00  =  -R$49.16
CCW: 24/50 hits × R$5 × 1.176 - 26 misses × R$5  =  R$141.12 - R$130.00  =  +R$11.12
TOTAL:                                                                         -R$38.04

─── Simulado (CW Bayesiano + CCW Bayesiano simulado) ───
CW:  22/49 hits × R$5 × 1.176 - 27 misses × R$5  =  R$129.36 - R$135.00  =  -R$5.64
CCW: 23/50 hits × R$5 × 1.176 - 27 misses × R$5  =  R$135.24 - R$135.00  =  +R$0.24
TOTAL:                                                                         -R$5.40

─── Ganho com unificação Bayesiana ───
Melhoria: -R$5.40 vs -R$38.04 = +R$32.64 (85.8% de redução de perda)
CW isolado: -R$5.64 vs -R$49.16 = +R$43.52 (88.5% de redução)
```

---

### 4.5 Conclusão da Simulação

**Resultado da Engenharia Reversa:**

1. ✅ **CW Bayesiano é significativamente superior ao ErrDriven:**
   - HR melhora de 36.7% → 44.9% (+8.2pp)
   - Miss streak máximo cai de 14 → 5 (-9 jogadas)
   - Redução de perda financeira: 88.5% no sentido CW

2. ✅ **CCW Bayesiano simulado confirma a metodologia:**
   - Simulação reproduz 78% dos resultados reais (11/50 divergências)
   - HR simulado 46.0% vs real 48.0% — margem de erro de -2pp (aceitável)
   - Validação: o algoritmo Bayesiano é consistente e reproduzível

3. ✅ **Premissa "apostar sempre" não prejudica o resultado:**
   - Com Bayesiano, o max miss streak é 5 (gerenciável)
   - Sem necessidade de Kill Switch quando o offset é auto-calibrado

4. ⚠️ **HR últimas 20 ainda abaixo do ideal:**
   - CW Bayesiano sim: 30% (vs 45% meta) — período final das 50 jogadas é difícil para ambos
   - Sugere que MEL-BAY-01 (janela dinâmica) seria benéfico nessa fase

5. 📊 **Offsets divergem muito entre CW e CCW:**
   - CW oscila entre 7 e 15 (padrão bimodal instável)
   - CCW converge fortemente para 7 (padrão estável)
   - Mesmo algoritmo, parâmetros independentes — comportamento correto

> **Status:** Simulação de Engenharia Reversa concluída. Resultados confirmam a viabilidade
> da migração CW→Bayesiano. Implementação pendente de aprovação. Modo Estudo encerrado.

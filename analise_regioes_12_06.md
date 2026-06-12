# Análise offline de regiões — A1/A2/A3 (12/06)

> Dataset: 4131 decisões com resultado e centros. Somente leitura; fórmula de P&L = PROFIT-LEDGER (B5).


## A1 — Atribuição de acerto por região (por sentido)

| Sentido | Slot | Hits | Hit-rate slot | Acaso | Lift (pp) |
|---|---|---|---|---|---|
| cw | C1 | 222/1262 | 17.6% | 18.9% | -1.3 |
| cw | C2 | 171/1262 | 13.5% | 13.5% | +0.0 |
| cw | C3 | 169/1262 | 13.4% | 13.5% | -0.1 |
| cw | miss | 700/1262 | 55.5% | 54.1% | — |
| ccw | C1 | 234/1272 | 18.4% | 18.9% | -0.5 |
| ccw | C2 | 159/1272 | 12.5% | 13.5% | -1.0 |
| ccw | C3 | 187/1272 | 14.7% | 13.5% | +1.2 |
| ccw | miss | 692/1272 | 54.4% | 54.1% | — |

**Leitura:** lift > 0 = a região captura mais que o acaso. Se C2 ou C3 tiver lift ≈ 0 num sentido, a '3ª melhor região' não está onde apostamos (recalibrar OFFSET_MIN/MAX).


## A2 — Oracle das 3 melhores regiões (region_efficiency)


### Sentido cw (n=1262)
- offsets praticados (moda): C2=+10, C3=−10
- densidade capturada pelas 17 posições apostadas: 554/1262 (43.9%)
- teto a posteriori (17 melhores posições): 660/1262 (52.3%)
- **region_efficiency = 83.9%**  ← responde P5
- viés do preditor C1: média de Δ(result,C1) = -0.03 posições (≠0 ⇒ erro sistemático de força; ~0 ⇒ erro é dos offsets)
- top-10 posições de queda (Δ:count): +13:43, -8:42, +6:42, +16:42, -9:40, -1:40, -15:40, +8:40, -7:38, +3:38

### Sentido ccw (n=1272)
- offsets praticados (moda): C2=+11, C3=−10
- densidade capturada pelas 17 posições apostadas: 598/1272 (47.0%)
- teto a posteriori (17 melhores posições): 667/1272 (52.4%)
- **region_efficiency = 89.7%**  ← responde P5
- viés do preditor C1: média de Δ(result,C1) = +0.01 posições (≠0 ⇒ erro sistemático de força; ~0 ⇒ erro é dos offsets)
- top-10 posições de queda (Δ:count): -12:51, +0:46, +13:45, +7:44, +6:42, -9:41, +18:39, -14:38, +1:37, +15:37

**Decomposição do regret:** se |média Δ| > 1 o problema dominante é o preditor de forças (C1); se a média ≈ 0 mas efficiency < 80%, os offsets C2/C3 estão mal posicionados (sigmoid).


## A3 — Assimetria entre sentidos (estrutural × episódica)

Sessões com ≥10 decisões em CADA sentido: 79

- CW melhor que CCW em 35/79 sessões (44.3%) — EPISÓDICO (alterna por sessão)
- gap médio |hit_cw − hit_ccw| = 14.5%; sessões com gap ≥ 15pp: 28/79

| Sessão | n cw | hit cw | pnl cw | n ccw | hit ccw | pnl ccw | gap |
|---|---|---|---|---|---|---|---|
| session_1779503535456 | 11 | 36.4% | -145 | 11 | 81.8% | +156 | -45pp |
| session_1774646822162 | 20 | 35.0% | -168 | 19 | 78.9% | +158 | -44pp |
| session_1774722613606 | 12 | 83.3% | +95 | 12 | 41.7% | -38 | +42pp |
| 02bc6d10 | 10 | 60.0% | +46 | 10 | 20.0% | -262 | +40pp |
| session_1773683853216 | 30 | 63.3% | +127 | 29 | 27.6% | -486 | +36pp |
| session_1775152526520 | 17 | 70.6% | +200 | 17 | 35.3% | -107 | +35pp |
| session_1774696285001 | 15 | 33.3% | -131 | 15 | 66.7% | +53 | -33pp |
| session_1774868233203 | 21 | 57.1% | +75 | 21 | 23.8% | -181 | +33pp |
| c712a127 | 33 | 33.3% | -207 | 33 | 66.7% | +364 | -33pp |
| 47b82d57 | 15 | 33.3% | -7 | 14 | 64.3% | +103 | -31pp |
| session_1775151127071 | 13 | 30.8% | -77 | 13 | 61.5% | +67 | -31pp |
| dab34c61 | 12 | 66.7% | +58 | 11 | 36.4% | -37 | +30pp |
| session_1770420294979 | 10 | 10.0% | -219 | 10 | 40.0% | -3 | -30pp |
| 40139879 | 16 | 25.0% | -145 | 17 | 52.9% | +35 | -28pp |
| session_1770414940452 | 27 | 25.9% | -266 | 21 | 52.4% | +22 | -26pp |

**Leitura A3:** episódico + gaps grandes reforça o Achado 1 (estado adaptativo herdado entre dealers — corrigido pelo B1). Estrutural indica diferença física entre os sentidos → B3 (adaptação modulada por volatilidade) entra em avaliação.


## EV de referência (sanity check do PROFIT-LEDGER)

- apostas: 3996 | stake total: 89991u | P&L: -4213.9u | EV/aposta: -1.055u (-4.7% do stake)
- política CUT v1 (score≥4, N≠19) no mesmo dataset: 2175 apostas | EV/aposta: -0.228u

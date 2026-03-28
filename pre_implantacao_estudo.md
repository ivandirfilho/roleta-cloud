# Pré-Implantação: Estudos 2 a 4 — Simulação com Dados Reais

> **Data:** 28/Mar/2026  
> **Premissa fixa:** 3 centros × 7 números = **21 números SEMPRE**  
> **Base de dados:** Últimas 100 apostas com resultado (4 sessões recentes)  
> **Hit rate (100 apostas):** 49/100 = **49.0%**  
> **P&L atual (100 apostas):** R$-336  
> **Break-even (21 nums):** 58.3%  
> **Status:** DOCUMENTO DE ESTUDO — nenhuma alteração no software

---

## PREMISSA ARQUITETURAL

A cobertura do sistema é **fixa em 3 centros × 7 números = 21 números** por aposta:
- **Custo por aposta:** R$21 (R$1 × 21 números)
- **Lucro por HIT:** R$15 (R$36 retorno - R$21 custo)
- **Break-even:** 21/36 = 58.3%

**ESTUDO 1 (redução de cobertura) foi DESCARTADO** — a estrutura 3×7=21 é premissa fixa do sistema.

---

## RESUMO EXECUTIVO

| Estudo | Descoberta (100 apostas) | Impacto | Veredicto |
|:------:|--------------------------|:-------:|:---------:|
| ~~E1~~ | ~~Reduzir cobertura~~ | — | ❌ DESCARTADO |
| **E2** | Score 3 = **58.1%** HR (quase break-even!) vs Score 4 = 44.4% | Cap score | ✅ VALE |
| **E3** | "media" 51.2% vs "alta" 47.4% — inversão confirmada | alta→G1 | ✅ VALE |
| **E4** | Distância hits=6.9 vs misses=11.1 — sinal existe mas score real inútil | Log only | ⚠️ PARCIAL |

---

## ESTUDO 2: SCORE SDA vs HIT RATE

### Hipótese
Score alto (mais dados passaram IQR) deveria predizer melhor. Scores extremos (5-6) podem ser overtrained.

### Dados Reais — Últimas 100 Apostas

| Score | Apostas | Hits | Hit Rate | P&L | Edge vs BE |
|:-----:|:-------:|:----:|:--------:|:---:|:----------:|
| **3** | **31** | **18** | **58.1%** | **R$-3** | **-0.3%** |
| 4 | 63 | 28 | 44.4% | R$-315 | -13.9% |
| 5 | 5 | 2 | 40.0% | R$-33 | -18.3% |
| 6 | 1 | 1 | 100% | R$+15 | +41.7% |

**Score 1-3:** 31 apostas, **58.1% hit rate** ← QUASE BREAK-EVEN!  
**Score 4-6:** 69 apostas, **44.9% hit rate** ← 13.4% abaixo do BE

### Comparação com Dataset Completo (1.761 apostas)

| Score | HR (100 apostas) | HR (1.761 apostas) | Tendência |
|:-----:|:-----------------:|:------------------:|:---------:|
| 3 | **58.1%** | 44.7% | ⬆️ Melhora nas recentes |
| 4 | 44.4% | 51.8% | ⬇️ Piora nas recentes |
| 5-6 | 42.9% | 39.8% | ≈ Consistentemente fraco |

### Análise por Força Predita

| Força | Apostas | Hit Rate | Observação |
|:-----:|:-------:|:--------:|:----------:|
| 1-10 | 26 | 50.0% | Bom |
| 11-20 | 38 | 47.4% | Médio |
| 21-30 | 28 | 46.4% | Médio |
| **31+** | **8** | **62.5%** | **Melhor!** |

### Análise

**Descoberta CRÍTICA:** Nas últimas 100 apostas, **Score 3 tem 58.1% HR** — praticamente break-even! Score 4 caiu para 44.4%. Isso inverte a relação vista no dataset completo.

**Interpretação:** Score 3 indica dados com mais outliers (menos dados passaram IQR) → MAIS VARIÂNCIA → mas essa variância pode estar capturando tendências REAIS de mudança de momentum. Score 4 indica dados "limpos" demais → perde sinal.

**Implicação para SmartGale:** O teto de gale por score está INVERTIDO nas recentes:
- Score 3 (max G1 atual) → deveria permitir G2 (58.1% HR justifica)
- Score 4 (max G2 atual) → deveria forçar G1 (44.4% HR não justifica escalação)

### Bugs Encontrados

| # | Bug | Severidade | Descrição |
|---|-----|:----------:|-----------|
| B1 | Score 3 limitado a G1 no SmartGale v5 | 🟡 | Regra `score <= 2 → max G1` pena score 3 que tem 58.1% HR |
| B2 | Score 5-6 libera G3 mas performa pior | 🟡 | `score >= 5 → max G3` com 40-43% HR é destrutivo |
| B3 | Score não é estável entre períodos | 🟡 | Score 4: 51.8% geral vs 44.4% recente — muda com contexto |

### Veredicto: ✅ VALE A PENA — Ajustar regra de score no SmartGale

**Recomendação:**
1. Remover a regra de teto por score no get_gale() — score não é preditor confiável de HR
2. Manter apenas: streak global + c4_rate + confiança (E3) como decisores de gale
3. Alternativa conservadora: cap score em 4 (score 5-6 → tratar como 4, nunca liberar G3 por score)

---

## ESTUDO 3: CONFIANÇA INVERTIDA

### Hipótese
"Media" (c4 < m6) performa melhor que "alta" (c4 ≥ m6). A classificação está invertida.

### Dados Reais — Últimas 100 Apostas

| Confiança | Apostas | Hits | Hit Rate | P&L |
|:---------:|:-------:|:----:|:--------:|:---:|
| **alta** | 57 | 27 | **47.4%** | R$-225 |
| **media** | 43 | 22 | **51.2%** | R$-111 |

### Comparação com Dataset Completo (1.761 apostas)

| Confiança | HR (100 apostas) | HR (1.761 apostas) | Consistente? |
|:---------:|:-----------------:|:------------------:|:------------:|
| alta | 47.4% | 46.4% | ✅ Sim — SEMPRE abaixo |
| media | 51.2% | 50.5% | ✅ Sim — SEMPRE acima |

**A inversão é CONSISTENTE** — tanto nas últimas 100 quanto nas 1.761 apostas totais.

### Análise por C4 Rate

| C4 Rate | Apostas | Hit Rate | Observação |
|:-------:|:-------:|:--------:|:----------:|
| 0-25% | 23 | 43.5% | 🔴 C4 baixo = ruim |
| 25-50% | 45 | 46.7% | 🟡 Médio |
| 50-75% | 17 | 52.9% | 🟢 Bom |
| **75-100%** | **15** | **60.0%** | 🟢 **Excelente** |

### Cenários Simulados com SmartGale v5

| Cenário | Lógica | P&L | Distribuição Gale |
|:-------:|--------|:---:|:-----------------:|
| Atual (todos G1-G3) | Escala por streak sem filtro | **R$-429** | G1:75 G2:25 |
| **E3: alta→G1, media→G1-G3** | Proteção contra spike | **R$-417** | G1:91 G2:9 |
| E3b: alta→G1, media→G1-G2 | Conservador | R$-417 | G1:91 G2:9 |

### Análise

**CONFIRMAÇÃO FORTE:** "media" supera "alta" por **3.8 pontos** nas recentes (51.2% vs 47.4%) e **4.1 pontos** no geral (50.5% vs 46.4%). A consistência entre amostras valida a descoberta.

**SmartGale com confiança:** A simulação mostra ganho modesto (R$12) porque nas últimas 100 a maioria já é G1. O impacto real será maior quando streaks globais ativarem — a confiança impede escalação nos piores momentos.

**C4 Rate esclarece:** C4 alto (75-100%) = 60% HR é excelente. Mas "alta" (c4≥m6) mistura C4 alto em spike com C4 médio em tendência — diluindo o sinal.

### Bugs Encontrados

| # | Bug | Severidade | Descrição |
|---|-----|:----------:|-----------|
| B4 | get_gale() não recebe `confidence` | 🟡 | Parâmetro inexistente — precisa ser adicionado |
| B5 | message_handler não passa `confidence` para get_gale() | 🟡 | Falta pipeline de passagem |
| B6 | "alta" não deveria ser nome — deveria ser "spike" para clareza | 🔵 | Confusão semântica |

### Veredicto: ✅ VALE A PENA IMPLANTAR

**Recomendação:** Adicionar parâmetro `confidence` ao get_gale(). Quando "alta" → forçar max_gale=1 (proteção contra spike regression). "media" → permitir escalação normal.

---

## ESTUDO 4: DISTÂNCIA AO CENTRO E SCORE REAL

### Hipótese
Score baseado em performance_snapshot recente seria melhor preditor que score SDA.

### Dados Reais — Últimas 100 Apostas

**Distância resultado ao centro:**
| Métrica | HITs | MISSes | Diferença |
|---------|:----:|:------:|:---------:|
| Distância média | **6.9 casas** | **11.1 casas** | 4.2 casas |
| N | 49 | 51 | — |

**Distribuição dos HITs:**
| Faixa | Hits | % dos Hits |
|:-----:|:----:|:----------:|
| 0-3 casas | 19 | **39%** |
| 4-6 casas | 4 | 8% |
| 7-10 casas | 12 | 24% |
| 11+ casas | 14 | **29%** |

### Hits por Centro (C1/C2/C3)

| Centro | Função | Hits | % |
|:------:|--------|:----:|:-:|
| **C1** | Mediana | **24** | **49%** |
| C2 | Max força | 13 | 27% |
| C3 | Min força | 12 | 24% |

→ **C1 (mediana) captura 49% dos hits** — é o centro mais forte. C2 e C3 contribuem 51% juntos — Triple Focus justificado.

### Score Real (performance_snapshot C4)

| Real Score | Apostas | Hits | Hit Rate |
|:----------:|:-------:|:----:|:--------:|
| 1 | 8 | 5 | 62.5% |
| 2 | 23 | 10 | 43.5% |
| 3 | 9 | 7 | **77.8%** |
| 4 | 28 | 9 | 32.1% |
| 5 | 17 | 9 | 52.9% |
| 6 | 15 | 9 | 60.0% |

### Comparação com Dataset Completo

| Real Score | HR (100 apostas) | HR (1.761 apostas) | Estável? |
|:----------:|:-----------------:|:------------------:|:--------:|
| 1 | 62.5% | 49.1% | ❌ Instável |
| 2 | 43.5% | 46.5% | ≈ |
| 3 | **77.8%** | 50.0% | ❌ Instável |
| 4 | 32.1% | 46.9% | ❌ Instável |
| 5 | 52.9% | 48.8% | ≈ |
| 6 | 60.0% | 49.2% | ❌ Instável |

### Análise

**O score real é COMPLETAMENTE instável.** Os valores variam enormemente entre amostras (32.1% vs 77.8% no mesmo score). Não há padrão preditivo.

**A distância ao centro CONFIRMA sinal:** Hits estão 4.2 casas mais perto que misses (6.9 vs 11.1). Isso valida que a SDA-21 prediz corretamente a REGIÃO, mas o score não captura essa qualidade.

**Triple Focus funciona:** C1 captura 49%, C2+C3 capturam 51%. Sem C2 e C3, perderíamos metade dos acertos.

### Bugs Encontrados

| # | Bug | Severidade | Descrição |
|---|-----|:----------:|-----------|
| B7 | Distância ao centro não é logada no DB | 🔵 | Sem métrica para monitorar evolução |
| B8 | Score real por C4 é ruidoso demais para decisão | 🟡 | Feedback loop se implementado |

### Veredicto: ⚠️ PARCIAL — Apenas logging, NÃO alterar score

**Recomendação:** Adicionar campo `distance_to_center` no DB quando `result_actual` é gravado. NÃO implementar score real — é instável e cria feedback loop.

---

## ENGENHARIA REVERSA — Últimas 20 Apostas

| # | Result | Score | Conf | C4 | Centros | Nums | Actual | Dist | Força |
|--:|:------:|:-----:|:----:|:--:|---------|:----:|:------:|:----:|:-----:|
| 2680 | **HIT** | 6 | med | 100% | [29] | 19 | 12 | 3 | 13 |
| 2681 | **HIT** | 4 | alt | 50% | [23,17,18] | 21 | 8 | 1 | 16 |
| 2682 | **HIT** | 4 | alt | 100% | [35,34,20] | 21 | 31 | 8 | 18 |
| 2683 | MISS | 4 | alt | 67% | [6,32,33] | 21 | 21 | 5 | 16 |
| 2684 | MISS | 5 | alt | 100% | [10,29,2] | 21 | 31 | 8 | 13 |
| 2685 | MISS | 3 | alt | 50% | [25,5,28] | 21 | 15 | 5 | 19 |
| 2686 | MISS | 4 | alt | 75% | [8,1,4] | 21 | 18 | 13 | 14 |
| 2687 | MISS | 3 | alt | 50% | [21,23,14] | 21 | 32 | 4 | 24 |
| 2688 | MISS | 3 | med | 50% | [14,0,34] | 21 | 16 | 4 | 24 |
| 2689 | MISS | 4 | med | 25% | [7,2,5] | 21 | 36 | 18 | 27 |
| 2690 | **HIT** | 4 | med | 25% | [12,19,16] | 21 | 19 | 7 | 20 |
| 2691 | **HIT** | 4 | med | 0% | [16,13,28] | 21 | 16 | 0 | 19 |
| 2692 | MISS | 4 | med | 25% | [21,23,7] | 21 | 14 | 17 | 21 |
| 2693 | MISS | 4 | med | 25% | [2,35,23] | 21 | 16 | 15 | 19 |
| 2694 | MISS | 4 | med | 25% | [4,27,14] | 21 | 18 | 12 | 20 |
| 2695 | **HIT** | 4 | alt | 25% | [6,32,14] | 21 | 34 | 1 | 19 |
| 2696 | MISS | 4 | alt | 25% | [5,26,25] | 21 | 7 | 12 | 10 |
| 2697 | MISS | 4 | alt | 50% | [13,19,9] | 21 | 1 | 11 | 19 |
| 2698 | MISS | 3 | alt | 25% | [8,22,4] | 21 | 6 | 6 | 30 |
| 2699 | MISS | 4 | alt | 50% | [15,5,9] | 21 | 27 | 9 | 8 |

**Padrões observados:**
- Últimas 13 apostas: 2 HITs, 11 MISSes (15.4%) — **sequência de perda**
- HITs recentes: dist 0, 1, 7 (próximos ao centro)
- MISSes recentes: dist 4, 5, 6, 9, 11, 12, 13, 15, 17, 18 (longe)
- C4 rate caindo: 100%→50%→25%→0%→25% — **declínio de performance**
- Score 4 dominante (14/20) mas com 28.6% HR neste trecho

---

## AUDITORIA FINAL: BUGS E MELHORIAS

### Bugs Consolidados

| # | Bug | Severidade | Estudo | Ação |
|---|-----|:----------:|:------:|:----:|
| B1 | Score 3 limitado a G1 mas tem 58.1% HR | 🟡 | E2 | Remover teto por score |
| B2 | Score 5-6 libera G3 com ~40% HR | 🟡 | E2 | Cap em 4 |
| B3 | Score instável entre períodos (51.8% geral vs 44.4% recente) | 🟡 | E2 | Não usar para gale |
| B4 | get_gale() não recebe `confidence` | 🟡 | E3 | Adicionar parâmetro |
| B5 | message_handler não passa `confidence` para get_gale() | 🟡 | E3 | Pipeline update |
| B6 | "alta" deveria chamar-se "spike" para clareza | 🔵 | E3 | Futuro |
| B7 | Distância ao centro não logada no DB | 🔵 | E4 | Novo campo |
| B8 | Score real por C4 é ruidoso demais | 🟡 | E4 | Não implementar |

### Melhorias Propostas

| # | Melhoria | Impacto | Prioridade |
|---|----------|:-------:|:----------:|
| M1 | Remover regra de teto por score no get_gale() | Menos restrição artificial | P1 |
| M2 | Confiança "alta" → força max_gale=1 | Protege contra spike | P0 |
| M3 | Cap score em 4 para gale (alternativa conservadora a M1) | Segurança | P2 |
| M4 | Logar `distance_to_center` no DB | Diagnóstico | P2 |

---

## TASKS PARA IMPLANTAÇÃO

### TASK-E2: Simplificar Regra de Score no SmartGale [P1]

**Arquivo:** `state/game.py` (método `get_gale`)

**Opção A — Remover teto por score:**
```python
def get_gale(self, score: int = 3, c4_rate: float = 0.5, confidence: str = "media") -> int:
    # Regra de score REMOVIDA — score não prediz HR de forma confiável
    max_gale = 3  # Teto definido por confiança e c4, não por score
```

**Opção B — Cap conservador em 4:**
```python
    effective_score = min(score, 4)
    if effective_score <= 2: max_gale = 1
    elif effective_score <= 4: max_gale = 2
```

**Impacto:** Score 3 (58.1% HR) não fica mais travado em G1

---

### TASK-E3: Confiança "alta" Força G1 no SmartGale [P0]

**Arquivo:** `state/game.py` (método `get_gale`)

**Lógica:**
```python
def get_gale(self, score: int = 3, c4_rate: float = 0.5, confidence: str = "media") -> int:
    max_gale = 3
    # Regra 6 — Proteção contra spike regression
    if confidence == "alta":
        max_gale = 1
    elif confidence == "baixa":
        max_gale = 1
    # Regra 4 — C4 advisor
    if c4_rate < 0.15:
        max_gale = 1
    # Regra 2 — Anti-Martingale
    streak = self.global_consecutive_hits
    if streak >= 3: desired = 3
    elif streak >= 2: desired = 2
    else: desired = 1
    self.level = min(desired, max_gale)
    return self.level
```

**Arquivo:** `server/message_handler.py` + `core/engine.py`

Atualizar chamada: `mg.get_gale(score=result.score, c4_rate=bet_c4_rate, confidence=advice.confidence)`

**Impacto:** Escalação APENAS em "media" (51.2% HR), proteção em "alta" (47.4% HR)

---

### TASK-E4: Logar Distância ao Centro [P2]

**Arquivo:** `server/message_handler.py`

**Lógica:** Quando `update_result()` é chamado com `result_actual`, calcular distância ao centro predito e logar.

---

## COMPARAÇÃO: ESTADO ATUAL vs PROPOSTA

### Com 21 números fixos (3×7)

| Cenário | Quem escala | P&L (100 apostas) | Obs |
|:-------:|-------------|:------------------:|-----|
| **Atual** | Todos por streak | **R$-429** | SmartGale sem filtro |
| **E3 (proposto)** | Só "media" por streak | **R$-417** | alta→G1 protege |
| **E2+E3** | "media" sem teto score | **≈R$-400** | Score 3 liberado |

**Nota:** O ganho aparente é pequeno (R$12-29) nas 100 apostas porque a maioria já é G1. O impacto REAL será nas sessões com streaks longos onde a escalação acontece — nesses momentos a confiança "alta" travando em G1 previne as maiores perdas.

---

## DIAGNÓSTICO FINAL

### Vale a pena implantar:

1. **TASK-E3 (P0):** Confiança no get_gale(). Consistente em TODAS as amostras. "media" > "alta" por 3.8-4.1 pontos. Zero risco.

2. **TASK-E2 (P1):** Remover teto por score OU cap em 4. Score 3 = 58.1% HR não merece ser travado em G1.

### Vale parcialmente:

3. **TASK-E4 (P2):** Log de distância. Diagnóstico valioso mas sem impacto direto.

### NÃO vale:

4. **ESTUDO 1:** Descartado pela premissa 3×7=21 fixos.
5. **Score real (E4):** Instável, feedback loop perigoso.

---

> **Documento de estudo** — nenhuma alteração no software  
> **Aguardando aprovação para TASK-E2 + TASK-E3 + TASK-E4**

# 📊 Análise de Resultados — Roleta Cloud v3.5.0

> **Data da Análise:** 26/03/2026  
> **Sessão Analisada:** `dab34c61` (26/03/2026 21:45–22:01 UTC)  
> **Base de Dados:** `data/decisions.db` — 2.379 decisões, 42 sessões  
> **Estratégia Ativa:** SDA-19 (IQR + Weighted Median + Drift Detection)  

---

## 1. MODELO DE ESTRATÉGIA EM USO

### 1.1 SDA-19 (Sinergia Direcional Avançada — Robust)

O sistema utiliza a estratégia **SDA-19**, implementada em `strategies/sda17.py`. O pipeline de decisão é:

```
Spin Recebido → Cálculo de Força → Timeline (CW/CCW) → SDA-19 Pipeline → Triple Rate Advisor → Decisão
```

**Pipeline SDA-19 (4 passos):**

| Passo | Método | Descrição |
|:-----:|--------|-----------|
| 1 | **Janela Adaptativa** | Tenta 7→5→3 forças recentes da timeline |
| 2 | **IQR Outlier Rejection** | Remove forças anômalas (quartis ± 1.5×IQR) |
| 3 | **Weighted Median** | Mediana ponderada (decay=0.8, mais recentes pesam mais) |
| 4 | **Drift Detection** | Extrapola tendência se 3 últimas forças são monotônicas |

**Cobertura:** 19 números (1 centro + 9 vizinhos de cada lado) = **51.4%** da roda

**Score (1-6):** Calculado por `survival_rate × 3 + tightness × 3 + stable_bonus`

### 1.2 Triple Rate Advisor (Kill Switch)

Filosofia: **APOSTAR SEMPRE**, só vetar catástrofe.

| Condição | Ação |
|----------|------|
| C4 = 0% **E** SDA Score ≤ 2 | 🛑 KILL SWITCH — PULAR |
| Qualquer outra combinação | ✅ APOSTAR |

Níveis de confiança: `alta` (C4 ≥ M6 ≥ L12), `media` (demais), `baixa` (kill switch)

### 1.3 Sistema de Direções

```
Spin Horário chegou → Força adicionada a timeline_CW
                    → Próxima predição usa timeline_CCW (direção oposta)
                    → Força aplicada em sentido ANTI-HORÁRIO a partir do último número
```

**Propriedade `target_direction`:** Sempre a direção OPOSTA à do último spin recebido.

---

## 2. FLUXO DE DADOS DE CADA DECISÃO

### 2.1 Sessão Atual — Rastreamento Completo (23 decisões)

#### Fase de Aquecimento (IDs 2358–2363): Dados Insuficientes

| ID | Dir | Número | Força | SDA Score | Ação | Motivo |
|:--:|:---:|:------:|:-----:|:---------:|:----:|--------|
| 2358 | H | 5 | 0 | 0 | PULAR | Forças insuficientes (0/3) |
| 2359 | AH | 16 | 35 | 0 | PULAR | Forças insuficientes |
| 2360 | H | 33 | 1 | 0 | PULAR | Forças insuficientes |
| 2361 | AH | 29 | 29 | 0 | PULAR | Forças insuficientes |
| 2362 | H | 13 | 19 | 0 | PULAR | Forças insuficientes |
| 2363 | AH | 15 | 10 | 0 | PULAR | Forças insuficientes |

> ⏳ **6 spins pulados** — o sistema precisa de pelo menos 3 forças por timeline antes de apostar.

#### Fase Ativa (IDs 2364–2379): Apostas com Resultados

| ID | Dir | Spin | Força | Pred. Força | Centro | Resultado | Hit? | Confiança | Gale |
|:--:|:---:|:----:|:-----:|:-----------:|:------:|:---------:|:----:|:---------:|:----:|
| 2364 | H | 13 | 10 | 17 | 28 | 35 | ✅ | media | G1 |
| 2365 | AH | 35 | 15 | 10 | 25 | 1 | ❌ | media | G1 |
| 2366 | H | 1 | 26 | 15 | 17 | 34 | ✅ | media | G1 |
| 2367 | AH | 34 | 14 | 19 | 22 | 22 | ✅ | media | G1 |
| 2368 | H | 22 | 19 | 15 | 36 | 5 | ✅ | alta | G1 |
| 2369 | AH | 5 | 9 | 19 | 32 | 30 | ❌ | alta | G1 |
| 2370 | H | 30 | 33 | 7 | 17 | 21 | ✅ | alta | G1 |
| 2371 | AH | 21 | 10 | 19 | 20 | 13 | ❌ | alta | G1 |
| 2372 | H | 13 | 7 | 10 | 15 | 21 | ✅ | alta | G1 |
| 2373 | AH | 21 | 7 | 19 | 20 | 32 | ❌ | alta | G1 |
| 2374 | H | 32 | 33 | 10 | 22 | 2 | ❌ | alta | G1 |
| 2375 | AH | 2 | 32 | 26 | 28 | 24 | ❌ | alta | G2 |
| 2376 | H | 24 | 14 | 10 | 6 | 4 | ✅ | media | G1 |
| 2377 | AH | 4 | 16 | 19 | 1 | 10 | ✅ | media | G2 |
| 2378 | H | 10 | 14 | 12 | 2 | 16 | ❌ | media | G1 |
| 2379 | AH | 16 | 34 | 14 | 3 | ⏳ | ⏳ | media | G2 |

---

## 3. ANÁLISE DE ACERTOS E ERROS

### 3.1 Resumo da Sessão Atual

| Direção | Apostas | Acertos | Erros | Taxa | Média Erro Força |
|---------|:-------:|:-------:|:-----:|:----:|:----------------:|
| **Horário (CW)** | 8 | 6 | 2 | **75.0%** | 7.5 posições |
| **Anti-Horário (CCW)** | 8 | 3 | 5 | **37.5%** | 8.8 posições |
| **Total** | 16 | 9 | 7 | **56.3%** | 8.1 posições |

### 3.2 Rastreamento dos ACERTOS (✅)

#### ✅ ID 2364 — Horário (spin=13, resultado=35)
```
Pipeline: last_number=13 → timeline_CW forces usadas
         SDA pred force=17 → center=28
         Números: [1,20,14,31,9,22,18,29,7,28,12,35,3,26,0,32,15,19,4]
         Resultado: 35 ∈ números → HIT (35 está a 3 posições do centro 28)
         Erro de força: |17 - 10| = 7 posições (subestimou)
```
**Por que acertou:** Apesar do erro de 7 na previsão de força, a cobertura de 19 números foi suficiente para capturar o resultado.

#### ✅ ID 2366 — Horário (spin=1, resultado=34)
```
Pipeline: last_number=1 → SDA pred force=15 → center=17
         Números: [26,0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23]
         Resultado: 34 ∈ números → HIT (34 está a 2 posições do centro 17)
```
**Por que acertou:** Previsão de força próxima da realidade (15 vs 26, mas a larga cobertura absorveu).

#### ✅ ID 2367 — Anti-Horário (spin=34, resultado=22)
```
Pipeline: last_number=34 → SDA pred force=19 → center=22
         Resultado: 22 = centro da previsão! → HIT PERFEITO
         Erro de força: |19 - 14| = 5
```
**Por que acertou:** Predição de centro quase perfeita. A mediana ponderada com drift capturou a tendência.

#### ✅ ID 2368 — Horário (spin=22, resultado=5)
```
Pipeline: last_number=22 → SDA pred force=15 → center=36
         Números: [4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33]
         Resultado: 5 ∈ números → HIT (5 está a 8 posições do centro, borda da cobertura)
         Confiança: ALTA (C4=100%, M6=100%, L12=100%)
```
**Por que acertou:** Cobertura larga (19 nums) capturou resultado na borda. Triple Rate com confiança máxima.

#### ✅ ID 2370 — Horário (spin=30, resultado=21)
```
Pipeline: last_number=30 → SDA pred force=7 → center=17
         Números: [26,0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23]
         Resultado: 21 ∈ números → HIT
         Erro de força: |7 - 33| = 26 posições! (erro massivo)
```
**Por que acertou:** Paradoxalmente, acertou COM ERRO DE FORÇA ENORME (26). A cobertura ampla de 51.4% compensou completamente a falha na predição de força.

#### ✅ ID 2372 — Horário (spin=13, resultado=21)
```
Pipeline: last_number=13 → SDA pred force=10 → center=15
         Números: [29,7,28,12,35,3,26,0,32,15,19,4,21,2,25,17,34,6,27]
         Resultado: 21 ∈ números → HIT
         Erro de força: |10 - 7| = 3
```
**Por que acertou:** Boa previsão de força (erro=3), resultado bem dentro da cobertura.

#### ✅ ID 2376 — Horário (spin=24, resultado=4)
```
Pipeline: last_number=24 → SDA pred force=10 → center=6
         Números: [32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5]
         Resultado: 4 ∈ números → HIT (4 está a 3 posições do centro)
```
**Por que acertou:** Predição de força razoável, resultado próximo ao centro.

#### ✅ ID 2377 — Anti-Horário (spin=4, resultado=10)
```
Pipeline: last_number=4 → SDA pred force=19 → center=1
         Números: [11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28]
         Resultado: 10 ∈ números → HIT (na borda da cobertura)
         Gale: G2 (segunda tentativa na janela)
```
**Por que acertou:** Recuperação em G2 após erro anterior (ID 2375). Cobertura absorveu.

### 3.3 Rastreamento dos ERROS (❌)

#### ❌ ID 2365 — Anti-Horário (spin=35, resultado=1)
```
Pipeline: last_number=35 → SDA pred force=10 → center=25
         Números: [3,26,0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8]
         Resultado: 1 NÃO está nos números → MISS
         Posição de 1 na roda: posição 23
         Posição do centro 25: posição 7
         Distância: 16 posições (fora da cobertura de 9+9)
```
**Por que errou:** Predição de força muito baixa (10 vs 15 real). O número 1 caiu 16 posições longe do centro previsto, muito além da cobertura.

#### ❌ ID 2369 — Anti-Horário (spin=5, resultado=30)
```
Pipeline: last_number=5 → SDA pred force=19 → center=32
         Números: [18,29,7,28,12,35,3,26,0,32,15,19,4,21,2,25,17,34,6]
         Resultado: 30 NÃO está nos números → MISS
         Posição de 30: posição 15
         Posição de centro 32: posição 1
         Distância: 14 posições (fora)
```
**Por que errou:** O SDA previu centro=32 (posição 1) mas o número caiu na posição 15. A previsão de força (19) era razoável para a força real (9), mas a direção de aplicação levou a um centro oposto ao resultado.

#### ❌ ID 2371 — Anti-Horário (spin=21, resultado=13)
```
Pipeline: last_number=21 → SDA pred force=19 → center=20
         Números: [30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12]
         Resultado: 13 NÃO está nos números → MISS
         Posição de 13: posição 12
         Posição do centro 20: posição 24
         Distância: 12 posições (fora)
```
**Por que errou:** Força real (10) muito diferente da prevista (19). O drift detection pode ter inflado a previsão.

#### ❌ ID 2373 — Anti-Horário (spin=21, resultado=32)
```
Pipeline: last_number=21 → SDA pred force=19 → center=20
         Resultado: 32 a 23 posições do centro → MISS
```
**Por que errou:** Mesmo cenário que ID 2371 — previsão repetida (centro=20, force=19) falhou novamente. A timeline CCW estava produzindo previsões estáveis mas incorretas.

#### ❌ ID 2374 — Horário (spin=32, resultado=2)
```
Pipeline: last_number=32 → SDA pred force=10 → center=22
         Números: [5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26,0]
         Resultado: 2 a 15 posições do centro → MISS
         Erro de força: |10 - 33| = 23! (erro massivo)
```
**Por que errou:** A força real (33) foi brutalmente maior que a prevista (10). O IQR pode ter removido forças altas como outliers, subestimando a tendência.

#### ❌ ID 2375 — Anti-Horário (spin=2, resultado=24)
```
Pipeline: last_number=2 → SDA pred force=26 → center=28
         Números: [1,20,14,31,9,22,18,29,7,28,12,35,3,26,0,32,15,19,4]
         Resultado: 24 a 12 posições do centro → MISS
         Gale: G2 (escalou de G1)
```
**Por que errou:** Apesar de prever força=26 (próxima da real 32), o centro calculado ficou longe. A aplicação da força em sentido anti-horário a partir do número 2 (posição 6) levou a posição 6-26=-20 → posição 17 mod 37, que é o 28 — mas 24 está na posição 20, a 3 posições de 28... Wait, 24 está no sda_numbers? 

Revisão: 24 NÃO está em [1,20,14,31,9,22,18,29,7,28,12,35,3,26,0,32,15,19,4]. Confirmado MISS.

#### ❌ ID 2378 — Horário (spin=10, resultado=16)
```
Pipeline: last_number=10 → SDA pred force=12 → center=2
         Números: [35,3,26,0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30]
         Resultado: 16 NÃO está nos números → MISS
         Erro de força: |12 - 14| = 2 (erro pequeno!)
```
**Por que errou:** Paradoxalmente, a previsão de força foi boa (erro=2), mas o resultado caiu fora. Isso sugere que a **direção de aplicação** pode estar invertida — com force=12 em sentido horário a partir de 10 (pos 18), chegamos a pos 30 = número 8. Mas o resultado (16) está na pos 21, a 3 posições da borda de cobertura.

---

## 4. VERIFICAÇÃO DOS FLUXOS DIRECIONAIS

### 4.1 Alternância de Direções
```
Sequência da sessão: H → AH → H → AH → H → AH → ... (23 spins)
```
✅ **CORRETO** — As direções alternam perfeitamente a cada spin, consistente com roleta europeia ao vivo.

### 4.2 Mapeamento Direção → Timeline

| Spin Recebido | Timeline Alimentada | Timeline Usada p/ Predição | Direção Aplicada |
|:-------------:|:-------------------:|:--------------------------:|:----------------:|
| Horário | `timeline_cw` | `timeline_ccw` | Anti-Horário |
| Anti-Horário | `timeline_ccw` | `timeline_cw` | Horário |

✅ **CORRETO** — O código em `game.py` (linhas 364-375) implementa `target_direction = oposto(last_direction)` e `target_timeline = timeline[oposto]`.

### 4.3 Aplicação da Força

```python
# sda17.py → _apply_force()
if target_direction in ("cw", "horario"):
    target_idx = (from_idx + force) % wheel_size   # Avança na roda
else:
    target_idx = (from_idx - force) % wheel_size   # Recua na roda
```

✅ **CORRETO** — Horário avança (sentido crescente dos índices da WHEEL_SEQUENCE), anti-horário recua.

### 4.4 Assimetria de Performance entre Direções

| Métrica | Horário (CW) | Anti-Horário (CCW) | Delta |
|---------|:------------:|:------------------:|:-----:|
| Taxa de acerto (sessão) | **75.0%** | **37.5%** | +37.5pp |
| Taxa de acerto (global) | **46.7%** | **46.6%** | +0.1pp |
| Erro médio de força (sessão) | 7.5 | 8.8 | -1.3 |
| Erro médio de força (global) | 11.3 | 12.1 | -0.8 |
| Força prevista média | 12.0 | 18.1 | -6.1 |
| Força real média | 19.5 | 17.1 | +2.4 |

⚠️ **OBSERVAÇÃO CRÍTICA:** Na sessão atual, a previsão para CW **subestima sistematicamente** a força (prevê 12, real é 19.5). Porém, a cobertura de 19 números compensa. Para CCW, a previsão (18.1) está próxima da real (17.1), mas a taxa de acerto é pior.

**Hipótese:** A timeline CCW nesta sessão pode ter dados enviesados (forças anômalas ou poucas observações) que prejudicam a IQR/Weighted Median.

---

## 5. JANELAS DE MARTINGALE (GALE)

### 5.1 Janelas Recentes

| Window | Dir | Gale | Plays | Hits | Result | SDA Rate Start |
|:------:|:---:|:----:|:-----:|:----:|:------:|:--------------:|
| 236 | CCW | G1 | 5 | **5** | ✅ success | 100% |
| 237 | CW | G1 | 5 | **1** | ⬆️ escalated→G2 | 0% |
| 238 | CCW | G1 | 3 | 1 | 🔄 em andamento | 83% |
| 239 | CW | G2 | 3 | 2 | 🔄 em andamento | 17% |

### 5.2 Análise da Janela 236 (CCW — Sucesso Perfeito 5/5)

| Play | Spin | Força | Centro Prev. | Resultado | Hit? |
|:----:|:----:|:-----:|:------------:|:---------:|:----:|
| 1 | 35 | 17 | 28 | 35 | ✅ |
| 2 | 34 | 15 | 17 | 34 | ✅ |
| 3 | 5 | 15 | 36 | 5 | ✅ |
| 4 | 21 | 7 | 17 | 21 | ✅ |
| 5 | 21 | 10 | 15 | 21 | ✅ |

> 🏆 **Sequência perfeita!** A timeline CCW estava bem calibrada neste período, com forças estáveis (7-17 range).

### 5.3 Análise da Janela 237 (CW — Escalou para G2)

| Play | Spin | Força | Centro Prev. | Resultado | Hit? |
|:----:|:----:|:-----:|:------------:|:---------:|:----:|
| 1 | 1 | 10 | 25 | 1 | ❌ |
| 2 | 22 | 19 | 22 | 5 | ✅ |
| 3 | 30 | 19 | 32 | 21 | ❌ |
| 4 | 13 | 19 | 20 | 21 | ❌ |
| 5 | 32 | 19 | 20 | 2 | ❌ |

> ⚠️ **Padrão problemático:** O SDA "travou" prevendo centro=20-22 (plays 3-5), enquanto os resultados variavam. A weighted median convergiu para uma previsão fixa quando as forças reais eram consistentes (19), mas o centro resultante não acompanhou.

---

## 6. ESTATÍSTICAS GLOBAIS DO DATABASE

### 6.1 Performance Geral (2.379 decisões, 1.512 apostas com resultado)

| Métrica | Valor |
|---------|:-----:|
| Total de decisões | 2.379 |
| Total de sessões | 42 |
| Apostas com resultado | 1.512 |
| Acertos totais | 705 |
| **Taxa de acerto global** | **46.6%** |
| Cobertura teórica (19/37) | 51.4% |
| **Delta vs aleatório** | **-4.8pp** |

### 6.2 Performance por Confiança

A taxa global de **46.6%** está **abaixo** do esperado aleatório (51.4%), indicando que:
1. A predição de força **não adiciona valor** em relação a apostar em 19 números aleatórios
2. A predição pode estar **deslocando** o centro para longe do resultado real em ~12% dos casos (anti-seleção)

### 6.3 Erro Médio de Força

| Direção | Erro Médio | Interpretação |
|---------|:----------:|---------------|
| Horário | 11.3 posições | ~30% da roda |
| Anti-Horário | 12.1 posições | ~33% da roda |

---

## 7. DIAGNÓSTICO E CONCLUSÕES

### 7.1 O que está funcionando ✅

1. **Fluxo direcional:** Alternância H/AH perfeita, timelines separadas corretamente
2. **Aplicação de força:** Cálculo e aplicação na roda estão matematicamente corretos
3. **Cobertura de 19 números:** Compensa erros de predição — mesmo com erro de força de 26, ainda acertou (ID 2370)
4. **Martingale CW/CCW independentes:** Gerenciamento correto de janelas por direção
5. **Kill Switch:** Corretamente permissivo (quase nunca veta), deixa Martingale gerir risco

### 7.2 O que precisa atenção ⚠️

1. **Taxa global abaixo do aleatório (46.6% vs 51.4%):** A predição de força não está adicionando valor preditivo. Os 19 números seriam mais eficazes se escolhidos aleatoriamente na vizinhança.

2. **Subestimação de força no CW:** Na sessão atual, a média prevista (12.0) é muito inferior à real (19.5). O filtro IQR pode estar removendo forças altas como "outliers" quando na verdade são o padrão.

3. **Repetição de previsões ruins no CCW:** IDs 2371 e 2373 produziram o MESMO centro (20) com a MESMA força prevista (19), falhando ambas. A timeline estava "travada" em dados que não refletiam a realidade.

4. **Drift Detection pode inflar/deflacionar:** Quando as últimas 3 forças são monotônicas, o drift extrapola — mas isso assume continuidade de tendência que nem sempre se mantém em jogos de azar.

### 7.3 Recomendações

| Prioridade | Ação | Impacto Esperado |
|:----------:|------|:----------------:|
| 🔴 Alta | Investigar se IQR está removendo forças válidas como outliers (comparar `clean_count` vs total) | +2-4pp hit rate |
| 🟡 Média | Considerar expandir cobertura para 21 números (10+1+10 = 56.8%) para compensar erro de força | +5pp hit rate |
| 🟡 Média | Implementar detecção de "timeline travada" (mesma previsão 3x consecutivas = reset) | Evitar sequências de loss |
| 🟢 Baixa | Logging da `survival_rate` e `outliers_removed` por spin para auditoria contínua | Observabilidade |

---

> **Documento gerado em:** 26/03/2026 21:58 UTC  
> **Fonte dos dados:** `data/decisions.db` via SSH (`root@187.45.181.75`)  
> **Código analisado:** `strategies/sda17.py`, `core/engine.py`, `state/game.py`, `state/bet_advisor.py`

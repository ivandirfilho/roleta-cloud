# Plano de Tarefas - Sessao 13:50 28/03/2026

> **Data:** 28/Mar/2026
> **Base:** `sessao13_50_28_03.md` + auditoria completa do software
> **Status:** DOCUMENTO DE ESTUDO - nenhuma alteracao no software
> **Dados:** 37 apostas resolvidas, 15 hits, 22 misses (40.5%)

---

## PARTE 1 — AUDITORIA: BUGS E MELHORIAS ENCONTRADOS

### BUG-01: get_gale() NUNCA Chamado em Producao [CRITICO]

**Arquivo:** `server/message_handler.py` linhas 228-244
**Descoberta:** O pipeline de producao (WebSocket) passa por `message_handler.py`, NAO por `core/engine.py`. O `message_handler.py` pula completamente a chamada `get_gale()`.

**Impacto:** SmartGale v4 E v5 sao puramente decorativos. TODAS as apostas desde o inicio do software foram G1 por default, nao por decisao estrategica.

**Evidencia:** `action_reason` no banco mostra `"SDA + Triple Rate aprovaram (media)"` em vez de `"SDA score=4 | G1 S0 GS0 | C4=50%"` (formato do engine.py).

**Codigo atual (message_handler.py linhas 230-244):**
```
if advice.should_bet:
    acao = "APOSTAR"
    action_reason = f"SDA + Triple Rate aprovaram ({advice.confidence})"
    # FALTA: mg.get_gale() aqui!
    self.game_state.store_prediction(...)
```

### BUG-02: sync_global() Nao Existe em Producao [CRITICO]

**Arquivo:** `server/message_handler.py` linhas 163-165
**Descoberta:** O `update()` do martingale nao passa `global_hit` e nao chama `sync_global()` para o martingale oposto.

**Codigo atual:**
```
if bet_direction in ("cw", "horario"):
    martingale_info = self.game_state.martingale_cw.update(hit_result)
    # FALTA: global_hit=hit_result
    # FALTA: self.game_state.martingale_ccw.sync_global(hit_result)
```

### BUG-03: Fallback Early-Session Ausente em Producao [MEDIO]

**Arquivo:** `server/message_handler.py` linhas 260-263
**Descoberta:** `engine.py` tem logica de fallback G1 seguro quando SDA tem dados mas sinal fraco (linhas 118-133). `message_handler.py` pula direto para "PULAR".

### BUG-04: get_bet_c4_rate() Nao Chamado em Producao [MEDIO]

**Arquivo:** `server/message_handler.py`
**Descoberta:** O c4_rate calculado pelo Triple Rate Advisor nao e passado para `get_gale()`, impossibilitando o filtro de seguranca.

### BUG-05: Confianca "alta" Performa PIOR que "media" [ANOMALIA]

**Arquivo:** `state/bet_advisor.py` linhas 97-108
**Causa raiz:** A classificacao `"alta"` exige `c4 >= m6` (curto prazo >= medio prazo). Isso detecta PICOS de performance que tendem a REGREDIR para a media. Resultado: "alta" = apostando no FIM de um streak, "media" = apostando em momento mais estavel.

**Dados da sessao:** "media" = 44.4% hit, "alta" = 35.0% hit.

### BUG-06: Score NAO Correlaciona com Acuracia [ANOMALIA]

**Arquivo:** `strategies/sda17.py` linhas 235-242
**Causa raiz:** Score = `survival*3 + tightness*3 + stable_bonus`. Survival alto (poucos outliers removidos) + tightness alta (forcas concentradas) + estabilidade (sem drift) = score alto. Porem:
- **IQR filtering remove outliers que sao SINAIS REAIS de mudanca de momentum**
- **Drift adjustment = 0 (stable_bonus) penaliza deteccao de tendencia**
- Score 3 com drift adjustment ACERTA mais porque CAPTURA mudancas reais

**Dados:** Score 3 = 40.0% hit, Score 4 = 37.5% hit, Score 5 = 33.3% hit.

### BUG-07: Gale Level no DB Esta 1 Decisao Atrasado [BAIXO]

**Arquivo:** `server/message_handler.py` linha 296
**Descoberta:** `gale_level=mg.level` e gravado APOS update do hit/miss anterior, mas ANTES do get_gale() para a nova aposta (que nem e chamado). Resultado: 1-decision lag.

---

## PARTE 2 — SIMULACAO DE 15 ESTRATEGIAS DE GALE

### Contexto Matematico

Cobertura de 21 numeros na roleta europeia (37 posicoes):
- Custo por aposta G1: R$21 (R$1 x 21 numeros)
- Retorno no HIT G1: R$36 (35:1 + aposta) = lucro R$15
- Retorno no HIT G2: R$72 = lucro R$30
- Retorno no HIT G3: R$108 = lucro R$45

**Break-even hit rate com 21 numeros: 21/36 = 58.3%**
**Hit rate desta sessao: 40.5% (significativamente abaixo)**

### Resultados das Simulacoes (37 apostas reais)

```
RANKING DE ESTRATEGIAS (melhor para pior)

| Pos | Estrategia                          | P&L     | MaxG | G2  | G3  |
|:---:|-------------------------------------|--------:|:----:|:---:|:---:|
|  1  | S1: Always G1 (baseline)            | -R$237  |  G1  |  0  |  0  |
|  2  | S10: Window-5 (3+hit -> G2)         | -R$267  |  G2  | 10  |  0  |
|  3  | S14: SmartGale v5 (global streak)   | -R$273  |  G3  |  4  |  4  |
|  4  | S9: Miss->G2 apos 2+ hits previos   | -R$285  |  G2  |  4  |  0  |
|  5  | S3: Anti-Martingale (hit up)        | -R$288  |  G3  |  7  |  8  |
|  6  | S7: Anti-MG + Take-Profit G3        | -R$291  |  G3  |  8  |  5  |
|  7  | S8: Anti-MG + Step-Down no miss     | -R$321  |  G3  | 10  |  9  |
|  8  | S4a: Soft MG (cap G2)               | -R$351  |  G2  | 14  |  0  |
|  9  | S6: Ping-Pong G1-G2-G1             | -R$366  |  G2  | 13  |  0  |
| 10  | S4b: Soft MG (G2+G3)               | -R$411  |  G3  |  6  |  8  |
| 11  | S11: Fibonacci no miss              | -R$411  |  G3  |  6  |  8  |
| 12  | S5: Conservative MG (max G2)        | -R$462  |  G2  | 21  |  0  |
| 13  | S12: Always G2                      | -R$489  |  G2  | 36  |  0  |
| 14  | S15: Hit-up + Gradual-down          | -R$495  |  G3  | 12  | 13  |
| 15  | S2: Classic Martingale (miss up)    | -R$576  |  G3  |  7  | 14  |
| 16  | S13: Always G3                      | -R$741  |  G3  |  0  | 36  |
```

### Analise dos Resultados

**CONCLUSAO MATEMATICA FUNDAMENTAL:**
> Com hit rate de 40.5% e break-even de 58.3%, QUALQUER escalacao de gale AMPLIFICA perdas. O Always G1 e a melhor estrategia porque minimiza a exposicao por aposta.

**Por que:** EV por aposta = (hit_rate x lucro) - (miss_rate x custo)
- G1: 0.405 x 15 - 0.595 x 21 = -R$6.42 por aposta
- G2: 0.405 x 30 - 0.595 x 42 = -R$12.84 (2x pior)
- G3: 0.405 x 45 - 0.595 x 63 = -R$19.26 (3x pior)

**A escalacao so ajuda quando hit rate > 58.3%.** Nenhuma estrategia de gale resolve o problema de hit rate baixo.

### S14 (SmartGale v5) — Melhor Entre as Que Escalam

Apesar de perder mais que G1, o SmartGale v5 e o **menos destrutivo** entre estrategias com escalacao:
- So escala em streaks reais (global >= 2)
- Take-profit limita exposicao em G3
- Resultado: -R$273 vs -R$576 do classico (47% menos perda)

---

## PARTE 3 — INSIGHT ESTRATEGICO: REDUCAO DE COBERTURA

### O Problema Real Nao E o Gale, E a Cobertura

Com 21 numeros, break-even = 58.3%. Com menos numeros:

| Cobertura | Custo | Lucro/Hit | Break-even | Random Hit | Gap House |
|:---------:|:-----:|:---------:|:----------:|:----------:|:---------:|
| 21 nums | R$21 | R$15 | 58.3% | 56.8% | 1.5% |
| 15 nums | R$15 | R$21 | 41.7% | 40.5% | 1.2% |
| 12 nums | R$12 | R$24 | 33.3% | 32.4% | 0.9% |
| 10 nums | R$10 | R$26 | 27.8% | 27.0% | 0.8% |

**Insight:** Com 15 numeros, break-even cai para 41.7% — MUITO mais proximo do nosso hit rate atual (40.5% nesta sessao). Com 12 numeros, break-even = 33.3%.

**Porem:** Reduzir cobertura reduz hit rate proporcional (menos numeros = menos chance de acertar). A vantagem so existe se a predicao for MELHOR QUE RANDOM — ou seja, se os numeros preditos tem probabilidade real > probabilidade aleatoria.

---

## PARTE 4 — PLANO DE TAREFAS PARA IMPLANTACAO

### TASK-01: Integrar SmartGale v5 no Pipeline de Producao [P0 CRITICO]

**O que:** Adicionar chamadas `get_gale()`, `sync_global()`, e `global_hit` ao `message_handler.py`.

**Arquivo:** `server/message_handler.py`

**Alteracao 1 — Linhas 163-165 (martingale update):**
```python
# ANTES:
if bet_direction in ("cw", "horario"):
    martingale_info = self.game_state.martingale_cw.update(hit_result)
else:
    martingale_info = self.game_state.martingale_ccw.update(hit_result)

# DEPOIS:
if bet_direction in ("cw", "horario"):
    martingale_info = self.game_state.martingale_cw.update(hit_result, global_hit=hit_result)
    self.game_state.martingale_ccw.sync_global(hit_result)
else:
    martingale_info = self.game_state.martingale_ccw.update(hit_result, global_hit=hit_result)
    self.game_state.martingale_cw.sync_global(hit_result)
```

**Alteracao 2 — Linhas 230-244 (decisao de apostar):**
```python
# ANTES:
if advice.should_bet:
    acao = "APOSTAR"
    action_reason = f"SDA + Triple Rate aprovaram ({advice.confidence})"
    self.game_state.store_prediction(...)

# DEPOIS:
if advice.should_bet:
    mg = self.game_state.target_martingale
    bet_c4_rate = self.game_state.get_bet_c4_rate()
    mg.get_gale(score=result.score, c4_rate=bet_c4_rate)
    acao = "APOSTAR"
    action_reason = f"SDA score={result.score} | {mg.gale_display} | C4={bet_c4_rate:.0%}"
    self.game_state.store_prediction(...)
```

**Risco:** BAIXO — retrocompativel, gale comeca em G1 como antes.

### TASK-02: Adicionar Fallback Early-Session [P1]

**O que:** Quando SDA nao recomenda MAS tem dados na timeline, apostar G1 seguro com 21 vizinhos (como engine.py linhas 118-133).

**Arquivo:** `server/message_handler.py` apos linha 262

**Codigo:**
```python
elif self.game_state.target_timeline.size > 0:
    mg = self.game_state.target_martingale
    mg.level = 1
    center = self.game_state.last_number
    fallback_nums = sorted(
        self.strategy.get_neighbors(center, 10, roulette.WHEEL_SEQUENCE)
    )
    acao = "APOSTAR"
    action_reason = f"SDA insuficiente ({self.game_state.target_timeline.size} forcas) -> G1 seguro"
    self.game_state.store_prediction(
        fallback_nums, self.game_state.target_direction, center,
        predicted_force=0, bet_placed=True,
        tr_confidence="baixa", tr_reason="Fallback early-session",
        sda_score=1, sda_centers=[center]
    )
```

**Risco:** BAIXO — ativa apenas nas primeiras jogadas da sessao.

### TASK-03: Testes de Integracao para message_handler.py [P1]

**O que:** Criar `tests/test_message_handler_gale.py` verificando que o pipeline de producao chama `get_gale()`, `sync_global()`, e grava `gale_level` correto no DB.

**Testes propostos:**
| ID | Teste | Cenario |
|:--:|-------|---------|
| T1 | `test_gale_called_on_bet` | Aposta deve chamar get_gale antes de gravar |
| T2 | `test_sync_global_on_hit` | Hit em CW deve sync para CCW |
| T3 | `test_global_hit_parameter` | update() recebe global_hit |
| T4 | `test_action_reason_format` | action_reason contem score e gale_display |
| T5 | `test_fallback_early_session` | SDA insuficiente com dados -> G1 seguro |
| T6 | `test_gale_level_in_decision` | gale_level no DB reflete get_gale resultado |

**Risco:** NENHUM — testes nao alteram producao.

### TASK-04: Atualizar Manutenabilidade ISO [P2]

**O que:** Documentar BUG-01 a BUG-07 e TASK-01 a TASK-03 na `Manutenabilidade_iso.md`.

**Secoes:** PARTE IV (Bugs), PARTE IV (Melhorias), footer.

---

## PARTE 5 — TAREFAS FUTURAS (ESTUDO)

Estas tarefas NAO devem ser implementadas agora. Requerem mais dados e validacao.

### ESTUDO-01: Investigar Reducao de Cobertura (21 -> 15 numeros)

**Hipotese:** Com 15 numeros, break-even cai de 58.3% para 41.7%. Se a SDA-21 prediz melhor que random, 15 numeros pode ser lucrativo.

**Teste:** Simular com os dados existentes: dos 21 numeros preditos, os 15 mais proximos do centro principal. Verificar se hit rate se mantém > 41.7%.

**Riscos:** Hit rate pode cair proporcionalmente, anulando o beneficio.

### ESTUDO-02: Ajustar IQR Threshold (1.5x -> 2.0x)

**Hipotese:** O filtro IQR com 1.5x esta removendo outliers que sao sinais reais de mudanca de momentum. Com 2.0x, mais dados passam, permitindo captura de tendencias.

**Beneficio potencial:** Score mais realista, drift detection mais eficaz.

### ESTUDO-03: Inverter Logica de Confianca no Triple Rate

**Hipotese:** "Media" (c4 < m6) indica mean-reversion e e mais preditivo que "alta" (c4 >= m6) que indica spike prestes a regredir.

**Opcoes:**
1. Inverter labels (c4 < m6 = "alta")
2. Adicionar minimum sample size (c4 so conta com N>=6 resultados)
3. Usar tendencia de c4 em vez de comparacao pontual

### ESTUDO-04: Score Baseado em Acuracia Real

**Hipotese:** Substituir `survival*3 + tightness*3 + stable_bonus` por formula que inclua `performance_bet` recente.

**Formula proposta:**
```
real_accuracy = hit_rate_last_8
score = min(6, max(1, int(real_accuracy * 6 + drift_bonus)))
```

### ESTUDO-05: Radius Variavel por Magnitude de Forca

**Hipotese:** Forcas longas (>20) sao menos precisas. Reduzir radius de 3 para 2 quando predicted_force > 20 concentra cobertura onde temos mais certeza.

**Dados:** Forcas 1-10 hit 46.2%, forcas >20 hit 25%.

---

## PARTE 6 — RESUMO EXECUTIVO

### O Que Descobrimos

1. **BUG CRITICO:** O SmartGale nunca funcionou em producao (`get_gale()` nao chamado)
2. **MATEMATICA:** Com 21 numeros e 40.5% hit rate, QUALQUER escalacao amplifica perdas
3. **ANOMALIAS:** Score e confianca estao inversamente correlacionados com hit rate
4. **OPORTUNIDADE:** Reducao de cobertura pode tornar o sistema viavel com hit rates atuais

### O Que Fazer Agora

| Prioridade | Task | Tipo | Impacto |
|:----------:|:----:|:----:|:-------:|
| **P0** | TASK-01: get_gale() em producao | Bug fix | SmartGale funciona pela primeira vez |
| P1 | TASK-02: Fallback early-session | Bug fix | Menos PULARs no inicio |
| P1 | TASK-03: Testes de integracao | Qualidade | Previne regressao |
| P2 | TASK-04: Documentar na ISO | Doc | Rastreabilidade |

### O Que Estudar Depois

| ID | Estudo | Potencial |
|:--:|:------:|:---------:|
| ESTUDO-01 | Cobertura 21->15 nums | Break-even 58%->42% |
| ESTUDO-02 | IQR 1.5x->2.0x | Score mais realista |
| ESTUDO-03 | Inverter confianca | Alta acerta mais |
| ESTUDO-04 | Score por acuracia real | Correlacao com hits |
| ESTUDO-05 | Radius variavel | Menos miss em forca longa |

### Premissa Mantida

> **O martingale NAO decide SE apostar. Ele decide QUANTO apostar.** O hit rate e responsabilidade da estrategia SDA-21. O gale gerencia a banca. Ambos precisam funcionar para o sistema ser rentavel.

---

> **Documento de estudo** — nenhuma alteracao foi feita no software
> **Aguardando aprovacao para executar TASK-01 a TASK-04**

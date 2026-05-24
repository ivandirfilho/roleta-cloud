# Resultados 02/04 - Auditoria Cronologica dos Resultados do Dia

> **Data analisada:** 02/04/2026  
> **Base de dados:** 306 decisoes exportadas do servidor de producao  
> **Janela:** 17:32:25 -> 21:21:30  
> **Estrategia alvo:** SDA17 M15-ADA v4.3 (M02-PctSigmoid) + fallback early-session + Martingale

---

## 1. Resumo executivo

| Metrica | Valor | Status |
|---|---:|---|
| Decisoes totais | 306 | Base completa do dia |
| Horario (CW) | 153 | Separado e auditado |
| Anti-horario (CCW) | 153 | Separado e auditado |
| Apostas verificadas | 271 | 21 ainda pendentes no fechamento da coleta |
| Hit rate geral | 123/271 = 45.4% | Abaixo do break-even teorico de 47.2% |
| Hit rate CW | 62/134 = 46.3% | Levemente acima do geral |
| Hit rate CCW | 61/137 = 44.5% | Levemente abaixo do CW |
| Divergencias de logging no warmup | 14 | Bug real identificado |
| Cobertura nominal por aposta valida | 17 numeros (45.9% da roda) | Aderente ao Triple Focus 7+5+5 |

**Conclusao curta:** o fluxo principal da estrategia esta rodando como SDA17 v4.3 na maior parte do dia, com offsets sigmoid, score 3-6 e cobertura fixa de 17 numeros. A divergencia real encontrada hoje esta no logging do fallback early-session: o sistema aposta em G1 seguro, mas o banco persiste `sda_score=0`, `sda_center=0` e `sda_numbers=[]`, o que mascara a previsao real nos registros de warmup.

---

## 2. Estrategia esperada e fluxo de dados auditado

Fluxo esperado do software para cada spin:

1. A extensao captura o resultado da mesa e envia `{numero, direcao}` ao servidor.
2. O servidor verifica a previsao pendente anterior (`check_prediction`) e atualiza martingale/performance.
3. O spin atual entra na timeline do sentido-alvo e gera uma nova `force` circular.
4. O `SDA17Strategy.analyze()` roda o pipeline: janela adaptativa -> IQR -> weighted median -> drift -> Smart Score -> Triple Focus com offsets sigmoid.
5. Se `should_bet=True`, a estrategia produz C1/C2/C3, 17 numeros e score 3-6; se ainda esta em warmup, o sistema cai no fallback `G1 seguro` quando ja existe ao menos 1 forca.
6. O minidashboard recebe a sugestao e a caixa de vidro deveria registrar tanto a sugestao quanto o desfecho.

**Aderencia encontrada no codigo:**

- `strategies/sda17.py` confirma M15-ADA v4.3 com `BAYESIAN_DEFAULT=10`, `BAYESIAN_WARMUP=2`, offsets `sigmoid` e cobertura 17 numeros.
- `server/message_handler.py` implementa fallback early-session: quando o SDA ainda nao recomenda mas a timeline ja tem dados, ele muda a acao para `APOSTAR` e grava uma previsao de 21 numeros centrada no ultimo numero (`G1 seguro`).
- **Bug de persistencia:** ao salvar `Decision`, o handler continua usando `result.score`, `result.center`, `result.numbers` e `result.should_bet`, em vez dos valores efetivamente usados pelo fallback. Resultado: o banco registra `final_action=APOSTAR`, mas com campos SDA vazios do warmup.**

---

## 3. Achados reais da auditoria de hoje

1. **Bug real de logging no warmup/fallback:** 14 registros aparecem como `APOSTAR`, mas no banco ficaram com `sda_score=0`, `sda_center=0`, `sda_numbers=[]`. O fallback G1 seguro existiu na execucao, porem nao ficou representado corretamente na linha gravada em `decisions`.
2. **A estrategia principal esta aderente fora do warmup:** 278 decisoes usaram offsets `sigmoid` com score 3-6 e cobertura fixa de 17 numeros, coerente com o M15-ADA v4.3.
3. **Offset 12 dominou e performou mal:** foi o offset mais frequente do dia, mas ficou pior que 11 e 13 nos dois sentidos. Isso sugere convergencia subotima do controlador M02-PctSigmoid nesta amostra.
4. **CW foi mais volatil no fim do dia:** houve uma sequencia de 12 misses consecutivos entre 21:03 e 21:18, derrubando o fechamento do horario.
5. **CCW foi mais estavel, mas tambem abaixo do esperado:** menor pior sequencia que CW, porem ainda abaixo do break-even teorico.

---

## 3.1 Confirmacao explicita: a estrategia esta sendo usada dos dois lados

Sim. A auditoria confirma que o **SDA17 M15-ADA v4.3 com offsets `sigmoid` esta ativo nos dois sentidos**:

- No codigo, `strategies/sda17.py` mantem **historicos independentes** (`cw_history` e `ccw_history`) e tambem offsets independentes em `_sigmoid_off`.
- O metodo `_get_adaptive_offset()` resolve `dir_key = "cw"` para horario e `dir_key = "ccw"` para anti-horario, sem misturar estados.
- O metodo `_pct_sigmoid_update()` atualiza `cw_off2/cw_off3` ou `ccw_off2/ccw_off3` conforme a direcao do spin analisado.
- Nos dados de hoje, houve **139 decisoes com `sda_offset_type=sigmoid` em CW** e **139 decisoes com `sda_offset_type=sigmoid` em CCW**.
- Fora das 14 divergencias de warmup/fallback, os dois lados exibiram centros `[C1,C2,C3]`, score 3-6 e cobertura nominal de 17 numeros, exatamente como esperado pela estrategia.

**Conclusao desta verificacao:** o problema de hoje **nao** e “a estrategia rodar so de um lado”. Ela esta sendo usada em **horario e anti-horario**. O problema real e que a adaptacao atual nao escolheu os melhores offsets para o regime do dia, e o warmup/fallback ficou mal representado no banco.

---

## 4. Analise isolada - Horario (CW)

### Resumo Horario (CW)

| Metrica | Valor |
|---|---:|
| Decisoes | 153 |
| APOSTAR | 146 |
| PULAR | 7 |
| Apostas verificadas | 134 |
| Hits | 62 |
| Hit rate | 46.3% |
| Max streak de hits | 6 |
| Max streak de misses | 12 |
| Decisoes pendentes | 12 |
| Scores | {0: 14, 3: 37, 4: 96, 5: 5, 6: 1} |

**Offsets por performance**

| Offset | Hits | Total | HR |
|---:|---:|---:|---:|
| 11 | 13 | 26 | 50.0% |
| 12 | 32 | 75 | 42.7% |
| 13 | 17 | 33 | 51.5% |

**Gales verificados**

| Gale | Hits | Total | HR |
|---:|---:|---:|---:|
| G2 | 4 | 4 | 100.0% |
| G3 | 4 | 7 | 57.1% |


**Leitura tecnica do sentido horario:**

- O warmup inicial alternou entre `PULAR` puro e fallback `G1 seguro`; os registros com score zero e numeros vazios nao significam ausencia de aposta, e sim falha de persistencia do contexto do fallback.
- Depois do warmup, o CW operou quase sempre com score 4, offset 12/13 e Triple Focus 17 numeros.
- O melhor trecho do CW ocorreu entre 20:24 e 21:00, quando fez 15 hits em 20 apostas (75%).
- O pior trecho do CW ocorreu entre 21:03 e 21:18, com 12 misses seguidos; nessa faixa, os centros e offsets continuaram aderentes ao algoritmo, mas a roda caiu repetidamente fora da cobertura prevista.

### Registro cronologico completo - Horario (CW)

| # | Hora | F | PF | Centros | Off | Score | Gale | Acao | Resultado | Leitura |
|---:|:----:|--:|---:|:--------|---:|------:|:----:|:-----|:----------|:--------|
| 1 | 17:33:17 | 19 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 2 | 17:34:51 | 17 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 3 | 17:36:21 | 0 | 4 | `[3, 34, 14]` | 11 | 4 | G1 | APOSTAR | MISS (8) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 4 | 17:37:51 | 34 | 23 | `[9, 15, 23]` | 12 | 4 | G1 | APOSTAR | MISS (11) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 5 | 17:39:27 | 4 | 37 | `[10, 29, 17]` | 12 | 3 | G1 | APOSTAR | HIT (2) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 6 | 17:40:55 | 27 | 23 | `[6, 33, 0]` | 12 | 4 | G1 | APOSTAR | MISS (30) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 7 | 17:42:25 | 28 | 18 | `[14, 32, 30]` | 13 | 4 | G1 | APOSTAR | MISS (4) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 8 | 17:43:55 | 35 | 15 | `[20, 0, 11]` | 13 | 4 | G1 | APOSTAR | HIT (15) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 9 | 17:45:20 | 12 | 1 | `[36, 31, 19]` | 13 | 3 | G1 | APOSTAR | MISS (28) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 10 | 17:46:48 | 6 | 18 | `[24, 28, 34]` | 12 | 4 | G1 | APOSTAR | MISS (21) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 11 | 17:48:18 | 34 | 35 | `[4, 8, 18]` | 12 | 3 | G1 | APOSTAR | HIT (29) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 12 | 17:49:54 | 17 | 10 | `[0, 13, 31]` | 12 | 4 | G1 | APOSTAR | MISS (29) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 13 | 17:51:24 | 30 | 17 | `[2, 10, 28]` | 12 | 4 | G1 | APOSTAR | HIT (25) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 14 | 17:53:00 | 35 | 16 | `[31, 32, 30]` | 12 | 4 | G1 | APOSTAR | MISS (28) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 15 | 17:54:28 | 14 | 13 | `[12, 34, 33]` | 13 | 3 | G1 | APOSTAR | MISS (4) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 16 | 17:56:06 | 0 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 17 | 17:57:36 | 32 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 18 | 17:59:10 | 34 | 18 | `[34, 33, 35]` | 13 | 4 | G1 | APOSTAR | MISS (4) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 19 | 18:00:40 | 8 | 28 | `[16, 12, 17]` | 12 | 3 | G1 | APOSTAR | HIT (3) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 20 | 18:02:15 | 23 | 18 | `[19, 30, 22]` | 12 | 5 | G1 | APOSTAR | HIT (30) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 21 | 18:03:51 | 7 | 6 | `[8, 22, 4]` | 12 | 3 | G1 | APOSTAR | MISS (35) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 22 | 18:05:27 | 19 | 18 | `[3, 27, 1]` | 13 | 4 | G1 | APOSTAR | HIT (20) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 23 | 18:06:57 | 25 | 34 | `[30, 22, 19]` | 13 | 3 | G1 | APOSTAR | HIT (21) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 24 | 18:08:41 | 3 | 16 | `[18, 21, 23]` | 13 | 4 | G1 | APOSTAR | HIT (28) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 25 | 18:10:19 | 33 | 13 | `[30, 9, 4]` | 12 | 4 | G2 | APOSTAR | HIT (18) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 26 | 18:11:57 | 27 | 33 | `[1, 3, 13]` | 12 | 3 | G1 | APOSTAR | HIT (12) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 27 | 18:13:35 | 19 | 23 | `[18, 4, 10]` | 12 | 4 | G1 | APOSTAR | MISS (1) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 28 | 18:15:07 | 5 | 27 | `[32, 36, 31]` | 12 | 4 | G1 | APOSTAR | HIT (26) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 29 | 18:16:53 | 28 | 29 | `[3, 6, 1]` | 12 | 4 | G1 | APOSTAR | HIT (14) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 30 | 18:18:28 | 9 | 23 | `[27, 33, 26]` | 11 | 4 | G1 | APOSTAR | MISS (18) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 31 | 18:20:08 | 16 | 13 | `[28, 17, 16]` | 13 | 4 | G1 | APOSTAR | MISS (10) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 32 | 18:21:45 | 10 | 37 | `[22, 4, 8]` | 13 | 3 | G1 | APOSTAR | HIT (31) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 33 | 18:23:20 | 24 | 5 | `[17, 24, 12]` | 12 | 4 | G1 | APOSTAR | HIT (27) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 34 | 18:25:00 | 5 | 2 | `[11, 31, 19]` | 12 | 4 | G3 | APOSTAR | HIT (27) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 35 | 18:26:40 | 16 | 5 | `[33, 35, 27]` | 12 | 4 | G1 | APOSTAR | pendente | Aderente ao M15-ADA v4.3; resultado ainda nao confirmado. |
| 36 | 18:28:10 | 9 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 37 | 18:29:48 | 1 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 38 | 18:31:22 | 28 | 3 | `[27, 1, 0]` | 12 | 4 | G3 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 39 | 18:32:58 | 24 | 18 | `[15, 11, 9]` | 12 | 4 | G1 | APOSTAR | MISS (33) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 40 | 18:34:40 | 24 | 34 | `[13, 1, 26]` | 11 | 3 | G1 | APOSTAR | MISS (23) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 41 | 18:36:11 | 27 | 29 | `[30, 9, 15]` | 12 | 4 | G1 | APOSTAR | HIT (4) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 42 | 18:37:49 | 21 | 2 | `[1, 3, 27]` | 12 | 3 | G3 | APOSTAR | MISS (15) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 43 | 18:39:21 | 31 | 23 | `[6, 1, 3]` | 13 | 4 | G1 | APOSTAR | HIT (25) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 44 | 18:40:57 | 7 | 35 | `[8, 22, 4]` | 12 | 3 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 45 | 18:42:25 | 0 | 31 | `[1, 3, 27]` | 12 | 3 | G1 | APOSTAR | MISS (17) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 46 | 18:44:03 | 7 | 24 | `[22, 19, 8]` | 12 | 4 | G1 | APOSTAR | MISS (28) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 47 | 18:45:43 | 11 | 20 | `[1, 3, 27]` | 12 | 4 | G1 | APOSTAR | MISS (17) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 48 | 18:47:21 | 18 | 37 | `[31, 32, 11]` | 12 | 3 | G1 | APOSTAR | MISS (21) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 49 | 18:49:01 | 22 | 21 | `[2, 5, 7]` | 13 | 4 | G1 | APOSTAR | MISS (35) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 50 | 18:50:41 | 14 | 28 | `[24, 12, 25]` | 13 | 4 | G1 | APOSTAR | MISS (27) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 51 | 18:52:15 | 23 | 21 | `[36, 31, 0]` | 13 | 4 | G1 | APOSTAR | HIT (22) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 52 | 18:53:54 | 26 | 9 | `[17, 24, 28]` | 12 | 4 | G1 | APOSTAR | HIT (2) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 53 | 18:55:30 | 26 | 16 | `[8, 22, 19]` | 12 | 3 | G1 | APOSTAR | HIT (15) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 54 | 18:56:58 | 6 | 28 | `[23, 18, 21]` | 12 | 3 | G1 | APOSTAR | pendente | Aderente ao M15-ADA v4.3; resultado ainda nao confirmado. |
| 55 | 18:58:28 | 22 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 56 | 19:00:00 | 28 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 57 | 19:01:24 | 21 | 6 | `[26, 27, 1]` | 12 | 4 | G1 | APOSTAR | MISS (18) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 58 | 19:03:04 | 18 | 13 | `[35, 17, 16]` | 11 | 4 | G1 | APOSTAR | HIT (6) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 59 | 19:04:36 | 1 | 6 | `[21, 8, 18]` | 11 | 5 | G1 | APOSTAR | HIT (19) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 60 | 19:05:58 | 36 | 8 | `[7, 21, 10]` | 11 | 4 | G1 | APOSTAR | HIT (7) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 61 | 19:07:22 | 13 | 8 | `[26, 6, 20]` | 11 | 5 | G1 | APOSTAR | MISS (25) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 62 | 19:08:51 | 33 | 8 | `[28, 2, 24]` | 11 | 4 | G1 | APOSTAR | MISS (15) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 63 | 19:10:19 | 26 | 1 | `[9, 15, 30]` | 12 | 5 | G1 | APOSTAR | MISS (21) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 64 | 19:11:51 | 12 | 8 | `[34, 16, 35]` | 12 | 4 | G1 | APOSTAR | HIT (12) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 65 | 19:13:19 | 0 | 8 | `[14, 0, 36]` | 12 | 4 | G1 | APOSTAR | HIT (22) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 66 | 19:14:51 | 26 | 1 | `[8, 22, 4]` | 12 | 3 | G1 | APOSTAR | MISS (6) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 67 | 19:16:15 | 26 | 7 | `[18, 4, 8]` | 12 | 4 | G1 | APOSTAR | MISS (1) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 68 | 19:17:49 | 6 | 14 | `[30, 9, 15]` | 12 | 3 | G1 | APOSTAR | HIT (8) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 69 | 19:19:11 | 24 | 13 | `[9, 32, 11]` | 11 | 4 | G1 | APOSTAR | MISS (6) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 70 | 19:20:37 | 30 | 13 | `[9, 32, 11]` | 11 | 4 | G1 | APOSTAR | MISS (2) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 71 | 19:21:57 | 26 | 31 | `[32, 36, 14]` | 12 | 3 | G1 | APOSTAR | HIT (3) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 72 | 19:23:27 | 0 | 30 | `[21, 23, 18]` | 12 | 4 | G1 | APOSTAR | MISS (16) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 73 | 19:24:58 | 17 | 22 | `[8, 18, 4]` | 13 | 4 | G1 | APOSTAR | MISS (32) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 74 | 19:26:26 | 14 | 1 | `[11, 31, 32]` | 12 | 3 | G1 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 75 | 19:27:54 | 25 | 19 | `[15, 11, 31]` | 12 | 4 | G1 | APOSTAR | MISS (1) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 76 | 19:29:22 | 10 | 37 | `[12, 17, 24]` | 12 | 3 | G1 | APOSTAR | MISS (18) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 77 | 19:30:50 | 32 | 16 | `[17, 24, 28]` | 12 | 4 | G1 | APOSTAR | MISS (11) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 78 | 19:32:18 | 10 | 10 | `[11, 9, 32]` | 13 | 4 | G1 | APOSTAR | MISS (33) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 79 | 19:33:50 | 18 | 7 | `[12, 34, 16]` | 13 | 4 | G1 | APOSTAR | HIT (34) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 80 | 19:35:20 | 28 | 10 | `[9, 19, 30]` | 13 | 4 | G1 | APOSTAR | MISS (16) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 81 | 19:36:46 | 17 | 16 | `[33, 35, 34]` | 12 | 4 | G1 | APOSTAR | HIT (16) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 82 | 19:38:14 | 36 | 16 | `[4, 8, 22]` | 12 | 4 | G1 | APOSTAR | MISS (7) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 83 | 19:39:42 | 28 | 22 | `[0, 13, 20]` | 12 | 3 | G1 | APOSTAR | MISS (10) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 84 | 19:41:10 | 33 | 16 | `[3, 6, 33]` | 12 | 4 | G1 | APOSTAR | MISS (9) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 85 | 19:42:35 | 19 | 20 | `[31, 32, 36]` | 12 | 4 | G1 | APOSTAR | HIT (19) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 86 | 19:44:01 | 25 | 16 | `[13, 20, 26]` | 12 | 4 | G3 | APOSTAR | MISS (22) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 87 | 19:45:33 | 10 | 1 | `[0, 13, 20]` | 12 | 3 | G1 | APOSTAR | MISS (24) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 88 | 19:47:03 | 32 | 17 | `[3, 6, 33]` | 12 | 4 | G1 | APOSTAR | MISS (8) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 89 | 19:48:29 | 3 | 35 | `[16, 35, 34]` | 13 | 3 | G1 | APOSTAR | HIT (26) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 90 | 19:49:55 | 20 | 20 | `[26, 13, 20]` | 13 | 4 | G3 | APOSTAR | HIT (3) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 91 | 19:51:27 | 23 | 20 | `[32, 11, 31]` | 13 | 4 | G1 | APOSTAR | MISS (29) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 92 | 19:52:55 | 15 | 25 | `[24, 28, 25]` | 12 | 3 | G1 | APOSTAR | pendente | Aderente ao M15-ADA v4.3; resultado ainda nao confirmado. |
| 93 | 19:54:29 | 33 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 94 | 19:55:49 | 2 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 95 | 19:57:11 | 18 | 23 | `[30, 9, 19]` | 12 | 6 | G1 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 96 | 19:58:31 | 21 | 17 | `[0, 36, 14]` | 13 | 4 | G1 | APOSTAR | HIT (35) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 97 | 19:59:52 | 20 | 20 | `[35, 6, 33]` | 13 | 4 | G1 | APOSTAR | HIT (34) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 98 | 20:01:15 | 13 | 17 | `[21, 10, 29]` | 13 | 4 | G1 | APOSTAR | HIT (21) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 99 | 20:02:46 | 4 | 17 | `[18, 21, 23]` | 13 | 4 | G1 | APOSTAR | HIT (29) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 100 | 20:04:08 | 5 | 16 | `[5, 7, 25]` | 12 | 4 | G1 | APOSTAR | MISS (1) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 101 | 20:05:36 | 14 | 14 | `[1, 26, 13]` | 13 | 3 | G1 | APOSTAR | HIT (33) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 102 | 20:07:00 | 32 | 15 | `[15, 11, 22]` | 12 | 4 | G2 | APOSTAR | HIT (32) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 103 | 20:08:30 | 11 | 18 | `[7, 2, 24]` | 12 | 4 | G1 | APOSTAR | MISS (13) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 104 | 20:10:06 | 24 | 15 | `[16, 35, 6]` | 13 | 4 | G1 | APOSTAR | HIT (35) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 105 | 20:11:36 | 21 | 12 | `[2, 5, 28]` | 13 | 4 | G1 | APOSTAR | HIT (7) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 106 | 20:13:00 | 36 | 26 | `[4, 23, 29]` | 13 | 3 | G1 | APOSTAR | MISS (1) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 107 | 20:14:26 | 23 | 7 | `[15, 11, 9]` | 12 | 4 | G1 | APOSTAR | HIT (32) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 108 | 20:15:48 | 26 | 8 | `[5, 7, 25]` | 12 | 4 | G1 | APOSTAR | MISS (27) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 109 | 20:17:09 | 5 | 12 | `[4, 8, 18]` | 12 | 3 | G1 | APOSTAR | HIT (7) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 110 | 20:18:37 | 33 | 23 | `[4, 8, 18]` | 12 | 3 | G1 | APOSTAR | MISS (26) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 111 | 20:19:57 | 11 | 28 | `[5, 29, 2]` | 11 | 3 | G1 | APOSTAR | MISS (32) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 112 | 20:21:25 | 5 | 16 | `[9, 32, 11]` | 11 | 4 | G1 | APOSTAR | MISS (24) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 113 | 20:22:51 | 8 | 22 | `[2, 23, 29]` | 11 | 4 | G1 | APOSTAR | HIT (22) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 114 | 20:24:13 | 23 | 16 | `[3, 34, 33]` | 11 | 4 | G2 | APOSTAR | HIT (12) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 115 | 20:25:47 | 0 | 18 | `[30, 31, 15]` | 11 | 4 | G1 | APOSTAR | HIT (4) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 116 | 20:27:15 | 15 | 36 | `[24, 7, 17]` | 11 | 3 | G1 | APOSTAR | MISS (3) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 117 | 20:28:45 | 36 | 21 | `[36, 20, 32]` | 11 | 4 | G1 | APOSTAR | HIT (13) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 118 | 20:30:13 | 31 | 21 | `[33, 12, 6]` | 11 | 4 | G1 | APOSTAR | MISS (26) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 119 | 20:31:45 | 11 | 21 | `[31, 32, 11]` | 12 | 4 | G1 | APOSTAR | HIT (9) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 120 | 20:33:15 | 9 | 20 | `[8, 9, 4]` | 11 | 4 | G1 | APOSTAR | HIT (10) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 121 | 20:34:46 | 36 | 18 | `[26, 6, 20]` | 11 | 4 | G1 | APOSTAR | MISS (28) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 122 | 20:36:14 | 21 | 21 | `[28, 2, 24]` | 11 | 5 | G1 | APOSTAR | HIT (21) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 123 | 20:37:46 | 12 | 18 | `[26, 6, 20]` | 11 | 4 | G1 | APOSTAR | pendente | Aderente ao M15-ADA v4.3; resultado ainda nao confirmado. |
| 124 | 20:39:18 | 8 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 125 | 20:40:50 | 7 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 126 | 20:42:18 | 12 | 3 | `[32, 13, 31]` | 11 | 4 | G1 | APOSTAR | HIT (36) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 127 | 20:43:52 | 36 | 23 | `[31, 0, 30]` | 11 | 4 | G1 | APOSTAR | HIT (14) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 128 | 20:45:22 | 8 | 24 | `[34, 24, 3]` | 11 | 4 | G1 | APOSTAR | HIT (3) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 129 | 20:46:58 | 28 | 24 | `[15, 36, 22]` | 11 | 4 | G1 | APOSTAR | MISS (17) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 130 | 20:48:26 | 13 | 24 | `[35, 34, 1]` | 12 | 4 | G1 | APOSTAR | HIT (33) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 131 | 20:50:31 | 10 | 28 | `[4, 8, 29]` | 12 | 4 | G3 | APOSTAR | HIT (15) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 132 | 20:51:57 | 17 | 30 | `[31, 0, 30]` | 11 | 4 | G3 | APOSTAR | HIT (11) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 133 | 20:53:19 | 0 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 134 | 20:54:47 | 10 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 135 | 20:56:11 | 8 | 32 | `[1, 3, 13]` | 12 | 4 | G2 | APOSTAR | HIT (0) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 136 | 20:57:41 | 16 | 18 | `[3, 6, 20]` | 12 | 4 | G1 | APOSTAR | HIT (27) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 137 | 20:59:05 | 8 | 5 | `[11, 31, 4]` | 12 | 3 | G1 | APOSTAR | HIT (31) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 138 | 21:00:29 | 8 | 18 | `[8, 22, 2]` | 12 | 4 | G1 | APOSTAR | MISS (24) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 139 | 21:01:59 | 34 | 18 | `[26, 27, 31]` | 12 | 4 | G1 | APOSTAR | HIT (3) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 140 | 21:03:29 | 28 | 18 | `[17, 24, 3]` | 12 | 4 | G1 | APOSTAR | MISS (13) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 141 | 21:04:53 | 20 | 14 | `[10, 29, 17]` | 12 | 4 | G1 | APOSTAR | MISS (33) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 142 | 21:06:19 | 8 | 10 | `[24, 28, 6]` | 12 | 3 | G1 | APOSTAR | MISS (22) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 143 | 21:07:45 | 27 | 4 | `[11, 9, 4]` | 13 | 3 | G1 | APOSTAR | MISS (5) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 144 | 21:09:02 | 11 | 14 | `[8, 18, 2]` | 13 | 4 | G1 | APOSTAR | MISS (26) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 145 | 21:10:28 | 8 | 19 | `[14, 32, 11]` | 13 | 4 | G1 | APOSTAR | MISS (10) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 146 | 21:11:52 | 3 | 21 | `[0, 13, 14]` | 12 | 3 | G1 | APOSTAR | MISS (4) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 147 | 21:13:20 | 13 | 14 | `[19, 30, 22]` | 12 | 3 | G1 | APOSTAR | MISS (26) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 148 | 21:14:44 | 11 | 18 | `[18, 4, 23]` | 12 | 4 | G1 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 149 | 21:16:06 | 6 | 18 | `[16, 35, 34]` | 13 | 4 | G1 | APOSTAR | MISS (4) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 150 | 21:17:22 | 18 | 22 | `[0, 13, 20]` | 12 | 4 | G1 | APOSTAR | MISS (7) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 151 | 21:18:40 | 30 | 28 | `[12, 17, 24]` | 12 | 4 | G1 | APOSTAR | MISS (30) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 152 | 21:20:04 | 21 | 5 | `[7, 2, 10]` | 12 | 3 | G1 | APOSTAR | HIT (21) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 153 | 21:21:30 | 10 | 28 | `[20, 26, 27]` | 12 | 4 | G1 | APOSTAR | pendente | Aderente ao M15-ADA v4.3; resultado ainda nao confirmado. |

---

## 5. Analise isolada - Anti-horario (CCW)

### Resumo Anti-horario (CCW)

| Metrica | Valor |
|---|---:|
| Decisoes | 153 |
| APOSTAR | 146 |
| PULAR | 7 |
| Apostas verificadas | 137 |
| Hits | 61 |
| Hit rate | 44.5% |
| Max streak de hits | 5 |
| Max streak de misses | 8 |
| Decisoes pendentes | 9 |
| Scores | {0: 14, 3: 38, 4: 90, 5: 5, 6: 6} |

**Offsets por performance**

| Offset | Hits | Total | HR |
|---:|---:|---:|---:|
| 10 | 0 | 1 | 0.0% |
| 11 | 9 | 16 | 56.2% |
| 12 | 24 | 61 | 39.3% |
| 13 | 28 | 59 | 47.5% |

**Gales verificados**

| Gale | Hits | Total | HR |
|---:|---:|---:|---:|
| G2 | 5 | 10 | 50.0% |
| G3 | 1 | 3 | 33.3% |


**Leitura tecnica do sentido anti-horario:**

- O CCW encaixou melhor no inicio do dia do que o CW, inclusive com score 6 logo na terceira decisao valida.
- O offset 11 foi o melhor do CCW; o offset 12 voltou a ser o pior, reforcando a leitura de convergencia para uma zona nao otima.
- O pior trecho do CCW foi entre 18:56 e 19:09, com 8 misses seguidos; ainda assim, o CCW recuperou melhor depois e fechou o dia sem colapso comparavel ao do CW.
- O fechamento do CCW entre 21:08 e 21:14 foi forte, com 5 hits consecutivos antes de nova queda pontual.

### Registro cronologico completo - Anti-horario (CCW)

| # | Hora | F | PF | Centros | Off | Score | Gale | Acao | Resultado | Leitura |
|---:|:----:|--:|---:|:--------|---:|------:|:----:|:-----|:----------|:--------|
| 1 | 17:32:25 | 0 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 2 | 17:34:03 | 30 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 3 | 17:35:35 | 4 | 17 | `[5, 7, 34]` | 12 | 6 | G1 | APOSTAR | MISS (15) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 4 | 17:37:01 | 23 | 8 | `[20, 3, 36]` | 11 | 3 | G1 | APOSTAR | HIT (36) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 5 | 17:38:37 | 36 | 17 | `[7, 21, 24]` | 11 | 4 | G1 | APOSTAR | HIT (10) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 6 | 17:40:07 | 12 | 17 | `[1, 35, 13]` | 11 | 4 | G1 | APOSTAR | HIT (12) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 7 | 17:41:37 | 18 | 17 | `[28, 2, 16]` | 11 | 4 | G1 | APOSTAR | HIT (2) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 8 | 17:43:07 | 2 | 37 | `[4, 30, 29]` | 11 | 3 | G1 | APOSTAR | HIT (15) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 9 | 17:44:33 | 0 | 32 | `[35, 17, 1]` | 11 | 3 | G1 | APOSTAR | MISS (11) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 10 | 17:45:58 | 19 | 27 | `[33, 35, 13]` | 12 | 4 | G1 | APOSTAR | MISS (32) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 11 | 17:47:30 | 33 | 1 | `[2, 5, 12]` | 13 | 3 | G1 | APOSTAR | MISS (15) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 12 | 17:49:02 | 9 | 27 | `[24, 28, 34]` | 12 | 4 | G1 | APOSTAR | HIT (6) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 13 | 17:50:36 | 17 | 17 | `[6, 33, 26]` | 12 | 4 | G1 | APOSTAR | HIT (1) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 14 | 17:52:12 | 16 | 29 | `[26, 27, 31]` | 12 | 4 | G1 | APOSTAR | MISS (21) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 15 | 17:53:44 | 10 | 37 | `[28, 17, 33]` | 13 | 3 | G1 | APOSTAR | HIT (34) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 16 | 17:55:13 | 5 | 17 | `[16, 35, 27]` | 13 | 4 | G1 | APOSTAR | pendente | Aderente ao M15-ADA v4.3; resultado ainda nao confirmado. |
| 17 | 17:56:48 | 3 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 18 | 17:58:20 | 18 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 19 | 17:59:52 | 23 | 34 | `[32, 11, 22]` | 13 | 6 | G1 | APOSTAR | HIT (13) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 20 | 18:01:26 | 14 | 32 | `[29, 21, 24]` | 12 | 4 | G1 | APOSTAR | HIT (16) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 21 | 18:03:00 | 6 | 23 | `[32, 36, 22]` | 12 | 4 | G1 | APOSTAR | MISS (33) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 22 | 18:04:35 | 25 | 23 | `[24, 28, 34]` | 12 | 4 | G1 | APOSTAR | MISS (8) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 23 | 18:06:11 | 29 | 19 | `[2, 10, 7]` | 12 | 4 | G1 | APOSTAR | MISS (13) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 24 | 18:07:49 | 7 | 32 | `[0, 36, 31]` | 13 | 3 | G1 | APOSTAR | MISS (17) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 25 | 18:09:29 | 13 | 19 | `[11, 9, 19]` | 13 | 4 | G1 | APOSTAR | HIT (22) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 26 | 18:11:11 | 36 | 21 | `[36, 14, 15]` | 12 | 4 | G3 | APOSTAR | MISS (5) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 27 | 18:12:45 | 23 | 25 | `[16, 35, 6]` | 13 | 4 | G1 | APOSTAR | MISS (30) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 28 | 18:14:19 | 29 | 12 | `[3, 27, 1]` | 13 | 3 | G1 | APOSTAR | MISS (22) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 29 | 18:15:59 | 29 | 8 | `[25, 5, 7]` | 12 | 3 | G1 | APOSTAR | MISS (9) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 30 | 18:17:39 | 2 | 26 | `[11, 31, 32]` | 12 | 4 | G1 | APOSTAR | MISS (35) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 31 | 18:19:18 | 5 | 19 | `[27, 1, 3]` | 12 | 4 | G1 | APOSTAR | HIT (17) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 32 | 18:20:54 | 27 | 16 | `[35, 34, 16]` | 12 | 4 | G1 | APOSTAR | MISS (22) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 33 | 18:22:30 | 2 | 10 | `[26, 27, 1]` | 12 | 4 | G1 | APOSTAR | HIT (36) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 34 | 18:24:13 | 2 | 16 | `[9, 32, 11]` | 11 | 4 | G1 | APOSTAR | HIT (8) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 35 | 18:25:50 | 5 | 10 | `[16, 28, 17]` | 11 | 4 | G1 | APOSTAR | MISS (9) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 36 | 18:27:28 | 0 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 37 | 18:28:58 | 34 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 38 | 18:30:36 | 3 | 1 | `[20, 26, 13]` | 12 | 5 | G2 | APOSTAR | HIT (11) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 39 | 18:32:10 | 18 | 9 | `[21, 23, 29]` | 12 | 4 | G1 | APOSTAR | MISS (24) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 40 | 18:33:48 | 35 | 24 | `[34, 16, 35]` | 12 | 4 | G1 | APOSTAR | HIT (34) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 41 | 18:35:27 | 29 | 24 | `[4, 8, 18]` | 12 | 4 | G1 | APOSTAR | HIT (25) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 42 | 18:37:01 | 3 | 24 | `[22, 19, 8]` | 12 | 4 | G2 | APOSTAR | HIT (14) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 43 | 18:38:31 | 23 | 24 | `[31, 32, 30]` | 12 | 4 | G1 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 44 | 18:40:11 | 26 | 27 | `[35, 6, 1]` | 13 | 4 | G1 | APOSTAR | MISS (11) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 45 | 18:41:33 | 34 | 27 | `[25, 24, 12]` | 13 | 4 | G1 | APOSTAR | MISS (23) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 46 | 18:43:17 | 9 | 6 | `[11, 9, 19]` | 13 | 3 | G1 | APOSTAR | HIT (30) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 47 | 18:44:55 | 20 | 7 | `[15, 30, 22]` | 13 | 4 | G1 | APOSTAR | MISS (2) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 48 | 18:46:33 | 35 | 14 | `[33, 3, 27]` | 13 | 3 | G1 | APOSTAR | MISS (31) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 49 | 18:48:13 | 21 | 16 | `[16, 35, 6]` | 13 | 3 | G1 | APOSTAR | MISS (9) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 50 | 18:49:49 | 30 | 23 | `[24, 12, 6]` | 13 | 3 | G1 | APOSTAR | HIT (27) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 51 | 18:51:22 | 0 | 14 | `[14, 32, 30]` | 13 | 4 | G1 | APOSTAR | MISS (35) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 52 | 18:53:04 | 6 | 18 | `[34, 33, 26]` | 13 | 4 | G1 | APOSTAR | MISS (23) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 53 | 18:54:42 | 11 | 28 | `[35, 6, 20]` | 13 | 3 | G1 | APOSTAR | HIT (28) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 54 | 18:56:14 | 30 | 23 | `[14, 32, 30]` | 13 | 4 | G1 | APOSTAR | MISS (17) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 55 | 18:57:46 | 0 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 56 | 18:59:16 | 30 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 57 | 19:00:46 | 6 | 28 | `[13, 20, 32]` | 12 | 6 | G2 | APOSTAR | MISS (21) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 58 | 19:02:16 | 13 | 22 | `[11, 31, 15]` | 12 | 5 | G1 | APOSTAR | MISS (6) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 59 | 19:03:50 | 0 | 16 | `[31, 32, 11]` | 12 | 4 | G1 | APOSTAR | MISS (27) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 60 | 19:05:14 | 8 | 8 | `[27, 1, 26]` | 12 | 3 | G1 | APOSTAR | MISS (15) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 61 | 19:06:45 | 8 | 21 | `[30, 9, 15]` | 12 | 4 | G1 | APOSTAR | MISS (25) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 62 | 19:08:10 | 0 | 18 | `[14, 26, 13]` | 11 | 4 | G1 | APOSTAR | MISS (19) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 63 | 19:09:37 | 1 | 21 | `[1, 3, 6]` | 12 | 4 | G1 | APOSTAR | MISS (22) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 64 | 19:11:03 | 23 | 26 | `[7, 25, 10]` | 13 | 4 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 65 | 19:12:31 | 21 | 8 | `[4, 8, 18]` | 12 | 3 | G1 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 66 | 19:14:07 | 5 | 1 | `[18, 4, 8]` | 12 | 3 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 67 | 19:15:33 | 7 | 26 | `[26, 27, 1]` | 12 | 4 | G1 | APOSTAR | HIT (26) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 68 | 19:17:01 | 13 | 26 | `[13, 20, 26]` | 12 | 4 | G1 | APOSTAR | MISS (18) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 69 | 19:18:35 | 13 | 19 | `[3, 27, 1]` | 13 | 4 | G1 | APOSTAR | MISS (19) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 70 | 19:19:57 | 30 | 24 | `[35, 6, 33]` | 13 | 4 | G1 | APOSTAR | MISS (19) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 71 | 19:21:19 | 34 | 37 | `[2, 5, 7]` | 13 | 3 | G1 | APOSTAR | HIT (28) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 72 | 19:22:46 | 34 | 26 | `[20, 0, 13]` | 13 | 4 | G2 | APOSTAR | HIT (3) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 73 | 19:24:13 | 14 | 11 | `[28, 17, 24]` | 13 | 3 | G1 | APOSTAR | MISS (32) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 74 | 19:25:38 | 0 | 17 | `[10, 7, 25]` | 13 | 4 | G1 | APOSTAR | HIT (30) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 75 | 19:27:08 | 19 | 17 | `[36, 31, 15]` | 13 | 4 | G1 | APOSTAR | MISS (16) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 76 | 19:28:38 | 35 | 20 | `[2, 5, 28]` | 13 | 4 | G1 | APOSTAR | HIT (12) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 77 | 19:30:10 | 4 | 14 | `[2, 5, 28]` | 13 | 4 | G1 | APOSTAR | MISS (20) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 78 | 19:31:32 | 10 | 17 | `[7, 25, 24]` | 13 | 4 | G1 | APOSTAR | MISS (20) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 79 | 19:33:04 | 2 | 14 | `[26, 13, 14]` | 13 | 4 | G1 | APOSTAR | MISS (19) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 80 | 19:34:36 | 31 | 18 | `[9, 19, 8]` | 13 | 4 | G1 | APOSTAR | MISS (0) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 81 | 19:36:02 | 16 | 27 | `[27, 20, 0]` | 13 | 3 | G1 | APOSTAR | HIT (32) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 82 | 19:37:32 | 17 | 18 | `[15, 30, 22]` | 13 | 4 | G2 | APOSTAR | MISS (24) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 83 | 19:39:00 | 26 | 23 | `[23, 29, 2]` | 13 | 4 | G1 | APOSTAR | MISS (33) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 84 | 19:40:28 | 4 | 28 | `[34, 33, 26]` | 13 | 4 | G1 | APOSTAR | MISS (11) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 85 | 19:41:51 | 24 | 28 | `[10, 7, 17]` | 13 | 4 | G1 | APOSTAR | HIT (34) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 86 | 19:43:17 | 6 | 28 | `[7, 25, 16]` | 13 | 4 | G2 | APOSTAR | HIT (22) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 87 | 19:44:47 | 0 | 25 | `[8, 18, 2]` | 13 | 4 | G1 | APOSTAR | MISS (32) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 88 | 19:46:15 | 18 | 25 | `[17, 24, 35]` | 12 | 4 | G1 | APOSTAR | MISS (30) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 89 | 19:47:47 | 36 | 26 | `[21, 10, 7]` | 13 | 4 | G1 | APOSTAR | HIT (5) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 90 | 19:49:13 | 20 | 19 | `[10, 7, 25]` | 13 | 4 | G1 | APOSTAR | HIT (5) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 91 | 19:50:41 | 21 | 20 | `[10, 7, 25]` | 13 | 4 | G3 | APOSTAR | HIT (16) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 92 | 19:52:09 | 28 | 30 | `[1, 3, 13]` | 12 | 3 | G1 | APOSTAR | MISS (17) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 93 | 19:53:45 | 0 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 94 | 19:55:07 | 17 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 95 | 19:56:31 | 23 | 2 | `[33, 35, 27]` | 12 | 4 | G1 | APOSTAR | MISS (32) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 96 | 19:57:53 | 5 | 18 | `[11, 9, 19]` | 13 | 4 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 97 | 19:59:06 | 20 | 27 | `[20, 26, 36]` | 12 | 3 | G1 | APOSTAR | MISS (23) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 98 | 20:00:34 | 8 | 20 | `[18, 4, 23]` | 12 | 4 | G1 | APOSTAR | MISS (33) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 99 | 20:01:58 | 17 | 14 | `[5, 7, 25]` | 12 | 3 | G1 | APOSTAR | HIT (34) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 100 | 20:03:26 | 16 | 5 | `[3, 6, 1]` | 12 | 3 | G1 | APOSTAR | HIT (3) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 101 | 20:04:50 | 12 | 5 | `[22, 19, 8]` | 12 | 4 | G1 | APOSTAR | MISS (0) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 102 | 20:06:20 | 15 | 18 | `[19, 30, 22]` | 12 | 3 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 103 | 20:07:44 | 16 | 27 | `[22, 19, 8]` | 12 | 3 | G1 | APOSTAR | MISS (13) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 104 | 20:09:18 | 0 | 12 | `[20, 26, 13]` | 12 | 4 | G1 | APOSTAR | HIT (26) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 105 | 20:10:50 | 2 | 14 | `[27, 33, 26]` | 11 | 4 | G2 | APOSTAR | MISS (10) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 106 | 20:12:14 | 24 | 21 | `[30, 9, 19]` | 12 | 4 | G1 | APOSTAR | MISS (29) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 107 | 20:13:40 | 7 | 24 | `[6, 33, 3]` | 12 | 4 | G1 | APOSTAR | HIT (34) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 108 | 20:15:07 | 8 | 23 | `[20, 26, 13]` | 12 | 4 | G1 | APOSTAR | HIT (9) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 109 | 20:16:31 | 16 | 24 | `[3, 6, 1]` | 12 | 4 | G1 | APOSTAR | MISS (8) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 110 | 20:17:47 | 22 | 23 | `[23, 29, 2]` | 13 | 4 | G1 | APOSTAR | MISS (9) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 111 | 20:19:17 | 28 | 26 | `[14, 32, 11]` | 13 | 4 | G1 | APOSTAR | MISS (6) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 112 | 20:20:43 | 9 | 23 | `[20, 0, 13]` | 13 | 4 | G1 | APOSTAR | MISS (2) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 113 | 20:22:09 | 23 | 1 | `[16, 12, 17]` | 12 | 3 | G1 | APOSTAR | MISS (22) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 114 | 20:23:27 | 0 | 8 | `[26, 13, 1]` | 13 | 4 | G1 | APOSTAR | HIT (11) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 115 | 20:24:57 | 18 | 20 | `[8, 18, 19]` | 13 | 3 | G1 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 116 | 20:26:33 | 29 | 8 | `[13, 14, 0]` | 13 | 4 | G1 | APOSTAR | MISS (5) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 117 | 20:27:59 | 21 | 11 | `[34, 33, 35]` | 13 | 4 | G1 | APOSTAR | HIT (35) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 118 | 20:29:27 | 22 | 32 | `[25, 24, 28]` | 13 | 3 | G1 | APOSTAR | HIT (2) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 119 | 20:30:57 | 7 | 23 | `[33, 3, 6]` | 13 | 4 | G1 | APOSTAR | HIT (6) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 120 | 20:32:31 | 20 | 3 | `[29, 21, 10]` | 12 | 3 | G1 | APOSTAR | MISS (26) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 121 | 20:34:00 | 18 | 1 | `[5, 28, 17]` | 13 | 3 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 122 | 20:35:30 | 22 | 23 | `[10, 7, 25]` | 13 | 4 | G1 | APOSTAR | HIT (8) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 123 | 20:37:00 | 11 | 21 | `[31, 15, 30]` | 13 | 4 | G2 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 124 | 20:38:28 | 0 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 125 | 20:40:00 | 23 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 126 | 20:41:32 | 3 | 7 | `[26, 13, 14]` | 13 | 6 | G2 | APOSTAR | MISS (4) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 127 | 20:43:02 | 28 | 8 | `[16, 35, 6]` | 13 | 6 | G1 | APOSTAR | HIT (13) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 128 | 20:44:36 | 24 | 26 | `[11, 9, 4]` | 13 | 3 | G1 | APOSTAR | MISS (12) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 129 | 20:46:08 | 35 | 8 | `[2, 10, 7]` | 12 | 4 | G1 | APOSTAR | MISS (31) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 130 | 20:47:38 | 18 | 12 | `[24, 28, 25]` | 12 | 4 | G1 | APOSTAR | HIT (16) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 131 | 20:49:47 | 36 | 13 | `[3, 6, 1]` | 12 | 4 | G1 | APOSTAR | HIT (28) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 132 | 20:51:13 | 30 | 3 | `[21, 23, 29]` | 12 | 3 | G1 | APOSTAR | HIT (5) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 133 | 20:52:39 | 5 | 13 | `[9, 15, 30]` | 12 | 4 | G1 | APOSTAR | pendente | Aderente ao M15-ADA v4.3; resultado ainda nao confirmado. |
| 134 | 20:54:05 | 17 | 0 | `[0]` | 0 | 0 | G1 | PULAR | pendente | Aderente: sem dados suficientes no warmup inicial. |
| 135 | 20:55:27 | 32 | 0 | `[0]` | 0 | 0 | G1 | APOSTAR | pendente | Divergencia de logging: fallback G1 seguro executado, mas DB gravou campos SDA vazios. |
| 136 | 20:56:56 | 18 | 8 | `[17, 24, 12]` | 12 | 6 | G3 | APOSTAR | MISS (8) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 137 | 20:58:25 | 5 | 10 | `[16, 35, 34]` | 13 | 5 | G1 | APOSTAR | HIT (5) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 138 | 20:59:49 | 30 | 8 | `[35, 6, 1]` | 13 | 5 | G1 | APOSTAR | HIT (35) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 139 | 21:01:13 | 14 | 8 | `[22, 19, 23]` | 12 | 5 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 140 | 21:02:45 | 19 | 8 | `[2, 10, 28]` | 12 | 4 | G2 | APOSTAR | MISS (31) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 141 | 21:04:07 | 14 | 16 | `[22, 19, 8]` | 12 | 4 | G1 | APOSTAR | MISS (28) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 142 | 21:05:36 | 10 | 13 | `[3, 6, 1]` | 12 | 3 | G1 | APOSTAR | MISS (29) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 143 | 21:07:02 | 2 | 8 | `[26, 27, 1]` | 12 | 3 | G1 | APOSTAR | MISS (10) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 144 | 21:08:24 | 36 | 23 | `[21, 23, 18]` | 12 | 4 | G1 | APOSTAR | HIT (29) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 145 | 21:09:46 | 31 | 20 | `[5, 7, 2]` | 12 | 4 | G1 | APOSTAR | HIT (25) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 146 | 21:11:12 | 26 | 2 | `[24, 28, 25]` | 12 | 3 | G1 | APOSTAR | HIT (16) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 147 | 21:12:38 | 17 | 4 | `[17, 5, 12]` | 11 | 3 | G1 | APOSTAR | HIT (23) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 148 | 21:13:58 | 18 | 11 | `[6, 16, 3]` | 11 | 4 | G1 | APOSTAR | HIT (6) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 149 | 21:15:26 | 14 | 11 | `[25, 10, 28]` | 11 | 4 | G1 | APOSTAR | MISS (15) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 150 | 21:16:46 | 35 | 5 | `[34, 24, 12]` | 11 | 3 | G1 | APOSTAR | HIT (33) | Aderente ao M15-ADA v4.3; Triple Focus 17 numeros acertou. |
| 151 | 21:18:00 | 28 | 11 | `[21, 8, 29]` | 11 | 4 | G1 | APOSTAR | MISS (20) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 152 | 21:19:22 | 9 | 25 | `[19, 11, 9]` | 11 | 3 | G1 | APOSTAR | MISS (26) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |
| 153 | 21:20:48 | 31 | 18 | `[1, 12, 6]` | 10 | 4 | G1 | APOSTAR | MISS (30) | Aderente ao M15-ADA v4.3; previsao valida, mas a roda caiu fora da cobertura. |

---

## 6. Verificacao de aderencia a estrategia estabelecida

| Item auditado | Resultado | Evidencia |
|---|---|---|
| Janela adaptativa + warmup minimo 2 | Aderente | Primeiros `PULAR` e fallbacks ocorrem antes da estrategia ter 2 forcas limpas |
| IQR + weighted median + drift | Aderente por desenho | `sda_predicted_force` ficou sempre populado apos warmup, com score 3-6 e sem violacoes de cobertura |
| Triple Focus 17 numeros | Aderente | Todas as apostas validas verificadas cobriram exatamente 17 numeros |
| Offsets sigmoid por direcao | Aderente | `sda_offset_type=sigmoid` em 278 decisoes; CW e CCW operaram de forma independente |
| Fallback early-session | Parcialmente aderente | Existe e aposta de fato, mas o banco nao persiste seus campos reais |
| Registro fiel para engenharia reversa | Nao aderente no warmup | 14 linhas ficaram sem numeros/centro reais, apesar de `final_action=APOSTAR` |

**Juizo final:** a estrategia em si esta majoritariamente de acordo com o desenho v4.3. O problema de hoje nao e um desvio do algoritmo principal, e sim um **bug de representacao/logging** no fallback early-session, somado a **performance insuficiente do offset 12** na amostra do dia.

---

## 7. Proximas correcoes recomendadas

1. Corrigir o `Decision` salvo no `message_handler` para usar os numeros/centro/score efetivamente colocados pelo fallback `G1 seguro`.
2. Reprocessar ou marcar os 14 registros do dia com um campo explicito de fallback, para a caixa de vidro nao interpretar essas apostas como previsoes vazias.
3. Auditar por que o controlador converge tanto para offset 12 quando 11 e 13 performaram melhor nesta janela.
4. Revisar o fechamento do CW apos 21:00, onde houve a pior sequencia de misses do dia.


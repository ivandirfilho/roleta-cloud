# Otimizacao da Estrategia - Adaptabilidade Baseada nos Resultados de 02/04

> **Objetivo:** avaliar, com base nos dados variaveis das jogadas de 02/04/2026, se vale a pena aumentar a adaptabilidade da estrategia para buscar a melhor jogada em cada momento.  
> **Base usada:** `resultados_02_04.md`, 306 decisoes do dia, SDA17 M15-ADA v4.3 em producao.

---

## 1. Resposta curta

**Sim, vale a pena aumentar a adaptabilidade**, mas de forma **controlada e mensuravel**.

Os dados de hoje mostram que:

- a estrategia esta ativa nos dois lados e funcionando como projetado na maior parte das jogadas;
- o problema principal nao e falta de estrategia, e sim **adaptacao subotima ao regime atual**;
- o **offset 12** foi o mais usado, mas performou pior que 11 e 13 em **CW e CCW**;
- o desempenho variou muito por faixa de tempo, com **19h = 36.4%**, **20h = 60.6%** e **21h = 30.0%**;
- isso indica que o sistema atual **adapta**, mas ainda **nao se adapta rapido o suficiente ao regime do momento**.

Portanto, a melhor direcao nao e trocar a estrategia, e sim **colocar uma camada adaptativa acima do controlador atual**, preservando o SDA17 como motor base.

---

## 2. O que os dados de hoje provaram

### 2.1 Estrategia realmente ativa em ambos os sentidos

- **CW:** 139 decisoes com `sda_offset_type=sigmoid`
- **CCW:** 139 decisoes com `sda_offset_type=sigmoid`
- Codigo com historicos independentes por direcao: `cw_history` e `ccw_history`
- Codigo com offsets independentes por direcao: `cw_off2/cw_off3` e `ccw_off2/ccw_off3`

**Leitura:** a estrategia ja e bidirecional e independente por lado. A otimizacao deve respeitar isso e continuar tratando CW e CCW separadamente.

### 2.2 O gargalo real do dia foi o offset

| Direcao | Offset | Hits | Total | HR |
|---|---:|---:|---:|---:|
| CW | 11 | 13 | 26 | 50.0% |
| CW | 12 | 32 | 75 | 42.7% |
| CW | 13 | 17 | 33 | 51.5% |
| CCW | 10 | 0 | 1 | 0.0% |
| CCW | 11 | 9 | 16 | 56.2% |
| CCW | 12 | 24 | 61 | 39.3% |
| CCW | 13 | 28 | 59 | 47.5% |

**Leitura:** o sistema convergiu demais para o offset 12, mas 12 foi o pior offset util dos dois lados.

### 2.3 O score tambem nao esta sendo aproveitado como filtro dinamico

| Direcao | Score | Hits | Total | HR |
|---|---:|---:|---:|---:|
| CW | 3 | 15 | 35 | 42.9% |
| CW | 4 | 44 | 93 | 47.3% |
| CW | 5 | 3 | 5 | 60.0% |
| CCW | 3 | 18 | 38 | 47.4% |
| CCW | 4 | 37 | 88 | 42.0% |
| CCW | 5 | 4 | 5 | 80.0% |
| CCW | 6 | 2 | 6 | 33.3% |

**Leitura:** score alto nem sempre significou melhor aposta. Hoje, por exemplo, **CCW score 5 foi excelente**, enquanto **CCW score 4 foi fraco**. Isso sugere que o score sozinho nao pode ser usado de forma fixa; ele precisa ser lido em conjunto com contexto recente.

### 2.4 O regime do dia mudou varias vezes

| Hora | Hits | Total | HR |
|---|---:|---:|---:|
| 17h | 13 | 28 | 46.4% |
| 18h | 30 | 65 | 46.2% |
| 19h | 28 | 77 | 36.4% |
| 20h | 43 | 71 | 60.6% |
| 21h | 9 | 30 | 30.0% |

**Leitura:** houve mudancas reais de regime. O controlador atual nao reagiu com velocidade suficiente ao colapso das 19h e 21h.

---

## 3. Onde melhorar a adaptabilidade

## 3.1 Prioridade maxima - seletor dinamico de offset por direcao

### Problema

O M02-PctSigmoid ajusta offsets de forma continua, mas hoje ele passou tempo demais em **12**, que foi ruim.

### Melhoria proposta

Criar um **meta-controlador leve**, por direcao, acima do sigmoid:

1. manter estatisticas rolling para offsets 11, 12 e 13;
2. usar uma janela curta, por exemplo ultimas 12 ou 16 apostas daquele sentido;
3. se um offset alternativo tiver vantagem clara sobre o atual, aplicar um **bias temporario** no sigmoid;
4. remover o bias quando a vantagem desaparecer.

### Beneficio esperado

- manter a suavidade do sigmoid;
- evitar convergencia prolongada em offset ruim;
- responder melhor a regimes curtos e medios.

### Risco

Se a janela for curta demais, o sistema pode superajustar ao ruido.

### Recomendacao

Implementar primeiro como **telemetria/sombra**, sem afetar aposta real, para comparar:

- offset escolhido hoje;
- offset que o meta-controlador teria escolhido;
- delta de hit rate simulado.

---

## 3.2 Prioridade alta - gate adaptativo de regime

### Problema

O sistema continuou apostando com comportamento quase igual mesmo durante colapsos claros, como:

- CW com 12 misses consecutivos no fim;
- queda geral para 30.0% na faixa das 21h.

### Melhoria proposta

Adicionar um **regime gate** por direcao:

- medir HR rolling nas ultimas 8/12 apostas;
- medir streak atual de misses;
- medir degradacao recente por offset e score;
- reduzir agressividade quando o regime piorar.

### Acoes possiveis do gate

1. reduzir gale ao minimo;
2. trocar temporariamente para offset alternativo melhor na janela curta;
3. exigir score mais forte para apostar;
4. em colapso severo, pular 1 ou 2 entradas daquele sentido.

### Beneficio esperado

Evitar insistencia cega durante janelas ruins.

---

## 3.3 Prioridade alta - score contextual, nao fixo

### Problema

O score do SDA mede estabilidade do pipeline, mas **nao mede diretamente vantagem empirica recente**.

### Melhoria proposta

Criar um **score composto**:

`score_final = score_sda + ajuste_regime + ajuste_offset + ajuste_direcao`

Onde:

- `score_sda` = score atual da estrategia;
- `ajuste_regime` = bonus/penalidade pela janela recente;
- `ajuste_offset` = bonus se o offset atual estiver performando bem;
- `ajuste_direcao` = bonus/penalidade conforme a direcao esteja em regime bom ou ruim.

### Beneficio esperado

Tomar a melhor jogada do momento com base nao so na geometria da roda, mas no comportamento recente do proprio motor.

---

## 3.4 Prioridade media - fallback early-session melhor modelado

### Problema

Hoje o fallback existe, mas ficou mal gravado no banco. Isso prejudica:

- caixa de vidro;
- auditoria;
- qualquer aprendizado futuro orientado por dados.

### Melhoria proposta

Persistir explicitamente:

- `mode = fallback_g1_safe`
- numeros reais usados no fallback;
- centro real do fallback;
- score especifico de fallback;
- flag `is_fallback = true`

### Beneficio esperado

Base limpa para aprender com dados reais, inclusive no warmup.

---

## 3.5 Prioridade media - detector de mudanca de regime por faixa horaria curta

### Problema

Os dados de hoje mostram que o comportamento mudou muito entre 19h, 20h e 21h.

### Melhoria proposta

Sem usar relogio como feature fixa, medir:

- volatilidade da `spin_force`;
- dispersao recente;
- variacao de acertos;
- distancia media dos misses ao centro coberto.

Se essas variaveis cruzarem um limiar, marcar o momento como:

- `regime_estavel`
- `regime_instavel`
- `regime_colapso`

E ajustar a agressividade da estrategia.

---

## 4. O que nao vale a pena fazer agora

1. **Nao vale trocar o SDA17 por outra estrategia inteira.** O problema observado foi mais de adaptacao fina do que de desenho base.
2. **Nao vale aumentar cobertura acima de 17 numeros sem estudo serio.** Isso muda break-even, payout e perfil de risco.
3. **Nao vale usar machine learning pesado agora.** A base ainda tem problema de logging no warmup, e o ganho mais provavel esta em regras adaptativas simples e auditaveis.

---

## 5. Plano de implementacao recomendado

## Fase 1 - higiene de dados

1. corrigir o bug de logging do fallback;
2. registrar explicitamente modo normal vs fallback;
3. enriquecer o banco com metricas rolling por direcao.

## Fase 2 - telemetria adaptativa em sombra

1. calcular performance rolling por offset em cada direcao;
2. simular seletor de offset 11/12/13 sem alterar aposta real;
3. registrar qual offset alternativo teria sido escolhido.

## Fase 3 - controle adaptativo leve

1. ativar bias temporario no offset quando houver vantagem estatistica curta;
2. ativar regime gate com thresholds conservadores;
3. validar por varios dias antes de mexer no gale.

## Fase 4 - integracao total

1. usar score composto contextual;
2. integrar ao minidashboard e caixa de vidro;
3. acompanhar se o sistema melhora sem aumentar volatilidade.

---

## 6. Juizo final

**Vale a pena otimizar a adaptabilidade.**

O diagnostico de hoje nao aponta para abandono da estrategia atual. Ele aponta para uma necessidade clara de **adaptacao contextual por direcao**, especialmente em:

- escolha dinamica de offset;
- deteccao de regime ruim;
- filtragem de aposta em momentos de colapso;
- persistencia correta do fallback para aprendizado futuro.

**Melhor direcao tecnica:** manter o SDA17 M15-ADA v4.3 como base e adicionar uma camada de **meta-adaptacao leve, auditavel e orientada por janelas curtas de performance**.

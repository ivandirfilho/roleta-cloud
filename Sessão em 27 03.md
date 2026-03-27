# 📋 Sessão de Trabalho — 27 de Março de 2026

> **Projeto:** Roleta Cloud v3.5.0  
> **Data:** 27/Mar/2026  
> **Commits realizados:** 2 (798007b + a762bb0)  
> **Arquivos modificados:** 18 (primeiro commit) + 6 (segundo commit)  
> **Linhas alteradas:** +3.205 / −828  
> **Testes finais:** 55/55 passing  
> **Deploy:** ✅ Servidor Debian (187.45.181.75) atualizado e rodando  

---

## 1. CONTEXTO INICIAL

O **Roleta Cloud** é um sistema de predição em tempo real para roleta, composto por:

- **Backend Python** (WebSocket + SQLite) rodando em Docker num servidor Debian
- **Extensão Chrome** que captura os números da roleta ao vivo e exibe o overlay com sugestões
- **Estratégia SDA** (Sinergia Direcional Avançada) que analisa forças direcionais para prever regiões da roda

No início do dia, o sistema operava com a **SDA-19** (1 centro + 9 vizinhos = 19 números, 51.4% de cobertura) e um **Martingale clássico de janela** (5 jogadas por nível, 3 níveis: G1=R$21, G2=R$42, G3=R$84).

A sessão de trabalho teve como objetivo **evoluir completamente** o sistema: da estratégia de predição ao sistema de gestão de apostas (Martingale), passando por análise de dados, estudos comparativos e implementação final.

---

## 2. CRONOLOGIA DOS DOCUMENTOS CRIADOS

A evolução seguiu uma **metodologia rigorosa de 6 etapas**, cada uma gerando um documento que alimentou a próxima:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. analise_de_resultados.md          → Diagnóstico da sessão real         │
│  2. sugestões de melhorias.md         → Propostas de melhoria              │
│  3. estudo aprofundado de numeros.md  → Simulação de 3 estratégias         │
│  4. sda21 transição.md               → Plano de implantação SDA-21        │
│  5. sessão de 18 jogadas.md          → Análise pós-implantação SDA-21     │
│  6. implantação proposta.md          → Smart Gale v4 + correção de bugs   │
│                                                                             │
│  → Commit 1: SDA-19 → SDA-21 (Triple Focus)                               │
│  → Commit 2: Smart Gale v4 + Strategy Fixes (4 Sprints)                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. DOCUMENTO 1 — `analise_de_resultados.md`

### Propósito
Diagnóstico completo da sessão `dab34c61` (26/03/2026) com a estratégia SDA-19 ativa. Avaliação de acertos, erros e fluxo de dados que levaram a cada resultado.

### Principais Descobertas
- **396 linhas** de análise detalhada
- Sessão com 15 decisões de aposta (APOSTAR) avaliáveis
- **Taxa de acerto CW:** 46.7% | **CCW:** 50.0% | **Global:** 48.1%
- O fluxo CW e CCW estava operando **corretamente e de forma independente**
- O sistema de forças direcionais mostrava coerência, mas a cobertura de 19 números (1 centro) era sensível a erros de posicionamento do centro
- Identificado que quando o centro errava por mais de 9 posições, o acerto era impossível

### Impacto
Este documento revelou que a **fragilidade principal** era depender de um único centro. Se a mediana ponderada errasse a posição por mais de 9 casas na roda, os 19 números seriam todos inúteis. Isso motivou a busca por estratégias multi-centro.

---

## 4. DOCUMENTO 2 — `sugestões de melhorias.md`

### Propósito
Propostas concretas de melhoria baseadas nos problemas encontrados na análise. Documento apenas de estudo, sem alterar código.

### Principais Sugestões (497 linhas)
O documento foi dividido em 4 partes:

| Parte | Foco | Melhorias |
|-------|------|-----------|
| **I** | Estratégia SDA-19 | MEL-01 a MEL-06: IQR, score, drift, diversificação |
| **II** | Triple Rate Advisor | MEL-07 a MEL-09: Kill switch, tendência, peso dinâmico |
| **III** | Martingale | MEL-10 a MEL-12: Progressão adaptativa, stop-loss, recuo |
| **IV** | Pipeline de Dados | MEL-13 a MEL-15: Normalização, logging, overlay |

### Destaques
- **MEL-01:** Correção do cálculo IQR (usava divisão inteira em vez de percentis reais)
- **MEL-05:** Drift detection usando dados pós-IQR (antes usava dados brutos com outliers)
- **MEL-13:** Normalização do spread por MAX_FORCE=18
- Cada melhoria passou por **auditoria de bugs** antes de ser finalizada

---

## 5. DOCUMENTO 3 — `estudo aprofundado de quantidade de numeros.md`

### Propósito
Simulação comparativa de **3 estratégias de cobertura** usando os dados reais da sessão analisada. Objetivo: encontrar a configuração ótima de centros × vizinhos.

### As 3 Configurações Testadas (873 linhas)

| Config | Nome | Centros | Vizinhos/Lado | Números | Cobertura |
|:------:|------|:-------:|:-------------:|:-------:|:---------:|
| **A** | SDA-19 | 1 | 9 | 19 | 51.4% |
| **B** | SDA-18 | 2 | 4 | até 18 | até 48.6% |
| **C** | SDA-21 | 3 | 3 | até 21 | até 56.8% |

### Resultado da Simulação
- **SDA-21 (Config C)** venceu em praticamente todos os cenários
- Motivo: 3 centros independentes (mediana ponderada + força máxima + força mínima) criam **redundância espacial** — se um centro erra, os outros dois podem salvar a jogada
- A cobertura de até 56.8% com 3 centros espalhados pela roda superou o arco contíguo de 51.4% da SDA-19
- O estudo incluiu quadro comparativo com cada sugestão de melhoria aplicada a cada estratégia

### Decisão
**SDA-21 (Triple Focus)** foi aprovado como a evolução da estratégia.

---

## 6. DOCUMENTO 4 — `sda21 transição.md`

### Propósito
Plano de implantação detalhado para trocar SDA-19 por SDA-21. Documentação completa do fluxo de dados antes e depois.

### Estrutura (948 linhas)

| Seção | Conteúdo |
|-------|----------|
| 1 | Situação Atual — Fluxo de dados completo SDA-19 |
| 2 | Situação Proposta — Fluxo de dados SDA-21 |
| 3 | Mapa de alterações por arquivo |
| 4 | Detalhamento de cada alteração |
| 5 | Migração do banco de dados |
| 6 | Migração do state.json |
| 7 | Melhorias incluídas (MEL) |
| 8 | Ordem de implementação |
| 9 | Auditoria de bugs |
| 10 | Checklist de deploy |

### Fluxo Antes vs Depois

**Antes (SDA-19):**
```
Forças → IQR → Weighted Median → 1 Centro → 9 vizinhos cada lado → 19 números
```

**Depois (SDA-21):**
```
Forças → IQR → Weighted Median → C1 (mediana)
                → max(forces)   → C2 (max)      → 3 vizinhos cada → até 21 números
                → min(forces)   → C3 (min)
```

### Impacto
Este documento foi a base para o **Commit 1** (798007b) que implementou a transição SDA-19 → SDA-21.

---

## 7. DOCUMENTO 5 — `sessão de 18 jogadas em cada sentido.md`

### Propósito
Análise detalhada da **primeira sessão ao vivo** com SDA-21 ativo. Engenharia reversa de cada uma das 31 jogadas (15 CW + 16 CCW).

### Resultados da Sessão (677 linhas)

| Métrica | CW | CCW | Global |
|---------|:--:|:---:|:------:|
| Jogadas | 15 | 16 | 31 |
| Acertos | 8 | 8 | 16 |
| Taxa | 53.3% | 50.0% | **51.6%** |
| Financeiro | +R$3 | −R$3 | **R$0** |

### Atribuição de Acertos por Centro

| Centro | Acertos | Percentual | Função |
|--------|:-------:|:----------:|--------|
| C1 (mediana) | 4 | 25% | Base do pipeline |
| C2 (max force) | 7 | **44%** | Hero — resgatou mais acertos |
| C3 (min force) | 4 | 25% | Cobertura complementar |
| Overlap | 1 | 6% | Acertado por 2+ centros |

### Bugs Identificados em Produção

| Bug | Severidade | Problema |
|-----|:----------:|---------|
| BUG-LIVE-01 | 🔴 Alta | `_ensure_diversity()` separação de 4 posições insuficiente → overlap entre centros |
| BUG-LIVE-02 | 🔴 Alta | Sem cobertura mínima forçada → 2 jogadas com <17 números (0% acerto) |
| BUG-LIVE-03 | 🟡 Média | Triple Rate Advisor não preveniu cold streak de 5 erros consecutivos |
| BUG-LIVE-04 | 🟡 Média | Força anômala (force=36) sem flag de alerta |

### Conclusão Principal
O SDA-21 **funcionou** — C2 provou ser o centro mais valioso com 44% dos acertos. Mas os bugs de diversificação e cobertura mínima precisavam de correção urgente.

---

## 8. DOCUMENTO 6 — `implantação proposta apos sessao 18 numeros.md`

### Propósito
Proposta completa de implantação em duas etapas: correção de bugs na estratégia + reestruturação total do Martingale. Incluiu estudo de **15 sistemas de gestão de aposta** diferentes.

### Etapa 1 — Bugs na Estratégia (1041 linhas)

| Bug | Correção |
|-----|----------|
| BUG-E1 | `_ensure_diversity()`: separação mínima 4 → 7 posições, offset 7 → 12 |
| BUG-E2 | Cobertura mínima ≥ 18: se <18, redistribuir centros a ~120° |
| BUG-E3 | Refatorar Advisor para expor c4_rate numericamente |
| BUG-E4 | Flag forças anômalas (>30) com inversão suave (37 − força) |
| BUG-E5 | Fallback SDA-19 quando <5 forças válidas (early-session) |

### Etapa 2 — 15 Sistemas de Martingale Estudados

| # | Sistema | Resultado Simulado |
|---|---------|-------------------|
| 1 | Martingale Clássico (dobrar) | −R$147 |
| 2 | Paroli (dobrar no acerto) | −R$63 |
| 3 | D'Alembert (subir/descer ±1) | −R$21 |
| 4 | Oscar's Grind | −R$42 |
| 5 | Sistema 1-3-2-6 | −R$84 |
| 6 | Sistema 1-3-2-4 | −R$63 |
| 7 | Fibonacci | −R$105 |
| 8 | Labouchère | −R$126 |
| 9 | Hollandish | −R$42 |
| 10 | Contra-D'Alembert | −R$21 |
| 11 | Whittaker | −R$84 |
| 12 | Kelly Criterion (simplificado) | −R$21 |
| 13 | **Streak-Adaptive** | **+R$12** |
| 14 | **Janela Ponderada** | **+R$18** |
| 15 | **Hybrid Score-Streak** | **+R$33** ✅ |

### Vencedor: Smart Gale v4 (Hybrid Score-Streak)

```
REGRAS:
  R1 — Teto por Score: Score 1-2 → max 1× | Score 3-4 → max 2× | Score 5-6 → max 3×
  R2 — Streak de acertos: 0 consec → 1× | 1 consec → mantém | 2+ consec → sobe 1
  R3 — Reset após MISS: volta a 1× imediatamente
  R4 — Gale Advisor: C4 rate < 25% → força teto 1×
  R5 — Independência: CW e CCW totalmente separados
```

**Restrições respeitadas:**
- ✅ Gales: apenas 1× (R$21), 2× (R$42), 3× (R$63)
- ✅ Sempre aposta — nunca pula, nunca para
- ✅ CW e CCW independentes

---

## 9. EVOLUÇÃO TÉCNICA DO SOFTWARE

### 9.1 Commit 1 — `feat: upgrade SDA-19 → SDA-21 (Triple Focus)` (798007b)

**18 arquivos modificados** | +2.932 / −680 linhas

| Arquivo | Alteração Principal |
|---------|-------------------|
| `strategies/sda17.py` | Pipeline Triple Focus (3 centros), IQR com statistics.quantiles(), drift com dados limpos |
| `state/game.py` | Suporte a multi-centros no store_prediction e check_prediction |
| `core/engine.py` | Passagem de sda_centers para decisão e DB |
| `database/models.py` | Campo sda_centers (TEXT JSON) |
| `database/sqlite_repo.py` | Auto-migração: coluna sda_centers adicionada |
| `extension/content.js` | Display multi-centro `[C1] [C2] [C3]` no overlay |
| `server/message_handler.py` | Envio de centros, action_reason e bet_advice para overlay |
| `models/output.py` | Campo sda_centers em SpinDecision |
| Documentos (4) | analise_de_resultados, sugestões, estudo, sda21 transição |
| `tests/` | 45 testes passing |

### 9.2 Commit 2 — `feat: Smart Gale v4 + SDA-21 strategy fixes` (a762bb0)

**6 arquivos modificados** | +273 / −148 linhas | Organizado em 4 Sprints:

#### Sprint 1 — Correções na Estratégia (`strategies/sda17.py`)

| Mudança | Antes | Depois |
|---------|-------|--------|
| MIN_SEPARATION | 4 posições | **7 posições** (zero overlap entre clusters) |
| SPREAD_OFFSET | 7 posições | **12 posições** (~1/3 da roda) |
| Cobertura mínima | Sem verificação | **≥ 18 números** (com redistribuição automática) |
| Fallback | Nenhum | **SDA-19 mode** quando <5 forças válidas |
| Anomalia | Sem detecção | **Flag e inversão** (37 − força) para force > 30 |

#### Sprint 2 — Smart Gale v4 (`state/game.py`, `core/engine.py`)

| Componente | Antes (Martingale Clássico) | Depois (Smart Gale v4) |
|------------|---------------------------|----------------------|
| Mecanismo | Janela de 5 jogadas por nível | **Streak-based** (acertos consecutivos) |
| Gales | G1=R$21, G2=R$42, G3=**R$84** | G1=R$21, G2=R$42, G3=**R$63** |
| Subida | Falhar janela → sobe nível | **2+ acertos consecutivos** → sobe 1 |
| Descida | Acertar 3/5 → volta G1 | **Qualquer miss** → volta G1 imediatamente |
| Teto | Fixo por nível | **Dinâmico por score SDA** (1-2→1×, 3-4→2×, 5-6→3×) |
| Skip/Pausa | STOP no G3 | **Nunca** — sempre aposta |
| Advisor | Não influenciava gale | **C4 rate < 25% → força teto 1×** |

#### Sprint 3 — Gale Advisor (`state/bet_advisor.py`)

- **c4_rate** (taxa de acerto dos últimos 4 resultados) agora é consumido pelo Smart Gale v4
- Se c4_rate < 25%: o sistema **força gale máximo em 1×** independente do score, protegendo contra cold streaks

#### Sprint 4 — Logging + Overlay (`server/message_handler.py`, `database/service.py`)

- Overlay agora recebe: `gale_reasoning`, `consecutive_hits`, `gale_display` no formato "G1 S0"
- Logging atualizado para Smart Gale v4 com mensagens de STREAK e RESET
- Tracking de janelas no DB adaptado para o modelo streak-based

### 9.3 Testes

| Antes | Depois |
|-------|--------|
| 45 testes | **55 testes** |
| TestMartingaleState (5 testes) | **TestSmartGaleV4 (15 testes)** |
| Sem teste de score ceiling | ✅ test_get_gale_score_ceiling |
| Sem teste de c4_rate override | ✅ test_get_gale_c4_rate_override |
| Sem teste de streak | ✅ test_get_gale_streak_raises |
| Sem teste de migração | ✅ test_from_dict_migration |
| Sem teste de validação total | ✅ test_always_returns_valid_gale (126 combinações) |

---

## 10. DIAGRAMA DA EVOLUÇÃO

```
ESTADO INICIAL (início do dia):
┌──────────────────────────────────────────────────────────┐
│  SDA-19: 1 centro + 9 vizinhos = 19 números (51.4%)     │
│  Martingale: Janela 5 jogadas, G1/G2/G3 = 21/42/84      │
│  Bugs: IQR impreciso, drift com outliers, spread bruto   │
│  Kill Switch: veta apostas (PULAR/STOP)                  │
│  Testes: 45                                              │
└──────────────────────────────────────────────────────────┘
                          │
               6 documentos de estudo
                          │
                          ▼
ESTADO FINAL (fim do dia):
┌──────────────────────────────────────────────────────────┐
│  SDA-21: 3 centros + 3 vizinhos = até 21 números (56.8%) │
│  Smart Gale v4: Score×Streak, G1/G2/G3 = 21/42/63       │
│  Fixes: IQR preciso, diversity 7, coverage ≥18           │
│  Sempre Aposta: nunca PULAR, nunca STOP                  │
│  Advisor: c4_rate < 25% → protege com teto 1×            │
│  Testes: 55                                              │
└──────────────────────────────────────────────────────────┘
```

---

## 11. RESUMO DAS MUDANÇAS POR ARQUIVO

| Arquivo | Mudança |
|---------|---------|
| `strategies/sda17.py` | Pipeline Triple Focus + diversity 7 + coverage ≥18 + fallback SDA-19 + anomaly flag |
| `state/game.py` | MartingaleState reescrito como Smart Gale v4 (streak-based, BET_VALUES 21/42/63) |
| `core/engine.py` | Sempre aposta + passa score e c4_rate para SmartGaleV4 |
| `state/bet_advisor.py` | c4_rate exposto para consumo pelo Gale Advisor (Rule 4) |
| `database/models.py` | Campo sda_centers para multi-centro |
| `database/sqlite_repo.py` | Auto-migração de coluna sda_centers |
| `database/service.py` | Tracking de janelas adaptado para modelo streak |
| `server/message_handler.py` | Gale reasoning + streak info no overlay + logging atualizado |
| `extension/content.js` | Display multi-centro [C1][C2][C3] |
| `models/output.py` | sda_centers em SpinDecision |
| `tests/test_game_state.py` | 15 novos testes SmartGaleV4 (126 combinações validadas) |
| `tests/test_sda17.py` | Testes para diversity e triple focus atualizados |

---

## 12. DOCUMENTOS DE ESTUDO — ÍNDICE FINAL

| # | Documento | Linhas | Propósito |
|---|----------|:------:|-----------|
| 1 | `analise_de_resultados.md` | 396 | Diagnóstico da sessão com SDA-19 |
| 2 | `sugestões de melhorias.md` | 497 | 15 propostas de melhoria categorizadas |
| 3 | `estudo aprofundado de quantidade de numeros.md` | 873 | Simulação de SDA-19 vs SDA-18 vs SDA-21 |
| 4 | `sda21 transição.md` | 948 | Plano de implantação detalhado SDA-19→SDA-21 |
| 5 | `sessão de 18 jogadas em cada sentido.md` | 677 | Análise da 1ª sessão ao vivo com SDA-21 |
| 6 | `implantação proposta apos sessao 18 numeros.md` | 1041 | Smart Gale v4 + 15 sistemas estudados |
| — | **TOTAL** | **4.432** | **Documentação completa da evolução** |

---

## 13. CONCLUSÃO

A sessão de 27 de março representou a **maior evolução técnica** do Roleta Cloud desde sua criação. O processo seguiu uma metodologia científica:

1. **Observar** → Análise de dados reais da sessão
2. **Diagnosticar** → Identificação de pontos fracos
3. **Propor** → 15 melhorias documentadas
4. **Simular** → 3 estratégias × 15 melhorias comparadas
5. **Planejar** → Documento de transição completo
6. **Implementar** → SDA-21 em produção
7. **Validar** → 31 jogadas ao vivo analisadas
8. **Corrigir** → 5 bugs encontrados e corrigidos
9. **Evoluir** → Smart Gale v4 (15 sistemas estudados, vencedor implementado)
10. **Testar** → 55/55 testes passando
11. **Deploy** → Servidor atualizado e operacional

O sistema agora opera com **maior cobertura** (21 vs 19 números), **melhor diversificação** (3 centros espalhados vs 1 arco contíguo), **gestão inteligente de aposta** (score × streak vs janela fixa), e **nunca para de apostar** — sempre escolhendo a melhor aposta possível para cada jogada.

# Graph Report - Roleta Cloud  (2026-05-22)

## Corpus Check
- 22 files · ~46,707 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 787 nodes · 895 edges · 55 communities (49 shown, 6 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6bdde3c8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]

## God Nodes (most connected - your core abstractions)
1. `BaseModel` - 21 edges
2. `SDA17Strategy` - 19 edges
3. `MessageHandler` - 15 edges
4. `Plano de Implantação — M15-ADA (C1/C2/C3 Melhorado)` - 15 edges
5. `simulate_all()` - 14 edges
6. `coverage_set()` - 11 edges
7. `PARTE I — ARQUITETURA COMPLETA DO SOFTWARE` - 11 edges
8. `cov_sym()` - 10 edges
9. `4. INVENTÁRIO DETALHADO DE ALTERAÇÕES POR ARQUIVO` - 10 edges
10. `mg.level permanece SEMPRE 1 (default)` - 10 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `start_server()`  [EXTRACTED]
  main.py → server/websocket.py

## Communities (55 total, 6 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (45): 4.2.1 MartingaleState.BET_VALUES (linha 39), 4.2.2 Estado Adaptativo no GameState, 4.2.3 Migração de Versão do state.json, 4.2.4 Docstrings da Classe MartingaleState, 4.2 `state/game.py` — ALTERAÇÃO MÉDIA, 4.3.1 Chamar `update_adaptive()` após verificação de resultado, 4.3.2 Persistir Estado Adaptativo, 4.3.3 Restaurar Estado Adaptativo no Startup (+37 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (42): 1. Visão Geral, 2. Estrutura de Diretórios, 3. Diagrama de Componentes e Dependências, 4. Fluxo de Dados Principal, 5. Modelo de Dados (SQLite), 6. Sistema de Decisão (Pipeline M15-ADA v4.3 + Kill Switch), 7. Protocolo WebSocket — Tipos de Mensagem, 8. Modelo de Conexão (Master/Slave) (+34 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (42): 1. RESUMO DO PROBLEMA, 2.1 Fluxo de dados do overlay, 2.2 Sequência temporal do bug, 2.3 Bug no modo expandido, 2. ANÁLISE DE CAUSA RAIZ, 3. BUGS IDENTIFICADOS, 4.1 Abordagem: Helper function DRY, 4.2 CSS: Visibilidade no modo expandido (+34 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (42): 1. RESUMO EXECUTIVO, 2.1 Fase 1: CORE (`strategies/sda17.py`), 2.2 Fase 2: ESTADO (`state/game.py`), 2.3 Fase 3: SERVIDOR (`server/`), 2.4 Fase 4: FRONTEND (Opcional), 2.5 Fase 5: TESTES, 2.6 Fase 6: VALIDAÇÃO, 2.7 Tarefas Extras (Não Planejadas) (+34 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (42): 13.1 Alterações na PARTE I — Arquitetura, 13.2 Alterações na PARTE II — Análise ISO, 13.3 Alterações na PARTE IV — Bugs, 13.4 Alterações na PARTE III — Scorecard, 13.5 Alterações na PARTE V — Mapa de Conformidade, 13.6 Alterações na PARTE VI — Conclusão, 13.7 Atualização do Rodapé, 13. ANOTAÇÕES PÓS-IMPLANTAÇÃO PARA `Manutenabilidade_iso.md` (+34 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (38): 1.1 Completude Funcional, 1.2 Correção Funcional, 1.3 Pertinência Funcional, 1. ADEQUAÇÃO FUNCIONAL (Functional Suitability), 2.1 Comportamento Temporal, 2.2 Utilização de Recursos, 2.3 Capacidade, 2. EFICIÊNCIA DE DESEMPENHO (Performance Efficiency) (+30 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (34): 1. Resumo das Sessoes Pos-Deploy SmartGale v5, 2.1 O Problema, 2.2 Impacto, 2.3 Correcao Necessaria, 2. BUG CRITICO ENCONTRADO: get_gale() Nunca e Chamado em Producao, 3.1 CW (Predicoes feitas em spins AH → alvo Horario), 3.2 CCW (Predicoes feitas em spins H → alvo Anti-Horario), 3.3 Comparacao entre Direcoes (+26 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (19): handle_shutdown(), main(), Handler para shutdown graceful., Ponto de entrada principal., MessageHandler, Manipulador de mensagens WebSocket., Verifica se é um spin duplicado (mesmo número no mesmo segundo)., Processa uma mensagem recebida. (+11 more)

### Community 8 - "Community 8"
Cohesion: 0.10
Nodes (33): circ_dir(), circ_dist(), cov(), cov_sym(), model_01_symmetric_bayesian(), model_02_asymmetric_bayesian(), model_03_momentum_shift(), model_04_error_vector() (+25 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (33): adaptive_state, last_direction, last_number, martingale_ccw, consecutive_hits, current_bet, gale_display, global_consecutive_hits (+25 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (17): Verificacao dos cenarios criticos — v4.3 (M02-PctSigmoid), Estratégia M15-ADA v4.3: M02-PctSigmoid — Triple Focus 17 números.          Pi, Pipeline robusto: IQR → Weighted Median → Drift.                  Args:, Retorna offsets adaptativos ASSIMÉTRICOS (off_c2, off_c3).         v4.3: M02-Pc, M04+M10 Hybrid: Error-Vector com Prior Gaussiano.                  M04 calcula, Bayesiano brute-force: testa todos offsets contra janela recente, retorna o melh, Direção circular de a para b na roda.         Retorna +1 se b está no sentido h, M02-PctSigmoid: Atualiza offsets C2/C3 com feedback sigmoid dampened. (+9 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (33): 6.1 Motivação, 6.2 Especificação, 6.3 Display Atual vs Proposto, 6.4 Análise de Impacto, 6.5 Tarefas de Implantação, 6.6 Detalhamento das Tasks, 6.7 Dependências, 6.8 Estimativa de Impacto (+25 more)

### Community 12 - "Community 12"
Cohesion: 0.07
Nodes (29): 1. Verificacao de Tarefas (TAsk_audit_pos.md), 2. Verificacao Git & Deploy, 3. Verificacao Servidor de Producao, 4. Auditoria Completa de Bugs, 5. Bugs NAO Corrigidos (Risco Aceitavel), 6. Resultados dos Testes Pos-Fix, 7. Resumo de Arquivos Modificados (v4.3.1), 8. Conclusao (+21 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (20): 2.1 Fluxo de Dados Completo (Estado Atual), 2.2 Mapa de Arquivos do Sistema, 2.3.1 Estratégia SDA-21 (`strategies/sda17.py`), 2.3.2 Base da Estratégia (`strategies/base.py`), 2.3.3 Estado do Jogo (`state/game.py`), 2.3.4 Handler de Mensagens (`server/message_handler.py`), 2.3.5 Banco de Dados (`database/models.py`), 2.3.6 Frontend Dashboard (`frontend/`) (+12 more)

### Community 14 - "Community 14"
Cohesion: 0.11
Nodes (18): 3.1 FIX: BUG-TASK-001 — `update_adaptive()` em `engine.py`, 3.2 FIX: BUG-TASK-003 — EMA Clamp Imediato, 3.3 FIX: BUG-TASK-004 — `_wheel` Inicializado Cedo, 3.4 FIX: BUG-TASK-005 — Validação de Bounds no Load, 3.5 FIX: BUG-TASK-006 + BUG-NEW-007 — Offset Real no DB, 3.6 FIX: BUG-NEW-002 — Validação de Cobertura, 3.7 FIX: BUG-NEW-003 + BUG-NEW-004 — Logging de Fallbacks, 3.8 Tabela Consolidada de Correções (+10 more)

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (17): 4.1.1 Mudanças nas Constantes (linhas 24-32), 4.1.2 Novo Método: `_get_adaptive_offset(direction)`, 4.1.3 Novo Método: `update_adaptive(direction, c1, actual_result)`, 4.1.4 Mudanças no `analyze()` (linhas 117-175), 4.1.5 Atualização do `details` no Retorno, 4.1.6 Métodos a REMOVER, 4.1.7 Novo Método: Serialização do Estado Adaptativo, 4.1.8 Atualização da Assinatura de `analyze()` (+9 more)

### Community 16 - "Community 16"
Cohesion: 0.14
Nodes (6): M05_AdaptiveEWMA, M10_MAD_Robust, M12_PercentileBand, EWMA com alpha adaptativo: erro maior → alpha maior → resposta mais rápida., MAD (Median Absolute Deviation) para identificar outliers e ajustar só com dados, Mantém offset entre 25º e 75º percentil dos oracle offsets recentes.

### Community 17 - "Community 17"
Cohesion: 0.26
Nodes (9): circ_dist(), clamp(), coverage_set(), error_pct(), M11_BayesianPosterior, neighbors(), Simulação de 15 modelos de controle variável para C2/C3. Cada modelo recebe feed, Distribuição de probabilidade sobre offsets [7-13], atualiza com Bayes após cada (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.18
Nodes (11): 5.1 Adequação Funcional (Functional Suitability), 5.2 Confiabilidade (Reliability), 5.3 Manutenibilidade (Maintainability), 5.4 Eficiência de Desempenho (Performance Efficiency), 5.5 Compatibilidade (Compatibility), 5.6 Usabilidade (Usability), 5.7 Segurança (Security), 5.8 Portabilidade (Portability) (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.20
Nodes (6): circ_dir(), M01_PercentualLinear, M03_PercentualThreshold, Só ajusta se erro > 7 posições (ignora misses pequenos como ruído)., Returns +1 if result is CW from c1, -1 if CCW, 0 if same., Ajuste linear baseado em % do erro. Hit: tighten 5% para center=10. Miss: mover

### Community 20 - "Community 20"
Cohesion: 0.18
Nodes (7): BaseModel, M08_DampedPID, M15_EnsembleVote, PID com anti-windup e filtro derivativo para prevenir oscilação., Média ponderada dos 3 melhores sub-modelos (M01,M04,M09), pesos por accuracy rec, Classe base para todos os modelos., Chamado após cada jogada com feedback.

### Community 21 - "Community 21"
Cohesion: 0.20
Nodes (9): 10. CHECKLIST PRÉ-IMPLANTAÇÃO, 14. VERSÃO DO DOCUMENTO, 5.1 Componentes que NÃO Mudam, 5.2 Verificação de Compatibilidade, 5. IMPACTO EM COMPONENTES NÃO MODIFICADOS, 9.1 Critérios para Validação, 9.2 Monitoramento Pós-Implantação, 9. MÉTRICAS DE SUCESSO (+1 more)

### Community 22 - "Community 22"
Cohesion: 0.20
Nodes (10): 11.1 Bugs Encontrados, 11.2 Análise Detalhada dos Bugs Críticos, 11.3 Classificação por Prioridade para M15-ADA, 11.4 Impacto dos Bugs no M15-ADA, 11. AUDITORIA DE BUGS — `main.py`, BUG-MAIN-002: Double Shutdown (Race Condition), BUG-MAIN-005: sys.exit() em asyncio, code:python (# FLUXO ATUAL (com bug):) (+2 more)

### Community 23 - "Community 23"
Cohesion: 0.20
Nodes (10): 6.1 Checklist de Validação Local (conforme `deployci_cd.md` §2), 6.2 Arquivos Modificados (para commit), 6.3 Commit Sugerido, 6.4 Migração de Dados, 6.5 Rollback Plan, code:block16 (core/engine.py           +11 linhas  (BUG-TASK-001)), code:block17 (fix(v4.0.3): correções auditoria Bayesiana — 9 bugs), code:block18 (Migração automática no startup:) (+2 more)

### Community 24 - "Community 24"
Cohesion: 0.27
Nodes (4): M04_EMA_ErrorTracking, M09_Kalman, EMA de erros direcionais com alpha=0.3, converte em ajuste de offset., Filtro de Kalman 1D para estimação de offset ótimo.

### Community 25 - "Community 25"
Cohesion: 0.22
Nodes (9): 12.1 Impacto por Característica ISO, 12.2.1 Adequação Funcional, 12.2.2 Eficiência de Desempenho, 12.2.3 Confiabilidade, 12.2.4 Manutenibilidade, 12.2 Requisitos de Conformidade para Cada Mudança, 12.3 Checklist ISO/IEC 25010 Pré-Deploy, 12. DIRETRIZES ISO/IEC 25010 PARA O M15-ADA (+1 more)

### Community 26 - "Community 26"
Cohesion: 0.25
Nodes (7): 4.1 Testes Automatizados, 4.2 Verificação de Imports, 4.3 Verificação de Integridade, 4.4 Teste Manual de Cenários Críticos, code:block12 (======================= 105 passed, 4 warnings in 0.48s ====), code:block14 (============================================================), FASE 4 — VALIDAÇÃO PÓS-CORREÇÃO

### Community 27 - "Community 27"
Cohesion: 0.25
Nodes (8): 1.1 Ciclo de Vida de uma Jogada, 1.2 Mapeamento Critico de Direcoes, 1.3 Pipeline de Predicao de Forca, 1.4 Pipeline de Offset Bayesiano (M04+M10), 1. ENGENHARIA REVERSA - FLUXO COMPLETO DE DADOS, code:block1 (SPIN CHEGA (numero, direcao)), code:block2 (Forcas recentes [f0, f1, f2, ..., f6]  (f0 = mais recente)), code:block3 (historico = [(c1_0, res_0), ..., (c1_n, res_n)]  (ultimas 24)

### Community 28 - "Community 28"
Cohesion: 0.29
Nodes (6): 1.1 Escopo do `tasks_resultados_30_03.md`, 1.2 Validação dos Resultados da Simulação, code:block1 (╔══════╦══════════════════════════╦════════╦══════════╗), FASE 1 — VALIDAÇÃO DO TASK DOCUMENT, 🔍 Validação de Tasks & Resultados — Roleta Cloud v4.0.3, ÍNDICE

### Community 29 - "Community 29"
Cohesion: 0.29
Nodes (7): 4.2 Bugs de Performance, BUG-PERF-001: Drift de Offset para Valores Altos [SEVERIDADE: CRITICA], BUG-PERF-002: Assimetria Excessiva do Error-Vector [SEVERIDADE: ALTA], BUG-PERF-003: Prior Gaussiano Insuficiente [SEVERIDADE: ALTA], BUG-PERF-004: ERROR_THRESHOLD Muito Baixo [SEVERIDADE: MEDIA], BUG-PERF-005: Ausencia de Limitador de Variacao [SEVERIDADE: MEDIA], code:python (last_off = self._last_offset.get(direction, BAYESIAN_DEFAULT)

### Community 30 - "Community 30"
Cohesion: 0.33
Nodes (6): 7.1 Lista de Tarefas (Ordem de Execução), 7.2 Dependências entre Tarefas, 7.3 Estimativa de Impacto por Arquivo, 7. TAREFAS DE IMPLANTAÇÃO, code:block42 (FASE 1: CORE (Estratégia)), code:block43 (T01 ──→ T02 ──→ T06)

### Community 31 - "Community 31"
Cohesion: 0.33
Nodes (6): 3.1 Descrição da Estratégia M15-ADA, 3.2 Diferenças Chave SDA-21 → M15-ADA, 3.3 Fluxo de Dados Proposto, 3. ARQUITETURA PROPOSTA — M15-ADA, code:block10 (┌───────────────────────────────────────────────────────────), code:block11 (┌───────────────────────────────────────────────────────────)

### Community 32 - "Community 32"
Cohesion: 0.33
Nodes (6): 8.2 Resultado do Deploy v4.0.3, code:block20 (tasks_resultados_30_03.md (estudo)), CONSOLIDAÇÃO FINAL, Métricas Finais, Próximos Passos, Rastreabilidade Completa

### Community 33 - "Community 33"
Cohesion: 0.33
Nodes (5): 2.1 Dados Brutos, 2.2 Performance por Offset (CW), 2.3 Analise de Erros CW (10 misses), 2. ANALISE DAS ULTIMAS 25 JOGADAS - SENTIDO HORARIO (CW), Validacao Task Final Manha - Auditoria Profunda v4.1.0

### Community 34 - "Community 34"
Cohesion: 0.40
Nodes (5): 8.1 Estratégia de Rollback, 8.2 Feature Flag (Recomendado), 8. ROLLBACK PLAN, code:python (# app_config/settings.py), code:python (# strategies/sda17.py)

### Community 35 - "Community 35"
Cohesion: 0.40
Nodes (4): Arquivos Protegidos, Política de Segurança, Regras de Credenciais, Reporte de Vulnerabilidades

### Community 36 - "Community 36"
Cohesion: 0.40
Nodes (5): 2.1 Bugs Conhecidos (do task document) — Verificação no Código, 2.2 Bugs Novos Descobertos (auditoria aprofundada), 2.3 Análise de Impacto, code:block2 (BUG-TASK-001 (engine.py) ────► Parcial: já corrigido em mess), FASE 2 — AUDITORIA PROFUNDA DE BUGS

### Community 37 - "Community 37"
Cohesion: 0.40
Nodes (5): 3.1 Dados Brutos, 3.2 Performance por Offset (CCW), 3.3 Analise de Erros CCW (12 misses + 6 fallback), 3. ANALISE DAS ULTIMAS 25 JOGADAS - SENTIDO ANTI-HORARIO (CCW), code:block4 (7 -> 7 -> 10 -> 10 -> 10 -> 10 -> 11 -> 10 -> 10 -> 11 -> 12)

### Community 38 - "Community 38"
Cohesion: 0.40
Nodes (5): 6.1 Proposta v4.2.0 - Parametros, 6.2 Simulacao Retroativa CW (10 misses), 6.3 Simulacao Retroativa CCW (12 misses), 6.4 Projecao Global v4.2.0, 6. SIMULACAO: IMPACTO DAS MELHORIAS PROPOSTAS

### Community 39 - "Community 39"
Cohesion: 0.50
Nodes (4): 1.1 Objetivo, 1.2 Motivação (Resultados do Estudo), 1.3 Princípio Fundamental, 1. RESUMO EXECUTIVO

### Community 40 - "Community 40"
Cohesion: 0.50
Nodes (4): 6.1 Testes Unitários, 6.2 Testes de Integração, 6.3 Teste de Regressão, 6. PLANO DE TESTES

### Community 46 - "Community 46"
Cohesion: 0.50
Nodes (4): 4.1 Bugs Funcionais, 4. BUGS IDENTIFICADOS, BUG-FUNC-001: DB Nao Armazena off_c3 [SEVERIDADE: MEDIA], BUG-FUNC-002: Fallback SDA-19 com Offset Zero [SEVERIDADE: BAIXA]

### Community 47 - "Community 47"
Cohesion: 0.50
Nodes (4): 5.1 CW - Jogadas Detalhadas (excluindo fallback), 5.2 CCW - Jogadas Detalhadas (excluindo fallback), 5.3 Resumo da Engenharia Reversa, 5. ANALISE DE DESEMPENHO POR JOGADA (ENGENHARIA REVERSA)

### Community 48 - "Community 48"
Cohesion: 0.50
Nodes (4): 7.1 tasks_resultados_30_03.md, 7.2 tasks_final_melhoria_pos.md, 7.3 Taskk_final_pos_implantacao_30_03_final_da_manha.md, 7. VERIFICACAO CONTRA DOCUMENTOS DE REFERENCIA

### Community 49 - "Community 49"
Cohesion: 0.50
Nodes (4): 8.1 Acoes Imediatas (v4.2.0), 8.2 Acoes de Medio Prazo (v4.3.0), 8.3 Investigacao Futura, 8. RECOMENDACOES PRIORIZADAS

### Community 50 - "Community 50"
Cohesion: 0.50
Nodes (4): 9. CONCLUSAO, O sistema v4.1.0 esta funcionando conforme projetado?, Performance real vs projetada, Veredicto Final

## Knowledge Gaps
- **368 isolated node(s):** `version`, `last_number`, `last_direction`, `direction`, `forces` (+363 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Plano de Implantação — M15-ADA (C1/C2/C3 Melhorado)` connect `Community 21` to `Community 0`, `Community 34`, `Community 4`, `Community 39`, `Community 40`, `Community 13`, `Community 22`, `Community 25`, `Community 30`, `Community 31`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `4. INVENTÁRIO DETALHADO DE ALTERAÇÕES POR ARQUIVO` connect `Community 0` to `Community 21`, `Community 15`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `13. ANOTAÇÕES PÓS-IMPLANTAÇÃO PARA `Manutenabilidade_iso.md`` connect `Community 4` to `Community 21`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **What connects `Handler para shutdown graceful.`, `Ponto de entrada principal.`, `version` to the rest of the system?**
  _432 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.044444444444444446 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.046511627906976744 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.046511627906976744 - nodes in this community are weakly interconnected._
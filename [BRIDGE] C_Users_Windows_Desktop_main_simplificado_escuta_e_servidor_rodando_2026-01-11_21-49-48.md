# [BRIDGE] Current Interface Analysis - SOTA Edition
> **Version**: Bridge Scanner v2.0
> **Source Context**: `[CONTEX] C_Users_Windows_Desktop_main_simplificado_escuta_e_servidor_rodando 11-01-2026 21-49-27.txt`
> **Architecture Graph**: `[ARCH] C_Users_Windows_Desktop_main simplificado escuta e servidor rodando_2026-01-11_21-49-36.md`
> **Target Project**: `main simplificado escuta e servidor rodando`
> **Timestamp**: 2026-01-11 21:49:48
> **Status do Sistema**: 🟢 SERVICE_MODE (Exposição de rede ativa detectada)

---

## 📁 Tríade de Documentação

| Artefato | Status | Arquivo |
| :--- | :---: | :--- |
| **[CONTEX]** | ✅ | `[CONTEX] C_Users_Windows_Desktop_main_simplificado_escuta_e_servidor_rodando 11-01-2026 21-49-27.txt` (0 arquivos, 0 tokens) |
| **[ARCH]** | ✅ | `[ARCH] C_Users_Windows_Desktop_main simplificado escuta e servidor rodando_2026-01-11_21-49-36.md` (1055 símbolos) |
| **[BRIDGE]** | 🔄 | *Este documento* |

---

## 📊 Análise de Fluxo de Dados (SOTA DataFlow Scanner)

### 📈 Estatísticas Gerais
| Métrica | Valor |
| :--- | :--- |
| **Arquivos Analisados** | 128 |
| **Linguagens Detectadas** | javascript, python |
| **Total de Bridges** | 1679 |
| **Saídas (Outbound)** | 1658 |
| **Entradas (Inbound)** | 0 |
| **Bidirecionais** | 21 |

---

### 🔌 Bridges Detectadas por Categoria

#### 🖨️ Console/Logging (1554 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `analisador_screenshot.py` | 99 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 100 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 102 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 103 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 104 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 126 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 133 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 142 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 152 | Python | print() | 🟡 70% |
| `analisador_screenshot.py` | 154 | Python | print() | 🟡 70% |

> *...e mais 1544 bridges nesta categoria*

#### 📁 File I/O (77 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `analisador_screenshot.py` | 285 | Python | File Write | 🟢 95% |
| `analisador_screenshot.py` | 286 | Python | Config File Write | 🟢 90% |
| `backtest_completo_modelos.py` | 623 | Python | File Write | 🟢 95% |
| `backtest_completo_modelos.py` | 704 | Python | File Write | 🟢 95% |
| `backtest_completo_modelos.py` | 624 | Python | Config File Write | 🟢 90% |
| `backtest_completo_modelos.py` | 705 | Python | Config File Write | 🟢 90% |
| `cinematica_db.py` | 399 | Python | File Write | 🟢 95% |
| `cinematica_db.py` | 400 | Python | Config File Write | 🟢 90% |
| `force_kalman.py` | 242 | Python | Config File Write | 🟢 90% |
| `force_kalman_integration.py` | 359 | Python | File Write | 🟢 95% |

> *...e mais 67 bridges nesta categoria*

#### ☁️ Cloud Service (24 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `app_controller.py` | 40 | Python | Firebase | 🟢 95% |
| `app_controller.py` | 49 | Python | Firebase | 🟢 95% |
| `app_controller.py` | 54 | Python | Firebase | 🟢 95% |
| `app_controller.py` | 55 | Python | Firebase | 🟢 95% |
| `app_controller.py` | 64 | Python | Firebase | 🟢 95% |
| `app_controller.py` | 67 | Python | Firebase | 🟢 95% |
| `app_controller.py` | 70 | Python | Firebase | 🟢 95% |
| `firebase_manager.py` | 11 | Python | Firebase | 🟢 95% |
| `firebase_manager.py` | 12 | Python | Firebase | 🟢 95% |
| `firebase_manager.py` | 16 | Python | Firebase | 🟢 95% |

> *...e mais 14 bridges nesta categoria*

#### 💾 Database (7 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `force_predictor_db.py` | 103 | Python | SQLite | 🟢 95% |
| `force_predictor_db.py` | 112 | Python | SQLite | 🟢 95% |
| `microservico_db.py` | 144 | Python | SQLite | 🟢 95% |
| `persistence.py` | 30 | Python | SQLite | 🟢 95% |
| `test_db_query.py` | 6 | Python | SQLite | 🟢 95% |
| `RoletaV11\database\microservico.py` | 137 | Python | SQLite | 🟢 95% |
| `RoletaV11\database\persistence.py` | 23 | Python | SQLite | 🟢 95% |

#### ⚙️ Subprocess/Shell (7 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `setup_dev.py` | 18 | Python | subprocess | 🟢 95% |
| `setup_dev.py` | 22 | Python | subprocess | 🟢 95% |
| `RoletaV11\Extrator Beat\build.py` | 20 | Python | subprocess | 🟢 95% |
| `RoletaV11\Extrator Beat\build.py` | 56 | Python | subprocess | 🟢 95% |
| `RoletaV11\Extrator Beat\build.py` | 59 | Python | subprocess | 🟢 95% |
| `RoletaV11\Extrator Beat\extrator_manual_gui.py` | 319 | Python | subprocess | 🟢 95% |
| `RoletaV11\Extrator Beat\interfaces\gui\main_window.py` | 267 | Python | subprocess | 🟢 95% |

#### 🗃️ Cache (4 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `strategies.py` | 34 | Python | Local Cache | 🟡 80% |
| `strategies.py` | 1061 | Python | Local Cache | 🟡 80% |
| `RoletaV11\strategies\legacy.py` | 34 | Python | Local Cache | 🟡 80% |
| `RoletaV11\strategies\legacy.py` | 1061 | Python | Local Cache | 🟡 80% |

#### 🔌 WebSocket (3 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `RoletaV11\Extrator Beat\Escuta Beat\extensao_chrome\background.js` | 90 | JavaScript/TypeScript | WebSocket API | 🟢 95% |
| `RoletaV11\Extrator Beat\Integracao Escuta x Roleta\bridge.py` | 57 | Python | WebSocket | 🟢 90% |
| `RoletaV11\Extrator Beat\Integracao Escuta x Roleta\websocket_server.py` | 161 | Python | websockets lib | 🟢 95% |

#### 🌐 HTTP Outbound (2 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `RoletaV11\Extrator Beat\extrator_html.py` | 42 | Python | Requests Library | 🟢 95% |
| `RoletaV11\Extrator Beat\extrator_html_gui.py` | 224 | Python | Requests Library | 🟢 95% |

#### 📨 Message Queue (1 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `firebase_manager.py` | 103 | Python | Redis PubSub | 🟢 90% |

---

## 1. 📡 Análise de Protocolos de Rede (Network Surface)
Varredura por instanciamento de servidores ou listeners ativos no código fornecido.

| Protocolo | Status Detectado | Evidência no Código |
| :--- | :--- | :--- |
| **HTTP / REST** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **gRPC** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **WebSockets** | ✅ ATIVO | Conexões WebSocket bidirecionais instanciados em 3 arquivo(s). |
| **Message Queue** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **GraphQL** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **Observabilidade** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **Database** | ✅ ATIVO | Conexões com bancos de dados instanciados em 6 arquivo(s). |

> **Conclusão da Seção 1:** O sistema possui **endpoints de rede ativos** permitindo conexão de clientes externos.

---
## 2. 📦 Contratos de Dados (Implicit DTOs)
Classes identificadas que funcionam como **estruturas de dados de troca** entre os módulos. Estas são as classes que *deverão* ser serializadas para o Frontend.

### Módulo: `.` (Enumerações e constantes do sistema)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ResultadoEstrategia`** (dataclass):
    * **Campos:** jogada_idx, numero_sorteado, estrategia, filtro, acertou, ... (+3 campos)
    * **Função:** Resultado de uma operação
* **`MetricasEstrategia`** (dataclass):
    * **Campos:** nome, filtro, total_jogadas, acertos, erros, ... (+5 campos)
    * **Função:** Métricas acumuladas de uma estratégia
* **`ModeloSelecao`** (Enum):
    * **Campos:** ROI_MEDIO_SIMPLES_4, ROI_MEDIO_SIMPLES_6, ROI_MEDIO_SIMPLES_9, ROI_MEDIO_SIMPLES_12, ENSEMBLE, ... (+5 campos)
    * **Função:** Modelo de dados
* **`AssinaturaJerk`** (dataclass):
    * **Campos:** centro, votos, ultimo_visto, forca_antes, forca_depois
    * **Função:** Representa uma assinatura de JERK conhecida pelo sistema.
* **`VereDict`** (dataclass):
    * **Campos:** indice, forca_original, accel_original, jerk_original, jerk_valido, ... (+7 campos)
    * **Função:** Resultado da análise forense de um ponto.
* **`BatchResult`** (dataclass):
    * **Campos:** forcas_originais, accels_originais, jerks_originais, forcas_validadas, accels_validadas, ... (+11 campos)
    * **Função:** Resultado de uma operação
* **`SeriesCinematica`** (dataclass):
    * **Campos:** nome, sentido, tipo, dados, max_items, ... (+1 campos)
    * **Função:** Representa uma série cinemática (forças, acelerações ou jerks).
* **`ClusterResult`** (dataclass):
    * **Campos:** centro, range_min, range_max, membros, count
    * **Função:** Resultado de uma operação
* **`KalmanState`** (dataclass):
    * **Campos:** x, P
    * **Função:** Estado interno do sistema
* **`RegistroCircular`** (dataclass):
    * **Campos:** timestamp, posicao_inicial, posicao_parada, angulo_inicial, angulo_parada, ... (+8 campos)
    * **Função:** Registro de uma observação circular
* **`ResultadoPredicao`** (dataclass):
    * **Campos:** posicao_prevista, posicao_absoluta_prevista, forcas_predominantes, padrao, confianca, ... (+3 campos)
    * **Função:** Resultado de uma operação
* **`Jogada`** (dataclass):
    * **Campos:** id, timestamp, posicao_inicial, posicao_final, voltas_por_segundo, ... (+5 campos)
    * **Função:** Representa uma jogada/ciclo do sistema.
* **`Derivada`** (dataclass):
    * **Campos:** jogada_id, delta_t, velocidade, aceleracao, arranco
    * **Função:** Representa as derivadas calculadas para uma jogada.
* **`Cluster`** (dataclass):
    * **Campos:** id, nome, centro, range_min, range_max, ... (+2 campos)
    * **Função:** Representa um cluster de força (X, Y ou Z).
* **`EstadoKalman`** (dataclass):
    * **Campos:** id, posicao_estimada, velocidade_estimada, aceleracao_estimada, matriz_P, ... (+1 campos)
    * **Função:** Estado interno do Filtro de Kalman.
* **`Predicao`** (dataclass):
    * **Campos:** id, timestamp_predicao, jogada_alvo, posicao_prevista, forca_prevista, ... (+3 campos)
    * **Função:** Representa uma predição gerada pelo sistema.
* **`ForcePredictorIntegrationV2`** (Class):
    * **Campos:** _instance
    * **Função:** Integra o sistema de predição v2 (duas linhas) com o GameStateManager.
* **`ResultadoPredicaoV2`** (dataclass):
    * **Campos:** direcao, posicao_prevista, posicao_absoluta_prevista, forcas_predominantes, padrao, ... (+3 campos)
    * **Função:** Resultado de uma operação
* **`NovaJogadaInfo`** (dataclass):
    * **Campos:** numero, fonte, direcao, dealer, modelo, ... (+3 campos)
    * **Função:** Agrupa todas as informações para processar uma nova jogada.
* **`LogContext`** (dataclass):
    * **Campos:** numero_sorteado, aposta_realizada, vitoria, resultado_financeiro, fonte, ... (+12 campos)
    * **Função:** Agrupa todos os dados necessários para formatar uma mensagem de log.
* **`GameStateManager`** (Class):
    * **Função:** Estado interno do sistema
* **`PrevisaoMicroservico`** (dataclass):
    * **Campos:** id, timestamp, sentido, posicao_partida, forca_vicio, ... (+8 campos)
    * **Função:** Representa uma previsão do microserviço.
* **`EstatisticasSentido`** (dataclass):
    * **Campos:** sentido, total_previsoes, total_acertos, total_erros, acertos_vicio, ... (+1 campos)
    * **Função:** Estatísticas de performance por sentido.
* **`ResultadoJogada`** (dataclass):
    * **Campos:** pos_temporal, linha, coluna, numero, resultado, ... (+2 campos)
    * **Função:** Resultado de uma operação
* **`HistoricoEstrategia`** (dataclass):
    * **Campos:** nome, resultados, roi_historico, historico_gatilhos
    * **Função:** Histórico completo de uma estratégia
* **`VagaEstacionamento`** (dataclass):
    * **Campos:** centro, votos, ultima_ocorrencia
    * **Função:** Representa uma VAGA de estacionamento para assinaturas.
* **`PointResult`** (dataclass):
    * **Campos:** cycle_step, sentido, phase, vagas_status, is_anomaly, ... (+8 campos)
    * **Função:** Resultado de uma operação
* **`ResultadoEstrategia`** (dataclass):
    * **Campos:** numero_sorteado, estrategia, acertou, roi, score_clusters
    * **Função:** Resultado de uma operação
* **`MetricasEstrategia`** (dataclass):
    * **Campos:** nome, total_jogadas, acertos, erros, roi_total, ... (+2 campos)
    * **Função:** Métricas acumuladas de uma estratégia
* **`ModeloSelecao`** (Enum):
    * **Campos:** ROI_MEDIO_SIMPLES, ENSEMBLE, UCB, THOMPSON, VOTACAO
    * **Função:** Modelo de dados
* **`ContextoAnalise`** (dataclass):
    * **Campos:** modo_leitura_forca, vitoria_anterior, sda_min_cluster_score, sda_min_cluster_score_7, sda_min_cluster_score_9, ... (+3 campos)
    * **Função:** Objeto de Transferência de Dados para o contexto da análise.
* **`DadosExtraidos`** (dataclass):
    * **Campos:** forcas_horario, forcas_antihorario, total_jogadas, total_outliers, sentido_mais_recente, ... (+1 campos)
    * **Função:** Dados extraídos do banco_de_dados_completo.
* **`BridgeOutput`** (dataclass):
    * **Campos:** target_forces, forcas_usadas, sentido_usado, sanitizer_output, profiler_output, ... (+4 campos)
    * **Função:** Saída completa do Bridge.
* **`Sentido`** (Enum):
    * **Campos:** HORARIO, ANTIHORARIO
    * **Função:** Direção do giro da roleta.
* **`ClusterJerk`** (dataclass):
    * **Campos:** nome, centro, membros, indices
    * **Função:** Representa um cluster de Jerks identificado.
* **`SanitizerOutput`** (dataclass):
    * **Campos:** clean_forces, clean_accs, clean_jerks, last_valid_force, cluster_a, ... (+11 campos)
    * **Função:** Saída do MS-01 Sanitizer.
* **`ProfilerOutput`** (dataclass):
    * **Campos:** habit_force_signature, acc_trend_primary, acc_trend_secondary, habit_cluster_size, habit_cluster_members, ... (+6 campos)
    * **Função:** Saída do MS-02 Profiler.
* **`TargetForce`** (dataclass):
    * **Campos:** nome, forca, origem, componentes
    * **Função:** Representa um vetor de força projetado.
* **`ProjectorOutput`** (dataclass):
    * **Campos:** force_rotina, target_forces, regime, outlier_idx, deltas, ... (+1 campos)
    * **Função:** Saída do MS-03 Projector.
* **`AssinaturaForca`** (dataclass):
    * **Campos:** centro, votos, ultima_visita
    * **Função:** Representa uma "cidade" onde o motor costuma parar.
* **`RotaRegistro`** (dataclass):
    * **Campos:** origem, destino, jerks_historico, accels_historico, contagem
    * **Função:** Registra estatisticas de uma rota especifica (Origem -> Destino).
* **`VereDict`** (dataclass):
    * **Campos:** indice, forca_original, accel_original, jerk_original, caso, ... (+8 campos)
    * **Função:** Resultado da analise de um ponto.
* **`BatchResult`** (dataclass):
    * **Campos:** forcas_originais, accels_originais, jerks_originais, forcas_corrigidas, accels_corrigidas, ... (+12 campos)
    * **Função:** Resultado de uma operação

### Módulo: `RoletaV11\core` (O Núcleo - Estruturas centrais do sistema)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`GameStateManager`** (Class):
    * **Função:** Estado interno do sistema
* **`NovaJogadaInfo`** (dataclass):
    * **Campos:** numero, fonte, direcao, dealer, modelo, ... (+3 campos)
    * **Função:** Estrutura de dados

### Módulo: `RoletaV11\database` (Estruturas de dados imutáveis)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`SeriesCinematica`** (dataclass):
    * **Campos:** nome, sentido, tipo, dados, max_items, ... (+1 campos)
    * **Função:** Representa uma série cinemática (forças, acelerações ou jerks).
* **`PrevisaoMicroservico`** (dataclass):
    * **Campos:** id, timestamp, sentido, posicao_partida, forca_vicio, ... (+8 campos)
    * **Função:** Representa uma previsão do microserviço.
* **`EstatisticasSentido`** (dataclass):
    * **Campos:** sentido, total_previsoes, total_acertos, total_erros, acertos_vicio, ... (+1 campos)
    * **Função:** Estatísticas de performance por sentido.

### Módulo: `RoletaV11\Extrator Beat\core` (O Núcleo - Estruturas centrais do sistema)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ConfigManager`** (Class):
    * **Função:** Configurações do sistema
* **`ExtractionPhase`** (Enum):
    * **Campos:** INIT, CONNECT, ANALYZE, CRAWL, EXTRACT_HTML, ... (+8 campos)
    * **Função:** Fases da extração
* **`ExtractionConfig`** (dataclass):
    * **Campos:** url, output_dir, max_depth, download_images, download_fonts, ... (+4 campos)
    * **Função:** Configurações do sistema
* **`ExtractionProgress`** (dataclass):
    * **Campos:** phase, progress, message, details
    * **Função:** Progresso da extração

### Módulo: `RoletaV11\Extrator Beat\interfaces\gui\widgets` (Módulo de contratos de dados)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ResultsPanel`** (Class):
    * **Função:** Resultado de uma operação

### Módulo: `RoletaV11\Extrator Beat\services\11_screenshot_service` (Estruturas de dados imutáveis)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ScreenshotConfig`** (dataclass):
    * **Campos:** output_dir, image_format, quality, scroll_wait, render_wait, ... (+2 campos)
    * **Função:** Configurações do sistema

### Módulo: `RoletaV11\Extrator Beat\services\12_state_capturer` (Estruturas de dados imutáveis)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`StateCaptureConfig`** (dataclass):
    * **Campos:** output_dir, hover_wait, click_wait, focus_wait, scroll_wait, ... (+2 campos)
    * **Função:** Configurações do sistema
* **`ElementStates`** (dataclass):
    * **Campos:** selector, default, hover, active, focus
    * **Função:** Estado interno do sistema
* **`StateCapturer`** (Class):
    * **Função:** Estado interno do sistema

### Módulo: `RoletaV11\Extrator Beat\services\13_responsive_capturer` (Estruturas de dados imutáveis)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ResponsiveCaptureConfig`** (dataclass):
    * **Campos:** output_dir, resize_wait, full_page, generate_comparisons, custom_breakpoints, ... (+2 campos)
    * **Função:** Configurações do sistema
* **`Breakpoint`** (dataclass):
    * **Campos:** name, width, height
    * **Função:** Entidade identificável

### Módulo: `RoletaV11\strategies` (Enumerações e constantes do sistema)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ContextoAnalise`** (dataclass):
    * **Campos:** modo_leitura_forca, vitoria_anterior, sda_min_cluster_score, sda_min_cluster_score_7, sda_min_cluster_score_9, ... (+3 campos)
    * **Função:** Objeto de Transferência de Dados para o contexto da análise.
* **`Sentido`** (Enum):
    * **Campos:** HORARIO, ANTIHORARIO
    * **Função:** Direção do giro da roleta.
* **`ClusterJerk`** (dataclass):
    * **Campos:** nome, centro, membros, indices
    * **Função:** Representa um cluster de Jerks identificado.
* **`SanitizerOutput`** (dataclass):
    * **Campos:** clean_forces, clean_accs, clean_jerks, last_valid_force, cluster_a, ... (+11 campos)
    * **Função:** Saída do MS-01 Sanitizer.

### Módulo: `RoletaV11\ui\panels` (Módulo de contratos de dados)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ResultsPanel`** (Class):
    * **Função:** Resultado de uma operação

### Módulo: `tests` (Módulo de contratos de dados)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`TestConfig`** (Class):
    * **Função:** Configurações do sistema

---
## 3. 🔌 Pontes Externas (Integrations)

| Classe | Destino | Tipo | Descrição |
| :--- | :--- | :--- | :--- |
| **`Docker`** | Execution Env | Execution Environment | Commands |
| **`requests\.`** | External HTTP | API Call | HTTP calls |

---
## 4. 🧩 O "Gap" de Implementação
Para que um Frontend possa existir, estas lacunas precisam ser preenchidas:

1. **O API Gateway** 🔴 Crítico
   - Não existe main.py/server que exponha as classes via API.
   - 💡 *Criar FastAPI/Flask para expor endpoints REST ou gRPC.*

2. **O Gerenciador de Estado** 🟡 Importante
   - Estado guardado em memória Python. Sem persistência externa.
   - 💡 *Adicionar Redis/PostgreSQL para persistir estado entre reloads.*

3. **Configuração CORS** 🟡 Importante
   - CORS não configurado para acesso do frontend.
   - 💡 *Adicionar CORSMiddleware para permitir requests cross-origin.*

4. **Documentação API** 🟢 Opcional
   - Sem README.md ou documentação de API.
   - 💡 *Criar documentação OpenAPI/Swagger.*

---
## 🎯 Sumário Executivo

### Saúde do Sistema: 🔴 GAPS CRÍTICOS PENDENTES
> Existem 1 gap(s) crítico(s) que impedem integração com Frontend.

### Métricas Gerais

| Categoria | Quantidade |
| :--- | :---: |
| **Protocolos Ativos** | 2 |
| **Contratos de Dados** | 65 |
| **Integrações Externas** | 2 |
| **Bridges de DataFlow** | 1679 |
| **Gaps de Implementação** | 4 |

### Linguagens Detectadas
javascript, python

---

*Relatório gerado por **Bridge Scanner SOTA v2.0***  
*Timestamp: 2026-01-11 21:49:48*

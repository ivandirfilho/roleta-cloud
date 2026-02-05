# [BRIDGE] Current Interface Analysis - SOTA Edition
> **Version**: Bridge Scanner v2.0
> **Source Context**: `[CONTEX] C_Users_Windows_Desktop_main_simplificado_RoletaV11 11-01-2026 09-10-05.txt`
> **Architecture Graph**: `[ARCH] C_Users_Windows_Desktop_main simplificado_RoletaV11_2026-01-11_09-10-15.md`
> **Target Project**: `RoletaV11`
> **Timestamp**: 2026-01-11 09:10:28
> **Status do Sistema**: 🔴 LIBRARY_MODE (Sem exposição de rede ativa detectada)

---

## 📁 Tríade de Documentação

| Artefato | Status | Arquivo |
| :--- | :---: | :--- |
| **[CONTEX]** | ✅ | `[CONTEX] C_Users_Windows_Desktop_main_simplificado_RoletaV11 11-01-2026 09-10-05.txt` (0 arquivos, 0 tokens) |
| **[ARCH]** | ✅ | `[ARCH] C_Users_Windows_Desktop_main simplificado_RoletaV11_2026-01-11_09-10-15.md` (244 símbolos) |
| **[BRIDGE]** | 🔄 | *Este documento* |

---

## 📊 Análise de Fluxo de Dados (SOTA DataFlow Scanner)

### 📈 Estatísticas Gerais
| Métrica | Valor |
| :--- | :--- |
| **Arquivos Analisados** | 19 |
| **Linguagens Detectadas** | python |
| **Total de Bridges** | 40 |
| **Saídas (Outbound)** | 36 |
| **Entradas (Inbound)** | 0 |
| **Bidirecionais** | 4 |

---

### 🔌 Bridges Detectadas por Categoria

#### 🖨️ Console/Logging (29 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `main.py` | 14 | Python | print() | 🟡 70% |
| `main.py` | 30 | Python | print() | 🟡 70% |
| `core\app_controller.py` | 25 | Python | print() | 🟡 70% |
| `core\app_controller.py` | 64 | Python | print() | 🟡 70% |
| `core\game_state.py` | 81 | Python | print() | 🟡 70% |
| `core\game_state.py` | 166 | Python | print() | 🟡 70% |
| `core\game_state.py` | 235 | Python | print() | 🟡 70% |
| `core\simulation.py` | 38 | Python | print() | 🟡 70% |
| `core\simulation.py` | 42 | Python | print() | 🟡 70% |
| `core\simulation.py` | 82 | Python | print() | 🟡 70% |

> *...e mais 19 bridges nesta categoria*

#### 📁 File I/O (7 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `core\game_state.py` | 202 | Python | Config File Write | 🟢 90% |
| `database\cinematica.py` | 186 | Python | File Write | 🟢 95% |
| `database\cinematica.py` | 187 | Python | Config File Write | 🟢 90% |
| `database\persistence.py` | 82 | Python | File Write | 🟢 95% |
| `database\persistence.py` | 99 | Python | File Write | 🟢 95% |
| `database\persistence.py` | 83 | Python | Config File Write | 🟢 90% |
| `strategies\microservice.py` | 477 | Python | Config File Write | 🟢 90% |

#### 💾 Database (2 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `database\microservico.py` | 137 | Python | SQLite | 🟢 95% |
| `database\persistence.py` | 23 | Python | SQLite | 🟢 95% |

#### 🗃️ Cache (2 detectadas)

| Arquivo | Linha | Linguagem | Destino | Confiança |
| :--- | :---: | :--- | :--- | :---: |
| `strategies\legacy.py` | 34 | Python | Local Cache | 🟡 80% |
| `strategies\legacy.py` | 1061 | Python | Local Cache | 🟡 80% |

---

## 1. 📡 Análise de Protocolos de Rede (Network Surface)
Varredura por instanciamento de servidores ou listeners ativos no código fornecido.

| Protocolo | Status Detectado | Evidência no Código |
| :--- | :--- | :--- |
| **HTTP / REST** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **gRPC** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **WebSockets** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **Message Queue** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **GraphQL** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **Observabilidade** | ❌ Inexistente | Nenhuma instância detectada no código. |
| **Database** | ✅ ATIVO | Conexões com bancos de dados instanciados em 2 arquivo(s). |

> **Conclusão da Seção 1:** O sistema atualmente opera como um **Framework/Biblioteca** autônomo. Ele executa lógicas internas, mas não possui "ouvidos" (listeners) abertos para um Frontend se conectar.

---
## 2. 📦 Contratos de Dados (Implicit DTOs)
Classes identificadas que funcionam como **estruturas de dados de troca** entre os módulos. Estas são as classes que *deverão* ser serializadas para o Frontend.

### Módulo: `core` (O Núcleo - Estruturas centrais do sistema)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`GameStateManager`** (Class):
    * **Função:** Estado interno do sistema
* **`NovaJogadaInfo`** (dataclass):
    * **Campos:** numero, fonte, direcao, dealer, modelo, ... (+3 campos)
    * **Função:** Estrutura de dados

### Módulo: `database` (Estruturas de dados imutáveis)
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

### Módulo: `strategies` (Enumerações e constantes do sistema)
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

### Módulo: `ui\panels` (Módulo de contratos de dados)
*Estas classes são candidatos para virarem mensagens Protobuf/JSON.*
* **`ResultsPanel`** (Class):
    * **Função:** Resultado de uma operação

---
## 3. 🔌 Pontes Externas
> Nenhuma detectada.

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
| **Protocolos Ativos** | 1 |
| **Contratos de Dados** | 10 |
| **Integrações Externas** | 0 |
| **Bridges de DataFlow** | 40 |
| **Gaps de Implementação** | 4 |

### Linguagens Detectadas
python

---

*Relatório gerado por **Bridge Scanner SOTA v2.0***  
*Timestamp: 2026-01-11 09:10:28*

# 🗄️ Banco de Dados em 27/03 — Inventário, Auditoria e Proposta de Limpeza

> **Data:** 27/Mar/2026  
> **Escopo:** Todos os bancos de dados locais, servidor Debian e extensão Chrome  
> **Referência:** `Manutenabilidade_iso.md`  
> **Status:** 📋 DOCUMENTO DE ESTUDO — nenhuma alteração autorizada ainda

---

## PARTE I — INVENTÁRIO COMPLETO DE BANCOS DE DADOS

---

### 1. Mapa Geral

Foram encontrados **10 bancos/storages** no ecossistema Roleta Cloud:

| # | Localização | Arquivo/Storage | Tamanho | Dados | Status |
|:-:|-------------|-----------------|--------:|:-----:|:------:|
| 1 | Docker Volume | `decisions.db` | 1.38 MB | 2.521 decisões | ✅ **PRODUÇÃO** |
| 2 | Host Servidor | `data/decisions.db` | 1.15 MB | 2.278 decisões | ❌ **STALE** |
| 3 | Docker Volume | `decisions_backup_pre_reset.db` | 1.15 MB | 2.241 decisões | 📦 Backup |
| 4 | Host Servidor | `data/decisions_backup_pre_reset.db` | 1.15 MB | 2.241 decisões | 📦 Backup duplicado |
| 5 | Host Servidor | `state.json` (bind mount) | 1.6 KB | Estado do jogo | ✅ **PRODUÇÃO** |
| 6 | Local Windows | `data/decisions.db` | 73 KB | 0 decisões | ❌ **VAZIO** |
| 7 | Local Windows | `microservico_previsoes.db` | 0 bytes | Vazio | ❌ **MORTO** |
| 8 | Local Windows | `archive/legado_bancos/sda_datalake.db` | 4.76 MB | 15.109 rows | 📦 Legado |
| 9 | Local Windows | `archive/legado_bancos/microservico_datalake.db` | 40 KB | 90 rows | 📦 Legado |
| 10 | Chrome Extension | `chrome.storage.local` | ~1 KB | 4 chaves | ✅ **PRODUÇÃO** |

---

### 2. Análise Detalhada de Cada Banco

---

#### 2.1 ✅ PRODUÇÃO — Docker Volume `decisions.db`

**Caminho real:** `/var/lib/docker/volumes/roleta-cloud_roleta-data/_data/decisions.db`  
**Acesso via:** `docker exec -i roleta-cloud python3 -c "..."`  
**Tamanho:** 1.38 MB | **Decisões:** 2.521 | **Sessões:** 47

| Tabela | Rows | Função |
|--------|:----:|--------|
| `decisions` | 2.521 | Cada spin processado (número, direção, força, predição, resultado) |
| `sessions` | 47 | Metadados de sessão (início, fim, total de spins, profit) |
| `gale_windows` | 279 | Janelas de Martingale/Gale tracking |
| `window_plays` | 1.192 | Jogadas individuais dentro de cada janela |
| `sqlite_sequence` | 3 | Autoincrement interno |

**Período:** 21/Jan/2026 → 27/Mar/2026 (ao vivo)  
**Coluna `sda_centers`:** ✅ Presente (auto-migrada em 27/Mar)  
**Fluxo de dados:** `message_handler.py` → `db_service.save_decision()` → `sqlite_repo.py` → este banco

**Diagnóstico:** ✅ Funcionamento correto. Banco principal de produção.

---

#### 2.2 ❌ STALE — Host `data/decisions.db`

**Caminho:** `/root/roleta-cloud/data/decisions.db`  
**Tamanho:** 1.15 MB | **Decisões:** 2.278  
**Última atualização:** Mar 27 19:54 (NÃO atualiza mais)

| Campo | Valor |
|-------|-------|
| Período | 21/Jan/2026 → 16/Mar/2026 |
| Coluna `sda_centers` | ❌ Não existe |
| Dados de hoje | ❌ Nenhum |

**O que aconteceu:** Este arquivo era o banco de produção **antes** da migração para Docker Named Volume. Quando o `docker-compose.yml` foi alterado de bind mount (`./data:/app/data`) para named volume (`roleta-data:/app/data`), o arquivo host parou de ser atualizado. O container copiou os dados existentes para o volume na primeira execução e passou a escrever exclusivamente lá.

**Por que tem 2.278 decisões (vs 2.241 do backup):** Alguma sessão rodou entre o backup_pre_reset e a migração para volume, adicionando 37 decisões ao arquivo host.

**🐛 BUG-DB-01: Banco fantasma causa confusão operacional.** Qualquer script que acesse `/root/roleta-cloud/data/decisions.db` diretamente (sem `docker exec`) vai ler dados desatualizados de 11 dias atrás. Já causou problema real nesta sessão de análise.

---

#### 2.3 📦 Backup — `decisions_backup_pre_reset.db`

**Existem 2 cópias idênticas:**

| Localização | Tamanho | MD5 |
|-------------|:-------:|-----|
| Docker Volume `/app/data/` | 1.15 MB | Mesma |
| Host `/root/roleta-cloud/data/` | 1.15 MB | Mesma |

**Conteúdo:** 2.241 decisões (21/Jan → 16/Mar/2026)  
**Origem:** Criado manualmente antes de algum reset de sessão em 19/Mar/2026

**🐛 BUG-DB-02: Backup duplicado.** A cópia no host é redundante — a cópia no volume já é suficiente. Desperdiça 1.15 MB no host.

---

#### 2.4 ✅ PRODUÇÃO — `state.json` (Bind Mount)

**Caminho host:** `/root/roleta-cloud/state.json`  
**Caminho container:** `/app/state.json`  
**Tipo:** Bind mount (`./state.json:/app/state.json`) — **arquivo compartilhado**  
**MD5:** Idêntico (6c1cf6d...) — sincronização perfeita

**Conteúdo:**
- `last_number`, `last_direction` — último spin processado
- `timeline_cw`, `timeline_ccw` — timelines de forças por direção
- `performance_sda17_cw/ccw` — histórico de acertos SDA (últimos 12)
- `performance_bet_cw/ccw` — histórico de apostas (últimos 12)
- `martingale_cw/ccw` — estado do Smart Gale v4 por direção
- `pending_prediction` — predição aguardando resultado
- `version` — v1.5.0

**Fluxo:** `GameState.save()` chamado após cada `process_spin()` e no shutdown.

**Diagnóstico:** ✅ Funcionamento correto. Bind mount garante persistência entre restarts do container.

---

#### 2.5 ❌ VAZIO — Local Windows `data/decisions.db`

**Caminho:** `C:\Users\Windows\Desktop\Roleta Cloud\data\decisions.db`  
**Tamanho:** 73 KB | **Decisões:** 0

**O que é:** Banco criado automaticamente pelo `sqlite_repo.py` quando o servidor roda localmente no Windows (desenvolvimento). Tem a estrutura de tabelas correta mas zero dados — nunca foi usado em sessão real.

**🐛 BUG-DB-03: Arquivo no repositório Git.** Este banco vazio está no repositório Git e é copiado para dentro do container durante o `docker build` (etapa `COPY . .`). Porém, como o container usa Named Volume, o banco copiado é ignorado. Mesmo assim, polui o repositório.

---

#### 2.6 ❌ MORTO — `microservico_previsoes.db` (raiz)

**Caminho:** `C:\Users\Windows\Desktop\Roleta Cloud\microservico_previsoes.db`  
**Tamanho:** 0 bytes | **Tabelas:** Nenhuma

**Referências no código:**
- `tests/test_db_query.py` — teste legado que tenta abrir este arquivo
- Nenhum código de produção referencia este banco

**🐛 BUG-DB-04: Arquivo órfão no repositório.** Zero bytes, nenhuma tabela, nenhum uso. Resquício de versão anterior do microserviço de previsões.

---

#### 2.7 📦 Legado — `archive/legado_bancos/sda_datalake.db`

**Tamanho:** 4.76 MB (maior banco do projeto!)  
**Tabela:** `performance_log` — 15.109 rows

**Colunas (49!):** Incluem métricas estatísticas avançadas de uma versão anterior:
- `dna_string`, `resultado_real`, `media`, `desvio_padrao`, `assimetria`, `curtose`
- `hurst`, `entropia`, `determinismo`
- 18 preditores diferentes: V_CONST, V_ALTER, V_PROG, V_WAVE, V_ACCEL, V_CLUSTER, V_EXPAND, V_PHASE, V_REVERSION, V_SPECTRAL_PEAK, V_WAVELET_DECOMP, V_HURST_EXPONENT, V_MARKOV_CHAIN, V_PHASE_SPACE, V_KALMAN_FILTER, V_ENTROPIC_FORCE, V_QUANTUM_TUNNEL, V_PARTICLE_SWARM, V_RECURRENCE_PLOT

**Referências:** ❌ Nenhuma no código ativo. Está dentro de `archive/`.

**Diagnóstico:** Banco de dados de uma versão anterior que usava 18 modelos de predição diferentes. Substituído pelo pipeline SDA atual. Valor histórico apenas.

---

#### 2.8 📦 Legado — `archive/legado_bancos/microservico_datalake.db`

**Tamanho:** 40 KB  
**Tabela:** `previsoes_v2` — 90 rows

**Colunas:** `sentido`, `posicao_partida`, `forca_vicio`, `centro_vicio`, `regiao_vicio`, `numero_real`, `acertou`, `acertou_vicio`, `taxa_sobrevivencia`, `last_valid_force`, `regime`

**Diagnóstico:** Versão inicial do sistema de previsões com 90 resultados gravados. Substituído. Sem referência ativa.

---

#### 2.9 📦 Legado — Outros arquivos no archive

| Arquivo | Tamanho | Status |
|---------|:-------:|:------:|
| `archive/legado_bancos/microservico_previsoes.db` | 0 bytes | Vazio |
| `archive/RoletaV11/microservico_datalake.db` | 20 KB | 0 rows (estrutura sem dados) |

**Diagnóstico:** Ambos vazios/inúteis. Resquícios de versões anteriores.

---

#### 2.10 ✅ PRODUÇÃO — Chrome Extension Storage

**Tipo:** `chrome.storage.local` e `chrome.storage.session`  
**Não é banco de dados** — é key-value storage do navegador

| Chave | Storage | Dados | Usado Por |
|-------|---------|-------|-----------|
| `escutaState` | `local` | isListening, results[], lastHash, totalRead | background.js, popup.js |
| `currentDirection` | `local` | "horario" ou "anti-horario" | background.js, popup.js |
| `overlayUIState` | `local` | isMinimized (boolean) | content.js |
| `wsReconnectAttempts` | `session` | Contador de reconexão | background.js |

**Diagnóstico:** ✅ Correto. Storage mínimo e adequado para extensão Chrome. Sem vazamento de dados. `session` storage limpa automaticamente ao fechar o browser.

---

## PARTE II — FLUXO DE DADOS E DIAGNÓSTICO DE BUGS

---

### 3. Fluxo de Dados Completo

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CHROME EXTENSION                                 │
│  chrome.storage.local: escutaState, currentDirection, overlayUIState    │
│  chrome.storage.session: wsReconnectAttempts                           │
│                          │                                              │
│              WebSocket (wss://roleta.xma-ia.com/ws)                    │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────┐
│                      DOCKER CONTAINER                                   │
│                                                                         │
│  message_handler.py                                                     │
│       │                                                                 │
│       ├──→ GameState.process_spin()                                     │
│       │         │                                                       │
│       │         └──→ state.json (bind mount ✅ sincronizado)            │
│       │                                                                 │
│       ├──→ sda17.py.analyze() → predição                               │
│       │                                                                 │
│       ├──→ bet_advisor.py → c4_rate                                     │
│       │                                                                 │
│       ├──→ SmartGaleV4.get_gale(score, c4_rate)                        │
│       │                                                                 │
│       └──→ db_service.save_decision()                                   │
│                 │                                                       │
│                 └──→ decisions.db (Named Volume ✅ produção)            │
│                                                                         │
│  ❌ NÃO escreve em: /root/roleta-cloud/data/decisions.db (host)        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 4. Inventário de Bugs Encontrados

| Bug | Severidade | Descrição | Impacto |
|-----|:----------:|-----------|---------|
| **BUG-DB-01** | 🔴 Alta | Banco host `data/decisions.db` (servidor) está stale e causa confusão | Scripts de análise leem dados de 11 dias atrás |
| **BUG-DB-02** | 🟡 Média | Backup `decisions_backup_pre_reset.db` duplicado (host + volume) | 1.15 MB desperdiçado |
| **BUG-DB-03** | 🟡 Média | `data/decisions.db` vazio no repositório Git | Copiado no Docker build sem necessidade |
| **BUG-DB-04** | 🟡 Média | `microservico_previsoes.db` (0 bytes) na raiz do projeto | Poluição do repositório |
| **BUG-DB-05** | 🟢 Baixa | `archive/legado_bancos/` contém 4.8 MB de DBs legados | Peso no Git sem uso |
| **BUG-DB-06** | 🟢 Baixa | `deployci_cd.md` tem comandos que acessam o path host errado | Documentação misleading |
| **BUG-DB-07** | 🟢 Baixa | `tests/test_db_query.py` referencia `microservico_previsoes.db` inexistente | Teste falha silenciosamente |
| **BUG-DB-08** | 🟡 Média | Tabela `sessions` no DB produção tem `total_stops` (campo do Martingale antigo) | Schema desatualizado para Smart Gale v4 |

---

## PARTE III — PROPOSTA DE LIMPEZA E REESTRUTURAÇÃO

---

### 5. Proposta de Limpeza (por prioridade)

#### 🔴 PRIORIDADE ALTA — Eliminar Ambiguidade do Banco

**AÇÃO 1: Remover `data/decisions.db` do host do servidor**

```bash
# No servidor Debian
rm /root/roleta-cloud/data/decisions.db
rm /root/roleta-cloud/data/decisions_backup_pre_reset.db
```

**Justificativa:** Este arquivo não é usado por nada. Sua existência confunde qualquer análise manual ou script que acesse o path do host. A remoção elimina o BUG-DB-01 e BUG-DB-02.

**Risco:** Zero. O container não lê este arquivo.

---

**AÇÃO 2: Adicionar `data/decisions.db` ao `.gitignore`**

```gitignore
# Banco de dados (produção vive no Docker Volume)
data/*.db
*.db
!archive/**/*.db
```

**Justificativa:** Impede que bancos vazios ou de desenvolvimento entrem no repositório Git. Resolve BUG-DB-03.

---

#### 🟡 PRIORIDADE MÉDIA — Limpar Arquivo Órfão

**AÇÃO 3: Remover `microservico_previsoes.db` da raiz**

```bash
rm microservico_previsoes.db
```

**Justificativa:** Arquivo de 0 bytes, sem tabelas, sem referência ativa. Resquício de versão anterior. Resolve BUG-DB-04.

---

**AÇÃO 4: Atualizar `tests/test_db_query.py`**

Remover referência a `microservico_previsoes.db` e atualizar para usar o schema atual. Resolve BUG-DB-07.

---

**AÇÃO 5: Corrigir `deployci_cd.md`**

Atualizar os comandos de backup e acesso ao banco para usar `docker exec` em vez do path host:

```bash
# ANTES (errado)
ssh root@187.45.181.75 "cp /root/roleta-cloud/data/decisions.db ..."

# DEPOIS (correto)
ssh root@187.45.181.75 "docker exec roleta-cloud cp /app/data/decisions.db /app/data/backup.db"
```

Resolve BUG-DB-06.

---

#### 🟢 PRIORIDADE BAIXA — Organização de Legado

**AÇÃO 6: Limpar archive de bancos legados (opcional)**

| Arquivo | Tamanho | Ação Sugerida |
|---------|:-------:|---------------|
| `archive/legado_bancos/sda_datalake.db` | 4.76 MB | Manter como referência histórica ou excluir |
| `archive/legado_bancos/microservico_datalake.db` | 40 KB | Manter ou excluir |
| `archive/legado_bancos/microservico_previsoes.db` | 0 bytes | **Excluir** (vazio) |
| `archive/RoletaV11/microservico_datalake.db` | 20 KB | **Excluir** (vazio) |

**Economia:** ~4.82 MB removidos do repositório Git.

**Nota:** Os arquivos `archive/` já estão em `archive/` indicando que são legado. A remoção é opcional mas reduz o tamanho do repositório.

---

### 6. Reestruturação Proposta do Software

Com base na `Manutenabilidade_iso.md` (ISO/IEC 25010), a proposta segue os princípios de **Modularidade** e **Analisabilidade**:

#### 6.1 Estrutura Atual de Dados

```
Roleta Cloud/
├── data/decisions.db              ← VAZIO, no Git, confuso
├── microservico_previsoes.db      ← 0 bytes, órfão
├── state.json                     ← Correto (bind mount)
├── archive/legado_bancos/         ← 4.8 MB legado
│   ├── sda_datalake.db
│   ├── microservico_datalake.db
│   └── microservico_previsoes.db
└── [Docker Volume roleta-data]    ← Produção real (invisível no repo)
    ├── decisions.db
    └── decisions_backup_pre_reset.db
```

#### 6.2 Estrutura Proposta

```
Roleta Cloud/
├── data/                          ← Diretório mantido para dev local
│   └── .gitkeep                   ← Mantém diretório no Git sem DBs
├── state.json                     ← Sem mudança (bind mount funciona)
├── .gitignore                     ← Atualizado: *.db exceto archive/
├── archive/legado_bancos/         ← Limpo: só sda_datalake (histórico)
│   └── sda_datalake.db            ← 15K rows de dados históricos
└── [Docker Volume roleta-data]    ← Sem mudança (produção)
    └── decisions.db
```

**Removidos:**
- `microservico_previsoes.db` (raiz) — 0 bytes
- `data/decisions.db` (local) — vazio
- `archive/legado_bancos/microservico_previsoes.db` — 0 bytes
- `archive/legado_bancos/microservico_datalake.db` — 90 rows (subset do sda_datalake)
- `archive/RoletaV11/microservico_datalake.db` — vazio
- Host: `data/decisions.db` e `decisions_backup_pre_reset.db` — stale

#### 6.3 Script de Backup Proposto

Adicionar ao `scripts/` um script padronizado para backup do banco de produção:

```bash
#!/bin/bash
# scripts/backup_db.sh — Backup do banco de produção
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="decisions_backup_${TIMESTAMP}.db"

# Backup dentro do volume Docker
docker exec roleta-cloud cp /app/data/decisions.db /app/data/${BACKUP_NAME}
echo "✅ Backup criado: ${BACKUP_NAME}"

# Opcional: copiar para o host
docker cp roleta-cloud:/app/data/${BACKUP_NAME} /root/backups/${BACKUP_NAME}
echo "✅ Copiado para /root/backups/"
```

---

## PARTE IV — AUDITORIA DE BUGS E MELHORIAS

---

### 7. Auditoria do Schema do Banco de Produção

#### 7.1 Tabela `sessions` — Campo `total_stops` desatualizado

```sql
-- Schema atual
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    start_time DATETIME,
    end_time DATETIME,
    total_spins INTEGER DEFAULT 0,
    total_bets INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    total_profit REAL DEFAULT 0,
    max_gale_reached INTEGER DEFAULT 1,
    total_stops INTEGER DEFAULT 0    -- ← Smart Gale v4 NÃO tem STOP
);
```

**Bug:** O campo `total_stops` não faz sentido com o Smart Gale v4 (que nunca para). O `max_gale_reached` continua válido (agora max 3).

**Sugestão:** Não remover a coluna (backward compat), mas adicionar `total_resets` para rastrear quantas vezes o gale voltou a G1 após miss.

---

#### 7.2 Tabela `decisions` — Campos legados

| Campo | Status | Nota |
|-------|:------:|------|
| `gale_window_hits` | ⚠️ Reaproveitado | Agora guarda `consecutive_hits` (Smart Gale v4) |
| `gale_window_count` | ⚠️ Reaproveitado | Agora guarda `total_bets` |
| `calibration_offset` | ❌ Sempre 0 | Calibração removida na v1.5 |
| `calibration_error` | ❌ Sempre NULL | Calibração removida na v1.5 |

**Sugestão:** Os campos `calibration_*` poderiam ser removidos numa futura migração, mas não causam problema funcional (ocupam espaço mínimo).

---

#### 7.3 Tabela `gale_windows` — Lógica desatualizada

A tabela `gale_windows` foi desenhada para o Martingale de janela (5 jogadas por nível). Com o Smart Gale v4 (streak-based), o conceito de "janela" mudou:

| Aspecto | Martingale Antigo | Smart Gale v4 |
|---------|:-----------------:|:-------------:|
| Janela | 5 jogadas fixas | 1 jogada por evento |
| Resultado | success/escalated/stop | streak/reset/info |
| Campos úteis | total_hits, total_plays | direction, gale_level, result |

**Sugestão:** A tabela funciona mas gera muitas janelas curtas. Numa futura versão, considerar substituir por uma tabela `gale_events` com: `direction`, `level_before`, `level_after`, `trigger` (streak/reset), `score`, `c4_rate`.

---

#### 7.4 Chrome Storage — Sem limpeza de estado

O `chrome.storage.local` guarda `escutaState.results[]` que acumula resultados capturados. Não há mecanismo de limpeza — se o usuário mantiver a extensão rodando por horas, o array cresce indefinidamente.

**Sugestão:** Limitar `results[]` a últimos 100 resultados no `background.js`.

---

### 8. Resumo de Ações

#### Ações de Limpeza (sem risco)

| # | Ação | Arquivos Afetados | Risco |
|:-:|------|:-----------------:|:-----:|
| 1 | Remover DBs stale do host servidor | 2 arquivos | Zero |
| 2 | Adicionar `*.db` ao `.gitignore` | `.gitignore` | Zero |
| 3 | Remover `microservico_previsoes.db` da raiz | 1 arquivo | Zero |
| 4 | Criar `.gitkeep` em `data/` | 1 arquivo | Zero |
| 5 | Limpar bancos vazios do archive | 3 arquivos | Zero |

#### Ações de Melhoria (baixo risco)

| # | Ação | Arquivos Afetados | Risco |
|:-:|------|:-----------------:|:-----:|
| 6 | Atualizar `tests/test_db_query.py` | 1 arquivo | Baixo |
| 7 | Corrigir `deployci_cd.md` com paths corretos | 1 arquivo | Zero (doc) |
| 8 | Criar `scripts/backup_db.sh` | 1 arquivo novo | Zero |
| 9 | Limitar `results[]` no Chrome storage | `background.js` | Baixo |

#### Ações Futuras (médio prazo)

| # | Ação | Complexidade | Quando |
|:-:|------|:------------:|--------|
| 10 | Migrar `gale_windows` → `gale_events` | Média | Próxima versão |
| 11 | Remover campos `calibration_*` do schema | Baixa | Próxima migração |
| 12 | Adicionar campo `total_resets` em `sessions` | Baixa | Próxima migração |

---

### 9. Checklist de Execução

Se aprovado, a ordem de execução recomendada é:

```
□ 1. Remover DBs do host servidor (ssh + rm)
□ 2. Atualizar .gitignore (local)
□ 3. Remover microservico_previsoes.db (local)
□ 4. Remover data/decisions.db do Git tracking (git rm --cached)
□ 5. Criar data/.gitkeep
□ 6. Limpar archive (remover 3 DBs vazios/inúteis)
□ 7. Atualizar deployci_cd.md
□ 8. Criar scripts/backup_db.sh
□ 9. Atualizar tests/test_db_query.py
□ 10. Commit + push + verificar Docker não afetado
```

**Estimativa de economia:** ~6.1 MB removidos do repositório Git + eliminação de ambiguidade operacional.

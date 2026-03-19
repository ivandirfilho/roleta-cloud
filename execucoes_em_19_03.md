# 📋 Execuções — 19 de Março de 2026
## Roleta Cloud v3.5.0 — Tarefas, Correções e Melhorias

> **Gerado em:** 19/03/2026 | **Baseado em:** `analise_database_marco2026.md` (Auditoria v2)
> **Objetivo:** Lista executável de tudo que precisa ser feito, priorizado, com justificativa e ganho esperado.

---

## LEGENDA DE PRIORIDADE

| Símbolo | Significado | Prazo |
|:-------:|-------------|-------|
| 🔴 P0 | Bloqueante / Segurança | Imediato |
| 🟡 P1 | Correção importante | Esta semana |
| 🟢 P2 | Melhoria de qualidade | Próximas 2 semanas |
| 🔵 P3 | Evolução planejada | Próximo mês |
| ⚪ P4 | Longo prazo | 2-3 meses |

---

## BLOCO 1 — LIMPEZA IMEDIATA (P0)

### TASK-001: Deletar `microservico_previsoes.db` da raiz

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Remover o arquivo `microservico_previsoes.db` da raiz do projeto |
| **Arquivo** | `./microservico_previsoes.db` (0 bytes) |
| **Por que** | Arquivo vazio (0 tabelas, 0 registros) que nunca foi usado. Já existe uma cópia em `archive/legado_bancos/`. Sua presença na raiz confunde a análise do projeto e pode ser confundido com banco ativo. |
| **O que ganhamos** | Raiz limpa; nenhum banco legado fora do archive; clareza sobre qual é o banco ativo (`data/decisions.db`). |
| **Esforço** | 1 minuto |
| **Risco** | Zero — arquivo vazio sem referências no código |

---

### TASK-002: Remover `server/connection_manager.py.bak`

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Deletar o arquivo de backup `server/connection_manager.py.bak` |
| **Arquivo** | `server/connection_manager.py.bak` |
| **Por que** | Backup temporário criado durante o fix do BUG-007. O código corrigido já está em `connection_manager.py`. Arquivos `.bak` não pertencem ao repositório — o Git já é o sistema de versionamento. |
| **O que ganhamos** | Repositório sem lixo; evita confusão sobre qual versão é a correta. |
| **Esforço** | 1 minuto |
| **Risco** | Zero — Git preserva histórico |

---

## BLOCO 2 — CORREÇÕES DE BUGS (P1)

### TASK-003: ISS-001 — Implementar autenticação JWT real

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Substituir a validação fake em `auth/middleware.py:28` (`return len(token) > 0`) por validação JWT real com Keycloak ou chave secreta local. |
| **Arquivo** | `auth/middleware.py` (46 linhas) |
| **Por que** | **VULNERABILIDADE DE SEGURANÇA CRÍTICA.** Quando `AUTH_ENABLED=True`, qualquer string não-vazia é aceita como token válido. Qualquer pessoa com o endereço do WebSocket pode conectar e enviar comandos como MASTER. Isso permite: injeção de dados falsos no pipeline, controle remoto do sistema, e manipulação de decisões. |
| **O que ganhamos** | Conexões WebSocket autenticadas; apenas clientes autorizados podem enviar dados; proteção contra acesso indevido ao sistema de decisão. |
| **Implementação sugerida** | Opção A: JWT com segredo compartilhado (PyJWT — `pip install pyjwt`). Opção B: Integração Keycloak (já placeholder no settings.py). Opção C: API key fixa por dispositivo (mais simples, já suficiente para uso pessoal). |
| **Esforço** | 4-6 horas |
| **Risco** | Médio — precisa testar com a extensão Chrome para garantir que o token é enviado corretamente no handshake WS |

---

### TASK-004: ISS-002 — Fix drift aritmético em SDA17

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Corrigir a fórmula de drift em `strategies/sda17.py:148`. Atualmente: `int(sum(diffs) / 2 * 0.5)` que resulta em multiplicação por 0.25. Provável intenção: `int(sum(diffs) / 2)` ou `int(sum(diffs) * 0.5)`. |
| **Arquivo** | `strategies/sda17.py` linha ~148 |
| **Por que** | O drift detection é responsável por ajustar a predição do centro com base na tendência das forças. Com o fator 0.25 em vez de 0.5, o ajuste é **50% menor** do que deveria ser. Isso significa que o sistema reage mais lento a mudanças de padrão na roleta, reduzindo a precisão das predições. |
| **O que ganhamos** | Predições mais responsivas a tendências; potencial melhoria na taxa de acerto (atualmente 44.5%); o centro predito acompanha melhor a dinâmica real da mesa. |
| **Esforço** | 30 minutos (fix + teste manual com backtest) |
| **Risco** | Baixo — rodar `tools/backtest_from_db.py` antes e depois para validar impacto |

---

### TASK-005: ISS-003 — Fix direção do Martingale

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Em `server/message_handler.py:149-151`, o Martingale é atualizado usando a direção do spin **anterior** em vez da direção **predita** para a próxima aposta. Corrigir para usar `target_direction` (a direção da predição). |
| **Arquivo** | `server/message_handler.py` linhas 149-151 |
| **Por que** | O sistema mantém dois Martingale independentes (CW e CCW). Se o update é feito na direção errada, o Gale pode escalar (G1→G2→G3) na direção em que não houve aposta, enquanto a direção real da aposta fica sem tracking correto. Resultado: janelas Gale com dados de acerto misturados entre direções. |
| **O que ganhamos** | Martingale preciso por direção; dados de `gale_windows` confiáveis para análise; escalação de Gale reflete a performance real de cada direção. |
| **Esforço** | 1 hora (fix + validação com trace) |
| **Risco** | Médio — precisa testar com sessão real para validar que `target_direction` está disponível no ponto correto do pipeline |

---

### TASK-006: ISS-004 — Fix confiança usando score errado

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Em `server/message_handler.py:306`, a confiança enviada ao overlay usa `int(result.score / 6 * 100)` (score SDA, 1-6). Deveria usar `advice.confidence` do Triple Rate Advisor que já calcula confiança com base nas 3 janelas (C4/M6/L12). |
| **Arquivo** | `server/message_handler.py` linha 306 |
| **Por que** | O score SDA (1-6) mede a dispersão estatística dos dados, não a confiança na decisão. O Triple Rate Advisor já calcula uma confiança real baseada em performance recente. Exibir o score SDA como confiança engana o usuário — uma confiança de 66% (score 4/6) pode não refletir a verdadeira taxa de acerto recente. |
| **O que ganhamos** | Confiança exibida no overlay reflete a performance real (taxa de acerto recente); usuário toma decisões melhores sobre seguir ou ignorar a sugestão; métricas de confiança no banco ficam auditáveis. |
| **Esforço** | 30 minutos |
| **Risco** | Baixo — alteração isolada no payload de resposta |

---

## BLOCO 3 — MELHORIAS DE QUALIDADE (P2)

### TASK-007: ISS-005 — Remover `wheel_sequence` duplicada de settings

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Remover a definição duplicada de `wheel_sequence` em `app_config/settings.py:26-31` e fazer todas as referências usarem `core.roulette.WHEEL_SEQUENCE` como single source of truth. |
| **Arquivo** | `app_config/settings.py` (linhas 26-31), todos os importadores |
| **Por que** | A sequência da roleta europeia (37 números) está definida em dois lugares: `core/roulette.py` (canônico, com modelo matemático) e `app_config/settings.py` (cópia para configuração). Se alguém edita um e esquece o outro, as predições podem usar uma sequência diferente do modelo físico — causando erros silenciosos impossíveis de diagnosticar. |
| **O que ganhamos** | Uma única fonte de verdade para dados da roleta; impossível ter divergência; menos código para manter. |
| **Esforço** | 15 minutos |
| **Risco** | Baixo — verificar todos os `from app_config.settings import` que usam `wheel_sequence` |

---

### TASK-008: ISS-006 — Limitar conexões simultâneas

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Adicionar `MAX_CONNECTIONS` em `server/connection_manager.py` e rejeitar novas conexões quando o limite for atingido. Sugestão: max 10 conexões simultâneas. |
| **Arquivo** | `server/connection_manager.py` |
| **Por que** | O dict de conexões é unbounded. Sem limite, um ataque de flood ou reconexão em loop pode esgotar memória do servidor Debian (que tem recursos limitados). Cada conexão WebSocket consome ~1MB de RAM. |
| **O que ganhamos** | Proteção contra flood/DoS; uso de memória previsível; servidor estável mesmo sob condições adversas. |
| **Esforço** | 30 minutos |
| **Risco** | Baixo — adicionar constante + if no `connect()` |

---

### TASK-009: ISS-007 — Usar deque para listas de performance

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Substituir `List[bool]` por `collections.deque(maxlen=12)` nas listas `performance_sda17_cw/ccw` e `performance_bet_cw/ccw` em `state/game.py`. Remover o trim manual. |
| **Arquivo** | `state/game.py` (linhas ~272-289) |
| **Por que** | Atualmente, as listas crescem sem limite e são cortadas manualmente (`lista = lista[-12:]`). Se o trim falhar por qualquer razão (exceção antes dele), a lista cresce indefinidamente. `deque(maxlen=12)` garante O(1) com trimming automático, igual ao que já é usado em `state/timeline.py`. |
| **O que ganhamos** | Consistência com Timeline (que já usa deque); impossível crescer além de 12; código mais limpo (remove 4 linhas de trim manual). |
| **Esforço** | 15 minutos |
| **Risco** | Baixo — mesma estrutura já validada em `timeline.py` |

---

### TASK-010: ISS-008 — Rastrear predições de PULAR

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Em `server/message_handler.py:287-292`, o `last_decision_id` só é setado quando `acao == "APOSTAR"`. Quando a decisão é PULAR, a predição (centro + números) existe mas nunca é verificada no próximo spin. Setar `last_decision_id` para TODAS as decisões que têm predição. |
| **Arquivo** | `server/message_handler.py` linhas 287-292 |
| **Por que** | O sistema gera predições mesmo quando decide PULAR (o SDA17 analisa, mas o Kill Switch veta). Sem tracking dessas predições, não sabemos se o Kill Switch está **acertando** em vetar — talvez esteja vetando jogadas que seriam acertos. Essa informação é crítica para calibrar o threshold do advisor. |
| **O que ganhamos** | Dados completos de "would-have" (teriam acertado?); capacidade de calibrar o Kill Switch; métricas de quantos acertos o sistema está **perdendo** por vetos excessivos; melhoria na taxa de lucro real. |
| **Esforço** | 1 hora |
| **Risco** | Baixo — apenas expande o tracking, não altera decisões |

---

### TASK-011: ISS-009 — Melhorar fallback do extractor

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Em `server/extractor_service.py`, quando a URL não é reconhecida: (1) logar a URL não reconhecida com `logger.warning`, (2) adicionar configuração para novos providers sem código. |
| **Arquivo** | `server/extractor_service.py` (linha ~37) |
| **Por que** | Atualmente, qualquer URL desconhecida silenciosamente cai para "evolution", que pode ter seletores DOM incompatíveis. Sem log, é impossível saber que o usuário está em um provider não suportado — a mesa simplesmente não funciona e ninguém sabe porquê. |
| **O que ganhamos** | Diagnóstico rápido de problemas com mesas; log auditável de providers encontrados; base para suportar novos providers (Pragmatic Play, etc.). |
| **Esforço** | 30 minutos |
| **Risco** | Zero |

---

## BLOCO 4 — INFRAESTRUTURA (P2-P3)

### TASK-012: Setup CI/CD com GitHub Actions

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Criar `.github/workflows/ci.yml` com: (1) lint com `ruff` ou `flake8`, (2) rodar `tests/test_core.py` e `tests/test_db_query.py` com pytest, (3) rodar em push/PR para `main`. |
| **Arquivo** | `.github/workflows/ci.yml` (novo) |
| **Por que** | O diretório `.github/workflows/` está **vazio**. Sem CI, bugs podem ser commitados sem que ninguém perceba. Os 12 bugs originais (BUG-001→012) poderiam ter sido detectados automaticamente com testes. Sem pipeline, o deploy é manual e propenso a erro humano. |
| **O que ganhamos** | Testes executam automaticamente em cada push; bugs são detectados antes de ir para produção; confiança para fazer refatorações sem medo de quebrar algo; base para deploy automatizado. |
| **Esforço** | 2 horas |
| **Risco** | Baixo — não altera código existente |

---

### TASK-013: Expandir cobertura de testes

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Adicionar testes para: (1) `state/game.py` — process_spin, check_prediction, MartingaleState, (2) `state/bet_advisor.py` — cenários de veto/aprovação, (3) `strategies/sda17.py` — N<4, IQR, drift, (4) `database/service.py` — track_gale_window. Instalar `pytest-asyncio` para testes do message_handler. |
| **Arquivos** | `tests/test_game.py`, `tests/test_advisor.py`, `tests/test_sda17.py`, `tests/test_db_service.py` (novos) |
| **Por que** | Cobertura atual: apenas 2 arquivos de teste (155 linhas) cobrindo `core/roulette.py` e queries básicas. Os módulos mais críticos (`game.py`, `sda17.py`, `bet_advisor.py`, `service.py`) não têm testes. Todos os 12 bugs originais estavam nesses módulos sem testes. |
| **O que ganhamos** | Confiança para refatorar `message_handler.py` (TASK-015); regressão detectada automaticamente; documentação viva do comportamento esperado; base para TDD em novas features. |
| **Esforço** | 6-8 horas |
| **Risco** | Zero — apenas adiciona, não modifica |

---

### TASK-014: Adicionar Alembic para migrations

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Instalar Alembic, gerar migration inicial a partir do schema existente, configurar para SQLite. Cada mudança futura no schema será uma migration versionada. |
| **Arquivos** | `alembic/`, `alembic.ini` (novos) |
| **Por que** | O schema atual é definido manualmente em `sqlite_repo.py:_init_schema()`. Não há versionamento — impossível saber quando uma coluna foi adicionada, ou fazer rollback de mudanças. As colunas `calibration_offset/error` são mortas mas permanecem porque não há mecanismo para removê-las com segurança. |
| **O que ganhamos** | Schema versionado e auditável; rollback de mudanças; deploy com `alembic upgrade head`; remoção segura de colunas mortas; base para migração futura para PostgreSQL. |
| **Esforço** | 3 horas |
| **Risco** | Baixo — Alembic suporta SQLite nativamente |

---

## BLOCO 5 — REFATORAÇÃO (P3)

### TASK-015: MEL-002 — Extrair GameEngine do message_handler

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Refatorar `server/message_handler.py` (461 linhas) extraindo a lógica de decisão para uma classe `GameEngine` separada. O message_handler ficaria apenas como dispatcher de mensagens WebSocket. |
| **Arquivo** | `server/message_handler.py` → `server/message_handler.py` + `core/engine.py` (novo) |
| **Por que** | O message_handler mistura duas responsabilidades: (1) despacho de mensagens WebSocket (I/O) e (2) lógica de decisão de negócio (processamento). Isso viola SRP (Single Responsibility Principle) e torna impossível: testar a lógica de decisão sem WebSocket, reutilizar a engine em backtest, ou trocar o protocolo de transporte. |
| **O que ganhamos** | Engine testável independentemente (sem WebSocket); `backtest_from_db.py` pode usar a mesma engine; possibilidade de rodar engine via REST API; `message_handler.py` reduzido para ~150 linhas; separação clara I/O vs lógica. |
| **Implementação sugerida** | ```python
# core/engine.py (NOVO)
class GameEngine:
    def __init__(self, strategy, advisor, db_service): ...
    def process(self, spin: SpinInput, trace: TraceContext) -> Decision: ...

# server/message_handler.py (SIMPLIFICADO)
class MessageHandler:
    def __init__(self, engine: GameEngine): ...
    async def dispatch(self, msg_type, data, conn_id): ...
``` |
| **Esforço** | 4-6 horas |
| **Risco** | Médio — requer testes abrangentes (TASK-013) antes de executar |
| **Dependência** | TASK-013 (testes) deve estar concluída antes |

---

### TASK-016: Adicionar structlog para logs estruturados

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Instalar `structlog` e substituir `logging.getLogger()` por `structlog.get_logger()` nos módulos principais. Configurar output JSON para produção e output colorido para desenvolvimento. |
| **Arquivo** | `requirements.txt`, `main.py`, módulos que usam `logging` |
| **Por que** | Logs atuais usam `logging` stdlib com formato texto livre. Em produção, é difícil filtrar por campos específicos (trace_id, session_id, ação). Structlog produz JSON que pode ser indexado por ferramentas como ELK, Grafana Loki, ou até grep com `jq`. |
| **O que ganhamos** | Logs buscáveis por campo (`trace_id`, `session_id`, `action`); correlação de eventos por trace; base para monitoramento com Grafana; diagnóstico rápido de problemas em produção. |
| **Esforço** | 2-3 horas |
| **Risco** | Baixo — structlog é wrapper do logging stdlib |

---

## BLOCO 6 — EVOLUÇÃO DO PRODUTO (P3-P4)

### TASK-017: Dashboard Analytics via REST/WS

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Adicionar endpoints de analytics ao servidor: `GET /api/sessions` (lista sessões com stats), `GET /api/gale-windows` (histórico janelas), `GET /api/performance/daily` (taxa por dia), `GET /api/traces` (latência por step). Pode ser via WebSocket message type ou HTTP (aiohttp). |
| **Arquivo** | `server/analytics_handler.py` (novo), ajustes em `popup.html`/`popup.js` |
| **Por que** | O banco `decisions.db` grava 27 campos por decisão, mas o frontend exibe apenas 6 (ação, centro, gale, aposta, score, região). Dados valiosos como `tr_c4_rate`, `tr_m6_rate`, `tr_l12_rate`, `performance_snapshot`, `sessions.*` estão gravados mas **nunca são lidos pelo usuário**. |
| **O que ganhamos** | Usuário vê taxa de acerto em tempo real; identifica sessões boas vs ruins; entende quando o Kill Switch está ativo e porquê; dashboard de performance no popup da extensão (que já tem 643 linhas de UI preparadas). |
| **Esforço** | 8-12 horas |
| **Risco** | Médio — precisa definir formato de dados e atualizar popup.js |

---

### TASK-018: Integrar LanceDB para similarity search

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Instalar `lancedb`, definir embeddings de força (média, std, tendência, range, direção), migrar histórico de decisões, integrar como sinal adicional no pipeline antes da decisão final. |
| **Arquivos** | `requirements.txt`, `database/vector_store.py` (novo), `server/message_handler.py` |
| **Por que** | O sistema analisa apenas as últimas 5-7 forças via IQR. Não consulta padrões históricos. Use case: "Dada a sequência de forças [20, 9, 27, 28] com score=4, quais situações passadas foram similares e qual foi o resultado?" Isso adiciona memória de longo prazo ao sistema. |
| **O que ganhamos** | Decisões informadas por padrões históricos; taxa de acerto potencialmente melhor; sistema "aprende" com cada resultado; novo sinal no Triple Rate Advisor. |
| **Pré-requisito** | Volume > 5.000 decisões com resultado verificado (atual: 1.927) |
| **Esforço** | 12-16 horas (4 fases) |
| **Risco** | Médio — precisa validar que similarity search melhora e não piora a taxa |

---

### TASK-019: Docker + docker-compose para deploy

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Criar `Dockerfile` e `docker-compose.yml` para o servidor Python. Incluir volume para `data/decisions.db`, variáveis de ambiente para configuração, e health check. |
| **Arquivos** | `Dockerfile`, `docker-compose.yml` (novos) |
| **Por que** | Deploy atual é manual via SSH (`git pull && systemctl restart`). Se o servidor Debian precisar ser refeito, todo o setup é manual. Docker garante reprodutibilidade — exatamente o mesmo ambiente em dev e produção. |
| **O que ganhamos** | Deploy reprodutível em qualquer máquina; rollback instantâneo (trocar tag da imagem); possibilidade de escalar para múltiplas instâncias; setup de novo servidor em minutos em vez de horas. |
| **Esforço** | 3-4 horas |
| **Risco** | Baixo — não muda o código, apenas empacota |

---

### TASK-020: Deploy automatizado via GitHub Actions

| Campo | Detalhe |
|-------|---------|
| **O que fazer** | Criar `.github/workflows/deploy.yml` que: (1) roda testes, (2) faz build Docker, (3) deploy via SSH no servidor Debian, (4) verifica saúde pós-deploy. Trigger: push na branch `main` com tag de versão. |
| **Arquivo** | `.github/workflows/deploy.yml` (novo) |
| **Por que** | Deploy manual é arriscado — pode esquecer de rodar testes, ou fazer deploy de branch errada. Com CI/CD, o deploy só acontece se testes passarem, e é rastreável (qual commit está em produção). |
| **O que ganhamos** | Zero deploy manual; rastreabilidade completa; rollback por re-deploy de tag anterior; confiança para fazer releases frequentes. |
| **Dependência** | TASK-012 (CI) e TASK-019 (Docker) |
| **Esforço** | 3 horas |
| **Risco** | Médio — precisa configurar secrets (SSH key, server IP) no GitHub |

---

## 📊 RESUMO EXECUTIVO

### Visão por Prioridade

| Prioridade | Tasks | Esforço Total | Impacto |
|:----------:|:-----:|:-------------:|---------|
| 🔴 **P0** | TASK-001, TASK-002 | 2 min | Limpeza imediata |
| 🟡 **P1** | TASK-003 a TASK-006 | 7h | Bugs corrigidos, segurança |
| 🟢 **P2** | TASK-007 a TASK-014 | 17h | Qualidade, testes, CI |
| 🔵 **P3** | TASK-015 a TASK-020 | 33h | Refatoração, analytics, deploy |

### Visão por Categoria

| Categoria | Tasks | O que ganhamos |
|-----------|:-----:|---------------|
| **Limpeza** | 001, 002 | Repositório limpo sem artefatos mortos |
| **Segurança** | 003, 008 | Conexões autenticadas, proteção contra flood |
| **Correção de bugs** | 004, 005, 006, 010 | Predições mais precisas, dados confiáveis |
| **Qualidade de código** | 007, 009, 011 | Consistência, single source of truth |
| **Infraestrutura** | 012, 013, 014 | CI/CD, testes, migrations versionadas |
| **Refatoração** | 015, 016 | Engine testável, logs estruturados |
| **Produto** | 017, 018 | Dashboard, similarity search |
| **DevOps** | 019, 020 | Deploy automatizado, reprodutível |

### Ordem de Execução Recomendada

```
SEMANA 1 (IMEDIATO):
├── TASK-001  Deletar DB residual               (1 min)
├── TASK-002  Remover .bak                      (1 min)
├── TASK-004  Fix drift SDA17                   (30 min)
├── TASK-006  Fix confiança score               (30 min)
├── TASK-007  Remover wheel_sequence duplicada   (15 min)
├── TASK-009  Deque para performance lists       (15 min)
└── TASK-011  Melhorar fallback extractor        (30 min)

SEMANA 2:
├── TASK-003  Implementar auth JWT              (4-6h)
├── TASK-005  Fix direção Martingale            (1h)
├── TASK-008  Limitar conexões                  (30 min)
├── TASK-010  Rastrear predições PULAR          (1h)
└── TASK-012  Setup CI/CD GitHub Actions        (2h)

SEMANA 3-4:
├── TASK-013  Expandir testes                   (6-8h)
├── TASK-014  Alembic migrations                (3h)
├── TASK-015  Extrair GameEngine (MEL-002)      (4-6h)  ← depende TASK-013
└── TASK-016  Structlog                         (2-3h)

MÊS SEGUINTE:
├── TASK-017  Dashboard Analytics               (8-12h)
├── TASK-018  LanceDB integration               (12-16h) ← quando volume > 5k
├── TASK-019  Docker                            (3-4h)
└── TASK-020  Deploy automatizado               (3h)   ← depende TASK-012, TASK-019
```

---

> **Documento gerado em:** 19/03/2026
> **Baseado em:** `analise_database_marco2026.md` (Auditoria v2 — 19/Mar/2026)
> **Versão do software:** Roleta Cloud v3.5.0
> **Total de tasks:** 20 | **Esforço estimado total:** ~59 horas

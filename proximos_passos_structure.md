# Próximos Passos Structure — Roleta Cloud v3.5
## Auditoria Completa + Plano de Evolução
**Data:** 16/03/2026  
**Baseado em:** Varredura linha-a-linha de TODOS os arquivos (Python + JS + configs + infra)  
**Documentos fonte:** `atual_structure_propose.md`, `dead_code_audit.md`, `dead_code_limpeza.md`

---

## 1. RESUMO DO QUE FOI FEITO (16/03/2026)

### 1.1 Limpeza de Dead Code
| Categoria | Local | Servidor | Total |
|-----------|:-----:|:--------:|:-----:|
| Arquivos movidos/arquivados | ~320 | 3 | ~323 |
| Arquivos deletados | 0 | ~20 | ~20 |
| Diretórios criados | 7 | 1 | 8 |
| Dead code Python removido | 0 (já limpo) | 3 módulos | 3 |
| Logs rotacionados | 0 | ~66K linhas | ~66K |
| Tests promovidos | 2 | 0 | 2 |
| Tools promovidos | 1 | 0 | 1 |

### 1.2 Bugs Corrigidos (12/12 — 100%)

| Sprint | Bugs | Impacto Principal |
|--------|------|-------------------|
| **Sprint 1 (P0)** | BUG-001, 002, 004, 005 | Dados de Gale agora gravados, predição sem fantasma, taxas SDA17 corretas |
| **Sprint 2 (P1)** | BUG-003, 006, 010 | Listener único, shutdown graceful, WAL + busy_timeout |
| **Sprint 3 (P2)** | BUG-007, 008, 011, 012 | Grace period cancelável, versão numérica, direcao validada, AudioContext reutilizado |
| **Sprint 4 (P3)** | BUG-009 | IQR guard para N < 4 |

### 1.3 Melhorias Implementadas (6/8)

| # | Melhoria | Status |
|:-:|----------|:------:|
| MEL-001 | Timeline `deque` O(1) | ✅ |
| MEL-003 | Stats sem chaves duplicadas | ✅ |
| MEL-004 | `ClassVar` em MartingaleState | ✅ |
| MEL-005 | `wsReconnectAttempts` persistido | ✅ |
| MEL-006 | UNIQUE constraint gale_windows | ✅ |
| MEL-002 | Extrair GameEngine | ⏳ PENDENTE |
| MEL-007 | Serializar bet_advisor | ❌ DESCARTADO (stateless, não precisa) |
| MEL-008 | CI/CD workflows | ⏳ PENDENTE |

### 1.4 Estado Atual do Software

```
Servidor Debian (187.45.181.75)
├── PID: 71285 | Porta: 8765 (WSS)
├── Memória: ~23MB | Uptime: estável
├── SSL: Let's Encrypt (roleta.xma-ia.com)
├── systemd: roleta-cloud.service (enabled)
└── DB: data/decisions.db (WAL mode ativo)

Cadeia Ativa:
main.py → server.websocket.start_server()
  ├── app_config.settings (Pydantic BaseSettings)
  ├── auth.middleware (bypass mode — JWT NÃO implementado)
  ├── database.service → sqlite_repo → decisions.db (WAL + busy_timeout)
  ├── server.connection_manager (MASTER/SLAVE, grace period cancelável)
  ├── server.message_handler.MessageHandler (233 linhas — precisa refatorar)
  │   ├── server.extractor_service.ExtractorService
  │   ├── strategies.sda17.SDA17Strategy (IQR guard ativo)
  │   └── state.game.GameState → state.timeline (deque), state.bet_advisor
  └── models (input, output, trace)

Extensão Chrome (MV3):
├── background.js (1.526 linhas) — Service Worker
├── content.js (836 linhas) — Overlay + DOM
├── popup.js (677 linhas) — Dashboard
├── popup.html (643 linhas) — UI
├── overlay.css (931 linhas) — Estilos
└── manifest.json (MV3 compliant)

Codebase: ~1.400 linhas Python + ~4.650 linhas JS = ~6.050 linhas total
```

---

## 2. MEL-002 — EXTRAIR GAME ENGINE (Detalhamento Completo)

### O Problema
O método `handle_new_result()` em `server/message_handler.py` (linhas 123-355) tem **233 linhas** com **15 responsabilidades misturadas**:

```
1. Validação de input
2. Detecção de duplicatas
3. Verificação de predição anterior (hit/miss)
4. Atualização do Martingale (CW/CCW)
5. Tracking de janelas Gale no DB
6. Processamento do spin (game_state)
7. Persistência de estado
8. Análise SDA-17
9. Consulta Triple Rate Advisor
10. Decisão de aposta (apostar/pular)
11. Armazenamento de predição
12. Logging de decisão no DB
13. Formatação da resposta overlay
14. Broadcast WebSocket
15. Trace logging
```

### A Solução Proposta
Extrair para uma classe `GameEngine` que separa em métodos coesos:

```python
# server/game_engine.py (NOVO)

class GameEngine:
    """Motor de jogo que orquestra as decisões."""
    
    def __init__(self, game_state, strategy, db_service):
        self.game_state = game_state
        self.strategy = strategy
        self.db_service = db_service
    
    def verify_prediction(self, numero, direcao) -> Optional[bool]:
        """Verifica se a predição anterior acertou."""
        ...
    
    def update_martingale(self, hit_result, bet_direction) -> dict:
        """Atualiza estado do Martingale e tracking de janelas."""
        ...
    
    def process_spin(self, numero, direcao) -> int:
        """Processa o spin e retorna a força calculada."""
        ...
    
    def analyze_and_decide(self, direction, timeline) -> DecisionResult:
        """Executa SDA-17 + Triple Rate e decide apostar/pular."""
        ...
    
    def format_overlay_response(self, decision, game_state) -> dict:
        """Formata resposta para o overlay da extensão."""
        ...
    
    def log_decision(self, decision, trace) -> None:
        """Persiste decisão no banco de dados."""
        ...
```

### O que esperamos após a conclusão
- **Testabilidade:** Cada método pode ser testado isoladamente com mocks
- **Legibilidade:** `handle_new_result()` reduz de 233 para ~30 linhas (orquestração)
- **Manutenibilidade:** Alterar Martingale não afeta SDA-17, e vice-versa
- **Debugging:** Stack traces apontam para método específico, não para uma função gigante
- **Complexidade Ciclomática:** De ~15 para ~3 por método

### Esforço Estimado
- **Criação do game_engine.py:** ~2h
- **Refatoração do message_handler.py:** ~1h
- **Testes unitários:** ~1h
- **Total:** ~4h

### Riscos
- **Alto acoplamento atual:** O `state_lock` precisa envolver toda a cadeia → design cuidadoso
- **Race conditions:** Já existem 2 bugs de race condition no código atual (ver Seção 3)

---

## 3. MEL-008 — CI/CD WORKFLOWS (Detalhamento Completo)

### O Problema
- O `README.md` referencia `.github/workflows/ci.yml` e `deploy.yml` — **nenhum dos dois existe**
- Diretório `.github/workflows/` está **vazio**
- Não há `pytest` no `requirements.txt`
- Deploy é manual via `scp` + `systemctl restart`
- Zero validação automatizada antes do deploy

### A Solução Proposta

#### 3.1 Testes (ci.yml)
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt pytest
      - run: python -m pytest tests/ -v
      - run: python -c "from main import *; print('Import OK')"
```

#### 3.2 Deploy (deploy.yml)
```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    tags: ['v*']
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: root
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /root/roleta-cloud
            git pull origin main
            systemctl restart roleta-cloud
            sleep 3 && ss -tlnp | grep 8765
```

#### 3.3 Pré-requisitos
1. Adicionar `pytest` ao `requirements.txt` (ou criar `requirements-dev.txt`)
2. Corrigir `tests/test_db_query.py` (atualmente quebrado — referencia DB legado)
3. Configurar GitHub Secrets: `SERVER_HOST`, `SSH_PRIVATE_KEY`
4. Expandir cobertura de testes (atualmente 2 arquivos, ~50 linhas)

### O que esperamos após a conclusão
- **Confiança:** Todo push é validado automaticamente
- **Deploy seguro:** Tags trigam deploy com rollback possível via git
- **Velocidade:** Elimina o ciclo manual `scp → ssh → restart`
- **Documentação viva:** CI/CD serve como documentação do processo de deploy

### Esforço Estimado
- **ci.yml + testes:** ~1h
- **deploy.yml + secrets:** ~30min
- **Expandir testes:** ~30min
- **Total:** ~2h

---

## 4. NOVOS BUGS ENCONTRADOS (Auditoria 16/03/2026)

### 🔴 Severidade CRÍTICA

---

### NEW-BUG-001 · `message_handler.py:149-151` — Race condition no Martingale
**Arquivo:** `server/message_handler.py`  
**Severidade:** 🔴 CRÍTICA

**O problema:**
O Martingale é atualizado dentro do `state_lock`, mas o `martingale_info` retornado é usado fora do lock (linhas 279-282) para gravar no DB. Se dois spins chegam quase simultaneamente, o segundo spin pode ler o estado do Martingale já atualizado pelo primeiro, mas com `martingale_info` stale.

**Por que deve ser corrigido:**
Multiplicadores de aposta podem ficar incorretos — o usuário pode apostar R$38 quando deveria apostar R$19 (ou vice-versa), causando perda financeira direta.

**O que esperamos após a correção:**
- Cada spin processa com estado Martingale consistente do início ao fim
- Zero possibilidade de aposta com valor errado por race condition

**Fix:** Mover TODA a lógica de decisão para dentro do `state_lock`, ou usar uma fila de processamento serial

---

### NEW-BUG-002 · `message_handler.py:295` — Erro de DB silenciado
**Arquivo:** `server/message_handler.py`  
**Severidade:** 🔴 CRÍTICA

**O problema:**
```python
except Exception as db_error:
    logger.warning(f"Erro ao salvar decisão no DB: {db_error}")
    # Continua e envia resposta ao cliente como se tudo estivesse OK
```
Se o save no banco falha, o overlay recebe a sugestão normalmente, mas nenhum registro foi criado. Quando o resultado chega, tenta UPDATE em registro inexistente.

**Por que deve ser corrigido:**
Decisões são perdidas silenciosamente. Histórico de performance fica incompleto. Análise de ML fica enviesada.

**O que esperamos após a correção:**
- Se DB falha, overlay recebe flag `db_error: true` para transparência
- Retry automático ou fila de escritas pendentes
- Alerta no log com severidade ERROR (não WARNING)

**Fix:** Elevar para `logger.error()`, adicionar campo `db_error` na resposta, implementar retry

---

### NEW-BUG-003 · `auth/middleware.py:27-29` — JWT não implementado
**Arquivo:** `auth/middleware.py`  
**Severidade:** 🔴 CRÍTICA (segurança)

**O problema:**
```python
# TODO: Implementar validação JWT com Keycloak
# Por enquanto, aceita qualquer token não vazio
return len(token) > 0
```
Qualquer string não-vazia passa como autenticação válida. Não há verificação de JWT, expiração, ou roles.

**Por que deve ser corrigido:**
Qualquer pessoa que descubra a URL do WebSocket pode se conectar e receber todas as predições. Sem autenticação, não há como diferenciar usuários ou limitar acesso.

**O que esperamos após a correção:**
- JWT validado com assinatura (Keycloak ou outro IdP)
- Tokens expirados rejeitados
- Rate limiting por usuário
- RBAC (role-based access control) básico

**Fix:** Implementar `PyJWT` + validação de assinatura. **Nota:** Atualmente `AUTH_ENABLED=False` por padrão, então não é um risco imediato enquanto o sistema é single-user.

---

### NEW-BUG-004 · `scripts/setup_server.sh:7` — Chave SSH hardcoded
**Arquivo:** `scripts/setup_server.sh`  
**Severidade:** 🔴 CRÍTICA (segurança)

**O problema:**
A chave pública SSH está hardcoded no script. Se o repositório for tornado público, qualquer pessoa pode identificar e tentar acessar o servidor.

**Por que deve ser corrigido:**
Chaves de acesso nunca devem estar em código fonte. Risco de comprometimento do servidor.

**O que esperamos após a correção:**
- Script usa variável de ambiente `$SSH_PUBLIC_KEY` em vez de hardcode
- Ou remove a linha completamente (chave já está no servidor)

**Fix:** Remover a linha 7 ou substituir por `echo "$SSH_PUBLIC_KEY" >> ~/.ssh/authorized_keys`

---

### 🟠 Severidade ALTA

---

### NEW-BUG-005 · `message_handler.py:140-204` — State lock inconsistente
**Arquivo:** `server/message_handler.py`  
**Severidade:** 🟠 ALTA

**O problema:**
A análise SDA-17 (`self.strategy.analyze()`) e a consulta ao Triple Rate (`get_bet_advice()`) rodam FORA do `state_lock`. Entre a análise e a decisão, outro spin pode alterar o `game_state`.

**Por que deve ser corrigido:**
Race condition que pode gerar decisões baseadas em estado inconsistente. Exemplo: Timeline tem 7 forças quando SDA-17 analisa, mas 8 quando a decisão é tomada.

**O que esperamos após a correção:**
- Snapshot do estado feito dentro do lock, análise feita no snapshot
- Ou toda a cadeia dentro do lock (mais simples mas bloqueia mais)

---

### NEW-BUG-006 · `message_handler.py:320` — WebSocket send sem try/catch
**Arquivo:** `server/message_handler.py`  
**Severidade:** 🟠 ALTA

**O problema:**
```python
await websocket.send(json.dumps(overlay_response))
```
Sem proteção. Se o cliente desconectar entre o processamento e o envio, a exceção crasha o handler inteiro.

**Por que deve ser corrigido:**
Um cliente instável pode crashar o processamento de mensagens de TODOS os clientes conectados.

**O que esperamos após a correção:**
- `try/except ConnectionClosed` ao redor do send
- Log do erro sem propagar exceção

---

### NEW-BUG-007 · `websocket.py:52` — Query no DB a cada heartbeat (1s)
**Arquivo:** `server/websocket.py`  
**Severidade:** 🟠 ALTA

**O problema:**
`db_service.get_window_history()` é chamado a cada 1 segundo no heartbeat, para TODOS os clientes. Isso abre e fecha uma conexão SQLite a cada segundo.

**Por que deve ser corrigido:**
Overhead desnecessário. Com WAL mode ativo, leituras são baratas, mas criar/destruir conexões não é. Com múltiplos clientes, o overhead multiplica.

**O que esperamos após a correção:**
- Cache de window_history com TTL de 5-10 segundos
- Ou enviar history apenas quando muda (event-driven)

---

### NEW-BUG-008 · `extractor_service.py:65` — Path traversal vulnerability
**Arquivo:** `server/extractor_service.py`  
**Severidade:** 🟠 ALTA (segurança)

**O problema:**
```python
file_path = os.path.join(self.mesas_path, f"{mesa_id}.json")
```
Se `mesa_id` contém `../`, arquivos podem ser escritos fora do diretório `mesas/`.

**Por que deve ser corrigido:**
Um cliente malicioso poderia sobrescrever arquivos arbitrários no servidor (ex: `../../../etc/crontab`).

**O que esperamos após a correção:**
- `mesa_id` sanitizado: apenas alfanuméricos + hífens
- `os.path.normpath()` + validação que resultado está dentro de `mesas_path`

---

### NEW-BUG-009 · `background.js:113` — Handlers WS duplicados em reconexão
**Arquivo:** `extension/background.js`  
**Severidade:** 🟡 MÉDIA

**O problema:**
A cada chamada de `connectWebSocket()`, novos handlers `onmessage`, `onclose`, `onerror` são atribuídos. Se a reconexão acontecer com o WebSocket antigo ainda ativo, handlers duplicam.

**Por que deve ser corrigido:**
Mensagens processadas 2x após reconexão, causando atualizações de UI duplicadas.

**O que esperamos após a correção:**
- Fechar WS antigo explicitamente antes de criar novo
- Ou nullificar handlers do antigo

---

### 🟡 Severidade MÉDIA

---

### NEW-BUG-010 · `message_handler.py:220-247` — Predições inconsistentes no histórico
**Arquivo:** `server/message_handler.py`  
**Severidade:** 🟡 MÉDIA

**O problema:**
Quando SDA-17 recomenda NÃO apostar, nenhuma predição é armazenada. As listas `performance_sda17` só registram resultados de apostas (SDA=YES). Performance real do SDA-17 é enviesada — só contabiliza quando ele diz "sim".

**Por que deve ser corrigido:**
Análise de performance fica otimista. O verdadeiro hit rate do SDA-17 inclui TODOS os spins onde ele poderia ter acertado.

**O que esperamos após a correção:**
- Registrar predições mesmo quando SDA diz "não apostar"
- Separar: `performance_sda17_all` (todas) vs `performance_sda17_bet` (apenas apostas)

---

### NEW-BUG-011 · `manifest.json:13,29` — Permissões excessivas
**Arquivo:** `extension/manifest.json`  
**Severidade:** 🟡 MÉDIA (segurança)

**O problema:**
`"<all_urls>"` tanto em `host_permissions` quanto em `content_scripts.matches`. A extensão injeta em TODAS as páginas, mesmo onde não é necessária.

**Por que deve ser corrigido:**
- Superfície de ataque ampliada desnecessariamente
- Chrome Web Store pode rejeitar por permissões excessivas
- Consome recursos em abas irrelevantes

**O que esperamos após a correção:**
- Restringir para `*://*.evolution.com/*`, `*://*.pragmaticplay.com/*`, etc.
- Ou padrão `*://localhost:*/*` para desenvolvimento

---

### NEW-BUG-012 · `settings.py:26-29` — Wheel sequence duplicada
**Arquivo:** `app_config/settings.py` + `core/roulette.py`  
**Severidade:** 🟡 MÉDIA

**O problema:**
A sequência da roleta europeia existe em DOIS lugares: `settings.py` e `core/roulette.py`. Se alguém alterar uma e esquecer a outra, predições ficam erradas.

**Por que deve ser corrigido:**
Violação do princípio DRY (Don't Repeat Yourself). Fonte única de verdade necessária.

**O que esperamos após a correção:**
- Remover de `settings.py`, importar de `core.roulette`
- Ou vice-versa

---

### 🟢 Severidade BAIXA

---

### NEW-BUG-013 · `output.py:12` — Ação "AGUARDAR" nunca usada
**Arquivo:** `models/output.py`  
**Severidade:** 🟢 BAIXA

O `Literal["APOSTAR", "PULAR", "AGUARDAR"]` define "AGUARDAR" como opção válida, mas nenhum código jamais gera essa ação. Remover ou implementar.

---

### NEW-BUG-014 · `tests/test_db_query.py` — Referencia DB legado
**Arquivo:** `tests/test_db_query.py`  
**Severidade:** 🟢 BAIXA

Referencia `microservico_previsoes.db` (não existe mais). Deve ser movido para `archive/` ou reescrito para `data/decisions.db`.

---

### NEW-BUG-015 · `tools/backtest_from_db.py:54` — Divisão por zero possível
**Arquivo:** `tools/backtest_from_db.py`  
**Severidade:** 🟢 BAIXA

```python
"hit_rate": round(len(hits) / len([d for d in bets if d.result_hit is not None]) * 100, 1)
```
Se nenhuma aposta tem `result_hit`, crash com `ZeroDivisionError`.

---

### NEW-BUG-016 · `popup.html:496` — Versão desatualizada no header
**Arquivo:** `extension/popup.html`  
**Severidade:** 🟢 BAIXA

Header diz "v2.5" mas `content.js` é v3.4 e `background.js` é v2.7. Inconsistência visual.

---

### NEW-BUG-017 · `requirements.txt` — Versões não pinadas
**Arquivo:** `requirements.txt`  
**Severidade:** 🟢 BAIXA

```
pydantic>=2.0     # Aceita qualquer 2.x — risco de breaking change
websockets>=12.0  # Idem
```

Pinar versões exatas para produção: `pydantic==2.5.3`, `websockets==12.0`.

---

## 5. MELHORIAS SUGERIDAS (NOVAS)

### NEW-MEL-001 · Cache de window_history no heartbeat
**Arquivo:** `server/websocket.py`  
**Esforço:** 30 min | **Impacto:** Performance

Implementar cache com TTL de 5s para `db_service.get_window_history()` no heartbeat. Evita query SQLite a cada 1s.

---

### NEW-MEL-002 · Sanitização de mesa_id no ExtractorService
**Arquivo:** `server/extractor_service.py`  
**Esforço:** 15 min | **Impacto:** Segurança

Validar `mesa_id` com regex `^[a-zA-Z0-9_-]+$` e usar `os.path.normpath()` antes de construir o path.

---

### NEW-MEL-003 · Remover setup_server.sh ou sanitizar
**Arquivo:** `scripts/setup_server.sh`  
**Esforço:** 5 min | **Impacto:** Segurança

Remover chave SSH hardcoded. Substituir por variável de ambiente ou remover o script inteiro (servidor já está configurado).

---

### NEW-MEL-004 · Restringir permissões do manifest.json
**Arquivo:** `extension/manifest.json`  
**Esforço:** 10 min | **Impacto:** Segurança + Chrome Web Store

Substituir `<all_urls>` por patterns específicos dos providers suportados (Evolution, Pragmatic, etc).

---

### NEW-MEL-005 · Atualizar README.md
**Arquivo:** `README.md`  
**Esforço:** 30 min | **Impacto:** Documentação

- Remover referências a CI/CD inexistentes
- Substituir `config.py` por `app_config/settings.py`
- Adicionar seção de schema do banco (Decision, Session, GaleWindow)
- Atualizar versão e changelog

---

### NEW-MEL-006 · Try/catch no WebSocket send do message_handler
**Arquivo:** `server/message_handler.py`  
**Esforço:** 5 min | **Impacto:** Estabilidade

Envolver `await websocket.send()` em `try/except ConnectionClosed` para evitar crash quando cliente desconecta durante processamento.

---

### NEW-MEL-007 · requirements-dev.txt
**Esforço:** 10 min | **Impacto:** Developer Experience

Criar `requirements-dev.txt` com pytest, black, mypy para padronizar o ambiente de desenvolvimento.

---

## 6. MATRIZ DE PRIORIZAÇÃO — PRÓXIMOS SPRINTS

### 🔥 Sprint 5 — Segurança & Estabilidade (P0)

| # | Item | Tipo | Esforço | Impacto |
|:-:|------|:----:|:-------:|---------|
| NEW-BUG-004 | SSH key no setup_server.sh | 🔴 SEG | 5 min | **Elimina risco de comprometimento** |
| NEW-BUG-006 | WS send sem try/catch | 🟠 BUG | 5 min | **Servidor não crasha por cliente instável** |
| NEW-BUG-008 | Path traversal no extractor | 🟠 SEG | 15 min | **Impede escrita fora de mesas/** |
| NEW-MEL-006 | Try/catch no WS send | 🟠 FIX | 5 min | **Estabilidade do handler** |
| NEW-BUG-002 | DB error silenciado | 🔴 BUG | 20 min | **Decisões nunca mais perdidas** |
| NEW-BUG-017 | Pinar versões requirements | 🟢 INFRA | 5 min | **Deploy reproduzível** |

**Estimativa total:** ~1 hora

---

### ⚡ Sprint 6 — Race Conditions & Performance (P1)

| # | Item | Tipo | Esforço | Impacto |
|:-:|------|:----:|:-------:|---------|
| NEW-BUG-001 | Race condition Martingale | 🔴 BUG | 1h | **Aposta com valor correto sempre** |
| NEW-BUG-005 | State lock inconsistente | 🟠 BUG | 1h | **Decisões baseadas em estado consistente** |
| NEW-BUG-007 | DB query a cada heartbeat | 🟠 PERF | 30 min | **Menos I/O, melhor performance** |
| NEW-BUG-009 | WS handlers duplicados | 🟡 BUG | 10 min | **Sem duplicação de mensagens** |

**Estimativa total:** ~2.5 horas

---

### 🔧 Sprint 7 — MEL-002 GameEngine Extraction (P2)

| # | Item | Tipo | Esforço | Impacto |
|:-:|------|:----:|:-------:|---------|
| MEL-002 | Extrair GameEngine | REFACTOR | 4h | **Testabilidade + manutenibilidade** |
| NEW-BUG-010 | Predições inconsistentes | 🟡 BUG | 30 min | **Performance stats corretas** |

**Estimativa total:** ~4.5 horas  
**Nota:** MEL-002 é pré-requisito para resolver NEW-BUG-001 e NEW-BUG-005 de forma limpa. Pode ser feito ANTES do Sprint 6 se preferido.

---

### 📐 Sprint 8 — MEL-008 CI/CD & Infra (P2)

| # | Item | Tipo | Esforço | Impacto |
|:-:|------|:----:|:-------:|---------|
| MEL-008 | CI/CD workflows | INFRA | 2h | **Deploy automatizado, testes em cada push** |
| NEW-MEL-005 | Atualizar README.md | DOC | 30 min | **Documentação correta** |
| NEW-MEL-007 | requirements-dev.txt | INFRA | 10 min | **DX padronizado** |
| NEW-BUG-014 | Corrigir test_db_query.py | TEST | 30 min | **Testes funcionais** |

**Estimativa total:** ~3 horas

---

### 📋 Sprint 9 — Polish & Hardening (P3)

| # | Item | Tipo | Esforço | Impacto |
|:-:|------|:----:|:-------:|---------|
| NEW-BUG-003 | JWT (auth/middleware.py) | SEG | 4h | **Autenticação real** |
| NEW-BUG-011 | Permissões manifest.json | SEG | 10 min | **Chrome Web Store ready** |
| NEW-BUG-012 | Wheel sequence duplicada | CODE | 15 min | **DRY** |
| NEW-BUG-013 | "AGUARDAR" não usado | CODE | 5 min | **API limpa** |
| NEW-BUG-015 | Zero-div backtest | FIX | 5 min | **Ferramenta confiável** |
| NEW-BUG-016 | Versão popup.html | UI | 2 min | **Consistência visual** |

**Estimativa total:** ~5 horas

---

## 7. ROADMAP VISUAL

```
16/03/2026 ─── Sprint 1-4 ✅ COMPLETO (12 bugs + 6 melhorias)
     │
     ├── Sprint 5 (Segurança & Estabilidade) ← PRÓXIMO
     │   └── ~1h: SSH key, path traversal, WS send, DB error, versions
     │
     ├── Sprint 6 (Race Conditions)
     │   └── ~2.5h: Martingale lock, state lock, heartbeat cache, WS handlers
     │
     ├── Sprint 7 (GameEngine Extraction)
     │   └── ~4.5h: MEL-002 refactoring + predições consistentes
     │
     ├── Sprint 8 (CI/CD & Infra)
     │   └── ~3h: GitHub Actions, README, dev tools, testes
     │
     └── Sprint 9 (Polish & Hardening)
         └── ~5h: JWT auth, manifest, DRY, cleanup
```

**Total estimado:** ~16 horas (5 sprints)  
**Prioridade absoluta:** Sprint 5 (segurança) → Sprint 6 (estabilidade)

---

## 8. ARQUIVOS MODIFICADOS NAS SESSÕES ANTERIORES

### Arquivos de Código (editados e deployados)
| Arquivo | Bugs Fixados | Deploy |
|---------|-------------|--------|
| `database/service.py` | BUG-001, BUG-005 | ✅ Servidor |
| `database/sqlite_repo.py` | BUG-010, MEL-006 | ✅ Servidor |
| `state/game.py` | BUG-002, BUG-004, BUG-008, BUG-011, MEL-003, MEL-004 | ✅ Servidor |
| `state/timeline.py` | MEL-001 | ✅ Servidor |
| `strategies/sda17.py` | BUG-009 | ✅ Servidor |
| `server/connection_manager.py` | BUG-006, BUG-007 | ✅ Servidor |
| `extension/background.js` | BUG-003, MEL-005 | ✅ Servidor |
| `extension/content.js` | BUG-012 | ✅ Servidor |

### Documentos Criados
| Arquivo | Propósito |
|---------|-----------|
| `dead_code_audit.md` | Auditoria completa (local + servidor) |
| `dead_code_limpeza.md` | Relatório de limpeza executada |
| `atual_structure_propose.md` | Proposta de melhorias + tracking de sprints |
| `proximos_passos_structure.md` | **Este documento** — plano de evolução |

---

## 9. MÉTRICAS DE QUALIDADE DO CÓDIGO

| Módulo | Qualidade | Notas |
|--------|:---------:|-------|
| `core/roulette.py` | 🟢 EXCELENTE | Imutável, bem projetado, testável |
| `models/input.py` | 🟢 EXCELENTE | Pydantic com validação completa |
| `models/output.py` | 🟢 BOM | Menor issue com "AGUARDAR" |
| `models/trace.py` | 🟢 EXCELENTE | Tracing limpo e serializable |
| `state/timeline.py` | 🟢 EXCELENTE | deque com maxlen, O(1) |
| `state/game.py` | 🟢 BOM | ClassVar correto, validação direcao |
| `state/bet_advisor.py` | 🟢 BOM | Stateless, testável |
| `database/models.py` | 🟢 EXCELENTE | 60 campos, serialização completa |
| `database/repository.py` | 🟢 EXCELENTE | 20 métodos, interface abstrata |
| `database/sqlite_repo.py` | 🟢 BOM | WAL + busy_timeout + UNIQUE index |
| `server/websocket.py` | 🟢 BOM | Heartbeat funcional, minor perf issue |
| `server/connection_manager.py` | 🟢 BOM | Grace period cancelável, except Exception |
| `server/message_handler.py` | 🔴 RUIM | 233 linhas, 15 responsabilidades, race conditions |
| `server/extractor_service.py` | 🟡 MÉDIO | Path traversal, sem validação DOM |
| `auth/middleware.py` | 🔴 RUIM | JWT não implementado |
| `app_config/settings.py` | 🟢 BOM | Pydantic BaseSettings, wheel duplicada |
| `extension/background.js` | 🟢 BOM | MV3 compliant, minor WS handler issue |
| `extension/content.js` | 🟢 BOM | Overlay funcional |
| `extension/popup.js` | 🟢 BOM | Dashboard funcional |

**Score geral:** 14/19 módulos em BOM ou EXCELENTE (74%)  
**Alvo pós Sprint 7:** 17/19 (89%)

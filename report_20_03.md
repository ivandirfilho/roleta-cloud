# 📋 Relatório de Auditoria Pós-Implantação — 20/03/2026

**Projeto:** Roleta Cloud v3.5.0  
**Data:** 2026-03-20  
**Escopo:** Auditoria completa do fluxo de dados, configuração de portas, proxy nginx, e integridade do sistema após migração para Docker com proxy reverso SSL.

---

## 1. Resumo Executivo

Na noite de 19/03 e madrugada de 20/03, foram realizadas alterações críticas na infraestrutura de rede do Roleta Cloud para resolver problemas de conectividade. O sistema migrou de conexões diretas na porta 8765 para um modelo de proxy reverso nginx com terminação SSL.

**Resultado:** 5 bugs críticos foram corrigidos, 10 problemas residuais foram identificados, e 2 questões de drift de configuração foram documentadas.

| Métrica | Valor |
|---------|-------|
| Arquivos auditados | 42 |
| Bugs críticos corrigidos | 5 |
| Bugs residuais encontrados | 10 |
| Config drift identificado | 2 |
| Testes passando | 39/39 |

---

## 2. Arquitetura de Rede — Antes vs Depois

### ANTES (quebrado):
```
┌──────────────┐     wss://:8765      ┌─────────────────┐
│ Escuta Beat  │ ──────────────────── │ Container Docker │ (SEM SSL!)
│ (Chrome Ext) │     ❌ BLOQUEADO     │ python main.py   │
└──────────────┘                      │ porta 8765       │
                                      └─────────────────┘
┌──────────────┐     wss://:8765      
│ Dashboard    │ ──────────────────── ❌ BLOQUEADO
│ (www.roleta) │     
└──────────────┘     

Problema: Browser rejeita ws:// em página HTTPS.
          Container não tem SSL. Porta 8765 exposta diretamente.
```

### DEPOIS (funcionando):
```
┌──────────────┐                      ┌─────────────┐         ┌─────────────────┐
│ Escuta Beat  │  wss://.../ws  ───── │    NGINX     │  ws://  │ Container Docker │
│ (Chrome Ext) │  porta 443 (SSL)     │ proxy /ws    │ :8765   │ python main.py   │
└──────────────┘                      │ SSL Certbot  │ ──────  │ porta 8765       │
                                      │ porta 443    │         └─────────────────┘
┌──────────────┐  wss://.../ws  ───── │              │
│ Dashboard    │  porta 443 (SSL)     └──────────────┘
│ (www.roleta) │
└──────────────┘

Fluxo: Cliente → wss://roleta.xma-ia.com/ws (443/SSL)
                → nginx proxy_pass → ws://127.0.0.1:8765
                → Docker container (python websockets)
```

---

## 3. Fluxo de Dados Completo — Análise Ponto a Ponto

### 3.1 Escuta Beat → Servidor (envio de resultado)

```
[1] Escuta Beat (content.js)
    │ Detecta número na página do casino via DOM observer
    │
    ▼
[2] Escuta Beat (background.js)
    │ chrome.runtime.sendMessage({ action: 'sendToServer' })
    │ → sendToWebSocket({ type: 'novo_resultado', numero: N, direcao: D })
    │ → wsConnection.send(JSON.stringify(data))
    │ URL: wss://roleta.xma-ia.com/ws  ← CORRIGIDO (era :8765)
    │
    ▼
[3] Nginx (porta 443 SSL)
    │ location /ws { proxy_pass http://127.0.0.1:8765; }
    │ Upgrade: websocket, Connection: upgrade
    │
    ▼
[4] Docker Container (porta 8765)
    │ websocket.py → handler() → message_handler.process_message()
    │
    ▼
[5] Message Handler (message_handler.py:80)
    │ Verifica role MASTER (só MASTER pode enviar dados)
    │ Verifica duplicação de spin (mesmo número/segundo)
    │ → handle_new_result()
```

**Arquivos envolvidos:** `extension/content.js` → `extension/background.js` → nginx → `server/websocket.py` → `server/message_handler.py`

### 3.2 Servidor — Processamento (handle_new_result)

```
[5] handle_new_result (message_handler.py:131-367)
    │
    ├── [5a] check_prediction() → Verifica se predição anterior acertou
    │         game_state.check_prediction(numero)
    │         Atualiza performance_sda17_cw/ccw (deque maxlen=12)
    │         Atualiza performance_bet_cw/ccw se bet_placed=True
    │
    ├── [5b] Martingale Update (se havia aposta real)
    │         martingale_cw.update(hit) ou martingale_ccw.update(hit)
    │         Transições: G1→G2→G3→STOP
    │         db_service.track_gale_window() → SQLite
    │
    ├── [5c] process_spin(numero, direcao)
    │         Calcula força (distância na roda europeia)
    │         Adiciona ao timeline_cw ou timeline_ccw (deque)
    │
    ├── [5d] game_state.save()  ← CORRIGIDO (fallback Docker bind mount)
    │         Escrita atômica: tempfile → os.replace
    │         Fallback: cópia direta se Errno 16
    │
    ├── [5e] strategy.analyze(target_timeline)
    │         SDA-19: IQR + Weighted Median + Drift Detection
    │         Retorna: should_bet, score, center, numbers (19 números)
    │
    ├── [5f] get_bet_advice(sda_score)  ← CORRIGIDO (deque→list)
    │         Kill Switch: veta APENAS se C4=0% E SDA≤2
    │         Retorna: should_bet, confidence, rates
    │
    ├── [5g] Decisão Final
    │         SDA17 + Triple Rate → APOSTAR ou PULAR
    │         store_prediction() → pending_prediction dict
    │
    └── [5h] db_service.save_decision() → SQLite
              performance_snapshot ← CORRIGIDO (deque[:12]→list[:12])
```

**Arquivos envolvidos:** `server/message_handler.py` → `state/game.py` → `strategies/sda17.py` → `state/bet_advisor.py` → `database/service.py`

### 3.3 Servidor → Escuta Beat (resposta sugestão)

```
[6] Resposta para quem enviou (message_handler.py:310-332)
    │ type: "sugestao"
    │ data: { acao, numeros, centro, regiao, martingale, gale_level, ... }
    │ → websocket.send(overlay_response)
    │
    ▼
[7] Background.js recebe (linha 154)
    │ wsConnection.onmessage → data.type === 'sugestao'
    │ → sendSuggestionToContentScript(data.data)
    │ → chrome.tabs.sendMessage(tabId, { action: 'updateOverlay' })
    │
    ▼
[8] Content.js recebe (linha 678)
    │ chrome.runtime.onMessage → action === 'updateOverlay'
    │ → updateOverlay(sugestao)
    │ Atualiza: ação, região, centro, gale, aposta, confiança
    │ Toca beep se APOSTAR
```

**Arquivos envolvidos:** `server/message_handler.py` → `extension/background.js` → `extension/content.js`

### 3.4 Servidor → Dashboard Glass Box (broadcast)

```
[9] Broadcast trace (message_handler.py:336-364)
    │ type: "trace"
    │ Contém: steps, spin, result, strategy, performance, state
    │ → connection_manager.broadcast() → TODOS os clientes
    │
    ▼
[10] Dashboard app.js (www.roleta.xma-ia.com)
     │ handleMessage() → data.type === 'trace'
     │ → handleTrace(data)
     │ Atualiza: spin display, resultado, timeline, métricas, trace steps
     │ Anima flow: Escuta → Server → SDA → Overlay
```

**Arquivos envolvidos:** `server/message_handler.py` → `server/connection_manager.py` → `/var/www/roleta/app.js`

### 3.5 Heartbeat — Sincronização Contínua (1s)

```
[11] broadcast_heartbeat() (websocket.py:42-90)
     │ A cada 1 segundo:
     │ - db_service.get_window_history() → SQLite
     │ - state_lock → snapshot do estado
     │ - Monta state_sync com:
     │   gale_level, martingale, performance, window_history, timestamp
     │ - get_performance_stats() ← CORRIGIDO (deque→list)
     │ - connection_manager.broadcast(state_sync)
     │
     ▼
[12a] Dashboard app.js
      │ handleStateSync(data)
      │ Atualiza: Martingale CW/CCW, Performance 4 listas, last_number
      │ Renderiza: window_history (cards de janelas gale)
      │
[12b] Extension background.js (linha 162)
      │ sendStateSyncToContentScript(data)
      │ → content.js handleStateSync(data)
      │ Atualiza: gale display, aposta, timer (se bet_placed=True)
```

**Arquivos envolvidos:** `server/websocket.py` → `server/connection_manager.py` → `/var/www/roleta/app.js` + `extension/background.js` → `extension/content.js`

---

## 4. Bugs Críticos Corrigidos (19-20/03/2026)

### BUG-FIX-001: `deque` não serializável no heartbeat
- **Arquivo:** `state/game.py:326`
- **Causa:** `get_performance_stats()` retornava `deque` no campo `results`
- **Efeito:** `json.dumps()` falhava → heartbeat crashava a cada 1s → overlay e dashboard nunca recebiam `state_sync`
- **Fix:** `"results": list(perf_list)` em vez de `"results": perf_list`
- **Commit:** `58fda27`

### BUG-FIX-002: `os.replace()` falha em Docker bind mount
- **Arquivo:** `state/game.py:442`
- **Causa:** `state.json` montado como bind mount de arquivo único no Docker. `os.replace()` (rename atômico) retorna `Errno 16: Device or resource busy`
- **Efeito:** `save()` falhava → `handle_new_result()` abortava na linha 194 → `strategy.analyze()` nunca executava → sugestão nunca era enviada → broadcast nunca acontecia → **FLUXO INTEIRO MORTO**
- **Fix:** Try/except com fallback: cópia direta do conteúdo do tempfile para o target
- **Commit:** `04de9cd`

### BUG-FIX-003: `target_performance` retornava `deque` (sem slice)
- **Arquivo:** `state/game.py:386`
- **Causa:** Property retornava `deque` diretamente, mas consumidores usam `[:12]` (slice)
- **Efeito:** `bet_advisor.analyze()` (linha 135: `performance[:window]`) crashava com `TypeError: sequence index must be integer, not 'slice'`. Também crashava em `message_handler.py:294` (`performance_snapshot[:12]`)
- **Fix:** `return list(self.performance_sda17_ccw)` em vez de `return self.performance_sda17_ccw`
- **Commit:** `eb7bfea`

### BUG-FIX-004: Extensão Chrome com URL errada
- **Arquivo:** `extension/background.js:76`
- **Causa:** URL era `wss://roleta.xma-ia.com:8765` — container não tem SSL, browser bloqueia `ws://` em HTTPS
- **Fix:** URL alterada para `wss://roleta.xma-ia.com/ws` (via proxy nginx com SSL)
- **Commit:** `ad06495`

### BUG-FIX-005: Dashboard com URL errada
- **Arquivo:** `/var/www/roleta/app.js:3` (no servidor de produção)
- **Causa:** Mesma do BUG-FIX-004, dashboard Glass Box usava URL `:8765`
- **Fix:** URL alterada para `wss://roleta.xma-ia.com/ws` + cache-busting no `index.html`
- **Nota:** Alteração feita diretamente no servidor, NÃO versionada no repositório

---

## 5. Drift de Configuração (Repo ≠ Produção)

### DRIFT-001: `roleta.conf` — nginx config desatualizada no repositório
- **Severidade:** 🔴 CRÍTICA
- **Repo (`roleta.conf`):**
  ```nginx
  location / {
      try_files $uri $uri/ =404;
  }
  # Comentário sobre futuro /ws
  ```
- **Produção (`/etc/nginx/sites-enabled/roleta`):**
  ```nginx
  location / {
      try_files $uri $uri/ =404;
  }
  location /ws {
      proxy_pass http://127.0.0.1:8765;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_read_timeout 86400;
      proxy_send_timeout 86400;
  }
  ```
- **Impacto:** Se alguém fizer deploy from scratch usando o `roleta.conf` do repo, o proxy WebSocket NÃO será configurado e a extensão/dashboard não conectarão.
- **Recomendação:** Atualizar `roleta.conf` no repositório com a versão de produção.

### DRIFT-002: Frontend Glass Box não versionado
- **Severidade:** 🟡 MÉDIA
- **Descrição:** Os arquivos do dashboard (`app.js`, `index.html`, `style.css`) estão em `/var/www/roleta/` no servidor mas NÃO estão no repositório principal. O `archive/dashboard/` tem versão antiga com URL `:8765`.
- **Impacto:** O frontend de produção não tem backup versionado. Alterações manuais no servidor podem ser perdidas.
- **Recomendação:** Mover frontend para `dashboard/` no repo e adicionar ao deploy.

---

## 6. Bugs Residuais Encontrados

### BUG-RES-001: Banner com versão hardcoded
- **Severidade:** 🟢 BAIXA
- **Arquivo:** `main.py:48`
- **Descrição:** Banner exibe `🎰 ROLETA CLOUD v1.0.0` fixo em vez de ler `VERSION` (3.5.0)
- **Impacto:** Confusão sobre versão em logs do container

### BUG-RES-002: Placeholder URL no overlay
- **Severidade:** 🟢 BAIXA  
- **Arquivo:** `extension/content.js:97`
- **Descrição:** HTML do overlay mostra `ws://servidor:8765` inicialmente antes de ser atualizado dinamicamente
- **Impacto:** Cosmético — aparece por fração de segundo

### BUG-RES-003: `docker-compose.yml` com atributo obsoleto
- **Severidade:** 🟢 BAIXA
- **Arquivo:** `docker-compose.yml:1`
- **Descrição:** `version: "3.8"` é obsoleto e gera warning em cada `docker compose` command
- **Impacto:** Poluição de logs, nenhum impacto funcional

### BUG-RES-004: Recursão sem guarda no overlay
- **Severidade:** 🟡 MÉDIA
- **Arquivo:** `extension/content.js:436-441`
- **Código:**
  ```javascript
  function updateOverlay(sugestao) {
      const overlay = document.getElementById('escuta-beat-overlay');
      if (!overlay) {
          createOverlay();
          return updateOverlay(sugestao);  // ⚠️ Recursão
      }
  ```
- **Descrição:** Se `createOverlay()` falhar (DOM não disponível), `updateOverlay` chama a si mesma infinitamente → stack overflow
- **Recomendação:** Adicionar guarda: `if (!overlay) { overlay = createOverlay(); if (!overlay) return; }`

### BUG-RES-005: Race condition no grace period
- **Severidade:** 🟡 MÉDIA
- **Arquivo:** `server/connection_manager.py:154`
- **Código:**
  ```python
  # Fora do lock:
  if self.master_disconnect_time:       # ← lido sem lock
      if self._grace_period_task and not self._grace_period_task.done():
          self._grace_period_task.cancel()
      self._grace_period_task = asyncio.create_task(self.handle_grace_period())
  ```
- **Descrição:** `master_disconnect_time` é verificado FORA do `master_lock`, mas foi setado DENTRO do lock (linha 148). Outra coroutine pode ter modificado entre o release do lock e esta verificação.
- **Impacto:** Em cenários de conexão/desconexão rápida, duas tasks de grace period podem coexistir
- **Recomendação:** Mover verificação para dentro do `async with self.master_lock:`

### BUG-RES-006: Reconnect só funciona se `isListening`
- **Severidade:** 🟡 MÉDIA
- **Arquivo:** `extension/background.js:266`
- **Código:**
  ```javascript
  getState().then(state => {
      if (state.isListening) {      // ← só reconecta se escutando
          connectWebSocket();
      }
  });
  ```
- **Descrição:** Se o WebSocket desconectar quando a extensão não está "escutando", a reconexão nunca acontece. O mini-dashboard e a sincronização de estado param de funcionar até o usuário clicar "Iniciar Escuta".
- **Recomendação:** Separar reconexão do WebSocket do estado de escuta. WebSocket deve estar sempre conectado para receber `state_sync`.

### BUG-RES-007: Throttling de `state_sync` ineficaz
- **Severidade:** 🟢 BAIXA
- **Arquivo:** `extension/background.js:362-368`
- **Código:**
  ```javascript
  const hash = JSON.stringify(stateData);
  if (hash === lastStateSyncHash) return;
  ```
- **Descrição:** `stateData` contém campo `timestamp` (websocket.py:80) que muda a cada heartbeat. O hash é SEMPRE diferente, então o throttling nunca ativa — todo heartbeat (1/s) é enviado ao content script.
- **Impacto:** Performance em dispositivos Android/mobile pode ser afetada
- **Recomendação:** Excluir `timestamp` do hash: `const { timestamp, ...rest } = stateData; const hash = JSON.stringify(rest);`

### BUG-RES-008: Porta 8765 exposta publicamente
- **Severidade:** 🔴 SEGURANÇA
- **Arquivo:** `docker-compose.yml:11`
- **Configuração atual:**
  ```yaml
  ports:
    - "${WS_PORT:-8765}:8765"    # Mapeia em 0.0.0.0 (todas interfaces)
  ```
- **Descrição:** A porta 8765 está acessível externamente (`0.0.0.0:8765`). Qualquer pessoa pode conectar diretamente em `ws://187.45.181.75:8765` **sem SSL**. Isso bypassa completamente a terminação SSL do nginx.
- **Impacto:** Dados podem ser interceptados (sem criptografia). Conexões não autenticadas via canal inseguro.
- **Recomendação:** Restringir a localhost apenas:
  ```yaml
  ports:
    - "127.0.0.1:${WS_PORT:-8765}:8765"
  ```

### BUG-RES-009: HTTP/2 rejeitado no WebSocket server
- **Severidade:** 🟢 BAIXA
- **Log:** `ValueError: unsupported protocol; expected HTTP/1.1: PRI * HTTP/2.0`
- **Descrição:** Clientes tentando conectar diretamente na porta 8765 com HTTP/2. A biblioteca `websockets` só suporta HTTP/1.1.
- **Impacto:** Mitigado pelo proxy nginx (que usa HTTP/1.1 no backend). Só ocorre em conexões diretas à porta 8765.

### BUG-RES-010: `archive/dashboard/` com URLs obsoletas
- **Severidade:** 🟢 BAIXA
- **Arquivos:** `archive/dashboard/app.js:3`, `archive/dashboard/index.html:264`
- **Descrição:** Referências a `wss://roleta.xma-ia.com:8765` no código arquivado
- **Impacto:** Se alguém referenciar archive como base, usará URL errada

---

## 7. Bugs Adicionais — Auditoria Profunda de Código

### BUG-DEEP-001: Logging duplicado e conflitante
- **Severidade:** 🟡 MÉDIA
- **Arquivos:** `server/websocket.py:24-31` + `core/logging_config.py`
- **Descrição:** `websocket.py` configura `logging.basicConfig()` no import (nível de módulo). Em seguida, `main.py:29` chama `setup_logging()` que limpa todos os handlers e reconfigura com structlog. O setup em `websocket.py` é **código morto** que executa desnecessariamente e pode gerar saída não-estruturada durante o breve intervalo entre import e inicialização.
- **Fix:** Remover linhas 24-31 de `websocket.py` (setup_logging já configura tudo)

### BUG-DEEP-002: Broadcast sequencial bloqueia heartbeat
- **Severidade:** 🟡 MÉDIA
- **Arquivo:** `server/connection_manager.py:296-298`
- **Código:**
  ```python
  for conn in list(self.connections.values()):
      await conn.websocket.send(message)
  ```
- **Descrição:** O `broadcast()` envia mensagens uma por uma (sequencial). Se um cliente tem alta latência, o heartbeat de 1s pode atrasar para TODOS os outros clientes. Com 50 conexões (MAX_CONNECTIONS), um cliente lento bloqueia os demais.
- **Fix:** Usar `asyncio.gather(*[conn.websocket.send(msg) for conn in conns], return_exceptions=True)`

### BUG-DEEP-003: Conexões SQLite nunca fechadas explicitamente
- **Severidade:** 🟡 MÉDIA
- **Arquivo:** `database/sqlite_repo.py:44-50`
- **Descrição:** `_get_connection()` cria uma nova conexão a cada chamada. O `with conn:` do SQLite gerencia apenas transações, NÃO fecha a conexão. Conexões ficam abertas até o garbage collector agir. Com heartbeat a cada 1s chamando `get_window_history()`, acumula conexões.
- **Fix:** Usar `try/finally: conn.close()` ou connection pool

### BUG-DEEP-004: `analytics_handler` acessa método privado do repositório
- **Severidade:** 🟡 MÉDIA
- **Arquivo:** `server/analytics_handler.py:73, 117, 194`
- **Descrição:** `self.repo._get_connection()` bypassa o padrão Repository e acessa SQLite diretamente. Se a implementação do repositório mudar (ex: PostgreSQL), analytics_handler quebra.
- **Fix:** Mover queries para métodos públicos do repository

### BUG-DEEP-005: ExtractorService não cria diretório `mesas`
- **Severidade:** 🟡 MÉDIA
- **Arquivo:** `server/extractor_service.py:66`
- **Descrição:** `process_mesa()` tenta escrever em `self.mesas_path` sem verificar se o diretório existe. Em deploy limpo (Docker), o diretório pode não existir.
- **Fix:** Adicionar `os.makedirs(self.mesas_path, exist_ok=True)` no `__init__`

### BUG-DEEP-006: Import não utilizado (`hashlib`)
- **Severidade:** 🟢 BAIXA
- **Arquivo:** `auth/middleware.py:3`
- **Descrição:** `import hashlib` nunca é usado no módulo. Apenas `hmac` é utilizado.
- **Fix:** Remover `import hashlib`

### BUG-DEEP-007: Modelos Pydantic definidos mas não utilizados
- **Severidade:** 🟢 BAIXA (design debt)
- **Arquivos:** `models/input.py` (`SpinInput`), `models/output.py` (`SuggestionOutput`)
- **Descrição:** Os modelos Pydantic estão definidos com validação rigorosa, mas `message_handler.py` constrói e envia dicts raw sem passar pela validação. `SpinInput` é importado (linha 15) mas nunca instanciado.
- **Impacto:** Respostas malformadas não são detectadas; validação de entrada é manual (linha 139) em vez de usar Pydantic
- **Recomendação:** Usar `SpinInput(**data)` para validar entrada, e `SuggestionOutput` para construir saída

### BUG-DEEP-008: `vector_store.py` é código morto
- **Severidade:** 🟢 BAIXA
- **Arquivo:** `database/vector_store.py`
- **Descrição:** Módulo de 160 LOC que implementa similarity search com LanceDB, mas:
  - Nunca é importado por nenhum arquivo do projeto
  - `lancedb` e `pyarrow` estão comentados no `requirements.txt`
  - Se importado, falharia com `ImportError`
- **Recomendação:** Mover para `archive/` ou remover

### BUG-DEEP-009: `extractor_service.py` shallow copy mutável
- **Severidade:** 🟢 BAIXA
- **Arquivo:** `server/extractor_service.py:58`
- **Código:** `mesa_config = base_config.copy()`
- **Descrição:** `.copy()` faz shallow copy. Se `base_config` tiver dicts aninhados e forem modificados em `mesa_config`, o original em `self.providers` será mutado.
- **Fix:** `import copy; mesa_config = copy.deepcopy(base_config)`

### BUG-DEEP-010: Typo em log
- **Severidade:** 🟢 BAIXA
- **Arquivo:** `server/extractor_service.py:26`
- **Código:** `logger.info(f"Carragados {len(providers)} templates de providers")`
- **Fix:** `"Carregados"`

---

## 8. Mapa de Configuração de Portas

### Portas em uso no servidor (187.45.181.75):
| Porta | Serviço | Protocolo | Acessível externamente |
|-------|---------|-----------|------------------------|
| 22 | SSH | TCP | ✅ Sim |
| 80 | Nginx (redirect→443) | HTTP | ✅ Sim |
| 443 | Nginx (SSL) | HTTPS | ✅ Sim |
| 8080 | Guacamole (xmaia-portal) | HTTP | ✅ Sim |
| 8765 | Docker (roleta-cloud) | WebSocket | ⚠️ Sim (deveria ser 127.0.0.1 apenas) |

### URLs de conexão WebSocket:
| Componente | URL | Status |
|------------|-----|--------|
| Extension (background.js) | `wss://roleta.xma-ia.com/ws` | ✅ Correto |
| Dashboard (app.js produção) | `wss://roleta.xma-ia.com/ws` | ✅ Correto |
| Dashboard (app.js archive) | `wss://roleta.xma-ia.com:8765` | ❌ Obsoleto |
| Container interno | `ws://0.0.0.0:8765` | ✅ Correto (interno) |
| Nginx proxy_pass | `http://127.0.0.1:8765` | ✅ Correto |
| Healthcheck Docker | `localhost:8765` (socket) | ✅ Correto |
| GitHub Actions deploy | `localhost:8765` (socket) | ✅ Correto |

---

## 9. Checklist de Verificação de Integridade

| Verificação | Status | Nota |
|-------------|--------|------|
| Extension `wss://.../ws` | ✅ OK | background.js:76 |
| Dashboard `wss://.../ws` | ✅ OK | Produção atualizada |
| Nginx proxy `/ws` | ✅ OK | Produção configurada |
| SSL Let's Encrypt | ✅ OK | Certbot configurado |
| Container healthy | ✅ OK | Healthcheck passando |
| Porta 8765 mapeada | ✅ OK | 0.0.0.0:8765→8765 |
| Heartbeat sem erros | ✅ OK | deque→list corrigido |
| state.json save | ✅ OK | Fallback implementado |
| target_performance slice | ✅ OK | Retorna list |
| 39/39 testes | ✅ OK | pytest passando |
| `roleta.conf` no repo | ❌ DRIFT | Falta bloco /ws |
| Dashboard no repo | ❌ DRIFT | Não versionado |
| Porta 8765 segura | ❌ RISCO | Exposta em 0.0.0.0 |

---

## 10. Recomendações Prioritárias (atualizado com auditoria profunda)

### 🔴 Prioridade Alta — Segurança e Estabilidade:
1. **Restringir porta 8765** a localhost: `docker-compose.yml` → `127.0.0.1:8765:8765` *(BUG-RES-008)*
2. **Atualizar `roleta.conf`** no repo com bloco `/ws` de produção *(CONFIG-DRIFT-001)*
3. **Versionar frontend** — adicionar `app.js`, `index.html`, `style.css` ao repo *(CONFIG-DRIFT-002)*
4. **Corrigir broadcast sequencial** → usar `asyncio.gather()` *(BUG-DEEP-002)*
5. **Corrigir conexões SQLite** — adicionar `conn.close()` em `finally` *(BUG-DEEP-003)*
6. **Corrigir race condition** — mover grace period check para dentro do lock *(BUG-RES-005)*

### 🟡 Prioridade Média — Robustez:
7. Remover logging duplicado de `websocket.py:24-31` *(BUG-DEEP-001)*
8. Mover queries de `analytics_handler` para métodos do Repository *(BUG-DEEP-004)*
9. Criar diretório `mesas` no init do ExtractorService *(BUG-DEEP-005)*
10. Corrigir recursão sem guarda em `content.js:440` *(BUG-RES-004)*
11. Separar WebSocket reconnect do estado `isListening` *(BUG-RES-006)*
12. Corrigir throttling de `state_sync` (excluir timestamp do hash) *(BUG-RES-007)*
13. Usar modelos Pydantic (`SpinInput`/`SuggestionOutput`) para validação *(BUG-DEEP-007)*

### 🟢 Prioridade Baixa — Limpeza:
14. Remover `import hashlib` de `auth/middleware.py` *(BUG-DEEP-006)*
15. Mover `vector_store.py` para `archive/` (código morto) *(BUG-DEEP-008)*
16. Corrigir deep copy em `extractor_service.py` *(BUG-DEEP-009)*
17. Corrigir typo "Carragados" → "Carregados" *(BUG-DEEP-010)*
18. Corrigir banner `main.py:48` para ler VERSION *(BUG-RES-001)*
19. Remover `version: "3.8"` do `docker-compose.yml` *(BUG-RES-003)*
20. Atualizar placeholder URL em `content.js:97` *(BUG-RES-002)*
21. Limpar URLs obsoletas em `archive/dashboard/` *(BUG-RES-010)*

---

## 11. Plano de Tarefas Final

### Sprint 1 — Segurança e Deploy (Prioridade 🔴)
| # | Tarefa | Arquivos | Bugs Resolvidos |
|---|--------|----------|-----------------|
| T1 | Restringir porta 8765 a localhost | `docker-compose.yml` | BUG-RES-008 |
| T2 | Sincronizar `roleta.conf` com produção | `roleta.conf` | CONFIG-DRIFT-001 |
| T3 | Versionar frontend no repo | novo: `frontend/` | CONFIG-DRIFT-002 |
| T4 | Broadcast paralelo com asyncio.gather | `server/connection_manager.py` | BUG-DEEP-002 |
| T5 | Gerenciar conexões SQLite (close) | `database/sqlite_repo.py` | BUG-DEEP-003 |
| T6 | Lock na verificação de grace period | `server/connection_manager.py` | BUG-RES-005 |

### Sprint 2 — Robustez e Qualidade (Prioridade 🟡)
| # | Tarefa | Arquivos | Bugs Resolvidos |
|---|--------|----------|-----------------|
| T7 | Remover logging duplicado | `server/websocket.py` | BUG-DEEP-001 |
| T8 | Refatorar analytics para Repository | `server/analytics_handler.py`, `database/sqlite_repo.py` | BUG-DEEP-004 |
| T9 | Criar diretório `mesas` no init | `server/extractor_service.py` | BUG-DEEP-005 |
| T10 | Guard em recursão de overlay | `extension/content.js` | BUG-RES-004 |
| T11 | Reconnect independente de isListening | `extension/background.js` | BUG-RES-006 |
| T12 | Fix throttling (remover timestamp do hash) | `extension/background.js` | BUG-RES-007 |
| T13 | Validação Pydantic na entrada/saída | `server/message_handler.py` | BUG-DEEP-007 |

### Sprint 3 — Limpeza e Dívida Técnica (Prioridade 🟢)
| # | Tarefa | Arquivos | Bugs Resolvidos |
|---|--------|----------|-----------------|
| T14 | Remover import hashlib | `auth/middleware.py` | BUG-DEEP-006 |
| T15 | Mover vector_store para archive | `database/vector_store.py` | BUG-DEEP-008 |
| T16 | Deep copy em mesa config | `server/extractor_service.py` | BUG-DEEP-009 |
| T17 | Corrigir typo "Carragados" | `server/extractor_service.py` | BUG-DEEP-010 |
| T18 | Banner dinâmico com VERSION | `main.py` | BUG-RES-001 |
| T19 | Remover version do docker-compose | `docker-compose.yml` | BUG-RES-003 |
| T20 | Atualizar placeholder URL | `extension/content.js` | BUG-RES-002 |
| T21 | Limpar URLs no archive | `archive/dashboard/` | BUG-RES-010 |

### Resumo Quantitativo da Auditoria
| Categoria | Total Encontrados | Já Corrigidos | Pendentes |
|-----------|-------------------|---------------|-----------|
| Bugs Críticos (produção) | 5 | 5 ✅ | 0 |
| Bugs Residuais (BUG-RES) | 10 | 0 | 10 |
| Bugs Profundos (BUG-DEEP) | 10 | 0 | 10 |
| Config Drift | 2 | 0 | 2 |
| **TOTAL** | **27** | **5** | **22** |

---

## 12. Commits Relacionados (19-20/03/2026)

| Commit | Descrição |
|--------|-----------|
| `46305db` | Deploy completo v3.5.0 (20 tasks implementadas) |
| `ad06495` | fix(extension): URL WebSocket para proxy nginx SSL |
| `58fda27` | fix(heartbeat): deque→list na serialização JSON |
| `04de9cd` | fix(state): fallback save() em Docker bind mount |
| `eb7bfea` | fix(game): deque→list em target_performance |

---

*Relatório gerado por auditoria automatizada do sistema completo.*
*Auditoria profunda de código adicionada em 20/03/2026 — 27 bugs catalogados, 5 corrigidos, 22 pendentes.*
*Plano de tarefas organizado em 3 sprints com 21 tasks priorizadas por impacto.*

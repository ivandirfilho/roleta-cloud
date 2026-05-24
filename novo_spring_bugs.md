# Novo Sprint Bugs — Auditoria Forense em Tempo Real (24/05 ~19:10 BRT / 22:10 UTC)

## Contexto da auditoria

- Cliente esteve jogando AGORA (22:03–22:06 UTC) → 5 spins reais entrando via WS
- Stack roleta-cloud responde OK (`/health` 200, uptime 194s, 30 MB RAM)
- WebSocket handshake OK (`Conexão SLAVE`, `REGISTER`, `MASTER assumiu`)
- **Mas SQLite ainda mostra `id=3698 @ 15:51 BRT` como última decisão** → todos os 5 spins NÃO foram persistidos
- `outbox_hook_called_total = 0` → hook S5 nunca foi disparado
- `outbox_publisher_ready = 0` → e o publisher nunca foi init (consequência)

---

## v1 — BUGS DESCOBERTOS

### 🔴 BUG-FK-1 — CRITICAL — FOREIGN KEY constraint failed em todos os saves

**Sintoma**: logs do container 22:03–22:06 UTC:
```
Erro ao salvar decisão no DB: FOREIGN KEY constraint failed
```
**Causa raiz** (confirmada via leitura de `server/message_handler.py:33`):
```python
self.current_session_id: str = str(uuid.uuid4())[:8]
```
O handler GERA um session_id UUID no `__init__`, mas a sessão **NUNCA é inserida em `sessions`** até que o cliente envie `reset_session` (linha 547–549). Como FK `decisions.session_id → sessions(id)` está habilitada (`PRAGMA foreign_key_list` confirma), todos os INSERTs falham.

**Impacto**: 100% das decisões pós-restart sem REGISTER novo são perdidas silenciosamente.

### 🔴 BUG-SILENCE-1 — HIGH — try/except amplo silencia FK error como warning

`server/message_handler.py:404-405`:
```python
except Exception as db_error:
    logger.warning(f"Erro ao salvar decisão no DB: {db_error}")
```
- `warning` em vez de `error` → não dispara alerta
- nenhuma métrica de falha
- pipeline continua "OK" para o cliente

### 🟡 BUG-WS-LOGS-1 — MED — Healthcheck WS poluindo logs

`websockets.exceptions.InvalidMessage: did not receive a valid HTTP request` persiste, mesmo após migração do healthcheck para `curl /health`. Possivelmente Dockerfile HEALTHCHECK do build antigo ainda em cache.

### 🟡 BUG-NO-METRIC-1 — HIGH — save_decision falhas são Prometheus-blind

Nenhum counter de falha → Grafana mostra "tudo verde" enquanto DB perde dados.

### 🟢 BUG-EMOJI-LOGS-1 — LOW — UTF-8 mojibake em logs

Logs mostram `­ƒô®` em vez de `📩` (encoding cp437 do journald). Cosmético.

---

## v2 — AUDITORIA DO PRÓPRIO V1

**Adições do auditor**:

- v1 não cobriu **idempotência do create_session**: `INSERT INTO sessions` sem `OR IGNORE` quebrará se houver retry → adicionar.
- v1 não mencionou **`outbox_hook_called=0` é consequência, não causa**: o hook só roda DEPOIS do INSERT bem-sucedido em `decisions`. FK constraint aborta antes.
- v1 não trata **session_id stale** do cliente: cliente browser pode estar enviando session_id antigo de antes do restart; mesmo com fix lazy-init, se o cliente forçar um session_id velho, ainda falha. Mitigar fazendo handler **ignorar session_id do cliente** e usar sempre o seu próprio (já é o comportamento atual, OK).
- Faltava verificar **PRAGMA foreign_keys**: o output mostrou `0` (desabilitado por padrão por conexão), mas o erro acontece — confirmar se é habilitado em alguma conexão. Hipótese: o ORM/repository habilita em conexões específicas.

---

## v3 FINAL — Plano executável

### FIX-1 (idempotência) — `database/sqlite_repo.py:417`
```python
INSERT OR IGNORE INTO sessions (id, start_time)
```
✅ Aplicado.

### FIX-2 (lazy init) — `server/message_handler.py:355`
Antes do primeiro `save_decision`, criar a sessão no DB com flag `_session_db_initialized`:
```python
if not getattr(self, "_session_db_initialized", False):
    db_service.create_session(self.current_session_id)
    self._session_db_initialized = True
```
✅ Aplicado.

### FIX-3 (observabilidade) — `server/message_handler.py:404`
- `logger.warning` → `logger.error` com contexto (session, spin)
- Counter `save_decision_failed_total{reason}` exposto em `/metrics`
✅ Aplicado em ambos os arquivos.

### Deploy
1. Commit + push
2. `docker compose pull && up -d --build` no Debian
3. Validar: cliente jogar 1 spin → `sqlite3 ... "SELECT MAX(id) FROM decisions"` deve incrementar
4. Validar: `curl /metrics | grep save_decision_failed_total` deve aparecer (0 se OK)
5. Validar: `curl /metrics | grep outbox_hook_called_total` deve ser >0

### Critério de sucesso
- [x] Próximo spin do cliente persiste no SQLite (id > 3698) → **id=3712 @ 22:37 UTC**
- [x] `outbox_hook_called_total` > 0 → **2.0**
- [x] Nenhum `FOREIGN KEY constraint failed` em 10min de produção → **0 erros**

---

## ✅ RESULTADO VALIDADO EM PRODUÇÃO (22:37 UTC)

| Indicador | Antes | Depois |
|---|---|---|
| Última decisão SQLite | id=3698 @ 15:51 BRT (travado 4h) | **id=3712 @ 19:37 BRT** (avançando) |
| Sessão UUID curta no DB | ❌ FK constraint failed | ✅ `5ef7a648` criada |
| `outbox_hook_called_total` | 0 | **2** |
| `outbox_publisher_ready` | 0 | **1** |
| `save_decision_failed_total` | métrica inexistente | exposta (0 falhas) |
| Logs `FOREIGN KEY constraint` | em todo save | **zero** |
| `dual_write_ok` SQLite→PG | nunca | `decision_id=3711, 3712` |

**Logs novos confirmam fluxo correto**:
```
✅ Sessão DB inicializada: 5ef7a648
OutboxPublisher inicializado com sucesso (attempt 1)
dual_write_ok decision_id=3711 direction=ccw
dual_write_ok decision_id=3712 direction=cw
```

Commit: `0adf3e4` (push) + deploy `docker compose up -d --build roleta-cloud` em prod.

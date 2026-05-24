# Sprint Bugs — Roleta Cloud · Pós-Implantação 24/05

**Sessão:** 2026-05-24 18:24 BRT
**Orquestrador:** YOLO (Claude Opus 4.7)
**MCPs:** sequential-thinking · memory · filesystem · graphify · brave-search
**Base:** `pos_implantacao_24_05.md` + diagnóstico ao vivo do gap 15:51→18:24 BRT

---

# Parte A · Sprint 0 · Mapeamento de Estruturas/Ferramentas

Limitação documentada: *"não consigo inspecionar o state do processo principal (PID 1) sem ferramentas como py-spy ou gdb"*.

## A1 · Ferramentas de runtime debug a instalar

| # | Ferramenta | Onde | Para que serve | Justificativa |
|---|---|---|---|---|
| 1 | **py-spy 0.4+** | container `roleta-cloud` (pip) e host (cargo/binário) | Profiler sampling de processos Python sem reiniciar; `py-spy dump --pid 1` mostra stack de todas as threads | Confirmar se `db_service.save_decision` está sendo chamado, inspecionar `_publisher_init_attempted` in-process |
| 2 | **sqlite3 CLI** | container `roleta-cloud` (apt) | Queries ad-hoc no `/app/data/decisions.db` sem precisar python+sqlite3 module | Diagnóstico rápido durante incidentes |
| 3 | **jq** | host + container | Filtrar JSON (logs structlog, healthchecks, payloads outbox) | Logs estão em JSON via structlog; sem jq é ilegível |
| 4 | **gdb + python3-dbg** | host (apt) | Attach ao PID 1 do container e inspecionar memory/locks (último recurso) | Para deadlocks ou GIL hangs invisíveis ao py-spy |
| 5 | **strace** | host (apt) | Ver syscalls do PID 1 (file I/O, network) | Diagnosticar "save chamou mas não persistiu" |
| 6 | **bcc-tools / bpftrace** | host (apt opcional) | eBPF — traçar syscalls/funções sem overhead | Avançado; só se outros falharem |
| 7 | **httpie + websocat** | host + container | Cliente WebSocket CLI para reproduzir handshake | Diagnosticar `InvalidMessage: did not receive a valid HTTP request` |
| 8 | **psutil** | container (já presente via base) | Métricas de processo expostas ao app | Healthcheck self-instrumentation |
| 9 | **prometheus-client** | container (pip) | Expor `/metrics` endpoint custom no app | Métricas internas: `outbox_pending_total`, `hook_called_total`, `hook_init_attempts_total` |
| 10 | **filelock** | container (pip, talvez já presente) | Lock files reentrantes para concorrência | Evitar race do hook em saves paralelos |

## A2 · Skills/estruturas Copilot a adicionar/atualizar

| # | Item | Localização | Status atual |
|---|---|---|---|
| 1 | **Skill `pyspy-debug`** | `~/.copilot/skills/pyspy-debug/SKILL.md` | a criar — keywords: "stuck", "hang", "not firing", "runtime state" |
| 2 | **Skill `ws-handshake`** | `~/.copilot/skills/ws-handshake/SKILL.md` | a criar — keywords: "websocket", "handshake failed", "InvalidMessage" |
| 3 | **graphify update no repo** | `c:\Users\Windows\Desktop\Roleta Cloud\graphify-out\` | regenerar grafo do código atual para queries durante correções |
| 4 | **Memory: `outbox_pipeline`** | MCP memory | adicionar entidade com observações desta sessão |

## A3 · Pacotes Debian a confirmar/instalar no host

```bash
apt-get update && apt-get install -y \
  sqlite3 jq strace gdb python3-dbg websocat
# opcional: bpftrace bcc-tools
```

## A4 · Pacotes pip a adicionar no container roleta-cloud

Adicionar a `requirements.txt`:
```
py-spy>=0.4.0
prometheus-client>=0.20.0
```

Rebuild Dockerfile inclui:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 jq strace \
 && rm -rf /var/lib/apt/lists/*
```

---

# Parte B · Sprint 1 · Plano de Instalação (a executar)

1. Host Debian: `apt install` da lista A3.
2. Atualizar `requirements.txt` + Dockerfile com lista A4.
3. Criar 2 skills Copilot (`pyspy-debug`, `ws-handshake`).
4. `graphify update .` no repo.
5. Smoke test: `py-spy dump --pid <PID-PYTHON-NO-CONTAINER>`.

---

# Parte C · Catálogo de Bugs (v1 — descoberta inicial)

> Bugs herdados de `pos_implantacao_24_05.md` + novos descobertos na inspeção 18:24 BRT.

## C1 · Bugs descobertos durante essa nova auditoria

### 🚨 BUG-GAP-1 · CRITICAL · Gap de 2h33 sem novas decisões no DB
- **Sintoma:** Última decisão `id=3698 @ 15:51:34 BRT`. Atual 18:24 BRT. Contagem por hora: 14h=51, 15h=73, **16h=0, 17h=0, 18h=0**.
- **Hipótese A:** Cliente extractor (browser/Tampermonkey) **não está conectando ao WS** desde 15:51. Logs do app mostram dezenas de `websockets.exceptions.InvalidMessage: did not receive a valid HTTP request` a cada ~30s. Isso é um **healthcheck TCP** batendo na porta 8765 (compose define `test: socket.connect`), MAS o cliente real provavelmente também não está conectando.
- **Hipótese B:** App esteve DOWN entre ~18:11-18:14 UTC (~15:11-15:14 BRT) durante restart errôneo causado pelo bug `mesas/` — **mas isso foi APÓS 15:51**, não causa o gap inicial.
- **Hipótese C:** Tampermonkey/extensão do navegador parou por motivo externo (login expirou no Pragmatic, captcha, sessão Stake.bet).
- **Próximo passo:** validar com usuário se cliente browser está enviando spins; se sim, capturar handshake com `websocat`.

### 🟡 BUG-WS-1 · HIGH · Healthcheck do compose poluindo logs com `InvalidMessage`
- **Sintoma:** A cada 30s o healthcheck faz `socket.connect((localhost, 8765))` puro, sem completar handshake WS, gerando stack trace de erro no log do app.
- **Impacto:** Logs poluídos; alertas falso-positivos no Loki; dificulta debug real.
- **Fix:** Mudar healthcheck para um endpoint HTTP /health ou um WS handshake completo via `websocat -1 -q ws://localhost:8765/health`.

### 🟢 BUG-SQLITE-1 · LOW · Container roleta-cloud sem `sqlite3` CLI
- **Sintoma:** `docker exec roleta-cloud sqlite3 ...` falha com `executable file not found`.
- **Impacto:** Diagnóstico mais lento (precisa via python).
- **Fix:** Adicionar ao Dockerfile.

## C2 · Bugs herdados de `pos_implantacao_24_05.md` (em aberto)

| ID | Severidade | Resumo |
|---|---|---|
| **HOOK-1** | 🚨 CRITICAL | `_get_publisher()` single-shot: 1 falha = perma-disabled |
| **CONFIGS-1** | MED | `server/configs/mesas/` untracked = qualquer `git clean` quebra startup |
| **LOG-1** | MED | Root logger=WARNING esconde `logger.info` do hook |
| **CDC-1** | LOW | CDC worker sem healthcheck/restart_policy |
| **GIT-1** | LOW | Stashes acumulados no servidor |

## C3 · Bugs resolvidos nesta sessão (referência)

| ID | Resumo | Resolução |
|---|---|---|
| B2-1/2/3/4 | WAL-G env e permissões | já resolvidos sessão anterior |
| DRIFT-1 | Servidor 2 commits atrás | git pull aplicado |
| APP-1 | Crash readonly-fs mesas | mkdir mitigação |
| DATA-1 | Row sintética 999999 | DELETE aplicado |

---

# Parte D · Auditoria (v2)

Análise dos bugs listados em C, priorização por impacto × esforço, e identificação de **dependências** entre fixes.

## D1 · Matriz Impacto × Esforço

| Bug | Impacto (1-5) | Esforço (1-5) | Score (I/E) | Prioridade |
|---|---|---|---|---|
| BUG-GAP-1 | 5 | 2 | 2.5 | 🔥 **P0** — bloqueia toda evolução |
| HOOK-1 | 5 | 1 | 5.0 | 🔥 **P0** — fix trivial, impacto máximo |
| CONFIGS-1 | 4 | 1 | 4.0 | 🔥 **P0** — risco de deploy |
| BUG-WS-1 | 3 | 1 | 3.0 | **P1** |
| LOG-1 | 3 | 1 | 3.0 | **P1** — desbloqueia debug futuro |
| CDC-1 | 3 | 2 | 1.5 | **P2** |
| BUG-SQLITE-1 | 1 | 1 | 1.0 | **P3** |
| GIT-1 | 1 | 1 | 1.0 | **P3** |

## D2 · Dependências

```
HOOK-1 ───→ requer LOG-1 para validar (saber se hook está sendo chamado)
            requer instrumentação (prometheus-client)
            requer BUG-GAP-1 resolvido (sem novas decisões, hook nunca dispara)

CONFIGS-1 ─→ independente, pode ir primeiro

BUG-GAP-1 ─→ requer ferramentas Sprint 1 (websocat, py-spy)
            possivelmente requer ação do usuário (verificar extensão browser)

CDC-1 ───→ independente
BUG-WS-1 ──→ healthcheck fix; não bloqueia mas reduz ruído
```

## D3 · Riscos identificados na auditoria

| Risco | Mitigação |
|---|---|
| Patch retry no `_get_publisher` pode ter race em multi-thread | Adicionar `threading.Lock()` |
| `mkdir mesas` no host não persiste em rebuild da VM | Mover `configs/mesas/.gitkeep` para git |
| `py-spy dump` em container precisa `--cap-add SYS_PTRACE` | Adicionar ao compose ou usar `docker exec --privileged` |
| Subir log para INFO pode estourar Loki quota | Subir só logger `database.*` ao INFO, manter root WARNING |
| Healthcheck WS mais complexo pode atrasar startup | Manter 30s interval, mas com `start_period: 60s` |

## D4 · Achados extras durante auditoria

- O log de erro `EOFError: connection closed while reading HTTP request line` é **causado pelo próprio healthcheck do compose** (definido no docker-compose.yml linha do healthcheck do roleta-cloud). Confirma BUG-WS-1.
- Total geral de decisões: **3698**. Histórico saudável (51-73 por hora).
- App veio sendo restartado várias vezes hoje (commits 4acdc19, 37c3ae0, audit) — cada restart com erro do mesas dir deixou o app DOWN por janelas pequenas.

---

# Parte E · Sprint Plan v3 FINAL (consolidado)

Esta é a versão **executável** consolidada. Cada sprint é atômico, testável, e tem rollback.

## E1 · Sprint VF-0 · Bootstrap de Tooling (15 min)

**Goal:** Instalar tooling necessário para todos os fixes subsequentes.

| Etapa | Comando | Validação |
|---|---|---|
| 0.1 | `ssh root@187.45.181.75 'apt-get update && apt-get install -y sqlite3 jq strace gdb websocat'` | `which sqlite3 jq strace gdb websocat` retorna paths |
| 0.2 | Adicionar `py-spy>=0.4.0`, `prometheus-client>=0.20.0` ao `requirements.txt` local | git diff mostra add |
| 0.3 | Editar `Dockerfile` para `RUN apt-get install -y sqlite3 jq` | imagem builda |
| 0.4 | Adicionar `cap_add: [SYS_PTRACE]` ao service `roleta-cloud` em docker-compose.yml | compose validate |
| 0.5 | `graphify update .` no repo local (Windows) | `graphify-out/graph.json` atualizado |

**Rollback:** apt list de pacotes / git checkout requirements.txt Dockerfile docker-compose.yml.

## E2 · Sprint VF-1 · Fix CONFIGS-1 (10 min — pré-requisito de segurança)

| Etapa | Ação |
|---|---|
| 1.1 | Criar `server/configs/mesas/.gitkeep` local |
| 1.2 | git add + commit |
| 1.3 | git push origin main |
| 1.4 | No servidor: `git pull` (mesas continua pois não foi deletado pelo pull desta vez) |

**Validação:** `ls server/configs/mesas/` mostra `.gitkeep`. Próximo deploy não quebra.

## E3 · Sprint VF-2 · Fix HOOK-1 (30 min — bug crítico)

**Patch em `database/outbox_integration.py`:**

```python
# Novos globals
_publisher_init_attempts = 0
_publisher_last_attempt_ts = 0.0
_publisher_lock = threading.Lock()
MAX_INIT_ATTEMPTS = 10
RETRY_BACKOFF_SEC = 60

def _get_publisher():
    """Retry-aware lazy singleton. Thread-safe."""
    global _publisher, _publisher_init_attempts, _publisher_last_attempt_ts
    if _publisher is not None:
        return _publisher
    with _publisher_lock:
        if _publisher is not None:  # double-check
            return _publisher
        if _publisher_init_attempts >= MAX_INIT_ATTEMPTS:
            return None
        now = time.time()
        if now - _publisher_last_attempt_ts < RETRY_BACKOFF_SEC:
            return None
        _publisher_last_attempt_ts = now
        _publisher_init_attempts += 1
        dsn = os.getenv("ROLETA_PG_DSN")
        if not dsn:
            logger.warning("ROLETA_PG_DSN not set; publisher disabled")
            return None
        try:
            from database.outbox_publisher import OutboxPublisher
            p = OutboxPublisher(dsn=dsn)
            _ = p._ensure_conn()
            _publisher = p
            logger.warning(f"OutboxPublisher initialized (attempt {_publisher_init_attempts})")
            return _publisher
        except Exception as e:
            logger.warning(f"OutboxPublisher init attempt {_publisher_init_attempts} failed: {e}")
            return None
```

**Validação:**
1. Unit test: simular falha + retry; assert `_publisher_init_attempts==2` após 60s.
2. Smoke prod: derrubar PG por 30s, app continua; sobe PG; próximo save publica em outbox em < 60s.

## E4 · Sprint VF-3 · Fix LOG-1 + instrumentação (20 min)

| Etapa | Ação |
|---|---|
| 3.1 | Em `main.py` ou config logging: `logging.getLogger("database").setLevel(logging.INFO)` |
| 3.2 | Em `database/outbox_integration.py` adicionar contadores Prometheus: `outbox_hook_called_total`, `outbox_hook_published_total`, `outbox_hook_init_attempts_total` |
| 3.3 | Expor `/metrics` HTTP via `prometheus_client.start_http_server(9100)` |
| 3.4 | Adicionar scrape no grafana-agent config |

## E5 · Sprint VF-4 · Fix BUG-WS-1 (15 min)

| Etapa | Ação |
|---|---|
| 4.1 | Adicionar endpoint HTTP `/health` no app (FastAPI minimal OU branch no websocket handler) |
| 4.2 | Trocar healthcheck do compose para `wget -q -O- http://localhost:8765/health` OU `websocat -1 -q ws://localhost:8765/health` |
| 4.3 | Set `start_period: 60s` no healthcheck |

## E6 · Sprint VF-5 · Fix CDC-1 (10 min)

| Etapa | Ação |
|---|---|
| 5.1 | Adicionar `healthcheck` ao service `roleta-cdc-worker` |
| 5.2 | Adicionar `restart: unless-stopped` |
| 5.3 | Adicionar `depends_on: roleta-pg: condition: service_healthy` |

## E7 · Sprint VF-6 · Investigar BUG-GAP-1 (30 min)

| Etapa | Ação |
|---|---|
| 6.1 | Confirmar com usuário se cliente browser está rodando (perguntar) |
| 6.2 | `websocat ws://localhost:8765` para testar handshake manual |
| 6.3 | `py-spy dump --pid $(pgrep -f main.py)` para confirmar threads vivas |
| 6.4 | Se OK: documentar como "cliente externo offline" não bug do servidor |
| 6.5 | Se ruim: investigar deeper |

## E8 · Sprint VF-7 · Cleanup + commits (15 min)

| Etapa | Ação |
|---|---|
| 7.1 | `git stash drop` todos os stashes acumulados no servidor |
| 7.2 | 1 commit por sprint, mensagens claras |
| 7.3 | Tag `v4.5.0-hardening` após validação |
| 7.4 | Atualizar `pos_implantacao_24_05.md` apêndice com resoluções |
| 7.5 | Memory checkpoint final |

## E9 · Ordem de execução recomendada

```
VF-0 (tooling) ──┬──► VF-1 (CONFIGS-1) ──► commit+push
                 ├──► VF-2 (HOOK-1) ──┬──► VF-3 (LOG/metrics)──┐
                 │                    │                        ├──► VF-7 (cleanup+tag)
                 ├──► VF-4 (WS health)│                        │
                 ├──► VF-5 (CDC HC)   │                        │
                 └──► VF-6 (gap diag)─┘────────────────────────┘
```

## E10 · Critérios de Done global

- [ ] `git status` clean no servidor + tag v4.5.0-hardening pushed
- [ ] App healthy 1h sem restart
- [ ] Próxima jogada real → outbox row criada em < 5s → spins_vectors row criada em < 10s
- [ ] `outbox_hook_called_total` métrica > 0 no Prometheus
- [ ] Healthcheck logs limpos (zero `InvalidMessage`)
- [ ] `pos_implantacao_24_05.md` apêndice atualizado
- [ ] Sprint backlog (S7, S9-S14) revalidado

---

# Parte F · Log de Execução

> Atualizado conforme cada sprint completa.

| Sprint | Início | Fim | Resultado | Commit |
|---|---|---|---|---|
| VF-0 | _pending_ | | | |
| VF-1 | _pending_ | | | |
| VF-2 | _pending_ | | | |
| VF-3 | _pending_ | | | |
| VF-4 | _pending_ | | | |
| VF-5 | _pending_ | | | |
| VF-6 | _pending_ | | | |
| VF-7 | _pending_ | | | |

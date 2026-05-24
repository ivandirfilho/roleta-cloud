# 🎰 Entendendo a Estrutura — Roleta Cloud + Servidor Debian
**Snapshot:** 2026-05-22 23:18 (UTC-3) · **Versão app:** v4.3.2 · **Commit:** `6bdde3c`
**Gerado por:** YOLO Orchestrator (Claude Opus 4.7) usando MCPs `graphify`, `filesystem`, `sequential-thinking` + 3 explore agents paralelos + SSH probe.

---

## 0. Sumário Executivo (TL;DR)

> A Roleta Cloud é uma **engine Python WebSocket** (porta 8765, Docker) que recebe *spins* de uma **extensão Chrome** injetada em casas de aposta, aplica a estratégia adaptativa **M15-ADA / SDA-17 v4.3.2** (17 números, 45,9% de cobertura, offset bayesiano com sigmoid anti-drift), persiste decisões em **SQLite** e expõe um **dashboard "Glass Box" em HTML/JS** servido por **nginx + Let's Encrypt** em `https://roleta.xma-ia.com`. Roda em um VPS Debian 12 (`xmaiajpvm`, `187.45.181.75`). Atualmente **OPERACIONAL** com 2 alertas (disco 97% cheio; serviço `systemd` legado em falha mas inofensivo — Docker assumiu).

| Métrica | Valor |
|---|---|
| Estado público | 🟢 **OPERACIONAL** (HTTPS 200, WebSocket healthy) |
| Estado interno | 🟡 **DEGRADED** (disco 97%, systemd FAILED) |
| Versão produção | **4.3.2** (sincronizada com `origin/main`) |
| Container | `roleta-cloud` UP 11 h healthy |
| Certificado SSL | Válido até **2026-07-06** (~44 dias) |
| Cobertura grafo | 787 nós · 895 arestas · 55 comunidades · 22 arquivos analisados |

---

## 1. Topologia & Fluxo End-to-End

```
┌──────────────────────────┐
│ Casa de aposta (browser) │
│  + extensão "Escuta Beat"│  ◀── Chrome MV3, content.js scrapa números
└────────────┬─────────────┘
             │  wss://roleta.xma-ia.com/ws  (mensagem: novo_resultado)
             ▼
┌──────────────────────────┐
│  nginx 1.22.1 (Debian)   │  ports 80/443  → redirect + reverse proxy /ws
│  Let's Encrypt SSL       │  cert: roleta.xma-ia.com (válido 44d)
└────────────┬─────────────┘
             │  proxy_pass http://127.0.0.1:8765 (upgrade websocket)
             ▼
┌──────────────────────────────────────────────────────────────┐
│  Container Docker  roleta-cloud  (python:3.12-slim)          │
│  ┌────────────┐                                              │
│  │  main.py   │ ─▶ asyncio.run(start_server())               │
│  └────────────┘                                              │
│         │                                                    │
│         ▼                                                    │
│  server/websocket.py ──▶ ConnectionManager  (MASTER/SLAVE)   │
│         │                                                    │
│         ▼                                                    │
│  server/message_handler.py (MessageHandler)                  │
│    │  dispatch por tipo: novo_resultado / apostar_sugestao   │
│    ├─▶ strategies/sda17.py  SDA17Strategy.analyze()          │
│    │     ├─ IQR outlier rejection                            │
│    │     ├─ weighted median (decay)                          │
│    │     ├─ M02-PctSigmoid anti-drift  (±2 pos/jogada max)   │
│    │     └─ retorna 17 números (C1+C2+C3) + score 0-6        │
│    ├─▶ state/bet_advisor.py  TripleRateAdvisor (Kill Switch) │
│    ├─▶ state/game.py  GameState + MartingaleState (Smart v6) │
│    └─▶ database/service.py  → SQLite /app/data/decisions.db  │
│         │                                                    │
│         ▼                                                    │
│  broadcast_heartbeat()  cada 1 s para todos os clientes      │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
              ┌──────────────────────────────┐
              │ frontend/ (Glass Box)        │  servido por nginx
              │ index.html + app.js + .css   │  em /var/www/roleta
              │  ws client reconnect 5 s     │
              └──────────────────────────────┘
```

**Latência alvo:** ~50–200 ms ponta a ponta (extensão → engine → overlay).

---

## 2. Mapa de Repositório (local + remoto)

```
C:\Users\Windows\Desktop\Roleta Cloud\
│
├── main.py                       Entry point: signals SIGINT/SIGTERM + asyncio
├── Dockerfile                    python:3.12-slim, healthcheck socket :8765
├── docker-compose.yml            volume roleta-data, restart=unless-stopped
├── requirements.txt              pydantic≥2, websockets≥12, structlog≥24
├── VERSION                       4.3.2
├── roleta.conf                   nginx (espelha /etc/nginx/sites-available/roleta)
├── state.json                    GameState persistente (timelines + martingales)
├── state.json.bak                backup do save anterior
│
├── core/                         primitivas puras (sem I/O)
│   ├── roulette.py               Direction enum, WHEEL_SEQUENCE (37), RouletteNumber
│   ├── engine.py                 GameEngine — entrega SpinDecision (15+ campos)
│   └── logging_config.py         structlog JSON + console colorido
│
├── server/                       I/O WebSocket
│   ├── websocket.py              start_server + broadcast_heartbeat
│   ├── message_handler.py        MessageHandler (dispatch / dedup / tracing)
│   ├── connection_manager.py     Master/Slave + grace period 10 s
│   ├── extractor_service.py      templates de providers (detecção de mesas)
│   └── analytics_handler.py      métricas em tempo real
│
├── strategies/
│   ├── base.py                   StrategyBase (ABC) + get_neighbors()
│   └── sda17.py                  ⭐ SDA17Strategy — M15-ADA v4.3 / M02-PctSigmoid
│                                 BAYESIAN_WINDOW=12, DEFAULT=10, WARMUP=2
│
├── database/
│   ├── service.py                DatabaseService (sessions / decisions / windows)
│   ├── models.py                 Decision dataclass + GaleWindow + Session
│   ├── repository.py             interface abstrata
│   └── sqlite_repo.py            implementação SQLite
│
├── auth/middleware.py            verify_auth() HMAC-SHA256 timing-safe + bypass
│
├── models/                       DTOs Pydantic
│   ├── input.py                  SpinInput (numero, direcao, trace_id, t_client)
│   ├── output.py                 SuggestionOutput / AckOutput / ErrorOutput
│   └── trace.py                  TraceContext + now_ms()
│
├── state/
│   ├── game.py                   GameState + MartingaleState (Smart Gale v6)
│   ├── bet_advisor.py            TripleRateAdvisor (Kill Switch v2)
│   └── timeline.py               Timeline = deque com maxlen
│
├── app_config/settings.py        ServerSettings/AuthSettings/GameSettings (Pydantic)
│
├── frontend/                     Glass Box dashboard (estático)
│   ├── index.html                272 linhas — cards: spin, result, timeline,
│   │                             SDA17 perf, Bet perf, Martingale, trace, logs
│   ├── app.js                    WebSocket client, reconnect, render
│   └── style.css                 tema escuro cyan/dourado
│
├── extension/                    Chrome MV3 "Escuta Beat" v3.0.0
│   ├── manifest.json             permissions: activeTab/tabs/scripting/storage/alarms
│   ├── content.js                injeta overlay; destaca [C1] em dourado
│   ├── background.js             service worker; chrome.alarms; log 100 entradas
│   ├── popup.html                UI 500 px (status, histórico, comandos)
│   ├── overlay.css               .eb-c1 destaque visual
│   └── icons/                    16, 48, 128 px
│
├── tests/                        pytest (8 suítes; 105/105 ✅ na última auditoria)
│   ├── conftest.py               adiciona raiz ao PYTHONPATH
│   ├── test_core.py              WHEEL_SEQUENCE + posições
│   ├── test_game_state.py        transições de fase
│   ├── test_sda17.py             estratégia + Triple Rate
│   ├── test_smartgale_v5.py      níveis e apostas Martingale
│   ├── test_message_handler_gale.py  WebSocket + Gale
│   ├── test_bet_advisor.py       centros/score/região
│   ├── test_db_query.py          consultas decisions.db
│   └── test_bug_fixes_28_03.py   regressão dos bugs pós-deploy 28/03
│
├── scripts/
│   ├── setup_server.sh           bootstrap Debian (chave SSH, ufw 8765)
│   └── sim_temp/                 simulações 10/15 modelos C2/C3
│
├── tools/backtest_from_db.py     replay de decisões reais
│
├── .github/workflows/
│   ├── ci.yml                    pytest matrix Python 3.12/3.13 (push/PR main+develop)
│   └── deploy.yml                trigger em tag v* → build Docker → SSH deploy
│
├── data/decisions.db             SQLite (origem; produção é volume Docker)
├── roleta.log                    log local (último: 2026-03-19)
├── archive/                      legado (RoletaV11, deploy.sh/ps1) — NÃO usar
│
└── 📚 ~25 .md de auditoria/validação (organizados por data 28/03 → 02/04 → 22/05)
    Documentos chave:
    • README.md ............. contexto para IAs (v3.5)
    • SECURITY.md ........... política de credenciais
    • Manutenabilidade_iso.md ISO/IEC 25010 (qualidade) v4.3.2
    • deployci_cd.md ........ pipeline GitHub Actions
    • analise_c1_c2_c3.md ... estudo de qual centro acerta mais
    • plano_implantação_c1_c2_c3_melhorado.md  migração SDA-21 → M15-ADA
    • resultados_*.md ....... séries diárias de jogadas reais
```

---

## 3. Componentes Centrais (Graph-derived God Nodes)

> Extraído via `graphify` — top-10 nós mais conectados:

| # | Nó | Edges | Significado |
|---|---|---|---|
| 1 | `BaseModel` | 21 | Raiz de todos os DTOs Pydantic |
| 2 | `SDA17Strategy` | 19 | ⭐ Estratégia central — calcula a aposta |
| 3 | `MessageHandler` | 15 | Roteador de mensagens WebSocket |
| 4 | `simulate_all()` | 14 | Backbone das simulações 10/15 modelos |
| 5 | `coverage_set()` | 11 | Calcula 17 números cobertos da roda |
| 6 | `cov_sym()` | 10 | Cobertura simétrica para validação |
| 7 | `main()` | — | Entry point → `start_server()` |
| 8 | `handle_shutdown()` | — | Persistência segura no encerramento |

**Comunidades estruturais notáveis:**
- C0 (45 nós) — Estado adaptativo: `MartingaleState`, persistência `state.json`, migrações.
- C7 (19 nós) — Núcleo runtime: `main`, `MessageHandler`, deduplicação.
- C8 (33 nós) — Algoritmos: `circ_dir`, `circ_dist`, `cov`, modelos M01–M15.
- C10 (17 nós) — Documentação M15-ADA v4.3 (M02-PctSigmoid, Triple Focus).
- C13 (20 nós) — Documentação completa do fluxo de dados.
- C18 (11 nós) — Conformidade ISO/IEC 25010 (8 dimensões).

Há **368 nós isolados** no grafo — em parte são docs extraídos como `code:block`, em parte oportunidades reais de documentação cruzada (linkar nomes de funções entre o código e os .md).

---

## 4. Modelo de Mensagens WebSocket

| Tipo (`type`) | Direção | Payload (resumo) | Handler |
|---|---|---|---|
| `historico_inicial` | client → server | últimos N spins ao conectar | `MessageHandler.process_message` |
| `novo_resultado` | client → server | `numero` (0-36), `direcao` (CW/CCW), `trace_id`, `t_client` | dispara `analyze()` → `SuggestionOutput` |
| `apostar_sugestao` | client → server | confirmação de aposta efetiva | atualiza `MartingaleState` |
| `state_sync` | server → client | snapshot completo (heartbeat 1 s) | `broadcast_heartbeat` |
| `role_assigned` | server → client | MASTER ou SLAVE | `ConnectionManager.connect` |
| `ack` / `error` | server → client | confirmação por `trace_id` | DTOs Pydantic |

---

## 5. Estratégia M15-ADA / SDA-17 v4.3.2 (essencial)

- **Cobertura:** 17 números = 7 (C1) + 5 (C2) + 5 (C3) = **45,9 %** da roda europeia.
- **Break-even:** 47,2 % (a estratégia opera com Kill Switch + Martingale para fechar gap).
- **Janela bayesiana:** 12 spins; warmup 2; default offset 10.
- **Pipeline:** janela adaptativa → **IQR** outlier rejection → **weighted median** com decay → **drift detection** → **M02-PctSigmoid** (atualização sigmoid, saturação ±2/jogada).
- **Estado por direção:** CW e CCW têm históricos, offsets e Martingales **independentes**.
- **Kill Switch v2 (`TripleRateAdvisor`)**: só veta a aposta quando **C4 = 0 % E SDA ≤ 2** (catástrofe dupla) — caso contrário sempre permite.
- **Smart Gale v6:** níveis 1-3; `get_gale(score, c4_rate, confidence)` decide subir nível; `update(hit, global_hit)` detecta streaks.

---

## 6. Infraestrutura Servidor — Debian 12 (xmaiajpvm)

| Item | Valor |
|---|---|
| IP | `187.45.181.75` (resolve `roleta.xma-ia.com` e `www.…`) |
| Acesso SSH | `root@187.45.181.75` (chave RSA `windows@IVANDIR`, sem passphrase local) |
| Kernel | Linux 6.1.55-1 Debian 6.1.0-13-amd64 |
| Uptime | ~11 h (último boot 2026-05-22 15:19 UTC) |
| RAM | 3,3 GiB total · 1,1 GiB usado · 2,2 GiB disp · swap 8 GiB livre |
| Disco | `/dev/vda1` 4,8 GiB → **4,4 GiB usado · 158 MiB livre · 97 %** ⚠️ |
| Diretório app | `/root/roleta-cloud` (não `/opt/...` como `deploy.yml` indica) |

### Serviços
| Serviço | Status | Observação |
|---|---|---|
| `nginx.service` | ✅ active (run 11 h) | escuta `0.0.0.0:80` e `0.0.0.0:443`, sites-enabled `roleta` |
| `docker.service` | ✅ active (run 11 h) | 2 containers up |
| `roleta-cloud.service` (systemd) | ❌ **FAILED** há 10 h | `ModuleNotFoundError: structlog` — tenta rodar Python na host (sem venv). **Inócuo** porque o Docker assumiu — apenas ruído de monitoramento. |
| `fail2ban` | ⛔ ausente | risco de brute-force SSH |
| `cron` | ⛔ sem jobs | nenhum housekeeping automático |

### Containers Docker
```
CONTAINER       IMAGE                        PORTS                      STATUS
roleta-cloud    roleta-cloud-roleta-cloud    127.0.0.1:8765→8765/tcp    Up 11h (healthy)
xmaia-portal    oznu/guacamole               0.0.0.0:8080→8080/tcp      Up 11h
```
Volumes: `roleta-cloud_roleta-data` (~6,4 MiB) montado em `/app/data` → `decisions.db` (1,9 MiB) + 3 backups (`_`, `deploy402`, `pre_reset`).

### Nginx (`/etc/nginx/sites-enabled/roleta` → `sites-available/roleta`)
- `:80` redireciona 301 para HTTPS.
- `:443` SSL Let's Encrypt (`/etc/letsencrypt/live/roleta.xma-ia.com/{fullchain,privkey}.pem`, válido até **2026-07-06**).
- `location /` serve `/var/www/roleta` (HTML/JS/CSS do dashboard).
- `location /ws` proxy para `127.0.0.1:8765` com `Upgrade: websocket` e `proxy_read_timeout 86400` (24 h).

### Testes ao vivo (verificados nesta sessão)
```
GET https://roleta.xma-ia.com          → 200  (Server: nginx/1.22.1)
GET https://www.roleta.xma-ia.com      → 200  (Server: nginx/1.22.1)
HTTP /ws → upgrade 101 Switching Protocols (frames role_assigned + state_sync)
```
> ⚠️ O explore agent inicial reportou HTTPS *down* — foi falso positivo (curl sem `-k` ou DNS local). Probe direto **confirma site UP**.

### Erros no `/var/log/nginx/error.log`
Apenas SSL handshake errors externos (`bad key share` de scanners com TLS antigo, IPs 87.236.176.130 / 66.132.186.185) — **não afetam clientes legítimos**.

### Segurança SSH (sshd_config consolidado)
```
Port 22 · PermitRootLogin yes · PasswordAuthentication yes
```
> ⚠️ Senha+root habilitados — risco de brute-force; sem fail2ban.

### Firewall
iptables com política ACCEPT (permissiva); regras Docker para 8765 e 8080; WireGuard UDP 51820 aberto.

---

## 7. CI/CD

| Workflow | Trigger | Ação |
|---|---|---|
| `ci.yml` | push em `main`/`develop`, PR para `main` | matrix Py 3.12 + 3.13 → `pytest tests/ -v` + `py_compile` |
| `deploy.yml` | tag `v*` ou `workflow_dispatch` | build imagem Docker → SSH `appleboy/ssh-action` → backup `decisions.db` → `git checkout <tag>` → `docker compose down/build/up` → health check + teste socket 8765 |

> ⚠️ `deploy.yml` faz `cd /opt/roleta-cloud`, mas o servidor real tem o repo em `/root/roleta-cloud`. **Mismatch potencial — ou o secret `SERVER_USER` faz `cd /opt/...` resolver (symlink?), ou deploys nunca passaram pela rota declarada e usam apenas o caminho legado `archive/deploy.sh`**. A confirmar antes da próxima release.

---

## 8. Decisões de Design & Padrões Observados

- **Strategy + Template Method** em `strategies/`.
- **Repository Pattern** em `database/` (interface + SQLite impl).
- **State Machine** distribuída: `MartingaleState` × 2 (CW/CCW) + `ConnectionManager` (MASTER/SLAVE/grace).
- **Observer/Pub-Sub** via `broadcast_heartbeat` (1 Hz).
- **DTOs Pydantic** para serialização e validação na borda.
- **Dataclass persistence** para `GameState` em `state.json` (versionado: `"version": "1.6.0"`).
- **Defensive coding**: flag global anti-double-shutdown; fallback try/except no `save()`; `BUG-MAIN-001..005` corrigidos.

---

## 9. Dívida Técnica e Pontos de Extensão

| Local | Severidade | Achado |
|---|---|---|
| `server/message_handler.py` | M | dispatch por `if/elif` → refatorar para tabela `{type: handler}` |
| `strategies/sda17.py` (~600 l.) | M | sigmas/thresholds **hardcoded** → expor em `app_config` |
| `state/game.py` | M | serialização JSON manual; substituir por `dataclasses.asdict` |
| `database/service.py` | M | sem `BEGIN/ROLLBACK` explícitos; falhas parciais possíveis |
| `core/engine.py` (`SpinDecision`) | B | dataclass com 15+ campos → considerar sub-DTOs por contexto |
| `server/connection_manager.py` | B | 4 casos aninhados → state machine declarativa |
| `.github/workflows/deploy.yml` | A | path `/opt/roleta-cloud` ≠ real `/root/roleta-cloud` |
| systemd `roleta-cloud.service` | M | legado falhando — disable ou converter para wrapper docker compose |
| Raiz do repo | B | ~25 `.md` poluem raiz; mover para `docs/auditorias/` |
| Documentação | B | 368 nós isolados no graphify — linkar nomes de função aos `.md` |

---

## 10. Riscos Operacionais Ativos (priorizados)

| # | Risco | Severidade | Mitigação imediata |
|---|---|---|---|
| 1 | **Disco / = 97 %** (158 MiB livres) | 🔴 CRÍTICO | `docker system prune -a --volumes` (~2,4 GiB recuperáveis) + rotação de `roleta.log`/backups antigos `decisions_backup_*.db` |
| 2 | `systemd roleta-cloud.service` FAILED | 🟠 ALTO (alerta) | `systemctl disable roleta-cloud.service` (Docker é a fonte da verdade) |
| 3 | SSH com `PermitRootLogin yes` + `PasswordAuthentication yes`, **sem fail2ban** | 🟠 ALTO | endurecer `sshd_config` (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`), instalar `fail2ban` |
| 4 | Certificado SSL expira em ~44 dias | 🟡 MÉDIO | confirmar `certbot renew --dry-run`; instalar timer systemd se ausente |
| 5 | Sem cron de housekeeping | 🟡 MÉDIO | `/etc/cron.daily/roleta-cleanup` (logs >7 d + `docker system prune -f`) |
| 6 | `deploy.yml` aponta `/opt/roleta-cloud` ≠ real | 🟡 MÉDIO | corrigir path ou criar symlink `ln -s /root/roleta-cloud /opt/roleta-cloud` |
| 7 | Sem testes end-to-end no CI (apenas unitários) | 🟢 BAIXO | adicionar smoke test pós-deploy via WebSocket |

---

## 11. Inventário de Segredos & Credenciais

| Segredo | Onde vive | Status |
|---|---|---|
| `firebase-credentials.json` | só no servidor + máquina do dev | ✅ ignorado por `.gitignore` |
| `config.py` | só no servidor | ✅ ignorado por `.gitignore` |
| `ROLETA_API_KEY` | env var no servidor (auth desabilitada por default) | ✅ |
| Chave SSH `windows@IVANDIR` | `~/.ssh/id_rsa` local + `authorized_keys` no servidor | ✅ |
| `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`, `SERVER_PORT` | GitHub Secrets (deploy.yml) | ✅ |
| Certificados Let's Encrypt | `/etc/letsencrypt/live/roleta.xma-ia.com/` | ✅ |

Nenhum segredo está no repositório (`SECURITY.md` documenta a política).

---

## 12. Insumos para o Planejamento de Evolução

### Quick wins (≤ 1 dia, sem risco)
1. **Liberar disco** — `docker system prune -a --volumes` + apagar `decisions_backup_pre_reset.db` (1,1 MiB) e `decisions_backup_deploy402.db` (1,6 MiB).
2. **Apaziguar systemd** — `systemctl disable --now roleta-cloud.service` (Docker assume).
3. **Cron de housekeeping** — `/etc/cron.daily/roleta-cleanup` com `find /root/roleta-cloud -name "*.log" -mtime +7 -delete && docker system prune -f`.
4. **Corrigir path do deploy** — atualizar `deploy.yml` para `/root/roleta-cloud` **ou** `ln -s /root/roleta-cloud /opt/roleta-cloud`.
5. **Arquivar .md históricos** — mover ~22 arquivos para `docs/auditorias/<YYYY-MM>/`; raiz passa a ter só `README`, `SECURITY`, `Manutenabilidade_iso`, este arquivo.

### Médio prazo (1–2 semanas)
6. **Endurecimento SSH** — chave-only + porta não-padrão + `fail2ban`.
7. **Observabilidade** — exportar métricas (Prometheus `/metrics`) e logs JSON para Loki/Grafana; alarme via `disk_used > 85 %`.
8. **Testes E2E** — workflow extra `e2e.yml` que sobe o container num runner e roda um cliente WebSocket fake (10 spins, valida resposta).
9. **Documentação cruzada** — preencher os 368 nós isolados do graphify (linkar funções aos .md).
10. **Refatorar `message_handler`** para tabela de dispatch + introduzir transações em `database/service.py`.

### Longo prazo (estratégia)
11. **Migração SQLite → SurrealDB ou Postgres** (já comentado em `requirements.txt`) para multi-instância.
12. **Similarity search com LanceDB** (já reservado em comments) quando volume > 5 k decisões.
13. **Multi-mesa** — `ConnectionManager` evoluir de Master/Slave 1-N para múltiplos jogos paralelos (uma instância por mesa).
14. **Autenticação real** — terminar pipeline Keycloak (settings já preparados em `AuthSettings`).
15. **CI hardening** — adicionar `bandit`, `pip-audit`, `mypy --strict` em workflow separado.

---

## 13. Comandos Operacionais de Bolso

```bash
# Status produção
ssh root@187.45.181.75 "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# Logs ao vivo
ssh root@187.45.181.75 "docker logs -f --tail 50 roleta-cloud"

# Backup banco
ssh root@187.45.181.75 "docker exec roleta-cloud sqlite3 /app/data/decisions.db .dump > /root/dump_$(date +%F).sql"

# Renovar certificado (dry run)
ssh root@187.45.181.75 "certbot renew --dry-run"

# Liberar disco
ssh root@187.45.181.75 "docker system prune -a --volumes -f"

# Restart limpo
ssh root@187.45.181.75 "cd /root/roleta-cloud && docker compose down && docker compose up -d"

# Atualizar grafo Graphify (local)
graphify update "C:\Users\Windows\Desktop\Roleta Cloud"
graphify query "como o MessageHandler aciona a SDA17?" --graph "C:\Users\Windows\Desktop\Roleta Cloud\graphify-out\graph.json"
```

---

## 14. Glossário Rápido

| Termo | Significado |
|---|---|
| **SDA-17** / **M15-ADA** | Estratégia atual: 17 números cobertos (45,9 %), offset adaptativo bayesiano |
| **C1 / C2 / C3** | Centros previstos para as 3 sub-regiões da roda (7+5+5) |
| **Triple Rate** | C4 (4 últimos), M6 (6), L12 (12) — Kill Switch |
| **CW / CCW** | Clockwise / Counter-Clockwise — sentidos da roda |
| **Smart Gale v6** | Martingale adaptativo (níveis 1-3) com detecção de streak global |
| **Glass Box** | Dashboard transparente do estado interno em tempo real |
| **MASTER/SLAVE** | Roles do `ConnectionManager` — apenas MASTER injeta novos spins |
| **Kill Switch** | Veta aposta apenas quando `C4=0 % AND SDA≤2` (catástrofe dupla) |

---

## 15. Como Atualizar Este Documento

```powershell
# 1. Atualizar grafo
cd "C:\Users\Windows\Desktop\Roleta Cloud"
graphify update .

# 2. Re-rodar este reconhecimento (no agente Copilot CLI)
#    /agent yolo-orchestrator
#    "atualize o Entendendo_estrutura_em_22.md com o estado atual"
```

---

**Snapshot fechado em:** 2026-05-22 23:18 (UTC-3)
**Branch/commit:** `main @ 6bdde3c`
**MCPs usados:** graphify · filesystem · sequential-thinking (implícito) · 3 explore subagents paralelos · SSH direto
**Próximo passo recomendado:** após você revisar, podemos iniciar o **planejamento de evolução** priorizando os Quick Wins da Seção 12.

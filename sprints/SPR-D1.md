# SPR-D1 · Diagnóstico 502 do /ws (Glass Box OFFLINE × HostDime online) + self-heal · Bloco BLK-K · Pri P0

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Incidente reportado pelo operador em 16/08: Glass Box não recebe "servidor online";
> painel HostDime mostra a VM online. Diretor já coletou evidência externa (abaixo).

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []
locks:      [deploy, health_server]     # scripts de deploy + nginx conf + runbook (+ server/ SÓ se a causa for código)
touches:    [scripts/roleta-deploy-pull.sh, roleta.conf, docs/runbooks/, docker-compose.yml (só comentário/healthcheck se preciso)]
base_sha:   origin/main
branch:     o branch da PRÓPRIA sessão (spr/SPR-D1 contém este brief; abra o PR do branch
            da sessão com título `SPR-D1:`)
```

## Objetivo (1 frase)
Determinar por que `wss://roleta.xma-ia.com/ws` responde **502** (upstream morto) com a VM
"online", entregar por PR o máximo de correção/observabilidade possível **sem ssh**, e
deixar runbook para o que só o dono pode executar no host.

## Evidência externa já coletada (Diretor, 16/08 ~03:46Z — NÃO refaça do zero, ATUALIZE)
```text
DNS roleta.xma-ia.com → A 187.45.181.75
GET  https://roleta.xma-ia.com/          → 200 (nginx 1.22.1 vivo, serve o Glass Box estático)
GET  https://roleta.xma-ia.com/health    → 404 (nginx NÃO tem location /health — gap de observabilidade)
GET  https://roleta.xma-ia.com/metrics   → 404 (idem)
WS   https://roleta.xma-ia.com/ws        → **502 Bad Gateway** (upstream 127.0.0.1:8765 não responde)
Portas 8765/8766 fechadas externamente (correto: compose binda em 127.0.0.1)
CI de main VERDE (runs 31921300746, 31920629817); sem issue main-red aberta
Últimos merges: #68/#69 docs-only (15-16/08); último código: 06-07/08 (#43 MIG-0, #58 R2, #64, #66, #67)
```

## Fatos do repo que orientam as hipóteses (âncoras)
- `roleta.conf` (versionado) só tem `location /` e `/ws` → **/health do container (8766) é
  invisível de fora**; impossível distinguir "app todo morto" de "WS morto / health vivo".
- `scripts/roleta-deploy-pull.sh`:
  - Tick **NOOP** (`LOCAL == REMOTE`, linha ~105): sai `exit 0` **sem healthcheck e sem
    `docker compose up -d`** → container morto fica morto para sempre entre merges.
  - Deploy real: build → **gate MIG-0** `assert_state_volume_ready` (exige `state.json` no
    volume) → alembic → `up -d` → healthcheck 3× → senão `rollback()` (que TAMBÉM faz
    `up -d` do last_good). Ou seja: se o timer rodou nos merges #68/#69, ALGUMA versão
    deveria estar de pé. 502 persistente ⇒ suspeita de **timer/entrypoint congelado,
    docker/disco quebrado, ou WS morto com health vivo** (healthcheck só olha 8766!).
  - Entrypoint real é **/usr/local/bin/roleta-deploy-pull.sh (fora do repo, não se
    auto-atualiza)** — ver comentário "Drift do entrypoint (OBS-INODE)" no próprio script.
    Mudanças suas neste script SÓ valem em produção após reinstalação (runbook!).
- `docker-compose.yml`: healthcheck do container = `curl http://localhost:8766/health`
  (não cobre o listener WS 8765); `restart: unless-stopped`.
- Suspeito de código (se for o caso): `server/websocket.py` / `server/main` — task do WS
  pode morrer com health server vivo (procure `except` engolindo exceção no serve-loop;
  cruze com `tools/lint_silent_except.py` e mudanças dos merges #43/#58 — ex.: dependência
  de PG/réplica que não sobe e mata o loop).

## Hipóteses ranqueadas (confirme/refute na ordem)
1. **H1 — WS morto, health vivo:** healthcheck 8766 passa, listener 8765 morreu (exceção na
   task asyncio pós #43/#58, ex. PG replica indisponível). Timer "vê" app saudável e não age.
2. **H2 — timer/entrypoint morto ou congelado pré-MIG-0:** nenhum deploy roda de fato;
   container caiu em algum momento e o NOOP-gap nunca o ressuscita.
3. **H3 — docker/disco quebrado no host:** build/up falham sempre; rollback também falha.
4. **H4 — gate MIG-0 (`state.json` ausente)** derruba todo deploy novo E o last_good não
   sobe por outro motivo.

## Tarefa (passos)
1. **Reproduzir o boot localmente** (é a única forma de testar H1 sem ssh):
   `docker compose build && docker compose up -d` (ou, sem Docker local: venv +
   `pip install -r requirements.txt` + `python main.py`) → `curl :8766/health` +
   handshake WS em `:8765` (script python `websockets` de 10 linhas) → derrube dependências
   opcionais (PG off) e veja se o WS sobrevive. Documente o comportamento no Log.
2. **Auditar o código do serve-loop** (`server/websocket.py`, `main.py`, mudanças #43/#58):
   exceção não tratada mata só o WS? Se SIM e houver fix cirúrgico (supervisão/retry/log),
   implementar + teste em `tests/` (fix de crash não é comportamento de estratégia — sem
   flag; mas qualquer retry/loop novo deve logar e não mascarar).
3. **Fechar o gap de observabilidade (entrega principal, independe da causa):**
   a. `roleta.conf`: adicionar `location /health` (e opcional `/metrics` com allowlist ou
      auth básica — decida e justifique) → proxy para 127.0.0.1:8766. Lembre: o arquivo é
      fonte versionada; a instalação no host é manual → runbook.
   b. `scripts/roleta-deploy-pull.sh`: no tick NOOP, **self-heal idempotente**: healthcheck
      local; se falhar → `docker compose up -d "$SERVICE"` + log `SELF-HEAL`; gateável por
      env (`SELF_HEAL="${SELF_HEAL:-1}"` — default ON é aceitável aqui por ser corretivo e
      idempotente; justifique no adendo). Healthcheck do self-heal deve cobrir **8766 E um
      TCP-connect no 8765** (senão H1 passa batido de novo).
4. **Runbook** `docs/runbooks/servidor-502-glassbox.md`: árvore de decisão (sondas externas
   → o que cada resultado significa), comandos que o DONO roda no host (journalctl do
   timer, `docker ps`, `docker logs roleta-cloud`, df -h, reinstalar entrypoint via
   `scripts/roleta-deploy-install.sh`, `nginx -t && reload` após instalar o conf novo) —
   um comando por linha, copy-paste.
5. **Fix-forward pelo próprio merge:** o merge deste PR dispara o deploy (~2 min). Após o
   merge: re-sondar `/ws` (e `/health` quando o conf estiver instalado). Registrar no Log:
   - `/ws` voltou 101 ⇒ causa era container caído + NOOP-gap (H2 leve) — encerrar.
   - continua 502 ⇒ timer/entrypoint/host (H2/H3 pesado) ⇒ abrir issue `ops: servidor
     requer intervenção do dono` com o runbook linkado e as evidências, e avisar o Diretor.
6. Se mexeu em `server/`: suíte + `tools/lint_silent_except.py --update` se novo except.

## Critério de "pronto" (Definition of Done)
- [ ] Diagnóstico com hipótese confirmada/refutada e evidência colada no Log (H1–H4).
- [ ] Reprodução local do boot documentada (WS + health testados).
- [ ] `roleta.conf` com `/health` + runbook de instalação; self-heal no tick NOOP com
      cobertura 8765+8766; runbook 502 completo.
- [ ] Se causa = código: fix + teste regressivo em `tests/`.
- [ ] `pytest tests/` verde (Windows: `--ignore=tests/test_obs_reload.py`).
- [ ] Pós-merge: sondagem externa re-executada e resultado no Log (ou issue ops aberta).

## Guardrails (inviolável)
- **PROIBIDO ssh/scp/systemctl no host de produção** — diagnóstico externo (curl/DNS/portas)
  + reprodução local + leitura de código APENAS. O que exigir host → runbook para o dono.
- **INV-3** intacto (não tocar estratégia/stake). Migração: NÃO mexer em alembic aqui.
- Mudanças no deploy script: defensivas, idempotentes, não-fatais quando acessório.
- **Git:** só no branch da sessão; PR; NUNCA push/checkout/reset em `main`. Sem segredos.
- NÃO commitar `graphify-out/`.

## Validação (rode e cole o resultado no Log)
```
pytest tests/ --ignore=tests/test_obs_reload.py
bash -n scripts/roleta-deploy-pull.sh          # sintaxe
# sondas externas antes/depois do merge:
curl -sS -o /dev/null -w "%{http_code}\n" https://roleta.xma-ia.com/health
curl -sSi -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" https://roleta.xma-ia.com/ws | head -3
```

## Rollback (ISO — sempre documentar)
`git revert` do PR (self-heal e nginx conf são aditivos; revert limpa) · self-heal
desligável via `SELF_HEAL=0` no environment da unit (documentar no runbook).

## Conformidade ISO (marque ANTES de abrir o PR)
- [ ] Aditivo/retro-compatível; sem remover chaves/flags.
- [ ] Novo `except Exception` → `python tools/lint_silent_except.py --update`.
- [ ] ADENDO ISO: arquivo NOVO `docs/iso/adendos/2026-08-16-diagnostico-502-self-heal.md`
      (NÃO apendar em `Manutenabilidade_iso.md`).
- [ ] Espelho Azure: mexeu em flag da compose? (não previsto) → se sim, sincronizar
      `deploy/azure/compose.azure.yml` no MESMO PR.

## Closeout (a ORDEM importa)
1. Validação → Log. 2. ADENDO (arquivo novo). 3. Code-review (subagent) → corrigir.
4. Append no Log. 5. Commit no branch da sessão (`SPR-D1: <resumo>` + trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`).
6. **Lock check pré-PR:** `gh pr list` — colisão em scripts/roleta.conf ⇒ serialize.
7. Push + PR `SPR-D1: ...` + auto-merge (`gh pr merge --auto --squash <nº>`).
8. Pós-merge: passo 5 da Tarefa (re-sondar) e avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->

### 2026-08-16 · EXECUTADO (aguardando merge) · diagnóstico sem ssh + /health + self-heal

**Re-sondagem inicial** (independente da do Diretor, mesmo resultado ⇒ incidente
persistente, não transitório):

| Sonda | Resultado |
|---|---|
| `GET /` | **200** (nginx/1.22.1 vivo, TLS ok) |
| `GET /health` | **404** (location inexistente no conf do host) |
| `GET /metrics` | **404** (idem) |
| `GET /ws` (Upgrade) | **502** upstream `127.0.0.1:8765` |

**H1 (serve-loop travado / deadlock no WS) — REFUTADA**, por dois caminhos
independentes:
1. *Estrutural:* `main.py:28` importa `server/websocket.py`, cujo top-level roda
   `GameState.load()`; `start_health_server()` só é chamada **depois**, dentro de
   `main()`. As portas 8765 e 8766 vivem e morrem juntas — não existe estado
   "WS morto, health vivo". Além disso, um serve-loop *travado* (socket aceitando,
   sem resposta) devolveria **504**, não 502. 502 = `connect()` recusado = processo
   fora do ar.
2. *Empírica:* 4 boots locais. Com PG derrubado e `SDA_PG_FEATURE_CONTEXT=1`, o WS
   **sobreviveu** e entregou heartbeat — o modo de falha imaginado por H1 não se
   reproduz. Com `STATE_FILE` inexistente, `FileNotFoundError` no import derruba
   **as duas** portas (assinatura idêntica à observada).

**H2 (NOOP-gap: deploy sai `exit 0` sem olhar o app) e H4 (`state.json` ausente →
crash-loop)** permanecem como causas prováveis, e são exatamente o que esta
entrega ataca (H2 diretamente; H4 fica diagnosticável pelo runbook).

**Entrega:**
- `roleta.conf`: `location = /health` e `= /metrics` → `127.0.0.1:8766`
  (`/metrics` com `allow 127.0.0.1; deny all`). Valida a distinção
  "nginx sem conf" × "app morto" de fora, sem ssh.
- `scripts/roleta-deploy-pull.sh`: self-heal idempotente no tick NOOP — sonda
  `/health` (8766) **e handshake WS** (8765, exige `101`); fora do ar ⇒
  `docker compose up -d` + revalidação; não curou ⇒ **`exit ≠ 0`** (unit `failed`,
  sem sucesso falso). Kill switch `SELF_HEAL=0`.
- Freios anti-pausa: sentinela `self_heal_paused` (`pause_app.sh` cria — fatal se
  falhar; `resume_app.sh` remove **só após** `healthy`) + stand-down por código de
  saída deliberado (`0`, `143`, `137` sem OOM). `137` **com** `OOMKilled` cura.
- `docs/runbooks/servidor-502-glassbox.md`: árvore de decisão das 4 sondas,
  comandos do dono no host, caso `state.json` ausente, pré-requisito do entrypoint.

**Validação:** suíte completa **1235 passed, 14 skipped, 1 xfailed**;
`tests/test_spr_d1_self_heal.py` **12 cenários** executando `self_heal_tick()` real
com stubs; `nginx -t` do `roleta.conf` em container ⇒ *"syntax is ok / test is
successful"*; `bash -n` nos 3 scripts; lint `lint_silent_except` OK.

**Code-review (subagent) → 5 achados corrigidos**, 1 crítico:
1. **[CRÍTICO]** o harness extraía o bloco "do marcador até `cd $REPO_DIR`"; com
   drift, ia até o EOF e `source`aria `git reset --hard origin/main` no checkout do
   CI (simulado: 229 linhas capturadas). ⇒ sentinelas `# >>> SPR-D1 SELF-HEAL
   BEGIN/END` + guard negativo (`exit 91`), verificado com marcador quebrado.
2. sonda WS era TCP-connect e dava **falso-OK** (o `docker-proxy` faz `accept()`
   antes de discar o backend — reproduzido em laboratório) ⇒ handshake real.
3. `pause_app.sh` seguia para o `docker stop` mesmo falhando ao criar a sentinela
   ⇒ fatal.
4. stand-down `exited:0` não cobria 143/137 ⇒ `deliberate_stop()` com `OOMKilled`;
   `docker stop --time 60` alinhado ao `stop_grace_period`.
5. `resume_app.sh` removia a sentinela antes do `up -d` (~90s de corrida com o
   tick) ⇒ remoção só depois do gate `healthy`.

**Limite conhecido (declarado no ADENDO §5 e no runbook §7):** o systemd executa
`/usr/local/bin/roleta-deploy-pull.sh` e o nginx lê `/etc/nginx/.../roleta.conf` —
**ambos fora do repo**. Se forem cópias congeladas, este PR não cura o incidente
até alguém rodar `scripts/roleta-deploy-install.sh` + `cp` do conf. O merge é
usado como fix-forward e o resultado da re-sondagem entra abaixo.

**Arquivos:** `roleta.conf`, `scripts/roleta-deploy-pull.sh`, `scripts/pause_app.sh`,
`scripts/resume_app.sh`, `docs/runbooks/servidor-502-glassbox.md` (novo),
`docs/runbooks/pause-policy.md`, `docs/iso/adendos/2026-08-16-diagnostico-502-self-heal.md`
(novo), `docs/iso/adendos/README.md`, `tests/test_spr_d1_self_heal.py` (novo).
Nenhuma flag do `docker-compose.yml` tocada ⇒ **sem espelho Azure**.
Lock check: só o PR #65 aberto (docs-only) ⇒ **sem colisão**.

### 2026-08-16 · PÓS-MERGE (fix-forward) · NÃO curou — ação do dono pendente

Merge do PR **#74** em `main` às **04:54:52Z**. Re-sondagem em **04:58:51Z**
(header `Date` do servidor; ≥ 2 ticks do timer de 120s):

| Sonda | Antes | Depois |
|---|---|---|
| `GET /` | 200 | **200** |
| `GET /health` | 404 | **404** |
| `GET /metrics` | 404 | **404** |
| `GET /ws` | 502 | **502** |

**Sem mudança — e a causa é a antecipada no ADENDO §5 / runbook §7.** Os dois
artefatos corrigidos vivem **fora do repo** e nenhum deploy os instala sozinho:
1. `/etc/nginx/sites-available/roleta.conf` — o deploy faz `nginx -t` + `reload`,
   mas **não copia** o conf. `/health` em 404 é evidência direta disto.
2. `/usr/local/bin/roleta-deploy-pull.sh` — o versionado chama
   `roleta-deploy-install.sh --check`, que **detecta** o drift mas não instala. Se
   o entrypoint for cópia congelada, o self-heal entregue **não está rodando**.

Como ambos se instalam pela mesma via, o mais provável é que (2) também esteja
pendente. Abri a issue **#76** (`ops:`) com os comandos exatos (~2 min) e o
critério de verificação externa (`/health` → 200, `/ws` → 101).

**Leitura honesta do sprint:** os objetivos de *diagnóstico* foram cumpridos (H1
refutada por código e por reprodução; 502 virou assinatura inequívoca de "processo
fora do ar") e os de *prevenção* estão em `main` (self-heal + `/health` + runbook +
12 cenários de teste). O objetivo de *cura imediata* **não** foi atingido, porque
a última milha do deploy ainda é manual — limite estrutural do sistema, não do
sprint. Recomendação ao Diretor: sprint próprio para o `roleta-deploy-pull.sh`
instalar o `roleta.conf` (com `nginx -t` + rollback) e se auto-atualizar; enquanto
existir artefato de produção fora do git, "mergeou" ≠ "implantado".

**Também nesta entrega:** o PR #73 foi aberto com base herdada da sessão
(`spr/SPR-D1`) e mergeou nesse branch; o conteúdo foi levado a `main` pelo PR #74,
cujo conflito `add/add` em `sprints/SPR-D1.md` foi resolvido preservando os dois
lados (a versão do branch era superconjunto estrito: +75/-0). CI verde
(`ci-ok`, `lint-and-test 3.12`, `extension-tests`, `iso-guardrails`).

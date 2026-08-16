# ADENDO ISO — 16/08/2026 · Diagnóstico do 502 e self-heal do tick NOOP

**Origem:** `SPR-D1` (sprint de diagnóstico aberto pelo Diretor durante o incidente
de 16/08/2026 — Glass Box sem "servidor online" com a VM ligada).
**Documento-mãe:** `Manutenabilidade_iso.md` (histórico; não recebe append).

## 1. O incidente e o que ele revelou

Sondas externas às 03:46Z e 04:07Z (sem ssh, por contrato):

| Sonda | Código | Leitura |
|---|---|---|
| `GET /` | 200 | nginx vivo, Glass Box servido |
| `GET /health` | **404** | **a location não existia no `roleta.conf`** |
| `GET /metrics` | 404 | idem |
| Upgrade `/ws` | **502** | ninguém escutando em `127.0.0.1:8765` |

O achado mais caro não foi o 502 — foi o **404**. Com a única sonda externa sendo
o próprio `/ws`, era impossível distinguir de fora "app morto" de "app vivo com
nginx mal configurado". O incidente ficou indiagnosticável sem acesso ao host, o
que colide com o modelo operacional do repo (agente não faz ssh; estado de
produção se lê por endpoint).

## 2. Diagnóstico: H1 refutada, H2/H4 prováveis

**H1 ("o WS morreu mas o health continua vivo") é estruturalmente impossível.**
Cadeia verificada no código: `main.py:28` importa `server/websocket.py`, cujo
top-level executa `GameState.load()` (linha 28); `start_health_server()` só é
chamado dentro de `main()`, **depois**, e sobe uma *thread daemon*. Logo o 8766
nasce após o 8765 e morre junto com o processo. Não existe estado "8765 morto +
8766 vivo".

Reprodução local (4 boots, fora do host):

1. `STATE_FILE` apontando para arquivo inexistente → `FileNotFoundError` **no
   import** (guard MIG-0, `state/game.py:1588-1592`), antes do health server:
   **as duas portas mortas**.
2. estado válido → 8765 e 8766 UP, `/health` → `200 {"status":"ok",...}`.
3. Postgres derrubado com `SDA_PG_FEATURE_CONTEXT=1` → **WS sobrevive**,
   handshake OK, heartbeat recebido. H1 refutada também empiricamente.

Corolário operacional que passa a valer como regra de leitura:
**`/ws` em 502 ⇒ o processo não está de pé.** Se o processo estivesse vivo mas
travado, o kernel aceitaria o TCP e o nginx devolveria **504**, não 502.

Restam **H2** (o tick NOOP nunca ressuscita nada) e **H4** (`state.json` ausente
no volume ⇒ crash-loop no import + `assert_state_volume_ready` barrando todo
deploy novo). H2 explica a *persistência* independentemente de qual foi o gatilho:
qualquer que tenha sido a morte, nada no sistema tentava desfazê-la.

## 3. O que mudou

### 3.1 `roleta.conf` — a sonda que faltava
`location = /health` (proxy → `127.0.0.1:8766`, `access_log off`, timeouts 3s/5s)
e `location = /metrics` (mesmo upstream, `allow 127.0.0.1; allow ::1; deny all`).
De fora passa a ser possível separar os casos: **200** = app de pé · **502** = app
morto · **404** = conf antigo instalado. O **403** do `/metrics` vira a prova
barata de que o conf novo está instalado, sem expor métrica de negócio (stake,
banca, hits).

### 3.2 `scripts/roleta-deploy-pull.sh` — nada a implantar ≠ nada a fazer
O gate NOOP (`HEAD == origin/main`) saía `exit 0` **sem olhar para o app**: um
container caído ficava caído até o próximo merge — janela silenciosa de horas ou
dias. Agora, a cada tick: sonda `HEALTH_URL` (8766) **e** faz um **handshake
WebSocket completo** no **8765** (bash puro sobre `/dev/tcp`, exigindo
`101 Switching Protocols`, sem dependências novas); se algo está fora do ar,
`docker compose up -d`, revalida as duas portas, loga `SELF-HEAL ok` /
`SELF-HEAL INEFICAZ`, e **sai ≠ 0** quando não curou — o systemd marca a unit como
`failed` em vez de reportar sucesso com o Glass Box offline. Saudável ⇒ silencioso,
`exit 0`.

Cobrir **as duas** portas é deliberado: a sonda de 8766 sozinha repetiria o ponto
cego original — o healthcheck do compose já observa só o 8766, e é justamente o
8765 que o cliente usa.

**Handshake, não TCP-connect.** A primeira versão da sonda apenas abria o socket.
Com o userland proxy do Docker (o modo padrão do bind `127.0.0.1:8765:8765`), quem
escuta é o `docker-proxy`, que **aceita a conexão antes** de discar para o
container: um connect puro devolve "ok" mesmo com a aplicação morta. Reproduzimos
o falso-positivo em laboratório (socket que só faz `accept()`: TCP-connect passa,
handshake falha) — a sonda seria decorativa e o self-heal nunca dispararia pelo
8765.

### 3.3 Freios anti-pausa (`pause_app.sh` / `resume_app.sh`)
`pause_app.sh` faz `docker stop` **deliberado**. Sem freio, o self-heal
ressuscitaria o app em ~2 min e destruiria a janela de manutenção. Dois freios
independentes:

1. **Sentinela** `/var/lib/roleta-deploy/self_heal_paused` — criada no pause
   (**fatal** se não conseguir criar: melhor abortar a pausa do que pausar sem
   proteção) e removida no resume **somente depois** de o app voltar `healthy`
   (removê-la antes abriria ~90 s de corrida com o tick).
2. **Código de saída do container** — stand-down em `Exited (0)`, `Exited (143)`
   (SIGTERM do `docker stop`) e `Exited (137)` **sem** `OOMKilled`
   (SIGKILL após o grace period). `Exited (137)` **com** `OOMKilled=true` é outage
   real e **é** curado. `pause_app.sh` passou a usar `--time 60`, alinhado ao
   `stop_grace_period: 60s` do compose — antes, `--time 30` matava o processo no
   meio do shutdown e produzia 137.

Isto espelha a semântica do `restart: unless-stopped`, que também não ressuscita
quem foi parado de propósito.

### 3.4 Runbook e teste
`docs/runbooks/servidor-502-glassbox.md`: árvore de decisão das quatro sondas
externas, comandos copy-paste do dono no host, o caso `state.json` ausente, e o
pré-requisito do entrypoint (§5). `tests/test_spr_d1_self_heal.py` executa
`self_heal_tick()` de verdade com sondas e `docker` stubados — **12 cenários**,
incluindo os três stand-downs por sinal, o OOM que **deve** curar, a sentinela e
as duas saídas `≠ 0`.

O harness extrai o bloco de self-heal do script real delimitado por sentinelas
explícitas (`# >>> SPR-D1 SELF-HEAL BEGIN/END`) e **recusa-se a rodar** se a
extração vier vazia (`exit 90`) ou capturar comandos do fluxo de deploy
(`exit 91`). Sem esse guard, um drift nos marcadores faria o teste `source`ar o
`git reset --hard origin/main` dentro do checkout do runner de CI.

## 4. Flags e defaults

| Flag | Default | Onde |
|---|---|---|
| `SELF_HEAL` | **1 (ligado)** | `scripts/roleta-deploy-pull.sh` / `Environment=` da unit |
| `SELF_HEAL_PAUSED_FILE` | `$STATE_DIR/self_heal_paused` | idem |
| `WS_PROBE_HOST` / `WS_PROBE_PORT` / `WS_PROBE_TIMEOUT` | `127.0.0.1` / `8765` / `3` | idem |

**Por que este nasce LIGADO, contra a regra "flag default-OFF".** A regra existe
para mudança de comportamento do produto: comportamento novo precisa de janela
shadow antes de afetar aposta. Aqui não há comportamento novo nem efeito em
estratégia/stake — é ação **corretiva e idempotente** (`up -d` em container de pé
é no-op) num caminho que hoje não faz nada. Nascer OFF significaria entregar o
sprint de um incidente ativo com a correção desligada, dependendo de um segundo PR
para valer — exatamente a "ação humana pendente" que o contrato proíbe. Kill
switch imediato via `SELF_HEAL=0`. Nenhuma flag do `docker-compose.yml` foi tocada,
logo não há espelho Azure a sincronizar.

## 5. Limite conhecido (honesto)

O systemd executa `/usr/local/bin/roleta-deploy-pull.sh`, **fora do repo**. Se
esse arquivo ainda for a cópia congelada, o self-heal deste PR **não roda em
produção** até alguém executar `scripts/roleta-deploy-install.sh` uma vez no host
(o launcher elimina o congelamento futuro). O `roleta.conf` tem a mesma natureza:
é fonte versionada instalada manualmente, exige `cp` + `nginx -t` + `systemctl
reload nginx`. Ambos os passos estão no runbook, §3 e §7. Este PR, sozinho,
**não** garante a cura do incidente de 16/08 — garante que o próximo seja
diagnosticável de fora e que a classe inteira (app caído entre merges) passe a se
curar sozinha.

## 6. Como reverter

- **Cirúrgico, sem deploy:** `SELF_HEAL=0` no `Environment=` da unit +
  `systemctl daemon-reload`. O tick volta ao `exit 0` silencioso.
- **Total:** `git revert` do PR do SPR-D1. Nada de schema, nada de flag de
  produto, nenhuma migração — o revert é limpo (~4 min até o deploy).
- **Só o nginx:** restaurar o backup `/root/roleta.conf.bak.<TS>` +
  `nginx -t && systemctl reload nginx`.

## 7. Lições ISO 25010 / 14764

- **Observabilidade é pré-requisito de manutenibilidade, não enfeite** (25010 ·
  *Analisabilidade*). O custo do incidente não foi o app cair — foi não haver
  sonda que separasse as hipóteses. Regra que fica: **todo processo com porta
  exposta ao usuário precisa de um endpoint de vivacidade acessível pelo mesmo
  caminho pelo qual ele é consumido.**
- **Caminho "sem novidade" é caminho não testado** (14764 · *manutenção
  corretiva*). O tick NOOP rodava a cada 2 min há meses e nunca fora exercitado
  contra um app fora do ar. Onde houver um ramo "nada a fazer", perguntar: *e se
  o mundo estiver quebrado enquanto nada muda?*
- **Automação corretiva precisa de stand-down explícito.** Um self-heal sem freio
  vira antagonista do operador. Sentinela + leitura do exit code deliberado são o
  mínimo — a mesma distinção que o Docker já faz em `unless-stopped`.
- **Hipótese descartada é entrega.** Refutar H1 por código *e* por reprodução
  eliminou a busca por "travamento do serve-loop" e transformou 502 numa
  assinatura inequívoca ("processo fora do ar"), que agora está no runbook.
- **Sonda que não pode falhar não é sonda** (25010 · *Analisabilidade*). O
  TCP-connect no 8765 passaria sempre, porque quem aceita é o `docker-proxy`, não a
  aplicação. Regra que fica: **a sonda tem que exercitar o mesmo protocolo que o
  cliente fala** — e ser validada contra um alvo deliberadamente quebrado antes de
  ser considerada pronta.
- **Teste que `source`a código de produção precisa de cerca dos dois lados**
  (14764 · *manutenção preventiva*). Extrair "do marcador A até o marcador B" falha
  em silêncio quando um marcador drifta: o teste passa a executar o que vier
  depois — aqui, `git reset --hard origin/main` no checkout do CI. Sentinelas
  explícitas + guard negativo (abortar se a captura contiver comandos que não
  deveriam estar ali) transformam o drift em falha de teste, não em dano.
- **Revisão adversarial encontra o que a suíte verde esconde.** Os cinco achados
  desta entrega (um crítico) apareceram com a suíte já verde e o harness já
  passando: eram falhas de *premissa*, não de asserção. Mudança em automação de
  infraestrutura deve passar por uma leitura que pergunte "e se a premissa estiver
  errada?", não só por testes que confirmam o desenho.

# Runbook — Glass Box OFFLINE / `/ws` respondendo 502

> **Quando usar:** o operador diz que o Glass Box "não recebe servidor online", o
> painel do provedor (HostDime) mostra a VM ligada, e `https://roleta.xma-ia.com/`
> abre normalmente.
> **Origem:** incidente de 16/08/2026 (SPR-D1). Diagnóstico completo em
> `sprints/SPR-D1.md` e `docs/iso/adendos/2026-08-16-diagnostico-502-self-heal.md`.

## 0. O modelo mental em 5 linhas

| Peça | Onde roda | Quem serve |
|---|---|---|
| Glass Box (HTML/JS) | nginx do **host**, `/var/www/roleta` | `location /` |
| WebSocket | container `roleta-cloud`, **8765** | `location /ws` → `127.0.0.1:8765` |
| `/health` + `/metrics` | **mesmo processo**, thread daemon, **8766** | `location = /health` (SPR-D1) |

**Fato que orienta tudo:** 8765 e 8766 vivem e morrem **juntos** — são o mesmo
processo Python. O health server é uma *thread daemon* iniciada **depois** do
import de `server/websocket.py`; qualquer exceção antes disso derruba o processo
inteiro e as duas portas somem. Portanto **não existe** o cenário "WS morto com
health vivo" (hipótese H1, refutada empiricamente no SPR-D1).

Consequência prática: `/ws` em 502 **⇒ o processo não está de pé** (nginx só
devolve 502 quando ninguém aceita a conexão no upstream; se o processo estivesse
vivo mas travado, a resposta seria **504**).

## 1. Sondas externas (qualquer máquina, sem ssh)

Rode as quatro, em ordem, e anote os códigos:

```bash
curl -sS -o /dev/null -w "raiz    %{http_code}\n" https://roleta.xma-ia.com/
curl -sS -o /dev/null -w "health  %{http_code}\n" https://roleta.xma-ia.com/health
curl -sS -o /dev/null -w "metrics %{http_code}\n" https://roleta.xma-ia.com/metrics
curl -sSi -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" https://roleta.xma-ia.com/ws | head -3
```

## 2. Árvore de decisão

| raiz | /health | /ws | Leitura | Ação |
|---|---|---|---|---|
| — | — | `101` | **Tudo certo.** | Se o Glass Box ainda diz offline, o problema é do **cliente** (extensão/cache/URL) — §6. |
| `200` | `404` | `502` | nginx vivo, mas **o `roleta.conf` novo ainda não está instalado** no host. | Desde o SPR-D2 isso se resolve sozinho no próximo tick; se persistir, §3. |
| `200` | `502` | `502` | **App morto ou em crash-loop.** nginx de pé, container não. | §4 (o dono no host). |
| `200` | `200` | `502` | App vivo servindo health, mas ninguém no 8765. Não deveria acontecer (§0). | §4 + colete `docker logs`; é achado novo, registre. |
| `502`/`000` | `502`/`000` | `502`/`000` | nginx caiu ou a VM/rede está fora. | §5. |
| `200` | `200` | `504` | Processo vivo mas **travado** (event loop bloqueado). | §4, passo "py-spy". |

> `/metrics` devolvendo **403** é o esperado de fora (allowlist só local) e é a
> prova barata de que o `roleta.conf` do SPR-D1 **está** instalado. **404** =
> conf antigo.

## 3. `roleta.conf` desatualizado — hoje é automático (SPR-D2)

O `roleta.conf` do repo é a **fonte versionada** e, desde 16/08 (SPR-D2), **o deploy o instala
sozinho** a cada tick em que houver diferença: pré-valida o candidato em um prefixo nginx isolado,
faz `mv` atômico, roda `nginx -t` global e, se reprovar, **restaura o backup** automaticamente.

Ou seja: `/health` devolvendo `404` deixou de ser uma tarefa de host — é `git` + esperar o tick.

Diagnóstico (sem ssh não dá para ver o arquivo; com ssh, um comando):

```bash
grep 'NGINX CONF' /var/log/roleta-deploy.log | tail -5
cmp -s /root/roleta-cloud/roleta.conf /etc/nginx/sites-enabled/roleta.conf && echo "em dia" || echo "divergente"
ls -t /var/lib/roleta-deploy/nginx/ | head        # backups: roleta.conf.bak + .bak.<TS>
```

| Log | Leitura | Ação |
|---|---|---|
| `NGINX CONF ok` | instalado e recarregado | nenhuma |
| `NGINX CONF ABORTADO` | o candidato **reprovou** a pré-validação; **destino intacto** | o `roleta.conf` do repo está quebrado → corrigir por PR |
| `NGINX CONF ROLLBACK ok` | `nginx -t` global reprovou; backup restaurado | o conf conflita com o `http{}` real → corrigir por PR |
| `NGINX CONF ROLLBACK INSTAVEL` | rollback também não validou | **único caso que pede host**: restaure à mão de `/var/lib/roleta-deploy/nginx/roleta.conf.bak` e rode `nginx -t && systemctl reload nginx` |
| `NGINX CONF destino nao encontrado` | nenhum candidato existe no host | primeira instalação: crie o arquivo/symlink uma vez (abaixo) ou aponte `NGINX_CONF_DST` |
| `NGINX CONF MULTIPLOS DESTINOS` | há dois `roleta.conf` **reais** distintos (ex.: um em `conf.d/`, outro em `sites-available/` sem relação) — o deploy se recusa a adivinhar qual é o servido | apague o obsoleto **ou** fixe `NGINX_CONF_DST` no `Environment=` |
| `NGINX CONF DESTINO INATIVO` | o arquivo foi instalado e validado, mas **não aparece no `nginx -T`**: o vhost servido é outro | `ln -sf` do `sites-available` para `sites-enabled` (bloco abaixo) ou corrija `NGINX_CONF_DST` |
| `NGINX CONF RELOAD PENDENTE` | um tick anterior trocou o arquivo mas não confirmou o reload (reboot, SIGKILL ou reload falho); este tick está recarregando | nenhuma — é a auto-correção funcionando; se repetir todo tick, veja `systemctl status nginx` |
| `NGINX RELOAD FALHOU` | conf válido, mas o `systemctl reload nginx` falhou | `systemctl status nginx`; o tick seguinte tenta de novo sozinho (a marca de pendência garante isso) |

**Primeira instalação / host fora do padrão** (o deploy atualiza o conteúdo, mas não cria o
symlink de `sites-enabled` na primeira vez):

```bash
cd /root/roleta-cloud
cp roleta.conf /etc/nginx/sites-available/roleta.conf
ln -sf /etc/nginx/sites-available/roleta.conf /etc/nginx/sites-enabled/roleta.conf
nginx -t && systemctl reload nginx
curl -sS -o /dev/null -w "health %{http_code}\n" https://roleta.xma-ia.com/health
```

Kill switches (em `systemctl edit roleta-deploy.service`, `[Service] / Environment=…`):
`NGINX_CONF_SYNC=0` (desliga o passo), `NGINX_CONF_PREVALIDATE=0` (pula só o gate isolado —
use se o vhost passar a depender do `http{}` real e a pré-validação virar falso-negativo),
`NGINX_CONF_DST=/caminho/exato.conf`.

## 4. App morto — diagnóstico no host (dono)

Um comando por linha, de cima para baixo. Pare no primeiro que explicar o caso.

```bash
docker ps -a --filter name=roleta-cloud --format "{{.Names}} {{.Status}} {{.State}}"
docker inspect roleta-cloud --format '{{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} health={{.State.Health.Status}}'
docker logs roleta-cloud --tail 80
journalctl -u roleta-deploy.service --since "2 hours ago" --no-pager | tail -60
systemctl list-timers roleta-deploy.timer --no-pager
df -h /
docker system df
free -m
```

Como ler o resultado:

- **`Exited (1)` + traceback `FileNotFoundError: STATE_FILE configurado, mas o
  estado persistente nao existe`** → o `state.json` sumiu do volume. É o caso mais
  provável de crash-loop *permanente*: o guard MIG-0 é intencional (fail-closed
  para não zerar a sessão do operador em silêncio) e **nem o self-heal nem o
  rollback conseguem curar** — o deploy inteiro fica barrado por
  `assert_state_volume_ready` ("STATE MIGRATION REQUIRED" no log). Correção:
  ```bash
  docker volume inspect roleta-cloud_roleta-data --format '{{.Mountpoint}}'
  ls -la "$(docker volume inspect roleta-cloud_roleta-data --format '{{.Mountpoint}}')"
  bash /root/roleta-cloud/scripts/migrate-state-to-volume.sh
  ```
- **`Exited (137)`** → OOM. Confira `mem_limit: 512m` no compose e `free -m`.
- **`Restarting`** → crash-loop: a causa está em `docker logs --tail 80`.
- **`Exited (0)`, `Exited (143)` ou `Exited (137)` sem OOM** → parada
  **deliberada** (`scripts/pause_app.sh` ou `docker stop` manual: 143 = SIGTERM,
  137 = SIGKILL depois do grace period). O self-heal **não** ressuscita estes
  casos, por desenho. `Exited (137)` **com** `OOMKilled=true` é outage de verdade
  e **é** curado. Retome com:
  ```bash
  bash /root/roleta-cloud/scripts/resume_app.sh
  ```
- **Container não existe** → `docker compose up -d roleta-cloud` em
  `/root/roleta-cloud` resolve; o self-heal do tick NOOP faria isso sozinho (§7).
- **Nenhum `DEPLOY START` no journal apesar de merges recentes** → o timer não
  está rodando ou o entrypoint congelou (§7).
- **Disco cheio (`df -h /` ≥ 95%)** → build e `up` falham em cascata:
  ```bash
  docker system prune -af --volumes=false
  journalctl --vacuum-time=7d
  ```
- **Vivo mas travado** (health 200, `/ws` 504):
  ```bash
  docker exec roleta-cloud py-spy dump --pid 1
  ```

Subida manual (último recurso, só depois de entender a causa):

```bash
cd /root/roleta-cloud
docker compose up -d roleta-cloud
sleep 20
curl -fsS http://127.0.0.1:8766/health && echo OK-8766
timeout 3 bash -c "exec 3<>/dev/tcp/127.0.0.1/8765" && echo OK-8765
```

## 5. nginx/VM fora

```bash
systemctl status nginx --no-pager
nginx -t
systemctl restart nginx
ss -ltnp | grep -E ':(80|443|8765|8766)'
```

Se nem o SSH responder, é infraestrutura: painel HostDime → reboot da VM. Depois
do boot, refaça §1 — o self-heal (§7) sobe o app no primeiro tick do timer.

## 6. Servidor de pé e Glass Box ainda offline

O 502 já não é a causa. Verifique no cliente:

```bash
curl -sSi -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" https://roleta.xma-ia.com/ws | head -3
```

`101 Switching Protocols` = servidor OK ⇒ investigue a extensão (URL `wss://`
configurada, versão instalada, console do navegador, master/slave em
`docs/runbooks/sem-apostas-master-slave.md`).

## 7. Self-heal do tick NOOP (SPR-D1) — o que passou a ser automático

Antes: com `HEAD == origin/main`, o deploy saía `exit 0` **sem olhar para o app**.
Container caído ficava caído até o próximo merge. Agora, todo tick:

1. sonda `http://127.0.0.1:8766/health` **e** faz um **handshake WebSocket** no
   `8765` (exige `101 Switching Protocols`);
2. tudo de pé → sai 0, em silêncio (sem ruído no log);
3. algo fora do ar → `docker compose up -d roleta-cloud`, revalida as duas portas
   e loga `SELF-HEAL ok` ou `SELF-HEAL INEFICAZ`;
4. não curou → sai **≠ 0**, e a unit aparece como `failed` (nada de "sucesso" com
   o Glass Box offline).

> Por que handshake e não um simples TCP-connect: com o userland proxy do Docker,
> quem escuta em `127.0.0.1:8765` é o `docker-proxy`, que **aceita a conexão antes**
> de discar para o container. Um connect puro retornaria "ok" mesmo com a aplicação
> morta lá dentro — a sonda nunca falharia sozinha.

**Não age** quando: `SELF_HEAL=0`; existe `/var/lib/roleta-deploy/self_heal_paused`
(criado por `pause_app.sh`, removido por `resume_app.sh` **só depois** de o app
ficar `healthy`); ou o container saiu por sinal de parada — `Exited (0)`, `(143)`,
ou `(137)` sem `OOMKilled`.

Acompanhar / desligar:

```bash
grep SELF-HEAL /var/log/roleta-deploy.log | tail -20
systemctl edit roleta-deploy.service     # [Service] / Environment=SELF_HEAL=0
systemctl daemon-reload
```

> **PRÉ-REQUISITO — sem isto o self-heal nunca roda.** O systemd executa
> `/usr/local/bin/roleta-deploy-pull.sh`, que fica **fora do repo**. Se ainda for
> a cópia congelada, nenhuma melhoria versionada (esta inclusive) chega em
> produção. Verifique e corrija:
> ```bash
> /root/roleta-cloud/scripts/roleta-deploy-install.sh --check
> /root/roleta-cloud/scripts/roleta-deploy-install.sh install-shim
> systemctl start roleta-deploy.service
> journalctl -u roleta-deploy.service -n 40 --no-pager
> ```
> Saída `1` no `--check` = congelado. Reverter: `roleta-deploy-install.sh --rollback`.

## 7b. Shim de deploy (SPR-D2) — por que não há mais "mergeou ≠ implantado"

O `--check` do §7 e o self-heal do §7 vivem no script **versionado**. Enquanto o entrypoint fosse
uma cópia congelada — ou um launcher que só executasse o **checkout** —, um deploy quebrado podia
impedir o próprio `git fetch/reset` e o revert no GitHub nunca chegava ao host.

O **shim** (`scripts/roleta-deploy-shim.sh`, instalado por `install-shim`) inverte a ordem:

```
fetch origin main → git show origin/main:scripts/roleta-deploy-pull.sh → gate `bash -n` → exec
```

Consequências operacionais:

- **`git revert` cura o deploy em ≤2 min**, sem ssh. É a rota padrão para qualquer regressão de deploy.
- O shim **não** mexe na working tree (usa `git show`): o gate de NOOP do deploy continua comparando
  `HEAD` com `origin/main` de verdade.
- Script inválido em `main` ⇒ `SHIM ... rejeitado pelo gate` + `exit 1`; o host fica intacto (unit
  `failed`, visível no journal).
- Rede/GitHub fora ⇒ `SHIM FETCH FAIL` e ele executa a cópia local — sem janela sem deploy.
- Auditoria do que rodou de fato:
  ```bash
  grep SHIM /var/log/roleta-deploy.log | tail -20
  diff /var/lib/roleta-deploy/deploy-from-main.sh /root/roleta-cloud/scripts/roleta-deploy-pull.sh
  ```

## 8. Encerramento

- Registre no `## Log` do sprint correspondente: sondas antes/depois, causa e ação.
- Causa de código → sprint com teste regressivo em `tests/`.
- Só o host resolvia → abra issue `ops:` com o link deste runbook e as evidências.

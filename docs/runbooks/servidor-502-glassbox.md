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
| `200` | `404` | `502` | nginx vivo, mas **o `roleta.conf` novo ainda não está instalado** no host. | Instale o conf (§3) e repita as sondas — só então o `/health` distingue os casos. |
| `200` | `502` | `502` | **App morto ou em crash-loop.** nginx de pé, container não. | §4 (o dono no host). |
| `200` | `200` | `502` | App vivo servindo health, mas ninguém no 8765. Não deveria acontecer (§0). | §4 + colete `docker logs`; é achado novo, registre. |
| `502`/`000` | `502`/`000` | `502`/`000` | nginx caiu ou a VM/rede está fora. | §5. |
| `200` | `200` | `504` | Processo vivo mas **travado** (event loop bloqueado). | §4, passo "py-spy". |

> `/metrics` devolvendo **403** é o esperado de fora (allowlist só local) e é a
> prova barata de que o `roleta.conf` do SPR-D1 **está** instalado. **404** =
> conf antigo.

## 3. Instalar o `roleta.conf` novo (host, uma vez)

O `roleta.conf` do repo é **fonte versionada**; o nginx do host lê a cópia em
`/etc/nginx/sites-available/`. O deploy automático **não** copia este arquivo.

```bash
cd /root/roleta-cloud
git pull --ff-only origin main
cp /etc/nginx/sites-available/roleta.conf /root/roleta.conf.bak.$(date -u +%Y%m%dT%H%M%SZ)
cp roleta.conf /etc/nginx/sites-available/roleta.conf
nginx -t
systemctl reload nginx
curl -sS -o /dev/null -w "health %{http_code}\n" https://roleta.xma-ia.com/health
```

Reverter: `cp /root/roleta.conf.bak.<TS> /etc/nginx/sites-available/roleta.conf && nginx -t && systemctl reload nginx`

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
> /root/roleta-cloud/scripts/roleta-deploy-install.sh
> systemctl start roleta-deploy.service
> journalctl -u roleta-deploy.service -n 40 --no-pager
> ```
> Saída `1` no `--check` = congelado. Reverter: `roleta-deploy-install.sh --rollback`.

## 8. Encerramento

- Registre no `## Log` do sprint correspondente: sondas antes/depois, causa e ação.
- Causa de código → sprint com teste regressivo em `tests/`.
- Só o host resolvia → abra issue `ops:` com o link deste runbook e as evidências.

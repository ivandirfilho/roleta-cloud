# Deploy Roleta Cloud

## Pipeline atual (SP-03)

```
dev push main
    ↓
GitHub Actions CI (lint+test+schema+silent-except)
    ↓ verde
[ servidor Debian 187.45.181.75 ]
roleta-deploy.timer (systemd, 2min)
    ↓
/usr/local/bin/roleta-deploy-pull.sh   (launcher -> scripts/roleta-deploy-pull.sh do repo)
    ↓ git fetch + compara hashes
    ↓ se diff: reset --hard + build + up -d roleta-cloud
    ↓ healthcheck 3× @ http://127.0.0.1:8766/health
    ↓ sync frontend/ → /var/www/roleta + reload nginx   (NOVO 17/06)
    ↓ obs-apply.sh: valida/aplica/verifica Prometheus   (NOVO 05/08, só se obs mudou)
    ↓ falha → rollback automatico para HEAD anterior
PROD running
```

**Tempo medio push → prod: ~3-4min** (CI 1min + janela timer 2min).

## Componentes

| Arquivo | Local | Descricao |
|---|---|---|
| `scripts/roleta-deploy-pull.sh` | repo | **script canonico** de deploy (idempotente, com alembic, rollback e passo de observabilidade) |
| `scripts/roleta-deploy-launcher.sh` | repo | **entrypoint durável**: stub estavel instalado no host que so faz `exec` do script versionado |
| `scripts/obs-apply.sh` | repo | passo de observabilidade (detecta/valida/aplica/verifica Prometheus) |
| `tools/deploy_pull.sh` | repo | duplicado legado — hoje so delega para o canonico |
| `/var/lib/roleta-deploy/obs_pending` | servidor | pendência de observabilidade (`action`/`escalated`/`sha`, retomada no tick seguinte) |
| `tools/systemd/roleta-deploy.service` | repo | unit oneshot |
| `tools/systemd/roleta-deploy.timer` | repo | dispara a cada 2min |
| `/usr/local/bin/roleta-deploy-pull.sh` | servidor | **launcher** (ponteiro para o script do repo) |
| `/etc/systemd/system/roleta-deploy.{service,timer}` | servidor | units instaladas |
| `/var/log/roleta-deploy.log` | servidor | log de execucoes |
| `/var/lib/roleta-deploy/last_good` | servidor | SHA para rollback |

## Instalacao no servidor

> O que se instala em `/usr/local/bin` é o **launcher**, não uma cópia do deploy. Ele não tem
> lógica nenhuma: resolve `$REPO_DIR/scripts/roleta-deploy-pull.sh` e faz `exec`. A partir daí
> toda mudança no deploy chega por `git`, como qualquer outro código — sem reinstalar nada.

```bash
ssh root@187.45.181.75 << 'EOF'
cd /root/roleta-cloud
install -m755 scripts/roleta-deploy-launcher.sh /usr/local/bin/roleta-deploy-pull.sh
install -m644 tools/systemd/roleta-deploy.service /etc/systemd/system/
install -m644 tools/systemd/roleta-deploy.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now roleta-deploy.timer
systemctl list-timers roleta-deploy.timer
EOF
```

O caminho e o nome do arquivo instalado **não mudam**, então a unit systemd
(`ExecStart=/usr/local/bin/roleta-deploy-pull.sh`) continua igual.

**Sair do esquema de launcher** (rollback do próprio entrypoint):

```bash
install -m755 /root/roleta-cloud/scripts/roleta-deploy-pull.sh /usr/local/bin/roleta-deploy-pull.sh
```

## Operacao

```bash
# ver proxima execucao
ssh root@... systemctl list-timers roleta-deploy.timer

# rodar agora (forca pull manual)
ssh root@... systemctl start roleta-deploy.service

# log recente
ssh root@... tail -50 /var/log/roleta-deploy.log

# pausar deploy automatico (manutencao)
ssh root@... systemctl stop roleta-deploy.timer

# rollback manual
ssh root@... 'cd /root/roleta-cloud && git reset --hard $(cat /var/lib/roleta-deploy/last_good) && docker compose up -d --build roleta-cloud'
```

## Rollback automatico

Se `curl http://127.0.0.1:8766/health` falhar 3× consecutivas apos
`docker compose up -d`, o script reverte para o SHA salvo em
`/var/lib/roleta-deploy/last_good` e religa o container. O log fica em
`/var/log/roleta-deploy.log` com a tag `DEPLOY FAIL — rollback`.

## Frontend (nginx do host) — IMPORTANTE

O container **não** serve os estáticos do dashboard. O `frontend/`
(`index.html`, `app.js`, `style.css`) é servido pelo **nginx do host** a partir de
`root /var/www/roleta` (`roleta.conf`), que também faz proxy de `/ws` → `127.0.0.1:8765`.

> ⚠️ **Gap corrigido (17/06):** o deploy fazia `git reset` + `docker build/up` mas
> **não** copiava `frontend/` para `/var/www/roleta` nem recarregava o nginx — então
> mudanças de front **nunca chegavam em produção** (prod ficou congelado em `app.js?v=4.3.2`).
> O `roleta-deploy-pull.sh` agora, **após o healthcheck OK**, sincroniza
> `frontend/ → $WWW_DIR` (default `/var/www/roleta`) e roda `nginx -t && systemctl reload nginx`
> (passo **não-fatal**: não derruba o backend saudável).

Pré-requisitos no host (one-time, não automatizados):
- `roleta.conf` instalado em `/etc/nginx/sites-enabled/` (versionado no repo, mas o deploy
  não o copia).
- `nginx` instalado e `/var/www/roleta` gravável pelo usuário do deploy (root).

Verificação pós-deploy:
```bash
curl -s https://roleta.xma-ia.com/app.js | grep -c updateBlockGale   # >=1 (versão nova)
curl -s https://roleta.xma-ia.com/ | grep -o 'app.js?v=[0-9.]*'      # confirma o ?v= novo
```

> ℹ️ **Um script só (05/08).** Havia **dois** deploys no repo — `scripts/roleta-deploy-pull.sh`
> (canônico, com `alembic`) e `tools/deploy_pull.sh` (duplicado mais antigo) — e mantê-los em
> sincronia era convite à divergência. O duplicado virou **delegador** (`exec` do canônico) e o
> host passou a rodar o **launcher**. Estado de fato antes da mudança: o binário instalado em
> `/usr/local/bin/roleta-deploy-pull.sh` já era **byte-idêntico** ao `scripts/roleta-deploy-pull.sh`
> (mesmo hash, ambos já com o passo `alembic`) — ou seja, **não** havia migração `tools/` → `scripts/`
> pendente; o problema era só o **congelamento** da cópia.

## Observabilidade no deploy (OBS-INODE, 05/08/2026) — IMPORTANTE

> ⚠️ **Incidente que originou este passo.** Depois do deploy do SPR-V1, `obs/alerts.yml` no
> servidor tinha **21** regras e o `roleta-prometheus` continuava servindo **18** — `promtool`
> dentro do container e a API concordavam com o número errado. `POST /-/reload` **não** resolveu;
> só recriar o container. Causa: o deploy usa `git reset --hard`, que reescreve cada arquivo via
> temp+rename (**novo inode**), e a compose montava `obs/prometheus.yml`/`obs/alerts.yml` como
> **bind de arquivo**, que fixa o inode. Como nenhum passo do deploy tocava a stack de
> observabilidade, a divergência sobrevivia a qualquer número de deploys.

Correção em duas camadas:

1. `docker-compose.obs.yml` monta o **diretório** `./obs:/etc/prometheus:ro`. O `git` não recria o
   diretório, então trocas de inode dos arquivos passam a ser visíveis pelo container. Os caminhos
   internos não mudaram (`--config.file` e `rule_files` intactos).
2. `scripts/obs-apply.sh`, chamado pelo deploy: **detecta → valida → aplica → verifica**.

| Passo do deploy | Comando | Quando |
|---|---|---|
| retomar pendência | `obs-apply.sh resume` | antes do gate NOOP (senão a falha some no tick seguinte) |
| validar | `obs-apply.sh check $LOCAL $REMOTE` | logo após o `git reset`. **Só reprova por config inválida comprovada** (promtool dizendo `FAILED:`) ⇒ reset p/ `$LOCAL` + abort, sem tocar em container. Stack fora do ar ou promtool inexecutável (imagem ausente, daemon fora, ENOSPC) **não** derrubam um deploy de aplicação válido — ficam para o `apply` |
| aplicar | `obs-apply.sh apply $LOCAL $REMOTE` | após o healthcheck do app |

Regras do passo `apply`:

- **Sem** mudança em `obs/prometheus.yml`, `obs/alerts.yml`, `obs/*.rules.yml` ou
  `docker-compose.obs.yml` ⇒ *noop*: o Prometheus **não** é reiniciado. Se a própria detecção
  falhar (`git diff` com erro), o script **loga e assume que mudou** — silêncio ali esconderia
  justamente o deploy que precisava do reload.
- Mudou a `docker-compose.obs.yml` ⇒ `docker compose -f docker-compose.obs.yml up -d --no-deps
  prometheus` (recriação **única**: o `up -d` puro recria quando a definição do serviço mudou e é
  no-op nas retentativas). Volume `prometheus-data` (TSDB) preservado, **sem `--remove-orphans`**,
  demais containers intocados.
- **Depois de qualquer `up`, e sempre no caso de config/regras, vem `POST /-/reload`.** Um `up -d`
  pode ser no-op (a compose mudou num comentário ou noutro serviço) e então **nada** recarregaria.
- **Readiness tem orçamento próprio** (`READY_TIMEOUT`, default 120s): um Prometheus reiniciado
  pode passar minutos em WAL replay. Confundir "ainda subindo" com "não aplicou" recriaria o
  container no meio do replay, repetidamente.
- **Verificação anti-sucesso-falso** (todas obrigatórias):
  1. `/-/ready`;
  2. `prometheus_config_last_reload_successful` = 1 **e** o timestamp
     (`prometheus_config_last_reload_success_timestamp_seconds`) **avançou** em relação ao momento
     anterior — o booleano sozinho é *sticky*, continua 1 de um carregamento antigo;
  3. **SHA-256 do arquivo no repo == SHA-256 do que o container lê** (`docker cp` do caminho
     montado, do container **em execução** — `ps -q`, nunca `-a`, para não verificar contra um
     container efêmero do `compose run`): é o detector exato do inode preso;
  4. **número de regras carregadas na API == declarado nos `rule_files`** (`arquivo=21 carregadas=18`
     era o sintoma do incidente).
- Se a verificação reprovar, o script **escala para uma única recriação** (`--force-recreate`) e só
  então grava `escalated` na pendência (`/var/lib/roleta-deploy/obs_pending`) — o próximo tick
  retoma sem recriar de novo (sem loop de restart a cada 2 min); se a própria recriação falhar, a
  pendência **não** avança, para que a tentativa se repita.
- **Nenhuma falha limpa a pendência** — nem um `POST /-/reload` recusado, nem promtool
  inexecutável. Ela só é apagada após uma aplicação comprovada.
- `OBS_ENABLED=0` é kill-switch operacional: pula o passo **preservando** a pendência (retoma
  quando religar). `OBS_ENABLED=1` exige a stack presente (ausência vira falha).
- Falha ⇒ log `OBS FAIL` + `DEPLOY PARCIAL` e **exit 1** (unit do systemd fica `failed`). O app
  **não** sofre rollback: ele já está saudável no SHA novo.

### Bootstrap one-time no servidor (obrigatório uma vez)

O systemd chama `/usr/local/bin/roleta-deploy-pull.sh`. Hoje esse arquivo é uma **cópia congelada**
do deploy — byte-idêntica ao `scripts/roleta-deploy-pull.sh` do repo, mas que não acompanha o git.
Enquanto ela não for trocada pelo **launcher**, o passo de observabilidade nunca roda e o Prometheus
continua com o mount antigo:

```bash
cd /root/roleta-cloud
git log --oneline -1                       # confirmar que o fix ja chegou via timer
install -m755 scripts/roleta-deploy-launcher.sh /usr/local/bin/roleta-deploy-pull.sh
bash scripts/obs-apply.sh force            # valida + recria o Prometheus + verifica
# esperado: "OBS verificado ..." e "regras ok: arquivo=21 carregadas=21"
```

Este é o **único** passo manual: a partir dele, qualquer mudança futura no deploy ou no passo de
observabilidade chega sozinha pelo timer.

Verificação independente:

```bash
docker exec roleta-prometheus sha256sum /etc/prometheus/alerts.yml
sha256sum /root/roleta-cloud/obs/alerts.yml            # tem de bater
curl -s http://127.0.0.1:9090/api/v1/rules | grep -o '"query":' | wc -l
curl -s http://127.0.0.1:9090/metrics | grep prometheus_config_last_reload
docker volume ls | grep prometheus-data                # TSDB preservado
```

Rollback: `git revert` do PR (volta ao bind de arquivo e remove o passo) + `bash scripts/obs-apply.sh force`
para recriar o container com a definição antiga. Nada disso toca `prometheus-data`. Para pausar só o
passo de observabilidade sem revert: `OBS_ENABLED=0` no ambiente do deploy (a pendência é preservada).

> **Follow-up conhecido:** `obs/alertmanager.yml` ainda é bind **de arquivo** (mesma classe de bug).
> Não foi alterado aqui para não recriar um container fora do escopo do incidente.

## Bypass (deploy SSH direto)

Continua funcionando para hotfixes urgentes. O script detecta hash
local divergente do remote e nao re-aplica:

```powershell
$bash = "cd /root/roleta-cloud && git pull && docker compose up -d --build roleta-cloud"
ssh root@187.45.181.75 "$bash"
```

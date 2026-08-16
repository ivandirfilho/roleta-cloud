# Deploy Roleta Cloud

## Pipeline atual (SP-03)

```
dev push main
    ↓
GitHub Actions CI (lint+test+schema+silent-except)
    ↓ verde
[ servidor Debian HostDime ]
roleta-deploy.timer (systemd, 2min)
    ↓
/usr/local/bin/roleta-deploy-pull.sh   (shim -> git fetch + `git show origin/main:` + exec)  (NOVO 16/08)
    ↓ git fetch + compara hashes
    ↓ se diff: reset --hard + build + estado preflight + migrations + up -d roleta-cloud
    ↓ healthcheck 3× @ http://127.0.0.1:8766/health
    ↓ instala roleta.conf no nginx (pré-valida → mv atômico → nginx -t → rollback)  (NOVO 16/08)
    ↓ sync frontend/ → /var/www/roleta + reload nginx   (NOVO 17/06)
    ↓ obs-apply.sh: valida/aplica/verifica Prometheus   (NOVO 05/08, só se obs mudou)
    ↓ install --check: avisa se o entrypoint congelou   (NOVO 05/08, não-fatal)
    ↓ falha → rollback automatico para HEAD anterior
PROD running
```

**Tempo medio push → prod: ~3-4min** (CI 1min + janela timer 2min).

## Componentes

| Arquivo | Local | Descricao |
|---|---|---|
| `scripts/roleta-deploy-pull.sh` | repo | **script canonico** de deploy (idempotente, com alembic, rollback, nginx conf e passo de observabilidade) |
| `scripts/roleta-deploy-shim.sh` | repo | **entrypoint auto-sincronizado** (SPR-D2): a cada tick busca `origin/main` e executa a versão de lá — um `git revert` cura o deploy no tick seguinte |
| `scripts/roleta-deploy-launcher.sh` | repo | entrypoint durável de 1ª geração: `exec` do script do **checkout** (sem fetch); o shim o supersede |
| `scripts/roleta-deploy-install.sh` | repo | instala/atualiza o entrypoint (`install`, `install-shim`, `--check` para drift, `--rollback`) |
| `roleta.conf` | repo | vhost nginx (proxy `/ws` + `root /var/www/roleta`); **o deploy o instala** desde 16/08 |
| `/usr/local/lib/roleta-deploy/` | servidor | backup do entrypoint anterior (rollback) |
| `/var/lib/roleta-deploy/nginx/` | servidor | backups do `roleta.conf` (`.bak` + `.bak.<TS>`, fora das pastas do nginx de propósito) |
| `/var/lib/roleta-deploy/deploy-from-main.sh` | servidor | cópia da `main` que o shim executa (auditável: `diff` contra o repo) |
| `scripts/obs-apply.sh` | repo | passo de observabilidade (detecta/valida/aplica/verifica Prometheus) |
| `tools/deploy_pull.sh` | repo | duplicado legado — hoje so delega para o canonico |
| `/var/lib/roleta-deploy/obs_pending` | servidor | pendência de observabilidade (`action`/`escalated`/`sha`, retomada no tick seguinte) |
| `tools/systemd/roleta-deploy.service` | repo | unit oneshot |
| `tools/systemd/roleta-deploy.timer` | repo | dispara a cada 2min |
| `/usr/local/bin/roleta-deploy-pull.sh` | servidor | **entrypoint** (shim: puxa a `main` e executa; ou launcher, 1ª geração) |
| `/etc/systemd/system/roleta-deploy.{service,timer}` | servidor | units instaladas |
| `/var/log/roleta-deploy.log` | servidor | log de execucoes |
| `/var/lib/roleta-deploy/last_good` | servidor | SHA para rollback |

## Instalacao no servidor

> O que se instala em `/usr/local/bin` é um **entrypoint fino**, não uma cópia do deploy. Desde
> 16/08 o recomendado é o **shim** (`install-shim`): ele busca `origin/main` e executa a versão de
> lá, então até um deploy quebrado se cura com `git revert` no tick seguinte. O `launcher`
> (1ª geração) continua suportado: faz `exec` do script do **checkout**, sem fetch próprio.

Use o instalador (idempotente, com backup e rollback) em vez de copiar arquivos à mão:

```bash
ssh root@187.45.181.75 << 'EOF'
cd /root/roleta-cloud
bash scripts/roleta-deploy-install.sh install-shim   # instala/atualiza o shim (recomendado)
install -m644 tools/systemd/roleta-deploy.service /etc/systemd/system/
install -m644 tools/systemd/roleta-deploy.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now roleta-deploy.timer
systemctl list-timers roleta-deploy.timer
EOF
```

## MIG-0 — migracao do `state.json` para o volume persistente

O compose nao monta mais `./state.json` como arquivo isolado. O estado do motor
passa a ser `/app/data/state.json`, dentro do volume nomeado `roleta-data`. Isso
mantem `GameState.save()` atomico (`os.replace`) e evita perder o estado ao
restaurar apenas o disco de dados.

Execute uma vez, **antes** do primeiro deploy que contenha a mudanca:

```bash
cd /root/roleta-cloud
docker compose stop -t 60 roleta-cloud
bash scripts/migrate-state-to-volume.sh
VOLUME_NAME="${VOLUME_NAME:-$(docker volume ls --quiet --filter 'label=com.docker.compose.volume=roleta-data')}"
test "$(printf '%s\n' "$VOLUME_NAME" | sed '/^$/d' | wc -l)" -eq 1
docker run --rm -v "$VOLUME_NAME:/data:ro" busybox test -f /data/state.json
docker compose up -d roleta-cloud
```

O script tenta primeiro o nome normalizado pelo Compose e, se `--format json`
não estiver disponível, usa o label `com.docker.compose.volume`. Em Compose
antigo ou quando houver mais de um volume candidato, informe o nome físico:
`VOLUME_NAME=projeto_roleta-data bash scripts/migrate-state-to-volume.sh`.
Se o deploy automático também não resolver o volume, defina
`STATE_VOLUME_NAME=projeto_roleta-data` no ambiente da unit systemd, execute
`systemctl daemon-reload` e repita o deploy.

O script falha se o container estiver rodando, se o JSON de origem for invalido
ou se ja houver um destino diferente. Ele e idempotente quando os checksums
coincidem. A origem `./state.json` nao deve ser apagada ate concluir o soak e
um backup/restore do novo caminho.

O deploy pull-based tambem falha fechado se `roleta-data/state.json` nao existir:
isso impede que um merge automatico remova o bind legado e suba a aplicacao com
estado default. O operador deve executar a migracao e repetir o deploy.

Rollback do MIG-0: pare o container, reverta o commit do compose e suba a
versao anterior. A copia de origem permanece intacta e o compose antigo volta a
monta-la; nao remova `roleta-data/state.json` antes de validar o rollback.

## Launcher, shim e drift do deploy

| Comando | O que faz |
|---|---|
| `roleta-deploy-install.sh install-shim` | instala o **shim** em `/usr/local/bin/roleta-deploy-pull.sh` (recomendado desde 16/08); **idempotente** e com backup do entrypoint anterior |
| `roleta-deploy-install.sh` (ou `install`) | instala o **launcher**; **não rebaixa** um shim já instalado (é preciso `install-shim` ou `--rollback`) |
| `roleta-deploy-install.sh --check` | **read-only**, tri-estado: `0` em dia (shim **ou** launcher) · `0` + `DESATUALIZADO` (mesma família, outra versão — as mudanças versionadas **continuam** chegando) · `1` + `DRIFT` (sem marcador = cópia congelada) |
| `roleta-deploy-install.sh --rollback` | restaura o entrypoint anterior a partir do backup |

Ambos os modos gravam via **instalação atômica**: gate `bash -n` no candidato → arquivo temporário
no mesmo diretório → `mv -f` (rename). Nunca existe um entrypoint meio-escrito em
`/usr/local/bin`, nem quando o disco enche no meio da cópia.

O caminho e o nome do arquivo instalado **não mudam**, então a unit systemd
(`ExecStart=/usr/local/bin/roleta-deploy-pull.sh`) continua igual.

### Por que o shim se auto-atualiza (e por que isso é seguro)

O launcher resolve `$REPO_DIR/scripts/roleta-deploy-pull.sh` e faz `exec` — mas quem faz o `git`
é o **próprio script executado**. Se ele quebrar de um jeito que impeça o `fetch/reset`, o revert
no GitHub nunca chega ao host: **mergeou ≠ implantado**. O shim fecha esse laço:

```
fetch origin main → git show origin/main:scripts/roleta-deploy-pull.sh > /var/lib/roleta-deploy/deploy-from-main.sh
                  → gate `bash -n` → exec
```

A objeção histórica ("um deploy que reescreve a si mesmo fica irrecuperável se a versão nova
estiver quebrada") continua válida — e é exatamente por isso que o **shim** é imutável e mínimo:
ele não se reescreve, só escolhe o que executar, e a escolha é sempre `origin/main`.

- **Não toca a working tree** (usa `git show`, não `reset`): o gate de NOOP do deploy compara
  `HEAD` com `origin/main`; um shim que resetasse o checkout deixaria os dois sempre iguais e o
  deploy nunca voltaria a construir nada.
- **Gate `bash -n`** antes do `exec`: script inválido em `main` ⇒ `exit 1` visível, host intacto.
- **Gate de identidade**: o alvo precisa ser não-vazio e conter o marcador `ROLETA-DEPLOY-PULL`.
  Um arquivo vazio ou truncado passaria em `bash -n` e sairia `0` — o host reportaria "deploy ok"
  para sempre sem nunca deployar. Vazio/impostor ⇒ `exit 1`.
- **Fetch falhou** (rede/GitHub fora) ⇒ loga `FETCH FAIL` e executa a cópia do checkout: uma
  falha de rede não pode virar uma janela sem deploy.
- **Auditável**: `diff /var/lib/roleta-deploy/deploy-from-main.sh /root/roleta-cloud/scripts/roleta-deploy-pull.sh`
  mostra exatamente o que rodou.

**Drift é sinalizado sozinho — com um limite importante.** Ao fim de cada deploy bem-sucedido, o
script roda `roleta-deploy-install.sh --check` (read-only, **não-fatal**), e a unit systemd roda a
mesma sonda em `ExecStartPre=-…` (o `-` a torna não-fatal).

> ⚠️ **A sonda NÃO detecta o congelamento atual.** Ela vive no script **versionado**; enquanto o
> entrypoint for a cópia congelada de antes deste PR, essa cópia **nunca executa a sonda**. A sonda só
> protege contra um **re-congelamento futuro** (alguém reinstalar uma cópia por engano). O caso de
> hoje só é resolvido pelo **bootstrap manual — obrigatório**, abaixo. A chamada em `ExecStartPre`
> ajuda apenas nos hosts onde a unit for reinstalada (ela também é uma cópia).

O deploy **não** se auto-instala de propósito: reescrever o próprio entrypoint em execução pode deixar
o host sem deploy funcional se o arquivo novo estiver quebrado — a correção é um comando único e
reversível. (O shim não viola isso: ele nunca reescreve `/usr/local/bin`; só escolhe qual script
versionado executar, e essa escolha é revertível por PR.)

**`--check` distingue três estados** (hash diferente, sozinho, não prova que o deploy versionado parou
de chegar — um entrypoint de outra versão continua fazendo `exec` do script do repo):

| Estado | Como é reconhecido | Saída |
|---|---|---|
| em dia | hash idêntico ao `roleta-deploy-shim.sh` **ou** ao `roleta-deploy-launcher.sh` | `0`, silencioso (use `OBS_VERBOSE=1` para logar) |
| entrypoint desatualizado | hash diferente **mas** com o marcador `ROLETA-DEPLOY-SHIM` ou `ROLETA-DEPLOY-LAUNCHER` | `0` + `DESATUALIZADO` (mudanças versionadas continuam chegando) |
| cópia congelada | sem marcador nenhum | `1` + `DRIFT` com o comando de correção |


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

## Fencing da HostDime após o cutover Azure

O workflow `.github/workflows/deploy.yml` **não** possui mais gatilho por tag.
Mesmo manualmente, o job remoto só executa quando o operador confirma
`DEPLOY_HOSTDIME` e a variável de repositório `HOSTDIME_DEPLOY_ENABLED` está
explicitamente em `true`. Após o C-25, revogue `SERVER_HOST`, `SERVER_USER`,
`SERVER_PORT` e `SSH_PRIVATE_KEY` e mantenha a variável ausente/`false`.

O workflow `.github/workflows/acr-image.yml` é a esteira de imagens Azure: publica
tags rastreáveis (`azure-<sha>`) e `azure-latest`, mas não faz deploy nem altera DNS.

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

> ℹ️ **Última milha fechada (16/08, SPR-D2):** o `roleta.conf` também era um pré-requisito
> manual — versionado no repo, mas nunca copiado pelo deploy. Agora o deploy o instala
> (pré-valida o candidato, `mv` atômico, `nginx -t` global e **rollback** do backup se reprovar).
> Veja "Instalação do `roleta.conf`" abaixo.

Pré-requisitos no host (one-time, não automatizados):
- `nginx` instalado, com o `roleta.conf` **habilitado** (o deploy atualiza o conteúdo do arquivo;
  criar o symlink `sites-enabled/` na primeira vez continua sendo do bootstrap).
- `/var/www/roleta` gravável pelo usuário do deploy (root).

### Instalação do `roleta.conf` (SPR-D2, 16/08)

Roda **depois** do healthcheck OK, junto do sync de `frontend/`. É idempotente: se o arquivo
instalado já for byte-idêntico ao do repo (`cmp -s`), não escreve, não faz backup e não recarrega.

| Etapa | O que acontece se falhar |
|---|---|
| resolve o destino (`NGINX_CONF_DST` ou o 1º de `NGINX_CONF_CANDIDATES` que existir; **symlink é resolvido para o alvo**, preservando o layout `sites-available` + `sites-enabled`) | nenhum destino ⇒ `DESTINO NAO ENCONTRADO`; **dois arquivos reais distintos** (ex.: `sites-available/roleta.conf` e `conf.d/roleta.conf` sem relação) ⇒ `MULTIPLOS DESTINOS` — não adivinha qual é o ativo, pede `NGINX_CONF_DST` |
| `cmp -s` fonte × destino | iguais **e** sem marca de reload pendente ⇒ no-op silencioso |
| copia para `<dir>/.roleta.conf.roleta-deploy.tmp` (nome com ponto: `include …/*` do nginx **não** casa dotfiles) | erro de I/O ⇒ `ABORTADO`, destino intacto |
| **pré-valida o candidato** em um prefixo nginx isolado (`nginx -t -p <tmpdir> -c <tmpdir>/nginx.conf`) | inválido ⇒ `ABORTADO`, **destino intacto** e nenhum reload (janela zero). `mktemp` indisponível ⇒ **falha fechada** (não instala sem validar) |
| backup do atual em `/var/lib/roleta-deploy/nginx/roleta.conf.bak` + `.bak.<TS>` | — (prune mantém as `NGINX_BACKUP_KEEP` mais recentes, default 10) |
| marca `.reload-pending` + `mv` atômico para o destino | — |
| `nginx -t` **global** (autoridade final: vê o `http{}` real) | reprovou ⇒ restaura o backup **também por `mv` atômico**, reconfere e loga `ROLLBACK ok` (ou `ROLLBACK INSTAVEL`) |
| `systemctl reload nginx` → limpa `.reload-pending` | falhou ⇒ a marca **fica**; o tick seguinte revalida e recarrega mesmo com o arquivo já em dia. `DEPLOY PARCIAL` no fim (o app saudável **não** sofre rollback) |
| confere no `nginx -T` que o destino está entre os arquivos carregados | não está ⇒ `DESTINO INATIVO` (vhost em `sites-available` sem symlink): falha visível em vez de sucesso mentiroso. `nginx -T` indisponível ⇒ passo indeterminado, não bloqueia |

> **Por que a marca `.reload-pending`?** Entre o `mv` e o `reload` o disco e a memória do nginx
> divergem. Um SIGKILL/reboot (ou um reload que falha) nesse intervalo deixaria o tick seguinte
> com `cmp` igual ⇒ no-op ⇒ nginx servindo a config velha **para sempre**. A marca só é apagada
> depois do reload confirmado.

> **Por que checar `nginx -T`?** O arquivo pode estar perfeito e simplesmente não ser carregado.
> `nginx -t`, o reload e o healthcheck do app passariam todos — e o deploy reportaria sucesso sem
> ter mudado nada do que é servido. É o mesmo "mergeou ≠ implantado" numa casca menor.

> **Por que pré-validar em vez de instalar-e-testar?** `nginx -t` só valida o que já está no disco.
> Instalar primeiro abre uma janela em que um reload de terceiro (certbot, por exemplo) carregaria
> um vhost quebrado. O candidato é validado **antes** de o destino ser tocado.

> **Por que o backup não fica em `/etc/nginx/`?** O Debian usa `include /etc/nginx/sites-enabled/*;`
> — um glob sem filtro de extensão. Um `roleta.conf.bak` ali seria **carregado** como configuração,
> duplicando o `server{}` e quebrando o `nginx -t` sozinho. Por isso os backups vão para
> `/var/lib/roleta-deploy/nginx/`.

Kill switches (variáveis de ambiente do deploy):

| Variável | Default | Para quê |
|---|---|---|
| `NGINX_CONF_SYNC` | `1` | `0` desliga o passo inteiro |
| `NGINX_CONF_PREVALIDATE` | `1` | `0` pula só a pré-validação isolada (use se o vhost passar a depender de diretivas do `http{}` real e a pré-validação virar falso-negativo; o `nginx -t` global continua protegendo) |
| `NGINX_CONF_DST` | — | caminho exato do vhost, quando o host foge dos candidatos padrão |
| `NGINX_CONF_CANDIDATES` | `/etc/nginx/sites-available/roleta.conf /etc/nginx/sites-enabled/roleta.conf /etc/nginx/conf.d/roleta.conf /etc/nginx/sites-available/roleta` | lista de busca (o 1º que existir vence; symlink resolve para o alvo) |
| `NGINX_BACKUP_KEEP` | `10` | quantos backups datados manter |

Verificação pós-deploy:
```bash
grep 'NGINX CONF' /var/log/roleta-deploy.log | tail -5
cmp -s /root/roleta-cloud/roleta.conf /etc/nginx/sites-enabled/roleta.conf && echo "conf em dia"
ls -t /var/lib/roleta-deploy/nginx/ | head
```

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
  3. **SHA-256 do arquivo no repo == SHA-256 do que o container lê**, obtido por `docker exec`
     (`sha256sum`, com fallback `cat`) no container **em execução** (`ps -q`, nunca `-a`).
     **Não** se usa `docker cp`: para um bind mount o daemon re-resolve o caminho de origem no host,
     então num bind de arquivo com inode trocado ele devolve os bytes *novos* enquanto o processo lê os
     *antigos* — a comparação viraria host×host. Sem leitor na imagem ⇒ **falha** (fail-closed);
  4. **número de regras carregadas na API == declarado nos `rule_files`** (resolvidos com glob e
     subdiretórios, **deduplicados** — `alerts.yml` + `*alerts.yml` contam o arquivo uma vez —;
     padrão sem correspondência ⇒ **falha**, não "zero regras").

> **Guardrail deliberado (mais estrito que o Prometheus):** um `rule_files` que não casa com nada
> (glob vazio **ou** literal ausente) é tratado como **erro fatal** deste passo. O Prometheus ignora
> glob vazio em silêncio; aqui isso viraria "0 regras declaradas" e mascararia justamente a classe de
> bug que este script existe para pegar. Se algum dia for preciso um padrão opcional, ele terá de ser
> declarado explicitamente — não silenciosamente tolerado.

- **Falha de leitura não é divergência de conteúdo.** `/api/v1/rules` fora do ar, `docker exec`
  falhando, imagem sem leitor ou container que sumiu são classificados como **processo/transporte**:
  o passo falha, preserva a pendência e **não recria** (recriar não conserta um transporte quebrado).
  Só um hash realmente diferente ou `declared != loaded` **após leitura válida** contam como conteúdo.
- Se a verificação reprovar, o script só **escala para uma única recriação** (`--force-recreate`)
  quando há evidência de que recriar resolve: processo saudável (ready + reload fresco e bem-sucedido)
  mas **conteúdo divergente** — a assinatura do inode preso. POST recusado, reload rejeitado ou
  "nunca ficou ready" **falham sem recriar**: recriar um Prometheus que ainda servia a última config
  boa pode virar crash loop e reiniciar o WAL replay. A marca `escalated` só é gravada depois que a
  recriação dá certo; se ela falhar, a pendência **não** avança, para que a tentativa se repita.
- **Nenhuma falha limpa a pendência** — nem um `POST /-/reload` recusado, nem promtool
  inexecutável. Ela só é apagada após uma aplicação comprovada.
- `OBS_ENABLED=0` é kill-switch operacional: pula o passo **preservando** a pendência (retoma
  quando religar). `OBS_ENABLED=1` exige a stack presente (ausência vira falha). Em host sem a stack
  a pendência também é gravada — se ela estiver só temporariamente fora, a mudança não se perde.
- Falha ⇒ log `OBS FAIL` + `DEPLOY PARCIAL` e **exit 1** (unit do systemd fica `failed`). O app
  **não** sofre rollback: ele já está saudável no SHA novo.

### Bootstrap one-time no servidor (OBRIGATÓRIO — nada o substitui)

O systemd chama `/usr/local/bin/roleta-deploy-pull.sh`. Hoje esse arquivo é uma **cópia congelada**
do deploy — byte-idêntica a algum `scripts/roleta-deploy-pull.sh` do passado, mas que não acompanha o
git. **Nenhuma automação deste repo corrige isso sozinha**: a sonda de drift vive no script
versionado, e a cópia congelada nunca a executa. Enquanto este passo não for feito, o deploy roda
com a lógica antiga (sem observabilidade, sem instalação do `roleta.conf`) — e um `git revert` no
GitHub **não** chega ao host.

```bash
cd /root/roleta-cloud
git log --oneline -1                                  # confirmar que o fix ja chegou via timer
bash scripts/roleta-deploy-install.sh install-shim     # troca a copia congelada pelo SHIM (idempotente)
install -m644 tools/systemd/roleta-deploy.service /etc/systemd/system/   # sonda em ExecStartPre
install -m644 tools/systemd/roleta-deploy.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start roleta-deploy.service
bash scripts/obs-apply.sh force                        # valida + recria o Prometheus + verifica
# esperado: "INSTALL shim instalado ..." e "regras ok: arquivo=21 carregadas=21"
```

Este é o **último bootstrap manual desta classe**: com o shim instalado, qualquer mudança futura no
deploy, no entrypoint efetivo, no `roleta.conf` ou no passo de observabilidade chega sozinha pelo
timer — e um `git revert` cura o host no tick seguinte, sem ssh. Um re-congelamento acidental passa
a ser sinalizado (`INSTALL DRIFT …`) tanto no `/var/log/roleta-deploy.log` quanto no journal da unit.

Verificação independente:

```bash
docker exec roleta-prometheus sha256sum /etc/prometheus/alerts.yml   # visao do PROCESSO
sha256sum /root/roleta-cloud/obs/alerts.yml                          # tem de bater
curl -s http://127.0.0.1:9090/api/v1/rules | grep -o '"query":' | wc -l
curl -s http://127.0.0.1:9090/metrics | grep prometheus_config_last_reload
docker volume ls | grep prometheus-data                # TSDB preservado
```

> ⚠️ Não troque o `docker exec` por `docker cp` nesta verificação: `docker cp` faz o **daemon**
> re-resolver o caminho de origem no host, então num bind de arquivo com inode trocado ele mostra os
> bytes novos que o processo **não** está lendo — exatamente o erro que esconderia o incidente.

Rollback: veja a seção abaixo — o `git revert` remove os próprios scripts, então o procedimento não
pode depender deles.

### Rollback após `git revert`

O revert deste PR apaga `scripts/obs-apply.sh`, `scripts/roleta-deploy-launcher.sh` e
`scripts/roleta-deploy-install.sh` do checkout — qualquer receita que os invoque **não roda mais**.
Depois do revert (esperar o timer, ~2 min, ou `systemctl start roleta-deploy.service`):

```bash
cd /root/roleta-cloud

# 1) Prometheus volta para a definicao antiga (bind de arquivo) com o TSDB intacto.
#    `--no-deps` protege Grafana/AlertManager/app; NUNCA usar --remove-orphans.
docker compose -f docker-compose.obs.yml up -d --no-deps --force-recreate prometheus

# 2) (opcional) entrypoint de volta para a copia congelada, se o launcher tiver sido instalado
install -m755 /usr/local/lib/roleta-deploy/roleta-deploy-pull.sh.bak /usr/local/bin/roleta-deploy-pull.sh
#    (sem backup? use a versao revertida do repo:)
#    install -m755 /root/roleta-cloud/scripts/roleta-deploy-pull.sh /usr/local/bin/roleta-deploy-pull.sh

# 3) limpar estado que so o passo revertido usava (inofensivo, evita confusao)
rm -f /var/lib/roleta-deploy/obs_pending /var/lib/roleta-deploy/obs_seen

# 4) conferir
docker volume ls | grep prometheus-data          # TSDB preservado
curl -s http://127.0.0.1:9090/-/ready
```

O volume nomeado `prometheus-data` **não** é tocado em nenhum dos passos: `--force-recreate`
substitui o container, não o volume.

**Pausar sem reverter** (mantém tudo instalado): `OBS_ENABLED=0` no ambiente do deploy — o passo é
pulado e a pendência é preservada para quando religar.

> **Follow-up conhecido:** `obs/alertmanager.yml` ainda é bind **de arquivo** (mesma classe de bug).
> Não foi alterado aqui para não recriar um container fora do escopo do incidente.

## Rollback do SPR-D2 (shim + instalação do `roleta.conf`)

O PR do SPR-D2 é revertível por PR, sem ssh — é justamente essa a propriedade que ele entrega:

| Sintoma | Ação | Efeito |
|---|---|---|
| deploy quebrado pela versão nova do script | `git revert` + merge | o **shim** busca `origin/main` no tick seguinte (≤2 min) e passa a executar a versão revertida |
| `roleta.conf` causando problema | `git revert` do conf + merge | o próximo deploy reinstala a versão anterior (com pré-validação e `nginx -t`) |
| suspeita do passo de nginx, sem tempo de reverter | `NGINX_CONF_SYNC=0` no ambiente da unit | passo pulado; o resto do deploy segue |
| suspeita da pré-validação isolada (falso-negativo) | `NGINX_CONF_PREVALIDATE=1` → `0` | só o gate isolado é pulado; o `nginx -t` global continua |
| quero voltar ao entrypoint anterior no host | `bash scripts/roleta-deploy-install.sh --rollback` | restaura o backup em `/usr/local/lib/roleta-deploy/` |

Se o shim precisar ser desfeito no host (última linha de defesa, exige ssh):
`bash scripts/roleta-deploy-install.sh --rollback` ou `install-shim` de novo depois de um revert —
o `--rollback` não passa pelo gate `bash -n`, de propósito: ele restaura exatamente o que estava lá.



Continua disponível para hotfixes urgentes, mas **não contorna o MIG-0**:
primeiro confirme que o volume `roleta-data` contém `state.json` ou execute a
migração documentada acima. Depois, prefira o script canônico, que mantém o
preflight de estado, migrations e rollback:

```powershell
$bash = "cd /root/roleta-cloud && git pull && bash scripts/roleta-deploy-pull.sh"
ssh root@187.45.181.75 "$bash"
```

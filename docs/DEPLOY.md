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
/usr/local/bin/roleta-deploy-pull.sh
    ↓ git fetch + compara hashes
    ↓ se diff: reset --hard + build + estado preflight + migrations + up -d roleta-cloud
    ↓ healthcheck 3× @ http://127.0.0.1:8766/health
    ↓ sync frontend/ → /var/www/roleta + reload nginx   (NOVO 17/06)
    ↓ falha → rollback automatico para HEAD anterior
PROD running
```

**Tempo medio push → prod: ~3-4min** (CI 1min + janela timer 2min).

## Componentes

| Arquivo | Local | Descricao |
|---|---|---|
| `scripts/roleta-deploy-pull.sh` | repo | script canônico idempotente com rollback |
| `tools/systemd/roleta-deploy.service` | repo | unit oneshot |
| `tools/systemd/roleta-deploy.timer` | repo | dispara a cada 2min |
| `/usr/local/bin/roleta-deploy-pull.sh` | servidor | symlink/copy do script |
| `/etc/systemd/system/roleta-deploy.{service,timer}` | servidor | units instaladas |
| `/var/log/roleta-deploy.log` | servidor | log de execucoes |
| `/var/lib/roleta-deploy/last_good` | servidor | SHA para rollback |

## Instalacao no servidor

```bash
ssh root@187.45.181.75 << 'EOF'
cd /root/roleta-cloud
install -m755 scripts/roleta-deploy-pull.sh /usr/local/bin/roleta-deploy-pull.sh
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

> ℹ️ Há **dois** scripts de deploy no repo: `scripts/roleta-deploy-pull.sh` (canônico, com
> passo `alembic`) e `tools/deploy_pull.sh` (duplicado mais antigo). Ambos agora
> falham fechado se o estado não foi migrado; a instalação deve apontar para o
> canônico.

## Bypass (deploy SSH direto)

Continua disponível para hotfixes urgentes, mas **não contorna o MIG-0**:
primeiro confirme que o volume `roleta-data` contém `state.json` ou execute a
migração documentada acima. Depois, prefira o script canônico, que mantém o
preflight de estado, migrations e rollback:

```powershell
$bash = "cd /root/roleta-cloud && git pull && bash scripts/roleta-deploy-pull.sh"
ssh root@187.45.181.75 "$bash"
```

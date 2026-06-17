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
    ↓ se diff: reset --hard + build + up -d roleta-cloud
    ↓ healthcheck 3× @ http://127.0.0.1:8766/health
    ↓ sync frontend/ → /var/www/roleta + reload nginx   (NOVO 17/06)
    ↓ falha → rollback automatico para HEAD anterior
PROD running
```

**Tempo medio push → prod: ~3-4min** (CI 1min + janela timer 2min).

## Componentes

| Arquivo | Local | Descricao |
|---|---|---|
| `tools/deploy_pull.sh` | repo | script idempotente com rollback |
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
install -m755 tools/deploy_pull.sh /usr/local/bin/roleta-deploy-pull.sh
install -m644 tools/systemd/roleta-deploy.service /etc/systemd/system/
install -m644 tools/systemd/roleta-deploy.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now roleta-deploy.timer
systemctl list-timers roleta-deploy.timer
EOF
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

> ℹ️ Há **dois** scripts de deploy no repo: `scripts/roleta-deploy-pull.sh` (canônico, com
> passo `alembic`) e `tools/deploy_pull.sh` (duplicado mais antigo). Ambos receberam o sync do
> frontend; **follow-up:** unificar num só e apontar a instalação para o canônico.

## Bypass (deploy SSH direto)

Continua funcionando para hotfixes urgentes. O script detecta hash
local divergente do remote e nao re-aplica:

```powershell
$bash = "cd /root/roleta-cloud && git pull && docker compose up -d --build roleta-cloud"
ssh root@187.45.181.75 "$bash"
```

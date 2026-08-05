# Deploy Azure — Roleta Cloud (canary → cutover)

Artefatos para rodar o Roleta Cloud na VM Azure (`maquina_roleta_cloud`) **sem tocar
a produção HostDime**. O objetivo é deixar a Azura 100% pronta para que o cutover
final seja só **(1)** copiar os dados reais e **(2)** apontar o DNS.

> **`main` é produção.** Nada aqui faz merge, push em `main`, deploy na HostDime,
> mudança de DNS ou de NSG. Tudo é entregue por PR e executado manualmente na VM.

## Conteúdo

| Arquivo | O que faz | Onde roda |
|---|---|---|
| `compose.azure.yml` | Compose standalone; imagem por **digest** do ACR; volume no disco persistente; portas só em loopback; flags 1:1 com produção (INV-3). | VM |
| `Caddyfile` | Reverse proxy nativo (`/ws`→8765, `/healthz`→8766, estático). `:80` no canary; domínio + auto‑TLS no cutover. | VM |
| `caddy.service.d/10-roleta.conf` | Carrega `/etc/caddy/caddy.env` via systemd sem colocar segredo no unit. | VM |
| `kv-to-env.sh` | Lê segredos do Key Vault via Managed Identity → `.env` (0600) e prepara domínio/e-mail do Caddy em arquivo staged. | VM |
| `deploy-azure.sh` | Resolve digest, valida estado, sincroniza frontend, `compose up --no-build` e espera health. | VM |
| `backup-sqlite-to-blob.sh` | Snapshot consistente, `integrity_check`, manifesto SHA-256 e upload → Blob (via MI). | VM |
| `restore-sqlite-from-blob.sh` | Restaura um par DB/estado sem sobrescrever sem `--force`; exige app parada. | VM |
| `set-blob-lifecycle.sh` | Preserva regras existentes e aplica retenção dos backups SQLite. | Operador/CI com acesso de plano de controle |

## Recursos (RG `maquina_roleta_cloud`)

- **ACR:** `acrroletaprod` (`acrroletaprod.azurecr.io`) — imagem `roleta-cloud`, tags `azure-latest` / `azure-<commit>`.
- **Key Vault:** `kv-roleta-prod` — segredos (`ROLETA-API-KEY`, `POSTGRES-HOST`, `PG-APP-PASSWORD`, `ROLETA-DOMAIN`, `CADDY-EMAIL`, …).
- **Storage:** `stroletaprod` — container `backups`.
- **VM:** série L (resource disk `/mnt` é **efêmero** — os dados vivem em `/opt/roleta/data`, disco gerenciado).

## Pré-requisitos de RBAC na Managed Identity da VM (gate humano, uma vez)

- `AcrPull` no `acrroletaprod` — para `docker pull`.
- `Key Vault Secrets User` no `kv-roleta-prod` — para ler segredos.
- `Storage Blob Data Contributor` no `stroletaprod` — só para os backups.

## Passo a passo — canary (sem DNS, sem dados reais)

Na VM (root), em `/opt/roleta` com os arquivos deste diretório copiados:

```bash
chmod +x kv-to-env.sh deploy-azure.sh backup-sqlite-to-blob.sh \
  restore-sqlite-from-blob.sh set-blob-lifecycle.sh

# 1) Buscar o e-mail/domínio no KV e instalar somente o e-mail no canário.
sudo ./kv-to-env.sh
sudo install -m 0600 caddy.cutover.env /etc/caddy/caddy.env
sudo sed -i 's/^SITE_ADDRESS=.*/SITE_ADDRESS=:80/' /etc/caddy/caddy.env
sudo install -D -m 0644 caddy.service.d/10-roleta.conf \
  /etc/systemd/system/caddy.service.d/10-roleta.conf
sudo install -m 0644 Caddyfile /etc/caddy/Caddyfile
sudo systemctl daemon-reload
sudo systemctl reload caddy   # ou: caddy reload --config /etc/caddy/Caddyfile

# 2) Sobe o app (resolve digest da tag azure-latest, pull, up --no-build).
sudo ./deploy-azure.sh --allow-canary-seed
# tag específica:  sudo ROLETA_TAG=azure-<commit> ./deploy-azure.sh
```

### Validação do canary

```bash
# App healthy?
docker inspect -f '{{.State.Health.Status}}' roleta-cloud     # -> healthy

# Health via Caddy (Host header simula o domínio):
curl -fsS -H 'Host: roleta.xma-ia.com' http://127.0.0.1/healthz

# WS handshake no /ws (Caddy -> 127.0.0.1:8765):
curl -fsS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: roleta.xma-ia.com' -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' -H 'Sec-WebSocket-Version: 13' \
  http://127.0.0.1/ws     # 101/426/400 = porta certa; 502 = app fora

# As portas do app NÃO podem estar públicas (só loopback):
ss -ltnp | grep -E '8765|8766'   # deve aparecer só 127.0.0.1
```

## Cutover (passos finais — **gates humanos**)

Depois do canary validado, o dono executa, em janela de manutenção:

1. **Freeze + cópia dos dados reais** (evita split‑brain): parar a escrita na HostDime,
   copiar `decisions.db` (~65 MB) e `state.json` para `/opt/roleta/data` na Azure
   (ex.: `sqlite3 .backup` + `rsync`), conferir contagem de linhas/`PRAGMA integrity_check`.
2. **Ativar domínio + TLS no Caddy:** instalar o arquivo staged
   (`sudo install -m 0600 caddy.cutover.env /etc/caddy/caddy.env`) e recarregar.
   O certificado Let's Encrypt só emite **depois** que o DNS resolver para a VM.
3. **Apontar o DNS** (`roleta.xma-ia.com` + `www`) para o IP público da VM Azure.
4. (Opcional, Onda PG) `sudo ./deploy-azure.sh --with-pg --with-cdc` prepara
   o DSN e o worker, mas **não** liga `dual_write_pg`; o flag continua exigindo
   gate próprio e soak observado.

## Rollback

- **App:** `docker compose -f compose.azure.yml down` (os dados persistem em `/opt/roleta/data`);
  para voltar a uma imagem anterior, `ROLETA_TAG=azure-<commit-antigo> ./deploy-azure.sh`.
- **DNS:** reverter o registro para o IP da HostDime (a HostDime segue intacta durante todo o processo).

## Backups

O backup roda na VM e precisa de `az`, `sqlite3`, `python3` e `jq`. A Managed
Identity da VM tem somente acesso de dados ao Blob; ela **não** deve receber
permissão ampla para alterar políticas da conta.

```bash
sudo ./backup-sqlite-to-blob.sh
# cron diário (03:10 UTC):
# 10 3 * * * cd /opt/roleta && REQUIRE_DB=1 ./backup-sqlite-to-blob.sh >> /var/log/roleta-backup.log 2>&1
```

Aplicar a retenção preservando regras já existentes a partir de uma sessão
Azure autenticada como operador/CI com permissão de plano de controle
(`Storage Account Contributor` ou equivalente). O modo `user` não faz login
nem usa a Managed Identity da VM:

```bash
az login
AZURE_AUTH_MODE=user ./set-blob-lifecycle.sh
```

Teste de restore com a aplicação parada (sem `--force`, o script recusa
sobrescrever dados existentes):

```bash
sudo ./restore-sqlite-from-blob.sh --stamp 20260805T031000Z
```

## Notas de segurança

- `.env` é 0600 e **nunca** é commitado; segredos vêm do Key Vault em tempo de deploy.
- Imagem fixada por **digest** (imutável) — sem `latest` mutável no runtime.
- `ROLETA_PG_DSN` fica **ausente** no canary; `--with-pg` é opt-in e a senha é
  URL-encoded. Isso não liga `dual_write_pg`, que continua flag-controlado.
- O profile `cdc` só sobe com `--with-pg --with-cdc` e imagem publicada pelo
  workflow `Publish Azure images`; por padrão ele fica inerte.

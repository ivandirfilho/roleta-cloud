# 🚀 Máquina Azure — Provisionamento ATUAL (25/05/2026)

**Versão:** 3.0 — **substitui** `archive/sessoes/solicitação_de_estrutura_azure.md` v2.0 (+ atualização A3)
**Data:** 2026-05-25 02:40 UTC-3
**Solicitante:** Ivandir Filho (`@ivandirfilho`)
**Autor:** YOLO Orchestrator (Claude Opus 4.7)
**Stack MCP:** graphify + filesystem + sql (SSH PG) + sequential-thinking + memory
**Servidor atual a substituir:** `187.45.181.75` (HostDime VPS, **QEMU Virtual CPU 2.5+ sem SSE4.2/AVX2** — gargalo arquitetural confirmado por benchmark)

---

## 0. TL;DR para o agente provisionador

> **Provisione 1 Resource Group em `brazilsouth` com:**
> 1. **1 VM Linux Debian 12** `Standard_D2as_v5` (2 vCPU AMD EPYC + 8 GB) — substitui a VPS HostDime cuja CPU bloqueia numpy 2.x / torch / faiss.
> 2. **1 Azure Database for PostgreSQL Flexible Server** `Standard_B1ms` (1 vCPU / 2 GB / 32 GB) — PG hoje pesa **11 MB**; B1ms tem folga 1000×.
> 3. **1 Key Vault**, **1 Azure Container Registry Basic**, **1 Storage Account** (blobs para modelos ML + backups), **1 Log Analytics + App Insights**, **1 DNS Zone opcional**.
> 4. **GitHub OIDC Federation** (sem secrets de longa duração no Actions).
> 5. **Custo alvo:** **≈ USD 110/mês** (créditos sem cap → priorizar confiabilidade).
>
> O cutover do servidor antigo é responsabilidade do YOLO Orchestrator após o agente entregar este pacote. **NÃO desligue `187.45.181.75` — esse passo é meu (D+7 do cutover).**

---

## 1. 🔎 Auditoria da solicitação v2.0 (bugs + melhorias)

Encontrei **14 itens** que precisam mudar entre a v2.0 e este documento v3.0. Tabelei cada um com **ID**, **severidade**, **diff** e **justificativa**.

| ID | Sev | Item original (v2.0 + A3) | Decisão atual (v3.0) | Justificativa |
|----|-----|---------------------------|----------------------|---------------|
| **AZ-BUG-01** | 🔴 Crítico | `az vm create --admin-username root` | Trocar para `--admin-username azureuser` + `usermod -aG sudo + SSH key` | Azure **rejeita** o username `root` no Linux. Provisionamento falha imediatamente com `BadRequest`. Acesso "root" continua possível via `sudo -i` ou habilitando `PermitRootLogin prohibit-password` no `sshd_config` pós-boot. |
| **AZ-BUG-02** | 🔴 Crítico | A3 mudou Postgres para **VM + Docker** porque AGE não está no allowlist do Flexible Server | **Voltar para Flexible Server** | Auditoria do PG atual (`SELECT extname FROM pg_extension`) mostra: `age, pg_stat_statements, pgcrypto, plpgsql, vector`. **AGE foi instalada mas NÃO é usada em código** — todo regime/similarity hoje é `pgvector` (S-STRAT-12). Flexible Server suporta `vector`, `pg_partman`, `pg_cron`, `pgcrypto`, `pgmq`, `pg_stat_statements`. **Volta a fazer sentido** + libera 1 VM + simplifica backup PITR nativo + zero patching manual. |
| **AZ-BUG-03** | 🟡 Médio | Imagem Postgres custom em ACR (`pg15-age15`) + WAL-G + Blob para PITR | **Removido.** Flexible Server cuida de tudo | Decorrência da AZ-BUG-02. Elimina sprints **S-AGE-CHECK** e **S0.5** (imagem custom) do plano original. |
| **AZ-BUG-04** | 🟡 Médio | PG SKU `Standard_B2ms` (2 vCPU / 8 GB) | **`Standard_B1ms`** (1 vCPU / 2 GB / 32 GB SSD) | DB hoje = **11 MB total**. Mesmo com S-STRAT-9 backtest e crescimento 10×, 32 GB e 1 vCPU é folga absurda. Burstable B1ms = **USD 13/mês** vs B2ms = USD 50. Sempre dá pra escalar com 1 comando. |
| **AZ-BUG-05** | 🟡 Médio | VM `Standard_D2as_v5` 2 vCPU / **8 GB** + Data disk **256 GB P15** | **Mantém D2as_v5** + Data disk **64 GB P6** | RAM uso hoje: **1.6 GB / 6.8 GB** (24%). 8 GB é o ponto certo. Disco atual: **6.7 GB / 79 GB (9%)** + Docker images ~2 GB. **64 GB P6 = USD 5/mês** vs 256 GB P15 = USD 38. Auto-extend pode ser ligado se necessário. |
| **AZ-BUG-06** | 🟡 Médio | `--data-disk-sizes-gb 256` montado em `/var/lib/docker` via rsync **com Docker rodando** no cloud-init | Tirar Docker do path crítico do rsync: parar antes, mover, religar; OU usar **`storage.driver-opts`** apontando para `/mnt/docker` direto e nem montar em `/var/lib/docker` | Cloud-init original faz `mkfs.ext4`, monta em `/var/lib/docker_new`, rsync, e SÓ DEPOIS `systemctl stop docker`. Isso pega Docker no meio da operação — perda silenciosa de containers. |
| **AZ-BUG-07** | 🟢 Baixo | `mkfs.ext4 -F /dev/disk/azure/scsi1/lun0` (caminho frágil) | Usar `lsblk` para detectar disco data (ex.: `/dev/sdc`) e montar por **UUID** | Caminho `scsi1/lun0` muda entre tamanhos de VM. UUID em `/etc/fstab` é canônico. |
| **AZ-BUG-08** | 🟢 Baixo | Secret `JWT_PRIVATE_KEY` RSA 4096 + `JWT_PUBLIC_KEY` | **Removidos** | Não usamos JWT em produção. Quando S-AUTH-2 entrar, geramos na hora. Reduz superfície de secrets. |
| **AZ-BUG-09** | 🟡 Médio | Discord webhook como canal único para Alertmanager (v2.0 §16) | **Apenas Slack como destino primário** (placeholder vazio); ignorar Telegram conforme decisão recente do usuário | Discord não é canal oficial do projeto. Slack já cogitado no S-OBS-16. Telegram explicitamente descartado nesta sessão. |
| **AZ-BUG-10** | 🟢 Baixo | Tags `costctr = roleta-v5` | **`costctr = roleta-2026q2`** + tags atualizadas (`stack = pg15-vector`, `replaces = hostdime-187.45.181.75`) | Versão semântica do código não é boa unidade de cost-center. Período fiscal + traço da substituição ajuda no billing. |
| **AZ-BUG-11** | 🟡 Médio | `solicitação` original esquece **`spin_features` cw/ccw e `spins_vectors` cw/ccw + outbox `shared`** ao listar schemas | Documentar **3 schemas obrigatórios** (`cw`, `ccw`, `shared`) + `partman` (opcional) + `public` | Auditoria mostra: `cw=2 tabelas, ccw=2, shared=6`. Sem documentar, migration `alembic upgrade head` na nova infra cria schemas vazios e quebra ordem de inserção. |
| **AZ-BUG-12** | 🟡 Médio | Lista de 7 containers + obs stack separada — sem **cdc-worker, node-exporter, pg-exporter** | **Adicionar** os 3 ao inventário | Sem cdc-worker, **outbox para de processar** — feature_store/spins_vectors não populam. node-exporter e pg-exporter são scrape targets do Prometheus. |
| **AZ-BUG-13** | 🟢 Baixo | Modelos ML (`models/spin_autoencoder.joblib`) sem persistência fora da VM | **Sincronizar `models/` ↔ Blob `roleta-models`** via cron + download no boot | Treino do PCA leva tempo + depende de PG. Perder a VM = perder o modelo. Blob LRS = USD 0.02/mês para esse volume. |
| **AZ-BUG-14** | 🟢 Baixo | Cron de backup `state.json` (v2.0 §C7) mas não menciona **outbox snapshot semanal** | Adicionar dump semanal `pg_dump -Fc shared.outbox` para Blob `backups/` | Mesmo com PITR do Flexible Server, dump lógico salva a vida em data-corruption silenciosa. |

**Resumo das mudanças vs v2.0:**
- **-1 VM** (PG volta para PaaS Flexible Server) → economia ~USD 70/mês
- **-1 imagem custom no ACR** (PG stack)
- **-2 secrets** (JWT)
- **+3 containers documentados** (cdc-worker, node-exporter, pg-exporter)
- **+1 sync de modelos ML** (blob)
- **-USD 30/mês** estimado em SKUs reduzidos (B1ms PG, P6 disk)
- Username VM corrigido (evita falha imediata de provisionamento)

---

## 2. 🎯 Arquitetura alvo v3.0

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  CLIENTE (Chrome Extension)                                                   │
└──────────────────────────┬──────────────────────────────────────────────────┘
                            │ wss://ws.SEU-DOMINIO  (443/TCP, Caddy TLS auto)
                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  AZURE — Resource Group rg-roleta-prod (brazilsouth)                          │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  VM Linux  vm-roleta-app-01                                            │    │
│  │  Debian 12  •  Standard_D2as_v5 (2 vCPU AMD EPYC + 8 GB)               │    │
│  │  OS: 64 GB P6 SSD  •  Data: 64 GB P6 SSD → /var/lib/docker             │    │
│  │  IP estático Standard + FQDN: roleta-app-01.brazilsouth.cloudapp.azure.com │
│  │  Managed Identity (system) com get/list no KV                          │    │
│  │  Stack rodando:                                                         │    │
│  │    - roleta-cloud      (app principal Python 3.12)                     │    │
│  │    - roleta-cdc-worker (outbox → feature_store/spins_vectors)          │    │
│  │    - roleta-prometheus + alertmanager + grafana                         │    │
│  │    - node-exporter + pg-exporter                                        │    │
│  │    - Caddy reverse-proxy (TLS Let's Encrypt automático)                │    │
│  └──────────────────────────┬───────────────────────────────────────────┘    │
│                              │ pg_wire (5432, TLS, private endpoint)            │
│                              ▼                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  Azure DB for PostgreSQL Flexible Server  pg-roleta-prod              │    │
│  │  PG 16  •  Standard_B1ms (1 vCPU / 2 GB)  •  32 GB Premium SSD        │    │
│  │  PITR 7d + LTR mensal 6m  •  Private Endpoint na subnet-db            │    │
│  │  Extensions: vector, pgmq, pg_partman, pg_cron, pgcrypto,             │    │
│  │              pg_stat_statements, uuid-ossp                            │    │
│  │  Schemas: shared, cw, ccw, partman, public                            │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
│  ┌──────────────────┐ ┌──────────────────┐ ┌────────────────────────────┐    │
│  │ Key Vault        │ │ Container Reg.   │ │ Storage Account            │    │
│  │ kv-roleta-prod   │ │ acrroletaprod    │ │ stroletaprod (LRS)         │    │
│  │ 14 secrets       │ │ Basic            │ │ blobs: models, backups,    │    │
│  │ (lista §6)       │ │                  │ │        reports             │    │
│  └──────────────────┘ └──────────────────┘ └────────────────────────────┘    │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ Log Analytics law-roleta-prod + App Insights ai-roleta-prod (30d)     │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ VNet roleta-vnet-prod 10.20.0.0/16                                    │    │
│  │  subnet-app 10.20.1.0/24 (VM)                                         │    │
│  │  subnet-db  10.20.2.0/24 (PG delegated)                               │    │
│  │  subnet-pe  10.20.3.0/24 (Private Endpoints)                          │    │
│  │ NSG nsg-app-prod: 22 SSH (IP whitelist), 80/443 público, resto deny   │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 📋 Nomenclatura obrigatória (use EXATAMENTE)

| Recurso | Nome |
|---------|------|
| Resource Group | `rg-roleta-prod` |
| Region | `brazilsouth` |
| VNet | `roleta-vnet-prod` |
| Subnets | `subnet-app` (10.20.1.0/24), `subnet-db` (10.20.2.0/24), `subnet-pe` (10.20.3.0/24) |
| NSG | `nsg-app-prod` |
| VM | `vm-roleta-app-01` |
| VM OS disk | `vm-roleta-app-01-osdisk` |
| VM data disk | `vm-roleta-app-01-data` |
| Public IP | `pip-roleta-app-01` (Static, Standard, FQDN `roleta-app-01`) |
| Postgres | `pg-roleta-prod` (DB: `roleta`, admin: `roleta_admin`) |
| Key Vault | `kv-roleta-prod` |
| ACR | `acrroletaprod` |
| Storage Account | `stroletaprod` |
| Log Analytics | `law-roleta-prod` |
| App Insights | `ai-roleta-prod` |
| Service Principal Orch | `sp-roleta-orch` |
| Managed Identity VM | sistema-atribuída (sem nome próprio) |
| Federation OIDC GitHub | `gh-oidc-roleta-prod` |

**Tags em TODO recurso:**
```
project   = roleta-cloud
env       = production
owner     = ivandirfilho
managed   = yolo-orchestrator
costctr   = roleta-2026q2
stack     = pg15-vector
replaces  = hostdime-187.45.181.75
```

---

## 4. 🔨 Passo a passo executável

> Comandos Azure CLI. Cada bloco é idempotente onde possível (use `az ... show` antes de `create` em produção real).

### 4.1 — Bootstrap (RG + VNet + NSG + DNS)

```bash
SUB_ID="<subscription-uuid>"
LOC="brazilsouth"
RG="rg-roleta-prod"

az account set --subscription $SUB_ID
az group create -n $RG -l $LOC --tags project=roleta-cloud env=production owner=ivandirfilho

# VNet + subnets
az network vnet create -g $RG -n roleta-vnet-prod \
  --address-prefix 10.20.0.0/16 \
  --subnet-name subnet-app --subnet-prefix 10.20.1.0/24

az network vnet subnet create -g $RG --vnet-name roleta-vnet-prod \
  -n subnet-db --address-prefix 10.20.2.0/24 \
  --delegations Microsoft.DBforPostgreSQL/flexibleServers

az network vnet subnet create -g $RG --vnet-name roleta-vnet-prod \
  -n subnet-pe --address-prefix 10.20.3.0/24 \
  --disable-private-endpoint-network-policies true

# NSG: SSH só do IP do Ivandir
IVANDIR_IP="<perguntar §5>"
az network nsg create -g $RG -n nsg-app-prod
az network nsg rule create -g $RG --nsg-name nsg-app-prod -n allow-ssh \
  --priority 100 --source-address-prefixes "$IVANDIR_IP/32" \
  --destination-port-ranges 22 --access Allow --protocol Tcp
az network nsg rule create -g $RG --nsg-name nsg-app-prod -n allow-http \
  --priority 200 --source-address-prefixes "*" \
  --destination-port-ranges 80 --access Allow --protocol Tcp
az network nsg rule create -g $RG --nsg-name nsg-app-prod -n allow-https \
  --priority 210 --source-address-prefixes "*" \
  --destination-port-ranges 443 --access Allow --protocol Tcp
az network vnet subnet update -g $RG --vnet-name roleta-vnet-prod \
  -n subnet-app --network-security-group nsg-app-prod

# Private DNS Zone para o Postgres
az network private-dns zone create -g $RG -n privatelink.postgres.database.azure.com
az network private-dns link vnet create -g $RG -n pdns-pg-link \
  --zone-name privatelink.postgres.database.azure.com \
  --virtual-network roleta-vnet-prod --registration-enabled false
```

### 4.2 — Key Vault + secrets iniciais

```bash
az keyvault create -g $RG -n kv-roleta-prod -l $LOC \
  --enable-rbac-authorization false --retention-days 30

# senhas geradas localmente — NUNCA logar
PG_ADMIN_PW=$(openssl rand -base64 32)
PG_APP_PW=$(openssl rand -base64 32)
PG_GRAFANA_PW=$(openssl rand -base64 32)
GRAFANA_ADMIN_PW=$(openssl rand -base64 24)
DEVICE_HMAC=$(openssl rand -hex 32)
API_KEY=$(openssl rand -hex 32)

for kv in \
  "PG_ADMIN_PASSWORD:$PG_ADMIN_PW" \
  "PG_APP_PASSWORD:$PG_APP_PW" \
  "PG_GRAFANA_PASSWORD:$PG_GRAFANA_PW" \
  "GRAFANA_ADMIN_PASSWORD:$GRAFANA_ADMIN_PW" \
  "DEVICE_HMAC_KEY:$DEVICE_HMAC" \
  "ROLETA_API_KEY:$API_KEY"; do
  N=${kv%%:*}; V=${kv#*:}
  az keyvault secret set --vault-name kv-roleta-prod --name "$N" --value "$V" >/dev/null
done
```

### 4.3 — PostgreSQL Flexible Server

```bash
az postgres flexible-server create \
  --resource-group $RG --name pg-roleta-prod --location $LOC \
  --tier Burstable --sku-name Standard_B1ms \
  --storage-size 32 --storage-auto-grow Enabled \
  --version 16 \
  --backup-retention 7 --geo-redundant-backup Disabled \
  --high-availability Disabled \
  --admin-user roleta_admin --admin-password "$PG_ADMIN_PW" \
  --vnet roleta-vnet-prod --subnet subnet-db \
  --private-dns-zone privatelink.postgres.database.azure.com \
  --yes --tags project=roleta-cloud

# Extensions
az postgres flexible-server parameter set -g $RG --server-name pg-roleta-prod \
  --name azure.extensions \
  --value "VECTOR,PGMQ,PG_PARTMAN,PG_CRON,PGCRYPTO,PG_STAT_STATEMENTS,UUID-OSSP"

# Shared preload libs
az postgres flexible-server parameter set -g $RG --server-name pg-roleta-prod \
  --name shared_preload_libraries \
  --value "pg_stat_statements,pg_cron,pg_partman_bgw"

az postgres flexible-server parameter set -g $RG --server-name pg-roleta-prod \
  --name pg.cron_database_name --value roleta

az postgres flexible-server restart -g $RG -n pg-roleta-prod
```

Depois (via VM como jump host, **após VM provisionada**):

```sql
-- conectado como roleta_admin
CREATE DATABASE roleta OWNER roleta_admin;
\c roleta

CREATE SCHEMA IF NOT EXISTS shared;
CREATE SCHEMA IF NOT EXISTS cw;
CREATE SCHEMA IF NOT EXISTS ccw;
CREATE SCHEMA IF NOT EXISTS partman;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;
CREATE EXTENSION IF NOT EXISTS pgmq;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE ROLE roleta_app LOGIN PASSWORD '<PG_APP_PASSWORD do KV>';
GRANT CONNECT ON DATABASE roleta TO roleta_app;
GRANT USAGE, CREATE ON SCHEMA shared, cw, ccw TO roleta_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA shared, cw, ccw GRANT ALL ON TABLES TO roleta_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA shared, cw, ccw GRANT ALL ON SEQUENCES TO roleta_app;

CREATE ROLE roleta_grafana LOGIN PASSWORD '<PG_GRAFANA_PASSWORD do KV>';
GRANT CONNECT ON DATABASE roleta TO roleta_grafana;
GRANT USAGE ON SCHEMA shared, cw, ccw TO roleta_grafana;
ALTER DEFAULT PRIVILEGES IN SCHEMA shared, cw, ccw GRANT SELECT ON TABLES TO roleta_grafana;
```

### 4.4 — VM Linux (com fix do AZ-BUG-01)

```bash
# IMPORTANTE: --admin-username NÃO PODE ser "root"
az vm create \
  --resource-group $RG --name vm-roleta-app-01 --location $LOC \
  --image Debian:debian-12:12:latest \
  --size Standard_D2as_v5 \
  --vnet-name roleta-vnet-prod --subnet subnet-app \
  --nsg nsg-app-prod \
  --public-ip-address pip-roleta-app-01 \
  --public-ip-sku Standard --public-ip-address-allocation static \
  --public-ip-address-dns-name roleta-app-01 \
  --admin-username azureuser \
  --ssh-key-values "@~/.ssh/ivandir.pub" "@~/.ssh/orch.pub" \
  --os-disk-name vm-roleta-app-01-osdisk \
  --os-disk-size-gb 64 \
  --storage-sku StandardSSD_LRS \
  --data-disk-sizes-gb 64 \
  --assign-identity \
  --accelerated-networking true \
  --custom-data cloud-init-vm.yaml
```

**`cloud-init-vm.yaml`** (fix AZ-BUG-06 + AZ-BUG-07):

```yaml
#cloud-config
package_update: true
package_upgrade: true
packages:
  - curl
  - git
  - htop
  - jq
  - ufw
  - ca-certificates
  - gnupg
  - lsb-release
  - python3-pip
  - postgresql-client-16

runcmd:
  # Detecta o disco data por tamanho/empty (NÃO usa /dev/disk/azure/scsi1/lun0)
  - DATA_DEV=$(lsblk -dno NAME,SIZE,TYPE | awk '$3=="disk" && $2=="64G" {print "/dev/"$1; exit}')
  - mkfs.ext4 -F "$DATA_DEV"
  - DATA_UUID=$(blkid -s UUID -o value "$DATA_DEV")
  - mkdir -p /mnt/docker
  - echo "UUID=$DATA_UUID /mnt/docker ext4 defaults,nofail 0 2" >> /etc/fstab
  - mount /mnt/docker

  # Docker Engine + Compose v2 oficial
  - install -m 0755 -d /etc/apt/keyrings
  - curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  - chmod a+r /etc/apt/keyrings/docker.gpg
  - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
  - apt-get update
  - apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # daemon.json APONTA para /mnt/docker (sem rsync com Docker rodando — fix AZ-BUG-06)
  - mkdir -p /etc/docker
  - |
    cat > /etc/docker/daemon.json <<EOF
    {
      "data-root": "/mnt/docker",
      "log-driver": "json-file",
      "log-opts": { "max-size": "100m", "max-file": "5" },
      "live-restore": true
    }
    EOF
  - systemctl enable docker --now

  # Caddy reverse-proxy
  - apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  - curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  - curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  - apt-get update && apt-get install -y caddy
  - systemctl enable caddy --now

  # Azure CLI
  - curl -sL https://aka.ms/InstallAzureCLIDeb | bash

  # SSH: permite root via key (sem senha)
  - sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
  - sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  - cp /home/azureuser/.ssh/authorized_keys /root/.ssh/authorized_keys
  - chown root:root /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
  - systemctl restart ssh

  # UFW + firewall mínimo
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow 22/tcp
  - ufw allow 80/tcp
  - ufw allow 443/tcp
  - ufw --force enable

  # Timezone + estrutura de diretórios
  - timedatectl set-timezone America/Sao_Paulo
  - mkdir -p /opt/roleta/{app,obs,backup,models}

write_files:
  - path: /etc/caddy/Caddyfile
    permissions: "0644"
    content: |
      {
        email placeholder@example.com
      }
      :80 {
        respond "Roleta Cloud VM provisioned. Awaiting config." 200
      }
```

### 4.5 — Managed Identity da VM → Key Vault

```bash
PRINCIPAL_ID=$(az vm identity show -g $RG -n vm-roleta-app-01 --query principalId -o tsv)
az keyvault set-policy -n kv-roleta-prod \
  --object-id $PRINCIPAL_ID --secret-permissions get list
```

### 4.6 — ACR + Storage Account + Log Analytics + App Insights

```bash
az acr create -g $RG -n acrroletaprod --sku Basic --admin-enabled true

az storage account create -g $RG -n stroletaprod -l $LOC \
  --sku Standard_LRS --kind StorageV2 --https-only true \
  --min-tls-version TLS1_2
for c in models backups reports; do
  az storage container create --account-name stroletaprod -n $c --auth-mode login
done
STORAGE_CONN=$(az storage account show-connection-string -g $RG -n stroletaprod -o tsv)
az keyvault secret set --vault-name kv-roleta-prod --name STORAGE_ACCOUNT_CONNECTION_STRING --value "$STORAGE_CONN"

az monitor log-analytics workspace create -g $RG -n law-roleta-prod -l $LOC --retention-time 30
WSID=$(az monitor log-analytics workspace show -g $RG -n law-roleta-prod --query id -o tsv)
az monitor app-insights component create -g $RG -a ai-roleta-prod -l $LOC --workspace $WSID
APPINS_CS=$(az monitor app-insights component show -g $RG -a ai-roleta-prod --query connectionString -o tsv)
az keyvault secret set --vault-name kv-roleta-prod --name APP_INSIGHTS_CONNECTION_STRING --value "$APPINS_CS"
```

### 4.7 — Service Principal + GitHub OIDC Federation

```bash
# SP para o YOLO orchestrator (CLI local + scripts pontuais)
SP_JSON=$(az ad sp create-for-rbac --name sp-roleta-orch \
  --role Contributor --scopes /subscriptions/$SUB_ID/resourceGroups/$RG)
echo "$SP_JSON" > sp-orch.json   # NÃO commitar
ORCH_ID=$(echo $SP_JSON | jq -r .appId)
ORCH_PW=$(echo $SP_JSON | jq -r .password)
az keyvault secret set --vault-name kv-roleta-prod --name SP_ORCH_CLIENT_ID --value "$ORCH_ID"
az keyvault secret set --vault-name kv-roleta-prod --name SP_ORCH_CLIENT_SECRET --value "$ORCH_PW"
az role assignment create --assignee $ORCH_ID --role "Key Vault Administrator" --scope $(az keyvault show -n kv-roleta-prod --query id -o tsv)
az role assignment create --assignee $ORCH_ID --role "AcrPush" --scope $(az acr show -n acrroletaprod --query id -o tsv)

# OIDC Federation para GitHub Actions (sem secret de longa duração)
GH_APP=$(az ad app create --display-name gh-oidc-roleta-prod --query appId -o tsv)
az ad sp create --id $GH_APP
az role assignment create --assignee $GH_APP --role Contributor --scope /subscriptions/$SUB_ID/resourceGroups/$RG
az role assignment create --assignee $GH_APP --role AcrPush --scope $(az acr show -n acrroletaprod --query id -o tsv)

# Federation credential — branch main + tags v*
cat > fed-main.json <<EOF
{ "name":"gh-main", "issuer":"https://token.actions.githubusercontent.com",
  "subject":"repo:ivandirfilho/roleta-cloud:ref:refs/heads/main",
  "audiences":["api://AzureADTokenExchange"] }
EOF
az ad app federated-credential create --id $GH_APP --parameters fed-main.json
```

### 4.8 — Resource Locks (segurança)

```bash
for r in "$(az group show -n $RG --query id -o tsv)" \
         "$(az keyvault show -n kv-roleta-prod --query id -o tsv)" \
         "$(az postgres flexible-server show -g $RG -n pg-roleta-prod --query id -o tsv)" \
         "$(az storage account show -g $RG -n stroletaprod --query id -o tsv)"; do
  az lock create --name no-delete --lock-type CanNotDelete --resource $r
done
```

### 4.9 — Cost Management Alert

```bash
THRESHOLD=350   # USD/mês (default; perguntar §5 item N)
az consumption budget create-with-rg \
  --resource-group $RG --budget-name budget-roleta-prod \
  --amount $THRESHOLD --time-grain Monthly \
  --start-date $(date +%Y-%m-01) --end-date $(date -d '+1 year' +%Y-%m-01) \
  --notifications threshold=80 contactEmails=ivandirfilho@email.com enabled=true operator=GreaterThan
```

### 4.10 — Backup automático do `state.json` + `pg_dump` semanal

Cron na VM (após cutover do app):

```bash
# /etc/cron.daily/state-backup
#!/bin/bash
set -e
DATE=$(date +%F)
az login --identity >/dev/null
CONN=$(az keyvault secret show --vault-name kv-roleta-prod --name STORAGE_ACCOUNT_CONNECTION_STRING --query value -o tsv)
az storage blob upload --connection-string "$CONN" \
  --container-name backups --name "state-$DATE.json" \
  --file /opt/roleta/app/state.json --overwrite

# /etc/cron.weekly/pg-dump
#!/bin/bash
set -e
DATE=$(date +%F)
az login --identity >/dev/null
PGPW=$(az keyvault secret show --vault-name kv-roleta-prod --name PG_APP_PASSWORD --query value -o tsv)
CONN=$(az keyvault secret show --vault-name kv-roleta-prod --name STORAGE_ACCOUNT_CONNECTION_STRING --query value -o tsv)
PGPASSWORD=$PGPW pg_dump -Fc \
  -h pg-roleta-prod.privatelink.postgres.database.azure.com \
  -U roleta_app roleta > /tmp/roleta-$DATE.dump
az storage blob upload --connection-string "$CONN" \
  --container-name backups --name "pg-$DATE.dump" \
  --file /tmp/roleta-$DATE.dump --overwrite
rm /tmp/roleta-$DATE.dump
```

### 4.11 — Sync de modelos ML (AZ-BUG-13)

```bash
# /etc/cron.hourly/models-sync (upload de novos modelos)
#!/bin/bash
az login --identity >/dev/null
CONN=$(az keyvault secret show --vault-name kv-roleta-prod --name STORAGE_ACCOUNT_CONNECTION_STRING --query value -o tsv)
az storage blob sync --connection-string "$CONN" \
  --container models --source /opt/roleta/models
```

E no boot do `roleta-cloud`:

```bash
# /opt/roleta/app/entrypoint-pre.sh (chamado pelo Dockerfile)
CONN=$(az keyvault secret show --vault-name kv-roleta-prod --name STORAGE_ACCOUNT_CONNECTION_STRING --query value -o tsv)
az storage blob download-batch --connection-string "$CONN" \
  --source models --destination /app/models 2>/dev/null || true
```

---

## 5. ❓ Inputs que o agente precisa do usuário (antes de começar)

| # | Item | Onde será usado |
|---|------|-----------------|
| A | **Azure Subscription ID** | `az account set` |
| B | **Tenant ID** | OIDC + SP login |
| C | **Chave SSH pública do Ivandir** | `~/.ssh/ivandir.pub` injetada na VM |
| D | **Email** para Let's Encrypt (Caddy) | `CADDY_EMAIL` no KV + Caddyfile |
| E | **Domínio** (ex.: `roletacloud.com.br`) + estratégia DNS (manter onde está OU delegar Azure DNS) | DNS records + Caddyfile |
| F | **IP fixo do Ivandir** (para SSH allowlist no NSG) | regra `allow-ssh` |
| G | **Threshold USD/mês** para Cost Management Alert (default 350) | §4.9 |
| H | **Slack webhook URL** ou marcar "criar canal depois" | Alertmanager receiver (Telegram **NÃO** — decisão do usuário) |
| I | **Confirmação** que servidor `187.45.181.75` pode ser desligado D+7 após cutover | cronograma |

---

## 6. 🧪 Bateria de testes (T01–T35)

Critério de aceitação do agente: **100% verde OU lista justificada de falhas**.

### Azure plane
| # | Teste | OK se |
|---|-------|-------|
| T01 | `az group show -n rg-roleta-prod` | `provisioningState=Succeeded` |
| T02 | VNet com 3 subnets corretas | `az network vnet show` lista 3 |
| T03 | NSG SSH permite somente IP do Ivandir | `sourceAddressPrefix == <IP>/32` |
| T04 | Public IP estático Standard com FQDN | `allocationMethod=Static, sku=Standard, dnsSettings.fqdn` populado |
| T05 | VM running | `instanceView.statuses[?code=='PowerState/running']` |
| T06 | PG Flexible Server Ready | `state=Ready` |
| T07 | Extensions carregadas | `SELECT extname FROM pg_extension` inclui vector, pgmq, pg_partman, pg_cron, pgcrypto |
| T08 | PG não tem IP público | `publicNetworkAccess=Disabled` |
| T09 | PG resolve via private DNS | `nslookup pg-roleta-prod.privatelink…` → 10.20.2.x |
| T10 | KV acessível pela MI da VM | `ssh azureuser@<IP> "sudo az login --identity && az keyvault secret list --vault-name kv-roleta-prod"` |
| T11 | ACR up + adminEnabled | `az acr show … sku.name=Basic` |
| T12 | Storage Account + 3 containers | `models`, `backups`, `reports` listados |
| T13 | Log Analytics + App Insights linkados | `workspaceResourceId` no AI = id do LAW |
| T14 | Resource Locks | `az lock list -g $RG` mostra 4 locks |
| T15 | OIDC Federation criada | `az ad app federated-credential list --id $GH_APP` mostra `gh-main` |

### VM plane (via SSH `azureuser@<IP>`)
| # | Teste | OK se |
|---|-------|-------|
| T16 | Docker + Compose v2 | `docker compose version` mostra v2.x |
| T17 | data-root = /mnt/docker | `docker info | grep "Docker Root Dir"` |
| T18 | Caddy ativo | `systemctl is-active caddy` |
| T19 | UFW ativo, 22/80/443 | `ufw status` |
| T20 | Timezone | `date` → -03:00 |
| T21 | Azure CLI + MI | `sudo az login --identity && az account show` |
| T22 | Root SSH por key funciona | `ssh root@<IP>` (com chave do Ivandir) |
| T23 | Password auth desabilitada | `grep ^PasswordAuthentication /etc/ssh/sshd_config` → no |
| T24 | `pg_isready` para PG privado | `accepting connections` |
| T25 | psql via DSN do KV | `SELECT version()` retorna 16.x |
| T26 | ACR pull funciona (MI) | `az acr login -n acrroletaprod && docker pull acrroletaprod.azurecr.io/hello-world` |
| T27 | Blob upload/download (MI) | `az storage blob upload --account-name stroletaprod --auth-mode login` |

### App plane (depois do deploy do código pelo YOLO Orchestrator)
| # | Teste | OK se |
|---|-------|-------|
| T28 | Migration Alembic | `alembic upgrade head` cria `cw/ccw/shared` |
| T29 | roleta-cloud healthy | `docker compose ps` → healthy |
| T30 | cdc-worker processando outbox | `SELECT count(*) FROM shared.outbox WHERE status='failed'` = 0 após 5 min |
| T31 | feature_store popula | `SELECT count(*) FROM cw.spin_features` > 0 após 10 spins |
| T32 | spins_vectors com pgvector | `SELECT count(*) FROM cw.spins_vectors WHERE raw_features IS NOT NULL` > 0 |
| T33 | Grafana login + dashboards | `https://grafana.<DOMINIO>` carrega `roleta-shadow-grid` |
| T34 | Alertmanager regras carregadas | `curl :9093/api/v2/status` retorna `cluster:ready` |
| T35 | Modelos sincronizados | `ls /opt/roleta/models/spin_autoencoder.joblib` existe pós-boot (via blob sync) |

---

## 7. 💰 Custo mensal estimado

| Item | SKU | USD/mês |
|------|-----|---------|
| VM D2as_v5 (2 vCPU AMD / 8 GB) | reservada | ~70 |
| OS disk 64 GB StandardSSD | E6 | ~5 |
| Data disk 64 GB StandardSSD | E6 | ~5 |
| PostgreSQL Flexible B1ms (1 vCPU / 2 GB) | Burstable | ~13 |
| PG Storage 32 GB Premium | — | ~4 |
| Public IP Standard estático | — | ~4 |
| Key Vault | Standard (operations) | ~1 |
| ACR Basic | — | ~5 |
| Storage Account LRS (3 containers, <5 GB) | — | ~1 |
| Log Analytics (5 GB/mês ingest) | PerGB2018 | ~13 |
| App Insights (incluso no LAW) | — | 0 |
| Azure DNS (opcional) | — | ~0.5 |
| **TOTAL estimado** | | **≈ USD 121/mês** |

vs **v2.0 original ≈ USD 227/mês** — economia de **~47%** mantendo igual ou melhor capacidade efetiva.

---

## 8. 🗓 Plano de cutover do servidor antigo

| Dia | Ação |
|-----|------|
| **D-7** | Agente entrega `entrega_azure_maquina_v3.md` (formato §11 da solicitação original) com todos os T01-T27 verdes. Usuário valida acessos. |
| **D-3** | YOLO Orch builda imagens (`roleta-cloud`, `cdc-worker`) e faz push para ACR. Faz `alembic upgrade head` no PG novo. Sobe stack obs (`prometheus`, `grafana`, `alertmanager`, `node-exporter`, `pg-exporter`) na VM nova. |
| **D-1** | `pg_dump -Fc` do PG antigo (`/root/roleta-cloud/docker-compose.pg.yml` → `roleta-pg`) + restore no Flexible Server novo. Validar `feature_store`, `spins_vectors`, `outbox`. Replay de qualquer evento `failed`. |
| **D-0** | Atualizar DNS `ws.<DOMINIO>` para IP da VM nova. Monitorar 2h via Grafana + Alertmanager. Rollback = reverter DNS (TTL 60s). |
| **D+7** | Confirmado tudo saudável: agente externo desliga e remove `187.45.181.75`. Fim do billing HostDime. |

---

## 9. ✅ Definition of Done para o agente provisionador

- [ ] Itens A–I da §5 coletados antes de qualquer comando `az create`
- [ ] Todos os recursos da §3 criados com nomes e tags exatos
- [ ] PG Flexible Server com 7 extensions ativas (T07)
- [ ] PG sem IP público (T08)
- [ ] VM com `--admin-username azureuser` (AZ-BUG-01 corrigido) e SSH root habilitado por chave pós-boot (T22)
- [ ] data-root do Docker = `/mnt/docker` (sem rsync com Docker rodando — AZ-BUG-06 corrigido) (T17)
- [ ] MI da VM funcionando contra KV (T10, T21)
- [ ] 14 secrets do KV presentes (§4.2 + §4.6)
- [ ] ACR + Storage Account + Log Analytics + App Insights + OIDC Federation criados
- [ ] 4 Resource Locks `CanNotDelete` (T14)
- [ ] Cost alert ativo (T15-ish, §4.9)
- [ ] Cron de backup `state.json` (diário) e `pg_dump` (semanal) instalados + testados manualmente uma vez (§4.10)
- [ ] Cron de sync de `models/` ↔ Blob ativo (§4.11)
- [ ] Bateria T01–T27 verde (T28–T35 ficam para o YOLO Orch após deploy do código)
- [ ] Documento de entrega no formato §11 da solicitação v2.0 original, com nome `entrega_azure_maquina_v3.md`

---

## 10. 🔗 Referências cruzadas

- **Solicitação original v2.0 + A3:** `archive/sessoes/solicitação_de_estrutura_azure.md`
- **Estado live audit (containers, schemas, extensions):** `fine_tuning_25.md` + checkpoint 024
- **Plano de evolução estratégico:** `plano_implentacao_pos_sessao_24_05.md`
- **Auditoria CPU/RAM/CPU-flags HostDime:** resposta anterior nesta sessão (load=0.42, RAM 1.6/6.8 GB, CPU SEM SSE4.2/AVX2)
- **Razão arquitetural do upgrade:** `numpy 2.x`, `torch`, `faiss` e `sklearn ≥1.5` exigem AVX2 — bloqueio confirmado no PCA training desta sessão

---

*Versão 3.0 gerada pelo YOLO Orchestrator em 2026-05-25 02:40 UTC-3.*
*Hash da solicitação original auditada: `archive/sessoes/solicitação_de_estrutura_azure.md` (v2.0 final pós-A3).*

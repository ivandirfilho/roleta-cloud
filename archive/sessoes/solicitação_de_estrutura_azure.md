> ⚠️ **ATUALIZAÇÃO A3 (2026-05-24) — SUPERA decisão de "PG Flexible Server"**
>
> A auditoria A3 em `plano_implentacao_pos_sessao_24_05.md` identificou o **achado crítico B32**: **Apache AGE não está na allowlist de extensões do Azure PostgreSQL Flexible Server**. Como o roadmap depende de AGE (grafos por sentido, Sprint S8), a stack de banco **DEIXA de ser Flexible Server** e passa a ser:
>
> | Camada | DECISÃO ATUAL (A3) | (era na v1.0 deste doc) |
> |---|---|---|
> | Postgres | **Azure VM Standard_B4ms Ubuntu 22.04 brazilsouth + Docker Compose** (imagem custom PG15 + pgvector + AGE + TimescaleDB) | ~~PG Flexible Server B4ms~~ |
> | Imagem custom | **Azure Container Registry (ACR Basic)** | N/A |
> | Backup PITR | **WAL-G + Azure Blob Storage LRS** (RPO 5 min, RTO ~30 min) | ~~PITR nativo Flexible~~ |
> | Secrets | **Managed Identity da VM → Key Vault** | Mesma (Key Vault) |
> | Custo mensal | ~US$ 130 (VM) + US$ 19 (Premium SSD P10) + US$ 2 (Blob) ≈ **US$ 151/mês** | ~US$ 140 (Flexible) — diferença desprezível |
> | LGPD/região | brazilsouth (mantida) | brazilsouth (mantida) |
> | Patch PG | **Time (cron mensal, ~30 min)** | ~~Microsoft~~ |
> | App | Sem mudança no que está neste doc; latência real medida em **S-CUTOVER** (substitui Sx-LATENCY) | — |
>
> **As seções abaixo deste banner devem ser lidas como contexto histórico/parcial.** Os requisitos de **rede, RBAC, monitoramento, LGPD, domínios, certificados, observabilidade** permanecem válidos — só a escolha de produto-PG mudou. O agente provisionador deve seguir esta tabela acima como fonte da verdade para a camada de dados.
>
> Referência completa: `plano_implentacao_pos_sessao_24_05.md` seção **A3** (sprints S0.5, S-AGE-CHECK, S-CUTOVER novas; S4, S4-BAK, Sx-SEC reescritas; Sx-LATENCY depreciada).

---
# 📨 Solicitação de Provisionamento — Estrutura Azure + VM substituta para Roleta Cloud v5.0

**Documento de pedido formal para agente provisionador externo**
**Solicitante:** Ivandir Filho (`@ivandirfilho`)
**Orquestrador autor:** YOLO Orchestrator (Claude Opus 4.7) no PC do usuário
**Versão:** **2.0 (final, pós-auditoria cruzada)** — 2026-05-23 16:18 UTC-3
**Validade da solicitação:** 30 dias úteis
**Documentos de origem (auditoria cruzada):**
- `final_refatoracao_proposta.md` (v5.0 — 1010 LoC)
- `proposta_refatoracao_23_05.md` (4 tiers / 16 sprints)
- `auditoria_proposta_refatoracao_23_05.md` (11 blocos ISO 25010)
- `resultados_23_05.md` (auditoria estratégica + brave-search)
**MCPs usados:** sequential-thinking + filesystem + memory + graphify

---

## 🆕 CHANGELOG v1.0 → v2.0 (mudanças após auditoria cruzada com 4 documentos)

| # | Mudança | Justificativa (documento que motivou) |
|---|---|---|
| C1 | **Padronizar ACR (Azure Container Registry) — REMOVER referências a GHCR** | Consistência; ACR alinha com Managed Identity da VM e federação OIDC com GitHub |
| C2 | **+§16 Observability Stack completa** (docker-compose + datasources Grafana + dashboards JSON + Alertmanager Discord) | `auditoria_proposta §B6.1` + `final_refatoracao §0.4` pediram stack completa, v1.0 só mencionou portas |
| C3 | **+§17 Azure Storage Account** (Blob containers: models, backups, reports, golden-traces) | T3.2' Calibrator pickle precisa persistir; T1.2 vectorbt nightly gera HTML; backup state.json crítico |
| C4 | **+§18 App Insights wiring real** (connection string em KV + variável `APPLICATIONINSIGHTS_CONNECTION_STRING` no app) | v1.0 só listou recurso; faltava integração |
| C5 | **+§19 GitHub OIDC Federation** (substitui SP_CI long-lived secret) | Best practice — credenciais efêmeras 1h em vez de senha permanente |
| C6 | **+§20 Resource Locks** (CanNotDelete em RG, KV, PG, Storage) | Evita acidente catastrófico em prod |
| C7 | **+§21 Backup automático state.json** (cron daily → Blob backups/) | state.json contém timelines+martingale+perf — perda = warm-start de zero |
| C8 | **+§22 Snapshot Policy diária da VM** (Azure Backup Vault, retenção 30d) | DR e rollback fácil |
| C9 | **+§4.7 Particionamento pg_partman operacional** (parent template + retention) | `final_refatoracao §4.4` requer particionamento mensal de `decisions` |
| C10 | **+§7.6 CORS/origens Chrome extension** no Caddy | extension bate de origem `chrome-extension://...` — sem CORS, conexão WSS quebra |
| C11 | **+§23 Cost Management Alert** (USD 350/mês threshold) | Visibilidade de uso de crédito |
| C12 | **+§24 DR — Disaster Recovery Plan** (RTO/RPO + runbook) | Operação crítica precisa de plano formal |
| C13 | **Atualizar §6 KV secrets** (+8 novos: APP_INSIGHTS_CS, STORAGE_CONN, GH_OIDC_AUDIENCE, etc) | Decorrência de C2-C5 |
| C14 | **Atualizar §9 testes** com T32-T48 (16 novos testes p/ observability, blob, OIDC, locks, snapshot, backup state.json) | Cobertura de validação das novas seções |
| C15 | **Atualizar §11 template entrega** com seções 14-19 (observability, blob, app insights, OIDC, locks, DR) | Garantir que o agente reporte os novos itens |
| C16 | **Atualizar §13 Definition of Done** com 9 itens novos | Mesmo motivo |
| C17 | **+§4.8 Bankroll inicial parametrizado** (variável `INITIAL_BANKROLL_UNITS` em KV, default 1000) | T3.4 ¼-Kelly requer bankroll inicial registrado em `bankroll_events` |
| C18 | **+§5.7 Accelerated Networking explícito** no NIC da VM | D2as_v5 suporta; ganho de latência relevante para WSS |
| C19 | **+§4.9 Postgres Performance Recommendations Enabled** | Auto-tuning Azure |
| C20 | **+§14.1 Pre-cutover smoke test** (WSS handshake + auth + 1 decisão completa) | Reduz risco do cutover de produção |

---

## 0. Resumo executivo (para o agente provisionador)

Você foi designado **agente provisionador único** desta solicitação. Sua missão tem três pilares:

1. **Provisionar toda a estrutura Azure** descrita neste documento (Postgres, Key Vault, Monitor, Container Registry, DNS, etc).
2. **Provisionar uma nova VM Linux Debian 12** (substituindo o servidor atual da HostDime `187.45.181.75` que será descomissionado), com SSH root habilitado para o usuário e configurado para receber Docker + nossa stack.
3. **Configurar DNS + apontamentos + secrets + firewall** de modo que, ao final, exista um **README único de entrega** (formato definido na §11 deste documento) onde o YOLO Orchestrator possa acessar todas as credenciais e endpoints com um único `ssh`/`az login` e começar a deployar o código v5.0 sem nenhum trabalho de configuração manual adicional.

> ⚠️ **Restrições inegociáveis:**
> - O **YOLO Orchestrator é o operador root deste ambiente** — toda autenticação deve ser configurada para permitir acesso root SSH via chave do usuário Ivandir + `az login` por service principal entregue.
> - **Hardening do servidor está FORA DE ESCOPO** (será tratado em sessão posterior). Use defaults razoáveis (ufw básico, fail2ban opcional), mas não monte WAF, IDS, etc.
> - **Region única:** **Brazil South** (brazilsouth) para tudo, sem exceção, para latência mínima com a HostDime/usuário.
> - **Crédito disponível:** usuário tem créditos AWS + Azure + GCP **sem cap**. Otimize por confiabilidade e performance, não por custo.
> - **Substituição do servidor atual:** o `187.45.181.75` (HostDime, Debian) **será apagado** após a migração. A nova VM deve ser **funcionalmente equivalente ou superior** (especificada na §5).
> - **Não alterar nenhum código da aplicação** — você só provisiona infra e configurações. O deploy do código fica para o YOLO Orchestrator após receber o README de entrega.

---

## 1. Inventário atual (o que existe hoje — para você comparar)

### 1.1 Servidor a ser substituído
| Campo | Valor atual |
|---|---|
| Provedor | HostDime |
| IP | `187.45.181.75` |
| Acesso | SSH root (chave do Ivandir) |
| OS | Debian 12 (Bookworm) |
| Recursos estimados | ~2 vCPU, ~4 GB RAM, ~80 GB SSD |
| Workload rodando | Docker container `roleta-cloud` (Python 3.12, websockets, SQLite local) |
| Domínio apontando | (verificar — usuário tem domínios próprios; veja §7) |
| Portas em uso | 8765 (WSS interno, `127.0.0.1`), 22 (SSH), 80/443 (provavelmente proxy reverso) |
| Volumes Docker | `roleta-data` (named) + bind mount `state.json` |
| Status atual | EM PRODUÇÃO — não apagar até o dia D do cutover |

### 1.2 Stack atual em execução
```yaml
# docker-compose.yml atual (do projeto):
services:
  roleta-cloud:
    container_name: roleta-cloud
    ports: ["127.0.0.1:8765:8765"]   # WS interno (provavelmente atrás de Caddy/Nginx para WSS)
    volumes:
      - roleta-data:/app/data         # SQLite + logs
      - ./state.json:/app/state.json  # estado persistente
      - ./server/configs:/app/server/configs:ro
    env: WS_HOST, WS_PORT, SSL_ENABLED, ROLETA_API_KEY, AUTH_ENABLED
```

### 1.3 Repositório código
- **GitHub:** `github.com/ivandirfilho/roleta-cloud`
- **Branch padrão:** `main` (em breve com branch protection — Fase 0 do plano)
- **Linguagem:** Python 3.12

---

## 2. Visão alvo da infra (o que você vai entregar)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                            CLIENTE (Chrome Extension)                                │
└────────────────────────────────┬───────────────────────────────────────────────────┘
                                  │ wss://roleta.SEU-DOMINIO.com  (443/TCP, TLS managed)
                                  ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│                       AZURE — REGIÃO Brazil South (único Resource Group)             │
│                       Resource Group: rg-roleta-prod                                 │
│                                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────────┐      │
│   │  VM Linux  (vm-roleta-app-01)                                             │      │
│   │  Debian 12 — substitui o servidor HostDime                                │      │
│   │  Standard_D2as_v5 (2 vCPU, 8 GB, AMD)                                     │      │
│   │  OS disk: 128 GB Premium SSD P10                                          │      │
│   │  Data disk: 256 GB Premium SSD P15 (montado em /var/lib/docker)           │      │
│   │  IP público estático + DNS label                                          │      │
│   │  Docker Engine + docker-compose v2 pré-instalados                         │      │
│   │  Caddy reverse-proxy (TLS automático Let's Encrypt)                       │      │
│   │  Acesso SSH root via chave Ivandir + chave do agente provisionador        │      │
│   └────────────────────────────┬─────────────────────────────────────────────┘      │
│                                  │ pg_wire (5432, TLS, private endpoint)              │
│                                  ▼                                                    │
│   ┌──────────────────────────────────────────────────────────────────────────┐      │
│   │  Azure Database for PostgreSQL Flexible Server (pg-roleta-prod)           │      │
│   │  PostgreSQL 16  •  Burstable B2ms (2 vCPU, 8 GB)                          │      │
│   │  Storage: 128 GB Premium SSD (auto-grow ON, max 512 GB)                   │      │
│   │  Backup PITR 7 dias + LTR weekly                                          │      │
│   │  HA Disabled (Burstable não suporta — aceitável v5.0)                     │      │
│   │  Extensions habilitadas: PGMQ, VECTOR, PG_PARTMAN, PG_CRON, PGCRYPTO,    │      │
│   │                          PG_STAT_STATEMENTS                               │      │
│   │  Private Endpoint dentro da mesma VNet da VM                              │      │
│   └──────────────────────────────────────────────────────────────────────────┘      │
│                                                                                      │
│   ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────────────┐   │
│   │ Key Vault          │  │ Container Registry │  │ Log Analytics + Monitor    │   │
│   │ kv-roleta-prod     │  │ acrroletaprod      │  │ law-roleta-prod            │   │
│   │ - PG_PASSWORD      │  │ Basic SKU          │  │ Retenção 30d               │   │
│   │ - DEVICE_HMAC_KEY  │  │ Geo-replic Disabled│  │ Diagnostic settings em     │   │
│   │ - ROLETA_API_KEY   │  │                    │  │ TUDO (VM, PG, KV, ACR,     │   │
│   │ - JWT_PRIVATE_KEY  │  │                    │  │  Storage, AppInsights)     │   │
│   │ - CADDY_EMAIL      │  │                    │  │                            │   │
│   │ - GRAFANA_ADMIN_PW │  │                    │  │                            │   │
│   │ - STORAGE_CONN     │  │                    │  │                            │   │
│   │ - APPINS_CS        │  │                    │  │                            │   │
│   └────────────────────┘  └────────────────────┘  └────────────────────────────┘   │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐       │
│   │ DNS Zone (Azure DNS) — dns-roleta-prod                                   │       │
│   │ Zone: SEU-DOMINIO.com (delegada — ver §7)                                │       │
│   │ Records:                                                                  │       │
│   │   roleta      A      <IP público VM>                                     │       │
│   │   ws          CNAME  roleta.SEU-DOMINIO.com                              │       │
│   │   grafana     CNAME  roleta.SEU-DOMINIO.com                              │       │
│   │   pgadmin     CNAME  roleta.SEU-DOMINIO.com  (opcional)                  │       │
│   └─────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐       │
│   │ VNet roleta-vnet-prod (10.20.0.0/16)                                     │       │
│   │  - subnet-app   10.20.1.0/24  (VM)                                       │       │
│   │  - subnet-db    10.20.2.0/24  (Postgres delegated subnet)                │       │
│   │  - subnet-pe    10.20.3.0/24  (Private Endpoints futuros)                │       │
│   │ NSG: nsg-app-prod (permite 22 SSH, 80/443 HTTP, deny resto)              │       │
│   └─────────────────────────────────────────────────────────────────────────┘       │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Convenções de nomenclatura (use EXATAMENTE estes nomes)

| Recurso | Nome obrigatório |
|---|---|
| Resource Group | `rg-roleta-prod` |
| Region | `brazilsouth` |
| VNet | `roleta-vnet-prod` |
| Subnet app | `subnet-app` |
| Subnet db | `subnet-db` |
| Subnet PE | `subnet-pe` |
| NSG | `nsg-app-prod` |
| VM | `vm-roleta-app-01` |
| VM OS disk | `vm-roleta-app-01-osdisk` |
| VM data disk | `vm-roleta-app-01-data` |
| Public IP | `pip-roleta-app-01` (Static, Standard SKU) |
| DNS label público | `roleta-app-01` (FQDN: `roleta-app-01.brazilsouth.cloudapp.azure.com`) |
| Postgres server | `pg-roleta-prod` |
| Postgres admin | `roleta_admin` |
| Postgres DB inicial | `roleta` |
| Key Vault | `kv-roleta-prod` |
| Container Registry | `acrroletaprod` (sem hífen — limitação Azure) |
| Log Analytics WS | `law-roleta-prod` |
| App Insights | `ai-roleta-prod` |
| DNS Zone | `<SEU-DOMINIO>` (verificar com usuário — ver §7) |
| Service Principal p/ CI | `sp-roleta-ci` (role: AcrPush + Reader em rg) |
| Service Principal p/ Orch | `sp-roleta-orch` (role: Contributor em rg) |
| Managed Identity da VM | `mi-vm-roleta-app-01` (SystemAssigned, get/list em KV) |

**Tags obrigatórias em TODO recurso:**
```
project = roleta-cloud
env     = production
owner   = ivandirfilho
managed = yolo-orchestrator
costctr = roleta-v5
```

---

## 4. PostgreSQL — especificação detalhada

### 4.1 Provisionamento (comando `az` esperado)
```bash
az postgres flexible-server create \
  --resource-group rg-roleta-prod \
  --name pg-roleta-prod \
  --location brazilsouth \
  --tier Burstable --sku-name Standard_B2ms \
  --storage-size 128 --storage-auto-grow Enabled \
  --version 16 \
  --high-availability Disabled \
  --backup-retention 7 \
  --geo-redundant-backup Disabled \
  --admin-user roleta_admin \
  --admin-password "$(az keyvault secret show --vault-name kv-roleta-prod --name PG_PASSWORD --query value -o tsv)" \
  --vnet roleta-vnet-prod --subnet subnet-db --private-dns-zone privatelink.postgres.database.azure.com \
  --tags project=roleta-cloud env=production
```

### 4.2 Extensions OBRIGATÓRIAS habilitadas
```bash
az postgres flexible-server parameter set \
  --resource-group rg-roleta-prod --server-name pg-roleta-prod \
  --name azure.extensions \
  --value PGMQ,VECTOR,PG_PARTMAN,PG_CRON,PGCRYPTO,PG_STAT_STATEMENTS,UUID_OSSP
```

Após server up:
```sql
-- conectado como roleta_admin no DB 'postgres' (não 'roleta')
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS uuid-ossp;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;
CREATE EXTENSION IF NOT EXISTS pgmq;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- DB de aplicação
CREATE DATABASE roleta OWNER roleta_admin;
-- Conectado a 'roleta':
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;
CREATE EXTENSION IF NOT EXISTS pgmq;
CREATE EXTENSION IF NOT EXISTS vector;
```

### 4.3 Parâmetros de servidor (`az postgres flexible-server parameter set`)
| Parâmetro | Valor | Por que |
|---|---|---|
| `shared_preload_libraries` | `pg_stat_statements,pg_cron,pg_partman_bgw` | habilita workers |
| `pg_cron.database_name` | `roleta` | jobs cron no DB certo |
| `max_connections` | `200` | suficiente para app + ferramentas |
| `log_min_duration_statement` | `500` | log queries > 500ms |
| `idle_in_transaction_session_timeout` | `300000` | kill idle 5min |
| `statement_timeout` | `60000` | 60s |
| `timezone` | `America/Sao_Paulo` | logs em horário local |

### 4.4 Firewall + Rede
- **Conectividade obrigatória:** Private Access via VNet integration (`subnet-db` delegada para `Microsoft.DBforPostgreSQL/flexibleServers`).
- **NÃO expor IP público** do Postgres.
- Private DNS Zone `privatelink.postgres.database.azure.com` linkada à VNet.
- VM resolve `pg-roleta-prod.privatelink.postgres.database.azure.com` automaticamente.

### 4.5 Backup
- PITR 7 dias (Burstable max suportado)
- LTR (Long-Term Retention): semanal por 12 semanas
- Habilitar `geo_backup` se SKU permitir (Burstable não permite — OK)

### 4.6 Roles e usuários a criar (após server up)
```sql
-- Usuário da app com permissões mínimas
CREATE ROLE roleta_app LOGIN PASSWORD '<gerar e gravar em KV como PG_APP_PASSWORD>';
GRANT CONNECT ON DATABASE roleta TO roleta_app;
\c roleta
GRANT USAGE, CREATE ON SCHEMA public TO roleta_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO roleta_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO roleta_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO roleta_app;

-- Usuário readonly para Grafana
CREATE ROLE roleta_grafana LOGIN PASSWORD '<gerar e gravar em KV como PG_GRAFANA_PASSWORD>';
GRANT CONNECT ON DATABASE roleta TO roleta_grafana;
\c roleta
GRANT USAGE ON SCHEMA public TO roleta_grafana;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO roleta_grafana;
```

---

## 5. VM substituta — especificação detalhada

### 5.1 Provisionamento (`az vm create` esperado)
```bash
az vm create \
  --resource-group rg-roleta-prod \
  --name vm-roleta-app-01 \
  --location brazilsouth \
  --image Debian:debian-12:12:latest \
  --size Standard_D2as_v5 \
  --vnet-name roleta-vnet-prod --subnet subnet-app \
  --nsg nsg-app-prod \
  --public-ip-address pip-roleta-app-01 \
  --public-ip-sku Standard --public-ip-address-allocation static \
  --public-ip-address-dns-name roleta-app-01 \
  --admin-username root --generate-ssh-keys \
  --ssh-key-values @~/.ssh/ivandir_id_ed25519.pub @~/.ssh/orch_id_ed25519.pub \
  --os-disk-name vm-roleta-app-01-osdisk \
  --os-disk-size-gb 128 --storage-sku Premium_LRS \
  --data-disk-sizes-gb 256 \
  --assign-identity [system] \
  --tags project=roleta-cloud env=production
```

> 🔑 **Chaves SSH:** o agente DEVE adicionar **2 chaves públicas**:
> 1. Chave pública do Ivandir (solicitar — ver §10 item C)
> 2. Chave pública do próprio agente provisionador (deixar `authorized_keys` linhado para que YOLO Orch acesse via service principal + jump quando necessário)

### 5.2 Cloud-init / Script de inicialização (executar no first-boot)
Salvar como `cloud-init-vm.yaml` e passar via `--custom-data`:
```yaml
#cloud-config
package_update: true
package_upgrade: true
packages:
  - curl
  - git
  - htop
  - ufw
  - ca-certificates
  - gnupg
  - lsb-release
  - python3-pip
  - postgresql-client-16
runcmd:
  # Docker Engine + Compose v2 oficial
  - install -m 0755 -d /etc/apt/keyrings
  - curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  - chmod a+r /etc/apt/keyrings/docker.gpg
  - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
  - apt-get update
  - apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  - systemctl enable docker --now

  # Monta data disk em /var/lib/docker
  - mkfs.ext4 -F /dev/disk/azure/scsi1/lun0
  - mkdir -p /var/lib/docker_new
  - mount /dev/disk/azure/scsi1/lun0 /var/lib/docker_new
  - systemctl stop docker
  - rsync -aHAX /var/lib/docker/ /var/lib/docker_new/
  - rm -rf /var/lib/docker && mv /var/lib/docker_new /var/lib/docker
  - echo "/dev/disk/azure/scsi1/lun0 /var/lib/docker ext4 defaults,nofail 0 2" >> /etc/fstab
  - systemctl start docker

  # Caddy reverse proxy (TLS automático)
  - apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  - curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  - curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  - apt-get update
  - apt-get install -y caddy
  - systemctl enable caddy --now

  # Azure CLI (para a VM puxar secrets do KV via Managed Identity)
  - curl -sL https://aka.ms/InstallAzureCLIDeb | bash

  # Estrutura de diretórios da aplicação
  - mkdir -p /opt/roleta/{app,obs,backup}
  - chown -R root:root /opt/roleta

  # UFW básico (sem hardening — só portas necessárias)
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow 22/tcp
  - ufw allow 80/tcp
  - ufw allow 443/tcp
  - ufw --force enable

  # Time sync
  - timedatectl set-timezone America/Sao_Paulo
  - systemctl enable systemd-timesyncd --now

  # Log rotation Docker
  - |
    cat > /etc/docker/daemon.json <<EOF
    {
      "log-driver": "json-file",
      "log-opts": { "max-size": "100m", "max-file": "5" },
      "live-restore": true
    }
    EOF
  - systemctl restart docker

write_files:
  - path: /etc/caddy/Caddyfile
    permissions: "0644"
    content: |
      # Será preenchido pelo agente após confirmar domínio — placeholder por enquanto
      # ws.SEU-DOMINIO.com {
      #   reverse_proxy 127.0.0.1:8765
      # }
      # grafana.SEU-DOMINIO.com {
      #   reverse_proxy 127.0.0.1:3000
      # }
      :80 {
        respond "Roleta Cloud VM provisioned. Awaiting config." 200
      }
```

### 5.3 Managed Identity + permissões no Key Vault
```bash
# Pega principal ID da identidade do sistema da VM
PRINCIPAL_ID=$(az vm identity show -g rg-roleta-prod -n vm-roleta-app-01 --query principalId -o tsv)

# Concede get/list de secrets no KV
az keyvault set-policy --name kv-roleta-prod \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list
```

### 5.4 Validação pós-boot (script `check-vm.sh` que o agente roda via SSH)
```bash
#!/bin/bash
set -e
echo "=== VM Validation ==="
docker --version
docker compose version
caddy version
az --version | head -1
df -h /var/lib/docker
ufw status
systemctl is-active docker caddy
# Testa KV access via managed identity
az login --identity
az keyvault secret show --vault-name kv-roleta-prod --name PG_APP_PASSWORD --query value -o tsv | head -c 8
echo "...OK (truncated)"
# Testa conectividade Postgres
PGPASSWORD=$(az keyvault secret show --vault-name kv-roleta-prod --name PG_APP_PASSWORD --query value -o tsv) \
  psql "host=pg-roleta-prod.privatelink.postgres.database.azure.com user=roleta_app dbname=roleta sslmode=require" -c "SELECT version();"
echo "=== ALL OK ==="
```

---

## 6. Key Vault — secrets que você DEVE criar

| Nome do secret | Tipo | Como gerar | Quem usa |
|---|---|---|---|
| `PG_ADMIN_PASSWORD` | senha forte 32 chars | `openssl rand -base64 32` | provisioning Postgres |
| `PG_APP_PASSWORD` | senha forte 32 chars | `openssl rand -base64 32` | app Python (DSN) |
| `PG_GRAFANA_PASSWORD` | senha forte 32 chars | `openssl rand -base64 32` | Grafana datasource |
| `DEVICE_HMAC_KEY` | 64 hex chars | `openssl rand -hex 32` | auth/device_token.py |
| `ROLETA_API_KEY` | 64 hex chars | `openssl rand -hex 32` | auth middleware |
| `JWT_PRIVATE_KEY` | RSA 4096 PEM | `openssl genrsa 4096` | futuro JWT (TASK-003) |
| `JWT_PUBLIC_KEY` | RSA 4096 pub PEM | derivado | verificação JWT |
| `ACR_LOGIN_SERVER` | string | `acrroletaprod.azurecr.io` | deploy.yml + Docker login VM |
| `APP_INSIGHTS_CONNECTION_STRING` | string | `az monitor app-insights component show` | app Python instrumentação |
| `STORAGE_ACCOUNT_CONNECTION_STRING` | string | `az storage account show-connection-string -n stroletaprod -g rg-roleta-prod -o tsv` | app: backups + modelos ML + relatórios |
| `STORAGE_ACCOUNT_NAME` | string | `stroletaprod` | app + scripts backup |
| `DISCORD_WEBHOOK_URL` | URL | solicitar (§10 item J) ou criar default channel | Alertmanager + nightly backtest report |
| `INITIAL_BANKROLL_UNITS` | int (default 1000) | parametrizar | T3.4 ¼-Kelly seed bankroll_events |
| `BACKTEST_DB_READONLY_DSN` | DSN | derivado de PG_GRAFANA_PASSWORD | tools/backtest_vectorbt.py (nightly) |
| `CADDY_EMAIL` | email | solicitar (§10 item E) | Let's Encrypt account |
| `GRAFANA_ADMIN_PASSWORD` | senha forte 24 chars | `openssl rand -base64 24` | login Grafana |
| `ACR_USERNAME` | string | `acrroletaprod` | docker login no deploy |
| `ACR_PASSWORD` | senha do ACR | `az acr credential show` | docker login (fallback se MI falhar) |
| `AZURE_TENANT_ID` | UUID tenant | `az account show` | SP login |
| `AZURE_SUBSCRIPTION_ID` | UUID sub | `az account show` | SP scope |
| `SP_ORCH_CLIENT_ID` | UUID SP | criar SP `sp-roleta-orch` | login YOLO orch |
| `SP_ORCH_CLIENT_SECRET` | secret SP | criar | login YOLO orch |
| `GH_OIDC_AUDIENCE` | string | `api://AzureADTokenExchange` | GitHub Actions federation |
| `GH_REPO_FULL_NAME` | string | `ivandirfilho/roleta-cloud` | federation trust subject |

**Política de acesso ao KV:**
- `sp-roleta-orch` → Get, List, Set, Delete (secrets)
- `mi-vm-roleta-app-01` → Get, List (secrets)
- `sp-roleta-ci` → **DESCONTINUADO em v2.0 — use GitHub OIDC Federation (§19)** — apenas Get nos secrets `ACR_*` se federation falhar como fallback
- Ivandir (user principal) → Owner, All

---

## 7. DNS — verificação e configuração

### 7.1 Verificações que o agente DEVE fazer ANTES de tocar em DNS
1. Perguntar ao usuário (ou solicitar via §10 item F) **qual domínio será usado**. Exemplo: `roletacloud.com.br`, `ivandirfilho.dev`, etc.
2. Verificar onde o domínio está registrado hoje (registro.br, GoDaddy, Cloudflare, etc).
3. Verificar onde o DNS está hospedado hoje (provavelmente o registrador, ou Cloudflare).
4. Verificar TODOS os registros existentes hoje:
   ```bash
   dig +short SEU-DOMINIO ANY @8.8.8.8
   dig +short SEU-DOMINIO MX @8.8.8.8
   dig +short www.SEU-DOMINIO @8.8.8.8
   dig +short SEU-DOMINIO TXT @8.8.8.8   # SPF, DKIM, verifications
   ```
5. **NÃO MIGRAR DNS** sem confirmação explícita do usuário. Apenas **propor mudança** se necessária.

### 7.2 Estratégia recomendada (apresentar opções ao usuário)
**Opção A — Subdomínio dedicado (RECOMENDADO, baixo risco):**
- Manter DNS atual onde está
- Criar apenas registros para subdomínios:
  - `roleta.SEU-DOMINIO` → A → `<IP VM Azure>`
  - `ws.SEU-DOMINIO` → CNAME → `roleta.SEU-DOMINIO`
  - `grafana.SEU-DOMINIO` → CNAME → `roleta.SEU-DOMINIO`
- Caddy lida com TLS automático via Let's Encrypt HTTP-01 challenge

**Opção B — Delegar para Azure DNS (CONTROLE TOTAL, médio risco):**
- Criar Azure DNS Zone `SEU-DOMINIO`
- Trocar NS records no registrador para apontar Azure DNS
- Replicar TODOS os registros existentes (email, www, etc) antes do switch
- Permite automação completa via `az network dns record-set`

**Default:** Opção A. Só usar Opção B se usuário pedir explicitamente.

### 7.3 Records finais alvo
```
roleta    IN  A      <IP estático VM>      TTL 3600
ws        IN  CNAME  roleta.SEU-DOMINIO.   TTL 3600
api       IN  CNAME  roleta.SEU-DOMINIO.   TTL 3600
grafana   IN  CNAME  roleta.SEU-DOMINIO.   TTL 3600
metrics   IN  CNAME  roleta.SEU-DOMINIO.   TTL 3600  (interno, IP whitelist no Caddy)
```

### 7.4 Caddyfile final (agente preenche após confirmar domínio)
```
{
    email {$CADDY_EMAIL}
}

ws.SEU-DOMINIO {
    reverse_proxy 127.0.0.1:8765
    log {
        output file /var/log/caddy/ws.log
    }
}

grafana.SEU-DOMINIO {
    reverse_proxy 127.0.0.1:3000
    log {
        output file /var/log/caddy/grafana.log
    }
}

metrics.SEU-DOMINIO {
    @internal client_ip <IP_DO_IVANDIR>/32
    handle @internal {
        reverse_proxy 127.0.0.1:9090
    }
    respond 403
}
```

---

## 8. Service Principal `sp-roleta-orch` (acesso do YOLO Orchestrator)

### 8.1 Criação
```bash
az ad sp create-for-rbac \
  --name sp-roleta-orch \
  --role Contributor \
  --scopes /subscriptions/<SUB>/resourceGroups/rg-roleta-prod \
  --sdk-auth > sp-orch.json
```

### 8.2 Permissões
- `Contributor` em `rg-roleta-prod`
- `Key Vault Administrator` em `kv-roleta-prod`
- `AcrPush` e `AcrPull` em `acrroletaprod`

### 8.3 Como o YOLO Orchestrator vai usar (instruções para README de entrega)
```bash
# Login não-interativo no PC do Ivandir:
az login --service-principal \
  -u <SP_ORCH_CLIENT_ID> \
  -p <SP_ORCH_CLIENT_SECRET> \
  --tenant <AZURE_TENANT_ID>

# Listar recursos
az resource list -g rg-roleta-prod -o table

# Acessar VM
ssh root@roleta-app-01.brazilsouth.cloudapp.azure.com
# ou via IP
ssh root@<IP>

# Acessar KV
az keyvault secret show --vault-name kv-roleta-prod --name PG_APP_PASSWORD
```

---

## 9. Testes obrigatórios que o agente DEVE executar

Antes de entregar o README, o agente provisionador DEVE executar e gravar os resultados de **todos** os testes abaixo. Falha em qualquer um = re-trabalho antes da entrega.

### 9.1 Testes Azure
| # | Teste | Comando | Critério de OK |
|---|---|---|---|
| T01 | RG existe | `az group show -n rg-roleta-prod` | provisioningState = Succeeded |
| T02 | VNet + subnets | `az network vnet show -g rg-roleta-prod -n roleta-vnet-prod` | 3 subnets listadas |
| T03 | NSG aplicado | `az network nsg rule list -g rg-roleta-prod --nsg-name nsg-app-prod` | regras 22, 80, 443 presentes |
| T04 | Public IP estático | `az network public-ip show -g rg-roleta-prod -n pip-roleta-app-01` | sku=Standard, allocation=Static, FQDN set |
| T05 | VM running | `az vm get-instance-view -g rg-roleta-prod -n vm-roleta-app-01 --query "instanceView.statuses[?code=='PowerState/running']"` | retorna 1 item |
| T06 | Data disk montado | `ssh root@<IP> "df -h \| grep docker"` | linha mostrando ext4 256GB |
| T07 | Postgres up | `az postgres flexible-server show -g rg-roleta-prod -n pg-roleta-prod --query state` | "Ready" |
| T08 | Postgres extensions | conectar e `SELECT extname FROM pg_extension;` | inclui pgmq, vector, pg_partman, pg_cron, pgcrypto |
| T09 | Postgres private endpoint | `nslookup pg-roleta-prod.privatelink.postgres.database.azure.com` resolve 10.20.2.x | IP privado |
| T10 | KV acessível pela VM (MI) | `ssh root@<IP> "az login --identity && az keyvault secret show --vault-name kv-roleta-prod --name PG_APP_PASSWORD"` | retorna valor |
| T11 | ACR up | `az acr show -n acrroletaprod` | sku=Basic, adminEnabled=true |
| T12 | Log Analytics up | `az monitor log-analytics workspace show -g rg-roleta-prod -n law-roleta-prod` | provisioningState=Succeeded |

### 9.2 Testes na VM
| # | Teste | Comando (via SSH) | OK |
|---|---|---|---|
| T13 | Docker | `docker run --rm hello-world` | output "Hello from Docker!" |
| T14 | Docker Compose | `docker compose version` | v2.x.x |
| T15 | Caddy ativo | `systemctl is-active caddy` | active |
| T16 | UFW ativo | `ufw status` | Status: active, com 22/80/443 |
| T17 | Timezone | `date` | horário UTC-3 Brasília |
| T18 | Azure CLI | `az --version` | mostra version |
| T19 | MI funciona | `az login --identity && az account show` | retorna subscription |
| T20 | DNS app resolve | `nslookup pg-roleta-prod.privatelink.postgres.database.azure.com` | IP privado |
| T21 | Postgres alcançável | `pg_isready -h pg-roleta-prod.privatelink.postgres.database.azure.com -p 5432 -U roleta_app` | accepting connections |
| T22 | Postgres login app | `PGPASSWORD=$(az keyvault secret show ... PG_APP_PASSWORD ...) psql ... -c "SELECT 1;"` | retorna 1 |
| T23 | Internet outbound | `curl -s https://ifconfig.me` | retorna IP público da VM |
| T24 | ACR pull (MI da VM) | `az acr login -n acrroletaprod && docker pull acrroletaprod.azurecr.io/roleta-cloud:latest` (ou hello-world se vazio) | Login Succeeded |

### 9.3 Testes DNS (somente após aprovação Opção A ou B)
| # | Teste | Comando | OK |
|---|---|---|---|
| T25 | roleta.X resolve | `dig +short roleta.SEU-DOMINIO @1.1.1.1` | retorna IP da VM |
| T26 | TLS válido | `curl -I https://ws.SEU-DOMINIO` | HTTP/2 + Let's Encrypt cert |
| T27 | WSS handshake | `wscat -c wss://ws.SEU-DOMINIO/ -n` (após app deploy) | Connected |

### 9.4 Testes de segurança mínimos
| # | Teste | OK |
|---|---|---|
| T28 | Postgres NÃO tem IP público | `az postgres flexible-server show ...` → `publicNetworkAccess=Disabled` |
| T29 | Senhas no KV, NÃO em env vars do `az vm` | `az vm show ... --query osProfile.customData` não deve ter senhas plain |
| T30 | SSH password auth DISABLED | `grep PasswordAuthentication /etc/ssh/sshd_config` → `no` |
| T31 | SSH só com chaves de Ivandir+orch | `cat /root/.ssh/authorized_keys` → exatamente 2 linhas |

---

## 10. Informações que VOCÊ (agente provisionador) deve solicitar ao usuário ANTES de começar

Antes de tocar em qualquer recurso, abra **uma única conversa de coleta** com o usuário e peça:

| # | Item | Justificativa |
|---|---|---|
| A | **Subscription Azure ID** que tem os créditos | Para `--subscription` em todos os comandos |
| B | **Tenant ID** | Para SP login |
| C | **Chave SSH pública** do PC do Ivandir (`~/.ssh/id_*.pub`) | Acesso SSH dele à VM |
| D | **(REMOVIDO em v2.0)** ~~PAT GitHub para GHCR~~ — substituído por OIDC Federation (§19); coletar apenas **GitHub username** e **repo full name** (`ivandirfilho/roleta-cloud`) | Federation trust + workflow identity |
| E | **Email** para Let's Encrypt account (alertas de expiração de cert) | CADDY_EMAIL no KV |
| F | **Domínio** a ser usado (ex: `roletacloud.com.br`) e qual a **estratégia DNS** (Opção A ou B) | Configurar Caddy + DNS |
| G | **IP fixo do Ivandir** (para whitelist do endpoint `/metrics`) | NSG rule + Caddy matcher |
| H | **Confirmação** de que o servidor HostDime `187.45.181.75` pode ser apagado **D+7 após cutover** (grace period) | Cronograma cutover |
| I | (opcional) Preferência por **AZ adicional** (zone-redundant) ou single-zone | Default: single-zone para Burstable |
| J | **Discord webhook URL** para alertas Grafana/Alertmanager + relatório nightly backtest (se já tem; senão agente cria canal `#roleta-alerts`) | DISCORD_WEBHOOK_URL no KV |
| K | **GitHub username** + nome **exato do repo** (default: `ivandirfilho/roleta-cloud`) + branches que devem ter trust OIDC (default: `main` + tags `v*`) | §19 OIDC Federation |
| L | **Bankroll inicial** em units para seed da tabela `bankroll_events` (default: 1000) | INITIAL_BANKROLL_UNITS no KV |
| M | Lista de IPs/origens permitidas para WSS além da Chrome extension (ex: dashboard web próprio) | CORS no Caddy (§7.6) |
| N | Threshold em USD/mês para Cost Management Alert (default: 350) | §23 |

---

## 11. ⭐ FORMATO OBRIGATÓRIO DO DOCUMENTO DE ENTREGA

Ao terminar, o agente provisionador DEVE entregar **um único arquivo markdown** chamado:

**`entrega_azure_roleta_v5.md`** — colocado em `c:\Users\Windows\Desktop\Roleta Cloud\`

Estrutura obrigatória do arquivo (seções na ordem exata abaixo):

```markdown
# 🚀 Entrega — Infraestrutura Azure Roleta Cloud v5.0

**Data de entrega:** YYYY-MM-DD HH:MM UTC-3
**Agente provisionador:** <nome/handle>
**Status geral:** ✅ READY | ⚠️ PARCIAL | ❌ FAILED
**Solicitação atendida:** `solicitação_de_estrutura_azure.md` v1.0

## 1. Resumo executivo
- N recursos provisionados
- Custo mensal estimado: USD X
- Testes executados: N/M passaram
- Pendências: <lista ou "nenhuma">

## 2. Acessos rápidos (1 cmd cada)
### 2.1 Login Azure (YOLO Orchestrator)
```bash
az login --service-principal -u <CLIENT_ID> -p <senha> --tenant <TENANT_ID>
az account set --subscription <SUB_ID>
```

### 2.2 SSH na VM
```bash
ssh root@roleta-app-01.brazilsouth.cloudapp.azure.com
# IP estático: <X.X.X.X>
```

### 2.3 Postgres (via VM como jump host)
```bash
ssh root@<VM> "PGPASSWORD=\$(az keyvault secret show --vault-name kv-roleta-prod --name PG_APP_PASSWORD --query value -o tsv) psql -h pg-roleta-prod.privatelink.postgres.database.azure.com -U roleta_app -d roleta"
```

### 2.4 Key Vault
```bash
az keyvault secret list --vault-name kv-roleta-prod -o table
az keyvault secret show --vault-name kv-roleta-prod --name <NAME> --query value -o tsv
```

### 2.5 Grafana
- URL: https://grafana.<DOMINIO>
- User: admin
- Pass: (em KV → GRAFANA_ADMIN_PASSWORD)

## 3. Inventário de recursos (tabela completa)
| Tipo | Nome | Region | SKU | IP/FQDN | Status |
|---|---|---|---|---|---|
| ResourceGroup | rg-roleta-prod | brazilsouth | — | — | ✅ |
| VNet | roleta-vnet-prod | brazilsouth | — | 10.20.0.0/16 | ✅ |
| VM | vm-roleta-app-01 | brazilsouth | D2as_v5 | <IP>, roleta-app-01.brazilsouth.cloudapp.azure.com | ✅ |
| Postgres | pg-roleta-prod | brazilsouth | B2ms | pg-roleta-prod.privatelink... | ✅ |
| KeyVault | kv-roleta-prod | brazilsouth | Standard | kv-roleta-prod.vault.azure.net | ✅ |
| ACR | acrroletaprod | brazilsouth | Basic | acrroletaprod.azurecr.io | ✅ |
| LogAnalytics | law-roleta-prod | brazilsouth | PerGB2018 | — | ✅ |
| DNS Zone | <DOMINIO> | global | — | — | ✅/N/A |
| ... | ... | ... | ... | ... | ✅ |

## 4. Credenciais e Secrets criados (NUNCA exponha senhas — apenas nomes)
| Nome do secret no KV | Tipo | Rotação? |
|---|---|---|
| PG_ADMIN_PASSWORD | senha 32ch | manual |
| PG_APP_PASSWORD | senha 32ch | manual |
| ... | ... | ... |

## 5. DNS configurado
| Record | Type | Value | TTL |
|---|---|---|---|
| roleta.<DOMINIO> | A | <IP> | 3600 |
| ws.<DOMINIO> | CNAME | roleta.<DOMINIO> | 3600 |
| ... | ... | ... | ... |

## 6. Service Principals criados
### 6.1 sp-roleta-orch
- ClientID: <UUID>
- Tenant: <UUID>
- Senha: (em KV → SP_ORCH_CLIENT_SECRET)
- Permissões: Contributor em rg-roleta-prod, KV Admin em kv-roleta-prod, AcrPush+Pull em acrroletaprod

### 6.2 sp-roleta-ci
- ClientID: <UUID>
- Senha: (em KV → SP_CI_CLIENT_SECRET)
- Permissões: AcrPush, Reader em rg

## 7. Testes executados (T01 a T31)
| # | Teste | Status | Output (resumido) |
|---|---|:---:|---|
| T01 | RG existe | ✅ | provisioningState=Succeeded |
| T02 | VNet+subnets | ✅ | 3 subnets |
| ... | ... | ... | ... |
| T31 | SSH só chaves Ivandir+orch | ✅ | 2 entries |

**Tudo passou? SIM/NÃO**
Se não, lista de falhas + remediação proposta.

## 8. Caddy + DNS finais
- Caddyfile localizado em /etc/caddy/Caddyfile
- (anexar conteúdo completo)
- Certificados emitidos: ws.X (✅), grafana.X (✅)

## 9. Plano de cutover sugerido (do servidor HostDime → VM Azure)
- D-7: agente entrega esta documentação; usuário valida acessos
- D-3: YOLO Orchestrator faz deploy do código v5.0 (imagem Docker) na VM Azure em paralelo
- D-1: dump SQLite do container atual + restore no Postgres Azure (via `tools/migrate_sqlite_to_pg.py`)
- D-0 (cutover): mudar DNS `ws.<DOMINIO>` para nova VM, monitorar 2h
- D+7: apagar VM HostDime, finalizar billing

## 10. Custo estimado mensal
- VM D2as_v5: USD ~70
- OS disk P10 128GB: USD ~19
- Data disk P15 256GB: USD ~38
- Postgres B2ms: USD ~50
- Storage Postgres 128GB: USD ~13
- Public IP Standard: USD ~4
- Key Vault: USD ~3
- ACR Basic: USD ~5
- Log Analytics (10GB/mês): USD ~25
- **Total estimado: USD ~227/mês**
- Crédito disponível: SIM (Azure trial/MS)

## 11. Pendências e ações requeridas do usuário
- [ ] Confirmar domínio e estratégia DNS final (item F da §10)
- [ ] Apontar IP fixo para whitelist /metrics (item G)
- [ ] Confirmar autorização para descomissionar HostDime D+7
- [ ] Validar checklist da §2 (3 acessos rápidos funcionam?)

## 12. Anexos
### 12.1 sp-orch.json (criar arquivo local protegido)
(NÃO COMITAR — apenas referenciar onde está)

### 12.2 cloud-init final aplicado
(anexar conteúdo)

### 12.3 NSG rules
(listar)

### 12.4 Comandos `az` executados na ordem (audit trail)
```bash
# 1. Criar RG
az group create ...
# 2. Criar VNet
...
```

## 13. Próximos passos do YOLO Orchestrator
Após validar este documento:
1. Adicionar secrets em `github.com/ivandirfilho/roleta-cloud/settings/secrets/actions`:
   - AZURE_CREDENTIALS (conteúdo de sp-orch.json)
   - AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
   - ACR_LOGIN_SERVER, ACR_USERNAME, ACR_PASSWORD
2. Configurar `deploy.yml` (Fase 0 do plano de refatoração) para usar SP CI
3. Rodar migration Alembic v2.0 (Postgres baseline) na nova infra
4. Deploy do código v5.0 na VM (Fase 4.3 do plano)

---
*Gerado pelo agente provisionador <handle> em <data>. Hash do solicitação original: <SHA256 do solicitação_de_estrutura_azure.md>.*
```

---

## 12. Cronograma esperado de execução do agente provisionador

| Etapa | Duração estimada |
|---|---|
| Coleta de inputs do usuário (§10) | 30min |
| Provisionar RG + VNet + NSG + KV + Log Analytics + ACR | 30min |
| Provisionar Postgres + extensions + roles | 1h (PG demora ~15min para ficar Ready) |
| Provisionar VM + cloud-init + validações | 45min |
| DNS + Caddy + certificados Let's Encrypt | 30min |
| Service Principals + permissões | 20min |
| Bateria de testes T01-T31 + correções | 1h |
| Geração do `entrega_azure_roleta_v5.md` | 30min |
| **TOTAL esperado** | **~5h** (pode rodar overnight) |

---

## 13. Definition of Done — checklist final

Antes de entregar `entrega_azure_roleta_v5.md`, **todos** os itens abaixo devem estar marcados:

- [ ] Todos os recursos da §3 criados com nomes exatos
- [ ] Todas as tags da §3 aplicadas em todo recurso
- [ ] Postgres com 7 extensions habilitadas (§4.2)
- [ ] Postgres acessível APENAS via private endpoint (T28)
- [ ] VM com 2 chaves SSH autorizadas (Ivandir + orch), password auth disabled (T30, T31)
- [ ] Cloud-init aplicado com sucesso: Docker, Caddy, Az CLI, UFW (T13-T18)
- [ ] Data disk montado em `/var/lib/docker` (T06)
- [ ] Managed Identity da VM com acesso ao KV (T10, T19)
- [ ] Todos os 18 secrets da §6 presentes no KV
- [ ] 2 Service Principals criados com permissões corretas (§8)
- [ ] DNS configurado e TLS válido (T25, T26) **OU** documentado como pendente do usuário (§10 item F)
- [ ] Bateria T01-T31: 100% passou OU lista de falhas anexada
- [ ] `entrega_azure_roleta_v5.md` segue formato exato da §11
- [ ] `sp-orch.json` salvo em local seguro e referenciado no doc de entrega
- [ ] **(v2.0) Stack observabilidade up: Prometheus+Loki+Grafana+Alertmanager rodando, dashboards 8 painéis importados, Discord webhook testado (T32-T38)**
- [ ] **(v2.0) Azure Storage Account `stroletaprod` com 4 containers (`models`, `backups`, `reports`, `golden-traces`) + lifecycle policy (T39-T40)**
- [ ] **(v2.0) App Insights conectado e recebendo um trace de teste do app (T41)**
- [ ] **(v2.0) GitHub OIDC Federation configurada — workflow `deploy.yml` consegue `az login` sem secret (T42)**
- [ ] **(v2.0) Resource Locks `CanNotDelete` aplicados em rg/kv/pg/storage (T43)**
- [ ] **(v2.0) Cron de backup `state.json` testado: 1 execução manual gerou blob em `backups/state-YYYY-MM-DD.json` (T44)**
- [ ] **(v2.0) Snapshot policy diária da VM ativa em Azure Backup Vault (T45)**
- [ ] **(v2.0) pg_partman parent template criado para `decisions` particionada por mês (T46)**
- [ ] **(v2.0) Cost Management Alert USD <threshold>/mês ativo (T47)**
- [ ] **(v2.0) Smoke test pré-cutover documentado e aprovado pelo orquestrador (T48 + §24.1)**

---

# 🆕 SEÇÕES ADICIONADAS NA v2.0 (auditoria cruzada)

## 16. Observability Stack na VM — Prometheus + Loki + Grafana + Alertmanager

### 16.1 Provisionamento via docker-compose
Salvar em `/opt/roleta/obs/docker-compose.yml` na VM (o agente cria estrutura, mas **não sobe** — esse passo fica para o YOLO Orchestrator no deploy do app na Fase 0.4):

```yaml
version: "3.8"
networks:
  obs-net:
    driver: bridge
volumes:
  prom-data: {}
  loki-data: {}
  grafana-data: {}
  alert-data: {}
services:
  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: prometheus
    restart: unless-stopped
    user: "65534:65534"
    ports: ["127.0.0.1:9090:9090"]
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./alert-rules.yml:/etc/prometheus/alert-rules.yml:ro
      - prom-data:/prometheus
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=60d"
      - "--storage.tsdb.retention.size=10GB"
      - "--web.enable-lifecycle"
    networks: [obs-net]
  loki:
    image: grafana/loki:3.0.0
    container_name: loki
    restart: unless-stopped
    ports: ["127.0.0.1:3100:3100"]
    volumes:
      - ./loki-config.yml:/etc/loki/local-config.yaml:ro
      - loki-data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    networks: [obs-net]
  promtail:
    image: grafana/promtail:3.0.0
    container_name: promtail
    restart: unless-stopped
    volumes:
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - ./promtail-config.yml:/etc/promtail/config.yml:ro
    command: -config.file=/etc/promtail/config.yml
    networks: [obs-net]
  grafana:
    image: grafana/grafana:11.1.0
    container_name: grafana
    restart: unless-stopped
    ports: ["127.0.0.1:3000:3000"]
    environment:
      - GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_pw
      - GF_INSTALL_PLUGINS=grafana-piechart-panel,grafana-clock-panel
      - GF_SERVER_ROOT_URL=https://grafana.SEU-DOMINIO
      - GF_AUTH_ANONYMOUS_ENABLED=false
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana-provisioning:/etc/grafana/provisioning
    secrets: [grafana_pw]
    networks: [obs-net]
  alertmanager:
    image: prom/alertmanager:v0.27.0
    container_name: alertmanager
    restart: unless-stopped
    ports: ["127.0.0.1:9093:9093"]
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alert-data:/alertmanager
    networks: [obs-net]
secrets:
  grafana_pw:
    file: ./grafana_pw.txt
```

### 16.2 Arquivos de config que o agente DEVE criar (estrutura pronta, sem secrets concretos)

**`/opt/roleta/obs/prometheus.yml`**
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
rule_files: [alert-rules.yml]
alerting:
  alertmanagers:
    - static_configs: [{ targets: ["alertmanager:9093"] }]
scrape_configs:
  - job_name: roleta-cloud
    static_configs: [{ targets: ["host.docker.internal:9000"] }]   # exposed by app
  - job_name: caddy
    static_configs: [{ targets: ["host.docker.internal:2019"] }]   # Caddy admin
  - job_name: node
    static_configs: [{ targets: ["host.docker.internal:9100"] }]   # node_exporter (opcional)
  - job_name: postgres
    static_configs: [{ targets: ["host.docker.internal:9187"] }]   # pg_exporter (opcional)
```

**`/opt/roleta/obs/alert-rules.yml`**
```yaml
groups:
  - name: roleta-strategy
    interval: 30s
    rules:
      - alert: HitRateCWLow
        expr: roleta_hit_rate{direction="cw",window="60"} < 0.40
        for: 30m
        labels: { severity: warning, direction: cw }
        annotations:
          summary: "Hit rate CW abaixo de 40% por 30min"
          description: "Direção CW está com {{ $value | humanizePercentage }} (target ≥ 47.2% break-even 17 nums)"
      - alert: HitRateCWCritical
        expr: roleta_hit_rate{direction="cw",window="60"} < 0.35
        for: 1h
        labels: { severity: critical, direction: cw }
      - alert: HitRateCCWLow
        expr: roleta_hit_rate{direction="ccw",window="60"} < 0.40
        for: 30m
        labels: { severity: warning, direction: ccw }
      - alert: DriftSurge
        expr: rate(roleta_adwin_drifts_total[5m]) > 0.6
        for: 5m
        labels: { severity: info }
        annotations: { summary: "ADWIN detectou drift surge — possível regime change" }
      - alert: MartingaleHighLevel
        expr: roleta_martingale_level > 5
        for: 1m
        labels: { severity: critical }
      - alert: BankrollDrawdown
        expr: roleta_bankroll_units < 500   # 50% do default 1000
        for: 1m
        labels: { severity: critical }
      - alert: SpinLatencyP99
        expr: histogram_quantile(0.99, rate(roleta_spin_latency_ms_bucket[5m])) > 100
        for: 10m
        labels: { severity: warning }
  - name: infra
    rules:
      - alert: AppDown
        expr: up{job="roleta-cloud"} == 0
        for: 2m
        labels: { severity: critical }
      - alert: DiskFull
        expr: node_filesystem_avail_bytes{mountpoint="/var/lib/docker"} / node_filesystem_size_bytes{mountpoint="/var/lib/docker"} < 0.10
        for: 10m
        labels: { severity: critical }
```

**`/opt/roleta/obs/alertmanager.yml`**
```yaml
route:
  receiver: discord-default
  group_by: [alertname, severity]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers: [severity="critical"]
      receiver: discord-critical
      repeat_interval: 30m
receivers:
  - name: discord-default
    discord_configs:
      - webhook_url_file: /etc/alertmanager/discord_webhook_url
        title: "🟡 Roleta Cloud — {{ .GroupLabels.alertname }}"
  - name: discord-critical
    discord_configs:
      - webhook_url_file: /etc/alertmanager/discord_webhook_url
        title: "🔴 CRÍTICO — {{ .GroupLabels.alertname }}"
```
- Webhook real é injetado em runtime via `docker secret` ou bind mount de arquivo gerado a partir do KV (`DISCORD_WEBHOOK_URL`)

**`/opt/roleta/obs/loki-config.yml`** — config padrão single-binary; retenção 30d.
**`/opt/roleta/obs/promtail-config.yml`** — coleta `/var/lib/docker/containers/*/*-json.log` com labels `container_name`, `compose_project`.

**`/opt/roleta/obs/grafana-provisioning/datasources/datasources.yml`**
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
  - name: Loki
    type: loki
    url: http://loki:3100
  - name: PostgresReadOnly
    type: postgres
    url: pg-roleta-prod.privatelink.postgres.database.azure.com:5432
    database: roleta
    user: roleta_grafana
    secureJsonData:
      password: $PG_GRAFANA_PASSWORD   # injetado via env
    jsonData:
      sslmode: require
      postgresVersion: 1600
```

**`/opt/roleta/obs/grafana-provisioning/dashboards/dashboards.yml`** + arquivos JSON dos 8 dashboards (agente cria stubs vazios; o YOLO Orchestrator preenche no Fase 0.4 com painéis reais):
1. `01-hit-rate-by-direction.json` (CW vs CCW rolling 30/60/100)
2. `02-sigmoid-offsets.json` (off2/off3 por direção, evolução)
3. `03-adwin-drifts.json`
4. `04-spin-latency.json`
5. `05-martingale-bankroll.json`
6. `06-score-distribution.json`
7. `07-action-distribution.json` (APOSTAR/ESPERAR/MONITORAR por direção)
8. `08-shadow-vs-prod.json` (comparação shadow runner — pós T2.2)

### 16.3 Caddy routes para observability (apenas IP whitelist Ivandir)
Append no Caddyfile (§7.4):
```
grafana.SEU-DOMINIO {
    @ivandir client_ip {$IVANDIR_IP}/32
    handle @ivandir { reverse_proxy 127.0.0.1:3000 }
    respond 403
}
prom.SEU-DOMINIO {
    @ivandir client_ip {$IVANDIR_IP}/32
    handle @ivandir { reverse_proxy 127.0.0.1:9090 }
    respond 403
}
alerts.SEU-DOMINIO {
    @ivandir client_ip {$IVANDIR_IP}/32
    handle @ivandir { reverse_proxy 127.0.0.1:9093 }
    respond 403
}
```

---

## 17. Azure Storage Account — `stroletaprod`

### 17.1 Provisionamento
```bash
az storage account create \
  --resource-group rg-roleta-prod \
  --name stroletaprod \
  --location brazilsouth \
  --sku Standard_LRS \
  --kind StorageV2 \
  --access-tier Hot \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2 \
  --default-action Deny \
  --bypass AzureServices

# Liberar acesso da VM via service endpoint + Ivandir IP
az storage account network-rule add -g rg-roleta-prod --account-name stroletaprod \
  --vnet-name roleta-vnet-prod --subnet subnet-app
az storage account network-rule add -g rg-roleta-prod --account-name stroletaprod \
  --ip-address <IVANDIR_IP>
```

### 17.2 Containers a criar
| Container | Lifecycle | Acesso | Uso |
|---|---|---|---|
| `models` | Hot por 90d → Cool | Private | Calibrator pickles `cw_model_YYYYMMDD.pkl`, `ccw_model_YYYYMMDD.pkl` (T3.2') |
| `backups` | Hot por 30d → Cool 90d → Archive 365d | Private | `state-YYYY-MM-DD.json` daily backup |
| `reports` | Hot por 30d → Cool | Private | `backtest_vectorbt_YYYY-MM-DD.html` (T1.2 nightly) |
| `golden-traces` | Hot por 180d | Private | 100 traces JSON para refactor regression (B4) |
| `pg-backups-export` | Archive imediato | Private | `pg_dump` semanais (cron pg_cron) |

### 17.3 Lifecycle policy (JSON)
```json
{
  "rules": [
    {
      "name": "tiering-default",
      "enabled": true,
      "type": "Lifecycle",
      "definition": {
        "filters": { "blobTypes": ["blockBlob"] },
        "actions": {
          "baseBlob": {
            "tierToCool":    { "daysAfterModificationGreaterThan": 30 },
            "tierToArchive": { "daysAfterModificationGreaterThan": 180 },
            "delete":        { "daysAfterModificationGreaterThan": 730 }
          }
        }
      }
    }
  ]
}
```

### 17.4 SAS tokens / Managed Identity
- VM acessa via Managed Identity (`mi-vm-roleta-app-01` recebe `Storage Blob Data Contributor` em `stroletaprod`)
- Sem SAS tokens long-lived; uso de `azcopy` com `--auth-mode login` quando necessário

---

## 18. Application Insights wiring real

### 18.1 Provisionamento
```bash
az monitor app-insights component create \
  -g rg-roleta-prod -a ai-roleta-prod -l brazilsouth \
  --workspace law-roleta-prod \
  --application-type web

CS=$(az monitor app-insights component show -g rg-roleta-prod -a ai-roleta-prod --query connectionString -o tsv)
az keyvault secret set --vault-name kv-roleta-prod --name APP_INSIGHTS_CONNECTION_STRING --value "$CS"
```

### 18.2 Instrumentação esperada (o app Python vai consumir — fora do escopo do agente, apenas garantir o secret)
- `pip install opencensus-ext-azure opentelemetry-azure-monitor-exporter`
- Variável `APPLICATIONINSIGHTS_CONNECTION_STRING` injetada via `docker run --env-file <(az keyvault secret show ...)`.

### 18.3 Test de smoke do agente
```bash
# Envia 1 trace dummy via REST API para validar pipeline
curl -X POST "https://brazilsouth-1.in.applicationinsights.azure.com/v2/track" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Microsoft.ApplicationInsights.Event\",\"time\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"iKey\":\"$IKEY\",\"data\":{\"baseType\":\"EventData\",\"baseData\":{\"name\":\"provisioning-smoke-test\"}}}"
# Aguarda 5min, valida no portal Azure ou via:
az monitor app-insights events show -g rg-roleta-prod -a ai-roleta-prod --type events --start-time "$(date -u -d '10 min ago' +%Y-%m-%dT%H:%M:%SZ)"
```

---

## 19. GitHub OIDC Federation (substitui SP_CI long-lived)

### 19.1 Criar SP federado SEM senha
```bash
az ad app create --display-name sp-roleta-gh-deploy
APP_ID=$(az ad app list --display-name sp-roleta-gh-deploy --query "[0].appId" -o tsv)
az ad sp create --id $APP_ID
SP_OID=$(az ad sp show --id $APP_ID --query id -o tsv)

# Role: contributor no RG + AcrPush
az role assignment create --role Contributor \
  --assignee-object-id $SP_OID --assignee-principal-type ServicePrincipal \
  --scope /subscriptions/<SUB>/resourceGroups/rg-roleta-prod
az role assignment create --role AcrPush \
  --assignee-object-id $SP_OID --assignee-principal-type ServicePrincipal \
  --scope /subscriptions/<SUB>/resourceGroups/rg-roleta-prod/providers/Microsoft.ContainerRegistry/registries/acrroletaprod
```

### 19.2 Federated credentials (3 trusts: branch main + tags v* + pull_request)
```bash
for sub in \
  "repo:ivandirfilho/roleta-cloud:ref:refs/heads/main" \
  "repo:ivandirfilho/roleta-cloud:ref:refs/tags/v*" \
  "repo:ivandirfilho/roleta-cloud:environment:production"
do
  az ad app federated-credential create --id $APP_ID --parameters "{
    \"name\": \"gh-${sub//[^a-zA-Z0-9]/_}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$sub\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }"
done
```

### 19.3 GitHub Actions secrets necessários (o agente fornece valores no doc de entrega — Ivandir adiciona em `Settings → Secrets`):
| Nome | Valor |
|---|---|
| `AZURE_CLIENT_ID` | $APP_ID acima |
| `AZURE_TENANT_ID` | tenant |
| `AZURE_SUBSCRIPTION_ID` | sub |
| `ACR_LOGIN_SERVER` | `acrroletaprod.azurecr.io` |
| `VM_HOST` | IP/FQDN VM |
| `VM_SSH_PRIVATE_KEY` | chave SSH dedicada para CI (gerada pelo agente, par adicionada em `authorized_keys` da VM) |

### 19.4 Workflow exemplar (`.github/workflows/deploy.yml`)
```yaml
permissions:
  id-token: write   # necessário para OIDC
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: az acr login -n acrroletaprod
      - run: docker buildx build --push -t acrroletaprod.azurecr.io/roleta-cloud:${{ github.sha }} -t acrroletaprod.azurecr.io/roleta-cloud:latest .
      - name: Deploy SSH
        run: ssh -o StrictHostKeyChecking=no root@${{ secrets.VM_HOST }} "cd /opt/roleta/app && docker compose pull && docker compose up -d && docker image prune -f"
```

---

## 20. Resource Locks (proteção anti-acidente)

```bash
for r in rg-roleta-prod; do
  az lock create --name dont-delete-rg --resource-group $r --lock-type CanNotDelete \
    --notes "v5.0 prod — proteção"
done
az lock create --name dont-delete-kv --resource-group rg-roleta-prod \
  --resource kv-roleta-prod --resource-type Microsoft.KeyVault/vaults --lock-type CanNotDelete
az lock create --name dont-delete-pg --resource-group rg-roleta-prod \
  --resource pg-roleta-prod --resource-type Microsoft.DBforPostgreSQL/flexibleServers --lock-type CanNotDelete
az lock create --name dont-delete-storage --resource-group rg-roleta-prod \
  --resource stroletaprod --resource-type Microsoft.Storage/storageAccounts --lock-type CanNotDelete
```

> ⚠️ Locks devem ser **removidos manualmente** antes de qualquer `az resource delete` futuro. Documentar isso no README de entrega.

---

## 21. Backup automático de `state.json` (cron daily → Blob)

### 21.1 Script `/opt/roleta/backup/state_backup.sh` (criar via cloud-init ou pós-boot)
```bash
#!/bin/bash
set -e
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
SRC=/opt/roleta/app/state.json
DEST=backups/state-${TS}.json
[ -f "$SRC" ] || { echo "state.json não existe ainda — skip"; exit 0; }
az login --identity > /dev/null
az storage blob upload \
  --auth-mode login \
  --account-name stroletaprod \
  --container-name backups \
  --name "$DEST" \
  --file "$SRC" \
  --overwrite false
echo "[$(date -u)] OK uploaded $DEST"
```

### 21.2 Crontab (root)
```cron
0 3 * * *  /opt/roleta/backup/state_backup.sh >> /var/log/roleta-backup.log 2>&1
0 */6 * * * /opt/roleta/backup/state_backup.sh >> /var/log/roleta-backup.log 2>&1
```
(3h UTC diário + a cada 6h — overkill aceito, dado tamanho pequeno do state.json ~50KB)

### 21.3 Test do agente
```bash
ssh root@<VM> "touch /opt/roleta/app/state.json && /opt/roleta/backup/state_backup.sh"
az storage blob list --auth-mode login --account-name stroletaprod -c backups -o table | grep state-
```

---

## 22. Snapshot Policy diária da VM

### 22.1 Azure Backup Vault
```bash
az backup vault create -g rg-roleta-prod -n bv-roleta-prod -l brazilsouth
az backup vault backup-properties set -g rg-roleta-prod -n bv-roleta-prod --backup-storage-redundancy LocallyRedundant

# Policy: daily 03:00 UTC, retenção 30 dias
az backup policy create -g rg-roleta-prod -v bv-roleta-prod -n daily-30d \
  --backup-management-type AzureIaasVM --policy '{...JSON policy daily 30d...}'

# Habilitar backup da VM
az backup protection enable-for-vm -g rg-roleta-prod -v bv-roleta-prod \
  --vm vm-roleta-app-01 --policy-name daily-30d
```

### 22.2 Test do agente
```bash
az backup item list -g rg-roleta-prod -v bv-roleta-prod \
  --backup-management-type AzureIaasVM -o table
# Deve mostrar vm-roleta-app-01 com policy daily-30d
```

---

## 23. Cost Management Alert

```bash
THRESHOLD=${1:-350}  # USD/mês, default 350; ajustável via §10 item N
SUB=$(az account show --query id -o tsv)
az consumption budget create \
  --budget-name budget-roleta-prod \
  --amount $THRESHOLD \
  --time-grain Monthly \
  --time-period start-date=$(date +%Y-%m-01) \
  --category Cost \
  --notifications 80_percent_threshold='{
    "enabled": true,
    "operator": "GreaterThan",
    "threshold": 80,
    "contactEmails": ["ivandir@email.example"],
    "thresholdType": "Actual"
  }' \
  --notifications 100_percent_threshold='{
    "enabled": true,
    "operator": "GreaterThan",
    "threshold": 100,
    "contactEmails": ["ivandir@email.example"]
  }' \
  --resource-group-filter rg-roleta-prod
```

---

## 24. Disaster Recovery Plan (RTO/RPO + runbook)

### 24.1 Pre-cutover smoke test (OBRIGATÓRIO antes do D-0 da migração)
Sequência exata que o agente provisionador deve executar **antes de declarar entrega** e que o YOLO Orchestrator vai re-executar antes do cutover:

```bash
# 1. WSS handshake (após app deploy — fora do agente; mas estrutura validada)
wscat -c wss://ws.SEU-DOMINIO/ -n
# Esperado: Connected; envia: {"type":"ping"}; recebe: {"type":"pong"}

# 2. Auth flow
curl -X POST https://api.SEU-DOMINIO/auth/device \
  -H "Content-Type: application/json" \
  -d '{"device_id":"smoke-test"}'
# Esperado: 200 + token HMAC válido

# 3. Decisão completa (após app deploy)
# Envia spin via WSS, recebe SuggestionOutput em <100ms, verifica grava em decisions

# 4. Métricas Prometheus
curl -s https://metrics.SEU-DOMINIO/metrics | grep roleta_decisions_total
```

### 24.2 RTO / RPO targets
| Cenário | RTO | RPO | Procedimento |
|---|:---:|:---:|---|
| App crash (Docker container) | 30s | 0 | `docker restart roleta-cloud` + healthcheck retoma |
| VM crash (cold) | 5min | 6h (state.json) | Azure Backup restore último snapshot |
| VM perda total | 15min | 6h | Recriar via Bicep (anexar §24.5) + restore snapshot |
| Postgres perda dado | <1min | 5min (PITR) | `az postgres flexible-server restore` |
| Postgres região perdida | 30min | 24h (LTR) | restore LTR em região secundária (delivery futura) |
| Region perda total (brazilsouth) | 4h | 24h | failover manual para `eastus` (DR-2026 plano separado) |

### 24.3 Runbook em 1 página (entregar como anexo no doc final)
Estrutura:
1. **Sintoma observado** → 2. **Métrica/log que confirma** → 3. **Comando de mitigação** → 4. **Verificação pós** → 5. **Quem notificar**

Exemplo (a ser preenchido no doc de entrega):
- *App não responde WSS*: `curl https://ws.X/healthz` retorna 502 → `ssh root@VM "docker compose -f /opt/roleta/app/docker-compose.yml restart roleta-cloud"` → re-curl 200 → notificar Ivandir Discord

### 24.4 Bicep IaC (entrega como anexo)
Agente DEVE entregar arquivo `infrastructure/main.bicep` capaz de re-provisionar TUDO em outra subscription/região com:
```bash
az deployment group create -g rg-roleta-dr -f main.bicep --parameters @main.bicepparam
```

---

## 25. Particionamento pg_partman operacional (detalhes para §4)

Após `CREATE EXTENSION pg_partman` (já em §4.2), o agente DEVE rodar:
```sql
-- 1. Parent table como partitioned
CREATE TABLE public.decisions (
    id BIGSERIAL,
    spin_id BIGINT NOT NULL,
    spin_direction TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- ... resto das 27 colunas (schema vem do Alembic baseline; aqui só estrutura partitioned)
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

-- 2. Configurar particionamento mensal
SELECT partman.create_parent(
  p_parent_table => 'public.decisions',
  p_control => 'ts',
  p_type => 'range',
  p_interval => '1 month',
  p_premake => 6   -- pré-cria 6 meses adiantado
);

-- 3. Retention: drop partições > 12 meses
UPDATE partman.part_config
SET retention = '12 months', retention_keep_table = false
WHERE parent_table = 'public.decisions';

-- 4. Job cron mensal de manutenção
SELECT cron.schedule('partman_maintenance', '0 4 1 * *',
  $$CALL partman.run_maintenance_proc()$$);
```

> ⚠️ **Importante:** O Alembic baseline (Fase 0.3 do `final_refatoracao_proposta.md`) precisa estar ciente da estrutura particionada. O agente DEVE entregar o DDL acima como **anexo `partition-setup.sql`** para que o YOLO Orchestrator aplique na ordem certa (baseline → partition setup → migrations subsequentes).

---

## 26. Accelerated Networking + Performance recommendations Postgres

### 26.1 VM NIC
```bash
NIC=$(az vm show -g rg-roleta-prod -n vm-roleta-app-01 --query "networkProfile.networkInterfaces[0].id" -o tsv | xargs basename)
az network nic update -g rg-roleta-prod -n $NIC --accelerated-networking true
```

### 26.2 Postgres
```bash
az postgres flexible-server parameter set \
  -g rg-roleta-prod -s pg-roleta-prod \
  --name pg_qs.query_capture_mode --value all
# Habilitar Performance Recommendations no portal Azure (manual ou via REST)
```

---

## 27. Testes ADICIONAIS v2.0 (T32-T48)

| # | Teste | Comando | OK |
|---|---|---|---|
| T32 | Storage account up | `az storage account show -n stroletaprod -g rg-roleta-prod --query provisioningState` | Succeeded |
| T33 | 4 containers existem | `az storage container list --account-name stroletaprod --auth-mode login -o table` | models, backups, reports, golden-traces |
| T34 | Lifecycle policy ativa | `az storage account management-policy show --account-name stroletaprod -g rg-roleta-prod` | retorna rules |
| T35 | App Insights up | `az monitor app-insights component show -g rg-roleta-prod -a ai-roleta-prod` | provisioningState=Succeeded |
| T36 | App Insights smoke trace | (§18.3) | evento visível em <10min |
| T37 | Grafana up | `ssh root@VM "docker compose -f /opt/roleta/obs/docker-compose.yml ps grafana"` | running |
| T38 | Grafana datasources provisionados | `curl -u admin:$PW http://localhost:3000/api/datasources` (via ssh) | 3 datasources |
| T39 | Discord webhook OK | `curl -X POST $DISCORD_WEBHOOK_URL -d '{"content":"provisioning smoke test"}'` | 204 No Content |
| T40 | Resource Lock RG | `az lock list -g rg-roleta-prod -o table` | dont-delete-rg listado |
| T41 | Resource Lock KV/PG/Storage | mesmo cmd | 4 locks total |
| T42 | GitHub OIDC trust | `az ad app federated-credential list --id $APP_ID -o table` | 3 entries (main, tags, env=production) |
| T43 | Cost budget ativo | `az consumption budget list --resource-group rg-roleta-prod -o table` | budget-roleta-prod listado |
| T44 | Snapshot policy VM | `az backup item list -g rg-roleta-prod -v bv-roleta-prod -o table` | vm-roleta-app-01 com policy daily-30d |
| T45 | state.json backup smoke | `ssh root@VM "touch /opt/roleta/app/state.json && /opt/roleta/backup/state_backup.sh"` + list blob | blob criado |
| T46 | pg_partman setup | `psql -c "SELECT parent_table FROM partman.part_config"` | public.decisions listado |
| T47 | Accelerated Networking VM | `az network nic show -g rg-roleta-prod -n $NIC --query enableAcceleratedNetworking` | true |
| T48 | Pre-cutover smoke (§24.1, parcial — sem app) | TLS+DNS+Caddy responde 200 em `/` | OK |

---

## 28. Atualizações ao template de entrega §11

O agente DEVE adicionar as seguintes seções ao `entrega_azure_roleta_v5.md`:

```markdown
## 14. Observability Stack (v2.0)
- Prometheus URL (interno): http://127.0.0.1:9090 (VPN/IP-whitelist via Caddy)
- Grafana URL: https://grafana.<DOMINIO>
- Alertmanager URL: https://alerts.<DOMINIO>
- Discord webhook: configurado (✅/❌) — secret `DISCORD_WEBHOOK_URL`
- Dashboards stub criados: 8 arquivos JSON em `/opt/roleta/obs/grafana-provisioning/dashboards/`
- Alert rules: 8 ativos (HitRateCWLow, HitRateCCWLow, DriftSurge, MartingaleHighLevel, BankrollDrawdown, SpinLatencyP99, AppDown, DiskFull)

## 15. Azure Storage (v2.0)
- Account: stroletaprod (Standard_LRS, Hot)
- Containers: models, backups, reports, golden-traces, pg-backups-export
- Lifecycle policy: aplicada (Hot 30d → Cool 180d → Archive 730d)
- Acesso: Managed Identity da VM com role Storage Blob Data Contributor
- Connection string: `STORAGE_ACCOUNT_CONNECTION_STRING` no KV

## 16. Application Insights (v2.0)
- Recurso: ai-roleta-prod (linkado a law-roleta-prod)
- Connection string: `APP_INSIGHTS_CONNECTION_STRING` no KV
- Smoke trace enviado: ✅/❌ (link/screenshot do trace)

## 17. GitHub OIDC Federation (v2.0)
- AppId: <UUID>
- Federated credentials: 3 trusts (main, tags v*, env=production)
- GitHub secrets a adicionar (lista pronta para copy-paste):
  - AZURE_CLIENT_ID
  - AZURE_TENANT_ID
  - AZURE_SUBSCRIPTION_ID
  - ACR_LOGIN_SERVER
  - VM_HOST
  - VM_SSH_PRIVATE_KEY (anexo arquivo)

## 18. Resource Locks (v2.0)
- 4 locks CanNotDelete aplicados em: rg, kv, pg, storage
- Procedimento de remoção documentado

## 19. DR / Backup (v2.0)
- state.json: backup cron `0 3,9,15,21 * * *` → Blob backups/
- VM snapshot: Azure Backup daily 03:00 UTC, retenção 30d
- Postgres PITR: 7d / LTR weekly 12 semanas
- Bicep IaC: anexo `infrastructure/main.bicep` validado
- Runbook: anexo `runbook.md` com 5+ cenários
- Cost budget: USD <threshold>/mês com alertas 80%/100%
```

---



## 14. Em caso de dúvida, FALE COM O ORQUESTRADOR

O agente provisionador pode pedir esclarecimentos ao usuário a qualquer momento via mensagem direta. Em caso de ambiguidade entre este documento e o `final_refatoracao_proposta.md`, **este documento prevalece** para questões de infraestrutura.

Não improvise:
- Não crie recursos com nomes fora do padrão
- Não use SKUs diferentes dos especificados sem aprovação
- Não rode comandos destrutivos no `187.45.181.75` (HostDime atual) — ele só será descomissionado pelo usuário após cutover
- Não exponha senhas em texto plano em nenhum documento (sempre referencie secrets do KV)

---

## 15. Histórico de revisões deste documento

| Versão | Data | Autor | Mudança |
|---|---|---|---|
| 1.0 | 2026-05-23 16:11 | YOLO Orchestrator | Versão inicial |
| **2.0** | **2026-05-23 16:18** | **YOLO Orchestrator** | **Auditoria cruzada com 4 docs. +9 seções (§16-§24). +17 testes (T32-T48). +8 secrets. Padronização ACR. Adição: observability stack, Blob Storage, App Insights real, OIDC Federation, Resource Locks, backup state.json, snapshot policy, particionamento pg_partman, cost alert, DR plan, smoke pré-cutover.** |

---

*Documento gerado por YOLO Orchestrator (Claude Opus 4.7) em 23/05/2026 16:11 UTC-3 utilizando MCPs: sequential-thinking + filesystem + memory + graphify. Solicitação formal de provisionamento Azure para suportar Roleta Cloud v5.0, conforme `final_refatoracao_proposta.md`.*


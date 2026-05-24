# Sx-OBS — Grafana Cloud + Prometheus

**Status: 100% — ATIVO em prod (validado 2026-05-24).
Métricas + logs sendo ingeridos via Grafana Cloud sa-east-1.**

## Estado atual em prod (Debian 187.45.181.75)

| Item | Path / Valor | Status |
|---|---|---|
| Grafana Agent | `/usr/local/bin/grafana-agent` v0.42.0 (systemd) | ✅ active |
| postgres-exporter | container `pg-exporter` em `roleta-cloud_default` | ✅ up, scrape OK |
| Config | `/etc/grafana-agent/config.yml` (chmod 600) | ✅ |
| Token Grafana Cloud | `/root/secrets/grafana_token` (chmod 600) | ✅ |
| Region | `prod-sa-east-1` | ✅ |
| Prom samples_in | 1700+/50s (failed=0) | ✅ |
| Loki entries_sent | ativo, todos `dropped=0` | ✅ |

## Setup completo em 1 comando (idempotente)

```bash
ssh root@187.45.181.75
export PROM_USER=<seu_prom_user_id>      # ex: 3255266 (numerico)
export LOKI_USER=<seu_loki_user_id>      # ex: 1623308 (numerico)
export PROM_URL=https://prometheus-prod-40-prod-sa-east-1.grafana.net/api/prom/push
export LOKI_URL=https://logs-prod-024.grafana.net/loki/api/v1/push
cd /root/roleta-cloud && bash scripts/install-grafana-agent.sh
```

Pre-requisito: `/root/secrets/grafana_token` (chmod 600) com o token Grafana Cloud (mesmo p/ Prom e Loki).

## Por que Grafana Cloud Free

- 10k series, 50GB logs, 14 dias retention — suficiente para projeto atual.
- Agentes leves no Debian (sem manter Prometheus/Loki).
- Alertas via email/Slack/Discord.

## Pre-requisitos (acao do usuario)

1. Criar conta em https://grafana.com/products/cloud/ (free tier).
2. Stack name: `roleta-cloud`.
3. Coletar:
   - Prometheus remote_write URL + user + API key.
   - Loki push URL + user + API key.

## Instalacao Grafana Agent no Debian

```bash
sudo wget -O /usr/local/bin/grafana-agent https://github.com/grafana/agent/releases/latest/download/grafana-agent-linux-amd64.zip
sudo unzip ... && sudo chmod +x /usr/local/bin/grafana-agent
sudo mkdir /etc/grafana-agent
sudo tee /etc/grafana-agent/config.yml <<EOF
server:
  log_level: warn
metrics:
  global:
    scrape_interval: 30s
    remote_write:
      - url: <PROM_URL>
        basic_auth:
          username: <PROM_USER>
          password: <PROM_KEY>
  configs:
    - name: pg
      scrape_configs:
        - job_name: postgres
          static_configs:
            - targets: ['localhost:9187']  # postgres_exporter
        - job_name: cdc-worker
          static_configs:
            - targets: ['localhost:9100']  # custom metrics endpoint
logs:
  configs:
    - name: roleta
      clients:
        - url: <LOKI_URL>
          basic_auth:
            username: <LOKI_USER>
            password: <LOKI_KEY>
      positions:
        filename: /var/lib/grafana-agent/positions.yaml
      scrape_configs:
        - job_name: docker
          docker_sd_configs:
            - host: unix:///var/run/docker.sock
EOF
sudo systemctl enable --now grafana-agent
```

## postgres_exporter

```bash
docker run -d --name pg-exporter --network roleta-net \
  -e DATA_SOURCE_NAME="postgresql://roleta:<PG_PASSWORD>@roleta-pg:5432/roleta?sslmode=disable" \
  -p 9187:9187 quay.io/prometheuscommunity/postgres-exporter
```

## Dashboard mínimo (cardapio)

| Painel                  | Metrica                                       |
|-------------------------|-----------------------------------------------|
| Outbox lag              | `shared.outbox` rows where consumed_at IS NULL |
| CDC worker erros        | log Loki `level=error` count                  |
| Latencia save_decision  | histogram custom                              |
| Win rate (1h)           | derivado de decisoes/results                  |
| ivfflat index size      | `pg_relation_size('cw.spins_vectors_ivfflat')` |
| Feature flags status    | `shared.feature_flags WHERE enabled=true`     |

## Alertas (mínimo)

| Alerta                       | Condicao                                  |
|------------------------------|-------------------------------------------|
| Outbox lag alto              | rows nao consumidos > 100 por > 5min      |
| CDC worker down              | sem heartbeat por > 2min                  |
| PG connections cheias        | usage > 80% de max_connections            |
| Disk usage Debian            | > 85%                                     |
| Feature flag desconhecida    | flag enabled fora da whitelist            |

## Custo

Free tier: $0/mes.
Estimativa de uso atual: <5% das cotas free.

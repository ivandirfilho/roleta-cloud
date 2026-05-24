#!/bin/bash
# install-grafana-agent.sh — Provisiona Grafana Agent + postgres_exporter no Debian.
#
# Pre-requisitos no servidor:
#   - /root/secrets/grafana_token (chmod 600) — token Grafana Cloud (mesmo p/ Prom+Loki)
#   - /root/.pg_password — senha do user 'roleta' no PG
#   - docker + rede roleta-cloud_default rodando com container roleta-pg
#
# Variaveis de ambiente esperadas:
#   PROM_USER=<numero do user Prometheus do Grafana Cloud>
#   LOKI_USER=<numero do user Loki do Grafana Cloud>
#   PROM_URL=https://prometheus-prod-XX-prod-REGION.grafana.net/api/prom/push
#   LOKI_URL=https://logs-prod-NNN.grafana.net/loki/api/v1/push
#
# Idempotente: pode rodar quantas vezes quiser.

set -euo pipefail

: "${PROM_USER:?PROM_USER required}"
: "${LOKI_USER:?LOKI_USER required}"
: "${PROM_URL:?PROM_URL required}"
: "${LOKI_URL:?LOKI_URL required}"

TOKEN_FILE="${TOKEN_FILE:-/root/secrets/grafana_token}"
[[ -f "$TOKEN_FILE" ]] || { echo "ERRO: $TOKEN_FILE nao existe"; exit 1; }
TOKEN=$(cat "$TOKEN_FILE")
PGPASS=$(cat /root/.pg_password)
HOST=$(hostname)
GA_VER="${GA_VER:-0.42.0}"

echo "[1/5] Instalando grafana-agent v${GA_VER} se faltando..."
if ! command -v grafana-agent >/dev/null; then
  apt-get update -qq && apt-get install -y -qq unzip wget
  cd /tmp
  wget -q "https://github.com/grafana/agent/releases/download/v${GA_VER}/grafana-agent-linux-amd64.zip" -O ga.zip
  unzip -o ga.zip
  install -m 755 grafana-agent-linux-amd64 /usr/local/bin/grafana-agent
  rm -f ga.zip grafana-agent-linux-amd64
fi
grafana-agent --version | head -1

echo "[2/5] Subindo postgres-exporter sidecar..."
docker rm -f pg-exporter 2>/dev/null || true
docker run -d --name pg-exporter \
  --network roleta-cloud_default \
  --restart unless-stopped \
  -e DATA_SOURCE_NAME="postgresql://roleta:${PGPASS}@roleta-pg:5432/roleta?sslmode=disable" \
  -p 127.0.0.1:9187:9187 \
  quay.io/prometheuscommunity/postgres-exporter:v0.15.0 >/dev/null
sleep 3
curl -sf http://127.0.0.1:9187/metrics | grep -q "^pg_up " && echo "  pg-exporter OK"

echo "[3/5] Gerando /etc/grafana-agent/config.yml..."
mkdir -p /etc/grafana-agent /var/lib/grafana-agent
cat > /etc/grafana-agent/config.yml <<EOF
server:
  log_level: warn
metrics:
  global:
    scrape_interval: 30s
    external_labels:
      host: ${HOST}
      env: prod
      project: roleta-cloud
    remote_write:
      - url: ${PROM_URL}
        basic_auth:
          username: "${PROM_USER}"
          password: "${TOKEN}"
  wal_directory: /var/lib/grafana-agent/wal
  configs:
    - name: roleta
      scrape_configs:
        - job_name: postgres
          static_configs:
            - targets: ['127.0.0.1:9187']
              labels:
                service: postgres
                instance: roleta-pg
logs:
  positions_directory: /var/lib/grafana-agent
  configs:
    - name: docker
      clients:
        - url: ${LOKI_URL}
          basic_auth:
            username: "${LOKI_USER}"
            password: "${TOKEN}"
          external_labels:
            host: ${HOST}
            env: prod
            project: roleta-cloud
      scrape_configs:
        - job_name: docker-json
          static_configs:
            - targets: [localhost]
              labels:
                job: docker
                __path__: /var/lib/docker/containers/*/*-json.log
          pipeline_stages:
            - json:
                expressions: {log: log, stream: stream, time: time}
            - timestamp: {source: time, format: RFC3339Nano}
            - output: {source: log}
            - labels: {stream: ""}
EOF
chmod 600 /etc/grafana-agent/config.yml

echo "[4/5] Instalando systemd unit..."
cat > /etc/systemd/system/grafana-agent.service <<'SVC'
[Unit]
Description=Grafana Agent
After=network.target docker.service
[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/grafana-agent -config.file=/etc/grafana-agent/config.yml
Restart=always
RestartSec=5
LimitNOFILE=1048576
[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable --now grafana-agent
sleep 6

echo "[5/5] Validando..."
systemctl is-active grafana-agent
curl -sf http://127.0.0.1:12345/-/ready
echo ""
echo "Aguardando primeiro push (~45s)..."
sleep 45
SENT=$(curl -s http://127.0.0.1:12345/metrics | awk '/^prometheus_remote_storage_samples_in_total/{print $2; exit}')
FAILED=$(curl -s http://127.0.0.1:12345/metrics | awk -F'} ' '/^prometheus_remote_storage_samples_failed_total/{print $2; exit}')
LOGS=$(curl -s http://127.0.0.1:12345/metrics | awk -F'} ' '/^promtail_sent_entries_total/{print $2; exit}')
echo "  prometheus samples_in=$SENT  failed=$FAILED"
echo "  loki entries_sent=$LOGS"
[[ "${FAILED:-0}" == "0" ]] && echo "OK Grafana Cloud RECEBENDO" || { echo "FAIL push_failed > 0"; exit 2; }

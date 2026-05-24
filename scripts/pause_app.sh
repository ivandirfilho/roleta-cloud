#!/usr/bin/env bash
# Sx-PAUSE — pausa controlada do app (NAO do PG).
# Uso: bash scripts/pause_app.sh
# Vide docs/runbooks/pause-policy.md.

set -euo pipefail

cd /root/roleta-cloud

TS=$(date -u +%Y%m%dT%H%M%SZ)
SNAP="/root/roleta-cloud/data/pause-${TS}.json"

echo "[pause] T-0  marcando app_paused=true no PG"
if [[ -f /root/.pg_password ]]; then
  PW=$(cat /root/.pg_password)
  docker exec -e PGPASSWORD="$PW" roleta-pg psql -U roleta -d roleta -c \
    "INSERT INTO shared.feature_flags (name, enabled, pct, payload) VALUES ('app_paused', true, 100, jsonb_build_object('reason','manual-pause','ts','${TS}')) ON CONFLICT (name) DO UPDATE SET enabled = EXCLUDED.enabled, pct = EXCLUDED.pct, payload = EXCLUDED.payload, updated_at = now();"
else
  echo "[pause] WARN: /root/.pg_password ausente; flag nao foi setada"
fi

echo "[pause] T+0  snapshot do estado em ${SNAP}"
mkdir -p "$(dirname "$SNAP")"
docker inspect roleta-cloud --format '{{json .State}}' > "$SNAP" 2>/dev/null || echo '{}' > "$SNAP"

echo "[pause] T+0  aguardando 60s para clientes drenarem"
sleep 60

echo "[pause] T+60 parando container roleta-cloud (PG continua up)"
docker stop --time 30 roleta-cloud

echo "[pause] OK app parado. Container PG segue em pe:"
docker ps --filter name=roleta-pg --format "  {{.Names}}  {{.Status}}"
echo "[pause] Para resumir: bash scripts/resume_app.sh"

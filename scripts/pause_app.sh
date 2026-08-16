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
# SPR-D1 (16/08/2026): sinaliza a parada DELIBERADA antes do stop. Sem esta
# sentinela, o self-heal do tick NOOP (scripts/roleta-deploy-pull.sh) subiria o
# container de volta em ate ~2 min e a janela de manutencao evaporaria.
# resume_app.sh remove o arquivo.
SELF_HEAL_PAUSED_FILE="${SELF_HEAL_PAUSED_FILE:-/var/lib/roleta-deploy/self_heal_paused}"
mkdir -p "$(dirname "$SELF_HEAL_PAUSED_FILE")" 2>/dev/null || true
# Falhar aqui e FATAL: a sentinela e o unico freio que cobre este stop, e seguir
# em frente entregaria uma janela de manutencao que o self-heal desfaz sozinho em
# ~2 min. Sem 2>/dev/null — se falhar (ex.: /var cheio), o motivo tem de aparecer.
if ! echo "manual-pause ${TS}" > "$SELF_HEAL_PAUSED_FILE"; then
    echo "[pause] ERRO: nao consegui criar ${SELF_HEAL_PAUSED_FILE} — abortando" >&2
    echo "[pause] (sem a sentinela o self-heal ressuscitaria o app durante a manutencao)" >&2
    exit 1
fi
echo "[pause] self-heal suspenso via ${SELF_HEAL_PAUSED_FILE}"
docker stop --time 60 roleta-cloud

echo "[pause] OK app parado. Container PG segue em pe:"
docker ps --filter name=roleta-pg --format "  {{.Names}}  {{.Status}}"
echo "[pause] Para resumir: bash scripts/resume_app.sh"

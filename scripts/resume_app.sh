#!/usr/bin/env bash
# Sx-PAUSE — resume do app apos janela de manutencao.
# Uso: bash scripts/resume_app.sh

set -euo pipefail

cd /root/roleta-cloud

STATE_VOLUME_KEY="${STATE_VOLUME_KEY:-roleta-data}"
STATE_VOLUME_NAME="${STATE_VOLUME_NAME:-}"

resolve_state_volume_name() {
  local candidates count volume_name
  if [[ -n "$STATE_VOLUME_NAME" ]]; then
    printf '%s\n' "$STATE_VOLUME_NAME"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1 &&
    volume_name="$(
      docker compose config --format json 2>/dev/null |
        python3 -c 'import json, sys; print(json.load(sys.stdin)["volumes"][sys.argv[1]]["name"])' "$STATE_VOLUME_KEY" 2>/dev/null
    )" &&
    [[ -n "$volume_name" ]]; then
    printf '%s\n' "$volume_name"
    return 0
  fi
  candidates="$(docker volume ls --quiet --filter "label=com.docker.compose.volume=$STATE_VOLUME_KEY")" || return 1
  count="$(printf '%s\n' "$candidates" | sed '/^$/d' | wc -l)"
  if [[ "$count" == "1" ]]; then
    printf '%s\n' "$candidates" | sed -n '1p'
    return 0
  fi
  return 1
}

assert_state_volume_ready() {
  local mountpoint volume_name
  volume_name="$(resolve_state_volume_name)" || {
    echo "[resume] ERRO: volume nao resolvido; use Compose >=2.6 ou STATE_VOLUME_NAME" >&2
    return 1
  }
  mountpoint="$(docker volume inspect -f '{{.Mountpoint}}' "$volume_name" 2>/dev/null)" || {
    echo "[resume] ERRO: volume Docker ausente: ${volume_name}" >&2
    return 1
  }
  [[ -f "$mountpoint/state.json" ]] || {
    echo "[resume] ERRO: migre state.json para o volume antes de subir o app" >&2
    return 1
  }
}

assert_state_volume_ready

echo "[resume] T+0  subindo container roleta-cloud"
docker compose up -d

echo "[resume] T+0  aguardando healthcheck (timeout 90s)"
for i in $(seq 1 18); do
  STATUS=$(docker inspect roleta-cloud --format '{{.State.Health.Status}}' 2>/dev/null || echo "missing")
  if [[ "$STATUS" == "healthy" ]]; then
    echo "[resume] T+$((i*5)) healthy"
    break
  fi
  echo "[resume] T+$((i*5))  status=${STATUS}"
  sleep 5
done

if [[ "$STATUS" != "healthy" ]]; then
  echo "[resume] ERRO: container nao ficou healthy em 90s. Status final: ${STATUS}"
  docker logs roleta-cloud --tail 30
  exit 2
fi

echo "[resume] desmarcando app_paused no PG"
if [[ -f /root/.pg_password ]]; then
  PW=$(cat /root/.pg_password)
  docker exec -e PGPASSWORD="$PW" roleta-pg psql -U roleta -d roleta -c \
    "UPDATE shared.feature_flags SET enabled = false, pct = 0, updated_at = now() WHERE name = 'app_paused';"
fi

echo "[resume] vigiando logs por 30s"
sleep 30
ERR_COUNT=$(docker logs roleta-cloud --since 30s 2>&1 | grep -cE "ERROR|FATAL|Traceback" || true)
if [[ "$ERR_COUNT" -gt 0 ]]; then
  echo "[resume] WARN: encontrei ${ERR_COUNT} sinais de erro nos ultimos 30s. Inspecionar:"
  docker logs roleta-cloud --since 30s 2>&1 | grep -E "ERROR|FATAL|Traceback" | head -20
  exit 3
fi

echo "[resume] OK app saudavel e sem erros."
docker ps --format "table {{.Names}}\t{{.Status}}"

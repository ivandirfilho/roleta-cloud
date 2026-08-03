#!/bin/bash
# SP-03: pull-based deploy automatizado.
#
# Roda como systemd timer no servidor Debian. A cada N minutos:
#   1) git fetch origin main
#   2) se HEAD local == origin/main -> NOOP exit 0
#   3) senao salva HEAD atual em /var/lib/roleta-deploy/last_good
#   4) git reset --hard origin/main
#   5) docker compose build --quiet roleta-cloud
#   6) docker compose up -d roleta-cloud
#   7) healthcheck 3x com 5s entre tentativas
#   8) se falhar, rollback para last_good + alerta no log
#
# Idempotente. Logs vao para /var/log/roleta-deploy.log + journald.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
STATE_DIR="${STATE_DIR:-/var/lib/roleta-deploy}"
LOG_FILE="${LOG_FILE:-/var/log/roleta-deploy.log}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8766/health}"
HEALTH_RETRIES="${HEALTH_RETRIES:-3}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"
SERVICE="${SERVICE:-roleta-cloud}"
STATE_VOLUME_NAME="${STATE_VOLUME_NAME:-}"
STATE_VOLUME_KEY="${STATE_VOLUME_KEY:-roleta-data}"

mkdir -p "$STATE_DIR"
exec >> "$LOG_FILE" 2>&1

log() { echo "[$(date -u +%FT%TZ)] $*"; }

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
        log "STATE MIGRATION REQUIRED — volume nao resolvido; use Compose >=2.6 ou defina STATE_VOLUME_NAME"
        return 1
    }
    mountpoint="$(docker volume inspect -f '{{.Mountpoint}}' "$volume_name" 2>/dev/null)" || {
        log "STATE MIGRATION REQUIRED — volume ausente: $volume_name"
        return 1
    }
    if [[ ! -f "$mountpoint/state.json" ]]; then
        log "STATE MIGRATION REQUIRED — falta $mountpoint/state.json"
        return 1
    fi
}

cd "$REPO_DIR"

git fetch --quiet origin main || { log "FETCH FAIL"; exit 1; }
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

log "DEPLOY START local=$LOCAL remote=$REMOTE"
echo "$LOCAL" > "$STATE_DIR/last_good"

git reset --hard origin/main >/dev/null

if ! docker compose build --quiet "$SERVICE"; then
    log "BUILD FAIL — rollback"
    git reset --hard "$LOCAL" >/dev/null
    exit 1
fi

if ! assert_state_volume_ready; then
    log "DEPLOY ABORTED — execute scripts/migrate-state-to-volume.sh antes do primeiro deploy"
    git reset --hard "$LOCAL" >/dev/null
    docker compose build --quiet "$SERVICE" || true
    docker compose up -d "$SERVICE" || true
    exit 1
fi

docker compose up -d "$SERVICE"

# Healthcheck loop
ok=0
for i in $(seq 1 "$HEALTH_RETRIES"); do
    sleep "$HEALTH_INTERVAL"
    if curl -fs --max-time 4 "$HEALTH_URL" >/dev/null 2>&1; then
        ok=1
        log "HEALTHCHECK ok (try $i)"
        break
    fi
    log "HEALTHCHECK fail (try $i)"
done

if [ "$ok" -ne 1 ]; then
    log "DEPLOY FAIL — rollback para $LOCAL"
    git reset --hard "$LOCAL" >/dev/null
    docker compose build --quiet "$SERVICE" || true
    docker compose up -d "$SERVICE" || true
    exit 1
fi

# --- Frontend estático para o nginx do host (gap de deploy corrigido 17/06) ---
# O container serve só o WebSocket; os assets do dashboard Glass Box são servidos
# pelo nginx do HOST a partir de $WWW_DIR (roleta.conf: `root /var/www/roleta`).
# Sem este passo, mudanças em frontend/ nunca chegavam em produção. Não-fatal.
# (Nota: duplicado mais antigo de scripts/roleta-deploy-pull.sh — manter em sincronia.)
WWW_DIR="${WWW_DIR:-/var/www/roleta}"
if [ -d "$REPO_DIR/frontend" ]; then
    if mkdir -p "$WWW_DIR" && cp -a "$REPO_DIR/frontend/." "$WWW_DIR/"; then
        log "FRONTEND sync ok -> $WWW_DIR (sha=$REMOTE)"
        if command -v nginx >/dev/null 2>&1 && nginx -t >/dev/null 2>&1; then
            systemctl reload nginx && log "NGINX reload ok" || log "NGINX reload falhou (nao-fatal)"
        else
            log "NGINX ausente/config invalida — reload pulado (nao-fatal)"
        fi
    else
        log "FRONTEND sync FALHOU (nao-fatal)"
    fi
fi

log "DEPLOY OK sha=$REMOTE"

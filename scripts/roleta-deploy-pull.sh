#!/bin/bash
# SP-03: pull-based deploy automatizado. (Fonte versionada — instalar em
# /usr/local/bin/roleta-deploy-pull.sh no servidor; manter LF.)
#
# Roda como systemd timer no servidor Debian. A cada N minutos:
#   1) git fetch origin main
#   2) se HEAD local == origin/main -> NOOP exit 0
#   3) senao salva HEAD atual em /var/lib/roleta-deploy/last_good
#   4) git reset --hard origin/main
#   5) docker compose build --quiet roleta-cloud
#   6) C1 (12/06): alembic upgrade head — elimina drift codigo x schema
#      (prod ficou em 0006 com repo em 0008 por 2 semanas; classe B-10)
#   7) docker compose up -d roleta-cloud
#   8) healthcheck 3x com 5s entre tentativas
#   9) se falhar, rollback para last_good + alerta no log
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

mkdir -p "$STATE_DIR"
exec >> "$LOG_FILE" 2>&1

log() { echo "[$(date -u +%FT%TZ)] $*"; }

rollback() {
    local reason="$1" sha="$2"
    log "$reason — rollback para $sha"
    git reset --hard "$sha" >/dev/null
    docker compose build --quiet "$SERVICE" || true
    docker compose up -d "$SERVICE" || true
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

# C1 (12/06): migrations ANTES do up. Falha de migration = rollback completo.
if ! docker compose run --rm "$SERVICE" alembic upgrade head; then
    rollback "ALEMBIC FAIL" "$LOCAL"
    exit 1
fi
log "ALEMBIC ok ($(docker compose run --rm "$SERVICE" alembic current 2>/dev/null | tail -1 || echo '?'))"

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
    rollback "DEPLOY FAIL" "$LOCAL"
    exit 1
fi

log "DEPLOY OK sha=$REMOTE"

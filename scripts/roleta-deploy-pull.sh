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
#  10) OBS-INODE (05/08): scripts/obs-apply.sh — se obs/prometheus.yml,
#      obs/alerts.yml ou docker-compose.obs.yml mudaram, valida (promtool),
#      aplica (reload OU recriacao unica do Prometheus) e VERIFICA que o
#      container passou a ler os mesmos bytes do repo. Sem mudanca de obs,
#      nao encosta no Prometheus.
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

# SPR-D1 (16/08/2026): self-heal do tick NOOP. Ver bloco self_heal_tick().
SELF_HEAL="${SELF_HEAL:-1}"
WS_PROBE_HOST="${WS_PROBE_HOST:-127.0.0.1}"
WS_PROBE_PORT="${WS_PROBE_PORT:-8765}"
WS_PROBE_TIMEOUT="${WS_PROBE_TIMEOUT:-3}"
SELF_HEAL_PAUSED_FILE="${SELF_HEAL_PAUSED_FILE:-$STATE_DIR/self_heal_paused}"

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

rollback() {
    local reason="$1" sha="$2"
    log "$reason — rollback para $sha"
    git reset --hard "$sha" >/dev/null
    docker compose build --quiet "$SERVICE" || true
    docker compose up -d "$SERVICE" || true
}

# >>> SPR-D1 SELF-HEAL BEGIN (sentinela usada por tests/test_spr_d1_self_heal.py —
# o teste extrai daqui até o END para exercitar as funções sem rodar o deploy)
# --- Sondas de vivacidade (SPR-D1, 16/08/2026) ------------------------------
# O healthcheck do compose olha SÓ o 8766 (/health). O listener que o Glass Box
# usa é o 8765 (WebSocket), e nginx traduz "ninguém escutando no 8765" em 502.
# Sondar os dois é o que impede um WS morto de passar batido.
probe_health_http() {
    curl -fs --max-time 4 "$HEALTH_URL" >/dev/null 2>&1
}

# Handshake WebSocket de verdade — NÃO um TCP-connect.
#
# POR QUE NÃO BASTA CONECTAR (achado do code-review do SPR-D1): a porta é
# publicada como `127.0.0.1:8765:8765`, e com o userland proxy do Docker (default)
# quem escuta em 127.0.0.1:8765 é o `docker-proxy`, não a aplicação. O docker-proxy
# faz `Accept()` PRIMEIRO e só depois disca para o container — então um TCP-connect
# puro retorna sucesso mesmo com ninguém escutando lá dentro. Verificado em
# laboratório: contra um socket que só aceita, o connect passa e o handshake falha.
#
# Um TCP-connect também daria "ok" na janela entre `up -d` e o bind real do WS,
# fazendo o self-heal declarar cura cedo demais.
#
# /dev/tcp é builtin do bash (o shebang deste script já é bash) — sem dependência
# nova no host. Exige a status line `101 Switching Protocols`: prova que o servidor
# WS respondeu, não que alguém aceitou o socket.
probe_ws_handshake() {
    timeout "$WS_PROBE_TIMEOUT" bash -c '
        exec 3<>/dev/tcp/'"$WS_PROBE_HOST"'/'"$WS_PROBE_PORT"' || exit 1
        printf "GET / HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n" "self-heal-probe" >&3
        head -n 1 <&3 | grep -q " 101 "
    ' 2>/dev/null
}

# Retorna a lista de sondas que falharam (vazio = tudo de pé).
failed_probes() {
    local failed=""
    probe_health_http || failed="health(8766)"
    probe_ws_handshake || failed="${failed:+$failed + }ws(${WS_PROBE_PORT})"
    printf '%s' "$failed"
}

# --- Self-heal do tick NOOP (SPR-D1, 16/08/2026) ----------------------------
# BURACO CORRIGIDO: quando LOCAL == REMOTE o tick saía `exit 0` sem olhar para o
# app. Um container parado (crash, OOM, `compose down`, daemon reiniciado) ficava
# parado ATÉ o próximo merge — dias, se o repo estivesse quieto. Foi esse gap que
# manteve `/ws` em 502 com a VM "online" no incidente de 16/08.
#
# É corretivo e idempotente (`up -d` num container já de pé é no-op), por isso
# nasce LIGADO (SELF_HEAL=1) em vez de flag default-OFF. Desligar: SELF_HEAL=0 no
# Environment da unit.
#
# NÃO pode brigar com uma parada DELIBERADA (scripts/pause_app.sh). Dois freios:
#   1. sentinela $SELF_HEAL_PAUSED_FILE (pause_app.sh cria, resume_app.sh remove);
#   2. exit code que só existe quando alguém MANDOU parar. Crash de Python sai 1
#      (ou 0); 143 = SIGTERM, 137 = SIGKILL após o grace period — ambos vêm de um
#      `docker stop`/`kill`, nunca de um crash espontâneo. A exceção é o OOM
#      killer, que também produz 137: esse é outage de verdade e DEVE ser curado,
#      por isso lemos `OOMKilled` para separar os dois.
#      Mesma semântica do `restart: unless-stopped` do Docker, que também não
#      ressuscita quem foi parado de propósito.
container_state() {
    docker inspect -f '{{.State.Status}}:{{.State.ExitCode}}:{{.State.OOMKilled}}' "$SERVICE" 2>/dev/null || echo "missing:0:false"
}

# Parada deliberada = não ressuscitar. Recebe a saída de container_state().
deliberate_stop() {
    case "$1" in
        exited:0:*)     return 0 ;;  # saída graciosa
        exited:143:*)   return 0 ;;  # SIGTERM (docker stop)
        exited:137:true) return 1 ;;  # OOM killer -> é outage, cura
        exited:137:*)   return 0 ;;  # SIGKILL após grace period (docker stop/kill)
        *)              return 1 ;;
    esac
}

self_heal_tick() {
    [ "$SELF_HEAL" = "1" ] || return 0

    local failed state
    failed="$(failed_probes)"
    [ -n "$failed" ] || return 0

    if [ -f "$SELF_HEAL_PAUSED_FILE" ]; then
        log "SELF-HEAL stand-down — app fora do ar mas pausa deliberada sinalizada ($SELF_HEAL_PAUSED_FILE): $failed"
        return 0
    fi

    state="$(container_state)"
    if deliberate_stop "$state"; then
        log "SELF-HEAL stand-down — parada deliberada (estado=$state); nao ressuscito quem mandaram parar: $failed"
        return 0
    fi

    log "SELF-HEAL sonda falhou ($failed) estado=$state — subindo $SERVICE"
    if ! docker compose up -d "$SERVICE"; then
        log "SELF-HEAL up FALHOU — host exige intervencao do dono (docs/runbooks/servidor-502-glassbox.md)"
        return 1
    fi

    local i
    for i in $(seq 1 "$HEALTH_RETRIES"); do
        sleep "$HEALTH_INTERVAL"
        if [ -z "$(failed_probes)" ]; then
            log "SELF-HEAL ok (try $i) — 8766 e ${WS_PROBE_PORT} respondendo"
            return 0
        fi
    done

    log "SELF-HEAL INEFICAZ apos $HEALTH_RETRIES tentativas ($(failed_probes)) — provavel crash-loop"
    log "SELF-HEAL proximo passo: docker logs $SERVICE --tail 50 (runbook docs/runbooks/servidor-502-glassbox.md)"
    return 1
}
# <<< SPR-D1 SELF-HEAL END

cd "$REPO_DIR"

# OBS-INODE (05/08/2026): uma pendencia de observabilidade de um deploy anterior
# tem de ser retomada ANTES do gate NOOP — senao, no tick seguinte, LOCAL==REMOTE
# encerra com exit 0 e a falha some (systemd volta a "success" sem nada aplicado).
obs_run() {
    if [ -f "$REPO_DIR/scripts/obs-apply.sh" ]; then
        REPO_DIR="$REPO_DIR" STATE_DIR="$STATE_DIR" bash "$REPO_DIR/scripts/obs-apply.sh" "$@"
    else
        log "OBS scripts/obs-apply.sh ausente neste checkout — passo pulado"
    fi
}

git fetch --quiet origin main || { log "FETCH FAIL"; exit 1; }
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    if [ -f "$STATE_DIR/obs_pending" ]; then
        if ! obs_run resume; then
            log "OBS RESUME FAIL — regras Prometheus seguem pendentes"
            exit 1
        fi
    fi
    # SPR-D1: nada a implantar != nada a fazer. Se o app estiver fora do ar,
    # cura aqui; sai != 0 se não conseguiu, para o systemd marcar a unit como
    # failed em vez de reportar sucesso com o Glass Box offline.
    if ! self_heal_tick; then
        exit 1
    fi
    exit 0
fi

log "DEPLOY START local=$LOCAL remote=$REMOTE"
echo "$LOCAL" > "$STATE_DIR/last_good"

git reset --hard origin/main >/dev/null

# OBS-INODE: valida a config de observabilidade JA no disco (o mount de diretorio
# a expoe ao container no mesmo instante). Config invalida aqui = Prometheus que
# nao sobe no proximo restart -> aborta antes de tocar em qualquer container.
if ! obs_run check "$LOCAL" "$REMOTE"; then
    log "OBS CONFIG INVALIDA — rollback para $LOCAL, nada aplicado"
    git reset --hard "$LOCAL" >/dev/null
    exit 1
fi

if ! docker compose build --quiet "$SERVICE"; then
    log "BUILD FAIL — rollback"
    git reset --hard "$LOCAL" >/dev/null
    exit 1
fi

# MIG-0: refuse any new deployment until the persisted engine state exists.
if ! assert_state_volume_ready; then
    rollback "STATE MIGRATION REQUIRED" "$LOCAL"
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

# SPR-D1: o gate de rollback continua sendo o /health (8766) — não mexo no
# critério de rollback para não introduzir flapping. Mas registro o estado do
# listener WS: um deploy "OK" com 8765 mudo é justamente o 502 do Glass Box, e
# antes disto não aparecia em lugar nenhum.
if probe_ws_handshake; then
    log "WS PROBE ok (${WS_PROBE_HOST}:${WS_PROBE_PORT} respondeu 101 Switching Protocols)"
else
    log "WS PROBE FALHOU — /health ok mas ninguem escuta em ${WS_PROBE_PORT}: nginx devolvera 502 em /ws"
fi

# --- Frontend estático para o nginx do host (gap de deploy corrigido 17/06) ---
# O container serve só o WebSocket (8765) + /health (8766); os assets do dashboard
# Glass Box são servidos pelo nginx do HOST a partir de $WWW_DIR
# (roleta.conf: `root /var/www/roleta`). Sem este passo, mudanças em frontend/
# (index.html, app.js, style.css) NUNCA chegavam em produção — o nginx continuava
# servindo a cópia manual antiga. Roda só após healthcheck OK e é NÃO-FATAL: uma
# falha aqui não derruba o backend já saudável (logada para inspeção).
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

log "DEPLOY OK (app) sha=$REMOTE"

# --- Drift do entrypoint (OBS-INODE, 05/08/2026) ---------------------------
# O systemd roda /usr/local/bin/roleta-deploy-pull.sh, que fica FORA do repo. Se
# ainda for a copia congelada, este proprio arquivo (versionado) nao e o que roda
# em producao — foi assim que o passo de observabilidade poderia nunca chegar la.
#
# LIMITE: esta sonda vive no script VERSIONADO, entao ela nao detecta o
# congelamento ATUAL (a copia congelada nunca a executa) — so protege contra um
# re-congelamento FUTURO. Quem cobre o caso atual e o bootstrap manual, e a unit
# systemd chama a mesma sonda em ExecStartPre (nao-fatal), independente de qual
# script esteja instalado.
#
# READ-ONLY e NAO-FATAL. Deliberadamente NAO se auto-instala: um deploy que
# reescreve o proprio entrypoint pode se tornar irrecuperavel se o arquivo novo
# estiver quebrado; a correcao e um comando unico, documentado em docs/DEPLOY.md.
if [ -f "$REPO_DIR/scripts/roleta-deploy-install.sh" ]; then
    REPO_DIR="$REPO_DIR" bash "$REPO_DIR/scripts/roleta-deploy-install.sh" --check || true
fi

# --- Observabilidade (OBS-INODE, 05/08/2026) -------------------------------
# So aqui, com o app ja saudavel: aplica/recarrega Prometheus se e somente se
# obs/prometheus.yml, obs/alerts.yml ou docker-compose.obs.yml mudaram neste
# deploy. Falha NAO faz rollback do app (desproporcional), mas o script sai !=0
# para o systemd marcar a unit como failed — sem sucesso falso.
if ! obs_run apply "$LOCAL" "$REMOTE"; then
    log "OBS FAIL — Prometheus NAO refletiu a config nova (app segue saudavel em $REMOTE)"
    log "DEPLOY PARCIAL sha=$REMOTE"
    exit 1
fi

log "DEPLOY OK sha=$REMOTE"

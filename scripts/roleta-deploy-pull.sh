#!/bin/bash
# ROLETA-DEPLOY-PULL — marcador estavel do entrypoint canonico. O shim (SPR-D2)
# recusa executar um alvo que nao o contenha (arquivo vazio/truncado passa em
# `bash -n` e sairia 0, fingindo deploy bem-sucedido para sempre).
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
#  11) SPR-D2 (16/08): sync_nginx_conf() — instala `roleta.conf` no vhost do
#      host (candidato pre-validado -> mv atomico -> nginx -t global -> reload,
#      com rollback do backup). Roda tambem no tick NOOP: o vhost e estado
#      convergente, nao subproduto de um commit novo.
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

# >>> SPR-D2 NGINX CONF BEGIN (sentinela usada por tests/test_spr_d2_ultima_milha.py —
# o teste extrai daqui até o END para exercitar a instalação do conf sem rodar o deploy)
# --- Instalação do `roleta.conf` pelo próprio deploy (SPR-D2, 16/08/2026) ----
# BURACO CORRIGIDO: `roleta.conf` era fonte versionada que NENHUM deploy instalava.
# O deploy fazia `nginx -t` + `reload` (do frontend) mas nunca copiava o arquivo, e
# o nginx do host seguia servindo a cópia manual antiga. Foi por isso que o merge do
# SPR-D1 não curou o 502: `/health` e `/metrics` existiam no repo e respondiam 404
# em produção — "mergeou" ≠ "implantado".
#
# ORDEM DOS GATES (importa): valida o CANDIDATO antes de tocar no destino. Instalar
# primeiro e testar depois deixa uma janela em que um `reload` de terceiro (o hook
# do certbot, por exemplo) carregaria um vhost inválido. Aqui:
#   1) escreve o candidato num arquivo OCULTO do mesmo diretório (o ponto inicial
#      impede que `include sites-enabled/*` o veja em voo; e mesmo diretório garante
#      que o `mv` seja rename atômico, não cópia);
#   2) `nginx -t` num prefixo isolado que inclui SÓ o candidato -> reprovou, aborta
#      com o destino intacto;
#   3) backup + `mv` atômico;
#   4) `nginx -t` GLOBAL (autoridade final, no contexto real) -> reprovou, restaura
#      o backup, reconfere e sai != 0;
#   5) `reload`.
# Idempotente: sem diff (`cmp -s`), não encosta no nginx.
NGINX_CONF_SYNC="${NGINX_CONF_SYNC:-1}"
NGINX_CONF_SRC="${NGINX_CONF_SRC:-$REPO_DIR/roleta.conf}"
NGINX_CONF_DST="${NGINX_CONF_DST:-}"
# Layout do host é incerteza conhecida (o agente não faz ssh): tenta os caminhos
# usuais e aceita override explícito. Documentado no runbook §3.
NGINX_CONF_CANDIDATES="${NGINX_CONF_CANDIDATES:-/etc/nginx/sites-available/roleta.conf /etc/nginx/sites-enabled/roleta.conf /etc/nginx/conf.d/roleta.conf /etc/nginx/sites-available/roleta}"
# Backups FORA das pastas do nginx: um `.bak` dentro de sites-enabled/ seria
# carregado pelo glob `include sites-enabled/*` e duplicaria o server block.
NGINX_BACKUP_DIR="${NGINX_BACKUP_DIR:-$STATE_DIR/nginx}"
NGINX_BACKUP_KEEP="${NGINX_BACKUP_KEEP:-10}"
NGINX_CONF_PREVALIDATE="${NGINX_CONF_PREVALIDATE:-1}"
# Marca "arquivo trocado, reload ainda não confirmado". Sem isso, um SIGKILL/reboot
# entre o `mv` e o `reload` (ou um reload que falha) deixaria o tick seguinte com
# `cmp` igual -> no-op -> nginx servindo a config velha da memória PARA SEMPRE.
NGINX_RELOAD_PENDING="${NGINX_RELOAD_PENDING:-$NGINX_BACKUP_DIR/.reload-pending}"

resolve_nginx_conf_dst() {
    local cand target found="" seen=""
    if [ -n "$NGINX_CONF_DST" ]; then
        printf '%s' "$NGINX_CONF_DST"
        return 0
    fi
    # shellcheck disable=SC2086 — lista separada por espaço, split é intencional
    for cand in $NGINX_CONF_CANDIDATES; do
        [ -e "$cand" ] || continue
        target="$cand"
        # Symlink (layout Debian: sites-enabled/x -> sites-available/x): escreve no
        # ALVO. Um `mv` sobre o link o substituiria por arquivo comum, quebrando a
        # convenção do host e deixando sites-available com a cópia velha.
        if [ -L "$cand" ]; then
            target="$(readlink -f "$cand" 2>/dev/null || true)"
            [ -n "$target" ] && [ -f "$target" ] || target="$cand"
        fi
        case " $seen " in *" $target "*) continue;; esac
        seen="$seen $target"
        [ -n "$found" ] || found="$target"
    done
    [ -n "$found" ] || return 1
    # Dois arquivos REAIS distintos: qual é o ativo? Adivinhar produziria "sucesso"
    # atualizando o inativo. Falha fechada pedindo NGINX_CONF_DST explícito.
    if [ "$seen" != " $found" ]; then
        printf '%s' "AMBIGUO:$seen"
        return 2
    fi
    printf '%s' "$found"
    return 0
}

# `nginx -T` lista os arquivos REALMENTE carregados. Serve de prova de que o
# destino escolhido é o ativo — sem isso, instalar num vhost desabilitado passaria
# em `nginx -t`, no reload e no healthcheck do frontend, reportando falso sucesso.
# 0 = ativo | 1 = inativo (dump obtido e o arquivo não está nele) | 2 = indeterminado.
nginx_conf_is_active() {
    local dst="$1" dump
    dump="$(nginx -T 2>/dev/null)" || return 2
    [ -n "$dump" ] || return 2
    case "$dump" in *"$dst"*) return 0;; esac
    return 1
}

# Valida o candidato num prefixo isolado, SEM tocar no destino. Falso-negativo
# possível (se o vhost dependesse de algo do `http` real — hoje não depende);
# escape documentado: NGINX_CONF_PREVALIDATE=0.
prevalidate_nginx_conf() {
    local candidate="$1" dir out
    [ "$NGINX_CONF_PREVALIDATE" = "1" ] || return 0
    dir="$(mktemp -d 2>/dev/null)" || {
        log "NGINX CONF PRE-VALIDACAO indisponivel — mktemp falhou; abortando (falha fechada, use NGINX_CONF_PREVALIDATE=0 para pular de propósito)"
        return 1
    }
    {
        echo "pid $dir/nginx.pid;"
        echo "error_log $dir/error.log;"
        echo "events { worker_connections 64; }"
        echo "http {"
        echo "    include $candidate;"
        echo "}"
    } > "$dir/nginx.conf"
    if out="$(nginx -t -p "$dir" -c "$dir/nginx.conf" 2>&1)"; then
        rm -rf "$dir" 2>/dev/null || true
        return 0
    fi
    log "NGINX CONF PRE-VALIDACAO reprovou o candidato: $(printf '%s' "$out" | tr '\n' ' ')"
    rm -rf "$dir" 2>/dev/null || true
    return 1
}

prune_nginx_backups() {
    local f
    { ls -1t "$NGINX_BACKUP_DIR"/*.bak.* 2>/dev/null || true; } |
        tail -n "+$((NGINX_BACKUP_KEEP + 1))" |
        while read -r f; do rm -f "$f" 2>/dev/null || true; done
    return 0
}

# 0 = em dia / instalado com sucesso / passo não aplicável; 1 = falha VISÍVEL.
sync_nginx_conf() {
    local dst rc tmp backup ts installed=0 active
    [ "$NGINX_CONF_SYNC" = "1" ] || return 0
    command -v nginx >/dev/null 2>&1 || return 0
    [ -f "$NGINX_CONF_SRC" ] || {
        log "NGINX CONF FALHA — fonte versionada ausente ($NGINX_CONF_SRC); o repo deveria sempre tê-la"
        return 1
    }

    dst="$(resolve_nginx_conf_dst)" && rc=0 || rc=$?
    if [ "$rc" = "2" ]; then
        log "NGINX CONF MULTIPLOS DESTINOS reais (${dst#AMBIGUO:} ) — nao da para adivinhar o ativo"
        log "NGINX CONF defina NGINX_CONF_DST no Environment= da unit (docs/runbooks/servidor-502-glassbox.md secao 3)"
        return 1
    fi
    if [ "$rc" != "0" ]; then
        log "NGINX CONF DESTINO NAO ENCONTRADO — candidatos: $NGINX_CONF_CANDIDATES"
        log "NGINX CONF defina NGINX_CONF_DST no Environment= da unit (docs/runbooks/servidor-502-glassbox.md secao 3)"
        return 1
    fi

    if cmp -s "$NGINX_CONF_SRC" "$dst"; then
        # Em dia no disco. Só é no-op se o reload do tick anterior tiver confirmado.
        [ -f "$NGINX_RELOAD_PENDING" ] || return 0
        log "NGINX CONF RELOAD PENDENTE de um tick anterior — arquivo ja em dia, revalidando e recarregando"
    else
        log "NGINX CONF diff detectado — $NGINX_CONF_SRC difere de $dst"

        if ! mkdir -p "$NGINX_BACKUP_DIR"; then
            log "NGINX CONF FALHA ao criar $NGINX_BACKUP_DIR — destino intacto"
            return 1
        fi

        tmp="$(dirname "$dst")/.$(basename "$dst").roleta-deploy.tmp"
        if ! cp -f "$NGINX_CONF_SRC" "$tmp"; then
            rm -f "$tmp" 2>/dev/null || true
            log "NGINX CONF FALHA ao escrever o candidato em $tmp — destino intacto"
            return 1
        fi
        chmod 644 "$tmp" 2>/dev/null || true

        if ! prevalidate_nginx_conf "$tmp"; then
            rm -f "$tmp" 2>/dev/null || true
            log "NGINX CONF ABORTADO — candidato invalido; $dst permanece como estava"
            return 1
        fi

        ts="$(date -u +%Y%m%dT%H%M%SZ)"
        backup="$NGINX_BACKUP_DIR/$(basename "$dst").bak"
        if [ -e "$dst" ]; then
            if ! cp -f "$dst" "$backup" || ! cp -f "$dst" "$backup.$ts"; then
                rm -f "$tmp" 2>/dev/null || true
                log "NGINX CONF FALHA no backup de $dst — destino intacto"
                return 1
            fi
        else
            backup=""
            log "NGINX CONF destino inexistente ($dst) — primeira instalacao, sem backup"
        fi

        # Sentinela ANTES do mv: a partir daqui o disco pode divergir da memória do
        # nginx, e só o reload confirmado abaixo limpa a marca.
        : > "$NGINX_RELOAD_PENDING" 2>/dev/null || true

        if ! mv -f "$tmp" "$dst"; then
            rm -f "$tmp" 2>/dev/null || true
            rm -f "$NGINX_RELOAD_PENDING" 2>/dev/null || true
            log "NGINX CONF FALHA no mv atomico para $dst — destino intacto"
            return 1
        fi
        installed=1
    fi

    if ! nginx -t >/dev/null 2>&1; then
        log "NGINX CONF INVALIDO no contexto global apos instalar em $dst: $(nginx -t 2>&1 | tr '\n' ' ')"
        if [ "$installed" != "1" ]; then
            log "NGINX CONF sem rollback — nada foi instalado neste tick; conf global quebrada por outra causa"
            return 1
        fi
        if [ -n "$backup" ]; then
            # Restauração também atômica: um SIGKILL no meio de um `cp` direto sobre o
            # destino deixaria o vhost truncado.
            if cp -f "$backup" "$tmp" && mv -f "$tmp" "$dst" && nginx -t >/dev/null 2>&1; then
                rm -f "$NGINX_RELOAD_PENDING" 2>/dev/null || true
                log "NGINX CONF ROLLBACK ok — $dst restaurado de $backup"
            else
                rm -f "$tmp" 2>/dev/null || true
                log "NGINX CONF ROLLBACK INSTAVEL — $dst restaurado mas nginx -t segue falhando; intervencao do dono (runbook secao 3)"
            fi
        else
            rm -f "$dst" 2>/dev/null || true
            rm -f "$NGINX_RELOAD_PENDING" 2>/dev/null || true
            log "NGINX CONF ROLLBACK ok — $dst removido (nao existia antes desta tentativa)"
        fi
        return 1
    fi

    if ! systemctl reload nginx >/dev/null 2>&1; then
        log "NGINX RELOAD FALHOU com conf valido em $dst — nginx segue servindo a config antiga da memoria; o proximo tick tenta de novo (marca de pendencia mantida)"
        return 1
    fi
    rm -f "$NGINX_RELOAD_PENDING" 2>/dev/null || true

    prune_nginx_backups
    log "NGINX CONF instalado -> $dst (backup ${backup:-nenhum}${ts:+ + $ts}) + reload ok"

    # Última defesa contra falso sucesso: o arquivo pode estar perfeito e simplesmente
    # não ser carregado (vhost em sites-available sem symlink em sites-enabled).
    nginx_conf_is_active "$dst" && active=0 || active=$?
    if [ "$active" = "1" ]; then
        log "NGINX CONF DESTINO INATIVO — $dst nao aparece no 'nginx -T'; o vhost servido NAO e este"
        log "NGINX CONF habilite o vhost (ln -s para sites-enabled) ou ajuste NGINX_CONF_DST (runbook secao 3)"
        return 1
    fi
    return 0
}
# <<< SPR-D2 NGINX CONF END

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
    tick_rc=0
    if ! self_heal_tick; then
        tick_rc=1
    fi
    # SPR-D2: o vhost também é estado convergente. Um tick sem commit novo ainda
    # tem de reconciliar o nginx com a fonte versionada — foi exatamente essa
    # divergência silenciosa que manteve o 502 vivo depois do merge do SPR-D1.
    if ! sync_nginx_conf; then
        tick_rc=1
    fi
    if [ "$tick_rc" != "0" ]; then
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

# --- Vhost do nginx (SPR-D2, 16/08/2026): o conf também é entregável --------
# Roda com o backend JÁ saudável e antes do sync de frontend (assim o reload do
# frontend já encontra o vhost novo). Falha aqui não faz rollback do app — seria
# desproporcional derrubar um backend saudável — mas contamina o status final:
# `DEPLOY PARCIAL` + exit != 0, para o systemd marcar a unit como failed em vez
# de reportar sucesso com o nginx servindo um vhost velho (o 502 de 16/08).
NGINX_CONF_FAIL=0
if ! sync_nginx_conf; then
    NGINX_CONF_FAIL=1
    log "NGINX CONF FALHOU — app saudavel em $REMOTE, mas o vhost do host NAO reflete o repo"
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
#
# SPR-D2 (16/08/2026): com o SHIM instalado no entrypoint, a sonda passa a ser
# uma rede de seguranca de segunda linha — o shim le o deploy da main a cada
# tick, entao o congelamento deixa de ser possivel por construcao. A sonda segue
# aqui porque ela e quem denuncia um host que ainda NAO recebeu o bootstrap.
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

# SPR-D2: o passo de obs roda mesmo com o conf do nginx falhado (senão um vhost
# quebrado esconderia um drift silencioso de Prometheus). Só agora o tick assume
# o status parcial.
if [ "$NGINX_CONF_FAIL" != "0" ]; then
    log "DEPLOY PARCIAL sha=$REMOTE — vhost do nginx nao sincronizado (ver NGINX CONF acima)"
    exit 1
fi

log "DEPLOY OK sha=$REMOTE"

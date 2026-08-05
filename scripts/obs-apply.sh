#!/bin/bash
# OBS-INODE (05/08/2026) — aplica mudancas de observabilidade ao Prometheus.
#
# PROBLEMA QUE ESTE SCRIPT RESOLVE (incidente real de producao, 05/08/2026)
#   Depois do merge do SPR-V1, /root/roleta-cloud/obs/alerts.yml tinha 21 regras e o
#   container roleta-prometheus continuava servindo 18: o deploy usa `git reset --hard`,
#   que reescreve cada arquivo via temp+rename (NOVO INODE), enquanto a compose montava
#   `obs/alerts.yml` como bind DE ARQUIVO — e um bind de arquivo fixa o inode.
#   `POST /-/reload` nao adianta (rele o mesmo inode antigo); so recriar o container
#   remonta o caminho. Alem disso, ninguem no deploy tocava a stack de observabilidade,
#   entao a divergencia sobrevivia a qualquer numero de deploys.
#
# CORRECAO EM DUAS CAMADAS
#   1) docker-compose.obs.yml passou a montar o DIRETORIO `./obs:/etc/prometheus:ro`
#      (o diretorio nao e recriado pelo git -> acompanha a troca de inode dos arquivos).
#   2) este script, chamado pelo deploy: detecta -> valida -> aplica -> VERIFICA.
#
# USO
#   obs-apply.sh check  [OLD_SHA NEW_SHA]   valida a config nova (nao toca em container)
#   obs-apply.sh apply  [OLD_SHA NEW_SHA]   valida + aplica (reload ou recriacao) + verifica
#   obs-apply.sh resume                     retoma uma pendencia de um deploy anterior
#   obs-apply.sh force                      bootstrap manual: valida + recria + verifica
#
# SAIDA
#   0 = nada a fazer, ou aplicado E VERIFICADO.
#   1 = falha explicita (nunca "sucesso falso"): a pendencia fica gravada em
#       $STATE_DIR/obs_pending e o proximo deploy a retoma via `resume`.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
STATE_DIR="${STATE_DIR:-/var/lib/roleta-deploy}"

# Somente a compose de observabilidade: incluir docker-compose.pg.yml aqui quebraria
# a interpolacao (`${PG_PASSWORD:?...}`) em hosts sem a env. O nome do projeto continua
# derivando de $REPO_DIR, entao network (`roleta-cloud_default`) e o volume nomeado
# `prometheus-data` sao exatamente os mesmos da subida manual da stack.
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.obs.yml}"
PROM_SERVICE="${PROM_SERVICE:-prometheus}"
PROM_URL="${PROM_URL:-http://127.0.0.1:9090}"

# auto = pula em host sem a stack (dev), MAS falha se a stack ja existiu aqui antes
# (marcador $STATE_DIR/obs_seen) — um Prometheus que sumiu e incidente, nao "skip".
OBS_ENABLED="${OBS_ENABLED:-auto}"

OBS_WATCH="${OBS_WATCH:-obs/prometheus.yml obs/alerts.yml obs/*.rules.yml docker-compose.obs.yml}"
VERIFY_RETRIES="${VERIFY_RETRIES:-6}"
VERIFY_INTERVAL="${VERIFY_INTERVAL:-2}"
CURL_MAX_TIME="${CURL_MAX_TIME:-5}"

# Seams de teste (o harness injeta stubs sem mexer no PATH).
DOCKER_BIN="${DOCKER_BIN:-docker}"
CURL_BIN="${CURL_BIN:-curl}"

CONF_HOST="obs/prometheus.yml"
CONF_CTR="/etc/prometheus/prometheus.yml"
ALERTS_HOST="obs/alerts.yml"
ALERTS_CTR="/etc/prometheus/alerts.yml"

PENDING_FILE="$STATE_DIR/obs_pending"
SEEN_FILE="$STATE_DIR/obs_seen"

log() { echo "[$(date -u +%FT%TZ)] OBS $*"; }

# shellcheck disable=SC2086  # $COMPOSE_FILES precisa de word splitting
dc() { "$DOCKER_BIN" compose $COMPOSE_FILES "$@"; }

# --- pendencia -------------------------------------------------------------
pending_read() {
    if [ -f "$PENDING_FILE" ]; then
        head -1 "$PENDING_FILE" 2>/dev/null || true
    fi
}

pending_write() {
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    echo "$1" > "$PENDING_FILE" 2>/dev/null || true
}

pending_clear() { rm -f "$PENDING_FILE" 2>/dev/null || true; }

# --- deteccao --------------------------------------------------------------
# Ecoa: none | reload | recreate | escalated
resolve_action() {
    local old="$1" new="$2" act="none" changed="" pending=""

    if [ -n "$old" ] && [ -n "$new" ]; then
        # shellcheck disable=SC2086  # $OBS_WATCH e uma lista de pathspecs
        changed="$(git -C "$REPO_DIR" diff --name-only "$old" "$new" -- $OBS_WATCH 2>/dev/null || true)"
        if [ -n "$changed" ]; then
            # `<<<` em vez de `printf | grep`: com `pipefail`, o grep -q sai no
            # primeiro match, o produtor morre de SIGPIPE (141) e a pipeline
            # inteira e reportada como falha.
            if grep -qx 'docker-compose\.obs\.yml' <<< "$changed"; then
                act="recreate"
            else
                act="reload"
            fi
        fi
    fi

    # Uma pendencia de deploy anterior sempre escala (nunca rebaixa) a acao.
    pending="$(pending_read)"
    case "$pending" in
        escalated) act="escalated" ;;
        recreate)  act="recreate" ;;
        reload)    if [ "$act" = "none" ]; then act="reload"; fi ;;
    esac

    if [ -n "$changed" ]; then
        log "mudou: $(printf '%s' "$changed" | tr '\n' ' ')" >&2
    fi
    echo "$act"
}

# Ecoa o ID do container Prometheus EM EXECUCAO.
# `ps -q` (sem `-a`) de proposito: com `-a` entram os containers efemeros do
# `compose run --rm` que este proprio script cria para o promtool — e o nome deles
# (`<projeto>-prometheus-run-<id>`) ordena ANTES do roleta-prometheus. Verificar
# contra um desses (que carrega o MESMO bind novo) daria "sucesso" com o Prometheus
# real ainda servindo as regras velhas — exatamente o falso sucesso que o script existe
# para impedir. Sem `head` na pipeline (SIGPIPE + pipefail).
# rc: 0 = achou, 1 = nao ha container em execucao, 2 = docker falhou.
prom_cid() {
    local ids first
    ids="$(dc ps -q "$PROM_SERVICE" 2>/dev/null)" || return 2
    ids="${ids//$'\r'/}"
    if [ -z "${ids//[[:space:]]/}" ]; then
        return 1
    fi
    first="${ids%%$'\n'*}"
    if [ "$first" != "$ids" ]; then
        log "WARN mais de um container para '$PROM_SERVICE'; usando $first" >&2
    fi
    printf '%s\n' "$first"
}

# --- gate: a stack existe neste host? --------------------------------------
# 0 = seguir, 1 = pular (exit 0 legitimo), 2 = falhar
obs_gate() {
    local cid="" rc=0
    if [ "$OBS_ENABLED" = "0" ]; then
        log "desativado (OBS_ENABLED=0)"
        return 1
    fi

    # `|| rc=$?` mantem isto em contexto de condicao: nao mexer em `set -e` aqui
    # (um `set -e` aninhado religaria o errexit do chamador e mataria o script).
    cid="$(prom_cid)" || rc=$?

    if [ -n "$cid" ]; then
        mkdir -p "$STATE_DIR" 2>/dev/null || true
        if [ ! -f "$SEEN_FILE" ]; then
            echo "$PROM_SERVICE" > "$SEEN_FILE" 2>/dev/null || true
        fi
        return 0
    fi

    if [ "$OBS_ENABLED" = "1" ] || [ -f "$SEEN_FILE" ]; then
        log "FAIL servico '$PROM_SERVICE' fora do ar/ausente (rc=$rc) — a stack de observabilidade era esperada neste host"
        return 2
    fi

    log "skip — servico '$PROM_SERVICE' nao existe neste host"
    return 1
}

# --- validacao (antes de aplicar) ------------------------------------------
validate_config() {
    log "validando config nova (promtool check config)"
    if dc run --rm --no-deps --entrypoint /bin/promtool "$PROM_SERVICE" check config "$CONF_CTR"; then
        log "promtool ok"
        return 0
    fi
    log "FAIL promtool reprovou $CONF_HOST/$ALERTS_HOST — nada aplicado"
    return 1
}

# --- aplicacao -------------------------------------------------------------
do_reload() {
    log "reload via $PROM_URL/-/reload"
    if "$CURL_BIN" -fsS --max-time "$CURL_MAX_TIME" -X POST "$PROM_URL/-/reload" >/dev/null; then
        return 0
    fi
    log "FAIL POST /-/reload"
    return 1
}

# `up -d` (sem --force-recreate) e idempotente: recria quando a definicao do
# servico mudou (o caso do mount novo) e vira no-op nas retentativas — evita
# restart em loop a cada tick do timer se a verificacao continuar falhando.
# NUNCA usar --remove-orphans aqui (derrubaria os outros containers do projeto).
do_up() {
    local force="${1:-}"
    if [ -n "$force" ]; then
        log "recriando servico '$PROM_SERVICE' (--force-recreate; volume TSDB preservado)"
        dc up -d --no-deps --force-recreate "$PROM_SERVICE"
    else
        log "reconciliando servico '$PROM_SERVICE' (up -d; recria so se a definicao mudou)"
        dc up -d --no-deps "$PROM_SERVICE"
    fi
}

# --- verificacao (anti "sucesso falso") ------------------------------------
# Le os bytes que o CONTAINER enxerga no caminho montado. Usa `docker cp` (e nao
# `exec cat`) de proposito: nao depende de shell/coreutils dentro da imagem, entao
# continua valendo se o prom/prometheus virar distroless.
container_bytes() {
    local cid
    cid="$(prom_cid)" || return 1
    if [ -z "$cid" ]; then
        return 1
    fi
    "$DOCKER_BIN" cp "$cid:$1" - 2>/dev/null | tar -xO 2>/dev/null
}

# Compara o SHA-256 do arquivo no repo com o SHA-256 do que o container le.
# E o detector exato do bug do inode preso: bate byte a byte, e nao apenas
# "a contagem de regras parece certa" (pega ate mudanca de expr com contagem igual).
same_bytes() {
    local host_file="$1" ctr_path="$2" h c
    if [ ! -f "$REPO_DIR/$host_file" ]; then
        log "FAIL arquivo ausente no repo: $host_file"
        return 1
    fi
    h="$(sha256sum < "$REPO_DIR/$host_file" | awk '{print $1}')"
    c="$(container_bytes "$ctr_path" | sha256sum | awk '{print $1}')" || c=""
    if [ "$h" = "$c" ]; then
        return 0
    fi
    log "divergencia: $host_file (repo=${h:0:12}) != $ctr_path (container=${c:0:12})"
    return 1
}

verify_once() {
    local body=""

    if ! "$CURL_BIN" -fsS --max-time "$CURL_MAX_TIME" "$PROM_URL/-/ready" >/dev/null; then
        return 1
    fi

    body="$("$CURL_BIN" -fsS --max-time "$CURL_MAX_TIME" "$PROM_URL/metrics")" || body=""
    # ATENCAO: nada de `printf "$body" | grep -q`. O /metrics do Prometheus tem
    # centenas de KB e a metrica aparece cedo; o grep -q sai no primeiro match, o
    # produtor leva SIGPIPE (141) e o `pipefail` transforma isso em FALSO NEGATIVO
    # (verify nunca passaria, e todo deploy de obs escalaria para recriacao).
    if ! grep -q '^prometheus_config_last_reload_successful 1$' <<< "$body"; then
        log "prometheus_config_last_reload_successful != 1"
        return 1
    fi

    if ! same_bytes "$CONF_HOST" "$CONF_CTR"; then return 1; fi
    if ! same_bytes "$ALERTS_HOST" "$ALERTS_CTR"; then return 1; fi
    return 0
}

verify() {
    local i
    for i in $(seq 1 "$VERIFY_RETRIES"); do
        if verify_once; then
            log "verificado (try $i): config e regras do container == repo"
            report_rules
            return 0
        fi
        sleep "$VERIFY_INTERVAL"
    done
    log "FAIL verificacao apos $VERIFY_RETRIES tentativas"
    report_rules
    return 1
}

# Diagnostico (nunca decide sucesso/falha): quantas regras o arquivo declara vs
# quantas a API carregou — os numeros do incidente (18 carregadas x 21 no disco).
report_rules() {
    local declared loaded json
    declared="$(grep -cE '^[[:space:]]*-[[:space:]]*(alert|record):' "$REPO_DIR/$ALERTS_HOST" || true)"
    json="$("$CURL_BIN" -fsS --max-time "$CURL_MAX_TIME" "$PROM_URL/api/v1/rules" 2>/dev/null || true)"
    loaded="$(printf '%s' "$json" | grep -o '"query":' | wc -l | tr -d ' ' || true)"
    log "regras: arquivo=$declared carregadas=$loaded"
    if [ -n "$json" ] && [ "$declared" != "$loaded" ]; then
        log "WARN contagem de regras divergente (diagnostico)"
    fi
}

# --- comandos --------------------------------------------------------------
cmd_check() {
    local action="$1"
    if [ "$action" = "none" ]; then
        log "noop — nenhuma mudanca de observabilidade neste deploy"
        return 0
    fi
    validate_config
}

cmd_apply() {
    local action="$1"

    if [ "$action" = "none" ]; then
        log "noop — nenhuma mudanca de observabilidade neste deploy (Prometheus intocado)"
        return 0
    fi

    if ! validate_config; then
        return 1
    fi

    pending_write "$action"

    case "$action" in
        recreate)
            if ! do_up; then
                log "FAIL up -d $PROM_SERVICE"
                return 1
            fi
            ;;
        escalated)
            # Ja houve uma recriacao BEM-SUCEDIDA nesta pendencia; nao recria de novo.
            do_reload || true
            ;;
        reload)
            if ! do_reload; then
                return 1
            fi
            ;;
    esac

    if verify; then
        pending_clear
        log "aplicado e verificado (acao=$action)"
        return 0
    fi

    # Nao refletiu: e o inode preso (ou um reload que nao pegou). Recria UMA vez.
    # A marca `escalated` so e gravada DEPOIS que a recriacao deu certo — senao uma
    # falha transitoria do `up` trancaria a pendencia num estado que nunca mais recria
    # (e reload, por definicao, nao conserta inode preso).
    if [ "$action" != "escalated" ]; then
        log "estado do container nao reflete o repo — escalando para recriacao unica"
        if ! do_up force; then
            log "FAIL up -d --force-recreate $PROM_SERVICE (pendencia segue '$action' para nova tentativa)"
            return 1
        fi
        pending_write "escalated"
        if verify; then
            pending_clear
            log "aplicado e verificado apos recriacao (acao=$action)"
            return 0
        fi
    fi

    log "FAIL observabilidade NAO aplicada (acao=$action) — pendencia gravada em $PENDING_FILE"
    return 1
}

main() {
    local cmd="${1:-apply}" old="" new="" action="" gate=0

    case "$cmd" in
        check|apply|resume|force) shift || true ;;
        *) cmd="apply" ;;
    esac

    old="${1:-}"
    new="${2:-}"

    if [ ! -d "$REPO_DIR" ]; then
        log "FAIL REPO_DIR inexistente: $REPO_DIR"
        return 1
    fi
    cd "$REPO_DIR"

    if [ "$cmd" = "resume" ]; then
        action="$(pending_read)"
        if [ -z "$action" ]; then
            return 0
        fi
        log "retomando pendencia: $action"
    elif [ "$cmd" = "force" ]; then
        action="recreate"
        log "bootstrap manual (force): recriacao + verificacao"
    else
        action="$(resolve_action "$old" "$new")"
    fi

    if [ "$action" = "none" ] && [ "$cmd" != "force" ]; then
        log "noop — nenhuma mudanca de observabilidade neste deploy"
        return 0
    fi

    gate=0
    obs_gate || gate=$?

    # `check` so pode reprovar por CONFIG INVALIDA: o deploy trata a falha dele com
    # `git reset --hard` do app inteiro. Stack de obs ausente/fora do ar nao pode
    # abortar um deploy de aplicacao que era valido — quem sinaliza isso e o `apply`.
    if [ "$cmd" = "check" ]; then
        if [ "$gate" -ne 0 ]; then
            log "validacao pulada (stack indisponivel) — o passo apply decide o resto"
            return 0
        fi
        cmd_check "$action"
        return $?
    fi

    case "$gate" in
        1) pending_clear; return 0 ;;
        2) return 1 ;;
    esac

    if [ "$cmd" = "force" ]; then
        if ! validate_config; then
            return 1
        fi
        pending_write "recreate"
        if ! do_up force; then
            log "FAIL up -d --force-recreate $PROM_SERVICE"
            return 1
        fi
        pending_write "escalated"
        if verify; then
            pending_clear
            log "bootstrap ok"
            return 0
        fi
        log "FAIL bootstrap nao verificado"
        return 1
    fi

    cmd_apply "$action"
}

main "$@"

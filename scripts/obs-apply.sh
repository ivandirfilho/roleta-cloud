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
# O QUE CONTA COMO "APLICADO" (verificacao, nunca "o comando respondeu 200")
#   a) o Prometheus esta ready;
#   b) `prometheus_config_last_reload_successful` = 1 **e** o timestamp do ultimo reload
#      AVANCOU em relacao ao momento anterior a esta execucao (FRESCOR — o booleano
#      sozinho e "sticky": continua 1 do carregamento anterior mesmo que nada tenha sido
#      recarregado agora);
#   c) os bytes que o container le sao os mesmos do repo — lidos pela VISAO DO
#      PROCESSO (`docker exec`), nunca por `docker cp`: o daemon re-resolve o caminho
#      de origem no host, entao num bind de arquivo com inode trocado ele devolveria
#      os bytes NOVOS enquanto o processo continua lendo os ANTIGOS (tautologia);
#   d) o numero de regras carregadas na API bate com o declarado nos rule_files
#      (resolvidos com glob/subpath, fail-closed se algum padrao nao casar).
#   Qualquer uma que falhe = FALHA EXPLICITA. Sem sucesso falso.
#
# USO
#   obs-apply.sh check  [OLD_SHA NEW_SHA]   valida a config nova (nao toca em container)
#   obs-apply.sh apply  [OLD_SHA NEW_SHA]   valida + aplica (reload/recriacao) + verifica
#   obs-apply.sh resume                     retoma uma pendencia de um deploy anterior
#   obs-apply.sh force                      bootstrap manual: valida + recria + verifica
#
# SAIDA
#   0 = nada a fazer, ou aplicado E VERIFICADO.
#   1 = falha explicita. A pendencia fica em $STATE_DIR/obs_pending (action/escalated/sha)
#       e o proximo deploy a retoma via `resume`. Falha NUNCA limpa a pendencia.
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
# 0 = kill-switch operacional: pula SEM apagar a pendencia (retoma quando religar).
OBS_ENABLED="${OBS_ENABLED:-auto}"

OBS_WATCH="${OBS_WATCH:-obs/prometheus.yml obs/alerts.yml obs/*.rules.yml docker-compose.obs.yml}"

# Readiness tem orcamento PROPRIO e generoso: um Prometheus reiniciado pode passar
# minutos em WAL replay antes de responder /-/ready. Confundir "ainda subindo" com
# "nao aplicou" levaria a recriar o container no meio do replay, repetidamente.
READY_TIMEOUT="${READY_TIMEOUT:-120}"
READY_INTERVAL="${READY_INTERVAL:-3}"
# Ja ready, a config recarregada aparece em milissegundos; estas retentativas cobrem
# apenas o assentamento das metricas.
VERIFY_RETRIES="${VERIFY_RETRIES:-6}"
VERIFY_INTERVAL="${VERIFY_INTERVAL:-2}"
CURL_MAX_TIME="${CURL_MAX_TIME:-5}"

# Seams de teste (o harness injeta stubs sem mexer no PATH).
DOCKER_BIN="${DOCKER_BIN:-docker}"
CURL_BIN="${CURL_BIN:-curl}"

OBS_DIR="${OBS_DIR:-obs}"
MOUNT_TARGET="${MOUNT_TARGET:-/etc/prometheus}"
CONF_HOST="$OBS_DIR/prometheus.yml"
CONF_CTR="$MOUNT_TARGET/prometheus.yml"

PENDING_FILE="$STATE_DIR/obs_pending"
SEEN_FILE="$STATE_DIR/obs_seen"

TS_METRIC="prometheus_config_last_reload_success_timestamp_seconds"
OK_METRIC="prometheus_config_last_reload_successful"

# Vocabulario explicito da verificacao de conteudo. A distincao entre "nao consegui
# LER" e "li e esta diferente" e o que decide se recriar o container faz sentido:
# recriacao conserta inode preso, nao conserta daemon/API fora do ar.
RC_MATCH=0        # bate
RC_READ_ERROR=1   # nao foi possivel ler (transporte)  -> classe PROCESS
RC_MISMATCH=2     # leitura valida, conteudo divergente -> classe CONTENT

ACTION="none"     # none | reload | recreate
ESCALATED="0"     # 1 = ja houve recriacao forcada BEM-SUCEDIDA nesta pendencia
FORCE_FLAG=""     # "force" = bootstrap manual

log() { echo "[$(date -u +%FT%TZ)] OBS $*"; }

# shellcheck disable=SC2086  # $COMPOSE_FILES precisa de word splitting
dc() { "$DOCKER_BIN" compose $COMPOSE_FILES "$@"; }

# --- pendencia (action / escalated / sha) ----------------------------------
P_ACTION=""
P_ESC="0"
P_SHA=""

pending_load() {
    P_ACTION=""
    P_ESC="0"
    P_SHA=""
    if [ ! -f "$PENDING_FILE" ]; then
        return 0
    fi
    local k v
    while IFS='=' read -r k v; do
        case "$k" in
            action)    P_ACTION="$v" ;;
            sha)       P_SHA="$v" ;;
            # Formato antigo (uma palavra por linha). `escalated` so era gravado
            # depois de uma recriacao, entao a acao que ele representa e `recreate`
            # — mapear para `reload` rebaixaria a acao e travaria a re-escalada.
            escalated) if [ -n "$v" ]; then P_ESC="$v"; else P_ACTION="recreate"; P_ESC="1"; fi ;;
            reload|recreate) P_ACTION="$k" ;;
        esac
    done < "$PENDING_FILE"
}

pending_save() {
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    { echo "action=$1"; echo "escalated=$2"; echo "sha=$3"; } > "$PENDING_FILE" 2>/dev/null || true
}

# So e chamado depois de uma aplicacao COMPROVADA.
pending_clear() { rm -f "$PENDING_FILE" 2>/dev/null || true; }

# --- deteccao --------------------------------------------------------------
severity() {
    case "$1" in
        recreate) echo 2 ;;
        reload)   echo 1 ;;
        *)        echo 0 ;;
    esac
}

resolve() {
    local old="$1" new="$2" diff_act="none" out="" rc=0

    if [ -n "$old" ] && [ -n "$new" ]; then
        # shellcheck disable=SC2086  # $OBS_WATCH e uma lista de pathspecs
        out="$(git -C "$REPO_DIR" diff --name-only "$old" "$new" -- $OBS_WATCH 2>&1)" || rc=$?
        if [ "$rc" -ne 0 ]; then
            # Silenciar isso como "nada mudou" esconderia justamente o deploy que
            # precisava do reload. Falha de deteccao => acao conservadora.
            log "WARN git diff $old..$new falhou (rc=$rc): $(tr '\n' ' ' <<< "$out")"
            log "WARN assumindo mudanca de observabilidade (acao conservadora: recreate)"
            diff_act="recreate"
        elif [ -n "$out" ]; then
            log "mudou: $(tr '\n' ' ' <<< "$out")"
            if grep -qx 'docker-compose\.obs\.yml' <<< "$out"; then
                diff_act="recreate"
            else
                diff_act="reload"
            fi
        fi
    fi

    pending_load
    local pend="${P_ACTION:-none}"

    # Severidade manda: uma pendencia de `reload` NUNCA pode rebaixar um `recreate`
    # novo (era assim que uma troca real de mount/compose acabava pulada).
    if [ "$(severity "$diff_act")" -ge "$(severity "$pend")" ]; then
        ACTION="$diff_act"
    else
        ACTION="$pend"
    fi

    ESCALATED="$P_ESC"
    if [ "$(severity "$ACTION")" -gt "$(severity "$pend")" ]; then
        ESCALATED="0"   # acao mais severa que a pendente: pode escalar de novo
    fi
    if [ -n "$new" ] && [ "$P_SHA" != "$new" ]; then
        # Episodio novo (outro SHA — ou pendencia sem SHA, do formato antigo):
        # a escalada anterior nao vale mais, senao a recriacao ficaria bloqueada
        # por episodios inteiros enquanto o inode continua preso.
        ESCALATED="0"
    fi
}

# --- gate: a stack existe neste host? --------------------------------------
# Ecoa o ID do container Prometheus EM EXECUCAO.
# `ps -q` (sem `-a`) de proposito: com `-a` entram os containers efemeros do
# `compose run --rm` que este proprio script cria para o promtool — e o nome deles
# (`<projeto>-prometheus-run-<id>`) ordena ANTES do roleta-prometheus. Verificar
# contra um desses (que carrega o MESMO bind novo) daria "sucesso" com o Prometheus
# real ainda servindo as regras velhas.
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

# 0 = seguir, 1 = kill-switch (pular preservando pendencia), 2 = falhar,
# 3 = host que nunca teve a stack (pular; nao ha nada a preservar)
obs_gate() {
    local cid="" rc=0
    if [ "$OBS_ENABLED" = "0" ]; then
        log "desativado (OBS_ENABLED=0) — pendencia PRESERVADA para quando religar"
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
    return 3
}

# --- validacao (antes de aplicar) ------------------------------------------
# 0 = config valida | 1 = config INVALIDA (comprovado) | 2 = nao deu para validar.
# A distincao importa: a falha do `check` derruba o deploy do app com `git reset --hard`,
# e "o daemon nao respondeu"/"a imagem nao esta no host" nao e prova de config quebrada.
validate_config() {
    local out="" rc=0
    log "validando config nova (promtool check config)"
    out="$(dc run --rm --no-deps --entrypoint /bin/promtool "$PROM_SERVICE" check config "$CONF_CTR" 2>&1)" || rc=$?
    if [ "$rc" -eq 0 ]; then
        log "promtool ok"
        return 0
    fi
    if grep -qiE 'FAILED:|error (parsing|loading)|parsing YAML' <<< "$out"; then
        log "FAIL config INVALIDA (promtool rc=$rc): $(tr '\n' ' ' <<< "$out")"
        return 1
    fi
    log "INDISPONIVEL nao foi possivel executar o promtool (rc=$rc): $(tr '\n' ' ' <<< "$out")"
    log "INDISPONIVEL isto NAO e prova de config invalida — deploy do app nao e revertido por isto"
    return 2
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
# restart em loop a cada tick do timer. Por isso o reload vem SEMPRE depois:
# um `up -d` que virou no-op nao recarrega nada sozinho.
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

wait_ready() {
    local waited=0 step="$READY_INTERVAL"
    if [ "$step" -lt 1 ]; then step=1; fi
    while :; do
        if "$CURL_BIN" -fsS --max-time "$CURL_MAX_TIME" "$PROM_URL/-/ready" >/dev/null 2>&1; then
            if [ "$waited" -gt 0 ]; then
                log "ready apos ${waited}s"
            fi
            return 0
        fi
        if [ "$waited" -ge "$READY_TIMEOUT" ]; then
            log "FAIL Prometheus nao ficou ready em ${READY_TIMEOUT}s (WAL replay travado?)"
            return 1
        fi
        sleep "$step"
        waited=$((waited + step))
    done
}

# --- verificacao (anti "sucesso falso") ------------------------------------
metrics_body() {
    "$CURL_BIN" -fsS --max-time "$CURL_MAX_TIME" "$PROM_URL/metrics" 2>/dev/null
}

# Extrai o valor de uma metrica sem series/labels. `<<<` em vez de pipe: com
# `pipefail`, um `grep -q`/`-m1` no fim de pipeline mata o produtor com SIGPIPE
# e a pipeline inteira e reportada como falha.
metric_value() {
    local body="$1" name="$2" v=""
    v="$(grep -m1 "^${name} " <<< "$body" | awk '{print $2}')" || v=""
    printf '%s' "$v"
}

reload_ts() {
    local body v
    body="$(metrics_body)" || body=""
    if [ -n "$body" ]; then
        v="$(metric_value "$body" "$TS_METRIC")"
        if [ -n "$v" ]; then
            printf '%s' "$v"
            return 0
        fi
    fi
    # Sem baseline legivel (Prometheus reiniciando, /metrics fora do ar), o relogio
    # do host serve — container e host compartilham o clock do kernel, entao exigir
    # "recarregou depois de agora" e uma baseline mais forte, nunca mais fraca.
    printf '%s' "$(( $(date +%s) - 2 ))"
}

# a > b (floats do Prometheus)
is_newer() {
    awk -v a="${1:-0}" -v b="${2:-0}" 'BEGIN { exit !(a + 0 > b + 0) }'
}

# Le o hash do arquivo COMO O PROCESSO DENTRO DO CONTAINER o enxerga.
#
# NAO usar `docker cp`: o daemon re-resolve o caminho de ORIGEM NO HOST para um bind
# mount, entao num bind de ARQUIVO com inode trocado ele devolve os bytes NOVOS
# enquanto o processo continua lendo os ANTIGOS. A comparacao viraria host x host —
# tautologia — e passaria exatamente no cenario do incidente. `docker exec` executa
# no mount namespace do container e e a unica leitura que prova o que o Prometheus le.
#
# Fail-closed: se nao houver como ler pela visao do container, a verificacao REPROVA
# (nao ha prova de que a config chegou), em vez de cair num leitor que mente.
container_sha() {
    local cid="$1" path="$2" out=""
    if out="$("$DOCKER_BIN" exec "$cid" sha256sum "$path" 2>/dev/null)"; then
        printf '%s' "$out" | awk '{print $1}'
        return 0
    fi
    if out="$("$DOCKER_BIN" exec "$cid" cat "$path" 2>/dev/null | sha256sum)"; then
        printf '%s' "$out" | awk '{print $1}'
        return 0
    fi
    return 1
}

# MATCH | READ_ERROR (nao deu para ler) | MISMATCH (leu e esta diferente)
same_bytes() {
    local host_file="$1" ctr_path="$2" h c cid
    if [ ! -f "$host_file" ]; then
        log "FAIL arquivo ausente no repo: $host_file"
        return "$RC_READ_ERROR"
    fi
    h="$(sha256sum < "$host_file" | awk '{print $1}')"
    cid="$(prom_cid)" || cid=""
    if [ -z "$cid" ]; then
        # nao conseguimos nem chegar no container: transporte, nao conteudo
        log "FAIL sem container em execucao para ler $ctr_path"
        return "$RC_READ_ERROR"
    fi
    if ! c="$(container_sha "$cid" "$ctr_path")"; then
        log "FAIL nao foi possivel ler $ctr_path pela visao do container (imagem sem sha256sum/cat? container sumiu?)"
        return "$RC_READ_ERROR"
    fi
    if [ "$h" = "$c" ]; then
        return "$RC_MATCH"
    fi
    log "FAIL divergencia: $host_file (repo=${h:0:12}) != $ctr_path (container=${c:0:12})"
    return "$RC_MISMATCH"
}

# --- rule_files: resolucao com glob/subpath --------------------------------
# Entradas cruas do bloco `rule_files:` do prometheus.yml.
rule_file_names() {
    awk '
        /^rule_files:/            { inblk = 1; next }
        inblk && /^[[:space:]]*-/ { sub(/^[[:space:]]*-[[:space:]]*/, ""); gsub(/["'"'"']/, ""); print; next }
        inblk && /^[^[:space:]]/  { inblk = 0 }
    ' "$REPO_DIR/$CONF_HOST"
}

# Ecoa "<caminho no container>|<caminho no host>" para CADA arquivo de regra,
# expandindo globs e preservando subdiretorios. Usar basename e ignorar globs fazia
# `/etc/prometheus/*.rules.yml` valer 0 regras declaradas — e 0 != carregadas vira
# falha (e recriacao) eterna. Zero correspondencia e FAIL-CLOSED: config que aponta
# para arquivo inexistente nao pode ser tratada como "nenhuma regra" — guardrail
# deliberadamente MAIS ESTRITO que o Prometheus, que ignora glob vazio em silencio.
# A saida e DEDUPLICADA: `alerts.yml` + `*alerts.yml` resolvem o mesmo arquivo, e
# conta-lo duas vezes faria declared != loaded para sempre.
rule_file_targets() {
    local pattern host_pattern matches f rel seen=""
    while IFS= read -r pattern; do
        if [ -z "$pattern" ]; then
            continue
        fi
        case "$pattern" in
            /*) ;;                                    # absoluto no container
            *)  pattern="$MOUNT_TARGET/$pattern" ;;   # relativo ao dir da config
        esac
        case "$pattern" in
            "$MOUNT_TARGET"/*) host_pattern="$REPO_DIR/$OBS_DIR/${pattern#"$MOUNT_TARGET"/}" ;;
            *)
                # `log` vai para stderr: esta funcao e consumida por `$(...)`, entao
                # qualquer coisa em stdout viraria "alvo" no lugar de mensagem.
                log "FAIL rule_file fora do diretorio montado ($MOUNT_TARGET): $pattern" >&2
                return 1
                ;;
        esac
        if ! matches="$(compgen -G "$host_pattern")"; then
            log "FAIL rule_files sem correspondencia no repo: $pattern (procurado em $host_pattern)" >&2
            return 1
        fi
        while IFS= read -r f; do
            if [ ! -f "$f" ]; then
                continue
            fi
            case "$seen" in
                *"|$f|"*) continue ;;   # ja emitido por outro padrao
            esac
            seen="$seen|$f|"
            rel="${f#"$REPO_DIR/$OBS_DIR/"}"
            printf '%s|%s\n' "$MOUNT_TARGET/$rel" "$f"
        done <<< "$matches"
    done < <(rule_file_names)
}

declared_rules() {
    local total=0 line host n
    while IFS= read -r line; do
        if [ -z "$line" ]; then
            continue
        fi
        host="${line#*|}"
        n="$(grep -cE '^[[:space:]]*-[[:space:]]*(alert|record):' "$host")" || n=0
        total=$((total + n))
    done <<< "$1"
    printf '%s' "$total"
}

# Config + TODOS os rule_files resolvidos (ja deduplicados): os alvos do byte-check
# saem da MESMA lista usada para contar as regras declaradas.
# MATCH | READ_ERROR | MISMATCH — propaga a classe do primeiro alvo que falhar.
content_matches() {
    local targets="$1" line rc="$RC_MATCH"
    same_bytes "$REPO_DIR/$CONF_HOST" "$CONF_CTR" || rc=$?
    if [ "$rc" -ne "$RC_MATCH" ]; then
        return "$rc"
    fi
    while IFS= read -r line; do
        if [ -z "$line" ]; then
            continue
        fi
        rc="$RC_MATCH"
        same_bytes "${line#*|}" "${line%%|*}" || rc=$?
        if [ "$rc" -ne "$RC_MATCH" ]; then
            return "$rc"
        fi
    done <<< "$targets"
    return "$RC_MATCH"
}

# Contagem de regras REALMENTE carregadas: cada objeto de regra da API tem
# exatamente um campo "query" (os objetos de grupo nao tem). E o numero que
# denunciou o incidente (18 carregadas x 21 no arquivo).
# MATCH | READ_ERROR (API fora do ar/invalida) | MISMATCH (declared != loaded)
rules_ok() {
    local targets="$1" declared loaded json
    declared="$(declared_rules "$targets")"
    json="$("$CURL_BIN" -fsS --max-time "$CURL_MAX_TIME" "$PROM_URL/api/v1/rules" 2>/dev/null)" || json=""
    if [ -z "$json" ]; then
        # nao conseguimos LER a API: recriar o container nao conserta isso
        log "FAIL /api/v1/rules indisponivel — impossivel provar que as regras carregaram"
        return "$RC_READ_ERROR"
    fi
    if ! grep -q '"status":[[:space:]]*"success"' <<< "$json"; then
        log "FAIL /api/v1/rules sem status=success (resposta invalida)"
        return "$RC_READ_ERROR"
    fi
    loaded="$(grep -o '"query":' <<< "$json" | wc -l | tr -d '[:space:]')" || loaded="0"
    loaded="${loaded:-0}"
    if [ "$declared" != "$loaded" ]; then
        log "FAIL regras: arquivo=$declared carregadas=$loaded (sintoma exato do incidente 21x18)"
        return "$RC_MISMATCH"
    fi
    log "regras ok: arquivo=$declared carregadas=$loaded"
    return "$RC_MATCH"
}

# 0 = verificado | 1 = falha de PROCESSO/TRANSPORTE (recriar nao conserta) |
# 2 = CONTEUDO divergente com leitura valida (assinatura do inode preso)
verify_once() {
    local before="${1:-0}" body="" ok="" ts="" targets="" rc=0

    body="$(metrics_body)" || body=""
    if [ -z "$body" ]; then
        log "/metrics indisponivel"
        return 1
    fi

    ok="$(metric_value "$body" "$OK_METRIC")"
    if [ "$ok" != "1" ]; then
        log "$OK_METRIC=${ok:-<ausente>} (esperado 1)"
        return 1
    fi

    # FRESCOR: o booleano acima e sticky — continua 1 de um carregamento antigo.
    # So o timestamp avancando prova que a config foi recarregada AGORA.
    ts="$(metric_value "$body" "$TS_METRIC")"
    if ! is_newer "$ts" "$before"; then
        log "FAIL frescor: ultimo reload em ${ts:-<ausente>} nao avancou (antes=$before) — nada foi recarregado"
        return 1
    fi

    if ! targets="$(rule_file_targets)"; then
        return 1
    fi

    # Daqui para baixo o processo esta comprovadamente saudavel e recarregou agora.
    # READ_ERROR continua sendo classe PROCESS: recriar o container nao conserta um
    # transporte quebrado (API fora do ar, docker exec falho) — e recriaria a toa.
    rc="$RC_MATCH"
    content_matches "$targets" || rc=$?
    if [ "$rc" -ne "$RC_MATCH" ]; then return "$rc"; fi
    rc="$RC_MATCH"
    rules_ok "$targets" || rc=$?
    if [ "$rc" -ne "$RC_MATCH" ]; then return "$rc"; fi
    return 0
}

verify() {
    local before="${1:-0}" i rc=1
    for i in $(seq 1 "$VERIFY_RETRIES"); do
        rc=0
        verify_once "$before" || rc=$?
        if [ "$rc" -eq 0 ]; then
            log "verificado (try $i): ready + reload fresco + bytes == repo + regras carregadas"
            return 0
        fi
        sleep "$VERIFY_INTERVAL"
    done
    log "FAIL verificacao apos $VERIFY_RETRIES tentativas (classe=$([ "$rc" -eq 2 ] && echo conteudo || echo processo))"
    return "$rc"
}

# ready -> reload (SEMPRE, inclusive depois de up/recriacao: um `up -d` que virou
# no-op nao recarrega nada) -> verificacao com frescor.
apply_and_verify() {
    local before="${1:-0}" rc=0
    if ! wait_ready; then return 1; fi
    if ! do_reload; then return 1; fi
    verify "$before" || rc=$?
    return "$rc"
}

do_apply() {
    local sha="$1" rc=0 before="0"

    validate_config || rc=$?
    if [ "$rc" -eq 1 ]; then
        log "FAIL config invalida — nada aplicado (pendencia mantida)"
        return 1
    fi
    if [ "$rc" -eq 2 ]; then
        log "FAIL validacao indisponivel — nada aplicado (pendencia mantida para o proximo tick)"
        return 1
    fi

    before="$(reload_ts)"

    if [ "$ACTION" = "recreate" ] || [ -n "$FORCE_FLAG" ]; then
        if ! do_up "$FORCE_FLAG"; then
            log "FAIL up -d $PROM_SERVICE (pendencia mantida)"
            return 1
        fi
        if [ -n "$FORCE_FLAG" ]; then
            ESCALATED="1"
            pending_save "$ACTION" "1" "$sha"
        fi
    fi

    rc=0
    apply_and_verify "$before" || rc=$?
    if [ "$rc" -eq 0 ]; then
        pending_clear
        log "aplicado e verificado (acao=$ACTION)"
        return 0
    fi

    # Escalar so com EVIDENCIA de que recriar resolve. Falha de PROCESSO (POST
    # recusado, reload rejeitado, nunca ficou ready) nao e consertada por recriacao —
    # e e pior: recriar um Prometheus que ainda servia a ultima config boa pode
    # transformar um problema de recarga em crash loop e reiniciar o WAL replay.
    if [ "$rc" -ne 2 ]; then
        log "FAIL observabilidade NAO aplicada (acao=$ACTION) — falha de PROCESSO; recriacao nao ajudaria (pendencia mantida)"
        return 1
    fi

    if [ "$ESCALATED" = "1" ]; then
        log "FAIL conteudo ainda divergente (acao=$ACTION) — ja houve recriacao nesta pendencia, nao recria de novo"
        return 1
    fi

    # Processo comprovadamente saudavel (ready + reload fresco e bem-sucedido) mas
    # com conteudo divergente: e a assinatura do inode preso, e ai sim recriar
    # conserta. A marca `escalated` so vai para a pendencia DEPOIS que a recriacao
    # deu certo — senao uma falha transitoria do `up` trancaria a pendencia num
    # estado que nunca mais recria.
    log "processo saudavel e conteudo divergente — escalando para recriacao unica"
    before="$(reload_ts)"
    if ! do_up force; then
        log "FAIL up -d --force-recreate $PROM_SERVICE (pendencia segue '$ACTION' para nova tentativa)"
        return 1
    fi
    pending_save "$ACTION" "1" "$sha"

    if apply_and_verify "$before"; then
        pending_clear
        log "aplicado e verificado apos recriacao (acao=$ACTION)"
        return 0
    fi

    log "FAIL observabilidade NAO aplicada (acao=$ACTION) — pendencia em $PENDING_FILE"
    return 1
}

main() {
    local cmd="${1:-apply}" old="" new="" sha="" gate=0 rc=0

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

    case "$cmd" in
        resume)
            pending_load
            if [ -z "$P_ACTION" ]; then
                return 0
            fi
            ACTION="$P_ACTION"
            ESCALATED="$P_ESC"
            sha="$P_SHA"
            log "retomando pendencia: acao=$ACTION escalated=$ESCALATED sha=${sha:-?}"
            ;;
        force)
            ACTION="recreate"
            ESCALATED="0"
            FORCE_FLAG="force"
            pending_load
            sha="${P_SHA:-manual}"
            log "bootstrap manual (force): recriacao + verificacao"
            ;;
        *)
            resolve "$old" "$new"
            sha="$new"
            ;;
    esac

    if [ "$ACTION" = "none" ]; then
        log "noop — nenhuma mudanca de observabilidade neste deploy (Prometheus intocado)"
        return 0
    fi

    gate=0
    obs_gate || gate=$?

    # `check` so pode reprovar por CONFIG INVALIDA COMPROVADA: o deploy trata a falha
    # dele com `git reset --hard` do app inteiro. Stack ausente/fora do ar ou promtool
    # inexecutavel nao podem abortar um deploy de aplicacao que era valido — quem
    # sinaliza isso e o `apply`.
    if [ "$cmd" = "check" ]; then
        if [ "$gate" -ne 0 ]; then
            log "validacao adiada (stack indisponivel) — quem decide e o passo apply"
            return 0
        fi
        rc=0
        validate_config || rc=$?
        if [ "$rc" -eq 1 ]; then
            return 1
        fi
        if [ "$rc" -eq 2 ]; then
            log "validacao adiada (promtool inexecutavel) — quem decide e o passo apply"
        fi
        return 0
    fi

    # A acao resolvida tem de sobreviver a ESTE processo antes de qualquer saida.
    # Sem isto, um kill-switch ou um Prometheus fora do ar descartariam a mudanca
    # detectada: no tick seguinte LOCAL==REMOTE, nao ha pendencia para retomar, e o
    # diff dos deploys seguintes ja nao contem aquela mudanca — ela se perde em
    # silencio, que e exatamente o incidente que este script existe para impedir.
    # Vale INCLUSIVE para gate=3 (host sem `obs_seen`): a stack pode estar apenas
    # temporariamente fora, e perder a mudanca por causa disso seria pior do que
    # carregar uma pendencia inofensiva num host que de fato nao roda a stack.
    pending_save "$ACTION" "$ESCALATED" "$sha"

    case "$gate" in
        1|3) return 0 ;;
        2)   return 1 ;;
    esac

    do_apply "$sha"
}

main "$@"

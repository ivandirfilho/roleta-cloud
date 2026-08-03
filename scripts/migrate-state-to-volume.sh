#!/usr/bin/env bash
# MIG-0: move the legacy host bind-mount state.json into roleta-data.
#
# Preconditions:
#   - run from a host with Docker access;
#   - stop roleta-cloud gracefully before running this script;
#   - keep the source file until the migration has soaked and been backed up.
#
# The operation is idempotent when source and destination already match. It
# refuses to overwrite a different destination so a bad restore cannot be
# hidden by a later deploy.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
VOLUME_NAME="${VOLUME_NAME:-}"
VOLUME_KEY="${VOLUME_KEY:-roleta-data}"
SOURCE_STATE="${SOURCE_STATE:-${REPO_DIR}/state.json}"
CONTAINER="${CONTAINER:-roleta-cloud}"

log() {
    printf '[migrate-state] %s\n' "$*"
}

die() {
    printf '[migrate-state] ERROR: %s\n' "$*" >&2
    exit 1
}

command -v docker >/dev/null 2>&1 || die "docker nao encontrado"
command -v python3 >/dev/null 2>&1 || die "python3 nao encontrado"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum nao encontrado"

[[ -f "$SOURCE_STATE" ]] || die "arquivo de origem ausente: $SOURCE_STATE"

cd "$REPO_DIR"

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER")"
    [[ "$running" != "true" ]] || die "pare $CONTAINER graciosamente antes da migracao"
fi

resolve_volume_name() {
    local candidates count resolved
    if [[ -n "$VOLUME_NAME" ]]; then
        printf '%s\n' "$VOLUME_NAME"
        return 0
    fi
    if resolved="$(
        docker compose config --format json 2>/dev/null |
            python3 -c 'import json, sys; print(json.load(sys.stdin)["volumes"][sys.argv[1]]["name"])' "$VOLUME_KEY" 2>/dev/null
    )" &&
        [[ -n "$resolved" ]]; then
        printf '%s\n' "$resolved"
        return 0
    fi
    candidates="$(docker volume ls --quiet --filter "label=com.docker.compose.volume=$VOLUME_KEY")" || return 1
    count="$(printf '%s\n' "$candidates" | sed '/^$/d' | wc -l)"
    if [[ "$count" == "1" ]]; then
        printf '%s\n' "$candidates" | sed -n '1p'
        return 0
    fi
    return 1
}

if [[ -z "$VOLUME_NAME" ]]; then
    VOLUME_NAME="$(resolve_volume_name)" ||
        die "nao foi possivel resolver o volume Compose: $VOLUME_KEY; use VOLUME_NAME explicitamente"
fi

mountpoint="$(docker volume inspect -f '{{.Mountpoint}}' "$VOLUME_NAME" 2>/dev/null)" \
    || die "volume Docker ausente: $VOLUME_NAME (chave Compose: $VOLUME_KEY)"
[[ -d "$mountpoint" ]] || die "mountpoint do volume ausente: $mountpoint"

python3 - "$SOURCE_STATE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    json.load(stream)
PY

target="$mountpoint/state.json"
if [[ -e "$target" ]]; then
    [[ -f "$target" ]] || die "destino existe mas nao e arquivo: $target"
    if cmp -s "$SOURCE_STATE" "$target"; then
        log "destino ja corresponde a origem; nada a fazer"
        exit 0
    fi
    die "destino ja existe e diverge; compare/autorize manualmente: $target"
fi

tmp_target="${target}.tmp.$$"
trap 'rm -f -- "$tmp_target"' EXIT
install -m 600 "$SOURCE_STATE" "$tmp_target"
mv -- "$tmp_target" "$target"
trap - EXIT

python3 - "$target" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    json.load(stream)
PY

source_sha="$(sha256sum "$SOURCE_STATE" | awk '{print $1}')"
target_sha="$(sha256sum "$target" | awk '{print $1}')"
[[ "$source_sha" == "$target_sha" ]] || die "checksum divergente apos a copia"
chmod 600 "$target"
log "migracao concluida: $SOURCE_STATE -> $target"
log "sha256=$source_sha"
log "mantenha a origem ate o fim do soak/backup"

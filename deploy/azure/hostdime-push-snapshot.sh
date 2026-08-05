#!/usr/bin/env bash
# Snapshot autoritativo HostDime -> container Blob dedicado, via SAS write-only.
set -euo pipefail
umask 077

CONTAINER_NAME="${CONTAINER_NAME:-roleta-cloud}"
DB_PATH="${DB_PATH:-}"
STATE_PATH="${STATE_PATH:-}"
AZURE_BLOB_BASE_URL="${AZURE_BLOB_BASE_URL:?defina a URL HTTPS do container Blob dedicado}"
AZURE_STORAGE_SAS_TOKEN="${AZURE_STORAGE_SAS_TOKEN:?defina o SAS Create+Write do container}"
BLOB_PREFIX="${BLOB_PREFIX:-snapshots/}"
WORK_DIR="${SNAPSHOT_WORK_DIR:-/var/lib/roleta-snapshots}"
LOCK_FILE="${LOCK_FILE:-/run/lock/roleta-hostdime-snapshot.lock}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

for cmd in curl docker gzip python3 sha256sum sqlite3 flock; do
  command -v "$cmd" >/dev/null || { echo "ERRO: comando ausente: $cmd" >&2; exit 1; }
done
[[ "$AZURE_BLOB_BASE_URL" =~ ^https://[A-Za-z0-9.-]+\.blob\.core\.windows\.net/[a-z0-9-]+$ ]] || {
  echo "ERRO: AZURE_BLOB_BASE_URL deve apontar para um container HTTPS" >&2
  exit 2
}
AZURE_STORAGE_SAS_TOKEN="${AZURE_STORAGE_SAS_TOKEN#\?}"
[ -n "$AZURE_STORAGE_SAS_TOKEN" ] || { echo "ERRO: SAS vazio" >&2; exit 2; }
BLOB_PREFIX="${BLOB_PREFIX#/}"
case "$BLOB_PREFIX" in
  ""|*".."*|*[!A-Za-z0-9._/-]*)
    echo "ERRO: BLOB_PREFIX invalido" >&2
    exit 2
    ;;
esac
[[ "$BLOB_PREFIX" == */ ]] || BLOB_PREFIX="${BLOB_PREFIX}/"

DATA_SOURCE="$(docker inspect "$CONTAINER_NAME" --format \
  '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}')"
[ -n "$DATA_SOURCE" ] || { echo "ERRO: mount /app/data não encontrado" >&2; exit 1; }
if [ -z "$DB_PATH" ]; then
  DB_PATH="$DATA_SOURCE/decisions.db"
fi
if [ -z "$STATE_PATH" ]; then
  STATE_PATH="$(docker inspect "$CONTAINER_NAME" --format \
    '{{range .Mounts}}{{if eq .Destination "/app/state.json"}}{{.Source}}{{end}}{{end}}')"
  # Antes do MIG-0 o state é bind em /app/state.json; depois, vive no volume.
  [ -n "$STATE_PATH" ] || STATE_PATH="$DATA_SOURCE/state.json"
fi
[ -f "$DB_PATH" ] || { echo "ERRO: decisions.db ausente em $DB_PATH" >&2; exit 1; }
[ -f "$STATE_PATH" ] || { echo "ERRO: state.json ausente em $STATE_PATH" >&2; exit 1; }
case "$DB_PATH" in *"'"*) echo "ERRO: DB_PATH contém aspas inválidas" >&2; exit 2 ;; esac

install -d -m 0700 "$WORK_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[hostdime-snapshot] outra execução ainda está ativa; pulando" >&2
  exit 0
fi

TMP="$(mktemp -d "$WORK_DIR/.snapshot.XXXXXX")"
trap 'rm -rf -- "$TMP"' EXIT
DB_SNAPSHOT="$TMP/decisions_${STAMP}.db"
STATE_SNAPSHOT="$TMP/state_${STAMP}.json"
METADATA="$TMP/metadata_${STAMP}.json"
MANIFEST="$TMP/manifest_${STAMP}.sha256"

sqlite3 "$DB_PATH" ".backup '$DB_SNAPSHOT'"
CHECK="$(sqlite3 "$DB_SNAPSHOT" 'PRAGMA integrity_check;')"
[ "$CHECK" = "ok" ] || {
  echo "ERRO: integrity_check do snapshot retornou: $CHECK" >&2
  exit 1
}
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$STATE_PATH"
install -m 0600 "$STATE_PATH" "$STATE_SNAPSHOT"

IMAGE_REF="$(docker inspect "$CONTAINER_NAME" --format '{{.Config.Image}}')"
python3 - "$DB_SNAPSHOT" "$STATE_SNAPSHOT" "$METADATA" "$STAMP" "$IMAGE_REF" <<'PY'
import datetime as dt
import json
import socket
import sqlite3
import sys

db_path, state_path, output_path, stamp, image_ref = sys.argv[1:]
with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
    count, max_id, max_ts = conn.execute(
        "SELECT COUNT(*), MAX(id), MAX(timestamp) FROM decisions"
    ).fetchone()
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
payload = {
    "source": "hostdime",
    "source_host": socket.gethostname(),
    "stamp": stamp,
    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "image": image_ref,
    "decisions_count": count,
    "decisions_max_id": max_id,
    "decisions_max_timestamp": max_ts,
    "state_spin_seq": state.get("spin_seq"),
}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True)
PY

gzip -9 "$DB_SNAPSHOT"
payloads=("$DB_SNAPSHOT.gz" "$STATE_SNAPSHOT" "$METADATA")
(
  cd "$TMP"
  : > "$(basename "$MANIFEST")"
  for file in "${payloads[@]}"; do
    sha256sum -- "$(basename "$file")" >> "$(basename "$MANIFEST")"
  done
)

upload_blob() {
  local file="$1"
  local blob="${BLOB_PREFIX}$(basename "$file")"
  local url="${AZURE_BLOB_BASE_URL}/${blob}?${AZURE_STORAGE_SAS_TOKEN}"
  printf 'url = "%s"\n' "$url" |
    curl --config - \
      --request PUT \
      --upload-file "$file" \
      --header 'x-ms-blob-type: BlockBlob' \
      --header 'x-ms-version: 2023-11-03' \
      --header 'If-None-Match: *' \
      --silent --show-error --fail \
      --retry 4 --retry-all-errors \
      --connect-timeout 10 --max-time 300
  echo "[hostdime-snapshot] enviado: $blob" >&2
}

for file in "${payloads[@]}"; do
  upload_blob "$file"
done
# O manifesto é o commit do snapshot e sempre sobe por último.
upload_blob "$MANIFEST"
echo "[hostdime-snapshot] OK stamp=$STAMP integrity_check=ok" >&2

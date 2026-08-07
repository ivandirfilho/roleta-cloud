#!/usr/bin/env bash
# backup-sqlite-to-blob.sh — snapshot consistente de SQLite + state para Blob.
#
# O banco é copiado via SQLite backup API e validado antes do upload. A MI da VM
# precisa de Storage Blob Data Contributor no storage account.
set -euo pipefail
umask 077

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stroletaprod}"
CONTAINER="${BACKUP_CONTAINER:-backups}"
BLOB_PREFIX="${BLOB_PREFIX:-azure-local/}"
DATA_DIR="${DATA_DIR:-/opt/roleta/data}"
DB="${DB_PATH:-$DATA_DIR/decisions.db}"
RETAIN_LOCAL="${RETAIN_LOCAL:-0}"
LOCAL_BACKUP_DIR="${LOCAL_BACKUP_DIR:-$DATA_DIR/backups}"
REQUIRE_DB="${REQUIRE_DB:-0}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

BLOB_PREFIX="${BLOB_PREFIX#/}"
case "$BLOB_PREFIX" in
  ""|*".."*|*[!A-Za-z0-9._/-]*)
    echo "ERRO: BLOB_PREFIX invalido" >&2
    exit 2
    ;;
esac
[[ "$BLOB_PREFIX" == */ ]] || BLOB_PREFIX="${BLOB_PREFIX}/"

command -v az >/dev/null || { echo "ERRO: az CLI ausente" >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERRO: sqlite3 ausente" >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERRO: python3 ausente" >&2; exit 1; }
case "$RETAIN_LOCAL:$REQUIRE_DB" in
  0:0|0:1|1:0|1:1) ;;
  *) echo "ERRO: RETAIN_LOCAL/REQUIRE_DB devem ser 0 ou 1" >&2; exit 2 ;;
esac

az login --identity >/dev/null

[ -f "$DATA_DIR/state.json" ] || {
  echo "ERRO: $DATA_DIR/state.json ausente" >&2
  exit 1
}
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$DATA_DIR/state.json"
STATE_SNAPSHOT="$TMP/state_$STAMP.json"
cp "$DATA_DIR/state.json" "$STATE_SNAPSHOT"

if [ -f "$DB" ]; then
  sqlite3 "$DB" ".backup '$TMP/decisions_$STAMP.db'"
  CHECK="$(sqlite3 "$TMP/decisions_$STAMP.db" 'PRAGMA integrity_check;')"
  [ "$CHECK" = "ok" ] || {
    echo "ERRO: integrity_check do snapshot retornou: $CHECK" >&2
    exit 1
  }
  python3 - "$TMP/decisions_$STAMP.db" "$STATE_SNAPSHOT" "$TMP/metadata_$STAMP.json" "$STAMP" <<'PY'
import datetime as dt
import json
import sqlite3
import sys

db_path, state_path, output_path, stamp = sys.argv[1:]
with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
    count, max_id, max_ts = conn.execute(
        "SELECT COUNT(*), MAX(id), MAX(timestamp) FROM decisions"
    ).fetchone()
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
metadata = {
    "source": "azure-local",
    "stamp": stamp,
    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "decisions_count": count,
    "decisions_max_id": max_id,
    "decisions_max_timestamp": max_ts,
    "state_spin_seq": state.get("spin_seq"),
}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(metadata, handle, sort_keys=True)
PY
  gzip -9 "$TMP/decisions_$STAMP.db"
elif [ "$REQUIRE_DB" = "1" ]; then
  echo "ERRO: $DB ausente e REQUIRE_DB=1" >&2
  exit 1
else
  echo "AVISO: $DB ausente; somente state.json sera enviado" >&2
fi

shopt -s nullglob
payloads=("$TMP"/decisions_*.db.gz "$TMP"/state_*.json "$TMP"/metadata_*.json)
[ "${#payloads[@]}" -gt 0 ] || { echo "ERRO: nada para enviar" >&2; exit 1; }
(
  cd "$TMP"
  : > "manifest_$STAMP.sha256"
  for f in "${payloads[@]}"; do
    sha256sum -- "$(basename "$f")" >> "manifest_$STAMP.sha256"
  done
)
manifest="$TMP/manifest_$STAMP.sha256"

az storage container create \
  --account-name "$STORAGE_ACCOUNT" \
  --name "$CONTAINER" \
  --auth-mode login >/dev/null

upload_file() {
  local f="$1"
  local name="${BLOB_PREFIX}$(basename "$f")"
  az storage blob upload \
    --account-name "$STORAGE_ACCOUNT" \
    --container-name "$CONTAINER" \
    --name "$name" \
    --file "$f" \
    --auth-mode login \
    --overwrite >/dev/null
  echo "[backup] enviado: $name" >&2
  if [ "$RETAIN_LOCAL" = "1" ]; then
    mkdir -p "$LOCAL_BACKUP_DIR"
    install -m 0600 "$f" "$LOCAL_BACKUP_DIR/$(basename "$f")"
  fi
}

# O manifesto e enviado por ultimo: sua presenca significa snapshot completo.
for f in "${payloads[@]}"; do
  upload_file "$f"
done
upload_file "$manifest"
echo "[backup] validado; destino: $STORAGE_ACCOUNT/$CONTAINER/$BLOB_PREFIX (stamp $STAMP)" >&2

#!/usr/bin/env bash
# backup-sqlite-to-blob.sh — snapshot consistente de SQLite + state para Blob.
#
# O banco é copiado via SQLite backup API e validado antes do upload. A MI da VM
# precisa de Storage Blob Data Contributor no storage account.
set -euo pipefail
umask 077

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stroletaprod}"
CONTAINER="${BACKUP_CONTAINER:-backups}"
DATA_DIR="${DATA_DIR:-/opt/roleta/data}"
DB="${DB_PATH:-$DATA_DIR/decisions.db}"
RETAIN_LOCAL="${RETAIN_LOCAL:-0}"
LOCAL_BACKUP_DIR="${LOCAL_BACKUP_DIR:-$DATA_DIR/backups}"
REQUIRE_DB="${REQUIRE_DB:-0}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

command -v az >/dev/null || { echo "ERRO: az CLI ausente" >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERRO: sqlite3 ausente" >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERRO: python3 ausente" >&2; exit 1; }
case "$RETAIN_LOCAL:$REQUIRE_DB" in
  0:0|0:1|1:0|1:1) ;;
  *) echo "ERRO: RETAIN_LOCAL/REQUIRE_DB devem ser 0 ou 1" >&2; exit 2 ;;
esac

az login --identity >/dev/null

if [ -f "$DB" ]; then
  sqlite3 "$DB" ".backup '$TMP/decisions_$STAMP.db'"
  CHECK="$(sqlite3 "$TMP/decisions_$STAMP.db" 'PRAGMA integrity_check;')"
  [ "$CHECK" = "ok" ] || {
    echo "ERRO: integrity_check do snapshot retornou: $CHECK" >&2
    exit 1
  }
  gzip -9 "$TMP/decisions_$STAMP.db"
elif [ "$REQUIRE_DB" = "1" ]; then
  echo "ERRO: $DB ausente e REQUIRE_DB=1" >&2
  exit 1
else
  echo "AVISO: $DB ausente; somente state.json sera enviado" >&2
fi

[ -f "$DATA_DIR/state.json" ] || {
  echo "ERRO: $DATA_DIR/state.json ausente" >&2
  exit 1
}
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$DATA_DIR/state.json"
cp "$DATA_DIR/state.json" "$TMP/state_$STAMP.json"

shopt -s nullglob
files=("$TMP"/*)
[ "${#files[@]}" -gt 0 ] || { echo "ERRO: nada para enviar" >&2; exit 1; }
(
  cd "$TMP"
  sha256sum -- * > "manifest_$STAMP.sha256"
)
files=("$TMP"/*)

az storage container create \
  --account-name "$STORAGE_ACCOUNT" \
  --name "$CONTAINER" \
  --auth-mode login >/dev/null

for f in "${files[@]}"; do
  name="sqlite/$(basename "$f")"
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
done
echo "[backup] validado; destino: $STORAGE_ACCOUNT/$CONTAINER/sqlite/ (stamp $STAMP)" >&2

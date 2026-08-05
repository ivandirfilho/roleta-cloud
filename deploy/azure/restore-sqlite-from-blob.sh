#!/usr/bin/env bash
# restore-sqlite-from-blob.sh — restaura um par decisions.db/state.json do Blob.
#
# Nunca sobrescreve dados sem --force e recusa restore enquanto roleta-cloud esta
# rodando. O par é escolhido pelo mesmo stamp do manifesto do backup.
set -euo pipefail
umask 077

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stroletaprod}"
CONTAINER="${BACKUP_CONTAINER:-backups}"
TARGET_DIR="${TARGET_DIR:-/opt/roleta/data}"
STAMP=""
FORCE=0

while (($# > 0)); do
  case "$1" in
    --stamp)
      [ "$#" -ge 2 ] || { echo "ERRO: --stamp exige valor" >&2; exit 2; }
      STAMP="$2"
      shift
      ;;
    --target-dir)
      [ "$#" -ge 2 ] || { echo "ERRO: --target-dir exige valor" >&2; exit 2; }
      TARGET_DIR="$2"
      shift
      ;;
    --force)
      FORCE=1
      ;;
    --help)
      sed -n '2,7p' "$0"
      exit 0
      ;;
    *)
      echo "ERRO: argumento desconhecido: $1" >&2
      exit 2
      ;;
  esac
  shift
done

command -v az >/dev/null || { echo "ERRO: az CLI ausente" >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERRO: sqlite3 ausente" >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERRO: python3 ausente" >&2; exit 1; }
if command -v docker >/dev/null &&
  [ "$(docker inspect -f '{{.State.Running}}' roleta-cloud 2>/dev/null || echo false)" = "true" ]; then
  echo "ERRO: pare roleta-cloud antes de restaurar" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
az login --identity >/dev/null

mapfile -t DB_BLOBS < <(
  az storage blob list \
    --account-name "$STORAGE_ACCOUNT" \
    --container-name "$CONTAINER" \
    --prefix sqlite/ \
    --auth-mode login \
    --query "[?ends_with(name, '.db.gz')].name" \
    -o tsv | sort
)
[ "${#DB_BLOBS[@]}" -gt 0 ] || {
  echo "ERRO: nenhum snapshot decisions.db encontrado" >&2
  exit 1
}

if [ -n "$STAMP" ]; then
  DB_BLOB="sqlite/decisions_${STAMP}.db.gz"
else
  DB_BLOB="${DB_BLOBS[${#DB_BLOBS[@]}-1]}"
  STAMP="${DB_BLOB##*/decisions_}"
  STAMP="${STAMP%.db.gz}"
fi
STATE_BLOB="sqlite/state_${STAMP}.json"
DB_EXISTS="$(az storage blob exists --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" --name "$DB_BLOB" --auth-mode login --query exists -o tsv)"
STATE_EXISTS="$(az storage blob exists --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" --name "$STATE_BLOB" --auth-mode login --query exists -o tsv)"
[ "$DB_EXISTS" = "true" ] && [ "$STATE_EXISTS" = "true" ] || {
  echo "ERRO: snapshot incompleto para stamp $STAMP (db=$DB_EXISTS state=$STATE_EXISTS)" >&2
  exit 1
}

az storage blob download \
  --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" \
  --name "$DB_BLOB" --file "$TMP/decisions.db.gz" \
  --auth-mode login --overwrite >/dev/null
az storage blob download \
  --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" \
  --name "$STATE_BLOB" --file "$TMP/state.json" \
  --auth-mode login --overwrite >/dev/null
gzip -dc "$TMP/decisions.db.gz" > "$TMP/decisions.db"
CHECK="$(sqlite3 "$TMP/decisions.db" 'PRAGMA integrity_check;')"
[ "$CHECK" = "ok" ] || { echo "ERRO: restore integrity_check retornou: $CHECK" >&2; exit 1; }
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$TMP/state.json"

mkdir -p "$TARGET_DIR"
for target in "$TARGET_DIR/decisions.db" "$TARGET_DIR/state.json"; do
  if [ -e "$target" ] && [ "$FORCE" != "1" ]; then
    echo "ERRO: $target ja existe; use --force apos validar o snapshot" >&2
    exit 1
  fi
done
if [ "$FORCE" = "1" ]; then
  for target in "$TARGET_DIR/decisions.db" "$TARGET_DIR/state.json"; do
    if [ -e "$target" ]; then
      cp -a "$target" "${target}.pre-restore.${STAMP}"
    fi
  done
fi
install -m 0640 "$TMP/decisions.db" "$TARGET_DIR/decisions.db.new"
install -m 0600 "$TMP/state.json" "$TARGET_DIR/state.json.new"
mv -f "$TARGET_DIR/decisions.db.new" "$TARGET_DIR/decisions.db"
mv -f "$TARGET_DIR/state.json.new" "$TARGET_DIR/state.json"
echo "[restore] OK: stamp=$STAMP target=$TARGET_DIR (integrity_check=ok)" >&2

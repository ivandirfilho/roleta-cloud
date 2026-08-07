#!/usr/bin/env bash
# restore-sqlite-from-blob.sh — restaura um par decisions.db/state.json do Blob.
#
# O caminho ativo exige stamp explícito, app parada e diretório vazio. Um standby
# separado pode ser atualizado com a app ativa, mas nunca reutiliza WAL/SHM.
set -euo pipefail
umask 077

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stroletaprod}"
CONTAINER="${BACKUP_CONTAINER:-backups}"
TARGET_DIR="${TARGET_DIR:-/opt/roleta/data}"
ACTIVE_DATA_DIR="${ACTIVE_DATA_DIR:-/opt/roleta/data}"
BLOB_PREFIX="${BLOB_PREFIX:-azure-local/}"
STATUS_FILE="${STATUS_FILE:-}"
APPLIED_STAMP_FILE="${APPLIED_STAMP_FILE:-}"
MAX_SNAPSHOT_AGE_SEC="${MAX_SNAPSHOT_AGE_SEC:-0}"
BACKUP_EXISTING="${BACKUP_EXISTING:-1}"
STAMP=""
STAMP_EXPLICIT=0
FORCE="${ALLOW_OVERWRITE:-0}"

while (($# > 0)); do
  case "$1" in
    --stamp)
      [ "$#" -ge 2 ] || { echo "ERRO: --stamp exige valor" >&2; exit 2; }
      STAMP="$2"
      STAMP_EXPLICIT=1
      shift
      ;;
    --target-dir)
      [ "$#" -ge 2 ] || { echo "ERRO: --target-dir exige valor" >&2; exit 2; }
      TARGET_DIR="$2"
      shift
      ;;
    --prefix)
      [ "$#" -ge 2 ] || { echo "ERRO: --prefix exige valor" >&2; exit 2; }
      BLOB_PREFIX="$2"
      shift
      ;;
    --container)
      [ "$#" -ge 2 ] || { echo "ERRO: --container exige valor" >&2; exit 2; }
      CONTAINER="$2"
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
command -v realpath >/dev/null || { echo "ERRO: realpath ausente" >&2; exit 1; }
command -v stat >/dev/null || { echo "ERRO: stat ausente" >&2; exit 1; }
case "$FORCE:$BACKUP_EXISTING" in
  0:0|0:1|1:0|1:1) ;;
  *) echo "ERRO: ALLOW_OVERWRITE/BACKUP_EXISTING devem ser 0 ou 1" >&2; exit 2 ;;
esac
[[ "$MAX_SNAPSHOT_AGE_SEC" =~ ^[0-9]+$ ]] || {
  echo "ERRO: MAX_SNAPSHOT_AGE_SEC deve ser inteiro >= 0" >&2
  exit 2
}

BLOB_PREFIX="${BLOB_PREFIX#/}"
case "$BLOB_PREFIX" in
  ""|*".."*|*[!A-Za-z0-9._/-]*)
    echo "ERRO: BLOB_PREFIX invalido" >&2
    exit 2
    ;;
esac
[[ "$BLOB_PREFIX" == */ ]] || BLOB_PREFIX="${BLOB_PREFIX}/"
[[ "$CONTAINER" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]] || {
  echo "ERRO: BACKUP_CONTAINER invalido" >&2
  exit 2
}
if [ -n "$STAMP" ] && [[ ! "$STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "ERRO: stamp invalido; esperado YYYYMMDDTHHMMSSZ" >&2
  exit 2
fi

TARGET_RESOLVED="$(realpath -m -- "$TARGET_DIR")"
ACTIVE_RESOLVED="$(realpath -m -- "$ACTIVE_DATA_DIR")"
IS_ACTIVE=0
same_location() {
  local left="$1"
  local right="$2"
  [ "$left" = "$right" ] && return 0
  [ -e "$left" ] && [ -e "$right" ] || return 1
  [ "$(stat -Lc '%d:%i' "$left")" = "$(stat -Lc '%d:%i' "$right")" ]
}

ACTIVE_ALIASES=("$ACTIVE_RESOLVED")
if command -v docker >/dev/null && docker inspect roleta-cloud >/dev/null 2>&1; then
  ACTIVE_MOUNT_TYPE="$(docker inspect roleta-cloud --format \
    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Type}}{{end}}{{end}}')"
  ACTIVE_MOUNT_NAME="$(docker inspect roleta-cloud --format \
    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Name}}{{end}}{{end}}')"
  ACTIVE_MOUNT_SOURCE="$(docker inspect roleta-cloud --format \
    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}')"
  [ -z "$ACTIVE_MOUNT_SOURCE" ] || ACTIVE_ALIASES+=("$(realpath -m -- "$ACTIVE_MOUNT_SOURCE")")
  if [ "$ACTIVE_MOUNT_TYPE" = "volume" ] && [ -n "$ACTIVE_MOUNT_NAME" ]; then
    ACTIVE_MOUNT_DEVICE="$(docker volume inspect "$ACTIVE_MOUNT_NAME" \
      --format '{{index .Options "device"}}' 2>/dev/null || true)"
    if [ -n "$ACTIVE_MOUNT_DEVICE" ] && [ "$ACTIVE_MOUNT_DEVICE" != "<no value>" ]; then
      ACTIVE_ALIASES+=("$(realpath -m -- "$ACTIVE_MOUNT_DEVICE")")
    fi
  fi
fi
for active_alias in "${ACTIVE_ALIASES[@]}"; do
  if same_location "$TARGET_RESOLVED" "$active_alias"; then
    IS_ACTIVE=1
    break
  fi
done

if [ "$IS_ACTIVE" = "1" ]; then
  [ -n "$STAMP" ] || {
    echo "ERRO: restore no caminho ativo exige --stamp explícito" >&2
    exit 2
  }
  if command -v docker >/dev/null &&
    [ "$(docker inspect -f '{{.State.Running}}' roleta-cloud 2>/dev/null || echo false)" = "true" ]; then
    echo "ERRO: pare roleta-cloud antes de restaurar o caminho ativo" >&2
    exit 1
  fi
  if [ -d "$TARGET_RESOLVED" ] &&
    find "$TARGET_RESOLVED" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "ERRO: mova o diretório ativo de lado; restore ativo exige destino vazio" >&2
    exit 1
  fi
fi

for sidecar in "$TARGET_RESOLVED/decisions.db-wal" "$TARGET_RESOLVED/decisions.db-shm"; do
  [ ! -e "$sidecar" ] || {
    echo "ERRO: sidecar SQLite presente em $sidecar; mova/limpe o diretório antes" >&2
    exit 1
  }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
az login --identity >/dev/null

mapfile -t MANIFEST_BLOBS < <(
  az storage blob list \
    --account-name "$STORAGE_ACCOUNT" \
    --container-name "$CONTAINER" \
    --prefix "${BLOB_PREFIX}manifest_" \
    --num-results '*' \
    --auth-mode login \
    --query "[?ends_with(name, '.sha256')].name" \
    -o tsv | sort
)
[ "${#MANIFEST_BLOBS[@]}" -gt 0 ] || {
  echo "ERRO: nenhum manifesto encontrado em $CONTAINER/$BLOB_PREFIX" >&2
  exit 1
}

if [ -n "$STAMP" ]; then
  MANIFEST_BLOB="${BLOB_PREFIX}manifest_${STAMP}.sha256"
else
  MANIFEST_BLOB="${MANIFEST_BLOBS[${#MANIFEST_BLOBS[@]}-1]}"
  STAMP="${MANIFEST_BLOB##*/manifest_}"
  STAMP="${STAMP%.sha256}"
fi
[[ "$STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || {
  echo "ERRO: manifesto remoto contém stamp inválido" >&2
  exit 1
}
SNAPSHOT_AGE_SEC="$(python3 - "$STAMP" <<'PY'
import datetime as dt
import sys

stamp = dt.datetime.strptime(sys.argv[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
print(max(0, int((dt.datetime.now(dt.timezone.utc) - stamp).total_seconds())))
PY
)"
if [ "$MAX_SNAPSHOT_AGE_SEC" -gt 0 ] &&
  [ "$SNAPSHOT_AGE_SEC" -gt "$MAX_SNAPSHOT_AGE_SEC" ]; then
  echo "ERRO: snapshot $STAMP está stale (${SNAPSHOT_AGE_SEC}s > ${MAX_SNAPSHOT_AGE_SEC}s)" >&2
  exit 1
fi
MANIFEST_EXISTS="$(az storage blob exists \
  --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" \
  --name "$MANIFEST_BLOB" --auth-mode login --query exists -o tsv)"
[ "$MANIFEST_EXISTS" = "true" ] || {
  echo "ERRO: manifesto ausente para stamp $STAMP" >&2
  exit 1
}

APPLIED_STAMP=""
if [ -n "$APPLIED_STAMP_FILE" ] && [ -f "$APPLIED_STAMP_FILE" ]; then
  APPLIED_STAMP="$(sed -n '1p' "$APPLIED_STAMP_FILE")"
  [[ "$APPLIED_STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || {
    echo "ERRO: applied stamp inválido em $APPLIED_STAMP_FILE" >&2
    exit 1
  }
  if [ "$STAMP_EXPLICIT" != "1" ] && [[ "$STAMP" < "$APPLIED_STAMP" ]]; then
    echo "ERRO: recusando rollback automático de $APPLIED_STAMP para $STAMP" >&2
    exit 1
  fi
fi

if [ -n "$APPLIED_STAMP_FILE" ] &&
  [ "$APPLIED_STAMP" = "$STAMP" ] &&
  [ -f "$TARGET_RESOLVED/decisions.db" ] &&
  [ -f "$TARGET_RESOLVED/state.json" ]; then
  NOOP_CHECK="$(sqlite3 "$TARGET_RESOLVED/decisions.db" 'PRAGMA quick_check;' 2>/dev/null || true)"
  if [ "$NOOP_CHECK" = "ok" ] &&
    python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' \
      "$TARGET_RESOLVED/state.json" 2>/dev/null; then
    echo "[restore] stamp $STAMP já aplicado e íntegro; age=${SNAPSHOT_AGE_SEC}s" >&2
    exit 0
  fi
  echo "[restore] stamp aplicado está corrompido; reaplicando snapshot" >&2
fi

MANIFEST_NAME="manifest_${STAMP}.sha256"
az storage blob download \
  --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" \
  --name "$MANIFEST_BLOB" --file "$TMP/$MANIFEST_NAME" \
  --auth-mode login --overwrite >/dev/null

python3 - "$TMP/$MANIFEST_NAME" "$STAMP" > "$TMP/files.txt" <<'PY'
import re
import sys

manifest_path, stamp = sys.argv[1:]
allowed = {
    f"decisions_{stamp}.db.gz",
    f"state_{stamp}.json",
    f"metadata_{stamp}.json",
}
required = {f"decisions_{stamp}.db.gz", f"state_{stamp}.json"}
seen = set()
with open(manifest_path, encoding="utf-8") as handle:
    for raw in handle:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)\n?", raw)
        if not match or match.group(2) not in allowed:
            raise SystemExit("manifesto contém entrada inválida")
        name = match.group(2)
        if name in seen:
            raise SystemExit("manifesto contém entrada duplicada")
        seen.add(name)
if not required.issubset(seen):
    raise SystemExit("manifesto não contém DB e state obrigatórios")
for name in sorted(seen):
    print(name)
PY

while IFS= read -r name; do
  az storage blob download \
    --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" \
    --name "${BLOB_PREFIX}${name}" --file "$TMP/$name" \
    --auth-mode login --overwrite >/dev/null
done < "$TMP/files.txt"
(
  cd "$TMP"
  sha256sum -c "$MANIFEST_NAME" >/dev/null
)

DB_ARCHIVE="$TMP/decisions_${STAMP}.db.gz"
STATE_SNAPSHOT="$TMP/state_${STAMP}.json"
gzip -dc "$DB_ARCHIVE" > "$TMP/decisions.db"
JOURNAL_MODE="$(sqlite3 "$TMP/decisions.db" 'PRAGMA journal_mode=DELETE;')"
[ "$JOURNAL_MODE" = "delete" ] || {
  echo "ERRO: nao foi possivel normalizar journal_mode do snapshot: $JOURNAL_MODE" >&2
  exit 1
}
CHECK="$(sqlite3 "$TMP/decisions.db" 'PRAGMA integrity_check;')"
[ "$CHECK" = "ok" ] || { echo "ERRO: restore integrity_check retornou: $CHECK" >&2; exit 1; }
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$STATE_SNAPSHOT"

install -d -m 0750 "$TARGET_RESOLVED"
for target in "$TARGET_RESOLVED/decisions.db" "$TARGET_RESOLVED/state.json"; do
  if [ -e "$target" ] && [ "$FORCE" != "1" ]; then
    echo "ERRO: $target ja existe; use --force apos validar o snapshot" >&2
    exit 1
  fi
done
if [ "$FORCE" = "1" ] && [ "$BACKUP_EXISTING" = "1" ] && [ "$IS_ACTIVE" != "1" ]; then
  for target in "$TARGET_RESOLVED/decisions.db" "$TARGET_RESOLVED/state.json"; do
    if [ -e "$target" ]; then
      cp -a "$target" "${target}.pre-restore.${STAMP}"
    fi
  done
fi
install -m 0640 "$TMP/decisions.db" "$TARGET_RESOLVED/decisions.db.new"
install -m 0600 "$STATE_SNAPSHOT" "$TARGET_RESOLVED/state.json.new"
mv -f "$TARGET_RESOLVED/decisions.db.new" "$TARGET_RESOLVED/decisions.db"
mv -f "$TARGET_RESOLVED/state.json.new" "$TARGET_RESOLVED/state.json"
sync -f "$TARGET_RESOLVED" 2>/dev/null || sync
POST_CHECK="$(sqlite3 "$TARGET_RESOLVED/decisions.db" 'PRAGMA integrity_check;')"
[ "$POST_CHECK" = "ok" ] || {
  echo "ERRO: integrity_check pós-instalação retornou: $POST_CHECK" >&2
  exit 1
}
for sidecar in "$TARGET_RESOLVED/decisions.db-wal" "$TARGET_RESOLVED/decisions.db-shm"; do
  [ ! -e "$sidecar" ] || {
    echo "ERRO: restore deixou sidecar SQLite em $sidecar" >&2
    exit 1
  }
done

if [ -n "$STATUS_FILE" ]; then
  python3 - "$TARGET_RESOLVED/decisions.db" "$TARGET_RESOLVED/state.json" \
    "$STATUS_FILE" "$STAMP" "$CONTAINER" "$BLOB_PREFIX" "$SNAPSHOT_AGE_SEC" <<'PY'
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile

db_path, state_path, status_path, stamp, container, prefix, snapshot_age = sys.argv[1:]
with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
    count, max_id, max_ts = conn.execute(
        "SELECT COUNT(*), MAX(id), MAX(timestamp) FROM decisions"
    ).fetchone()
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
payload = {
    "stamp": stamp,
    "container": container,
    "prefix": prefix,
    "restored_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "decisions_count": count,
    "decisions_max_id": max_id,
    "decisions_max_timestamp": max_ts,
    "state_spin_seq": state.get("spin_seq"),
    "snapshot_age_sec": int(snapshot_age),
    "integrity_check": "ok",
}
parent = os.path.dirname(status_path) or "."
os.makedirs(parent, mode=0o750, exist_ok=True)
fd, tmp = tempfile.mkstemp(prefix=".standby-status.", dir=parent, text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o640)
    os.replace(tmp, status_path)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
PY
fi

if [ -n "$APPLIED_STAMP_FILE" ]; then
  install -d -m 0750 "$(dirname "$APPLIED_STAMP_FILE")"
  printf '%s\n' "$STAMP" > "$TMP/applied-stamp"
  install -m 0640 "$TMP/applied-stamp" "$APPLIED_STAMP_FILE"
fi

echo "[restore] OK: stamp=$STAMP age=${SNAPSHOT_AGE_SEC}s source=$CONTAINER/$BLOB_PREFIX target=$TARGET_RESOLVED (integrity_check=ok)" >&2

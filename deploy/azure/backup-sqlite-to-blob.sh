#!/usr/bin/env bash
# backup-sqlite-to-blob.sh — na VM Azure: snapshot CONSISTENTE do decisions.db
# (sqlite3 .backup — seguro com o app rodando, sem travar o writer) + do state.json,
# e upload no Blob (stroletaprod/backups) via Managed Identity (AAD, sem chave).
#
# Uso: ./backup-sqlite-to-blob.sh          # sob demanda ou via cron diario
# Pré-requisito de RBAC (gate humano, uma vez): a MI da VM precisa de
#   "Storage Blob Data Contributor" no stroletaprod (ver README).
set -euo pipefail
umask 077

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stroletaprod}"
CONTAINER="${BACKUP_CONTAINER:-backups}"
DATA_DIR="${DATA_DIR:-/opt/roleta/data}"
DB="${DB_PATH:-$DATA_DIR/decisions.db}"
RETAIN_LOCAL="${RETAIN_LOCAL:-0}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

command -v az >/dev/null      || { echo "ERRO: az CLI ausente" >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERRO: sqlite3 ausente" >&2; exit 1; }

az login --identity >/dev/null

# Snapshot consistente do SQLite (não interrompe o app).
if [ -f "$DB" ]; then
  sqlite3 "$DB" ".backup '$TMP/decisions_$STAMP.db'"
  gzip -9 "$TMP/decisions_$STAMP.db"
else
  echo "AVISO: $DB ausente (canary sem dados reais ainda) — pulando decisions.db" >&2
fi
# state.json versionado junto.
[ -f "$DATA_DIR/state.json" ] && cp "$DATA_DIR/state.json" "$TMP/state_$STAMP.json"

shopt -s nullglob
files=("$TMP"/*)
[ ${#files[@]} -gt 0 ] || { echo "ERRO: nada para enviar" >&2; exit 1; }

# Garante o container (idempotente) e sobe cada artefato (auth via AAD/MI).
az storage container create --account-name "$STORAGE_ACCOUNT" --name "$CONTAINER" --auth-mode login >/dev/null 2>&1 || true
for f in "${files[@]}"; do
  az storage blob upload \
    --account-name "$STORAGE_ACCOUNT" --container-name "$CONTAINER" \
    --name "sqlite/$(basename "$f")" --file "$f" --auth-mode login --overwrite >/dev/null
  echo "[backup] enviado: sqlite/$(basename "$f")" >&2
done
echo "[backup] destino: https://$STORAGE_ACCOUNT.blob.core.windows.net/$CONTAINER/sqlite/ (stamp $STAMP)" >&2

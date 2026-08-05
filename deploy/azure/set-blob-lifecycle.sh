#!/usr/bin/env bash
# set-blob-lifecycle.sh — aplica/reconcilia retenção dos snapshots SQLite.
#
# Preserva regras existentes do Storage Account e substitui somente a regra
# gerenciada por este script.
set -euo pipefail

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stroletaprod}"
RESOURCE_GROUP="${RESOURCE_GROUP:-maquina_roleta_cloud}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
COOL_AFTER_DAYS="${COOL_AFTER_DAYS:-7}"
RULE_NAME="roleta-sqlite-retention"
PREFIX="${BACKUP_PREFIX:-backups/sqlite/}"

while (($# > 0)); do
  case "$1" in
    --help)
      sed -n '2,6p' "$0"
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
command -v python3 >/dev/null || { echo "ERRO: python3 ausente" >&2; exit 1; }
[[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "ERRO: RETENTION_DAYS invalido" >&2; exit 2; }
[[ "$COOL_AFTER_DAYS" =~ ^[0-9]+$ ]] || { echo "ERRO: COOL_AFTER_DAYS invalido" >&2; exit 2; }
[ "$COOL_AFTER_DAYS" -lt "$RETENTION_DAYS" ] || {
  echo "ERRO: COOL_AFTER_DAYS deve ser menor que RETENTION_DAYS" >&2
  exit 2
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
CURRENT="$TMP/current.json"
POLICY="$TMP/policy.json"
ERR="$TMP/show.err"

if ! az storage account management-policy show \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  -o json > "$CURRENT" 2> "$ERR"; then
  if grep -Eqi 'ResourceNotFound|ManagementPolicyNotFound|No ManagementPolicy found' "$ERR"; then
    printf '%s\n' '{"rules":[]}' > "$CURRENT"
  else
    cat "$ERR" >&2
    exit 1
  fi
fi

python3 - "$CURRENT" "$POLICY" "$RULE_NAME" "$PREFIX" "$RETENTION_DAYS" "$COOL_AFTER_DAYS" <<'PY'
import json
import sys

current_path, output_path, rule_name, prefix, retention, cool = sys.argv[1:]
with open(current_path, encoding="utf-8") as handle:
    current = json.load(handle)
rules = [rule for rule in current.get("rules", []) if rule.get("name") != rule_name]
rules.append(
    {
        "enabled": True,
        "name": rule_name,
        "type": "Lifecycle",
        "definition": {
            "filters": {"blobTypes": ["blockBlob"], "prefixMatch": [prefix]},
            "actions": {
                "baseBlob": {
                    "tierToCool": {"daysAfterModificationGreaterThan": int(cool)},
                    "delete": {"daysAfterModificationGreaterThan": int(retention)},
                }
            },
        },
    }
)
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump({"rules": rules}, handle, indent=2)
PY

az storage account management-policy create \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --policy "$POLICY" \
  -o none
echo "[lifecycle] regra $RULE_NAME aplicada: cool=${COOL_AFTER_DAYS}d delete=${RETENTION_DAYS}d prefix=$PREFIX" >&2

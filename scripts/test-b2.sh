#!/bin/bash
# test-b2.sh — Autoriza B2, cria bucket se necessario e faz smoke upload.
#
# Pre-requisito: /etc/wal-g/env preenchido (substituir os 3 TODO_PREENCHER_*).
# Idempotente: pode rodar quantas vezes quiser.
#
# Instalado em prod via:
#   scp scripts/test-b2.sh root@debian:/usr/local/bin/test-b2.sh
#   chmod 755 /usr/local/bin/test-b2.sh

set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/wal-g/env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERRO: $ENV_FILE nao existe. Veja docs/runbooks/wal-g-backblaze.md." >&2
  exit 1
fi

if grep -q "TODO_PREENCHER" "$ENV_FILE"; then
  echo "ERRO: $ENV_FILE tem placeholders nao preenchidos:" >&2
  grep -n "TODO_PREENCHER" "$ENV_FILE" >&2
  echo "" >&2
  echo "Substitua: AWS_ACCESS_KEY_ID, WALG_S3_PREFIX (bucket), AWS_ENDPOINT (region)." >&2
  exit 2
fi

# shellcheck disable=SC1090
. "$ENV_FILE"

BUCKET=$(echo "${WALG_S3_PREFIX:?}" | sed 's|^s3://||' | sed 's|/.*||')
if [[ -z "$BUCKET" ]]; then
  echo "ERRO: bucket vazio em WALG_S3_PREFIX" >&2
  exit 3
fi

command -v b2 >/dev/null || {
  echo "ERRO: b2 CLI nao instalada. pip3 install --break-system-packages b2" >&2
  exit 4
}

echo "[1/4] b2 account authorize..."
b2 account authorize "${AWS_ACCESS_KEY_ID}" "${AWS_SECRET_ACCESS_KEY}"

echo "[2/4] Listando buckets..."
b2 bucket list

if ! b2 bucket list | awk '{print $3}' | grep -qx "${BUCKET}"; then
  echo "[3/4] Bucket '${BUCKET}' nao existe — criando (private + SSE-B2)..."
  b2 bucket create --default-server-side-encryption=SSE-B2 "${BUCKET}" allPrivate
else
  echo "[3/4] Bucket '${BUCKET}' ja existe — ok."
fi

echo "[4/4] Upload + sanity check..."
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
date -Iseconds > "$TMP"
SHA=$(sha256sum "$TMP" | awk '{print $1}')
REMOTE="smoke-test/$(hostname)-$(date +%s).txt"
b2 file upload "${BUCKET}" "$TMP" "$REMOTE"
echo "OK — uploaded $REMOTE (sha256: $SHA)"

echo ""
echo "=== B2 PRONTO. Proximos passos: docs/runbooks/wal-g-backblaze.md secao 'Instalacao no Debian' ==="

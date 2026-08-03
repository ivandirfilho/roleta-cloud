#!/usr/bin/env bash
# kv-to-env.sh — na VM Azure, materializa /opt/roleta/.env (0600) com os SEGREDOS
# lidos do Key Vault (kv-roleta-prod) via Managed Identity da VM.
#
# NÃO escreve as flags de estratégia: a fonte da verdade delas é
# deploy/azure/compose.azure.yml (defaults ${VAR:-...}), 1:1 com a produção
# HostDime — assim o flag-set/INV-3 não corre risco de divergir do compose.
#
# Uso (root na VM):
#   ./kv-to-env.sh              # segredos p/ canary (dual_write PG OFF)
#   ./kv-to-env.sh --with-pg    # também injeta ROLETA_PG_DSN (Onda PG; opt-in)
#
# Idempotente: preserva a linha ROLETA_IMAGE (imutável, gravada pelo deploy-azure.sh).
# Nunca ecoa valores de segredo no stdout/stderr.
set -euo pipefail
umask 077

KV_NAME="${KV_NAME:-kv-roleta-prod}"
ENV_FILE="${ENV_FILE:-/opt/roleta/.env}"
WITH_PG=0
[ "${1:-}" = "--with-pg" ] && WITH_PG=1

command -v az >/dev/null || { echo "ERRO: az CLI ausente na VM" >&2; exit 1; }

# Autentica pela identidade gerenciada da VM (nenhum segredo em disco).
az login --identity >/dev/null

kv_get() { az keyvault secret show --vault-name "$KV_NAME" --name "$1" --query value -o tsv; }

echo "[kv-to-env] lendo segredos de $KV_NAME ..." >&2
ROLETA_API_KEY="$(kv_get ROLETA-API-KEY)"
[ -n "$ROLETA_API_KEY" ] || { echo "ERRO: ROLETA-API-KEY vazio no KV" >&2; exit 1; }

PG_LINE=""
if [ "$WITH_PG" = "1" ]; then
  PG_HOST="$(kv_get POSTGRES-HOST)"
  PG_PASS="$(kv_get PG-APP-PASSWORD)"
  [ -n "$PG_HOST" ] && [ -n "$PG_PASS" ] || { echo "ERRO: POSTGRES-HOST/PG-APP-PASSWORD ausentes p/ --with-pg" >&2; exit 1; }
  # Azure PG Flexible exige TLS. Usuário/BD app: ajuste via env se diferir.
  PG_USER="${PG_APP_USER:-roleta_app}"
  PG_DB="${PG_APP_DB:-roleta}"
  PG_LINE="ROLETA_PG_DSN=postgresql://${PG_USER}:${PG_PASS}@${PG_HOST}:5432/${PG_DB}?sslmode=require"
fi

# Preserva ROLETA_IMAGE já gravado (o deploy-azure.sh define o digest imutável).
PRIOR_IMAGE=""
if [ -f "$ENV_FILE" ]; then
  PRIOR_IMAGE="$(grep -E '^ROLETA_IMAGE=' "$ENV_FILE" || true)"
fi

TMP="$(mktemp)"
{
  echo "# GERADO por kv-to-env.sh — NAO commitar. Segredos do Key Vault ($KV_NAME)."
  echo "# Flags de estrategia vem do compose.azure.yml (paridade INV-3 com producao)."
  [ -n "$PRIOR_IMAGE" ] && echo "$PRIOR_IMAGE"
  echo "ROLETA_API_KEY=${ROLETA_API_KEY}"
  [ -n "$PG_LINE" ] && echo "$PG_LINE"
} > "$TMP"

install -m 0600 "$TMP" "$ENV_FILE"
rm -f "$TMP"
echo "[kv-to-env] $ENV_FILE atualizado (0600). PG dual-write: $([ "$WITH_PG" = 1 ] && echo ON || echo OFF)." >&2

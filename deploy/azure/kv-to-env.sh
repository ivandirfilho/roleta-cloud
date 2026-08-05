#!/usr/bin/env bash
# kv-to-env.sh — materializa /opt/roleta/.env com segredos do Key Vault via MI.
#
# O arquivo é recriado de forma atômica. Flags de estratégia continuam no
# compose.azure.yml; apenas valores de runtime e segredos entram aqui.
#
# Uso:
#   ./kv-to-env.sh
#   ./kv-to-env.sh --with-pg
#   ./kv-to-env.sh --without-pg
set -euo pipefail
umask 077

KV_NAME="${KV_NAME:-kv-roleta-prod}"
APP_DIR="${APP_DIR:-/opt/roleta}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
CADDY_STAGE_FILE="${CADDY_STAGE_FILE:-$APP_DIR/caddy.cutover.env}"
WITH_PG=0
CLEAR_PG=0

while (($# > 0)); do
  case "$1" in
    --with-pg)
      WITH_PG=1
      ;;
    --without-pg)
      CLEAR_PG=1
      ;;
    --help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "ERRO: argumento desconhecido: $1 (use --with-pg ou --without-pg)" >&2
      exit 2
      ;;
  esac
  shift
done

if [ "$WITH_PG" = "1" ] && [ "$CLEAR_PG" = "1" ]; then
  echo "ERRO: --with-pg e --without-pg sao mutuamente exclusivos" >&2
  exit 2
fi

command -v az >/dev/null || { echo "ERRO: az CLI ausente na VM" >&2; exit 1; }
if [ "$WITH_PG" = "1" ]; then
  command -v python3 >/dev/null || {
    echo "ERRO: python3 e necessario para codificar a senha PostgreSQL" >&2
    exit 1
  }
fi

az login --identity >/dev/null

kv_get() {
  az keyvault secret show --vault-name "$KV_NAME" --name "$1" --query value -o tsv
}

reject_newline() {
  case "$2" in
    *$'\n'*|*$'\r'*)
      echo "ERRO: $1 contem quebra de linha" >&2
      exit 1
      ;;
  esac
}

urlencode() {
  python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read().rstrip("\n"), safe=""))'
}

read_env_value() {
  local key="$1"
  if [ -f "$ENV_FILE" ]; then
    sed -n "s/^${key}=//p" "$ENV_FILE" | sed -n '1p'
  fi
}

echo "[kv-to-env] lendo segredos de $KV_NAME ..." >&2
ROLETA_API_KEY="$(kv_get ROLETA-API-KEY)"
[ -n "$ROLETA_API_KEY" ] || {
  echo "ERRO: ROLETA-API-KEY vazio no KV" >&2
  exit 1
}
reject_newline ROLETA-API-KEY "$ROLETA_API_KEY"

ROLETA_DOMAIN="$(kv_get ROLETA-DOMAIN)"
CADDY_EMAIL="$(kv_get CADDY-EMAIL)"
[ -n "$ROLETA_DOMAIN" ] && [ -n "$CADDY_EMAIL" ] || {
  echo "ERRO: ROLETA-DOMAIN/CADDY-EMAIL ausentes no KV" >&2
  exit 1
}
reject_newline ROLETA-DOMAIN "$ROLETA_DOMAIN"
reject_newline CADDY-EMAIL "$CADDY_EMAIL"

PG_LINE=""
if [ "$WITH_PG" = "1" ]; then
  PG_HOST="$(kv_get POSTGRES-HOST)"
  PG_PASS="$(kv_get PG-APP-PASSWORD)"
  [ -n "$PG_HOST" ] && [ -n "$PG_PASS" ] || {
    echo "ERRO: POSTGRES-HOST/PG-APP-PASSWORD ausentes para --with-pg" >&2
    exit 1
  }
  reject_newline POSTGRES-HOST "$PG_HOST"
  reject_newline PG-APP-PASSWORD "$PG_PASS"
  [[ "$PG_HOST" =~ ^[A-Za-z0-9.-]+$ ]] || {
    echo "ERRO: POSTGRES-HOST contem caracteres invalidos" >&2
    exit 1
  }
  PG_USER="${PG_APP_USER:-roleta_app}"
  PG_DB="${PG_APP_DB:-roleta}"
  [[ "$PG_USER" =~ ^[A-Za-z0-9_.-]+$ ]] || {
    echo "ERRO: PG_APP_USER contem caracteres invalidos" >&2
    exit 1
  }
  [[ "$PG_DB" =~ ^[A-Za-z0-9_.-]+$ ]] || {
    echo "ERRO: PG_APP_DB contem caracteres invalidos" >&2
    exit 1
  }
  PG_PASS_URLENCODED="$(printf '%s' "$PG_PASS" | urlencode)"
  PG_LINE="ROLETA_PG_DSN=postgresql://${PG_USER}:${PG_PASS_URLENCODED}@${PG_HOST}:5432/${PG_DB}?sslmode=require"
elif [ "$CLEAR_PG" != "1" ]; then
  PRIOR_PG="$(read_env_value ROLETA_PG_DSN)"
  if [ -n "$PRIOR_PG" ]; then
    reject_newline ROLETA_PG_DSN "$PRIOR_PG"
    PG_LINE="ROLETA_PG_DSN=${PRIOR_PG}"
  fi
fi

PRIOR_IMAGE="$(read_env_value ROLETA_IMAGE)"
PRIOR_CDC_IMAGE="$(read_env_value CDC_IMAGE)"
TMP=""
CADDY_TMP=""
cleanup() {
  [ -z "$TMP" ] || rm -f "$TMP"
  [ -z "$CADDY_TMP" ] || rm -f "$CADDY_TMP"
}
trap cleanup EXIT

mkdir -p "$(dirname "$ENV_FILE")" "$(dirname "$CADDY_STAGE_FILE")"
TMP="$(mktemp "$(dirname "$ENV_FILE")/.env.XXXXXX")"
{
  echo "# GERADO por kv-to-env.sh — NAO commitar."
  echo "# Flags de estrategia vem do compose.azure.yml."
  [ -n "$PRIOR_IMAGE" ] && printf 'ROLETA_IMAGE=%s\n' "$PRIOR_IMAGE"
  [ -n "$PRIOR_CDC_IMAGE" ] && printf 'CDC_IMAGE=%s\n' "$PRIOR_CDC_IMAGE"
  printf 'ROLETA_API_KEY=%s\n' "$ROLETA_API_KEY"
  [ -n "$PG_LINE" ] && printf '%s\n' "$PG_LINE"
} > "$TMP"
install -m 0600 "$TMP" "$ENV_FILE"
TMP=""

# Staging separado: o domínio real só será carregado pelo Caddy após o gate de DNS.
CADDY_TMP="$(mktemp "$(dirname "$CADDY_STAGE_FILE")/.caddy.XXXXXX")"
{
  echo "# Staged by kv-to-env.sh; source this file only during cutover."
  printf 'SITE_ADDRESS=%s\n' "$ROLETA_DOMAIN"
  printf 'CADDY_EMAIL=%s\n' "$CADDY_EMAIL"
  printf 'WS_ALLOWED_CIDRS="%s"\n' "0.0.0.0/0 ::/0"
} > "$CADDY_TMP"
install -m 0600 "$CADDY_TMP" "$CADDY_STAGE_FILE"
CADDY_TMP=""

if [ "$WITH_PG" = "1" ]; then
  PG_STATUS="prepared (dual_write_pg remains flag-controlled)"
elif [ "$CLEAR_PG" = "1" ]; then
  PG_STATUS="cleared explicitly"
elif [ -n "$PG_LINE" ]; then
  PG_STATUS="preserved"
else
  PG_STATUS="absent"
fi
echo "[kv-to-env] $ENV_FILE atualizado (0600); PG DSN: $PG_STATUS." >&2

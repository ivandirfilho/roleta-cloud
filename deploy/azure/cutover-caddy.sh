#!/usr/bin/env bash
# Instala um EnvironmentFile do Caddy com validate/reload e rollback automático.
set -euo pipefail
umask 077

STAGED_ENV="${STAGED_ENV:-/opt/roleta/caddy.cutover.env}"
ACTIVE_ENV="${ACTIVE_ENV:-/etc/caddy/caddy.env}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"

[ "$(id -u)" -eq 0 ] || { echo "ERRO: execute como root" >&2; exit 1; }
command -v caddy >/dev/null || { echo "ERRO: caddy ausente" >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERRO: python3 ausente" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "ERRO: systemctl ausente" >&2; exit 1; }
[ -f "$STAGED_ENV" ] || { echo "ERRO: staged env ausente: $STAGED_ENV" >&2; exit 1; }
[ -f "$CADDYFILE" ] || { echo "ERRO: Caddyfile ausente: $CADDYFILE" >&2; exit 1; }

python3 - "$STAGED_ENV" <<'PY'
import re
import sys

path = sys.argv[1]
values = {}
allowed = {"SITE_ADDRESS", "CADDY_EMAIL", "WS_ALLOWED_CIDRS"}
with open(path, encoding="utf-8") as handle:
    for raw in handle:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"linha inválida em {path}")
        key, value = line.split("=", 1)
        if key not in allowed:
            raise SystemExit(f"chave não permitida: {key}")
        value = value.strip().strip('"')
        if not value or not re.fullmatch(r"[A-Za-z0-9@+._,:/ \-]+", value):
            raise SystemExit(f"valor inválido para {key}")
        values[key] = value
missing = allowed - values.keys()
if missing:
    raise SystemExit(f"chaves ausentes: {sorted(missing)}")
PY

install -d -m 0755 "$(dirname "$ACTIVE_ENV")"
BACKUP=""
if [ -f "$ACTIVE_ENV" ]; then
  BACKUP="${ACTIVE_ENV}.previous.$(date -u +%Y%m%dT%H%M%SZ)"
  install -m 0600 "$ACTIVE_ENV" "$BACKUP"
fi

rollback() {
  if [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
    install -m 0600 "$BACKUP" "$ACTIVE_ENV"
    set -a
    # shellcheck disable=SC1090
    . "$ACTIVE_ENV"
    set +a
    caddy validate --config "$CADDYFILE" >/dev/null 2>&1 || :
    systemctl reload caddy >/dev/null 2>&1 || :
  else
    rm -f "$ACTIVE_ENV"
  fi
}

install -m 0600 "$STAGED_ENV" "$ACTIVE_ENV"
set -a
# Valores foram restritos a um alfabeto seguro pelo parser acima.
# shellcheck disable=SC1090
. "$ACTIVE_ENV"
set +a
if ! caddy validate --config "$CADDYFILE"; then
  rollback
  echo "ERRO: Caddyfile inválido com o novo ambiente; rollback aplicado" >&2
  exit 1
fi
if ! systemctl reload caddy || ! systemctl is-active --quiet caddy; then
  rollback
  echo "ERRO: reload do Caddy falhou; rollback aplicado" >&2
  exit 1
fi
echo "[caddy] ambiente aplicado e reload validado: SITE_ADDRESS=$SITE_ADDRESS" >&2

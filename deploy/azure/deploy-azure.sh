#!/usr/bin/env bash
# deploy-azure.sh — baixa uma imagem ACR por digest e sobe o compose Azure.
#
# O script não builda no host, não altera DNS/NSG e não toca a HostDime.
# Um state.json ausente ou marcado como canário bloqueia o deploy por padrão.
set -euo pipefail
umask 077

ACR_NAME="${ACR_NAME:-acrroletaprod}"
ACR_LOGIN="${ACR_LOGIN:-acrroletaprod.azurecr.io}"
IMAGE_REPO="${IMAGE_REPO:-roleta-cloud}"
CDC_REPO="${CDC_REPO:-roleta-cdc-worker}"
ROLETA_TAG="${ROLETA_TAG:-azure-latest}"
CDC_TAG="${CDC_TAG:-azure-latest}"
APP_DIR="${APP_DIR:-/opt/roleta}"
DATA_DIR="${DATA_DIR:-$APP_DIR/data}"
ENV_FILE="$APP_DIR/.env"
COMPOSE="$APP_DIR/compose.azure.yml"
WWW_DIR="${WWW_DIR:-/var/www/roleta}"
WITH_PG_ARG=""
WITH_CDC=0
ALLOW_CANARY_SEED="${ALLOW_CANARY_SEED:-0}"

while (($# > 0)); do
  case "$1" in
    --with-pg)
      WITH_PG_ARG="--with-pg"
      ;;
    --with-cdc)
      WITH_CDC=1
      ;;
    --allow-canary-seed)
      ALLOW_CANARY_SEED=1
      ;;
    --help)
      sed -n '2,9p' "$0"
      exit 0
      ;;
    *)
      echo "ERRO: argumento desconhecido: $1" >&2
      exit 2
      ;;
  esac
  shift
done

if [ "$WITH_CDC" = "1" ] && [ -z "$WITH_PG_ARG" ]; then
  echo "ERRO: --with-cdc exige --with-pg; a Onda PG continua opt-in." >&2
  exit 2
fi
case "$ALLOW_CANARY_SEED" in
  0|1) ;;
  *) echo "ERRO: ALLOW_CANARY_SEED deve ser 0 ou 1" >&2; exit 2 ;;
esac

cd "$APP_DIR"
command -v az >/dev/null || { echo "ERRO: az CLI ausente" >&2; exit 1; }
command -v docker >/dev/null || { echo "ERRO: docker ausente" >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERRO: python3 ausente (validacao de state)" >&2; exit 1; }
[ -f "$COMPOSE" ] || { echo "ERRO: $COMPOSE ausente" >&2; exit 1; }
[ -x "$APP_DIR/kv-to-env.sh" ] || {
  echo "ERRO: kv-to-env.sh ausente/nao executavel em $APP_DIR" >&2
  exit 1
}

az login --identity >/dev/null

# 1) Dados somente no disco persistente gerenciado.
mkdir -p "$DATA_DIR"
MNT_TGT="$(findmnt -no TARGET --target "$DATA_DIR" 2>/dev/null || echo /)"
case "$MNT_TGT" in
  /mnt|/mnt/*)
    echo "ERRO: $DATA_DIR reside no resource disk efemero ($MNT_TGT)" >&2
    exit 1
    ;;
esac
echo "[deploy] data persistente: $DATA_DIR (mount: $MNT_TGT)" >&2

# 2) Resolve e baixa a imagem imutável.
echo "[deploy] resolvendo ${IMAGE_REPO}:${ROLETA_TAG} no $ACR_NAME ..." >&2
DIGEST="$(az acr repository show -n "$ACR_NAME" --image "${IMAGE_REPO}:${ROLETA_TAG}" --query digest -o tsv)"
[ -n "$DIGEST" ] || {
  echo "ERRO: digest ausente para ${IMAGE_REPO}:${ROLETA_TAG}" >&2
  exit 1
}
IMAGE_REF="${ACR_LOGIN}/${IMAGE_REPO}@${DIGEST}"
echo "[deploy] imagem: $IMAGE_REF" >&2
az acr login -n "$ACR_NAME" >/dev/null
docker pull "$IMAGE_REF"

# 3) Extrai artefatos da mesma imagem antes de alterar o runtime.
STAGE_ROOT="$(mktemp -d "$APP_DIR/.image-stage.XXXXXX")"
FRONTEND_STAGE=""
CONTAINER_ID=""
cleanup() {
  if [ -n "$CONTAINER_ID" ]; then
    docker rm "$CONTAINER_ID" >/dev/null 2>&1 || :
  fi
  [ -z "$FRONTEND_STAGE" ] || rm -rf "$FRONTEND_STAGE"
  rm -rf "$STAGE_ROOT"
}
trap cleanup EXIT

CONTAINER_ID="$(docker create "$IMAGE_REF")"
mkdir -p "$STAGE_ROOT/configs" "$STAGE_ROOT/frontend"
docker cp "$CONTAINER_ID:/app/server/configs/." "$STAGE_ROOT/configs/"
docker cp "$CONTAINER_ID:/app/frontend/." "$STAGE_ROOT/frontend/"
docker rm "$CONTAINER_ID" >/dev/null
CONTAINER_ID=""
[ -f "$STAGE_ROOT/frontend/index.html" ] || {
  echo "ERRO: a imagem nao contem frontend/index.html" >&2
  exit 1
}

if [ ! -d "$APP_DIR/server/configs" ]; then
  mkdir -p "$APP_DIR/server"
  cp -a "$STAGE_ROOT/configs" "$APP_DIR/server/configs"
fi

# Staging no mesmo filesystem do root do Caddy.
WWW_PARENT="$(dirname "$WWW_DIR")"
install -d -m 0755 "$WWW_PARENT"
chmod 0755 "$WWW_PARENT"
FRONTEND_STAGE="$(mktemp -d "$WWW_PARENT/.roleta-frontend.XXXXXX")"
cp -a "$STAGE_ROOT/frontend/." "$FRONTEND_STAGE/"
if find "$FRONTEND_STAGE" -type l -print -quit | grep -q .; then
  echo "ERRO: frontend da imagem contem link simbolico" >&2
  exit 1
fi
find "$FRONTEND_STAGE" -type d -exec chmod 0755 {} +
find "$FRONTEND_STAGE" -type f -exec chmod 0644 {} +
chown -R root:root "$FRONTEND_STAGE"

# 4) Segredos/DSN e imagem pinada; kv-to-env também prepara o cutover do Caddy.
"$APP_DIR/kv-to-env.sh" $WITH_PG_ARG
sed -i '/^ROLETA_IMAGE=/d' "$ENV_FILE"
printf 'ROLETA_IMAGE=%s\n' "$IMAGE_REF" >> "$ENV_FILE"

if [ "$WITH_CDC" = "1" ]; then
  CDC_DIGEST="$(az acr repository show -n "$ACR_NAME" --image "${CDC_REPO}:${CDC_TAG}" --query digest -o tsv)"
  [ -n "$CDC_DIGEST" ] || {
    echo "ERRO: digest ausente para ${CDC_REPO}:${CDC_TAG}" >&2
    exit 1
  }
  CDC_IMAGE="${ACR_LOGIN}/${CDC_REPO}@${CDC_DIGEST}"
  docker pull "$CDC_IMAGE"
  sed -i '/^CDC_IMAGE=/d' "$ENV_FILE"
  printf 'CDC_IMAGE=%s\n' "$CDC_IMAGE" >> "$ENV_FILE"
fi

# 5) MIG-0: sem dados reais, somente um canário explicitamente autorizado.
STATE_FILE="$DATA_DIR/state.json"
if [ ! -f "$STATE_FILE" ]; then
  if [ "$ALLOW_CANARY_SEED" != "1" ]; then
    echo "ERRO: $STATE_FILE ausente; copie os dados reais ou use --allow-canary-seed apenas no canário" >&2
    exit 1
  fi
  echo "[deploy] criando state.json sintético (canário autorizado)" >&2
  printf '%s\n' '{"__canary_seed__": true, "version": "1.6.0"}' > "$STATE_FILE"
fi
STATE_KIND="$(python3 -c 'import json, sys; d=json.load(open(sys.argv[1], encoding="utf-8")); print("canary" if d.get("__canary_seed__") is True else "real")' "$STATE_FILE")"
if [ "$STATE_KIND" = "canary" ] && [ "$ALLOW_CANARY_SEED" != "1" ]; then
  echo "ERRO: state.json marcado como __canary_seed__; deploy de produção bloqueado" >&2
  exit 1
fi
chmod 600 "$STATE_FILE"

# 6) Compose sem build. O profile CDC só existe quando explicitamente solicitado.
COMPOSE_CMD=(docker compose -f "$COMPOSE" --env-file "$ENV_FILE")
if [ "$WITH_CDC" = "1" ]; then
  COMPOSE_CMD+=(--profile cdc)
fi
"${COMPOSE_CMD[@]}" up -d --no-build

# 7) Healthcheck do backend.
echo -n "[deploy] aguardando health " >&2
st="starting"
for _ in $(seq 1 40); do
  st="$(docker inspect -f '{{.State.Health.Status}}' roleta-cloud 2>/dev/null || echo starting)"
  [ "$st" = "healthy" ] && break
  echo -n "." >&2
  sleep 3
done
echo "" >&2
[ "$st" = "healthy" ] || {
  echo "ERRO: container nao ficou healthy; frontend nao foi publicado" >&2
  exit 1
}

# 8) Publica frontend somente depois do backend saudável, com rollback local.
FRONTEND_BACKUP=""
if [ -e "$WWW_DIR" ] || [ -L "$WWW_DIR" ]; then
  FRONTEND_BACKUP="$WWW_PARENT/.roleta-frontend-previous.$(date -u +%Y%m%dT%H%M%SZ)"
  while [ -e "$FRONTEND_BACKUP" ] || [ -L "$FRONTEND_BACKUP" ]; do
    FRONTEND_BACKUP="${FRONTEND_BACKUP}.$RANDOM"
  done
  mv "$WWW_DIR" "$FRONTEND_BACKUP"
fi
if ! mv "$FRONTEND_STAGE" "$WWW_DIR"; then
  [ -z "$FRONTEND_BACKUP" ] || mv "$FRONTEND_BACKUP" "$WWW_DIR"
  echo "ERRO: nao foi possivel publicar frontend" >&2
  exit 1
fi
FRONTEND_STAGE=""

frontend_rollback() {
  rm -rf "$WWW_DIR"
  [ -z "$FRONTEND_BACKUP" ] || mv "$FRONTEND_BACKUP" "$WWW_DIR"
}

frontend_http_ok() {
  local site first_site asset
  site="$(sed -n 's/^SITE_ADDRESS=//p' /etc/caddy/caddy.env 2>/dev/null | sed -n '1p' | tr -d '"')"
  first_site="${site%%,*}"
  first_site="${first_site#"${first_site%%[![:space:]]*}"}"
  first_site="${first_site%"${first_site##*[![:space:]]}"}"
  for asset in / /app.js /style.css; do
    if [ -z "$first_site" ] || [[ "$first_site" == :* ]]; then
      curl -fsS --max-time 10 "http://127.0.0.1${asset}" >/dev/null || return 1
    else
      curl -fsS --max-time 15 \
        --resolve "${first_site}:443:127.0.0.1" \
        "https://${first_site}${asset}" >/dev/null || return 1
    fi
  done
}

if ! test -f "$WWW_DIR/index.html" || ! test -f "$WWW_DIR/app.js" || ! test -f "$WWW_DIR/style.css"; then
  frontend_rollback
  echo "ERRO: frontend publicado sem os tres artefatos obrigatorios" >&2
  exit 1
fi
if ! frontend_http_ok; then
  frontend_rollback
  echo "ERRO: frontend publicado, mas o Caddy nao retornou 200 para /, app.js e style.css" >&2
  exit 1
fi
[ -z "$FRONTEND_BACKUP" ] || rm -rf "$FRONTEND_BACKUP"

"${COMPOSE_CMD[@]}" ps
echo "[deploy] OK; backend healthy, frontend sincronizado, Caddy em 80/443." >&2

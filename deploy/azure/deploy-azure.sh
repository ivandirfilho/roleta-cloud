#!/usr/bin/env bash
# deploy-azure.sh — na VM Azure: baixa a imagem do ACR por DIGEST (imutável) e sobe
# o compose standalone. NÃO builda no host (C3/A1), NÃO toca a produção HostDime,
# NÃO liga o dual_write PG e NÃO altera DNS/NSG.
#
# Uso (root na VM, a partir de /opt/roleta com compose.azure.yml + Caddyfile + *.sh):
#   ./deploy-azure.sh                       # tag azure-latest, resolve o digest
#   ROLETA_TAG=azure-80fe40c ./deploy-azure.sh
#   ./deploy-azure.sh --with-pg             # repassa --with-pg ao kv-to-env
#
# Fluxo: MI login → checa disco persistente → resolve digest → docker pull →
#        seed configs/.env/state → compose up --no-build → espera health.
set -euo pipefail
umask 077

ACR_NAME="${ACR_NAME:-acrroletaprod}"
ACR_LOGIN="${ACR_LOGIN:-acrroletaprod.azurecr.io}"
IMAGE_REPO="${IMAGE_REPO:-roleta-cloud}"
ROLETA_TAG="${ROLETA_TAG:-azure-latest}"
APP_DIR="${APP_DIR:-/opt/roleta}"
DATA_DIR="${DATA_DIR:-$APP_DIR/data}"
ENV_FILE="$APP_DIR/.env"
COMPOSE="$APP_DIR/compose.azure.yml"
WITH_PG_ARG=""
[ "${1:-}" = "--with-pg" ] && WITH_PG_ARG="--with-pg"

cd "$APP_DIR"
command -v az >/dev/null     || { echo "ERRO: az CLI ausente" >&2; exit 1; }
command -v docker >/dev/null || { echo "ERRO: docker ausente" >&2; exit 1; }
[ -f "$COMPOSE" ] || { echo "ERRO: $COMPOSE ausente (copie deploy/azure/* p/ $APP_DIR)" >&2; exit 1; }
[ -x "$APP_DIR/kv-to-env.sh" ] || { echo "ERRO: kv-to-env.sh ausente/nao executavel em $APP_DIR" >&2; exit 1; }

az login --identity >/dev/null

# 1) Disco PERSISTENTE p/ os dados: fail-fast se cair no resource disk efêmero (/mnt).
mkdir -p "$DATA_DIR"
MNT_TGT="$(findmnt -no TARGET --target "$DATA_DIR" 2>/dev/null || echo /)"
case "$MNT_TGT" in
  /mnt|/mnt/*) echo "ERRO: $DATA_DIR reside no resource disk efemero ($MNT_TGT). Aponte p/ disco gerenciado." >&2; exit 1;;
esac
echo "[deploy] data em disco persistente: $DATA_DIR (mount: $MNT_TGT)" >&2

# 2) Resolve o DIGEST imutável da tag e faz login docker no ACR (via MI).
echo "[deploy] resolvendo digest de ${IMAGE_REPO}:${ROLETA_TAG} no $ACR_NAME ..." >&2
DIGEST="$(az acr repository show -n "$ACR_NAME" --image "${IMAGE_REPO}:${ROLETA_TAG}" --query digest -o tsv)"
[ -n "$DIGEST" ] || { echo "ERRO: nao encontrei o digest da tag ${ROLETA_TAG}" >&2; exit 1; }
IMAGE_REF="${ACR_LOGIN}/${IMAGE_REPO}@${DIGEST}"
echo "[deploy] imagem (imutavel): $IMAGE_REF" >&2

az acr login -n "$ACR_NAME" >/dev/null
docker pull "$IMAGE_REF"

# 3) Seed de server/configs a partir da imagem se ausente (o bind :ro precisa existir).
if [ ! -d "$APP_DIR/server/configs" ]; then
  echo "[deploy] semeando server/configs a partir da imagem ..." >&2
  cid="$(docker create "$IMAGE_REF")"
  mkdir -p "$APP_DIR/server"
  docker cp "$cid:/app/server/configs" "$APP_DIR/server/configs"
  docker rm "$cid" >/dev/null
fi

# 4) Segredos do KV -> .env (0600) e grava ROLETA_IMAGE (pin por digest).
"$APP_DIR/kv-to-env.sh" $WITH_PG_ARG
grep -q '^ROLETA_IMAGE=' "$ENV_FILE" && sed -i '/^ROLETA_IMAGE=/d' "$ENV_FILE"
printf 'ROLETA_IMAGE=%s\n' "$IMAGE_REF" >> "$ENV_FILE"

# 5) Seed de state.json SINTÉTICO (canary) se ausente — marcado NAO-PRODUCAO.
#    Necessário: com STATE_FILE setado, o load() (C1) falha fechado se o arquivo
#    nao existir. Os DADOS REAIS entram no passo humano de freeze+copia (pre-cutover).
if [ ! -f "$DATA_DIR/state.json" ]; then
  echo "[deploy] seed state.json sintetico (canary; NAO e producao) ..." >&2
  printf '%s\n' '{"__canary_seed__": true, "version": "1.6.0"}' > "$DATA_DIR/state.json"
fi
chmod 600 "$DATA_DIR/state.json" 2>/dev/null || true

# 6) Sobe SEM build.
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" up -d --no-build

# 7) Espera o healthcheck ficar healthy.
echo -n "[deploy] aguardando health " >&2
st="starting"
for _ in $(seq 1 40); do
  st="$(docker inspect -f '{{.State.Health.Status}}' roleta-cloud 2>/dev/null || echo starting)"
  [ "$st" = "healthy" ] && break
  echo -n "." >&2; sleep 3
done
echo "" >&2
echo "[deploy] health: $st" >&2
docker compose -f "$COMPOSE" ps
[ "$st" = "healthy" ] || { echo "AVISO: container nao ficou healthy — ver 'docker logs roleta-cloud'" >&2; exit 1; }
echo "[deploy] OK. Canary no ar (loopback 8765/8766). Caddy publica 80/443." >&2

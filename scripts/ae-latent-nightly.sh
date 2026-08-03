#!/bin/bash
# ae-latent-nightly.sh — mantém cw|ccw.spins_vectors.ae_latent em dia (H5 03/08).
#
# Contexto: nenhuma imagem de produção carrega joblib/scikit-learn (por design,
# hot path não depende de ML libs). O backfill roda num container EFÊMERO
# python:3.12-slim na rede do PG, montando o repo como /app. Idempotente:
# só processa rows com raw_features preenchido e ae_latent NULL.
#
# Uso (cron diário em /etc/cron.d/roleta-ae-latent):
#   25 4 * * * root /root/roleta-cloud/scripts/ae-latent-nightly.sh >> /var/log/roleta-ae-latent.log 2>&1
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
PG_NETWORK="${PG_NETWORK:-roleta-cloud_default}"
PIP_CACHE="${PIP_CACHE:-/root/.cache/pip}"

echo "[$(date -Is)] ae-latent-nightly start"

# DSN da mesma fonte que o CDC worker usa (worker está sempre up em produção).
DSN="$(docker exec roleta-cdc-worker printenv ROLETA_PG_DSN)"
if [ -z "$DSN" ]; then
    echo "[$(date -Is)] ERRO: ROLETA_PG_DSN vazio no roleta-cdc-worker" >&2
    exit 1
fi

mkdir -p "$PIP_CACHE"
docker run --rm \
    --network "$PG_NETWORK" \
    -v "$REPO_DIR":/app:ro \
    -v "$PIP_CACHE":/root/.cache/pip \
    -w /app \
    -e PYTHONPATH=/app \
    -e ROLETA_PG_DSN="$DSN" \
    python:3.12-slim \
    sh -c 'pip install --quiet --disable-pip-version-check "numpy==1.26.4" "scikit-learn==1.9.0" joblib psycopg2-binary && python scripts/backfill_ae_latent.py'
    # numpy pinado em 1.26.4: wheels do numpy>=2 exigem baseline x86-64-v2,
    # que a CPU deste host não suporta (mesma versão usada na imagem roleta-cloud).
    # scikit-learn 1.9.0 = versão com que os .joblib foram treinados (pickle exato).

echo "[$(date -Is)] ae-latent-nightly done"

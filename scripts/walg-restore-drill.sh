#!/usr/bin/env bash
# S-WALG-1 — wal-g restore drill em container PG isolado.
#
# Objetivo: validar que `wal-g backup-fetch` + recovery PG funciona sem
# tocar no postgres de produção. Idempotente — recria o container drill
# do zero a cada execução.
#
# Uso:
#   bash scripts/walg-restore-drill.sh           # último basebackup
#   bash scripts/walg-restore-drill.sh BACKUP    # backup específico
#
# Pré-requisitos: /etc/wal-g/env preenchido (mesmas creds usadas em prod),
# binário wal-g em /usr/local/bin/wal-g OU em /root/roleta-cloud/wal-g/wal-g.

set -euo pipefail

BACKUP_NAME="${1:-LATEST}"
DRILL_CONTAINER="roleta-pg-drill"
DRILL_VOLUME="roleta-pg-drill-data"
DRILL_PORT="5440"
WALG_BIN="${WALG_BIN:-/root/roleta-cloud/wal-g/wal-g}"

if [[ ! -f /etc/wal-g/env ]]; then
  echo "ERRO: /etc/wal-g/env nao encontrado. Abortando." >&2
  exit 1
fi

if [[ ! -x "${WALG_BIN}" ]]; then
  echo "ERRO: wal-g binario nao encontrado em ${WALG_BIN}. Set WALG_BIN=..." >&2
  exit 1
fi

echo "=== [1/6] Cleanup container/volume drill anteriores ==="
docker rm -f "${DRILL_CONTAINER}" 2>/dev/null || true
docker volume rm "${DRILL_VOLUME}" 2>/dev/null || true
docker volume create "${DRILL_VOLUME}" >/dev/null

echo "=== [2/6] Sobe PG drill vazio (sem inicializar) ==="
docker run -d --name "${DRILL_CONTAINER}" \
  -v "${DRILL_VOLUME}":/var/lib/postgresql/data \
  -v /etc/wal-g/env:/etc/wal-g/env:ro \
  -v /etc/ssl/certs:/etc/ssl/certs:ro \
  -v "${WALG_BIN}":/usr/local/bin/wal-g:ro \
  -e POSTGRES_PASSWORD=drill_only \
  -p "127.0.0.1:${DRILL_PORT}:5432" \
  --entrypoint sleep \
  pgvector/pgvector:pg15 infinity >/dev/null

echo "=== [3/6] Fetch basebackup ${BACKUP_NAME} via wal-g ==="
docker exec "${DRILL_CONTAINER}" bash -c '
  set -e
  . /etc/wal-g/env
  rm -rf /var/lib/postgresql/data/*
  /usr/local/bin/wal-g backup-fetch /var/lib/postgresql/data '"${BACKUP_NAME}"'
  # Fix 03/08: PG exige aspas SIMPLES no valor (aspas duplas = syntax error
  # no auto.conf) e recovery.signal para entrar em archive recovery.
  printf "restore_command = '"'"'. /etc/wal-g/env && /usr/local/bin/wal-g wal-fetch %%f %%p'"'"'\n" \
    > /var/lib/postgresql/data/postgresql.auto.conf
  touch /var/lib/postgresql/data/recovery.signal
  chown -R postgres:postgres /var/lib/postgresql/data
  chmod 700 /var/lib/postgresql/data
'

echo "=== [4/6] Inicia PG em recovery ==="
docker exec -d -u postgres "${DRILL_CONTAINER}" /usr/lib/postgresql/15/bin/postgres -D /var/lib/postgresql/data

# Fix 03/08: espera ativa (replay de WAL do B2 pode passar de 10s fixos).
for _ in $(seq 1 24); do
  sleep 5
  if docker exec -u postgres "${DRILL_CONTAINER}" pg_isready -q 2>/dev/null; then
    break
  fi
done

echo "=== [5/6] Smoke: lista databases + counts ==="
docker exec -u postgres "${DRILL_CONTAINER}" psql -U roleta -d roleta -c "\l" || true
docker exec -u postgres "${DRILL_CONTAINER}" psql -U roleta -d roleta \
  -c "SELECT COUNT(*) AS outbox FROM shared.outbox;" || true
docker exec -u postgres "${DRILL_CONTAINER}" psql -U roleta -d roleta \
  -c "SELECT COUNT(*) AS dna FROM shared.decision_dna;" || true

echo "=== [6/6] Drill concluido. Container '${DRILL_CONTAINER}' deixado vivo na porta ${DRILL_PORT} para inspecao. ==="
echo "Limpar manualmente: docker rm -f ${DRILL_CONTAINER} && docker volume rm ${DRILL_VOLUME}"

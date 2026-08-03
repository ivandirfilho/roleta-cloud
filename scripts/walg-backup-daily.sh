#!/usr/bin/env bash
# walg-backup-daily.sh — S4-BAK-2
# Roda no host, executa basebackup + retention dentro do container roleta-pg.
#
# Pré-requisitos:
#   - Container roleta-pg up (docker compose -f docker-compose.pg.yml)
#   - /etc/wal-g/env populado (chown postgres:postgres do container, chmod 600)
#   - /usr/local/bin/wal-g montado no container via bind (ver docker-compose.pg.yml)
#
# Política: retém 48 basebackups full (30min × 48 = 24h de janela FULL;
# antes era 7 = só 3h30 — auditoria 03/08). WALs órfãos saem pela regra de
# lifecycle 30d do bucket B2 — segurança em camadas.
#
# Log: /var/log/wal-g/backup.log (1 linha por execução para grep/Loki).
#
# Cron: /etc/cron.d/walg-backup (instalado por install-walg-cron.sh)

set -euo pipefail

CONTAINER=${WALG_CONTAINER:-roleta-pg}
RETAIN_FULL=${WALG_RETAIN_FULL:-48}
LOG_DIR=${WALG_LOG_DIR:-/var/log/wal-g}
LOG="${LOG_DIR}/backup.log"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

mkdir -p "${LOG_DIR}"

{
  echo "=== ${TS} START backup-push (container=${CONTAINER}) ==="
  docker exec -u postgres "${CONTAINER}" bash -c \
    'set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g backup-push /var/lib/postgresql/data'

  echo "=== ${TS} START delete-retention (keep FULL ${RETAIN_FULL}) ==="
  docker exec -u postgres "${CONTAINER}" bash -c \
    "set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g delete retain FULL ${RETAIN_FULL} --confirm"

  echo "=== ${TS} DONE ==="
} >> "${LOG}" 2>&1

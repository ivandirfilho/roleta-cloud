#!/usr/bin/env bash
# install-walg-cron.sh — S4-BAK-2
# Instala o cron diário 02:00 UTC para basebackup + retention.
# Idempotente: sobrescreve /etc/cron.d/walg-backup se já existir.

set -euo pipefail

SCRIPT_PATH=${WALG_SCRIPT_PATH:-/root/roleta-cloud/scripts/walg-backup-daily.sh}
CRON_FILE=/etc/cron.d/walg-backup

if [[ ! -x "${SCRIPT_PATH}" ]]; then
  echo "ERROR: ${SCRIPT_PATH} não existe ou não é executável. chmod +x?" >&2
  exit 1
fi

cat > "${CRON_FILE}" <<EOF
# WAL-G basebackup + retention diário 02:00 UTC (S4-BAK-2)
# Log: /var/log/wal-g/backup.log
MAILTO=""
0 2 * * * root ${SCRIPT_PATH}
EOF

chmod 644 "${CRON_FILE}"
echo "[ok] cron instalado em ${CRON_FILE}"
systemctl is-active cron >/dev/null && echo "[ok] cron service ativo" || {
  echo "[warn] cron service inativo; tentando start..."
  systemctl start cron
}

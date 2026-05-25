#!/usr/bin/env bash
# S-WALG-2 — Ativa wal-g com:
#   - archive_mode contínuo (cada WAL segment quando preenche)
#   - base backup a cada 30 minutos via cron
#
# IMPORTANTE: este script REINICIA o postgres uma vez para aplicar archive_mode.
# Planejar janela de baixo tráfego. Idempotente: pode ser rodado várias vezes.
#
# Pré-requisitos:
#   - container roleta-pg rodando
#   - wal-g binary disponível no host (apt install wal-g OU baixar do GitHub releases)
#   - diretório /var/lib/postgresql/wal-g montado como volume no container
set -euo pipefail

PG_CONT="${PG_CONT:-roleta-pg}"
WAL_DIR="${WAL_DIR:-/var/lib/postgresql/wal-g}"
PG_DATA="${PG_DATA:-/var/lib/postgresql/data}"
CRON_FREQ="${CRON_FREQ:-*/30 * * * *}"

echo "==> [1/6] Verificando wal-g binary"
if ! command -v wal-g >/dev/null 2>&1; then
    echo "wal-g não encontrado. Instale com:"
    echo "  curl -fLo /usr/local/bin/wal-g.tar.gz https://github.com/wal-g/wal-g/releases/download/v3.0.5/wal-g-pg-ubuntu-22.04-amd64.tar.gz"
    echo "  cd /tmp && tar -xzf /usr/local/bin/wal-g.tar.gz && mv wal-g-* /usr/local/bin/wal-g && chmod +x /usr/local/bin/wal-g"
    exit 1
fi

echo "==> [2/6] Criando diretório de backup"
docker exec "$PG_CONT" mkdir -p "$WAL_DIR"
docker exec "$PG_CONT" chown postgres:postgres "$WAL_DIR"

echo "==> [3/6] Ativando archive_mode no postgres"
docker exec "$PG_CONT" bash -c "
cat >> $PG_DATA/postgresql.conf <<'EOF'

# S-WALG-2 (idempotente)
archive_mode = on
archive_command = 'WALG_FILE_PREFIX=$WAL_DIR /usr/local/bin/wal-g wal-push %p'
archive_timeout = 60
wal_level = replica
EOF
" || true

echo "==> [4/6] Reiniciando postgres"
docker restart "$PG_CONT"
sleep 8

echo "==> [5/6] Validando archive_mode"
docker exec "$PG_CONT" psql -U roleta -d roleta -tc "SHOW archive_mode;" | grep -q on \
    && echo "OK archive_mode=on" \
    || { echo "FALHA: archive_mode não está ativo"; exit 2; }

echo "==> [6/6] Instalando cron a cada $CRON_FREQ"
CRON_LINE="$CRON_FREQ root WALG_FILE_PREFIX=$WAL_DIR /usr/local/bin/wal-g backup-push $PG_DATA >> /var/log/walg-backup.log 2>&1"
CRON_FILE="/etc/cron.d/walg-roleta"
echo "$CRON_LINE" > "$CRON_FILE"
chmod 644 "$CRON_FILE"
systemctl restart cron || service cron restart

echo
echo "===================================================="
echo "S-WALG-2 ATIVO:"
echo "  • archive_mode=on, archive_timeout=60s (WAL streaming contínuo)"
echo "  • base backup a cada 30 min via cron"
echo "  • backups em: $WAL_DIR"
echo "  • log: /var/log/walg-backup.log"
echo
echo "Verifique amanhã com:"
echo "  WALG_FILE_PREFIX=$WAL_DIR wal-g backup-list"
echo "===================================================="

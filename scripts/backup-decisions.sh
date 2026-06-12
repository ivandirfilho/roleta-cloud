#!/bin/bash
# C3 (12/06): backup diario do decisions.db — a FONTE PRIMARIA do produto
# nao tinha NENHUMA rotina de backup (so o PG/replica tinha, e o wal-g
# parou em 25/05). Premissa P1: as decisoes sao tomadas com os dados
# atuais — eles sao insubstituiveis.
#
# Estrategia: sqlite3 backup API (consistente com app vivo) via python do
# proprio container -> gzip -> rotacao 7 dias -> textfile metric p/ alerta.
#
# Instalar: /usr/local/bin/roleta-backup-decisions.sh (LF!)
# Cron:     /etc/cron.d/roleta-backup-decisions  (diario 03:15 UTC)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/root/backups/sqlite}"
CONTAINER="${CONTAINER:-roleta-cloud}"
DB_PATH="${DB_PATH:-/app/data/decisions.db}"
KEEP_DAYS="${KEEP_DAYS:-7}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"
LOG_FILE="${LOG_FILE:-/var/log/roleta-backup-decisions.log}"

exec >> "$LOG_FILE" 2>&1
log() { echo "[$(date -u +%FT%TZ)] $*"; }

mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%d_%H%M%S)
TMP_IN_CONTAINER="/app/data/_backup_${STAMP}.db"
OUT="$BACKUP_DIR/decisions_${STAMP}.db"

# Snapshot consistente via sqlite backup API (python ja existe na imagem).
docker exec "$CONTAINER" python -c "import sqlite3; s = sqlite3.connect('$DB_PATH'); d = sqlite3.connect('$TMP_IN_CONTAINER'); s.backup(d); d.close(); s.close()"
docker cp "$CONTAINER:$TMP_IN_CONTAINER" "$OUT"
docker exec "$CONTAINER" rm -f "$TMP_IN_CONTAINER"

gzip -f "$OUT"
SIZE=$(stat -c%s "${OUT}.gz")
log "BACKUP OK ${OUT}.gz (${SIZE} bytes)"

# Rotacao
find "$BACKUP_DIR" -name "decisions_*.db.gz" -mtime +"$KEEP_DAYS" -delete

# Metrica textfile (padrao do gap-check) p/ alerta RoletaBackupStale.
if [ -d "$TEXTFILE_DIR" ]; then
    {
        echo "# HELP roleta_decisions_backup_last_success_timestamp Unix ts do ultimo backup ok do decisions.db"
        echo "# TYPE roleta_decisions_backup_last_success_timestamp gauge"
        echo "roleta_decisions_backup_last_success_timestamp $(date +%s)"
        echo "# HELP roleta_decisions_backup_size_bytes Tamanho do ultimo backup comprimido"
        echo "# TYPE roleta_decisions_backup_size_bytes gauge"
        echo "roleta_decisions_backup_size_bytes ${SIZE}"
    } > "$TEXTFILE_DIR/roleta_backup_decisions.prom.tmp"
    mv "$TEXTFILE_DIR/roleta_backup_decisions.prom.tmp" "$TEXTFILE_DIR/roleta_backup_decisions.prom"
fi

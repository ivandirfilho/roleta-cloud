#!/bin/bash
# SP-03 (LEGADO) — este arquivo deixou de ter logica propria.
#
# Por anos existiram DUAS copias do deploy no repo (`tools/deploy_pull.sh`, mais
# antiga, e `scripts/roleta-deploy-pull.sh`, canonica com alembic). Manter as duas
# em sincronia era um convite a divergencia: uma correcao entrava numa e faltava na
# outra. Hoje o servidor roda a canonica (o binario instalado em /usr/local e
# byte-identico a ela), entao este arquivo virou um delegador fino — mantido apenas
# para nao quebrar quem ainda o referencie.
#
# NAO adicione logica de deploy aqui. O script real e scripts/roleta-deploy-pull.sh,
# e o entrypoint durável do servidor e scripts/roleta-deploy-launcher.sh.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
TARGET="${DEPLOY_SCRIPT:-$REPO_DIR/scripts/roleta-deploy-pull.sh}"

if [ ! -f "$TARGET" ]; then
    echo "[$(date -u +%FT%TZ)] DEPLOY FAIL: $TARGET ausente" >&2
    exit 1
fi

exec bash "$TARGET" "$@"

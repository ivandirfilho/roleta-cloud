#!/bin/bash
# Launcher ESTAVEL do deploy — instalado em /usr/local/bin/roleta-deploy-pull.sh.
#
# POR QUE ELE EXISTE
#   O systemd executa um caminho FORA do repo. Ate aqui, esse caminho era uma COPIA
#   congelada do script de deploy: qualquer melhoria versionada (por exemplo o passo
#   de observabilidade do OBS-INODE) so chegava em producao se alguem lembrasse de
#   reinstalar a copia a mao. Este stub troca "copia congelada" por "ponteiro":
#   ele nao contem NENHUMA logica de deploy, so resolve o script VERSIONADO e faz
#   `exec`. A partir da instalacao (unica) deste arquivo, toda mudanca no deploy
#   viaja pelo git como qualquer outro codigo.
#
#   Manter isto minusculo e proposital: quanto menos ele muda, menos vezes precisa
#   ser reinstalado. Ele nao deve ganhar logica nova — logica nova vai no script
#   versionado (tests/test_obs_reload.py trava esse contrato).
#
# INSTALACAO (uma vez, no servidor)
#   install -m755 scripts/roleta-deploy-launcher.sh /usr/local/bin/roleta-deploy-pull.sh
#
# ROLLBACK
#   O launcher sempre roda o script do checkout atual, entao reverter o deploy e
#   reverter o repo (`git reset --hard <sha bom>` em $REPO_DIR) — o proximo tick ja
#   usa a versao antiga. Para sair do esquema de launcher, basta reinstalar a copia:
#   install -m755 $REPO_DIR/scripts/roleta-deploy-pull.sh /usr/local/bin/roleta-deploy-pull.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
TARGET="${DEPLOY_SCRIPT:-$REPO_DIR/scripts/roleta-deploy-pull.sh}"

if [ ! -f "$TARGET" ]; then
    echo "[$(date -u +%FT%TZ)] LAUNCHER FAIL: $TARGET ausente — checkout de $REPO_DIR quebrado?" >&2
    exit 1
fi

exec bash "$TARGET" "$@"
